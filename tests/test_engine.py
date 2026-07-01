"""Phase-0 acceptance tests on the real land engine (brief §7, §8): the loop
completes, invariants hold, replay is byte-deterministic, fold reproduces the
live state, and illegal orders are rejected at the boundary without mutating
state."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game.apply import fold
from game.engine import RunResult, determinism_signature, run
from game.events import EventKind, Side
from game.invariants import InvariantViolation, check
from game.policy import AttackOrder, Policy, ScriptedPolicy
from game.scenario import coastal_corridor
from game.state import StepRecord


class _BadPolicy(Policy):
    """Ill-behaved (proxy for a future LLM) policy: proposes an off-map teleport
    every movement phase. The engine boundary must reject it, never move the unit."""

    def movement(self, state, side):
        if side != Side.AXIS:
            return []
        from game.policy import MoveOrder
        return [MoveOrder(u.id, (u.hex[0] + 50, u.hex[1])) for u in state.living(side)]

    def combat(self, state, side) -> list[AttackOrder]:
        return []


def _run(seed: int = 1941) -> RunResult:
    pol = ScriptedPolicy(Side.AXIS)
    return run(coastal_corridor(seed=seed), axis=pol, allied=pol)


def test_runs_to_completion():
    result = _run()
    assert result.winner in (Side.AXIS, Side.ALLIED)
    assert result.final.turn <= result.final.max_turns
    assert result.events[0].kind == EventKind.GAME_INITIALIZED


def test_determinism_same_seed():
    assert determinism_signature(_run(7).events) == determinism_signature(_run(7).events)


def test_different_seeds_can_diverge():
    sigs = {determinism_signature(_run(s).events) for s in range(8)}
    assert len(sigs) > 1


def test_replay_equivalence():
    result = _run()
    assert fold(result.initial, result.events) == result.final


def test_axis_actually_advances_on_real_terrain():
    # sanity that real CPA/road movement happens at all (not just rejections)
    result = _run()
    assert any(e.kind == EventKind.UNIT_MOVED for e in result.events)
    dak_start = coastal_corridor().unit("DAK-5le").hex
    assert result.final.unit("DAK-5le").hex != dak_start


def test_invariant_detects_negative_strength():
    s = coastal_corridor()
    broken = s.with_unit(replace(s.units[0], steps=(StepRecord("pz", -1),)))
    with pytest.raises(InvariantViolation):
        check(broken)


def test_invariant_detects_overstacking():
    s = coastal_corridor()
    # pile all four 2-point units into one hex (8 > limit 5)
    piled = replace(s, units=tuple(replace(u, hex=(0, 0)) for u in s.units))
    with pytest.raises(InvariantViolation):
        check(piled)


def test_retreat_relocates_defender_away_from_attacker():
    # a defender with room retreats the mandated hexes away from the assaulting
    # unit (rule 15.82); with no supply to bias toward, it moves as far as told.
    from game.engine import _Run, _retreat
    from game.events import Phase
    from game.hexmap import distance
    from game.movement import TerrainMap
    from game.state import GameState, SupplyUnit, Unit, VP
    from game.terrain import Mobility, Terrain
    terr = {(q, 0): Terrain.CLEAR for q in range(6)}
    defender = Unit("D", Side.ALLIED, (3, 0), (StepRecord("inf", 4),),
                    mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=2, dca=2)
    attacker = Unit("A", Side.AXIS, (2, 0), (StepRecord("inf", 4),),
                    mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=3, dca=3)
    st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS,
                   seed=1, weather="clear", move_modifier=0, vp=VP(),
                   terrain=TerrainMap(terrain=terr), control={}, units=(defender, attacker),
                   target_hex=(5, 0), supplies=(), consumed={"AMMO": 0, "FUEL": 0},
                   initial_supply={"AMMO": 0, "FUEL": 0})
    r = _Run(st)
    _retreat(r, Side.AXIS, "AXIS/Front", ["D"], (2, 0), 2)
    moved = r.state.unit("D")
    assert moved.hex != (3, 0)
    assert distance(moved.hex, (2, 0)) >= 3                # retreated 2 hexes away


def test_scenarios_robust_across_seeds():
    # every scenario, across many dice, must finish with a winner, be replay-exact
    # and deterministic, with invariants holding every event (checked inside run).
    from game.scenario import battle_for_tobruk, coastal_corridor, rommels_arrival
    for factory in (coastal_corridor, battle_for_tobruk, rommels_arrival):
        for seed in range(1, 6):
            a = run(factory(seed=seed), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
            assert a.winner in (Side.AXIS, Side.ALLIED)
            assert fold(a.initial, a.events) == a.final
            b = run(factory(seed=seed), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
            assert determinism_signature(a.events) == determinism_signature(b.events)


def test_combined_arms_penalty():
    from game.engine import _combined_arms_penalty
    from game.terrain import Mobility

    def mk(uid, n, **kw):
        return __import__("game.state", fromlist=["Unit"]).Unit(
            uid, Side.AXIS, (0, 0), (StepRecord("s", n),), mobility=Mobility.FOOT,
            cpa=25, stacking_points=1, oca=2, dca=2, **kw)
    tank = lambda n: mk("t" + str(n), n, is_tank=True, armor_protection=4)
    inf = lambda n: mk("i" + str(n), n)
    recce = lambda n: mk("r" + str(n), n, armor_protection=2)   # armor but NOT a tank
    assert _combined_arms_penalty([tank(7), inf(5)]) == 1        # 2 unsupported -> ceil(2/3)
    assert _combined_arms_penalty([tank(3), inf(21)]) == 0       # fully supported
    assert _combined_arms_penalty([tank(4)]) == 2               # rulebook "/3" reading (§1)
    assert _combined_arms_penalty([tank(20)]) == 4              # capped at 4
    assert _combined_arms_penalty([recce(10)]) == 0            # recce/SP exempt (15.4)
    assert _combined_arms_penalty([tank(6), recce(6)]) == 2     # recce does not support tanks


def test_cohesion_changed_event_applies():
    from game.apply import apply as apply_event
    from game.events import Event, EventKind, Phase
    s = coastal_corridor()
    uid = s.units[0].id
    e = Event(0, 1, Phase.COMBAT, Side.AXIS, "x", EventKind.COHESION_CHANGED,
              {"unit_id": uid, "delta": -3})
    assert apply_event(s, e).unit(uid).cohesion == -3


def test_cohesion_decays_on_heavy_combat_losses():
    # a 30%+ close-assault loss disorganizes the unit (rule 15.87); recovery is
    # deferred, so Cohesion accumulates downward over repeated combats.
    from game.events import EventKind
    from game.scenario import battle_for_tobruk
    res = run(battle_for_tobruk(seed=1), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    changes = [e for e in res.events if e.kind == EventKind.COHESION_CHANGED]
    assert changes and all(e.payload["delta"] == -3 for e in changes)
    assert res.final.unit(changes[0].payload["unit_id"]).cohesion < 0


def test_engine_rejects_illegal_orders_without_mutating_state():
    result = run(coastal_corridor(), axis=_BadPolicy(), allied=ScriptedPolicy(Side.AXIS))
    rejected = [e for e in result.events if e.kind == EventKind.ORDER_REJECTED]
    assert rejected and all("reason" in e.payload for e in rejected)
    assert result.final.unit("DAK-5le").hex == (0, 0)      # never moved
    assert result.final.unit("IT-Ariete").hex == (1, 1)
