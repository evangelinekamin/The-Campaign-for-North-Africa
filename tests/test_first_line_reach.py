"""Phase 4 -- rule [53.11] FIRST-LINE TRUCKS, THE LAST MILE (activation slice).

The [60.31]/[60.41] first-line-truck allotment (test_first_line.py) is seeded onto units as the
fl_light/fl_medium/fl_heavy carrying-ceiling fields, but until this slice it was DORMANT: the 48
V.C.6 Supply Distribution top-up (engine._supply_distribution) refilled a unit's FUEL/AMMO pools
from a co-located dump, and STORES -- which has no intrinsic 51.0 reservoir -- had no pool at all,
so a unit had to physically stand on a dump every Stores Expenditure or go short (the binding
constraint the faucet audit measured: delivered Stores exceed eaten Stores threefold, yet 53% of
Axis unit-Game-Turns take a stores shortfall).

This file pins the activation, and it pins the FAITHFUL shape of it. The draw stays strictly in-hex
(48 V.C.6 "supplies in the same hex"; 49.15; 53.24 loads first-line trucks IN PLACE during this
segment -- they do not drive a solo run, which is the 2nd/3rd-line convoy's job). There is NO supply
RANGE: the earlier cut reached a dump within a CPA/2 round trip, but that is rule 32.16, the ABSTRACT
game's supply range (Section 32, which rule 3 of this port says DOES NOT APPLY) -- removed. What
crosses the last hex is CARRIED, not reached: a unit's first-line trucks BUFFER stores from a
co-located dump up to their 54.2 ceiling (supply.first_line_capacity) and ride that ration forward as
the unit advances (53.22: first-line trucks move with the parent). WATER is excluded (it stays on the
abstract half-CPA trace, the S8 proxy). German units / reinforcements / garrisons own no first-line
trucks ([4.43b] deferred) and stay strictly in-hex.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataclasses import replace

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


# --- the last mile: a co-located dump buffers stores onto the lorries ---------------------

def test_a_colocated_dump_buffers_stores_a_bare_unit_gets_none():
    # THE HEADLINE, faithful shape: a unit STANDING ON a stocked dump buffers stores onto its own
    # first-line trucks (53.11), up to the 54.2 ceiling; a unit with NO first-line trucks buffers no
    # stores at all (51.0: stores have no intrinsic pool). Both top their 49.14 tank and 50.0 ammo
    # load from the co-located dump.
    trucked = _unit("AX-T", (5, 0), fl_medium=5)
    bare = _unit("AX-B", (5, 0))                       # identical but no first-line trucks
    for u, buffers in ((trucked, True), (bare, False)):
        r = _Run(_state([u], [_dump("AX-D", (5, 0), **STOCK)]))     # dump ON the unit's hex
        _supply_distribution(r, Side.AXIS)
        got = r.state.unit(u.id)
        assert got.fuel == supply.fuel_capacity(u) > 0
        assert got.ammo == supply.ammo_capacity(u) > 0
        if buffers:
            assert got.stores == supply.first_line_capacity(u, supply.STORES) == 75
        else:
            assert got.stores == 0                     # no lorries -> no stores buffer (51.0)


def test_no_cross_hex_reach_the_last_mile_is_not_a_supply_range():
    # 48 V.C.6 redistributes "supplies in the same hex"; 53.24 loads first-line trucks IN PLACE during
    # this segment. There is NO supply RANGE -- the removed CPA/2 reach was rule 32.16, the ABSTRACT
    # game (rule 3: DOES NOT APPLY). A dump one hex away (or five) feeds NOTHING here, WITH or WITHOUT
    # first-line trucks -- the trucks buffer, they do not ferry.
    for dist in (1, 5):
        trucked = _unit("AX-T", (0, 0), fl_medium=5)
        bare = _unit("AX-B", (0, 0))
        for u in (trucked, bare):
            r = _Run(_state([u], [_dump("AX-D", (dist, 0), **STOCK)]))
            _supply_distribution(r, Side.AXIS)
            got = r.state.unit(u.id)
            assert got.stores == got.fuel == got.ammo == 0   # nothing crossed the last hex


def test_the_buffered_stores_ride_forward_to_an_empty_hex():
    # THE LAST MILE, CARRIED. A unit tops its stores buffer on a co-located dump, then ADVANCES one
    # hex off the dump (53.22: first-line trucks move with the parent). On its new, empty hex it still
    # draws its Stores requirement from its own lorry-borne pool (in_hex_draw own-pool-first) -- so it
    # eats though the dump is now a hex behind. That is how supply crosses the last hex faithfully.
    u = _unit("AX-1", (5, 0), fl_medium=5)
    r = _Run(_state([u], [_dump("AX-D", (5, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    fed = r.state.unit("AX-1")
    assert fed.stores == 75

    advanced = replace(fed, hex=(4, 0))                # marched one hex forward, off the dump
    empty = _state([advanced], [])                     # no dump on the new hex
    draws = supply.in_hex_draw(empty, advanced, supply.STORES, supply.stores_cost(advanced))
    assert draws is not None                            # not a shortfall -- the buffer covers it
    assert draws == [("unit", "AX-1", supply.stores_cost(advanced))]   # drawn from own lorry stores


def test_capacity_ceiling_caps_the_stores_buffer():
    # A unit ON a bottomless dump buffers stores only up to its first-line-truck ceiling (54.2), never
    # more -- fl_medium=3 -> 45 Stores, not the 5000 the dump holds.
    u = _unit("AX-1", (5, 0), fl_medium=3)
    r = _Run(_state([u], [_dump("AX-D", (5, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    assert r.state.unit("AX-1").stores == supply.first_line_capacity(u, supply.STORES) == 45


def test_water_is_not_drawn_through_the_first_line_tier():
    # WATER stays on the abstract half-CPA trace (S8 proxy): the refill beat never fills unit.water,
    # even standing on a full dump with first-line trucks present.
    u = _unit("AX-1", (5, 0), fl_medium=5)
    r = _Run(_state([u], [_dump("AX-D", (5, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    assert r.state.unit("AX-1").water == 0


def test_refill_conserves_stores():
    # The buffer fill is a pure dump->unit transfer (UNIT_REFILLED): stores neither minted nor lost.
    u = _unit("AX-1", (5, 0), fl_medium=5)
    r = _Run(_state([u], [_dump("AX-D", (5, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    on_hand = (sum(su.stores for su in r.state.supplies)
               + sum(x.stores for x in r.state.units))
    assert on_hand + r.state.consumed["STORES"] == r.state.initial_supply["STORES"] == 5000


def test_colocated_dump_still_feeds_a_bare_unit():
    # A unit STANDING ON a dump refills its intrinsic pools regardless of first-line trucks (48 V.C.6
    # same-hex): the strict in-hex path, unchanged.
    u = _unit("AX-1", (5, 0))                          # no first-line trucks
    r = _Run(_state([u], [_dump("AX-D", (5, 0), **STOCK)]))
    _supply_distribution(r, Side.AXIS)
    got = r.state.unit("AX-1")
    assert got.fuel == supply.fuel_capacity(u) > 0     # fuel/ammo top up from the co-located dump
    assert got.ammo == supply.ammo_capacity(u) > 0
    assert got.stores == 0                             # but no lorries -> no stores buffer (51.0)
