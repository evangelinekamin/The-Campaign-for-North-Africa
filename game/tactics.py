"""Shared tactical glue between the engine (authority) and policies (deciders).

Both need the same view of "where can this unit legally move, given enemy ZOC".
Keeping it here (importing state + zoc, imported by engine + policy) avoids an
engine<->policy import cycle and guarantees decider and validator agree.
"""
from __future__ import annotations

import functools
import math
from collections import OrderedDict

from . import cp_costs, minefields, movement, zoc
from .events import Side
from .hexmap import Coord
from .state import GameState, Unit
from .terrain import Mobility


def other(side: Side) -> Side:
    return Side.ALLIED if side == Side.AXIS else Side.AXIS


class _PositionMemo:
    """Bounded LRU memo for a pure function of enemy/friendly UNIT POSITIONS.

    The enemy-ZOC / trace-blocked sets are a pure function of `state.living(side)`
    (each unit's hex, combat flag and on-map status) over the static terrain, so
    they turn over ONLY when a unit moves, dies, or arrives -- and a supply/water/
    stores phase moves no unit, so the same set is asked for thousands of times per
    OpStage (measured ~99% redundant: 8,905 calls -> 58 distinct results in three
    turns). Recomputing it rebuilds the whole enemy control map every time.

    THE KEY is (id(state.units), state.turn, side). `dataclasses.replace` KEEPS the
    `state.units` tuple reference when unrelated fields (turn, weather, consumed,
    control, ...) change and REBUILDS it on any move / attrition, so id(state.units)
    is an exact, self-invalidating fingerprint of unit positions. The one input it
    misses is ARRIVAL -- a reinforcement is already in the tuple and merely becomes
    on-map when `turn` reaches its arrival_turn (state.on_map reads turn >=
    arrival_turn) -- so `turn` joins the key. Terrain is static within a run and
    never shares a units-tuple identity across runs (see below), so it needs no key.

    ID REUSE is the only failure mode of an id()-keyed cache, and it is closed by
    holding a STRONG REFERENCE to every keyed tuple for its entry's lifetime: while
    any entry for id X is live, its tuple is alive, so X cannot be reused by a
    different tuple; once all X entries are evicted the ref is dropped and a later
    tuple may take X, but then there is no X entry to hit -- so a stale hit is
    impossible by construction. Bounded to the last `maxsize` boards.

    Determinism: the value is a pure function of the key, returned by reference and
    only ever READ (frozensets, used as sets) by callers -> byte-identical log."""

    def __init__(self, compute, maxsize: int = 64) -> None:
        self._compute = compute
        self._maxsize = maxsize
        self._cache: OrderedDict = OrderedDict()
        functools.update_wrapper(self, compute)

    def __call__(self, state: GameState, side: Side):
        key = (id(state.units), state.turn, side)
        entry = self._cache.get(key)
        if entry is not None:
            self._cache.move_to_end(key)
            return entry[1]
        value = self._compute(state, side)
        self._cache[key] = (state.units, value)   # hold the tuple ref: pins its id()
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)
        return value


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


SURRENDER_FLOOR = -17     # rule 15.88 / 17.24: a unit at <= -17 auto-Surrenders when assaulted / on contact


def _overage_dp(cp_used: float, cpa: int) -> int:
    """Mirror of engine._overage_dp (6.21): Disorganization Points from CP spent over CPA. Kept
    here, not imported, to hold the decider on the policy side of the engine<->policy import
    boundary (as effective_cpa is) -- the determinism baseline catches any drift from
    engine.py:4652."""
    return max(0, math.floor(cp_used - cpa))


def voluntary_overage_dp(state: GameState, unit: Unit, cp_cost: float) -> int:
    """The 6.21 DP `unit` would NEWLY earn by voluntarily spending `cp_cost` more CP this
    Operations Stage on top of what it has already used -- exactly the increment
    engine._disorganize_overage will charge for the move (reads the live cp_used and the same
    31.4-effective CPA)."""
    cpa = effective_cpa(state, unit)
    return _overage_dp(unit.cp_used + cp_cost, cpa) - _overage_dp(unit.cp_used, cpa)


def husbands_cohesion(state: GameState, unit: Unit, cp_cost: float,
                      floor: int = SURRENDER_FLOOR) -> bool:
    """A competent commander does not VOLUNTARILY march a unit into -- or, if it is already there,
    any step further toward -- the rule-15.88 auto-surrender band. Every call site feeding this
    predicate proposes a move TOWARD the enemy or the objective, and rule 6.0/8.16 permit a
    motorized unit to exceed its CPA 'at a price' that this restraint declines to pay. True iff the
    unit's Cohesion after the predicted 6.21 overage stays strictly above `floor`:
      * a unit still above the floor keeps its full CPA-respecting move (zero overage never lowers
        Cohesion, so it always passes) and may spend as much overage as leaves it above the floor --
        a healthy unit still dashes, a merely-battered one creeps at <=1x CPA;
      * a unit ALREADY at or below the floor is held out of the forward advance entirely -- it would
        auto-surrender the instant it made the contact ahead, so a commander does not send it there;
        holding it lets 6.24 recover it in place, and the unhusbanded 10.31 retreat path still lets
        it fall back.
    A self-restraint only: the engine still prices and re-validates every move."""
    return unit.cohesion - voluntary_overage_dp(state, unit, cp_cost) > floor


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
        enemy_occupied=frozenset(), break_off=0.0, weather=state.weather_at(r.hex))


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


