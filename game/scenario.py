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

import math
import random
from collections import deque
from dataclasses import replace

from . import cna_map, coords, logistics_data, oob
from .events import Phase, Side
from .hexmap import distance, neighbors
from .movement import TerrainMap, edge
from .state import Convoy, GameState, Port, StepRecord, SupplyUnit, Unit, VP
from .supply import COMMODITIES, _UNLIMITED, tons_to_points
from .terrain import Hexside, Mobility, Terrain

LENGTH = 8
MAX_TURNS = 8


def _zero_consumed() -> dict:
    return {c: 0 for c in COMMODITIES}


def _initial_supply(supplies) -> dict:
    """Total of each commodity ever introduced at t0 (54.5 conservation base). The
    faucet (SUPPLY_ARRIVED) raises these at runtime; game.invariants checks
    on_hand + consumed == initial per commodity."""
    return {c: sum(getattr(s, c.lower()) for s in supplies) for c in COMMODITIES}

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
    initial = _initial_supply(supplies)

    return GameState(
        turn=1, max_turns=MAX_TURNS, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="clear", move_modifier=0, vp=VP(),
        terrain=tmap, control={}, units=units, target_hex=target,
        supplies=supplies, consumed=_zero_consumed(), initial_supply=initial,
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
    initial = _initial_supply(supplies)
    return GameState(
        turn=1, max_turns=12, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="clear", move_modifier=0, vp=VP(),
        terrain=tmap, control={}, units=units, target_hex=target,
        supplies=supplies, consumed=_zero_consumed(), initial_supply=initial,
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
                _supply.plan_draw(ps, u, _supply.FUEL, _supply.fuel_rate(u)) is not None
                and _supply.plan_draw(ps, u, _supply.AMMO, _supply.ammo_cost(u, phasing=True)) is not None)]

        for side, prefix in ((Side.AXIS, "AX"), (Side.ALLIED, "AL")):
            i = 0
            while (stranded := _unsupplied(side)) and i < 40:
                supplies.append(SupplyUnit(f"{prefix}-Fwd{i}", side, stranded[0].hex, ammo=40, fuel=60))
                i += 1

    # Tobruk sea lifeline (rules 30/56.3/56.28/32.36): a supply dump built into the
    # port, co-located ON the objective (the uncapturable MAJOR_CITY, 15.82). The
    # garrison traces to it at distance 0, and the per-turn ferry (below) refills it,
    # so the fortress can always draw Close-Assault ammunition and never starves out
    # (15.15). Placed here rather than reusing the adjacent AL-Dump#3 (which the Axis
    # can overrun) makes the lifeline robust.
    supplies.append(SupplyUnit("AL-Tobruk", Side.ALLIED, target, ammo=oob.DUMP_AMMO,
                               fuel=oob.DUMP_FUEL, stores=oob.DUMP_STORES, water=oob.DUMP_WATER))

    # A supply dump beside a road is on the supply net: add a short road spur so
    # units can trace to it along the road (rule 32.16 trace is priced as roaded).
    road_hexes = {c for e in tmap.roads for c in e}
    spurs = {edge(s.hex, nb) for s in supplies for nb in neighbors(s.hex)
             if nb in road_hexes}
    if spurs:
        tmap = replace(tmap, roads=tmap.roads | spurs)

    max_turns = 12
    convoys = _rommel_convoys(supplies, target, max_turns, seed)
    ports = _rommel_ports(supplies, target)
    initial = _initial_supply(supplies)
    return GameState(
        turn=1, max_turns=max_turns, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="clear", move_modifier=0, vp=VP(),
        terrain=tmap, control={}, units=tuple(units), target_hex=target,
        supplies=tuple(supplies), consumed=_zero_consumed(),
        initial_supply=initial, convoys=convoys, ports=ports,
    )


# [55.3] per-port MAXIMUM supply tonnage per Operations Stage (the real chart, from
# Step 0). Under 55.14 the tonnage IS the gate; the per-commodity Point caps drop to the
# _UNLIMITED sentinel so tonnage is the sole valve (crossed to Points via 54.5 at the
# landing edge, game.supply.port_landing_cap).
_PORT_TONS = logistics_data.port_supply_tonnage_55_3()


