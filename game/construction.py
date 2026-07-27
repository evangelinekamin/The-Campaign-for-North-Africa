"""[24.0] CONSTRUCTION -- and the one asymmetry the rulebook writes into the desert by hand.

    "Fortifications, minefields, air facilities, repair facilities, roads, RAILROADS and SUPPLY
     DUMPS all come into existence (for the most part) through construction. Construction entails
     the use of manpower under the leadership of Engineers, along with the expenditure of TIME and
     SUPPLIES. Construction occurs in the Construction Segment of the Organization Phase, and it may
     be affected by weather. Units involved in construction may not expend any Capability Points
     during an Operations Stage; otherwise that construction is halted." -- 24.0

THE TWO SLICES BUILT HERE, and they are the two the campaign was starving for.

  [24.6] THE RAILWAY. "The only units that may build railroads are the two New Zealand railroad
    construction companies (the 10th and the 13th)" (24.61). One company takes two Operations Stages
    per hex of new track; two companies stacked take one (24.62). Each hex costs ONE Store Point,
    present with the engineer and actually expended in the Construction Segment (24.64). No
    enemy-controlled or enemy-occupied hex may be built (24.65). And the line grows one way only:
    "the Alexandria-Mersa Matruh-Tobruk line may be constructed in only one specific direction.
    Construction must start from the last completed hex extending from Mersa Matruh and grow WESTWARD
    towards Tobruk. NO HEX MAY BE SKIPPED... Unbuilt railroad hexes simply do not exist" (24.67).

    READ THE UNITS COLUMN. The Construction Chart's Build row for Railroad is NZRRC -- and there is
    no Axis row at all. The Panzerarmee has no railway construction in this game because it had none
    in this war: the Eighth Army could push its railhead west and be fed off it, and the Axis could
    only lengthen a lorry haul from Benghazi. That is not a thumb on the scale, it is the scale. The
    Axis's own answer -- 54.4, running captured rolling stock over five contiguous controlled rail
    hexes -- stays deferred and flagged, as it was.

  [24.9] THE SUPPLY DUMP, and the distinction the engine had collapsed. "A supply dump may be
    constructed by having ANY ONE TOE STRENGTH POINT OF ANY TYPE expend three Capability Points and
    20 Store Points in a hex." No engineer. No elapsed time. And then the Note, which is the whole
    point of the rule:

      "Supplies may be placed in a hex NOT containing a constructed supply dump. The only restriction
       on the use of such supplies is that trucks 'in convoy' may not load such supplies."

    So dropping a load in the desert is FREE (54.11: "any hex can be used as a supply dump"; 54.35:
    "supplies may be moved from any one spot and dumped in another"), and the army may eat off it at
    once. What the three CP and the twenty Stores BUY is the right to give supply BACK to a lorry --
    which is the one thing a bucket brigade needs of its intermediate depots (53.14/54.16). A pile is
    a sink; a constructed dump is a LINK. That is why the Commonwealth chain could never extend past
    the last depot somebody seeded in September 1940.

PHASE 8.2 ADDED TWO MORE SLICES: 24.3 (minefields) and 24.4 (fortifications) -- see the REAL_MINEFIELD
/ DUMMY_MINEFIELD / FORT / CLEAR_MINEFIELD items below and game.minefields for rule 26's effects.
Both are gated on the general Engineering capabilities (state.Unit.engineer: 'ENGINEER' for an
Engineer battalion/company, 'HQ_ENGINEER' for 23.14's HQ with an E beside its Stacking Points),
which no OOB in this repo currently seeds -- the flagged gap game.minefields' own docstring names.
Built and correct; unreachable by any live scenario until that OOB gap closes.

The ONE anti-minefield capability that IS reachable is 23.15's: the two Commonwealth tank battalions
refitted with Scorpion flails (42/44 RTR, data/reinforcements_campaign.json, arriving GT99, and
on-map in the [63.0] El Alamein scenarios). They carry engineer='SCORPION' from the OOB's model row
and, per 23.15, count as engineers ONLY for anti-minefield purposes and ONLY while they hold six or
more Scorpion TOE Strength Points -- so they clear belts ([24.18]'s Real Minefield row: "Any E or
tank bn with 6+ TOE of Scorpions") and escort movers through them (26.24), and they build nothing.

DELIBERATELY NOT BUILT (24 is a big rule and this is the smallest faithful slice of it):
  * 24.5 roads (the 1 SA Road Construction Battalion is seeded and idle -- it exists, it is the
    rulebook's unit, and it has no unfinished-road overlay to build on because the map's
    unfinished-road hexes are untranscribed), 24.7 air facilities, 24.8 repair facilities, and the
    24.18 Demolition Chart's rail/road/port destruction (24.66 and the rest of §6 there).
  * 24.21's ten Water Points per site in Hot weather, and 24.23's pinned-by-artillery halt.
  * 52.22's water pipeline following the new rails ("the Commonwealth Player may consider any
    OPERATING Railroad hex to be a pipeline for water"). It is a real rule and it falls out of a
    built rail hex, but a pipeline hex is an UNLIMITED water source (52.23), so extending it means
    minting supply mid-game -- a conservation seam this slice does not need: the coast road the
    railway follows is already strung with wells (Sollum, Bardia, Tobruk, Derna are all major-city
    water sources, 52.13), which is why both armies used it.
  * The [24.18] Demolition Chart's Fake Minefield row ("Clear | Any unit | 1 Op Stage"), whose
    Restrictions cell -- "cleared at the end of the Movement Segment in which it is entered" --
    is 26.14's automatic sweep, already built (engine._sweep_revealed_dummies). No SEPARATE
    any-unit demolition beat is wired for a dummy belt; an Engineer may still lift one deliberately
    (26.13's Op-Stage), which is a superset of what the chart's row describes.
"""
from __future__ import annotations

