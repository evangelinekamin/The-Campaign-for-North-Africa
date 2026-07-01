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

from . import coords
from .events import Side
from .state import StepRecord, SupplyUnit, Unit
from .terrain import Mobility

_DATA = os.path.join(os.path.dirname(__file__), "..", "data")
DUMP_AMMO = 40      # rule 32.15 dump capacity
DUMP_FUEL = 60


def _load(name: str) -> dict | list:
    with open(os.path.normpath(os.path.join(_DATA, name))) as f:
        return json.load(f)


def _nationality(side: str) -> str:
    return "GE" if side == "AXIS" else "CW"


# Basic Morale by formation (rule 17.1, from the OA sheets; see cna-unit-stats-source).
FORMATION_MORALE = (
    ("5th Light", 2), ("15th Panzer", 2), ("90th", 2), ("164th", 1), ("Ariete", 1),
    ("2nd Armoured", 2), ("9th Australian", 1), ("Indian", 1), ("Oasis", 0),
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
    supplies: list[SupplyUnit] = []
    seen: dict[str, int] = {}

    for rec in _load(oob_file):
        hexlbl = rec["hex"]
        if sections is not None and hexlbl[0] not in sections:
            continue
        side = Side.AXIS if rec["side"] == "AXIS" else Side.ALLIED
        ax = coords.to_axial(coords.parse(hexlbl))

        if rec["kind"] == "dump":
            uid = _uid(seen, f"{rec['side'][:2]}-Dump")
            supplies.append(SupplyUnit(uid, side, ax, ammo=DUMP_AMMO, fuel=DUMP_FUEL))
            continue
        if rec["kind"] != "unit":
            continue                                 # features are not engine units
        role = classify(rec["counter"], rec["group"])
        if role is not None:
            units.append(_make_unit(rec, side, ax, role, stats, seen, 0))

    for rec in (_load(reinforcements_file).get("reinforcements", []) if reinforcements_file else []):
        side = Side.AXIS if rec["side"] == "AXIS" else Side.ALLIED
        role = rec.get("role") or classify(rec["counter"], rec["group"])
        if role is not None:
            units.append(_make_unit(rec, side, tuple(rec["hex"]), role, stats, seen,
                                    rec["arrival_turn"]))
    return units, supplies


# Default weapon model per (nationality, role) for units that don't name one, so
# the role-level combat ratings resolve to a concrete period model (1941). A unit
# record may override with its own "model" (e.g. Matildas vs cruisers).
MODEL_DEFAULTS = {
    ("GE", "tank"): "pz3h", ("GE", "antitank"): "pak38", ("GE", "artillery"): "lefh18",
    ("CW", "tank"): "a13", ("CW", "artillery"): "25pdr",
}


def _make_unit(rec: dict, side: Side, ax, role: str, stats: dict, seen: dict,
               arrival_turn: int) -> Unit:
    nat = _nationality(rec["side"])
    s = stats[nat][role]
    model = stats.get("models", {}).get(rec.get("model") or MODEL_DEFAULTS.get((nat, role)), {})

    def rating(key: str) -> int:                     # model overrides role, else 0
        return model.get(key, s.get(key, 0))
    return Unit(
        _uid(seen, rec["counter"]), side, ax,
        (StepRecord(role, s["steps"]),),
        mobility=Mobility[s["mobility"]],
        cpa=s["cpa"], stacking_points=1,
        oca=model.get("oca", s["oca"]), dca=model.get("dca", s["dca"]),
        barrage=rating("barrage"), anti_armor=rating("anti_armor"),
        armor_protection=rating("armor_protection"), vulnerability=rating("vulnerability"),
        is_tank=model.get("is_tank", s.get("is_tank", False)),
        morale=_morale_for(rec["group"], rec["counter"]),
        is_combat=s.get("is_combat", True),
        arrival_turn=arrival_turn,
    )


def _uid(seen: dict[str, int], base: str) -> str:
    base = base.replace(" - none", "").replace(" ", "-")
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}#{seen[base]}"
