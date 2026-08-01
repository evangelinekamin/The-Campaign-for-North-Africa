"""[54.4] AXIS USE OF THE COMMONWEALTH RAILROAD.

    "Under certain conditions the Axis Player may make use of the coastal railline extending from
    Egypt to Libya (the Commonwealth railroad system). In essence, he must control the rail hexes
    and he must import rolling stock. Remember, the Barce railroad east of Benghazi is not usable
    under any conditions."  -- 54.4, PDF page 74 (book folio 23), read at 150dpi.

This module owns the CONTROL half of that rule -- 54.41's five-contiguous-hex gate, the runs that
gate activates, and 54.34's dead Operations Stage. The rolling stock and the 300-ton haul (54.43)
stand on it in game.engine._axis_rail.

*** [54.44] THE 900-TON TROOP LIFT IS NAMED DEBT, NOT DEFERRED WORK. *** This docstring used to say
the lift would be built "once the gate is measured to be reachable". THE GATE HAS NOW BEEN MEASURED
REACHABLE (5 of 5 campaign seeds open it), so that trigger has fired and the rule is still missing:
there is no RailMoveOrder, nothing reads TONS_PER_STACKING_POINT_54_44, and 54.41's own subject --
"he may use such rail hexes to transport EQUIPMENT AND PERSONNEL" -- therefore only half exists. The
Axis can rail freight and cannot rail a battalion. Declared here so the gap is a debt with a name
rather than a promise whose condition has quietly come true.

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

from . import calendar, hexmap, logistics_data
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
# [5.1] A Game-Turn is three Operations Stages, so the LAST one is the third -- which is the stage
# 54.34's dead Operations Stage is fixed at (dead_opstages_54_34's flagged judgement call). The
# magnitude is the clock's, and is read from the clock's one home rather than re-typed here.
LAST_OPSTAGE = calendar.OPSTAGES_PER_GAME_TURN
# [54.43] "...in any ONE direction during an Operations Stage" -- the two directions a train may run
# in, and the words the audit log names them by (see haul_direction_54_43).
EASTWARD, WESTWARD = 1, -1
DIRECTION_NAMES = {EASTWARD: "eastward", WESTWARD: "westward"}


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


def stock_in_run(state: GameState, run) -> int:
    """[54.43] The units of Rolling Stock standing inside `run` (a set of Coords).

    A locomotive is bought at a hex -- "brings to any controlled and operative rail hex" -- and it
    activates "all such hexes under his control (AS LONG AS THEY ARE CONTIGUOUS)", so the block it
    was put down on is the block it works. It cannot be lifted onto another one: 54.42 lets the
    Axis repair rail hexes and never lets him move stock off the rails."""
    return 0 if run is None else sum(n for hx, n in state.rolling_stock_at.items() if hx in run)


def haul_capacity_tons(state: GameState, run) -> int:
    """[54.43] The tons of supply the Axis may move along `run` in ONE direction this Operations
    Stage: 300 per unit of Rolling Stock STANDING ON THAT RUN. Zero for a run with no stock on it,
    and zero for None (a pair of hexes that is in no activated run at all)."""
    return stock_in_run(state, run) * TONS_PER_ACTIVATION_54_43


def orphaned_stock(state: GameState) -> dict:
    """[54.45] The stock the Commonwealth has just destroyed by retaking the line: activation hex ->
    units, for every hex that no longer lies in a run of five contiguous Axis-controlled rail hexes.

    "If at any time the Axis Player loses control of enough rail hexes so that he does not have the
    necessary five contiguous hexes the Rolling Stock is considered to have been destroyed."

    *** FLAGGED AS A READING. *** The sentence's subject is the Player, so read alone it would kill
    the board's stock only when NO run of five survives anywhere. Taken with 54.43 -- which sells
    the stock onto one contiguous block and rates it by what that block can haul -- the necessary
    five hexes are the ones under the locomotive: a machine standing on an overrun stretch is lost
    whatever the Axis still holds three hundred miles away, and it certainly cannot be driven there
    across the Eighth Army. This is also the reading that keeps the engine honest, since the other
    one strands stock that can never haul again and never dies.

    *** THE OLD FLAG SAID SOMETHING FALSE HERE AND IS CORRECTED. *** It reassured a future reader
    that "where only one run ever exists (the campaign as measured) the two readings coincide". THE
    CAMPAIGN DOES NOT HOLD ONLY ONE RUN. Re-measured over six seeds (1941, 7, 2026, 1, 99, 4) folded
    to GT111, recomputing activated_runs at every change of rail_control
    (scratchpad/54.4-scan/measure_runs_and_colocation.py): every seed reaches TWO concurrent
    activated runs, as early as Game-Turn 3-6, and holds two for 1 to 21 Operations Stages depending
    on the seed. So the readings are not made to coincide by the board, and this choice is load-
    bearing rather than moot.

    WHAT IS TRUE, MEASURED SEPARATELY (measure_54_45_readings.py): the two readings have not yet
    DIFFERED ON AN ACTUAL LOCOMOTIVE, because the campaign has only ever put one on the board -- one
    activation in six seeds (seed 4, GT4), destroyed at GT13 with 54.41's gate shut board-wide, so
    both readings kill it. That is a fact about 54.43's price keeping the rails empty (see the
    transcription's verdict), not about the two readings agreeing, and it stops being true the first
    time the Axis affords a second locomotive while he holds two runs."""
    return {hx: n for hx, n in sorted(state.rolling_stock_at.items())
            if activated_run_at(state, hx) is None}


def haul_direction_54_43(src: Coord, dst: Coord) -> int:
    """[54.43] Which of the line's two directions a haul from `src` to `dst` runs in: EASTWARD or
    WESTWARD.

    54.4's subject is "the coastal railline extending from Egypt to Libya", a line whose two ends
    are east and west, and this map lays that line out along the axial r axis (the campaign's rail
    corridor spans r100-r139), so the sign of dr IS the direction a train runs in. *** FLAGGED, the
    tiebreak: *** two dumps in the SAME column are ordered by q, because every haul must have
    exactly one direction or the 54.43 pin has a hole to slip through; a haul whose two ends are the
    same dump has no direction at all and is refused before this is asked (engine._rail_haul)."""
    return EASTWARD if (dst[1], dst[0]) > (src[1], src[0]) else WESTWARD


def activation_affordable(dump, cost: dict | None = None) -> bool:
    """[54.43] Does `dump` hold the 250 Stores + 100 Fuel one activation costs? The points must be
    at "any controlled and operative rail hex"; the caller checks the hex, this checks the purse."""
    cost = ACTIVATION_COST_54_43 if cost is None else cost
    return all(getattr(dump, c.lower()) >= q for c, q in cost.items())


def dead_opstages_54_34(gt: int) -> frozenset:
    """[54.34] via [54.46]: the (Game-Turn, Operations Stage) pairs of `gt`'s CALENDAR MONTH in
    which the railroad "may not be used for anything" because it is hauling its own water.

    ONE PER CALENDAR MONTH, NOT ONE PER GAME-TURN. 54.34 prints the parenthetical itself -- "For
    the duration of one Operations Stage per month (CALENDAR MONTH)" -- because the weekly reading
    is the obvious misreading, and this engine had made it: a bare `state.stage == 3` killed the
    railway on stage 3 of all 111 Game-Turns, ~111 dead Operations Stages against the book's ~29.
    The month is game.calendar.month_turns (four Game-Turns, or TWO for the half-month September
    1940 the campaign opens in, 64.2), and the COUNT is the data file's own
    DEAD_OPSTAGES_PER_MONTH_54_34 rather than a literal here.

    WHICH stage is the PLAYER'S CALL -- "Players must state each month which Operations Stage they
    are not using the railroad" -- and this engine has no seat for that declaration. *** FLAGGED AS
    A JUDGEMENT CALL: *** it is fixed at the LAST Operations Stage of the month's FIRST Game-Turn.
    Two reasons, neither of them a balance argument. It is the beat the COMMONWEALTH half of the
    same clause already stands down on (scenario._campaign_rail_cargo drops the month-start
    Game-Turn's STORES load, the third of that turn's three stage-loads), so 54.34 is now encoded
    ONE way on both sides of the board instead of two. And it is the least generous reading
    available within that turn: the Axis has already had stages 1 and 2 to haul before he loses
    one, so the choice neither hands him a lever the book withholds nor lets him dodge the cost."""
    return frozenset((t, LAST_OPSTAGE)
                     for t in calendar.month_turns(gt)[:DEAD_OPSTAGES_PER_MONTH_54_34])


def is_dead_stage_54_34(state: GameState) -> bool:
    """[54.34] Is the railway standing down THIS Operations Stage, hauling its own water?"""
    return (state.turn, state.stage) in dead_opstages_54_34(state.turn)


def activated_runs(state: GameState) -> list:
    """[54.41]/[54.43] The blocks of Axis-controlled rail hexes that may actually be RUN ON --
    every contiguous run of at least CONTIGUOUS_HEXES_54_41 hexes, largest first.

    54.41 grants the use of "SUCH rail hexes" (the five-or-more contiguous ones he controls) and
    54.43 activates "all such hexes under his control (AS LONG AS THEY ARE CONTIGUOUS)". So the
    thing the Axis operates is a RUN, not the railway at large -- and a run of five somewhere in
    Cyrenaica licenses nothing three hundred miles away in Egypt."""
    return [run for run in contiguous_runs(controlled_by(state, Side.AXIS))
            if len(run) >= CONTIGUOUS_HEXES_54_41]


def activated_run_at(state: GameState, hx: Coord):
    """The activated run `hx` belongs to (a set of Coords), or None if it belongs to none. Runs are
    disjoint by construction, so "the" run is well defined."""
    return next((run for run in activated_runs(state) if hx in run), None)


def one_activated_run(state: GameState, a: Coord, b: Coord) -> bool:
    """[54.41]/[54.43] Do `a` and `b` lie in the SAME activated run -- i.e. may a train run between
    them at all? THIS IS THE CONTROL HALF of a haul's legality and it is not implied by either
    endpoint being Axis-controlled: a run the Commonwealth breaks in the middle is two runs, and a
    train that crosses the break would be running through the Eighth Army's own railhead."""
    run = activated_run_at(state, a)
    return run is not None and b in run


def usable_this_stage(state: GameState) -> bool:
    """[54.34]/[54.41] May the Axis run a train AT ALL right now? He must hold a run long enough to
    activate, and this must not be the calendar month's dead Operations Stage."""
    return gate_open(state, Side.AXIS) and not is_dead_stage_54_34(state)


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
