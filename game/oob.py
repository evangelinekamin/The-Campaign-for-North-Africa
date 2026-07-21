"""Turn the extracted Rommel's Arrival order of battle into engine units.

Joins data/oob_desert_fox.json (unit identity + side + start hex, from the VASSAL
save) with data/unit_stats.json (role stats, from the Characteristics Charts) and
game.coords (hex label -> global axial). Each combat counter is classified to a
role from its counter identity and organisational group, then given that role's
CPA / close-assault / steps / mobility. Supply dumps become SupplyUnits.

The classification is a small, explicit heuristic over the ~28 on-map pieces; the
close-assault-only stat model is documented in data/unit_stats.json.
"""
from __future__ import annotations

import json
import os
from dataclasses import replace

from . import air, coords, logistics_data, wells
from .events import Side
from .state import AirFacility, Rommel, StepRecord, SupplyUnit, Unit
from .terrain import Mobility, NON_MOT_CLASSES

_DATA = os.path.join(os.path.dirname(__file__), "..", "data")

_COMMODITIES = ("AMMO", "FUEL", "STORES", "WATER")

# A representative real-scale (Regime B) Supply-Unit load = Tobruk's [61.36] built-in
# supply (500 Fuel / 1500 Ammo / 1000 Stores), plus a FLAGGED wells/rail Water proxy
# (52.7/54.3 deferred; 61.36 charts no Tobruk dump water). Used for the Tobruk lifeline
# dump and the rail/ferry per-turn loads (game.scenario). The field dumps are seeded
# separately from the section-60/61 start-line pools (see _place_dumps).
_TOBRUK_BUILTIN = logistics_data.tobruk_builtin_61_36()
DUMP_AMMO = _TOBRUK_BUILTIN["AMMO"]      # 1500 [61.36]
DUMP_FUEL = _TOBRUK_BUILTIN["FUEL"]      # 500  [61.36]
DUMP_STORES = _TOBRUK_BUILTIN["STORES"]  # 1000 [61.36]
DUMP_WATER = 1000                        # FLAGGED wells/rail proxy (52.7/54.3 deferred)

# START-LINE ANONYMOUS field-dump pools, distributed over each side's field dumps by _place_dumps
# (authored even split, clipped to the 54.12 caps). Rule 64.3 keys the pool to WHERE the campaign
# begins: the Rommel-start / Desert Fox scenarios use SECTION 61 (the DEFAULT -- rommels_arrival,
# siege_of_tobruk), while the FULL campaign from September 1940 uses SECTION 60 (CAMPAIGN_DUMP_POOLS,
# passed by game.scenario.campaign). Loading the 61.44 pool into the full campaign handed the Axis
# 9600 Fuel where 60.34 charts 3000 -- the bug T0-2 fixes.
_CW_WATER_PROXY = 1600                                      # FLAGGED Desert Fox wells/rail Water (52.7/54.3)
DESERT_FOX_DUMP_POOLS = {
    Side.AXIS: logistics_data.axis_dump_pool_61_44(),                               # [61.44] AMMO/FUEL/STORES/WATER
    Side.ALLIED: {**logistics_data.cw_dump_pool_61_36(), "WATER": _CW_WATER_PROXY},  # [61.36] + wells/rail proxy
}
CAMPAIGN_DUMP_POOLS = {
    Side.AXIS: logistics_data.axis_dump_pool_60_34(),      # [60.34] AMMO/FUEL/STORES/WATER (400)
    Side.ALLIED: logistics_data.cw_dump_pool_60_44(),      # [60.44] AMMO/FUEL/STORES -- 60.44 charts NO CW dump water
}
_OTHER_CAP = logistics_data.dump_other_terrain_cap()       # [54.12] Other-Terrain ceilings

# --- [36.17] THE AIR-FACILITY SUPPLY ALLOTMENTS (rule 35.14's larder) --------------------------
# The pool each scenario charts for distribution among a side's AIR FACILITIES, keyed by Side and
# dispatched by rule 64.3 exactly as the dump pools and the first-line trucks are: Section 61 for
# the Desert Fox benchmarks, Section 60 for the full campaign. Rule 59.61 -- "ignore all Trucks and
# supplies available at/for Air facilities in the initial set-ups" -- kept these off the board while
# the Air Game was abstract; the full Air Game is played from Phase 5.1, so they are in force.
DESERT_FOX_AIR_POOLS = {
    Side.AXIS:   logistics_data.axis_air_pool_61_44(),     # [61.44] 50 Ammo / 50 Fuel
    Side.ALLIED: logistics_data.cw_air_pool_61_36(),       # [61.36] 250 Ammo / 180 Fuel / 50 Stores
}
CAMPAIGN_AIR_POOLS = {
    Side.AXIS:   logistics_data.axis_air_pool_60_34(),     # [60.34] 1200/850/100/100
    Side.ALLIED: logistics_data.cw_air_pool_60_44(),       # [60.44] 200 Ammo / 250 Fuel / 50 Stores
}

