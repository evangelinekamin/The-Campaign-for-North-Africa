"""A small *toy* scenario on the real engine — NOT yet Rommel's Arrival's OOB.

An 8-hex coastal corridor (a road along the clear coast, a desert row inland, one
escarpment hexside as an obstacle) with a port objective at the east end. Its job
is to exercise the real movement + ZOC + stacking core inside the turn loop. The
faithful Rommel's Arrival OOB (rule 61) is transcribed once combat + supply +
coordinate-conversion land.

Geography (axial coords): row r=0 is the coast (CLEAR + coastal road), r=1 is the
DESERT plateau, with an escarpment between them at q=3. Axis enters west and
drives the road for the port (7,0); the Commonwealth holds it.
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace

from . import cna_map, coords, oob
from .events import Phase, Side
from .hexmap import neighbors
from .movement import TerrainMap, edge
from .state import GameState, StepRecord, SupplyUnit, Unit, VP
from .terrain import Hexside, Mobility, Terrain

LENGTH = 8
MAX_TURNS = 8

# Fortified major cities of the corridor (rule 15.82): label -> fortification
# level. A MAJOR_CITY hex both exempts its garrison from retreat/eviction and, at
# the given level, stiffens the close-assault defense. Extensible -- add a label to
# fortify another town. Tobruk (C4807) and Bardia (C4321) are the victory hexes.
MAJOR_CITIES: dict[str, int] = {"C4807": 2, "C4321": 2}


def _apply_major_cities(terrain: dict) -> dict:
    """Mark each MAJOR_CITIES hex as MAJOR_CITY terrain (in place, fixing the data
    bug where coastal towns colour-sample as CLEAR) and return the fortification
    map (hex -> level) for the TerrainMap."""
    forts: dict = {}
    for label, level in MAJOR_CITIES.items():
        h = coords.to_axial(coords.parse(label))
        terrain[h] = Terrain.MAJOR_CITY
        forts[h] = level
    return forts


def coastal_corridor(seed: int = 1941) -> GameState:
    terrain: dict = {}
    for q in range(LENGTH):
        terrain[(q, 0)] = Terrain.MAJOR_CITY if q == LENGTH - 1 else Terrain.CLEAR
        terrain[(q, 1)] = Terrain.DESERT

    roads = frozenset(edge((q, 0), (q + 1, 0)) for q in range(LENGTH - 1))
    hexsides = {
        ((3, 0), (3, 1)): Hexside.UP_ESCARPMENT,     # coast -> plateau: climb
        ((3, 1), (3, 0)): Hexside.DOWN_ESCARPMENT,   # plateau -> coast: descend
    }
    tmap = TerrainMap(terrain=terrain, hexsides=hexsides, roads=roads)
    target = (LENGTH - 1, 0)

    units = (
        Unit("DAK-5le", Side.AXIS, (0, 0),
             (StepRecord("pz", 3), StepRecord("inf", 2)),
             mobility=Mobility.VEHICLE, cpa=25, stacking_points=2, oca=6, dca=6),
        Unit("IT-Ariete", Side.AXIS, (1, 1),
             (StepRecord("tank", 3), StepRecord("inf", 2)),
             mobility=Mobility.VEHICLE, cpa=20, stacking_points=2, oca=5, dca=5),
        Unit("UK-2Armd", Side.ALLIED, (6, 0),
             (StepRecord("cruiser", 3),),
             mobility=Mobility.VEHICLE, cpa=20, stacking_points=2, oca=6, dca=6),
        Unit("UK-9Aus", Side.ALLIED, target,
             (StepRecord("inf", 4),),
             mobility=Mobility.FOOT, cpa=10, stacking_points=2, oca=5, dca=8),
    )

    # One supply dump co-located with each combat unit (rule 32.15 max 40/60).
    supplies = (
        SupplyUnit("AX-Dump1", Side.AXIS, (0, 0), ammo=40, fuel=60),
        SupplyUnit("AX-Dump2", Side.AXIS, (1, 1), ammo=40, fuel=60),
        SupplyUnit("UK-Dump1", Side.ALLIED, (6, 0), ammo=40, fuel=60),
        SupplyUnit("UK-Dump2", Side.ALLIED, target, ammo=40, fuel=60),
    )
    initial = {
        "AMMO": sum(s.ammo for s in supplies),
        "FUEL": sum(s.fuel for s in supplies),
    }

    return GameState(
        turn=1, max_turns=MAX_TURNS, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="clear", move_modifier=0, vp=VP(),
        terrain=tmap, control={}, units=units, target_hex=target,
        supplies=supplies, consumed={"AMMO": 0, "FUEL": 0}, initial_supply=initial,
    )


def battle_for_tobruk(seed: int = 1941) -> GameState:
    """A scenario on REAL Map C terrain (from the VASSAL map): an Axis push from
    Bardia toward the Tobruk objective. Terrain is the colour-sampled background
    (data/terrain_C.json); unit stats are placeholders until the OA charts are
    transcribed. This is the map-pipeline -> engine integration proof, not yet
    the full Rommel's Arrival (which needs Maps A/B and the real OOB)."""
    tmap, _ = cna_map.load_section("C")

    def ax(label: str):
        return coords.to_axial(coords.parse(label))

    target = ax("C4807")  # Tobruk (objective)
    # Axis pressed up against the Tobruk perimeter (adjacent land hexes), each
    # with a co-located dump — so they're supplied and in contact. (A static
    # dump can't sustain a long advance until mobile supply lands; see notes.)
    units = (
        Unit("DAK-15Pz", Side.AXIS, ax("C4707"),                     # NW of Tobruk
             (StepRecord("pz", 3), StepRecord("inf", 2)),
             mobility=Mobility.VEHICLE, cpa=25, stacking_points=2, oca=6, dca=6),
        Unit("IT-Ariete", Side.AXIS, ax("C4607"),                    # N of El Adem
             (StepRecord("tank", 3), StepRecord("inf", 2)),
             mobility=Mobility.VEHICLE, cpa=20, stacking_points=2, oca=5, dca=5),
        Unit("UK-Tobruk", Side.ALLIED, target,                       # Tobruk garrison
             (StepRecord("inf", 4),),
             mobility=Mobility.FOOT, cpa=10, stacking_points=2, oca=5, dca=8),
        Unit("UK-7Armd", Side.ALLIED, ax("C4507"),                   # El Adem
             (StepRecord("cruiser", 3),),
             mobility=Mobility.VEHICLE, cpa=20, stacking_points=2, oca=6, dca=6),
    )
    supplies = (
        SupplyUnit("AX-Dump1", Side.AXIS, ax("C4707"), ammo=40, fuel=60),
        SupplyUnit("AX-Dump2", Side.AXIS, ax("C4607"), ammo=40, fuel=60),
        SupplyUnit("UK-Dump", Side.ALLIED, target, ammo=40, fuel=60),
    )
    initial = {"AMMO": sum(s.ammo for s in supplies), "FUEL": sum(s.fuel for s in supplies)}
    return GameState(
        turn=1, max_turns=12, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="clear", move_modifier=0, vp=VP(),
        terrain=tmap, control={}, units=units, target_hex=target,
        supplies=supplies, consumed={"AMMO": 0, "FUEL": 0}, initial_supply=initial,
    )


