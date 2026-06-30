"""Property checks run after every applied event (brief §7).

A violation means the engine misencoded a rule — the project's single biggest
risk — so we fail loud rather than continue "confidently wrong for 111 turns".
"""
from __future__ import annotations

from .state import GameState

FUEL_EPS = 1e-6


class InvariantViolation(Exception):
    pass


def check(state: GameState, initial_fuel: float) -> None:
    for u in state.units:
        for s in u.steps:
            if s.strength < 0:
                raise InvariantViolation(
                    f"unit {u.id} step {s.label!r} has negative strength {s.strength}")
        if u.fuel < -FUEL_EPS:
            raise InvariantViolation(f"unit {u.id} has negative fuel {u.fuel}")
        if state.hex_at(u.hex) is None:
            raise InvariantViolation(f"unit {u.id} on non-existent hex {u.hex}")

    # Supply conservation (per commodity; here: fuel). Fuel is only consumed —
    # no sources in the toy — so on-hand + consumed must equal the initial total.
    on_hand = sum(u.fuel for u in state.units)
    if abs(on_hand + state.fuel_consumed - initial_fuel) > FUEL_EPS:
        raise InvariantViolation(
            f"fuel not conserved: on_hand={on_hand} + consumed={state.fuel_consumed} "
            f"!= initial={initial_fuel}")
