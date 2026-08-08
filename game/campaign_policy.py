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

from collections import defaultdict
from dataclasses import dataclass, replace

from . import (campaign_claim, construction, malta, organization, rail, stacking, supply, tactics,
               wells)
from .campaign_claim import (STAGING, garrison_units,   # the rule-64.73 standing orders, re-exported
                             hold_depots, hold_garrisons)   # (game.campaign_staff and the tests import them from here)
from .events import Control, Side
from .hexmap import Coord, distance
from .policy import (AttackOrder, BuildOrder, CoastalShipOrder, DemolitionOrder, MotorizeOrder,
                     MoveOrder, OrganizationOrder, RailActivateOrder, RailHaulOrder,
                     ScriptedPolicy, SupplyMoveOrder, TruckOrder)
from .state import GameState, SupplyUnit
from .relay import (  # extracted to game.relay; re-exported so every caller and __all__ keep working
    _step_toward, _relay_source, _is_faucet, _a_link_in_the_chain, _field_dump_id,
    _forward_depot_sites, build_the_chain, _room_in, _lands_anything, _fit_to_dest,
    _load_mix, air_supply_orders, campaign_truck_orders)

__all__ = ["CAMPAIGN_CW_OFFENSIVES", "CampaignAxisPolicy", "CampaignCommonwealthPolicy",
           "OffensiveSchedule", "air_supply_orders", "build_the_chain", "campaign_motorization",
           "campaign_truck_orders", "concentrate_formations", "deny_dumps", "formation_moves",
           "garrison_units",
           "hold_depots", "hold_garrisons", "keep_in_trace", "railhead", "take_and_hold_moves",
           "take_and_hold_supply"]


def concentrate_formations(state: GameState, side: Side) -> list[OrganizationOrder]:
    """[19.4]/[19.12] THE REORGANIZATION SEGMENT STANDING ORDER that makes the seeded [4.45]
    formation tree actually FIGHT as formations -- the driver Gate 7A found missing, without which
    the [15.53] Organization Size chart could never leave its lone-battalion tier in 111 turns.

    Two acts, both the book's, both re-validated at the engine boundary (engine._reorganize):

      * ATTACH (19.4/19.41) every ASSIGNED unit that stands in its Parent Formation's hex. "Any
        units assigned to a particular Parent Formation may freely be attached to or detached from
        that Parent Formation" -- so this is the no-cost homecoming of a unit to the formation it
        belongs to (19.28's paper assignment made concrete on the map), not the [19.5]-capped
        attachment of a stranger. Once attached, the formation's units resolve at its Organization
        Size in close assault (organization.combat_size), and its counter carries them as one when
        it advances (organization.co_located_subtree) -- so a division fights, and moves, as a division.

      * DETACH (19.43) any unit a link still binds to a Parent it no longer stands with. Voluntary
        movement keeps a formation together (the carry above), but a retreat or a Reaction can
        split one, and 19.12 attachment is a SAME-HEX relationship; a stale link is reconciled here,
        in the one Segment the rule lets it be. This is not the gratuitous break-up of a historical
        formation -- it keeps the map tree honest to where the counters actually stand.

    THE STACKING GATE (9.14/9.31). Attaching is normally free of stacking cost -- a subsidiary folds
    to zero inside its Parent's counter (9.13) -- but the FIRST unit under a large HQ makes that HQ
    jump from a bare 0 (9.12) to its full formation value, which can push a hex over its limit. So a
    formation concentrates only where the resulting stack is legal; the rest of its units come in as
    room is made. The engine re-checks the limit at rest regardless (invariants), this only keeps the
    staff from ordering an attach the board cannot hold.

    UNDER ANY PARENT A UNIT IS ASSIGNED TO -- combat counter or bare HQ (2026-08-04). (This heading
    read "ANY PARENT THE CHART NAMES" until the faithfulness review pointed out that the attach loop
    below tests only side, alive and co-location -- it never asks organization.formation(org_type),
    so it does not in fact confine itself to Parents the [19.3] chart names. Harmless today: measured,
    zero Parents with assigned children lack a [19.3] row, and zero lack a [19.5] row at Game-Turns
    1/13/68/75. But the engine, not this proposer, is what would catch a future OOB pass that seeded
    `assigned_to` at a chartless counter -- organization.may_attach rejects it -- and a heading should
    not describe a guard that lives somewhere else.) This used to be
    confined to formations whose Parent is itself a COMBAT counter, and that gate was a WORKAROUND
    FOR A MISSING DRIVER, flagged here as "an engine limitation, not a rule": in the game a division
    is one counter and its HQ moves WITH it, while in this engine an HQ is a separate counter, and no
    proposer ever ordered a bare, non-combat one. Fold a formation into such an HQ and its units --
    which may no longer self-move once attached (19.12, engine._movement) -- were FROZEN where they
    stood, because nothing could order the HQ to lead them. Measured, and it killed the faucet: the
    Eighth Army's Delta brigades concentrated and never reached the railhead.

    THE DRIVER IS BUILT AND THE GATE IS GONE: formation_moves below orders a Parent counter that
    carries a subtree, at the destination the army's own proposer gave its strongest carried combat
    child, and both campaign policies compose it into movement(). A concentrated formation MARCHES.
    Nothing about the attach half changed -- 19.4/19.41 was never the thing that was wrong.

    WHAT THE GATE COST, MEASURED on scenario.campaign(1) before it was dropped: of 91 Parent
    Formations with assigned children, 15 concentrated and 76 were refused, freezing 318 children --
    and 61 of the 76 were COMMONWEALTH (37 infantry brigades, 13 infantry divisions, 3
    super-brigades, 6 armour formations, 2 allied brigades) against 8 German (4 division HQs, 2
    armored regiments, 288 Son and the Ramcke Brigade) and 7 Italian. (Both parenthetical
    breakdowns were CORRECTED 2026-08-04: they read "5 armour" and "5 division HQs", so the
    Commonwealth cells summed to 60 against a stated 61 and the German cells to 7 against a stated
    8. In a repo where docstrings are the audit record, a census whose cells do not sum is a
    defect.) So [15.53] Organization Size bit for the AXIS through its
    Italian binary divisions and for almost nobody else -- the reverse of the historical picture,
    with the DAK's own panzer regiments unable to concentrate. Both tiers are now open to both
    sides, on the same rule.

    Pure setup-tree play: no Kampfgruppe is formed here (that is the speculative 19.71 act, flagged
    and deferred). Returns [] when no unit carries the tree, so any policy that inherits this on a
    tree-less scenario is byte-identical."""
    by_id = {u.id: u for u in state.units}
    living = list(state.living(side))
    orders: list[OrganizationOrder] = []

    # DETACH the stale links first (a formation split by a retreat/Reaction; 19.43 in-Segment).
    for u in living:
        if u.attached_to:
            p = by_id.get(u.attached_to)
            if p is None or not p.alive or tuple(p.hex) != tuple(u.hex):
                orders.append(OrganizationOrder("detach", unit_id=u.id, parent_id=u.attached_to))

    # ATTACH each assigned unit co-located with its Parent, per formation, gated on 9.14.
    kids: dict[str, list] = defaultdict(list)
    for u in living:
        if not u.assigned_to or u.attached_to:
            continue
        p = by_id.get(u.assigned_to)
        if p is not None and p.side == side and p.alive and tuple(p.hex) == tuple(u.hex):
            kids[p.id].append(u)

    work = {u.id: u for u in state.units}                 # tracks this Segment's attaches so several
    for pid in sorted(kids):                              # formations sharing a hex compose correctly
        children = sorted(kids[pid], key=lambda u: u.id)
        parent = by_id[pid]
        terrain = state.terrain.terrain[tuple(parent.hex)]
        cset = {c.id for c in children}
        stack = [replace(work[x.id], attached_to=pid) if x.id in cset else work[x.id]
                 for x in state.units_at(parent.hex)]
        if not stacking.within_hex_limit(stack, terrain):
            continue                                      # 9.14: not enough room to fold them in yet
        for c in children:
            orders.append(OrganizationOrder("attach", unit_id=c.id, parent_id=pid))
            work[c.id] = replace(work[c.id], attached_to=pid)
    return orders


