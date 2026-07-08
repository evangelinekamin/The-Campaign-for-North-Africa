"""Steps 8-9: the fog god-view split and the deterministic diary. Every test is
ZERO-token -- the diary is a PURE query over a recorded log (no client, no engine
re-run), and the fog split is a diff of two observe() calls. The seats reason off the
fogged view; the narrator alone reads the god-view, and every diary line traces to a
real event seq.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import _mock_staff                           # noqa: E402

from game import narrator                                           # noqa: E402
from game.engine import run                                         # noqa: E402
from game.events import Event, EventKind, Phase, Side               # noqa: E402
from game.llm import MockClient                                     # noqa: E402
from game.observation import observe                                # noqa: E402
from game.policy import ScriptedPolicy                              # noqa: E402
from game.scenario import rommels_arrival                          # noqa: E402
from game.staff import Lane, role_brief, unit_lanes                 # noqa: E402
from game.staff_policy import StaffPolicy                           # noqa: E402
from game.supply import FUEL                                        # noqa: E402


def _mock_game():
    return run(rommels_arrival(seed=4200),
               axis=StaffPolicy(MockClient(_mock_staff), side=Side.AXIS),
               allied=ScriptedPolicy(attacker=Side.AXIS))


# --- Step 8: the fog god-view split -------------------------------------------

def test_god_view_reveals_stacks_absent_from_every_seat_brief():
    """The design irony, made computable: at the opening the Commonwealth stacks stand
    outside the flat SIGHTING radius, so they are ABSENT from every seat's role_brief
    enemy_sightings yet PRESENT in the narrator's god-view."""
    state = rommels_arrival(seed=4200)
    hidden = narrator.hidden_from_staff(state, Side.AXIS)
    assert hidden, "expected Commonwealth stacks beyond SIGHTING at the opening"
    hidden_hexes = {tuple(s["hex"]) for s in hidden}

    fogged = observe(state, Side.AXIS)               # what a seat actually reasons off
    idl = unit_lanes(state, Side.AXIS)
    for lane in (Lane.MOBILE, Lane.INFANTRY, Lane.QM):
        brief = role_brief(fogged, lane, idl)
        seat_hexes = {tuple(s["hex"]) for s in brief["enemy_sightings"]}
        assert hidden_hexes.isdisjoint(seat_hexes)   # absent from the seat's brief

    god = observe(state, Side.AXIS, reveal_all=True)
    god_hexes = {tuple(s["hex"]) for s in god["enemy_sightings"]}
    assert hidden_hexes <= god_hexes                 # present in the god-view


def test_hidden_is_exactly_god_view_minus_fogged():
    """hidden_from_staff is precisely the set difference (god-view enemy hexes minus the
    fogged staff's) -- a pure, total diff, nothing invented."""
    state = rommels_arrival(seed=4200)
    god = {tuple(s["hex"]) for s in observe(state, Side.AXIS, reveal_all=True)["enemy_sightings"]}
    fog = {tuple(s["hex"]) for s in observe(state, Side.AXIS)["enemy_sightings"]}
    hidden = {tuple(s["hex"]) for s in narrator.hidden_from_staff(state, Side.AXIS)}
    assert hidden == god - fog


# --- Step 9: the diary is a fully-traceable projection over a recorded log -----

def test_every_diary_line_traces_to_a_real_event():
    """The engine is untouched: the diary reads the recorded RunResult. Every line's
    anchor seq AND every ref is a seq that exists in the log -- nothing authored,
    everything grounded."""
    result = _mock_game()
    seqs = {e.seq for e in result.events}
    lines = narrator.diary(result)
    assert lines
    for ln in lines:
        assert ln.seq in seqs
        assert all(r in seqs for r in ln.refs)


def test_stakes_are_named_before_the_outcomes():
    """A STAFF_INTENT stakes line precedes the VICTORY_CHECKED verdict (stakes named
    before outcomes), and the intent is deduped to its reframings."""
    result = _mock_game()
    lines = narrator.diary(result)
    stakes = [ln for ln in lines if ln.beat == "stakes"]
    verdict = [ln for ln in lines if ln.beat == "verdict"]
    assert stakes and verdict
    assert max(ln.seq for ln in stakes) < min(ln.seq for ln in verdict)


