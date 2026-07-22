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


def _fuelled(points: int) -> int:
    """The 38.24 draw a test of 41.36's Capacity-Level arithmetic passes in: every committed Air
    Point flies. Written out at each call site rather than defaulted inside the resolver -- a
    resolver that can be called WITHOUT a fuel argument is a resolver a future caller can fly for
    free, silently, and this engine fails loud instead."""
    return points


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

# 43.12 bases three quarters of a German bomber pool in Italy/Sicily (game.basing), so an
# ESTABLISHMENT of 2400 Bomb Points is what puts the [41.5] table's top column -- 600 Bomb Points,
# 120 Ju. 87B -- over the target. Every fixture below is declared in establishment, not in sorties.
def _bomb_state(level, strike=2400, side=Side.AXIS):
    field = _strip("FIELD", side=Side.ALLIED, kind=air.AIRFIELD, level=level)
    st = _mini(facilities=[field])
    return replace(st, air=(AirWing("LW", side, "LAND", fighters=9, strike=strike, recon=0),),
                   air_superiority={"LAND": side.value})


def test_41_36_bombing_reduces_capacity_levels_on_the_41_5_crt():
    """41.36: "The result is the NUMBER OF CAPACITY LEVELS that facility is reduced." The [41.5]
    table prints ONE row for "Airfields / Air Landing Strips / Ports", so the airfield reads the
    same transcribed column set the harbour does."""
    r = _Run(_bomb_state(6))
    _air_facility_bomb(r, Side.AXIS, (0, 0), _fuelled)
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
    _air_facility_bomb(r, Side.AXIS, (0, 0), _fuelled)
    assert r.events == []


def test_41_36_a_destroyed_strip_leaves_the_map_an_airfield_does_not():
    """36.2: a strip at zero is "eliminated and removed from the game-map". 36.14: an airfield at
    zero is "considered destroyed for all purposes" but stays to be rebuilt (24.76)."""
    for kind, still_there in ((air.STRIP, False), (air.AIRFIELD, True)):
        field = _strip("F", side=Side.ALLIED, kind=kind, level=1)
        st = replace(_mini(facilities=[field]),
                     air=(AirWing("LW", Side.AXIS, "LAND", 9, 2400, 0),),
                     air_superiority={"LAND": Side.AXIS.value})
        # roll until the CRT actually takes the level (the 471+ column is 1-4 levels on every code)
        r = _Run(st)
        _air_facility_bomb(r, Side.AXIS, (0, 0), _fuelled)
        assert r.state.air_facility("F") is not None or not still_there
        if still_there:
            assert r.state.air_facility("F").level == 0
        else:
            assert r.state.air_facility("F") is None


def test_41_5_key_an_airlanding_strip_receiving_a_result_of_1_or_greater_is_eliminated():
    """THE KEY TO THE [41.5] TABLE, PDF p.108, verbatim: "Results: An Airlanding Strip receiving a
    result of 1 or greater is eliminated. Airfield: That number of Squadron GroundSupport Units may
    no longer use the Airfield's Readying Capacity. Ports: Reduce the Port by that number of
    Efficiency Levels." ONE ROW, THREE MEANINGS -- and until this pass the engine read the Ports
    meaning, min(result, level), off every one of them.

    The strip's rule is ELIMINATION, not whittling. On the map the two readings agree by arithmetic
    accident (36.2 caps a strip at ONE level, so min() takes all of it), which is why the
    discriminating case below is a strip standing at more levels than 36.2 prints: it is not a state
    oob or malta can seed, and it is the only way to assert WHICH RULE IS ENCODED rather than which
    number happens to come out."""
    strip = _strip("S", kind=air.STRIP)                       # the map's strip: one level
    assert air.levels_lost(strip, 0) == 0                     # No Effect leaves it standing
    assert air.levels_lost(strip, 1) == 1 and air.levels_lost(strip, 4) == 1
    assert air.levels_lost(replace(strip, level=3), 1) == 3   # eliminated, not reduced to two
    # the airfield keeps 41.36's capacity-level arithmetic, and never loses more than it has
    field = _strip("F", kind=air.AIRFIELD, level=6)
    assert air.levels_lost(field, 0) == 0 and air.levels_lost(field, 2) == 2
    assert air.levels_lost(replace(field, level=1), 4) == 1
    # 36.3/36.4 make a basin and an alighting area airfields with a smaller ceiling
    assert air.levels_lost(_strip("B", kind=air.BASIN), 1) == 1
    assert air.levels_lost(_strip("B", kind=air.BASIN), 4) == 3


