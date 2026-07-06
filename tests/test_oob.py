"""Tests for the Rommel's Arrival OOB loader and scenario (game.oob,
scenario.rommels_arrival): units build from the parsed save + chart stats, the
counter identity beats the (sometimes misleading) organisational group, and the
scenario runs to completion deterministically with invariants intact."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import logistics_data, oob, supply
from game.apply import fold
from game.engine import determinism_signature, run
from game.events import Side
from game.policy import ScriptedPolicy
from game.scenario import rommels_arrival


def _stranded_combat(state, side):
    """Combat units of `side` on-map at start that cannot trace fuel and/or ammo
    (missing either strands it) from the placed dumps (the real 32.16 supply gate)."""
    return [u for u in state.living(side) if u.is_combat and not (
        supply.plan_draw(state, u, supply.FUEL, supply.fuel_rate(u)) is not None
        and supply.plan_draw(state, u, supply.AMMO, supply.ammo_cost(u, phasing=True)) is not None)]


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


def test_default_supply_is_faithfully_scarce():
    # The FAITHFUL default keeps only the authored start-line dumps: the spread-out
    # periphery (Italian rear divisions, the Cyrenaica screen) starts genuinely
    # out of supply (rule 32.16), so the Quartermaster has something to ration and
    # "outrun your supply" is possible. The advance is sustained by MOVING dumps
    # forward (rule 32.3), not by blanketing every unit with a co-located dump.
    faithful = rommels_arrival()                         # default: blanket_supply=False
    blanket = rommels_arrival(blanket_supply=True)       # the old auto-pad crutch

    # Scarcity is real: at least one combat unit per side cannot trace supply at t1.
    assert _stranded_combat(faithful, Side.AXIS)
    assert _stranded_combat(faithful, Side.ALLIED)
    # The reservoir is REAL-SCALE now (Regime B): the Axis dumps hold the whole [61.44]
    # start-line pool, so scarcity is no longer a gross shortage but a DISTRIBUTION
    # problem -- the fuel exists, but the 32.16 trace strands the periphery (asserted
    # above) and the 49.13 x-TOE-strength demand is itself real-scale (~5-8x the old proxy).
    # Step 5 also seeds the [61.44] Tripoli-box built-in (held at the rear harbour, IN
    # ADDITION to the field-dump split), so the Axis total is the field pool + that box.
    axis_fuel = sum(s.fuel for s in faithful.supplies if s.side == Side.AXIS)
    assert axis_fuel == (logistics_data.axis_dump_pool_61_44()["FUEL"]
                         + logistics_data.tripoli_builtin_61_44()["FUEL"])   # [61.44] pool + box
    demand = sum(supply.fuel_cost(u, 1) for u in faithful.living(Side.AXIS)
                 if u.is_combat and supply.fuel_rate(u) > 0)
    assert demand > 5 * 33                               # per-stage floor now dwarfs the old ~33

    # The crutch (blanket_supply=True) leaves nobody stranded and pads the map with
    # far more dumps -- the exact over-supply we are removing.
    assert not _stranded_combat(blanket, Side.AXIS)
    assert not _stranded_combat(blanket, Side.ALLIED)
    assert len(blanket.supplies) > len(faithful.supplies)


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
