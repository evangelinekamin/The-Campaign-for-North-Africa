"""Structural adjudication dry-run (the future Chief's conflict detector).

The Chief must resolve ENGINE-DETECTED conflicts, never rubber-stamp. This module
is the pure, additive substrate it calls: given a COMBINED batch of proposed
orders, it reports the structural conflicts the batch would create -- conflicts
that the per-order engine boundary can miss because each order is legal in
isolation but they collide once folded together (two stacks onto one hex; two
draws draining one dump).

PURE + ADDITIVE: nothing here changes gameplay. validate_batch never touches the
real state -- it folds the batch onto a COPY via the pure apply (game.apply) and
inspects that. stacking_violations is the single source of truth for the resting
stacking check (game.invariants delegates to it).

A Conflict is shaped to populate a STAFF_ADJUDICATION payload verbatim: its
`kind` is exactly the `conflict` enum in game.staff_events; the Chief fills the
`favored` / `denied` / `ruling` fields when it rules.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import stacking, supply
from .apply import fold
from .events import Event, EventKind
from .hexmap import Coord
from .policy import MoveOrder, SupplyMoveOrder
from .state import GameState


@dataclass(frozen=True, slots=True)
class Conflict:
    """One structural collision in a batch. `kind` is the STAFF_ADJUDICATION
    `conflict` enum verbatim; `approximate` marks a v1 heuristic (road-cap)."""
    kind: str                          # "over-stack" | "oversubscribed-dump" | "road-cap"
    hex: Coord
    unit_ids: tuple[str, ...] = ()
    dump_id: str | None = None
    approximate: bool = False          # road-cap is a destination proxy (rule 9.33)


def stacking_violations(state: GameState) -> list[Conflict]:
    """Hexes whose at-rest stacking exceeds the limit (rule 9.31), in unit order --
    the single source of truth for the stacking check (game.invariants raises on the
    first; validate_batch collects them all). All on-map units at a hex count
    together, matching the historic invariant."""
    occupied: dict[Coord, list] = {}
    for u in state.units:
        if state.on_map(u):                        # off-map reinforcements don't stack yet
            occupied.setdefault(u.hex, []).append(u)
    out: list[Conflict] = []
    for coord, units in occupied.items():
        terrain = state.terrain.terrain[coord]
        if not stacking.within_hex_limit(units, terrain):
            out.append(Conflict("over-stack", coord, tuple(u.id for u in units)))
    return out


def validate_batch(state: GameState, orders: list) -> list[Conflict]:
    """The Chief's dry-run: the structural conflicts a COMBINED batch would create.

    Move/supply orders are folded onto a COPY of state (via the pure apply) so the
    real state is never mutated; the resulting board is inspected for over-stacks
    and (as a rule-9.33 destination approximation) road-cap breaches. Oversubscribed
    dumps are read from the base-state fuel draws the batch would issue."""
    moved = fold(state, _order_events(state, orders))
    return (stacking_violations(moved)
            + _oversubscribed_dumps(state, orders)
            + _road_cap_violations(moved, orders))


def _order_events(state: GameState, orders: list) -> list[Event]:
    """Synthesize the minimal position-changing events for a batch, so the copy is
    produced by the one canonical fold. Unknown ids are skipped (nothing to move)."""
    events: list[Event] = []
    for o in orders:
        if isinstance(o, MoveOrder):
            u = state.unit(o.unit_id)
            if u is not None:
                events.append(_event(state, EventKind.UNIT_MOVED, {
                    "unit_id": o.unit_id, "from": list(u.hex),
                    "to": list(o.to), "cp_spent": 0.0}))
        elif isinstance(o, SupplyMoveOrder):
            su = state.supply(o.supply_id)
            if su is not None:
                events.append(_event(state, EventKind.SUPPLY_MOVED, {
                    "supply_id": o.supply_id, "from": list(su.hex), "to": list(o.to)}))
    return events


def _event(state: GameState, kind: EventKind, payload: dict) -> Event:
    return Event(0, state.turn, state.phase, state.active_side, "ADJUDICATION",
                 kind, payload)


def _oversubscribed_dumps(state: GameState, orders: list) -> list[Conflict]:
    """Dumps whose combined fuel draws across the batch exceed their pool. Each
    first-move order draws fuel from the nearest reachable dumps (rule 32.23); read
    on the base state (undepleted), so two orders both landing on one dump surface
    the oversubscription the sequential engine would only hit on the second."""
    drawn: dict[str, int] = {}
    drawers: dict[str, list[str]] = {}
    for o in orders:
        if not isinstance(o, MoveOrder):
            continue
        u = state.unit(o.unit_id)
        if u is None or u.cp_used != 0:            # only the first move pays fuel (32.23)
            continue
        plan = supply.plan_draw(state, u, supply.FUEL, supply.fuel_rate(u))
        if not plan:
            continue
        for sid, qty in plan:
            drawn[sid] = drawn.get(sid, 0) + qty
            drawers.setdefault(sid, []).append(u.id)
    out: list[Conflict] = []
    for sid, total in drawn.items():
        dump = state.supply(sid)
        if dump is not None and total > dump.fuel:
            out.append(Conflict("oversubscribed-dump", dump.hex,
                                tuple(drawers[sid]), dump_id=sid))
    return out


def _road_cap_violations(moved: GameState, orders: list) -> list[Conflict]:
    """Destinations receiving movers whose stack breaches the 5-point road/track
    limit (rule 9.33). v1 DESTINATION APPROXIMATION: the real cap is on units moving
    ALONG a road track, not the hex they rest in -- flagged approximate."""
    dests = dict.fromkeys(o.to for o in orders if isinstance(o, MoveOrder))
    out: list[Conflict] = []
    for coord in dests:
        units = moved.units_at(coord)
        if not stacking.within_road_track_limit(units):
            out.append(Conflict("road-cap", coord, tuple(u.id for u in units),
                                approximate=True))
    return out