@_PositionMemo
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


def _mine_extra_cost(state: GameState, unit: Unit):
    """[26.21/26.22/26.24] The per-step CP hook movement._search applies outside its shared
    (mobility, weather) cache: 0 for every edge that doesn't enter a minefield hex, otherwise
    minefields.entry_surcharge read against `unit`'s own side/mobility/CPA and whatever Engineer
    escort stands at the step's ORIGIN. None (skip the hook entirely) when the board carries no
    minefield at all, so every scenario that never lays or meets one pays no extra Dijkstra work
    and stays byte-identical."""
    if not state.minefields:
        return None
    side, mobility, cpa = unit.side, unit.mobility, unit.cpa

    def extra(here: Coord, nb: Coord) -> float:
        return minefields.entry_surcharge(state, side, mobility, cpa, here, nb)
    return extra


def formation_cpa(state: GameState, unit: Unit, formation=()) -> int:
    """[6.15] The Capability Point Allowance a PARENT FORMATION moves on: "that of the lowest CPA
    of the units comprising that parent formation, regardless of the CPA of any higher-CPA units.
    If the British 7th Armored Division was to move as an entity... it would move with a CPA of
    '10', or that of its lowest-CPA unit -- the 1st KRRC (without trucks)."

    `formation` is the [19.12] subtree the counter carries (engine._co_located_subtree). Empty for
    a counter with nothing attached, which is every counter in a scenario with no live organization
    tree -- so those are byte-identical to the bare `effective_cpa` this replaced.

    The minimum is over EFFECTIVE CPA, not printed cpa, because [6.17] lets a motorized infantry
    unit "assume the CPA of the Truck unit carrying it": a subsidiary that has been given trucks
    must stop binding the formation down to its foot rate. (effective_cpa also carries Rommel's
    31.4 +5, which is the same argument from the other end -- the value a unit can actually spend
    this Operations Stage is the one the rule is about.)

    ONLY THE CPA IS BOUND HERE, NOT THE MOBILITY CLASS, and that gap is deliberate and flagged.
    The counter still crosses ground on its Parent's `unit.mobility`, so a motorized subsidiary
    carried by a foot Parent is not tested against [8.44]'s Salt Marsh ban or [8.45]'s desert gate.
    That is a LIVE defect today and not one this rule introduces -- IT-4-CCNN---(4CN) already
    carries kids of mobility {FOOT, MOTORIZED} under a FOOT Parent on scenario.campaign(1).
    `tactics.may_step_into` is the existing instrument for it (it already asks whether EVERY unit
    in a stack may legally cross a hexside, for forced relocations), and wiring it is its own
    measured slice: [6.15] speaks about Capability Points and says nothing about mobility, so
    extending it here would be inventing the rest of a rule the book stops short of."""
    return min([effective_cpa(state, unit)] + [effective_cpa(state, u) for u in formation])


def reachable_for(state: GameState, unit: Unit, enemy_zoc: frozenset,
                  enemy_occupied: frozenset, roster: tuple | None = None,
                  formation=()) -> dict[Coord, float]:
    """Hexes `unit` can legally reach this segment within its remaining CPA. Pass a
    `roster` (the friendly units snapshotted at phase start) so a unit's legal set
    is computed against the phase-start board -- otherwise ZOC-negation shifts as
    earlier units move and the observation ends up offering hexes the engine then
    rejects (the observation/validation must agree on ONE snapshot).

    `formation` is the [19.12] subtree this counter carries, and it binds the CPA under [6.15]
    (see formation_cpa). It does NOT change `cp_used`: the carried units ride inside the Parent's
    counter and cost no Capability Point of their own, so the spend is the Parent's alone."""
    budget = max(0.0, _cp_ceiling(formation_cpa(state, unit, formation), unit.reserve_released)
                 - unit.cp_used)                                     # 8.17 ceiling (+31.4, +18.24)
    src = roster if roster is not None else state.living(unit.side)
    negators = frozenset(u.hex for u in src if u.is_combat and u.id != unit.id)  # §10.26
    return zoc.reachable_with_zoc(
        state.terrain, unit.hex, budget, unit.mobility,
        enemy_zoc=enemy_zoc, friendly_negators=negators, enemy_occupied=enemy_occupied,
        break_off=_break_off_cost(unit), extra_cost=_mine_extra_cost(state, unit),
        weather=state.weather_at(unit.hex))


