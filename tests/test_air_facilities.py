"""[36.0] AIR FACILITIES and [35.0] SQUADRON GROUND SUPPORT UNITS -- Phase 5.1.

The ground the air game stands on: a facility is an INSTALLATION with a Capacity Level (not a
unit), bombs take that level down (36.14/41.36), an airfield IS a supply dump for its SGSUs
(36.17), and an SGSU that cannot draw its own 35.14 upkeep may not repair its planes.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.air as air
import game.supply as supply
from game import oob
from game.apply import apply, fold
from game.engine import _air_facility_bomb, _Run, _sgsu_upkeep, run
from game.events import Control, Event, EventKind, Phase, Side
from game.invariants import InvariantViolation, check
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import campaign, rommels_arrival
from game.state import (AirFacility, AirMission, AirWing, GameState, StepRecord, SupplyUnit,
                        Unit, VP)
from game.terrain import Mobility, Terrain

import pytest


def _sgsu(uid: str, side: Side = Side.ALLIED, hex_=(0, 0), **kw) -> Unit:
    """An SGSU exactly as game.oob builds one: the `sgsu` role as its step label, no combat
    values (35.12), no stacking points, a Medium-truck CPA."""
    return Unit(uid, side, hex_, (StepRecord(air.SGSU_ROLE, 1),), Mobility.MOTORIZED,
                cpa=30, stacking_points=0, oca=0, dca=0, is_combat=False, **kw)


def _mini(*, facilities=(), supplies=(), units=(), stage=1, control=None) -> GameState:
    hexes = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR}
    return GameState(
        turn=1, max_turns=4, phase=Phase.LOGISTICS, active_side=Side.SYSTEM,
        seed=1, weather="normal", vp=VP(),
        terrain=TerrainMap(terrain=hexes, fortifications={}),
        control=control or {}, units=tuple(units), target_hex=(1, 0),
        supplies=tuple(supplies), consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES},
        air_facilities=tuple(facilities), stage=stage)


def _strip(fid="STRIP", side=Side.ALLIED, hex_=(0, 0), kind=air.STRIP, level=None) -> AirFacility:
    cap = air.max_capacity(kind)
    return AirFacility(fid, side, hex_, kind=kind, level=cap if level is None else level,
                       max_level=cap)


def _air_dump(sid="AF-Sup", side=Side.ALLIED, hex_=(0, 0), **pools) -> SupplyUnit:
    base = {"ammo": 0, "fuel": 0, "stores": 0, "water": 0}
    return SupplyUnit(sid, side, hex_, air_dump=True, **{**base, **pools})


# --- [36.1]-[36.4] the charted capacity levels ---------------------------------------------

def test_charted_capacity_levels():
    """36.12 an airfield six; 36.2 a landing strip one; 36.3 a flying boat basin three;
    36.4 an alighting area one. These are the rulebook's numbers, cell for cell."""
    assert air.max_capacity(air.AIRFIELD) == 6
    assert air.max_capacity(air.STRIP) == 1
    assert air.max_capacity(air.BASIN) == 3
    assert air.max_capacity(air.ALIGHTING) == 1
    assert air.SGSU_HEX_LIMIT == 6                     # 36.12: never more than six SGSUs in a hex


def test_35_14_upkeep_magnitudes():
    """35.14 verbatim: one Stores Point per GAME-TURN, one Fuel and one Water per OPERATIONS
    STAGE."""
    assert (air.SGSU_STORES_PER_TURN, air.SGSU_FUEL_PER_STAGE, air.SGSU_WATER_PER_STAGE) == (1, 1, 1)


# --- [36.14] / [24.76] damage, destruction and rebuild -------------------------------------

def test_36_14_bombing_takes_levels_and_zero_is_destroyed():
    """36.14: "if bombing has reduced the capacity of an airfield from six to three, that airfield
    may handle only three squadrons at a time... If an airfield is reduced to zero capacity, it is
    considered destroyed for all purposes"."""
    field = _strip("FIELD", kind=air.AIRFIELD)
    assert field.level == 6 and not air.destroyed(field)
    battered = replace(field, level=3)
    assert not air.destroyed(battered)
    assert air.destroyed(replace(field, level=0))


