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

from . import cna_map, coords
from .events import Phase, Side
from .movement import TerrainMap, edge
from .state import GameState, StepRecord, SupplyUnit, Unit, VP
from .terrain import Hexside, Mobility, Terrain

LENGTH = 8
MAX_TURNS = 8


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
