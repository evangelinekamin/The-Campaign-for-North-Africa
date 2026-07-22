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

  * arm OFF:   the Malta lane's orders replaced by static bomb_points=1 -- the [41.5] CRT's flat-0%
                 column. It DRAWS its two dice and denies nothing. Malta switched off WITHOUT
                 switching off its dice.
  * arm LIVE:  the campaign exactly as seeded -- rule 44's island (game.malta), whose strength each
                 Game-Turn is read off its surviving Capacity Levels and Swordfish.

Both arms therefore roll the IDENTICAL interdiction dice AND the identical rule-44 dice (the island
is seeded in both, so the Axis raid and the [44.5] repair draw the same); they differ only in
whether the convoy attack is read on Malta's live column or on the flat-0% one. One variable. The
other two interdicted lanes (6 = Italy->Tobruk, SEA-TOBRUK = the Commonwealth ferry) are left
exactly as the campaign seeds them, in both arms.

UPDATED FOR RULE 44 (Phase 5.4). The arms used to be bomb=1 against bomb=500 -- a measurement of
the CRT's dynamic range, made when Malta's strength was a constant somebody typed. There is now an
island to switch off instead, so the LIVE arm measures OUR Malta rather than the ceiling of the
table it reads.

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

from game import malta                                             # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,               # noqa: E402
                                  CampaignCommonwealthPolicy)
from game.campaign_victory import CampaignVictory                   # noqa: E402
from game.engine import run                                         # noqa: E402
from game.events import EventKind, Side                             # noqa: E402
from game.scenario import campaign                                  # noqa: E402
from game.state import InterdictionOrder                            # noqa: E402

SEEDS = (1941, 7, 2026, 1, 99)
MALTA_LANE = "2"        # scenario._campaign_malta_interdiction: the Axis Mediterranean convoy lane
OFF, LIVE = "off", "live"


# [42.1] THE `--discretionary-pct` KNOB IS DELETED, 2026-07-22, AND ITS DELETION IS THE POINT.
# It monkeypatched `axis_discretionary_italy_sicily_pct_43_1` into the rule-43 basing block to
# answer the then-open [60.32]-versus-[44.21] owner ruling for one run. The owner answered that
# ruling on 2026-07-22 -- [60.32] is a SET-UP rule, the bridge to Sicily is a [42.1] TRANSFER
# MISSION -- and the percentage was deleted from data/malta_44.json with it. NOTHING IN game/ HAS
# READ THAT KEY SINCE: the posture lives in GameState.air_mediterranean, written by a policy's
# transfer order. So the knob still patched a key, still printed "the OPEN Italy/Sicily basing
# ruling is SEEDED AT 10% for this run", and CHANGED NOT ONE DIE -- a driver announcing a posture
# it did not apply, which is worse than the sibling driver's honest KeyError and is exactly the
# failure mode the [63.46] transplant was withdrawn for. To measure a different Axis air posture
# now, vary the POLICY (campaign_policy.air_transfer_doctrine) and say which one ran.


def _arm(state, arm: str):
    """The campaign in one of the two arms. LIVE is the state exactly as the scenario built it;
    OFF swaps Malta's lane orders for static flat-0%-column ones, leaving their COUNT (one per
    Game-Turn) and everything else -- including the island, its raids and its repairs -- alone, so
    the interdiction stream is consumed at the same rate in both."""
    if arm == LIVE:
        return state
    others = tuple(o for o in state.interdictions if o.lane != MALTA_LANE)
    silent = tuple(InterdictionOrder(MALTA_LANE, t, 1)
                   for t in range(1, state.max_turns + 1))
    return replace(state, interdictions=others + silent)


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


