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

import game.supply as supply_mod
from game.events import Phase, Side
from game.hexmap import distance
from game.observation import _sighted_hexes
from game.policy import MoveOrder, ScriptedPolicy
from game.scenario import coastal_corridor
from game.state import StepRecord, SupplyUnit, Unit
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


def test_commonwealth_defender_wiring_is_not_the_footgun():
    # Regression guard for the ScriptedPolicy(attacker=...) footgun that silently
    # killed the garrison sortie in every benchmark/live game: the Commonwealth
    # defender MUST be built with the scenario's attacker (attacker=Side.AXIS), NOT
    # ScriptedPolicy(Side.ALLIED). The engine only ever calls the Commonwealth policy
    # with side=ALLIED, so attacker=ALLIED sends it down the attacker-advance branch
    # and _defender_moves never runs.
    state = _defender_state_with_exposed_tank()

    correct = ScriptedPolicy(attacker=Side.AXIS).movement(state, Side.ALLIED)
    assert any(o.unit_id == "UK-2Armd" and distance(o.to, EXPOSED_HEX) == 1
               for o in correct), "correct wiring: the reserve sorties"

    footgun = ScriptedPolicy(Side.ALLIED).movement(state, Side.ALLIED)
    assert correct != footgun, "the attacker= arg must change the Commonwealth's behavior"


# --- FIX 1: _is_exposed reads only LEGALLY-OBSERVABLE signals (rule 3.6) --------

def test_is_exposed_never_consults_enemy_private_supply(monkeypatch):
    """The important one: a legal commander cannot see the ENEMY's ammo/supply
    ledger, so _is_exposed must never call supply.plan_draw on it (nor read hidden
    TOE). Spy on plan_draw and assert it is not touched while judging exposure."""
    state = _defender_state_with_exposed_tank()
    policy = ScriptedPolicy()
    sighted = _sighted_hexes(state, Side.ALLIED)

    real = supply_mod.plan_draw
    calls: list = []

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(supply_mod, "plan_draw", spy)
    policy._is_exposed(state, Side.ALLIED, EXPOSED_HEX, sighted)
    assert calls == [], "_is_exposed must not read the enemy's private supply state"


def test_is_exposed_requires_the_stack_to_be_sighted():
    """Fog of presence: an enemy the side cannot SEE is never exposed to a sortie,
    however weak it really is."""
    state = _defender_state_with_exposed_tank()
    policy = ScriptedPolicy()
    assert policy._is_exposed(state, Side.ALLIED, EXPOSED_HEX,
                              _sighted_hexes(state, Side.ALLIED))
    assert not policy._is_exposed(state, Side.ALLIED, EXPOSED_HEX, frozenset())


def test_is_exposed_false_when_enemy_stack_has_visible_support():
    """A sighted stack with another enemy stack in an adjacent hex is SUPPORTED by
    what is visible -- not an isolated forward stack, so not exposed."""
    state = _defender_state_with_exposed_tank()
    supporter = Unit("AX-Inf", Side.AXIS, (4, 0), (StepRecord("inf", 3),),
                     mobility=Mobility.FOOT, cpa=10, stacking_points=2, oca=5, dca=5)
    state = replace(state, units=state.units + (supporter,))
    policy = ScriptedPolicy()
    sighted = _sighted_hexes(state, Side.ALLIED)
    assert EXPOSED_HEX in sighted
    assert not policy._is_exposed(state, Side.ALLIED, EXPOSED_HEX, sighted)


# --- FIX 2: the garrison anchor never counter-assaults OUT of the objective -----

def _combat_state_enemy_on_perimeter():
    """COMBAT phase: an Axis stack sits on the objective's perimeter (6,0), adjacent
    to BOTH the garrison anchor UK-9Aus on the objective (7,0) and the reserve
    UK-2Armd at (5,0). Both Commonwealth units are co-located with an ammo dump, so
    only the anchor exemption -- not supply -- can keep the garrison from sortieing."""
    base = replace(coastal_corridor(), phase=Phase.COMBAT)
    target = base.target_hex                                     # (7,0)
    garrison = next(u for u in base.units if u.id == "UK-9Aus")  # on target
    reserve = replace(next(u for u in base.units if u.id == "UK-2Armd"), hex=(5, 0))
    enemy = Unit("AX-Storm", Side.AXIS, (6, 0), (StepRecord("pz", 3),),
                 mobility=Mobility.VEHICLE, cpa=20, stacking_points=2, oca=6, dca=6)
    supplies = (
        SupplyUnit("UK-Dump1", Side.ALLIED, (5, 0), ammo=40, fuel=60),
        SupplyUnit("UK-Dump2", Side.ALLIED, target, ammo=40, fuel=60),
    )
    return replace(base, units=(garrison, reserve, enemy), supplies=supplies)


def test_anchor_does_not_counter_assault_in_combat():
    state = _combat_state_enemy_on_perimeter()
    policy = ScriptedPolicy(attacker=Side.AXIS)
    assert "UK-9Aus" in policy._anchor_ids(state, Side.ALLIED)

    orders = policy.combat(state, Side.ALLIED)
    attackers = {uid for o in orders for uid in o.attacker_ids}
    assert "UK-9Aus" not in attackers, "the anchor holds the fortress, it does not sortie"
    assert "UK-2Armd" in attackers, "the non-anchor reserve still counter-attacks"
    assert any(o.target == (6, 0) for o in orders)
