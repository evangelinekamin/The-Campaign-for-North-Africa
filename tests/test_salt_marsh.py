"""RULE [8.44] SALT MARSH -- the gate that makes the Qattara Depression a barrier.

Verbatim off the scan (PDF page 15; [8.37] chart note 2 on page 70 restates it):

    "Vehicles, except for Light Trucks, Recce-type units, and motorcycle infantry may enter or
     leave a Salt Marsh hex only on a Road or Track. A prohibited vehicle that enters a Salt Marsh
     hex without using the Track, whatever the reason, is Abandoned (see 5.33). Because most
     vehicles are prohibited from entering Salt Marshes in a normal manner, no motorized unit or
     AFV (tank, armored car, etc.) may ever engage in Assault with units defending in a Salt Marsh
     hex. The one camel unit in the game (the Italian Meharisti Camel Cavalry) travels as infantry
     in non-track Salt Marsh hexes, as these hexes could not support loaded camels."

WHY THIS RULE IS LOAD-BEARING AND NOT GARNISH. The [8.37] chart prices Salt Marsh at 2 CP for a
motorized unit -- CHEAPER than the DESERT (4) and ROUGH (4) that ring the Depression, at a quarter
of the rough's Breakdown Value and a sixth of the desert's. Put 270 salt-marsh hexes on the map
WITHOUT this gate and the one piece of ground that historically stopped an army becomes the best
tank road on the board: measured on the live map before the gate, the cheapest motorized crossing
of the Depression (D1215 -> D2430, 40 CP) ran twelve consecutive hexes THROUGH the marsh. With the
gate the same vehicle pays 46 CP on a path with zero marsh hexes -- it goes around, which is the
whole point -- while infantry still cuts through for 44.

The pure-chart half of the rule lives with the other chart goldens (tests/test_terrain.py's
salt_marsh_barred, tests/test_movement.py's step_cost gate). This file holds the ENGINE half: the
Close-Assault prohibition, and the forced-relocation paths that would otherwise smuggle a barred
vehicle into a marsh with no movement point ever being spent.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.engine import _mandatory_retreat, _resolve_combat, _retreat, _Run   # noqa: E402
from game.events import EventKind, Phase, Side                           # noqa: E402
from game.hexmap import distance                                          # noqa: E402
from game.movement import TerrainMap                                     # noqa: E402
from game.state import GameState, StepRecord, Unit, VP                   # noqa: E402
from game.terrain import Mobility, Terrain                               # noqa: E402


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


def _field(marsh=frozenset()) -> dict:
    """A small blob around the origin; every hex CLEAR except the named salt marshes."""
    hexes = {(q, r) for q in range(-3, 4) for r in range(-3, 4)}
    return {h: (Terrain.SALT_MARSH if h in marsh else Terrain.CLEAR) for h in hexes}


# --- the Close-Assault prohibition ---------------------------------------------------------------

def test_a_tank_may_not_assault_a_defender_in_a_salt_marsh():
    """"no motorized unit or AFV (tank, armored car, etc.) may ever engage in Assault with units
    defending in a Salt Marsh hex" -- the sole attacker is barred, so no armed attacker is left and
    the assault is REJECTED without spending a round of ammunition (the same shape as the 52.51
    water gate: barred before _charge_ammo, never after)."""
    dfn = _unit("D", Side.ALLIED, (0, 0))
    tank = _unit("T", Side.AXIS, (1, 0), mob=Mobility.VEHICLE)
    r = _run([tank, dfn], _field(marsh={(0, 0)}), (0, 0))
    assert _resolve_combat(r, Side.AXIS, "AXIS/Front", [tank], [dfn], (0, 0), set(), set()) is False
    rejected = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert rejected and "8.44" in rejected[0].payload["reason"]
    assert tank.ammo == 100000                       # the barred unit never spent its load


def test_infantry_may_still_assault_into_a_salt_marsh():
    """The prohibition is on VEHICLES. Foot infantry assaults the marsh normally -- which is what
    makes the Depression an infantryman's barrier and an armoured army's wall."""
    dfn = _unit("D", Side.ALLIED, (0, 0))
    foot = _unit("I", Side.AXIS, (1, 0), mob=Mobility.FOOT)
    r = _run([foot, dfn], _field(marsh={(0, 0)}), (0, 0))
    assert _resolve_combat(r, Side.AXIS, "AXIS/Front", [foot], [dfn], (0, 0), set(), set()) is True


def test_a_mixed_stack_assaults_with_its_infantry_only():
    """A combined attack drops just the barred units, exactly as the 15.21 anti-armor filter does:
    the assault resolves, and the tank contributes nothing to it."""
    dfn = _unit("D", Side.ALLIED, (0, 0))
    tank = _unit("T", Side.AXIS, (1, 0), mob=Mobility.VEHICLE)
    foot = _unit("I", Side.AXIS, (1, 0), mob=Mobility.FOOT)
    r = _run([tank, foot, dfn], _field(marsh={(0, 0)}), (0, 0))
    assert _resolve_combat(r, Side.AXIS, "AXIS/Front", [tank, foot], [dfn], (0, 0),
                           set(), set()) is True
    resolved = [e for e in r.events if e.kind == EventKind.COMBAT_RESOLVED][0].payload
    assert resolved["attackers"] == ["I"]


def test_a_motorized_unit_may_not_assault_OUT_of_a_salt_marsh_either():
    """[8.37] note 2 states the same case more widely than the rule body does -- "Motorized units
    may not engage in combat into/out of a Salt Marsh (Case 8.44)" -- so a motorized unit standing
    IN the marsh cannot close out of it either. Both are printed text; both are honoured."""
    dfn = _unit("D", Side.ALLIED, (0, 0))
    tank = _unit("T", Side.AXIS, (1, 0), mob=Mobility.VEHICLE)
    r = _run([tank, dfn], _field(marsh={(1, 0)}), (0, 0))        # the ATTACKER is in the marsh
    assert _resolve_combat(r, Side.AXIS, "AXIS/Front", [tank], [dfn], (0, 0), set(), set()) is False


def test_the_light_classes_are_exempt_from_movement_but_not_from_the_assault_ban():
    """The [8.44] exemption is an exemption from the MOVEMENT ban only. Its sentence on assault
    says "no motorized unit or AFV", with no exception list at all -- so a Recce unit that may
    legally drive into the marsh still may not assault into it."""
    dfn = _unit("D", Side.ALLIED, (0, 0))
    recce = _unit("R", Side.AXIS, (1, 0), mob=Mobility.RECCE)
    r = _run([recce, dfn], _field(marsh={(0, 0)}), (0, 0))
    assert _resolve_combat(r, Side.AXIS, "AXIS/Front", [recce], [dfn], (0, 0), set(), set()) is False


# --- the forced-relocation gate -------------------------------------------------------------------

def test_a_retreat_does_not_shove_a_barred_vehicle_into_a_marsh():
    """[15.82]'s retreat walks raw hex adjacency, not movement.step_cost, so without an explicit
    legality gate it would push a tank into ground the tank may not enter -- and then, under this
    same rule, the tank could never leave it. tactics.may_step_into keeps the retreat on legal
    ground: here exactly one of the hexes away from the attacker is not marsh, and the stack takes
    it (the alternative reading -- push it in and Abandon it per 5.33 -- needs a 5.33 the engine
    does not have; see tactics.may_step_into)."""
    # Attacker at (-1, 0): the hexes FARTHER from it are (1, 0), (1, -1) and (0, 1), and the
    # retreat's own deterministic tiebreak would otherwise take (0, 1) -- so barring (0, 1) and
    # (1, -1) forces the gate to actually decide the destination, rather than agreeing with the
    # order the picker was going to choose anyway.
    tank = _unit("T", Side.ALLIED, (0, 0), mob=Mobility.VEHICLE)
    r = _run([tank], _field(marsh={(0, 1), (1, -1)}), (0, 0))
    _retreat(r, Side.AXIS, "AXIS/Front", ["T"], (-1, 0), 1)
    assert r.state.unit("T").hex == (1, 0)
    # ...and the same retreat with the gate's terrain removed is the one that would have gone to
    # (0, 1): the assertion above is the gate, not the tiebreak.
    control = _run([_unit("T", Side.ALLIED, (0, 0), mob=Mobility.VEHICLE)], _field(), (0, 0))
    _retreat(control, Side.AXIS, "AXIS/Front", ["T"], (-1, 0), 1)
    assert control.state.unit("T").hex == (0, 1)


def test_a_retreat_with_only_marsh_behind_it_costs_losses_not_an_illegal_move():
    """When EVERY hex away from the attacker is barred marsh, the retreat simply cannot be made:
    the stack stays put and pays [15.82]'s 10% for the un-retreated hex. That is the existing
    no-room branch, reached for a new and faithful reason."""
    tank = _unit("T", Side.ALLIED, (0, 0), mob=Mobility.VEHICLE, strength=10)
    r = _run([tank], _field(marsh={(1, 0), (1, -1), (0, 1)}), (0, 0))
    _retreat(r, Side.AXIS, "AXIS/Front", ["T"], (-1, 0), 1)
    assert r.state.unit("T").hex == (0, 0)
    assert not [e for e in r.events if e.kind == EventKind.UNIT_RETREATED]
    losses = [e for e in r.events if e.kind == EventKind.STEP_LOST]
    assert losses and losses[0].payload["amount"] == 1        # ceil(10% of 10)


def test_the_mandatory_10_36_retreat_obeys_the_gate_too():
    """[10.36]'s three-hex forced retreat is the OTHER walker over raw adjacency. Ring the only
    hexes three distant from the anchor with marsh and a barred vehicle has no legal destination,
    so it surrenders in entirety (10.36e) -- while a foot unit in the identical position walks in
    and lives. Two rules meeting honestly: contact must be paid for, and the marsh is a wall."""
    field = _field()
    anchor = (-1, 0)
    ring = {h for h in field if distance(h, anchor) == 3}
    marsh_field = {h: (Terrain.SALT_MARSH if h in ring else Terrain.CLEAR) for h in field}

    tank = _unit("T", Side.AXIS, (0, 0), mob=Mobility.VEHICLE, strength=6)
    r = _run([tank], marsh_field, (0, 0))
    _mandatory_retreat(r, Side.AXIS, [r.state.unit("T")], anchor)
    assert not [e for e in r.events if e.kind == EventKind.UNIT_RETREATED]
    assert [e for e in r.events
            if e.kind == EventKind.STEP_LOST and e.payload["role"] == "surrender"]

    foot = _unit("F", Side.AXIS, (0, 0), mob=Mobility.FOOT, strength=6)
    r2 = _run([foot], marsh_field, (0, 0))
    _mandatory_retreat(r2, Side.AXIS, [r2.state.unit("F")], anchor)
    assert r2.state.unit("F").hex in ring


def test_infantry_retreats_into_the_marsh_normally():
    """The gate is per-mobility, not a blanket ban on the terrain: the same retreat with a foot
    unit takes the marsh hex the tank could not."""
    foot = _unit("F", Side.ALLIED, (0, 0), mob=Mobility.FOOT)
    r = _run([foot], _field(marsh={(1, 0), (1, -1), (0, 1)}), (0, 0))
    _retreat(r, Side.AXIS, "AXIS/Front", ["F"], (-1, 0), 1)
    assert r.state.unit("F").hex in {(1, 0), (1, -1), (0, 1)}
    assert r.state.terrain.terrain[r.state.unit("F").hex] == Terrain.SALT_MARSH
