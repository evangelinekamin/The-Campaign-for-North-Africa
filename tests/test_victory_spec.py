"""C1-3: victory conditions are a pluggable strategy on GameState. A scenario may
name its own VictorySpec (check() per Record Phase, decide() at the final turn); the
default None routes to the engine's built-in Race-for-Tobruk logic, byte-identically.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.engine import _DEFAULT_VICTORY, determinism_signature, run
from game.events import Side
from game.policy import ScriptedPolicy
from game.scenario import coastal_corridor


class _ForceAxis:
    """A spec that ends the game for the Axis on the first Record Phase -- proves the
    engine consults GameState.victory rather than its own built-in logic."""

    def check(self, r) -> tuple[Side, str]:
        return Side.AXIS, "forced axis win (test spec)"

    def decide(self, r) -> tuple[Side, str]:
        return Side.AXIS, "forced axis win (test spec)"


def test_custom_spec_is_consulted():
    base = coastal_corridor(seed=7)
    result = run(replace(base, victory=_ForceAxis()), axis=ScriptedPolicy(), allied=ScriptedPolicy())
    assert result.winner is Side.AXIS
    assert "test spec" in result.reason
    # The forced win fires on the first Record Phase, before the scenario's own logic
    # (which never hands the Axis a win on turn 1) could ever trigger.
    assert result.final.turn == 1


def test_none_routes_to_default_byte_identical():
    # victory=None and victory=_DEFAULT_VICTORY must produce identical event streams:
    # the `or _DEFAULT_VICTORY` fallback is the exact built-in path, so unset scenarios
    # are unchanged.
    base = coastal_corridor(seed=7)
    a = run(base, axis=ScriptedPolicy(), allied=ScriptedPolicy())                    # victory=None
    b = run(replace(base, victory=_DEFAULT_VICTORY), axis=ScriptedPolicy(), allied=ScriptedPolicy())
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert a.winner == b.winner and a.reason == b.reason
