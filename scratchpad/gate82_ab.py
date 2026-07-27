"""GATE 8.2 -- THE A/B: does rule 26 / 24.3 / 24.4 change a real 111-turn campaign?

Read-only.  Runs the full campaign for a list of seeds and answers the gate's questions 2, 3 and 4:

  2. DOES IT HAPPEN IN PLAY?  Counts every MINEFIELD_* / FORTIFICATION event the war emits, the
     belts and fort levels standing on the final board, and -- the upstream question -- how many
     units capable of LAYING one (24.31's EBn/ECoy/CHQ-E) or of CLEARING/ESCORTING through one
     (26.24's engineer, incl. 23.15's Scorpions) ever appear on the map at all.
  3. THE BALANCE.  Winner + the 64.76 grade string (which carries both VP totals).
  4. SANITY.  Belts nobody can cross or clear, hexes carrying both a fort and a belt (24.46), units
     with no legal exit, and the fortification-level census.

Written so the SAME file runs unmodified in the pre-slice worktree (7b2c2cc, where
GameState.minefields, game.minefields and the MINEFIELD_* EventKinds do not exist) and at HEAD:
every HEAD-only symbol is reached through getattr/string comparison, so the BASE arm reports zero
rather than crashing.

Usage:
  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate82_ab.py --seeds 1941 7 4 24 2026 99 1 \
      --workers 7 --out <path.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

# The rule-26 / 24.3 / 24.4 event vocabulary, matched BY STRING so the base arm (which has none of
# these EventKind members) runs the identical code path and simply counts zero.
ENGINEERING_KINDS = ("MINEFIELD_CONSTRUCTED", "MINEFIELD_REVEALED", "MINEFIELD_CLEARED",
                     "MINEFIELD_TRIGGERED", "FORTIFICATION_BUILT", "FORTIFICATION_CONSTRUCTED",
                     "PROJECT_STARTED", "PROJECT_COMPLETED", "CONSTRUCTION_STARTED",
                     "CONSTRUCTION_COMPLETED")


def tmap_of(state):
    return state.terrain


def _kind(e) -> str:
    k = getattr(e, "kind", "")
    return str(getattr(k, "value", k))


def report(seed: int) -> dict:
    try:
        return _report(seed)
    except Exception as exc:                                # noqa: BLE001 - a driver, not engine code
        return {"seed": seed, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-2000:]}


def _report(seed: int) -> dict:
    from game import coords
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import determinism_signature, run
    from game.events import Side
    from game.hexmap import neighbors
    from game.movement import step_cost
    from game.scenario import campaign

    init = campaign(seed=seed)
    res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final

    # ---- 2. DID ANY OF IT FIRE? -------------------------------------------------------------
    eng_events: Counter = Counter()
    all_kinds: Counter = Counter()
    mine_sites: Counter = Counter()
    for e in res.events:
        k = _kind(e)
        all_kinds[k] += 1
        if k in ENGINEERING_KINDS:
            eng_events[f"{k}/{getattr(e.side, 'value', e.side)}"] += 1
            h = (e.payload or {}).get("hex")
            if isinstance(h, (list, tuple)) and len(h) == 2:
                mine_sites[str(tuple(h))] += 1

    # ---- 2b. THE UPSTREAM GATE: does a unit that COULD build/clear one ever exist? -----------
    # Walked over EVERY unit the war ever contains (setup + every reinforcement that arrived),
    # not just the survivors, so a Scorpion that landed and died still counts.
    # GameState.units retains eliminated counters (live() has to filter strength>0), and arriving
    # reinforcements are appended to it, so final ∪ setup IS every unit the war contained.
    ever = list(fin.units)
    ids = {u.id for u in ever}
    for st_units in (init.units,):
        for u in st_units:
            if u.id not in ids:
                ever.append(u)
                ids.add(u.id)

    eng_census: Counter = Counter()
    for u in ever:
        cap = getattr(u, "engineer", None)
        if cap:
            eng_census[f"{u.side.value}/{cap}"] += 1

    try:
        from game import minefields as mfmod
        lay_capable = sum(1 for u in ever
                          if getattr(u, "engineer", None) in (mfmod.GENERAL_ENGINEER,
                                                              mfmod.HQ_ENGINEER))
        clear_capable = sum(1 for u in ever if mfmod.is_engineer(u))
    except Exception:                                        # noqa: BLE001 - base arm has no module
        lay_capable, clear_capable = None, None

    # ---- 4. THE FINAL BOARD -------------------------------------------------------------------
    belts = dict(getattr(fin, "minefields", {}) or {})
    # fort_levels is the DYNAMIC overlay (41.37 batter / 24.4 build); terrain.fortifications is the
    # static Major-City roster the 8.1a slice wired.  fort_level() folds the two, so read it.
    fort_hexes = set(getattr(fin, "fort_levels", {}) or {}) | set(
        getattr(tmap_of(fin), "fortifications", {}) or {})
    forts = {str(tuple(h)): fin.fort_level(h) for h in sorted(fort_hexes)}
    static_forts = dict(getattr(tmap_of(fin), "fortifications", {}) or {})
    built_forts = {str(tuple(h)): fin.fort_level(h) for h in sorted(fort_hexes)
                   if fin.fort_level(h) != static_forts.get(h, 0)}

    def live(side):
        return [u for u in fin.units if u.side == side and getattr(u, "is_combat", True)
                and u.strength > 0 and fin.on_map(u)]

    axis_live, cw_live = live(Side.AXIS), live(Side.ALLIED)
    tmap = fin.terrain

    stuck = []
    for u in axis_live + cw_live:
        h = u.hex if isinstance(u.hex, tuple) else coords.to_axial(u.hex)
        if not any(tmap.exists(nb) and step_cost(tmap, h, nb, u.mobility) is not None
                   for nb in neighbors(h)):
            stuck.append({"unit": u.id, "side": u.side.value, "mob": u.mobility.value,
                          "hex": list(h)})

    def _r(h):
        return h[1] if isinstance(h, tuple) else coords.to_axial(h)[1]

    return {
        "seed": seed,
        "winner": None if res.winner is None else res.winner.value,
        "reason": res.reason,                                 # carries the 64.76 grade + both VP
        "events": len(res.events),
        "signature": hashlib.blake2b(
            determinism_signature(res.events).encode(), digest_size=8).hexdigest(),
        "engineering_events": dict(sorted(eng_events.items())),
        "engineering_event_total": sum(eng_events.values()),
        "engineering_sites": mine_sites.most_common(12),
        "engineer_capability_census_all_units_ever": dict(sorted(eng_census.items())),
        "units_that_could_LAY_a_belt_24_31": lay_capable,
        "units_that_could_CLEAR_or_ESCORT_26_24": clear_capable,
        "final_minefields": len(belts),
        "final_minefield_detail": [
            {"hex": str(tuple(h)), "side": getattr(m.side, "value", str(m.side)),
             "real": getattr(m, "real", None), "revealed": getattr(m, "revealed", None)}
            for h, m in list(belts.items())[:20]],
        "final_fortifications": forts,
        "fortifications_raised_above_the_static_roster": built_forts,
        "fort_level_census": dict(Counter(forts.values())),
        "axis_units_alive": len(axis_live), "cw_units_alive": len(cw_live),
        "axis_east_at_end": max((_r(u.hex) for u in axis_live), default=None),
        "cw_west_at_end": min((_r(u.hex) for u in cw_live), default=None),
        "stuck_units": stuck,
        "kind_total": len(all_kinds),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1941, 7, 4, 24, 2026, 99, 1])
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc: dict = {"seeds": args.seeds, "results": []}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(report, args.seeds):
            doc["results"].append(r)
            with open(args.out, "w") as f:
                json.dump(doc, f, indent=1)
            if "ERROR" in r:
                print(f"  seed {r['seed']}: {r['ERROR']}", flush=True)
            else:
                print(f"  seed {r['seed']}: {r['winner']} | sig {r['signature']} | "
                      f"eng_events={r['engineering_event_total']} "
                      f"belts={r['final_minefields']} lay={r['units_that_could_LAY_a_belt_24_31']} "
                      f"clear={r['units_that_could_CLEAR_or_ESCORT_26_24']} | {r['reason']}",
                      flush=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