def _lowest_total_capacity(start, events) -> int:
    """The island's LOW-WATER TOTAL Capacity Level over the whole war -- summed across all six
    Maltese facilities, which is the number both halves of rule 44 turn on (44.14's 18 planes per
    level is read off the total, and 44.12 says a facility may be reduced to zero but never
    destroyed).

    THIS FUNCTION EXISTS BECAUSE THE OBVIOUS ONE-LINER WAS WRONG AND THE ERROR WAS REPORTED AS A
    RESULT. The first version of this script minned the island's TOTAL capacity against the
    per-FACILITY levels carried in AIR_FACILITY_LEVEL_CHANGED (apply.py sets ONE facility's level
    from that payload), so a single field dropping to 0 while the other five stood full printed
    "levels 5->5 (low 0)" and the block report read it as an island driven flat. The true low-water
    on the same seed was 4 of 5. Replaying the per-facility ledger is the only honest way to get
    it: carry each facility's level and sum after every change."""
    level = {f.id: f.level for f in malta.facilities(start)}
    lowest = sum(level.values())
    for e in events:
        if e.kind is not EventKind.AIR_FACILITY_LEVEL_CHANGED:
            continue
        fid = str(e.payload["facility_id"])
        if not fid.startswith(malta.PREFIX):
            continue
        level[fid] = e.payload["level"]
        lowest = min(lowest, sum(level.values()))
    return lowest


def _highest_total_capacity(start, events) -> int:
    """The island's HIGH-WATER total Capacity Level -- the twin of the low-water reading above, and
    the one [34.86] moved: the book grows Malta 5 -> 8 -> 14 -> 28 levels, so an end-of-war total
    tells you only where the last raid left it, never whether it ever climbed."""
    level = {f.id: f.level for f in malta.facilities(start)}
    highest = sum(level.values())
    for e in events:
        if e.kind is not EventKind.AIR_FACILITY_LEVEL_CHANGED:
            continue
        fid = str(e.payload["facility_id"])
        if not fid.startswith(malta.PREFIX):
            continue
        level[fid] = e.payload["level"]
        highest = max(highest, sum(level.values()))
    return highest


