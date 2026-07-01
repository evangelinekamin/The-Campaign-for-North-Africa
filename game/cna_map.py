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

from . import coords
from .movement import TerrainMap
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
    return TerrainMap(terrain=terrain), index


def load_section(section: str) -> tuple[TerrainMap, dict]:
    """Convenience wrapper for a single section (e.g. "C")."""
    return load_sections(section)
