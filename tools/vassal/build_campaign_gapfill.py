"""Author data/oob_campaign_extra.json -- the September-1940 campaign gap-fill.

The VASSAL "setup italian.vsav" (data/oob_italian.json) is a PARTIAL setup: it fields
61 Italian counters but omits two of the 10th Army's infantry divisions and nearly all
of its armour. This script layers the missing forces on top, from the rulebook rather
than the save (which does not contain them):

  - 63 Cirene & 62 Marmarica Divisions. These have NO [4.44b] Organization-at-Arrival
    sheet (the design "melted" many 1940 units), so they are reconstructed from the
    Catanzaro semi-mot archetype (rule-90 [4.44b] l.4191-4209) -- two infantry regiments
    of three battalions, regiment HQs, an artillery regiment, an MG and an engineer
    battalion -- at their rule-60.31 deployment hexes, with historical regiment numbers.
    Basic Morale -1 is INFERRED from the Catanzaro-class pattern (marked in the record).
  - The Libyan Tank Command ("Babini" Gruppo), transcribed from the [4.44b] sheet
    (l.3945-3956): eight CV33 tankette battalions + Aresca HQ, and two M11/39 medium
    battalions (I(M), II(M)), deployed per the rule-60.31 attachments.
  - The Derna and Bir Scheferzen garrisons (rule 60.31), omitted from the save.

Placement: each unit targets its rule-60.31 anchor hex and spills to the nearest valid,
low-occupancy hex. The historical divisions spread ~1 unit per hex and the 5-point
stacking limit (rule 9.14) forbids piling a division on one hex; occupancy is seeded from
the extraction so the gap-fill never over-stacks a hex the start force already holds.

    python3 tools/vassal/build_campaign_gapfill.py

Consumed by game.oob.build(extra_file="oob_campaign_extra.json") -> game.scenario.campaign.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from game import cna_map, coords, oob  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")
CAP = 4                                # keep each hex <= 4 points (limit is 5; extraction ~1/hex)


def _dist(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (abs(a[0] - b[0]) + abs(a[0] + a[1] - b[0] - b[1]) + abs(a[1] - b[1])) // 2


def main() -> int:
    tmap, _ = cna_map.load_sections("ABCDE")
    valid = set(tmap.terrain)
    base, _ = oob.build(oob_file="oob_italian.json", sections="ABCDE", reinforcements_file=None)
    occ: dict[tuple[int, int], int] = {}
    for u in base:
        occ[u.hex] = occ.get(u.hex, 0) + u.stacking_points

    def place(anchor: str) -> str:
        """Nearest valid hex to `anchor` with spare stacking capacity; reserve it."""
        sec, tgt = anchor[0], coords.to_axial(coords.parse(anchor))
        cands = []
        for col in range(1, 62):
            for row in range(1, 62):
                lbl = f"{sec}{col:02d}{row:02d}"
                try:
                    ax = coords.to_axial(coords.parse(lbl))
                except Exception:
                    continue
                if ax in valid:
                    cands.append((_dist(ax, tgt), lbl, ax))
        for _, lbl, ax in sorted(cands):
            if occ.get(ax, 0) < CAP:
                occ[ax] = occ.get(ax, 0) + 1
                return lbl
        raise RuntimeError(f"no free hex near {anchor}")

    def unit(counter: str, group: str, anchor: str, role: str, model: str | None = None) -> dict:
        r = {"counter": counter, "group": group, "hex": place(anchor), "side": "AXIS",
             "kind": "unit", "nationality": "IT", "role": role}
        if model:
            r["model"] = model
        return r

    def division(nick: str, group: str, anchor: str, regts: list[str], arty: str) -> list[dict]:
        out = []
        for rn in regts:
            out.append(unit(f"IT {rn} - {nick}", group, anchor, "infantry"))          # regiment HQ
            for bn in ("I", "II", "III"):
                out.append(unit(f"IT {bn}/{rn} - {nick}", group, anchor, "infantry"))  # infantry bn
        out.append(unit(f"IT {arty} - {nick} (ART)", group, anchor, "artillery"))       # arty regt
        out.append(unit(f"IT {nick} (MG)", group, anchor, "mg"))                        # MG bn
        out.append(unit(f"IT {nick} (ENG)", group, anchor, "infantry"))                 # engineer bn
        return out

    recs: list[dict] = [{
        "kind": "_comment",
        "note": ("C2-2 campaign gap-fill, authored by tools/vassal/build_campaign_gapfill.py "
                 "from rule 60.31 + rule-90 [4.44b]. Layered onto oob_italian.json via "
                 "oob.build(extra_file=...). Cirene/Marmarica reconstructed (no [4.44b] sheet), "
                 "morale -1 inferred; armour transcribed from the Libyan Tank Command sheet.")
    }]
    recs += division("63 Cir", "IT 63rd Cirene Division", "C4120", ["157", "158"], "45")
    recs += division("62 Marm", "IT 62nd Marmarica Division", "C3918", ["115", "116"], "44")

    ltc = "IT The Libyan Tank Command"
    armour = [
        ("IT Aresca - LTC", "C3919", "cv33"), ("IT XXI(L) - LTC", "C3919", "cv33"),
        ("IT XX(L) - LTC", "C4321", "cv33"), ("IT LX(L) - LTC", "C4321", "cv33"),
        ("IT LXI(L) - LTC", "C4321", "cv33"), ("IT IX(L) - LTC", "C4014", "cv33"),
        ("IT LXII(L) - LTC", "C3918", "cv33"), ("IT LXIII(L) - LTC", "C4120", "cv33"),
        ("IT I(M) - LTC", "C4218", "m11_39"), ("IT II(M) - LTC", "C3822", "m11_39"),
    ]
    recs += [unit(c, ltc, h, "tank", m) for c, h, m in armour]

    recs.append(unit("IT Derna - Derna", "IT Derna Garrison", "B5925", "infantry"))
    recs.append(unit("IT Scheferzen - BirSch", "IT Bir Scheferzen Garrison", "C3419", "infantry"))
    recs.append(unit("IT Barka - Bardia", "IT Barka Garrison", "C4321", "infantry"))  # rule 60.31 Bardia

    out_path = os.path.normpath(os.path.join(DATA, "oob_campaign_extra.json"))
    with open(out_path, "w") as f:
        json.dump(recs, f, indent=2)
        f.write("\n")
    units = [r for r in recs if r.get("kind") == "unit"]
    print(f"wrote {len(recs)} records ({len(units)} units) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
