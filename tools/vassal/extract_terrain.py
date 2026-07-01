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


def classify(rgb) -> str:
    R, G, B = (int(v) for v in rgb)
    if B > R + 12 and B > 120:
        return "sea"
    if G > R + 8 and G > B + 8:
        return "vegetation"
    if R > 195 and G > 150 and B < 135 and R - B > 70:
        return "desert"
    if R > 200 and G > 195 and B > 165:
        return "clear"
    if 120 < R < 215 and 115 < G < 200 and B < 160 and abs(R - G) < 45:
        return "rough"          # includes escarpment bands (hexsides refined later)
    return "unknown"


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
    out: dict = {}
    for nx in range(nx_lo, nx_hi + 1):
        for ny in range(ny_lo, ny_hi + 1):
            h = coords.from_raw(section, nx, ny)
            x, y = coords.to_pixel(h)
            xi, yi = int(round(x)), int(round(y))
            if not (bx0 <= xi <= bx1 and by0 <= yi <= by1):
                continue
            if not (9 <= xi < W - 9 and 9 <= yi < H - 9):
                continue
            patch = arr[yi - 9:yi + 9, xi - 9:xi + 9].reshape(-1, 3)
            med = np.median(patch, axis=0)
            out[h.label] = KNOWN_TERRAIN.get(h.label) or classify(med)
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
