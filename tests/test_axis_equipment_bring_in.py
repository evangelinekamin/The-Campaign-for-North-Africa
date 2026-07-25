"""[20.62]/[20.64]/[20.66] THE AXIS EQUIPMENT BRING-IN (Block B).

The mechanism that brings in Axis tank/gun Replacement Points via the same [20.62] convoy coupling
and [20.64] priority that the infantry bring-in uses. Tank and gun Replacement Points are drawn
from the [20.66] German and Italian Production Charts, bounded by per-Game-Turn Max and campaign
totals, at per-type tonnages read from the charts' own Tonnage columns.

ALSO: Enforcement of the [20.66] Italian infantry sub-cap (max 100 RP across GT5-24), a window
total distinct from the per-Game-Turn Max.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.supply as supply
from game import organization, replacements
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.engine import _convoy_planning, _Run, run
from game.events import EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import Policy
from game.scenario import campaign
from game.state import Convoy, GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


# --- [20.66] the Axis equipment pool readers (tank/gun) ------------------------------------------

def test_axis_tank_total_reads_the_pool():
    """[20.66] The German and Italian tank pools have their own campaign totals: 131 + 204 = 335
    Axis tank Replacement Points (the sum of all rows classed 'tank')."""
    assert replacements.axis_tank_total("german") == 131
    assert replacements.axis_tank_total("italian") == 204
    total = replacements.axis_tank_total("german") + replacements.axis_tank_total("italian")
    assert total == 335


def test_axis_gun_total_reads_the_pool():
    """The German and Italian gun pools: 218 + 281 = 499 Axis gun Replacement Points (all rows
    classed 'gun' -- excluding recce)."""
    assert replacements.axis_gun_total("german") == 218
    assert replacements.axis_gun_total("italian") == 281
    total = replacements.axis_gun_total("german") + replacements.axis_gun_total("italian")
    assert total == 499


def test_axis_equipment_per_gt_max_reads_the_20_66_windows():
    """[20.66]/[20.67] The most tank/gun Points the Axis may PLAN in a Game-Turn, summing the Max of
    every row of that class whose plan window contains the turn. Italian CV L.3 opens GT3, German
    PzII opens GT41; gun pool starts with Italian early guns at GT2."""
    # Italian tanks open early (CV L.3 at GT3), so GT1-2 has zero tank max
    assert replacements.axis_equipment_per_gt_max(2, "tank") == 0
    # At GT3, CV L.3 (max 5) and other Italian tanks become available
    tank_3 = replacements.axis_equipment_per_gt_max(3, "tank")
    assert tank_3 >= 5  # at least CV L.3's max
    # At GT41, German PzII (max 1) is added
    tank_40 = replacements.axis_equipment_per_gt_max(40, "tank")
    tank_41 = replacements.axis_equipment_per_gt_max(41, "tank")
    assert tank_41 > tank_40  # GT41 adds at least PzII
    # Gun pool: Italian light AA opens GT2 (tiers)
    gun_1 = replacements.axis_equipment_per_gt_max(1, "gun")
    assert gun_1 == 0  # No guns at GT1
    gun_2 = replacements.axis_equipment_per_gt_max(2, "gun")
    assert gun_2 > 0  # Guns available at GT2 (Italian light AA tiers start at 2)


def test_axis_equipment_tonnage_per_point():
    """[20.62] Each equipment type has its own tonnage charge: PzII 135 tons, PzIII E 190 tons, etc.
    The tonnage is read from the chart's Tonnage column."""
    assert replacements.axis_tonnage_per_point("german", "pz2") == 135
    assert replacements.axis_tonnage_per_point("german", "pz3e") == 190
    assert replacements.axis_tonnage_per_point("italian", "cv_l3") == 16


def test_axis_equipment_pool_totals():
    """Campaign-total caps for each class from the [20.66] pool."""
    assert replacements.axis_equipment_pool_total("tank") == 335  # 131 German + 204 Italian
    assert replacements.axis_equipment_pool_total("gun") == 499   # 218 German + 281 Italian


# --- Italian sub-cap enforcement (20.66 tiers) -------------------------------------------------------

