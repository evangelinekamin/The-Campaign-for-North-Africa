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


def test_morale_table_partitions_every_row():
    # every cohesion row must map each of the 36 legal rolls to exactly one modifier
    for lvl, cells in ct._MORALE_TABLE.items():
        seen: dict[int, int] = {}
        for cell in cells:
            for roll in ct.expand(cell):
                seen[roll] = seen.get(roll, 0) + 1
        assert set(seen) == set(VALID_ROLLS), f"cohesion {lvl} gap: {set(VALID_ROLLS) - set(seen)}"
        assert all(c == 1 for c in seen.values()), f"cohesion {lvl} overlapping cells"


def test_morale_modifier_matches_rulebook_rolls():
    # the four rolls the rules cite (15.64 + 15.2xx example) + the table corners
    assert ct.morale_modifier(-4, 43) == -2
    assert ct.morale_modifier(2, 63) == 0
    assert ct.morale_modifier(-2, 21) == 0
    assert ct.morale_modifier(-3, 53) == -2
    assert ct.morale_modifier(8, 11) == 4
    assert ct.morale_modifier(-17, 66) == "SURR"


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
    assert ct.defender_result(c, 2) == (True, 0)           # sum 2 -> captured only
    assert ct.defender_result(c, 5) == (False, 1)          # 4-7 -> retreat 1
    assert ct.defender_result(c, 11) == (False, 2)         # 11 -> retreat 2
    assert ct.defender_result(c, 8) == (False, 0)          # in contact
    assert ct.attacker_result(c, 8) == (False, True)       # 8-10,12 -> engaged
    assert ct.attacker_result(c, 2) == (False, False)      # attacker capt only on -diff


def test_retreat_takes_priority_over_engaged():
    # +3 column: defender sum 5 -> retreat 1; attacker sum 8 -> eng, but the
    # retreat drops the eng (rule 15.74).
    res = combat.resolve(attacker_raw=45, defender_raw=24,
                         attacker_strength=10, defender_strength=10,
                         def_terrain=Terrain.CLEAR, attack_feature=None,
                         atk_roll=26, def_roll=14)          # sums: atk 8, def 5
    assert res.column == 10
    assert res.retreat_hexes == 1 and res.attacker_engaged is False


def test_combat_example_captured_and_retreat_together():
    # The rulebook combat example (§15.2xx) resolves on the +4 column: the defender
    # rolls 21 -> 15% loss, and its dice SUM 3 (2+1) is BOTH captured (2-3) AND a
    # 1-hex retreat (3-7) -- the two results co-occur (rule 15.73). Attacker 32 -> 5%.
    col = ct.diff_to_column(4)
    assert col == 11
    assert ct.defender_loss_pct(col, 21) == 15
    assert ct.defender_result(col, 3) == (True, 1)
    assert ct.attacker_loss_pct(col, 32) == 5


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


def test_org_size_shift():
    assert ct.org_size_shift(1, 0) == 2        # battalion vs company -> +2 attacker (15.53)
    assert ct.org_size_shift(0, 1) == -2       # company vs battalion -> defender
    assert ct.org_size_shift(5, 1) == 4        # division vs battalion
    assert ct.org_size_shift(1, 1) == 0        # equal sizes
    assert ct.org_size_shift(3, 2) == 0        # super-brigade vs brigade


def test_barrage_crt():
    assert ct.barrage_result("infantry", 11, 66) == (True, 1)    # col 5, 45-66 -> lose 1 + pin
    assert ct.barrage_result("infantry", 1, 11) == (False, 0)    # no effect
    assert ct.barrage_result("gun", 13, 66) == (False, 2)        # guns never Pinned
    assert ct.barrage_result("armor", 2, 66) == (True, 0)        # pinned, no loss


def test_barrage_strength_worked_example():
    # rule 11.35: 90th Leichte artillery = 108 raw barrage -> 11 Actual Points.
    assert combat.actual_points(108, False) == 11


def test_anti_armor_crt():
    assert ct.anti_armor_damage(5, 35) == 7            # rule 14.43 worked example
    assert ct.anti_armor_damage(0, 11) == 0            # low points, low roll -> nothing
    assert ct.anti_armor_damage(16, 66) == 32          # max column, max roll
    assert ct.anti_armor_damage(8, 55, phasing=True) <= ct.anti_armor_damage(8, 55)


def test_combined_arms_reduces_actual_points():
    # §15.2xx worked example: Axis 63 raw -> 6 Actual (21 inf TOE >= 3 tank -> no
    # penalty); CW 38 raw -> 4 Actual, tanks (7) exceed inf (5) by 2 -> -1 Actual
    # -> 3. Basic differential +3.
    res = combat.resolve(attacker_raw=63, defender_raw=38,
                         attacker_strength=24, defender_strength=12,
                         def_terrain=Terrain.CLEAR, attack_feature=None,
                         atk_roll=11, def_roll=11,
                         attacker_ca_penalty=0, defender_ca_penalty=1)
    assert res.differential == 3               # 6 - (4-1)


def test_loss_rounding_attacker_up_defender_down():
    # column 0 differential, both sides 6 actual -> diff 0 (col 7)
    res = combat.resolve(attacker_raw=60, defender_raw=60,
                         attacker_strength=10, defender_strength=10,
                         def_terrain=Terrain.CLEAR, attack_feature=None,
                         atk_roll=25, def_roll=24)   # col 7: atk 25->10%, def 24->10%
    assert res.column == 7
    assert res.attacker_loss_pct == 10 and res.defender_loss_pct == 10
    assert res.attacker_steps_lost == 1 and res.defender_steps_lost == 1
