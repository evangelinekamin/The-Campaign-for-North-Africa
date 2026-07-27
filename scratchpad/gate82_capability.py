"""GATE 8.2, QUESTION 1 -- WHAT DOES A MINED AND FORTIFIED ALAMEIN SHOULDER COST AN ATTACKER?

Read-only.  Changes nothing in game/ or data/.  Measured on the engine's OWN step graph and the
engine's OWN combat tables, by the same method the 8.1a/8.1b/8.45 gates used: min-vertex-cut,
VERIFIED BY DELETION, plus a cheapest-route Dijkstra whose edge weight is the engine's real
movement.step_cost + minefields.entry_surcharge.

Phase 8.1 proved geometry does not seal El Alamein: the fills leave the corridor 30 hexes wide at
the Alamein meridian, the escarpment rim changes that number by zero, and [8.45]'s desert bar moves
the campaign by exactly zero.  This asks the successor question -- can ENGINEERING (rule 26 belts +
24.4 fortifications) do what the ground could not?

FOUR MEASUREMENTS
  A. THE BELT GEOMETRY.  The minimum-vertex cut in the Alamein sector IS the cheapest Devil's
     Gardens that every west->east route must cross (a vertex cut lies on every s-t path, by
     definition), so its size is the *smallest belt that cannot be walked around*.  Verified by
     deletion, and by restoring one hex at a time.
  B. WHAT IT COSTS THE DEFENDER TO BUILD.  24.31/24.32's Stores + Ammo and Operations-Stage price
     of that belt, and of a historically-shaped full-width band of depth k, read out of
     data/minefields.json via game.minefields -- never from a literal here.
  C. WHAT IT COSTS THE ATTACKER TO FORCE (MOVEMENT).  Cheapest-CP route west->east, unmined vs
     mined, motorized vs non-motorized, unescorted vs 26.24-escorted; plus the minimum number of
     mined-hex ENTRIES any route can be reduced to (a second Dijkstra on that count alone), the
     [8.37] +2 Breakdown Points, and 26.25's expected TOE/Truck Point destruction.
  D. WHAT IT COSTS THE ATTACKER TO FORCE (COMBAT).  The [8.37] column shifts a defender in his own
     belt and/or a 24.4 fortification receives, run EXHAUSTIVELY through the engine's own
     combat.resolve over all 36x36 legal d6d6 pairs -- an exact expectation, not a sample.

Usage:  PYTHONPATH=<repo> python3 scratchpad/gate82_capability.py --out <path.json>
"""
from __future__ import annotations

import argparse
import heapq
import json
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gate81b_alamein import _min_vertex_cut, _passable_graph  # noqa: E402

from game import cna_map, minefields as mf                    # noqa: E402
from game.events import Side                                  # noqa: E402
from game.hexmap import neighbors                             # noqa: E402
from game.movement import step_cost                           # noqa: E402
from game.state import GameState, Minefield, VP               # noqa: E402
from game.terrain import Mobility, Terrain                    # noqa: E402

# The SAME sector the 8.1b and 8.45 gates cut, so the numbers are comparable across the phase.
WEST_R, EAST_R = 80, 130
ALAMEIN_LABEL = "E3002"

# Representative attackers.  CPA values are read off the engine's own unit_stats rows below, not
# guessed here -- see _attacker_profiles().
DUMMY_STATE_KW = dict(turn=1, max_turns=1, phase=None, active_side=Side.SYSTEM, seed=1,
                      weather="normal", vp=VP(), control={}, units=(), supplies=(),
                      consumed={}, initial_supply={})


def _state(tmap, belt: dict) -> GameState:
    return GameState(terrain=tmap, target_hex=(0, 0), minefields=belt, **DUMMY_STATE_KW)


# ---------------------------------------------------------------------------------------------
# A. THE BELT GEOMETRY
# ---------------------------------------------------------------------------------------------

def _reaches(adj, west, east, banned) -> bool:
    src = [h for h in west if h not in banned]
    seen, dq = set(src), deque(src)
    while dq:
        c = dq.popleft()
        if c in east:
            return True
        for nb in adj.get(c, ()):
            if nb not in seen and nb not in banned:
                seen.add(nb)
                dq.append(nb)
    return False


