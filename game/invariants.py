"""Property checks run after every applied event (brief §7).

A violation means the engine misencoded a rule — the project's biggest risk — so
we fail loud rather than continue "confidently wrong for 111 turns".

TWO ENTRY POINTS, ONE SET OF PREDICATES.

  * ``check(state)`` is the COMPLETE O(state) sweep. Its behaviour and raise-order are
    byte-identical to the historic single-pass check.
  * ``check_event(pre, post, event)`` is the INCREMENTAL checker the engine runs after
    every applied event: each ``EventKind`` touches a statically-known slice, so it
    validates only that slice (the touched unit's steps/hex/broken bounds, the touched
    supply/truck pools + the destination hex stack, and conservation of THAT change),
    and it retains the full ``check`` sweep at the OpStage/turn boundaries
    (STAGE_ADVANCED / TURN_ADVANCED) and at run start (GAME_INITIALIZED) as the global
    backstop -- which bounds any cross-slice violation the per-slice checks cannot see to
    a single Operations Stage.

Both call the SAME per-slice guards below, so the incremental path can never disagree
with the full sweep about what "legal" means. The checks are read-only, so the event log
is byte-identical whichever entry point runs; the per-EventKind equivalence and fault-
injection tests (tests/test_invariants_delta.py) pin that the slicing is coverage-
preserving -- the one thing the byte-identity harness cannot see.
"""
from __future__ import annotations

from itertools import chain

from . import adjudication, air, malta, stacking, supply
from .events import Event, EventKind, Side
from .state import GameState


class InvariantViolation(Exception):
    pass


# The commodity field names are fixed (supply.COMMODITIES); precompute the lowercased
# attribute names once rather than re-lowering the same four strings ~6.8M times a campaign.
_COMMODITY_ATTRS = tuple((c, c.lower()) for c in supply.COMMODITIES)


# --- per-slice guards --------------------------------------------------------------------
# Each guard validates the minimal slice one event can touch. They are the single source of
# truth for every property, shared verbatim by the full sweep and the incremental checker.

def _check_stage(state: GameState) -> None:
    # The Operations Stage is always one of the three within a game-turn (rule 5.1).
    if state.stage not in (1, 2, 3):
        raise InvariantViolation(f"stage {state.stage} out of the 1..3 Operations-Stage range")


def _check_unit(u, terrain) -> None:
    for s in u.steps:
        if s.strength < 0:
            raise InvariantViolation(
                f"unit {u.id} step {s.label!r} has negative strength {s.strength}")
    if not terrain.exists(u.hex):
        raise InvariantViolation(f"unit {u.id} on non-existent hex {u.hex}")
    # Broken-down TOE is a subset of the unit's strength (rule 21.44): it is peeled off the
    # operational pool, never below zero nor above total strength.
    if not 0 <= u.broken_down <= u.strength:
        raise InvariantViolation(
            f"unit {u.id} broken_down={u.broken_down} out of [0, {u.strength}]")
    # CP spent and Breakdown Points accrued this OpStage only ever rise from zero and reset to
    # zero each turn (apply, TURN_ADVANCED) -- neither is ever a debt (21.25).
    if u.cp_used < 0:
        raise InvariantViolation(f"unit {u.id} has negative cp_used {u.cp_used}")
    if u.bp_accumulated < 0:
        raise InvariantViolation(f"unit {u.id} has negative bp_accumulated {u.bp_accumulated}")


def _check_supply_hex(su, terrain) -> None:
    if not terrain.exists(su.hex):                 # dumps relocate now (rule 32.3)
        raise InvariantViolation(f"supply {su.id} on non-existent hex {su.hex}")


def _check_supply_pools(su) -> None:
    # Supply pools are physical quantities (rule 32): no dump may hold a NEGATIVE amount of any
    # commodity. Conservation alone is blind to an over-drain -- `consumed` rises by exactly what
    # a pool sinks below zero, so the on-hand + consumed identity still balances -- so guard the
    # pools directly and fail loud.
    for commodity, attr in _COMMODITY_ATTRS:
        qty = getattr(su, attr)
        if qty < 0:
            raise InvariantViolation(f"supply {su.id} has negative {commodity} pool {qty}")


