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
    # NOT Rosetta (E4019). It is a Port in the book's SUMMARY OF IMPORTANT LOCATIONS and a village
    # water source, it is currently unreachable (Swamp with no road/track edge), and it is TEMPTING to
    # add here -- an override was written and then REVERTED 2026-07-26. The five entries above correct
    # a SAMPLING ARTIFACT (a harbour's water dominates the port hex's patch and it mis-samples as sea);
    # E4019 is not that. The raster genuinely paints it the Key's swamp, tufts and all, read by eye.
    # Forcing it `clear` would make the terrain data lie about the map to paper over a MISSING ROAD
    # LAYER -- the debt is the road trace (8.1b), and the faithful fix is to trace the road, not to
    # falsify the fill. See tests/test_map_terrain_fills.py, which pins exactly this.
}


SAMPLE_RADIUS = 24        # patch half-size (px); the FILL/sea sample (48x48 = 2,304 px)
SEA_FRACTION = 0.55       # a hex is sea only if it is MOSTLY water

# The GLYPH sample: the largest disc that fits INSIDE a hex (inradius 42.6 px at this grid), so it
# can never bleed into a neighbour, and it sees 5,025 px -- 2.2x the fill patch's 2,304.
#
# WHY THE TWO SAMPLES DIFFER, and why that is not an inconsistency: a FILL is flat vector art that
# saturates any sample taken inside it (a patch in a fill returns 1,964-2,304 of 2,304 px of that one
# RGB), so widening the fill sample cannot sharpen the fill vote -- it only re-litigates which side of
# a region BOUNDARY a straddling hex falls on, a different question this slice does not reopen (and
# the sea test in particular must stay verbatim: terrain-key.md Sec 2 trap 2). A GLYPH is the exact
# opposite: gravel and swamp have NO fill colour at all, so a sparse stipple's DENSITY is the entire
# signal and the sample area IS the measurement.
#
# MEASURED, whole board (scratchpad/port/terrain-key.md Sec 4d.6 asked for exactly this eyeball):
# over the 48x48 patch the gravel histogram is NOT bimodal -- 8,056 hexes at 0, then 2 at 5-8, 52 at
# 9-16, 117 at 17-20, 277 at 21-37 -- so GLYPH_MIN=17 cut straight through a populated band and lost
# 54 hexes to CLEAR. Over the disc the same histogram is decisively bimodal: 8,040 at 0, 17 at 1-4,
# NOTHING AT ALL between 5 and 20, then 448 at 21+. Every threshold from 5 to 21 returns the same 448
# hexes. Rendered and read by eye: A1618/A1619/A1620/A1621/A1622 are five adjacent hexes under one
# unbroken pebble stipple that the patch classified gravel/clear/clear/clear/clear, and A1524 (a hex
# whose centre a wadi band crosses, which is what suppressed its patch count) is uniformly stippled.
# Swamp has no grey zone at all under either sample (nothing between 0 and 150 disc px).
GLYPH_RADIUS = 40

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
GLYPH_MIN = 17             # px in the GLYPH_RADIUS disc; it sits inside a genuinely empty histogram
                           # gap (gravel: nothing between 5 and 20; swamp: nothing between 0 and 150)


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


def _disc(radius: int) -> np.ndarray:
    """The inscribed-disc stencil for a (2r+1)^2 window."""
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    return (yy * yy + xx * xx) <= radius * radius


DISC = _disc(GLYPH_RADIUS)


def _count(window: np.ndarray, colour: tuple, stencil: np.ndarray | None = None) -> int:
    """Exact-colour pixel count in a window, optionally restricted to a stencil."""
    hit = ((window[..., 0] == colour[0]) & (window[..., 1] == colour[1])
           & (window[..., 2] == colour[2]))
    return int((hit & stencil).sum() if stencil is not None else hit.sum())


def classify_patch(patch: np.ndarray, glyph_window: np.ndarray | None = None) -> str:
    """Classify a hex: sea only if mostly water, else the dominant land terrain by
    exact-colour vote over `patch` (fold the salt-marsh/vegetation glyphs into their
    fill's count), falling back to the gravel/swamp overlay glyphs ONLY when nothing
    else won (they have no fill colour of their own -- they sit on bare clear ground).
    This keeps thin coastal land (ports, the coast road corridor) on the map instead
    of drowning it.

    The sparse gravel/swamp glyphs are counted over `glyph_window` masked by the
    inscribed DISC when one is supplied (see GLYPH_RADIUS: a stipple's density is the
    whole signal, so it gets the widest sample that cannot bleed into a neighbour);
    `patch` itself is the fallback for a hex too close to the raster edge to hold one."""
    m = _masks(patch)
    total = patch.shape[0] * patch.shape[1]
    if m["sea"].sum() >= SEA_FRACTION * total:
        return "sea"
    land = {k: int(v.sum()) for k, v in m.items() if k != "sea"}
    land["salt_marsh"] += _count(patch, GLYPH["salt_marsh"])
    land["vegetation"] += _count(patch, GLYPH["vegetation"])
    winner = max(land, key=land.get) if any(land.values()) else "clear"
    if winner == "clear":
        window = patch if glyph_window is None else glyph_window
        stencil = None if glyph_window is None else DISC
        if _count(window, GLYPH["gravel"], stencil) >= GLYPH_MIN:
            return "gravel"
        if _count(window, GLYPH["swamp"], stencil) >= GLYPH_MIN:
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
    R, D = SAMPLE_RADIUS, GLYPH_RADIUS
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
            glyph = (arr[yi - D:yi + D + 1, xi - D:xi + D + 1].astype(np.int16)
                     if D <= xi < W - D and D <= yi < H - D else None)
            out[h.label] = KNOWN_TERRAIN.get(h.label) or classify_patch(patch, glyph)
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
