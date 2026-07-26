"""Golden tests for stacking (rule 9.0)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import stacking
from game.terrain import Terrain


@dataclass
class S:
    """A StackUnit stub. `attached_to` / `org_type` joined the protocol when rule 19 landed:
    §9.12 and §9.21 make a counter's stacking value a function of the organization tree (a bare
    HQ is 0, a Parent Formation is worth its printed value, an attached subsidiary is inside its
    Parent's counter). Both default to "independent", which is what every counter here is."""
    stacking_points: int = 1
    is_first_line_truck: bool = False
    is_pure_aa: bool = False
    is_garrison_home: bool = False
    attached_to: str = ""
    org_type: str = ""


def test_two_battalions_within_default_limit():
    units = [S(1), S(1)]
    assert stacking.hex_points(units, Terrain.CLEAR) == 2
    assert stacking.within_hex_limit(units, Terrain.CLEAR)


# --- [8.37] per-terrain Stacking Limit (replaces the old flat DEFAULT_HEX_LIMIT=5 placeholder) --

def test_six_stack_on_clear_is_within_limit():
    # THE REGRESSION: under the old flat DEFAULT_HEX_LIMIT=5 placeholder this raised. The real
    # [8.37] Clear Stacking Limit is 6 (data/stacking_limits.json, verified against the scan) --
    # a legal 6-stack on a limit-6 terrain must no longer raise.
    units = [S(1)] * 6
    assert stacking.hex_points(units, Terrain.CLEAR) == 6
    assert stacking.within_hex_limit(units, Terrain.CLEAR)


def test_seven_stack_on_clear_exceeds_limit():
    units = [S(1)] * 7
    assert not stacking.within_hex_limit(units, Terrain.CLEAR)


def test_mountain_limit_is_three():
    units = [S(1)] * 3
    assert stacking.within_hex_limit(units, Terrain.MOUNTAIN)
    assert not stacking.within_hex_limit(units + [S(1)], Terrain.MOUNTAIN)


def test_major_city_limit_is_eight():
    units = [S(1)] * 8
    assert stacking.within_hex_limit(units, Terrain.MAJOR_CITY)
    assert not stacking.within_hex_limit(units + [S(1)], Terrain.MAJOR_CITY)


def test_hex_stack_limit_matches_chart_of_record():
    # Every terrain currently reachable on the map (game/terrain.py's Terrain enum) reads back
    # exactly data/stacking_limits.json -- the chart-of-record, not a second hardcoded copy.
    assert stacking.hex_stack_limit(Terrain.CLEAR) == 6
    assert stacking.hex_stack_limit(Terrain.GRAVEL) == 6
    assert stacking.hex_stack_limit(Terrain.SALT_MARSH) == 6
    assert stacking.hex_stack_limit(Terrain.HEAVY_VEG) == 6
    assert stacking.hex_stack_limit(Terrain.ROUGH) == 6
    assert stacking.hex_stack_limit(Terrain.DELTA) == 6
    assert stacking.hex_stack_limit(Terrain.DESERT) == 6
    assert stacking.hex_stack_limit(Terrain.MOUNTAIN) == 3
    assert stacking.hex_stack_limit(Terrain.MAJOR_CITY) == 8


def test_first_line_trucks_excluded():
    units = [S(1)] * 6 + [S(2, is_first_line_truck=True)]
    assert stacking.hex_points(units, Terrain.CLEAR) == 6      # truck contributes 0
    assert stacking.within_hex_limit(units, Terrain.CLEAR)     # would fail at 8 if the truck counted


def test_pure_aa_free_in_major_city_only():
    aa = S(1, is_pure_aa=True)
    assert stacking.counts_in_hex(aa, Terrain.MAJOR_CITY) == 0
    assert stacking.counts_in_hex(aa, Terrain.CLEAR) == 1       # not free outside cities


def test_garrison_free_in_home_hex():
    assert stacking.counts_in_hex(S(1, is_garrison_home=True), Terrain.CLEAR) == 0


def test_road_track_limit_is_five_and_excludes_first_line_trucks():
    assert stacking.within_road_track_limit([S(1)] * 5)
    assert not stacking.within_road_track_limit([S(1)] * 6)
    convoy = [S(1)] * 5 + [S(3, is_first_line_truck=True)]
    assert stacking.within_road_track_limit(convoy)            # truck excluded
