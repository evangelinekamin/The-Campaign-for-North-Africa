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
                         def_terrain=Terrain.CLEAR, hexside_shift=0,
                         atk_roll=11, def_roll=11)
    assert res.differential == 3 and res.column == 12


def test_terrain_shift_favours_defender():
    # diff +2 (base col 9); 2:1 raw (+2) cancelled by Rough terrain (-2) -> col 9
    res = combat.resolve(attacker_raw=40, defender_raw=20,
                         def_terrain=Terrain.ROUGH, hexside_shift=0,
                         atk_roll=11, def_roll=11)
    assert res.column == 9


def test_hexside_shift_reads_every_attacking_hex_15_33():
    # 15.33: "if any units are attacking through a given hexside, the Differential is adjusted as if
    # all units were attacking through that hexside." So the shift is read over EVERY attacking hex,
    # not the one the policy happens to list first (the old armed_atk[0] order-dependence). One attacker
    # crosses a Ridge (-2), the other clear -> the full -2. The helper takes a SET, so it is order-free.
    from game.engine import _assault_hexside_shift
    from game.movement import TerrainMap
    tmap = TerrainMap(terrain={(0, 0): Terrain.CLEAR, (0, 1): Terrain.CLEAR, (1, 0): Terrain.CLEAR},
                      hexsides={((0, 1), (0, 0)): Hexside.RIDGE})
    assert _assault_hexside_shift(tmap, {(0, 1), (1, 0)}, (0, 0)) == -2


def test_hexside_defender_benefits_from_one_type_15_35():
    # 15.35: the defender benefits from only ONE hexside type. WADI(-1) + RIDGE(-2) across two
    # attacking hexes -> the single best-for-defender (-2), NOT the sum (-3).
    from game.engine import _assault_hexside_shift
    from game.movement import TerrainMap
    tmap = TerrainMap(terrain={(0, 0): Terrain.CLEAR, (0, 1): Terrain.CLEAR, (1, 0): Terrain.CLEAR},
                      hexsides={((0, 1), (0, 0)): Hexside.WADI, ((1, 0), (0, 0)): Hexside.RIDGE})
    assert _assault_hexside_shift(tmap, {(0, 1), (1, 0)}, (0, 0)) == -2


def test_hexside_downslope_offsets_the_defender_15_36():
    # 15.36 (verbatim example): a down-slope (+1) attacker benefit OFFSETS an up-escarpment (-3) -> -2.
    from game.engine import _assault_hexside_shift
    from game.movement import TerrainMap
    tmap = TerrainMap(terrain={(0, 0): Terrain.CLEAR, (0, 1): Terrain.CLEAR, (1, 0): Terrain.CLEAR},
                      hexsides={((0, 1), (0, 0)): Hexside.DOWN_SLOPE,
                                ((1, 0), (0, 0)): Hexside.UP_ESCARPMENT})
    assert _assault_hexside_shift(tmap, {(0, 1), (1, 0)}, (0, 0)) == -2


def test_resolve_applies_the_hexside_shift():
    # The pure resolver now takes the final integer shift: -2 moves two columns toward the defender.
    base = combat.resolve(attacker_raw=40, defender_raw=20, def_terrain=Terrain.CLEAR,
                          hexside_shift=0, atk_roll=11, def_roll=11)
    ridge = combat.resolve(attacker_raw=40, defender_raw=20, def_terrain=Terrain.CLEAR,
                           hexside_shift=-2, atk_roll=11, def_roll=11)
    assert ridge.column == base.column - 2


def test_small_raw_uses_raw_as_actual():
    # both < 10 raw -> raw used directly: 8 - 6 = diff 2
    res = combat.resolve(attacker_raw=8, defender_raw=6,
                         def_terrain=Terrain.CLEAR, hexside_shift=0,
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
                         def_terrain=Terrain.CLEAR, hexside_shift=0,
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
                          def_terrain=Terrain.CLEAR, hexside_shift=0,
                          atk_roll=11, def_roll=11)
    up = combat.resolve(attacker_raw=30, defender_raw=30,
                        def_terrain=Terrain.CLEAR, hexside_shift=0,
                        atk_roll=11, def_roll=11, morale_shift=2)
    assert up.column == base.column + 2


