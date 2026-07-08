"""Truck-convoy haulage machinery (rules 48 V.J / 53 / 54.2; CHUNK 4, dormant).

The unattached 2nd/3rd-line truck convoys are the inland DISTRIBUTION layer: they
LOAD supply at a rear dump, MOVE up to the 53.22 extended convoy CPA burning their
OWN cargo fuel (49.18), and UNLOAD into a forward dump. The three events fold PURELY
-- TRUCK_LOADED / TRUCK_UNLOADED are conserving dump<->truck transfers, TRUCK_MOVED
burns cargo fuel like a consume -- so invariants.check gains exactly ONE surface: it
sums truck cargo alongside the dumps. The machinery lands seeded NOWHERE, so every
existing scenario stays byte-identical (state.trucks defaults to ()). These tests pin
the dataclass, the 54.2 chart accessor, the 53.12 load-admissibility rule, the three
folds' conservation, a full load->move->unload relay through the V.J phase, and the
byte-identity of truck-less scenarios."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import logistics_data, supply
from game.apply import apply
from game.engine import _truck_convoys, _Run, determinism_signature, run
from game.events import Event, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap
from game.policy import Policy, ScriptedPolicy, TruckOrder
from game.scenario import coastal_corridor, rommels_arrival
from game.state import GameState, SupplyUnit, TruckFormation, VP
from game.terrain import Terrain


def _state(supplies, trucks, terrain, *, turn: int = 1) -> GameState:
    """A mini state whose initial_supply counts BOTH dumps and truck cargo (the truck
    machinery's single new conservation surface)."""
    def total(c):
        attr = c.lower()
        return (sum(getattr(s, attr) for s in supplies)
                + sum(getattr(t, attr) for t in trucks))
    return GameState(
        turn=turn, max_turns=4, phase=Phase.LOGISTICS, active_side=Side.SYSTEM,
        seed=1, weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terrain, fortifications={}),
        control={}, units=(), target_hex=(0, 0), supplies=tuple(supplies),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: total(c) for c in supply.COMMODITIES},
        trucks=tuple(trucks))


class _TruckPolicy(Policy):
    """A scripted policy that issues a fixed list of truck orders (and nothing else)."""

    def __init__(self, orders):
        self._orders = orders

    def movement(self, state, side):
        return []

    def combat(self, state, side):
        return []

    def truck_orders(self, state, side):
        return list(self._orders)


# --- the dataclass + state field ---------------------------------------------

def test_trucks_default_empty():
    assert GameState.__dataclass_fields__["trucks"].default == ()
    assert coastal_corridor().trucks == ()     # toy corridor stays truck-less (dormant)


def test_rommels_arrival_seeds_the_axis_truck_pool():
    # Step 5 activation: Rommel's Arrival now fields the representative Axis 2nd/3rd-line
    # motor-transport pool at the rear supply port (where PORT-Tripoli lands its convoys).
    trucks = rommels_arrival().trucks
    assert {t.id for t in trucks} == {"AX-Truck-H", "AX-Truck-M"}
    assert all(t.side == Side.AXIS for t in trucks)
    assert {t.truck_class for t in trucks} == {"heavy", "medium"}


def test_truck_formation_defaults():
    t = TruckFormation("T", Side.AXIS, (2, 3), "medium", points=5)
    assert t.line == 2 and (t.ammo, t.fuel, t.stores, t.water) == (0, 0, 0, 0)


def test_truck_lookups_and_with_truck():
    t = TruckFormation("T", Side.AXIS, (2, 3), "heavy", points=3, fuel=10)
    s = _state([], [t], {(2, 3): Terrain.CLEAR})
    assert s.truck("T") is t and s.truck("nope") is None
    assert s.trucks_at((2, 3)) == (t,) and s.trucks_at((9, 9)) == ()
    s2 = s.with_truck(replace(t, fuel=20))
    assert s2.truck("T").fuel == 20 and s.truck("T").fuel == 10   # immutable


# --- 54.2 Truck Characteristics accessor -------------------------------------

