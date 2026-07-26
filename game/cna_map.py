"""Load extracted CNA map terrain into an engine TerrainMap.

Bridges the map pipeline (data/terrain_<section>.json from tools/vassal/extract_terrain.py,
data/roads_<section>.json/data/hexsides_<section>.json from extract_roads.py/extract_hexsides.py)
to the engine's geometry. Hex labels convert to a BOARD-GLOBAL axial via game.coords (the same
axial the engine's movement uses), so several sections merge into one continuous map with
cross-section adjacency for free — no seam data (game.coords.to_axial carries its own A/B and D/E
correction, Phase 8.1b, found tracing hexsides). Sea hexes are dropped so land units simply cannot
enter them.
"""
from __future__ import annotations

import json
import os

from collections import defaultdict, deque

from . import coords
from .hexmap import neighbors
from .movement import TerrainMap, edge
from .terrain import Hexside, Terrain

_TERRAIN = {
    "clear": Terrain.CLEAR,
    "rough": Terrain.ROUGH,
    "desert": Terrain.DESERT,
    "vegetation": Terrain.HEAVY_VEG,
    "gravel": Terrain.GRAVEL,
    "salt_marsh": Terrain.SALT_MARSH,
    "mountain": Terrain.MOUNTAIN,
    "delta": Terrain.DELTA,
    "swamp": Terrain.SWAMP,
    "unknown": Terrain.CLEAR,       # conservative default
}
_DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def _resolve(t: str) -> Terrain:
    """Look up an extracted terrain string, LOUDLY: silently defaulting an unrecognised
    class to CLEAR (the old `_TERRAIN.get(t, Terrain.CLEAR)`) is the exact bug class
    Phase 8.1a exists to close -- a typo'd or newly-added extractor class would
    otherwise vanish into open ground with no signal. `_TERRAIN["unknown"]` above stays
    as the one deliberate, named exception (an extraction pass that could not classify
    a hex at all, distinct from an unrecognised STRING)."""
    try:
        return _TERRAIN[t]
    except KeyError:
        raise ValueError(
            f"unrecognised terrain class {t!r} in extracted data -- add a "
            "game.cna_map._TERRAIN key (see tools/vassal/extract_terrain.py's "
            "FILL/GLYPH tables)") from None

# HEXES THE RULEBOOK ITSELF NAMES AS LAND, against a colour sample that reads them as sea.
#
# data/terrain_<section>.json is not a transcription of a printed chart -- it is the output of
# colour-sampling the background of a map scan (tools/vassal/extract_terrain.py), and along the
# Gulf of Sirte that sample runs roughly one hex too far inland. Where the BOOK states outright
# that land units stand on a hex, the book wins. That is not a new principle invented here; it is
# the one this module and game.scenario already apply from two other evidence sources:
#   * _load_edges below: "A road runs on land, so any endpoint that colour-sampled as sea (coastal
#     road hexes) is added as coastal CLEAR" -- evidence from the roads data;
#   * game.scenario._connect_pieces / rommels_arrival: "A hex where a land unit stands is land:
#     coastal ports (El Agheila, Tobruk, ...) colour-sample as sea" -- evidence from the OOB.
# This table is the same override taken from the RULEBOOK, which is the strongest of the three.
#
# [8.85], verbatim: "For a unit to be moved off the game map towards Tripolitania it must start
# that Operations Stage in hex A2802. A unit entering the game-map from the off-map region is
# simply placed in the Road hex closest to the Tripolitania box." A sea hex holds no Stacking
# Points of land units and carries no road, so A2802 is land -- the book says so twice in one
# breath, and it says it in a MOVEMENT rule, with no reference to any victory condition.
#
# WHY IT MATTERS: A2802 is the on-map gateway to Tripoli, and rules 64.71/64.72 name Tobruk and
# Tripoli as the TWO harbours a Supply Dump must be feedable from. With A2802 sea, Tripoli had no
# hex, the trace ran on Tobruk alone, and MEASURED on the real campaign board the Commonwealth
# taking Tobruk collapsed the Axis from 13 fed dumps to 0 and all 177 of its combat units out of
# the 60-MP trace -- a 64.72 Commonwealth automatic win at Game-Turn 35, off a sampling error, in
# the exact historical situation (Tobruk falls, January 1941) where the Axis fought on out of
# Tripoli for two more years. See game.campaign_victory.
#
# FLAGGED, and deliberately NOT widened. Promoted as CLEAR, not as a road hex: 8.85 calls it a Road
# hex and a road is an EDGE in this pipeline (data/roads_<section>.json), so seeding the road here
# would be inventing a road net the extraction does not carry. CLEAR is the conservative reading --
# it makes the hex passable and no cheaper than open ground. STILL SEA, and still the open coastline
# job: A2803/A2804 (8.85's own "e.g., 5 points in hex 2802, 5 points in 2803, and 3 points in 2804"
# -- an illustration of stacking, where A2802 is the operative sentence) and A1816, El Agheila,
# which 61.43C names as a road hex. So Tripoli enters this map through a ONE-hex gateway where the
# book gives it a road; that understates the Axis's road home and can only make 64.72 fire more
# readily than the book, never less.
_RULEBOOK_LAND = {
    "A2802": "clear",       # [8.85] -- the Tripolitania gateway; Tripoli's source hex (64.71/64.72)
}