from . import minefields as mf
from . import tactics
from . import wells
from .events import Control, Side
from .hexmap import Coord
from .movement import edge
from .state import GameState, Unit

RAIL = "RAIL"                    # 24.6: a hex of new track
DUMP = "DUMP"                    # 24.9: a supply dump
REAL_MINEFIELD = "REAL_MINEFIELD"        # 24.3/26.11
DUMMY_MINEFIELD = "DUMMY_MINEFIELD"      # 24.3/26.11
FORT = "FORT"                            # 24.4: one Level of fortification
CLEAR_MINEFIELD = "CLEAR_MINEFIELD"      # 26.13/24.38: an Engineer's CP-free Op-Stage in the hex

# [24.11]/[24.32]/[24.42] Op-Stages of Construction-Segment work each item needs banked before its
# Completion Step fires -- the SAME "company-stages" counter RAIL_COMPANY_STAGES already reads,
# generalised: a project is complete once GameState.construction[(item, hex)] reaches this.
PROJECT_STAGES: dict[str, int] = {
    RAIL: 2,                                   # 24.62 (two NZRRC company-stages)
    REAL_MINEFIELD: mf.MINEFIELD_OP_STAGES,    # 24.32: one, real or dummy alike
    DUMMY_MINEFIELD: mf.MINEFIELD_OP_STAGES,
    FORT: mf.FORT_OP_STAGES,                   # 24.42: three
    CLEAR_MINEFIELD: 1,                        # 26.13: one full Operations Stage, CP-free
}

# [24.62] "One NZRRC company requires TWO OpStages to build one hex of new track. TWO NZRRC
# companies in the same hex can build one hex of new track in ONE OpStage." Both sentences are one
# number if the work is counted in COMPANY-STAGES: a hex of track is two of them, and each company
# on the site contributes one per Construction Segment. No pair special-case, no branch.
RAIL_COMPANY_STAGES = 2
RAIL_STORES = 1                  # 24.64: one Store Point per railroad hex, expended in the Segment

DUMP_CP = 3                      # 24.9: three Capability Points...
DUMP_STORES = 20                 # 24.9: ...and 20 Store Points (Logistics Game), by any 1 TOE SP

# [24.22] "No construction may occur in a hex affected by a sandstorm or a rainstorm. This does not
# stop construction entirely; it only prohibits that Operations Stage from counting towards
# construction time costs." The storm is localised (29.7): construction halts in the 2-3 sections
# the storm covers and proceeds elsewhere, so the test is on the BUILD HEX's section (weather_at).
FOUL = ("sandstorm", "rainstorm")