def _check_truck_pools(t) -> None:
    for commodity, attr in _COMMODITY_ATTRS:
        qty = getattr(t, attr)
        if qty < 0:
            raise InvariantViolation(f"truck {t.id} has negative {commodity} cargo {qty}")


def _check_port(p) -> None:
    # A port's Efficiency Level is bounded by its assigned maximum (55.12): bomb damage
    # (engine._air_port) floors it at 0, regeneration (55.18) ceils it at max_eff - blocked.
    if not 0 <= p.eff <= p.max_eff:
        raise InvariantViolation(f"port {p.id} eff={p.eff} out of [0, max_eff={p.max_eff}]")


def _check_air_facility(f) -> None:
    # [36.14] A facility's Capacity Level is bounded by its charted maximum (36.12 six / 36.2 one /
    # 36.3 three / 36.4 one): bombing floors it at 0 ("reduced to zero capacity... considered
    # destroyed for all purposes") and 24.76's level-by-level rebuild ceils it at the maximum. The
    # exact twin of the Port Efficiency-Level guard above.
    if not 0 <= f.level <= f.max_level:
        raise InvariantViolation(
            f"air facility {f.id} level={f.level} out of [0, max_level={f.max_level}]")


def _check_squadron_unfit(state: GameState, squadron: str, unfit: int) -> None:
    # [38.31] A squadron's unrefitted planes are a count of REAL AEROPLANES out of its own
    # establishment: never negative, never more machines than the squadron has. The exact twin of
    # the Port Efficiency and Capacity-Level guards -- a stock with two hard ends.
    side_value, arena, role = squadron.split("/")
    total = air.squadron_planes(state, Side(side_value), arena, role)
    if not 0 <= unfit <= total:
        raise InvariantViolation(
            f"squadron {squadron} unfit={unfit} out of [0, planes={total}]")


def _check_malta_unfit(state: GameState) -> None:
    # [38.31] via [44.16] Malta's unrefitted aeroplanes are a count of REAL machines out of the
    # island's own anti-shipping arm: never negative, never more than are standing on the island.
    # The exact twin of _check_squadron_unfit, for the one air force with no squadron key -- and
    # it is what holds the ledger honest across 41.36, which kills planes the ledger stands for.
    total = malta.strike_establishment(state)
    if not 0 <= state.malta_unfit <= total:
        raise InvariantViolation(
            f"Malta unfit={state.malta_unfit} out of [0, strike planes={total}]")


def _check_fort(coord, level: int) -> None:
    # A fortification level is a physical wall height (15.82): siege artillery (25.14) batters it
    # DOWN but never below razed ground.
    if level < 0:
        raise InvariantViolation(f"fort level {level} at {coord} is negative")


def _check_stack_at(state: GameState, coord) -> None:
    # Stacking limit, checked at rest (rule 9.31): no hex over its point limit. The detection
    # lives in stacking.within_hex_limit (single source of truth); on-map units at the hex count
    # together, matching adjudication.stacking_violations.
    units = state.units_at(coord)
    terrain = state.terrain.terrain[coord]
    if not stacking.within_hex_limit(units, terrain):
        pts = stacking.hex_points(units, terrain)
        raise InvariantViolation(
            f"stacking exceeded at {coord}: {pts} points "
            f"(limit {stacking.DEFAULT_HEX_LIMIT})")


