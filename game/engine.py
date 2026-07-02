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

from . import combat, combat_tables, stacking, supply, tactics
from .apply import apply
from .events import Control, Event, EventKind, Phase, Side
from .hexmap import distance, is_adjacent, neighbors
from .invariants import check
from .policy import AttackOrder, MoveOrder, Policy
from .state import Coord, GameState

CONTROL_OF: dict[Side, Control] = {Side.AXIS: Control.AXIS, Side.ALLIED: Control.ALLIED}


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
    while True:
        _weather(r)
        _reinforcements(r)
        for side in (Side.AXIS, Side.ALLIED):
            r.go(Phase.MOVEMENT, side)
            _movement(r, policies[side], side)
            _supply_movement(r, policies[side], side)   # supply follows the army (32.3)
            r.go(Phase.COMBAT, side)
            _combat(r, policies, side)
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


def _weather(r: _Run) -> None:
    die = r.d6()
    label, modifier = {
        1: ("storm", -2), 2: ("rain", -1), 3: ("clear", 0),
        4: ("clear", 0), 5: ("clear", 0), 6: ("hot", 0),
    }[die]
    r.emit(EventKind.WEATHER_ROLLED, Side.SYSTEM, "SYSTEM",
           {"weather": label, "move_modifier": modifier}, rng_draws=(die,))


def _movement(r: _Run, policy: Policy, side: Side) -> None:
    actor = f"{side.value}/Front"
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(r.state, side)
    for order in policy.movement(r.state, side):
        u = r.state.unit(order.unit_id)
        if u is None or not u.alive or u.side != side:
            _reject(r, side, actor, order, "no such living unit under this command")
            continue
        # Re-validate against current state — earlier moves this phase count.
        reach = tactics.reachable_for(r.state, u, enemy_zoc, enemy_occupied)
        if order.to == u.hex or order.to not in reach:
            _reject(r, side, actor, order,
                    "destination unreachable within CPA or blocked by ZOC")
            continue
        present = [x for x in r.state.units_at(order.to) if x.side == side]
        if not stacking.within_hex_limit(present + [u], r.state.terrain.terrain[order.to]):
            _reject(r, side, actor, order, "destination over stacking limit")
            continue
        if u.cp_used == 0:                          # first move this OpStage pays fuel (32.23)
            draws = supply.plan_draw(r.state, u, supply.FUEL, supply.fuel_cost(u))
            if draws is None:
                _reject(r, side, actor, order, "out of supply: no fuel in range")
                continue
            for sid, qty in draws:
                r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                       {"supply_id": sid, "commodity": supply.FUEL, "qty": qty, "unit_id": u.id})
        r.emit(EventKind.UNIT_MOVED, side, actor,
               {"unit_id": u.id, "from": list(u.hex), "to": list(order.to),
                "cp_spent": reach[order.to]})