# --- [60.31]/[60.41] & [61.43]/[61.31] FIRST-LINE TRUCK ALLOTMENTS (rule 53.11) ----------------
# The per-side first-line Truck-Point totals by 54.2 class, transcribed cell-by-cell off the 1979
# scan (scratchpad/port/phase4-first-line-trucks.md: [60.31]/[60.41] PDF p.78, [61.43] p.81,
# [61.31] p.80). Keyed by Side exactly like the dump pools, and dispatched the same way by rule
# 64.3: the FULL campaign inherits Section 60, the Desert Fox benchmarks Section 61.
#
# 59.42 lists the allotment BY HEX and makes its division among that hex's units a FREE player
# choice; the design (sec 3.2) makes only the per-side Sigma load-bearing. German first-line trucks
# arrive attached via the Reinforcement Schedule ([4.43b]/[61.43], design sec 4.3) and are DEFERRED,
# so the Axis allotment below is the ITALIAN first line and _seed_first_line places it on Italian
# ('IT ') units only. See _seed_first_line for how the per-hex rows collapse to the per-side total.
DESERT_FOX_FIRST_LINE = {
    Side.AXIS:   {"light": 45, "medium": 220, "heavy": 50},   # [61.43] Italian first line -- 315 TP
    Side.ALLIED: {"light": 15, "medium": 113, "heavy":  5},   # [61.31] Commonwealth -- 133 TP
}
CAMPAIGN_FIRST_LINE = {
    Side.AXIS:   {"light": 55, "medium": 260, "heavy": 45},   # [60.31] Italian 10th Army -- 360 TP
    Side.ALLIED: {"light": 30, "medium": 125, "heavy": 22},   # [60.41] Western Desert Force -- 177 TP
}

# [49.13]/[4.47-4.49] per-model Fuel Consumption Rate, keyed by model name.
_FUEL_RATE_BY_MODEL = logistics_data.fuel_rate_by_model()


def _load(name: str) -> dict | list:
    with open(os.path.normpath(os.path.join(_DATA, name))) as f:
        return json.load(f)


def _nationality(side: str) -> str:
    return "GE" if side == "AXIS" else "CW"


def _nat(rec: dict) -> str:
    """Nationality for the stat lookup. The record's own field wins (Desert-Fox
    reinforcements state it). Otherwise an 'IT '-prefixed counter/group is Italian -- the
    raw campaign extraction carries no nationality -- and the rest fall back to side
    (Axis=German, Commonwealth=CW). Desert-Fox on-map pieces carry no 'IT ' prefix, so
    they resolve exactly as before (byte-identical)."""
    if rec.get("nationality"):
        return rec["nationality"]
    if rec.get("counter", "").startswith("IT ") or rec.get("group", "").startswith("IT "):
        return "IT"
    return _nationality(rec["side"])


# Basic Morale by formation (rule 17.1, from the [4.44b]/[4.44B] OA sheets; see
# cna-unit-stats-source). _morale_for returns the FIRST substring match, so order is
# specificity: a more-specific key must precede a shorter one it contains (e.g. "Libyan
# Tank Command" before "Libyan"; the garrison/"Giarabub" keys before the generic "Oasis").
FORMATION_MORALE = (
    # German & Commonwealth (Desert Fox / siege) -- matched first, unchanged.
    ("5th Light", 2), ("15th Panzer", 2), ("90th", 2), ("164th", 1), ("Ariete", 1),
    ("2nd Armoured", 2), ("9th Australian", 1), ("Indian", 1),
    # Italian garrisons are -3 (Tobruk/Benghazi/Bardia/Derna/minor) EXCEPT the Giarabub oasis
    # fortress, which the [4.44b] sheet rates 0 (it famously held out for months). The Giarabub
    # keys must precede the generic "Garrison" (-3), which precedes "Oasis" (rule 60.31).
    ("Libyan Tank Command", 0),                                       # Babini gruppo (before "Libyan")
    ("Giariabub", 0), ("Giarabub", 0), ("Garrison", -3), ("Oasis", 0),
    # Italian semi-motorized infantry divisions (-1) with their 0/+1 exceptions. Cirene,
    # Marmarica and Sirte have no [4.44b] sheet (melted units) -- -1 is INFERRED from the
    # Catanzaro-class semi-mot pattern, the only 1940 sheet analogue.
    ("Pavia", -1), ("Bologna", -1), ("Brescia", -1), ("Savona", -1),
    ("Trento", 0), ("Sabratha", -1), ("Pistoia", -1), ("Trieste", 0),
    ("Catanzaro", -1), ("Cirene", -1), ("Marmar", -1), ("Sirte", -1),
    ("Littorio", 0), ("Folgore", 1), ("Giovani Fascisti", -3), ("GGFF", -3),
    # Italian colonial (Libyan, -2), Maletti (-2), Blackshirt (CCNN). The 1st/2nd/4th CCNN
    # divisions are morale 0 ([4.44b]); the 3rd CCNN (-2) would need its own key ahead of
    # this one if it enters (rule 60.31 Tripoli reserve -- C2-3 reinforcements).
    ("Libyan", -2), ("Maletti", -2), ("CCNN", 0),
)


def _morale_for(group: str, counter: str) -> int:
    if "Rommel" in counter or "DAK" in counter:
        return 1                                      # DAK HQ
    for key, m in FORMATION_MORALE:
        if key in group:
            return m
    return 0                                          # unknown formation -> neutral


