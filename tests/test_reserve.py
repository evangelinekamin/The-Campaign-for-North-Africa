"""Rule 18 -- Reserve Status, the counterpunch held back to exploit a hole in the line.

Two per-OpStage scalars on Unit (reserve tier 0/1/2 + the release tier) mirror the `engaged`
marker: designated before Movement (18.11-18.12), released at the inter-pulse Release Segment
(18.13/48 V.H.4), reset at the OpStage boundary (18.14). A Reserve I shuffles one hex CP-free
(18.22), a Reserve II is frozen, and a unit released from Reserve II is capped at half its CPA
(18.24). All inert unless a Policy opts in, so every current scenario is byte-identical.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import tactics
from game.apply import _reset_opstage, apply
from game.engine import (_continual_movement, _movement, _reserve_designation, _reserve_release,
                         _Run, determinism_signature, run)
from game.events import EventKind, Phase, Side
from game.hexmap import Coord
from game.movement import TerrainMap
from game.policy import MoveOrder, Policy, ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


# --- fixtures ----------------------------------------------------------------

def _grid(n: int = 10) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _unit(uid: str, side: Side, hex_: Coord, *, cpa: int = 40, reserve: int = 0,
          reserve_released: int = 0) -> Unit:
    return Unit(uid, side, hex_, (StepRecord("x", 6),), Mobility.MOTORIZED,
                cpa=cpa, stacking_points=3, oca=4, dca=4, cohesion=6,
                reserve=reserve, reserve_released=reserve_released)


def _state(units, *, dumps=(), initial=None) -> GameState:
    init = dict(initial or {})
    return GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                     seed=7, weather="normal", vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=(0, 0), supplies=tuple(dumps),
                     consumed={k: 0 for k in init}, initial_supply=init)


class _Designator(Policy):
    def __init__(self, designate=(), release=()):
        self._d = list(designate)
        self._r = list(release)

    def movement(self, state, side):
        return []

    def combat(self, state, side):
        return []

    def reserve_designation(self, state, side):
        return list(self._d)

    def reserve_release(self, state, side):
        return list(self._r)


# --- designation (18.11-18.12) -----------------------------------------------

def test_designation_places_reserve_one_and_emits_the_phase():
    u = _unit("A1", Side.AXIS, (2, 0))
    r = _Run(_state([u]))
    _reserve_designation(r, _Designator(designate=["A1"]), Side.AXIS)
    assert any(e.kind == EventKind.PHASE_ADVANCED and e.payload["phase"] == "RESERVE"
               for e in r.events)
    assert any(e.kind == EventKind.RESERVE_DESIGNATED for e in r.events)
    assert r.state.unit("A1").reserve == 1


def test_designation_of_nothing_is_byte_silent():
    u = _unit("A1", Side.AXIS, (2, 0))
    r = _Run(_state([u]))
    _reserve_designation(r, _Designator(), Side.AXIS)
    assert r.events == []


# --- the 18.22 shuffle / freeze in _movement ---------------------------------

def test_reserve_two_unit_is_frozen():
    frozen = _unit("A1", Side.AXIS, (2, 0), reserve=2)
    enemy = _unit("E", Side.ALLIED, (0, 0))

    class _P(Policy):
        def movement(self, state, side):
            return [MoveOrder("A1", (3, 0))]
        def combat(self, state, side):
            return []
    r = _Run(_state([frozen, enemy]))
    _movement(r, {Side.AXIS: _P(), Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    assert r.state.unit("A1").hex == (2, 0)             # 18.22: never moves
    assert any(e.kind == EventKind.ORDER_REJECTED and "18.22" in e.payload["reason"]
               for e in r.events)


def test_reserve_one_unit_shuffles_one_hex_cp_free():
    res = _unit("A1", Side.AXIS, (5, 0), reserve=1)     # far from any enemy -> out of enemy ZOC

    class _P(Policy):
        def movement(self, state, side):
            return [MoveOrder("A1", (5, 1))]            # a single adjacent hex
        def combat(self, state, side):
            return []
    r = _Run(_state([res]))
    _movement(r, {Side.AXIS: _P(), Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    moved = r.state.unit("A1")
    assert moved.hex == (5, 1)
    assert moved.cp_used == 0.0                         # 18.22: CP-FREE, no overage


def test_reserve_one_may_not_shuffle_more_than_one_hex():
    res = _unit("A1", Side.AXIS, (5, 0), reserve=1)

    class _P(Policy):
        def movement(self, state, side):
            return [MoveOrder("A1", (7, 0))]            # two hexes -- illegal
        def combat(self, state, side):
            return []
    r = _Run(_state([res]))
    _movement(r, {Side.AXIS: _P(), Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    assert r.state.unit("A1").hex == (5, 0)
    assert any(e.kind == EventKind.ORDER_REJECTED for e in r.events)


# --- release (18.13) ---------------------------------------------------------

def test_release_clears_the_chosen_and_flips_the_rest():
    a = _unit("A1", Side.AXIS, (2, 0), reserve=1)       # released
    b = _unit("A2", Side.AXIS, (3, 0), reserve=1)       # unreleased -> flips to II
    r = _Run(_state([a, b]))
    released = _reserve_release(r, _Designator(release=["A1"]), Side.AXIS)
    assert released == frozenset({"A1"})
    assert r.state.unit("A1").reserve == 0
    assert r.state.unit("A1").reserve_released == 1     # released FROM tier I
    assert r.state.unit("A2").reserve == 2              # 18.13: unreleased I -> II


def test_release_from_reserve_two_records_tier_two():
    a = _unit("A1", Side.AXIS, (2, 0), reserve=2)
    r = _Run(_state([a]))
    _reserve_release(r, _Designator(release=["A1"]), Side.AXIS)
    assert r.state.unit("A1").reserve == 0
    assert r.state.unit("A1").reserve_released == 2


# --- 18.24 the half-CPA cap --------------------------------------------------

def test_reserve_two_release_halves_the_cp_ceiling():
    base = _unit("A1", Side.AXIS, (0, 0), cpa=40)
    capped = replace(base, reserve_released=2)
    ez, eo = tactics.enemy_zoc_and_occupied(_state([base]), Side.AXIS)
    normal = tactics.reachable_for(_state([base]), base, ez, eo)
    half = tactics.reachable_for(_state([capped]), capped, ez, eo)
    # the 18.24 cap must strictly shrink the reachable set (half its CPA ceiling)
    assert max(half.values()) < max(normal.values())


# --- 18.14 the OpStage reset -------------------------------------------------

def test_reserve_resets_at_the_opstage_boundary():
    u = _unit("A1", Side.AXIS, (2, 0), reserve=2, reserve_released=1)
    reset = _reset_opstage((u,))[0]
    assert reset.reserve == 0 and reset.reserve_released == 0


# --- 18.25 released units feed the next pulse's eligible ----------------------

def test_released_units_feed_the_next_pulse_eligible():
    # A released reserve far from the enemy (outside the 8.23 two-hex zone) must still be able to
    # exploit in the ensuing pulse via the 18.25 exception -- proven by _reserve_release feeding
    # _continual_movement's `also` set, letting the far unit move where the 8.23 gate would refuse.
    far = _unit("A-res", Side.AXIS, (8, 0), reserve=1, cpa=60)
    enemy = _unit("E", Side.ALLIED, (0, 0))
    dump = SupplyUnit("D", Side.AXIS, (8, 0), ammo=0, fuel=10_000)
    st = _state([far, enemy], dumps=[dump], initial={"FUEL": 10_000})
    st = replace(st, target_hex=(8, -8))

    class _P(Policy):
        def __init__(self):
            self._n = 0
        def movement(self, state, side):
            u = state.unit("A-res")
            if u is None:
                return []
            return [MoveOrder("A-res", (8, -1))]        # one step toward (8,-8)
        def combat(self, state, side):
            return []
        def reserve_release(self, state, side):
            return ["A-res"]                            # release it at the first Release Segment
        def continual_movement(self, state, side):
            self._n += 1
            return [MoveOrder("A-res", (8, -1))] if self._n <= 1 else []
    r = _Run(st)
    _continual_movement(r, {Side.AXIS: _P(), Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    assert r.state.unit("A-res").hex == (8, -1)         # moved despite being outside the 8.23 zone


# --- byte-identity of the shipped scenarios ----------------------------------

def test_scripted_scenarios_are_byte_identical_under_reserve():
    for factory in (coastal_corridor, rommels_arrival):
        a = run(factory(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        b = run(factory(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert determinism_signature(a.events) == determinism_signature(b.events)
        assert not any(e.kind in (EventKind.RESERVE_DESIGNATED, EventKind.RESERVE_FLIPPED,
                                  EventKind.RESERVE_RELEASED) for e in a.events)
