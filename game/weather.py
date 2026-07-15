"""Weather determination (rule 29): season -> the 29.61 Weather Table -> a weather
type, and, for a foul result, the 29.7 Foul Weather Location Table -> the affected
map sections.

Pure. The engine (game.engine._weather) rolls the dice; the theatre-wide TYPE folds into
GameState.weather and, for a foul result, the covered sections into GameState.storm_sections.
Normal and Hot fall on EVERY section (29.2 / 29.31), so their couplings read the scalar
`weather` directly; a Sandstorm/Rainstorm falls on only 2-3 sections (29.7), so its couplings
ask GameState.weather_at(hex) for the weather in that hex's section:
  - hot / sandstorm  -> +1 Breakdown column (combat_tables.weather_breakdown_shift, 21.37)
  - hot              -> +5% Fuel/Water evaporation (engine._evaporate, 29.34 / 49.3 / 52.44)
  - sandstorm        -> doubled Movement Cost (movement.step_cost, 29.44)
  - rainstorm        -> Road treated as Track for CP and BP, wadi hexsides uncrossable
                        (movement.step_cost / movement.breakdown_points, 29.55 / 29.56)
  - rainstorm        -> depleted wells refilled (engine._well_refill, 29.53 / 52.15)
  - foul             -> no construction (24.22), no field repair (22.13d), no air (29.43/29.52)

The four weather types are the rulebook's own: {normal, hot, sandstorm, rainstorm}
(29.0). The tables below are transcribed from data/breakdown_rates.json (the chart-
of-record) and bound to it by test_weather so code and data cannot drift; the 29.61
table was RECOVERED off the scan (PDF page 101) because the OCR scrambled it.
"""
from __future__ import annotations

from .combat_tables import expand   # the canonical sequential-2d6 range parser (11..66)

NORMAL = "normal"
HOT = "hot"
SANDSTORM = "sandstorm"
RAINSTORM = "rainstorm"
_TYPES = (NORMAL, HOT, SANDSTORM, RAINSTORM)
_FOUL = frozenset({SANDSTORM, RAINSTORM})

# [29.61] WEATHER TABLE (RECOVERED from PDF page 101; the docs/rules/90 OCR was
# incoherent). Each season row partitions the sequential 2d6 roll (11..66) among the
# four weather types; a '' cell means that weather never occurs that season. Bound to
# data/breakdown_rates.json.weather_table_29_61 by test_weather.
_WEATHER_TABLE: dict[str, dict[str, str]] = {
    "spring": {NORMAL: "11-42", HOT: "43-55", SANDSTORM: "56-64", RAINSTORM: "65-66"},
    "summer": {NORMAL: "11-23", HOT: "24-55", SANDSTORM: "56-66", RAINSTORM: ""},
    "fall":   {NORMAL: "11-35", HOT: "36-54", SANDSTORM: "55-61", RAINSTORM: "62-66"},
    "winter": {NORMAL: "11-52", HOT: "",      SANDSTORM: "",      RAINSTORM: "53-66"},
}

# [29.7] FOUL WEATHER LOCATION TABLE (docs/rules/90; PDF page 103). After a Sandstorm/
# Rainstorm result, one die names the affected map sections; unaffected sections have
# Normal Weather. Bound to data/breakdown_rates.json.foul_weather_location_29_7.
_FOUL_LOCATION: dict[int, frozenset[str]] = {
    1: frozenset("AB"),
    2: frozenset("CD"),
    3: frozenset("DE"),
    4: frozenset("BC"),
    5: frozenset("BD"),
    6: frozenset("BCD"),
}

# Season length is a 48-Game-Turn year, each year Spring/Summer/Fall/Winter in equal
# twelve-turn quarters (data/breakdown_rates.json.season_game_turns: 1-12 spring,
# 13-24 summer, 25-36 fall, 37-48 winter, recurring at +48). The modular formula below
# reproduces every listed range exactly (bound by test_weather) and extends past the
# tabulated turns for a hypothetical long campaign.
_SEASON_BY_QUARTER = ("spring", "spring", "spring",       # turns 1-12
                      "summer", "summer", "summer",       # turns 13-24
                      "fall", "fall", "fall",             # turns 25-36
                      "winter", "winter", "winter")       # turns 37-48


def season_for_turn(turn: int) -> str:
    """The season a Game-Turn falls in (29.1). Turns recur on a 48-turn year anchored
    at turn 1 = Spring."""
    return _SEASON_BY_QUARTER[((turn - 1) % 48) // 4]


def weather_for_roll(season: str, roll: int) -> str:
    """Rule 29.61: the weather type for a sequential-2d6 `roll` (11..66) in `season`.
    Returns one of {normal, hot, sandstorm, rainstorm}."""
    row = _WEATHER_TABLE[season]
    for wtype in _TYPES:
        if roll in expand(row[wtype]):
            return wtype
    return NORMAL          # defensive: the row partitions all 36 rolls (test_weather)


def foul_sections(die: int) -> frozenset[str]:
    """Rule 29.7: the map sections a foul-weather result covers, from one die."""
    return _FOUL_LOCATION[die]


# [29.41] A Sandstorm "never occurs over delta hexes (Game-Map E)" even when the 29.7 die names
# them; a Rainstorm DOES reach the delta (29.51 / 29.58). Map E is the Nile delta section.
DELTA = "E"


def affected_sections(label: str, die: int, theater: frozenset) -> frozenset[str]:
    """The sections a foul `label` (rolled `die` on the 29.7 table) actually covers within
    `theater` -- the localised storm. Sections outside the theatre read Normal (29.1); a
    Sandstorm is stripped of the delta (Map E, 29.41), a Rainstorm keeps it (29.51). An empty
    result means the storm missed the theatre entirely, so the stage is Normal everywhere (29.1)."""
    hit = _FOUL_LOCATION[die] & theater
    if label == SANDSTORM:
        hit = hit - {DELTA}                        # 29.41: sandstorms never fall on the delta
    return hit


def is_foul(label: str) -> bool:
    """A Sandstorm or Rainstorm -- the results that consult the 29.7 location table."""
    return label in _FOUL
