"""[6.15] A PARENT FORMATION MOVES AT ITS LOWEST COMPONENT'S CAPABILITY POINT ALLOWANCE.

The rule, verbatim (docs/rules/06-the-capability-point-system.md, chapter 6):

    "The CPA of a "Parent Formation" (e.g., division, brigade, etc.) is that of the lowest CPA of
    the units comprising that parent formation, regardless of the CPA of any higher-CPA units. If
    the British 7th Armored Division was to move as an entity (consult the OA Sheet for the 7th
    Arm. Div) it would move with a CPA of '10', or that of its lowest-CPA unit -- the 1st KRRC
    (without trucks)."

WHY THIS LANDS NOW. `organization.co_located_subtree` has carried a Parent's attached subtree since the
[4.45] formation tree was seeded, and its own docstring has flagged this simplification the whole
time: the mover's reach was gated on the PARENT's CPA, which it called immaterial "while the only
Parents that carry a subtree are homogeneous foot-infantry regiments -- a motorized formation's HQ
is non-combat and never carries". Both halves of that excuse are expiring:

  * [15.53] HQ-follows-its-formation is the next slice, and it hands motorized HQ counters a
    subtree to carry. data/unit_stats.json prints GE.hq at CPA 60 MOTORIZED and CW.hq at CPA 30
    MOTORIZED, so without [6.15] a German divisional HQ would drag foot infantry across the desert
    at sixty Capability Points.
  * A GUEST attached under [19.5] need not be assigned to the Parent and may print a LOWER CPA than
    it -- an artillery battalion at 15 joining a CPA-20 Italian tank group -- which is reachable in
    play on the roster as it stands.

MEASURED BEFORE BUILDING, on scenario.campaign(1): all 15 combat Parents have a Parent CPA that
already IS the formation minimum (ten Italian infantry regiments 10/10, three tank groups 20/20,
1-Army-Tank-Bde 25/25, and IT-4-CCNN---(4CN) at parent 10 against kids {10, 15, 25}). So this rule
is expected to be byte-identical on the setup tree, and the campaign signatures are the proof --
not this file, which constructs the heterogeneous formations the setup does not yet contain.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import engine, tactics
from game.events import EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import MoveOrder, ScriptedPolicy
from game.state import GameState, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain

LINE = [(q, 0) for q in range(14)]


def _u(uid, *, cpa, hex_=(0, 0), attached_to="", org_type="", mobility=Mobility.FOOT):
    return Unit(uid, Side.AXIS, hex_, (StepRecord("s", 8),), mobility=mobility,
                cpa=cpa, stacking_points=1, oca=2, dca=2, nationality="GE",
                org_type=org_type, attached_to=attached_to)


def _state(units, *, max_turns=1):
    hexes = {u.hex for u in units} | set(LINE)
    tmap = TerrainMap(terrain={h: Terrain.DESERT for h in hexes},
                      hexsides={}, roads=frozenset(), tracks=frozenset(), rails=frozenset())
    return GameState(turn=1, max_turns=max_turns, phase=Phase.RECORD, active_side=Side.AXIS,
                     seed=42, weather="normal", vp=VP(), terrain=tmap, control={},
                     units=tuple(units), target_hex=(13, 0), supplies=(), consumed={},
                     initial_supply={})


def _reach(state, unit, formation=()):
    return tactics.reachable_for(state, unit, frozenset(), frozenset(),
                                 state.living(Side.AXIS), formation=formation)


# --- the rule, in isolation -----------------------------------------------------------------

def test_6_15_a_slow_subsidiary_binds_the_whole_formation():
    """The headline. A fast Parent carrying a slow subsidiary moves at the SLOW one's CPA."""
    parent = _u("P", cpa=40, org_type="ge_battle_group")
    slow = _u("C", cpa=10, attached_to="P")
    state = _state([parent, slow])

    alone = _reach(state, parent)
    bound = _reach(state, parent, formation=[slow])

    assert len(bound) < len(alone), (
        "a Parent carrying a CPA-10 subsidiary must not move on its own CPA of 40 ([6.15])")


def test_6_15_the_formation_reaches_exactly_as_far_as_its_slowest_component():
    """Not merely "less" -- the rule names the value: "that of its lowest-CPA unit"."""
    parent = _u("P", cpa=40, org_type="ge_battle_group")
    slow = _u("C", cpa=10, attached_to="P")
    state = _state([parent, slow])

    bound = _reach(state, parent, formation=[slow])
    solo_slow = _reach(_state([_u("P", cpa=10, org_type="ge_battle_group")]),
                       _u("P", cpa=10, org_type="ge_battle_group"))

    assert set(bound) == set(solo_slow)


