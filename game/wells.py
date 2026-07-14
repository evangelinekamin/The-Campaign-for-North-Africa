"""The water SOURCES (rules 52.1-52.3) -- where water comes from.

The engine has long charged water DEMAND (52.4: one Water Point per infantry battalion
per Operations Stage, one per vehicle/truck TOE Point) and enforced the PENALTY (52.53:
an infantry unit short of water sheds one TOE Point every consecutive stage after the
first). It never modelled the supply side, so the campaign's armies drank from nothing
and died of thirst: measured, ~17.5k Axis water shortfalls and total Axis water income
of ZERO across the whole 111-turn campaign. This module is the missing half.

THE MODEL. A well is a water-only Supply Unit standing on its hex:

  * base=True is exactly right and already carries both properties the rules demand: the
    engine refuses to relocate a base (rule 57 / engine._supply_movement), so a well stays
    where the geography put it; and _evaporate skips it, which IS [52.44] ("Water -- except
    for water in wells and pipelines -- is subject to evaporation").
  * ammo = fuel = stores = 0: a well yields water and nothing else [52.11]. (An oasis also
    yields Stores under [52.3]/[8.48]; that half is DEFERRED and flagged below.)
  * MAJOR CITIES and OASES hold _UNLIMITED // 8 -- a reservoir no 111-turn draw can
    exhaust, the same idiom scenario._CW_BASE_SEED uses for the bottomless Suez base.
    [52.13]: their wells "have unlimited water; they may not be depleted and they may not
    be poisoned."
  * VILLAGES and BIRS hold a FLAGGED finite pool derived from the [52.7] Water Availability
    Table (see _table_yield): they can run dry, which is the [52.0] "nuisance".

ONE WELL PER SIDE, AND WHY (the load-bearing modelling decision). A well is geography --
it belongs to neither army -- but game.supply.reachable_supplies filters candidate dumps by
state.active_supplies(unit.side), so a side-neutral Supply Unit could be traced by NOBODY.
The pragmatic faithful model is therefore ONE well Supply Unit PER SIDE on each well hex
("AX-Well-Tobruk" / "AL-Well-Tobruk"), which reproduces the right behaviour at the only
place it is observable: an army can drink from a well it can reach, and enemy ZOC or
occupation of the well hex blocks the other army's 32.16 trace to it (game.supply's trace
blocking) -- you cannot drink from a well the enemy is sitting on. It is a PROXY for
side-neutral geography, not the geography itself; the seam to a true neutral source is
active_supplies, and it is not worth widening for this.

DEFERRED, and flagged so nothing is silently missing:
  * [52.13]/[52.7] the CP expenditure and the draw die at a village/bir well, and with it
    [52.14] depletion and [52.15] rain replenishment. Village/bir wells are seeded instead
    as a finite pool sized from the chart (below). Deferring the depletion die and the rain
    that undoes it together is self-consistent; the seeded pool is the conservative half.
  * [52.16]/[52.17] poisoning and sweetening.
  * [52.21]/[52.24] player-CONSTRUCTED pipelines (10 Stores and a Construction Phase per
    hex) and [52.25] their destruction. Only the Commonwealth's standing RR-as-pipeline
    ([52.22], which needs no construction) is seeded.
  * [52.45] water carried by trucks -- the 54.2 chart gives every truck class a Water
    capacity, and the campaign's coastal relay hauls Ammo/Fuel/Stores only. This is the
    open half of the supply side: a well waters what stands within its 32.16 trace (half
    the unit's CPA -- five CP, one or two hexes, for leg infantry), and hauling it further
    is the trucks' job. See the task report.
  * [52.3] the oasis as a Stores source as well as a water source.
"""
from __future__ import annotations

import json
import os
from collections import deque

from . import coords
from .events import Side
from .hexmap import Coord, neighbors
from .state import SupplyUnit
from .supply import _UNLIMITED

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "wells.json")

# [52.13] Major-city and oasis wells are unlimited and may never be depleted. Seeded, like
# scenario._CW_BASE_SEED, as a reservoir no 111-turn draw can exhaust -- and small enough
# against the 54.12 MAJOR_CITY ceiling (_UNLIMITED) that nothing overflows.
UNLIMITED_WELL = _UNLIMITED // 8

# [52.7] WATER AVAILABILITY TABLE (docs/rules/90): the Water Points a draw yields, by die,
# and the rows that then throw the depletion die ("*"). A '1' on that second die depletes
# the source.
_WATER_TABLE_52_7 = {
    "village": {"draws": (100, 150, 200, 300, 350, 500), "depletes_on": (5, 6)},   # Town row
    "bir": {"draws": (50, 100, 150, 200, 300, 400), "depletes_on": (4, 5, 6)},     # Bir row
}


