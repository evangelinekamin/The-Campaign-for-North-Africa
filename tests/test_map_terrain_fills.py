"""THE MAP DATA ITSELF (Phase 8.1a, the [8.37] terrain fills) -- the pins nothing else holds.

data/terrain_<section>.json is not a chart transcription anyone can re-read line by line; it is
8,505 hexes of classifier output, and until these tests existed the ONLY thing standing behind it
was two determinism signatures that this project's own rules (port rule 4) say may be re-baselined.
Re-running tools/vassal/extract_terrain.py with a different sample or threshold would have moved a
thousand hexes with a green suite.

So these are the verification gates scratchpad/port/terrain-key.md Sec 4d specified, asserted:

  1. THE COASTLINE (hard gate). sea == 1,750 hexes. The sea test in the extractor is deliberately
     fuzzy and must stay verbatim -- exact-matching it moves 27 hexes across the land/sea line,
     which changes which hexes EXIST and interacts with KNOWN_TERRAIN, _RULEBOOK_LAND and the
     coastal-road promotion. Any drift here means someone touched it.
  2. THE ANCHOR. The Qattara Depression is one 69-hex connected salt_marsh body with NO sea in its
     6-neighbourhood, plus a 25-hex southern lobe -- the geography that makes El Alamein a LINE.
  3. THE CORRIDOR. Measured on the real hex graph: the Mediterranean coast narrows to 9 hexes from
     the marsh body just west of El Alamein, 11 at El Alamein itself, 26 back at Alexandria. If
     these move, the grid or the classifier moved.
  4. WADI NATRUN, a free positive control: an 8-hex salt_marsh component the raster LABELS.
  5. THE CLASS CENSUS, per class and per section -- gravel 448 in particular (see
     test_gravel_is_the_disc_count, the review finding this file was written for).
  6. THE SEAM. 21 axials carry two section labels; all 21 must agree, or load_sections' last-write-
     wins merge becomes order-dependent.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import cna_map, coords, movement                               # noqa: E402
from game.hexmap import neighbors                                        # noqa: E402
from game.terrain import Mobility, Terrain                               # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
SECTIONS = "ABCDE"


def _raw() -> dict:
    """Every section's raw extractor output, label -> class string (no merge, no overrides)."""
    out: dict[str, dict] = {}
    for s in SECTIONS:
        out[s] = json.loads((DATA / f"terrain_{s}.json").read_text())
    return out


def _by_axial() -> dict:
    """label-class merged onto board-global axials, the way cna_map merges the sections."""
    merged = {}
    for section in _raw().values():
        for label, klass in section.items():
            merged[coords.to_axial(coords.parse(label))] = klass
    return merged


def _component(hexes: set, seed) -> set:
    """The connected component of `seed` within `hexes`, over real hex adjacency."""
    seen, frontier = {seed}, deque([seed])
    while frontier:
        here = frontier.popleft()
        for nb in neighbors(here):
            if nb in hexes and nb not in seen:
                seen.add(nb)
                frontier.append(nb)
    return seen


def _components(hexes: set) -> list[set]:
    out, unseen = [], set(hexes)
    while unseen:
        comp = _component(hexes, next(iter(unseen)))
        out.append(comp)
        unseen -= comp
    return sorted(out, key=len, reverse=True)


def test_the_coastline_is_exactly_1750_sea_hexes():
    """GATE 1. The land/sea line is the one thing in this dataset that decides which hexes EXIST."""
    tally = Counter(k for sec in _raw().values() for k in sec.values())
    assert tally["sea"] == 1750, f"the coastline moved: sea = {tally['sea']}"
    assert sum(tally.values()) == 8505
    assert sum(v for k, v in tally.items() if k != "sea") == 6755


def test_the_class_census_matches_the_transcribed_map():
    """GATE 5. Every [8.37] fill class, board-wide. These are counts read off the arbiter
    (scratchpad/port/terrain-key.md Sec 4c), not preferences -- a change here is a claim that the
    map is painted differently than it is, and must be argued against the raster."""
    tally = Counter(k for sec in _raw().values() for k in sec.values())
    assert tally == Counter({
        "clear": 4245, "sea": 1750, "desert": 686, "rough": 649, "gravel": 448,
        "delta": 325, "salt_marsh": 270, "mountain": 109, "swamp": 17, "vegetation": 6,
    })


