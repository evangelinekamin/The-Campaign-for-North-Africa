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

    for su in state.supplies:                      # dumps relocate now (rule 32.3)
        if not state.terrain.exists(su.hex):
            raise InvariantViolation(f"supply {su.id} on non-existent hex {su.hex}")

    # Stacking limits, checked at rest (rule 9.31): no hex over its point limit.
    occupied: dict = {}
    for u in state.units:
        if state.on_map(u):                        # off-map reinforcements don't stack yet
            occupied.setdefault(u.hex, []).append(u)
    for coord, units in occupied.items():
        terrain = state.terrain.terrain[coord]
        if not stacking.within_hex_limit(units, terrain):
            pts = stacking.hex_points(units, terrain)
            raise InvariantViolation(
                f"stacking exceeded at {coord}: {pts} points "
                f"(limit {stacking.DEFAULT_HEX_LIMIT})")

    # Supply conservation (rule 32): per commodity, on-hand + consumed == initial.
    # Nothing is created except at sources (none modelled yet); nothing vanishes
    # except defined consumption.
    for commodity, initial in state.initial_supply.items():
        on_hand = sum(getattr(su, commodity.lower()) for su in state.supplies)
        if on_hand + state.consumed.get(commodity, 0) != initial:
            raise InvariantViolation(
                f"{commodity} not conserved: on_hand={on_hand} + "
                f"consumed={state.consumed.get(commodity, 0)} != initial={initial}")