def test_italian_infantry_has_a_window_100_point_pool_gt5_24():
    """[20.66] Italian infantry has a window-total cap of 100 RP across GT5-24, distinct from its
    per-GT rate changes (5 GT5-8, 10 GT9-24, 25 GT25+). The 100-point pool is split across two
    tiers: Tier 0 (GT5-8) marks the start with number=100, and Tier 1 (GT9-24) continues it with
    number=0 (indicating no new pool), both sharing the same 100-RP campaign total."""
    italian_inf = replacements.axis_item("italian", "infantry")
    tiers = italian_inf["tiers"]
    # Tier 0: the start of the 100-point window
    assert tiers[0]["number"] == 100
    assert tiers[0]["plan_first"] == 5
    assert tiers[0]["plan_last"] == 8
    assert tiers[0]["max"] == 5  # 5/GT
    # Tier 1: same window, higher rate, zero new pool (the '--' dash in the chart)
    assert tiers[1]["number"] == 0
    assert tiers[1]["plan_first"] == 9
    assert tiers[1]["plan_last"] == 24
    assert tiers[1]["max"] == 10  # 10/GT
    # Tier 2: new pool from GT25
    assert tiers[2]["number"] == 1100
    assert tiers[2]["plan_first"] == 25
    assert tiers[2]["plan_last"] is None
    assert tiers[2]["max"] == 25  # 25/GT


def test_period_max_is_per_gt_and_window_total_is_a_separate_cap():
    """[20.66] Italian infantry carries TWO distinct caps read by TWO functions: the per-Game-Turn RATE
    (_applicable_period_max -> the active tier's Max, all 'game_turn') and the 100-RP WINDOW TOTAL across
    GT5-24 (axis_italian_infantry_window_total). _applicable_period_max does NOT read the window total --
    it returns only (max, period) -- so the two are metered separately in the flow-in."""
    italian_inf = replacements.axis_item("italian", "infantry")
    for plan_turn in range(5, 25):
        max_per_gt, max_period = replacements._applicable_period_max(italian_inf, plan_turn)
        assert max_per_gt > 0 and max_period == "game_turn"         # the per-GT rate (5 then 10)
        assert replacements.axis_italian_infantry_window_total(plan_turn) == 100   # the separate cap
    # outside GT5-24 the window total is not in force (None); the per-GT rate continues (25/GT from GT25)
    assert replacements.axis_italian_infantry_window_total(4) is None
    assert replacements.axis_italian_infantry_window_total(25) is None
    assert replacements._applicable_period_max(italian_inf, 25)[0] == 25


# --- the equipment bring-in beat harness (placeholder structure) ----------------------------------

def _tank(uid, hex_, strength, max_toe):
    """A depleted Axis tank unit -- is_tank so organization.replacement_kind maps it to the 'tank' pool."""
    return Unit(uid, Side.AXIS, hex_, (StepRecord("s", strength),),
                is_tank=True, mobility=Mobility.VEHICLE, cpa=8, stacking_points=2, oca=1, dca=2,
                nationality="GE", is_combat=True, max_toe=max_toe)


def _inf(uid, hex_, strength, max_toe):
    """A depleted Axis infantry unit -- replacement_kind maps a plain combat counter to
    'any_other_infantry', the 'infantry' pool."""
    return Unit(uid, Side.AXIS, hex_, (StepRecord("s", strength),),
                mobility=Mobility.FOOT, cpa=8, stacking_points=2, oca=1, dca=2,
                nationality="IT", is_combat=True, max_toe=max_toe)


def _dump(sid="AX-Port", side=Side.AXIS, hex_=(0, 0), **pools):
    base = {"ammo": 0, "fuel": 0, "stores": 0, "water": 0}
    return SupplyUnit(sid, side, hex_, **{**base, **pools})


def _state(convoys, units=(), *, turn=50, production=True, supplies=None,
           pool=None, training=None, shipped=None) -> GameState:
    """A campaign-shaped state for the equipment bring-in: Axis convoy, depleted Axis armour,
    replacement_production gate. turn=50 so tank pool (opens GT41) is open. `shipped` seeds the lifetime
    flow-in ledger (replacements_shipped) so the campaign-total / window caps can be exercised."""
    dumps = tuple(supplies) if supplies is not None else (_dump(),)
    hexes = {u.hex for u in units} | {d.hex for d in dumps} | {(0, 0)}
    tmap = TerrainMap(terrain={h: Terrain.CLEAR for h in hexes}, fortifications={})
    return GameState(
        turn=turn, max_turns=111, phase=Phase.LOGISTICS, active_side=Side.SYSTEM, seed=1,
        weather="clear", vp=VP(), terrain=tmap, control={}, units=tuple(units),
        target_hex=(0, 0), supplies=dumps, consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: getattr(dumps[0], c.lower()) for c in supply.COMMODITIES},
        convoys=tuple(convoys), stage=1, replacement_production=production,
        replacement_pool=dict(pool or {}), replacement_training={k: dict(v) for k, v in (training or {}).items()},
        replacements_shipped=dict(shipped or {}))


def _axis_conv(turn_plus_1, tons):
    """The forward Benghazi lane convoy (arrival == plan turn + 1)."""
    return Convoy(f"axis-conv-t{turn_plus_1}", Side.AXIS, turn_plus_1, "3", "AX-Port", {}, tons=tons)


