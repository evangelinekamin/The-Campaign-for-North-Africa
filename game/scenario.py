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

from . import (calendar, campaign_victory, cna_map, coords, logistics_data, oob,
               wells)
from .events import Phase, Side
from .hexmap import distance, neighbors
from .movement import TerrainMap, edge
from .state import (AirMission, AirWing, Convoy, GameState, InterdictionOrder,
                    Port, StepRecord, SupplyUnit, TruckFormation, Unit, VP)
from .supply import COMMODITIES, _UNLIMITED, tons_to_points
from .terrain import Hexside, Mobility, Terrain

LENGTH = 8
MAX_TURNS = 8

# Initiative (rule 7.14 / 7.15 / 61.5) for the Race for Tobruk. 61.5 fixes Initiative to the
# Axis through GT27 (the first two game-turns of the GT26-start scenario, until=2 on the
# synthetic 1..12 clock), rolling from GT28. The 7.2 Initiative Ratings chart is untranscribed;
# these are a REPRESENTATIVE PROXY (Rommel/DAK a slight edge over the Commonwealth), flagged --
# not transcribed values. Only the ordering they bias is affected, never a rulebook magnitude.
_AXIS_INITIATIVE_UNTIL = 2
_INITIATIVE_RATINGS_PROXY = {"AXIS": 3, "ALLIED": 2}


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
        seed=seed, weather="normal", vp=VP(),
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
        seed=seed, weather="normal", vp=VP(),
        terrain=tmap, control={}, units=units, target_hex=target,
        supplies=supplies, consumed=_zero_consumed(), initial_supply=initial,
        map_sections=frozenset("C"),                     # real Map C (29.1 / 29.7)
        initiative_fixed=Side.AXIS, initiative_fixed_until=_AXIS_INITIATIVE_UNTIL,
        initiative_ratings=dict(_INITIATIVE_RATINGS_PROXY),   # 7.14/61.5 (proxy ratings)
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
    rommel = oob.rommel_entity(sections="ABC")    # rule 31: the leader as an entity, off units[]

    # The rear Axis HARBOUR (Tripoli): a dedicated built-in port dump (56.28) seeded with the
    # 61.44 Tripoli-box stock (fuel 3000 / ammo 1500 / stores 500) and placed one hex behind
    # the rearmost 61.44 FIELD dump. Keeping it SEPARATE from the field dumps is the whole
    # point of Step 5: the harbour is a fixed installation (the port anchors it, and the
    # naval convoy lands its tonnage here), while the field-dump reservoir stays mobile and
    # leapfrogs forward with the army (rule 32.58A). So supply reaches the front two ways --
    # the start reservoir rides the field dumps forward, and the ongoing convoy tonnage must
    # be HAULED off Tripoli by the truck pool (the faithful Tripoli->front bottleneck).
    supplies.append(SupplyUnit("AX-Tripoli", Side.AXIS,
                               _axis_harbour_hex(supplies, target),
                               **{k.lower(): v for k, v in logistics_data.tripoli_builtin_61_44().items()}))

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
                           seed=seed, weather="normal", vp=VP(), terrain=tmap,
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

    # RAIL SEED (54.3) -- FLAGGED, not laid. The Egyptian railhead IS fed (the CW-RAILHEAD
    # convoy lane refills the easternmost CW dump every turn), but the *physical* rail edge-
    # set stays empty: (a) the abstracted ABC corridor carries no transcribed rail line, and
    # the CW dumps are 40+ hexes apart, so any rails would be fabricated geography; and (b)
    # the 54.3 rail HAUL driver was deferred at Step 4 (no engine phase fires RAIL_HAULED),
    # so seeded rails would be inert decoration. The rail machinery stays dormant here and
    # keeps its isolated coverage in tests/test_rail.py; activating it needs the deferred
    # driver, not a scenario seed. TerrainMap.rails therefore remains frozenset().
    max_turns = 12
    convoys = _rommel_convoys(supplies, target, max_turns, seed)
    ports = _rommel_ports(supplies, target)
    trucks = _rommel_trucks(supplies, target)     # Step 5: the inland haulage, now live
    initial = _initial_supply(supplies)
    return GameState(
        turn=1, max_turns=max_turns, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="normal", vp=VP(),
        terrain=tmap, control={}, units=tuple(units), target_hex=target,
        supplies=tuple(supplies), consumed=_zero_consumed(),
        initial_supply=initial, convoys=convoys, ports=ports, trucks=trucks,
        map_sections=frozenset("ABC"),                   # real Maps A/B/C (29.1 / 29.7)
        initiative_fixed=Side.AXIS, initiative_fixed_until=_AXIS_INITIATIVE_UNTIL,
        initiative_ratings=dict(_INITIATIVE_RATINGS_PROXY),   # 7.14/61.5 (proxy ratings)
        rommel=rommel,                                        # rule 31: the Axis leader entity
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


def _axis_harbour_hex(supplies, target):
    """A fresh hex one step BEHIND the rearmost Axis field dump for the Tripoli harbour --
    the rearward neighbour furthest from the objective that no dump already occupies, so the
    port sits on its own hex (distinct from the mobile field dumps, which the bridge relocates
    freely). _connect_pieces + the road-spur step wire it into the corridor's supply net."""
    rear = _axis_rear(supplies, target)
    occupied = {s.hex for s in supplies}
    free = [h for h in neighbors(rear.hex) if h not in occupied]
    return max(free or [rear.hex], key=lambda h: (distance(h, target), h))


def _cw_railhead(supplies, target):
    cw = [s for s in supplies if s.side == Side.ALLIED and s.id != "AL-Tobruk"]
    return max(cw, key=lambda s: (distance(s.hex, target), s.id)) if cw else None


def _rommel_ports(supplies, target) -> tuple[Port, ...]:
    """The scenario's ports and their built-in dumps (56.28), seeded from the real 55.3
    tonnages + the 61.6 scenario Efficiency Levels. Tonnage is the sole 55.14 gate (the
    per-commodity caps are _UNLIMITED). Per 61.6: Tobruk starts at Efficiency 7 of 7 (the
    rulebook seeds 7 verbatim -- above its 55.3 listed max of 5, San Giorgio penalty
    unaccounted; transcribed as stated, not silently reconciled).

    The rear Axis supply port is TRIPOLI (55.3 Efficiency 10, 15000 t/OpStage) -- the real
    main Axis harbour, working at full efficiency. STEP 5 repointed it here from the scuttled
    Benghazi (eff 0, which landed nothing): the historical bottleneck was never the harbour
    but the ~1500 km haul from Tripoli to the front, which the 2nd/3rd-line truck pool
    (_rommel_trucks) must now bridge. The Commonwealth base proxies Alexandria (55.3 15000 t)
    at full efficiency. Tonnages are the real 55.3 chart; the port geography (rearmost Axis
    dump / easternmost CW dump) is the scenario proxy for off-corridor Tripoli/Alexandria."""
    ports = [Port("PORT-Tobruk", Side.ALLIED, target, "major", max_eff=7, eff=7,
                  **_caps_tonnage(_PORT_TONS["tobruk"]["tons"]))]        # 61.6 eff 7; 55.3 1700 t
    axis_rear = _axis_rear(supplies, target)
    if axis_rear is not None:
        ports.append(Port("PORT-Tripoli", Side.AXIS, axis_rear.hex, "major",
                          max_eff=10, eff=10,                            # 55.3 eff 10, working
                          **_caps_tonnage(_PORT_TONS["tripoli"]["tons"])))   # 55.3 15000 t
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
      - CW-RAILHEAD (rule 57): the abstract Commonwealth rail feed to the Egyptian railhead
        (easternmost CW dump), refilling it through the full-efficiency CW base every game-
        turn. The physical 54.3 rail HAUL driver is deferred (see rommels_arrival), so this
        lane IS the rail feed for now; hauling it forward is the truck layer.
      - Axis lane "1" (56.4/56.11): the real 56.5 tonnage-by-die faucet, now landing at the
        rearmost Axis dump through the WORKING PORT-Tripoli (Step 5; 55.3 eff 10, 15000 t).
        The tonnage piles at the rear port and must be HAULED ~75 hexes forward by the
        truck pool -- the historical Tripoli-to-front bottleneck. The Axis still opens on
        its 61.44 start-line reservoir; no Axis convoy on turn 1 (61.44).

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


def _rommel_trucks(supplies, target) -> tuple[TruckFormation, ...]:
    """The Axis 2nd/3rd-line motor-transport pool (rules 53 / 54.2), staged at the rear
    supply port (the AX rear dump, where PORT-Tripoli lands its convoys). This is the
    inland distribution layer that must relay the port's tonnage forward to the dumps the
    front traces to (53.14 relay = the load/move/unload triple). The scripted
    policy.truck_orders shuttles it between Tripoli and the front, each hop burning the
    trucks' OWN cargo fuel (49.18) -- so the further the front, the more of every load the
    convoy burns just moving it, the classic desert supply death-spiral.

    FLAG -- REPRESENTATIVE strength, pending the real rule-61 truck OOB: one heavy and one
    medium formation (54.2 rows), deliberately LEAN. The haulage bottleneck over the
    Tripoli->front distance IS the scarcity; over-provisioning the pool would erase it.
    Sizes here are a plausible-DAK placeholder, not a transcribed chart value."""
    rear = _axis_rear(supplies, target)
    if rear is None:
        return ()
    return (
        TruckFormation("AX-Truck-H", Side.AXIS, rear.hex, "heavy", points=8, line=2),
        TruckFormation("AX-Truck-M", Side.AXIS, rear.hex, "medium", points=6, line=3),
    )


# FLAGGED representative Air-Point weights + bombing cadence for the Tobruk air choke -- NOT
# rulebook magnitudes (the 34.6/59.3 Initial Air Strengths chart is untranscribed, like the
# truck-pool sizes and initiative_ratings). Tuned against measured crack rates in later steps,
# never here: the port cutoff is otherwise near-inevitable, so the tuning direction is to SLOW
# the siege (later start-turn, sparser cadence, a stronger contesting RAF) into a race against
# the 12-turn clock.
_TOBRUK_LW_FIGHTERS = 8              # F: the Axis LAND fighter pool contesting the sky
_TOBRUK_LW_STRIKE = 6               # S: the Axis LAND strike points that batter the harbour
_TOBRUK_DAF_FIGHTERS = 3           # G: the Commonwealth LAND fighter pool (only when raf=True)
_TOBRUK_PORTBOMB_START = 1         # first game-turn the harbour is bombed
_TOBRUK_PORTBOMB_CADENCE = 1       # bomb every N-th turn from the start


def _tobruk_ferry_interdiction(max_turns: int, bomb_points: int = 200
                               ) -> tuple[InterdictionOrder, ...]:
    """The static Axis air-interdiction schedule against the Tobruk sea ferry (rules 41.6 /
    32.7 -- Axis bombing of the Commonwealth Mediterranean run; the historical Luftwaffe
    pressure on the Tobruk Ferry Service). One order per game-turn on lane SEA-TOBRUK, so
    every ferry sails into a CRT strike (41.66). bomb_points is a FLAGGED representative
    weight (the untranscribed per-strike Bomb-Point order-of-battle, like the truck-pool
    sizes) -- 200 lands on the [41.5] 161..200 column (a 5-20% per-turn skim). Static and
    seeded so the crack is CONTINGENT, not inevitable (the live naval seat is Step 6)."""
    return tuple(InterdictionOrder("SEA-TOBRUK", t, bomb_points) for t in range(1, max_turns + 1))


def _axis_land_air(raf: bool, raf_fighters: int = _TOBRUK_DAF_FIGHTERS) -> tuple[AirWing, ...]:
    """The LAND-arena air force for the siege: the Axis Luftwaffe wing that flies the harbour
    bombing (fighters contest the sky, strike batters PORT-Tobruk), plus -- only when `raf` --
    a Commonwealth Desert Air Force fighter wing so _air_superiority rolls a GENUINE per-OpStage
    contest for the LAND sky (a contested/lost sky scales the strike below the gate, delaying the
    port-bomb, never preventing it -- the harbour is monotone-blocked). Air-Point weights are
    FLAGGED proxies; `raf_fighters` is the contesting Commonwealth pool (a stronger RAF wins the
    sky more OpStages, delaying the port cut further). recon=0: this air chokes the lifeline, not
    lifts fog."""
    wings = [AirWing("LW-land", Side.AXIS, "LAND",
                     fighters=_TOBRUK_LW_FIGHTERS, strike=_TOBRUK_LW_STRIKE, recon=0)]
    if raf:
        wings.append(AirWing("DAF-land", Side.ALLIED, "LAND",
                             fighters=raf_fighters, strike=0, recon=0))
    return tuple(wings)


def _tobruk_port_bomb(max_turns: int, start: int = _TOBRUK_PORTBOMB_START,
                      cadence: int = _TOBRUK_PORTBOMB_CADENCE) -> tuple[AirMission, ...]:
    """The static Axis harbour-bombing schedule against PORT-Tobruk (rule 41.39B): one 'port'
    LAND air mission per scheduled game-turn, each knocking the harbour's Efficiency Level down
    one (engine._air_port) -- and because PORT-Tobruk is HARBOUR_BLOCKED (San Giorgio), it never
    regenerates, so the schedule ratchets eff 7->0 and collapses the ~425-Ammo/OpStage landing
    cap that is the garrison's lifeline. `start`/`cadence` are FLAGGED tuning proxies for the
    siege TEMPO (how fast the throat closes against the 12-turn clock)."""
    return tuple(AirMission(Side.AXIS, "port", "PORT-Tobruk", t)
                 for t in range(start, max_turns + 1, cadence))


def siege_of_tobruk(seed: int = 1941, *, port_bomb: bool = False, raf: bool = False,
                    ferry_bomb: int = 200,
                    portbomb_start: int = _TOBRUK_PORTBOMB_START,
                    portbomb_cadence: int = _TOBRUK_PORTBOMB_CADENCE,
                    raf_fighters: int = _TOBRUK_DAF_FIGHTERS) -> GameState:
    """The Siege of Tobruk (rule 25.14 / 25.16): Rommel's Arrival with the siege-
    artillery rule LIVE and a sustained Axis air-interdiction of the Tobruk ferry. It is
    the SAME battle -- identical OOB, placement, base supply, the 12-turn clock, the
    garrison morale and the base fort level are all reused from rommels_arrival untouched --
    but siege_rules is on (so a sustained Axis barrage batters Tobruk's works down one level
    at a time, 25.14) and the SEA-TOBRUK ferry now runs a gauntlet of CRT convoy bombing
    (41.6), throttling the fuel/stores/water the garrison lands each turn.

    MEASURED (see the task report): the interdiction faithfully chokes the lifeline (a
    strong cut removes thousands of supply points over the campaign), but Tobruk capture
    does NOT move off the ~0-3% floor under the scripted policies. Two pre-existing facts
    dominate, neither an interdiction defect: (a) the fortress is essentially never STORMED
    -- the deferred siege-assault path (memory: cna-tobruk-crackability; the no-eviction
    15.82 rule), so the 15.15 dry-stack surrender the ferry-cut aims at is never triggered;
    and (b) the PORT-Tobruk landing throttle (425 Ammo Points/OpStage) already caps the
    ammo refill far below the 1500-Ammo ferry, absorbing any <=50% CRT cut to the AMMO
    lifeline. The ferry-cut is thus real and load-bearing but LATENT here; realizing the
    crack needs the deferred storming AI, out of this step's faithful scope.

    The no-eviction rule (15.82), the clock, the garrison and the base level stay faithful
    and load-bearing. The crack rate is tuned -- deliberately NOT here -- with
    engine.BARRAGE_HITS_PER_FORT_LEVEL and the Axis ammo/dump schedule via the benchmark
    harness (design target ~15-35% under strong play).

    The keyword knobs seed the SECOND throat of the lifeline -- the harbour, not just the
    ferry -- so the crack the ferry-cut only made latent can actually fire. `port_bomb` fields
    the Axis Luftwaffe LAND wing and a per-turn PORT-Tobruk bombing schedule (eff 7->0, no regen
    under HARBOUR_BLOCKED); `raf` adds a contesting Commonwealth fighter wing so winning the LAND
    sky is a genuine contest (the air-superiority gate on _air_port); `ferry_bomb` sets the SEA
    ferry CRT weight. `portbomb_start`/`portbomb_cadence`/`raf_fighters` are the siege-TEMPO
    knobs (push the first bomb later, bomb every N-th turn, field a stronger contesting RAF) that
    slow the harbour cut into a race against the 12-turn clock. DEFAULTS are air-less
    (air=()/air_missions=(), ferry at 200), so the default siege stays byte-identical to the
    pre-choke scenario -- the knobs are FLAGGED tuning proxies, not rulebook magnitudes."""
    base = rommels_arrival(seed=seed)
    air = _axis_land_air(raf, raf_fighters) if port_bomb else ()
    air_missions = (_tobruk_port_bomb(base.max_turns, portbomb_start, portbomb_cadence)
                    if port_bomb else ())
    return replace(base, siege_rules=True, air=air, air_missions=air_missions,
                   interdictions=_tobruk_ferry_interdiction(base.max_turns, ferry_bomb))


# --- the full campaign (rule 64) -----------------------------------------------

_ALEXANDRIA = "E3613"       # the Axis objective (rule 64.7); land-verified on Map E.
_CW_OBJECTIVE = "A4827"     # Benghazi -- the Axis port-of-arrival; the offensive Commonwealth's
                            # westward drive (Operation Compass), the exact mirror of the Axis aim.


# --- C3: the convoy / supply economy (rule 57 / 56.4 / 60.34). Campaign-only: the engine
# faucet (game.engine._naval_convoys) is gated on state.convoys/ports, both defaulting empty
# (state.py), so seeding them here leaves the benchmark scenarios byte-identical -- the same
# opt-in seam rommels_arrival uses. This restores the strategic ASYMMETRY that is the
# campaign's drama: the Commonwealth's inexhaustible Suez base vs the Axis Mediterranean
# convoy that lands in the west and must be hauled to a front hundreds of hexes east. ---
_MON = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_CW_BASE_HEXES = {"Cairo": "E1730", "Alexandria": "E3613"}   # rule 57 / 60.44 unlimited base
_AXIS_PORT_HEX = "A4827"                                     # Benghazi -- forward Axis harbour (60.34)
_CW_BASE_SEED = _UNLIMITED // 8    # a reservoir no 111-turn draw can exhaust (MAJOR_CITY = unlimited cap)


def _campaign_cw_base() -> list[SupplyUnit]:
    """Rule 57 / 60.44: the Commonwealth's inexhaustible Suez base -- a dump on Cairo and
    Alexandria, each seeded beyond any 111-turn draw and standing on a MAJOR_CITY hex (so
    supply.dump_capacity is _UNLIMITED and it neither overflows nor empties). 'If he wants
    something, it is in Cairo' (57.0): the Commonwealth can always fall back and refit."""
    return [SupplyUnit(f"AL-{name}", Side.ALLIED, coords.to_axial(coords.parse(lbl)),
                       ammo=_CW_BASE_SEED, fuel=_CW_BASE_SEED,
                       stores=_CW_BASE_SEED, water=_CW_BASE_SEED, base=True)
            for name, lbl in _CW_BASE_HEXES.items()]


def _campaign_axis_base() -> SupplyUnit:
    """The Axis port-of-arrival dump at Benghazi (A4827), where the Mediterranean convoys land
    (rule 60.34). Seeded with its 60.34 start-line stock -- the reservoir the coastal truck
    relay (game.campaign_policy.campaign_truck_orders) lifts forward leg by leg along the
    staging dumps, and the monthly convoys top up. NOT a rule-57 base (base=False): a forward
    field harbour dump evaporates like any other (49.3)."""
    return SupplyUnit("AX-Benghazi", Side.AXIS, coords.to_axial(coords.parse(_AXIS_PORT_HEX)),
                      ammo=100, fuel=250, stores=100, water=0)


def _campaign_staging_dumps() -> list[SupplyUnit]:
    """The historical Axis coastal staging dumps (rule 60.34), Axis-held at Game-Turn 1 -- the
    intermediate depots that let the lean Benghazi truck pool relay its landed tonnage forward
    LEG BY LEG (each hop <= one 30-CP truck move, rule 53.22) instead of in one impossible ~75-
    hex jump to the front. Three are pre-stocked from the 60.34 chart (Tobruk, Bardia, Derna); the
    rest are empty waypoints spaced along the Via Balbia -- Benghazi -> W1 -> W2 -> Derna -> W3 ->
    Tobruk -> Bardia -- each a forward dump campaign_truck_orders fills from the one behind it.

    base=False deliberately: a field dump evaporates (49.3) and is NOT a rule-57 strategic base
    -- exempting it would both mislabel the chain and freeze its stock. Labelled hexes go through
    coords; the four probed waypoints are passed as raw axial (no rulebook label)."""
    def ax(lbl: str):
        return coords.to_axial(coords.parse(lbl))
    return [
        SupplyUnit("AX-Stage-Tobruk", Side.AXIS, ax("C4807"), ammo=200, fuel=2000, stores=500, water=0),
        SupplyUnit("AX-Stage-Bardia", Side.AXIS, ax("C4321"), ammo=100, fuel=1000, stores=200, water=0),
        SupplyUnit("AX-Stage-W1", Side.AXIS, (5, 36), ammo=0, fuel=0, stores=0, water=0),
        SupplyUnit("AX-Stage-W2", Side.AXIS, (4, 45), ammo=0, fuel=0, stores=0, water=0),
        SupplyUnit("AX-Stage-Derna", Side.AXIS, ax("B5925"), ammo=0, fuel=250, stores=50, water=0),
        SupplyUnit("AX-Stage-W3", Side.AXIS, (15, 63), ammo=0, fuel=0, stores=0, water=0),
    ]


def _campaign_axis_cargo(gt: int, rng: random.Random) -> dict | None:
    """[56.4]x[56.5]x[54.5] Axis naval-convoy cargo for Game-Turn `gt`, calendar-driven across
    the whole GT1..111 span (calendar.gt_to_month) -- the generalization of _axis_convoy_cargo,
    which hardcodes the six Race-for-Tobruk months. The month's 56.4 Convoy Level sets the 56.5
    tonnage (fixed + variable x die), the 56.22 split apportions it across fuel/ammo/stores, and
    54.5 crosses each to supply Points. Returns None for a month the 56.4 chart lists no convoy
    (a '-' -- e.g. before September 1940, when the desert lanes had not yet opened)."""
    year, month = calendar.gt_to_month(gt)
    level = _CONVOY_LEVEL_56_4[str(year)][_MON[month - 1]]
    if level == "-":
        return None
    cap = _CONVOY_CAP_56_5[level]
    die = rng.randint(1, 6)
    tonnage = math.ceil((cap["fixed_tons"] + cap["variable_tons_per_die"] * die) / 1000) * 1000
    return {c: tons_to_points(tonnage * frac, c) for c, frac in _CONVOY_SPLIT_56_22.items()}


_CW_RAILHEAD = "D3714"                 # Mersa Matruh -- the RR terminus (rule 60.7)

# The Commonwealth supply SPINE, west (the front) to east (the Delta) -- the twin of the Axis
# _campaign_staging_dumps, and the reason the Western Desert Force can attack at all.
#   * WEST of the railhead: the Operation Compass FIELD SUPPLY DEPOTS (60.34). The Western Desert
#     Force did not attack out of Egypt on its trace range -- it spent weeks lorrying dumps forward
#     into the desert first, and then attacked out of THEM.
#   * EAST of it: the Western Desert Railway stations. Not depots to haul into -- the line the
#     RAILHEAD RETRACTS along when the enemy takes Mersa Matruh (54.3, _campaign_cw_rail_line).
_CW_FIELD_DEPOTS = (("Sollum", "C4021"), ("Barrani", "C4131"))                    # 60.34, forward
_CW_RAIL_STATIONS = (("Matruh", _CW_RAILHEAD), ("ElDaba", "D3329"), ("ElHamman", "E3007"))   # 54.3


def _campaign_cw_depots() -> list[SupplyUnit]:
    """The seeded Commonwealth spine (see _CW_FIELD_DEPOTS / _CW_RAIL_STATIONS above). Each leg is
    within ONE 30-CP truck convoy hop of the one behind it (53.22), VERIFIED against
    supply.reachable_truck_moves the way the Axis chain was: Matruh -> Sidi Barrani costs 29 CP and
    Sidi Barrani -> Sollum 22, so no waypoint hex is needed. (What blocks the second leg on
    Game-Turn 1 is the Italian 10th Army standing on it -- which is the point of the offensive, not
    a gap in the chain.)

    EMPTY, and base=False: a Field Supply Depot is hauled into, not pre-filled -- the lorries put
    it there -- and it evaporates like any field dump (49.3), being no rule-57 strategic base."""
    return [SupplyUnit(f"AL-Stage-{name}", Side.ALLIED, coords.to_axial(coords.parse(lbl)),
                       ammo=0, fuel=0, stores=0, water=0)
            for name, lbl in _CW_FIELD_DEPOTS + _CW_RAIL_STATIONS]


def _campaign_cw_railhead(supplies):
    """The Mersa Matruh railhead dump (rule 60.7: "the RR runs to Mersa Matruh and ends
    there"). The Commonwealth FORWARD dump (not the bottomless Cairo/Alexandria base) nearest
    D3714 -- the rail lane refills it every turn so the Commonwealth can project supply WEST of
    its rear base (its cpa/2 trace reaches only ~6-12 hexes, far short of the front), the faucet
    that makes Operation Compass sustainable. With the spine seeded that is AL-Stage-Matruh, the
    depot standing ON Mersa Matruh -- so the rail lane, PORT-Matruh's 55.3 throttle and the lorry
    pool all key off the one railhead, instead of off whichever field dump happened to lie nearest
    it (which is how a passing Italian truck came to switch the Commonwealth's faucet off)."""
    rh = coords.to_axial(coords.parse(_CW_RAILHEAD))
    fwd = [s for s in supplies if s.side == Side.ALLIED and not s.base and not s.is_dummy]
    return min(fwd, key=lambda s: (distance(s.hex, rh), s.id)) if fwd else None


def _campaign_cw_rail_line(supplies) -> tuple[str, ...]:
    """The Commonwealth railway (rule 54.3) as the engine needs to see it: the ordered LINE of
    depots it feeds, forward (the Mersa Matruh terminus, 60.7) to rear (the inexhaustible Delta
    base, 57). game.engine._convoy_dest lands each turn's cargo in the first station on it the
    enemy does not control.

    THE RAILHEAD IS NOT A PLACE -- it is the furthest station of the operating railway the
    Commonwealth still holds. Bound to one hex it dies to the first enemy vehicle that drives
    across it: measured, an Italian vehicle stepped beside Mersa Matruh on Game-Turn 2 and the
    56.15 gate then cancelled 55 STRAIGHT rail convoys -- GT3 to GT57, the whole of Operation
    Compass -- on a railhead the Commonwealth had never lost. As a line it retracts instead."""
    railhead = _campaign_cw_railhead(supplies)
    if railhead is None:
        return ()
    have = {s.id for s in supplies}
    rear = ("AL-Stage-ElDaba", "AL-Stage-ElHamman", "AL-Alexandria")   # 54.3 stations, then the base
    return (railhead.id, *(sid for sid in rear if sid in have and sid != railhead.id))


def _campaign_cw_trucks(supplies) -> tuple[TruckFormation, ...]:
    """The Commonwealth 2nd/3rd-line motor-transport pool (rules 53 / 54.2 / 60.33), staged on the
    Mersa Matruh railhead the rail lane feeds. Without it the Commonwealth has NO way to project
    supply west of its railhead -- its trace reaches ~6-12 hexes -- so Operation Compass and Crusader
    strand every unit they send toward Benghazi (measured: zero supplied Commonwealth units at GT111).
    The Western Desert Force ran on lorries; this is the pool that hauled it to El Agheila."""
    railhead = _campaign_cw_railhead(supplies)
    if railhead is None:
        return ()
    return (
        TruckFormation("AL-Truck-H", Side.ALLIED, railhead.hex, "heavy", points=8, line=3),
        TruckFormation("AL-Truck-M", Side.ALLIED, railhead.hex, "medium", points=8, line=3),
    )


def _campaign_axis_trucks(supplies, target) -> tuple[TruckFormation, ...]:
    """The Axis 2nd/3rd-line motor-transport pool (rules 53 / 54.2 / 60.33), staged at the
    Benghazi port-of-arrival where the Mediterranean convoys land -- the Quartermaster's
    forward-haul lever, a lean ~1/6 slice of the 60.33 Tripoli row (heavy + medium).
    LIMITATION (measured): the September-1940 field dumps sit ~48-76 hexes east of Benghazi,
    far beyond the pool's ~30-CP single-hop reach (53.22), so the scripted single-port relay
    (policy.truck_orders) bridges NOTHING -- faithful to the historical Tripoli-to-front wall,
    but it means effective resupply needs a MANAGED multi-hop coastal relay (intermediate
    staging dumps hauled leg by leg), which a Quartermaster agent can build but the scripted
    reflex does not. The DAK's own trucks ([4.43b]) are deferred (state.trucks is static at
    construction; no truck-arrival scheduler yet)."""
    rear = _axis_rear(supplies, target)
    if rear is None:
        return ()
    return (
        TruckFormation("AX-Truck-H", Side.AXIS, rear.hex, "heavy", points=8, line=3),
        TruckFormation("AX-Truck-M", Side.AXIS, rear.hex, "medium", points=8, line=3),
    )


def _campaign_convoys(supplies, target, max_turns: int, seed: int) -> tuple[Convoy, ...]:
    """The supply source timetables. AXIS: the Mediterranean convoy (56.2/56.4), one delivery a
    month landing at Benghazi through PORT-Benghazi's 55.14 throttle -- the tonnage piles at the
    rear and is hauled forward by the lean truck pool (_campaign_axis_trucks), which culminates
    as the front outruns it. COMMONWEALTH: the rail lane (rule 57 / 60.7), refilling the Mersa
    Matruh railhead every turn so the Suez base's supply actually reaches a forward dump the
    front can trace to -- without it the inexhaustible base is stranded 34+ hexes behind the
    railhead and no westward counterattack can be sustained. The Cairo/Alexandria base itself is
    seeded inexhaustible (_campaign_cw_base) and needs no lane."""
    convoys = []
    railhead = _campaign_cw_railhead(supplies)
    if railhead is not None:
        load = _load_cargo()                           # rule 57 rail feed to the Egyptian railhead
        line = _campaign_cw_rail_line(supplies)        # 54.3/60.7: the railhead RETRACTS, it never dies
        convoys += [Convoy(f"cw-rail-t{gt}", Side.ALLIED, gt, "CW-RAILHEAD", railhead.id,
                           dict(load), retarget=line)
                    for gt in range(1, max_turns + 1)]
    # THE TOBRUK SEA LIFELINE, BOTH HALVES (rules 30 / 56.3 / 56.11) -- ONE harbour, TWO lanes, and
    # rule 56.15 hands it from one to the other the Game-Turn the city changes hands.
    #
    #   * SEA-TOBRUK -- the Commonwealth ferry into the AL-Tobruk garrison dump. The historical
    #     Tobruk Ferry Service; it sails only while the Commonwealth holds the fortress.
    #   * "6" -- the AXIS lane, Italy -> Tobruk (the 56.18 Convoy Air Distance chart names the six
    #     Axis lanes: 1 Sicily->Bizerta, 2 Sicily->Tripoli, 3 Italy->Benghazi, 4 Greece->Benghazi,
    #     5 Greece->Tobruk, 6 Italy->Tobruk). THE RULEBOOK GIVES THE AXIS TWO CONVOY LANES TO
    #     TOBRUK and the campaign sailed neither: the Axis has held Tobruk since Game-Turn 1 --
    #     it was an ITALIAN port, and Italy supplied its army through it -- yet its only supply
    #     forward of Benghazi was a sixty-hex truck haul. Measured, that is why its 200 Victory
    #     Points were one hex deep and a coin-flip: cut the land chain (take Benghazi and the
    #     56.15 gate kills the Mediterranean convoy for the rest of the war) and the Tobruk
    #     garrison starves to a 15.15 dry-ammunition surrender. Fed by sea it is a FORTRESS,
    #     which is what it historically was -- and the besieger's job becomes what it historically
    #     was too: CUT THE SEA LANE (_campaign_tobruk_axis_interdiction).
    #
    # It lands in AX-Stage-Tobruk, the 60.34 staging dump standing ON the city, so the garrison
    # traces to it at distance 0 -- the exact mirror of AL-Tobruk under the ferry. Neither lane is
    # a free faucet: engine._naval_convoys throttles both through the ONE 55.3 harbour (1700 t,
    # eff 5 -> 425 Ammunition Points/OpStage; see _campaign_ports), and 56.15 cancels whichever of
    # them is sailing into a city the enemy now controls. They hand off automatically, in both
    # directions, for as many times as the fortress changes hands.
    convoys += [Convoy(f"tobruk-ferry-t{gt}", Side.ALLIED, gt, "SEA-TOBRUK", "AL-Tobruk", _load_cargo())
                for gt in range(1, max_turns + 1)]
    convoys += [Convoy(f"tobruk-axis-t{gt}", Side.AXIS, gt, _AXIS_TOBRUK_LANE, "AX-Stage-Tobruk",
                       _load_cargo())
                for gt in range(1, max_turns + 1)]
    rear = _axis_rear(supplies, target)
    if rear is not None:
        rng = random.Random(seed)
        for gt in range(1, max_turns + 1):
            if (gt - 1) % calendar.GT_PER_MONTH != 0:  # compute the month's cargo on its first Game-Turn
                continue
            month_cargo = _campaign_axis_cargo(gt, rng)
            if month_cargo is None:
                continue
            # Quarter the month's 56.5 tonnage across its Game-Turns (56.2 "as they actually
            # occurred"): the chart monthly total is preserved (remainder to the first week), but
            # split so each weekly convoy lands UNDER the 55.14 port cap instead of one clipped
            # surge -- and so Malta interdicts a convoy every turn, not once a month.
            per = {c: v // calendar.GT_PER_MONTH for c, v in month_cargo.items()}
            rem = {c: v - per[c] * calendar.GT_PER_MONTH for c, v in month_cargo.items()}
            for i in range(calendar.GT_PER_MONTH):
                wk = gt + i
                if wk > max_turns:
                    break
                cargo = {c: per[c] + (rem[c] if i == 0 else 0) for c in month_cargo}
                convoys.append(Convoy(f"axis-conv-t{wk}", Side.AXIS, wk, "2", rear.id, cargo))  # 60.37 lane 2
    return tuple(convoys)


def _campaign_ports(supplies, target) -> tuple[Port, ...]:
    """The ports of arrival (55.3). AXIS: Benghazi, the forward Mediterranean harbour the
    convoys land at, full efficiency (55.14 throttles by efficiency; the campaign's bottleneck
    is the port-to-front haul, not the harbour). COMMONWEALTH: Mersa Matruh, the railhead the
    rail lane feeds (rule 60.7). The bottomless Cairo/Alexandria MAJOR_CITY base needs no port.

    AND TOBRUK -- which is A HARBOUR, NOT A POSSESSION. There is ONE Tobruk in the 55.3 chart
    (1700 t, Efficiency Level 5, "starts below eff 5 -- San Giorgio partially blocks harbour") and
    ONE Port object here, because that is how the engine already reads a port: GameState.port_at is
    keyed by HEX, engine._naval_convoys throttles whatever lands there with no side test at all, and
    rule 56.15 gates the sailing on CONTROL of the destination hex. So the harbour serves whoever
    holds the city -- the Italians and then the Panzerarmee until Compass/Crusader takes it, the
    Commonwealth afterwards -- and a second, duplicate Port on the same hex would only make port_at
    ambiguous. It is flagged with the side that HOLDS Tobruk at Game-Turn 1 (the Axis -- see
    _CAMPAIGN_CONTROL: it was an Italian port and Italy supplied its army through it), which is what
    engine._air_port reads to decide whose harbour may be bombed.

    Kept under the id PORT-Tobruk so the San Giorgio block already modelled in the engine
    (HARBOUR_BLOCKED: no 55.18 regeneration, ever) keeps applying -- the scuttled cruiser does not
    care who owns the quay. The 1700-t rating is the chart's; at eff 5/5 it crosses (54.5) to a
    landing ceiling of 425 AMMUNITION Points per Operations Stage, which is the real gate on either
    side's Tobruk lifeline."""
    ports = []
    rear = _axis_rear(supplies, target)
    if rear is not None:
        tons = _PORT_TONS.get("benghazi", _PORT_TONS["tripoli"])["tons"]
        ports.append(Port("PORT-Benghazi", Side.AXIS, rear.hex, "major", max_eff=10, eff=10,
                          **_caps_tonnage(tons)))
    railhead = _campaign_cw_railhead(supplies)
    if railhead is not None:
        tons = _PORT_TONS.get("mersa_matruh", _PORT_TONS["tripoli"])["tons"]   # 55.3 railhead tonnage
        ports.append(Port("PORT-Matruh", Side.ALLIED, railhead.hex, "major", max_eff=10, eff=10,
                          **_caps_tonnage(tons)))
    ports.append(Port("PORT-Tobruk", Side.AXIS, coords.to_axial(coords.parse(_TOBRUK)), "major",
                      max_eff=5, eff=5, **_caps_tonnage(_PORT_TONS["tobruk"]["tons"])))
    return tuple(ports)


def _malta_bomb_points(gt: int) -> int:
    """Historical Malta pressure on the Axis convoy, mapped to 41.66 CRT Bomb-Point columns (rule
    44 is untranscribed -- a FLAGGED proxy, like the _TOBRUK_* weights): rising through 1941 to the
    Force-K peak (Nov-Dec 1941), collapsing to zero under the Jan-Apr 1942 Luftwaffe blitz on the
    island, then reviving as the RAF returns. A primary calibration lever for the Axis faucet."""
    year, month = calendar.gt_to_month(gt)
    if year <= 1940:
        return 100
    if year == 1941:
        if month <= 6:
            return 200
        if month <= 10:
            return 300
        return 500                       # Nov-Dec 1941: Force K at its peak
    if month <= 4:
        return 0                          # Jan-Apr 1942: the Luftwaffe blitz suppresses Malta
    if month <= 7:
        return 150                        # May-Jul 1942
    return 400                            # Aug-Dec 1942: the revival


def _campaign_malta_interdiction(max_turns: int) -> tuple[InterdictionOrder, ...]:
    """Rule 44 (Malta) abstracted as a Commonwealth interdiction of the Axis Mediterranean convoy
    lane (60.37 lane '2') -- the twin of the Tobruk-ferry interdiction. Each Game-Turn's convoy is
    under _malta_bomb_points(gt) of 41.66 CRT bombing, skimming a tens-of-percent of its cargo
    before it lands at Benghazi (41.67), leaving a smaller SUPPLY_ARRIVED beside a CONVOY_INTERDICTED
    marker. The counterweight -- Malta's strangling of the sea lane that kept the Panzerarmee short
    of fuel. Turns Malta is suppressed (bomb_points 0) seed no order and draw no dice."""
    return tuple(InterdictionOrder("2", t, _malta_bomb_points(t))
                 for t in range(1, max_turns + 1) if _malta_bomb_points(t) > 0)


_TOBRUK = "C4807"    # the fortress (a 64.73 victory hex); the sea lifeline that lets a siege hold
# [56.18] the Axis naval-convoy lane Italy -> Tobruk. The Convoy Air Distance chart names all six
# (1 Sicily->Bizerta, 2 Sicily->Tripoli, 3 Italy->Benghazi, 4 Greece->Benghazi, 5 Greece->Tobruk,
# 6 Italy->Tobruk), so the Axis run into the harbour it holds is the rulebook's own lane, not an
# invented one. (Benghazi's lane is labelled "2" above -- a pre-existing mislabel against this
# chart, which reads 3/4 for Benghazi. Left alone: the label is the Malta interdiction's key.)
_AXIS_TOBRUK_LANE = "6"
# Historically-correct September-1940 ownership. The 56.15 gate cancels a convoy whose destination
# hex is ENEMY-controlled, but control_of defaults NEUTRAL and _naval_convoys runs before the first
# _record_control -- so without this the GT1 Tobruk ferry would land inside Italian-held Tobruk.
# Once CW combat units occupy Tobruk (Compass), _record_control flips it and the ferry starts
# landing: self-correcting under any unfolding, with CONVOY_CANCELLED markers while the Axis holds it.
_CAMPAIGN_CONTROL = {"C4807": Side.AXIS, "C4321": Side.AXIS, "A4827": Side.AXIS,        # Cyrenaican ports
                     "D3714": Side.ALLIED, "E3613": Side.ALLIED, "E1730": Side.ALLIED}  # Egyptian rear


def _campaign_initial_control() -> dict:
    """Seed the Sep-1940 city ownership (rule 64.2) so the 56.15 convoy gate reads correctly from
    Game-Turn 1 -- the Axis Cyrenaican harbours vs the Commonwealth's Egyptian base and railhead."""
    return {coords.to_axial(coords.parse(lbl)): side for lbl, side in _CAMPAIGN_CONTROL.items()}


def _campaign_tobruk_dump() -> SupplyUnit:
    """Rule 30 / 56.3: the Commonwealth's Tobruk garrison dump, EMPTY at GT1 (the Axis holds Tobruk
    in September 1940). It fills only from the SEA-TOBRUK ferry once the Commonwealth takes the
    fortress (Compass); the garrison then traces to it at distance 0 -- the lifeline that lets a
    besieged Tobruk hold on Close-Assault ammunition instead of starving out (15.15), as it
    historically did. On the C4807 MAJOR_CITY hex, so its 54.12 dump capacity is unlimited."""
    return SupplyUnit("AL-Tobruk", Side.ALLIED, coords.to_axial(coords.parse(_TOBRUK)),
                      ammo=0, fuel=0, stores=0, water=0)


def _campaign_tobruk_ferry_interdiction(max_turns: int, bomb_points: int = 200
                                        ) -> tuple[InterdictionOrder, ...]:
    """The Axis air-interdiction of the Tobruk sea ferry (rules 41.6 / 30) -- the CUTTABLE lane that
    makes a siege winnable the FAITHFUL way (cut the lifeline) rather than impossible. Runs from
    GT20, when the DAK and its Luftwaffe arrive within reach of the ferry; a cancelled ferry (while
    the Axis holds Tobruk) skips interdiction entirely, and an unmatched order draws no dice."""
    return tuple(InterdictionOrder("SEA-TOBRUK", t, bomb_points) for t in range(20, max_turns + 1))


def _campaign_tobruk_axis_interdiction(max_turns: int, bomb_points: int = 200
                                       ) -> tuple[InterdictionOrder, ...]:
    """THE MIRROR: the COMMONWEALTH's interdiction of the Axis Tobruk run (rules 41.6 / 30) -- the
    Mediterranean Fleet out of Alexandria and the Desert Air Force over the Gulf of Bomba, which is
    what made the Tobruk run murderous for the Axis in every year of this war. Without it the sea
    lifeline above would make the fortress INVULNERABLE: rule 15.82 grants Tobruk no eviction, so it
    falls only to a 15.15 dry-ammunition surrender, and a garrison fed by an uncontested sea lane
    never goes dry. A besieger has to be able to fight the lane.

    The exact twin of _campaign_tobruk_ferry_interdiction, at the same FLAGGED 200 Bomb-Point weight
    (the [41.5] 161..200 column, a 5-20% per-turn skim) -- no new magnitude on either side of the
    duel. It runs from Game-Turn 1, where the ferry's Axis interdiction runs from GT20, and the
    difference is not a thumb on the scale: the Luftwaffe has to ARRIVE (it reaches the theatre with
    the DAK at GT20), while the Mediterranean Fleet and the RAF are already at Alexandria in
    September 1940. A cancelled convoy (the Commonwealth holding Tobruk) skips interdiction entirely,
    and an unmatched order draws no dice -- so the schedule is inert the moment the lane changes
    hands, and the ferry's own gauntlet takes over."""
    return tuple(InterdictionOrder(_AXIS_TOBRUK_LANE, t, bomb_points)
                 for t in range(1, max_turns + 1))


def campaign(seed: int = 1941, *, max_turns: int | None = None) -> GameState:
    """The full Campaign for North Africa, walking skeleton (rule 64). One board-global
    A-E map, Game-Turn 1 (September 1940, rule 64.2) through Game-Turn 111 -- the whole
    theatre and the whole clock. Its job is to prove the campaign MACHINERY runs end to
    end: the 111-turn x 3-OpStage clock, the eastern geography (Maps D/E), the calendar
    (season_offset so a September start reads fall), and the pluggable victory seam. The
    real September-1940 armies are here (C2) and the full convoy/supply economy (C3): the
    Commonwealth's inexhaustible Suez base + rail-fed Mersa Matruh railhead vs the Axis
    Mediterranean convoy hauled forward from Benghazi by a lean truck pool. Commonwealth
    offensive agency and balance (C4) land next. The objective is Alexandria (E3613), far
    to the east -- the historical Axis goal.

    Victory is the faithful campaign spec (rule 64.7): the Axis wins by taking Alexandria
    and Cairo or by out-pointing the Commonwealth on the 64.73 geographic Victory-Point
    table graded by 64.76, else annihilation. `max_turns` truncates the run (default the
    full GT111) -- a shorter slice for fast tests or a single-season study."""
    tmap, _ = cna_map.load_sections("ABCDE")
    target = coords.to_axial(coords.parse(_ALEXANDRIA))
    max_turns = max_turns or calendar.FINAL_GT
    # C2: the real September-1940 order of battle -- the Italian 10th Army (extraction +
    # rule-60.31 gap-fill) vs the Western Desert Force -- with the historical reinforcement
    # flow (rule 20 / [4.43b]/[4.43a]): Rommel and the DAK arrive from Tripoli from GT20, the
    # 8th Army builds up from Cairo, across the whole GT1..111 span.
    units, oob_supplies = oob.build(oob_file="oob_italian.json", extra_file="oob_campaign_extra.json",
                                    sections="ABCDE", reinforcements_file="reinforcements_campaign.json")
    # C3: the supply economy -- the Commonwealth's inexhaustible Suez base (Cairo/Alexandria),
    # the Axis port-of-arrival dump (Benghazi) the Mediterranean convoys land at, and the
    # historical coastal staging dumps (60.34) the campaign truck relay hauls forward along.
    # BOTH armies get a spine: the Axis one runs east from Benghazi, the Commonwealth one west
    # from the rail-fed Mersa Matruh railhead (60.7) to the Compass Field Supply Depots. Without
    # its own, the Western Desert Force cannot sustain an offensive one hex past the wire.
    dumps = (tuple(oob_supplies) + tuple(_campaign_cw_base())
             + (_campaign_axis_base(), _campaign_tobruk_dump())
             + tuple(_campaign_staging_dumps()) + tuple(_campaign_cw_depots()))
    # C5: THE WELLS (rules 52.1-52.3) -- the water SOURCES. Water is found in wells and only
    # wells (52.11), so without these the armies drink from nothing: the demand side (52.4) and
    # the 52.53 attrition were both live while total Axis water income across the whole campaign
    # was ZERO. See game.wells for the model and its flagged proxies. The 60.34 dump chart is the
    # tell: its Tobruk/Bardia/Benghazi/Derna dumps carry NO Water Points at all -- because those
    # cities have wells -- while the two free-placed desert dumps carry 200 each.
    water_sources = wells.wells()

    # A hex a piece stands on is land (coastal ports colour-sample as sea); add + connect,
    # exactly as the corridor scenarios do.
    terrain = dict(tmap.terrain)
    for piece in (*units, *dumps, *water_sources):
        terrain.setdefault(piece.hex, Terrain.CLEAR)
    _connect_pieces(terrain, [p.hex for p in (*units, *dumps, *water_sources)])
    forts = _apply_major_cities(terrain)
    for lbl in _CW_BASE_HEXES.values():              # rule 57: the CW base stands on MAJOR_CITY hexes
        terrain[coords.to_axial(coords.parse(lbl))] = Terrain.MAJOR_CITY
    # Benghazi is a city: stamp its terrain MAJOR_CITY (unlimited 54.12 dump capacity), so the Axis
    # port-of-arrival dump no longer clips the convoy to a 5000-fuel Other-Terrain ceiling and the
    # designed 55.3 port tonnage becomes the sole gate. Terrain only -- NOT added to _MAJOR_CITIES,
    # so no 15.82 no-eviction fort is granted at the Axis rear.
    terrain[coords.to_axial(coords.parse(_AXIS_PORT_HEX))] = Terrain.MAJOR_CITY
    tmap = replace(tmap, terrain=terrain, fortifications=forts)

    # The Commonwealth pipeline (52.22): laid over the FINAL land map, so the corridor walks real
    # hexes and invents no terrain. Commonwealth-only -- the Axis may not use the defunct
    # Barce-Benghazi railroad (52.22).
    water_sources += wells.pipeline(tmap.terrain)

    # The wells go in the supplies tuple LAST, and the convoy/port/truck geography below is
    # derived from `dumps` (the armies' depots) ALONE. A well is geography, not a depot: it is
    # not a port of arrival, no convoy lands in it, and no truck reloads from it. Feeding the
    # wells to _axis_rear would hand "the rearmost Axis dump" -- the Benghazi harbour the whole
    # Mediterranean convoy lands at -- to the well out at Jalo oasis. Order matters for the same
    # reason: the policies' co-located-dump scans take the FIRST dump on a hex, and every one of
    # Benghazi/Tobruk/Bardia/Derna/Cairo/Alexandria carries both a depot and a well.
    supplies = dumps + water_sources

    return GameState(
        turn=1, max_turns=max_turns, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="normal", vp=VP(),
        terrain=tmap, control=_campaign_initial_control(), units=tuple(units), target_hex=target,
        allied_objective=coords.to_axial(coords.parse(_CW_OBJECTIVE)),   # offensive CW drives west (Compass)
        supplies=supplies, consumed=_zero_consumed(),
        initial_supply=_initial_supply(supplies),
        map_sections=frozenset("ABCDE"),
        season_offset=calendar.CAMPAIGN_SEASON_OFFSET,   # GT1 = September 1940 (fall)
        victory=campaign_victory.CampaignVictory(),      # rule 64.7 (see game.campaign_victory)
        convoys=_campaign_convoys(dumps, target, max_turns, seed),      # C3: Axis Med + CW rail (56.4/60.7)
        ports=_campaign_ports(dumps, target),                           # C3: PORT-Benghazi + PORT-Matruh
        trucks=(_campaign_axis_trucks(dumps, target)                    # C3-2: the Benghazi->front haul (53/60.33)
                + _campaign_cw_trucks(dumps)),                          # and the CW railhead->west haul (60.33)
        interdictions=(_campaign_malta_interdiction(max_turns)             # C4: Malta throttles the Axis Med convoy (rule 44)
                       + _campaign_tobruk_ferry_interdiction(max_turns)    # + BOTH halves of the Tobruk sea duel
                       + _campaign_tobruk_axis_interdiction(max_turns)),   #   (30/41.6): each side can fight the other's lane
    )
