"""[56.21] / [56.22] THE AXIS CONVOY PLANNING PHASE -- Phase 5.5, and the death of invention I11.

    56.0   "Convoys are planned ONE GAME-TURN IN ADVANCE and the route of the convoy (the shipping
            lane it will use) is also chosen at that time."
    56.21  "The Axis Convoy Capacity Table refers the Axis Player, by month and year, to the Tonnage
            Capacity Table for that particular month. The figures given on the Tonnage Determination
            Table are the tonnage of supplies that the Axis may ship in that Game-Turn (FOR WHICH HE
            IS PLANNING)."
    56.22  "Having determined the allowable tonnage for a given Game-Turn, THE AXIS PLAYER MAY NOW
            PLAN TO SHIP ANY AMOUNTS (within the limits of allowable tonnage) OF FUEL, AMMUNITION,
            AND STORES THAT HE WISHES. They are available (for game purposes) in unlimited
            quantities in Europe."

What stood here before was `scenario._CONVOY_SPLIT_56_22 = {FUEL 0.60, AMMO 0.25, STORES 0.15}` --
a constant, applied at scenario construction, to every Axis convoy of a hundred and eleven
Game-Turns. The port plan calls it invention I11 and calls the decision it replaced "the Axis
Player's single most important recurring choice". The first test in this file is that the constant
is gone, because a deleted invention that comes back is worse than one that never left.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import game.scenario as scenario
import game.supply as supply
from game.campaign_policy import (CampaignAxisPolicy, CampaignCommonwealthPolicy,
                                  convoy_plan_doctrine)
from game.engine import _convoy_planning, _Run, run
from game.events import EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import Policy
from game.scenario import campaign, rommels_arrival
from game.state import Convoy, GameState, SupplyUnit, VP
from game.terrain import Terrain


# --- the invention is gone ------------------------------------------------------------------------

def test_the_hardcoded_commodity_split_no_longer_exists():
    """I11, deleted. A constant in the scenario builder is not a decision, and 56.22 makes this one
    the Axis Player's, taken afresh for every sailing."""
    assert not hasattr(scenario, "_CONVOY_SPLIT_56_22")
    assert not hasattr(scenario, "_axis_convoy_cargo")
    assert not hasattr(scenario, "_campaign_axis_cargo")


def test_the_axis_lane_now_sails_with_an_ALLOWANCE_and_no_manifest():
    """[56.21] The charts fix the TONNAGE (56.4 x 56.5 x a die, still in the scenario builder where
    the timetable lives); what goes into it is decided later, by a player. Every other lane -- the
    Tobruk ferry, the Commonwealth railway -- keeps its fixed manifest and is untouched."""
    st = campaign(seed=1, max_turns=8)
    axis_lane = [c for c in st.convoys if c.id.startswith("axis-conv-")]
    assert axis_lane, "the campaign must still sail the Mediterranean convoy"
    assert all(c.tons > 0 and c.cargo == {} for c in axis_lane)
    others = [c for c in st.convoys if not c.id.startswith("axis-conv-")]
    assert others and all(c.tons == 0 and c.cargo for c in others)
    assert Convoy.__dataclass_fields__["tons"].default == 0     # opt-in, so nothing else moves


# --- the beat -------------------------------------------------------------------------------------

def _dump(sid="AX-Port", side=Side.AXIS, hex_=(0, 0), **pools) -> SupplyUnit:
    base = {"ammo": 0, "fuel": 0, "stores": 0, "water": 0}
    return SupplyUnit(sid, side, hex_, **{**base, **pools})


def _state(convoys, *, turn=1, supplies=()) -> GameState:
    dumps = tuple(supplies) or (_dump(),)
    return GameState(
        turn=turn, max_turns=8, phase=Phase.LOGISTICS, active_side=Side.SYSTEM, seed=1,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0), supplies=dumps,
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: getattr(dumps[0], c.lower()) for c in supply.COMMODITIES},
        convoys=tuple(convoys), stage=1)


def _plan(convoys, policy=None, turn=1):
    r = _Run(_state(convoys, turn=turn))
    _convoy_planning(r, {Side.AXIS: policy or Policy(), Side.ALLIED: Policy()})
    return r


def _axis(cid, turn, tons):
    return Convoy(cid, Side.AXIS, turn, "2", "AX-Port", {}, tons=tons)


