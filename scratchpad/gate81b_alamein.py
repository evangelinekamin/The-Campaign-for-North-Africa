"""GATE 8.1b -- DOES THE ESCARPMENT RIM SEAL THE ALAMEIN LINE?  (read-only)

Measures, off the loaded TerrainMap and full 111-turn campaign folds, the four questions the
Block-A spec asked of the hexside slice. Changes NOTHING in game/ or data/; the only mutation is
an optional in-process neuter (--neuter) that empties TerrainMap.hexsides at load time, so the
rim's effect can be separated from the A/B + D/E section-seam coordinate fix that shipped in the
same commit.

  1. THE CORRIDOR -- coast->marsh land width (the 8.1a metric), plus the honest one: the MINIMUM
     VERTEX CUT across the Alamein sector on the engine's own mobility-aware step graph, i.e. the
     width of the front a defender must physically hold, per mobility class.
  2. DOES IT SEAL -- is there still a vehicle-passable route around the marsh's eastern tip, and
     what does it cost against the coastal route.
  3. THE CAMPAIGN -- Axis furthest-east high-water mark, position at war's end, winner + 64.76.
  4. SANITY -- hexes nobody can enter or leave, graph components, one-way traps.

Usage:
  PYTHONPATH=<repo> python3 scratchpad/gate81b_alamein.py --mode corridor
  PYTHONPATH=<repo> python3 scratchpad/gate81b_alamein.py --mode campaign --seeds 1941 7 ... \
      --workers 7 --out <path.json> [--neuter]
"""
from __future__ import annotations

import argparse
import json
import os
from collections import deque
from concurrent.futures import ProcessPoolExecutor

# ---------------------------------------------------------------------------------------------
# THE NEUTER.  game/scenario.py does `from . import cna_map` and calls `cna_map.load_sections(...)`
# by module attribute, so rebinding the attribute on the MODULE reaches the caller's lookup (the
# baselines.py trap is about `from .x import f` call sites -- this one is not).  Verified live by
# _assert_neutered below, which reads hexsides back off the state the scenario actually built.
# ---------------------------------------------------------------------------------------------
NEUTER = os.environ.get("GATE81B_NEUTER") == "1"


def _install_neuter() -> None:
    import dataclasses
    from game import cna_map

    orig_sections = cna_map.load_sections
    orig_section = cna_map.load_section

    def strip(pair):
        tmap, index = pair
        return dataclasses.replace(tmap, hexsides={}), index

    cna_map.load_sections = lambda s: strip(orig_sections(s))
    cna_map.load_section = lambda s: strip(orig_section(s))


def _maybe_neuter() -> None:
    if NEUTER:
        _install_neuter()


# ---------------------------------------------------------------------------------------------
# graph helpers
# ---------------------------------------------------------------------------------------------

def _passable_graph(tmap, mob):
    """{hex: [reachable neighbour, ...]} using the engine's own step_cost -- so escarpment
    prohibitions ([8.42]), the [8.44] salt-marsh gate, road/track and terrain P all bind."""
    from game.hexmap import neighbors
    from game.movement import step_cost

    out = {}
    for h in tmap.terrain:
        row = []
        for nb in neighbors(h):
            if tmap.exists(nb) and step_cost(tmap, h, nb, mob) is not None:
                row.append(nb)
        out[h] = row
    return out


def _components(adj):
    seen, comps = set(), []
    for s in adj:
        if s in seen:
            continue
        comp, dq = 0, deque([s])
        seen.add(s)
        while dq:
            c = dq.popleft()
            comp += 1
            for nb in adj[c]:          # weak components over the directed rows
                if nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        comps.append(comp)
    return sorted(comps, reverse=True)


def _min_vertex_cut(adj, west, east):
    """Minimum number of HEXES that must be removed to separate `west` from `east` on the directed
    step graph.  Vertex-splitting max-flow (Dinic-free Edmonds-Karp: the cut is ~15, so a handful of
    BFS augmentations).  Returns (cut_size, cut_hexes)."""
    INF = float("inf")
    nodes = list(adj)
    idx = {h: i for i, h in enumerate(nodes)}
    n = len(nodes)
    S, T = 2 * n, 2 * n + 1
    cap: dict[int, dict[int, float]] = {}

    def add(u, v, c):
        cap.setdefault(u, {})[v] = cap.setdefault(u, {}).get(v, 0) + c
        cap.setdefault(v, {}).setdefault(u, 0)

    for h, i in idx.items():
        add(2 * i, 2 * i + 1, INF if (h in west or h in east) else 1.0)
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