def test_org_size_shift():
    assert ct.org_size_shift(1, 0) == 2        # battalion vs company -> +2 attacker (15.53)
    assert ct.org_size_shift(0, 1) == -2       # company vs battalion -> defender
    assert ct.org_size_shift(5, 1) == 4        # division vs battalion
    assert ct.org_size_shift(1, 1) == 0        # equal sizes
    assert ct.org_size_shift(3, 2) == 0        # super-brigade vs brigade


def test_fortification_shifts_columns_toward_defender():
    # Chart 8.37 grades the close-assault fortification benefit L2 / L3 / L4 for Levels
    # 1 / 2 / 3 (rule 15.82). The old level*(-2) gave -2/-4/-6, over-shifting Level 2 by
    # one column and Level 3 by two (T0-8). Level 0 (default) is unchanged.
    assert ct.FORT_CA_SHIFT_BY_LEVEL == {1: -2, 2: -3, 3: -4}
    kw = dict(attacker_raw=60, defender_raw=30, def_terrain=Terrain.CLEAR,
              hexside_shift=0, atk_roll=11, def_roll=11)
    base = combat.resolve(**kw)
    for level, expected in ct.FORT_CA_SHIFT_BY_LEVEL.items():
        fort = combat.resolve(**kw, fortification_level=level)
        assert fort.column == max(0, base.column + expected)   # exact per-level shift
        assert fort.column < base.column                       # measurably better defense
    assert combat.resolve(**kw, fortification_level=0) == base   # default = today


def test_minefield_shifts_column_toward_defender():
    # a defensive minefield belt shifts the assault toward the defender
    # (MINEFIELD_CA_SHIFT); default False is unchanged.
    kw = dict(attacker_raw=60, defender_raw=30, def_terrain=Terrain.CLEAR,
              hexside_shift=0, atk_roll=11, def_roll=11)
    base = combat.resolve(**kw)
    mined = combat.resolve(**kw, in_enemy_minefield=True)
    assert mined.column == base.column + ct.MINEFIELD_CA_SHIFT
    assert mined.column < base.column
    assert combat.resolve(**kw, in_enemy_minefield=False) == base


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


def test_minefield_shift_is_one_column_rule_26_26():
    # Rule 26.26: "the defending Player adjusts all columns ONE in his favor" (8.37
    # gives the minefield close-assault effect as L1). The belt is a single column,
    # not two -- pins the corrected magnitude.
    assert ct.MINEFIELD_CA_SHIFT == -1


def test_phasing_anti_armor_row_shift_rule_14_6():
    # 14.6 CRT Modifiers: "Phasing Player decreases his dice roll by one row (an 11
    # or 12 is unaffected)." Phasing on roll 35 must equal non-phasing on roll 33
    # (the row directly below), and rolls 11/12 (the top row) are unaffected.
    assert ct.anti_armor_damage(8, 35, phasing=True) == ct.anti_armor_damage(8, 33)
    assert ct.anti_armor_damage(8, 12, phasing=True) == ct.anti_armor_damage(8, 12)


def test_anti_armor_terrain_shift_rule_14_32():
    # 8.37 / 14.32: the defending armour's hex terrain shifts the Actual Anti-Armor
    # Points column LEFT -- Rough & Heavy Vegetation L1, Mountain L2, Clear none.
    assert ct.anti_armor_terrain_shift(Terrain.ROUGH, 0) == -1
    assert ct.anti_armor_terrain_shift(Terrain.HEAVY_VEG, 0) == -1
    assert ct.anti_armor_terrain_shift(Terrain.MOUNTAIN, 0) == -2
    assert ct.anti_armor_terrain_shift(Terrain.CLEAR, 0) == 0
    # 14.32 worked example: 9 Actual Anti-Armor Points into Rough resolve on the 8
    # column (a one-column-left shift).
    assert ct.anti_armor_damage(9, 55, terrain_shift=-1) == ct.anti_armor_damage(8, 55)


