"""Commonwealth off-shore naval bombardment -- the P5 Step-5 mirror-completeness/camera piece
(rule 30.2). A CW ship stationed in a coastal hex within Range 100 of Alexandria (30.15, a
seed-time constraint) fires ONCE per Operations Stage (30.24): its Gun Rating goes in as Actual
Barrage Points with NO ammo draw (30.22) on the 12.6 CRT, a capital ship (BB/CA) reaching one hex
further at half strength (30.21); a ship that fires then spends two Operations Stages refitting in
Alexandria (30.25). Off the crackability path (the CW is the Tobruk DEFENDER); ship damage/repair
(30.3) and the Chariot raid (30.4) are deferred. Default GameState.naval=() -> byte-identical."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import apply
from game.engine import _naval_bombardment, _naval_target, _Run, determinism_signature, run
from game.events import Event, EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival, siege_of_tobruk
from game.state import GameState, NavalUnit, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain


def _foe(hex_=(1, 0), strength=6):
    return Unit("AX", Side.AXIS, hex_, (StepRecord("in", strength),), mobility=Mobility.FOOT,
                cpa=10, stacking_points=2, oca=5, dca=8)


def _state(ships=(), foes=None, *, seed=0) -> GameState:
    """A two-hex state: an Axis stack the Commonwealth fleet stands off and bombards."""
    if foes is None:
        foes = (_foe(),)
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR}
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.ALLIED, seed=seed,
        weather="clear", vp=VP(), terrain=TerrainMap(terrain=terr, fortifications={}),
        control={}, units=tuple(foes), target_hex=(1, 0), supplies=(), consumed={},
        initial_supply={}, naval=tuple(ships))


def _ship(hex_=(1, 0), gun=8, kind="CL", cooldown=0, side=Side.ALLIED):
    return NavalUnit(f"HMS-{kind}", side, hex_, gun_rating=gun, aa_rating=4, kind=kind,
                     port_cooldown=cooldown)


# --- the state field ---------------------------------------------------------

def test_naval_defaults_empty():
    assert GameState.__dataclass_fields__["naval"].default == ()
    for s in (coastal_corridor(), rommels_arrival(), siege_of_tobruk()):
        assert s.naval == ()


# --- the bombardment beat: barrage-points in, pin joins the 12.44 set ---------

def test_bombardment_fires_pins_and_folds_cooldown():
    r = _Run(_state(ships=(_ship(gun=8),), seed=0))       # seed 0 -> 4,4 -> a Pin on infantry
    pinned: set = set()
    _naval_bombardment(r, Side.ALLIED, pinned)
    nb = [e for e in r.events if e.kind == EventKind.NAVAL_BOMBARDMENT]
    assert len(nb) == 1
    p = nb[0].payload
    assert p["ship_id"] == "HMS-CL" and p["target"] == [1, 0] and p["actual"] == 8
    assert p["target_unit"] == "AX" and p["half"] is False
    assert p["pinned"] is True and "AX" in pinned          # 12.44: joined the pin set
    assert r.state.naval_of("HMS-CL").port_cooldown == 2   # 30.25: two OpStages in Alexandria


def test_pin_set_membership_tracks_the_payload():
    # The wiring is exact regardless of the die: pinned iff the CRT pinned, loss iff CRT loss.
    r = _Run(_state(ships=(_ship(gun=8),), seed=0))
    pinned: set = set()
    _naval_bombardment(r, Side.ALLIED, pinned)
    p = [e for e in r.events if e.kind == EventKind.NAVAL_BOMBARDMENT][0].payload
    assert ("AX" in pinned) == bool(p["pinned"])
    losses = [e for e in r.events if e.kind == EventKind.STEP_LOST]
    assert len(losses) == (1 if p["loss"] > 0 else 0)


def test_bombardment_draws_no_ammo():
    # 30.22: the Gun Rating fires with no supply behind it -- no SUPPLY_CONSUMED at the seam.
    r = _Run(_state(ships=(_ship(gun=8),), seed=0))
    _naval_bombardment(r, Side.ALLIED, set())
    assert not any(e.kind == EventKind.SUPPLY_CONSUMED for e in r.events)


def test_heavy_gun_sheds_a_step_as_naval_role():
    r = _Run(_state(ships=(_ship(gun=16),), foes=(_foe(strength=6),), seed=0))  # 4,4 -> loss 1
    _naval_bombardment(r, Side.ALLIED, set())
    loss = [e for e in r.events if e.kind == EventKind.STEP_LOST]
    assert len(loss) == 1 and loss[0].payload["role"] == "naval"
    assert loss[0].payload["unit_id"] == "AX"
    assert r.state.unit("AX").strength == 6 - loss[0].payload["amount"]


# --- 30.25 cooldown: refit gate + the OpStage tick ---------------------------

def test_ship_in_refit_does_not_fire():
    r = _Run(_state(ships=(_ship(cooldown=1),), seed=0))
    _naval_bombardment(r, Side.ALLIED, set())
    assert not any(e.kind == EventKind.NAVAL_BOMBARDMENT for e in r.events)


def test_refit_ticks_down_at_the_opstage_boundary():
    s = _state(ships=(_ship(cooldown=2),), seed=0)
    stage = Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", EventKind.STAGE_ADVANCED, {"stage": 2})
    assert apply(s, stage).naval_of("HMS-CL").port_cooldown == 1   # 30.25: one stage down
    turn = Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", EventKind.TURN_ADVANCED, {"turn": 2})
    assert apply(s, turn).naval_of("HMS-CL").port_cooldown == 1
    # a ready ship stays ready (floored at 0)
    s0 = _state(ships=(_ship(cooldown=0),))
    assert apply(s0, stage).naval_of("HMS-CL").port_cooldown == 0


def test_fires_only_for_the_owning_side():
    r = _Run(_state(ships=(_ship(side=Side.ALLIED),), seed=0))
    _naval_bombardment(r, Side.AXIS, set())               # the Axis phasing segment
    assert not any(e.kind == EventKind.NAVAL_BOMBARDMENT for e in r.events)


# --- 30.21 capital-ship reach ------------------------------------------------

def test_capital_ship_reaches_one_hex_further_at_half():
    # own hex (0,0) empty; the Axis stack is adjacent at (1,0) -- a BB reaches it at half gun.
    ship = _ship(hex_=(0, 0), gun=8, kind="BB")
    tgt = _naval_target(_state(ships=(ship,)), Side.ALLIED, ship)
    assert tgt is not None
    hexc, victim, actual = tgt
    assert hexc == (1, 0) and victim.id == "AX" and actual == 4   # 30.21: half of 8


def test_light_ship_has_no_extended_reach():
    ship = _ship(hex_=(0, 0), gun=8, kind="CL")           # own hex empty, not a capital ship
    assert _naval_target(_state(ships=(ship,)), Side.ALLIED, ship) is None
    r = _Run(_state(ships=(ship,), seed=0))
    _naval_bombardment(r, Side.ALLIED, set())
    assert not any(e.kind == EventKind.NAVAL_BOMBARDMENT for e in r.events)


def test_no_target_no_fire_no_cooldown():
    ship = _ship(hex_=(0, 0), kind="BB")
    r = _Run(_state(ships=(ship,), foes=(), seed=0))       # nothing to shoot
    _naval_bombardment(r, Side.ALLIED, set())
    assert not any(e.kind == EventKind.NAVAL_BOMBARDMENT for e in r.events)
    assert r.state.naval_of("HMS-BB").port_cooldown == 0   # never fired, no refit owed


# --- the fold in isolation ---------------------------------------------------

def test_naval_bombardment_fold_sets_cooldown_only():
    s = _state(ships=(_ship(gun=8),))
    e = Event(0, 1, Phase.COMBAT, Side.ALLIED, "ALLIED/Fleet", EventKind.NAVAL_BOMBARDMENT,
              {"ship_id": "HMS-CL", "target": [1, 0], "actual": 8, "target_class": "infantry",
               "target_unit": "AX", "pinned": True, "loss": 0, "half": False})
    s2 = apply(s, e)
    assert s2.naval_of("HMS-CL").port_cooldown == 2
    assert s2.units == s.units                             # the pin/loss ride elsewhere


# --- byte-identity: naval=() scenarios stay silent and deterministic ---------

def test_scenarios_naval_silent_and_byte_identical():
    for scen in (rommels_arrival(seed=1941), siege_of_tobruk(seed=1941)):
        a = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        b = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert determinism_signature(a.events) == determinism_signature(b.events)
        assert not any(e.kind == EventKind.NAVAL_BOMBARDMENT for e in a.events)
