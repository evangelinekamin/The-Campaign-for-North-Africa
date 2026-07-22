"""[43.0] AXIS ITALIAN-AEGEAN AIR BASES, and [39.19] ONE MISSION PER PLANE -- the two rules that
make the Axis air force choose.

An air force that is everywhere is not an air force, it is a constant. Until this module, the
Panzerarmee's bombers raided Malta in the Strategic Air Phase (rule 44, block 5.4) and then bombed
Tobruk in all three Operations Stages of the same Game-Turn, with the SAME aeroplanes, and neither
sortie cost the other anything. Two printed rules forbid that, one structurally and one temporally:

  * **[43.12] THE STRUCTURAL HALF -- THREE QUARTERS OF THE BOMBERS ARE NOT IN AFRICA.** "Until 1/35
    Game-Turn 1941, 75% OF ALL GERMAN BOMBERS must be based in Italy/Sicily." That sentence names
    no type: it is every German bomber in the game, which is exactly the one abstract Axis LAND
    strike pool this engine fields. A bomber standing on a Sicilian field is not available to fly a
    Land Support mission over the desert -- and it is the same bomber rule 44 sizes the Malta raid
    from, so it may not be counted in both places. From Game-Turn 35 that sentence EXPIRES and what
    is left is typed: see THE OWNER RULING below.

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
⚠⚠ OWNER RULING NEEDED -- and it is now two questions, not one. Written out in full at
`typed_requirement_applies` below and at `constrained_types_43_11` in data/malta_44.json.

  (1) **FROM GAME-TURN 35, DOES RULE 43 BIND ON A Ju. 87B AT ALL?** 43.12's untyped sentence covers
      Game-Turns 1-34 and then expires. What replaces it is TYPED: 43.11 "at least 75% of all
      German He 111's, Ju88D's and FW220's must be based in Mediterranean Bases" and 43.13 "at
      least 50% of all He111's, Ju88's, and FW220's must be based in Crete". This engine fields
      none of those: game.air expresses the whole abstract Axis strike pool as the **Ju. 87B**, a
      dive bomber, and precisely the type that did fly from African fields. Read strictly, the
      Crete requirement therefore binds on nothing, and THE LUFTWAFFE'S AFRICAN BOMBER FORCE
      TRIPLES IN JUNE 1941 (25% of the pool before Game-Turn 35, 75% after) -- a discontinuity
      produced by a type list, not by the war. Read as a stand-in (our one abstract bomber
      represents the whole German bomber arm), Crete takes its 50% and Africa stays at 25% all war.
      The code takes the STRICT reading and leaves the Crete term unseeded, which is this project's
      rule 1: transcribe the law, let the DATA decide the magnitude. `crete_planes` returns 0 until
      a named type enters the order of battle, and the whole change is that list.

  (2) **WHAT IS "FW220"?** 43.11 and 43.13 both name it. **No such aircraft exists in this game.**
      The [4.44b] German Aircraft Characteristics Chart (PDF page 145, rendered at 300 dpi and read
      with eyes) prints exactly eight German bombers/transports/recon types: Ar. 196, Fw. 200 C,
      He. 111, Hs. 126, Ju. 52/3m, Ju. 87B, Ju. 87D, Ju. 88D. The nearest Focke Wulf bomber is the
      **Fw. 200 C** (Range 205, Bomb 14). Whether 43.11's "FW220" is a misprint for it is a
      book-internal inconsistency of the 54.17 class, so it is NOT decided here: the constrained
      list carries the two types that map onto printed chart rows unambiguously (He. 111, Ju. 88D)
      and the third is left UNSEEDED under `unresolved_type_43_11` in the data file.

  Note the names in that list are the CHART's, verbatim, periods and all -- "He. 111", not
  "He 111" -- because `typed_requirement_applies` is an exact string test against the keys of
  game.air.AIRCRAFT, which are the chart's printed names. A list transcribed off the RULE's prose
  instead ("He 111", "FW 220") could never match a transcribed row, and would have failed silently.

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
  * **So the Axis raid on Malta is free of airframes.** 44.28's pro-rata split of losses between
    planes in play and planes not in play (the whole point of that case) has nothing to split, and
    Malta's 19 fighters and 17 AA Points ([60.46], transcribed) never fire. The raid is stronger
    than the book's raid, and the Commonwealth's only reply is the [44.5] repair table.
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

from . import air, logistics_data
from .events import Side
from .state import GameState

# The one arena and role rule 43 speaks about: the Axis BOMBER force. 43 says nothing about
# fighters (they are 40/45's business) and nothing about army-cooperation reconnaissance.
BOMBER_ROLE = "strike"
LAND_ARENA = "LAND"


def _basing() -> dict:
    return logistics_data.malta_italy_sicily_basing_43_1()


def italy_sicily_pct(turn: int) -> int:
    """[43.12]/[43.13] The percentage of the Axis bomber force based in ITALY/SICILY -- the only
    part of the Mediterranean force 43.25 lets raid Malta. 75 until Game-Turn 35 ("75% of all
    German bombers", untyped), 25 from it (the printed ceiling on 43.13's permissive "the remaining
    25% MAY be based in Sicily/Italy or in Crete"; the choice of the ceiling over the floor is the
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
    prints them (PDF page 145) so that an exact match against game.air.AIRCRAFT is possible at all:
    "He. 111" and "Ju. 88D".

    ⚠ THE RULE NAMES A THIRD, "FW220", AND THE CHART DOES NOT PRINT IT. That is an OWNER RULING
    (see the module docstring); it is left unseeded in data/malta_44.json rather than guessed at
    the Fw. 200 C."""
    return tuple(_basing()["constrained_types_43_11"])


def typed_requirement_applies(state: GameState, side: Side) -> bool:
    """Does 43.11/43.13's TYPED Mediterranean requirement -- the one that survives Game-Turn 35 and
    sends half the bomber arm to Crete -- bind on the force `side` flies as its LAND bombers?

      * THE GERMAN PLAYER, and only him: 43.1 is headed "AXIS MEDITERRANEAN BOMBER BASE
        REQUIREMENTS" and every case in it names German aircraft. The Commonwealth's basing is rule
        36's and is entirely on the map.
      * There must be a LAND bomber pool for it to bind on -- so every air-less scenario, and every
        scenario whose Axis flies no strike, is untouched.
      * AND THE TYPE MUST BE ONE OF THE ONES THE RULE NAMES (constrained_types).

    ⚠⚠ OWNER RULING NEEDED, question (1) of the module docstring -- scan: rule 43.11 and 43.13 at
    PDF page 61, the [4.44b] aircraft chart at PDF page 145.

    THE THIRD CONDITION IS FALSE TODAY, so this returns False and `crete_planes` stays zero: from
    Game-Turn 35 no CRETE requirement is laid on a Ju. 87B, and the African contingent rises from
    25% of the pool to 75%. It is NOT the whole of rule 43 going quiet. 43.12's untyped "75% of all
    German bombers must be based in Italy/Sicily" governs Game-Turns 1-34 on any reading and is
    applied; and from Game-Turn 35 the Axis still keeps 43.13's printed 25% ceiling in Italy/Sicily
    (the flagged 5.4 policy choice that keeps a Malta war at all), which is deducted from Africa
    like any other aeroplane standing on a Sicilian field.

    THE OWNER'S CHOICE, stated plainly, is between (a) this -- the typed cases are silent until the
    roster names a type they constrain, and the Luftwaffe's desert bomber force triples in June 1941
    -- and (b) treating our one abstract Axis bomber as a stand-in for the whole Luftwaffe bomber
    arm, in which case Crete takes its 50% and the African contingent stays at 25% for the whole
    war. Flipping data/malta_44.json's constrained list is the whole of (b)."""
    if side != Side.AXIS:
        return False
    if air.squadron_points(state, side, LAND_ARENA, BOMBER_ROLE) <= 0:
        return False
    return air.REPRESENTATIVE_AIRCRAFT[(side, BOMBER_ROLE)] in constrained_types()


def italy_sicily_planes(state: GameState, turn: int) -> int:
    """[43.12]/[43.13]/[43.25] The Axis bombers based in Italy/Sicily -- the force [44.42]'s two
    percentages are percentages OF (rule 44 reads this, and reads it from here, so that the raid's
    sizing and the battlefield's deduction are literally the same number).

    THIS IS RULE 43'S LARGEST EFFECT ON THE CAMPAIGN. The raidable share falls from 75% to 25% at
    Game-Turn 35, because 43.13 sends at least half the force to Crete and 43.25 lets only the
    Italy/Sicily half raid Malta. The Axis's Malta war gets structurally harder in June 1941, by a
    printed rule -- and until then three quarters of his bomber arm is in Sicily and NOT over the
    desert (africa_planes).

    ⚠ THE ESTABLISHMENT IT IS A PERCENTAGE OF IS A PROXY, flagged here, at malta.italy_sicily_planes
    and in data/malta_44.json: [60.32] musters the real Regia Aeronautica in the hundreds where the
    campaign seeds the Axis two dozen strike Air Points (scenario._AXIS_AIR_STRIKE -- five Ju. 87B,
    of which this leaves three in Sicily), because [34.6]/[59.3]'s Initial Air Strengths roster is
    untranscribed. The RATIOS above are the book's; the force they divide is ours.

    Taken in PLANES, not in Air Points, because that is what the [44.42] table counts and what
    44.27 bounds the African contingent by."""
    return air.squadron_planes(state, Side.AXIS, LAND_ARENA, BOMBER_ROLE) * italy_sicily_pct(turn) // 100


def crete_planes(state: GameState, turn: int) -> int:
    """[43.13] The Axis bombers required to sit in Crete: off the battlefield AND barred from Malta.

    ⚠⚠ ZERO TODAY, AND THAT IS THE UNSEEDED HALF OF THE OWNER RULING (question (1) of the module
    docstring): 43.13's requirement is written about NAMED heavy bomber types and the engine fields
    a Ju. 87B. The moment a named type enters the order of battle, half the bomber arm goes
    to Crete and `africa_planes` falls back to a quarter of the force for the rest of the war."""
    if not typed_requirement_applies(state, Side.AXIS):
        return 0
    return air.squadron_planes(state, Side.AXIS, LAND_ARENA, BOMBER_ROLE) * crete_pct(turn) // 100


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
    return min(points, left * air.points_per_plane(side, role))
