"""THE CAMPAIGN SUCCESS CRITERION: how much of each army can actually EAT, and where.

    python3 -m scripts.measure_campaign                     # the 5 canonical seeds
    python3 -m scripts.measure_campaign --seeds 1941 7      # a subset

WHY THIS EXISTS, AND WHY THE OBVIOUS METRIC IS A TRAP. "Supplied fraction" -- the share of an
army that can trace Fuel and Ammunition (rule 64.73's own occupation quality-test) -- counts a
division parked on the bottomless Cairo base as supplied. It is therefore MAXIMISED BY NOT
FIGHTING: an Eighth Army that never leaves the Delta scores ~100%, and a measurement that rewards
an army for standing still is measuring the wrong thing. Measured, the strict `keep_in_trace`
consolidation constraint took the "supplied fraction" from 29% to 91% precisely BY paralysing the
Commonwealth into the Delta -- a number that flattered the very defect it caused.

SO WE REPORT SUPPLIED **AND FORWARD**: a unit that can trace supply AND is standing somewhere that
costs the enemy something.

  * COMMONWEALTH: west of the Delta (r < 133 -- Alexandria is r=133, Cairo r=140). The Delta is the
    rule-57 base with unlimited supplies of every type "in Cairo at all times"; eating there is free
    and means nothing. Everything the Commonwealth can win (64.73: Matruh 10, Barrani 10, Sollum 10,
    Bardia 50, Tobruk 100, Derna 50, Benghazi 100) lies west of it.
  * AXIS: east of Benghazi (r > 20). Benghazi is the port the Mediterranean convoy lands at -- the
    Axis rear. An army sitting on its own quay is not fighting a desert campaign either.

The axial r-coordinate IS the east-west axis of this map (Benghazi r=20, Tobruk 66, Sollum 76,
Bardia 77, Barrani 86, Matruh 100, El Daba 113, El Hamman 124, Alexandria 133, Cairo 140), so a
half-open r test is the whole of "forward" -- no boxes to draw, and the same number the culmination
row reports.

ALSO REPORTED, because a campaign that is ALIVE must show them and a dead one cannot:
  * CULMINATION -- the furthest-EAST hex any Axis combat unit reached, by game-turn. The Italian
    10th Army beelining to r=133 (Alexandria) on Game-Turn 4 is the tell that nothing restrains it;
    Graziani actually halted at Sidi Barrani (r=86) for three months.
  * CITIES CHANGING HANDS -- which 64.73 city, which turn, to whom. A campaign in which nothing
    ever changes hands is not a campaign; the final score is just the September-1940 setup.
  * SEED DIVERGENCE -- the 64.76 grade and VP tally per seed. If every seed returns an IDENTICAL
    score the dice are irrelevant and the campaign is dead, whatever the grade says.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import apply                                     # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,            # noqa: E402
                                  CampaignCommonwealthPolicy, _can_trace)
from game.campaign_victory import load_victory_cities            # noqa: E402
from game.engine import run                                      # noqa: E402
from game.events import EventKind, Side                          # noqa: E402
from game import coords                                          # noqa: E402
from game.scenario import campaign                               # noqa: E402

SEEDS = (1941, 7, 2026, 1, 99)
PROBES = (20, 40, 60, 80, 111)

# The rear each side must get OUT of to be doing anything (see the module docstring). The axial
# r-coordinate is the east-west axis: bigger r is further east.
DELTA_R = 133          # Alexandria: the westernmost hex of the rule-57 Commonwealth base
BENGHAZI_R = 20        # the Axis port of arrival (56.2)


def forward(side: Side, hex_) -> bool:
    """Is this hex FORWARD for `side` -- out of its own rear and into the contested desert?"""
    return hex_[1] < DELTA_R if side == Side.ALLIED else hex_[1] > BENGHAZI_R


def snapshot(state, side: Side) -> tuple[int, int, int]:
    """(supplied-and-forward, forward, alive) combat units of `side` in this state."""
    live = [u for u in state.living(side) if u.is_combat]
    fwd = [u for u in live if forward(side, u.hex)]
    return sum(1 for u in fwd if _can_trace(state, u)), len(fwd), len(live)


def lorries(state, side: Side) -> tuple[int, int, int]:
    """[32.32] THE CONTESTED POOL: (committed, medium park, whole park) Truck Points of `side`.

    `committed` is the Truck Points standing UNDER a desert column and therefore NOT hauling
    freight -- thirty per depot on the move (32.32), drawn from the Medium class (32.51). This is
    the decision the rule creates and the one number that shows it being paid: every point here is
    a point of the 60.33/60.43 park that is carrying a depot instead of the army's fuel."""
    committed = sum(pts for legs in state.motorization.values() for tid, pts in legs
                    if (t := state.truck(tid)) is not None and t.side == side)
    park = [t for t in state.trucks if t.side == side]
    medium = sum(t.points for t in park if t.truck_class == "medium")
    return committed, medium, sum(t.points for t in park)


