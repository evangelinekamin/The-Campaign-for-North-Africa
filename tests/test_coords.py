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
    # Every neighbour must be ~one hex-spacing (85.25 px) away on the map image.
    # This cross-validates the even-q convention against the fitted pixel lattice.
    for lbl in ("C4507", "C4414", "C4321", "C4020", "C4218"):
        h = parse(lbl)
        hx, hy = coords.to_pixel_mapc(h)
        for n in coords.neighbours(h):
            nx, ny = coords.to_pixel_mapc(n)
            d = math.hypot(nx - hx, ny - hy)
            assert 80 <= d <= 91, f"{h.label}->{n.label} spacing {d:.1f}px off-lattice"
