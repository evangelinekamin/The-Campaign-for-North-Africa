"""C2-0: the September-1940 campaign Order of Battle, extracted from the VASSAL
'setup italian.vsav' by tools/vassal/extract_oob.py. Guards data/oob_italian.json --
the two-sided Italian-offensive force the full campaign opens with -- against extraction
rot, and confirms it is a genuinely different (and larger) force than the Feb-1941
Desert-Fox slice.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import oob

_DATA = Path(__file__).resolve().parent.parent / "data" / "oob_italian.json"
OOB = json.loads(_DATA.read_text())
UNITS = [r for r in OOB if r.get("kind") == "unit"]


def test_two_sided_force_across_the_theatre():
    by_side = Counter(r["side"] for r in UNITS)
    assert by_side["AXIS"] >= 55, by_side          # the Italian 10th Army
    assert by_side["ALLIED"] >= 25, by_side         # the Western Desert Force
    sections = {r["hex"][0] for r in UNITS if r.get("hex")}
    assert sections >= set("ABCDE"), sections       # deployed across all five maps


def test_italian_tenth_army_formations_present():
    groups = " | ".join(r.get("group", "") for r in UNITS)
    for formation in ("Maletti", "Libyan", "Catanzaro", "CCNN", "Tobruk Garrison"):
        assert formation in groups, f"missing {formation}"


def test_build_consumes_it_without_reinforcements():
    # The campaign start alone (no Desert-Fox reinforcements bleeding in): every unit is
    # a live combat piece the engine can place.
    units, dumps = oob.build(oob_file="oob_italian.json", sections="ABCDE",
                             reinforcements_file=None)
    assert len(units) >= 80
    assert all(u.strength >= 1 for u in units)
    assert {u.side.value for u in units} == {"AXIS", "ALLIED"}


def test_is_a_distinct_larger_force_than_desert_fox():
    df = json.loads((_DATA.parent / "oob_desert_fox.json").read_text())
    df_units = [r for r in df if r.get("kind") == "unit"]
    assert len(UNITS) > len(df_units)               # 100 vs 28 on-map: a whole army, not a slice
