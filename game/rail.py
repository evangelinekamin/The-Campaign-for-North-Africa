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

from . import hexmap
from .events import Side
from .state import Coord, GameState

# [54.41] "five or more contiguous rail hexes"
CONTIGUOUS_HEXES_54_41 = 5


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
