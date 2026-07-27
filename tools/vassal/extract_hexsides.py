"""Extract escarpment hexsides from the VASSAL map image onto directed hex-edge pairs.

Escarpments are drawn as a solid charcoal BAND hugging a hexside (not a colour region, and not a
thin drawn line either -- a wide band with a ragged "splash" fringe on one side), so the pipeline is
a band detector, not a patch classifier or extract_roads.py's ridge filter:

  1. MASK: exact colour (94, 97, 98) -- and nothing else. terrain-key.md originally listed
     (51, 53, 51) and (84, 88, 89) as "escarpment secondary tones", but both occur in open clear
     terrain thousands of px from any escarpment, and (51, 53, 51) occurs over open sea -- they are
     the map's generic line/label ink (grid, track dashes, text). NOTHING is filtered out of the
     mask: the map's own charcoal lettering ("The Qatara Depression" is set in this exact ink) is
     left in, and rejected in step 3 where it is separable, rather than in the mask where it is not.
     The first cut of this tool dropped whole connected components below a max-inscribed-radius of
     5px on a claimed "empty trough at r=3-4"; re-measured, THE TROUGH IS NOT EMPTY (r=3: 4
     components / 452 px; r=4: 3 components / 1,355 px, three of them 378-533 px band segments
     broken by the vegetation and lettering glyphs drawn over them), and the filter silently cost
     FOUR real hexsides -- the Qattara north rim at the notch west of El Alamein, the Qara rim, and
     the Tobruk and Tocra coastal escarpments -- while the one lettering artifact it did catch there
     is caught by step 3(a) anyway. Component size does not separate band from lettering; SIDEDNESS
     does. (A fifth edge, the second of the two at Tocra, was lost to a PEAK_MIN that had been set
     one bin above the real trough because the filter had emptied the bins below it.)
  2. PROFILE: for every adjacent hex pair (game.hexmap neighbours, board-global axial), NSAMP points
     along the shared hexside (the perpendicular bisector of the two centres, corners excluded --
     three bands meet at a hex corner and a corner sample reads a NEIGHBOURING hexside's band), and
     at each one the ink count at every signed 1px normal offset out to TMAX.
  3. ORIENT AND ACCEPT, one measurement -- [8.35], PDF p.14, verbatim: "The splash contours of the
     respective terrain symbols are always on the 'down' side of the slope or escarpment." The map
     draws the WHOLE symbol (solid band AND splash fringe) on that one side, with the band's own
     crisp edge sitting ON the hexside line -- so ink side = DOWN, full stop; no band/splash
     separation is needed. That rule is also the ACCEPTANCE test, which is the point: if the ink
     straddles the hexside, the map has named no down side, and [8.35] says that is therefore not an
     escarpment hexside at all. So an edge is accepted only when
        (a) it is ONE-SIDED: min(ink either side) / max(...) <= SIDE_MAX. Measured, sharply
            bimodal with a wide EMPTY gap: 194 edges at <= 0.341 (median 0.000 -- the far side is
            literally empty), then nothing until 0.809 and 0.912, which are the map's lettering
            (the "D" of "Depression" standing on a hexside) and one band CORNER (two bands meeting
            at a hexside's lower vertex, ink dx -4..+2 across the line). Both were accepted by the
            first cut; both are rejected here, and eye-checked on the raster.
        (b) its peak ink count within +-NEAR px reaches PEAK_MIN of NSAMP. Over the ONE-SIDED
            edges this histogram has a measured EMPTY trough at 10-11/21 between a low "bleed" hump
            (<=9: an edge merely clipping a NEIGHBOURING hexside's band) and the real cluster
            (>=12, 181 of them at a perfect 21); PEAK_MIN sits in that trough, and the accepted set
            is identical for PEAK_MIN 10, 11 and 12.
     Orientation confirmed three independent ways (scratchpad/port/hexside-trace.md Sec 2): the
     rule's own words; two ground truths of OPPOSITE compass sign (the Mediterranean coast: down =
     seaward; the Qattara Depression floor: down = into the depression -- a method that merely
     learned "north is down" could not pass both); and the named Sollum/Halfaya Pass escarpment,
     where every traced tick points north-east, out to sea, exactly as [8.42] describes the Libyan
     Plateau rising from the coastal strip.

This is the promoted, committed form of Phase 8.1b Block A's read-only recon
(scratchpad/port/hexside-trace.md and scratchpad/hexside/*.py) -- same geometry, same orientation
rule, reproducible from the raster alone.

WHAT THIS DATA TURNS ON, AND WHAT IT DOES NOT (the recon's Sec 3.6 ship-blocking flag, retired by
measurement rather than by silence). Block A warned that landing escarpments without a road/track
layer would make Halfaya Pass and the Sollum escarpment one-way for every vehicle. One-way is
exactly what [8.42] says they are, and measured on the loaded map that costs nothing: of 189 loaded
edges exactly ONE coincides with a road (A5533/B5400 at Tocra) and none with a track or a railroad,
and forward VEHICLE reachability over the whole board is identical with the rim and with it
stripped -- every hex above an escarpment is still reachable, by the long way round. The flag was
real and is answered by measurement; tests/test_hexsides.py pins both halves.

    python3 tools/vassal/extract_hexsides.py [SECTIONS] [path/to/CNAv2.1.0.vmod]
    python3 tools/vassal/extract_hexsides.py ABCDE      # the whole board (the default)

The trace always runs over the FULL five-section board -- an escarpment edge can straddle a section
seam, so tracing one section in isolation (unlike extract_terrain.py/extract_roads.py, which have no
cross-section adjacency to worry about) would silently drop it. SECTIONS instead selects which
data/hexsides_<section>.json files get WRITTEN; every edge is filed once, under its DOWN hex's own
section (mirrors roads/tracks' per-section filing -- game.cna_map reads every requested section's
file and merges by axial).

Writes data/hexsides_<section>.json ({"escarpment": [[down_label, up_label], ...]}).
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
from game import cna_map, coords  # noqa: E402
from game.hexmap import neighbors  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
MAP_IMAGE = "images/CNA Map Vassal Mitch Guthrie 2021.png"
DEFAULT_VMOD = "/mnt/c/Users/evang/Downloads/CNAv2.1.0.vmod"
_DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# ONLY this colour -- see the module docstring's Sec 1 palette correction.
ESCARPMENT = (94, 97, 98)

NSAMP = 21        # sample points along a hexside
FRAC = 0.78       # fraction of the half-edge sampled (corners excluded; flat between 0.6 and 0.85)
NEAR = 9          # px; acceptance window around the hexside line
PEAK_MIN = 12     # of NSAMP; sits in the measured empty 10-11 trough of the one-sided edges
SIDE_MAX = 0.5    # max weak-side/strong-side ink ratio; sits in the measured empty 0.35-0.81 gap
TMAX = 34         # px; profile half-width
SQ3 = math.sqrt(3)


def _pack(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (r << 16) | (g << 8) | b


def _packed_map(arr: np.ndarray) -> np.ndarray:
    a = arr.astype(np.uint32)
    return (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]


def _all_hexes(sections: str) -> dict:
    """axial -> (px, py, label) for EVERY hex (land and sea) in `sections`, board-global axial --
    so this tool's edges key onto the SAME axials game.cna_map.load_sections will load, and the 4
    sea-touching escarpment edges (scratchpad/port/hexside-trace.md Sec 3.5.6) are traced here but
    left for the loader to silently drop, not invented into land. Sections are folded in fixed A-E
    order regardless of the `sections` argument's own order, so a shared seam axial (game.coords.
    to_axial's own A/B, D/E correction, or C/D's natural coincidence) resolves to the
    alphabetically-later section's own pixel/label -- the same "last write wins" convention
    game.cna_map.load_sections already uses for its terrain dict."""
    order = [s for s in "ABCDE" if s in sections]
    out: dict = {}
    for s in order:
        for label in cna_map._read(s):
            ax = coords.to_axial(coords.parse(label))
            px, py = coords.to_pixel(coords.parse(label))
            out[ax] = (px, py, label)
    return out


def _all_edges(hexes: dict) -> list:
    out, seen = [], set()
    for a in sorted(hexes):
        for b in neighbors(a):
            if b not in hexes:
                continue
            key = (a, b) if a < b else (b, a)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def _profile(mask: np.ndarray, hexes: dict, edges: list) -> tuple[np.ndarray, np.ndarray]:
    """prof[e, k] = how many of NSAMP points along edge e see mask ink at signed normal offset
    OFFS[k] (whole board, vectorised in chunks)."""
    H, W = mask.shape
    offs = np.arange(-TMAX, TMAX + 1, 1.0)
    fs = np.linspace(-1.0, 1.0, NSAMP)
    pa = np.array([hexes[a][:2] for a, b in edges])
    pb = np.array([hexes[b][:2] for a, b in edges])
    mid = (pa + pb) / 2
    d = pb - pa
    dist = np.hypot(d[:, 0], d[:, 1])
    n = d / dist[:, None]                       # normal, a -> b
    t = np.stack([-n[:, 1], n[:, 0]], axis=1)   # along the hexside
    half = dist / (2 * SQ3) * FRAC
    prof = np.zeros((len(edges), len(offs)), dtype=np.uint8)
    CH = 4000
    for lo in range(0, len(edges), CH):
        hi = min(lo + CH, len(edges))
        m_, tt, nn, hh = mid[lo:hi], t[lo:hi], n[lo:hi], half[lo:hi]
        base = m_[:, None, :] + tt[:, None, :] * (hh[:, None] * fs)[:, :, None]
        pts = base[:, :, None, :] + nn[:, None, None, :] * offs[None, None, :, None]
        x = np.clip(np.rint(pts[..., 0]).astype(np.int32), 0, W - 1)
        y = np.clip(np.rint(pts[..., 1]).astype(np.int32), 0, H - 1)
        prof[lo:hi] = mask[y, x].sum(axis=1).astype(np.uint8)
    return prof, offs


def trace_escarpment(arr: np.ndarray) -> tuple[dict, dict]:
    """Return ({section: [[down_label, up_label], ...]}, stats) over the WHOLE board."""
    mask = _packed_map(arr) == _pack(ESCARPMENT)
    hexes = _all_hexes("ABCDE")
    edges = _all_edges(hexes)
    prof, offs = _profile(mask, hexes, edges)
    peak = prof[:, np.abs(offs) <= NEAR].max(axis=1)

    out: dict = {s: [] for s in "ABCDE"}
    accepted = two_sided = 0
    for i, (a, b) in enumerate(edges):
        if peak[i] < PEAK_MIN:
            continue
        row = prof[i]
        pos = int(row[offs > 0].sum())
        neg = int(row[offs < 0].sum())
        if min(pos, neg) > SIDE_MAX * max(pos, neg):    # [8.35] names no down side here -> not an
            two_sided += 1                              # escarpment hexside; Sec 3(a)
            continue
        accepted += 1
        down, up = (b, a) if pos > neg else (a, b)      # ink (splash) side = DOWN, Sec 3
        down_label, up_label = hexes[down][2], hexes[up][2]
        out[down_label[0]].append([down_label, up_label])
    for s in out:
        out[s].sort()
    stats = {"candidates": int((peak >= PEAK_MIN).sum()), "accepted": accepted,
             "two_sided": two_sided, "mask_px": int(mask.sum())}
    return out, stats


def main() -> int:
    args = sys.argv[1:]
    vmod = next((a for a in args if a.endswith(".vmod")), DEFAULT_VMOD)
    letters = next((a.upper() for a in args if not a.endswith(".vmod")), "ABCDE")
    arr = np.asarray(Image.open(io.BytesIO(zipfile.ZipFile(vmod).read(MAP_IMAGE))).convert("RGB"))
    by_section, stats = trace_escarpment(arr)
    print(f"escarpment: {stats['candidates']} candidates (peak>={PEAK_MIN}), "
          f"{stats['accepted']} oriented, {stats['two_sided']} rejected two-sided, "
          f"mask {stats['mask_px']} px")
    for section in letters:
        edges = by_section.get(section, [])
        path = os.path.normpath(os.path.join(_DATA, f"hexsides_{section}.json"))
        with open(path, "w") as f:
            json.dump({"escarpment": edges}, f, indent=0, sort_keys=True)
        print(f"section {section}: {len(edges)} escarpment hexsides -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
