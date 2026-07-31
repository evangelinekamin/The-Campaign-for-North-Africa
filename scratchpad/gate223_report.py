"""GATE 22.3 -- fold the arm files written by gate223_ab.py into the four answers.

  python3 scratchpad/gate223_report.py --base BASE_live.json --head HEAD_live.json \
      [--facoff HEAD_facility_off.json] [--noop HEAD_noop.json]

Reports only what the arm files carry; it computes no game state of its own.
"""
from __future__ import annotations

import argparse
import json


def _load(path):
    if not path:
        return {}
    with open(path) as fh:
        return {r["seed"]: r for r in json.load(fh)["results"]}


def _sum(rows, path, side=None):
    tot = 0
    for r in rows:
        v = r
        for k in path:
            v = (v or {}).get(k, {}) if isinstance(v, dict) else {}
        tot += (v.get(side, 0) if side else v) if isinstance(v, dict) else (v or 0)
    return tot


def _fmt_delta(a, b):
    d = b - a
    return f"{a} -> {b} ({d:+})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--facoff", default=None)
    ap.add_argument("--noop", default=None)
    args = ap.parse_args()
    base, head = _load(args.base), _load(args.head)
    facoff, noop = _load(args.facoff), _load(args.noop)
    seeds = [s for s in head if s in base]

    print("=" * 100)
    print("0. PROVENANCE / NEUTER PROOFS")
    print("=" * 100)
    for s in seeds:
        line = f"  seed {s}: BASE {base[s]['signature8']}  HEAD {head[s]['signature8']}"
        if s in noop:
            ok = "IDENTICAL" if noop[s]["signature"] == head[s]["signature"] else "*** DIFFERS ***"
            line += f"  NOOP {noop[s]['signature8']} [{ok}]"
        if s in facoff:
            ok = "differs (good)" if facoff[s]["signature"] != head[s]["signature"] else "*** IDENTICAL: DEAD NEUTER ***"
            line += f"  FACOFF {facoff[s]['signature8']} [{ok}]"
        print(line)
    print(f"  major facility hexes (HEAD): {head[seeds[0]]['major_facility_hexes']}")

    print()
    print("=" * 100)
    print("1. THE MECHANISM -- what 22.3 restores, in the units the rule restores")
    print("=" * 100)
    print(f"  {'seed':>6} | {'TOE broken CW/AX':>18} | {'TOE fixed CW/AX BASE':>22} | "
          f"{'TOE fixed CW/AX HEAD':>22} | {'of which FACILITY CW/AX':>24}")
    for s in seeds:
        b, h = base[s], head[s]
        fac = h["paths"].get("facility/unit", {}).get("points_by_side", {})
        print(f"  {s:>6} | {h['broken_points']['toe'].get('ALLIED',0):>8}/"
              f"{h['broken_points']['toe'].get('AXIS',0):<9} | "
              f"{b['repaired_points']['toe'].get('ALLIED',0):>10}/"
              f"{b['repaired_points']['toe'].get('AXIS',0):<11} | "
              f"{h['repaired_points']['toe'].get('ALLIED',0):>10}/"
              f"{h['repaired_points']['toe'].get('AXIS',0):<11} | "
              f"{fac.get('ALLIED',0):>11}/{fac.get('AXIS',0):<12}")
    print()
    print(f"  {'seed':>6} | {'TRUCK broken CW/AX':>20} | {'TRUCK fixed BASE':>20} | "
          f"{'TRUCK fixed HEAD':>20} | {'of which FACILITY':>20}")
    for s in seeds:
        b, h = base[s], head[s]
        fac = h["paths"].get("facility/truck", {}).get("points_by_side", {})
        print(f"  {s:>6} | {h['broken_points']['truck'].get('ALLIED',0):>9}/"
              f"{h['broken_points']['truck'].get('AXIS',0):<10} | "
              f"{b['repaired_points']['truck'].get('ALLIED',0):>9}/"
              f"{b['repaired_points']['truck'].get('AXIS',0):<10} | "
              f"{h['repaired_points']['truck'].get('ALLIED',0):>9}/"
              f"{h['repaired_points']['truck'].get('AXIS',0):<10} | "
              f"{fac.get('ALLIED',0):>9}/{fac.get('AXIS',0):<10}")
    print()
    print("  RECOVERY RATE (repaired / broken WITHIN the same run -- the only cross-arm-safe")
    print("  normalisation, because chaotic divergence moves how much breaks in the first place):")
    print(f"  {'seed':>6} | {'CW TOE %':>18} | {'AX TOE %':>18} | {'CW truck %':>18} | {'AX truck %':>18}")
    means: dict = {}
    for s in seeds:
        cells = []
        for cls, side in (("toe", "ALLIED"), ("toe", "AXIS"), ("truck", "ALLIED"), ("truck", "AXIS")):
            vals = []
            for arm in (base, head):
                r = arm[s]
                bb = r["broken_points"][cls].get(side, 0)
                ff = r["repaired_points"][cls].get(side, 0)
                vals.append(100.0 * ff / bb if bb else float("nan"))
            means.setdefault((cls, side), []).append(vals)
            cells.append(f"{vals[0]:>7.1f}->{vals[1]:<7.1f}")
        print(f"  {s:>6} | " + " | ".join(f"{c:>18}" for c in cells))
    print("  MEAN over seeds:")
    for (cls, side), rows in means.items():
        b_ = sum(v[0] for v in rows) / len(rows)
        h_ = sum(v[1] for v in rows) / len(rows)
        down = sum(1 for v in rows if v[1] < v[0])
        print(f"    {cls}/{side:<7} BASE {b_:5.1f}%  HEAD {h_:5.1f}%  ({h_ - b_:+.1f} pp; "
              f"HEAD lower in {down}/{len(rows)} seeds)")

    print()
    print("  PATH LEDGER (HEAD, summed over seeds) -- calls / funded / offered / repaired / F+S spent")
    for key in ("facility/unit", "facility/truck", "field/unit", "field/truck"):
        c = f_ = o = u = p = fu = st_ = 0
        by_side_pts: dict = {}
        by_r: dict = {}
        for s in seeds:
            v = head[s]["paths"].get(key)
            if not v:
                continue
            c += v["calls"]; f_ += v["funded"]; o += v["offered"]; u += v["offered_unfunded"]
            p += v["points"]; fu += v["fuel"]; st_ += v["stores"]
            for k2, v2 in v["points_by_side"].items():
                by_side_pts[k2] = by_side_pts.get(k2, 0) + v2
            for k2, v2 in v["points_by_hex_r"].items():
                by_r[int(k2)] = by_r.get(int(k2), 0) + v2
        print(f"    {key:<16} calls={c:<6} funded={f_:<6} offered={o:<7} "
              f"offered_unfunded={u:<6} repaired={p:<6} fuel={fu:<6} stores={st_:<6} {by_side_pts}")
        if key.startswith("facility") and by_r:
            print(f"      repaired by hex r: {dict(sorted(by_r.items()))}")

    print()
    print("=" * 100)
    print("2. DOES IT REACH THE FRONT?")
    print("=" * 100)
    for s in seeds:
        h = head[s]
        print(f"  seed {s}:")
        for label, book in (("units", h["front_reach_units"]), ("trucks", h["front_reach_trucks"])):
            for side, v in sorted(book.items()):
                print(f"    {label:<7} {side:<7} counters={v['counters']:<4} "
                      f"points={v['points_recovered']:<5} "
                      f"median_r_at_repair={v['median_r_at_repair']:<5} "
                      f"best_r={v['best_r_reached']} "
                      f"moved_at_all={v['hexes_gained_toward_enemy']['moved_at_all']} "
                      f"max_gain={v['hexes_gained_toward_enemy']['max']} "
                      f"fwd_after={v['counters_forward_after_repair']} "
                      f"fwd_at_end={v['counters_forward_at_end']}")
                if side == "ALLIED":
                    print(f"            reach: {v['reach_histogram']}  "
                          f"points_west_of_alexandria={v['points_reaching_west_of_alexandria']}")

    print()
    print("=" * 100)
    print("3. THE BALANCE -- winner, 64.76 grade, and the geography/bookkeeping decomposition")
    print("=" * 100)
    hdr = f"  {'seed':>6} | {'BASE':<46} | {'HEAD':<46} | dVP(AX) dVP(CW) | dGEO(AX) dGEO(CW)"
    print(hdr)
    n_ax_up = n_ax_dn = n_cw_up = n_cw_dn = 0
    for s in seeds:
        b, h = base[s], head[s]
        dax = (h["victory_total_axis"] or 0) - (b["victory_total_axis"] or 0)
        dcw = (h["victory_total_cw"] or 0) - (b["victory_total_cw"] or 0)
        dgax = h["geographic_64_73"]["AXIS"] - b["geographic_64_73"]["AXIS"]
        dgcw = h["geographic_64_73"]["ALLIED"] - b["geographic_64_73"]["ALLIED"]
        n_ax_up += dax > 0; n_ax_dn += dax < 0
        n_cw_up += dcw > 0; n_cw_dn += dcw < 0
        print(f"  {s:>6} | {b['reason'][:46]:<46} | {h['reason'][:46]:<46} | "
              f"{dax:>+7.1f} {dcw:>+7.1f} | {dgax:>+8} {dgcw:>+8}")
    print(f"  SIGN TALLY over {len(seeds)} seeds: Axis VP up {n_ax_up} / down {n_ax_dn}; "
          f"CW VP up {n_cw_up} / down {n_cw_dn}")
    print("  winners: BASE", {s: base[s]["winner"] for s in seeds})
    print("  winners: HEAD", {s: head[s]["winner"] for s in seeds})
    if facoff:
        print()
        print("  FACILITY-ONLY (HEAD live vs HEAD facility_off -- isolates the 22.3 routing from the")
        print("  in_hex_draw / partial-attempt fixes that shipped in the same commit):")
        up = dn = 0
        for s in seeds:
            if s not in facoff:
                continue
            f_, h = facoff[s], head[s]
            dax = (h["victory_total_axis"] or 0) - (f_["victory_total_axis"] or 0)
            up += dax > 0
            dn += dax < 0
            print(f"    seed {s}: facoff {f_['reason'][:44]:<44} -> live {h['reason'][:44]:<44} "
                  f"dVP(AX)={dax:+.1f} "
                  f"dVP(CW)={(h['victory_total_cw'] or 0)-(f_['victory_total_cw'] or 0):+.1f} "
                  f"dGEO(AX)={h['geographic_64_73']['AXIS']-f_['geographic_64_73']['AXIS']:+} "
                  f"dGEO(CW)={h['geographic_64_73']['ALLIED']-f_['geographic_64_73']['ALLIED']:+}")
        print(f"    SIGN TALLY (facility half alone): Axis VP up {up} / down {dn}")
        print("    CW TOE recovery rate, facility_off -> live (the facility half's own contribution):")
        for s in seeds:
            if s not in facoff:
                continue
            out = []
            for cls, side in (("toe", "ALLIED"), ("truck", "ALLIED")):
                vs = []
                for arm in (facoff, head):
                    r = arm[s]
                    bb = r["broken_points"][cls].get(side, 0)
                    vs.append(100.0 * r["repaired_points"][cls].get(side, 0) / bb if bb else 0.0)
                out.append(f"{cls} {vs[0]:.1f}%->{vs[1]:.1f}%")
            print(f"      seed {s}: " + "  ".join(out))

    print()
    print("=" * 100)
    print("4. SANITY")
    print("=" * 100)
    for name, arm in (("BASE", base), ("HEAD", head), ("FACOFF", facoff), ("NOOP", noop)):
        if not arm:
            continue
        bad = {s: r.get("sanity_absurd") for s, r in arm.items() if r.get("sanity_absurd")}
        err = {s: r.get("ERROR") for s, r in arm.items() if r.get("ERROR")}
        print(f"  {name}: absurdities={bad or 'NONE'} errors={err or 'NONE'} "
              f"seconds={[r.get('seconds') for r in arm.values()]}")
    for s in seeds:
        h, b = head[s], base[s]
        print(f"  seed {s}: biggest single repair HEAD {h['biggest_single_repair']} "
              f"BASE {b['biggest_single_repair']} | alive AX/CW "
              f"{b['axis_units_alive']}/{b['cw_units_alive']} -> "
              f"{h['axis_units_alive']}/{h['cw_units_alive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
