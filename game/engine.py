"""Orchestrator (brief §4.3, §4.4).

Walks the phase sequence, invokes the owning side's policy, validates orders
against the rules, and emits events. This is the only place RNG lives — outcomes
are rolled here and baked into events so that apply/fold stay pure (§4.1).

Validation lives here, at the engine boundary — NOT in constrained decoding
(§3.3, the load-bearing decision): a policy emits permissive orders; the engine
returns typed rejections with machine-readable reasons; in Phase 1 the agent
revises on a bounded retry. The scripted policy just eats the rejection.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .apply import apply
from .events import (Control, Event, EventKind, Phase, Side, log_to_json)
from .invariants import check
from .policy import AttackOrder, MoveOrder, Policy, BASE_MOVE_ALLOWANCE, STACK_LIMIT
from .state import Coord, GameState, adjacent

CONTROL_OF: dict[Side, Control] = {Side.AXIS: Control.AXIS, Side.ALLIED: Control.ALLIED}

# Toy Combat Results Table: odds-bucket x die(1-6) -> (defender_loss, attacker_loss)
# in steps. Real CRTs are transcribed from rule 11.0 / the charts sheet later.
_CRT: dict[str, dict[int, tuple[int, int]]] = {
    "low":   {1: (0, 2), 2: (0, 1), 3: (1, 1), 4: (1, 1), 5: (1, 0), 6: (2, 0)},
    "even":  {1: (0, 1), 2: (1, 1), 3: (1, 1), 4: (1, 0), 5: (2, 0), 6: (2, 1)},
    "good":  {1: (1, 1), 2: (1, 0), 3: (2, 0), 4: (2, 0), 5: (2, 1), 6: (3, 0)},
    "great": {1: (1, 0), 2: (2, 0), 3: (2, 0), 4: (3, 0), 5: (3, 0), 6: (3, 1)},
}


def _bucket(odds: float) -> str:
    if odds < 1.0:
        return "low"
    if odds < 2.0:
        return "even"
    if odds < 3.0:
        return "good"
    return "great"


@dataclass(frozen=True, slots=True)
class RunResult:
    initial: GameState
    events: list[Event]
    final: GameState
    winner: Side | None
    reason: str


class _Run:
    """Mutable driver wrapping an immutable state — every change flows through
    apply() so the live state equals fold(initial, events) by construction."""

    def __init__(self, initial: GameState):
        self.initial = initial
        self.state = initial
        self.rng = random.Random(initial.seed)
        self.initial_fuel = sum(u.fuel for u in initial.units)
        self.events: list[Event] = []
        self._seq = 0

    def emit(self, kind: EventKind, side: Side, actor: str, payload: dict,
             rng_draws: tuple[int, ...] = ()) -> None:
        e = Event(self._seq, self.state.turn, self.state.phase, side, actor,
                  kind, payload, rng_draws)
        self._seq += 1
        self.state = apply(self.state, e)
        check(self.state, self.initial_fuel)
        self.events.append(e)

    def d6(self) -> int:
        return self.rng.randint(1, 6)

    # --- phase transitions ---------------------------------------------------
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
        r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM",
               {"turn": r.state.turn + 1})
        r.go(Phase.WEATHER, Side.SYSTEM)

    return RunResult(r.initial, r.events, r.state, winner, reason)


# --- phase implementations ---------------------------------------------------

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
    for order in policy.movement(r.state, side):
        ok, info = _validate_move(r.state, order, side)
        if not ok:
            r.emit(EventKind.ORDER_REJECTED, side, actor,
                   {"order": "move", "unit_id": order.unit_id,
                    "to": list(order.to), "reason": info})
            continue
        cost = info["cost"]
        unit = r.state.unit(order.unit_id)
        r.emit(EventKind.UNIT_MOVED, side, actor,
               {"unit_id": order.unit_id, "from": list(unit.hex),
                "to": list(order.to), "fuel_cost": cost,
                "fuel_after": unit.fuel - cost})


def _validate_move(state: GameState, order: MoveOrder, side: Side) -> tuple[bool, dict | str]:
    unit = state.unit(order.unit_id)
    if unit is None or not unit.alive or unit.side != side:
        return False, "no such living unit under this command"
    dest = state.hex_at(order.to)
    if dest is None:
        return False, "destination off-map"
    distance = abs(order.to[0] - unit.hex[0]) + abs(order.to[1] - unit.hex[1])
    if distance == 0:
        return False, "no movement"
    cost = distance * dest.move_cost
    allowance = max(0, BASE_MOVE_ALLOWANCE + state.move_modifier)
    if cost > allowance:
        return False, f"insufficient movement allowance: need {cost}, have {allowance}"
    if unit.fuel < cost:
        return False, f"insufficient fuel: need {cost}, have {unit.fuel:g}"
    if state.enemies_at(order.to, side):
        return False, "destination occupied by enemy"
    friendly = [u for u in state.units_at(order.to) if u.side == side]
    if len(friendly) >= STACK_LIMIT:
        return False, "destination over stacking limit"
    return True, {"cost": cost}


def _combat(r: _Run, policy: Policy, side: Side) -> None:
    actor = f"{side.value}/Front"
    for order in policy.combat(r.state, side):
        attackers = [r.state.unit(a) for a in order.attacker_ids]
        attackers = [u for u in attackers if u and u.alive and u.side == side
                     and adjacent(u.hex, order.target)]
        defenders = list(r.state.enemies_at(order.target, side))
        if not attackers or not defenders:
            r.emit(EventKind.ORDER_REJECTED, side, actor,
                   {"order": "attack", "target": list(order.target),
                    "reason": "no valid attackers or empty target"})
            continue
        _resolve_combat(r, side, actor, attackers, defenders, order.target)


def _resolve_combat(r: _Run, side: Side, actor: str, attackers, defenders,
                    target: Coord) -> None:
    atk = sum(u.strength for u in attackers)
    dfn = sum(u.strength for u in defenders)
    odds = atk / dfn
    bucket = _bucket(odds)
    die = r.d6()
    def_loss, atk_loss = _CRT[bucket][die]

    r.emit(EventKind.COMBAT_RESOLVED, side, actor,
           {"target": list(target), "attackers": [u.id for u in attackers],
            "defenders": [u.id for u in defenders],
            "odds": round(odds, 2), "bucket": bucket,
            "defender_loss": def_loss, "attacker_loss": atk_loss},
           rng_draws=(die,))

    for uid, amount in _spread_losses(defenders, def_loss):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "defender"})
    for uid, amount in _spread_losses(attackers, atk_loss):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "attacker"})


def _spread_losses(units, total: int) -> list[tuple[str, int]]:
    """Distribute `total` step losses across units, strongest first; emit only
    the units that actually lose strength (so each STEP_LOST is meaningful)."""
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
    for h in r.state.hexes:
        occ = r.state.units_at(h.coord)
        sides = {u.side for u in occ}
        if len(sides) == 1:
            new = CONTROL_OF[next(iter(sides))]
        else:
            new = h.control  # empty or contested -> ground stays as it was
        if new != h.control:
            r.emit(EventKind.HEX_CONTROL_CHANGED, Side.SYSTEM, "SYSTEM",
                   {"coord": list(h.coord), "control": new.value})


def _victory(r: _Run) -> tuple[Side | None, str]:
    s = r.state
    tgt = s.hex_at(s.target_hex)
    axis_vp = 100 if tgt.control == Control.AXIS else 0
    allied_vp = 100 if tgt.control == Control.ALLIED else 0
    r.emit(EventKind.VICTORY_CHECKED, Side.SYSTEM, "SYSTEM",
           {"axis": axis_vp, "allied": allied_vp})

    if tgt.control == Control.AXIS:
        return Side.AXIS, "Axis strategic victory: objective captured and held"
    if not s.living(Side.ALLIED):
        return Side.AXIS, "Axis victory by annihilation"
    if not s.living(Side.AXIS):
        return Side.ALLIED, "Allied victory by annihilation"
    return None, ""


def _final_decision(r: _Run) -> tuple[Side, str]:
    s = r.state
    if s.hex_at(s.target_hex).control == Control.AXIS:
        return Side.AXIS, "Axis held the objective at the final turn"
    return Side.ALLIED, "Allied held the line to the final turn"


def determinism_signature(events: list[Event]) -> str:
    return log_to_json(events)
