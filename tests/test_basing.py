"""[43.0] AXIS ITALIAN-AEGEAN AIR BASES and [39.19] ONE MISSION PER PLANE -- Phase 5.5.

The rule these two enforce together is that the Axis air force cannot be everywhere:

  43.11 "At least 75% of all German He 111's, Ju88D's and FW220's must be based in MEDITERRANEAN
        BASES."
  43.12 "Until 1/35 Game-Turn 1941, 75% of all German bombers must be based in Italy/Sicily."
  43.13 "From June 1/35 Game-Turn 1941 to the end of the game AT LEAST 50% of all He111's, Ju88's,
        and FW220's MUST BE BASED IN CRETE; the remaining 25% may be based in Sicily/Italy or in
        Crete."
  43.25 "Bombers based in Italy/Sicily... may ALSO BE USED IN RAIDS ON MALTA (see 44.0)" -- and, by
        omission, Crete-based bombers may not.
  39.19 "A PLANE FLYING A MISSION IN AN OPERATIONS STAGE MAY NOT FLY IN THE STRATEGIC PHASE OF THAT
        GAME-TURN AND VICE VERSA."

⚠ ONE OWNER RULING RIDES ON THIS FILE and is asserted rather than hidden: 43 names three GERMAN
HEAVY BOMBER types, and this engine's abstract Axis strike pool is a Ju. 87B, which is not one of
them. The deduction is implemented against the NAMED LIST, so it is currently inert -- and the test
that says so also measures what the other reading would do.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.air as air
import game.basing as basing
import game.malta as malta
import game.supply as supply
from game.apply import apply
from game.campaign_policy import CampaignAxisPolicy, malta_africa_doctrine
from game.engine import _air_points, _malta_raid, _Run
from game.events import Event, EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import Policy
from game.scenario import campaign
from game.state import AirWing, GameState, VP
from game.terrain import Terrain

AXIS_STRIKE = "AXIS/LAND/strike"


def _mini(*, strike=6, turn=1, missions=(), unfit=None, strategic=None) -> GameState:
    return GameState(
        turn=turn, max_turns=111, phase=Phase.COMBAT, active_side=Side.AXIS, seed=1,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0), supplies=(),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES},
        air=(AirWing("LW", Side.AXIS, "LAND", fighters=0, strike=strike, recon=2),),
        air_missions=tuple(missions), air_unfit=dict(unfit or {}),
        air_strategic=dict(strategic or {}), stage=1)


# --- the printed percentages --------------------------------------------------------------------

def test_the_three_printed_basing_percentages():
    """43.11's Mediterranean 75 never moves. What moves at Game-Turn 35 is WHERE inside the
    Mediterranean that force sits: 43.12's Italy/Sicily 75 becomes 43.13's Crete 50 + up to 25 in
    Italy/Sicily. Only the Italy/Sicily part may raid Malta (43.25), so the Axis's Malta-capable
    force falls by two thirds in June 1941 by a printed rule."""
    assert basing.mediterranean_pct(1) == basing.mediterranean_pct(111) == 75
    assert basing.italy_sicily_pct(34) == 75 and basing.italy_sicily_pct(35) == 25
    assert basing.crete_pct(34) == 0 and basing.crete_pct(35) == 50
    assert basing.africa_pct(1) == 25
    # 43.13's own arithmetic: from GT35 the Mediterranean requirement is met by Crete plus whatever
    # is left in Italy/Sicily, and the two must add to the 43.11 total
    assert basing.crete_pct(35) + basing.italy_sicily_pct(35) == basing.mediterranean_pct(35)


def test_the_malta_capable_force_collapses_at_game_turn_35():
    """43.13 + 43.25, read on a real establishment: the same island, the same aeroplanes, and two
    thirds fewer of them able to reach it once Crete takes its half."""
    st = _mini(strike=100)                               # 20 Ju 87B on the 34.14 bridge
    assert basing.italy_sicily_planes(st, 34) == 15
    assert basing.italy_sicily_planes(st, 35) == 5
    assert basing.crete_planes(st, 34) == 0
    assert basing.crete_planes(st, 35) == 10
    # and rule 44 reads THIS function, so the two cannot drift apart
    assert malta.italy_sicily_planes(st, 35) == basing.italy_sicily_planes(st, 35)


# --- the owner ruling ----------------------------------------------------------------------------

def test_43_11_names_three_types_and_this_engine_fields_none_of_them():
    """⚠ OWNER RULING. 43.11/43.13 constrain "all German He 111's, Ju88D's and FW220's" and nothing
    else. game.air expresses the Axis LAND bomber pool as the Ju. 87B -- a Stuka, which the rule
    does not name and which flew from African strips. So the deduction is written against the list
    and binds on nothing today. If the owner rules the other way (our one abstract bomber STANDS IN
    for the whole Luftwaffe bomber arm), flipping this list is the whole change."""
    assert basing.constrained_types() == ("He 111", "Ju. 88D", "FW 220")
    assert air.REPRESENTATIVE_AIRCRAFT[(Side.AXIS, "strike")] == "Ju. 87B"
    assert not basing.applies(_mini(), Side.AXIS)
    assert basing.africa_points(_mini(), Side.AXIS, "LAND", "strike", 6) == 6


def test_what_the_other_reading_would_cost_measured_not_asserted():
    """THE REASON THE RULING IS BEING ASKED FOR RATHER THAN TAKEN. Applied to the whole abstract
    pool, 43.11 leaves the campaign's Axis with 25% of six Air Points and 25% of TWO aeroplanes --
    one Bomb Point carried by no plane at all. Every Axis Land Support mission in the war would be
    grounded by a rule written about three bomber types this engine does not own."""
    st = _mini(strike=6)
    pool = air.squadron_points(st, Side.AXIS, "LAND", "strike")
    planes = air.squadron_planes(st, Side.AXIS, "LAND", "strike")
    assert (pool, planes) == (6, 2)
    assert pool * basing.africa_pct(1) // 100 == 1          # one Bomb Point...
    assert planes * basing.africa_pct(1) // 100 == 0        # ...carried by no aeroplane


def test_the_deduction_binds_the_moment_a_named_type_enters_the_order_of_battle(monkeypatch):
    """The law is written once and the DATA decides whether it binds. Put a He 111 in the Axis
    bomber seat and three quarters of the force leaves the desert with no further code."""
    monkeypatch.setitem(air.REPRESENTATIVE_AIRCRAFT, (Side.AXIS, "strike"), "He 111")
    monkeypatch.setitem(air.AIRCRAFT, "He 111", {"bombload": 5, "fuel": 2, "tacair": 0})
    st = _mini(strike=100)
    assert basing.applies(st, Side.AXIS)
    assert basing.africa_points(st, Side.AXIS, "LAND", "strike", 100) == 25
    assert basing.africa_planes(st, Side.AXIS, 1) == 5       # 20 aeroplanes, 25% left in Africa
    # ...and the readiness ledger is then measured against the AFRICAN force, not the whole one
    assert basing.establishment(st, Side.AXIS, "LAND", "strike") == 5
    # every other side, arena and role is untouched by rule 43
    assert basing.africa_points(st, Side.ALLIED, "LAND", "strike", 100) == 100
    assert basing.africa_points(st, Side.AXIS, "LAND", "recon", 100) == 100
    assert basing.africa_points(st, Side.AXIS, "SEA", "strike", 100) == 100


# --- [39.19] the Strategic-Phase ledger ----------------------------------------------------------

def test_39_19_a_plane_that_flew_the_strategic_phase_may_not_fly_the_desert():
    """"A plane flying a mission in an Operations Stage may not fly in the Strategic Phase of that
    Game-Turn AND VICE VERSA." Both Stukas go to Malta; the desert gets nothing."""
    both = _mini(strike=10, strategic={AXIS_STRIKE: 2})
    assert air.squadron_planes(both, Side.AXIS, "LAND", "strike") == 2
    assert _air_points(both, Side.AXIS, "LAND", "strike") == 0
    one = _mini(strike=10, strategic={AXIS_STRIKE: 1})
    assert _air_points(one, Side.AXIS, "LAND", "strike") == 5     # the other plane's Bombload
    none = _mini(strike=10)
    assert _air_points(none, Side.AXIS, "LAND", "strike") == 10


