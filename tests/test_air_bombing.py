"""[41.32] B-TC and [41.35] B-SD -- air reaches into the logistics game, Phase 5.5.

Two more rows of the [41.5] Air Bombardment and Secondary Barrage Targets Table were transcribed
for this block (PDF page 107, rendered at 300 dpi and read with eyes, row by row), and with them
the two missions that let a bomber touch the thing this war is actually about:

  41.35 B-SD "The result is THE PERCENTAGE OF EACH TYPE OF SUPPLY IN THAT DUMP that is destroyed.
        In addition, if there are any unattached trucks in the hex, FOR EVERY 10% OF SUPPLIES
        DESTROYED, ONE TRUCK POINT IS LOST, choice of defender, dividing losses as evenly as
        possible."
  41.32 B-TC "The results are given in THE NUMBER OF TRUCK UNITS DESTROYED... TRUCKS IN MAJOR
        CITIES MAY NOT BE BOMBED BY AIR UNTIL THE CITY IS REDUCED TO ZERO ('0')."

The chart's own Key (PDF page 108) settles the units: "Supply Dump: Eliminate that percentage of
all Supplies in that Dump. In addition, lose 1 Truck Point for each 10%, if possible, defender's
choice. Trucks: THAT NUMBER OF TRUCK POINTS AND THEIR CARGO DESTROYED."
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import game.air as air
import game.supply as supply
from game.engine import (_air_dump_bomb, _air_support, _air_truck_bomb, _crt_result,
                         _divide_truck_loss, _Run)
from game.events import EventKind, Phase, Side
from game.invariants import check
from game.logistics_data import (air_dump_bombing_crt_41_35, air_dump_truck_loss_per_pct_41_35,
                                 air_truck_bombing_crt_41_32)
from game.movement import TerrainMap
from game.state import (AirFacility, AirMission, AirWing, GameState, StepRecord, SupplyUnit,
                        TruckFormation, Unit, VP)
from game.terrain import Mobility, Terrain

CODES = [d1 * 10 + d2 for d1 in range(1, 7) for d2 in range(1, 7)]
BRACKETS = [[1, 20], [21, 40], [41, 80], [81, 120], [121, 160], [161, 200],
            [201, 260], [261, 320], [321, 390], [391, 470], [471, None]]


# --- the transcription itself ------------------------------------------------------------------

@pytest.mark.parametrize("columns,key", [(air_dump_bombing_crt_41_35(), "pct"),
                                         (air_truck_bombing_crt_41_32(), "points")])
def test_every_column_partitions_all_36_sequential_dice_codes(columns, key):
    """The self-check the transcription was accepted on, and the same guard the Ports and Axis
    Naval Convoy rows of this chart already stand under: 41.22 reads the two dice SEQUENTIALLY as a
    two-digit code, so each column must account for all 36 of them exactly once. A column slip in a
    hand-transcribed grid shows up here and nowhere else."""
    assert [c["bomb_points"] for c in columns] == BRACKETS
    for col in columns:
        seen: set[int] = set()
        for entry in col["results"]:
            lo, hi = entry["die"]
            span = {c for c in CODES if lo <= c <= hi}
            assert not (span & seen), (col["bomb_points"], entry, "overlapping die span")
            seen |= span
        assert seen == set(CODES), (col["bomb_points"], "column does not partition 36 codes")


def test_the_printed_result_ladders_are_the_charts():
    """The Result columns as printed: the Supply Dump row runs 0/10/20/30/40/50/75 percent and the
    Trucks row runs 0..7 Truck Points. The 75% appears in exactly ONE cell of the whole table --
    the 471+ column on a 65-66 -- and that singleness is worth pinning, because a mis-keyed 75 in a
    lower column would quietly make every dump in the desert twice as flammable."""
    dump_results = {e["pct"] for col in air_dump_bombing_crt_41_35() for e in col["results"]}
    assert dump_results == {0, 10, 20, 30, 40, 50, 75}
    truck_results = {e["points"] for col in air_truck_bombing_crt_41_32() for e in col["results"]}
    assert truck_results == set(range(8))
    seventy_five = [(col["bomb_points"], e["die"]) for col in air_dump_bombing_crt_41_35()
                    for e in col["results"] if e["pct"] == 75]
    assert seventy_five == [([471, None], [65, 66])]
    assert air_dump_truck_loss_per_pct_41_35() == 10        # 41.35: one Truck Point per 10%


def test_the_expected_result_rises_monotonically_with_bomb_points():
    """More bombs is never worse. Not a printed sentence, but a property EVERY row of this table
    has and the one a transposed column would break (it caught nothing here; it is the guard)."""
    for columns, key in ((air_dump_bombing_crt_41_35(), "pct"),
                         (air_truck_bombing_crt_41_32(), "points")):
        means = []
        for col in columns:
            total = sum(entry[key] * len([c for c in CODES
                                          if entry["die"][0] <= c <= entry["die"][1]])
                        for entry in col["results"])
            means.append(total / 36)
        assert means == sorted(means), means
        assert means[0] < means[-1]


def test_the_lookup_is_the_one_every_row_of_41_5_shares():
    """41.22: tens=first die, units=second. Below the table's floor (0 Bomb Points) nothing is
    scored -- the same answer the harbour and convoy rows already give."""
    cols = air_dump_bombing_crt_41_35()
    assert _crt_result(cols, 10, 1, 1, "pct") == 0          # 1-20 column, code 11 -> 0%
    assert _crt_result(cols, 10, 6, 6, "pct") == 10         # 1-20 column, code 66 -> 10%
    assert _crt_result(cols, 500, 6, 6, "pct") == 75        # 471+ column, code 66 -> 75%
    assert _crt_result(cols, 0, 6, 6, "pct") == 0           # below the floor: no column, no effect


# --- "as evenly as possible" -------------------------------------------------------------------

def _truck(tid, points, side=Side.AXIS, hex_=(1, 0), **cargo) -> TruckFormation:
    return TruckFormation(tid, side, hex_, "medium", points=points, **cargo)


def test_41_32_losses_are_divided_as_evenly_as_possible():
    """"The defending Player must DIVIDE THE LOSSES AS EVENLY AS POSSIBLE amongst type of trucks"
    (41.32); 41.35 says the same of its own Truck Point. One Point at a time, round-robin."""
    trucks = [_truck("T-A", 5), _truck("T-B", 5), _truck("T-C", 5)]
    assert sorted((t.id, n) for t, n in _divide_truck_loss(trucks, 3)) == [
        ("T-A", 1), ("T-B", 1), ("T-C", 1)]
    assert sorted((t.id, n) for t, n in _divide_truck_loss(trucks, 4)) == [
        ("T-A", 2), ("T-B", 1), ("T-C", 1)]


def test_a_loss_larger_than_the_hex_holds_takes_everything_and_no_more():
    """41.35's "if possible" and 41.32's arithmetic both stop at what is there. A formation may be
    bombed to zero Truck Points; it may never be bombed past it (invariants would raise)."""
    trucks = [_truck("T-A", 2), _truck("T-B", 1)]
    assert sorted((t.id, n) for t, n in _divide_truck_loss(trucks, 99)) == [("T-A", 2), ("T-B", 1)]


# --- fixtures ----------------------------------------------------------------------------------

def _state(*, missions=(), supplies=(), trucks=(), forts=None, strike=800, city=False,
           stage=2) -> GameState:
    """An Axis LAND wing over an Allied logistics target at (1,0). Stage 2: [59.32] gives the
    scenario's first Operations Stage its fuel free, so a fixture that wants a fuel bill must be
    past it. The Axis is based on its own field at (0,0) with a full dump, so nothing here is
    grounded for want of fuel and every refusal under test is the RULE's.

    THE WING IS DECLARED FOUR TIMES THE FORCE THAT FLIES, and that is rule 43 (game.basing): 43.12
    bases 75% of every German bomber pool in Italy/Sicily, so an ESTABLISHMENT of 800 Bomb Points
    (160 Ju. 87B on the 34.14 bridge) puts 40 aeroplanes -- 200 Bomb Points -- over the desert,
    which is the [41.5] column these rows are read on.

    `city` stamps the target hex a MAJOR CITY, because 41.31's and 41.32's bombing shelters are
    written about cities and not about fortification levels (engine._city_wall)."""
    field = AirFacility("FIELD", Side.AXIS, (0, 0), kind=air.AIRFIELD, level=6, max_level=6)
    larder = SupplyUnit("AF-Sup", Side.AXIS, (0, 0), ammo=0, fuel=99, stores=99, water=0,
                        air_dump=True)
    foe = Unit("GAR", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=2, oca=5, dca=8)
    all_supplies = (larder,) + tuple(supplies)
    initial = {c: sum(getattr(s, c.lower()) for s in all_supplies)
               + sum(getattr(t, c.lower()) for t in trucks) for c in supply.COMMODITIES}
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR,
                                    (1, 0): Terrain.MAJOR_CITY if city else Terrain.CLEAR},
                           fortifications=forts or {}),
        control={}, units=(foe,), target_hex=(1, 0), supplies=all_supplies,
        consumed={c: 0 for c in supply.COMMODITIES}, initial_supply=initial,
        air=(AirWing("LW", Side.AXIS, "LAND", fighters=0, strike=strike, recon=0),),
        air_missions=tuple(missions), air_facilities=(field,), trucks=tuple(trucks), stage=stage)


def _enemy_dump(sid="AL-Dump", hex_=(1, 0), **pools) -> SupplyUnit:
    base = {"ammo": 0, "fuel": 0, "stores": 0, "water": 0}
    return SupplyUnit(sid, Side.ALLIED, hex_, **{**base, **pools})


def _pin(r: _Run, *rolls) -> None:
    """Force the [41.5] dice. The bombardment stream is its own (game.dice), so pinning it here
    moves nothing else in the engine -- which is the whole reason that stream exists."""
    seq = iter(rolls)
    r.dice.stream("air_bombard").randint = lambda a, b: next(seq)


# --- [41.35] B-SD ------------------------------------------------------------------------------

def test_41_35_the_result_is_the_percentage_of_EVERY_supply_in_the_dump():
    """The chart Key, verbatim: "Eliminate that percentage of ALL Supplies in that Dump." Not the
    largest pool, not one commodity -- every one of them, at the same printed percentage."""
    dump = _enemy_dump(ammo=100, fuel=200, stores=50, water=30)
    st = _state(supplies=[dump])
    r = _Run(st)
    _pin(r, 6, 6)                                        # 200 Bomb Points, code 66 -> 30%
    _air_dump_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    bombed = [e for e in r.events if e.kind == EventKind.AIR_DUMP_BOMBED]
    assert len(bombed) == 1 and bombed[0].payload["pct"] == 30
    assert bombed[0].payload["destroyed"] == {"AMMO": 30, "FUEL": 60, "STORES": 15, "WATER": 9}
    left = r.state.supply("AL-Dump")
    assert (left.ammo, left.fuel, left.stores, left.water) == (70, 140, 35, 21)
    check(r.state)                                       # conservation: on_hand + consumed == initial


def test_41_35_costs_the_defender_one_truck_point_per_ten_percent():
    """"In addition, if there are any UNATTACHED trucks in the hex, for every 10% of supplies
    destroyed, ONE TRUCK POINT IS LOST, choice of defender, dividing losses as evenly as possible."
    A TruckFormation IS the unattached 2nd/3rd-line convoy (53.13), which is exactly the target
    this clause names."""
    st = _state(supplies=[_enemy_dump(fuel=100)],
                trucks=[_truck("AL-T1", 4, side=Side.ALLIED, fuel=40),
                        _truck("AL-T2", 4, side=Side.ALLIED, fuel=40)])
    r = _Run(st)
    _pin(r, 6, 6)                                        # 30% -> three Truck Points
    _air_dump_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    killed = [e for e in r.events if e.kind == EventKind.TRUCK_POINTS_DESTROYED]
    assert {e.payload["truck_id"]: e.payload["points"] for e in killed} == {"AL-T1": 2, "AL-T2": 1}
    assert all(e.payload["rule"] == "41.35" for e in killed)
    assert r.state.truck("AL-T1").points == 2 and r.state.truck("AL-T2").points == 3
    # the cargo goes with the lorries, pro rata (flagged: 41.35 prints only the Point)
    assert r.state.truck("AL-T1").fuel == 20 and r.state.truck("AL-T2").fuel == 30
    check(r.state)


def test_41_35_a_hex_with_no_unattached_trucks_loses_none():
    """"if there are any unattached trucks in the hex" -- and the Key's "if possible". No lorries,
    no lorry loss; the dump still burns."""
    st = _state(supplies=[_enemy_dump(fuel=100)])
    r = _Run(st)
    _pin(r, 6, 6)
    _air_dump_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    assert not [e for e in r.events if e.kind == EventKind.TRUCK_POINTS_DESTROYED]
    assert any(e.kind == EventKind.AIR_DUMP_BOMBED for e in r.events)


def test_41_35_a_no_effect_roll_burns_nothing_but_is_still_a_mission_flown():
    """A 0% result leaves the dump whole. The sortie was still flown and still billed -- 39.0's
    blind mission, the same line _air_strike and _air_port already draw."""
    st = _state(supplies=[_enemy_dump(fuel=100)], strike=40)   # 10 Bomb Points: the 1-20 column
    r = _Run(st)
    _pin(r, 1, 1)                                        # code 11 -> 0%
    billed: list[int] = []
    _air_dump_bomb(r, Side.AXIS, (1, 0), lambda pts: billed.append(pts) or pts)
    assert billed == [10]
    assert not [e for e in r.events if e.kind == EventKind.AIR_DUMP_BOMBED]
    resolved = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert resolved[0].payload["arena"] == "DUMP" and resolved[0].payload["pct"] == 0
    assert r.state.supply("AL-Dump").fuel == 100


def test_41_35_a_dump_is_hidden_so_the_sortie_is_flown_blind_and_never_hits_your_own():
    """A harbour and an airfield are PLACES whose owner is on the map, so _air_port and
    _air_facility_bomb refuse to bomb their own. A supply dump is hidden (3.6), and 39.0 says so
    outright -- missions are assigned "blindly", and the planes "only find out what target are
    present when they arrive". So this mission is flown and billed over a hex holding only the
    bomber's own supply, draws no [41.5] die, and destroys nothing of his."""
    own = SupplyUnit("AX-Dump", Side.AXIS, (1, 0), ammo=0, fuel=100, stores=0, water=0)
    st = _state(supplies=[own])
    r = _Run(st)
    billed: list[int] = []
    _air_dump_bomb(r, Side.AXIS, (1, 0), lambda pts: billed.append(pts) or pts)
    assert billed == [200]                               # flown blind over a hex holding nothing his
    assert not [e for e in r.events if e.kind == EventKind.AIR_DUMP_BOMBED]
    resolved = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED][0]
    assert resolved.payload["dumps"] == [] and resolved.rng_draws == ()
    assert r.state.supply("AX-Dump").fuel == 100