def formation_moves(state: GameState, side: Side,
                    ordered: list[MoveOrder]) -> list[MoveOrder]:
    """[19.12] THE PARENT COUNTER MARCHES ITS FORMATION -- the driver without which concentrating
    a formation FREEZES it, and the reason concentrate_formations above no longer has to refuse.

    An attached subsidiary may not self-move: "both the attached unit and the Parent Formation are
    in the same hex... functionally combined into one unit", and engine._movement drops a
    subsidiary's own order accordingly. The formation moves when its PARENT's counter moves, which
    carries the whole co-located subtree at no Capability Point and no Fuel. So somebody has to
    order the Parent -- and until this function existed nobody ever did, because every proposer in
    this repo skips a non-combat unit and every Commonwealth brigade/division HQ and every German
    division and panzer-regiment HQ is exactly that.

    IT RIDES ALONGSIDE, ON THE `_railway` PRECEDENT, and it keeps that proposer's invariant by
    reading it rather than by assuming it: `ordered` is every move order the side has already made
    this Segment, and a Parent that appears in it is left alone. NO UNIT IS ORDERED TWICE. A COMBAT
    Parent is skipped outright -- the army proposer already had its say about that counter, and the
    fifteen combat Parents on the campaign board keep behaving exactly as they did.

    *** THE DOCTRINE, AND IT IS INHERITED RATHER THAN AUTHORED (flagged: this is the one judgement
    call in the slice). *** Where should a division HQ go? That is a commander's question, and this
    project's answer to commanders' questions is that they belong to the staff, not to a scripted
    reflex. So no HQ doctrine is invented here. The Parent REPRESENTS its children (19.12), so it
    is given THE DESTINATION THE EXISTING PROPOSER ALREADY CHOSE FOR THE STRONGEST COMBAT UNIT IT
    CARRIES -- the formation's main body. Whatever the army was doing, the formation keeps doing:
    the Commonwealth's forward concentration on the railhead, the Axis drive on Alexandria, the
    rule-64.73 take-and-hold, and the standing garrison order. The alternative default -- "the
    Parent follows the army it belongs to" -- would have been a second, weaker copy of doctrine
    that already exists.

    *** THE STANDING ORDERS ARE A VETO, AND THAT SENTENCE IS LOAD-BEARING (repaired 2026-08-04
    after both adversarial reviews found the same defect, independently, each with its own A/B).
    This docstring used to claim the garrison case worked by itself -- "a child held on its city
    proposes no move, so its formation stands with it" -- and it was FLATLY WRONG. hold_garrisons
    and delta_garrison hold a unit by DELETING its move order, so a pinned child looks exactly like
    a child the army had no plans for, and the strength-ordered fallback below stepped over it and
    took a sibling's destination. The [19.12] carry then marched the garrison off its hex at zero
    Capability Points. A formation carrying ANY pinned unit is now skipped outright. ***

    TWO GATES, BOTH THE ENGINE'S OWN, so the proposer rarely orders a rejection (the discipline
    _march keeps: "don't propose a reject" -- and note RARELY, not never: this pre-tests [6.15] and
    [9.14], but engine._movement's chain has six more gates a bare HQ can fail, and measured on
    campaign(1) over 12 Game-Turns the non-combat ORDER_REJECTED count goes 0 -> 36, every one of
    them "out of supply: no fuel for this move". That is faithful behaviour, not a defect; the
    earlier wording of this sentence simply overstated the guarantee):
      * [6.15] the destination must lie within the FORMATION's reach, which is bound to the lowest
        CPA among its components (tactics.formation_cpa) -- and the strongest child's own order was
        computed at ITS CPA, which may be far higher than the formation's;
      * [9.14] the resulting stack at the destination must be legal, tested on the formation's whole
        footprint exactly as engine._movement tests it (a Parent jumps from a bare 0 to its full
        Organization value the moment it carries anybody, 9.12).
    When the strongest child's destination fails either, the next strongest is tried. That is not a
    new heuristic: every candidate is a destination the existing doctrine chose for a member of this
    formation, and without the fallback one fast battalion in a slow brigade would freeze it -- the
    very failure this driver exists to end.

    Returns [] for any counter carrying nothing, so a scenario with no live organization tree (both
    Desert Fox benchmarks) proposes nothing and stays byte-identical."""
    index = organization.attached_index(state)
    dest = {o.unit_id: tuple(o.to) for o in ordered}
    roster = state.living(side)
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
    # [64.71]/[64.73] THE STANDING ORDERS BIND THE FORMATION, NOT ONLY THE COUNTER THEY NAME.
    # Both standing orders are implemented as order-DROPPING transforms (campaign_claim.
    # hold_garrisons, delta_garrison): the way a garrison is held is that its move order is
    # deleted. So a pinned child is INDISTINGUISHABLE from a child the army simply had no plans
    # for, and the fallback below would step over it and take a sibling's destination -- after
    # which engine._movement's [19.12] carry walks the garrison off its hex at zero Capability
    # Points, with no rejection and no event anyone would look at. Measured before this guard on
    # campaign(seed=1): Polish-Bde-I carried off Delta hex (43,141) three times in three
    # Game-Turns, and Delta hex occupancy over a 12-turn fold fell to 8 stages in 36.
    # ABSTENTION IS A VETO HERE, because delta_garrison's contract is absolute: "the one unit
    # standing on each of them never marches away. Ever." [64.71] is the AUTO-WIN condition.
    pinned = campaign_claim.garrison_units(state, side) | campaign_claim.delta_garrison(state, side)
    orders: list[MoveOrder] = []
    for p in roster:
        if p.is_combat or p.attached_to or p.id in dest or p.id not in index:
            continue                       # the army's counters, a subsidiary, and anything another
                                           # proposer already ordered, are not this proposer's
        carried = organization.co_located_subtree(state, p, index)
        if not carried:
            continue                       # a bare HQ carrying nothing is nobody's formation
        if any(c.id in pinned for c in carried):
            continue                       # 64.71/64.73: a formation holding a pinned garrison stays
        reach = tactics.reachable_for(state, p, enemy_zoc, enemy_occupied, roster,
                                      formation=carried)              # 6.15
        for child in sorted(carried, key=lambda u: (-u.effective_strength, u.id)):
            to = dest.get(child.id)
            if to is None or to == tuple(p.hex) or to not in reach:
                continue
            present = [x for x in state.units_at(to) if x.side == side]
            if not stacking.within_hex_limit(present + [p] + carried,
                                             state.terrain.terrain[to]):     # 9.14
                continue
            orders.append(MoveOrder(p.id, to))
            break
    return orders


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


