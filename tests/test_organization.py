"""Rule 19 -- ORGANIZATION AND REORGANIZATION, and the [9.2] unit-equivalent
arithmetic it feeds.

The chapter was entirely missing: `Unit` had no parent/assigned/attached field, so no
division and no Kampfgruppe could ever form, and the [15.53] Organization Size chart --
transcribed exactly in game.combat_tables and verified against the scan -- could never reach
its Brigade / Super-Brigade / Division rows. No counter in the engine carries more than one
Stacking Point (the ten HQ / gun roles are SP 0, everything else SP 1), so the chart could only
ever fire on its lowest (1,0) row -- a battalion against a lone company or gun, a two-column
shift -- and never on the 2 / 3 / 5 SP tiers that need a Parent Formation you BUILD.

These tests are the port of that chapter. The headline is
test_org_size_shift_fires_for_the_first_time_when_a_kampfgruppe_forms.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import combat, combat_tables, cp_costs, organization
from game.events import Side
from game.state import StepRecord, Unit
from game.terrain import Mobility, Terrain


def _u(uid: str, *, side: Side = Side.AXIS, sp: int = 1, strength: int = 6,
       org_type: str = "", attached_to: str = "", assigned_to: str = "",
       nationality: str = "GE", is_tank: bool = False, is_combat: bool = True,
       hex_: tuple = (0, 0), oca: int = 2, dca: int = 2, cpa: int = 20) -> Unit:
    return Unit(uid, side, hex_, (StepRecord("s", strength),), mobility=Mobility.FOOT,
                cpa=cpa, stacking_points=sp, oca=oca, dca=dca, nationality=nationality,
                is_tank=is_tank, is_combat=is_combat,
                org_type=org_type, attached_to=attached_to, assigned_to=assigned_to)


# --- the charts as DATA (19.3 / 19.5 / 6.3) -----------------------------------------

def test_19_5_maximum_attachment_chart_is_data_not_literals():
    row = organization.attachment_row("ge_battle_group", turn=1)
    assert row["units"] == 4                       # [19.5] German Battle Group: 4 units
    assert row["max_tank"] == 1 and row["max_infantry"] == 2      # [19.72]
    assert organization.attachment_row("it_battle_group", turn=1)["units"] == 3   # [19.73]


def test_19_5_commonwealth_armor_division_row_changes_at_game_turn_68():
    early = organization.attachment_row("cw_armor_division_II", turn=67)
    late = organization.attachment_row("cw_armor_division_II", turn=68)
    assert (early["units"], early["max_tank"]) == (2, 0)          # "2 units. 1 Infantry; no Tank."
    assert (late["units"], late["max_tank"]) == (3, 1)            # "3 units. 1 Infantry and/or 1 Tank."


def test_19_3_formation_chart_carries_the_9_4_stacking_tier():
    assert organization.formation("ge_15_panzer_division")["sp"] == 5       # [9.4] Division
    assert organization.formation("ge_15_infantry_brigade")["sp"] == 3      # [9.4] Super Brigade
    assert organization.formation("ge_battle_group")["sp"] == 2             # [9.4] Battle Group


def test_6_3_organization_capability_point_rows_are_transcribed():
    assert cp_costs.detach_cost() == 1              # "Detach a unit (PF and detaching unit)"
    assert cp_costs.attach_cost(assigned=True) == 1     # "Attach an assigned unit"
    assert cp_costs.attach_cost(assigned=False) == 2    # "Attach an unassigned unit"
    assert cp_costs.absorb_cost() == 1              # "Absorb 2 TOE Replacement Strength Points"


# --- [9.12] / [9.21] / [9.26] the size of a counter ----------------------------------

def test_9_12_a_bare_hq_counter_is_worth_zero_stacking_points():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    assert organization.size(hq, ()) == 0


def test_9_12_an_hq_that_represents_its_formation_is_worth_its_printed_value():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    kids = tuple(_u(f"B{i}", attached_to="KG") for i in range(3))
    assert organization.size(hq, kids) == 2


def test_9_21_an_attached_unit_does_not_stack_on_its_own_account():
    bn = _u("B1", attached_to="KG")
    assert organization.size(bn, ()) == 0          # represented by the Parent's counter (19.12)


def test_9_13_a_kampfgruppe_stacks_at_two_not_at_the_sum_of_its_battalions():
    """'a full division has a Stacking Point value of 5, while it may include units whose
    total Stacking Point values are much greater than five' -- 9.13."""
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    kids = tuple(_u(f"B{i}", attached_to="KG") for i in range(4))
    stack = (hq,) + kids
    assert organization.stack_points(stack) == 2   # not 0 + 4x1