def test_6_15_a_faster_subsidiary_never_speeds_a_slow_parent_up():
    """"regardless of the CPA of any higher-CPA units" -- the rule is a floor, never a boost."""
    parent = _u("P", cpa=10, org_type="ge_battle_group")
    fast = _u("C", cpa=40, attached_to="P")
    state = _state([parent, fast])

    assert set(_reach(state, parent, formation=[fast])) == set(_reach(state, parent))


def test_6_15_the_slowest_of_several_binds_not_merely_the_first():
    parent = _u("P", cpa=40, org_type="ge_battle_group")
    mid = _u("C1", cpa=25, attached_to="P")
    slow = _u("C2", cpa=10, attached_to="P")
    state = _state([parent, mid, slow])

    both = _reach(state, parent, formation=[mid, slow])
    only_mid = _reach(state, parent, formation=[mid])

    assert len(both) < len(only_mid), "the minimum must be over the WHOLE formation"


def test_6_15_an_empty_formation_changes_nothing():
    """The default, and the byte-identity guarantee: a counter with nothing attached -- which is
    every counter in every scenario with no live organization tree -- must compute exactly the
    reach it computed before this rule existed."""
    lone = _u("P", cpa=40)
    state = _state([lone])
    assert set(_reach(state, lone, formation=())) == set(_reach(state, lone))


def test_6_15_reaches_the_predecessor_form_too():
    """engine._movement uses reachable_for_prev, not reachable_for. Both must bind, or the rule
    would hold for what a policy is OFFERED and not for what the engine ACCEPTS."""
    parent = _u("P", cpa=40, org_type="ge_battle_group")
    slow = _u("C", cpa=10, attached_to="P")
    state = _state([parent, slow])

    bound, _prev = tactics.reachable_for_prev(state, parent, frozenset(), frozenset(),
                                              state.living(Side.AXIS), formation=[slow])
    assert set(bound) == set(_reach(state, parent, formation=[slow]))


# --- the wiring: the engine really binds a carried formation ---------------------------------

class _MovePolicy(ScriptedPolicy):
    """Issues one MoveOrder on Game-Turn 1 stage 1 and nothing after."""

    def __init__(self, order, attacker=Side.AXIS):
        super().__init__(attacker)
        self._order = order
        self._fired = False

    def movement(self, state, side):
        if side != Side.AXIS or self._fired or state.stage != 1:
            return []
        self._fired = True
        return [self._order]


def test_the_engine_rejects_a_move_the_formations_slowest_component_cannot_make():
    """THE DRIVER TEST. Without this, [6.15] would be one more piece of correct machinery that
    nothing consults -- the exact failure mode this port keeps rediscovering.

    The destination is chosen by measurement, not by hand: a hex the bare CPA-40 Parent reaches
    and a CPA-10 unit does not. The Parent is ordered there while carrying its CPA-10 subsidiary,
    and the engine must refuse.
    """
    parent = _u("P", cpa=40, org_type="ge_battle_group")
    slow = _u("C", cpa=10, attached_to="P")
    state = _state([parent, slow])

    fast_only = set(_reach(state, parent)) - set(_reach(state, parent, formation=[slow]))
    assert fast_only, "test scaffold: the two CPAs must actually differ in reach"
    target = min(fast_only)

    res = engine.run(state, _MovePolicy(MoveOrder("P", target)), ScriptedPolicy(Side.AXIS))

    moved = [e for e in res.events
             if e.kind == EventKind.UNIT_MOVED and e.payload.get("unit_id") == "P"]
    rejected = [e for e in res.events
                if e.kind == EventKind.ORDER_REJECTED and e.payload.get("unit_id") == "P"]

    assert not moved, (
        f"the formation moved to {target}, which its CPA-10 subsidiary cannot reach ([6.15])")
    assert rejected, "the order was neither carried out nor rejected -- it vanished"


def test_the_engine_still_allows_what_the_slowest_component_can_make():
    """The other half, so the guard is not merely a blanket refusal."""
    parent = _u("P", cpa=40, org_type="ge_battle_group")
    slow = _u("C", cpa=10, attached_to="P")
    state = _state([parent, slow])

    reachable = set(_reach(state, parent, formation=[slow])) - {parent.hex}
    assert reachable, "test scaffold: the bound formation must still be able to move somewhere"
    target = min(reachable)

    res = engine.run(state, _MovePolicy(MoveOrder("P", target)), ScriptedPolicy(Side.AXIS))

    moved = [e for e in res.events
             if e.kind == EventKind.UNIT_MOVED and e.payload.get("unit_id") == "P"]
    assert moved, f"the formation was refused {target}, which its slowest component can reach"
    assert tuple(res.final.unit("C").hex) == tuple(target), (
        "[19.12] the subsidiary rides inside its Parent's counter and must arrive with it")
