"""Tests for abstract logistics (rule 32): supply trace, costs, gating, and the
per-commodity conservation invariant."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import supply
from game.engine import _Run, _supply_movement, run
from game.events import EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import coastal_corridor
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


def _run(seed: int = 1941):
    pol = ScriptedPolicy(Side.AXIS)
    return run(coastal_corridor(seed=seed), axis=pol, allied=pol)


def test_fuel_cost_by_mobility():
    s = coastal_corridor()
    assert supply.fuel_cost(s.unit("DAK-5le")) == 2     # VEHICLE / tank bn-eq
    assert supply.fuel_cost(s.unit("UK-9Aus")) == 0     # FOOT walks


def test_ammo_cost_phasing_doubles():
    dak = coastal_corridor().unit("DAK-5le")            # stacking_points 2
    assert supply.ammo_cost(dak, phasing=False) == 2
    assert supply.ammo_cost(dak, phasing=True) == 4


def test_in_supply_when_colocated_with_dump():
    s = coastal_corridor()
    dak = s.unit("DAK-5le")                              # shares (0,0) with AX-Dump1
    assert supply.plan_draw(s, dak, supply.FUEL, 2) is not None


def test_out_of_supply_when_no_dump_in_range():
    s = coastal_corridor()
    stripped = replace(s, supplies=())                  # no dumps anywhere
    assert supply.plan_draw(stripped, s.unit("DAK-5le"), supply.FUEL, 2) is None


def test_movement_blocked_when_out_of_fuel():
    # The scripted policy now pre-filters out-of-fuel units, so probe the ENGINE
    # gate directly: a policy that forces the move onto a reachable hex must still
    # be rejected for fuel, and the unit must stay put.
    from game import tactics
    from game.policy import MoveOrder, Policy
    s = coastal_corridor()
    dry_axis = tuple(replace(su, fuel=0) if su.side == Side.AXIS else su
                     for su in s.supplies)
    init = {"AMMO": sum(su.ammo for su in dry_axis), "FUEL": sum(su.fuel for su in dry_axis)}
    dry = replace(s, supplies=dry_axis, consumed={"AMMO": 0, "FUEL": 0}, initial_supply=init)
    ez, eo = tactics.enemy_zoc_and_occupied(dry, Side.AXIS)
    dak = dry.unit("DAK-5le")
    dest = min((h for h in tactics.reachable_for(dry, dak, ez, eo) if h != dak.hex),
               key=lambda h: h)

    class ForceMove(Policy):
        def movement(self, st, side):
            return [MoveOrder("DAK-5le", dest)] if side == Side.AXIS else []

        def combat(self, st, side):
            return []
    result = run(dry, axis=ForceMove(), allied=ForceMove())
    fuel_rejects = [e for e in result.events if e.kind == EventKind.ORDER_REJECTED
                    and "fuel" in e.payload.get("reason", "")]
    assert fuel_rejects
    assert result.final.unit("DAK-5le").hex == dak.hex   # never moved without fuel


def _mobile_state() -> GameState:
    """A fuelled dump behind a combat unit that has advanced toward the objective."""
    terr = {(q, 0): Terrain.CLEAR for q in range(6)}
    units = (Unit("AX-1", Side.AXIS, (2, 0), (StepRecord("inf", 3),),
                  mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=3, dca=3),)
    dumps = (SupplyUnit("AX-D", Side.AXIS, (0, 0), ammo=10, fuel=10),)
    return GameState(
        turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS, seed=1,
        weather="clear", move_modifier=0, vp=VP(), terrain=TerrainMap(terrain=terr),
        control={}, units=units, target_hex=(5, 0), supplies=dumps,
        consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 10, "FUEL": 10})


def test_supply_relocates_to_join_the_advance():
    # a fuelled dump moves up to CPA 15 to the forward combat unit's hex (rule
    # 32.33 stacked), burning exactly 1 Fuel (rule 32.24); fuel stays conserved.
    r = _Run(_mobile_state())
    _supply_movement(r, ScriptedPolicy(Side.AXIS), Side.AXIS)
    d = r.state.supply("AX-D")
    assert d.hex == (2, 0)                               # joined the advance
    assert d.fuel == 9                                   # burned 1 Fuel to move
    assert sum(e.kind == EventKind.SUPPLY_MOVED for e in r.events) == 1
    on_hand = sum(su.fuel for su in r.state.supplies)
    assert on_hand + r.state.consumed["FUEL"] == r.state.initial_supply["FUEL"]


def test_supply_cannot_move_without_fuel():
    dry = replace(_mobile_state(),
                  supplies=(SupplyUnit("AX-D", Side.AXIS, (0, 0), ammo=10, fuel=0),),
                  initial_supply={"AMMO": 10, "FUEL": 0})
    r = _Run(dry)
    _supply_movement(r, ScriptedPolicy(Side.AXIS), Side.AXIS)
    assert r.state.supply("AX-D").hex == (0, 0)          # no fuel -> stays put


def test_run_conserves_each_commodity():
    final = _run().final
    for commodity in ("AMMO", "FUEL"):
        on_hand = sum(getattr(su, commodity.lower()) for su in final.supplies)
        assert on_hand + final.consumed[commodity] == final.initial_supply[commodity]
    assert final.consumed["FUEL"] > 0                   # logistics actually engaged
