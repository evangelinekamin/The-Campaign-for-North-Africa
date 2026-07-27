"""RULE [8.45] DESERT -- the last-mile gate that seals Alamein.

Verbatim off the scan (PDF page 15; [8.37] chart note 3 on page 70 restates it):

    "Desert hexes... are forbidden to Light Trucks, Motorcycle infantry, and motorcycle Recce
     units whose weight was not sufficient enough to provide the traction necessary for moving
     vehicles through the soft surface. Such units may not enter any Desert hexes, whether
     traversed by Tracks or not."

Unlike [8.44] Salt Marsh, [8.45] carries no Close-Assault prohibition and no Abandonment clause --
its printed text is a bare movement-entry bar, so its whole engine-facing surface is
movement.step_cost's gate (tests/test_terrain.py's desert_barred, tests/test_movement.py's
step_cost gate) plus the forced-relocation path this file covers. Where [8.44]'s gate reads BOTH
ends of the edge and opens for a Road OR a Track, [8.45]'s reads only the DESTINATION and opens for
neither -- see the DESERT_BARRED comment in game/terrain.py for why the two rules, two paragraphs
apart in the same rulebook chapter, were transcribed to different shapes rather than one being
copied from the other.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import supply                                                 # noqa: E402
from game.engine import _mandatory_retreat, _retreat, _Run              # noqa: E402
from game.events import EventKind, Phase, Side                          # noqa: E402
from game.hexmap import distance                                        # noqa: E402
from game.movement import TerrainMap                                    # noqa: E402
from game.state import GameState, StepRecord, TruckFormation, Unit, VP  # noqa: E402
from game.terrain import Mobility, Terrain                              # noqa: E402


def _unit(uid, side, hex_, *, mob=Mobility.FOOT, oca=4, dca=2, strength=6, ammo=100000):
    return Unit(uid, side, hex_, (StepRecord("s", strength),), mobility=mob, cpa=10,
                stacking_points=1, oca=oca, dca=dca, ammo=ammo, morale=3, cohesion=0)


def _zoc_unit(mobility, *, stacking_points=5, raw_defense=30):
    """The duck-typed shape game.zoc reads (its ZocUnit protocol), not a full Unit."""
    return SimpleNamespace(mobility=mobility, stacking_points=stacking_points,
                           raw_defense=raw_defense, cohesion=0, is_combat=True)


def _run(units, terrain: dict, target, *, seed=1, trucks=()):
    st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=seed,
                   weather="clear", vp=VP(), terrain=TerrainMap(terrain=terrain), control={},
                   units=tuple(units), target_hex=target, supplies=(), trucks=tuple(trucks),
                   consumed={"AMMO": 0, "FUEL": 0, "STORES": 0, "WATER": 0},
                   initial_supply={"AMMO": sum(u.ammo for u in units), "FUEL": 0,
                                   "STORES": 0, "WATER": 0})
    return _Run(st)


def _field(desert=frozenset()) -> dict:
    """A small blob around the origin; every hex CLEAR except the named desert hexes."""
    hexes = {(q, r) for q in range(-3, 4) for r in range(-3, 4)}
    return {h: (Terrain.DESERT if h in desert else Terrain.CLEAR) for h in hexes}


def test_a_retreat_does_not_shove_a_barred_light_truck_into_desert():
    """[15.82]'s retreat walks raw hex adjacency, not movement.step_cost, so without
    tactics.may_step_into it would push a Light Truck into ground it may never enter."""
    truck = _unit("T", Side.ALLIED, (0, 0), mob=Mobility.LIGHT_TRUCK)
    r = _run([truck], _field(desert={(0, 1), (1, -1)}), (0, 0))
    _retreat(r, Side.AXIS, "AXIS/Front", ["T"], (-1, 0), 1)
    assert r.state.unit("T").hex == (1, 0)
    # ...and the same retreat with the gate's terrain removed would have taken (0, 1) instead --
    # the assertion above is the gate, not the deterministic tiebreak.
    control = _run([_unit("T", Side.ALLIED, (0, 0), mob=Mobility.LIGHT_TRUCK)], _field(), (0, 0))
    _retreat(control, Side.AXIS, "AXIS/Front", ["T"], (-1, 0), 1)
    assert control.state.unit("T").hex == (0, 1)


def test_the_mandatory_10_36_retreat_obeys_the_desert_gate_too():
    """[10.36]'s three-hex forced retreat is the other walker over raw adjacency. Ring the only
    hexes three distant from the anchor with desert and a barred motorcycle unit has no legal
    destination, so it surrenders in entirety (10.36e) -- while an ordinary vehicle in the
    identical position, ungated by [8.45], walks in and lives."""
    field = _field()
    anchor = (-1, 0)
    ring = {h for h in field if distance(h, anchor) == 3}
    desert_field = {h: (Terrain.DESERT if h in ring else Terrain.CLEAR) for h in field}

    cycle = _unit("M", Side.AXIS, (0, 0), mob=Mobility.MOTORCYCLE, strength=6)
    r = _run([cycle], desert_field, (0, 0))
    _mandatory_retreat(r, Side.AXIS, [r.state.unit("M")], anchor)
    assert not [e for e in r.events if e.kind == EventKind.UNIT_RETREATED]
    assert [e for e in r.events
            if e.kind == EventKind.STEP_LOST and e.payload["role"] == "surrender"]

    tank = _unit("V", Side.AXIS, (0, 0), mob=Mobility.VEHICLE, strength=6)
    r2 = _run([tank], desert_field, (0, 0))
    _mandatory_retreat(r2, Side.AXIS, [r2.state.unit("V")], anchor)
    assert r2.state.unit("V").hex in ring


def test_a_light_truck_already_standing_in_desert_may_still_leave():
    """[8.45] bars only ENTRY -- unlike [8.44]'s enter-or-leave -- so a retreat that starts a
    barred unit already inside a Desert hex is free to move it into ordinary Clear ground."""
    truck = _unit("T", Side.ALLIED, (0, 0), mob=Mobility.LIGHT_TRUCK)
    r = _run([truck], _field(desert={(0, 0)}), (0, 0))
    _retreat(r, Side.AXIS, "AXIS/Front", ["T"], (-1, 0), 1)
    assert r.state.unit("T").hex != (0, 0)
    assert [e for e in r.events if e.kind == EventKind.UNIT_RETREATED]


# --- the rule's OWN named consumer: a Light Truck CONVOY ---------------------------------------
# The [8.45] review's first finding, and the reason the gate looked dormant when it was not: a
# TruckFormation is the only Light Truck this engine builds, and supply.reachable_truck_moves used
# to path EVERY convoy at SUPPLY_MOBILITY (Medium), so a light convoy was routed around BOTH
# class rules at once -- denied [8.44]'s Salt Marsh exemption and granted [8.45]'s Desert. The
# two assertions below are one rule each, on one convoy, and they point in OPPOSITE directions:
# that is what makes them a test of the truck's CLASS rather than of any single gate.

def _convoy_field():
    """Three hexes in a row from the convoy's start: Clear, then Salt Marsh, then Desert, with no
    road and no track anywhere -- the only surface on which [8.44] and [8.45] both bite."""
    field = {h: Terrain.CLEAR for h in {(q, r) for q in range(-2, 3) for r in range(-2, 3)}}
    field[(1, 0)] = Terrain.SALT_MARSH
    field[(2, 0)] = Terrain.DESERT
    return field


def _convoy_reach(truck_class):
    truck = TruckFormation("T", Side.AXIS, (0, 0), truck_class, points=10)
    r = _run([], _convoy_field(), (0, 0), trucks=[truck])
    return supply.reachable_truck_moves(r.state, r.state.truck("T"))


def test_a_light_convoy_carries_its_own_8_44_and_8_45_class_rules():
    light, medium = _convoy_reach("light"), _convoy_reach("medium")

    # [8.45]: "Desert hexes are forbidden to Light Trucks... Such units may not enter any Desert
    # hexes, whether traversed by Tracks or not." A Medium convoy is not named and may.
    assert (2, 0) not in light
    assert (2, 0) in medium

    # [8.44]: "Vehicles, EXCEPT FOR LIGHT TRUCKS, Recce-type units, and motorcycle infantry may
    # enter or leave a Salt Marsh hex only on a Road or Track." The exemption is the Light Truck's
    # and this field has neither surface, so the Medium convoy is the one shut out.
    assert (1, 0) in light
    assert (1, 0) not in medium


def test_a_barred_class_projects_no_zoc_into_the_desert_it_may_not_enter():
    """[10.21]c, and this is the rule ASKING for the coupling, not a side effect of sharing a
    function: "ZOC's do not extend into any adjacent hex into which the unit wishing to exert the
    ZOC could not enter from its present location. (Example: a Tank Battalion could not exert a ZOC
    into a Salt Marsh hex unless there was a Track or Road connecting the two hexes.)" Since
    game.zoc.zoc_extends asks movement._step_cost_known_adjacent, [8.45] reaches ZOC for free --
    and now that the 15th Kradschutzen Bn is a live MOTORCYCLE combat unit, it is worth pinning."""
    from game import zoc
    from game.movement import TerrainMap

    tmap = TerrainMap(terrain=_field(desert={(1, 0)}))
    stack = [_zoc_unit(Mobility.MOTORCYCLE), _zoc_unit(Mobility.MOTORCYCLE)]
    assert (1, 0) not in zoc.controlled_from(stack, (0, 0), tmap)
    assert (0, 1) in zoc.controlled_from(stack, (0, 0), tmap)          # ordinary ground, controlled
    tanks = [_zoc_unit(Mobility.VEHICLE), _zoc_unit(Mobility.VEHICLE)]
    assert (1, 0) in zoc.controlled_from(tanks, (0, 0), tmap)          # not a class [8.45] names


def test_a_light_convoy_accrues_breakdown_over_the_path_it_actually_drove():
    """supply.truck_bp_for_move reconstructs the min-CP path to charge 21.21 Breakdown over it, so
    it must reconstruct at the SAME mobility reachable_truck_moves pathed at -- otherwise the
    accrual is billed over a route the convoy was never allowed to take. Asking it for the Desert
    hex the class may not enter must therefore yield no path at all, not a phantom one."""
    truck = TruckFormation("T", Side.AXIS, (0, 0), "light", points=10)
    r = _run([], _convoy_field(), (0, 0), trucks=[truck])
    assert supply.truck_bp_for_move(r.state, r.state.truck("T"), (2, 0)) == 0.0
    # ...while the Salt Marsh hex [8.44] does open to it is reached, and charged, for real:
    # 54.2's off-road +1 Breakdown Point is a Light-Truck-only penalty, so a positive accrual here
    # is also proof the reconstruction ran at LIGHT_TRUCK and not at Medium.
    assert supply.truck_bp_for_move(r.state, r.state.truck("T"), (1, 0)) > 0.0
