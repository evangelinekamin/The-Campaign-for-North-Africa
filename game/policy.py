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


@dataclass(frozen=True, slots=True)
class DemolitionOrder:
    """[54.14] Blow a supply dump. `unit_id` is the non-gun combat unit standing on it, paying one
    third of its basic CPA (rounded up); `extra_thirds` (0-2) buys +1 on the 54.17 die per extra
    third of CPA announced BEFORE the roll -- "the Player may adjust the die roll by announcing,
    before rolling the die, that he is expending an additional one-third or two-thirds"."""
    unit_id: str
    supply_id: str
    extra_thirds: int = 0


@dataclass(frozen=True, slots=True)
class BuildOrder:
    """[24.0] One construction project, initiated or continued in the Construction Segment.

    `item` is what is being built -- 'RAIL' (24.6: a new hex of the Alexandria-Mersa Matruh-Tobruk
    line, buildable only by the two New Zealand Railroad Construction companies, 24.61) or 'DUMP'
    (24.9: a supply dump, buildable by any one TOE Strength Point of any type, for 3 CP and 20
    Store Points). `unit_ids` are the units doing the work -- more than one because 24.62 makes the
    PAIR of NZRRC companies twice as fast as one. `hex` is the site.

    Everything else the rule demands -- who may build (24.61/23.13), whether the site is the next
    hex of the surveyed line (24.67), whether the enemy holds it (24.65), the Store Points on hand
    (24.64/24.13), the weather (24.22) -- the engine re-validates (game.engine._construction), like
    every other order."""
    item: str                       # 'RAIL' (24.6) | 'DUMP' (24.9)
    hex: Coord
    unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MotorizeOrder:
    """[32.32] Attach or detach the lorries under a supply dump, in the Organization Phase.

    `truck_ids` names the Medium formations (32.51) the thirty Motorization Points are drawn from,
    in priority order -- the engine takes what is free from each in turn until it has its thirty
    (game.supply.column_legs) and REJECTS the order if they cannot muster them between them ("a
    supply unit not assigned the minimum necessary number of Motorization Points may not be moved").
    An EMPTY `truck_ids` is the detach: stand the column down and give the lorries back to the
    freight relay.

    This is the order that makes the desert column cost something. Every one issued is thirty Truck
    Points out of the same finite park (60.33/60.43) that hauls the army's fuel and ammunition, for
    as long as it stands -- 32.32 hinges attach AND detach on the Organization Phase, so it is a
    STANDING RESERVATION, not a fare paid per hex."""
    supply_id: str
    truck_ids: tuple[str, ...] = ()


Order = (MoveOrder | AttackOrder | SupplyMoveOrder | TruckOrder | DemolitionOrder | BuildOrder
         | MotorizeOrder)


