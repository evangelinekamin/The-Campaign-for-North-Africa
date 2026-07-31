"""Axis Coastal Shipping (rule 56.3) -- the small, fixed, fully-deterministic fleet that shuttles
already-landed cargo port to port without spending truck capacity. See
scratchpad/port/transcriptions/56.3-axis-inter-port-transport.md for the transcription and the
routing notes (no Terrain.SEA layer, Tripoli off-map) game.engine._coastal_shipping works around.

Two ports, six hexes apart (`_ports`, distance six -- well inside one Phase's 50-point CPA) or
sixty apart (`_far_ports`, distance sixty -- forces a voyage to span two Phases) let every case
run without needing the real campaign map."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import invariants, supply
from game.apply import apply
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy, coastal_shipping_doctrine
from game.engine import _coastal_shipping, _Run, determinism_signature, run
from game.events import Control, Event, EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import CoastalShipOrder, Policy, ScriptedPolicy
from game.scenario import campaign, rommels_arrival, siege_of_tobruk
from game.state import CoastalShip, GameState, Port, SupplyUnit, VP
from game.terrain import Terrain


def _port(pid, hex_, *, eff=5, max_eff=5, side=Side.AXIS):
    return Port(pid, side, hex_, "major", max_eff=max_eff, eff=eff,
               cap_ammo=100_000, cap_fuel=100_000, cap_stores=100_000, cap_water=0,
               cap_tons=100_000)


def _dump(sid, hex_, *, side=Side.AXIS, fuel=0, ammo=0, stores=0):
    return SupplyUnit(sid, side, hex_, ammo=ammo, fuel=fuel, stores=stores, water=0)


def _ship(sid="AX-Ship-A", *, port="PORT-A", tons=1000, dest=None, progress=0,
         fuel=0, ammo=0, stores=0, side=Side.AXIS):
    return CoastalShip(sid, side, tons, port, dest=dest, progress=progress,
                       ammo=ammo, fuel=fuel, stores=stores)


def _ports(dist=6):
    return _port("PORT-A", (0, 0)), _port("PORT-B", (dist, 0))


def _state(*, ships=(), ports=None, supplies=(), dist=6) -> GameState:
    a, b = ports if ports is not None else _ports(dist)
    terr = {a.hex: Terrain.MAJOR_CITY, b.hex: Terrain.MAJOR_CITY}
    return GameState(
        turn=1, max_turns=4, phase=Phase.LOGISTICS, active_side=Side.AXIS, seed=0,
        weather="clear", vp=VP(), terrain=TerrainMap(terrain=terr, fortifications={}),
        control={}, units=(), target_hex=b.hex, supplies=supplies, consumed={},
        initial_supply={}, ports=(a, b), ships=ships)


class _StubPolicy:
    """A bare coastal_shipping_orders stub -- _coastal_shipping asks for nothing else."""
    def __init__(self, orders=()):
        self._orders = list(orders)

    def coastal_shipping_orders(self, state, side):
        return self._orders


# --- the state field / campaign seeding ---------------------------------------------------------

def test_ships_default_empty():
    assert GameState.__dataclass_fields__["ships"].default == ()
    for s in (rommels_arrival(), siege_of_tobruk()):
        assert s.ships == ()


def test_campaign_seeds_four_ships_at_benghazi_empty():
    s = campaign(seed=1941, max_turns=1)
    assert len(s.ships) == 4
    assert {sh.tons for sh in s.ships} == {1000, 1000, 1000, 2000}   # 56.31: A/B/C 1000t, D 2000t
    benghazi = s.port("PORT-Benghazi")
    assert benghazi is not None
    for sh in s.ships:
        assert sh.side == Side.AXIS
        assert sh.port == benghazi.id
        assert sh.dest is None and sh.progress == 0
        assert (sh.ammo, sh.fuel, sh.stores, sh.water) == (0, 0, 0, 0)   # 59.54: begins unloaded


# --- fold-only: apply() in isolation ------------------------------------------------------------

def test_loaded_fold_moves_dump_to_ship_conserving():
    dump = _dump("D", (0, 0), fuel=500)
    ship = _ship()
    s = _state(ships=(ship,), supplies=(dump,))
    e = Event(0, 1, Phase.LOGISTICS, Side.AXIS, "AXIS/Logistics", EventKind.COASTAL_SHIP_LOADED,
              {"ship_id": ship.id, "supply_id": dump.id, "cargo": {"FUEL": 300}})
    s2 = apply(s, e)
    assert s2.supply("D").fuel == 200
    assert s2.ship(ship.id).fuel == 300
    assert s2.ship(ship.id).ammo == 0 and s2.ship(ship.id).stores == 0


def test_unloaded_fold_moves_ship_to_dump_conserving():
    dump = _dump("D", (6, 0), fuel=0)
    ship = _ship(port="PORT-B", fuel=400)
    s = _state(ships=(ship,), supplies=(dump,))
    e = Event(0, 1, Phase.LOGISTICS, Side.AXIS, "AXIS/Logistics", EventKind.COASTAL_SHIP_UNLOADED,
              {"ship_id": ship.id, "supply_id": dump.id, "cargo": {"FUEL": 400}})
    s2 = apply(s, e)
    assert s2.supply("D").fuel == 400
    assert s2.ship(ship.id).fuel == 0


def test_sailed_fold_banks_progress_without_arriving():
    ship = _ship(dest=None, progress=0)
    s = _state(ships=(ship,))
    e = Event(0, 1, Phase.LOGISTICS, Side.AXIS, "AXIS/Logistics", EventKind.COASTAL_SHIP_SAILED,
              {"ship_id": ship.id, "dest": "PORT-B", "progress": 40, "arrived": False})
    s2 = apply(s, e)
    sh2 = s2.ship(ship.id)
    assert sh2.dest == "PORT-B" and sh2.progress == 40 and sh2.port == "PORT-A"


def test_sailed_fold_arrival_resets_dest_and_progress():
    ship = _ship(dest="PORT-B", progress=44)
    s = _state(ships=(ship,))
    e = Event(0, 1, Phase.LOGISTICS, Side.AXIS, "AXIS/Logistics", EventKind.COASTAL_SHIP_SAILED,
              {"ship_id": ship.id, "dest": "PORT-B", "progress": 6, "arrived": True})
    s2 = apply(s, e)
    sh2 = s2.ship(ship.id)
    assert sh2.port == "PORT-B" and sh2.dest is None and sh2.progress == 0


# --- behavioural: _coastal_shipping over the _Run harness ----------------------------------------

def test_no_ships_no_op_byte_identical():
    s = _state(ships=())
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy(), Side.AXIS)
    assert r.events == []                      # the guard _truck_convoys itself uses


def test_load_and_depart_completes_within_one_phase_when_cpa_allows():
    # distance 6: load (5) + travel (6) = 11 CP, well inside the 50-point CPA (56.31/56.34).
    dump_a = _dump("D-A", (0, 0), fuel=1000)
    dump_b = _dump("D-B", (6, 0), fuel=0)              # 56.28: every port has a dump built in
    ship = _ship()
    s = _state(ships=(ship,), supplies=(dump_a, dump_b))
    order = CoastalShipOrder(ship.id, load_from="D-A", load={"FUEL": 400}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    kinds = [e.kind for e in r.events if e.kind != EventKind.PHASE_ADVANCED]
    assert kinds == [EventKind.COASTAL_SHIP_LOADED, EventKind.COASTAL_SHIP_SAILED,
                     EventKind.COASTAL_SHIP_UNLOADED]
    final = r.state.ship(ship.id)
    assert final.port == "PORT-B" and final.dest is None and final.fuel == 0   # auto-unloaded
    assert r.state.supply("D-A").fuel == 600
    assert r.state.supply("D-B").fuel == 400


def test_voyage_spans_multiple_phases_when_cpa_is_not_enough():
    # distance 60: one Phase cannot cover load(5) + 60 sea hexes inside a 50-point CPA.
    dump_a = _dump("D-A", (0, 0), fuel=1000)
    dump_b = _dump("D-B", (60, 0), fuel=0)
    ship = _ship()
    s = _state(ships=(ship,), supplies=(dump_a, dump_b), dist=60)
    order = CoastalShipOrder(ship.id, load_from="D-A", load={"FUEL": 400}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)          # Phase 1: load + partial sail
    mid = r.state.ship(ship.id)
    assert mid.port == "PORT-A" and mid.dest == "PORT-B" and mid.fuel == 400
    assert 0 < mid.progress < 60
    first_progress = mid.progress

    _coastal_shipping(r, _StubPolicy(), Side.AXIS)                 # Phase 2: auto-continue, no order
    mid2 = r.state.ship(ship.id)
    if mid2.port == "PORT-A":                                      # still short (progress < 50/phase)
        assert mid2.progress > first_progress
        _coastal_shipping(r, _StubPolicy(), Side.AXIS)             # Phase 3: arrives
        mid2 = r.state.ship(ship.id)
    assert mid2.port == "PORT-B" and mid2.dest is None and mid2.fuel == 0   # arrived and auto-unloaded


def test_en_route_ship_needs_no_order_and_ignores_a_fresh_one():
    # distance 60, progress 5: this Phase's 50-point CPA (5 + 50 = 55) still falls short, so the
    # ship stays en route -- isolating "did it keep sailing toward PORT-B" from "did it arrive".
    ship = _ship(dest="PORT-B", progress=5, fuel=200)
    s = _state(ships=(ship,), dist=60)
    bogus = CoastalShipOrder(ship.id, to="PORT-A")     # a redirect attempt on a ship at sea
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([bogus]), Side.AXIS)
    rejects = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert len(rejects) == 1
    assert "under way" in rejects[0].payload["reason"]
    sailed = [e for e in r.events if e.kind == EventKind.COASTAL_SHIP_SAILED]
    assert len(sailed) == 1 and sailed[0].payload["dest"] == "PORT-B"   # kept its ORIGINAL heading
    final = r.state.ship(ship.id)
    assert final.dest == "PORT-B" and final.progress == 5 + 50 and final.fuel == 200


def test_single_cargo_type_only_load_rejected_while_carrying():
    # No dump at the ship's OWN port: the Phase's automatic leftover-cargo unload (56.34) has
    # nothing to unload into, so the ship is still genuinely carrying fuel when the fresh order
    # is considered -- isolating the 56.34 "one type at a time" check from the auto-unload path.
    dump_b = _dump("D-B", (6, 0), ammo=500)
    ship = _ship(fuel=100)                              # already carrying fuel
    s = _state(ships=(ship,), supplies=(dump_b,))
    order = CoastalShipOrder(ship.id, load_from="D-B", load={"AMMO": 50}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    rejects = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert any("only one type" in e.payload["reason"] for e in rejects)
    assert r.state.ship(ship.id).ammo == 0               # the AMMO never boarded
    assert r.state.ship(ship.id).fuel == 100              # and the fuel never left


def test_neutralized_destination_port_refuses_entry():
    a, b = _ports()
    b = replace(b, eff=0)                                # 56.33: Capacity Level zero
    dump = _dump("D", (0, 0), fuel=500)
    ship = _ship()
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump,))
    order = CoastalShipOrder(ship.id, load_from="D", load={"FUEL": 100}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    rejects = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert any("neutralized" in e.payload["reason"] for e in rejects)
    assert not any(e.kind == EventKind.COASTAL_SHIP_SAILED for e in r.events)
    assert r.state.ship(ship.id).fuel == 100             # loaded, but never sailed


def test_enemy_held_destination_port_refuses_entry():
    a, b = _ports()
    dump = _dump("D", (0, 0), fuel=500)
    ship = _ship()
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump,))
    s = replace(s, control={b.hex: Control.ALLIED})
    order = CoastalShipOrder(ship.id, load_from="D", load={"FUEL": 100}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    rejects = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert any("enemy-held" in e.payload["reason"] for e in rejects)


def test_load_exceeding_capacity_rejected():
    dump = _dump("D", (0, 0), fuel=100_000)
    ship = _ship(tons=1000)                              # 1000 tons -> 8000 Fuel Points (54.5)
    s = _state(ships=(ship,), supplies=(dump,))
    order = CoastalShipOrder(ship.id, load_from="D", load={"FUEL": 8001}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    rejects = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert any("tonnage capacity" in e.payload["reason"] for e in rejects)


def test_dump_lacking_the_load_rejected():
    dump = _dump("D", (0, 0), fuel=10)
    ship = _ship()
    s = _state(ships=(ship,), supplies=(dump,))
    order = CoastalShipOrder(ship.id, load_from="D", load={"FUEL": 500}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    rejects = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert any("lacks the ordered load" in e.payload["reason"] for e in rejects)


def test_no_die_ever_rolled():
    # 56.31-56.35 carries no chart, no die -- every emitted event's rng_draws is empty.
    dump = _dump("D", (0, 0), fuel=1000)
    ship = _ship()
    s = _state(ships=(ship,), supplies=(dump,))
    order = CoastalShipOrder(ship.id, load_from="D", load={"FUEL": 400}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    assert all(e.rng_draws == () for e in r.events)


# --- the campaign doctrine (game.campaign_policy.coastal_shipping_doctrine) ----------------------

def test_doctrine_ships_the_richest_ports_surplus_toward_the_poorest():
    a, b = _ports()
    dump_a = _dump("D-A", a.hex, fuel=8000)
    dump_b = _dump("D-B", b.hex, fuel=0)
    ship = _ship(port="PORT-A")
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump_a, dump_b))
    orders = coastal_shipping_doctrine(s, Side.AXIS)
    assert len(orders) == 1
    o = orders[0]
    assert o.ship_id == ship.id and o.to == "PORT-B"
    assert o.load_from == "D-A" and set(o.load) == {"FUEL"}
    assert o.load["FUEL"] == min(8000, supply.tons_to_points(ship.tons, "FUEL"))


def test_doctrine_sends_an_idle_ship_back_to_the_richest_port():
    a, b = _ports()
    dump_a = _dump("D-A", a.hex, fuel=8000)
    dump_b = _dump("D-B", b.hex, fuel=0)
    ship = _ship(port="PORT-B")                          # empty, sitting at the POORER port
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump_a, dump_b))
    orders = coastal_shipping_doctrine(s, Side.AXIS)
    assert len(orders) == 1
    o = orders[0]
    assert o.ship_id == ship.id and o.to == "PORT-A" and o.load is None


def test_doctrine_stands_by_when_nothing_to_relieve():
    a, b = _ports()
    dump_a = _dump("D-A", a.hex, fuel=100)
    dump_b = _dump("D-B", b.hex, fuel=100)                # already even
    ship = _ship(port="PORT-A")
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump_a, dump_b))
    assert coastal_shipping_doctrine(s, Side.AXIS) == []


def test_doctrine_does_not_target_a_port_of_the_wrong_side():
    # PORT-Matruh-style: an Allied-owned harbour must never be a shuttle candidate, even if a
    # transient unit presence flips state.control_of(its hex) to AXIS for one Phase (the bug this
    # doctrine used to have -- see coastal_shipping_doctrine's own docstring).
    a = _port("PORT-A", (0, 0), side=Side.AXIS)
    matruh = _port("PORT-Matruh", (6, 0), side=Side.ALLIED)
    dump_a = _dump("D-A", a.hex, fuel=8000)
    ship = _ship(port="PORT-A")
    s = _state(ships=(ship,), ports=(a, matruh), supplies=(dump_a,))
    s = replace(s, control={matruh.hex: Control.AXIS})    # the transient flip
    assert coastal_shipping_doctrine(s, Side.AXIS) == []  # only ONE Axis-side port -> no pair to shuttle


# --- CampaignAxisPolicy wiring + a live short campaign slice --------------------------------------

def test_campaign_axis_policy_exposes_the_doctrine():
    pol = CampaignAxisPolicy()
    a, b = _ports()
    dump_a = _dump("D-A", a.hex, fuel=8000)
    dump_b = _dump("D-B", b.hex, fuel=0)
    ship = _ship(port="PORT-A")
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump_a, dump_b))
    assert pol.coastal_shipping_orders(s, Side.AXIS) == coastal_shipping_doctrine(s, Side.AXIS)


def test_base_policy_ships_nothing():
    assert Policy().coastal_shipping_orders(_state(), Side.AXIS) == []


def test_short_campaign_moves_real_cargo_and_stays_invariant_clean():
    s = campaign(seed=1941, max_turns=10)
    res = run(s, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    invariants.check(res.final)
    unloaded = [e for e in res.events if e.kind == EventKind.COASTAL_SHIP_UNLOADED]
    assert len(unloaded) > 0                              # the shuttle actually delivers something
    for sh in res.final.ships:
        assert sh.side == Side.AXIS
        assert sh.port in {p.id for p in res.final.ports}  # never stranded off the known ports


# --- determinism / byte-identity for the ship-less benchmarks ------------------------------------

def test_benchmarks_stay_silent_and_byte_identical():
    for scen in (rommels_arrival(seed=1941), siege_of_tobruk(seed=1941)):
        a = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        b = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert determinism_signature(a.events) == determinism_signature(b.events)
        assert not any(e.kind.value.startswith("COASTAL_SHIP") for e in a.events)


def test_campaign_coastal_shipping_is_deterministic():
    a = campaign(seed=1941, max_turns=8)
    b = campaign(seed=1941, max_turns=8)
    ra = run(a, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    rb = run(b, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert determinism_signature(ra.events) == determinism_signature(rb.events)