def test_truck_characteristics_source_the_verified_chart():
    chars = logistics_data.truck_characteristics()
    assert chars["light"]["capacity"] == {"AMMO": 2, "FUEL": 50, "STORES": 6, "WATER": 40}
    assert chars["medium"]["capacity"] == {"AMMO": 4, "FUEL": 120, "STORES": 15, "WATER": 100}
    assert chars["heavy"]["capacity"] == {"AMMO": 8, "FUEL": 250, "STORES": 30, "WATER": 200}
    assert chars["light"]["convoy_cpa"] == 40                  # 53.22 extended
    assert chars["medium"]["convoy_cpa"] == chars["heavy"]["convoy_cpa"] == 30
    assert (chars["light"]["fuel_capacity"], chars["medium"]["fuel_capacity"]) == (8, 6)
    assert all(chars[c]["fuel_factor"] == 1 for c in ("light", "medium", "heavy"))


# --- 53.12 load admissibility -------------------------------------------------

def test_load_admissible_fractional_capacity_53_12():
    # A 5-point MEDIUM formation (fuel cap 120/pt): 600 fuel exactly fills 5 points.
    t = TruckFormation("T", Side.AXIS, (0, 0), "medium", points=5)
    assert supply.truck_load_admissible(t, {"FUEL": 600})
    assert not supply.truck_load_admissible(t, {"FUEL": 601})
    # A fractional MIX: 300 fuel (2.5 pts) + 30 stores (2 pts) = 4.5 <= 5.
    assert supply.truck_load_admissible(t, {"FUEL": 300, "STORES": 30})
    assert not supply.truck_load_admissible(t, {"FUEL": 300, "STORES": 45})   # 2.5 + 3 = 5.5
    # Admissibility is on the cargo AFTER loading -- an already-laden truck has less room.
    laden = replace(t, fuel=600)
    assert not supply.truck_load_admissible(laden, {"AMMO": 1})


def test_truck_move_fuel_49_13():
    # 49.13/49.18: factor(1) x ceil(CP/5) x Truck Points, from the truck's OWN cargo.
    t = TruckFormation("T", Side.AXIS, (0, 0), "medium", points=5)
    assert supply.truck_move_fuel(t, 30) == 30                 # 1 x 6 x 5
    assert supply.truck_move_fuel(t, 1) == 5                   # 1 x 1 x 5
    assert supply.truck_move_fuel(t, 0) == 0                   # did not move -> free


# --- the three folds conserve ------------------------------------------------

def _terr(*coords):
    from game.terrain import Terrain
    return {c: Terrain.CLEAR for c in coords}


def _conserved(state) -> bool:
    for c in supply.COMMODITIES:
        attr = c.lower()
        on_hand = (sum(getattr(s, attr) for s in state.supplies)
                   + sum(getattr(t, attr) for t in state.trucks))
        if on_hand + state.consumed[c] != state.initial_supply[c]:
            return False
    return True


def test_truck_loaded_is_a_conserving_transfer():
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=1000)
    truck = TruckFormation("T", Side.AXIS, (0, 0), "medium", points=5)
    s = _state([dump], [truck], _terr((0, 0)))
    e = Event(0, 1, Phase.LOGISTICS, Side.AXIS, "AXIS/Logistics", EventKind.TRUCK_LOADED,
              {"truck_id": "T", "supply_id": "D", "cargo": {"FUEL": 300}})
    s2 = apply(s, e)
    assert s2.supply("D").fuel == 700 and s2.truck("T").fuel == 300
    assert s2.initial_supply["FUEL"] == 1000 and s2.consumed["FUEL"] == 0
    check(s2); assert_conserved(s2)


def assert_conserved(state):
    assert _conserved(state)


def test_truck_unloaded_is_the_dual():
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0)
    truck = TruckFormation("T", Side.AXIS, (0, 0), "medium", points=5, fuel=300)
    s = _state([dump], [truck], _terr((0, 0)))
    e = Event(0, 1, Phase.LOGISTICS, Side.AXIS, "AXIS/Logistics", EventKind.TRUCK_UNLOADED,
              {"truck_id": "T", "supply_id": "D", "cargo": {"FUEL": 300}})
    s2 = apply(s, e)
    assert s2.supply("D").fuel == 300 and s2.truck("T").fuel == 0
    check(s2); assert_conserved(s2)


