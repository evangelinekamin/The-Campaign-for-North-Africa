"""Orchestrator (brief §4.3, §4.4).

Walks the phase sequence, invokes the owning side's policy, validates orders at
the engine boundary (NOT via constrained decoding, §3.3), and emits events. The
only place RNG lives — outcomes are rolled here and baked into events so apply/
fold stay pure (§4.1).

MOVEMENT is now real: CPA-budget pathing over terrain with Zones of Control and
stacking (game.movement / game.zoc / game.stacking via game.tactics). COMBAT is
still a placeholder CRT (the real land combat — rule 11 — is the next slice).
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import combat, stacking, supply, tactics
from .apply import apply
from .events import Control, Event, EventKind, Phase, Side
from .hexmap import is_adjacent
from .invariants import check
from .policy import AttackOrder, MoveOrder, Policy
from .state import Coord, GameState

CONTROL_OF: dict[Side, Control] = {Side.AXIS: Control.AXIS, Side.ALLIED: Control.ALLIED}


@dataclass(frozen=True, slots=True)
class RunResult:
    initial: GameState
    events: list[Event]
    final: GameState
    winner: Side | None
    reason: str


class _Run:
    """Mutable driver wrapping immutable state — every change flows through apply()
    so live state equals fold(initial, events) by construction."""

    def __init__(self, initial: GameState):
        self.initial = initial
        self.state = initial
        self.rng = random.Random(initial.seed)
        self.events: list[Event] = []
        self._seq = 0

    def emit(self, kind: EventKind, side: Side, actor: str, payload: dict,
             rng_draws: tuple[int, ...] = ()) -> None:
        e = Event(self._seq, self.state.turn, self.state.phase, side, actor,
                  kind, payload, rng_draws)
        self._seq += 1
        self.state = apply(self.state, e)
        check(self.state)
        self.events.append(e)

    def d6(self) -> int:
        return self.rng.randint(1, 6)

    def go(self, phase: Phase, side: Side) -> None:
        self.emit(EventKind.PHASE_ADVANCED, Side.SYSTEM, "SYSTEM",
                  {"phase": phase.value, "active_side": side.value})


def run(initial: GameState, axis: Policy, allied: Policy) -> RunResult:
    r = _Run(initial)
    policies = {Side.AXIS: axis, Side.ALLIED: allied}
    r.emit(EventKind.GAME_INITIALIZED, Side.SYSTEM, "SYSTEM",
           {"seed": initial.seed, "max_turns": initial.max_turns})

    winner: Side | None = None
    reason = "campaign reached final turn"
    while True:
        _weather(r)
        for side in (Side.AXIS, Side.ALLIED):
            r.go(Phase.MOVEMENT, side)
            _movement(r, policies[side], side)
            r.go(Phase.COMBAT, side)
            _combat(r, policies[side], side)
        r.go(Phase.RECORD, Side.SYSTEM)
        _record_control(r)
        winner, reason = _victory(r)
        if winner is not None:
            break
        if r.state.turn >= r.state.max_turns:
            winner, reason = _final_decision(r)
            break
        r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM", {"turn": r.state.turn + 1})
        r.go(Phase.WEATHER, Side.SYSTEM)

    return RunResult(r.initial, r.events, r.state, winner, reason)


# --- phases ------------------------------------------------------------------

def _weather(r: _Run) -> None:
    die = r.d6()
    label, modifier = {
        1: ("storm", -2), 2: ("rain", -1), 3: ("clear", 0),
        4: ("clear", 0), 5: ("clear", 0), 6: ("hot", 0),
    }[die]
    r.emit(EventKind.WEATHER_ROLLED, Side.SYSTEM, "SYSTEM",
           {"weather": label, "move_modifier": modifier}, rng_draws=(die,))


def _movement(r: _Run, policy: Policy, side: Side) -> None:
    actor = f"{side.value}/Front"
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(r.state, side)
    for order in policy.movement(r.state, side):
        u = r.state.unit(order.unit_id)
        if u is None or not u.alive or u.side != side:
            _reject(r, side, actor, order, "no such living unit under this command")
            continue
        # Re-validate against current state — earlier moves this phase count.
        reach = tactics.reachable_for(r.state, u, enemy_zoc, enemy_occupied)
        if order.to == u.hex or order.to not in reach:
            _reject(r, side, actor, order,
                    "destination unreachable within CPA or blocked by ZOC")
            continue
        present = [x for x in r.state.units_at(order.to) if x.side == side]
        if not stacking.within_hex_limit(present + [u], r.state.terrain.terrain[order.to]):
            _reject(r, side, actor, order, "destination over stacking limit")
            continue
        if u.cp_used == 0:                          # first move this OpStage pays fuel (32.23)
            draws = supply.plan_draw(r.state, u, supply.FUEL, supply.fuel_cost(u))
            if draws is None:
                _reject(r, side, actor, order, "out of supply: no fuel in range")
                continue
            for sid, qty in draws:
                r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                       {"supply_id": sid, "commodity": supply.FUEL, "qty": qty, "unit_id": u.id})
        r.emit(EventKind.UNIT_MOVED, side, actor,
               {"unit_id": u.id, "from": list(u.hex), "to": list(order.to),
                "cp_spent": reach[order.to]})


def _reject(r: _Run, side: Side, actor: str, order: MoveOrder, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "move", "unit_id": order.unit_id, "to": list(order.to),
            "reason": reason})


def _combat(r: _Run, policy: Policy, side: Side) -> None:
    actor = f"{side.value}/Front"
    for order in policy.combat(r.state, side):
        attackers = [r.state.unit(a) for a in order.attacker_ids]
        attackers = [u for u in attackers
                     if u and u.alive and u.side == side and is_adjacent(u.hex, order.target)]
        defenders = list(r.state.enemies_at(order.target, side))
        if not attackers or not defenders:
            r.emit(EventKind.ORDER_REJECTED, side, actor,
                   {"order": "attack", "target": list(order.target),
                    "reason": "no valid attackers or empty target"})
            continue
        _resolve_combat(r, side, actor, attackers, defenders, order.target)


def _resolve_combat(r: _Run, side: Side, actor: str, attackers, defenders,
                    target: Coord) -> None:
    # Ammo gates participation (rule 32.21 / 15.15): a unit that cannot draw ammo
    # cannot assault; an unarmed defender adds no defensive strength but still
    # suffers losses. Charged before resolution (conservation holds per event).
    armed_atk = [u for u in attackers if _charge_ammo(r, side, actor, u, phasing=True)]
    if not armed_atk:
        r.emit(EventKind.ORDER_REJECTED, side, actor,
               {"order": "attack", "target": list(target),
                "reason": "attackers out of ammo"})
        return
    armed_def = [u for u in defenders if _charge_ammo(r, side, actor, u, phasing=False)]

    # Close Assault via the real differential engine (rule 15 / §15.79 CRT).
    feature = r.state.terrain.hexsides.get((armed_atk[0].hex, target))  # §15.33
    ab, asm, db, dsm = r.d6(), r.d6(), r.d6(), r.d6()
    res = combat.resolve(
        attacker_raw=sum(u.raw_offense for u in armed_atk),
        defender_raw=sum(u.raw_defense for u in armed_def),     # unarmed defenders -> 0
        attacker_strength=sum(u.strength for u in armed_atk),
        defender_strength=sum(u.strength for u in defenders),   # all defenders take losses
        def_terrain=r.state.terrain.terrain[target], attack_feature=feature,
        atk_roll=ab * 10 + asm, def_roll=db * 10 + dsm)
    r.emit(EventKind.COMBAT_RESOLVED, side, actor,
           {"target": list(target), "attackers": [u.id for u in armed_atk],
            "defenders": [u.id for u in defenders],
            "differential": res.differential, "column": res.column,
            "attacker_loss_pct": res.attacker_loss_pct,
            "defender_loss_pct": res.defender_loss_pct},
           rng_draws=(ab, asm, db, dsm))
    for uid, amount in _spread_losses(defenders, res.defender_steps_lost):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "defender"})
    for uid, amount in _spread_losses(armed_atk, res.attacker_steps_lost):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "attacker"})


def _charge_ammo(r: _Run, side: Side, actor: str, unit, *, phasing: bool) -> bool:
    draws = supply.plan_draw(r.state, unit, supply.AMMO,
                             supply.ammo_cost(unit, phasing=phasing))
    if draws is None:
        return False
    for sid, qty in draws:
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": sid, "commodity": supply.AMMO, "qty": qty, "unit_id": unit.id})
    return True


def _spread_losses(units, total: int) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    remaining = total
    for u in sorted(units, key=lambda x: -x.strength):
        if remaining <= 0:
            break
        take = min(remaining, u.strength)
        if take > 0:
            out.append((u.id, take))
            remaining -= take
    return out


def _record_control(r: _Run) -> None:
    for coord in r.state.terrain.terrain:
        occ = r.state.units_at(coord)
        sides = {u.side for u in occ}
        new = CONTROL_OF[next(iter(sides))] if len(sides) == 1 else r.state.control_of(coord)
        if new != r.state.control_of(coord):
            r.emit(EventKind.HEX_CONTROL_CHANGED, Side.SYSTEM, "SYSTEM",
                   {"coord": list(coord), "control": new.value})


def _victory(r: _Run) -> tuple[Side | None, str]:
    s = r.state
    ctrl = s.control_of(s.target_hex)
    r.emit(EventKind.VICTORY_CHECKED, Side.SYSTEM, "SYSTEM",
           {"axis": 100 if ctrl == Control.AXIS else 0,
            "allied": 100 if ctrl == Control.ALLIED else 0})
    if ctrl == Control.AXIS:
        return Side.AXIS, "Axis strategic victory: objective captured and held"
    if not s.living(Side.ALLIED):
        return Side.AXIS, "Axis victory by annihilation"
    if not s.living(Side.AXIS):
        return Side.ALLIED, "Allied victory by annihilation"
    return None, ""


def _final_decision(r: _Run) -> tuple[Side, str]:
    if r.state.control_of(r.state.target_hex) == Control.AXIS:
        return Side.AXIS, "Axis held the objective at the final turn"
    return Side.ALLIED, "Allied held the line to the final turn"


def determinism_signature(events: list[Event]) -> str:
    from .events import log_to_json
    return log_to_json(events)
