"""GATE 8.1c, QUESTION 1 -- THE ENGINEER CENSUS, before vs after the 8.1b OOB seeding.

Read-only.  Changes nothing in game/ or data/.  Runs UNMODIFIED in both arms (the BASE worktree at
e73409a and HEAD at e068c2f): every symbol it touches -- game.minefields, game.construction,
Unit.engineer -- landed with the 8.2 slice at aa4b6a2, which is an ancestor of both, so the only
thing that can move between the arms is the ORDER OF BATTLE.

The 8.2 gate measured the census over a folded 111-turn campaign, because it had to prove that
reinforcements which ARRIVED were counted too.  That is unnecessary work: game.scenario.campaign
seeds every counter the war will ever contain into GameState.units at t0, each carrying its own
arrival_turn (on-map units carry the map hex, the rest wait off-board).  So this walks the setup
state and is exact, and cheap enough to answer the question in a second rather than an hour.

FOUR CAPABILITIES, each read through the ENGINE'S OWN predicate, never re-implemented here:
  LAY      [24.31]/[24.17]  construction.lays_minefield  -- EBn/ECoy either side, CHQ-E Allied only
  FORTIFY  [24.42]          construction.builds_engineering -- the chart's "AnyE"
  CLEAR    [26.13]/[24.38]  minefields.is_engineer       -- plus 23.15's Scorpion flails
  ESCORT   [26.24]          minefields.is_engineer       -- the same predicate entry_surcharge asks

Usage:  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate81c_census.py --out <path.json>
"""
from __future__ import annotations

import argparse
import json
from collections import Counter


def census(seed: int = 1) -> dict:
    from game import construction, minefields as mf
    from game.events import Side
    from game.scenario import campaign

    init = campaign(seed=seed)
    units = list(init.units)

    def per_side(pred) -> dict:
        c = Counter(u.side.value for u in units if pred(u))
        return {"AXIS": c.get(Side.AXIS.value, 0), "ALLIED": c.get(Side.ALLIED.value, 0),
                "total": sum(c.values())}

    # The raw flag census the 8.2 gate printed, so the two numbers are directly comparable.
    flags = Counter(f"{u.side.value}/{u.engineer}" for u in units if u.engineer)

    def roster(pred) -> list:
        return [
            {"id": u.id, "side": u.side.value, "flag": u.engineer,
             "arrival_turn": u.arrival_turn, "on_map_at_setup": bool(init.on_map(u)),
             "hex": list(u.hex) if init.on_map(u) else None}
            for u in sorted(units, key=lambda u: (u.side.value, u.arrival_turn or 0, u.id))
            if pred(u)
        ]

    lay = construction.lays_minefield
    fortify = construction.builds_engineering
    clear_escort = mf.is_engineer

    # 24.42 needs a PARTNER: an Infantry battalion at 3+ TOE standing on the same hex.  Count the
    # pool of possible partners the war ever contains, per side, through the engine's predicate.
    partner = construction._is_infantry_battalion

    return {
        "seed": seed,
        "units_the_war_ever_contains": len(units),
        "engineer_flag_census": dict(sorted(flags.items())),
        "capability": {
            "LAY_a_belt_24_31": per_side(lay),
            "BUILD_a_fortification_24_42": per_side(fortify),
            "CLEAR_a_belt_26_13": per_side(clear_escort),
            "ESCORT_through_a_belt_26_24": per_side(clear_escort),
            "24_42_infantry_partner_pool_3plus_TOE": per_side(partner),
        },
        "arrival_turn_of_every_lay_capable_counter": sorted(
            Counter(u.arrival_turn for u in units if lay(u)).items()),
        "roster_LAY": roster(lay),
        "roster_CLEAR_or_ESCORT_only": roster(lambda u: clear_escort(u) and not lay(u)),
        "roster_RAIL_ROAD_specialists": roster(
            lambda u: u.engineer in ("RAIL", "ROAD")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    doc = census(args.seed)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    slim = {k: v for k, v in doc.items() if not k.startswith("roster")}
    print(json.dumps(slim, indent=1))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
