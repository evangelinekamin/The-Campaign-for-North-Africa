"""GATE 8.1c, QUESTION 2b -- THE AUTOPSY.  If no belt is laid, WHICH clause refuses?

Read-only.  Changes nothing in game/ or data/.  Runs unmodified in both arms.

gate81c_ab.py establishes the negative: zero belts and zero fortification Levels over seven full
111-turn campaigns per arm.  This takes the refusal apart.  A wrapper around
Policy.construction MEASURES every Construction Segment of the war on its way past and returns the
policy's own orders untouched -- no event, no die, no state change -- so the folded log is identical
to the un-probed arm's.  That is not asserted, it is PROVEN: this driver reports the same
determinism signature gate81c_ab.py reports, and the two must match seed for seed.

Rule 24.31 gives four independent ways for a belt not to exist, and they are separable:

  (i)   NO ENGINEER EXISTS.                 -> lay-capable census is 0.  (This is what the 8.2 gate
                                               found and what the 8.1b OOB pass fixed.)
  (ii)  NO ENGINEER STANDS ON A LEGAL SITE. -> engineer-segments on a legal 24.31 site is 0.
  (iii) THE 24.33 PRICE IS NEVER ON HAND.   -> legal sites > 0 but affordable sites is 0.  Taken
                                               further here, because 24.33's price is read through
                                               24.13's "on hand IN THE HEX": (a) the engineer never
                                               stands on a dump at all, (b) he does but it is too
                                               thin, or (c) rich dumps exist and are far away.
  (iv)  THE POLICY NEVER ASKS.              -> affordable sites > 0 and no BuildOrder is issued.
                                               Counted directly, by item.

The same split runs for 24.43's 30 Stores (fortifications), which need no Ammunition and so can come
apart differently.  Distances are hexmap.distance -- the engine's own metric.

PERFORMANCE NOTE, because it changes no number: the dumps are indexed by hex ONCE per Construction
Segment rather than rescanning state.supplies per engineer (construction.stores_at's own loop).  The
filter is construction._construction_dumps' filter verbatim, so the quantities are identical to what
the engine would charge; only the number of times the list is walked differs.

Usage:
  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate81c_probe.py --seeds 4 1941 24 --workers 3 \
      --out <path.json> [--max-turns N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor


def _install(tally: dict, sites: dict):
    from game import cna_map, construction as C, minefields as mfmod, wells
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.hexmap import distance

    mine_s, mine_a = C.minefield_supplies(True)
    fort_s = mfmod.FORT_STORES
    # WHERE an affordable site is, in the one coordinate the Alamein question is asked in: the
    # axial r offset from El Alamein (index 1 runs east-west; E3002 is the Alamein meridian).
    _, index = cna_map.load_sections("ABCDE")
    r_alamein = index["E3002"][1]

    def index_dumps(state, side):
        """construction._construction_dumps' filter, applied once and bucketed by hex."""
        by_hex: dict = defaultdict(lambda: [0, 0])          # hex -> [stores, ammo]
        rich_mine, rich_fort = [], []
        for s in state.supplies:
            if s.side != side or s.is_dummy or s.air_dump or wells.is_water_source(s):
                continue
            h = tuple(s.hex)
            b = by_hex[h]
            b[0] += s.stores
            b[1] += s.ammo
            if s.stores >= mine_s and s.ammo >= mine_a:
                rich_mine.append(h)
            if s.stores >= fort_s:
                rich_fort.append(h)
        return by_hex, rich_mine, rich_fort

    def measure(state, side, orders):
        t = tally.setdefault(side.value, defaultdict(int))
        t["segments"] += 1
        for o in orders:
            t[f"order/{o.item}"] += 1

        engineers = [u for u in state.units
                     if u.side == side and state.on_map(u) and u.strength > 0
                     and C.lays_minefield(u)]
        if not engineers:
            return
        t["segments_with_a_lay_capable_engineer_on_map"] += 1
        t["max_lay_capable_engineers_on_map"] = max(
            t["max_lay_capable_engineers_on_map"], len(engineers))

        by_hex, rich_mine, rich_fort = index_dumps(state, side)
        t["max_dumps_meeting_24_33_15S_15A_anywhere"] = max(
            t["max_dumps_meeting_24_33_15S_15A_anywhere"], len(rich_mine))
        t["max_dumps_meeting_24_43_30S_anywhere"] = max(
            t["max_dumps_meeting_24_43_30S_anywhere"], len(rich_fort))
        t["segments_with_a_24_33_capable_dump_SOMEWHERE"] += 1 if rich_mine else 0

        # 24.42's other half: an Infantry battalion at 3+ TOE on the same hex, CP unspent.
        partners: dict = defaultdict(int)
        for u in state.units:
            if u.side == side and state.on_map(u) and C._is_infantry_battalion(u) and u.cp_used == 0:
                partners[tuple(u.hex)] += 1

        for u in engineers:
            hx = tuple(u.hex)
            t["engineer_segments"] += 1
            here_s, here_a = by_hex.get(hx, (0, 0))
            on_a_dump = hx in by_hex
            t["engineer_segments_standing_on_a_dump"] += 1 if on_a_dump else 0
            t["best_stores_ever_under_an_engineer"] = max(
                t["best_stores_ever_under_an_engineer"], here_s)
            t["best_ammo_ever_under_an_engineer"] = max(
                t["best_ammo_ever_under_an_engineer"], here_a)
            if by_hex:
                d_any = min(distance(hx, h) for h in by_hex)
                t["sum_hexes_to_the_nearest_dump_of_ANY_richness"] += d_any
                t["n_for_that_any_mean"] += 1

            if C.can_lay_minefield(state, side, u, hx):
                t["engineer_segments_on_a_LEGAL_lay_site"] += 1
                t["engineer_segments_on_a_LEGAL_site_AND_a_dump"] += 1 if on_a_dump else 0
                if here_s >= mine_s and here_a >= mine_a:
                    t["engineer_segments_on_an_AFFORDABLE_lay_site"] += 1
                    sites.setdefault(side.value, []).append(
                        {"kind": "LAY", "gt": state.turn, "unit": u.id,
                         "r_offset_from_alamein": hx[1] - r_alamein})
                elif here_s >= mine_s:
                    t["short_of_AMMO_only"] += 1
                elif here_a >= mine_a:
                    t["short_of_STORES_only"] += 1
                else:
                    t["short_of_BOTH"] += 1
                if rich_mine:
                    d = min(distance(hx, h) for h in rich_mine)
                    t["sum_hexes_to_the_nearest_24_33_capable_dump"] += d
                    t["n_for_that_mean"] += 1
                    t["min_hexes_to_a_24_33_capable_dump_ever"] = (
                        d if t["n_for_that_mean"] == 1
                        else min(t["min_hexes_to_a_24_33_capable_dump_ever"], d))

            # 24.42 fortification, whose gates are different in every clause.
            if C.builds_engineering(u) and u.cp_used == 0 and C.fort_buildable(state, side, hx):
                if partners.get(hx, 0) - (1 if C._is_infantry_battalion(u) else 0) > 0:
                    t["engineer_segments_on_a_LEGAL_fort_site"] += 1
                    if here_s >= fort_s:
                        t["engineer_segments_on_an_AFFORDABLE_fort_site"] += 1
                        sites.setdefault(side.value, []).append(
                            {"kind": "FORT", "gt": state.turn, "unit": u.id,
                             "r_offset_from_alamein": hx[1] - r_alamein})
                else:
                    t["fort_site_legal_but_NO_INFANTRY_PARTNER"] += 1

    def wrap(cls):
        orig = cls.construction

        def probed(self, state, side):
            orders = orig(self, state, side)
            measure(state, side, orders)
            return orders

        cls.construction = probed

    wrap(CampaignAxisPolicy)
    wrap(CampaignCommonwealthPolicy)


