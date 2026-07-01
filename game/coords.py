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
axial is q = nx, r = ny - (nx - (nx & 1)) // 2. Neighbours and distances follow
exactly and are pixel-independent. See memory: vassal-coordinate-formula.
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
    gMR: int          # getMaxRows for this zone


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
        )
    return out


SECTIONS: dict[str, Section] = _load_sections()


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
    return nx, ny - (nx - (nx & 1)) // 2


def from_axial(section: str, q: int, r: int) -> Hex:
    nx = q
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
