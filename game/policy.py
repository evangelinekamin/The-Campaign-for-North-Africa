"""Decision layer (brief §4.5, §8).

Phase 0 uses a *scripted* (non-LLM) policy so the engine is proven before any
token is spent. In Phase 1 an LLMPolicy with the same interface drops in,
receiving role-scoped observations and emitting the same Orders, which the engine
validates identically. The scripted policy may read full state and uses the same
tactical reachability the engine validates against (game.tactics).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import observation, stacking, supply, tactics
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


@dataclass(frozen=True, slots=True)
class TruckOrder:
    """One truck-convoy order (rule 48 Stage V.J): optionally LOAD `load` ({commodity:
    qty}) from the dump `load_from` at the truck's hex, MOVE to `to`, then UNLOAD `unload`
    into the dump `unload_to` at the destination. Any leg may be omitted (None) so a bare
    load, a bare relocation, or a full port->forward relay all fit one order shape."""
    truck_id: str
    load_from: str | None = None
    load: dict | None = None
    to: Coord | None = None
    unload_to: str | None = None
    unload: dict | None = None


Order = MoveOrder | AttackOrder | SupplyMoveOrder | TruckOrder


class Policy:
    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        raise NotImplementedError

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        raise NotImplementedError

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        return []  # optional: relocate supply to follow the advance (rule 32.3)

    def retreat_before_assault(self, state: GameState, side: Side,
                               pinned: frozenset[str]) -> list[MoveOrder]:
        return []  # optional: slip non-phasing units out of an assault (rule 13.0)

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        return []  # optional: haul supply forward with 2nd/3rd-line truck convoys (rule 48 V.J)


class ScriptedPolicy(Policy):
    """Simple desert doctrine: the attacker presses toward the objective along the
    cheapest legal path; the defender holds and counter-attacks anything adjacent.
    Proposals are pre-filtered for legality, but the engine re-validates.

    `attacker` is the SCENARIO'S attacking side, not the side this policy plays: the
    policy attacks when asked to move for `attacker` and otherwise defends (holds +
    sorties). So a Commonwealth defender in an Axis-attacker scenario is
    ScriptedPolicy(attacker=Side.AXIS) -- NOT ScriptedPolicy(Side.ALLIED), which sets
    attacker=ALLIED and silently makes the Commonwealth run the attacker branch."""

    def __init__(self, attacker: Side = Side.AXIS):
        self.attacker = attacker

    def declare_ab(self, state: GameState, stage: int) -> Side:
        """Initiative Declaration (rule 7.11/7.12): the scripted default takes the DOUBLE-MOVE
        -- the Initiative side moves LAST in Operations Stage 2 and FIRST otherwise, so across
        the stage 2->3 boundary it lands two consecutive operational pulses (7.12). Returns who
        moves FIRST this stage. The engine re-validates and emits INITIATIVE_DECLARED."""
        init = state.initiative_side
        return tactics.other(init) if stage == 2 else init

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
                    state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
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
        # When defending, the objective's anchor HOLDS (same exemption
        # _defender_moves uses): it never sorties out of the fortress to counter-
        # assault, so the garrison keeps its terrain/fort defense (rule 15.82).
        anchors = self._anchor_ids(state, side) if side != self.attacker else frozenset()
        by_target: dict[Coord, list[str]] = {}
        for u in state.living(side):
            if u.id in anchors:
                continue
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
            if state.port_at(su.hex) is not None:
                continue                              # a harbour dump stays put -- the port
                                                      # is where convoys land; trucks haul it
                                                      # forward (rule 55/53.14), not this bridge
            reach = supply.reachable_moves(state, su)
            here = distance(su.hex, target)
            forward = [u.hex for u in combat_units
                       if u.hex in reach and u.hex != su.hex
                       and distance(u.hex, target) < here]
            if forward:
                dest = min(forward, key=lambda c: (distance(c, target), reach[c], c))
                orders.append(SupplyMoveOrder(su.id, dest))
        return orders

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        """Shuttle the 2nd/3rd-line truck pool between the rear supply port and the front
        (rule 48 V.J / 53.14). Each formation plies a two-beat run:

          - AT the rear port dump: LOAD a run of AMMO and FUEL (splitting its 54.2 capacity
            between the two -- the front needs both to press an assault, and the anchored
            harbour is the only place they land) and deliver it in one hop to the nearest
            friendly dump strictly closer to the objective, depositing everything bar a
            return-trip reserve of its own cargo fuel (49.18 -- a truck burns cargo fuel to
            move, so it must carry enough home to come back and reload).
          - AWAY from the port: drive back to it (on the retained reserve) to reload.

        Because a formation only ever spends fuel it is carrying and always keeps its return
        reserve, it never strands empty in the desert; it idles AT the port when the front has
        outrun its one-hop reach. Every hop burns cargo fuel, so the further Tobruk pulls
        ahead of Tripoli the more of each run the trucks eat in transit and the less arrives --
        the faithful Tripoli->front haulage bottleneck. The script only routes; it never bends
        a magnitude (capacity 54.2, burn 49.18, reach 53.22 all come from game.supply)."""
        base = self._truck_base(state, side)
        if base is None:
            return []
        target = state.target_hex
        orders: list[TruckOrder] = []
        for t in state.trucks:
            if t.side != side:
                continue
            reach = supply.reachable_truck_moves(state, t)
            if t.hex != base.hex:                     # RETURN leg -- head home to reload
                step = self._truck_step(reach, t.hex, base.hex)
                if step is not None and t.fuel >= supply.truck_move_fuel(t, reach[step]):
                    orders.append(TruckOrder(t.id, to=step))
                continue
            if base.fuel <= 0 and base.ammo <= 0:
                continue                              # nothing at the port to lift
            here = distance(t.hex, target)
            forward = [s for s in state.supplies
                       if s.side == side and not s.is_dummy and s.hex != t.hex
                       and s.hex in reach and distance(s.hex, target) < here]
            if not forward:
                continue                              # front outran the pool -- idle at port
            dest = min(forward, key=lambda s: (distance(s.hex, target), reach[s.hex], s.id))
            out = supply.truck_move_fuel(t, reach[dest.hex])
            cap = supply.truck_capacity(t.truck_class)
            half = t.points / 2                       # split the load: half ammo, half fuel
            ammo = min(base.ammo, int(half * cap["AMMO"]))
            fuel = min(base.fuel, int(half * cap["FUEL"]))
            fuel_deliver = fuel - 3 * out             # keep 2x the one-way burn to get home
            if fuel_deliver <= 0:                     # not enough fuel to make the round trip
                continue
            load = {"FUEL": fuel}
            unload = {"FUEL": fuel_deliver}
            if ammo > 0:
                load["AMMO"] = ammo
                unload["AMMO"] = ammo
            orders.append(TruckOrder(t.id, load_from=base.id, load=load,
                                     to=dest.hex, unload_to=dest.id, unload=unload))
        return orders

    def _truck_base(self, state: GameState, side: Side):
        """The rearmost WORKING supply port's built-in dump -- the truck pool's reload point
        (where the naval convoy lands). None if the side fields no working port."""
        ports = [p for p in state.ports if p.side == side and p.eff > 0]
        if not ports:
            return None
        base = max(ports, key=lambda p: (distance(p.hex, state.target_hex), p.id))
        return next((s for s in state.supplies if s.side == side and not s.is_dummy
                     and s.hex == base.hex), None)

    def _truck_step(self, reach: dict, here: Coord, dest: Coord) -> Coord | None:
        """The reachable hex nearest `dest` (a single Truck Convoy Phase move toward it), or
        None if the truck is already as close as it can get."""
        step = min(reach, key=lambda c: (distance(c, dest), reach[c], c))
        return step if step != here else None

    def retreat_before_assault(self, state: GameState, side: Side,
                               pinned: frozenset[str]) -> list[MoveOrder]:
        """Elastic desert defense (rule 13.0): when defending, slip each non-anchor,
        UNPINNED combat unit that is in contact with the phasing enemy out of the
        assault -- to the cheapest reachable hex that is itself out of contact --
        while the garrison (anchors) and any Pinned unit stay and are assaulted. The
        attacking side never retreats before its own assault. Units at Cohesion -26
        or worse may not retreat (13.1); the engine re-validates every proposal."""
        if side == self.attacker:
            return []                          # the attacker presses on; it does not slip
        anchors = self._anchor_ids(state, side)
        enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
        orders: list[MoveOrder] = []
        for u in state.living(side):
            if (not u.is_combat or u.id in anchors or u.id in pinned
                    or u.cohesion <= -26):
                continue
            if not self._in_contact(state, side, u.hex):
                continue                       # only units about to be assaulted bother to slip
            if u.cp_used == 0 and supply.plan_draw(
                    state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
                continue                       # no fuel to move -- don't propose it
            reach = tactics.reachable_for(state, u, enemy_zoc, enemy_occupied)
            escapes = [c for c in reach
                       if c != u.hex and self._stacking_ok(state, u, c)
                       and not self._in_contact(state, side, c)]
            if escapes:
                orders.append(MoveOrder(u.id, min(escapes, key=lambda c: (reach[c], c))))
        return orders

    def _in_contact(self, state: GameState, side: Side, hex_: Coord) -> bool:
        """True if `hex_` is adjacent to an enemy combat unit -- a hex that would be
        (or expose the unit to) a close assault this segment."""
        return any(e.is_combat for nb in neighbors(hex_)
                   for e in state.enemies_at(nb, side))

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

    def _is_exposed(self, state: GameState, side: Side, enemy_hex: Coord,
                    sighted: frozenset[Coord] | set[Coord]) -> bool:
        """True if the enemy stack on `enemy_hex` looks exposed by what THIS side can
        LEGALLY observe (rule 3.6 fog of presence) -- never the enemy's private
        supply/ammo ledger or hidden tank/support composition, which no real
        commander can see (game.observation fogs enemy strength and presence). Two
        signals, both read straight off the map:
          - the stack is SIGHTED (within sighting range of a friendly unit), and
          - it is ISOLATED -- no other SIGHTED enemy stack in an adjacent hex to
            support it, a lone forward stack a reserve can pounce on. Support on an
            UNSIGHTED neighbour does not count: a commander cannot see it, so it
            cannot stay his sortie (the isolation test itself must respect the fog).
        `sighted` is game.observation._sighted_hexes(state, side), passed in so the
        defender and the observation share ONE fog seam."""
        if enemy_hex not in sighted:
            return False
        return not any(nb in sighted and state.enemies_at(nb, side)
                       for nb in neighbors(enemy_hex))

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
        sighted = observation._sighted_hexes(state, side)   # the legal fog seam
        exposed = sorted(h for h in {u.hex for u in state.living(enemy) if u.is_combat}
                         if self._is_exposed(state, side, h, sighted))
        if not exposed:
            return []
        anchors = self._anchor_ids(state, side)
        enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
        orders: list[MoveOrder] = []
        for u in state.living(side):
            if not u.is_combat or u.id in anchors:
                continue
            if u.cp_used == 0 and supply.plan_draw(
                    state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
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
