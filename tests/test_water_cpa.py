"""[52.42] THE CONDITION ON THE VEHICLE'S WATER POINT -- "if it uses any of its CPA".

    [52.41] "Each infantry battalion or company regardless of its TOE Strength, requires one
            Water Point per Operations Stage. See also 52.6."
    [52.42] "Each TOE Strength Point of Vehicle (Tank, Recce, Artillery, etc.) or Truck Point
            requires one Water Point each Operations Stage, if it uses any of its CPA."

Read off the scan at 400 dpi, PDF page 68 = book folio 21, column 3. The asymmetry is the book's
own: the infantryman drinks whether he marches or not, the vehicle's ration falls due only when it
runs. [53.0]'s General Rule says the same thing for the lorries in one line -- "Trucks consume fuel
and water when they move, and they suffer breakdown."

WHAT THIS FILE PINS. engine._water_distribution used to charge EVERY vehicle unconditionally at the
TOP of the Operations Stage, which is the one moment in the stage when the condition CANNOT be
evaluated: cp_used is 0 for every counter there (apply._reset_opstage). Measured over full
12-Game-Turn campaigns on seeds 1941/7/4/2026 before the fix: 88.9% / 88.9% / 88.3% / 84.0% of all
vehicle-class Water Points billed went to a counter that spent ZERO CPA that whole stage, and 98.2%
/ 98.9% / 99.4% / 99.2% of vehicle WATER_SHORTFALL rows -- the rows that set stages_without_water
and so halve a defender under [52.51] -- were on a counter that, under 52.42 as printed, owed
nothing at all.

The bill is now drawn where the CPA is spent (engine._draw_stage_water), ONCE per Operations Stage,
at every site that raises cp_used. A vehicle that stands still all stage pays nothing and is never
dry; a vehicle that acts and cannot pay is refused the act it is barred from ([52.51] "Vehicles
without water may not move or close assault offensively") and carries the dryness into the rest of
the stage.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataclasses import replace

from game import construction, supply
from game.engine import (_Run, _blow_dumps, _build_dump, _combat, _draw_stage_water, _movement,
                         _react, _rebuild, _reorganize, _resolve_combat, _retreat_before_assault,
                         _water_body)
from game.events import EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import (BuildOrder, DemolitionOrder, MoveOrder, OrganizationOrder,
                         Policy, ScriptedPolicy)
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain

COMMODITIES = ("AMMO", "FUEL", "STORES", "WATER")


# --- fixtures -------------------------------------------------------------------------------

def _grid(n: int = 8) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _veh(uid, side, hex_, *, strength=3, cpa=20, fuel=1000, ammo=100, **kw) -> Unit:
    """A VEHICLE-class counter (52.42: 1 Water Point per TOE Strength Point, conditionally)."""
    return Unit(uid, side, hex_, (StepRecord("s", strength),), Mobility.VEHICLE,
                cpa=cpa, stacking_points=kw.pop("sp", 1), oca=kw.pop("oca", 4),
                dca=kw.pop("dca", 4), fuel=fuel, ammo=ammo, morale=3, **kw)


def _foot(uid, side, hex_, *, strength=3, cpa=20, ammo=100, **kw) -> Unit:
    """A FOOT counter (52.41: 1 Water Point flat, unconditionally)."""
    return Unit(uid, side, hex_, (StepRecord("s", strength),), Mobility.FOOT,
                cpa=cpa, stacking_points=kw.pop("sp", 1), oca=kw.pop("oca", 4),
                dca=kw.pop("dca", 4), ammo=ammo, morale=3, **kw)


def _well(sid, side, hex_, water=1000) -> SupplyUnit:
    return SupplyUnit(sid, side, hex_, ammo=0, fuel=0, stores=0, water=water, base=True)


def _elsewhere(side) -> SupplyUnit:
    """A well the OTHER side owns, so the board MODELS water (engine._models_full_logistics) while
    `side` can draw none of it (supply.reachable_supplies is side-filtered). This is how a test
    puts a counter in a waterless desert without also switching rule 52 off wholesale."""
    other = Side.ALLIED if side is Side.AXIS else Side.AXIS
    return _well(f"{other.value}-FarWell", other, (8, 8), water=1)


def _state(units, supplies=(), *, phase=Phase.MOVEMENT, active=Side.AXIS, seed=1,
           weather="normal") -> GameState:
    """A full-LOGISTICS toy board: initial_supply carries WATER, so engine._models_full_logistics
    is True and the whole of rule 52 is in force (an ammo/fuel-only scenario models no Water at
    all -- see engine._water_body -- and neither the stage-start beat nor the 52.42 draw runs)."""
    initial = {k: (sum(getattr(s, k.lower()) for s in supplies)
                   + sum(getattr(u, k.lower()) for u in units)) for k in COMMODITIES}
    return GameState(turn=1, max_turns=4, phase=phase, active_side=active, seed=seed,
                     weather=weather, vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=(8, 0), supplies=tuple(supplies),
                     consumed={k: 0 for k in COMMODITIES}, initial_supply=initial)


class _Mover(Policy):
    """A policy that issues one fixed batch of move orders, then nothing."""

    def __init__(self, orders, react=()):
        self._orders, self._react, self._fired = list(orders), list(react), False

    def movement(self, state, side):
        if self._fired:
            return []
        self._fired = True
        return self._orders

    def combat(self, state, side):
        return []

    def react_to(self, state, side, trigger, eligible):
        return [o for o in self._react if o.unit_id in eligible]


def _policies(axis=None, allied=None):
    return {Side.AXIS: axis or ScriptedPolicy(Side.AXIS),
            Side.ALLIED: allied or ScriptedPolicy(Side.AXIS)}


def _water_drawn(events, unit_id=None):
    return sum(e.payload["qty"] for e in events
               if e.kind == EventKind.SUPPLY_CONSUMED
               and e.payload["commodity"] == supply.WATER
               and (unit_id is None or e.payload.get("unit_id") == unit_id))


def _shortfalls(events, unit_id=None):
    return [e for e in events if e.kind == EventKind.WATER_SHORTFALL
            and (unit_id is None or e.payload["unit_id"] == unit_id)]


def _cp_charged(events, unit_id):
    """The [6.3] Capability Points billed to one counter -- the OTHER leg of the charges this file
    watches. 52.42's Point falls due because a charge landed; if no charge may land, no Point does."""
    return sum(e.payload["cp"] for e in events
               if e.kind == EventKind.CP_EXPENDED and e.payload.get("unit_id") == unit_id)