def classify(counter: str, group: str) -> "str | None":
    """Best-effort role for an OOB counter that carries no explicit `role`.

    DATA-DRIVEN FIRST: every shipped OOB record names its own `role` (build() reads
    `rec["role"]` and only falls back to this function), so this is a safety net, not the
    source of truth. It keys off the COUNTER's own type tokens -- the regiment/weapon
    identity printed on the counter -- and NEVER off the organisational GROUP. A group name
    describes the FORMATION, not the counter: "7th Armoured Division" contains that division's
    Royal Horse Artillery, its motor battalion and its anti-tank regiment, and the "Unassigned
    Anti-Tank Regiments" group contains the substring "Tank" -- so a group-substring guess read
    five Commonwealth artillery/motor/anti-tank battalions as phantom tanks (the T0-6 bug). An
    unrecognised counter defaults to infantry.

    Two categories the old classifier lost are carried now: Anti-Aircraft-Type units (rule
    3.23) map to the `aa` role (the Commonwealth had no AA arm), and Squadron Ground Support
    Units (rules 3.21 / 35.0) map to the `sgsu` role instead of being dropped. The AIR
    FACILITIES that used to share that role -- Air Landing Strips, flying-boat Alighting areas --
    are not units at all: Phase 5.1 made them game.state.AirFacility installations, carried in
    their own OOB records (kind "air_facility", see air_facilities below), so a counter reaching
    this function should never be one of them -- and the guard below is what makes "should never"
    safe rather than hopeful.
    """
    c = counter
    # Squadron Ground Support Units (rules 3.21 / 35.0): non-combat squadron bases, no combat
    # values (35.12). Their upkeep is 35.14's, drawn from their facility's 36.17 dump.
    if "SGSU" in c:
        return "sgsu"
    # [36.0] AIR FACILITIES ARE NOT UNITS -- and an air-facility counter that reaches this function
    # is a DATA fault, not a piece to muster. They are read from their own kind ("air_facility",
    # air_facilities below), so build() never routes one here; but the tail of this classifier is a
    # sensible-default-to-infantry, and a re-extraction that emitted a landing strip under kind
    # "unit" would fall all the way through it and put AN AIR LANDING STRIP ON THE MAP AS AN
    # INFANTRY COMBAT UNIT with a TOE, a close-assault value and a stacking cost. Dropped instead:
    # None is build()'s "this counter is not a unit", the same answer it gives a supply-dump record.
    if "Airstrip" in group or "Alighting" in group or "Air Strip" in c or "Airboat" in c:
        return None
    # Anti-Aircraft-Type (rule 3.23); the AA/Flak symbol on the counter -> Pure Flak (46.17).
    if "LAA" in c or "HAA" in c or "(AA)" in c:
        return "aa"

    if c.startswith("IT "):                          # 1940 Italian 10th Army (rule 60.31 / [4.44b])
        if "(MG)" in c or "(MMG)" in c:
            return "mg"                              # machinegun battalions / companies
        if "(ART)" in c:
            return "artillery"
        if "Sno" in c:
            return "infantry"                        # Sahariano camel battalions (before Maletti)
        if "Maletti" in c:
            return "artillery"                       # 1st / 2nd Maletti artillery battalions
        if "LTC" in c:
            return "tank"                            # Libyan Tank Command tankettes (M11/39 + CV33)
        return "infantry"                            # colonial / Blackshirt / garrison / marine line

    if "Rommel" in c or "DAK" in c or "SPt" in c or c.endswith(" Le - none"):
        return "hq"                                  # HQs (counter is authoritative)
    if "RNF" in c or "(MG)" in c or "(MMG)" in c:
        return "mg"                                  # Royal Northumberland Fusiliers = MG bn
    if "(ATG)" in c:
        return "antitank"
    if "RHA" in c or "(ART)" in c or " Med " in c or " Fld " in c or "ArKo" in c or "155" in c:
        return "artillery"                           # Horse/Field/Medium regiments, ArKo, 155mm
    if "OAS" in c or "Oasis" in c:
        return "oasis"
    if "KRRC" in c or "FMtMr" in c:
        return "motor_infantry"                      # King's Royal Rifle Corps = motor bn
    if "RTR" in c or "LTC" in c:
        return "tank"                                # Royal Tank Regiment / Libyan Tank Command
    return "infantry"                                # sensible default


def build(oob_file: str = "oob_desert_fox.json", sections: str | None = None,
          reinforcements_file: str | None = "reinforcements_desert_fox.json",
          extra_file: str | None = None, dump_pools: dict | None = None,
          first_line: dict | None = None,
          ) -> tuple[list[Unit], list[SupplyUnit]]:
    """Build engine units/supplies from an OOB file. If `sections` is given (e.g.
    "ABC"), only pieces whose hex is in those map sections are kept (rear units on
    unloaded sections are dropped). `reinforcements_file` (rule 20) adds off-map
    units that enter on their arrival_turn at an axial entry hex. `extra_file` adds
    further on-map pieces from a second OOB file (same schema), so a hand-authored
    campaign gap-fill can layer onto a raw VASSAL extraction without editing it; an
    on-map record may carry an explicit `role` to override classify(). `dump_pools`
    (Side -> commodity->points) is the 64.3 start-line field-dump pool; it defaults to
    the SECTION-61 Desert Fox pools, and game.scenario.campaign passes SECTION 60.
    `first_line` (Side -> class->Truck Points) is the 53.11 first-line-truck allotment seeded
    onto the units (Option B); it likewise defaults to Section 61 and the campaign passes
    Section 60 (see _seed_first_line)."""
    stats = _load("unit_stats.json")
    units: list[Unit] = []
    dumps_meta: list[tuple[str, Side, tuple]] = []   # (uid, side, hex) placed after the loop
    seen: dict[str, int] = {}

    for rec in (_load(oob_file) + (_load(extra_file) if extra_file else [])):
        if rec.get("kind") not in ("unit", "dump"):
            continue                                 # provenance/comment records carry no hex
        hexlbl = rec["hex"]
        if sections is not None and hexlbl[0] not in sections:
            continue
        side = Side.AXIS if rec["side"] == "AXIS" else Side.ALLIED
        ax = coords.to_axial(coords.parse(hexlbl))

        if rec["kind"] == "dump":
            uid = _uid(seen, f"{rec['side'][:2]}-Dump")   # uid order preserved
            dumps_meta.append((uid, side, ax))
            continue
        if rec["kind"] != "unit":
            continue                                 # features are not engine units
        role = rec.get("role") or classify(rec["counter"], rec["group"])
        if role is not None:
            units.append(_make_unit(rec, side, ax, role, stats, seen, 0))

    supplies: list[SupplyUnit] = _place_dumps(dumps_meta, dump_pools or DESERT_FOX_DUMP_POOLS)

    for rec in (_load(reinforcements_file)["reinforcements"] if reinforcements_file else []):
        side = Side.AXIS if rec["side"] == "AXIS" else Side.ALLIED
        role = rec.get("role") or classify(rec["counter"], rec["group"])
        if role is not None:
            units.append(_make_unit(rec, side, tuple(rec["hex"]), role, stats, seen,
                                    rec["arrival_turn"]))
    units = _seed_first_line(units, first_line or DESERT_FOX_FIRST_LINE)   # 53.11 / 64.3
    units = _seed_fuel_tanks(units)                                        # 49.14 fuel tanks
    units = _seed_ammo_loads(units)                                        # 50.0 ammo basic loads
    return units, supplies


