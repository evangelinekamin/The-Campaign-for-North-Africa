"""P5 Step 6: the staff grows 5 -> 7. The two order-type resource seats -- the Convoy
officer (NAVAL) and the Air Marshal (AIR) -- command NON-Unit assets on the QM pattern,
so the Lane partition stays untouched. The naval seat commits the seeded ferry
interdiction as a CONTINGENT command decision at the _naval_convoys seam, drained just
before the CONVOY_INTERDICTED it explains. Everything runs at zero tokens (MockClient)
and stays byte-deterministic; a scripted side (no naval seat) leaves the interdiction as
ambient as before -- byte-identical.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import _mock_staff                         # noqa: E402

from game.apply import fold                                       # noqa: E402
from game.engine import run                                       # noqa: E402
from game.events import EventKind, Side, log_to_json              # noqa: E402
from game.llm import MockClient                                   # noqa: E402
from game.observation import observe                              # noqa: E402
from game.policy import ScriptedPolicy                            # noqa: E402
from game.scenario import rommels_arrival, siege_of_tobruk        # noqa: E402
from game.staff import air_brief, naval_brief                     # noqa: E402
from game.staff_policy import AIR, NAVAL, StaffPolicy             # noqa: E402
from game.state import AirWing, InterdictionOrder                 # noqa: E402


def _staff(side=Side.AXIS):
    return StaffPolicy(MockClient(_mock_staff), side=side)


def _play(scenario, seed=4200):
    return run(scenario(seed=seed), axis=_staff(),
               allied=ScriptedPolicy(attacker=Side.AXIS))


# --- the pure resource briefs (no Unit, all shared context kept) -----------------

def test_resource_briefs_are_pure_projections_with_no_ground_units():
    obs = observe(siege_of_tobruk(seed=4200), Side.AXIS)
    for brief in (naval_brief(obs), air_brief(obs)):
        assert brief["your_units"] == []
        assert brief["attack_options"] == []
        # the non-Unit context the seats reason over survives untouched
        for shared in ("weather", "objective", "pending_convoys", "your_ports",
                       "enemy_sightings"):
            assert brief[shared] == obs[shared]
        assert obs["your_units"] != []                 # the projection did not mutate obs


# --- the seven-seat game runs and stays deterministic ----------------------------

def test_seven_seat_game_completes_and_is_byte_deterministic():
    a = _play(siege_of_tobruk)
    b = _play(siege_of_tobruk)
    assert a.winner is not None or a.reason
    assert log_to_json(a.events) == log_to_json(b.events)


def test_all_seven_seats_speak():
    seats = {e.actor.split("/", 1)[1] for e in _play(siege_of_tobruk).events
             if e.actor.startswith("AXIS/") and e.kind.name.startswith("STAFF_")}
    assert {"Chief", "MOBILE", "INFANTRY", "QM", "Naval", "Air", "Intel"} <= seats


# --- the naval seat's contingent interdiction ------------------------------------

def _interdict_beats(events):
    return [e for e in events
            if e.kind == EventKind.STAFF_PROPOSAL and e.actor == "AXIS/Naval"
            and any(p.get("order") == "interdict" for p in e.payload.get("proposes", []))]


def test_naval_seat_emits_interdiction_beats_on_the_seeded_schedule():
    events = _play(siege_of_tobruk).events
    beats = _interdict_beats(events)
    assert beats                                       # the ferry cut is now the seat's order
    # every committed lane names the seeded SEA-TOBRUK ferry
    lanes = {u for e in beats for p in e.payload["proposes"] for u in p["units"]}
    assert lanes == {"SEA-TOBRUK"}


def test_interdict_beat_precedes_the_convoy_interdicted_it_explains():
    events = _play(siege_of_tobruk).events
    first_beat = _interdict_beats(events)[0]
    marker = next(e for e in events if e.kind == EventKind.CONVOY_INTERDICTED
                  and e.turn == first_beat.turn)
    assert first_beat.seq < marker.seq                 # the order is issued before the cut lands


def test_rommels_arrival_has_no_interdiction_so_the_naval_seat_stays_silent_on_cuts():
    # rommels_arrival seeds convoys but NO interdictions -> no lane to commit.
    assert _interdict_beats(_play(rommels_arrival).events) == []


# --- the naval command loop is a no-op without a naval seat (byte-identity) -------

def test_scripted_both_sides_is_unchanged_by_the_naval_command_loop():
    scripted = lambda: run(siege_of_tobruk(seed=1941),
                           axis=ScriptedPolicy(attacker=Side.AXIS),
                           allied=ScriptedPolicy(attacker=Side.AXIS))
    assert log_to_json(scripted().events) == log_to_json(scripted().events)
    # and it emits zero resource-seat beats (no naval_command hook on a scripted policy)
    assert not any(e.actor.endswith(("/Naval", "/Air")) for e in scripted().events)


def test_board_is_invariant_to_the_resource_seat_events():
    result = _play(siege_of_tobruk)
    non_staff = [e for e in result.events if not e.kind.name.startswith("STAFF_")]
    assert any(e.actor.endswith(("/Naval", "/Air")) for e in result.events)
    assert fold(result.initial, result.events) == fold(result.initial, non_staff)


# --- the Chief's air/sea scarcity adjudications ----------------------------------

def _adjudications(events, conflict):
    return [e for e in events if e.kind == EventKind.STAFF_ADJUDICATION
            and e.payload.get("conflict") == conflict]


def test_oversubscribed_tonnage_fires_when_a_convoy_overruns_its_dump():
    # The Axis lane-1 convoy piles into the rear port (the historic Tripoli overflow),
    # so the Chief rules oversubscribed-tonnage and the officer dissents.
    events = _play(siege_of_tobruk).events
    tonnage = _adjudications(events, "oversubscribed-tonnage")
    assert tonnage
    assert any(e.actor == "AXIS/Chief" for e in tonnage)
    dissents = [e for e in events if e.kind == EventKind.STAFF_DISSENT
                and e.actor == "AXIS/Naval"]
    assert dissents


def test_oversubscribed_sorties_fires_when_committed_bombing_outstrips_sea_air():
    # Craft two enemy-ferry lanes both interdicted at turn 1, and give the Axis a THIN
    # SEA strike wing whose Air Points the combined bombing overruns -> the Chief throttles.
    base = siege_of_tobruk(seed=4200)
    ferry = next(c for c in base.convoys if c.lane == "SEA-TOBRUK" and c.arrival_turn == 1)
    second = replace(ferry, id="ferry2-t1", lane="SEA-TOBRUK-2")
    crafted = replace(
        base,
        convoys=base.convoys + (second,),
        interdictions=base.interdictions + (InterdictionOrder("SEA-TOBRUK-2", 1, 200),),
        air=(AirWing("AX-SEA", Side.AXIS, "SEA", fighters=0, strike=100, recon=0),))
    axis = _staff()
    axis.naval_command(crafted, Side.AXIS)             # demand 200+200 > 100 strike
    kinds = [(k, p.get("conflict")) for k, p in axis.drain_staff()]
    assert (EventKind.STAFF_ADJUDICATION, "oversubscribed-sorties") in kinds


def test_a_lone_committed_lane_does_not_oversubscribe_sorties():
    # One lane's bombing can never oversubscribe (the >=2-contender guard), even under air.
    base = siege_of_tobruk(seed=4200)
    crafted = replace(base, air=(AirWing("AX-SEA", Side.AXIS, "SEA",
                                          fighters=0, strike=1, recon=0),))
    axis = _staff()
    axis.naval_command(crafted, Side.AXIS)
    conflicts = [p.get("conflict") for k, p in axis.drain_staff()
                 if k == EventKind.STAFF_ADJUDICATION]
    assert "oversubscribed-sorties" not in conflicts


# --- the fixed deliberation order ------------------------------------------------

def test_movement_plan_seats_run_in_the_fixed_order():
    events = _play(siege_of_tobruk).events
    first = next(e for e in events if e.kind == EventKind.STAFF_INTENT)
    key = (first.turn, first.stage, first.side)
    order = []
    for e in events:
        if (e.turn, e.stage, e.side) == key and e.actor.startswith("AXIS/") \
                and e.phase.value == "MOVEMENT" and e.kind.name.startswith("STAFF_"):
            seat = e.actor.split("/", 1)[1]
            if not order or order[-1] != seat:
                order.append(seat)
    assert order == ["Chief", "MOBILE", "INFANTRY", "QM", "Naval", "Air", "Intel"]
