"""[22.3] Facility Repairs -- the pure helpers in game.repair, bound to their chart-of-record
(data/breakdown_rates.json) and to the OWNER RULING on the 22.34a die-modifier footnote (see
scratchpad/port/transcriptions/22.3-cw-rear-area-recovery.md section 5).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords
from game import combat_tables as ct
from game import repair
from game.events import Phase, Side
from game.movement import TerrainMap
from game.state import GameState, SupplyUnit, VP
from game.terrain import Terrain

_BRK = json.load(open(os.path.join(
    os.path.dirname(__file__), "..", "data", "breakdown_rates.json")))


def _blank_state(*, terrain=None, supplies=()) -> GameState:
    tmap = terrain or TerrainMap(terrain={})
    return GameState(turn=1, max_turns=9, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                     seed=1, weather="clear", vp=VP(), terrain=tmap,
                     control={}, units=(), target_hex=(0, 0), supplies=tuple(supplies),
                     consumed={}, initial_supply={})


# --- major_facility_hexes ----------------------------------------------------

def test_includes_alexandria_cairo_and_tobruk():
    hexes = repair.major_facility_hexes(_blank_state())
    for label in ("E3613", "E3714", "E1730", "E1829", "E1830", "E1930", "E1931", "C4807"):
        assert coords.to_axial(coords.parse(label)) in hexes, label


def test_excludes_tripoli_without_an_on_map_proxy():
    # game.scenario.campaign() seeds no AX-Tripoli proxy -- Tripoli stays off-map (8.81/8.88).
    hexes = repair.major_facility_hexes(_blank_state())
    assert len(hexes) == 8                              # 2 Alexandria + 5 Cairo + 1 Tobruk, no Tripoli


def test_includes_tripoli_proxy_when_a_scenario_seeds_one():
    dump = SupplyUnit("AX-Tripoli", Side.AXIS, (9, 9), ammo=0, fuel=100)
    hexes = repair.major_facility_hexes(_blank_state(supplies=(dump,)))
    assert (9, 9) in hexes
    assert len(hexes) == 9


# --- facility_die_modifier (22.34a, the chart-vs-prose owner ruling) ---------

_HEX = (0, 0)


def _terrain(baseline: int) -> TerrainMap:
    return TerrainMap(terrain={_HEX: Terrain.MAJOR_CITY}, fortifications={_HEX: baseline})


def test_zero_outside_a_major_city():
    st = _blank_state(terrain=TerrainMap(terrain={_HEX: Terrain.CLEAR}))
    assert repair.facility_die_modifier(st, _HEX) == 0


def test_zero_when_undamaged_at_level_3():
    st = _blank_state(terrain=_terrain(3))
    assert repair.facility_die_modifier(st, _HEX) == 0


def test_plus_one_when_a_level_3_city_is_reduced_by_one():
    st = replace(_blank_state(terrain=_terrain(3)), fort_levels={_HEX: 2})
    assert repair.facility_die_modifier(st, _HEX) == 1


def test_plus_two_when_a_level_3_city_is_reduced_by_two_or_three():
    for current in (1, 0):
        st = replace(_blank_state(terrain=_terrain(3)), fort_levels={_HEX: current})
        assert repair.facility_die_modifier(st, _HEX) == 2, current


def test_undamaged_level_2_city_gets_no_modifier():
    # THE RULING: the chart's own footnote shorthand ("at present two" -> +1) would wrongly
    # penalise an undamaged Level-2 city (Tobruk/Bardia/Benghazi/Helwan) that was never
    # bombed. Rule 22.34a's prose ("if the Enemy succeeds in REDUCING...") wins.
    st = _blank_state(terrain=_terrain(2))
    assert repair.facility_die_modifier(st, _HEX) == 0


def test_level_2_city_reduced_by_one_gets_plus_one():
    st = replace(_blank_state(terrain=_terrain(2)), fort_levels={_HEX: 1})
    assert repair.facility_die_modifier(st, _HEX) == 1


def test_level_2_city_reduced_to_zero_gets_plus_two():
    st = replace(_blank_state(terrain=_terrain(2)), fort_levels={_HEX: 0})
    assert repair.facility_die_modifier(st, _HEX) == 2


# --- facility_repaired_count (22.34/22.25) -----------------------------------

def test_rounds_fractions_up():
    assert repair.facility_repaired_count(33, 8) == 3    # ceil(2.64) = 3
    assert repair.facility_repaired_count(50, 8) == 4


def test_single_toe_ignores_a_ten_percent_result():
    assert repair.facility_repaired_count(10, 1) == 0     # 22.25 single-TOE exception
    assert repair.facility_repaired_count(10, 2) == 1      # ceil(0.2) = 1, exception does not apply


def test_zero_broken_repairs_nothing():
    assert repair.facility_repaired_count(75, 0) == 0


def test_never_exceeds_the_broken_pool():
    assert repair.facility_repaired_count(75, 3) == 3


# --- combat_tables.facility_repair, bound to the chart of record -------------

def test_facility_repair_table_matches_chart_of_record():
    by_die = _BRK["broken_down_vehicle_repair_22_8"]["by_die"]
    for die_str, row in by_die.items():
        die = int(die_str)
        assert ct.facility_repair("temporary", die) == int(row[3].rstrip("%*"))
        assert ct.facility_repair("major", die) == int(row[4].rstrip("%*"))


def test_facility_repair_clamps_outside_the_charted_range():
    assert ct.facility_repair("major", -3) == ct.facility_repair("major", 0)
    assert ct.facility_repair("major", 20) == ct.facility_repair("major", 8)