def _still_following(view: GameState, side: Side, dump: SupplyUnit) -> bool:
    """Has this depot still got an army IN FRONT of it -- somewhere forward to be carried to?

    THE STABLE TEST, and it has to be stable or 32.32 eats the campaign. The Organization Phase
    commits the lorries BEFORE the army moves (32.32), but the depot is carried AFTER it
    (engine._supply_movement), so the quartermaster's reach-based leapfrog names a DIFFERENT set of
    depots at the two moments -- an OpStage's ZOC and the front's exact hex both shift under it. A
    column stood down on that flicker is a column that is not there when the depot needs it:
    MEASURED (seed 7, before this test existed), the Eighth Army's depots were REFUSED a move 71
    times against 63 granted, its offensives died, and three of five seeds froze at the identical
    445-20 -- the signature of a campaign in which nothing changes hands. That was never rule
    32.32's thirty Truck Points doing the damage; it was standing the column down and raising it
    again every OpStage, which is a per-hex toll and precisely what the rule is NOT.

    So: distance to the objective, no reach, no ZOC. The army only ever gets closer to its
    objective, so a depot behind it stays behind it, and a column raised for it STANDS -- which is
    what 32.32 says a Motorization Point assignment is.

    `view` is the POLICY'S OWN view, not the raw state, and that matters: off its offensive windows
    the Commonwealth plans its supply against the RAILHEAD (_forward_view), not against Benghazi, so
    a persistence test run on the raw objective would pin a column to every rear depot in Egypt for
    the whole war -- measured, 92% of the Eighth Army's Medium park under depots that were never
    going anywhere. The test has to ask the question the quartermaster actually asked."""
    obj = view.objective_for(side)
    here = distance(dump.hex, obj)
    return any(distance(u.hex, obj) < here for u in view.living(side) if u.is_combat)


