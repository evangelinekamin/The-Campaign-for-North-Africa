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
                      hex_entry_cost, hexside_cost)

Edge = frozenset


def edge(a: Coord, b: Coord) -> frozenset:
    return frozenset((a, b))


@dataclass(frozen=True, slots=True)
class TerrainMap:
    terrain: dict[Coord, Terrain]                       # the hexes that exist
    hexsides: dict[tuple[Coord, Coord], Hexside] = field(default_factory=dict)  # directed
    roads: frozenset = frozenset()                      # of edge(a, b)
    tracks: frozenset = frozenset()                     # of edge(a, b)

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
              blocked: frozenset = frozenset()) -> dict[Coord, float]:
    """All hexes reachable from start within `budget` CP (Dijkstra). `blocked`
    hexes (e.g. enemy-occupied) cannot be entered. Continual Movement allows
    exceeding CPA, so the caller passes whatever budget it is willing to spend."""
    best: dict[Coord, float] = {start: 0.0}
    pq: list[tuple[float, Coord]] = [(0.0, start)]
    while pq:
        cost, here = heapq.heappop(pq)
        if cost > best.get(here, float("inf")):
            continue
        for nb in neighbors(here):
            if nb in blocked or not tmap.exists(nb):
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
