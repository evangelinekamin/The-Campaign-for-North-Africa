"""Golden + structural tests for Close Assault (rule 15 / §15.79 CRT).

The partition tests are the safety net for the dense-chart transcription: every
legal d6d6 roll must map to exactly one loss row in every column. Any miscounted
or dropped cell breaks coverage and fails here. The worked-example test pins the
table to the rulebook's own example (§15.64)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import combat, combat_tables as ct
from game.terrain import Hexside, Terrain

VALID_ROLLS = [v for v in range(11, 67) if 1 <= v // 10 <= 6 and 1 <= v % 10 <= 6]


def _partition(grid):
    for col in range(ct.N_COLS):
        seen: dict[int, int] = {}
        for _pct, cells in grid:
            for roll in ct.expand(cells[col]):
                seen[roll] = seen.get(roll, 0) + 1
        # every legal roll covered exactly once
        assert set(seen) == set(VALID_ROLLS), f"column {col} coverage gap: {set(VALID_ROLLS) - set(seen)}"
        assert all(c == 1 for c in seen.values()), f"column {col} has overlapping cells"


def test_attacker_table_partitions_every_column():
    _partition(ct._ATTACKER)


def test_defender_table_partitions_every_column():
    _partition(ct._DEFENDER)


def test_worked_example_15_64():
    # §15.64: assault resolved on the +4 column; attacker rolls 32 -> 5% loss,
    # defender rolls 21 -> 15% loss.
    col = ct.diff_to_column(4)
    assert ct.attacker_loss_pct(col, 32) == 5
    assert ct.defender_loss_pct(col, 21) == 15


def test_diff_to_column_grouping():
    assert ct.diff_to_column(0) == 7
    assert ct.diff_to_column(3) == 10
    assert ct.diff_to_column(4) == 11
    assert ct.diff_to_column(5) == ct.diff_to_column(6) == 12
    assert ct.diff_to_column(-11) == 0
    assert ct.diff_to_column(99) == ct.N_COLS - 1


def test_two_to_one_raw_shifts_two_columns_right():
    # 60 vs 30 raw -> actual 6 vs 3 (diff +3, base col 10); 2:1 raw adds +2 -> col 12
    res = combat.resolve(attacker_raw=60, defender_raw=30,
                         attacker_strength=10, defender_strength=10,
                         def_terrain=Terrain.CLEAR, attack_feature=None,
                         atk_roll=11, def_roll=11)
    assert res.differential == 3 and res.column == 12


def test_terrain_shift_favours_defender():
    # diff +2 (base col 9); 2:1 raw (+2) cancelled by Rough terrain (-2) -> col 9
    res = combat.resolve(attacker_raw=40, defender_raw=20,
                         attacker_strength=8, defender_strength=4,
                         def_terrain=Terrain.ROUGH, attack_feature=None,
                         atk_roll=11, def_roll=11)
    assert res.column == 9


def test_small_raw_uses_raw_as_actual():
    # both < 10 raw -> raw used directly: 8 - 6 = diff 2
    res = combat.resolve(attacker_raw=8, defender_raw=6,
                         attacker_strength=4, defender_strength=3,
                         def_terrain=Terrain.CLEAR, attack_feature=None,
                         atk_roll=11, def_roll=11)
    assert res.differential == 2


def test_defender_and_attacker_result_tables():
    c = ct.diff_to_column(3)                       # +3 column (index 10)
    assert ct.defender_result(c, 2) == ("CAPT", 0)         # sum 2 -> captured
    assert ct.defender_result(c, 5) == ("RETREAT", 1)      # 4-7 -> retreat 1
    assert ct.defender_result(c, 11) == ("RETREAT", 2)     # 11 -> retreat 2
    assert ct.defender_result(c, 8) == (None, 0)           # in contact
    assert ct.attacker_result(c, 8) == "ENG"               # 8-10,12 -> engaged
    assert ct.attacker_result(c, 2) is None                # attacker capt only on -diff


def test_retreat_takes_priority_over_engaged():
    # +3 column: defender sum 5 -> retreat 1; attacker sum 8 -> eng, but the
    # retreat drops the eng (rule 15.74).
    res = combat.resolve(attacker_raw=45, defender_raw=24,
                         attacker_strength=10, defender_strength=10,
                         def_terrain=Terrain.CLEAR, attack_feature=None,
                         atk_roll=26, def_roll=14)          # sums: atk 8, def 5
    assert res.column == 10
    assert res.defender_result == "RETREAT" and res.retreat_hexes == 1
    assert res.attacker_result is None


def test_morale_shift_moves_the_column():
    # +2 morale (e.g. 15th Panzer +3 vs +1) shifts the assault two columns right.
    base = combat.resolve(attacker_raw=30, defender_raw=30,
                          attacker_strength=10, defender_strength=10,
                          def_terrain=Terrain.CLEAR, attack_feature=None,
                          atk_roll=11, def_roll=11)
    up = combat.resolve(attacker_raw=30, defender_raw=30,
                        attacker_strength=10, defender_strength=10,
                        def_terrain=Terrain.CLEAR, attack_feature=None,
                        atk_roll=11, def_roll=11, morale_shift=2)
    assert up.column == base.column + 2


def test_loss_rounding_attacker_up_defender_down():
    # column 0 differential, both sides 6 actual -> diff 0 (col 7)
    res = combat.resolve(attacker_raw=60, defender_raw=60,
                         attacker_strength=10, defender_strength=10,
                         def_terrain=Terrain.CLEAR, attack_feature=None,
                         atk_roll=25, def_roll=24)   # col 7: atk 25->10%, def 24->10%
    assert res.column == 7
    assert res.attacker_loss_pct == 10 and res.defender_loss_pct == 10
    assert res.attacker_steps_lost == 1 and res.defender_steps_lost == 1
