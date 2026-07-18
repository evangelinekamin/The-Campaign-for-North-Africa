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

Edge = tuple


def edge(a: Coord, b: Coord) -> tuple:
    """An undirected map edge as a normalized (lo, hi) coord pair, so edge(a, b) == edge(b, a).
    A hashable tuple keyed this way is the elegant undirected-edge representation: road/track/rail
    membership becomes a plain tuple lookup with none of the per-query frozenset allocation the hot
    step_cost core paid 29.6M times, and every construction/query site stays symmetric."""
    return (a, b) if a <= b else (b, a)


@dataclass(frozen=True, slots=True)
class TerrainMap:
    terrain: dict[Coord, Terrain]                       # the hexes that exist
    hexsides: dict[tuple[Coord, Coord], Hexside] = field(default_factory=dict)  # directed
    roads: frozenset = frozenset()                      # of edge(a, b)
    tracks: frozenset = frozenset()                     # of edge(a, b)
    fortifications: dict[Coord, int] = field(default_factory=dict)  # hex -> fort level (15.82)
    minefields: frozenset = frozenset()                 # of Coord: defensive minefield belt
    rails: frozenset = frozenset()                      # of edge(a, b): Commonwealth railroad (54.3)
    # Hex -> its map-section letter (A-E, or M=Malta), from the "S####" label the map was
    # transcribed under (game.cna_map). This is the geometry rule 29.7 needs: a foul-weather
    # result lands on 2-3 named sections, so every coupling that reads the weather at a HEX
    # (movement, breakdown, repair, construction, air, the supply trace) must know which
    # section the hex is in. Empty for a synthetic map (no section geometry) -> weather stays
    # theatre-wide there, byte-identical to before localisation (game.state.weather_at).
    sections: dict[Coord, str] = field(default_factory=dict)
    # Derived-value cache (perf only, NOT game state): per-(mobility, weather) adjacency rows
    # {hex: [(neighbor, step_cost), ...]} in neighbors() order, populated lazily by _adjacency via
    # step_cost so every stored float is bit-identical to the live chart. init=False + default_factory
    # means every constructor AND every dataclasses.replace() starts EMPTY, so a rebuilt map (the rail
    # construction in apply.py, the terrain replace in scenario.py) can never inherit a stale table.
    # compare=False/repr=False keep it out of __eq__/__repr__ (frozen forbids reassigning the field,
    # not mutating the dict it points to) so two states stay comparable and no signature can move.
    _edge_cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def exists(self, coord: Coord) -> bool:
        return coord in self.terrain


def rainstorm(weather: str) -> bool:
    """29.55/29.56: during a Rainstorm a Road is treated as a Track (for both CP and
    Breakdown Points) and wadi hexsides become uncrossable except by Road. Keyed off
    the canonical rule-29 weather label."""
    return weather == "rainstorm"


def sandstorm(weather: str) -> bool:
    """29.44: in a Sandstorm all Movement Costs are doubled. Keyed off the canonical
    rule-29 weather label."""
    return weather == "sandstorm"


def step_cost(tmap: TerrainMap, src: Coord, dst: Coord, mobility: Mobility,
              weather: str = "normal") -> float | None:
    """CP to move from src into the adjacent hex dst, or None if impossible (off-map,
    non-adjacent, or a prohibited terrain/hexside for this mobility). Weather (rule 29)
    couples in: a Rainstorm makes a Road behave as a Track (29.56) and closes wadi
    hexsides to everything but a Road (29.55); a Sandstorm doubles the whole cost
    (29.44). Under Normal/Hot weather this is byte-identical to the dry chart."""
    if not tmap.exists(dst) or not is_adjacent(src, dst):
        return None
    return _step_cost_known_adjacent(tmap, src, dst, mobility, weather)


def _step_cost_known_adjacent(tmap: TerrainMap, src: Coord, dst: Coord, mobility: Mobility,
                              weather: str = "normal") -> float | None:
    """step_cost's core for callers that already guarantee dst exists and is adjacent to src
    -- the _adjacency table build and zoc.zoc_extends, both of which draw dst from neighbors()
    and check tmap.exists first. It skips the redundant exists/is_adjacent gate (29.6M distance
    computations in the pre-table core) but is otherwise byte-identical to step_cost, which stays
    the checked public entry point for external callers."""
    e = (src, dst) if src <= dst else (dst, src)         # normalized undirected edge, no allocation churn
    on_road = e in tmap.roads
    on_track = e in tmap.tracks
    mot = mobility
    rain = rainstorm(weather)
    road_as_road = on_road and not rain                 # 29.56: a rained Road acts as a Track
    on_track_eff = on_track or (on_road and rain)

    if road_as_road:
        entry = ROAD_ENTRY[_mot(mot)]
    elif on_track_eff:
        entry = TRACK_ENTRY[_mot(mot)]
    else:
        entry = hex_entry_cost(tmap.terrain[dst], mot)
        if entry is None:
            return None

    feature = tmap.hexsides.get((src, dst))
    if feature is None or road_as_road:                 # dry road negates hexside costs (note 6)
        add = 0.0
    else:
        if rain and feature == Hexside.WADI and not on_road:   # 29.55: wadi shut except by road
            return None
        base = hexside_cost(feature, mot)
        if base is None:
            return None                                 # e.g. motorized up an escarpment
        if on_track_eff:
            # Track halves hexside costs, EXCEPT a *vehicle's* CP down an
            # escarpment (note 8); foot units still get the discount.
            no_halve = feature == Hexside.DOWN_ESCARPMENT and _mot(mot)
            add = base if no_halve else base / 2
        else:
            add = base

    cost = entry + add
    return cost * 2 if sandstorm(weather) else cost      # 29.44: sandstorm doubles movement


