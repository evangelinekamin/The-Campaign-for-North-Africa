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

import math
import random
from dataclasses import dataclass

from . import combat, combat_tables, stacking, supply, tactics
from .apply import apply
from .events import Control, Event, EventKind, Phase, Side
from .hexmap import distance, is_adjacent, neighbors
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
            _supply_movement(r, policies[side], side)   # supply follows the army (32.3)
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


def _supply_movement(r: _Run, policy: Policy, side: Side) -> None:
    """Relocate supply units with the advancing army (rule 32.3): a carried dump
    moves up to CPA 15 as medium-truck, costs a flat 1 Fuel Point (32.24) drawn
    from its own trucks, and must end stacked with a friendly combat unit (32.33).
    Validated at the boundary like every other order."""
    actor = f"{side.value}/Logistics"
    for order in policy.supply_orders(r.state, side):
        su = r.state.supply(order.supply_id)
        if su is None or su.side != side or su.empty:
            _reject_supply(r, side, actor, order, "no such active supply unit")
            continue
        if order.to == su.hex or order.to not in supply.reachable_moves(r.state, su):
            _reject_supply(r, side, actor, order, "beyond CPA 15 or blocked by ZOC")
            continue
        if not any(u.side == side and u.is_combat for u in r.state.units_at(order.to)):
            _reject_supply(r, side, actor, order, "must end stacked with a friendly combat unit")
            continue
        if su.fuel < supply.SUPPLY_MOVE_FUEL:
            _reject_supply(r, side, actor, order, "out of fuel to move")
            continue
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": su.id, "commodity": supply.FUEL,
                "qty": supply.SUPPLY_MOVE_FUEL, "unit_id": su.id})
        r.emit(EventKind.SUPPLY_MOVED, side, actor,
               {"supply_id": su.id, "from": list(su.hex), "to": list(order.to)})


def _reject_supply(r: _Run, side: Side, actor: str, order, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "supply_move", "supply_id": order.supply_id,
            "to": list(order.to), "reason": reason})


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
    # Morale is rolled FIRST (rule 15 order): each side's 17.4 roll adjusts its
    # Basic Morale by Cohesion, and the difference shifts the assault column (15.62).
    atk_m, atk_md = _adjusted_morale(r, armed_atk)
    def_m, def_md = _adjusted_morale(r, defenders)
    ab, asm, db, dsm = r.d6(), r.d6(), r.d6(), r.d6()
    res = combat.resolve(
        attacker_raw=sum(u.raw_offense for u in armed_atk),
        defender_raw=sum(u.raw_defense for u in armed_def),     # unarmed defenders -> 0
        attacker_strength=sum(u.strength for u in armed_atk),
        defender_strength=sum(u.strength for u in defenders),   # all defenders take losses
        def_terrain=r.state.terrain.terrain[target], attack_feature=feature,
        atk_roll=ab * 10 + asm, def_roll=db * 10 + dsm,
        morale_shift=atk_m - def_m,
        attacker_ca_penalty=_combined_arms_penalty(armed_atk),      # rule 15.4
        defender_ca_penalty=_combined_arms_penalty(armed_def))
    r.emit(EventKind.COMBAT_RESOLVED, side, actor,
           {"target": list(target), "attackers": [u.id for u in armed_atk],
            "defenders": [u.id for u in defenders],
            "differential": res.differential, "column": res.column,
            "morale_shift": atk_m - def_m,
            "attacker_loss_pct": res.attacker_loss_pct,
            "defender_loss_pct": res.defender_loss_pct,
            "attacker_captured": res.attacker_captured,
            "defender_captured": res.defender_captured,
            "attacker_engaged": res.attacker_engaged,
            "retreat_hexes": res.retreat_hexes},
           rng_draws=(*atk_md, *def_md, ab, asm, db, dsm))
    for uid, amount in _spread_losses(defenders, res.defender_steps_lost):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "defender"})
    for uid, amount in _spread_losses(armed_atk, res.attacker_steps_lost):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "attacker"})
    # Cohesion: 30%+ losses disorganize the involved units (rule 15.87). Recovery
    # (Reorganization Points, rule 20) is deferred, so Cohesion only falls -- flagged.
    if res.attacker_loss_pct >= 30:
        for u in armed_atk:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -3})
    if res.defender_loss_pct >= 30:
        for u in defenders:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -3})
    if res.retreat_hexes > 0:                                   # rule 15.8 / 15.82
        _retreat(r, side, actor, [d.id for d in defenders], armed_atk[0].hex, res.retreat_hexes)