def belt_geometry(tmap, index, mob) -> dict:
    adj = _passable_graph(tmap, mob)
    west = {h for h in adj if h[1] <= WEST_R}
    east = {h for h in adj if h[1] >= EAST_R}
    size, cut_hexes = _min_vertex_cut(adj, west, east)
    cut = {h for h in cut_hexes} if not isinstance(cut_hexes[0], str) else {
        index[l] for l in cut_hexes if l in index}
    rev = {h: l for l, h in index.items()}
    r_alamein = index[ALAMEIN_LABEL][1]

    # VERIFY BY DELETION -- a cut that does not disconnect is not a cut; and a cut with a
    # redundant hex is not minimal.
    verify = {
        "baseline_west_reaches_east": _reaches(adj, west, east, set()),
        "DELETING_THE_CUT_still_connects": _reaches(adj, west, east, cut),
        "hexes_whose_restoration_reopens_the_line": sum(
            1 for h in cut if _reaches(adj, west, east, cut - {h})),
    }
    return {
        "mobility": mob.value,
        "min_vertex_cut_size": size,
        "cut_hexes": sorted(rev.get(h, str(h)) for h in cut),
        "cut_r_offsets_from_alamein": sorted(h[1] - r_alamein for h in cut),
        "cut_terrain_census": _census(tmap, cut),
        "verify": verify,
        "_cut": cut,
    }


def _census(tmap, hexes) -> dict:
    out: dict = {}
    for h in hexes:
        t = tmap.terrain.get(h)
        out[getattr(t, "value", str(t))] = out.get(getattr(t, "value", str(t)), 0) + 1
    return dict(sorted(out.items()))


def full_width_band(tmap, adj, index, depth: int) -> set:
    """A historically-shaped Devil's Gardens: every LIVE land hex on the `depth` consecutive
    meridians starting at El Alamein and running WEST (into the attacker's face).  Unlike the
    min-cut this is the belt a player would actually draw on the map."""
    r_alamein = index[ALAMEIN_LABEL][1]
    want = set(range(r_alamein - depth + 1, r_alamein + 1))
    return {h for h in adj if h[1] in want and adj[h]}


# ---------------------------------------------------------------------------------------------
# C. WHAT IT COSTS THE ATTACKER TO FORCE (MOVEMENT)
# ---------------------------------------------------------------------------------------------

def _dijkstra(tmap, adj, west, east, weight) -> tuple[float, list]:
    """Cheapest west->east route under `weight(a, b) -> float`.  Returns (cost, path)."""
    dist = {h: 0.0 for h in west}
    prev: dict = {}
    pq = [(0.0, h) for h in west]
    heapq.heapify(pq)
    while pq:
        d, c = heapq.heappop(pq)
        if d > dist.get(c, float("inf")):
            continue
        if c in east:
            path = [c]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return d, list(reversed(path))
        for nb in adj.get(c, ()):
            w = weight(c, nb)
            if w is None:
                continue
            nd = d + w
            if nd < dist.get(nb, float("inf")):
                dist[nb] = nd
                prev[nb] = c
                heapq.heappush(pq, (nd, nb))
    return float("inf"), []