def _play(seed: int, arm: str) -> dict:
    start = campaign(seed=seed)
    res = run(_arm(start, arm), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    axis, cwlth = _score(res.final)
    denied = sum(e.payload["tons_lost"] for e in res.events
                 if e.kind is EventKind.CONVOY_INTERDICTED and e.payload["lane"] == MALTA_LANE)
    dice = tuple(d for e in res.events if e.kind is EventKind.CONVOY_INTERDICTED
                 and e.payload["lane"] == MALTA_LANE for d in e.rng_draws)
    raids = [e for e in res.events if e.kind is EventKind.MALTA_RAID_ORDERED]
    hits = [e for e in res.events if e.kind is EventKind.MALTA_PLANES_LOST]
    flown = [e for e in res.events if e.kind is EventKind.MALTA_STRIKE_UNFIT]
    # GATE 5.6: the raid's DELIVERY, not just its count. Gate 5 found 84 of 111 raids landing zero
    # Bomb Points because the Axis strike force was a 3-plane proxy and a percentage of 3 rounds to
    # nothing; with [34.6]/[59.3] transcribed this is the census that says whether that is fixed.
    armed = [e for e in raids if not e.payload.get("cancelled")]
    bombs = [e.payload.get("bomb_points", 0) for e in armed]
    grew = [e for e in res.events if e.kind is EventKind.MALTA_REINFORCED]
    return {"seed": seed, "arm": arm, "axis": axis, "allied": cwlth,
            "raids_armed": len(armed),
            "raids_bombing": sum(1 for b in bombs if b > 0),
            "bomb_min": min(bombs, default=0), "bomb_max": max(bombs, default=0),
            "bomb_total": sum(bombs),
            "raid_planes": sum(e.payload.get("planes", 0) for e in armed),
            "levels_max": _highest_total_capacity(start, res.events),
            "planes_max": max([start.malta_planes]
                              + [e.payload["planes"] for e in grew]
                              + [e.payload["planes"] for e in hits]),
            "reinforcements": len(grew),
            "planes_arrived": sum(e.payload["arrived"] for e in grew),
            "winner": None if res.winner is None else res.winner.value,
            "reason": res.reason, "tons_denied": denied, "dice": dice,
            # rule 44's own trajectory: does the island move, and does the budget run down?
            "raids": len(raids), "budget": dict(res.final.malta_raids),
            "levels_start": malta.capacity(start), "levels_end": malta.capacity(res.final),
            "levels_min": _lowest_total_capacity(start, res.events),
            "planes_start": start.malta_planes, "planes_end": res.final.malta_planes,
            "planes_killed": sum(e.payload["lost"] for e in hits),
            # 44.16: does the [38.37] refit governor actually bind on the island's sortie rate?
            "sorties": len(flown),
            "flown_min": min((e.payload["planes"] for e in flown), default=0),
            "flown_max": max((e.payload["planes"] for e in flown), default=0)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    args = ap.parse_args()

    jobs = [(s, b) for s in args.seeds for b in (OFF, LIVE)]
    with ProcessPoolExecutor() as pool:                    # 16 threads: one campaign per worker
        out = list(pool.map(_play, [j[0] for j in jobs], [j[1] for j in jobs]))
    by = {(r["seed"], r["arm"]): r for r in out}

    print("\nMALTA A/B -- the island SILENCED (flat-0% column) vs the island LIVE (rule 44)")
    print("the full 111-turn campaign, CampaignAxisPolicy vs CampaignCommonwealthPolicy\n")
    hdr = f"{'seed':>5} | {'MALTA SILENCED':^30} | {'MALTA LIVE (rule 44)':^30} | {'swing':>18}"
    print(hdr)
    print("-" * len(hdr))
    for s in args.seeds:
        off, mx = by[(s, OFF)], by[(s, LIVE)]
        o = f"{off['reason'].split(':')[0][:17]:17s} {off['axis']:3d}-{off['allied']:<3d}"
        m = f"{mx['reason'].split(':')[0][:17]:17s} {mx['axis']:3d}-{mx['allied']:<3d}"
        # the Axis margin: how far ahead the Axis is. Malta should push it DOWN.
        swing = (mx["axis"] - mx["allied"]) - (off["axis"] - off["allied"])
        flip = "  <-- FLIPS THE WINNER" if off["winner"] != mx["winner"] else ""
        print(f"{s:>5} | {o:^30} | {m:^30} | {swing:>+7d} VP{flip}")

    print("\nthe dice held still (the whole point):")
    for s in args.seeds:
        off, mx = by[(s, OFF)], by[(s, LIVE)]
        n = min(len(off["dice"]), len(mx["dice"]))
        shared = off["dice"][:n] == mx["dice"][:n]
        print(f"  seed {s:>5}: first {n:3d} Malta dice identical in both arms: {shared} "
              f"| tons denied  off={off['tons_denied']:>9,}  live={mx['tons_denied']:>9,}")

    print("\ndoes the island actually move? (the LIVE arm, rule 44's own trajectory)")
    for s in args.seeds:
        m = by[(s, LIVE)]
        budget = " ".join(f"{k}x{v}" for k, v in sorted(m["budget"].items())) or "-"
        print(f"  seed {s:>5}: levels {m['levels_start']}->{m['levels_end']} "
              f"(low {m['levels_min']}, high {m['levels_max']}) "
              f"| planes {m['planes_start']}->{m['planes_end']} "
              f"(high {m['planes_max']}, +{m['planes_arrived']} in {m['reinforcements']} convoys, "
              f"-{m['planes_killed']} bombed) | raids {m['raids']:>3d}  budget spent: {budget}")
        print(f"         44.16 refit: {m['sorties']:>3d} strikes flown, "
              f"{m['flown_min']}-{m['flown_max']} Swordfish per sortie (12 on the island)")
        print(f"         the raid DELIVERS: {m['raids_bombing']:>3d} of {m['raids_armed']:>3d} "
              f"armed raids carried Bomb Points ({m['bomb_min']}-{m['bomb_max']} per raid, "
              f"{m['bomb_total']} total, {m['raid_planes']} plane-sorties flown at the island)")
    print("\n(the arms diverge in draw COUNT once sunk cargo changes the war -- that is the signal,")
    print(" not the noise. Five seeds is not a distribution: read the sign, not one seed.)\n")


if __name__ == "__main__":
    main()
