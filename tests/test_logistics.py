"""Full-logistics consumption (rules 49-52; CHUNK 2 sub-steps C/D).

The Stores Expenditure Stage (rule 48 IV) expends Stores (51) and Water (52) from
the dumps a unit can trace, after fuel/water evaporate (49.3/52.44), applies the
Italian Pasta Rule (52.6), and -- for units that go unsupplied -- drives the 51/52
shortfall attrition through the existing STEP_LOST/COHESION path. These tests pin
the consumption + conservation, the evaporation sink, the pasta beat, and the
cut-off degradation."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import supply
from game.engine import _logistics, _Run
from game.events import EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain

FOUR = ("AMMO", "FUEL", "STORES", "WATER")


def _state(units=(), supplies=(), *, weather="clear") -> GameState:
    hexes = {u.hex for u in units} | {s.hex for s in supplies} | {(0, 0)}
    terr = {h: Terrain.CLEAR for h in hexes}
    initial = {c: sum(getattr(s, c.lower()) for s in supplies) for c in FOUR}
    return GameState(
        turn=1, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM, seed=1,
        weather=weather, move_modifier=0, vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={}),
        control={}, units=tuple(units), target_hex=(0, 0), supplies=tuple(supplies),
        consumed={c: 0 for c in FOUR}, initial_supply=initial)


def _inf(uid, hex=(0, 0), *, strength=3, side=Side.AXIS, cohesion=0) -> Unit:
    return Unit(uid, side, hex, (StepRecord("i", strength),), mobility=Mobility.FOOT,
                cpa=10, stacking_points=1, oca=5, dca=5, cohesion=cohesion)


def _conserves(state) -> bool:
    return all(sum(getattr(su, c.lower()) for su in state.supplies)
               + state.consumed.get(c, 0) == state.initial_supply[c] for c in FOUR)


# --- stores + water consumption folds and conserves --------------------------

def test_stores_and_water_consumed_and_conserved():
    unit = _inf("U")                                    # foot infantry, strength 3
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=100, water=100)
    r = _Run(_state([unit], [dump]))
    _logistics(r)
    kinds = [(e.payload.get("commodity"), e.payload.get("unit_id"))
             for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]
    assert ("STORES", "U") in kinds                     # 51.11: 4 x TOE stores
    assert ("WATER", "U") in kinds                      # 52.41: 1 water (infantry, flat)
    d = r.state.supply("D")
    assert d.stores == 100 - supply.stores_cost(unit)   # 100 - 12
    assert _conserves(r.state)
    check(r.state)


# --- evaporation is a conserving sink (49.3 / 52.44) -------------------------

def test_evaporation_is_a_conserving_sink():
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=50, fuel=100, stores=50, water=100)
    r = _Run(_state([], [dump]))                        # no units -> only evaporation runs
    _logistics(r)
    evap = [e for e in r.events if e.kind == EventKind.SUPPLY_EVAPORATED]
    assert {e.payload["commodity"] for e in evap} == {"FUEL", "WATER"}   # ammo/stores don't evaporate
    d = r.state.supply("D")
    assert (d.fuel, d.water) == (94, 94)                # 6% rounded down
    assert (d.ammo, d.stores) == (50, 50)               # untouched
    assert r.state.consumed["FUEL"] == 6 and r.state.consumed["WATER"] == 6
    assert _conserves(r.state)
    check(r.state)


def test_hot_weather_evaporates_eleven_percent():
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=100, stores=0, water=100)
    r = _Run(_state([], [dump], weather="hot"))
    _logistics(r)
    d = r.state.supply("D")
    assert (d.fuel, d.water) == (89, 89)                # 6% + 5% hot = 11%
    assert _conserves(r.state)


# --- the Italian Pasta Rule (52.6) -------------------------------------------

def test_pasta_caps_unwatered_italian():
    # An Italian battalion that receives its Stores but no Water for its pasta is
    # flagged PASTA_DENIED (may not exceed its CPA that turn).
    it = _inf("IT-X")
    dry = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=100, water=0)
    r = _Run(_state([it], [dry]))
    _logistics(r)
    assert any(e.kind == EventKind.PASTA_DENIED and e.payload["unit_id"] == "IT-X"
               for e in r.events)


def test_watered_italian_gets_its_pasta_point():
    it = _inf("IT-X")
    wet = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=100, water=100)
    r = _Run(_state([it], [wet]))
    _logistics(r)
    assert not any(e.kind == EventKind.PASTA_DENIED for e in r.events)
    # the pasta point IS drawn (an extra water beyond the 52.41 point)
    water_draws = [e for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED
                   and e.payload["commodity"] == "WATER" and e.payload["unit_id"] == "IT-X"]
    assert len(water_draws) == 2                         # pasta point + normal 52.41 water


def test_pasta_disorganizes_a_shaky_italian():
    # 52.6: a denied Italian already at Cohesion -10 or worse immediately disorganizes
    # as if at -26, feeding the live surrender path.
    it = _inf("IT-X", cohesion=-10)
    dry = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=100, water=0)
    r = _Run(_state([it], [dry]))
    _logistics(r)
    assert any(e.kind == EventKind.COHESION_CHANGED and e.payload["unit_id"] == "IT-X"
               for e in r.events)
    assert r.state.unit("IT-X").cohesion == -26

    # a denied Italian still in good order (cohesion 0) is capped but NOT disorganized
    r2 = _Run(_state([_inf("IT-Y")], [dry]))
    _logistics(r2)
    assert any(e.kind == EventKind.PASTA_DENIED for e in r2.events)
    assert not any(e.kind == EventKind.COHESION_CHANGED for e in r2.events)


# --- opt-in: ammo/fuel-only scenarios skip logistics entirely ----------------

def test_logistics_skipped_when_no_stores_or_water():
    unit = _inf("U")
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=40, fuel=60)   # stores/water 0
    r = _Run(_state([unit], [dump]))
    _logistics(r)
    assert not r.events                                 # inert: no LOGISTICS phase, byte-identical


# --- SUB-STEP D: shortfall counters + attrition ------------------------------

def _cutoff(unit) -> _Run:
    """A unit at (0,0) with a stocked dump stranded far away at (9,9): the two hexes
    are disconnected, so nothing can be traced -- the unit is cut off (but the scenario
    still models full logistics, so the phase engages)."""
    dump = SupplyUnit("D", Side.AXIS, (9, 9), ammo=0, fuel=0, stores=500, water=500)
    return _Run(_state([unit], [dump]))


def test_cutoff_unit_accrues_shortfalls_and_conserves():
    r = _cutoff(_inf("U"))
    _logistics(r)
    assert any(e.kind == EventKind.STORES_SHORTFALL and e.payload["unit_id"] == "U"
               for e in r.events)
    assert any(e.kind == EventKind.WATER_SHORTFALL and e.payload["unit_id"] == "U"
               for e in r.events)
    u = r.state.unit("U")
    assert (u.turns_without_stores, u.stages_without_water, u.disorganization) == (1, 1, 1)
    assert _conserves(r.state)


def test_sustained_stores_shortfall_disorganizes():
    # 51.21: after DISORGANIZED_AFTER (6) consecutive short turns the unit disorganizes
    # via COHESION_CHANGED, feeding the surrender path; earlier turns only accrue points.
    # Water is supplied (co-located dump has water, no stores) so the unit survives long
    # enough for the stores disorganization to bite (a cut-off unit dies of thirst first).
    from game.engine import DISORGANIZED_AFTER
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=0, water=500)
    r = _Run(_state([_inf("U", strength=3)], [dump]))
    for _ in range(DISORGANIZED_AFTER - 1):
        _logistics(r)
    assert not any(e.kind == EventKind.COHESION_CHANGED for e in r.events)   # not yet
    _logistics(r)                                       # the DISORGANIZED_AFTER-th short turn
    assert any(e.kind == EventKind.COHESION_CHANGED and e.payload["unit_id"] == "U"
               for e in r.events)
    assert r.state.unit("U").turns_without_stores == DISORGANIZED_AFTER


def test_two_consecutive_turns_without_stores_attrit_infantry():
    # 51.22: 2% of TOE at 2 consecutive short game-turns (infantry only). Water is
    # supplied here (co-located dump has water, no stores) to isolate the stores loss.
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=0, water=500)
    r = _Run(_state([_inf("U", strength=100)], [dump]))
    _logistics(r)
    assert not any(e.kind == EventKind.STEP_LOST for e in r.events)          # first short turn: none
    _logistics(r)                                       # second consecutive short turn
    losses = [e for e in r.events if e.kind == EventKind.STEP_LOST
              and e.payload.get("role") == "attrition"]
    assert losses and losses[0].payload["amount"] == 2                       # 2% of 100
    assert r.state.unit("U").strength == 98


def test_water_shortfall_costs_a_step_after_the_first_stage():
    # 52.53: one TOE per consecutive Operations Stage AFTER the first without water.
    # Stores supplied (co-located dump has stores, no water) to isolate the water loss.
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=500, water=0)
    r = _Run(_state([_inf("U", strength=5)], [dump]))
    _logistics(r)
    assert not any(e.kind == EventKind.STEP_LOST for e in r.events)          # first stage: none
    _logistics(r)                                       # second consecutive dry stage
    losses = [e for e in r.events if e.kind == EventKind.STEP_LOST
              and e.payload.get("role") == "attrition"]
    assert losses and losses[0].payload["amount"] == 1
    assert r.state.unit("U").strength == 4


def test_guns_are_exempt_from_shortfall_attrition():
    # 51.22: only infantry-type TOE may be eliminated. A gun (artillery) starves without
    # losing steps.
    gun = replace(_inf("G", strength=100), vulnerability=5)   # is_gun -> not infantry
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=0, water=500)
    r = _Run(_state([gun], [dump]))
    _logistics(r)
    _logistics(r)
    assert not any(e.kind == EventKind.STEP_LOST for e in r.events)
    assert r.state.unit("G").strength == 100


def test_resupply_resets_the_consecutive_counter():
    # A unit that had gone short but now draws stores/water resets its consecutive count
    # (Disorganization persists -- recovery is the deferred Reorganization, 19/20).
    unit = replace(_inf("U"), turns_without_stores=3, stages_without_water=2, disorganization=3)
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=500, water=500)
    r = _Run(_state([unit], [dump]))
    _logistics(r)
    assert any(e.kind == EventKind.STORES_RESTORED for e in r.events)
    assert any(e.kind == EventKind.WATER_RESTORED for e in r.events)
    u = r.state.unit("U")
    assert (u.turns_without_stores, u.stages_without_water) == (0, 0)
    assert u.disorganization == 3                       # persists