def _check_no_dup_ids(state: GameState) -> None:
    # No id may repeat across units, supplies, and trucks. apply() resolves an event's target by
    # id to the FIRST match, so a duplicate silently corrupts the wrong entity -- a re-founded rail
    # dump did exactly this once (engine._rail_station), and the second Supply Unit with the same
    # id double-counted its pool 299 points over initial.
    seen_ids: set[str] = set()
    for entity in chain(state.units, state.supplies, state.trucks):
        if entity.id in seen_ids:
            raise InvariantViolation(
                f"duplicate entity id {entity.id!r} across units/supplies/trucks")
        seen_ids.add(entity.id)


def _check_conservation_full(state: GameState) -> None:
    # Supply conservation (rule 32): per commodity, on-hand + consumed == initial. Nothing is
    # created except at sources; nothing vanishes except defined consumption. on-hand sums the
    # dumps, any cargo riding on truck convoys (rules 53-54), AND the units' own supply pools (the
    # 49.14 fuel tanks + 53.11 first-line loads, Phase 4 Option B) -- a unit carries supply exactly
    # as a truck does, so unit pools are the third on-hand surface, credited into initial at t0
    # (scenario._initial_supply) and never minted at runtime.
    for commodity, initial in state.initial_supply.items():
        attr = commodity.lower()
        on_hand = (sum(getattr(su, attr) for su in state.supplies)
                   + sum(getattr(t, attr) for t in state.trucks)
                   + sum(getattr(u, attr) for u in state.units))
        if on_hand + state.consumed.get(commodity, 0) != initial:
            raise InvariantViolation(
                f"{commodity} not conserved: on_hand={on_hand} + "
                f"consumed={state.consumed.get(commodity, 0)} != initial={initial}")


def _check_conservation_delta(pre: GameState, post: GameState, event: Event,
                              dump_ids: tuple, truck_ids: tuple, unit_ids: tuple) -> None:
    """Incremental conservation: given the identity held BEFORE the event (the inductive base a
    prior check or the last boundary sweep established), it still holds AFTER iff the event's net
    change to (on_hand + consumed - initial) is zero, per commodity. on_hand's change is read from
    the ACTUAL touched pools (post minus pre) -- dumps, truck convoys, AND units (the 49.14/53.11
    Phase-4 pools); consumed/initial's change from the accounting dicts apply() maintains -- so a
    fold that drains the wrong amount, or credits the wrong ledger, makes the two disagree and fails
    loud here, no O(state) re-sum needed."""
    for commodity, attr in _COMMODITY_ATTRS:
        d_on_hand = 0
        for sid in dump_ids:
            old = pre.supply(sid)
            d_on_hand += getattr(post.supply(sid), attr) - (getattr(old, attr) if old else 0)
        for tid in truck_ids:
            old = pre.truck(tid)
            d_on_hand += getattr(post.truck(tid), attr) - (getattr(old, attr) if old else 0)
        for uid in unit_ids:
            old = pre.unit(uid)
            d_on_hand += getattr(post.unit(uid), attr) - (getattr(old, attr) if old else 0)
        d_consumed = post.consumed.get(commodity, 0) - pre.consumed.get(commodity, 0)
        d_initial = post.initial_supply.get(commodity, 0) - pre.initial_supply.get(commodity, 0)
        if d_on_hand + d_consumed - d_initial != 0:
            raise InvariantViolation(
                f"{commodity} not conserved across {event.kind.value}: d_on_hand={d_on_hand} + "
                f"d_consumed={d_consumed} != d_initial={d_initial}")


# --- the full sweep ----------------------------------------------------------------------

def check(state: GameState) -> None:
    """The COMPLETE O(state) sweep. Behaviour and raise-order are byte-identical to the historic
    single-pass check; check_event runs the same guards incrementally between boundaries and calls
    this one at each boundary as the backstop."""
    _check_stage(state)
    for u in state.units:
        _check_unit(u, state.terrain)
    for su in state.supplies:
        _check_supply_hex(su, state.terrain)
    for su in state.supplies:
        _check_supply_pools(su)
    for t in state.trucks:
        _check_truck_pools(t)
    _check_no_dup_ids(state)
    for p in state.ports:
        _check_port(p)
    for f in state.air_facilities:
        _check_air_facility(f)
    for squadron, unfit in state.air_unfit.items():
        _check_squadron_unfit(state, squadron, unfit)
    _check_malta_unfit(state)
    for coord, level in state.fort_levels.items():
        _check_fort(coord, level)
    for c in adjudication.stacking_violations(state):
        _check_stack_at(state, c.hex)              # raise on the first, preserving raise-order
    _check_conservation_full(state)