def test_41_5_key_the_airfield_result_is_the_sgsus_denied_the_readying_capacity():
    """[41.5 Key] "Airfield: That number of Squadron GroundSupport Units may no longer use the
    Airfield's Readying Capacity", which 41.36 states as capacity levels and 37.24 shows to be the
    same fact: "if there are five SGSU's on an airfield, but the capacity level of that airfield has
    been reduced to two, only two of those SGSU's may refit and ready their planes. The other three
    squadrons are forced to remain inactive because of the reduced field capacity."

    So the Key's sentence is assertable on the engine as it stands, and this pins it: bomb a full
    field carrying its full six mechanics and EXACTLY the charted result number of them lose the
    readying capacity."""
    field = _strip("FIELD", side=Side.ALLIED, kind=air.AIRFIELD, level=6)
    sgsus = [_sgsu(f"SG{i}") for i in range(6)]               # 36.12: six may stand on the hex
    st = replace(_mini(facilities=[field], supplies=[_air_dump(fuel=99, water=99, stores=99)],
                       units=sgsus),
                 air=(AirWing("LW", Side.AXIS, "LAND", fighters=9, strike=2400, recon=0),),
                 air_superiority={"LAND": Side.AXIS.value})
    before = len(air.functioning_sgsus(st, st.air_facility("FIELD")))
    assert before == 6                                        # 36.13: all six work an intact field
    r = _Run(st)
    _air_facility_bomb(r, Side.AXIS, (0, 0), _fuelled)
    levels = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED][0].payload["levels"]
    after = air.functioning_sgsus(r.state, r.state.air_facility("FIELD"))
    assert len(after) == before - levels                       # the Key's own sentence
    denied = {u.id for u in st.units} - {u.id for u in after}
    assert all(not air.may_refit(r.state, r.state.unit(uid)) for uid in denied)
    assert all(air.may_refit(r.state, u) for u in after)       # 35.14 fed, 36.13 inside the level


def test_air_missions_route_the_airfield_kind():
    """An AirMission of kind "airfield" flies through _air_support like strike/fort/port/recon."""
    field = _strip("F", side=Side.ALLIED, kind=air.AIRFIELD, level=6)
    st = replace(_mini(facilities=[field]),
                 air=(AirWing("LW", Side.AXIS, "LAND", 9, 2400, 0),),
                 air_missions=(AirMission(Side.AXIS, "airfield", (0, 0), 1),),
                 air_superiority={"LAND": Side.AXIS.value})
    from game.engine import _air_support
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert [e for e in r.events if e.payload.get("arena") == "AIRFIELD"]


# --- the order of battle --------------------------------------------------------------------

def test_the_oob_ships_facilities_as_installations_not_units():
    """Phase 3.1 stopped discarding the air counters; Phase 5.1 stops mis-modelling them. An Air
    Landing Strip is no longer a CPA-0 Unit standing on the map.

    RESTATED for the [60.5] transcription: the campaign's facilities now come off the BOOK'S CHART
    (oob.charted_air_facilities), not the VASSAL extraction, so the kinds assertion is no longer
    "strips and one alighting area" -- that WAS the defect. The second half is unchanged and is
    where the point of this test lives: build() never materialises an air facility as a unit. (An
    earlier draft of this docstring said the extraction READER was exercised in that second half.
    It is not -- the second half calls oob.build, and oob.air_facilities is now reached only from
    the Desert Fox scenarios and their own tests.)"""
    facilities = oob.charted_air_facilities(sections="ABCDE")
    assert facilities, "the campaign carries the [60.5] air facilities"
    assert {f.kind for f in facilities} == {air.AIRFIELD, air.STRIP, air.BASIN, air.ALIGHTING}
    assert all(f.level == f.max_level == air.max_capacity(f.kind) for f in facilities)
    units, _ = oob.build(oob_file="oob_italian.json", sections="ABCDE",
                         reinforcements_file=None)
    assert not [u for u in units if "Air-Strip" in u.id or "Alighting" in u.id]


def test_air_dumps_split_the_charted_allotment_and_carry_the_flag():
    """[60.34] "a total of 1200 Ammo, 850 Fuel, 100 Stores and 100 Water Points which may be freely
    distributed among his airfields"; [60.44] "Ammo: 200 Fuel: 250 Stores: 50"."""
    facilities = oob.charted_air_facilities(sections="ABCDE")
    dumps = oob.air_dumps(facilities, oob.CAMPAIGN_AIR_POOLS)
    assert all(d.air_dump for d in dumps)
    axis = [d for d in dumps if d.side == Side.AXIS]
    cw = [d for d in dumps if d.side == Side.ALLIED]
    assert (sum(d.ammo for d in axis), sum(d.fuel for d in axis),
            sum(d.stores for d in axis), sum(d.water for d in axis)) == (1200, 850, 100, 100)
    assert (sum(d.ammo for d in cw), sum(d.fuel for d in cw),
            sum(d.stores for d in cw), sum(d.water for d in cw)) == (200, 250, 50, 0)


