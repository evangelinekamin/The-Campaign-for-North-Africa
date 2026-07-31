"""GATE 8.1c-OOB (8.1d) -- WHAT THE FIFTEEN DIVISION HQs AND THE FOUR (ENG) COUNTERS BOUGHT.

Read-only.  Changes NOTHING in game/ or data/.  Runs UNMODIFIED in both trees -- BASE is the
detached worktree at a6c9700 (the last commit before the division-HQ pass), HEAD is 607b63c.  Every
symbol it touches (the [4.45] tree, Unit.assigned_to/org_type/is_combat, concentrate_formations,
organization.combat_size, combat_tables.org_size_shift, campaign_victory._occupier) shipped at
083f0dc or earlier, an ancestor of both, so the ONLY difference between the arms is the order of
battle.

THE ARMS, and why there are three rather than two.  BASE->HEAD moves two independent things at once:
the fourteen seeded HQ counters (plus the 1st Libyan role repair, which TOOK a phantom infantry
counter off the border) and the 23.11 (ENG) correction (which took four more off it).  A two-arm A/B
cannot say which of them did what, and the slice is asked for the (ENG) correction's own effect.  So
the third arm runs in the HEAD tree with ONLY the (ENG) correction backed out, at the point the OOB
is loaded:

    live     : nothing patched.
    eng_off  : the four (ENG) records' role is put back to the "infantry" BASE gave them.
    noop     : the SAME patch machinery installed with an identity transform.

`noop` is the neuter-proof and it is not optional.  A neuter that never reaches the caller measures
the un-neutered arm and reports it as a finding; the trap is recorded in tests/baselines.py and has
bitten this project twice.  Two independent checks are asserted here, in-process, and the run DIES
rather than report a number if either fails:
  (a) REACH -- game.oob's callers resolve `_load` through the module globals at call time
      (`_load(oob_file)` at oob.py:288, not a from-import), so rebinding game.oob._load reaches
      them.  The wrapper counts its own calls and counts the four target records as it sees them;
      zero of either is a dead patch, and _install raises.
  (b) INERTNESS -- the `noop` arm's determinism signature must equal the `live` arm's, byte for
      byte.  Compared in the report, not asserted here, because the two are separate processes.

WHAT IT ANSWERS
  1. FORMATIONS (dynamic half; the static census is gate81d_formations.py).  Every UNIT_ATTACHED /
     UNIT_DETACHED of the war, by side and by parent, plus the construction-segment rejects; and
     [15.53] Organization-Size firing, counted as the engine itself records it -- a COMBAT_RESOLVED
     payload carries attacker_size/defender_size ONLY when max(size) >= 2 (engine.py:5586) -- with
     the column shift re-derived through combat_tables.org_size_shift so "which side did it favour"
     is the chart's answer and not this file's.
  2. THE (ENG) CORRECTION.  City ownership over the whole war at 64.73 quality (the victory
     projection's own _occupier, i.e. a supplied combat unit), sampled at every Game-Turn boundary
     and reported as CHANGE POINTS, so Sidi Barrani and Sollum can be read turn by turn; the banked
     sets at GT30 and at the end; and the Axis ground high-water mark (r, and the turn it was set).
  3. THE BALANCE.  Winner and the full 64.76 grade string, which carries both VP totals.
  4. SANITY.  Units alive at the end by side, combats fought and surrenders by side, counters that
     never moved in 111 turns, and the fate of every HQ this slice seeded.  A side that cannot fight,
     a garrison that evaporates or a formation frozen in place shows up in these four.

Usage:
  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate81d_ab.py --seeds 1941 7 4 24 2026 99 1 \
      --arm live --workers 7 --out <path.json> [--max-turns N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

# The four counters the [4.44b] chart / the counter sheet tags "(ENG)" and the 23.11 correction
# flipped from combat infantry to Engineer.  Named by COUNTER STRING, which is the key both trees
# agree on; the role either side of the correction is likewise the literal both files carry.
ENG_COUNTERS = ("IT 64 - Cat (ENG)", "IT 204 - 4CCNN (ENG)",
                "IT 63 Cir (ENG)", "IT 62 Marm (ENG)")
ENG_ROLE_BEFORE = "infantry"
ENG_ROLE_AFTER = "engineer"

GROUND_MOVE_KINDS = ("UNIT_MOVED", "REACTION_MOVED", "UNIT_RETREATED")


def _kind(e) -> str:
    k = getattr(e, "kind", "")
    return str(getattr(k, "value", k))


def _side(e) -> str:
    s = getattr(e, "side", "")
    return str(getattr(s, "value", s))


# --- THE NEUTER, AND ITS PROOF --------------------------------------------------------------------

def _install(arm: str) -> dict:
    """Rebind game.oob._load.  Returns the live counter dict the caller asserts against."""
    from game import oob

    stats = {"calls": 0, "records_seen": 0, "targets_seen": 0, "targets_rewritten": 0}
    original = oob._load

    def wrapped(name: str):
        data = original(name)
        stats["calls"] += 1
        if isinstance(data, list):
            out = []
            for rec in data:
                stats["records_seen"] += 1
                if isinstance(rec, dict) and rec.get("counter") in ENG_COUNTERS:
                    stats["targets_seen"] += 1
                    if arm == "eng_off" and rec.get("role") == ENG_ROLE_AFTER:
                        rec = {**rec, "role": ENG_ROLE_BEFORE}
                        stats["targets_rewritten"] += 1
                out.append(rec)
            return out
        return data

    oob._load = wrapped
    return stats


def _assert_reached(arm: str, stats: dict) -> None:
    """REACH half of the neuter-proof.  Fail loud; a silent dead patch is the whole trap."""
    if arm == "live":
        return
    if stats["calls"] == 0:
        raise RuntimeError("NEUTER DEAD: game.oob._load was never called through the wrapper")
    if stats["targets_seen"] != len(ENG_COUNTERS):
        raise RuntimeError(
            f"NEUTER DEAD: saw {stats['targets_seen']} of {len(ENG_COUNTERS)} (ENG) records "
            f"({stats['calls']} _load calls, {stats['records_seen']} records)")
    if arm == "eng_off" and stats["targets_rewritten"] != len(ENG_COUNTERS):
        raise RuntimeError(
            f"NEUTER DEAD: rewrote {stats['targets_rewritten']} of {len(ENG_COUNTERS)} (ENG) roles "
            "-- this tree may not carry the correction at all")
    if arm == "noop" and stats["targets_rewritten"] != 0:
        raise RuntimeError("NEUTER BROKEN: the identity arm rewrote a record")


# --- the run --------------------------------------------------------------------------------------

def report(job) -> dict:
    seed, arm, max_turns = job
    try:
        return _report(seed, arm, max_turns)
    except Exception as exc:                                # noqa: BLE001 - a driver, not engine code
        return {"seed": seed, "arm": arm, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-3000:]}


def _report(seed: int, arm: str, max_turns) -> dict:
    stats = _install(arm) if arm != "live" else {}
    from game import combat_tables, coords
    from game.apply import apply
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import determinism_signature, run
    from game.events import Side
    from game.scenario import campaign

    init = campaign(seed=seed) if max_turns is None else campaign(seed=seed, max_turns=max_turns)
    if arm != "live":
        _assert_reached(arm, stats)
    res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final

    by_id = {u.id: u for u in init.units}

    def label(uid: str) -> str:
        u = by_id.get(uid)
        return getattr(u, "counter", None) or uid if u else uid

    # ---- 1. attachment, and [15.53] --------------------------------------------------------------
    attach = Counter()
    attach_parents: Counter = Counter()
    attach_assigned = Counter()
    detach = Counter()
    rejects: Counter = Counter()
    org_fires: Counter = Counter()
    org_tiers: Counter = Counter()
    combats = Counter()
    surrenders = Counter()
    moved_ids: set = set()

    turn = 0
    hw_r, hw_turn = -999, None
    hw_per_turn: dict = {}

    for e in res.events:
        k, s = _kind(e), _side(e)
        p = e.payload or {}
        if k == "TURN_ADVANCED":
            turn = p.get("turn", turn + 1)
        elif k == "UNIT_ATTACHED":
            attach[s] += 1
            attach_parents[f"{s}/{label(p.get('parent_id',''))}"] += 1
            attach_assigned["assigned" if p.get("assigned") else "unassigned"] += 1
        elif k == "UNIT_DETACHED":
            detach[s] += 1
        elif k == "ORDER_REJECTED":
            rejects[f"{s}/{p.get('order','?')}"] += 1
        elif k == "COMBAT_RESOLVED":
            combats[s] += 1
            if p.get("surrender") or p.get("attacker_captured") or p.get("defender_captured"):
                surrenders[s] += 1
            if "attacker_size" in p:                     # engine.py:5586 -- [15.53] took part
                a, d = p["attacker_size"], p["defender_size"]
                shift = combat_tables.org_size_shift(a, d)
                org_tiers[f"atk{a}/def{d}"] += 1
                if shift == 0:
                    org_fires["recorded_but_no_shift"] += 1
                else:
                    favoured = s if shift > 0 else ("ALLIED" if s == "AXIS" else "AXIS")
                    org_fires[f"favoured_{favoured}"] += 1
                    org_fires["shifting_total"] += 1
                org_fires["recorded_total"] += 1
        if k in GROUND_MOVE_KINDS:
            if k == "UNIT_MOVED" and p.get("unit_id"):
                moved_ids.add(p["unit_id"])
            if e.side == Side.AXIS:
                h = p.get("to") or p.get("hex")
                if isinstance(h, (list, tuple)) and len(h) == 2 and all(isinstance(x, int) for x in h):
                    if h[1] > hw_r:
                        hw_r, hw_turn = h[1], turn
                    if h[1] > hw_per_turn.get(turn, -999):
                        hw_per_turn[turn] = h[1]

    # ---- 2. the city ledger, turn by turn, at 64.73 quality ---------------------------------------
    # Re-folds the SAME log (apply is pure, so this cannot perturb anything) and reads the victory
    # projection's own _occupier at every Game-Turn boundary.  Reported as change points: a city
    # appears in the track only on the turns its holder changes.
    st = init
    vic = init.victory
    cities = [(name, ax) for ax, _a, _c, name in vic.cities]
    track: dict = {name: [] for name, _ in cities}
    banked_at: dict = {}
    last: dict = {name: "__start__" for name, _ in cities}
    seen_turn = 0

    def sample(t: int) -> None:
        for name, ax in cities:
            o = vic._occupier(st, ax)
            v = None if o is None else o.value
            if v != last[name]:
                track[name].append([t, v])
                last[name] = v
        if t in (30, 60, 90):
            banked_at[f"GT{t}"] = {
                "AXIS": sorted(n for n, _ in cities if last[n] == "AXIS"),
                "ALLIED": sorted(n for n, _ in cities if last[n] == "ALLIED")}

    sample(0)
    for e in res.events:
        st = apply(st, e)
        if _kind(e) == "TURN_ADVANCED":
            seen_turn = (e.payload or {}).get("turn", seen_turn + 1)
            sample(seen_turn)
    sample(seen_turn)
    banked_at["final"] = {
        "AXIS": sorted(n for n, ax in cities if vic._occupier(fin, ax) == Side.AXIS),
        "ALLIED": sorted(n for n, ax in cities if vic._occupier(fin, ax) == Side.ALLIED)}

    # ---- 4. sanity --------------------------------------------------------------------------------
    def live_combat(s):
        return [u for u in fin.units if u.side == s and getattr(u, "is_combat", True)
                and u.strength > 0 and fin.on_map(u)]

    def _r(h):
        return h[1] if isinstance(h, tuple) else coords.to_axial(h)[1]

    ax_live, cw_live = live_combat(Side.AXIS), live_combat(Side.ALLIED)
    hq_ids = [u.id for u in init.units if not u.is_combat and getattr(u, "org_type", "")]
    hq_fate = []
    for uid in sorted(hq_ids):
        u0, u1 = by_id[uid], fin.unit(uid)
        hq_fate.append({
            "id": uid, "counter": getattr(u0, "counter", None), "side": u0.side.value,
            "engineer": getattr(u0, "engineer", ""),
            "moved_at_least_once": uid in moved_ids,
            "alive_at_end": bool(u1 is not None and u1.strength > 0),
            "on_map_at_end": bool(u1 is not None and fin.on_map(u1)),
            "hex_at_end": list(u1.hex) if u1 is not None and fin.on_map(u1) else None,
        })

    on_map_at_setup = [u.id for u in init.units if init.on_map(u)]
    return {
        "seed": seed, "arm": arm, "max_turns": max_turns,
        "winner": None if res.winner is None else res.winner.value,
        "reason": res.reason,
        "events": len(res.events),
        # engine.determinism_signature returns the WHOLE canonical log as JSON (engine.py:6041 ->
        # events.log_to_json), ~71 MB for one 111-turn campaign.  Two logs are byte-identical iff
        # their digests are, which is the only thing an A/B or a neuter-proof asks of it, so the
        # arm files carry the digest -- the same choice scratchpad/gate81c_ab.py made.
        "signature": hashlib.blake2b(
            determinism_signature(res.events).encode(), digest_size=16).hexdigest(),
        "signature8": hashlib.blake2b(
            determinism_signature(res.events).encode(), digest_size=8).hexdigest(),
        "neuter": dict(stats),
        # 1
        "unit_attached": dict(sorted(attach.items())),
        "unit_attached_by_parent": dict(sorted(attach_parents.items())),
        "unit_attached_assignment": dict(sorted(attach_assigned.items())),
        "unit_detached": dict(sorted(detach.items())),
        "order_rejected": dict(sorted(rejects.items())),
        "org_size_15_53": dict(sorted(org_fires.items())),
        "org_size_tiers": dict(sorted(org_tiers.items())),
        # 2
        "city_change_points": {k: v for k, v in track.items() if v},
        "banked": banked_at,
        "axis_ground_high_water_r": hw_r,
        "axis_ground_high_water_turn": hw_turn,
        "axis_ground_high_water_per_turn": {str(k): v for k, v in sorted(hw_per_turn.items())},
        # 4
        "combats_by_side": dict(sorted(combats.items())),
        "surrender_combats_by_side": dict(sorted(surrenders.items())),
        "axis_combat_units_alive": len(ax_live),
        "cw_combat_units_alive": len(cw_live),
        "axis_east_at_end": max((_r(u.hex) for u in ax_live), default=None),
        "cw_west_at_end": min((_r(u.hex) for u in cw_live), default=None),
        "units_that_never_moved": len([u for u in init.units if u.id not in moved_ids]),
        "units_on_map_at_setup_that_never_moved": len(
            [u for u in on_map_at_setup if u not in moved_ids]),
        "units_the_war_contains": len(init.units),
        "hq_fate": hq_fate,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1941, 7, 4, 24, 2026, 99, 1])
    ap.add_argument("--arm", choices=("live", "eng_off", "noop"), default="live")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--max-turns", type=int, default=None,
                    help="TRUNCATE the war -- for smoke-testing this driver only, never for the gate")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc: dict = {"seeds": args.seeds, "arm": args.arm, "max_turns": args.max_turns, "results": []}
    jobs = [(s, args.arm, args.max_turns) for s in args.seeds]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(report, jobs):
            doc["results"].append(r)
            with open(args.out, "w") as f:
                json.dump(doc, f, indent=1)
            if "ERROR" in r:
                print(f"  seed {r['seed']}: {r['ERROR']}", flush=True)
            else:
                print(f"  seed {r['seed']} [{r['arm']}]: sig {r['signature8']} | "
                      f"attach={r['unit_attached']} | 15.53={r['org_size_15_53']} | "
                      f"hw_r={r['axis_ground_high_water_r']} | {r['reason']}", flush=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
