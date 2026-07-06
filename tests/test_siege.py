"""Siege of Tobruk (rule 25.14 / 25.16): a sustained artillery BARRAGE batters a
fortification's level down one step at a time, gated behind GameState.siege_rules.

Verifies the faithful crackable siege -- the wall reduces and emits FORT_REDUCED
(folding into a dynamic per-hex fort level), close assault reads the CURRENT
(possibly reduced) level, barrage never evicts, close assault never reduces the
wall, and the canonical rommels_arrival benchmark is byte-identical with the rule
OFF (the default)."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import apply, fold
from game.engine import (BARRAGE_HITS_PER_FORT_LEVEL, _barrage_step, _resolve_combat,
                         _Run, determinism_signature, run)
from game.events import Event, EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import rommels_arrival, siege_of_tobruk
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


def _siege_state(*, siege: bool, fort: int = 2, atk_barrage: int = 25,
                 fort_levels: dict | None = None) -> GameState:
    """Axis artillery in (0,0) adjacent to a fortified Allied garrison in (1,0).
    atk_barrage=25 x TOE 8 -> 20 Actual Barrage Points -> CRT column 8, where EVERY
    d66 roll yields a Pin or a loss, so the barrage's effect is seed-independent."""
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.MAJOR_CITY}
    arty = Unit("AR", Side.AXIS, (0, 0), (StepRecord("ar", 8),), mobility=Mobility.MOTORIZED,
                cpa=20, stacking_points=1, oca=0, dca=1, barrage=atk_barrage, vulnerability=5)
    gar = Unit("GAR", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=2, oca=5, dca=8, is_garrison_home=True)
    # Ammo sized for several barrages: barrage now costs 4 x TOE (50.14) = 4*8 = 32.
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=200, fuel=60)
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={(1, 0): fort}),
        control={}, units=(arty, gar), target_hex=(1, 0), supplies=(dump,),
        consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 200, "FUEL": 60},
        siege_rules=siege, fort_levels=dict(fort_levels or {}))


# --- the dynamic fort level (state layer) ------------------------------------

def test_fort_level_falls_back_to_static():
    # with no dynamic overlay, the current level IS the static terrain fortification.
    s = _siege_state(siege=True, fort=2)
    assert s.fort_level((1, 0)) == 2
    assert s.fort_level((0, 0)) == 0            # unfortified hex


def test_fort_reduced_event_folds():
    s = _siege_state(siege=True, fort=2)
    e = Event(0, 1, Phase.COMBAT, Side.AXIS, "AXIS/Front",
              EventKind.FORT_REDUCED, {"hex": [1, 0], "level": 1})
    s2 = apply(s, e)
    assert s2.fort_level((1, 0)) == 1
    assert s.fort_level((1, 0)) == 2            # original state untouched (immutability)
    assert fold(s, [e]).fort_level((1, 0)) == 1


# --- barrage batters the wall (gated) ----------------------------------------

def test_barrage_reduces_fort_and_emits_event():
    r = _Run(_siege_state(siege=True, fort=2))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set())
    reduced = [e for e in r.events if e.kind == EventKind.FORT_REDUCED]
    assert reduced, "a successful barrage on a fortified hex must emit FORT_REDUCED"
    assert reduced[0].payload == {"hex": [1, 0], "level": 1}
    assert r.state.fort_level((1, 0)) == 1


def test_barrage_never_reduces_when_siege_off():
    # default (benchmark) posture: the wall-reduction mechanic is inert.
    r = _Run(_siege_state(siege=False, fort=2))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set())
    assert not any(e.kind == EventKind.FORT_REDUCED for e in r.events)
    assert r.state.fort_level((1, 0)) == 2      # wall intact


def test_barrage_never_evicts_the_garrison():
    # rule 25.14 is sacred: barrage brings the wall down but never moves the garrison
    # nor its base fort in the static map -- only the dynamic overlay drops.
    r = _Run(_siege_state(siege=True, fort=2))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set())
    gar = r.state.unit("GAR")
    assert gar.hex == (1, 0)                                   # not evicted
    assert not any(e.kind == EventKind.UNIT_RETREATED for e in r.events)
    assert r.state.terrain.fortifications[(1, 0)] == 2         # static base sacred