def _table_yield(kind: str) -> int:
    """The Water Points a village/bir well is seeded with: a FLAGGED finite proxy for the
    [52.7] draw-and-deplete cycle we do not roll.

    Sized straight off the chart as the well's EXPECTED LIFETIME YIELD between rains -- the
    mean draw times the expected number of draws before the depletion die fires:

        village (Town row): mean 1600/6 = 266.7  x  1 / ((2/6) x (1/6)) = 18 draws  = 4800
        bir     (Bir row) : mean 1200/6 = 200.0  x  1 / ((3/6) x (1/6)) = 12 draws  = 2400

    Conservative in two ways, both deliberate: it ignores [52.15] (a rainstorm replenishes
    EVERY depleted well on the map-section, and a 111-turn campaign sees many), and it lets
    a whole army camped on one village drink it dry. A well that can run dry is the [52.0]
    nuisance the rule asks for; a well that cannot is a faucet."""
    row = _WATER_TABLE_52_7[kind]
    draws = row["draws"]
    mean = sum(draws) / len(draws)
    p_deplete = (len(row["depletes_on"]) / 6) * (1 / 6)      # starred row, then a '1'
    return round(mean / p_deplete)


def _pool(kind: str) -> int:
    """Water Points seeded at a well of `kind` (52.13 unlimited / 52.7 finite)."""
    if kind in ("major_city", "oasis"):
        return UNLIMITED_WELL
    return _table_yield(kind)


def load() -> dict:
    with open(_DATA) as f:
        return json.load(f)


def _ax(label: str) -> Coord:
    return coords.to_axial(coords.parse(label))


_SIDE_PREFIX = ((Side.AXIS, "AX"), (Side.ALLIED, "AL"))
WELL_ID_MARK = "-Well-"
PIPE_ID_MARK = "-Pipe-"


def is_water_source(su: SupplyUnit) -> bool:
    """True for a 52.1-52.3 well or pipeline hex. These are GEOGRAPHY, not an army's field
    dump: the supply trace draws water from them, but the haulage layer must not treat them
    as depots to fill or reload from (the id-prefix idiom game.campaign_policy already uses
    to hide the AX-Stage waypoints from the base leapfrog)."""
    return WELL_ID_MARK in su.id or PIPE_ID_MARK in su.id


def wells(data: dict | None = None) -> tuple[SupplyUnit, ...]:
    """Every 52.11 well on the map, ONE PER SIDE (see the module docstring): unlimited at the
    major cities and oases (52.13), a finite 52.7 pool at the villages and birs."""
    data = data or load()
    out: list[SupplyUnit] = []
    for w in data["wells"]:
        hexid = _ax(w["hex"])
        water = _pool(w["kind"])
        tag = w["name"].replace(" ", "")
        for side, prefix in _SIDE_PREFIX:
            out.append(SupplyUnit(f"{prefix}{WELL_ID_MARK}{tag}", side, hexid,
                                  ammo=0, fuel=0, stores=0, water=water, base=True))
    return tuple(out)


def _land_path(terrain: dict, start: Coord, end: Coord) -> list[Coord]:
    """The shortest chain of EXISTING land hexes from `start` to `end` (breadth-first,
    neighbours in sorted order so the path is deterministic). Walking the real map rather
    than drawing a straight line means the corridor invents no terrain and crosses no sea."""
    prev: dict = {start: None}
    frontier = deque([start])
    while frontier:
        here = frontier.popleft()
        if here == end:
            break
        for nb in sorted(neighbors(here)):
            if nb in terrain and nb not in prev:
                prev[nb] = here
                frontier.append(nb)
    if end not in prev:
        return []
    path, node = [], end
    while node is not None:
        path.append(node)
        node = prev[node]
    return list(reversed(path))


def corridor(terrain: dict, data: dict | None = None) -> tuple[Coord, ...]:
    """THE COMMONWEALTH RAILWAY, as a chain of hexes: the ONE piece of geography that is both the
    [54.3] Commonwealth railroad and the [52.22] water pipeline, because the rulebook says they are
    the same thing -- "the Commonwealth Player may consider any operating Railroad hex to be a
    pipeline for water" (52.22), "the railroad hexes are pipelines in and of themselves" (54.33).
    Deriving both from this one function is what stops the rails and the pipeline from drifting into
    two different lines.

    IT RUNS CAIRO -> ALEXANDRIA -> MERSA MATRUH, and the first leg was missing. Rule 24.6 names the
    line in one sentence and we had modelled half of it: "the rail complex that CRISSCROSSES THE NILE
    DELTA and extends towards Mersa Matruh (eventually to be completed at Tobruk)". The corridor was
    laid from Alexandria only, so between the rule-57 base at CAIRO -- "he has an unlimited amount of
    supplies of all types in Cairo at all times; HIS PROBLEM IS SOLELY TO GET IT TO WHERE HE WANTS IT"
    -- and Alexandria there lay NINETEEN HEXES OF TRACKLESS NOTHING, in the middle of Britain's own
    base area, with not one supply point in them.

    MEASURED, and it is what made the consolidation constraint unshippable: a Commonwealth foot
    battalion traces five Capability Points -- about three hexes -- so standing in Cairo it could
    trace supply at Cairo, and at Alexandria, and NOWHERE IN BETWEEN. The whole Eighth Army lands in
    Cairo as reinforcements. Under campaign_policy.keep_in_trace ("do not outrun your supply") it
    therefore could not take one step out of the Nile Delta for the entire war -- thirty of thirty-two
    combat units still sitting in it at Game-Turn 42 -- and the reason was not a rule and not a
    doctrine. It was a hole in the map.

    FLAGGED PROXY: the map's rail geography is untranscribed (the VASSAL extract carries terrain and
    roads, not rails), so each leg is the shortest LAND path between the transcribed endpoints in
    data/wells.json. It walks real hexes and invents no terrain, but its exact hex chain is OURS, not
    the map's -- and a single line is a thin model of a "complex that crisscrosses" the Delta. It is
    the conservative thin one: one line where the rulebook gives a network."""
    data = data or load()
    spec = data["pipeline"]
    delta = _land_path(terrain, _ax(spec["base"]), _ax(spec["from"]))       # 24.6: the Delta complex
    west = _land_path(terrain, _ax(spec["from"]), _ax(spec["to"]))          # 60.7: ...to Mersa Matruh
    return tuple(delta[:-1] + west)


