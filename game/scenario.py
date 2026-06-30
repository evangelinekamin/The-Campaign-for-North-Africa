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

from .events import Phase, Side
from .movement import TerrainMap, edge
from .state import GameState, StepRecord, Unit, VP
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

    return GameState(
        turn=1, max_turns=MAX_TURNS, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=seed, weather="clear", move_modifier=0, vp=VP(),
        terrain=tmap, control={}, units=units, target_hex=target,
    )