class Policy:
    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        raise NotImplementedError

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        raise NotImplementedError

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        return []  # optional: relocate supply to follow the advance (rule 32.3)

    def motorization(self, state: GameState, side: Side) -> list[MotorizeOrder]:
        return []  # optional: detail lorries to carry a dump, or stand them down (rule 32.32)

    def retreat_before_assault(self, state: GameState, side: Side,
                               pinned: frozenset[str]) -> list[MoveOrder]:
        return []  # optional: slip non-phasing units out of an assault (rule 13.0)

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        return []  # optional: haul supply forward with 2nd/3rd-line truck convoys (rule 48 V.J)

    def demolition(self, state: GameState, side: Side) -> list[DemolitionOrder]:
        return []  # optional: blow your own dump rather than lose it to the enemy (rule 54.14)

    def construction(self, state: GameState, side: Side) -> list[BuildOrder]:
        return []  # optional: build railroad / supply dumps in the Construction Segment (rule 24)

    def continual_movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        """Continual Movement go/no-go (rule 8.2): return the intended continuation moves for the
        NEXT exploitation pulse (a non-empty list = press on; [] = the OpStage portion ends). Only
        its emptiness gates the pulse; the pulse's actual moves are re-proposed through movement(),
        gated by the engine's 8.23 two-hex exploitation eligibility. Base [] declines, so every
        current scenario runs zero pulses and stays byte-identical."""
        return []

    def reserve_designation(self, state: GameState, side: Side) -> list[str]:
        return []  # optional: hold units back in Reserve before Movement (rule 18.12 / 48 V.G)

    def reserve_release(self, state: GameState, side: Side) -> list[str]:
        return []  # optional: release reserves at the inter-pulse Release Segment (rule 18.13 / 48 V.H.4)

    def react_to(self, state: GameState, side: Side, trigger: str,
                 eligible: frozenset[str]) -> list[MoveOrder]:
        return []  # optional: a non-phasing motorized unit slides aside as an enemy moves adjacent (rule 8.5)


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
        target = state.objective_for(side)   # attacker's objective; Axis east, offensive CW west
        orders: list[MoveOrder] = []
        for u in state.living(side):
            if not u.is_combat:
                continue
            if supply.in_hex_draw(
                    state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
                continue          # out of fuel -- every move pays (49.13); don't propose a reject
            reach = supply.affordable_reach(                             # 49.15: only fundable hexes
                state, u, tactics.reachable_for(state, u, enemy_zoc, enemy_occupied))
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
            if not u.is_combat or supply.in_hex_draw(
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
        target = state.objective_for(side)   # dumps leapfrog toward the side's own objective
        orders: list[SupplyMoveOrder] = []
        for su in state.active_supplies(side):
            if su.base:
                continue                              # a strategic rear base (rule 57) is immobile
                                                      # -- the front hauls FROM it, it never advances
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
        """Run the faithful multi-hop forward relay (rule 53.14 / 54.16, game.relay.campaign_truck_orders):
        the competent baseline's logistics -- load at the rear port, bucket-brigade the tonnage forward
        LEG BY LEG reloading at each intermediate dump, and FOUND dumps (54.11) on the spearhead's own
        hexes so the supply network follows the advance. Doctrine, not an engine mandate (53.14 is
        "recommended ... not a rule"), but the doctrine of any competent quartermaster (54.16: the dump
        network is the logistics commander's "top priority") -- so the deterministic baseline owes it.

        Replaces the earlier single-hop shuttle: an abstract-era stand-in that could only reach one convoy
        hop from the rear port and so stranded every army the instant it advanced past its start-line
        dumps. The relay lives in game.relay, shared by every competent built-in policy (a lazy import
        because relay reads this module's TruckOrder/BuildOrder dataclasses)."""
        from . import relay
        return relay.campaign_truck_orders(state, side)

    def construction(self, state: GameState, side: Side) -> list[BuildOrder]:
        """[24.9] Construct the forward dump at the head of the advance (game.relay.build_the_chain): turn
        the heap the convoy dropped into a CONSTRUCTED dump the lorries can lift out of again, so the
        bucket brigade grows one hop longer. The load-bearing companion to truck_orders -- the relay only
        reloads from constructed/staging/port dumps, so without this the chain cannot extend past the port
        and 54.16's viable dump network never forms."""
        from . import relay
        return relay.build_the_chain(state, side)

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
            if supply.in_hex_draw(
                    state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
                continue                       # no fuel -- every move pays (49.13); don't propose it
            reach = supply.affordable_reach(                             # 49.15: only fundable hexes
                state, u, tactics.reachable_for(state, u, enemy_zoc, enemy_occupied))
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
            if supply.in_hex_draw(
                    state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
                continue          # out of fuel -- every move pays (49.13); don't propose a reject
            reach = supply.affordable_reach(                             # 49.15: only fundable hexes
                state, u, tactics.reachable_for(state, u, enemy_zoc, enemy_occupied))
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


class StormPolicy(ScriptedPolicy):
    """A strong-general storming proxy (zero tokens) that isolates the garrison-STARVATION
    mechanism (rule 15.15) from the LLM staff's assault timidity AND from the Axis desert-supply
    death-spiral. It is the SCRIPTED instrument for proving that the Tobruk harbour choke is
    load-bearing: with the sea lifeline cut (port bombed to Efficiency 0), a sustained storm
    drains the garrison's finite dump to zero and forces the 15.15 dry-stack capitulation --
    the historical siege, where the sea lane decides the fortress -- rather than the brute-force
    casualty-destruction path. Three doctrines layer over ScriptedPolicy's attacker branch:

      - MOVEMENT drives every fuelled combat unit onto the objective's perimeter and HOLDS it
        there (never drifting back), and OCCUPIES the objective the instant its garrison vacates
        it -- the 15.15 surrender eliminates the garrison and leaves the hex empty, so a stormer
        must step on to flip control (rule 12.6).
      - a SUPPLY BRIDGE relocates each field dump to the rearmost combat unit that has outrun its
        fuel, keeping the advancing column connected instead of leapfrogging every dump to the
        front and stranding the army in a supply desert (the ScriptedPolicy attacker's failure
        mode: the spearhead reaches the wall, the dumps follow it, the spearhead dies, and the
        rear strands out of fuel with the dumps beyond half-CPA).
      - COMBAT assaults the objective EVERY stage. While the garrison can still draw Close-Assault
        ammunition it commits a MINIMAL spearhead (drawing the garrison's ammo down one assault at
        a time while a resupplied reserve is kept armed); the instant every defender on the
        objective is dry (the exact 15.15 condition the engine checks) it throws the whole
        perimeter in as one assault -- the capitulation trigger.

    Reads full state, exactly like ScriptedPolicy; every proposal is re-validated by the engine.
    `attacker` is the storming side (Side.AXIS for the siege)."""

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        if side != self.attacker:
            return self._defender_moves(state, side)
        target = state.target_hex
        perim = frozenset(neighbors(target))
        enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
        takeable = not any(e.is_combat for e in state.enemies_at(target, side))
        orders: list[MoveOrder] = []
        claimed = False
        for u in state.living(side):
            if not u.is_combat:
                continue
            if supply.in_hex_draw(state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
                continue          # out of fuel -- every move pays (49.13); don't propose a reject
            reach = supply.affordable_reach(                             # 49.15: only fundable hexes
                state, u, tactics.reachable_for(state, u, enemy_zoc, enemy_occupied))
            if (takeable and not claimed and target in reach
                    and self._stacking_ok(state, u, target)):
                orders.append(MoveOrder(u.id, target))     # claim the vacated objective (control flip)
                claimed = True
                continue
            if u.hex == target or u.hex in perim:
                continue                                   # already storming -- HOLD the perimeter
            cands = [c for c in reach if c != u.hex and self._stacking_ok(state, u, c)
                     and distance(c, target) < distance(u.hex, target)]
            if cands:
                # prefer stepping onto the perimeter (esp. an enemy dump hex, to trace-block it)
                dest = min(cands, key=lambda c: (c not in perim, distance(c, target), reach[c], c))
                orders.append(MoveOrder(u.id, dest))
        return orders

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        if side != self.attacker:
            return ScriptedPolicy.supply_orders(self, state, side)
        target = state.target_hex
        stranded = sorted(
            (u for u in state.living(side) if u.is_combat
             and supply.in_hex_draw(state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None),
            key=lambda u: distance(u.hex, target))         # bridge the nearest-to-front gap first
        orders: list[SupplyMoveOrder] = []
        claimed: set[Coord] = set()
        for su in state.active_supplies(side):
            if su.fuel < supply.SUPPLY_MOVE_FUEL or state.port_at(su.hex) is not None:
                continue                                   # no fuel to move, or a harbour dump stays put
            reach = supply.reachable_moves(state, su)
            pick = next((u for u in stranded if u.hex in reach
                         and u.hex != su.hex and u.hex not in claimed), None)
            if pick is not None:
                claimed.add(pick.hex)
                orders.append(SupplyMoveOrder(su.id, pick.hex))
        # nobody stranded -> fall back to the leapfrog-forward bridge (rule 32.3)
        return orders or ScriptedPolicy.supply_orders(self, state, side)

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        if side != self.attacker:
            return ScriptedPolicy.combat(self, state, side)
        target = state.target_hex
        armed = [u for u in state.living(side)
                 if u.is_combat and target in set(neighbors(u.hex))
                 and supply.in_hex_draw(state, u, supply.AMMO,
                                        supply.ammo_cost(u, phasing=True)) is not None]
        elsewhere = [a for a in ScriptedPolicy.combat(self, state, side) if a.target != target]
        if not armed:
            return elsewhere                               # no adjacent ammo-capable unit this stage
        defenders = [u for u in state.enemies_at(target, side) if u.strength > 0]
        dry = bool(defenders) and all(                     # the exact 15.15 condition (mirrors _has_ammo)
            supply.in_hex_draw(state, u, supply.AMMO,
                               supply.ammo_cost(u, phasing=False, activity="assault")) is None
            for u in defenders)
        if dry:                                            # TRIGGER: throw the whole perimeter in (15.15)
            return [AttackOrder(tuple(u.id for u in armed), target)] + elsewhere
        # DRAIN: a minimal spearhead draws the garrison's Close-Assault ammo; the reserve stays armed.
        spear = min(armed, key=lambda u: (u.strength, u.id))
        return [AttackOrder((spear.id,), target)] + elsewhere