# --- [52.41] / [52.42] at the stage-start Water Distribution ---------------------------------

def test_52_42_a_vehicle_that_has_spent_no_cpa_is_billed_nothing_at_the_stage_start():
    # THE DEFECT, stated as a test. At the top of an Operations Stage nobody has spent a
    # Capability Point yet, so 52.42's condition ("if it uses any of its CPA") is false for every
    # vehicle on the board -- and a bill drawn there is a bill the book does not print. The
    # infantryman's 52.41 Point IS drawn here, unconditionally, because his rule carries no
    # condition to wait for.
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    inf = _foot("INF", Side.AXIS, (0, 0), strength=3)
    r = _Run(_state([tank, inf], [_well("AX-Well", Side.AXIS, (0, 0))], phase=Phase.LOGISTICS))
    _water_body(r)
    assert _water_drawn(r.events, "TANK") == 0        # 52.42: the condition is not met
    assert _water_drawn(r.events, "INF") == 1         # 52.41: flat 1, regardless of TOE
    assert _shortfalls(r.events) == []                # and nothing is marked dry


def test_52_42_a_vehicle_starts_every_operations_stage_not_dry():
    # A vehicle carries no thirst across the stage boundary: the stage-start beat RESTORES it,
    # so dryness is only ever something it earns by failing to pay for an act it took THIS stage.
    # Without this the 52.51 immobilisation would be permanent -- the vehicle can no longer move,
    # so it can never trigger the draw that would clear it.
    tank = _veh("TANK", Side.AXIS, (0, 0), stages_without_water=1)
    r = _Run(_state([tank], [_well("AX-Well", Side.AXIS, (0, 0))], phase=Phase.LOGISTICS))
    _water_body(r)
    assert r.state.unit("TANK").stages_without_water == 0
    assert any(e.kind == EventKind.WATER_RESTORED and e.payload["unit_id"] == "TANK"
               for e in r.events)


def test_52_41_infantry_still_goes_dry_at_the_stage_start_when_the_well_is_out_of_reach():
    # The other half of the asymmetry, unchanged: the foot battalion's Point is unconditional, so
    # a battalion out of reach of any water is dry from the top of the stage (52.52/52.53), which
    # is what it always was. This slice does not touch the infantry leg.
    inf = _foot("INF", Side.AXIS, (0, 0))
    r = _Run(_state([inf], [_elsewhere(Side.AXIS)], phase=Phase.LOGISTICS))
    _water_body(r)
    assert r.state.unit("INF").stages_without_water == 1


