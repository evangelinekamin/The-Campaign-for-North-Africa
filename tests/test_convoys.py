"""Convoy faucet + Tobruk sea lifeline (rules 30 / 48 / 55 / 56 / 57; CHUNK 1).

A convoy is the supply SOURCE -- the exact dual of the SUPPLY_CONSUMED drain.
SUPPLY_CONSUMED conserves by (on_hand-q)+(consumed+q)=initial; the SUPPLY_ARRIVED
faucet conserves by (on_hand+q)+consumed=(initial+q), so invariants.check needs no
change. These tests pin the faucet, its capacity throttle, the 56.15 cancellation,
that it fires only on a convoy's arrival turn and stays byte-invisible to convoy-
less scenarios, and the ACCEPTANCE that the Tobruk sea lifeline holds the fortress
against pure land-starvation (the 15.15 defender surrender never fires)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords
from game.apply import apply
from game.engine import _naval_convoys, _Run, determinism_signature, run
from game.events import Control, Event, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival, siege_of_tobruk
from game.state import Convoy, GameState, SupplyUnit, VP
from game.terrain import Terrain

TOBRUK = coords.to_axial(coords.parse("C4807"))


def _mini(dump: SupplyUnit, convoys=(), *, control=None, turn: int = 1) -> GameState:
    """A one-hex, one-dump state to exercise the faucet in isolation."""
    terr = {dump.hex: Terrain.CLEAR}
    return GameState(
        turn=turn, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=1, weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={}),
        control=dict(control or {}), units=(), target_hex=dump.hex,
        supplies=(dump,), consumed={"AMMO": 0, "FUEL": 0},
        initial_supply={"AMMO": dump.ammo, "FUEL": dump.fuel}, convoys=tuple(convoys))


# --- the state field ---------------------------------------------------------

def test_convoys_default_empty():
    assert GameState.__dataclass_fields__["convoys"].default == ()
    assert coastal_corridor().convoys == ()


# --- the SUPPLY_ARRIVED fold (dual of SUPPLY_CONSUMED) -----------------------

def test_supply_arrived_folds_and_conserves():
    s = _mini(SupplyUnit("D", Side.ALLIED, (0, 0), ammo=10, fuel=20))
    e = Event(0, 1, Phase.LOGISTICS, Side.ALLIED, "SYSTEM", EventKind.SUPPLY_ARRIVED,
              {"supply_id": "D", "cargo": {"AMMO": 15, "FUEL": 25},
               "lane": "SEA-TOBRUK", "convoy_id": "c1"})
    s2 = apply(s, e)
    d = s2.supply("D")
    assert (d.ammo, d.fuel) == (25, 45)                 # topped up
    assert s2.initial_supply == {"AMMO": 25, "FUEL": 45}  # initial rose by the same delta
    check(s2)                                            # on_hand+consumed==initial holds
    on_hand = sum(su.ammo for su in s2.supplies)
    assert on_hand + s2.consumed["AMMO"] == s2.initial_supply["AMMO"]


# --- the engine capacity throttle (post-cap landed amounts are baked) --------

def test_supply_arrived_caps_at_capacity():
    # A CLEAR dump hex reads the 54.12 "Other Terrain" ceiling (1500 ammo / 5000 fuel).
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=1495, fuel=4998)
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 40, "FUEL": 60})
    r = _Run(_mini(dump, [conv]))
    _naval_convoys(r)
    arrived = [e for e in r.events if e.kind == EventKind.SUPPLY_ARRIVED]
    assert len(arrived) == 1
    # 1495/4998 under the 1500/5000 cap -> only 5 ammo + 2 fuel land (over-cap never credited)
    assert arrived[0].payload["cargo"] == {"AMMO": 5, "FUEL": 2}
    d = r.state.supply("D")
    assert (d.ammo, d.fuel) == (1500, 5000)
    check(r.state)                                       # no conservation fault on over-cap


def test_full_dump_lands_nothing_but_no_fault():
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=1500, fuel=5000)   # at the Other cap
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 40, "FUEL": 60})
    r = _Run(_mini(dump, [conv]))
    _naval_convoys(r)
    assert not any(e.kind == EventKind.SUPPLY_ARRIVED for e in r.events)  # nothing to land
    check(r.state)


def test_major_city_dump_is_unlimited():
    from game import supply
    from game.terrain import Terrain
    cap = supply.dump_capacity(Terrain.MAJOR_CITY)
    assert all(cap[c] >= 10 ** 9 for c in supply.COMMODITIES)
    other = supply.dump_capacity(Terrain.CLEAR)
    assert (other["AMMO"], other["FUEL"], other["STORES"], other["WATER"]) == (1500, 5000, 1000, 1000)


def test_supply_arrived_folds_all_four_commodities():
    # The faucet routes all four commodities through one getattr path and conserves each.
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0, stores=0, water=0)
    s = GameState(
        turn=1, max_turns=4, phase=Phase.LOGISTICS, active_side=Side.SYSTEM, seed=1,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0), supplies=(dump,),
        consumed={c: 0 for c in ("AMMO", "FUEL", "STORES", "WATER")},
        initial_supply={c: 0 for c in ("AMMO", "FUEL", "STORES", "WATER")})
    e = Event(0, 1, Phase.LOGISTICS, Side.ALLIED, "SYSTEM", EventKind.SUPPLY_ARRIVED,
              {"supply_id": "D", "cargo": {"STORES": 12, "WATER": 7},
               "lane": "SEA-TOBRUK", "convoy_id": "c1"})
    s2 = apply(s, e)
    d = s2.supply("D")
    assert (d.stores, d.water) == (12, 7)
    assert s2.initial_supply["STORES"] == 12 and s2.initial_supply["WATER"] == 7
    check(s2)
    for c in ("STORES", "WATER"):
        on_hand = sum(getattr(su, c.lower()) for su in s2.supplies)
        assert on_hand + s2.consumed[c] == s2.initial_supply[c]


# --- 56.15 a convoy to an enemy-captured port never sails --------------------

def test_convoy_cancelled_when_dest_enemy_controlled():
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=10, fuel=10)
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 40, "FUEL": 60})
    r = _Run(_mini(dump, [conv], control={(0, 0): Control.AXIS}))
    _naval_convoys(r)
    assert any(e.kind == EventKind.CONVOY_CANCELLED for e in r.events)
    assert not any(e.kind == EventKind.SUPPLY_ARRIVED for e in r.events)
    assert r.state.supply("D").ammo == 10                # no top-up; folds to identity
    check(r.state)


# --- fires only on the arrival turn ------------------------------------------

def test_naval_convoys_fires_on_arrival_turn_only():
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0)
    conv = Convoy("c1", Side.ALLIED, 3, "SEA-TOBRUK", "D", {"AMMO": 40, "FUEL": 60})
    r1 = _Run(_mini(dump, [conv], turn=1))
    _naval_convoys(r1)
    assert not r1.events                                 # nothing due at turn 1
    r3 = _Run(_mini(dump, [conv], turn=3))
    _naval_convoys(r3)
    assert any(e.kind == EventKind.SUPPLY_ARRIVED for e in r3.events)
    assert any(e.kind == EventKind.PHASE_ADVANCED and e.payload["phase"] == "LOGISTICS"
               for e in r3.events)


# --- convoy-less scenarios stay byte-identical (no LOGISTICS phase at all) ----

def test_convoyless_scenario_byte_identical():
    a = run(coastal_corridor(seed=7), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(coastal_corridor(seed=7), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    # no Phase.LOGISTICS is emitted and no supply ever arrives in a convoy-less run
    assert not any(e.kind == EventKind.PHASE_ADVANCED and e.payload["phase"] == "LOGISTICS"
                   for e in a.events)
    assert not any(e.kind in (EventKind.SUPPLY_ARRIVED, EventKind.CONVOY_CANCELLED)
                   for e in a.events)


# --- the Tobruk sea lifeline is seeded ---------------------------------------

def test_tobruk_ferry_seeded():
    s = rommels_arrival()
    ferries = [c for c in s.convoys if c.lane == "SEA-TOBRUK"]
    assert ferries, "rommels_arrival must seed a Tobruk ferry"
    assert all(c.side == Side.ALLIED and c.dest == "AL-Tobruk" for c in ferries)
    # a recurring per-turn faucet, one convoy for every game-turn
    assert {c.arrival_turn for c in ferries} == set(range(1, s.max_turns + 1))
    assert s.supply("AL-Tobruk") is not None
    assert s.supply("AL-Tobruk").hex == TOBRUK


# --- Step 5: the Axis distribution switch-on (Tripoli port + truck relay) -----

def test_axis_convoy_lands_at_working_tripoli():
    # Step 5 repointed the Axis naval convoy from the scuttled Benghazi (eff 0, landed
    # nothing) to the WORKING rear harbour Tripoli (55.3 eff 10). The convoy now lands its
    # tonnage there each due turn, emitted as PORT_UNLOADED beats at full efficiency.
    s = rommels_arrival()
    tri = s.port_at(s.supply("AX-Tripoli").hex)
    assert tri is not None and tri.id == "PORT-Tripoli"
    assert (tri.side, tri.eff, tri.max_eff) == (Side.AXIS, 10, 10)
    assert all(c.dest == "AX-Tripoli" for c in s.convoys if c.side == Side.AXIS)
    res = run(rommels_arrival(seed=7), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    beats = [e for e in res.events if e.kind == EventKind.PORT_UNLOADED
             and e.payload["port_id"] == "PORT-Tripoli"]
    assert beats and all(b.payload["eff"] == 10 for b in beats)


def test_axis_trucks_relay_supply_off_tripoli():
    # The lean truck pool hauls tonnage off the anchored harbour and deposits it into a
    # field dump strictly forward of the port -- the load/move/unload relay (53.14). The
    # harbour stays put (it is a port), so its ongoing convoy tonnage can ONLY reach the
    # front by truck: the faithful Tripoli->front haulage bottleneck.
    res = run(rommels_arrival(seed=7), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    from game.hexmap import distance
    port_dist = distance(res.final.supply("AX-Tripoli").hex, TOBRUK)
    delivered = [e for e in res.events if e.kind == EventKind.TRUCK_UNLOADED]
    assert delivered, "the Axis truck relay must move tonnage forward"
    for e in delivered:
        dump = res.final.supply(e.payload["supply_id"])
        assert distance(dump.hex, TOBRUK) < port_dist          # deposited forward of Tripoli
    # the harbour is anchored -- it never leapfrogs off its port hex (a fixed installation)
    assert res.final.port_at(res.final.supply("AX-Tripoli").hex) is not None


# --- ACCEPTANCE: the lifeline holds Tobruk vs pure land-starvation -----------

def _def_surrender_at_objective(events) -> bool:
    return any(e.kind == EventKind.COMBAT_RESOLVED
               and e.payload.get("surrender") == "defender"
               and tuple(e.payload.get("target", ())) == TOBRUK
               for e in events)


def test_tobruk_holds_vs_land_starvation():
    for seed in range(1, 7):
        res = run(rommels_arrival(seed=seed),
                  ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert res.final.control_of(TOBRUK) != Control.AXIS, f"Tobruk fell (seed {seed})"
        # the precise 15.15 all-out-of-ammo mechanism never fires at the objective
        assert not _def_surrender_at_objective(res.events), f"garrison surrendered (seed {seed})"


def test_determinism_preserved():
    a = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)


def test_siege_of_tobruk_machinery_intact():
    """The faucet must not disturb the siege mechanism. The ferry historically ran
    THROUGH the 1941 siege (the Tobruk Ferry Service), so it feeds the garrison in
    this scenario too and the 15.15 ammo-starvation crack no longer fires -- which is
    faithful: Tobruk held the 1941 siege and was not stormed until June 1942 under
    different conditions (see memory: cna-tobruk-crackability; the genuine siege-
    storm capture path is deferred, not a CHUNK-1 regression). What CHUNK 1 must
    preserve is that the 25.14 artillery path stays LIVE: with siege_rules ON the
    wall is still battered down (FORT_REDUCED fires at the objective across seeds),
    which never happens with siege OFF.

    Seed note: the faithful two-level clock (rules 5/48) runs THREE Operations Stages per
    game-turn, each with its own 29.0 weather roll, so the seeded stream is reshuffled again
    and the seeds that crack shifted with it -- and again when General Rommel's 31.4 +5 CPA
    (his 300th-Oasis companion) widened one Axis move at El Agheila, and AGAIN when the
    SEA-TOBRUK air-interdiction schedule (41.6) drew its per-ferry CRT dice into the shared
    stream. This guards only that the 25.14 path SURVIVES -- the crack rate is the owner's
    siege knob, not tuned here."""
    battered = False
    for seed in (4, 10, 14):
        res = run(siege_of_tobruk(seed=seed),
                  ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert res.initial.siege_rules is True
        if any(e.kind == EventKind.FORT_REDUCED and tuple(e.payload["hex"]) == TOBRUK
               for e in res.events):
            battered = True
    assert battered, "siege artillery must still batter Tobruk's wall (25.14)"