def _reject(r: _Run, side: Side, actor: str, order: MoveOrder, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "move", "unit_id": order.unit_id, "to": list(order.to),
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


def _other(side: Side) -> Side:
    return Side.ALLIED if side is Side.AXIS else Side.AXIS


def _combat(r: _Run, policies: dict, side: Side) -> None:
    """One Combat Segment (rule 11.0), the Phasing side = `side`. Barrage and Anti-
    Armor are fought by BOTH players (their losses land before Close Assault); then
    the Phasing player Close Assaults. Retreat-Before-Assault (13) is deferred."""
    enemy = _other(side)
    pinned: set[str] = set()          # units Pinned by barrage this segment (12.44)
    _barrage_step(r, side, enemy, pinned)
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
            armed = [u for u in firers if _charge_ammo(r, firing, actor, u, phasing=is_phasing)]
            raw = sum(u.raw_barrage for u in armed)
            target_unit = _barrage_target(state0.enemies_at(tgt, firing))
            if raw <= 0 or target_unit is None:
                continue
            cls = _barrage_class(target_unit)
            d1, d2 = r.d6(), r.d6()
            pin, loss = combat_tables.barrage_result(
                cls, combat.actual_points(raw, False), d1 * 10 + d2)
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
            armed = [u for u in firers if _charge_ammo(r, firing, actor, u, phasing=is_phasing)]
            raw = sum(u.raw_anti_armor for u in armed)
            if raw <= 0:
                continue
            d1, d2 = r.d6(), r.d6()
            dmg = combat_tables.anti_armor_damage(combat.actual_points(raw, False),
                                                   d1 * 10 + d2, phasing=is_phasing)
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
    armed_def = [u for u in defenders
                 if u.id not in pinned and _charge_ammo(r, side, actor, u, phasing=False)]

    # Close Assault via the real differential engine (rule 15 / §15.79 CRT).
    feature = r.state.terrain.hexsides.get((armed_atk[0].hex, target))  # §15.33
    # Morale is rolled FIRST (rule 15 order): each side's 17.4 roll adjusts its
    # Basic Morale by Cohesion, and the difference shifts the assault column (15.62).
    atk_m, atk_md, atk_surr = _adjusted_morale(r, armed_atk)
    def_m, def_md, def_surr = _adjusted_morale(r, defenders)
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
        attacker_strength=sum(u.strength for u in armed_atk),
        defender_strength=sum(u.strength for u in defenders),   # all defenders take losses
        def_terrain=r.state.terrain.terrain[target], attack_feature=feature,
        atk_roll=ab * 10 + asm, def_roll=db * 10 + dsm,
        morale_shift=atk_m - def_m,
        attacker_ca_penalty=_combined_arms_penalty(armed_atk),      # rule 15.4
        defender_ca_penalty=_combined_arms_penalty(armed_def),
        attacker_size=max((u.stacking_points for u in armed_atk), default=0),  # 15.53
        defender_size=max((u.stacking_points for u in defenders), default=0))  # incl. pinned (15.12)
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
    for uid, amount in _spread_losses(defenders, res.defender_steps_lost):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "defender"})
    for uid, amount in _spread_losses(armed_atk, res.attacker_steps_lost):
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


def _adjusted_morale(r: _Run, units) -> tuple[int, tuple[int, int], bool]:
    """Adjusted Morale of a close-assault stack (rule 15.6): the LARGEST unit's
    Basic Morale (17.32), plus the 17.4 modifier rolled at its Cohesion level, +1
    if Rommel is present (17.28), clamped to -3..+3 (17.23). Returns (morale, the
    two dice, surrendered). A SURR result eliminates the stack (17.25) unless its
    largest unit has Basic Morale >= +1 (17.26 exception), in which case it is taken
    as the -4 penalty. The Cohesion<=-11 / enemy-3x sub-conditions of 17.26 are
    deferred + flagged."""
    live = [u for u in units if u.strength > 0]
    if not live:
        return 0, (0, 0), False
    largest = max(live, key=lambda u: (u.stacking_points, u.strength))
    d1, d2 = r.d6(), r.d6()
    mod = combat_tables.morale_modifier(largest.cohesion, d1 * 10 + d2)
    surrendered = mod == "SURR" and largest.morale < 1
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
        done += 1

    if done > 0:
        for u in survivors:
            r.emit(EventKind.UNIT_RETREATED, atk_side, actor,
                   {"unit_id": u.id, "from": list(u.hex), "to": list(cur), "hexes": done})
    for _ in range(n - done):                                   # 15.82: 10% per un-retreated hex
        for u in survivors:
            cur_u = r.state.unit(u.id)
            extra = math.ceil(0.10 * cur_u.strength)
            if extra > 0:
                r.emit(EventKind.STEP_LOST, atk_side, actor,
                       {"unit_id": u.id, "amount": min(extra, cur_u.strength), "role": "defender"})


def _charge_ammo(r: _Run, side: Side, actor: str, unit, *, phasing: bool) -> bool:
    draws = supply.plan_draw(r.state, unit, supply.AMMO,
                             supply.ammo_cost(unit, phasing=phasing))
    if draws is None:
        return False
    for sid, qty in draws:
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": sid, "commodity": supply.AMMO, "qty": qty, "unit_id": unit.id})
    return True


def _spread_losses(units, total: int) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    remaining = total
    for u in sorted(units, key=lambda x: -x.strength):
        if remaining <= 0:
            break
        take = min(remaining, u.strength)
        if take > 0:
            out.append((u.id, take))
            remaining -= take
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
