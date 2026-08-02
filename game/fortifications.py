"""[25.14] BATTERING A FORTIFICATION DOWN -- the two channels the book allows, and the one
opinion the book does not supply.

    [25.14] "Fortifications may be reduced in Level strength by air bombardment (see Case 39.37)
            or artillery barrage (Case 12.5). No other type of combat affects fortifications.
            Reduced fortifications may be rebuilt."          (PDF p.38, read off the scan)

    [25.16] "Major cities and fortifications may be reduced to a Fortification Level of zero.
            (Note: The "zero" level has no effect in the Land Game, except to mean that the
            fortification can be more easily rebuilt. However, see the Strafing Table, Case
            40.8)."                                           (PDF p.38, read off the scan)

            -- so the level floors at ZERO, which is a level and not an absence. The two printed
            qualifications are carried here rather than dropped, because a "no effect" this file
            states flatly would be wrong twice over: [40.8] STRAFING still cares about the zero
            level (unimplemented -- declared debt below), and "more easily rebuilt" is [24.42]'s
            business, which is the other half of 25.14's own last sentence.

            A PARAPHRASE OF THIS RULE SHIPPED HERE INSIDE QUOTATION MARKS -- "A fortification may
            be reduced below Level One, but this has no effect on the Land Game" -- and it is
            recorded rather than silently swapped, because that is the failure this port most
            has to be able to see in itself. It said "below Level One" where the book says "to a
            Fortification Level of zero" (the book never contemplates below), and it dropped both
            printed exceptions, turning a qualified note into a blanket rule. Cf. the 56.3
            correction: a transcription that corrects the book toward what the rule ought to say
            is the exact failure this port exists to avoid, and an INVENTED quotation is worse,
            because a later reader cannot tell it from a real one.

HOW TO READ A QUOTATION IN THIS SLICE, stated once so the next reader never has to guess. Anything
between quotation marks and attributed to a Case is the 1979 ink, character for character, off a
300-dpi render of the named PDF page. "..." marks an elision. "[sic]" marks the book's own
misprint, kept. CAPITALS INSIDE A QUOTATION ARE EMPHASIS ADDED HERE -- the house convention across
this engine's docstrings -- and never the book's own setting; the book emphasises with italics,
which plain-text docstrings cannot carry. Nothing else is altered: no word is modernised, no
qualification is dropped, and no clause is rewritten toward what a rule "obviously means".

WHAT LIVES HERE. The two [41.5] readings (`reduced_by_barrage` on the Artillery-Barrage-Points
scale per [12.53]; `reduced_by_bombing` on the Bomb-Points scale per [41.3]/[41.37]) and the
target-designation doctrine `barrage_target`. The level itself lives on GameState (fort_levels,
folded from FORT_REDUCED / FORT_LEVEL_BUILT); the close-assault, barrage and anti-armor shifts a
standing wall confers live in game.combat_tables off the [8.37] TEC; building one back up lives in
game.construction ([24.42]/[24.45]).

THE CROSS-REFERENCE IN 25.14 IS WRONG IN THE BOOK, and it is recorded here so nobody "fixes" the
engine toward it. [39.37] (PDF p.56, AIR folio 9) is inside [39.3] VOLUNTARILY ABORTED MISSIONS and
defines a sufficient fighter screen; it has nothing to do with fortifications. The rule 25.14 means
is [41.37] Bombing Major Cities/Fortifications (B-F/C). The same stale pointer appears again at
[22.31], consistent with a late renumbering of the Air booklet.

WHAT IS *NOT* HERE, and is declared debt rather than quietly absent:

  * [25.14]'s own second sentence, "Reduced fortifications may be rebuilt." The MECHANISM exists and
    is tested (game.construction.fort_buildable / can_build_fort, engine's FORT_LEVEL_BUILT, the
    [24.17] Construction Chart row: AnyE + an Infantry Battalion of 3+ TOE, 30 Stores, 3 Construction
    Segments, and [24.45] allows it in an Enemy ZOC). What does not exist is any Policy.construction
    that ever emits a FORT BuildOrder -- the same "the rule is built, no doctrine orders it" pattern
    the minefields (rule 26) and the Devil's Gardens already stand in. So a battered wall currently
    ratchets DOWN and is never rebuilt, and the honest reading of that is: half of 25.14 is wired and
    the other half waits on a staff officer, not on this module.
  * [22.34b] / [41.37]'s last clause -- a barrage or bombing result that WOULD reduce a fortification
    instead neutralises a temporary repair facility that is not in a Major City hex, for one
    Operations Stage. game.repair has the 22.34a modifier but no neutralisation state.
  * [12.55] "Off-Shore Bombardment may be used to Barrage facilities; see Case 30.12." (PDF p.21).
    That is a THIRD channel into this same [41.5] row, and it is not the same thing as the air and
    artillery channels 25.14 names -- 25.14's "No other type of combat affects fortifications"
    forecloses close assault and anti-armor, not a rule that routes off-shore fire THROUGH 12.5.
    engine._naval_bombardment exists and fires on the [12.6] unit table only: _naval_target picks a
    unit and never a works, so a Commonwealth battleship cannot shell Tobruk's wall. Wiring it means
    reading [30.12] and deciding whether a ship's Gun Rating (30.22, fed in as Actual Barrage Points
    with no ammunition draw) enters the Artillery-Barrage-Points scale unchanged. NOT DONE, and
    named here rather than left as the silent negative that _naval_bombardment's own docstring used
    to state as a virtue.
  * [40.8] the Strafing Table, which [25.16] points at in the same breath as it says the zero level
    has no Land-Game effect -- i.e. the book's own reason that "no effect" is not the whole truth.
    No strafing rule is implemented anywhere in this engine, so nothing reads the zero level for it.
"""
from __future__ import annotations