def campaign_motorization(state: GameState, side: Side, wish: list[SupplyMoveOrder],
                          view: GameState | None = None) -> list[MotorizeOrder]:
    """[32.32] THE DECISION THE DESERT WAR IS ACTUALLY ABOUT: which depots get the lorries.

    "THIRTY Motorization Points are required to transport one real supply unit", and by 32.51 a
    Motorization Point IS a Medium Truck Point -- so every depot this staff pushes forward is thirty
    Medium Truck Points lifted OUT of the freight relay that is hauling the army's fuel and
    ammunition to the front. The park is finite and charted (60.33: the Axis fields 150 Medium Points
    on-map, four columns and a bit; 60.43: the Commonwealth 130, four), so the pool RUNS DRY, and
    when it does the rest of the quartermaster's list simply does not move. That is the whole point.
    Free, a depot outran the infantry it fed (15 CP an OpStage) and the desert filled with them.

    A STANDING RESERVATION (32.32: attached AND detached only in the Organization Phase; 32.56 "the
    unit they are ASSIGNED to"), so the assignment is rebuilt each Organization Phase against a
    PRIORITY LIST and then LEFT ALONE:

      1. the depots the quartermaster names this OpStage, in take_and_hold_supply's own order --
         the ones marching with a garrison to a rule-64.73 city first (a depot is the only thing
         that makes a city BANKABLE), the ordinary forward leapfrog after;
      2. then every depot already under a column that still has an army in front of it to follow
         (_still_following) -- so a column STANDS across the OpStages instead of being raised and
         stood down every beat, which is a per-hex toll and not this rule.

    The park's own limit cuts that list off (130 Medium Points buy the Commonwealth four columns and
    no more), and a depot below the cut loses its lorries to the depot above it -- which is exactly
    the contested pool the rule creates. The engine re-validates all of it (engine._organization /
    supply.column_legs); the arithmetic here only keeps the staff from ordering columns it cannot pay
    for. Inert unless the rule is live (state.motorized_supply)."""
    if not state.motorized_supply:
        return []
    view = state if view is None else view
    mediums = sorted((t for t in state.trucks
                      if t.side == side and t.truck_class == supply.MOTORIZATION_CLASS),
                     key=lambda t: t.id)
    cap = sum(t.points for t in mediums) // supply.MOTORIZATION_POINTS   # columns the park can raise

    named = {o.supply_id for o in wish}
    ranked: list[str] = []
    for sid in [o.supply_id for o in wish] + sorted(state.motorization):
        dump = state.supply(sid)
        if sid in ranked or dump is None or dump.side != side:
            continue
        if dump.empty or dump.base or dump.is_dummy:         # nothing carriable here
            continue
        if sid not in named and not _still_following(view, side, dump):
            continue                                         # arrived: the column has done its job
        ranked.append(sid)
    keep = ranked[:cap]

    orders: list[MotorizeOrder] = []
    free = {t.id: supply.free_points(state, t) for t in mediums}
    for sid, legs in sorted(state.motorization.items()):      # stand down what fell below the cut
        if sid in keep or not any(t and t.side == side
                                  for t in (state.truck(tid) for tid, _ in legs)):
            continue
        orders.append(MotorizeOrder(sid, ()))
        for tid, pts in legs:
            if tid in free:
                free[tid] += pts                             # the lorries come back to the pool

    for sid in keep:                                         # fund the list until the park is dry
        if sid in state.motorization:
            continue                                         # already has its thirty -- it STANDS
        pick, need = [], supply.MOTORIZATION_POINTS
        # THE SLACKEST FORMATION FIRST -- mirrors supply.column_legs exactly (which re-sorts the ids
        # it is handed), so the staff's arithmetic and the engine's draw can never disagree. Taking
        # the last twenty Points from a twenty-Point lorry group deletes it from the relay entirely.
        for t in sorted(mediums, key=lambda t: (-free[t.id], t.id)):
            take = min(need, free[t.id])
            if take > 0:
                pick.append((t.id, take))
                need -= take
            if need == 0:
                break
        if need > 0:
            break                                            # 32.32: the park is dry -- no more columns
        for tid, take in pick:
            free[tid] -= take
        orders.append(MotorizeOrder(sid, tuple(tid for tid, _ in pick)))
    return orders


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

    def organization(self, state: GameState, side: Side) -> list[OrganizationOrder]:
        # [19.4]/[19.12] Concentrate the seeded [4.45] formation tree so the Eighth Army's divisions
        # fight as divisions -- the [15.53] Organization Size chart the Commonwealth needs to stand
        # against the DAK's concentration (see concentrate_formations).
        return concentrate_formations(state, side)

    def air_missions(self, state: GameState, side: Side) -> list:
        # [39.1] The SAME Air Marshal doctrine the campaign Axis flies, and it is symmetric because
        # the rule and the target are: there is one Tobruk harbour, both sides task it every
        # Game-Turn, and _air_port hands the besieger's role back and forth as the fortress changes
        # hands (scenario._campaign_air_missions). Malta's raid is the Axis Player's alone; the LAND
        # mission column is not.
        return air_mission_doctrine(state, side)

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
        #
        # [19.12] AND SO DOES THE FORMATION PROPOSER, on the same precedent -- but it reads the
        # orders already made instead of assuming the invariant, because a Parent counter IS a
        # non-combat unit and the railway gang is the one other proposer that names those. It marches
        # each concentrated formation where the army was already sending its main body; without it a
        # brigade that folds into its own HQ can never move again (see formation_moves).
        plan = self._railway(state, side) + take_and_hold_moves(state, side, army,
                                                                escort=self._escort(state))
        return plan + formation_moves(state, side, plan)

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
        # 36.17: an air-facility dump is no spring for a land column -- it may not draw a point from
        # it when it arrives, so marching at one is marching at nothing (the same exclusion _bridge,
        # the leapfrog and keep_in_trace make).
        wet = [s for s in state.supplies
               if s.side == side and not s.air_dump and s.water > 0]
        fuelled = [s for s in state.supplies
                   if s.side == side and not s.is_dummy and not s.air_dump and s.fuel > 0]
        orders: list[MoveOrder] = []
        for u in rear:
            if supply.in_hex_draw(state, u, supply.FUEL, supply.fuel_cost(u, 1)) is None:
                continue          # out of fuel -- every move pays (49.13, IN HEX); don't propose a reject
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
                     and self._stacking_ok(state, u, c)
                     and tactics.husbands_cohesion(state, u, reach[c])]  # 6.21/15.88: don't dash to surrender
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

    def motorization(self, state: GameState, side: Side) -> list[MotorizeOrder]:
        # [32.32] The Eighth Army pays for its own desert columns out of the same 60.43 park that
        # hauls its freight up from the Delta -- the identical charge the Panzerarmee now pays.
        # This is the rule that made Compass a matter of "spending weeks lorrying dumps forward
        # into the desert first, and THEN attacking out of them" (60.34): the lorries doing the
        # first half are not doing the second.
        #
        # The view is the one supply_orders itself planned against (the railhead off-window, the
        # objective on it), so a column is only held for a depot THIS policy is actually marching.
        view = _without_staging(state if self._on_offensive(state)
                                else self._forward_view(state))
        return campaign_motorization(state, side, self.supply_orders(state, side), view=view)

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
                           and supply.in_hex_draw(state, u, supply.FUEL,
                                                  supply.fuel_cost(u, 1)) is None),
                          key=lambda u: (distance(u.hex, target), u.id))
        if not stranded:
            return []
        orders: list[SupplyMoveOrder] = []
        claimed: set = set()
        for su in state.active_supplies(side):
            if (su.base or su.air_dump or su.fuel < supply.SUPPLY_MOVE_FUEL
                    or state.port_at(su.hex) is not None):
                continue          # a rule-57 base is immobile; an airfield's larder stays on its
                                  # airfield (36.17); a dry dump cannot move (32.24); a harbour dump
                                  # stays where the convoys land (55)
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
        # PLUS 35.15's air-supply shuttle (see ScriptedPolicy.truck_orders): the [60.43] "Any Air
        # Facility" park is a squadron's own transport, not the Eighth Army's freight.
        return campaign_truck_orders(state, side) + air_supply_orders(state, side)

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


def _can_trace(state: GameState, u) -> bool:
    """A POLICY's cheap supply sanity-check, asked of a unit anywhere: can it draw both Fuel (its
    per-model rate -- FOOT infantry burns none at all, 49.12) and Ammunition off a dump inside the
    32.16 cpa/2 trace?

    IT IS NOT THE RULE-64.73 TEST AND THIS DOCSTRING USED TO SAY IT WAS ("the same question
    game.campaign_victory._supplied asks"). It never was: 64.73 asks for 20 CP of Fuel and THREE
    firings where this asks one turn's bare rate and ONE firing. Since 64.73's test moved in-hex and
    grew its Stores/Water week (campaign_victory._supplied), the two are not even the same SHAPE --
    this one still walks the abstract 32.16 trace, which rule 3 of this port says does not apply.
    Left as it stands rather than quietly re-pointed: it is a heuristic inside a scripted policy, its
    magnitudes are its own, and changing what a policy proposes is a behaviour change that belongs in
    a measured slice of its own. FLAGGED as debt here so the next reader is not misled twice."""
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