def test_24_76_only_an_airfield_is_rebuilt_in_place():
    """24.76: "Air landing strips, and flying boat facilities (both) must be BUILT FROM SCRATCH if
    destroyed. AIRFIELDS ARE REBUILT CAPACITY LEVEL BY CAPACITY LEVEL... Only one Level may be
    rebuilt at a time." And 36.12's six is the ceiling."""
    assert air.removed_when_destroyed(air.STRIP)
    assert air.removed_when_destroyed(air.BASIN)
    assert air.removed_when_destroyed(air.ALIGHTING)
    assert not air.removed_when_destroyed(air.AIRFIELD)

    field = _strip("FIELD", kind=air.AIRFIELD, level=0)
    assert air.rebuilt_level(field) == 1               # one level at a time, from the ground up
    assert air.rebuilt_level(replace(field, level=5)) == 6
    assert air.rebuilt_level(replace(field, level=6)) is None      # 36.12: six is the maximum
    assert air.rebuilt_level(_strip(level=0)) is None             # a dead strip is off the map


def test_level_change_and_destruction_fold():
    st = _mini(facilities=[_strip("FIELD", kind=air.AIRFIELD), _strip("S1")])
    lower = Event(0, 1, Phase.COMBAT, Side.AXIS, "AXIS/Air", EventKind.AIR_FACILITY_LEVEL_CHANGED,
                  {"facility_id": "FIELD", "level": 2})
    assert apply(st, lower).air_facility("FIELD").level == 2
    kill = Event(1, 1, Phase.COMBAT, Side.AXIS, "AXIS/Air", EventKind.AIR_FACILITY_DESTROYED,
                 {"facility_id": "S1", "kind": air.STRIP})
    assert apply(st, kill).air_facility("S1") is None
    assert len(apply(st, kill).air_facilities) == 1


def test_invariant_guards_the_level_range():
    """A Capacity Level outside [0, max_level] means a rule is misencoded -- fail loud."""
    check(_mini(facilities=[_strip("S1")]))                       # in range: silent
    with pytest.raises(InvariantViolation):
        check(_mini(facilities=[AirFacility("S1", Side.AXIS, (0, 0), air.STRIP, 2, 1)]))
    with pytest.raises(InvariantViolation):
        check(_mini(facilities=[AirFacility("S1", Side.AXIS, (0, 0), air.STRIP, -1, 1)]))


# --- [36.15] the holder is whoever holds the ground ----------------------------------------

def test_36_15_a_facility_belongs_to_whoever_controls_its_hex():
    """36.15: "Land combat units may CAPTURE or destroy (entirely) an airfield by occupying its
    hex. Airfields are, in essence, non-denominational; they may be used by anyone." 60.5 agrees:
    "air facilities may be used by anyone WHO CONTROLS THEM"."""
    f = _strip("S1", side=Side.ALLIED)
    assert air.holder(_mini(facilities=[f]), f) == Side.ALLIED            # neutral -> as seeded
    taken = _mini(facilities=[f], control={(0, 0): Control.AXIS})
    assert air.holder(taken, f) == Side.AXIS
    assert air.facilities_of(taken, Side.AXIS) == (f,)
    assert air.facilities_of(taken, Side.ALLIED) == ()


# --- [36.13] / [36.14] capacity gates how many SGSUs can WORK -------------------------------

def test_36_14_a_battered_field_holds_six_but_works_fewer():
    """36.14: "regardless of the capacity of an airfield, each airfield may still have six SGSU's
    with it, even though SOME MAY NOT BE ABLE TO FUNCTION because of a reduced capacity level"."""
    field = _strip("FIELD", kind=air.AIRFIELD, level=2)
    sgsus = [_sgsu(f"SG{i}") for i in range(4)]
    st = _mini(facilities=[field], units=sgsus)
    assert len(air.sgsus_at(st, (0, 0), Side.ALLIED)) == 4       # all four stand there...
    working = air.functioning_sgsus(st, field)
    assert [u.id for u in working] == ["SG0", "SG1"]             # ...only two can work
    assert air.functioning_sgsus(st, replace(field, level=0)) == ()


def test_35_14_refit_gate():
    """35.14: "SGSUs without the required supplies (for themselves) MAY NOT REPAIR THEIR PLANES."
    35.17: only an SGSU refits, and never "beyond the capacity of the air facility"."""
    field = _strip("FIELD", kind=air.AIRFIELD)
    fed, starved = _sgsu("SG-FED"), _sgsu("SG-DRY", stages_without_air_supply=1)
    st = _mini(facilities=[field], units=[fed, starved])
    assert air.may_refit(st, fed)
    assert not air.may_refit(st, starved)                        # 35.14: unsupplied, no repair
    # off a facility altogether, and on a destroyed one: no base, no refit (35.17 / 36.14)
    assert not air.may_refit(_mini(units=[fed]), fed)
    assert not air.may_refit(_mini(facilities=[replace(field, level=0)], units=[fed]), fed)
    # and never past the field's current capacity (36.13)
    crowded = _mini(facilities=[replace(field, level=1)], units=[fed, _sgsu("SG-AAA")])
    assert not air.may_refit(crowded, crowded.unit("SG-FED"))    # SG-AAA sorts first, takes the slot


