"""[20.78C] THE COMMONWEALTH EQUIPMENT FLOW-IN -- the last unbuilt lever of Gate 7A.

Block 7.2a built the Commonwealth INFANTRY production stream and Block A generalized THE SPEND
to every mass class (infantry/tank/gun) for both sides -- but nothing FILLED the Commonwealth
tank/gun pools, so the [20.78C] chart (62 Shermans, 250 25-pounders, ...) produced on paper and
never reached the board. This is the producer that closes it.

    20.73  Infantry and Trucks are the RANDOM streams; everything on the [20.78C] Production Chart
           is ELECTED (draw-at-will), like the Axis Pool.
    20.75  "The Commonwealth Player has no Shipping Problems; his Replacement Points simply
           arrive." -- FREE: no tonnage, no convoy, no interdiction (the mirror of the Axis coupling).

Same shape as the Axis infantry bring-in (engine._axis_replacement_bring_in), minus the tonnage:
heal the current tank/gun deficit, bounded by the [20.78C] per-Game-Turn Max, the campaign-total
'#', and what is already in the pipeline; the points enter the [20.43] Training ledger with the
owner-ruled FOUR-Game-Turn Commonwealth lead + the [17.6] delay, from which the spend heals the army.
"""
from __future__ import annotations

import game.supply as supply
from game import organization, replacements
from game.engine import _cw_equipment_production, _Run
from game.events import EventKind, Phase, Side
from game.movement import TerrainMap
from game.state import GameState, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain


# --- [20.78C] the chart readers -------------------------------------------------------------------

def test_cw_equipment_class_total_sums_the_20_78C_by_class():
    """The campaign-total Replacement Points on the [20.78C] chart, summed by class -- the lifetime
    ceiling the flow-in may not exceed (owner ruling 2: tank_total 332, not the plan's 306)."""
    assert replacements.commonwealth_equipment_class_total("tank") == 332
    assert replacements.commonwealth_equipment_class_total("gun") == 536
    assert replacements.commonwealth_equipment_class_total("recce") == 90
    # tank + gun + recce = the chart's own equipment_total (958)
    assert (replacements.commonwealth_equipment_class_total("tank")
            + replacements.commonwealth_equipment_class_total("gun")
            + replacements.commonwealth_equipment_class_total("recce")) == 958


def test_cw_equipment_per_gt_max_reads_the_plan_windows():
    """[20.78C] The most tank/gun Points that may be PLANNED in a Game-Turn -- the sum of the Max of
    every chart item whose plan window (plan_first..plan_last) contains the turn. The printed Max is
    taken as a per-Game-Turn ceiling (see the reader's flag on max_period)."""
    # tanks: GT3 only the earliest cruisers (Mk VI 3 + A9 2 + A10 3); GT9 adds A13 2 + Matilda 2
    assert replacements.commonwealth_equipment_per_gt_max(3, "tank") == 3 + 2 + 3
    assert replacements.commonwealth_equipment_per_gt_max(9, "tank") == 3 + 2 + 3 + 2 + 2
    # GT89: the Shermans open (12), alongside Grant 8, Crusader III 6, Valentine 3
    assert replacements.commonwealth_equipment_per_gt_max(89, "tank") == 12 + 8 + 6 + 3
    # GT90: the lone Churchill (Max dash -> its number, 1) joins
    assert replacements.commonwealth_equipment_per_gt_max(90, "tank") == 12 + 8 + 6 + 3 + 1
    # guns: nothing before the 2-pounder opens (GT5); GT11 the 25-pounder era
    assert replacements.commonwealth_equipment_per_gt_max(3, "gun") == 0
    assert replacements.commonwealth_equipment_per_gt_max(5, "gun") == 5           # 2-pounder only
    assert replacements.commonwealth_equipment_per_gt_max(11, "gun") == 1 + 1 + 4 + 5


# --- the flow-in beat -----------------------------------------------------------------------------

def _u(uid, **kw):
    kw.setdefault("nationality", "CW")
    return Unit(uid, kw.pop("side", Side.ALLIED), kw.pop("hex", (0, 0)),
                (StepRecord("s", kw.pop("strength", 8)),),
                mobility=Mobility.FOOT, cpa=kw.pop("cpa", 10),
                stacking_points=kw.pop("sp", 1), oca=kw.pop("oca", 1), dca=kw.pop("dca", 2), **kw)


def _tank(uid, strength, max_toe, **kw):
    return _u(uid, strength=strength, max_toe=max_toe, is_tank=True, is_combat=True, **kw)


def _state(units, *, turn=89, production=True, pool=None, training=None, shipped=None) -> GameState:
    hexes = {u.hex for u in units} | {(0, 0)}
    tmap = TerrainMap(terrain={h: Terrain.CLEAR for h in hexes}, fortifications={})
    return GameState(
        turn=turn, max_turns=111, phase=Phase.ORGANIZATION, active_side=Side.SYSTEM, seed=1941,
        weather="clear", vp=VP(), terrain=tmap, control={}, units=tuple(units), target_hex=(0, 0),
        supplies=(), consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES}, stage=1,
        replacement_pool=dict(pool or {}), replacement_production=production,
        replacement_training={k: dict(v) for k, v in (training or {}).items()},
        replacements_shipped=dict(shipped or {}))


