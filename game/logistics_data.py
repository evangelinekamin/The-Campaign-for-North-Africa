"""Load the faithful logistics magnitudes from data/logistics_rates.json.

This mirrors how game.oob loads data/unit_stats.json: a thin, cached reader that
turns the transcribed rulebook charts into the constants the supply/engine code
consumes, so the balance is the RULEBOOK'S (one source of truth) rather than magic
numbers scattered through game/*.py. Each accessor cites the chart it draws from.

WIRED FAITHFULLY here (magnitudes now equal to the chart values):
  - [50.2] Ammunition Consumption Rates -- barrage 4, anti-armor 3, close-assault 2.
  - 51.11/51.13 Stores -- 4 per TOE (combat), 1 per TOE (HQ/engineer/non-combat).
  - [49.3]/52.44 Fuel & Water evaporation -- 6% base, +5% hot.
  - [54.12] Supply Dump Capacity (Other-Terrain ceilings) and the Major-City U.

([54.5] Equivalent Weights stay as exact fractions in supply.TONS_PER_POINT: the
data file rounds Water to 0.1667, so sourcing it here would inject a rounding error
into the conservation math -- they are exact-faithful already.)

STILL PROXY (recorded here as the engine_proxy the chart replaces, and FLAGGED for
the CHUNK-4 real-scale fork): the per-mobility Fuel Rate (flat 2/1 instead of the
per-model [4.47-4.49] rates 1-7) and the omitted x TOE-strength fuel factor (49.13).
Those two are coupled to a real-scale rescale of the dump/convoy/port RESERVOIRS
(their per-point magnitudes are ~1-2 orders of magnitude below [54.12]); wiring the
fuel magnitude alone against proxy-scale dumps would make scarcity incoherent, so it
is deliberately left for the coordinated rescale. See data/logistics_rates.json
scale_observation and this task's scale_decision.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from .terrain import Mobility

_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "logistics_rates.json"))


@lru_cache(maxsize=1)
def _data() -> dict:
    with open(_PATH) as f:
        return json.load(f)


def ammo_rates() -> dict:
    """[50.2] Ammunition Consumption Rates (Ammo Points per TOE Strength Point using
    the function, rule 50.14), keyed by the activity string the engine passes. The
    'assault' key carries the chart's close_assault rate."""
    played = _data()["ammunition_consumption"]["logistics_game_played"]
    return {
        "barrage": played["barrage"],            # 4
        "anti_armor": played["anti_armor"],      # 3
        "assault": played["close_assault"],      # 2 (close assault)
    }


def stores_rates() -> dict:
    """51.11/51.13 Stores per TOE Strength Point per Game-Turn: combat units 4, HQ /
    engineer / non-combat 1."""
    s = _data()["stores_consumption"]
    return {"combat": s["per_toe_strength_point_per_game_turn"],
            "noncombat": s["hq_or_engineer_per_game_turn"]}


def evaporation_percent() -> dict:
    """[49.3]/52.44 Fuel & Water evaporation: 6% base per Game-Turn, +5% in hot
    weather (rounded down)."""
    e = _data()["fuel_consumption"]["evaporation_49_3"]
    return {"base": e["base_percent_per_game_turn"],
            "hot_additional": e["hot_weather_additional_percent"]}


def dump_other_terrain_cap() -> dict:
    """[54.12] Supply Dump Capacity Chart, the Other-Terrain row (the ceiling a
    non-city dump hex may hold), keyed by engine commodity name."""
    row = _data()["supply_dump_capacity_54_12"]["other_terrain"]
    return {"AMMO": row["ammo"], "FUEL": row["fuel"],
            "STORES": row["stores"], "WATER": row["water"]}


def fuel_rate_proxy() -> dict:
    """PROXY (flagged): the per-mobility-class Fuel Consumption Rate the engine uses
    until the per-model [4.47-4.49] rates and the 49.13 x-strength factor land with the
    real-scale reservoir rescale (CHUNK 4). Recorded in the data file's engine_proxy
    block so the proxy has a single, documented home."""
    by_name = _data()["fuel_consumption"]["engine_proxy"]["fuel_rate_by_mobility"]
    return {Mobility[name]: rate for name, rate in by_name.items()}