def test_truck_moved_burns_its_own_cargo_fuel():
    truck = TruckFormation("T", Side.AXIS, (0, 0), "medium", points=5, fuel=300)
    s = _state([], [truck], _terr((0, 0), (1, 0)))
    e = Event(0, 1, Phase.LOGISTICS, Side.AXIS, "AXIS/Logistics", EventKind.TRUCK_MOVED,
              {"truck_id": "T", "from": [0, 0], "to": [1, 0], "cp_spent": 30, "fuel": 30})
    s2 = apply(s, e)
    assert s2.truck("T").hex == (1, 0) and s2.truck("T").fuel == 270   # 49.18 own cargo
    assert s2.consumed["FUEL"] == 30                                   # left the system
    check(s2); assert_conserved(s2)


# --- the V.J phase: a full load -> move -> unload relay -----------------------

def test_full_relay_through_the_vj_phase_conserves():
    rear = SupplyUnit("REAR", Side.AXIS, (0, 0), ammo=0, fuel=1000)
    fwd = SupplyUnit("FWD", Side.AXIS, (1, 0), ammo=0, fuel=0)
    truck = TruckFormation("T", Side.AXIS, (0, 0), "medium", points=5)
    s = _state([rear, fwd], [truck], _terr((0, 0), (1, 0)))
    r = _Run(s)
    reach = supply.reachable_truck_moves(s, truck)
    burn = supply.truck_move_fuel(truck, reach[(1, 0)])
    order = TruckOrder("T", load_from="REAR", load={"FUEL": 600},
                       to=(1, 0), unload_to="FWD", unload={"FUEL": 600})
    _truck_convoys(r, _TruckPolicy([order]), Side.AXIS)
    kinds = [e.kind for e in r.events]
    assert EventKind.TRUCK_LOADED in kinds
    assert EventKind.TRUCK_MOVED in kinds
    assert EventKind.TRUCK_UNLOADED in kinds
    fs = r.state
    assert fs.truck("T").hex == (1, 0)
    # 600 loaded, `burn` spent moving, the rest deposited forward.
    assert fs.supply("REAR").fuel == 400
    assert fs.supply("FWD").fuel == 600 - burn
    assert fs.truck("T").fuel == 0
    assert fs.consumed["FUEL"] == burn
    check(fs); assert_conserved(fs)


def test_vj_phase_emits_no_events_when_side_has_no_trucks():
    # Dormant guard: a side with no formations does nothing (no Phase.LOGISTICS, no orders).
    rear = SupplyUnit("REAR", Side.AXIS, (0, 0), ammo=0, fuel=1000)
    truck = TruckFormation("T", Side.ALLIED, (0, 0), "medium", points=5)  # wrong side
    s = _state([rear], [truck], _terr((0, 0)))
    r = _Run(s)
    _truck_convoys(r, _TruckPolicy([TruckOrder("T", to=(1, 0))]), Side.AXIS)
    assert r.events == []


# --- rejections at the engine boundary ---------------------------------------

def _first_rejection(orders):
    truck = TruckFormation("T", Side.AXIS, (0, 0), "medium", points=5, fuel=300)
    rear = SupplyUnit("REAR", Side.AXIS, (0, 0), ammo=0, fuel=1000)
    fwd = SupplyUnit("FWD", Side.AXIS, (1, 0), ammo=0, fuel=0)
    s = _state([rear, fwd], [truck], _terr((0, 0), (1, 0)))
    r = _Run(s)
    _truck_convoys(r, _TruckPolicy(orders), Side.AXIS)
    rej = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    return rej[0].payload["reason"] if rej else None


def test_reject_load_over_capacity():
    assert "capacity" in _first_rejection([TruckOrder("T", load_from="REAR", load={"FUEL": 601})])


def test_reject_load_dump_short():
    r = _first_rejection([TruckOrder("T", load_from="REAR", load={"AMMO": 5})])   # dump has 0 ammo
    assert "lacks" in r


def test_reject_load_unknown_commodity():
    # A live QM/Convoy seat naming a bogus commodity must be rejected, not crash the run
    # on getattr(dump, <bad>.lower()) (findings #9a).
    r = _first_rejection([TruckOrder("T", load_from="REAR", load={"PETROL": 5})])
    assert "unknown commodity" in r


