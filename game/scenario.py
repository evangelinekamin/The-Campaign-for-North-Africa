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

from . import (calendar, campaign_victory, cna_map, coords, logistics_data, oob, villages,
               wells)
from .events import Phase, Side
from .hexmap import Coord, distance, neighbors
from .movement import TerrainMap, edge
from .state import (AirMission, AirWing, Convoy, GameState, InterdictionOrder,
                    Port, RommelArrival, StepRecord, SupplyUnit, TruckFormation, Unit, VP)
from .supply import (COMMODITIES, TONS_PER_POINT, _UNLIMITED, port_tonnage_budget,
                     tons_to_points)
from .terrain import Hexside, Mobility, Terrain

LENGTH = 8
MAX_TURNS = 8

# Initiative (rule 7.14 / 7.15 / 61.5) for the Race for Tobruk. 61.5 fixes Initiative to the
# Axis through GT27 (the first two game-turns of the GT26-start scenario, until=2 on the
# synthetic 1..12 clock), rolling from GT28. The [7.2] chart IS transcribed (game.initiative), but
# it keys on the real Game-Turn (the Commonwealth band) and on-map presence (the Axis row); the
# Desert Fox benchmarks run a synthetic 1..12 clock, not the real GT26-37, so the date bands do not
# describe them. They keep this REPRESENTATIVE PROXY (Rommel/DAK a slight edge over the
# Commonwealth), flagged -- only the ordering it biases is affected, never a rulebook magnitude. The
# full campaign, on the real clock, opts into the chart instead (initiative_chart=True).
_AXIS_INITIATIVE_UNTIL = 2
_INITIATIVE_RATINGS_PROXY = {"AXIS": 3, "ALLIED": 2}


def _zero_consumed() -> dict:
    return {c: 0 for c in COMMODITIES}


def _initial_supply(supplies, units=()) -> dict:
    """Total of each commodity ever introduced at t0 (54.5 conservation base): the dumps' pools PLUS
    every unit's own supply pool (the 49.14 fuel tanks + 53.11 first-line loads). Units carry supply
    from t0 -- dormant rule-20 reinforcements included, since they sit in state.units from the start
    -- so their supply belongs in the base and their arrival mints nothing. The faucet
    (SUPPLY_ARRIVED) raises these at runtime; game.invariants checks on_hand + consumed == initial
    per commodity, where on_hand sums dumps + trucks + units."""
    return {c: (sum(getattr(s, c.lower()) for s in supplies)
                + sum(getattr(u, c.lower()) for u in units)) for c in COMMODITIES}

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
    initial = _initial_supply(supplies, units)

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
    initial = _initial_supply(supplies, units)
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
    # [36.0]/[36.17] The AIR FACILITIES the OOB carries on this corridor, and the supply dumps they
    # ARE. [61.36]/[61.44] chart the Desert Fox air-supply allotment (CW 250 Ammo / 180 Fuel / 50
    # Stores; Axis 50/50); rule 59.61 suppressed it while the Air Game was abstract and it is in
    # force now. An air dump feeds only the SGSUs standing on it (35.14), never the land army.
    facilities = oob.air_facilities(sections="ABC")
    supplies += oob.air_dumps(facilities, oob.DESERT_FOX_AIR_POOLS)
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
    initial = _initial_supply(supplies, units)
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
        air_facilities=tuple(facilities),                     # rule 36: the squadron bases on the map
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


def _campaign_tobruk_cargo() -> dict:
    """The per-Game-Turn Tobruk lifeline cargo -- BOTH the Commonwealth ferry and the Axis lane 6
    into the San-Giorgio-crippled harbour -- sized to what that harbour can actually land, so the
    lane no longer plans 3.5x its quay (T0-17). Asks the SEEDED port for its budget (_tobruk_port,
    which is the one place the 55.3-vs-60.7/61.6 Efficiency question is decided) rather than
    restating the number here: 1700 t at eff 2/5 -> 680 t/OpStage. The old _load_cargo() shipped
    7229 t -- 1500 Ammunition into a quay that lands ~170 -- and 56.27 forbids shipping over capacity
    (the un-landable overflow was silently annihilated). FLAGGED PROXY: this keeps the representative
    61.36 MIX but scales its tonnage to the harbour, inventing no new ratio; the real fix is the
    56.21/56.22 convoy-planning decision (deferred, T1-9)."""
    base = _load_cargo()
    base_tons = sum(base[c] * TONS_PER_POINT[c] for c in base)
    budget = port_tonnage_budget(_tobruk_port(Side.AXIS, coords.to_axial(coords.parse(_TOBRUK))))
    frac = budget / base_tons
    return {c: max(1, math.floor(base[c] * frac)) for c in base}


def _caps_tonnage(tons: int) -> dict:
    """55.14 port caps: per-commodity Point caps _UNLIMITED (so tonnage is the sole gate)
    plus the 55.3 tonnage rating crossed to Points at the landing edge (54.5)."""
    return {"cap_ammo": _UNLIMITED, "cap_fuel": _UNLIMITED, "cap_stores": _UNLIMITED,
            "cap_water": _UNLIMITED, "cap_tons": tons}


# 55.25, verbatim: "The San Giorgio reduces the efficiency level of Tobruk by three levels."
_SAN_GIORGIO_BLOCK = 3


