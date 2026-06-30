"""The smallest possible vertical slice — a *toy* desert strip, NOT a faithful
CNA scenario.

Its only job is to exercise every architectural bone (event log, RNG capture,
phased turn loop, role-scoped action, typed rejection, invariants, deterministic
replay) end to end. The first *real* scenario — Graziani's Offensive (rule
60.22: Game-Turn 1-6, Air & Logistics abstracted, rule 60.92) — is transcribed
onto these same bones next; the design is scenario-agnostic by intent (§9).

Geography is a single 8-hex line running west->east. The Italians enter from the
west and drive for the eastern town (the objective); the Commonwealth holds it.
"""
from __future__ import annotations

from .events import Control, Phase, Side
from .state import GameState, Hex, StepRecord, Unit, VP

STRIP_LENGTH = 8
MAX_TURNS = 6  # mirrors Graziani's Offensive length


def toy_strip(seed: int = 1940) -> GameState:
    hexes = tuple(
        Hex(coord=(x, 0), terrain="desert", move_cost=1, control=Control.NEUTRAL)
        for x in range(STRIP_LENGTH)
    )
    target = (STRIP_LENGTH - 1, 0)

    axis = (
        Unit("IT-Maletti", Side.AXIS, (0, 0),
             (StepRecord("inf", 3), StepRecord("arty", 1)), fuel=20.0),
        Unit("IT-Cirene", Side.AXIS, (1, 0),
             (StepRecord("inf", 2), StepRecord("tank", 2)), fuel=20.0),
    )
    allied = (
        Unit("UK-7Armd", Side.ALLIED, (target[0] - 1, 0),
             (StepRecord("tank", 3),), fuel=15.0),
        Unit("UK-4Ind", Side.ALLIED, target,
             (StepRecord("inf", 3),), fuel=10.0),
    )

    return GameState(
        turn=1,
        max_turns=MAX_TURNS,
        phase=Phase.WEATHER,
        active_side=Side.SYSTEM,
        seed=seed,
        weather="clear",
        move_modifier=0,
        vp=VP(),
        hexes=hexes,
        units=axis + allied,
        target_hex=target,
        fuel_consumed=0.0,
    )
