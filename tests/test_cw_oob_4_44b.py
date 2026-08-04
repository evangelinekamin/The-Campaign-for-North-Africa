"""[4.44B]/[4.46a] THE COMMONWEALTH ORDER OF BATTLE, off the two charts that print it.

A read-only survey (scratchpad/data-debt/cw-counters.md) measured the Commonwealth OOB against
the book for the first time: `[4.44B]` COMMONWEALTH ORGANIZATION AT ARRIVAL CHART (scan PDF
p.116-132) prints 436 counters, the engine seeded 349, and **91 named counters were absent
outright**. Every one of the 24 distinct ID Codes among them resolves to a row `[4.46a]`
COMMONWEALTH UNIT CHARACTERISTICS CHART (p.133-134) actually prints, so the whole roster is
seedable with NOTHING INVENTED -- with one exception, the `200 Gds` counter, whose arrival the
book does not print at all (asserted absent below, with its reason).

THE DEBT WAS FRONT-LOADED ONTO THE OPENING. 62 of the 91 arrive by Game-Turn 30 and 39 of them
arrive `D` (Deployed, on the map at Game-Turn 1). The Commonwealth's ONLY armoured formation at
the start had no tanks and no armoured cars in this engine; the Operation Compass infantry -- 6th
Australian, 4th Indian, 2nd New Zealand -- was more than half absent. These tests assert the
charts' own cells, sheet by sheet, so that a future edit that quietly drops a counter fails here
rather than in a campaign measurement two months later.

WHERE EACH NUMBER COMES FROM. Every counter row below was read off a 300-dpi `pdftoppm` render of
its own page (600 dpi for the disputed Royal Yugoslav Guards ID glyph, see
test_royal_yugoslav_guards_is_id_code_t). Every stat row below was read off the p.133/p.134
renders of `[4.46a]`. The `Arrives` column prints OpStage/Game-Turn -- the chart's own key, p.116:
"#/- = The Operation Stage of the Game-Turn the unit arrives. -/# = The Game-Turn on which the
unit arrives" -- so `3/58` is OpStage 3 of Game-Turn 58 and `D` is "Deployed... begins the first
Operation Stage of Game-Turn One on the map".

THE AT-START HEXES ARE [60.41]'s, NOT OURS, wherever [60.41] Commonwealth Initial Deployment (scan
p.78) names the counter -- the same authority the Phase-8.1c division-HQ pass used. The two places
our own placement fills a gap the charts leave are asserted as such in
test_the_two_authored_placements_are_the_only_ones.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import adjudication, coords, oob, scenario                     # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
STATS = json.loads((_ROOT / "data" / "unit_stats.json").read_text())["CW"]
EXTRA = json.loads((_ROOT / "data" / "oob_campaign_extra.json").read_text())
REINF = json.loads((_ROOT / "data" / "reinforcements_campaign.json").read_text())["reinforcements"]


def _campaign_units():
    units, _ = oob.build(oob_file="oob_italian.json", extra_file="oob_campaign_extra.json",
                         sections="ABCDE", reinforcements_file="reinforcements_campaign.json",
                         dump_pools=oob.CAMPAIGN_DUMP_POOLS, first_line=oob.CAMPAIGN_FIRST_LINE)
    return {u.id: u for u in units}


def _reinf(counter):
    hits = [r for r in REINF if r.get("counter") == counter]
    assert len(hits) == 1, f"{counter}: expected exactly one record, got {len(hits)}"
    return hits[0]


def _extra(counter):
    hits = [r for r in EXTRA if r.get("counter") == counter]
    assert len(hits) == 1, f"{counter}: expected exactly one record, got {len(hits)}"
    return hits[0]


# --- 1. the [4.46a] stat rows -------------------------------------------------------------
# Columns as the chart prints them: Unit Type | ID Code | CPA | Anti-Air | Barrage | Anti-Armor |
# Vulnerability | Armor Prtctn | Close Assault Off/Def | Maximum TOE.  '-' = not applicable.
# Only the rows a seeded Commonwealth counter actually uses are asserted; the roster's other
# codes (h, j, q, r, s, z, gg, gg, hh, jj, kk, mm, nn, qq, rr, tt) are not seeded by this OOB
# and are deliberately NOT transcribed -- an unused row is an untested row.
#   role key              ID    CPA  oca  dca  MaxTOE
_4_46A_ROWS = [
    ("hq",           "a",  30,  0,  0,  1),   # Max TOE '-'; the row can hold nothing (see _hq_dash_comment)
    ("hq_b",         "b",  30,  0,  0,  1),   # '(1)' -- one tank TOE Strength Point
    ("hq_c",         "c",  30,  0,  0,  3),   # 3 -- up to three artillery TOE Strength Points
    ("hq_d",         "d",  20,  0,  0,  1),   # '(1)' -- one tank TOE Strength Point
    ("hq_e",         "e",  20,  0,  1,  1),
    ("hq_f",         "f",  20,  0,  1,  1),
    ("tank",         "g",  25,  3,  3, 10),   # pre-existing row: steps 8 vs the chart's 10 (see note)
    ("infantry_k",   "k",  10,  2,  2,  7),
    ("motor_infantry", "l", 10,  2,  2,  6),
    ("infantry_m",   "m",  10,  2,  2,  6),
    ("infantry_n",   "n",  10,  1,  2,  6),
    ("infantry",     "p",  10,  1,  2,  6),
    ("infantry_t",   "t",  10,  1,  1,  3),
    ("mg",           "u",   8,  4,  6,  3),
    ("infantry_v",   "v",  10,  1,  1,  1),
    ("infantry_w",   "w",   8,  4,  6,  2),
    ("artillery",    "x",  20,  0,  1,  6),
    ("artillery_y",  "y",  20,  0,  1,  4),
    ("antitank",     "aa", 15,  1,  2,  8),
    ("antitank_bb",  "bb", 15,  1,  2,  6),
    ("antitank_cc",  "cc", 15,  1,  2,  4),
    ("antitank_dd",  "dd", 15,  1,  2,  2),
    ("aa",           "ee", 15,  0,  1,  6),
    ("light_aa_ff",  "ff", 15,  0,  1,  4),
    ("recon_ll",     "ll", 45,  2,  3,  8),
    ("recon",        "pp", 45,  2,  3,  6),
    ("recon_ss",     "ss", 45,  1,  2,  4),
    ("rr_engineer",  "uu", 25,  0,  0,  1),
]


def test_every_4_46a_row_the_oob_uses_matches_the_printed_chart():
    """[4.46a] p.133/p.134, cell by cell. CPA and Close Assault Off/Def are the chart's; Maximum
    TOE is the chart's Maximum TOE column (the engine's `max_toe`, defaulted from `steps`)."""
    for role, code, cpa, oca, dca, max_toe in _4_46A_ROWS:
        row = STATS[role]
        assert row["type"] == code, f"{role}: ID Code {row['type']!r}, chart prints {code!r}"
        assert row["cpa"] == cpa, f"{role} ({code}): CPA {row['cpa']}, chart prints {cpa}"
        assert row["oca"] == oca, f"{role} ({code}): CA Off {row['oca']}, chart prints {oca}"
        assert row["dca"] == dca, f"{role} ({code}): CA Def {row['dca']}, chart prints {dca}"
        assert row.get("max_toe", row["steps"]) == max_toe, (
            f"{role} ({code}): Maximum TOE {row.get('max_toe', row['steps'])}, "
            f"chart prints {max_toe}")


def test_the_new_rows_transcribe_the_dashes_the_chart_prints():
    """[4.46a] prints a DASH in Anti-Armor / Vulnerability / Armor Prtctn on every infantry,
    artillery, anti-tank and reconnaissance row; the ONLY non-dash cells among the rows this
    slice adds are the Headquarters 'e'/'f' Anti-Armor 1/2 and Vulnerability 1, and the
    reconnaissance 'll'/'ss' Armor Protection 1. Transcribing the dash is what makes the row a
    transcription rather than a copy of its neighbour."""
    assert STATS["hq_e"]["anti_armor"] == 1 and STATS["hq_e"]["vulnerability"] == 1
    assert STATS["hq_f"]["anti_armor"] == 2 and STATS["hq_f"]["vulnerability"] == 1
    assert STATS["recon_ll"]["armor_protection"] == 1
    assert STATS["recon_ss"]["armor_protection"] == 1
    for role in ("infantry_k", "infantry_m", "infantry_n", "infantry_t",
                 "infantry_v", "infantry_w", "recon_ll", "recon_ss"):
        row = STATS[role]
        assert row.get("anti_armor", 0) == 0, f"{role}: chart prints a dash in Anti-Armor"
        assert row.get("vulnerability", 0) == 0, f"{role}: chart prints a dash in Vulnerability"
    for role in ("hq_b", "hq_c", "hq_d", "hq_e", "hq_f"):
        assert STATS[role]["is_combat"] is False        # a Headquarters, exactly as row 'a' is
        assert STATS[role]["sp"] == 0                   # [9.12] parenthesized Stacking Points


def test_the_plus_mark_is_what_decides_motorization():
    """[4.46a]'s own key (p.134, verbatim): '+ = The unit was historically supplied with enough
    trucks to entirely motorize its components. Note that only commonwealth battalion and
    company-equivalent units may be motorized.' The mark is printed in the CPA cell -- 'l' 10+,
    'n' 10+, 'v' 10+ -- and 'k', 'm', 'p', 't', 'w' print a bare number. So the marked rows are
    MOTORIZED here and the unmarked ones FOOT, which is the convention the pre-existing
    motor_infantry ('l', MOTORIZED) / infantry ('p', FOOT) pair already set."""
    for role in ("motor_infantry", "infantry_n", "infantry_v"):
        assert STATS[role]["mobility"] == "MOTORIZED", f"{role}: chart prints '+'"
    for role in ("infantry", "infantry_k", "infantry_m", "infantry_t", "infantry_w"):
        assert STATS[role]["mobility"] == "FOOT", f"{role}: chart prints no '+'"


# --- 2. the 7th Armoured Division ---------------------------------------------------------

def test_the_desert_rats_have_their_tanks_and_their_armoured_cars():
    """[4.44B] p.117. The single worst hole the survey found: the Commonwealth's ONLY armoured
    formation on the map at Game-Turn 1 had an HQ, two Royal Horse Artillery regiments and a
    motor battalion -- and not one tank, not one armoured car. The chart deploys it with two
    armoured brigades of two tank regiments apiece and the 11th Hussars as divisional recon."""
    by = _campaign_units()
    #   counter id            role      model     TOE  (chart's TOE & Weapon System(s) column)
    for uid, role, model, toe in (("4-Armd-Bde-HQ-[7]", "hq_b",       None,   1),
                                  ("6-RTR-[7]",         "tank",       "mk6", 10),
                                  ("7-Hus-[7]",         "tank",       "mk6", 10),
                                  ("7-Armd-Bde-HQ-[7]", "hq_d",       None,   1),
                                  ("1-RTR-[7]",         "tank",       "a9",   7),
                                  ("8-Hus-[7]",         "tank",       "a10",  7),
                                  ("7-Spt-Grp-HQ-[7]",  "hq",         None,   1),
                                  ("2-RflBde-[7]",      "infantry_n", None,   6),
                                  ("11-Hus-[7]",        "recon_ll",   None,   6)):
        u = by[uid]
        assert u.arrival_turn == 0, f"{uid}: the chart prints Arrives 'D'"
        assert u.steps[0].label == role, f"{uid}: role {u.steps[0].label}, chart implies {role}"
        assert u.strength == toe, f"{uid}: TOE {u.strength}, chart prints {toe}"
        assert u.morale == 2                       # sheet header 'Basic Morale: +2'
    # the four tank regiments really are tanks, at the models the chart names
    assert all(by[f"{r}-[7]"].is_tank for r in ("6-RTR", "7-Hus", "1-RTR", "8-Hus"))
    # 11 Hus prints 'U@6 TOE' -- understrength at six, against the 'll' row's Maximum TOE of eight,
    # so it arrives with headroom a Replacement Point can fill (chart key, p.116).
    assert by["11-Hus-[7]"].max_toe == 8 and by["11-Hus-[7]"].strength == 6


def test_the_7th_armoured_stands_where_60_41_prints_it():
    """[60.41] Commonwealth Initial Deployment, scan p.78, names three of these counters at their
    own hexes rather than with the division: 'C3520: 1st RTR (7/7)', 'C3320: 2nd Rifle Bde (I;
    7Spt/7)', 'C3020: 11th Hus (R; 7Spt/7)'. The rest are 'D3612: 7th Armored Division'."""
    for counter, label in (("1 RTR [7]", "C3520"), ("2 RflBde [7]", "C3320"),
                           ("11 Hus [7]", "C3020"), ("6 RTR [7]", "D3612"),
                           ("7 Spt Grp HQ [7]", "D3612")):
        assert _extra(counter)["hex"] == label


