"""RULE 54.11 -- AN ARMY THAT CAN BUILD ITS OWN DUMPS. And 32.13 -- one it can take.

THE MISSING SUBSYSTEM. Until this commit YOU COULD NOT CREATE A SUPPLY DUMP. No EventKind made one,
game.apply never appended to state.supplies, and engine._truck_unload rejected any unload with "no
co-located friendly dump to unload into". The depot list was FROZEN AT CONSTRUCTION for all 111
Game-Turns -- which contradicts [54.11] ("Any hex can be used as a supply dump") and [54.16]
("Establishing a viable dump network should be TOP PRIORITY for logistics commanders"), and it meant
an advance could never be consolidated: measured, both armies ended ~9 hexes beyond the nearest
stocked dump -- just outside the 32.16 cpa/2 trace -- and stayed there. 5-8% of the Axis and 29% of
the Commonwealth could draw a single Point of supply, from Game-Turn 10 to Game-Turn 111.

Three rules land together, because each is inert without the others: capture alone is a gift to
whoever is advancing, a depot network alone is never filled, and a consolidation constraint alone has
nothing to consolidate INTO.
"""
from __future__ import annotations

import hashlib

import pytest

from game import supply
from game.campaign_policy import (CampaignAxisPolicy, CampaignCommonwealthPolicy,
                                  keep_in_trace)
from game.engine import determinism_signature, run
from game.events import EventKind, Side
from game.invariants import check
from game.policy import MoveOrder, ScriptedPolicy
from game.scenario import campaign, rommels_arrival, siege_of_tobruk


@pytest.fixture(scope="module")
def gt30():
    # Seed 99: the relay founds six depots and the first dumps change hands on GT9-11, so one
    # thirty-turn slice exercises all three rules at once.
    return run(campaign(seed=99, max_turns=30), CampaignAxisPolicy(), CampaignCommonwealthPolicy())


# --- [54.11] a dump can be established ------------------------------------------------------

def test_a_dump_can_be_established(gt30):
    """[54.11] "Any hex can be used as a supply dump." The relay founds them where the army stands
    (campaign_policy._forward_depot_sites), so the network follows the advance instead of the
    advance starving away from the network."""
    made = [e for e in gt30.events if e.kind == EventKind.SUPPLY_DUMP_ESTABLISHED]
    assert made, "no supply dump was ever established -- 54.11 is still unimplemented"
    born = {e.payload["supply_id"] for e in made}
    live = {s.id for s in gt30.final.supplies}
    assert born & live, "a founded dump never reached the final board"


def test_an_established_dump_is_born_empty_and_then_filled(gt30):
    """It mints nothing -- conservation is untouched -- and the supplies arrive by the
    TRUCK_UNLOADED that follows it."""
    made = next(e for e in gt30.events if e.kind == EventKind.SUPPLY_DUMP_ESTABLISHED)
    sid = made.payload["supply_id"]
    filled = [e for e in gt30.events
              if e.kind == EventKind.TRUCK_UNLOADED and e.payload["supply_id"] == sid]
    assert filled, f"{sid} was founded and never filled"


def test_the_founded_network_conserves_supply(gt30):
    """game.invariants: on_hand + consumed == initial, per commodity. Founding a dump appends an
    EMPTY one, so it cannot mint a Point."""
    check(gt30.final)


# --- [32.13] a dump can be captured ---------------------------------------------------------

def test_a_field_dump_is_captured_when_the_enemy_enters_its_hex(gt30):
    """[32.13] "If any enemy combat unit enters a Supply Unit's hex, that unit is captured (and its
    supplies used immediately and freely)." [49.19]: "Fuel is non-denominational... making a supply
    dump a worthwhile objective." """
    took = [e for e in gt30.events if e.kind == EventKind.SUPPLY_CAPTURED]
    assert took, "no dump ever changed hands -- 32.13 is still unimplemented"
    for e in took:
        assert e.payload["from"] != e.payload["to"]


def test_capture_moves_supply_and_never_mints_it(gt30):
    """CONSERVATION. Capture flips an owner; it does not create or destroy a Point."""
    check(gt30.final)


def test_the_bottomless_base_is_not_capturable(gt30):
    """THE LANDMINE, and it is a FLAGGED PROXY. AL-Cairo and AL-Alexandria hold ~125,000,000 Points
    apiece because they stand for an OFF-MAP Nile Delta / Suez source of unlimited capacity (54.12),
    not for a Supply Dump counter 32.13 can pick up. Measured under a capture rule that did not
    exempt them: the Axis took the Commonwealth's base depots and its score went 380 -> 434, its
    supplied strength leaping from 4 units to 23-41. An infinite dump lying on the map as a
    capturable prize is a bug with a rules citation."""
    took = {e.payload["supply_id"] for e in gt30.events if e.kind == EventKind.SUPPLY_CAPTURED}
    assert "AL-Cairo" not in took and "AL-Alexandria" not in took
    for s in gt30.final.supplies:
        if s.base:
            assert s.side == (Side.ALLIED if s.id.startswith("AL") else Side.AXIS), \
                f"{s.id} is a base (or a well) and changed hands"


