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

from game import engine, invariants, logistics_data, supply
from game.apply import apply
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy, coastal_shipping_doctrine
from game.campaign_staff import CampaignStaffPolicy
from game.engine import _coastal_shipping, _Run, determinism_signature, run
from game.llm import MockClient
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


def test_water_is_shippable_cargo():
    # [56.34] bars PERSONNEL and "Tanks, guns, etc." and nothing else. Water is a supply (52.0,
    # 57.0), and this is a transfer between two AFRICAN ports -- not [56.22]'s run from Europe,
    # whose three-commodity list (fuel/ammunition/stores) is what the pre-repair code wrongly
    # applied here. The campaign DOCTRINE still never ships water (the Axis draws it from wells);
    # this asserts the RULE, which is a different thing.
    dump_a = _dump("D-A", (0, 0))
    dump_a = replace(dump_a, water=900)
    dump_b = _dump("D-B", (6, 0))
    ship = _ship()
    s = _state(ships=(ship,), supplies=(dump_a, dump_b))
    order = CoastalShipOrder(ship.id, load_from="D-A", load={"WATER": 600}, to="PORT-B")
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    assert not any(e.kind == EventKind.ORDER_REJECTED for e in r.events)
    assert r.state.supply("D-A").water == 300
    assert r.state.supply("D-B").water == 600


# --- [55.3]/[56.27] THE HARBOUR THROTTLE ---------------------------------------------------------
# The 55.3 chart legend: "Maximum Tonnage: The total tonnage of supplies that may be shipped in
# and/or out in one Operations Stage" -- ONE budget per port, BOTH directions, shared with the
# overseas convoy's own landings. 55.13 "may enter and leave that port"; 55.14 "brought into or out
# of"; 56.27 "they may not receive supplies over that capacity"; and 48 V.C.7's own note that
# coastal shipping "is limited only by the port capacities". The module's default _port carries
# 100,000 t so the older cases never meet it; these ports are sized so it binds.

def _tight_ports(dist=6, *, tons_a=100, tons_b=100_000):
    a = replace(_port("PORT-A", (0, 0)), cap_tons=tons_a)
    b = replace(_port("PORT-B", (dist, 0)), cap_tons=tons_b)
    return a, b


def test_load_is_trimmed_to_the_ports_remaining_tonnage():
    # PORT-A ships 100 t per OpStage; 54.5 makes a Fuel Point 1/8 t, so 800 Points is the whole
    # budget however much the order asks for. 56.27 forbids shipping OVER capacity -- shipping UP
    # to it is legal, so the load is trimmed, not cancelled (the same treatment _naval_convoys
    # gives this rule at the landing edge).
    a, b = _tight_ports()
    dump = _dump("D", (0, 0), fuel=100_000)
    ship = _ship(tons=100_000)                        # hull is not the binding limit here
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump,))
    order = CoastalShipOrder(ship.id, load_from="D", load={"FUEL": 8000})
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([order]), Side.AXIS)
    loaded = [e for e in r.events if e.kind == EventKind.COASTAL_SHIP_LOADED]
    assert len(loaded) == 1 and loaded[0].payload["cargo"] == {"FUEL": 800}
    assert r.state.ship(ship.id).fuel == 800
    assert engine._port_tons(r)["PORT-A"] == 100.0     # read through the ledger's one accessor


def test_second_ship_finds_the_ports_tonnage_spent_this_operations_stage():
    a, b = _tight_ports()
    dump = _dump("D", (0, 0), fuel=100_000)
    one, two = _ship("AX-Ship-A", tons=100_000), _ship("AX-Ship-B", tons=100_000)
    s = _state(ships=(one, two), ports=(a, b), supplies=(dump,))
    orders = [CoastalShipOrder("AX-Ship-A", load_from="D", load={"FUEL": 800}),
              CoastalShipOrder("AX-Ship-B", load_from="D", load={"FUEL": 800})]
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy(orders), Side.AXIS)
    assert r.state.ship("AX-Ship-A").fuel == 800
    assert r.state.ship("AX-Ship-B").fuel == 0
    rejects = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert any("tonnage capacity for this Operations Stage is spent" in e.payload["reason"]
               for e in rejects)