def keep_in_trace(orders: list, state: GameState, side: Side) -> list:
    """[54.16]/[32.16] DO NOT OUTRUN YOUR SUPPLY -- the consolidation constraint, as a transform on an
    army's move orders, in the same idiom as hold_garrisons.

    WIRED AT LAST, and only because rule 32.33 and rule 24 arrived to pay for it. FOUR earlier
    measurements rejected it and the log of them is kept below, because the thing that finally made it
    shippable is exactly the thing every one of those measurements said was missing.

    IT IS LAID OVER THE GENERAL ADVANCE ALONE (take_and_hold_moves), and that is the whole design.
    The standing orders' DETACHMENTS are not filtered by it, because each of them has already
    answered the same question in a better-informed way: a city claim is only made where the unit
    could be FED (campaign_claim.can_be_fed -- the PLANNER's reach question over the 32.16 line,
    asked of the destination; this line called it "rule 64.73's own trace test" until 2026-08-02 and
    that is false twice over, because 64.73 asks for a Week of Stores and Water too and because since
    campaign_victory._supplied moved in-hex the rule has no trace at all -- see _can_trace below),
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
              and not s.air_dump                     # 36.17: the squadron's larder, not the army's
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
        # ...and 35.15's air-supply shuttle beside it (see ScriptedPolicy.truck_orders): the [60.33]
        # "Any Air Facility" park keeps the Regia Aeronautica's 36.17 larder full, and it is the only
        # thing on the map that can.
        return campaign_truck_orders(state, side) + air_supply_orders(state, side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        return super().supply_orders(_without_staging(state), side)

    def motorization(self, state: GameState, side: Side) -> list[MotorizeOrder]:
        # [32.32] Pay for the desert column, out of the same park that hauls the freight. The wish
        # is this policy's OWN supply_orders -- whatever it means to march, in its own priority
        # order -- so the two halves of the rule can never disagree about which depot is going where,
        # and the view is the one it planned against (the staging chain hidden, _without_staging).
        return campaign_motorization(state, side, self.supply_orders(state, side),
                                     view=_without_staging(state))


# ⚠ THE ONE CONSTANT LEFT IN THE 56.22 DECISION, and it is the policy's, not the book's: the share
# of a sailing no commodity is ever allotted less than. See convoy_plan_doctrine's flag (a).
_CONVOY_FLOOR_SHARE = 0.10


def convoy_plan_doctrine(state: GameState, side: Side, tons: int) -> dict:
    """[56.22] THE AXIS QUARTERMASTER'S CONVOY DECISION: ship what the army in Africa is SHORT OF.

    56.22 gives the Axis Player free choice of what to load into the tonnage the charts allow him,
    and calls the three commodities unlimited in Europe. So the only thing that can inform the
    choice is the state of his own dumps -- which is exactly what a quartermaster planning next
    week's convoy looks at, and exactly what the constant this replaces (invention I11's fixed
    60/25/15) could not see.

    Deliberately NOT a calendar. The thing Phase 5 exists to delete is a hand-typed month table;
    a doctrine that shipped ammunition in November because Crusader opened in November would be the
    same mistake wearing a different hat.

    THE COMMON UNIT IS THE BOOK'S OWN. Fuel, Ammunition and Stores Points are not comparable to each
    other -- one Ammunition Point weighs 4 tons and one Fuel Point an eighth of a ton (54.5) -- so
    the stocks are converted to TONNAGE on the [54.5] Equivalent Weight Chart before they are
    compared, which is the same chart the convoy's own allowance is denominated in. No rate, no
    weighting and no constant of ours enters the comparison.

    Each commodity's share of the sailing is then proportional to the tonnage of the OTHER two
    already ashore: a commodity the army is out of is the one every other commodity's abundance
    votes for. Three equal larders split the convoy in three; an army with no ammunition ships
    ammunition.

    ONLY A FINITE LARDER MAY VOTE (`_is_faucet`), AND THIS WAS MEASURED COSTING THE AXIS HIS BREAD.
    A [52.3] oasis is seeded as an endless Stores dump (wells.UNLIMITED_WELL, 125,000,000 Points);
    Siwa, Jalo and Giarabub put 375,000,000 Stores Points -- 375 MILLION TONS on the [54.5] chart --
    on the Axis books, which swamped every real quantity in the comparison so completely that the
    doctrine's output was bit-identical across two campaigns that differed in every battle: 45.02%
    fuel / 44.97% ammunition / 10.01% stores, the flagged floor, every sailing for a hundred and
    eleven Game-Turns (scratchpad/port/faucet-audit.md, stage 1b). The Axis shipped nine times his
    lifetime fuel need and a fifth of his food, and better than half of all his unit-Game-Turns were
    spent with no stores at all. A bottomless source is GEOGRAPHY, not a larder: an oasis feeds the
    unit standing on it (52.3, drawn in-hex) and the army five hundred kilometres away cannot eat
    Siwa's dates. So the same test the haulage layer already applies -- relay._is_faucet, "a
    bottomless source cannot be strip-mined because it cannot be emptied" -- is applied here, and
    only stock somebody could actually run out of informs the decision.

    ⚠ FLAGGED, AND THEY ARE THE ONLY TWO NUMBERS HERE. (a) The FLOOR: no commodity is allotted less
    than a tenth of the tonnage, because a convoy that starves one commodity outright for a month is
    a decision no quartermaster makes and one this engine's dumps cannot recover from (51.0 makes
    Stores a per-Game-Turn upkeep with no organic pool to ride out a gap on). (b) An army holding
    NOTHING has no proportions to reason from and splits the sailing evenly. Neither is in the book;
    both are the policy's, which is where 56.22 puts this decision."""
    stock = {c: 0 for c in supply.CONVOY_COMMODITIES}
    for su in state.supplies:
        if su.side == side and not su.is_dummy and not _is_faucet(su, None):
            for c in stock:
                stock[c] += getattr(su, c.lower())
    for t in state.trucks:
        if t.side == side:
            for c in stock:
                stock[c] += getattr(t, c.lower())
    ashore = {c: supply.points_to_tons(stock[c], c) for c in stock}   # 54.5: the common unit
    total = sum(ashore.values())
    if total <= 0:                                       # nothing ashore to reason from (flag b)
        return {c: tons / len(stock) for c in stock}
    weight = {c: total - ashore[c] for c in ashore}      # what the OTHER larders vote for
    floor = tons * _CONVOY_FLOOR_SHARE                   # the flagged tenth (flag a)
    span = sum(weight.values()) or 1.0
    rest = tons - floor * len(weight)                    # every commodity gets its floor FIRST,
    return {c: floor + rest * w / span for c, w in weight.items()}   # then the rest by the vote


def _friendly_dump_at(state: GameState, side: Side, hex_: Coord) -> "SupplyUnit | None":
    """The one non-water-source friendly dump standing on `hex_` -- a port's own built-in depot
    (56.28), read the same way engine._ship_load/_ship_unload read it."""
    return next((s for s in state.supplies if s.side == side and s.hex == hex_
                and not wells.is_water_source(s)), None)


def _port_stock_tons(state: GameState, side: Side, port) -> float:
    """A port's on-hand stock, in the ONE common unit (54.5 tonnage) convoy_plan_doctrine already
    compares commodities in -- so "richest"/"poorest" below means the same thing that doctrine's
    "what the army is short of" means."""
    dump = _friendly_dump_at(state, side, port.hex)
    if dump is None:
        return 0.0
    return sum(supply.points_to_tons(getattr(dump, c.lower()), c) for c in supply.CONVOY_COMMODITIES)


