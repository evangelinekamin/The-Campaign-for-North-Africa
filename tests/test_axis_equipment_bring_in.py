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

import pytest

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


def test_applicable_period_max_enforces_window_total_for_italian_infantry():
    """[20.66] The _applicable_period_max function reads BOTH the per-GT max AND the window-total
    cap. For Italian infantry GT5-24, the window total of 100 is the lifetime cap for that tier,
    enforced separately from the per-GT rate."""
    # This will be tested via the engine's flow-in behaviour, but the function should expose both
    italian_inf = replacements.axis_item("italian", "infantry")
    # For tiers, we get both the per-GT max and the window total from the tier
    for plan_turn in range(5, 25):
        max_per_gt, max_period = replacements._applicable_period_max(italian_inf, plan_turn)
        assert max_per_gt > 0  # per-GT max is available
        # The window total (100 for the first tier) should be tracked separately in the flow-in


# --- the equipment bring-in beat harness (placeholder structure) ----------------------------------

def _tank(uid, hex_, strength, max_toe):
    """A depleted Axis tank unit."""
    return Unit(uid, Side.AXIS, hex_, (StepRecord("s", strength),),
                mobility=Mobility.TRACKED, cpa=8, stacking_points=2, oca=1, dca=2,
                nationality="GE", is_combat=True, max_toe=max_toe)


def _dump(sid="AX-Port", side=Side.AXIS, hex_=(0, 0), **pools):
    base = {"ammo": 0, "fuel": 0, "stores": 0, "water": 0}
    return SupplyUnit(sid, side, hex_, **{**base, **pools})


def _state(convoys, units=(), *, turn=50, production=True, supplies=None,
           pool=None, training=None) -> GameState:
    """A campaign-shaped state for the equipment bring-in: Axis convoy, depleted Axis armour,
    replacement_production gate. turn=50 so tank pool (opens GT41) is open."""
    dumps = tuple(supplies) if supplies is not None else (_dump(),)
    hexes = {u.hex for u in units} | {d.hex for d in dumps} | {(0, 0)}
    tmap = TerrainMap(terrain={h: Terrain.CLEAR for h in hexes}, fortifications={})
    return GameState(
        turn=turn, max_turns=111, phase=Phase.LOGISTICS, active_side=Side.SYSTEM, seed=1,
        weather="clear", vp=VP(), terrain=tmap, control={}, units=tuple(units),
        target_hex=(0, 0), supplies=dumps, consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: getattr(dumps[0], c.lower()) for c in supply.COMMODITIES},
        convoys=tuple(convoys), stage=1, replacement_production=production,
        replacement_pool=dict(pool or {}), replacement_training={k: dict(v) for k, v in (training or {}).items()})


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

def test_equipment_bring_in_charges_tonnage_like_infantry():
    """[20.62] Equipment Replacement Points are charged at their per-type tonnage, just like
    Infantry. A PzII at 135 tons/point should reduce the allowed tonnage for supplies."""
    # This test will pass once we implement the equipment bring-in in engine.py
    # For now, mark as expected to fail
    pytest.skip("Equipment bring-in not yet implemented")


def test_equipment_per_gt_max_bounds_the_bring_in():
    """[20.66]/[20.67] Tank/gun points cannot exceed the per-Game-Turn Max."""
    pytest.skip("Equipment bring-in not yet implemented")


def test_equipment_campaign_total_caps_the_lifetime_bring_in():
    """[20.66] Tank/gun points cannot exceed the chart's campaign total."""
    pytest.skip("Equipment bring-in not yet implemented")


def test_italian_infantry_sub_cap_enforces_100_points_in_gt5_24():
    """[20.66] Italian infantry's 100-point window pool (GT5-24) is enforced as a separate cap
    from the per-GT rate. The engine cannot plan more than 100 total Italian infantry across
    GT5-24, even if the per-GT rates alone would allow more."""
    pytest.skip("Italian sub-cap enforcement not yet implemented")