def test_39_19_the_exclusion_lasts_the_GAME_TURN_not_the_operations_stage():
    """39.19 says "of that GAME-TURN", so the ledger survives an OpStage boundary and dies with the
    turn -- unlike air_superiority, which is a per-stage gate, and unlike air_unfit, which only a
    [38.37] refit roll clears."""
    st = _mini(strategic={AXIS_STRIKE: 2})
    stage = Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", EventKind.STAGE_ADVANCED, {"stage": 2})
    assert apply(st, stage).air_strategic == {AXIS_STRIKE: 2}
    turn = Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", EventKind.TURN_ADVANCED, {"turn": 2})
    assert apply(st, turn).air_strategic == {}


def test_the_ledger_defaults_empty_so_nothing_without_a_malta_raid_changes():
    assert GameState.__dataclass_fields__["air_strategic"].default_factory() == {}
    assert _mini().air_strategic == {}
    assert basing.strategic_planes(_mini(), Side.AXIS, "LAND", "strike") == 0


# --- [44.25]/[44.27] the African contingent, and the choice it is -------------------------------

class _SendEverything(Policy):
    def malta_raid(self, state):
        return "IV"                                      # a heavy commitment, so the trade is live

    def malta_africa_planes(self, state, available, level):
        return available


class _SendTooMany(Policy):
    def malta_raid(self, state):
        return "IV"

    def malta_africa_planes(self, state, available, level):
        return 999