def rail_survey(terrain: dict, data: dict | None = None) -> tuple[Coord, ...]:
    """[24.67] THE SURVEYED ROUTE THE RAILWAY MAY BE BUILT ALONG -- Mersa Matruh, westward, to
    Tobruk. The line rule 60.7 leaves unfinished and rule 24.6 lets the Commonwealth finish.

        "There are two railroad lines on the game-maps: the rail complex that crisscrosses the Nile
         Delta and extends towards Mersa Matruh (EVENTUALLY TO BE COMPLETED AT TOBRUK)..." (24.6)
        "The Alexandria-Mersa Matruh-Tobruk line may be constructed in only ONE SPECIFIC DIRECTION.
         Construction must start from the last completed hex extending from Mersa Matruh and grow
         westward towards Tobruk. NO HEX MAY BE SKIPPED." (24.67)

    So it is a LINE, not a freedom -- "neither Player may invent new stretches" (24.51, of roads, and
    24.67 is stricter still) -- and it is returned ordered, head first. It OPENS with Mersa Matruh
    itself, the terminus rule 60.7 already gives the Commonwealth: the first hex of new track must
    extend from the last completed one, so the completed one has to be on the line to extend from
    (game.construction.rail_head).

    Same FLAGGED PROXY as corridor() above, and for the same reason: the map's rail geography is
    untranscribed, so the route is the shortest LAND path between the two transcribed endpoints. It
    walks real hexes, invents no terrain and crosses no sea -- and the real Western Desert Railway
    hugged this same coastal strip, which is why it ran through Sidi Barrani and Capuzzo."""
    data = data or load()
    spec = data["pipeline"]
    return tuple(_land_path(terrain, _ax(spec["to"]), _ax(RAIL_OBJECTIVE)))


RAIL_OBJECTIVE = "C4807"    # Tobruk -- 24.6's "eventually to be completed at Tobruk"


def pipeline(terrain: dict, data: dict | None = None) -> tuple[SupplyUnit, ...]:
    """[52.22]/[52.23] The Commonwealth water pipeline: the Egyptian railroad corridor.

    The Commonwealth "may consider any operating Railroad hex to be a pipeline for water",
    and a pipeline hex is a water source "similar to a major city" -- unlimited, never
    depleted, never poisoned (52.23), and never evaporating (52.44, hence base=True). Axis-
    excluded by 52.22 (it may not use the defunct Barce-Benghazi line), which is exactly the
    asymmetry that let the Eighth Army live in the desert while the Panzerarmee carried its water.

    THIS IS THE CONDUIT HALF OF THE RAILWAY, and the rulebook draws the line between the halves
    itself. WATER is drawn straight off the rail hex -- 52.23 makes an RR hex "a source of water
    similar to a major city", so a unit that reaches the line drinks, with no train and no dump.
    AMMUNITION, FUEL and STORES are NOT: they must be hauled by the railway (54.32) and UNLOADED
    at a hex (54.35) before anyone can eat them (49.15: "for fuel to be consumed, it must be
    present in the same hex"; 51.15: "Stores must be present in the hex to be used"). That freight
    half is game.engine._rail_stops -- and note 52.23's analogy is drawn for WATER alone ("a source
    of WATER similar to a major city"), which is precisely what forbids extending it to the rest."""
    data = data or load()
    spec = data["pipeline"]
    side = Side[spec["side"]]
    prefix = dict(_SIDE_PREFIX)[side]
    return tuple(SupplyUnit(f"{prefix}{PIPE_ID_MARK}{i:02d}", side, hexid,
                            ammo=0, fuel=0, stores=0, water=UNLIMITED_WELL, base=True)
                 for i, hexid in enumerate(corridor(terrain, data)))


def well_hexes(data: dict | None = None) -> tuple[Coord, ...]:
    """The hexes carrying a well (52.11) -- the map's water geography, for tests/observation."""
    data = data or load()
    return tuple(_ax(w["hex"]) for w in data["wells"])
