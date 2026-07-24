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
_WITHDRAWALS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "withdrawals_campaign.json"))


@lru_cache(maxsize=1)
def _data() -> dict:
    with open(_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _withdrawals() -> dict:
    with open(_WITHDRAWALS_PATH, encoding="utf-8") as fh:
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


# --- [20.3] the REPLACEMENT POINT CONVERSION CHART (Block 7.2b, THE SPEND) ----------------

def _conversion() -> dict:
    return _data()["replacement_conversion_20_3"]


def conversion_rows() -> list:
    """Every row of the [20.3] Replacement Point Conversion Chart -- unit type -> the
    Replacement Points, by class, that restore one of its TOE Strength Points."""
    return _conversion()["rows"]


def conversion_for(unit_type: str) -> dict:
    """The [20.3] row for a unit TYPE key (e.g. 'any_other_infantry', 'tank'). Its `requires`
    is a list of ALTERNATIVES (OR); each alternative a list of {class,count} (AND). An empty
    `requires` is the free Road/Railroad Construction rebuild (note f)."""
    for row in conversion_rows():
        if row["unit_type"] == unit_type:
            return row
    raise KeyError(f"no [20.3] Replacement Point Conversion row {unit_type!r}")


def conversion_charge(unit_type: str) -> dict:
    """The DEFAULT Replacement-Point charge to rebuild ONE TOE Strength Point of `unit_type`:
    the FIRST [20.3] alternative folded to {class: count}. The first alternative is the plain
    same-class rebuild (a Recce/Armored-Car row's second alternative is the Lt-Tank UPGRADE,
    Case 20.5). {} for the free Road/Railroad Construction row (note f)."""
    alts = conversion_for(unit_type)["requires"]
    if not alts:
        return {}
    charge: dict = {}
    for req in alts[0]:
        charge[req["class"]] = charge.get(req["class"], 0) + req["count"]
    return charge


# --- [20.8] the Commonwealth MANDATORY WITHDRAWAL schedule (Block 7.2b) -------------------

def withdrawal_rows() -> list:
    """The [4.43a] WD-column schedule -- every mandatory Commonwealth withdrawal, {turn, stage,
    formation, match, tpt, by_type?}. `match` is a list of counter-name prefixes (may be empty
    where the named formation is not yet in the OOB)."""
    return _withdrawals()["withdrawals"]


def withdrawals_for_turn(turn: int) -> list:
    """The withdrawal rows scheduled for this Game-Turn. The engine fires them at the turn's start
    (turn-granular, as reinforcements arrive at Stage 1 regardless of their own arrival_stage); the
    row's `stage` is transcribed but not used for timing -- flagged in engine._commonwealth_withdrawals."""
    return [w for w in withdrawal_rows() if w["turn"] == turn]


def withdrawal_base_hexes() -> dict:
    """[20.83]/[20.84] Cairo and Alexandria, as axial (q, r) -- the two cities a withdrawing unit
    must reach by its Stage or be ELIMINATED."""
    return {city: tuple(hx) for city, hx in _withdrawals()["base_hexes"].items()}


def withdrawal_toe_fraction() -> float:
    """[20.82] The 75% of maximum TOE Strength a withdrawing unit must hold to be cleanly withdrawn
    (else eliminated, 20.83) and to satisfy a by-type withdrawal. Read from the named errata key
    that records the 20.83 '(20.75)' -> (20.82) cross-reference typo (owner ruling 3)."""
    return _withdrawals()["toe_threshold_errata_20_82"]["toe_fraction"]


def withdrawal_matches(counter: str, prefixes) -> bool:
    """Does an engine counter id belong to a withdrawal's formation? The schedule's `match` prefixes
    are the human-readable formation names ('7 In Bde'); engine unit ids are the slug game.oob._uid
    builds by turning every space into a hyphen ('HQ-7-In-Bde', '7-In-Bde-I', '7-In-Bde-(Rtn)-I').
    Both sides are normalised to that slug, then a counter matches prefix P if it equals P or 'HQ-'+P,
    or begins with P+'-' or 'HQ-'+P+'-' -- so a formation's HQ, its battalions and its later (Rtn)
    instances all match one prefix, and being on-map at the withdrawal turn selects the right instance
    across a withdraw/return shuffle."""
    cid = counter.replace(" ", "-")
    for p in prefixes:
        s = p.replace(" ", "-")
        if cid == s or cid == f"HQ-{s}" or cid.startswith(f"{s}-") or cid.startswith(f"HQ-{s}-"):
            return True
    return False
