"""THE 10TH ARMY CULMINATES -- AND THE DELTA IS HELD.

Measured before this suite: an Axis combat unit stood on AL-Alexandria -- the Commonwealth's
bottomless base dump -- on GAME-TURN 4, in 5/5 seeds, and six Italian battalions sat on it at GT6.
Graziani's 10th Army was in the Nile Delta in three weeks. Historically it halted at SIDI BARRANI
and sat there for three months, because it could not supply itself one mile further.

Three rules were missing, and not one of them is a magnitude we invented:

  * [25.12] "Cairo and Alexandria are Level 3 fortifications." The Delta carried fort level ZERO.
    The only unfortified major cities on the map were the two the whole war was fought for.
  * [64.71] the Axis wins the WAR OUTRIGHT by occupying every hex of Alexandria AND Cairo -- and
    the Commonwealth left all seven of them EMPTY for 111 Game-Turns, because they are not 64.73
    victory cities and the standing garrison order only ever held those.
  * [13.21] Retreat Before Assault is VOLUNTARY movement -- a SECOND door out of a city, which the
    standing garrison order never watched. Rule 15.82 forbids EVICTING a garrison from a major
    city; nothing forbade the garrison from politely leaving. Measured: the Commonwealth garrisoned
    all seven Delta hexes by GT3 exactly as ordered, the Italians closed up and announced an
    assault on GT4, the elastic desert defense slipped BR-1-Ches and BR-2-KOR out of Alexandria to
    make room -- and six Italian battalions walked into the empty city on GT5.

AND ONE RULE MEASURED AND REJECTED, recorded so it is not re-invented: a WELL-CONTROL gate (deny a
side any water source standing on a hex the enemy controls, 54.41). See the note in
game.supply.reachable_supplies. It changes NOTHING about the Delta -- a garrisoned hex is already
enemy-OCCUPIED, which the 32.16 trace already blocks -- and it is perverse, because control flips to
whoever last STOOD on a hex, so one Italian column driving through El Daba poisons the well against
the Eighth Army for the rest of the war.
"""
from __future__ import annotations

import hashlib

import pytest

from game.campaign_claim import (delta_claims, delta_garrison, delta_hexes,
                                 hold_garrisons)
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.campaign_victory import CampaignVictory
from game.engine import determinism_signature, run
from game.events import Side
from game.policy import MoveOrder, ScriptedPolicy
from game.scenario import campaign, rommels_arrival, siege_of_tobruk
from game.terrain import Terrain
from baselines import BENCHMARKS                                    # noqa: E402


@pytest.fixture(scope="module")
def board():
    return campaign(seed=1941)


# --- [25.12] the Delta is a Level 3 fortification -------------------------------------------

def test_delta_is_a_level_3_fortification(board):
    """[25.12] 'Each major city on the game-map is a Level 2 fortification. Cairo and Alexandria
    are Level 3 fortifications.' Every hex of both -- the 64.71 objective enumerates them."""
    assert delta_hexes(board), "the campaign must carry the 64.71 objective"
    for ax in delta_hexes(board):
        assert board.fort_level(ax) == 3, f"{ax} is not a Level 3 fortification (25.12)"
        assert board.terrain.terrain[ax] == Terrain.MAJOR_CITY


def test_tobruk_and_bardia_keep_their_level_2(board):
    """[25.12]: every OTHER major city stays Level 2. The Delta is the exception, not a re-grade."""
    from game.coords import parse, to_axial
    for lbl in ("C4807", "C4321"):                      # Tobruk, Bardia
        assert board.fort_level(to_axial(parse(lbl))) == 2


# --- [64.71] the Delta standing order -------------------------------------------------------

def test_the_commonwealth_garrisons_every_hex_of_the_delta(board):
    """[64.71] The Axis auto-wins by occupying every hex of Alexandria AND Cairo. Leaving them
    empty is not a strategy, it is a way to lose the war -- so between them the standing order and
    the units already there cover all seven, one unit apiece.

    RESTATED 2026-08-04, CAUSE [4.44B] -- and the restatement is the SAME CLAIM asked correctly.
    The old form said "at t0 all seven stand empty, so all seven are claimed", which was a fact
    about an INCOMPLETE order of battle, not about the rule: [60.41] Commonwealth Initial
    Deployment prints 'Alexandria (E3613 &/or 3714): HQ: 2nd New Zealand Division; 4th NZ Bde
    (2 NZ); 27th NZ MG Bn (2 NZ); 2nd NZ Cavalry (2 NZ); 4th NZ Field Arty Regt (2 NZ)', and with
    those counters seeded the Alexandria hex E3613 is garrisoned from Game-Turn 1 by the book's own
    setup. delta_claims deliberately SKIPS an occupied hex (delta_garrison pins its holder instead),
    so asserting "every hex is claimed" would now be asserting that the standing order sends a
    second battalion to a hex the 2nd New Zealand Division is already standing on. What 64.71
    actually requires is that no hex is left OPEN, and that is what is asserted."""
    plan = delta_claims(board, Side.ALLIED)
    garrisoned = {ax for ax in delta_hexes(board)
                  if any(u.side == Side.ALLIED and u.alive and u.is_combat and u.strength >= 1
                         for u in board.units_at(ax))}
    assert {c.city for c in plan} | garrisoned == set(delta_hexes(board))
    assert not ({c.city for c in plan} & garrisoned), "a garrisoned hex must not also be claimed"
    assert len({c.unit_id for c in plan}) == len(plan), "one unit may not hold two hexes"
    # ...and the one hex the book itself garrisons is Alexandria, by the counters [60.41] names.
    from game.coords import parse, to_axial
    assert garrisoned == {to_axial(parse("E3613"))}
    assert delta_garrison(board, Side.ALLIED)      # the 64.71 pin is on the holder it found there


