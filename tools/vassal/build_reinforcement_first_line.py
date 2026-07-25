"""Author data/reinforcement_first_line.json -- the [4.43a]/[4.43b] "Attached Trucks"
column of the campaign reinforcement schedule (rule 53.11/59.42/61.170).

BLOCK B, Part 2 (scratchpad/port/ammo-last-mile-spec.md): the intrinsic 50.0 ammo load
(Part 1) affords a reinforcement tank exactly one close assault, and every one of the
39 CW armour counters in the campaign is a rule-20 reinforcement, so without this file
every one of them carries a first-line AMMO buffer of zero (_seed_first_line only seeds
GT1 on-map units). This is the transcription that fixes that: the schedule prints an
"Attached Trucks" figure beside many (not all) arrivals, and 53.11's own legend settles
the division -- "All trucks listed are 1st Line (attached) trucks and MAY BE FREELY
DIVIDED AMONGST THE UNITS unless otherwise indicated" (CW, PDF p.115) / "Trucks must
arrive attached to any unit of their nationality arriving in that Operations Stage"
(Axis, PDF p.146) -- so this is rule TEXT, not a judgement call: an even split
(_share, matching _seed_first_line's own GT1 convention) over the combat-eligible
reinforcement counters arriving that side/nationality/Game-Turn.

SCAN-VERIFIED (port rule 2, OR-4): rendered at 200/400dpi from
tmp/The Campaign for North Africa.pdf pages 114-115 ([4.43a] COMMONWEALTH LAND UNIT
REINFORCEMENT AND WITHDRAWAL SCHEDULE) and 145-146 ([4.43b] AXIS LAND UNIT REINFORCEMENT
SCHEDULE), read directly -- NOT the OCR dump in docs/rules/90-charts-tables-and-play-
aids.md, which garbles several of these exact cells (confirmed by direct comparison,
e.g. its column-bleed at CW GT9/GT30). Renders kept at scratchpad/port/ammo_scan/.

WHAT IS EXCLUDED (faithful, not an oversight):
  - WD (withdrawal) and Rtn (returning) lines. Both mechanics are unimplemented (no
    unit ever leaves the map to return), so a Rtn unit's "Trucks:" figure has no
    live counter to attach to -- the unit is already on the board under its ORIGINAL
    arrival, still there. Attaching a second truck ration on the Rtn date would
    double-count against a withdrawal that never happened.
  - Axis "lone" truck lines with no unit named in the same clause, e.g. "Gm: Trucks:
    40 M (15 Panzer Div)." -- the Axis schedule's OWN legend (PDF p.146) calls these
    out by name: "Certain trucks arrive 'alone' ... historically assigned to the
    German 15th, 90th or 164th Divisions ... The Axis Player may treat these as
    UNATTACHED trucks (2nd-3rd Line)." Not 53.11 first-line stock by the book's own
    ruling, so they are outside this slice's scope entirely (not first-line-truck
    data at all).
  - The Tiger Convoy's "consists of" replacement-point tally (GT32) has no truck
    figure of its own; it shares the GT32 CW pool with 5 SA Bde exactly as printed.

WHAT IS SEEDED BUT LANDS NOWHERE (documented, not invented around): MEASURED against
the built reinforcement roster (data/reinforcements_campaign.json), exactly two of the
65 buckets below have no combat-eligible recipient: Axis-GE GT44 (20 TP) names ONLY
"HQ 90 Light Div" -- is_combat=False, the same rule _seed_first_line's GT1 muster
already excludes HQs under -- and Axis-IT GT99 (15 TP) names "57 Brs Bn [16 Pist]", one
of the minor detached battalions build_campaign_reinforcements.py's own docstring
already flags as out of scope ("standalone flak/artillery batteries, oasis companies
and truck-only lines are deferred"). Those 35 of 3,394 transcribed truck points (1.0%)
are recorded here for the record (the per-side total below is exact against the scan)
but _seed_reinforcement_first_line skips a bucket with no combat-eligible recipient
rather than force an attachment the roster has no unit for -- see
tests/test_first_line.py for the exact accounting.
ONE CASE is a discovered PRE-EXISTING off-by-one, not a new gap: the chart's GT40
"10 In Bde"/"29 In Bde" (5th Indian Division) already sit in
data/reinforcements_campaign_source.json at arrival_gt 39, one Game-Turn earlier than
the scan prints -- out of scope for this slice (it is the existing schedule
transcription, not the truck column), flagged here rather than silently worked around.

    python3 tools/vassal/build_reinforcement_first_line.py

Consumed by game.oob.build(reinforcement_first_line_file="reinforcement_first_line.json"),
called only by game.scenario.campaign (the Desert Fox benchmarks have no [4.43a]/[4.43b]
schedule -- rule 61's own reinforcement chart is a separate, untranscribed source).
"""
from __future__ import annotations

