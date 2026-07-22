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

RESTATED 2026-07-22, WHEN THE [34.6]/[59.3] INITIAL AIR STRENGTHS LANDED. This file used to carry
an owner ruling: rule 43's typed cases name German heavy bombers and the engine's Axis strike pool
was ONE abstract Ju. 87B, so the Crete half bound on nothing for a reason that was ours. With the
real muster transcribed (game.roster) the answer is flatter and needs no ruling at all -- **[60.32]
MUSTERS NO GERMAN AEROPLANE**, so every clause of rule 43, typed and untyped alike, has nothing to
base until the untranscribed [34.87] reinforcement schedule brings the Luftwaffe to Africa. The
tests below therefore assert the LAW against a doctored establishment that does field a named type,
and assert separately that the campaign's own establishment does not.
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
import game.roster as roster
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


def _with_german_bombers(monkeypatch, available=100):
    """Put a type rule 43 NAMES into the Axis bomber establishment -- the chart's own "He. 111", so
    the exact string match binds -- and keep it the whole of that establishment, so the percentages
    below are percentages of a force the rule governs entire. This is what [34.87]'s Axis Airplane
    Reinforcement Schedule will do for real; until it is transcribed, a monkeypatch is the only way
    to exercise a law the campaign cannot yet reach."""
    real = roster._establishments()
    kept = [r for r in real["campaign_64"]["AXIS"]["planes"] if r["role"] != "strike"]
    axis = {**real["campaign_64"]["AXIS"],
            "planes": kept + [{"type": "He. 111", "printed": "He 111", "available": available,
                               "refitted": available, "role": "strike"}]}
    patched = {**real,
               "campaign_64": {**real["campaign_64"], "AXIS": axis}}
    monkeypatch.setattr(roster, "_establishments", lambda: patched)


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


def test_the_malta_capable_force_collapses_at_game_turn_35(monkeypatch):
    """43.13 + 43.25, read on an establishment rule 43 actually governs: the same island, the same
    aeroplanes, and two thirds fewer of them able to reach it once Crete takes its half. (The
    establishment is doctored to field He. 111s, because [60.32]'s does not field one German
    aeroplane -- see test_the_campaign_musters_no_german_aeroplane_at_all.)"""
    _with_german_bombers(monkeypatch)
    st = _mini(strike=2700)                              # 100 He. 111 at Bombload 27
    assert air.squadron_planes(st, Side.AXIS, "LAND", "strike") == 100
    assert basing.italy_sicily_planes(st, 34) == 75
    assert basing.italy_sicily_planes(st, 35) == 25
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


def test_43_12_is_untyped_but_it_is_not_un_nationed(monkeypatch):
    """"Until 1/35 Game-Turn 1941, 75% OF ALL GERMAN BOMBERS must be based in Italy/Sicily" names no
    aircraft TYPE -- which is why it used to be read as binding on the whole abstract Axis pool --
    but it does name a NATIONALITY, and that word is the whole difference now that the establishment
    is the book's. Given a German bomber force it takes three quarters of it off the desert; given
    [60.32]'s Regia Aeronautica it takes nothing.

    RESTATED 2026-07-22 (rule 5: the old assertion enshrined the proxy, not the rule -- it read
    "twenty Stukas, fifteen in Sicily, five in Africa" of an establishment that never existed)."""
    _with_german_bombers(monkeypatch)
    st = _mini(strike=2700)                                          # 100 He. 111
    assert basing.africa_planes(st, Side.AXIS, 1) == 25
    assert basing.establishment(st, Side.AXIS, "LAND", "strike") == 25
    assert basing.available_points(st, Side.AXIS, "LAND", "strike", 2700) == 675  # 25 x Bombload 27
    # every other side, arena and role is untouched by rule 43 -- 43.1 is the German Player's
    daf = replace(st, air=st.air + (AirWing("DAF", Side.ALLIED, "LAND",
                                            fighters=0, strike=382, recon=0),))
    assert basing.africa_planes(daf, Side.ALLIED, 1) == air.squadron_planes(
        daf, Side.ALLIED, "LAND", "strike") == 56
    assert basing.available_points(daf, Side.ALLIED, "LAND", "strike", 382) == 382
    assert basing.available_points(st, Side.AXIS, "LAND", "recon", 2) == 2
    assert basing.available_points(daf, Side.ALLIED, "SEA", "strike", 0) == 0


