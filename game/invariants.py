"""Property checks run after every applied event (brief §7).

A violation means the engine misencoded a rule — the project's biggest risk — so
we fail loud rather than continue "confidently wrong for 111 turns". Multi-commodity
supply conservation returns as its own invariant once the supply slice lands; for
now we guard step counts, legal positions, and stacking limits.
"""
from __future__ import annotations

from . import stacking
from .state import GameState


class InvariantViolation(Exception):
    pass


def check(state: GameState) -> None:
    for u in state.units:
        for s in u.steps:
            if s.strength < 0:
                raise InvariantViolation(
                    f"unit {u.id} step {s.label!r} has negative strength {s.strength}")
        if not state.terrain.exists(u.hex):
            raise InvariantViolation(f"unit {u.id} on non-existent hex {u.hex}")

    # Stacking limits, checked at rest (rule 9.31): no hex over its point limit.
    occupied: dict = {}
    for u in state.units:
        if u.alive:
            occupied.setdefault(u.hex, []).append(u)
    for coord, units in occupied.items():
        terrain = state.terrain.terrain[coord]
        if not stacking.within_hex_limit(units, terrain):
            pts = stacking.hex_points(units, terrain)
            raise InvariantViolation(
                f"stacking exceeded at {coord}: {pts} points "
                f"(limit {stacking.DEFAULT_HEX_LIMIT})")
