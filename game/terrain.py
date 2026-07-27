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

# [8.44], read verbatim off the scan (PDF page 15) and restated by [8.37] chart note 2 (page 70):
# "Vehicles, except for Light Trucks, Recce-type units, and motorcycle infantry may enter or leave a
# Salt Marsh hex only on a Road or Track." So the three named light classes are EXEMPT and keep the
# chart's 2 CP Mot entry; every other vehicle class is barred off-road/off-track. Foot and Camel are
# not vehicles and are never barred -- which is also where the rule's last sentence lands for free:
# "the one camel unit in the game (the Italian Meharisti Camel Cavalry) travels as infantry in non-
# track Salt Marsh hexes" is already true here, because CAMEL is in NON_MOT_CLASSES and therefore
# pays the chart's non-Mot 3 CP, exactly as infantry does.
SALT_MARSH_EXEMPT = frozenset({Mobility.LIGHT_TRUCK, Mobility.RECCE, Mobility.MOTORCYCLE})

# [8.45], read verbatim off the scan (PDF page 15) and restated by [8.37] chart note 3 (page 70):
# "Desert hexes are forbidden to Light Trucks, Motorcycle infantry, and motorcycle Recce units whose
# weight was not sufficient enough to provide the traction necessary for moving vehicles through the
# soft surface. Such units may not enter any Desert hexes, whether traversed by Tracks or not." /
# chart note 3: "Light Trucks, motorcycle reconnaissance units, and motorcycle infantry units may not
# enter, even via a track."
#
# This is the DUAL of [8.44], not its twin -- three things read differently on the scan, each
# checked against the printed word rather than copied from the Salt Marsh gate:
#
#   1. ENTER, not "enter or leave": 8.44 bars a class from crossing the edge in EITHER direction
#      ("may enter or leave... only on a Road or Track"); 8.45 bars only entry ("may not enter any
#      Desert hexes"). A barred unit already standing in a Desert hex (however it got there) may
#      still leave normally -- the gate below reads only the destination hex, never the source.
#
#   2. NO exemption at all, not even a Road: 8.44's exemption is explicit and reads "Road or Track";
#      8.45 mentions Track ONLY to close the one loophole a reader fresh off 8.44 would reach for --
#      "whether traversed by Tracks or not" -- and says nothing whatever about a Road. Two rulebook
#      paragraphs apart, the designer wrote "Road or Track" once and then, choosing his words again,
#      wrote neither. Read as written: the bar is unconditional.
#      THE COUNTER-ARGUMENT, recorded beside the ruling because it is the honest one: [8.37] note 2
#      restates 8.44 as "may only enter/leave the hex on a TRACK" -- dropping the Road the body rule
#      plainly grants -- which proves the chart notes are casual about the word "Road". So note 3's
#      "may not enter, even via a track" may equally be loose shorthand for "even via a road or
#      track". Both readings of that carelessness land on the SAME gate: either 8.45 names no
#      exemption (read strictly) or its "track" stands for "road or track" (read loosely as note 2
#      demonstrably does), and a Road opens nothing either way. What was written here before the
#      review and is NOT true, struck rather than quietly deleted: "A Road through the open desert
#      is also not something the 1979 map draws." The engine's own extracted road layer draws EIGHT
#      road edges touching a Desert hex -- D1930-D1931-D1932-D1933-E2000-E2001 (the Siwa/Jarabub
#      run) plus B0525-B0526, B0529-B0530 and B0402-B0403 -- and 16 track edges likewise, where the
#      book is explicit. An unchecked supporting fact that happened to flatter the ruling. Measured,
#      it is not load-bearing: a Road-exempt variant of this gate leaves every live Light convoy's
#      reach identical (scratchpad/rep845/roadexempt.py).
#
#   3. The named class list does not partition this engine's Mobility enum the way [8.44]'s did.
#      8.44 exempts "Recce-type units" as a whole -- which is exactly Mobility.RECCE, one class, one
#      name, no ambiguity. 8.45 bars "motorcycle Recce units" -- a NAMED SUBSET of Recce, called out
#      by name because the book itself distinguishes it from the wheeled/armoured-car recce that
#      SALT_MARSH_EXEMPT's Mobility.RECCE actually represents (data/unit_stats.json's "recon" entries
#      carry an armor_protection rating and a 40-45 CPA -- an armoured car, not a motorcycle). This
#      engine has no separate motorcycle-recce class to bar without also catching every armoured-car
#      recce unit the book does NOT forbid from the desert -- which would be worse than the gap it
#      closes, since armoured-car recce screening the open desert is exactly what those units did.
#      FLAGGED DEBT: DESERT_BARRED below covers Light Trucks and (foot-)motorcycle infantry, the two
#      classes the engine CAN name exactly; "motorcycle Recce units" specifically is left ungated
#      until the OOB carries a class finer than Mobility.RECCE to hang it on.
DESERT_BARRED = frozenset({Mobility.LIGHT_TRUCK, Mobility.MOTORCYCLE})


def is_motorized(m: Mobility) -> bool:
    return m not in NON_MOT_CLASSES


def salt_marsh_barred(m: Mobility) -> bool:
    """[8.44]: may this mobility class NOT enter or leave a Salt Marsh hex off a Road/Track?"""
    return is_motorized(m) and m not in SALT_MARSH_EXEMPT


def desert_barred(m: Mobility) -> bool:
    """[8.45]: may this mobility class NOT ENTER a Desert hex, on any terms -- Road, Track or
    open ground alike? Unlike salt_marsh_barred there is no exemption to check for and no need to
    gate leaving: see the DESERT_BARRED comment above for why."""
    return m in DESERT_BARRED


