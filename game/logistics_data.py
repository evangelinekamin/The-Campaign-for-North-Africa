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
  - [49.13]/[4.47-4.49] per-model Fuel Consumption Rate (fuel_rate_by_model) -- now
    wired onto Unit.fuel_rate (game.oob) with the x TOE-strength law (game.supply.
    fuel_cost). This is the Regime-B FULL-LOGISTICS fuel demand.
  - 61.44/61.36 real-scale Desert Fox dump pools + 55.3 per-port supply tonnage --
    the reservoir the real fuel demand draws on (game.oob / game.scenario).

([54.5] Equivalent Weights stay as exact fractions in supply.TONS_PER_POINT: the
data file rounds Water to 0.1667, so sourcing it here would inject a rounding error
into the conservation math -- they are exact-faithful already.)

STILL PROXY: the per-MOBILITY Fuel Rate (fuel_rate_proxy, flat 2/1) survives only as
the fallback for scenarios whose units carry no transcribed Unit.fuel_rate (the toy
coastal corridor); the real Desert Fox OOB now uses the per-model chart above.
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


def _dump_cap_row(name: str) -> dict:
    """One row of the [54.12] Supply Dump Capacity Chart, keyed by engine commodity name."""
    row = _data()["supply_dump_capacity_54_12"][name]
    return {"AMMO": row["ammo"], "FUEL": row["fuel"],
            "STORES": row["stores"], "WATER": row["water"]}


def dump_other_terrain_cap() -> dict:
    """[54.12] Supply Dump Capacity Chart, the Other-Terrain row (the ceiling a
    non-city dump hex may hold), keyed by engine commodity name."""
    return _dump_cap_row("other_terrain")


def dump_village_cap() -> dict:
    """[54.12] Supply Dump Capacity Chart, the VILLAGE row -- the ceiling a dump in a village
    hex may hold (2,500 Ammo / 8,000 Fuel / 3,000 Stores / 1,000 Water). Between the Major-City
    row (unlimited) and Other Terrain. See game.villages for which hexes carry a village."""
    return _dump_cap_row("village")


def fuel_rate_proxy() -> dict:
    """PROXY fallback: the per-mobility-class Fuel Consumption Rate used only for units
    that carry no transcribed Unit.fuel_rate (the toy coastal-corridor scenario). The
    real Desert Fox OOB carries the per-model rate from fuel_rate_by_model(). Recorded
    in the data file's engine_proxy block so the proxy has a single, documented home."""
    by_name = _data()["fuel_consumption"]["engine_proxy"]["fuel_rate_by_mobility"]
    return {Mobility[name]: rate for name, rate in by_name.items()}


def fuel_rate_by_model() -> dict:
    """[49.13]/[4.47-4.49] per-model Fuel Consumption Rate, flattened from the three
    tank Characteristics sub-charts (german_tank / commonwealth_tank / italian_tank)
    into a single {model_name: rate} map. Model names mirror data/unit_stats.json
    'models'. The gun/SP scalars in the same chart are role-level defaults (they are
    not per-model), so game.oob applies them as role defaults rather than reading them
    here. Tanks span rate 1 (Mk VI light) to 7 (Grant / Churchill)."""
    chart = _data()["fuel_consumption"]["fuel_consumption_rate_by_model"]
    out: dict = {}
    for nation_key in ("german_tank", "commonwealth_tank", "italian_tank"):
        out.update(chart[nation_key])
    return out


def truck_characteristics() -> dict:
    """[54.2] Truck Characteristics Chart, reduced to what the CHUNK-4 haulage layer
    consumes, keyed by class ('light'|'medium'|'heavy'): the per-Truck-Point supply-point
    capacity of each commodity (the chart's 'Supplies' columns), the convoy CPA (the
    chart's Supplies CPA, which EQUALS the 53.22 extended allowance -- Light 40,
    Medium/Heavy 30), the truck's own Fuel Capacity (self-tank), and its Fuel Consumption
    Factor (1 for every class). Verified cell-by-cell against docs/rules/90."""
    chart = _data()["truck_characteristics_54_2"]
    out: dict = {}
    for cls in ("light", "medium", "heavy"):
        row = chart[cls]
        cap = row["supply_point_capacity"]
        out[cls] = {
            "capacity": {"AMMO": cap["ammo"], "FUEL": cap["fuel"],
                         "STORES": cap["stores"], "WATER": cap["water"]},
            "convoy_cpa": row["cpa"]["supplies"],
            "fuel_capacity": row["fuel_capacity"],
            "fuel_factor": row["fuel_consumption_factor"],
        }
    return out


def _scenario_61() -> dict:
    return _data()["scenario_61_desert_fox_initial_supply"]


def axis_dump_pool_61_44() -> dict:
    """[61.44] the FULL-LOGISTICS Axis start-line supply pool, split across the Axis
    dumps (game.oob authored placement). Keyed by engine commodity name."""
    p = _scenario_61()["axis_dump_split_61_44"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"], "WATER": p["water"]}


def cw_dump_pool_61_36() -> dict:
    """[61.36] the FULL-LOGISTICS Commonwealth start-line supply pool (fuel/ammo/stores),
    split across the CW dumps. Note 61.36 charts NO dump Water for the Commonwealth --
    CW water comes from the 52.7 wells and the 54.3 rail, both deferred -- so game.oob
    seeds a FLAGGED wells/rail Water proxy on top of this."""
    p = _scenario_61()["commonwealth_dump_split_61_36"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def tobruk_builtin_61_36() -> dict:
    """[61.36] Tobruk's built-in supply (fuel/ammo/stores); Tobruk is itself a dump."""
    p = _scenario_61()["commonwealth_tobruk_builtin_61_36"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def tripoli_builtin_61_44() -> dict:
    """[61.44] the Tripoli box built-in supply (fuel/ammo/stores), held IN ADDITION to the
    61.44 field-dump split -- the standing stock at the rear Axis harbour."""
    p = _scenario_61()["axis_tripoli_builtin_61_44"]
    return {"AMMO": p["ammo"], "FUEL": p["fuel"], "STORES": p["stores"]}


def port_supply_tonnage_55_3() -> dict:
    """[55.3] per-port MAXIMUM supply tonnage per Operations Stage + its Efficiency
    Level, keyed by port name (game.scenario crosses tonnage->points via 54.5)."""
    return _data()["port_supply_tonnage_55_3"]["max_supply_tonnage_per_opstage"]


def convoy_level_56_4() -> dict:
    """[56.4] Axis Naval Convoy Level letter (A-G / '-') by calendar year and month."""
    return _data()["axis_naval_convoys_56"]["convoy_level_chart_56_4"]


def convoy_capacity_56_5() -> dict:
    """[56.5] Axis Naval Convoy capacity by Level: fixed_tons + variable_tons_per_die x die."""
    return _data()["axis_naval_convoys_56"]["convoy_capacity_table_56_5"]


def convoy_bombing_crt_41_66() -> list:
    """[41.66]/[32.66] the Axis-Naval-Convoy row of the [41.5] Air Bombardment &
    Secondary Barrage Targets Table: the ordered Bomb-Point columns of the convoy-
    bombing CRT. Each column carries its bomb_points bracket [lo, hi] (hi=None on the
    open 471+ bracket) and a `results` list of {die: [lo, hi], pct_lost}: the engine
    picks the column by total Bomb Points, then reads 2d6 SEQUENTIALLY as a two-digit
    code (tens=first die, units=second) and looks up the tens-of-percent cargo lost."""
    return _data()["axis_naval_convoys_56"]["air_convoy_bombing_crt_41_66"]["columns"]