def axis_rail_doctrine(state: GameState, side: Side) -> list:
    """[54.4] What the Axis does with a captured stretch of the Commonwealth railroad.

    *** FLAGGED AS AN OPINION A COMMANDER MAY HOLD, NOT A LAW OF THE WORLD. *** The book supplies no
    doctrine here at all -- 54.43 says what Rolling Stock COSTS and what it BUYS, never when a
    commander should want one. Same standing as convoy_plan_doctrine and coastal_shipping_doctrine,
    and the same open question the minefields (rule 26) and the Tobruk relay staging already raise:
    the real answer is a staff officer's, and belongs to Gate C rather than to a heuristic here.

    The opinion taken: BUY ONE LOCOMOTIVE, AND ONLY ONE. 54.41's gate opens for roughly half the
    campaign but the Axis holds the line only in the middle of it -- measured, he ends every seed
    with zero controlled rail hexes -- and 54.45 destroys the whole stock the moment the gate shuts,
    with no refund. A second locomotive doubles the haul and doubles what the Eighth Army burns when
    it comes back; one is the cautious buy, and caution is what a quartermaster who has read 54.45
    would feel. Then haul the fullest single commodity FORWARD -- from the westmost controlled rail
    dump to the eastmost -- which is the direction the DAK's supply problem actually runs.

    Nothing here tries to make 54.4 look valuable. If one locomotive's 300 tons an Operations Stage
    turns out not to matter, that is the measurement, and it is reported rather than tuned away."""
    if side is not Side.AXIS or not rail.usable_this_stage(state):
        return []
    # ONE RUN AT A TIME (54.41/54.43). A locomotive is activated on, and a train runs inside, ONE
    # contiguous block of five-or-more controlled rail hexes -- so the doctrine picks its dumps
    # within a single activated run rather than off the controlled set at large, which could pair
    # a dump in Cyrenaica with one in Egypt and have the engine reject it every Operations Stage.
    runs = rail.activated_runs(state)
    # THE DEPOTS THAT COUNT, read exactly as engine._dump_on reads them for the Commonwealth's own
    # rail lane. A WELL or pipeline hex is geography and not a freight depot (52.11/52.3), and no
    # lorry or ship may ever load out of one (engine._truck_load / _ship_load refuse it), so freight
    # railed there is freight parked for good -- measured, seed 4 railed 2,400 Fuel and 42 Ammo into
    # AX-Well-ElDaba and the war ended with all of it still on the platform. An AIR-facility dump
    # (36.17) is skipped from the other end: the army may not eat from it, so a train unloading into
    # it would be shipping its freight out of the war.
    dumps_by_run = [[s for s in state.supplies
                     if s.side == side and s.hex in run and not s.is_dummy
                     and not s.air_dump and not wells.is_water_source(s)] for run in runs]
    if state.rolling_stock <= 0:                     # 54.43: one locomotive, bought once
        for dumps in dumps_by_run:
            payer = next((d for d in sorted(dumps, key=lambda d: d.id)
                          if rail.activation_affordable(d)), None)
            if payer is not None:
                return [RailActivateOrder(payer.id)]
        return []
    for dumps in dumps_by_run:
        if len(dumps) < 2:
            continue
        # forward = eastward: the DAK's problem is always the last mile toward Egypt
        west = min(dumps, key=lambda d: (d.hex[1], d.id))
        east = max(dumps, key=lambda d: (d.hex[1], d.id))
        if west.id == east.id:      # two counters, one id: state.supply() would resolve both ends
            continue                # to the same dump, and a haul must have two (engine._rail_haul)
        commodity = max(supply.RAIL_COMMODITIES_54_33,      # 54.33: fuel, ammunition or stores
                        key=lambda c: (getattr(west, c.lower()), c))
        qty = getattr(west, commodity.lower())
        if qty > 0:
            return [RailHaulOrder(west.id, east.id, commodity, qty)]
    return []


def coastal_shipping_doctrine(state: GameState, side: Side) -> list[CoastalShipOrder]:
    """[56.3] THE AXIS COASTAL-SHIPPING DECISION: a Benghazi<->Tobruk relief shuttle (or, in
    general, whichever two Axis harbours this campaign build carries -- nothing here names a port
    by hex) -- flagged as an opinion a commander may hold, not a law of the world, exactly like
    convoy_plan_doctrine's own flag on the overseas convoy split.

    Candidate harbours are picked by `Port.side` -- the STRUCTURAL Axis network (56.28: "Tripoli,
    Bizerta, Tobruk" are named as a NATION's ports of arrival), not by the live, unit-presence
    `state.control_of` signal `game.engine._record_control` flips the instant a single recon
    counter merely TRANSITS an unoccupied hex. Using live control here stranded ships: a lone
    Axis unit passing through the Commonwealth's Mersa Matruh railhead hex flipped it AXIS for one
    Phase, the doctrine sent a ship there, and it arrived carrying cargo with no Axis dump on that
    hex to unload into -- a real dead end. `game.engine._port_enterable` still checks LIVE control
    at the moment of departure and arrival (56.33), so a genuinely enemy-held Axis harbour (Tobruk
    recaptured) simply refuses the order/loiters rather than stranding anything.

    It only ever ships the three CONVOY_COMMODITIES. That is a DOCTRINE choice, not the rule:
    56.34 bars personnel and "Tanks, guns, etc." and nothing else, so game.engine._ship_load will
    carry Water too -- but the Axis draws his water from wells (52.7), not off a quay, so no
    commander here would spend a hull on it.

    A ship docked anywhere OTHER than the richest Axis harbour (by the same 54.5-tonnage common
    unit convoy_plan_doctrine already uses) sails there EMPTY to fetch more -- the return leg of
    the shuttle. A ship docked AT the richest harbour loads the single commodity with the largest
    gap over the poorest harbour's own stock (up to its 56.31 tonnage capacity) and sails to
    relieve it. A ship still carrying cargo needs no order (the engine unloads it automatically,
    see game.engine._coastal_shipping); an idle ship at the richest harbour with nothing positive
    to relieve stands by rather than shuffling cargo pointlessly."""
    ports = [p for p in state.ports if p.side == side]
    if len(ports) < 2:
        return []
    orders: list[CoastalShipOrder] = []
    for ship in state.ships:
        if ship.side != side or ship.dest is not None:
            continue
        if ship.ammo or ship.fuel or ship.stores or ship.water:
            continue                              # still under way's cargo -- auto-unloads
        home = state.port(ship.port)
        if home is None or home.side != side:
            continue                              # defensive: the ship's own dock is not ours
        richest = max(ports, key=lambda p: _port_stock_tons(state, side, p))
        if home.id != richest.id:
            orders.append(CoastalShipOrder(ship.id, to=richest.id))
            continue
        poorest = min((p for p in ports if p.id != home.id),
                      key=lambda p: _port_stock_tons(state, side, p))
        home_dump = _friendly_dump_at(state, side, home.hex)
        if home_dump is None:
            continue
        poorest_dump = _friendly_dump_at(state, side, poorest.hex)

        def _gap(c: str) -> float:
            here = supply.points_to_tons(getattr(home_dump, c.lower()), c)
            there = supply.points_to_tons(getattr(poorest_dump, c.lower()), c) if poorest_dump else 0
            return here - there

        commodity = max(supply.CONVOY_COMMODITIES, key=_gap)
        if _gap(commodity) <= 0:
            continue
        qty = min(getattr(home_dump, commodity.lower()), supply.tons_to_points(ship.tons, commodity))
        if qty <= 0:
            continue
        orders.append(CoastalShipOrder(ship.id, load_from=home_dump.id,
                                       load={commodity: qty}, to=poorest.id))
    return orders