def test_41_35_one_roll_covers_every_dump_stacked_in_the_hex():
    """"Eliminate that percentage of all Supplies in that dump" -- and our supply layer routinely
    stacks several SupplyUnits on one hex. ONE roll, applied to each, so the number of DICE the
    engine draws can never depend on how many counters happen to be there (game.dice's whole
    reason for existing)."""
    st = _state(supplies=[_enemy_dump("AL-D1", fuel=100), _enemy_dump("AL-D2", ammo=50)])
    r = _Run(st)
    _pin(r, 6, 6)
    _air_dump_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    resolved = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert len(resolved) == 1 and resolved[0].rng_draws == (6, 6)
    assert resolved[0].payload["dumps"] == ["AL-D1", "AL-D2"]
    bombed = {e.payload["supply_id"]: e.payload["destroyed"]
              for e in r.events if e.kind == EventKind.AIR_DUMP_BOMBED}
    assert bombed == {"AL-D1": {"FUEL": 30}, "AL-D2": {"AMMO": 15}}
    check(r.state)


# --- [41.32] B-TC ------------------------------------------------------------------------------

def test_41_32_the_result_is_truck_points_and_their_cargo():
    """The chart Key: "Trucks: That number of TRUCK POINTS AND THEIR CARGO destroyed." Our
    TruckFormation.points is denominated in exactly that unit (1 Point = 10 trucks, 53.0)."""
    st = _state(trucks=[_truck("AL-T1", 6, side=Side.ALLIED, fuel=60, ammo=12)])
    r = _Run(st)
    _pin(r, 6, 6)                                        # 200 Bomb Points, code 66 -> 4 points
    _air_truck_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    killed = [e for e in r.events if e.kind == EventKind.TRUCK_POINTS_DESTROYED]
    assert len(killed) == 1 and killed[0].payload["points"] == 4
    assert killed[0].payload["rule"] == "41.32"
    assert killed[0].payload["cargo"] == {"AMMO": 8, "FUEL": 40}      # pro rata, rounded up
    tf = r.state.truck("AL-T1")
    assert (tf.points, tf.fuel, tf.ammo) == (2, 20, 4)
    check(r.state)