from . import logistics_data
from .events import CONTROL_OF, Side
from .hexmap import Coord, neighbors
from .state import GameState, Unit


def reduced_by_barrage(actual_points: int, d1: int, d2: int) -> int:
    """[12.53] Resolve one ARTILLERY barrage against a fortification on the [41.5] Fortification row,
    entering it on the Artillery-Barrage-Points scale. Returns 1 if the wall drops a level, 0 if not
    -- the Key prints exactly two outcomes and no cell of this row ever takes two levels.

    ACTUAL points, not Raw. [12.53] sends a facility barrage to "the Artillery Barrage Points
    column"; [12.54] then switches to RAW for Supply Dumps and Air Facilities ALONE, which is what
    makes the contrast explicit. The scale's own footnote (b) -- "Calculated in the same manner as
    for the Master Barrage Against Units CRT" -- points at [11.32], Actual = round(Raw/10), which
    game.combat.actual_points already computes for every other barrage in the engine."""
    return logistics_data.crt_result(
        logistics_data.fortification_bombardment_crt_41_5(),
        actual_points, d1, d2, "reduced", scale="barrage_points")


def reduced_by_bombing(bomb_points: int, d1: int, d2: int) -> int:
    """[41.37] B-F/C. The SAME row read on the Bomb-Points scale: "[41.3] All Land Support bombing
    missions except 'mining harbors' are resolved using the Air Bombardment and Secondary Barrage
    Target Combat Results Table (41.5)."

    [41.37]'s own words are "If the Player obtains a RESULT that would reduce the fortification level
    by one" -- a die is rolled and it can fail. The engine used to reduce a level unconditionally
    here, which is the same invented certainty its artillery twin carried, arrived at independently."""
    return logistics_data.crt_result(
        logistics_data.fortification_bombardment_crt_41_5(),
        bomb_points, d1, d2, "reduced", scale="bomb_points")


