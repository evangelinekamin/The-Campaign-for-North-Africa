"""[54.4] AXIS USE OF THE COMMONWEALTH RAILROAD.

    "Under certain conditions the Axis Player may make use of the coastal railline extending from
    Egypt to Libya (the Commonwealth railroad system). In essence, he must control the rail hexes
    and he must import rolling stock. Remember, the Barce railroad east of Benghazi is not usable
    under any conditions."  -- 54.4, PDF page 74 (book folio 23), read at 150dpi.

This module owns the CONTROL half of that rule -- 54.41's five-contiguous-hex gate -- and nothing
else. The rolling stock (54.43), the 300-ton haul (54.43) and the 900-ton troop lift (54.44) are
downstream of it and are built only once the gate is measured to be reachable: 54.41 is the
precondition for every other case in 54.4, so it is also the honest place to find out whether the
rest of the rule can ever fire.

WHY THIS IS NOT `GameState.control`. 54.41 defines its own control notion:

    "At any time the Axis player controls five or more contiguous rail hexes he may use such rail
    hexes to transport equipment and personnel. To control a rail hex the Axis player must be the
    last player to have a land combat unit of any type pass through that hex."

PASS THROUGH, not occupy -- so a unit that transits a rail hex and marches on still claims it, and
the claim STICKS until the other side transits it in turn. `engine._record_control` derives
`GameState.control` from SOLE COMBAT OCCUPANCY sampled at a phase boundary, which is both narrower
(a transit claims nothing) and non-sticky in the contested case. Measured on a full campaign, the
difference is not academic: under the occupancy reading the Axis peaks at 3-4 contiguous rail hexes
and never opens the gate, while his units demonstrably reach the rail belt (event log furthest east
r130 against a railway spanning r100-139). So the two notions are kept separate, and 54.41 gets the
one the book actually prints.
"""
from __future__ import annotations

from . import hexmap, logistics_data
from .events import Side
from .state import Coord, GameState

_RAIL_54_4 = logistics_data.axis_rail_54_4()

# [54.41] "five or more contiguous rail hexes"
CONTIGUOUS_HEXES_54_41 = _RAIL_54_4["contiguous_hexes"]
# [54.43] "For each 250 Stores and 100 Fuel Points that the Axis Player imports to Africa and
# brings to any controlled and operative rail hex..."
ACTIVATION_COST_54_43 = dict(_RAIL_54_4["activation_cost"])
# [54.43] "...to the extent of hauling 300 Tons of Supplies in any one direction during an
# Operations Stage." Compare [54.32]'s 1,500 t for the Commonwealth: the Axis pays per activation
# for a fifth of what the owner of the line gets for free, which is the rule's whole point.
TONS_PER_ACTIVATION_54_43 = _RAIL_54_4["tons_per_activation_per_opstage"]
# [54.44] "the equivalent of 900 Tons of Supplies in any one direction" per Stacking Point of units.
TONS_PER_STACKING_POINT_54_44 = _RAIL_54_4["tons_per_stacking_point_54_44"]
# [54.34] (via 54.46) "For the duration of one Operations Stage per month (calendar month), the
# railroad may not be used for anything. It is transporting water forward for railroad use."
DEAD_OPSTAGES_PER_MONTH_54_34 = _RAIL_54_4["dead_opstages_per_calendar_month_54_34"]


def rail_hexes(state: GameState) -> set:
    """Every hex the BUILT railway runs through. Read off the map's own rail edge-set, the same
    single source of truth construction.rail_head reads, so an unbuilt stretch of the surveyed
    line simply is not here ("Unbuilt railroad hexes simply do not exist", 24.67)."""
    return {h for e in state.terrain.rails for h in e}


def controlled_by(state: GameState, side: Side) -> set:
    """[54.41] The built rail hexes `side` controls -- those it was last to pass a land combat unit
    through. A hex neither side has ever crossed is controlled by neither."""
    return {h for h in rail_hexes(state) if state.rail_control_of(h) is side}