def test_41_32_trucks_in_a_major_city_are_sheltered_until_the_city_is_at_zero():
    """"TRUCKS IN MAJOR CITIES MAY NOT BE BOMBED BY AIR UNTIL THE CITY IS REDUCED TO ZERO ('0')."
    Note the asymmetry with 41.31, which shelters a GARRISON only while the wall is above ONE: the
    lorries are protected by any surviving level at all. That is the book's, not ours."""
    trucks = [_truck("AL-T1", 6, side=Side.ALLIED, fuel=60)]
    st = _state(trucks=trucks, forts={(1, 0): 1}, city=True)
    r = _Run(st)
    _pin(r, 6, 6)
    _air_truck_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    assert not [e for e in r.events if e.kind == EventKind.TRUCK_POINTS_DESTROYED]
    resolved = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert resolved[0].payload["walled"] is True and resolved[0].rng_draws == ()
    assert r.state.truck("AL-T1").points == 6
    # ...and the moment the last level goes, they are bombable
    flat = _state(trucks=trucks, forts={(1, 0): 0}, city=True)
    r2 = _Run(flat)
    _pin(r2, 6, 6)
    _air_truck_bomb(r2, Side.AXIS, (1, 0), lambda pts: pts)
    assert r2.state.truck("AL-T1").points == 2