def test_the_delta_order_never_impounds_the_armour(board):
    """Base defence is a job for base troops. is_tank sorts BEFORE distance, so a tank is drafted
    into the Delta only if no infantryman anywhere could stand there instead -- measured with
    distance first, the standing order quietly impounded 2-RTR and 7-RTR in Cairo for the war."""
    for c in delta_claims(board, Side.ALLIED):
        assert not board.unit(c.unit_id).is_tank


def test_the_axis_never_garrisons_the_delta(board):
    """It is the Axis OBJECTIVE, not something the Axis holds."""
    assert delta_claims(board, Side.AXIS) == ()
    assert delta_garrison(board, Side.AXIS) == set()


def test_a_unit_on_a_delta_hex_is_pinned_there(board):
    """The dual of the claim: the unit that arrives never marches away again (hold_garrisons).

    RESTATED 2026-08-04, CAUSE [4.44B]. The hex this used to inject into -- delta_hexes()[0], the
    Alexandria hex E3613 -- is no longer empty: [60.41] deploys the 2nd New Zealand Division there
    and the pass that seeded it put four of its battalions on the hex. delta_garrison keeps ONE
    holder per hex (min by (is_tank, id)), so the injected battalion was simply not the one chosen
    and the test was asking whether a unit is pinned on a hex where a DIFFERENT unit is pinned. It
    injects into an unoccupied Delta hex instead, which is the case the test was written for; the
    already-garrisoned hex is asserted beside it, so both halves of the standing order are covered
    rather than one being traded for the other."""
    from dataclasses import replace
    empty = next(ax for ax in delta_hexes(board)
                 if not any(u.side == Side.ALLIED and u.alive and u.is_combat and u.strength >= 1
                            for u in board.units_at(ax)))
    briton = next(u for u in board.living(Side.ALLIED) if u.is_combat and not u.is_tank)
    held = replace(board, units=tuple(replace(u, hex=empty) if u.id == briton.id else u
                                      for u in board.units))
    assert briton.id in delta_garrison(held, Side.ALLIED)
    assert hold_garrisons([MoveOrder(briton.id, (27, 100))], held, Side.ALLIED) == []
    # the hex [60.41] garrisons for us pins its own holder on the untouched board
    pinned = delta_garrison(board, Side.ALLIED)
    assert len(pinned) == 1 and hold_garrisons(
        [MoveOrder(next(iter(pinned)), (27, 100))], board, Side.ALLIED) == []


def test_delta_helpers_are_inert_without_a_campaign_victory():
    """Every helper must be safe to call in a scenario carrying no 64.71 objective -- which is what
    keeps the byte-locked benchmarks untouched."""
    board = rommels_arrival(seed=42)
    assert not isinstance(board.victory, CampaignVictory)
    assert delta_hexes(board) == ()
    assert delta_claims(board, Side.ALLIED) == ()
    assert delta_garrison(board, Side.ALLIED) == set()


# --- [13.21] the other door out of a city ---------------------------------------------------

def test_a_garrison_does_not_slip_out_of_its_city_before_an_assault():
    """Retreat Before Assault is VOLUNTARY movement (13.21) -- the second door, and the one the
    Delta actually fell through. A unit under a standing garrison order declines it, on BOTH
    sides: the Axis opens the war standing on Tobruk and Bardia."""
    from dataclasses import replace
    st = campaign(seed=1941)
    alex = delta_hexes(st)[0]
    briton = next(u for u in st.living(Side.ALLIED) if u.is_combat and not u.is_tank)
    held = replace(st, units=tuple(replace(u, hex=alex) if u.id == briton.id else u
                                   for u in st.units))
    pol = CampaignCommonwealthPolicy()
    rba = pol.retreat_before_assault(held, Side.ALLIED, frozenset({briton.id}))
    assert all(o.unit_id != briton.id for o in rba), \
        "the Delta garrison slipped out of Alexandria before an assault"


# --- the gate --------------------------------------------------------------------------------

def test_the_10th_army_is_not_in_the_delta_in_three_weeks():
    """THE GATE, asked where it was measured to fail. Graziani stood on Alexandria on GAME-TURN 4
    in 5/5 seeds and had six battalions there by GT6, so twelve Game-Turns is a decisive window --
    and a cheap one. No Axis combat unit may stand on a hex of Alexandria or Cairo, and the Delta
    must be HELD, which is what denies it."""
    res = run(campaign(seed=1941, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    st = res.final
    delta = set(delta_hexes(st))
    squatters = [(u.id, u.hex) for u in st.living(Side.AXIS)
                 if u.is_combat and u.strength >= 1 and u.hex in delta]
    assert not squatters, f"the 10th Army is in the Nile Delta by GT12: {squatters}"
    garrisoned = {ax for ax in delta
                  if any(u.side == Side.ALLIED and u.is_combat and u.strength >= 1
                         for u in st.units_at(ax))}
    assert garrisoned == delta, f"the Delta is not held: {delta - garrisoned} stand empty"


# --- the hard constraint ---------------------------------------------------------------------

def test_rommel_and_siege_stay_byte_identical():
    """Every rule in this suite is campaign-scoped BY CONSTRUCTION: the Delta helpers key off the
    64.71 objective, which only CampaignVictory carries and the two benchmark scenarios do not.
    They must not move one byte."""
    axis = ScriptedPolicy(Side.AXIS)
    baselines = BENCHMARKS            # tests/baselines.py -- the ONE place, and why they moved
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        res = run(build(seed=42), axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baselines[name], f"{name} byte-identity broken: {sig} != {baselines[name]}"
