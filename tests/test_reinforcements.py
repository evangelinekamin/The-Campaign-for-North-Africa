"""Rule 20 -- reinforcements WAIT for stacking room instead of crashing the invariant.

A reinforcement is dormant (off-map, uncounted by the 9.31 stacking check) until its
arrival_turn, at which point state.on_map pops it onto its entry hex. If that hex is already
at the stacking limit -- something live LLM play can arrange by crowding an entry hex while
the reinforcement is dormant -- the pop happens at the TURN_ADVANCED fold and the stacking
invariant would hard-crash. The engine now DEFERS such an arrival (game.engine.
_defer_crowded_reinforcements, run just before the TURN_ADVANCED emit): it bumps the unit's
arrival_turn one game-turn (REINFORCEMENT_DELAYED) so the unit stays dormant and retries next
turn, arriving only once its entry hex has room.

The scripted scenarios seed distinct entry hexes with room, so the deferral never fires and
their event logs stay byte-identical (asserted in test_engine.py / here at scenario level).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game import stacking
from game.engine import _Run, _defer_crowded_reinforcements, _reinforcements, run
from game.events import EventKind, Phase, Side
from game.hexmap import Coord
from game.invariants import InvariantViolation
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import rommels_arrival
from game.state import GameState, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain


# --- fixtures ----------------------------------------------------------------

def _grid(n: int = 4) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _unit(uid: str, hex_: Coord, *, sp: int = 1, arrival: int = 0) -> Unit:
    return Unit(uid, Side.AXIS, hex_, (StepRecord("x", 6),), Mobility.MOTORIZED,
                cpa=40, stacking_points=sp, oca=4, dca=4, cohesion=6, arrival_turn=arrival)


def _state(units, *, turn: int = 1) -> GameState:
    return GameState(turn=turn, max_turns=8, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                     seed=7, weather="normal", vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=(0, 0), supplies=(),
                     consumed={}, initial_supply={})


def _advance_turn_boundary(r: _Run, next_turn: int) -> None:
    """Mirror the run() game-turn boundary: defer any crowded arrival, THEN advance the turn
    (whose fold + invariant check would crash on an un-deferred over-stack), then land arrivals."""
    _defer_crowded_reinforcements(r, next_turn)
    r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM", {"turn": next_turn})
    _reinforcements(r)


ENTRY: Coord = (0, 0)


# --- the landmine, unguarded -------------------------------------------------

def test_full_entry_hex_would_crash_without_the_deferral():
    # Documents the bug the fix defuses: a dormant reinforcement popping onto a full hex at the
    # TURN_ADVANCED fold trips the 9.31 stacking invariant. This is the raw pop, WITHOUT the
    # _defer_crowded_reinforcements guard -- it must raise.
    residents = [_unit(f"R{i}", ENTRY, sp=1) for i in range(stacking.DEFAULT_HEX_LIMIT)]  # hex full
    reinf = _unit("REINF", ENTRY, sp=1, arrival=2)
    r = _Run(_state(residents + [reinf], turn=1))
    with pytest.raises(InvariantViolation):
        r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM", {"turn": 2})   # no deferral: pops -> crash


# --- (1) full entry hex delays the arrival until room opens -------------------

def test_reinforcement_delays_when_entry_hex_full_then_arrives_when_room_opens():
    residents = [_unit(f"R{i}", ENTRY, sp=1) for i in range(stacking.DEFAULT_HEX_LIMIT)]  # 5 pts = full
    reinf = _unit("REINF", ENTRY, sp=1, arrival=2)
    r = _Run(_state(residents + [reinf], turn=1))

    # Game-turn 1 -> 2: the entry hex is full, so the arrival is deferred (no crash) not popped.
    _advance_turn_boundary(r, 2)
    assert r.state.turn == 2
    ru = r.state.unit("REINF")
    assert ru.arrival_turn == 3                       # bumped one game-turn
    assert not r.state.on_map(ru)                     # still dormant, uncounted by stacking
    delayed = [e for e in r.events if e.kind == EventKind.REINFORCEMENT_DELAYED]
    assert [e.payload["unit_id"] for e in delayed] == ["REINF"]
    assert not any(e.kind == EventKind.REINFORCEMENT_ARRIVED and e.payload["unit_id"] == "REINF"
                   for e in r.events)                 # has NOT arrived yet

    # Room opens: a resident vacates the entry hex.
    r.emit(EventKind.UNIT_MOVED, Side.AXIS, "SYSTEM",
           {"unit_id": "R0", "from": list(ENTRY), "to": [1, 0], "cp_spent": 0.0})

    # Game-turn 2 -> 3: room now exists, so the reinforcement arrives on its (delayed) turn 3.
    _advance_turn_boundary(r, 3)
    assert r.state.turn == 3
    ru = r.state.unit("REINF")
    assert r.state.on_map(ru)                          # now on the board
    arrived = [e for e in r.events
               if e.kind == EventKind.REINFORCEMENT_ARRIVED and e.payload["unit_id"] == "REINF"]
    assert len(arrived) == 1 and arrived[0].turn == 3  # arrived a LATER turn than scheduled (2)
    # exactly one deferral fired; the unit was never dropped or duplicated.
    assert sum(1 for e in r.events if e.kind == EventKind.REINFORCEMENT_DELAYED) == 1


# --- (2) regression: a reinforcement with room still arrives on its exact turn -

def test_reinforcement_with_room_arrives_on_its_scheduled_turn():
    residents = [_unit("R0", ENTRY, sp=1), _unit("R1", ENTRY, sp=1)]   # 2 pts: room to spare
    reinf = _unit("REINF", ENTRY, sp=1, arrival=2)
    r = _Run(_state(residents + [reinf], turn=1))

    _advance_turn_boundary(r, 2)
    ru = r.state.unit("REINF")
    assert ru.arrival_turn == 2                         # untouched: no deferral
    assert not any(e.kind == EventKind.REINFORCEMENT_DELAYED for e in r.events)
    assert r.state.on_map(ru)                           # on-map exactly at turn 2
    arrived = [e for e in r.events
               if e.kind == EventKind.REINFORCEMENT_ARRIVED and e.payload["unit_id"] == "REINF"]
    assert len(arrived) == 1 and arrived[0].turn == 2   # exact scheduled turn


# --- scenario-level guard: the scripted seeds never defer (byte-identity safety) -

def test_scripted_scenario_reinforcements_never_defer():
    # Rommel's Arrival seeds distinct entry hexes with room, so the deferral path stays inert --
    # zero REINFORCEMENT_DELAYED events -- which is why the event log is byte-identical to before.
    init = rommels_arrival(seed=42)
    res = run(rommels_arrival(seed=42), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.AXIS))
    assert not any(e.kind == EventKind.REINFORCEMENT_DELAYED for e in res.events)
    arrivals = [(e.payload["unit_id"], e.turn)
                for e in res.events if e.kind == EventKind.REINFORCEMENT_ARRIVED]
    assert arrivals                                     # some reinforcement did enter this run
    for uid, turn in arrivals:
        assert init.unit(uid).arrival_turn == turn      # each landed on its seeded turn -- no delay
