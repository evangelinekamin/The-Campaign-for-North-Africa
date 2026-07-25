"""Phase 4 slice S0/S2 -- the first-line-truck supply pools seeded onto units (rule 53.11).

Pins the transcribed [60.31]/[60.41] (campaign, rule 64.3) and [61.43]/[61.31] (Desert Fox)
first-line Truck-Point allotments as the Option-B fl_* carrying-ceiling fields on game.state.Unit
(scratchpad/port/phase4-first-line-trucks.md). The load-bearing, gated fact is the PER-SIDE Sigma
(59.42 makes the per-unit split a free choice); this file is that data lint plus the faithfulness
guards (garrisons static, German first-line deferred, reinforcements deferred). This file pins the
ALLOTMENT (the per-side Sigma); the ACTIVATION of the fl_* pools as the 53.11 last-mile carrier --
which moved both benchmark signatures -- is a later slice, pinned in tests/test_first_line_reach.py
and re-baselined in tests/baselines.py under rule [53.11].
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game import oob, scenario, supply
from game.events import Side
from game.state import StepRecord


def _tp(u):
    return u.fl_light + u.fl_medium + u.fl_heavy


def _side_tp(units, side, pred=lambda u: True):
    return sum(_tp(u) for u in units if u.side == side and pred(u))


def test_campaign_first_line_totals_match_60_31_60_41():
    # [60.31] Italian 10th Army = 55 L / 260 M / 45 H = 360 TP; [60.41] Western Desert Force =
    # 30 L / 125 M / 22 H = 177 TP. These per-side sums are the S0 gate (Axis 360 / CW 177) --
    # RESTATED (ammo-last-mile Part 2) to the GT1 muster (arrival_turn == 0) explicitly: this
    # test pins the [60.31]/[60.41] GT1 allotment specifically, which an unscoped side-wide sum
    # used to equal only because reinforcements carried no first-line trucks at all. They now do
    # (the [4.43a]/[4.43b] Attached-Trucks schedule, test_reinforcement_first_line_* below), so
    # the old unscoped assertion would silently start pinning THAT total too.
    st = scenario.campaign(max_turns=1)
    gt1 = lambda u: u.arrival_turn == 0                                    # noqa: E731
    assert _side_tp(st.units, Side.AXIS, gt1) == 360
    assert _side_tp(st.units, Side.ALLIED, gt1) == 177
    for cls, ax, cw in (("fl_light", 55, 30), ("fl_medium", 260, 125), ("fl_heavy", 45, 22)):
        assert sum(getattr(u, cls) for u in st.units if u.side == Side.AXIS and gt1(u)) == ax
        assert sum(getattr(u, cls) for u in st.units if u.side == Side.ALLIED and gt1(u)) == cw


def test_benchmark_first_line_totals_match_61_43_61_31():
    # [61.43] Italian first line = 45 L / 220 M / 50 H = 315 TP (assigned to Italian units only);
    # [61.31] Commonwealth = 15 L / 113 M / 5 H = 133 TP. German first-line is the deferred [4.43b]
    # Reinforcement-Schedule attachment, so the German Sigma is 0.
    st = scenario.rommels_arrival()
    assert _side_tp(st.units, Side.AXIS, lambda u: u.formation.startswith("IT ")) == 315
    assert _side_tp(st.units, Side.AXIS, lambda u: u.formation.startswith("GE ")) == 0
    assert _side_tp(st.units, Side.ALLIED) == 133


def test_siege_inherits_the_benchmark_first_line():
    # siege_of_tobruk is rommels_arrival + replace, so it carries the identical allotment.
    st = scenario.siege_of_tobruk()
    assert _side_tp(st.units, Side.AXIS, lambda u: u.formation.startswith("IT ")) == 315
    assert _side_tp(st.units, Side.ALLIED) == 133


def test_static_garrisons_carry_no_first_line_reinforcements_now_do():
    # The scan: "Garrisons ... start with no organic transport (faithful: they are static)" --
    # unaffected by Part 2. RESTATED (ammo-last-mile Part 2): reinforcement first-line trucks
    # ([4.43a]/[4.43b]) are no longer deferred -- this assertion used to read "== 0" and PROVED
    # the armour-elimination diagnosis's headline gap (every CW armour counter is a reinforcement,
    # so none of them ever carried a truck buffer). The transcribed reinforcement-schedule total
    # (test_reinforcement_first_line_totals_match_the_transcribed_schedule) is 2072 CW + 437 GE +
    # 885 IT = 3394; 35 of the Axis TP land on no combat-eligible unit and stay unattached -- GT44
    # GE names only a headquarters (is_combat=False, see
    # test_reinforcement_first_line_skips_a_bucket_with_no_combat_recipient) and GT99 IT's lone
    # named battalion (57 Brs Bn, detached from 16 Pistoia Div) is one of the minor units this
    # campaign's curated reinforcement roster never gave a counter to.
    st = scenario.campaign(max_turns=1)
    assert _side_tp(st.units, Side.AXIS, lambda u: u.is_garrison_home) == 0
    assert _side_tp(st.units, Side.ALLIED, lambda u: u.is_garrison_home) == 0
    reinforcements = lambda u: u.arrival_turn != 0                         # noqa: E731
    assert sum(_tp(u) for u in st.units if u.side == Side.ALLIED and reinforcements(u)) == 2072
    assert sum(_tp(u) for u in st.units if u.side == Side.AXIS and reinforcements(u)) == 1287


def test_build_defaults_to_desert_fox_section_61():
    # oob.build with no first_line uses the Section-61 default (64.3), matching the benchmark.
    units, _ = oob.build(sections="ABC")
    assert _side_tp(units, Side.AXIS, lambda u: u.formation.startswith("IT ")) == 315
    assert _side_tp(units, Side.ALLIED) == 133


def test_seed_first_line_data_lint_fires_when_no_unit_can_hold_the_pool():
    # The per-side Sigma is exact by construction; the guard fails loud if a side's eligible set is
    # empty (a future OOB change) so its allotment would silently vanish (design S0's data lint),
    # rather than shipping a shortfall below the transcribed total.
    with pytest.raises(ValueError, match="expected 5"):
        oob._seed_first_line([], {Side.ALLIED: {"light": 5, "medium": 0, "heavy": 0}})


def test_stores_water_contents_stay_zero_while_ammo_is_seeded():
    # RESTATED for slice S6 (50.0 ammo basic load): the AMMO pool is now seeded to the intrinsic
    # 'fire once' capacity (supply.ammo_capacity, the dual of the 49.14 fuel tank), so every combat
    # unit carries a nonzero ammo load. Stores/water CONTENTS remain a later slice (S7/S8), so those
    # two pools stay 0. First-line trucks (fl_*) stay dormant for all three commodities here.
    st = scenario.campaign(max_turns=1)
    assert all(u.stores == u.water == 0 for u in st.units)
    assert all(u.ammo == supply.ammo_capacity(u) for u in st.units)   # seeded to capacity
    assert any(u.ammo > 0 for u in st.units)                          # combat units carry a load


# --- [4.43a]/[4.43b] Attached Trucks: first-line trucks ON REINFORCEMENTS (ammo-last-mile Part 2) ---

def test_reinforcement_first_line_totals_match_the_transcribed_schedule():
    # data/reinforcement_first_line.json is the scan transcription of the [4.43a] CW / [4.43b] Axis
    # "Attached Trucks" column (tools/vassal/build_reinforcement_first_line.py); this pins its
    # per-nationality Sigma so a future edit cannot silently drop or inflate a cell.
    import json
    pool = json.loads((Path(oob._DATA) / "reinforcement_first_line.json").read_text())
    totals = {}
    for rec in pool:
        t = totals.setdefault(rec["nationality"], [0, 0, 0])
        t[0] += rec["light"]; t[1] += rec["medium"]; t[2] += rec["heavy"]
    assert tuple(totals["CW"]) == (397, 1425, 250)     # [4.43a], PDF p.114-115
    assert tuple(totals["GE"]) == (45, 323, 69)        # [4.43b], PDF p.145-146
    assert tuple(totals["IT"]) == (182, 615, 88)       # [4.43b], PDF p.145-146


def test_reinforcement_first_line_seeds_a_cw_tank_reinforcement():
    # The armour-elimination diagnosis's headline gap: EVERY CW armour counter in the campaign is a
    # rule-20 reinforcement, and _seed_first_line only ever seeded the GT1 muster, so all 39 carried
    # first_line_capacity(AMMO) == 0. [4.43a] GT88: "24 Armored Bde [8]; Trucks: 7 L, 36 M, 8 H" -- it
    # is the LONE combat-eligible arrival that Game-Turn, so it receives the entire bucket undivided --
    # the direct proof the fix reaches CW armour.
    st = scenario.campaign(max_turns=1)
    tank = st.unit("24-Armd-Bde")   # 8th Armoured Division, arrival_turn 88 (see reinforcements_campaign.json)
    assert tank is not None and tank.arrival_turn == 88
    assert (tank.fl_light, tank.fl_medium, tank.fl_heavy) == (7, 36, 8)
    assert supply.first_line_capacity(tank, "AMMO") == 7 * 2 + 36 * 4 + 8 * 8


def test_reinforcement_first_line_skips_a_bucket_with_no_combat_recipient():
    # GT44 GE ("HQ 90 Light Div; Trucks: 10 L, 10 M.") names ONLY a headquarters -- is_combat=False,
    # the same rule the GT1 muster's own eligibility filter already applies -- so the bucket has no
    # unit to attach to and is skipped rather than forced onto something the schedule never named.
    st = scenario.campaign(max_turns=1)
    hq = st.unit("HQ-90-Light-Div")
    assert hq is not None and hq.arrival_turn == 44 and not hq.is_combat
    assert (hq.fl_light, hq.fl_medium, hq.fl_heavy) == (0, 0, 0)


def test_seed_reinforcement_first_line_even_splits_a_shared_bucket():
    # Unit test of the mechanism in isolation: two combat-eligible units sharing one (nationality,
    # arrival_turn) bucket split it evenly (remainder to the first, exactly like _share/_seed_first_line's
    # own GT1 convention) -- the rule's own text ("may be freely divided amongst the units").
    from game.state import Unit
    from game.terrain import Mobility

    def u(uid, side, nat, gt, combat=True):
        return Unit(uid, side, (0, 0), (StepRecord("s", 4),), mobility=Mobility.VEHICLE, cpa=10,
                    stacking_points=1, oca=1, dca=1,
                    nationality=nat, arrival_turn=gt, is_combat=combat)

    units = [u("A", Side.ALLIED, "CW", 5), u("B", Side.ALLIED, "CW", 5),
             u("HQ", Side.ALLIED, "CW", 5, combat=False),          # excluded: is_combat False
             u("C", Side.ALLIED, "CW", 6)]                          # different GT: untouched
    out = oob._seed_reinforcement_first_line(
        units, [{"nationality": "CW", "arrival_turn": 5, "light": 5, "medium": 0, "heavy": 0}])
    by_id = {x.id: x for x in out}
    assert by_id["A"].fl_light == 3 and by_id["B"].fl_light == 2      # 5 split 2 ways, remainder first
    assert by_id["HQ"].fl_light == 0
    assert by_id["C"].fl_light == 0
