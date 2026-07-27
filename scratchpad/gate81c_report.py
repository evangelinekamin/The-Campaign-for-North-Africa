"""GATE 8.1c -- the report.  Folds the census, the A/B and the autopsy into one table.

Read-only; consumes the JSON the other three drivers wrote and computes nothing from the engine
except the campaign calendar (game.calendar.gt_dateline) and the belt price (game.minefields), so
that every magnitude printed here is the rulebook's.

Usage:  PYTHONPATH=<repo> python3 scratchpad/gate81c_report.py --dir scratchpad/gate81c
"""
from __future__ import annotations

import argparse
import json
import math
import os


PROVENANCE = [
    "GATE 8.1c -- CAN THE DEVIL'S GARDENS NOW BE BUILT?   measured 2026-07-27",
    "",
    "  BASE  e73409a  the last commit before the 8.1b engineer order of battle",
    "  HEAD  e068c2f  306bcfe (seed the engineer counters) + e068c2f (its 23.11/23.14 repair)",
    "  Rule 26, 24.3 and 24.4 shipped earlier, at aa4b6a2, an ancestor of BOTH arms, so the only",
    "  thing that differs between them is the ORDER OF BATTLE.  Nothing in game/ or data/ was",
    "  touched by this gate; every driver lives in scratchpad/ and is read-only.",
    "",
    "  census   scratchpad/gate81c_census.py, both trees, static over campaign(seed=1).t0",
    "  A/B      scratchpad/gate81c_ab.py,     both trees, seeds 1941 7 4 24 2026 99 1, 7 workers,",
    "           each arm one process, full GT1-111",
    "  autopsy  scratchpad/gate81c_probe.py,  HEAD, same seven seeds, same shape",
    "  BASE reproduced all seven of the 8.2 gate's own HEAD-arm signatures (gate82_ab_HEAD3.log,",
    "  run at 2737e5e) byte for byte, and the probed and unprobed HEAD runs agree seed for seed --",
    "  two independent confirmations of the cross-process reproducibility that gate's provenance",
    "  note left open.",
    "",
    "  The autopsy's dump indexing was refactored for speed mid-gate; probe_smoke.json (pre) and",
    "  probe_smoke2.json (post) are the 30-turn seed-4 pair proving it moved no measured number.",
]


def load(d, name):
    p = os.path.join(d, name)
    return json.load(open(p)) if os.path.exists(p) else None


def census_block(base, head) -> list:
    from game import calendar

    out = ["=" * 100,
           "1. THE CENSUS -- every counter the 111-turn campaign ever contains",
           "=" * 100]
    out.append(f"  units in the order of battle:  BASE {base['units_the_war_ever_contains']}"
               f"  ->  HEAD {head['units_the_war_ever_contains']}"
               f"  (+{head['units_the_war_ever_contains'] - base['units_the_war_ever_contains']})")
    out.append("")
    out.append(f"  {'engineer flag':<26} {'BASE':>6} {'HEAD':>6}")
    keys = sorted(set(base["engineer_flag_census"]) | set(head["engineer_flag_census"]))
    for k in keys:
        out.append(f"  {k:<26} {base['engineer_flag_census'].get(k, 0):>6} "
                   f"{head['engineer_flag_census'].get(k, 0):>6}")
    out.append("")
    out.append(f"  {'capability (rule)':<40} {'BASE AX/AL':>14} {'HEAD AX/AL':>14}")
    for k in ("LAY_a_belt_24_31", "BUILD_a_fortification_24_42", "CLEAR_a_belt_26_13",
              "ESCORT_through_a_belt_26_24"):
        b, h = base["capability"][k], head["capability"][k]
        out.append(f"  {k:<40} {str(b['AXIS']) + '/' + str(b['ALLIED']):>14} "
                   f"{str(h['AXIS']) + '/' + str(h['ALLIED']):>14}")

    # WHEN the capability exists -- the 8.2 gate could not ask this, having nothing to time.
    out.append("")
    out.append("  cumulative lay-capable counters on the order of battle, by Game-Turn:")
    roster = head["roster_LAY"]
    for gt in (1, 12, 24, 36, 48, 60, 72, 84, 96, 111):
        ax = sum(1 for r in roster if r["side"] == "AXIS" and (r["arrival_turn"] or 1) <= gt)
        al = sum(1 for r in roster if r["side"] == "ALLIED" and (r["arrival_turn"] or 1) <= gt)
        out.append(f"    GT{gt:>3} ({calendar.gt_dateline(gt)}):  Axis {ax:>2}   Commonwealth {al:>2}")
    return out


