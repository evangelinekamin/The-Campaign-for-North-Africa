"""Property checks run after every applied event (brief §7).

A violation means the engine misencoded a rule — the project's biggest risk — so
we fail loud rather than continue "confidently wrong for 111 turns". Multi-commodity
supply conservation returns as its own invariant once the supply slice lands; for
now we guard step counts, legal positions, and stacking limits.
"""
from __future__ import annotations

from . import adjudication, stacking
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
    # The detection lives in adjudication.stacking_violations (single source of
    # truth); here we fail loud on the first, preserving the historic raise-order.
    for c in adjudication.stacking_violations(state):
        units = state.units_at(c.hex)
        pts = stacking.hex_points(units, state.terrain.terrain[c.hex])
        raise InvariantViolation(
            f"stacking exceeded at {c.hex}: {pts} points "
            f"(limit {stacking.DEFAULT_HEX_LIMIT})")

    # Supply conservation (rule 32): per commodity, on-hand + consumed == initial.
    # Nothing is created except at sources (none modelled yet); nothing vanishes
    # except defined consumption. on-hand sums the dumps AND any cargo riding on truck
    # convoys (rules 53-54) -- a TRUCK_LOADED merely moves supply from a dump onto a
    # truck, so the truck's pools are the single new conservation surface.
    for commodity, initial in state.initial_supply.items():
        attr = commodity.lower()
        on_hand = (sum(getattr(su, attr) for su in state.supplies)
                   + sum(getattr(t, attr) for t in state.trucks))
        if on_hand + state.consumed.get(commodity, 0) != initial:
            raise InvariantViolation(
                f"{commodity} not conserved: on_hand={on_hand} + "
                f"consumed={state.consumed.get(commodity, 0)} != initial={initial}")
