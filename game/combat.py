"""Close Assault resolution (rule 15) — the differential engine.

Computes Actual Close Assault points (rule 11.3 / 15.4), the adjusted Assault
Differential (terrain column-shifts 15.3 + the two-to-one raw size shift 15.51),
and reads loss percentages off the §15.79 CRT (combat_tables). Losses are applied
as a percentage of committed TOE strength (attacker rounds up, defender rounds
down, §15.83c).

DEFERRED + FLAGGED for later slices: morale shift (15.6), combined-arms (15.4),
the organizational-size table beyond 2:1 (15.52/15.53), Retreat / Engaged results,
Captured / prisoners (15.85), guns & vulnerability (15.84), Probe (15.9), and the
other combat types — Anti-Armor (14), Barrage (12).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import combat_tables as ct
from .terrain import Hexside, Terrain


@dataclass(frozen=True, slots=True)
class CombatResult:
    differential: int
    column: int
    attacker_loss_pct: int
    defender_loss_pct: int
    attacker_steps_lost: int
    defender_steps_lost: int


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def actual_points(raw: int, both_small: bool) -> int:
    if both_small:                 # 15.28: if both sides < 10 raw, use raw as actual
        return raw
    if raw < 5:                    # 15.28/11.33: < 5 raw -> 0 actual
        return 0
    return _round_half_up(raw / 10)


def resolve(*, attacker_raw: int, defender_raw: int,
            attacker_strength: int, defender_strength: int,
            def_terrain: Terrain, attack_feature: Hexside | None,
            atk_roll: int, def_roll: int, extra_shift: int = 0) -> CombatResult:
    both_small = attacker_raw < 10 and defender_raw < 10
    diff = actual_points(attacker_raw, both_small) - actual_points(defender_raw, both_small)

    shift = ct.HEX_CA_SHIFT.get(def_terrain, 0)                 # 15.3 terrain
    if attack_feature is not None:
        shift += ct.HEXSIDE_CA_SHIFT.get(attack_feature, 0)
    if defender_raw > 0 and attacker_raw >= 2 * defender_raw:   # 15.51 two-to-one
        shift += 2
    elif attacker_raw > 0 and defender_raw >= 2 * attacker_raw:
        shift -= 2
    shift += extra_shift

    col = max(0, min(ct.N_COLS - 1, ct.diff_to_column(diff) + shift))
    a_pct = ct.attacker_loss_pct(col, atk_roll)
    d_pct = ct.defender_loss_pct(col, def_roll)
    return CombatResult(
        differential=diff, column=col,
        attacker_loss_pct=a_pct, defender_loss_pct=d_pct,
        attacker_steps_lost=math.ceil(a_pct / 100 * attacker_strength),
        defender_steps_lost=math.floor(d_pct / 100 * defender_strength),
    )
