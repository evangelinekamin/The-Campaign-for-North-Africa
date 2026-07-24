"""Rule 10.31-10.36 (Mandatory Attack / Holding Off), 8.64-8.67 (break-off negation) and the
6.26 Cohesion -26 floor -- Phase 6.3, "make contact cost something".

Before this, an army drifted up to an enemy stack, declined battle, and drifted on for free:
break-off was free the moment a unit stacked with a friendly negator (8.67), and a Phasing unit
could sit in an enemy Zone of Control and simply do nothing (10.31). Now Contact is answered or paid
for -- a stack that leaves an enemy hex neither Close Assaulted nor Held Off is force-retreated three
hexes for all its remaining CP and three Disorganization Points (10.36), or Surrenders if it is boxed
in (10.36e).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import zoc
from game.engine import (_combat, _mandatory_attack, _movement, _resolve_combat, _Run)
from game.events import EventKind, Phase, Side
from game.hexmap import Coord, distance
from game.movement import TerrainMap
from game.policy import MoveOrder, Policy
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


# --- fixtures ----------------------------------------------------------------

def _grid(n: int = 8) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _unit(uid: str, side: Side, hex_: Coord, *, cpa: int = 40, sp: int = 5, oca: int = 4,
          dca: int = 4, cohesion: int = 6, morale: int = 3, mob: Mobility = Mobility.MOTORIZED,
          vuln: int = 0, ammo: int = 0, strength: int = 6) -> Unit:
    return Unit(uid, side, hex_, (StepRecord("x", strength),), mob, cpa=cpa, stacking_points=sp,
                oca=oca, dca=dca, cohesion=cohesion, morale=morale, vulnerability=vuln, ammo=ammo)


def _state(units, terrain: TerrainMap | None = None) -> GameState:
    total_ammo = sum(u.ammo for u in units)
    return GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS,
                     seed=7, weather="normal", vp=VP(), terrain=terrain or _grid(), control={},
                     units=tuple(units), target_hex=(0, 0), supplies=(),
                     consumed={"AMMO": 0}, initial_supply={"AMMO": total_ammo})


class _NoOp(Policy):
    def movement(self, state, side):
        return []

    def combat(self, state, side):
        return []


def _policies():
    return {Side.AXIS: _NoOp(), Side.ALLIED: _NoOp()}


# A phasing Axis unit at (0,0); an Allied division at (1,0) exerts a ZOC into (0,0).
def _contact_state(**axis_kw):
    axis = _unit("A1", Side.AXIS, (0, 0), **axis_kw)
    foe = _unit("B1", Side.ALLIED, (1, 0), dca=6)      # sp5, raw_defense 36 -> exerts ZOC (10.15)
    return axis, foe, _state([axis, foe])


# --- 8.64-8.67: the break-off toll survives the 10.26 negator --------------------------------

LINE = TerrainMap(terrain={(x, 0): Terrain.CLEAR for x in range(4)})


def test_stacked_unit_still_pays_the_break_off_toll():
    # 8.62/8.67: a unit whose start hex is in an enemy ZOC is in Contact and pays 2 CP to leave,
    # EVEN when a co-located friendly combat unit negates that ZOC for through-movement (10.26).
    # Reading the negated form let a stacked unit break off for free -- the drift-up-and-away.
    reach = zoc.reachable_with_zoc(LINE, (0, 0), budget=20, mobility=Mobility.VEHICLE,
                                   enemy_zoc=frozenset({(0, 0)}),
                                   friendly_negators=frozenset({(0, 0)}), break_off=2.0)
    assert reach[(0, 0)] == 2.0            # still pays the toll to break off
    assert reach[(1, 0)] == 2.0 + 2       # break-off + the clear-hex step


def test_break_off_free_only_when_not_in_a_zoc():
    # The negator still frees through-movement (10.26): a unit that does NOT start in a ZOC pays
    # nothing to move, negator or not.
    reach = zoc.reachable_with_zoc(LINE, (0, 0), budget=20, mobility=Mobility.VEHICLE,
                                   enemy_zoc=frozenset({(1, 0)}),
                                   friendly_negators=frozenset({(1, 0)}))
    assert reach[(0, 0)] == 0.0


# --- 10.31-10.36: the mandatory attack ------------------------------------------------------

def test_declining_unit_is_force_retreated_and_disorganized():
    # 10.36: a Phasing combat unit in an unanswered enemy ZOC, not exempt, must retreat three
    # hexes -- spending all its remaining CP and taking three Disorganization Points.
    axis, foe, st = _contact_state()
    r = _Run(st)
    _mandatory_attack(r, Side.AXIS, set(), set(), {})
    assert any(e.kind == EventKind.UNIT_RETREATED and e.payload["unit_id"] == "A1"
               for e in r.events)
    a = r.state.unit("A1")
    assert distance(a.hex, (1, 0)) > 1        # it has broken contact
    assert a.cohesion == 3                    # 6 - 3 DP (10.36)
    assert a.cp_used == 40                    # "playing all CP's for such movement"


def test_boxed_in_unit_surrenders():
    # 10.36e: if no ZOC-free three-hex retreat exists the unit Surrenders in entirety. On a bare
    # line map the unit at (0,0) can only move toward the enemy at (1,0), so it is trapped.
    axis = _unit("A1", Side.AXIS, (0, 0))
    foe = _unit("B1", Side.ALLIED, (1, 0), dca=6)
    st = _state([axis, foe], terrain=LINE)
    r = _Run(st)
    _mandatory_attack(r, Side.AXIS, set(), set(), {})
    assert any(e.kind == EventKind.STEP_LOST and e.payload["unit_id"] == "A1"
               and e.payload["role"] == "surrender" for e in r.events)
    assert not r.state.unit("A1").alive


def test_close_assaulted_hex_discharges_the_obligation():
    # 10.31: an enemy hex that WAS Close Assaulted this segment is answered -- no forced retreat.
    axis, foe, st = _contact_state()
    r = _Run(st)
    _mandatory_attack(r, Side.AXIS, set(), {(1, 0)}, {})
    assert not any(e.kind == EventKind.UNIT_RETREATED for e in r.events)
    assert r.state.unit("A1").hex == (0, 0)


def test_holding_off_barrage_discharges_the_obligation():
    # 10.33/10.34: a Holding-Off Barrage that meets the threshold (one Actual Barrage Point per
    # enemy non-Gun battalion, here a single division = 1) satisfies 10.31 without a Close Assault.
    axis, foe, st = _contact_state()
    r = _Run(st)
    _mandatory_attack(r, Side.AXIS, set(), set(), {(1, 0): 4})
    assert not any(e.kind == EventKind.UNIT_RETREATED for e in r.events)


def test_gun_only_stack_is_exempt():
    # 10.32: a hex whose combat units are solely Guns (Artillery/AT/AA) owes no attack.
    axis, foe, st = _contact_state(vuln=4)             # a gun (Vulnerability > 0)
    r = _Run(st)
    _mandatory_attack(r, Side.AXIS, set(), set(), {})
    assert not any(e.kind == EventKind.UNIT_RETREATED for e in r.events)
    assert r.state.unit("A1").hex == (0, 0)


def test_unit_out_of_contact_is_untouched():
    axis = _unit("A1", Side.AXIS, (5, 5))              # nowhere near the enemy ZOC
    foe = _unit("B1", Side.ALLIED, (1, 0), dca=6)
    r = _Run(_state([axis, foe]))
    _mandatory_attack(r, Side.AXIS, set(), set(), {})
    assert not any(e.kind == EventKind.UNIT_RETREATED for e in r.events)


def test_combat_segment_wires_the_sweep():
    # End-to-end: a Combat Segment in which the Phasing side declines every attack still force-
    # retreats the unit sitting in the enemy ZOC (the sweep runs at the end of _combat).
    axis, foe, st = _contact_state()
    r = _Run(st)
    _combat(r, _policies(), Side.AXIS)
    assert any(e.kind == EventKind.UNIT_RETREATED and e.payload["unit_id"] == "A1"
               for e in r.events)


# --- 6.26: a unit at Cohesion -26 or worse may not move, attack, or defend --------------------

def test_minus_26_may_not_move():
    axis = _unit("A1", Side.AXIS, (0, 0), cohesion=-26)
    r = _Run(_state([axis]))

    class _MoveOrder(_NoOp):
        def movement(self, state, side):
            return [MoveOrder("A1", (2, 0))]

    _movement(r, {Side.AXIS: _MoveOrder(), Side.ALLIED: _NoOp()}, Side.AXIS)
    assert any(e.kind == EventKind.ORDER_REJECTED and "6.26" in e.payload.get("reason", "")
               for e in r.events)
    assert r.state.unit("A1").hex == (0, 0)


def test_minus_26_may_not_attack():
    # A lone attacker at Cohesion -26 is dropped from armed_atk (6.26): the assault is rejected.
    axis = _unit("A1", Side.AXIS, (0, 0), oca=8, cohesion=-30, ammo=100)
    foe = _unit("B1", Side.ALLIED, (1, 0), dca=4)
    r = _Run(_state([axis, foe]))
    resolved = _resolve_combat(r, Side.AXIS, "AXIS/Front", [axis], [foe], (1, 0), set(), set())
    assert resolved is False
    assert any(e.kind == EventKind.ORDER_REJECTED and "6.26" in e.payload.get("reason", "")
               for e in r.events)


def test_minus_26_may_not_defend():
    # 6.26: a defender at Cohesion -26 adds no defensive Rating -- it is excluded from armed_def
    # and so is never charged the 3-CP defence, while its healthy stackmate is. The large unit at
    # Cohesion 0 keeps the 6.27-averaged stack above the 15.88 auto-surrender floor.
    atk = _unit("A", Side.AXIS, (1, 0), oca=8, ammo=100)
    big = _unit("L", Side.ALLIED, (0, 0), sp=5, dca=4, cohesion=0, ammo=100)
    dead = _unit("S", Side.ALLIED, (0, 0), sp=1, dca=4, cohesion=-30)
    r = _Run(_state([atk, big, dead]))
    _resolve_combat(r, Side.AXIS, "AXIS/Front", [atk], [big, dead], (0, 0), set(), set())
    assert r.state.unit("S").cp_used == 0             # excluded from the defence, uncharged
    assert r.state.unit("L").cp_used == 3             # the healthy defender still pays (6.3)
