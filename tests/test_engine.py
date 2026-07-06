"""Phase-0 acceptance tests on the real land engine (brief §7, §8): the loop
completes, invariants hold, replay is byte-deterministic, fold reproduces the
live state, and illegal orders are rejected at the boundary without mutating
state."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game.apply import fold
from game.engine import RunResult, determinism_signature, run
from game.events import EventKind, Side
from game.invariants import InvariantViolation, check
from game.policy import AttackOrder, Policy, ScriptedPolicy
from game.scenario import coastal_corridor
from game.state import StepRecord


class _BadPolicy(Policy):
    """Ill-behaved (proxy for a future LLM) policy: proposes an off-map teleport
    every movement phase. The engine boundary must reject it, never move the unit."""

    def movement(self, state, side):
        if side != Side.AXIS:
            return []
        from game.policy import MoveOrder
        return [MoveOrder(u.id, (u.hex[0] + 50, u.hex[1])) for u in state.living(side)]

    def combat(self, state, side) -> list[AttackOrder]:
        return []


def _run(seed: int = 1941) -> RunResult:
    pol = ScriptedPolicy(Side.AXIS)
    return run(coastal_corridor(seed=seed), axis=pol, allied=pol)


def test_runs_to_completion():
    result = _run()
    assert result.winner in (Side.AXIS, Side.ALLIED)
    assert result.final.turn <= result.final.max_turns
    assert result.events[0].kind == EventKind.GAME_INITIALIZED


def test_determinism_same_seed():
    assert determinism_signature(_run(7).events) == determinism_signature(_run(7).events)


def test_different_seeds_can_diverge():
    sigs = {determinism_signature(_run(s).events) for s in range(8)}
    assert len(sigs) > 1


def test_replay_equivalence():
    result = _run()
    assert fold(result.initial, result.events) == result.final


def test_axis_actually_advances_on_real_terrain():
    # sanity that real CPA/road movement happens at all (not just rejections)
    result = _run()
    assert any(e.kind == EventKind.UNIT_MOVED for e in result.events)
    dak_start = coastal_corridor().unit("DAK-5le").hex
    assert result.final.unit("DAK-5le").hex != dak_start


def test_invariant_detects_negative_strength():
    s = coastal_corridor()
    broken = s.with_unit(replace(s.units[0], steps=(StepRecord("pz", -1),)))
    with pytest.raises(InvariantViolation):
        check(broken)


def test_invariant_detects_overstacking():
    s = coastal_corridor()
    # pile all four 2-point units into one hex (8 > limit 5)
    piled = replace(s, units=tuple(replace(u, hex=(0, 0)) for u in s.units))
    with pytest.raises(InvariantViolation):
        check(piled)


def test_retreat_relocates_defender_away_from_attacker():
    # a defender with room retreats the mandated hexes away from the assaulting
    # unit (rule 15.82); with no supply to bias toward, it moves as far as told.
    from game.engine import _Run, _retreat
    from game.events import Phase
    from game.hexmap import distance
    from game.movement import TerrainMap
    from game.state import GameState, SupplyUnit, Unit, VP
    from game.terrain import Mobility, Terrain
    terr = {(q, 0): Terrain.CLEAR for q in range(6)}
    defender = Unit("D", Side.ALLIED, (3, 0), (StepRecord("inf", 4),),
                    mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=2, dca=2)
    attacker = Unit("A", Side.AXIS, (2, 0), (StepRecord("inf", 4),),
                    mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=3, dca=3)
    st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS,
                   seed=1, weather="clear", vp=VP(),
                   terrain=TerrainMap(terrain=terr), control={}, units=(defender, attacker),
                   target_hex=(5, 0), supplies=(), consumed={"AMMO": 0, "FUEL": 0},
                   initial_supply={"AMMO": 0, "FUEL": 0})
    r = _Run(st)
    _retreat(r, Side.AXIS, "AXIS/Front", ["D"], (2, 0), 2)
    moved = r.state.unit("D")
    assert moved.hex != (3, 0)
    assert distance(moved.hex, (2, 0)) >= 3                # retreated 2 hexes away


def test_major_city_defender_is_not_evicted():
    # rule 15.82: a defender invested in a MAJOR CITY holds rather than retreat --
    # Tobruk sits out the siege. Same setup as the plain retreat test but the
    # defender's hex is a city: it must NOT move and take no eviction loss.
    from game.engine import _Run, _retreat
    from game.events import Phase
    from game.movement import TerrainMap
    from game.state import GameState, Unit, VP
    from game.terrain import Mobility, Terrain
    terr = {(q, 0): Terrain.CLEAR for q in range(6)}
    terr[(3, 0)] = Terrain.MAJOR_CITY
    defender = Unit("D", Side.ALLIED, (3, 0), (StepRecord("inf", 4),),
                    mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=2, dca=2)
    attacker = Unit("A", Side.AXIS, (2, 0), (StepRecord("inf", 4),),
                    mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=3, dca=3)
    st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS,
                   seed=1, weather="clear", vp=VP(),
                   terrain=TerrainMap(terrain=terr), control={}, units=(defender, attacker),
                   target_hex=(5, 0), supplies=(), consumed={"AMMO": 0, "FUEL": 0},
                   initial_supply={"AMMO": 0, "FUEL": 0})
    r = _Run(st)
    _retreat(r, Side.AXIS, "AXIS/Front", ["D"], (2, 0), 2)
    held = r.state.unit("D")
    assert held.hex == (3, 0)         # invested, not evicted (15.82)
    assert held.strength == 4         # no 10%/un-retreated-hex eviction loss


def test_rommels_arrival_fortifies_major_cities():
    # the data-bug fix: Tobruk (C4807) and Bardia (C4321) -- the victory hexes --
    # load as fortified MAJOR_CITY, not CLEAR, so the 15.82 exemption can fire.
    from game import coords
    from game.scenario import rommels_arrival
    from game.terrain import Terrain
    s = rommels_arrival(seed=1941)
    tobruk = coords.to_axial(coords.parse("C4807"))
    bardia = coords.to_axial(coords.parse("C4321"))
    assert s.terrain.terrain[tobruk] == Terrain.MAJOR_CITY
    assert s.terrain.terrain[bardia] == Terrain.MAJOR_CITY
    assert s.terrain.fortifications.get(tobruk) == 2
    assert s.terrain.fortifications.get(bardia) == 2


def test_scenarios_robust_across_seeds():
    # every scenario, across many dice, must finish with a winner, be replay-exact
    # and deterministic, with invariants holding every event (checked inside run).
    from game.scenario import battle_for_tobruk, coastal_corridor, rommels_arrival
    for factory in (coastal_corridor, battle_for_tobruk, rommels_arrival):
        for seed in range(1, 6):
            a = run(factory(seed=seed), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
            assert a.winner in (Side.AXIS, Side.ALLIED)
            assert fold(a.initial, a.events) == a.final
            b = run(factory(seed=seed), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
            assert determinism_signature(a.events) == determinism_signature(b.events)


def test_reinforcement_enters_on_its_arrival_turn():
    # off-map until its arrival_turn, then on-map (rule 20). The 15th Panzer tank
    # battalions arrive mid-scenario; a CW tank battalion arrives to hold Tobruk.
    from game.events import EventKind
    from game.scenario import rommels_arrival
    init = rommels_arrival(seed=1941)
    tank = init.unit("GE-I-8-Pz")
    assert tank is not None and not init.on_map(tank)         # exists but dormant at turn 1
    assert tank not in init.living(Side.AXIS)
    res = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    arrivals = {e.payload["unit_id"]: e.turn
                for e in res.events if e.kind == EventKind.REINFORCEMENT_ARRIVED}
    assert arrivals.get("GE-I-8-Pz") == 6 and arrivals.get("BR-4-RTR") == 4


def test_two_level_clock_cadence():
    # rules 5/48: each game-turn runs THREE Operations Stages. Weather (29.0) and water (52)
    # are per Operations Stage; reinforcement/convoy arrival (48 V.D) lands ONCE, in the
    # game-turn's first stage. This pins the split cadence the flat loop could never express.
    from collections import Counter

    from game.events import EventKind
    from game.scenario import rommels_arrival
    res = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    ev = res.events

    arrivals = [e for e in ev if e.kind == EventKind.REINFORCEMENT_ARRIVED]
    assert arrivals and all(n == 1 for n in Counter(e.payload["unit_id"] for e in arrivals).values())
    assert all(e.stage == 1 for e in arrivals)                 # 48 V.D: arrivals in stage 1 only

    # exactly one weather roll per Operations Stage executed; every body ends in a stage
    # advance, a turn advance, or the terminating victory/decision (the one un-advanced stage).
    weather = sum(1 for e in ev if e.kind == EventKind.WEATHER_ROLLED)
    stage_adv = sum(1 for e in ev if e.kind == EventKind.STAGE_ADVANCED)
    turn_adv = sum(1 for e in ev if e.kind == EventKind.TURN_ADVANCED)
    assert weather == stage_adv + turn_adv + 1
    assert all(e.payload["stage"] in (2, 3) for e in ev if e.kind == EventKind.STAGE_ADVANCED)
    assert res.final.stage in (1, 2, 3)


def test_surrender_at_collapsed_cohesion():
    # the 17.4 row for Cohesion <= -17 is all-Surrender; a stack there surrenders
    # (17.25). A Basic Morale of +1 or better normally shrugs the SURR off (17.26),
    # but that reprieve is VOIDED when Cohesion is -11 or worse (17.26a) -- so at
    # Cohesion -17 even a +1-morale stack must Surrender.
    from game.engine import _Run, _adjusted_morale
    from game.events import Phase
    from game.movement import TerrainMap
    from game.state import GameState, Unit, VP
    from game.terrain import Mobility, Terrain

    def mk(mor):
        return Unit("U", Side.AXIS, (0, 0), (StepRecord("s", 6),), mobility=Mobility.FOOT,
                    cpa=10, stacking_points=1, oca=2, dca=2, morale=mor, cohesion=-17)
    st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=1,
                   weather="clear", vp=VP(),
                   terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}), control={},
                   units=(mk(0),), target_hex=(0, 0), supplies=(),
                   consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 0, "FUEL": 0})
    r = _Run(st)
    assert _adjusted_morale(r, [mk(0)])[2] is True       # morale 0 -> surrenders
    assert _adjusted_morale(r, [mk(1)])[2] is True       # 17.26a: -17 cohesion voids the +1 reprieve


def test_honors_surrender_17_25_and_17_26():
    # 17.25 / 17.26: a rolled SURR sticks unless the largest unit's Basic Morale is
    # +1 or better -- but that reprieve is void with collapsed cohesion (17.26a) or an
    # enemy at 3x strength (17.26b).
    from game.engine import _honors_surrender
    assert _honors_surrender(0, -5, False) is True        # 17.25: morale < +1 always surrenders
    assert _honors_surrender(-3, 0, False) is True        # 17.25: bad morale, still surrenders
    assert _honors_surrender(1, -5, False) is False       # 17.26: +1 morale shrugs SURR off
    assert _honors_surrender(3, -10, False) is False      # 17.26: +3 morale, cohesion > -11, shrugs off
    assert _honors_surrender(1, -11, False) is True       # 17.26a: cohesion -11 voids the reprieve
    assert _honors_surrender(2, -12, False) is True       # 17.26a: worse cohesion, void
    assert _honors_surrender(1, -5, True) is True         # 17.26b: enemy 3x voids the reprieve


def _lone_hex_state(units, supplies=(), *, seed=1):
    from game.events import Phase
    from game.movement import TerrainMap
    from game.state import GameState, VP
    from game.terrain import Terrain
    ammo = sum(s.ammo for s in supplies)
    fuel = sum(s.fuel for s in supplies)
    return GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=seed,
                     weather="clear", vp=VP(),
                     terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR}),
                     control={}, units=tuple(units), target_hex=(0, 0), supplies=tuple(supplies),
                     consumed={"AMMO": 0, "FUEL": 0},
                     initial_supply={"AMMO": ammo, "FUEL": fuel})


def test_all_dry_defenders_capitulate_15_15():
    # 15.15: if EVERY non-Phasing defender in an assaulted hex is out of Close-Assault
    # ammunition, the stack automatically Surrenders en masse. With no reachable dump
    # the garrison cannot draw ammo, so _defenders_capitulate fires; a supplied stack
    # (a dump in-hex) does not.
    from game.engine import _Run, _defenders_capitulate
    from game.state import SupplyUnit, Unit
    from game.terrain import Mobility

    def garrison(coh=0):
        return Unit("G", Side.ALLIED, (0, 0), (StepRecord("g", 6),), mobility=Mobility.FOOT,
                    cpa=10, stacking_points=1, oca=2, dca=2, morale=2, cohesion=coh)
    dry = _Run(_lone_hex_state([garrison()]))
    assert _defenders_capitulate(dry, [garrison()]) is True          # cut off, no ammo -> 15.15

    dump = SupplyUnit("DUMP", Side.ALLIED, (0, 0), ammo=40, fuel=0)
    fed = _Run(_lone_hex_state([garrison()], supplies=[dump]))
    assert _defenders_capitulate(fed, [garrison()]) is False         # supplied -> fights on


def test_collapsed_cohesion_defender_capitulates_15_88():
    # 15.88: an assaulted unit with Cohesion -17 or worse automatically Surrenders,
    # even fully supplied (the Largest Unit Rule 17.27 keys off the biggest defender).
    from game.engine import _Run, _defenders_capitulate
    from game.state import SupplyUnit, Unit
    from game.terrain import Mobility

    broken = Unit("B", Side.ALLIED, (0, 0), (StepRecord("b", 6),), mobility=Mobility.FOOT,
                  cpa=10, stacking_points=1, oca=2, dca=2, morale=3, cohesion=-17)
    dump = SupplyUnit("DUMP", Side.ALLIED, (0, 0), ammo=40, fuel=0)
    r = _Run(_lone_hex_state([broken], supplies=[dump]))
    assert _defenders_capitulate(r, [broken]) is True

    steady = replace(broken, cohesion=-16)
    r2 = _Run(_lone_hex_state([steady], supplies=[dump]))
    assert _defenders_capitulate(r2, [steady]) is False              # -16 does not auto-surrender


def test_starved_garrison_surrenders_in_close_assault_15_15():
    # End-to-end: a cut-off, dry defender that is assaulted is eliminated by en-masse
    # Surrender (15.15), not merely reduced. The COMBAT_RESOLVED event marks it as a
    # defender surrender and the garrison loses all its steps.
    from game.engine import _Run, _resolve_combat
    from game.state import SupplyUnit, Unit
    from game.terrain import Mobility

    attacker = Unit("A", Side.AXIS, (1, 0), (StepRecord("a", 6),), mobility=Mobility.FOOT,
                    cpa=10, stacking_points=1, oca=3, dca=3, morale=1, cohesion=0)
    garrison = Unit("G", Side.ALLIED, (0, 0), (StepRecord("g", 6),), mobility=Mobility.FOOT,
                    cpa=10, stacking_points=1, oca=2, dca=2, morale=2, cohesion=0)
    dump = SupplyUnit("AXDUMP", Side.AXIS, (1, 0), ammo=40, fuel=0)   # only the attacker is supplied
    r = _Run(_lone_hex_state([attacker, garrison], supplies=[dump]))
    _resolve_combat(r, Side.AXIS, "AXIS/Front", [attacker], [garrison], (0, 0), set())
    resolved = [e for e in r.events if e.kind == EventKind.COMBAT_RESOLVED]
    assert resolved and resolved[-1].payload["surrender"] == "defender"
    assert r.state.unit("G").strength == 0                           # garrison captured en masse


def test_barrage_fires_at_adjacent_enemy():
    # artillery barrages an adjacent enemy infantry hex (rule 12); the barrage is
    # resolved against the target's class and can pin / cost steps.
    from game.engine import _Run, _barrage_step
    from game.events import EventKind, Phase
    from game.movement import TerrainMap
    from game.state import GameState, SupplyUnit, Unit, VP
    from game.terrain import Mobility, Terrain
    terr = {(q, 0): Terrain.CLEAR for q in range(4)}
    arty = Unit("AR", Side.AXIS, (0, 0), (StepRecord("ar", 8),), mobility=Mobility.MOTORIZED,
                cpa=20, stacking_points=1, oca=0, dca=1, barrage=15, vulnerability=5)
    inf = Unit("IN", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=1, oca=2, dca=2)
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=40, fuel=60)
    st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS,
                   seed=3, weather="clear", vp=VP(),
                   terrain=TerrainMap(terrain=terr), control={}, units=(arty, inf),
                   target_hex=(3, 0), supplies=(dump,),
                   consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 40, "FUEL": 60})
    r = _Run(st)
    _barrage_step(r, Side.AXIS, Side.ALLIED, set())
    resolved = [e for e in r.events if e.kind == EventKind.BARRAGE_RESOLVED]
    assert resolved and resolved[0].payload["target_class"] == "infantry"
    assert resolved[0].payload["actual"] == 12          # 15 x 8 / 10 = 12 Actual Barrage Points


def test_anti_armor_fire_damages_adjacent_armor():
    # an AT unit fires anti-armor at an adjacent enemy tank; the tank loses TOE to
    # absorb the damage (rule 14). Needs ammo in range to fire (14.24).
    from game.engine import _Run, _anti_armor_step
    from game.events import Phase
    from game.movement import TerrainMap
    from game.state import GameState, SupplyUnit, Unit, VP
    from game.terrain import Mobility, Terrain
    terr = {(q, 0): Terrain.CLEAR for q in range(4)}
    at = Unit("AT", Side.AXIS, (0, 0), (StepRecord("at", 8),), mobility=Mobility.MOTORIZED,
              cpa=20, stacking_points=1, oca=1, dca=2, anti_armor=6, vulnerability=2)
    tank = Unit("TK", Side.ALLIED, (1, 0), (StepRecord("tk", 8),), mobility=Mobility.VEHICLE,
                cpa=25, stacking_points=1, oca=3, dca=3, is_tank=True, armor_protection=3)
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=40, fuel=60)
    st = GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS,
                   seed=5, weather="clear", vp=VP(),
                   terrain=TerrainMap(terrain=terr), control={}, units=(at, tank),
                   target_hex=(3, 0), supplies=(dump,),
                   consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 40, "FUEL": 60})
    r = _Run(st)
    _anti_armor_step(r, Side.AXIS, Side.ALLIED, set())
    assert r.state.unit("TK").strength < 8             # tank absorbed anti-armor damage
    # 14.24 / [50.2]: anti-armor fire draws the anti-armor rate (3) x TOE (8) = 24 Ammo,
    # NOT the close-assault rate -- the faithful chart value from data/logistics_rates.json.
    assert r.state.supply("D").ammo == 40 - 24


def test_combined_arms_penalty():
    from game.engine import _combined_arms_penalty
    from game.terrain import Mobility

    def mk(uid, n, **kw):
        return __import__("game.state", fromlist=["Unit"]).Unit(
            uid, Side.AXIS, (0, 0), (StepRecord("s", n),), mobility=Mobility.FOOT,
            cpa=25, stacking_points=1, oca=2, dca=2, **kw)
    tank = lambda n: mk("t" + str(n), n, is_tank=True, armor_protection=4)
    inf = lambda n: mk("i" + str(n), n)
    recce = lambda n: mk("r" + str(n), n, armor_protection=2)   # armor but NOT a tank
    assert _combined_arms_penalty([tank(7), inf(5)]) == 1        # 2 unsupported -> ceil(2/3)
    assert _combined_arms_penalty([tank(3), inf(21)]) == 0       # fully supported
    assert _combined_arms_penalty([tank(4)]) == 2               # rulebook "/3" reading (§1)
    assert _combined_arms_penalty([tank(20)]) == 4              # capped at 4
    assert _combined_arms_penalty([recce(10)]) == 0            # recce/SP exempt (15.4)
    assert _combined_arms_penalty([tank(6), recce(6)]) == 2     # recce does not support tanks


def _combat_state(units, supplies):
    from game.events import Phase
    from game.movement import TerrainMap
    from game.state import GameState, VP
    from game.terrain import Terrain
    terr = {(q, 0): Terrain.CLEAR for q in range(4)}
    return GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=1,
                     weather="clear", vp=VP(),
                     terrain=TerrainMap(terrain=terr), control={}, units=tuple(units),
                     target_hex=(3, 0), supplies=tuple(supplies),
                     consumed={"AMMO": 0, "FUEL": 0},
                     initial_supply={"AMMO": sum(s.ammo for s in supplies),
                                     "FUEL": sum(s.fuel for s in supplies)})


def test_combat_boundary_guards_exploits():
    # duplicate attacker ids must not multiply strength; a non-combat HQ must not
    # attack; a hex must not be close-assaulted twice in one segment (15.23/15.24).
    from game.engine import _Run, _combat
    from game.events import EventKind, Phase
    from game.movement import TerrainMap
    from game.state import SupplyUnit, Unit
    from game.terrain import Mobility, Terrain
    atk = Unit("A", Side.AXIS, (0, 0), (StepRecord("i", 6),), mobility=Mobility.FOOT,
               cpa=25, stacking_points=1, oca=3, dca=2)
    hq = Unit("HQ", Side.AXIS, (0, 0), (StepRecord("hq", 1),), mobility=Mobility.MOTORIZED,
              cpa=30, stacking_points=0, oca=5, dca=1, is_combat=False)
    dfd = Unit("D", Side.ALLIED, (1, 0), (StepRecord("i", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=1, oca=1, dca=2)
    supplies = (SupplyUnit("DA", Side.AXIS, (0, 0), ammo=40, fuel=60),
                SupplyUnit("DL", Side.ALLIED, (1, 0), ammo=40, fuel=60))
    from game.policy import AttackOrder, Policy

    class Exploit(Policy):
        def movement(self, s, side):
            return []

        def combat(self, s, side):
            return [AttackOrder(("A", "A", "HQ"), (1, 0)), AttackOrder(("A",), (1, 0))] \
                if side == Side.AXIS else []
    r = _Run(_combat_state([atk, hq, dfd], supplies))
    _combat(r, {Side.AXIS: Exploit(), Side.ALLIED: Exploit()}, Side.AXIS)
    resolved = [e for e in r.events if e.kind == EventKind.COMBAT_RESOLVED]
    assert len(resolved) == 1                                # the repeat assault was rejected
    assert resolved[0].payload["attackers"] == ["A"]         # deduped + HQ (non-combat) dropped


def test_only_combat_units_hold_ground():
    # a lone non-combat HQ must not capture a hex (rule: control by combat units)
    from game.engine import _Run, _record_control
    from game.events import Control
    from game.state import Unit
    from game.terrain import Mobility
    hq = Unit("HQ", Side.AXIS, (2, 0), (StepRecord("hq", 1),), mobility=Mobility.MOTORIZED,
              cpa=30, stacking_points=0, oca=0, dca=1, is_combat=False)
    r = _Run(_combat_state([hq], []))
    _record_control(r)
    assert r.state.control_of((2, 0)) == Control.NEUTRAL     # HQ alone does not capture


def test_cohesion_changed_event_applies():
    from game.apply import apply as apply_event
    from game.events import Event, EventKind, Phase
    s = coastal_corridor()
    uid = s.units[0].id
    e = Event(0, 1, Phase.COMBAT, Side.AXIS, "x", EventKind.COHESION_CHANGED,
              {"unit_id": uid, "delta": -3})
    assert apply_event(s, e).unit(uid).cohesion == -3


def test_cohesion_decays_on_heavy_combat_losses():
    # a 30%+ close-assault loss disorganizes the unit (rule 15.87); recovery is
    # deferred, so Cohesion accumulates downward over repeated combats.
    from game.events import EventKind
    from game.scenario import battle_for_tobruk
    res = run(battle_for_tobruk(seed=1), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    changes = [e for e in res.events if e.kind == EventKind.COHESION_CHANGED]
    assert changes and all(e.payload["delta"] == -3 for e in changes)
    assert res.final.unit(changes[0].payload["unit_id"]).cohesion < 0


def test_engine_rejects_illegal_orders_without_mutating_state():
    result = run(coastal_corridor(), axis=_BadPolicy(), allied=ScriptedPolicy(Side.AXIS))
    rejected = [e for e in result.events if e.kind == EventKind.ORDER_REJECTED]
    assert rejected and all("reason" in e.payload for e in rejected)
    assert result.final.unit("DAK-5le").hex == (0, 0)      # never moved
    assert result.final.unit("IT-Ariete").hex == (1, 1)


# --- Retreat Before Assault (rule 13.0) --------------------------------------

def _rba_state(units):
    from game.events import Phase
    from game.movement import TerrainMap
    from game.state import GameState, VP
    from game.terrain import Terrain
    # A long clear row; the objective sits far off (20,0) so none of the defenders
    # count as the garrison anchor -- they are all free reserves for rule 13.
    terr = {(q, 0): Terrain.CLEAR for q in range(8)}
    return GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS,
                     seed=1, weather="clear", vp=VP(),
                     terrain=TerrainMap(terrain=terr), control={}, units=tuple(units),
                     target_hex=(20, 0), supplies=(),
                     consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 0, "FUEL": 0})


def _rba_infantry(uid, side, hex_, cohesion=0):
    from game.state import Unit
    from game.terrain import Mobility
    return Unit(uid, side, hex_, (StepRecord("in", 4),), mobility=Mobility.FOOT,
                cpa=10, stacking_points=1, oca=3, dca=3, cohesion=cohesion)


def test_unpinned_defender_slips_before_assault():
    # rule 13.0/13.1: after barrage, a non-phasing, UNPINNED unit in contact may
    # Retreat Before Assault -- slipping out of contact so the ensuing Close Assault
    # cannot reach it. A Pinned neighbour (12.44) may NOT and stays to be assaulted.
    from game.engine import _Run, _retreat_before_assault
    from game.hexmap import is_adjacent
    from game.events import EventKind
    atk = _rba_infantry("A", Side.AXIS, (2, 0))
    d_free = _rba_infantry("D_free", Side.ALLIED, (3, 0))
    d_pin = _rba_infantry("D_pin", Side.ALLIED, (1, 0))
    r = _Run(_rba_state([atk, d_free, d_pin]))
    # AXIS is the phasing attacker; ALLIED is the non-phasing defender.
    _retreat_before_assault(r, ScriptedPolicy(Side.AXIS), Side.ALLIED, Side.AXIS, {"D_pin"})
    moved = r.state.unit("D_free")
    assert moved.hex != (3, 0)                              # it slipped
    assert not is_adjacent(moved.hex, (2, 0))               # ...out of contact with the attacker
    assert r.state.unit("D_pin").hex == (1, 0)             # the Pinned unit stayed
    assert any(e.kind == EventKind.UNIT_MOVED and e.payload["unit_id"] == "D_free"
               for e in r.events)


def test_pinned_unit_proposal_is_rejected_at_the_boundary():
    # even if a policy proposes it, the engine refuses to retreat a Pinned unit (13.1).
    from game.engine import _Run, _retreat_before_assault
    from game.events import EventKind
    from game.policy import MoveOrder, Policy

    class _RetreatPinned(Policy):
        def movement(self, state, side):
            return []

        def combat(self, state, side):
            return []

        def retreat_before_assault(self, state, side, pinned):
            return [MoveOrder("D_pin", (0, 0))]

    atk = _rba_infantry("A", Side.AXIS, (2, 0))
    d_pin = _rba_infantry("D_pin", Side.ALLIED, (1, 0))
    r = _Run(_rba_state([atk, d_pin]))
    _retreat_before_assault(r, _RetreatPinned(), Side.ALLIED, Side.AXIS, {"D_pin"})
    assert r.state.unit("D_pin").hex == (1, 0)             # never moved
    rej = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert rej and "pinned" in rej[0].payload["reason"]
    assert rej[0].payload["order"] == "retreat_before_assault"


def test_broken_cohesion_unit_may_not_retreat_before_assault():
    # rule 13.1: a unit at Cohesion Level -26 or worse may not Retreat Before Assault.
    from game.engine import _Run, _retreat_before_assault
    from game.events import EventKind
    from game.policy import MoveOrder, Policy

    class _RetreatBroken(Policy):
        def movement(self, state, side):
            return []

        def combat(self, state, side):
            return []

        def retreat_before_assault(self, state, side, pinned):
            return [MoveOrder("D_broken", (4, 0))]

    atk = _rba_infantry("A", Side.AXIS, (2, 0))
    d_broken = _rba_infantry("D_broken", Side.ALLIED, (3, 0), cohesion=-26)
    r = _Run(_rba_state([atk, d_broken]))
    _retreat_before_assault(r, _RetreatBroken(), Side.ALLIED, Side.AXIS, set())
    assert r.state.unit("D_broken").hex == (3, 0)          # held -- too broken to retreat
    rej = [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]
    assert rej and "cohesion" in rej[0].payload["reason"]
