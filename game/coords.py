"""CNA hex-label coordinate system (rulebook labels <-> axial <-> neighbours).

A rulebook hex is "S####" — a section letter (A-E, or M=Malta) plus a 4-digit
XXYY label (e.g. "C4807" = section C, column 48, row 07). The geometry was
calibrated from the VASSAL map (see data/cna_map_calibration.json): flat-top
hexes with XX as the (roughly N-S) staggering column axis, even-q offset. That
makes neighbours and distances EXACT and pixel-independent — which is all the
game engine needs. Pixel mapping (for terrain sampling off the map image) is a
separate, per-section calibration and only Map C is pinned so far.

Cross-section adjacency (a hex on one section's seam touching the next section)
is NOT handled here — sections have independent XX/YY numbering. For a bounded
sub-region the few seam links are supplied as explicit map data.
"""
from __future__ import annotations

from dataclasses import dataclass

AXIAL_DIRS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))


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


def to_axial(h: Hex) -> tuple[int, int]:
    """Even-q offset -> axial (col = XX is the staggering axis)."""
    q = h.xx
    r = h.yy - (h.xx + (h.xx & 1)) // 2
    return q, r


def from_axial(section: str, q: int, r: int) -> Hex:
    xx = q
    yy = r + (xx + (xx & 1)) // 2
    return Hex(section, xx, yy)


def neighbours(h: Hex) -> list[Hex]:
    """The 6 same-section neighbours. Callers filter to hexes that exist in the
    scenario map; cross-section seams are added as explicit data."""
    q, r = to_axial(h)
    return [from_axial(h.section, q + dq, r + dr) for dq, dr in AXIAL_DIRS]


def distance(a: Hex, b: Hex) -> int:
    """Hex distance (only meaningful within one section here)."""
    aq, ar = to_axial(a)
    bq, br = to_axial(b)
    return (abs(aq - bq) + abs(aq + ar - bq - br) + abs(ar - br)) // 2


# --- Map C pixel mapping (provisional, ~30px; data/cna_map_calibration.json) ---
_MAPC_PX = (5824.30, 39.34, 84.34)   # px = c0 + c1*q + c2*r
_MAPC_PY = (4669.75, -76.16, -3.99)  # py = c0 + c1*q + c2*r


def to_pixel_mapc(h: Hex) -> tuple[float, float]:
    """Approximate map-image pixel of a Map C hex centre (for terrain sampling).
    Provisional until dot detection is refined to <10px."""
    if h.section != "C":
        raise ValueError("only Map C is pixel-calibrated so far")
    q, r = to_axial(h)
    px = _MAPC_PX[0] + _MAPC_PX[1] * q + _MAPC_PX[2] * r
    py = _MAPC_PY[0] + _MAPC_PY[1] * q + _MAPC_PY[2] * r
    return px, py
