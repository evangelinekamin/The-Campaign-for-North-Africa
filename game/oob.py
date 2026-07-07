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
# separately from the 61.44/61.36 pools (see _place_dumps).
_TOBRUK_BUILTIN = logistics_data.tobruk_builtin_61_36()
DUMP_AMMO = _TOBRUK_BUILTIN["AMMO"]      # 1500 [61.36]
DUMP_FUEL = _TOBRUK_BUILTIN["FUEL"]      # 500  [61.36]
DUMP_STORES = _TOBRUK_BUILTIN["STORES"]  # 1000 [61.36]
DUMP_WATER = 1000                        # FLAGGED wells/rail proxy (52.7/54.3 deferred)

# [61.44]/[61.36] FULL-LOGISTICS start-line supply pools, distributed over each side's
# dumps by _place_dumps (authored, deterministic even split, clipped to the 54.12 caps).
_AXIS_DUMP_POOL = logistics_data.axis_dump_pool_61_44()   # AMMO/FUEL/STORES/WATER
_CW_DUMP_POOL = logistics_data.cw_dump_pool_61_36()        # AMMO/FUEL/STORES (no charted water)
_CW_WATER_PROXY = 1600                                     # FLAGGED wells/rail Water (52.7/54.3)
_OTHER_CAP = logistics_data.dump_other_terrain_cap()       # [54.12] Other-Terrain ceilings

# [49.13]/[4.47-4.49] per-model Fuel Consumption Rate, keyed by model name.
_FUEL_RATE_BY_MODEL = logistics_data.fuel_rate_by_model()


def _load(name: str) -> dict | list:
    with open(os.path.normpath(os.path.join(_DATA, name))) as f:
        return json.load(f)


def _nationality(side: str) -> str:
    return "GE" if side == "AXIS" else "CW"


# Basic Morale by formation (rule 17.1, from the OA sheets; see cna-unit-stats-source).
FORMATION_MORALE = (
    ("5th Light", 2), ("15th Panzer", 2), ("90th", 2), ("164th", 1), ("Ariete", 1),
    ("2nd Armoured", 2), ("9th Australian", 1), ("Indian", 1), ("Oasis", 0),
    ("Pavia", -1), ("Bologna", -1), ("Brescia", -1), ("Savona", -1),  # Italian semi-mot divs
    ("Trento", 0), ("Sabratha", -1),
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
    if "Air Strip" in c or "Airstrip" in c or "SGSU" in c:
        return None                                  # airfields / air-support bases
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
          ) -> tuple[list[Unit], list[SupplyUnit]]:
    """Build engine units/supplies from an OOB file. If `sections` is given (e.g.
    "ABC"), only pieces whose hex is in those map sections are kept (rear units on
    unloaded sections are dropped). `reinforcements_file` (rule 20) adds off-map
    units that enter on their arrival_turn at an axial entry hex."""
    stats = _load("unit_stats.json")
    units: list[Unit] = []
    dumps_meta: list[tuple[str, Side, tuple]] = []   # (uid, side, hex) placed after the loop
    seen: dict[str, int] = {}

    for rec in _load(oob_file):
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
        role = classify(rec["counter"], rec["group"])
        if role is not None:
            units.append(_make_unit(rec, side, ax, role, stats, seen, 0))

    supplies: list[SupplyUnit] = _place_dumps(dumps_meta)

    for rec in (_load(reinforcements_file).get("reinforcements", []) if reinforcements_file else []):
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


def _dump_pool(side: Side) -> dict:
    """The [61.44]/[61.36] start-line supply pool for `side`, as commodity->points.
    The Axis pool carries its charted Water (61.44); the Commonwealth pool has no
    charted dump Water, so a FLAGGED wells/rail proxy is layered on (52.7/54.3)."""
    if side == Side.AXIS:
        return dict(_AXIS_DUMP_POOL)
    return {**_CW_DUMP_POOL, "WATER": _CW_WATER_PROXY}


def _share(total: int, n: int, i: int) -> int:
    """Deterministic even split of `total` over `n` slots; the first `total % n`
    slots carry the extra point so the pool is conserved exactly."""
    return total // n + (1 if i < total % n else 0)


def _place_dumps(dumps_meta: list[tuple[str, Side, tuple]]) -> list[SupplyUnit]:
    """Authored, deterministic placement of each side's 61.44/61.36 supply pool over
    its dump hexes: an even split (remainder to the earliest dumps) clipped to the
    54.12 Other-Terrain ceilings. Real-scale (Regime B) start-line reservoir -- the
    fuel the 49.13 x-strength demand draws on. The rulebook's <=50% (Axis) / <=25%
    (CW) per-dump placement caps are honoured wherever the (abstracted) corridor's
    dump count allows; the binding ceiling here is 54.12, which every share clears."""
    by_side: dict[Side, list[tuple[str, tuple]]] = {}
    for uid, side, ax in dumps_meta:
        by_side.setdefault(side, []).append((uid, ax))
    out: list[SupplyUnit] = []
    for side, lst in by_side.items():
        pool = _dump_pool(side)
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
    nat = rec.get("nationality") or _nationality(rec["side"])    # IT units set it explicitly
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
        morale=_morale_for(rec["group"], rec["counter"]),
        is_combat=s.get("is_combat", True),
        arrival_turn=arrival_turn,
        formation=rec["group"],
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