import json
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")
OUT = "reinforcement_first_line.json"

# (nationality, arrival_turn) -> (light, medium, heavy) Truck Points, transcribed cell-by-
# cell off the scan. Multiple truck clauses landing on the same side/nationality/Game-Turn
# (e.g. a German AND an Italian arrival in the same Axis Operations Stage, or two named
# sub-formations in one Commonwealth clause) are summed here -- the schedule's own
# "freely divided amongst the units" licenses treating a Game-Turn's pool as one bucket,
# and _seed_reinforcement_first_line further restricts each bucket to units that actually
# share that (side, nationality, arrival_turn).
#
# CW -- [4.43a], PDF p.114-115.
CW: dict[int, tuple[int, int, int]] = {
    5: (5, 20, 0),          # 7 In Bde [4 In]
    6: (25, 85, 5),         # 6 NZ Bde
    9: (28, 74, 15),        # 19 Aus Bde [6 Aus]
    13: (10, 25, 6),        # 20 Aus Bde [9 Aus]
    14: (12, 30, 10),       # 18 Aus Bde [*]
    15: (4, 72, 13),        # 2nd Armored Div (Trucks (2nd))
    20: (10, 25, 6),        # HQ 9 Aus Div / 26 Aus Bde / 2-3 Aus AT Bn / HQ 22 Guards Bde
    21: (10, 34, 6),        # 24 Aus Bde [9 Aus] / HQ 70 Infantry Div
    23: (10, 25, 0),        # 3rd In Motor Bde
    32: (10, 34, 5),        # HQ 1 SA Div / 5 SA Bde / 1st Imperial Light Horse / 10 NZR RB Bn
    35: (5, 25, 6),         # 14 Infantry Bde [70] (Trucks (14/70))
    36: (18, 84, 11),       # 1st Army Tank Bde (20M,4H) + (1 SA=)10L34M5H + (150=)8L30M2H
    37: (10, 34, 6),        # 1st SA Bde [1 SA]
    38: (30, 97, 22),       # OpS1 Capetown Highlanders.. 20L68M12H + OpS2 9 In Bde 10L25M5H
                            #   + OpS3 (5 In) 0L4M5H
    40: (19, 50, 10),       # 10 In Bde 9L25M5H + 29 In Bde (Trucks (29/5 In)) 10L25M5H --
                            # NOTE: reinforcements_campaign_source.json seats both at
                            # arrival_gt 39, one GT before the scan's "40 1" / "40 3" rows
                            # (pre-existing off-by-one in that file, not this transcription;
                            # flagged above, left untouched -- out of scope for this slice).
    44: (10, 34, 6),        # 4 SA Bde [2 SA]
    51: (5, 30, 6),         # 22nd Armored Bde
    56: (2, 2, 0),          # HQ 1st Armored Div
    58: (10, 30, 6),        # 2nd Armored Bde [1] (Trucks (2/1))
    59: (8, 30, 6),         # 1st Support Group [1]
    62: (10, 15, 3),        # HQ 1 Free French Bde et al.
    65: (2, 15, 0),         # 1st Sherwood Forresters (2L,10M) + 1st Bn d'inf de marine (5M)
    68: (1, 8, 5),          # HQ 50 Infantry Div / 2nd Chesire MG Bn / 74th Fld Arty Regt
    69: (24, 80, 13),       # 69 Inf Bde 8L30M3H + 151 Inf Bde etc 8L30M5H + 8th Armd Bde 8L20M5H
    73: (7, 24, 5),         # 161 In Motor Bde
    75: (5, 14, 2),         # 2nd Free French Bde (Trucks (2 FF))
    80: (8, 30, 5),         # 9 Armored Bde [10] / 3rd Fld Arty Regt
    82: (6, 45, 9),         # 25 In Bde Group 2L15M3H + 20/21 In Bde Group 4L30M6H
    86: (7, 24, 2),         # 18 In Bde (Trucks (18 In))
    87: (8, 36, 8),         # HQ 8 Armored Div / 23 Armored Bde / 2nd Derbyshire Yeomanry
    88: (7, 36, 8),         # 24 Armored Bde [8]
    89: (2, 10, 0),         # 14th Sherwood Forresters
    90: (32, 108, 20),      # 131 Inf Bde 10L35M + 44 Inf Div body 22L73M20H
    92: (27, 102, 19),      # HQ 51 Inf Div etc (Trucks (51))
    93: (8, 28, 6),         # 1st Greek Bde (Trucks (Greek))
    94: (2, 10, 0),         # Yorkshire Dragoons
}

