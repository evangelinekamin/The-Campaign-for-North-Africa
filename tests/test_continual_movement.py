"""Rule 8.2/8.23 -- Continual Movement, the exploitation pulse loop.

The shared substrate of the exploitation cluster: after a side's segment-0 Movement/Combat,
a Policy that opts into continual_movement drives bounded exploitation pulses. Each pulse is
gated to the 8.23 two-hex exploitation zone, re-runs a FRESH Combat Segment (8.25), and -- the
adopted fidelity fix -- charges PER-PULSE fuel (49.13) so exploitation is not fuel-free.

A declining base (ScriptedPolicy) runs ZERO pulses, so every current scenario is byte-identical.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import tactics
from game.apply import fold
from game.engine import (_continual_movement, _exploitation_eligible, _movement, _Run,
                         determinism_signature, run)
from game.events import EventKind, Phase, Side
from game.hexmap import Coord
from game.movement import TerrainMap
from game.policy import MoveOrder, Policy, ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival
from game.state import GameState, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain


# --- fixtures ----------------------------------------------------------------

def _grid(n: int = 10) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _unit(uid: str, side: Side, hex_: Coord, *, cpa: int = 40, sp: int = 3) -> Unit:
    return Unit(uid, side, hex_, (StepRecord("x", 6),), Mobility.MOTORIZED,
                cpa=cpa, stacking_points=sp, oca=4, dca=4, cohesion=6)


def _state(units, *, seed: int = 7, target: Coord = (0, 0)) -> GameState:
    fuel = {"FUEL": 10_000}
    dumps = ()
    return GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                     seed=seed, weather="normal", vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=target, supplies=dumps,
                     consumed={}, initial_supply={})


class _Pusher(Policy):
    """An attacker that creeps its mover ONE hex toward the objective per call (so exploitation
    advances in controlled single steps rather than one big jump) and opts into continual movement
    for a fixed number of pulses -- the minimal driver that exercises the 8.2 loop."""

    def __init__(self, mover_id: str, target: Coord, pulses: int = 2):
        self.mover_id = mover_id
        self.target = target
        self.pulses = pulses
        self._seen = 0

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        from game.hexmap import distance, neighbors
        u = state.unit(self.mover_id)
        if u is None or u.side != side:
            return []
        here = distance(u.hex, self.target)
        steps = [c for c in neighbors(u.hex)
                 if state.terrain.exists(c) and distance(c, self.target) < here]
        if not steps:
            return []
        return [MoveOrder(self.mover_id, min(steps, key=lambda c: (distance(c, self.target), c)))]

    def combat(self, state: GameState, side: Side):
        return []

    def continual_movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        if self._seen >= self.pulses:
            return []
        self._seen += 1
        return self.movement(state, side)


# --- 8.23 eligibility --------------------------------------------------------

def test_exploitation_eligible_is_the_two_hex_zone():
    near = _unit("A-near", Side.AXIS, (2, 0))     # 2 hexes from the enemy at (0,0)
    far = _unit("A-far", Side.AXIS, (6, 0))       # 6 hexes -- outside the zone
    enemy = _unit("E", Side.ALLIED, (0, 0))
    elig = _exploitation_eligible(_state([near, far, enemy]), Side.AXIS)
    assert elig == frozenset({"A-near"})


def test_exploitation_eligible_unions_the_also_seam():
    far = _unit("A-far", Side.AXIS, (8, 0))
    enemy = _unit("E", Side.ALLIED, (0, 0))
    elig = _exploitation_eligible(_state([far, enemy]), Side.AXIS, also=frozenset({"A-far"}))
    assert "A-far" in elig                          # the 18.25 reserve seam overrides the 8.23 gate


# --- the pulse loop ----------------------------------------------------------

def test_continual_movement_runs_bounded_pulses_and_emits_segment_markers():
    # Mover at (2,0) is 2 hexes from the enemy at (0,0); stepping toward (2,-8) it stays inside
    # the 8.23 zone for (2,-1) and (2,-2), so both allowed pulses land a real advance.
    from game.state import SupplyUnit
    mover = _unit("A1", Side.AXIS, (2, 0), cpa=60)
    enemy = _unit("E", Side.ALLIED, (0, 0))
    dump = SupplyUnit("D", Side.AXIS, (2, 0), ammo=0, fuel=10_000)
    st = GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                   seed=7, weather="normal", vp=VP(), terrain=_grid(), control={},
                   units=(mover, enemy), target_hex=(2, -8), supplies=(dump,),
                   consumed={"FUEL": 0}, initial_supply={"FUEL": 10_000})
    r = _Run(st)
    pol = _Pusher("A1", target=(2, -8), pulses=2)
    _continual_movement(r, {Side.AXIS: pol, Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    segs = [e for e in r.events if e.kind == EventKind.SEGMENT_ADVANCED]
    assert len(segs) == 2                           # exactly the two pulses the policy allowed
    assert all(e.payload["side"] == "AXIS" for e in segs)
    assert r.state.unit("A1").hex != (2, 0)         # the mover advanced during exploitation


def test_a_declining_policy_runs_zero_pulses():
    mover = _unit("A1", Side.AXIS, (2, 0))
    enemy = _unit("E", Side.ALLIED, (0, 0))
    r = _Run(_state([mover, enemy]))
    _continual_movement(r, {Side.AXIS: ScriptedPolicy(Side.AXIS),
                            Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    assert not any(e.kind == EventKind.SEGMENT_ADVANCED for e in r.events)


def test_pulses_are_gated_to_the_eight_two_three_zone():
    # A far mover (outside the two-hex zone) that the policy tries to push is rejected in-pulse.
    far = _unit("A-far", Side.AXIS, (9, 0), cpa=60)
    enemy = _unit("E", Side.ALLIED, (0, 0))
    r = _Run(_state([far, enemy]))
    pol = _Pusher("A-far", target=(0, 0), pulses=1)
    _continual_movement(r, {Side.AXIS: pol, Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    rejects = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED
               and "8.23" in e.payload.get("reason", "")]
    assert rejects, "an out-of-zone mover must be rejected by the 8.23 gate"


# --- the adopted per-pulse fuel fidelity fix (49.13) -------------------------

def test_each_pulse_charges_fuel_afresh():
    # A mover far enough that each pulse actually moves -> each pulse should draw fuel, so
    # exploitation is NOT fuel-free after pulse 0 (the adopted fidelity fix). Under the in-hex model
    # (S5) that fuel comes from the unit's OWN 49.14 tank -- the mover leaves its dump after segment 0,
    # so the TANK must carry the exploitation (a dry-tank unit off a dump would be rejected, the 49.15
    # stranding). Seed a full tank so each pulse has fuel to burn (UNIT_SUPPLY_CONSUMED afresh).
    from dataclasses import replace
    from game.state import SupplyUnit
    mover = replace(_unit("A1", Side.AXIS, (2, 0), cpa=60), fuel=10_000)
    enemy = _unit("E", Side.ALLIED, (0, 0))
    dump = SupplyUnit("D", Side.AXIS, (2, 0), ammo=0, fuel=10_000)
    st = GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                   seed=7, weather="normal", vp=VP(), terrain=_grid(), control={},
                   units=(mover, enemy), target_hex=(2, -8), supplies=(dump,),
                   consumed={"FUEL": 0}, initial_supply={"FUEL": 10_000})
    r = _Run(st)
    pol = _Pusher("A1", target=(2, -8), pulses=2)
    # segment 0 first (charges fuel once), then the pulses
    _movement(r, {Side.AXIS: pol, Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    fuel_after_seg0 = r.state.consumed["FUEL"]
    assert fuel_after_seg0 > 0
    _continual_movement(r, {Side.AXIS: pol, Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    assert r.state.consumed["FUEL"] > fuel_after_seg0, "each pulse must burn fuel afresh (49.13)"


# --- byte-identity of the shipped scenarios ----------------------------------

def test_scripted_scenarios_are_byte_identical_under_continual_movement():
    for factory in (coastal_corridor, rommels_arrival):
        a = run(factory(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        b = run(factory(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert determinism_signature(a.events) == determinism_signature(b.events)
        assert not any(e.kind == EventKind.SEGMENT_ADVANCED for e in a.events)
        assert fold(a.initial, a.events) == a.final
