"""Primitive B: the STAFF_* narrative event substrate. These kinds fold as pure
no-ops (the board is invariant to staff chatter), clean_staff_payload whitelists +
caps a rambling model's payload down to JSON primitives, and staff_log filters an
event stream to just the narrative record."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import fold
from game.events import Event, EventKind, Phase, Side
from game.scenario import coastal_corridor
from game.staff_events import clean_staff_payload, staff_log


def _ev(seq: int, kind: EventKind, payload: dict) -> Event:
    return Event(seq, 1, Phase.MOVEMENT, Side.AXIS, "AXIS/Chief", kind, payload)


def test_staff_event_folds_as_board_invariant_noop():
    init = coastal_corridor()
    base = [_ev(0, EventKind.GAME_INITIALIZED, {})]
    narrative = _ev(1, EventKind.STAFF_INTENT, {"objective": "seize Tobruk"})
    assert fold(init, base + [narrative]) == fold(init, base)


def test_clean_staff_payload_whitelists_caps_and_stays_json_serializable():
    raw = {
        "objective": "x" * 500,             # over the 140 cap -> truncated
        "line": "y" * 400,                  # over the 240 envelope cap -> truncated
        "hexes": [[1, 2], "junk", (3, 4)],  # tuple coerced to list, junk pair dropped
        "lessons": ["a", "b", "c", "d"],    # >3 -> truncated to 3
        "smuggled_transcript": "z" * 9000,  # unknown key -> dropped
    }
    out = clean_staff_payload(EventKind.STAFF_INTENT, raw)
    assert "smuggled_transcript" not in out
    assert len(out["objective"]) == 140
    assert len(out["line"]) == 240
    assert out["hexes"] == [[1, 2], [3, 4]]
    assert len(out["lessons"]) == 3
    assert json.loads(json.dumps(out)) == out          # round-trips as JSON primitives


def test_clean_staff_payload_drops_invalid_enum_value():
    out = clean_staff_payload(EventKind.STAFF_CONSTRAINT,
                              {"kind": "fuel", "severity": "meltdown", "subject": "5th Light"})
    assert out["kind"] == "fuel"                        # valid enum value kept
    assert "severity" not in out                        # invalid enum value dropped
    assert out["subject"] == "5th Light"


def test_staff_log_filters_to_staff_events_in_seq_order():
    events = [
        _ev(0, EventKind.GAME_INITIALIZED, {}),
        _ev(1, EventKind.STAFF_INTENT, {"objective": "a"}),
        _ev(2, EventKind.UNIT_MOVED, {"unit_id": "u", "to": [1, 0], "cp_spent": 1}),
        _ev(3, EventKind.STAFF_DISSENT, {"against": "the plan", "stance": "too slow"}),
    ]
    log = staff_log(events)
    assert [e.kind for e in log] == [EventKind.STAFF_INTENT, EventKind.STAFF_DISSENT]
    assert [e.seq for e in log] == [1, 3]               # seq order preserved