# --- 3. Operation Compass ------------------------------------------------------------------

def test_the_operation_compass_order_of_battle_is_on_the_map_at_game_turn_one():
    """[4.44B] p.124 (6th Australian), p.126 (4th Indian), p.129 (2nd New Zealand). 27 counters,
    every one of them 'D'. This is the infantry that took Bardia and Tobruk."""
    by = _campaign_units()
    aus = ["16-Aus-Bde-HQ-[6-Aus]", "2/1-Aus-[16-Aus]", "2/2-Aus-[16-Aus]", "2/3-Aus-[16-Aus]",
           "17-Aus-Bde-HQ-[6-Aus]", "2/5-Aus-[17-Aus]", "2/6-Aus-[17-Aus]", "2/7-Aus-[17-Aus]",
           "6-AusCav-[6-Aus]"]
    ind = ["5-In-Bde-HQ-[4-In]", "1-RFslr-[5-In]", "3/1-Pjb-[5-In]", "4/6-RajRf-[5-In]",
           "11-In-Bde-HQ-[4-In]", "2-Cmrn-[11-In]", "1/6-RajRf-[11-In]", "4/7-Rajpt-[11-In]",
           "1-CIH-[4-In]", "25-Fld-[4-In]"]
    nz = ["4-NZ-Bde-HQ-[2-NZ]", "18-NZ-[4-NZ]", "19-NZ-[4-NZ]", "20-NZ-[4-NZ]",
          "27-NZ-MG-Bn-[2-NZ]", "2-NZ-Cv-[2-NZ]", "4-NZ-Fld-[2-NZ]"]
    for uid in aus + ind + nz:
        assert uid in by, f"{uid}: charted 'D' on its [4.44B] sheet and missing from the OOB"
        assert by[uid].arrival_turn == 0, f"{uid}: the chart prints Arrives 'D'"
    # the brigade HQs the chart gives an Anti-Armor rating to (p.124: 16 Aus 'f', 17 Aus 'e')
    assert by["16-Aus-Bde-HQ-[6-Aus]"].anti_armor == 2
    assert by["17-Aus-Bde-HQ-[6-Aus]"].anti_armor == 1
    # 27 NZ prints 'U@2' against the 'u' row's Maximum TOE of three
    assert by["27-NZ-MG-Bn-[2-NZ]"].strength == 2 and by["27-NZ-MG-Bn-[2-NZ]"].max_toe == 3
    # the three divisional recce counters are the 'll' row (Armor Protection 1), not 'pp'
    for uid in ("6-AusCav-[6-Aus]", "1-CIH-[4-In]", "2-NZ-Cv-[2-NZ]"):
        assert by[uid].armor_protection == 1 and by[uid].max_toe == 8


