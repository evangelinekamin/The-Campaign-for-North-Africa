"""GATE 8.2 -- the A/B comparison table.  Read-only."""
from __future__ import annotations

import json
import sys

base = json.load(open(sys.argv[1]))["results"]
head = json.load(open(sys.argv[2]))["results"]
B = {r["seed"]: r for r in base}
H = {r["seed"]: r for r in head}

print(f"{'seed':>6} {'sig BASE':>17} {'sig HEAD':>17} {'same':>5} "
      f"{'winner':>7} {'VP BASE':>10} {'VP HEAD':>10} {'dAxis':>6} {'dCW':>5} {'belts':>5}")


def vp(r):
    import re
    m = re.search(r"(\d+)-(\d+) Victory Points", r["reason"] or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


rows = []
for s in [r["seed"] for r in head]:
    b, h = B[s], H[s]
    ba, bc = vp(b)
    ha, hc = vp(h)
    same = b["signature"] == h["signature"]
    rows.append((s, same, ha - ba if None not in (ha, ba) else None,
                 hc - bc if None not in (hc, bc) else None))
    print(f"{s:>6} {b['signature']:>17} {h['signature']:>17} {str(same):>5} "
          f"{str(h['winner']):>7} {f'{ba}-{bc}':>10} {f'{ha}-{hc}':>10} "
          f"{str(ha - ba):>6} {str(hc - bc):>5} {h['final_minefields']:>5}")

print(f"\nbyte-identical: {sum(1 for r in rows if r[1])}/{len(rows)}")
print(f"winner changed on: {[s for s in H if H[s]['winner'] != B[s]['winner']]}")
print(f"grade string changed on: {[s for s in H if H[s]['reason'] != B[s]['reason']]}")
d = [r[2] for r in rows if r[2] is not None]
print(f"Axis VP deltas: {d}   (sum {sum(d)}, nonzero on {sum(1 for x in d if x)} of {len(d)})")
print(f"CW   VP deltas: {[r[3] for r in rows]}")

print("\n--- ENGINEERING, HEAD arm (the rule-26/24.3/24.4 machinery in live play) ---")
for s, r in H.items():
    print(f"  seed {s}: minefields on the final board={r['final_minefields']}  "
          f"forts raised by construction={len(r['fortifications_raised_above_the_static_roster'])}  "
          f"units able to LAY a belt (24.31)={r['units_that_could_LAY_a_belt_24_31']}  "
          f"units able to CLEAR/ESCORT (26.24)={r['units_that_could_CLEAR_or_ESCORT_26_24']}  "
          f"engineering events={r['engineering_events']}")
    print(f"           engineer census over every unit the war contained: "
          f"{r['engineer_capability_census_all_units_ever']}")
    print(f"           static Major-City fort census (levels): {r['fort_level_census']}")
    print(f"           stuck units (no legal exit): {len(r['stuck_units'])}")
