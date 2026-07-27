"""Phase 8.1b: the escarpment hexside trace, wired into TerrainMap.hexsides.

data/hexsides_<section>.json (tools/vassal/extract_hexsides.py) is classifier output, exactly
like data/terrain_<section>.json before it (tests/test_map_terrain_fills.py's own framing) -- so
this file pins the same class of thing: the raw counts (EXACT per section, as the fills are, not a
band: a +-20% band would not notice a fifth of the rim going missing), the [8.35]/[8.42] direction
convention decoding correctly, and all FOUR previously-dead consumers lighting up on the real map
-- movement.step_cost's hexside CP, movement.breakdown_points' hexside BP, zoc.py's
ZOC_BLOCKING_HEXSIDES, and engine._assault_hexside_shift's [15.33/15.35/15.36] differential -- plus
the [8.37] Anti-Armor "P" that the trace made reachable.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import cna_map, combat_tables, coords                           # noqa: E402
from game.hexmap import neighbors                                         # noqa: E402
from game.movement import breakdown_points, edge, step_cost               # noqa: E402
from game.terrain import Hexside, Mobility                                # noqa: E402
from game.zoc import zoc_extends                                          # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
SECTIONS = "ABCDE"

# The trace, per section, filed under each edge's DOWN hex (extract_hexsides.py's bucketing rule).
# EXACT, re-derived from the raster 2026-07-26 by the repaired acceptance rule (one-sidedness,
# [8.35], replacing a component-size filter that silently dropped five real band segments).
TRACED = {"A": 36, "B": 5, "C": 41, "D": 78, "E": 34}
LOADED_UNDIRECTED = 189      # 194 traced - 5 whose down or up hex colour-sampled as sea


def _raw_escarpment() -> dict:
    return {s: json.loads((DATA / f"hexsides_{s}.json").read_text())["escarpment"]
            for s in SECTIONS}


def test_the_trace_is_194_edges_all_escarpment_filed_under_its_down_hex():
    """Exact counts, not a band. Every [down, up] pair is filed under the DOWN hex's own section
    letter -- a loud, cheap check that a future re-trace did not mix up the convention."""
    raw = _raw_escarpment()
    assert {s: len(v) for s, v in raw.items()} == TRACED
    for section, edges in raw.items():
        for down, up in edges:
            assert down[0] == section, f"{down}->{up} filed under {section}, down is {down[0]}"


def test_hexsides_load_directed_both_ways_with_no_ties():
    """Every traced edge becomes exactly two directed TerrainMap.hexsides entries (the [8.35]
    ruling: ink/splash side = DOWN), and the two counts must be equal -- an UP with no matching
    DOWN (or vice versa) means the loader or the trace's orientation broke."""
    tmap, index = cna_map.load_sections("ABCDE")
    ups = [k for k, v in tmap.hexsides.items() if v is Hexside.UP_ESCARPMENT]
    downs = [k for k, v in tmap.hexsides.items() if v is Hexside.DOWN_ESCARPMENT]
    assert len(ups) == len(downs) == LOADED_UNDIRECTED
    assert len(tmap.hexsides) == len(ups) + len(downs)
    for down_ax, up_ax in ups:
        assert (up_ax, down_ax) in tmap.hexsides
        assert tmap.hexsides[(up_ax, down_ax)] is Hexside.DOWN_ESCARPMENT


def test_hexsides_scale_with_the_requested_sections():
    """A C-only load must carry only escarpment edges with both ends inside Map C -- FEWER than
    the 41 filed under C, because an edge filed under a C down-hex may climb into B or D, and its
    up hex then does not exist. Loading more sections only ever adds entries, never removes or
    reorders the existing ones (each edge's axial identity is section-independent)."""
    tmap_c, _ = cna_map.load_section("C")
    tmap_abc, _ = cna_map.load_sections("ABC")
    tmap_all, _ = cna_map.load_sections("ABCDE")
    assert len(tmap_c.hexsides) // 2 < TRACED["C"]
    assert 0 < len(tmap_c.hexsides) < len(tmap_abc.hexsides) < len(tmap_all.hexsides)
    assert set(tmap_c.hexsides.items()) <= set(tmap_abc.hexsides.items())
    assert set(tmap_abc.hexsides.items()) <= set(tmap_all.hexsides.items())


