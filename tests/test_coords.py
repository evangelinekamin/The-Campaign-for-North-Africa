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


def test_axial_roundtrip_holds_through_the_ab_de_seam_correction():
    # game.coords._SEAM_SHIFT (Phase 8.1b) nudges B's and E's raw indices before computing the
    # axial; the round trip must still be exact for the two corrected sections, not just C.
    for section in ("A", "B", "D", "E"):
        for xx in range(1, 55):
            for yy in range(1, 35):
                h = Hex(section, xx, yy)
                assert coords.from_axial(section, *coords.to_axial(h)) == h


def test_ab_and_de_seam_hexes_coincide():
    # [8.1b] The A/B and D/E section joins redraw the SAME physical hex under each section's own
    # raw numbering (confirmed by pixel proximity: their to_pixel outputs sit 2-4 px apart) --
    # unlike C/D, which already coincides under the plain formula, A/B and D/E used to decode to
    # two DIFFERENT board-global axials one column/row apart. They must now agree, exactly like
    # C/D's existing 21 (tests/test_map_de.py / test_map_terrain_fills.py's "THE SEAM" gate).
    ab_pairs = [("A0233", "B0200"), ("A0433", "B0400"), ("A1033", "B1000")]
    de_pairs = [("D0233", "E0200"), ("D0433", "E0400"), ("D1033", "E1000")]
    for a, b in ab_pairs + de_pairs:
        assert coords.to_axial(parse(a)) == coords.to_axial(parse(b)), f"{a} != {b}"
    # and C/D, untouched by this correction, still agrees too
    assert coords.to_axial(parse("C0233")) == coords.to_axial(parse("D0200"))


def test_ab_and_de_seam_neighbours_are_not_phantoms():
    # The bug this closes: before the correction, a hex just west of the A/B or D/E join lost its
    # TRUE cross-seam neighbour (the axial arithmetic landed one column short/long), which silently
    # disconnected the map along the whole seam, not just at the 49 duplicate hexes themselves
    # (confirmed against the real, transcribed board: a min-vertex-cut probe across the Alamein
    # sector found the WHOLE region split into two disconnected halves at this exact line before
    # this fix). Checked by AXIAL distance, matching test_cross_section_adjacency_is_seamless's own
    # method -- coords.neighbours(h) always relabels its 6 results in h's OWN section (by design,
    # per its docstring), so it can never literally return a far-section label even when correct.
    a133, b200 = parse("A0133"), parse("B0200")
    assert coords.distance(a133, b200) == 1
    d133, e200 = parse("D0133"), parse("E0200")
    assert coords.distance(d133, e200) == 1


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


def test_from_pixel_inverts_to_pixel():
    for lbl in ("C4507", "A1816", "A5633", "B4827", "D3716", "E3613"):
        h = parse(lbl)
        assert coords.from_pixel(*coords.to_pixel(h)) == h
    # a piece nudged off-centre (< half a hex) still snaps to the right hex
    px, py = coords.to_pixel(parse("C4507"))
    assert coords.from_pixel(px + 25, py - 20) == parse("C4507")
    # a point off every map section is None
    assert coords.from_pixel(10, 10) is None


def test_map_c_pixels_match_detected_town_dots():
    # The exact formula must land on real Map C town-dot pixels (dots sit a little
    # off-centre, so allow the ~35px dot-offset floor). Guards the whole chain.
    known = {"C4507": (6267, 1299), "C4414": (6876, 1362), "C4108": (6320, 1595)}
    for lbl, (px, py) in known.items():
        x, y = coords.to_pixel(parse(lbl))
        assert math.hypot(x - px, y - py) <= 35, f"{lbl} off by too much"