def _summarise(rows: list) -> dict:
    """Where and when a site the 24.33/24.43 price WAS payable at stood -- the whole point of
    question 3, which cannot be answered by a count."""
    from collections import Counter
    out: dict = {}
    for kind in ("LAY", "FORT"):
        sub = [r for r in rows if r["kind"] == kind]
        if not sub:
            continue
        offs = [r["r_offset_from_alamein"] for r in sub]
        out[kind] = {
            "n": len(sub),
            "game_turns": [min(r["gt"] for r in sub), max(r["gt"] for r in sub)],
            "r_offset_from_alamein_min_max": [min(offs), max(offs)],
            "r_offset_histogram": dict(sorted(Counter(offs).items())),
            "units": dict(sorted(Counter(r["unit"] for r in sub).items())),
            "east_of_alamein": sum(1 for o in offs if o > 0),
            "within_5_hexes_of_the_alamein_meridian": sum(1 for o in offs if abs(o) <= 5),
        }
    return out


def report(job) -> dict:
    seed, max_turns = job
    try:
        tally: dict = {}
        sites: dict = {}
        _install(tally, sites)
        from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
        from game.engine import determinism_signature, run
        from game.scenario import campaign
        init = campaign(seed=seed) if max_turns is None else campaign(seed=seed,
                                                                     max_turns=max_turns)
        res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
        return {"seed": seed, "max_turns": max_turns, "reason": res.reason,
                "signature": hashlib.blake2b(
                    determinism_signature(res.events).encode(), digest_size=8).hexdigest(),
                "autopsy": {s: dict(sorted(d.items())) for s, d in tally.items()},
                "affordable_sites": {s: _summarise(v) for s, v in sites.items()}}
    except Exception as exc:                                # noqa: BLE001 - a driver
        return {"seed": seed, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-2500:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[4, 1941, 24])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-turns", type=int, default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc: dict = {"seeds": args.seeds, "max_turns": args.max_turns, "results": []}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(report, [(s, args.max_turns) for s in args.seeds]):
            doc["results"].append(r)
            with open(args.out, "w") as f:
                json.dump(doc, f, indent=1)
            print(f"  seed {r['seed']}: sig {r.get('signature', r.get('ERROR'))}", flush=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