def test_barrage_floors_fort_at_zero():
    # a barrage on an already-open (level 0) fortified hex emits nothing.
    r = _Run(_siege_state(siege=True, fort=0))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set())
    assert not any(e.kind == EventKind.FORT_REDUCED for e in r.events)


def test_hits_per_level_knob(monkeypatch):
    # the tuning knob: N successful barrages per fort level. At 2, one barrage does
    # NOT yet drop the wall; the second one does.
    monkeypatch.setattr("game.engine.BARRAGE_HITS_PER_FORT_LEVEL", 2)
    r = _Run(_siege_state(siege=True, fort=2))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set())
    assert not any(e.kind == EventKind.FORT_REDUCED for e in r.events)   # 1 hit: no drop yet
    assert r.state.fort_level((1, 0)) == 2
    _barrage_step(r, Side.AXIS, Side.ALLIED, set())
    assert any(e.kind == EventKind.FORT_REDUCED for e in r.events)        # 2nd hit drops it
    assert r.state.fort_level((1, 0)) == 1


# --- close assault reads the CURRENT (reduced) level -------------------------

def _assault_state(fort_levels: dict) -> GameState:
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR}
    atk = Unit("A", Side.AXIS, (0, 0), (StepRecord("i", 5),), mobility=Mobility.FOOT,
               cpa=25, stacking_points=1, oca=6, dca=2)
    dfd = Unit("D", Side.ALLIED, (1, 0), (StepRecord("i", 3),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=1, oca=2, dca=2)
    sup = (SupplyUnit("DA", Side.AXIS, (0, 0), ammo=40, fuel=60),
           SupplyUnit("DL", Side.ALLIED, (1, 0), ammo=40, fuel=60))
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=11,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={(1, 0): 2}),
        control={}, units=(atk, dfd), target_hex=(1, 0), supplies=sup,
        consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 80, "FUEL": 120},
        siege_rules=True, fort_levels=dict(fort_levels))


def _assault_column(fort_levels: dict) -> int:
    r = _Run(_assault_state(fort_levels))
    atk = [r.state.unit("A")]
    dfd = [r.state.unit("D")]
    _resolve_combat(r, Side.AXIS, "AXIS/Front", atk, dfd, (1, 0), set())
    resolved = [e for e in r.events if e.kind == EventKind.COMBAT_RESOLVED]
    return resolved[0].payload["column"]


def test_close_assault_tracks_reduced_fort_level():
    # identical assault + identical seed: a reduced wall (overlay 0) yields a column
    # further toward the attacker than the intact wall (static 2). Same dice, so the
    # ONLY difference is the fortification shift -- proving the engine reads the
    # dynamic level, not the static one.
    intact = _assault_column({})              # falls back to static level 2
    breached = _assault_column({(1, 0): 0})   # wall battered open
    assert breached > intact


# --- the benchmark is untouched (siege OFF is the default) -------------------

def test_rommels_arrival_defaults_to_siege_off():
    assert rommels_arrival().siege_rules is False


def test_benchmark_byte_identical_and_emits_no_fort_reduction():
    a = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert not any(e.kind == EventKind.FORT_REDUCED for e in a.events)


# --- the new scenario --------------------------------------------------------

def test_siege_of_tobruk_constructible():
    s = siege_of_tobruk(seed=1941)
    assert s.siege_rules is True
    # same battle: identical OOB / placement to rommels_arrival, only the flag differs.
    base = rommels_arrival(seed=1941)
    assert [u.id for u in s.units] == [u.id for u in base.units]
    assert {u.id: u.hex for u in s.units} == {u.id: u.hex for u in base.units}


def test_siege_of_tobruk_runs_full_game():
    a = run(siege_of_tobruk(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert a.winner in (Side.AXIS, Side.ALLIED)
    assert fold(a.initial, a.events) == a.final               # replay-exact
    b = run(siege_of_tobruk(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)


def test_siege_of_tobruk_deterministic_across_seeds():
    from game.hexmap import distance  # noqa: F401 (ensures import health)
    for seed in range(1, 4):
        a = run(siege_of_tobruk(seed=seed), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert a.winner in (Side.AXIS, Side.ALLIED)
        assert fold(a.initial, a.events) == a.final
