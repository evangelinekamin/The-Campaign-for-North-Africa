"""C1-2: the campaign victory geography (rule 64.7). Guards data/victory_cities.json
against transcription rot -- every hex must be a well-formed label that decodes as land
on the full A-E campaign map, and the Victory-Point table must match rule 64.73.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import cna_map, coords

_DATA = Path(__file__).resolve().parent.parent / "data" / "victory_cities.json"
CITIES = json.loads(_DATA.read_text())

# The rule-64.73 Geographic Occupation Point totals (a transcription checksum).
_AXIS_VP_TOTAL = 620
_CWLTH_VP_TOTAL = 370


def _index():
    _, index = cna_map.load_sections("ABCDE")
    return index


def _all_hexes() -> list[str]:
    hexes = [c["hex"] for c in CITIES["cities"]]
    hexes += CITIES["auto_win"]["alexandria"] + CITIES["auto_win"]["cairo"]
    hexes.append(CITIES["supply_sources"]["tobruk"])
    return hexes


def test_every_victory_hex_decodes_as_land():
    index = _index()
    for lbl in _all_hexes():
        assert coords.parse(lbl).label == lbl, f"{lbl} malformed"
        assert lbl in index, f"{lbl} did not decode as land on the A-E map"


def test_all_ten_vp_cities_present():
    names = {c["name"] for c in CITIES["cities"]}
    assert names == {
        "Mersa Matruh", "Sidi Barrani", "Siwa", "Jalo", "Giarabub",
        "Bardia", "Sollum", "Tobruk", "Derna", "Benghazi",
    }


def test_vp_table_matches_rule_64_73():
    assert sum(c["axis_vp"] for c in CITIES["cities"]) == _AXIS_VP_TOTAL
    assert sum(c["cwlth_vp"] for c in CITIES["cities"]) == _CWLTH_VP_TOTAL
    # Tobruk is the crown objective at 200/100.
    tobruk = next(c for c in CITIES["cities"] if c["name"] == "Tobruk")
    assert (tobruk["axis_vp"], tobruk["cwlth_vp"]) == (200, 100)


def test_alexandria_and_cairo_hex_sets():
    # Rule 64.71 auto-win requires occupying ALL hexes of both cities.
    assert CITIES["auto_win"]["alexandria"] == ["E3613", "E3714"]
    assert len(CITIES["auto_win"]["cairo"]) == 5


def test_tripoli_is_off_map():
    # Rule 22.31 / 8.88: the Tripoli Box is an off-map supply source, not a map hex.
    assert CITIES["supply_sources"]["tripoli"] is None
    assert CITIES["supply_sources"]["tobruk"] == "C4807"