def builds_rail(u: Unit) -> bool:
    """[24.61] May this unit BUILD railroad? Only the two New Zealand Railroad Construction
    companies -- "the NZRRC companies are considered engineering companies, but they may be used
    only for RR work" (24.61), "used solely for the construction and repair of Railroads" (23.13).
    Every other engineer in the game may REPAIR destroyed track (24.61) and none of them may lay
    new track; repair is deferred with the rest of 24.66, so this is the whole test."""
    return u.engineer == RAIL


def rail_head(state: GameState) -> "Coord | None":
    """The last COMPLETED hex of the surveyed line -- the Railhead marker of 24.67. The hex the next
    one must extend from, and (once the Eighth Army starts laying track) the end of the operating
    railway the trains run to.

    Read off the map's own rail edge-set rather than off a counter, so there is exactly one truth
    about how far the railway reaches. state.rail_line OPENS with the scenario's existing terminus --
    Mersa Matruh, where rule 60.7 leaves it -- and the hexes are built strictly in order (rail_next
    below refuses to skip one), so the last hex of the line that carries a rail edge IS the head."""
    built = {h for e in state.terrain.rails for h in e}
    head = None
    for hx in state.rail_line:
        if hx not in built:
            break
        head = hx
    return head


def rail_next(state: GameState) -> "Coord | None":
    """[24.67] The ONE hex of new track that may be laid next: the first hex of the surveyed line
    that is not built. "Construction must start from the last completed hex extending from Mersa
    Matruh and grow westward towards Tobruk. No hex may be skipped." None once the line is complete,
    or for any scenario that surveys none."""
    built = {h for e in state.terrain.rails for h in e}
    return next((hx for hx in state.rail_line if hx not in built), None)


def rail_buildable(state: GameState, side: Side, hx: Coord) -> bool:
    """[24.65]/[24.22] May track be laid on `hx` this Operations Stage? Not on a hex the enemy
    CONTROLS or OCCUPIES -- "no Enemy-controlled or Enemy-occupied railroad hex may be built or
    rebuilt" (24.65) -- and not in a sandstorm or a rainstorm (24.22).

    24.65 is what makes the railway FOLLOW the army rather than lead it, and it is the loop the
    whole campaign turns on: the Eighth Army takes ground, the railhead comes up behind it, and the
    trains then feed the ground it took (54.35/engine._rail_stops). Neither half moves without the
    other, which is the desert war."""
    if state.weather_at(hx) in FOUL:                    # 24.22 / 29.7: no construction in a storm hex
        return False
    if fort_under_construction(state, hx):              # 24.46: not while a Level is going up here
        return False
    enemy = Control.AXIS if side == Side.ALLIED else Control.ALLIED
    return (state.control_of(hx) != enemy
            and not any(u.is_combat for u in state.enemies_at(hx, side)))


def rail_edge(state: GameState, hx: Coord) -> "frozenset | None":
    """The rail edge a completed hex adds to the map: `hx` joined to the head it extends from
    (24.67). None if `hx` is not the next hex of the surveyed line."""
    head = rail_head(state)
    return edge(head, hx) if head is not None else None


def _construction_dumps(state: GameState, side: Side, hx: Coord):
    """The friendly dumps standing at `hx` that a Construction Segment may draw from -- 24.13's
    "on hand in the hex", excluding an airfield's own pile (36.17: the SGSUs', not the army's) and
    an oasis (52.3: funds upkeep, not construction)."""
    return (s for s in state.supplies
            if s.side == side and s.hex == hx and not s.is_dummy
            and not s.air_dump and not wells.is_water_source(s))


def commodity_at(state: GameState, side: Side, hx: Coord, commodity: str) -> int:
    """[24.13] The Points of `commodity` a Player has "on hand IN THE HEX" to expend on
    construction: what his own dumps standing on the site hold. 24.13 is explicit that the
    supplies "must BEGIN the Construction Segment in the given hex" -- construction is not fed
    down a supply trace, it is fed out of the pile the engineers are standing on."""
    attr = commodity.lower()
    return sum(getattr(s, attr) for s in _construction_dumps(state, side, hx))