def test_a_sea_touching_escarpment_edge_is_silently_dropped_not_promoted():
    """[8.1b Sec 3.5.6]: an edge whose down or up hex colour-sampled as sea has no entry in
    `terrain` and must not appear in `hexsides` either -- not promoted to land the way a coastal
    ROAD hex is (cna_map._load_edges' own, different, evidence-backed exception)."""
    tmap, index = cna_map.load_sections("ABCDE")
    raw = _raw_escarpment()
    dropped = 0
    for section, edges in raw.items():
        for down, up in edges:
            dax = coords.to_axial(coords.parse(down))
            uax = coords.to_axial(coords.parse(up))
            if dax not in tmap.terrain or uax not in tmap.terrain:
                dropped += 1
                assert (dax, uax) not in tmap.hexsides
                assert (uax, dax) not in tmap.hexsides
    assert dropped > 0, "expected at least one sea-touching escarpment edge (Sec 3.5.6)"


def test_up_escarpment_bars_only_vehicles_matching_the_837_chart():
    """[8.42]: "No vehicle may ever move up an escarpment" -- EVERY one of the traced up
    directions, not a sampled one; foot pays a real, non-prohibitive cost, because the chart's
    UP_ESCARPMENT motorized cost is PROHIBITED outright while its non-Mot cost is merely +6.

    The reverse direction is DOWN_ESCARPMENT and the chart prices it (+8 Mot), so the HEXSIDE
    never bars a descent -- but the descent may still be barred by what is at the bottom: 50 of
    these rims drop into the Qattara salt marsh, which [8.44] closes to a vehicle off a Road or
    Track. That is two faithful rules composing, not an escarpment that blocks both ways, and the
    test says so rather than sampling an edge where it does not show."""
    tmap, index = cna_map.load_sections("ABCDE")
    from game.terrain import Terrain, hexside_cost
    ups = [k for k, v in tmap.hexsides.items() if v is Hexside.UP_ESCARPMENT]
    assert hexside_cost(Hexside.DOWN_ESCARPMENT, Mobility.VEHICLE) == 8
    barred_descents = 0
    for src, dst in ups:
        assert step_cost(tmap, src, dst, Mobility.VEHICLE) is None
        assert step_cost(tmap, src, dst, Mobility.MOTORIZED) is None
        foot_cost = step_cost(tmap, src, dst, Mobility.FOOT)
        assert foot_cost is not None and foot_cost > 0
        assert tmap.hexsides[(dst, src)] is Hexside.DOWN_ESCARPMENT
        if step_cost(tmap, dst, src, Mobility.VEHICLE) is None:
            assert tmap.terrain[src] is Terrain.SALT_MARSH, "a DOWN escarpment barred a vehicle"
            barred_descents += 1
    assert barred_descents == 50


