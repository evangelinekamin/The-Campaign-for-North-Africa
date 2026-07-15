"""The [7.2] Initiative Ratings chart (docs/rules/90:607-617), transcribed.

Each side adds its Initiative Rating to a die in the 7.14 determination; the higher total holds
the Initiative for all three Operations Stages of the game-turn (7.12). The two ratings are read
off DIFFERENT axes of the game state -- which is the whole story of the campaign's tempo:

  * The COMMONWEALTH rating is a function of the DATE. It climbs across the war as the Eighth
    Army grows: 3 on Game-Turns 1 thru 42, 4 on 43 thru 90, 5 on 91 thru 111.
  * The AXIS rating is a function of PRESENCE on the game-maps: 6 while General Rommel's counter
    is on the board, 3 with German land combat units but no Rommel, 1 with neither (the 1940
    Italians, alone). The chart footnote excludes the Tripoli/Tunisia Holding Boxes on Game-Map
    A from "the game-maps" for this purpose; this engine models no such Holding Box (a unit is
    either arrived/on-map or off-map awaiting its arrival_turn), so on-map is on-map, and a
    Rommel sent to Germany by the 31.5 recall is -- correctly -- not on the maps.

So, against a Commonwealth on 3, the 1940 Italians (rating 1) win the determination in only
6/32 = ~19% of decided rolls; the moment the Desert Fox lands (rating 6) the tempo inverts to
30/33 = ~91%; and it slackens again only as the Commonwealth rating climbs -- ~81% at 6-vs-4,
~68% at 6-vs-5. That inversion is the point of wiring the chart AND Rommel's arrival together:
the rating-6 row is dead paper until he reaches the board (rule 64.2, the 3rd OpStage of GT26).

This module is the transcription; game.engine._initiative applies it when the scenario opts in
(GameState.initiative_chart) and rolls the seeded 'initiative' stream. The Desert Fox benchmark
scenarios run a synthetic 1..12 clock rather than the real Game-Turns 26-37, so the DATE bands
do not describe them; they keep their flagged proxy ratings (game.scenario).
"""
from __future__ import annotations

from .events import Side
from .state import GameState

# [7.2], the three Commonwealth rows: (last game-turn of the band, inclusive; rating).
_COMMONWEALTH_BANDS: tuple[tuple[int, int], ...] = ((42, 3), (90, 4), (111, 5))


def commonwealth_rating(turn: int) -> int:
    """The Commonwealth Initiative Rating for a game-turn (the [7.2] date bands: 3 / 4 / 5)."""
    for last, rating in _COMMONWEALTH_BANDS:
        if turn <= last:
            return rating
    return _COMMONWEALTH_BANDS[-1][1]        # past GT111 (the game has ended): hold the last band


def _rommel_on_map(state: GameState) -> bool:
    """[7.2] / 31: General Rommel's counter stands on the game-maps -- he has arrived and the
    Berlin recall (31.5) has not sent him to Germany (which is not part of the game-maps)."""
    return state.rommel is not None and not state.rommel.in_germany


def _german_land_combat(state: GameState) -> bool:
    """[7.2]: any German land COMBAT unit stands on the game-maps. Formation 'GE ...' is the
    German nationality (the DAK, the 5th Light / 15th Panzer / 90th & 164th Light Divisions);
    is_combat drops the bare divisional HQs -- a headquarters is not a combat unit."""
    return any(u.formation.startswith("GE ") and u.is_combat
               for u in state.living(Side.AXIS))


def axis_rating(state: GameState) -> int:
    """The Axis Initiative Rating (the [7.2] presence rows): 6 with Rommel on the maps, 3 with
    German land combat units but no Rommel, 1 with neither."""
    if _rommel_on_map(state):
        return 6
    if _german_land_combat(state):
        return 3
    return 1