# --- SITE 1: ordinary movement (rule 8.1) and the continual-movement pulse (8.2) ---------------

def test_52_42_a_vehicle_that_moves_pays_one_water_point_per_toe_strength_point():
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    well = _well("AX-Well", Side.AXIS, (0, 0))
    r = _Run(_state([tank], [well]))
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    assert r.state.unit("TANK").hex == (1, 0)
    assert _water_drawn(r.events, "TANK") == 3           # 52.42: one Point per TOE Strength Point


def test_52_42_infantry_pays_no_water_for_moving():
    # 52.41 has no CPA condition and is billed at the stage beat; the move itself must not
    # double-charge the foot battalion.
    inf = _foot("INF", Side.AXIS, (0, 0))
    r = _Run(_state([inf], [_well("AX-Well", Side.AXIS, (0, 0))]))
    _movement(r, _policies(axis=_Mover([MoveOrder("INF", (1, 0))])), Side.AXIS)
    assert r.state.unit("INF").hex == (1, 0)
    assert _water_drawn(r.events, "INF") == 0


def test_52_42_the_bill_falls_due_once_per_operations_stage_however_often_it_moves():
    # "one Water Point each Operations Stage" -- not per move. A unit that moves in Segment 0 and
    # again in a Continual-Movement pulse (8.2) pays once, unlike the 49.16 per-move fuel draw
    # standing beside it.
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    r = _Run(_state([tank], [_well("AX-Well", Side.AXIS, (0, 0), water=1000)]))
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (2, 0))])), Side.AXIS,
              frozenset({"TANK"}))                        # the 8.23-eligible pulse
    assert r.state.unit("TANK").hex == (2, 0)
    assert _water_drawn(r.events, "TANK") == 3            # ONE stage bill, two moves


# --- the ledger's OWN boundary: it must expire on (turn, stage), not be reset by run() ----------

def test_52_42_the_stage_ledger_expires_at_the_operations_stage_boundary():
    # "one Water Point EACH Operations Stage" -- so the settled-this-stage ledger must die at the
    # stage boundary, and it must die BY ITSELF. This test drives two Operations Stages by hand on
    # one _Run, exactly as every other test in this file drives one, and never enters engine.run():
    # a ledger cleared by a line inside run()'s stage loop is still holding stage 1's ids here, and
    # the tank makes its second stage's move for free. (The engine rejects that shape by name in
    # two places already -- engine._port_tons for [55.3] and _Run.rail_stage for [54.43] -- each
    # because "any caller that drives the stages itself -- a test, a measurement driver -- would
    # otherwise silently inherit a spent budget". All three share engine._OpStageLedger since the
    # ledger refactor; the per-ledger _expire_rail_stage this comment used to name is gone.)
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    r = _Run(_state([tank], [_well("AX-Well", Side.AXIS, (0, 0), water=1000)]))
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    assert _water_drawn(r.events, "TANK") == 3
    r.emit(EventKind.STAGE_ADVANCED, Side.SYSTEM, "SYSTEM", {"stage": 2})   # 6.16: a new CPA window
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (2, 0))])), Side.AXIS)
    assert r.state.unit("TANK").hex == (2, 0)
    assert _water_drawn(r.events, "TANK") == 6            # a SECOND stage, a SECOND Point


def test_52_42_the_stage_ledger_expires_at_the_game_turn_boundary_too():
    # The same boundary from the other side, and this one is not hypothetical: engine.run() charges
    # [19.68]'s rebuild Capability Points from _replacement_spend, a GAME-TURN-level beat that runs
    # BEFORE `for stage in (1, 2, 3)`. Under a reset-in-the-loop ledger that beat reads the PREVIOUS
    # Game-Turn's Operations Stage 3 entries, so a counter that acted then is billed nothing now --
    # measured live on campaign seeds 4 and 7, one suppressed vehicle bill each. TURN_ADVANCED
    # re-opens the CPA window (apply._reset_opstage) and must re-open this ledger with it.
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    r = _Run(_state([tank], [_well("AX-Well", Side.AXIS, (0, 0), water=1000)]))
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    assert _water_drawn(r.events, "TANK") == 3
    r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM", {"turn": 2})
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (2, 0))])), Side.AXIS)
    assert r.state.unit("TANK").hex == (2, 0)
    assert _water_drawn(r.events, "TANK") == 6


# --- the two draws are ONE affordability question ([49.15] before [52.42]) ----------------------