def test_the_convoy_and_the_fleet_share_one_tonnage_budget():
    # The ledger _naval_convoys bills its landings to is the SAME dict -- so a quay the overseas
    # convoy has already filled this OpStage has nothing left for a coastal load (55.16: "a port's
    # capacity applies to ALL shipments received in a Game-Turn (including OpStages)").
    a, b = _tight_ports()
    dump = _dump("D", (0, 0), fuel=100_000)
    ship = _ship(tons=100_000)
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump,))
    r = _Run(s)
    # Seeded THROUGH engine._port_tons, the ledger's one accessor -- it is keyed on (turn, stage)
    # and expires itself, so a raw write to the dict is discarded the moment the stage is read.
    engine._port_tons(r)["PORT-A"] = 100.0            # as if the convoy had landed the lot
    _coastal_shipping(r, _StubPolicy([CoastalShipOrder(ship.id, load_from="D",
                                                       load={"FUEL": 800})]), Side.AXIS)
    assert r.state.ship(ship.id).fuel == 0
    assert any("tonnage capacity" in e.payload["reason"]
               for e in r.events if e.kind == EventKind.ORDER_REJECTED)


def test_unload_is_partial_when_the_receiving_port_is_nearly_full_and_finishes_next_stage():
    # 56.27's own words are about RECEIVING. The remainder stays aboard and lands next Operations
    # Stage, exactly like a truck's partial unload against a 54.12 ceiling.
    a, b = _tight_ports(tons_a=100_000, tons_b=50)     # PORT-B takes 50 t = 400 Fuel Points
    dump_b = _dump("D-B", (6, 0))
    ship = _ship(port="PORT-B", tons=100_000, fuel=800)
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump_b,))
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy(), Side.AXIS)
    assert r.state.supply("D-B").fuel == 400
    assert r.state.ship(ship.id).fuel == 400           # the rest is still aboard
    # The next Operations Stage opens a fresh budget -- and it opens it BY ITSELF. This line used
    # to wipe the ledger dict from outside, which asserted the remainder lands given an empty
    # budget and said nothing about what empties it; the stage boundary is the thing under test, so
    # move the clock and let engine._OpStageLedger's (turn, stage) stamp do the emptying.
    r.emit(EventKind.STAGE_ADVANCED, Side.SYSTEM, "SYSTEM", {"stage": 2})
    _coastal_shipping(r, _StubPolicy(), Side.AXIS)
    assert r.state.supply("D-B").fuel == 800
    assert r.state.ship(ship.id).fuel == 0