def test_gravel_is_the_disc_count_not_the_centre_patch_count():
    """448, NOT 394. The Rock/Gravel class has no fill colour at all -- only a sparse pebble-ring
    stipple -- so the sample AREA is the measurement, and the original 48x48 centre patch (37% of a
    hex) cut straight through a populated band of the histogram and lost 54 hexes to CLEAR. Over the
    inscribed disc the histogram is decisively bimodal (nothing whatever between 5 and 20 ring px),
    and every threshold in that gap returns the same 448. Rendered and read by eye: A1618-A1622 are
    five adjacent hexes under one unbroken stipple that the patch called gravel/clear/clear/clear/
    clear. Consequence of the miss: Breakdown Value 4 where the chart says 6."""
    raw = _raw()
    gravel = {s: sum(1 for v in raw[s].values() if v == "gravel") for s in SECTIONS}
    assert gravel == {"A": 231, "B": 180, "C": 3, "D": 31, "E": 3}
    for label in ("A1618", "A1619", "A1620", "A1621", "A1622", "A1524", "A1309", "B4421"):
        assert raw[label[0]][label] == "gravel", f"{label} is under the pebble stipple"


def test_the_qattara_depression_is_one_69_hex_body_with_no_sea_neighbour():
    """GATE 2, THE ANCHOR. The Depression is a closed inland salt pan: if any part of it touched
    the sea the classifier would have merged a coastal sebkha into it, and the barrier that makes
    the Alamein position a line instead of an open flank would be a different shape."""
    ax = _by_axial()
    marsh = {h for h, k in ax.items() if k == "salt_marsh"}
    sea = {h for h, k in ax.items() if k == "sea"}
    comps = _components(marsh)
    body = comps[0]
    assert len(body) == 69, f"the Qattara body is {len(body)} hexes"
    assert not any(nb in sea for h in body for nb in neighbors(h)), "the Depression touches the sea"
    assert coords.to_axial(coords.parse("D1316")) in body
    assert coords.to_axial(coords.parse("D2229")) in body
    # The southern lobe is 25 hexes and sits immediately south of the body. (The board's OTHER
    # 26-hex salt_marsh component is an unrelated sebkha ~7,000 px away in southern Libya, B1502
    # onward -- it is NOT the Qattara lobe, and the two must not be confused in the record.)
    lobe = _component(marsh, coords.to_axial(coords.parse("D0714")))
    assert len(lobe) == 25, f"the Qattara southern lobe is {len(lobe)} hexes"
    libya = _component(marsh, coords.to_axial(coords.parse("B1502")))
    assert len(libya) == 26 and not (libya & body) and not (libya & lobe)


def test_wadi_natrun_is_the_labelled_8_hex_control():
    """GATE 4. [8.41]: "the Wadi Natrun, just west of the Nile Delta, which is treated, for
    game-purposes, as if it were Salt Marsh" -- the raster labels it, so it is a free positive
    control on the salt-marsh colour binding."""
    ax = _by_axial()
    marsh = {h for h, k in ax.items() if k == "salt_marsh"}
    natrun = _component(marsh, coords.to_axial(coords.parse("E2218")))
    assert len(natrun) == 8


def test_the_alamein_corridor_is_nine_to_eleven_hexes():
    """GATE 3, THE POINT OF THE SLICE. Distance ON THE HEX GRAPH from the Mediterranean shore to
    the Qattara body: 9 at its narrowest (D3133), 11 at El Alamein itself, and 26 back at
    Alexandria -- i.e. the corridor an army must force narrows by two thirds in the 25 hexes
    between the Delta and Alamein, exactly as the historical position does."""
    ax = _by_axial()
    land = {h for h, k in ax.items() if k != "sea"}
    sea = {h for h, k in ax.items() if k == "sea"}
    body = _components({h for h, k in ax.items() if k == "salt_marsh"})[0]

    dist = {h: 0 for h in body}
    frontier = deque(body)
    while frontier:
        here = frontier.popleft()
        for nb in neighbors(here):
            if nb in land and nb not in dist:
                dist[nb] = dist[here] + 1
                frontier.append(nb)

    def at(label: str) -> int:
        return dist[coords.to_axial(coords.parse(label))]

    assert at("D3133") == 9                          # the narrowest coastal hex on the whole front
    assert at("D3231") == at("D3232") == 10
    assert at("E3001") == at("E3101") == 10
    assert at("E3002") == 11                         # El Alamein
    assert at("E3714") == 26                         # Alexandria, the open end of the funnel
    # ...and D3133 really is on the shore, not an inland hex that happens to be close.
    assert any(nb in sea for nb in neighbors(coords.to_axial(coords.parse("D3133"))))