def test_anti_armor_fortification_gated_to_major_city_note_12():
    # 8.37 note 12: an armour target (every anti-armor target IS armour) receives the
    # fortification anti-armor benefit ONLY in a Major City hex -- so a Level-2 fort in
    # Clear terrain gives nothing, but the same fort at Tobruk (Major City) gives L2.
    assert ct.anti_armor_terrain_shift(Terrain.CLEAR, 2) == 0
    assert ct.anti_armor_terrain_shift(Terrain.MAJOR_CITY, 1) == -1
    assert ct.anti_armor_terrain_shift(Terrain.MAJOR_CITY, 2) == -2
    assert ct.anti_armor_terrain_shift(Terrain.MAJOR_CITY, 3) == -2


def test_barrage_terrain_shift_rule_12_33():
    # 8.37: only Rough (L1) and Mountain (L2) shift barrage; every other terrain none.
    assert ct.barrage_terrain_shift(Terrain.ROUGH, 0, "infantry") == -1
    assert ct.barrage_terrain_shift(Terrain.MOUNTAIN, 0, "infantry") == -2
    assert ct.barrage_terrain_shift(Terrain.CLEAR, 0, "infantry") == 0
    # 12.33 worked example: a gun in a Level-Two Fortification (Clear terrain) barraged
    # by 12 Barrage Points (the 11-12 band) resolves on the 7-8 band -- two bands left.
    assert ct.barrage_terrain_shift(Terrain.CLEAR, 2, "gun") == -2
    assert ct.barrage_result("gun", 12, 51, column_shift=-2) == ct.barrage_result("gun", 8, 51)
    # 12.34: a shift off the low end of the table means the barrage had no effect.
    assert ct.barrage_result("infantry", 2, 66, column_shift=-2) == (False, 0)


def test_barrage_fortification_armor_gated_to_major_city_note_12():
    # 8.37 note 12: an ARMOUR-class barrage target gets the fort benefit only in a
    # Major City hex; infantry and gun targets get it in any fortified hex.
    assert ct.barrage_terrain_shift(Terrain.CLEAR, 2, "armor") == 0
    assert ct.barrage_terrain_shift(Terrain.MAJOR_CITY, 2, "armor") == -2
    assert ct.barrage_terrain_shift(Terrain.CLEAR, 2, "infantry") == -2
    assert ct.barrage_terrain_shift(Terrain.CLEAR, 1, "gun") == -1


def test_combined_arms_reduces_actual_points():
    # §15.2xx worked example: Axis 63 raw -> 6 Actual (21 inf TOE >= 3 tank -> no
    # penalty); CW 38 raw -> 4 Actual, tanks (7) exceed inf (5) by 2 -> -1 Actual
    # -> 3. Basic differential +3.
    res = combat.resolve(attacker_raw=63, defender_raw=38,
                         def_terrain=Terrain.CLEAR, hexside_shift=0,
                         atk_roll=11, def_roll=11,
                         attacker_ca_penalty=0, defender_ca_penalty=1)
    assert res.differential == 3               # 6 - (4-1)


def test_loss_rounding_attacker_up_defender_down():
    # 15.83b/c: the loss percentage is taken of the total RAW assault points, and
    # the attacker rounds the raw points lost UP while the defender rounds DOWN.
    # col 7, both 10% of 60 raw = 6.0 -> 6 points each (exact, no rounding gap).
    res = combat.resolve(attacker_raw=60, defender_raw=60,
                         def_terrain=Terrain.CLEAR, hexside_shift=0,
                         atk_roll=25, def_roll=24)   # col 7: atk 25->10%, def 24->10%
    assert res.column == 7
    assert res.attacker_loss_pct == 10 and res.defender_loss_pct == 10
    assert res.attacker_points_lost == 6 and res.defender_points_lost == 6