def _combined_arms_penalty(units) -> int:
    """Combined arms (rule 15.4): tanks unsupported by an equal TOE of infantry /
    MG / heavy-weapons units lose Actual close-assault points -- 1 for every 1-3
    unsupported tank TOE points, capped at 4. Tanks only (recce and SP artillery,
    which have Armor Protection but are not tanks, are exempt). Off and def alike."""
    tank_toe = sum(u.strength for u in units if u.is_tank)
    if tank_toe == 0:
        return 0
    support = sum(u.strength for u in units
                  if u.is_combat and not u.is_tank and not u.is_armor and not u.is_gun)
    unsupported = max(0, tank_toe - support)
    return min(4, math.ceil(unsupported / 3))


def _adjusted_morale(r: _Run, units) -> tuple[int, tuple[int, int]]:
    """Adjusted Morale of a close-assault stack (rule 15.6): the LARGEST unit's
    Basic Morale (17.32), plus the 17.4 modifier rolled at its Cohesion level, +1
    if Rommel is present (17.28), clamped to -3..+3 (17.23). Returns (morale, the
    two dice rolled). A SURR result is taken as the -4 penalty -- full
    surrender-elimination (17.25) is deferred + flagged."""
    live = [u for u in units if u.strength > 0]
    if not live:
        return 0, (0, 0)
    largest = max(live, key=lambda u: (u.stacking_points, u.strength))
    d1, d2 = r.d6(), r.d6()
    mod = combat_tables.morale_modifier(largest.cohesion, d1 * 10 + d2)
    if mod == "SURR":
        mod = -4
    m = largest.morale + mod + (1 if any("Rommel" in u.id for u in live) else 0)
    return max(-3, min(3, m)), (d1, d2)


def _retreat(r: _Run, atk_side: Side, actor: str, defender_ids: list[str],
             attacker_hex: Coord, n: int) -> None:
    """Retreat the surviving defenders n hexes away from the attacker, toward the
    nearest friendly supply/city, never into enemy ZOC or enemy units (rule 15.82);
    each hex that cannot be retreated costs an extra 10% loss. The stack retreats
    together. Retreat CP cost (15.82) is not charged yet (flagged)."""
    survivors = [u for u in (r.state.unit(uid) for uid in defender_ids) if u and u.alive]
    if not survivors:
        return
    def_side = survivors[0].side
    enemy_zoc, enemy_occ = tactics.enemy_zoc_and_occupied(r.state, def_side)
    friendly = frozenset(u.hex for u in r.state.living(def_side))
    blocked = (enemy_zoc - friendly) | enemy_occ
    supplies = [s.hex for s in r.state.active_supplies(def_side)]

    cur = survivors[0].hex
    done = 0
    for _ in range(n):
        cands = [nb for nb in neighbors(cur)
                 if nb in r.state.terrain.terrain and nb not in blocked
                 and distance(nb, attacker_hex) > distance(cur, attacker_hex)]
        if not cands:
            break
        occupied = frozenset(u.hex for u in r.state.living(def_side))

        def _key(nb):
            sup = min((distance(nb, s) for s in supplies), default=0)
            return (nb in occupied, sup, -distance(nb, attacker_hex), nb)
        cur = min(cands, key=_key)
        done += 1

    if done > 0:
        for u in survivors:
            r.emit(EventKind.UNIT_RETREATED, atk_side, actor,
                   {"unit_id": u.id, "from": list(u.hex), "to": list(cur), "hexes": done})
    for _ in range(n - done):                                   # 15.82: 10% per un-retreated hex
        for u in survivors:
            cur_u = r.state.unit(u.id)
            extra = math.ceil(0.10 * cur_u.strength)
            if extra > 0:
                r.emit(EventKind.STEP_LOST, atk_side, actor,
                       {"unit_id": u.id, "amount": min(extra, cur_u.strength), "role": "defender"})


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
