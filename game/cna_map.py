"""Load extracted CNA map terrain into an engine TerrainMap.

Bridges the map pipeline (data/terrain_<section>.json, from
tools/vassal/extract_terrain.py) to the engine's geometry. Hex labels convert to
a BOARD-GLOBAL axial via game.coords (the same axial the engine's movement uses),
so several sections merge into one continuous map with cross-section adjacency for
free — no seam data. Sea hexes are dropped so land units simply cannot enter them;
hexside features (roads/tracks/escarpments) are not present yet (v1 background
terrain only).
"""
from __future__ import annotations

import json
import os

from collections import defaultdict, deque

from . import coords
from .hexmap import neighbors
from .movement import TerrainMap, edge
from .terrain import Terrain

_TERRAIN = {
    "clear": Terrain.CLEAR,
    "rough": Terrain.ROUGH,
    "desert": Terrain.DESERT,
    "vegetation": Terrain.HEAVY_VEG,
    "unknown": Terrain.CLEAR,       # conservative default
}
_DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def _read(section: str) -> dict:
    path = os.path.normpath(os.path.join(_DATA, f"terrain_{section}.json"))
    with open(path) as f:
        return json.load(f)


def load_sections(sections: str) -> tuple[TerrainMap, dict]:
    """Return (TerrainMap, label->axial index) for the given sections' land hexes,
    merged into one board-global map. `sections` is a string like "ABC"."""
    terrain: dict = {}
    index: dict = {}
    for section in sections:
        for label, t in _read(section).items():
            if t == "sea":
                continue                # sea is off the land map -> impassable
            ax = coords.to_axial(coords.parse(label))
            terrain[ax] = _TERRAIN.get(t, Terrain.CLEAR)
            index[label] = ax
    roads, tracks = _load_edges(sections, terrain, index)
    # Invert the label->axial index into axial->section-letter (rule 29.7 geometry): every hex
    # carries the section of the "S####" label it was transcribed under. Built after the edges so
    # the coastal road hexes _load_edges promotes to land are sectioned too. The global axial is
    # unique per hex (it stitches the sections with no seam), so no two labels collide on one hex.
    hex_sections = {ax: label[0].upper() for label, ax in index.items()}
    return TerrainMap(terrain=terrain, roads=roads, tracks=tracks, sections=hex_sections), index


def _load_edges(sections: str, terrain: dict, index: dict):
    """Load road/track edges (extract_roads.py output) as axial hex-pairs. A road
    runs on land, so any endpoint that colour-sampled as sea (coastal road hexes)
    is added as coastal CLEAR -- this also stitches the coast into one land mass."""
    roads: set = set()
    tracks: set = set()
    for section in sections:
        path = os.path.normpath(os.path.join(_DATA, f"roads_{section}.json"))
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for key, dst in (("roads", roads), ("tracks", tracks)):
            for a, b in data.get(key, ()):
                ax = coords.to_axial(coords.parse(a))
                bx = coords.to_axial(coords.parse(b))
                for lbl, c in ((a, ax), (b, bx)):
                    if c not in terrain:
                        terrain[c] = Terrain.CLEAR
                        index[lbl] = c
                dst.add(edge(ax, bx))
    _bridge_gaps(roads, terrain)                    # heal short CV gaps at road ends
    return frozenset(roads), frozenset(tracks)


def _bridge_gaps(roads: set, terrain: dict) -> None:
    """Heal short gaps the line CV leaves where roads curve: extend a road
    dead-end across <=2 hexes to reconnect a separate road segment. In-place;
    intermediate hexes are promoted to land. Deterministic (sorted scans)."""
    adj: dict = defaultdict(set)
    for e in roads:
        a, b = tuple(e)
        adj[a].add(b); adj[b].add(a)
    comp: dict = {}
    for start in sorted(adj):
        if start in comp:
            continue
        comp[start] = start; stack = [start]
        while stack:
            x = stack.pop()
            for n in adj[x]:
                if n not in comp:
                    comp[n] = start; stack.append(n)
    road_hexes = set(adj)
    for A in sorted(h for h in adj if len(adj[h]) <= 1):
        prev = {A: None}; dq = deque([A]); hit = None
        for _ in range(2):                          # up to a 2-hex gap
            nxt = []
            for x in list(dq):
                for n in neighbors(x):
                    if n in prev:
                        continue
                    prev[n] = x
                    if n in road_hexes and comp.get(n) != comp.get(A):
                        hit = n; break
                    nxt.append(n)
                if hit:
                    break
            dq = deque(nxt)
            if hit:
                break
        if hit is None:
            continue
        node = hit
        while node != A:                            # add the bridging edges
            p = prev[node]
            roads.add(edge(node, p))
            terrain.setdefault(node, Terrain.CLEAR)
            node = p
        merged = comp.get(hit)
        for h in list(comp):
            if comp[h] == merged:
                comp[h] = comp[A]


def load_section(section: str) -> tuple[TerrainMap, dict]:
    """Convenience wrapper for a single section (e.g. "C")."""
    return load_sections(section)
