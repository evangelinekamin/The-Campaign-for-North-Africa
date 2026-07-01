"""Extract the road / track network from the VASSAL map image onto hex edges.

Roads, tracks, and the railroad are thin drawn LINES (not colour regions), so a
patch classifier can't see them. Instead:
  * ROADS are solid BROWN double-lines -> a ridge filter on the brown channel.
  * TRACKS are dashed GREY lines, the RAILROAD a crossed grey line -> a ridge
    filter on the neutral-grey channel, split by coverage (dashed vs solid) and
    max width (narrow track vs wide railroad ticks).
The printed HEX GRID is itself a thin line at every edge, so it is rendered from
game.coords and SUBTRACTED first; road orientation (along the centre-to-centre
segment) then rejects escarpment band edges (which cross it). Each surviving edge
becomes a road/track between two adjacent hexes -- exactly the engine's model.

    python3 tools/vassal/extract_roads.py [SECTIONS] [path/to/CNAv2.1.0.vmod]

Writes data/roads_<section>.json ({"roads": [[labelA,labelB],...], "tracks": ...}).
The railroad is detected but not emitted (the engine has no rail movement yet).
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, gaussian_filter
from skimage.filters import sato

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from game import coords  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
MAP_IMAGE = "images/CNA Map Vassal Mitch Guthrie 2021.png"
DEFAULT_VMOD = "/mnt/c/Users/evang/Downloads/CNAv2.1.0.vmod"
_DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")
MARGIN = 90


def _ridges(rgb: np.ndarray):
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    bright = (R + G + B) / 3
    brownish = (R >= G - 12) & (G >= B - 5) & ((R - B) > 22) & (bright < 205) & (bright > 55)
    brown = np.where(brownish, np.clip(215 - bright, 0, 170), 0.0)
    road = sato(brown, sigmas=[1, 2], black_ridges=False)
    neutral = (np.abs(R - G) < 24) & (np.abs(G - B) < 32) & (np.abs(R - B) < 32)
    grey = np.where(neutral, np.clip(150 - bright, 0, 150), 0.0)
    greyr = sato(grey, sigmas=[1, 2, 3], black_ridges=False)
    gx = gaussian_filter(brown, 1.0, order=(0, 1))
    gy = gaussian_filter(brown, 1.0, order=(1, 0))
    Jxx = gaussian_filter(gx * gx, 2.0); Jyy = gaussian_filter(gy * gy, 2.0)
    Jxy = gaussian_filter(gx * gy, 2.0)
    line_dir = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2
    return (road / (road.max() or 1)), (greyr / (greyr.max() or 1)), line_dir


def extract(section: str, arr: np.ndarray) -> dict:
    raw = json.load(open(os.path.join(_DATA, f"terrain_{section}.json")))
    hexes = [coords.parse(l) for l in raw]
    pts = {(h.xx, h.yy): coords.to_pixel(h) for h in hexes}
    xs = [p[0] for p in pts.values()]; ys = [p[1] for p in pts.values()]
    ox, oy = max(0, int(min(xs)) - MARGIN), max(0, int(min(ys)) - MARGIN)
    x1 = min(arr.shape[1], int(max(xs)) + MARGIN)
    y1 = min(arr.shape[0], int(max(ys)) + MARGIN)
    sub = arr[oy:y1, ox:x1].astype(float)
    Hh, Ww = sub.shape[:2]
    roadr, greyr, line_dir = _ridges(sub)

    # subtract the known hex grid (perpendicular segment at each edge midpoint)
    gimg = Image.new("L", (Ww, Hh), 0); gd = ImageDraw.Draw(gimg); seen = set()
    for h in hexes:
        pa = np.array(pts[(h.xx, h.yy)])
        for n in coords.neighbours(h):
            k = frozenset({(h.xx, h.yy), (n.xx, n.yy)})
            if k in seen:
                continue
            seen.add(k)
            pb = np.array(coords.to_pixel(n)); M = (pa + pb) / 2
            u = (pb - pa); u = u / (np.hypot(*u) or 1); v = np.array([-u[1], u[0]])
            gd.line([tuple((M + v * 24) - [ox, oy]), tuple((M - v * 24) - [ox, oy])],
                    fill=255, width=3)
    grid = binary_dilation(np.asarray(gimg) > 0, iterations=2)
    roadmask = (roadr > 0.10) & ~grid
    greymask = (greyr > 0.12) & ~grid

    def road_cov(pa, pb):
        seg = np.arctan2(pb[1] - pa[1], pb[0] - pa[0]); perp = np.array([-np.sin(seg), np.cos(seg)])
        cov = tot = 0
        for t in [x / 28 for x in range(5, 24)]:
            c = pa + (pb - pa) * t; hit = False
            for off in range(-4, 5):
                p = c + perp * off
                x, y = int(round(p[0])) - ox, int(round(p[1])) - oy
                if 0 <= y < Hh and 0 <= x < Ww and roadmask[y, x]:
                    if abs(((line_dir[y, x] - seg + np.pi / 2) % np.pi) - np.pi / 2) < 0.5:
                        hit = True; break
            tot += 1; cov += hit
        return cov / tot

    def grey_cov_w(pa, pb):
        seg = np.arctan2(pb[1] - pa[1], pb[0] - pa[0]); perp = np.array([-np.sin(seg), np.cos(seg)])
        cov = tot = mw = 0
        for t in [x / 28 for x in range(5, 24)]:
            c = pa + (pb - pa) * t; hit = False; w = 0
            for off in range(-9, 10):
                p = c + perp * off; x, y = int(round(p[0])) - ox, int(round(p[1])) - oy
                if 0 <= y < Hh and 0 <= x < Ww and greymask[y, x]:
                    w += 1
                    if abs(off) <= 4:
                        hit = True
            tot += 1; cov += hit; mw = max(mw, w)
        return cov / tot, mw

    roads, tracks = [], []
    seen = set(); present = set(pts)
    for h in hexes:
        pa = np.array(pts[(h.xx, h.yy)])
        for n in coords.neighbours(h):
            if (n.xx, n.yy) not in present:
                continue
            k = frozenset({(h.xx, h.yy), (n.xx, n.yy)})
            if k in seen:
                continue
            seen.add(k); pb = np.array(pts[(n.xx, n.yy)])
            if road_cov(pa, pb) >= 0.62:
                roads.append([h.label, n.label]); continue
            gc, gw = grey_cov_w(pa, pb)
            if gc >= 0.45 and gw < 8:                       # dashed & narrow -> track (rail is wide)
                tracks.append([h.label, n.label])
    return {"roads": roads, "tracks": tracks}


def main() -> int:
    args = sys.argv[1:]
    vmod = next((a for a in args if a.endswith(".vmod")), DEFAULT_VMOD)
    letters = next((a.upper() for a in args if not a.endswith(".vmod")), "C")
    arr = np.asarray(Image.open(io.BytesIO(zipfile.ZipFile(vmod).read(MAP_IMAGE))).convert("RGB"))
    for section in letters:
        out = extract(section, arr)
        path = os.path.normpath(os.path.join(_DATA, f"roads_{section}.json"))
        with open(path, "w") as f:
            json.dump(out, f, indent=0, sort_keys=True)
        print(f"section {section}: {len(out['roads'])} road edges, "
              f"{len(out['tracks'])} track edges -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