def test_no_operations_stage_ever_ships_a_campaign_port_over_its_capacity():
    # THE REGRESSION GUARD for the repair. Pre-repair this campaign drove 4,000 t of coastal cargo
    # through Tobruk's 1,700 t quay in a single Operations Stage. Asserted against cap_tons (the
    # port at FULL efficiency) rather than the live eff-scaled budget, because a port can be bombed
    # part-way through a stage and the tonnage already shipped at the higher Level is not undone.
    s = campaign(seed=1941, max_turns=10)
    res = run(s, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    caps = {p.id: p.cap_tons for p in s.ports}
    where = {sh.id: sh.port for sh in s.ships}
    stage, tons = 0, {}
    for e in res.events:
        k = e.kind
        if k in (EventKind.TURN_ADVANCED, EventKind.STAGE_ADVANCED):
            stage, tons = stage + 1, {}
        elif k == EventKind.PORT_UNLOADED:
            pid, p = e.payload["port_id"], e.payload
            tons[pid] = tons.get(pid, 0.0) + p["qty"] * supply.TONS_PER_POINT[p["commodity"]]
        elif k == EventKind.COASTAL_SHIP_SAILED and e.payload["arrived"]:
            where[e.payload["ship_id"]] = e.payload["dest"]
        elif k == EventKind.COASTAL_SHIP_RECALLED:
            where[e.payload["ship_id"]] = e.payload["port"]
        elif k in (EventKind.COASTAL_SHIP_LOADED, EventKind.COASTAL_SHIP_UNLOADED):
            pid = where[e.payload["ship_id"]]
            tons[pid] = tons.get(pid, 0.0) + sum(q * supply.TONS_PER_POINT[c]
                                                 for c, q in e.payload["cargo"].items())
        for pid, t in tons.items():
            assert t <= caps[pid] + 1e-6, (
                f"stage {stage}: {pid} shipped {t:.1f} t over its {caps[pid]} t capacity (55.3)")


# --- [56.34] THE ORDERING: coastal shipping loads at the BEGINNING of the Truck Convoy Phase ------

def test_coastal_shipping_runs_ahead_of_the_lorries_in_the_truck_convoy_phase(monkeypatch):
    # [56.34]: the Axis Player "loads supplies ... at the beginning of the Truck Convoy Phase". The
    # book's own Sequence of Play puts it earlier still (48 V.C.7's Tactical Shipping Segment sits
    # in the Organization Phase, ahead of movement and of V.J's lorries) -- see the transcription's
    # owner-ruling flag on that tension. Under EVERY reading the ships load before the trucks roll,
    # and the pre-repair engine ran them last, which handed the lorries first pick of the quay.
    # Patching the module GLOBALS engine.run resolves at call time (the pattern tests/baselines.py
    # records as the one that actually reaches the caller's reference).
    calls: list[str] = []
    monkeypatch.setattr(engine, "_coastal_shipping", lambda *a, **k: calls.append("ships"))
    monkeypatch.setattr(engine, "_truck_convoys", lambda *a, **k: calls.append("trucks"))
    run(campaign(seed=1941, max_turns=1), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert calls and len(calls) % 2 == 0
    assert calls == ["ships", "trucks"] * (len(calls) // 2)


# --- [56.33]/[56.15] A DESTINATION LOST UNDER A SHIP AT SEA --------------------------------------

def test_a_ship_whose_destination_falls_puts_about_and_comes_home_with_its_cargo():
    # Pre-repair this ship loitered at sea for the rest of the war and its cargo left the game.
    # The book has no at-sea state to rule on (in 56.35 a voyage completes inside one Phase when
    # the CPA covers it); the closest thing it prints is 56.15, which CANCELS a sailing whose
    # destination the Commonwealth has taken. Flagged as a judgement call in the transcription.
    dump_a = _dump("D-A", (0, 0))
    ship = _ship(dest="PORT-B", progress=20, fuel=300)      # 20 of 60 sea hexes covered
    a, b = _ports(dist=60)
    s = _state(ships=(ship,), ports=(a, b), supplies=(dump_a,), dist=60)
    s = replace(s, control={b.hex: Control.ALLIED})         # 56.33: the destination is now enemy-held
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy(), Side.AXIS)
    recalled = [e for e in r.events if e.kind == EventKind.COASTAL_SHIP_RECALLED]
    assert len(recalled) == 1
    # RESTATED (rule 5), because the original arithmetic here was wrong, not the engine: it put
    # about only 20 sea hexes out, so the passage home costs 20 of this Phase's 50 CPA (56.31, one
    # point per sea hex) and leaves 30 -- the automatic 56.34 unload needs 5, so it DOES fit, and
    # the ship is home AND discharged inside this same Phase. That is exactly how _ship_continue
    # already treats an ordinary arrival with CPA to spare; a recall is not a special case.
    home = r.state.ship(ship.id)
    assert home.port == "PORT-A" and home.dest is None and home.progress == 0
    # What the test is really for: the cargo never leaves the game. Pre-repair the ship loitered
    # at sea forever and these 300 points were gone for good.
    assert r.state.supply("D-A").fuel == 300
    assert home.fuel == 0 and home.fuel + r.state.supply("D-A").fuel == 300


def test_a_ship_recalled_over_a_long_passage_takes_more_than_one_phase_to_get_home():
    # The put-about is NOT a teleport: it pays the sea hexes back at 56.31's one point per hex.
    a, b = _port("PORT-A", (0, 0)), _port("PORT-B", (200, 0))
    ship = _ship(dest="PORT-B", progress=120, fuel=300)
    s = _state(ships=(ship,), ports=(a, b))
    s = replace(s, control={b.hex: Control.ALLIED})
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy(), Side.AXIS)
    mid = r.state.ship(ship.id)
    assert mid.port == "PORT-B" and mid.dest == "PORT-A"    # heading the other way now
    assert mid.progress == (200 - 120) + 50                 # 80 already back down the chord, +50 CPA
    _coastal_shipping(r, _StubPolicy(), Side.AXIS)
    assert r.state.ship(ship.id).progress == 180
    _coastal_shipping(r, _StubPolicy(), Side.AXIS)
    home = r.state.ship(ship.id)
    assert home.port == "PORT-A" and home.dest is None and home.fuel == 300


def test_a_ship_with_both_ends_shut_holds_station():
    # 56.33 shuts the destination AND the port it sailed from: there is nowhere to put about to,
    # so the literal reading stands and the ship holds where it is. No event, nothing lost.
    a, b = _ports(dist=60)
    a = replace(a, eff=0)
    ship = _ship(dest="PORT-B", progress=20, fuel=300)
    s = _state(ships=(ship,), ports=(a, b), dist=60)
    s = replace(s, control={b.hex: Control.ALLIED})
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy(), Side.AXIS)
    assert [e for e in r.events if e.kind != EventKind.PHASE_ADVANCED] == []
    assert r.state.ship(ship.id) == ship


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


