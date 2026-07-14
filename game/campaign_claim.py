"""THE TAKE-AND-HOLD (rule 64.73) -- the half of the campaign that is not a march.

Rule 64.73 scores each side, at the FINAL Game-Turn, on the victory CITIES it holds with a SUPPLIED
combat unit. It does not score how far the spearhead got. An offensive that drives every battalion
at objective_for() therefore banks the objective and nothing else -- and that is exactly what the
scripted Commonwealth did: measured over the full campaign, it sprinted past Sollum, Bardia and
Derna to Benghazi, garrisoned none of them, and finished 200-120 down with 250 Victory Points of
EMPTY CITY lying behind its own front line. The same disease the LLM staff has: it chases the
objective hex instead of the points.

So this module is the standing orders a competent staff would keep, in the three beats the rule
itself dictates:

  * TAKE (claims / claim_moves) -- every turn, each victory city the side does not already bank gets
    the NEAREST unit that could actually be FED there detached to go and get it. An empty city is
    walked onto; an ENEMY-HELD one is closed on and left to the inherited combat reflex, which
    assaults whatever it finds itself adjacent to. Nothing here knows that Bardia and Tobruk are
    fortresses: rule 15.82 grants them NO EVICTION and no assault will ever move those garrisons, so
    a siege takes them only by 15.15 -- dry-ammunition SURRENDER -- or not at all.
  * FEED (claim_supply) -- a garrison that cannot trace Fuel and Ammunition banks NOTHING (64.73's
    occupation quality-test), and out at Siwa or Jalo there is no depot within forty hexes: the wells
    hold water and nothing else. A depot may only relocate onto a hex a friendly COMBAT unit already
    holds (32.33), so the depot cannot go first. The garrison and its depot therefore march as a
    PAIR, AT THE DEPOT'S PACE, and only to where the lorries can keep it fed -- a column that walks
    into the desert ahead of its supply arrives unsupplied and scores nothing, which is the standing
    failure mode of every policy in this repo.
  * HOLD (garrison_units/hold_garrisons + garrison_depots/hold_depots) -- the unit banking a city
    never marches away, and neither does the depot feeding it. Two halves of one standing order: a
    depot walked off a city un-banks it just as surely as marching the garrison off does.

THE ONE CLAUSE THAT DOES ALL THE SORTING is 'could be FED there' (can_be_fed -- the 64.73 trace test
asked of a unit as if it already stood on the city). It sends the army to Sollum, and through Sollum
to Bardia; it declines Siwa and Jalo, which are reachable but not suppliable; and it decides, with no
fortress special-case anywhere, that Bardia is worth besieging and Tobruk -- for most of the war --
is not. You do not besiege a city you could not hold, and you do not garrison one you cannot feed.

Campaign-ONLY: every helper needs the 64.73 city table, which rommels_arrival / siege_of_tobruk do
not carry (_cities returns () for them), so the two benchmark scenarios stay byte-identical.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from . import stacking, supply, tactics, wells
from .events import Control, Side
from .hexmap import Coord, distance
from .policy import MoveOrder, SupplyMoveOrder
from .state import GameState

STAGING = ("AX-Stage", "AL-Stage")     # the seeded supply SPINES of both sides (60.34 / 54.3)


def _cities(state: GameState) -> tuple:
    """The rule-64.73 city table, or () for a scenario that carries none -- which is every scenario
    but the campaign, and is what makes every helper in this module safe to call anywhere."""
    return tuple(getattr(state.victory, "cities", None) or ())


def _banking(state: GameState, side: Side, ax: Coord) -> list:
    """The combat units of `side` BANKING the city at `ax` right now -- standing on it, alive, at
    Strength, and able to trace Fuel AND Ammunition. The exact rule-64.73 occupier test, asked of
    the live state, so every helper here scores the city the way the game itself will."""
    vic = state.victory
    return [u for u in state.units_at(ax)
            if u.side == side and u.alive and u.is_combat and u.strength >= 1
            and vic._supplied(state, u)]


def within_a_lorry_hop(state: GameState, side: Side, frm: Coord, to: Coord, cache: dict) -> bool:
    """Could a lorry make `frm` -> `to` in ONE Truck Convoy Phase (rule 53.22, the 30-CP extended
    convoy CPA)? Asked of the engine's own supply.reachable_truck_moves, so no magnitude is invented
    -- and it is the very test the seeded supply chain is BUILT on: 'each depot is within one 30-CP
    truck convoy hop of the one behind it, so the relay can bucket-brigade into it'
    (scenario._campaign_cw_depots).

    THIS IS WHAT SEPARATES A LINK IN THE CHAIN FROM A BOX OF SUPPLIES DYING IN THE SAND, and it is
    the honest answer to 'can a garrison be supplied out there'. A depot the lorries cannot reach is
    never refilled; rule 49.3 evaporates six per cent of it every Game-Turn; and the garrison it was
    sent to feed starves long before the final Game-Turn that scores it.

    MEASURED, and this is not a guess -- the flying columns DID reach SIWA and JALO, and were banked
    there at Game-Turn 24. By Game-Turn 111 both depots were dry, both garrisons had starved, both
    cities stood empty, and the two dumps were gone from the army's park for good (32.33: a dump only
    relocates onto a hex a friendly COMBAT unit holds, so a depot alone in the desert is stranded
    there for the rest of the war). Meanwhile the lorry pool quadrupled its mileage -- 106 moves to
    449 -- driving off into the desert after them, because a dump at Jalo reads as 'forward' to the
    relay. The Commonwealth lost BENGHAZI and SIDI BARRANI, a hundred and ten Victory Points, chasing
    thirty it could not keep. The oases are reachable. They are not SUPPLIABLE."""
    if frm not in cache:
        truck = next((t for t in state.trucks if t.side == side), None)
        if truck is None:
            return False            # no lorries at all: nothing could ever refill a depot out there
        cache[frm] = supply.reachable_truck_moves(state, replace(truck, hex=frm))
    return to in cache[frm]


def is_field_dump(su) -> bool:
    """A FIELD dump: the mobile supply an army drags along behind it (32.3). NOT a rule-57
    strategic base (immobile), not a well (52.11 geography, not a depot), and not one of the seeded
    staging depots -- a railhead, a railway station or a Field Supply Depot is a place ON the supply
    line, not a dump that follows the army (the distinction campaign_policy._without_staging already
    draws for the leapfrog bridge)."""
    return (not su.base and not su.is_dummy and not su.id.startswith(STAGING)
            and not wells.is_water_source(su))


# --- HOLD: the standing orders on a city already banked ------------------------------------------

def garrison_units(state: GameState, side: Side) -> set:
    """THE STANDING GARRISON ORDER (rule 64.73). The campaign is scored on the victory cities a side
    HOLDS SUPPLIED at the end, so a combat unit already sitting on one it can trace supply at is
    banking its points for free, and marching it away throws them in the desert.

    Measured, this is the single largest source of value destruction in the campaign: the Axis opens
    holding Tobruk (200 VP) and Bardia (100 VP) with the Libyan Tank Command, and EVERY policy tried
    -- scripted and LLM alike -- marched those garrisons east and finished with every victory city
    empty (a 0-0 draw), while a side that did NOTHING AT ALL simply held them and won 300-10.

    So one unit per supplied victory city stays put: a standing order no competent staff would
    countermand. It prefers a non-tank holder, freeing the armour for manoeuvre (the real reason the
    garrisons kept leaving: they ARE the armour, and the mobile lane wants them)."""
    held = set()
    for ax, _avp, _cvp, _name in _cities(state):
        here = _banking(state, side, ax)
        if here:
            held.add(min(here, key=lambda u: (u.is_tank, u.id)).id)   # infantry first
    return held


def hold_garrisons(orders: list, state: GameState, side: Side) -> list:
    """Drop any move order for a unit under the standing garrison order (garrison_units): it holds
    its supplied victory city and banks the points. Combat orders are untouched -- a garrison still
    fights from its city. Applied by every campaign policy, scripted and staff alike."""
    keep = garrison_units(state, side)
    return [o for o in orders if o.unit_id not in keep] if keep else orders


def depot_on(state: GameState, side: Side, ax: Coord):
    """The side's seeded SPINE depot standing on the city at `ax`, if any -- the rail-fed railhead at
    Mersa Matruh, or one of the Operation Compass Field Supply Depots at Sidi Barrani and Sollum
    (60.34 / 54.3)."""
    return next((s for s in state.supplies
                 if s.side == side and s.hex == ax and s.id.startswith(STAGING)), None)


def spine_awaits_control(state: GameState, side: Side, ax: Coord) -> bool:
    """A city with the side's OWN Field Supply Depot standing on it, EMPTY, on a hex the ENEMY still
    controls. Such a city needs no depot marched to it -- it HAS one, and what is keeping it dry is
    not distance but CONTROL: the lorry relay will not deliver into a hex the enemy holds
    (campaign_truck_orders' own 56.15-shaped gate), and neither will the 32.3 leapfrog put a field
    dump on ground the army does not stand on. Take the hex and the supply follows; the honest trace
    test (can_be_fed) cannot see that, because it asks what the depot holds TODAY.

    THIS IS THE WHOLE STORY OF SOLLUM, and it is the hinge of the whole take-and-hold. The
    Commonwealth swept past Sollum for a hundred and eleven Game-Turns without once standing on it.
    The hex stayed AXIS-CONTROLLED to the last turn of the war; AL-Stage-Sollum -- the third link of
    the Commonwealth's OWN supply chain, seeded one 22-CP lorry hop beyond Sidi Barrani -- stood
    empty the whole time; and the ten points sat there untaken. Put one battalion on it and the
    supply comes up behind it within a Game-Turn or two (measured: a depot holding ~400 Ammunition
    Points stands on Sollum from Game-Turn 24 to the end, and the city banks in every seed tried).

    And the ten points are the least of it. A depot ON Sollum is what puts BARDIA -- three hexes away,
    and worth FIFTY -- inside a Commonwealth supply trace for the first time in the campaign, which
    is what makes Bardia worth besieging at all (see the siege clause in claims).

    It must be the enemy's CONTROL that is the blocker and nothing else. A depot of ours standing
    empty on a hex we ALREADY hold is empty for a quite different reason: the relay is a bucket
    brigade that LIFTS from each staging depot to fill the one in front of it, so every link BEHIND
    the chain's head is a transit node drained to zero (measured: AL-Stage-Barrani takes fifty
    deliveries over the campaign and still sits at zero at the end of every one). Standing another
    battalion on THAT will not fill it -- it just parks a brigade on a hex it can never bank. So the
    shortcut is gated on enemy control, and everywhere else can_be_fed governs."""
    depot = depot_on(state, side, ax)
    enemy_holds = Control.AXIS if side == Side.ALLIED else Control.ALLIED
    return (depot is not None and depot.empty
            and state.control_of(ax) == enemy_holds)


def garrison_depots(state: GameState, side: Side) -> set:
    """THE STANDING ORDER ON THE DEPOT -- the exact dual of garrison_units, and the half without
    which the other half is worthless. A garrison out at Bardia or Derna is supplied by ONE thing:
    the field dump standing under it. The base 32.3 bridge leapfrogs every fuelled dump toward the
    objective, so the turn after the depot arrives it would march straight off again to the head of
    the column -- and the city it just made bankable would stop scoring. A depot feeding a banked
    city is part of the garrison.

    NOT on a city the SPINE already feeds (depot_on). A field dump parked on top of a seeded Field
    Supply Depot is not doing logistics -- it is MASKING one. The lorry relay picks its delivery
    address by (distance-to-objective, reach, id) and two dumps on one hex tie on the first two, so
    'AL-Dump#2' wins the tie over 'AL-Stage-Barrani' and every load lands in the field dump instead
    of the depot the chain is built out of. Measured: pin a field dump on Sidi Barrani and
    AL-Stage-Barrani takes 0 of 24 deliveries and stands empty at Game-Turn 24, the Sollum leg of the
    chain is never fed, and the Commonwealth loses BENGHAZI -- a hundred Victory Points -- to save a
    ten-point city that the railway was already feeding for free.

    One depot per city (the richest field dump on it), so a stack of dumps that happens to pile up on
    the objective is not frozen wholesale -- only the one actually doing the feeding."""
    keep = set()
    for ax, _avp, _cvp, _name in _cities(state):
        if depot_on(state, side, ax) is not None or not _banking(state, side, ax):
            continue
        here = [s for s in state.supplies
                if s.side == side and s.hex == ax and is_field_dump(s)]
        if here:
            keep.add(max(here, key=lambda s: (s.ammo, s.water, s.fuel, s.id)).id)
    return keep


def hold_depots(orders: list, state: GameState, side: Side) -> list:
    """Drop any relocation order for a depot under the standing order above (garrison_depots)."""
    keep = garrison_depots(state, side)
    return [o for o in orders if o.supply_id not in keep] if keep else orders


def keep_off_the_spine(orders: list, state: GameState, side: Side) -> list:
    """A FIELD DUMP DOES NOT PARK ON TOP OF A FIELD SUPPLY DEPOT. That hex belongs to the chain.

    The lorry relay picks its delivery address by (distance-to-objective, reach, id), and two dumps
    on one hex tie on the first two -- so the tie breaks on the ID, 'AL-Dump#2' beats
    'AL-Stage-Barrani', and every load lands in the field dump. And a field dump is precisely what
    the relay may NOT lift from again (campaign_policy._relay_source lifts only from the supply LINE
    and the port of arrival -- a lorry that carries a division's stock back off it has done negative
    work). So supply goes IN to a masked link and can never come OUT: the chain is severed at exactly
    the hex that was built to carry it.

    MEASURED, twice, and both times it cost the campaign. A field dump parked on Sidi Barrani took
    every one of AL-Stage-Barrani's deliveries, left the seeded depot at zero, starved the Sollum leg
    beyond it, and lost the Commonwealth BENGHAZI -- a hundred Victory Points. Field dumps sitting on
    all three of Matruh, Barrani and Sollum drained the whole seeded spine to zero fuel while the
    lorries ran four times their old mileage feeding dumps that could never pass it on.

    The army's mobile supply follows the army (32.3); the chain's own depots stay where the chain
    put them; and the two do not stand on the same hex."""
    spine = {s.hex for s in state.supplies
             if s.side == side and s.id.startswith(STAGING)}
    if not spine:
        return orders
    return [o for o in orders
            if o.to not in spine or not is_field_dump(state.supply(o.supply_id))]


# --- TAKE: go and occupy the cities you do not hold -----------------------------------------------

@dataclass(frozen=True)
class Claim:
    """One victory city, the unit detached to occupy it, and -- when the city cannot yet feed a
    garrison -- the depot that marches with it (32.33)."""
    city: Coord
    name: str
    unit_id: str
    depot_id: "str | None"


def claims(state: GameState, side: Side, *, escort: bool = True) -> tuple[Claim, ...]:
    """THE TAKE. One detachment per unclaimed victory city, richest city first, computed fresh from
    the state every call (stateless, like the truck relay -- so it re-aims itself as the front, the
    depots and the enemy move, and needs no memory to stay consistent between the Movement and the
    Supply Movement Phase).

    A city is a target when it is worth points to this side and this side is not already BANKING it.
    Its garrison is the NEAREST unit that could be FED there -- and everything else follows from that
    one question, asked of the unit as if it ALREADY STOOD on the city (can_be_fed: rule 64.73's own
    trace test). A city that can feed nobody is not claimed at all. We do not send men to starve on a
    hex that scores nothing, which is the standing failure mode of every policy in this repo.

    The four answers:

      * ENEMY-HELD, and we could be fed there -> THE SIEGE. The hex cannot be walked onto; the unit
        closes on it and the inherited combat reflex assaults. Rule 15.82 gives the fort-2 majors NO
        EVICTION, so only 15.15 dry-ammunition SURRENDER will ever take Bardia or Tobruk -- and
        nothing here knows they are fortresses. 'Could we be fed there' sorts them by itself: it sends
        the army to BARDIA (fed from the Sollum depot three hexes off, once Sollum is taken) and
        leaves TOBRUK alone until the same test says otherwise. You do not besiege a city you could
        not hold.
      * A STOCKED DEPOT ALREADY IN TRACE -> send the unit alone, at its own pace.
      * OUR OWN FIELD SUPPLY DEPOT ON IT, EMPTY, ON AN ENEMY-CONTROLLED HEX (spine_awaits_control)
        -> send the unit alone. The depot is already there; what is keeping it dry is CONTROL, and
        taking the hex is what fixes that. This is the hinge -- see spine_awaits_control for SOLLUM,
        and for why a field dump must never be sent to such a city instead.
      * NOTHING AT ALL -> THE FLYING COLUMN: a spare field depot marches WITH the garrison (`escort`),
        the pair moving together at the depot's pace (claim_moves). Only to where the lorries can
        keep it fed (within_a_lorry_hop -- which is what declines Siwa and Jalo), and never with the
        army's LAST spare depot: an army with no mobile supply behind it cannot hold what it takes,
        and the objective it is advancing on is a victory city too.

    Armour is passed over where an infantryman will do (the same preference the standing garrison
    order applies), so the mobile lane keeps its tanks."""
    targets = []
    for ax, avp, cvp, name in _cities(state):
        points = avp if side == Side.AXIS else cvp
        if points <= 0 or _banking(state, side, ax):
            continue
        targets.append((-points, ax, name))
    if not targets:
        return ()
    targets.sort()

    held = garrison_units(state, side)              # never strip one city to garrison another
    free = sorted((u for u in state.living(side)
                   if u.is_combat and u.strength >= 1 and u.id not in held
                   and supply.plan_draw(state, u, supply.FUEL,
                                        supply.fuel_cost(u, 1)) is not None),
                  key=lambda u: u.id)
    pinned = garrison_depots(state, side)
    spare = sorted((s for s in state.active_supplies(side)
                    if is_field_dump(s) and s.id not in pinned and s.ammo > 0
                    and s.fuel >= supply.SUPPLY_MOVE_FUEL and state.port_at(s.hex) is None),
                   key=lambda s: s.id)

    # The 'fed there' test depends only on the CITY and the unit's supply CLASS (its trace budget,
    # its terrain class and what it must draw) -- never on where the unit currently stands. Two
    # reachability searches apiece, so cache them by class: a fifty-unit army has four.
    fed: dict = {}

    def can_be_fed(u, ax: Coord) -> bool:
        key = (ax, u.cpa, u.mobility, supply.fuel_rate(u), supply.ammo_cost(u, phasing=True))
        if key not in fed:
            fed[key] = state.victory._supplied(state, replace(u, hex=ax))
        return fed[key]

    reach: dict = {}                                # a depot's CPA-15 relocation reach, once each

    def can_follow(s, hx: Coord) -> bool:
        if s.hex == hx:
            return True
        if s.id not in reach:
            reach[s.id] = supply.reachable_moves(state, s)
        return hx in reach[s.id]

    hops: dict = {}                                 # a lorry's 53.22 convoy reach, once per origin

    def sustainable(s, ax: Coord) -> bool:
        # The depot may only plant itself where the LORRIES CAN FOLLOW (within_a_lorry_hop): a link
        # the chain can extend to, not a box of supplies dying in the sand. This is the clause that
        # declines Siwa and Jalo -- and the measurement behind it is in within_a_lorry_hop.
        return within_a_lorry_hop(state, side, s.hex, ax, hops)

    taken_units: set = set()
    taken_depots: set = set()
    plan: list[Claim] = []
    for _neg, ax, name in targets:
        spine = spine_awaits_control(state, side, ax)
        besieged = any(u.is_combat and u.strength >= 1 for u in state.enemies_at(ax, side))
        for u in sorted(free, key=lambda u: (distance(u.hex, ax), u.is_tank, u.id)):
            if u.id in taken_units:
                continue
            if besieged:
                # THE SIEGE. An enemy-held city cannot be walked onto -- it has to be assaulted off,
                # and rule 15.82 grants the fort-2 majors NO EVICTION, so for Tobruk and Bardia no
                # assault will ever move the garrison: only 15.15, dry-ammunition SURRENDER, will.
                # So the detachment is sent to CLOSE ON the city and the inherited combat reflex does
                # the rest (it assaults whatever it ends up adjacent to) -- no fortress special case,
                # nothing hacked around 15.82.
                #
                # ONLY IF WE COULD HOLD THE PLACE. You do not besiege a city you cannot feed a
                # garrison on: the hex would score nothing even if it fell, and the men sent to take
                # it starve in front of it. That single clause sorts the two fortresses by itself --
                # measured at Game-Turn 64, BARDIA can be supplied by 18 of the 43 Commonwealth units
                # (AL-Stage-Sollum sits three hexes away with 560 Ammunition Points, once Sollum is
                # taken) and is held by ONE Italian marine battalion the cut Axis chain has left
                # unsupplied; TOBRUK can be supplied by NONE of them, and is left alone.
                #
                # ...OR IF OUR OWN DEPOT IS STANDING ON IT (`spine`, spine_awaits_control) -- the
                # SAME question the un-besieged branch below asks, and it must be asked here too.
                # can_be_fed reads what the depot holds TODAY, and a Field Supply Depot of ours under
                # an enemy GARRISON holds nothing today for exactly the reason the garrison is the
                # problem: no lorry delivers into a hex the enemy is standing in. Ask only can_be_fed
                # and the city is never claimed, never besieged, and our own depot on it stays dry for
                # the whole war -- which is the precise failure spine_awaits_control was written to
                # end, resurrected the moment the enemy leaves a battalion behind instead of driving
                # through. MEASURED (seed 1941, once the Axis got the take-and-hold and put
                # IT-1-Libyan on SOLLUM): the Commonwealth stopped claiming Sollum at all,
                # AL-Stage-Sollum -- the third link of its OWN supply chain -- stood empty to Game-Turn
                # 111, and with it BARDIA stayed outside any Commonwealth trace. Sollum is no
                # fortress: 15.82 grants it no eviction rights, so it CAN be assaulted off, and
                # Operation Compass did exactly that.
                if spine or can_be_fed(u, ax):
                    plan.append(Claim(ax, name, u.id, None))
                    break
                continue
            if spine or can_be_fed(u, ax):
                plan.append(Claim(ax, name, u.id, None))
                break
            if depot_on(state, side, ax) is not None:
                # The chain's OWN depot already stands on this city. Never march a field dump onto it:
                # keep_off_the_spine would refuse the order anyway, and a field dump there would mask
                # the depot from the lorries -- severing the chain at the very hex built to carry it.
                # What fills a Field Supply Depot is CONTROL of its hex, not another dump on top of
                # it, and the unit sent above is what takes the control.
                continue
            # THE FLYING COLUMN. Its depot is the nearest spare field dump that can KEEP UP (one able
            # to relocate onto the unit's own hex this stage -- 32.33 lets it, the unit being a
            # friendly combat unit) and that can be KEPT FED where it is going (sustainable). Never
            # the army's LAST spare depot: an army with no mobile supply left behind it cannot hold
            # what it takes, and the objective it is advancing on is a victory city too. A pair that
            # cannot form is not dispatched at all -- we do not send men to starve on a hex that
            # scores nothing.
            if not escort or len(taken_depots) >= len(spare) - 1:
                continue
            depot = next((s for s in sorted(spare, key=lambda s: (distance(s.hex, ax), s.id))
                          if s.id not in taken_depots and can_follow(s, u.hex)
                          and sustainable(s, ax)), None)
            if depot is not None:
                plan.append(Claim(ax, name, u.id, depot.id))
                taken_depots.add(depot.id)
                break
        if plan and plan[-1].city == ax:
            taken_units.add(plan[-1].unit_id)
    return tuple(plan)


def claim_moves(state: GameState, side: Side, plan: tuple[Claim, ...]) -> list[MoveOrder]:
    """THE DETOUR: each detached unit marches at ITS CITY instead of at the far objective. This is
    the whole defect being fixed -- the base attacker only ever proposes a hex strictly closer to
    objective_for(), so Sollum and Derna, which sit BESIDE the geodesic to Benghazi and not on it,
    were never once stepped onto in a hundred and eleven Game-Turns.

    THE COLUMN MOVES AT THE PACE OF ITS DEPOT. An escorted garrison steps only where its depot can
    follow it (supply.reachable_moves, the 32.58A CPA of 15), so the pair arrives together and the
    city can be fed the moment it is taken; a garrison that outran its depot would stand on the city
    banking nothing. An unescorted claim -- a city that already has a depot in trace -- runs at the
    unit's own pace. Every inherited gate still holds: fuel (49.13, checked in claims), stacking
    (9.14) and the tactical reachability the engine re-validates.

    A BESIEGING detachment closes on a city it cannot enter and stops adjacent to it: an enemy-held
    hex is never in tactics.reachable_for, so the march simply runs out of hexes strictly closer to
    the city and the unit stands where it stopped -- in contact. From there the inherited combat
    reflex assaults it every stage, which is the whole of the siege; nothing here knows or cares that
    Bardia is a fortress."""
    if not plan:
        return []
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
    orders: list[MoveOrder] = []
    for c in plan:
        u = state.unit(c.unit_id)
        if u is None or u.hex == c.city:
            continue                         # arrived -- the standing garrison order takes over
        reach = tactics.reachable_for(state, u, enemy_zoc, enemy_occupied)
        if c.depot_id is not None:
            depot = state.supply(c.depot_id)
            if depot is None:
                continue
            follow = supply.reachable_moves(state, depot)
            reach = {h: cp for h, cp in reach.items() if h in follow or h == depot.hex}
        here = distance(u.hex, c.city)
        cands = [h for h in reach
                 if h != u.hex and distance(h, c.city) < here     # only ever toward the city
                 and _stacking_ok(state, u, h)]
        if cands:
            dest = min(cands, key=lambda h: (distance(h, c.city), reach[h], h))
            orders.append(MoveOrder(u.id, dest))
    return orders


def claim_supply(state: GameState, side: Side, plan: tuple[Claim, ...]) -> list[SupplyMoveOrder]:
    """THE DEPOT FOLLOWS ITS GARRISON (rule 32.33). The engine runs the Supply Movement Phase AFTER
    the Movement Phase (engine._supply_movement), so the depot steps onto the hex its garrison has
    just taken -- and onto the CITY itself on the Game-Turn the city falls, which is the step that
    turns a merely OCCUPIED hex into a BANKED one. From the next Record Phase the pair is scoring,
    and garrison_depots pins the depot there for good."""
    orders: list[SupplyMoveOrder] = []
    for c in plan:
        if c.depot_id is None:
            continue
        depot, u = state.supply(c.depot_id), state.unit(c.unit_id)
        if depot is None or u is None or depot.hex == u.hex:
            continue
        if u.hex in supply.reachable_moves(state, depot):
            orders.append(SupplyMoveOrder(depot.id, u.hex))
    return orders


def _stacking_ok(state: GameState, unit, dest: Coord) -> bool:
    """Rule 9.14, exactly as ScriptedPolicy._stacking_ok asks it."""
    present = [u for u in state.units_at(dest) if u.side == unit.side]
    return stacking.within_hex_limit(present + [unit], state.terrain.terrain[dest])