def throughput_block(head) -> list:
    """[24.32] one Op-Stage per belt hex, and the belt is the 8.2 gate's own measured geometry."""
    from game import minefields as mf

    out = ["", "=" * 100,
           "   ...and what that buys, at [24.32]'s one Operations Stage per hex (3 stages / GT):",
           "=" * 100]
    roster = [r for r in head["roster_LAY"] if r["side"] == "ALLIED"]
    for gt, belt, label in ((72, 30, "the 8.2 gate's depth-1 full-width band at the Alamein meridian"),
                            (72, 12, "the 8.2 gate's 12-hex VEHICLE min-vertex cut"),
                            (96, 30, "the same band"),
                            (96, 12, "the same cut")):
        n = sum(1 for r in roster if (r["arrival_turn"] or 1) <= gt)
        stages = math.ceil(belt / n) if n else None
        out.append(f"    GT{gt:>3}: {n:>2} CW lay-capable counters -> {belt:>3} hexes "
                   f"= {stages} Op-Stages = {stages / 3.0:.1f} Game-Turns   ({label})")
    out.append(f"    price of the 30-hex band: {30 * mf.REAL_STORES} Stores + {30 * mf.REAL_AMMO} "
               f"Ammunition; of the 12-hex cut: {12 * mf.REAL_STORES} + {12 * mf.REAL_AMMO}"
               f"   (data/minefields.json)")
    return out


def _late(r, lo):
    """The Axis ground high-water from Game-Turn `lo` on -- the Panzerarmee's mark rather than the
    Italian 10th Army's.  Derived from the per-turn series the A/B already recorded."""
    pt = {int(k): v for k, v in r["axis_ground_high_water_per_turn"].items() if int(k) >= lo}
    if not pt:
        return None, None
    m = max(pt.values())
    return m, min(k for k, v in pt.items() if v == m)


def ab_block(base, head) -> list:
    ra = base["results"][0]["r_alamein"]
    out = ["", "=" * 100,
           "2 + 3 + 4. THE A/B -- seven full 111-turn campaigns per arm",
           "=" * 100,
           f"  anchors: El Alamein r={ra}   Alexandria r={base['results'][0]['r_alexandria']}"
           f"   Tobruk r={base['results'][0]['r_tobruk']}",
           "  hw = furthest-east axial r of an Axis GROUND move (air missions excluded by kind)",
           "",
           f"  {'seed':>6} {'arm':<5} {'winner':<7} {'belts':>6} {'forts+':>7} {'eng.ev':>7} "
           f"{'hw':>4} {'GT':>4} {'hw>=GT48':>9} {'GT':>4} {'end':>4}  grade"]
    by = {}
    for arm, doc in (("BASE", base), ("HEAD", head)):
        for r in doc["results"]:
            by.setdefault(r["seed"], {})[arm] = r
    for seed in base["seeds"]:
        for arm in ("BASE", "HEAD"):
            r = by.get(seed, {}).get(arm)
            if r is None or "ERROR" in (r or {}):
                out.append(f"  {seed:>6} {arm:<5} ERROR {(r or {}).get('ERROR', 'missing')}")
                continue
            lm, lt = _late(r, 48)
            out.append(f"  {seed:>6} {arm:<5} {str(r['winner']):<7} {r['final_minefields']:>6} "
                       f"{len(r['fortifications_raised_above_the_static_roster']):>7} "
                       f"{r['engineering_event_total']:>7} "
                       f"{r['axis_ground_high_water_r']:>4} "
                       f"{str(r['axis_ground_high_water_turn']):>4} "
                       f"{str(lm):>9} {str(lt):>4} "
                       f"{str(r['axis_east_at_end']):>4}  {r['reason']}")
        out.append("")

    # The balance, stated as the gate asks: mechanism, not verdict.
    out.append("  VP delta, HEAD minus BASE (positive = the Commonwealth gained):")
    shifts = []
    for seed in base["seeds"]:
        pair = by.get(seed, {})
        if "BASE" not in pair or "HEAD" not in pair:
            continue
        if "ERROR" in pair["BASE"] or "ERROR" in pair["HEAD"]:
            continue

        def vp(r):
            tok = r["reason"].split(":")[-1].strip().split()[0]
            a, c = tok.split("-")
            return int(a), int(c)

        ab, cb = vp(pair["BASE"])
        ah, ch = vp(pair["HEAD"])
        d = (ch - cb) - (ah - ab)
        shifts.append(d)
        out.append(f"    seed {seed:>5}: Axis {ab:>5} -> {ah:>5}   CW {cb:>4} -> {ch:>4}   "
                   f"CW-ward swing {d:+6}")
    if shifts:
        pos = sum(1 for s in shifts if s > 0)
        neg = sum(1 for s in shifts if s < 0)
        out.append(f"    {pos} seeds toward the Commonwealth, {neg} toward the Axis, "
                   f"{len(shifts) - pos - neg} unmoved  -- "
                   f"{'SYSTEMATIC' if pos == len(shifts) or neg == len(shifts) else 'RANDOM IN SIGN'}")
    return out


