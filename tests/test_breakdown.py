"""Vehicle Breakdown + Repair (rules 21/22, Fork B faithful proxy).

Every magnitude here is the rulebook's own -- the terrain/hexside Breakdown Values,
the 21.38 Breakdown Table, the 22.8 field-repair schedule -- and a chart-of-record
test binds the code constants to data/breakdown_rates.json so they cannot drift.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import combat_tables as ct
from game import terrain as T
from game.movement import TerrainMap, breakdown_points, edge
from game.terrain import Hexside, Mobility, Terrain

_BRK = json.load(open(os.path.join(
    os.path.dirname(__file__), "..", "data", "breakdown_rates.json")))


# --- Step 1: terrain Breakdown Values + breakdown_points ---------------------

# JSON chart keys -> engine enum (the one spelling mismatch: heavy_vegetation).
_TERRAIN_KEY = {
    "clear": Terrain.CLEAR, "gravel": Terrain.GRAVEL, "salt_marsh": Terrain.SALT_MARSH,
    "heavy_vegetation": Terrain.HEAVY_VEG, "rough": Terrain.ROUGH,
    "mountain": Terrain.MOUNTAIN, "delta": Terrain.DELTA, "desert": Terrain.DESERT,
    "major_city": Terrain.MAJOR_CITY,
}
_HEXSIDE_KEY = {
    "ridge": Hexside.RIDGE, "up_slope": Hexside.UP_SLOPE, "down_slope": Hexside.DOWN_SLOPE,
    "up_escarpment": Hexside.UP_ESCARPMENT, "down_escarpment": Hexside.DOWN_ESCARPMENT,
    "wadi": Hexside.WADI, "major_river": Hexside.MAJOR_RIVER, "minor_river": Hexside.MINOR_RIVER,
}


def test_terrain_breakdown_values_match_chart_of_record():
    hexes = _BRK["terrain_breakdown_values_8_37"]["hex_terrain"]
    for key, terrain in _TERRAIN_KEY.items():
        assert T.breakdown_value(terrain) == hexes[key], key
    assert T.breakdown_value(Terrain.DESERT) == 24         # the load-bearing recovery


def test_hexside_breakdown_values_match_chart_of_record():
    sides = _BRK["terrain_breakdown_values_8_37"]["hexside"]
    for key, feature in _HEXSIDE_KEY.items():
        want = None if sides[key] == "P" else sides[key]
        assert T.hexside_breakdown(feature) == want, key


def test_road_breakdown_value_matches_chart():
    assert T.ROAD_BREAKDOWN == _BRK["terrain_breakdown_values_8_37"]["road"]["breakdown_value"]


def _line(*coords, terrain, hexsides=None, roads=(), tracks=()):
    return TerrainMap(terrain={c: terrain for c in coords},
                      hexsides=hexsides or {},
                      roads=frozenset(roads), tracks=frozenset(tracks))


def test_foot_never_breaks_down():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.DESERT)
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.FOOT) == 0.0
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.CAMEL) == 0.0


def test_desert_step_is_the_tank_killer():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.DESERT)
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 24


def test_54_2_worked_example_is_ten():
    # A Light Truck along a Track, across a Wadi hexside, into a Rough hex:
    # 1/2x8 (rough) + 1/2x8 (wadi) + 1 (hex off-road) + 1 (hexside off-road) = 10.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.ROUGH,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 tracks=[edge((0, 0), (1, 0))])
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.LIGHT_TRUCK) == 10
    example = _BRK["terrain_breakdown_values_8_37"]["light_truck_offroad_54_2"]
    assert "10 BP" in example["worked_example_54_2"]


def test_road_negates_hexside_breakdown():
    # On a road across a wadi into desert: only the road's own 1/2 value, hexside negated.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.DESERT,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 roads=[edge((0, 0), (1, 0))])
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 0.5
    # a light truck ON a road gets no off-road penalty either
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.LIGHT_TRUCK) == 0.5


def test_track_halves_hex_and_hexside():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.ROUGH,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 tracks=[edge((0, 0), (1, 0))])
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 4 + 4


def test_track_does_not_halve_down_escarpment():
    # note-8 exception: a vehicle's Breakdown down an escarpment is NOT halved by a track.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.CLEAR,
                 hexsides={((0, 0), (1, 0)): Hexside.DOWN_ESCARPMENT},
                 tracks=[edge((0, 0), (1, 0))])
    # entry clear=4 halved to 2, escarpment 6 NOT halved.
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 2 + 6


def test_rainstorm_treats_road_as_track():
    # 29.56: in a rainstorm the road no longer negates; it halves like a track.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.ROUGH,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 roads=[edge((0, 0), (1, 0))])
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "clear") == 0.5
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "rain") == 4 + 4