def breakdown_points(tmap: TerrainMap, src: Coord, dst: Coord, mobility: Mobility,
                     weather: str = "normal") -> float:
    """Breakdown Points accrued moving one step src->dst (rule 21.21 / 8.37), the
    pure dual of step_cost. Foot/camel accrue none (21.11). A Road contributes its
    own 1/2 value and NEGATES the hexside (note 6); a Track HALVES both the entered-
    hex and hexside value EXCEPT down an escarpment for a vehicle (note 8); during a
    Rainstorm a Road counts as a Track (29.56). A Light Truck moving off-road garners
    one extra Breakdown Point per hex entered and per hexside crossed (54.2 note)."""
    if not is_motorized(mobility):
        return 0.0
    e = (src, dst) if src <= dst else (dst, src)         # normalized undirected edge, no allocation churn
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


def path_cost(tmap: TerrainMap, path: list[Coord], mobility: Mobility,
              weather: str = "normal") -> float | None:
    """Total CP to traverse a contiguous path (path[0] is the start, not entered)."""
    total = 0.0
    for src, dst in zip(path, path[1:]):
        c = step_cost(tmap, src, dst, mobility, weather)
        if c is None:
            return None
        total += c
    return total


def reachable(tmap: TerrainMap, start: Coord, budget: float, mobility: Mobility,
              *, blocked: frozenset = frozenset(),
              terminal=None, passable=None, start_cost: float = 0.0,
              weather: str = "normal") -> dict[Coord, float]:
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
    return _search(tmap, start, budget, mobility, blocked=blocked, terminal=terminal,
                   passable=passable, start_cost=start_cost, weather=weather)[0]


def reachable_prev(tmap: TerrainMap, start: Coord, budget: float, mobility: Mobility,
                   *, blocked: frozenset = frozenset(), terminal=None, passable=None,
                   start_cost: float = 0.0,
                   weather: str = "normal") -> tuple[dict[Coord, float], dict[Coord, Coord]]:
    """`reachable`, additionally returning the predecessor map of the min-CP Dijkstra
    tree so the actual step-by-step path to a reached hex can be reconstructed (the
    Breakdown-Point accrual needs the hexes and hexsides the mover crossed, not just
    the destination and total cost)."""
    return _search(tmap, start, budget, mobility, blocked=blocked, terminal=terminal,
                   passable=passable, start_cost=start_cost, weather=weather)


def _adjacency(tmap: TerrainMap, mobility: Mobility,
               weather: str) -> dict[Coord, list[tuple[Coord, float]]]:
    """The precomputed edge-cost table for (mobility, weather): every hex mapped to its outgoing
    [(neighbor, step_cost), ...] rows, in neighbors() order, keeping only existing neighbours with a
    finite cost. step_cost is a pure function of the frozen map, so the immutable TerrainMap can
    memoise this derived value; it is built once per (mobility, weather) and cached on the map.
    Only "normal" and "rainstorm" are ever built -- a Sandstorm edge is exactly 2x a Normal edge
    (29.44), applied at use in _search. Rows are populated BY CALLING step_cost, so every stored float
    is bit-identical to the live chart and step_cost stays the single source of truth."""
    key = (mobility, weather)
    adj = tmap._edge_cache.get(key)
    if adj is not None:
        return adj
    adj = {}
    exists = tmap.exists
    for here in tmap.terrain:
        row = []
        for nb in neighbors(here):
            if not exists(nb):
                continue
            step = _step_cost_known_adjacent(tmap, here, nb, mobility, weather)
            if step is None:
                continue
            row.append((nb, step))
        adj[here] = row
    tmap._edge_cache[key] = adj
    return adj


def _search(tmap: TerrainMap, start: Coord, budget: float, mobility: Mobility,
            *, blocked, terminal, passable, start_cost, weather="normal") -> tuple[dict, dict]:
    # A Sandstorm reuses the Normal table doubled at use (29.44); a Rainstorm has its own table
    # (29.55/29.56); every other label behaves as Normal, so it maps to the Normal table too.
    if sandstorm(weather):
        adj, scale = _adjacency(tmap, mobility, "normal"), 2
    elif rainstorm(weather):
        adj, scale = _adjacency(tmap, mobility, "rainstorm"), 1
    else:
        adj, scale = _adjacency(tmap, mobility, "normal"), 1
    best: dict[Coord, float] = {start: start_cost}
    prev: dict[Coord, Coord] = {}
    pq: list[tuple[float, Coord]] = [(start_cost, start)]
    while pq:
        cost, here = heapq.heappop(pq)
        if cost > best.get(here, float("inf")):
            continue
        if terminal is not None and here != start and terminal(here):
            continue
        for nb, step in adj.get(here, ()):
            if nb in blocked:
                continue
            if passable is not None and not passable(here, nb):
                continue
            nc = cost + step * scale
            if nc <= budget and nc < best.get(nb, float("inf")):
                best[nb] = nc
                prev[nb] = here
                heapq.heappush(pq, (nc, nb))
    return best, prev


def reconstruct_path(prev: dict[Coord, Coord], start: Coord, dst: Coord) -> list[Coord]:
    """The min-CP path start..dst from a predecessor map (movement.reachable_prev /
    zoc.reachable_with_zoc_prev), or [] if dst was not reached."""
    if dst == start:
        return [start]
    path = [dst]
    while path[-1] != start:
        step = prev.get(path[-1])
        if step is None:
            return []
        path.append(step)
    path.reverse()
    return path


def _mot(mobility: Mobility) -> bool:
    return is_motorized(mobility)
