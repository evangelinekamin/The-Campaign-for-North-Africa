"""Block 7.C -- MAKING [15.53] ACTUALLY FIRE IN CAMPAIGN COMBAT.

Block B (test_organization_seeding) seeded the [4.45] formation tree so divisions EXIST; Gate 7A
then found it INERT in play -- no policy attached anything, so no formation ever concentrated and the
[15.53] Organization Size chart fired its >=2-SP tiers ZERO times in 111 turns. This block drives it:

  * concentrate_formations (game.campaign_policy) is the Reorganization-Segment standing order both
    campaign policies now issue -- 19.4/19.12 attach of each assigned unit that stands in its Parent's
    hex, plus the 19.43 reconciliation of any link a retreat has left stale, under a 9.14 stacking gate;
  * a concentrated formation then MOVES as one counter (engine._co_located_subtree, 19.12) so it
    reaches combat still concentrated;
  * organization.size and engine._parents_of read the fold from PHYSICAL co-location, so a split
    formation counts honestly and never mis-fires;
  * and the close-assault resolver records the Organization-Size tier in COMBAT_RESOLVED.

The proof at the foot of this file fights a real campaign and shows the tier fire a non-zero number
of times. No Kampfgruppe is formed here -- the dynamic 19.71 Battle Group is flagged and deferred as
speculative AI (see the block report); the setup-tree firing is the core, and this is it.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import engine, organization
from game.campaign_policy import (CampaignAxisPolicy, CampaignCommonwealthPolicy,
                                  concentrate_formations)
from game.engine import run
from game.events import EventKind, Phase, Side
from game.policy import MoveOrder, ScriptedPolicy
from game.scenario import campaign
from game.state import GameState, StepRecord, Unit, VP
from game.movement import TerrainMap
from game.terrain import Mobility, Terrain


# --- a tiny synthetic board, for the mechanics that do not need a whole campaign -----------------

def _u(uid, hex_, **kw):
    kw.setdefault("nationality", "IT")
    return Unit(uid, kw.pop("side", Side.AXIS), hex_, (StepRecord("s", kw.pop("strength", 8)),),
                mobility=Mobility.FOOT, cpa=kw.pop("cpa", 20), stacking_points=kw.pop("sp", 1),
                oca=kw.pop("oca", 2), dca=kw.pop("dca", 2), **kw)


def _state(units, *, turn=1, max_turns=1):
    pts = {u.hex for u in units} | {(0, 0), (9, 9)}
    box = {(rr, cc) for rr in range(min(p[0] for p in pts) - 1, max(p[0] for p in pts) + 2)
           for cc in range(min(p[1] for p in pts) - 1, max(p[1] for p in pts) + 2)}
    terrain = TerrainMap(terrain={h: Terrain.DESERT for h in box},
                         hexsides={}, roads=frozenset(), tracks=frozenset(), rails=frozenset())
    return GameState(
        turn=turn, max_turns=max_turns, phase=Phase.RECORD, active_side=Side.AXIS, seed=42,
        weather="normal", vp=VP(), terrain=terrain, control={}, units=tuple(units),
        target_hex=(9, 9), supplies=(), consumed={}, initial_supply={}, replacement_pool={})


# --- concentrate_formations: the Reorganization-Segment standing order ---------------------------

def test_concentrate_attaches_a_colocated_seeded_regiment():
    # The 62nd Marmarica's 115th Infantry Regiment opens the war with all three of its battalions
    # stacked on its own hex ([4.45]); the standing order folds them into it (19.4/19.12).
    orders = concentrate_formations(campaign(seed=1941), Side.AXIS)
    attached = {(o.unit_id, o.parent_id) for o in orders if o.kind == "attach"}
    for bn in ("IT-I/115---62-Marm", "IT-II/115---62-Marm", "IT-III/115---62-Marm"):
        assert (bn, "IT-115---62-Marm") in attached


def test_concentrate_reconciles_a_link_a_split_left_stale():
    # A battalion still bound to its regiment by an attached_to link but standing in another hex --
    # a formation a retreat or Reaction split -- is DETACHED (19.43), so the map tree stays honest to
    # where the counters actually stand. (Voluntary movement never causes this; the carry keeps them
    # together. It is the involuntary paths this reconciles.)
    state = campaign(seed=1941)
    units = tuple(replace(u, attached_to="IT-115---62-Marm", hex=(40, 72))
                  if u.id == "IT-I/115---62-Marm" else u for u in state.units)
    orders = concentrate_formations(replace(state, units=units), Side.AXIS)
    assert any(o.kind == "detach" and o.unit_id == "IT-I/115---62-Marm" for o in orders)


def test_concentrate_respects_the_9_14_stacking_gate():
    # A super-regiment HQ (SP 3) counts 0 while bare but its full 3 once a unit attaches (9.12/9.13),
    # so folding a single battalion into it while four loose units share the hex would make 3+0+4 = 7,
    # over the [8.37] Desert limit of 6 (data/stacking_limits.json -- restated from the pre-8.37 "3
    # loose units, over the 5-point limit" scenario, which no longer overflows now that the real
    # per-terrain limit, 6, replaces the old flat DEFAULT_HEX_LIMIT=5 placeholder: rule 5, restate
    # don't weaken). The formation may not concentrate here yet (9.14/9.31): no attach.
    H = (2, 2)
    hq = _u("SR", H, org_type="it_tank_regiment_super")
    bn = _u("SR-I", H, assigned_to="SR")
    loose = [_u(f"X{i}", H) for i in range(4)]
    orders = concentrate_formations(_state([hq, bn, *loose]), Side.AXIS)
    assert not [o for o in orders if o.kind == "attach"]


# --- the 19.12 carry: a formation moves as one counter ------------------------------------------

def test_co_located_subtree_is_only_the_units_standing_with_the_parent():
    hq = _u("R", (1, 1), org_type="ge_battle_group", sp=2, is_combat=True, nationality="GE")
    here = _u("R-I", (1, 1), attached_to="R", nationality="GE")
    split = _u("R-II", (7, 7), attached_to="R", nationality="GE")     # stale link: elsewhere
    state = _state([hq, here, split])
    subtree = engine._co_located_subtree(state, hq, engine._attached_index(state))
    assert [u.id for u in subtree] == ["R-I"]                          # the split unit is NOT carried


class _MoveOne(ScriptedPolicy):
    """Issues one MoveOrder for `uid`->`to` on Game-Turn 1 stage 1, then nothing."""
    def __init__(self, uid, to):
        super().__init__(Side.AXIS)
        self._uid, self._to, self._fired = uid, to, False

    def movement(self, state, side):
        if side != Side.AXIS or self._fired or state.stage != 1:
            return []
        self._fired = True
        return [MoveOrder(self._uid, self._to)]


def test_a_concentrated_formation_moves_as_one_counter():
    # A regiment HQ (combat, SP 2) with two attached battalions is ordered forward one hex; its
    # counter carries the battalions with it (19.12), so the formation never separates on the march --
    # the thing that makes it arrive at a close assault still concentrated. The battalions are given
    # NO order of their own (19.12: they may not self-move); they move only because the HQ did.
    hq = _u("R", (1, 1), org_type="ge_battle_group", sp=2, is_combat=True, nationality="GE")
    bns = [_u(f"R-{i}", (1, 1), attached_to="R", nationality="GE") for i in range(2)]
    res = engine.run(_state([hq, *bns]), _MoveOne("R", (2, 1)), ScriptedPolicy(Side.AXIS))
    final = res.final
    assert final.unit("R").hex == (2, 1)                              # the HQ advanced
    assert {final.unit("R-0").hex, final.unit("R-1").hex} == {(2, 1)}  # carried with it, one hex


# --- a detached straggler fights at its own size (the co-location distinction, drawn in combat) ---

def test_a_detached_straggler_fights_at_its_own_size_not_folded_to_zero():
    # size() folds an attached unit to zero by its LINK (local, for the per-event stacking invariant),
    # but the close-assault reader tells a genuinely detached straggler -- one whose Parent is NOT
    # among the participants -- apart, so it fights as the battalion it is, not a zero-size company.
    child = _u("R-I", (5, 5), attached_to="R")
    assert organization.combat_size([child]) == 1                      # Parent absent: fights as itself
    # co-located under its Parent it IS the formation (a two-battalion regiment reads the Brigade tier)
    reg = _u("R", (5, 5), org_type="it_infantry_regiment", sp=2)
    kids = [_u("R-I", (5, 5), attached_to="R"), _u("R-II", (5, 5), attached_to="R")]
    assert organization.combat_size([reg, *kids]) == 2


# --- THE PROOF: [15.53] fires in a full campaign ------------------------------------------------

def test_15_53_organization_size_tier_fires_in_a_full_campaign():
    """Gate 7A measured 0 firings of the [15.53] >=2-SP tiers over 111 turns. With the tree driven,
    a real campaign fires them: the close-assault resolver records the Organization-Size tier in
    COMBAT_RESOLVED whenever a FORMATION (>= Brigade / Battle Group) takes part -- absent otherwise,
    which is why the two benchmarks stay byte-identical (test in test_campaign_culmination)."""
    res = run(campaign(seed=1941, max_turns=6), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    tier = [e for e in res.events if e.kind == EventKind.COMBAT_RESOLVED
            and max(e.payload.get("attacker_size", 0), e.payload.get("defender_size", 0)) >= 2]
    assert len(tier) >= 2, "the [15.53] Organization-Size tier is inert -- the setup tree does not fire"
    # Concentration cuts BOTH ways: a formation on the attack (Organization Size FOR the attacker) and
    # a formation standing on the defence (Organization Size AGAINST the attacker) both occur.
    assert any(e.payload["attacker_size"] >= 2 for e in tier)
    assert any(e.payload["defender_size"] >= 2 for e in tier)