# Axis -- [4.43b], PDF p.145-146. Split GE/IT because the schedule itself does (separate
# "Gm:"/"It:" clauses, often in the same Operations Stage) and _make_unit resolves a
# reinforcement's Unit.nationality to exactly "GE" or "IT" (game.oob._nat).
GE: dict[int, tuple[int, int, int]] = {
    21: (0, 40, 0),         # 3rd Aufklarungs Bn / 39 Panzerjaeger Bn
    22: (10, 0, 10),        # I/5 Panzer Bn / 606 Flak Bn
    24: (0, 10, 0),         # II/5 Panzer Bn / 529 & 532 CD Arty Bn
    25: (0, 40, 0),         # 2 MG Bn
    26: (10, 0, 5),         # 8 MG Bn
    29: (0, 40, 20),        # 5th Coy 300 Oasis Bn (20H) + HQ 15 Panzer Div (40M)
    32: (0, 25, 10),        # 155 Schutzen Regt / I/155 Arty Bn
    33: (0, 30, 0),         # 33 Arty Regt (20M) + 10th Coy 300 Oasis Bn (10M)
    44: (10, 10, 0),        # HQ 90 Light Div -- lands nowhere: is_combat=False (see docstring)
    76: (5, 18, 4),         # Sonderverband 288 Regt
    93: (10, 60, 0),        # HQ 164 Light Div etc (30M) + II/5 Flak Bn (10L,30M)
    94: (0, 25, 20),        # 164 Aufklarungs Bn
    95: (0, 25, 0),         # 433 Panzergrenadier Regt
}
IT: dict[int, tuple[int, int, int]] = {
    10: (10, 35, 15),       # 61 Sirte Div
    11: (2, 25, 3),         # 10 Brs Regt
    12: (10, 35, 15),       # 60 Sabratha Div
    18: (25, 40, 5),        # 132 Ariete Div
    21: (25, 135, 25),      # 102 Trento Div (10L95M15H) + 27 Brescia Div (15L40M10H)
    22: (25, 30, 0),        # 17 Pavia Div
    24: (10, 30, 10),       # 25 Bologna Div
    25: (10, 45, 5),        # 55 Savona Div
    45: (0, 10, 0),         # RECAM
    50: (10, 65, 5),        # 101 Trieste Div
    62: (40, 50, 0),        # 133 Littorio Div / 5 & 23 Desert Patrol
    70: (0, 5, 0),          # 8 Armored Bers Bn [Trieste]
    92: (5, 45, 0),         # 16 Pistoia Div
    94: (5, 30, 5),         # 185 Folgore Div
    97: (5, 20, 0),         # 136 GGFF Div
    99: (0, 15, 0),         # 57 Brs Bn
}


def main() -> int:
    out = []
    for nat, table in (("CW", CW), ("GE", GE), ("IT", IT)):
        for gt, (light, medium, heavy) in sorted(table.items()):
            out.append({"nationality": nat, "arrival_turn": gt,
                       "light": light, "medium": medium, "heavy": heavy})
    out_path = os.path.normpath(os.path.join(DATA, OUT))
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    totals = {}
    for rec in out:
        t = totals.setdefault(rec["nationality"], [0, 0, 0])
        t[0] += rec["light"]; t[1] += rec["medium"]; t[2] += rec["heavy"]
    print(f"wrote {len(out)} truck records -> {out_path}")
    for nat, (light, medium, heavy) in totals.items():
        print(f"  {nat}: {light} L, {medium} M, {heavy} H = {light + medium + heavy} TP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
