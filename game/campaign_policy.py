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

from . import supply, wells
from .events import Control, Side
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


def garrison_units(state: GameState, side: Side) -> set:
    """THE STANDING GARRISON ORDER (rule 64.73). The campaign is scored on the victory cities a side
    HOLDS SUPPLIED at the end, and a city with a stocked friendly dump standing on it supplies its
    garrison at range zero -- so a combat unit already sitting on such a city is banking its points
    for free, and marching it away throws them in the desert.

    Measured, this is the single largest source of value destruction in the campaign: the Axis opens
    holding Tobruk (200 VP) and Bardia (100 VP) with the Libyan Tank Command, and EVERY policy tried
    -- scripted and LLM alike -- marched those garrisons east and finished with every victory city
    empty (a 0-0 draw), while a side that did NOTHING AT ALL simply held them and won 300-10.

    So one unit per supplied victory city stays put: a standing order no competent staff would
    countermand. It prefers a non-tank holder, freeing the armour for manoeuvre (the real reason the
    garrisons kept leaving: they ARE the armour, and the mobile lane wants them). Campaign-only --
    it needs the 64.73 city table, which rommels_arrival / siege_of_tobruk do not carry."""
    vic = state.victory
    cities = getattr(vic, "cities", None)
    if not cities:
        return set()
    held = set()
    for ax, _avp, _cvp, _name in cities:
        # Whoever is BANKING this city right now keeps banking it: a combat unit standing on it that
        # can trace fuel AND ammo is exactly the 64.73 occupier test the campaign scores on.
        here = [u for u in state.units_at(ax)
                if u.side == side and u.alive and u.is_combat and u.strength >= 1
                and vic._supplied(state, u)]
        if here:
            held.add(min(here, key=lambda u: (u.is_tank, u.id)).id)   # infantry first; armour is for manoeuvre
    return held


