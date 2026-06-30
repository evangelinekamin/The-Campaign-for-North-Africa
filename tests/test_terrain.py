"""Golden tests for the Terrain Effects Chart transcription (rule 8.37)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.terrain import (Hexside, Mobility, Terrain, hex_entry_cost,
                          hexside_cost, is_motorized)


def test_motorization_classification():
    assert not is_motorized(Mobility.FOOT)
    assert not is_motorized(Mobility.CAMEL)
    assert is_motorized(Mobility.MOTORIZED)
    assert is_motorized(Mobility.VEHICLE)
    assert is_motorized(Mobility.LIGHT_TRUCK)


def test_hex_entry_costs_match_chart():
    assert hex_entry_cost(Terrain.CLEAR, Mobility.FOOT) == 2
    assert hex_entry_cost(Terrain.CLEAR, Mobility.VEHICLE) == 2
    assert hex_entry_cost(Terrain.DESERT, Mobility.FOOT) == 3
    assert hex_entry_cost(Terrain.DESERT, Mobility.VEHICLE) == 4
    assert hex_entry_cost(Terrain.MOUNTAIN, Mobility.VEHICLE) == 6
    assert hex_entry_cost(Terrain.MAJOR_CITY, Mobility.VEHICLE) == 0.5


def test_hexside_costs_and_prohibitions_match_chart():
    assert hexside_cost(Hexside.UP_ESCARPMENT, Mobility.FOOT) == 6
    assert hexside_cost(Hexside.UP_ESCARPMENT, Mobility.VEHICLE) is None  # 'P'
    assert hexside_cost(Hexside.MAJOR_RIVER, Mobility.VEHICLE) is None    # 'P'
    assert hexside_cost(Hexside.MINOR_RIVER, Mobility.FOOT) == 3
    assert hexside_cost(Hexside.MINOR_RIVER, Mobility.VEHICLE) == 6
    assert hexside_cost(Hexside.DOWN_SLOPE, Mobility.FOOT) == 1