def test_starvation_line_links_a_panzer_draw_to_a_stalled_formation():
    """The fuel-starvation chain: a mobile-formation FUEL draw empties the shared dump,
    then a trailing formation's move is ORDER_REJECTED for want of fuel in the SAME
    Operations Stage -- the starvation line anchors to the reject and references the
    panzer draw. Driven off a synthetic log (like its dissent siblings) so it pins the
    narrator's LINKING LOGIC rather than the mock game's shifting fuel choreography."""
    from game.staff import MOBILE_FORMATIONS
    initial = rommels_arrival(seed=4200)
    by_id = {u.id: u for u in initial.units}
    panzer_id, trailing_id = "GE-5-Le", "GE-2---300-OAS"
    assert by_id[panzer_id].formation in MOBILE_FORMATIONS
    events = [
        _ev(0, 1, Side.SYSTEM, EventKind.GAME_INITIALIZED, {"seed": 4200}),
        _ev(1, 2, Side.AXIS, EventKind.SUPPLY_CONSUMED,
            {"supply_id": "d1", "commodity": FUEL, "qty": 5, "unit_id": panzer_id}, stage=3),
        _ev(2, 2, Side.AXIS, EventKind.ORDER_REJECTED,
            {"order": "move", "unit_id": trailing_id, "to": [1, 1],
             "reason": "out of supply: no fuel for this move"}, stage=3),
        _ev(3, 2, Side.SYSTEM, EventKind.VICTORY_CHECKED, {"axis": 30, "allied": 70, "axis_reach": 20}),
    ]
    result = SimpleNamespace(initial=initial, events=events, final=initial, winner=Side.ALLIED)
    by_seq = {e.seq: e for e in events}
    starv = [ln for ln in narrator.diary(result) if ln.beat == "starvation"]
    assert starv, "a same-stage panzer draw + trailing no-fuel reject must yield a starvation line"
    ln = starv[0]
    anchor = by_seq[ln.seq]
    assert anchor.kind == EventKind.ORDER_REJECTED and "fuel" in anchor.payload["reason"].lower()
    (draw_seq,) = ln.refs
    draw = by_seq[draw_seq]
    assert draw.kind == EventKind.SUPPLY_CONSUMED and draw.payload["commodity"] == FUEL
    assert draw.seq < anchor.seq
    assert by_id[draw.payload["unit_id"]].formation in MOBILE_FORMATIONS


def _ev(seq, turn, side, kind, payload, stage=1):
    return Event(seq=seq, turn=turn, phase=Phase.MOVEMENT, side=side,
                 actor=f"{side.value}/x", kind=kind, payload=payload, stage=stage)


def test_infantry_dissent_resolves_to_a_downstream_no_fuel_reject():
    """The 'Infantry GOC warned the fuel would not reach' arc: a STAFF_DISSENT resolves
    to a concrete DOWNSTREAM event -- the later no-fuel reject of the very formation the
    Chief starved -- and that vindicating seq is carried in the line's refs."""
    initial = rommels_arrival(seed=4200)       # real state so the god-view fog beat works
    inf_id, inf_form = "GE-2---300-OAS", "GE 300th Oasis Battalion"
    events = [
        _ev(0, 1, Side.SYSTEM, EventKind.GAME_INITIALIZED, {"seed": 4200}),
        _ev(1, 1, Side.AXIS, EventKind.STAFF_INTENT,
            {"seat": "Chief", "objective": "Seize Tobruk", "scheme": "armour leading"}),
        _ev(2, 1, Side.AXIS, EventKind.STAFF_DISSENT,
            {"seat": Lane.INFANTRY.value, "formation": inf_form,
             "against": "Chief favours GE 5th Light Panzer Division",
             "stance": "the fuel will not reach my corps"}),
        _ev(3, 1, Side.AXIS, EventKind.SUPPLY_CONSUMED,
            {"supply_id": "d1", "commodity": FUEL, "qty": 5, "unit_id": "GE-5-Le"}),
        _ev(4, 1, Side.AXIS, EventKind.ORDER_REJECTED,
            {"order": "move", "unit_id": inf_id, "to": [1, 1],
             "reason": "out of supply: no fuel for this move"}),
        _ev(5, 1, Side.SYSTEM, EventKind.VICTORY_CHECKED,
            {"axis": 20, "allied": 80, "axis_reach": 40}),
    ]
    result = SimpleNamespace(initial=initial, events=events,
                             final=initial, winner=Side.ALLIED)
    lines = narrator.diary(result)
    dissent = next(ln for ln in lines if ln.beat == "dissent")
    assert dissent.refs == (4,)                       # resolves to the seq-4 no-fuel reject
    assert "vindicated" in dissent.text
    assert "fuel will not reach my corps" in dissent.text


def test_dissent_without_a_downstream_reject_is_marked_refuted():
    """No downstream no-fuel reject for the denied corps -> the protest is noted refuted,
    still anchored to the dissent event, carrying no vindicating ref."""
    initial = rommels_arrival(seed=4200)
    events = [
        _ev(0, 1, Side.SYSTEM, EventKind.GAME_INITIALIZED, {"seed": 4200}),
        _ev(1, 1, Side.AXIS, EventKind.STAFF_DISSENT,
            {"seat": Lane.INFANTRY.value, "formation": "GE 300th Oasis Battalion",
             "against": "Chief favours the panzers", "stance": "we will be starved"}),
    ]
    result = SimpleNamespace(initial=initial, events=events, final=initial, winner=Side.AXIS)
    dissent = next(ln for ln in narrator.diary(result) if ln.beat == "dissent")
    assert dissent.refs == ()
    assert "refuted" in dissent.text