def test_41_32_shelters_a_CITY_and_not_a_fortification_level():
    """RESTATED IN THE 5.5 REPAIR PASS, and the reason is in the rule's own words: 41.32 shelters
    "trucks in MAJOR CITIES", not trucks behind works. The test used to assert that any hex with a
    fortification level sheltered its lorries -- true today only because every fortification in the
    tree stands on a Major City -- which would have made a Level-1 field work in open desert (24.4,
    unbuilt) an un-bombable lorry park by a rule that grants no such thing."""
    trucks = [_truck("AL-T1", 6, side=Side.ALLIED, fuel=60)]
    st = _state(trucks=trucks, forts={(1, 0): 1})        # fortified, but NOT a Major City
    r = _Run(st)
    _pin(r, 6, 6)
    _air_truck_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    resolved = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert resolved[0].payload["walled"] is False
    assert r.state.truck("AL-T1").points == 2


def test_41_32_never_bombs_your_own_lorries():
    """The target is the ENEMY's transport. Your own convoy parked in the target hex is not a
    target, and the mission finds the hex empty (39.0's blind sortie -- billed, no die)."""
    st = _state(trucks=[_truck("AX-T1", 6, side=Side.AXIS, fuel=60)])
    r = _Run(st)
    _air_truck_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    assert not [e for e in r.events if e.kind == EventKind.TRUCK_POINTS_DESTROYED]
    assert r.state.truck("AX-T1").points == 6


