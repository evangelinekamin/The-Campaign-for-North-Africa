"""Abstract air -- the P5 "fidelity where the camera is" layer (rules 33-46 at the 32.0/58.0
grain). Step 3 is the SPINE: the AirWing force pool, the two-arena air-superiority gate (LAND +
SEA, forced apart by 41.63), the weather grounding (29.43/29.52), and the byte-identical default
(air=() draws no dice, fires no beat). Real EFFECTS via per-side Air Point scalars, NO per-plane
bookkeeping; the magnitudes are FLAGGED PROXY (the 34.6/59.3 chart is untranscribed)."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import apply, fold
from game.engine import (_air_arena_fighters, _air_grounded, _air_superiority, _Run,
                         determinism_signature, run)
from game.events import Event, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival, siege_of_tobruk
from game.state import AirWing, GameState, VP
from game.terrain import Terrain


def _mini(air=(), *, weather="clear", turn=1, stage=1) -> GameState:
    """A unit-/dump-free state to exercise the air beat in isolation."""
    return GameState(
        turn=turn, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=1, weather=weather, vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0),
        supplies=(), consumed={}, initial_supply={},
        air=tuple(air), stage=stage)


# --- the state fields --------------------------------------------------------

def test_air_defaults_empty():
    assert GameState.__dataclass_fields__["air"].default == ()
    assert GameState.__dataclass_fields__["air_superiority"].default_factory() == {}
    for s in (coastal_corridor(), rommels_arrival(), siege_of_tobruk()):
        assert s.air == () and s.air_superiority == {}


# --- the gate fold + OpStage clearing ----------------------------------------

def test_superiority_folds_victor():
    s = _mini()
    e = Event(0, 1, Phase.LOGISTICS, Side.SYSTEM, "SYSTEM", EventKind.AIR_SUPERIORITY_RESOLVED,
              {"arena": "LAND", "axis_fighters": 8, "allied_fighters": 3,
               "victor": Side.AXIS.value, "margin": 5}, rng_draws=(4, 2))
    s2 = apply(s, e)
    assert s2.air_superiority == {"LAND": Side.AXIS.value}
    assert s2.air_superiority_of("LAND") == Side.AXIS.value
    assert s2.air_superiority_of("SEA") is None


def test_superiority_tie_folds_none():
    s = _mini().with_air_superiority("SEA", None)
    assert s.air_superiority == {"SEA": None}
    assert s.air_superiority_of("SEA") is None


def test_superiority_cleared_at_opstage_boundary():
    s = _mini(stage=1).with_air_superiority("LAND", Side.AXIS.value)
    stage_adv = Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", EventKind.STAGE_ADVANCED,
                      {"stage": 2})
    assert apply(s, stage_adv).air_superiority == {}
    turn_adv = Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", EventKind.TURN_ADVANCED,
                     {"turn": 2})
    assert apply(s, turn_adv).air_superiority == {}


# --- the SYSTEM air-superiority beat -----------------------------------------

def _wings():
    return (AirWing("LW-land", Side.AXIS, "LAND", fighters=9, strike=6, recon=2),
            AirWing("DAF-land", Side.ALLIED, "LAND", fighters=3, strike=4, recon=3),
            AirWing("RA-sea", Side.AXIS, "SEA", fighters=2, strike=5, recon=1),
            AirWing("FAA-sea", Side.ALLIED, "SEA", fighters=7, strike=3, recon=4))


def test_arena_fighters_partition():
    s = _mini(_wings())
    assert _air_arena_fighters(s, "LAND") == (9, 3)
    assert _air_arena_fighters(s, "SEA") == (2, 7)


def test_beat_resolves_each_arena_and_folds():
    r = _Run(_mini(_wings()))
    _air_superiority(r)
    res = [e for e in r.events if e.kind == EventKind.AIR_SUPERIORITY_RESOLVED]
    assert {e.payload["arena"] for e in res} == {"LAND", "SEA"}
    for e in res:                                        # every roll records its two dice
        assert len(e.rng_draws) == 2
        margin = abs((e.payload["axis_fighters"] + e.rng_draws[0])
                     - (e.payload["allied_fighters"] + e.rng_draws[1]))
        assert e.payload["margin"] == margin
    # the folded gate matches the emitted victors
    assert r.state.air_superiority == {e.payload["arena"]: e.payload["victor"] for e in res}
    check(r.state)


def test_beat_is_grounded_by_foul_weather():
    for foul in ("sandstorm", "rainstorm"):
        assert _air_grounded(foul)
        r = _Run(_mini(_wings(), weather=foul))
        _air_superiority(r)
        assert not r.events                              # no beat, no dice, no phase
        assert r.state.air_superiority == {}
    assert not _air_grounded("clear") and not _air_grounded("hot")


def test_beat_noop_without_air():
    r = _Run(_mini(()))                                  # air=() -> byte-identical
    _air_superiority(r)
    assert not r.events


# --- byte-identity of the live scenarios (air=() everywhere) -----------------

def test_rommels_arrival_byte_identical_and_air_silent():
    a = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert not any(e.kind == EventKind.AIR_SUPERIORITY_RESOLVED for e in a.events)
    assert a.final.air_superiority == {}


def test_seeded_air_run_is_deterministic_and_fires():
    base = rommels_arrival(seed=7)
    scen = replace(base, air=(AirWing("LW", Side.AXIS, "LAND", 8, 6, 2),
                              AirWing("DAF", Side.ALLIED, "LAND", 4, 3, 3)))
    a = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    sup = [e for e in a.events if e.kind == EventKind.AIR_SUPERIORITY_RESOLVED]
    assert sup and all(e.payload["arena"] == "LAND" for e in sup)
    # live state equals the fold of its own log (the replay identity)
    assert fold(a.initial, a.events).air_superiority == a.final.air_superiority
