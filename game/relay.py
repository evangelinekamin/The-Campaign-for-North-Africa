"""The truck-convoy forward relay + 24.9 dump construction (rules 53-54), shared by all competent policies. Extracted from campaign_policy where the dropped byte-lock had kept it."""
from __future__ import annotations

from dataclasses import replace

from . import air, campaign_claim, construction, supply, wells
from .campaign_claim import STAGING
from .events import Control, Side
from .hexmap import Coord, distance
from .policy import BuildOrder, TruckOrder
from .state import GameState, SupplyUnit


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


# ⚠ THE LORRY'S OWN LOADING MIX, AND IT IS A FLAGGED POLICY CONSTANT, NOT A CHART. How a truck
# apportions its 54.2 capacity between fuel, ammunition and stores is a quartermaster's choice; the
# rulebook prints no split for it (53.12 gives only the Point ceiling the mix must satisfy). These
# three numbers were borrowed from `scenario._CONVOY_SPLIT_56_22` when that constant existed -- they
# were never the same decision, and block 5.5 deleted the convoy one (56.22 makes it the Axis
# Player's, taken per sailing in the Convoy Planning Phase). They stay here, under their own name
# and their own flag, because changing what a lorry loads is a separate question from what a ship
# carries and would move both byte-locked benchmarks for no rule.
_TRUCK_LOAD_MIX = {"FUEL": 0.60, "AMMO": 0.25, "STORES": 0.15}


def _load_mix(t, dump) -> dict:
    """A fresh load off `dump`, apportioned by the truck's own loading mix (_TRUCK_LOAD_MIX) and
    sized against its REMAINING 54.2 capacity -- a truck home from a run still holds its return
    reserve, so loading a full share on top of it would overrun the 53.12 Point ceiling and the
    engine would reject the order."""
    cap = supply.truck_capacity(t.truck_class)
    load: dict = {}
    for c, frac in _TRUCK_LOAD_MIX.items():
        room = int(frac * t.points * cap[c]) - getattr(t, c.lower())
        take = min(getattr(dump, c.lower()), max(0, room))
        if take > 0:
            load[c] = take
    return load


# --- [35.15] / [36.3] / [36.17] THE AIR-SUPPLY SHUTTLE -- the faucet on the airfield larder -----
#
# 35.15  "TRUCK UNITS MAY BE ATTACHED TO AN SGSU AS FIRST LINE TRANSPORT. THEY ARE USED TO CARRY
#         THE SUPPLIES THAT THE SGSU NEEDS TO KEEP ITS PLANES FIT AND READIED."
# 36.3   "Players should note that THEY CAN BRING SUPPLIES TO A FLYING BOAT BASIN SIMPLY BY BRINGING
#         TRUCKS INTO THE HEX; they need no other transport."
# 36.17  "An airfield IS A SUPPLY DUMP for supplies to be used by the SGSU's on that airfield. Fuel,
#         ammunition, stores, etc., may be stored at an airfield as if it were a dump."
#
# THE DRAIN HAD NO FAUCET, AND IT WAS MEASURED. [60.34] and [60.44] seed the air-facility dumps once
# -- 850 Axis and 250 Commonwealth Fuel Points -- and until this block NOTHING on the map could put a
# Point back. Seed 4 balanced to the last unit: 850 = 467 evaporated (49.3) + 325 spent on 35.14
# upkeep + 58 burnt by aeroplanes (38.24). The larder emptied around Game-Turn 9-18, every SGSU then
# read unfed (35.14: "SGSUs without the required supplies MAY NOT REPAIR THEIR PLANES"), and both air
# forces were grounded for the remaining ninety Game-Turns. The rule doing that is correct; what was
# missing is the three sentences above, which are the book's three ways to restock an airfield.
#
# WHOSE LORRIES. The [60.33] and [60.43] charts each print a row the engine already seeds and already
# parks ON a facility -- "Any Air Facility: 10 Light, 50 Medium" for the Italians, "5 Light, 30
# Medium, 20 Heavy" for the Commonwealth -- and 35.15 is the sentence that says what those lorries
# ARE. They are carried as `line=1` formations (First Line Transport, attached to a squadron) and are
# the ONLY trucks this shuttle moves; the general freight pool (campaign_truck_orders) never touches
# an air dump, for the reason written at its own air-dump filter.
#
# WHAT IS NOT MODELLED, and each is named where it lands: 36.5's UNLIMITED supply at an off-map
# facility (a fourth refill path, which needs an off-map air box before it needs a rule -- see
# oob.charted_air_facilities); the ATTACHMENT itself as a state relation (an SGSU has no truck
# roster, so "attached" is expressed by the formation's line and its standing at a facility, exactly
# as a unit's first-line ceiling is expressed by its fl_* fields); and AMMUNITION, which the shuttle
# does not carry because nothing in this engine spends an air dump's Ammo Points -- 38.4's bombs are
# a separate commodity and a separate block, and hauling a commodity no one draws would spend 53.12
# capacity on freight that could never be consumed.


