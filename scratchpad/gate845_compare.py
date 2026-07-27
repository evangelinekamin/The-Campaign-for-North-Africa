"""GATE [8.45] -- fold the two A/B arms into the four answers the gate asks.  (read-only)"""
from __future__ import annotations

import json
import re
import sys


def load(p):
    return {r["seed"]: r for r in json.load(open(p))["results"]}


def vp(reason):
    m = re.search(r"(-?[\d.]+)-(-?[\d.]+) Victory Points", reason or "")
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def level(reason):
    m = re.match(r"(Axis|Commonwealth) ([A-Za-z ]+?):", reason or "")
    return m.group(0)[:-1] if m else (reason or "")[:40]


def main():
    base, head = load(sys.argv[1]), load(sys.argv[2])
    seeds = [s for s in base if s in head]

    print("=" * 118)
    print("3. THE BALANCE -- winner + 64.76 grade, per seed")
    print("=" * 118)
    print(f"{'seed':>6} | {'BASE outcome':38} | {'HEAD outcome':38} | {'dAxisVP':>8} {'dCwVP':>7} {'dRatio':>8}")
    shifts = []
    for s in seeds:
        ba, bc = vp(base[s]["reason"])
        ha, hc = vp(head[s]["reason"])
        dr = (ha / max(hc, 1e-9)) - (ba / max(bc, 1e-9))
        shifts.append((s, ha - ba, hc - bc, dr))
        print(f"{s:>6} | {level(base[s]['reason']):38} | {level(head[s]['reason']):38} | "
              f"{ha - ba:>+8.0f} {hc - bc:>+7.0f} {dr:>+8.1f}")
    print(f"\n  winners identical: {all(base[s]['winner'] == head[s]['winner'] for s in seeds)}"
          f"   grades identical: {all(level(base[s]['reason']) == level(head[s]['reason']) for s in seeds)}")
    pos = sum(1 for _, da, _, _ in shifts if da > 0)
    neg = sum(1 for _, da, _, _ in shifts if da < 0)
    zer = sum(1 for _, da, _, _ in shifts if da == 0)
    print(f"  Axis VP delta sign: +{pos} / -{neg} / 0 {zer}   "
          f"mean {sum(d for _, d, _, _ in shifts) / len(shifts):+.1f}")
    pos = sum(1 for _, _, dc, _ in shifts if dc > 0)
    neg = sum(1 for _, _, dc, _ in shifts if dc < 0)
    print(f"  CW   VP delta sign: +{pos} / -{neg} / 0 {len(shifts) - pos - neg}   "
          f"mean {sum(d for _, _, d, _ in shifts) / len(shifts):+.1f}")

    print()
    print("=" * 118)
    print("2. DOES THE AXIS STOP -- furthest east (r; El Alamein r118, Alexandria r133, Tobruk r66)")
    print("=" * 118)
    print(f"{'seed':>6} | {'ground high-water':>26} | {'any-event high-water':>26} | "
          f"{'east at end':>22} | {'sig':>14}")
    for s in seeds:
        b, h = base[s], head[s]
        print(f"{s:>6} | r{b['axis_east_ever_ground']:>3} -> r{h['axis_east_ever_ground']:<3} "
              f"({h['axis_east_ever_ground'] - b['axis_east_ever_ground']:+4d})        | "
              f"r{b['axis_east_ever_any']:>3} -> r{h['axis_east_ever_any']:<3} "
              f"({h['axis_east_ever_any'] - b['axis_east_ever_any']:+4d})        | "
              f"r{b['axis_east_at_end']:>3} -> r{h['axis_east_at_end']:<3} "
              f"({h['axis_east_at_end'] - b['axis_east_at_end']:+4d}) | "
              f"{b['signature'][:6]}->{h['signature'][:6]}")
    d = [head[s]['axis_east_ever_ground'] - base[s]['axis_east_ever_ground'] for s in seeds]
    print(f"  ground high-water delta: {d}  (mean {sum(d) / len(d):+.1f}, "
          f"west on {sum(1 for x in d if x < 0)}/{len(d)} seeds)")
    d = [head[s]['axis_east_at_end'] - base[s]['axis_east_at_end'] for s in seeds]
    print(f"  east-at-end     delta: {d}  (mean {sum(d) / len(d):+.1f}, "
          f"west on {sum(1 for x in d if x < 0)}/{len(d)} seeds)")

    print()
    print("=" * 118)
    print("4. SANITY -- can the Axis still feed and reach his own front?")
    print("=" * 118)
    keys = ["events", "truck_moves", "truck_moves_ending_in_desert", "axis_ground_moves_into_desert",
            "rejects_total", "axis_units_alive", "cw_units_alive"]
    print(f"{'seed':>6} | " + " | ".join(f"{k[:22]:>22}" for k in keys))
    for s in seeds:
        print(f"{s:>6} | " + " | ".join(
            f"{base[s][k]:>9} ->{head[s][k]:>10}" for k in keys))
    print()
    for s in seeds:
        b, h = base[s], head[s]
        print(f"  seed {s}: stuck BASE={len(b['stuck_units'])} HEAD={len(h['stuck_units'])} "
              f"| barred-in-desert HEAD={len(h['barred_units_standing_in_desert'])} "
              f"| same stuck set={sorted(u['unit'] for u in b['stuck_units']) == sorted(u['unit'] for u in h['stuck_units'])}")
    allw = sorted({k for s in seeds for k in list(base[s]['watch']) + list(head[s]['watch'])})
    print("\n  whole-war event census (sum over the 7 seeds), BASE -> HEAD:")
    for k in allw:
        bt = sum(base[s]['watch'].get(k, 0) for s in seeds)
        ht = sum(head[s]['watch'].get(k, 0) for s in seeds)
        if bt or ht:
            print(f"    {k:38} {bt:>8} -> {ht:>8}  ({ht - bt:+d})")
    print("\n  order-rejection reasons (sum over the 7 seeds), BASE -> HEAD:")
    br, hr = {}, {}
    for s in seeds:
        for r, n in base[s]['rejects_top']:
            br[r] = br.get(r, 0) + n
        for r, n in head[s]['rejects_top']:
            hr[r] = hr.get(r, 0) + n
    for r in sorted(set(br) | set(hr), key=lambda x: -max(br.get(x, 0), hr.get(x, 0))):
        print(f"    {r:62} {br.get(r, 0):>7} -> {hr.get(r, 0):>7}  ({hr.get(r, 0) - br.get(r, 0):+d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