def commodity_draw(state: GameState, side: Side, hx: Coord, commodity: str,
                   qty: int) -> list[tuple[str, int]]:
    """[24.13]/[32.15] Spend `qty` Points of `commodity` OUT OF THE HEX: ((supply_id, qty), ...),
    the piles drawn from and how much each gives up. Field dumps first (by id), the bottomless
    rule-57 base last, so a garrison spends what it carried before it spends Cairo's.

    THE BUG THIS FIXES, and it is a real one that predates rule 32.32. `commodity_at` counts what
    EVERY friendly dump on the hex holds -- 24.13's "on hand in the hex", and correct, since 32.15
    lets a Player rearrange supplies among co-located Supply Units for free -- but engine._build_dump
    used to consume the whole quantity from ONE of them (`dump_at`, the first by id). Two dumps
    sharing a hex with the stores split between them passed the check and over-drained the named
    one: MEASURED, "supply AL-Field-22-87 has negative STORES pool -6", an InvariantViolation that
    took the whole campaign down. The check counts the hex, so the charge must come out of the hex."""
    attr = commodity.lower()
    legs: list[tuple[str, int]] = []
    here = sorted(_construction_dumps(state, side, hx), key=lambda s: (s.base, s.id))
    for s in here:
        take = min(qty, getattr(s, attr))
        if take > 0:
            legs.append((s.id, take))
            qty -= take
        if qty == 0:
            break
    return legs


def stores_at(state: GameState, side: Side, hx: Coord) -> int:
    """[24.13] `commodity_at` for Store Points -- the original, still-used single-commodity
    accessor (24.6 railroads, 24.9 supply dumps need only Stores)."""
    return commodity_at(state, side, hx, "STORES")


def stores_draw(state: GameState, side: Side, hx: Coord, qty: int) -> list[tuple[str, int]]:
    """`commodity_draw` for Store Points -- see stores_at."""
    return commodity_draw(state, side, hx, "STORES", qty)


def dump_at(state: GameState, side: Side, hx: Coord):
    """The side's own dump standing on `hx` -- the heap of supplies a 24.9 construction turns into a
    proper dump. Rule 24.9 lets a Player designate ANY hex a supply dump, empty or not; ours requires
    the pile to already be there, because an empty dump on an empty hex is a counter with no job and
    the engine's one-dump-per-hex rule (engine._dump_on) would then have to arbitrate between it and
    the next lorry's unload."""
    return next((s for s in sorted(state.supplies, key=lambda s: s.id)
                 if s.side == side and s.hex == hx and not s.is_dummy and not s.base
                 and not s.air_dump), None)         # 36.17: the airfield's own pile is not the army's


def can_construct_dump(state: GameState, side: Side, u: Unit, dump) -> bool:
    """[24.9] May `u` construct `dump` into a proper supply dump this Construction Segment? "Any one
    TOE Strength Point of any type" -- so any unit at Strength, engineer or not, standing on the hex,
    with the three Capability Points still unspent and the twenty Store Points on hand in the hex.

    An already-constructed dump is not re-built (the 60.34 staging depots, the ports of arrival and
    the rule-57 bases are all constructed by construction), and a rule-57 base is not a Supply Dump
    counter at all -- the same exemption engine._capture_dumps and 54.14 make."""
    return (dump is not None and not dump.constructed and not dump.base and not dump.is_dummy
            and u.hex == dump.hex and u.effective_strength >= 1
            and u.cpa - u.cp_used >= DUMP_CP
            and not fort_under_construction(state, u.hex)      # 24.46
            and stores_at(state, side, u.hex) >= DUMP_STORES)


# --- [24.3] CONSTRUCTING MINEFIELDS ---------------------------------------------------------------

def builds_engineering(u: Unit) -> bool:
    """[24.42] General Engineering capability -- the Construction Chart's "AnyE", the units column
    of its 1-Level-of-Fortification row: "any engineer battalion, engineer company, or headquarters
    unit with engineering capability", EITHER SIDE. Distinct from 'RAIL' and 'ROAD' (23.13 restricts
    those two counters to their one named specialty), from `lays_minefield` below (the chart's
    narrower EBn/ECoy/CHQ-E), and from game.minefields.is_engineer (which additionally admits a
    23.15 Scorpion battalion, an anti-minefield capability that builds nothing)."""
    return u.engineer in (mf.GENERAL_ENGINEER, mf.HQ_ENGINEER)


