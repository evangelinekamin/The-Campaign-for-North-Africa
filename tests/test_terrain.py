"""Golden tests for the Terrain Effects Chart transcription (rule 8.37)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.terrain import (Hexside, Mobility, Terrain, hex_entry_cost,
                          hexside_cost, is_motorized, salt_marsh_barred)


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


def test_swamp_prohibits_off_road_entry_to_every_mobility_class():
    # The Swamp row's own spanned cell on [8.37] (NOT note 4, which is the fortification note --
    # see game/terrain.py): "May enter only on road or railroad", with no exception for foot units.
    assert hex_entry_cost(Terrain.SWAMP, Mobility.FOOT) is None
    assert hex_entry_cost(Terrain.SWAMP, Mobility.VEHICLE) is None


def test_salt_marsh_bars_only_the_vehicle_classes_844_names():
    """[8.44] (PDF p.15, restated by [8.37] chart note 2): "Vehicles, except for Light Trucks,
    Recce-type units, and motorcycle infantry may enter or leave a Salt Marsh hex only on a Road
    or Track." Foot and Camel are not vehicles -- and the Camel case is the rule's own last
    sentence ("travels as infantry in non-track Salt Marsh hexes"), satisfied because CAMEL pays
    the chart's non-Mot 3 CP."""
    assert salt_marsh_barred(Mobility.MOTORIZED)
    assert salt_marsh_barred(Mobility.VEHICLE)
    for exempt in (Mobility.LIGHT_TRUCK, Mobility.RECCE, Mobility.MOTORCYCLE):
        assert not salt_marsh_barred(exempt)
    assert not salt_marsh_barred(Mobility.FOOT)
    assert not salt_marsh_barred(Mobility.CAMEL)
    # The chart's own cells still stand behind the gate: the marsh is CHEAP for whoever may use it.
    assert hex_entry_cost(Terrain.SALT_MARSH, Mobility.FOOT) == 3
    assert hex_entry_cost(Terrain.SALT_MARSH, Mobility.LIGHT_TRUCK) == 2


def test_hexside_costs_and_prohibitions_match_chart():
    assert hexside_cost(Hexside.UP_ESCARPMENT, Mobility.FOOT) == 6
    assert hexside_cost(Hexside.UP_ESCARPMENT, Mobility.VEHICLE) is None  # 'P'
    assert hexside_cost(Hexside.MAJOR_RIVER, Mobility.VEHICLE) is None    # 'P'
    assert hexside_cost(Hexside.MINOR_RIVER, Mobility.FOOT) == 3
    assert hexside_cost(Hexside.MINOR_RIVER, Mobility.VEHICLE) == 6
    assert hexside_cost(Hexside.DOWN_SLOPE, Mobility.FOOT) == 1