# --- [36.17] an airfield is a supply dump -- for its SGSUs and NOBODY else -------------------

def _land_unit(uid="INF", side=Side.ALLIED, hex_=(0, 0)) -> Unit:
    return Unit(uid, side, hex_, (StepRecord("infantry", 3),), Mobility.FOOT,
                cpa=20, stacking_points=1, oca=3, dca=2)


def test_36_17_land_units_may_not_eat_from_an_air_dump():
    """36.17: "LAND UNITS MAY NOT USE AIRFIELD SUPPLY DUMPS unless it is an emergency. Any SGSU at
    an airfield may make use of the supplies there." That asymmetry is the rule -- without it the
    charted air allotment is simply extra fuel for the army."""
    dump = _air_dump(fuel=500, stores=500, water=500, ammo=500)
    inf, sg = _land_unit(), _sgsu("SG1")
    st = _mini(facilities=[_strip()], supplies=[dump], units=[inf, sg])

    assert supply.in_hex_available(st, inf, supply.STORES) == 0          # invisible to the army
    assert supply.in_hex_draw(st, inf, supply.STORES, 1) is None
    assert supply.reachable_supplies(st, inf, supply.STORES) == []       # and off the 32.16 trace

    assert supply.in_hex_available(st, sg, supply.STORES) == 500         # visible to the squadron
    assert supply.in_hex_draw(st, sg, supply.STORES, 1) == [("dump", "AF-Sup", 1)]


def test_36_17_an_ordinary_dump_is_still_the_armys():
    """The flag is the only difference: an air facility standing on an ORDINARY dump changes
    nothing about that dump."""
    ordinary = SupplyUnit("D1", Side.ALLIED, (0, 0), ammo=10, fuel=10, stores=10, water=10)
    inf = _land_unit()
    st = _mini(facilities=[_strip()], supplies=[ordinary], units=[inf])
    assert supply.in_hex_draw(st, inf, supply.STORES, 5) == [("dump", "D1", 5)]


# --- [35.14] the upkeep beat ----------------------------------------------------------------

def _upkeep(stage: int, dump: SupplyUnit, sgsus=None):
    sgsus = sgsus if sgsus is not None else [_sgsu("SG1")]
    st = _mini(facilities=[_strip()], supplies=[dump], units=sgsus, stage=stage)
    r = _Run(st)
    _sgsu_upkeep(r, Side.ALLIED)
    return r


def test_35_14_stage_one_charges_stores_fuel_and_water():
    """"Each SGSU must expend one Stores Point per Game-Turn. In addition, each SGSU requires one
    Fuel Point and one Water Point per Operations Stage." The Stores leg falls in the game-turn's
    first Operations Stage; all three are drawn IN HEX, off the 36.17 dump."""
    r = _upkeep(1, _air_dump(fuel=9, stores=9, water=9))
    drawn = [(e.payload["commodity"], e.payload["qty"]) for e in r.events
             if e.kind == EventKind.SUPPLY_CONSUMED]
    assert drawn == [(supply.STORES, 1), (supply.FUEL, 1), (supply.WATER, 1)]
    assert not [e for e in r.events if e.kind == EventKind.SGSU_UNSUPPLIED]
    assert r.state.supply("AF-Sup").stores == 8


def test_35_14_later_stages_charge_no_stores():
    """Stores are a per-GAME-TURN charge; Fuel and Water are per Operations Stage."""
    for stage in (2, 3):
        r = _upkeep(stage, _air_dump(fuel=9, stores=9, water=9))
        drawn = [e.payload["commodity"] for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]
        assert drawn == [supply.FUEL, supply.WATER]
        assert r.state.supply("AF-Sup").stores == 9


def test_35_14_a_dry_base_goes_unsupplied_and_may_not_refit():
    """An empty larder grounds the squadron: the shortfall counter rises and game.air.may_refit --
    the gate Phase 5.3's Refit Table reads -- goes False."""
    r = _upkeep(2, _air_dump(fuel=1, water=0))
    short = [e for e in r.events if e.kind == EventKind.SGSU_UNSUPPLIED]
    assert len(short) == 1 and short[0].payload["commodity"] == supply.WATER
    assert r.state.unit("SG1").stages_without_air_supply == 1
    assert not air.may_refit(r.state, r.state.unit("SG1"))
    # what WAS there is still expended -- 35.14 is a list of requirements, not a package
    assert r.state.supply("AF-Sup").fuel == 0