def test_sgsus_are_seeded_within_facility_capacity():
    """60.42: SGSUs "may be placed at any... air facility, WITHIN THE CAPACITY OF THAT FACILITY".

    RESTATED at the [60.5] transcription, and the restatement is the measurement of what the map
    was costing: over the extraction's 11 one-level strips this seeded 11 SGSUs of the charted 53
    ([60.32] 39 Italian + [60.42] 14 Commonwealth) because the MAP was the binder. Over the book's
    map the POOL is the binder, which is what 60.42 says it should be -- so the assertion flips
    from "as many as the map can hold" to "the whole charted pool, and no more"."""
    facilities = oob.charted_air_facilities(sections="ABCDE")
    sgsus = oob.seed_sgsus(facilities, oob.CAMPAIGN_SGSU_AVAILABLE)
    assert len(sgsus) <= sum(f.level for f in facilities)
    by_hex: dict = {}
    for u in sgsus:
        assert air.is_sgsu(u) and not u.is_combat and u.stacking_points == 0   # 35.12
        by_hex[u.hex] = by_hex.get(u.hex, 0) + 1
    for f in facilities:
        assert by_hex.get(f.hex, 0) <= min(f.level, air.SGSU_HEX_LIMIT)
    for side, pool in oob.CAMPAIGN_SGSU_AVAILABLE.items():
        assert len([u for u in sgsus if u.side == side]) == pool   # the pool now binds, not the map


def test_the_axis_squadrons_are_based_where_60_34_lets_its_supply_go():
    """THE DUAL OF THE PLACEMENT ABOVE, and the two must be exercised together or one starves the
    other. [60.34] lets the Axis air allotment stand on AIRFIELDS ONLY, so an Italian squadron based
    on a landing strip has no charted supply source at all -- and under a bare id-order fill, nine
    of the 39 went to strips and the basin and were dry from Game-Turn 1 by OUR placement. 60.42
    puts the choice in the Player's hands ("may be placed at ANY... air facility, within the
    capacity of that facility"), and every Italian squadron fits on the Axis's own airfields, so it
    is filled that way. The Commonwealth's pool is unrestricted ([60.44]) and his order is
    untouched -- he keeps his forward strips at the wire."""
    st = campaign(seed=4)
    at = {f.hex: f for f in st.air_facilities}
    axis = [u for u in st.units if air.is_sgsu(u) and u.side == Side.AXIS]
    assert len(axis) == 39 and all(at[u.hex].kind == air.AIRFIELD for u in axis)
    cw = [u for u in st.units if air.is_sgsu(u) and u.side == Side.ALLIED]
    assert len(cw) == 14 and any(at[u.hex].kind == air.STRIP for u in cw)   # still at the wire
    # ...and the ordering comes off the transcribed restriction: with none it is the plain id order,
    # which here would put the one squadron on the STRIP that sorts first.
    strips = [_strip("F1", Side.AXIS, (0, 0)), _strip("F2", Side.AXIS, (1, 0), kind=air.AIRFIELD)]
    assert [u.hex for u in oob.seed_sgsus(strips, {Side.AXIS: 1})] == [(0, 0)]       # id order
    assert [u.hex for u in oob.seed_sgsus(strips, {Side.AXIS: 1},
                                          kinds={Side.AXIS: (air.AIRFIELD,)})] == [(1, 0)]


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


# --- THE REPAIR PASS: the four places 36.17 was written down and one place it was not ---------
#
# 36.17 is not one rule with one implementation; it is a property an air dump has to carry past
# every scan in the engine that enumerates supply. Each test below is a scan that got it wrong.

def test_36_17_the_supply_distribution_top_up_skips_an_air_dump():
    """[36.17] / 48 V.C.6. The Supply Distribution Segment tops every unit's 49.14 tank and 50.0
    ammo load up from a dump ON ITS HEX -- and it used to enumerate active_supplies itself, filtered
    on the hex alone, so a tank battalion parked on an airfield refilled off the squadron's larder.
    (Measured on the pre-repair tree, campaign seed 4 over twelve Game-Turns: 314 Fuel and 108 Ammo
    Points moved out of Axis air dumps into land combat units.) It now asks the same enumeration the
    in-hex draw asks, which is the only way the exclusion cannot drift apart from it."""
    from game.engine import _supply_distribution
    dump = _air_dump(fuel=500, ammo=500)
    inf = replace(_land_unit(), fuel=0, ammo=0)
    sg = _sgsu("SG1", fuel=0)
    st = _mini(facilities=[_strip()], supplies=[dump], units=[inf, sg])
    r = _Run(st)
    _supply_distribution(r, Side.ALLIED)
    refills = [e.payload for e in r.events if e.kind == EventKind.UNIT_REFILLED]
    assert not [p for p in refills if p["unit_id"] == "INF"], \
        f"a land unit refilled from an air dump (36.17): {refills}"
    # ...and the squadron standing on the same pile still may (36.17's second sentence)
    assert [p for p in refills if p["unit_id"] == "SG1"]