def crossing_cost(tmap, adj, index, belt: set, mob, cpa: int, escorted: bool) -> dict:
    """The [6.3]/[8.37] price of forcing `belt`, on the engine's own step graph and the engine's
    own minefields.entry_surcharge.

    ESCORT MODEL: 26.24's discount is granted when the mover is STACKED with an Engineer unit, so
    an escorted column carries its engineer at every step.  minefields.engineer_present is the
    predicate entry_surcharge consults; this driver overrides that ONE function for the escorted
    arm rather than seeding 6,699 synthetic engineer counters (units_at is a linear scan).  The
    override is proven live below (`_escort_probe`), and it is applied to game.minefields --
    the module entry_surcharge's own body resolves it in, so the NEUTER TRAP does not bite."""
    west = {h for h in adj if h[1] <= WEST_R}
    east = {h for h in adj if h[1] >= EAST_R}
    mined = {h: Minefield(Side.ALLIED, real=True) for h in belt}
    st = _state(tmap, mined)

    orig = mf.engineer_present
    if escorted:
        mf.engineer_present = lambda state, coord, side: True
    try:
        probe_a = (mf.entry_surcharge(st, Side.AXIS, mob, cpa, (0, 0), next(iter(belt)))
                   if belt else None)

        def cp_weight(a, b):
            base = step_cost(tmap, a, b, mob)
            if base is None:
                return None
            return base + mf.entry_surcharge(st, Side.AXIS, mob, cpa, a, b)

        cp, path = _dijkstra(tmap, adj, west, east, cp_weight)

        # The SEPARATE question: how few mined hexes can a route be reduced to, whatever the CP?
        def mine_weight(a, b):
            if step_cost(tmap, a, b, mob) is None:
                return None
            return 1.0 if b in belt else 0.0

        min_entries, _ = _dijkstra(tmap, adj, west, east, mine_weight)

        # Breakdown Points along the cheapest-CP route (8.37: the belt adds +2 to the hex's own).
        bd = sum(mf.breakdown_surcharge(st, Side.AXIS, b) for a, b in zip(path, path[1:]))
    finally:
        mf.engineer_present = orig

    entries = sum(1 for a, b in zip(path, path[1:]) if b in belt)
    exposures = sum(1 for a, b in zip(path, path[1:])
                    if b in belt and mf.rolls_destruction(mined[b], Side.AXIS, mob, escorted))
    return {
        "mobility": mob.value, "cpa": cpa, "escorted": escorted,
        "_escort_probe_surcharge_on_first_belt_hex": probe_a,
        "cheapest_cp": round(cp, 2),
        "route_hexes": len(path),
        "mined_hex_entries_on_that_route": entries,
        "min_possible_mined_entries_any_route": None if min_entries == float("inf") else int(min_entries),
        "operations_stages_of_CPA": round(cp / cpa, 2),
        "extra_breakdown_points_from_the_belt": bd,
        "26_25_destruction_roll_exposures": exposures,
        "26_25_expected_points_destroyed": round(exposures * len(mf.MINE_DESTROY_ROLLS) / 6.0, 3),
    }


# ---------------------------------------------------------------------------------------------
# D. WHAT IT COSTS THE ATTACKER TO FORCE (COMBAT) -- exhaustive over the legal d6d6 space
# ---------------------------------------------------------------------------------------------

LEGAL_ROLLS = [t * 10 + u for t in range(1, 7) for u in range(1, 7)]


def assault_expectation(attacker_raw: int, defender_raw: int, fort: int, mined: bool) -> dict:
    """Expected outcome of ONE close assault onto a CLEAR Alamein hex, averaged over all 36x36
    equiprobable d6d6 pairs the engine actually rolls.  Uses game.combat.resolve unmodified."""
    from game import combat

    n = 0
    a_lost = d_lost = 0.0
    retreats = engaged = captured = 0
    col_sum = 0
    for ar in LEGAL_ROLLS:
        for dr in LEGAL_ROLLS:
            r = combat.resolve(attacker_raw=attacker_raw, defender_raw=defender_raw,
                               def_terrain=Terrain.CLEAR, atk_roll=ar, def_roll=dr,
                               fortification_level=fort, in_enemy_minefield=mined)
            n += 1
            a_lost += r.attacker_points_lost
            d_lost += r.defender_points_lost
            retreats += 1 if r.retreat_hexes > 0 else 0
            engaged += 1 if r.attacker_engaged else 0
            captured += 1 if r.defender_captured else 0
            col_sum += r.column
    return {
        "fort_level": fort, "defender_in_own_minefield": mined,
        "column": round(col_sum / n, 3),
        "E[attacker_points_lost]": round(a_lost / n, 3),
        "E[defender_points_lost]": round(d_lost / n, 3),
        "P(defender_retreats)": round(retreats / n, 4),
        "P(attacker_engaged)": round(engaged / n, 4),
        "P(defender_captured)": round(captured / n, 4),
    }


def anti_armor_shifts() -> dict:
    """[8.37]'s Anti Armor column for the Fortification and Minefield rows, as the engine computes
    it -- against the chart as re-read off PDF p.70 for this gate."""
    from game import combat_tables as ct
    out = {}
    for terr in (Terrain.CLEAR, Terrain.MAJOR_CITY):
        for lvl in (0, 1, 2, 3):
            for mined in (False, True):
                out[f"{terr.value}/fort{lvl}/mined={mined}"] = ct.anti_armor_terrain_shift(
                    terr, lvl, mined)
    return out


# ---------------------------------------------------------------------------------------------