def _tobruk_port(side: Side, hex_: Coord) -> Port:
    """THE ONE Tobruk harbour -- seeded HERE for every scenario (campaign and benchmark alike),
    because the book prints two irreconcilable starting Efficiencies for it and the choice between
    them must be made once, in one place, with its reasons attached.

    WHAT THE BOOK PRINTS (the three disputed sites -- the 55.3 chart, 60.7 and 61.6 -- were rendered
    from the original scan and read by eye, page numbers below; the rest are docs/rules):

      [55.12] -- "Every port in the game has an Efficiency Level, which is an abstract number
          assigned to that port. For example, TOBRUK HAS AN EFFICIENCY LEVEL OF 5." (The rules
          proper, naming this port's number outright -- and 55.12 is the rule Port.max_eff cites.)
      [55.14] -- "a port with an assigned Efficiency Level of 5 that has had its Level reduced to 3
          operates at 3/5 (or 60%) of its assigned capacity" -- i.e. supply.port_tonnage_budget's
          eff/max_eff, worked on Tobruk's own 5.
      [55.3] Port Capacity and Efficiency Level Chart (PDF p110 = play-aid booklet p15) --
          "Tobruk†  Efficiency Level 5 | In 1 | Out 3 | Maximum Tonnage 1,700"
      [55.3] legend -- "A loss of one level of efficiency decreases the port's capacity by a
          fraction equal to one over the LISTED efficiency level."
      [55.3] footnote † -- "Begins the campaign with an efficiency below the listed five due to
          the San Girogio [sic] partially blocking the harbor."
      [55.25] -- "The San Giorgio reduces the efficiency level of Tobruk by three levels."  => 5 - 3 = 2
      [55.18] -- a port regains +1/OpStage but "can never go above its maximum assigned level
          (see Case 55.3)."
      [60.7]  (PDF p79) -- "Tobruk, which is at Efficiency Level 7 (the San Giorgio is partially
          sunk, blocking the harbor)."
      [61.6]  (PDF p81) -- "Tobruk (at seven-and San Giorgio is still there)."

    THE CONTRADICTION IS THE BOOK'S OWN, not an OCR artifact: the scan shows the digit 7 in 60.7 and
    the word "seven" in 61.6, on two different pages, so no single mis-read produces both (the port
    plan's guess that 7 is a mis-scanned 2 is refuted -- but its conclusion, 2, is right). SEVEN
    printed statements -- 55.12, 55.14, 55.18, the chart row, the legend, the dagger, 55.25 -- put
    this harbour at a listed 5 starting at 2; two (60.7, 61.6) put it at 7 while stating in the same
    breath that the San Giorgio is present.

    JUDGEMENT CALL, FLAGGED -- WE FOLLOW THE CHART, and the campaign and benchmark agree on it:
      1. A 7 is not representable in the chart's own machinery. 55.18 forbids a level above the 55.3
         assigned maximum, 55.12 assigns this port 5 by name, and the legend defines capacity only as
         a REDUCTION from the listed level -- an Efficiency 7 on a listed-5 port has no defined
         capacity at all.
      2. Seeding max_eff=7 to make the 7 fit would silently re-denominate the legend's charted
         per-level damage fraction from 1/5 to 1/7 (each [41.5] harbour hit costing 243 t instead of
         340 t) -- bending a printed chart magnitude to rescue a number, which is backwards.
      3. It would also make 55.25/55.26 and the charted Tobruk unblock cost (25 Ammo + 10 Stores,
         chart 90:1335) dead content: with no block there is nothing for engineers to clear.
      4. 60.7's own parenthetical explains Tobruk as the EXCEPTION to "all ports at listed
         Efficiency" BECAUSE the San Giorgio blocks it -- i.e. the exception is a reduction, which
         only 2 is and 7 is not.
    The 7 is transcribed as printed in data/logistics_rates.json initial_port_states_61_6 (flagged
    there as not followed); it is not reconciled away, and it is not silently obeyed either.

    So: max_eff = the chart's LISTED 5 (also the legend's damage denominator), blocked = the 55.25
    three-level block, eff = 5 - 3 = 2 = the regeneration ceiling. Bomb damage below 2 still recovers
    +1/OpStage (55.18) but never past the wreck (55.26, engineer clearing deferred), so the besieger
    must keep bombing to hold the quay shut. The chart's 1,700 t at eff 2/5 crosses (54.5) to a
    680 t/Operations-Stage SHARED budget across all commodities -- the real gate on either side's
    Tobruk lifeline."""
    tob = _PORT_TONS["tobruk"]
    listed = tob["efficiency_level"]                     # [55.3] 5 -- the chart, not a literal here
    return Port("PORT-Tobruk", side, hex_, "major",
                max_eff=listed, eff=listed - _SAN_GIORGIO_BLOCK, blocked=_SAN_GIORGIO_BLOCK,
                **_caps_tonnage(tob["tons"]))            # [55.3] 1700 t


def _axis_rear(supplies, target):
    # An air-facility dump (36.17) is skipped for the same reason a well is: it is the SGSUs'
    # larder, not a freight depot, so no convoy lands in it and no lorry park stages on it.
    axis = [s for s in supplies if s.side == Side.AXIS and not s.air_dump]
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
    cw = [s for s in supplies if s.side == Side.ALLIED and s.id != "AL-Tobruk"
          and not s.air_dump]                    # 36.17: an airfield's pile is no railhead
    return max(cw, key=lambda s: (distance(s.hex, target), s.id)) if cw else None


def _rommel_ports(supplies, target) -> tuple[Port, ...]:
    """The scenario's ports and their built-in dumps (56.28), seeded from the real 55.3
    tonnages + the 61.6 scenario Efficiency Levels. Tonnage is the sole 55.14 gate (the
    per-commodity caps are _UNLIMITED). Tobruk comes from _tobruk_port -- the ONE place the
    55.3-chart-vs-60.7/61.6-setup Efficiency contradiction is decided (chart: eff 2 of a listed 5,
    San Giorgio blocking 3) -- so this benchmark and the full campaign cannot drift apart. 61.6's
    printed "at seven" is NOT followed; see that function for the scan reading and the reasons.

    The rear Axis supply port is TRIPOLI (55.3 Efficiency 10, 15000 t/OpStage) -- the real
    main Axis harbour, working at full efficiency. STEP 5 repointed it here from the scuttled
    Benghazi (eff 0, which landed nothing): the historical bottleneck was never the harbour
    but the ~1500 km haul from Tripoli to the front, which the 2nd/3rd-line truck pool
    (_rommel_trucks) must now bridge. The Commonwealth base proxies Alexandria (55.3 15000 t)
    at full efficiency. Tonnages are the real 55.3 chart; the port geography (rearmost Axis
    dump / easternmost CW dump) is the scenario proxy for off-corridor Tripoli/Alexandria."""
    ports = [_tobruk_port(Side.ALLIED, target)]          # 55.3: eff 2 of 5 (San Giorgio), 1700 t
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
        PORT-Tobruk (55.3 eff 2/5, the San Giorgio blocking it) -- the load-bearing garrison
        lifeline.
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


# [61.43] "Additional second/third line trucks: 10 Medium Trucks at air facilities." The Desert Fox
# twin of [60.33]/[60.43]'s "Any Air Facility" rows, and gated by the same 59.61 switch.
_TRUCKS_61_43_AIR = {"light": 0, "medium": 10, "heavy": 0}


