"""Close Assault resolution (rule 15) — the differential engine.

Computes Actual Close Assault points (rule 11.3 / 15.4), the adjusted Assault
Differential (terrain column-shifts 15.3 + the two-to-one raw size shift 15.51),
and reads loss percentages off the §15.79 CRT (combat_tables). Per §15.83b/c the
loss percentage is taken of the total RAW assault points (attacker rounds up,
defender rounds down) to yield the raw points lost; the engine then removes TOE
steps to ABSORB those raw points via each unit's close-assault rating (§15.83d),
so a high-rated (elite) unit loses fewer steps than a weak one for the same loss.

Also resolves the CRT's special results (rule 15.79) from the dice SUM: the
defender's RETREAT (n hexes) or CAPT, and the attacker's ENG (Engaged) or CAPT.
Retreat takes priority over Engaged (15.74). The engine executes the retreat and
the Engaged marker; advance-after-combat is not a CRT result (the attacker simply
moves into a vacated hex next phase, rule 10.24).

Combined arms (15.4) reduces each side's Actual close-assault points via the
`*_ca_penalty` args (the engine computes them from the tank/infantry TOE mix).

DEFERRED + FLAGGED for later slices: the Prisoners Captured % table (15.89 — Capt
here just records that some already-counted losses are prisoners, no board effect),
the organizational-size table beyond 2:1 (15.52/15.53), guns & vulnerability
(15.84), Probe (15.9). Morale (15.6) is a column shift, applied via `morale_shift`.
Anti-Armor (14) + Barrage (12) are their own combat steps in the engine segment.
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
    attacker_points_lost: int            # raw assault points to absorb (15.83c, rounded up)
    defender_points_lost: int            # raw assault points to absorb (15.83c, rounded down)
    attacker_captured: bool = False      # some attacker losses become prisoners (15.85)
    defender_captured: bool = False      # some defender losses become prisoners
    attacker_engaged: bool = False       # attacker locked in contact (15.81)
    retreat_hexes: int = 0               # defender must retreat this many hexes (15.82)


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def actual_points(raw: int, both_small: bool) -> int:
    if both_small:                 # 15.28: if both sides < 10 raw, use raw as actual
        return raw
    if raw < 5:                    # 15.28/11.33: < 5 raw -> 0 actual
        return 0
    return _round_half_up(raw / 10)


def resolve(*, attacker_raw: int, defender_raw: int,
            def_terrain: Terrain, attack_feature: Hexside | None,
            atk_roll: int, def_roll: int,
            extra_shift: int = 0, morale_shift: int = 0,
            attacker_ca_penalty: int = 0, defender_ca_penalty: int = 0,
            attacker_size: int = 0, defender_size: int = 0,
            fortification_level: int = 0, in_enemy_minefield: bool = False,
            defender_loss_raw: int | None = None) -> CombatResult:
    both_small = attacker_raw < 10 and defender_raw < 10
    # Combined-arms reduces each side's ACTUAL close-assault points (rule 15.4).
    a_actual = max(0, actual_points(attacker_raw, both_small) - attacker_ca_penalty)
    d_actual = max(0, actual_points(defender_raw, both_small) - defender_ca_penalty)
    diff = a_actual - d_actual

    shift = ct.HEX_CA_SHIFT.get(def_terrain, 0)                 # 15.3 terrain
    if attack_feature is not None:
        shift += ct.HEXSIDE_CA_SHIFT.get(attack_feature, 0)
    if defender_raw > 0 and attacker_raw >= 2 * defender_raw:   # 15.51 two-to-one
        shift += 2
    elif attacker_raw > 0 and defender_raw >= 2 * attacker_raw:
        shift -= 2
    shift += ct.org_size_shift(attacker_size, defender_size)    # 15.53 organization size
    shift += morale_shift + extra_shift                         # 15.62 morale column shift
    shift += fortification_level * ct.FORT_CA_SHIFT             # 15.82 static fortification
    if in_enemy_minefield:                                      # defensive minefield belt
        shift += ct.MINEFIELD_CA_SHIFT

    col = max(0, min(ct.N_COLS - 1, ct.diff_to_column(diff) + shift))
    a_pct = ct.attacker_loss_pct(col, atk_roll)
    d_pct = ct.defender_loss_pct(col, def_roll)

    # Special results read the SAME dice as an arithmetic sum (rule 15.79).
    a_capt, a_eng = ct.attacker_result(col, atk_roll // 10 + atk_roll % 10)
    d_capt, retreat = ct.defender_result(col, def_roll // 10 + def_roll % 10)
    if retreat > 0:                                            # 15.74 retreat beats engaged
        a_eng = False
    # 15.83b/c: the loss percentage is taken of the TOTAL RAW assault points, not
    # of TOE steps. Attacker rounds up, defender rounds down (overrun rounds the
    # defender up under 15.77 -- deferred). Steps to absorb these are chosen per
    # unit in the engine via each unit's close-assault rating (15.83d).
    #
    # 15.12/15.15/15.83c: the DEFENDER'S casualty pool is wider than defender_raw --
    # it adds the TOE (raw) of PINNED and withheld (out-of-ammo, retreated-in) units,
    # which contribute NO Ratings to the differential above yet still bleed. The engine
    # passes that full pool as defender_loss_raw; it defaults to the armed defender_raw
    # when there are no withheld defenders (all resolve() unit tests, which pass none).
    defender_loss_pool = defender_raw if defender_loss_raw is None else defender_loss_raw
    return CombatResult(
        differential=diff, column=col,
        attacker_loss_pct=a_pct, defender_loss_pct=d_pct,
        attacker_points_lost=math.ceil(a_pct / 100 * attacker_raw),
        defender_points_lost=math.floor(d_pct / 100 * defender_loss_pool),
        attacker_captured=a_capt, defender_captured=d_capt,
        attacker_engaged=a_eng, retreat_hexes=retreat,
    )