def lays_minefield(u: Unit) -> bool:
    """[24.31]/[24.17] Who may LAY a belt -- and it is not everyone who may build a fortification.
    24.31 (prose): "Minefields may be constructed by any Engineering unit (or COMMONWEALTH HQ
    Engineers)." The Construction Chart's Real/Fake Minefield rows agree, unit for unit: "EBn,
    ECoy or CHQ-E", where its own key reads CHQ-E = "ALLIED headquarters with engineering
    capability" (as against AnyE's "headquarters unit with engineering capability", either side,
    on the Fortification row). So an AXIS HQ with engineering capability may raise a fortification
    and may not sow mines -- an asymmetry the book states twice and this engine now keeps.

    A 23.15 Scorpion battalion builds nothing: it "possesses only ANTI-MINEFIELD capabilities"."""
    if u.engineer == mf.GENERAL_ENGINEER:                  # EBn / ECoy, either side
        return True
    return u.engineer == mf.HQ_ENGINEER and u.side == Side.ALLIED      # CHQ-E only


def fort_under_construction(state: GameState, hx: Coord) -> bool:
    """[24.46] first direction: is a Level of fortification already being built on `hx`? "No other
    construction -- of any type -- may take place in a hex which is undergoing fortification
    construction." The test is on the ground, not on the side, because the rule is about the hex.

    The Construction Chart's Restrictions cell for the Fortification row carves out ports and
    flying-boat facilities; neither exists in this engine, and data/minefields.json flags the
    carve-out rather than silently adopting it."""
    return (FORT, tuple(hx)) in state.construction


def other_construction_underway(state: GameState, hx: Coord) -> bool:
    """[24.46] second direction: is any NON-fortification project banked on `hx`? A fortification
    may not be started on top of one -- otherwise the other project would be "taking place in a
    hex which is undergoing fortification construction" the moment the fortification began."""
    return any(h == tuple(hx) and i != FORT for (i, h) in state.construction)


def minefield_buildable(state: GameState, side: Side, hx: Coord) -> bool:
    """[24.35]/[24.36] May a minefield be laid at `hx` at all -- allowed terrain (OWNER RULING
    NEEDED #2, data/minefields.json: this engine follows 24.35's prose list, Clear/Gravel/Rough,
    over the Construction Chart's Clear/Gravel/Salt-Marsh), not Enemy-controlled, not already
    carrying a belt ("only one Minefield -- real or dummy -- may be constructed in any one hex"),
    and not a hex already undergoing fortification construction (24.46)."""
    if state.terrain.terrain.get(hx) not in mf.MINEFIELD_TERRAIN or hx in state.minefields:
        return False
    if fort_under_construction(state, hx):                     # 24.46
        return False
    enemy = Control.AXIS if side == Side.ALLIED else Control.ALLIED
    return state.control_of(hx) != enemy


def minefield_supplies(real: bool) -> tuple[int, int]:
    """(Store Points, Ammunition Points) a Player must have on hand at the START of construction
    (24.33 real / 24.34 dummy)."""
    return (mf.REAL_STORES, mf.REAL_AMMO) if real else (mf.DUMMY_STORES, mf.DUMMY_AMMO)


def can_lay_minefield(state: GameState, side: Side, u: Unit, hx: Coord) -> bool:
    """[24.31] May `u` initiate or continue laying a minefield at `hx` this Construction Segment?
    An EBn/ECoy (or, Commonwealth only, an HQ with Engineering capability -- see lays_minefield),
    standing on the site, with no Capability Points spent this stage (24.12) -- the hex-level gates
    (terrain/control/one-per-hex/24.46) are minefield_buildable's."""
    return (u.side == side and tuple(u.hex) == tuple(hx) and lays_minefield(u)
            and u.cp_used == 0 and minefield_buildable(state, side, hx))


