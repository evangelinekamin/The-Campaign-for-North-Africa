"""Extract background terrain per hex from the VASSAL map image.

Terrain on the CNA map is colour-coded, so we sample a small patch at each hex
centre and classify by colour. Hex centres come from game.coords.to_pixel, which
uses the EXACT VASSAL grid formula (data/cna_map_grid.json) — no per-section
fitting, so every section (A-E, Malta) works from its published parameters. This
recovers background terrain (clear / rough / desert / gravel / salt_marsh /
mountain / delta / swamp / vegetation / sea — [8.37] Phase 8.1a, see
scratchpad/port/terrain-key.md); it does NOT recover hexside features
(escarpment / wadi / road / track edges), which are line features added
separately (Phase 8.1b).

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
    "A4827": "clear",   # Benghazi (port, victory city 64.73)
    "E3714": "clear",   # Alexandria second hex (port, 64.71 auto-win objective)
}


SAMPLE_RADIUS = 24        # patch half-size (px); covers most of a ~85px hex
SEA_FRACTION = 0.55       # a hex is sea only if it is MOSTLY water

# The Guthrie raster is FLAT VECTOR ART, not a photographic scan: a whole-raster census
# (scratchpad/port/terrain-key.md Sec 2) finds each land terrain occupies exactly ONE RGB, bound to
# the Terrain Key (images/TEC.png in the same .vmod, the [8.37] chart's own swatch panel) by pattern
# + place-name. So classification is an exact-colour vote, not a CV/texture problem.
FILL = {
    "clear": (251, 250, 239),
    "desert": (223, 207, 100),
    "rough": (194, 185, 149),
    "delta": (164, 178, 171),          # the Nile Delta
    "salt_marsh": (186, 175, 129),     # the Qatara Depression / Wadi Natrun
    "mountain": (151, 136, 66),        # Jebel Akhdar massif core
    "vegetation": (203, 216, 91),      # keep the EXISTING key string, not "veg"
}
# Overlay glyphs, keyed by their own exact colour. salt_marsh's crackle net and vegetation's tree
# stipple sit ON their fill and simply add to that fill's vote; gravel's pebble-ring and swamp's
# grass-tuft glyphs sit on a bare CLEAR base and only ever PROMOTE a clear winner (there is no
# "gravel fill" or "swamp fill" colour -- the glyph is the whole signal).
GLYPH = {
    "salt_marsh": (222, 207, 99),
    "vegetation": (56, 142, 87),
    "gravel": (170, 157, 97),
    "swamp": (91, 161, 102),
}
GLYPH_MIN = 17             # px in the patch; the histogram gap terrain-key.md Sec 4a documents
                           # (gravel: nothing between 5-16 and nothing above 37; swamp: nothing 0-40)


def _masks(patch: np.ndarray) -> dict:
    """Per-pixel terrain masks over an HxWx3 patch (vectorised). The sea test is
    UNCHANGED and deliberately fuzzy -- it reads antialiased/shaded coastal blue
    that an exact match misses; exact-matching it moves 27 hexes across the
    land/sea line (terrain-key.md Sec 2, trap 2). Every land class below IS exact
    colour: this is flat vector art, not a photograph."""
    R, G, B = patch[..., 0], patch[..., 1], patch[..., 2]
    sea = (B > R + 12) & (B > 120)
    masks = {"sea": sea}
    for name, (r, g, b) in FILL.items():
        masks[name] = (R == r) & (G == g) & (B == b) & ~sea
    return masks


def classify_patch(patch: np.ndarray) -> str:
    """Classify a hex from a patch: sea only if mostly water, else the dominant
    land terrain by exact-colour vote (fold the salt-marsh/vegetation glyphs into
    their fill's count), falling back to the gravel/swamp overlay glyphs ONLY
    when nothing else won (they have no fill colour of their own -- they sit on
    bare clear ground). This keeps thin coastal land (ports, the coast road
    corridor) on the map instead of drowning it."""
    m = _masks(patch)
    total = patch.shape[0] * patch.shape[1]
    if m["sea"].sum() >= SEA_FRACTION * total:
        return "sea"
    R, G, B = patch[..., 0], patch[..., 1], patch[..., 2]
    land = {k: int(v.sum()) for k, v in m.items() if k != "sea"}
    land["salt_marsh"] += int(((R == GLYPH["salt_marsh"][0]) & (G == GLYPH["salt_marsh"][1])
                               & (B == GLYPH["salt_marsh"][2])).sum())
    land["vegetation"] += int(((R == GLYPH["vegetation"][0]) & (G == GLYPH["vegetation"][1])
                               & (B == GLYPH["vegetation"][2])).sum())
    winner = max(land, key=land.get) if any(land.values()) else "clear"
    if winner == "clear":
        gravel_px = int(((R == GLYPH["gravel"][0]) & (G == GLYPH["gravel"][1])
                         & (B == GLYPH["gravel"][2])).sum())
        swamp_px = int(((R == GLYPH["swamp"][0]) & (G == GLYPH["swamp"][1])
                        & (B == GLYPH["swamp"][2])).sum())
        if gravel_px >= GLYPH_MIN:
            return "gravel"
        if swamp_px >= GLYPH_MIN:
            return "swamp"
    return winner


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