def _rommel_trucks(supplies, target) -> tuple[TruckFormation, ...]:
    """The Axis 2nd/3rd-line motor-transport pool (rules 53 / 54.2), staged at the rear
    supply port (the AX rear dump, where PORT-Tripoli lands its convoys). This is the
    inland distribution layer that must relay the port's tonnage forward to the dumps the
    front traces to (53.14 relay = the load/move/unload triple). The scripted
    policy.truck_orders shuttles it between Tripoli and the front, each hop burning the
    trucks' OWN cargo fuel (49.18) -- so the further the front, the more of every load the
    convoy burns just moving it, the classic desert supply death-spiral.

    Transcribed off the 1979 [61.43] chart: 95 Light / 280 Medium / 50 Heavy Truck Points, "available
    for any and all purposes" -- the book "firmly suggests" the Axis run these as its Second/Third Line
    Trucks, "otherwise he will have a hard time moving his Supply around." The chart's further row --
    "Additional second/third line trucks: 10 Medium Trucks at air facilities" -- was GATED OFF while the
    Air Game was abstract (59.61); Phase 5.1 plays the Air Game, so it is seeded (_air_facility_trucks).
    It goes to the rear with the rest, and that is a FLAGGED placement: the extracted Desert Fox order of
    battle carries no AXIS air facility on maps A-C at all (61.42 gives the Axis a free "one airfield and
    one air landing strip in any hex west of El Agheila" that we do not model), so there is no facility
    hex for the chart's restriction to name.
    One TruckFormation per 54.2 class at the rear, the campaign idiom (_truck_park).

    This REPLACES the earlier 14-Truck-Point placeholder (8 H + 6 M): the real pool is ~30x larger, and
    the placeholder was why a competent Axis stranded 69 hexes short of Tobruk -- it had 3% of its lorries
    and physically could not relay the port's tonnage forward (rule 53.0: "without a well-organized convoy
    system your entire military effort will fall apart"). The haulage bottleneck over the Tripoli->front
    distance is still the scarcity -- it is now the CHART'S scarcity, not a guessed one."""
    rear = _axis_rear(supplies, target)
    if rear is None:
        return ()
    # Organized as MANY convoy formations (~40 Truck Points each) rather than one giant column per class,
    # so the relay runs parallel bucket-brigade legs -- port, first dump, second dump all filling at once
    # instead of one column serialising the whole haul. A competent quartermaster's organization of the
    # SAME faithful 425-Truck-Point [61.43] total (points conserved exactly), not a magnitude change.
    out: list[TruckFormation] = []
    air_medium = sum(row["medium"] for row in _air_facility_trucks(_TRUCKS_61_43_AIR))
    for cls, total in (("light", 95), ("medium", 280 + air_medium), ("heavy", 50)):
        n = max(1, total // 40)
        for i in range(n):
            pts = total // n + (1 if i < total % n else 0)
            out.append(TruckFormation(f"AX-Truck-{cls[0].upper()}{i + 1}", Side.AXIS, rear.hex,
                                      cls, points=pts, line=3))
    return tuple(out)


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
    LAND air mission per scheduled game-turn, each ROLLING on the [41.5] Ports CRT (engine._air_port)
    for the Efficiency Levels knocked off -- and the harbour regenerates (55.18) any OpStage it is not
    bombed down, so the schedule must sustain the pressure to shut the ~141-Ammo/OpStage landing cap
    that is the garrison's lifeline (Tobruk is seeded at the 55.3 eff 2 of 5 with the San Giorgio
    blocking three levels, so 55.18 recovers a bombed quay only back up to that ceiling of 2 -- see
    _tobruk_port). `start`/`cadence` are FLAGGED tuning proxies for the siege TEMPO (how fast the
    throat closes against the 12-turn clock)."""
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
    the Axis Luftwaffe LAND wing and a per-turn PORT-Tobruk bombing schedule ([41.5] rolls against a
    harbour that regenerates 55.18 between the bombs); `raf` adds a contesting Commonwealth fighter wing so winning the LAND
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

# [25.12] "Each major city on the game-map is a Level 2 fortification. CAIRO AND ALEXANDRIA ARE
# LEVEL 3 FORTIFICATIONS." The Delta carried level ZERO -- the only unfortified major cities on the
# map were the two the whole war was fought for. It is also the rule-64.71 auto-win objective (the
# Axis wins the war OUTRIGHT by occupying every hex of both), so the hexes are one and the same set
# and are read from the one table that already enumerates them.
_DELTA_FORT = 3


def delta_hexes() -> tuple:
    """Every hex of Alexandria and Cairo: the 64.71 auto-win objective, and (25.12) the map's two
    Level 3 fortifications. Two hexes of Alexandria, five of Cairo, off the 64.7 city table."""
    aw = campaign_victory.load_victory_cities()["auto_win"]
    return tuple(coords.to_axial(coords.parse(h))
                 for h in aw["alexandria"] + aw["cairo"])


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
    hex jump to the front. Three COASTAL dumps are pre-stocked from the 60.34 chart (Tobruk, Bardia,
    Derna); the intervening waypoints are empty, spaced along the Via Balbia -- Benghazi -> W1 -> W2 ->
    Derna -> W3 -> Tobruk -> Bardia -- each a forward dump campaign_truck_orders fills from the one
    behind it. A FOURTH 60.34 dump, C0716 (100 Ammo / 50 Fuel / 50 Stores), is off the coast road
    entirely: the deep-desert supply point the [60.31] Saharan Detachment (deployed within 3 hexes)
    traces to. Transcribed here to COMPLETE the 60.34 Axis dump chart (its omission left the Axis 50
    Fuel under the charted on-map total); a static outpost ~30 hexes from the nearest unit, NOT a relay
    leg -- it never becomes _axis_rear (dist 79 to Alexandria vs Benghazi's 126, so the harbour holds).

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
        SupplyUnit("AX-Stage-C0716", Side.AXIS, ax("C0716"), ammo=100, fuel=50, stores=50, water=0),
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


# [24.9] The OOB's own field dumps -- the mobile supply that rides with a division (32.3) and
# follows it about the desert. Everything else the campaign seeds is a place ON the supply line, and
# is a CONSTRUCTED dump (see the stamp in campaign()). game.oob._place_dumps mints these ids.
_MOBILE_DUMPS = ("AX-Dump", "AL-Dump")

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

# [60.44] COMMONWEALTH INITIAL SUPPLY STATUS -- the charted start-line stock, transcribed. The Axis
# got its 60.34 equivalents (Tobruk/Bardia/Benghazi/Derna) at construction; the Commonwealth's own
# chart was never seeded at all, so the Western Desert Force opened the war standing on an EMPTY
# railhead and an EMPTY Sidi Barrani, with nothing forward of the Delta but what a 16-Truck-Point
# pool could carry. Keyed by the depot NAME on the spine above; the chart lists no stock for Sollum,
# El Daba or El Hamman, so those stay empty (a Field Supply Depot is hauled into, not pre-filled).
#
# The chart's third row, "Dump I" (500 Ammo / 750 Fuel / 500 Stores), is the anonymous FREE-PLACEMENT
# field dump -- it IS seeded, as the AL-Dump pool game.oob splits over the OOB field dumps
# (CAMPAIGN_DUMP_POOLS -> cw_dump_pool_60_44), the mirror of the Axis Dump 1 + Dump 2 pool
# (axis_dump_pool_60_34). What both charts leave unseeded, and flagged, is symmetric: the DUMMY dumps
# (bluff counters carrying no supply) and the AIR SUPPLY allotments (CW 200/250/50; Axis
# 1200/850/100/100), the latter gated off with the abstracted Air Game (59.61, see _air_facility_trucks).
# The Axis Tripoli box (250/5000/250) is off-map -- Tripoli has no hex in sections A-E (see
# _campaign_axis_trucks). Every stocked, on-map, fixed-hex dump on BOTH 60.34 and 60.44 is now seeded
# (C0716 in _campaign_staging_dumps).
_CW_DUMPS_60_44 = {
    "Matruh":  {"ammo": 1000, "fuel": 3000, "stores": 4000},    # Mersa Matruh (D3714)
    "Barrani": {"ammo":  250, "fuel":  500, "stores":  100},    # Sidi Barrani (C4131)
}


def _campaign_cw_depots() -> list[SupplyUnit]:
    """The seeded Commonwealth spine (see _CW_FIELD_DEPOTS / _CW_RAIL_STATIONS above). Each leg is
    within ONE 30-CP truck convoy hop of the one behind it (53.22), VERIFIED against
    supply.reachable_truck_moves the way the Axis chain was: Matruh -> Sidi Barrani costs 29 CP and
    Sidi Barrani -> Sollum 22, so no waypoint hex is needed. (What blocks the second leg on
    Game-Turn 1 is the Italian 10th Army standing on it -- which is the point of the offensive, not
    a gap in the chain.)

    Mersa Matruh and Sidi Barrani open STOCKED, to the [60.44] chart above -- these are the existing
    spine depots, filled, not new dumps beside them. The rest start EMPTY. All base=False: a Field
    Supply Depot evaporates like any field dump (49.3), being no rule-57 strategic base."""
    return [SupplyUnit(f"AL-Stage-{name}", Side.ALLIED, coords.to_axial(coords.parse(lbl)),
                       water=0, **_CW_DUMPS_60_44.get(name, {"ammo": 0, "fuel": 0, "stores": 0}))
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
    fwd = [s for s in supplies if s.side == Side.ALLIED and not s.base and not s.is_dummy
           and not s.air_dump]                   # 36.17: an airfield's pile is no railhead
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


# [54.32] "The Commonwealth supply capacity of the railroad is 1500 tons per Operations Stage in
# either direction." The charted capacity of the Western Desert Railway -- the exact twin of the
# Axis's [56.5] convoy tonnage, and the number the campaign was missing. Transcribed from the rule
# text (docs/rules/54-supply-co-ordination.md); it is not in the 90-charts play-aid, so it lives
# here beside _PORT_TONS rather than in data/logistics_rates.json.
_RAIL_TONS_PER_OPSTAGE = 1500
_RAIL_STAGE_COMMODITIES = ("AMMO", "FUEL", "STORES")   # 54.33: one type per stage. Water is piped.


def _campaign_rail_cargo(gt: int) -> dict:
    """One Game-Turn of Western Desert Railway freight (rules 54.32 / 54.33 / 54.34).

    54.32 rates the railroad at 1,500 TONS PER OPERATIONS STAGE, and a Game-Turn is three
    Operations Stages (engine.run), so a week of trains is three stage-loads. 54.33 lets the
    railroad carry only ONE type of supply at a time -- "it may move fuel, ammunition, or stores,
    not any combination of the three" -- so each stage is a single commodity, and its tonnage
    crosses to Points through the 54.5 Equivalent Weights (a ton of ammunition is a quarter of a
    Point; a ton of fuel is eight, which is why the same train is worth 375 Ammunition or 12,000
    Fuel). Water is NOT hauled: 54.33 says it need not be -- "the railroad hexes are pipelines in
    and of themselves" -- and game.wells.pipeline already seeds that corridor, Alexandria to Mersa
    Matruh, as an unlimited 52.23 water source.

    54.34 stands the railway down for ONE Operations Stage a calendar month, hauling water for its
    own use. WHICH stage is the player's call -- "Players must state each month which Operations
    Stage they are not using the railroad" -- and this schedule gives up the STORES stage in the
    month's first week, the load a fighting army misses least. That choice is a flagged SCHEDULING
    proxy; the 1,500-ton magnitude behind it is the rulebook's own.

    What this REPLACES is the bug: the lane used to ship one _load_cargo() Supply Unit a week --
    a placeholder borrowed from Tobruk's 61.36 built-in dump -- which put 500 Fuel a turn on the
    trains against the Axis convoy's charted thousands. Measured over the full campaign, the
    Commonwealth landed 55,500 Fuel to the Axis's 1,770,000."""
    stages = list(_RAIL_STAGE_COMMODITIES)
    if (gt - 1) % calendar.GT_PER_MONTH == 0:           # 54.34: one OpStage a month carries water
        stages.remove("STORES")
    cargo = {c: 0 for c in COMMODITIES}
    for c in stages:
        cargo[c] += tons_to_points(_RAIL_TONS_PER_OPSTAGE, c)
    return cargo


