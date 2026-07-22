"""[43.0] AXIS ITALIAN-AEGEAN AIR BASES, and [39.19] ONE MISSION PER PLANE -- the two rules that
make the Axis air force choose.

An air force that is everywhere is not an air force, it is a constant. Until this module, the
Panzerarmee's bombers raided Malta in the Strategic Air Phase (rule 44, block 5.4) and then bombed
Tobruk in all three Operations Stages of the same Game-Turn, with the SAME aeroplanes, and neither
sortie cost the other anything. Two printed rules forbid that, one structurally and one temporally:

  * **[43.12] THE STRUCTURAL HALF -- THREE QUARTERS OF THE GERMAN BOMBERS ARE NOT IN AFRICA.**
    "Until 1/35 Game-Turn 1941, 75% OF ALL GERMAN BOMBERS must be based in Italy/Sicily." That
    sentence names no type but it does name a nationality, and with the [59.3] muster transcribed
    that word is load-bearing: the campaign's September-1940 Axis air force is Italian to the last
    aeroplane, so 43.12 has nothing to base and takes nothing off the desert until [34.87] brings
    the Luftwaffe. A bomber standing on a Sicilian field is not available to fly a Land Support
    mission over the desert -- and it is the same bomber rule 44 sizes the Malta raid from, so it
    may not be counted in both places. From Game-Turn 35 that sentence EXPIRES and what is left is
    typed (43.11/43.13), which is `constrained_planes` below.

    ⚠ **SO RULE 43'S SUBJECT CHANGES AT GAME-TURN 35, AND `required_planes` IS WHERE.** Corrected
    2026-07-22: the first shipping of this module applied 43.12's percentage to `constrained_
    planes` -- the three NAMED heavies -- which narrowed an untyped sentence to a typed one and
    dropped every other German bomber ([4.44b] also prints the Ju. 87B, the Ju. 87D and the
    Ju. 52/3m, and the transcribed rows already carry their nationality) into the discretionary
    term. Before Game-Turn 35 the population is EVERY GERMAN BOMBER; from it, the three types
    43.11/43.13 name. The rule as written was expressible with the data in hand and now is.

  * **[39.19] THE TEMPORAL HALF -- MALTA OR THE DESERT, NOT BOTH.** "Generally, a plane may fly only
    one mission per Operations Stage or Strategic Phase... A PLANE FLYING A MISSION IN AN OPERATIONS
    STAGE MAY NOT FLY IN THE STRATEGIC PHASE OF THAT GAME-TURN AND VICE VERSA." This binds on the
    one force that can be in both places: 44.21/44.25 let the Axis add **African-based planes** to
    the Malta raid ("in no case may the Axis Player assign more planes of any one type from map
    bases than are assigned from the Availability Tables", 44.27). Every African bomber he sends to
    Malta is one that does not fly over the desert for the rest of that Game-Turn. That is the
    choice, it is the Axis Player's, and it is now his to make (Policy.malta_africa_planes).

--------------------------------------------------------------------------------------------------
THE ONE ARITHMETIC THIS MODULE ENFORCES: **AN AEROPLANE IS IN EXACTLY ONE PLACE.**

    africa_planes = the squadron - (the planes rule 43 bases in Italy/Sicily + those it bases in
                                    Crete)

and `italy_sicily_planes` is the SAME function rule 44 sizes its raid from (game.malta). Before this
repair the two halves ran on different readings at once -- 75% of the pool was in Sicily raiding
Malta AND 100% of it was in Africa flying Land Support, 35 aeroplanes of basing out of a 20-plane
force, in the direction that gave the Axis both arenas at once. Whatever is disputed below, that
was not: it was a double count, and the identity above is what replaced it.

⚠ THE ROUNDING DIRECTION IS A FLAGGED JUDGEMENT CALL. 43.11 says "AT LEAST 75%", which points at
rounding the Mediterranean requirement UP; the Mediterranean share here is floored, because it is
the same floored number [44.42] sizes the raid from ("rounding fractions down" is that table's own
key) and conserving whole aeroplanes exactly is worth more than rounding a percentage of a proxy
establishment the strict way. The floor is generous to Africa by at most one aeroplane.

--------------------------------------------------------------------------------------------------
BOTH OF THE 2026-07-21 OWNER RULINGS ARE IN, AND THE FIRST ONE DISSOLVED RATHER THAN BEING ANSWERED.

  (1) **"FROM GAME-TURN 35, DOES RULE 43 BIND ON A Ju. 87B AT ALL?" -- THE QUESTION IS GONE.** It
      was a question about a PROXY: the engine expressed the whole Axis bomber arm as one abstract
      Ju. 87B, rule 43's typed cases name heavy bombers, and so the Crete requirement bound on
      nothing for a reason that was ours and not the book's. The [34.6]/[59.3] Initial Air Strengths
      are now transcribed (game.roster), and the real answer is flatter and better evidenced:
      **[60.32] MUSTERS NO GERMAN AEROPLANE AT ALL.** In September 1940 the Axis air force in Africa
      is the Regia Aeronautica entire -- 65 C.R. 42, 70 C.R. 32, 133 S.M. 79, and six more types --
      and the Luftwaffe arrives on the [34.87] Axis Airplane Reinforcement Schedule, which is
      untranscribed. So 43.11/43.12/43.13 are written here in the book's own types (`constrained_
      planes`), they bind on nothing yet, and they will bind on their own the day that schedule
      lands. No reading is being taken; a chart is missing.

  (2) **WHAT IS "FW220"? -- RULED 2026-07-21: IT IS THE Fw. 200 C** ("yes thats the same
      aircraft"). 43.11 and 43.13 both name an aeroplane no chart prints. The [4.44b] German
      Aircraft Characteristics Chart (PDF page 145, rendered at 300 dpi and read with eyes) prints
      exactly eight German bombers/transports/recon types: Ar. 196, Fw. 200 C, He. 111, Hs. 126,
      Ju. 52/3m, Ju. 87B, Ju. 87D, Ju. 88D, and the nearest Focke Wulf bomber is the **Fw. 200 C**
      (Range 205, Bomb 14). The owner ruled it the same aircraft, so the constrained list carries
      all three types 43.11/43.13 name, and all three are now transcribed rows of the chart.

  Note the names in that list are the CHART's, verbatim, periods and all -- "He. 111", not
  "He 111" -- because `constrained_planes` is an exact string test against the [59.3] muster's own
  type names, which are the chart's printed names. A list transcribed off the RULE's prose
  instead ("He 111", "FW 220") could never match a transcribed row, and would have failed silently.

⚠⚠ AND ONE NEW OWNER RULING, WHICH THE REAL MUSTER CREATED, AND WHICH IS **OPEN AND UNSEEDED**.
**[60.32] PRINTS "NO PLANES START THE GAME IN ITALY/SICILY", AND [44.21]/[44.25]/[44.27] MAKE
PLANES BASED IN ITALY/SICILY THE PRECONDITION FOR ANY AXIS RAID ON MALTA AT ALL** -- while [64.52]
and [44.41]'s campaign row hand the Axis unlimited Level-I raids and 25 Level-II Game-Turns. The
bridge the book intends is 43.1's free basing choice ("the Axis Player may base any portion of his
airforce at Italy/Sicily", 61.42) and a rule-37 transfer, and this engine has an order channel for
neither.

CORRECTED 2026-07-22. This module first shipped with `discretionary_pct` seeded at [63.46]'s
printed 10% -- an El Alamein (October 1942) ceiling, transplanted whole onto September 1940 against
[60.32]'s plain printed sentence. `italy_sicily_planes` is the ONLY force rule 44 sizes its raid
from, so that one transplanted integer produced the entire Malta result the block reported: it was
a measurement of [63.46], not of [60.32]. That is deciding an owner ruling by transplant, which is
the invention this port exists to stop, so **the posture is now UNSEEDED**: the data key is null,
`discretionary_pct` answers 0, and the Axis bases in Italy/Sicily exactly what rule 43 REQUIRES him
to (nothing, until [34.87] brings a German bomber). The consequence is stated rather than hidden --
**the campaign Axis raids Malta with nothing while the ruling is open** -- and it is attributable
to an unbuilt order channel (the rule-37 transfer) rather than to a repealed rule. [63.46]'s 10% is
transcribed verbatim beside the null key under a name nothing reads, exactly as the unapplied
[35.23] printing is; answering the ruling is seeding one integer.

--------------------------------------------------------------------------------------------------
THE DEFERRED DEBT OF THE WHOLE AIR GAME, RECORDED HERE BECAUSE THIS IS THE LAST BLOCK OF PHASE 5
AND THE NEXT PERSON WILL LOOK FOR IT.

The port plan defers, by name: **40 (fighter combat), 45 (air-to-air combat), 46 (anti-aircraft
fire / flak), pilots, maneuver ratings, night missions, torpedoes, and paradrops.** The consequence
is one sentence and it is the sharpest thing in the plan:

    "`AirWing.fighters` is a constant that never dies. SOMETHING MUST EVENTUALLY KILL AEROPLANES,
     or Malta is a lever with no cost to pull."

Concretely, as of the end of Phase 5:

  * **No aeroplane on the African mainland can ever be shot down.** engine._air_superiority collapses
    40/45/46 into one die that SCALES a side's commitment for one Operations Stage; nothing folds a
    loss. The only channel in the engine that permanently removes aircraft is 41.36's "10% of the
    planes on the ground per level destroyed", and it exists on MALTA ALONE (malta.planes_lost).
  * **So the Axis raid on Malta is free of airframes, AGAINST THE PRINTED CASE.** [44.24] is
    explicit that the raid is not a free hit -- "the raid is conducted NORMALLY -- including
    air-to-air and AA/flak" -- and none of the three is built: 44.28's pro-rata split of losses
    between planes in play and planes not in play (the whole point of that case) has nothing to
    split, and Malta's 19 fighters and 17 AA Points ([60.46], transcribed) never fire. The raid is
    stronger than the book's raid, and the Commonwealth's only reply is the [44.5] repair table.
    THIS GOT SHARPER, NOT SOFTER, WITH THE [59.3] ESTABLISHMENTS: the raid used to be sized off a
    four-aeroplane proxy, so a missing loss channel cost the Commonwealth almost nothing; sized off
    [60.32]'s 184 bombers it is the difference between an air force that can be worn down and one
    that cannot. It is the first thing to build after the Italy/Sicily basing ruling is answered.
  * **[46.3]'s Anti-Aircraft CRT and the [45.4]/[45.5] TacAir tables are untranscribed** (the audit
    recovered [46.3] from PDF page 108 and it is legible). Transcribing them is the precondition for
    any of the above.
  * **Night (41.4), torpedoes as a weapon scale (41.7), paradrops (42.4) and pilot points** are all
    unbuilt. The [41.5] table's Torpedo-Points and Barrage-Points index scales are likewise still
    untranscribed, which is what 41.7 and 12.54 wait on.
  * **[39.16] "PLANES FROM THE SAME SQUADRON MAY NOT BE DIVIDED between strategic and land support
    missions"** is NOT implemented, and this block is what makes it reachable: engine._malta_africa
    sends `planes <= available` out of the single AXIS/LAND/strike squadron and leaves the
    remainder free to fly the desert, which 39.16 forbids at squadron grain. It is inert under the
    shipped doctrine (campaign_policy.malta_africa_doctrine commits every available African bomber,
    an all-or-nothing split), and 43.22's "divide all bombers in a given area into GROUPS OF 6 TO 12,
    considering each such group a squadron" may well make it moot once a real roster exists -- our
    whole abstract pool is smaller than one of the book's squadrons. Written down rather than left
    silent, because 5.5 is the block that opened the door.

Until something kills aeroplanes, every Malta measurement this engine produces is an upper bound on
the Axis's ability to suppress the island and a lower bound on what it costs him to try.
"""
from __future__ import annotations