def test_52_42_no_water_is_drawn_for_a_move_the_fuel_refuses():
    # A move that cannot be fuelled never happens, so the vehicle "uses none of its CPA" and owes no
    # Water Point -- and 52.51 bars a dry vehicle from moving anyway, so it must not burn the fuel
    # either. The two draws are therefore asked in one breath: the fuel is TESTED (engine._can_fuel_move,
    # over supply.in_hex_available -- in_hex_draw's own documented monotone oracle) before the water
    # is DRAWN. Measured on campaign/1941 to Game-Turn 12 with the water drawn first: 270 of 1,179
    # vehicle Water Points, 23% of the whole bill, paid for moves that never happened.
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3, fuel=0)   # 49.14 tank empty, no dump beside it
    r = _Run(_state([tank], [_well("AX-Well", Side.AXIS, (0, 0), water=1000)]))
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    assert r.state.unit("TANK").hex == (0, 0)             # 49.15 refused it
    assert any(e.kind == EventKind.ORDER_REJECTED and "fuel" in str(e.payload.get("reason", ""))
               for e in r.events)
    assert _water_drawn(r.events, "TANK") == 0            # ...and its water was never spent on it
    assert r.state.unit("TANK").stages_without_water == 0
    assert _shortfalls(r.events, "TANK") == []


def test_52_42_51_a_vehicle_that_cannot_draw_its_water_may_not_move_and_is_dry_thereafter():
    # 52.42 falls due the moment the vehicle uses its CPA; unpaid, 52.51 bars the move ("Vehicles
    # without water may not move") and the counter is dry for the rest of the stage -- which is
    # what halves it in defence (52.51) and bars its offensive close assault.
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    r = _Run(_state([tank], [_elsewhere(Side.AXIS)]))     # water on the board, none of it his
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    assert r.state.unit("TANK").hex == (0, 0)             # refused
    assert r.state.unit("TANK").stages_without_water == 1
    assert len(_shortfalls(r.events, "TANK")) == 1
    assert any(e.kind == EventKind.ORDER_REJECTED and "52.51" in str(e.payload.get("reason", ""))
               for e in r.events)


def test_52_42_a_refused_vehicle_is_not_billed_twice_in_the_same_stage():
    # The bill is settled once per stage whether it was PAID or FAILED: a second order in the same
    # stage must not raise a second WATER_SHORTFALL (which would make 52.53's "consecutive
    # Operations Stage" counter advance twice inside one stage).
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    r = _Run(_state([tank], [_elsewhere(Side.AXIS)]))
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    assert len(_shortfalls(r.events, "TANK")) == 1
    assert r.state.unit("TANK").stages_without_water == 1


def test_52_42_a_move_that_is_rejected_for_another_reason_draws_no_water():
    # The condition is "if it uses any of its CPA", and USES is the operative word: an order
    # rejected before any Capability Point is spent -- here an unreachable destination -- uses
    # none, so no Point falls due and the counter stays wet. (The draw sits beside the 49.13 fuel
    # draw, after every legality check.)
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3, cpa=2)
    r = _Run(_state([tank], [_well("AX-Well", Side.AXIS, (0, 0))]))
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (7, 0))])), Side.AXIS)  # far out of CPA
    assert r.state.unit("TANK").hex == (0, 0)
    assert _water_drawn(r.events, "TANK") == 0
    assert _shortfalls(r.events, "TANK") == []


def test_52_42_the_hot_weather_doubling_rides_the_conditional_bill():
    # 29.35: "During hot weather, water requirements for all units are doubled." The rate is
    # supply.water_cost's, unchanged -- what moved is WHEN it is asked, not what it returns.
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    r = _Run(_state([tank], [_well("AX-Well", Side.AXIS, (0, 0))], weather="hot"))
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    assert _water_drawn(r.events, "TANK") == 6


# --- SITE 2: Reaction Movement (rule 8.5 -- "reaction IS movement", 8.51) ---------------------

def test_52_42_a_reacting_vehicle_pays_its_stage_water():
    mover = _veh("A1", Side.AXIS, (2, 0), cpa=40)
    reactor = _veh("B1", Side.ALLIED, (3, 0), cpa=40, strength=3, sp=3)
    r = _Run(_state([mover, reactor], [_well("AL-Well", Side.ALLIED, (3, 0))]))
    _react(r, _policies(allied=_Mover([], react=[MoveOrder("B1", (5, 0))])), Side.AXIS, "A1")
    assert r.state.unit("B1").hex == (5, 0)
    assert _water_drawn(r.events, "B1") == 3


