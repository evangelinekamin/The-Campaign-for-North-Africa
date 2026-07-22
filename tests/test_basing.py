"""[43.0] AXIS ITALIAN-AEGEAN AIR BASES and [39.19] ONE MISSION PER PLANE -- Phase 5.5.

The rule these two enforce together is that the Axis air force cannot be everywhere:

  43.11 "At least 75% of all German He 111's, Ju88D's and FW220's must be based in MEDITERRANEAN
        BASES."
  43.12 "Until 1/35 Game-Turn 1941, 75% OF ALL GERMAN BOMBERS must be based in Italy/Sicily."
        -- UNTYPED, so it binds on the engine's abstract Axis bomber pool on any reading.
  43.13 "From June 1/35 Game-Turn 1941 to the end of the game AT LEAST 50% of all He111's, Ju88's,
        and FW220's MUST BE BASED IN CRETE; the remaining 25% may be based in Sicily/Italy or in
        Crete."
  43.25 "Bombers based in Italy/Sicily... may ALSO BE USED IN RAIDS ON MALTA (see 44.0)" -- and, by
        omission, Crete-based bombers may not.
  39.19 "A PLANE FLYING A MISSION IN AN OPERATIONS STAGE MAY NOT FLY IN THE STRATEGIC PHASE OF THAT
        GAME-TURN AND VICE VERSA."

THE INVARIANT THIS FILE EXISTS TO PIN IS THAT AN AEROPLANE IS IN EXACTLY ONE PLACE: what rule 44
raids Malta with is what rule 43 has taken off the African battlefield, subtracted once.

⚠ ONE OWNER RULING RIDES ON THIS FILE and is asserted rather than hidden: 43.11/43.13 are written
about GERMAN HEAVY BOMBER types, and this engine's abstract Axis strike pool is a Ju. 87B, which is
not one of them -- so from Game-Turn 35, when 43.12's untyped sentence expires, the Crete half binds
on nothing. The tests below measure what that costs rather than assert it away.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.air as air
import game.basing as basing
import game.logistics_data as logistics_data
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
    printed = logistics_data.malta_italy_sicily_basing_43_1()
    assert basing.italy_sicily_pct(34) == 75 and basing.italy_sicily_pct(35) == 25
    assert basing.crete_pct(34) == 0 and basing.crete_pct(35) == 50
    # 43.13's own arithmetic: from GT35 the Mediterranean requirement is met by Crete plus whatever
    # is left in Italy/Sicily, and the two must add to 43.11's printed total. The engine reads the
    # two PARTS and never the total, so this is the transcription cross-check.
    assert basing.crete_pct(35) + basing.italy_sicily_pct(35) == printed["mediterranean_pct"] == 75
    assert basing.italy_sicily_pct(34) + basing.crete_pct(34) == printed["mediterranean_pct"]


def test_the_malta_capable_force_collapses_at_game_turn_35():
    """43.13 + 43.25, read on a real establishment: the same island, the same aeroplanes, and two
    thirds fewer of them able to reach it once Crete takes its half."""
    st = _mini(strike=100)                               # 20 Ju 87B on the 34.14 bridge
    assert basing.italy_sicily_planes(st, 34) == 15
    assert basing.italy_sicily_planes(st, 35) == 5
    # and rule 44 reads THIS function, so the two cannot drift apart
    assert malta.italy_sicily_planes(st, 35) == basing.italy_sicily_planes(st, 35)


def test_an_aeroplane_is_in_exactly_one_place():
    """THE ARITHMETIC THE 5.5 REPAIR PASS EXISTS FOR. Rule 44 raids Malta with the bombers rule 43
    bases in Italy/Sicily; rule 43 leaves the REST in Africa. Before the repair the same pool was
    75% in Sicily for the raid AND 100% in Africa for Land Support -- 35 aeroplanes of basing out of
    a force of 20, in the direction that gave the Axis both arenas at once."""
    st = _mini(strike=100)
    pool = air.squadron_planes(st, Side.AXIS, "LAND", "strike")
    for turn in (1, 34, 35, 111):
        med = basing.mediterranean_planes(st, turn)
        assert med == basing.italy_sicily_planes(st, turn) + basing.crete_planes(st, turn)
        assert basing.africa_planes(st, Side.AXIS, turn) + med == pool


def test_43_12_is_untyped_so_the_desert_keeps_a_quarter_of_the_bombers_until_game_turn_35():
    """"Until 1/35 Game-Turn 1941, 75% OF ALL GERMAN BOMBERS must be based in Italy/Sicily" names no
    aircraft type, so it binds on the one abstract German bomber pool this engine fields whatever
    the owner rules about 43.11's three named types. Twenty Stukas, fifteen in Sicily, five in
    Africa -- and the five carry the Bombload of five aeroplanes and no more."""
    st = _mini(strike=100)
    assert basing.africa_planes(st, Side.AXIS, 1) == 5
    assert basing.establishment(st, Side.AXIS, "LAND", "strike") == 5
    assert basing.available_points(st, Side.AXIS, "LAND", "strike", 100) == 25   # 5 x Bombload 5
    # every other side, arena and role is untouched by rule 43 -- 43.1 is the German Player's
    daf = replace(st, air=st.air + (AirWing("DAF", Side.ALLIED, "LAND",
                                            fighters=0, strike=100, recon=0),))
    assert basing.africa_planes(daf, Side.ALLIED, 1) == air.squadron_planes(
        daf, Side.ALLIED, "LAND", "strike") == 20
    assert basing.available_points(daf, Side.ALLIED, "LAND", "strike", 100) == 100
    assert basing.available_points(st, Side.AXIS, "LAND", "recon", 2) == 2
    assert basing.available_points(daf, Side.ALLIED, "SEA", "strike", 0) == 0


# --- the owner ruling ----------------------------------------------------------------------------

def test_43_11_and_43_13_name_types_this_engine_does_not_field():
    """⚠ OWNER RULING (1). 43.11/43.13 constrain named GERMAN HEAVY BOMBERS and nothing else, and
    game.air expresses the Axis LAND bomber pool as the Ju. 87B -- a Stuka, which they do not name
    and which flew from African strips. So the CRETE half binds on nothing, and when 43.12's untyped
    sentence expires at Game-Turn 35 the Luftwaffe's desert bomber force TRIPLES. That discontinuity
    is the cost of leaving the ruling open, and it is measured here rather than smoothed away."""
    st = _mini(strike=100)
    assert air.REPRESENTATIVE_AIRCRAFT[(Side.AXIS, "strike")] == "Ju. 87B"
    assert not basing.typed_requirement_applies(st, Side.AXIS)
    assert basing.crete_planes(st, 35) == 0                  # the unseeded half of the ruling
    assert basing.africa_planes(st, Side.AXIS, 34) == 5       # 43.12 in force
    assert basing.africa_planes(st, Side.AXIS, 35) == 15      # 43.12 expired, 43.13 typed out


def test_the_constrained_types_are_the_chart_s_printed_names_not_the_rule_s_prose():
    """THE BUG THE 5.5 REPAIR PASS CAUGHT. typed_requirement_applies is an exact string test against
    the keys of game.air.AIRCRAFT, which are the [4.44b] chart's printed names (PDF p.145, read with
    eyes: "Fw. 200 C", "He. 111", "Hs. 126", "Ju. 52/3m", "Ju. 87B", "Ju. 87D", "Ju. 88D"). A list
    transcribed off rule 43.11's PROSE instead -- "He 111", "FW 220" -- can never match a transcribed
    row, and fails SILENTLY rather than loudly. Every constrained type must therefore be a name the
    chart actually prints.

    ⚠ OWNER RULING (2): 43.11 also names "FW220" and NO SUCH AIRCRAFT IS ON THE CHART. It is left
    unseeded in the data file rather than guessed at the Fw. 200 C."""
    # The German half of [4.44b], as the 1979 chart prints it. The full roster is untranscribed
    # ([34.6]/[59.3] is Phase 6 work) -- only the six representative rows are in the data file --
    # so this literal is the scan reading itself, and it is what the constrained list must live in.
    printed_p145 = ("Ar. 196", "Fw. 200 C", "He. 111", "Hs. 126", "Ju. 52/3m",
                    "Ju. 87B", "Ju. 87D", "Ju. 88D")
    assert basing.constrained_types() == ("He. 111", "Ju. 88D")
    for name in basing.constrained_types():
        assert name in printed_p145, (name, "not a row of [4.44b] -- it could never bind")
    # ...and the rows that ARE transcribed use those same printed names, which is why an exact
    # membership test is the right mechanism and a prose transcription was the wrong one
    german = [k for k, v in logistics_data.aircraft_characteristics_4_44().items()
              if v["nation"] == "german" and v["class"] != "fighter"]   # the fighters are p.144
    assert german and all(k in printed_p145 for k in german), german
    unresolved = logistics_data.malta_italy_sicily_basing_43_1()["unresolved_type_43_11"]
    assert unresolved == "FW220" and unresolved not in printed_p145


def test_the_crete_half_binds_the_moment_a_named_type_enters_the_order_of_battle(monkeypatch):
    """The law is written once and the DATA decides whether it binds. Put a He. 111 in the Axis
    bomber seat -- the chart's own name for it -- and from Game-Turn 35 half the force sits in
    Crete, where 43.25 lets it raid nothing and 43.11 keeps it off the battlefield."""
    monkeypatch.setitem(air.REPRESENTATIVE_AIRCRAFT, (Side.AXIS, "strike"), "He. 111")
    monkeypatch.setitem(air.AIRCRAFT, "He. 111", {"bombload": 5, "fuel": 3, "tacair": 0})
    st = _mini(strike=100)
    assert basing.typed_requirement_applies(st, Side.AXIS)
    assert basing.crete_planes(st, 35) == 10                 # 20 aeroplanes, half to Crete
    assert basing.africa_planes(st, Side.AXIS, 35) == 5       # ...and the desert keeps a quarter
    assert basing.africa_planes(st, Side.AXIS, 34) == 5       # as it already did under 43.12
    # ...and the readiness ledger is then measured against the AFRICAN force, not the whole one
    assert basing.establishment(replace(st, turn=35), Side.AXIS, "LAND", "strike") == 5


# --- [39.19] the Strategic-Phase ledger ----------------------------------------------------------

def test_39_19_a_plane_that_flew_the_strategic_phase_may_not_fly_the_desert():
    """"A plane flying a mission in an Operations Stage may not fly in the Strategic Phase of that
    Game-Turn AND VICE VERSA." Both Stukas go to Malta; the desert gets nothing."""
    none = _mini(strike=40)                                      # 8 Ju 87B on the 34.14 bridge...
    assert air.squadron_planes(none, Side.AXIS, "LAND", "strike") == 8
    assert basing.africa_planes(none, Side.AXIS, 1) == 2          # ...of which 43.12 leaves TWO
    assert _air_points(none, Side.AXIS, "LAND", "strike") == 10   # 2 x Bombload 5
    one = _mini(strike=40, strategic={AXIS_STRIKE: 1})
    assert _air_points(one, Side.AXIS, "LAND", "strike") == 5     # the other plane's Bombload
    both = _mini(strike=40, strategic={AXIS_STRIKE: 2})
    assert _air_points(both, Side.AXIS, "LAND", "strike") == 0    # both African bombers went


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
