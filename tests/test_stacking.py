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


def test_over_limit_rejected():
    units = [S(1)] * 6
    assert not stacking.within_hex_limit(units, Terrain.CLEAR, limit=5)


def test_first_line_trucks_excluded():
    units = [S(1)] * 5 + [S(2, is_first_line_truck=True)]
    assert stacking.hex_points(units, Terrain.CLEAR) == 5      # truck contributes 0
    assert stacking.within_hex_limit(units, Terrain.CLEAR, limit=5)


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