def test_52_42_51_a_dry_reactor_may_not_slide_aside():
    mover = _veh("A1", Side.AXIS, (2, 0), cpa=40)
    reactor = _veh("B1", Side.ALLIED, (3, 0), cpa=40, strength=3, sp=3)
    r = _Run(_state([mover, reactor], [_elsewhere(Side.ALLIED)]))   # no well of HIS within reach
    _react(r, _policies(allied=_Mover([], react=[MoveOrder("B1", (5, 0))])), Side.AXIS, "A1")
    assert r.state.unit("B1").hex == (3, 0)               # 52.51: it may not move
    assert r.state.unit("B1").stages_without_water == 1


# --- SITE 3: Retreat Before Assault (rule 13.21 -- "it is Voluntary Movement") -----------------

class _Retreater(Policy):
    def __init__(self, order):
        self._order = order

    def movement(self, state, side):
        return []

    def combat(self, state, side):
        return []

    def retreat_before_assault(self, state, side, pinned):
        return [self._order]


def test_52_42_a_vehicle_retreating_before_assault_pays_its_stage_water():
    atk = _veh("A", Side.AXIS, (0, 0))
    dfn = _veh("D", Side.ALLIED, (1, 0), strength=3)
    r = _Run(_state([atk, dfn], [_well("AL-Well", Side.ALLIED, (1, 0))], phase=Phase.COMBAT))
    _retreat_before_assault(r, _Retreater(MoveOrder("D", (2, 0))), Side.ALLIED, Side.AXIS, set())
    assert r.state.unit("D").hex == (2, 0)
    assert _water_drawn(r.events, "D") == 3


def test_52_42_51_a_dry_vehicle_may_not_retreat_before_assault():
    atk = _veh("A", Side.AXIS, (0, 0))
    dfn = _veh("D", Side.ALLIED, (1, 0), strength=3)
    r = _Run(_state([atk, dfn], [_elsewhere(Side.ALLIED)], phase=Phase.COMBAT))
    _retreat_before_assault(r, _Retreater(MoveOrder("D", (2, 0))), Side.ALLIED, Side.AXIS, set())
    assert r.state.unit("D").hex == (1, 0)
    assert r.state.unit("D").stages_without_water == 1


# --- SITE 4: the offensive Close Assault (rule 15 / 52.51's own prohibition) -------------------

def test_52_42_51_a_vehicle_that_cannot_pay_may_not_close_assault_offensively():
    # 52.51: "Vehicles without water may not... close assault offensively." The 5-CP Assault is a
    # use of CPA, so the bill falls due as the attacker is armed -- BEFORE its ammunition is
    # charged, so a refused attacker does not even spend its load.
    dfn = _foot("D", Side.ALLIED, (0, 0), ammo=100)
    atk = _veh("A", Side.AXIS, (1, 0), strength=3, ammo=100)
    r = _Run(_state([atk, dfn], [_elsewhere(Side.AXIS)], phase=Phase.COMBAT))
    assert _resolve_combat(r, Side.AXIS, "AXIS/Front", [atk], [dfn], (0, 0), set(), set()) is False
    assert r.state.unit("A").stages_without_water == 1
    assert r.state.unit("A").ammo == 100                  # not a round spent


def test_52_42_an_attacker_refused_for_ammunition_pays_no_water_point():
    # THE CONDITION CUTS BOTH WAYS. 52.42 bills the Point "if it uses any of its CPA", and an
    # attacker that cannot draw its [50.15] Close-Assault ammunition is dropped from armed_atk,
    # never reaches _charge_combat_cp, and so spends none of the [6.3] 5-CP Assault -- it uses none
    # of its CPA and owes nothing. So the ammunition question must be SETTLED (not charged) first.
    # That is verbatim _can_fuel_move's reasoning one site over: "each is due only if the move
    # actually happens". _has_ammo is the non-mutating oracle for it -- the same one 15.15's
    # capitulation test already uses -- so nothing is spent to ask.
    #
    # NOT a swap of the two draws: charging the ammunition first would spend the SCARCE commodity
    # on an assault the water then refuses, which is what the test above forbids.
    dfn = _foot("D", Side.ALLIED, (0, 0), ammo=100)
    atk = _veh("A", Side.AXIS, (1, 0), strength=3, ammo=0)       # watered, but shot out (50.12)
    r = _Run(_state([atk, dfn], [_well("AX-Well", Side.AXIS, (1, 0))], phase=Phase.COMBAT))
    assert _resolve_combat(r, Side.AXIS, "AXIS/Front", [atk], [dfn], (0, 0), set(), set()) is False
    assert _water_drawn(r.events, "A") == 0                      # no act, no Water Point
    assert r.state.unit("A").stages_without_water == 0           # and it is not made dry either


