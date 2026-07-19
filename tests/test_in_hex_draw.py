"""Phase 4, slice S3: the FULL-GAME in-hex supply draw (supply.in_hex_draw) and its two
conserving folds (UNIT_SUPPLY_CONSUMED / UNIT_REFILLED), tested in isolation on constructed
boards.

These are DORMANT in run() -- no consumer emits them yet (the parallel-run, design sec 3) -- so
this file is the only exercise of the draw priority and the fold conservation until a consumer is
switched onto in_hex_draw (S5). DAK-5le sits at (0,0) sharing its hex with AX-Dump1 (fuel=60,
ammo=40); that shared hex is the fixture for the whole draw priority."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import apply as apply_mod
from game import supply
from game.events import Event, EventKind, Phase, Side
from game.scenario import coastal_corridor
from game.state import TruckFormation


def _ev(kind: EventKind, payload: dict) -> Event:
    return Event(seq=0, turn=1, phase=Phase.LOGISTICS, side=Side.AXIS,
                 actor="AXIS/Front", kind=kind, payload=payload)


def test_draws_own_pool_first():
    # 49.16: a unit with fuel in its own 49.14 tank draws THAT first, never touching the
    # co-located dump while the tank covers the need.
    s = coastal_corridor()
    dak = replace(s.unit("DAK-5le"), fuel=50)
    s = s.with_unit(dak)
    assert supply.in_hex_draw(s, dak, supply.FUEL, 30) == [("unit", "DAK-5le", 30)]


def test_own_pool_exact_cover_skips_dump():
    s = coastal_corridor()
    dak = replace(s.unit("DAK-5le"), fuel=30)
    s = s.with_unit(dak)
    assert supply.in_hex_draw(s, dak, supply.FUEL, 30) == [("unit", "DAK-5le", 30)]


def test_falls_through_to_colocated_dump():
    # own tank drained first, the remainder from the dump ON the hex (54.11).
    s = coastal_corridor()
    dak = replace(s.unit("DAK-5le"), fuel=20)
    s = s.with_unit(dak)
    assert supply.in_hex_draw(s, dak, supply.FUEL, 50) == [
        ("unit", "DAK-5le", 20), ("dump", "AX-Dump1", 30)]


def test_dump_only_when_own_pool_empty():
    # the default seeded state: DAK's fuel tank is 0 (S1 tank-fill deferred), so a fuel draw
    # comes wholly from the co-located dump -- the pre-Phase-4 behaviour, expressed in-hex.
    s = coastal_corridor()
    dak = s.unit("DAK-5le")
    assert dak.fuel == 0
    assert supply.in_hex_draw(s, dak, supply.FUEL, 15) == [("dump", "AX-Dump1", 15)]


def test_empty_hex_returns_none():
    # a unit off the dump network with a dry tank cannot be supplied -- there is NO trace to a
    # distant dump in the full game (49.15). DAK moved to (3,1), no dump there, tank empty.
    s = coastal_corridor()
    dak = replace(s.unit("DAK-5le"), hex=(3, 1), fuel=0)
    s = s.with_unit(dak)
    assert supply.in_hex_draw(s, dak, supply.FUEL, 10) is None


def test_partial_cover_returns_none():
    # the hex holds SOME but not enough: the draw fails as a whole (the caller rejects the move),
    # it does not return a partial list.
    s = coastal_corridor()
    dak = replace(s.unit("DAK-5le"), hex=(3, 1), fuel=8)
    s = s.with_unit(dak)
    assert supply.in_hex_draw(s, dak, supply.FUEL, 10) is None


def test_convoy_truck_on_hex_is_not_a_source():
    # 49.16: "such fuel from convoying trucks must be off-loaded first." A 2nd-line truck full
    # of fuel, parked on the unit's hex, is NOT a draw source until it unloads into a dump.
    s = coastal_corridor()
    dak = replace(s.unit("DAK-5le"), hex=(3, 1), fuel=0)          # off the dump, dry
    truck = TruckFormation("AX-Conv", Side.AXIS, (3, 1), "medium", points=10, fuel=500)
    s = s.with_unit(dak).with_truck(truck)
    assert supply.in_hex_draw(s, dak, supply.FUEL, 10) is None    # truck fuel is unreachable


def test_enemy_dump_on_hex_is_not_a_source():
    # in-hex draw is friendly-only: an enemy dump sharing the hex is not drawn (a captured dump
    # has already flipped side by the time a unit draws, so active_supplies(unit.side) is right).
    s = coastal_corridor()
    dak = replace(s.unit("DAK-5le"), hex=(6, 0), fuel=0)          # onto UK-Dump1's hex
    s = s.with_unit(dak)
    assert supply.in_hex_draw(s, dak, supply.FUEL, 10) is None


def test_zero_need_is_empty_draw():
    s = coastal_corridor()
    assert supply.in_hex_draw(s, s.unit("DAK-5le"), supply.FUEL, 0) == []


def test_ammo_draws_same_priority():
    # the function is commodity-agnostic: ammo from the first-line pool first, then the dump.
    s = coastal_corridor()
    dak = replace(s.unit("DAK-5le"), ammo=5)
    s = s.with_unit(dak)
    assert supply.in_hex_draw(s, dak, supply.AMMO, 12) == [
        ("unit", "DAK-5le", 5), ("dump", "AX-Dump1", 7)]


def test_unit_supply_consumed_fold_conserves():
    # UNIT_SUPPLY_CONSUMED drains the unit's own pool and books it to consumed[] -- the local
    # identity pool_before == pool_after + consumed_delta (dual of SUPPLY_CONSUMED off a unit).
    s = coastal_corridor()
    s = s.with_unit(replace(s.unit("DAK-5le"), fuel=50))
    before = s.consumed.get("FUEL", 0)
    s2 = apply_mod.apply(s, _ev(EventKind.UNIT_SUPPLY_CONSUMED,
                                {"unit_id": "DAK-5le", "commodity": supply.FUEL, "qty": 18}))
    assert s2.unit("DAK-5le").fuel == 32
    assert s2.consumed["FUEL"] == before + 18


def test_unit_refilled_fold_conserves():
    # UNIT_REFILLED is the 48 V.C.6 top-up: dump -> unit, a conserving transfer. Dump down,
    # unit up, consumed unchanged (grand total constant, the dual of TRUCK_LOADED).
    s = coastal_corridor()
    s = s.with_unit(replace(s.unit("DAK-5le"), fuel=0))
    before_consumed = dict(s.consumed)
    s2 = apply_mod.apply(s, _ev(EventKind.UNIT_REFILLED,
                                {"unit_id": "DAK-5le", "supply_id": "AX-Dump1",
                                 "commodity": supply.FUEL, "qty": 25}))
    assert s2.unit("DAK-5le").fuel == 25
    assert s2.supply("AX-Dump1").fuel == 60 - 25
    assert s2.consumed == before_consumed         # nothing left the system
