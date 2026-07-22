"""[43.0] AXIS ITALIAN-AEGEAN AIR BASES, and [39.19] ONE MISSION PER PLANE -- the two rules that
make the Axis air force choose.

An air force that is everywhere is not an air force, it is a constant. Until this module, the
Panzerarmee's bombers raided Malta in the Strategic Air Phase (rule 44, block 5.4) and then bombed
Tobruk in all three Operations Stages of the same Game-Turn, with the SAME aeroplanes, and neither
sortie cost the other anything. Two printed rules forbid that, one structurally and one temporally:

  * **[43.11] THE STRUCTURAL HALF -- 75% OF THE BOMBERS ARE NOT IN AFRICA.** "At least 75% of all
    German He 111's, Ju88D's and FW220's must be based in Mediterranean Bases." 43.12 puts all of
    that in Italy/Sicily until Game-Turn 35; 43.13 then requires at least half of the whole force
    in **Crete**, "the remaining 25% may be based in Sicily/Italy or in Crete". A bomber standing
    on a Sicilian field is not available to fly a Land Support mission over the desert -- and, from
    Game-Turn 35, a bomber standing on Crete is not available to raid Malta either, because 43.25
    licenses only the Italy/Sicily half ("bombers based in Italy/Sicily... may also be used in raids
    on Malta"). So the Axis is REQUIRED to keep a Malta-capable bomber force off the battlefield,
    and required to keep half of it where it can do neither job.

  * **[39.19] THE TEMPORAL HALF -- MALTA OR THE DESERT, NOT BOTH.** "Generally, a plane may fly only
    one mission per Operations Stage or Strategic Phase... A PLANE FLYING A MISSION IN AN OPERATIONS
    STAGE MAY NOT FLY IN THE STRATEGIC PHASE OF THAT GAME-TURN AND VICE VERSA." This binds on the
    one force that can be in both places: 44.21/44.25 let the Axis add **African-based planes** to
    the Malta raid ("in no case may the Axis Player assign more planes of any one type from map
    bases than are assigned from the Availability Tables", 44.27). Every African bomber he sends to
    Malta is one that does not fly over the desert for the rest of that Game-Turn. That is the
    choice, it is the Axis Player's, and it is now his to make (Policy.malta_africa_planes).

⚠⚠ OWNER RULING NEEDED, AND IT IS THE ONE JUDGEMENT IN THIS BLOCK. WRITTEN OUT IN FULL AT `applies`
BELOW AND AT `constrained_types_43_11` IN data/malta_44.json. In short: 43.11 constrains THREE NAMED
AIRCRAFT TYPES -- "all German He 111's, Ju88D's and FW220's" -- and this engine fields none of them.
game.air expresses the whole abstract Axis strike pool as the **Ju. 87B**, the Stuka: a dive bomber,
not on 43's list, and precisely the type that did fly from African fields. So the deduction is
implemented here against the NAMED LIST and currently deducts nothing, which is the transcribe-
never-invent answer: the law is written once and the DATA decides whether it binds. It was measured
the other way first, and the measurement is why the ruling is being asked for rather than taken --
applied to the whole abstract pool, 75% of two aeroplanes is two aeroplanes, and the Luftwaffe flies
NOTHING over the desert for a hundred and eleven Game-Turns.

WHAT RULE 43 THEREFORE STILL DOES, TODAY, WITH NO RULING: it shrinks the Malta raid on schedule.
Before Game-Turn 35 the Malta-capable force is 75% of the establishment; from Game-Turn 35, 43.13
sends at least half of it to CRETE and 43.25 does not license Crete to raid Malta, so the raidable
share falls to 25%. That is the "Malta-capable bomber force kept off the battlefield" arriving as a
number the Axis cannot spend, and it is already what rule 44 sizes its raids from.

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


def mediterranean_pct(turn: int) -> int:
    """[43.11] The percentage of the Axis bomber force that must be based in a Mediterranean base
    -- Italy, Sicily or Crete -- and is therefore not on the African battlefield. Seventy-five,
    for the whole war: 43.12 and 43.13 redistribute that force between the three bases, they never
    change its size. `turn` is taken for symmetry with the two functions below (and because a
    scenario that ever charts a different figure will want it); the printed answer does not move."""
    return _basing()["mediterranean_pct"]


def italy_sicily_pct(turn: int) -> int:
    """[43.12]/[43.13] The percentage based in ITALY/SICILY -- the only part of the Mediterranean
    force 43.25 lets raid Malta. 75 until Game-Turn 35, 25 from it (the printed ceiling on 43.13's
    permissive "the remaining 25% MAY be based in Sicily/Italy or in Crete"; the choice of the
    ceiling over the floor is the flagged policy call recorded in data/malta_44.json)."""
    b = _basing()
    return b["before_turn_35_pct"] if turn < b["change_turn"] else b["from_turn_35_pct"]


def crete_pct(turn: int) -> int:
    """[43.13] The percentage based in CRETE -- nothing until Game-Turn 35, at least half the force
    from it. These bombers may not raid Malta (43.25 grants that to the Italy/Sicily half alone) and
    they are not in Africa, so from Game-Turn 35 the Axis is holding half his bomber arm where it
    can do neither job. 43.23's four Suez OpStages a month are a further tax on a force that already
    does nothing in this engine, and are therefore not modelled (see the module docstring)."""
    b = _basing()
    return 0 if turn < b["change_turn"] else b["crete_pct_from_turn_35"]


def africa_pct(turn: int) -> int:
    """[43.11] What is left for the desert: the whole minus the Mediterranean requirement."""
    return 100 - mediterranean_pct(turn)


def _pool(state: GameState, side: Side) -> int:
    """`side`'s whole LAND-arena bomber establishment in Air Points, before any of 43's cuts."""
    return air.squadron_points(state, side, LAND_ARENA, BOMBER_ROLE)


def constrained_types() -> tuple[str, ...]:
    """[43.11]/[43.13] The three aircraft types rule 43 names, transcribed: "all German HE 111's,
    JU88D's and FW220's". 43.13 repeats the same three. No other aircraft in the game is required to
    be based in the Mediterranean by any case of rule 43."""
    return tuple(_basing()["constrained_types_43_11"])


def applies(state: GameState, side: Side) -> bool:
    """Does rule 43's Mediterranean basing requirement bind on the force `side` flies as its LAND
    bombers? Three conditions, and the third is the ruling.

      * THE GERMAN PLAYER, and only him: 43.1 is headed "AXIS MEDITERRANEAN BOMBER BASE
        REQUIREMENTS" and every case in it names German aircraft. The Commonwealth's basing is rule
        36's and is entirely on the map.
      * There must be a LAND bomber pool for it to bind on -- so every air-less scenario, and every
        scenario whose Axis flies no strike, is untouched.
      * AND THE TYPE MUST BE ONE OF THE THREE THE RULE NAMES (constrained_types).

    ⚠⚠ OWNER RULING NEEDED -- scan: rule 43.11 and 43.13, docs/rules/43-axis-italian-aegean-air-
    bases.md; the aircraft charts at PDF pages 144-145.

    THE THIRD CONDITION IS FALSE TODAY, so this function returns False and rule 43 deducts nothing
    from the African battlefield. game.air.REPRESENTATIVE_AIRCRAFT expresses the Axis LAND strike
    pool as the **Ju. 87B** -- a Stuka, which 43 does not name and which historically operated from
    forward African strips. The alternative reading, that 43's percentages apply to the whole
    abstract Axis bomber arm because that arm STANDS IN for a force which includes He 111s, was
    built and MEASURED FIRST, and it is why this is a ruling and not a decision: the campaign's Axis
    fields six strike Air Points -- two Ju. 87B on the 34.14 Bombload bridge -- and 25% of two
    aeroplanes, floored, is NONE. Every Axis Land Support mission in the war is grounded, by a rule
    written about three bomber types the engine does not own.

    So the deduction is coded against the NAMED LIST and left to the data, which is this project's
    own rule 1: transcribe the law, let the chart decide the magnitude. The day [34.6]/[59.3]'s
    Initial Air Strengths roster is transcribed and a He 111 or Ju 88D enters the Axis order of
    battle, three quarters of it leaves the desert with no further code.

    THE OWNER'S CHOICE, stated plainly, is between (a) this -- 43 is silent until the roster names
    a type it constrains -- and (b) treating our one abstract Axis bomber as a stand-in for the
    whole Luftwaffe bomber arm, in which case its Land Support must be cut by 75% and, at the
    present proxy scale, extinguished."""
    if side != Side.AXIS or _pool(state, side) <= 0:
        return False
    return air.REPRESENTATIVE_AIRCRAFT[(side, BOMBER_ROLE)] in constrained_types()


def italy_sicily_planes(state: GameState, turn: int) -> int:
    """[43.12]/[43.13]/[43.25] The Axis bombers based in Italy/Sicily -- the force [44.42]'s two
    percentages are percentages OF (rule 44 reads this, and reads it from here so that the raid's
    sizing and the battlefield's deduction can never disagree).

    THIS IS RULE 43'S LIVE EFFECT ON THE CAMPAIGN TODAY. Whatever the owner rules about the African
    deduction (see `applies`), the raidable share falls from 75% to 25% at Game-Turn 35, because
    43.13 sends at least half the force to Crete and 43.25 lets only the Italy/Sicily half raid
    Malta. The Axis's Malta war gets structurally harder in June 1941, by a printed rule.

    ⚠ THE ESTABLISHMENT IT IS A PERCENTAGE OF IS A PROXY, flagged here, at malta.italy_sicily_planes
    and in data/malta_44.json: 44.22's Malta force is aircraft "based permanently in Italy and
    Sicily AND OTHERWISE NOT AVAILABLE TO THE AXIS PLAYER", which no counter in this order of battle
    represents, so its SIZE is read off the one Axis bomber pool the engine does field.

    Taken in PLANES, not in Air Points, because that is what the [44.42] table counts and what
    44.27 bounds the African contingent by."""
    return air.squadron_planes(state, Side.AXIS, LAND_ARENA, BOMBER_ROLE) * italy_sicily_pct(turn) // 100


def crete_planes(state: GameState, turn: int) -> int:
    """[43.13] The Axis bombers required to sit in Crete: off the battlefield AND barred from Malta."""
    return air.squadron_planes(state, Side.AXIS, LAND_ARENA, BOMBER_ROLE) * crete_pct(turn) // 100


def africa_points(state: GameState, side: Side, arena: str, role: str, points: int) -> int:
    """[43.11] `points` of committed Air Points capped by what rule 43 leaves in AFRICA.

    The cap is a percentage of the side's whole establishment (43's percentages are of the FORCE,
    not of a tasking), and it binds only on the Axis LAND bomber pool -- every other side, arena and
    role passes through untouched, so nothing but the Luftwaffe's Land Support changes.

    Rounded DOWN, which is the direction 43.11's "AT LEAST 75%" points: a fraction of an aeroplane
    left over in Africa is one the Mediterranean requirement claims."""
    if arena != LAND_ARENA or role != BOMBER_ROLE or not applies(state, side):
        return points
    return min(points, _pool(state, side) * africa_pct(state.turn) // 100)


def africa_planes(state: GameState, side: Side, turn: int) -> int:
    """[43.11] The aeroplanes rule 43 leaves in Africa -- the establishment less the Mediterranean
    requirement, in the same PLANE unit 44.27 and 39.19 are denominated in. Zero for any side rule
    43 does not bind."""
    if not applies(state, side):
        return air.squadron_planes(state, side, LAND_ARENA, BOMBER_ROLE)
    return air.squadron_planes(state, side, LAND_ARENA, BOMBER_ROLE) * africa_pct(turn) // 100


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
    """[43.11] + [39.19] `points` capped by BOTH: what rule 43 leaves in Africa, and what 39.19
    leaves un-flown after the Strategic Phase took its share.

    This is the one function engine._air_points calls, so the two rules can never be applied in
    only one of the places a mission is sized from. A side rule 43 does not bind, with nothing
    committed to the Strategic Phase, gets its points back verbatim -- so every scenario without an
    Axis Malta raid stays byte-identical."""
    capped = africa_points(state, side, arena, role, points)
    flown = strategic_planes(state, side, arena, role)
    if flown <= 0:
        return capped
    left = max(0, establishment(state, side, arena, role) - flown)
    return min(capped, left * air.points_per_plane(side, role))
