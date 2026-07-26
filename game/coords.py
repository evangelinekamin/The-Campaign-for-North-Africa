"""CNA hex-label coordinate system, built on the VASSAL map's exact geometry.

A rulebook hex is "S####" — a section letter (A-E, or M=Malta) plus a 4-digit
XXYY label (e.g. "C4807"). Each map section is a VASSAL HexGrid whose parameters
(dx, dy, x0, y0, hOff, vOff, stagger) live in data/cna_map_grid.json. Those
parameters, run through VASSAL's own numbering + placement maths, give BOTH the
board-image pixel of every hex centre (for terrain sampling) AND — because the
raw grid indices (nx, ny) are continuous across the whole board — a single GLOBAL
axial coordinate that stitches the sections together with no seam data.

Geometry (decoded from VASSAL HexGrid/HexGridNumbering; every CNA section is
sideways with vDescend and no hDescend):

    gMR   = floor(zone_bbox_height / dx + 0.5)          # getMaxRows (zone, not board)
    nx    = gMR + hOff - XX                              # raw column (staggering axis)
    ny    = YY - vOff - (1 if stagger and nx odd else 0) # raw row
    px    = dy*ny + (dy/2 if nx odd else 0) + y0         # board-image pixel (sideways
    py    = dx*nx + x0                                   #   swap already applied)

The raw grid is odd-q offset (odd nx columns carry the +dy/2 shift), so the global
axial is q = nx, r = ny - (nx - (nx & 1)) // 2, PLUS a per-section constant correction
(_SEAM_SHIFT, Phase 8.1b) at the A/B and D/E joins, where each section's raw grid alone
does not land the boundary on one shared axial the way C/D's happens to. Neighbours and
distances follow exactly and are pixel-independent. See memory: vassal-coordinate-formula.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

AXIAL_DIRS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))

_GRID_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cna_map_grid.json")


@dataclass(frozen=True, slots=True)
class Section:
    """One map section's VASSAL grid parameters (all distances in board pixels)."""
    letter: str
    dx: float
    dy: float
    x0: float
    y0: float
    hOff: int
    vOff: int
    stagger: bool
    gMR: int                        # getMaxRows for this zone
    bbox: tuple[int, int, int, int]  # zone bounding box (x0, y0, x1, y1)


def _load_sections() -> dict[str, Section]:
    with open(os.path.normpath(_GRID_PATH)) as f:
        grid = json.load(f)
    out: dict[str, Section] = {}
    for z in grid["zones"]:
        hg, nm, name = z.get("hexgrid"), z.get("numbering"), z["name"]
        if not hg or not nm:
            continue                       # holding boxes / tracks have no grid
        letter = "M" if name == "Malta" else name.split()[-1]
        if len(letter) != 1:
            continue
        bx0, by0, bx1, by1 = z["bbox"]
        out[letter] = Section(
            letter=letter, dx=hg["dx"], dy=hg["dy"], x0=hg["x0"], y0=hg["y0"],
            hOff=nm["hOff"], vOff=nm["vOff"], stagger=nm.get("stagger", False),
            gMR=int(math.floor((by1 - by0) / hg["dx"] + 0.5)),
            bbox=(bx0, by0, bx1, by1),
        )
    return out


SECTIONS: dict[str, Section] = _load_sections()

# [44.11] MALTA IS AN OFF-SCALE BOX, NOT A CONTINUATION OF THE HEX GRID. "The map of Malta
# represented on GameMap 'A' is not in the same scale as the African portions of the game-maps, nor
# is it in scale in terms of geographic location vis-a-vis the African coast." The VASSAL redraw
# prints that box inside section A's own corner of the board image (its bbox 40,78..692,764 sits
# INSIDE A's 44,447..2863,4557), so the raw grid indices the box numbers its hexes with are section
# A's indices over again: M0802 and A5504 both raw-index to (7,0), M0704 and A5405 to (8,1), M0604
# and A5306 to (9,1), M0805 and A5507 to (7,3). The module docstring's "raw grid indices are
# continuous across the whole board" is true of A-E, which abut; it was never true of this box.
#
# The aliasing is not cosmetic: the engine keys air facilities, control and dumps BY HEX
# (air.facility_at, air.holder, air.facility_dumps), so an unshifted Malta means an Axis unit
# standing on a clear hex of section A silently becomes the holder of a Maltese airfield. Off-scale
# sections are therefore translated into their own disjoint slice of the global axial space. The
# shift is DERIVED from the grid data, not chosen: one past the largest column index any mainland
# section can number (nx = gMR + hOff at XX=0), so it can never meet the board however the redraw
# is re-measured. It is a key-space disambiguation and nothing else -- distances and neighbours
# WITHIN the box are untouched (every M hex moves by the same amount), and no rule reads a
# map distance between Malta and Africa: 44.11 puts those on the Malta Box's own printed list.
OFF_SCALE: frozenset[str] = frozenset({"M"})
_OFF_SCALE_Q = max(s.gMR + s.hOff for k, s in SECTIONS.items() if k not in OFF_SCALE) + 1

