"""Load the faithful logistics magnitudes from data/logistics_rates.json.

This mirrors how game.oob loads data/unit_stats.json: a thin, cached reader that
turns the transcribed rulebook charts into the constants the supply/engine code
consumes, so the balance is the RULEBOOK'S (one source of truth) rather than magic
numbers scattered through game/*.py. Each accessor cites the chart it draws from.

WIRED FAITHFULLY here (magnitudes now equal to the chart values):
  - [50.2] Ammunition Consumption Rates -- barrage 4, anti-armor 3, close-assault 2.
  - 51.11/51.13 Stores -- 4 per TOE (combat), 1 per TOE (HQ/engineer/non-combat).
  - [49.3]/52.44 Fuel & Water evaporation -- 6% base, +5% hot.
  - [54.12] Supply Dump Capacity (Other-Terrain ceilings) and the Major-City U.
  - [49.13]/[4.47-4.49] per-model Fuel Consumption Rate (fuel_rate_by_model) -- now
    wired onto Unit.fuel_rate (game.oob) with the x TOE-strength law (game.supply.
    fuel_cost). This is the Regime-B FULL-LOGISTICS fuel demand.
  - 61.44/61.36 real-scale Desert Fox dump pools + 55.3 per-port supply tonnage --
    the reservoir the real fuel demand draws on (game.oob / game.scenario).

([54.5] Equivalent Weights stay as exact fractions in supply.TONS_PER_POINT: the
data file rounds Water to 0.1667, so sourcing it here would inject a rounding error
into the conservation math -- they are exact-faithful already.)

STILL PROXY: the per-MOBILITY Fuel Rate (fuel_rate_proxy, flat 2/1) survives only as
the fallback for scenarios whose units carry no transcribed Unit.fuel_rate (the toy
coastal corridor); the real Desert Fox OOB now uses the per-model chart above.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from .terrain import Mobility

_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "logistics_rates.json"))


@lru_cache(maxsize=1)
def _data() -> dict:
    with open(_PATH) as f:
        return json.load(f)


def ammo_rates() -> dict:
    """[50.2] Ammunition Consumption Rates (Ammo Points per TOE Strength Point using
    the function, rule 50.14), keyed by the activity string the engine passes. The
    'assault' key carries the chart's close_assault rate."""
    played = _data()["ammunition_consumption"]["logistics_game_played"]
    return {
        "barrage": played["barrage"],            # 4
        "anti_armor": played["anti_armor"],      # 3
        "assault": played["close_assault"],      # 2 (close assault)
    }


def stores_rates() -> dict:
    """51.11/51.13 Stores per TOE Strength Point per Game-Turn: combat units 4, HQ /
    engineer / non-combat 1."""
    s = _data()["stores_consumption"]
    return {"combat": s["per_toe_strength_point_per_game_turn"],
            "noncombat": s["hq_or_engineer_per_game_turn"]}


def evaporation_percent() -> dict:
    """[49.3]/52.44 Fuel & Water evaporation: 6% base per Game-Turn, +5% in hot
    weather (rounded down)."""
    e = _data()["fuel_consumption"]["evaporation_49_3"]
    return {"base": e["base_percent_per_game_turn"],
            "hot_additional": e["hot_weather_additional_percent"]}


def demolition_percent_54_17() -> dict:
    """[54.17] SUPPLY DUMP DEMOLITION TABLE: the percentage of EVERY commodity in a dump destroyed,
    keyed by the MODIFIED die roll (int), with the chart's "8 or more" row under the key 8.

    ERRATA APPLIED (owner-approved) -- THE ONE PLACE THIS TRANSCRIPTION OVERRIDES THE BOOK. The 1979
    printing is misprinted: it reads -2:0 -1:33 0:0 1:10 2:20 3:33 4:50 5:75 6:100 7:33 8+:100, so a
    modified -1 destroys a THIRD while a 0 destroys nothing, and a 7 undoes a 6. Two auditors rendered
    the original scan (PDF p109) at 400 and 600 dpi and both confirm the OCR is faithful -- the page
    really is non-monotone. The correction is forced by the neighbours: strike -1 and 7 and every other
    cell is a clean ladder 0/10/20/33/50/75/100, and those two cells are pinned on both sides (-1
    between two 0s, 7 between two 100s) -- a duplicated '33' slug in the paste-up. Corrected -1:33->0,
    7:33->100. The printed values, the corrected values and this reasoning are recorded under the
    _errata key in data/logistics_rates.json; percent_by_modified_die there is the corrected table."""
    row = _data()["supply_dump_demolition_54_17"]["percent_by_modified_die"]
    return {(8 if k == "8+" else int(k)): v for k, v in row.items()}


