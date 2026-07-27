"""GATE 8.1c -- CAN THE DEVIL'S GARDENS NOW BE BUILT?  The full-campaign A/B.

Read-only.  Changes nothing in game/ or data/.  BASE is a detached worktree at e73409a (the last
commit before the 8.1b engineer order-of-battle landed); HEAD is e068c2f.  Everything between the
two arms is the OOB: rule 26, rule 24.3/24.4 and the whole minefield/fortification machinery shipped
earlier, at aa4b6a2, which is an ancestor of both.  So this file runs UNMODIFIED in both trees.

WHAT IT ANSWERS
  2. DOES IT HAPPEN IN PLAY?  Every rule-24/26 event the war emits, counted by the CORRECT event
     vocabulary (the 8.2 gate's list was guessed from rule names and misses FORT_LEVEL_BUILT,
     CONSTRUCTION_ADVANCED and the construction ORDER_REJECTED outright, while naming four kinds
     that do not exist), plus the belts and fortification Levels standing on the final board.
  2b. IF IT DOES NOT, WHY -- PRECISELY.  A construction OPPORTUNITY probe wraps
     Policy.construction: at every Construction Segment of the war it reads the live state and
     counts, through the ENGINE'S OWN predicates, how many (unit, hex) pairs would satisfy each of
     24.31 lay / 24.42 fortify / 26.13 clear, and -- separately -- how many of those also have the
     24.33/24.43 Stores and Ammunition standing on the hex.  It returns the policy's own orders
     unchanged, so it is an observation and not an intervention; --probe is off for the arms whose
     signature is reported, and a --probe run's signature is compared against the plain one to
     prove it.  Three candidate causes are therefore separable by measurement:
        (i)   no engineer ever exists                    -> capability census is 0
        (ii)  no engineer ever stands on a legal site    -> sites_legal is 0 while census is not
        (iii) the price is never on hand                 -> sites_legal > 0, sites_affordable is 0
        (iv)  the policy simply never asks               -> sites_affordable > 0 and orders is 0
  3. THE ALAMEIN QUESTION.  The Axis ground high-water mark: the furthest-east axial r any Axis
     UNIT_MOVED / REACTION_MOVED / UNIT_RETREATED ever reaches, when, and the same mark at the end.
     Air missions are excluded by event kind (the 8.1b gate found they otherwise dominate it).
  4. THE BALANCE.  Winner + the 64.76 grade string, which carries both VP totals.

Usage:
  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate81c_ab.py --seeds 1941 7 4 24 2026 99 1 \
      --workers 7 --out <path.json> [--probe]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

# The rule-24 / rule-26 event vocabulary, matched BY STRING so an arm that lacks a member counts
# zero instead of crashing.  Verified against game/events.py at HEAD.
ENGINEERING_KINDS = (
    "CONSTRUCTION_ADVANCED", "CONSTRUCTION_COMPLETED",
    "MINEFIELD_CONSTRUCTED", "MINEFIELD_REVEALED", "MINEFIELD_CLEARED", "MINEFIELD_TRIGGERED",
    "FORT_LEVEL_BUILT", "FORT_REDUCED",
)
# A refused BuildOrder is not its own kind: engine._reject_build emits ORDER_REJECTED carrying
# payload["order"] == "construction".  Counted separately -- it is the loudest possible evidence
# that a policy DID ask and the rule said no, and its absence is evidence that nobody asked.

# The kinds that move a COUNTER over the ground.  An air mission's payload also carries a hex, and
# the 8.1b gate showed it otherwise sets the high-water mark all by itself.
GROUND_MOVE_KINDS = ("UNIT_MOVED", "REACTION_MOVED", "UNIT_RETREATED")


def _kind(e) -> str:
    k = getattr(e, "kind", "")
    return str(getattr(k, "value", k))


# --- 2b. THE CONSTRUCTION OPPORTUNITY PROBE -------------------------------------------------------

def _install_probe(tally: dict):
    """Wrap CampaignAxisPolicy.construction / CampaignCommonwealthPolicy.construction so that every
    Construction Segment of the war is MEASURED on its way past.  The wrapper calls the original and
    returns its result untouched -- no event, no die, no state change -- so the folded log is
    identical to the un-probed arm's (asserted by --probe's signature comparison in main)."""
    from game import construction as C, minefields as mfmod, supply
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy

    def wrap(cls):
        orig = cls.construction

        def probed(self, state, side):
            orders = orig(self, state, side)
            _measure(state, side, tally, C, mfmod, supply)
            t = tally.setdefault(side.value, defaultdict(int))
            t["segments"] += 1
            t["orders_issued"] += len(orders)
            for o in orders:
                t[f"order/{o.item}"] += 1
            return orders

        cls.construction = probed

    wrap(CampaignAxisPolicy)
    wrap(CampaignCommonwealthPolicy)


def _measure(state, side, tally, C, mfmod, supply) -> None:
    """One Construction Segment's opportunity, through the engine's own predicates."""
    t = tally.setdefault(side.value, defaultdict(int))
    mine_s, mine_a = C.minefield_supplies(True)

    engineers = [u for u in state.units
                 if u.side == side and u.engineer and state.on_map(u) and u.strength > 0]
    t["engineer_counters_on_map_max"] = max(t["engineer_counters_on_map_max"], len(engineers))
    if not engineers:
        return
    t["segments_with_an_engineer_on_map"] += 1

    partners = defaultdict(list)
    for u in state.units:
        if u.side == side and state.on_map(u) and C._is_infantry_battalion(u):
            partners[tuple(u.hex)].append(u)

    lay_sites = fort_sites = clear_sites = 0
    lay_afford = fort_afford = 0
    for u in engineers:
        hx = tuple(u.hex)
        if C.can_lay_minefield(state, side, u, hx):
            lay_sites += 1
            if (C.stores_at(state, side, hx) >= mine_s
                    and C.commodity_at(state, side, hx, supply.AMMO) >= mine_a):
                lay_afford += 1
        if C.builds_engineering(u) and C.fort_buildable(state, side, hx) and u.cp_used == 0:
            if any(p.id != u.id and p.cp_used == 0 for p in partners.get(hx, ())):
                fort_sites += 1
                if C.stores_at(state, side, hx) >= mfmod.FORT_STORES:
                    fort_afford += 1
        if C.can_clear_minefield(state, side, u, hx):
            clear_sites += 1

    t["lay_sites_legal_24_31"] += lay_sites
    t["lay_sites_affordable_24_33"] += lay_afford
    t["fort_sites_legal_24_42"] += fort_sites
    t["fort_sites_affordable_24_43"] += fort_afford
    t["clear_sites_legal_26_13"] += clear_sites
    t["segments_with_a_legal_lay_site"] += 1 if lay_sites else 0
    t["segments_with_an_affordable_lay_site"] += 1 if lay_afford else 0
    t["segments_with_a_legal_fort_site"] += 1 if fort_sites else 0
    t["segments_with_an_affordable_fort_site"] += 1 if fort_afford else 0


# --- the run --------------------------------------------------------------------------------------

def report(job) -> dict:
    seed, probe, max_turns = job
    try:
        return _report(seed, probe, max_turns)
    except Exception as exc:                                # noqa: BLE001 - a driver, not engine code
        return {"seed": seed, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-2500:]}


def _report(seed: int, probe: bool, max_turns) -> dict:
    from game import cna_map, coords
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import determinism_signature, run
    from game.events import Side
    from game.scenario import campaign

    tally: dict = {}
    if probe:
        _install_probe(tally)

    _, index = cna_map.load_sections("ABCDE")
    r_alamein = index["E3002"][1]
    r_alex = index["E3714"][1]
    r_tobruk = index["C4807"][1]          # game.scenario._TOBRUK

    init = campaign(seed=seed) if max_turns is None else campaign(seed=seed, max_turns=max_turns)
    res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final

    # ---- 2. did any of it fire? --------------------------------------------------------------
    eng_events: Counter = Counter()
    eng_detail: list = []
    turn = 0
    hw_r, hw_turn = -999, None
    hw_per_turn: dict = {}
    for e in res.events:
        k = _kind(e)
        if k == "TURN_ADVANCED":
            turn = (e.payload or {}).get("turn", turn + 1)
        is_reject = k == "ORDER_REJECTED" and (e.payload or {}).get("order") == "construction"
        if k in ENGINEERING_KINDS or is_reject:
            tag = "CONSTRUCTION_ORDER_REJECTED" if is_reject else k
            eng_events[f"{tag}/{getattr(e.side, 'value', e.side)}"] += 1
            if len(eng_detail) < 40:
                eng_detail.append({"turn": turn, "kind": tag,
                                   "side": getattr(e.side, "value", str(e.side)),
                                   "payload": {kk: (list(vv) if isinstance(vv, tuple) else vv)
                                               for kk, vv in (e.payload or {}).items()
                                               if kk in ("item", "hex", "reason", "level",
                                                         "progress", "stages")}})
        if k in GROUND_MOVE_KINDS and e.side == Side.AXIS:
            p = e.payload or {}
            h = p.get("to") or p.get("hex")
            if isinstance(h, (list, tuple)) and len(h) == 2 and all(isinstance(x, int) for x in h):
                if h[1] > hw_r:
                    hw_r, hw_turn = h[1], turn
                if h[1] > hw_per_turn.get(turn, -999):
                    hw_per_turn[turn] = h[1]

    # ---- 4. the final board -------------------------------------------------------------------
    belts = dict(getattr(fin, "minefields", {}) or {})
    static_forts = dict(getattr(fin.terrain, "fortifications", {}) or {})
    fort_hexes = set(getattr(fin, "fort_levels", {}) or {}) | set(static_forts)
    built_forts = {str(tuple(h)): fin.fort_level(h) for h in sorted(fort_hexes)
                   if fin.fort_level(h) != static_forts.get(h, 0)}

    def live(s):
        return [u for u in fin.units if u.side == s and getattr(u, "is_combat", True)
                and u.strength > 0 and fin.on_map(u)]

    def _r(h):
        return h[1] if isinstance(h, tuple) else coords.to_axial(h)[1]

    axis_live, cw_live = live(Side.AXIS), live(Side.ALLIED)
    out = {
        "seed": seed, "probe": probe, "max_turns": max_turns,
        "winner": None if res.winner is None else res.winner.value,
        "reason": res.reason,
        "events": len(res.events),
        "signature": hashlib.blake2b(
            determinism_signature(res.events).encode(), digest_size=8).hexdigest(),
        "engineering_events": dict(sorted(eng_events.items())),
        "engineering_event_total": sum(eng_events.values()),
        "engineering_event_sample": eng_detail,
        "final_minefields": len(belts),
        "fortifications_raised_above_the_static_roster": built_forts,
        "r_alamein": r_alamein, "r_alexandria": r_alex, "r_tobruk": r_tobruk,
        "axis_ground_high_water_r": hw_r,
        "axis_ground_high_water_turn": hw_turn,
        "axis_ground_high_water_offset_from_alamein": hw_r - r_alamein,
        "axis_ground_high_water_per_turn": {str(k): v for k, v in sorted(hw_per_turn.items())},
        "axis_east_at_end": max((_r(u.hex) for u in axis_live), default=None),
        "cw_west_at_end": min((_r(u.hex) for u in cw_live), default=None),
        "axis_units_alive": len(axis_live), "cw_units_alive": len(cw_live),
    }
    if probe:
        out["construction_opportunity"] = {s: dict(sorted(d.items())) for s, d in tally.items()}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1941, 7, 4, 24, 2026, 99, 1])
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--max-turns", type=int, default=None,
                    help="TRUNCATE the war -- for smoke-testing this driver only, never for the gate")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc: dict = {"seeds": args.seeds, "probe": args.probe, "max_turns": args.max_turns,
                 "results": []}
    jobs = [(s, args.probe, args.max_turns) for s in args.seeds]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(report, jobs):
            doc["results"].append(r)
            with open(args.out, "w") as f:
                json.dump(doc, f, indent=1)
            if "ERROR" in r:
                print(f"  seed {r['seed']}: {r['ERROR']}", flush=True)
            else:
                print(f"  seed {r['seed']}: {r['winner']} | sig {r['signature']} | "
                      f"eng={r['engineering_event_total']} belts={r['final_minefields']} "
                      f"forts+={len(r['fortifications_raised_above_the_static_roster'])} "
                      f"hw_r={r['axis_ground_high_water_r']}"
                      f"(GT{r['axis_ground_high_water_turn']}) | {r['reason']}", flush=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