from . import air, logistics_data, roster
from .events import Side
from .state import GameState

# The one arena and role rule 43 speaks about: the Axis BOMBER force. 43 says nothing about
# fighters (they are 40/45's business) and nothing about army-cooperation reconnaissance.
BOMBER_ROLE = "strike"
LAND_ARENA = "LAND"

# [43.12] "75% of all GERMAN bombers" -- the nationality the [4.44b] chart prints, which is the
# subject of that sentence and the reason it is not `constrained_types` (see german_bombers).
GERMAN = "german"


def _basing() -> dict:
    return logistics_data.malta_italy_sicily_basing_43_1()


def italy_sicily_pct(turn: int) -> int:
    """[43.12]/[43.13] The percentage of the REQUIRED Axis bomber force (`required_planes` -- every
    German bomber before Game-Turn 35, the three named heavies from it) that rule 43 compels to be
    based in ITALY/SICILY, the only part of the Mediterranean force 43.25 lets raid Malta. What the
    Axis CHOOSES to base there of everything else is discretionary_pct. 75 until Game-Turn 35 ("75%
    of all German bombers", untyped), 25 from it (the printed ceiling on 43.13's permissive "the
    remaining 25% MAY be based in Sicily/Italy or in Crete"; the choice of the ceiling over the
    floor is the
    flagged policy call recorded in data/malta_44.json, made where the alternative -- 0 -- would
    silently end the Malta war in June 1941)."""
    b = _basing()
    return b["before_turn_35_pct"] if turn < b["change_turn"] else b["from_turn_35_pct"]


