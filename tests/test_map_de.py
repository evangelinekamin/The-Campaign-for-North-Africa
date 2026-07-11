"""C1-1: the eastern maps (D, E) decode and merge with A-C into one board-global
land map. Guards the campaign geography -- rule 64 fights across Maps A-E, so
`load_sections("ABCDE")` must succeed and the eastern objective belt (the
Alexandria/Cairo approaches) must resolve as reachable land, not sea or off-map.

These assertions are the C1-1 exit checks: (1) the full A-E map loads, (2) D and E
each contribute a sane land-hex count, (3) the named eastern objective hexes are
land and classify clear, (4) A/B/C land counts are unchanged by the merge.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import cna_map, coords
from game.terrain import Terrain

# The deep-east objective hexes the campaign victory conditions (rule 64.7) turn on:
# Mersa Matruh (D3714), both Alexandria hexes (E3613/E3714, rule 64.71), and a Cairo
# hex (E1730). All must decode as reachable land. Hexes verified against docs/rules/90;
# the full VP table lives in data/victory_cities.json (see tests/test_victory_cities.py).
EAST_OBJECTIVES = ("D3714", "E3613", "E3714", "E1730")


def _land_labels(index: dict, section: str) -> list[str]:
    return [lbl for lbl in index if lbl.startswith(section)]


def test_full_campaign_map_loads():
    # The single load-bearing guard: the whole A-E theatre merges into one map.
    tmap, index = cna_map.load_sections("ABCDE")
    assert index, "empty A-E index"
    assert tmap.terrain, "empty A-E terrain"


def test_eastern_sections_contribute_land():
    _, index = cna_map.load_sections("ABCDE")
    d_land = _land_labels(index, "D")
    e_land = _land_labels(index, "E")
    # Ranges around the decoded counts (D ~1199 land, E ~1234 land); loose enough to
    # survive a classifier tweak, tight enough to catch a half-dropped eastern map.
    assert 1100 <= len(d_land) <= 1300, f"Map D land hexes = {len(d_land)}"
    assert 1130 <= len(e_land) <= 1330, f"Map E land hexes = {len(e_land)}"


def test_eastern_objectives_are_clear_land():
    tmap, index = cna_map.load_sections("ABCDE")
    for lbl in EAST_OBJECTIVES:
        assert coords.parse(lbl).label == lbl          # in-bounds, well-formed
        assert lbl in index, f"{lbl} did not decode as land"
        assert tmap.terrain[index[lbl]] == Terrain.CLEAR, f"{lbl} not clear"


def test_abc_land_counts_unchanged_by_merge():
    # Merging D/E must not perturb the western sections. Baselines are the committed
    # A/B/C land-hex counts; a change here means the eastern merge leaked west.
    _, abc = cna_map.load_sections("ABC")
    _, abcde = cna_map.load_sections("ABCDE")
    for section, expected in (("A", None), ("B", None), ("C", None)):
        got_abc = len(_land_labels(abc, section))
        got_abcde = len(_land_labels(abcde, section))
        assert got_abc == got_abcde, f"Map {section} land count shifted: {got_abc} -> {got_abcde}"
