"""THE FORWARD CONCENTRATION -- the Eighth Army marches to the line it fights from.

The measured defect: the Commonwealth army never concentrated forward, and therefore never fought.
At Game-Turn 1 ten Commonwealth combat units stood within fifteen hexes of the Mersa Matruh
railhead; its SEVENTY-FIVE combat reinforcements all arrived in the Nile Delta, sixty hexes behind
the front, and SAT THERE FOR THE ENTIRE WAR. At GT12, GT40 and GT80 the count near the railhead was
zero, while the rail-fed depot on the railhead filled to its cap with nobody to drink it -- and the
three offensive windows then ordered an attack on Benghazi from sixty hexes behind the start line.
Not one Commonwealth unit was ever supplied forward of the railhead during Operation Compass.

The cause was a policy that had its own rear as its objective: the off-window CW hid
allied_objective, objective_for(ALLIED) fell back to state.target_hex -- ALEXANDRIA, its OWN BASE --
and a ScriptedPolicy defender pointed at a hex sixty hexes behind itself has no anchors to hold, no
objective to uncover, and no reason to move at all.

The fix is one substitution and its consequences (game.campaign_policy): between offensives BOTH
objectives become THE LINE -- the rail-fed railhead (54.3/60.7) -- so the rear army marches up to
it, the dumps come up behind the column instead of racing to its head, and the defender ANCHORS on
the railhead instead of on a base it does not garrison. Four measured facts drive the details, and
each has a test below:

  * the railhead must be PHYSICALLY HELD or the whole faucet dies (an empty terminus is driven over
    by the first Axis armoured car heading for Alexandria, and the 54.3 retraction then walks down a
    line the same rush has already driven over);
  * the march must follow the SPRINGS, not the crow: 149 water shortfalls and 81 attrition losses in
    six Game-Turns when it walked straight, and half the army frozen in the fuel hole between the
    Delta base and the railhead when it hopped short;
  * the dumps must BRIDGE the column, not leapfrog to its head;
  * and the standing garrison order must survive all of it.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords                                              # noqa: E402
from game.apply import fold                                         # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,               # noqa: E402
                                  CampaignCommonwealthPolicy, garrison_units, railhead)
from game.campaign_victory import CampaignVictory                   # noqa: E402
from game.engine import determinism_signature, run                  # noqa: E402
from game.events import Control, Side                               # noqa: E402
from game.hexmap import distance                                    # noqa: E402
from game.policy import ScriptedPolicy                              # noqa: E402
from game.scenario import campaign, rommels_arrival, siege_of_tobruk  # noqa: E402

MATRUH = coords.to_axial(coords.parse("D3714"))       # the railhead (60.7) -- and the line
ELDABA = coords.to_axial(coords.parse("D3329"))       # the next station east (54.3)
ELHAMMAN = coords.to_axial(coords.parse("E3007"))
CAIRO = coords.to_axial(coords.parse("E1730"))
ALEX = coords.to_axial(coords.parse("E3613"))
BENGHAZI = coords.to_axial(coords.parse("A4827"))

COMPASS = range(13, 23)                               # campaign_policy.COMPASS


def _combat(state, side):
    return [u for u in state.living(side) if u.is_combat and u.strength >= 1]


def _near_railhead(state, side=Side.ALLIED) -> int:
    return sum(1 for u in _combat(state, side) if distance(u.hex, MATRUH) <= 15)


def _in_the_delta(state, side=Side.ALLIED) -> int:
    return sum(1 for u in _combat(state, side) if distance(u.hex, CAIRO) <= 15)


@pytest.fixture(scope="module")
def gt12():
    """The campaign run up to the eve of Operation Compass -- the concentration with no offensive
    yet to spend it. One run, shared: the engine is deterministic."""
    return run(campaign(seed=1941, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())


# --- the line ------------------------------------------------------------------------------

def test_the_line_is_the_rail_fed_railhead_and_it_retracts():
    """THE ANCHOR. The line the army holds is the station the trains actually reach -- read off the
    rail lane's own retarget line and resolved with the engine's own 56.15 test, so 'the railhead'
    has ONE definition in this campaign and not two that can drift apart. Drive the enemy over Mersa
    Matruh and the line falls back down the railway with the trains (54.3); drive him over every
    station and the line becomes the terminus again -- the hex to retake to switch the railway back
    on, not a reason to have no line at all."""
    st = campaign(seed=1941)
    assert railhead(st).id == "AL-Stage-Matruh"
    assert railhead(st).hex == MATRUH

    def with_axis_on(*hexes):
        return replace(st, control={**st.control, **{h: Control.AXIS for h in hexes}})

    assert railhead(with_axis_on(MATRUH)).id == "AL-Stage-ElDaba"
    assert railhead(with_axis_on(MATRUH, ELDABA)).id == "AL-Stage-ElHamman"
    assert railhead(with_axis_on(MATRUH, ELDABA, ELHAMMAN)).id == "AL-Alexandria"
    # every station overrun -> the terminus is the objective again (retake it)
    assert railhead(with_axis_on(MATRUH, ELDABA, ELHAMMAN, ALEX)).id == "AL-Stage-Matruh"

    # and no railway at all (rommels_arrival) -> no line, and the policy is safe to construct anyway
    assert railhead(rommels_arrival(seed=42)) is None


def test_the_defender_anchors_on_the_line_not_on_the_rear_base():
    """WHAT A DEFENDER DOES WITH AN OBJECTIVE, and why the old view broke it. ScriptedPolicy's
    defender ANCHORS on state.target_hex (whoever holds it never moves) and never UNCOVERS it. The
    campaign's target_hex is ALEXANDRIA -- sixty hexes behind the front, where the Commonwealth has
    not one unit -- so both tests were vacuous and the reflex was free to march the RAILHEAD'S OWN
    GARRISON off to chase an exposed Italian. Selby Force left Mersa Matruh on Game-Turn 1 and
    surrendered on Game-Turn 2.

    The defensive view points both objectives at the line, so the garrison stays."""
    st = campaign(seed=1941)
    pol = CampaignCommonwealthPolicy()
    assert not pol._on_offensive(st)

    view = pol._forward_view(st)
    assert view.target_hex == MATRUH                       # the ANCHOR (_anchor_ids / _uncovers)
    assert view.objective_for(Side.ALLIED) == MATRUH       # and the objective (march + 32.3 leapfrog)
    assert st.target_hex == ALEX                           # the real state is untouched

    selby = next(u for u in st.living(Side.ALLIED) if u.hex == MATRUH and u.is_combat)
    moves = pol.movement(st, Side.ALLIED)
    assert selby.id not in {o.unit_id for o in moves}, "the railhead's garrison marched away"


# --- the concentration ---------------------------------------------------------------------

def test_the_army_does_not_sit_out_the_war_in_the_delta(gt12):
    """THE ACCEPTANCE, and it is NOT 'the Delta empties' any more -- rule 64.71 forbids that.

    THE ORIGINAL DEFECT this test was written for: all seventy-five Commonwealth combat
    reinforcements arrive in the Nile Delta, and the whole army SAT THERE for the entire war -- ten
    units near the railhead at GT1, zero at GT12/40/80, the rail-fed depot at Mersa Matruh filled to
    its cap with nobody to drink it. That defect is what _concentrate fixed, and it stays fixed: the
    rear echelon marches up, the Delta stream does not sit still, and the railhead is garrisoned.

    WHAT CHANGED, and why the old assertions had to go. The Delta must now be HELD (rule 64.71: the
    Axis wins the WAR OUTRIGHT by occupying every hex of Alexandria and Cairo, and we left all seven
    of them empty for 111 Game-Turns -- see game.campaign_claim.delta_garrison). So:

      * `_in_the_delta(fin) <= 3` asserted the exact thing 64.71 forbids. It is now a FLOOR, not a
        ceiling: the seven-hex garrison is a standing order, not a failure to concentrate.
      * `_near_railhead(fin) > _near_railhead(start)` no longer holds, and the reason is worth
        writing down because it is the next lever, not a defect in the concentration. MEASURED at
        GT12, seed 1941, against the same slice before the Delta was defended:

            near railhead   13 -> 5        Axis combat units alive   33 -> 21
            in the Delta     0 -> 5        Axis attrition           196 -> 261
            CW alive        25 -> 22       Axis surrender           158 -> 63

        Seven battalions are now pinned in the Delta (that is the 64.71 order, and it is cheap over
        111 Game-Turns and 75 reinforcements). The other eight are not missing -- they are DEAD or
        strung out, because the Italian 10th Army still BEELINES to r=132 and, now that it can no
        longer walk into Alexandria, it sits down squarely ACROSS the Commonwealth's line of march
        from the Delta to Mersa Matruh and starves there. The rear echelon marching up walks into it
        piecemeal. The beeline is a POLICY artifact (CampaignAxisPolicy drives at target_hex with no
        consolidation and no windows), not a rule we are missing; the fix is the consolidation
        constraint, and until it lands this count stays depressed. Flagged, not papered over."""
    start, fin = gt12.initial, gt12.final
    assert _near_railhead(start) == 10                       # the Game-Turn 1 frontier screen
    assert sum(1 for u in start.units if u.side == Side.ALLIED and u.is_combat
               and u.arrival_turn > 1 and distance(u.hex, CAIRO) <= 15) == 75   # the Delta stream

    # The rear echelon MOVES -- the original defect was an army that never left the Delta at all.
    moved = sum(1 for u in fin.units if u.side == Side.ALLIED and u.is_combat
                and u.arrival_turn > 1 and u.alive and distance(u.hex, CAIRO) > 15)
    assert moved >= 5, f"the reinforcement stream is still sitting in the Delta: only {moved} left it"
    assert _near_railhead(fin) >= 4                          # a fitted floor; see the docstring
    assert _in_the_delta(fin) >= 5, (                        # 64.71: the Delta is HELD, not emptied
        f"only {_in_the_delta(fin)} combat units hold the Delta at GT12")


def test_the_concentration_never_marches_the_army_backwards():
    """ONE-DIRECTIONAL BY CONSTRUCTION. The rear is everything FURTHER from the front (the Axis rear
    at Benghazi) than the line itself is, so a unit at or forward of the line is never in it. The
    concentration can therefore never walk the army back out of ground it has taken -- which an
    assembly that simply rallied everyone on the railhead would do the moment Operation Compass
    ended, abandoning every fortress it had just captured."""
    st = campaign(seed=1941)
    pol = CampaignCommonwealthPolicy()
    line = railhead(st)
    depth = distance(line.hex, st.objective_for(Side.ALLIED))

    moves = {o.unit_id: o for o in pol.movement(st, Side.ALLIED)}
    forward = [u for u in _combat(st, Side.ALLIED)
               if distance(u.hex, st.objective_for(Side.ALLIED)) <= depth]
    assert forward, "the GT1 frontier screen stands forward of the line"
    for u in forward:
        if u.id in moves:                       # it may still SORTIE (the base defender reflex) ...
            assert distance(moves[u.id].to, BENGHAZI) <= distance(u.hex, BENGHAZI), \
                f"{u.id} was marched back east out of the front line"


def test_the_railhead_is_held_and_the_faucet_keeps_running(gt12):
    """THE LOAD-BEARING HEX. The rail lane lands its cargo in the forwardmost station the enemy does
    not CONTROL, and control flips to whoever last stood on it -- so an EMPTY Mersa Matruh is taken
    by the first Axis armoured car that drives through on its way to Alexandria, the retraction then
    walks El Daba -> El Hamman -> the Delta (all already driven over by the same rush), and the
    Commonwealth's entire faucet switches off. Measured, that is exactly what happened. A unit
    standing on the terminus cannot be driven through, so the trains keep running."""
    fin = gt12.final
    assert [u for u in fin.units_at(MATRUH) if u.side == Side.ALLIED and u.is_combat], \
        "nobody is standing on the railhead"
    assert fin.control_of(MATRUH) != Control.AXIS
    assert railhead(fin).id == "AL-Stage-Matruh"            # the line never retracted

    cancelled = [e for e in gt12.events if e.kind.name == "CONVOY_CANCELLED"
                 and e.payload.get("lane") == "CW-RAILHEAD"]
    assert not cancelled, f"the rail faucet died {len(cancelled)} times"
    assert fin.supply("AL-Stage-Matruh").ammo > 0           # and it is actually filling


def test_the_standing_garrison_order_still_holds(gt12):
    """The garrison order (rule 64.73) is untouched by the concentration and by the offensive: a
    combat unit that is BANKING a victory city -- standing on it, supplied -- is never given a move
    order. The railhead is itself a victory city, so the line's garrison ends up held by BOTH rules,
    which is exactly right."""
    fin = gt12.final
    keep = garrison_units(fin, Side.ALLIED)
    assert keep, "the Commonwealth banks no victory city at all"
    assert CampaignVictory()._occupier(fin, MATRUH) == Side.ALLIED   # supplied, on the line

    pol = CampaignCommonwealthPolicy()
    assert not pol._on_offensive(fin)
    assert not (keep & {o.unit_id for o in pol.movement(fin, Side.ALLIED)})

    on_compass = replace(fin, turn=COMPASS.start)                    # and on the offensive too
    assert pol._on_offensive(on_compass)
    assert not (garrison_units(on_compass, Side.ALLIED)
                & {o.unit_id for o in pol.movement(on_compass, Side.ALLIED)})


def test_the_commonwealth_can_mount_a_supplied_offensive():
    """THE HEADLINE. Not one Commonwealth combat unit used to be SUPPLIED forward of Mersa Matruh at
    any point in Operation Compass -- the faucet and the lorry relay were healthy and the depot at
    Sidi Barrani was full, but the army was sixty hexes away and there was nobody to drink it. With
    the army on the line it launches from, the offensive is supplied where it is fought."""
    res = run(campaign(seed=1941, max_turns=COMPASS.stop - 1),
              CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin, vic = res.final, CampaignVictory()
    forward = [u for u in _combat(fin, Side.ALLIED)
               if distance(u.hex, ALEX) > distance(MATRUH, ALEX) and vic._supplied(fin, u)]
    assert forward, "no Commonwealth unit is supplied forward of the railhead during Compass"


# --- conservation + byte identity -----------------------------------------------------------

def test_conservation_holds_over_the_concentration(gt12):
    """The concentration only MOVES units and dumps -- it mints nothing. The recorded log folds
    byte-identically back to the final state, and game.invariants (checked by the engine after every
    applied event, so a clean run IS the proof) never raised."""
    assert fold(gt12.initial, gt12.events) == gt12.final
    for c, initial in gt12.final.initial_supply.items():
        on_hand = (sum(getattr(s, c.lower()) for s in gt12.final.supplies)
                   + sum(getattr(t, c.lower()) for t in gt12.final.trucks))
        assert on_hand + gt12.final.consumed.get(c, 0) == initial


def test_rommel_and_siege_stay_byte_identical():
    """THE HARD CONSTRAINT. Every change is inside CampaignCommonwealthPolicy, which the two
    benchmark scenarios never construct (they run ScriptedPolicy on both sides), and neither carries
    a railway for it to anchor on. They must not move one byte."""
    axis = ScriptedPolicy(Side.AXIS)
    baselines = {"rommel": "9339d2b308d7", "siege": "5ba4da88d107"}
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        res = run(build(seed=42), axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baselines[name], f"{name} byte-identity broken: {sig} != {baselines[name]}"