def test_41_32_a_result_larger_than_the_hex_holds_is_capped_and_reported_honestly():
    """The CRT can call for more Truck Points than are standing there. The log records what was
    actually destroyed AND the raw chart result beside it, so the cap is visible rather than
    silently swallowed."""
    st = _state(trucks=[_truck("AL-T1", 1, side=Side.ALLIED, fuel=10)])
    r = _Run(st)
    _pin(r, 6, 6)                                        # the chart says 4
    _air_truck_bomb(r, Side.AXIS, (1, 0), lambda pts: pts)
    resolved = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED][0]
    assert resolved.payload["result"] == 4 and resolved.payload["points"] == 1
    assert r.state.truck("AL-T1").points == 0 and r.state.truck("AL-T1").fuel == 0
    check(r.state)


# --- the missions are real tasking ---------------------------------------------------------------

@pytest.mark.parametrize("kind", ["dump", "trucks"])
def test_the_new_mission_kinds_route_through_the_air_support_segment(kind):
    """Both are ordinary LAND air missions: they are tasked on the schedule, flown in the phasing
    side's Combat Segment, fuelled out of the 36.17 air-facility dump (38.24) and un-refit
    afterwards (38.31), exactly like every other bombing mission in the engine."""
    st = _state(missions=[AirMission(Side.AXIS, kind, (1, 0), 1)],
                supplies=[_enemy_dump(fuel=100)],
                trucks=[_truck("AL-T1", 6, side=Side.ALLIED, fuel=60)])
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    kinds = [e.kind for e in r.events]
    assert EventKind.AIR_STRIKE_RESOLVED in kinds
    assert EventKind.SUPPLY_CONSUMED in kinds                    # 38.24: the sortie was fuelled
    assert EventKind.AIR_SQUADRON_UNFIT in kinds                 # 38.31: the planes have flown
    check(r.state)


def test_a_grounded_air_force_bombs_no_dump_and_no_lorry():
    """38.21 "planes must have fuel to fly": an unfuellable mission is not flown, draws no [41.5]
    die and destroys nothing. The fuel callback returning 0 is the engine's own signal."""
    st = _state(supplies=[_enemy_dump(fuel=100)],
                trucks=[_truck("AL-T1", 6, side=Side.ALLIED, fuel=60)])
    for resolver in (_air_dump_bomb, _air_truck_bomb):
        r = _Run(st)
        resolver(r, Side.AXIS, (1, 0), lambda pts: 0)
        assert not [e for e in r.events if e.kind in (EventKind.AIR_DUMP_BOMBED,
                                                      EventKind.TRUCK_POINTS_DESTROYED)]
        assert not [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
