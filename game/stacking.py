"""Stacking (rule 9.0).

Each unit has a Stacking-Point value; each hex caps the total points present at
the end of a Movement Segment (§9.14), with a separate 5-point limit for road/
track movement (§9.33). Some units don't count: first-line attached trucks
(§9.29), pure AA in major cities / air facilities (§9.16b / §46.17), and a
garrison in its assigned home hex (§9.16a).

PROVISIONAL VALUES — VERIFY AGAINST SCAN: the per-terrain hex limits live on the
8.37 chart / counter sheets (§9.4 "separate sheet") and did NOT survive OCR (the
OCR'd 8.37 has no stacking column). So the hex limit is injected by the caller;
DEFAULT_HEX_LIMIT below is a placeholder. The road/track limit of 5 IS sourced
(§9.33 prose).
"""
from __future__ import annotations

from typing import Iterable, Protocol

from .terrain import Terrain

ROAD_TRACK_STACK_LIMIT = 5      # §9.33 (sourced from prose)
DEFAULT_HEX_LIMIT = 5          # PLACEHOLDER — verify per-terrain limits vs scan


class StackUnit(Protocol):
    stacking_points: int
    is_first_line_truck: bool   # §9.29: excluded from hex stacking (and road space)
    is_pure_aa: bool            # §9.16b/§46.17: free in major cities / air facilities
    is_garrison_home: bool      # §9.16a: free in its assigned city/village


def counts_in_hex(u: StackUnit, terrain: Terrain) -> int:
    if u.is_first_line_truck:                       # §9.29
        return 0
    if u.is_garrison_home:                          # §9.16a
        return 0
    if u.is_pure_aa and terrain == Terrain.MAJOR_CITY:   # §9.16b (city; airfield/strip later)
        return 0
    return u.stacking_points


def hex_points(units: Iterable[StackUnit], terrain: Terrain) -> int:
    return sum(counts_in_hex(u, terrain) for u in units)


def within_hex_limit(units: Iterable[StackUnit], terrain: Terrain,
                     limit: int = DEFAULT_HEX_LIMIT) -> bool:
    return hex_points(units, terrain) <= limit


def road_track_points(units: Iterable[StackUnit]) -> int:
    # §9.29: first-line trucks don't count for road space either; unattached truck
    # convoys DO (modelled when the truck/supply slice lands).
    return sum(u.stacking_points for u in units if not u.is_first_line_truck)


def within_road_track_limit(units: Iterable[StackUnit]) -> bool:
    return road_track_points(units) <= ROAD_TRACK_STACK_LIMIT
