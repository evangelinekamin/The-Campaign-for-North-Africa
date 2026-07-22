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

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import game.scenario as scenario
import game.supply as supply
from game import calendar, wells
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


def test_an_oasis_is_geography_and_never_votes_in_the_convoy_split():
    """[56.22] + [52.3] THE SENTINEL THAT COST THE AXIS HIS BREAD FOR A HUNDRED AND ELEVEN GAME-TURNS.

    A 52.3 oasis is seeded as an endless Stores dump (wells.UNLIMITED_WELL = 125,000,000 Points);
    Siwa, Jalo and Giarabub between them put 375 MILLION tons of 'food' on the Axis books. Counted as
    larder, that swamps every real quantity in the doctrine's comparison, so the quartermaster read
    an army that would never want for stores again and shipped the flagged 10% floor -- every
    sailing, all war, bit-identically across seeds that differed in every battle (measured:
    45.02 / 44.97 / 10.01 on both, scratchpad/port/faucet-audit.md stage 1b).

    A bottomless source is not a larder. The oasis feeds the unit standing ON it (52.3, drawn in
    hex); the army five hundred kilometres away cannot eat Siwa's dates. So the doctrine counts only
    stock somebody could run out of, and the plan is the one it would make if the oasis were not on
    the map at all."""
    field = _dump("AX-Field", fuel=80000)                       # a lake of fuel and NO food
    oasis = SupplyUnit("AX-Well-Siwa", Side.AXIS, (1, 0), ammo=0, fuel=0,
                       stores=wells.UNLIMITED_WELL, water=wells.UNLIMITED_WELL, base=True)
    plan = convoy_plan_doctrine(_state([], supplies=(field, oasis)), Side.AXIS, 10000)
    assert plan[supply.STORES] > 10000 * 0.10 + 1e-6, "the oasis voted, and the floor won"
    assert plan[supply.STORES] > plan[supply.FUEL]              # ship what the army is out of
    # and it is exactly the plan the same army makes with no oasis in the theatre at all
    assert plan == convoy_plan_doctrine(_state([], supplies=(field,)), Side.AXIS, 10000)


# --- [56.21]: the allowance is a GAME-TURN's, not a month's ---------------------------------------

def test_every_game_turn_gets_its_own_56_5_allowance_and_benghazi_takes_its_share():
    """[56.21] "The figures given on the Tonnage Determination Table are the tonnage of supplies
    that the Axis may ship IN THAT GAME-TURN (for which he is planning)" -- with a worked example
    that ships 21,000 tons on Game-Turn 55 alone (scan PDF p.75 = book p.24), and 56.22/56.24 both
    saying "for a given Game-Turn" / "for that Game-Turn". The engine used to roll the [56.5] die
    ONCE A CALENDAR MONTH and quarter it -- 507,000 tons of a licensed 1,550,000-2,544,000 (24.9%,
    faucet-audit.md stage 1a); the per-Game-Turn licence is what the book prints, and this test
    reads it at its true layer, _campaign_axis_tonnage (the ROLL).

    [56.25] "The Axis Player then, at the same time, ALLOCATES his available tonnage to the lanes --
    AND PORTS -- he wants them to use." The licence is for all six [56.11] lanes together; no player
    sails a harbour more than it can land, so the ONE modelled lane (Italy -> Benghazi) carries
    min(licence, Benghazi's Game-Turn throughput) and the balance sails the lanes into Tripoli and
    Bizerta this engine does not model. The repair: the whole licence used to be sailed into
    Benghazi and the overflow annihilated at the quay (56.27 misread as its sink), which made
    convoy interdiction unable to reduce landed supply. It is now PLANNED AROUND, not annihilated."""
    st = campaign(seed=1941)
    lane = {c.arrival_turn: c for c in st.convoys if c.id.startswith("axis-conv-")}
    beng = next(p for p in st.ports if p.id == "PORT-Benghazi")
    gt_capacity = scenario._OPSTAGES_PER_GAME_TURN * supply.port_tonnage_budget(beng)   # 3 x 2,500

    def level(gt: int) -> str:
        year, month = calendar.gt_to_month(gt)
        return scenario._CONVOY_LEVEL_56_4.get(str(year), {}).get(scenario._MON[month - 1], "-")

    # replay the scenario's own convoy rng to recover the per-Game-Turn licence roll exactly
    rng = random.Random(1941)
    licence = {}
    for gt in range(1, st.max_turns + 1):
        t = scenario._campaign_axis_tonnage(gt, rng)
        if t is not None:
            licence[gt] = t

    scheduled = {gt for gt in range(1, st.max_turns + 1) if level(gt) != "-"}
    assert set(lane) == scheduled, "a convoy sails every Game-Turn the 56.4 chart schedules one"
    assert set(licence) == scheduled
    for gt, c in lane.items():
        cap = scenario._CONVOY_CAP_56_5[level(gt)]
        fixed, var = cap["fixed_tons"], cap["variable_tons_per_die"]
        lo = math.ceil((fixed + var * 1) / 1000) * 1000       # the die envelope of THIS Game-Turn's
        hi = math.ceil((fixed + var * 6) / 1000) * 1000       # 56.5 row -- a whole roll, not a quarter
        assert lo <= licence[gt] <= hi, (gt, level(gt), licence[gt])   # rank-3: the full licence
        assert c.tons == min(licence[gt], gt_capacity)        # 56.25: Benghazi's share of it
        assert c.tons <= gt_capacity                          # never more than the quay can land
    assert sum(licence.values()) >= 1_550_000                 # the licence's own die minimum
    # the clip BINDS -- the licence overruns one harbour's Game-Turn throughput in the vast majority
    # of Game-Turns, which is why the [56.4]/[56.5] variation above it cannot reach this lane's
    # landed tonnage (flagged in engine._unload_convoys), and why the surplus goes to other ports
    assert any(c.tons == gt_capacity for c in lane.values())
    assert sum(c.tons for c in lane.values()) < sum(licence.values())


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
