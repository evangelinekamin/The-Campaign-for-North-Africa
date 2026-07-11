"""C1-6: the campaign calendar (rule 64.2) and its binding to the weather clock.

GT1 is September 1940; four Game-Turns to a month. The load-bearing test is the
identity that ties the human calendar to the engine's weather-season model: shifting
the weather turn by CAMPAIGN_SEASON_OFFSET makes the game-cadence season equal the
calendar season on every campaign turn, so a campaign scenario that stamps that offset
onto GameState gets historically correct weather.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import weather
from game.calendar import (CAMPAIGN_SEASON_OFFSET, FINAL_GT, gt_dateline,
                           gt_to_month, gt_to_season)


def test_anchor_and_span():
    assert gt_to_month(1) == (1940, 9)       # GT1 = September 1940 (64.2)
    assert gt_to_month(26) == (1941, 3)      # GT26 = March 1941 (Desert Fox opens)
    assert gt_to_month(FINAL_GT) == (1942, 12)  # GT111 = December 1942, campaign's end
    assert gt_dateline(1) == "September 1940"


def test_four_turns_to_a_month():
    # GT1-4 September, GT5-8 October: the month advances every fourth Game-Turn.
    assert {gt_to_month(gt) for gt in (1, 2, 3, 4)} == {(1940, 9)}
    assert {gt_to_month(gt) for gt in (5, 6, 7, 8)} == {(1940, 10)}


def test_season_from_calendar():
    assert gt_to_season(1) == "fall"         # September
    assert gt_to_season(26) == "spring"      # March
    assert gt_to_season(40) == "summer"      # June 1941
    assert gt_to_season(16) == "winter"      # December 1940


def test_weather_clock_matches_calendar_every_campaign_turn():
    # The invariant that makes CAMPAIGN_SEASON_OFFSET correct: the engine's weather
    # season (fed turn + offset) equals the calendar season for all GT1..111.
    for gt in range(1, FINAL_GT + 1):
        assert weather.season_for_turn(gt + CAMPAIGN_SEASON_OFFSET) == gt_to_season(gt), \
            f"weather/calendar season disagree at GT{gt}"


def test_gt_must_be_positive():
    import pytest
    with pytest.raises(ValueError):
        gt_to_month(0)


def _minimal_state(season_offset: int):
    from game.events import Phase, Side
    from game.movement import TerrainMap
    from game.state import VP, GameState
    from game.terrain import Terrain
    tmap = TerrainMap(terrain={(0, 0): Terrain.CLEAR})
    return GameState(turn=1, max_turns=9, phase=Phase.WEATHER, active_side=Side.AXIS,
                     seed=1, weather="normal", vp=VP(), terrain=tmap, control={},
                     units=(), target_hex=(0, 0), supplies=(), consumed={},
                     initial_supply={}, season_offset=season_offset)


def test_engine_weather_reads_season_offset():
    # The wiring test: GameState.season_offset must reach the engine's Weather
    # Determination. Turn 1 reads spring with no offset (the local-clock default) and the
    # campaign's fall once the campaign offset is stamped on -- matching gt_to_season(1).
    from game.engine import _Run, _weather
    from game.events import EventKind

    def season_of(offset: int) -> str:
        r = _Run(_minimal_state(offset))
        _weather(r)
        rolled = [e for e in r.events if e.kind == EventKind.WEATHER_ROLLED]
        return rolled[-1].payload["season"]

    assert season_of(0) == "spring"
    assert season_of(CAMPAIGN_SEASON_OFFSET) == "fall" == gt_to_season(1)
