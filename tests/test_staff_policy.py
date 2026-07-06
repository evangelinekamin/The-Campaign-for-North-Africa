"""Step 3: the StaffPolicy skeleton -- deliberate-once / dispense-slices, driven by
a deterministic MockClient stub (zero tokens). A full Rommel's Arrival game runs to
completion, proposes only engine-legal orders, and is byte-deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import _mock_staff                         # noqa: E402

from game.engine import run                                       # noqa: E402
from game.events import EventKind, Side                           # noqa: E402
from game.events import log_to_json                               # noqa: E402
from game.llm import MockClient                                   # noqa: E402
from game.policy import ScriptedPolicy                            # noqa: E402
from game.scenario import rommels_arrival                         # noqa: E402
from game.staff_policy import StaffPolicy, merge_attacks          # noqa: E402
from game.policy import AttackOrder                               # noqa: E402


def _play():
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    return run(rommels_arrival(seed=4200), axis=axis,
               allied=ScriptedPolicy(attacker=Side.AXIS))


def test_staff_game_completes_with_a_verdict():
    result = _play()
    assert result.winner is not None or result.reason
    assert result.final.turn >= 1


def test_staff_proposals_are_individually_engine_legal():
    """The GOCs propose only from can_move_to / attack_options, so no order bounces
    as unreachable or unknown -- the only rejections the engine may raise are the
    batch-interaction ones (fuel/stacking), never a malformed proposal."""
    result = _play()
    bad = [e for e in result.events
           if e.kind == EventKind.ORDER_REJECTED and e.side == Side.AXIS
           and any(w in e.payload.get("reason", "")
                   for w in ("unreachable", "no such living"))]
    assert bad == []


def test_staff_run_is_byte_deterministic():
    a = log_to_json(_play().events)
    b = log_to_json(_play().events)
    assert a == b


def test_combat_batch_merges_same_target_attacks():
    merged = merge_attacks([
        AttackOrder(("m1", "m2"), (5, 5)),
        AttackOrder(("i1",), (5, 5)),          # same target -> combined arms
        AttackOrder(("m3",), (7, 7)),
    ])
    by_target = {a.target: a.attacker_ids for a in merged}
    assert by_target[(5, 5)] == ("m1", "m2", "i1")   # union, first-seen order
    assert by_target[(7, 7)] == ("m3",)
    assert len(merged) == 2