def _load_cargo() -> dict:
    """One representative real-scale (Regime B) Supply-Unit load -- the ferry and rail
    per-turn cargo (game.oob DUMP_* = Tobruk's 61.36 built-in + a wells/rail Water proxy)."""
    return {"AMMO": oob.DUMP_AMMO, "FUEL": oob.DUMP_FUEL,
            "STORES": oob.DUMP_STORES, "WATER": oob.DUMP_WATER}


def _caps_tonnage(tons: int) -> dict:
    """55.14 port caps: per-commodity Point caps _UNLIMITED (so tonnage is the sole gate)
    plus the 55.3 tonnage rating crossed to Points at the landing edge (54.5)."""
    return {"cap_ammo": _UNLIMITED, "cap_fuel": _UNLIMITED, "cap_stores": _UNLIMITED,
            "cap_water": _UNLIMITED, "cap_tons": tons}


def _axis_rear(supplies, target):
    axis = [s for s in supplies if s.side == Side.AXIS]
    return max(axis, key=lambda s: (distance(s.hex, target), s.id)) if axis else None


def _cw_railhead(supplies, target):
    cw = [s for s in supplies if s.side == Side.ALLIED and s.id != "AL-Tobruk"]
    return max(cw, key=lambda s: (distance(s.hex, target), s.id)) if cw else None


def _rommel_ports(supplies, target) -> tuple[Port, ...]:
    """The scenario's ports and their built-in dumps (56.28), seeded from the real 55.3
    tonnages + the 61.6 scenario Efficiency Levels. Tonnage is the sole 55.14 gate (the
    per-commodity caps are _UNLIMITED). Per 61.6: Tobruk starts at Efficiency 7 of 7 (the
    rulebook seeds 7 verbatim -- above its 55.3 listed max of 5, San Giorgio penalty
    unaccounted; transcribed as stated, not silently reconciled) and Benghazi is scuttled
    to Efficiency 0 of 3 (the Axis wrecked it -- it lands nothing until engineers clear it,
    game.engine.HARBOUR_BLOCKED). The Commonwealth base proxies Alexandria (55.3 15000 t)
    at full efficiency. Tonnages are the real 55.3 chart; the port geography (rearmost
    Axis dump / easternmost CW dump) is the scenario proxy for off-corridor Tripoli/Cairo."""
    ports = [Port("PORT-Tobruk", Side.ALLIED, target, "major", max_eff=7, eff=7,
                  **_caps_tonnage(_PORT_TONS["tobruk"]["tons"]))]        # 61.6 eff 7; 55.3 1700 t
    axis_rear = _axis_rear(supplies, target)
    if axis_rear is not None:
        ports.append(Port("PORT-Benghazi", Side.AXIS, axis_rear.hex, "major",
                          max_eff=3, eff=0,                              # 61.6 scuttled to 0; 55.3 2500 t
                          **_caps_tonnage(_PORT_TONS["benghazi"]["tons"])))
    cw_rail = _cw_railhead(supplies, target)
    if cw_rail is not None:
        ports.append(Port("PORT-Cairo", Side.ALLIED, cw_rail.hex, "major",
                          max_eff=10, eff=10,                            # CW base @ Alexandria (55.3 15000 t)
                          **_caps_tonnage(_PORT_TONS["alexandria"]["tons"])))
    return tuple(ports)


# The Race for Tobruk spans March-August 1941 (61.2); the 12-turn clock pairs into the
# six calendar months whose Axis Naval Convoy Levels (56.4) are F,E,D,G,C,E.
_RACE_MONTHS_1941 = ("mar", "apr", "may", "jun", "jul", "aug")
_CONVOY_LEVEL_56_4 = logistics_data.convoy_level_56_4()
_CONVOY_CAP_56_5 = logistics_data.convoy_capacity_56_5()
# [56.22] the Axis Player's tonnage allocation across commodities (a player knob, defaulted
# here); Water is NOT a convoy commodity (56.22) -- it comes from wells (52.7) and rail.
_CONVOY_SPLIT_56_22 = {"FUEL": 0.60, "AMMO": 0.25, "STORES": 0.15}


