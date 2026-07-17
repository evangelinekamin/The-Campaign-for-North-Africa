"""Property checks run after every applied event (brief §7).

A violation means the engine misencoded a rule — the project's biggest risk — so
we fail loud rather than continue "confidently wrong for 111 turns". Multi-commodity
supply conservation returns as its own invariant once the supply slice lands; for
now we guard step counts, legal positions, and stacking limits.
"""
from __future__ import annotations

from itertools import chain

from . import adjudication, stacking, supply
from .state import GameState


class InvariantViolation(Exception):
    pass


def check(state: GameState) -> None:
    # The Operations Stage is always one of the three within a game-turn (rule 5.1).
    if state.stage not in (1, 2, 3):
        raise InvariantViolation(f"stage {state.stage} out of the 1..3 Operations-Stage range")

    for u in state.units:
        for s in u.steps:
            if s.strength < 0:
                raise InvariantViolation(
                    f"unit {u.id} step {s.label!r} has negative strength {s.strength}")
        if not state.terrain.exists(u.hex):
            raise InvariantViolation(f"unit {u.id} on non-existent hex {u.hex}")
        # Broken-down TOE is a subset of the unit's strength (rule 21.44): it is
        # peeled off the operational pool, never below zero nor above total strength.
        if not 0 <= u.broken_down <= u.strength:
            raise InvariantViolation(
                f"unit {u.id} broken_down={u.broken_down} out of [0, {u.strength}]")
        # CP spent and Breakdown Points accrued this OpStage only ever rise from zero and
        # reset to zero each turn (apply, TURN_ADVANCED) -- neither is ever a debt (21.25).
        if u.cp_used < 0:
            raise InvariantViolation(f"unit {u.id} has negative cp_used {u.cp_used}")
        if u.bp_accumulated < 0:
            raise InvariantViolation(f"unit {u.id} has negative bp_accumulated {u.bp_accumulated}")

    for su in state.supplies:                      # dumps relocate now (rule 32.3)
        if not state.terrain.exists(su.hex):
            raise InvariantViolation(f"supply {su.id} on non-existent hex {su.hex}")

    # Supply pools are physical quantities (rule 32): no dump or truck may hold a
    # NEGATIVE amount of any commodity. Conservation alone is blind to an over-drain --
    # `consumed` rises by exactly what a pool sinks below zero, so the on-hand + consumed
    # identity still balances -- so guard the pools directly and fail loud.
    for su in state.supplies:
        for commodity in supply.COMMODITIES:
            qty = getattr(su, commodity.lower())
            if qty < 0:
                raise InvariantViolation(
                    f"supply {su.id} has negative {commodity} pool {qty}")
    for t in state.trucks:
        for commodity in supply.COMMODITIES:
            qty = getattr(t, commodity.lower())
            if qty < 0:
                raise InvariantViolation(
                    f"truck {t.id} has negative {commodity} cargo {qty}")

    # No id may repeat across units, supplies, and trucks. apply() resolves an event's
    # target by id to the FIRST match, so a duplicate silently corrupts the wrong entity --
    # a re-founded rail dump did exactly this once (engine._rail_station), and the second
    # Supply Unit with the same id double-counted its pool 299 points over initial.
    seen_ids: set[str] = set()
    for entity in chain(state.units, state.supplies, state.trucks):
        if entity.id in seen_ids:
            raise InvariantViolation(
                f"duplicate entity id {entity.id!r} across units/supplies/trucks")
        seen_ids.add(entity.id)

    # A port's Efficiency Level is bounded by its assigned maximum (55.12): bomb damage
    # (engine._air_port) floors it at 0, regeneration (55.18) ceils it at max_eff - blocked.
    for p in state.ports:
        if not 0 <= p.eff <= p.max_eff:
            raise InvariantViolation(
                f"port {p.id} eff={p.eff} out of [0, max_eff={p.max_eff}]")

    # A fortification level is a physical wall height (15.82): siege artillery (25.14)
    # batters it DOWN but never below razed ground.
    for coord, level in state.fort_levels.items():
        if level < 0:
            raise InvariantViolation(f"fort level {level} at {coord} is negative")

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
