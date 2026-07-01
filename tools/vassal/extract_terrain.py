"""Extract background terrain per hex from the VASSAL map image.

Terrain on the CNA map is colour-coded, so we sample a small patch at each hex
centre (via the per-section pixel calibration in game.coords) and classify by
colour. This recovers background terrain (clear / rough / desert / sea /
vegetation) reliably; it does NOT recover hexside features (escarpment / wadi /
road / track edges) — those are line features added separately (manual for now).
Validated by overlaying the classification on the map (see the terrain_validate
crop): dots align on hex centres and match the map's regions.

    python3 tools/vassal/extract_terrain.py [path/to/CNAv2.1.0.vmod]

Writes data/terrain_<section>.json (label -> terrain). Only Map C is pixel-
calibrated so far; extend SECTION_FIT as Maps A/B (etc.) are calibrated.
"""
from __future__ import annotations

import io
import json
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

# per-section pixel fit: px = a0 + a1*q + a2*r ; py = b0 + b1*q + b2*r
SECTION_FIT = {
    "C": ((5788.138, 40.1934, 84.8042), (4599.947, -73.4760, -0.5699)),
}
# rough hex ranges to sample per section (XX, YY); trims off-map margins
SECTION_RANGE = {"C": (range(30, 50), range(3, 40))}

# Coastal ports/towns whose hex is land+port but colour-samples as sea (the town
# sits on the shoreline). Their underlying terrain is coastal clear; the port is
# a separate feature. From the rulebook (60.x). Applied after colour classify.
KNOWN_TERRAIN = {
    "C4807": "clear",   # Tobruk (port, scenario objective)
    "C4321": "clear",   # Bardia (port)
    "C4021": "clear",   # Sollum (small port)
}


def classify(rgb) -> str:
    R, G, B = rgb
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


def pixel(section: str, h: coords.Hex) -> tuple[float, float]:
    (a0, a1, a2), (b0, b1, b2) = SECTION_FIT[section]
    q, r = coords.to_axial(h)
    return a0 + a1 * q + a2 * r, b0 + b1 * q + b2 * r


def extract(section: str, arr: np.ndarray) -> dict:
    xr, yr = SECTION_RANGE[section]
    out = {}
    for xx in xr:
        for yy in yr:
            h = coords.Hex(section, xx, yy)
            x, y = pixel(section, h)
            xi, yi = int(x), int(y)
            if not (9 <= xi < arr.shape[1] - 9 and 9 <= yi < arr.shape[0] - 9):
                continue
            med = np.median(arr[yi - 9:yi + 9, xi - 9:xi + 9].reshape(-1, 3), axis=0)
            out[h.label] = KNOWN_TERRAIN.get(h.label) or classify(med)
    return out


def main() -> int:
    vmod = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VMOD
    arr = np.asarray(Image.open(io.BytesIO(zipfile.ZipFile(vmod).read(MAP_IMAGE)))
                     .convert("RGB")).astype(int)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
    for section in SECTION_FIT:
        terrain = extract(section, arr)
        tally = {}
        for t in terrain.values():
            tally[t] = tally.get(t, 0) + 1
        path = os.path.normpath(os.path.join(out_dir, f"terrain_{section}.json"))
        with open(path, "w") as f:
            json.dump(terrain, f, indent=0, sort_keys=True)
        print(f"section {section}: {len(terrain)} hexes {tally} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
