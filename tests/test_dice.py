"""THE INSTRUMENT (game.dice) -- independent, deterministic dice streams per subsystem.

The engine used to draw every die in the game from ONE random.Random. Subsystems draw
CONDITIONALLY -- engine._interdict rolls its two [41.66] dice only when an InterdictionOrder
covers the lane -- so changing the NUMBER of draws in one subsystem reshuffled the dice EVERY
OTHER SUBSYSTEM saw for the rest of the war. Every A/B that toggled a conditionally-drawing
feature was measuring that reshuffle. Malta was measured through it and recorded as "causally
inert"; it is in fact one of the strongest levers in the engine.

The load-bearing test here is test_a_conditional_interdiction_draw_shifts_no_other_subsystem,
and its companion test_the_property_test_catches_the_shared_stream_bug re-installs the OLD
shared-stream engine and proves the property test FAILS against it. That is the guarantee that
this suite would have caught the bug that cost us the measurement.
"""
from __future__ import annotations

import random
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import dice, engine
from game.dice import SUBSYSTEMS, DiceBox, stream_seed
from game.engine import determinism_signature, run
from game.events import EventKind, Side
from game.policy import ScriptedPolicy
from game.scenario import rommels_arrival
from game.state import InterdictionOrder

AXIS_LANE = "1"          # rommels_arrival's Axis Mediterranean convoy lane (scenario._rommel_convoys)


# --- the derivation ----------------------------------------------------------------------------

def test_every_subsystem_gets_its_own_distinct_stream():
    """15 subsystems, 15 different sequences. If two shared a seed they would roll in lockstep
    and a 'correlated' engine is only marginally better than a desynchronised one."""
    box = DiceBox(1941)
    draws = {sub: [box.d6(sub) for _ in range(40)] for sub in SUBSYSTEMS}
    assert len(SUBSYSTEMS) == 15                                      # + air_bombard ([41.5] harbour bombing)
    assert len({tuple(v) for v in draws.values()}) == len(SUBSYSTEMS)


def test_the_same_seed_rebuilds_the_same_streams():
    a, b = DiceBox(7), DiceBox(7)
    assert [a.d6(s) for s in SUBSYSTEMS] == [b.d6(s) for s in SUBSYSTEMS]
    assert DiceBox(7).d6("weather") is not None
    assert [DiceBox(8).d6(s) for s in SUBSYSTEMS] != [DiceBox(7).d6(s) for s in SUBSYSTEMS]


def test_stream_seeds_are_stable_across_processes():
    """The stream seed MUST NOT come from the builtin hash(), which is salted per process
    (PYTHONHASHSEED): a seed derived from it would give the same master seed a different game in
    a different process, which is the exact opposite of what this module is for. Two subprocesses
    with hostile, differing hash salts must agree."""
    prog = ("import sys; sys.path.insert(0, '.'); from game.dice import stream_seed, SUBSYSTEMS; "
            "print([stream_seed(1941, s) for s in SUBSYSTEMS])")
    out = [subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True,
                          cwd=str(Path(__file__).resolve().parent.parent),
                          env={"PYTHONHASHSEED": salt, "PATH": "/usr/bin:/bin"},
                          check=True).stdout
           for salt in ("0", "1", "12345")]
    assert out[0] == out[1] == out[2]
    assert stream_seed(1941, "weather") != stream_seed(1941, "combat")
    assert stream_seed(1941, "weather") != stream_seed(1942, "weather")


def test_an_unknown_subsystem_is_rejected():
    """A typo must not silently share another subsystem's dice -- it must fail loudly."""
    box = DiceBox(1)
    with pytest.raises(KeyError, match="unknown dice subsystem"):
        box.d6("wether")
    with pytest.raises(KeyError, match="unknown dice subsystem"):
        box.load("interdction", random.Random(1))


def test_load_pins_one_stream_and_leaves_the_others_alone():
    """The test seam. Pinning the repair die must not bend the weather."""
    box, ref = DiceBox(99), DiceBox(99)
    box.load("repair", random.Random(4))
    assert [box.d6("repair") for _ in range(5)] != [ref.d6("repair") for _ in range(5)]
    assert [box.d6(s) for s in SUBSYSTEMS if s != "repair"] == \
           [ref.d6(s) for s in SUBSYSTEMS if s != "repair"]


# --- the invariant that never bends ------------------------------------------------------------

def _play(state):
    return run(state, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))


def test_same_seed_two_runs_stay_byte_identical():
    """Determinism. This is the one property that does not bend, and per-subsystem streams must
    not cost us a byte of it."""
    a, b = _play(rommels_arrival(seed=1941)), _play(rommels_arrival(seed=1941))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert _play(rommels_arrival(seed=7)).events != a.events      # and the seed still matters


def test_a_run_reproduces_in_a_fresh_process():
    """Determinism across processes, not merely within one -- the guard that a stream seed can
    never sneak back to a salted hash()."""
    prog = ("import sys, hashlib; sys.path.insert(0, '.'); "
            "from game.engine import determinism_signature, run; "
            "from game.events import Side; from game.policy import ScriptedPolicy; "
            "from game.scenario import rommels_arrival; "
            "res = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED)); "
            "print(hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12])")
    sigs = [subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True,
                           cwd=str(Path(__file__).resolve().parent.parent),
                           env={"PYTHONHASHSEED": salt, "PATH": "/usr/bin:/bin"},
                           check=True).stdout.strip()
            for salt in ("0", "31337")]
    assert sigs[0] == sigs[1] and len(sigs[0]) == 12


# --- THE KEY PROPERTY --------------------------------------------------------------------------