def _rp(r):
    return [e for e in r.events if e.kind == EventKind.REPLACEMENTS_PRODUCED]


def test_the_flow_in_heals_the_tank_deficit_free_of_tonnage():
    """A depleted Commonwealth tank battalion draws Sherman-era tank Points -- deficit 4, well under
    the GT89 rate ceiling and the 332 pool, so exactly 4 are brought in, FREE (no tons_charged)."""
    r = _Run(_state([_tank("T", strength=4, max_toe=8)], turn=89))
    _cw_equipment_production(r)
    rp = _rp(r)
    assert len(rp) == 1
    p = rp[0].payload
    assert (p["side"], p["type"], p["points"]) == (Side.ALLIED.value, "tank", 4)
    assert "tons_charged" not in p                          # 20.75: the Commonwealth pays nothing
    assert rp[0].side is Side.ALLIED


def test_the_flow_in_lands_with_the_four_game_turn_lead_and_tank_training():
    """[20.21]/[20.78B] owner ruling 1: the Commonwealth lead is FOUR Game-Turns; [17.6] then trains
    a tank Point SIX Operations Stages = two Game-Turns. So a Point planned GT89 arrives GT93 and
    matures GT95 -- into the ALLIED/tank Training ledger, not yet absorbable, and marked shipped."""
    r = _Run(_state([_tank("T", strength=4, max_toe=8)], turn=89))
    _cw_equipment_production(r)
    p = _rp(r)[0].payload
    assert p["plan_turn"] == 89 and p["arrival_turn"] == 93 and p["mature_turn"] == 95
    assert r.state.replacement_training["ALLIED/tank"] == {95: 4}
    assert r.state.replacements_available("ALLIED/tank") == 0     # still training
    assert r.state.replacements_shipped["ALLIED/tank"] == 4       # lifetime ledger


def test_the_per_game_turn_max_bounds_a_huge_deficit():
    """[20.78C] Even a bottomless deficit cannot plan more than the chart's per-Game-Turn Max -- at
    GT11 the gun rate is 25-pounder 4 + 2-pounder 5 + the two AA 1+1 = 11."""
    gun = _u("G", strength=1, max_toe=200, barrage=3, vulnerability=2, is_combat=True)
    r = _Run(_state([gun], turn=11))
    _cw_equipment_production(r)
    p = _rp(r)[0].payload
    assert p["points"] == 11 and p["type"] == "gun"


def test_the_campaign_total_caps_the_lifetime_bring_in():
    """[20.78C] The Commonwealth may bring in only 332 tank Points across the whole war. With 330
    already shipped, a deep deficit takes only the last 2."""
    r = _Run(_state([_tank("T", strength=1, max_toe=200)], turn=89, shipped={"ALLIED/tank": 330}))
    _cw_equipment_production(r)
    assert _rp(r)[0].payload["points"] == 2
    assert r.state.replacements_shipped["ALLIED/tank"] == 332
    dry = _Run(_state([_tank("T", strength=1, max_toe=200)], turn=89, shipped={"ALLIED/tank": 332}))
    _cw_equipment_production(dry)
    assert _rp(dry) == []                                   # pool exhausted


def test_pipeline_awareness_does_not_re_bring_points_already_in_flight():
    """The election subtracts what is already absorbable plus what is still Training, so the same
    deficit is not re-shipped every Game-Turn while the first batch matures (deficit 8, 5 in flight)."""
    r = _Run(_state([_tank("T", strength=2, max_toe=10)], turn=89,
                    pool={"ALLIED/tank": 3}, training={"ALLIED/tank": {95: 2}}))
    _cw_equipment_production(r)
    assert _rp(r)[0].payload["points"] == 8 - 5


def test_a_full_strength_army_brings_in_nothing():
    """No deficit -> no flow-in, a pure identity (no Phase.LOGISTICS beat)."""
    r = _Run(_state([_tank("T", strength=8, max_toe=8)], turn=89))
    _cw_equipment_production(r)
    assert _rp(r) == []


def test_gated_off_without_the_production_economy():
    """Gated exactly as the rest of the rule-20 economy: the two Desert Fox benchmarks
    (replacement_production False) bring in nothing and stay byte-identical."""
    r = _Run(_state([_tank("T", strength=4, max_toe=8)], turn=89, production=False))
    _cw_equipment_production(r)
    assert _rp(r) == []


def test_before_a_class_window_opens_nothing_is_brought_in():
    """[20.78C] The gun chart opens no earlier than the 2-pounder (GT5). On GT3 a depleted gun
    brings in nothing, however deep its deficit."""
    gun = _u("G", strength=1, max_toe=40, barrage=3, vulnerability=2, is_combat=True)
    r = _Run(_state([gun], turn=3))
    _cw_equipment_production(r)
    assert _rp(r) == []
