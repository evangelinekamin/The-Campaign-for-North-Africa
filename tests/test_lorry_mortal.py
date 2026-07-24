"""The mortal lorry (rules 21.11 / 22.23 / 12.46 / 29.34; Phase 6.1).

For two years 380-410 Truck Points crossed the desert and not one was ever lost. Three
rulebook channels take Truck Points now, and these tests pin each:

  * 21.11 BREAKDOWN -- Truck Points are named FIRST among the breakdown-subject vehicles.
    A convoy accrues Breakdown Points as it relocates (21.21) and, having ceased moving with
    more than three, rolls on the 21.38 table at BAR 2 Left (21.14); the percentage breaks
    down into TruckFormation.broken_down (immobile, 21.44), off the haulage pool.
  * 22.23 REPAIR -- the field truck column comes alive with it: one die per hex, 1 -> two
    Points, 2 -> one Point, and FREE (no supply expenditure).
  * 12.46 BARRAGE -- every land Barrage that fires rolls a second, independent d66 on the
    [12.6] Truck row for any enemy Trucks in the hex, destroying Truck Points and their cargo.
    Previously declined by citing rule 32.56, an ABSTRACT-game rule; in the full Logistics
    Game barrage kills real Truck Points.
  * 29.34 EVAPORATION -- fuel and water carried by a convoy evaporate as in a dump (already
    wired; confirmed here so parking freight on a lorry is not evaporation-proof).
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.combat_tables as ct
import game.supply as supply
from game.apply import apply
from game.engine import _barrage_step, _breakdown, _repair, _truck_breakdown, _Run
from game.events import Event, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap
from game.state import GameState, StepRecord, SupplyUnit, TruckFormation, Unit, VP
from game.terrain import Mobility, Terrain

_DATA = json.loads((Path(__file__).resolve().parent.parent / "data"
                    / "breakdown_rates.json").read_text())


# --- helpers -----------------------------------------------------------------------------------

def _state(*, units=(), supplies=(), trucks=(), terrain=None, weather="clear",
           turn=1, stage=2) -> GameState:
    terrain = terrain or {(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR}
    surfaces = tuple(supplies) + tuple(trucks) + tuple(units)
    initial = {c: sum(getattr(s, c.lower(), 0) for s in surfaces) for c in supply.COMMODITIES}
    return GameState(
        turn=turn, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather=weather, vp=VP(), terrain=TerrainMap(terrain=terrain, fortifications={}),
        control={}, units=tuple(units), target_hex=(0, 0), supplies=tuple(supplies),
        consumed={c: 0 for c in supply.COMMODITIES}, initial_supply=initial,
        trucks=tuple(trucks), stage=stage)


def _pin(r: _Run, stream: str, *rolls) -> None:
    """Force a per-subsystem die stream. The stream is its own (game.dice), so pinning it
    moves nothing else -- the whole reason those streams exist."""
    seq = iter(rolls)
    r.dice.stream(stream).randint = lambda a, b: next(seq)


def _truck(tid, points, side=Side.ALLIED, hex_=(1, 0), tclass="medium", **kw) -> TruckFormation:
    return TruckFormation(tid, side, hex_, tclass, points=points, **kw)


# --- the chart: TRUCK_BAR + the [12.6] Truck row + the 22.8 truck column ------------------------

def test_truck_bar_is_the_54_2_two_left():
    # 21.14 / 54.2: ALL Truck Points are BAR "2 Left" == -2, the same for Light/Medium/Heavy.
    assert ct.TRUCK_BAR == -2
    chart = _DATA["bar_by_model"]["trucks_54_2"]
    assert chart["light"] == chart["medium"] == chart["heavy"] == ct.TRUCK_BAR


def test_the_12_6_truck_row_partitions_all_36_codes_and_never_pins():
    # Every column of the CRT must partition all 36 sequential d66 codes across No-effect / 1 / 2.
    codes = {10 * a + b for a in range(1, 7) for b in range(1, 7)}
    block = ct._BARRAGE["truck"]
    for col in range(9):
        hit = ct.expand(block["1"][col]) | ct.expand(block["2"][col])
        assert not (ct.expand(block["1"][col]) & ct.expand(block["2"][col]))   # disjoint 1 vs 2
        assert hit <= codes
    # 12.44: a Truck is never Pinned -- only ever No-effect or a Truck-Point loss.
    for actual in range(1, 40):
        for roll in codes:
            pinned, _ = ct.barrage_result("truck", actual, roll)
            assert pinned is False


def test_the_22_8_field_truck_column():
    # 22.23: a roll of 1 repairs two Truck Points, a 2 repairs one, 3-6 repair none. FREE.
    assert [ct.field_repair("truck", d) for d in range(1, 7)] == [2, 1, 0, 0, 0, 0]
    by_die = _DATA["broken_down_vehicle_repair_22_8"]["by_die"]      # field_truck is column 0
    assert (by_die["1"][0], by_die["2"][0], by_die["3"][0]) == ("2", "1", "0")


# --- the folds: broken_down pool, BP accrual, evaporation, resets -------------------------------

def test_effective_points_is_haulage_less_the_broken():
    t = _truck("T", 5)
    assert t.effective_points == 5
    assert replace(t, broken_down=2).effective_points == 3


def test_truck_broke_down_moves_points_off_the_haulage_pool():
    t = _truck("T", 5, hex_=(0, 0))
    s = _state(trucks=[t])
    e = Event(0, 1, Phase.MOVEMENT, Side.ALLIED, "ALLIED/Front",
              EventKind.TRUCK_BROKE_DOWN, {"truck_id": "T", "amount": 2})
    s2 = apply(s, e)
    assert s2.truck("T").broken_down == 2 and s2.truck("T").points == 5      # still 5 lorries
    assert s2.truck("T").effective_points == 3                               # 3 can haul
    check(s2)


def test_truck_repaired_returns_points_to_the_pool():
    t = _truck("T", 5, hex_=(0, 0), broken_down=3)
    s = _state(trucks=[t])
    e = Event(0, 1, Phase.REPAIR, Side.ALLIED, "ALLIED/Repair",
              EventKind.TRUCK_REPAIRED, {"truck_id": "T", "amount": 2})
    s2 = apply(s, e)
    assert s2.truck("T").broken_down == 1 and s2.truck("T").effective_points == 4
    check(s2)


def test_truck_moved_accrues_breakdown_points():
    t = _truck("T", 5, hex_=(0, 0), fuel=300)
    s = _state(trucks=[t], terrain={(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR})
    e = Event(0, 1, Phase.LOGISTICS, Side.ALLIED, "ALLIED/Logistics", EventKind.TRUCK_MOVED,
              {"truck_id": "T", "from": [0, 0], "to": [1, 0], "cp_spent": 5, "fuel": 5, "bp": 8.0})
    s2 = apply(s, e)
    assert s2.truck("T").bp_accumulated == 8.0 and s2.truck("T").hex == (1, 0)


def test_29_34_a_convoys_fuel_and_water_evaporate_like_a_dump():
    # 29.34: the +5% hot slice "includes water and fuel ... in trucks" -- freight on a lorry is
    # NOT evaporation-proof. TRUCK_EVAPORATED folds like a dump's SUPPLY_EVAPORATED (a sink).
    t = _truck("T", 5, hex_=(0, 0), fuel=200, water=100)
    s = _state(trucks=[t])
    for commodity, qty in (("FUEL", 12), ("WATER", 6)):
        e = Event(0, 1, Phase.LOGISTICS, Side.SYSTEM, "SYSTEM", EventKind.TRUCK_EVAPORATED,
                  {"truck_id": "T", "commodity": commodity, "qty": qty})
        s = apply(s, e)
    assert s.truck("T").fuel == 188 and s.truck("T").water == 94
    assert s.consumed["FUEL"] == 12 and s.consumed["WATER"] == 6
    check(s)


def test_a_barraged_convoy_loses_broken_lorries_first_no_negative_effective():
    # A convoy with broken lorries that is then destroyed down past the broken count keeps
    # broken_down <= points, so effective_points never goes negative (21.44 cap).
    t = _truck("T", 5, hex_=(0, 0), broken_down=3)
    s = _state(trucks=[t])
    e = Event(0, 1, Phase.COMBAT, Side.ALLIED, "ALLIED/Front", EventKind.TRUCK_POINTS_DESTROYED,
              {"truck_id": "T", "points": 4, "left": 1, "cargo": {}, "rule": "12.46"})
    s2 = apply(s, e)
    assert s2.truck("T").points == 1 and s2.truck("T").broken_down == 1       # capped from 3
    assert s2.truck("T").effective_points == 0
    check(s2)


def test_opstage_reset_clears_bp_but_keeps_broken_down():
    t = _truck("T", 5, hex_=(0, 0), bp_accumulated=40.0, broken_down=2)
    s = _state(trucks=[t])
    for kind, extra in ((EventKind.STAGE_ADVANCED, {"stage": 3}),
                        (EventKind.TURN_ADVANCED, {"turn": 2})):
        s2 = apply(s, Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", kind, extra))
        assert s2.truck("T").bp_accumulated == 0.0        # 21.25 BP cumulative within a stage only
        assert s2.truck("T").broken_down == 2             # 21.44 persists until repaired


# --- effective_points threads into the haulage layer -------------------------------------------

def test_broken_lorries_cannot_haul_or_be_detailed_to_a_column():
    t = _truck("T", 5, hex_=(0, 0), broken_down=3)
    s = _state(trucks=[t])
    assert supply.free_points(s, t) == 2                             # 5 - 3 broken
    assert supply.truck_load_admissible(t, {"FUEL": 240})            # 2 pts * 120 == 240
    assert not supply.truck_load_admissible(t, {"FUEL": 241})        # the broken 3 carry nothing


# --- 21.11 / 21.24 the breakdown check ---------------------------------------------------------

def test_a_convoy_that_crossed_the_desert_breaks_down():
    # A convoy that relocated and accrued Breakdown Points, checked in HOT weather (21.37 +1) so the
    # 21.38 column reaches the band where every roll breaks something. The percentage of its
    # effective Truck Points goes to broken_down (21.44) -- immobile until field-repaired.
    t = _truck("T", 10, hex_=(0, 0), bp_accumulated=100.0)
    s = _state(trucks=[t], weather="hot")
    r = _Run(s)
    _pin(r, "breakdown", 6, 6)                       # the roll is certified regardless of value
    _truck_breakdown(r, Side.ALLIED)
    checked = [e for e in r.events if e.kind == EventKind.TRUCK_BREAKDOWN_CHECKED]
    broke = [e for e in r.events if e.kind == EventKind.TRUCK_BROKE_DOWN]
    assert len(checked) == 1 and checked[0].rng_draws == (6, 6)      # dice on the record
    assert broke and r.state.truck("T").broken_down > 0
    check(r.state)


def test_a_convoy_that_barely_moved_does_not_check_21_27():
    # 21.27: three or fewer accumulated Breakdown Points -> no check, no roll, no event.
    t = _truck("T", 10, hex_=(0, 0), bp_accumulated=3.0)
    r = _Run(_state(trucks=[t], weather="hot"))
    _truck_breakdown(r, Side.ALLIED)
    assert not r.events


def test_the_bar_2_left_makes_a_convoy_break_down_LESS_than_a_tank():
    # 21.14: Trucks' BAR is favourable (2 Left). At the same accumulated BP + weather, a truck's
    # 21.38 column sits two left of a BAR-0 vehicle's -> a strictly lower breakdown percentage.
    for bp in (20.0, 40.0, 60.0):
        for roll in (34, 55, 66):
            truck_pct = ct.breakdown_result(bp, ct.TRUCK_BAR, 0, roll)
            bar0_pct = ct.breakdown_result(bp, 0, 0, roll)
            assert truck_pct <= bar0_pct


# --- 22.23 the field repair beat ---------------------------------------------------------------

def test_field_truck_repair_is_free_and_returns_points():
    # 22.23: a die of 1 repairs TWO Truck Points and costs NO supply (unlike the 22.26 tank fuel).
    t = _truck("T", 5, side=Side.AXIS, hex_=(0, 0), broken_down=3)
    r = _Run(_state(trucks=[t]))
    _pin(r, "repair", 1)                             # 22.8 field truck: 1 -> two Points
    _repair(r, Side.AXIS)
    repaired = [e for e in r.events if e.kind == EventKind.TRUCK_REPAIRED]
    assert repaired and repaired[0].payload["amount"] == 2 and repaired[0].rng_draws == (1,)
    assert not [e for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]   # FREE (22.23)
    assert r.state.truck("T").broken_down == 1
    check(r.state)


def test_field_truck_repair_a_three_to_six_repairs_nothing():
    t = _truck("T", 5, side=Side.AXIS, hex_=(0, 0), broken_down=3)
    r = _Run(_state(trucks=[t]))
    _pin(r, "repair", 4)                             # 22.8 field truck: 3-6 -> zero
    _repair(r, Side.AXIS)
    assert not [e for e in r.events if e.kind == EventKind.TRUCK_REPAIRED]
    assert r.state.truck("T").broken_down == 3


# --- 12.46 barrage destroys trucks -------------------------------------------------------------

def _arty(**kw) -> Unit:
    base = dict(id="AX-Arty", side=Side.AXIS, hex=(0, 0), steps=(StepRecord("g", 20),),
                mobility=Mobility.MOTORIZED, cpa=10, stacking_points=2, oca=0, dca=0, barrage=10)
    return Unit(**{**base, **kw})


def _foe() -> Unit:
    return Unit("AL-Inf", Side.ALLIED, (1, 0), (StepRecord("i", 6),), mobility=Mobility.FOOT,
                cpa=10, stacking_points=2, oca=5, dca=8)


def test_12_46_a_barrage_destroys_trucks_in_the_target_hex():
    # 20 Actual Barrage Points (col 8). Primary roll pinned first, then the SECOND, independent
    # d66 on the Truck row: code 66 at col 8 lands in the "2" range -> two Truck Points destroyed,
    # their cargo with them (rule "12.46").
    ammo = SupplyUnit("AX-Ammo", Side.AXIS, (0, 0), ammo=9999, fuel=0)
    tf = _truck("AL-T", 5, hex_=(1, 0), fuel=600)
    s = _state(units=[_arty(), _foe()], supplies=[ammo], trucks=[tf])
    r = _Run(s)
    _pin(r, "barrage", 1, 1, 6, 6)                   # primary 11, then truck 66 -> lose 2
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    barraged = [e for e in r.events if e.kind == EventKind.TRUCK_BARRAGED]
    killed = [e for e in r.events if e.kind == EventKind.TRUCK_POINTS_DESTROYED]
    assert len(barraged) == 1 and barraged[0].payload["points"] == 2 and barraged[0].rng_draws == (6, 6)
    assert killed and killed[0].payload["rule"] == "12.46"
    assert r.state.truck("AL-T").points == 3                         # 5 - 2
    assert r.state.truck("AL-T").fuel == 360                         # cargo went pro rata (3/5)
    check(r.state)


def test_12_46_no_second_roll_when_no_trucks_stand_in_the_hex():
    # 12.46 fires "if there are any Trucks in the same hex" -- none here, so no second die is
    # drawn and no TRUCK_BARRAGED is emitted (a truck-less hex stays byte-identical).
    ammo = SupplyUnit("AX-Ammo", Side.AXIS, (0, 0), ammo=9999, fuel=0)
    s = _state(units=[_arty(), _foe()], supplies=[ammo])
    r = _Run(s)
    _pin(r, "barrage", 1, 1, 1, 1)
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    assert not [e for e in r.events if e.kind == EventKind.TRUCK_BARRAGED]
    assert not [e for e in r.events if e.kind == EventKind.TRUCK_POINTS_DESTROYED]


def test_12_46_a_no_effect_truck_roll_certifies_the_dice_but_destroys_nothing():
    ammo = SupplyUnit("AX-Ammo", Side.AXIS, (0, 0), ammo=9999, fuel=0)
    tf = _truck("AL-T", 5, hex_=(1, 0), fuel=600)
    s = _state(units=[_arty(), _foe()], supplies=[ammo], trucks=[tf])
    r = _Run(s)
    _pin(r, "barrage", 1, 1, 1, 1)                   # truck code 11 -> No effect at every column
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    barraged = [e for e in r.events if e.kind == EventKind.TRUCK_BARRAGED]
    assert len(barraged) == 1 and barraged[0].payload["points"] == 0
    assert not [e for e in r.events if e.kind == EventKind.TRUCK_POINTS_DESTROYED]
    assert r.state.truck("AL-T").points == 5
    check(r.state)