class Terrain(str, Enum):
    CLEAR = "CLEAR"
    GRAVEL = "GRAVEL"
    SALT_MARSH = "SALT_MARSH"
    HEAVY_VEG = "HEAVY_VEG"
    ROUGH = "ROUGH"
    MOUNTAIN = "MOUNTAIN"
    DELTA = "DELTA"
    DESERT = "DESERT"
    SWAMP = "SWAMP"
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
    # "May enter only on road or railroad" -- the Swamp row's OWN cell text on [8.37] (PDF p.70,
    # re-read at 450 dpi), spanning the non-Mot, Mot AND Breakdown-Value columns outright, with no
    # exception carved out for foot units, so off-road/off-rail entry is prohibited to every
    # mobility class. A Road/Track edge bypasses this table entirely (ROAD_ENTRY/TRACK_ENTRY in
    # movement.step_cost), which is how "only on road or railroad" actually gets satisfied -- this
    # pair only governs the case where neither is present.
    #
    # NOT note 4, and the scan is worth recording because the printed chart is confusing here: the
    # row IS printed "Swamp{superscript 4}", but note 4 reads "Alexandria and Cairo hexes are Level
    # Three Fortifications, all others are Level Two" -- a fortification note that says nothing
    # whatever about swamp, and that plainly belongs to the Major City row directly above (which is
    # printed with NO superscript at all, and whose Combat-Adjustment cell is the cross-reference
    # "See Fortifications"). Read as a typesetting slip in the 1979 chart, recorded rather than
    # "corrected": nothing depends on it, because the fort roster this engine builds
    # (data/city_forts.json) is independently stated in prose by [25.12].
    #
    # Known imprecision, flagged (LATENT -- all 17 Swamp hexes carry zero road/track/rail edges
    # today, so nothing reaches this branch): the engine's Track feature does not distinguish a
    # Track from a Railroad, so once 8.1b traces edges here a vehicle could enter Swamp off a mere
    # Track, where the chart admits only a Road or Railroad -- and, because Swamp's Breakdown Value
    # is the chart's blank cell (0, see _HEX_BREAKDOWN), it would do so at zero Breakdown cost, the
    # safest ground on the board. The same Track/Railroad coarseness is already accepted for [8.37]
    # notes 2/3; it is not a gap this slice invents, but it is the one to close first in 8.1b.
    Terrain.SWAMP: (PROHIBITED, PROHIBITED),
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


# --- Breakdown Point Values (the 8.37 chart's Breakdown-Value columns, rule 21.21)
# Breakdown Points a MOTORIZED vehicle accrues entering a hex / crossing a hexside;
# foot/camel never accrue any (21.11). Transcribed from data/breakdown_rates.json
# (the chart-of-record) and bound to it by test_breakdown; verified on PDF page 70.
# DESERT = 24 (two full-size digits on the scan, NOT the long-assumed "2 + footnote-4"
# bleed): the single highest value on the chart, which is exactly what makes the open
# desert -- not the enemy -- the main tank-killer.
_HEX_BREAKDOWN: dict[Terrain, float] = {
    Terrain.CLEAR: 4,
    Terrain.GRAVEL: 6,
    Terrain.SALT_MARSH: 6,
    Terrain.HEAVY_VEG: 3,
    Terrain.ROUGH: 8,
    Terrain.MOUNTAIN: 12,
    Terrain.DELTA: 2,
    Terrain.DESERT: 24,
    # The chart prints NO Breakdown-Value digit for Swamp (data/breakdown_rates.json's own
    # _absent_note: "no independent BV") -- read the same way Track's blank BV cell reads (8.37
    # note 8: "A track carries no BV of its own"), i.e. faithfully 0, not a guessed number. In
    # practice this is nearly unreachable: off-road/off-track entry is PROHIBITED (_HEX_ENTRY
    # above), a dry Road bypasses this table via ROAD_BREAKDOWN, so only the Track-halving branch
    # in movement.breakdown_points ever consults it.
    Terrain.SWAMP: 0,
    Terrain.MAJOR_CITY: 0.5,
}

# Breakdown Points ADDED crossing a hexside feature. None = prohibited to vehicles
# (Up Escarpment 8.42 / Major River except by road at no BP, note 11). Down Escarpment
# is NOT halved by a track (the explicit note-8 exception; see breakdown_points).
_HEXSIDE_BREAKDOWN: dict[Hexside, float | None] = {
    Hexside.RIDGE: 2,
    Hexside.UP_SLOPE: 2,
    Hexside.DOWN_SLOPE: 2,
    Hexside.UP_ESCARPMENT: PROHIBITED,
    Hexside.DOWN_ESCARPMENT: 6,
    Hexside.WADI: 8,
    Hexside.MAJOR_RIVER: PROHIBITED,
    Hexside.MINOR_RIVER: 1,
}

# A Road has its own Breakdown Value of 1/2 and NEGATES hexside Breakdown Points
# (note 6); a Track HALVES both hex and hexside Breakdown Values (note 8).
ROAD_BREAKDOWN: float = 0.5


def breakdown_value(terrain: Terrain) -> float:
    """Breakdown Points a vehicle accrues entering a hex of this terrain (8.37)."""
    return _HEX_BREAKDOWN[terrain]


def hexside_breakdown(feature: Hexside) -> float | None:
    """Breakdown Points a vehicle accrues crossing this hexside feature (8.37), or
    None if the hexside is prohibited to vehicles (no Breakdown Value)."""
    return _HEXSIDE_BREAKDOWN[feature]