def _air_larders(state: GameState, side: Side) -> list:
    """[36.17] The air-facility dumps this shuttle exists to fill, id-ordered."""
    return sorted((s for s in state.supplies
                   if s.side == side and s.air_dump and not s.is_dummy), key=lambda s: s.id)


def _air_demand(state: GameState, side: Side) -> dict:
    """[35.14]/[38.36]/[38.24] HOW FULL A LARDER IS FULL -- one Game-Turn of this side's air
    operations, and the reason the shuttle is not simply pointed at the 54.12 terrain ceiling.

    A dump's 54.12 headroom in open desert is 8,000 Fuel Points. Sized against THAT, the [60.43]
    park's 30-Point Medium formation lifts 2,700 Fuel Points out of the Eighth Army's railhead on
    its first trip and parks them at an airfield no land unit may draw from (36.17) -- which is not
    a faucet, it is a second army's worth of fuel taken out of the war. So the target is the demand,
    and every term of it is a rule with a printed rate:

      * 35.14 -- one Fuel Point per SGSU per Operations Stage and one Stores Point per Game-Turn;
      * 38.36 -- one more Stores Point for every refit ATTEMPT, and this engine attempts once per
        squadron per Operations Stage (flagged at engine._air_maintenance);
      * 38.24/34.17 -- and the aeroplanes' own fuel, one mission's worth for the whole
        establishment at each type's charted Fuel Consumption Rating.

    That last term is what makes the target the right SIZE rather than a guess, and the check is the
    book's own allotment: [60.34] gives the Axis airfields 850 Fuel Points and [60.44] gives the
    Commonwealth's 250, which is very nearly one full-force sortie apiece. The scenario seeded these
    larders at about a Game-Turn of operations, so keeping them there is keeping them where the book
    put them."""
    stages = 3                                           # 48 V: three Operations Stages a Game-Turn
    sgsus = sum(1 for u in state.living(side) if air.is_sgsu(u))
    fuel = sgsus * air.SGSU_FUEL_PER_STAGE * stages
    for w in state.air:
        if w.side != side:
            continue
        for role in ("fighters", "strike", "recon"):
            fuel += air.mission_fuel(side, role, getattr(w, role))
    return {"FUEL": fuel,
            "STORES": sgsus * (air.SGSU_STORES_PER_TURN
                               + air.REFIT_STORES_PER_ATTEMPT * stages)}


def _air_source(state: GameState, side: Side, hx: Coord):
    """The dump an air-supply lorry standing on `hx` may LIFT A RUN FROM: the same test the forward
    relay applies (a constructed dump, a seeded staging depot or a rule-57/port faucet), minus the
    air larders themselves -- carrying supply OUT of one airfield to fill another is not a faucet."""
    here = [s for s in state.supplies
            if s.side == side and not s.is_dummy and s.hex == hx and not s.air_dump
            and not wells.is_water_source(s)
            and (s.constructed or s.base or s.id.startswith(STAGING))]
    return max(here, key=lambda s: (s.fuel + s.stores, s.id), default=None)


