"""GATE 8.2, QUESTION 4 -- IS ANY OF IT ABSURD?  (read-only)

Six things that would each make the Devil's Gardens a bug rather than a rule, asked of the ENGINE'S
OWN primitives (tactics.reachable_for, construction, combat_tables) rather than of a re-implementation:

  1. A BELT NOBODY CAN CROSS.  26.22 says a unit without engineers "will expend points far over
     their CPA" -- so the belt must be crossable at all, or rule 26 is a wall, not a toll.  Asked of
     tactics.reachable_for against the 8.16/8.17 CP ceiling, unescorted / escorted / Reserve-released.
  2. A BELT NOBODY CAN CLEAR.  26.13 lifts a belt with one CP-free Operations Stage by an Engineer.
     Is such a unit reachable in this engine, and does the beat terminate?
  3. A FORTIFICATION THAT MAKES A HEX INVULNERABLE.  Sweep every (fort level x belt) combination
     through combat.resolve over all 36x36 legal d6d6 pairs and check the defender can still bleed
     and still be made to retreat.
  4. 24.46 -- can a fort and a belt stand on one hex?
  5. 26.25 on a DUMMY belt -- a fake field must destroy no real tanks.
  6. THE FIELD CAP -- 24.4 caps a built fortification below the Major-City levels.

Usage:  PYTHONPATH=<repo> python3 scratchpad/gate82_sanity.py --out <path.json>
"""
from __future__ import annotations

import argparse
import json

from game import cna_map, construction, minefields as mf
from game.events import Side
from game.state import GameState, Minefield, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain
from game import tactics

STATE_KW = dict(turn=1, max_turns=1, phase=None, active_side=Side.AXIS, seed=1,
                weather="normal", vp=VP(), control={}, supplies=(), consumed={},
                initial_supply={})


def _unit(uid, side, hx, mob, cpa, *, engineer="", toe=10, reserve_released=0, cp_used=0.0):
    return Unit(uid, side, hx, (StepRecord("x", toe),), mob, cpa, 1, 3, 3,
                engineer=engineer, reserve_released=reserve_released, cp_used=cp_used,
                is_tank=(mob == Mobility.VEHICLE))


def crossability(tmap, index) -> dict:
    """[26.21]+[26.22] vs the [8.16/8.17] CP ceiling, through tactics.reachable_for -- the ONE
    function the engine itself uses to decide where a unit may go."""
    # two adjacent CLEAR land hexes deep in the open desert west of Alamein
    from game.hexmap import neighbors
    start = None
    for h, t in sorted(tmap.terrain.items()):
        if t != Terrain.CLEAR:
            continue
        nbs = [n for n in neighbors(h) if tmap.terrain.get(n) == Terrain.CLEAR]
        if nbs:
            start, dst = h, sorted(nbs)[0]
            break
    belt = {dst: Minefield(Side.ALLIED, real=True)}
    out = {"start": str(start), "mined_neighbour": str(dst),
           "terrain": [str(tmap.terrain[start]), str(tmap.terrain[dst])]}

    cases = {
        "GE tank bn CPA25, unescorted": (_unit("T", Side.AXIS, start, Mobility.VEHICLE, 25), ()),
        "GE tank bn CPA25, escorted (Engineer stacked)":
            (_unit("T", Side.AXIS, start, Mobility.VEHICLE, 25),
             (_unit("E", Side.AXIS, start, Mobility.MOTORIZED, 30, engineer="ENGINEER"),)),
        "GE tank bn CPA25, released from Reserve I (18.23-1 caps at 1.0x CPA)":
            (_unit("T", Side.AXIS, start, Mobility.VEHICLE, 25, reserve_released=1), ()),
        "GE tank bn CPA25, released from Reserve II (18.24-1 caps at 0.5x CPA)":
            (_unit("T", Side.AXIS, start, Mobility.VEHICLE, 25, reserve_released=2), ()),
        "GE tank bn CPA25 that already spent 24 CP this stage":
            (_unit("T", Side.AXIS, start, Mobility.VEHICLE, 25, cp_used=24.0), ()),
        "GE infantry bn CPA25 FOOT, unescorted (non-Mot pays a flat +4)":
            (_unit("I", Side.AXIS, start, Mobility.FOOT, 25), ()),
        "CW owner walking into HIS OWN belt (Friendly Minefield row)":
            (_unit("C", Side.ALLIED, start, Mobility.VEHICLE, 25), ()),
    }
    rows = {}
    for label, (mover, escorts) in cases.items():
        st = GameState(terrain=tmap, target_hex=start, minefields=belt,
                       units=(mover,) + escorts, **STATE_KW)
        reach = tactics.reachable_for(st, mover, frozenset(), frozenset())
        unmined = tactics.reachable_for(
            GameState(terrain=tmap, target_hex=start, minefields={},
                      units=(mover,) + escorts, **STATE_KW), mover, frozenset(), frozenset())
        rows[label] = {
            "can_enter_the_mined_hex": dst in reach,
            "cp_charged": reach.get(dst),
            "cp_if_unmined": unmined.get(dst),
            "hexes_reachable_mined_vs_unmined": [len(reach), len(unmined)],
        }
    out["cases"] = rows
    return out