def air_facilities(oob_file: str = "oob_desert_fox.json", sections: str | None = None,
                   extra_file: str | None = None) -> list[AirFacility]:
    """[36.0] Lift the OOB's air-facility records onto the map as AirFacility installations.

    An air facility is NOT a unit and this is the seam that says so. It has no TOE, no supply
    ledger, no CPA and no combat values -- it is an installation the Air Game flies from, exactly
    as a Port is one the sea game lands at -- so it is diverted out of build()'s units[] into its
    own tuple, the same way rommel_entity() diverts the leader counter. (It used to be built as an
    inert `air`-role Unit with cpa 0, which gave the map a counter that could be stacked with,
    traced through and starved by the land logistics beat, and still carried no capacity level.)

    Each record names its `facility` kind; the Capacity Level opens at that kind's charted maximum
    (36.12 six / 36.2 one / 36.3 three / 36.4 one) because a facility in a scenario's initial set-up
    is an intact one -- 36.14's reductions are what BOMBING does to it. `sections` and `extra_file`
    filter exactly as build()'s do.

    ⚠ FLAGGED, AND IT IS THE NEXT DATA JOB -- SAY THE SIZE OF IT PLAINLY. This reads the VASSAL
    extraction, and the extraction is NOT the book's map. [60.5] (docs/rules/60, lines 288-362; scan
    p.79) charts the campaign's real set -- 20 Airfields, 31 Air Landing Strips, 3 Flying Boat Basins
    and 1 Alighting Area, each with its printed hex -- and the extraction ships 10 Air Landing Strips
    and 1 Alighting Area, NO AIRFIELD AT ALL. Compared hex by hex against the chart:

        C4021 (Sollum) is the ONLY ONE OF THE ELEVEN that stands where [60.5] prints it.
        B4922 / C1015 / C4322 / C4420 / D3904 are one row off the charted Mechili B4921, Giarabub
          C1014, Bardia C4321, Menastir C4419 and the blank strip D3903;
        B6024, the Alighting Area, is one hex off the only one [60.5] charts, Derna B5925;
        C4317, C4908, C4122 and C4230 DO NOT APPEAR IN [60.5] AT ALL.

    So: ten of the eleven facilities on the campaign map stand on hexes the book does not print, and
    everything Phase 5.1 hangs on them -- 60 Axis and 55 Commonwealth charted Truck Points, the whole
    [60.34]/[60.44] air allotment, and every seeded SGSU -- hangs there with them. Nothing here is
    load-bearing for the FAITHFULNESS of rules 35 and 36 (the capacity levels, the 36.17 dump and the
    35.14 upkeep are the book's), but the MAP is a placeholder and must not be read as the book's.

    Transcribing [60.5] needs one decision this extraction makes for us: the chart assigns ownership
    by GEOGRAPHY -- "All facilities in Egypt belong to the Commonwealth; all those in Libya belong to
    the Italians at the start of the game" -- and the Libya/Egypt frontier is in no data file we hold.
    It is not a map-section line either: Sollum C4021 (Egypt) and Ft. Capuzzo C4020 (Libya) are
    adjacent hexes of map C, and so are Bardia C4321 (Libya) and Sidi Barrani C4131 (Egypt)."""
    out: list[AirFacility] = []
    seen: dict[str, int] = {}
    for rec in (_load(oob_file) + (_load(extra_file) if extra_file else [])):
        if rec.get("kind") != "air_facility":
            continue
        hexlbl = rec["hex"]
        if sections is not None and hexlbl[0] not in sections:
            continue
        kind = rec["facility"]
        level = air.max_capacity(kind)
        out.append(AirFacility(_uid(seen, rec["counter"]),
                               Side.AXIS if rec["side"] == "AXIS" else Side.ALLIED,
                               coords.to_axial(coords.parse(hexlbl)),
                               kind=kind, level=level, max_level=level))
    return out