def crete_pct(turn: int) -> int:
    """[43.13] The percentage based in CRETE -- nothing until Game-Turn 35, at least half the force
    from it. These bombers may not raid Malta (43.25 grants that to the Italy/Sicily half alone) and
    they are not in Africa, so from Game-Turn 35 the Axis is holding half his bomber arm where it
    can do neither job. It is also the printed remainder of 43.11's Mediterranean total: 75 less
    43.13's own 25 left in Sicily/Italy (data/malta_44.json carries all three numbers and a test
    checks the book's arithmetic closes).

    43.23's four Suez OpStages a month are a further tax on the Crete contingent and are not
    modelled: it flies no mission in this engine to be taxed out of (see the module docstring)."""
    b = _basing()
    return 0 if turn < b["change_turn"] else b["crete_pct_from_turn_35"]


def constrained_types() -> tuple[str, ...]:
    """[43.11]/[43.13] The aircraft types rule 43's TYPED cases name, given as the [4.44b] chart
    prints them (PDF page 145) so that an exact match against the [59.3] muster's own type names --
    which are the chart's -- is possible at all: "Fw. 200 C", "He. 111" and "Ju. 88D".

    THE RULE'S THIRD NAME, "FW220", IS PRINTED ON NO CHART -- and the owner ruled on 2026-07-21
    that it IS the "Fw. 200 C", which is therefore seeded here beside the other two (the ruling is
    written out at `_ruling_fw220_is_the_fw_200_c` in data/malta_44.json). All three are transcribed
    rows of the chart now; none of them is in the campaign's [60.32] muster, which is why the typed
    cases still bind on nothing -- see constrained_planes."""
    return tuple(_basing()["constrained_types_43_11"])