def test_the_live_campaign_staff_sails_the_same_fleet_as_its_scripted_twin():
    # The watchable-campaign path and its scripted twin must not diverge on a rule the port has
    # built (the reason CampaignStaffPolicy already carries malta_raid / convoy_plan / truck_orders).
    # CampaignStaffPolicy is (_CampaignAxisSupplyMixin, StaffPolicy), and NEITHER of those defines
    # coastal_shipping_orders -- so before the repair the MRO reached Policy's empty list and a live
    # staff left all four ships tied up at Benghazi for 111 turns.
    a, b = _ports()
    dump_a = _dump("D-A", a.hex, fuel=8000)
    dump_b = _dump("D-B", b.hex, fuel=0)
    s = _state(ships=(_ship(port="PORT-A"),), ports=(a, b), supplies=(dump_a, dump_b))
    staff = CampaignStaffPolicy(MockClient("{}"), side=Side.AXIS)
    orders = staff.coastal_shipping_orders(s, Side.AXIS)
    assert orders == coastal_shipping_doctrine(s, Side.AXIS) != []


def test_the_commonwealth_fields_no_countered_fleet():
    # 56.3 is titled AXIS Coastal Shipping, and 48 V.C.7 says outright: "Axis coastal ships are
    # represented in the game by counters. Allied coastal shipping is not represented by counters,
    # and is limited only by the port capacities" -- the Commonwealth's side of the idea lives in
    # its 57.0 supply-base abstraction, not in a fleet this subsystem could sail.
    ship = _ship(side=Side.ALLIED)
    dump = _dump("D", (0, 0), side=Side.ALLIED, fuel=1000)
    s = _state(ships=(ship,), supplies=(dump,))
    r = _Run(s)
    _coastal_shipping(r, _StubPolicy([CoastalShipOrder(ship.id, load_from="D",
                                                       load={"FUEL": 100}, to="PORT-B")]),
                      Side.ALLIED)
    assert r.events == []


# --- the magnitudes come from data, not from literals --------------------------------------------

def test_every_56_3_magnitude_is_read_from_data():
    from game import scenario
    from game.engine import (_SHIP_CPA_56_31, _SHIP_LOAD_CP_56_34, _SHIP_SEA_HEX_CP_56_31,
                             _SHIP_UNLOAD_CP_56_34)
    block = logistics_data.coastal_shipping_56_3()
    assert (_SHIP_CPA_56_31, _SHIP_SEA_HEX_CP_56_31, _SHIP_LOAD_CP_56_34, _SHIP_UNLOAD_CP_56_34) \
        == (block["cpa"], block["sea_hex_cost"], block["load_cp"], block["unload_cp"])
    assert (block["cpa"], block["sea_hex_cost"], block["load_cp"], block["unload_cp"]) == (50, 1, 5, 5)
    # And the roster -- the one number here the SCAN does not carry, so the data file holds its
    # provenance next to it rather than a bare literal sitting in scenario.py.
    assert scenario._COASTAL_SHIPS_56_31 == logistics_data.coastal_shipping_fleet_56_31()
    assert scenario._COASTAL_SHIPS_56_31 == (("A", 1000), ("B", 1000), ("C", 1000), ("D", 2000))
    assert "vmod" in block["fleet"]["_source"].lower()


def test_short_campaign_moves_real_cargo_and_stays_invariant_clean():
    s = campaign(seed=1941, max_turns=10)
    res = run(s, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    invariants.check(res.final)
    unloaded = [e for e in res.events if e.kind == EventKind.COASTAL_SHIP_UNLOADED]
    assert len(unloaded) > 0                              # the shuttle actually delivers something
    # RESTATED (port rule 5): the old "sh.port is a known port id" could not fail, because `port`
    # holds the voyage's ORIGIN while a ship is at sea and so stays a real port id even for a ship
    # stranded forever. What the repair actually guarantees is that no ship ends the war bound for
    # a port 56.33 will not let it enter -- the case that used to hold a laden ship, and its cargo,
    # out of the game for the rest of the campaign.
    for sh in res.final.ships:
        assert sh.side == Side.AXIS
        assert sh.port in {p.id for p in res.final.ports}
        if sh.dest is not None:
            dest = res.final.port(sh.dest)
            assert dest is not None and dest.eff > 0
            assert res.final.control_of(dest.hex) != Control.ALLIED


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
