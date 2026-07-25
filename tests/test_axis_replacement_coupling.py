"""[20.62]/[20.64]/[20.66] THE AXIS CONVOY COUPLING -- Block B of Gate 7A.

The mechanism that makes the Axis faucet PAY for its army's healing. Where the Commonwealth's
Replacement Points simply arrive ([20.75], free), every Axis Replacement Point is counted against
the [56.5] Shipping Tonnage allowance ([20.62]: 30 tons per Infantry Point, the named errata) at
PRIORITY over fuel/ammunition/stores ([20.64]) -- so a Game-Turn heavy on replacements ships less
supply.

    20.62  "each Replacement Point is counted against the Shipping Tonnage allowance ... 10 Italian
            Infantry Replacement Points would need [300] Tons of Shipping." (errata: 30, not 35)
    20.64  "Replacement Points have priority in Shipping Space over any type of supplies."
    20.75  "The Commonwealth Player has no Shipping Problems; his Replacement Points simply arrive."
    56.24  "10 Infantry Points ... this would subtract 300 tons from the available tonnage for that
            Game-Turn."

This block builds the CHARGE and a minimal, faithful INFANTRY flow-in as its vehicle (the [20.66]
German 400 + Italian 1,200 infantry pool). The Axis brings in the Infantry Replacement Points his
depleted army needs; their tonnage comes off the convoy allowance first, and the points enter the
[20.43] Training ledger with the [20.63] two-Game-Turn lead, from which Block A's spend heals the
army. Tank/gun Axis flow-in is DEFERRED (the per-type tonnage awaits the [20.3]/class reconciliation
data/replacements.json flags); the charge itself is class-agnostic and lands them cheaply later.
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


# --- [20.66] the Axis infantry pool readers -------------------------------------------------------

def test_axis_infantry_tonnage_is_the_30_ton_errata():
    """[20.62] errata (owner ruling 6): 30 Shipping Tons per Axis Infantry Replacement Point, both
    German and Italian -- read from the chart's own Tonnage column, not a literal."""
    assert replacements.axis_infantry_tonnage() == 30
    assert replacements.axis_tonnage_per_point("german", "infantry") == 30
    assert replacements.axis_tonnage_per_point("italian", "infantry") == 30


def test_axis_infantry_per_gt_max_reads_the_20_66_windows_and_tiers():
    """[20.66]/[20.67] The most INFANTRY Points the Axis may PLAN in a Game-Turn: the Italian pool
    opens GT5 (tier 5/10/25 across GT5-8 / GT9-24 / GT25+), the German pool GT38 (12/GT). Before GT5
    nothing infantry may be planned."""
    assert replacements.axis_infantry_per_gt_max(4) == 0     # neither pool open yet
    assert replacements.axis_infantry_per_gt_max(5) == 5     # Italian tier 0 only
    assert replacements.axis_infantry_per_gt_max(8) == 5
    assert replacements.axis_infantry_per_gt_max(9) == 10    # Italian tier 1
    assert replacements.axis_infantry_per_gt_max(24) == 10
    assert replacements.axis_infantry_per_gt_max(25) == 25   # Italian tier 2
    assert replacements.axis_infantry_per_gt_max(37) == 25
    assert replacements.axis_infantry_per_gt_max(38) == 37   # + German 12 from GT38
    assert replacements.axis_infantry_per_gt_max(111) == 37


# --- the coupling beat harness --------------------------------------------------------------------

def _inf(uid, hex_, strength, max_toe):
    """A depleted Axis infantry battalion -- replacement_kind => 'any_other_infantry'."""
    return Unit(uid, Side.AXIS, hex_, (StepRecord("s", strength),),
                mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=1, dca=2,
                nationality="GE", is_combat=True, max_toe=max_toe)


def _dump(sid="AX-Port", side=Side.AXIS, hex_=(0, 0), **pools):
    base = {"ammo": 0, "fuel": 0, "stores": 0, "water": 0}
    return SupplyUnit(sid, side, hex_, **{**base, **pools})


def _state(convoys, units=(), *, turn=30, production=True, supplies=None,
           pool=None, training=None) -> GameState:
    """A campaign-shaped state the coupling reads: an Axis convoy to charge, depleted Axis infantry
    (the deficit), the replacement_production gate. turn=30 so the Italian pool (25/GT) is open."""
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
    """The forward Benghazi lane convoy (arrival == plan turn + 1), lane '3', the one charged."""
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


# --- the charge -----------------------------------------------------------------------------------

def test_the_charge_comes_off_the_allowance_before_the_supply_split():
    """[20.62]/[20.64] A depleted Axis army brings in Infantry Points; their 30-ton-per-point charge
    is taken off the convoy allowance FIRST, so the supply split sees only what is left."""
    army = [_inf("A", (1, 1), strength=4, max_toe=8)]      # deficit 4 -> 4 points -> 120 tons
    r = _plan(_state([_axis_conv(31, 7500)], army, turn=30))
    rp = _rp_events(r)
    assert len(rp) == 1
    p = rp[0].payload
    assert p["side"] == "AXIS" and p["type"] == "infantry" and p["points"] == 4
    assert p["tons_charged"] == 4 * 30 == 120
    plan = _planned(r, "axis-conv-t31")
    assert plan["allowed_tons"] == 7500 - 120                # supplies get the remainder
    assert sum(plan["tons_by"].values()) == pytest.approx(7500 - 120)