def test_9_26_a_brigade_with_fewer_than_two_thirds_of_its_battalions_is_a_shell():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    two = tuple(_u(f"B{i}", attached_to="KG") for i in range(2))     # 2 of 4 < 2/3
    three = tuple(_u(f"B{i}", attached_to="KG") for i in range(3))   # 3 of 4 >= 2/3
    assert organization.is_shell(hq, two) is True
    assert organization.is_shell(hq, three) is False


def test_9_26_a_battalion_below_half_its_toe_is_a_shell_and_artillery_below_a_quarter():
    full = _u("B", strength=8, oca=2)
    assert organization.is_shell(full, (), max_toe=8) is False
    assert organization.is_shell(_u("B", strength=3), (), max_toe=8) is True
    gun = Unit("G", Side.AXIS, (0, 0), (StepRecord("s", 3),), mobility=Mobility.FOOT,
               cpa=15, stacking_points=1, oca=0, dca=1, barrage=4, vulnerability=2)
    assert organization.is_shell(gun, (), max_toe=8) is False       # 3/8 > 25%
    gun = Unit("G", Side.AXIS, (0, 0), (StepRecord("s", 1),), mobility=Mobility.FOOT,
               cpa=15, stacking_points=1, oca=0, dca=1, barrage=4, vulnerability=2)
    assert organization.is_shell(gun, (), max_toe=8) is True        # 1/8 < 25%


def test_9_28_a_shell_reads_one_organizational_level_down_for_close_assault():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    two = tuple(_u(f"B{i}", attached_to="KG") for i in range(2))
    # a shell BRIGADE is a battalion equivalent (9.28), i.e. 1 SP, not 2
    assert organization.size_equivalent(hq, two) == 1
    three = tuple(_u(f"B{i}", attached_to="KG") for i in range(3))
    assert organization.size_equivalent(hq, three) == 2


# --- [19.7] AXIS BATTLE GROUPS (KAMPFGRUPPEN) ----------------------------------------

def _gun(uid: str, *, barrage: int = 4) -> Unit:
    return Unit(uid, Side.AXIS, (0, 0), (StepRecord("s", 6),), mobility=Mobility.MOTORIZED,
                cpa=15, stacking_points=1, oca=0, dca=1, barrage=barrage, vulnerability=2,
                nationality="GE")


def test_19_72_a_german_battle_group_takes_four_battalions_one_tank_two_infantry():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    ok = (_u("T1", is_tank=True), _u("I1"), _u("I2"), _gun("A1"))
    assert organization.may_attach(hq, ok[:3], ok[3], turn=1) == ""
    two_tanks = (_u("T1", is_tank=True),)
    assert "tank" in organization.may_attach(hq, two_tanks, _u("T2", is_tank=True), turn=1)
    three_inf = (_u("I1"), _u("I2"))
    assert "infantry" in organization.may_attach(hq, three_inf, _u("I3"), turn=1)
    assert "four" in organization.may_attach(hq, ok, _u("X1", oca=0, dca=1), turn=1)


def test_19_73_italian_battle_groups_are_capped_at_two_in_existence_at_once():
    board = [_u("BG1", side=Side.AXIS, org_type="it_battle_group", nationality="IT"),
             _u("BG2", side=Side.AXIS, org_type="it_battle_group", nationality="IT")]
    assert organization.may_form_battle_group(board, "IT") != ""
    assert organization.may_form_battle_group(board[:1], "IT") == ""