def _dump_cap_row(name: str) -> dict:
    """One row of the [54.12] Supply Dump Capacity Chart, keyed by engine commodity name."""
    row = _data()["supply_dump_capacity_54_12"][name]
    return {"AMMO": row["ammo"], "FUEL": row["fuel"],
            "STORES": row["stores"], "WATER": row["water"]}


def dump_other_terrain_cap() -> dict:
    """[54.12] Supply Dump Capacity Chart, the Other-Terrain row (the ceiling a
    non-city dump hex may hold), keyed by engine commodity name."""
    return _dump_cap_row("other_terrain")


def dump_village_cap() -> dict:
    """[54.12] Supply Dump Capacity Chart, the VILLAGE row -- the ceiling a dump in a village
    hex may hold (2,500 Ammo / 8,000 Fuel / 3,000 Stores / 1,000 Water). Between the Major-City
    row (unlimited) and Other Terrain. See game.villages for which hexes carry a village."""
    return _dump_cap_row("village")


def fuel_rate_proxy() -> dict:
    """PROXY fallback: the per-mobility-class Fuel Consumption Rate used only for units
    that carry no transcribed Unit.fuel_rate (the toy coastal-corridor scenario). The
    real Desert Fox OOB carries the per-model rate from fuel_rate_by_model(). Recorded
    in the data file's engine_proxy block so the proxy has a single, documented home."""
    by_name = _data()["fuel_consumption"]["engine_proxy"]["fuel_rate_by_mobility"]
    return {Mobility[name]: rate for name, rate in by_name.items()}


def fuel_rate_by_model() -> dict:
    """[49.13]/[4.47-4.49] per-model Fuel Consumption Rate, flattened from the three
    tank Characteristics sub-charts (german_tank / commonwealth_tank / italian_tank)
    into a single {model_name: rate} map. Model names mirror data/unit_stats.json
    'models'. The gun/SP scalars in the same chart are role-level defaults (they are
    not per-model), so game.oob applies them as role defaults rather than reading them
    here. Tanks span rate 1 (Mk VI light) to 7 (Grant / Churchill)."""
    chart = _data()["fuel_consumption"]["fuel_consumption_rate_by_model"]
    out: dict = {}
    for nation_key in ("german_tank", "commonwealth_tank", "italian_tank"):
        out.update(chart[nation_key])
    return out


def truck_characteristics() -> dict:
    """[54.2] Truck Characteristics Chart, reduced to what the CHUNK-4 haulage layer
    consumes, keyed by class ('light'|'medium'|'heavy'): the per-Truck-Point supply-point
    capacity of each commodity (the chart's 'Supplies' columns), the convoy CPA (the
    chart's Supplies CPA, which EQUALS the 53.22 extended allowance -- Light 40,
    Medium/Heavy 30), the truck's own Fuel Capacity (self-tank), and its Fuel Consumption
    Factor (1 for every class). Verified cell-by-cell against docs/rules/90."""
    chart = _data()["truck_characteristics_54_2"]
    out: dict = {}
    for cls in ("light", "medium", "heavy"):
        row = chart[cls]
        cap = row["supply_point_capacity"]
        out[cls] = {
            "capacity": {"AMMO": cap["ammo"], "FUEL": cap["fuel"],
                         "STORES": cap["stores"], "WATER": cap["water"]},
            "convoy_cpa": row["cpa"]["supplies"],
            "fuel_capacity": row["fuel_capacity"],
            "fuel_factor": row["fuel_consumption_factor"],
        }
    return out


def _scenario_61() -> dict:
    return _data()["scenario_61_desert_fox_initial_supply"]