def test_the_compass_divisions_stand_where_60_41_prints_them():
    """[60.41] p.78: 'Cairo and/or Helwan (E 1430): In Training: 6th Australian Division';
    'Alexandria (E3613 &/or 3714): HQ: 2nd New Zealand Division; 4th NZ Bde (2 NZ); 27th NZ MG Bn
    (2 NZ); 2nd NZ Cavalry (2 NZ); 4th NZ Field Arty Regt (2 NZ)'; 'D3615: 4th Indian Division'."""
    assert _extra("16 Aus Bde HQ [6 Aus]")["hex"] == "E1430"
    assert _extra("4 NZ Bde HQ [2 NZ]")["hex"] == "E3613"
    assert _extra("5 In Bde HQ [4 In]")["hex"] == "D3615"
    assert _extra("16 Inf Bde HQ [70]")["hex"] == "E1829"        # '[60.41] E1829: 16th Inf Bde (70)'
    assert _extra("1 SoStff")["hex"] == "D3714"                  # attached to the Matruh Garrison


# --- 4. the rest of the roster --------------------------------------------------------------

def test_the_alamein_infantry_division_arrives_whole():
    """[4.44B] p.118, 44th (Home Countries) Infantry Division: two of its three infantry brigades,
    its MG battalion, its recce regiment and its Light AA regiment were absent -- eleven counters,
    all printed '2/90'. (The row-by-row Arrives alignment matters here: the sheet's artillery is
    2/95 and the 30th Light AA is 2/90, one row below three 2/95 rows.)"""
    by = _campaign_units()
    for counter, role in (("132 Inf Bde HQ [44]", "hq"), ("4 RWK [132]", "infantry_m"),
                          ("5 RWK [132]", "infantry_m"), ("2 Buffs [132]", "infantry_m"),
                          ("133 Inf Bde HQ [44]", "hq"), ("2 RSsx [133]", "infantry_m"),
                          ("4 RSsx [133]", "infantry_m"), ("5 RSsx [133]", "infantry_m"),
                          ("6 Ches MG Bn [44]", "mg"), ("44 Recce Regt [44]", "recon_ll"),
                          ("30 LAA [44]", "aa")):
        rec = _reinf(counter)
        assert (rec["arrival_turn"], rec["arrival_stage"]) == (90, 2), f"{counter}: chart prints 2/90"
        assert rec["role"] == role
        assert by[counter.replace(" ", "-")].morale == 2      # sheet header 'Basic Morale: +2'