def _cheapest(tmap, adj, srcs, dsts, mob):
    import heapq
    from game.movement import step_cost

    dist = {h: 0.0 for h in srcs}
    pq = [(0.0, h) for h in srcs]
    heapq.heapify(pq)
    best = None
    while pq:
        d, h = heapq.heappop(pq)
        if d > dist.get(h, 1e18):
            continue
        if h in dsts:
            best = d
            break
        for nb in adj[h]:
            c = step_cost(tmap, h, nb, mob)
            if c is None:
                continue
            nd = d + c
            if nd < dist.get(nb, 1e18):
                dist[nb] = nd
                heapq.heappush(pq, (nd, nb))
    return best


# ---------------------------------------------------------------------------------------------
# 1 + 2 + 4: the map report
# ---------------------------------------------------------------------------------------------

# MEASURED axials (game.cna_map index, sections ABCDE): El Alamein E3002 = (q32, r118),
# Alexandria E3714 = (q25, r133), Cairo E1830 = (q44, r140), Tobruk C4807 = (q14, r66).
# Axial index 1 (r) is EAST-WEST, index 0 (q) is NORTH-SOUTH with HIGHER q = FURTHER SOUTH
# (Cairo q44 sits south of Alexandria q25).  The Qattara body spans r87-108, q40-49 -- entirely
# WEST of El Alamein's meridian, which is why the west source band must sit west of r87.
# A step in axial space changes r by at most 1, so a COLUMN r = const is a valid vertex separator:
# every west->east path crosses it.  The passable width at meridian r is therefore the number of
# hexes in that column that lie on some legal west->east path for the mobility class.
# All r anchors are resolved from the loaded index per arm, because the 8.1b section-seam fix
# MOVES section D/E axials -- a hardcoded meridian would compare two different places.


