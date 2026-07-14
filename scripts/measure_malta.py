"""WHAT IS MALTA WORTH? -- the A/B that the shared-RNG engine could not take.

    python3 -m scripts.measure_malta                    # the 5 canonical seeds
    python3 -m scripts.measure_malta --seeds 1941 7     # a subset

THE MEASUREMENT THIS REPLACES. The air audit ran this comparison on the old engine and concluded
"Malta is causally inert -- cranked to the rule-41.66 ceiling it denies 342,000 Fuel Points and the
victory score does not move." That went into project memory as a settled dead end. IT WAS AN
ARTEFACT OF A BROKEN INSTRUMENT: the engine drew every die -- weather, combat, breakdown, morale --
from ONE random.Random, and engine._interdict drew its two [41.66] dice ONLY when an
InterdictionOrder covered the lane. So changing the NUMBER of Malta orders reshuffled the dice every
other subsystem saw for the rest of the war, and drowned the signal in +-200 VP of noise.

HOW THIS A/B HOLDS THE DICE STILL. game.dice gives interdiction its own stream, and BOTH ARMS SEED
111 ORDERS on Malta's lane -- one per Game-Turn -- so interdiction consumes its stream at exactly
the same rate in both:

  * arm OFF:  bomb_points=1   -- the [41.66] CRT's flat-0% column. It DRAWS its two dice and denies
                                 nothing. This is Malta switched off WITHOUT switching off its dice.
  * arm MAX:  bomb_points=500 -- the CRT's top column (20-50% of every cargo, rule 41.66).

Both arms therefore roll the IDENTICAL interdiction dice; they differ only in which column those
dice are read on. One variable. The other two interdicted lanes (6 = Italy->Tobruk, SEA-TOBRUK =
the Commonwealth ferry) are left exactly as the campaign seeds them, in both arms.

WHAT IS STILL NOT A MEASUREMENT. Five seeds is not a distribution. Malta really does sink cargo, so
the two arms diverge downstream and consume their OTHER streams differently from then on -- that is
inherent to a stochastic simulation and no stream discipline removes it (see game/dice.py). Read the
SIGN and the MAGNITUDE across seeds; do not read a single seed as a fact.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.campaign_policy import (CampaignAxisPolicy,               # noqa: E402
                                  CampaignCommonwealthPolicy)
from game.campaign_victory import CampaignVictory                   # noqa: E402
from game.engine import run                                         # noqa: E402
from game.events import EventKind, Side                             # noqa: E402
from game.scenario import campaign                                  # noqa: E402
from game.state import InterdictionOrder                            # noqa: E402

SEEDS = (1941, 7, 2026, 1, 99)
MALTA_LANE = "2"        # scenario._campaign_malta_interdiction: the Axis Mediterranean convoy lane
OFF, MAX = 1, 500       # the flat-0% column, and the top column of the [41.66] CRT


def _with_malta(state, bomb_points: int):
    """The campaign with Malta's lane bombed at `bomb_points` EVERY Game-Turn, and every other
    interdicted lane left exactly as seeded. 111 orders in either arm -> the interdiction stream is
    consumed at the same rate whichever column we read."""
    others = tuple(o for o in state.interdictions if o.lane != MALTA_LANE)
    malta = tuple(InterdictionOrder(MALTA_LANE, t, bomb_points)
                  for t in range(1, state.max_turns + 1))
    return replace(state, interdictions=others + malta)


def _score(state) -> tuple[int, int]:
    """The rule-64.73 tally of the final board -- the campaign's real scoreboard. (GameState.vp is
    the toy scenarios' counter and stays 0-0 all campaign; CampaignVictory.decide computes the
    score at the final turn and folds it into the reason string, so read it the same way.)"""
    vic = CampaignVictory()
    axis = cwlth = 0
    for ax, avp, cvp, _name in vic.cities:
        side = vic._occupier(state, ax)
        if side == Side.AXIS:
            axis += avp
        elif side == Side.ALLIED:
            cwlth += cvp
    return axis, cwlth


def _play(seed: int, bomb_points: int) -> dict:
    res = run(_with_malta(campaign(seed=seed), bomb_points),
              CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    axis, cwlth = _score(res.final)
    denied = sum(e.payload["tons_lost"] for e in res.events
                 if e.kind is EventKind.CONVOY_INTERDICTED and e.payload["lane"] == MALTA_LANE)
    dice = tuple(d for e in res.events if e.kind is EventKind.CONVOY_INTERDICTED
                 and e.payload["lane"] == MALTA_LANE for d in e.rng_draws)
    return {"seed": seed, "bomb": bomb_points, "axis": axis, "allied": cwlth,
            "winner": None if res.winner is None else res.winner.value,
            "reason": res.reason, "tons_denied": denied, "dice": dice}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    args = ap.parse_args()

    jobs = [(s, b) for s in args.seeds for b in (OFF, MAX)]
    with ProcessPoolExecutor() as pool:                    # 16 threads: one campaign per worker
        out = list(pool.map(_play, [j[0] for j in jobs], [j[1] for j in jobs]))
    by = {(r["seed"], r["bomb"]): r for r in out}

    print(f"\nMALTA A/B -- bomb={OFF} (CRT flat-0% column) vs bomb={MAX} (CRT top column)")
    print("the full 111-turn campaign, CampaignAxisPolicy vs CampaignCommonwealthPolicy\n")
    hdr = f"{'seed':>5} | {'MALTA OFF (bomb=1)':^30} | {'MALTA MAX (bomb=500)':^30} | {'swing':>18}"
    print(hdr)
    print("-" * len(hdr))
    for s in args.seeds:
        off, mx = by[(s, OFF)], by[(s, MAX)]
        o = f"{off['reason'].split(':')[0][:17]:17s} {off['axis']:3d}-{off['allied']:<3d}"
        m = f"{mx['reason'].split(':')[0][:17]:17s} {mx['axis']:3d}-{mx['allied']:<3d}"
        # the Axis margin: how far ahead the Axis is. Malta should push it DOWN.
        swing = (mx["axis"] - mx["allied"]) - (off["axis"] - off["allied"])
        flip = "  <-- FLIPS THE WINNER" if off["winner"] != mx["winner"] else ""
        print(f"{s:>5} | {o:^30} | {m:^30} | {swing:>+7d} VP{flip}")

    print("\nthe dice held still (the whole point):")
    for s in args.seeds:
        off, mx = by[(s, OFF)], by[(s, MAX)]
        n = min(len(off["dice"]), len(mx["dice"]))
        shared = off["dice"][:n] == mx["dice"][:n]
        print(f"  seed {s:>5}: first {n:3d} Malta dice identical in both arms: {shared} "
              f"| tons denied  off={off['tons_denied']:>9,}  max={mx['tons_denied']:>9,}")
    print("\n(the arms diverge in draw COUNT once sunk cargo changes the war -- that is the signal,")
    print(" not the noise. Five seeds is not a distribution: read the sign, not one seed.)\n")


if __name__ == "__main__":
    main()
