"""The scripted policies for the FULL campaign -- both sides' campaign-only overrides that make
the desert war SEE-SAW instead of one player sandbagging for 111 turns:

  * CampaignCommonwealthPolicy -- an army that CONCENTRATES FORWARD onto the rail-fed railhead
    between offensives (the Matruh line: the springboard every one of its offensives was
    launched from), and goes over to the offensive on the historical Game-Turn windows (Operation
    Compass, Crusader, Second Alamein) advancing toward objective_for(ALLIED) (Benghazi, the Axis
    rear, far WEST).
  * CampaignAxisPolicy -- the base attacker PLUS the multi-hop coastal supply haul
    (campaign_truck_orders) that lets the Panzerarmee fight east of Benghazi at all: the lean
    truck pool relays Benghazi's landed tonnage forward LEG BY LEG along the seeded staging
    dumps (rule 60.34), where the shared single-hop base relay can only shuttle the port.

BOTH OF THEM PLAY THE 64.73 POINTS (take_and_hold_moves / take_and_hold_supply below). The campaign
is scored on the victory CITIES a side holds SUPPLIED at the final Game-Turn, and for a long time
only the Commonwealth was taught to play them: the Axis never garrisoned a city it took and threw
away Bardia -- a hundred points it OPENS HOLDING -- every single game. A campaign whose grade turns
on which side we made competent is not balanced, it is broken. So the standing orders of rule 64.73
are side-generic (game.campaign_claim was already written that way) and both staffs keep them; what
decides the war is then the war.

Campaign-ONLY: rommels_arrival / siege_of_tobruk keep the base ScriptedPolicy (whose byte-locked
truck relay they seed trucks through), so their event streams stay byte-identical. Neither the
base ScriptedPolicy.truck_orders/supply_orders nor game.staff_policy is touched; all new haul
logic lives in the module-level campaign_truck_orders below.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from . import campaign_claim, construction, supply, tactics, wells
from .campaign_claim import (STAGING, garrison_units,   # the rule-64.73 standing orders, re-exported
                             hold_depots, hold_garrisons)   # (game.campaign_staff and the tests import them from here)
from .events import Control, Side
from .hexmap import Coord, distance
from .policy import (AttackOrder, BuildOrder, DemolitionOrder, MoveOrder, ScriptedPolicy,
                     SupplyMoveOrder, TruckOrder)
from .scenario import _CONVOY_SPLIT_56_22
from .state import GameState, SupplyUnit

__all__ = ["CAMPAIGN_CW_OFFENSIVES", "CampaignAxisPolicy", "CampaignCommonwealthPolicy",
           "OffensiveSchedule", "build_the_chain", "campaign_truck_orders", "deny_dumps",
           "garrison_units", "hold_depots", "hold_garrisons", "keep_in_trace", "railhead",
           "take_and_hold_moves", "take_and_hold_supply"]


# --- the rule-64.73 standing orders, SIDE-GENERIC (see game.campaign_claim) -----------------------

def _standing_plan(state: GameState, side: Side, *, escort: bool) -> tuple:
    """THE STANDING ORDERS, in priority order: the 64.71 DELTA first, then the 64.73 cities, then the
    32.33 DESERT COLUMNS that open the ground the next city will be taken from.

    A pure function of the state (like claims() itself), so the movement half and the supply half
    of the take-and-hold cannot disagree about who is going where -- neither needs to remember the
    other. A unit sent to hold Alexandria is not also available to go and take Sollum: the Delta
    claims are computed first and their units struck from the city plan, never the reverse. A city
    is worth Victory Points; the Delta is worth the war (64.71); and a column is worth the NEXT city,
    which is why it is computed last, out of whatever the scored objectives did not want.

    The columns ride only with an army that is ON THE OFFENSIVE (`escort`, the same gate the flying
    columns already keep). A defender that walks its mobile supply west into the oncoming
    Panzerarmee has not pushed a depot forward, it has posted one to the enemy (32.33's trap: a dump
    is only recoverable from a hex a friendly combat unit still holds)."""
    delta = campaign_claim.delta_claims(state, side)
    busy = {c.unit_id for c in delta}
    cities = tuple(c for c in campaign_claim.claims(state, side, escort=escort)
                   if c.unit_id not in busy)
    if not escort:
        return delta + cities
    busy |= {c.unit_id for c in cities}
    busy |= {c.depot_id for c in cities if c.depot_id}
    columns = tuple(c for c in campaign_claim.column_claims(state, side, busy)
                    if c.depot_id not in busy)
    return delta + cities + columns


def take_and_hold_moves(state: GameState, side: Side, army: list[MoveOrder], *,
                        escort: bool) -> list[MoveOrder]:
    """THE TAKE-AND-HOLD, written as a TRANSFORM on an army's move orders -- the same idiom as
    hold_garrisons itself, and the shape that lets BOTH campaign policies keep the rule-64.73
    standing orders over whatever march each of them would otherwise make (the Commonwealth's
    concentrate-or-attack, the Axis's drive on Alexandria).

      * TAKE -- campaign_claim.claims detaches the nearest unit that could actually be FED there to
        each victory city this side does not already bank, and claim_moves marches it at ITS city
        instead of at the far objective.
      * A DETACHED UNIT IS OUT OF THE GENERAL ADVANCE -- every unit in the plan, not merely the ones
        with a move order in it. The one that has ALREADY REACHED its city emits no move (there is
        nowhere to go), and if that left it in the advance the attacker branch would march it
        straight back off toward the objective the same stage -- the city taken and abandoned in one
        breath. It stands on the hex it took, banked or not: an occupied city is what flips its
        control, and control is what lets the lorries fill the depot that will bank it.
      * HOLD -- and whatever the army proposed, the unit BANKING a supplied victory city stays on it
        (hold_garrisons). A standing order no competent staff would countermand, on either side.

      * AND THE ARMY DOES NOT OUTRUN ITS SUPPLY (keep_in_trace, rules 54.16/32.16). The general
        advance -- everything the standing orders did not detach -- may only march where it can still
        eat. The DETACHMENTS are not filtered by it and must not be: each has already answered the
        same question better (a city claim only goes where the unit could be FED; a 32.33 column
        carries its larder). See keep_in_trace, which is where the whole argument is.

    `escort` rides through to claims(): may a flying column's DEPOT march with it (32.33)? True for
    an army on the offensive; False for one that would only be walking its mobile supply into the
    enemy's advance (see CampaignCommonwealthPolicy._on_offensive)."""
    plan = _standing_plan(state, side, escort=escort)
    take = campaign_claim.claim_moves(state, side, plan)
    busy = {c.unit_id for c in plan}
    march = keep_in_trace([o for o in army if o.unit_id not in busy], state, side)
    return hold_garrisons(take + march, state, side)


def take_and_hold_supply(state: GameState, side: Side, army: list[SupplyMoveOrder], *,
                         escort: bool) -> list[SupplyMoveOrder]:
    """The dual of take_and_hold_moves, on the DEPOTS (rule 32.33, game.campaign_claim). The plan is
    recomputed rather than passed in: claims() is a pure function of the state, so the depot's orders
    cannot disagree with its garrison's, and neither half needs to remember the other.

      * THE DEPOTS OF THE TAKE-AND-HOLD COME FIRST (claim_supply): a depot marching with a garrison
        to a city that has none is the only thing that will make that city BANKABLE (64.73), so it
        outranks the ordinary forward leapfrog.
      * The depot already feeding a banked city never leapfrogs away from it (hold_depots) -- a depot
        walked off a city un-banks it just as surely as marching the garrison off does.
      * And no field dump ever parks on a seeded Field Supply Depot and MASKS it from the lorries
        (keep_off_the_spine -- the hex belongs to the chain)."""
    follow = campaign_claim.claim_supply(state, side,
                                         _standing_plan(state, side, escort=escort))
    busy = {o.supply_id for o in follow}
    rest = [o for o in hold_depots(army, state, side) if o.supply_id not in busy]
    return campaign_claim.keep_off_the_spine(follow + rest, state, side)


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


_CW_RAIL_LANE = "CW-RAILHEAD"        # the Commonwealth rail lane (game.scenario._campaign_convoys)


def railhead(state: GameState):
    """THE LINE THE COMMONWEALTH FIGHTS FROM (rules 54.3 / 60.7): the RAIL-FED RAILHEAD -- the
    forwardmost station of the Western Desert Railway the enemy does not hold. The trains run to it
    EVERY Game-Turn, so it is the one place forward of the Delta where an army can stand and be fed;
    and when the enemy drives across Mersa Matruh it RETRACTS east down the line (Matruh -> El Daba
    -> El Hamman -> the Delta base) -- and the line the army holds retracts with it.

    Read straight off the rail convoy's own retarget line and resolved with the engine's own 56.15
    test (game.engine._convoy_dest), so the army concentrates on exactly the station the trains are
    actually reaching -- one definition of 'the railhead', not two that can drift apart. The line is
    bound once, at construction (game.scenario._campaign_cw_rail_line), which is also why it is read
    from the convoy and not re-derived from state.supplies: a field dump that leapfrogs onto Mersa
    Matruh would otherwise tie for 'the dump nearest the terminus' and hijack the railway.

    If the enemy has driven over EVERY station the answer is the terminus itself -- the railway is
    switched off and the hex that switches it back on is the line to fight for, not a reason to have
    no line at all. None only for a state with no railway -- every scenario but the campaign --
    which is what makes this policy safe to construct anywhere."""
    line = next((c.retarget for c in state.convoys
                 if c.side == Side.ALLIED and c.lane == _CW_RAIL_LANE and c.retarget), ())
    by_id = {s.id: s for s in state.supplies}
    for sid in line:
        dump = by_id.get(sid)
        if dump is not None and state.control_of(dump.hex) != Control.AXIS:
            return dump
    return by_id.get(line[0]) if line else None      # every station overrun: retake the terminus


def _fed_by(state: GameState, unit, dump) -> bool:
    """True when `unit` can draw its AMMUNITION from `dump` -- the rule-32.16 trace (cpa/2 CP,
    blocked by enemy ZOC), which is the same test rule 64.73 scores a city's occupier on. It is
    also, deliberately, the stop-line of the march below: a unit is ON the line when the line can
    FEED it, so an army concentrating forward halts inside its own supply instead of walking past
    it into the desert. Infantry (cpa 10) must close to ~5 hexes of the depot for that; the lorried
    and armoured units trace ~12-13 and screen wider -- the deployment sorts itself by what each
    formation can actually be fed at."""
    return any(s.id == dump.id for s in supply.reachable_supplies(state, unit, supply.AMMO))


class CampaignCommonwealthPolicy(ScriptedPolicy):
    """A scripted Commonwealth DEFENDER (attacker=AXIS, so every inherited reflex -- defender
    moves and sorties, counter-assault, elastic retreat, initiative -- is unchanged) that
    CONCENTRATES ITS REAR ARMY FORWARD onto the rail-fed railhead between offensives (see
    _concentrate) and switches to the ATTACKER branch on the scheduled offensive Game-Turns, driving
    west toward objective_for(ALLIED). Over that march lie the rule-64.73 standing orders
    (take_and_hold_moves / take_and_hold_supply): it TAKES THE VICTORY CITIES AS IT GOES instead of
    running the whole army past them at the objective hex -- the same orders the Axis now keeps."""

    def __init__(self, schedule: OffensiveSchedule = CAMPAIGN_CW_OFFENSIVES):
        super().__init__(attacker=Side.AXIS)                   # defender wiring, exactly like the base
        self._schedule = schedule
        # The ADVANCE branch. It drives on whatever objective the view it is handed carries:
        # Benghazi on an offensive Game-Turn, the assembly line between them.
        self._advance = ScriptedPolicy(attacker=Side.ALLIED)

    def _on_offensive(self, state: GameState) -> bool:
        return self._schedule.is_offensive(state.turn)

    def _escort(self, state: GameState) -> bool:
        """A DEPOT ONLY MARCHES WITH A GARRISON ON AN OFFENSIVE (claims(escort=)). Off-window the
        Commonwealth is a defender concentrating on the railhead, and the only cities it can bank are
        the ones its seeded spine already feeds -- Mersa Matruh and Sidi Barrani, which it stands on
        anyway. To detach a field dump then would be to walk the army's mobile supply WEST into the
        oncoming Panzerarmee (32.33's trap: a dump can only be recovered from a hex a friendly combat
        unit still holds) for a city the offensive has not yet reached. So off-window the
        take-and-hold garrisons only what the line ALREADY feeds; the expeditions ride with the
        offensives."""
        return self._on_offensive(state)

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        army = (self._advance.movement(state, side) if self._on_offensive(state)
                else self._concentrate(state, side))
        # The railway gang is never in `army`: an engineer is not a combat unit "in any way, shape,
        # or form" (23.11), and every proposer in this repo skips a non-combat unit. So its orders
        # simply ride alongside, and no unit can be ordered twice.
        return self._railway(state, side) + take_and_hold_moves(state, side, army,
                                                                escort=self._escort(state))

    def _railway(self, state: GameState, side: Side) -> list[MoveOrder]:
        """[24.6] THE TWO NEW ZEALAND RAILROAD CONSTRUCTION COMPANIES GO WHERE THE TRACK ENDS.

        They are the only units in the game that may build railroad (24.61) and the railway is the
        only thing that moves the Commonwealth's whole supply trace west instead of one column's, so
        their standing order is the simplest in this file: march to the next hex of the surveyed line
        and stand on it. The Construction Segment then books them (engine._construction), rule 24.12
        pins them for the Operations Stage, and two of them stacked lay a hex of track per stage
        (24.62).

        THE MARCH IS TO THE RAILHEAD, not to the hex being laid: the Construction Chart restricts
        building to "head or track", so the gang stands on the last completed hex and pushes the line
        out in front of it (engine._build_rail). That is also where the Store Points are -- 24.64
        wants one present WITH the engineer, and the next hex of the line is empty desert.

        THEY MARCH SPRING TO SPRING like everyone else (_march) -- they are MOTORIZED and burn fuel
        (49.13), and the road from Cairo to Mersa Matruh is forty hexes of desert with a ten-hex hole
        in the middle of it. What feeds them once they are past Mersa Matruh is the railway itself:
        engine._rail_stops serves the RAILHEAD (24.67's marker: the end of the track is where a train
        can go and no further) whether or not a combat unit is standing on it, precisely because these
        two are not combat units and a railway whose builders starve does not get built.

        Rule 24.65 will refuse to lay track on a hex the enemy controls or occupies, and rule 23.11
        forbids an engineer to enter one at all, so the line simply stops until the Eighth Army takes
        the ground back. The railway FOLLOWS the army; the army then eats off the railway. Neither
        half moves without the other, which is the desert war."""
        head = construction.rail_head(state)
        if head is None or construction.rail_next(state) is None:
            return []                                    # no line, or the line is finished
        gang = [u for u in state.living(side)
                if construction.builds_rail(u) and u.hex != head
                and state.control_of(head) != Control.AXIS]      # 23.11: never into enemy ground
        if not gang:
            return []
        # AND THE GANG DOES NOT OUTRUN ITS SUPPLY EITHER (keep_in_trace). It is not exempt from the
        # desert because it carries shovels: it is MOTORIZED, it burns fuel to move (49.13), and
        # between Alexandria and Mersa Matruh lie thirty-four hexes with no depot in them. Measured
        # without this line: both companies dashed sixty Capability Points out of Alexandria in one
        # stage, ran dry at (33,118) in the middle of the hole, and sat there for the rest of the war
        # -- so not one hex of railway was ever laid. They creep up the line behind the army instead,
        # station by station, as the trains found them (54.35). The railway follows the army; it does
        # not race it.
        return keep_in_trace(self._march(state, side, gang, head, held=True), state, side)

    def construction(self, state: GameState, side: Side) -> list[BuildOrder]:
        """[24.6]/[24.9] The Construction Segment's standing orders: lay the next hex of the Western
        Desert Railway with whichever NZRRC companies are standing on the railhead, and construct the
        forward dump the chain needs next (build_the_chain). The engine re-validates every clause.

        THE RAILWAY IS ONLY LAID ON GROUND THE ARMY HOLDS, and that is DOCTRINE, not rule -- 24.65
        forbids building only on an "Enemy-controlled or Enemy-occupied" hex, so NEUTRAL desert nobody
        has ever walked over is legal track by the letter of it. It is also a catastrophe, and this is
        the measurement that says so.

        MEASURED, five seeds, the full GT1-111, with the letter of 24.65 and nothing more: the two New
        Zealand companies laid fourteen hexes of track STRAIGHT INTO NO-MAN'S-LAND -- the surveyed line
        runs Mersa Matruh to Tobruk and nobody had contested most of it -- and the trains then
        obediently ran the 54.32 haul out to the stations they founded there, forward-first
        (engine._rail_deliver). The freight went to empty desert. Mersa Matruh, where the Eighth Army
        and 115 of its 195 Truck Points actually stand, was thinned; the forward stations were
        captured under 32.13 or evaporated under 49.3. Seed 1941 went from a COMMONWEALTH MARGINAL
        VICTORY (120-180) to an AXIS SMASHING VICTORY (275-80) -- the railway lost the Commonwealth
        the war it had just won without it.

        The historical Western Desert Railway was built BEHIND the front, through ground the Eighth
        Army held, and it reached Capuzzo only after Crusader had taken Capuzzo. So the gang lays track
        on a hex the Commonwealth CONTROLS -- one a combat unit of ours has stood on (54.41) -- and
        nowhere else. The railway FOLLOWS the army. It does not lead it into the desert."""
        orders = build_the_chain(state, side)
        head, site = construction.rail_head(state), construction.rail_next(state)
        gang = tuple(u.id for u in sorted(state.living(side), key=lambda u: u.id)
                     if construction.builds_rail(u) and u.hex == head)
        if (site is not None and gang and construction.rail_buildable(state, side, site)
                and state.control_of(site) == Control.ALLIED):     # doctrine: only ground we hold
            orders.append(BuildOrder(construction.RAIL, site, gang))
        return orders

    def _concentrate(self, state: GameState, side: Side) -> list[MoveOrder]:
        """THE FORWARD CONCENTRATION -- the Eighth Army marches to the line it fights from.

        Between offensives the Commonwealth was a rear-oriented defender with no objective at all,
        and the base defender reflex only sorties at an EXPOSED enemy stack within reach. So an army
        that begins the war 60 hexes behind the front never sees one and NEVER MOVES: measured, the
        76 combat reinforcements that arrive in the Nile Delta sat there for the entire war, ten CW
        units stood near the railhead at Game-Turn 1 and ZERO stood there at Game-Turn 12, 40 or 80,
        the rail-fed depot at Mersa Matruh filled to its cap with nobody to drink it, and the three
        offensive windows then ordered an attack on Benghazi from 60 hexes behind the start line --
        which cannot arrive, and could not be supplied if it did. The Commonwealth never fought.

        The historical answer is the obvious one: the Eighth Army moved UP and stood on a forward
        line -- Matruh, later Alamein -- and every one of its offensives was launched out of it. So
        between offensives the rear army marches to the RAILHEAD (the line the trains reach, above)
        and holds:

          - THE REAR is everything further from the front (objective_for -- the Axis rear at
            Benghazi, the direction of the whole war) than the railhead itself is. One-directional
            BY CONSTRUCTION: a unit at or forward of the line is never in the rear, so the
            concentration can never march the army BACKWARDS out of ground it has taken -- what it
            holds forward of the line it keeps holding, and only the rear echelon comes up.
          - IT MARCHES SPRING TO SPRING (_march), not as the crow flies -- and the dumps BRIDGE the
            column behind it (_bridge) instead of racing to its head.
          - IT GARRISONS THE RAILHEAD ITSELF. The first unit that can reach Mersa Matruh STANDS ON
            IT (_march), and the standing garrison order then keeps it there for good -- the
            railhead is a 64.73 victory city, and a supplied unit on it is banking points. This is
            not a flourish, it is the load-bearing hex of the whole Commonwealth position: the rail
            lane lands its cargo in the forwardmost station the enemy does not CONTROL (56.15/54.3),
            and control flips to whoever last stood there. Measured: leave Mersa Matruh empty and a
            single Axis armoured car, driving through on its way to Alexandria, takes the railhead,
            the retraction walks El Daba -> El Hamman -> the Delta (all of them already driven over
            by the same rush), and the Commonwealth's ENTIRE FAUCET switches off -- army, offensives
            and all. An occupied hex cannot be driven through (the enemy must assault it), so one
            battalion standing on the terminus keeps the trains running.
          - IT STOPS ON SUPPLY, not on arrival: once the railhead is held, a unit halts as soon as
            the line can FEED it (_fed_by), which is what keeps a concentration from becoming yet
            another sprint into the desert -- the standing failure mode of every policy here. The
            army ends up inside the trace of a depot the railway refills every turn, which is the
            whole point: a supplied army on the start line.
          - EVERYTHING ELSE HOLDS. Units already on the line, and the units the standing garrison
            order keeps on their victory cities, are left to the base defender reflex (hold, and
            sortie at an exposed enemy) exactly as before."""
        line = railhead(state)
        view = self._forward_view(state)
        if line is None:                          # no railway: the vanilla rear-oriented defender
            return super().movement(view, side)
        front = state.objective_for(side)         # the direction of the war: the Axis rear
        depth = distance(line.hex, front)
        held = any(u.is_combat and u.hex == line.hex for u in state.living(side))
        rear = [u for u in state.living(side)
                if u.is_combat and distance(u.hex, front) > depth
                and not (held and _fed_by(state, u, line))]
        march = self._march(state, side, rear, line.hex, held)
        moving = {o.unit_id for o in march}
        hold = [o for o in super().movement(view, side) if o.unit_id not in moving]
        return march + hold

    def _march(self, state: GameState, side: Side, rear: list, assembly: Coord,
               held: bool) -> list[MoveOrder]:
        """THE ROUTE MARCH: SPRING TO SPRING, the one law of the Western Desert. A column that
        marches on its objective AS THE CROW FLIES dies in the desert, and the two ways it dies are
        the two things the desert has none of:

          - WATER. It is found in wells and only wells (52.11), drawn on the same cpa/2 trace as
            everything else (52.4), and every consecutive Operations Stage without it costs a
            marching battalion a TOE Strength Point (52.53) -- three a Game-Turn. Measured on the
            straight-line march: 149 water shortfalls and 81 attrition losses in SIX Game-Turns, and
            the Nile Delta army was destroyed by the desert before it ever saw an Italian. An
            infantryman's trace is barely five hexes, so his road is the wells -- which is simply
            the coast road, and is why every army in this war used it.
          - FUEL. A lorried or armoured unit pays fuel for every move (49.13) and may only draw it
            from a dump it can trace. Between the Delta base and the railhead lie THIRTY-FOUR hexes
            with no dump in them at all -- a ten-hex hole in the middle that a twelve-hex trace
            cannot span. Measured: half the army (25 of 54 units) froze in it, out of fuel, having
            walked itself into the one place it could not be refuelled from. Its bound (up to 22
            hexes) can CLEAR the hole in one move -- but only if it is aimed at the far side.

        So each unit marches at the next SPRING of the thing it will die without: a fuel-burner at
        the nearest forward dump that holds FUEL, a marching man at the nearest forward source of
        WATER (well, the Alexandria-Matruh pipeline, or any dump holding some). 'Forward' is the
        truck relay's own test (campaign_truck_orders) -- strictly closer to the assembly than the
        unit itself -- so reaching a spring drops it from the list and the next one down the line
        becomes the target: a bucket brigade in reverse, the column hauling ITSELF along its own
        supply chain. Every step must still close on the assembly (never a step backwards, so the
        march always terminates), and the inherited gates all hold: fuel (a move it cannot pay for
        is never proposed), stacking (9.14), and the tactical reachability the engine validates."""
        if not rear:
            return []
        enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
        wet = [s for s in state.supplies if s.side == side and s.water > 0]
        fuelled = [s for s in state.supplies if s.side == side and not s.is_dummy and s.fuel > 0]
        orders: list[MoveOrder] = []
        for u in rear:
            if supply.plan_draw(state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
                continue          # out of fuel -- every move pays (49.13); don't propose a reject
            reach = tactics.reachable_for(state, u, enemy_zoc, enemy_occupied)
            if not held and assembly in reach and self._stacking_ok(state, u, assembly):
                orders.append(MoveOrder(u.id, assembly))   # CLAIM the railhead: the trains run to it
                held = True                                # only while it stands does the faucet run
                continue
            here = distance(u.hex, assembly)
            springs = fuelled if supply.fuel_rate(u) else wet     # what THIS unit dies without
            spring = min((s for s in springs if distance(s.hex, assembly) < here),
                         key=lambda s: (distance(s.hex, u.hex), distance(s.hex, assembly), s.id),
                         default=None)
            target = spring.hex if spring is not None else assembly   # nothing ahead: straight at it
            cands = [c for c in reach
                     if c != u.hex and distance(c, assembly) < here   # only ever toward the line
                     and self._stacking_ok(state, u, c)]
            if cands:
                dest = min(cands, key=lambda c: (distance(c, target), reach[c], c))
                orders.append(MoveOrder(u.id, dest))
        return orders

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        if self._on_offensive(state):
            return self._advance.combat(state, side)
        return super().combat(self._forward_view(state), side)

    def retreat_before_assault(self, state: GameState, side: Side,
                               pinned: frozenset[str]) -> list[MoveOrder]:
        # The elastic desert defense (13.0) with the LINE as its anchor: every unit still slips out
        # of an assault it can, but a GARRISON UNDER A STANDING ORDER STANDS. A garrison that slips
        # off Mersa Matruh hands the enemy the hex, and with it the whole Commonwealth faucet
        # (_concentrate) -- an elastic defense is a way to hold a line, not a way to lose one.
        #
        # AND RBA IS THE OTHER DOOR OUT OF A CITY. Retreat Before Assault is VOLUNTARY movement
        # (13.21), so it is a second order channel entirely, and hold_garrisons never watched it:
        # rule 15.82 forbids EVICTING a garrison from a major city, but nothing forbids the garrison
        # from politely leaving. Measured, and this is how the Delta fell in three weeks with seven
        # battalions standing in it: the Commonwealth garrisoned all seven hexes of Alexandria and
        # Cairo by Game-Turn 3 exactly as ordered, the Italians closed up and announced an assault on
        # Game-Turn 4, the elastic defense slipped BR-1-Ches and BR-2-KOR out of Alexandria to make
        # room -- and six Italian battalions walked into the empty city on Game-Turn 5. The standing
        # order has to hold BOTH doors or it holds neither.
        view = state if self._on_offensive(state) else self._forward_view(state)
        return hold_garrisons(super().retreat_before_assault(view, side, pinned), state, side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        # The army's ORDINARY 32.3 leapfrog, over which take_and_hold_supply lays the standing orders
        # of rule 64.73. The seeded spine stays put: a railhead, a railway station and a Field Supply
        # Depot are places on the supply LINE, not field dumps that follow the army (see
        # _without_staging). The remaining FIELD dumps bridge the units that have outrun their fuel
        # (_bridge), else leapfrog toward the view's objective (32.3) -- so between offensives they
        # come forward onto the assembly WITH the army they feed, instead of trailing back to a rear
        # base that is already bottomless, and on an offensive they follow the attack west.
        view = _without_staging(state if self._on_offensive(state)
                                else self._forward_view(state))
        army = self._bridge(view, side) or super().supply_orders(view, side)
        return take_and_hold_supply(state, side, army, escort=self._escort(state))

    def _bridge(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        """THE SUPPLY BRIDGE (rule 32.3) -- a dump goes to the unit that has OUTRUN ITS FUEL, not to
        the unit nearest the objective. StormPolicy's own answer to this exact failure, applied to a
        column on the march instead of a column in the assault.

        The base 32.3 bridge leapfrogs every dump to the MOST FORWARD unit it can reach, and that is
        a trap for an army moving up: the dumps all race to the head of the column and stack on the
        railhead (measured: four of the Commonwealth's five field dumps ended on the one hex), while
        the lorried and armoured units strung out behind them sit in the thirty-four-hex hole
        between the Delta base and the railhead with no dump in trace and no fuel to move -- half
        the army, frozen, being marched at by nothing. A dump that is not under the units that
        cannot move is not doing logistics.

        So while ANY combat unit cannot pay for a move (49.13 -- the exact gate the march itself
        checks), the dumps go to those units, nearest-the-front first, one dump per unit. With the
        column moving again the bridge stands down and the ordinary forward leapfrog resumes."""
        target = state.objective_for(side)
        stranded = sorted((u for u in state.living(side) if u.is_combat
                           and supply.plan_draw(state, u, supply.FUEL,
                                                supply.fuel_cost(u, 1)) is None),
                          key=lambda u: (distance(u.hex, target), u.id))
        if not stranded:
            return []
        orders: list[SupplyMoveOrder] = []
        claimed: set = set()
        for su in state.active_supplies(side):
            if su.base or su.fuel < supply.SUPPLY_MOVE_FUEL or state.port_at(su.hex) is not None:
                continue          # a rule-57 base is immobile; a dry dump cannot move (32.24); a
                                  # harbour dump stays where the convoys land (55)
            reach = supply.reachable_moves(state, su)
            pick = next((u for u in stranded if u.hex in reach and u.hex != su.hex
                         and u.hex not in claimed), None)
            if pick is not None:
                claimed.add(pick.hex)
                orders.append(SupplyMoveOrder(su.id, pick.hex))
        return orders

    def demolition(self, state: GameState, side: Side) -> list[DemolitionOrder]:
        # [54.14] Deny the enemy your stocks -- symmetric, both sides, one standing order (deny_dumps).
        return deny_dumps(state, side)

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        # The Commonwealth hauls with the same multi-hop relay as the Axis (it is side-generic):
        # from the rail-fed Mersa Matruh railhead forward to the Field Supply Depots its offensives
        # are launched out of (game.scenario._campaign_cw_depots). The REAL state, deliberately: the
        # lorries always haul toward the front (Benghazi), never toward the assembly they start on
        # -- a relay pointed at its own railhead would find nothing forward of itself and stop.
        return campaign_truck_orders(state, side)

    def _forward_view(self, state: GameState) -> GameState:
        """THE DEFENSIVE POSTURE'S VIEW OF THE WAR: BOTH objectives are THE LINE (the rail-fed
        railhead). One substitution, and every inherited reflex starts defending the right hex:

          - objective_for(ALLIED) -> the line: the march above and the 32.3 dump leapfrog both aim
            at the assembly, so the army and its dumps come forward TOGETHER and stop there.
          - target_hex -> the line: and THIS is what a ScriptedPolicy defender actually does with an
            objective. It ANCHORS on it (_anchor_ids: whoever holds it never moves, never sorties,
            never counter-assaults out of it) and it never UNCOVERS it (_uncovers gates every
            sortie on leaving the objective covered). Pointed at Alexandria -- 60 hexes behind the
            front, where the Commonwealth has not one unit -- both tests are vacuous: there are no
            anchors, nothing is uncovered, and the reflex is free to throw the RAILHEAD'S OWN
            GARRISON at the first exposed Italian it sees. Measured, that is exactly what it did:
            Selby Force marched off Mersa Matruh on Game-Turn 1 and surrendered on Game-Turn 2,
            leaving the terminus empty for an Axis armoured car to drive over on its way to
            Alexandria. Anchor the defender on the line and the garrison stays.

        This is what the old _rear_view got backwards. It blanked allied_objective, and
        objective_for then fell back to state.target_hex -- ALEXANDRIA, the Commonwealth's OWN BASE.
        The army's 'forward' was its own rear: the dumps fell back east and the army never came up
        at all. Hiding the objective was the right instinct (an off-window defender must not chase
        Benghazi into the advancing Axis, rule 32.33) but the wrong hex: the answer is not NO
        objective, it is the RIGHT one -- the line you intend to hold. With no railway there is no
        line, and the old rear-oriented defender is exactly what is wanted."""
        line = railhead(state)
        if line is None:
            return replace(state, allied_objective=None)
        return replace(state, target_hex=line.hex, allied_objective=line.hex)


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
    staged = {s.hex for s in state.supplies if s.id.startswith(STAGING)}
    return replace(state,
                   supplies=tuple(s for s in state.supplies if not s.id.startswith(STAGING)),
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
    wheels, read as DRY.

    [24.9] AND A DUMP THE ARMY HAS BUILT. "The only restriction on the use of such supplies is that
    trucks 'in convoy' may not load such supplies" -- of an UNconstructed pile. A dump somebody has
    stopped and paid three Capability Points and twenty Store Points to construct is a proper supply
    dump, and the lorries may load from it. This is what lets the chain grow past the last depot that
    was seeded in September 1940 (build_the_chain); until it existed the relay's own guard, written to
    stop it strip-mining the divisions, also silently forbade it to ever lengthen its own line."""
    here = [s for s in state.supplies
            if s.side == side and not s.is_dummy and s.hex == hx
            and (s.constructed or s.id.startswith(STAGING) or _is_faucet(s, anchor))]
    return max(here, key=lambda s: (s.fuel, s.ammo + s.stores, s.id), default=None)


def _is_faucet(s, anchor) -> bool:
    """A BOTTOMLESS source: the side's port of arrival (the reload `anchor`) or a rule-57 strategic
    base -- Cairo and Alexandria, where "if he wants something, it is in Cairo" (57.0). Everything
    else on the map is a finite depot whose stock belongs to somebody.

    The relay guards jealously against lifting supply back OUT of a depot (see _relay_source and
    _a_link_in_the_chain: it has already cost the Axis a hundred Victory Points once). A faucet is
    the exception, and the reason is simply that giving supply away is what a faucet is FOR: it
    cannot be strip-mined, because it cannot be emptied.

    This is what lets the [60.43] DELTA PARK exist at all. The chart stations 40 Medium + 10 Heavy
    Truck Points in CAIRO and 10 Light + 20 Medium in ALEXANDRIA -- both on the rule-57 base, both
    far behind the railhead. A lorry standing on that base could neither load from it nor refuel
    from it, because the relay admitted only the staging chain and the anchor; seeded dry, with no
    liftable dump underneath, all fifty of those Truck Points would have sat in the Delta for the
    entire war and the chart's largest Commonwealth allotment would have been a decoration.
    (The wells are stripped from `state` before any of this runs, so `base` here means the Delta
    base and nothing else -- a water source is geography, not a faucet.)"""
    return s.base or (anchor is not None and s.id == anchor.id)


def _a_link_in_the_chain(s, anchor) -> bool:
    """Could the relay LIFT this load out again? The exact dual of _relay_source, asked on the
    DESTINATION side: a seeded staging depot or the port of arrival is a LINK -- supply goes in one
    end and comes out the other -- while a FIELD dump is a one-way sink (a lorry may never carry a
    division's stock back off it).

    THE RELAY FILLS THE CHAIN BEFORE IT FILLS A SINK, and this is what says so. Both are legal
    delivery addresses -- pouring supply into the army's field dumps IS the job -- but a sink that
    happens to lie DEEPER than the chain's own tail must never be allowed to divert the brigade past
    it, because everything poured in there stops moving for good.

    MEASURED, and it cost the Axis a hundred Victory Points the moment it got the take-and-hold: a
    flying column planted its escort field dump on SOLLUM -- which sits forward of Bardia -- and the
    lorries, chasing 'the deepest forward dump', drove the entire Mediterranean tonnage past
    AX-Stage-Bardia and into it. Sixteen deliveries went in over twenty-four Game-Turns and not one
    Point ever came out. AX-Stage-Bardia -- the larder of the garrison banking BARDIA, worth a
    hundred -- went from 1,598 Fuel to ZERO, its garrison could no longer trace, and the
    Commonwealth walked the city off it."""
    return s.constructed or s.id.startswith(STAGING) or (anchor is not None and s.id == anchor.id)


def _field_dump_id(side: Side, hx: Coord) -> str:
    """A deterministic id for a dump founded at `hx` (54.11). Derived from the hex, so the stateless
    relay names the same depot every time it recomputes and never mints a duplicate."""
    return f"{'AX' if side == Side.AXIS else 'AL'}-Field-{hx[0]}-{hx[1]}"


def _forward_depot_sites(state: GameState, side: Side, objective: Coord, here: int,
                         enemy_held, reach: dict) -> list:
    """[54.11]/[54.16] THE CHAIN EXTENDS ITSELF -- the hexes the relay may FOUND a new depot on,
    handed to the leapfrog below as ordinary delivery addresses so no special case is needed.

    Rule 54.11: "ANY HEX CAN BE USED AS A SUPPLY DUMP." Rule 54.16: "Establishing a viable dump
    network should be TOP PRIORITY for logistics commanders." The engine could not do it -- no
    EventKind created a dump and game.apply never appended to state.supplies, so the depot list was
    FROZEN AT CONSTRUCTION for all 111 Game-Turns. The relay could therefore only ever deliver into
    depots placed in September 1940; the army marched away from them and starved. Measured: both
    armies ended ~9 hexes beyond the nearest stocked dump -- JUST outside the 32.16 cpa/2 trace --
    and stayed there, with 5-8% of the Axis and 29% of the Commonwealth able to draw a single Point
    of supply, from Game-Turn 10 to Game-Turn 111. Ninety per cent of both armies were logistically
    dead for the entire war.

    WHERE. On a hex a friendly COMBAT UNIT is standing on: forward of the lorry, inside its 53.22
    convoy reach, holding no dump already, with no enemy on it and not on ground the enemy controls.
    Not in empty desert -- a depot the army is not standing on is a depot the enemy walks onto
    (32.13) -- and not behind the front, where the seeded chain already reaches. That single clause
    makes the network follow the army instead of the army starving away from the network, and the
    sort in the caller does the rest: it fills the CHAIN first (_a_link_in_the_chain) and only then
    the deepest of these, which is the leading brigade's own hex.

    Founded EMPTY by the engine the instant a lorry unloads into it (engine._establish_dump), so
    nothing is minted and conservation is untouched."""
    taken = {s.hex for s in state.supplies if not s.is_dummy}       # never two dumps on one hex
    sites: list = []
    for u in sorted(state.living(side), key=lambda u: u.id):
        if not u.is_combat or u.strength < 1 or u.hex in taken:
            continue
        if distance(u.hex, objective) >= here or u.hex not in reach:
            continue
        if state.enemies_at(u.hex, side) or state.control_of(u.hex) == enemy_held:
            continue
        taken.add(u.hex)
        sites.append(SupplyUnit(_field_dump_id(side, u.hex), side, u.hex, ammo=0, fuel=0))
    return sites


def _can_trace(state: GameState, u) -> bool:
    """The rule-64.73 occupation quality-test, asked of a unit anywhere: can it draw both Fuel (its
    per-model rate -- FOOT infantry burns none at all, 49.12) and Ammunition off a dump inside the
    32.16 cpa/2 trace? This is the same question game.campaign_victory._supplied asks, written
    without the victory object so the movement layer can ask it too."""
    return (supply.plan_draw(state, u, supply.FUEL, supply.fuel_rate(u)) is not None
            and supply.plan_draw(state, u, supply.AMMO, supply.ammo_cost(u, phasing=True)) is not None)


def deny_dumps(state: GameState, side: Side) -> list:
    """[54.14] BLOW THE DUMP -- the standing order that makes an overrun depot a DECISION.

    Rule 32.13 hands a dump, and everything in it, to any enemy combat unit that walks onto its hex.
    Until 54.14 existed on our side of the engine that was a pure one-way gift to whoever was
    advancing -- and in September 1940 that is the Italian 10th Army, all the way to the wire. The
    rulebook never left a retreating army its stocks to hand over: it let it burn them, at a price
    (a third of the unit's CPA) and with a die (the 54.17 Demolition Table).

    THE DOCTRINE, and it is FLAGGED AS DOCTRINE, NOT RULE -- 54.14 says a player MAY blow a dump,
    and says nothing whatever about when he should. Ours burns a depot only when it is ABOUT TO
    FALL, which we read as: an enemy combat unit is ADJACENT, and the enemy strength next to the hex
    OUTWEIGHS the friendly strength standing on it. Both halves matter.

      * Without the adjacency test an army torches its own supply at the first sign of trouble.
      * Without the OUTWEIGHED test, the Tobruk and Bardia garrisons -- which sit with enemies
        adjacent for sixty turns and do not fall, because rule 15.82's fortification forbids
        eviction -- would burn their own fuel every Operations Stage of the siege. A garrison that
        can hold does not blow its dump; that is not denial, it is arson.

    We do not blow a base (rule 57) or a well (52.1): neither is a Supply Dump counter, which is the
    same exemption engine._capture_dumps makes and for the same reason. The engine re-validates all
    of it (non-gun, co-located, CP available, one attempt per hex per dump)."""
    orders: list = []
    mine: dict = {}                           # hex -> my combat units standing there
    for u in state.living(side):
        if u.is_combat:
            mine.setdefault(u.hex, []).append(u)
    if not mine:
        return orders
    enemy = [u for u in state.living(tactics.other(side)) if u.is_combat and u.strength >= 1]
    for su in sorted(state.supplies, key=lambda s: s.id):
        if su.side != side or su.base or su.is_dummy or su.empty or wells.is_water_source(su):
            continue                          # 57 / 52.1: a base and a well are not Supply Dumps
        held = mine.get(su.hex)
        if not held:
            continue                          # 54.14: only a unit ON the dump can blow it
        threat = sum(u.effective_strength for u in enemy if distance(u.hex, su.hex) == 1)
        if not threat or threat <= sum(u.effective_strength for u in held):
            continue                          # nobody adjacent, or we can hold it: no arson
        demolisher = next((u for u in sorted(held, key=lambda u: u.id)
                           if supply.can_blow(u, su)), None)
        if demolisher is not None:
            # Buy the +1s: 54.14 lets the attempt spend an additional two-thirds of the unit's basic
            # CPA before rolling, and a unit about to lose the hex has no better use for the CP. The
            # engine clamps what it cannot afford (supply.affordable_thirds).
            orders.append(DemolitionOrder(demolisher.id, su.id,
                                          extra_thirds=supply.DEMOLITION_MAX_THIRDS))
    return orders


def build_the_chain(state: GameState, side: Side) -> list[BuildOrder]:
    """[24.9] CONSTRUCT THE FORWARD DUMP -- turn the heap of supplies at the head of the advance into
    a LINK the lorries can lift out of again, and the bucket brigade grows one hop longer.

    Rule 24.9's Note is the whole of this: "supplies may be placed in a hex not containing a
    constructed supply dump. The only restriction on the use of such supplies is that TRUCKS 'IN
    CONVOY' MAY NOT LOAD SUCH SUPPLIES." So a lorry may always set a load down in the desert (54.11 --
    that is what engine._establish_dump does, and it is free because the rulebook makes it free) and
    the army may eat off it at once. What three Capability Points and twenty Store Points BUY is the
    right to give supply back to a truck: a pile is a one-way sink, a constructed dump is a link.

    THIS IS THE SECOND CHOKE-POINT, and it is a quiet one. The relay may only reload from the supply
    LINE (campaign_policy._relay_source: a lorry that carries a division's stock back off it has done
    negative work -- measured, it once siphoned 1,365 of the Commonwealth's 1,530 forward Fuel Points
    and froze every field dump it owned). But the LINE was whatever September 1940 seeded and nothing
    else: the Commonwealth's ends at Sollum, the Axis's at Bardia. So the chain could never grow, and
    an army that advanced past the last seeded depot was hauling from a hundred hexes back for the
    rest of the war. 24.9 is the rulebook handing both sides the tool to extend it -- and making them
    pay for it, and stop to do it.

    THE DOCTRINE, and it is FLAGGED AS DOCTRINE: 24.9 says a Player MAY construct a dump and says
    nothing about when. Ours builds one when it would actually LENGTHEN THE CHAIN -- a dump forward of
    the chain's current head, with a combat unit standing on it and the twenty Stores on hand. Not
    every dump the army sits on (that would spend 20 Stores a time to license the lorries to
    strip-mine the front-line divisions), and never behind the head (the chain already reaches there).
    Side-generic, like every other standing order here: the Panzerarmee may extend its chain east on
    exactly the same terms, which is the point -- what 24 gives the Commonwealth alone is the RAILWAY."""
    objective = state.objective_for(side)
    head = campaign_claim.chain_head(state, side, objective)
    if head is None:
        return []
    reach = distance(head.hex, objective)
    orders: list[BuildOrder] = []
    for su in sorted(state.supplies, key=lambda s: s.id):
        if su.side != side or su.constructed or su.base or su.is_dummy:
            continue
        if wells.is_water_source(su) or distance(su.hex, objective) >= reach:
            continue                       # behind the head: the chain already reaches this hex
        if construction.stores_at(state, side, su.hex) < construction.DUMP_STORES:
            continue                       # 24.9/24.13: the twenty Stores must be ON HAND in the hex
        crew = [u for u in sorted(state.units_at(su.hex), key=lambda u: u.id)
                if u.side == side and construction.can_construct_dump(state, side, u, su)]
        if crew:
            orders.append(BuildOrder(construction.DUMP, su.hex, (crew[0].id,)))
    return orders


def keep_in_trace(orders: list, state: GameState, side: Side) -> list:
    """[54.16]/[32.16] DO NOT OUTRUN YOUR SUPPLY -- the consolidation constraint, as a transform on an
    army's move orders, in the same idiom as hold_garrisons.

    WIRED AT LAST, and only because rule 32.33 and rule 24 arrived to pay for it. FOUR earlier
    measurements rejected it and the log of them is kept below, because the thing that finally made it
    shippable is exactly the thing every one of those measurements said was missing.

    IT IS LAID OVER THE GENERAL ADVANCE ALONE (take_and_hold_moves), and that is the whole design.
    The standing orders' DETACHMENTS are not filtered by it, because each of them has already
    answered the same question in a better-informed way: a city claim is only made where the unit
    could be FED (campaign_claim.can_be_fed -- rule 64.73's own trace test, asked of the destination),
    and a 32.33 DESERT COLUMN is in supply BY CONSTRUCTION -- its depot ends the Movement Phase in its
    own hex (engine._supply_movement runs after engine._movement), which satisfies not merely the
    32.16 trace at distance zero but the stricter thing the full logistics game asks: 49.15, "for fuel
    to be consumed, it must be present in the SAME HEX with the consuming unit". Reading a column's
    destination against the depot's CURRENT hex would say it is marching into the desert. It is
    marching with its larder.

    TWO CLAUSES, then, for everyone else:

      * A unit that CAN trace supply may not march to a hex where it CANNOT. It advances at the pace
        its logistics can follow, and no faster.
      * A unit that is ALREADY DRY may move ONLY into the trace, or strictly NEARER a stocked depot.
        It walks back to its supply, or to where its supply has caught up. It does not march on.

    The second clause is not decoration, and getting it wrong is instructive. Written first as "a unit
    out of trace may move freely -- it needs to seek supply", the constraint did NOTHING: the base
    attacker's proposer only ever offers hexes strictly CLOSER TO THE OBJECTIVE, so "freely" meant
    "onward to Alexandria". The starving unit was the one unit on the map with a licence to keep
    marching, and the 10th Army -- every man of which is out of trace by Game-Turn 3 -- beelined
    through the gap exactly as before. An escape hatch that only opens forward is not an escape hatch.

    WHY THE POLICY AND NOT THE ENGINE: the engine already halts a unit that cannot pay a move's Fuel
    (49.13/49.16, engine._draw_move_fuel), and that is the rulebook's own gate. But FOOT infantry
    burns NO FUEL AT ALL (49.12), so that gate never touched the Italian 10th Army for one hex of the
    war -- which is why it walked sixty hexes into Egypt and stood on Alexandria on Game-Turn 4. The
    rulebook does not forbid an infantryman from walking into the desert; it merely kills him there
    (51.22 stores attrition, 52.53 thirst, 15.15 dry-ammunition surrender), and it kills him far too
    slowly to stop a scripted policy that cannot see it coming. So the restraint belongs where the
    judgement belongs: in the staff that gives the order. FLAGGED as doctrine, not as rule.

    ############################################################################################
    # THE FOUR REJECTIONS, kept so nobody re-runs them. Every one of these was measured over five
    # seeds and none of them shipped.
    #
    #   BOTH SIDES, STRICT (before the railway) -- killed the Axis beeline (GT4 furthest-east fell
    #     from r=133, Alexandria, to r=81-100: SIDI BARRANI, where Graziani actually stopped) and
    #     PARALYSED the Eighth Army: 31 of 42 Commonwealth combat units sitting in the Nile Delta at
    #     Game-Turn 60, with a 91% "supplied" score to flatter it -- because a division parked on the
    #     bottomless Cairo base is by definition in supply. That trap is why scripts.measure_campaign
    #     reports supplied-AND-FORWARD.
    #   BOTH SIDES, PERMISSIVE (a supplied unit may cross dry ground; only a starving one is pinned)
    #     -- did NOTHING. The Axis dump CARPET (32.3: a depot relocates 15 CP per OpStage, faster
    #     than the infantry it feeds) keeps the spearhead in trace as it runs. GT4: r=122-131.
    #   AXIS ONLY -- dampened the beeline (GT4: r=88-109) and was worse overall: the Commonwealth
    #     marched west into a now better-supplied Axis and was destroyed. 445-20, 445-20, 445-20,
    #     420-20, 400-30.
    #   BOTH SIDES, STRICT, WITH THE RAILWAY FEEDING ITS LINE (54.3/54.35) -- fixed what it was for
    #     (10th Army culminates at r=95-99; Axis supplied-and-forward 4-16% -> 25-67%; both armies
    #     survive, combat units alive roughly double) AND FROZE THE WAR: Axis 425-20 in ALL FIVE
    #     SEEDS, where the unwired campaign returns three distinct scores. Operation Compass did not
    #     run. Two tests went red and both named the defect.
    #
    # THE BLOCKER, in one sentence: _forward_depot_sites founds a depot ONLY where a friendly combat
    # unit stands, and this constraint forbids a unit from standing where it cannot eat -- so the army
    # could not reach a hex until a depot fed it, and a depot could not be founded until the army
    # reached it. It bit the moment the rails ended (60.7: the RR runs to Mersa Matruh and no
    # further). Sollum is ten hexes from Sidi Barrani; the widest Commonwealth trace on this map is
    # nine; measured, ZERO Commonwealth combat units could trace supply standing on Sollum.
    #
    # THE TWO KEYS, and the rulebook cut them both. [32.33] the escorted desert column, which walks a
    # depot forward INSIDE the army's supply because the depot IS the army's supply
    # (campaign_claim.column_claims + the `escorted` clause above); and [24.6] the railway the
    # Commonwealth may BUILD west from Mersa Matruh -- and the Axis may not -- which moves the whole
    # trace, not merely one column's (game.construction).
    ############################################################################################
    """
    if not orders:
        return orders
    fed: dict = {}
    # The depots that count: friendly, real, holding AMMUNITION -- the commodity every unit needs and
    # the one that runs a foot battalion dry (49.12: infantry burns no Fuel at all, so a fuel-only
    # depot feeds it nothing). Wells are geography and hold water only, so they are never "supply".
    depots = [s.hex for s in state.supplies
              if s.side == side and not s.is_dummy and s.ammo > 0
              and not wells.is_water_source(s)]
    if not depots:
        return orders                          # no depot anywhere: never freeze the army

    def ok(u, dest: Coord) -> bool:
        key = (dest, u.cpa, u.mobility, supply.fuel_rate(u), supply.ammo_cost(u, phasing=True))
        if key not in fed:
            fed[key] = _can_trace(state, replace(u, hex=dest))
        return fed[key]

    def toward_supply(frm: Coord, dest: Coord) -> bool:
        return (min(distance(dest, d) for d in depots)
                < min(distance(frm, d) for d in depots))

    out = []
    for o in orders:
        u = state.unit(o.unit_id)
        if u is None:
            continue
        if _can_trace(state, u):
            if ok(u, o.to):                    # IN SUPPLY: it may not march OUT of supply
                out.append(o)
            continue
        if ok(u, o.to) or toward_supply(u.hex, o.to):
            out.append(o)                      # DRY: only into the trace, or nearer a depot
        # otherwise: HOLD. A starving unit does not march deeper into the desert.
    return out


def _room_in(state, dump, commodity: str) -> int:
    """The 54.12 HEADROOM of `dump`: how many more Points of `commodity` its hex may legally hold.
    A dump is not a bottomless hole -- supply.dump_capacity_at caps it by terrain AND location (a
    major city is unlimited, a village takes the Village row, anything else the Other-Terrain row)
    -- and the engine lands only what fits, silently. Any order sized past this ceiling is a no-op,
    so the relay asks first."""
    cap = supply.dump_capacity_at(state, dump.hex)
    return max(0, cap[commodity] - getattr(dump, commodity.lower()))


def _lands_anything(state, dump, t, out: int, reserve: int) -> bool:
    """Is `dump` a DELIVERY ADDRESS for this lorry -- would anything it carries actually land there?

    A dump at its 54.12 ceiling accepts nothing, and the engine lands nothing into it SILENTLY (see
    engine._truck_unload). So a relay that reads a full depot as a destination drives to it, unloads
    air, drives home for more, and repeats that until the war ends. This is the question that stops
    it: room for the ammo I hold, or the stores I hold, or the fuel I could spare after the trip."""
    if t.ammo > 0 and _room_in(state, dump, "AMMO") > 0:
        return True
    if t.stores > 0 and _room_in(state, dump, "STORES") > 0:
        return True
    return t.fuel - out - reserve > 0 and _room_in(state, dump, "FUEL") > 0


def _fit_to_dest(state, load: dict, t, dest) -> dict:
    """Trim a fresh load to what the DESTINATION can actually land (54.12) -- never lift what cannot
    be put down.

    A lorry that picks up a commodity its delivery address is already full of can NEVER unload it. It
    stays `carrying` for ever, so it can never stop to load a real cargo, and the carrying branch then
    shuttles it to and fro between two full dumps until the last Game-Turn.

    MEASURED, the moment the charts landed: the railway lands 1,500 STORES a Game-Turn (54.32) into a
    railhead whose 54.12 Other-Terrain ceiling is 1,000, so Stores pinned at the cap the length of the
    Commonwealth spine -- and the 70-Point Medium park, the biggest formation the Commonwealth owns,
    lifted 157 Stores on Game-Turn 7 and spent the next hundred Game-Turns driving Mersa Matruh to
    Sidi Barrani and back with them still aboard, delivering NOTHING and burning 1,260 Fuel a turn out
    of the forward depot it was sent there to fill."""
    fitted = dict(load)
    for c in ("AMMO", "STORES"):
        room = max(0, _room_in(state, dest, c) - getattr(t, c.lower()))
        if fitted.get(c, 0) > room:
            fitted[c] = room
        if fitted.get(c, 0) <= 0:
            fitted.pop(c, None)
    return fitted


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
    # MEASURED AND REVERTED, so it is not re-invented: anchoring the relay on the RAILHEAD instead of
    # the port (the loading point walks west with the track, which is the real reason Britain built
    # the railway) reads beautifully and wrecks the campaign. The [60.43] chart stations 50 of the
    # Commonwealth's Truck Points in CAIRO and ALEXANDRIA; move their reload point 80 hexes west to a
    # forward railhead and they can no longer reach it, the Delta park idles for the whole war, and
    # the Eighth Army never comes forward at all (GT12: ZERO reinforcements left the Delta, against
    # three before). The port of arrival is where the trucks live. It stays the anchor.
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
        # [54.11] ...and the depots that DO NOT EXIST YET. The chain extends itself onto the hexes
        # the army is actually standing on, so the network follows the advance instead of the
        # advance starving away from the network (_forward_depot_sites). They are ordinary delivery
        # addresses from here down; the engine founds one the instant a lorry unloads into it.
        forward += _forward_depot_sites(state, side, objective, here, enemy_held, reach)
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
        carrying = t.ammo > 0 or t.stores > 0
        if carrying:
            # Deliver into the DEEPEST reachable dump the truck can AFFORD the hop to -- not
            # blindly the farthest (which may cost more cargo fuel than it holds), so a nearer,
            # cheaper dump is the fallback.
            # ...and only where something will actually LAND (_lands_anything): a depot standing at
            # its 54.12 ceiling is not a delivery address, it is a wall.
            affordable = [s for s in in_reach
                          if t.fuel >= supply.truck_move_fuel(t, reach[s.hex])
                          and _lands_anything(state, s, t, supply.truck_move_fuel(t, reach[s.hex]),
                                              keep(t, s.hex))]
            if affordable:
                dest = min(affordable, key=lambda s: (not _a_link_in_the_chain(s, anchor),
                                                      distance(s.hex, objective), reach[s.hex], s.id))
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
            deliverable = [s for s in forward
                           if _lands_anything(state, s, t, 0, keep(t, s.hex))]
            if deliverable:                                # nothing affordable in reach -> close the gap
                dest = min(deliverable, key=lambda s: (not _a_link_in_the_chain(s, anchor),
                                                       distance(s.hex, objective), s.id))
                step = _step_toward(reach, t.hex, dest.hex)
                if step is not None and t.fuel >= supply.truck_move_fuel(t, reach[step]):
                    orders.append(TruckOrder(t.id, to=step))
                    continue
            if sink is not None:                           # sub-hop fuel, stuck on a dump: shed the
                # unmovable ammo/stores into it (a pure co-located transfer) so the truck is never
                # frozen holding a load it cannot move, and is free to return for fuel next phase.
                #
                # ONLY WHAT WILL ACTUALLY LAND, and if none of it will, DO NOT `continue`. A dump has
                # a 54.12 ceiling (game.supply.dump_capacity) and the engine silently lands nothing
                # into a full one -- so a blind shed order became a NO-OP the truck re-issued every
                # OpStage, for ever, a livelock that never moved and never burned a Point. Measured
                # the moment the [60.44] chart put real stock on Sidi Barrani: the depot reached its
                # Other-Terrain ceiling, and the 70-Point Medium park -- the largest formation the
                # Commonwealth owns -- sat on it holding 157 Stores it could not put down, making ONE
                # move in twenty-five Game-Turns. A lorry that cannot unload here drives home instead.
                unload = {c: min(getattr(t, c.lower()), _room_in(state, sink, c))
                          for c in ("AMMO", "STORES")}
                unload = {c: q for c, q in unload.items() if q > 0}
                if unload:
                    orders.append(TruckOrder(t.id, unload_to=sink.id, unload=unload))
                    continue

        # EMPTY of cargo, standing on a dump that still has FUEL: load a fresh forward leg (the
        # 56.22 split) off it and run it. `not carrying` is what the CARRYING block's old
        # unconditional `continue` used to say: a lorry with a load still aboard has a delivery to
        # finish and must never stop to pick up MORE. It now falls through to the return leg
        # instead of `continue`-ing, so that guard has to be stated here rather than implied.
        if not carrying and colocated is not None and colocated.fuel > 0 and (in_reach or forward):
            load = _load_56_22(t, colocated)
            if in_reach:
                # A forward dump within one convoy hop -- LOAD + MOVE + UNLOAD in one order, but
                # ONLY when the truck can afford the move and still keep its return reserve (the
                # base relay's 49.18 guard, generalised to `keep`), so it never loads a leg it
                # cannot move (the freeze) NOR delivers itself past the point of no return.
                dest = min(in_reach, key=lambda s: (not _a_link_in_the_chain(s, anchor),
                                                    distance(s.hex, objective), reach[s.hex], s.id))
                load = _fit_to_dest(state, load, t, dest)   # never lift what dest cannot land (54.12)
                # AND THE CHAIN IS NEVER CANNIBALISED TO FILL A SINK. Lifting from link N to fill
                # link N+1 is the bucket brigade -- the whole job. Lifting from link N to fill a
                # FIELD dump, which the relay may never lift back OUT of (_relay_source), pours the
                # chain into a hole: the load stops moving for good and the link it came from is
                # emptier than before. Only the ANCHOR may fill a sink, because the anchor is the
                # bottomless port of arrival and giving supply away is what a faucet is for.
                #
                # This is the same law the OPEN-DESERT leg below already keeps ("off the faucet
                # ONLY"), which is why it never bit until now: no Axis field dump had ever sat within
                # one 30-CP hop of the chain. The take-and-hold puts one there -- a flying column's
                # escort depot, planted on SOLLUM, three hexes past the chain's tail at Bardia -- and
                # the lorries promptly began pumping AX-Stage-Bardia straight through into it.
                # MEASURED at Game-Turn 24: 8,616 Fuel Points delivered INTO Bardia and 8,611 lifted
                # back OUT, the larder of the garrison banking a hundred Victory Points left at ZERO.
                # A truck with nothing but a sink ahead of it goes BACK for more (the return leg
                # below); it does not carry the depot under its wheels off into the desert.
                cannibalises = (not _a_link_in_the_chain(dest, anchor)
                                and not _is_faucet(colocated, anchor))
                out = supply.truck_move_fuel(t, reach[dest.hex])
                fuel_deliver = t.fuel + load.get("FUEL", 0) - out - keep(t, dest.hex)
                if not cannibalises and fuel_deliver > 0:
                    unload = {"FUEL": fuel_deliver}
                    for c in ("AMMO", "STORES"):
                        amt = getattr(t, c.lower()) + load.get(c, 0)
                        if amt > 0:
                            unload[c] = amt
                    orders.append(TruckOrder(t.id, load_from=colocated.id, load=load,
                                             to=dest.hex, unload_to=dest.id, unload=unload))
                    continue
            elif _is_faucet(colocated, anchor):
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
                dest = min(forward, key=lambda s: (not _a_link_in_the_chain(s, anchor),
                                                   distance(t.hex, s.hex),
                                                   distance(s.hex, objective), s.id))
                step = _step_toward(reach, t.hex, dest.hex)
                if step is not None and t.fuel + load.get("FUEL", 0) >= supply.truck_move_fuel(
                        t, reach[step]):
                    orders.append(TruckOrder(t.id, load_from=colocated.id, load=load, to=step))
                    continue

        # No forward leg to make from here: HEAD FOR THE ANCHOR to reload -- topping up from a
        # co-located fuel dump to its return reserve so a truck at a drained chain-tip is never
        # stranded on fumes. This is what keeps the pool cycling instead of walking itself dry.
        #
        # ANY truck not standing on the anchor, in EITHER direction. The guard used to read "the
        # anchor is further from the objective than I am" -- i.e. only a truck FORWARD of the anchor
        # was ever sent back to it -- which silently stranded every lorry that began the war BEHIND
        # the port of arrival. The [60.43] chart stations 30 Truck Points in ALEXANDRIA, 34 hexes
        # behind the Mersa Matruh railhead: measured, they made exactly ONE delivery, to El Hamman,
        # and then sat there for the remaining 108 Game-Turns, because from El Hamman -- still east
        # of the railhead -- the relay had no leg that would take them west to it. A lorry with
        # nothing to carry drives to the faucet; which side of it he happens to be on is not a
        # reason to park in the desert.
        if anchor is not None and t.hex != anchor.hex:
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
    """The campaign Axis forward-SUPPLY behaviour, shared by the scripted CampaignAxisPolicy and the
    live CampaignStaffPolicy (game.campaign_staff): the multi-hop coastal truck haul
    (campaign_truck_orders) instead of the base single-hop port shuttle, and hiding the staging
    dumps from the base leapfrog bridge (which would otherwise walk the waypoint chain toward
    Alexandria and UNSTAGE the relay the trucks feed -- see _without_staging). Campaign-only --
    rommels_arrival / siege_of_tobruk seed trucks through the byte-locked base relay and never
    construct these.

    SUPPLY ONLY. The rule-64.73 standing orders on the ARMY are take_and_hold_moves /
    take_and_hold_supply, which each campaign policy lays over its own march; the live staff keeps
    just the garrison half of them (game.campaign_staff), because the whole point of a staff is that
    it decides where the rest of the army goes."""

    def demolition(self, state: GameState, side: Side) -> list[DemolitionOrder]:
        # [54.14] Deny the enemy your stocks -- symmetric, both sides, one standing order (deny_dumps).
        return deny_dumps(state, side)

    def construction(self, state: GameState, side: Side) -> list[BuildOrder]:
        # [24.9] The Panzerarmee extends its chain east on exactly the same terms the Eighth Army
        # extends its own (build_the_chain). What it does NOT get is 24.6: the Construction Chart's
        # Build row for Railroad reads NZERC and there is no Axis row at all. That asymmetry is the
        # rulebook's, and it is the historical one -- the Eighth Army could push a railhead west and
        # be fed off it; Rommel could only lengthen a lorry haul from Benghazi.
        return build_the_chain(state, side)

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        return campaign_truck_orders(state, side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        return super().supply_orders(_without_staging(state), side)


class CampaignAxisPolicy(_CampaignAxisSupplyMixin, ScriptedPolicy):
    """The scripted Axis for the FULL campaign: the base attacker (attacker=AXIS, so combat and
    elastic retreat are inherited and byte-identical to ScriptedPolicy(Side.AXIS)), PLUS the
    multi-hop coastal haul (see _CampaignAxisSupplyMixin) that lets the Panzerarmee fight east of
    Benghazi at all, PLUS -- exactly as the Commonwealth has -- the rule-64.73 take-and-hold.

    THE AXIS PLAYS THE POINTS TOO. It opens the campaign holding Tobruk (200) and Bardia (100) and
    controlling Benghazi (75) and Derna (25); it garrisoned none of them and marched the whole army
    east at Alexandria, so it banked whatever the standing garrison order happened to pin and threw
    the rest away -- measured, it lost Bardia in every seed, a hundred Victory Points it starts the
    war standing on. It is on the offensive at all times, so its flying columns take their depots
    with them (escort=True); everything else -- which city, which unit, whether it can be fed there
    at all -- is campaign_claim's side-generic judgement, the same judgement the Commonwealth uses."""

    def __init__(self):
        super().__init__(attacker=Side.AXIS)

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        return take_and_hold_moves(state, side, super().movement(state, side), escort=True)

    def retreat_before_assault(self, state: GameState, side: Side,
                               pinned: frozenset[str]) -> list[MoveOrder]:
        # The garrison half of the standing order, on the OTHER door out of a city (13.21: Retreat
        # Before Assault is voluntary movement, so hold_garrisons has to watch it too -- see the
        # Commonwealth's own override). Symmetric by design: the Axis opens the war standing on
        # Tobruk and Bardia, and a garrison that slips out of a fortress to dodge an assault has
        # thrown the city away just as surely as one that marched off east.
        return hold_garrisons(super().retreat_before_assault(state, side, pinned), state, side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        return take_and_hold_supply(state, side, super().supply_orders(state, side), escort=True)
