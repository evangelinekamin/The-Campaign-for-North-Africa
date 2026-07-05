"""Decision layer (brief §4.5, §8).

Phase 0 uses a *scripted* (non-LLM) policy so the engine is proven before any
token is spent. In Phase 1 an LLMPolicy with the same interface drops in,
receiving role-scoped observations and emitting the same Orders, which the engine
validates identically. The scripted policy may read full state and uses the same
tactical reachability the engine validates against (game.tactics).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import stacking, supply, tactics
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


@dataclass(frozen=True, slots=True)
class SupplyMoveOrder:
    supply_id: str
    to: Coord


Order = MoveOrder | AttackOrder | SupplyMoveOrder


class Policy:
    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        raise NotImplementedError

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        raise NotImplementedError

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        return []  # optional: relocate supply to follow the advance (rule 32.3)


class ScriptedPolicy(Policy):
    """Simple desert doctrine: the attacker presses toward the objective along the
    cheapest legal path; the defender holds and counter-attacks anything adjacent.
    Proposals are pre-filtered for legality, but the engine re-validates."""

    def __init__(self, attacker: Side = Side.AXIS):
        self.attacker = attacker

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        if side != self.attacker:
            return self._defender_moves(state, side)
        enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
        target = state.target_hex
        orders: list[MoveOrder] = []
        for u in state.living(side):
            if not u.is_combat:
                continue
            if u.cp_used == 0 and supply.plan_draw(
                    state, u, supply.FUEL, supply.fuel_cost(u)) is None:
                continue          # out of fuel -- don't propose a move the engine will reject
            reach = tactics.reachable_for(state, u, enemy_zoc, enemy_occupied)
            here_dist = distance(u.hex, target)
            # Barrage/anti-armor units seek a firing position -- adjacent to an
            # enemy (their range is 1) without falling back -- so support arms
            # actually engage (rules 12/14) instead of trailing the infantry.
            if u.barrage > 0 or u.anti_armor > 0:
                firing = [
                    c for c in reach
                    if c != u.hex and distance(c, target) <= here_dist
                    and self._stacking_ok(state, u, c)
                    and any(state.enemies_at(nb, side) for nb in neighbors(c))
                ]
                if firing:
                    dest = min(firing, key=lambda c: (distance(c, target), reach[c], c))
                    orders.append(MoveOrder(u.id, dest))
                    continue
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
            if not u.is_combat or supply.plan_draw(
                    state, u, supply.AMMO, supply.ammo_cost(u, phasing=True)) is None:
                continue          # out of ammo -- can't assault (don't propose it)
            for nb in neighbors(u.hex):
                if state.enemies_at(nb, side):
                    by_target.setdefault(nb, []).append(u.id)
        return [AttackOrder(tuple(ids), tgt) for tgt, ids in by_target.items()]

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        """Keep supply with the advance: relocate each fuelled dump (CPA 15) to the
        most-forward friendly combat unit it can reach, ending stacked with it
        (rule 32.33). Dumps thus leapfrog toward the objective behind the front."""
        combat_units = [u for u in state.living(side) if u.is_combat]
        if not combat_units:
            return []
        target = state.target_hex
        orders: list[SupplyMoveOrder] = []
        for su in state.active_supplies(side):
            if su.fuel < supply.SUPPLY_MOVE_FUEL:
                continue                              # no fuel to move (rule 32.24)
            reach = supply.reachable_moves(state, su)
            here = distance(su.hex, target)
            forward = [u.hex for u in combat_units
                       if u.hex in reach and u.hex != su.hex
                       and distance(u.hex, target) < here]
            if forward:
                dest = min(forward, key=lambda c: (distance(c, target), reach[c], c))
                orders.append(SupplyMoveOrder(su.id, dest))
        return orders

    # --- defender: hold the objective, sortie against exposed enemies ---------
    def _anchor_ids(self, state: GameState, side: Side) -> frozenset[str]:
        """Combat units holding (or, if none stands on it, covering) the objective.
        Anchors never vacate it -- the garrison that makes the position worth
        taking, so a reserve's sortie can never strip the objective bare."""
        target = state.target_hex
        combat = [u for u in state.living(side) if u.is_combat]
        holders = frozenset(u.id for u in combat if u.hex == target)
        if holders:
            return holders
        return frozenset(u.id for u in combat if distance(u.hex, target) == 1)

    def _is_exposed(self, state: GameState, enemy_stack) -> bool:
        """True if `enemy_stack` is UNSUPPORTED ARMOR (tanks whose non-tank support
        is deficient -- the engine's combined-arms test, rule 15.4) OR OUT OF SUPPLY
        (a combat unit in it cannot draw ammo -- supply.plan_draw is None)."""
        combat = [u for u in enemy_stack if u.is_combat]
        if not combat:
            return False
        tank_toe = sum(u.strength for u in combat if u.is_tank)
        support = sum(u.strength for u in combat
                      if not u.is_tank and not u.is_armor and not u.is_gun)
        if tank_toe > support:              # unsupported armor (mirror engine 15.4)
            return True
        return any(supply.plan_draw(state, u, supply.AMMO,
                                    supply.ammo_cost(u, phasing=True)) is None
                   for u in combat)         # cut off from ammo -- can't fight

    def _uncovers(self, state: GameState, side: Side, unit: Unit, dest: Coord) -> bool:
        """Would moving `unit` to `dest` leave the objective undefended -- no other
        friendly combat unit holding-or-covering it, and the mover not ending on
        its perimeter either?"""
        target = state.target_hex
        others_hold = any(u.is_combat and distance(u.hex, target) <= 1
                          for u in state.living(side) if u.id != unit.id)
        return not (others_hold or distance(dest, target) <= 1)

    def _defender_moves(self, state: GameState, side: Side) -> list[MoveOrder]:
        """A reserve (non-anchor mobile unit) sorties to a hex ADJACENT to an
        exposed enemy stack it can legally reach, without uncovering the objective.
        No exposed stack reachable -> HOLD (empty), never reckless."""
        enemy = tactics.other(side)
        exposed = sorted(h for h in {u.hex for u in state.living(enemy) if u.is_combat}
                         if self._is_exposed(state, state.enemies_at(h, side)))
        if not exposed:
            return []
        anchors = self._anchor_ids(state, side)
        enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
        orders: list[MoveOrder] = []
        for u in state.living(side):
            if not u.is_combat or u.id in anchors:
                continue
            if u.cp_used == 0 and supply.plan_draw(
                    state, u, supply.FUEL, supply.fuel_cost(u)) is None:
                continue          # out of fuel -- don't propose a move the engine rejects
            reach = tactics.reachable_for(state, u, enemy_zoc, enemy_occupied)
            best: tuple[tuple[int, float, Coord], Coord] | None = None
            for h in exposed:
                for c in neighbors(h):
                    if (c != u.hex and c in reach and self._stacking_ok(state, u, c)
                            and not self._uncovers(state, side, u, c)):
                        key = (distance(c, h), reach[c], c)
                        if best is None or key < best[0]:
                            best = (key, c)
            if best is not None:
                orders.append(MoveOrder(u.id, best[1]))
        return orders

    def _stacking_ok(self, state: GameState, unit: Unit, dest: Coord) -> bool:
        present = [u for u in state.units_at(dest) if u.side == unit.side]
        return stacking.within_hex_limit(present + [unit], state.terrain.terrain[dest])