def test_the_understrength_arrivals_are_seeded_at_their_printed_toe():
    """The chart's key, p.116: 'U@# = Understrength at "x" TOE Strength Points. The unit
    arrives/deploys with that number of TOE Strength Points... but may only absorb replacement
    points up to the maximum number permitted for that ID Code.' Four counters in this roster
    print one, and before this slice the engine had no way to say it -- every unit was built at
    its role's full TOE."""
    by = _campaign_units()
    for uid, toe, max_toe in (("11-Hus-[7]", 6, 8),               # p.117 'U@6 TOE', row 'll'
                              ("27-NZ-MG-Bn-[2-NZ]", 2, 3),       # p.129 'U@2', row 'u'
                              ("28-Mao-[4-NZ]", 2, 7),            # p.129 'U@2', row 'k'
                              ("Kopnski-[Polish]", 1, 2)):        # p.132 'U@1', row 'w'
        assert (by[uid].strength, by[uid].max_toe) == (toe, max_toe), uid


def test_the_polish_brigade_is_more_than_three_rifle_battalions():
    """[4.44B] p.132. The engine seeded an HQ and three anonymous battalions; the sheet prints an
    MG company, a cavalry regiment, an anti-tank company and an artillery regiment beside them --
    half the brigade's counters, all '3/1'."""
    for counter, role in (("Kopnski [Polish]", "infantry_w"), ("1 PolCv [Polish]", "recon_ss"),
                          ("1 Pol AT Coy [Polish]", "antitank_dd"),
                          ("1 Pol Arty Regt [Polish]", "artillery_y")):
        rec = _reinf(counter)
        assert (rec["arrival_turn"], rec["arrival_stage"]) == (1, 3), f"{counter}: chart prints 3/1"
        assert rec["role"] == role