def _connect_pieces(terrain: dict, hexes) -> None:
    """In-place: bridge coastal pieces to the mainland across the few sea hexes
    between them (the coast road runs along here), so isolated ports/salients like
    El Agheila join the map and their supply can trace. Gaps are 2-3 hexes; this
    is a stopgap until roads/coastal terrain are extracted as line features.
    Deterministic (sorted scans, fixed neighbour order, bounded search)."""
    def largest_component() -> set:
        seen: set = set()
        best: set = set()
        for start in sorted(terrain):
            if start in seen:
                continue
            comp = {start}
            dq = deque([start])
            while dq:
                x = dq.popleft()
                for n in neighbors(x):
                    if n in terrain and n not in comp:
                        comp.add(n)
                        dq.append(n)
            seen |= comp
            if len(comp) > len(best):
                best = comp
        return best

    main = largest_component()
    for h in sorted(set(hexes)):
        if h in main:
            continue
        prev = {h: None}
        dq = deque([h])
        hit = None
        while dq and len(prev) < 3000:                 # bounded; real gaps are tiny
            x = dq.popleft()
            if x in main and x != h:
                hit = x
                break
            for n in neighbors(x):
                if n not in prev:
                    prev[n] = x
                    dq.append(n)
        if hit is None:
            continue
        node = hit
        while node != h:
            terrain.setdefault(node, Terrain.CLEAR)     # coastal land along the road
            main.add(node)
            node = prev[node]
        main.add(h)