def test_36_17_an_air_facilitys_dump_may_not_be_marched_off_its_field():
    """[36.17] "An AIRFIELD IS a supply dump for supplies to be used by the SGSU's on that
    airfield" -- the pile is a property of the installation, and nothing in rule 36 or in the
    [60.34]/[60.44] charts gives it wheels. The 32.3 leapfrog used to carry it away: measured on the
    pre-repair tree, all eleven campaign air dumps left their facility within six Game-Turns, four of
    them ending stacked on one desert hex, and the entire air force went permanently unsupplied
    beside its own empty airfields. The rejection lives at the ENGINE boundary so it binds every
    policy, scripted or live."""
    from game.engine import _supply_movement
    from game.policy import Policy, SupplyMoveOrder

    dump = _air_dump("AF-Sup", side=Side.ALLIED, hex_=(0, 0), fuel=500, ammo=500)
    st = _mini(facilities=[_strip()], supplies=[dump], units=[_land_unit(hex_=(1, 0))])

    class _Mover(Policy):
        def supply_orders(self, state, side):
            return [SupplyMoveOrder("AF-Sup", (1, 0))]

    r = _Run(st)
    _supply_movement(r, _Mover(), Side.ALLIED)
    assert not [e for e in r.events if e.kind == EventKind.SUPPLY_MOVED]
    rejects = [e.payload for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert rejects and "36.17" in rejects[0]["reason"]
    assert r.state.supply("AF-Sup").hex == (0, 0)


def test_the_scripted_leapfrog_never_proposes_an_air_dump():
    """The other half of the same law: a policy should not propose what the engine must reject.
    Both campaign policies inherit this leapfrog, and it is where the air dumps escaped."""
    dump = _air_dump("AF-Sup", side=Side.ALLIED, hex_=(0, 0), fuel=500, ammo=500)
    field = SupplyUnit("D1", Side.ALLIED, (0, 0), ammo=10, fuel=10, stores=10, water=10)
    st = _mini(facilities=[_strip()], supplies=[dump, field], units=[_land_unit(hex_=(1, 0))])
    orders = ScriptedPolicy(Side.ALLIED).supply_orders(st, Side.ALLIED)
    assert "AF-Sup" not in {o.supply_id for o in orders}


def test_64_71_does_not_count_an_air_dump_as_a_supply_dump():
    """[64.71]/[64.72] ask whether an ARMY has a line of supply -- "within 90 Truck Movement Points
    of a supply dump which can in turn be supplied from Tobruk or Tripoli in any way". 36.17 forbids
    the army a single Point from an airfield's pile, so no air dump is the Supply Dump this rule is
    asking for: the same argument that excludes a well. Rule 64.71 is the Axis auto-win and 64.72 the
    Commonwealth instant-win, so a widened predicate is a widened victory condition."""
    from game.campaign_victory import CampaignVictory
    assert not CampaignVictory._is_supply_dump(_air_dump("AF-Sup", fuel=500))
    assert CampaignVictory._is_supply_dump(
        SupplyUnit("D1", Side.ALLIED, (0, 0), ammo=10, fuel=10, stores=10, water=10))


def test_35_14_water_rides_the_same_abstract_trace_as_the_armys():
    """[35.14] water, and the ONE flagged inconsistency the repair pass removed. Every land unit's
    rule-52 water is drawn on the abstract half-CPA trace (supply.plan_draw), because the S8
    investigation measured the naive in-hex water draw unfaithful until 52.45's water trucks exist.
    The SGSU was being held to the stricter standard -- and [60.44] charts the Commonwealth air
    facilities NO WATER AT ALL, so an in-hex draw denied every RAF squadron its water on Game-Turn 1
    of the campaign and every turn after, out of a chart's silence. Water asks the trace; Stores and
    Fuel stay in hex on the 36.17 pile."""
    # a bone-dry facility, with water one hex away on an ordinary dump inside the SGSU's trace
    near = SupplyUnit("WELL", Side.ALLIED, (1, 0), ammo=0, fuel=0, stores=0, water=50)
    r = _upkeep(2, _air_dump(fuel=9))
    assert [e.payload["commodity"] for e in r.events if e.kind == EventKind.SGSU_UNSUPPLIED] \
        == [supply.WATER]                                  # nothing in reach -> still a shortfall

    st = _mini(facilities=[_strip()], supplies=[_air_dump(fuel=9), near],
               units=[_sgsu("SG1")], stage=2)
    r2 = _Run(st)
    _sgsu_upkeep(r2, Side.ALLIED)
    assert not [e for e in r2.events if e.kind == EventKind.SGSU_UNSUPPLIED]
    assert r2.state.supply("WELL").water == 49
    assert r2.state.supply("AF-Sup").fuel == 8             # 36.17: fuel still off its own pile


def test_59_52_the_air_allotment_is_never_stacked_on_a_field_dump():
    """[59.52] "Air facilities automatically possess a supply dump. If a Player places supplies
    available at a supply dump in the same location as those available at an air facility, THE
    TOTALS ARE COMBINED AND IT BECOMES ONE DUMP." Two Supply Units on one hex is what the engine's
    one-dump-per-hex law forbids, so the free placement does not create the case. The campaign walks
    right into it: the Commonwealth's charted Sollum Field Supply Depot stands on the Sollum landing
    strip's hex. The share is not lost -- it goes to that side's other facilities.

    WHAT THEN FEEDS THE SQUADRON ON THE SKIPPED HEX IS A FLAGGED JUDGEMENT CALL, not a rule this
    test asserts: supply.colocated_dumps lets it eat the army's depot under its feet because nothing
    forbids that, where the sentence quoted above says the two piles COMBINE -- and the book does not
    say which pile's restriction the combined dump would then carry. See oob.air_dumps."""
    strips = [_strip("F1", Side.ALLIED, (0, 0)), _strip("F2", Side.ALLIED, (1, 0))]
    field = SupplyUnit("D1", Side.ALLIED, (0, 0), ammo=0, fuel=0, stores=0, water=0)
    dumps = oob.air_dumps(strips, {Side.ALLIED: {"AMMO": 100, "FUEL": 0, "STORES": 0, "WATER": 0}},
                          placed=[field])
    assert [d.hex for d in dumps] == [(1, 0)]
    assert sum(d.ammo for d in dumps) == 100               # the whole allotment still lands
    # and with no field dump in the way, the ordinary even split
    both = oob.air_dumps(strips, {Side.ALLIED: {"AMMO": 100, "FUEL": 0, "STORES": 0, "WATER": 0}})
    assert sorted(d.ammo for d in both) == [50, 50]


def test_60_34_gives_the_axis_pool_to_airfields_and_60_44_the_cws_to_any_facility():
    """THE TWO ROWS DO NOT SAY THE SAME THING. [60.34] (scan PDF p.78): the Axis "receives a total
    of 1200 Ammo, 850 Fuel, 100 Stores and 100 Water Points which may be freely distributed among
    his AIRFIELDS". [60.44] (p.79): "Air Supply (Distribute amongst AIR FACILITIES as desired)".
    The same section's abstract-game appendix draws the distinction a second time in the same words
    ([60.9] B/C: "any Axis airfields(s)" against "any Commonwealth air facilities") -- cited as a
    witness to the wording only, since 60.9 is the abstract game and is not in force.

    It was an empty distinction while the campaign's air map was the VASSAL extraction, which
    carried NO AIRFIELD AT ALL; [60.5] put fifteen on the board and made the word load-bearing.
    Before this, ~63% of the Axis's charted air supply stood on landing strips, a basin and an
    alighting area -- installations the printed row does not name."""
    mixed = [_strip("F1", Side.AXIS, (0, 0), kind=air.AIRFIELD), _strip("F2", Side.AXIS, (1, 0))]
    pool = {Side.AXIS: {"AMMO": 100, "FUEL": 0, "STORES": 0, "WATER": 0}}
    restricted = oob.air_dumps(mixed, pool, kinds={Side.AXIS: (air.AIRFIELD,)})
    assert [(d.hex, d.ammo) for d in restricted] == [((0, 0), 100)]      # the strip gets nothing
    assert sorted(d.ammo for d in oob.air_dumps(mixed, pool)) == [50, 50]   # unrestricted: even

    # ...and on the campaign map itself, off the transcribed restriction (never a code literal).
    assert oob.CAMPAIGN_AIR_POOL_KINDS == {Side.AXIS: (air.AIRFIELD,), Side.ALLIED: None}
    st = campaign(seed=4)
    at = {f.hex: f for f in st.air_facilities}
    axis = [s for s in st.supplies if s.air_dump and s.side == Side.AXIS]
    assert axis and all(at[s.hex].kind == air.AIRFIELD for s in axis)
    # the Commonwealth's is NOT restricted, and in the campaign it does land on landing strips
    cw = [s for s in st.supplies if s.air_dump and s.side == Side.ALLIED]
    assert cw and any(at[s.hex].kind != air.AIRFIELD for s in cw)


def test_the_air_allotment_is_placed_where_the_squadrons_actually_are():
    """OUR FREE CHOICE, EXERCISED COHERENTLY -- and the bug is what happens when it is not.

    [60.34]/[60.44] leave the placement to the Player and [60.42] leaves the squadron bases to him
    too, so the engine authors both (oob.air_dumps, oob.seed_sgsus). They were authored
    INDEPENDENTLY, which was harmless over the extraction's 11 facilities and 11 squadrons -- every
    facility held one -- and collided on [60.5]'s 49-facility map: measured at campaign(seed=4)
    set-up, the Axis had 24 air dumps of which 12 held a squadron and the Commonwealth 18 of which
    9 did, stranding 430 of 850 Axis Fuel Points and 126 of 250 Commonwealth ones.

    PERMANENTLY stranded, which is why this is a defect and not untidiness: 35.14's Fuel and Stores
    legs are an IN-HEX draw (engine._sgsu_upkeep) and no code path ever moves an SGSU, so those
    Points could never be reached by anybody for 111 Game-Turns. The campaign seeds the bases first
    and hands them to air_dumps. A Fuel Point at an empty field is our doing, not the book's."""
    st = campaign(seed=4)
    manned = {(u.side, u.hex) for u in st.units if air.is_sgsu(u)}
    for d in [s for s in st.supplies if s.air_dump]:
        assert (d.side, d.hex) in manned, f"stranded air supply at {d.hex}"
    # ...and with no squadron information the filter is inert, which is what the Desert Fox
    # scenarios rely on: their SGSUs are the extraction's own counters, not seeded by us.
    strips = [_strip("F1", Side.ALLIED, (0, 0)), _strip("F2", Side.ALLIED, (1, 0))]
    pool = {Side.ALLIED: {"AMMO": 100, "FUEL": 0, "STORES": 0, "WATER": 0}}
    assert sorted(d.ammo for d in oob.air_dumps(strips, pool, squadrons=())) == [50, 50]
    one = oob.air_dumps(strips, pool, squadrons=[_sgsu("SG1", Side.ALLIED, (1, 0))])
    assert [(d.hex, d.ammo) for d in one] == [((1, 0), 100)]


def test_the_campaign_air_allotment_is_conserved_exactly():
    """[60.34] 1200 Ammo / 850 Fuel / 100 Stores / 100 Water + [60.44] 200 / 250 / 50 -- and the
    59.52 placement above must not lose a Point of either."""
    st = campaign(seed=4)
    axis = [s for s in st.supplies if s.air_dump and s.side == Side.AXIS]
    cw = [s for s in st.supplies if s.air_dump and s.side == Side.ALLIED]
    assert (sum(s.ammo for s in axis), sum(s.fuel for s in axis),
            sum(s.stores for s in axis), sum(s.water for s in axis)) == (1200, 850, 100, 100)
    assert (sum(s.ammo for s in cw), sum(s.fuel for s in cw),
            sum(s.stores for s in cw), sum(s.water for s in cw)) == (200, 250, 50, 0)


# --- [60.5] THE CAMPAIGN AIR MAP -------------------------------------------------------------
# The chart (docs/rules/60 lines 288-362; scan PDF p.79, read at 600 dpi with eyes) against the
# data file it was transcribed into and the campaign it seeds.

def _hex(label: str):
    from game import coords
    return coords.to_axial(coords.parse(label))


def test_60_5_charts_the_airfields_the_campaign_map_had_none_of():
    """[60.5] The whole point of the transcription. The VASSAL extraction gave the campaign 10 Air
    Landing Strips and 1 Alighting Area -- ONE-level facilities, every one of them eliminated by the
    first bombing result it took ([41.5] Key) -- and no airfield anywhere. The chart prints 20
    Airfield rows plus its closing "the four Tripoli/Tunisia boxes (off-map)", 31 Air Landing
    Strips, 3 Flying Boat Basins and 1 Alighting Area.

    ONE RECORD PER PRINTED ROW is the invariant, and it is the assertion that changed: Alexandria's
    single row ("Both hexes, (E3613, 3714)") was transcribed as TWO six-level airfields, which is
    six squadron slots, a second bombable installation and an extra share of the [60.44] pool that
    the chart does not print -- an inference from the shape of our per-hex facility model, inside a
    transcription. It is one record again (data/air_facilities_60_5.json carries the flag and the
    unseeded second hex), so 24 airfield records, 15 of them on the playable map."""
    import collections
    from game import logistics_data
    rows = logistics_data.air_facilities_60_5()
    assert collections.Counter(r["kind"] for r in rows) == {
        "airfield": 24, "strip": 31, "basin": 3, "alighting": 1}
    on_map = oob.charted_air_facilities(sections="ABCDE")
    assert collections.Counter(f.kind for f in on_map) == {
        "airfield": 15, "strip": 31, "basin": 2, "alighting": 1}


def test_60_5_the_off_map_rows_are_charted_and_not_placed():
    """[60.5] prints six facilities "Off-Map" -- Abu Seier, Deversoir, Fayid, Ismailia, Kabrit and
    the Port Said basin -- plus "the four Tripoli/Tunisia boxes (off-map)". Where the chart gives a
    hex in parentheses, E(3433) / E(1833) / E4033, that is the off-map box's entry hex and not the
    facility's location: seeding one would put an off-map installation on the playable map. They
    are transcribed (the chart is not silently edited) and not placed (the engine has no off-map
    air box), which is exactly how data/victory_cities.json already treats the Tripoli box."""
    from game import logistics_data
    off = [r for r in logistics_data.air_facilities_60_5() if not r.get("on_map", True)]
    assert len(off) == 10 and all(r["hex"] is None for r in off)
    assert {r["name"] for r in off if r["country"] == "Egypt"} == {
        "Abu Seier", "Deversoir", "Fayid", "Ismailia", "Kabrit", "Port Said"}
    placed = {f.hex for f in oob.charted_air_facilities(sections="ABCDE")}
    for entry in ("E3433", "E1833", "E4033"):
        assert _hex(entry) not in placed


def test_60_5_every_printed_hex_is_a_real_hex_and_one_facility_stands_on_it():
    """A wrong hex silently puts an airfield in the sea, so every label is parsed, resolved on the
    real map grid and required to exist in the terrain data. The FOUR SEA READINGS ARE NAMED HERE
    RATHER THAN SWEPT UP: Bomba B5331 is a FLYING BOAT BASIN and belongs on water, while El Agheila
    A1816, Gazala B4933 and Matten Baggush D3520 are the known coastal colour-sampling defect of
    the terrain extraction (game.cna_map:42, game.campaign_victory:100) -- data/wells.json
    independently places all three VILLAGES on those same hexes, so the chart's hexes stand and the
    terrain file is the suspect. If this list ever shrinks, the map extraction improved; if it
    grows, a transcription is wrong."""
    import json
    from pathlib import Path
    from game import coords
    terrain = {s: json.loads((Path(__file__).resolve().parent.parent /
                              f"data/terrain_{s}.json").read_text()) for s in "ABCDE"}
    from game import logistics_data
    labels = [r["hex"] for r in logistics_data.air_facilities_60_5() if r.get("on_map", True)]
    assert len(labels) == len(set(labels)) == 49            # one facility per hex, no duplicates
    sea = set()
    for label in labels:
        assert label[0] in "ABCDE"
        coords.to_axial(coords.parse(label))                # parses on the real grid
        assert label in terrain[label[0]], f"{label} is not a hex of map {label[0]}"
        if terrain[label[0]][label] == "sea":
            sea.add(label)
    assert sea == {"B5331", "A1816", "B4933", "D3520"}


def test_60_5_ownership_is_the_charts_own_geography_rule():
    """[60.5] "All facilities in Egypt belong to the Commonwealth; all those in Libya belong to the
    Italians. at the start of the game."

    THE VICTORY CONDITIONS IN THE NEXT COLUMN OF THE SAME PAGE ARE THE STRONGEST CORROBORATION and
    they are what this now leads on: [60.81] (scan PDF p.79 col.3) makes the Commonwealth "take and
    hold Bardia, Fort Maddalena, Sidi Omar, Sollum and Siwa" for his Decisive Victory and makes the
    Italian "retain possession of Sollum (C4021) and Fort Maddalena and Giarabub" for his Tactical.
    Bardia C4321, Ft. Maddalena C3019, Sidi Omar C3618 and Giarabub C1014 are therefore AXIS at the
    start, which is what this asserts. (SOLLUM is the one row where [60.81] and [60.5] point
    different ways, and the file records why rather than dropping it: [60.5] says who a facility
    BELONGS to, [60.81] describes who is standing on the hex on 15 September 1940 -- the Italians
    had just taken it -- and 36.15 reconciles them, since air.holder reads the current controller.)

    The chart also prints its own frontier anchor -- Sollum C4021 and Ft. Capuzzo C4020, the twin
    posts either side of the wire, listed as two separate Air Landing Strips -- and the neighbouring
    supply charts agree from both directions: [60.34] gives the AXIS its start-line dumps at Tobruk
    C4807, Bardia C4321 and Derna B5925, and [60.44] gives the COMMONWEALTH his at Mersa Matruh
    D3714 and Sidi Barrani C4131. (The extraction had Sollum Axis.)"""
    at = {f.hex: f for f in oob.charted_air_facilities(sections="ABCDE")}
    for label, side in (("C4021", Side.ALLIED), ("C4131", Side.ALLIED), ("D3714", Side.ALLIED),
                        ("C4020", Side.AXIS), ("C4321", Side.AXIS), ("C4807", Side.AXIS),
                        ("B5925", Side.AXIS)):
        assert at[_hex(label)].side == side, label


def test_60_5_the_kinds_carry_rule_36s_capacities_into_the_campaign():
    """[36.12]/[36.2]/[36.3]/[36.4] -- and the kind is load-bearing since the [41.5] Key: a strip is
    eliminated by any result at all, an airfield loses that many Capacity Levels and is rebuilt one
    at a time (24.76). Alexandria is the row that proves the chart was read and not skimmed: the
    airfield at E3613 and the FLYING BOAT BASIN at E3614 beside it are two facilities of different
    kinds at the same city, which no reading of the extraction would have produced.

    RESTATED: this used to assert a second six-level airfield at E3714 as well, off the "Both hexes,
    (E3613, 3714)" in the row's Hex column. That was our per-hex model inferring a second
    installation from one printed row -- capacity the chart does not print -- so the row is seeded
    once and E3714 is now deliberately EMPTY of any air facility. The reading is flagged for the
    owner in data/air_facilities_60_5.json; if it comes back "both hexes", E3714 returns here."""
    at = {f.hex: f for f in campaign(seed=4).air_facilities}
    assert _hex("E3714") not in at, "one printed row, one installation"
    for label, kind in (("E3613", air.AIRFIELD), ("E3614", air.BASIN),
                        ("B5925", air.ALIGHTING), ("C4021", air.STRIP), ("C4507", air.AIRFIELD)):
        f = at[_hex(label)]
        assert (f.kind, f.level, f.max_level) == (kind, air.max_capacity(kind),
                                                  air.max_capacity(kind)), label


def test_the_campaign_air_map_is_the_book_s_and_the_squadrons_have_somewhere_to_stand():
    """The end of the [60.5] job, measured on the campaign it seeds: airfields exist (there were
    none), and both charted SGSU pools -- [60.32] 39 Italian, [60.42] 14 Commonwealth -- are on the
    board, where the extraction's 11 one-level strips could base 11 of the 53 between them."""
    st = campaign(seed=4)
    mainland = [f for f in st.air_facilities if not f.id.startswith("Malta/")]
    assert len([f for f in mainland if f.kind == air.AIRFIELD]) == 15
    sgsus = [u for u in st.units if air.is_sgsu(u)]
    assert len([u for u in sgsus if u.side == Side.AXIS]) == 39
    assert len([u for u in sgsus if u.side == Side.ALLIED]) == 14
    # every SGSU stands on a facility its own side holds, within that facility's Capacity Level
    for u in sgsus:
        f = air.facility_at(st, u.hex)
        assert f is not None and f.side == u.side
        assert len(air.sgsus_at(st, u.hex, u.side)) <= min(f.level, air.SGSU_HEX_LIMIT)


def test_36_17_the_observation_does_not_offer_an_air_dump_as_the_armys_supply():
    """[36.17] in the read-only projection the staff plans against (game.observation). The
    victory_cities "supply_on_hex" field exists to tell a staff which cities it can garrison for
    free -- "a friendly dump holding both fuel and ammunition stands on this hex, so the garrison is
    supplied by definition" -- and that is FALSE of an airfield's pile, which no land unit may draw
    from. The dump is still listed under your_supplies (it IS the Player's supply; hiding it would be
    its own falsehood) and now carries the 36.17 flag that says what it is."""
    from game import observation
    dump = _air_dump("AF-Sup", side=Side.ALLIED, hex_=(0, 0), fuel=500, ammo=500)
    st = _mini(facilities=[_strip()], supplies=[dump], units=[_land_unit()])
    obs = observation.observe(st, Side.ALLIED)
    listed = {s["id"]: s for s in obs["your_supplies"]}
    assert listed["AF-Sup"]["air_dump"] is True