def test_35_14_resupply_resets_the_counter():
    st = _mini(facilities=[_strip()], supplies=[_air_dump(fuel=9, water=9)],
               units=[_sgsu("SG1", stages_without_air_supply=3)], stage=2)
    r = _Run(st)
    _sgsu_upkeep(r, Side.ALLIED)
    assert [e.kind for e in r.events if e.kind == EventKind.SGSU_SUPPLIED]
    assert r.state.unit("SG1").stages_without_air_supply == 0
    assert air.may_refit(r.state, r.state.unit("SG1"))


def test_sgsus_are_exempt_from_the_land_stores_and_water_beats():
    """35.14 gives the SGSU its own upkeep, so it must not ALSO pay the rule-51/52 land demand."""
    assert supply.is_sgsu(_sgsu("SG1"))
    assert not supply.is_sgsu(_land_unit())


# --- [41.36] bombing an air facility --------------------------------------------------------

def _bomb_state(level, strike=600, side=Side.AXIS):
    field = _strip("FIELD", side=Side.ALLIED, kind=air.AIRFIELD, level=level)
    st = _mini(facilities=[field])
    return replace(st, air=(AirWing("LW", side, "LAND", fighters=9, strike=strike, recon=0),),
                   air_superiority={"LAND": side.value})


def test_41_36_bombing_reduces_capacity_levels_on_the_41_5_crt():
    """41.36: "The result is the NUMBER OF CAPACITY LEVELS that facility is reduced." The [41.5]
    table prints ONE row for "Airfields / Air Landing Strips / Ports", so the airfield reads the
    same transcribed column set the harbour does."""
    r = _Run(_bomb_state(6))
    _air_facility_bomb(r, Side.AXIS, (0, 0))
    resolved = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert len(resolved) == 1 and resolved[0].payload["arena"] == "AIRFIELD"
    assert len(resolved[0].rng_draws) == 2                        # 41.22: two dice, sequential
    levels = resolved[0].payload["levels"]
    assert 0 <= levels <= 4                                       # the row's charted result range
    assert r.state.air_facility("FIELD").level == 6 - levels
    check(r.state)


def test_41_36_never_bombs_a_facility_your_own_side_holds():
    st = replace(_bomb_state(6), control={(0, 0): Control.AXIS})
    r = _Run(st)
    _air_facility_bomb(r, Side.AXIS, (0, 0))
    assert r.events == []


def test_41_36_a_destroyed_strip_leaves_the_map_an_airfield_does_not():
    """36.2: a strip at zero is "eliminated and removed from the game-map". 36.14: an airfield at
    zero is "considered destroyed for all purposes" but stays to be rebuilt (24.76)."""
    for kind, still_there in ((air.STRIP, False), (air.AIRFIELD, True)):
        field = _strip("F", side=Side.ALLIED, kind=kind, level=1)
        st = replace(_mini(facilities=[field]),
                     air=(AirWing("LW", Side.AXIS, "LAND", 9, 600, 0),),
                     air_superiority={"LAND": Side.AXIS.value})
        # roll until the CRT actually takes the level (the 471+ column is 1-4 levels on every code)
        r = _Run(st)
        _air_facility_bomb(r, Side.AXIS, (0, 0))
        assert r.state.air_facility("F") is not None or not still_there
        if still_there:
            assert r.state.air_facility("F").level == 0
        else:
            assert r.state.air_facility("F") is None


def test_air_missions_route_the_airfield_kind():
    """An AirMission of kind "airfield" flies through _air_support like strike/fort/port/recon."""
    field = _strip("F", side=Side.ALLIED, kind=air.AIRFIELD, level=6)
    st = replace(_mini(facilities=[field]),
                 air=(AirWing("LW", Side.AXIS, "LAND", 9, 600, 0),),
                 air_missions=(AirMission(Side.AXIS, "airfield", (0, 0), 1),),
                 air_superiority={"LAND": Side.AXIS.value})
    from game.engine import _air_support
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert [e for e in r.events if e.payload.get("arena") == "AIRFIELD"]


# --- the order of battle --------------------------------------------------------------------

