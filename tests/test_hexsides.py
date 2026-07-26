"""Phase 8.1b: the escarpment hexside trace, wired into TerrainMap.hexsides.

data/hexsides_<section>.json (tools/vassal/extract_hexsides.py) is classifier output, exactly
like data/terrain_<section>.json before it (tests/test_map_terrain_fills.py's own framing) -- so
this file pins the same class of thing: the raw counts, the [8.35]/[8.42] direction convention
decoding correctly, and the two previously-dead consumers (movement.step_cost's hexside cost,
zoc.py's ZOC_BLOCKING_HEXSIDES) actually lighting up on the real map.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import cna_map, coords                                          # noqa: E402
from game.movement import step_cost                                       # noqa: E402
from game.terrain import Hexside, Mobility                                # noqa: E402
from game.zoc import zoc_extends                                          # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
SECTIONS = "ABCDE"


def _raw_escarpment() -> dict:
    return {s: json.loads((DATA / f"hexsides_{s}.json").read_text())["escarpment"]
            for s in SECTIONS}


def test_the_trace_is_around_190_edges_all_escarpment_in_section():
    """Every [down, up] pair is filed under the DOWN hex's own section letter (extract_hexsides.py's
    bucketing rule) -- a loud, cheap check that a future re-trace didn't mix up the convention."""
    raw = _raw_escarpment()
    total = sum(len(v) for v in raw.values())
    assert 150 <= total <= 230, f"escarpment trace count moved a lot: {total}"
    for section, edges in raw.items():
        for down, up in edges:
            assert down[0] == section, f"{down}->{up} filed under {section}, down is {down[0]}"


def test_hexsides_load_directed_both_ways_with_no_ties():
    """Every traced edge becomes exactly two directed TerrainMap.hexsides entries (Sec 2's ruling:
    ink/splash side = DOWN), and the two counts must be equal -- an UP with no matching DOWN (or
    vice versa) means the loader or the trace's orientation broke."""
    tmap, index = cna_map.load_sections("ABCDE")
    ups = [k for k, v in tmap.hexsides.items() if v is Hexside.UP_ESCARPMENT]
    downs = [k for k, v in tmap.hexsides.items() if v is Hexside.DOWN_ESCARPMENT]
    assert len(ups) == len(downs) > 0
    assert len(tmap.hexsides) == len(ups) + len(downs)
    for down_ax, up_ax in ups:
        assert (up_ax, down_ax) in tmap.hexsides
        assert tmap.hexsides[(up_ax, down_ax)] is Hexside.DOWN_ESCARPMENT


def test_hexsides_scale_with_the_requested_sections():
    """A C-only load must carry only escarpment edges with both ends inside Map C; loading more
    sections only ever adds entries, never removes or reorders the existing ones (each edge's
    axial identity is section-independent)."""
    tmap_c, _ = cna_map.load_section("C")
    tmap_abc, _ = cna_map.load_sections("ABC")
    tmap_all, _ = cna_map.load_sections("ABCDE")
    assert 0 < len(tmap_c.hexsides) < len(tmap_abc.hexsides) < len(tmap_all.hexsides)
    assert set(tmap_c.hexsides.items()) <= set(tmap_abc.hexsides.items())
    assert set(tmap_abc.hexsides.items()) <= set(tmap_all.hexsides.items())


def test_a_sea_touching_escarpment_edge_is_silently_dropped_not_promoted():
    """[8.1b Sec 3.5.6]: an edge whose down or up hex colour-sampled as sea has no entry in
    `terrain` and must not appear in `hexsides` either -- not promoted to land the way a coastal
    ROAD hex is (cna_map._load_edges' own, different, evidence-backed exception)."""
    tmap, index = cna_map.load_sections("ABCDE")
    raw = _raw_escarpment()
    dropped = 0
    for section, edges in raw.items():
        for down, up in edges:
            dax = coords.to_axial(coords.parse(down))
            uax = coords.to_axial(coords.parse(up))
            if dax not in tmap.terrain or uax not in tmap.terrain:
                dropped += 1
                assert (dax, uax) not in tmap.hexsides
                assert (uax, dax) not in tmap.hexsides
    assert dropped > 0, "expected at least one sea-touching escarpment edge (Sec 3.5.6)"


def test_up_escarpment_bars_only_vehicles_matching_the_837_chart():
    """[8.42]: "No vehicle may ever move up an escarpment" -- foot pays a real, non-prohibitive
    cost; a motorized/vehicle unit gets None (impassable) regardless of road or track, because the
    chart's UP_ESCARPMENT motorized cost is PROHIBITED outright, not merely expensive."""
    tmap, index = cna_map.load_sections("ABCDE")
    up_edge = next(k for k, v in tmap.hexsides.items() if v is Hexside.UP_ESCARPMENT)
    src, dst = up_edge
    assert step_cost(tmap, src, dst, Mobility.VEHICLE) is None
    assert step_cost(tmap, src, dst, Mobility.MOTORIZED) is None
    foot_cost = step_cost(tmap, src, dst, Mobility.FOOT)
    assert foot_cost is not None and foot_cost > 0
    # and the reverse direction (high -> low) is DOWN_ESCARPMENT, passable to a vehicle
    assert tmap.hexsides[(dst, src)] is Hexside.DOWN_ESCARPMENT
    assert step_cost(tmap, dst, src, Mobility.VEHICLE) is not None


def test_zoc_does_not_cross_a_traced_escarpment():
    """[10.21a/b] via game.zoc.ZOC_BLOCKING_HEXSIDES -- dead code before this slice landed any
    hexsides (zoc.py:26 had nothing to match against on the real map). Blocks BOTH directions and
    every mobility class, matching the rule (ZOC is a control effect, not a movement one)."""
    tmap, index = cna_map.load_sections("ABCDE")
    up_edge = next(k for k, v in tmap.hexsides.items() if v is Hexside.UP_ESCARPMENT)
    src, dst = up_edge
    assert zoc_extends(src, dst, tmap, Mobility.FOOT) is False
    assert zoc_extends(dst, src, tmap, Mobility.FOOT) is False
    assert zoc_extends(src, dst, tmap, Mobility.VEHICLE) is False


def test_the_alamein_rim_does_not_narrow_the_front():
    """[8.1b's headline finding]: only UP_ESCARPMENT and MAJOR_RIVER are prohibited to a vehicle in
    the whole [8.37] hexside table, and the Qattara rim's escarpment lies entirely on the
    depression's own north face -- four hexes west of El Alamein's meridian, per
    scratchpad/port/hexside-trace.md Sec 5.3. So a vehicle can walk around the depression's eastern
    tip on ground the escarpment never touches: the cheapest coastal route is unaffected by the
    hexsides being present at all. Cheap, deterministic proxy for the slice's own min-vertex-cut
    probe (scratchpad/hexside/corridor2.py): the coastal road route from west of the depression to
    Alexandria costs the same with or without the traced rim."""
    from dataclasses import replace
    tmap, index = cna_map.load_sections("ABCDE")
    no_rim = replace(tmap, hexsides={})
    west, alex = index["D0233"], index["E3714"]

    def cheapest(m):
        import heapq
        from game.hexmap import neighbors
        dist = {west: 0.0}
        pq = [(0.0, west)]
        while pq:
            du, u = heapq.heappop(pq)
            if u == alex:
                return du
            if du > dist.get(u, 1e18):
                continue
            for v in neighbors(u):
                if v not in m.terrain:
                    continue
                c = step_cost(m, u, v, Mobility.MOTORIZED)
                if c is None:
                    continue
                nd = du + c
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        return None

    assert cheapest(tmap) == cheapest(no_rim)
