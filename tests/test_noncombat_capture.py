"""[10.29] A NON-COMBAT COUNTER WITH NO STRENGTH, LEFT ALONE IN FRONT OF THE ENEMY, IS CAPTURED.

Verbatim off a 300-dpi render of PDF p.18 (the page prints its own folio 18), read character by
character:

    [10.29] "Truck Convoys may not enter an Enemy ZOC unless such hex is already occupied by a
            Friendly combat unit. Furthermore, no non-combat unit (i.e., bare HQ's, Engineers, Air
            Squadron Ground Support Units, etc.) may ever enter an unoccupied hex in an enemy ZOC
            voluntarily. If such a unit is alone in an Enemy ZOC at any time during the Enemy
            Movement/Combat Phase and it has no strength of any type, such Friendly non-combat unit
            is Captured."

THE HOLE IT FILLS. Two engine rules were each independently correct and together produced a hex
nobody could resolve:

  * tactics.enemy_zoc_and_occupied bars entry on ANY living enemy unit, combat or not. That is
    [8.13] word for word (PDF p.14): "A unit may never enter a hex containing an enemy unit (see,
    however, Case 27.4)." No qualifier -- so this stays, and no test here weakens it.
  * engine._record_control banks a hex only for COMBAT units, and campaign_victory._occupier asks
    [64.73]'s own question ("a combat unit of at least 1 TOE Strength in the hex"). Also right:
    [10.11] gives a bare HQ no ZOC and [10.15] gives a sub-10-point stack none either.

So a hex whose last survivor was a valueless non-combat counter could be neither ENTERED nor
FLIPPED, and it stayed that way: a 0-rated defender cannot shed a step (engine._absorb_losses,
"Units with no rating cannot absorb") and never runs out of Close-Assault ammunition, so [15.15]
never fires either. Measured over 32 full campaigns: 281 such stalemates, 2,830 stage-closes, one
of them 319 stages of a 332-stage war. THE BOOK IS NOT SILENT ABOUT THIS -- it legislates the same
doctrine four times ([3.36] bare HQs, [10.29] any strengthless non-combat unit, [35.12] SGSUs,
[22.63] Tank Delivery Squadrons), and the engine implemented none of them.

WHAT IS BUILT HERE IS [10.29] AND ONLY [10.29] -- the one clause whose trigger the engine can
already compute exactly, from the same ZOC map movement is gated on. Two readings are flagged as
judgement calls and asserted below so they cannot drift:

  * "alone" = with no FRIENDLY COMBAT UNIT in the hex, not "with no other counter at all". 10.29's
    own preceding sentence contrasts an "unoccupied hex" with one "already occupied by a Friendly
    combat unit", and the book's three sibling clauses say combat unit outright -- [3.36] "in a hex
    without any combat units", [35.12] "no Friendly combat unit stacked with it", [22.63] "alone in
    a hex". This is also exactly [10.26]'s negation condition, so a counter under guard is not in a
    ZOC to be alone in.
  * "at any time during the Enemy Movement/Combat Phase" is sampled at the three beats where the
    phasing player's board can have changed -- after movement (Reaction 8.5 rides inside it), after
    combat (retreat and advance-after-combat) and after the 8.2 exploitation pulse. That is exactly
    where _capture_dumps already sweeps, and for the same reason: a unit arrives through five
    different doors and the rule does not care which.

NOT BUILT, AND WHY. [3.36] captures an HQ that "has no combat values, either with or without
parentheses" -- and this engine has no such HQ to capture: data/unit_stats.json prints "dca": 1 on
every hq / hq_engineer row while calling them chart row 'a', and that row prints a DASH in the Close
Assault column on all three national charts, each re-rendered at 300 dpi and read for this file:
German [4.46c] PDF p.137, Commonwealth [4.46a] p.133, Italian [4.46b] p.136 (printed a* there).
That 1 is not on the chart.
Until it is transcribed, 3.36's population is empty and 10.29 (whose condition is strictly wider --
"no strength of ANY type") covers every counter 3.36 would reach. THE TWO CHANGES ARE COUPLED: fix
that dca without landing this rule and every bare HQ becomes as unkillable as the SGSU was.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import supply
from game.engine import _capture_noncombat, _Run, run
from game.events import Control, EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import MoveOrder, Policy
from game.state import GameState, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain

LINE = ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0))


def _div(uid, side, hx, **kw) -> Unit:
    """A division that exerts a ZOC: >1 Stacking Point (10.11) and >=10 raw defensive
    Close-Assault Points (10.15)."""
    return Unit(uid, side, hx, (StepRecord("in", 4),), mobility=Mobility.FOOT,
                cpa=30, stacking_points=5, oca=6, dca=8, fuel=500, **kw)


def _sgsu(uid, side, hx) -> Unit:
    """A Squadron Ground Support Unit: is_combat False and no strength of any type (35.12)."""
    return Unit(uid, side, hx, (StepRecord("sq", 1),), mobility=Mobility.FOOT,
                cpa=10, stacking_points=1, oca=0, dca=0, is_combat=False)


def _hq(uid, side, hx) -> Unit:
    """An HQ counter that DOES print a rating -- the Italian [4.46b] row 'f' shape, Close Assault
    0/(1). It has strength of a type, so 10.29 does not reach it: the book says assault it."""
    return Unit(uid, side, hx, (StepRecord("hq", 1),), mobility=Mobility.FOOT,
                cpa=20, stacking_points=1, oca=0, dca=1, is_combat=False)


def _state(units, *, control=None, max_turns=1) -> GameState:
    # The 49.14 fuel tanks the divisions carry are an on-hand supply surface, so they must be
    # credited into initial_supply at t0 exactly as game.scenario does (invariants._check_conservation).
    return GameState(
        turn=1, max_turns=max_turns, phase=Phase.WEATHER, active_side=Side.SYSTEM, seed=7,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={c: Terrain.CLEAR for c in LINE}),
        control=dict(control or {}), units=tuple(units), target_hex=LINE[-1],
        supplies=(), consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: sum(getattr(u, c.lower(), 0) for u in units)
                        for c in supply.COMMODITIES})


def _captured(r) -> list[str]:
    return [e.payload["unit_id"] for e in r.events
            if e.kind == EventKind.STEP_LOST and e.payload.get("role") == "captured"]


# --- the rule itself ----------------------------------------------------------------------------

def test_a_valueless_non_combat_counter_alone_in_an_enemy_zoc_is_captured():
    # The Axis division at (0,0) projects a ZOC into (1,0); the Commonwealth SGSU standing there
    # has no friendly combat unit with it and no strength of any type.
    r = _Run(_state([_div("AX-DIV", Side.AXIS, (0, 0)), _sgsu("AL-SGSU", Side.ALLIED, (1, 0))]))
    _capture_noncombat(r, Side.AXIS)
    assert _captured(r) == ["AL-SGSU"]
    assert not r.state.unit("AL-SGSU").alive


def test_capture_needs_the_zoc_and_not_mere_existence():
    # Two hexes away is out of the ZOC entirely -- nothing happens.
    r = _Run(_state([_div("AX-DIV", Side.AXIS, (0, 0)), _sgsu("AL-SGSU", Side.ALLIED, (2, 0))]))
    _capture_noncombat(r, Side.AXIS)
    assert _captured(r) == []
    assert r.state.unit("AL-SGSU").alive


def test_a_friendly_combat_unit_in_the_hex_means_the_counter_is_not_alone():
    # "alone" (10.29) / "in a hex without any combat units" (3.36) / "no Friendly combat unit
    # stacked with it" (35.12) -- and it is [10.26]'s negation besides: a guarded counter is not
    # in an un-negated Enemy ZOC at all.
    r = _Run(_state([_div("AX-DIV", Side.AXIS, (0, 0)),
                     _sgsu("AL-SGSU", Side.ALLIED, (1, 0)),
                     _div("AL-GUARD", Side.ALLIED, (1, 0))]))
    _capture_noncombat(r, Side.AXIS)
    assert _captured(r) == []
    assert r.state.unit("AL-SGSU").alive


def test_a_counter_that_prints_a_rating_has_strength_of_a_type_and_is_not_captured():
    # 10.29 captures only a counter that "has no strength of any type". An HQ printing Close
    # Assault 0/(1) -- the Italian [4.46b] row 'f', which is what garrisons Bardia -- has one, and
    # the book's answer to it is a Close Assault, not a capture.
    r = _Run(_state([_div("AX-DIV", Side.AXIS, (0, 0)), _hq("AL-HQ", Side.ALLIED, (1, 0))]))
    _capture_noncombat(r, Side.AXIS)
    assert _captured(r) == []
    assert r.state.unit("AL-HQ").alive


def test_a_combat_unit_is_never_captured_by_10_29():
    # 10.29's subject is "no non-combat unit (i.e., bare HQ's, Engineers, Air Squadron Ground
    # Support Units, etc.)". A combat unit is fought, not collected -- even a 0-rated one.
    #
    # WHICH GUARD ACTUALLY HOLDS THIS, measured rather than assumed: NOT the `not u.is_combat`
    # filter. Neutering that filter alone leaves all ten tests in this file passing, because a
    # combat unit is always its own [10.26] negator -- it is in `living(victim)` and it is a combat
    # unit, so its hex is in `guarded` by construction and it can never be alone. The two clauses
    # overlap exactly on this population. Both are kept because both are the rule (10.29's subject
    # AND its "alone" condition), and the filter is also what keeps the sweep off every combat
    # counter on the board; but this assertion is enforced by `guarded`, and it fails only when
    # BOTH are dropped. Recorded here so the line is not mistaken for a load-bearing one.
    zeroed = replace(_div("AL-ZERO", Side.ALLIED, (1, 0)), oca=0, dca=0)
    r = _Run(_state([_div("AX-DIV", Side.AXIS, (0, 0)), zeroed]))
    _capture_noncombat(r, Side.AXIS)
    assert _captured(r) == []
    assert r.state.unit("AL-ZERO").alive


def test_it_is_the_enemy_movement_combat_phase_so_the_phasing_side_loses_nothing():
    # "at any time during the ENEMY Movement/Combat Phase" -- a side does not capture its own
    # counters, and a side's own counters are not at risk in its own phase. Both stacks stand in
    # the other's ZOC here; only the non-phasing side's counter goes.
    r = _Run(_state([_div("AX-DIV", Side.AXIS, (0, 0)), _sgsu("AX-SGSU", Side.AXIS, (1, 0)),
                     _div("AL-DIV", Side.ALLIED, (2, 0)), _sgsu("AL-SGSU", Side.ALLIED, (1, 0))]))
    _capture_noncombat(r, Side.AXIS)
    assert _captured(r) == ["AL-SGSU"]
    assert r.state.unit("AX-SGSU").alive


def test_a_stack_of_valueless_counters_goes_together_in_id_order():
    # Determinism: the sweep is ordered by unit id, like _capture_dumps' sorted(supplies).
    r = _Run(_state([_div("AX-DIV", Side.AXIS, (0, 0)),
                     _sgsu("AL-SGSU-B", Side.ALLIED, (1, 0)),
                     _sgsu("AL-SGSU-A", Side.ALLIED, (1, 0))]))
    _capture_noncombat(r, Side.AXIS)
    assert _captured(r) == ["AL-SGSU-A", "AL-SGSU-B"]


def test_a_lone_battalion_that_exerts_no_zoc_captures_nothing():
    # 10.11/10.15: a single 1-Stacking-Point counter projects no ZOC, so there is no ZOC to be
    # alone in. The capture is keyed on the SAME control map movement is gated on, never on
    # adjacency -- which is also why [35.12]'s mere-adjacency trigger is NOT built here.
    lone = replace(_div("AX-BN", Side.AXIS, (0, 0)), stacking_points=1)
    r = _Run(_state([lone, _sgsu("AL-SGSU", Side.ALLIED, (1, 0))]))
    _capture_noncombat(r, Side.AXIS)
    assert _captured(r) == []


# --- the freeze, end to end, through engine.run() -------------------------------------------------

class _March(Policy):
    """Orders one unit into one hex, every stage, forever."""

    def __init__(self, unit_id: str, dest):
        self._unit_id, self._dest = unit_id, dest

    def movement(self, state, side):
        u = state.unit(self._unit_id)
        return [MoveOrder(self._unit_id, self._dest)] if u is not None and u.side == side else []

    def combat(self, state, side):
        return []


def _freeze_board():
    """(0,0) an Axis division; (1,0) the lone Commonwealth SGSU it is about to place in its ZOC;
    (4,0) a Commonwealth division three hexes clear of the whole affair, so that taking the SGSU
    does not simply annihilate the Commonwealth and end the run before Stage 2."""
    return _state([_div("AX-DIV", Side.AXIS, (0, 0)),
                   _sgsu("AL-SGSU", Side.ALLIED, (1, 0)),
                   _div("AL-DIV", Side.ALLIED, (4, 0))],
                  control={(1, 0): Control.ALLIED})


def test_the_bare_hq_freeze_clears_the_hex_is_entered_and_the_ground_changes_hands():
    """THE INCIDENT, end to end. Before this rule the Axis division could not enter (8.13, and
    rightly), could not kill the counter (a 0-rated defender absorbs nothing), and could not flip
    the hex (10.11/64.73), so (1,0) stayed Commonwealth-held-by-nobody for the rest of the war.

    Now: Operations Stage 1 the move is refused because the hex is occupied -- 8.13 is untouched --
    and the sweep captures the counter that made it occupied. Stage 2 the division walks in and
    _record_control banks the ground."""
    march = _March("AX-DIV", (1, 0))
    res = run(_freeze_board(), march, march)
    caught = [e for e in res.events
              if e.kind == EventKind.STEP_LOST and e.payload.get("role") == "captured"]
    assert [e.payload["unit_id"] for e in caught] == ["AL-SGSU"]
    assert caught[0].stage == 1, "the counter is taken in the stage the enemy came adjacent"
    assert not res.final.unit("AL-SGSU").alive
    assert res.final.unit("AX-DIV").hex == (1, 0), "the hex is enterable once it is empty"
    assert res.final.control_of((1, 0)) == Control.AXIS, "and the ground finally changes hands"


def test_entry_into_an_occupied_hex_stays_barred_while_the_counter_stands():
    """[8.13] IS NOT WEAKENED BY THIS SLICE, and this test exists to keep it that way. The Axis
    division may not step onto the SGSU; it takes the hex only after the counter is gone. Run with
    the capture beat monkeypatched out, the division stays put for all three Operations Stages."""
    import game.engine as engine
    march = _March("AX-DIV", (1, 0))
    real = engine._capture_noncombat
    try:
        engine._capture_noncombat = lambda r, side: None
        res = run(_freeze_board(), march, march)
    finally:
        engine._capture_noncombat = real
    assert res.final.unit("AX-DIV").hex == (0, 0)
    assert res.final.unit("AL-SGSU").alive
    assert any(e.kind == EventKind.ORDER_REJECTED for e in res.events)
