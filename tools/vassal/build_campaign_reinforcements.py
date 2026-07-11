"""Author data/reinforcements_campaign.json -- the rule-20 reinforcement flow for the
full campaign, transcribed from the [4.43b] Axis and [4.43a] Commonwealth Land Unit
Reinforcement Schedules (rule 90) and Fable-cross-checked, then given entry hexes and
Basic Morale here.

The transcription (RECORDS below) captures the MAJOR combat formations at battalion/
regiment granularity -- the German DAK build-up (Rommel GT20, 5th Light / 15 Panzer /
90 & 164 Light), the Italian reinforcement divisions (Sirte, Sabratha, Ariete, Trento,
Pavia, Bologna, Savona, Brescia, Trieste, Littorio, Pistoia, Folgore) and the 8th-Army
build-up (2nd/7th/10th Armoured, the Tiger Convoy, the Australian/NZ/Indian/SA divisions).
Standalone flak/artillery batteries, oasis companies and truck-only lines are deferred.

Entry: Axis reinforcements enter from the west (the Tripoli box, at El Agheila A1816);
Commonwealth from the east (Cairo E1730). Each is placed at the nearest free hex to its
side's entry anchor -- reinforcements sit dormant on the map from turn 1 (game.engine
_reinforcements) so every one needs its own stacking room (rule 9.14). Basic Morale is
set per formation from the OA charts: German DAK divisions and the Italian [4.44b] sheets,
and the Commonwealth [4.44B] sheets.

    python3 tools/vassal/build_campaign_reinforcements.py

Consumed by game.oob.build(reinforcements_file="reinforcements_campaign.json").
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from game import cna_map, coords, oob  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")
CAP = 4                                 # keep each entry hex <= 4 points (rule-9.14 limit is 5)
WEST, EAST = "A1816", "E1730"           # Axis-from-Tripoli / Commonwealth-from-Cairo entry anchors

# Basic Morale by formation substring (rule 17.1 / the OA charts), most-specific first.
# German DAK divisions; Italian [4.44b]; Commonwealth [4.44B] (Fable-extracted). Defaults:
# German troops were good (+1), Italian neutral (0), Commonwealth +1 (every "Unassigned" is +1).
MORALE = {
    "GE": [("5 Le", 2), ("5th Light", 2), ("15", 2), ("90", 2), ("164", 1)],
    "IT": [("Ariete", 1), ("Littorio", 0), ("Trento", 0), ("Trieste", 0), ("Folgore", 1),
           ("GGFF", -3), ("Giovani Fascisti", -3), ("Sirte", -1), ("Sabratha", -1),
           ("Pavia", -1), ("Bologna", -1), ("Brescia", -1), ("Savona", -1), ("Pistoia", -1),
           ("3 CCNN", -2)],
    "CW": [("1st Armoured", 2), ("2nd Armoured", 2), ("7th Armoured", 2), ("22nd Armoured", 2),
           ("32nd Army Tank", 2), ("8th Armoured", 1), ("10th Armoured", 1), ("Army Tank", 1),
           ("44th", 2), ("50th", 1), ("51st", 1), ("70th", 1), ("Indian", 1), ("Australian", 1),
           ("New Zealand", 1), ("South African", 0), ("Free French", 1), ("Greek", 0),
           ("Polish", 1), ("Czech", 1)],
}
MORALE_DEFAULT = {"GE": 1, "IT": 0, "CW": 1}


def morale_for(formation: str, nat: str) -> int:
    for key, m in MORALE[nat]:
        if key in formation:
            return m
    return MORALE_DEFAULT[nat]


# The transcribed schedule lives in data/reinforcements_campaign_source.json -- one record
# per {counter, formation, nationality (GE|IT|CW), role, model?, arrival_gt, entry (west|east)},
# transcribed from [4.43b]/[4.43a] by the c2-3-reinforcements workflow and Fable-verified.
SOURCE = "reinforcements_campaign_source.json"


def _dist(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (abs(a[0] - b[0]) + abs(a[0] + a[1] - b[0] - b[1]) + abs(a[1] - b[1])) // 2


def main() -> int:
    tmap, _ = cna_map.load_sections("ABCDE")
    valid = set(tmap.terrain)
    # Seed occupancy from the on-map campaign force so reinforcements never share a hex with it.
    base, _ = oob.build(oob_file="oob_italian.json", extra_file="oob_campaign_extra.json",
                        sections="ABCDE", reinforcements_file=None)
    occ: dict[tuple[int, int], int] = {}
    for u in base:
        occ[u.hex] = occ.get(u.hex, 0) + u.stacking_points

    def place(anchor: str) -> list[int]:
        sec, tgt = anchor[0], coords.to_axial(coords.parse(anchor))
        cands = []
        for col in range(1, 62):
            for row in range(1, 62):
                try:
                    ax = coords.to_axial(coords.parse(f"{sec}{col:02d}{row:02d}"))
                except Exception:
                    continue
                if ax in valid:
                    cands.append((_dist(ax, tgt), ax))
        for _, ax in sorted(cands):
            if occ.get(ax, 0) < CAP:
                occ[ax] = occ.get(ax, 0) + 1
                return [ax[0], ax[1]]
        raise RuntimeError(f"no free hex near {anchor}")

    with open(os.path.join(DATA, SOURCE)) as f:
        records = json.load(f)
    out = []
    for rec in records:
        nat = rec["nationality"]
        side = "AXIS" if nat in ("GE", "IT") else "ALLIED"
        r = {
            "counter": rec["counter"],
            "group": f"{nat} {rec['formation']}",
            "hex": place(WEST if rec["entry"] == "west" else EAST),
            "side": side,
            "role": rec["role"],
            "nationality": None if nat == "CW" else nat,
            "morale": morale_for(rec["formation"], nat),
            "arrival_turn": rec["arrival_gt"],
        }
        if rec.get("model"):
            r["model"] = rec["model"]
        out.append(r)

    out.sort(key=lambda r: (r["arrival_turn"], r["side"], r["counter"]))
    out_path = os.path.normpath(os.path.join(DATA, "reinforcements_campaign.json"))
    with open(out_path, "w") as f:
        json.dump({"reinforcements": out}, f, indent=2)
        f.write("\n")
    from collections import Counter
    print(f"wrote {len(out)} reinforcements -> {out_path}")
    print("by side:", dict(Counter(r["side"] for r in out)))
    print("arrival GT span:", min((r["arrival_turn"] for r in out), default=0),
          "-", max((r["arrival_turn"] for r in out), default=0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
