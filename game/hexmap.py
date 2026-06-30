"""Hex geometry (axial / cube coordinates).

Pure geometry only — no terrain, no costs (those live in terrain.py / movement.py).
Internal coordinates are axial (q, r); cube is (q, r, -q-r). This is unambiguous
and fully testable. The rulebook's "C4218"-style (section, col, row) labels are
opaque identifiers we attach to hexes when the real map is transcribed; the
offset<->axial conversion is deferred until we can pin the map's offset
convention against the physical board (do not guess it here).
"""
from __future__ import annotations

Coord = tuple[int, int]  # axial (q, r)

# The six axial directions, in clockwise order from "east".
AXIAL_DIRECTIONS: tuple[Coord, ...] = (
    (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1),
)


def neighbors(coord: Coord) -> tuple[Coord, ...]:
    q, r = coord
    return tuple((q + dq, r + dr) for dq, dr in AXIAL_DIRECTIONS)


def is_adjacent(a: Coord, b: Coord) -> bool:
    return distance(a, b) == 1


def distance(a: Coord, b: Coord) -> int:
    """Hex distance via the cube metric."""
    aq, ar = a
    bq, br = b
    dq, dr = aq - bq, ar - br
    return (abs(dq) + abs(dq + dr) + abs(dr)) // 2


def line(a: Coord, b: Coord) -> tuple[Coord, ...]:
    """A contiguous straight-ish path of coords from a to b (inclusive),
    using cube linear interpolation with rounding — handy for tests/tools."""
    n = distance(a, b)
    if n == 0:
        return (a,)
    return tuple(_cube_round(_lerp(a, b, i / n)) for i in range(n + 1))


def _lerp(a: Coord, b: Coord, t: float) -> tuple[float, float, float]:
    aq, ar = a
    bq, br = b
    ax, az, ay = aq, ar, -aq - ar
    bx, bz, by = bq, br, -bq - br
    return (ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t)


def _cube_round(frac: tuple[float, float, float]) -> Coord:
    x, y, z = frac
    rx, ry, rz = round(x), round(y), round(z)
    dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return (int(rx), int(rz))  # back to axial (q, r)