def test_the_1st_and_2nd_armoured_divisions_get_their_support_arms():
    """[4.44B] p.116 (1st Armored: 3/58 and 3/59) and p.117 (2nd Armored: all 1/15)."""
    for counter, gt, stage in (("1 RflBde [1]", 58, 3), ("2 KRRC [1]", 59, 3),
                               ("76 AT Regt [1]", 59, 3), ("11 RHA [1]", 59, 3),
                               ("61 LAA [1]", 59, 3),
                               ("3 Armd Bde HQ [2]", 15, 1), ("2 Spt Grp HQ [2]", 15, 1),
                               ("1 THRf [2]", 15, 1), ("1 Ranger [2]", 15, 1),
                               ("2 RHA [2]", 15, 1), ("102(NH) [2]", 15, 1),
                               ("KDGd [2]", 15, 1)):
        rec = _reinf(counter)
        assert (rec["arrival_turn"], rec["arrival_stage"]) == (gt, stage), counter
    # the 102(NH) is the chart's only 'bb' counter: four anti-tank + two Light AA TOE Strength
    # Points is its ceiling, and it arrives with '2 x 2-pounders, 2 x Light AA' = four.
    assert _reinf("102(NH) [2]")["role"] == "antitank_bb"
    assert _reinf("102(NH) [2]")["toe"] == 4
    # ...and it is NOT the 102nd Anti-tank Regt already seeded: the Unassigned Anti-tank sheet's
    # own note b (p.121) says so -- "this is not the same unit as the 102(NH) Anti-tank/light
    # anti-aircraft unit."
    assert any(r["counter"] == "102nd AT" for r in REINF)