def rommels_arrival(seed: int = 1941, *, blanket_supply: bool = False) -> GameState:
    """The REAL Rommel's Arrival OOB (rule 61.2), parsed from the VASSAL setup and
    placed on the connected El-Agheila -> Tobruk corridor (Maps A/B/C, real
    colour-sampled terrain). Unit stats come from the Characteristics Charts as a
    close-assault approximation (see data/unit_stats.json and game.oob). The Axis
    (Rommel/DAK, artillery, the 300th Oasis companies) starts around El Agheila;
    the Commonwealth screen (9th Australian, 2nd Armoured, 3rd Indian) is spread
    across Cyrenaica; the objective is Tobruk. Models the full land Combat Segment
    (barrage + anti-armor + close assault with combined arms, morale/cohesion,
    retreat, surrender, org-size), reinforcement arrival (15th Panzer over turns),
    per-model unit stats, and graded degree-of-success victory. Air/naval and the
    full off-map OOB remain out of scope."""
    tmap, _ = cna_map.load_sections("ABC")
    target = coords.to_axial(coords.parse("C4807"))               # Tobruk
    units, supplies = oob.build(sections="ABC")   # corridor only (drops rear Map-D units)

    # A hex where a land unit stands is land: coastal ports (El Agheila, Tobruk,
    # ...) colour-sample as sea, so add every occupied hex as coastal CLEAR + connect.
    terrain = dict(tmap.terrain)
    for piece in (*units, *supplies):
        terrain.setdefault(piece.hex, Terrain.CLEAR)
    _connect_pieces(terrain, [p.hex for p in (*units, *supplies)])
    forts = _apply_major_cities(terrain)          # Tobruk/Bardia -> fortified MAJOR_CITY (15.82)
    tmap = replace(tmap, terrain=terrain, fortifications=forts)

    # FAITHFUL SUPPLY (default): keep ONLY the authored start-line dumps (rule 32.15,
    # a dump per force concentration). The concentrated attacking core (5th Light and
    # Ariete panzers, the German artillery) can trace both fuel and ammo at t1; the
    # spread-out periphery (the Italian rear divisions, the Cyrenaica screen) starts
    # stranded > 1/2 CPA from a dump and stays so until MOVING supply forward (rule
    # 32.3, engine._supply_movement) reaches it. Scarcity is the point -- the
    # Quartermaster rations fuel and the Axis can outrun its supply.
    #
    # blanket_supply=True restores the old auto-pad crutch (a full 40/60 dump on every
    # stranded unit until nobody is stranded) -- kept only for back-compat/comparison;
    # it erases scarcity and is NOT faithful.
    if blanket_supply:
        from . import supply as _supply

        def _unsupplied(side: Side) -> list[Unit]:
            ps = GameState(turn=1, max_turns=12, phase=Phase.MOVEMENT, active_side=Side.SYSTEM,
                           seed=seed, weather="clear", move_modifier=0, vp=VP(), terrain=tmap,
                           control={}, units=tuple(units), target_hex=target, supplies=tuple(supplies),
                           consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 0, "FUEL": 0})
            return [u for u in units if u.side == side and u.is_combat and not (
                _supply.plan_draw(ps, u, _supply.FUEL, _supply.fuel_cost(u)) is not None
                and _supply.plan_draw(ps, u, _supply.AMMO, _supply.ammo_cost(u, phasing=True)) is not None)]

        for side, prefix in ((Side.AXIS, "AX"), (Side.ALLIED, "AL")):
            i = 0
            while (stranded := _unsupplied(side)) and i < 40:
                supplies.append(SupplyUnit(f"{prefix}-Fwd{i}", side, stranded[0].hex, ammo=40, fuel=60))
                i += 1

    # A supply dump beside a road is on the supply net: add a short road spur so
    # units can trace to it along the road (rule 32.16 trace is priced as roaded).
    road_hexes = {c for e in tmap.roads for c in e}
    spurs = {edge(s.hex, nb) for s in supplies for nb in neighbors(s.hex)
             if nb in road_hexes}
    if spurs:
        tmap = replace(tmap, roads=tmap.roads | spurs)

    initial = {"AMMO": sum(s.ammo for s in supplies),
               "FUEL": sum(s.fuel for s in supplies)}
    return GameState(
        turn=1, max_turns=12, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="clear", move_modifier=0, vp=VP(),
        terrain=tmap, control={}, units=tuple(units), target_hex=target,
        supplies=tuple(supplies), consumed={"AMMO": 0, "FUEL": 0},
        initial_supply=initial,
    )