def autopsy_block(doc) -> list:
    out = ["", "=" * 100,
           "2b. THE AUTOPSY -- which clause of 24.31/24.33/24.42/24.43 actually refuses",
           "=" * 100,
           "  Every column is an engineer-SEGMENT: one lay-capable counter, one Construction",
           "  Segment.  [24.32] prices a belt hex at ONE such segment, so the AFFORDABLE column is",
           "  belt hexes the side could have laid and did not.",
           "",
           f"  {'seed':>6} {'side':<7} {'segs':>5} {'legalLAY':>9} {'affLAY':>7} {'legalFRT':>9} "
           f"{'affFRT':>7} {'onDump':>7} {'lgl+dmp':>8} {'dist':>6}  orders"]
    for r in doc["results"]:
        if "ERROR" in r:
            out.append(f"  {r['seed']:>6} ERROR {r['ERROR']}")
            continue
        for side, t in r["autopsy"].items():
            n = t.get("n_for_that_mean", 0)
            mean = (t.get("sum_hexes_to_the_nearest_24_33_capable_dump", 0) / n) if n else None
            orders = {k.split("/")[1]: v for k, v in t.items() if k.startswith("order/")}
            out.append(
                f"  {r['seed']:>6} {side:<7} {t.get('segments', 0):>5} "
                f"{t.get('engineer_segments_on_a_LEGAL_lay_site', 0):>9} "
                f"{t.get('engineer_segments_on_an_AFFORDABLE_lay_site', 0):>7} "
                f"{t.get('engineer_segments_on_a_LEGAL_fort_site', 0):>9} "
                f"{t.get('engineer_segments_on_an_AFFORDABLE_fort_site', 0):>7} "
                f"{t.get('engineer_segments_standing_on_a_dump', 0):>7} "
                f"{t.get('engineer_segments_on_a_LEGAL_site_AND_a_dump', 0):>8} "
                f"{('%.1f' % mean) if mean is not None else '-':>6}  "
                f"{orders or 'NONE'}")
    out.append("")
    out.append("  dist = mean hexes from a lay-capable engineer on a legal site to the nearest")
    out.append("         friendly dump holding 24.33's 15 Stores + 15 Ammunition.")
    out.append("")
    out.append("  WHERE the price WAS payable, and by whom -- the r offset is from the El Alamein")
    out.append("  meridian, negative = west of it (the attacker's side):")
    for r in doc["results"]:
        if "ERROR" in r:
            continue
        s = r.get("affordable_sites") or {}
        if not s:
            out.append(f"    seed {r['seed']:>5}: no affordable site in the whole war, either side")
            continue
        for side, kinds in s.items():
            for kind, v in kinds.items():
                out.append(
                    f"    seed {r['seed']:>5}: {side} {kind:<4} {v['n']:>3} segments, "
                    f"GT{v['game_turns'][0]}-{v['game_turns'][1]}, r offset "
                    f"{v['r_offset_from_alamein_min_max']}, {v['east_of_alamein']} east of "
                    f"Alamein -- {', '.join(v['units'])}")
    return out


def neutrality_block(head, probe) -> list:
    """The probe wraps Policy.construction.  If that wrapper moved ONE die the autopsy above would
    be measuring a different war from the A/B, so the two runs' determinism signatures must agree
    seed for seed -- which also re-proves cross-process reproducibility at HEAD, the thing the 8.2
    gate's provenance note recorded as unsettled."""
    out = ["", "=" * 100,
           "VERIFICATION -- the probe is an observation, not an intervention",
           "=" * 100,
           f"  {'seed':>6} {'A/B (unprobed)':>18} {'autopsy (probed)':>18}  match"]
    ps = {r["seed"]: r.get("signature") for r in probe["results"]}
    ok = True
    for r in head["results"]:
        a, b = r.get("signature"), ps.get(r["seed"])
        ok &= a == b
        out.append(f"  {r['seed']:>6} {str(a):>18} {str(b):>18}  {'OK' if a == b else 'DIFFERS'}")
    out.append(f"  -> {'all seven byte-identical' if ok else 'A SIGNATURE MOVED -- the autopsy is not measuring the A/B war'}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="scratchpad/gate81c")
    args = ap.parse_args()
    d = args.dir

    lines: list = list(PROVENANCE)
    cb, ch = load(d, "census_BASE.json"), load(d, "census_HEAD.json")
    if cb and ch:
        lines += census_block(cb, ch) + throughput_block(ch)
    ab, ah = load(d, "ab_BASE.json"), load(d, "ab_HEAD.json")
    if ab and ah:
        lines += ab_block(ab, ah)
    au = load(d, "probe.json")
    if au:
        lines += autopsy_block(au)
    if au and ah:
        lines += neutrality_block(ah, au)
    txt = "\n".join(lines)
    print(txt)
    with open(os.path.join(d, "REPORT.txt"), "w") as f:
        f.write(txt + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