def test_52_42_a_watered_vehicle_close_assaults_and_pays_for_it():
    dfn = _foot("D", Side.ALLIED, (0, 0), ammo=100)
    atk = _veh("A", Side.AXIS, (1, 0), strength=3, ammo=100)
    r = _Run(_state([atk, dfn], [_well("AX-Well", Side.AXIS, (1, 0))], phase=Phase.COMBAT))
    assert _resolve_combat(r, Side.AXIS, "AXIS/Front", [atk], [dfn], (0, 0), set(), set()) is True
    assert _water_drawn(r.events, "A") == 3


# --- SITE 5: every 6.3 combat Capability Point (engine._spend_cp) ------------------------------

def test_52_42_a_defending_vehicle_pays_its_stage_water_for_the_6_3_defence_cp():
    # [6.3] charges a NON-PHASING unit 3 Capability Points to defend, which cp_used accrues exactly
    # as movement does (6.14) -- so by the engine's own accounting the defender "uses its CPA" and
    # 52.42's Point falls due. FLAGGED as a reading in engine._draw_stage_water's docstring.
    dfn = _veh("D", Side.ALLIED, (0, 0), strength=3, ammo=100)
    atk = _foot("A", Side.AXIS, (1, 0), ammo=100)
    r = _Run(_state([atk, dfn], [_well("AL-Well", Side.ALLIED, (0, 0))], phase=Phase.COMBAT))
    _resolve_combat(r, Side.AXIS, "AXIS/Front", [atk], [dfn], (0, 0), set(), set())
    assert _water_drawn(r.events, "D") == 3


def test_52_42_a_barraging_battery_pays_its_stage_water():
    # 52.42 names Artillery outright. A gun that fires a barrage pays the 6.3 combat CP, so its
    # water falls due even though it never moved a hex.
    gun = _veh("G", Side.AXIS, (0, 0), strength=3, barrage=10, ammo=1000, oca=0, dca=1)
    tgt = _foot("D", Side.ALLIED, (1, 0), ammo=100)
    r = _Run(_state([gun, tgt], [_well("AX-Well", Side.AXIS, (0, 0))], phase=Phase.COMBAT))
    _combat(r, _policies(), Side.AXIS)
    assert any(e.kind == EventKind.BARRAGE_RESOLVED for e in r.events)
    assert _water_drawn(r.events, "G") == 3


# --- SITE 6: the [6.3] ORGANIZATION rows (rule 19) ---------------------------------------------

def test_52_42_a_vehicle_charged_an_organization_cp_pays_its_stage_water():
    # [6.3]'s organization rows charge real Capability Points, folded into the same cp_used
    # accumulator (apply.CP_EXPENDED), so an attach is a use of CPA under 52.42.
    hq = _foot("KG", Side.AXIS, (0, 0), strength=1, sp=2, is_combat=False,
               org_type="ge_battle_group")
    tank = _veh("TK", Side.AXIS, (0, 0), strength=3, is_tank=True)
    r = _Run(_state([hq, tank], [_well("AX-Well", Side.AXIS, (0, 0))], phase=Phase.RECORD))
    _reorganize(r, Side.AXIS, OrganizationOrder("attach", unit_id="TK", parent_id="KG"))
    assert r.state.unit("TK").attached_to == "KG"
    assert _water_drawn(r.events, "TK") == 3


# --- SITE 7: blowing a supply dump ([54.14], one third of basic CPA) ---------------------------

class _Demolisher(Policy):
    def __init__(self, order):
        self._order = order

    def movement(self, state, side):
        return []

    def combat(self, state, side):
        return []

    def demolition(self, state, side):
        return [self._order]


def test_52_42_a_vehicle_blowing_a_dump_pays_its_stage_water():
    tank = _veh("TK", Side.AXIS, (0, 0), strength=3)
    dump = SupplyUnit("AX-Dump", Side.AXIS, (0, 0), ammo=500, fuel=0, stores=0, water=0)
    r = _Run(_state([tank], [dump, _well("AX-Well", Side.AXIS, (0, 0))]))
    _blow_dumps(r, _Demolisher(DemolitionOrder("TK", "AX-Dump")), Side.AXIS)
    assert any(e.kind == EventKind.SUPPLY_DUMP_BLOWN for e in r.events)
    assert _water_drawn(r.events, "TK") == 3


