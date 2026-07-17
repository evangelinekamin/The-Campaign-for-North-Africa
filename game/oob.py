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


def classify(counter: str, group: str) -> str | None:
    """Map a counter to a stat role, or None to skip (feature / air base)."""
    c, g = counter, group
    if ("Air Strip" in c or "Airstrip" in c or "SGSU" in c or "Alighting" in c
            or "Airstrip" in g or "Alighting" in g):
        return None                                  # airfields / landing strips / flying-boat basins

    if c.startswith("IT ") or g.startswith("IT "):   # 1940 Italian 10th Army (rule 60.31 / [4.44b])
        if "(MG)" in c or "(MMG)" in c:
            return "mg"                              # machinegun battalions / companies
        if "(ART)" in c:
            return "artillery"
        if "(AA)" in c:
            return "antitank"                        # emplaced dual-purpose CD / flak (immobility deferred)
        if "(ENG)" in c or "(SPA)" in c:
            return "infantry"                        # engineers / garrison support fight as infantry
        if "Gun Units" in g:
            return "artillery"                       # X Corpo & unassigned artillery
        if "Sno" in c:
            return "infantry"                        # Sahariano camel battalions (Maletti)
        if "Maletti" in c:
            return "artillery"                       # 1st / 2nd Maletti artillery battalions
        if "Tank Command" in g:
            return "tank"                            # Libyan Tank Command (M11/39 + CV33)
        return "infantry"                            # colonial / Blackshirt / garrison / marine line infantry

    if "Rommel" in c or "DAK" in c or "SPt" in c or c.endswith(" Le - none"):
        return "hq"                                  # HQs (counter is authoritative)
    if "RNF" in c:
        return "mg"
    if "(ATG)" in c:
        return "antitank"
    if "Artillery" in g or "ArKo" in c or "155" in c or " Med " in c:
        return "artillery"
    if "Oasis" in g:
        return "oasis"
    if "Australian" in g:
        return "infantry"
    if "Indian" in g or "FMtMr" in c or "Free French" in g:
        return "motor_infantry"
    if "Armoured" in g or "Tank" in g:
        return "tank"
    return "infantry"                                # sensible default


def build(oob_file: str = "oob_desert_fox.json", sections: str | None = None,
          reinforcements_file: str | None = "reinforcements_desert_fox.json",
          extra_file: str | None = None, dump_pools: dict | None = None,
          ) -> tuple[list[Unit], list[SupplyUnit]]:
    """Build engine units/supplies from an OOB file. If `sections` is given (e.g.
    "ABC"), only pieces whose hex is in those map sections are kept (rear units on
    unloaded sections are dropped). `reinforcements_file` (rule 20) adds off-map
    units that enter on their arrival_turn at an axial entry hex. `extra_file` adds
    further on-map pieces from a second OOB file (same schema), so a hand-authored
    campaign gap-fill can layer onto a raw VASSAL extraction without editing it; an
    on-map record may carry an explicit `role` to override classify(). `dump_pools`
    (Side -> commodity->points) is the 64.3 start-line field-dump pool; it defaults to
    the SECTION-61 Desert Fox pools, and game.scenario.campaign passes SECTION 60."""
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