def malta_africa_doctrine(state: GameState, available: int, level: str) -> int:
    """[44.25]/[44.27] + [39.19] How many AFRICAN bombers the Axis adds to this Game-Turn's Malta
    raid -- and, by 39.19, withdraws from the desert for the rest of it.

    THE TRADE IS THE POINT OF BLOCK 5.5, so the doctrine is written as a trade and not as a
    schedule. The signal it reads is THE AXIS'S OWN COMMITMENT, `level`: the [44.41] Availability
    Level he has just spent on this raid, which 44.26 says is exactly what he knows at this moment
    ("the Axis Player always assigns his map-based planes AFTER determining how many planes he will
    get from the tables").

      * ON A HEAVY LEVEL (II, III or IV) he has spent one of a finite and printed budget -- 25, 12
        and 12 Game-Turns of the whole campaign -- and a Game-Turn of that budget is worth more than
        one Operations Stage of harbour bombing. He reinforces with everything 44.27 allows.
      * ON LEVEL I -- unlimited, and 44.25's own do-nothing answer -- he has committed nothing, so
        there is nothing for the desert to be stripped for. His bombers stay in Africa.

    There is no half measure in the book to take: the cap is already the Availability Table's own
    (44.27), and a bomber held back from a raid he has decided to fly flies nothing at all that
    Game-Turn anyway.

    A DOCTRINE, NOT A CALENDAR -- the same discipline malta_raid_doctrine is written under, and for
    the same reason: the thing Phase 5 exists to delete is a hand-typed month table."""
    if available <= 0 or level == malta.DEFAULT_LEVEL:
        return 0
    return available


def air_transfer_doctrine(state: GameState, based: int, available: int) -> int:
    """[42.1]/[43.1]/[44.21] THE AXIS'S BASING DECISION: send the bomber arm to Sicily to suppress
    Malta, and bring it home to the desert when the island is down.

    THE TRADE IS THE WHOLE POINT, and it is symmetric to malta_africa_doctrine's. A bomber standing
    in the Italy/Sicily box is the ONLY bomber [44.25]/[44.42] will size a raid from -- and it is
    one that flies no Land Support over the desert until it is flown back (basing.africa_planes
    subtracts it, and 42.14 charges fuel for the flight). So the doctrine reads the same board
    signal the raid doctrine does, and answers the other half of the question:

      * **MALTA STANDING AT ITS REPAIR CEILING** -- undamaged, every Capacity Level intact, 44.14's
        eighteen aeroplanes a level all operating: there is something there to take, so the Regia
        Aeronautica's bombers go to Sicily.
      * **MALTA ALREADY KNOCKED DOWN**: the raid has done its work and the [44.5] repair table will
        take Game-Turns to undo it. Bombers held in Sicily against a flattened island are bombers
        not bombing the Eighth Army, so they come home.

    ⚠ AND THE RETURN IS NOT GRANTED THE TURN HE ASKS FOR IT, WHICH IS [39.19] AND NOT A BUG. "A
    plane flying a mission in an Operations Stage may not fly in the Strategic Phase of that
    Game-Turn AND VICE VERSA": the bombers that raided Malta this Game-Turn may not also fly the
    [42.1] mission home in it, so engine._air_transfer refuses them and the doctrine's order is
    honoured on the NEXT Game-Turn. That bites exactly when the doctrine asks -- the return trigger
    fires because the raid just knocked the island down -- and it is the point: the raid costs the
    desert a Game-Turn of the force that flew it. Until 2026-07-22 it cost nothing, and the same 56
    bombers bombed Malta and flew Land Support in one Game-Turn.

    A DOCTRINE, NOT A CALENDAR -- the same discipline the rest of this module is written under. It
    oscillates on purpose: surge, raid, return, and surge again when the island is repaired. That
    is a commander reading the position, it costs 34.17 fuel every time he does it, and it is the
    behaviour that makes the [60.32] ruling's "Sicily is a decision" true on the board rather than
    only in a docstring.

    ALL OR NOTHING, for the same reason malta_africa_doctrine is: the [44.42] table's percentages
    are percentages OF the based force, so half a bomber arm in Sicily is half a raid, and there is
    no printed middle the book asks him to pick.

    ⚠ AND IT DRIVES A MECHANISM THIS ENGINE STILL MAKES TOO STRONG, WHICH IS SAID HERE RATHER THAN
    DISCOVERED IN A MEASUREMENT. [44.24] is explicit that a raid on Malta is conducted normally,
    "including air-to-air and AA/flak", and NONE of 40/45/46 is built (game.basing's debt block):
    nothing shoots an Axis bomber down over the island, Malta's [60.46] fighters and AA Points never
    fire, and 44.28 has no losses to split. A doctrine that commits the whole bomber arm therefore
    reads as an upper bound on what the Axis can do to Malta and a lower bound on what it costs him.
    The cost that IS modelled is the desert's: while they are in Sicily they fly no Land Support."""
    if malta.capacity(state) < malta.repair_ceiling(state):
        return -based                                   # the island is down: back to the desert
    return available                                    # it is whole: go and knock it down