def discretionary_pct() -> int:
    """[43.1] / [63.46] THE SHARE OF HIS UNREQUIRED BOMBERS THE AXIS CHOOSES TO BASE IN
    ITALY/SICILY -- a DECISION, not a requirement, which is why it has its own name, its own data
    key and its own owner ruling (data/malta_44.json, `_owner_ruling_needed_60_32_vs_44_21`).

    Rule 43 compels a percentage only of GERMAN bombers. Every other aeroplane the Axis owns he
    bases where he likes: [61.42] says so in the scenario set-ups' own words -- "the Axis Player MAY
    BASE ANY PORTION OF HIS AIRFORCE AT ITALY/SICILY within the minimum German plane restrictions of
    Case 43.1" -- and 44.27's own worked example has him keeping Italian types there ("He has, based
    in Italy and Sicily, 12 SM 79's, 6 BR 20's, 16 CR 42's, and 4 CR 32's").

    **THE POSTURE IS UNSEEDED AND THIS RETURNS ZERO** (data key null). This engine has no order
    channel for the choice -- no 37/39 transfer mission, no basing seat -- and the only number the
    book ever prints for it, [63.46]'s "he may not have more than 10% of his air power in Italy or
    Sicily", is written for El Alamein in October 1942 and for a scenario whose very next sentence
    reads "Strategic air attacks against Malta may be made only in the Long Retreat scenario". This
    module shipped once with that 10 transplanted onto September 1940, and because
    `italy_sicily_planes` is the only force rule 44 sizes a raid from, that single integer WAS the
    Malta result. It is withdrawn until the owner rules (the escalation protocol: implement what is
    safe, leave the disputed part unseeded). Zero here is not a reading of [60.32] either -- it is
    the absence of a transfer order, and the raid it produces (none) is reported as such."""
    pct = _basing()["axis_discretionary_italy_sicily_pct_43_1"]
    return 0 if pct is None else pct