def air_dumps(facilities: list[AirFacility], pools: dict, placed=()) -> list[SupplyUnit]:
    """[36.17] Give each side's air facilities the supply dump the rule says they ARE: "an airfield
    is a supply dump for supplies to be used by the SGSU's on that airfield. Fuel, ammunition,
    stores, etc., may be stored at an airfield AS IF IT WERE A DUMP."

    `pools` is the scenario's charted air-supply allotment keyed by Side ([60.34] 1200 Ammo / 850
    Fuel / 100 Stores / 100 Water for the campaign Axis, [60.44] 200/250/50 for the Commonwealth;
    [61.44] 50/50 and [61.36] 250/180/50 for the Desert Fox). Every one of those charts grants FREE
    PLACEMENT -- "freely distributed among his airfields", "distribute amongst Air Facilities as
    desired" -- so the even split below (remainder to the earliest facility by id, clipped to the
    54.12 Other-Terrain ceilings) is OUR ASSIGNMENT of that free choice, the identical convention
    _place_dumps uses for the field dumps.

    These dumps carry air_dump=True, which is the whole point: game.supply hides them from the land
    army's trace and in-hex draw and shows them only to an SGSU's 35.14 upkeep. Without the flag the
    Axis's 850 charted air Fuel Points would simply be 850 more Fuel Points for the Panzerarmee.

    [59.52] IS WHY `placed` EXISTS, AND IT IS THE ONE CONSTRAINT THE FREE CHOICE HAS. "Air facilities
    automatically possess a supply dump. IF A PLAYER PLACES SUPPLIES AVAILABLE AT A SUPPLY DUMP IN THE
    SAME LOCATION AS THOSE AVAILABLE AT AN AIR FACILITY, THE TOTALS ARE COMBINED AND IT BECOMES ONE
    DUMP (see Case 36.17)." Two Supply Units on one hex is exactly what the engine's one-dump-per-hex
    law forbids (engine._dump_on: our dump IS that hex's 54.12 Supply Dump Capacity, not a counter),
    so the placement must not create the case -- and a quartermaster would not create it anyway. The
    campaign walks straight into it: the Commonwealth's charted Sollum Field Supply Depot stands on
    the Sollum landing strip's hex, in the path of the September-1940 Italian advance, so an even
    split would stack the RAF's larder on a depot that is overrun on Game-Turn 1. `placed` is the
    dumps already on the board; a facility sharing a hex with its OWN side's real dump is skipped, and
    its share goes to that side's other facilities (the squadron there is not starved by the skip --
    36.17 restricts LAND units from an airfield's pile, it does not restrict an SGSU from an ordinary
    dump under its feet, so the depot it stands on feeds it: supply.colocated_dumps). If skipping
    would leave a side no facility at all, nothing is skipped -- charted supply is never dropped to
    honour a placement convention.

    ⚠ A SIDE WITH NO FACILITY GETS NO DUMP, AND ITS CHARTED POOL IS DROPPED. The split is over the
    facilities passed in, so a pool keyed to a side that holds none simply does not land -- and the
    Desert Fox benchmarks are exactly that case: their extraction carries only the two Commonwealth
    landing strips (B4006, C4808), so [61.44]'s Axis 50 Fuel / 50 Ammo air allotment is not on the
    board in either of them. It is the supply twin of the flagged truck case (_rommel_trucks): 61.42
    gives the Axis a free "one airfield and one air landing strip in any hex west of El Agheila" that
    we do not model, so there is no Axis facility hex on maps A-C for the chart to name. Stated here
    rather than silent, because charted supply that does not appear is a fact about the scenario."""
    taken = {(s.side, s.hex) for s in placed
             if not (s.is_dummy or s.air_dump or wells.is_water_source(s))}
    out: list[SupplyUnit] = []
    by_side: dict[Side, list[AirFacility]] = {}
    for f in sorted(facilities, key=lambda f: f.id):
        by_side.setdefault(f.side, []).append(f)
    for side, all_of_them in by_side.items():
        pool = pools.get(side, {})
        lst = [f for f in all_of_them if (side, f.hex) not in taken] or all_of_them   # 59.52
        n = len(lst)
        for i, f in enumerate(lst):
            amt = {c: min(_share(pool.get(c, 0), n, i), _OTHER_CAP[c]) for c in _COMMODITIES}
            out.append(SupplyUnit(f"{f.id}-Supply", side, f.hex, ammo=amt["AMMO"],
                                  fuel=amt["FUEL"], stores=amt["STORES"], water=amt["WATER"],
                                  air_dump=True))
    return out


def _sgsu_available() -> dict:
    """[60.32]/[60.42] SGSU AVAILABILITY for the full campaign, off the charts: "Italian SGSU
    Available: 39" (the last line of [60.32] Italian Air Strengths -- NOT [60.31], which is the
    Italian Initial Deployment) and "SGSU Available: 14" ([60.42], the Commonwealth North African Air
    Force). 60.42 states the placement rule for both: "the following planes, SGSU's and pilots may be
    placed at any... air facility, WITHIN THE CAPACITY OF THAT FACILITY." Read from data with every
    other charted magnitude, not carried as a literal."""
    return {Side.AXIS: logistics_data.italian_sgsu_available_60_32(),
            Side.ALLIED: logistics_data.cw_sgsu_available_60_42()}


CAMPAIGN_SGSU_AVAILABLE = _sgsu_available()