# --- 5. the transcription errors this slice repairs -----------------------------------------

def test_royal_yugoslav_guards_is_id_code_t():
    """[4.44B] p.122, Unassigned British Infantry-type Units. The transcription recorded ID Code
    'f'; re-rendered at 600 dpi and cropped to the ID column, the book prints 't' -- a crossbar
    and a curved foot, plainly different from the plain-vertical 'l' of the 1st Sherwood
    Forresters printed one row above it and the 14th Sherwood Forresters one row below.

    It is not cosmetic. 'f' is a HEADQUARTERS row (CPA 20, Anti-Armor 2, Vulnerability 1, CA 0/1);
    't' is an Infantry Bn-Eq (CPA 10, CA 1/1, Maximum TOE 3). The counter was seeded 'infantry'
    (row 'p': CA 1/2, Maximum TOE 6), which is neither."""
    by = _campaign_units()
    u = by["Royal-Yugoslav-Guards"]
    assert u.steps[0].label == "infantry_t"
    assert (u.cpa, u.oca, u.dca, u.max_toe) == (10, 1, 1, 3)
    assert u.is_combat is True                      # 't' is an infantry battalion, not an HQ


def test_the_10th_indian_brigade_group_artillery_are_artillery():
    """[4.44B] p.128. The 10th Indian Division's three brigade groups each print a Field Artillery
    Regiment at ID Code 'x' -- 97 Fld (3/82), 157 Fld (3/82), 164 Fld (2/82), all 6 x 25-pounders.
    The engine covered them with anonymous '20/21/25 In Bde Grp III' slots typed `infantry`:
    three artillery regiments playing as rifle battalions."""
    by = _campaign_units()
    for counter, gt, stage in (("97 Fld [20 In]", 82, 3), ("157 Fld [21 In]", 82, 3),
                               ("164 Fld [25 In]", 82, 2)):
        rec = _reinf(counter)
        assert rec["role"] == "artillery" and rec["model"] == "25pdr", counter
        assert (rec["arrival_turn"], rec["arrival_stage"]) == (gt, stage), counter
        assert by[counter.replace(" ", "-")].barrage > 0
    # the anonymous III slots they replaced are gone
    assert not any(r["counter"].endswith("In Bde Grp III") for r in REINF)


