"""GATE [8.45] -- ITEM 1: THE FRONT.  Does the Desert gate narrow the Axis last mile?  (read-only)

Extends scratchpad/gate845_desert.py with the two things that gate did not do:

  * DELETION VERIFICATION -- a claimed min-vertex-cut is only a cut if removing it actually
    disconnects the west band from the east band on the engine's own step graph, and only MINIMAL
    if putting any single hex back reopens a route.  Both are checked here (gate81b_cutcheck's
    method, applied to the 8.45 arms).
  * WHERE THE CUT RUNS -- is it a real line (the coast at Alamein, then south-west around the
    depression) or an artifact hugging the map edge?  Reported as: labels, the q (north-south)
    span, the r (east-west) span relative to El Alamein's own meridian, how many cut hexes sit on
    the raster's own boundary, and the terrain each cut hex stands on.

BEFORE = the gate neutered at the CALLER's binding (game.movement.desert_barred), per the
project's documented neuter trap -- movement.py does `from .terrain import desert_barred`, so
patching game.terrain would not reach movement.step_cost's already-bound reference.  The neuter is
PROVEN live below (_prove_neuter) rather than assumed.
AFTER = the gate as HEAD ships it, no patch.

Usage:  PYTHONPATH=<repo> python3 scratchpad/gate845_front.py
"""
from __future__ import annotations

import json
from collections import deque

MOBS = ("LIGHT_TRUCK", "MOTORCYCLE", "VEHICLE", "MOTORIZED", "FOOT")


def _load():
    from game import cna_map
    return cna_map.load_sections("ABCDE")


def _passable_graph(tmap, mob):
    from game.hexmap import neighbors
    from game.movement import step_cost
    out = {}
    for h in tmap.terrain:
        out[h] = [nb for nb in neighbors(h)
                  if tmap.exists(nb) and step_cost(tmap, h, nb, mob) is not None]
    return out


def _min_vertex_cut(adj, west, east):
    """Vertex-splitting max-flow; the min cut is the number of HEXES a defender must hold."""
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
    return flow, [nodes[i] for i in range(n) if (2 * i) in reach and (2 * i + 1) not in reach]


def _reaches(adj, west, east, banned):
    src = {h for h in west if h not in banned}
    seen, dq = set(src), deque(src)
    while dq:
        c = dq.popleft()
        if c in east:
            return True
        for nb in adj[c]:
            if nb not in seen and nb not in banned:
                seen.add(nb)
                dq.append(nb)
    return False


def _cheapest(tmap, adj, srcs, dsts, mob):
    import heapq
    from game.movement import step_cost
    dist = {h: 0.0 for h in srcs}
    pq = [(0.0, h) for h in srcs]
    heapq.heapify(pq)
    while pq:
        d, h = heapq.heappop(pq)
        if d > dist.get(h, 1e18):
            continue
        if h in dsts:
            return d
        for nb in adj[h]:
            c = step_cost(tmap, h, nb, mob)
            if c is None:
                continue
            if d + c < dist.get(nb, 1e18):
                dist[nb] = d + c
                heapq.heappush(pq, (d + c, nb))
    return None


def _sector(tmap, index):
    """The Alamein sector: a west band clear of the depression's western end, an east band on the
    Delta's doorstep.  Identical to gate81b/gate845_desert so the three gates compare like with
    like.  Axial index 1 (r) is EAST-WEST; index 0 (q) is NORTH-SOUTH, HIGHER q = FURTHER SOUTH."""
    from game.hexmap import neighbors
    from game.terrain import Terrain
    land = set(tmap.terrain)
    marsh = {h for h, t in tmap.terrain.items() if t == Terrain.SALT_MARSH}
    seen, comps = set(), []
    for start in marsh:
        if start in seen:
            continue
        comp, dq = set(), deque([start])
        seen.add(start)
        while dq:
            c = dq.popleft()
            comp.add(c)
            for nb in neighbors(c):
                if nb in marsh and nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    body = comps[0] if comps else set()
    body_r = sorted({h[1] for h in body})
    r_alamein, r_alex = index["E3002"][1], index["E3714"][1]
    R_WEST, R_EAST = body_r[0] - 7, r_alex - 3
    return {
        "land": land, "body": body, "r_alamein": r_alamein, "r_alex": r_alex,
        "R_WEST": R_WEST, "R_EAST": R_EAST,
        "west": {h for h in land if h[1] <= R_WEST},
        "east": {h for h in land if h[1] >= R_EAST},
    }