def seed_sgsus(facilities: list[AirFacility], available: dict) -> list[Unit]:
    """[35.11]/[60.32]/[60.42] Base each side's Squadron Ground Support Units at its air facilities.

    35.11: "Each SGSU counter is placed on the game-map to indicate where that squadron is located.
    They are usually placed at air facilities." 60.42 gives the constraint that decides HOW MANY go
    where: they "may be placed at any... air facility, WITHIN THE CAPACITY OF THAT FACILITY" -- and
    36.12/36.2 set that capacity (an airfield six squadrons, a landing strip one). So a facility
    takes SGSUs up to its Capacity Level, in facility-id order, until the side's charted pool runs
    out. Free placement inside a stated restriction: OUR ASSIGNMENT of it, the identical convention
    the [60.31] first-line trucks and the [60.34] dump pools are placed under.

    ⚠ FLAGGED, AND IT IS THE SAME FLAG air_facilities CARRIES. The extraction gives the campaign 11
    landing strips of capacity 1 and no airfield, so 11 of the charted 53 SGSUs find a base and the
    rest have nowhere to stand. Transcribe [60.5]'s twenty Airfields (six squadrons each) and the
    number rises to the charts'. The pool is a CEILING here, never a target -- we place what the map
    can hold and no more, which is exactly what 60.42's sentence says to do.

    Used by the full campaign, whose order of battle ships no SGSU counter at all. The Desert Fox
    scenarios are NOT seeded this way: their extraction ships real SGSU counters at their own
    (drifted) hexes, and inventing more beside them would double the squadron bases the scenario
    charts.

    ⚠⚠ OWNER RULING NEEDED -- EVERY AXIS SGSU HERE IS ITALIAN, AND SINCE PHASE 5.3 THAT DECIDES A
    RULE. The nationality below is the label of the pool the counter came out of: the Axis pool is
    [60.32]'s "Italian SGSU Available: 39" and nothing else, because NO GERMAN SGSU AVAILABILITY IS
    TRANSCRIBED FOR THE CAMPAIGN AT ALL (grep SGSU over data/reinforcements_campaign.json and
    data/oob_campaign_extra.json returns nothing). [60.32] is Scenario Group One -- the Italians, 15
    Sept 1940 to Feb 1941 -- so the campaign runs the whole 1941-42 war on the September-1940
    Italian ground crews. The book DOES chart German SGSUs for exactly that period, but only inside
    the later SCENARIO groups (docs/rules/62 line 311 "The Axis Player receives 33 German SGSU's";
    docs/rules/63 lines 289/313, 21 and 27), while [61] line 162 prints no count at all ("German
    SGSU's are available as per the Air Game rules"). There is therefore no campaign arrival
    schedule to transcribe, and writing one would be inventing an order of battle.

    IT IS NOT COSMETIC ANY MORE. Before Phase 5.3 `Unit.nationality` was read by nothing; now
    engine._air_maintenance reads it for [38.37]'s serviceability modifier, so this literal is what
    refits the Deutsches Afrikakorps's Staffeln at the ITALIAN +2 for the entire war, where a German
    SGSU would take +1 -- worth about a sixth of the Axis air force (realised refit 48.6% against
    ~56.7%). See game.air.refit_drm, which carries the same flag from the other end. The ruling:
    transcribe a German SGSU availability for the campaign, or state that the Axis refit modifier is
    uniformly +2 because this order of battle contains no German SGSU counter."""
    stats = _load("unit_stats.json")
    seen: dict[str, int] = {}
    left = dict(available)
    out: list[Unit] = []
    for f in sorted(facilities, key=lambda f: f.id):
        nat = "IT" if f.side == Side.AXIS else "CW"
        # [36.12] "There may never be more than SIX SGSU's in a given airfield hex" -- the STACKING
        # ceiling, a different number from the Capacity Level (36.14 lets six stand at a battered
        # field, only `level` of them functioning). It binds nothing today (no charted facility has a
        # capacity above six) and it is the law all the same, so the placement asks for both.
        for _ in range(min(f.level, air.SGSU_HEX_LIMIT)):
            if left.get(f.side, 0) <= 0:
                break
            left[f.side] -= 1
            rec = {"counter": f"{nat} SGSU", "group": f"{nat} SGSU", "side": f.side.value,
                   "nationality": nat, "morale": 0}
            out.append(_make_unit(rec, f.side, f.hex, air.SGSU_ROLE, stats, seen, 0))
    # The same two per-unit pools build() seeds, for the same conservation reason: every unit sits in
    # state.units from t0, so its organic supply belongs in the initial base (scenario._initial_supply).
    out = _seed_fuel_tanks(out)                        # 49.14 (an SGSU is a vehicle, 35.12)
    return _seed_ammo_loads(out)                       # 50.0 -> 0: an SGSU has no combat function


def rommel_entity(oob_file: str = "oob_desert_fox.json",
                  sections: str | None = None) -> Rommel | None:
    """Divert the General Rommel leader counter (rule 31) OUT of units[] into a
    conservation-invisible entity (game.state.Rommel). The extracted OOB merges the leader
    and his headquarters into one 'GE Rommel - DAK' counter; build() still materialises that
    counter as the is_combat=False DAK-HQ Unit (morale 1, unchanged), and this lifts a SECOND,
    parallel reading of it -- Rommel himself -- onto the board as the entity. Returns the
    entity at the counter's start hex, or None if this OOB fields no Rommel (so every non-
    Rommel scenario stays byte-identical). `sections` filters to a loaded map area, exactly
    like build()."""
    for rec in _load(oob_file):
        if rec.get("kind") != "unit":
            continue
        hexlbl = rec["hex"]
        if sections is not None and hexlbl[0] not in sections:
            continue
        if "Rommel" in rec["counter"]:
            return Rommel(hex=coords.to_axial(coords.parse(hexlbl)))
    return None


def _share(total: int, n: int, i: int) -> int:
    """Deterministic even split of `total` over `n` slots; the first `total % n`
    slots carry the extra point so the pool is conserved exactly."""
    return total // n + (1 if i < total % n else 0)