# --- the incremental checker -------------------------------------------------------------
# The full sweep runs at run start and at every OpStage/turn boundary; between boundaries only
# the touched slice is validated. apply() is the ONLY state mutator and events are its only
# input, so a guard nothing in the event could have moved cannot have broken.

# Boundaries: the fold that opens a new Operations Stage (or the game) resets per-stage counters
# and can bring reinforcements on-map (turn >= arrival_turn), so a full audit here re-establishes
# the inductive base and catches any cross-slice drift within one OpStage.
_BOUNDARY_KINDS = frozenset({
    EventKind.GAME_INITIALIZED, EventKind.STAGE_ADVANCED, EventKind.TURN_ADVANCED})

# Events that relocate a unit (p["unit_id"] -> p["to"]): check the unit AND its destination stack.
_UNIT_MOVE_KINDS = frozenset({
    EventKind.UNIT_MOVED, EventKind.REACTION_MOVED, EventKind.UNIT_RETREATED})

# Events that touch one unit by p["unit_id"] without moving it: check that unit only.
_UNIT_KINDS = frozenset({
    EventKind.RESERVE_DESIGNATED, EventKind.RESERVE_FLIPPED, EventKind.RESERVE_RELEASED,
    EventKind.BREAKDOWN_CHECKED, EventKind.VEHICLE_BROKE_DOWN, EventKind.VEHICLE_REPAIRED,
    EventKind.STEP_LOST, EventKind.CP_EXPENDED, EventKind.COHESION_CHANGED,
    EventKind.STORES_SHORTFALL, EventKind.WATER_SHORTFALL, EventKind.STORES_RESTORED,
    EventKind.WATER_RESTORED, EventKind.REINFORCEMENT_DELAYED,
    EventKind.SGSU_SUPPLIED, EventKind.SGSU_UNSUPPLIED,         # 35.14 the SGSU upkeep counter
    EventKind.UNIT_REFILLED, EventKind.UNIT_SUPPLY_CONSUMED})   # Phase 4 unit pools

# Events that change a dump's pools or hex, resolved by p["supply_id"].
_DUMP_ID_KINDS = frozenset({
    EventKind.SUPPLY_EVAPORATED, EventKind.WELL_REFILLED, EventKind.SUPPLY_DUMP_BLOWN,
    EventKind.SUPPLY_ARRIVED, EventKind.SUPPLY_CAPTURED, EventKind.SUPPLY_CONSUMED,
    EventKind.SUPPLY_DUMP_ESTABLISHED, EventKind.SUPPLY_DUMP_CONSTRUCTED, EventKind.SUPPLY_MOVED,
    EventKind.TRUCK_LOADED, EventKind.TRUCK_UNLOADED,
    EventKind.UNIT_REFILLED})       # 48 V.C.6 dump->unit top-up drains a dump (Phase 4)

# Events that change a truck's cargo, resolved by p["truck_id"].
_TRUCK_ID_KINDS = frozenset({
    EventKind.TRUCK_LOADED, EventKind.TRUCK_UNLOADED, EventKind.TRUCK_EVAPORATED,
    EventKind.TRUCK_MOVED})

