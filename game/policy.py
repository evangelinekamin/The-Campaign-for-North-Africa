"""Decision layer (brief §4.5, §8).

In Phase 0 this is a *scripted* (non-LLM) policy — the highest-ROI, most-skipped
step: prove the engine is correct before a single token is spent. In Phase 1 an
LLMPolicy with the same interface drops in, receiving role-scoped observations
(an Observation layer slots between engine and policy then) and emitting the same
Orders, which the engine validates identically. The scripted policy is allowed
to read full state; an LLM policy will not be.
"""
from __future__ import annotations

from dataclasses import dataclass

from .events import Side
from .state import Coord, GameState, Unit, neighbors

BASE_MOVE_ALLOWANCE = 3
STACK_LIMIT = 2


@dataclass(frozen=True, slots=True)
class MoveOrder:
    unit_id: str
    to: Coord


@dataclass(frozen=True, slots=True)
class AttackOrder:
    attacker_ids: tuple[str, ...]
    target: Coord


Order = MoveOrder | AttackOrder


class Policy:
    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        raise NotImplementedError

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        raise NotImplementedError


class ScriptedPolicy(Policy):
    """A deliberately simple desert doctrine: the Axis presses east toward the
    objective; the defender (Allied) holds and counter-attacks anything that
    comes adjacent. It naively proposes the farthest legal advance — when a unit
    runs low on fuel its order is *rejected* by the engine, exercising the
    typed-rejection feedback channel even with no LLM in the loop."""

    def __init__(self, attacker: Side = Side.AXIS):
        self.attacker = attacker

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        if side != self.attacker:
            return []  # defender holds the line
        direction = 1 if state.target_hex[0] >= 0 else -1  # toy strip runs east
        orders: list[MoveOrder] = []
        for u in state.living(side):
            dest = self._advance(state, u, direction)
            if dest != u.hex:
                orders.append(MoveOrder(u.id, dest))
        return orders

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        # Batch attackers by the hex they assault — one resolved call per target
        # (brief §3.4 rule 3), not one call per unit.
        by_target: dict[Coord, list[str]] = {}
        for u in state.living(side):
            for nb in neighbors(u.hex):
                if state.enemies_at(nb, side):
                    by_target.setdefault(nb, []).append(u.id)
        return [AttackOrder(tuple(ids), tgt) for tgt, ids in by_target.items()]

    def _advance(self, state: GameState, unit: Unit, direction: int) -> Coord:
        allowance = max(0, BASE_MOVE_ALLOWANCE + state.move_modifier)
        budget = min(allowance, int(unit.fuel))
        x, y = unit.hex
        dest = unit.hex
        for _ in range(budget):
            nb = (x + direction, y)
            h = state.hex_at(nb)
            if h is None:
                break                                   # edge of map
            if state.enemies_at(nb, unit.side):
                break                                   # stop adjacent, then assault
            friendly = [u for u in state.units_at(nb) if u.side == unit.side]
            if len(friendly) >= STACK_LIMIT:
                break                                   # stacking limit
            dest, x = nb, x + direction
        return dest