def _place_dumps(dumps_meta: list[tuple[str, Side, tuple]], pools: dict) -> list[SupplyUnit]:
    """Authored, deterministic placement of each side's start-line field-dump pool (`pools`,
    keyed by Side -- SECTION 61 for the Desert Fox, SECTION 60 for the full campaign, per 64.3)
    over its dump hexes: an even split (remainder to the earliest dumps) clipped to the 54.12
    Other-Terrain ceilings. Real-scale (Regime B) start-line reservoir -- the fuel the 49.13
    x-strength demand draws on. The section-60/61 charts constrain WHERE the anonymous dumps go
    (Axis: map-C Libya, clear of Commonwealth units; CW: Egypt on map C/D), not how the pool
    splits; the binding ceiling here is 54.12, which every share clears."""
    by_side: dict[Side, list[tuple[str, tuple]]] = {}
    for uid, side, ax in dumps_meta:
        by_side.setdefault(side, []).append((uid, ax))
    out: list[SupplyUnit] = []
    for side, lst in by_side.items():
        pool = pools[side]
        n = len(lst)
        for i, (uid, ax) in enumerate(lst):
            amt = {c: min(_share(pool.get(c, 0), n, i), _OTHER_CAP[c]) for c in _COMMODITIES}
            out.append(SupplyUnit(uid, side, ax, ammo=amt["AMMO"], fuel=amt["FUEL"],
                                  stores=amt["STORES"], water=amt["WATER"]))
    return out


def _seed_first_line(units: list[Unit], first_line: dict) -> list[Unit]:
    """Seed each side's transcribed first-line-truck allotment (rule 53.11 / 59.42) onto its units
    as the Option-B fl_* carrying-ceiling fields (game.state.Unit).

    59.42 lists first-line trucks BY HEX in the initial deployment, but the campaign OOB is a VASSAL
    extraction whose Game-Turn-1 positions have DRIFTED from the [60.31]/[60.41] setup hexes -- and
    several rulebook setup units (the 2nd New Zealand Division, 11th Hussars, 1 RTR, the French Motor
    Marines) are modelled here as later rule-20 reinforcements, not as GT1 on-map pieces -- so a
    faithful per-hex placement is not reconstructible against this order of battle. 59.42 makes the
    division among a side's units a FREE player choice and the design (sec 3.2) makes only the
    per-side Sigma load-bearing, so this is OUR ASSIGNMENT of that free choice, exactly as the
    [60.33]/[60.43] second/third-line truck parks are placed: an even split (_share, remainder to the
    earliest units) across the side's GT1 on-map FIELD combat units. Static garrisons (is_garrison_
    home, 9.16a) are left with NO organic transport, faithful to the scan ("Garrisons ... start with
    no organic transport"). The Axis line goes to Italian ('IT ') units only -- German first-line is
    the deferred [4.43b] Reinforcement-Schedule attachment. The per-side Sigma is exact by
    construction and asserted below (design S0's data lint)."""
    seeded = {u.id: u for u in units}
    for side, pool in first_line.items():
        elig = [u for u in units if u.side == side and u.arrival_turn == 0
                and u.is_combat and not u.is_garrison_home
                and (side is not Side.AXIS or u.formation.startswith("IT "))]
        n = len(elig)
        if not n:
            continue
        for i, u in enumerate(elig):
            seeded[u.id] = replace(seeded[u.id],
                                   fl_light=_share(pool.get("light", 0), n, i),
                                   fl_medium=_share(pool.get("medium", 0), n, i),
                                   fl_heavy=_share(pool.get("heavy", 0), n, i))
    out = [seeded[u.id] for u in units]
    for side, pool in first_line.items():
        got = sum(u.fl_light + u.fl_medium + u.fl_heavy for u in out if u.side == side)
        want = sum(pool.get(c, 0) for c in ("light", "medium", "heavy"))
        if got != want:
            raise ValueError(
                f"first-line seed for {side.name}: seeded {got} Truck Points, expected {want}")
    return out


def _seed_fuel_tanks(units: list[Unit]) -> list[Unit]:
    """[49.14] Fill every unit's Fuel Capacity tank (game.state.Unit.fuel = supply.fuel_capacity(u)):
    the fuel its own vehicles carry, "exactly sufficient to allow all its CPA to be expended on
    movement" (49.14 Note). Non-motorized units (49.12, fuel_rate 0) get a 0 tank they never read.
    Applied to ALL units -- the GT1 muster AND rule-20 reinforcements -- because every unit sits in
    state.units from t0 (on_map gates it live by arrival_turn), so a dormant reinforcement's full
    tank is counted in the t0 conservation base (scenario._initial_supply / invariants) and its
    arrival mints no fuel. Parallel-run (design S1): the tank is seeded but NOT yet drained -- no
    consumer reads Unit.fuel until the fuel switch (S5) -- so the event log is byte-identical and
    only initial_supply rises."""
    from . import supply                                # lazy: supply is a heavier module
    return [replace(u, fuel=supply.fuel_capacity(u)) for u in units]