def _share(state: GameState, side: Side, keep) -> int:
    """The aeroplanes of `side`'s LAND bomber squadron whose [59.3] muster rows satisfy `keep`,
    taken as the establishment's own share of itself -- an AirWing is Air Points and not a roster
    of aeroplanes (game.roster), so what fraction of the bomber arm a population is on the printed
    muster is the fraction of the wing in play it is."""
    squadron = air.squadron_planes(state, side, LAND_ARENA, BOMBER_ROLE)
    if squadron <= 0:
        return 0
    establishment = roster.planes(side, BOMBER_ROLE)
    charted = sum(m.available for m in roster.by_role(side, BOMBER_ROLE) if keep(m))
    return squadron * charted // establishment


def constrained_planes(state: GameState, side: Side) -> int:
    """[43.11]/[43.13] How many of `side`'s LAND bombers are of the TYPES rule 43's typed cases
    NAME -- the He. 111, the Ju. 88D and (by the owner's ruling of 2026-07-21) the Fw. 200 C. This
    is the population from Game-Turn 35, when 43.12's wider untyped sentence expires.

    Zero for anybody but the Axis -- 43.1 is headed "AXIS MEDITERRANEAN BOMBER BASE REQUIREMENTS"
    and the Commonwealth's basing is rule 36's, entirely on the map.

    ⚠⚠ ZERO IN THE CAMPAIGN TODAY, AND THE REASON HAS CHANGED. It used to be zero because the engine
    expressed the whole Axis bomber arm as ONE abstract Ju. 87B, which rule 43 does not name -- an
    artefact of a proxy, and an open owner ruling. It is now zero because [60.32] MUSTERS NO GERMAN
    AEROPLANE AT ALL: the September-1940 Axis air force in Africa is the Regia Aeronautica entire,
    and the Luftwaffe arrives on the [34.87] Axis Airplane Reinforcement Schedule, which is
    untranscribed (game.roster says so). That is a transcription gap, not a reading -- so the law is
    written here once, in the book's own types, and the DATA decides when it binds."""
    if side != Side.AXIS:
        return 0
    named = frozenset(constrained_types())
    return _share(state, side, lambda m: m.type in named)


