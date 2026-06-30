"""Pure fold: apply(state, event) -> state (brief §4.1).

No RNG, no I/O — outcomes are already facts in the event. fold(initial, events)
reconstructs state from scratch (the replay/visualisation path, §4.7).
"""
from __future__ import annotations

from dataclasses import replace

from .events import Control, Event, EventKind, Phase, Side
from .state import GameState, StepRecord, VP


def apply(state: GameState, event: Event) -> GameState:
    k = event.kind
    p = event.payload

    if k in (EventKind.GAME_INITIALIZED, EventKind.ORDER_REJECTED,
             EventKind.COMBAT_RESOLVED):
        return state  # markers / audit records — losses come as separate STEP_LOST

    if k == EventKind.WEATHER_ROLLED:
        return replace(state, weather=p["weather"], move_modifier=p["move_modifier"])

    if k == EventKind.UNIT_MOVED:
        u = state.unit(p["unit_id"])
        return state.with_unit(
            replace(u, hex=tuple(p["to"]), cp_used=u.cp_used + p["cp_spent"]))

    if k == EventKind.STEP_LOST:
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, steps=_apply_step_loss(u.steps, p["amount"])))

    if k == EventKind.HEX_CONTROL_CHANGED:
        return state.with_control(tuple(p["coord"]), Control(p["control"]))

    if k == EventKind.VICTORY_CHECKED:
        return replace(state, vp=VP(axis=p["axis"], allied=p["allied"]))

    if k == EventKind.PHASE_ADVANCED:
        return replace(state, phase=Phase(p["phase"]), active_side=Side(p["active_side"]))

    if k == EventKind.TURN_ADVANCED:
        # New OpStage: every unit's CPA refreshes (rule 6.16 — CP do not carry over).
        units = tuple(replace(u, cp_used=0.0) for u in state.units)
        return replace(state, turn=p["turn"], units=units)

    raise ValueError(f"unhandled event kind {k}")


def _apply_step_loss(steps: tuple[StepRecord, ...], amount: int) -> tuple[StepRecord, ...]:
    """Peel `amount` strength off the back of the step list (last sub-unit absorbs
    losses first) — a deterministic, replayable loss rule."""
    out = list(steps)
    i = len(out) - 1
    while amount > 0 and i >= 0:
        take = min(amount, out[i].strength)
        out[i] = replace(out[i], strength=out[i].strength - take)
        amount -= take
        i -= 1
    return tuple(out)


def fold(initial: GameState, events: list[Event]) -> GameState:
    state = initial
    for e in events:
        state = apply(state, e)
    return state