def hold_garrisons(orders: list, state: GameState, side: Side) -> list:
    """Drop any move order for a unit under the standing garrison order (garrison_units): it holds
    its supplied victory city and banks the points. Combat orders are untouched -- a garrison still
    fights from its city. Applied by every campaign policy, scripted and staff alike."""
    keep = garrison_units(state, side)
    return [o for o in orders if o.unit_id not in keep] if keep else orders


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
        orders = (self._offensive.movement(state, side) if self._on_offensive(state)
                  else super().movement(self._rear_view(state), side))
        return hold_garrisons(orders, state, side)     # even an offensive keeps its supplied cities

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        if self._on_offensive(state):
            return self._offensive.combat(state, side)
        return super().combat(self._rear_view(state), side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        # The seeded spine stays put: a railhead, a railway station and a Field Supply Depot are
        # places on the supply LINE, not field dumps that follow the army (see _without_staging).
        state = _without_staging(state)
        if self._on_offensive(state):
            return self._offensive.supply_orders(state, side)
        return super().supply_orders(self._rear_view(state), side)

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        # The Commonwealth hauls with the same multi-hop relay as the Axis (it is side-generic):
        # from the rail-fed Mersa Matruh railhead forward to the Field Supply Depots its offensives
        # are launched out of (game.scenario._campaign_cw_depots).
        return campaign_truck_orders(state, side)

    def _rear_view(self, state: GameState) -> GameState:
        """Between offensives the Commonwealth has NO westward objective -- it is a vanilla
        rear-oriented defender, identical to the proven rommels_arrival CW. Hiding allied_objective
        flips every objective_for(ALLIED) read (dump leapfrog, movement, combat) back toward the
        Egyptian rear, so the front and its dumps fall back EAST with the pressure instead of
        chasing Benghazi into the advancing Axis (rule 32.33). On the offensive the real state
        (allied_objective = Benghazi) drives the attack west."""
        return replace(state, allied_objective=None)


_STAGING = ("AX-Stage", "AL-Stage")     # the seeded supply SPINES of both sides (60.34 / 54.3)


def _without_staging(state: GameState) -> GameState:
    """Hide both seeded spines from the base leapfrog bridge (rule 32.3). A staging dump is a fixed
    depot ON the supply line -- a railhead, a railway station, a Field Supply Depot -- not a field
    dump that follows the army: let the 32.3 bridge walk them toward the objective and the chain
    the trucks feed UNSTAGES itself one hop at a time.

    Their PORTS go with them. The bridge skips any dump standing on a harbour hex ("the port is
    where convoys land; trucks haul it forward") -- a guard meant for the harbour dump ITSELF, which
    here is a staging depot already hidden and already immobile. Left visible, PORT-Matruh would pin
    every Commonwealth FIELD dump that ever falls back onto the Mersa Matruh railhead -- and falling
    back onto the railhead is precisely what they do -- freezing the army's mobile supply on the one
    hex it retreats to."""
    staged = {s.hex for s in state.supplies if s.id.startswith(_STAGING)}
    return replace(state,
                   supplies=tuple(s for s in state.supplies if not s.id.startswith(_STAGING)),
                   ports=tuple(p for p in state.ports if p.hex not in staged))


def _step_toward(reach: dict, here: Coord, dest: Coord) -> "Coord | None":
    """The reachable hex nearest `dest` -- one Truck Convoy Phase move toward it (rule 53.22),
    or None if the truck is already as near as its convoy CPA can carry it. The module-level
    twin of ScriptedPolicy._truck_step, so the campaign relay steps a long open-desert leg
    exactly as the base relay steps its return."""
    step = min(reach, key=lambda c: (distance(c, dest), reach[c], c))
    return step if step != here else None


def _relay_source(state: GameState, side: Side, hx: Coord, anchor):
    """The dump a relay truck standing on `hx` may LIFT from: the seeded supply SPINE, or the port
    of arrival itself (the faucet). Never an army FIELD dump -- that stock belongs to the division
    parked on it, and a lorry that carries it back off the division has done negative work.
    Measured: the relay siphoned 1,365 of the 1,530 Fuel Points the Commonwealth's field dumps
    owned, and a dump with no fuel cannot relocate (32.24) -- so every one of them froze on the
    Mersa Matruh railhead, the army advanced with no mobile supply behind it, and it could hold
    nothing it took.

    The RICHEST such dump on the hex, not the first: dumps share hexes once the 32.3 bridge starts
    walking field dumps around, and an empty one that had wandered onto the railhead MASKED the
    rail-fed depot beneath it and froze the whole pool -- 4,700 Fuel Points under the truck's
    wheels, read as DRY."""
    here = [s for s in state.supplies
            if s.side == side and not s.is_dummy and s.hex == hx
            and (s.id.startswith(_STAGING) or (anchor is not None and s.id == anchor.id))]
    return max(here, key=lambda s: (s.fuel, s.ammo + s.stores, s.id), default=None)


def _load_56_22(t, dump) -> dict:
    """A fresh load off `dump`, apportioned by the 56.22 fuel/ammo/stores tonnage split and sized
    against the truck's REMAINING 54.2 capacity -- a truck home from a run still holds its return
    reserve, so loading a full share on top of it would overrun the 53.12 Point ceiling and the
    engine would reject the order."""
    cap = supply.truck_capacity(t.truck_class)
    load: dict = {}
    for c, frac in _CONVOY_SPLIT_56_22.items():
        room = int(frac * t.points * cap[c]) - getattr(t, c.lower())
        take = min(getattr(dump, c.lower()), max(0, room))
        if take > 0:
            load[c] = take
    return load


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
      - a hop burns cargo fuel (49.18); the carrying/empty split is purely by CARGO -- a truck's
        fuel is always its own movement/return reserve, never re-counted as deliverable cargo, so
        a truck ferrying its own return fuel is not mistaken for a delivery.
      - every delivery RETAINS enough fuel to bail all the way back to the bottomless port (the
        `anchor`, rearmost convoy-fed dump), sized to the drop hex's distance from it (`keep`) --
        so a truck that chains deep still holds its way home even when a later forward reload loses
        the race for a co-located dump's fuel to the other truck (the strand a flat 2x-hop reserve
        could not survive).
      - CARRYING (ammo/stores aboard): UNLOAD everything bar that return reserve into the DEEPEST
        forward dump in reach the truck can AFFORD the hop to (a nearer, cheaper dump is the
        fallback); if it can afford none, STEP toward the deepest forward dump, or -- stuck with
        sub-hop fuel on a dump -- shed its ammo/stores into that co-located dump so it never
        freezes holding an unmovable load.
      - EMPTY (no cargo) on a dump that still has FUEL: LOAD the 56.22 split off it and MOVE +
        UNLOAD into a forward dump within one hop -- only when the truck can afford the move AND
        keep its return reserve (never a leg it cannot move, never a delivery past the point of no
        return). With nothing forward in reach it drives at the nearest forward dump anyway, but
        ONLY off the bottomless faucet (the anchor): a truck that loads out of an INTERMEDIATE depot
        and drives deeper is not hauling supply forward, it is strip-mining its own chain.
      - Otherwise RETURN toward the anchor to reload, topping up from a co-located fuel dump so it
        is never stranded on fumes -- the cycle that keeps the lean pool running instead of walking
        itself dry against the deepest staging dump."""
    orders: list[TruckOrder] = []
    objective = state.objective_for(side)
    # The 52.1-52.3 WELLS are geography, not depots: hide them from every dump scan below (the
    # idiom _CampaignAxisSupplyMixin.supply_orders already uses to hide the AX-Stage waypoints
    # from the base leapfrog). A well holds water and nothing else, so the relay can neither
    # reload from one nor usefully fill one -- and left visible, the "deepest forward dump" for
    # an Axis truck becomes the well standing on ALEXANDRIA and the whole pool marches at it.
    # (Hauling water FROM a well is rule 52.45 and the 54.2 Water column -- deferred, see
    # game.wells.)
    state = replace(state, supplies=tuple(s for s in state.supplies
                                          if not wells.is_water_source(s)))
    # THE RELOAD ANCHOR: the side's rearmost PORT OF ARRIVAL (55.3) -- the dump its convoys
    # actually land in. Every return leg heads for it, and every delivery retains enough fuel to
    # get back to it from where it drops, so a truck that chains deep still carries its own way
    # home. It is the FAUCET, not merely "the rearmost dump that happens to hold fuel": for the
    # Axis the two readings agree (Benghazi is both), but for the Commonwealth they differ
    # fatally -- the rail lands at the Mersa Matruh railhead (60.7) while the rearmost fuelled
    # dump is the bottomless Cairo base, 78 truck-hexes further east. Reading the puddle instead
    # of the faucet marched the whole Commonwealth pool off to Cairo on its first return leg and
    # idled it there for the rest of the war (measured: 10 truck moves in 111 game-turns, against
    # the Axis's 394). The old reading survives as the fallback, for a state with no port at all.
    faucets = {p.hex for p in state.ports if p.side == side}
    anchor = max([s for s in state.supplies
                  if s.side == side and not s.is_dummy and s.hex in faucets]
                 or [s for s in state.supplies
                     if s.side == side and not s.is_dummy and s.fuel > 0],
                 key=lambda s: (distance(s.hex, objective), s.id), default=None)

    def keep(t, dest_hex):
        """Fuel to RETAIN at dest_hex to trek back to the anchor: 2x the hex-distance's fuel
        (terrain CP + ZOC detours overshoot the straight line) plus a hop of margin. This is what
        lets a truck survive losing the race for a co-located dump's fuel to the other truck -- it
        still holds its way home instead of stranding on a flat 2x-hop reserve."""
        home = supply.truck_move_fuel(t, supply.truck_convoy_cpa(t.truck_class))
        if anchor is None:
            return 2 * home
        return 2 * supply.truck_move_fuel(t, distance(dest_hex, anchor.hex)) + home

    enemy_held = Control.AXIS if side == Side.ALLIED else Control.ALLIED
    for t in state.trucks:
        if t.side != side:
            continue
        reach = supply.reachable_truck_moves(state, t)
        here = distance(t.hex, objective)
        # The dumps to haul INTO: friendly, real, strictly closer to the objective -- and NOT on a
        # hex the enemy holds. That last clause is 56.15's own logic (a convoy does not sail to a
        # captured port) applied to the lorry: a depot the enemy is standing in is not a delivery
        # address, it is a trap. Without it the DEEPEST forward "dump" for a Commonwealth truck is
        # the empty garrison dump inside AXIS-HELD TOBRUK, 45 hexes behind the enemy front -- and
        # the pool drives at it and is ZOC-boxed in the desert for the rest of the war. As the
        # front moves, the chain extends itself: Sollum becomes a legal destination the game-turn
        # Operation Compass takes it, which is exactly when the Field Supply Depot there is worth
        # filling.
        forward = [s for s in state.supplies
                   if s.side == side and not s.is_dummy and s.hex != t.hex
                   and distance(s.hex, objective) < here
                   and state.control_of(s.hex) != enemy_held]
        in_reach = [s for s in forward if s.hex in reach]
        # The dump under the wheels, in its two distinct roles: what the truck may LIFT from (the
        # supply line only -- see _relay_source) and what it may SHED an unmovable load into (any
        # friendly dump: shedding is a delivery, and delivering into a field dump is the whole job).
        colocated = _relay_source(state, side, t.hex, anchor)
        sink = next((s for s in state.supplies if s.side == side and not s.is_dummy
                     and s.hex == t.hex), None)

        # CARRYING a delivery -- ammo/stores aboard. A truck's FUEL is always its own movement /
        # return reserve, NEVER re-counted as cargo (a hop burns cargo fuel 49.18), so fuel alone
        # never means "carrying". That is the split the old 3x-full-CPA reserve got wrong: it
        # flipped a just-delivered truck to EMPTY to re-load in place, and it mistook a truck
        # ferrying its own return fuel for a delivery.
        if t.ammo > 0 or t.stores > 0:
            # Deliver into the DEEPEST reachable dump the truck can AFFORD the hop to -- not
            # blindly the farthest (which may cost more cargo fuel than it holds), so a nearer,
            # cheaper dump is the fallback.
            affordable = [s for s in in_reach
                          if t.fuel >= supply.truck_move_fuel(t, reach[s.hex])]
            if affordable:
                dest = min(affordable, key=lambda s: (distance(s.hex, objective), reach[s.hex], s.id))
                out = supply.truck_move_fuel(t, reach[dest.hex])
                unload: dict = {}
                surplus = t.fuel - out - keep(t, dest.hex)  # unload fuel bar the return reserve
                if surplus > 0:
                    unload["FUEL"] = surplus
                if t.ammo > 0:
                    unload["AMMO"] = t.ammo
                if t.stores > 0:
                    unload["STORES"] = t.stores
                orders.append(TruckOrder(t.id, to=dest.hex, unload_to=dest.id, unload=unload))
                continue
            if forward:                                    # nothing affordable in reach -> close the gap
                dest = min(forward, key=lambda s: (distance(s.hex, objective), s.id))
                step = _step_toward(reach, t.hex, dest.hex)
                if step is not None and t.fuel >= supply.truck_move_fuel(t, reach[step]):
                    orders.append(TruckOrder(t.id, to=step))
                    continue
            if sink is not None:                           # sub-hop fuel, stuck on a dump: shed the
                unload = {}                                # unmovable ammo/stores into it (a pure
                if t.ammo > 0:                             # co-located transfer) so the truck is never
                    unload["AMMO"] = t.ammo                # frozen holding a load it cannot move, and
                if t.stores > 0:                           # is free to return for fuel next phase.
                    unload["STORES"] = t.stores
                orders.append(TruckOrder(t.id, unload_to=sink.id, unload=unload))
            continue

        # EMPTY of cargo, standing on a dump that still has FUEL: load a fresh forward leg (the
        # 56.22 split) off it and run it.
        if colocated is not None and colocated.fuel > 0 and (in_reach or forward):
            load = _load_56_22(t, colocated)
            if in_reach:
                # A forward dump within one convoy hop -- LOAD + MOVE + UNLOAD in one order, but
                # ONLY when the truck can afford the move and still keep its return reserve (the
                # base relay's 49.18 guard, generalised to `keep`), so it never loads a leg it
                # cannot move (the freeze) NOR delivers itself past the point of no return.
                dest = min(in_reach, key=lambda s: (distance(s.hex, objective), reach[s.hex], s.id))
                out = supply.truck_move_fuel(t, reach[dest.hex])
                fuel_deliver = t.fuel + load.get("FUEL", 0) - out - keep(t, dest.hex)
                if fuel_deliver > 0:
                    unload = {"FUEL": fuel_deliver}
                    for c in ("AMMO", "STORES"):
                        amt = getattr(t, c.lower()) + load.get(c, 0)
                        if amt > 0:
                            unload[c] = amt
                    orders.append(TruckOrder(t.id, load_from=colocated.id, load=load,
                                             to=dest.hex, unload_to=dest.id, unload=unload))
                    continue
            elif anchor is not None and colocated.id == anchor.id:
                # THE OPEN-DESERT LEG, and ONLY off the FAUCET. Nothing forward is within one hop,
                # so load at the port of arrival and DRIVE AT the nearest forward dump anyway,
                # exactly as the CARRYING branch already crosses a long leg. A truck standing on the
                # railhead that answers "no dump in reach" by going home is standing where home IS:
                # it simply idles there for the rest of the war, which is what froze the whole
                # Commonwealth pool whenever an enemy screen pushed the Field Supply Depot past a
                # single 30-CP hop.
                #
                # Off the faucet ONLY, because the faucet is bottomless and a forward depot is not.
                # Let a truck load out of an INTERMEDIATE depot and drive deeper and the relay stops
                # hauling supply forward and starts strip-mining its own chain: measured, the Axis
                # pool emptied the Tobruk and Bardia staging dumps -- the very dumps that supply the
                # garrisons banking those two cities under rule 64.73 -- and carried them off into
                # the desert after a front that had long outrun it, costing the Axis every victory
                # point it held. A truck with nothing reachable ahead of it goes BACK for more; it
                # does not cannibalise the depot under its wheels.
                dest = min(forward, key=lambda s: (distance(t.hex, s.hex),
                                                   distance(s.hex, objective), s.id))
                step = _step_toward(reach, t.hex, dest.hex)
                if step is not None and t.fuel + load.get("FUEL", 0) >= supply.truck_move_fuel(
                        t, reach[step]):
                    orders.append(TruckOrder(t.id, load_from=colocated.id, load=load, to=step))
                    continue

        # No forward leg to make from here: RETURN toward the anchor to reload -- topping up from a
        # co-located fuel dump to its return reserve so a truck at a drained chain-tip is never
        # stranded on fumes. This is what keeps the lean pool cycling instead of walking itself dry.
        if anchor is not None and distance(anchor.hex, objective) > here:
            step = _step_toward(reach, t.hex, anchor.hex)
            if step is not None:
                load = None
                need = keep(t, t.hex)
                if colocated is not None and colocated.fuel > 0 and t.fuel < need:
                    cap = supply.truck_capacity(t.truck_class)
                    room = int(t.points * cap["FUEL"]) - t.fuel
                    take = min(colocated.fuel, max(0, room), need - t.fuel)
                    if take > 0:
                        load = {"FUEL": take}
                onboard = t.fuel + (load["FUEL"] if load else 0)
                if onboard >= supply.truck_move_fuel(t, reach[step]):
                    if load is not None:
                        orders.append(TruckOrder(t.id, load_from=colocated.id, load=load, to=step))
                    else:
                        orders.append(TruckOrder(t.id, to=step))
    return orders


class _CampaignAxisSupplyMixin:
    """The campaign Axis forward-supply behaviour, shared by the scripted CampaignAxisPolicy and the
    live CampaignStaffPolicy (game.campaign_staff): the multi-hop coastal truck haul
    (campaign_truck_orders) instead of the base single-hop port shuttle, and hiding the staging
    dumps from the base leapfrog bridge (which would otherwise walk the waypoint chain toward
    Alexandria and UNSTAGE the relay the trucks feed -- see _without_staging). Campaign-only --
    rommels_arrival / siege_of_tobruk seed trucks through the byte-locked base relay and never
    construct these."""

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        # The standing garrison order applies to the live staff too: whatever the seats propose, the
        # units holding a supplied victory city stay on it. A staff may manoeuvre with everything
        # else; it may not march the Tobruk and Bardia garrisons into the desert.
        return hold_garrisons(super().movement(state, side), state, side)

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        return campaign_truck_orders(state, side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        return super().supply_orders(_without_staging(state), side)


class CampaignAxisPolicy(_CampaignAxisSupplyMixin, ScriptedPolicy):
    """The scripted Axis for the FULL campaign: the base attacker (attacker=AXIS, so movement, combat
    and elastic retreat are inherited and byte-identical to ScriptedPolicy(Side.AXIS)) PLUS the
    multi-hop coastal haul (see _CampaignAxisSupplyMixin) that lets the Panzerarmee fight east of
    Benghazi at all."""

    def __init__(self):
        super().__init__(attacker=Side.AXIS)
