"""THE TAKE-AND-HOLD (rule 64.73, game.campaign_claim).

The campaign is scored on the victory CITIES a side holds with a SUPPLIED combat unit at the final
Game-Turn -- not on how far its spearhead got. The scripted Commonwealth used to drive every
battalion at objective_for(ALLIED) and bank nothing on the way: measured over the full campaign it
sprinted past Sollum, Bardia and Derna to Benghazi, garrisoned none of them, and finished 200-120
down with 250 Victory Points of EMPTY CITY lying behind its own front line.

These are the acceptance tests for the fix, and for the three things it must NOT do: strand a
garrison out of supply, strand a depot in the desert, or mask its own supply chain.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import campaign_claim, coords                                  # noqa: E402
from game.apply import apply, fold                                       # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,                    # noqa: E402
                                  CampaignCommonwealthPolicy)
from game.engine import determinism_signature, run                       # noqa: E402
from game.events import Control, Side                                    # noqa: E402
from game.policy import ScriptedPolicy, SupplyMoveOrder                  # noqa: E402
from game.scenario import campaign, rommels_arrival, siege_of_tobruk     # noqa: E402
from baselines import (BENCHMARKS, CAMPAIGN_FLOOR,                       # noqa: E402
                       CAMPAIGN_PANEL, CAMPAIGN_SEED)


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


SOLLUM, BARDIA, TOBRUK = _ax("C4021"), _ax("C4321"), _ax("C4807")
MATRUH = _ax("D3714")                       # the railhead city, and [60.5]'s airfield
BARRANI = _ax("C4131")                      # the forward city the take-and-hold contests
SIWA, JALO, GIARABUB = _ax("C0127"), _ax("B0513"), _ax("C1014")


def _run(max_turns: int):
    return run(campaign(seed=CAMPAIGN_SEED, max_turns=max_turns),
               CampaignAxisPolicy(), CampaignCommonwealthPolicy())


def _banked(state, side: Side) -> set:
    vic = state.victory
    return {name for ax, _a, _c, name in vic.cities if vic._occupier(state, ax) == side}


# --- TAKE ----------------------------------------------------------------------------------------

_PANEL_TURNS = 30          # THE HORIZON: see the panel test's docstring.


def _claim_reading(seed: int) -> dict:
    """ONE ROW OF THE PANEL for test_both_sides_take_the_cities_they_used_to_sprint_past: the
    GT30 board at `seed`, read for OCCUPATION (who stands on the city -- the take-and-hold) and for
    BANKING (whose scoreboard it is on -- 64.73's supply quality-test). Kept apart deliberately;
    the gap between them is a measurement of the supply chain, not of the policy."""
    fin = run(campaign(seed=seed, max_turns=_PANEL_TURNS),
              CampaignAxisPolicy(), CampaignCommonwealthPolicy()).final
    matruh = [s for s in fin.supplies if s.id == "AL-Stage-Matruh"]
    return {
        "seed": seed,
        "cw_banked": _banked(fin, Side.ALLIED),
        "ax_banked": _banked(fin, Side.AXIS),
        "cw_barrani": campaign_claim._occupied(fin, Side.ALLIED, BARRANI),
        "ax_sollum": campaign_claim._occupied(fin, Side.AXIS, SOLLUM),
        "ax_tobruk": campaign_claim._occupied(fin, Side.AXIS, TOBRUK),
        "ax_bardia": campaign_claim._occupied(fin, Side.AXIS, BARDIA),
        "ax_matruh": campaign_claim._occupied(fin, Side.AXIS, MATRUH),
        "cw_matruh": campaign_claim._occupied(fin, Side.ALLIED, MATRUH),
        "matruh_depot": len(matruh) == 1 and matruh[0].hex == MATRUH,
    }


def test_both_sides_take_the_cities_they_used_to_sprint_past():
    """THE ACCEPTANCE, asked of BOTH armies -- because both of them have the take-and-hold, and it
    is the same side-generic code (campaign_policy.take_and_hold_moves). What it pins is the thing
    that must stay true on both sides: AN ARMY KEEPS THE CITIES IT BANKS, AND GOES AND GETS THE ONES
    IT DOES NOT.

    *** RESTATED ONTO A SEED PANEL 2026-08-03, AND THE DOCSTRING THAT USED TO LIVE HERE IS THE
    ARGUMENT FOR DOING IT. *** This test was re-pinned SIX times to whichever side currently stood
    on the one contested forward city, each re-pin honest, each measured, each obsolete within a
    slice. The [4.46] Headquarters close-assault dash finally broke it at CAMPAIGN_SEED=23, where
    the Commonwealth loses Sidi Barrani outright. Re-pinning a seventh time was available and is
    refused: it is choosing the evidence, and tests/baselines.py's CAMPAIGN_SEED note carries the
    whole argument -- the constant is OVER-SUBSCRIBED, and no single seed makes all of its consumers
    green, so pinning a CAPABILITY to one is the defect rather than the fixture.

    So the whole of baselines.CAMPAIGN_PANEL is folded -- seeds 1..24, unshopped, the prefix of
    scripts/gate_c.py's own 1..N -- and the claims are split by what they actually are:

      * SEVEN HOLD ON EVERY SEED OF BOTH TREES and are asserted PER SEED, twenty-four times each.
      * SEVEN ARE SEED-LUCK and are asserted as a COUNT against baselines.CAMPAIGN_FLOOR (half the
        panel), with BOTH trees' measurements written beside each so the headroom is visible.

    Nothing was dropped: every assertion the single-seed form made is still made, and the seven that
    are universal got twenty-four times stronger.

    MEASURED, panel 1..24, Game-Turn 30, this tree against a `git archive 80b1de1` control tree
    built OUTSIDE the repo (control -> current):

        the Axis OCCUPIES Tobruk                      24/24 -> 24/24
        the Axis OCCUPIES Bardia                      24/24 -> 24/24
        the Axis BANKS Tobruk                         24/24 -> 24/24
        the Axis BANKS Benghazi                       24/24 -> 24/24
        Bardia is NOT banked                          24/24 -> 24/24
        the Matruh depot is staged on the city        24/24 -> 24/24
        no city is banked by both sides               24/24 -> 24/24
        --- the Commonwealth OCCUPIES Sidi Barrani    19/24 -> 18/24   floor 12
        --- the Axis OCCUPIES Sollum                  24/24 -> 23/24   floor 12
        --- the Axis OCCUPIES Mersa Matruh            20/24 -> 18/24   floor 12
        --- the Commonwealth does NOT occupy Matruh   23/24 -> 21/24   floor 12
        --- Sidi Barrani is NOT banked                23/24 -> 22/24   floor 12
        --- Sollum is NOT banked                      23/24 -> 24/24   floor 12
        --- Mersa Matruh is NOT banked by the CW      23/24 -> 21/24   floor 12

    THE HORIZON STAYS AT GAME-TURN 30, which is where every measurement in this file's history was
    taken, so the panel's rows are directly comparable with the single-seed record below them. Cost
    is stated rather than hidden: 24 folds to GT30 is ~17 minutes of one worker, and Game-Turn 24 --
    two turns past the close of Operation Compass, the earliest horizon that contains everything
    this test is about -- would have saved three of them, which is not worth losing the
    comparability.

    THE GT24 ARM WAS MEASURED TOO, AND THE ONE PLACE THE HORIZON MATTERS IS DISCLOSED RATHER THAN
    LEFT FOR A READER TO FIND. Six of the seven per-seed claims are 24/24 at both horizons and all
    seven counts agree within ONE seed, never moving toward the floor. The exception is BARDIA IS
    NOT BANKED: 24/24 on both trees at GT30, but 24 (control) / 23 (this tree) at GT24, where seed 2
    banks it. So at the shorter horizon that row would be a count rather than an invariant. The
    horizon was not chosen for that -- it is the horizon this file has always used, and both arms
    were measured before either was chosen -- but a choice with a consequence is worth writing down.

    THE TRIPWIRE, DEMONSTRATED. In a scratch copy of this tree (outside the repo)
    game.campaign_policy.take_and_hold_moves was made to return the army's own march untransformed
    -- no take, no hold, the capability removed outright, which is the state this test was written
    against, when the Commonwealth "sprinted past Sollum, Bardia and Derna to Benghazi, garrisoned
    none of them, and finished 200-120 down with 250 Victory Points of EMPTY CITY lying behind its
    own front line". The run goes red on seed 1, "the Axis threw away Tobruk, which it opened the
    war holding", and the collapse is total on the same panel:

        the Axis OCCUPIES Tobruk / Bardia             24/24 -> 0/24    (per seed)
        the Axis BANKS Tobruk / Benghazi              24/24 -> 0/24    (per seed)
        the Commonwealth OCCUPIES Sidi Barrani        18/24 -> 0/24    against a floor of 12
        the Axis OCCUPIES Sollum                      23/24 -> 0/24    against a floor of 12
        the Axis OCCUPIES Mersa Matruh                18/24 -> 0/24    against a floor of 12

    Both arms fail, so neither the per-seed invariants nor the counts are along for the ride. (Three
    rows do NOT move: the depot stays staged, no city is double-banked, and Bardia stays unbanked --
    which is correct and is the point of keeping them separate. An army that banks nothing trivially
    banks nothing twice.)

    ------------------------------------------------------------------------------------------------
    OCCUPATION AND BANKING ARE TWO DIFFERENT MEASUREMENTS AND THE SPLIT IS LOAD-BEARING (2026-08-02,
    cause [64.73]). campaign_victory._supplied now asks the rule's own question -- a Week of Stores
    and Water, three firings, and 20 CP of Fuel, HELD IN THE HEX -- where it used to trace Fuel and
    Ammunition over the section-32.16 half-CPA line of the ABSTRACT game. THE ARMY DID NOT MOVE when
    that landed; three cities simply stopped scoring. So OCCUPIED is the take-and-hold (this test's
    subject) and BANKED is the scoreboard, and asserting both is strictly more than the old
    `"Sollum" in ax` was.

    WHY THE BORDER CITIES STOP SCORING, measured clause by clause at GT30 on five boards, every
    board agreeing -- and the FIRST answer named the wrong clause and the wrong army, so the table
    is kept:

        city          holder                     clause that FAILS      what stands under it
        Giarabub      6 x IT-Grbub (Italian)     AMMUNITION only        AX-Well-Giarabub ONLY -- the
                                                 (2 of the 6 also Fuel) oasis, holding 124,996,400
                                                                        Stores, so STORES is SATISFIED
        Bardia        IT-Barka (Italian)         STORES only            AX-Stage-Bardia: 146
                                                                        Ammunition and NO Stores
        Sollum        IT-1-CCNN (Italian)        AMMUNITION + STORES    AX-Well-Sollum ONLY -- water,
                                                                        no Stores, no Ammunition

    Three corrections fall out of that table and each still stands. (1) The failing clause is not
    uniformly Stores -- one city fails on Ammunition alone, one on Stores alone, one on both -- and
    at Giarabub the old "cannot show a Week of Stores" sentence is refuted by a printed rule, [52.3]
    OASES: "Units sitting in Oases have all the stores and water they need to last them the entire
    game" (verbatim, folio 21). (2) Every failing garrison is ITALIAN, and not one German counter
    stands on a 64.73 city on any measured board, so [4.43b] first-line trucks could not flip any of
    them whatever they landed. (3) It does not spare the Commonwealth: BR-2SctGds fails the same
    STORES clause at Sidi Barrani on every A/B seed, and banks it at all only on a knife-edge -- 20
    of the 20 Points its five steps need before [4.46], 3 of the 24 its SIX steps need after. A step
    stronger and one ration short.

    WHAT IT ACTUALLY MEASURES IS THE LAST MILE. 64.73 asks for a WEEK, and no organic pool the book
    gives a counter is a week deep: [51.0] grants no organic Stores at all (what a counter holds is
    a [53.11] first-line buffer the war spends -- 1 of 57 Italian and 0 of 17 German combat units
    hold any Stores at GT30, against 25 of 67 Commonwealth), and [50.0]'s ammunition load is ONE
    firing against 64.73's three. So the failing clause is decided by WHAT DUMP STANDS UNDER THE
    GARRISON, which is this project's faucet debt and not its OOB debt.

    INVERT-THIS, AND THE PANEL IS WHY THEY CAN NOW BE STATED HONESTLY. The four "NOT banked" counts
    below are characterisation pins on a KNOWN GAP, not assertions that the gap is correct. WHEN THE
    LAST MILE CARRIES STORES FORWARD they will rise past the floor and the counts will fail --
    loudly, and on the distribution rather than on one board's Point-by-Point luck. Sollum and
    Bardia invert together (both fail on a dry forward dump); Sidi Barrani inverts with them; none
    of the three turns on [4.43b].

    MERSA MATRUH IS A DIFFERENT FINDING AND MUST NOT BE FOLDED INTO THEM (2026-08-02, cause
    [10.29]). engine._capture_noncombat takes a non-combat counter with no strength of any type when
    it is left alone in an enemy ZOC during the enemy's Movement/Combat Phase. [60.5] seeds THREE
    Commonwealth Squadron Ground Support Units on the railhead; the moment the garrison is retreated
    off the hex they stand alone, and where the old engine froze the hex behind them -- unenterable
    under [8.13], unflippable under [10.11]/[64.73] -- this one captures them and an Italian
    battalion walks in. The terminus is GENUINELY LOST on most panel boards, and that is asserted as
    OCCUPATION, where the take-and-hold lives. tests/test_campaign_concentration.py::test_the_
    railhead_is_held_and_the_faucet_keeps_running carries the full trace and the hundred-seed
    measurement.

    ------------------------------------------------------------------------------------------------
    THE SINGLE-SEED HISTORY THIS PANEL REPLACES, kept because the chain is the record of a rule
    moving an army and a reader will want it. The contested forward city changed hands six times and
    every one of them was a real measurement: the Commonwealth banked Sidi Barrani and garrisoned
    Mersa Matruh unbanked at the [60.5] air map; [15.53] Organization Size gave Sidi Barrani to a
    concentrated Axis (2026-07-25); the [8.37] per-terrain stacking limit gave it straight back the
    same day; Phase 8.1a's Delta terrain fills slowed the Commonwealth's march so far that NO Allied
    unit reached the railhead by GT30 (2026-07-26); Phase 8.1b's section-seam correction put an Axis
    unit on the empty terminus by GT3; Phase 8.1c's 23.11 (ENG) correction took four Italian counters
    out of the Sidi Barrani screen and its own review repair gave half of it back; and the
    [54.32]/[54.33]/[54.34] per-Operations-Stage railway (2026-08-01) fed the Eighth Army three times
    a week and INVERTED the whole thing back -- "the Commonwealth stands on Mersa Matruh and banks
    it", exactly as the 2026-07-26 note had instructed its successor to do. Six honest re-pins, and
    the seventh is a panel.

    ------------------------------------------------------------------------------------------------
    *** 🟢 2026-08-04, CAUSE [4.44B] -- THE ORDER OF BATTLE, AND THE LARGEST MOVE THIS PANEL HAS
    RECORDED. *** The Commonwealth order-of-battle pass seeds the 90 counters the [4.44B] chart
    prints and this engine did not carry -- 39 of them at Arrives 'D', among them the whole of the
    7th Armoured Division's armour, the Operation Compass infantry (6th Australian, 4th Indian, 2nd
    New Zealand), and the 1st South Staffordshires that [60.41] attaches to the Matruh Garrison.
    Panel 1..24 at Game-Turn 30, control tree against this one, and the control arm REPRODUCES every
    number the "(this tree)" column of the counts below carried before this entry -- 18 / 23 / 18 /
    21 / 22 / 24 / 21 -- which is what licenses the comparison:

        the Axis stands on Tobruk                24/24 -> 24/24
        the Axis stands on Bardia                24/24 -> 22/24   (moved to a count; see its note)
        the Axis banks Tobruk / Benghazi         24/24 -> 24/24
        Bardia is not banked                     24/24 -> 24/24
        the Commonwealth stands on Sidi Barrani  18/24 -> 23/24
        the Axis stands on Sollum                23/24 -> 22/24
        --- THE AXIS STANDS ON MERSA MATRUH      18/24 ->  4/24
        --- THE COMMONWEALTH STANDS ON IT         3/24 -> 20/24
        --- THE COMMONWEALTH BANKS IT             3/24 -> 20/24
        Sidi Barrani is not banked               22/24 -> 20/24

    THE EIGHTH ARMY KEEPS ITS OWN RAILHEAD NOW, and it is the counters that did it, not a policy and
    not a rule: the same pass moves Sidi Barrani from 18 boards to 23 and leaves the Axis's own rear
    (Tobruk, Benghazi, Bardia's control) exactly where it was. Two consequences are recorded
    elsewhere and belong beside this table: the Axis railway stops being bought with captured
    Commonwealth stores (tests/test_rail_control.py's 2026-08-04 re-pin -- 24 of 29 activations were
    paid by AL-Stage-Matruh on the control tree and none is here), and the Commonwealth's own rail
    line stops retracting (tests/test_campaign_concentration.py's, same date)."""
    panel = [_claim_reading(seed) for seed in CAMPAIGN_PANEL]

    # --- the seven claims that hold on every seed of both trees, asserted on every seed ----------
    for r in panel:
        s = r["seed"]
        # The AXIS -- which used to bank whatever the garrison order happened to pin and throw the
        # rest away, losing Bardia in every seed, a hundred Victory Points it starts the war
        # standing on -- now holds its own rear. Asserted on OCCUPATION, because "threw away what it
        # opened holding" is a claim about the ARMY.
        assert r["ax_tobruk"], f"seed {s}: the Axis threw away Tobruk, which it opened the war holding"
        # (Bardia MOVED to the seed-luck block below 2026-08-04, cause [4.44B] -- see its _count.)
        # ...and Tobruk BANKS because its 500-point staging dump stands under the garrison, which is
        # the clause table above told the other way round.
        assert "Tobruk" in r["ax_banked"], \
            f"seed {s}: the Axis no longer banks its own fortress: {sorted(r['ax_banked'])}"
        assert "Benghazi" in r["ax_banked"], \
            f"seed {s}: the Axis still does not garrison its own port: {sorted(r['ax_banked'])}"
        assert "Bardia" not in r["ax_banked"], (
            f"seed {s}: Bardia is banked again -- measured, this hex fails on STORES ALONE, its own "
            f"staging dump standing under it stocked with Ammunition and dry of rations. INVERT IT "
            f"WITH SOLLUM: both come back when the last mile carries Stores forward, and neither "
            f"turns on [4.43b]")
        assert r["matruh_depot"], \
            f"seed {s}: the railhead depot must still be staged under its garrison"
        assert not (r["cw_banked"] & r["ax_banked"]), \
            f"seed {s}: a city is banked by both sides: {sorted(r['cw_banked'] & r['ax_banked'])}"

    def _count(label, keep, control, current, note=""):
        """Assert one seed-luck claim of the DISTRIBUTION. `control`/`current` are what the two
        measured trees read, carried into the message so a failure reports its own headroom."""
        hits = [r["seed"] for r in panel if keep(r)]
        assert len(hits) >= CAMPAIGN_FLOOR, (
            f"{label} -- it holds on only {len(hits)} of {len(CAMPAIGN_PANEL)} panel seeds, failing "
            f"on {[r['seed'] for r in panel if not keep(r)]}, against a floor of {CAMPAIGN_FLOOR} "
            f"and a measurement of {control} (control) / {current} (this tree). {note}")

    # --- the seven seed-luck claims, asserted of the DISTRIBUTION --------------------------------
    # THE TAKE-AND-HOLD ITSELF, on the two cities the two armies actually contest. Sidi Barrani is
    # the Commonwealth's -- the forward city Operation Compass goes and gets -- and Sollum is the
    # Axis's, which it holds against Compass. These are claims about the ARMY, so they are asked of
    # occupation and not of the scoreboard.
    _count("the Commonwealth lost Sidi Barrani -- the take-and-hold itself has regressed, not its "
           "score", lambda r: r["cw_barrani"], 18, 23)
    _count("the Axis lost Sollum -- the take-and-hold itself has regressed, not merely its score",
           lambda r: r["ax_sollum"], 23, 22)
    # BARDIA MOVED HERE FROM THE PER-SEED BLOCK, 2026-08-04, CAUSE [4.44B]. "The Axis holds its own
    # rear" held on 24 of 24 boards of both trees until the Commonwealth order-of-battle pass; it now
    # reads 22 of 24, failing at seeds 10 and 16. IT IS NOT THROWN AWAY ON EITHER: measured, the hex
    # is Axis-CONTROLLED at Game-Turn 30 on both (Control.AXIS), it simply has no counter standing on
    # it -- the garrison marched off to meet an Eighth Army that, with its Operation Compass order of
    # battle finally on the board, is over the wire by GT30 (on seed 10 the Commonwealth is standing
    # on Sollum). An army that leaves a city it still controls to fight is doing the opposite of
    # sprinting past one, which is what this test is named for, so the claim keeps its floor and
    # loses its absoluteness.
    _count("the Axis threw away Bardia, which it opened the war holding",
           lambda r: r["ax_bardia"], 24, 22,
           "measured, the hex is still Control.AXIS on both failing seeds -- the garrison left it, "
           "the enemy did not take it")
    # THE RAILHEAD CITY -- AND THE [10.29] FINDING IS REVERSED, 2026-08-04, CAUSE [4.44B]. Both
    # counts below said "INVERT this restatement / update this restatement" if the Commonwealth ever
    # started retaking its own terminus. It has, and by a landslide: control 18/24 -> 4/24 for the
    # Axis holding it, 21/24 -> 4/24 for the Commonwealth NOT holding it. What changed is not a rule
    # about capture but the order of battle that was supposed to garrison the hex: [60.41] prints
    # the 1st South Staffordshires on Mersa Matruh at Game-Turn 1 and this engine did not carry the
    # counter, so the terminus was defended by three Squadron Ground Support Units and [10.29] duly
    # collected them. The rule was right; the roster was short. The pins are inverted, both
    # directions kept, so a THIRD flip cannot pass unnoticed either.
    _count("the Commonwealth lost the railhead city on most of the panel -- INVERT this "
           "restatement, the [4.44B] finding reversed", lambda r: r["cw_matruh"], 3, 20)
    _count("the Axis holds the railhead city on most of the panel -- INVERT this restatement, the "
           "[4.44B] finding reversed", lambda r: not r["ax_matruh"], 6, 20)
    # THE SCOREBOARD, and every one of these is an INVERT-ME on the last mile (see the docstring).
    _count("Sidi Barrani is banked again", lambda r: "Sidi Barrani" not in r["cw_banked"], 22, 20,
           "measured, it fails on STORES ALONE and by ONE ration: the depot under it is dry of "
           "Stores in every arm, so the clause rests on the garrison's own [53.11] buffer. INVERT "
           "THIS when the last mile carries Stores forward; do not re-pin it to a counter that "
           "happens to be one step lighter")
    _count("Sollum is banked again", lambda r: "Sollum" not in r["ax_banked"], 24, 24,
           "64.73's Ammunition and Stores are reaching the border cities. INVERT THIS: measured, "
           "this hex fails on AMMUNITION AND STORES because only AX-Well-Sollum stands on it, so "
           "what gives it back is a stocked forward dump (the last mile), not [4.43b] -- no German "
           "counter stands on a 64.73 city on any measured board")
    # INVERTED 2026-08-04, CAUSE [4.44B], with the two occupation counts above: the Commonwealth
    # does not merely stand on its railhead again, it BANKS it -- 21/24 -> 4/24 for "not banked",
    # i.e. banked on twenty of twenty-four boards where it was banked on three. 64.73's quality test
    # is an in-hex supply question and the answer changed because a garrison the chart prints is
    # finally standing there to be asked it.
    _count("Mersa Matruh is NOT banked by the Commonwealth any more -- INVERT this restatement, "
           "the [4.44B] finding reversed", lambda r: "Mersa Matruh" in r["cw_banked"], 3, 20,
           "the depot's own residual Ammunition is NOT pinned with it -- that is a transit node's "
           "leftovers, not the banking, and the capability it stood for is pinned in "
           "tests/test_campaign_concentration.py on the can-move-and-fire draw")


def test_occupying_sollum_brings_the_supply_chain_up_to_it():
    """THE HINGE. Sollum carries the Commonwealth's OWN Field Supply Depot (60.34), seeded EMPTY one
    22-CP lorry hop beyond Sidi Barrani -- and the old policy swept past the hex for a hundred and
    eleven Game-Turns without once standing on it. So Sollum stayed AXIS-CONTROLLED to the last turn
    of the war, no lorry would deliver into it and no dump would leapfrog onto it, and the third link
    of the Commonwealth's own chain sat dry all campaign.

    Take the hex and the supply comes up behind it (spine_awaits_control: what was missing was never
    distance, it was CONTROL). And the ten points are the least of it -- a stocked depot ON Sollum is
    what puts BARDIA, three hexes away and worth FIFTY, inside a Commonwealth supply trace for the
    first time in the campaign.

    *** PINNED ON THE HINGE ITSELF, NOT ON WINNING THE FIGHT FOR IT. *** The Axis now garrisons
    Sollum (it has the take-and-hold too), so the Commonwealth no longer walks onto the hex by
    Game-Turn 24 -- and an outcome test would then be measuring the Axis's defence, not this
    shortcut. What must hold, and what actually failed before spine_awaits_control existed, is the
    JUDGEMENT: a city carrying our OWN empty Field Supply Depot on an ENEMY-CONTROLLED hex is dry
    because of CONTROL, not distance, so it is claimed and a unit is sent -- and NO field dump is
    sent with it (the depot is already there; a second one would only mask it from the lorries).

    *** 🟢 RESTATED 2026-08-04, CAUSE [19.12] -- AND THE NOTE ABOVE IS WITHDRAWN BECAUSE THE
    COMMONWEALTH NOW WINS THE FIGHT FOR IT. *** The [15.53] HQ-follows-its-formation driver lets a
    concentrated brigade march under its own bare HQ, and the Eighth Army takes Sollum. The old form
    asserted the hinge OF THE FINAL BOARD, which is exactly where it is no longer true: at GT24 the
    hex is COMMONWEALTH-controlled, two battalions stand on it, and AL-Stage-Sollum -- the depot
    this test's own docstring says "sat dry all campaign" and "stood empty the whole time" -- holds
    1,176 Fuel and 15 Ammunition. spine_awaits_control reads False because its precondition (the
    ENEMY holds the hex) has been removed by the thing it exists to cause.

    So the test is restated to assert BOTH halves of its own story, and it is strictly stronger than
    the form it replaces:
      * THE JUDGEMENT, on the turn-closes OF THIS RUN where its precondition genuinely stands.
        MEASURED at CAMPAIGN_SEED: Sollum is Axis-held with our empty depot on it at the Game-Turn
        2, 3 and 4 closes, and it is claimed at every one of them with NO dump in tow.
      * THE OUTCOME, which the pre-driver tree could not reach and which this docstring could
        therefore only promise: 1-RFslr walks onto the hex at Game-Turn 5, the supply comes up
        behind it from Game-Turn 8 (4 Ammunition / 45 Fuel), and the depot carries 1,000-2,000 Fuel
        from Game-Turn 16 to the end. That is spine_awaits_control's own sentence -- "put one
        battalion on it and the supply comes up behind it within a Game-Turn or two" -- happening.
    Asserting the outcome is no longer "measuring the Axis's defence" as a substitute for the
    judgement, because the judgement is still asserted, on real boards, immediately above it."""
    res = _run(24)
    assert res.initial.supply("AL-Stage-Sollum").empty        # seeded empty: hauled into, not filled
    fin = res.final

    # The hinge: our own depot, empty, on a hex the enemy holds -- distance is not the problem.
    st, hinge = res.initial, []
    for e, nxt in zip(res.events, res.events[1:] + [None]):
        st = apply(st, e)
        if (nxt is None or nxt.turn != e.turn) and campaign_claim.spine_awaits_control(
                st, Side.ALLIED, SOLLUM):
            hinge.append(st)
    assert hinge, ("Sollum is never both enemy-held and carrying our own empty depot -- the hinge "
                   "has no board to stand on in this run; re-derive it, do not delete it")
    # (Two lines stood here re-asserting `depot.empty` and `control_of(SOLLUM) == AXIS` of
    # hinge[0]. DROPPED 2026-08-04, flagged by the [15.53] correctness review: the selector above
    # is `spine_awaits_control`, which returns EXACTLY `depot is not None and depot.empty and
    # control_of(ax) == AXIS`, so both lines re-asserted the selector's own conjuncts of a board
    # chosen BY that selector and could no longer fail. They were real assertions in the older
    # form, which asked them of the FINAL board independently of any selector; once the test moved
    # to selecting hinge boards they became tautologies. A test line that cannot fail is worse than
    # no line -- it reads as coverage. What still bites here: `assert hinge`, the claims() loop
    # below, and the two outcome assertions at the end.)

    # ...so a unit is claimed for it -- ALONE, with no field dump in tow.
    for board in hinge:
        plan = {c.city: c for c in campaign_claim.claims(board, Side.ALLIED, escort=True)}
        assert SOLLUM in plan, "Sollum is not even claimed -- the shortcut is dead"
        assert plan[SOLLUM].depot_id is None, \
            "a field dump was sent to MASK the depot already on Sollum"

    # AND THE SHORTCUT DELIVERS: the hex is taken and OUR OWN depot on it fills (2026-08-04).
    assert fin.control_of(SOLLUM) == Control.ALLIED, \
        "the Eighth Army no longer takes Sollum -- INVERT this restatement, the finding reversed"
    assert not campaign_claim.depot_on(fin, Side.ALLIED, SOLLUM).empty, \
        "Sollum is held and its own Field Supply Depot is still dry -- the supply did not follow"

    # THE SHORTCUT'S EVIDENCE -- AND WHAT CHANGED UNDERNEATH IT. This block used to open by
    # re-asserting the hinge of the FINAL board ("the depot ON Sollum is still EMPTY and the hex is
    # still ENEMY-HELD"). Both halves of that are now false and both are asserted the other way
    # round twelve lines above: [19.12]'s formation driver puts the Eighth Army on the hex, and the
    # lorries fill its depot. The duplicate assertion is DROPPED rather than restated, because the
    # single restatement above already carries it -- two copies of a claim is how one of them goes
    # stale unnoticed, which is exactly what happened here.
    #
    # What was no longer true even before that -- the old COROLLARY -- is that a Commonwealth
    # battalion standing on Sollum could not be fed there either, so gating the claim on can_be_fed
    # alone would decline Sollum for ever. It would not: the railway carries its charted 54.32
    # tonnage, so the link BEHIND Sollum -- the Sidi Barrani Field Supply Depot -- is stocked, and a
    # 32.16 trace from Sollum reaches it. Before that fix the entire Commonwealth chain was dry (the
    # railhead held ZERO Fuel on every turn of the war) and the honest trace test said NO everywhere.
    # The judgement was right then and is right now; the ground under it is finally supplied.
    #
    # THE LINK BEHIND SOLLUM IS STOCKED -- which is the claim, and the only form of it that was ever
    # true. The Sidi Barrani Field Supply Depot now carries a real reservoir (the charted [60.44]
    # start-line stock, kept topped up by the [60.43] lorry park off the rail-fed railhead), so the
    # chain the offensive advances along is alive and the ground under this claim is supplied.
    #
    # What this used to assert -- that the claimed battalion could be FED standing on Sollum -- was a
    # latent falsehood that happened to pass. The unit the claim sends is 24-Aus-Bde: FOOT, CPA 10,
    # so a 32.16 trace of cpa/2 reaches FIVE Capability Points on foot. Sidi Barrani is TEN HEXES from
    # Sollum. It was never reachable, and never could be. The old assertion passed only because one of
    # the army's MOBILE field dumps (32.3) happened to be parked one hex off Sollum on Game-Turn 24 of
    # this one seed -- the army's own baggage, not "the chain behind Sollum" at all. A unit standing
    # on Sollum is fed by the depot ON Sollum, which is what the lorries fill once the offensive takes
    # the hex; that is the whole reason the depot is seeded there empty.
    # RESTATED 2026-07-25 (Block 7.C, rule 15.53 Organization Size): the head moved BACK one bound.
    # The Axis now fights its regiments concentrated (campaign_policy.concentrate_formations) and its
    # [15.53] column-shift edge has OVERRUN the forward Sidi Barrani reservoir (32.13: the hex and its
    # dump changed hands), so the live Commonwealth chain now sits at the rail-fed Matruh railhead
    # reservoir. That the chain is ALIVE -- the rail faucet and the lorry park still filling it -- is
    # what this pins; the concentration edge decides only HOW FAR FORWARD the head reaches, and it is
    # the railhead now, not Sidi Barrani (measured seed 4, GT24: Matruh wet, AL-Stage-Barrani AXIS).
    #
    # RESTATED AGAIN 2026-07-26 (Phase 8.1b, the A/B/D/E section-seam correction): the head moved back
    # ANOTHER bound. An Axis unit now walks over the empty Matruh terminus by GT3 (see
    # test_campaign_concentration.py's RESTATED note -- the same measured fact, not a new regression)
    # and the rail lane correctly drains the hex it no longer controls (AL-Stage-Matruh: 0 Ammo/0
    # Fuel here). Sidi Barrani, in turn, is no longer overrun at this seed (its hex is Commonwealth-
    # held again at GT24, matching the [8.37] stacking-fix restatement two notes up in
    # test_campaign_claim.py::test_both_sides_take_the_cities_they_used_to_sprint_past), so the live
    # chain sits where the 2026-07-25 note above says it sat before 15.53 concentration pushed it
    # forward: the Sidi Barrani Field Supply Depot. Same claim, same mechanism (a 32.16 trace behind
    # Sollum is alive), different depot, again.
    barrani = fin.supply("AL-Stage-Barrani")
    assert barrani.ammo > 0 and barrani.fuel > 0, \
        "the chain behind Sollum is dry -- the rail faucet or the lorry park is dead"


def test_you_do_not_besiege_a_city_you_could_not_hold():
    """The ONE clause that sorts the two fortresses, with no fortress special-case anywhere. Rule
    15.82 grants Bardia and Tobruk NO EVICTION, so an assault will never move those garrisons and a
    policy that throws men at them forever is just bleeding. The take-and-hold does not know they are
    fortresses -- it only asks whether it could FEED a garrison there, and that answer, by itself,
    sends the army to Bardia and leaves Tobruk alone.

    Bardia is three hexes from the Sollum depot the take-and-hold has just filled; Tobruk is not near
    anything the Commonwealth owns.

    *** THE ATTRIBUTION WAS FALSE AND THE TEST HAD GONE VACUOUS BEHIND IT. Both repaired 2026-08-02.
    *** This docstring called the gate "the 64.73 trace test". It is not one, and after the in-hex
    repair rule 64.73 has no trace at all: the gate is campaign_claim.could_be_fed, the planner's own
    32.16 REACH heuristic, which was split off campaign_victory._supplied when that predicate became
    the rule's real one. THE WITNESS BELOW WENT WITH THE NAME AND NOT WITH THE GATE. It read
    victory._supplied -- which, before the split, WAS could_be_fed to the Point (_PLANNER_CP 20 /
    _PLANNER_FIRINGS 3 are the very magnitudes it inherited) and afterwards is a different question
    entirely. The two are NOT ordered: MEASURED at CAMPAIGN_SEED over 67 Commonwealth combat units x
    the 10 cities, they agree on 87 pairs and disagree on 171 (124 _supplied-only, 47
    could_be_fed-only). At Bardia and at Tobruk _supplied answered YES for 14 units apiece where
    could_be_fed answers NO for all 67 -- so `feedable` read True at both, the `if` guard was False
    at both, and THIS TEST EXECUTED NO ASSERTION AT ALL. It is pointed back at the gate it is named
    for, which is the predicate that stood here before the split; the assertion fires again at both
    cities, and it fires on the thing the docstring above describes."""
    fin = _run(30).final
    cw = [u for u in fin.living(Side.ALLIED) if u.is_combat and u.strength >= 1]
    plan = {c.city: c for c in campaign_claim.claims(fin, Side.ALLIED, escort=True)}

    feedable = {ax: any(campaign_claim.could_be_fed(fin, u, ax) for u in cw)
                for ax in (BARDIA, TOBRUK)}
    assert not any(feedable.values()), (
        "a Commonwealth unit could now be fed at Bardia or Tobruk -- the `if` below has stopped "
        "guarding anything and this test is inert; re-derive the witness, do not delete it")
    for ax, name in ((BARDIA, "Bardia"), (TOBRUK, "Tobruk")):
        if not feedable[ax] and fin.victory._occupier(fin, ax) != Side.ALLIED:
            assert ax not in plan, f"{name} is besieged but no unit could be supplied there"


def test_the_desert_oases_are_reachable_but_not_suppliable_so_no_depot_goes_there():
    """MEASURED, and the reason this clause exists: flying columns CAN reach Siwa and Jalo, and were
    banked on both by Game-Turn 24. By Game-Turn 111 both depots were dry, both garrisons had
    starved, both cities stood empty -- and the two dumps were gone from the army's park for good
    (32.33: a depot only relocates onto a hex a friendly COMBAT unit holds, so a depot alone in the
    desert is stranded there for the rest of the war). The lorry pool meanwhile quadrupled its
    mileage driving after them, and the Commonwealth lost BENGHAZI and SIDI BARRANI -- 110 Victory
    Points -- chasing 30 it could not keep.

    So a depot only marches to where the LORRIES can follow (within_a_lorry_hop, the rulebook's own
    53.22 convoy CPA). The oases are reachable. They are not SUPPLIABLE, and nothing is sent."""
    res = _run(30)
    for d in res.final.supplies:
        if d.side == Side.ALLIED and campaign_claim.is_field_dump(d):
            assert d.hex not in (SIWA, JALO, GIARABUB), \
                f"{d.id} was marched to a desert oasis it can never be refilled at ({d.hex})"


# --- HOLD ----------------------------------------------------------------------------------------

def test_a_depot_feeding_a_banked_city_never_leapfrogs_away_from_it():
    """The dual of the standing garrison order, and the half without which the other half is
    worthless: the base 32.3 bridge leapfrogs every fuelled dump toward the objective, so the turn
    after a depot arrives at Sollum it would march straight off again to the head of the column and
    the city it had just made bankable would stop scoring.

    ASKED OF THE AXIS, because that is where a depot is now doing this job. Both policies run the
    identical side-generic transform (campaign_policy.take_and_hold_supply), and the Axis is the side
    that at Game-Turn 24 is feeding a banked city off a FIELD dump (AX-Dump#5, standing on Sollum);
    the Commonwealth banks only cities its seeded SPINE already feeds, which garrison_depots
    deliberately does not pin (a staging depot is immobile anyway -- see the docstring there). Asking
    the Commonwealth here would be a vacuous test, and it says so out loud."""
    fin = _run(24).final
    pol = CampaignAxisPolicy()
    pinned = campaign_claim.garrison_depots(fin, Side.AXIS)
    assert pinned, "no depot is feeding a banked city -- the check is vacuous"
    moved = {o.supply_id for o in pol.supply_orders(fin, Side.AXIS)}
    assert not (pinned & moved), f"a garrison's own depot was ordered away: {sorted(pinned & moved)}"


def test_a_field_dump_never_parks_on_top_of_a_seeded_field_supply_depot():
    """THE MASKING GUARD (campaign_claim.keep_off_the_spine). The lorry relay picks its delivery
    address by (distance-to-objective, reach, id), and two dumps on one hex tie on the first two --
    so the tie breaks on the ID, 'AL-Dump#2' beats 'AL-Stage-Barrani', and every load lands in the
    field dump. And a field dump is exactly what the relay may NOT lift from again. Supply goes IN to
    a masked link and can never come OUT: the chain is severed at the very hex built to carry it.

    Measured, a field dump on Sidi Barrani took every one of AL-Stage-Barrani's deliveries, left the
    seeded depot at zero, starved the Sollum leg beyond it and lost the Commonwealth BENGHAZI -- a
    hundred Victory Points. That hex belongs to the chain."""
    fin = _run(24).final
    spine = {s.hex: s.id for s in fin.supplies
             if s.side == Side.ALLIED and s.id.startswith("AL-Stage")}
    assert spine
    for d in fin.supplies:
        if d.side == Side.ALLIED and campaign_claim.is_field_dump(d) and d.hex in spine:
            raise AssertionError(
                f"{d.id} is parked on {spine[d.hex]} and masks it from the lorries")

    # and the chain it protects actually carries: a seeded Field Supply Depot holds stock.
    chain = ("AL-Stage-Matruh", "AL-Stage-Barrani", "AL-Stage-Sollum")
    assert any(fin.supply(d).fuel > 0 for d in chain), \
        f"the spine carries nothing: {[(d, fin.supply(d).fuel) for d in chain]}"


def test_a_detached_unit_is_out_of_the_general_advance():
    """A detached unit is out of the advance -- EVERY unit in the plan, not merely the ones that
    happen to have a move order in it. A unit that has already REACHED its city emits no claim move
    (there is nowhere left to go), and if that left it in the attacker branch it would be marched
    straight back off toward Benghazi the same stage: the city taken and abandoned in one breath.

    So a claimed unit carries its claim's order or no order at all -- never the advance's."""
    fin = _run(14).final              # mid-Compass: detachments are in flight
    pol = CampaignCommonwealthPolicy()
    plan = campaign_claim.claims(fin, Side.ALLIED, escort=True)
    assert plan, "the take-and-hold claims nothing -- the check is vacuous"
    mine = {o.unit_id: o for o in campaign_claim.claim_moves(fin, Side.ALLIED, plan)}
    orders = {o.unit_id: o for o in pol.movement(fin, Side.ALLIED)}
    for c in plan:
        got = orders.get(c.unit_id)
        assert got is None or got == mine.get(c.unit_id), \
            f"{c.unit_id} was claimed for {c.name} but marched on the objective instead: {got}"


# --- conservation + byte identity ----------------------------------------------------------------

def test_conservation_holds_over_the_take_and_hold():
    """The take-and-hold only MOVES units and depots; it mints nothing. The recorded log folds
    byte-identically back to the final state, and game.invariants (on_hand + consumed == initial, per
    commodity) never raises -- the engine checks it after every applied event, so a clean run IS the
    conservation proof.

    RESTATED (56.3 slice, port rule 5): on_hand now also sums state.ships. Axis coastal shipping
    (rule 56.3) carries cargo the same way a truck convoy does, and this campaign build (GT24) runs
    long enough for the shuttle to be under way -- omitting the ships made this test's own hand-rolled
    sum disagree with game.invariants' (which already covers ships, and is the actual proof this test
    is restating in longhand), not the engine under-conserving."""
    res = _run(24)
    assert fold(res.initial, res.events) == res.final
    for c, initial in res.final.initial_supply.items():
        on_hand = (sum(getattr(s, c.lower()) for s in res.final.supplies)
                   + sum(getattr(t, c.lower()) for t in res.final.trucks)
                   + sum(getattr(sh, c.lower()) for sh in res.final.ships)   # 56.3 coastal ships
                   + sum(getattr(u, c.lower()) for u in res.final.units))   # 49.14 unit tanks (Phase 4)
        assert on_hand + res.final.consumed.get(c, 0) == initial


def test_rommel_and_siege_stay_byte_identical():
    """THE HARD CONSTRAINT. Every helper in game.campaign_claim needs the rule-64.73 city table, and
    rommels_arrival / siege_of_tobruk do not carry one (_cities returns () for them), so the two
    benchmark scenarios must hash exactly as they did before this slice existed."""
    axis = ScriptedPolicy(Side.AXIS)
    baselines = BENCHMARKS            # tests/baselines.py -- the ONE place, and why they moved
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        st = build(seed=42)
        assert not campaign_claim._cities(st)                # no city table -> every helper is inert
        assert campaign_claim.garrison_units(st, Side.AXIS) == set()
        assert campaign_claim.claims(st, Side.AXIS) == ()
        res = run(st, axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baselines[name], f"{name} drifted: {sig} != {baselines[name]}"


def test_the_claim_helpers_are_inert_without_a_city_table():
    """The whole module is safe to call on any state: no city table, no orders, no crash."""
    st = rommels_arrival(seed=42)
    assert campaign_claim.garrison_depots(st, Side.AXIS) == set()
    assert campaign_claim.claim_moves(st, Side.AXIS, ()) == []
    assert campaign_claim.claim_supply(st, Side.AXIS, ()) == []
    orders = [SupplyMoveOrder("AX-Dump", (0, 0))]
    assert campaign_claim.hold_depots(orders, st, Side.AXIS) == orders
