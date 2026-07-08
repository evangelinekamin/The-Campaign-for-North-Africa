"""Tests for structural adjudication (game.adjudication).

The dry-run the future Chief calls: it detects ENGINE-DETECTED conflicts in a
COMBINED batch of orders (over-stack, oversubscribed dump, road-cap) without ever
mutating real state. Also pins that invariants.check still raises exactly as
before now that its stacking logic is delegated to adjudication.stacking_violations.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import adjudication, invariants
from game.events import Phase, Side
from game.movement import TerrainMap
from game.policy import MoveOrder
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


def _state(units, supplies=(), *, initial_supply=None, consumed=None) -> GameState:
    terr = {(q, 0): Terrain.CLEAR for q in range(8)}
    return GameState(
        turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS, seed=1,
        weather="clear", vp=VP(), terrain=TerrainMap(terrain=terr),
        control={}, units=tuple(units), target_hex=(7, 0), supplies=tuple(supplies),
        consumed=consumed if consumed is not None else {},
        initial_supply=initial_supply if initial_supply is not None else {})


def _unit(uid, hex, sp=1, mob=Mobility.MOTORIZED, cpa=10, strength=3):
    return Unit(uid, Side.AXIS, hex, (StepRecord("s", strength),),
                mobility=mob, cpa=cpa, stacking_points=sp, oca=3, dca=3)


# --- Conflict shape -----------------------------------------------------------

def test_conflict_kind_matches_staff_adjudication_enum():
    # Conflict.kind must be one of the STAFF_ADJUDICATION `conflict` enum values
    # verbatim, so a ruling can drop it straight into the payload.
    for kind in ("over-stack", "oversubscribed-dump", "road-cap"):
        c = adjudication.Conflict(kind, (0, 0))
        assert c.kind == kind


# --- validate_batch: phase-start-illegal orders dropped silently -------------

def test_validate_batch_drops_off_map_destination_without_crashing():
    # A hallucinated destination off the map (no terrain there) is illegal at phase
    # start; the dry-run must drop it silently (the engine rejects it downstream), not
    # crash folding a unit onto a non-existent hex. Regression: a live model proposed
    # exactly this and the terrain lookup in stacking_violations raised KeyError.
    units = [_unit("A", (1, 0)), _unit("B", (2, 0))]
    conflicts = adjudication.validate_batch(_state(units), [MoveOrder("A", (41, -4))])
    assert conflicts == []


# --- validate_batch: over-stack ----------------------------------------------

def test_validate_batch_flags_combined_over_stack():
    # Two 3-point units each legal alone, but both ordered onto the same empty hex
    # -> 6 > 5 stacking limit: a conflict only the COMBINED batch reveals.
    units = [_unit("A", (1, 0), sp=3), _unit("B", (2, 0), sp=3)]
    state = _state(units)
    orders = [MoveOrder("A", (3, 0)), MoveOrder("B", (3, 0))]

    conflicts = adjudication.validate_batch(state, orders)

    over = [c for c in conflicts if c.kind == "over-stack"]
    assert over, "combined move onto one hex must flag over-stack"
    c = over[0]
    assert c.hex == (3, 0)
    assert set(c.unit_ids) == {"A", "B"}
    assert state.unit("A").hex == (1, 0)          # real state never mutated
    assert state.unit("B").hex == (2, 0)


# --- validate_batch: oversubscribed dump -------------------------------------

def test_validate_batch_flags_oversubscribed_dump():
    # Two motorized units (strength 3 -> fuel_cost 3 each, the 49.13 x-strength charge)
    # both draw from a dump holding 5 fuel: each 3 is individually satisfiable but the
    # combined draw 6 > pool 5, which the strength-scaled detector must surface.
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=10, fuel=5)
    units = [_unit("A", (0, 0)), _unit("B", (1, 0))]
    state = _state(units, [dump],
                   initial_supply={"AMMO": 10, "FUEL": 5}, consumed={"AMMO": 0, "FUEL": 0})
    orders = [MoveOrder("A", (2, 0)), MoveOrder("B", (3, 0))]

    conflicts = adjudication.validate_batch(state, orders)

    sub = [c for c in conflicts if c.kind == "oversubscribed-dump"]
    assert sub, "combined fuel draw exceeding the pool must flag oversubscribed-dump"
    c = sub[0]
    assert c.dump_id == "D"
    assert set(c.unit_ids) == {"A", "B"}
    assert state.supply("D").fuel == 5            # real state never mutated


# --- validate_batch: road-cap (approximate) ----------------------------------

def test_validate_batch_flags_road_cap_as_approximate():
    units = [_unit("A", (1, 0), sp=3), _unit("B", (2, 0), sp=3)]
    state = _state(units)
    orders = [MoveOrder("A", (3, 0)), MoveOrder("B", (3, 0))]

    conflicts = adjudication.validate_batch(state, orders)

    road = [c for c in conflicts if c.kind == "road-cap"]
    assert road, "destination exceeding the road/track limit must flag road-cap"
    assert road[0].approximate is True            # rule 9.33 destination proxy


# --- validate_batch: compatible orders ---------------------------------------

def test_validate_batch_returns_empty_for_compatible_orders():
    # Distinct light destinations, ample fuel: nothing conflicts.
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=10, fuel=10)
    units = [_unit("A", (0, 0), sp=1), _unit("B", (1, 0), sp=1)]
    state = _state(units, [dump],
                   initial_supply={"AMMO": 10, "FUEL": 10}, consumed={"AMMO": 0, "FUEL": 0})
    orders = [MoveOrder("A", (2, 0)), MoveOrder("B", (3, 0))]

    assert adjudication.validate_batch(state, orders) == []


def test_validate_batch_ignores_unknown_ids():
    state = _state([_unit("A", (1, 0))])
    assert adjudication.validate_batch(state, [MoveOrder("ghost", (3, 0))]) == []


# --- stacking_violations: single source of truth -----------------------------

def test_stacking_violations_flags_resting_over_stack():
    state = _state([_unit("A", (3, 0), sp=3), _unit("B", (3, 0), sp=3)])
    violations = adjudication.stacking_violations(state)
    assert len(violations) == 1
    assert violations[0].kind == "over-stack"
    assert violations[0].hex == (3, 0)


def test_stacking_violations_empty_when_within_limit():
    state = _state([_unit("A", (3, 0), sp=2), _unit("B", (3, 0), sp=3)])
    assert adjudication.stacking_violations(state) == []


# --- invariants delegation: behavior preserved (raise-first) -----------------

def test_invariants_still_raises_on_over_stack_unchanged():
    state = _state([_unit("A", (3, 0), sp=3), _unit("B", (3, 0), sp=3)])
    with pytest.raises(invariants.InvariantViolation) as exc:
        invariants.check(state)
    assert str(exc.value) == "stacking exceeded at (3, 0): 6 points (limit 5)"


def test_invariants_passes_when_within_limit():
    state = _state([_unit("A", (3, 0), sp=2), _unit("B", (4, 0), sp=3)])
    invariants.check(state)          # must not raise