# --- the owner ruling ----------------------------------------------------------------------------

def test_the_campaign_musters_no_german_aeroplane_at_all():
    """THE FINDING THAT DISSOLVED OWNER RULING (1), and it is a fact about the book rather than a
    reading of it: [60.32] is the campaign's Initial Air Strengths ([64.3] sends the campaign to
    section 60) and every one of its nine rows is Italian. So the Axis air force in Africa in
    September 1940 is the Regia Aeronautica entire, rule 43 -- typed and untyped alike -- has no
    German bomber to base anywhere, and the whole establishment flies over the desert.

    The Luftwaffe arrives on [34.87]'s Axis Airplane Reinforcement Schedule, which is untranscribed;
    when it lands, rule 43 starts binding on its own with no code change, which is what the doctored
    fixtures above prove."""
    chart = logistics_data.aircraft_characteristics_4_44()
    assert [m.type for m in roster.roster(Side.AXIS)]         # the muster is not empty...
    assert not [m for m in roster.roster(Side.AXIS) if chart[m.type]["nation"] == "german"]
    assert all(chart[m.type]["nation"] == "italian" for m in roster.roster(Side.AXIS))
    st = _mini(strike=100)
    assert basing.constrained_planes(st, Side.AXIS) == 0
    assert not basing.typed_requirement_applies(st, Side.AXIS)
    assert basing.crete_planes(st, 35) == 0
    pool = air.squadron_planes(st, Side.AXIS, "LAND", "strike")
    assert basing.africa_planes(st, Side.AXIS, 34) == pool    # 43.12 has nothing to base
    assert basing.africa_planes(st, Side.AXIS, 35) == pool    # nor do 43.11/43.13


def test_the_constrained_types_are_the_chart_s_printed_names_not_the_rule_s_prose():
    """THE BUG THE 5.5 REPAIR PASS CAUGHT. typed_requirement_applies is an exact string test against
    the keys of game.air.AIRCRAFT, which are the [4.44b] chart's printed names (PDF p.145, read with
    eyes: "Fw. 200 C", "He. 111", "Hs. 126", "Ju. 52/3m", "Ju. 87B", "Ju. 87D", "Ju. 88D"). A list
    transcribed off rule 43.11's PROSE instead -- "He 111", "FW 220" -- can never match a transcribed
    row, and fails SILENTLY rather than loudly. Every constrained type must therefore be a name the
    chart actually prints.

    OWNER RULING (2), MADE 2026-07-21: 43.11 also names "FW220" and NO SUCH AIRCRAFT IS ON THE
    CHART. Eve ruled it the same aeroplane as the chart's "Fw. 200 C", so the constrained list now
    carries all three types the rule names -- and the mechanism this test guards is unchanged: the
    seeded name is the CHART's, so it can bind."""
    # The German half of [4.44b], as the 1979 chart prints it. The data file transcribes six of the
    # eight (the Ar. 196 and the Ju. 52/3m are in no muster and are not needed), so this literal is
    # the scan reading itself, and it is what the constrained list must live in.
    printed_p145 = ("Ar. 196", "Fw. 200 C", "He. 111", "Hs. 126", "Ju. 52/3m",
                    "Ju. 87B", "Ju. 87D", "Ju. 88D")
    assert basing.constrained_types() == ("Fw. 200 C", "He. 111", "Ju. 88D")
    for name in basing.constrained_types():
        assert name in printed_p145, (name, "not a row of [4.44b] -- it could never bind")
    # ...and the rows that ARE transcribed use those same printed names, which is why an exact
    # membership test is the right mechanism and a prose transcription was the wrong one
    german = [k for k, v in logistics_data.aircraft_characteristics_4_44().items()
              if v["nation"] == "german" and v["class"] != "fighter"]   # the fighters are p.144
    assert german and all(k in printed_p145 for k in german), german
    # the ruling keeps BOTH names on the record: the prose's and the chart row it was ruled to be
    ruled = logistics_data.malta_italy_sicily_basing_43_1()["ruled_type_43_11"]
    assert ruled["prose_name_pdf_p61"] == "FW220" and ruled["prose_name_pdf_p61"] not in printed_p145
    assert ruled["chart_row_pdf_p145"] in printed_p145
    assert ruled["chart_row_pdf_p145"] in basing.constrained_types()


