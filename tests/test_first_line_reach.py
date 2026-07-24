"""Phase 4 -- rule [53.11] FIRST-LINE TRUCKS, THE LAST MILE (activation slice).

The [60.31]/[60.41] first-line-truck allotment (test_first_line.py) is seeded onto units as the
fl_light/fl_medium/fl_heavy carrying-ceiling fields, but until this slice it was DORMANT: the 48
V.C.6 Supply Distribution top-up (engine._supply_distribution) refilled a unit's pools only from a
dump ON ITS HEX, so a unit adjacent to but not standing on a stocked forward dump starved even
though the supply was one hex away -- the binding constraint the faucet audit measured (delivered
Stores exceed eaten Stores threefold, yet 53% of Axis unit-Game-Turns take a stores shortfall).

This file pins the activation: a unit's organic first-line trucks (supply.first_line_dumps) reach a
dump within their round-trip basic-CPA range (53.22, CPA/2 one-way) and haul the load home, capped
at their 54.2 capacity (supply.first_line_capacity). WATER is deliberately excluded (it stays on the
abstract half-CPA trace, the S8 proxy). German units / reinforcements / garrisons own no first-line
trucks ([4.43b] deferred) and stay strictly in-hex.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import supply
from game.engine import _Run, _supply_distribution
from game.events import Phase, Side
from game.movement import TerrainMap
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain

STOCK = {"AMMO": 5000, "FUEL": 5000, "STORES": 5000, "WATER": 5000}


def _unit(uid: str, hex_, *, fl_medium: int = 0, fl_light: int = 0, fl_heavy: int = 0,
          cpa: int = 20) -> Unit:
    return Unit(uid, Side.AXIS, hex_, (StepRecord("inf", 4),), mobility=Mobility.MOTORIZED,
                cpa=cpa, stacking_points=1, oca=3, dca=3, barrage=0,
                fl_light=fl_light, fl_medium=fl_medium, fl_heavy=fl_heavy)


def _state(units, dumps) -> GameState:
    terr = {(q, 0): Terrain.CLEAR for q in range(12)}
    on_hand = {c: sum(getattr(d, c.lower()) for d in dumps)
               + sum(getattr(u, c.lower()) for u in units) for c in supply.COMMODITIES}
    return GameState(turn=1, max_turns=4, phase=Phase.ORGANIZATION, active_side=Side.AXIS, seed=1,
                     weather="clear", vp=VP(), terrain=TerrainMap(terrain=terr), control={},
                     units=tuple(units), target_hex=(11, 0), supplies=tuple(dumps),
                     consumed={c: 0 for c in supply.COMMODITIES}, initial_supply=on_hand)


def _dump(did: str, hex_, **stock) -> SupplyUnit:
    s = {**{c.lower(): 0 for c in supply.COMMODITIES}, **{k.lower(): v for k, v in stock.items()}}
    return SupplyUnit(did, Side.AXIS, hex_, ammo=s["ammo"], fuel=s["fuel"],
                      stores=s["stores"], water=s["water"])


# --- the 54.2 carrying ceiling -----------------------------------------------------------

def test_first_line_capacity_reads_the_54_2_chart():
    # Light 2/50/6/40, Medium 4/120/15/100, Heavy 8/250/30/200 Ammo/Fuel/Stores/Water per Truck Point.
    u = _unit("AX-1", (0, 0), fl_light=10, fl_medium=5, fl_heavy=2)
    assert supply.first_line_capacity(u, supply.STORES) == 10 * 6 + 5 * 15 + 2 * 30   # 195
    assert supply.first_line_capacity(u, supply.FUEL) == 10 * 50 + 5 * 120 + 2 * 250  # 1600
    assert supply.first_line_capacity(u, supply.AMMO) == 10 * 2 + 5 * 4 + 2 * 8        # 48
    assert supply.first_line_capacity(_unit("AX-2", (0, 0)), supply.STORES) == 0       # no trucks


# --- the last mile: a unit adjacent to a dump is now supplied -----------------------------

def test_trucked_unit_reaches_an_adjacent_dump_where_a_bare_unit_cannot():
    # THE HEADLINE: a unit ONE hex from a stocked dump. With first-line trucks it draws stores/fuel/
    # ammo across the last hex (53.11); with none it draws nothing (strict in-hex, 51.15/49.15).
    trucked = _unit("AX-T", (5, 0), fl_medium=5)
    bare = _unit("AX-B", (5, 0))                       # identical but no first-line trucks
    for u, buffers in ((trucked, True), (bare, False)):
        r = _Run(_state([u], [_dump("AX-D", (6, 0), **STOCK)]))
        _supply_distribution(r, Side.AXIS)
        got = r.state.unit(u.id)
        if buffers:
            assert got.stores == supply.first_line_capacity(u, supply.STORES) == 75
            assert got.fuel == supply.fuel_capacity(u) > 0
            assert got.ammo == supply.ammo_capacity(u) > 0
        else:
            assert got.stores == got.fuel == got.ammo == 0   # nothing crossed the last hex


def test_reach_is_bounded_by_the_round_trip_cpa():
    # 53.22: first-line trucks round-trip at basic CPA (20) -> one-way budget CPA/2 = 10 CP = 5 clear
    # hexes. A dump 5 hexes off is reachable; 6 hexes off is not (round trip 24 CP > 20).
    for dist, reachable in ((5, True), (6, False)):
        u = _unit("AX-1", (0, 0), fl_medium=5)
        r = _Run(_state([u], [_dump("AX-D", (dist, 0), **STOCK)]))
        _supply_distribution(r, Side.AXIS)
        assert (r.state.unit("AX-1").stores > 0) is reachable


def test_capacity_ceiling_caps_the_stores_buffer():
    # A unit beside a bottomless dump buffers stores only up to its first-line-truck ceiling (54.2),
    # never more -- fl_medium=3 -> 45 Stores, not the 5000 the dump holds.
    u = _unit("AX-1", (5, 0), fl_medium=3)
    r = _Run(_state([u], [_dump("AX-D", (6, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    assert r.state.unit("AX-1").stores == supply.first_line_capacity(u, supply.STORES) == 45


def test_water_is_not_drawn_through_the_first_line_tier():
    # WATER stays on the abstract half-CPA trace (S8 proxy): the refill beat never fills unit.water,
    # even beside a full dump with first-line trucks present.
    u = _unit("AX-1", (5, 0), fl_medium=5)
    r = _Run(_state([u], [_dump("AX-D", (6, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    assert r.state.unit("AX-1").water == 0


def test_refill_conserves_stores():
    # The haul is a pure dump->unit transfer (UNIT_REFILLED): stores neither minted nor lost.
    u = _unit("AX-1", (5, 0), fl_medium=5)
    r = _Run(_state([u], [_dump("AX-D", (6, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    on_hand = (sum(su.stores for su in r.state.supplies)
               + sum(x.stores for x in r.state.units))
    assert on_hand + r.state.consumed["STORES"] == r.state.initial_supply["STORES"] == 5000


def test_colocated_dump_still_feeds_a_bare_unit():
    # A unit STANDING ON a dump refills regardless of first-line trucks (48 V.C.6 same-hex): the
    # d=0 member of first_line_dumps, so the bare-unit in-hex path is unchanged.
    u = _unit("AX-1", (5, 0))                          # no first-line trucks
    r = _Run(_state([u], [_dump("AX-D", (5, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    got = r.state.unit("AX-1")
    assert got.fuel == supply.fuel_capacity(u) > 0     # fuel/ammo top up from the co-located dump
    assert got.ammo == supply.ammo_capacity(u) > 0
    assert got.stores == 0                             # but no lorries -> no stores buffer (51.0)
