"""Rule 20 -- the Replacement economy's FLOW IN (production), Block 7.2a.

Reads data/replacements.json (the transcribed [20.66]/[20.66a]/[20.78B]/[20.78C] charts)
and models what Replacement Points become AVAILABLE, per side, per type. The SPEND -- a
unit absorbing a point to restore TOE Strength, via the already-wired UNIT_REBUILT /
organization.absorb path -- is Block 7.2b. Nothing here restores a strength point.

THE ASYMMETRY (20.75) is the point of Phase 7 and it lives here structurally:
  * the Commonwealth INFANTRY stream is a RANDOM production stream (20.73/20.78B) -- one
    2d6 roll every Game-Turn, FREE, arriving four Game-Turns later. The engine draws the
    dice off the DiceBox 'cw_production' subsystem and calls cw_infantry_lookup() to read
    the table; game.engine._replacement_production is the beat.
  * every AXIS Replacement Point is charged tonnage against the [56.5] convoy (20.62), at
    priority over supplies (20.64), planned two Game-Turns ahead (20.63) -- tonnage_per_point.
  * the Commonwealth EQUIPMENT chart (20.78C) is drawn at will, also FREE (20.75).

This mirrors game.logistics_data: a thin cached reader that turns the transcribed charts
into the constants the engine consumes, so the magnitudes are the RULEBOOK'S -- read from
data, never literals.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "replacements.json"))


@lru_cache(maxsize=1)
def _data() -> dict:
    with open(_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# --- lead times (20.63 / ruling 1) ------------------------------------------------------

def _lead() -> dict:
    return _data()["arrival_lead_time"]


CW_ARRIVAL_LEAD: int = _lead()["commonwealth_game_turns"]     # 4 Game-Turns (owner ruling 1)
AXIS_ARRIVAL_LEAD: int = _lead()["axis_game_turns"]           # 2 Game-Turns (20.63)


def commonwealth_arrival_turn(plan_gt: int) -> int:
    """The Game-Turn a Commonwealth point PLANNED on `plan_gt` reaches the map (20.76): plan + 4."""
    return plan_gt + CW_ARRIVAL_LEAD


def axis_arrival_turn(plan_gt: int) -> int:
    """The Game-Turn an Axis point planned on `plan_gt` reaches the map (20.63): plan + 2."""
    return plan_gt + AXIS_ARRIVAL_LEAD


# --- [20.78B] the Commonwealth infantry PRODUCTION STREAM -------------------------------
#
# 2d6 probability weights (out of 36), for the analytic expectation. The engine ROLLS the
# stream (two d6 off the 'cw_production' subsystem) and hands the total to cw_infantry_lookup;
# these weights never touch the live game -- they only prove the table's expected yield.
_D2D6_WEIGHT = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}


def _cw_infantry() -> dict:
    return _data()["commonwealth_infantry_production_20_78B"]


def cw_infantry_column(plan_gt: int) -> dict | None:
    """The [20.78B] column whose Game-Turn window contains `plan_gt`, or None if the turn is
    outside all four columns (GT1-2 and GT108-111 produce nothing)."""
    for col in _cw_infantry()["columns"]:
        if col["plan_first"] <= plan_gt <= col["plan_last"]:
            return col
    return None


def cw_infantry_lookup(plan_gt: int, roll: int) -> int:
    """The Infantry Replacement Points a 2d6 `roll` (2..12) produces when planned on `plan_gt`.
    PURE -- the engine draws the dice; this only reads the transcribed table. 0 when `plan_gt`
    is outside the GT3-107 production window ('none' cells are also 0)."""
    col = cw_infantry_column(plan_gt)
    if col is None:
        return 0
    return col["by_roll"][str(roll)]


def cw_infantry_plan_turns() -> range:
    """Every Game-Turn on which the Commonwealth rolls the [20.78B] stream: GT3 through GT107
    inclusive (105 rolls), the union of the four columns' windows."""
    cols = _cw_infantry()["columns"]
    return range(cols[0]["plan_first"], cols[-1]["plan_last"] + 1)


def cw_infantry_expected_yield() -> float:
    """The analytic 2d6 expectation of the [20.78B] stream over its whole GT3-107 window --
    the port plan's '~1,617' (transcription: 1,615.9). A property of the table alone."""
    total = 0.0
    for col in _cw_infantry()["columns"]:
        span = col["plan_last"] - col["plan_first"] + 1
        per_turn = sum(_D2D6_WEIGHT[int(r)] * v for r, v in col["by_roll"].items()) / 36.0
        total += span * per_turn
    return total


# --- [20.66] the AXIS REPLACEMENT POOL --------------------------------------------------

def _axis_chart(chart: str) -> dict:
    key = {"german": "german_production", "italian": "italian_production"}[chart]
    return _data()["axis_pool_20_66"][key]


def axis_items(chart: str) -> list:
    """Every row of the German or Italian Production Chart ([20.66])."""
    return _axis_chart(chart)["items"]


def axis_item(chart: str, key: str) -> dict:
    """One row of the German ('german') or Italian ('italian') Production Chart, by key."""
    for item in axis_items(chart):
        if item["key"] == key:
            return item
    raise KeyError(f"no {chart} Axis pool item {key!r}")


def axis_tank_total(chart: str) -> int:
    """The campaign-total tank-class Replacement Points on one Axis chart (German 131 / Italian 204)."""
    return sum(i["number"] for i in axis_items(chart) if i.get("class") == "tank")


def axis_trucks() -> list:
    """[20.66a] the Axis Truck Production Chart rows (Light 835 / Medium 2890 / Heavy 525)."""
    return _data()["axis_pool_20_66"]["truck_production_20_66a"]["items"]


def axis_tonnage_per_point(chart: str, key: str) -> int:
    """The Axis Naval Convoy tons charged per Replacement Point of this type (20.62), read from
    the chart's own Tonnage column -- which already carries the ruling-6 errata (Infantry 30, not
    the 35 that 20.62's example implies). This is the number [54.5] forward-references, and the
    number that couples the replacement economy to the convoy (priority over supplies, 20.64)."""
    return axis_item(chart, key)["tonnage"]


def tonnage_errata() -> dict:
    """The named errata key recording the 30-vs-35 tons-per-Infantry-Point ruling (owner ruling 6)."""
    return _data()["axis_tonnage_errata_20_62"]


# --- [20.78C] the COMMONWEALTH PRODUCTION CHART -----------------------------------------

def _cw_equipment() -> dict:
    return _data()["commonwealth_production_20_78C"]


def commonwealth_equipment_items() -> list:
    """Every row of the [20.78C] Commonwealth Production Chart (24 tank/gun/AA rows)."""
    return _cw_equipment()["items"]


def commonwealth_item(key: str) -> dict:
    """One [20.78C] row by key (e.g. 'sherman', '25_pounder')."""
    for item in commonwealth_equipment_items():
        if item["key"] == key:
            return item
    raise KeyError(f"no Commonwealth equipment item {key!r}")


def commonwealth_tank_total() -> int:
    """The 13 armour rows summed at their printed # -- 332 (owner ruling 2, NOT the plan's 306)."""
    return sum(i["number"] for i in commonwealth_equipment_items() if i.get("class") == "tank")


def commonwealth_tonnage_per_point(key: str) -> int:
    """[20.75] Zero, always. The Commonwealth Player has no Shipping Problems; his Replacement
    Points -- infantry stream and equipment chart alike -- simply arrive, free of tonnage."""
    return 0
