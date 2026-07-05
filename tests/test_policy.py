"""Tests for the scripted policy's defender (game.policy.ScriptedPolicy).

The defender must be worth fighting: a mobile RESERVE sorties out to strike an
EXPOSED enemy stack (unsupported armor, or cut off from ammo) while the garrison
ANCHOR never vacates the objective. With nothing exposed it holds -- the tragedy
(a sally that butchers unsupported panzers) must EMERGE from these primitives,
never be hand-scripted into recklessness.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.events import Phase, Side
from game.hexmap import distance
from game.policy import MoveOrder, ScriptedPolicy
from game.scenario import coastal_corridor
from game.state import StepRecord, Unit
from game.terrain import Mobility

EXPOSED_HEX = (5, 0)  # a neighbour of the reserve at (6,0); on the corridor map


def _defender_state_with_exposed_tank():
    """Corridor, MOVEMENT phase, with an UNSUPPORTED Axis tank alone at (5,0)
    (reachable by the Commonwealth reserve UK-2Armd at (6,0)); the garrison
    UK-9Aus holds the objective. The Italian is removed so the only enemy stack
    is the exposed one."""
    base = replace(coastal_corridor(), phase=Phase.MOVEMENT)
    tank = Unit("AX-Tank", Side.AXIS, EXPOSED_HEX, (StepRecord("pz", 3),),
                mobility=Mobility.VEHICLE, cpa=20, stacking_points=2,
                oca=6, dca=6, is_tank=True)
    reserve = next(u for u in base.units if u.id == "UK-2Armd")   # (6,0)
    garrison = next(u for u in base.units if u.id == "UK-9Aus")   # on target
    return replace(base, units=(tank, reserve, garrison))


def test_reserve_sorties_toward_exposed_enemy_stack():
    state = _defender_state_with_exposed_tank()
    orders = ScriptedPolicy().movement(state, Side.ALLIED)

    assert orders, "the reserve should sortie against the exposed tank"
    assert all(isinstance(o, MoveOrder) for o in orders)
    sortie = next(o for o in orders if o.unit_id == "UK-2Armd")
    assert distance(sortie.to, EXPOSED_HEX) == 1  # ends adjacent, ready to assault


def test_anchor_never_vacates_the_objective():
    state = _defender_state_with_exposed_tank()
    policy = ScriptedPolicy()

    assert "UK-9Aus" in policy._anchor_ids(state, Side.ALLIED)
    moved = {o.unit_id for o in policy.movement(state, Side.ALLIED)}
    assert "UK-9Aus" not in moved  # the garrison holds the objective


def test_defender_holds_when_nothing_is_exposed():
    # Base corridor: both Axis units are supported and co-located with a dump,
    # so nothing is exposed -- the defender must not regress into recklessness.
    state = replace(coastal_corridor(), phase=Phase.MOVEMENT)
    assert ScriptedPolicy().movement(state, Side.ALLIED) == []