def _axis_convoy_cargo(turn: int, rng: random.Random) -> dict:
    """[56.4]x[56.5]x[54.5] Axis naval-convoy cargo for `turn`. The month's Convoy Level
    (56.4) sets the 56.5 tonnage = fixed + variable x die (die from the seeded rng, rounded
    UP to the nearest 1000 t); the 56.22 split apportions it across fuel/ammo/stores by
    tonnage; 54.5 crosses each to supply Points. Real-scale, deterministic per seed."""
    month = _RACE_MONTHS_1941[min((turn - 1) // 2, len(_RACE_MONTHS_1941) - 1)]
    cap = _CONVOY_CAP_56_5[_CONVOY_LEVEL_56_4["1941"][month]]
    die = rng.randint(1, 6)
    tonnage = math.ceil((cap["fixed_tons"] + cap["variable_tons_per_die"] * die) / 1000) * 1000
    return {c: tons_to_points(tonnage * frac, c) for c, frac in _CONVOY_SPLIT_56_22.items()}


def _rommel_convoys(supplies, target, max_turns: int, seed: int) -> tuple[Convoy, ...]:
    """The Rommel's Arrival supply SOURCE as a deterministic timetable (56.2: 'reflect
    Axis supplies as they actually occurred'). Three lanes, each landing into an EXISTING
    destination dump (clipped by the 54.12 dump cap then the 55.14 port throttle):

      - SEA-TOBRUK (56.3/30): the Tobruk ferry, every game-turn, feeding AL-Tobruk through
        PORT-Tobruk (61.6 eff 7/7 = full) -- the load-bearing garrison lifeline.
      - CW-RAILHEAD (rule 57): Cairo's rail refills the rear Egyptian dump through the
        full-efficiency CW base; hauling it forward is the CHUNK-4 truck layer.
      - Axis lane "1" (56.4/56.11): the real 56.5 tonnage-by-die faucet, landing at the
        rearmost Axis dump. In this scenario that dump carries scuttled Benghazi (61.6
        eff 0), so it lands NOTHING until Step 5 repoints the lane to a working port --
        the Axis lives off its 61.44 start-line reservoir, the intended desert scarcity.
        No Axis convoy on turn 1 (61.44).

    Destinations are chosen by geography (rearmost Axis dump; easternmost CW dump) so the
    timetable is robust to the OOB's generated dump ids."""
    turns = range(1, max_turns + 1)
    load = _load_cargo()          # one representative real-scale Supply Unit (61.36)

    convoys: list[Convoy] = [
        Convoy(f"ferry-t{t}", Side.ALLIED, t, "SEA-TOBRUK", "AL-Tobruk", dict(load))
        for t in turns]
    railhead = _cw_railhead(supplies, target)
    if railhead is not None:
        convoys += [Convoy(f"rail-t{t}", Side.ALLIED, t, "CW-RAILHEAD", railhead.id, dict(load))
                    for t in turns]
    rear = _axis_rear(supplies, target)
    if rear is not None:
        rng = random.Random(seed)                    # seed-driven 56.5 die (deterministic)
        convoys += [Convoy(f"axis-l1-t{t}", Side.AXIS, t, "1", rear.id, _axis_convoy_cargo(t, rng))
                    for t in range(2, max_turns + 1, 2)]
    return tuple(convoys)


def siege_of_tobruk(seed: int = 1941) -> GameState:
    """The Siege of Tobruk (rule 25.14 / 25.16): Rommel's Arrival with the siege-
    artillery rule LIVE. It is the SAME battle -- identical OOB, placement, supply,
    the 12-turn clock, the garrison morale and the base fort level are all reused
    from rommels_arrival untouched -- but siege_rules is on, so a sustained Axis
    barrage can batter Tobruk's fortifications down one level at a time (the wall the
    intact works present to a close assault comes off turn by turn). This is what
    makes the fortress crackable SOMETIMES rather than never: a strong attacker who
    brings up artillery and ammunition can open the works, then storm them.

    The no-eviction rule (15.82), the clock, the garrison and the base level stay
    faithful and load-bearing. The crack rate is tuned -- deliberately NOT here --
    with engine.BARRAGE_HITS_PER_FORT_LEVEL and the Axis ammo/dump schedule via the
    benchmark harness (design target ~15-35% under strong play)."""
    return replace(rommels_arrival(seed=seed), siege_rules=True)