def test_a_heavier_deficit_squeezes_supply_harder():
    """[20.64] priority: the more the army needs healing, the less fuel/ammo the convoy carries."""
    light = _plan(_state([_axis_conv(31, 7500)], [_inf("A", (1, 1), 7, 8)], turn=30))   # deficit 1
    heavy = _plan(_state([_axis_conv(31, 7500)], [_inf("A", (1, 1), 2, 20)], turn=30))  # deficit 18
    lo = _planned(light, "axis-conv-t31")["allowed_tons"]
    hi = _planned(heavy, "axis-conv-t31")["allowed_tons"]
    assert hi < lo <= 7500
    assert _rp_events(heavy)[0].payload["points"] > _rp_events(light)[0].payload["points"]


def test_replacements_win_and_supplies_are_squeezed_to_nothing_when_tonnage_is_tight():
    """If the tonnage cannot cover both, the rule's priority means REPLACEMENTS win: the points are
    NOT dropped, supplies are what gets squeezed. Bounded by the ship (56.27) -- points may not
    exceed what the allowance can carry."""
    army = [_inf("A", (1, 1), strength=1, max_toe=40)]      # deficit 39
    r = _plan(_state([_axis_conv(31, 300)], army, turn=30))  # 300 t / 30 = 10 points fit the ship
    p = _rp_events(r)[0].payload
    assert p["points"] == 10 and p["tons_charged"] == 300    # replacements take the whole allowance
    plan = _planned(r, "axis-conv-t31")
    assert plan["allowed_tons"] == 0                         # supplies squeezed to nothing
    assert plan["cargo"] == {} and plan["tons_by"] == {}


def test_the_flow_in_enters_training_with_the_20_63_two_game_turn_lead():
    """[20.63] planned 2 Game-Turns ahead; [20.43]/[17.6] then trains one more (infantry 3 OpStages
    = 1 GT). So a point planned on GT30 arrives GT32 and matures GT33 -- into the AXIS/infantry
    Training ledger, from which Block A's spend heals the army."""
    r = _plan(_state([_axis_conv(31, 7500)], [_inf("A", (1, 1), 4, 8)], turn=30))
    p = _rp_events(r)[0].payload
    assert p["plan_turn"] == 30 and p["arrival_turn"] == 32 and p["mature_turn"] == 33
    assert r.state.replacement_training["AXIS/infantry"] == {33: 4}
    assert r.state.replacements_available("AXIS/infantry") == 0   # still training, not absorbable


def test_pipeline_awareness_does_not_re_ship_points_already_in_flight():
    """The election subtracts what is already in the pipeline (absorbable pool + still training), so
    the same deficit is not shipped every Game-Turn while the first batch matures."""
    army = [_inf("A", (1, 1), strength=2, max_toe=10)]      # deficit 8
    st = _state([_axis_conv(31, 7500)], army, turn=30,
                pool={"AXIS/infantry": 3}, training={"AXIS/infantry": {32: 2}})   # 5 in flight
    r = _plan(st)
    assert _rp_events(r)[0].payload["points"] == 8 - 5      # only the shortfall


def test_a_full_strength_army_ships_no_replacements_and_pays_nothing():
    """No deficit, no charge -- the allowance is wholly the supply Player's, byte-identical to the
    pre-coupling path."""
    r = _plan(_state([_axis_conv(31, 7500)], [_inf("A", (1, 1), 8, 8)], turn=30))
    assert _rp_events(r) == []
    assert _planned(r, "axis-conv-t31")["allowed_tons"] == 7500


def test_before_the_pool_opens_nothing_is_brought_in():
    """[20.66] The Italian infantry pool opens GT5, the German GT38. On GT3 (plan turn 3) neither is
    open, so a depleted army still ships no infantry and pays nothing."""
    r = _plan(_state([_axis_conv(4, 7500)], [_inf("A", (1, 1), 2, 8)], turn=3))
    assert _rp_events(r) == []
    assert _planned(r, "axis-conv-t4")["allowed_tons"] == 7500


def test_the_per_game_turn_cap_bounds_the_bring_in():
    """[20.67] Even a huge deficit cannot ship more than the pool's per-Game-Turn Max -- 25 Italian
    Points on GT30 (the German pool opens GT38)."""
    army = [_inf("A", (1, 1), strength=1, max_toe=200)]     # deficit 199
    r = _plan(_state([_axis_conv(31, 100000)], army, turn=30))   # tonnage not the binding limit
    assert _rp_events(r)[0].payload["points"] == 25         # the GT30 per-GT ceiling


def _with_shipped(st, points):
    return st.__class__(**{**{f: getattr(st, f) for f in st.__dataclass_fields__},
                           "replacements_shipped": {"AXIS/infantry": points}})


