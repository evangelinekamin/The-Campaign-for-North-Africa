"""[22.3] FACILITY REPAIRS -- the rear-area vehicle recovery economy.

    "There are two types of Repair Facilities: Temporary Facilities and Major Facilities.
     Temporary Facilities may be constructed by the Players (see Case 24.8), and those in
     existence at the start of a scenario are designated in that scenario. Major Repair
     Facilities are found in Tripoli (the Tripoli Box), Tobruk (for whoever controls it),
     Alexandria and Cairo (all hexes)." -- 22.31

THIS SLICE BUILDS THE MAJOR-FACILITY HALF -- the four locations 24.81 says are "already in
existence", so nothing need be constructed for them to work. Alexandria and Cairo are the
Commonwealth's own rear base and effectively unlosable in every scenario this engine runs;
Tobruk repairs for "whoever controls it" (22.31), so the facility itself is side-neutral
even though the geography favours the Commonwealth (Alexandria/Cairo never change hands;
Tobruk is contested) -- exactly the port plan's own verdict on this item: "HIGH -- this is
the Commonwealth's entire rear-area recovery economy" (scratchpad/port/00-THE-PORT-PLAN.md).
Tripoli, the one Axis-only Major Facility, is an off-map "Tripoli Box" (8.81/8.88) with NO
on-map hex in the full campaign() scenario (game.scenario._campaign_ports uses Benghazi, not
Tripoli, as the Axis harbour) -- so this module reports it as an empty set of Tripoli hexes
in the campaign, and picks up whatever on-map PROXY a scenario already stands in for the
harbour (rommels_arrival/siege_of_tobruk's "AX-Tripoli" SupplyUnit) where one exists -- the
same proxy those scenarios already use for the harbour itself, not a new invention.

Full transcription + scan cites: scratchpad/port/transcriptions/22.3-cw-rear-area-recovery.md

NAMED DEBT, NOT BUILT HERE:

  * 24.8 TEMPORARY REPAIR FACILITY CONSTRUCTION. 24.85 sites a temp facility "in any major
    city hex or in any village hex" -- this engine's terrain data has no village/town hex
    roster (only MAJOR_CITY hexes are enumerated, data/city_forts.json), so a faithful build
    would silently drop half the book's legal sites. The Construction Chart (24.17, PDF
    p.104) also prints Fuel costs and an Op-Stage count that CONTRADICT the rule prose
    (24.83: 150 Fuel / 3 Construction Segments to build; chart: 50 Fuel / 1 stage -- Stores
    (250) and the 24.84 rebuild's Stores (50) agree, but Fuel is exactly 1/3 of the prose
    figure both times) -- an owner ruling this slice records (prose wins, see the
    transcription section 5) but does not need to act on, because nothing is built. And even
    built, no Policy anywhere proposes a construction order for one (the same gap already
    flagged for minefields and fortifications in game.construction's own module docstring)
    -- a Temporary Facility, capped at two per side, would sit unused. Building the
    Major-Facility half alone delivers the load-bearing value the port plan names without
    half-building 24.8. SEPARATE, SMALLER, AND BETTER FOUNDED (found during the review repair,
    flagged not built): 22.31's OTHER source of Temporary Facilities is the scenario itself --
    "those in existence at the start of a scenario are designated in that scenario" -- and
    data/oob_desert_fox.json already carries two such records (Temp rep fac-01 at C4908 and
    D3913). game.oob builds nothing from them, so combat_tables' `temporary` column stays
    unreachable in play; that ingest, not 24.8, is the natural next slice here. A Temporary
    Facility inherits NEITHER exemption the Major one gets: 22.36 weather-blocks it and 22.37
    bars it in an Enemy ZOC unless it stands in a Major City.
  * 21.6 TOWING. Broken-down and destroyed vehicles reach a Repair Facility by being towed
    there (21.61-21.67, one full sub-rule of chapter 21) -- zero code exists for this
    anywhere in the engine. Without it, a unit can only be repaired at a Facility if it
    happens to BREAK DOWN while already standing on one (a garrison moving locally within
    Alexandria/Cairo/Tobruk) -- see the measurement in the transcription for how often that
    actually happens.
  * 22.4 REPAIRING DESTROYED TANKS. This engine's Unit model has no "destroyed tank" state
    distinct from `broken_down` (no combat result strips a tank to a separately-repairable
    wreck) -- already flagged in data/breakdown_rates.json's own scope note, reconfirmed.
  * 22.6/22.7 THE DESERT TANK DELIVERY ORGANIZATION / GERMAN MOBILE TANK REPAIR SQUAD. No
    OOB counter exists for either; their die-roll modifier (-1, already recorded in
    data/breakdown_rates.json's die_modifiers) is consequently unreachable.
  * 22.34b's same-Op-Stage bombing-threshold neutralization of a non-Major-City Temporary
    Facility -- moot while no Temporary Facility can be built, noted for completeness.
  * 22.33/22.25's "one die per TYPE of tank" is a die per COUNTER in game.engine._repair, and
    that is a PROXY, flagged rather than silently taken. 22.25 rolls "once for the PzII's and
    once for the PzIV Specials" in a hex; this engine carries NO per-counter tank type at play
    time -- data/unit_stats.json's per-model ratings are resolved at BUILD time
    (game.oob._make_unit) and the model NAME is never kept on the counter, and for all but ten
    Italian records it is not transcribed per counter at all but supplied by
    oob.MODEL_DEFAULTS, one default per (nationality, role). Grouping the repair die on that
    default would MERGE the types the book explicitly separates -- every German panzer
    battalion in a hex under one die -- which is a larger error in the opposite direction, and
    reaching for it would mean inventing a per-counter type the order of battle does not
    print. One counter is one battalion of one type, so a die per counter never merges two
    types; it only splits a type that happens to field two battalions in one hex. AC/Recce
    needs no such proxy and does not get one: 22.24 rolls "one die for all the A/C's and Recce
    points in the hex" with no type subdivision at all, so they pool per hex and per
    nationality (22.14, the Axis repairs German separately from Italian) -- as Truck Points
    already did (22.23).
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache

from . import campaign_victory, coords
from .hexmap import Coord
from .state import GameState

_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "breakdown_rates.json"))


@lru_cache(maxsize=1)
def _supply_costs() -> dict:
    """[22.15] VEHICLE REPAIR SUPPLY COSTS CHART -- the chart of record for what a repair
    attempt costs BEFORE it is rolled (data/breakdown_rates.json's
    vehicle_repair_supply_costs_22_15, scan-verified PDF p.102: Field/Bd/Truck,AC,Recce =
    None; Field/Bd/Tank,SPA,TD = 1 Fuel; Facility/Bd/All = 1 Fuel and 1 Stores). READ from the
    data rather than re-typed as a literal beside it: the block was transcribed and, as the
    review of this slice found, nothing in the engine read it."""
    with open(_PATH) as fh:
        return json.load(fh)["vehicle_repair_supply_costs_22_15"]


# [22.35] "For each Truck Point, Gun or Tank TOE Strength Point undergoing repair the Player
# must have present in that hex and expend (before rolling for Repairs) one Store Point and
# one Fuel Point." Unlike Field Repair, EVERY class pays at a Facility -- the chart's single
# `Facility | Bd | All` row.
FACILITY_FUEL_PER_POINT: int = _supply_costs()["facility_bd_all"]["fuel"]
FACILITY_STORES_PER_POINT: int = _supply_costs()["facility_bd_all"]["stores"]
# [22.26] Field Repair's own cost, the chart's `Field | Bd | Tank, SPA, TD` row: one Fuel Point
# per tank TOE Strength Point ATTEMPTED ("He may attempt to repair only those Tank TOE Strength
# Points he has expended Fuel for"). The chart's `Field | Bd | Truck, AC, Recce` row is "None"
# -- 22.23/22.24 repair those free, which is exactly why the Field die is still worth rolling
# on a Major Facility hex whose dumps have run dry (game.engine._repair's fallback).
FIELD_TANK_FUEL_PER_TOE: int = _supply_costs()["field_bd_tank_spa_td"]["fuel"]


def _tripoli_hexes(state: GameState) -> frozenset:
    """[22.31] Tripoli (the Tripoli Box) is off-map (8.81/8.88), so no scenario can print a
    hex for it. Reuses whatever ON-MAP PROXY the scenario already stands in for the harbour
    itself -- the "AX-Tripoli" SupplyUnit rommels_arrival/siege_of_tobruk seed (game.scenario
    Step 5). game.scenario.campaign() seeds no such proxy -- its Axis harbour is Benghazi --
    so the campaign's Tripoli facility is simply absent, exactly as faithful as inventing a
    hex would be unfaithful."""
    return frozenset(s.hex for s in state.supplies if s.id == "AX-Tripoli")


@lru_cache(maxsize=1)
def _static_major_facility_hexes() -> frozenset:
    """The part of [22.31]'s roster that never varies within a process: Alexandria + Cairo
    ("all hexes", campaign_victory's own 64.71 auto_win table -- two Alexandria hexes, five
    Cairo) and Tobruk ("for whoever controls it" -- the facility is side-neutral; the
    ordinary 22.13a enemy-control gate the caller already applies is what decides who may
    use it). Cached: this is a Repair-Phase-frequency call (game.engine._repair, up to twice
    per Operations Stage) re-parsing a small, unchanging JSON file for no reason otherwise."""
    aw = campaign_victory.load_victory_cities()
    hexes = {coords.to_axial(coords.parse(h))
             for h in aw["auto_win"]["alexandria"] + aw["auto_win"]["cairo"]}
    tobruk = next((c["hex"] for c in aw["cities"] if c["name"] == "Tobruk"), None)
    if tobruk is not None:
        hexes.add(coords.to_axial(coords.parse(tobruk)))
    return frozenset(hexes)


def major_facility_hexes(state: GameState) -> frozenset:
    """[22.31] Every hex a Major Repair Facility already stands on -- the cached static
    roster (Alexandria/Cairo/Tobruk) plus Tripoli's on-map proxy where THIS state's
    scenario has one (see _tripoli_hexes; state.supplies varies run to run, so that half
    cannot be cached)."""
    return _static_major_facility_hexes() | _tripoli_hexes(state)


def facility_die_modifier(state: GameState, hx: Coord) -> int:
    """[22.34a] +1/+2 to a Major-City Repair Facility's repair die when the city's own
    Fortification Level stands below its printed baseline. Keyed to the REDUCTION (rule
    prose: 'reduced by one' -> +1, 'reduced by two or three' -> +2), not the Broken Down
    Vehicle Repair Table footnote's absolute shorthand ('at present two' -> +1, 'at present
    one or zero' -> +2), which is only equivalent to the prose for a Level-3 city
    (Alexandria/Cairo) and would wrongly penalise an UNDAMAGED Level-2 city (Tobruk/Bardia/
    Benghazi/Helwan) that has never been bombed. The numbered rule's own prose wins, matching
    game.construction.fort_buildable's precedent for the same chart-vs-prose class of
    conflict -- see the OWNER RULING in scratchpad/port/transcriptions/
    22.3-cw-rear-area-recovery.md section 5 and data/breakdown_rates.json's
    _owner_ruling_2026_07_30. Zero outside a Major City hex, or if the level has never been
    reduced from its own baseline."""
    baseline = state.terrain.fortifications.get(hx, 0)
    if baseline <= 0:
        return 0
    reduction = baseline - state.fort_level(hx)
    if reduction <= 0:
        return 0
    return 1 if reduction == 1 else 2


def facility_repaired_count(result_pct: int, attempted: int) -> int:
    """[22.34]/[22.25] The Facility columns are ALWAYS a percentage of that vehicle type
    repaired -- for trucks and AC/Recce too, unlike Field Repair's flat truck/AC-Recce point
    counts ('the result of the dieroll is the percentage of that type of vehicle that may be
    Repaired', 22.34). `attempted` is the number of points supplies were actually expended for,
    which 22.35 makes the pool undergoing repair ('He may attempt to repair only those points
    he has expended supplies for'), not necessarily the whole broken pool. Fractions round up
    (22.25), except the single-TOE 10% exception ('if only attempting to repair a single TOE
    Strength Point, treat as a 0% result').

    TRANSCRIPTION NOTE (scan p.103, 600dpi, scratchpad/port/22.3-scan/p103_228table.png):
    every OTHER 10% cell on this chart prints the asterisk that ties it to the single-TOE
    exception (Field Tank/SPA/TD rows 2-4, every Temporary row 5-8) EXCEPT the Major
    column's row-8 cell, which prints a bare '10%' with no asterisk. Applied here anyway,
    uniformly, for two reasons: (1) no rule text anywhere explains why this one cell alone
    would behave differently, and (2) it is reachable only via 22.34a's die-8 ceiling (a
    natural 6 PLUS a Major City reduced to Level <=1) -- a narrow enough case that a
    dedicated (column, die) special-case would be disproportionate to what it changes.
    Flagged rather than silently either way."""
    if attempted <= 0:
        return 0
    if attempted == 1 and result_pct == 10:
        return 0
    return min(attempted, math.ceil(result_pct / 100 * attempted))