def corridor_report() -> dict:
    _maybe_neuter()
    from game import cna_map, hexmap
    from game.terrain import Mobility, Terrain

    tmap, index = cna_map.load_sections("ABCDE")
    rev = {h: lbl for lbl, h in index.items()}
    land = set(tmap.terrain)
    marsh = {h for h, t in tmap.terrain.items() if t == Terrain.SALT_MARSH}

    # --- marsh body (engine adjacency) ---
    seen, comps = set(), []
    for start in marsh:
        if start in seen:
            continue
        comp, dq = set(), deque([start])
        seen.add(start)
        while dq:
            c = dq.popleft()
            comp.add(c)
            for nb in hexmap.neighbors(c):
                if nb in marsh and nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    body = comps[0] if comps else set()

    # --- the 8.1a metric: plain LAND distance from the marsh body to each coastal hex ---
    coast = {h for h in land if any(nb not in land for nb in hexmap.neighbors(h))}
    dist = {h: 0 for h in body}
    dq = deque(body)
    while dq:
        c = dq.popleft()
        for nb in hexmap.neighbors(c):
            if nb in land and nb not in dist:
                dist[nb] = dist[c] + 1
                dq.append(nb)
    widths = {rev.get(h, str(h)): dist[h] for h in coast if h in dist}
    narrow = sorted(widths.items(), key=lambda kv: kv[1])[:8]
    named = {lbl: widths.get(lbl) for lbl in ("E3002", "E3714", "D3231", "D3133", "E3101", "D3232")}

    out = {
        "hexsides_loaded": len(tmap.hexsides),
        "land_hexes": len(land),
        "marsh_total": len(marsh),
        "marsh_components": [len(c) for c in comps[:5]],
        "largest_body": len(body),
        "land_width_named": named,
        "land_width_narrowest": narrow,
    }

    # --- the honest metric: minimum vertex cut of the Alamein sector, per mobility ---
    r_alamein = index["E3002"][1]
    r_alex = index["E3714"][1]
    body_r = sorted({h[1] for h in body})
    R_WEST = body_r[0] - 7           # west of the depression's western end
    R_EAST = r_alex - 3              # the Delta's doorstep
    PROFILE_R = range(R_WEST + 4, r_alex + 3)
    west = {h for h in land if h[1] <= R_WEST}
    east = {h for h in land if h[1] >= R_EAST}
    out["marsh_body_r_range"] = [body_r[0], body_r[-1]]
    out["anchors"] = {"r_alamein_E3002": r_alamein, "r_alexandria_E3714": r_alex,
                      "r_tobruk_C4807": index["C4807"][1]}
    out["sector"] = {"west_band_r<=": R_WEST, "east_band_r>=": R_EAST,
                     "west_hexes": len(west), "east_hexes": len(east)}

    body_q = sorted(h[0] for h in body)
    for mob in (Mobility.VEHICLE, Mobility.MOTORIZED, Mobility.FOOT):
        adj = _passable_graph(tmap, mob)
        radj: dict = {h: [] for h in adj}
        for h, row in adj.items():
            for nb in row:
                radj[nb].append(h)

        def flood(seed, g):
            seen, dq = set(seed), deque(seed)
            while dq:
                c = dq.popleft()
                for nb in g[c]:
                    if nb not in seen:
                        seen.add(nb)
                        dq.append(nb)
            return seen

        fw = flood(west & set(adj), adj)          # reachable FROM the west
        bw = flood(east & set(adj), radj)         # can REACH the east
        live = fw & bw                            # hexes on some legal west->east route
        # keyed by OFFSET from El Alamein's own meridian so the two arms compare like with like
        profile = {r - r_alamein: sum(1 for h in live if h[1] == r) for r in PROFILE_R}
        narrow_r = min(profile, key=lambda r: profile[r])

        cut, cut_hexes = _min_vertex_cut(adj, west, east)
        labels = sorted(rev.get(h, str(h)) for h in cut_hexes)
        cut_q = sorted(h[0] for h in cut_hexes)
        cut_r = sorted(h[1] - r_alamein for h in cut_hexes)
        srcs = {h for h in land if h[1] == R_WEST}
        dsts = {h for h in land if h[1] == R_EAST}
        out[f"cut_{mob.value}"] = {
            "min_vertex_cut": cut,
            "cut_hexes": labels,
            "cut_q_range": [cut_q[0], cut_q[-1]] if cut_q else None,
            "cut_offset_range_from_alamein": [cut_r[0], cut_r[-1]] if cut_r else None,
            "marsh_body_q_range": [body_q[0], body_q[-1]] if body_q else None,
            "width_profile_by_offset_from_alamein": profile,
            "width_at_alamein": profile.get(0),
            "width_at_alexandria": profile.get(r_alex - r_alamein),
            "narrowest_column_offset": [narrow_r, profile[narrow_r]],
            "live_hexes": len(live),
        }
        out[f"cut_{mob.value}"]["cheapest_cp"] = _cheapest(tmap, adj, srcs, dsts, mob)
        # the flank: at each meridian, how many live hexes sit SOUTH of the marsh body?
        qmax = max(body_q, default=0)
        south = {r - r_alamein: sum(1 for h in live if h[1] == r and h[0] > qmax)
                 for r in range(body_r[0], r_alamein + 4)}
        out[f"cut_{mob.value}"]["live_south_of_marsh_by_offset"] = south
        # SANITY: dead hexes and graph fragmentation
        indeg = {h: 0 for h in adj}
        for h, row in adj.items():
            for nb in row:
                indeg[nb] = indeg.get(nb, 0) + 1
        no_exit = [rev.get(h, str(h)) for h, row in adj.items() if not row]
        no_entry = [rev.get(h, str(h)) for h in adj if indeg.get(h, 0) == 0]
        comps_sz = _components(adj)
        out[f"sanity_{mob.value}"] = {
            "hexes_with_no_exit": len(no_exit), "no_exit_sample": sorted(no_exit)[:12],
            "hexes_with_no_entry": len(no_entry), "no_entry_sample": sorted(no_entry)[:12],
            "weak_components": comps_sz[:6], "n_components": len(comps_sz),
            "directed_edges": sum(len(r) for r in adj.values()),
        }

    # --- the flank: can a VEHICLE get east round the depression, north side vs south side? ---
    # HIGHER q = FURTHER SOUTH (Cairo q44 sits south of Alexandria q25).
    from game.terrain import Mobility as M
    adjv = _passable_graph(tmap, M.VEHICLE)
    body_q_max = max(h[0] for h in body) if body else 0
    body_q_min = min(h[0] for h in body) if body else 0

    def _restrict(adj, keep):
        return {h: [nb for nb in row if nb in keep] for h, row in adj.items() if h in keep}

    for name, keep in (
        ("coastal_north_of_body", {h for h in land if h[0] < body_q_min}),
        ("southern_flank", {h for h in land if h[0] > body_q_max}),
    ):
        sub = _restrict(adjv, keep)
        srcs = {h for h in sub if h[1] == R_WEST}
        dsts = {h for h in sub if h[1] == R_EAST}
        out[f"flank_{name}"] = {
            "hexes": len(sub), "srcs": len(srcs), "dsts": len(dsts),
            "vehicle_cp": _cheapest(tmap, sub, srcs, dsts, M.VEHICLE) if srcs and dsts else None,
        }

    # --- SANITY: is the theatre still one connected vehicle road, end to end? ---
    keys = {k: index[k] for k in ("A4827", "C4807", "C4321", "D3714", "E3002", "E3714", "E1830")
            if k in index}
    pairs = {}
    for a, ha in keys.items():
        for b, hb in keys.items():
            if a >= b:
                continue
            pairs[f"{a}->{b}"] = _cheapest(tmap, adjv, {ha}, {hb}, M.VEHICLE)
            pairs[f"{b}->{a}"] = _cheapest(tmap, adjv, {hb}, {ha}, M.VEHICLE)
    out["sanity_key_hex_vehicle_cp"] = pairs
    out["sanity_key_hex_unreachable"] = sorted(k for k, v in pairs.items() if v is None)
    return out


