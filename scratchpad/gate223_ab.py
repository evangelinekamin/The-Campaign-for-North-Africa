"""GATE 22.3 -- WHAT THE MAJOR REPAIR FACILITIES ACTUALLY RECOVER, AND WHETHER IT REACHES THE FRONT.

Read-only.  Changes NOTHING in game/ or data/.  Runs UNMODIFIED in BOTH trees:
  BASE = detached worktree at 88e5314 (the last commit before 48dbad1, the first 22.3 commit)
  HEAD = 35edbdd (22.3 + its review repair)
Every symbol it touches outside the 22.3 slice itself (Unit.broken_down, TruckFormation.broken_down,
campaign_victory.cities/_occupier, EventKind.VEHICLE_REPAIRED/TRUCK_REPAIRED/*_BROKE_DOWN) shipped
long before 88e5314, an ancestor of both, so the ONLY difference between the arms is rule 22.3.

WHAT BASE->HEAD ACTUALLY MOVES, AND WHY THERE ARE THREE ARMS.  The 22.3 commit bundles three
changes, not one:
  (a) FACILITY ROUTING -- a broken vehicle or Truck Point standing on Alexandria / Cairo / Tobruk
      rolls the [22.34] Facility column instead of the [22.8] Field one, pays 1 Fuel + 1 Stores per
      point (22.35), takes the 22.34a fortification-damage die shift, and is exempt from the
      weather (22.36) and enemy-control (22.13a) gates Field Repair keeps.
  (b) THE FIELD TANK FUEL DRAW -- switched from supply.plan_draw (rule 32.16's ABSTRACT half-CPA
      trace, a Section-32 rule that does not apply to this engine) to supply.in_hex_draw, which is
      what 22.26 "present in the hex" actually says.
  (c) THE PARTIAL ATTEMPT -- 22.26/22.35's "he may attempt to repair only those points he has
      expended supplies for" replaces BASE's all-or-nothing forfeit.
A two-arm A/B cannot separate (a) from (b)+(c), and the slice is asked what the FACILITY economy
buys.  So the third arm runs in the HEAD tree with only (a) backed out, at the one seam the whole
routing hangs on:

    live         : nothing patched.
    facility_off : game.repair.major_facility_hexes returns the empty set, so every repair in the
                   war takes the Field path -- (b) and (c) still in force.
    noop         : the SAME patch machinery installed with an identity transform.

`noop` is the neuter-proof and it is not optional.  A neuter that never reaches the caller measures
the un-neutered arm and reports it as a finding; the trap is recorded in tests/baselines.py and has
bitten this project twice.  game/engine.py does "from . import ... repair ..." (engine.py:19) -- a
MODULE import, so `repair.major_facility_hexes` is an attribute lookup at call time and rebinding
game.repair.major_facility_hexes DOES reach engine._repair.  Three independent checks are asserted
in-process, and the run DIES rather than report a number if any fails:
  (a) REACH -- the wrapper counts its own calls; zero in a 111-turn war is a dead patch.
  (b) CONSEQUENCE -- in the facility_off arm the instrumented facility path must be entered ZERO
      times across the whole war.  A patch that is called but changes nothing is equally dead.
  (c) INERTNESS -- the noop arm's determinism signature must equal live's, byte for byte.  Compared
      in the report (separate processes), and the read-only instrumentation is proved inert the
      same way by gate223_inert.py on a truncated war.

WHAT IT ANSWERS
  1. THE MECHANISM.  What rule 22.3 restores is BROKEN-DOWN TOE STRENGTH POINTS (tanks, armoured
     cars, recce) and BROKEN-DOWN TRUCK POINTS, so those are the units of account -- counted
     against what broke in the first place, split Facility-column vs Field-column by wrapping the
     four engine repair helpers themselves (exact, not inferred from a supply-spend heuristic), and
     located by hex.
  2. DOES IT REACH THE FRONT.  Every counter that took a Facility repair is tracked for the REST OF
     THE WAR through a re-fold of the log: the furthest FORWARD it subsequently stood (west of the
     Delta for the Commonwealth, east of Benghazi for the Axis), and whether it was forward at the
     end.  A tank recovered in Cairo that never leaves Cairo has recovered nothing that matters.
  3. THE BALANCE.  Winner, the full 64.76 grade string with both totals, AND the 64.73 GEOGRAPHIC
     half recomputed independently off the final state -- so a VP move can be decomposed into
     ground versus the 64.74/64.75 bookkeeping, which is exactly the distinction the 8.1c gate had
     to make after a 7/7 Axis VP fall turned out to be bookkeeping.
  4. SANITY.  Repaired points versus broken points per side (recovery cannot exceed breakage), the
     largest single repair, any repair folded onto a counter that could not absorb it (a
     resurrection the rules do not grant), and wall-clock per run (a loop that never terminates).

Usage:
  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate223_ab.py --seeds 1941 7 4 24 2026 99 1 \
      --arm live --workers 7 --out <path.json> [--max-turns N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

# The east-west axial coordinate (index 1) IS this map's east-west axis: Benghazi r=20, Tobruk 66,
# Sollum 76, Bardia 77, Barrani 86, Matruh 100, El Daba 113, El Hamman 124, Alexandria 133, Cairo
# 140.  The two "rear" lines are scripts/measure_campaign.py's own, unchanged.
DELTA_R = 132          # see below -- the westernmost hex of the rule-57 Commonwealth base
BENGHAZI_R = 20        # the Axis port of arrival (56.2)

# THE 132-NOT-133 CORRECTION, and why it matters here more than it did for measure_campaign.
# scripts/measure_campaign.py draws the Delta line at r<133 "Alexandria is r=133".  The [22.31]
# Major-Facility roster this gate reads off campaign_victory's own 64.71 table has TWO Alexandria
# hexes, (25,133) AND (26,132) -- and the second one is where every Commonwealth facility repair in
# the campaign actually happens.  Under a r<133 test a tank repaired at (26,132) that never moves an
# inch scores as "forward", which would answer question 2 by construction.  The line is therefore
# strictly WEST of every Alexandria/Cairo hex, and the reach histogram below reports the raw
# distribution as well so the threshold argues nothing on its own.
REACH_MARKS = ((132, "west_of_alexandria"), (124, "west_of_el_hamman"), (119, "west_of_el_alamein"),
               (113, "west_of_el_daba"), (100, "west_of_matruh"), (86, "west_of_barrani"),
               (77, "west_of_bardia"), (66, "west_of_tobruk"))


def _forward(side_value: str, r_coord: int) -> bool:
    """Is this hex FORWARD for `side` -- out of its own rear and into the contested desert?"""
    return r_coord < DELTA_R if side_value == "ALLIED" else r_coord > BENGHAZI_R


def _kind(e) -> str:
    k = getattr(e, "kind", "")
    return str(getattr(k, "value", k))


def _side(e) -> str:
    s = getattr(e, "side", "")
    return str(getattr(s, "value", s))


def _rc(h) -> int:
    return h[1] if isinstance(h, (tuple, list)) else -999


# --- THE NEUTER, AND ITS PROOF --------------------------------------------------------------------

def _install_neuter(arm: str) -> dict:
    """Rebind game.repair.major_facility_hexes.  Returns the live counter dict asserted against.
    In the BASE tree game.repair does not exist at all, and neither neuter arm is ever run there."""
    from game import repair

    stats = {"calls": 0, "hexes_seen": 0, "hexes_returned": 0}
    original = repair.major_facility_hexes

    def wrapped(state):
        out = original(state)
        stats["calls"] += 1
        stats["hexes_seen"] = len(out)
        if arm == "facility_off":
            out = frozenset()
        stats["hexes_returned"] = len(out)
        return out

    repair.major_facility_hexes = wrapped
    return stats


def _assert_neuter_reached(arm: str, stats: dict, paths: dict) -> None:
    """REACH + CONSEQUENCE halves of the neuter-proof.  Fail loud; a silent dead patch is the trap."""
    if arm == "live":
        return
    if stats["calls"] == 0:
        raise RuntimeError("NEUTER DEAD: repair.major_facility_hexes was never called through the "
                           "wrapper in a 111-turn war")
    if stats["hexes_seen"] == 0:
        raise RuntimeError("NEUTER DEAD: the real major_facility_hexes returned an EMPTY roster -- "
                           "there is nothing for this arm to switch off")
    entered = paths[("facility", "unit")]["calls"] + paths[("facility", "truck")]["calls"]
    if arm == "facility_off" and entered != 0:
        raise RuntimeError(f"NEUTER DEAD: the facility path was still entered {entered} times")
    if arm == "noop" and entered == 0:
        raise RuntimeError("NEUTER BROKEN: the identity arm never entered the facility path, so it "
                           "is not measuring the same thing as live")
    if arm == "noop" and stats["hexes_returned"] != stats["hexes_seen"]:
        raise RuntimeError("NEUTER BROKEN: the identity arm changed the roster")


# --- THE INSTRUMENT (read-only): which repair COLUMN did each point come off? ----------------------

def _install_instrument() -> tuple[dict, list]:
    """Wrap game.engine's four repair helpers with pure delegating recorders.

    Exact by construction rather than inferred: the column a point came off is the FUNCTION THE
    ENGINE CALLED, not a heuristic over which commodities were spent afterwards.  engine._repair
    calls each of these as a bare module global (engine.py, _repair's body), so rebinding the
    module attribute reaches it.  In the BASE tree only the two Field helpers exist as separate
    functions -- BASE inlines its whole Repair Phase into _repair -- so every wrap is guarded and
    BASE simply reports no per-path split (it has only one path, the Field one, by construction).

    Returns (paths, detail).  `detail` is one record per repaired counter per repair, which is what
    the front-reach half re-folds against; repairs are rare enough (hundreds per war) that keeping
    them all is cheaper than a second pass."""
    from game import engine

    paths: dict = defaultdict(lambda: {"calls": 0, "funded": 0, "points": 0, "fuel": 0, "stores": 0,
                                       "offered": 0, "offered_unfunded": 0,
                                       "points_by_side": Counter(), "calls_by_side": Counter(),
                                       "offered_by_side": Counter(),
                                       "points_by_hex_r": Counter()})
    detail: list = []

    def _harvest(path: str, cls: str, r, emitted, funded: bool, side, offered: int) -> None:
        b = paths[(path, cls)]
        sv = str(getattr(side, "value", side))
        b["calls"] += 1
        b["calls_by_side"][sv] += 1
        b["offered"] += offered
        b["offered_by_side"][sv] += offered
        if funded:
            b["funded"] += 1
        else:
            b["offered_unfunded"] += offered
        for e in emitted:
            k, p = _kind(e), (e.payload or {})
            if k in ("SUPPLY_CONSUMED", "UNIT_SUPPLY_CONSUMED"):
                c = str(p.get("commodity", "")).lower()
                if "fuel" in c:
                    b["fuel"] += p.get("qty", 0)
                elif "stores" in c:
                    b["stores"] += p.get("qty", 0)
            elif k in ("VEHICLE_REPAIRED", "TRUCK_REPAIRED"):
                tid = p.get("unit_id") or p.get("truck_id")
                amt = p.get("amount", 0)
                obj = r.state.unit(tid) if k == "VEHICLE_REPAIRED" else r.state.truck(tid)
                hx = getattr(obj, "hex", None)
                b["points"] += amt
                b["points_by_side"][_side(e)] += amt
                b["points_by_hex_r"][_rc(hx)] += amt
                detail.append({"path": path, "cls": cls, "side": _side(e), "id": tid,
                               "turn": r.state.turn, "amount": amt, "r": _rc(hx),
                               "hex": list(hx) if isinstance(hx, tuple) else None})

    def _wrap(name: str, path: str, cls: str, side_arg: int, target_arg: int):
        orig = getattr(engine, name, None)
        if orig is None:
            return                                       # BASE tree: this helper does not exist
        def wrapped(*a, **kw):
            r = a[0]
            n = len(r.events)
            # The BROKEN POOL PRESENTED to this column, read BEFORE the call -- so "offered vs
            # repaired" separates what the die refused from what 22.35 could not pay for.
            live = (r.state.unit if cls == "unit" else r.state.truck)
            offered = sum(getattr(live(getattr(x, "id")), "broken_down", 0) for x in a[target_arg])
            out = orig(*a, **kw)
            _harvest(path, cls, r, r.events[n:], bool(out) if out is not None else True,
                     a[side_arg], offered)
            return out
        setattr(engine, name, wrapped)

    _wrap("_facility_repair_units", "facility", "unit", 1, 3)
    _wrap("_facility_repair_trucks", "facility", "truck", 1, 4)
    _wrap("_field_repair_units", "field", "unit", 1, 4)
    _wrap("_field_repair_trucks", "field", "truck", 1, 3)
    return paths, detail


# --- the run --------------------------------------------------------------------------------------

def report(job) -> dict:
    seed, arm, max_turns, instrument = job
    try:
        return _report(seed, arm, max_turns, instrument)
    except Exception as exc:                                # noqa: BLE001 - a driver, not engine code
        return {"seed": seed, "arm": arm, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-3000:]}


def _report(seed: int, arm: str, max_turns, instrument: bool = True) -> dict:
    t0 = time.time()
    neuter = _install_neuter(arm) if arm != "live" else {}
    paths, detail = (_install_instrument() if instrument
                     else (defaultdict(lambda: {"calls": 0}), []))

    from game.apply import apply
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import determinism_signature, run
    from game.events import Side
    from game.scenario import campaign

    init = campaign(seed=seed) if max_turns is None else campaign(seed=seed, max_turns=max_turns)
    facility_roster = []
    try:                                                    # BASE tree has no game.repair at all
        from game import repair as _repair_mod
        facility_roster = sorted(list(h) for h in _repair_mod.major_facility_hexes(init))
    except ImportError:
        pass

    res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final
    if arm != "live":
        _assert_neuter_reached(arm, neuter, paths)

    # ---- 1. the mechanism: what broke, what came back ---------------------------------------------
    broke = defaultdict(Counter)        # class -> side -> points
    fixed = defaultdict(Counter)
    fixed_events = Counter()
    biggest = Counter()
    turn = 0
    repairs_by_turn_bucket: dict = defaultdict(Counter)
    for e in res.events:
        k, s, p = _kind(e), _side(e), (e.payload or {})
        if k == "TURN_ADVANCED":
            turn = p.get("turn", turn + 1)
        elif k == "VEHICLE_BROKE_DOWN":
            broke["toe"][s] += p.get("amount", 0)
        elif k == "TRUCK_BROKE_DOWN":
            broke["truck"][s] += p.get("amount", 0)
        elif k == "VEHICLE_REPAIRED":
            fixed["toe"][s] += p.get("amount", 0)
            fixed_events[f"toe/{s}"] += 1
            biggest["toe"] = max(biggest["toe"], p.get("amount", 0))
            repairs_by_turn_bucket[f"{(turn - 1) // 20 * 20 + 1}-{((turn - 1) // 20 + 1) * 20}"][s] += \
                p.get("amount", 0)
        elif k == "TRUCK_REPAIRED":
            fixed["truck"][s] += p.get("amount", 0)
            fixed_events[f"truck/{s}"] += 1
            biggest["truck"] = max(biggest["truck"], p.get("amount", 0))

    # ---- 2. does it reach the front? --------------------------------------------------------------
    # Re-fold the SAME log (apply is pure, so this cannot perturb anything) and, at every Game-Turn
    # boundary AFTER a counter took a Facility repair, record how far forward it then stood.
    facility_units: dict = {}       # unit_id -> {"side","first_turn","points","r_at_repair"}
    facility_trucks: dict = {}
    for d in detail:
        if d["path"] != "facility":
            continue
        book = facility_units if d["cls"] == "unit" else facility_trucks
        rec = book.setdefault(d["id"], {"side": d["side"], "first_turn": d["turn"], "points": 0,
                                        "r_at_repair": d["r"], "best_r": None, "final_r": None,
                                        "forward_after": False})
        rec["points"] += d["amount"]
        rec["first_turn"] = min(rec["first_turn"], d["turn"])

    st = init
    seen_turn = 0

    def _track(t: int) -> None:
        for uid, rec in facility_units.items():
            if t < rec["first_turn"]:
                continue
            u = st.unit(uid)
            if u is None or not st.on_map(u):
                continue
            rr = _rc(u.hex)
            best = rec["best_r"]
            # "forward" is west (smaller r) for the Commonwealth, east (bigger r) for the Axis
            if best is None or (rr < best if rec["side"] == "ALLIED" else rr > best):
                rec["best_r"] = rr
            if _forward(rec["side"], rr):
                rec["forward_after"] = True
        if facility_trucks:
            by_id = {t_.id: t_ for t_ in st.trucks}
            for tid, rec in facility_trucks.items():
                if t < rec["first_turn"] or tid not in by_id:
                    continue
                rr = _rc(by_id[tid].hex)
                best = rec["best_r"]
                if best is None or (rr < best if rec["side"] == "ALLIED" else rr > best):
                    rec["best_r"] = rr
                if _forward(rec["side"], rr):
                    rec["forward_after"] = True

    _track(0)
    for e in res.events:
        st = apply(st, e)
        if _kind(e) == "TURN_ADVANCED":
            seen_turn = (e.payload or {}).get("turn", seen_turn + 1)
            _track(seen_turn)
    _track(seen_turn)
    fin_trucks = {t_.id: t_ for t_ in fin.trucks}
    for uid, rec in facility_units.items():
        u = fin.unit(uid)
        rec["final_r"] = _rc(u.hex) if u is not None and fin.on_map(u) else None
        rec["alive_at_end"] = bool(u is not None and u.strength > 0)
    for tid, rec in facility_trucks.items():
        t_ = fin_trucks.get(tid)
        rec["final_r"] = _rc(t_.hex) if t_ is not None else None
        rec["alive_at_end"] = t_ is not None

    def _reach(book: dict) -> dict:
        out: dict = {}
        for s in ("ALLIED", "AXIS"):
            rows = [r_ for r_ in book.values() if r_["side"] == s]
            if not rows:
                continue
            # How far each counter actually TRAVELLED toward the enemy after being made whole --
            # the raw datum question 2 turns on, reported as a histogram against the map's own
            # named places so no single threshold carries the answer.
            gained = sorted((r_["r_at_repair"] - r_["best_r"]) if s == "ALLIED"
                            else (r_["best_r"] - r_["r_at_repair"])
                            for r_ in rows if r_["best_r"] is not None)
            out[s] = {
                "counters": len(rows),
                "points_recovered": sum(r_["points"] for r_ in rows),
                "counters_forward_after_repair": sum(1 for r_ in rows if r_["forward_after"]),
                "points_on_counters_that_went_forward":
                    sum(r_["points"] for r_ in rows if r_["forward_after"]),
                "counters_forward_at_end":
                    sum(1 for r_ in rows if r_["final_r"] is not None
                        and _forward(s, r_["final_r"])),
                "median_r_at_repair": sorted(r_["r_at_repair"] for r_ in rows)[len(rows) // 2],
                "best_r_reached": (min if s == "ALLIED" else max)(
                    [r_["best_r"] for r_ in rows if r_["best_r"] is not None], default=None),
                "hexes_gained_toward_enemy": {"median": gained[len(gained) // 2] if gained else None,
                                              "max": max(gained) if gained else None,
                                              "moved_at_all": sum(1 for g in gained if g > 0)},
                "reach_histogram": ({mark: sum(1 for r_ in rows if r_["best_r"] is not None
                                               and r_["best_r"] < cut)
                                     for cut, mark in REACH_MARKS} if s == "ALLIED" else
                                    {"east_of_benghazi": sum(1 for r_ in rows
                                                             if r_["best_r"] is not None
                                                             and r_["best_r"] > BENGHAZI_R)}),
                "points_reaching_west_of_alexandria":
                    sum(r_["points"] for r_ in rows
                        if r_["best_r"] is not None and r_["best_r"] < DELTA_R) if s == "ALLIED"
                    else None,
            }
        return out

    # ---- 3. the balance, decomposed ---------------------------------------------------------------
    vic = init.victory
    cities = [(name, ax, avp, cvp) for ax, avp, cvp, name in vic.cities]
    geo = {"AXIS": 0, "ALLIED": 0}
    held: dict = {"AXIS": [], "ALLIED": []}
    for name, ax, avp, cvp in cities:
        o = vic._occupier(fin, ax)
        if o == Side.AXIS:
            geo["AXIS"] += avp
            held["AXIS"].append(name)
        elif o == Side.ALLIED:
            geo["ALLIED"] += cvp
            held["ALLIED"].append(name)
    axis_total = cw_total = None
    reason = res.reason or ""
    if "Victory Points" in reason:                          # "...: 620-140 Victory Points (64.76)"
        tail = reason.split(":")[-1].split("Victory Points")[0].strip() if ":" in reason else ""
        if not tail:
            tail = reason.split("Draw at")[-1].split("Victory Points")[0].strip()
        try:
            a, c = tail.split("-")
            axis_total, cw_total = float(a), float(c)
        except ValueError:
            pass

    # ---- 4. sanity --------------------------------------------------------------------------------
    absurd = []
    for cls in ("toe", "truck"):
        for s in ("AXIS", "ALLIED"):
            if fixed[cls][s] > broke[cls][s]:
                absurd.append(f"{cls}/{s}: repaired {fixed[cls][s]} > broke {broke[cls][s]}")
    neg = [u.id for u in fin.units if getattr(u, "broken_down", 0) < 0]
    if neg:
        absurd.append(f"negative broken_down on {len(neg)} counters: {neg[:5]}")
    negt = [t_.id for t_ in fin.trucks if t_.broken_down < 0]
    if negt:
        absurd.append(f"negative broken_down on {len(negt)} truck formations: {negt[:5]}")
    dead_repaired = [d for d in detail
                     if d["cls"] == "unit" and (fin.unit(d["id"]) is None)]
    if dead_repaired:
        absurd.append(f"{len(dead_repaired)} repairs onto counters absent from the final state")

    sig = determinism_signature(res.events)
    return {
        "seed": seed, "arm": arm, "max_turns": max_turns,
        "seconds": round(time.time() - t0, 1),
        "winner": None if res.winner is None else res.winner.value,
        "reason": reason,
        "events": len(res.events),
        "signature": hashlib.blake2b(sig.encode(), digest_size=16).hexdigest(),
        "signature8": hashlib.blake2b(sig.encode(), digest_size=8).hexdigest(),
        "neuter": dict(neuter),
        "major_facility_hexes": facility_roster,
        # 1
        "broken_points": {c: dict(v) for c, v in broke.items()},
        "repaired_points": {c: dict(v) for c, v in fixed.items()},
        "repair_events": dict(fixed_events),
        "repair_toe_by_turn_bucket": {k: dict(v) for k, v in sorted(repairs_by_turn_bucket.items())},
        "paths": {f"{p}/{c}": {"calls": v["calls"], "funded": v["funded"], "points": v["points"],
                               "fuel": v["fuel"], "stores": v["stores"],
                               "offered": v["offered"], "offered_unfunded": v["offered_unfunded"],
                               "points_by_side": dict(v["points_by_side"]),
                               "calls_by_side": dict(v["calls_by_side"]),
                               "offered_by_side": dict(v["offered_by_side"]),
                               "points_by_hex_r": dict(sorted(v["points_by_hex_r"].items()))}
                  for (p, c), v in sorted(paths.items())},
        # 2
        "front_reach_units": _reach(facility_units),
        "front_reach_trucks": _reach(facility_trucks),
        "facility_unit_rows": sorted(
            ({"id": k, **v} for k, v in facility_units.items()), key=lambda d: d["id"])[:80],
        # 3
        "victory_total_axis": axis_total, "victory_total_cw": cw_total,
        "geographic_64_73": geo,
        "nongeographic": {"AXIS": None if axis_total is None else round(axis_total - geo["AXIS"], 1),
                          "ALLIED": None if cw_total is None else round(cw_total - geo["ALLIED"], 1)},
        "cities_held_at_end": {k: sorted(v) for k, v in held.items()},
        # 4
        "sanity_absurd": absurd,
        "biggest_single_repair": dict(biggest),
        "axis_units_alive": sum(1 for u in fin.units if u.side == Side.AXIS and u.strength > 0),
        "cw_units_alive": sum(1 for u in fin.units if u.side == Side.ALLIED and u.strength > 0),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1941, 7, 4, 24, 2026, 99, 1])
    ap.add_argument("--arm", choices=("live", "facility_off", "noop"), default="live")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--max-turns", type=int, default=None,
                    help="TRUNCATE the war -- for smoke-testing this driver only, never for the gate")
    ap.add_argument("--instrument", choices=("on", "off"), default="on",
                    help="off = run with the read-only wrappers UNINSTALLED; the inertness proof "
                         "compares the two signatures (gate223_inert.py)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc: dict = {"seeds": args.seeds, "arm": args.arm, "max_turns": args.max_turns,
                 "instrument": args.instrument, "results": []}
    jobs = [(s, args.arm, args.max_turns, args.instrument == "on") for s in args.seeds]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(report, jobs):
            doc["results"].append(r)
            with open(args.out, "w") as f:
                json.dump(doc, f, indent=1)
            if "ERROR" in r:
                print(f"  seed {r['seed']}: {r['ERROR']}", flush=True)
            else:
                print(f"  seed {r['seed']} [{r['arm']}] {r['seconds']}s: sig {r['signature8']} | "
                      f"fixed={r['repaired_points']} | paths="
                      f"{ {k: v['points'] for k, v in r['paths'].items()} } | {r['reason']}",
                      flush=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
