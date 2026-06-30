"""Decision layer (brief §4.5, §8).

Phase 0 uses a *scripted* (non-LLM) policy so the engine is proven before any
token is spent. In Phase 1 an LLMPolicy with the same interface drops in,
receiving role-scoped observations and emitting the same Orders, which the engine
validates identically. The scripted policy may read full state and uses the same
tactical reachability the engine validates against (game.tactics).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import stacking, tactics
from .events import Side
from .hexmap import Coord, distance, neighbors
from .state import GameState, Unit


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
    """Simple desert doctrine: the attacker presses toward the objective along the
    cheapest legal path; the defender holds and counter-attacks anything adjacent.
    Proposals are pre-filtered for legality, but the engine re-validates."""

    def __init__(self, attacker: Side = Side.AXIS):
        self.attacker = attacker

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        if side != self.attacker:
            return []  # defender holds the line
        enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
        target = state.target_hex
        orders: list[MoveOrder] = []
        for u in state.living(side):
            if not u.is_combat:
                continue
            reach = tactics.reachable_for(state, u, enemy_zoc, enemy_occupied)
            here_dist = distance(u.hex, target)
            candidates = [
                c for c in reach
                if c != u.hex
                and distance(c, target) < here_dist          # only advance toward objective
                and self._stacking_ok(state, u, c)
            ]
            if candidates:
                dest = min(candidates, key=lambda c: (distance(c, target), reach[c], c))
                orders.append(MoveOrder(u.id, dest))
        return orders

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        # Batch attackers by the hex they assault — one resolved call per target.
        by_target: dict[Coord, list[str]] = {}
        for u in state.living(side):
            if not u.is_combat:
                continue
            for nb in neighbors(u.hex):
                if state.enemies_at(nb, side):
                    by_target.setdefault(nb, []).append(u.id)
        return [AttackOrder(tuple(ids), tgt) for tgt, ids in by_target.items()]

    def _stacking_ok(self, state: GameState, unit: Unit, dest: Coord) -> bool:
        present = [u for u in state.units_at(dest) if u.side == unit.side]
        return stacking.within_hex_limit(present + [unit], state.terrain.terrain[dest])