def _air_faucets(state: GameState, side: Side) -> list:
    """The bottomless ends the shuttle may reload at: the side's ports of arrival (where its convoys
    and its railway land) and its rule-57 strategic bases. The same set campaign_truck_orders calls
    a faucet, minus the air larders themselves and minus the wells (52.11: geography, not a depot)."""
    ports = {p.hex for p in state.ports if p.side == side}
    return [s for s in state.supplies
            if s.side == side and not s.is_dummy and not s.air_dump
            and not wells.is_water_source(s) and (s.base or s.hex in ports)]


# The air shuttle's own loading mix, and it is _TRUCK_LOAD_MIX's two air commodities renormalised
# over themselves -- the SAME flagged quartermaster's opinion, not a second one. Ammunition is
# dropped because nothing in this engine spends an air dump's Ammo Points (38.4's bombs are a
# separate block), so its share would be capacity spent on freight no squadron could draw.
_AIR_CARGO = ("FUEL", "STORES")
_AIR_LOAD_MIX = {c: _TRUCK_LOAD_MIX[c] / sum(_TRUCK_LOAD_MIX[x] for x in _AIR_CARGO)
                 for c in _AIR_CARGO}


def air_supply_orders(state: GameState, side: Side) -> list[TruckOrder]:
    """[35.15]/[36.17] THE AIR-SUPPLY SHUTTLE: the first-line lorries attached to a squadron, running
    between the army's supply line and the 36.17 larder their SGSUs eat from.

    One order per line-1 formation, a two-point cycle and nothing cleverer -- this is not the forward
    relay and must not become it. The chain it feeds has exactly two ends:

      * ON A LIFTABLE DUMP and empty -> LOAD Fuel and Stores against what the larder is SHORT of,
        then deliver -- in the same order when the field is within one convoy hop, otherwise a step
        toward it.
      * AT THE FIELD holding a load -> UNLOAD it, keeping back the fuel the trip home costs (49.18
        burns cargo fuel by the hop, so a lorry that gives away its last Point strands at the
        airfield and the faucet delivers exactly once).
      * OTHERWISE -> step toward the field with a load aboard, toward the anchor without one.

    THE FIELD IT SERVES is fixed for the SIDE and not for the lorry: the neediest larder among those
    nearest a faucet, with the tie broken on stock and then on id. Read off the faucets rather than
    off the truck's own position so that it cannot move under a lorry mid-leg -- a shuttle that
    re-chose its destination every hop would walk the length of the map between two fields and
    deliver to neither. A field already holding a Game-Turn's stock drops out, so the cycle rotates
    to the next one down the coast on its own.

    Sized against the LARDER'S SHORTFALL (_air_demand), not against the truck's capacity and not
    against the 54.12 terrain ceiling: the [60.33] Axis park alone is 60 Truck Points and a Medium
    Point hauls 100 Fuel (54.2), so an unbounded load lifts thousands of Fuel Points out of the
    army's own dump to feed seven Italian squadrons that spend twenty-one a Game-Turn. The target is
    applied PER LARDER rather than per side, because 35.14's upkeep and 38.24's refuelling are both
    IN-HEX draws: a field can only feed the squadrons standing on it, so each one has to hold a
    Game-Turn of its own.

    ⚠ ONE PARK CANNOT FEED SEVENTEEN FIELDS, and this is the shape of what it does not do. The
    charts give each side ONE "Any Air Facility" row while [60.5] puts squadrons on a dozen fields
    from Benghazi to Siwa, and 35.15's attachment is per SQUADRON -- so the honest model is one first-
    line park per SGSU, which needs an attachment relation this engine has not got. What the shuttle
    therefore does is fill the fields nearest the port of arrival and rotate to the next as each
    reaches a Game-Turn's stock (a fed larder drops out of `room`). Measured on seed 4 over sixteen
    Game-Turns: the three Cyrenaican fields stand at ~1,000 Fuel Points each where all seven Axis
    fields used to stand at zero from Game-Turn 13, and AIR_REFIT_DENIED(reason='no_sgsu') falls from
    hundreds to none -- but Ft. Maddalena and Siwa, forty hexes down the coast road from any faucet,
    are still dry. The far fields wait on the attachment, not on this function."""
    orders: list[TruckOrder] = []
    larders = _air_larders(state, side)
    faucets = _air_faucets(state, side)
    if not larders or not faucets:
        return orders
    demand = _air_demand(state, side)

    def _short(dump, commodity: str) -> int:
        """How much of `commodity` this larder is short of one Game-Turn's air operations, never
        more than its 54.12 hex ceiling will take (_air_demand says why the demand and not the
        ceiling is the target)."""
        return max(0, min(_room_in(state, dump, commodity),
                          demand[commodity] - getattr(dump, commodity.lower())))

    room = [s for s in larders if any(_short(s, c) > 0 for c in _AIR_CARGO)]
    if not room:
        return orders                                    # every field is fed: the lorries stand to

    def _leg(dump) -> int:
        """How far this field is from the nearest faucet -- the length of the run to fill it."""
        return min(distance(dump.hex, f.hex) for f in faucets)

    # THE FIELD THIS SHUTTLE SERVES, and the faucet it reloads at (see the docstring: both are read
    # off the map and not off the lorry, so neither moves under it mid-leg).
    dest = min(room, key=lambda s: (_leg(s), s.fuel + s.stores, s.id))
    anchor = min(faucets, key=lambda f: (distance(f.hex, dest.hex), f.id))
    # Two or three formations share every park (one per 54.2 class), and they plan against the SAME
    # unmodified state -- so without a running ledger the second one orders a load the first has
    # already taken and the engine rejects it (measured: 38 rejections in fourteen Game-Turns, and
    # a Light formation carrying the whole run while a 50-Point Medium sat beside it).
    taken: dict = {}

    def _left(dump, commodity: str) -> int:
        return max(0, getattr(dump, commodity.lower()) - taken.get((dump.id, commodity), 0))

    def _take(dump, commodity: str, qty: int) -> None:
        taken[(dump.id, commodity)] = taken.get((dump.id, commodity), 0) + qty

    for t in state.trucks:
        if t.side != side or t.line != 1:
            continue
        free = supply.free_points(state, t)              # 32.32: haul with the lorries still free
        if free <= 0:
            continue
        t = replace(t, points=free)
        reach = supply.reachable_truck_moves(state, t)
        source = _air_source(state, side, t.hex)
        carrying = any(getattr(t, c.lower()) > 0 for c in ("AMMO", "STORES"))
        keep = supply.truck_move_fuel(t, distance(dest.hex, anchor.hex)) + supply.truck_move_fuel(
            t, supply.truck_convoy_cpa(t.truck_class))

        load: dict = {}
        if source is not None and not carrying:          # standing on the line: pick a run up
            cap = supply.truck_capacity(t.truck_class)
            for c in _AIR_CARGO:
                head = min(_short(dest, c),
                           int(_AIR_LOAD_MIX[c] * t.points * cap[c]) - getattr(t, c.lower()))
                take = min(_left(source, c), max(0, head))
                if take > 0:
                    load[c] = take
                    _take(source, c, take)
        aboard = {c: getattr(t, c.lower()) + load.get(c, 0) for c in _AIR_CARGO}
        out = 0 if dest.hex == t.hex else supply.truck_move_fuel(t, reach.get(dest.hex, 0.0))

        if dest.hex == t.hex or (dest.hex in reach and aboard["FUEL"] >= out):
            unload = {"STORES": min(aboard["STORES"], _short(dest, "STORES")),
                      "FUEL": min(max(0, aboard["FUEL"] - out - keep), _short(dest, "FUEL"))}
            unload = {c: q for c, q in unload.items() if q > 0}
            if unload:
                orders.append(TruckOrder(t.id, load_from=source.id if load else None,
                                         load=load or None,
                                         to=None if dest.hex == t.hex else dest.hex,
                                         unload_to=dest.id, unload=unload))
                continue

        # Nothing lands from here: close the gap -- toward the field with a load aboard, toward the
        # anchor without one.
        target = dest.hex if (carrying or load) else anchor.hex
        step = _step_toward(reach, t.hex, target)
        if step is None:
            continue
        cost = supply.truck_move_fuel(t, reach[step])
        if aboard["FUEL"] < cost and not load:
            # ⚠ THE BOOTSTRAP, AND IT IS THE ONE PLACE THIS SHUTTLE TOUCHES THE LARDER IT FEEDS.
            # A [60.33]/[60.43] park is seeded DRY, standing at an airfield with no army dump under
            # it, so on Game-Turn 1 it cannot make the first hop to the port at all and the faucet
            # would never open. 35.15 attaches these lorries TO THE SQUADRON and 36.17 says what the
            # squadron's dump is for -- "any SGSU at an airfield may make use of the supplies there"
            # -- so the field's own Fuel Points are what puts its transport on the road. Taken ONLY
            # as movement fuel (never as cargo: it is unloaded back into an air dump, so lifting it
            # as freight would be a lorry pushing a pile round in a circle), only enough for the leg
            # in hand, and only when there is nothing else in the hex to take it from.
            here = next((s for s in state.supplies if s.side == side and not s.is_dummy
                         and s.hex == t.hex and _left(s, "FUEL") > 0), None)
            if here is None:
                continue
            take = min(_left(here, "FUEL"), cost + keep - t.fuel)
            if take <= 0:
                continue
            _take(here, "FUEL", take)
            load = {"FUEL": take}
            source = here
            aboard["FUEL"] = t.fuel + take
        if aboard["FUEL"] >= cost:
            orders.append(TruckOrder(t.id, load_from=source.id if load else None,
                                     load=load or None, to=step))
    return orders


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
    #
    # [36.17] THE AIR-FACILITY DUMPS GO WITH THEM, and for a sharper version of the same reason. An
    # airfield's pile is "a supply dump for supplies to be used by the SGSU's on that airfield", and
    # "land units may not use airfield supply dumps"; it is the squadron's larder, filled by the
    # [60.33]/[60.43] "Any Air Facility" lorries that sit on it (35.15). Left visible, the relay
    # would read it as an ordinary forward depot -- pouring the army's freight into a pile no unit
    # of the army may eat from, and (once constructed) lifting the squadron's own stores back out.
    # Measured: a Commonwealth air dump landed on a railway station and MASKED it from the lorries.
    state = replace(state, supplies=tuple(s for s in state.supplies
                                          if not wells.is_water_source(s) and not s.air_dump))
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
        if t.side != side or t.line == 1:
            continue                                     # 35.15: a squadron's own transport is not
                                                         # the army's freight (air_supply_orders)
        # [32.32] THE RELAY HAULS WITH THE LORRIES IT STILL HAS. A formation with Truck Points booked
        # under a desert column (supply.free_points) is a SMALLER convoy: it may lift less (53.12)
        # and it burns less getting there (49.18). Plan against the freed-up remainder, exactly as
        # engine._truck_order validates against it -- a relay that budgeted its full strength would
        # order lifts the engine then rejects, and the freight would simply stop. Fully committed ->
        # no convoy at all this OpStage; those lorries are carrying a depot.
        free = supply.free_points(state, t)
        if free <= 0:
            continue
        t = replace(t, points=free)
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
            load = _load_mix(t, colocated)
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