def test_a_road_does_not_carry_a_vehicle_up_the_one_escarpment_it_crosses():
    """[8.33] verbatim: "Units which are moving along Roads or Tracks ignore, for movement
    purposes, any other terrain in the hex or hexside, WITH THE EXCEPTION OF VEHICLES CROSSING
    ESCARPMENTS (see 8.42)." So chart note 6 ("a Road negates all hexside terrain feature entry
    costs and Breakdown Point Values") stops at an escarpment for a motorized unit, and [8.42]'s
    "no vehicle may ever" stays unconditional -- while FOOT on the same road is not excepted and
    pays nothing. This is half of Block A's Sec 3.6 ship-blocking worry, measured: exactly
    ONE traced escarpment edge on the whole board coincides with a road (A5533/B5400, the Tocra
    coastal escarpment), none with a track or a railroad."""
    tmap, index = cna_map.load_sections("ABCDE")
    on_road = {edge(a, b) for a, b in tmap.hexsides} & set(tmap.roads)
    assert on_road == {edge(index["A5533"], index["B5400"])}
    assert not {edge(a, b) for a, b in tmap.hexsides} & (set(tmap.tracks) | set(tmap.rails))

    low, high = index["A5533"], index["B5400"]
    assert tmap.hexsides[(low, high)] is Hexside.UP_ESCARPMENT
    assert step_cost(tmap, low, high, Mobility.VEHICLE) is None          # the road does not help
    assert step_cost(tmap, low, high, Mobility.FOOT) == 1.0              # note 6 still applies
    # ...and coming DOWN the road, the vehicle pays the chart's full +8 CP / 6 BP on top of the
    # road's own 1/2 hex entry and 1/2 Breakdown Value -- neither negated, neither halved.
    assert step_cost(tmap, high, low, Mobility.VEHICLE) == 8.5
    assert breakdown_points(tmap, high, low, Mobility.VEHICLE) == 6.5
    assert breakdown_points(tmap, high, low, Mobility.FOOT) == 0.0


def test_the_rim_leaves_no_hex_vehicle_unreachable():
    """The other half of Block A's Sec 3.6 flag, and the reason it is not ship-blocking: an
    escarpment is ONE-WAY for a vehicle, not a wall. Forward vehicle reachability over the whole
    board is byte-identical with the rim and with it stripped -- every hex above an escarpment is
    still reachable, by the long way round."""
    tmap, index = cna_map.load_sections("ABCDE")
    no_rim = replace(tmap, hexsides={})

    def reachable(m, mob):
        seen, stack = {index["A5533"]}, [index["A5533"]]
        while stack:
            u = stack.pop()
            for v in neighbors(u):
                if v in seen or v not in m.terrain or step_cost(m, u, v, mob) is None:
                    continue
                seen.add(v)
                stack.append(v)
        return seen

    for mob in (Mobility.VEHICLE, Mobility.FOOT):
        assert reachable(tmap, mob) == reachable(no_rim, mob)


def test_breakdown_points_read_the_traced_hexsides():
    """The third dead consumer: movement.breakdown_points' hexside term ([8.37] Down Escarpment
    Breakdown Value +6; note 8's exception means a Track does NOT halve it for a vehicle)."""
    tmap, index = cna_map.load_sections("ABCDE")
    down = next(k for k, v in tmap.hexsides.items() if v is Hexside.DOWN_ESCARPMENT)
    src, dst = down
    plain = breakdown_points(tmap, src, dst, Mobility.VEHICLE)
    assert plain == breakdown_points(replace(tmap, hexsides={}), src, dst, Mobility.VEHICLE) + 6
    assert breakdown_points(tmap, src, dst, Mobility.FOOT) == 0.0        # 21.11


def test_close_assault_differential_reads_the_traced_hexsides():
    """The fourth dead consumer: engine._assault_hexside_shift -> combat_tables.HEXSIDE_CA_SHIFT,
    [8.37]'s Close Assault column (Up Escarpment L3 = -3 for the attacker coming up, Down
    Escarpment R1 = +1 for the attacker coming down), read over the real map."""
    from game import engine
    tmap, index = cna_map.load_sections("ABCDE")
    low, high = next(k for k, v in tmap.hexsides.items() if v is Hexside.UP_ESCARPMENT)
    assert engine._assault_hexside_shift(tmap, {low}, high) == -3
    assert engine._assault_hexside_shift(tmap, {high}, low) == +1
    assert combat_tables.HEXSIDE_CA_SHIFT[Hexside.UP_ESCARPMENT] == -3
    assert combat_tables.HEXSIDE_CA_SHIFT[Hexside.DOWN_ESCARPMENT] == +1