def test_the_crete_half_binds_the_moment_a_named_type_enters_the_order_of_battle(monkeypatch):
    """The law is written once and the DATA decides whether it binds. Put He. 111s in the Axis
    bomber establishment -- the chart's own name for the aeroplane -- and from Game-Turn 35 half the
    force sits in Crete, where 43.25 lets it raid nothing and 43.11 keeps it off the battlefield."""
    _with_german_bombers(monkeypatch)
    st = _mini(strike=2700)                                  # 100 He. 111
    assert basing.typed_requirement_applies(st, Side.AXIS)
    assert basing.crete_planes(st, 35) == 50                 # 100 aeroplanes, half to Crete
    assert basing.africa_planes(st, Side.AXIS, 35) == 25      # ...and the desert keeps a quarter
    assert basing.africa_planes(st, Side.AXIS, 34) == 25      # as it already did under 43.12
    # ...and the readiness ledger is then measured against the AFRICAN force, not the whole one
    assert basing.establishment(replace(st, turn=35), Side.AXIS, "LAND", "strike") == 25


# --- [39.19] the Strategic-Phase ledger ----------------------------------------------------------

def test_39_19_a_plane_that_flew_the_strategic_phase_may_not_fly_the_desert():
    """"A plane flying a mission in an Operations Stage may not fly in the Strategic Phase of that
    Game-Turn AND VICE VERSA." Both Stukas go to Malta; the desert gets nothing."""
    none = _mini(strike=40)                                      # 4 of [60.32]'s bombers...
    assert air.squadron_planes(none, Side.AXIS, "LAND", "strike") == 4
    assert basing.africa_planes(none, Side.AXIS, 1) == 4          # ...all four in Africa (43.12
    assert _air_points(none, Side.AXIS, "LAND", "strike") == 40   # bases no Italian aeroplane)
    one = _mini(strike=40, strategic={AXIS_STRIKE: 1})
    assert _air_points(one, Side.AXIS, "LAND", "strike") == 35    # the other three carry 35 points
    three = _mini(strike=40, strategic={AXIS_STRIKE: 3})
    assert _air_points(three, Side.AXIS, "LAND", "strike") == 11  # one bomber left
    allgone = _mini(strike=40, strategic={AXIS_STRIKE: 4})
    assert _air_points(allgone, Side.AXIS, "LAND", "strike") == 0  # every African bomber went


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
    assert p["bomb_points"] == air.points_of_planes(Side.AXIS, "strike", p["planes"])
    assert r.state.air_strategic[AXIS_STRIKE] == p["planes"] == p["strategic"]
    # 38.31: they have flown a mission, so they are no longer refitted -- on top of the [59.32]
    # aeroplanes the campaign already opens with in the hangars (137 of the Axis's 184 bombers)
    assert r.state.air_unfit[AXIS_STRIKE] == campaign(
        seed=7, max_turns=3).air_unfit[AXIS_STRIKE] + p["planes"]
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