def test_19_71_no_cap_on_the_number_of_german_battle_groups():
    """'If the Axis Player wishes to form more Kampfgruppen than he has battlegroup
    counters, he may do so' -- Kampfgruppen HQ's sheet, note a."""
    board = [_u(f"KG{i}", org_type="ge_battle_group") for i in range(20)]
    assert organization.may_form_battle_group(board, "GE") == ""


def test_kampfgruppen_sheet_note_4_caps_italian_units_across_all_german_battle_groups():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    italians = [_u(f"I{i}", nationality="IT", attached_to="OTHER") for i in range(3)]
    assert "Italian" in organization.may_attach(hq, (), _u("I9", nationality="IT"),
                                                turn=1, board=italians)
    assert organization.may_attach(hq, (), _u("I9", nationality="IT"),
                                   turn=1, board=italians[:2]) == ""


# --- [19.4] attachment / detachment restrictions --------------------------------------

def test_19_41_an_assigned_unit_may_only_attach_in_its_parents_hex():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1, hex_=(0, 0))
    far = _u("B1", assigned_to="KG", hex_=(5, 5))
    assert "hex" in organization.may_attach(hq, (), far, turn=1)


def test_19_13_a_unit_may_never_be_attached_to_two_parents_at_once():
    hq = _u("KG2", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    already = _u("B1", attached_to="KG1")
    assert "attached" in organization.may_attach(hq, (), already, turn=1)


def test_19_21_only_an_already_attached_unit_may_be_assigned():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    loose = _u("B1")
    assert organization.may_assign(hq, (), loose) != ""
    assert organization.may_assign(hq, (), _u("B1", attached_to="KG")) == ""


def test_19_28_an_already_assigned_unit_may_not_be_assigned_to_a_second_parent():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    taken = _u("B1", attached_to="KG", assigned_to="OTHER")
    assert organization.may_assign(hq, (), taken) != ""


# --- [19.6] rebuilding depleted units --------------------------------------------------

def test_19_61_no_unit_may_be_rebuilt_above_its_printed_maximum_toe():
    u = _u("B", strength=7)
    assert organization.rebuild_headroom(u, max_toe=8) == 1
    assert organization.rebuild_headroom(_u("B", strength=8), max_toe=8) == 0


def test_19_62_a_unit_eliminated_by_combat_attrition_may_not_be_rebuilt():
    dead = _u("B", strength=0)
    assert organization.may_rebuild(dead, max_toe=8, points=2) != ""


def test_19_68_rebuilding_costs_one_capability_point_per_two_replacement_points():
    assert organization.rebuild_cp(2) == 1
    assert organization.rebuild_cp(4) == 2
    assert organization.rebuild_cp(3) == 2          # a part-pair still costs its point


# --- [19.8] / [19.9] ad hoc anti-tank --------------------------------------------------

def test_19_81_83_an_axis_brigade_hq_takes_three_to_six_toe_of_anti_tank():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    assert organization.may_augment_at(hq, points=2, at_units=()) != ""      # 19.83 >= 3
    assert organization.may_augment_at(hq, points=7, at_units=()) != ""      # 19.81 <= 6
    assert organization.may_augment_at(hq, points=3, at_units=()) == ""


def test_19_82_augmentation_is_barred_while_any_at_unit_is_below_two_thirds_toe():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    thin = [(_u("AT1", strength=4), 8)]                       # 50% < 67%
    assert "67" in organization.may_augment_at(hq, points=3, at_units=thin)
    fat = [(_u("AT1", strength=6), 8)]                        # 75% >= 67%
    assert organization.may_augment_at(hq, points=3, at_units=fat) == ""


def test_19_87_an_augmented_hq_keeps_a_stacking_point_value_of_zero():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    hq = organization.augment_at(hq, 4)
    assert organization.size(hq, ()) == 0
    assert hq.strength == 5                                   # 1 cadre + 4 AT TOE points


def test_19_85_an_augmented_hq_takes_the_cpa_of_its_anti_tank_points():
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1, cpa=60)
    assert organization.augment_at(hq, 4, at_cpa=15).cpa == 15