# THE A/B AND D/E SEAM CORRECTION -- adjacency space only; to_pixel is untouched and was never
# wrong. Found tracing hexsides (Phase 8.1b): C/D's raw grids already agree at their shared
# boundary column (21 hexes decode to the SAME (nx, ny) under the plain formula above, with no
# help from anything below), but A/B and D/E do not -- the SAME physical hex gets a raw index one
# column (A/B, nx) or one row (D/E, ny) apart, so the two labels' to_pixel outputs sit 2-4 px apart
# (the same hex, redrawn twice at the section join) yet to_axial gave them ADJACENT-but-DIFFERENT
# axials. That is worse than a cosmetic duplicate: to_axial (unlike to_pixel) also DEFINES
# adjacency via AXIAL_DIRS, so every hex on the wrong side of that 1-unit gap silently loses its
# cross-seam neighbours -- confirmed by hand and by the min-vertex-cut probe this slice runs, which
# found the WHOLE El Alamein sector split into two disconnected halves at exactly this line before
# this fix, not just a few duplicate hexes.
#
# THE CORRECTION IS APPLIED IN AXIAL SPACE, AFTER the odd-q offset->axial conversion below, NOT
# to the raw (nx, ny) offset grid beforehand. That distinction is load-bearing, not cosmetic: an
# odd-q offset grid's row term `ny - (nx - (nx & 1)) // 2` is PARITY-sensitive (an even column and
# an odd column stagger differently), so nudging the raw nx by an odd amount before that formula
# runs flips every hex's column parity and silently distorts EVERY neighbour relationship inside
# the shifted section -- caught by test_pixel_lattice_consistency, which found a purely-internal
# Map B neighbour pair sitting 147 px apart (one hex pitch is ~85 px) under a first draft of this
# fix that shifted nx before conversion. A constant added to the AXIAL (q, r) pair has no such
# problem: axial neighbours are six fixed unit vectors (AXIAL_DIRS) with no parity dependence at
# all, so translating a whole section's axial space by one constant vector preserves every
# relative adjacency inside it exactly, and only moves the section as a whole to align with its
# neighbour -- the same principle 44.11's Malta shift already relies on, just added rather than
# folded into nx.
#
# MEASURED, not chosen: for every one of the 28 A/B and 21 D/E hex pairs whose to_pixel outputs
# coincide (<10 px apart, mutual nearest neighbour -- the same test that finds C/D's 21), the delta
# between B's (or E's) NATIVE axial (the plain formula below, no correction) and its A-side (or
# D-side) twin's is the SAME constant: (-1, 0) for B relative to A, (0, -1) for E relative to D.
#
# THE CORRECTION CASCADES, because A's error propagates down the chain: B/C and C/D each ALREADY
# agree natively (0 relative shift -- confirmed the same way, by cross-section neighbour count, not
# assumed), so whatever correction re-aligns B with A must carry unchanged through C and D to keep
# THOSE joins aligned too, and E then adds its own (0, -1) on top of D's inherited correction. A
# first draft that gave B alone (-1, 0) and left C/D/E at (0, 0) passed every A/B check but broke
# the B/C join instead (test_cross_section_adjacency_is_seamless), which is how the cascade was
# caught -- fixing one seam by shifting only the section on one side of it silently un-fixes its
# OTHER seam if that section was already correctly aligned with its other neighbour.
#
# Round-trip (to_axial then from_axial) is exact over all 8,505 transcribed hexes with this
# correction in place, every interior neighbour pair stays on the true ~85 px pixel lattice
# (test_pixel_lattice_consistency), and all four section joins (A/B, B/C, C/D, D/E) now show
# genuine cross-section axial adjacency, not just the two that used to accidentally work.
_SEAM_SHIFT: dict[str, tuple[int, int]] = {
    "B": (-1, 0),
    "C": (-1, 0),
    "D": (-1, 0),
    "E": (-1, -1),
}


