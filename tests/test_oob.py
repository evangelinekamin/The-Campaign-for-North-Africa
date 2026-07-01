"""Tests for the Rommel's Arrival OOB loader and scenario (game.oob,
scenario.rommels_arrival): units build from the parsed save + chart stats, the
counter identity beats the (sometimes misleading) organisational group, and the
scenario runs to completion deterministically with invariants intact."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import oob
from game.apply import fold
from game.engine import determinism_signature, run
from game.events import Side
from game.policy import ScriptedPolicy
from game.scenario import rommels_arrival


def test_oob_builds_both_sides_with_chart_stats():
    units, supplies = oob.build(sections="ABC")
    assert [u for u in units if u.side == Side.AXIS]
    assert [u for u in units if u.side == Side.ALLIED]
    assert supplies
    assert all(u.cpa > 0 for u in units)              # CPA came from the charts
    assert any(not u.is_combat for u in units)        # HQs are non-combat
    assert any(u.oca > 0 for u in units)              # close-assault units exist


def test_oob_classify_prefers_counter_identity_over_group():
    # the Rommel/DAK counter is grouped "Unassigned Infantry" but is an HQ
    assert oob.classify("GE Rommel - DAK", "GE Unassigned Infantry Units") == "hq"
    assert oob.classify("GE 3 - 300 OAS", "GE 300th Oasis Battalion") == "oasis"
    assert oob.classify("AU 2-17Aus - 20-9Aus", "AU 9th Australian Division") == "infantry"
    assert oob.classify("GE 33 - 15 (ATG)", "GE 15th Panzer Division") == "antitank"
    assert oob.classify("AL SGSU 250RAF", "AL SGSU") is None       # air base -> skip


def test_per_model_stats_override_role():
    u = {x.id: x for x in oob.build(sections="ABC")[0]}
    assert u["BR-4-RTR"].armor_protection == 6         # Matilda II -- heavy armour
    assert u["BR-Tiger"].armor_protection == 4         # Crusader II
    assert u["GE-I-8-Pz"].anti_armor == 4              # Pz III H
    assert u["GE-33---15-(ATG)"].anti_armor == 5       # 5cm Pak 38 (GE antitank default)


def test_oob_assigns_basic_morale_by_formation():
    m = {u.id: u.morale for u in oob.build(sections="ABC")[0]}
    assert next(v for k, v in m.items() if "5-Le" in k) == 2        # 5th Light Panzer +2
    assert next(v for k, v in m.items() if "Aus" in k) == 1         # 9th Australian +1
    assert next(v for k, v in m.items() if "Rommel" in k) == 1      # DAK HQ +1
    assert next(v for k, v in m.items() if "OAS" in k) == 0         # 300th Oasis 0


def test_rommels_arrival_runs_soundly():
    st = rommels_arrival()
    assert any(u.side == Side.AXIS for u in st.units)
    assert any(u.side == Side.ALLIED for u in st.units)
    assert st.supplies
    res = run(rommels_arrival(), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert res.winner in (Side.AXIS, Side.ALLIED)
    assert fold(res.initial, res.events) == res.final            # replay-equivalent
    res2 = run(rommels_arrival(), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(res.events) == determinism_signature(res2.events)