def can_clear_minefield(state: GameState, side: Side, u: Unit, hx: Coord) -> bool:
    """[26.13]/[24.38]/[24.18] May `u` clear the minefield standing at `hx`? The Demolition Chart's
    Real Minefield row prints the units column exactly: "Any E OR TANK BN WITH 6+ TOE OF SCORPIONS"
    -- so any general Engineering unit (EBn, ECoy, HQ-with-Engineering) or one of 23.15's two
    refitted Commonwealth flail battalions while it still holds six Scorpion TOE Strength Points.
    NOT 'RAIL'/'ROAD', which 23.13 restricts to their one named job.

    Standing on the site with a real OR dummy belt present, no Capability Points spent this stage,
    and no fortification under construction on the hex (24.46). One full Op-Stage of exactly this,
    un-interrupted, clears it (engine._construction's Completion Step,
    PROJECT_STAGES[CLEAR_MINEFIELD])."""
    return (u.side == side and tuple(u.hex) == tuple(hx) and mf.is_engineer(u)
            and u.cp_used == 0 and hx in state.minefields
            and not fort_under_construction(state, hx))                    # 24.46


# --- [24.4] CONSTRUCTING FORTIFICATIONS -----------------------------------------------------------

def _is_infantry_battalion(u: Unit) -> bool:
    """24.42's "one Infantry battalion with three or more TOE Strength Points" -- read as any
    combat unit that is neither armour nor a gun (this engine carries no finer unit-type tag than
    is_tank/is_gun), at Strength >= 3."""
    return u.is_combat and not u.is_tank and not u.is_gun and u.effective_strength >= 3


def _fort_cap(state: GameState, hx: Coord) -> int:
    """[24.48] The Level a hex may be built or rebuilt UP TO: a Major City's own printed cap (2,
    or 3 for Alexandria/Cairo -- terrain.fortifications' static seed, [25.12]) if it has one, else
    the field-fortification cap (2, 24.41's "Level 1 or Level 2" counter set)."""
    static = state.terrain.fortifications.get(hx, 0)
    return static if static > 0 else mf.FORT_FIELD_CAP


def fort_buildable(state: GameState, side: Side, hx: Coord) -> bool:
    """[24.42]/[24.44]/[24.45]/[24.48] May one more Level of fortification be built at `hx`?

    A hex that ALREADY carries a Level (state.fort_level(hx) > 0 -- every Major City does, from
    t0) is read as a REBUILD (24.45): no terrain exclusion, and construction MAY proceed in an
    Enemy ZOC. A hex at Level 0 is a NEW build (24.44): excluded terrain bars it outright, and it
    may not be started inside an Enemy ZOC. (This engine seeds no field fortification that has
    ever been reduced-then-eligible-for-rebuild at Level 0, so the "genuinely new" and "rebuild
    a razed field fort" cases coincide here; flagged rather than silently assumed away.)
    Either way, the Level may never exceed _fort_cap, and 24.46 bars a Level from being raised on
    a hex that is already running some OTHER construction project.

    The excluded-terrain list is 24.44's prose (mountain, salt marsh, desert, major city, delta).
    The Construction Chart's Restrictions cell names only three of the five -- a prose-vs-chart
    collision recorded as an owner ruling in data/minefields.json (_owner_ruling_3_fortification_
    terrain), resolved the same way ruling #2 was: the numbered rule's own prose wins."""
    terrain = state.terrain.terrain.get(hx)
    if terrain is None:
        return False
    if other_construction_underway(state, hx):                             # 24.46
        return False
    existing = state.fort_level(hx)
    if existing >= _fort_cap(state, hx):
        return False
    is_rebuild = existing > 0
    if not is_rebuild:
        if terrain in mf.FORT_EXCLUDED_TERRAIN:
            return False
        enemy_zoc, _ = tactics.enemy_zoc_and_occupied(state, side)
        if hx in enemy_zoc:
            return False
    return True


def can_build_fort(state: GameState, side: Side, engineer_u: Unit, infantry_u: Unit,
                   hx: Coord) -> bool:
    """[24.42] Both an Engineering-capable unit AND an Infantry battalion at 3+ TOE, standing
    together on the site, neither having spent a Capability Point this stage (24.12)."""
    return (engineer_u.side == side and infantry_u.side == side and engineer_u.id != infantry_u.id
            and tuple(engineer_u.hex) == tuple(hx) and tuple(infantry_u.hex) == tuple(hx)
            and builds_engineering(engineer_u) and _is_infantry_battalion(infantry_u)
            and engineer_u.cp_used == 0 and infantry_u.cp_used == 0
            and fort_buildable(state, side, hx))
