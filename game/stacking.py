"""Stacking (rule 9.0).

Each unit has a Stacking-Point value; each hex caps the total points present at
the end of a Movement Segment (§9.14), with a separate 5-point limit for road/
track movement (§9.33). Some units don't count: first-line attached trucks
(§9.29), pure AA in major cities / air facilities (§9.16b / §46.17), and a
garrison in its assigned home hex (§9.16a).

The per-terrain hex limits are the [8.37] Terrain Effects Chart's Stacking-Points
column, sourced from data/stacking_limits.json (transcribed
scratchpad/port/transcriptions/8.37-terrain-effects-chart.md, PDF page 70; the
prior DEFAULT_HEX_LIMIT=5 placeholder matched no real chart value): every terrain
is 6 EXCEPT Mountain (3) and Major City (8). Hexside features / fortification
levels / minefields print a dash in that column -- they overlay a hex whose base
Terrain already supplies the limit, so the lookup keys ONLY on Terrain, never on
those. The road/track limit of 5 (§9.33 prose) is independently confirmed by the
SAME chart's Road/Track rows and is sourced from the same data file.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Iterable, Protocol

from . import organization
from .terrain import Terrain

_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "stacking_limits.json"))

# JSON chart keys -> engine enum (the one spelling mismatch: heavy_vegetation -- matches
# test_breakdown.py's identical adapter for data/breakdown_rates.json, the chart's other columns).
_TERRAIN_KEY: dict[Terrain, str] = {
    Terrain.CLEAR: "clear", Terrain.GRAVEL: "gravel", Terrain.SALT_MARSH: "salt_marsh",
    Terrain.HEAVY_VEG: "heavy_vegetation", Terrain.ROUGH: "rough",
    Terrain.MOUNTAIN: "mountain", Terrain.DELTA: "delta", Terrain.DESERT: "desert",
    Terrain.MAJOR_CITY: "major_city",
}


@lru_cache(maxsize=1)
def _data() -> dict:
    with open(_PATH) as f:
        return json.load(f)


def hex_stack_limit(terrain: Terrain) -> int:
    """[8.37]/[9.14]: the maximum Stacking Points a hex of this terrain may hold at the
    end of a Movement Segment."""
    return _data()["hex_terrain"][_TERRAIN_KEY[terrain]]


# [9.33]: a separate, flat limit for units/trucks moving THROUGH a stack (not terrain-keyed --
# see data/stacking_limits.json's road_track_9_33 block for why Road/Track are not a Terrain).
ROAD_TRACK_STACK_LIMIT: int = _data()["road_track_9_33"]["limit"]

# The value every currently-mapped terrain shares except Major City (8) and the still-unmapped
# Mountain (3) -- see hex_stack_limit for the real per-hex lookup. Exposed only for the LLM-
# facing advisory in game.observation; every legality check in the engine resolves the true
# per-hex terrain through hex_stack_limit / within_hex_limit, never this shortcut.
COMMON_HEX_LIMIT: int = hex_stack_limit(Terrain.CLEAR)


class StackUnit(Protocol):
    stacking_points: int
    is_first_line_truck: bool   # §9.29: excluded from hex stacking (and road space)
    is_pure_aa: bool            # §9.16b/§46.17: free in major cities / air facilities
    is_garrison_home: bool      # §9.16a: free in its assigned city/village
    attached_to: str            # §9.21/§19.12: represented by its Parent Formation's counter
    org_type: str               # §9.12: an HQ's parenthesized value lives on the 19.3 chart


def counts_in_hex(u: StackUnit, terrain: Terrain, stack: Iterable[StackUnit] = ()) -> int:
    """§9.11-§9.21: what one counter costs the hex it stands in.

    `stack` is the rest of the hex, needed only for the rule-19 organization tree: an HQ is
    worth "'0' when it has no combat units of any type attached; the printed number... when it
    represents the division or brigade as a combat unit" (§9.12), and a unit attached to a Parent
    is inside that Parent's counter and costs nothing more (§9.21). Every attached unit is in its
    Parent's hex by §19.13, so the hex is all the context this needs. Default () = no tree, which
    reads the printed value on every counter -- the pre-rule-19 behaviour, unchanged."""
    if u.is_first_line_truck:                       # §9.29
        return 0
    if u.is_garrison_home:                          # §9.16a
        return 0
    if u.is_pure_aa and terrain == Terrain.MAJOR_CITY:   # §9.16b (city; airfield/strip later)
        return 0
    return organization.size(u, stack)


def hex_points(units: Iterable[StackUnit], terrain: Terrain) -> int:
    stack = tuple(units)
    return sum(counts_in_hex(u, terrain, stack) for u in stack)


def within_hex_limit(units: Iterable[StackUnit], terrain: Terrain) -> bool:
    return hex_points(units, terrain) <= hex_stack_limit(terrain)


def road_track_points(units: Iterable[StackUnit]) -> int:
    # §9.29: first-line trucks don't count for road space either; unattached truck
    # convoys DO (modelled when the truck/supply slice lands). Road space is denominated in
    # the same Stacking Points as the hex limit, so it reads the same §9.12/§9.21 tree.
    stack = tuple(units)
    return sum(organization.size(u, stack) for u in stack if not u.is_first_line_truck)


def within_road_track_limit(units: Iterable[StackUnit]) -> bool:
    return road_track_points(units) <= ROAD_TRACK_STACK_LIMIT
