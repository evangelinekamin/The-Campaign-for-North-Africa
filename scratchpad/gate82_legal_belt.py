"""GATE 8.2, QUESTION 1 (the decisive half) -- CAN A *LEGAL* DEVIL'S GARDENS SEAL EL ALAMEIN?

Read-only.  The 24.35 terrain restriction turns the belt question into a geometry question again:
minefields may be laid ONLY on the terrain classes data/minefields.json names (game.minefields.
MINEFIELD_TERRAIN), and fortifications only off game.minefields.FORT_EXCLUDED_TERRAIN.  DESERT is
barred to both.  The Alamein corridor's southern half is desert.

So the honest question is not "how much does a belt cost" but "is the mineable subset of the
corridor a CUT at all?"  Formulated exactly: run the same vertex-splitting max-flow the 8.1a/8.1b/
8.45 gates used, but give every UNMINEABLE hex INFINITE node capacity and every mineable hex
capacity 1.  Then

  * a FINITE max-flow  == a legal all-mineable belt of that size exists that every west->east route
    must cross;
  * an INFINITE max-flow == no belt the rules permit can force a single route through mines: the
    attacker walks round the end of the minefield on ground the defender is forbidden to mine.

Both answers are verified by DELETION, the same way every claim in this phase has been.

Usage:  PYTHONPATH=<repo> python3 scratchpad/gate82_legal_belt.py --out <path.json>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gate81b_alamein import _passable_graph                  # noqa: E402

from game import cna_map, minefields as mf                   # noqa: E402
from game.terrain import Mobility, Terrain                   # noqa: E402

WEST_R, EAST_R = 80, 130
ALAMEIN_LABEL = "E3002"
INF = float("inf")


def min_cut(adj, west, east, cap_of) -> tuple[float, list]:
    """Vertex-splitting max-flow / min-cut where `cap_of(hex) -> float` is the node capacity
    (INF = a hex that may not be part of the cut).  Edmonds-Karp; returns (flow, cut_hexes)."""
    nodes = list(adj)
    idx = {h: i for i, h in enumerate(nodes)}
    n = len(nodes)
    S, T = 2 * n, 2 * n + 1
    cap: dict[int, dict[int, float]] = {}

    def add(u, v, c):
        cap.setdefault(u, {})[v] = cap.setdefault(u, {}).get(v, 0) + c
        cap.setdefault(v, {}).setdefault(u, 0)

    for h, i in idx.items():
        add(2 * i, 2 * i + 1, INF if (h in west or h in east) else cap_of(h))
    for h, i in idx.items():
        for nb in adj[h]:
            if nb in idx:
                add(2 * i + 1, 2 * idx[nb], INF)
    for h in west:
        add(S, 2 * idx[h], INF)
    for h in east:
        add(2 * idx[h] + 1, T, INF)

    flow = 0.0
    while True:
        par, dq = {S: None}, deque([S])
        while dq and T not in par:
            u = dq.popleft()
            for v, c in cap[u].items():
                if c > 0 and v not in par:
                    par[v] = u
                    dq.append(v)
        if T not in par:
            break
        b, v = INF, T
        while par[v] is not None:
            b = min(b, cap[par[v]][v])
            v = par[v]
        if b == INF:                       # an all-INF augmenting path: the cut is unbounded
            return INF, []
        v = T
        while par[v] is not None:
            cap[par[v]][v] -= b
            cap[v][par[v]] += b
            v = par[v]
        flow += b

    reach, dq = {S}, deque([S])
    while dq:
        u = dq.popleft()
        for v, c in cap[u].items():
            if c > 0 and v not in reach:
                reach.add(v)
                dq.append(v)
    cut = [nodes[i] for i in range(n) if (2 * i) in reach and (2 * i + 1) not in reach]
    return flow, cut


def reaches(adj, west, east, banned) -> bool:
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


def run(tmap, index, mob, allowed: frozenset, label: str) -> dict:
    adj = _passable_graph(tmap, mob)
    west = {h for h in adj if h[1] <= WEST_R}
    east = {h for h in adj if h[1] >= EAST_R}
    rev = {h: l for l, h in index.items()}
    r_alamein = index[ALAMEIN_LABEL][1]

    def cap_of(h):
        t = tmap.terrain.get(h)
        return 1.0 if getattr(t, "name", str(t)) in allowed else INF

    flow, cut = min_cut(adj, west, east, cap_of)
    row = {
        "mobility": mob.value,
        "restriction": label,
        "allowed_terrain": sorted(allowed),
        "min_cut_size": "UNBOUNDED (no legal belt is a cut)" if flow == INF else flow,
        "a_legal_belt_can_force_every_route_through_mines": flow != INF,
    }
    if flow != INF:
        row["cut_hexes"] = sorted(rev.get(h, str(h)) for h in cut)
        row["cut_r_offsets_from_alamein"] = sorted(h[1] - r_alamein for h in cut)
        row["cut_terrain_census"] = _census(tmap, cut)
        row["VERIFY_deleting_the_cut_still_connects"] = reaches(adj, west, east, set(cut))
        row["VERIFY_every_cut_hex_is_legal_to_mine"] = all(
            getattr(tmap.terrain.get(h), "name", "") in allowed for h in cut)
        row["build_price_stores"] = len(cut) * mf.REAL_STORES
        row["build_price_ammo"] = len(cut) * mf.REAL_AMMO
        row["build_price_engineer_op_stages"] = len(cut) * mf.MINEFIELD_OP_STAGES
    else:
        # WHERE does it leak?  The unmineable hexes that a route can still use.
        illegal = {h for h in adj if getattr(tmap.terrain.get(h), "name", "") not in allowed}
        row["VERIFY_mining_EVERY_legal_hex_still_connects"] = reaches(
            adj, west, east, {h for h in adj if h not in illegal})
        leak = {}
        for h in illegal:
            t = getattr(tmap.terrain.get(h), "name", "?")
            leak[t] = leak.get(t, 0) + 1
        row["unmineable_hexes_on_the_graph_by_terrain"] = dict(sorted(leak.items()))
    return row


def _census(tmap, hexes) -> dict:
    out: dict = {}
    for h in hexes:
        t = getattr(tmap.terrain.get(h), "name", "?")
        out[t] = out.get(t, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="scratchpad/gate82_legal_belt.json")
    args = ap.parse_args()
    tmap, index = cna_map.load_sections("ABCDE")

    engine_allowed = frozenset(mf.MINEFIELD_TERRAIN)
    # The [24.17] chart's rival list, which the port plan records as OPEN OWNER RULING E4
    # ("Clear, Sand/Gravel and Salt Marsh" vs 24.35's "clear, sand/gravel, or rough").  Measured
    # too, so the answer does not hang on a ruling that is not yet made.
    chart_allowed = frozenset({"CLEAR", "GRAVEL", "SALT_MARSH"})
    both = engine_allowed | chart_allowed
    fort_allowed = frozenset(
        t.name for t in Terrain if t.name not in mf.FORT_EXCLUDED_TERRAIN)

    doc = {"sector": {"west_r<=": WEST_R, "east_r>=": EAST_R,
                      "r_alamein": index[ALAMEIN_LABEL][1]},
           "results": []}
    for mob in (Mobility.VEHICLE, Mobility.FOOT):
        doc["results"].append(run(tmap, index, mob, engine_allowed,
                                 "[24.35] as the engine implements it"))
        doc["results"].append(run(tmap, index, mob, chart_allowed,
                                 "[24.17] chart's rival list (open ruling E4)"))
        doc["results"].append(run(tmap, index, mob, both,
                                 "the UNION of both readings (most generous possible)"))
        doc["results"].append(run(tmap, index, mob, fort_allowed,
                                 "[24.4] FORTIFICATION-legal terrain"))
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1, default=str)
    for r in doc["results"]:
        print(f"{r['mobility']:8} | {r['restriction']:48} | cut={r['min_cut_size']} | "
              f"seals={r['a_legal_belt_can_force_every_route_through_mines']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
