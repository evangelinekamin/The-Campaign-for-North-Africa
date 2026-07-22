"""[34.6] / [59.3] WHAT THE AIR FORCES ACTUALLY ARE -- the establishment read, by type, plus the
one downstream number the transcription was undertaken for.

    python3 -m scripts.measure_air                     # the establishment + one campaign seed
    python3 -m scripts.measure_air --seeds 4 1941 7    # more seeds for the Malta-raid count

THREE REPORTS:

  1. **THE ESTABLISHMENT BY TYPE**, at Game-Turn 1 and at Game-Turn 35, for both sides. They are the
     same list, and that IS the finding: [34.86] and [34.87], the two monthly Airplane Reinforcement
     Schedules, are untranscribed, so nothing brings an aeroplane into this war after the set-up and
     nothing (outside Malta) takes one out of it.

  2. **WHERE RULE 43 PUTS THEM**, at Game-Turn 1 and at Game-Turn 35 -- the Italy/Sicily, Crete and
     Africa split that sizes both the Malta raid (44.42) and the desert's Land Support.

  3. **HOW MANY OF THE CAMPAIGN'S 111 MALTA RAIDS DELIVER BOMB POINTS.** Before the transcription the
     Axis strike establishment was a ~4-plane proxy and percentages of it rounded to zero: 27 of 111.

     THE OWNER RULING THAT GOVERNED THIS NUMBER IS ANSWERED, AND THE KNOB THAT STOOD IN FOR IT IS
     GONE. [44.42] sizes the raid as a percentage of the Axis's ITALY/SICILY-based force; [60.32]
     prints "no planes start the game in Italy/Sicily"; for two blocks the bridge was a percentage
     in a data file and this script carried a `--discretionary-pct` flag to seed it for a run. The
     owner ruled on 2026-07-22 that [60.32] is a SET-UP rule and the bridge is a [42.1] TRANSFER
     MISSION, so the posture is now a DECISION a policy takes (Policy.air_transfer, the
     GameState.air_mediterranean ledger) and no percentage exists to seed. The flag was deleted on
     2026-07-22 rather than left: `axis_discretionary_italy_sicily_pct_43_1` was removed from
     data/malta_44.json by the ruling's own commit, which never touched scripts/, so the flag had
     been dying with a KeyError. To measure a different posture now, vary the POLICY.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import basing, roster
from game.engine import run
from game.events import EventKind, Side
from game.logistics_data import aircraft_characteristics_4_44
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.scenario import campaign

ROLES = ("fighters", "strike", "recon")


def _establishment_table() -> None:
    chart = aircraft_characteristics_4_44()
    for side in (Side.AXIS, Side.ALLIED):
        print(f"\n=== {side.value} -- [60.32]/[60.42] Initial Air Strengths ===")
        print(f"{'type':22} {'nation':12} {'role':9} {'avail':>6} {'ready':>6} {'pts':>6}")
        for m in roster.roster(side):
            rate = roster.rating(m.type, m.role)
            print(f"{m.type:22} {chart[m.type]['nation']:12} {m.role:9} "
                  f"{m.available:6} {m.refitted:6} {m.available * rate:6}")
        for role in ROLES:
            print(f"  {role:9} planes {roster.planes(side, role):4}  "
                  f"ready {roster.ready(side, role):4}  Air Points {roster.points(side, role):5}  "
                  f"fuel/plane {roster.fuel_per_plane(side, role)}")
        print(f"  TOTAL aeroplanes {sum(m.available for m in roster.roster(side))}")


def _basing_table(state) -> None:
    print("\n=== [43.1] where the Axis bomber arm is based ===")
    print(f"{'GT':>4} {'squadron':>9} {'Italy/Sicily':>13} {'Crete':>6} {'Africa':>7}")
    for turn in (1, 34, 35, 111):
        print(f"{turn:4} {roster.planes(Side.AXIS, 'strike'):9} "
              f"{basing.italy_sicily_planes(state, turn):13} "
              f"{basing.crete_planes(state, turn):6} "
              f"{basing.africa_planes(state, Side.AXIS, turn):7}")


def _malta_raids(seed: int, turns: int) -> None:
    res = run(campaign(seed=seed, max_turns=turns),
              CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    ordered = [e for e in res.events if e.kind == EventKind.MALTA_RAID_ORDERED]
    reinforced = Counter()
    for e in res.events:
        if e.kind == EventKind.MALTA_RAID_REINFORCED:
            reinforced[e.turn] += e.payload["bomb_points"]
    live = [e for e in ordered
            if e.payload["bomb_points"] + reinforced.get(e.turn, 0) > 0]
    pts = [e.payload["bomb_points"] + reinforced.get(e.turn, 0) for e in live]
    print(f"\nseed {seed}: Malta raids ordered {len(ordered)}, "
          f"delivering bomb points {len(live)} "
          f"({100 * len(live) // max(1, len(ordered))}%)")
    if pts:
        print(f"  bomb points per live raid: min {min(pts)} median {sorted(pts)[len(pts)//2]} "
              f"max {max(pts)}")
    lost = [e.payload for e in res.events if e.kind == EventKind.MALTA_PLANES_LOST]
    print(f"  Maltese capacity levels knocked down: {sum(p['levels'] for p in lost)}, "
          f"aeroplanes destroyed on the ground: {sum(p['lost'] for p in lost)}")
    _transfers(res)


def _transfers(res) -> None:
    """[42.1] The posture the `--discretionary-pct` knob used to seed, MEASURED instead of asserted:
    what the Axis policy actually flew to Sicily, out of which fields, and at what [37.24] ceiling."""
    moved = [e.payload for e in res.events if e.kind == EventKind.AIR_TRANSFERRED]
    out = [p for p in moved if p["to_mediterranean"]]
    home = [p for p in moved if not p["to_mediterranean"]]
    fields = Counter(p["departure"] for p in out)
    print(f"  [42.1] transfers to Italy/Sicily: {len(out)} flights, "
          f"{sum(p['planes'] for p in out)} aeroplanes, {sum(p['fuel'] for p in out)} Fuel Points; "
          f"home {len(home)} flights, {sum(p['planes'] for p in home)} aeroplanes")
    for fid, n in fields.items():
        cap = next(p["capacity"] for p in out if p["departure"] == fid)
        biggest = max(p["planes"] for p in out if p["departure"] == fid)
        print(f"    out of {fid}: {n} flights, largest {biggest}, [37.24] ceiling {cap}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[4])
    ap.add_argument("--turns", type=int, default=111)
    args = ap.parse_args()
    _establishment_table()
    _basing_table(campaign(seed=args.seeds[0], max_turns=1))
    for seed in args.seeds:
        _malta_raids(seed, args.turns)


if __name__ == "__main__":
    main()