def _read(section: str) -> dict:
    path = os.path.normpath(os.path.join(_DATA, f"terrain_{section}.json"))
    with open(path) as f:
        return json.load(f)


def load_sections(sections: str) -> tuple[TerrainMap, dict]:
    """Return (TerrainMap, label->axial index) for the given sections' land hexes,
    merged into one board-global map. `sections` is a string like "ABC". Sections merge with
    NO seam data needed: game.coords.to_axial carries its own A/B and D/E correction, so every
    section's raw grid already lands a shared boundary hex on one board-global axial (like C/D's
    naturally-coinciding 21) and this loop's unconditional `terrain[ax] = ...` -- last section
    processed wins -- is the entire merge."""
    terrain: dict = {}
    index: dict = {}
    for section in sections:
        for label, t in _read(section).items():
            t = _RULEBOOK_LAND.get(label, t)    # the book outranks the colour sample (see above)
            if t == "sea":
                continue                # sea is off the land map -> impassable
            ax = coords.to_axial(coords.parse(label))
            terrain[ax] = _resolve(t)
            index[label] = ax
    roads, tracks = _load_edges(sections, terrain, index)
    hexsides = _load_hexsides(sections, terrain)
    # Invert the label->axial index into axial->section-letter (rule 29.7 geometry): every hex
    # carries the section of the "S####" label it was transcribed under. Built after the edges so
    # the coastal road hexes _load_edges promotes to land are sectioned too. The global axial is
    # unique per hex (it stitches the sections with no seam), so no two labels collide on one hex.
    hex_sections = {ax: label[0].upper() for label, ax in index.items()}
    return TerrainMap(terrain=terrain, roads=roads, tracks=tracks, hexsides=hexsides,
                       sections=hex_sections), index


def _load_hexsides(sections: str, terrain: dict) -> dict:
    """Load directed hexside features (tools/vassal/extract_hexsides.py output) as axial pairs.
    Phase 8.1b: only ESCARPMENT is traced so far (wadi/ridge/slope are deferred --
    scratchpad/port/hexside-trace.md Sec 4 -- their coverage statistic does not have this class's
    clean bimodal gap). [8.35]/[8.42]: the escarpment symbol (band + splash) is drawn wholly on the
    DOWN side, so data/hexsides_<section>.json's `[down_label, up_label]` pairs decode directly:
    moving FROM the low hex INTO the high one crosses UP; the reverse crosses DOWN.

    An edge whose down or up hex colour-sampled as sea (or was never a hex at all -- the tracer
    covers the raster, not the engine's land set) has no entry in `terrain` and is silently
    dropped, exactly like the [8.44]/road-hex debt cna_map._RULEBOOK_LAND documents -- not
    promoted to land, because the extraction gives no evidence a hex is there, only that the band
    passes through where one would be."""
    hexsides: dict = {}
    for section in sections:
        path = os.path.normpath(os.path.join(_DATA, f"hexsides_{section}.json"))
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for down, up in data.get("escarpment", ()):
            dx, ux = coords.to_axial(coords.parse(down)), coords.to_axial(coords.parse(up))
            if dx not in terrain or ux not in terrain:
                continue                                    # sea-touching edge -- see docstring
            hexsides[(dx, ux)] = Hexside.UP_ESCARPMENT       # low -> high crosses UP
            hexsides[(ux, dx)] = Hexside.DOWN_ESCARPMENT     # high -> low crosses DOWN
    return hexsides


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
