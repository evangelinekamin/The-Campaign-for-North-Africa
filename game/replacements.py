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
import math
import os
from functools import lru_cache

from . import campaign_victory, coords
from .events import Side

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


def axis_gun_total(chart: str) -> int:
    """The campaign-total gun-class Replacement Points on one Axis chart (German 124 / Italian 251)."""
    return sum(i["number"] for i in axis_items(chart) if i.get("class") == "gun")


def axis_equipment_pool_total(pool_class: str) -> int:
    """[20.66] The campaign-total Axis tank/gun Replacement Points across both German and Italian
    charts (tank 335 / gun 499). The lifetime ceiling the equipment bring-in may not exceed."""
    if pool_class == "tank":
        return axis_tank_total("german") + axis_tank_total("italian")
    elif pool_class == "gun":
        return axis_gun_total("german") + axis_gun_total("italian")
    return 0


def axis_equipment_per_gt_max(plan_turn: int, pool_class: str) -> int:
    """[20.66]/[20.67] The most tank/gun Replacement Points of `pool_class` the Axis may PLAN in
    Game-Turn `plan_turn` -- the sum of the Max of every chart item of that class whose plan window
    contains the turn. Read from the chart, not a literal; 0 before the class's first window opens
    (tanks GT41, guns GT45 both German).

    FLAG (a judgement call, no transcribed number moved -- the same one commonwealth_equipment_per_gt_max
    makes): the printed Max is taken as a per-GAME-TURN ceiling regardless of its max_period. Some rows
    print Max per month or per two weeks; a monthly allowance MAY be planned inside a single Game-Turn.
    (axis_infantry_per_gt_max instead RAISES on a non-game_turn period, because infantry is game_turn on
    both charts, so a stray period there would be a data error -- equipment periods legitimately vary.)
    This is the aggregate class ceiling for documentation/tests; the live bring-in
    (axis_equipment_election / engine._axis_replacement_bring_in) realizes it PER-ITEM, bounding each
    type by its own Max, so this summed value is not what charges the convoy."""
    total = 0
    for chart in ("german", "italian"):
        for item in axis_items(chart):
            if item.get("class") != pool_class:
                continue
            mx, period = _applicable_period_max(item, plan_turn)
            if mx and mx > 0:
                total += mx
    return total


