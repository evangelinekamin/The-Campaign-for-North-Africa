"""Shared fixture for the two [25.14] "is the mechanism still live?" guards.

tests/test_ports.py (the Benghazi-rear harbour throttle) and tests/test_convoys.py (the convoy
faucet) each own a guard whose thesis is that their own throttle must not silently GATE OFF rule
[25.14]. Both used to state it as a COUNT over the run's own events, and both counts turned out to
be tautological -- `reductions == scored` where `scored` was the very conjunction engine._batter_fort
uses to decide whether to emit a reduction, so the assertion held by construction and passed with
the whole facility-barrage path neutered.

The behavioural form they were restated to needs one thing the scripted policies never supply in
twelve turns: a gun standing next to the wall. That construction lives here, once, rather than
drifting in two copies -- the same reason tests/baselines.py is the one home of the benchmark
signatures. It belongs to the tests, not to the engine: nothing in game/ builds it.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords
from game.events import Side
from game.hexmap import neighbors
from game.state import GameState

TOBRUK = coords.to_axial(coords.parse("C4807"))

# [11.32] Actual = round-half-up(Raw / 10), and 21 Actual Barrage Points is the LAST column of the
# [41.5] Fortification row -- the 21+ bracket, where all 36 sequential codes read "Reduced". Massing
# to it is what makes these guards seed-independent; it is not a magnitude anyone chose for effect.
RAW_FOR_THE_TOP_COLUMN = 205


def stand_the_siege_train_beside_tobruk(state: GameState) -> GameState:
    """Put the Axis siege batteries, and the dump they draw their ammunition from, in one hex
    adjacent to Tobruk.

    [12.32] "Artillery units in a Forward position may combine Barrage strengths in one Barrage
    against a given Target", so one hex is the faithful arrangement rather than a convenience.
    Guns are taken in the state's own (deterministic) order until their combined Raw Barrage clears
    RAW_FOR_THE_TOP_COLUMN. Raises if the state fields no siege train -- an empty fixture must fail
    loudly rather than make a guard vacuous, which is the exact defect these guards were restated
    to fix.
    """
    beside = next(nb for nb in neighbors(TOBRUK) if nb in state.terrain.terrain)
    guns: list[str] = []
    raw = 0
    for u in state.living(Side.AXIS):
        if raw >= RAW_FOR_THE_TOP_COLUMN:
            break
        if u.barrage > 0 and u.is_combat:
            guns.append(u.id)
            raw += u.raw_barrage
    if raw < RAW_FOR_THE_TOP_COLUMN:
        raise AssertionError(
            f"the Axis fields only {raw} Raw Barrage Points of surviving artillery; "
            "this fixture cannot reach the [41.5] 21+ column and the guard would be vacuous")
    ammo = max((d for d in state.supplies if d.side is Side.AXIS), key=lambda d: d.ammo)
    return replace(
        state,
        units=tuple(replace(u, hex=beside) if u.id in guns else u for u in state.units),
        supplies=tuple(replace(d, hex=beside) if d.id == ammo.id else d for d in state.supplies))