def barrage_target(state: GameState, unit: Unit, side: Side) -> "Coord | None":
    """[12.51]/[12.52] TARGET DESIGNATION: the hex whose WORKS this gun declares as its target this
    Barrage Step, or None if it has no fortification to shoot at and should barrage units as usual.

    *** FLAGGED AS AN OPINION A COMMANDER MAY HOLD, NOT A LAW OF THE WORLD. *** Same standing as
    campaign_policy.axis_rail_doctrine, coastal_shipping_doctrine and convoy_plan_doctrine, and
    flagged for the same reason: the book supplies the CHOICE and refuses to supply the DOCTRINE.
    [12.51] says artillery "may be used to Barrage facilities, RATHER THAN actual units, in an effort
    to reduce their effectiveness" -- may, rather than, in an effort to. Which of the two a battery
    fires at is the Barraging Player's decision every single Combat Segment, and the book never once
    says when he should prefer the wall. The real answer is a staff officer's and belongs to the LLM
    command staff; this is the smallest honest stand-in until then.

    WHY THERE HAS TO BE ONE AT ALL. There is no barrage ORDER in this engine -- no Policy method
    proposes one, and no order dataclass can carry a facility target (the only combat order is
    AttackOrder, which names a hex for close assault). Barrage is resolved automatically inside
    engine._barrage_step, so if this function does not designate the works, NOTHING EVER DOES and
    25.14 ships correct and permanently inert.

    THE OPINION TAKEN, in one sentence: A GUN STANDING NEXT TO AN ENEMY FORTIFICATION SHOOTS THE
    FORTIFICATION. Its justification is the rest of the rulebook rather than any measurement:
    [15.82] never lets a fortress be evicted, so the garrison has to be eliminated where it stands;
    [8.37] hands that garrison a two-, three- or four-column close-assault shift while the wall
    stands, which is what makes eliminating it hopeless; [41.31] will not even let bombers at the men
    "unless and until the fortification level of the city is reduced to one (1) or less". Flattening
    the works first is therefore what the surrounding rules leave a besieger to do -- and [25.16]'s
    floor at zero makes the preference SELF-LIMITING with no knob to tune: the moment the level
    reaches zero this returns None and the battery goes back to shelling men.

    THE HONEST ALTERNATIVE, stated because it was really considered and rejected: "shoot the works
    only when there is no unit to shoot at" is a smaller opinion and a defensible one. It was rejected
    because it is INERT BY CONSTRUCTION at the only hexes 25.14 exists for -- Tobruk, Bardia and
    Benghazi always hold a garrison, so under that reading a wall could never be battered at all, and
    the slice would ship a rule that is correct and can never fire. Neither reading is tuned: no
    number in this function was chosen by running the game.

    THE THREE TESTS -- TWO ARE RULES, AND THE MIDDLE ONE IS PART OF THE OPINION. That sentence used
    to read "each of which is a rule and not a preference", which promoted a doctrine choice to law
    inside the one docstring whose job is to keep the two apart:
      * A RULE. The hex must carry a STANDING wall -- [25.16] takes a fortification down "to a
        Fortification Level of zero" and no further, so at zero there is nothing left to reduce and
        the [41.5] row has no result that could apply.
      * NOT A RULE, PART OF THE OPINION. It must not be the firer's OWN works. No case says this.
        [12.51] lists the legal facility targets -- "Major Cities, Fortifications, Roads, Railroads,
        Supply Dumps, and Air Facilities" -- with no ownership qualifier, and [15.82] routinely
        leaves an enemy stack sitting in works whose control record is still mine, which is a board
        state a commander might well decide to shell. Refusing to is a defensible choice and not a
        law; the only authority it ever had was that engine._air_fort draws the same line for
        bombing, and _air_fort's line carries no citation either. It is kept because a garrison
        knocking its own walls down for the enemy behind them is not something a staff officer would
        order, and it is flagged HERE so the next reader is not told the book settled it.
      * A RULE. It must be ENEMY-held -- either the enemy controls the hex, or his units are standing
        in it. [12.31] "Artillery units may not Barrage non-occupied hexes (however, see Case 12.5)"
        is the exception that lets an EMPTY enemy fortress be shelled, and it is why occupancy alone
        is not the test.
    Ties are broken by neighbors() order, the same deterministic idiom the unit-barrage loop uses.

    WHAT THE OPINION COSTS ELSEWHERE, stated because the accrual it ADDS is flagged in
    engine._barrage_step and the accrual it REMOVES was not. A gun adjacent to BOTH an enemy works
    hex and a different enemy-OCCUPIED hex now sends all of its points at the wall, so the occupied
    hex receives no [10.34] Holding-Off points from it; if that gun's stack also holds non-gun combat
    units and nothing else answers that hex, [10.36] can force a three-hex retreat or the surrender
    of the whole stack (engine._mandatory_attack). Measured today the exposure is near zero -- 6
    facility barrages on 1 of 3 campaign seeds, 0 on either benchmark -- but that is proximity, not
    design. And the all-or-nothing shape is the ENGINE's, not the book's: [12.15] lets a battery in a
    Forward position "split their TOE Strength and attack more than one target, directing a portion
    of its TOE Strength against one unit and another portion against a different unit (target)"
    (PDF p.20), so the book would let the same battery do both and this function may not."""
    enemy_control = CONTROL_OF[Side.ALLIED if side is Side.AXIS else Side.AXIS]
    for nb in neighbors(unit.hex):
        if state.fort_level(nb) <= 0:                       # 25.16: floored at zero, nothing to take
            continue
        if state.control_of(nb) == CONTROL_OF[side]:        # never batter your OWN works
            continue
        if state.control_of(nb) != enemy_control and not state.enemies_at(nb, side):
            continue                                        # 12.31/12.5: an ENEMY fortification
        return nb
    return None