def test_56_0_convoys_are_planned_ONE_GAME_TURN_IN_ADVANCE():
    """"Convoys are planned one Game-Turn in advance" -- 56.21's own worked example plans Game-Turn
    55's sailing at the beginning of Game-Turn 54. The OPENING Game-Turn plans twice, because a
    scenario starts in the middle of a war whose first convoy was planned the week before."""
    convoys = [_axis("c1", 1, 1000), _axis("c2", 2, 1000), _axis("c3", 3, 1000)]
    r = _Run(_state(convoys))
    _convoy_planning(r, {Side.AXIS: Policy(), Side.ALLIED: Policy()})
    planned = [e.payload["convoy_id"] for e in r.events if e.kind == EventKind.CONVOY_PLANNED]
    assert planned == ["c1", "c2"]                       # the curtain-raiser plus one turn ahead
    # ...and from then on, exactly one turn ahead. The double-plan is keyed on the SCENARIO's
    # opening Game-Turn (r.initial), so it happens once per run and never again.
    r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM", {"turn": 2})
    before = len(r.events)
    _convoy_planning(r, {Side.AXIS: Policy(), Side.ALLIED: Policy()})
    assert [e.payload["convoy_id"] for e in r.events[before:]
            if e.kind == EventKind.CONVOY_PLANNED] == ["c3"]


def test_the_plan_is_what_the_convoy_carries():
    """The fold puts the plan on GameState.convoy_plans and state.convoy_cargo reconciles it with
    the schedule -- ONE place, so the interdiction skim, the arrival manifest and the
    Quartermaster's projection can never disagree about what is in the hold."""
    r = _plan([_axis("c1", 1, 1000)])
    ev = [e for e in r.events if e.kind == EventKind.CONVOY_PLANNED][0]
    assert r.state.convoy_plans["c1"] == ev.payload["cargo"]
    convoy = next(c for c in r.state.convoys if c.id == "c1")
    assert r.state.convoy_cargo(convoy) == ev.payload["cargo"] != {}
    # a convoy nobody planned still reports its scheduled manifest
    ferry = Convoy("ferry", Side.ALLIED, 1, "SEA-TOBRUK", "AX-Port", {"FUEL": 5})
    assert r.state.convoy_cargo(ferry) == {"FUEL": 5}


def test_56_22_the_split_is_crossed_to_points_on_the_54_5_equivalent_weight_chart():
    """54.5 is the only conversion in the rule ("the tonnage equivalencies of supplies are listed on
    the Equivalent Weight Chart", 56.23): one Ammunition Point weighs 4 tons and one Fuel Point an
    eighth of a ton, so equal TONNAGE is wildly unequal POINTS. The log carries both."""
    r = _plan([_axis("c1", 1, 1000)])
    p = [e for e in r.events if e.kind == EventKind.CONVOY_PLANNED][0].payload
    for commodity, tons in p["tons_by"].items():
        assert p["cargo"][commodity] == supply.tons_to_points(tons, commodity)
    assert p["tons"] == p["allowed_tons"] == 1000


class _OverAsks(Policy):
    def convoy_plan(self, state, side, tons):
        return {supply.FUEL: tons, supply.AMMO: tons, supply.STORES: tons}


class _ShipsWater(Policy):
    def convoy_plan(self, state, side, tons):
        return {supply.WATER: tons * 0.5, supply.FUEL: tons * 0.5}


class _ShipsNonsense(Policy):
    def convoy_plan(self, state, side, tons):
        return {supply.FUEL: -500, "GOLD": 1000, supply.AMMO: 0}


def test_56_21_a_plan_over_the_allowance_is_clipped_at_the_boundary():
    """"Within the limits of allowable tonnage" (56.22) and "ports have maximum capacities; they may
    not receive supplies over that capacity" (56.27). The order is re-validated at the acceptance
    boundary, like every other order in this engine -- and clipped PROPORTIONALLY, so an
    oversubscribed plan keeps the mix the Axis asked for."""
    r = _plan([_axis("c1", 1, 900)], _OverAsks())
    p = [e for e in r.events if e.kind == EventKind.CONVOY_PLANNED][0].payload
    assert sum(p["tons_by"].values()) == pytest.approx(900)
    assert p["tons_by"] == {supply.AMMO: 300.0, supply.FUEL: 300.0, supply.STORES: 300.0}


def test_56_22_water_is_not_a_convoy_commodity():
    """56.22 names FUEL, AMMUNITION AND STORES and no fourth thing. Water comes out of the ground
    (52.7 wells) and off the railway; a plan that tries to ship it simply does not."""
    assert supply.CONVOY_COMMODITIES == (supply.AMMO, supply.FUEL, supply.STORES)
    r = _plan([_axis("c1", 1, 1000)], _ShipsWater())
    p = [e for e in r.events if e.kind == EventKind.CONVOY_PLANNED][0].payload
    assert set(p["cargo"]) == {supply.FUEL}
    assert supply.WATER not in p["tons_by"]