def test_an_empty_dump_is_not_a_prize(gt30):
    """[32.13] captures a Supply Unit "and its supplies"; by [32.15] a Unit with nothing left in it
    is REMOVED -- there is no counter to take. It is also load-bearing: the campaign parks the
    Commonwealth's EMPTY Compass Field Supply Depots inside cities the Axis holds on Game-Turn 1
    (AL-Stage-Sollum under the garrison at Sollum, AL-Tobruk under the one in Tobruk), because what
    keeps them dry is CONTROL, not distance (campaign_claim.spine_awaits_control). Capturing them on
    GT1 loots nothing and severs the Commonwealth's supply spine before the war starts -- measured,
    the take-and-hold then claimed NO CITY AT ALL for the whole campaign, in every seed. Nobody
    "enters" a dump that was under their feet at the setup."""
    early = [e for e in gt30.events if e.kind == EventKind.SUPPLY_CAPTURED and e.turn == 1]
    assert not early, f"an empty dump was captured at the setup: {[e.payload for e in early]}"
    for e in (e for e in gt30.events if e.kind == EventKind.SUPPLY_CAPTURED):
        p = e.payload
        assert p["ammo"] + p["fuel"] + p["stores"] + p["water"] > 0, \
            f"an empty dump was captured: {p}"


# --- [32.16]/[54.16] do not outrun your supply ----------------------------------------------

def test_a_supplied_unit_may_not_march_out_of_supply():
    """The consolidation constraint. A unit that CAN trace supply may not march to a hex where it
    CANNOT -- the army advances at the pace its logistics can follow, and no faster."""
    from game.campaign_policy import _can_trace
    st = campaign(seed=1941)
    fed = [u for u in st.living(Side.AXIS)
           if u.is_combat and u.strength >= 1 and _can_trace(st, u)]
    assert fed, "no Axis unit is in supply at the setup -- the fixture is wrong"
    u = fed[0]
    alex = (27, 133)                            # the Nile Delta: far outside any Axis trace
    assert keep_in_trace([MoveOrder(u.id, alex)], st, Side.AXIS) == [], \
        "a supplied unit was allowed to march sixty hexes out of its own supply"


def test_a_starving_unit_may_still_walk_back_to_its_supply():
    """It is never FROZEN. A dry unit may move into the trace, or strictly nearer a stocked depot --
    it just may not march on. (Written first as "a dry unit may move freely", the constraint did
    NOTHING: the proposer only ever offers hexes closer to the OBJECTIVE, so a starving unit was the
    one unit on the map with a licence to keep marching, and the beeline came straight back.)"""
    from game.campaign_policy import _can_trace
    from game.hexmap import distance, neighbors
    st = campaign(seed=1941)
    dry = [u for u in st.living(Side.AXIS)
           if u.is_combat and u.strength >= 1 and not _can_trace(st, u)]
    if not dry:
        pytest.skip("every Axis unit is in supply at the setup")
    depots = [s.hex for s in st.supplies
              if s.side == Side.AXIS and s.ammo > 0 and not supply_is_well(s)]
    u = min(dry, key=lambda u: min(distance(u.hex, d) for d in depots))
    near = min(depots, key=lambda d: distance(u.hex, d))
    step = min((h for h in neighbors(u.hex) if st.terrain.exists(h)),
               key=lambda h: distance(h, near))
    assert keep_in_trace([MoveOrder(u.id, step)], st, Side.AXIS), \
        "a starving unit was forbidden from walking back toward its own depot"


def supply_is_well(s) -> bool:
    return "-Well-" in s.id or "-Pipe-" in s.id


# --- the hard constraint ---------------------------------------------------------------------

def test_rommel_and_siege_stay_byte_identical():
    """32.13 is a GENERAL rule and it fires immediately in both benchmark scenarios -- on Game-Turn 1
    of each, the Axis walks onto AL-Dump#2 and takes 567 Ammo / 799 Fuel / 509 Stores / 501 Water off
    the Commonwealth, moving both published signatures. Those signatures are the regression lock the
    LLM generalship leaderboard is published against, so 32.13 is GATED on state.dump_capture, which
    only game.scenario.campaign sets. A flagged asymmetry pending a re-baseline decision -- NOT a
    claim that the rule is campaign-only. See game.state.dump_capture."""
    assert campaign(seed=1941).dump_capture is True
    assert rommels_arrival(seed=42).dump_capture is False
    assert siege_of_tobruk(seed=42).dump_capture is False

    axis = ScriptedPolicy(Side.AXIS)
    baselines = {"rommel": "9339d2b308d7", "siege": "5ba4da88d107"}
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        res = run(build(seed=42), axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baselines[name], f"{name} byte-identity broken: {sig} != {baselines[name]}"