# --- SITE 8: constructing a supply dump ([24.9], 3 CP + 20 Stores) -----------------------------

def test_52_42_a_vehicle_constructing_a_dump_pays_its_stage_water():
    tank = _veh("TK", Side.AXIS, (0, 0), strength=3)
    stores = SupplyUnit("AX-Stores", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=100, water=0)
    r = _Run(_state([tank], [stores, _well("AX-Well", Side.AXIS, (0, 0))]))
    _build_dump(r, Side.AXIS, "AXIS/Engineers",
                BuildOrder(item=construction.DUMP, hex=(0, 0), unit_ids=("TK",)))
    assert any(e.kind == EventKind.SUPPLY_DUMP_CONSTRUCTED for e in r.events)
    assert _water_drawn(r.events, "TK") == 3


# --- SITE 9: the [19.68] rebuild, which charges the unit AND its parent ------------------------

def _rebuildable(uid, side, hex_, *, strength=2, max_toe=6, **kw):
    """A depleted VEHICLE-class counter [20.3] can rebuild: a tank, whose row is the single-class
    'tank' one the Block-7.2b spend already wires."""
    return _veh(uid, side, hex_, strength=strength, is_tank=True, max_toe=max_toe, **kw)


def _rebuild_state(units, supplies, pool):
    return replace(_state(units, supplies, phase=Phase.RECORD), replacement_pool=pool)


def test_52_42_a_rebuilt_vehicle_pays_its_stage_water_on_its_live_toe_strength():
    # [19.68] "For every two Replacement TOE Strength Points added to a unit, that unit (and its
    # parent, if such is the situation) uses one Capability Point" -- a use of CPA, so 52.42's
    # Point falls due. AND IT FALLS DUE ON THE COUNTER THE REBUILD LEFT BEHIND: the bill is drawn
    # after UNIT_REBUILT has folded, and 52.42 bills "Each TOE Strength Point", so the strength it
    # reads must be the LIVE one. Billing the caller's pre-rebuild snapshot instead under-bills by
    # exactly the points absorbed -- measured on campaign/1941 to Game-Turn 12, seven settlements
    # billed on a stale TOE, every one of them an under-bill.
    tank = _rebuildable("TK", Side.AXIS, (0, 0), strength=2, max_toe=6)
    r = _Run(_rebuild_state([tank], [_well("AX-Well", Side.AXIS, (0, 0))], {"AXIS/tank": 2}))
    assert _rebuild(r, Side.AXIS, tank, 2) == ""
    assert r.state.unit("TK").strength == 4
    assert _water_drawn(r.events, "TK") == 4              # the LIVE TOE of 4, not the stale 2


def test_52_42_the_rebuilt_units_parent_formation_pays_its_stage_water_too():
    # [19.68] charges the SAME Capability Point to the parent, so the parent uses its CPA too and
    # owes its own 52.42 Point. (The dead-parent case is the test below: state.on_map refuses it.)
    parent = _veh("HQ", Side.AXIS, (0, 0), strength=3)
    tank = _rebuildable("TK", Side.AXIS, (0, 0), strength=2, max_toe=6, assigned_to="HQ")
    r = _Run(_rebuild_state([parent, tank], [_well("AX-Well", Side.AXIS, (0, 0))],
                            {"AXIS/tank": 2}))
    assert _rebuild(r, Side.AXIS, tank, 2) == ""
    assert _water_drawn(r.events, "HQ") == 3


def test_a_destroyed_parent_formation_drinks_nothing():
    # [19.68] and the [6.3] organization rows charge their Capability Points to the PARENT
    # FORMATION as well as to the unit, and a Parent may be a counter that has already been
    # eliminated -- state.on_map is what state.living, and so the stage-start beat, has always
    # filtered on. FOUND BY INSTRUMENTING THE CAMPAIGN, not by inspection: on campaign/1941 to
    # Game-Turn 12 the first cut of this slice made four such calls, one of which drew real Water
    # Points out of a dump for a dead Italian tank regiment. A destroyed counter uses no CPA.
    dead = _veh("DEAD", Side.AXIS, (0, 0), strength=3)
    dead = replace(dead, steps=(StepRecord("s", 0),))
    assert not dead.alive
    r = _Run(_state([dead], [_well("AX-Well", Side.AXIS, (0, 0))]))
    assert _draw_stage_water(r, dead) is True
    assert _water_drawn(r.events, "DEAD") == 0
    assert _shortfalls(r.events, "DEAD") == []


