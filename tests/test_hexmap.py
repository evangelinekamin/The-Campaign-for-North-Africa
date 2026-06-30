"""Golden tests for hex geometry (axial/cube)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import hexmap


def test_six_neighbors_all_distance_one():
    nbs = hexmap.neighbors((0, 0))
    assert len(nbs) == 6
    assert len(set(nbs)) == 6
    assert all(hexmap.distance((0, 0), nb) == 1 for nb in nbs)


def test_distance_is_symmetric_and_known():
    assert hexmap.distance((0, 0), (0, 0)) == 0
    assert hexmap.distance((0, 0), (3, 0)) == 3
    assert hexmap.distance((0, 0), (-2, 1)) == hexmap.distance((-2, 1), (0, 0))
    # a "knight-ish" hop: (2,-1) is distance 2 from origin
    assert hexmap.distance((0, 0), (2, -1)) == 2


def test_adjacency():
    assert hexmap.is_adjacent((0, 0), (1, 0))
    assert not hexmap.is_adjacent((0, 0), (2, 0))


def test_line_is_contiguous_and_spans_endpoints():
    ln = hexmap.line((0, 0), (3, 0))
    assert ln[0] == (0, 0) and ln[-1] == (3, 0)
    assert len(ln) == 4
    assert all(hexmap.is_adjacent(a, b) for a, b in zip(ln, ln[1:]))