# Events that move supply between pools / the ledger: conservation of the change is checked.
_CONSERVATION_KINDS = frozenset({
    EventKind.SUPPLY_EVAPORATED, EventKind.TRUCK_EVAPORATED, EventKind.WELL_REFILLED,
    EventKind.SUPPLY_DUMP_BLOWN, EventKind.SUPPLY_ARRIVED, EventKind.SUPPLY_CAPTURED,
    EventKind.SUPPLY_CONSUMED, EventKind.TRUCK_LOADED, EventKind.TRUCK_UNLOADED,
    EventKind.TRUCK_MOVED, EventKind.RAIL_HAULED, EventKind.SUPPLY_DUMP_ESTABLISHED,
    EventKind.UNIT_REFILLED, EventKind.UNIT_SUPPLY_CONSUMED})    # Phase 4 unit-pool moves


def _touched_dumps(event: Event) -> tuple:
    if event.kind in _DUMP_ID_KINDS:
        return (event.payload["supply_id"],)
    if event.kind == EventKind.RAIL_HAULED:
        return (event.payload["from_dump"], event.payload["to_dump"])
    return ()


def _touched_trucks(event: Event) -> tuple:
    if event.kind in _TRUCK_ID_KINDS:
        return (event.payload["truck_id"],)
    return ()


def _touched_units(event: Event) -> tuple:
    # Phase 4: the unit is a conservation surface for the events that move supply into or out of its
    # own pools (49.14 tank / 53.11 first-line load) -- UNIT_REFILLED (dump -> unit) and
    # UNIT_SUPPLY_CONSUMED (unit -> consumed).
    if event.kind in (EventKind.UNIT_REFILLED, EventKind.UNIT_SUPPLY_CONSUMED):
        return (event.payload["unit_id"],)
    return ()


def check_event(pre: GameState, post: GameState, event: Event) -> None:
    """Validate the slice `event` touched (see module docstring). Pure function of (pre, post,
    event): it holds no state between calls, so it replays trivially in the equivalence test."""
    kind = event.kind
    if kind in _BOUNDARY_KINDS:
        check(post)                                # the global backstop
        return

    _check_stage(post)                             # O(1) tripwire on every event
    p = event.payload

    # --- unit slice ---
    if kind in _UNIT_MOVE_KINDS:
        _check_unit(post.unit(p["unit_id"]), post.terrain)
        _check_stack_at(post, tuple(p["to"]))
    elif kind in _UNIT_KINDS:
        _check_unit(post.unit(p["unit_id"]), post.terrain)
    # COMBAT_RESOLVED folds only the 15.81 Engaged marker (no guarded field), so nothing to check.

    # --- supply / truck / unit-pool slice ---
    dump_ids = _touched_dumps(event)
    truck_ids = _touched_trucks(event)
    unit_ids = _touched_units(event)
    for sid in dump_ids:
        su = post.supply(sid)
        _check_supply_hex(su, post.terrain)
        _check_supply_pools(su)
    for tid in truck_ids:
        _check_truck_pools(post.truck(tid))
    if kind in _CONSERVATION_KINDS:
        _check_conservation_delta(pre, post, event, dump_ids, truck_ids, unit_ids)
    if kind == EventKind.SUPPLY_DUMP_ESTABLISHED:  # the one fold that mints a new entity id
        _check_no_dup_ids(post)

    # --- port / fort slice ---
    if kind == EventKind.PORT_EFFICIENCY_CHANGED:
        _check_port(post.port(p["port_id"]))
    elif kind == EventKind.AIR_FACILITY_LEVEL_CHANGED:      # 36.14: 0 <= level <= the charted max
        _check_air_facility(post.air_facility(p["facility_id"]))
    elif kind in (EventKind.AIR_SQUADRON_UNFIT, EventKind.AIR_REFIT_RESOLVED):
        _check_squadron_unfit(post, p["squadron"], post.air_unfit.get(p["squadron"], 0))
    elif kind in (EventKind.MALTA_STRIKE_UNFIT, EventKind.MALTA_REFIT_RESOLVED,
                  EventKind.MALTA_PLANES_LOST):
        _check_malta_unfit(post)
    elif kind == EventKind.FORT_REDUCED:
        _check_fort(tuple(p["hex"]), p["level"])
