"""Where do the two 8.2 arms first disagree?  Dumps a canonical per-event digest of one campaign
so the BASE and HEAD trees can be compared line by line.  Read-only.

Usage:  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate82_divergence.py --seed 24 --out <path>
"""
from __future__ import annotations

import argparse
import json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import run
    from game.scenario import campaign

    res = run(campaign(seed=args.seed), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    with open(args.out, "w") as f:
        for i, e in enumerate(res.events):
            k = getattr(e, "kind", "")
            f.write(json.dumps({
                "i": i,
                "turn": getattr(e, "turn", None),
                "kind": str(getattr(k, "value", k)),
                "side": str(getattr(getattr(e, "side", None), "value", getattr(e, "side", None))),
                "payload": e.payload,
                "rng": list(getattr(e, "rng_draws", ()) or ()),
            }, sort_keys=True, default=str) + "\n")
    print(f"wrote {args.out} ({len(res.events)} events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
