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

from . import coords, logistics_data
from .events import Side
from .state import Rommel, StepRecord, SupplyUnit, Unit
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


def classify(counter: str, group: str) -> str:
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
    3.23) map to the `aa` role (the Commonwealth had no AA arm), and Air Landing Strips /
    flying-boat Alighting areas / Squadron Ground Support Units (rule 3.21) map to the inert
    `air` role instead of being dropped -- they carry the facility hexes the Phase 5 Air Game
    needs. `air` never returns None, so nothing the OOB ships is silently discarded here.
    """
    c = counter
    # Air facilities + Squadron Ground Support Units (rule 3.21): inert non-combat pieces.
    if ("Air Strip" in c or "Airstrip" in c or "Airboat" in c or "Alighting" in c
            or "SGSU" in c):
        return "air"
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
    return units, supplies


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
