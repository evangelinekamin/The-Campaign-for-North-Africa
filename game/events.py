"""Event-sourcing core types (brief §4.1).

The engine is an append-only log of Events; GameState is a deterministic fold
over that log (see game.apply). Every Event is a *fact* — outcomes (die rolls,
losses) are baked in at generation time and the die rolls that produced them are
recorded in `rng_draws`, so that `apply` is pure and replay needs no RNG. This
is what makes runs reproducible: same seed -> identical event stream ->
byte-identical state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class Side(str, Enum):
    AXIS = "AXIS"
    ALLIED = "ALLIED"
    SYSTEM = "SYSTEM"


class Control(str, Enum):
    AXIS = "AXIS"
    ALLIED = "ALLIED"
    NEUTRAL = "NEUTRAL"


class Phase(str, Enum):
    WEATHER = "WEATHER"
    MOVEMENT = "MOVEMENT"
    COMBAT = "COMBAT"
    RECORD = "RECORD"


# System owns WEATHER and RECORD; the active side's Front Commander owns
# MOVEMENT and COMBAT. This is the seam the orchestrator uses to decide which
# role/agent to invoke per phase (brief §4.3).
SYSTEM_PHASES = (Phase.WEATHER, Phase.RECORD)


class EventKind(str, Enum):
    GAME_INITIALIZED = "GAME_INITIALIZED"
    WEATHER_ROLLED = "WEATHER_ROLLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    REINFORCEMENT_ARRIVED = "REINFORCEMENT_ARRIVED"
    UNIT_MOVED = "UNIT_MOVED"
    UNIT_RETREATED = "UNIT_RETREATED"
    SUPPLY_MOVED = "SUPPLY_MOVED"
    SUPPLY_CONSUMED = "SUPPLY_CONSUMED"
    BARRAGE_RESOLVED = "BARRAGE_RESOLVED"
    ANTI_ARMOR_RESOLVED = "ANTI_ARMOR_RESOLVED"
    COMBAT_RESOLVED = "COMBAT_RESOLVED"
    STEP_LOST = "STEP_LOST"
    COHESION_CHANGED = "COHESION_CHANGED"
    FORT_REDUCED = "FORT_REDUCED"
    HEX_CONTROL_CHANGED = "HEX_CONTROL_CHANGED"
    PHASE_ADVANCED = "PHASE_ADVANCED"
    TURN_ADVANCED = "TURN_ADVANCED"
    VICTORY_CHECKED = "VICTORY_CHECKED"
    # STAFF_* are narrative / no-op audit events: staff chatter the board is
    # invariant to (they fold to state unchanged; see game.apply, game.staff_events).
    STAFF_INTENT = "STAFF_INTENT"
    STAFF_PROPOSAL = "STAFF_PROPOSAL"
    STAFF_CONSTRAINT = "STAFF_CONSTRAINT"
    STAFF_ADJUDICATION = "STAFF_ADJUDICATION"
    STAFF_DISSENT = "STAFF_DISSENT"


@dataclass(frozen=True, slots=True)
class Event:
    seq: int                       # global total order, 0-based
    turn: int                      # 1..max_turns
    phase: Phase                   # phase active when the event was emitted
    side: Side                     # acting side (or SYSTEM)
    actor: str                     # role id, or "SYSTEM"
    kind: EventKind
    payload: dict                  # json-safe values only (no enums/sets)
    rng_draws: tuple[int, ...] = ()


def event_to_dict(e: Event) -> dict:
    """Stable, json-safe projection of an event (for hashing/serialisation)."""
    return {
        "seq": e.seq,
        "turn": e.turn,
        "phase": e.phase.value,
        "side": e.side.value,
        "actor": e.actor,
        "kind": e.kind.value,
        "payload": e.payload,
        "rng_draws": list(e.rng_draws),
    }


def log_to_json(events: list[Event]) -> str:
    """Canonical serialisation of an event log; equality of two such strings is
    the determinism test (brief §7: same seed + log => identical game)."""
    return json.dumps([event_to_dict(e) for e in events], sort_keys=True)
