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


def build(oob_file: str = "oob_desert_fox.json",
          sections: str | None = None) -> tuple[list[Unit], list[SupplyUnit]]:
    """Build engine units/supplies from an OOB file. If `sections` is given (e.g.
    "ABC"), only pieces whose hex is in those map sections are kept (rear units on
    unloaded sections are dropped)."""
    oob = _load(oob_file)
    stats = _load("unit_stats.json")
    units: list[Unit] = []
    supplies: list[SupplyUnit] = []
    seen: dict[str, int] = {}

    for rec in oob:
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
        if role is None:
            continue
        s = stats[_nationality(rec["side"])][role]
        uid = _uid(seen, rec["counter"])
        units.append(Unit(
            uid, side, ax,
            (StepRecord(role, s["steps"]),),
            mobility=Mobility[s["mobility"]],
            cpa=s["cpa"], stacking_points=1,
            oca=s["oca"], dca=s["dca"],
            morale=_morale_for(rec["group"], rec["counter"]),
            is_combat=s.get("is_combat", True),
        ))
    return units, supplies


def _uid(seen: dict[str, int], base: str) -> str:
    base = base.replace(" - none", "").replace(" ", "-")
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}#{seen[base]}"