def axis_equipment_election(plan_turn: int, pool_class: str, want_points: int,
                            allowed_tons: int) -> "tuple[int, int]":
    """[20.62]/[20.66] Elect up to `want_points` tank/gun Replacement Points of `pool_class` for the
    Game-Turn's bring-in and return (points, tons) charged at the chart's REAL per-type Tonnage.

    The book charges each Replacement Point its printed per-type Tonnage (the Tonnage column: PzII 135,
    CV L.3 16, 17cm K18 206, gun_65_17 3, ...), NOT one class number -- so the earlier average was an
    invented figure the gun class alone spans 3->206 tons across. The DEFICIT the QM heals is per-class
    (which specific tank TYPE restores a depleted battalion is the [20.3] conversion's free choice, and
    replacement_kind collapses every tank counter to one 'tank'), so the per-type ELECTION is a
    judgement call, FLAGGED: the QM brings in the CHEAPEST-Tonnage types first -- the most Replacement
    Points per ton of scarce convoy. Each type is bounded by its own [20.66]/[20.67] per-Game-Turn Max
    (the printed Max as a per-Game-Turn ceiling, the axis_equipment_per_gt_max flag); `want_points`
    already carries the deficit and the class campaign-total cap; `allowed_tons` is the convoy allowance
    left after infantry, so a point is elected only if its real Tonnage still fits.

    RESIDUAL (FLAGGED, deficit-bound): the per-ITEM campaign '#'/'first Number' window sub-cap (e.g. the
    German Light AA's 40 total, or an early-window step) is not metered here -- the shipped ledger is
    class-keyed (AXIS/gun), so the engine caps the class aggregate (axis_equipment_pool_total), not each
    row. The deficit binds far below these per-row ceilings in play (the review measured ~20 tank / ~1
    gun Points across the whole campaign), so this never differs live; per-row metering awaits a per-type
    ledger. This is the same CLASS-not-TYPE aggregation the Commonwealth flow-in already documents."""
    if want_points <= 0 or allowed_tons <= 0:
        return 0, 0
    rows = []
    for chart in ("german", "italian"):
        for item in axis_items(chart):
            if item.get("class") != pool_class:
                continue
            mx, _ = _applicable_period_max(item, plan_turn)
            if mx and mx > 0:
                rows.append((item["tonnage"], mx))
    points = tons = 0
    for tonnage, cap in sorted(rows):                     # cheapest Tonnage first (the flagged election)
        if points >= want_points or allowed_tons - tons < tonnage:
            break
        n = min(cap, want_points - points, (allowed_tons - tons) // tonnage)
        if n <= 0:
            continue
        points += n
        tons += n * tonnage
    return points, tons


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


# --- [20.62]/[20.64]/[20.67] the AXIS INFANTRY bring-in ceiling (Block B, the convoy coupling) -----
#
# Block B builds the [20.62] tonnage charge (engine._axis_replacement_bring_in), whose vehicle is a
# minimal, faithful INFANTRY flow-in: the Axis brings in the Infantry Replacement Points his depleted
# army needs, bounded by the [20.66]/[20.67] pool. Only INFANTRY is wired live -- both German and
# Italian print an unambiguous 30 tons/point, and Block A's spend already heals AXIS/infantry. The
# TANK/GUN Axis flow-in is DEFERRED: its per-type tonnage (PzII 135 ... PzIV F2 235) is not a single
# number, and the recce-vs-gun class split awaits the [20.3] reconciliation data/replacements.json
# flags. The tonnage charge itself is class-agnostic and lands them cheaply once that reconciliation
# and a per-type election arrive.

def _applicable_period_max(item: dict, plan_turn: int) -> "tuple[int, str | None]":
    """The [20.66]/[20.67] Max Replacement Points of one Production-Chart `item` plannable on
    `plan_turn`, with its Max period -- honouring either a flat `plan_gt` window (German rows) or the
    tiered `plan_first`/`plan_last` windows (the Italian pool's rate steps). (0, None) outside every
    window. The Italian infantry `tiers` share one campaign pool but step their per-Game-Turn rate at
    GT9 and GT25; the active tier is the one whose window contains the plan turn."""
    if "tiers" in item:
        for tier in item["tiers"]:
            hi = tier.get("plan_last")
            if tier["plan_first"] <= plan_turn and (hi is None or plan_turn <= hi):
                return tier["max"], tier["max_period"]
        return 0, None
    if plan_turn >= item.get("plan_gt", 1 << 30):
        return item["max"], item["max_period"]
    return 0, None


def axis_infantry_per_gt_max(plan_turn: int) -> int:
    """[20.66]/[20.67] The most INFANTRY Replacement Points the Axis may PLAN in Game-Turn `plan_turn`
    -- the German pool (400, 12/Game-Turn from GT38) plus the active Italian tier (1,200 total: 5/GT
    across GT5-8, 10/GT across GT9-24, 25/GT from GT25). Both nations' infantry Max is per game_turn,
    so this is a direct per-Game-Turn ceiling; it is 0 before the Italian pool opens (GT5). Read from
    the [20.66] chart, not a literal."""
    total = 0
    for chart in ("german", "italian"):
        mx, period = _applicable_period_max(axis_item(chart, "infantry"), plan_turn)
        if mx and period != "game_turn":                # infantry is all per-game_turn on both charts
            raise ValueError(f"{chart} infantry Max period is {period!r}, not 'game_turn'")
        total += mx
    return total


def axis_italian_infantry_window_total(plan_turn: int) -> "int | None":
    """[20.66] Italian infantry's WINDOW TOTAL cap across GT5-24: max 100 RP. The Italian pool
    records this as tier 0 with number=100 (GT5-8) and tier 1 with number=0 (GT9-24), both sharing
    the same 100-RP pool. Returns 100 if plan_turn is in GT5-24, None otherwise. This is distinct
    from the per-GT rate (5/GT GT5-8, 10/GT GT9-24) and enforces a separate lifetime cap."""
    italian_inf = axis_item("italian", "infantry")
    if italian_inf["tiers"]:
        tier0 = italian_inf["tiers"][0]
        # Tier 0 defines the window start and total (100)
        # Tier 1 (if present) continues the same window at a higher rate
        if len(italian_inf["tiers"]) > 1:
            tier1 = italian_inf["tiers"][1]
            # Both tiers must have the same window end (GT24) for this to work
            if tier0["plan_first"] <= plan_turn <= tier1.get("plan_last", 111):
                # We're in the shared 100-RP window (GT5-24)
                if plan_turn >= tier0["plan_first"] and plan_turn <= (tier1.get("plan_last") or 111):
                    return tier0["number"]  # 100
    return None


def axis_infantry_tonnage() -> int:
    """[20.62]/errata (owner ruling 6): the Shipping Tons charged per Axis Infantry Replacement Point
    -- 30, printed identically on the German and Italian charts. Read from the chart's Tonnage column,
    asserting the two agree, so the coupling's magnitude is the book's."""
    german = axis_tonnage_per_point("german", "infantry")
    italian = axis_tonnage_per_point("italian", "infantry")
    if german != italian:
        raise ValueError(f"German ({german}) and Italian ({italian}) infantry tonnage disagree")
    return german


def axis_infantry_pool_total() -> int:
    """[20.66] The campaign-total Axis INFANTRY Replacement Points -- the German 400 plus the Italian
    1,200 = 1,600, each chart's own '#'. The lifetime ceiling the bring-in may not exceed (the coupling
    tracks cumulative shipped against it). FLAG: this is the NATION-AGGREGATE cap, collapsing the German
    400 / Italian 1,200 sub-caps into one, exactly as the engine's AXIS/infantry pool and
    organization.replacement_kind already treat Axis infantry as one nation-agnostic class."""
    return (axis_item("german", "infantry")["number"]
            + axis_item("italian", "infantry")["number"])


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


def commonwealth_equipment_class_total(pool_class: str) -> int:
    """The campaign-total [20.78C] Replacement Points of one mass class (tank 332 / gun 536 / recce 90)
    -- the lifetime ceiling the [20.78C] equipment flow-in (engine._cw_equipment_production) may not
    exceed. The chart's own item 'class' column IS the pool class (tank/gun/recce), so this sums the
    '#' of the matching rows; the recce total is inert (recce is not a spendable pool -- see
    engine._get_eligible_units_for_class -- so the flow-in never draws it)."""
    return sum(i["number"] for i in commonwealth_equipment_items() if i.get("class") == pool_class)


def commonwealth_equipment_per_gt_max(plan_turn: int, pool_class: str) -> int:
    """[20.78C] The most Replacement Points of `pool_class` (tank/gun) the Commonwealth may PLAN in
    Game-Turn `plan_turn` -- the sum of the Max of every chart item of that class whose plan window
    (plan_first..plan_last, a null plan_last running to campaign end) contains the turn. Read from the
    chart, not a literal; 0 before the class's first window opens (the gun chart opens GT5, tanks GT3).

    FLAG (a judgement call, no transcribed number moved): the printed Max is taken as a per-GAME-TURN
    ceiling regardless of its max_period. Some [20.78C] rows print Max per month ('*') or per two weeks
    (dagger); a monthly allowance MAY be planned inside a single Game-Turn (the cap governs the month's
    total, not the turn's), and the campaign-total '#' (commonwealth_equipment_class_total) is the hard
    lifetime ceiling this flow-in actually tracks -- so the rolling month/two-week WINDOW total is not
    separately metered. Under the heal-the-deficit doctrine the rate is dominated by the deficit and the
    campaign total anyway; this is the same aggregation axis_infantry_per_gt_max already makes over the
    two nations' pools. A Max printed as a dash (the lone Churchill) carries no rate cap and contributes
    its '#'."""
    total = 0
    for item in commonwealth_equipment_items():
        if item.get("class") != pool_class:
            continue
        lo, hi = item["plan_first"], item["plan_last"]
        if plan_turn < lo or (hi is not None and plan_turn > hi):
            continue
        mx = item["max"]
        total += item["number"] if mx is None else mx
    return total


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


def _build_conversion_class_to_pool_class_map() -> dict:
    """BUILD: Static reverse mapping from [20.3] Replacement Point classes to pool classes.

    The mass pools use simplified class names (infantry, tank, gun) but [20.3] uses specific
    classes (e.g., "artillery", "anti_tank", "anti_air" all map to pool "gun"). This mapping is
    used in engine._rebuild to convert the [20.3] class from conversion_charge back to the pool
    class for looking up available points."""
    mapping = {}
    # Explicit mappings based on data inspection:
    # Gun types ([20.78C] / [20.66] use "gun", [20.3] uses "artillery"/"anti_tank"/"anti_air")
    mapping["artillery"] = "gun"
    mapping["anti_tank"] = "gun"
    mapping["anti_air"] = "gun"
    # Tank types (both use "tank")
    mapping["tank"] = "tank"
    # Infantry and all its variants (both use "infantry")
    mapping["infantry"] = "infantry"
    # NOT mapped -- the [20.3] recce classes "armr"/"lt_tank": organization.replacement_kind never
    # emits a recce kind (a recce counter collapses to any_other_infantry, the [4.47] proxy), so no
    # selectable unit ever charges these, and a "recce" pool would be structurally unreachable. They
    # fall through to None, exactly as the one-off special classes do, until the engine can tell recce
    # from infantry (the same gate engine._get_eligible_units_for_class documents).
    # Unknown classes fall through to return None (will cause _rebuild to fail clearly)
    return mapping


_CONVERSION_CLASS_TO_POOL_CLASS: dict | None = None


def conversion_class_to_pool_class(conv_class: str) -> str | None:
    """Convert a [20.3] Replacement Point class to the pool class that can supply it.
    Returns None if the class is not in any pool (e.g., special one-off classes like
    'italian_para_art' or 'german_75_lt_gun' that have no mass pool)."""
    global _CONVERSION_CLASS_TO_POOL_CLASS
    if _CONVERSION_CLASS_TO_POOL_CLASS is None:
        _CONVERSION_CLASS_TO_POOL_CLASS = _build_conversion_class_to_pool_class_map()
    return _CONVERSION_CLASS_TO_POOL_CLASS.get(conv_class)


# --- [17.6]/[20.43] the TRAINING CHART: the RP-training delay (Block 7.4) -----------------

OPSTAGES_PER_GAME_TURN = 3      # rule 5.1: a Game-Turn is three Operations Stages


def _training() -> dict:
    return _data()["training_chart_17_6"]["opstages"]


def training_opstages(rp_type: str) -> int:
    """[17.6]/[20.43] The Operations Stages an arrived Replacement Point of `rp_type` must Train
    before a depleted unit may absorb it (Gun 1 / Infantry 3 / Tank,AC,Recce 6 / Commando 12), read
    from the transcribed [17.6] chart. 'commonwealth_unit' (6) is the SEPARATE 17.3 unit-morale track
    (its climb consumer is deferred -- see the data key's flag)."""
    return _training()[rp_type]


def training_delay_gt(rp_type: str) -> int:
    """The whole Game-Turns an arrived Replacement Point of `rp_type` spends in 20.43 Training before
    it is absorbable, given the once-per-Game-Turn Reorganization spend: ceil(OpStages / 3), because a
    Game-Turn is OPSTAGES_PER_GAME_TURN Operations Stages (rule 5.1) and the spend runs at the turn's
    head, before its stages -- so a point arriving on Game-Turn N is absorbable on Game-Turn N + delay.

    Infantry 3 -> 1, Tank/Recce 6 -> 2, Commando 12 -> 4. Gun 1 -> 1: a sub-turn 1-OpStage training
    rounds UP to a full Game-Turn's wait at this per-Game-Turn spend grain -- flagged. The Gun and Tank
    delays are LIVE (not inert): the [20.78C] Commonwealth equipment flow-in (engine._cw_equipment_
    production) feeds ALLIED/tank and ALLIED/gun into the training ledger alongside the CW-infantry
    stream, so a gun point trains one Game-Turn and a tank point two before the spend may absorb it."""
    return math.ceil(training_opstages(rp_type) / OPSTAGES_PER_GAME_TURN)


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


@lru_cache(maxsize=1)
def withdrawal_base_hexes() -> frozenset:
    """[20.83]/[20.84] EVERY hex of Cairo and Alexandria as axial (q, r) -- the two cities a
    withdrawing unit must stand in by its Stage or be ELIMINATED (20.83). Cairo is FIVE hexes and
    Alexandria TWO; they are read from the ONE canonical enumeration -- data/victory_cities.json
    'auto_win' (the rule-64.71 auto-win objective and the 25.12 Level-3 forts), the same source
    game.scenario.delta_hexes reads -- NOT a narrower private copy that recognised one hex per city
    and so eliminated units standing anywhere else in the Delta."""
    aw = campaign_victory.load_victory_cities()["auto_win"]
    return frozenset(coords.to_axial(coords.parse(h))
                     for h in aw["alexandria"] + aw["cairo"])


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


# --- [64.74] UNUSED REPLACEMENT-POINT VICTORY POINTS (Block 7.3) --------------------------

def _victory_64_74() -> dict:
    return _data()["victory_replacement_points_64_74"]


def replacement_vp_excluded_classes(side: Side) -> frozenset:
    """[64.74] The Replacement-Point CLASSES the printed rule PERMANENTLY excludes from Victory Points
    for `side` (planes and Trucks both sides; Infantry for the Commonwealth only). Read from the named
    'victory_replacement_points_64_74' key. This set is book-faithful (scan p.088): the earlier proxy
    that also dropped Axis infantry was reverted 2026-07-24 -- the spendable gate below, not an
    exclusion, now keeps an unbuilt-spend class from scoring."""
    return frozenset(_victory_64_74()["excluded_classes"].get(side.value, ()))


def replacement_vp_spendable_classes(side: Side) -> frozenset:
    """[64.74] The Replacement-Point classes the engine can currently SPEND for `side` -- the only
    classes whose UNUSED count is a real quantity. OWNER RULING 2026-07-24 (Eve): 64.74 scores only
    spendable classes, because a class with no rebuild beat is 100% unused by construction (an
    unmodelled spend, not the husbandry 64.74 rewards). It GROWS one data edit at a time WITH the
    producer that makes its spend real -- and ONLY when that spend is non-trivial AND its book-symmetric
    counterpart on the other side is producible too, so 64.74 never scores half of a rule the book
    applies to both sides. Today only AXIS 'infantry' scores (the [20.66] coupling + Block B flow-in +
    spend heals ~1,587 of the 1,600 pool -- a real used>0). ALLIED holds 'infantry' (spendable via the
    [20.78B] stream but book-EXCLUDED, so it scores 0). ALLIED 'tank'/'gun' were added by Block A and
    REVERTED in its review-repair (2026-07-25): the CW equipment producer is faithful but its spend is
    near-zero (gun is never produced -- CW guns do not deplete-alive), so scoring it banks a fixed ~865
    the book only means as husbandry, and -- with the symmetric Axis equipment pool unbuilt and unscored
    -- that one-sided ~865 flipped the pinned campaign seed (see the data key's REVERTED note). They
    return with their Axis mirror. Read from data so adding a class is never a literal here."""
    return frozenset(_victory_64_74()["spendable_classes"].get(side.value, ()))


def replacement_allotment_by_class(side: Side) -> dict:
    """The campaign-total Replacement Points ALLOTTED per class (the charts' '#' columns), by side.
    Axis = the [20.66] German + Italian Replacement Pool; Commonwealth = the [20.78C] equipment
    chart. The [20.78B] Commonwealth Infantry stream is a RANDOM production, not a fixed allotment,
    and 64.74 excludes it anyway; the [20.66a]/[20.78A] Truck streams are separate and excluded too.
    A pure read of the transcribed charts -- the magnitudes are the book's, grouped by the per-row
    'class' (an implementer derivation the data flags, inert here: it only buckets the sum)."""
    out: dict = {}
    if side == Side.AXIS:
        items = axis_items("german") + axis_items("italian")
    elif side == Side.ALLIED:
        items = commonwealth_equipment_items()
    else:
        return out
    for item in items:
        out[item["class"]] = out.get(item["class"], 0) + item["number"]
    return out


def unused_replacement_vp(side: Side, used: dict, spendable: "frozenset | None" = None) -> int:
    """[64.74] `side`'s replacement Victory Points: ONE per UNUSED Replacement Point (allotted minus
    used), summed over the SCORING classes -- a class scores only if it is both SPENDABLE
    (replacement_vp_spendable_classes, Eve's 2026-07-24 ruling) and NOT permanently excluded
    (replacement_vp_excluded_classes -- planes/trucks both, infantry CW-only). `used` maps
    (side_value, class) -> Replacement Points already drawn by the SPEND (game.campaign_victory sums it
    from the UNIT_REBUILT log). Floored at zero per class so an over-draw (impossible today -- the SPEND
    gate caps every rebuild at the pool) can never score negative.

    `spendable` overrides the data-driven set, for tests that verify the allotted-minus-used arithmetic
    of a class not yet spendable in the live campaign. Left None in all engine callers.

    LIVE (as of the Block A CW-equipment review-repair, 2026-07-25): only the AXIS scores, its unused
    'infantry' -- the [20.66] flow-in + [20.62] coupling + spend made 'AXIS/infantry' a real spendable
    class (~13 unused of the 1,600 pool in the seed-1941 war). The COMMONWEALTH scores 0 here: its
    'infantry' is spendable but book-EXCLUDED, and its 'tank'/'gun' were REVERTED from spendable_classes
    (Block A scored them, but the CW equipment spend is near-zero -- gun is never even produced -- so the
    ~865 husbandry is unused-by-construction, and scoring it while the symmetric Axis equipment pool is
    unbuilt/unscored flipped the pinned campaign; see data/replacements.json). CW equipment scoring
    returns with its Axis mirror. Still awaiting their own Axis flow-ins: Axis 'tank'/'gun'/'recce'
    (per-type tonnage + the [20.3] class reconciliation the data flags on axis_pool_20_66); CW 'recce'
    is additionally structurally unspendable (replacement_kind never emits a recce kind)."""
    excluded = replacement_vp_excluded_classes(side)
    if spendable is None:
        spendable = replacement_vp_spendable_classes(side)
    total = 0
    for cls, allotted in replacement_allotment_by_class(side).items():
        if cls not in spendable or cls in excluded:
            continue
        total += max(0, allotted - used.get((side.value, cls), 0))
    return total
