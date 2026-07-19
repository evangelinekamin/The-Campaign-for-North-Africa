"""Phase 4 slice S0/S2 -- the first-line-truck supply pools seeded onto units (rule 53.11).

Pins the transcribed [60.31]/[60.41] (campaign, rule 64.3) and [61.43]/[61.31] (Desert Fox)
first-line Truck-Point allotments as the Option-B fl_* carrying-ceiling fields on game.state.Unit
(scratchpad/port/phase4-first-line-trucks.md). The load-bearing, gated fact is the PER-SIDE Sigma
(59.42 makes the per-unit split a free choice); this file is that data lint plus the faithfulness
guards (garrisons static, German first-line deferred, reinforcements deferred). The pools are seeded
BESIDE the abstract 32.16 trace and NOT consumed here, so both benchmark determinism signatures are
byte-identical -- pinned in tests/test_convoys / test_ports; nothing to re-baseline for this slice.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game import oob, scenario, supply
from game.events import Side


def _tp(u):
    return u.fl_light + u.fl_medium + u.fl_heavy


def _side_tp(units, side, pred=lambda u: True):
    return sum(_tp(u) for u in units if u.side == side and pred(u))


def test_campaign_first_line_totals_match_60_31_60_41():
    # [60.31] Italian 10th Army = 55 L / 260 M / 45 H = 360 TP; [60.41] Western Desert Force =
    # 30 L / 125 M / 22 H = 177 TP. These per-side sums are the S0 gate (Axis 360 / CW 177).
    st = scenario.campaign(max_turns=1)
    assert _side_tp(st.units, Side.AXIS) == 360
    assert _side_tp(st.units, Side.ALLIED) == 177
    for cls, ax, cw in (("fl_light", 55, 30), ("fl_medium", 260, 125), ("fl_heavy", 45, 22)):
        assert sum(getattr(u, cls) for u in st.units if u.side == Side.AXIS) == ax
        assert sum(getattr(u, cls) for u in st.units if u.side == Side.ALLIED) == cw


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


def test_static_garrisons_and_reinforcements_carry_no_first_line():
    # The scan: "Garrisons ... start with no organic transport (faithful: they are static)"; and
    # reinforcement first-line trucks ([4.43b]) are deferred, so off-map arrivals seed none.
    st = scenario.campaign(max_turns=1)
    assert _side_tp(st.units, Side.AXIS, lambda u: u.is_garrison_home) == 0
    assert _side_tp(st.units, Side.ALLIED, lambda u: u.is_garrison_home) == 0
    assert sum(_tp(u) for u in st.units if u.arrival_turn != 0) == 0


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