def _plan(state, policy=None):
    r = _Run(state)
    _convoy_planning(r, {Side.AXIS: policy or Policy(), Side.ALLIED: Policy()})
    return r


def _rp_events(r):
    return [e for e in r.events if e.kind == EventKind.REPLACEMENTS_PRODUCED]


def _planned(r, convoy_id):
    return next(e.payload for e in r.events
               if e.kind == EventKind.CONVOY_PLANNED and e.payload["convoy_id"] == convoy_id)


# --- tests for the equipment bring-in (TDD: write test first) ------------------------------------

def test_equipment_bring_in_charges_its_real_per_type_tonnage():
    """[20.62] Equipment Replacement Points are charged their REAL per-type Tonnage, not an average.
    At GT50 the cheapest open tank is the Italian CV L.3 at 16 tons, so electing one tank Point charges
    exactly 16 (the chart cell) and two charge 32; the average of the open tank types (16/28/70/135) is
    62, which the charge is NOT. The convoy allowance binds on that real Tonnage: only one 16-ton CV L.3
    fits in 20 tons (the next-cheapest type is 28), so a large want yields a single point at its real
    charge."""
    pts, tons = replacements.axis_equipment_election(50, "tank", 1, 10**6)
    assert (pts, tons) == (1, 16) == (1, replacements.axis_tonnage_per_point("italian", "cv_l3"))
    assert replacements.axis_equipment_election(50, "tank", 2, 10**6) == (2, 32)
    open_tank_tonnages = [it["tonnage"] for ch in ("german", "italian")
                          for it in replacements.axis_items(ch) if it.get("class") == "tank"
                          and replacements._applicable_period_max(it, 50)[0] > 0]
    assert tons != sum(open_tank_tonnages) / len(open_tank_tonnages)   # not the invented average
    assert replacements.axis_equipment_election(50, "tank", 99, 20) == (1, 16)


def test_equipment_per_gt_max_bounds_the_bring_in():
    """[20.66]/[20.67] The election cannot exceed the summed per-Game-Turn Max of the open types. With
    the deficit (want) and the convoy allowance both non-binding, the points elected equal
    axis_equipment_per_gt_max -- each type capped at its own printed Max. Before a class's first window
    opens nothing is electable (CV L.3 opens GT3, so GT2 is empty)."""
    for pool_class in ("tank", "gun"):
        cap = replacements.axis_equipment_per_gt_max(50, pool_class)
        assert cap > 0
        pts, _tons = replacements.axis_equipment_election(50, pool_class, 10**6, 10**9)
        assert pts == cap
    assert replacements.axis_equipment_election(2, "tank", 10**6, 10**9) == (0, 0)


def test_equipment_campaign_total_caps_the_lifetime_bring_in():
    """[20.66] The engine bounds the election by the class campaign total (335 tank / 499 gun) minus what
    has shipped, so a pool already at its lifetime '#' brings in nothing more, and one Point of headroom
    admits at most one more Point."""
    assert replacements.axis_equipment_pool_total("tank") == 335
    tank = _tank("t1", (1, 1), 2, 8)                                   # headroom 6, so the pool binds
    full = _plan(_state([_axis_conv(51, 5000)], [tank], turn=50, shipped={"AXIS/tank": 335}))
    assert not [e for e in _rp_events(full) if e.payload["type"] == "tank"]
    near = _plan(_state([_axis_conv(51, 5000)], [tank], turn=50, shipped={"AXIS/tank": 334}))
    tank_rp = [e for e in _rp_events(near) if e.payload["type"] == "tank"]
    assert sum(e.payload["points"] for e in tank_rp) == 1


def test_italian_infantry_sub_cap_enforces_100_points_in_gt5_24():
    """[20.66] Italian infantry's 100-Point WINDOW pool (GT5-24) caps the cumulative bring-in separately
    from the per-Game-Turn rate. With 100 already shipped inside the window, no more infantry is planned
    even though the per-GT rate (10) and a deep deficit would otherwise allow it; with 96 shipped, at
    most the 4 remaining window Points come in."""
    inf = _inf("i1", (1, 1), 1, 60)                                    # headroom 59 so the caps bind
    full = _plan(_state([_axis_conv(16, 5000)], [inf], turn=15, shipped={"AXIS/infantry": 100}))
    assert not [e for e in _rp_events(full) if e.payload["type"] == "infantry"]
    near = _plan(_state([_axis_conv(16, 5000)], [inf], turn=15, shipped={"AXIS/infantry": 96}))
    inf_rp = [e for e in _rp_events(near) if e.payload["type"] == "infantry"]
    assert 0 < sum(e.payload["points"] for e in inf_rp) <= 4