def clearability(tmap, index) -> dict:
    """[26.13]: 'Real minefields may be removed by having an Engineer unit spend one full
    Operations Stage in the hex.'  Which units in this engine can do it, and is any of them
    reachable by a live scenario?"""
    hx = next(iter(tmap.terrain))
    probes = {}
    for cap, toe in (("ENGINEER", 10), ("HQ_ENGINEER", 10), ("SCORPION", 10), ("SCORPION", 5),
                     ("RAIL", 10), ("ROAD", 10), ("", 10)):
        u = _unit("U", Side.ALLIED, hx, Mobility.MOTORIZED, 30, engineer=cap, toe=toe)
        probes[f"{cap or '(none)'} @ {toe} TOE"] = {
            "is_engineer_26_24_clear_and_escort": mf.is_engineer(u),
            "builds_engineering_24_42_fortification": construction.builds_engineering(u),
            "lays_minefield_24_31": construction.lays_minefield(u),
        }
    return {"scorpion_min_toe_23_15": mf.SCORPION_MIN_TOE, "by_capability": probes}


def invulnerability() -> dict:
    """Is there ANY (fortification level x belt) combination on which the defender cannot be hurt
    and cannot be dislodged?  Exhaustive over the 36x36 legal d6d6 space."""
    from game import combat
    rolls = [t * 10 + u for t in range(1, 7) for u in range(1, 7)]
    worst = []
    for fort in (0, 1, 2, 3):
        for mined in (False, True):
            dl = rt = 0.0
            n = 0
            for ar in rolls:
                for dr in rolls:
                    r = combat.resolve(attacker_raw=60, defender_raw=30,
                                       def_terrain=Terrain.CLEAR, atk_roll=ar, def_roll=dr,
                                       fortification_level=fort, in_enemy_minefield=mined)
                    dl += r.defender_points_lost
                    rt += 1 if r.retreat_hexes > 0 else 0
                    n += 1
            worst.append({"fort": fort, "mined": mined,
                          "E[defender_points_lost]": round(dl / n, 3),
                          "P(defender_retreats)": round(rt / n, 4),
                          "INVULNERABLE": dl == 0 and rt == 0})
    return {"rows": worst, "any_invulnerable": any(r["INVULNERABLE"] for r in worst)}


def exclusivity(tmap) -> dict:
    """[24.46]: a fortification and a real minefield may not occupy the same hex.  Asked of
    construction's own predicates, both directions."""
    hx = next(iter(h for h, t in tmap.terrain.items() if t == Terrain.CLEAR))
    out = {}
    st_clean = GameState(terrain=tmap, target_hex=hx, minefields={}, units=(), **STATE_KW)
    st_mined = GameState(terrain=tmap, target_hex=hx,
                         minefields={hx: Minefield(Side.ALLIED, real=True)}, units=(), **STATE_KW)
    out["minefield_buildable_on_a_clean_hex"] = construction.minefield_buildable(
        st_clean, Side.ALLIED, hx)
    out["minefield_buildable_where_a_belt_already_stands"] = construction.minefield_buildable(
        st_mined, Side.ALLIED, hx)
    out["_terrain_allowed_24_35"] = sorted(mf.MINEFIELD_TERRAIN)
    out["_fort_terrain_excluded_24_4"] = sorted(mf.FORT_EXCLUDED_TERRAIN)
    out["_fort_field_cap_24_4"] = mf.FORT_FIELD_CAP
    return out


def dummy_belt() -> dict:
    """[26.25] vs [26.23]: a DUMMY belt costs the same to enter and destroys nothing."""
    real = Minefield(Side.ALLIED, real=True)
    fake = Minefield(Side.ALLIED, real=False)
    return {
        "real_belt_rolls_destruction_for_an_unescorted_vehicle":
            mf.rolls_destruction(real, Side.AXIS, Mobility.VEHICLE, False),
        "DUMMY_belt_rolls_destruction_for_an_unescorted_vehicle":
            mf.rolls_destruction(fake, Side.AXIS, Mobility.VEHICLE, False),
        "real_belt_rolls_destruction_for_an_ESCORTED_vehicle":
            mf.rolls_destruction(real, Side.AXIS, Mobility.VEHICLE, True),
        "real_belt_rolls_destruction_for_FOOT":
            mf.rolls_destruction(real, Side.AXIS, Mobility.FOOT, False),
        "destroys_on": sorted(mf.MINE_DESTROY_ROLLS),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="scratchpad/gate82_sanity.json")
    args = ap.parse_args()
    tmap, index = cna_map.load_sections("ABCDE")
    doc = {
        "1_crossability": crossability(tmap, index),
        "2_clearability": clearability(tmap, index),
        "3_invulnerability": invulnerability(),
        "4_exclusivity_24_46": exclusivity(tmap),
        "5_dummy_belt": dummy_belt(),
    }
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1, default=str)
    print(json.dumps(doc, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