# --- [60.33] / [60.43] THE SECOND/THIRD-LINE TRUCK PARKS -------------------------------------
# The rulebook charts BOTH sides' 2nd/3rd-line motor transport IN FULL, by location, in Truck Points
# (1 Point = 10 lorries, 53.0). The campaign seeded a token 8 Heavy + 8 Medium a side -- about a
# thirteenth of the charted parks -- and the lorries then WERE the war: the Commonwealth's rail-fed
# railhead could stand there holding 1,476 Ammunition and 3,000-5,000 Fuel and still put only ~48
# Ammunition and ~1,000 Fuel a turn on the road, because 16 Truck Points is the whole of the 54.2
# capacity there was to load. The pool was the binder on everything upstream of it.
#
# Both charts grant FREE PLACEMENT inside a restriction -- the player "may assign them and place
# them as he wishes, within the restrictions listed" -- so the hexes chosen below are OUR ASSIGNMENT
# of the allotment, flagged as such at each site, and every row goes to the location its own
# restriction names. The magnitudes are the rulebook's and are transcribed, not tuned.
_TRUCKS_60_33 = {                    # [60.33] Italian Second-Third Line Trucks (Truck Points)
    "Tripoli":           {"light": 25, "medium": 140, "heavy": 40},
    "Anywhere in Libya": {"light": 30, "medium": 100, "heavy": 25},
    "Any Air Facility":  {"light": 10, "medium":  50, "heavy":  0},
}
_TRUCKS_60_43 = {                    # [60.43] Commonwealth Second-Third Line Trucks (Truck Points)
    "Any hex in Cairo":  {"light":  0, "medium": 40, "heavy": 10},
    "Alexandria":        {"light": 10, "medium": 20, "heavy":  0},
    "Anywhere, maps":    {"light": 15, "medium": 40, "heavy":  5},
    "Any Air Facility":  {"light":  5, "medium": 30, "heavy": 20},
}

# [59.61] AIR-FACILITY TRUCKS: THE GATE IS NOW OPEN. 59.61 says to "ignore all Trucks and supplies
# available at/for Air facilities in the initial set-ups" -- and it says it under the heading of
# playing this game WITHOUT the Air Game. That was our mode, and the engine obeyed the rule for the
# air SUPPLIES and disobeyed it for the air TRUCKS ([60.33]'s 'Any Air Facility' 10 L / 50 M = 60 TP
# for the Axis, [60.43]'s 5 L / 30 M / 20 H = 55 TP for the Commonwealth), over-seeding both parks --
# the T0-18 bug. The port plan's instruction was to GATE the rows, not delete them, "because when
# the Air Game lands these come back, and the SGSUs need them."
#
# Phase 5.1 is that landing. Rule 36 air facilities are on the map, rule 35 SGSUs are eating off
# them, and the [60.34]/[60.44] air-supply allotments 59.61 also suppressed are seeded beside them
# (game.oob.air_dumps). So both truck rows come back on, and the flag stays as the ONE named place
# the exclusion is expressed rather than being scattered back through the chart.
_AIR_GAME_PLAYED = True


def _air_facility_trucks(row: dict) -> tuple[dict, ...]:
    """The 59.61 switch over one [60.33]/[60.43]/[61.43] 'Any Air Facility' truck row: seeded when
    the full Air Game is played (it is, from Phase 5.1), ignored when air is abstract. The row lives
    on the charts either way -- this only decides whether it is placed on the board."""
    return (row,) if _AIR_GAME_PLAYED else ()


def _air_facility_park(facilities, side: Side, near) -> "Coord | None":
    """WHERE a chart's "Any Air Facility" truck row is placed: the side's own air facility nearest
    `near` -- its main supply hub -- with ties broken by facility id.

    The rows say "Any Air Facility", so which one is the Player's free choice; this is OUR ASSIGNMENT
    of it, and it is the ordinary quartermaster's answer (the field the freight can actually reach).
    It matters that the row lands ON a facility and not on the hub itself: 36.17 makes the facility
    its squadron's larder, so these are the lorries that keep the larder full (35.15) -- and a park
    parked on the railhead instead would simply be more freight lorries competing for the trains'
    tonnage, which is not what the chart allotted them for. None when the side holds no facility."""
    own = [f for f in facilities if f.side == side]
    return min(own, key=lambda f: (distance(f.hex, near), f.id)).hex if own else None


