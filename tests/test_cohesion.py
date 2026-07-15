"""Cohesion rules 6.24.2 / 6.26 / 6.27 (with 15.88 / 17.24 / 17.27).

6.27 is the load-bearing fix: the Cohesion a Close-Assault stack fights at is the
AVERAGE over its largest units, not the single strongest unit's level. Every combat
counter in CNA is one Stacking Point, so a multi-unit stack is always a tie and the
average fires in nearly every real assault. Reading the strongest unit's level instead
let one shattered counter drag a whole stack past the 17.24 '-17 et seq' Surrender floor,
so the CRT rarely rolled -- most assaults ended in an instant morale Surrender.

6.24.2 gives the counter-weight: a Close Assault that empties the defender's hex earns
the victor three Reorganization Points, so Cohesion is no longer a one-way ratchet.

6.26 stops a unit at Cohesion -26 or worse from moving or attacking (the
surrender-on-enemy-adjacency half is deferred and flagged).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.events import EventKind, Phase, Side
from game.movement import TerrainMap
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


def _unit(uid, side, hex_, coh, *, strength=6, sp=1, mor=0):
    return Unit(uid, side, hex_, (StepRecord("s", strength),), mobility=Mobility.FOOT,
                cpa=10, stacking_points=sp, oca=2, dca=2, morale=mor, cohesion=coh)


def _combat_state(units, supplies=()):
    ammo = sum(s.ammo for s in supplies)
    fuel = sum(s.fuel for s in supplies)
    return GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=1,
                     weather="clear", vp=VP(),
                     terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR}),
                     control={}, units=tuple(units), target_hex=(0, 0), supplies=tuple(supplies),
                     consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": ammo, "FUEL": fuel})


# ---- 6.27: the average, and the rulebook's own worked example --------------------------

def test_stack_cohesion_worked_example_6_27():
    from game.engine import _stack_cohesion
    brigades = [_unit("A", Side.AXIS, (0, 0), -4), _unit("B", Side.AXIS, (0, 0), -1),
                _unit("C", Side.AXIS, (0, 0), 3)]
    assert _stack_cohesion(brigades) == -1              # (-4 -1 +3)/3 = -0.667 -> -1


def test_stack_cohesion_single_unit_is_its_own_level():
    from game.engine import _stack_cohesion
    assert _stack_cohesion([_unit("A", Side.AXIS, (0, 0), -12)]) == -12


def test_stack_cohesion_averages_not_worst_case_6_27():
    from game.engine import _stack_cohesion
    # one shattered counter (-30) among three fresh ones does NOT define the stack: the
    # average is -7.5 -> -8, not -30. This is the whole point of the fix.
    stack = [_unit("A", Side.AXIS, (0, 0), -30), _unit("B", Side.AXIS, (0, 0), 0),
             _unit("C", Side.AXIS, (0, 0), 0), _unit("D", Side.AXIS, (0, 0), 0)]
    assert _stack_cohesion(stack) == -8


def test_stack_cohesion_only_largest_units_contribute_6_27():
    from game.engine import _stack_cohesion
    # a battalion (2 SP) with two shattered companies (1 SP) fights at the battalion's
    # level -- only the single largest unit contributes when it stands alone (6.27).
    stack = [_unit("BN", Side.AXIS, (0, 0), 0, sp=2),
             _unit("C1", Side.AXIS, (0, 0), -20, sp=1),
             _unit("C2", Side.AXIS, (0, 0), -20, sp=1)]
    assert _stack_cohesion(stack) == 0


# ---- 6.27 feeds 15.88 capitulation and the 17.4 morale roll ----------------------------

def test_averaged_cohesion_saves_stack_from_15_88_capitulation():
    from game.engine import _Run, _defenders_capitulate
    # the strongest-by-strength defender is shattered (-20, 10 steps); its fresh companion
    # (0) pulls the stack average to -10, ABOVE the -17 auto-surrender floor. Under the old
    # strongest-unit rule this stack read -20 and capitulated; averaged, it fights on.
    shattered = _unit("A", Side.ALLIED, (0, 0), -20, strength=10)
    fresh = _unit("B", Side.ALLIED, (0, 0), 0, strength=6)
    dump = SupplyUnit("DUMP", Side.ALLIED, (0, 0), ammo=40, fuel=0)
    r = _Run(_combat_state([shattered, fresh], supplies=[dump]))
    assert _defenders_capitulate(r, [shattered, fresh]) is False


def test_averaged_cohesion_below_floor_still_capitulates_15_88():
    from game.engine import _Run, _defenders_capitulate
    both = [_unit("A", Side.ALLIED, (0, 0), -18, strength=10),
            _unit("B", Side.ALLIED, (0, 0), -18, strength=6)]
    dump = SupplyUnit("DUMP", Side.ALLIED, (0, 0), ammo=40, fuel=0)
    r = _Run(_combat_state(both, supplies=[dump]))
    assert _defenders_capitulate(r, both) is True       # average -18 <= -17


# ---- 6.24.2: a Close Assault that empties the hex earns the victor 3 RP -----------------

def test_victorious_assault_earns_3_rp_6_24_2():
    from game.engine import _Run, _resolve_combat
    # a strong attacker eliminates a lone dry garrison (it capitulates, 15.15); the hex is
    # vacated as a direct result, so the surviving attacker gains three Reorganization
    # Points -- Cohesion climbs from -5 to -2.
    attacker = _unit("A", Side.AXIS, (1, 0), -5, strength=10, mor=1)
    garrison = _unit("G", Side.ALLIED, (0, 0), 0, strength=6, mor=2)   # dry: no ALLIED dump
    axd = SupplyUnit("AXD", Side.AXIS, (1, 0), ammo=40, fuel=0)        # only the attacker is fed
    r = _Run(_combat_state([attacker, garrison], supplies=[axd]))
    _resolve_combat(r, Side.AXIS, "AXIS/Front", [attacker], [garrison], (0, 0), set(), set())
    assert r.state.unit("G").strength == 0              # hex vacated
    assert r.state.unit("A").cohesion == -2             # -5 + 3 RP (6.24.2)


def test_victory_rp_capped_at_plus_10_6_23():
    from game.engine import _Run, _resolve_combat
    attacker = _unit("A", Side.AXIS, (1, 0), 9, strength=10, mor=1)    # already +9
    garrison = _unit("G", Side.ALLIED, (0, 0), 0, strength=6, mor=2)
    axd = SupplyUnit("AXD", Side.AXIS, (1, 0), ammo=40, fuel=0)
    r = _Run(_combat_state([attacker, garrison], supplies=[axd]))
    _resolve_combat(r, Side.AXIS, "AXIS/Front", [attacker], [garrison], (0, 0), set(), set())
    assert r.state.unit("A").cohesion == 10             # +9 + min(3, 10-9) = +10, NOT +12


def test_no_rp_when_defender_still_holds_the_hex_6_24_2():
    from game.engine import _Run, _award_vacate_rp
    attacker = _unit("A", Side.AXIS, (1, 0), -5, strength=10)
    defender = _unit("D", Side.ALLIED, (0, 0), 0, strength=6)          # still standing at (0,0)
    r = _Run(_combat_state([attacker, defender]))
    _award_vacate_rp(r, Side.AXIS, "AXIS/Front", [attacker], (0, 0))
    assert r.state.unit("A").cohesion == -5             # hex held -> no Reorganization


# ---- 6.26: a unit at Cohesion -26 or worse may not move or attack -----------------------

def test_unit_at_minus_26_may_not_attack_6_26():
    from game.engine import _Run, _resolve_combat
    broken = _unit("A", Side.AXIS, (1, 0), -26, strength=10, mor=1)    # may not attack (6.26)
    garrison = _unit("G", Side.ALLIED, (0, 0), 0, strength=6, mor=2)
    axd = SupplyUnit("AXD", Side.AXIS, (1, 0), ammo=40, fuel=0)
    ald = SupplyUnit("ALD", Side.ALLIED, (0, 0), ammo=40, fuel=0)      # fed -> not a 15.15 case
    r = _Run(_combat_state([broken, garrison], supplies=[axd, ald]))
    resolved = _resolve_combat(r, Side.AXIS, "AXIS/Front", [broken], [garrison],
                               (0, 0), set(), set())
    assert resolved is False                            # no eligible attacker -> assault rejected
    assert r.state.supply("AXD").ammo == 40             # the -26 unit drew no ammo (did not attack)
    assert r.state.unit("G").strength == 6              # garrison untouched
    assert any(e.kind == EventKind.ORDER_REJECTED for e in r.events)


def test_unit_at_minus_26_may_not_move_6_26():
    from game.engine import _Run, _movement
    from game.policy import MoveOrder
    terr = {(q, 0): Terrain.CLEAR for q in range(4)}
    u = Unit("U", Side.AXIS, (0, 0), (StepRecord("s", 6),), mobility=Mobility.FOOT,
             cpa=10, stacking_points=1, oca=2, dca=2, cohesion=-26)
    st = GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS, seed=1,
                   weather="clear", vp=VP(), terrain=TerrainMap(terrain=terr), control={},
                   units=(u,), target_hex=(3, 0), supplies=(),
                   consumed={"FUEL": 0}, initial_supply={"FUEL": 0})

    class _P:
        def movement(self, state, side):
            return [MoveOrder("U", (1, 0))]

    r = _Run(st)
    _movement(r, {Side.AXIS: _P(), Side.ALLIED: _P()}, Side.AXIS)
    assert r.state.unit("U").hex == (0, 0)              # 6.26: too broken to move
    rej = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert rej and "6.26" in rej[0].payload["reason"]
