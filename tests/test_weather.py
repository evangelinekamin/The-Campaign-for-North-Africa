"""Real weather (rule 29) — season -> the 29.61 Weather Table -> a weather type,
the 29.7 Foul Weather Location Table, and the movement/breakdown couplings (29.44 /
29.55 / 29.56). The 29.61 and 29.7 tables are bound to data/breakdown_rates.json (the
chart-of-record) so game.weather and the data cannot drift.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import weather
from game.combat_tables import expand
from game.events import Phase, Side
from game.movement import TerrainMap, breakdown_points, edge, step_cost
from game.state import GameState, StepRecord, Unit, VP
from game.terrain import Hexside, Mobility, Terrain

_BRK = json.load(open(os.path.join(
    os.path.dirname(__file__), "..", "data", "breakdown_rates.json")))


def _line(*coords, terrain, hexsides=None, roads=(), tracks=()):
    return TerrainMap(terrain={c: terrain for c in coords},
                      hexsides=hexsides or {},
                      roads=frozenset(roads), tracks=frozenset(tracks))


# --- season selection --------------------------------------------------------

def test_season_for_turn_matches_chart_of_record():
    ranges = _BRK["weather_table_29_61"]["season_game_turns"]
    for season, spans in ranges.items():
        if season.startswith("_"):
            continue
        for span in spans:
            lo, hi = (int(x) for x in span.split("-"))
            for turn in range(lo, hi + 1):
                assert weather.season_for_turn(turn) == season, (season, turn)


def test_season_cycles_on_a_48_turn_year():
    # Turn 1 and turn 49 are both the first Spring turn (the year recurs at +48).
    assert weather.season_for_turn(1) == weather.season_for_turn(49) == "spring"
    assert weather.season_for_turn(48) == weather.season_for_turn(96) == "winter"


# --- 29.61 Weather Table -----------------------------------------------------

def test_weather_table_matches_chart_of_record():
    table = _BRK["weather_table_29_61"]["by_season"]
    for season, row in table.items():
        if season.startswith("_"):
            continue
        for wtype, cell in row.items():
            for roll in expand("" if cell == "-" else cell):
                assert weather.weather_for_roll(season, roll) == wtype, (season, roll)


def test_every_season_row_partitions_all_36_rolls():
    all_rolls = expand("11-66")
    assert len(all_rolls) == 36
    for season in ("spring", "summer", "fall", "winter"):
        covered = [r for r in all_rolls if weather.weather_for_roll(season, r)]
        assert len(covered) == 36            # every legal 2d6 maps to exactly one type


def test_the_rulebook_29_1_worked_example():
    # 29.1: "a diceroll of 53 during summer results in Hot Weather."
    assert weather.weather_for_roll("summer", 53) == weather.HOT


def test_winter_has_no_hot_or_sandstorm():
    for roll in expand("11-66"):
        assert weather.weather_for_roll("winter", roll) in (weather.NORMAL, weather.RAINSTORM)


# --- 29.7 Foul Weather Location Table ----------------------------------------

def test_foul_location_matches_chart_of_record():
    table = _BRK["foul_weather_location_29_7"]["by_die"]
    for die_s, sections in table.items():
        if die_s.startswith("_"):
            continue
        assert weather.foul_sections(int(die_s)) == frozenset(sections)


def test_is_foul_only_for_storms():
    assert weather.is_foul("sandstorm") and weather.is_foul("rainstorm")
    assert not weather.is_foul("normal") and not weather.is_foul("hot")


# --- 29.56 rainstorm: road behaves as a track (CP and BP) --------------------

def test_rainstorm_road_as_track_for_cp():
    # A clear-hex road step: dry = ROAD_ENTRY (1/2), rained = TRACK_ENTRY (1).
    tmap = _line((0, 0), (1, 0), terrain=Terrain.CLEAR, roads=[edge((0, 0), (1, 0))])
    dry = step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "normal")
    wet = step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "rainstorm")
    assert dry == 0.5 and wet == 1.0            # 29.56: the road is now a track


def test_rainstorm_road_as_track_for_breakdown():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.ROUGH, roads=[edge((0, 0), (1, 0))])
    dry = breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "normal")
    wet = breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "rainstorm")
    assert dry == 0.5                            # note 6: dry road's own 1/2 BV
    assert wet == 8 / 2                           # note 8: rained road halves the rough BV


# --- 29.55 rainstorm: wadi hexsides uncrossable except by road ---------------

def test_rainstorm_closes_a_wadi_hexside():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.CLEAR,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI})
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "normal") is not None
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "rainstorm") is None


def test_rainstorm_wadi_still_crossable_by_road():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.CLEAR,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 roads=[edge((0, 0), (1, 0))])
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "rainstorm") is not None


# --- 29.44 sandstorm: movement costs doubled ---------------------------------

def test_sandstorm_doubles_movement_cost():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.DESERT)   # mot entry 4
    dry = step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "normal")
    storm = step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "sandstorm")
    assert storm == dry * 2 == 8                            # 29.44


def test_normal_weather_is_byte_identical_to_the_dry_chart():
    # The whole point of the coupling: Normal/Hot leave movement untouched.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.ROUGH,
                 hexsides={((0, 0), (1, 0)): Hexside.DOWN_SLOPE},
                 tracks=[edge((0, 0), (1, 0))])
    base = step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE)          # default "normal"
    for w in ("normal", "hot"):
        assert step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE, w) == base


# --- 21.37 / 29.33 hot weather measurably raises breakdown -------------------

def _breakdown_state(weather_label: str, seed: int) -> GameState:
    # A tank with BAR -1 accumulating 8 BP sits in the 4-10 column shifted one LEFT by
    # its BAR (21.32) -- below the breakdown floor (21.33), so it NEVER breaks under
    # Normal weather. Hot weather's +1R column shift (21.37) lifts it back into the
    # 4-10 column, where some rolls break. So the ONLY difference is the weather.
    tank = Unit("T1", Side.AXIS, (0, 0), (StepRecord("tank", 10),),
                mobility=Mobility.VEHICLE, cpa=20, stacking_points=1, oca=4, dca=3,
                barrage=0, anti_armor=5, armor_protection=6, is_tank=True,
                bar=-1, bp_accumulated=8.0)
    tmap = TerrainMap(terrain={(0, 0): Terrain.DESERT})
    return GameState(turn=1, max_turns=9, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                     seed=seed, weather=weather_label, vp=VP(), terrain=tmap, control={},
                     units=(tank,), target_hex=(0, 0), supplies=(), consumed={},
                     initial_supply={})


def _total_broken(weather_label: str) -> int:
    from game.engine import _Run, _breakdown
    total = 0
    for seed in range(1, 41):
        r = _Run(_breakdown_state(weather_label, seed))
        _breakdown(r, Side.AXIS)
        total += r.state.unit("T1").broken_down
    return total


def test_hot_weather_measurably_raises_breakdown():
    normal = _total_broken("normal")
    hot = _total_broken("hot")
    assert normal == 0                 # BAR -1 at the 4-10 band is below the 21.33 floor
    assert hot > 0                     # the 29.33/21.37 +1R shift lifts it into breakdown range