def _arm(tag: str) -> dict:
    from game.hexmap import neighbors
    from game.terrain import Mobility
    tmap, index = _load()
    rev = {h: lbl for lbl, h in index.items()}
    sec = _sector(tmap, index)
    land, west, east = sec["land"], sec["west"], sec["east"]
    r_alamein = sec["r_alamein"]
    body_q = sorted(h[0] for h in sec["body"])
    q_all = sorted(h[0] for h in land)

    out: dict = {"arm": tag, "anchors": {
        "r_alamein_E3002": r_alamein, "r_alexandria_E3714": sec["r_alex"],
        "r_tobruk_C4807": index["C4807"][1], "r_cairo_E1830": index["E1830"][1],
        "west_band_r<=": sec["R_WEST"], "east_band_r>=": sec["R_EAST"],
        "marsh_body_q_range": [body_q[0], body_q[-1]] if body_q else None,
        "map_q_range": [q_all[0], q_all[-1]]}}

    for name in MOBS:
        mob = Mobility[name]
        adj = _passable_graph(tmap, mob)
        cut, cut_hexes = _min_vertex_cut(adj, west, east)
        banned = set(cut_hexes)

        # DELETION VERIFICATION + minimality
        still = _reaches(adj, west & set(adj), east, banned)
        reopen = sum(1 for h in cut_hexes if _reaches(adj, west & set(adj), east, banned - {h}))

        # WHERE THE CUT RUNS
        on_edge = sum(1 for h in cut_hexes if any(nb not in land for nb in neighbors(h)))
        cq = sorted(h[0] for h in cut_hexes)
        cr = sorted(h[1] - r_alamein for h in cut_hexes)
        terr = {}
        for h in cut_hexes:
            terr[str(tmap.terrain[h].value)] = terr.get(str(tmap.terrain[h].value), 0) + 1

        # width profile at each meridian: hexes on SOME legal west->east route
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

        live = flood(west & set(adj), adj) & flood(east & set(adj), radj)
        prof = {r - r_alamein: sum(1 for h in live if h[1] == r)
                for r in range(sec["R_WEST"], sec["R_EAST"] + 1)}
        nmin = min(prof, key=lambda k: prof[k])

        out[name] = {
            "min_vertex_cut": cut,
            "cut_hexes": sorted(rev.get(h, str(h)) for h in cut_hexes),
            "cut_terrain_census": terr,
            "cut_q_range_north_south": [cq[0], cq[-1]] if cq else None,
            "cut_r_offset_from_alamein_range": [cr[0], cr[-1]] if cr else None,
            "cut_hexes_touching_map_boundary": on_edge,
            "DELETING_THE_CUT_still_connects": still,
            "cut_hexes_whose_restoration_reopens": reopen,
            "width_at_alamein_meridian": prof.get(0),
            "narrowest_meridian_offset_and_width": [nmin, prof[nmin]],
            "width_profile_by_offset_from_alamein": prof,
            "live_hexes_on_some_west_east_route": len(live),
            "cheapest_west_east_cp": _cheapest(
                tmap, adj, {h for h in land if h[1] == sec["R_WEST"]},
                {h for h in land if h[1] == sec["R_EAST"]}, mob),
        }
    return out


def _prove_neuter() -> dict:
    """An unchanged number is equally consistent with a neuter that never fired.  Prove the patch
    is live by asking the patched symbol itself, through the caller's binding."""
    import game.movement as movement
    from game.terrain import Mobility
    return {"movement.desert_barred(LIGHT_TRUCK)": movement.desert_barred(Mobility.LIGHT_TRUCK),
            "movement.desert_barred(MOTORCYCLE)": movement.desert_barred(Mobility.MOTORCYCLE),
            "movement.desert_barred(VEHICLE)": movement.desert_barred(Mobility.VEHICLE)}


def main() -> int:
    import game.movement as movement
    doc = {}
    doc["after_probe"] = _prove_neuter()
    doc["after"] = _arm("AFTER  ([8.45] live, HEAD)")

    orig = movement.desert_barred
    movement.desert_barred = lambda m: False
    try:
        doc["before_probe"] = _prove_neuter()
        doc["before"] = _arm("BEFORE ([8.45] neutered at movement's binding)")
    finally:
        movement.desert_barred = orig

    for name in MOBS:
        b, a = doc["before"][name], doc["after"][name]
        print(f"{name:12s} cut {b['min_vertex_cut']:>5.0f} -> {a['min_vertex_cut']:<5.0f}"
              f" | width@Alamein {b['width_at_alamein_meridian']:>3} -> {a['width_at_alamein_meridian']:<3}"
              f" | narrowest {b['narrowest_meridian_offset_and_width']} -> {a['narrowest_meridian_offset_and_width']}"
              f" | cheapest CP {b['cheapest_west_east_cp']} -> {a['cheapest_west_east_cp']}"
              f" | verified-disconnect {not b['DELETING_THE_CUT_still_connects']}/"
              f"{not a['DELETING_THE_CUT_still_connects']}")
    with open("scratchpad/gate845_front_out.json", "w") as f:
        json.dump(doc, f, indent=1)
    print("wrote scratchpad/gate845_front_out.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
