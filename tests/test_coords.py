"""Tests for the CNA hex-label coordinate system (game.coords)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords
from game.coords import Hex, parse


def test_label_roundtrip():
    for lbl in ("C4807", "A1816", "B4827", "C4021", "D3714"):
        assert parse(lbl).label == lbl


def test_axial_roundtrip():
    for xx in range(1, 60):
        for yy in range(1, 40):
            h = Hex("C", xx, yy)
            assert coords.from_axial("C", *coords.to_axial(h)) == h


def test_six_neighbours_all_distance_one():
    h = parse("C4020")
    nbs = coords.neighbours(h)
    assert len(nbs) == 6 and len(set(n.label for n in nbs)) == 6
    assert all(coords.distance(h, n) == 1 for n in nbs)


def test_neighbour_symmetry():
    for xx in range(30, 50):
        for yy in range(5, 35):
            h = Hex("C", xx, yy)
            for n in coords.neighbours(h):
                assert h.label in {m.label for m in coords.neighbours(n)}


def test_known_town_distances():
    # calibrated against the map (Map C)
    assert coords.distance(parse("C4507"), parse("C4807")) == 3   # El Adem -> Tobruk
    assert coords.distance(parse("C4021"), parse("C4020")) == 1   # Sollum -> Ft Capuzzo
    # Ft Capuzzo is an actual neighbour of Sollum
    assert "C4020" in {n.label for n in coords.neighbours(parse("C4021"))}


def test_pixel_lattice_consistency():
    # Every neighbour must be ~one hex-spacing away on the map image. This
    # cross-validates the odd-q convention against the exact VASSAL pixel formula,
    # across several sections (not just Map C).
    for lbl in ("C4507", "C4414", "C4218", "B4827", "B4004", "A2021", "A2629"):
        h = parse(lbl)
        hx, hy = coords.to_pixel(h)
        for n in coords.neighbours(h):
            nx, ny = coords.to_pixel(n)
            d = math.hypot(nx - hx, ny - hy)
            assert 80 <= d <= 91, f"{h.label}->{n.label} spacing {d:.1f}px off-lattice"


def test_cross_section_adjacency_is_seamless():
    # The raw grid is board-global, so a Map B hex on the B/C seam and the Map C
    # hex one column east of it are axial-distance 1 despite being in different
    # sections (verified geometrically: same raw nx, consecutive raw ny ~ one hex).
    b_edge = coords.from_raw("B", 30, 66)
    c_edge = coords.from_raw("C", 30, 67)
    assert coords.distance(b_edge, c_edge) == 1
    bx, by = coords.to_pixel(b_edge)
    cx, cy = coords.to_pixel(c_edge)
    assert 80 <= math.hypot(cx - bx, cy - by) <= 91


def test_map_c_pixels_match_detected_town_dots():
    # The exact formula must land on real Map C town-dot pixels (dots sit a little
    # off-centre, so allow the ~35px dot-offset floor). Guards the whole chain.
    known = {"C4507": (6267, 1299), "C4414": (6876, 1362), "C4108": (6320, 1595)}
    for lbl, (px, py) in known.items():
        x, y = coords.to_pixel(parse(lbl))
        assert math.hypot(x - px, y - py) <= 35, f"{lbl} off by too much"
