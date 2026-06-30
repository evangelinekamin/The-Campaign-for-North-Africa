"""Pure fold: apply(state, event) -> state (brief §4.1).

No RNG, no I/O — outcomes are already facts in the event. fold(initial, events)
reconstructs state from scratch, which is both the replay path and the
visualisation path (§4.7): the renderer is just another fold over the same log.
"""
from __future__ import annotations

from dataclasses import replace

from .events import Control, Event, EventKind, Phase, Side
from .state import GameState, StepRecord, Unit, VP


def apply(state: GameState, event: Event) -> GameState:
    k = event.kind
    p = event.payload

    if k in (EventKind.GAME_INITIALIZED, EventKind.ORDER_REJECTED,
             EventKind.COMBAT_RESOLVED):
        # Markers / audit records — no state mutation. (Combat losses are
        # emitted as separate STEP_LOST events so each fact stands alone.)
        return state

    if k == EventKind.WEATHER_ROLLED:
        return replace(state, weather=p["weather"], move_modifier=p["move_modifier"])

    if k == EventKind.UNIT_MOVED:
        u = state.unit(p["unit_id"])
        moved = state.with_unit(replace(u, hex=tuple(p["to"]), fuel=p["fuel_after"]))
        # Conservation is kept true after *this single event* by folding the
        # consumption in here rather than in a separate event.
        return replace(moved, fuel_consumed=moved.fuel_consumed + p["fuel_cost"])

    if k == EventKind.SUPPLY_CONSUMED:
        return replace(state, fuel_consumed=state.fuel_consumed + p["fuel"])

    if k == EventKind.STEP_LOST:
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, steps=_apply_step_loss(u.steps, p["amount"])))

    if k == EventKind.HEX_CONTROL_CHANGED:
        h = state.hex_at(tuple(p["coord"]))
        return state.with_hex(replace(h, control=Control(p["control"])))

    if k == EventKind.VICTORY_CHECKED:
        return replace(state, vp=VP(axis=p["axis"], allied=p["allied"]))

    if k == EventKind.PHASE_ADVANCED:
        return replace(state, phase=Phase(p["phase"]), active_side=Side(p["active_side"]))

    if k == EventKind.TURN_ADVANCED:
        return replace(state, turn=p["turn"])

    raise ValueError(f"unhandled event kind {k}")


def _apply_step_loss(steps: tuple[StepRecord, ...], amount: int) -> tuple[StepRecord, ...]:
    """Peel `amount` strength off the back of the step list (last sub-unit
    absorbs losses first) — a deterministic, replayable loss rule."""
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