def _attacker_profiles() -> list:
    """CPA read out of data/unit_stats.json -- the magnitudes come from the data file, never from a
    literal in this driver."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                           "data", "unit_stats.json")) as f:
        stats = json.load(f)

    def find(*path):
        node = stats
        for p in path:
            node = node[p]
        return node

    picks = []
    for label, keys in (("GE tank bn", ("GE", "tank")),
                        ("GE artillery bn", ("GE", "artillery")),
                        ("GE infantry bn", ("GE", "infantry"))):
        row = find(*keys)
        picks.append((label, int(row["cpa"]), Mobility[row["mobility"]]))
    return picks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="scratchpad/gate82_capability.json")
    ap.add_argument("--depths", type=int, nargs="+", default=[1, 2, 3, 5])
    args = ap.parse_args()

    tmap, index = cna_map.load_sections("ABCDE")
    doc: dict = {"sector": {"west_r<=": WEST_R, "east_r>=": EAST_R,
                            "r_alamein": index[ALAMEIN_LABEL][1]}}

    # ---- A. geometry -------------------------------------------------------------------------
    geo = {}
    cuts = {}
    for mob in (Mobility.VEHICLE, Mobility.FOOT):
        g = belt_geometry(tmap, index, mob)
        cuts[mob] = g.pop("_cut")
        geo[mob.value] = g
    doc["A_belt_geometry"] = geo

    adj_v = _passable_graph(tmap, Mobility.VEHICLE)

    # ---- B. construction price --------------------------------------------------------------
    def price(n_hexes: int) -> dict:
        return {
            "hexes": n_hexes,
            "real_belt_stores": n_hexes * mf.REAL_STORES,
            "real_belt_ammo": n_hexes * mf.REAL_AMMO,
            "dummy_belt_stores": n_hexes * mf.DUMMY_STORES,
            "engineer_operations_stages": n_hexes * mf.MINEFIELD_OP_STAGES,
            "engineer_GAME_TURNS_at_3_stages_per_turn": round(
                n_hexes * mf.MINEFIELD_OP_STAGES / 3.0, 1),
            "if_fortified_instead_stores": n_hexes * mf.FORT_STORES,
            "if_fortified_instead_op_stages": n_hexes * mf.FORT_OP_STAGES,
        }

    bands = {}
    for d in args.depths:
        band = full_width_band(tmap, adj_v, index, d)
        bands[d] = band
        doc.setdefault("B_construction_price", {})[f"full_width_band_depth_{d}"] = price(len(band))
    doc["B_construction_price"]["min_vertex_cut_VEHICLE"] = price(len(cuts[Mobility.VEHICLE]))
    doc["B_construction_price"]["_rates_from_data_minefields_json"] = {
        "real_stores_per_hex": mf.REAL_STORES, "real_ammo_per_hex": mf.REAL_AMMO,
        "dummy_stores_per_hex": mf.DUMMY_STORES, "op_stages_per_hex": mf.MINEFIELD_OP_STAGES,
        "fort_stores_per_level": mf.FORT_STORES, "fort_op_stages_per_level": mf.FORT_OP_STAGES,
        "fort_field_cap": mf.FORT_FIELD_CAP,
    }

    # ---- C. movement cost to force ----------------------------------------------------------
    profiles = _attacker_profiles()
    doc["_attacker_profiles"] = [(l, c, m.value) for l, c, m in profiles]
    graphs = {Mobility.VEHICLE: adj_v}
    for _l, _c, m in profiles:
        graphs.setdefault(m, _passable_graph(tmap, m))

    move: dict = {}
    belts_to_test = {"UNDEFENDED (no belt at all)": set(),
                     "min_vertex_cut": cuts[Mobility.VEHICLE]}
    belts_to_test.update({f"band_depth_{d}": b for d, b in bands.items()})
    for bname, belt in belts_to_test.items():
        move[bname] = {}
        for label, cpa, m in profiles:
            for esc in (False, True):
                if not belt and esc:
                    continue                      # escort is meaningless with nothing to escort through
                move[bname][f"{label} | {m.value} | escorted={esc}"] = crossing_cost(
                    tmap, graphs[m], index, belt, m, cpa, esc)
    doc["C_movement_cost"] = move

    # ---- D. combat cost to force -------------------------------------------------------------
    combat_rows = []
    for fort in (0, 1, 2, 3):
        for mined in (False, True):
            combat_rows.append(assault_expectation(60, 30, fort, mined))
    doc["D_close_assault_60v30_CLEAR_exhaustive_36x36"] = combat_rows
    doc["D_anti_armor_shifts"] = anti_armor_shifts()

    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1, default=str)
    print(json.dumps({k: v for k, v in doc.items() if k != "C_movement_cost"},
                     indent=1, default=str)[:6000])
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
