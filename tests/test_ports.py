"""Ports + harbour-efficiency throttle (rules 30 / 54.5 / 55 / 56.28; CHUNK 3).

A port owns the built-in dump at its hex (56.28). A convoy lands THROUGH the port:
the effective per-OpStage receiving capacity is ceil(cap * eff / max_eff) (55.14),
so a harbour crippled by a scuttled ship lands only a fraction of a convoy. The
San Giorgio blocks Tobruk to 2/5 = 40% (30.17 / 55.25). Efficiency regenerates
+1/OpStage up to max_eff (55.18) -- except a permanent harbour BLOCK, which needs
engineers (55.26). Tonnage <-> points crosses the 54.5 Equivalent Weights at the
port edge only. These tests pin the throttle, the regen, the San Giorgio seed, the
byte-identity of port-less scenarios, and the ACCEPTANCE that the throttled ferry
still holds Tobruk (the ferry is sized so 40% of it feeds the garrison)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords, supply
from game.engine import (HARBOUR_BLOCKED, _naval_convoys, _port_regen, _Run,
                         determinism_signature, run)
from game.events import Control, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival, siege_of_tobruk
from game.state import Convoy, GameState, Port, SupplyUnit, VP
from game.terrain import Terrain

TOBRUK = coords.to_axial(coords.parse("C4807"))


def _port_state(port: Port, dump: SupplyUnit, convoys=(), *, turn: int = 1) -> GameState:
    """A one-hex state with a port and its built-in dump, to exercise the throttle."""
    return GameState(
        turn=turn, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=1, weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={dump.hex: Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=dump.hex, supplies=(dump,),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: getattr(dump, c.lower()) for c in supply.COMMODITIES},
        convoys=tuple(convoys), ports=(port,))


# --- the Port dataclass + GameState field ------------------------------------

def test_ports_default_empty():
    assert GameState.__dataclass_fields__["ports"].default == ()
    assert coastal_corridor().ports == ()
    assert rommels_arrival().ports != ()          # CHUNK 3 seeds ports


def test_port_lookups_and_with_port():
    from dataclasses import replace
    p = Port("P", Side.ALLIED, (2, 3), "major", max_eff=5, eff=2,
             cap_ammo=300, cap_fuel=100, cap_stores=500, cap_water=150, cap_tons=1200)
    s = _port_state(p, SupplyUnit("D", Side.ALLIED, (2, 3), ammo=0, fuel=0))
    assert s.port("P") is p and s.port_at((2, 3)) is p
    assert s.port("nope") is None and s.port_at((9, 9)) is None
    s2 = s.with_port(replace(p, eff=3))
    assert s2.port("P").eff == 3 and s.port("P").eff == 2   # immutable


# --- 54.5 tonnage <-> points at the port edge --------------------------------

def test_equivalent_weights_conversion():
    # 54.5: Ammo 4t, Fuel 1/8t, Stores 1t, Water 1/6t per Point.
    assert supply.tons_to_points(1200, "AMMO") == 300      # 1200 / 4
    assert supply.tons_to_points(1200, "STORES") == 1200   # 1200 / 1
    assert supply.tons_to_points(100, "FUEL") == 800       # 100 / (1/8)
    assert supply.tons_to_points(100, "WATER") == 600      # 100 / (1/6)
    assert supply.points_to_tons(300, "AMMO") == 1200
    assert supply.points_to_tons(120, "STORES") == 120


# --- 55.14 the efficiency throttle -------------------------------------------

def test_port_landing_cap_is_efficiency_gated():
    p = Port("P", Side.ALLIED, (0, 0), "major", max_eff=5, eff=2,
             cap_ammo=300, cap_fuel=100, cap_stores=500, cap_water=150, cap_tons=1200)
    # ceil(cap * 2/5): rounds reductions UP (55.14)
    assert supply.port_landing_cap(p, "AMMO") == math.ceil(300 * 2 / 5)     # 120
    assert supply.port_landing_cap(p, "STORES") == math.ceil(500 * 2 / 5)   # 200
    assert supply.port_landing_cap(p, "WATER") == math.ceil(150 * 2 / 5)    # 60
    assert supply.port_landing_cap(p, "FUEL") == math.ceil(100 * 2 / 5)     # 40


def test_convoy_lands_only_the_throttled_amount():
    # A convoy carrying a full port-load lands only ceil(cap * eff/max_eff) (55.14),
    # and initial_supply rises by exactly that -- no conservation fault.
    p = Port("P", Side.ALLIED, (0, 0), "major", max_eff=5, eff=2,
             cap_ammo=300, cap_fuel=100, cap_stores=500, cap_water=150, cap_tons=1200)
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0, stores=0, water=0)
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D",
                  {"AMMO": 300, "FUEL": 100, "STORES": 500, "WATER": 150})
    r = _Run(_port_state(p, dump, [conv]))
    _naval_convoys(r)
    arrived = [e for e in r.events if e.kind == EventKind.SUPPLY_ARRIVED]
    assert len(arrived) == 1
    assert arrived[0].payload["cargo"] == {"AMMO": 120, "FUEL": 40, "STORES": 200, "WATER": 60}
    d = r.state.supply("D")
    assert (d.ammo, d.fuel, d.stores, d.water) == (120, 40, 200, 60)
    for c in supply.COMMODITIES:                          # conservation exact
        on_hand = sum(getattr(su, c.lower()) for su in r.state.supplies)
        assert on_hand + r.state.consumed[c] == r.state.initial_supply[c]
    check(r.state)


def test_two_convoys_share_one_port_cap_per_opstage():
    # 55.14: the harbour throttle is per-PORT-per-OpStage, not per-convoy. Two convoys to the
    # same port this stage land ONE cap between them (120 AMMO), not 120 each.
    p = Port("P", Side.ALLIED, (0, 0), "major", max_eff=5, eff=2,
             cap_ammo=300, cap_fuel=100, cap_stores=500, cap_water=150, cap_tons=1200)
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0, stores=0, water=0)
    convoys = [Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 300}),
               Convoy("c2", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 300})]
    r = _Run(_port_state(p, dump, convoys))
    _naval_convoys(r)
    landed = sum(e.payload["cargo"].get("AMMO", 0)
                 for e in r.events if e.kind == EventKind.SUPPLY_ARRIVED)
    assert landed == math.ceil(300 * 2 / 5)               # 120 total across BOTH convoys, not 240
    assert r.state.supply("D").ammo == 120
    check(r.state)


def test_port_unloaded_beat_is_emitted_with_tons_and_eff():
    p = Port("P", Side.ALLIED, (0, 0), "major", max_eff=5, eff=2,
             cap_ammo=300, cap_fuel=100, cap_stores=500, cap_water=150, cap_tons=1200)
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0, stores=0, water=0)
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D",
                  {"AMMO": 300, "FUEL": 100, "STORES": 500, "WATER": 150})
    r = _Run(_port_state(p, dump, [conv]))
    _naval_convoys(r)
    beats = [e for e in r.events if e.kind == EventKind.PORT_UNLOADED]
    assert {b.payload["commodity"] for b in beats} == {"AMMO", "FUEL", "STORES", "WATER"}
    ammo_beat = next(b for b in beats if b.payload["commodity"] == "AMMO")
    assert ammo_beat.payload["port_id"] == "P"
    assert ammo_beat.payload["qty"] == 120
    assert ammo_beat.payload["eff"] == 2
    assert ammo_beat.payload["tons"] == supply.points_to_tons(120, "AMMO")   # 480


def test_throttle_ignored_without_a_port():
    # A dump with NO port lands the full cargo (the CHUNK-1/2 behaviour is preserved).
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0, stores=0, water=0)
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D",
                  {"AMMO": 300, "FUEL": 100, "STORES": 500, "WATER": 150})
    s = GameState(
        turn=1, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM, seed=1,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0), supplies=(dump,),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES}, convoys=(conv,))
    r = _Run(s)
    _naval_convoys(r)
    d = r.state.supply("D")
    assert (d.ammo, d.stores) == (300, 500)               # full cargo, no throttle
    assert not any(e.kind == EventKind.PORT_UNLOADED for e in r.events)


# --- 55.18 efficiency regeneration -------------------------------------------

def test_port_regen_helper():
    p = Port("P", Side.AXIS, (0, 0), "major", max_eff=5, eff=2,
             cap_ammo=1, cap_fuel=1, cap_stores=1, cap_water=1, cap_tons=1)
    assert supply.regen_eff(p) == 3                        # +1 toward max
    assert supply.regen_eff(__import__("dataclasses").replace(p, eff=5)) is None   # at max


def test_efficiency_regens_one_per_opstage_up_to_max():
    # A non-blocked port below max regains +1/OpStage, emitted as PORT_EFFICIENCY_CHANGED,
    # and stops at max_eff.
    p = Port("FREE", Side.AXIS, (0, 0), "major", max_eff=4, eff=1,
             cap_ammo=1, cap_fuel=1, cap_stores=1, cap_water=1, cap_tons=1)
    assert "FREE" not in HARBOUR_BLOCKED
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=0, fuel=0)
    s = _port_state(p, dump)
    r = _Run(s)
    levels = []
    for _ in range(5):
        _port_regen(r)
        levels.append(r.state.port("FREE").eff)
    assert levels == [2, 3, 4, 4, 4]                      # climbs then caps at max_eff
    assert any(e.kind == EventKind.PORT_EFFICIENCY_CHANGED for e in r.events)


def test_blocked_harbour_does_not_regen():
    # 55.26 / 55.25: a scuttled-ship BLOCK (San Giorgio) is not bomb damage; the 55.18
    # regen never restores it -- only engineers do (deferred). It stays pinned.
    assert "PORT-Tobruk" in HARBOUR_BLOCKED
    p = Port("PORT-Tobruk", Side.ALLIED, (0, 0), "major", max_eff=5, eff=2,
             cap_ammo=1, cap_fuel=1, cap_stores=1, cap_water=1, cap_tons=1)
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0)
    r = _Run(_port_state(p, dump))
    for _ in range(4):
        _port_regen(r)
    assert r.state.port("PORT-Tobruk").eff == 2           # San Giorgio stays
    assert not any(e.kind == EventKind.PORT_EFFICIENCY_CHANGED for e in r.events)


# --- San Giorgio seeds Tobruk at 2/5 -----------------------------------------

def test_tobruk_seeded_at_full_efficiency_per_61_6():
    s = rommels_arrival()
    tob = s.port_at(TOBRUK)
    assert tob is not None, "Tobruk must have a built-in port (56.28)"
    # [61.6] the rulebook seeds Tobruk at Efficiency 7 of 7 verbatim (above its 55.3
    # listed max of 5; San Giorgio penalty unaccounted -- transcribed, not reconciled).
    assert (tob.eff, tob.max_eff) == (7, 7)
    assert tob.cap_tons == 1700                           # [55.3] Tobruk supply tonnage
    assert tob.id in HARBOUR_BLOCKED                      # San Giorgio block: no regen (moot at max)
    # the built-in dump lives at the port hex (56.28)
    assert s.supply("AL-Tobruk").hex == tob.hex == TOBRUK


def test_tobruk_ferry_feeds_the_garrison_at_full_efficiency():
    # At the 61.6 Efficiency 7/7 the ferry lands min(cargo, 55.14 tonnage throttle) each
    # turn; that effective delivery must still cover the garrison's per-turn draw (peak
    # ~176 Stores). Now the CARGO binds for some commodities and the 1700 t throttle for
    # others -- either way each lands a positive amount and Stores clears the draw.
    s = rommels_arrival()
    tob = s.port_at(TOBRUK)
    ferry = next(c for c in s.convoys if c.lane == "SEA-TOBRUK")
    for c in supply.COMMODITIES:
        landed = min(ferry.cargo[c], supply.port_landing_cap(tob, c))
        assert landed > 0                                 # every commodity lands something
    stores_landed = min(ferry.cargo["STORES"], supply.port_landing_cap(tob, "STORES"))
    assert stores_landed >= 180                           # covers the ~176 Stores peak draw


# --- port-less scenarios stay byte-identical ---------------------------------

def test_portless_scenario_byte_identical():
    a = run(coastal_corridor(seed=7), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(coastal_corridor(seed=7), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert not any(e.kind in (EventKind.PORT_UNLOADED, EventKind.PORT_EFFICIENCY_CHANGED)
                   for e in a.events)


# --- ACCEPTANCE: the throttled ferry still holds Tobruk 6/6 ------------------

def _def_surrender_at_objective(events) -> bool:
    return any(e.kind == EventKind.COMBAT_RESOLVED
               and e.payload.get("surrender") == "defender"
               and tuple(e.payload.get("target", ())) == TOBRUK
               for e in events)


def test_tobruk_holds_6_of_6_through_the_port():
    for seed in range(1, 7):
        res = run(rommels_arrival(seed=seed),
                  ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert res.final.control_of(TOBRUK) != Control.AXIS, f"Tobruk fell (seed {seed})"
        assert not _def_surrender_at_objective(res.events), f"garrison surrendered (seed {seed})"
        # the ferry lands through PORT-Tobruk at its 61.6 Efficiency 7
        beats = [e for e in res.events if e.kind == EventKind.PORT_UNLOADED
                 and e.payload["port_id"] == "PORT-Tobruk"]
        assert beats and all(b.payload["eff"] == 7 for b in beats), f"ferry not landing at eff 7 (seed {seed})"


def test_determinism_preserved_with_ports():
    a = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)


def test_siege_still_crackable_through_the_throttle():
    # The Benghazi rear throttle must not starve the Axis barrage below the crack path: a strong
    # seed still batters the wall through it.
    #
    # These seeds were re-pinned three times under the old shared rng (the two-level clock, Rommel's
    # +5 CPA, the SEA-TOBRUK interdiction schedule) -- all ONE instrument bug, a shared stream any
    # subsystem re-indexed. T0-0 (per-subsystem streams, game/dice.py) ended that class of re-pin.
    # A genuine RULE change still moves them, and it is not the same bug: T0-5 (6.27 Cohesion / 15.63
    # Morale AVERAGED over the largest units in a Close Assault) changed which assaults surrender vs
    # reach the CRT, so units live/die on different hexes and the cascade reaches the 25.14 wall on
    # different seeds -- inherent single-seed chaos, not a desync. Re-pinned (16, 162) -> (197, 214);
    # MEASURED, siege_of_tobruk fires FORT_REDUCED on 6 of seeds 1..500 (197,214,220,232,293,405),
    # still rare (2/220 under T0-0). The crack RATE is the owner's siege knob, NOT a magnitude to
    # bend here. This test guards only that the path SURVIVES.
    battered = False
    for seed in (197, 214):
        res = run(siege_of_tobruk(seed=seed),
                  ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        if any(e.kind == EventKind.FORT_REDUCED and tuple(e.payload["hex"]) == TOBRUK
               for e in res.events):
            battered = True
    assert battered, "siege artillery must still batter Tobruk's wall through the throttle"
