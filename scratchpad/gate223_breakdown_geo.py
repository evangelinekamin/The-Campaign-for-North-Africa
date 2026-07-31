"""GATE 22.3, SUPPLEMENT -- WHERE DOES THE BROKEN POOL ACTUALLY LIE?

If rule 22.3 recovers little, the diagnosis has to be precise, and there are only two candidate
causes: either almost nothing breaks down, or almost nothing that breaks down is STANDING on one of
the eight Major-Facility hexes when the Repair Phase comes round.  21.6 TOWING -- the book's own
mechanism for getting a wreck to a facility -- is named debt in game/repair.py's docstring and no
code anywhere implements it, so a counter can only ever use a facility if it breaks down while
already sitting on one.  This probe measures that directly, on the HEAD tree.

For every VEHICLE_BROKE_DOWN / TRUCK_BROKE_DOWN in the war it re-folds the log to the moment of the
event and records the hex the breakage happened in: how many points broke ON a Major-Facility hex,
how many broke within one/two/three hexes of one (i.e. how far towing would have to reach), and the
whole east-west distribution.  Read-only; changes nothing.

  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate223_breakdown_geo.py --seeds 1941 7 4 --out x.json
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor


def _kind(e) -> str:
    k = getattr(e, "kind", "")
    return str(getattr(k, "value", k))


def _side(e) -> str:
    s = getattr(e, "side", "")
    return str(getattr(s, "value", s))


def report(seed: int) -> dict:
    try:
        return _report(seed)
    except Exception as exc:                                # noqa: BLE001 - a driver, not engine code
        return {"seed": seed, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-3000:]}


def _report(seed: int) -> dict:
    t0 = time.time()
    from game import repair
    from game.apply import apply
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import run
    from game.hexmap import distance
    from game.scenario import campaign

    init = campaign(seed=seed)
    fac = repair.major_facility_hexes(init)
    res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())

    on_facility: Counter = Counter()          # "cls/side" -> points that broke ON a facility hex
    total: Counter = Counter()
    by_ring: Counter = Counter()              # "cls/side/dN" -> points that broke N hexes from one
    by_r: Counter = Counter()                 # "cls/side" -> {r: points}, flattened as "cls/side/r"
    # [22.34a] is only reachable while a facility's Major City has been bombed or barraged BELOW its
    # printed Fortification Level.  If no facility hex ever loses a level, the whole modifier -- and
    # the die-7/die-8 rows of the [22.8] Major column with it -- is unreachable in the campaign.
    fort_min = {str(list(h)): init.fort_level(h) for h in fac}
    fort_base = {str(list(h)): init.terrain.fortifications.get(h, 0) for h in fac}

    st = init
    for e in res.events:
        k = _kind(e)
        if k in ("FORT_REDUCED", "FORT_LEVEL_BUILT"):
            for h in fac:                                   # cheap: only on the rare fort events
                key = str(list(h))
                fort_min[key] = min(fort_min[key], st.fort_level(h))
        if k in ("VEHICLE_BROKE_DOWN", "TRUCK_BROKE_DOWN"):
            p = e.payload or {}
            amt = p.get("amount", 0)
            cls = "toe" if k == "VEHICLE_BROKE_DOWN" else "truck"
            key = f"{cls}/{_side(e)}"
            obj = (st.unit(p["unit_id"]) if cls == "toe" else st.truck(p["truck_id"]))
            hx = getattr(obj, "hex", None)
            total[key] += amt
            if hx is not None:
                by_r[f"{key}/{hx[1]}"] += amt
                d = min((distance(hx, f) for f in fac), default=999)
                by_ring[f"{key}/d{min(d, 6)}"] += amt
                if d == 0:
                    on_facility[key] += amt
        st = apply(st, e)

    for h in fac:                                           # final sample, in case the last event moved it
        key = str(list(h))
        fort_min[key] = min(fort_min[key], res.final.fort_level(h))
    return {"seed": seed, "seconds": round(time.time() - t0, 1),
            "facility_hexes": sorted(list(h) for h in fac),
            "facility_fort_baseline": fort_base,
            "facility_fort_min_reached": fort_min,
            "die_modifier_22_34a_ever_reachable": any(
                fort_min[k] < fort_base[k] for k in fort_base),
            "broken_total": dict(sorted(total.items())),
            "broken_on_a_facility_hex": dict(sorted(on_facility.items())),
            "broken_by_ring_from_nearest_facility": dict(sorted(by_ring.items())),
            "broken_by_hex_r": dict(sorted(by_r.items()))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1941, 7, 4])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    doc: dict = {"seeds": args.seeds, "results": []}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(report, args.seeds):
            doc["results"].append(r)
            with open(args.out, "w") as f:
                json.dump(doc, f, indent=1)
            print(f"  seed {r['seed']}: on_facility={r.get('broken_on_a_facility_hex')} "
                  f"total={r.get('broken_total')} {r.get('ERROR','')}", flush=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