def malta_raid_doctrine(state: GameState) -> str:
    """[44.23] Spend the heaviest Availability Level still in the budget while Malta is at
    full health; drop to the unlimited Level I once the island is already damaged.

    ⚠ FIRST, THE GUARD, ADDED 2026-07-22: **A COMMANDER DOES NOT ROLL A TABLE HE HAS NO AIRCRAFT
    FOR.** 44.29 makes the Availability Level spent the moment it is consulted -- "the raid is
    cancelled, BUT HE STILL HAS USED THE TABLE HE ROLLED FOR ONCE" -- and the campaign's heavy
    budget is 25 + 12 + 12 Game-Turns out of 111. With no bomber based in Italy/Sicily [44.42]
    grants no planes whatever it rolls (its percentages are percentages of that force) and 44.27
    then bars the African contingent too, so the raid is arithmetically empty. Measured before this
    guard existed: the doctrine spent the ENTIRE heavy budget -- 49 Game-Turns of II, III and IV --
    on 49 raids in which not one aeroplane flew. The engine was faithful (44.29 is exactly that
    unforgiving); the DOCTRINE was not asking whether it had anything to send. It asks now, and
    Level I is free, unlimited, and 44.25's own do-nothing answer.

    A DOCTRINE, NOT A CALENDAR, and the distinction is the whole point of this block. The
    thing this engine deleted to make room for rule 44 was a hardcoded month table; a policy
    that spent III in January 1942 because that is when the Luftwaffe historically arrived
    would be the same mistake wearing a different hat. So the trigger is the BOARD: a heavy
    raid is worth its one-of-twelve Game-Turns only against an island standing at its full
    capacity (there is a level there to take), and against a Malta already knocked down the
    free Level I keeps the pressure on for nothing. That is a commander's reading of the
    position, which is what a policy is for and what the rulebook leaves to him ("it is up to
    the Axis Player to plan his raids according to what he wants to accomplish and when he
    wants to do it", 44.23).

    The second half is RATIONING, and it is the reason for the `elapsed` term. The campaign
    row grants 49 Game-Turns of heavy raiding out of 111; a commander who simply took the
    heaviest level on offer would spend every one of them before Game-Turn 50 and fight the
    second half of the war with nothing. So a level is taken only while the share of it already
    spent is no greater than the share of the war already fought -- the budget paced against
    the calendar of the SCENARIO, not against a calendar of history."""
    if malta.italy_sicily_planes(state, state.turn) <= 0:
        return "I"                                  # 44.42/44.27: no base in Sicily, no raid to fly
    if malta.capacity(state) < malta.repair_ceiling(state):
        return "I"
    elapsed = (state.turn - 1) / max(1, state.max_turns)
    for level in ("IV", "III", "II"):
        allowance = malta.budget()[level]
        if allowance and malta.spent(state, level) <= elapsed * allowance:
            return level
    return "I"


def air_mission_doctrine(state: GameState, side: Side) -> list:
    """[39.1] THE AIR MARSHAL'S STANDING TASKING IN THE CAMPAIGN: bomb the harbour, every Game-Turn,
    all war. Shared verbatim by the scripted campaign and the LIVE-STAFF campaign, the way
    malta_raid_doctrine, convoy_plan_doctrine, axis_rail_doctrine and coastal_shipping_doctrine
    already are, so the two campaign variants cannot diverge on rule 39.

    IT IS THE SEEDED SCHEDULE, AND THAT IS A DELIBERATE FLOOR RATHER THAN A DOCTRINE THIS FUNCTION
    INVENTED. scenario._campaign_air_missions writes a symmetric B-P mission against PORT-Tobruk for
    both sides every Game-Turn and lets the ENGINE decide who is besieging (_air_port refuses the
    side that holds the hex), which is the siege duel the campaign is built around. Reading it back
    out here is what makes it the SEAT'S order instead of a fact of the world: it is now proposed by
    the Air Marshal, validated at the boundary, bounded by [39.19], and OVERRIDABLE.

    ⚠ FLAGGED, AND IT IS WHY NOTHING CLEVERER IS WRITTEN HERE. The rulebook prints no target-
    selection doctrine at all -- 39.12 gives the Player a mission column and 39.15 tells him there
    is no limit on what he writes in it. A heuristic that picked targets off the board (the nearest
    enemy dump, the richest truck stack) would be an INVENTION with a citation stapled to it, and
    would move the campaign signature on nothing but this file's opinion. The decision now has a
    seat; giving that seat a real opinion is an LLM's job, or a later block's, not this one's."""
    return [m for m in state.air_missions if m.side == side and m.turn == state.turn]


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

    def organization(self, state: GameState, side: Side) -> list[OrganizationOrder]:
        # [19.4]/[19.12] Concentrate the seeded [4.45] formation tree -- ALL of it, Italian regiments
        # and tank groups and the DAK's own division and panzer-regiment HQs alike, now that a bare HQ
        # can be ordered to lead its formation (formation_moves, composed into movement below).
        return concentrate_formations(state, side)

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        # [19.12] The formation proposer rides alongside the army here exactly as it does on the
        # Commonwealth side: every DAK Parent Formation is a bare, non-combat HQ counter, so without
        # it the panzer divisions concentrate and then stand still (see formation_moves).
        plan = take_and_hold_moves(state, side, super().movement(state, side), escort=True)
        return plan + formation_moves(state, side, plan)

    def air_missions(self, state: GameState, side: Side) -> list:
        # [39.1] The Air Marshal's LAND tasking, shared verbatim with the LIVE-staff campaign
        # (game.campaign_staff) so the two campaign variants cannot diverge on rule 39.
        return air_mission_doctrine(state, side)

    def malta_raid(self, state: GameState) -> str:
        # [44.23] The Axis Malta doctrine, shared verbatim with the LIVE-staff campaign
        # (game.campaign_staff) so the two campaign variants cannot diverge on rule 44.
        return malta_raid_doctrine(state)

    def malta_africa_planes(self, state: GameState, available: int, level: str) -> int:
        # [44.25]/[39.19] The African contingent, shared with the live-staff campaign.
        return malta_africa_doctrine(state, available, level)

    def air_transfer(self, state: GameState, based: int, available: int) -> int:
        # [42.1]/[43.1] The Italy/Sicily basing decision -- the redeploy half of the Malta doctrine,
        # shared verbatim with the LIVE-staff campaign so the two variants cannot diverge on it.
        return air_transfer_doctrine(state, based, available)

    def convoy_plan(self, state: GameState, side: Side, tons: int) -> dict:
        # [56.22] The convoy split, shared with the live-staff campaign -- the Axis Player's single
        # most important recurring choice, made from the board rather than from a constant.
        return convoy_plan_doctrine(state, side, tons)

    def coastal_shipping_orders(self, state: GameState, side: Side) -> list[CoastalShipOrder]:
        # [56.3] The Benghazi<->Tobruk relief shuttle -- see coastal_shipping_doctrine's own flag.
        return coastal_shipping_doctrine(state, side)

    def rail_orders(self, state: GameState, side: Side) -> list:
        # [54.4] Buy a locomotive when the captured line is long enough to be worth one, then run
        # freight forward down it -- see axis_rail_doctrine's own flag.
        return axis_rail_doctrine(state, side)

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