def _seed_ammo_loads(units: list[Unit]) -> list[Unit]:
    """[50.0] Fill every unit's intrinsic 'fire once' ammunition basic load (game.state.Unit.ammo =
    supply.ammo_capacity(u)): "Each TOE Strength Point may carry (i.e., transport by itself without
    trucks) only enough ammo to fire once" (rule 50.0 GENERAL RULE). The ammo dual of _seed_fuel_tanks
    -- a unit deploys combat-ready, able to fire its most-demanding function once from organic ammo
    before it must draw on a co-located dump (49.16). Non-combat units (no barrage/anti-armor/assault
    strength) get a 0 load they never read. Applied to ALL units -- the GT1 muster AND rule-20
    reinforcements -- because every unit sits in state.units from t0, so its load is counted in the t0
    conservation base (scenario._initial_supply sums unit pools) and its arrival mints no ammo.
    Parallel-run (design S6): the load is seeded but NOT yet drained -- no consumer reads Unit.ammo
    until the ammo switch (engine._charge_ammo -> in_hex_draw) -- so the event log is byte-identical
    and only initial_supply rises. First-line trucks (fl_*) stay dormant here exactly as they do for
    fuel; truck-borne ammo headroom is a separate later slice."""
    from . import supply                                # lazy: supply is a heavier module
    return [replace(u, ammo=supply.ammo_capacity(u)) for u in units]


def _fuel_role_default(mobility: Mobility) -> int:
    """49.12/49.13 fallback Fuel Consumption Rate for a unit the per-model chart does
    not name: gun-class / anti-tank / HQ-with-TOE and truck-borne infantry / recce burn
    at rate 1 (the 54.2 truck Fuel Consumption Factor); foot / camel / motorcycle burn
    nothing (49.12). SP guns would be 2 (GE) / 3 (CW), but this OOB fields no SP role."""
    if mobility in NON_MOT_CLASSES or mobility == Mobility.MOTORCYCLE:
        return 0
    return 1


# Default weapon model per (nationality, role) for units that don't name one, so
# the role-level combat ratings resolve to a concrete period model (1941). A unit
# record may override with its own "model" (e.g. Matildas vs cruisers).
MODEL_DEFAULTS = {
    ("GE", "tank"): "pz3h", ("GE", "antitank"): "pak38", ("GE", "artillery"): "lefh18",
    ("CW", "tank"): "a13", ("CW", "artillery"): "25pdr", ("CW", "antitank"): "2pdr",
    ("IT", "tank"): "m13",
}


def _make_unit(rec: dict, side: Side, ax, role: str, stats: dict, seen: dict,
               arrival_turn: int) -> Unit:
    nat = _nat(rec)    # explicit field, else 'IT ' prefix, else side (see _nat)
    s = stats[nat][role]
    model_name = rec.get("model") or MODEL_DEFAULTS.get((nat, role))
    model = stats.get("models", {}).get(model_name, {})
    mob = Mobility[s["mobility"]]
    # 49.13 per-model Fuel Consumption Rate ([4.47-4.49]); the role default (49.12)
    # covers guns/AT/HQ/truck-borne/recce and zeroes foot/camel/motorcycle.
    fuel_rate = _FUEL_RATE_BY_MODEL.get(model_name, _fuel_role_default(mob))

    def rating(key: str) -> int:                     # model overrides role, else 0
        return model.get(key, s.get(key, 0))
    return Unit(
        _uid(seen, rec["counter"]), side, ax,
        (StepRecord(role, s["steps"]),),
        mobility=mob,
        cpa=s["cpa"], stacking_points=s.get("sp", 1),       # 1=battalion (rule 9.4)
        oca=model.get("oca", s["oca"]), dca=model.get("dca", s["dca"]),
        barrage=rating("barrage"), anti_armor=rating("anti_armor"),
        armor_protection=rating("armor_protection"), vulnerability=rating("vulnerability"),
        is_tank=model.get("is_tank", s.get("is_tank", False)),
        # An authored record may state its Basic Morale directly (reinforcements set it from
        # the OA charts, robust to formation-name spelling); else derive it from the group.
        morale=rec["morale"] if "morale" in rec else _morale_for(rec["group"], rec["counter"]),
        is_combat=s.get("is_combat", True),
        # Rule 46.17 / 9.16b: a Pure Flak unit (only AA points) ignores the stacking limit in
        # Major Cities. Set from the `aa` role stat; every other role leaves it False.
        is_pure_aa=s.get("is_pure_aa", False),
        # [23.0]/[24.61] Engineer capability and what it may be used FOR: 'RAIL' for the two New
        # Zealand Railroad Construction companies (the only units that may build railroad, 24.61),
        # 'ROAD' for the 1 SA Road Construction Battalion (23.13). '' for everything else, which is
        # every unit in every OOB that carries no engineer row -- so nothing else moves.
        engineer=s.get("engineer", ""),
        arrival_turn=arrival_turn,
        formation=rec["group"],
        # The nationality the stats were selected under, carried onto the counter: [38.37] prints
        # its refit modifiers and [35.23] its squadron capacity per nationality of the SGSU.
        nationality=nat,
        # Rule 9.16a: a garrison in its assigned home hex is free of the stacking limit
        # (the Giarabub "Oasis Complex" and the city garrisons deploy concentrated on one
        # hex). They are static defenders; home-hex tracking is deferred, so the exemption
        # travels with the unit -- faithful at setup, where the stacking check bites.
        is_garrison_home="Garrison" in rec["group"],
        fuel_rate=fuel_rate,
        # [21.12]/[4.47-4.49] Breakdown Adjustment Rating, per-model (mirror of fuel_rate):
        # 0 for a unit whose model carries none (guns never break down, 21.11). The German
        # early-war "+1R until Game-Turn 1/31" gate (4.49 note *) is moot for the seeded
        # Rommel's-Arrival / Desert-Fox scenarios, which begin after that gate -- so the
        # chart's steady post-gate value in unit_stats.json is faithful here.
        bar=model.get("bar", 0),
    )


def _uid(seen: dict[str, int], base: str) -> str:
    base = base.replace(" - none", "").replace(" ", "-")
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}#{seen[base]}"