def test_the_two_free_french_role_mismatches_are_repaired():
    """[4.44B] p.131 and p.132. '1st Bn de fusiliers' (counter `1 Fslrs`) is ID Code 'ff' --
    Light Anti-air Bn-Eq, 4 x Light AA -- and was seeded `infantry`. '23 NA Anti-tank Coy'
    (counter `23 NA`) is ID Code 'cc' -- Anti-tank Company-Eq, 3 x 2-pounder -- and was standing
    in the 2nd Free French Brigade as a third anonymous rifle battalion."""
    by = _campaign_units()
    fslr = _reinf("1st Bn de Fusiliers [1 FF]")
    assert fslr["role"] == "light_aa_ff" and fslr["model"] == "light_aa" and fslr["toe"] == 4
    assert by["1st-Bn-de-Fusiliers-[1-FF]"].is_pure_aa is True
    na = _reinf("23 NA AT Coy [2 FF]")
    assert na["role"] == "antitank_cc" and na["model"] == "2pdr" and na["toe"] == 3
    assert (na["arrival_turn"], na["arrival_stage"]) == (75, 3)      # chart prints 3/75
    assert by["23-NA-AT-Coy-[2-FF]"].anti_armor > 0
    assert not any(r["counter"] == "2 Free French Bde III" for r in REINF)


def test_the_22nd_armoured_brigade_arrives_when_the_chart_says():
    """[4.44B] p.121: the 22nd Armored Bde HQ and its three County London Yeomanry regiments all
    print Arrives '3/20'. The engine had them at Game-Turn 51 -- thirty-one Game-Turns late, which
    is the whole of the 1941 fighting."""
    for counter in ("HQ 22 Armd Bde", "22 Armd Bde Regt I",
                    "22 Armd Bde Regt II", "22 Armd Bde Regt III"):
        rec = _reinf(counter)
        assert (rec["arrival_turn"], rec["arrival_stage"]) == (20, 3), counter


def test_the_only_commonwealth_engineers_arrive_when_the_chart_says():
    """[4.44B] p.130 ('10th NZ RR Construction Coy' 1/32, '13th NZ RR Construction Coy' 3/50) and
    p.129 ('1st SA Road Construction Bn' 1/50). All three were anchored to Game-Turn 6 by a
    FLAGGED proxy -- 'the campaign OOB's engineer rows are untranscribed' -- and they no longer
    are. These are the ONLY Commonwealth 'uu' construction counters in the game and [24.61] makes
    the NZ pair the only units that may build railroad at all, so their arrival turn decides when
    the Western Desert Railway can leave Mersa Matruh."""
    for counter, gt, stage in (("10 NZ RR Constr Coy", 32, 1), ("13 NZ RR Constr Coy", 50, 3),
                               ("1 SA Road Constr Bn", 50, 1)):
        rec = _reinf(counter)
        assert (rec["arrival_turn"], rec["arrival_stage"]) == (gt, stage), counter


# --- 6. the honest negatives ----------------------------------------------------------------

def test_the_200th_guards_brigade_is_absent_and_the_book_is_why():
    """The ONE counter on the 91-row roster that this slice does not seed. [4.44B] p.121's 22nd
    Guards Brigade sheet is prose, not a table: 'Basic Morale: None (that of attached units). ID
    Code: a', and 'In January 1942, it became the 200th Guards Brigade... Note that there are two
    counters (22 Gds and the 200 Gds) provided for this unit.' A month is not an Arrives cell.
    Every other row on the roster carries a printed OpStage/Game-Turn; this one does not, so
    seeding it would mean inventing a swap turn. Absent, with the reason recorded rather than a
    number guessed."""
    assert not any("200 Gds" in r.get("counter", "") for r in REINF)
    assert not any("200 Gds" in r.get("counter", "") for r in EXTRA)
    assert any(r["counter"] == "HQ 22 Guards Bde" for r in REINF)     # its sibling counter is seeded