def test_19_92_94_commonwealth_battalions_eligible_for_anti_tank_by_cpa_and_ratings():
    walking = _u("BN", side=Side.ALLIED, nationality="CW", cpa=10, oca=1, dca=2)
    motor = _u("BN", side=Side.ALLIED, nationality="CW", cpa=25, oca=2, dca=2)
    wrong = _u("BN", side=Side.ALLIED, nationality="CW", cpa=10, oca=3, dca=3)
    assert organization.cw_at_allowance(walking, turn=75) == 1        # 19.94 non-motorized
    assert organization.cw_at_allowance(motor, turn=75) == 2          # 19.94 motorized
    assert organization.cw_at_allowance(wrong, turn=75) == 0          # 19.92 ratings
    assert organization.cw_at_allowance(walking, turn=74) == 0        # 19.91 not before GT 75


# --- THE PROOF: [15.53] fires ----------------------------------------------------------

def test_org_size_shift_only_reached_its_lowest_row_before_rule_19():
    """The state of the world BEFORE rule 19: no counter carries more than one Stacking Point
    (the ten HQ / gun roles are SP 0, everything else SP 1), so the transcribed [15.53] chart
    could reach only its lowest row -- the (1,0) 'battalion vs. a lone company or gun' edge,
    which DID fire (it is not wholly inert) -- and never the 2 / 3 / 5 SP brigade/division tiers
    that need a Parent Formation. Two SP-1 battalions tie, so their own row is a no-op."""
    assert combat_tables.org_size_shift(1, 1) == 0      # battalion vs battalion: no shift
    assert combat_tables.org_size_shift(1, 0) == 2      # battalion vs lone gun/company: the one
    #                                                     # shift reachable before rule 19


def test_org_size_shift_fires_for_the_first_time_when_a_kampfgruppe_forms():
    """[19.72] + [9.12] + [15.53]: four German battalions attached to a Battle Group HQ
    are ONE brigade-equivalent counter of 2 Stacking Points. Assaulting a lone enemy
    battalion (1 SP), the [15.53] Organization Size chart shifts TWO columns in the
    Kampfgruppe's favour off its '2 or 3 SP's / 1 SP' row -- the first time the chart reaches a
    brigade tier, which no counter could do before rule 19 built one."""
    hq = _u("KG", sp=2, org_type="ge_battle_group", is_combat=False, strength=1)
    kids = tuple(_u(f"B{i}", attached_to="KG", strength=8) for i in range(4))
    defender = _u("D1", side=Side.ALLIED, nationality="CW", strength=8)

    atk = organization.combat_size((hq,) + kids)
    dfd = organization.combat_size((defender,))
    assert (atk, dfd) == (2, 1)
    assert combat_tables.org_size_shift(atk, dfd) == 2       # [15.53] "2 or 3 SP's / 1 SP -> 2"

    shifted = combat.resolve(
        attacker_raw=64, defender_raw=16, defender_loss_raw=16, def_terrain=Terrain.DESERT,
        atk_roll=34, def_roll=34, attacker_size=atk, defender_size=dfd)
    flat = combat.resolve(
        attacker_raw=64, defender_raw=16, defender_loss_raw=16, def_terrain=Terrain.DESERT,
        atk_roll=34, def_roll=34, attacker_size=1, defender_size=1)
    assert shifted.column > flat.column                       # the chart MOVED the fight


def test_a_division_against_a_company_is_the_chart_s_eight_column_shift():
    """[15.53] 5 SP vs 0 SP = 8. Reachable only once rule 19 lets a division form."""
    div = _u("DIV", sp=5, org_type="ge_15_panzer_division", is_combat=False, strength=1)
    bdes = tuple(_u(f"BDE{i}", sp=2, attached_to="DIV", strength=8) for i in range(2))
    coy = _u("COY", side=Side.ALLIED, sp=0, strength=2)
    assert organization.combat_size((div,) + bdes) == 5
    assert organization.combat_size((coy,)) == 0
    assert combat_tables.org_size_shift(5, 0) == 8


def test_unit_defaults_carry_no_organization_tree():
    """Every existing counter and every hand-built test unit stays independent, so the
    whole chapter is inert until somebody attaches something (byte-identical)."""
    u = _u("X")
    assert (u.attached_to, u.assigned_to, u.org_type) == ("", "", "")
    assert organization.size(u, ()) == u.stacking_points