@dataclass(frozen=True, slots=True)
class Hex:
    section: str
    xx: int
    yy: int

    @property
    def label(self) -> str:
        return f"{self.section}{self.xx:02d}{self.yy:02d}"


def parse(label: str) -> Hex:
    label = label.strip()
    return Hex(label[0].upper(), int(label[1:3]), int(label[3:5]))


# --- label <-> raw VASSAL grid index (nx, ny), board-global ------------------

def to_raw(h: Hex) -> tuple[int, int]:
    s = SECTIONS[h.section]
    nx = s.gMR + s.hOff - h.xx
    ny = h.yy - s.vOff - (1 if s.stagger and (nx & 1) else 0)
    return nx, ny


def from_raw(section: str, nx: int, ny: int) -> Hex:
    s = SECTIONS[section]
    xx = s.gMR + s.hOff - nx
    yy = ny + s.vOff + (1 if s.stagger and (nx & 1) else 0)
    return Hex(section, xx, yy)


# --- global axial (odd-q on the raw grid) -----------------------------------

def to_axial(h: Hex) -> tuple[int, int]:
    nx, ny = to_raw(h)
    q = nx + (_OFF_SCALE_Q if h.section in OFF_SCALE else 0)   # 44.11: the off-scale box, disjoint
    r = ny - (nx - (nx & 1)) // 2
    dq, dr = _SEAM_SHIFT.get(h.section, (0, 0))                # A/B, D/E seam correction, see above
    return q + dq, r + dr


def from_axial(section: str, q: int, r: int) -> Hex:
    dq, dr = _SEAM_SHIFT.get(section, (0, 0))
    q, r = q - dq, r - dr
    nx = q - (_OFF_SCALE_Q if section in OFF_SCALE else 0)
    ny = r + (nx - (nx & 1)) // 2
    return from_raw(section, nx, ny)


def neighbours(h: Hex) -> list[Hex]:
    """The 6 neighbours as labels in h's own section. Cross-section adjacency is
    carried by the global axial (to_axial), which the engine uses directly."""
    q, r = to_axial(h)
    return [from_axial(h.section, q + dq, r + dr) for dq, dr in AXIAL_DIRS]


def distance(a: Hex, b: Hex) -> int:
    aq, ar = to_axial(a)
    bq, br = to_axial(b)
    return (abs(aq - bq) + abs(aq + ar - bq - br) + abs(ar - br)) // 2


# --- board-image pixel of a hex centre (exact; for terrain sampling) ---------

def to_pixel(h: Hex) -> tuple[float, float]:
    s = SECTIONS[h.section]
    nx, ny = to_raw(h)
    px = s.dy * ny + (s.dy / 2 if nx & 1 else 0) + s.y0
    py = s.dx * nx + s.x0
    return px, py


def from_pixel(px: float, py: float) -> Hex | None:
    """Inverse of to_pixel: the hex whose centre is nearest a board-image pixel.
    Picks the section whose bbox contains the point and whose hex centre is
    closest (sections abut, so a seam pixel can fall in two bboxes). Returns None
    if the point is off every map section."""
    best: tuple[float, Hex] | None = None
    for s in SECTIONS.values():
        bx0, by0, bx1, by1 = s.bbox
        if not (bx0 <= px <= bx1 and by0 <= py <= by1):
            continue
        nx = round((py - s.x0) / s.dx)
        ny = round((px - s.y0 - (s.dy / 2 if nx & 1 else 0)) / s.dy)
        h = from_raw(s.letter, nx, ny)
        cx, cy = to_pixel(h)
        d = (cx - px) ** 2 + (cy - py) ** 2
        if best is None or d < best[0]:
            best = (d, h)
    return best[1] if best else None
