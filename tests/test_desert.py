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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.engine import _mandatory_retreat, _retreat, _Run              # noqa: E402
from game.events import EventKind, Phase, Side                          # noqa: E402
from game.hexmap import distance                                        # noqa: E402
from game.movement import TerrainMap                                    # noqa: E402
from game.state import GameState, StepRecord, Unit, VP                  # noqa: E402
from game.terrain import Mobility, Terrain                              # noqa: E402


def _unit(uid, side, hex_, *, mob=Mobility.FOOT, oca=4, dca=2, strength=6, ammo=100000):
    return Unit(uid, side, hex_, (StepRecord("s", strength),), mobility=mob, cpa=10,
                stacking_points=1, oca=oca, dca=dca, ammo=ammo, morale=3, cohesion=0)


def _run(units, terrain: dict, target, *, seed=1):
    st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=seed,
                   weather="clear", vp=VP(), terrain=TerrainMap(terrain=terrain), control={},
                   units=tuple(units), target_hex=target, supplies=(),
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