def test_zoc_does_not_cross_a_traced_escarpment():
    """[10.21a/b] via game.zoc.ZOC_BLOCKING_HEXSIDES -- dead code before this slice landed any
    hexsides (zoc.py:26 had nothing to match against on the real map). Blocks BOTH directions and
    every mobility class, matching the rule (ZOC is a control effect, not a movement one)."""
    tmap, index = cna_map.load_sections("ABCDE")
    up_edge = next(k for k, v in tmap.hexsides.items() if v is Hexside.UP_ESCARPMENT)
    src, dst = up_edge
    assert zoc_extends(src, dst, tmap, Mobility.FOOT) is False
    assert zoc_extends(dst, src, tmap, Mobility.FOOT) is False
    assert zoc_extends(src, dst, tmap, Mobility.VEHICLE) is False


def test_anti_armor_fire_may_not_cross_an_up_escarpment():
    """[8.37], scan p.70: the Up Escarpment row's Anti-Armor cell is "P" -- Prohibited, not a
    column shift. A firer on the coastal strip may not shoot at armour standing on the plateau
    above it. This cell was unreachable while TerrainMap.hexsides was empty; the trace made it
    live. Synthetic map (the real board guarantees no armour placement), and the control is the
    same firer with the SAME two adjacent armour stacks and no escarpment: it must then fire at
    the hex it was just barred from, so a test that merely silenced the firer cannot pass."""
    from game.engine import _Run, _anti_armor_step
    from game.events import EventKind, Phase, Side
    from game.movement import TerrainMap
    from game.state import GameState, StepRecord, Unit, VP
    from game.terrain import Terrain

    home = (0, 0)
    up, flat = neighbors(home)[0], neighbors(home)[1]
    terr = {h: Terrain.CLEAR for h in (home, up, flat)}
    firer = Unit("G", Side.AXIS, home, (StepRecord("at", 4),), mobility=Mobility.FOOT,
                 cpa=10, stacking_points=1, oca=2, dca=2, anti_armor=6, vulnerability=2, ammo=99)
    tanks = tuple(Unit(f"T{i}", Side.ALLIED, h, (StepRecord("tank", 4),),
                       mobility=Mobility.VEHICLE, cpa=10, stacking_points=1, oca=3, dca=3,
                       armor_protection=4)
                  for i, h in enumerate((up, flat)))

    def targets(hexsides):
        st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=7,
                       weather="clear", vp=VP(),
                       terrain=TerrainMap(terrain=terr, hexsides=hexsides), control={},
                       units=(firer, *tanks), target_hex=home, supplies=(),
                       consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 0, "FUEL": 0})
        r = _Run(st)
        _anti_armor_step(r, Side.AXIS, Side.ALLIED, set(), set(), set())
        return [tuple(e.payload["target"]) for e in r.events
                if e.kind is EventKind.ANTI_ARMOR_RESOLVED]

    assert targets({}) == [up]                                  # control: nearest armour, no rim
    assert targets({(home, up): Hexside.UP_ESCARPMENT,
                    (up, home): Hexside.DOWN_ESCARPMENT}) == [flat]