# ---------------------------------------------------------------------------------------------
# 3: the campaign fold
# ---------------------------------------------------------------------------------------------

def campaign_report(seed: int) -> dict:
    """One worker = one 111-turn fold.  Wrapped so a single bad seed reports itself instead of
    taking the whole pool's completed folds down with it (learned the hard way)."""
    try:
        return _campaign_report(seed)
    except Exception as exc:                                  # noqa: BLE001 - a driver, not engine code
        import traceback
        return {"seed": seed, "ERROR": f"{type(exc).__name__}: {exc}",
                "tb": traceback.format_exc()[-1500:]}


def _campaign_report(seed: int) -> dict:
    _maybe_neuter()
    from game import coords
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.engine import determinism_signature, run
    from game.events import Side
    from game.scenario import campaign

    init = campaign(seed=seed)
    n_hexsides = len(init.terrain.hexsides)
    res = run(init, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final

    def east(side):
        hs = [u.hex for u in fin.units
              if u.side == side and getattr(u, "is_combat", True) and u.strength > 0
              and fin.on_map(u)]
        return max((h[1] if isinstance(h, tuple) else coords.to_axial(h)[1]) for h in hs) if hs else None

    best, best_turn = 0, None
    for e in res.events:
        p = e.payload or {}
        h = p.get("to") or p.get("hex")
        if isinstance(h, (list, tuple)) and len(h) == 2 and e.side == Side.AXIS:
            if h[1] > best:
                best, best_turn = h[1], getattr(e, "turn", None)
    return {
        "seed": seed,
        "hexsides_loaded": n_hexsides,
        "winner": None if res.winner is None else res.winner.value,
        "reason": res.reason,
        "axis_furthest_east_ever": best,
        "axis_east_ever_turn": best_turn,
        "axis_furthest_east_at_end": east(Side.AXIS),
        "cw_furthest_west_at_end": min(
            (u.hex[1] for u in fin.units
             if u.side == Side.ALLIED and getattr(u, "is_combat", True)
             and u.strength > 0 and fin.on_map(u)), default=None),
        "events": len(res.events),
        "signature": determinism_signature(res.events),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("corridor", "campaign", "both"), default="both")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1941, 7, 4, 24, 2026, 99, 1])
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--out", default="scratchpad/gate81b.json")
    args = ap.parse_args()

    doc = {"neuter": NEUTER}
    if args.mode in ("corridor", "both"):
        doc["corridor"] = corridor_report()
        print(json.dumps(doc["corridor"], indent=1))
    if args.mode in ("campaign", "both"):
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            doc["campaigns"] = []
            for r in pool.map(campaign_report, args.seeds):
                doc["campaigns"].append(r)
                with open(args.out, "w") as f:                # checkpoint every fold
                    json.dump(doc, f, indent=1)
        for r in doc["campaigns"]:
            if "ERROR" in r:
                print(f"  seed {r['seed']}: {r['ERROR']}")
                continue
            print(f"  seed {r['seed']}: hx={r['hexsides_loaded']} {r['winner']} "
                  f"| ever r{r['axis_furthest_east_ever']} | end r{r['axis_furthest_east_at_end']} "
                  f"| {r['reason']}")
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
