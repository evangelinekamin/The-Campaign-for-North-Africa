"""IS ONE PROCESS ALLOWED TO RUN TWO CAMPAIGNS?  (read-only)

Port rule 4: "Same seed -> byte-identical event log across two runs."  The 8.2 A/B turned up three
seeds whose signature moved between two POOLED runs of the same tree, while the same seeds were
rock-solid across a dozen isolated single-campaign processes.  That points at cross-run state
leaking through the two module-level id()-keyed memos (supply._reach, tactics._PositionMemo), which
survive a run() call and are the only mutable module-level state in the engine keyed on an
ADDRESS rather than on content.

This runs the SAME seed N times IN ONE PROCESS and prints the signature each time.  Byte-identical
signatures every iteration => one process may run many campaigns.  Any drift => it may not, and
every pooled multi-seed measurement this project has ever taken is suspect.

Usage:  PYTHONPATH=<tree> python3 scratchpad/gate82_repeatability.py --seed 99 --repeats 3
"""
from __future__ import annotations

import argparse
import hashlib


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import determinism_signature, run
    from game.scenario import campaign

    sigs = []
    for i in range(args.repeats):
        res = run(campaign(seed=args.seed), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
        sig = hashlib.blake2b(
            determinism_signature(res.events).encode(), digest_size=8).hexdigest()
        sigs.append(sig)
        print(f"  in-process run {i + 1}: sig {sig}  events {len(res.events)}  "
              f"{res.reason}", flush=True)
    print(f"\nDISTINCT SIGNATURES IN ONE PROCESS: {len(set(sigs))} "
          f"({'REPEATABLE' if len(set(sigs)) == 1 else 'NOT REPEATABLE -- rule 4 violated'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