def test_every_section_seam_axial_agrees():
    """GATE 6. Sections overlap by one column, so 21 board-global axials carry two labels. If the
    two disagree, cna_map.load_sections' last-write-wins merge silently becomes order-dependent."""
    seen: dict = {}
    clashes = []
    for section in _raw().values():
        for label, klass in section.items():
            key = coords.to_axial(coords.parse(label))
            if key in seen and seen[key][1] != klass:
                clashes.append((seen[key], (label, klass)))
            seen.setdefault(key, (label, klass))
    duplicates = sum(len(sec) for sec in _raw().values()) - len(seen)
    assert duplicates == 21, f"{duplicates} duplicated axials"
    assert clashes == [], f"section seams disagree: {clashes}"


def test_the_delta_lagoon_swamp_is_seventeen_hexes_and_is_absolutely_shut():
    """The [8.37] Swamp row -- "May enter only on road or railroad" -- lands on 17 hexes of the
    Burullus/Idku lagoon fringe. This test pins BOTH the data and its live consequence, because
    that consequence is a FLAGGED DEBT, not an accident:

    data/roads_E.json carries no road, track or rail edge touching ANY of the 17 (the road layer is
    Phase 8.1b's job), so today the class is an absolute wall -- and the raster plainly draws a road
    running into E4019, ROSETTA, which the book's own SUMMARY OF IMPORTANT LOCATIONS (PDF p.73)
    lists as a Port and data/wells.json:58 carries as a village water source. So one book-named
    place is currently unreachable, and it is unreachable because a dataset is missing, not because
    the terrain is wrong (rendered and read by eye: the hex is painted the Key's swamp, tufts and
    all). Isolating it is faithful -- these ARE the impassable lagoons -- but the port is real debt.

    WHEN 8.1b TRACES THAT ROAD, this test must be restated to assert the corridor exists, not that
    it does not. What must NOT happen is the debt being paid by falsifying E4019's terrain."""
    raw = _raw()
    swamp = {lbl for lbl in raw["E"] if raw["E"][lbl] == "swamp"}
    assert len(swamp) == 17
    assert not any(v == "swamp" for s in "ABCD" for v in raw[s].values())
    assert "E4019" in swamp                                      # Rosetta

    edges = json.loads((DATA / "roads_E.json").read_text())
    for kind in ("roads", "tracks"):
        for a, b in edges[kind]:
            assert a not in swamp and b not in swamp, f"a {kind} edge reaches swamp: {a}-{b}"

    # ...so every one of the 17 is cut off from the board for every mobility class. Asserted on the
    # real engine map, through the real movement chart -- a flood from Alexandria reaches the whole
    # land board except the 17 and the pre-existing offshore islands in section A.
    tmap, index = cna_map.load_sections("ABCDE")
    reached = movement.connected(tmap, [index["E3714"]], Mobility.FOOT)
    for label in swamp:
        assert tmap.terrain[index[label]] == Terrain.SWAMP
        assert index[label] not in reached, f"{label} became reachable -- restate this test"
    stranded = {lbl for lbl, h in index.items() if h not in reached}
    assert stranded - swamp == {                      # islands, unchanged by this slice
        "A4101", "A4102", "A5306", "A5403", "A5404", "A5405", "A5406", "A5407",
        "A5502", "A5503", "A5504", "A5505", "A5506", "A5507",
        "A5601", "A5602", "A5603", "A5604", "A5605"}
