"""Land movement core (rule 8.0): CPA-budget pathing over a terrain map.

Movement is "Continual Movement" on a Capability Point Allowance (rule 6.0/8.2):
entering a hex and crossing a hexside each cost CP per the Terrain Effects Chart
(terrain.py). Roads negate hexside costs and cheapen entry; tracks give 1 CP/hex
and halve hexside costs (except a vehicle's CP down an escarpment — note 8).

This module is pure: given a TerrainMap + a unit's mobility/CPA, it answers
"what does this step/path cost?" and "where can this unit reach?". Zones of
control, stacking, breakdown, and disorganization-on-overspend are later slices;
the engine layer composes them on top.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .hexmap import Coord, is_adjacent, neighbors
from .terrain import (Hexside, Mobility, Terrain, TRACK_ENTRY, ROAD_ENTRY,
                      ROAD_BREAKDOWN, breakdown_value, hex_entry_cost, hexside_cost,
                      hexside_breakdown, is_motorized)

Edge = frozenset


def edge(a: Coord, b: Coord) -> frozenset:
    return frozenset((a, b))


@dataclass(frozen=True, slots=True)
class TerrainMap:
    terrain: dict[Coord, Terrain]                       # the hexes that exist
    hexsides: dict[tuple[Coord, Coord], Hexside] = field(default_factory=dict)  # directed
    roads: frozenset = frozenset()                      # of edge(a, b)
    tracks: frozenset = frozenset()                     # of edge(a, b)
    fortifications: dict[Coord, int] = field(default_factory=dict)  # hex -> fort level (15.82)
    minefields: frozenset = frozenset()                 # of Coord: defensive minefield belt
    rails: frozenset = frozenset()                      # of edge(a, b): Commonwealth railroad (54.3)

    def exists(self, coord: Coord) -> bool:
        return coord in self.terrain


def step_cost(tmap: TerrainMap, src: Coord, dst: Coord, mobility: Mobility) -> float | None:
    """CP to move from src into the adjacent hex dst, or None if impossible
    (off-map, non-adjacent, or a prohibited terrain/hexside for this mobility)."""
    if not tmap.exists(dst) or not is_adjacent(src, dst):
        return None

    e = edge(src, dst)
    on_road = e in tmap.roads
    on_track = e in tmap.tracks
    mot = mobility

    if on_road:
        entry = ROAD_ENTRY[_mot(mot)]
    elif on_track:
        entry = TRACK_ENTRY[_mot(mot)]
    else:
        entry = hex_entry_cost(tmap.terrain[dst], mot)
        if entry is None:
            return None

    feature = tmap.hexsides.get((src, dst))
    if feature is None or on_road:                      # road negates hexside costs (note 6)
        add = 0.0
    else:
        base = hexside_cost(feature, mot)
        if base is None:
            return None                                 # e.g. motorized up an escarpment
        if on_track:
            # Track halves hexside costs, EXCEPT a *vehicle's* CP down an
            # escarpment (note 8); foot units still get the discount.
            no_halve = feature == Hexside.DOWN_ESCARPMENT and _mot(mot)
            add = base if no_halve else base / 2
        else:
            add = base

    return entry + add


def rainstorm(weather: str) -> bool:
    """29.56: during a Rainstorm a Road is treated as a Track for Breakdown Points.
    Keyed off the weather label; the current toy vocabulary's wet labels both count
    (Step-6 real weather swaps in the 29.61 'rainstorm' label without touching this)."""
    return weather in ("rain", "rainstorm", "storm")


def breakdown_points(tmap: TerrainMap, src: Coord, dst: Coord, mobility: Mobility,
                     weather: str = "clear") -> float:
    """Breakdown Points accrued moving one step src->dst (rule 21.21 / 8.37), the
    pure dual of step_cost. Foot/camel accrue none (21.11). A Road contributes its
    own 1/2 value and NEGATES the hexside (note 6); a Track HALVES both the entered-
    hex and hexside value EXCEPT down an escarpment for a vehicle (note 8); during a
    Rainstorm a Road counts as a Track (29.56). A Light Truck moving off-road garners
    one extra Breakdown Point per hex entered and per hexside crossed (54.2 note)."""
    if not is_motorized(mobility):
        return 0.0
    e = edge(src, dst)
    on_road = e in tmap.roads
    on_track = e in tmap.tracks
    rain = rainstorm(weather)
    road_as_road = on_road and not rain
    halving = on_track or (on_road and rain)               # a track, or a rained-on road

    if road_as_road:
        entry = ROAD_BREAKDOWN                             # note 6: road's own 1/2 value
    elif halving:
        entry = breakdown_value(tmap.terrain[dst]) / 2     # note 8: track halves entry
    else:
        entry = breakdown_value(tmap.terrain[dst])

    feature = tmap.hexsides.get((src, dst))
    if feature is None or road_as_road:                    # road negates hexside BP (note 6)
        add = 0.0
    else:
        base = hexside_breakdown(feature)
        if base is None:                                   # prohibited hexside (defensive)
            return 0.0
        no_halve = feature == Hexside.DOWN_ESCARPMENT      # note-8 exception (vehicles)
        add = base if (no_halve or not halving) else base / 2

    if mobility == Mobility.LIGHT_TRUCK and not road_as_road:   # 54.2 off-road light truck
        entry += 1
        add += 1
    return entry + add


def path_cost(tmap: TerrainMap, path: list[Coord], mobility: Mobility) -> float | None:
    """Total CP to traverse a contiguous path (path[0] is the start, not entered)."""
    total = 0.0
    for src, dst in zip(path, path[1:]):
        c = step_cost(tmap, src, dst, mobility)
        if c is None:
            return None
        total += c
    return total


def reachable(tmap: TerrainMap, start: Coord, budget: float, mobility: Mobility,
              *, blocked: frozenset = frozenset(),
              terminal=None, passable=None, start_cost: float = 0.0) -> dict[Coord, float]:
    """All hexes reachable from start within `budget` CP (Dijkstra). `blocked`
    hexes (e.g. enemy-occupied) cannot be entered. Continual Movement allows
    exceeding CPA, so the caller passes whatever budget it is willing to spend.

    Two optional predicates let callers (e.g. zoc.py) layer rules on top of pure
    terrain cost without re-implementing the search:
      - terminal(coord): if True, the hex may be ENTERED but not expanded from
        (rule 10.23 "must cease movement upon entering an enemy-controlled hex");
      - passable(here, nb): if False, that specific step is forbidden
        (rule 10.24 "no move from one enemy-controlled hex into another").
    start_cost seeds the start hex (e.g. a break-off cost paid to leave a ZOC)."""
    best: dict[Coord, float] = {start: start_cost}
    pq: list[tuple[float, Coord]] = [(start_cost, start)]
    while pq:
        cost, here = heapq.heappop(pq)
        if cost > best.get(here, float("inf")):
            continue
        if terminal is not None and here != start and terminal(here):
            continue
        for nb in neighbors(here):
            if nb in blocked or not tmap.exists(nb):
                continue
            if passable is not None and not passable(here, nb):
                continue
            step = step_cost(tmap, here, nb, mobility)
            if step is None:
                continue
            nc = cost + step
            if nc <= budget and nc < best.get(nb, float("inf")):
                best[nb] = nc
                heapq.heappush(pq, (nc, nb))
    return best


def _mot(mobility: Mobility) -> bool:
    from .terrain import is_motorized
    return is_motorized(mobility)
