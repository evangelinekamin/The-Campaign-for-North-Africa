"""Phase-0 acceptance tests (brief §7, §8): the loop completes, invariants hold,
replay is byte-deterministic, fold reproduces the live state, and the engine
rejects illegal orders with a reason rather than silently mutating state.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game.apply import fold
from game.engine import RunResult, determinism_signature, run, _validate_move
from game.events import EventKind, Side
from game.invariants import InvariantViolation, check
from game.policy import AttackOrder, MoveOrder, Policy, ScriptedPolicy
from game.scenario import toy_strip


class _BadPolicy(Policy):
    """Stand-in for an ill-behaved (e.g. future LLM) policy: it proposes an
    illegal teleport every movement phase. The engine boundary must reject it."""

    def movement(self, state, side):
        if side != Side.AXIS:
            return []
        return [MoveOrder(u.id, (u.hex[0] + 5, u.hex[1])) for u in state.living(side)]

    def combat(self, state, side) -> list[AttackOrder]:
        return []


def _run(seed: int = 1940) -> RunResult:
    pol = ScriptedPolicy(Side.AXIS)
    return run(toy_strip(seed=seed), axis=pol, allied=pol)


def test_runs_to_completion():
    result = _run()
    assert result.winner in (Side.AXIS, Side.ALLIED)
    assert result.final.turn <= result.final.max_turns
    assert result.events[0].kind == EventKind.GAME_INITIALIZED


def test_determinism_same_seed():
    a, b = _run(7), _run(7)
    assert determinism_signature(a.events) == determinism_signature(b.events)


def test_different_seeds_can_diverge():
    # Not strictly required, but a sanity check that the RNG actually wires in.
    sigs = {determinism_signature(_run(s).events) for s in range(8)}
    assert len(sigs) > 1


def test_replay_equivalence():
    result = _run()
    assert fold(result.initial, result.events) == result.final


def test_fuel_conservation_holds_at_end():
    result = _run()
    on_hand = sum(u.fuel for u in result.final.units)
    initial = sum(u.fuel for u in result.initial.units)
    assert on_hand + result.final.fuel_consumed == pytest.approx(initial)


def test_invariant_detects_negative_fuel():
    s = toy_strip()
    broken = s.with_unit(replace(s.units[0], fuel=-5.0))
    with pytest.raises(InvariantViolation):
        check(broken, initial_fuel=sum(u.fuel for u in s.units))


def test_move_rejected_when_out_of_fuel():
    s = toy_strip()
    dry = s.with_unit(replace(s.units[0], fuel=0.0))
    unit = dry.units[0]
    dest = (unit.hex[0] + 1, unit.hex[1])
    ok, info = _validate_move(dry, MoveOrder(unit.id, dest), unit.side)
    assert ok is False
    assert "fuel" in info


def test_engine_rejects_illegal_orders_without_mutating_state():
    # An ill-behaved policy proposing illegal moves must yield typed rejections,
    # and the units must NOT move (no silent illegal mutation). This is the
    # load-bearing boundary the brief insists on (§3.3).
    result = run(toy_strip(), axis=_BadPolicy(), allied=ScriptedPolicy(Side.AXIS))
    rejected = [e for e in result.events if e.kind == EventKind.ORDER_REJECTED]
    assert rejected, "expected typed rejections for illegal orders"
    assert all("reason" in e.payload for e in rejected)
    assert result.final.unit("IT-Maletti").hex == (0, 0)
    assert result.final.unit("IT-Cirene").hex == (1, 0)
