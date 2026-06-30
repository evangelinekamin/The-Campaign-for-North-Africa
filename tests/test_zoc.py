"""Golden tests for Zones of Control (rule 10.0) and ZOC-aware movement."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import hexmap, zoc
from game.movement import TerrainMap, edge
from game.terrain import Hexside, Mobility, Terrain


@dataclass
class U:
    stacking_points: int = 5
    raw_defense: int = 30
    cohesion: int = 0
    is_combat: bool = True
    mobility: Mobility = Mobility.MOTORIZED


def field(radius: int = 3) -> TerrainMap:
    coords = [(q, r)
              for q in range(-radius, radius + 1)
              for r in range(-radius, radius + 1)
              if hexmap.distance((0, 0), (q, r)) <= radius]
    return TerrainMap(terrain={c: Terrain.CLEAR for c in coords})


# --- eligibility / exertion (10.11, 10.14, 10.15) ----------------------------

def test_single_battalion_does_not_exert():
    assert not zoc.hex_exerts_zoc([U(stacking_points=1, raw_defense=12)])


def test_two_battalions_exert():
    assert zoc.hex_exerts_zoc([U(stacking_points=1, raw_defense=12),
                               U(stacking_points=1, raw_defense=12)])


def test_division_alone_exerts():
    assert zoc.hex_exerts_zoc([U(stacking_points=5, raw_defense=30)])


def test_low_defense_does_not_exert():
    # > 1 stacking point but < 10 raw defensive close-assault points (10.15)
    assert not zoc.hex_exerts_zoc([U(stacking_points=2, raw_defense=4)])


def test_noncombat_and_broken_units_are_ineligible():
    assert not zoc.unit_eligible(U(is_combat=False))           # truck convoy / bare HQ
    assert not zoc.unit_eligible(U(cohesion=-26))              # 10.14


# --- projection / blocking (10.21) -------------------------------------------

def test_division_controls_all_six_neighbors_on_clear():
    ctrl = zoc.controlled_from([U()], (0, 0), field())
    assert ctrl == frozenset(hexmap.neighbors((0, 0)))


def test_escarpment_hexside_blocks_zoc_even_for_foot():
    # foot CAN cross an up-escarpment (cost), but ZOC still does not extend through it
    sides = {((0, 0), (1, 0)): Hexside.UP_ESCARPMENT}
    tmap = TerrainMap(terrain=field().terrain, hexsides=sides)
    ctrl = zoc.controlled_from([U(mobility=Mobility.FOOT)], (0, 0), tmap)
    assert (1, 0) not in ctrl
    assert (0, 1) in ctrl                                      # other neighbors fine


# --- ZOC-aware movement (10.23, 10.24, 10.26, 8.64) --------------------------

LINE = TerrainMap(terrain={(x, 0): Terrain.CLEAR for x in range(4)})  # (0,0)..(3,0)


def test_must_stop_on_entering_enemy_zoc():
    reach = zoc.reachable_with_zoc(LINE, (0, 0), budget=20, mobility=Mobility.VEHICLE,
                                   enemy_zoc=frozenset({(2, 0)}))
    assert (2, 0) in reach          # may enter
    assert (3, 0) not in reach      # but may not continue past it (10.23)


def test_friendly_unit_negates_enemy_zoc():
    reach = zoc.reachable_with_zoc(LINE, (0, 0), budget=20, mobility=Mobility.VEHICLE,
                                   enemy_zoc=frozenset({(1, 0)}),
                                   friendly_negators=frozenset({(1, 0)}))
    assert (3, 0) in reach          # negated ZOC no longer stops movement (10.26)


def test_break_off_cost_paid_when_starting_in_zoc():
    reach = zoc.reachable_with_zoc(LINE, (0, 0), budget=20, mobility=Mobility.VEHICLE,
                                   enemy_zoc=frozenset({(0, 0)}), break_off=2.0)
    assert reach[(0, 0)] == 2.0     # 8.64: pay to break off before moving
    assert reach[(1, 0)] == 2.0 + 2 # break-off + 2 CP to enter the clear hex


def test_enemy_occupied_hex_is_impassable():
    reach = zoc.reachable_with_zoc(LINE, (0, 0), budget=20, mobility=Mobility.VEHICLE,
                                   enemy_zoc=frozenset(),
                                   enemy_occupied=frozenset({(1, 0)}))
    assert (1, 0) not in reach and (2, 0) not in reach        # 8.13, corridor blocked