def axis_dump_pool_61_44() -> dict:
    """[61.44] the FULL-LOGISTICS Axis start-line supply pool, split across the Axis
    dumps (game.oob authored placement). Keyed by engine commodity name."""
    p = _scenario_61()["axis_dump_split_61_44"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"], "WATER": p["water"]}


def cw_dump_pool_61_36() -> dict:
    """[61.36] the FULL-LOGISTICS Commonwealth start-line supply pool (fuel/ammo/stores),
    split across the CW dumps. Note 61.36 charts NO dump Water for the Commonwealth --
    CW water comes from the 52.7 wells and the 54.3 rail, both deferred -- so game.oob
    seeds a FLAGGED wells/rail Water proxy on top of this."""
    p = _scenario_61()["commonwealth_dump_split_61_36"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def _scenario_60() -> dict:
    return _data()["scenario_60_campaign_initial_supply"]


def axis_dump_pool_60_34() -> dict:
    """[60.34] the FULL-CAMPAIGN Axis anonymous field-dump pool (Dump 1 + Dump 2), split
    across the Axis field dumps by game.oob. Rule 64.3 mandates Section 60 for the entire
    campaign -- this REPLACES the 61.44 Desert-Fox pool (which gave 9600 Fuel, not 3000)."""
    p = _scenario_60()["axis_field_dump_pool_60_34"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"], "WATER": p["water"]}


def cw_dump_pool_60_44() -> dict:
    """[60.44] the FULL-CAMPAIGN Commonwealth anonymous field-dump pool (Dump I). 64.3
    mandates Section 60; this REPLACES the 61.36 Desert-Fox pool. 60.44 charts NO dump
    Water (deferred 52.7 wells / 54.3 rail; unlimited water at Cairo/Alexandria)."""
    p = _scenario_60()["commonwealth_field_dump_pool_60_44"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def axis_air_pool_61_44() -> dict:
    """[61.44] the Desert Fox Axis AIR-FACILITY supply allotment -- "for distribution to Air
    Facilities... there are 50 Fuel Points and 50 Ammo Points" (no Stores, no Water charted). It
    lands in the rule-36.17 air-facility dumps, which only an SGSU may draw from (35.14)."""
    p = _scenario_61()["axis_air_facility_pool_61_44"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"]}


def cw_air_pool_61_36() -> dict:
    """[61.36] the Desert Fox Commonwealth AIR-FACILITY supply allotment -- "180 Fuel Points, 250
    Ammo Points, and 50 Stores for distribution amongst Air Facilities" (no Water charted)."""
    p = _scenario_61()["commonwealth_air_facility_pool_61_36"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def axis_air_pool_60_34() -> dict:
    """[60.34] the FULL-CAMPAIGN Axis AIR-FACILITY supply allotment -- "a total of 1200 Ammo, 850
    Fuel, 100 Stores and 100 Water Points which may be freely distributed among his airfields"."""
    p = _scenario_60()["axis_air_facility_pool_60_34"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"], "WATER": p["water"]}


def cw_air_pool_60_44() -> dict:
    """[60.44] the FULL-CAMPAIGN Commonwealth AIR-FACILITY supply allotment -- "Air Supply
    (Distribute amongst Air Facilities as desired): Ammo 200, Fuel 250, Stores 50" (no Water)."""
    p = _scenario_60()["commonwealth_air_facility_pool_60_44"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def campaign_air_pool_kinds() -> dict:
    """[60.34]/[60.44] WHICH KINDS OF AIR FACILITY each side's campaign air allotment may stand on.

    The two rows do not say the same thing and the difference is the book's: the Axis pool is
    "freely distributed among his AIRFIELDS" while the Commonwealth's is "distribute amongst AIR
    FACILITIES as desired". That was inert while the campaign's air map was the VASSAL extraction
    (which carried no airfield at all, so the restriction had nothing to select); [60.5] put 15
    Airfields, 31 Air Landing Strips, 2 Basins and 1 Alighting Area on the board and made the word
    load-bearing. Returned by SIDE NAME (the caller keys it to Side), each value a tuple of
    game.air kind strings or None for unrestricted."""
    s = _scenario_60()
    rows = {"AXIS": s["axis_air_facility_pool_60_34"],
            "ALLIED": s["commonwealth_air_facility_pool_60_44"]}
    return {side: None if row["facility_kinds"] is None else tuple(row["facility_kinds"])
            for side, row in rows.items()}


def italian_sgsu_available_60_32() -> int:
    """[60.32] "Italian SGSU Available: 39" -- the last line of the Italian Air Strengths chart."""
    return _scenario_60()["italian_sgsu_available_60_32"]["sgsu"]


def cw_sgsu_available_60_42() -> int:
    """[60.42] "SGSU Available: 14" -- Commonwealth North African Air Force."""
    return _scenario_60()["commonwealth_sgsu_available_60_42"]["sgsu"]


def tobruk_builtin_61_36() -> dict:
    """[61.36] Tobruk's built-in supply (fuel/ammo/stores); Tobruk is itself a dump."""
    p = _scenario_61()["commonwealth_tobruk_builtin_61_36"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def tripoli_builtin_61_44() -> dict:
    """[61.44] the Tripoli box built-in supply (fuel/ammo/stores), held IN ADDITION to the
    61.44 field-dump split -- the standing stock at the rear Axis harbour."""
    p = _scenario_61()["axis_tripoli_builtin_61_44"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def port_supply_tonnage_55_3() -> dict:
    """[55.3] per-port MAXIMUM supply tonnage per Operations Stage + its Efficiency
    Level, keyed by port name (game.scenario crosses tonnage->points via 54.5)."""
    return _data()["port_supply_tonnage_55_3"]["max_supply_tonnage_per_opstage"]


def convoy_level_56_4() -> dict:
    """[56.4] Axis Naval Convoy Level letter (A-G / '-') by calendar year and month."""
    return _data()["axis_naval_convoys_56"]["convoy_level_chart_56_4"]


def convoy_capacity_56_5() -> dict:
    """[56.5] Axis Naval Convoy capacity by Level: fixed_tons + variable_tons_per_die x die."""
    return _data()["axis_naval_convoys_56"]["convoy_capacity_table_56_5"]


def convoy_bombing_crt_41_66() -> list:
    """[41.66]/[32.66] the Axis-Naval-Convoy row of the [41.5] Air Bombardment &
    Secondary Barrage Targets Table: the ordered Bomb-Point columns of the convoy-
    bombing CRT. Each column carries its bomb_points bracket [lo, hi] (hi=None on the
    open 471+ bracket) and a `results` list of {die: [lo, hi], pct_lost}: the engine
    picks the column by total Bomb Points, then reads 2d6 SEQUENTIALLY as a two-digit
    code (tens=first die, units=second) and looks up the tens-of-percent cargo lost."""
    return _data()["axis_naval_convoys_56"]["air_convoy_bombing_crt_41_66"]["columns"]


def air_port_bombing_crt_41_5() -> list:
    """[41.39B]/[41.36] the "Airfields / Air Landing Strips / Ports" block of the [41.5] Air
    Bombardment & Secondary Barrage Targets Table -- ONE shared set of result columns for the
    three targets. Each column carries its bomb_points bracket [lo, hi] (hi=None on the open
    471+ bracket) and a `results` list of {die: [lo, hi], levels}: the engine picks the column
    by total Bomb Points, then reads 2d6 SEQUENTIALLY as a two-digit code (tens=first die,
    units=second) and looks up the RESULT.

    WHAT THE RESULT MEANS IS THE TARGET'S BUSINESS, NOT THIS ACCESSOR'S -- the chart's Key
    (transcribed verbatim beside the block under `_key_41_5`) makes it Efficiency Levels for a
    port (55.1), elimination for an Air Landing Strip, and Capacity Levels for an Airfield
    (41.36). game.air.levels_lost owns the two air readings; the `levels` field name is the
    Ports one because that is the row this block was first transcribed for."""
    return _data()["air_bombardment_41_5"]["ports"]["columns"]


def air_dump_bombing_crt_41_35() -> list:
    """[41.35] the SUPPLY DUMP row of the [41.5] Air Bombardment & Secondary Barrage Targets
    Table: the ordered Bomb-Point columns of the dump-bombing CRT. Same procedure as every other
    row -- pick the column by total Bomb Points, read 2d6 SEQUENTIALLY as a two-digit code -- and
    the result is `pct`, the percentage of EVERY supply in that dump eliminated (0/10/20/30/40/50/
    75). Transcribed and eyes-verified off the 1979 foldout, PDF page 107."""
    return _data()["air_bombardment_41_5"]["supply_dump"]["columns"]


def air_dump_truck_loss_per_pct_41_35() -> int:
    """[41.35] "In addition, if there are any unattached trucks in the hex, FOR EVERY 10% OF
    SUPPLIES DESTROYED, ONE TRUCK POINT IS LOST, choice of defender, dividing losses as evenly as
    possible." The chart's own Key says the same in fewer words ("lose 1 Truck Point for each 10%,
    if possible, defender's choice"). This is the 10."""
    return _data()["air_bombardment_41_5"]["supply_dump"]["truck_points_lost_per_pct"]


def air_truck_bombing_crt_41_32() -> list:
    """[41.32] the TRUCKS / Flak Suppression / Combat Units / Commonwealth Fleet row of the [41.5]
    table: the ordered Bomb-Point columns, each `results` entry carrying the number result `points`
    (0..7). Read as TRUCK POINTS destroyed, which is the chart Key's own word for it and the unit
    TruckFormation.points is denominated in. The row's other three readings (flak suppression,
    combat-unit pinning, Commonwealth Fleet damage) are the same numbers and are not wired -- see
    the data file's `_deferred`. Transcribed and eyes-verified off the 1979 foldout, PDF page 107."""
    return _data()["air_bombardment_41_5"]["trucks"]["columns"]


def aircraft_characteristics_4_44() -> dict:
    """[4.44A/b/c] AIRCRAFT CHARACTERISTICS CHARTS, by aircraft name: the charted `tacair`
    (34.13), `bombload` (34.14), `fuel` Consumption Rating (34.17/38.21 -- "the number of Fuel
    Points the plane requires before it may be flown") and `mission_capability` ("the types of
    missions the plane may be assigned" -- the F/S/R/D cells on the fighter charts, D/R/B/Transport
    on the bomber charts) of each transcribed type. EVERY TYPE THE [34.6]/[59.3] INITIAL AIR
    STRENGTHS FIELD is transcribed (game.roster), plus the three German heavy bombers rule 43.11/
    43.13 names; the rest of the three charts waits on the [34.86]/[34.87] reinforcement schedules.
    See the data file's own three notes (every row eyes-verified off the scan, BOTH the Commonwealth
    and Italian fighter OCR being column-shifted, and the D-vs-B reading of the Mission Capability
    column recorded as a flagged judgement call)."""
    return _data()["aircraft_characteristics_4_44"]["aircraft"]


def aircraft_refit_table_38_37() -> dict:
    """[38.37] AIRCRAFT REFIT TABLE, section B (by squadron) -- the ordered die columns of 38.34's
    roll, each carrying its modified-die bracket `die` [lo, hi] and the `pct_refitted` that column
    prints, plus the chart's own `modifiers`. One d6 plus modifiers spans exactly the printed 1..9.
    Section A (the 38.39 OPTIONAL per-plane method) is transcribed beside it in the data file and
    is deliberately not returned here: nothing rolls it."""
    return _data()["aircraft_refit_38_37"]["by_squadron"]


def squadron_capacity_35_23() -> dict:
    """[35.23] SQUADRON CAPACITY CHART, by nationality key ("italian", "german",
    "commonwealth_1940_june_41", "commonwealth_july_41_43"): the charted `ready` + `reserve` =
    `total`, the dated Commonwealth rows additionally carrying the `from`/`to` [year, month] span
    read off their own printed labels (the boundary is part of the chart, so it is transcribed with
    it). The total is the cap 38.23 puts on an SGSU's refuelling and 38.33 on its refitting -- "each
    SGSU can refit up to the maximum planes the SGSU can contain (Ready plus Reserve)".

    Returns only the APPLIED printing -- case 35.23's own table on PDF p.53, per the owner ruling of
    2026-07-21. The book prints this chart twice and the two disagree about the Commonwealth rows;
    the rejected one sits beside it in the data file under `play_aid_35_23_unapplied` with the
    ruling written out. See air.squadron_capacity."""
    return _data()["squadron_capacity_35_23"]["nationalities"]


# --- [44.0] MALTA -------------------------------------------------------------------------------
# A SECOND data file, and deliberately so: rule 44's charts are neither logistics rates nor an
# order of battle, and one of them (the printed Maltese air facilities) does not come out of the
# rulebook at all -- it comes off the game-map. They live together in data/malta_44.json with their
# provenance attached, and game.malta is the only reader.

_MALTA_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "malta_44.json"))


@lru_cache(maxsize=1)
def _malta() -> dict:
    with open(_MALTA_PATH) as f:
        return json.load(f)


def malta_facilities_44_12() -> list:
    """[44.12] The Maltese air facilities as PRINTED ON THE GAME-MAP -- name, hex label, kind and
    charted maximum Capacity Level. Read off the map image, not the rulebook (the book charts no
    Malta facility anywhere); the data file carries that provenance and the cross-check that every
    printed maximum equals its kind's rulebook ceiling."""
    return _malta()["air_facilities_44_12"]["facilities"]


def malta_planes_per_level_44_14() -> int:
    """[44.14] "Each 'level' of air facility can handle up to 18 planes of any type." """
    return _malta()["planes_per_level_44_14"]["planes"]


def malta_setup_60_46() -> dict:
    """[60.46] The campaign's Malta set-up (64.3 sends the full campaign to Section 60): the
    initial total `capacity_levels`, the month `construction_begins`, the printed `planes` roster
    and the `strike_weapon` block naming Malta's anti-shipping type and its per-plane points."""
    return _malta()["initial_setup_60_46"]


def malta_establishment_snapshots() -> list:
    """The book's four printed snapshots of Malta -- [60.46] September 1940, [61.34] March 1941,
    [62.36] November 1941, [63.37] October 1942 -- each with its `date`, `capacity_levels`, total
    `planes` and the `torpedo_planes` of that roster, in date order.

    These are the only statements the book makes about how big the island actually was, and they
    are the aiming point 34.81's free choice and 44.13's unmetered construction "may" are assigned
    to (game.malta.establishment). The data file's own `_comment` argues the assignment."""
    return _malta()["later_scenario_establishments"]["snapshots"]


def malta_planes_lost_pct_41_36() -> int:
    """[41.36] "For every level destroyed, REMOVE 10% OF THE PLANES ON THE GROUND (e.g., 2 levels,
    20% planes)", rounded down."""
    return _malta()["planes_on_the_ground_41_36"]["pct_per_level"]


def malta_construction_table_44_5() -> dict:
    """[44.5] MALTESE AIR FACILITY CONSTRUCTION TABLE: die face (as a string) -> the number of
    Capacity Levels repaired and/or constructed. One roll per Malta facility per Game-Turn."""
    return _malta()["construction_table_44_5"]["die"]


def malta_commitment_44_41(scenario: str = "campaign_64") -> dict:
    """[44.41] AXIS STRATEGIC AIRFORCE COMMITMENT CHART, one scenario row: Availability Level
    ("I".."IV") -> the number of Game-Turns it may be used, None for the chart's U (unlimited) and
    0 for its na. [64.52] sends both campaign games to the campaign row."""
    return _malta()["strategic_commitment_44_41"]["rows"][scenario]


def malta_availability_44_42() -> dict:
    """[44.42] AXIS MALTA AVAILABILITY TABLE: the two-dice total (as a string, 2..12) -> Level ->
    [in-play %, strategic %], or None for the chart's na."""
    return _malta()["availability_table_44_42"]["dice"]


def malta_italy_sicily_basing_43_1() -> dict:
    """[43.11]/[43.12]/[43.13] The rule-43 basing percentages of the Axis bomber force: the share
    in Italy/Sicily -- the base [44.42]'s percentages are percentages OF (`before_turn_35_pct`,
    `from_turn_35_pct`, meeting at `change_turn`) -- plus `crete_pct_from_turn_35`, the 43.13 half
    that may not raid Malta either (43.25), `mediterranean_pct`, the 43.11 TOTAL those two close on
    (transcribed for the cross-check, not read by game.basing, which adds up the two parts), the
    `constrained_types_43_11` the typed cases name AS THE [4.44b] CHART PRINTS THEM, and
    `ruled_type_43_11` -- the "FW220" the rule names against the chart row the owner ruled it to be
    (2026-07-21: the Fw. 200 C), kept as a pair so the prose name stays on the record."""
    return _malta()["italy_sicily_basing_43_1"]


# --- [60.5] THE CAMPAIGN AIR MAP -----------------------------------------------------------------
# A THIRD data file, on the same principle as data/malta_44.json: [60.5] is not a rate chart and it
# is not an order of battle -- it is a MAP, fifty-odd installations with printed hexes, and it is
# long enough that folding it into logistics_rates.json would bury both. game.oob is its only
# reader (charted_air_facilities).

_AIR_FACILITIES_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "air_facilities_60_5.json"))


@lru_cache(maxsize=1)
def _air_facilities() -> dict:
    with open(_AIR_FACILITIES_PATH) as f:
        return json.load(f)


def air_facilities_60_5() -> list:
    """[60.5] AIR FACILITIES -- the campaign's air map as the book prints it: every facility's
    `kind` (rule 36's four), `name`, printed `hex` label, the `country` it stands in and the `side`
    [60.5]'s geography rule gives it at the start of the game ("all facilities in Egypt belong to
    the Commonwealth; all those in Libya belong to the Italians"). Rows printed "Off-Map" carry
    `on_map: false` and are not placeable on maps A-E. Capacity is NOT here: it is rule 36's, by
    kind (game.air.MAX_CAPACITY). Verified against the scan, PDF p.79."""
    return _air_facilities()["air_facilities_60_5"]["facilities"]


# --- [34.6] / [59.3] THE INITIAL AIR STRENGTHS ---------------------------------------------------
# A FOURTH data file, on the same principle as data/malta_44.json and data/air_facilities_60_5.json:
# a scenario's Initial Air Strengths are not a rate chart, they are an ORDER OF BATTLE -- twenty
# printed muster rows carrying their own provenance, their own role reading and their own owner
# ruling. game.roster is its only reader.

_AIR_ESTABLISHMENTS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "air_establishments.json"))


@lru_cache(maxsize=1)
def _air_establishments() -> dict:
    with open(_AIR_ESTABLISHMENTS_PATH) as f:
        return json.load(f)


def air_establishments_59_3() -> dict:
    """[34.6]/[59.3] INITIAL AIR STRENGTHS, by scenario key then by side: the printed muster rows
    ([60.32] Italian, [60.42] Commonwealth), each with the [4.44] chart name of the `type`, the
    scenario's own spelling, Total `available`, Total `refitted` (59.32's readiness at Game-Turn 1)
    and the `role` the type is fielded in. Also carries the scenario's pilot and SGSU rows, and
    [60.32]'s garbled '2S01' row -- transcribed, UNSEEDED, and raised as an owner ruling. See
    game.roster for what reads this and the data file's own four notes for what it is."""
    return _air_establishments()


# --- [34.86] THE COMMONWEALTH AIRPLANE REINFORCEMENT SCHEDULE ------------------------------------
# A FIFTH data file, on the principle the four above already set: thirty printed schedule rows with
# their own key, their own withdrawal column and their own type-to-role reading are not a rate
# chart. game.malta is its only reader.

_AIR_REINFORCEMENTS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "air_reinforcements_34_86.json"))


@lru_cache(maxsize=1)
def _air_reinforcements() -> dict:
    with open(_AIR_REINFORCEMENTS_PATH) as f:
        return json.load(f)


def cw_air_reinforcements_34_86() -> list:
    """[34.86] COMMONWEALTH AIRPLANE REINFORCEMENT AND SQUADRON WITHDRAWAL SCHEDULE, one row per
    printed entry in the chart's own order: the `year`/`month`/`label` it is printed under, the
    `turns` it arrives on ([34.84]'s "divided amongst the weeks as evenly as possible"), the row
    `total`, the `planes` by printed type with the [4.44A] `chart_type` and the `role` it is
    fielded in, and the `withdrawals` column verbatim (34.85 -- transcribed, unapplied).

    Only 34.81A's Malta branch reads this; the mainland ninety per cent waits on [34.87], and the
    data file's own `_what_is_not_wired` says why the two schedules land together or not at all."""
    return _air_reinforcements()["commonwealth_34_86"]["months"]


def malta_share_pct_34_81a() -> int:
    """[34.81A] "No more than 10% of a month's airplane reinforcements may be sent to Malta." """
    return _air_reinforcements()["malta_share_34_81a"]["pct"]


def torpedo_chart_types_4_44a() -> frozenset:
    """[4.44A] The Commonwealth aircraft that MAY CARRY A TORPEDO -- the chart's `chart_type` names.

    The chart key: "Only planes possessing an '/T' may carry torpedos. The number to the right of
    the T is the Torpedo Capacity." Read off both of its tables end to end at 400 dpi, exactly three
    rows carry one (Albacore 8/T8, Beaufort Mk. I -/T8, Swordfish Mk. I -/T8) and all three at the
    same capacity -- which is what lets Malta's anti-shipping arm stay a single count instead of a
    per-type ledger, and what makes 41.73's "at least 50% of the planes are carrying torpedoes"
    true of that arm by construction."""
    return frozenset(_air_reinforcements()["torpedo_types_4_44a"]["chart_types"])
