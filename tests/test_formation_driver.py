"""[19.12]/[15.53] THE PARENT COUNTER MARCHES ITS FORMATION -- the missing DRIVER.

The machinery to move a formation as one counter has been complete for a long time:
`organization.may_attach` has no combat test (a bare HQ with an [19.3] org_type row is a legal
Parent today), `engine._movement` carries the whole co-located subtree at no Capability Point and
no Fuel and stacking-tests the FORMATION's footprint at the destination, and its rejection chain
contains no `is_combat` test at all -- so a MoveOrder naming a bare HQ is validated like any other.

WHAT WAS MISSING WAS THE ORDER. No proposer in this repo ever names a non-combat unit (the one
exception, `CampaignCommonwealthPolicy._railway`, states the invariant in as many words), and an
attached subsidiary MAY NOT SELF-MOVE (19.12, engine._movement). So folding a formation into a bare
HQ FROZE it where it stood -- measured, and it killed the Commonwealth faucet: "the Eighth Army's
Delta brigades concentrated and never reached the railhead". `concentrate_formations` therefore
gated concentration on `p.is_combat`, a workaround its own docstring flagged as "an engine
limitation, not a rule".

MEASURED on scenario.campaign(1) before this slice: 91 Parent Formations have assigned children, 15
of them are combat counters and concentrate, and **76 are gated out, freezing 318 children** -- 61
of the 76 Commonwealth (37 infantry brigades, 13 infantry divisions, 3 super-brigades, 6 armour
formations, 2 allied brigades), 8 German (4 division HQs, 2 armored regiments, 288 Son and the
Ramcke Brigade) and 7 Italian -- both breakdowns corrected 2026-08-04, they did not sum. So the
[15.53] Brigade and Division tiers were denied almost entirely to the side this project has
repeatedly measured as the starved one.

`campaign_policy.formation_moves` is that driver, and it inherits doctrine rather than inventing
any: the Parent is given THE DESTINATION THE EXISTING PROPOSER ALREADY GAVE ITS STRONGEST CARRIED
COMBAT CHILD. See its docstring for the doctrine decision and its flag.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import engine, organization, stacking, tactics                  # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,                     # noqa: E402
                                  CampaignCommonwealthPolicy,
                                  concentrate_formations, formation_moves)
from game.events import EventKind, Phase, Side                            # noqa: E402
from game.movement import TerrainMap                                      # noqa: E402
from game.policy import MoveOrder, ScriptedPolicy                         # noqa: E402
from game.scenario import campaign                                        # noqa: E402
from game.state import GameState, StepRecord, Unit, VP                    # noqa: E402
from game.terrain import Mobility, Terrain                                # noqa: E402
from baselines import CAMPAIGN_SEED                                       # noqa: E402

LINE = [(q, 0) for q in range(14)]
H = (0, 0)


def _u(uid, *, hex_=H, strength=8, cpa=20, attached_to="", org_type="", is_combat=True,
       sp=1, mobility=Mobility.FOOT, side=Side.AXIS, **kw):
    return Unit(uid, side, hex_, (StepRecord("s", strength),), mobility=mobility, cpa=cpa,
                stacking_points=sp, oca=kw.pop("oca", 2), dca=kw.pop("dca", 2),
                nationality=kw.pop("nationality", "GE"), org_type=org_type,
                attached_to=attached_to, is_combat=is_combat, **kw)


def _state(units, *, max_turns=1):
    hexes = {u.hex for u in units} | set(LINE)
    tmap = TerrainMap(terrain={h: Terrain.DESERT for h in hexes},
                      hexsides={}, roads=frozenset(), tracks=frozenset(), rails=frozenset())
    return GameState(turn=1, max_turns=max_turns, phase=Phase.RECORD, active_side=Side.AXIS,
                     seed=42, weather="normal", vp=VP(), terrain=tmap, control={},
                     units=tuple(units), target_hex=(13, 0), supplies=(), consumed={},
                     initial_supply={}, replacement_pool={})


def _reach(state, unit, formation=()):
    return tactics.reachable_for(state, unit, frozenset(), frozenset(),
                                 state.living(unit.side), formation=formation)


def _brigade(**kw):
    """A BARE, NON-COMBAT HQ with two attached battalions standing on its hex -- the shape every
    Commonwealth brigade/division HQ and every German division HQ actually has."""
    hq = _u("HQ", org_type="ge_battle_group", sp=2, is_combat=False, strength=1, **kw)
    big = _u("B-big", strength=8, attached_to="HQ")
    small = _u("B-small", strength=3, attached_to="HQ")
    return hq, big, small


# --- the doctrine: the Parent goes where the formation was already going ------------------------

def test_the_bare_hq_is_ordered_where_its_strongest_carried_child_was_sent():
    """THE DOCTRINE, and it is inherited rather than authored. The Parent counter REPRESENTS its
    children (19.12, "functionally combined into one unit"), so it is given the destination the
    army's own proposer chose for the strongest combat unit it carries -- the formation's main
    body. No new HQ doctrine is invented here; the formation goes where that formation was going."""
    hq, big, small = _brigade()
    state = _state([hq, big, small])
    army = [MoveOrder("B-big", (1, 0)), MoveOrder("B-small", (2, 0))]

    orders = formation_moves(state, Side.AXIS, army)

    assert [(o.unit_id, tuple(o.to)) for o in orders] == [("HQ", (1, 0))], \
        "the Parent must inherit its strongest carried child's destination"


def test_a_parent_with_nothing_attached_is_untouched():
    """THE BYTE-IDENTITY GUARANTEE. A counter that carries no subtree -- which is every counter in
    every scenario with no live organization tree, both Desert Fox benchmarks included -- yields no
    order at all, so a tree-less scenario cannot move one byte."""
    lone = _u("HQ", org_type="ge_battle_group", sp=2, is_combat=False, strength=1)
    loose = _u("B", strength=8)                      # assigned to nobody, attached to nobody
    state = _state([lone, loose])

    assert formation_moves(state, Side.AXIS, [MoveOrder("B", (1, 0))]) == []


def test_a_stale_link_across_hexes_is_not_carried_and_not_followed():
    """[19.12]/[19.13] attachment is a SAME-HEX relationship. A subsidiary standing somewhere else
    is a split the Reorganization Segment has yet to reconcile: it is not in the counter, so the
    Parent must not march off after ITS order."""
    hq = _u("HQ", org_type="ge_battle_group", sp=2, is_combat=False, strength=1)
    away = _u("B-away", hex_=(5, 0), strength=8, attached_to="HQ")
    state = _state([hq, away])

    assert formation_moves(state, Side.AXIS, [MoveOrder("B-away", (6, 0))]) == []


def test_a_child_the_army_left_standing_leaves_the_formation_standing():
    """A formation whose children were given no orders has nowhere to be: the army's doctrine said
    stay, and the Parent keeps it. (This is what makes the standing garrison order survive
    concentration -- hold_garrisons withholds the child's move, and no Parent order replaces it.)"""
    hq, big, small = _brigade()
    state = _state([hq, big, small])

    assert formation_moves(state, Side.AXIS, []) == []


# --- [6.15]: never order a Parent where its slowest component cannot go -------------------------

def test_the_proposer_never_orders_a_parent_beyond_its_slowest_components_reach():
    """[6.15] binds a Parent Formation to the lowest CPA in it, so the destination the army chose
    for a FAST child may be flatly unreachable by the formation. Proposing it anyway would order a
    rejection -- the "don't propose a reject" discipline every proposer in campaign_policy keeps.

    The destination is chosen by measurement, not by hand: a hex the CPA-40 child's own Parent
    reaches alone and the CPA-10-bound formation does not."""
    hq = _u("HQ", cpa=40, org_type="ge_battle_group", sp=2, is_combat=False, strength=1)
    fast = _u("B-fast", cpa=40, strength=8, attached_to="HQ")
    slow = _u("B-slow", cpa=10, strength=3, attached_to="HQ")
    state = _state([hq, fast, slow])

    beyond = set(_reach(state, hq)) - set(_reach(state, hq, formation=[fast, slow]))
    assert beyond, "test scaffold: the two CPAs must actually differ in reach"
    target = min(beyond)

    assert formation_moves(state, Side.AXIS, [MoveOrder("B-fast", target)]) == []


def test_the_proposer_falls_back_to_a_destination_the_whole_formation_can_make():
    """...and it does not simply give up on the formation when the strongest child's destination is
    out of [6.15] reach. Every candidate is still a destination THE EXISTING DOCTRINE CHOSE for a
    member of this formation -- the next strongest, in strength order -- so the fallback inherits
    doctrine exactly as the primary does. Without it a formation with one fast battalion in it
    would stand still all war, which is the freeze this slice exists to end."""
    hq = _u("HQ", cpa=40, org_type="ge_battle_group", sp=2, is_combat=False, strength=1)
    fast = _u("B-fast", cpa=40, strength=8, attached_to="HQ")
    slow = _u("B-slow", cpa=10, strength=3, attached_to="HQ")
    state = _state([hq, fast, slow])

    bound = set(_reach(state, hq, formation=[fast, slow])) - {H}
    beyond = set(_reach(state, hq)) - set(_reach(state, hq, formation=[fast, slow]))
    assert bound and beyond, "test scaffold"
    near, far = min(bound), min(beyond)

    orders = formation_moves(state, Side.AXIS,
                             [MoveOrder("B-fast", far), MoveOrder("B-slow", near)])

    assert [(o.unit_id, tuple(o.to)) for o in orders] == [("HQ", near)]


def test_the_proposer_keeps_the_9_14_stacking_gate_at_the_destination():
    """[9.14]/[9.12] The FIRST unit under a large HQ makes that HQ jump from a bare 0 to its full
    formation value, so a formation can be legal where it stands and illegal one hex on. The engine
    tests the formation's whole footprint at the destination (engine._movement); the proposer tests
    the same thing rather than ordering a move the board cannot hold."""
    hq, big, small = _brigade()
    dest = (1, 0)
    crowd = [_u(f"X{i}", hex_=dest) for i in range(6)]
    state = _state([hq, big, small, *crowd])

    assert not stacking.within_hex_limit([*crowd, hq, big, small], Terrain.DESERT), \
        "test scaffold: the destination stack must actually be over the limit"
    assert formation_moves(state, Side.AXIS, [MoveOrder("B-big", dest)]) == []


# --- no unit is ordered twice -------------------------------------------------------------------

def test_a_parent_another_proposer_has_already_ordered_is_left_alone():
    """THE `_railway` INVARIANT, kept. That proposer rides alongside the army because "every
    proposer in this repo skips a non-combat unit... so no unit can be ordered twice"; a formation
    proposer that names non-combat counters must therefore look at what has ALREADY been ordered.
    A Parent somebody else is already moving is not ordered again."""
    hq, big, small = _brigade()
    state = _state([hq, big, small])
    already = [MoveOrder("HQ", (2, 0)), MoveOrder("B-big", (1, 0))]

    assert formation_moves(state, Side.AXIS, already) == []


def test_no_unit_is_ordered_twice_on_the_live_campaign():
    """The composition, on the real board and on BOTH sides: the railway gang, the army under its
    rule-64.73 standing orders, and the formation proposer, with no unit named twice.

    THE PRECONDITION IS CONSTRUCTED, not hoped for: nothing is attached at setup (the attaches are
    issued in the Reorganization Segment), so concentrate_formations' own orders are applied to the
    board first. That is the same technique tests/test_campaign_concentration.py uses to give its
    garrison test something to protect."""
    for side, policy in ((Side.ALLIED, CampaignCommonwealthPolicy()),
                         (Side.AXIS, CampaignAxisPolicy())):
        st = campaign(seed=CAMPAIGN_SEED)
        attach = {o.unit_id: o.parent_id
                  for o in concentrate_formations(st, side) if o.kind == "attach"}
        assert attach, f"{side.value}: nothing concentrates at all -- the check would be vacuous"
        st = replace(st, units=tuple(replace(u, attached_to=attach[u.id]) if u.id in attach else u
                                     for u in st.units))
        moves = policy.movement(st, side)
        ids = [o.unit_id for o in moves]
        assert len(ids) == len(set(ids)), \
            f"{side.value}: ordered twice -- {sorted({i for i in ids if ids.count(i) > 1})}"


def test_the_formation_proposer_actually_fires_on_the_live_campaign():
    """...and the check above is not vacuous on its own subject either: with the tree concentrated,
    at least one BARE, NON-COMBAT Parent is under orders on the real campaign board. This is the
    order that did not exist before this slice."""
    fired = 0
    for side, policy in ((Side.ALLIED, CampaignCommonwealthPolicy()),
                         (Side.AXIS, CampaignAxisPolicy())):
        st = campaign(seed=CAMPAIGN_SEED)
        attach = {o.unit_id: o.parent_id
                  for o in concentrate_formations(st, side) if o.kind == "attach"}
        st = replace(st, units=tuple(replace(u, attached_to=attach[u.id]) if u.id in attach else u
                                     for u in st.units))
        ordered = {o.unit_id for o in policy.movement(st, side)}
        fired += sum(1 for u in st.living(side) if not u.is_combat and u.id in ordered
                     and any(k.attached_to == u.id for k in st.units_at(u.hex)))
    assert fired, "no bare HQ is under orders anywhere on the campaign board"


# --- the wiring: a formation under a bare HQ actually MARCHES -----------------------------------

class _Army(ScriptedPolicy):
    """An 'army' proposer that names COMBAT units only -- the invariant every proposer in
    game.campaign_policy keeps -- fired once, on Game-Turn 1 stage 1."""

    def __init__(self, army, *, drive=True):
        super().__init__(Side.AXIS)
        self._army, self._drive, self._fired = army, drive, False

    def movement(self, state, side):
        if side != Side.AXIS or self._fired or state.stage != 1:
            return []
        self._fired = True
        if not self._drive:
            return list(self._army)               # the CONTROL: the army alone, as it was before
        return list(self._army) + formation_moves(state, side, self._army)


def test_a_concentrated_formation_under_a_bare_hq_marches_and_its_children_arrive_with_it():
    """THE HEADLINE, with the defect it fixes measured in the same test.

    CONTROL (the army alone, which is every proposer in this repo before this slice): the battalions
    are attached, so 19.12 drops their own orders at engine._movement and NOTHING MOVES. That is the
    freeze -- "concentrate, then freeze, then starve".

    DRIVEN: the Parent is ordered instead, and its counter carries the formation (19.12,
    organization.co_located_subtree) -- the HQ arrives and every battalion arrives with it."""
    hq, big, small = _brigade()
    army = [MoveOrder("B-big", (1, 0)), MoveOrder("B-small", (1, 0))]

    frozen = engine.run(_state([hq, big, small]), _Army(army, drive=False),
                        ScriptedPolicy(Side.AXIS)).final
    assert (frozen.unit("HQ").hex, frozen.unit("B-big").hex) == (H, H), \
        "test scaffold: the control arm must reproduce the freeze this slice fixes"

    res = engine.run(_state([hq, big, small]), _Army(army), ScriptedPolicy(Side.AXIS))
    fin = res.final
    assert tuple(fin.unit("HQ").hex) == (1, 0), "the bare HQ never marched -- the formation is frozen"
    assert tuple(fin.unit("B-big").hex) == (1, 0) and tuple(fin.unit("B-small").hex) == (1, 0), \
        "[19.12] the subsidiaries ride inside their Parent's counter and must arrive with it"

    # ...and they arrived as ONE counter: the Parent pays, the carried pay nothing (19.12).
    moved = [e for e in res.events if e.kind == EventKind.UNIT_MOVED]
    spent = {e.payload["unit_id"]: e.payload["cp_spent"] for e in moved}
    assert spent["B-big"] == 0 and spent["B-small"] == 0 and spent["HQ"] > 0


def test_the_15_53_tier_is_reached_by_a_formation_that_marched_under_a_bare_hq():
    """THE POINT OF THE WHOLE SLICE, end to end through the engine's own resolver -- the same proof
    tests/test_reorganization_segment.py makes of a Kampfgruppe, made here of a formation that
    MARCHED to the fight under a counter no proposer could previously order.

    The formation is driven one hex by formation_moves, and the Close Assault it then fights from
    the hex it marched to is resolved by engine._resolve_combat. The A/B is the identical fight with
    the same battalions unattached: the ONLY difference is the [15.53] Organization Size column
    shift, which under the old `p.is_combat` gate no Commonwealth brigade or German division could
    ever reach, because every one of their Parents is a bare HQ."""
    def _fight(driven: bool):
        hq = _u("HQ", org_type="ge_battle_group", sp=2, is_combat=False, strength=1,
                morale=3, cohesion=6)
        parent = "HQ" if driven else ""
        kids = [_u(f"B{i}", strength=6, ammo=50, morale=3, cohesion=6, attached_to=parent)
                for i in range(3)]
        army = [MoveOrder("B0", (1, 0))]
        pol = _Army(army) if driven else _Army([MoveOrder(k.id, (1, 0)) for k in kids])
        fin = engine.run(_state([hq, *kids]), pol, ScriptedPolicy(Side.AXIS)).final
        atk = [fin.unit(k.id) for k in kids]
        assert all(tuple(u.hex) == (1, 0) for u in atk), "the attackers never reached the fight"

        dfd = _u("D", hex_=(2, 0), side=Side.ALLIED, nationality="CW", strength=6, dca=6,
                 ammo=50, morale=3, cohesion=6)
        r = engine._Run(_state([*[fin.unit(u.id) for u in [hq, *kids]], dfd]))
        size = organization.combat_size(atk + engine._parents_of(r, atk))
        engine._resolve_combat(r, Side.AXIS, "AXIS/Command", atk, [dfd], (2, 0), set(), set())
        resolved = [e for e in r.events if e.kind == EventKind.COMBAT_RESOLVED]
        assert len(resolved) == 1 and "surrender" not in resolved[0].payload
        return size, resolved[0].payload["column"]

    formed_size, formed_col = _fight(driven=True)
    loose_size, loose_col = _fight(driven=False)

    assert loose_size == 1, "unattached battalions fight at the lone-battalion tier"
    assert formed_size >= 2, \
        "a formation that marched under a bare HQ must fight at its Organization Size ([15.53])"
    assert formed_col != loose_col, \
        "the [15.53] Organization Size chart did not move the fought column"


# --- step 3: the gate is gone, and the tier is no longer denied to the Commonwealth -------------

def test_concentration_is_no_longer_confined_to_combat_parents():
    """STEP 3 of the slice, asserted of the real order of battle. `concentrate_formations` used to
    gate on `p.is_combat` -- a workaround for the missing driver, not a rule -- and that denied the
    [15.53] Brigade and Division tiers to 76 of the 91 Parent Formations on the campaign board, 61
    of them Commonwealth. With the driver built the gate is dropped, and the Eighth Army's brigades
    and divisions concentrate like anybody else's."""
    st = campaign(seed=1)
    by_id = {u.id: u for u in st.units}

    def _bare_parents(state):
        orders = (concentrate_formations(state, Side.ALLIED)
                  + concentrate_formations(state, Side.AXIS))
        return [by_id[o.parent_id] for o in orders if o.kind == "attach"
                and not by_id[o.parent_id].is_combat]

    bare = _bare_parents(st)
    assert bare, "not one bare HQ concentrates -- the p.is_combat gate is still in force"
    assert any(p.side == Side.ALLIED for p in bare), \
        "the Commonwealth brigade/division tier is still gated out"

    # THE DAK IS NOT ON THE SEPTEMBER-1940 BOARD, so its half of the claim needs a turn rather than
    # a fixture: every German Parent Formation is a rule-20 reinforcement (HQ 5 Le Div arrives on
    # Game-Turn 21, HQ 15 Panzer Div on 29, and the rest later still), and state.on_map hides a
    # counter until then. Advancing the clock is the whole construction -- the muster hexes are the
    # seeded ones, and the DAK arrives standing on its own HQs.
    landed = _bare_parents(replace(st, turn=29))
    assert any(p.nationality == "GE" for p in landed), \
        "every German Parent is a bare HQ, so the DAK must now concentrate too"


# --- THE STANDING ORDERS OUTRANK THE FORMATION (2026-08-04 review repair) -----------------------
#
# Both adversarial reviews of this slice, independently and each with its own A/B, found the same
# defect: `hold_garrisons` and `delta_garrison` enforce a standing order by DROPPING the pinned
# unit's move order, and abstention was not a veto. `formation_moves` saw a child with no
# destination, skipped it, took a SIBLING's destination, and the [19.12] carry then walked the
# pinned garrison off its hex at cp_spent 0 -- no rejection, no event anyone would notice.
# Measured on scenario.campaign(1): Delta hex (43,141) stood unheld for 28 of 36 (turn, stage)
# snapshots of a 12-Game-Turn fold, on every seed tried, where the control tree makes it
# structurally impossible. [64.71] is the AUTO-WIN condition -- the Axis wins the war outright by
# occupying Alexandria and Cairo -- so this was the most expensive hex on the board.

def test_a_pinned_garrison_is_never_carried_off_its_hex_by_its_own_formation():
    """THE REPAIR, asserted on a real fold because that is the only place it shows.

    A setup-time check does NOT catch this: at Game-Turn 1 stage 1 only three units are attached
    and no Parent yet carries a pinned unit. The attaches land in the engine's own Reorganization
    Segment, so the defect first appears at GT1 stage 2 -- which is exactly where both reviews
    found it, and why this test folds the campaign instead of inspecting the setup.

    Measured before the fix, campaign(seed=1, max_turns=3): Polish-Bde-I is carried off Delta hex
    (43,141) three times at cp_spent 0. delta_garrison's own docstring states the contract:
    "the one unit standing on each of them never marches away. Ever."
    """
    from game import campaign_claim
    from game.apply import fold

    st = campaign(seed=1, max_turns=3)
    res = engine.run(st, CampaignAxisPolicy(), CampaignCommonwealthPolicy())

    board, pins, carried_off = st, set(), []
    for i, e in enumerate(res.events):
        if (e.kind == EventKind.UNIT_MOVED and e.side == Side.ALLIED
                and e.payload.get("unit_id") in pins and not e.payload.get("cp_spent")):
            carried_off.append((e.turn, e.payload["unit_id"],
                                tuple(e.payload.get("from") or ()), tuple(e.payload.get("to") or ())))
        board = fold(board, [e])
        if e.kind == EventKind.TURN_ADVANCED or i % 400 == 0:
            pins = (campaign_claim.garrison_units(board, Side.ALLIED)
                    | campaign_claim.delta_garrison(board, Side.ALLIED))

    assert not carried_off, (
        "a unit under a [64.71]/[64.73] standing order was carried off its hex by its own "
        f"formation at zero Capability Points: {carried_off[:5]}")


def test_a_combat_parent_is_still_left_to_the_army_proposer():
    """The `p.is_combat` skip, which the correctness review mutation-tested and found UNPINNED --
    deleting it left all thirteen tests green. It is load-bearing: without it the same standing-order
    defeat above opens through the fifteen combat Parents as well, because a combat Parent whose own
    order hold_garrisons dropped would become eligible for a sibling's destination."""
    hq = _u("P", org_type="ge_battle_group", sp=2, is_combat=True, strength=8)
    big = _u("B-big", strength=8, attached_to="P")
    small = _u("B-small", strength=3, attached_to="P")
    state = _state([hq, big, small])
    to = min(h for h in _reach(state, hq, formation=[big, small]) if h != hq.hex)

    assert formation_moves(state, Side.AXIS, [MoveOrder("B-big", to)]) == [], (
        "a COMBAT Parent belongs to the army proposer -- this proposer must not order it")