def reachable_for_prev(state: GameState, unit: Unit, enemy_zoc: frozenset,
                       enemy_occupied: frozenset,
                       roster: tuple | None = None,
                       formation=()) -> tuple[dict[Coord, float], dict]:
    """`reachable_for`, additionally returning the Dijkstra predecessor map so a mover's
    actual ZOC-legal path can be reconstructed for Breakdown-Point accrual (21.21).

    `formation` binds the CPA under [6.15] exactly as in `reachable_for`. THIS is the form
    engine._movement validates against, so a rule that bound only the other one would hold for
    what a policy is offered and not for what the engine accepts."""
    budget = max(0.0, _cp_ceiling(formation_cpa(state, unit, formation), unit.reserve_released)
                 - unit.cp_used)                                     # 8.17 ceiling (+31.4, +18.24)
    src = roster if roster is not None else state.living(unit.side)
    negators = frozenset(u.hex for u in src if u.is_combat and u.id != unit.id)  # §10.26
    return zoc.reachable_with_zoc_prev(
        state.terrain, unit.hex, budget, unit.mobility,
        enemy_zoc=enemy_zoc, friendly_negators=negators, enemy_occupied=enemy_occupied,
        break_off=_break_off_cost(unit), extra_cost=_mine_extra_cost(state, unit),
        weather=state.weather_at(unit.hex))


def breakdown_points_over(state: GameState, unit: Unit, path: list[Coord]) -> float:
    """Total Breakdown Points a vehicle accrues traversing `path` (rule 21.21/21.23),
    under the current weather. Zero for a non-vehicle (21.11), so a bp of 0 is omitted
    from the move event and non-vehicle scenarios stay byte-identical."""
    if not unit.breaks_down or len(path) < 2:
        return 0.0
    weather = state.weather_at(unit.hex)               # 29.7: the storm the mover set out under
    total = sum(movement.breakdown_points(state.terrain, a, b, unit.mobility, weather)
               for a, b in zip(path, path[1:]))
    if state.minefields:                                # 26.22: added on top of the terrain BV
        total += sum(minefields.breakdown_surcharge(state, unit.side, dst) for dst in path[1:])
    return total


def may_step_into(state: GameState, units, src: Coord, dst: Coord) -> bool:
    """May EVERY unit in `units` legally cross src -> dst -- i.e. is the step permitted by the
    Terrain Effects Chart for its mobility class ([8.37] Swamp's "may enter only on road or
    railroad", [8.44]'s Salt Marsh gate, [8.45]'s Desert gate, and the [8.42] escarpment
    prohibition when 8.1b lands the hexsides)? Cost is irrelevant here; only legality is.

    This is the gate the FORCED relocations need. Voluntary movement (movement.reachable,
    tactics.reachable_for, retreat-before-assault) already runs through movement.step_cost and
    therefore already obeys the chart, but engine._retreat and engine._mandatory_retreat walk
    raw `terrain` membership -- so without this a stack could be shoved into ground its own
    movement rules forbid it to enter, and (worse) then be unable to leave.

    FLAGGED, [8.44]'s own answer to this case is a rule the engine does not carry: "A prohibited
    vehicle that enters a Salt Marsh hex without using the Track, WHATEVER THE REASON, is
    Abandoned (see 5.33)" -- i.e. the book lets the retreat push the vehicle in and then destroys
    it. 5.33 Abandonment has no engine concept at all (no salvage, no recovery, no marker), so
    building half of it here would invent a loss the rules attach to a mechanism we do not have.
    Excluding the hex from the retreat instead keeps the two things the rule guarantees -- a
    barred vehicle never gains free passage through a marsh, and never ends its retreat frozen in
    one -- and leaves 5.33 as named debt rather than a silent hole.

    THE ONE HOLE THIS GATE CANNOT CLOSE, and it is SETUP, not movement: [8.45] is entry-only and
    has no 5.33 Abandonment clause, so a class barred from Desert that is PLACED in one has every
    move legal (it may always leave) unless every neighbour is Desert too -- of which the engine's
    deep sand-sea interiors have plenty. Nothing can reach that state by moving; only an OOB or
    scenario that deploys a Light Truck formation or a motorcycle unit into the sand can create it.
    MEASURED, not assumed, at the point [8.45] gained its first live consumers: zero of the five
    campaign / two benchmark Light convoys and neither Kradschutzen counter starts on a Desert hex,
    and a TruckFormation has exactly one mover in the engine (engine._truck_move, gated by
    supply.reachable_truck_moves) with no forced-relocation path at all. FLAGGED for the OOB slice
    that adds the book's seven Italian Bersaglieri Mitrg battalions."""
    weather = state.weather_at(src)
    return all(movement.step_cost(state.terrain, src, dst, u.mobility, weather) is not None
               for u in units)


def bp_for_move(state: GameState, unit: Unit, prev: dict, dst: Coord) -> float:
    """Breakdown Points for a move to `dst`, reconstructing the min-CP path from a
    predecessor map (reachable_for_prev). The engine passes this straight into the
    UNIT_MOVED faucet."""
    path = movement.reconstruct_path(prev, unit.hex, dst)
    return breakdown_points_over(state, unit, path)