def measure(seed: int) -> dict:
    """Run one full campaign and read the criterion off it.

    The probes REPLAY the log rather than hooking the engine: game.apply.fold is the engine's own
    fold, so the state at the end of Game-Turn N is exactly the state the engine held there, and
    the measurement adds no seam to the thing it measures (and no callback to run())."""
    initial = campaign(seed=seed)
    result = run(initial, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    cities = {coords.to_axial(coords.parse(c["hex"])): c["name"]
              for c in load_victory_cities()["cities"]}

    # Fold the log once, snapshotting only at the CLOSE of each probe turn (a snapshot Dijkstras
    # every unit's trace, so it must not run per-event).
    probes: dict[int, dict] = {}
    pool: dict[int, dict] = {}
    peak_columns = {Side.AXIS: 0, Side.ALLIED: 0}
    tied_up = {Side.AXIS: 0, Side.ALLIED: 0}      # Truck-Point-OpStages spent carrying depots
    stages = 0
    state = initial
    for e, nxt in zip(result.events, result.events[1:] + [None]):
        state = apply(state, e)
        if e.kind == EventKind.STAGE_ADVANCED or e.kind == EventKind.TURN_ADVANCED:
            stages += 1
            for s in (Side.AXIS, Side.ALLIED):
                c, _, _ = lorries(state, s)
                tied_up[s] += c
                peak_columns[s] = max(peak_columns[s], c // 30)
        closing = nxt is None or nxt.turn != e.turn
        if closing and e.turn in PROBES:
            probes[e.turn] = {s: snapshot(state, s) for s in (Side.AXIS, Side.ALLIED)}
            pool[e.turn] = {s: lorries(state, s) for s in (Side.AXIS, Side.ALLIED)}

    # Culmination: the furthest-east hex any Axis combat unit stood on, per game-turn.
    east: dict[int, int] = defaultdict(int)
    axis_ids = {u.id for u in initial.units if u.side == Side.AXIS and u.is_combat}
    for e in result.events:
        if e.kind == EventKind.UNIT_MOVED and e.payload["unit_id"] in axis_ids:
            east[e.turn] = max(east[e.turn], e.payload["to"][1])

    # Cities changing hands (64.73), from the control log.
    flips = [(e.turn, cities[tuple(e.payload["coord"])], e.payload["control"])
             for e in result.events
             if e.kind == EventKind.HEX_CONTROL_CHANGED and tuple(e.payload["coord"]) in cities]

    # [32.32] The column ledger: how often the staff raised one, and how often the rule REFUSED a
    # depot the lorries to move (the park dry -- the contention, in the log).
    attached = sum(1 for e in result.events if e.kind == EventKind.MOTORIZATION_ATTACHED)
    refused = sum(1 for e in result.events if e.kind == EventKind.ORDER_REJECTED
                  and "32.32" in str(e.payload.get("reason", "")))

    return {"seed": seed, "probes": probes, "east": dict(east), "flips": flips,
            "pool": pool, "peak_columns": peak_columns,
            "mean_tied": {s: tied_up[s] / max(1, stages) for s in tied_up},
            "attached": attached, "refused": refused,
            "winner": result.winner, "reason": result.reason}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    args = ap.parse_args()

    # One process per seed: a campaign is a ~30s single-threaded CPU grind and the seeds are wholly
    # independent, so the whole sweep costs one campaign of wall-clock.
    with ProcessPoolExecutor() as pool:
        runs = list(pool.map(measure, args.seeds))

    print("\n=== SUPPLIED AND FORWARD (combat units that can trace Fuel+Ammo, out of their own rear) ===")
    print("    CW forward = west of the Delta (r<133).  Axis forward = east of Benghazi (r>20).\n")
    for r in runs:
        print(f"  seed {r['seed']}")
        for side in (Side.AXIS, Side.ALLIED):
            row = []
            for gt in PROBES:
                p = r["probes"].get(gt)
                if p is None:
                    row.append(f"GT{gt}:   --   ")
                    continue
                sup, fwd, alive = p[side]
                pct = 100 * sup // alive if alive else 0
                row.append(f"GT{gt}: {sup:>2}/{alive:<2} ({pct:>3}%)")
            print(f"    {side.value:<7} " + "  ".join(row))
    print("\n=== [32.32] THE LORRY POOL: Truck Points CARRYING DEPOTS vs HAULING FREIGHT ===")
    print("    committed / medium park (whole park).  Thirty Medium Truck Points per desert column")
    print("    (32.32 + 32.51).  Axis medium park 150 of 215 on-map; Commonwealth 130 of 195.\n")
    for r in runs:
        print(f"  seed {r['seed']}")
        for side in (Side.AXIS, Side.ALLIED):
            row = []
            for gt in PROBES:
                p = r["pool"].get(gt)
                if p is None:
                    row.append(f"GT{gt}:   --   ")
                    continue
                com, med, whole = p[side]
                row.append(f"GT{gt}: {com:>3}/{med:<3}({100*com//med if med else 0:>2}%)")
            print(f"    {side.value:<7} " + "  ".join(row))
        print(f"      columns raised {r['attached']:>3} | depot-moves REFUSED for want of lorries "
              f"{r['refused']:>4} | peak columns AX {r['peak_columns'][Side.AXIS]} "
              f"CW {r['peak_columns'][Side.ALLIED]}")
        print(f"      mean Truck Points under a column, per OpStage: "
              f"AX {r['mean_tied'][Side.AXIS]:>5.1f}   CW {r['mean_tied'][Side.ALLIED]:>5.1f}")
    print("\n=== CULMINATION: furthest-EAST hex an Axis combat unit reached (r) ===")
    print("    Sidi Barrani r=86, Mersa Matruh r=100, Alexandria r=133 (the 64.71 objective)\n")
    for r in runs:
        peaks = [f"GT{gt}: r={max((v for t, v in r['east'].items() if t <= gt), default=0)}"
                 for gt in (4, 10, 20, 40, 111)]
        print(f"  seed {r['seed']:<5} " + "  ".join(peaks))
    print("\n=== CITIES CHANGING HANDS (64.73) ===")
    for r in runs:
        if not r["flips"]:
            print(f"  seed {r['seed']:<5} NOTHING EVER CHANGES HANDS")
            continue
        print(f"  seed {r['seed']:<5} " + ", ".join(f"GT{t} {n}->{c}" for t, n, c in r["flips"][:14])
              + (" ..." if len(r["flips"]) > 14 else ""))
    print("\n=== 64.76 GRADE (do the SEEDS DIVERGE? identical scores == the dice are irrelevant) ===")
    for r in runs:
        print(f"  seed {r['seed']:<5} {r['reason']}")
    print()


if __name__ == "__main__":
    main()
