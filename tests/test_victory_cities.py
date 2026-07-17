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


def test_tripoli_enters_the_map_at_its_rule_8_85_gateway():
    # RESTATED 2026-07-16 when 64.72 landed. This test asserted `tripoli is None` under the heading
    # "the Tripoli Box is an off-map supply source, not a map hex" -- and the premise is TRUE (8.81
    # puts the Tripoli/Tunisia boxes off the western edge of Map A; 8.88 makes them Supply Dumps of
    # unlimited capacity; 22.31 names the Box). But the CONCLUSION did not follow, and the null it
    # pinned was not a reading of the rules -- it was a map defect wearing one.
    #
    # 64.71 and 64.72 both trace to a dump feedable "from Tobruk or TRIPOLI in any way", so Tripoli
    # must be reachable or half of every such trace silently does not exist. The book gives the hex
    # itself -- 8.85: "For a unit to be moved off the game map towards Tripolitania it must start
    # that Operations Stage in hex A2802 ... placed in the Road hex closest to the Tripolitania
    # box." A2802 was `null` here only because data/terrain_A.json colour-samples it as SEA (the
    # Gulf of Sirte coastline is sampled a hex too far inland); game.cna_map._RULEBOOK_LAND now
    # overrides that from 8.85, as this engine already overrides it from the roads data and the OOB.
    #
    # WHAT THE NULL COST, measured on the real campaign board: with Tobruk the only source, the
    # Commonwealth capturing Tobruk took the Axis from 13 fed dumps to 0 and all 177 of its combat
    # units out of the 60-MP trace -- a 64.72 Commonwealth automatic win at Game-Turn 35, off a
    # sampling error, in the exact situation where the historical Axis fought on out of Tripoli for
    # two more years. See tests/test_campaign_victory.py::test_losing_tobruk_does_not_hand_the_
    # commonwealth_the_war, which pins that regression.
    #
    # FLAGGED AS A PROXY, and the off-map premise is why: this engine has no off-map box, so the
    # source is anchored at the ON-MAP GATEWAY the book names for it. A2802 stands for Tripoli.
    assert CITIES["supply_sources"]["tripoli"] == "A2802"
    assert CITIES["supply_sources"]["tobruk"] == "C4807"
