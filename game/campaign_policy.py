"""The scripted policies for the FULL campaign -- both sides' campaign-only overrides that make
the desert war SEE-SAW instead of one player sandbagging for 111 turns:

  * CampaignCommonwealthPolicy -- a defender that goes over to the offensive on the historical
    Game-Turn windows (Operation Compass, Crusader, Second Alamein), advancing toward
    objective_for(ALLIED) (Benghazi, the Axis rear, far WEST) and culminating where it outruns
    its supply; between offensives it holds and gives ground.
  * CampaignAxisPolicy -- the base attacker PLUS the multi-hop coastal supply haul
    (campaign_truck_orders) that lets the Panzerarmee fight east of Benghazi at all: the lean
    truck pool relays Benghazi's landed tonnage forward LEG BY LEG along the seeded staging
    dumps (rule 60.34), where the shared single-hop base relay can only shuttle the port.

Campaign-ONLY: rommels_arrival / siege_of_tobruk keep the base ScriptedPolicy (whose byte-locked
truck relay they seed trucks through), so their event streams stay byte-identical. Neither the
base ScriptedPolicy.truck_orders/supply_orders nor game.staff_policy is touched; all new haul
logic lives in the module-level campaign_truck_orders below.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from . import supply
from .events import Side
from .hexmap import Coord, distance
from .policy import AttackOrder, MoveOrder, ScriptedPolicy, SupplyMoveOrder, TruckOrder
from .scenario import _CONVOY_SPLIT_56_22
from .state import GameState


@dataclass(frozen=True)
class OffensiveSchedule:
    """The Game-Turns the Commonwealth is on the offensive (inclusive windows on state.turn).
    Empty windows -> never offensive -> byte-identical to the pure defender."""
    windows: tuple[tuple[int, int], ...] = ()

    def is_offensive(self, gt: int) -> bool:
        return any(a <= gt <= b for a, b in self.windows)


# The three Commonwealth offensives of the desert war on the campaign calendar (game.calendar:
# GT1 = Sep 1940, 4 GT/month): Operation Compass (Dec 1940 - Feb 1941, destroys the 10th Army and
# reaches El Agheila), Operation Crusader (Nov 1941 - Jan 1942, relieves Tobruk), Second El Alamein
# (Oct - Dec 1942, the decisive drive). Cross-checked to the game's own scenario start-turns
# (Rommel GT20/26, Crusader GT57, El Alamein GT102).
COMPASS = (13, 22)
CRUSADER = (57, 64)
ALAMEIN = (102, 111)
CAMPAIGN_CW_OFFENSIVES = OffensiveSchedule((COMPASS, CRUSADER, ALAMEIN))


class CampaignCommonwealthPolicy(ScriptedPolicy):
    """A scripted Commonwealth DEFENDER (attacker=AXIS, so every inherited reflex -- defender
    moves and sorties, counter-assault, elastic retreat, initiative -- is unchanged) that switches
    to the ATTACKER branch on the scheduled offensive Game-Turns, driving west toward
    objective_for(ALLIED)."""

    def __init__(self, schedule: OffensiveSchedule = CAMPAIGN_CW_OFFENSIVES):
        super().__init__(attacker=Side.AXIS)                     # defender wiring, exactly like the base
        self._schedule = schedule
        self._offensive = ScriptedPolicy(attacker=Side.ALLIED)   # the attacker branch for offensive turns

    def _on_offensive(self, state: GameState) -> bool:
        return self._schedule.is_offensive(state.turn)

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        if self._on_offensive(state):
            return self._offensive.movement(state, side)
        return super().movement(self._rear_view(state), side)

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        if self._on_offensive(state):
            return self._offensive.combat(state, side)
        return super().combat(self._rear_view(state), side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        if self._on_offensive(state):
            return self._offensive.supply_orders(state, side)
        return super().supply_orders(self._rear_view(state), side)

    def _rear_view(self, state: GameState) -> GameState:
        """Between offensives the Commonwealth has NO westward objective -- it is a vanilla
        rear-oriented defender, identical to the proven rommels_arrival CW. Hiding allied_objective
        flips every objective_for(ALLIED) read (dump leapfrog, movement, combat) back toward the
        Egyptian rear, so the front and its dumps fall back EAST with the pressure instead of
        chasing Benghazi into the advancing Axis (rule 32.33). On the offensive the real state
        (allied_objective = Benghazi) drives the attack west."""
        return replace(state, allied_objective=None)


def _step_toward(reach: dict, here: Coord, dest: Coord) -> "Coord | None":
    """The reachable hex nearest `dest` -- one Truck Convoy Phase move toward it (rule 53.22),
    or None if the truck is already as near as its convoy CPA can carry it. The module-level
    twin of ScriptedPolicy._truck_step, so the campaign relay steps a long open-desert leg
    exactly as the base relay steps its return."""
    step = min(reach, key=lambda c: (distance(c, dest), reach[c], c))
    return step if step != here else None


def campaign_truck_orders(state: GameState, side: Side) -> list[TruckOrder]:
    """The campaign's multi-hop coastal supply relay (rules 53.14 / 60.33-60.34): a stateless,
    one-order-per-truck bucket brigade that walks Benghazi's landed tonnage forward along the
    seeded staging dumps (game.scenario._campaign_staging_dumps) LEG BY LEG, where the shared
    single-hop ScriptedPolicy.truck_orders can only shuttle the rear port and stalls at the
    first dump. Campaign-only, so it lives here and NOT in the byte-locked base relay (which
    rommels_arrival seeds its trucks through).

    Per truck (side's trucks only), routing on the base arithmetic -- capacity 54.2, cargo-fuel
    burn 49.18, convoy reach 53.22, all from game.supply -- so it never bends a magnitude:
      - `objective` is the side's own front (objective_for, so an offensive Commonwealth's
        trucks would haul WEST) -- NOT the bare target_hex the base relay uses.
      - forward dumps are the friendly, non-dummy dumps strictly closer to the objective,
        scanned off state.supplies directly so EMPTY waypoints count (unlike active_supplies) --
        the chain fills into them.
      - CARRYING (deliverable cargo aboard): UNLOAD everything bar a 3x-one-way FUEL reserve
        (49.18) into the nearest forward dump in reach; if none is in reach, STEP toward the
        nearest forward dump (a carried open-desert leg is legal, burning cargo fuel per hop).
      - EMPTY (only its return reserve left): if its co-located dump has stock AND a forward
        dump is in reach, LOAD (splitting the load FUEL/AMMO/STORES by the 56.22 fractions,
        sized against residual cargo) + MOVE + UNLOAD in one order; else roll back toward the
        nearest STOCKED dump farther from the objective to reload (the nearest REAR dump, not
        always Benghazi)."""
    orders: list[TruckOrder] = []
    objective = state.objective_for(side)
    for t in state.trucks:
        if t.side != side:
            continue
        reach = supply.reachable_truck_moves(state, t)
        here = distance(t.hex, objective)
        forward = [s for s in state.supplies
                   if s.side == side and not s.is_dummy and s.hex != t.hex
                   and distance(s.hex, objective) < here]
        in_reach = [s for s in forward if s.hex in reach]
        reserve = 3 * supply.truck_move_fuel(t, supply.truck_convoy_cpa(t.truck_class))
        carrying = t.ammo > 0 or t.stores > 0 or t.fuel > reserve

        if carrying:
            delivered = False
            if in_reach:
                dest = min(in_reach, key=lambda s: (distance(s.hex, objective), reach[s.hex], s.id))
                out = supply.truck_move_fuel(t, reach[dest.hex])
                if t.fuel >= out:                          # can afford the hop's cargo-fuel burn
                    unload: dict = {}
                    if t.fuel - 3 * out > 0:               # keep 2x the one-way burn to get home
                        unload["FUEL"] = t.fuel - 3 * out
                    if t.ammo > 0:
                        unload["AMMO"] = t.ammo
                    if t.stores > 0:
                        unload["STORES"] = t.stores
                    if unload:
                        orders.append(TruckOrder(t.id, to=dest.hex, unload_to=dest.id, unload=unload))
                        delivered = True
            if not delivered and forward:                  # nothing deliverable in reach -> close the gap
                dest = min(forward, key=lambda s: (distance(s.hex, objective), s.id))
                step = _step_toward(reach, t.hex, dest.hex)
                if step is not None and t.fuel >= supply.truck_move_fuel(t, reach[step]):
                    orders.append(TruckOrder(t.id, to=step))
            continue

        colocated = next((s for s in state.supplies if s.side == side and not s.is_dummy
                          and s.hex == t.hex), None)
        if colocated is not None and not colocated.empty and in_reach:
            dest = min(in_reach, key=lambda s: (distance(s.hex, objective), reach[s.hex], s.id))
            out = supply.truck_move_fuel(t, reach[dest.hex])
            cap = supply.truck_capacity(t.truck_class)
            load: dict = {}
            for c, frac in _CONVOY_SPLIT_56_22.items():    # 56.22 fuel/ammo/stores tonnage split
                room = int(frac * t.points * cap[c]) - getattr(t, c.lower())
                take = min(getattr(colocated, c.lower()), max(0, room))
                if take > 0:
                    load[c] = take
            if load:
                unload = {}
                fuel_deliver = t.fuel + load.get("FUEL", 0) - 3 * out
                if fuel_deliver > 0:
                    unload["FUEL"] = fuel_deliver
                for c in ("AMMO", "STORES"):
                    amt = getattr(t, c.lower()) + load.get(c, 0)
                    if amt > 0:
                        unload[c] = amt
                orders.append(TruckOrder(t.id, load_from=colocated.id, load=load,
                                         to=dest.hex, unload_to=dest.id, unload=unload))
                continue

        rear = [s for s in state.supplies
                if s.side == side and not s.is_dummy and not s.empty
                and distance(s.hex, objective) > here]
        if rear:
            dest = min(rear, key=lambda s: (distance(s.hex, t.hex), s.id))
            step = _step_toward(reach, t.hex, dest.hex)
            if step is not None and t.fuel >= supply.truck_move_fuel(t, reach[step]):
                orders.append(TruckOrder(t.id, to=step))
    return orders


class CampaignAxisPolicy(ScriptedPolicy):
    """The scripted Axis for the FULL campaign: the base attacker (attacker=AXIS, so movement,
    combat and elastic retreat are inherited and byte-identical to ScriptedPolicy(Side.AXIS))
    PLUS the multi-hop coastal haul that lets the Panzerarmee fight east of Benghazi at all.
    Campaign-only, so rommels_arrival / siege_of_tobruk (which seed trucks through the byte-
    locked base relay) are untouched. Two overrides:
      - truck_orders runs the leg-by-leg relay (campaign_truck_orders) instead of the base
        single-hop port shuttle.
      - supply_orders HIDES the staging dumps (id 'AX-Stage*') from the base leapfrog bridge,
        which would otherwise walk the waypoint chain toward Alexandria and UNSTAGE the very
        relay the trucks feed."""

    def __init__(self):
        super().__init__(attacker=Side.AXIS)

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        return campaign_truck_orders(state, side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        staged_out = replace(state, supplies=tuple(
            s for s in state.supplies if not s.id.startswith("AX-Stage")))
        return super().supply_orders(staged_out, side)
