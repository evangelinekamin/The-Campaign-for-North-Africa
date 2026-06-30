"""Terrain Effects Chart (rule 8.37) — the movement-cost data.

Transcribed from docs/rules/90-charts-tables-and-play-aids.md (the engine is the
structure; the rulebook is the numbers). Only the two CP columns the land-movement
core needs are encoded here: hex-entry cost and hexside-crossing cost, each split
non-motorized / motorized. The chart's Breakdown-Value and combat-shift columns
(Barrage / Anti-Armor / Close Assault) are deferred to later slices (§21, §11-15).

PROVISIONAL VALUES — VERIFY AGAINST THE SCAN: the OCR of this dense chart bled a
couple of footnote digits into values (e.g. Desert "4³"/"2⁴"). The CP figures
below read clean, but per the brief, spot-check exact chart cells against the
Internet Archive scan before trusting them in a scored run.
"""
from __future__ import annotations

from enum import Enum

PROHIBITED: None = None  # 'P' on the chart — impassable for that mobility class


class Mobility(str, Enum):
    """A unit's movement class. `motorized` (below) collapses these to the
    chart's non-Mot / Mot columns; the finer classes carry the sub-type terrain
    prohibitions (footnotes 2/3) applied once units have real OOB data."""
    FOOT = "FOOT"            # leg infantry / most gun units
    CAMEL = "CAMEL"          # Meharisti camel cavalry (moves as foot off-track)
    MOTORIZED = "MOTORIZED"  # truck-borne infantry, towed artillery
    VEHICLE = "VEHICLE"      # tanks / AFVs / SP artillery
    RECCE = "RECCE"
    MOTORCYCLE = "MOTORCYCLE"
    LIGHT_TRUCK = "LIGHT_TRUCK"

NON_MOT_CLASSES = frozenset({Mobility.FOOT, Mobility.CAMEL})


def is_motorized(m: Mobility) -> bool:
    return m not in NON_MOT_CLASSES


class Terrain(str, Enum):
    CLEAR = "CLEAR"
    GRAVEL = "GRAVEL"
    SALT_MARSH = "SALT_MARSH"
    HEAVY_VEG = "HEAVY_VEG"
    ROUGH = "ROUGH"
    MOUNTAIN = "MOUNTAIN"
    DELTA = "DELTA"
    DESERT = "DESERT"
    MAJOR_CITY = "MAJOR_CITY"


class Hexside(str, Enum):
    """Crossing features live on the hexside and are *directional* (up vs down).
    The map encodes which direction is 'up' by which ordered edge carries which."""
    RIDGE = "RIDGE"
    UP_SLOPE = "UP_SLOPE"
    DOWN_SLOPE = "DOWN_SLOPE"
    UP_ESCARPMENT = "UP_ESCARPMENT"
    DOWN_ESCARPMENT = "DOWN_ESCARPMENT"
    WADI = "WADI"
    MAJOR_RIVER = "MAJOR_RIVER"
    MINOR_RIVER = "MINOR_RIVER"


# (non_mot, mot) CP to ENTER a hex of this terrain. None = prohibited.
_HEX_ENTRY: dict[Terrain, tuple[float | None, float | None]] = {
    Terrain.CLEAR: (2, 2),
    Terrain.GRAVEL: (2, 2),
    Terrain.SALT_MARSH: (3, 2),
    Terrain.HEAVY_VEG: (3, 3),
    Terrain.ROUGH: (3, 4),
    Terrain.MOUNTAIN: (4, 6),
    Terrain.DELTA: (2, 4),
    Terrain.DESERT: (3, 4),
    Terrain.MAJOR_CITY: (1, 0.5),
}

# (non_mot, mot) CP ADDED to cross this hexside feature. None = prohibited.
_HEXSIDE_ADD: dict[Hexside, tuple[float | None, float | None]] = {
    Hexside.RIDGE: (2, 4),
    Hexside.UP_SLOPE: (2, 4),
    Hexside.DOWN_SLOPE: (1, 2),
    Hexside.UP_ESCARPMENT: (6, PROHIBITED),       # no vehicle may move up an escarpment (8.42)
    Hexside.DOWN_ESCARPMENT: (4, 8),
    Hexside.WADI: (1, 4),                          # impassable in rainstorm except by road (note 10)
    Hexside.MAJOR_RIVER: (8, PROHIBITED),          # mot only by road/railroad (note 11)
    Hexside.MINOR_RIVER: (3, 6),
}

# Moving ALONG a road / track replaces the hex-entry cost (rule 8.33/8.46).
ROAD_ENTRY: dict[bool, float] = {False: 1, True: 0.5}    # keyed by is_motorized
TRACK_ENTRY: dict[bool, float] = {False: 1, True: 1}


def hex_entry_cost(terrain: Terrain, mobility: Mobility) -> float | None:
    return _HEX_ENTRY[terrain][1 if is_motorized(mobility) else 0]


def hexside_cost(feature: Hexside, mobility: Mobility) -> float | None:
    return _HEXSIDE_ADD[feature][1 if is_motorized(mobility) else 0]