def test_15_83c_loss_pct_applies_to_raw_points_rounding_directions():
    # 15.83c: 15% of 43 raw = 6.45 -> attacker rounds UP to 7, defender rounds DOWN
    # to 6. Proves the percentage is taken of RAW assault points (not TOE steps) and
    # that the two players round opposite directions on the same fractional loss.
    res = combat.resolve(attacker_raw=43, defender_raw=43,
                         def_terrain=Terrain.CLEAR, hexside_shift=0,
                         atk_roll=21, def_roll=21)   # col 7: 21 -> 15% both sides
    assert res.attacker_loss_pct == 15 and res.defender_loss_pct == 15
    assert res.attacker_points_lost == 7      # ceil(6.45)
    assert res.defender_points_lost == 6      # floor(6.45)


def test_15_12_pinned_defenders_widen_the_casualty_pool():
    # 15.12/15.83c: PINNED (and withheld) defenders add NO Ratings to the defense
    # -- the differential, column, and 15.51 shift are read off the armed defender_raw
    # -- yet their TOE strengths ARE in the casualty pool. Here 38 armed raw plus a
    # pinned battalion's 32 raw make a 70-point loss pool (the rulebook's own worked
    # example: 15% of 70 = 10.5 -> floor 10).
    kw = dict(attacker_raw=63, def_terrain=Terrain.CLEAR, hexside_shift=0,
              atk_roll=21, def_roll=21, defender_ca_penalty=1)
    armed = combat.resolve(defender_raw=38, **kw)
    pooled = combat.resolve(defender_raw=38, defender_loss_raw=70, **kw)
    # the pinned TOE never touches the differential / column
    assert pooled.differential == armed.differential
    assert pooled.column == armed.column
    assert pooled.defender_loss_pct == armed.defender_loss_pct == 15
    assert armed.defender_points_lost == 5          # floor(0.15 * 38)
    assert pooled.defender_points_lost == 10        # floor(0.15 * 70)


def test_15_12_all_pinned_garrison_still_bleeds():
    # The regression: a lone PINNED garrison has defender_raw == 0 (adds no Ratings) so
    # WITHOUT a separate pool it would take ZERO losses at any column/roll. With its TOE
    # in the pool it must still bleed when the CRT calls for a loss.
    res = combat.resolve(attacker_raw=60, defender_raw=0, defender_loss_raw=40,
                         def_terrain=Terrain.CLEAR, hexside_shift=0,
                         atk_roll=21, def_roll=21)
    assert res.defender_loss_pct > 0
    assert res.defender_points_lost > 0


def test_15_83d_elite_absorbs_fewer_steps_than_weak_at_same_loss():
    # 15.83d: steps are removed to ABSORB the raw points lost, each step soaking up
    # its unit's close-assault rating. For the SAME raw points lost, an elite unit
    # (high rating/step) sheds fewer steps than a weak one (low rating/step).
    from game.engine import _absorb_losses
    from game.state import Side, StepRecord, Unit
    from game.terrain import Mobility

    def _u(uid, rating):
        return Unit(uid, Side.AXIS, (0, 0), (StepRecord("s", 10),),
                    mobility=Mobility.MOTORIZED, cpa=10, stacking_points=1,
                    oca=rating, dca=rating)

    points = 8
    elite = _absorb_losses([_u("elite", 4)], points, lambda u: u.oca)
    weak = _absorb_losses([_u("weak", 1)], points, lambda u: u.oca)
    assert elite == [("elite", 2)]     # ceil(8 / 4) = 2 steps absorb 8 raw points
    assert weak == [("weak", 8)]       # ceil(8 / 1) = 8 steps for the same 8 points
    assert sum(a for _, a in elite) < sum(a for _, a in weak)
