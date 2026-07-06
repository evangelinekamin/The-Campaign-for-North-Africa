"""Orchestrator (brief §4.3, §4.4).

Walks the phase sequence, invokes the owning side's policy, validates orders at
the engine boundary (NOT via constrained decoding, §3.3), and emits events. The
only place RNG lives — outcomes are rolled here and baked into events so apply/
fold stay pure (§4.1).

MOVEMENT is now real: CPA-budget pathing over terrain with Zones of Control and
stacking (game.movement / game.zoc / game.stacking via game.tactics). COMBAT is
still a placeholder CRT (the real land combat — rule 11 — is the next slice).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import combat, combat_tables, logistics_data, stacking, supply, tactics, weather
from .apply import apply
from .events import Control, Event, EventKind, Phase, Side
from .hexmap import distance, is_adjacent, neighbors
from .invariants import check
from .policy import AttackOrder, MoveOrder, Policy
from .state import Coord, GameState
from .terrain import Terrain

CONTROL_OF: dict[Side, Control] = {Side.AXIS: Control.AXIS, Side.ALLIED: Control.ALLIED}

# Siege of Tobruk tuning knob (rule 25.14): how many effective barrages (a Pin or a
# step loss) it takes to batter a fortification down one level. 1 = each effective
# barrage drops a level. Raise it to make cracking Tobruk harder; the lead tunes
# this (and the Axis ammo/dump schedule) with the benchmark harness.
BARRAGE_HITS_PER_FORT_LEVEL: int = 1

# 55.2 harbour BLOCKING (a scuttled ship) permanently cripples a port until Friendly
# engineers clear the wreck (55.26) -- it is NOT bomb damage, so the 55.18 +1/OpStage
# regeneration does NOT restore it. The San Giorgio scuttled in Tobruk (30.17 / 55.25,
# -3 levels) is such a block: it stays pinned at its seeded Efficiency Level. (The Axis
# rear harbour in the Desert Fox corridor is the WORKING PORT-Tripoli, not the scuttled
# Benghazi -- Step 5 -- so no Axis port is blocked here.)
# Bomb/mine reductions (41.3), which DO regenerate, arrive with the air subsystem (CHUNK 6).
HARBOUR_BLOCKED: frozenset = frozenset({"PORT-Tobruk"})


@dataclass(frozen=True, slots=True)
class RunResult:
    initial: GameState
    events: list[Event]
    final: GameState
    winner: Side | None
    reason: str


class _Run:
    """Mutable driver wrapping immutable state — every change flows through apply()
    so live state equals fold(initial, events) by construction."""

    def __init__(self, initial: GameState):
        self.initial = initial
        self.state = initial
        self.rng = random.Random(initial.seed)
        self.events: list[Event] = []
        self._seq = 0
        self.fort_hits: dict[Coord, int] = {}   # accumulated barrage hits per hex (25.14)

    def emit(self, kind: EventKind, side: Side, actor: str, payload: dict,
             rng_draws: tuple[int, ...] = ()) -> None:
        e = Event(self._seq, self.state.turn, self.state.phase, side, actor,
                  kind, payload, rng_draws)
        self._seq += 1
        self.state = apply(self.state, e)
        check(self.state)
        self.events.append(e)

    def d6(self) -> int:
        return self.rng.randint(1, 6)

    def go(self, phase: Phase, side: Side) -> None:
        self.emit(EventKind.PHASE_ADVANCED, Side.SYSTEM, "SYSTEM",
                  {"phase": phase.value, "active_side": side.value})


def run(initial: GameState, axis: Policy, allied: Policy) -> RunResult:
    r = _Run(initial)
    policies = {Side.AXIS: axis, Side.ALLIED: allied}
    r.emit(EventKind.GAME_INITIALIZED, Side.SYSTEM, "SYSTEM",
           {"seed": initial.seed, "max_turns": initial.max_turns})

    winner: Side | None = None
    reason = "campaign reached final turn"
    cursor = {Side.AXIS: 0, Side.ALLIED: 0}

    def _debrief(side: Side) -> None:
        # Hand the policy the events since it last acted (its rejected orders, losses,
        # ground changes, enemy sorties) -- a commander receives dispatches between
        # decisions. Optional (hasattr): scripted policies ignore it. Pure function of
        # the seeded event log, so replay stays deterministic.
        pol = policies[side]
        if hasattr(pol, "debrief"):
            pol.debrief(r.events[cursor[side]:])
        cursor[side] = len(r.events)

    while True:
        _weather(r)
        _logistics(r)                                   # Stage IV: stores/water expenditure + evaporation
        _reinforcements(r)
        _naval_convoys(r)                               # V.C.7 + V.D: convoy arrival (SYSTEM)
        for side in (Side.AXIS, Side.ALLIED):
            _debrief(side)                              # enemy turn + own last combat
            r.go(Phase.MOVEMENT, side)
            _movement(r, policies[side], side)
            _breakdown(r, side)                         # 21.24: check vehicles that ceased moving
            _supply_movement(r, policies[side], side)   # supply follows the army (32.3)
            _debrief(side)                              # which moves/pincers actually formed
            r.go(Phase.COMBAT, side)
            _combat(r, policies, side)
            _breakdown(r, _other(side))                 # 21.22: the enemy's retreats accrued BP too
            _repair(r, side)                            # 22.12: the phasing side's Repair Phase
        for side in (Side.AXIS, Side.ALLIED):
            _truck_convoys(r, policies[side], side)     # V.J: 2nd/3rd-line truck convoys (48)
        r.go(Phase.RECORD, Side.SYSTEM)
        _record_control(r)
        winner, reason = _victory(r)
        if winner is not None:
            break
        if r.state.turn >= r.state.max_turns:
            winner, reason = _final_decision(r)
            break
        r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM", {"turn": r.state.turn + 1})
        r.go(Phase.WEATHER, Side.SYSTEM)

    return RunResult(r.initial, r.events, r.state, winner, reason)


# --- phases ------------------------------------------------------------------

def _reinforcements(r: _Run) -> None:
    """Bring on any units scheduled to enter this game-turn (rule 20). Each is
    already in state at its entry hex but dormant (off-map, state.on_map) until its
    arrival_turn; this records the arrival. The scenario must give entry hexes room
    to stack (checked by the invariant on arrival)."""
    for u in r.state.units:
        if u.arrival_turn == r.state.turn and u.alive:
            r.emit(EventKind.REINFORCEMENT_ARRIVED, u.side, "SYSTEM",
                   {"unit_id": u.id, "hex": list(u.hex), "turn": r.state.turn})


def interdict(convoy, state: GameState, rng) -> dict:
    """Commonwealth attrition of a convoy in transit (56.13/41.6). CHUNK 1: the ferry
    is invulnerable -- the cargo arrives verbatim. This is the seam CHUNK 6 fills with
    the 32.66 Naval Convoy Bombing chart + Mediterranean-Fleet suppression, emitting
    CONVOY_INTERDICTED beside a reduced SUPPLY_ARRIVED (56.65B min-1-point rule)."""
    return dict(convoy.cargo)


def _naval_convoys(r: _Run) -> None:
    """Naval Convoy Arrival (rule 48 V.C.7 Tactical Shipping + V.D Convoy Arrival): the
    supply SOURCE lands each due convoy's cargo into its destination dump, capped at the
    dump capacity (32.15 -- overflow is simply never credited, a miniature port throttle,
    CHUNK 3 makes it the real 55.14 efficiency gauge). A convoy to an enemy-captured port
    never sails (56.15). Fires ONLY when convoys are due this game-turn, so every convoy-
    less scenario stays byte-identical (no Phase.LOGISTICS is emitted)."""
    due = [c for c in r.state.convoys if c.arrival_turn == r.state.turn]
    regenable = [p for p in r.state.ports
                 if p.id not in HARBOUR_BLOCKED and p.eff < p.max_eff]
    if not due and not regenable:
        return                                          # convoy-/port-less stays byte-identical
    r.go(Phase.LOGISTICS, Side.SYSTEM)
    for c in sorted(due, key=lambda c: c.id):           # deterministic arrival order
        dump = r.state.supply(c.dest)
        enemy_ctrl = CONTROL_OF[_other(c.side)]
        if dump is None or r.state.control_of(dump.hex) == enemy_ctrl:   # 56.15
            r.emit(EventKind.CONVOY_CANCELLED, c.side, "SYSTEM",
                   {"convoy_id": c.id, "lane": c.lane, "dest": c.dest, "reason": "port captured"})
            continue
        cargo = interdict(c, r.state, r.rng)            # CHUNK 1: identity -> dict(c.cargo)
        cap = supply.dump_capacity(r.state.terrain.terrain[dump.hex])   # 54.12, keyed by dump terrain
        port = r.state.port_at(dump.hex)                # 56.28: a port's built-in dump
        landed: dict = {}
        for k, v in cargo.items():
            onhand = getattr(dump, k.lower())
            room = min(cap[k], onhand + v) - onhand     # 54.12 dump headroom
            if port is not None:
                room = min(room, supply.port_landing_cap(port, k))   # 55.14 harbour throttle
            if room > 0:
                landed[k] = room
        if port is not None:                            # legible per-commodity landing beat
            for k in sorted(landed):
                r.emit(EventKind.PORT_UNLOADED, c.side, "SYSTEM",
                       {"port_id": port.id, "commodity": k, "qty": landed[k],
                        "tons": supply.points_to_tons(landed[k], k), "eff": port.eff})
        if landed:                                      # nothing to land into a full dump
            r.emit(EventKind.SUPPLY_ARRIVED, c.side, "SYSTEM",
                   {"supply_id": c.dest, "cargo": landed, "lane": c.lane, "convoy_id": c.id})
    _port_regen(r)      # 55.18: the port worked this OpStage at its current eff, then recovers


def _port_regen(r: _Run) -> None:
    """55.18: every port regains one Efficiency Level per OpStage (up to its assigned
    maximum), emitted as PORT_EFFICIENCY_CHANGED -- except a permanent harbour BLOCK
    (HARBOUR_BLOCKED: San Giorgio, scuttled Benghazi), which only engineers clear (55.26).
    Deterministic (sorted by id). No bomb/mine reductions exist yet (CHUNK 6), so in the
    current scenarios only bomb-free ports below max would climb -- the seeded blocks stay."""
    for p in sorted(r.state.ports, key=lambda p: p.id):
        if p.id in HARBOUR_BLOCKED:
            continue
        level = supply.regen_eff(p)
        if level is not None:
            r.emit(EventKind.PORT_EFFICIENCY_CHANGED, p.side, "SYSTEM",
                   {"port_id": p.id, "level": level})


def _logistics(r: _Run) -> None:
    """Stores Expenditure Stage (rule 48 Stage IV) at the top of the game-turn: both
    sides expend STORES (51, once/game-turn) and WATER (52, per Operations Stage --
    coincident with the game-turn under the current one-ops-stage cadence), after fuel
    and water have evaporated (49.3/52.44). A unit draws each commodity from the dumps
    it can trace (the 32.16 gate, reused via supply.plan_draw); an Italian battalion
    that gets its stores also needs a Pasta Point of water (52.6). Shortfall attrition
    for units that go unsupplied lands in SUB-STEP D.

    Fires ONLY for scenarios that model full logistics (some dump seeds Stores/Water);
    an ammo/fuel-only scenario skips it entirely and stays byte-identical."""
    s = r.state
    if not s.initial_supply.get(supply.STORES, 0) and not s.initial_supply.get(supply.WATER, 0):
        return
    r.go(Phase.LOGISTICS, Side.SYSTEM)
    hot = s.weather == "hot"
    _evaporate(r, hot)
    for side in (Side.AXIS, Side.ALLIED):
        _stores_expenditure(r, side, hot)
        _water_distribution(r, side, hot)


_EVAP = logistics_data.evaporation_percent()   # 49.3/52.44, from the rulebook


def _evaporate(r: _Run, hot: bool) -> None:
    """49.3 / 52.44: each game-turn, on-map Fuel and Water lose 6% (rounded down), plus
    a further 5% in hot weather. A SINK into consumed[] (the 9% Sep40-Aug41 Commonwealth
    container rate is deferred). Deterministic: sorted dumps, fuel then water."""
    pct = _EVAP["base"] + (_EVAP["hot_additional"] if hot else 0)
    for sid in sorted(su.id for su in r.state.supplies):
        for commodity in (supply.FUEL, supply.WATER):
            amt = getattr(r.state.supply(sid), commodity.lower())
            loss = amt * pct // 100
            if loss > 0:
                r.emit(EventKind.SUPPLY_EVAPORATED, Side.SYSTEM, "SYSTEM",
                       {"supply_id": sid, "commodity": commodity, "qty": loss})


def _stores_expenditure(r: _Run, side: Side, hot: bool) -> None:
    actor = f"{side.value}/Logistics"
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        draws = supply.plan_draw(r.state, u, supply.STORES, supply.stores_cost(u))
        if draws is None:
            _stores_shortfall(r, side, actor, u)        # 51.21/51.22
            continue
        for sid, qty in draws:
            r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                   {"supply_id": sid, "commodity": supply.STORES, "qty": qty, "unit_id": u.id})
        if u.turns_without_stores > 0:                  # resupplied -> reset the consecutive count
            r.emit(EventKind.STORES_RESTORED, side, actor, {"unit_id": u.id})
        _pasta_point(r, side, actor, u)                 # 52.6: got stores -> needs its pasta water


# A unit only DISORGANIZES (a cohesion hit that feeds the 15.88/17 surrender path) once
# its Stores shortfall is SUSTAINED, not on a single turn out of trace -- the rules stress
# "consecutive" shortfall, and a unit briefly outrunning its stores while advancing must
# not have its morale collapse (which would unravel the whole combat trajectory). The
# Disorganization Point itself (51.21) still accrues every short turn in the counter.
DISORGANIZED_AFTER: int = 6        # consecutive short game-turns before cohesion bites


def _stores_shortfall(r: _Run, side: Side, actor: str, u) -> None:
    """A unit that cannot draw its Stores this game-turn (51.2). It earns a
    Disorganization Point every turn (51.21, accrued in the counter); once sustained
    (>= DISORGANIZED_AFTER consecutive turns) it disorganizes, routed through
    COHESION_CHANGED so it feeds the live 15.88/17 surrender. Every second consecutive
    short turn an INFANTRY unit sheds that turn's percentage of its TOE Strength Points
    (51.22: 2% at 2 turns, 4% at 4 ...) via STEP_LOST role='attrition'. Guns/tanks are
    exempt from the step loss (51.22)."""
    r.emit(EventKind.STORES_SHORTFALL, side, actor, {"unit_id": u.id})
    cur = r.state.unit(u.id)
    n = cur.turns_without_stores
    if n >= DISORGANIZED_AFTER:                          # 51.21 disorganization bites (sustained)
        r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -1})
    if supply.is_infantry(cur) and n >= 2 and n % 2 == 0:
        loss = round(n / 100 * cur.strength)            # 51.22 n% of TOE, nearest whole
        if loss > 0:
            r.emit(EventKind.STEP_LOST, side, actor,
                   {"unit_id": u.id, "amount": min(loss, cur.strength), "role": "attrition"})


def _pasta_point(r: _Run, side: Side, actor: str, u) -> None:
    """52.6 the Italian Pasta Rule: an Italian battalion, when it receives its Stores,
    must also receive one Water Point to cook its pasta. Denied it, the battalion may
    not voluntarily exceed its CPA that turn (a no-op in the CPA-bounded engine, flagged
    by the PASTA_DENIED marker), and if it is already shaky (Cohesion -10 or worse) it
    immediately disorganizes as if at -26 -- feeding the live 15.88/17 surrender path.
    Recovery on later receipt of the Pasta Point (52.6) is deferred, like all Cohesion
    recovery."""
    if not supply.is_italian(u) or not u.is_combat:
        return
    draws = supply.plan_draw(r.state, u, supply.WATER, 1)
    if draws is not None:
        for sid, qty in draws:
            r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                   {"supply_id": sid, "commodity": supply.WATER, "qty": qty, "unit_id": u.id})
        return
    r.emit(EventKind.PASTA_DENIED, side, actor, {"unit_id": u.id})
    if u.cohesion <= -10:
        r.emit(EventKind.COHESION_CHANGED, side, actor,
               {"unit_id": u.id, "delta": -26 - u.cohesion})


def _water_distribution(r: _Run, side: Side, hot: bool) -> None:
    actor = f"{side.value}/Logistics"
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        draws = supply.plan_draw(r.state, u, supply.WATER, supply.water_cost(u, hot=hot))
        if draws is None:
            _water_shortfall(r, side, actor, u)         # 52.53
            continue
        for sid, qty in draws:
            r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                   {"supply_id": sid, "commodity": supply.WATER, "qty": qty, "unit_id": u.id})
        if u.stages_without_water > 0:                  # resupplied -> reset the consecutive count
            r.emit(EventKind.WATER_RESTORED, side, actor, {"unit_id": u.id})


def _water_shortfall(r: _Run, side: Side, actor: str, u) -> None:
    """A unit deprived of Water this Operations Stage (52.5). For every consecutive stage
    AFTER the first, an INFANTRY unit loses one TOE Strength Point (52.53), via the
    existing STEP_LOST role='attrition'. (Vehicles-can't-move / defend-at-half, 52.51-52,
    are deferred; the attrition is the load-bearing degradation.)"""
    r.emit(EventKind.WATER_SHORTFALL, side, actor, {"unit_id": u.id})
    cur = r.state.unit(u.id)
    if supply.is_infantry(cur) and cur.stages_without_water >= 2:    # after the first stage
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": u.id, "amount": min(1, cur.strength), "role": "attrition"})


def _weather(r: _Run) -> None:
    """Weather Determination (rule 29.1): the season (from the Game-Turn) selects the
    29.61 Weather Table row; a sequential 2d6 gives the weather type. A foul result
    (sandstorm/rainstorm) rolls one more die on the 29.7 Foul Weather Location Table for
    the affected map sections -- if none of the scenario's own sections are hit, the
    theater stays Normal (29.1: unaffected sections have normal weather). Hot occurs on
    every section (29.31), so it needs no location roll. The single emitted label is
    what every downstream coupling (breakdown shift, evaporation, movement cost) reads."""
    season = weather.season_for_turn(r.state.turn)
    d1, d2 = r.d6(), r.d6()
    label = weather.weather_for_roll(season, d1 * 10 + d2)
    draws = (d1, d2)
    sections: frozenset = frozenset()
    if weather.is_foul(label):
        d3 = r.d6()
        draws = (d1, d2, d3)
        sections = weather.foul_sections(d3)
        theater = r.state.map_sections
        if theater and theater.isdisjoint(sections):        # 29.1: foul missed this theater
            label = weather.NORMAL
    r.emit(EventKind.WEATHER_ROLLED, Side.SYSTEM, "SYSTEM",
           {"weather": label, "season": season, "sections": sorted(sections)},
           rng_draws=draws)


def _movement(r: _Run, policy: Policy, side: Side) -> None:
    actor = f"{side.value}/Front"
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(r.state, side)
    roster = r.state.living(side)          # phase-start snapshot (matches the observation)
    for order in policy.movement(r.state, side):
        u = r.state.unit(order.unit_id)
        if u is None or not u.alive or u.side != side:
            _reject(r, side, actor, order, "no such living unit under this command")
            continue
        if u.effective_strength == 0:                   # 21.44: all vehicles broken down
            _reject(r, side, actor, order, "all vehicles broken down, may not move (21.44)")
            continue
        # Reachability is computed against the phase-start roster so a unit's legal
        # set doesn't depend on the order earlier units moved (matches observe()).
        reach, prev = tactics.reachable_for_prev(r.state, u, enemy_zoc, enemy_occupied, roster)
        if order.to == u.hex or order.to not in reach:
            _reject(r, side, actor, order,
                    "destination unreachable within CPA or blocked by ZOC")
            continue
        present = [x for x in r.state.units_at(order.to) if x.side == side]
        if not stacking.within_hex_limit(present + [u], r.state.terrain.terrain[order.to]):
            _reject(r, side, actor, order, "destination over stacking limit")
            continue
        if u.cp_used == 0:                          # first move this OpStage pays fuel (49.16)
            # Distance-based fuel (49.13): rate x ceil(CP/5) for THIS move's path cost,
            # drawn in the hex the move begins -- so a long dash outruns its fuel.
            draws = supply.plan_draw(r.state, u, supply.FUEL,
                                     supply.fuel_cost(u, reach[order.to]))
            if draws is None:
                _reject(r, side, actor, order, "out of supply: no fuel for this move")
                continue
            for sid, qty in draws:
                r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                       {"supply_id": sid, "commodity": supply.FUEL, "qty": qty, "unit_id": u.id})
        payload = {"unit_id": u.id, "from": list(u.hex), "to": list(order.to),
                   "cp_spent": reach[order.to]}
        bp = tactics.bp_for_move(r.state, u, prev, order.to)     # 21.21 accrual (0 for non-vehicles)
        if bp:
            payload["bp"] = bp
        r.emit(EventKind.UNIT_MOVED, side, actor, payload)


def _broken_count(pct: int, effective: int) -> int:
    """TOE Strength Points that break down: `pct` of the operational vehicles, fractions
    rounded UP (21.35), capped at the operational count. Exception (21.35): a unit of a
    single TOE point ignores a 10% result."""
    if pct <= 0 or effective <= 0:
        return 0
    if effective == 1 and pct == 10:
        return 0
    return min(effective, math.ceil(pct / 100 * effective))


def _breakdown(r: _Run, side: Side) -> None:
    """Breakdown check (rule 21.24): every vehicle unit of `side` that has ceased moving
    with more than three accumulated Breakdown Points (21.27) rolls on the 21.38 table,
    but only if it has climbed into a HIGHER column than its last check this OpStage
    (21.26 -- the geometric moving/stopping penalty). The rolled percentage of its
    operational TOE breaks down (21.35 rounding), moving into Unit.broken_down. Inert on
    non-vehicle scenarios (no vehicle accrues BP -> no roll -> byte-identical)."""
    actor = f"{side.value}/Front"
    wshift = combat_tables.weather_breakdown_shift(r.state.weather)          # 21.37
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        if not u.breaks_down or u.bp_accumulated <= 3:                       # 21.11 / 21.27
            continue
        col = combat_tables.breakdown_column(u.bp_accumulated, u.bar, wshift)
        if col <= u.bp_checked_column:                                       # 21.26 gate
            continue
        d1, d2 = r.d6(), r.d6()
        pct = combat_tables.breakdown_result(u.bp_accumulated, u.bar, wshift, d1 * 10 + d2)
        broken = _broken_count(pct, u.effective_strength)
        r.emit(EventKind.BREAKDOWN_CHECKED, side, actor,
               {"unit_id": u.id, "column": col, "bar": u.bar,
                "weather_shift": wshift, "pct": pct}, rng_draws=(d1, d2))
        if broken > 0:
            r.emit(EventKind.VEHICLE_BROKE_DOWN, side, actor,
                   {"unit_id": u.id, "amount": broken})


# Field tank/SPA repair expends Fuel (22.15/22.26). Fork B charges it per repair
# ATTEMPT (one unit's roll) rather than per TOE point -- the design's documented proxy;
# armored-car / recce field repair is free (22.24).
_REPAIR_FUEL: int = 1


def _field_repair_blocked(weather_label: str) -> bool:
    """22.13d: no Field Repair while the Weather is Rainstorm or Sandstorm (keyed off the
    single global 29.1 label -- the per-section coupling stays a documented Fork-B proxy)."""
    return weather_label in ("rainstorm", "sandstorm")


def _repaired_count(vclass: str, result: int, broken: int) -> int:
    """TOE Strength Points a 22.8 field result repairs, capped at the broken pool. A
    tank result is a percentage (fractions round up, 22.25); an armored-car/recce or
    truck result is a flat point count (22.23/22.24)."""
    if broken <= 0:
        return 0
    if vclass == "tank":
        if broken == 1 and result == 10:                # 22.25 single-TOE ignores 10%
            return 0
        return min(broken, math.ceil(result / 100 * broken))
    return min(result, broken)


def _repair(r: _Run, side: Side) -> None:
    """Repair Phase (rule 22.12): the phasing side field-repairs its broken-down vehicles.
    Each such unit in a non-enemy hex (22.13a), weather permitting (22.13d), expends the
    22.15 Fuel and rolls one die on the 22.8 Field column; the repaired TOE flows back to
    the operational pool (VEHICLE_REPAIRED). Fires only when the side actually has broken
    vehicles to repair, so every pre-breakdown scenario stays byte-identical."""
    if _field_repair_blocked(r.state.weather):          # 22.13d: whole-map proxy, no field repair
        return
    enemy_ctrl = CONTROL_OF[_other(side)]
    repairable = [u for u in r.state.living(side)
                  if u.broken_down > 0 and u.breaks_down
                  and r.state.control_of(u.hex) != enemy_ctrl]     # 22.13a
    if not repairable:
        return
    r.go(Phase.REPAIR, side)
    actor = f"{side.value}/Repair"
    for u in sorted(repairable, key=lambda u: u.id):
        cur = r.state.unit(u.id)
        vclass = "tank" if cur.is_tank else "ac_recce"
        if vclass == "tank":                            # 22.26: expend Fuel before rolling
            draws = supply.plan_draw(r.state, cur, supply.FUEL, _REPAIR_FUEL)
            if draws is None:
                continue                                # 22.13b: no supplies -> no repair
            for sid, qty in draws:
                r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                       {"supply_id": sid, "commodity": supply.FUEL, "qty": qty, "unit_id": cur.id})
        die = r.d6()
        cur = r.state.unit(u.id)                        # re-read after the fuel draw
        repaired = _repaired_count(vclass, combat_tables.field_repair(vclass, die), cur.broken_down)
        if repaired > 0:
            r.emit(EventKind.VEHICLE_REPAIRED, side, actor,
                   {"unit_id": cur.id, "amount": repaired})


def _reject(r: _Run, side: Side, actor: str, order: MoveOrder, reason: str,
            order_kind: str = "move") -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": order_kind, "unit_id": order.unit_id, "to": list(order.to),
            "reason": reason})


def _supply_movement(r: _Run, policy: Policy, side: Side) -> None:
    """Relocate supply units with the advancing army (rule 32.3): a carried dump
    moves up to CPA 15 as medium-truck, costs a flat 1 Fuel Point (32.24) drawn
    from its own trucks, and must end stacked with a friendly combat unit (32.33).
    Validated at the boundary like every other order."""
    actor = f"{side.value}/Logistics"
    moved: set = set()               # a dump relocates at most once per OpStage (32.58A)
    for order in policy.supply_orders(r.state, side):
        su = r.state.supply(order.supply_id)
        if su is None or su.side != side or su.empty:
            _reject_supply(r, side, actor, order, "no such active supply unit")
            continue
        if su.id in moved:
            _reject_supply(r, side, actor, order, "already moved this OpStage (CPA 15/stage)")
            continue
        if order.to == su.hex or order.to not in supply.reachable_moves(r.state, su):
            _reject_supply(r, side, actor, order, "beyond CPA 15 or blocked by ZOC")
            continue
        if not any(u.side == side and u.is_combat for u in r.state.units_at(order.to)):
            _reject_supply(r, side, actor, order, "must end stacked with a friendly combat unit")
            continue
        if su.fuel < supply.SUPPLY_MOVE_FUEL:
            _reject_supply(r, side, actor, order, "out of fuel to move")
            continue
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": su.id, "commodity": supply.FUEL,
                "qty": supply.SUPPLY_MOVE_FUEL, "unit_id": su.id})
        r.emit(EventKind.SUPPLY_MOVED, side, actor,
               {"supply_id": su.id, "from": list(su.hex), "to": list(order.to)})
        moved.add(su.id)


def _reject_supply(r: _Run, side: Side, actor: str, order, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "supply_move", "supply_id": order.supply_id,
            "to": list(order.to), "reason": reason})


def _truck_convoys(r: _Run, policy: Policy, side: Side) -> None:
    """Truck Convoy Movement Phase (rule 48 Stage V.J): the unattached 2nd/3rd-line truck
    convoys (rule 53) haul supply forward. Each order may LOAD from a co-located dump, MOVE
    up to the 53.22 extended convoy CPA (Light 40, Medium/Heavy 30) reusing the 32.16
    trace-blocking verbatim while burning its OWN cargo fuel (49.18), then UNLOAD into a
    forward dump (respecting the 54.12 ceiling). Fires ONLY when the side fields truck
    formations, so every truck-less scenario stays byte-identical."""
    if not any(t.side == side for t in r.state.trucks):
        return
    r.go(Phase.LOGISTICS, side)
    actor = f"{side.value}/Logistics"
    moved: set = set()               # a formation relocates at most once per phase (53.21)
    for order in policy.truck_orders(r.state, side):
        _truck_order(r, side, actor, order, moved)


def _truck_order(r: _Run, side: Side, actor: str, order, moved: set) -> None:
    truck = r.state.truck(order.truck_id)
    if truck is None or truck.side != side:
        _reject_truck(r, side, actor, order, "no such truck formation under this command")
        return
    if order.load and not _truck_load(r, side, actor, order, r.state.truck(truck.id)):
        return
    if order.to is not None and not _truck_move(r, side, actor, order, r.state.truck(truck.id), moved):
        return
    if order.unload:
        _truck_unload(r, side, actor, order, r.state.truck(truck.id))


def _truck_load(r: _Run, side: Side, actor: str, order, truck) -> bool:
    dump = r.state.supply(order.load_from)
    if dump is None or dump.side != side or dump.hex != truck.hex:
        _reject_truck(r, side, actor, order, "no co-located friendly dump to load from")
        return False
    cargo = {c: q for c, q in order.load.items() if q > 0}
    if any(getattr(dump, c.lower()) < q for c, q in cargo.items()):
        _reject_truck(r, side, actor, order, "dump lacks the ordered load")
        return False
    if not supply.truck_load_admissible(truck, cargo):
        _reject_truck(r, side, actor, order, "load exceeds truck capacity (53.12)")
        return False
    r.emit(EventKind.TRUCK_LOADED, side, actor,
           {"truck_id": truck.id, "supply_id": dump.id, "cargo": cargo})
    return True


def _truck_move(r: _Run, side: Side, actor: str, order, truck, moved: set) -> bool:
    if truck.id in moved:
        _reject_truck(r, side, actor, order, "already moved this Truck Convoy Phase")
        return False
    reach = supply.reachable_truck_moves(r.state, truck)
    to = tuple(order.to)
    if to == truck.hex or to not in reach:
        _reject_truck(r, side, actor, order, "beyond convoy CPA or blocked by ZOC")
        return False
    fuel = supply.truck_move_fuel(truck, reach[to])
    if truck.fuel < fuel:
        _reject_truck(r, side, actor, order, "out of cargo fuel to move (49.18)")
        return False
    r.emit(EventKind.TRUCK_MOVED, side, actor,
           {"truck_id": truck.id, "from": list(truck.hex), "to": list(to),
            "cp_spent": reach[to], "fuel": fuel})
    moved.add(truck.id)
    return True


def _truck_unload(r: _Run, side: Side, actor: str, order, truck) -> None:
    dump = r.state.supply(order.unload_to)
    if dump is None or dump.side != side or dump.hex != truck.hex:
        _reject_truck(r, side, actor, order, "no co-located friendly dump to unload into")
        return
    cap = supply.dump_capacity(r.state.terrain.terrain[dump.hex])     # 54.12 ceiling
    cargo: dict = {}
    for c, q in order.unload.items():
        onhand = getattr(dump, c.lower())
        landed = min(q, getattr(truck, c.lower()), min(cap[c], onhand + q) - onhand)
        if landed > 0:
            cargo[c] = landed
    if cargo:
        r.emit(EventKind.TRUCK_UNLOADED, side, actor,
               {"truck_id": truck.id, "supply_id": dump.id, "cargo": cargo})


def _reject_truck(r: _Run, side: Side, actor: str, order, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "truck_convoy", "truck_id": order.truck_id, "reason": reason})


def _other(side: Side) -> Side:
    return Side.ALLIED if side is Side.AXIS else Side.AXIS


def _combat(r: _Run, policies: dict, side: Side) -> None:
    """One Combat Segment (rule 11.0), the Phasing side = `side`. Barrage and Anti-
    Armor are fought by BOTH players (their losses land before Close Assault); then
    the Phasing player Close Assaults. Retreat-Before-Assault (13.0) slots in after
    all Barrages and before the ensuing Anti-Armor / Close Assault sub-segments
    (13.28): the NON-PHASING side may slip UNPINNED units out of contact."""
    enemy = _other(side)
    pinned: set[str] = set()          # units Pinned by barrage this segment (12.44)
    _barrage_step(r, side, enemy, pinned)
    _retreat_before_assault(r, policies[enemy], enemy, side, pinned)
    _anti_armor_step(r, side, enemy, pinned)
    actor = f"{side.value}/Front"
    assaulted: set = set()            # 15.23: each hex is close-assaulted at most once/segment
    committed: set = set()            # 15.24: each unit joins at most one assault/segment
    for order in policies[side].combat(r.state, side):
        target = order.target
        # Dedupe attacker ids (else a repeated id multiplies strength), drop units
        # already committed to another assault this segment, and require is_combat
        # (an HQ costs 0 ammo and would otherwise farm assaults / Rommel's +1).
        ids = [a for a in dict.fromkeys(order.attacker_ids) if a not in committed]
        attackers = [r.state.unit(a) for a in ids]
        attackers = [u for u in attackers if u and u.alive and u.is_combat
                     and u.side == side and is_adjacent(u.hex, target)]
        defenders = list(r.state.enemies_at(target, side))
        if target in assaulted:
            r.emit(EventKind.ORDER_REJECTED, side, actor,
                   {"order": "attack", "target": list(target),
                    "reason": "hex already close-assaulted this segment"})
            continue
        if not attackers or not defenders:
            r.emit(EventKind.ORDER_REJECTED, side, actor,
                   {"order": "attack", "target": list(target),
                    "reason": "no valid attackers or empty target"})
            continue
        _resolve_combat(r, side, actor, attackers, defenders, target, pinned)
        assaulted.add(target)
        committed.update(u.id for u in attackers)


def _retreat_before_assault(r: _Run, policy: Policy, side: Side, phasing: Side,
                            pinned: set[str]) -> None:
    """Retreat Before Assault (rule 13.0): once all Barrages are complete, the NON-
    PHASING side (`side`) may pull units out of contact before the assault lands. It
    is Voluntary Movement (13.21) -- it spends CP (and Fuel for vehicles) and obeys
    enemy ZOC, break-off cost and the no-ZOC-to-ZOC rule (13.22 / 13.26) exactly as
    ordinary movement does (tactics.reachable_for already models all three). So an
    unpinned reserve can slip an assault while the Pinned garrison stays and is
    close-assaulted -- the elastic desert defense. Units Pinned by barrage, or at a
    Cohesion Level of -26 or worse, may NOT retreat before assault (13.1). Suscep-
    tibility of a unit that retreats INTO an attacked hex (13.28) is deferred."""
    actor = f"{side.value}/Front"
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(r.state, side)
    roster = r.state.living(side)          # phase-start snapshot (matches reachability)
    for order in policy.retreat_before_assault(r.state, side, frozenset(pinned)):
        u = r.state.unit(order.unit_id)
        if u is None or not u.alive or u.side != side:
            _reject(r, side, actor, order, "no such living unit under this command",
                    order_kind="retreat_before_assault")
            continue
        if u.id in pinned:                                      # 13.1: Pinned may not retreat
            _reject(r, side, actor, order, "pinned units may not retreat before assault (13.1)",
                    order_kind="retreat_before_assault")
            continue
        if u.cohesion <= -26:                                   # 13.1: -26 or worse may not
            _reject(r, side, actor, order,
                    "cohesion -26 or worse may not retreat before assault (13.1)",
                    order_kind="retreat_before_assault")
            continue
        reach_all, prev = tactics.reachable_for_prev(r.state, u, enemy_zoc, enemy_occupied, roster)
        reach = _rba_cp_cap(r.state, u, reach_all)
        if order.to == u.hex or order.to not in reach:
            _reject(r, side, actor, order,
                    "destination unreachable within CPA or blocked by ZOC",
                    order_kind="retreat_before_assault")
            continue
        present = [x for x in r.state.units_at(order.to) if x.side == side]
        if not stacking.within_hex_limit(present + [u], r.state.terrain.terrain[order.to]):
            _reject(r, side, actor, order, "destination over stacking limit",
                    order_kind="retreat_before_assault")
            continue
        if u.cp_used == 0:                          # first move this OpStage pays fuel (49.16)
            draws = supply.plan_draw(r.state, u, supply.FUEL,
                                     supply.fuel_cost(u, reach[order.to]))
            if draws is None:
                _reject(r, side, actor, order, "out of supply: no fuel for this move",
                        order_kind="retreat_before_assault")
                continue
            for sid, qty in draws:
                r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                       {"supply_id": sid, "commodity": supply.FUEL, "qty": qty, "unit_id": u.id})
        payload = {"unit_id": u.id, "from": list(u.hex), "to": list(order.to),
                   "cp_spent": reach[order.to]}
        bp = tactics.bp_for_move(r.state, u, prev, order.to)     # 21.22: reaction/retreat accrues BP
        if bp:
            payload["bp"] = bp
        r.emit(EventKind.UNIT_MOVED, side, actor, payload)   # 13.21: retreat-before-assault IS movement


def _rba_cp_cap(state: GameState, unit, reach: dict) -> dict:
    """CP ceiling on a Retreat Before Assault (13.23 / 13.24): a unit that BEGINS the
    step adjacent to an enemy combat unit may expend as many CP as it likes (13.23);
    one that does not may expend at most four CP -- or move a single hex, whichever
    is greater (13.24). The reachable set from tactics.reachable_for already bounds
    the unit's remaining CPA; this trims it to the 13.24 allowance when out of
    contact, but always leaves any directly-adjacent hex it can afford."""
    in_contact = any(e.is_combat for nb in neighbors(unit.hex)
                     for e in state.enemies_at(nb, unit.side))
    if in_contact:
        return reach
    return {c: cost for c, cost in reach.items()
            if cost <= 4.0 or distance(unit.hex, c) == 1}


def _barrage_class(u) -> str:
    return "armor" if u.is_armor else "gun" if u.is_gun else "infantry"


def _barrage_target(enemies) -> "object | None":
    """The firer bombards one target in the hex; blind, so a reasonable default is
    the strongest combat unit present."""
    combatants = [u for u in enemies if u.is_combat and u.alive]
    return max(combatants, key=lambda u: u.strength, default=None)


def _barrage_step(r: _Run, phasing: Side, enemy: Side, pinned: set[str]) -> None:
    """Barrage (rule 12): both sides' artillery bombard adjacent enemy hexes first,
    simultaneously (strengths read pre-loss). Each barrage resolves against one
    target unit's class on the 12.6 CRT -> Pin and/or step loss; a Pin suppresses
    that unit for the rest of the segment (no anti-armor, no close assault, 12.44).
    Terrain column-shifts and the separate truck roll (12.46) are deferred."""
    state0 = r.state
    plan: list[tuple] = []
    for firing in (phasing, enemy):
        actor = f"{firing.value}/Front"
        is_phasing = firing is phasing
        by_target: dict[Coord, list] = {}
        for u in state0.living(firing):
            if u.barrage <= 0 or not u.is_combat:
                continue
            for nb in neighbors(u.hex):
                if state0.enemies_at(nb, firing):
                    by_target.setdefault(nb, []).append(u)
                    break
        for tgt, firers in by_target.items():
            armed = [u for u in firers
                     if _charge_ammo(r, firing, actor, u, phasing=is_phasing, activity="barrage")]
            raw = sum(u.raw_barrage for u in armed)
            target_unit = _barrage_target(state0.enemies_at(tgt, firing))
            if raw <= 0 or target_unit is None:
                continue
            cls = _barrage_class(target_unit)
            d1, d2 = r.d6(), r.d6()
            shift = combat_tables.barrage_terrain_shift(          # 12.33 terrain / fortification
                state0.terrain.terrain[tgt], state0.fort_level(tgt), cls)
            pin, loss = combat_tables.barrage_result(
                cls, combat.actual_points(raw, False), d1 * 10 + d2, column_shift=shift)
            plan.append((firing, actor, tgt, [u.id for u in armed],
                         combat.actual_points(raw, False), cls, target_unit.id, (d1, d2), pin, loss))
    for firing, actor, tgt, firer_ids, actual, cls, tgt_id, dice, pin, loss in plan:
        r.emit(EventKind.BARRAGE_RESOLVED, firing, actor,
               {"target": list(tgt), "firers": firer_ids, "actual": actual,
                "target_class": cls, "target_unit": tgt_id, "pinned": pin, "loss": loss},
               rng_draws=dice)
        if loss > 0:
            tu = r.state.unit(tgt_id)
            if tu and tu.alive:
                r.emit(EventKind.STEP_LOST, firing, actor,
                       {"unit_id": tgt_id, "amount": min(loss, tu.strength), "role": "barrage"})
        if pin:
            pinned.add(tgt_id)
        _batter_fort(r, firing, actor, tgt, effective=pin or loss > 0)


def _batter_fort(r: _Run, firing: Side, actor: str, tgt: Coord, *, effective: bool) -> None:
    """Siege of Tobruk (rule 25.14): an EFFECTIVE artillery barrage (a Pin or a step
    loss) on a fortified hex batters its wall. After BARRAGE_HITS_PER_FORT_LEVEL such
    hits the fortification drops one level (floored at 0), emitted as FORT_REDUCED so
    the reduction folds into GameState.fort_levels and close assault reads the lower
    wall. Gated behind siege_rules -- inert (and silent) in the canonical benchmark.
    Barrage NEVER evicts and NEVER touches the static base map: only the level falls."""
    if not r.state.siege_rules or not effective or r.state.fort_level(tgt) <= 0:
        return
    r.fort_hits[tgt] = r.fort_hits.get(tgt, 0) + 1
    if r.fort_hits[tgt] >= BARRAGE_HITS_PER_FORT_LEVEL:
        r.fort_hits[tgt] = 0
        r.emit(EventKind.FORT_REDUCED, firing, actor,
               {"hex": list(tgt), "level": r.state.fort_level(tgt) - 1})


def _anti_armor_step(r: _Run, phasing: Side, enemy: Side, pinned: set[str]) -> None:
    """Anti-Armor Fire (rule 14): both sides fire at each other's adjacent armor,
    simultaneously (target strengths are read before any loss lands), and all armor
    losses precede Close Assault. Each unit with an Anti-Armor rating fires at one
    adjacent enemy hex holding armor, combining with others onto that target; firing
    costs ammunition (14.24). Voluntary withholding and splitting TOE between anti-
    armor and assault are deferred -- all committed armor fires and is a target."""
    state0 = r.state
    plan: list[tuple] = []
    for firing in (phasing, enemy):
        is_phasing = firing is phasing
        actor = f"{firing.value}/Front"
        by_target: dict[Coord, list] = {}
        for u in state0.living(firing):
            if u.anti_armor <= 0 or not u.is_combat or u.id in pinned:   # 12.44 pinned can't fire
                continue
            for nb in neighbors(u.hex):
                if any(t.is_armor for t in state0.enemies_at(nb, firing)):
                    by_target.setdefault(nb, []).append(u)
                    break
        for tgt, firers in by_target.items():
            armed = [u for u in firers                       # 14.24/50.2: anti-armor fire draws
                     if _charge_ammo(r, firing, actor, u, phasing=is_phasing,
                                     activity="anti_armor")]  # the anti-armor rate (3/TOE)
            raw = sum(u.raw_anti_armor for u in armed)
            if raw <= 0:
                continue
            d1, d2 = r.d6(), r.d6()
            shift = combat_tables.anti_armor_terrain_shift(      # 14.32 terrain / fortification
                state0.terrain.terrain[tgt], state0.fort_level(tgt))
            dmg = combat_tables.anti_armor_damage(combat.actual_points(raw, False),
                                                   d1 * 10 + d2, phasing=is_phasing,
                                                   terrain_shift=shift)
            plan.append((firing, actor, tgt, [u.id for u in armed], raw, (d1, d2), dmg))
    for firing, actor, tgt, firer_ids, raw, dice, dmg in plan:
        r.emit(EventKind.ANTI_ARMOR_RESOLVED, firing, actor,
               {"target": list(tgt), "firers": firer_ids, "raw": raw,
                "actual": combat.actual_points(raw, False), "damage": dmg},
               rng_draws=dice)
        _apply_armor_losses(r, firing, actor, tgt, dmg)


def _apply_armor_losses(r: _Run, firing: Side, actor: str, target: Coord, damage: int) -> None:
    """Remove armored TOE from the target hex to absorb >= `damage` Armor-Protection
    Points; each step absorbs that unit's Armor Protection rating (rule 14.42/43).
    Excess beyond destroying all armor there is ignored (14.45)."""
    remaining = damage
    for u in r.state.enemies_at(target, firing):
        if remaining <= 0:
            break
        if not u.is_armor or not u.alive:
            continue
        steps = min(u.strength, math.ceil(remaining / u.armor_protection))
        if steps > 0:
            r.emit(EventKind.STEP_LOST, firing, actor,
                   {"unit_id": u.id, "amount": steps, "role": "armor"})
            remaining -= steps * u.armor_protection


def _resolve_combat(r: _Run, side: Side, actor: str, attackers, defenders,
                    target: Coord, pinned: set[str]) -> None:
    # Ammo gates participation (rule 32.21 / 15.15) and Pin suppresses it (12.44):
    # a unit that cannot draw ammo or is Pinned cannot assault; a Pinned or unarmed
    # defender adds no defensive strength but still suffers losses. Charged before
    # resolution (conservation holds per event).
    armed_atk = [u for u in attackers
                 if u.id not in pinned and _charge_ammo(r, side, actor, u, phasing=True)]
    if not armed_atk:
        r.emit(EventKind.ORDER_REJECTED, side, actor,
               {"order": "attack", "target": list(target),
                "reason": "attackers out of ammo or pinned"})
        return
    # 15.15 / 15.88: an assaulted stack that is entirely out of Close-Assault ammo,
    # or whose (largest) unit's Cohesion has collapsed to -17 or worse, automatically
    # Surrenders the instant it is assaulted -- BEFORE it rolls morale or spends a
    # round of ammunition. This is the fix that lets a besieged, cut-off garrison
    # (a dry Tobruk) finally be forced to capitulate instead of holding at zero
    # defensive strength in perpetuity.
    if _defenders_capitulate(r, defenders):
        _resolve_surrender(r, side, actor, target, armed_atk, defenders,
                           atk_surr=False, def_surr=True, morale_shift=0, dice=())
        return
    armed_def = [u for u in defenders
                 if u.id not in pinned and _charge_ammo(r, side, actor, u, phasing=False)]

    # Close Assault via the real differential engine (rule 15 / §15.79 CRT).
    feature = r.state.terrain.hexsides.get((armed_atk[0].hex, target))  # §15.33
    fort = r.state.fort_level(target)          # §15.82 current level (25.14 may have reduced it)
    mined = target in r.state.terrain.minefields                # defensive minefield belt
    # Morale is rolled FIRST (rule 15 order): each side's 17.4 roll adjusts its
    # Basic Morale by Cohesion, and the difference shifts the assault column (15.62).
    atk_m, atk_md, atk_surr = _adjusted_morale(r, armed_atk)
    # 17.26(b): a defender whose largest unit has Basic Morale +1 or better may NOT
    # shrug off a rolled SURR when the assaulting enemy fields at least three times
    # its strength (Enemy Raw Offensive Assault : Friendly Raw Defensive). The
    # cohesion-based 17.26(a) reprieve-void is handled per-unit in _adjusted_morale.
    overwhelms = (sum(u.raw_offense for u in armed_atk)
                  >= 3 * sum(u.raw_defense for u in armed_def))
    def_m, def_md, def_surr = _adjusted_morale(r, defenders, enemy_overwhelms=overwhelms)
    if atk_surr and def_surr:                                   # 17.25: mutual surrender is IGNORED --
        r.emit(EventKind.COMBAT_RESOLVED, side, actor,          # no assault occurs, both Engaged
               {"target": list(target), "attackers": [u.id for u in armed_atk],
                "defenders": [u.id for u in defenders], "surrender": "mutual-ignored",
                "differential": 0, "column": 0, "morale_shift": atk_m - def_m,
                "attacker_loss_pct": 0, "defender_loss_pct": 0,
                "attacker_captured": False, "defender_captured": False,
                "attacker_engaged": True, "retreat_hexes": 0},
               rng_draws=(*atk_md, *def_md))
        return
    if atk_surr or def_surr:                                    # rule 17.25: the stack surrenders
        _resolve_surrender(r, side, actor, target, armed_atk, defenders,
                           atk_surr, def_surr, atk_m - def_m, (*atk_md, *def_md))
        return
    ab, asm, db, dsm = r.d6(), r.d6(), r.d6(), r.d6()
    res = combat.resolve(
        attacker_raw=sum(u.raw_offense for u in armed_atk),
        defender_raw=sum(u.raw_defense for u in armed_def),     # unarmed defenders -> 0
        def_terrain=r.state.terrain.terrain[target], attack_feature=feature,
        atk_roll=ab * 10 + asm, def_roll=db * 10 + dsm,
        morale_shift=atk_m - def_m,
        attacker_ca_penalty=_combined_arms_penalty(armed_atk),      # rule 15.4
        defender_ca_penalty=_combined_arms_penalty(armed_def),
        attacker_size=max((u.stacking_points for u in armed_atk), default=0),  # 15.53
        defender_size=max((u.stacking_points for u in defenders), default=0),  # incl. pinned (15.12)
        fortification_level=fort, in_enemy_minefield=mined)
    r.emit(EventKind.COMBAT_RESOLVED, side, actor,
           {"target": list(target), "attackers": [u.id for u in armed_atk],
            "defenders": [u.id for u in defenders],
            "differential": res.differential, "column": res.column,
            "morale_shift": atk_m - def_m,
            "attacker_loss_pct": res.attacker_loss_pct,
            "defender_loss_pct": res.defender_loss_pct,
            "attacker_captured": res.attacker_captured,
            "defender_captured": res.defender_captured,
            "attacker_engaged": res.attacker_engaged,
            "retreat_hexes": res.retreat_hexes},
           rng_draws=(*atk_md, *def_md, ab, asm, db, dsm))
    # 15.83d: steps are removed to ABSORB the raw points lost, each step soaking up
    # its unit's close-assault rating (dca defending, oca attacking) worth of points.
    for uid, amount in _absorb_losses(defenders, res.defender_points_lost, lambda u: u.dca):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "defender"})
    for uid, amount in _absorb_losses(armed_atk, res.attacker_points_lost, lambda u: u.oca):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "attacker"})
    # Cohesion: 30%+ losses disorganize the involved units (rule 15.87). Recovery
    # (Reorganization Points, rule 20) is deferred, so Cohesion only falls -- flagged.
    if res.attacker_loss_pct >= 30:
        for u in armed_atk:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -3})
    if res.defender_loss_pct >= 30:
        for u in defenders:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -3})
    if res.retreat_hexes > 0:                                   # rule 15.8 / 15.82
        _retreat(r, side, actor, [d.id for d in defenders], armed_atk[0].hex, res.retreat_hexes)


def _combined_arms_penalty(units) -> int:
    """Combined arms (rule 15.4): tanks unsupported by an equal TOE of infantry /
    MG / heavy-weapons units lose Actual close-assault points -- 1 for every 1-3
    unsupported tank TOE points, capped at 4. Tanks only (recce and SP artillery,
    which have Armor Protection but are not tanks, are exempt). Off and def alike."""
    tank_toe = sum(u.strength for u in units if u.is_tank)
    if tank_toe == 0:
        return 0
    support = sum(u.strength for u in units
                  if u.is_combat and not u.is_tank and not u.is_armor and not u.is_gun)
    unsupported = max(0, tank_toe - support)
    return min(4, math.ceil(unsupported / 3))


def _honors_surrender(morale: int, cohesion: int, enemy_overwhelms: bool) -> bool:
    """Does a rolled SURR (17.4 Surrender column) actually stick? By 17.25 the stack
    Surrenders -- UNLESS its (largest) unit's Basic Morale is +1 or better, in which
    case 17.26 lets it treat the SURR as a mere -4 adjustment and fight on. That
    reprieve is voided, and the Surrender enforced, when either 17.26 exception holds:
    (a) the unit's Cohesion has collapsed to -11 or worse, or (b) the assaulting enemy
    brings at least three times the strength (Enemy Raw Offensive : Friendly Raw
    Defensive), passed in as `enemy_overwhelms`."""
    if morale < 1:
        return True
    return cohesion <= -11 or enemy_overwhelms


def _adjusted_morale(r: _Run, units, *,
                     enemy_overwhelms: bool = False) -> tuple[int, tuple[int, int], bool]:
    """Adjusted Morale of a close-assault stack (rule 15.6): the LARGEST unit's
    Basic Morale (17.32), plus the 17.4 modifier rolled at its Cohesion level, +1
    if Rommel is present (17.28), clamped to -3..+3 (17.23). Returns (morale, the
    two dice, surrendered). A SURR result eliminates the stack (17.25); the 17.26
    reprieve and its (a) cohesion / (b) enemy-3x exceptions are decided by
    _honors_surrender. When SURR is shrugged off it counts as the -4 penalty."""
    live = [u for u in units if u.strength > 0]
    if not live:
        return 0, (0, 0), False
    largest = max(live, key=lambda u: (u.stacking_points, u.strength))
    d1, d2 = r.d6(), r.d6()
    mod = combat_tables.morale_modifier(largest.cohesion, d1 * 10 + d2)
    surrendered = mod == "SURR" and _honors_surrender(
        largest.morale, largest.cohesion, enemy_overwhelms)
    if mod == "SURR":
        mod = -4
    m = largest.morale + mod + (1 if any("Rommel" in u.id for u in live) else 0)
    return max(-3, min(3, m)), (d1, d2), surrendered


def _resolve_surrender(r: _Run, side: Side, actor: str, target: Coord, attackers,
                       defenders, atk_surr: bool, def_surr: bool,
                       morale_shift: int, dice: tuple) -> None:
    """A side whose morale collapses to Surrender (17.25) is eliminated in place.
    Recorded as a normal COMBAT_RESOLVED + STEP_LOST so replay + conservation hold."""
    surr = "both" if (atk_surr and def_surr) else "attacker" if atk_surr else "defender"
    r.emit(EventKind.COMBAT_RESOLVED, side, actor,
           {"target": list(target), "attackers": [u.id for u in attackers],
            "defenders": [u.id for u in defenders], "surrender": surr,
            "differential": 0, "column": 0, "morale_shift": morale_shift,
            "attacker_loss_pct": 0, "defender_loss_pct": 0,
            "attacker_captured": False, "defender_captured": False,
            "attacker_engaged": False, "retreat_hexes": 0},
           rng_draws=dice)
    for u in (attackers if atk_surr else []) + (defenders if def_surr else []):
        cur = r.state.unit(u.id)
        if cur and cur.alive:
            r.emit(EventKind.STEP_LOST, side, actor,
                   {"unit_id": u.id, "amount": cur.strength, "role": "surrender"})


def _retreat(r: _Run, atk_side: Side, actor: str, defender_ids: list[str],
             attacker_hex: Coord, n: int) -> None:
    """Retreat the surviving defenders n hexes away from the attacker, toward the
    nearest friendly supply/city, never into enemy ZOC or enemy units (rule 15.82);
    each hex that cannot be retreated costs an extra 10% loss. The stack retreats
    together. Retreat CP cost (15.82) is not charged yet (flagged)."""
    survivors = [u for u in (r.state.unit(uid) for uid in defender_ids) if u and u.alive]
    if not survivors:
        return
    # Rule 15.82: a unit invested in a MAJOR CITY is not evicted -- it holds the
    # city (Tobruk/Bardia sit out the siege) rather than retreat or take losses.
    if r.state.terrain.terrain.get(survivors[0].hex) == Terrain.MAJOR_CITY:
        return
    def_side = survivors[0].side
    enemy_zoc, enemy_occ = tactics.enemy_zoc_and_occupied(r.state, def_side)
    friendly = frozenset(u.hex for u in r.state.living(def_side))
    blocked = (enemy_zoc - friendly) | enemy_occ
    supplies = [s.hex for s in r.state.active_supplies(def_side)]

    surv_ids = {u.id for u in survivors}

    def _fits(nb: Coord) -> bool:                    # the retreating stack must fit (rule 9.31)
        here = [x for x in r.state.units_at(nb) if x.side == def_side and x.id not in surv_ids]
        return stacking.within_hex_limit(here + survivors, r.state.terrain.terrain[nb])

    cur = survivors[0].hex
    path = [cur]                                      # the hexes crossed, for Breakdown Points
    done = 0
    for _ in range(n):
        cands = [nb for nb in neighbors(cur)
                 if nb in r.state.terrain.terrain and nb not in blocked
                 and distance(nb, attacker_hex) > distance(cur, attacker_hex)
                 and _fits(nb)]
        if not cands:
            break
        occupied = frozenset(u.hex for u in r.state.living(def_side))

        def _key(nb):
            sup = min((distance(nb, s) for s in supplies), default=0)
            return (nb in occupied, sup, -distance(nb, attacker_hex), nb)
        cur = min(cands, key=_key)
        path.append(cur)
        done += 1

    if done > 0:
        for u in survivors:
            payload = {"unit_id": u.id, "from": list(u.hex), "to": list(cur), "hexes": done}
            bp = tactics.breakdown_points_over(r.state, u, path)    # 21.22 retreat accrues BP
            if bp:
                payload["bp"] = bp
            r.emit(EventKind.UNIT_RETREATED, atk_side, actor, payload)
    for _ in range(n - done):                                   # 15.82: 10% per un-retreated hex
        for u in survivors:
            cur_u = r.state.unit(u.id)
            extra = math.ceil(0.10 * cur_u.strength)
            if extra > 0:
                r.emit(EventKind.STEP_LOST, atk_side, actor,
                       {"unit_id": u.id, "amount": min(extra, cur_u.strength), "role": "defender"})


def _has_ammo(state: GameState, unit, *, phasing: bool) -> bool:
    """Can this unit draw its Close-Assault ammunition right now (rule 32.21 / 50)?
    A non-mutating mirror of the _charge_ammo supply gate, used to detect the 15.15
    all-out-of-ammunition condition without expending anything."""
    return supply.plan_draw(state, unit, supply.AMMO,
                            supply.ammo_cost(unit, phasing=phasing, activity="assault")) is not None


def _defenders_capitulate(r: _Run, defenders) -> bool:
    """Hard surrender thresholds on an assaulted defending stack, ahead of the 17.4
    roll (15.88 -- units so afflicted automatically Surrender). Returns True when:
      - 15.15: EVERY defender is out of Close-Assault ammunition, so a cut-off, dry
        garrison capitulates en masse rather than defend on at zero strength; or
      - 15.88: the stack's largest unit's Cohesion has collapsed to -17 or worse
        (17.24 '-17 et seq'; 17.27 Largest Unit Rule)."""
    live = [u for u in defenders if u.strength > 0]
    if not live:
        return False
    largest = max(live, key=lambda u: (u.stacking_points, u.strength))
    if largest.cohesion <= -17:                                        # 15.88
        return True
    return all(not _has_ammo(r.state, u, phasing=False) for u in live)  # 15.15


def _charge_ammo(r: _Run, side: Side, actor: str, unit, *, phasing: bool,
                 activity: str = "assault") -> bool:
    draws = supply.plan_draw(r.state, unit, supply.AMMO,
                             supply.ammo_cost(unit, phasing=phasing, activity=activity))
    if draws is None:
        return False
    for sid, qty in draws:
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": sid, "commodity": supply.AMMO, "qty": qty, "unit_id": unit.id})
    return True


def _absorb_losses(units, points: int, rating_of) -> list[tuple[str, int]]:
    """Rule 15.83d: remove enough TOE steps to ABSORB the raw points lost. Each step
    soaks up its unit's close-assault rating worth of raw points, so a high-rated
    (elite) unit sheds fewer steps than a weak one for the same points. Steps come
    off the largest units first; a fractional remainder still costs a whole step
    (enough must be removed to fully absorb the loss). Units with no rating cannot
    absorb (they contribute nothing to the raw total either)."""
    out: list[tuple[str, int]] = []
    remaining = points
    for u in sorted(units, key=lambda x: -x.strength):
        if remaining <= 0:
            break
        rating = rating_of(u)
        if rating <= 0 or u.strength <= 0:
            continue
        take = min(u.strength, math.ceil(remaining / rating))
        out.append((u.id, take))
        remaining -= take * rating
    return out


def _record_control(r: _Run) -> None:
    for coord in r.state.terrain.terrain:
        occ = [u for u in r.state.units_at(coord) if u.is_combat]   # only combat units hold ground
        if not occ:
            continue
        sides = {u.side for u in occ}
        new = CONTROL_OF[next(iter(sides))] if len(sides) == 1 else r.state.control_of(coord)
        if new != r.state.control_of(coord):
            r.emit(EventKind.HEX_CONTROL_CHANGED, Side.SYSTEM, "SYSTEM",
                   {"coord": list(coord), "control": new.value})


BARDIA: Coord = (20, 77)          # C4321, east of Tobruk -> Axis Decisive Victory (61.8)


def _degree_of_success(r: _Run) -> tuple[int, int, bool, bool]:
    """The Axis high-water mark toward Tobruk, as a graded signal (rule 61.8 is a
    binary hold, but this scenario's interest is HOW FAR the Axis got -- the Race
    for Tobruk). Returns (advance %, closest-reach hexes, holds Tobruk, holds
    Bardia). Advance % = fraction of the opening Axis->Tobruk gap closed by the
    furthest Axis-controlled or Axis-occupied hex."""
    s = r.state
    tobruk = s.target_hex
    axis = [h for h, c in s.control.items() if c == Control.AXIS]
    axis += [u.hex for u in s.living(Side.AXIS)]
    reach = min((distance(h, tobruk) for h in axis), default=99)
    start = min((distance(u.hex, tobruk) for u in r.initial.living(Side.AXIS)), default=99)
    advance = max(0, min(100, round(100 * (start - reach) / max(1, start))))
    return advance, reach, s.control_of(tobruk) == Control.AXIS, s.control_of(BARDIA) == Control.AXIS


def _axis_win_reason(holds_bardia: bool) -> str:
    return ("Axis Decisive Victory: Tobruk and Bardia held (61.8)" if holds_bardia
            else "Axis Victory: Tobruk captured and held (61.8)")


def _victory(r: _Run) -> tuple[Side | None, str]:
    s = r.state
    advance, reach, holds_tobruk, holds_bardia = _degree_of_success(r)
    r.emit(EventKind.VICTORY_CHECKED, Side.SYSTEM, "SYSTEM",
           {"axis": advance, "allied": 100 - advance, "axis_reach": reach})
    if holds_tobruk:
        return Side.AXIS, _axis_win_reason(holds_bardia)
    if not s.living(Side.ALLIED):
        return Side.AXIS, "Axis victory by annihilation"
    if not s.living(Side.AXIS):
        return Side.ALLIED, "Allied victory by annihilation"
    return None, ""


def _final_decision(r: _Run) -> tuple[Side, str]:
    advance, reach, holds_tobruk, holds_bardia = _degree_of_success(r)
    if holds_tobruk:
        return Side.AXIS, _axis_win_reason(holds_bardia)
    if reach <= 2:
        return Side.ALLIED, f"Commonwealth marginal victory: Tobruk held but invested (Axis {advance}% of the way)"
    if advance >= 50:
        return Side.ALLIED, f"Commonwealth victory: Tobruk held, Axis reached within {reach} hexes ({advance}% advance)"
    return Side.ALLIED, f"Commonwealth decisive victory: Axis advance stalled {reach} hexes short ({advance}% advance)"


def determinism_signature(events: list[Event]) -> str:
    from .events import log_to_json
    return log_to_json(events)