def german_bombers(state: GameState, side: Side) -> int:
    """[43.12] How many of `side`'s LAND bombers are GERMAN -- the subject of the one clause of
    rule 43 that names a NATIONALITY and no type at all: "Until 1/35 Game-Turn 1941, 75% of ALL
    GERMAN BOMBERS must be based in Italy/Sicily."

    A strictly wider population than `constrained_planes`: [4.44b] prints the Ju. 87B, the Ju. 87D
    and the Ju. 52/3m beside the three heavies 43.11/43.13 name, and a Stuka is a German bomber
    whether or not 43.11 lists it. Read off the chart's own `nation` cell (game.roster.nation), so
    the sentence binds on exactly the aeroplanes it is written about.

    Zero in the campaign for the same reason `constrained_planes` is -- [60.32] musters no German
    aeroplane -- but zero for a WIDER reason, which is the whole of the 2026-07-22 correction."""
    if side != Side.AXIS:
        return 0
    return _share(state, side, lambda m: roster.nation(m.type) == GERMAN)


def required_planes(state: GameState, side: Side, turn: int) -> int:
    """WHICH POPULATION RULE 43'S ITALY/SICILY REQUIREMENT IS A PERCENTAGE OF, at `turn` -- because
    the rule changes its own subject at Game-Turn 35 and the percentage alone does not say so.

    Until then it is 43.12's untyped-but-nationed "all German bombers"; from then that sentence has
    expired ("UNTIL 1/35 Game-Turn 1941") and what remains is 43.11/43.13's three named heavies.
    Everything outside the population of the moment is the Axis Player's free choice, which is
    `discretionary_pct`'s (unseeded) business and not this function's."""
    if turn < _basing()["change_turn"]:
        return german_bombers(state, side)
    return constrained_planes(state, side)


def typed_requirement_applies(state: GameState, side: Side) -> bool:
    """Does 43.11/43.13's TYPED Mediterranean requirement -- the one that survives Game-Turn 35 and
    sends half the bomber arm to Crete -- bind on any of the aeroplanes `side` flies as its LAND
    bombers? True exactly when the establishment fields one of the types the rule names."""
    return constrained_planes(state, side) > 0


