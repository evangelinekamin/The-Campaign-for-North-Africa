"""engine._organization is the REAL Reorganization Segment (48 V.C.2), driven end to end.

test_organization.py proves the game.organization rule arithmetic in isolation; this file
proves the ENGINE wiring -- that a Policy issuing OrganizationOrders folds the rule-19 events,
charges the [6.3] Capability Points, and that an illegal order is rejected at the boundary --
by running a minimal scenario through engine.run with a scripted organization policy.

The headline is test_a_kampfgruppe_forms_and_the_15_53_chart_moves_a_real_close_assault: a
Kampfgruppe is built, then a real Close Assault is fought through the engine's own resolver and
its COMBAT_RESOLVED column is shown to move off the [15.53] brigade tier -- the first time the
chart reaches that tier in a fought combat, which no counter could do before rule 19.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import engine, organization
from game.events import EventKind, Phase, Side
from game.policy import OrganizationOrder, ScriptedPolicy
from game.state import GameState, StepRecord, Unit, VP
from game.movement import TerrainMap
from game.terrain import Mobility, Terrain


def _terrain(hexes):
    return TerrainMap(terrain={h: Terrain.DESERT for h in hexes},
                      hexsides={}, roads=frozenset(), tracks=frozenset(), rails=frozenset())


def _u(uid, hex_, **kw):
    kw.setdefault("nationality", "GE")
    kw.setdefault("oca", 2)
    kw.setdefault("dca", 2)
    return Unit(uid, kw.pop("side", Side.AXIS), hex_, (StepRecord("s", kw.pop("strength", 8)),),
                mobility=Mobility.FOOT, cpa=kw.pop("cpa", 20),
                stacking_points=kw.pop("sp", 1), oca=kw.pop("oca"), dca=kw.pop("dca"), **kw)


def _state(units, *, turn=1, max_turns=1):
    hexes = {u.hex for u in units} | {(0, 0), (9, 9)}
    return GameState(
        turn=turn, max_turns=max_turns, phase=Phase.RECORD, active_side=Side.AXIS, seed=42,
        weather="normal", vp=VP(), terrain=_terrain(hexes),
        control={}, units=tuple(units), target_hex=(9, 9),
        supplies=(), consumed={}, initial_supply={})


class _OrgPolicy(ScriptedPolicy):
    """A ScriptedPolicy that issues a fixed batch of OrganizationOrders on Game-Turn 1, stage 1,
    then nothing (so the batch fires exactly once)."""
    def __init__(self, orders, attacker=Side.AXIS):
        super().__init__(attacker)
        self._orders = orders
        self._fired = False

    def organization(self, state, side):
        if side != Side.AXIS or self._fired or state.stage != 1:
            return []
        self._fired = True
        return list(self._orders)


def _run(units, orders, **kw):
    st = _state(units, **kw)
    return engine.run(st, _OrgPolicy(orders), ScriptedPolicy(Side.AXIS))


def _kinds(events, kind):
    return [e for e in events if e.kind == kind]


# --- the wiring: an attach folds the tree AND charges CP -------------------------------

def test_attach_folds_the_tree_and_charges_both_counters_the_6_3_cp():
    hq = _u("KG", (0, 0), sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    bn = _u("B1", (0, 0), is_tank=True)
    res = _run([hq, bn], [OrganizationOrder("attach", unit_id="B1", parent_id="KG")])

    attached = _kinds(res.events, EventKind.UNIT_ATTACHED)
    assert len(attached) == 1 and attached[0].payload["parent_id"] == "KG"
    # 6.3: "Attach an unassigned unit (Parent Formation and attaching unit) = 2" -- BOTH counters
    cp = _kinds(res.events, EventKind.CP_EXPENDED)
    charged = {e.payload["unit_id"]: e.payload["cp"] for e in cp if e.payload.get("activity") == "attach"}
    assert charged == {"KG": 2, "B1": 2}
    assert res.final.unit("B1").attached_to == "KG"


def test_an_illegal_attach_is_rejected_at_the_boundary():
    # a lone battalion is not a Parent Formation (19.0): nothing may attach to it
    a = _u("A", (0, 0))
    b = _u("B", (0, 0))
    res = _run([a, b], [OrganizationOrder("attach", unit_id="B", parent_id="A")])
    assert _kinds(res.events, EventKind.UNIT_ATTACHED) == []
    rej = [e for e in res.events if e.kind == EventKind.ORDER_REJECTED
           and e.payload.get("order") == "attach"]
    assert rej and "Parent Formation" in rej[0].payload["reason"]
    assert res.final.unit("B").attached_to == ""


def test_the_maximum_attachment_chart_is_enforced_by_the_engine():
    hq = _u("KG", (0, 0), sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    tanks = [_u(f"T{i}", (0, 0), is_tank=True) for i in range(2)]
    orders = [OrganizationOrder("attach", unit_id="T0", parent_id="KG"),
              OrganizationOrder("attach", unit_id="T1", parent_id="KG")]   # 2nd tank illegal (19.72)
    res = _run([hq] + tanks, orders)
    assert len(_kinds(res.events, EventKind.UNIT_ATTACHED)) == 1           # only the first
    assert res.final.unit("T1").attached_to == ""


# --- form / disband a Kampfgruppe -----------------------------------------------------

def test_form_kg_appends_a_headquarters_counter():
    bn = _u("B1", (0, 0), is_tank=True)
    res = _run([bn], [OrganizationOrder("form_kg", unit_id="KG-Voss",
                                        org_type="ge_battle_group", name="Gruppe Voss")])
    formed = _kinds(res.events, EventKind.BATTLE_GROUP_FORMED)
    assert len(formed) == 1
    kg = res.final.unit("KG-Voss")
    assert kg is not None and kg.org_type == "ge_battle_group" and not kg.is_combat
    assert organization.size(kg, ()) == 0                                 # 9.12: empty HQ is 0 SP


def test_detaching_the_last_german_unit_disbands_the_kampfgruppe():
    res = _run(
        [_u("B1", (0, 0), is_tank=True)],
        [OrganizationOrder("form_kg", unit_id="KG-Voss", org_type="ge_battle_group", name="Voss"),
         OrganizationOrder("attach", unit_id="B1", parent_id="KG-Voss"),
         OrganizationOrder("detach", unit_id="B1", parent_id="KG-Voss")])
    assert _kinds(res.events, EventKind.BATTLE_GROUP_DISBANDED)            # note 2
    assert not res.final.unit("KG-Voss").alive                            # counter removed


def test_disbanding_a_kampfgruppe_detaches_its_remaining_italian_units():
    """Kampfgruppen HQ's sheet note 2: when the last GERMAN unit detaches, the Battle Group is
    removed AND 'any remaining Italian units must be detached'. Without that, the Italian would go
    on pointing its 19.12 representation at a counter that is gone -- a dangling parent that would
    read a size for the dead HQ (organization.size returns the HQ's SP while any child claims it)."""
    hq = _u("KG", (0, 0), sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    ge = _u("GE1", (0, 0), is_tank=True)
    it = _u("IT1", (0, 0), nationality="IT")                       # an Italian infantry battalion
    res = _run([hq, ge, it],
               [OrganizationOrder("attach", unit_id="GE1", parent_id="KG"),
                OrganizationOrder("attach", unit_id="IT1", parent_id="KG"),
                OrganizationOrder("detach", unit_id="GE1", parent_id="KG")])   # last German leaves
    attached_it = [e for e in _kinds(res.events, EventKind.UNIT_ATTACHED)
                   if e.payload["unit_id"] == "IT1"]
    assert attached_it                                  # sanity: the Italian DID attach first
    assert _kinds(res.events, EventKind.BATTLE_GROUP_DISBANDED)    # note 2: KG removed
    assert not res.final.unit("KG").alive
    assert res.final.unit("IT1").attached_to == ""                # note 2: the Italian was detached
    assert res.final.unit("GE1").attached_to == ""                # the German that triggered it


# --- rebuild + augment ----------------------------------------------------------------

def test_rebuild_absorbs_replacement_points_up_to_the_printed_maximum():
    bn = _u("B1", (0, 0), strength=4, max_toe=8)
    res = _run([bn], [OrganizationOrder("rebuild", unit_id="B1", points=2)])
    assert res.final.unit("B1").strength == 6
    cp = [e for e in _kinds(res.events, EventKind.CP_EXPENDED)
          if e.payload.get("activity") == "rebuild"]
    assert cp and cp[0].payload["cp"] == 1                                # 19.68: 1 CP per 2 points


def test_rebuild_past_the_printed_maximum_is_rejected():
    bn = _u("B1", (0, 0), strength=7, max_toe=8)
    res = _run([bn], [OrganizationOrder("rebuild", unit_id="B1", points=4)])
    assert res.final.unit("B1").strength == 7                             # 19.61: unchanged
    assert [e for e in res.events if e.kind == EventKind.ORDER_REJECTED
            and e.payload.get("order") == "rebuild"]


def test_augment_folds_anti_tank_toe_onto_an_axis_hq():
    hq = _u("KG", (0, 0), sp=2, org_type="ge_battle_group", is_combat=False, strength=1, cpa=60)
    res = _run([hq], [OrganizationOrder("augment", unit_id="KG", points=4)])
    assert _kinds(res.events, EventKind.HQ_AUGMENTED)
    out = res.final.unit("KG")
    assert organization.at_points(out) == 4
    assert organization.size(out, ()) == 0                                # 19.87


# --- THE PROOF, end to end ------------------------------------------------------------

def test_a_kampfgruppe_forms_and_the_engine_feeds_15_53_its_two_stacking_points():
    """The exact expression the engine hands the [15.53] chart at its combat.resolve call site
    (game.engine, `attacker_size=organization.combat_size(armed_atk + _parents_of(r, armed_atk))`)
    must read the FORMATION's size, not the battalions' own: 19.12 makes attached battalions one
    counter, 9.13 makes that counter worth 2. The engine's Close Assault never appears in the
    armed-attacker list for the HQ -- an HQ is not a combat unit -- so _parents_of has to walk the
    attachment chain back onto the board before combat_size can see it. This proves that walk on a
    real engine state.

    A/B against the same battalions NOT attached: there the expression is 1, each counting for
    itself. This is the wired proof that the chart -- which could never reach its brigade tier
    before, no counter in the engine carrying more than one Stacking Point -- now reads a real
    formation once rule 19 builds one."""
    hq = _u("KG", (0, 0), sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    # 1 tank + 3 infantry offered; 19.72 caps infantry at 2, so THREE attach (tank + 2 infantry) --
    # 3 of the Battle Group's 4 attachable battalions, above 9.26's two-thirds, so a full 2-SP
    # brigade-equivalent and NOT a shell. (A 2-of-4 Kampfgruppe would be a shell -> read as 1 SP.)
    bns = [_u(f"B{i}", (0, 0), is_tank=(i == 0), strength=8) for i in range(4)]
    res = _run([hq] + bns, [OrganizationOrder("attach", unit_id=f"B{i}", parent_id="KG")
                            for i in range(4)])
    r = engine._Run(res.final)                       # a driver over the post-attach board
    armed_atk = [res.final.unit(f"B{i}") for i in range(4) if res.final.unit(f"B{i}").attached_to]
    assert len(armed_atk) == 3                        # 19.72: the 3rd infantry was rejected
    engine_size = organization.combat_size(armed_atk + engine._parents_of(r, armed_atk))
    assert engine_size == 2                           # [9.13]/[19.12] the formation, not three 1s

    # A/B: the identical battalions with no Parent are worth 1 apiece -> largest is 1
    loose = [replace(u, attached_to="") for u in armed_atk]
    r2 = engine._Run(replace(res.final, units=tuple(loose) + (res.final.unit("KG"),)))
    assert organization.combat_size(loose + engine._parents_of(r2, loose)) == 1


def test_a_kampfgruppe_forms_and_the_15_53_chart_moves_a_real_close_assault():
    """END TO END through the engine's own resolver, not just the size expression: a German
    Kampfgruppe (HQ + three attached battalions) Close Assaults a lone Commonwealth battalion.
    engine._resolve_combat reads the attacker's size up the attachment chain
    (organization.combat_size + engine._parents_of), so the [15.53] chart shifts the FOUGHT column
    two steps off its '2 or 3 SP's / 1 SP' row and that shift lands in the COMBAT_RESOLVED event.

    The A/B is the identical fight with the same battalions NOT attached (size 1, no shift), same
    seed, same dice: the ONLY difference between the two resolutions is the org-size column shift.
    This is the wired proof the reviewer asked for -- a real fought combat whose column moved from
    organization size -- reachable only once rule 19 builds a formation."""
    def _fight(attached: bool):
        hq = _u("KG", (0, 0), sp=2, org_type="ge_battle_group", is_combat=False, strength=1,
                morale=3, cohesion=6)
        parent = "KG" if attached else ""
        atk = [_u(f"B{i}", (0, 0), strength=6, oca=2, dca=2, ammo=50, morale=3, cohesion=6,
                  attached_to=parent) for i in range(3)]
        dfd = _u("D", (1, 0), side=Side.ALLIED, nationality="CW", strength=6, oca=2, dca=6,
                 ammo=50, morale=3, cohesion=6)
        r = engine._Run(_state([hq] + atk + [dfd]))
        size = organization.combat_size(atk + engine._parents_of(r, atk))
        engine._resolve_combat(r, Side.AXIS, "AXIS/Command", atk, [dfd], (1, 0), set(), set())
        resolved = _kinds(r.events, EventKind.COMBAT_RESOLVED)
        assert len(resolved) == 1 and "surrender" not in resolved[0].payload, \
            "the fight must resolve to a column, not a surrender"
        return size, resolved[0].payload["column"]

    kg_size, kg_col = _fight(attached=True)
    loose_size, loose_col = _fight(attached=False)
    assert (kg_size, loose_size) == (2, 1)              # 9.13/19.12: the formation vs three loose 1s
    assert kg_col > loose_col                            # [15.53] moved the fought column
