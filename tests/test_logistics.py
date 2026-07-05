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
