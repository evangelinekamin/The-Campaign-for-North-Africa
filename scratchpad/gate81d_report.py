"""GATE 8.1c-OOB (8.1d) -- the report.  Reads the arm JSONs written by gate81d_ab.py and the two
static censuses written by gate81d_formations.py and prints the gate's four answers.

Pure reduction: it opens no engine module and folds no campaign, so it cannot itself perturb what it
reports.  Every number it prints is copied from a measured arm.

Usage:
  python3 scratchpad/gate81d_report.py --dir scratchpad/gate81d
"""
from __future__ import annotations

import argparse
import json
import os


def load(path):
    with open(path) as f:
        return json.load(f)


def by_seed(doc) -> dict:
    return {r["seed"]: r for r in doc["results"] if "ERROR" not in r}


def errors(name, doc) -> list:
    return [f"{name} seed {r['seed']}: {r['ERROR']}" for r in doc["results"] if "ERROR" in r]


def vp(reason: str) -> "tuple[float, float] | None":
    """Pull the two 64.76 totals out of the grade string."""
    if "Victory Points" not in reason:
        return None
    body = reason.split(":")[-1] if ":" in reason else reason
    body = body.split("Victory Points")[0].strip()
    body = body.replace("Draw at", "").strip()
    try:
        a, c = body.split("-")
        return float(a), float(c)
    except ValueError:
        return None