def test_reject_unknown_truck():
    assert "no such truck" in _first_rejection([TruckOrder("GHOST", to=(1, 0))])


def test_reject_move_already_moved():
    # Two move legs for the same formation: the first moves, the second is refused
    # (53.21 -- a formation relocates at most once per Truck Convoy Phase).
    truck = TruckFormation("T", Side.AXIS, (0, 0), "medium", points=5, fuel=300)
    rear = SupplyUnit("REAR", Side.AXIS, (0, 0), ammo=0, fuel=1000)
    fwd = SupplyUnit("FWD", Side.AXIS, (1, 0), ammo=0, fuel=0)
    s = _state([rear, fwd], [truck], _terr((0, 0), (1, 0)))
    r = _Run(s)
    _truck_convoys(r, _TruckPolicy([TruckOrder("T", to=(1, 0)),
                                    TruckOrder("T", to=(0, 0))]), Side.AXIS)
    reasons = [e.payload["reason"] for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert any("already moved" in x for x in reasons)


# --- byte-identity: no trucks => every existing scenario unchanged ------------

def test_truckless_scenario_byte_identical():
    a = run(coastal_corridor(seed=7), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(coastal_corridor(seed=7), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    truck_kinds = {EventKind.TRUCK_LOADED, EventKind.TRUCK_MOVED, EventKind.TRUCK_UNLOADED}
    assert not any(e.kind in truck_kinds for e in a.events)


def test_rommels_arrival_runs_the_truck_relay():
    # Step 5 activation: with the Axis pool seeded, the V.J phase now fires -- the trucks
    # load at the rear supply port and haul fuel forward through the load/move/unload triple.
    res = run(rommels_arrival(seed=3), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    truck_kinds = {EventKind.TRUCK_LOADED, EventKind.TRUCK_MOVED, EventKind.TRUCK_UNLOADED}
    assert all(any(e.kind == k for e in res.events) for k in truck_kinds)
    # every hauled Fuel Point is deposited into a friendly dump strictly forward of the port
    from game.hexmap import distance
    rear = max((s for s in res.final.supplies if s.side == Side.AXIS),
               key=lambda s: distance(s.hex, res.final.target_hex))
    delivered = [e for e in res.events if e.kind == EventKind.TRUCK_UNLOADED]
    assert delivered and all(e.payload["cargo"].get("FUEL", 0) > 0 for e in delivered)
    for e in delivered:
        dump = res.final.supply(e.payload["supply_id"])
        assert distance(dump.hex, res.final.target_hex) < distance(rear.hex, res.final.target_hex)


# --- ScriptedPolicy.truck_orders sizes the load under residual cargo ------------

def test_truck_orders_size_load_under_residual_cargo():
    """A truck that returns to base with RESERVE fuel still in its tank must not be
    reloaded past its 53.12 capacity: the fresh load is sized against the residual so
    ScriptedPolicy.truck_orders never emits an over-capacity load (the 68 'load exceeds
    truck capacity' rejects). Heavy truck (points 8), 200 residual fuel: the naive half-
    capacity load (1000 FUEL) plus the residual overruns the 8-Point ceiling."""
    from game.state import Port
    target = (5, 0)
    terr = _terr(*[(q, 0) for q in range(6)])
    port = Port("PORT", Side.AXIS, (0, 0), kind="major", max_eff=10, eff=10,
                cap_ammo=9999, cap_fuel=9999, cap_stores=9999, cap_water=9999, cap_tons=9999)
    base = SupplyUnit("BASE", Side.AXIS, (0, 0), ammo=200, fuel=2000)
    fwd = SupplyUnit("FWD", Side.AXIS, (1, 0), ammo=0, fuel=0)
    truck = TruckFormation("T", Side.AXIS, (0, 0), "heavy", points=8, fuel=200)
    s = replace(_state([base, fwd], [truck], terr), ports=(port,), target_hex=target)

    orders = ScriptedPolicy(attacker=Side.AXIS).truck_orders(s, Side.AXIS)
    assert orders and orders[0].load is not None, "the truck should propose a forward run"
    assert supply.truck_load_admissible(s.truck("T"), orders[0].load), \
        f"load {orders[0].load} exceeds capacity given residual fuel {truck.fuel}"