def italy_sicily_planes(state: GameState, turn: int) -> int:
    """[43.12]/[43.13]/[43.25] + [43.1] The Axis bombers based in Italy/Sicily -- the force [44.42]'s
    two percentages are percentages OF (rule 44 reads this, and reads it from here, so that the
    raid's sizing and the battlefield's deduction are literally the same number).

    TWO TERMS, AND THEY ARE DIFFERENT KINDS OF THING:

      * **THE REQUIREMENT.** 43.12's untyped "75% of ALL GERMAN BOMBERS must be based in
        Italy/Sicily" until Game-Turn 35, and 43.13's printed 25% ceiling from it (the flagged
        choice of ceiling over floor recorded in data/malta_44.json) applied to the three types
        rule 43 NAMES, once 43.12 has expired. `required_planes` is that changing subject. Zero in
        the campaign today -- there is no German aeroplane in [60.32].
      * **THE CHOICE.** Everything else he owns, at `discretionary_pct` -- **UNSEEDED, and so zero**
        while the [60.32]-versus-[44.21] owner ruling is open.

    THE FIRST TERM IS RULE 43'S LARGEST EFFECT ON THE CAMPAIGN THE DAY THE LUFTWAFFE ARRIVES: the
    raidable share of a German bomber force falls from 75% to 25% at Game-Turn 35, because 43.13
    sends at least half of it to Crete and 43.25 lets only the Italy/Sicily half raid Malta. Until
    then three quarters of it is in Sicily and NOT over the desert (africa_planes).

    Taken in PLANES, not in Air Points, because that is what the [44.42] table counts and what
    44.27 bounds the African contingent by."""
    squadron = air.squadron_planes(state, Side.AXIS, LAND_ARENA, BOMBER_ROLE)
    required = required_planes(state, Side.AXIS, turn)
    return (required * italy_sicily_pct(turn) // 100
            + (squadron - required) * discretionary_pct() // 100)


def crete_planes(state: GameState, turn: int) -> int:
    """[43.13] The Axis bombers required to sit in Crete: off the battlefield AND barred from Malta.
    Only the NAMED types -- 43.13's sentence is "at least 50% of all He111's, Ju88's, and FW220's",
    and it says nothing about anybody else's aeroplanes. Zero until Game-Turn 35 on any reading, and
    zero in the campaign at every turn until [34.87] brings a German bomber to Africa."""
    return constrained_planes(state, Side.AXIS) * crete_pct(turn) // 100


def mediterranean_planes(state: GameState, turn: int) -> int:
    """[43.11] The Axis bombers rule 43 bases OFF the African battlefield: Italy/Sicily plus Crete.

    43.11 prints the total directly -- "at least 75% ... must be based in Mediterranean Bases" --
    and the engine never reads that number: it adds up 43.12's and 43.13's own two parts, which
    close on it exactly under the reading where all three cases bind (75 + 0 before Game-Turn 35,
    25 + 50 from it). Where they do not close, the missing part is the flagged one."""
    return italy_sicily_planes(state, turn) + crete_planes(state, turn)


def africa_planes(state: GameState, side: Side, turn: int) -> int:
    """[43.11]/[43.12] The aeroplanes rule 43 leaves in AFRICA -- the squadron less the ones it
    bases in the Mediterranean, in the same PLANE unit 44.27 and 39.19 are denominated in.

    THE WHOLE SQUADRON for any side rule 43 does not speak about: 43.1 is the German player's, so
    the Commonwealth's Desert Air Force passes through untouched (its basing is rule 36's, and
    entirely on the map)."""
    squadron = air.squadron_planes(state, side, LAND_ARENA, BOMBER_ROLE)
    if side != Side.AXIS:
        return squadron
    return max(0, squadron - mediterranean_planes(state, turn))


# --- [39.19] ONE MISSION PER PLANE PER GAME-TURN: MALTA OR THE DESERT ----------------------------

def establishment(state: GameState, side: Side, arena: str, role: str) -> int:
    """[43.11] The aeroplanes `side` has available in `arena` for `role` once rule 43 has taken its
    Mediterranean share -- which is the force the 38.31 readiness ledger must be measured against,
    because a bomber standing on a Sicilian field is no part of the squadron flying Land Support
    over the desert. Only the Axis LAND bomber pool is ever reduced; every other side, arena and
    role reads its whole squadron, which is what africa_planes answers for them anyway."""
    if arena == LAND_ARENA and role == BOMBER_ROLE:
        return africa_planes(state, side, state.turn)
    return air.squadron_planes(state, side, arena, role)


def strategic_planes(state: GameState, side: Side, arena: str, role: str) -> int:
    """[39.19] How many of this squadron's aeroplanes have already flown in the STRATEGIC PHASE of
    the current Game-Turn -- the African contingent the Axis sent to Malta (44.21/44.25). Absent
    from the ledger means none, and the ledger is cleared at the Game-Turn boundary (39.19 is a
    per-GAME-TURN exclusion, not a per-Operations-Stage one; state.air_strategic says so)."""
    return state.air_strategic.get(air.squadron(side, arena, role), 0)


def available_points(state: GameState, side: Side, arena: str, role: str, points: int) -> int:
    """[43.11]/[43.12] + [39.19] `points` capped by BOTH of rule 43's and rule 39.19's answers to
    the same question -- how many aeroplanes of this squadron are on this continent and have not
    already flown today -- read back out in the rating those Air Points are denominated in (34.13
    TacAir / 34.14 Bombload).

    This is the one function engine._air_points calls, so the two rules can never be applied in
    only one of the places a mission is sized from. A side rule 43 does not bind, with nothing
    committed to the Strategic Phase, gets its points back verbatim: its whole squadron of planes
    carries at least the Air Points the same squadron was totted up from."""
    left = max(0, establishment(state, side, arena, role)
               - strategic_planes(state, side, arena, role))
    return min(points, air.points_of_planes(side, role, left))
