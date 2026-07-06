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


def test_fuel_rate_by_mobility():
    s = coastal_corridor()
    assert supply.fuel_rate(s.unit("DAK-5le")) == 2     # VEHICLE proxy (49.19)
    assert supply.fuel_rate(s.unit("UK-9Aus")) == 0     # FOOT walks -- no fuel (49.12)


def test_fuel_cost_is_distance_based():
    # 49.13 (Regime B FULL LOGISTICS): rate x ceil(CP/5) x TOE Strength Points. A long
    # dash costs strictly more than a short hop, and the whole formation burns -- a
    # strength-5 unit costs 5-fold a single step.
    dak = coastal_corridor().unit("DAK-5le")            # rate 2, strength 5
    assert supply.fuel_cost(dak, 0) == 0                # did not move
    assert supply.fuel_cost(dak, 3) == 10               # one 5-CP group: 2 x 1 x 5
    assert supply.fuel_cost(dak, 10) == 20              # two groups: 2 x 2 x 5
    assert supply.fuel_cost(dak, 22) == 50              # five groups (ceil 22/5): 2 x 5 x 5
    assert supply.fuel_cost(dak, 10) > supply.fuel_cost(dak, 3)


def test_fuel_rate_field_overrides_proxy():
    dak = replace(coastal_corridor().unit("DAK-5le"), fuel_rate=6)   # transcribed value wins
    assert supply.fuel_rate(dak) == 6
    assert supply.fuel_cost(dak, 5) == 30               # 6 x ceil(5/5) x strength 5 (49.13)


def _z() -> dict:
    return {"AMMO": 0, "FUEL": 0, "STORES": 0, "WATER": 0}


def _init(supplies) -> dict:
    return {c: sum(getattr(s, c.lower()) for s in supplies)
            for c in ("AMMO", "FUEL", "STORES", "WATER")}


def test_fuelled_but_far_unit_strands():
    # A vehicle (rate 2, strength 3) with only 12 fuel can afford a short hop (4 hexes =
    # 8 CP -> 2*ceil(8/5)*3 = 12 fuel) but not a long dash (8 hexes = 16 CP ->
    # 2*ceil(16/5)*3 = 24 fuel): the engine rejects the far move and the unit stays put.
    # The dash-outruns-fuel law, under the 49.13 x-TOE-strength full-logistics charge.
    from game.policy import MoveOrder, Policy
    terr = {(q, 0): Terrain.CLEAR for q in range(9)}    # clear row, no roads: 2 CP/hex motorized
    unit = Unit("V", Side.AXIS, (0, 0), (StepRecord("pz", 3),),
                mobility=Mobility.VEHICLE, cpa=30, stacking_points=1, oca=6, dca=6)
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=40, fuel=12)
    st = GameState(
        turn=1, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM, seed=1,
        weather="clear", vp=VP(), terrain=TerrainMap(terrain=terr),
        control={}, units=(unit,), target_hex=(8, 0), supplies=(dump,),
        consumed=_z(), initial_supply=_init((dump,)))
    assert supply.fuel_cost(unit, 16) == 24 and supply.fuel_cost(unit, 8) == 12

    class ForceMove(Policy):
        def __init__(self, dest):
            self.dest = dest

        def movement(self, s2, side):
            return [MoveOrder("V", self.dest)] if side == Side.AXIS else []

        def combat(self, s2, side):
            return []
    near = run(st, axis=ForceMove((4, 0)), allied=ForceMove((4, 0)))     # 8 CP -> 4 fuel, ok
    assert near.final.unit("V").hex == (4, 0)
    far = run(st, axis=ForceMove((8, 0)), allied=ForceMove((8, 0)))      # 16 CP -> 8 fuel, denied
    assert any(e.kind == EventKind.ORDER_REJECTED and "fuel" in e.payload.get("reason", "")
               for e in far.events)
    assert far.final.unit("V").hex == (0, 0)            # never made the unaffordable dash


def test_ammo_cost_per_toe_function():
    # 50.14: rate x TOE Strength Points. Now FAITHFUL to the [50.2] chart (from
    # data/logistics_rates.json): barrage 4, anti-armor 3, close-assault 2 -- so a
    # strength-5 DAK unit spends 10 / 15 / 20 (the earlier proxy under-charged
    # close-assault at 1 -> 5 and anti-armor at 2 -> 10).
    dak = coastal_corridor().unit("DAK-5le")            # strength 5
    assert supply.ammo_cost(dak, activity="assault") == 10      # [50.2] close-assault 2
    assert supply.ammo_cost(dak, activity="anti_armor") == 15   # [50.2] anti-armor 3
    assert supply.ammo_cost(dak, activity="barrage") == 20      # [50.2] barrage 4
    # rule 50 draws no phasing distinction -- the cost is phasing-independent
    assert supply.ammo_cost(dak, phasing=False) == supply.ammo_cost(dak, phasing=True)


def test_logistics_rates_are_sourced_from_the_chart():
    # The consumption magnitudes are the RULEBOOK'S, loaded from
    # data/logistics_rates.json rather than hardcoded -- so the balance is the chart's.
    assert supply.AMMO_RATE == {"barrage": 4, "anti_armor": 3, "assault": 2}   # [50.2]
    assert supply._OTHER_CAP == {"AMMO": 1500, "FUEL": 5000,                   # [54.12] Other
                                 "STORES": 1000, "WATER": 1000}
    assert supply.TONS_PER_POINT == {"AMMO": 4, "FUEL": 0.125,                 # [54.5]
                                     "STORES": 1, "WATER": 1 / 6}
    # 51.11/51.13 stores: 4 per TOE combat, 1 per TOE non-combat.
    inf = coastal_corridor().unit("UK-9Aus")            # combat, strength 4
    assert supply.stores_cost(inf) == 16


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
        weather="clear", vp=VP(), terrain=TerrainMap(terrain=terr),
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
