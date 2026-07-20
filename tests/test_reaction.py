"""Rule 8.5 -- Reaction Movement, the non-phasing tempo interrupt (RBA-shaped, in the Movement Segment).

As a phasing unit moves adjacent to a non-phasing motorized unit, that unit may slide aside. The
8.53 eligibility filters (motorized, not pre-pinned by OTHER enemy ZOC, not Engaged, the 8.53b
CPA-gap pin, the 8.54 size-pin) are read off the current board; the reactor is validated against
plain reachable_for (8.55) and REACTION_MOVED folds like UNIT_MOVED. Inert unless the non-phasing
policy opts into react_to, so every current scenario is byte-identical.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.engine import _movement, _react, _Run, determinism_signature, run
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


def _unit(uid: str, side: Side, hex_: Coord, *, cpa: int = 40, sp: int = 3,
          mob: Mobility = Mobility.MOTORIZED, engaged: bool = False) -> Unit:
    return Unit(uid, side, hex_, (StepRecord("x", 6),), mob,
                cpa=cpa, stacking_points=sp, oca=4, dca=4, cohesion=6, engaged=engaged)


def _state(units) -> GameState:
    dump = SupplyUnit("D", Side.ALLIED, (3, 0), ammo=0, fuel=10_000)
    dump2 = SupplyUnit("D2", Side.AXIS, (2, 0), ammo=0, fuel=10_000)
    return GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                     seed=7, weather="normal", vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=(0, 0), supplies=(dump, dump2),
                     consumed={"FUEL": 0}, initial_supply={"FUEL": 20_000})


class _Reactor(Policy):
    """A non-phasing policy that slides its reactor to a fixed hex when offered a reaction."""

    def __init__(self, unit_id: str, to: Coord):
        self.unit_id = unit_id
        self.to = to

    def movement(self, state, side):
        return []

    def combat(self, state, side):
        return []

    def react_to(self, state, side, trigger, eligible):
        if self.unit_id in eligible:
            return [MoveOrder(self.unit_id, self.to)]
        return []


def _policies(reactor: Policy):
    return {Side.AXIS: ScriptedPolicy(Side.AXIS), Side.ALLIED: reactor}


# --- the happy path ----------------------------------------------------------

def test_a_motorized_reactor_slides_aside():
    mover = _unit("A1", Side.AXIS, (2, 0))
    reactor = _unit("B1", Side.ALLIED, (3, 0))          # adjacent + motorized
    r = _Run(_state([mover, reactor]))
    _react(r, _policies(_Reactor("B1", (5, 0))), Side.AXIS, "A1")
    assert any(e.kind == EventKind.REACTION_MOVED for e in r.events)
    assert r.state.unit("B1").hex == (5, 0)
    assert r.state.unit("B1").cp_used > 0                # 8.52: reaction expends CP


def test_a_vehicle_reactor_slides_aside():
    # 8.53a: reaction is open to EVERY motorized-class unit, not just truck-borne infantry -- a tank
    # (VEHICLE) adjacent to a driving-by enemy may slide to react. The old `== MOTORIZED` gate wrongly
    # locked out every real tank / recce / motorcycle.
    mover = _unit("A1", Side.AXIS, (2, 0))
    reactor = _unit("B1", Side.ALLIED, (3, 0), mob=Mobility.VEHICLE)     # a panzer -- is_motorized
    r = _Run(_state([mover, reactor]))
    _react(r, _policies(_Reactor("B1", (5, 0))), Side.AXIS, "A1")
    assert any(e.kind == EventKind.REACTION_MOVED for e in r.events)
    assert r.state.unit("B1").hex == (5, 0)


def test_a_recce_reactor_slides_aside():
    # 8.53a / the rulebook's own 8.53b example is a recce unit: a RECCE reactor is eligible too.
    mover = _unit("A1", Side.AXIS, (2, 0))
    reactor = _unit("B1", Side.ALLIED, (3, 0), mob=Mobility.RECCE)
    r = _Run(_state([mover, reactor]))
    _react(r, _policies(_Reactor("B1", (5, 0))), Side.AXIS, "A1")
    assert any(e.kind == EventKind.REACTION_MOVED for e in r.events)
    assert r.state.unit("B1").hex == (5, 0)


def test_base_policy_never_reacts():
    mover = _unit("A1", Side.AXIS, (2, 0))
    reactor = _unit("B1", Side.ALLIED, (3, 0))
    r = _Run(_state([mover, reactor]))
    _react(r, {Side.AXIS: ScriptedPolicy(Side.AXIS),
               Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS, "A1")
    assert not any(e.kind == EventKind.REACTION_MOVED for e in r.events)
    assert r.state.unit("B1").hex == (3, 0)


# --- 8.53 eligibility gates --------------------------------------------------

def test_non_motorized_unit_may_not_react():
    mover = _unit("A1", Side.AXIS, (2, 0))
    foot = _unit("B1", Side.ALLIED, (3, 0), mob=Mobility.FOOT)
    r = _Run(_state([mover, foot]))
    _react(r, _policies(_Reactor("B1", (5, 0))), Side.AXIS, "A1")
    assert not any(e.kind == EventKind.REACTION_MOVED for e in r.events)   # 8.53a


def test_engaged_unit_may_not_react():
    mover = _unit("A1", Side.AXIS, (2, 0))
    reactor = _unit("B1", Side.ALLIED, (3, 0), engaged=True)
    r = _Run(_state([mover, reactor]))
    _react(r, _policies(_Reactor("B1", (5, 0))), Side.AXIS, "A1")
    assert not any(e.kind == EventKind.REACTION_MOVED for e in r.events)   # 8.53d


def test_a_far_heavier_mover_pins_the_reactor():
    # 8.53b: mover CPA (48) exceeds reactor CPA (40) by >= 6 -> reaction pinned.
    mover = _unit("A1", Side.AXIS, (2, 0), cpa=48)
    reactor = _unit("B1", Side.ALLIED, (3, 0), cpa=40)
    r = _Run(_state([mover, reactor]))
    _react(r, _policies(_Reactor("B1", (5, 0))), Side.AXIS, "A1")
    assert not any(e.kind == EventKind.REACTION_MOVED for e in r.events)


def test_a_small_reactor_cannot_pin_a_large_mover():
    # 8.54: a reactor less than half the mover's stacking size may not react.
    mover = _unit("A1", Side.AXIS, (2, 0), sp=8)
    small = _unit("B1", Side.ALLIED, (3, 0), sp=3)      # 3*2 < 8
    r = _Run(_state([mover, small]))
    _react(r, _policies(_Reactor("B1", (5, 0))), Side.AXIS, "A1")
    assert not any(e.kind == EventKind.REACTION_MOVED for e in r.events)


def test_a_pre_pinned_reactor_may_not_react():
    # 8.53c: a reactor already in a DIFFERENT enemy unit's ZOC is pinned and may not react,
    # even though the trigger mover has moved adjacent to it.
    mover = _unit("A1", Side.AXIS, (2, 0))
    pinner = _unit("A2", Side.AXIS, (4, 1))             # its ZOC covers (3,0) via adjacency
    reactor = _unit("B1", Side.ALLIED, (3, 0))
    # (3,0) is adjacent to A2 (4,1)? neighbors of (4,1) include (3,1),(4,0),(5,0),(4,2),(5,1),(3,2)
    # -- not (3,0). Use a pinner truly adjacent to (3,0):
    pinner = _unit("A2", Side.AXIS, (4, 0))             # (4,0) is adjacent to (3,0)
    r = _Run(_state([mover, pinner, reactor]))
    _react(r, _policies(_Reactor("B1", (5, -1))), Side.AXIS, "A1")
    assert not any(e.kind == EventKind.REACTION_MOVED for e in r.events)


# --- integrated: reaction rides inside _movement -----------------------------

def test_reaction_fires_from_within_movement():
    # The AXIS attacker's scripted advance toward (0,0) moves a unit adjacent to a Commonwealth
    # reactor, which slides aside -- the whole flow through _movement.
    mover = _unit("A1", Side.AXIS, (4, 0))
    reactor = _unit("B1", Side.ALLIED, (2, 1))
    ad = SupplyUnit("AD", Side.AXIS, (4, 0), ammo=0, fuel=10_000)   # co-located so A1 can move
    bd = SupplyUnit("BD", Side.ALLIED, (2, 1), ammo=0, fuel=10_000)  # co-located so B1 can react
    st = GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                   seed=7, weather="normal", vp=VP(), terrain=_grid(), control={},
                   units=(mover, reactor), target_hex=(0, 0), supplies=(ad, bd),
                   consumed={"FUEL": 0}, initial_supply={"FUEL": 20_000})

    class _Attacker(ScriptedPolicy):
        def movement(self, state, side):
            return [MoveOrder("A1", (3, 1))]            # ends adjacent to the reactor at (2,1)
    r = _Run(st)
    _movement(r, {Side.AXIS: _Attacker(Side.AXIS),
                  Side.ALLIED: _Reactor("B1", (2, 3))}, Side.AXIS)
    assert r.state.unit("A1").hex == (3, 1)
    assert any(e.kind == EventKind.REACTION_MOVED for e in r.events)
    assert r.state.unit("B1").hex == (2, 3)


# --- 8.5 re-entrancy: a reactor may slide into a later phasing mover's path ---

def test_phasing_mover_cannot_land_on_a_hex_a_reactor_slid_into():
    # The crash-guard: _movement freezes the enemy_occupied snapshot once per segment, but a
    # reaction relocates a NON-phasing unit mid-loop. A LATER phasing order into the reactor's
    # NEW hex passed the frozen reachability + the FRIENDLY-only stacking check, co-locating two
    # HOSTILE stacks (6 pts > the limit 5) -> invariants raised mid-run from a legal-looking order.
    # The live enemies_at check at emit rejects that order instead.
    a1 = _unit("A1", Side.AXIS, (4, 0))            # trigger mover -> pushes B1 to react
    a2 = _unit("A2", Side.AXIS, (2, 4))            # later mover, ordered onto B1's reaction hex
    b1 = _unit("B1", Side.ALLIED, (2, 1))          # reactor, slides to (2,3)
    sup = (SupplyUnit("AD1", Side.AXIS, (4, 0), ammo=0, fuel=10_000),
           SupplyUnit("AD2", Side.AXIS, (2, 4), ammo=0, fuel=10_000),
           SupplyUnit("BD", Side.ALLIED, (2, 1), ammo=0, fuel=10_000))
    st = GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                   seed=7, weather="normal", vp=VP(), terrain=_grid(), control={},
                   units=(a1, a2, b1), target_hex=(0, 0), supplies=sup,
                   consumed={"FUEL": 0}, initial_supply={"FUEL": 30_000})

    class _Attacker(ScriptedPolicy):
        def movement(self, state, side):
            return [MoveOrder("A1", (3, 1)),        # ends adjacent to B1 -> B1 reacts
                    MoveOrder("A2", (2, 3))]        # onto the hex B1 reacts INTO

    r = _Run(st)
    _movement(r, {Side.AXIS: _Attacker(Side.AXIS),
                  Side.ALLIED: _Reactor("B1", (2, 3))}, Side.AXIS)   # no InvariantViolation raised
    assert r.state.unit("B1").hex == (2, 3)                          # the reactor slid here
    assert r.state.unit("A2").hex == (2, 4)                          # the phasing order was refused
    rej = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED
           and e.payload.get("unit_id") == "A2"]
    assert rej and "enemy unit" in rej[0].payload["reason"]


# --- byte-identity of the shipped scenarios ----------------------------------

def test_scripted_scenarios_are_byte_identical_under_reaction():
    for factory in (coastal_corridor, rommels_arrival):
        a = run(factory(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        b = run(factory(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert determinism_signature(a.events) == determinism_signature(b.events)
        assert not any(e.kind == EventKind.REACTION_MOVED for e in a.events)