def test_the_three_authored_placements_are_the_only_ones():
    """Every at-start counter this slice adds stands where [60.41] prints it, with exactly three
    exceptions, each recorded in the record's own `_comment`:

    (1) `1 Buffs` and `1 Hamp` are 'D' on [4.44B] p.122 and [60.41] names neither, so they are
        placed with the other Cairo-area unassigned British battalions the extraction carries.
    (2) The 11th Indian Brigade stands one hex from its division. [60.41] prints ONE hex for the
        4th Indian ('D3615') and the division's counters total EIGHT Stacking Points there, on a
        Rough hex whose [8.37] limit is six. [9.14] caps a hex 'at the end of any Movement
        Segment', which a set-up is not -- but this engine's at-rest invariant sweep runs at run
        start and would raise. The brigade therefore stands on D3614, adjacent.
    (3) The Polish Brigade's support half. All eight of its counters print '3/1', so all eight are
        on the map during Game-Turn 1; [60.41] does not mention the brigade at all, and its
        existing entry hex is itself the reinforcement builder's authored choice. Seven Stacking
        Points would not fit on one Delta hex, so the four counters this pass adds muster on the
        next Cairo hex."""
    assert _extra("1 Buffs")["hex"] == _extra("1 Hamp")["hex"] == "E4115"
    assert _extra("11 In Bde HQ [4 In]")["hex"] == "D3614"
    assert _extra("5 In Bde HQ [4 In]")["hex"] == "D3615"
    for counter in ("1 Buffs", "1 Hamp", "11 In Bde HQ [4 In]"):
        assert "_comment" in _extra(counter), f"{counter}: an authored placement must say so"
    assert _reinf("1 PolCv [Polish]")["hex"] == [42, 141]
    assert _reinf("Polish Bde I")["hex"] == [42, 140]
    # every other at-start counter this pass adds cites [60.41] in its own comment
    charted = [r for r in EXTRA if r.get("kind") == "unit" and r.get("side") == "ALLIED"
               and r["counter"] not in ("1 Buffs", "1 Hamp", "11 In Bde HQ [4 In]",
                                        "2 Cmrn [11 In]", "1/6 RajRf [11 In]",
                                        "4/7 Rajpt [11 In]", "1 CIH [4 In]")]
    for rec in charted:
        assert "[60.41]" in rec["_comment"], f"{rec['counter']}: no [60.41] citation"


def test_the_setup_the_charts_produce_is_legal_at_rest():
    """39 counters land on the Game-Turn-1 map. The regression this guards is the one that would
    have been found by a crash three weeks later: an over-stacked set-up hex raises out of
    game.invariants at run start, before a single event."""
    st = scenario.campaign(42)
    assert adjudication.stacking_violations(st) == []


def test_the_charted_counters_all_stand_on_hexes_the_map_carries():
    st = scenario.campaign(42)
    for rec in EXTRA:
        if rec.get("kind") == "unit" and rec.get("side") == "ALLIED":
            ax = coords.to_axial(coords.parse(rec["hex"]))
            assert ax in st.terrain.terrain, f"{rec['counter']}: {rec['hex']} is off the map"


# --- 7. the size of the debt this pays ------------------------------------------------------

def test_ninety_of_the_ninety_one_missing_counters_are_now_seeded():
    """The survey measured 91 named counters absent outright; 90 are seedable straight off the
    charts and the 91st (`200 Gds`) is the one the book gives no arrival for. 39 of the 90 are
    'D' and land in data/oob_campaign_extra.json; 51 are rule-20 reinforcements."""
    added_extra = [r for r in EXTRA if r.get("kind") == "unit" and r.get("side") == "ALLIED"]
    # the four division HQs the Phase-8.1c pass seeded were already there
    assert len(added_extra) == 4 + 39
    by = _campaign_units()
    # The survey's own definition of a DISTINCT counter, so the two numbers are comparable: a
    # "(Rtn)" record is the same physical counter returning from Syria or Palestine, not a new one
    # (rule 20.8 withdrawals are unmodelled, so the return arrives beside its original -- a
    # pre-existing double-count this pass neither widens nor hides).
    cw = [u for u in by.values() if u.nationality == "CW" and "SGSU" not in u.id]
    distinct = [u for u in cw if "(Rtn)" not in u.id]
    assert len(cw) - len(distinct) == 47                 # the survey's 47 re-arrivals, unchanged
    assert len(distinct) == 349 + 90                     # 349 before this slice, nothing removed
