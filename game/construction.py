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

DELIBERATELY NOT BUILT (24 is a big rule and this is the smallest faithful slice of it):
  * 24.3 minefields, 24.4 fortifications, 24.5 roads (the 1 SA Road Construction Battalion is seeded
    and idle -- it exists, it is the rulebook's unit, and it has no unfinished-road overlay to build
    on because the map's unfinished-road hexes are untranscribed), 24.7 air facilities, 24.8 repair
    facilities, and the 24.18 Demolition Chart's rail/road destruction (24.66).
  * 24.21's ten Water Points per site in Hot weather, and 24.23's pinned-by-artillery halt.
  * 52.22's water pipeline following the new rails ("the Commonwealth Player may consider any
    OPERATING Railroad hex to be a pipeline for water"). It is a real rule and it falls out of a
    built rail hex, but a pipeline hex is an UNLIMITED water source (52.23), so extending it means
    minting supply mid-game -- a conservation seam this slice does not need: the coast road the
    railway follows is already strung with wells (Sollum, Bardia, Tobruk, Derna are all major-city
    water sources, 52.13), which is why both armies used it.
"""
from __future__ import annotations

from .events import Control, Side
from .hexmap import Coord
from .movement import edge
from .state import GameState, Unit

RAIL = "RAIL"                    # 24.6: a hex of new track
DUMP = "DUMP"                    # 24.9: a supply dump

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
# construction time costs." Our weather is theatre-wide (rule 29.7 localisation is per map-section
# and the campaign plays all five), so a foul stage simply banks no company-stages anywhere.
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
    if state.weather in FOUL:
        return False
    enemy = Control.AXIS if side == Side.ALLIED else Control.ALLIED
    return (state.control_of(hx) != enemy
            and not any(u.is_combat for u in state.enemies_at(hx, side)))


def rail_edge(state: GameState, hx: Coord) -> "frozenset | None":
    """The rail edge a completed hex adds to the map: `hx` joined to the head it extends from
    (24.67). None if `hx` is not the next hex of the surveyed line."""
    head = rail_head(state)
    return edge(head, hx) if head is not None else None


def stores_at(state: GameState, side: Side, hx: Coord) -> int:
    """[24.13] The Store Points a Player has "on hand IN THE HEX" to expend on construction: what
    his own dumps standing on the site hold. 24.13 is explicit that the supplies "must BEGIN the
    Construction Segment in the given hex" -- construction is not fed down a supply trace, it is fed
    out of the pile the engineers are standing on."""
    return sum(s.stores for s in state.supplies
               if s.side == side and s.hex == hx and not s.is_dummy)


def stores_draw(state: GameState, side: Side, hx: Coord, qty: int) -> list[tuple[str, int]]:
    """[24.13]/[32.15] Spend `qty` Store Points OUT OF THE HEX: ((supply_id, qty), ...), the piles
    drawn from and how much each gives up. Field dumps first (by id), the bottomless rule-57 base
    last, so a garrison spends what it carried before it spends Cairo's.

    THE BUG THIS FIXES, and it is a real one that predates rule 32.32. `stores_at` counts what EVERY
    friendly dump on the hex holds -- 24.13's "on hand in the hex", and correct, since 32.15 lets a
    Player rearrange supplies among co-located Supply Units for free -- but engine._build_dump then
    consumed all twenty Store Points from ONE of them (`dump_at`, the first by id). Two dumps sharing
    a hex with the stores split between them passed the check and over-drained the named one:
    MEASURED, "supply AL-Field-22-87 has negative STORES pool -6", an InvariantViolation that took
    the whole campaign down. The check counts the hex, so the charge must come out of the hex."""
    legs: list[tuple[str, int]] = []
    here = sorted((s for s in state.supplies
                   if s.side == side and s.hex == hx and not s.is_dummy),
                  key=lambda s: (s.base, s.id))
    for s in here:
        take = min(qty, s.stores)
        if take > 0:
            legs.append((s.id, take))
            qty -= take
        if qty == 0:
            break
    return legs


def dump_at(state: GameState, side: Side, hx: Coord):
    """The side's own dump standing on `hx` -- the heap of supplies a 24.9 construction turns into a
    proper dump. Rule 24.9 lets a Player designate ANY hex a supply dump, empty or not; ours requires
    the pile to already be there, because an empty dump on an empty hex is a counter with no job and
    the engine's one-dump-per-hex rule (engine._dump_on) would then have to arbitrate between it and
    the next lorry's unload."""
    return next((s for s in sorted(state.supplies, key=lambda s: s.id)
                 if s.side == side and s.hex == hx and not s.is_dummy and not s.base), None)


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
            and stores_at(state, side, u.hex) >= DUMP_STORES)