def test_19_68_a_destroyed_parent_formation_is_charged_no_capability_point():
    # THE OTHER LEG OF THE SAME CHARGE, and until now the two disagreed about who exists. The
    # 52.42 draw above asks state.on_map; [19.68]'s own CP_EXPENDED for "(and its parent, if such
    # is the situation)" asked nothing at all, so a Parent Formation the campaign had already
    # destroyed had cp_used folded onto its corpse.
    #
    #   [19.62] "Units that have been completely eliminated because of attrition on combat -- not
    #           breakdown (i.e., no TOE Strength Points remaining) may not be rebuilt."
    #   [19.63] "If a HQ unit (counter) is eliminated, it may not be rebuilt unless at least 50%
    #           of its assigned units still exist ... Otherwise it is gone for good."
    #   [19.67] "The HQ unit for a Parent Formation is, for play purposes, its Cadre."
    #   [6.11]  "Each unit has a Capability Point Allowance (CPA)."
    #
    # A counter that is gone for good has no CPA for 19.68 to spend. The CHILD's own charge is
    # untouched -- organization.may_rebuild already applies 19.62's existence test to it.
    dead = _veh("HQ", Side.AXIS, (0, 0), strength=3)
    dead = replace(dead, steps=(StepRecord("s", 0),))
    assert not dead.alive
    tank = _rebuildable("TK", Side.AXIS, (0, 0), strength=2, max_toe=6, assigned_to="HQ")
    r = _Run(_rebuild_state([dead, tank], [_well("AX-Well", Side.AXIS, (0, 0))],
                            {"AXIS/tank": 2}))
    assert _rebuild(r, Side.AXIS, tank, 2) == ""
    assert _cp_charged(r.events, "TK") == 1              # 19.68: the rebuilt unit itself still pays
    assert _cp_charged(r.events, "HQ") == 0              # the destroyed Parent Formation does not


def test_19_68_a_parent_that_has_not_yet_arrived_is_charged_no_capability_point():
    # THE SAME GUARD'S SECOND ARM, AND IT IS A READING RATHER THAN A TRANSCRIPTION -- flagged here
    # and at the site. state.on_map is `alive and turn >= arrival_turn`, so it also excludes a
    # Parent Formation whose rule-20 reinforcement turn has not come. 19.68 says nothing about
    # reinforcement timing; what licenses this arm is that state.on_map is the predicate
    # state.living -- and so every rule-52 water beat, including the 52.42 leg of THIS charge --
    # has always filtered on, and one charge must not be half-billed. The narrower alternative
    # (test `alive` only) would leave the two legs disagreeing again on ~5 charges per campaign.
    unarrived = _veh("HQ", Side.AXIS, (0, 0), strength=3, arrival_turn=9)
    tank = _rebuildable("TK", Side.AXIS, (0, 0), strength=2, max_toe=6, assigned_to="HQ")
    r = _Run(_rebuild_state([unarrived, tank], [_well("AX-Well", Side.AXIS, (0, 0))],
                            {"AXIS/tank": 2}))
    assert r.state.turn == 1 and not r.state.on_map(unarrived)
    assert _rebuild(r, Side.AXIS, tank, 2) == ""
    assert _cp_charged(r.events, "TK") == 1
    assert _cp_charged(r.events, "HQ") == 0


# --- the scenario gate: a board that models no Water at all is untouched -----------------------

def test_a_scenario_that_seeds_no_water_is_untouched_by_the_52_42_draw():
    # engine._models_full_logistics is the SAME gate that already governs the whole of rule 52
    # (engine._water_body returns at once for an ammo/fuel-only scenario, so stages_without_water
    # is 0 for every counter in one). The 52.42 draw honours it too: a board with no Water on it
    # anywhere models no water demand either, and a vehicle there is not immobilised out of a
    # commodity the scenario does not have.
    tank = _veh("TANK", Side.AXIS, (0, 0), strength=3)
    st = replace(_state([tank]), initial_supply={"AMMO": 100, "FUEL": 1000},
                 consumed={"AMMO": 0, "FUEL": 0})
    r = _Run(st)
    _movement(r, _policies(axis=_Mover([MoveOrder("TANK", (1, 0))])), Side.AXIS)
    assert r.state.unit("TANK").hex == (1, 0)
    assert _water_drawn(r.events) == 0
    assert _shortfalls(r.events) == []