def _truck_park(prefix: str, side: Side, hexpos, *rows: dict) -> list[TruckFormation]:
    """One TruckFormation per 54.2 class, pooling the chart `rows` assigned to `hexpos`.

    All THREE classes are modelled, Light included: game.supply.truck_capacity carries the full 54.2
    chart, so the Light rows are honoured rather than folded away (a Light Truck Point hauls 50 Fuel
    and 2 Ammunition, at the longest convoy reach on the chart -- CPA 40 against Medium/Heavy's 30)."""
    pool = {cls: sum(row.get(cls, 0) for row in rows) for cls in ("light", "medium", "heavy")}
    return [TruckFormation(f"{prefix}-{cls[0].upper()}", side, hexpos, cls, points=pts, line=3)
            for cls, pts in pool.items() if pts > 0]


def _campaign_cw_trucks(supplies, facilities) -> tuple[TruckFormation, ...]:
    """The Commonwealth 2nd/3rd-line motor-transport pool: the WHOLE [60.43] chart, 195 Truck Points
    against the 16 the campaign used to seed (140 on the non-air rows plus the 55 at Air Facilities,
    which 59.61 kept off the board only while the Air Game was abstract -- see _air_facility_trucks).
    Without lorries the Commonwealth cannot project supply one hex west of its railhead -- a unit's
    own trace reaches ~6-12 hexes -- so Operation Compass
    and Crusader strand every unit they send toward Benghazi. The Western Desert Force ran on
    lorries; this is the park that hauled it to El Agheila.

    OUR ASSIGNMENT of the chart's free placement, row by row:
      * "Any hex in Cairo" (40 M / 10 H) -> Cairo, and "Alexandria" (10 L / 20 M) -> Alexandria:
        placed exactly where the chart's restriction puts them, on the rule-57 Delta base. They sit
        60 and 34 hexes BEHIND the railhead and must drive up to join the relay -- which is the real
        Delta lorry park, and which is why campaign_policy._is_faucet must let a lorry lift from the
        bottomless base under its wheels. (Seeded dry with nothing loadable beneath them, as the
        relay stood, all fifty of those Truck Points would have idled in the Delta for the whole war.)
      * "Anywhere, maps" (15 L / 40 M / 5 H) -> the Mersa Matruh RAILHEAD: the rail-fed faucet (60.7)
        and the exact hex the pool binds at. Not the forward Field Supply Depots -- on Game-Turn 1
        Sollum and Sidi Barrani lie in the path of the advancing Italian 10th Army, and a staff does
        not park its lorry reserve in front of an oncoming army.
      * "Any Air Facility" (5 L / 30 M / 20 H) -> the Commonwealth air facility nearest the railhead
        (_air_facility_park). 59.61 suppressed this row while the Air Game was abstract; Phase 5.1
        plays it, so it is on the board -- and it goes where the chart puts it, ON a facility, now
        that rule 36 gives facilities hexes. These are not more freight lorries for the front: they
        are the transport that keeps a squadron's 36.17 larder full (35.15), and pooling them at the
        railhead instead measurably drained the transit node the garrison eats from."""
    railhead = _campaign_cw_railhead(supplies)
    if railhead is None:
        return ()
    def ax(lbl: str):
        return coords.to_axial(coords.parse(lbl))
    airfield = _air_facility_park(facilities, Side.ALLIED, railhead.hex)
    park = tuple(
        _truck_park("AL-Truck-Cairo", Side.ALLIED, ax(_CW_BASE_HEXES["Cairo"]),
                    _TRUCKS_60_43["Any hex in Cairo"])
        + _truck_park("AL-Truck-Alex", Side.ALLIED, ax(_CW_BASE_HEXES["Alexandria"]),
                      _TRUCKS_60_43["Alexandria"])
        + _truck_park("AL-Truck-Matruh", Side.ALLIED, railhead.hex,
                      _TRUCKS_60_43["Anywhere, maps"]))
    if airfield is None:
        return park
    return park + tuple(_truck_park("AL-Truck-Airfield", Side.ALLIED, airfield,
                                    *_air_facility_trucks(_TRUCKS_60_43["Any Air Facility"])))


