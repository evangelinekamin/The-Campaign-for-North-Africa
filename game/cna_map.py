"""Load extracted CNA map terrain into an engine TerrainMap.

Bridges the map pipeline (data/terrain_<section>.json, produced by
tools/vassal/extract_terrain.py) to the engine's geometry. Hex labels are
converted to axial via game.coords (same axial system the engine's movement
uses); sea hexes are dropped so land units simply cannot enter them; hexside
features (roads/tracks/escarpments) are not present yet (v1 background terrain).
Single-section only for now — cross-section global axial is a later step.
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


def load_section(section: str) -> tuple[TerrainMap, dict]:
    """Return (TerrainMap, label->axial index) for one map section's land hexes."""
    path = os.path.normpath(os.path.join(_DATA, f"terrain_{section}.json"))
    with open(path) as f:
        raw = json.load(f)
    terrain: dict = {}
    index: dict = {}
    for label, t in raw.items():
        if t == "sea":
            continue                # sea is off the land map -> impassable
        ax = coords.to_axial(coords.parse(label))
        terrain[ax] = _TERRAIN.get(t, Terrain.CLEAR)
        index[label] = ax
    return TerrainMap(terrain=terrain), index