def _campaign_run(policy):
    r = _Run(campaign(seed=7, max_turns=3))
    _malta_raid(r, {Side.AXIS: policy, Side.ALLIED: Policy()})
    return r


def test_44_25_the_axis_may_add_african_bombers_and_they_carry_their_bombload():
    """"He may then add in -- up to the maximums he gets from the Table -- ANY PLANES HE WISHES FROM
    AFRICA." The raid grows by their [34.14] Bombload, and the same event books them out of the
    desert for the rest of the Game-Turn (39.19)."""
    r = _campaign_run(_SendEverything())
    sent = [e for e in r.events if e.kind == EventKind.MALTA_RAID_REINFORCED]
    assert sent, "the Axis policy asked for African planes and got none"
    p = sent[0].payload
    assert p["squadron"] == AXIS_STRIKE and p["planes"] > 0
    assert p["bomb_points"] == p["planes"] * air.AIRCRAFT["Ju. 87B"]["bombload"]
    assert r.state.air_strategic[AXIS_STRIKE] == p["planes"] == p["strategic"]
    # 38.31: they have flown a mission, so they are no longer refitted
    assert r.state.air_unfit[AXIS_STRIKE] == p["planes"]
    # ...and the bombs they carry reach the island: the [41.5] roll is made on the larger total
    strike = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED
              and e.payload.get("arena") == "AIRFIELD"][0]
    ordered = [e for e in r.events if e.kind == EventKind.MALTA_RAID_ORDERED][0]
    assert strike.payload["strength"] == ordered.payload["bomb_points"] + p["bomb_points"]


def test_44_27_the_map_contingent_may_never_exceed_what_the_table_granted():
    """"IN NO CASE may the Axis Player assign more planes of any one type FROM MAP BASES than are
    assigned from the Availability Tables." A greedy policy is clamped at the boundary, exactly as
    every other order in this engine is re-validated rather than trusted."""
    r = _campaign_run(_SendTooMany())
    sent = [e for e in r.events if e.kind == EventKind.MALTA_RAID_REINFORCED]
    ordered = [e for e in r.events if e.kind == EventKind.MALTA_RAID_ORDERED][0]
    if sent:                                             # a turn the [44.42] table granted forces
        assert sent[0].payload["planes"] <= ordered.payload["planes"]
        assert sent[0].payload["planes"] <= sent[0].payload["cap"]


def test_the_base_policy_sends_nobody_so_nothing_without_a_doctrine_changes():
    """Policy.malta_africa_planes returns 0: the raid is the Mediterranean force alone, which is
    the Axis's default posture under rule 43 and keeps every un-doctrined scenario unchanged."""
    r = _campaign_run(Policy())
    assert not [e for e in r.events if e.kind == EventKind.MALTA_RAID_REINFORCED]
    assert r.state.air_strategic == {}


def test_the_campaign_doctrine_strips_the_desert_only_for_a_raid_it_has_paid_for():
    """THE 39.19 TRADE, WHICH IS THE POINT OF THE BLOCK. The campaign Axis commits his African
    bombers only when he has spent a Game-Turn of the finite [44.41] budget on this raid -- a
    heavy Availability Level. On Level I, which is unlimited and is also 44.25's do-nothing
    answer, he has committed nothing, so there is nothing for the desert to be stripped for."""
    st = campaign(seed=7, max_turns=3)
    for level in ("II", "III", "IV"):
        assert malta_africa_doctrine(st, 4, level) == 4
    assert malta_africa_doctrine(st, 4, "I") == 0        # 44.25's do-nothing level
    assert malta_africa_doctrine(st, 0, "IV") == 0       # 44.27 granted nothing to match
    assert CampaignAxisPolicy().malta_africa_planes(st, 4, "IV") == 4