def track_at(changes, turn) -> str:
    """The holder of a city at `turn`, from its change-point list."""
    who = None
    for t, v in changes:
        if t <= turn:
            who = v
        else:
            break
    return who or "-"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="scratchpad/gate81d")
    args = ap.parse_args()
    d = args.dir

    arms = {}
    for name, fn in (("BASE", "ab_BASE.json"), ("HEAD", "ab_HEAD.json"),
                     ("ENGOFF", "ab_HEAD_eng_off.json"), ("NOOP", "ab_HEAD_noop.json")):
        p = os.path.join(d, fn)
        if os.path.exists(p):
            arms[name] = load(p)
    seeds = arms["HEAD"]["seeds"]
    S = {k: by_seed(v) for k, v in arms.items()}

    err = [e for k, v in arms.items() for e in errors(k, v)]
    print("=" * 100)
    print("GATE 8.1c-OOB -- THE DIVISION HQs AND THE 23.11 (ENG) CORRECTION, MEASURED")
    print("=" * 100)
    print(f"BASE = a6c9700 (detached worktree)   HEAD = 607b63c   seeds = {seeds}")
    print(f"arms present: {sorted(arms)}   errors: {err or 'none'}")

    # --- THE NEUTER-PROOF -------------------------------------------------------------------------
    print("\n" + "-" * 100)
    print("0. THE NEUTER-PROOF (the trap in tests/baselines.py: a patch that never reaches its caller")
    print("   measures the un-neutered arm and reports it as a finding)")
    print("-" * 100)
    if "NOOP" in S:
        for s in sorted(S["NOOP"]):
            a, b = S["NOOP"][s], S["HEAD"].get(s)
            same = b is not None and a["signature"] == b["signature"]
            print(f"  seed {s}: identity-patched signature {'==' if same else '!='} unpatched "
                  f"({a['signature8']} vs {b['signature8'] if b else '?'})   "
                  f"_load calls {a['neuter']['calls']}, (ENG) records seen "
                  f"{a['neuter']['targets_seen']}, rewritten {a['neuter']['targets_rewritten']}")
            if not same:
                print("  *** THE HARNESS ITSELF PERTURBS THE RUN -- every eng_off number below is void")
    if "ENGOFF" in S:
        n = next(iter(S["ENGOFF"].values()))["neuter"]
        print(f"  eng_off arm: _load calls {n['calls']}, (ENG) records seen {n['targets_seen']}, "
              f"rewritten {n['targets_rewritten']} (the driver raises if either is short)")
        diff = sum(1 for s in seeds if s in S["ENGOFF"] and s in S["HEAD"]
                   and S["ENGOFF"][s]["signature"] != S["HEAD"][s]["signature"])
        print(f"  eng_off signature differs from live on {diff}/{len(seeds)} seeds -- the patch BITES")

    # --- 1. FORMATIONS ----------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("1. FORMATIONS -- DID THE HQs GIVE ANY FORMATION A PARENT, AND CAN IT CONCENTRATE?")
    print("=" * 100)
    fb = os.path.join(d, "..", "gate81d_BASE_formations.json")
    fh = os.path.join(d, "..", "gate81d_HEAD_formations.json")
    if os.path.exists(fb) and os.path.exists(fh):
        B, H = load(fb), load(fh)
        print("  (a) ON PAPER -- a formation 'has an HQ' when the [4.45] tree's parent counter resolves")
        print("      to a mustered unit id (game.oob._seed_organization wrote Unit.assigned_to).")
        for k in ("units_the_war_ever_contains", "paper_parent_counters_named_by_the_4_45_tree"):
            print(f"      {k:52s} {B[k]:>6}  ->{H[k]:>6}")
        for k in ("formations_with_a_live_parent",
                  "formations_whose_parent_is_a_COMBAT_counter",
                  "formations_whose_parent_is_a_BARE_HQ"):
            b, h = B[k], H[k]
            print(f"      {k:52s} AXIS {b['AXIS']:>3}->{h['AXIS']:<3} "
                  f"ALLIED {b['ALLIED']:>3}->{h['ALLIED']:<3} total {b['total']:>3}->{h['total']}")
        # Unit carries no `counter` attribute -- the OOB slugifies it into `id`, which is what
        # Unit.assigned_to holds, so parent_id is the only key the two arms can be diffed on.
        bp = {r["parent_id"] for r in B["formations"]}
        hp = {r["parent_id"] for r in H["formations"]}
        gained = sorted(hp - bp)
        lost = sorted(bp - hp)
        print(f"\n      FORMATIONS THAT NOW HAVE AN HQ AND HAD NONE: {len(gained)}")
        hkids = {r["parent_id"]: r["children"] for r in H["formations"]}
        hside = {r["parent_id"]: r["parent_side"] for r in H["formations"]}
        hcomb = {r["parent_id"]: r["parent_is_combat"] for r in H["formations"]}
        for c in gained:
            print(f"        + {c:28s} {hside[c]:6s} {hkids[c]:>3} sub-units now parented   "
                  f"(parent is_combat={hcomb[c]})")
        if lost:
            print(f"      parents that went away: {lost}")
        bhq = {x["id"] for x in B["hq_roster"]}
        childless = [x for x in H["hq_roster"] if x["id"] not in bhq and x["children_assigned"] == 0]
        print(f"      HQs this slice seeded that parent NOTHING: {len(childless)} "
              f"{[x['id'] for x in childless]}")
        print(f"\n      HQ COUNTERS IN THE ORDER OF BATTLE: {len(B['hq_roster'])} -> {len(H['hq_roster'])}")
        print("      role census (side/role -> count):")
        allk = sorted(set(B["role_census"]) | set(H["role_census"]))
        for k in allk:
            b, h = B["role_census"].get(k, 0), H["role_census"].get(k, 0)
            flag = "   <-- moved" if b != h else ""
            print(f"        {k:24s} {b:>4} -> {h:<4}{flag}")
        print("\n  (b) ON THE MAP -- what campaign_policy.concentrate_formations proposes at t0:")
        for side in ("AXIS", "ALLIED"):
            b = B["concentrate_formations_at_t0"][side]
            h = H["concentrate_formations_at_t0"][side]
            print(f"        {side:6s} attach orders {b['attach']:>3} -> {h['attach']:<3}   "
                  f"distinct parents {len(b['distinct_parents_attached_to'])} -> "
                  f"{len(h['distinct_parents_attached_to'])}")

    print("\n  (c) IN PLAY -- every UNIT_ATTACHED of the full 111-turn war:")
    print(f"      {'seed':>6} | {'BASE attach':>26} | {'HEAD attach':>26} | {'ENGOFF attach':>26}")
    for s in seeds:
        row = [f"{s:>6}"]
        for arm in ("BASE", "HEAD", "ENGOFF"):
            r = S.get(arm, {}).get(s)
            row.append(f"{str(r['unit_attached']) if r else '-':>26}")
        print("      " + " | ".join(row))
    newhq = set()
    if os.path.exists(fh) and os.path.exists(fb):
        newhq = {c for c in gained}
    for arm in ("BASE", "HEAD"):
        pool = {}
        for s in seeds:
            r = S.get(arm, {}).get(s)
            if r:
                for k, v in r["unit_attached_by_parent"].items():
                    pool[k] = pool.get(k, 0) + v
        print(f"\n      {arm}: attach parents actually used across all seeds ({len(pool)} distinct)")
        for k, v in sorted(pool.items(), key=lambda kv: -kv[1]):
            mark = "  <-- an HQ THIS SLICE SEEDED" if k.split("/", 1)[-1] in newhq else ""
            print(f"        {k:44s} {v:>5}{mark}")

    print("\n  (d) [15.53] ORGANIZATION-SIZE -- COMBAT_RESOLVED payloads carrying attacker_size")
    print("      (engine.py:5586 records the tier only when max(size) >= 2), with the column shift")
    print("      re-derived through combat_tables.org_size_shift:")
    print(f"      {'seed':>6} | {'arm':>7} | {'recorded':>8} | {'shifting':>8} | {'favAXIS':>8} | "
          f"{'favALLIED':>9} | tiers")
    for s in seeds:
        for arm in ("BASE", "HEAD", "ENGOFF"):
            r = S.get(arm, {}).get(s)
            if not r:
                continue
            o = r["org_size_15_53"]
            print(f"      {s:>6} | {arm:>7} | {o.get('recorded_total',0):>8} | "
                  f"{o.get('shifting_total',0):>8} | {o.get('favoured_AXIS',0):>8} | "
                  f"{o.get('favoured_ALLIED',0):>9} | {r['org_size_tiers']}")
    for arm in ("BASE", "HEAD", "ENGOFF"):
        if arm not in S:
            continue
        tot = sum(S[arm][s]["org_size_15_53"].get("recorded_total", 0) for s in S[arm])
        ax = sum(S[arm][s]["org_size_15_53"].get("favoured_AXIS", 0) for s in S[arm])
        al = sum(S[arm][s]["org_size_15_53"].get("favoured_ALLIED", 0) for s in S[arm])
        print(f"      TOTAL {arm:>7}: recorded {tot:>5}   favouring AXIS {ax:>5}   "
              f"favouring ALLIED {al:>5}")

    # --- 2. THE (ENG) CORRECTION ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("2. THE 23.11 (ENG) CORRECTION -- THE SEPTEMBER-1940 OPENING")
    print("=" * 100)
    print("  Ownership is the victory projection's own 64.73 test (campaign_victory._occupier: a")
    print("  SUPPLIED combat unit of >=1 TOE strength), sampled at every Game-Turn boundary.")
    for city in ("Sidi Barrani", "Sollum"):
        print(f"\n  {city.upper()} -- holder at Game-Turn:")
        print(f"      {'seed':>6} | {'arm':>7} | " + " | ".join(f"GT{t:<3}" for t in
                                                                (1, 5, 10, 20, 30, 50, 70, 90, 111)))
        for s in seeds:
            for arm in ("BASE", "ENGOFF", "HEAD"):
                r = S.get(arm, {}).get(s)
                if not r:
                    continue
                ch = r["city_change_points"].get(city, [])
                cells = " | ".join(f"{track_at(ch, t)[:5]:<5}" for t in
                                   (1, 5, 10, 20, 30, 50, 70, 90, 111))
                print(f"      {s:>6} | {arm:>7} | {cells}")
    print("\n  CITIES BANKED AT GT30 (the window the restated tests pin):")
    print(f"      {'seed':>6} | {'arm':>7} | {'CW':>3} | {'AX':>3} | Commonwealth set")
    for s in seeds:
        for arm in ("BASE", "ENGOFF", "HEAD"):
            r = S.get(arm, {}).get(s)
            if not r:
                continue
            b = r["banked"].get("GT30", {"AXIS": [], "ALLIED": []})
            print(f"      {s:>6} | {arm:>7} | {len(b['ALLIED']):>3} | {len(b['AXIS']):>3} | "
                  f"{b['ALLIED']}")
    for arm in ("BASE", "ENGOFF", "HEAD"):
        if arm not in S:
            continue
        tot = sum(len(S[arm][s]["banked"].get("GT30", {}).get("ALLIED", [])) for s in S[arm])
        tax = sum(len(S[arm][s]["banked"].get("GT30", {}).get("AXIS", [])) for s in S[arm])
        print(f"      TOTAL {arm:>7}: Commonwealth {tot:>3} city-holdings at GT30, Axis {tax:>3}")

    print("\n  THE AXIS GROUND HIGH-WATER MARK (furthest-east axial r a counter ever reached;")
    print("  El Alamein is r118, Alexandria r126):")
    print(f"      {'seed':>6} | " + " | ".join(f"{a:>16}" for a in ("BASE", "ENGOFF", "HEAD")))
    for s in seeds:
        cells = []
        for arm in ("BASE", "ENGOFF", "HEAD"):
            r = S.get(arm, {}).get(s)
            cells.append(f"{'r%s (GT%s)' % (r['axis_ground_high_water_r'], r['axis_ground_high_water_turn']) if r else '-':>16}")
        print(f"      {s:>6} | " + " | ".join(cells))

    # --- 3. THE BALANCE ---------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("3. THE BALANCE -- winner and the 64.76 grade, per seed, per arm")
    print("=" * 100)
    print(f"      {'seed':>6} | {'arm':>7} | {'winner':>7} | grade")
    for s in seeds:
        for arm in ("BASE", "ENGOFF", "HEAD"):
            r = S.get(arm, {}).get(s)
            if not r:
                continue
            print(f"      {s:>6} | {arm:>7} | {str(r['winner']):>7} | {r['reason']}")
    print("\n  VP DELTA vs BASE (positive = toward the Commonwealth):")
    print(f"      {'seed':>6} | {'BASE VP':>16} | {'HEAD VP':>16} | {'d(AX)':>7} | {'d(CW)':>7} | sign")
    signs = []
    for s in seeds:
        b, h = S.get("BASE", {}).get(s), S.get("HEAD", {}).get(s)
        if not (b and h):
            continue
        vb, vh = vp(b["reason"]), vp(h["reason"])
        if not (vb and vh):
            continue
        dax, dcw = vh[0] - vb[0], vh[1] - vb[1]
        sign = "CW" if (dcw - dax) > 0 else ("AXIS" if (dcw - dax) < 0 else "none")
        signs.append(sign)
        print(f"      {s:>6} | {('%g-%g' % vb):>16} | {('%g-%g' % vh):>16} | "
              f"{dax:>+7g} | {dcw:>+7g} | {sign}")
    print(f"      sign tally BASE->HEAD: {{'CW': {signs.count('CW')}, 'AXIS': {signs.count('AXIS')},"
          f" 'none': {signs.count('none')}}}  of {len(signs)} seeds")
    print("\n  VP DELTA, the (ENG) correction ALONE (eng_off -> HEAD, same tree otherwise):")
    signs2 = []
    for s in seeds:
        e, h = S.get("ENGOFF", {}).get(s), S.get("HEAD", {}).get(s)
        if not (e and h):
            continue
        ve, vh = vp(e["reason"]), vp(h["reason"])
        if not (ve and vh):
            continue
        dax, dcw = vh[0] - ve[0], vh[1] - ve[1]
        sign = "CW" if (dcw - dax) > 0 else ("AXIS" if (dcw - dax) < 0 else "none")
        signs2.append(sign)
        print(f"      {s:>6} | {('%g-%g' % ve):>16} | {('%g-%g' % vh):>16} | "
              f"{dax:>+7g} | {dcw:>+7g} | {sign}")
    print(f"      sign tally ENGOFF->HEAD: {{'CW': {signs2.count('CW')}, "
          f"'AXIS': {signs2.count('AXIS')}, 'none': {signs2.count('none')}}} of {len(signs2)} seeds")

    # --- 4. SANITY --------------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("4. SANITY -- did any of it break something absurd?")
    print("=" * 100)
    cols = ("axis_combat_units_alive", "cw_combat_units_alive", "units_that_never_moved",
            "units_on_map_at_setup_that_never_moved", "units_the_war_contains")
    print(f"      {'seed':>6} | {'arm':>7} | " + " | ".join(f"{c[:14]:>14}" for c in cols)
          + " | combats AX/CW | surrenders AX/CW")
    for s in seeds:
        for arm in ("BASE", "ENGOFF", "HEAD"):
            r = S.get(arm, {}).get(s)
            if not r:
                continue
            c = r["combats_by_side"]
            su = r["surrender_combats_by_side"]
            print(f"      {s:>6} | {arm:>7} | " + " | ".join(f"{r[c2]:>14}" for c2 in cols)
                  + f" | {c.get('AXIS',0):>6}/{c.get('ALLIED',0):<6}"
                  + f" | {su.get('AXIS',0):>6}/{su.get('ALLIED',0):<6}")
    print("\n  THE FATE OF EVERY HQ THIS SLICE SEEDED (HEAD, seed %s):" % seeds[0])
    h = S["HEAD"][seeds[0]]
    b = S["BASE"][seeds[0]]
    base_hq = {x["id"] for x in b["hq_fate"]}
    for x in h["hq_fate"]:
        if x["id"] in base_hq:
            continue
        print(f"      + {str(x['id']):28s} {x['side']:6s} eng={str(x['engineer'] or '-'):12s} "
              f"moved={str(x['moved_at_least_once']):5s} alive={str(x['alive_at_end']):5s} "
              f"on_map={str(x['on_map_at_end']):5s} hex={x['hex_at_end']}")
    print("\n  ORDER_REJECTED totals, all seeds:")
    for arm in ("BASE", "HEAD", "ENGOFF"):
        if arm not in S:
            continue
        pool = {}
        for s in S[arm]:
            for k, v in S[arm][s]["order_rejected"].items():
                pool[k] = pool.get(k, 0) + v
        print(f"      {arm:>7}: {dict(sorted(pool.items()))}")
    print("\n  (game/invariants.py runs after every applied event and must never raise.  Twenty-eight")
    print("   completed 111-turn campaigns here -- four arms x seven seeds -- plus the fourteen the")
    print("   mechanism probe below folds, are themselves that proof.)")

    # --- 5. THE MECHANISM -------------------------------------------------------------------------
    mb = os.path.join(d, "mech_BASE.json")
    mh = os.path.join(d, "mech_HEAD.json")
    if not (os.path.exists(mb) and os.path.exists(mh)):
        return 0
    MB, MH = by_seed(load(mb)), by_seed(load(mh))
    print("\n" + "=" * 100)
    print("5. THE MECHANISM -- WHERE THE VICTORY POINTS ACTUALLY WENT")
    print("=" * 100)
    print("  The 64.76 total is 64.73 Geographic Occupation + 64.75 Withdrawal (Commonwealth only)")
    print("  + 64.74 unused Replacement Points.  Split it.")
    print("\n  (a) 64.73 GEOGRAPHIC -- the ground.  Axis Occupation Points from the cities its supplied")
    print("      combat units hold at the final Game-Turn:")
    vps = {"Mersa Matruh": (100, 10), "Sidi Barrani": (50, 10), "Siwa": (20, 10), "Jalo": (10, 20),
           "Giarabub": (15, 10), "Bardia": (100, 50), "Sollum": (25, 10), "Tobruk": (200, 100),
           "Derna": (25, 50), "Benghazi": (75, 100)}
    print(f"      {'seed':>6} | {'BASE AXgeo':>10} | {'HEAD AXgeo':>10} | {'BASE CWgeo':>10} | "
          f"{'HEAD CWgeo':>10} | HEAD Axis cities")
    tb = th = cb = cw = 0
    for s in seeds:
        b, h = S["BASE"][s]["banked"]["final"], S["HEAD"][s]["banked"]["final"]
        bg = sum(vps[c][0] for c in b["AXIS"]);  hg = sum(vps[c][0] for c in h["AXIS"])
        bc = sum(vps[c][1] for c in b["ALLIED"]); hc = sum(vps[c][1] for c in h["ALLIED"])
        tb += bg; th += hg; cb += bc; cw += hc
        print(f"      {s:>6} | {bg:>10} | {hg:>10} | {bc:>10} | {hc:>10} | {h['AXIS']}")
    print(f"      {'MEAN':>6} | {tb/len(seeds):>10.1f} | {th/len(seeds):>10.1f} | "
          f"{cb/len(seeds):>10.1f} | {cw/len(seeds):>10.1f}")
    print("\n  (b) 64.74 -- the AXIS INFANTRY REPLACEMENT POOL (1,600 points; the Commonwealth scores")
    print("      ZERO replacement VP under the 2026-07-24 owner ruling, so this term is one-sided).")
    print("      unused = 1600 - the [20.66] rebuild spend, read off the UNIT_REBUILT log:")
    print(f"      {'seed':>6} | {'BASE spend':>10} {'HEAD spend':>10} {'d':>7} | "
          f"{'BASE 64.74':>10} {'HEAD 64.74':>10} {'d':>7} | "
          f"{'BASE AXsteps':>12} {'HEAD AXsteps':>12} {'d':>7}")
    dsp = dst = []
    dsp, dst, d74 = [], [], []
    for s in seeds:
        b, h = MB[s], MH[s]
        bs = b["replacement_spend_by_pool"].get("AXIS/infantry", 0)
        hs = h["replacement_spend_by_pool"].get("AXIS/infantry", 0)
        b7 = b["unused_replacement_vp_64_74"]["AXIS"]
        h7 = h["unused_replacement_vp_64_74"]["AXIS"]
        bl = b["steps_lost_by_side"].get("AXIS", 0)
        hl = h["steps_lost_by_side"].get("AXIS", 0)
        dsp.append(hs - bs); d74.append(h7 - b7); dst.append(hl - bl)
        print(f"      {s:>6} | {bs:>10} {hs:>10} {hs-bs:>+7} | {b7:>10} {h7:>10} {h7-b7:>+7} | "
              f"{bl:>12} {hl:>12} {hl-bl:>+7}")
    print(f"      SIGNS: Axis rebuild spend UP on {sum(1 for x in dsp if x > 0)}/{len(seeds)} seeds "
          f"(mean {sum(dsp)/len(seeds):+.0f}); Axis 64.74 DOWN on "
          f"{sum(1 for x in d74 if x < 0)}/{len(seeds)} (mean {sum(d74)/len(seeds):+.0f}); "
          f"Axis steps lost UP on {sum(1 for x in dst if x > 0)}/{len(seeds)} "
          f"(mean {sum(dst)/len(seeds):+.0f})")
    print("\n  (c) THE FIVE COUNTERS THE SLICE TOOK OUT OF THE AXIS LINE -- what became of them")
    print("      (the four [23.11] '(ENG)' Engineer Battalions and the 1st Libyan Division HQ^E),")
    print(f"      seed {seeds[0]}:")
    fb = {x["id"]: x for x in MB[seeds[0]]["the_five_reroled_counters"]}
    for x in MH[seeds[0]]["the_five_reroled_counters"]:
        b = fb.get(x["id"], {})
        print(f"        {x['id']:24s} BASE is_combat={str(b.get('is_combat')):5s} "
              f"moved={str(b.get('moved_at_least_once')):5s} end_strength={b.get('strength_at_end')}"
              f"   ->   HEAD is_combat={str(x['is_combat']):5s} "
              f"moved={str(x['moved_at_least_once']):5s} end_strength={x['strength_at_end']}")
    print("\n  (d) WHO NEVER MOVED IN 111 GAME-TURNS, by role (seed %s):" % seeds[0])
    b, h = MB[seeds[0]]["never_moved_by_role"], MH[seeds[0]]["never_moved_by_role"]
    for k in sorted(set(b) | set(h)):
        print(f"        {k:24s} {b.get(k,0):>4} -> {h.get(k,0):<4}")
    print("\n  (e) combat counters at setup / alive at the end:")
    for s in seeds[:1]:
        print(f"        BASE  AXIS {MB[s]['axis_combat_counters_at_setup']:>4} -> "
              f"{MB[s]['axis_combat_counters_alive']:<4}   ALLIED "
              f"{MB[s]['cw_combat_counters_at_setup']:>4} -> {MB[s]['cw_combat_counters_alive']}")
        print(f"        HEAD  AXIS {MH[s]['axis_combat_counters_at_setup']:>4} -> "
              f"{MH[s]['axis_combat_counters_alive']:<4}   ALLIED "
              f"{MH[s]['cw_combat_counters_at_setup']:>4} -> {MH[s]['cw_combat_counters_alive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
