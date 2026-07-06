"""Shared tactical glue between the engine (authority) and policies (deciders).

Both need the same view of "where can this unit legally move, given enemy ZOC".
Keeping it here (importing state + zoc, imported by engine + policy) avoids an
engine<->policy import cycle and guarantees decider and validator agree.
"""
from __future__ import annotations

from . import cp_costs, movement, zoc
from .events import Side
from .hexmap import Coord
from .state import GameState, Unit


def other(side: Side) -> Side:
    return Side.ALLIED if side == Side.AXIS else Side.AXIS


def _break_off_cost(unit: Unit) -> float:
    """The CP a unit pays to LEAVE an enemy ZOC it starts in (rule 6.3): Disengage = 4
    while it carries the 15.81 Engaged marker (it was in a Close Assault this stage),
    else Break Contact = 2. Sourced from the 6.3 chart-of-record (game.cp_costs)."""
    return float(cp_costs.disengage_cost() if unit.engaged else cp_costs.break_contact_cost())


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
    budget = max(0.0, unit.cpa - unit.cp_used)
    src = roster if roster is not None else state.living(unit.side)
    negators = frozenset(u.hex for u in src if u.is_combat and u.id != unit.id)  # §10.26
    return zoc.reachable_with_zoc(
        state.terrain, unit.hex, budget, unit.mobility,
        enemy_zoc=enemy_zoc, friendly_negators=negators, enemy_occupied=enemy_occupied,
        break_off=_break_off_cost(unit), weather=state.weather)


def reachable_for_prev(state: GameState, unit: Unit, enemy_zoc: frozenset,
                       enemy_occupied: frozenset,
                       roster: tuple | None = None) -> tuple[dict[Coord, float], dict]:
    """`reachable_for`, additionally returning the Dijkstra predecessor map so a mover's
    actual ZOC-legal path can be reconstructed for Breakdown-Point accrual (21.21)."""
    budget = max(0.0, unit.cpa - unit.cp_used)
    src = roster if roster is not None else state.living(unit.side)
    negators = frozenset(u.hex for u in src if u.is_combat and u.id != unit.id)  # §10.26
    return zoc.reachable_with_zoc_prev(
        state.terrain, unit.hex, budget, unit.mobility,
        enemy_zoc=enemy_zoc, friendly_negators=negators, enemy_occupied=enemy_occupied,
        break_off=_break_off_cost(unit), weather=state.weather)


def breakdown_points_over(state: GameState, unit: Unit, path: list[Coord]) -> float:
    """Total Breakdown Points a vehicle accrues traversing `path` (rule 21.21/21.23),
    under the current weather. Zero for a non-vehicle (21.11), so a bp of 0 is omitted
    from the move event and non-vehicle scenarios stay byte-identical."""
    if not unit.breaks_down or len(path) < 2:
        return 0.0
    return sum(movement.breakdown_points(state.terrain, a, b, unit.mobility, state.weather)
               for a, b in zip(path, path[1:]))


def bp_for_move(state: GameState, unit: Unit, prev: dict, dst: Coord) -> float:
    """Breakdown Points for a move to `dst`, reconstructing the min-CP path from a
    predecessor map (reachable_for_prev). The engine passes this straight into the
    UNIT_MOVED faucet."""
    path = movement.reconstruct_path(prev, unit.hex, dst)
    return breakdown_points_over(state, unit, path)