def test_the_20_66_campaign_total_caps_the_lifetime_bring_in():
    """[20.66] The Axis may bring in only 1,600 Infantry Points across the whole war (German 400 +
    Italian 1,200). With 1,590 already shipped, the deep deficit takes only the last 10 -- and the
    ledger folds forward off the event to the cap. Once 1,600 are shipped, the pool is dry and no
    convoy brings in more, however depleted the army."""
    army = [_inf("A", (1, 1), strength=1, max_toe=200)]     # deficit 199, far over the remaining 10
    r = _plan(_with_shipped(_state([_axis_conv(31, 100000)], army, turn=30), 1590))
    assert _rp_events(r)[0].payload["points"] == 1600 - 1590         # only the pool's remainder
    assert r.state.replacements_shipped["AXIS/infantry"] == 1600     # ledger folded to the cap
    dry = _plan(_with_shipped(_state([_axis_conv(31, 100000)], army, turn=30), 1600))
    assert _rp_events(dry) == []                                     # pool exhausted, nothing ships
    assert _planned(dry, "axis-conv-t31")["allowed_tons"] == 100000  # supplies get the whole allowance


# --- gating & determinism -------------------------------------------------------------------------

def test_the_coupling_is_inert_without_replacement_production():
    """Gated exactly as the rest of the rule-20 economy: a scenario that does not model the CW
    Production system (the two Desert Fox benchmarks) charges nothing and stays byte-identical."""
    army = [_inf("A", (1, 1), 4, 8)]
    r = _plan(_state([_axis_conv(31, 7500)], army, turn=30, production=False))
    assert _rp_events(r) == []
    assert _planned(r, "axis-conv-t31")["allowed_tons"] == 7500


def test_only_the_forward_convoy_is_charged_on_the_opening_double_plan():
    """56.0's opening Game-Turn plans TWICE (the curtain-raiser it inherits + one turn ahead). The
    replacement charge attaches only to the FORWARD convoy (arrival == turn+1); the curtain-raiser,
    whose tonnage was booked before the game began, is not charged. (turn=30 so the [20.66] pool is
    open -- the historical opening turn GT1 predates it, but the gate is general.)"""
    st = _state([_axis_conv(30, 7500), _axis_conv(31, 7500)], [_inf("A", (1, 1), 4, 8)], turn=30)
    # turn=30 == initial turn: _convoy_planning plans arrival 30 (curtain) and arrival 31 (forward).
    r = _plan(st)
    rp = _rp_events(r)
    assert len(rp) == 1 and rp[0].payload["convoy_id"] == "axis-conv-t31"
    assert _planned(r, "axis-conv-t30")["allowed_tons"] == 7500         # curtain-raiser untouched
    assert _planned(r, "axis-conv-t31")["allowed_tons"] < 7500          # forward one charged


def test_the_commonwealth_convoy_is_never_charged():
    """[20.75] The Commonwealth has no shipping problem. Only the Axis lane is coupled; a CW convoy
    with an allowance is planned free of any replacement charge."""
    cw = Convoy("cw-x-t2", Side.ALLIED, 2, "CW-X", "AX-Port", {}, tons=5000)
    r = _plan(_state([cw], [_inf("A", (1, 1), 4, 8)], turn=1))
    assert _rp_events(r) == []
    assert _planned(r, "cw-x-t2")["allowed_tons"] == 5000


# --- end to end -----------------------------------------------------------------------------------

def test_the_campaign_charges_axis_replacements_against_the_convoy():
    """On the real campaign the Axis brings in Infantry and Equipment Replacement Points and their
    tonnage is charged against the Benghazi convoy -- the mechanism that makes the faucet pay for the
    army's healing. And it is AXIS-only: the Commonwealth ships its replacements free."""
    res = run(campaign(seed=1941, max_turns=45),
              CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    axis_rp = [e for e in res.events if e.kind == EventKind.REPLACEMENTS_PRODUCED
               and e.payload["side"] == "AXIS"]
    assert axis_rp, "the Axis must bring in Replacement Points (infantry/tank/gun) once pools open"
    # Axis brings in infantry (30 t/pt) and equipment (tank/gun, per-type tonnage)
    assert any(e.payload["type"] == "infantry" for e in axis_rp), "infantry RPs are brought in"
    # Infantry events charge 30 t/pt
    infantry = [e for e in axis_rp if e.payload["type"] == "infantry"]
    assert all(e.payload["tons_charged"] == e.payload["points"] * 30 for e in infantry)
    assert sum(e.payload["tons_charged"] for e in axis_rp) > 0
    # the charge sits ON the convoy allowance: some Axis sailing shows allowed_tons < its gross tons
    squeezed = [e.payload for e in res.events if e.kind == EventKind.CONVOY_PLANNED
                and e.payload["convoy_id"].startswith("axis-conv-")
                and e.payload["allowed_tons"] < e.payload["tons"]]
    assert squeezed, "a replacement-heavy Game-Turn must ship less supply"
