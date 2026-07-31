"""GATE 8.1c-OOB (8.1d), THE MECHANISM PROBE -- WHERE DID THE VICTORY POINTS GO?

Read-only.  Changes NOTHING in game/ or data/.  Runs UNMODIFIED in both trees.

WHY THIS FILE EXISTS.  The A/B (gate81d_ab.py) found the Axis 64.76 total falling on all seven
seeds, and then found that its 64.73 GEOGRAPHIC half did not move at all -- the Axis still ends
every campaign holding Tobruk, Benghazi and Giarabub, and the seven-seed mean geographic score is
flat.  So the entire shift lives in the other term the tally adds, [64.74] UNUSED Replacement Points,
which today scores the AXIS INFANTRY POOL ONLY (campaign_victory._unused_replacement_points_64_74:
the Commonwealth scores zero replacement VP under the 2026-07-24 owner ruling).  A shift there is a
shift in HOW MUCH OF ITS OWN REPLACEMENT POOL THE AXIS BURNED, not in who holds the desert.

This probe reads that spend off the log directly -- every UNIT_REBUILT's pool_key and cost, which is
the exact quantity `replacements.unused_replacement_vp` subtracts -- together with the casualty
stream that drives it (STEP_LOST by side) and the elimination count.  It also answers the sanity half
of the gate that the A/B could only count in aggregate: WHICH counters stopped moving, by name.

Usage:
  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate81d_mechanism.py --seeds 1941 7 4 24 2026 99 1 \
      --workers 7 --out <path.json>
"""
from __future__ import annotations

import argparse
import json
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

# The five counters BASE fought as combat infantry and HEAD does not: the four [23.11] "(ENG)"
# Engineer Battalions and the 1st Libyan Division HQ^E, whose id is the same in both trees.
REROLED = ("IT-64---Cat-(ENG)", "IT-204---4CCNN-(ENG)", "IT-63-Cir-(ENG)", "IT-62-Marm-(ENG)",
           "IT-1-Libyan")


def _kind(e) -> str:
    k = getattr(e, "kind", "")
    return str(getattr(k, "value", k))


def _side(e) -> str:
    s = getattr(e, "side", "")
    return str(getattr(s, "value", s))


def report(job) -> dict:
    seed, max_turns = job
    try:
        return _report(seed, max_turns)
    except Exception as exc:                                # noqa: BLE001 - a driver, not engine code
        return {"seed": seed, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-3000:]}


def _report(seed: int, max_turns) -> dict:
    from game import replacements
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import run
    from game.events import Side
    from game.scenario import campaign

    init = campaign(seed=seed) if max_turns is None else campaign(seed=seed, max_turns=max_turns)
    res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final
    by_id = {u.id: u for u in init.units}

    rebuilt_cost: Counter = Counter()
    rebuilt_n: Counter = Counter()
    steps_lost: Counter = Counter()
    moved: set = set()
    for e in res.events:
        k, p = _kind(e), (e.payload or {})
        if k == "UNIT_REBUILT":
            pk, c = p.get("pool_key"), p.get("cost", 0)
            if pk:
                rebuilt_cost[pk] += c
                rebuilt_n[pk] += 1
        elif k == "STEP_LOST":
            u = by_id.get(p.get("unit_id"))
            if u is not None:
                steps_lost[u.side.value] += p.get("amount", 0)
        elif k == "UNIT_MOVED" and p.get("unit_id"):
            moved.add(p["unit_id"])

    used = {}
    for pk, c in rebuilt_cost.items():
        sv, cls = pk.split("/", 1)
        used[(sv, cls)] = used.get((sv, cls), 0) + c
    ax74 = replacements.unused_replacement_vp(Side.AXIS, used)
    cw74 = replacements.unused_replacement_vp(Side.ALLIED, used)

    def alive(s):
        return [u for u in fin.units if u.side == s and getattr(u, "is_combat", True)
                and u.strength > 0]

    # WHO STOPPED MOVING, by name.  The counters this slice re-roled, and every HQ it seeded.
    frozen = []
    for uid in REROLED:
        u0 = by_id.get(uid)
        if u0 is None:
            continue
        u1 = fin.unit(uid)
        frozen.append({"id": uid, "is_combat": bool(u0.is_combat),
                       "engineer": getattr(u0, "engineer", ""),
                       "moved_at_least_once": uid in moved,
                       "hex_at_setup": list(u0.hex) if init.on_map(u0) else None,
                       "hex_at_end": list(u1.hex) if u1 is not None and fin.on_map(u1) else None,
                       "strength_at_end": None if u1 is None else u1.strength})

    never_by_role: Counter = Counter()
    for u in init.units:
        if u.id in moved:
            continue
        role = ("hq_engineer" if getattr(u, "engineer", "") == "HQ_ENGINEER"
                else "hq" if (not u.is_combat and getattr(u, "org_type", ""))
                else "non_combat" if not u.is_combat else "combat")
        never_by_role[f"{u.side.value}/{role}"] += 1

    return {
        "seed": seed,
        "winner": None if res.winner is None else res.winner.value,
        "reason": res.reason,
        "replacement_spend_by_pool": dict(sorted(rebuilt_cost.items())),
        "rebuilds_by_pool": dict(sorted(rebuilt_n.items())),
        "unused_replacement_vp_64_74": {"AXIS": ax74, "ALLIED": cw74},
        "steps_lost_by_side": dict(sorted(steps_lost.items())),
        "axis_combat_counters_alive": len(alive(Side.AXIS)),
        "cw_combat_counters_alive": len(alive(Side.ALLIED)),
        "axis_combat_counters_at_setup": len([u for u in init.units
                                              if u.side == Side.AXIS and u.is_combat]),
        "cw_combat_counters_at_setup": len([u for u in init.units
                                            if u.side == Side.ALLIED and u.is_combat]),
        "the_five_reroled_counters": frozen,
        "never_moved_by_role": dict(sorted(never_by_role.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1941, 7, 4, 24, 2026, 99, 1])
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--max-turns", type=int, default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc: dict = {"seeds": args.seeds, "max_turns": args.max_turns, "results": []}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(report, [(s, args.max_turns) for s in args.seeds]):
            doc["results"].append(r)
            with open(args.out, "w") as f:
                json.dump(doc, f, indent=1)
            if "ERROR" in r:
                print(f"  seed {r['seed']}: {r['ERROR']}", flush=True)
            else:
                print(f"  seed {r['seed']}: 64.74 AXIS {r['unused_replacement_vp_64_74']['AXIS']} | "
                      f"spend {r['replacement_spend_by_pool']} | steps lost "
                      f"{r['steps_lost_by_side']} | {r['reason']}", flush=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
