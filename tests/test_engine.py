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


def test_engine_rejects_illegal_orders_without_mutating_state():
    result = run(coastal_corridor(), axis=_BadPolicy(), allied=ScriptedPolicy(Side.AXIS))
    rejected = [e for e in result.events if e.kind == EventKind.ORDER_REJECTED]
    assert rejected and all("reason" in e.payload for e in rejected)
    assert result.final.unit("DAK-5le").hex == (0, 0)      # never moved
    assert result.final.unit("IT-Ariete").hex == (1, 1)