def test_15_34_a_motorized_unit_may_never_close_assault_up_an_escarpment():
    """[15.34], scan p.23, verbatim: "Certain terrain prohibits full Close Assaults or Probes by
    certain types of units. MOTORIZED UNITS MAY NEVER ASSAULT UP AN ESCARPMENT, EVEN IF IT IS
    CROSSED BY A TRACK. (You may, of course, take your infantry out of the Trucks and then
    Assault.)"

    The sentence immediately after it -- "Motorized units may not assault units defending in Salt
    Marshes" -- was already implemented (engine._salt_marsh_barred_assault); this one was not, and
    like the [8.37] Anti-Armor "P" it was UNREACHABLE while TerrainMap.hexsides was empty, so the
    escarpment trace is what makes it bite. It is a PROHIBITION, not the Up Escarpment L3 column
    shift that engine._assault_hexside_shift already applies: the chart's L3 prices the assault
    a non-motorized unit is allowed to make, and 15.34 forbids the motorized one outright.

    Four cases, so that nothing passes by merely silencing the attacker: the motorized unit is
    barred UP, the SAME unit resolves with the rim removed, FOOT resolves across the very same
    escarpment (the rule's own "take your infantry out of the Trucks" parenthetical), and the
    motorized unit resolves coming DOWN -- only "up" is named."""
    from game.engine import _Run, _resolve_combat
    from game.events import EventKind, Phase, Side
    from game.movement import TerrainMap
    from game.state import GameState, StepRecord, Unit, VP
    from game.terrain import Terrain

    low, high = (0, 0), neighbors((0, 0))[0]
    terr = {low: Terrain.CLEAR, high: Terrain.CLEAR}
    rim = {(low, high): Hexside.UP_ESCARPMENT, (high, low): Hexside.DOWN_ESCARPMENT}

    def assault(attacker_hex, target, mobility, hexsides):
        atk = Unit("A", Side.AXIS, attacker_hex, (StepRecord("inf", 4),), mobility=mobility,
                   cpa=10, stacking_points=1, oca=4, dca=2, ammo=100)
        dfn = Unit("D", Side.ALLIED, target, (StepRecord("inf", 4),), mobility=Mobility.FOOT,
                   cpa=10, stacking_points=1, oca=2, dca=2, ammo=100)
        st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
                       weather="clear", vp=VP(),
                       terrain=TerrainMap(terrain=terr, hexsides=hexsides), control={},
                       units=(atk, dfn), target_hex=target, supplies=(),
                       consumed={"AMMO": 0}, initial_supply={"AMMO": 0})
        r = _Run(st)
        resolved = _resolve_combat(r, Side.AXIS, "AXIS/Front", [atk], [dfn], target, set(), set())
        rejected = [e for e in r.events if e.kind is EventKind.ORDER_REJECTED]
        return resolved, rejected, atk

    resolved, rejected, atk = assault(low, high, Mobility.MOTORIZED, rim)
    assert resolved is False, "[15.34] a motorized unit assaulted UP an escarpment"
    assert rejected, "the barred assault must be rejected loudly, not silently dropped"
    assert atk.ammo == 100, "a barred attacker must not spend its close-assault load"

    assert assault(low, high, Mobility.MOTORIZED, {})[0] is True    # control: the rim is the cause
    assert assault(low, high, Mobility.FOOT, rim)[0] is True        # "take your infantry out"
    assert assault(high, low, Mobility.MOTORIZED, rim)[0] is True   # only "up" is named


def test_the_alamein_rim_does_not_narrow_the_front():
    """[8.1b's headline finding]: only UP_ESCARPMENT and MAJOR_RIVER are prohibited to a vehicle in
    the whole [8.37] hexside table, and the Qattara rim's escarpment lies entirely on the
    depression's own north face -- four hexes west of El Alamein's meridian, per
    scratchpad/port/hexside-trace.md Sec 5.3. So a vehicle can walk around the depression's eastern
    tip on ground the escarpment never touches: the cheapest coastal route is unaffected by the
    hexsides being present at all. Cheap, deterministic proxy for the slice's own min-vertex-cut
    probe (scratchpad/hexside/corridor2.py): the coastal road route from west of the depression to
    Alexandria costs the same with or without the traced rim."""
    from dataclasses import replace
    tmap, index = cna_map.load_sections("ABCDE")
    no_rim = replace(tmap, hexsides={})
    west, alex = index["D0233"], index["E3714"]

    def cheapest(m):
        import heapq
        from game.hexmap import neighbors
        dist = {west: 0.0}
        pq = [(0.0, west)]
        while pq:
            du, u = heapq.heappop(pq)
            if u == alex:
                return du
            if du > dist.get(u, 1e18):
                continue
            for v in neighbors(u):
                if v not in m.terrain:
                    continue
                c = step_cost(m, u, v, Mobility.MOTORIZED)
                if c is None:
                    continue
                nd = du + c
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        return None

    assert cheapest(tmap) == cheapest(no_rim)
