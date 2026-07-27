"""GATE [8.45] -- THE A/B: does the Desert last-mile gate stop the Axis, and does it move the war?

Read-only. Runs the full 111-turn campaign for a list of seeds and reports the four things the
gate asks: the front, the high-water mark, the balance, and the sanity of the logistics.

Written so the SAME file runs unmodified in the pre-slice worktree (4a08f4d, where neither
terrain.desert_barred nor supply.TRUCK_MOBILITY exists) and at HEAD -- every HEAD-only symbol is
reached through a guarded getattr, so an arm that lacks it reports null rather than crashing.

Usage:
  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate845_ab.py --seeds 1941 7 4 24 2026 99 1 \
      --workers 7 --out <path.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

# Movement event kinds that a GROUND unit emits (as opposed to an air mission or a convoy), so the
# "furthest east" mark can be attributed instead of being an unattributed max over every payload.
GROUND_KINDS = {"UNIT_MOVED", "UNIT_RETREATED", "REACTION_MOVED"}


def _hex_of(payload):
    for key in ("to", "hex"):
        h = payload.get(key)
        if isinstance(h, (list, tuple)) and len(h) == 2 and all(isinstance(x, int) for x in h):
            return tuple(h)
    return None


# THIRD ARM.  The BASE worktree is the whole slice (the [8.45] gate AND its review repair's OOB
# corrections -- the 15 Kradschutzen retype, the [54.2] truck-class pathing).  tests/baselines.py
# already attributes the two benchmark signatures to the OOB retype, not the gate; this arm does
# the same for the campaign, by running HEAD's bodies with ONLY the Desert gate switched off.
#
# NEUTER SITE: game.movement.desert_barred.  movement.py does `from .terrain import desert_barred`,
# so patching game.terrain.desert_barred would NOT reach step_cost's already-bound reference (the
# trap tests/baselines.py records).  step_cost is the rule's ONLY call site -- verified by grep --
# so this switches the gate off whole, and nothing else.  Proven live per worker in _report.
NEUTER_DESERT = False


def _install_neuter() -> None:
    import game.movement as movement
    movement.desert_barred = lambda m: False


def report(seed: int) -> dict:
    try:
        if NEUTER_DESERT:
            _install_neuter()
        return _report(seed)
    except Exception as exc:                                # noqa: BLE001 - a driver, not engine code
        return {"seed": seed, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-2000:]}


def _report(seed: int) -> dict:
    from game import cna_map, coords, terrain as terrain_mod
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import determinism_signature, run
    from game.events import Side
    from game.hexmap import neighbors
    from game.movement import step_cost
    from game.scenario import campaign
    from game.terrain import Terrain

    _, index = cna_map.load_sections("ABCDE")
    r_alamein = index["E3002"][1]

    init = campaign(seed=seed)
    res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final
    tmap = fin.terrain
    desert = {h for h, t in tmap.terrain.items() if t == Terrain.DESERT}

    # ---- 2. THE HIGH-WATER MARK, attributed -------------------------------------------------
    any_best, any_turn, any_kind = -1, None, None
    gnd_best, gnd_turn = -1, None
    per_kind: Counter = Counter()
    rejects: Counter = Counter()
    truck_moves = 0
    truck_moves_into_desert = 0
    unit_moves_into_desert = 0
    # LOGISTICS HEALTH -- can the Axis still feed and reach his own front, or did the gate strand
    # him?  These are the engine's own shortfall/starvation events, counted whole-war.
    WATCH = ("STORES_SHORTFALL", "UNIT_SURRENDERED", "UNIT_ELIMINATED", "SUPPLY_ARRIVED",
             "SUPPLY_DUMP_ESTABLISHED", "VEHICLE_BROKE_DOWN", "AMMO_SHORTFALL", "WATER_SHORTFALL",
             "FUEL_SHORTFALL", "TRUCK_MOVED", "UNIT_MOVED")
    watch: Counter = Counter()
    for e in res.events:
        kind = str(getattr(getattr(e, "kind", ""), "value", getattr(e, "kind", "")))
        p = e.payload or {}
        if kind in WATCH:
            watch[f"{kind}/{getattr(e.side, 'value', e.side)}"] += 1
        if kind == "ORDER_REJECTED":
            rejects[str(p.get("reason"))[:60]] += 1
        if kind == "TRUCK_MOVED":
            truck_moves += 1
            h = _hex_of(p)
            if h in desert:
                truck_moves_into_desert += 1
        if e.side != Side.AXIS:
            continue
        h = _hex_of(p)
        if h is None:
            continue
        if kind in GROUND_KINDS and h in desert:
            unit_moves_into_desert += 1
        if h[1] > any_best:
            any_best, any_turn, any_kind = h[1], getattr(e, "turn", None), kind
        if kind in GROUND_KINDS and h[1] > gnd_best:
            gnd_best, gnd_turn = h[1], getattr(e, "turn", None)
        if kind in GROUND_KINDS:
            per_kind[kind] = max(per_kind[kind], h[1])

    def _r(h):
        return h[1] if isinstance(h, tuple) else coords.to_axial(h)[1]

    def live(side):
        return [u for u in fin.units if u.side == side and getattr(u, "is_combat", True)
                and u.strength > 0 and fin.on_map(u)]

    axis_live, cw_live = live(Side.AXIS), live(Side.ALLIED)

    # ---- 4. SANITY: can every unit still legally step somewhere? -----------------------------
    stuck, in_barred_hex = [], []
    barred = getattr(terrain_mod, "desert_barred", None)
    for u in axis_live + cw_live:
        h = u.hex if isinstance(u.hex, tuple) else coords.to_axial(u.hex)
        exits = 0
        for nb in neighbors(h):
            if tmap.exists(nb) and step_cost(tmap, h, nb, u.mobility) is not None:
                exits += 1
        if exits == 0:
            stuck.append({"unit": u.id, "side": u.side.value, "mob": u.mobility.value,
                          "hex": list(h), "terrain": str(tmap.terrain.get(h))})
        if barred is not None and barred(u.mobility) and h in desert:
            in_barred_hex.append({"unit": u.id, "mob": u.mobility.value, "hex": list(h)})

    import game.movement as movement
    neuter_probe = {
        "movement.desert_barred(LIGHT_TRUCK)": bool(
            movement.desert_barred(terrain_mod.Mobility.LIGHT_TRUCK)),
        "movement.desert_barred(MOTORCYCLE)": bool(
            movement.desert_barred(terrain_mod.Mobility.MOTORCYCLE)),
    } if hasattr(movement, "desert_barred") else {"absent_in_this_tree": True}

    return {
        "seed": seed,
        "neuter_probe": neuter_probe,
        "winner": None if res.winner is None else res.winner.value,
        "reason": res.reason,
        "events": len(res.events),
        "signature": hashlib.blake2b(
            determinism_signature(res.events).encode(), digest_size=6).hexdigest(),
        "r_alamein": r_alamein,
        "axis_east_ever_any": any_best, "axis_east_ever_any_turn": any_turn,
        "axis_east_ever_any_kind": any_kind,
        "axis_east_ever_ground": gnd_best, "axis_east_ever_ground_turn": gnd_turn,
        "axis_east_ever_ground_by_kind": dict(per_kind),
        "axis_east_at_end": max((_r(u.hex) for u in axis_live), default=None),
        "cw_west_at_end": min((_r(u.hex) for u in cw_live), default=None),
        "axis_units_alive": len(axis_live), "cw_units_alive": len(cw_live),
        "truck_moves": truck_moves,
        "truck_moves_ending_in_desert": truck_moves_into_desert,
        "axis_ground_moves_into_desert": unit_moves_into_desert,
        "watch": dict(sorted(watch.items())),
        "rejects_total": sum(rejects.values()),
        "rejects_top": rejects.most_common(6),
        "stuck_units": stuck,
        "barred_units_standing_in_desert": in_barred_hex,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1941, 7, 4, 24, 2026, 99, 1])
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--neuter-desert", action="store_true",
                    help="HEAD's bodies with ONLY the [8.45] Desert gate switched off")
    args = ap.parse_args()
    global NEUTER_DESERT
    NEUTER_DESERT = args.neuter_desert

    doc: dict = {"seeds": args.seeds, "results": []}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(report, args.seeds):
            doc["results"].append(r)
            with open(args.out, "w") as f:
                json.dump(doc, f, indent=1)
            if "ERROR" in r:
                print(f"  seed {r['seed']}: {r['ERROR']}", flush=True)
            else:
                print(f"  seed {r['seed']}: {r['winner']} | ever r{r['axis_east_ever_ground']} "
                      f"(any r{r['axis_east_ever_any']}) | end r{r['axis_east_at_end']} | "
                      f"stuck={len(r['stuck_units'])} | {r['reason']}", flush=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