def test_a_nonsensical_plan_is_refused_rather_than_trusted():
    """Negative tonnages, unknown commodities and zeroes are all dropped at the boundary. This is
    the same order-rejection surface game.llm's adversarial MockClient exercises everywhere else."""
    r = _plan([_axis("c1", 1, 1000)], _ShipsNonsense())
    p = [e for e in r.events if e.kind == EventKind.CONVOY_PLANNED][0].payload
    assert p["cargo"] == {} and p["tons_by"] == {}


def test_a_scenario_that_plans_nothing_fires_no_beat():
    """Every convoy with tons == 0 carries a fixed manifest, so the Planning Phase has nothing to
    do and emits nothing -- which is what keeps both byte-locked benchmarks unchanged."""
    ferry = Convoy("ferry", Side.ALLIED, 1, "SEA-TOBRUK", "AX-Port", {"FUEL": 5})
    r = _plan([ferry])
    assert not r.events
    # The Desert Fox benchmark DOES sail an Axis lane on the [56.5] tonnage (it always did -- the
    # constant merely split it at construction), so its Axis lane is planned and its other two are
    # not. That is the whole of the change to that scenario, and the reason its signature moved.
    lanes = {c.lane: c.tons > 0 for c in rommels_arrival(seed=42).convoys}
    assert lanes == {"1": True, "SEA-TOBRUK": False, "CW-RAILHEAD": False}


def test_a_convoy_is_planned_once_and_only_once():
    """The beat skips anything already in convoy_plans, so the opening double-plan cannot re-plan a
    sailing on the following Game-Turn and overwrite the decision that was made for it."""
    r = _plan([_axis("c1", 1, 1000), _axis("c2", 2, 1000)])
    r2 = _Run(r.state)
    _convoy_planning(r2, {Side.AXIS: Policy(), Side.ALLIED: Policy()})
    assert not r2.events


# --- the doctrine ---------------------------------------------------------------------------------

def test_the_campaign_axis_ships_what_his_army_is_short_of():
    """[56.22] The decision reads the BOARD. Against an army swimming in fuel and out of
    ammunition, the doctrine ships ammunition -- which a constant, by construction, cannot do."""
    st = campaign(seed=4, max_turns=4)
    fuelled = st.__class__(**{**{f: getattr(st, f) for f in st.__dataclass_fields__},
                              "supplies": tuple(
                                  s.__class__(s.id, s.side, s.hex, ammo=0, fuel=200000,
                                              stores=s.stores, water=s.water,
                                              air_dump=s.air_dump, is_dummy=s.is_dummy,
                                              base=s.base, constructed=s.constructed)
                                  if s.side == Side.AXIS else s for s in st.supplies)})
    plan = convoy_plan_doctrine(fuelled, Side.AXIS, 10000)
    assert sum(plan.values()) == pytest.approx(10000)
    assert plan[supply.AMMO] > plan[supply.FUEL], plan
    # and the campaign policy is wired to it, on both campaign variants
    assert CampaignAxisPolicy().convoy_plan(fuelled, Side.AXIS, 10000) == plan


def test_the_doctrine_never_starves_a_commodity_outright():
    """⚠ The flagged tenth. 51.0 makes Stores a per-Game-Turn upkeep with no organic pool to ride a
    gap out on, so no commodity is ever allotted nothing -- our number, not the book's, and the only
    constant left in this decision."""
    st = campaign(seed=4, max_turns=4)
    plan = convoy_plan_doctrine(st, Side.AXIS, 10000)
    assert min(plan.values()) >= 1000 - 1e-6
    assert sum(plan.values()) == pytest.approx(10000)


def test_an_army_holding_nothing_splits_the_sailing_evenly():
    """⚠ The other flagged fallback: with no stocks ashore there are no proportions to reason from."""
    bare = _state([], supplies=(_dump(),))
    plan = convoy_plan_doctrine(bare, Side.AXIS, 900)
    assert plan == {c: 300.0 for c in supply.CONVOY_COMMODITIES}


# --- end to end ------------------------------------------------------------------------------------

def test_the_campaign_plans_every_axis_sailing_and_lands_what_it_planned():
    """The whole chain, on the real campaign: a plan per sailing, and the supply that arrives is the
    supply the Axis Player decided to ship."""
    res = run(campaign(seed=4, max_turns=4), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    planned = [e for e in res.events if e.kind == EventKind.CONVOY_PLANNED]
    assert len(planned) >= 4 and all(e.payload["cargo"] for e in planned)
    assert {e.side for e in planned} == {Side.AXIS}       # 56.22 is an Axis rule
    landed = [e for e in res.events if e.kind == EventKind.SUPPLY_ARRIVED
              and e.payload.get("convoy_id", "").startswith("axis-conv-")]
    assert landed, "the planned convoys must actually land something"
    shipped = {c for e in planned for c in e.payload["cargo"]}
    assert {c for e in landed for c in e.payload["cargo"]} <= shipped