def _bomb(state, points: int):
    """The same scenario with every Axis convoy turn under `points` of [41.66] bombing."""
    orders = tuple(InterdictionOrder(AXIS_LANE, t, points)
                   for t in range(1, state.max_turns + 1))
    return replace(state, interdictions=orders)


def _log_besides_interdiction(events):
    """Every event except the CONVOY_INTERDICTED marker, minus its sequence number. The marker is
    a pure marker (apply() returns identity), so if interdiction denies no cargo, two runs that
    differ ONLY in whether it rolled its dice must agree here to the byte."""
    return [(e.turn, e.stage, e.phase, e.side, e.actor, e.kind, e.payload, e.rng_draws)
            for e in events if e.kind is not EventKind.CONVOY_INTERDICTED]


def _interdiction_dice(events):
    return [e.rng_draws for e in events if e.kind is EventKind.CONVOY_INTERDICTED]


def test_a_conditional_interdiction_draw_shifts_no_other_subsystem():
    """🔴 THE TEST THAT WOULD HAVE CAUGHT IT.

    bomb=1 is the [41.66] CRT's flat-0% column: it DRAWS two dice and denies nothing. So a run
    with 12 interdiction orders at bomb=1 and a run with none differ in EXACTLY ONE way -- the
    interdiction subsystem drew dice in one and not the other. The cargo, and therefore the whole
    unfolding of the war, is identical.

    Under the old single shared rng those extra draws re-indexed the weather, breakdown, morale
    and every CRT roll for the rest of the game. Under per-subsystem streams they must be
    invisible outside interdiction. Every other event -- every other die -- must match to the byte."""
    base = rommels_arrival(seed=1941)
    silent = _play(base)                                   # no orders -> interdiction draws nothing
    drawing = _play(_bomb(base, 1))                        # 12 orders -> it draws, and denies 0%

    assert not _interdiction_dice(silent.events), "the control arm must draw no interdiction dice"
    rolled = _interdiction_dice(drawing.events)
    assert rolled, "the probe arm must actually roll -- otherwise this test proves nothing"
    assert all(len(d) == 2 for d in rolled)
    strikes = [e for e in drawing.events if e.kind is EventKind.CONVOY_INTERDICTED]
    assert all(e.payload["pct_lost"] == 0 for e in strikes), "bomb=1 is the flat-0% column"

    assert _log_besides_interdiction(silent.events) == _log_besides_interdiction(drawing.events)
    # ...and the war ends in the same place. (interdictions is the INPUT schedule we varied, not
    # an outcome, so it is stripped from both sides before the states are compared.)
    assert silent.winner == drawing.winner
    assert replace(silent.final, interdictions=()) == replace(drawing.final, interdictions=())


def test_the_property_test_catches_the_shared_stream_bug():
    """The proof that the test above has teeth: re-install the OLD engine -- one random.Random
    shared by every subsystem -- and the property must FAIL. A regression guard that guards the
    guard. If someone collapses the streams back into one, this test goes red first."""

    class _SharedStream(DiceBox):                 # the pre-fix engine, exactly: one rng for all
        def __init__(self, seed: int) -> None:
            super().__init__(seed)
            shared = random.Random(seed)
            self._streams = {sub: shared for sub in SUBSYSTEMS}

    base = rommels_arrival(seed=1941)
    original = engine.DiceBox
    engine.DiceBox = _SharedStream
    try:
        silent, drawing = _play(base), _play(_bomb(base, 1))
    finally:
        engine.DiceBox = original

    assert _interdiction_dice(drawing.events), "the probe must still roll on the old engine"
    # THE BUG: two extra dice per convoy, drawn off the ONE stream, re-index every later roll.
    assert _log_besides_interdiction(silent.events) != _log_besides_interdiction(drawing.events), \
        "the shared-stream engine must desynchronise -- if it does not, this probe is too weak"


def test_the_malta_ab_now_compares_like_with_like():
    """What the fix buys the measurement. bomb=1 and bomb=500 seed the SAME number of orders, so
    interdiction consumes its stream at the same rate and BOTH ARMS ROLL THE IDENTICAL DICE --
    the arms differ only in which [41.66] column those dice are read on. That is an A/B: one
    variable. (The two runs then diverge downstream, because bomb=500 really does sink cargo.
    That divergence is the SIGNAL. Report it over N seeds, never one -- see game/dice.py.)"""
    base = rommels_arrival(seed=1941)
    weak, strong = _play(_bomb(base, 1)), _play(_bomb(base, 500))

    assert _interdiction_dice(weak.events) == _interdiction_dice(strong.events)
    assert all(e.payload["pct_lost"] == 0 for e in weak.events
               if e.kind is EventKind.CONVOY_INTERDICTED)
    assert any(e.payload["pct_lost"] > 0 for e in strong.events
               if e.kind is EventKind.CONVOY_INTERDICTED), "bomb=500 must actually bite"


@pytest.mark.parametrize("subsystem", SUBSYSTEMS)
def test_no_subsystem_can_reach_another_stream(subsystem):
    """Generalised: pin ANY one subsystem to a degenerate always-1 die and every OTHER stream
    must roll exactly what it rolled before. The property, stated once per subsystem."""

    class _Always1:
        def randint(self, a, b):
            return 1

    box, ref = DiceBox(2026), DiceBox(2026)
    box.load(subsystem, _Always1())
    for _ in range(20):
        box.d6(subsystem)                                   # burn the pinned stream hard
    others = [s for s in SUBSYSTEMS if s != subsystem]
    assert [box.d6(s) for s in others] == [ref.d6(s) for s in others]