def contiguous_runs(hexes: set) -> list:
    """The connected components of `hexes` under the map's own hex adjacency, largest first.

    54.41 says "contiguous" without defining it, and the only adjacency this game has is the hex
    grid, so components are taken over ordinary hex neighbours. Note this deliberately does NOT
    require the run to be connected ALONG the railway: two rail hexes that touch are contiguous
    even if the line between them loops, which is the plain reading and the one that cannot
    under-grant a Player a lever the book gives him."""
    remaining = set(hexes)
    runs = []
    while remaining:
        seed = min(remaining)                       # deterministic: lowest Coord starts each run
        comp, stack = set(), [seed]
        remaining.discard(seed)
        while stack:
            c = stack.pop()
            comp.add(c)
            for nb in hexmap.neighbors(c):
                if nb in remaining:
                    remaining.discard(nb)
                    stack.append(nb)
        runs.append(comp)
    runs.sort(key=lambda s: (-len(s), min(s)))      # size desc, then Coord: stable and seed-free
    return runs


def longest_run(state: GameState, side: Side) -> int:
    """The size of `side`'s largest contiguous block of controlled rail hexes (54.41)."""
    runs = contiguous_runs(controlled_by(state, side))
    return len(runs[0]) if runs else 0


def gate_open(state: GameState, side: Side) -> bool:
    """[54.41] Does `side` control five or more contiguous rail hexes -- the precondition for every
    other case of 54.4? AXIS-ONLY by the rule's own subject ("the Axis player"): 54.4 is about the
    Axis borrowing the Commonwealth's railroad, and the Commonwealth's own use of it is rule 54.3.
    """
    if side is not Side.AXIS:
        return False
    return longest_run(state, side) >= CONTIGUOUS_HEXES_54_41


def haul_capacity_tons(state: GameState) -> int:
    """[54.43] The tons of supply the Axis may move along his controlled line in ONE direction this
    Operations Stage: 300 per activated Rolling Stock. Zero the moment 54.41's gate is shut, which
    is also when 54.45 destroys the stock outright -- so this never needs to ask twice."""
    if not gate_open(state, Side.AXIS):
        return 0
    return state.rolling_stock * TONS_PER_ACTIVATION_54_43


def activation_affordable(dump, cost: dict | None = None) -> bool:
    """[54.43] Does `dump` hold the 250 Stores + 100 Fuel one activation costs? The points must be
    at "any controlled and operative rail hex"; the caller checks the hex, this checks the purse."""
    cost = ACTIVATION_COST_54_43 if cost is None else cost
    return all(getattr(dump, c.lower()) >= q for c, q in cost.items())


def dead_stage_54_34(state: GameState) -> int:
    """[54.34] via [54.46]: the ONE Operations Stage each calendar month in which the railroad "may
    not be used for anything" because it is hauling its own water. "Players must state each month
    which Operations Stage they are not using the railroad" -- a declaration this engine has no
    seat to make, so it is FIXED at the month's LAST stage (3) rather than left to a policy.

    FLAGGED as a judgement call, and deliberately the least generous reading available: taking the
    last stage means the Axis has already had stages 1 and 2 to haul before losing one, which
    neither hands him a lever the book withholds nor lets him dodge the cost."""
    return 3


def usable_this_stage(state: GameState) -> bool:
    """[54.34]/[54.41] May the Axis run a train AT ALL right now? The gate must be open and this
    must not be the month's dead stage."""
    return gate_open(state, Side.AXIS) and state.stage != dead_stage_54_34(state)


def claims(state: GameState, side: Side, path: list) -> list:
    """The rail hexes along `path` whose 54.41 control would CHANGE hands to `side`.

    Returns them in path order, so the event log reads in the order the unit actually walked them.
    A hex `side` already controls yields nothing -- the claim is idempotent, and re-emitting it
    every time a unit re-crosses its own railway would bury the log in no-op events."""
    if not path:
        return []
    rails = rail_hexes(state)
    out, seen = [], set()
    for hx in path:
        if hx in rails and hx not in seen and state.rail_control_of(hx) is not side:
            seen.add(hx)
            out.append(hx)
    return out
