"""Golden positions for the land-movement core (rule 8.0) — hand-computed CP
costs straight off the Terrain Effects Chart."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import hexmap
from game.movement import TerrainMap, edge, path_cost, reachable, step_cost
from game.terrain import Hexside, Mobility, Terrain

LINE = [(0, 0), (1, 0), (2, 0), (3, 0)]


def clear_line() -> TerrainMap:
    return TerrainMap(terrain={c: Terrain.CLEAR for c in LINE})


def clear_field(radius: int) -> TerrainMap:
    coords = [(q, r)
              for q in range(-radius, radius + 1)
              for r in range(-radius, radius + 1)
              if hexmap.distance((0, 0), (q, r)) <= radius]
    return TerrainMap(terrain={c: Terrain.CLEAR for c in coords})


def test_clear_terrain_path_cost():
    tmap = clear_line()
    assert path_cost(tmap, LINE, Mobility.VEHICLE) == 6   # 3 hexes x 2 CP
    assert path_cost(tmap, LINE, Mobility.FOOT) == 6


def test_road_negates_and_cheapens():
    roads = frozenset(edge(a, b) for a, b in zip(LINE, LINE[1:]))
    tmap = TerrainMap(terrain={c: Terrain.CLEAR for c in LINE}, roads=roads)
    assert path_cost(tmap, LINE, Mobility.VEHICLE) == 1.5  # 3 x 1/2 CP
    assert path_cost(tmap, LINE, Mobility.FOOT) == 3       # 3 x 1 CP


def test_track_is_one_cp_per_hex():
    tracks = frozenset(edge(a, b) for a, b in zip(LINE, LINE[1:]))
    tmap = TerrainMap(terrain={c: Terrain.CLEAR for c in LINE}, tracks=tracks)
    assert path_cost(tmap, LINE, Mobility.VEHICLE) == 3
    assert path_cost(tmap, LINE, Mobility.FOOT) == 3


def test_wadi_hexside_costs():
    sides = {((0, 0), (1, 0)): Hexside.WADI}
    tmap = TerrainMap(terrain={(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR},
                      hexsides=sides)
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.FOOT) == 3      # 2 entry + 1 wadi
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 6   # 2 entry + 4 wadi
    # a track halves the wadi crossing
    tmap_t = TerrainMap(terrain=tmap.terrain, hexsides=sides,
                        tracks=frozenset({edge((0, 0), (1, 0))}))
    assert step_cost(tmap_t, (0, 0), (1, 0), Mobility.VEHICLE) == 3  # 1 entry + 4/2
    # a road negates it
    tmap_r = TerrainMap(terrain=tmap.terrain, hexsides=sides,
                        roads=frozenset({edge((0, 0), (1, 0))}))
    assert step_cost(tmap_r, (0, 0), (1, 0), Mobility.VEHICLE) == 0.5


def test_escarpment_prohibitions_and_track_exception():
    up = {((0, 0), (1, 0)): Hexside.UP_ESCARPMENT}
    down = {((0, 0), (1, 0)): Hexside.DOWN_ESCARPMENT}
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR}
    up_map = TerrainMap(terrain=terr, hexsides=up)
    assert step_cost(up_map, (0, 0), (1, 0), Mobility.FOOT) == 8     # 2 + 6
    assert step_cost(up_map, (0, 0), (1, 0), Mobility.VEHICLE) is None  # no vehicle up

    trk = frozenset({edge((0, 0), (1, 0))})
    down_map = TerrainMap(terrain=terr, hexsides=down, tracks=trk)
    # vehicle down-escarpment CP is NOT halved by track (note 8): 1 entry + 8
    assert step_cost(down_map, (0, 0), (1, 0), Mobility.VEHICLE) == 9
    # foot still gets the track discount: 1 entry + 4/2
    assert step_cost(down_map, (0, 0), (1, 0), Mobility.FOOT) == 3


def test_offmap_and_noncontiguous_return_none():
    tmap = clear_line()
    assert step_cost(tmap, (0, 0), (5, 0), Mobility.FOOT) is None     # not adjacent
    assert step_cost(tmap, (3, 0), (4, 0), Mobility.FOOT) is None     # off-map
    assert path_cost(tmap, [(0, 0), (4, 0)], Mobility.FOOT) is None


def test_reachable_respects_budget_and_blocking():
    tmap = clear_field(radius=5)
    reach = reachable(tmap, (0, 0), budget=6, mobility=Mobility.VEHICLE)
    assert reach[(3, 0)] == 6          # distance 3 x 2 CP
    assert (4, 0) not in reach         # would cost 8 > 6
    # block the direct neighbor; it must not appear, but detours still work
    blocked = frozenset({(1, 0)})
    reach_b = reachable(tmap, (0, 0), budget=6, mobility=Mobility.VEHICLE,
                        blocked=blocked)
    assert (1, 0) not in reach_b
    assert (2, 0) in reach_b           # reachable around the block
