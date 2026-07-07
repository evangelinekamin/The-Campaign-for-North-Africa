"""Step 4: the engine drain_staff hook. StaffPolicy's deliberation is emitted into
the SAME event log, just before the orders it explains -- and because STAFF_* fold
as no-ops with rng_draws=(), emission perturbs neither the board nor the dice.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import _mock_staff                         # noqa: E402

from game.apply import fold                                       # noqa: E402
from game.engine import run                                       # noqa: E402
from game.events import EventKind, Phase, Side                    # noqa: E402
from game.llm import MockClient                                   # noqa: E402
from game.policy import ScriptedPolicy                            # noqa: E402
from game.scenario import rommels_arrival                         # noqa: E402
from game.staff_events import staff_log                           # noqa: E402
from game.staff_policy import StaffPolicy                         # noqa: E402


def _is_staff(e) -> bool:
    return e.kind.name.startswith("STAFF_")


class _SilentStaff(StaffPolicy):
    """Identical deliberation and orders, but emits NO staff events -- the control to
    prove staff emission perturbs no dice (the engine rolls the same numbers)."""

    def drain_staff(self):
        super().drain_staff()          # still clear the pending buffer
        return []


def _play(policy_cls):
    axis = policy_cls(MockClient(_mock_staff), side=Side.AXIS)
    return run(rommels_arrival(seed=4200), axis=axis,
               allied=ScriptedPolicy(attacker=Side.AXIS))


def test_board_is_invariant_to_staff_events():
    result = _play(StaffPolicy)
    non_staff = [e for e in result.events if not _is_staff(e)]
    assert any(_is_staff(e) for e in result.events)          # staff really were emitted
    assert fold(result.initial, result.events) == fold(result.initial, non_staff)


def test_staff_log_is_nonempty_and_ordered_intent_proposal_constraint():
    staff = staff_log(_play(StaffPolicy).events)
    assert staff
    head = staff[0]
    assert head.kind == EventKind.STAFF_INTENT
    # the first movement side-turn's block -- scoped by its (turn, stage, phase, side)
    # stamp. It opens on the single Chief INTENT and closes on the Intel CONSTRAINT; the
    # interior is the seats' PROPOSALs interleaved with the two resource seats' status
    # CONSTRAINTs (air grounding, naval throttle). A conflict-free movement plan carries
    # no ADJUDICATION/DISSENT (those ride the convoy seam / cross-lane clashes).
    key = (head.turn, head.stage, head.phase, head.side)
    block = [e.kind for e in staff
             if (e.turn, e.stage, e.phase, e.side) == key and e.phase == Phase.MOVEMENT]
    assert block[0] == EventKind.STAFF_INTENT
    assert block.count(EventKind.STAFF_INTENT) == 1
    assert block[-1] == EventKind.STAFF_CONSTRAINT           # the Intel seat closes the block
    assert EventKind.STAFF_PROPOSAL in block
    assert all(k in (EventKind.STAFF_PROPOSAL, EventKind.STAFF_CONSTRAINT) for k in block[1:])


def test_staff_emission_perturbs_no_dice():
    """The non-STAFF rng_draws subsequence of the staff run is byte-identical to the
    full rng_draws of the silent (no-emission) run -- staff events roll no dice."""
    loud = _play(StaffPolicy)
    silent = _play(_SilentStaff)
    loud_rng = [tuple(e.rng_draws) for e in loud.events if not _is_staff(e)]
    silent_rng = [tuple(e.rng_draws) for e in silent.events]
    assert not any(_is_staff(e) for e in silent.events)
    assert loud_rng == silent_rng