def test_the_oob_ships_facilities_as_installations_not_units():
    """Phase 3.1 stopped discarding the air counters; Phase 5.1 stops mis-modelling them. An Air
    Landing Strip is no longer a CPA-0 Unit standing on the map."""
    facilities = oob.air_facilities("oob_italian.json", sections="ABCDE")
    assert facilities, "the campaign order of battle carries air facilities"
    assert {f.kind for f in facilities} <= {air.STRIP, air.ALIGHTING}
    assert all(f.level == f.max_level == air.max_capacity(f.kind) for f in facilities)
    units, _ = oob.build(oob_file="oob_italian.json", sections="ABCDE",
                         reinforcements_file=None)
    assert not [u for u in units if "Air-Strip" in u.id or "Alighting" in u.id]


def test_air_dumps_split_the_charted_allotment_and_carry_the_flag():
    """[60.34] "a total of 1200 Ammo, 850 Fuel, 100 Stores and 100 Water Points which may be freely
    distributed among his airfields"; [60.44] "Ammo: 200 Fuel: 250 Stores: 50"."""
    facilities = oob.air_facilities("oob_italian.json", sections="ABCDE")
    dumps = oob.air_dumps(facilities, oob.CAMPAIGN_AIR_POOLS)
    assert all(d.air_dump for d in dumps)
    axis = [d for d in dumps if d.side == Side.AXIS]
    cw = [d for d in dumps if d.side == Side.ALLIED]
    assert (sum(d.ammo for d in axis), sum(d.fuel for d in axis),
            sum(d.stores for d in axis), sum(d.water for d in axis)) == (1200, 850, 100, 100)
    assert (sum(d.ammo for d in cw), sum(d.fuel for d in cw),
            sum(d.stores for d in cw), sum(d.water for d in cw)) == (200, 250, 50, 0)


def test_sgsus_are_seeded_within_facility_capacity():
    """60.42: SGSUs "may be placed at any... air facility, WITHIN THE CAPACITY OF THAT FACILITY"."""
    facilities = oob.air_facilities("oob_italian.json", sections="ABCDE")
    sgsus = oob.seed_sgsus(facilities, oob.CAMPAIGN_SGSU_AVAILABLE)
    assert len(sgsus) == sum(f.level for f in facilities)
    by_hex: dict = {}
    for u in sgsus:
        assert air.is_sgsu(u) and not u.is_combat and u.stacking_points == 0   # 35.12
        by_hex[u.hex] = by_hex.get(u.hex, 0) + 1
    for f in facilities:
        assert by_hex.get(f.hex, 0) <= f.level
    # the charted pool is a CEILING, never a target
    assert len([u for u in sgsus if u.side == Side.AXIS]) <= oob.CAMPAIGN_SGSU_AVAILABLE[Side.AXIS]


# --- the scenarios --------------------------------------------------------------------------

def test_the_benchmark_scenario_seeds_facilities_and_their_dumps():
    st = rommels_arrival(1941)
    assert st.air_facilities
    air_dumps = [s for s in st.supplies if s.air_dump]
    assert len(air_dumps) == len(st.air_facilities)
    # [61.36] CW air supply: 250 Ammo, 180 Fuel, 50 Stores (no Water charted)
    cw = [d for d in air_dumps if d.side == Side.ALLIED]
    assert (sum(d.ammo for d in cw), sum(d.fuel for d in cw), sum(d.stores for d in cw),
            sum(d.water for d in cw)) == (250, 180, 50, 0)
    check(st)


def test_the_59_61_air_facility_truck_rows_are_no_longer_gated():
    """T0-18: with the Air Game abstract, 59.61 said to ignore the air-facility truck rows; the
    engine obeyed it for the supplies and disobeyed it for the trucks. Phase 5.1 plays the Air
    Game, so [61.43]'s "10 Medium Trucks at air facilities" is on the board."""
    from game.scenario import _AIR_GAME_PLAYED, _air_facility_trucks
    assert _AIR_GAME_PLAYED
    assert _air_facility_trucks({"medium": 10}) == ({"medium": 10},)
    st = rommels_arrival(1941)
    medium = sum(t.points for t in st.trucks if t.truck_class == "medium")
    assert medium == 290                                # [61.43] 280 + the 10 at air facilities


def test_a_benchmark_run_is_replayable_and_holds_its_invariants():
    st = rommels_arrival(42)
    pol = ScriptedPolicy(Side.AXIS)
    result = run(st, pol, pol)
    check(fold(result.initial, result.events))
    assert [e for e in result.events
            if e.kind in (EventKind.SGSU_SUPPLIED, EventKind.SGSU_UNSUPPLIED)], \
        "the 35.14 upkeep beat fires in the benchmark"
