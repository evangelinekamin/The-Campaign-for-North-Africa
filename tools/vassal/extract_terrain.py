"""Extract background terrain per hex from the VASSAL map image.

Terrain on the CNA map is colour-coded, so we sample a small patch at each hex
centre and classify by colour. Hex centres come from game.coords.to_pixel, which
uses the EXACT VASSAL grid formula (data/cna_map_grid.json) — no per-section
fitting, so every section (A-E, Malta) works from its published parameters. This
recovers background terrain (clear / rough / desert / sea / vegetation); it does
NOT recover hexside features (escarpment / wadi / road / track edges), which are
line features added separately.

    python3 tools/vassal/extract_terrain.py [SECTIONS] [path/to/CNAv2.1.0.vmod]
    python3 tools/vassal/extract_terrain.py ABC          # extract Maps A, B, C

Writes data/terrain_<section>.json (label -> terrain).
"""
from __future__ import annotations

import io
import json
import math
import os
import sys
import zipfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from game import coords  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
MAP_IMAGE = "images/CNA Map Vassal Mitch Guthrie 2021.png"
DEFAULT_VMOD = "/mnt/c/Users/evang/Downloads/CNAv2.1.0.vmod"
_GRID = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cna_map_grid.json")
_OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# Coastal ports/towns whose hex is land+port but colour-samples as sea (the town
# sits on the shoreline). Their underlying terrain is coastal clear; the port is
# a separate feature (rulebook 60.x). Applied after the colour classifier.
KNOWN_TERRAIN = {
    "C4807": "clear",   # Tobruk (port, scenario objective)
    "C4321": "clear",   # Bardia (port)
    "C4021": "clear",   # Sollum (small port)
}


SAMPLE_RADIUS = 24        # patch half-size (px); covers most of a ~85px hex
SEA_FRACTION = 0.55       # a hex is sea only if it is MOSTLY water


def _masks(patch: np.ndarray) -> dict:
    """Per-pixel terrain masks over an HxWx3 patch (vectorised; sea wins ties so a
    coastal hex with real land is still land)."""
    R, G, B = patch[..., 0], patch[..., 1], patch[..., 2]
    sea = (B > R + 12) & (B > 120)
    veg = (G > R + 8) & (G > B + 8) & ~sea
    desert = (R > 195) & (G > 150) & (B < 135) & (R - B > 70) & ~sea & ~veg
    clear = (R > 200) & (G > 195) & (B > 165) & ~sea & ~veg & ~desert
    rough = ((R > 120) & (R < 215) & (G > 115) & (G < 200) & (B < 160)
             & (np.abs(R - G) < 45) & ~sea & ~veg & ~desert & ~clear)
    return {"sea": sea, "vegetation": veg, "desert": desert, "clear": clear, "rough": rough}


def classify_patch(patch: np.ndarray) -> str:
    """Classify a hex from a patch: sea only if mostly water, else the dominant
    land terrain. This keeps thin coastal land (ports, the coast road corridor)
    on the map instead of drowning it."""
    m = _masks(patch)
    total = patch.shape[0] * patch.shape[1]
    if m["sea"].sum() >= SEA_FRACTION * total:
        return "sea"
    land = {k: int(v.sum()) for k, v in m.items() if k != "sea"}
    return max(land, key=land.get) if any(land.values()) else "clear"


def _bbox(section: str) -> tuple[int, int, int, int]:
    grid = json.load(open(os.path.normpath(_GRID)))
    name = "Malta" if section == "M" else f"Map {section}"
    for z in grid["zones"]:
        if z["name"] == name:
            return tuple(z["bbox"])
    raise KeyError(section)


def extract(section: str, arr: np.ndarray) -> dict:
    s = coords.SECTIONS[section]
    bx0, by0, bx1, by1 = _bbox(section)
    # raw index ranges that cover this section's bounding box (py=dx*nx+x0, px=dy*ny+..)
    nx_lo = int(math.floor((by0 - s.x0) / s.dx)) - 1
    nx_hi = int(math.ceil((by1 - s.x0) / s.dx)) + 1
    ny_lo = int(math.floor((bx0 - s.y0) / s.dy)) - 1
    ny_hi = int(math.ceil((bx1 - s.y0) / s.dy)) + 1
    H, W = arr.shape[:2]
    R = SAMPLE_RADIUS
    out: dict = {}
    for nx in range(nx_lo, nx_hi + 1):
        for ny in range(ny_lo, ny_hi + 1):
            h = coords.from_raw(section, nx, ny)
            x, y = coords.to_pixel(h)
            xi, yi = int(round(x)), int(round(y))
            if not (bx0 <= xi <= bx1 and by0 <= yi <= by1):
                continue
            if not (R <= xi < W - R and R <= yi < H - R):
                continue
            patch = arr[yi - R:yi + R, xi - R:xi + R].astype(np.int16)
            out[h.label] = KNOWN_TERRAIN.get(h.label) or classify_patch(patch)
    return out


def main() -> int:
    args = [a for a in sys.argv[1:]]
    vmod = next((a for a in args if a.endswith(".vmod")), DEFAULT_VMOD)
    letters = next((a.upper() for a in args if not a.endswith(".vmod")), "C")
    arr = np.asarray(Image.open(io.BytesIO(zipfile.ZipFile(vmod).read(MAP_IMAGE)))
                     .convert("RGB"))                       # uint8; patch-convert only
    for section in letters:
        terrain = extract(section, arr)
        tally: dict = {}
        for t in terrain.values():
            tally[t] = tally.get(t, 0) + 1
        path = os.path.normpath(os.path.join(_OUT, f"terrain_{section}.json"))
        with open(path, "w") as f:
            json.dump(terrain, f, indent=0, sort_keys=True)
        print(f"section {section}: {len(terrain)} hexes {tally} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
