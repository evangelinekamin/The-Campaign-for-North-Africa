"""C1-6: the campaign calendar (rule 64.2) and its binding to the weather clock.

GT1 is the THIRD WEEK of September 1940, so September holds two Game-Turns and every month from
October 1940 holds four, starting at GT3. The load-bearing test is the identity that ties the human
calendar to the engine's weather-season model: shifting the weather turn by CAMPAIGN_SEASON_OFFSET
makes the game-cadence season equal the calendar season on every campaign turn, so a campaign
scenario that stamps that offset onto GameState gets historically correct weather.

RESTATED 2026-07-22, NOT WEAKENED (rules of this port, 5). test_four_turns_to_a_month used to
assert GT1-4 September and GT5-8 October, which enshrined a naive four-turns-from-GT1 map that ran
TWO GAME-TURNS BEHIND the book from October 1940 onward. 64.2 prints "the third week of September,
1940 (1st OpStage of GameTurn 1)" and "the fourth week of March, 1941 (3rd OpStage of Game-Turn
26)", and the [34.86] schedule prints its own Game-Turn labels against its months on the scan (PDF
p.143, read with eyes): Sept IV = GT2, Oct I = GT3, Nov II = GT8, Dec I = GT11, Jan 1941 = GT15-18,
Sep 1941 = GT47-50, Dec 1942 = GT107-110. Those labels are the arbiter and they are asserted below.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import weather
from game.calendar import (CAMPAIGN_SEASON_OFFSET, FINAL_GT, gt_dateline,
                           gt_to_month, gt_to_season, is_month_start)


def test_anchor_and_span():
    assert gt_to_month(1) == (1940, 9)       # GT1 = the third week of September 1940 (64.2)
    assert gt_to_month(26) == (1941, 3)      # GT26 = the fourth week of March 1941 (64.2, verbatim)
    # GT111 is the campaign's last Game-Turn (64.2) and it falls in JANUARY 1943, one week past the
    # [34.86] schedule's last printed row ("Dec (GT 107...110)"). It used to read December 1942,
    # which was an artefact of the four-turn September this module no longer has.
    assert gt_to_month(FINAL_GT) == (1943, 1)
    assert gt_dateline(1) == "September 1940"


def test_the_chart_prints_its_own_game_turns():
    # [34.86] on scan PDF p.143 labels its rows with the Game-Turns they cover. Those labels ARE
    # the calendar, and every one of them must fall out of this module.
    assert gt_to_month(2) == (1940, 9)          # "Sept IV (GT 2)"
    assert {gt_to_month(gt) for gt in (3, 4, 5, 6)} == {(1940, 10)}      # "Oct I (GT 3)"
    assert gt_to_month(8) == (1940, 11)         # "Nov II (GT 8)"
    assert gt_to_month(11) == (1940, 12)        # "Dec I (GT 11)"
    assert {gt_to_month(gt) for gt in (15, 16, 17, 18)} == {(1941, 1)}   # "Jan (GT 15...18)"
    assert {gt_to_month(gt) for gt in (47, 48, 49, 50)} == {(1941, 9)}   # "Sep (GT 47...50)"
    assert {gt_to_month(gt) for gt in (107, 108, 109, 110)} == {(1942, 12)}  # "Dec (GT 107...110)"


def test_month_starts_follow_the_book_not_the_arithmetic():
    # The first Game-Turn of each month: GT1 (September opens mid-month), then GT3, 7, 11, ...
    assert [gt for gt in range(1, 20) if is_month_start(gt)] == [1, 3, 7, 11, 15, 19]


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
