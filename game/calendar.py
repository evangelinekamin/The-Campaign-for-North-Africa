"""The campaign calendar (rule 64.2).

The full Campaign for North Africa opens on the THIRD WEEK of September 1940 (Game-Turn 1) and runs
to Game-Turn 111 -- roughly two years, one Game-Turn to a week, four Game-Turns to a calendar month.

⚠ SEPTEMBER 1940 IS TWO GAME-TURNS LONG, AND THAT IS THE BOOK'S OWN CLOCK, CORRECTED 2026-07-22.
64.2 verbatim: the campaign "begins in the third week of September, 1940 (i.e., the Italian
Offensive, 1st OpStage of GameTurn 1)... The 'shorter' campaign begins with the arrival of General
Erwin Rommel and the Deutsches Afrika Korps during the FOURTH WEEK OF MARCH, 1941 (i.e., the Desert
Fox, 3rd OpStage of GAME-TURN 26)." A month of four weeks that starts at its THIRD week has only two
Game-Turns in it, so the first WHOLE month is October 1940 and it opens on Game-Turn 3 -- and the
[34.86] Commonwealth Airplane Reinforcement Schedule prints that arithmetic on its own face (scan
PDF p.143, rendered and read with eyes): "Sept IV (GT 2)", "Oct I (GT 3)", "Nov II (GT 8)", "Dec I
(GT 11)", "1941, Jan (GT 15...18)", "Sep (GT 47...50)", "Dec (GT 107...110)". Every one of those
labels falls out of `two turns of September, then four to a month from Game-Turn 3`, and Rommel's
fourth week of March 1941 lands on Game-Turn 26 exactly. It was previously a naive four-turns-from-
Game-Turn-1 map, which put the engine's month TWO GAME-TURNS BEHIND the book's own labels from
October 1940 onward (engine October = GT5-8 against the chart's GT3-6) -- two clocks, and rule 44
was the first thing in the engine to stand on both at once.

Twelve Game-Turns make a season and forty-eight a year: the same cadence the weather model uses
(game.weather runs on 4-turn quarters, 12-turn seasons), so a campaign that shifts the weather clock
by CAMPAIGN_SEASON_OFFSET reads the historically correct season on every turn. That identity --
weather.season_for_turn(gt + CAMPAIGN_SEASON_OFFSET) == gt_to_season(gt) -- is pinned by
tests/test_calendar.py, and the offset moved with the anchor.

The engine keeps counting bare Game-Turns; this module is the read-only human-facing
projection (a September-1940 dateline for the war diary, the season the campaign
scenario stamps onto GameState.season_offset).
"""
from __future__ import annotations

CAMPAIGN_START: tuple[int, int] = (1940, 9)   # (year, month) of Game-Turn 1 (64.2)
GT_PER_MONTH: int = 4                          # 1 Game-Turn ~ 1 week; 4 to a month
FINAL_GT: int = 111                            # the campaign ends on GT111.3 (64.2)

# 64.2: Game-Turn 1 is the THIRD week of September 1940, so September holds Game-Turns 1-2 and the
# first Game-Turn of the first whole month (October 1940) is Game-Turn 3. The [34.86] schedule's
# own printed labels are the proof (see the module docstring).
FIRST_WHOLE_MONTH_GT: int = 3
FIRST_WHOLE_MONTH: tuple[int, int] = (1940, 10)

# Weather-clock shift for the campaign: the weather season model (game.weather) anchors
# its own Game-Turn 1 to spring, but the campaign's Game-Turn 1 is September 1940 (fall).
# Adding this offset to the turn fed to weather.season_for_turn makes the game-cadence
# season match the calendar season for every campaign turn (proven in test_calendar.py).
# 26 rather than 24 since 2026-07-22: the calendar anchor moved two Game-Turns when 64.2's
# two-week September was implemented, and the weather clock follows the calendar, not the reverse.
CAMPAIGN_SEASON_OFFSET: int = 26

_MONTHS = ("January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December")

# Meteorological seasons, Northern hemisphere (the North African theatre).
_MONTH_SEASON = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "fall", 10: "fall", 11: "fall",
}


def gt_to_month(gt: int) -> tuple[int, int]:
    """The (year, month) a Game-Turn falls in, anchored at GT1 = the third week of September 1940
    (64.2). month is 1-12. September 1940 is two Game-Turns long; every month from October 1940 is
    four, starting at FIRST_WHOLE_MONTH_GT -- see the module docstring for the [34.86] labels that
    prove it."""
    if gt < 1:
        raise ValueError(f"game-turn must be >= 1, got {gt}")
    if gt < FIRST_WHOLE_MONTH_GT:
        return CAMPAIGN_START
    months_elapsed = (gt - FIRST_WHOLE_MONTH_GT) // GT_PER_MONTH
    year0, month0 = FIRST_WHOLE_MONTH
    absolute = (month0 - 1) + months_elapsed
    return year0 + absolute // 12, absolute % 12 + 1


def is_month_start(gt: int) -> bool:
    """Is this Game-Turn the FIRST of its calendar month -- the beat a monthly allotment lands on?

    Game-Turn 1 opens September 1940 mid-month (64.2), and every whole month from October 1940
    opens on FIRST_WHOLE_MONTH_GT + 4k. Callers used to spell this `(gt - 1) % GT_PER_MONTH == 0`,
    which was the same thing only while the calendar wrongly gave September four Game-Turns."""
    return gt == 1 or (gt >= FIRST_WHOLE_MONTH_GT
                       and (gt - FIRST_WHOLE_MONTH_GT) % GT_PER_MONTH == 0)


def month_turns(gt: int) -> tuple[int, ...]:
    """Every Game-Turn of the calendar month `gt` falls in, in order.

    Four of them for a whole month; TWO for September 1940, which the campaign joins at its third
    week (64.2). A monthly allotment divided "as evenly as possible amongst the weeks" (34.84, and
    54.34's railroad month) must be divided amongst the weeks THE MONTH ACTUALLY HAS -- spreading
    September's over four would spill it into October. ([56.5]'s convoy tonnage is NOT such an
    allotment and no longer calls this: 56.21 grants the whole row PER GAME-TURN, and the month
    only selects the row -- see scenario._campaign_convoys.)"""
    if gt < FIRST_WHOLE_MONTH_GT:
        return tuple(range(1, FIRST_WHOLE_MONTH_GT))
    first = gt - (gt - FIRST_WHOLE_MONTH_GT) % GT_PER_MONTH
    return tuple(range(first, first + GT_PER_MONTH))


def gt_to_season(gt: int) -> str:
    """The calendar season a Game-Turn falls in (spring/summer/fall/winter), from its
    month. Bound to the engine's weather season by CAMPAIGN_SEASON_OFFSET."""
    _, month = gt_to_month(gt)
    return _MONTH_SEASON[month]


def gt_dateline(gt: int) -> str:
    """A human dateline for the war diary, e.g. 'September 1940'. Month granularity: the
    4-Game-Turn month is the finest unit the calendar commits to (rule 64.2's "third week
    of September" is the historical opening; the game clock runs on whole-month quarters)."""
    year, month = gt_to_month(gt)
    return f"{_MONTHS[month - 1]} {year}"