def _campaign_axis_trucks(supplies, target, facilities) -> tuple[TruckFormation, ...]:
    """The Axis 2nd/3rd-line motor-transport pool: the [60.33] chart's ON-MAP rows, 215 Truck Points,
    staged at the Benghazi port-of-arrival where the Mediterranean convoys land and where the coastal
    relay (campaign_policy.campaign_truck_orders) reloads.

    OUR ASSIGNMENT: "Anywhere in Libya" (30 L / 100 M / 25 H) -> Benghazi, which is in Libya and is
    the single hex the entire Axis economy passes through. "Any Air Facility" (10 L / 50 M) -> the
    Axis air facility nearest Benghazi (_air_facility_park): 59.61 kept that row off the board only
    while the Air Game was abstract, Phase 5.1 plays it, and rule 36 now gives it a facility hex to
    stand on -- these lorries keep a squadron's 36.17 larder full (35.15), they are not extra freight
    capacity for the Panzerarmee.

    *** THE TRIPOLI ROW IS NOT SEEDED, AND THAT IS NOT A CONCESSION -- IT IS THE AXIS'S WAR. *** The
    chart's largest row by a wide margin -- 25 Light / 140 Medium / 40 Heavy, 205 of the Italian
    park's 420 Truck Points, very nearly half of it -- is restricted to TRIPOLI, and Tripoli has no
    hex. It is the off-map "Tripoli Box" (rule 22.31 / 8.88; data/victory_cities.json records
    tripoli: null -- "no hex exists in sections A-E"). No hex on the playable map may hold that row,
    and the engine has no truck-ARRIVAL scheduler to walk it east ([4.43b] deferred: state.trucks is
    static at construction). So it stays off the board, flagged, and the Axis fights on the half of
    its park that is actually in the theatre -- which is the literal historical fact the campaign is
    about: the lorries were at Tripoli, fifteen hundred kilometres behind the wire, and that is
    exactly why the Panzerarmee could never be fed at Alamein."""
    rear = _axis_rear(supplies, target)
    if rear is None:
        return ()
    park = tuple(_truck_park("AX-Truck-Benghazi", Side.AXIS, rear.hex,
                             _TRUCKS_60_33["Anywhere in Libya"]))
    airfield = _air_facility_park(facilities, Side.AXIS, rear.hex)
    if airfield is None:
        return park
    return park + tuple(_truck_park("AX-Truck-Airfield", Side.AXIS, airfield,
                                    *_air_facility_trucks(_TRUCKS_60_33["Any Air Facility"])))


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
        line = _campaign_cw_rail_line(supplies)        # 54.3/60.7: the railhead RETRACTS, it never dies
        # rail=True: a train is not a ship. It carries the railroad's OWN charted capacity
        # (54.32, _campaign_rail_cargo) and never crosses a quay, so the 55.14 harbour throttle
        # does not apply to it -- see state.Convoy. Mersa Matruh is BOTH a 250-ton harbour and the
        # railway terminus, and putting the Western Desert Railway through the harbour's cranes
        # clipped it to a twenty-fourth of its rated capacity (measured: 62 of 1,500 Ammunition
        # Points a turn).
        convoys += [Convoy(f"cw-rail-t{gt}", Side.ALLIED, gt, "CW-RAILHEAD", railhead.id,
                           _campaign_rail_cargo(gt), retarget=line, rail=True)
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
    # a free faucet: engine._naval_convoys throttles both through the ONE 55.3 harbour (1700 t at
    # eff 2/5 -> a 680 t/OpStage SHARED tonnage budget; see _tobruk_port), and 56.15 cancels whichever of
    # them is sailing into a city the enemy now controls. They hand off automatically, in both
    # directions, for as many times as the fortress changes hands.
    convoys += [Convoy(f"tobruk-ferry-t{gt}", Side.ALLIED, gt, "SEA-TOBRUK", "AL-Tobruk",
                       _campaign_tobruk_cargo())     # T0-17: sized to the 55.3 harbour, not 3.5x it
                for gt in range(1, max_turns + 1)]
    convoys += [Convoy(f"tobruk-axis-t{gt}", Side.AXIS, gt, _AXIS_TOBRUK_LANE, "AX-Stage-Tobruk",
                       _campaign_tobruk_cargo())     # T0-17: sized to the 55.3 harbour, not 3.5x it
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

    Kept under the id PORT-Tobruk and seeded by _tobruk_port -- the ONE place the harbour's disputed
    starting Efficiency is decided, shared with the Desert Fox benchmark (_rommel_ports) so the two
    cannot drift apart. It reads the [55.3] chart: eff 2 of a listed max 5, the San Giorgio blocking
    three levels (55.25), 1700 t crossing (54.5) to a 680 t/Operations-Stage SHARED tonnage budget
    across all commodities -- the real gate on either side's Tobruk lifeline. 60.7's printed
    "Efficiency Level 7" is NOT followed; the scan reading and the reasons live in _tobruk_port."""
    ports = []
    rear = _axis_rear(supplies, target)
    if rear is not None:
        chart = _PORT_TONS.get("benghazi", _PORT_TONS["tripoli"])   # 55.3: Benghazi Efficiency Level 3
        eff = chart["efficiency_level"]
        ports.append(Port("PORT-Benghazi", Side.AXIS, rear.hex, "major", max_eff=eff, eff=eff,
                          **_caps_tonnage(chart["tons"])))
    railhead = _campaign_cw_railhead(supplies)
    if railhead is not None:
        chart = _PORT_TONS.get("mersa_matruh", _PORT_TONS["tripoli"])   # 55.3: Mersa Matruh Efficiency Level 1
        eff = chart["efficiency_level"]
        ports.append(Port("PORT-Matruh", Side.ALLIED, railhead.hex, "major", max_eff=eff, eff=eff,
                          **_caps_tonnage(chart["tons"])))
    ports.append(_tobruk_port(Side.AXIS, coords.to_axial(coords.parse(_TOBRUK))))
    return tuple(ports)


# --- C4: the air war over the harbours (rules 40-46 at the abstract 32.0/58.0 grain) ----------
# FLAGGED PROXY: the 34.6/59.3 Initial Air Strengths chart is untranscribed (see state.AirWing,
# which says so of its own magnitudes), so these Air Points are proxies. They are deliberately
# SYMMETRIC -- neither side is handed the sky by fiat -- because this is the UNTUNED structural
# baseline: the 40/45/46 superiority roll should decide who flies, not the seeding. Period-varying
# strengths (the Luftwaffe's 1941-42 ascendancy, the Desert Air Force's 1942 revival) are the
# obvious calibration lever, and deliberately NOT pulled here.
_AIR_FIGHTERS = 8          # F: the fighter pool contesting air superiority each Operations Stage
_AIR_STRIKE = 6            # S: the strike points that batter a harbour (41.39B)


def _campaign_air() -> tuple[AirWing, ...]:
    """A LAND-arena air wing for BOTH sides -- the Luftwaffe/Regia Aeronautica and the Desert Air
    Force. The campaign seeded NONE, and that single omission is why its Tobruk was invulnerable:
    with state.air empty no air beat fires at all, engine._air_port is unreachable, and no port can
    ever lose Efficiency. And interdiction alone cannot cut the lane: the 41.66 CRT skims a
    PERCENTAGE off a cargo the 55.3 SHARED tonnage budget has already clipped to the harbour's
    680 t/OpStage (1700 t at eff 2/5), so a cut that still leaves the manifest over the budget lands the same
    tonnage -- arithmetically inert (see the Tobruk interdiction tests). Only bombing the harbour's
    Efficiency down ([41.5], _air_port) actually chokes a sea lane, and the harbour regenerates
    (55.18) between the bombs, so it takes a sustained air campaign to keep it shut."""
    return (AirWing("LW-land", Side.AXIS, "LAND",
                    fighters=_AIR_FIGHTERS, strike=_AIR_STRIKE, recon=0),
            AirWing("DAF-land", Side.ALLIED, "LAND",
                    fighters=_AIR_FIGHTERS, strike=_AIR_STRIKE, recon=0))


def _campaign_air_missions(max_turns: int) -> tuple[AirMission, ...]:
    """THE SIEGE OF TOBRUK AS A DUEL: both sides bomb the harbour, every game-turn, all war.

    There is ONE Tobruk, one harbour and one Port object (see _campaign_ports), and it serves
    whoever holds the city. So the SCHEDULE is symmetric and the ENGINE decides who is besieging:
    _air_port reads CONTROL of the hex and refuses the side that holds it ("never bomb your own
    harbour"), letting the other one through. The holder is fed by sea; the besieger must bomb the
    quay shut and starve the garrison to a rule-15.15 dry-ammunition surrender. The roles hand off
    automatically, in both directions, as many times as the fortress changes hands -- exactly as
    the 56.15 convoy lane already hands the sea route from one side to the other.

    PORT-Tobruk starts at the 55.3 Efficiency 2 of 5, the San Giorgio blocking three levels (55.25;
    see _tobruk_port), and bomb damage is NOT a one-way ratchet: a level knocked off the quay by
    [41.5] regenerates +1 every OpStage the harbour is not bombed, up to that blocked ceiling of 2
    (55.18/55.26, _port_regen). So a besieger who rolls a [41.5] level off the quay must keep rolling
    to hold it down -- one bomb no longer shuts the lifeline for good. That is what
    makes Tobruk's 200 Victory Points something a side has to
    EARN and then keep fed, instead of the free gift of whoever happened to be standing there on
    Game-Turn 1.

    NO mission is flown at Mersa Matruh, and that is not an oversight. Its harbour is real (55.3:
    250 tons) but it is not what feeds the Eighth Army -- the RAILWAY is (54.3), and a railway is
    not cut by bombing a quay. It is cut by taking the rail hexes, which pushes the railhead back
    east down the line (_campaign_cw_rail_line). That is the Axis's lever against the Commonwealth
    lifeline, and it is a GROUND one -- which is how Rommel actually did it."""
    return tuple(AirMission(side, "port", "PORT-Tobruk", t)
                 for t in range(1, max_turns + 1)
                 for side in (Side.AXIS, Side.ALLIED))


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

    Victory is the faithful campaign spec (rule 64.7): the Axis auto-wins by occupying every
    hex of Alexandria AND Cairo and HOLDING them for one full Game-Turn (64.71) -- the hold is
    the rule's own clause, so a Delta hex retaken inside that turn denies the win outright
    rather than postponing it. Failing that, the war runs its span and is counted on the 64.73
    geographic Victory-Point table, graded by 64.76. Rule 64.7 defines NO annihilation clause
    and this spec invents none: a side whose last counter dies does not lose on the instant,
    the campaign is still settled on the tally. DEFERRED, not silently missing: the book's
    other automatic end (64.72's Game-Turn-35 Commonwealth win) and 64.71's other half (the
    <=90 truck-MP line of supply back to a Tobruk/Tripoli-fed dump) -- see game.campaign_victory
    for the model and its full deferred list. `max_turns` truncates the run (default the full
    GT111) -- a shorter slice for fast tests or a single-season study."""
    tmap, _ = cna_map.load_sections("ABCDE")
    target = coords.to_axial(coords.parse(_ALEXANDRIA))
    max_turns = max_turns or calendar.FINAL_GT
    # C2: the real September-1940 order of battle -- the Italian 10th Army (extraction +
    # rule-60.31 gap-fill) vs the Western Desert Force -- with the historical reinforcement
    # flow (rule 20 / [4.43b]/[4.43a]): Rommel and the DAK arrive from Tripoli from GT20, the
    # 8th Army builds up from Cairo, across the whole GT1..111 span.
    units, oob_supplies = oob.build(oob_file="oob_italian.json", extra_file="oob_campaign_extra.json",
                                    sections="ABCDE", reinforcements_file="reinforcements_campaign.json",
                                    dump_pools=oob.CAMPAIGN_DUMP_POOLS,   # 64.3: the full campaign uses Section 60
                                    first_line=oob.CAMPAIGN_FIRST_LINE)   # 53.11: [60.31]/[60.41] first-line trucks
    # C3: the supply economy -- the Commonwealth's inexhaustible Suez base (Cairo/Alexandria),
    # the Axis port-of-arrival dump (Benghazi) the Mediterranean convoys land at, and the
    # historical coastal staging dumps (60.34) the campaign truck relay hauls forward along.
    # BOTH armies get a spine: the Axis one runs east from Benghazi, the Commonwealth one west
    # from the rail-fed Mersa Matruh railhead (60.7) to the Compass Field Supply Depots. Without
    # its own, the Western Desert Force cannot sustain an offensive one hex past the wire.
    dumps = (tuple(oob_supplies) + tuple(_campaign_cw_base())
             + (_campaign_axis_base(), _campaign_tobruk_dump())
             + tuple(_campaign_staging_dumps()) + tuple(_campaign_cw_depots()))
    # C6 / [36.0] THE AIR FACILITIES, and the dumps rule 36.17 says they ARE. The OOB has carried
    # these counters since Phase 3.1 and discarded their meaning; they are now installations with a
    # Capacity Level (36.12/36.2/36.3/36.4) that bombing takes down (36.14/41.36) and that gates how
    # many SGSUs can function (36.13). Their supply is the [60.34]/[60.44] air allotment -- 1200
    # Ammo / 850 Fuel / 100 Stores / 100 Water for the Axis, 200/250/50 for the Commonwealth -- which
    # 59.61 kept off the board while the Air Game was abstract. It is flagged air_dump, so ONLY the
    # SGSUs standing on it may eat it (35.14): it is the air force's larder, not the army's.
    facilities = oob.air_facilities(oob_file="oob_italian.json",
                                    extra_file="oob_campaign_extra.json", sections="ABCDE")
    air_supply = tuple(oob.air_dumps(facilities, oob.CAMPAIGN_AIR_POOLS))
    # [35.11]/[60.31]/[60.42] ...and the SQUADRON BASES that stand on them. The campaign order of
    # battle ships no SGSU counter at all, while [60.31] charts 39 Italian and [60.42] 14
    # Commonwealth "available" for placement "at any air facility, within the capacity of that
    # facility" -- so without this the whole of rule 35 would be inert in the campaign and the air
    # supply above would have no one to feed. Each facility takes SGSUs up to its Capacity Level.
    units += oob.seed_sgsus(facilities, oob.CAMPAIGN_SGSU_AVAILABLE)
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
    for piece in (*units, *dumps, *water_sources, *air_supply):
        terrain.setdefault(piece.hex, Terrain.CLEAR)
    _connect_pieces(terrain, [p.hex for p in (*units, *dumps, *water_sources, *air_supply)])
    forts = _apply_major_cities(terrain)
    for h in delta_hexes():                          # rule 57 + 25.12: the Delta, at Level 3
        terrain[h] = Terrain.MAJOR_CITY
        forts[h] = _DELTA_FORT
    # Benghazi is a city: stamp its terrain MAJOR_CITY (unlimited 54.12 dump capacity), so the Axis
    # port-of-arrival dump no longer clips the convoy to a 5000-fuel Other-Terrain ceiling and the
    # designed 55.3 port tonnage becomes the sole gate. Terrain only -- NOT added to _MAJOR_CITIES,
    # so no 15.82 no-eviction fort is granted at the Axis rear.
    terrain[coords.to_axial(coords.parse(_AXIS_PORT_HEX))] = Terrain.MAJOR_CITY
    tmap = replace(tmap, terrain=terrain, fortifications=forts)

    # THE WESTERN DESERT RAILWAY (rule 54.3), laid over the FINAL land map so it walks real hexes
    # and invents no terrain. ONE corridor (game.wells.corridor), read TWICE, because the rulebook
    # says the rails and the pipeline are the same hexes:
    #   * as the rails edge-set (54.3), which is what the railway HAULS freight along -- 1500 tons
    #     of ONE commodity per Operations Stage (54.32/54.33), unloaded at a hex (54.35) into a
    #     dump (54.11). That is engine._rail_stops, and it is the half that was missing: the lane
    #     used to land its whole haul on the Mersa Matruh railhead and leave every other station on
    #     four hundred miles of line at ZERO, so the Eighth Army could not eat on its own railway.
    #   * as the water pipeline (52.22/52.23), which needs no train at all -- an RR hex simply IS
    #     "a source of water similar to a major city", unlimited and undepletable.
    # Commonwealth-only: the Axis may not use the defunct Barce-Benghazi railroad (52.22), and its
    # 54.4 right to run rolling stock over CAPTURED Commonwealth rail (five contiguous controlled
    # hexes + 250 Stores/100 Fuel imported as locomotives) is DEFERRED and flagged -- the Axis
    # hauls by lorry from Benghazi, which is the historical asymmetry, not a thumb on the scale.
    rail_corridor = wells.corridor(tmap.terrain)
    tmap = replace(tmap, rails=frozenset(edge(a, b) for a, b
                                         in zip(rail_corridor, rail_corridor[1:])))
    water_sources += wells.pipeline(tmap.terrain)
    # [24.6]/[24.67] ...AND THE ROUTE IT MAY BE FINISHED ALONG. The line "extends towards Mersa
    # Matruh (eventually to be completed at TOBRUK)", and the two New Zealand Railroad Construction
    # companies are the only units in the game that may lay it (24.61). Surveyed here, built hex by
    # westward hex by game.engine._construction; the Axis has no railway construction at all, which
    # is the rulebook's asymmetry and not ours (see game.construction).
    rail_line = wells.rail_survey(tmap.terrain)

    # THE 54.12 VILLAGE ROW (see game.villages). Read off the FINAL map, so every hex stamped
    # MAJOR_CITY above -- Tobruk, Bardia, Benghazi, Cairo, Alexandria -- keeps its unlimited city
    # ceiling and the named villages beneath it get theirs. This is a LOCATION overlay: it moves
    # no unit, shifts no combat and fortifies nothing (8.37 / 25.12); it raises the dump ceiling of
    # the hexes the whole logistics chain stands on. Campaign-only, so the byte-locked benchmark
    # scenarios keep reading the Other-Terrain row (state.villages defaults empty).
    village_hexes = villages.village_hexes(tmap.terrain)

    # [24.9] THE SUPPLY LINE IS CONSTRUCTED; THE ARMY'S MOBILE DUMPS ARE NOT. Rule 24.9's Note makes
    # a constructed dump the only kind a truck "in convoy" may LOAD from -- the difference between a
    # LINK in a bucket brigade and a one-way sink. The places ON the line are constructed depots and
    # always were: the 60.34 Axis staging chain, the 60.44 Commonwealth Field Supply Depots and rail
    # stations, the ports of arrival, and the rule-57 bases (54.11: "all major cities are natural
    # supply dumps"). The FIELD dumps the OOB rides the armies in with are not -- they are the
    # mobile supply that follows the division (32.3), and a lorry that carries a division's stock
    # back off it has done negative work (measured; see campaign_policy._relay_source).
    #
    # Which is what makes 24.9 a DECISION rather than a formality: an army that wants its forward
    # dump to become a link in the chain must stop and build it -- 3 Capability Points and 20 Store
    # Points, by any one TOE Strength Point standing on it.
    dumps = tuple(d if d.id.startswith(_MOBILE_DUMPS) else replace(d, constructed=True)
                  for d in dumps)

    # The wells go in the supplies tuple LAST, and the convoy/port/truck geography below is
    # derived from `dumps` (the armies' depots) ALONE. A well is geography, not a depot: it is
    # not a port of arrival, no convoy lands in it, and no truck reloads from it. Feeding the
    # wells to _axis_rear would hand "the rearmost Axis dump" -- the Benghazi harbour the whole
    # Mediterranean convoy lands at -- to the well out at Jalo oasis. Order matters for the same
    # reason: the policies' co-located-dump scans take the FIRST dump on a hex, and every one of
    # Benghazi/Tobruk/Bardia/Derna/Cairo/Alexandria carries both a depot and a well.
    #
    # The air-facility dumps (36.17) go in for exactly the same reason and with the same care: they
    # are supply the SGSUs eat, so they belong in `supplies` and in the conservation base, but they
    # are not depots on the freight line, so they are kept out of `dumps` and out of every geography
    # derived from it.
    supplies = dumps + water_sources + air_supply

    # 64.2 / 64.51: General Rommel (the rule-31 entity) reaches Africa at the 3rd OpStage of
    # Game-Turn 26 -- co-located with the DAK headquarters counter he lands beside, so the leader
    # and his headquarters arrive together at the same entry hex rather than at an invented spot.
    # Until then state.rommel is None; game.engine._rommel_arrival lifts him onto the board there,
    # and from GT27's 7.14 determination the Axis reads the [7.2] rating-6 row.
    rommel_entry = next(u.hex for u in units if u.formation == "GE DAK")

    return GameState(
        turn=1, max_turns=max_turns, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="normal", vp=VP(),
        terrain=tmap, control=_campaign_initial_control(), units=tuple(units), target_hex=target,
        allied_objective=coords.to_axial(coords.parse(_CW_OBJECTIVE)),   # offensive CW drives west (Compass)
        supplies=supplies, consumed=_zero_consumed(),
        initial_supply=_initial_supply(supplies, units),
        villages=village_hexes,                          # 54.12: the missing capacity row
        dump_capture=True,                               # 32.13/54.15: a dump entered is a dump taken
        # [32.32] THE DESERT COLUMN'S PRICE -- BUILT, TESTED, AND MEASURED OFF. This is not an
        # oversight and it is not balance: the rule is implemented in full (game.engine._organization,
        # game.supply.MOTORIZATION_POINTS, tests/test_motorization.py) and turning it on here breaks
        # the campaign. Measured, all five seeds:
        #
        #   * Commonwealth freight delivered COLLAPSES 62% (440,293 -> 167,853 supply points, seed
        #     1941) while the Axis loses 2.7% and does not change its depot movement AT ALL (55 -> 54).
        #     The rule is a Commonwealth-only tax, because the Commonwealth is the side whose whole
        #     operational method IS the lorried dump (60.34), and its charted Medium park buys FOUR
        #     columns (130 Points / 30).
        #   * Eight behaviour tests fail, among them "the Commonwealth can mount a supplied offensive"
        #     and "the haul reaches the front" -- six slices of work undone.
        #   * And it does not even move the lean it was meant to move: Axis 4/5 before, Axis 4/5 after.
        #
        # WHY, and this is the finding: 32.32 prices a SCARCE COUNTER, and our engine has an ABUNDANT
        # PILE POPULATION. In the abstract game a Supply Unit is a counter a player owns a handful of
        # (32.41-32.47, and 32.14 caps them 5 per city), so thirty Motorization Points each is
        # affordable. In the full Logistics Game, 54.11 ("any hex can be used as a supply dump") plus
        # truck-unload dump creation plus 24.9 construction leaves DOZENS of dumps on the map and the
        # leapfrog wants several marching every OpStage. Thirty Medium Truck Points apiece against a
        # 130-Point park is bankrupt on the first turn. Section 32's own General Rule is the warning
        # we walked past: it applies "if the Players are playing the Land Game WITHOUT the Air and
        # Logistics Games". The two systems are alternatives. The price cannot be imported without the
        # population it was priced for.
        motorized_supply=False,                          # 32.32: thirty Medium Truck Points per desert
                                                         # column, out of the SAME 60.33/60.43 park that
                                                         # hauls the freight -- we took 32.33's permission
                                                         # and never paid its price. See game.state.
        rail_line=rail_line,                             # 24.6/24.67: the route west the NZRRC may build
        map_sections=frozenset("ABCDE"),
        season_offset=calendar.CAMPAIGN_SEASON_OFFSET,   # GT1 = September 1940 (fall)
        initiative_fixed=Side.AXIS, initiative_fixed_until=1,   # 64.4->60.6: the Italians hold Game-Turn 1
        initiative_chart=True,                                  # [7.2] date+presence ratings (game.initiative)
        rommel_arrival=RommelArrival(turn=26, stage=3, hex=rommel_entry),   # 64.2: the Desert Fox lands
        victory=campaign_victory.CampaignVictory(),      # rule 64.7 (see game.campaign_victory)
        convoys=_campaign_convoys(dumps, target, max_turns, seed),      # C3: Axis Med + CW rail (56.4/60.7)
        ports=_campaign_ports(dumps, target),                           # C3: PORT-Benghazi + PORT-Matruh
        trucks=(_campaign_axis_trucks(dumps, target, facilities)        # C3-2: the Benghazi->front haul (53/60.33)
                + _campaign_cw_trucks(dumps, facilities)),              # and the CW railhead->west haul (60.33)
        interdictions=(_campaign_malta_interdiction(max_turns)             # C4: Malta throttles the Axis Med convoy (rule 44)
                       + _campaign_tobruk_ferry_interdiction(max_turns)    # + BOTH halves of the Tobruk sea duel
                       + _campaign_tobruk_axis_interdiction(max_turns)),   #   (30/41.6): each side can fight the other's lane
        air=_campaign_air(),                                # C4: BOTH air forces (34/40-46) -- without
        air_missions=_campaign_air_missions(max_turns),     # them no harbour can ever be cut (41.39B)
        air_facilities=tuple(facilities),                   # C6/36: the squadron bases on the map
    )
