"""Golden positions for the land-movement core (rule 8.0) — hand-computed CP
costs straight off the Terrain Effects Chart."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import hexmap
from game.movement import TerrainMap, _adjacency, edge, path_cost, reachable, step_cost
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


def test_salt_marsh_gate_bars_vehicles_off_road_and_track():
    """[8.44] / [8.37] note 2: a barred vehicle "may enter or leave a Salt Marsh hex only on a
    Road or Track" -- so the gate reads BOTH ends of the edge, and the exempt light classes and
    the foot/camel column still pay the chart's plain cell. Without it the marsh's 2 CP Mot entry
    would be the CHEAPEST motorized ground on the board (Desert and Rough are both 4)."""
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.SALT_MARSH, (2, 0): Terrain.CLEAR}
    tmap = TerrainMap(terrain=terr)
    for barred in (Mobility.MOTORIZED, Mobility.VEHICLE):
        assert step_cost(tmap, (0, 0), (1, 0), barred) is None      # may not ENTER
        assert step_cost(tmap, (1, 0), (2, 0), barred) is None      # nor LEAVE
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.FOOT) == 3      # chart non-Mot cell
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.CAMEL) == 3     # 8.44: travels as infantry
    for exempt in (Mobility.LIGHT_TRUCK, Mobility.RECCE, Mobility.MOTORCYCLE):
        assert step_cost(tmap, (0, 0), (1, 0), exempt) == 2         # chart Mot cell

    # ... and a Road or a Track opens it to everyone, at that edge's own cost.
    on_track = TerrainMap(terrain=terr, tracks=frozenset({edge((0, 0), (1, 0))}))
    assert step_cost(on_track, (0, 0), (1, 0), Mobility.VEHICLE) == 1
    on_road = TerrainMap(terrain=terr, roads=frozenset({edge((0, 0), (1, 0))}))
    assert step_cost(on_road, (0, 0), (1, 0), Mobility.VEHICLE) == 0.5
    # A road/track on the FAR side does not license the barred step it does not cross.
    far = TerrainMap(terrain=terr, tracks=frozenset({edge((1, 0), (2, 0))}))
    assert step_cost(far, (0, 0), (1, 0), Mobility.VEHICLE) is None
    assert step_cost(far, (1, 0), (2, 0), Mobility.VEHICLE) == 1


def test_desert_gate_bars_entry_only_no_road_or_track_exemption():
    """[8.45] / [8.37] note 3: Light Trucks and motorcycle infantry "may not enter any Desert
    hexes, whether traversed by Tracks or not" -- entry only (unlike [8.44]'s enter-or-leave), and
    with no Road exemption either: the rule names Track by itself to close that loophole and says
    nothing at all about Road, in contrast to [8.44]'s explicit "Road or Track" two paragraphs
    earlier."""
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.DESERT, (2, 0): Terrain.CLEAR}
    tmap = TerrainMap(terrain=terr)
    for barred in (Mobility.LIGHT_TRUCK, Mobility.MOTORCYCLE):
        assert step_cost(tmap, (0, 0), (1, 0), barred) is None       # may not ENTER
        assert step_cost(tmap, (1, 0), (2, 0), barred) == 2          # but MAY leave -- entry-only
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.FOOT) == 3        # chart non-Mot cell, ungated
    assert step_cost(tmap, (0, 0), (1, 0), Mobility.RECCE) == 4       # ungated: not "motorcycle" Recce

    # Neither a Track nor a Road opens it -- the opposite of the Salt Marsh gate.
    on_track = TerrainMap(terrain=terr, tracks=frozenset({edge((0, 0), (1, 0))}))
    assert step_cost(on_track, (0, 0), (1, 0), Mobility.LIGHT_TRUCK) is None
    on_road = TerrainMap(terrain=terr, roads=frozenset({edge((0, 0), (1, 0))}))
    assert step_cost(on_road, (0, 0), (1, 0), Mobility.LIGHT_TRUCK) is None
    # ... while an unbarred class rides the road/track discount through the same hex normally.
    assert step_cost(on_road, (0, 0), (1, 0), Mobility.VEHICLE) == 0.5


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


def _rich_map() -> TerrainMap:
    """A connected blob exercising every step_cost branch the shipped maps do not yet carry
    (both transcribed maps have hexsides == {}): varied terrain, a road, a track, and up/down
    escarpment, wadi (with and without a road), major/minor river, up-slope and ridge hexsides."""
    coords = [(q, r) for q in range(-2, 3) for r in range(-2, 3)
              if hexmap.distance((0, 0), (q, r)) <= 2]
    terr = {c: Terrain.CLEAR for c in coords}
    terr[(1, 0)] = Terrain.MOUNTAIN
    terr[(0, 1)] = Terrain.ROUGH
    terr[(-1, 0)] = Terrain.MAJOR_CITY
    terr[(1, -1)] = Terrain.DESERT
    hexsides = {
        ((0, 0), (1, 0)): Hexside.UP_ESCARPMENT,     # no vehicle up (-> None)
        ((1, 0), (0, 0)): Hexside.DOWN_ESCARPMENT,   # note-8 track exception (track edge below)
        ((0, 0), (0, 1)): Hexside.WADI,              # road below keeps it open in a rainstorm
        ((0, 0), (-1, 0)): Hexside.MAJOR_RIVER,      # motorized prohibited (-> None)
        ((0, 0), (0, -1)): Hexside.MINOR_RIVER,
        ((1, -1), (0, 0)): Hexside.WADI,             # road-less wadi (-> None in a rainstorm)
        ((-1, 1), (0, 0)): Hexside.UP_SLOPE,
        ((0, 1), (0, 0)): Hexside.RIDGE,
    }
    return TerrainMap(terrain=terr, hexsides=hexsides,
                      roads=frozenset({edge((0, 0), (0, 1))}),
                      tracks=frozenset({edge((1, 0), (0, 0))}))


def test_edge_cost_table_locks_to_live_step_cost():
    """THE BYTE-IDENTITY LOCK for the precomputed _search adjacency table. Over every directed edge x
    mobility x weather the table must reproduce step_cost exactly -- membership (an edge is absent iff
    step_cost is None) and value (normal/rainstorm straight from the table; a sandstorm edge = the
    normal edge doubled, rule 29.44) -- reconstructed precisely as _search consumes it. Any divergence
    would make a Dijkstra flood take a different edge and move the determinism signature."""
    tmap = _rich_map()
    for mob in Mobility:
        normal_adj = _adjacency(tmap, mob, "normal")
        rain_adj = _adjacency(tmap, mob, "rainstorm")
        # every non-storm label ("normal", "hot", ...) is served by the normal table at scale 1;
        # a sandstorm reuses the normal table at scale 2; a rainstorm has its own table.
        for weather, (adj, scale) in {"normal": (normal_adj, 1), "hot": (normal_adj, 1),
                                      "sandstorm": (normal_adj, 2),
                                      "rainstorm": (rain_adj, 1)}.items():
            for here in tmap.terrain:
                row = dict(adj[here])
                for nb in hexmap.neighbors(here):
                    if not tmap.exists(nb):
                        continue
                    live = step_cost(tmap, here, nb, mob, weather)
                    ctx = (here, nb, mob.name, weather)
                    if live is None:
                        assert nb not in row, ctx
                    else:
                        assert nb in row, ctx
                        assert row[nb] * scale == live, (ctx, row[nb] * scale, live)
