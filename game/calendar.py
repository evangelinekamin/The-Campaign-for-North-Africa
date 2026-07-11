"""The campaign calendar (rule 64.2).

The full Campaign for North Africa opens on the third week of September 1940
(Game-Turn 1) and runs to Game-Turn 111 -- roughly two years, one Game-Turn to a
week. Four Game-Turns make a calendar month, twelve a season, forty-eight a year:
the same cadence the weather model already uses (game.weather runs on 4-turn
quarters, 12-turn seasons), so a campaign that shifts the weather clock by
CAMPAIGN_SEASON_OFFSET reads the historically correct season on every turn. That
identity -- weather.season_for_turn(gt + CAMPAIGN_SEASON_OFFSET) == gt_to_season(gt)
-- is pinned by tests/test_calendar.py.

The engine keeps counting bare Game-Turns; this module is the read-only human-facing
projection (a September-1940 dateline for the war diary, the season the campaign
scenario stamps onto GameState.season_offset).
"""
from __future__ import annotations

CAMPAIGN_START: tuple[int, int] = (1940, 9)   # (year, month) of Game-Turn 1 (64.2)
GT_PER_MONTH: int = 4                          # 1 Game-Turn ~ 1 week; 4 to a month
FINAL_GT: int = 111                            # the campaign ends on GT111.3 (64.2)

# Weather-clock shift for the campaign: the weather season model (game.weather) anchors
# its own Game-Turn 1 to spring, but the campaign's Game-Turn 1 is September 1940 (fall).
# Adding this offset to the turn fed to weather.season_for_turn makes the game-cadence
# season match the calendar season for every campaign turn (proven in test_calendar.py).
CAMPAIGN_SEASON_OFFSET: int = 24

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
    """The (year, month) a Game-Turn falls in, anchored at GT1 = September 1940 (64.2).
    month is 1-12. Four Game-Turns to a month."""
    if gt < 1:
        raise ValueError(f"game-turn must be >= 1, got {gt}")
    months_elapsed = (gt - 1) // GT_PER_MONTH
    year0, month0 = CAMPAIGN_START
    absolute = (month0 - 1) + months_elapsed
    return year0 + absolute // 12, absolute % 12 + 1


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
