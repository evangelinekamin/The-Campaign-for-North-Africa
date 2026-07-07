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
from .terrain import Mobility


def other(side: Side) -> Side:
    return Side.ALLIED if side == Side.AXIS else Side.AXIS


def effective_cpa(state: GameState, unit: Unit) -> int:
    """A unit's Capability Point Allowance for THIS Operations Stage, with General Rommel's
    31.4 +5: the leader grants +5 CPA to a unit he started the stage with and never left --
    modelled as membership of the OpStage-boundary companion snapshot (rule 31 / ROMMEL_
    ANCHORED) AND the unit still standing on the anchor hex AND Rommel not having moved off it
    (unit.hex == anchor_hex == rommel.hex). Byte-identical to unit.cpa whenever no Rommel is
    on the board, so every non-Rommel scenario is untouched."""
    r = state.rommel
    if (r is not None and not r.in_germany and unit.id in r.companions
            and unit.hex == r.anchor_hex == r.hex):
        return unit.cpa + 5
    return unit.cpa


def rommel_reach(state: GameState) -> dict[Coord, float]:
    """31.1: General Rommel's leader-movement reach -- a 60-MP 'four-wheel-drive medium truck'
    (31.1 / 27.14) that IGNORES enemy Zones of Control (31.2 impunity) and stacking (he is off
    units[], carries no ZOC and can be blocked by no one). A deliberately simplified BFS: the
    standard motorized terrain search with every enemy/friendly interaction switched off and no
    break-off cost, so the only limits are terrain and the 60-CP budget under the day's weather."""
    r = state.rommel
    return zoc.reachable_with_zoc(
        state.terrain, r.hex, 60.0, Mobility.MOTORIZED,
        enemy_zoc=frozenset(), friendly_negators=frozenset(),
        enemy_occupied=frozenset(), break_off=0.0, weather=state.weather)


def _cp_ceiling(cpa: int, reserve_released: int = 0) -> float:
    """The voluntary-movement CP ceiling (rule 8.16/8.17). A non-motorized unit (CPA of ten
    or less, 8.17) may never voluntarily spend more than 150% of its CPA in its portion of an
    Operations Stage. A motorized unit (CPA > 10) has NO rule ceiling (8.16 -- it may exceed
    its CPA, paying Disorganization by 6.21); a 2x-CPA soft bound only terminates the
    reachability search and never clips an affordable legal destination. Reaction / Retreat
    Before Assault (not voluntary) are re-bounded by their own 13.23/13.24 caps downstream.
    Takes the (Rommel-)effective CPA so the 31.4 +5 widens the reach uniformly.

    A unit RELEASED from Reserve this stage carries a tighter voluntary ceiling that overrides
    the ordinary 8.16/8.17 one:
      * released from Reserve I (reserve_released == 1, rule 18.23-1) may NOT voluntarily exceed
        its CPA -- ceiling 1.0x CPA (no motorized 2x, no non-motorized 1.5x surplus);
      * released from Reserve II (reserve_released == 2, rule 18.24-1) is capped at ONE-HALF its
        CPA, rounded down (a CPA-9 unit gets 4, not 4.5; a CPA-10 unit gets 5).
    FLAGGED (not yet wired): the companion 18.23-2 / 18.24-2 "one offensive Close Assault (or
    Probe) only" limit and the 18.24-3 "+1 Disorganization Point if it fights" surcharge are
    per-STAGE restrictions that need a released-this-stage assault ledger; deferred."""
    if reserve_released == 1:
        return float(cpa)
    if reserve_released == 2:
        return float(cpa // 2)
    return cpa * (1.5 if cpa <= 10 else 2.0)


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


def enemy_zoc_excluding(state: GameState, mover_side: Side, exclude_id: str) -> frozenset:
    """The enemy Zone of Control as seen by `mover_side`, projected by every enemy combat unit
    EXCEPT `exclude_id`. The 8.53c Reaction eligibility test uses this so a unit that the trigger
    mover has JUST moved adjacent to is not read as 'already in an enemy ZOC' by that same mover --
    only a pre-existing pin from some OTHER enemy unit disqualifies the reaction."""
    enemy = other(mover_side)
    by_hex: dict[Coord, list[Unit]] = {}
    for u in state.living(enemy):
        if u.is_combat and u.id != exclude_id:
            by_hex.setdefault(u.hex, []).append(u)
    return zoc.control_map(by_hex, state.terrain)


def reachable_for(state: GameState, unit: Unit, enemy_zoc: frozenset,
                  enemy_occupied: frozenset, roster: tuple | None = None) -> dict[Coord, float]:
    """Hexes `unit` can legally reach this segment within its remaining CPA. Pass a
    `roster` (the friendly units snapshotted at phase start) so a unit's legal set
    is computed against the phase-start board -- otherwise ZOC-negation shifts as
    earlier units move and the observation ends up offering hexes the engine then
    rejects (the observation/validation must agree on ONE snapshot)."""
    budget = max(0.0, _cp_ceiling(effective_cpa(state, unit), unit.reserve_released)
                 - unit.cp_used)                                     # 8.17 ceiling (+31.4, +18.24)
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
    budget = max(0.0, _cp_ceiling(effective_cpa(state, unit), unit.reserve_released)
                 - unit.cp_used)                                     # 8.17 ceiling (+31.4, +18.24)
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
