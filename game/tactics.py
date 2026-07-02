"""Shared tactical glue between the engine (authority) and policies (deciders).

Both need the same view of "where can this unit legally move, given enemy ZOC".
Keeping it here (importing state + zoc, imported by engine + policy) avoids an
engine<->policy import cycle and guarantees decider and validator agree.
"""
from __future__ import annotations

from . import zoc
from .events import Side
from .hexmap import Coord
from .state import GameState, Unit


def other(side: Side) -> Side:
    return Side.ALLIED if side == Side.AXIS else Side.AXIS


def enemy_zoc_and_occupied(state: GameState, mover_side: Side) -> tuple[frozenset, frozenset]:
    enemy = other(mover_side)
    by_hex: dict[Coord, list[Unit]] = {}
    for u in state.living(enemy):
        if u.is_combat:
            by_hex.setdefault(u.hex, []).append(u)
    enemy_zoc = zoc.control_map(by_hex, state.terrain)
    enemy_occupied = frozenset(u.hex for u in state.living(enemy))
    return enemy_zoc, enemy_occupied


def reachable_for(state: GameState, unit: Unit, enemy_zoc: frozenset,
                  enemy_occupied: frozenset, roster: tuple | None = None) -> dict[Coord, float]:
    """Hexes `unit` can legally reach this segment within its remaining CPA. Pass a
    `roster` (the friendly units snapshotted at phase start) so a unit's legal set
    is computed against the phase-start board -- otherwise ZOC-negation shifts as
    earlier units move and the observation ends up offering hexes the engine then
    rejects (the observation/validation must agree on ONE snapshot)."""
    budget = max(0.0, unit.cpa + state.move_modifier - unit.cp_used)
    src = roster if roster is not None else state.living(unit.side)
    negators = frozenset(u.hex for u in src if u.is_combat and u.id != unit.id)  # §10.26
    return zoc.reachable_with_zoc(
        state.terrain, unit.hex, budget, unit.mobility,
        enemy_zoc=enemy_zoc, friendly_negators=negators, enemy_occupied=enemy_occupied)
