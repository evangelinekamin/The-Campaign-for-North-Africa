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
    # CPA came from the charts for every mustered piece. RESTATED at Phase 5.1: this used to carve
    # out the inert `air` role at CPA 0. Air facilities are no longer units (rule 36 -- see
    # oob.air_facilities), and the SGSU counters that remain are vehicles with a real CPA (35.12:
    # "SGSU's have their Capability Point Allowance printed on the counter; they are vehicles"), so
    # there is no CPA-0 piece left to carve out.
    assert all(u.cpa > 0 for u in units)
    assert [u for u in units if u.steps[0].label == "sgsu"]              # the SGSU counters muster
    assert any(not u.is_combat for u in units)        # HQs are non-combat
    assert any(u.oca > 0 for u in units)              # close-assault units exist


def test_oob_classify_prefers_counter_identity_over_group():
    # the Rommel/DAK counter is grouped "Unassigned Infantry" but is an HQ
    assert oob.classify("GE Rommel - DAK", "GE Unassigned Infantry Units") == "hq"
    assert oob.classify("GE 3 - 300 OAS", "GE 300th Oasis Battalion") == "oasis"
    assert oob.classify("AU 2-17Aus - 20-9Aus", "AU 9th Australian Division") == "infantry"
    assert oob.classify("GE 33 - 15 (ATG)", "GE 15th Panzer Division") == "antitank"
    assert oob.classify("AL SGSU 250RAF", "AL SGSU") == "sgsu"     # rules 3.21/35.0, not a combat piece


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


# --- C2-1: the September-1940 Italian 10th Army (rule 60.31 / rule-90 [4.44b]/[4.46b]/[4.48]) ---

def test_classify_italian_tenth_army_counters():
    # Weapon-suffix markers on the COUNTER beat the parent formation; the Libyan Tank Command's
    # tankettes (LTC) read as armour; the Sahariano camel battalions as infantry.
    assert oob.classify("IT 64 - Cat (MG)", "IT 64th Catanzaro Division") == "mg"
    assert oob.classify("IT 204 - 4CCNN (ART)", "IT 4th CCNN (3 January) Division") == "artillery"
    # The Giarabub "(AA)" emplaced flak is an Anti-Aircraft-Type unit (rule 3.23 / 46.17 Pure
    # Flak) -> the `aa` role, NOT the old antitank proxy that stood in before the AA role existed.
    assert oob.classify("IT Grbub - Grbub (AA)", "IT Giariabub Oasis Complex Garrison") == "aa"
    assert oob.classify("IT 64 - Cat (ENG)", "IT 64th Catanzaro Division") == "infantry"
    # "IT X Cp" (X Corpo's guns) carries NO weapon marker on the counter, so the counter-only
    # classifier cannot type it: it defaults to infantry, and data/oob_italian.json carries an
    # explicit role:"artillery" for it (the data-driven path that replaces the old group guess).
    assert oob.classify("IT X Cp - none", "IT Unassigned Gun Units") == "infantry"
    assert oob.classify("IT 1Maletti - Maletti", "IT Gruppo Maletti") == "artillery"
    assert oob.classify("IT 3Sno-Sno - Maletti", "IT Gruppo Maletti") == "infantry"
    assert oob.classify("IT Trvli - LTC", "IT The Libyan Tank Command") == "tank"
    assert oob.classify("IT 1 Libyan - none", "IT 1st Libyan Infantry Division (Sibille)") == "infantry"
    # RESTATED at Phase 5.1: flying-boat Alighting areas and Air Landing Strips are not UNITS and
    # so are not classified at all -- their OOB records carry kind "air_facility" and build() never
    # reaches classify() for them (rule 36; see tests/test_air_facilities.py). classify() answers
    # only for counters that muster, and an unrecognised one defaults to infantry.
    assert oob.classify("Airboat Alighting axis", "AX Alighting/") == "infantry"
    assert oob.classify("Air Strip axis", "AX Airstrip/") == "infantry"


def test_classify_italian_gate_leaves_desert_fox_untouched():
    # The 'IT ' gate must not disturb the German/Commonwealth classifications.
    assert oob.classify("GE 33 - 15 (ATG)", "GE 15th Panzer Division") == "antitank"
    assert oob.classify("GE 3 - 300 OAS", "GE 300th Oasis Battalion") == "oasis"
    assert oob.classify("AL SGSU 250RAF", "AL SGSU") == "sgsu"


def test_morale_italian_formations():
    m = oob._morale_for                                                # signature: (group, counter)
    assert m("IT The Libyan Tank Command", "IT LTC - none") == 0       # Babini gruppo (before "Libyan")
    assert m("IT 2nd Libyan (Prescatori) Infantry Division", "II/3L") == -2
    assert m("IT Gruppo Maletti", "1Maletti") == -2
    assert m("IT 64th Catanzaro Division", "64 Cat") == -1
    assert m("IT 4th CCNN (3 January) Division", "4CCNN") == 0        # [4.44b]: 1st & 4th CCNN are 0
    assert m("IT Tobruk Garrison", "Marines") == -3
    assert m("IT Giariabub Oasis Complex Garrison", "Grbub") == 0     # [4.44b] rates the oasis fortress 0
    assert m("GE 300th Oasis Battalion", "300 OAS") == 0              # Oasis key still resolves for the DAK


def test_italian_oob_builds_with_it_stats_and_roles():
    # The raw Sept-1940 extraction has no nationality field, so build() infers IT from
    # the 'IT ' prefix: every counter musters with Italian stats (not the German fallback)
    # and a sensible role. Five weapon roles are represented across the 10th Army.
    units, _ = oob.build(oob_file="oob_italian.json", sections="ABCDE", reinforcements_file=None)
    muster = [u for u in units if u.side == Side.AXIS]
    assert len(muster) == 61                                          # the Italian 10th Army muster
    # RESTATED at Phase 5.1 (rules 35/36). This used to assert that the eight Axis Air Landing
    # Strips and the flying-boat Alighting area musters as inert `air`-role UNITS -- which was
    # Phase 3.1 rescuing them from being DISCARDED, and was still the wrong model: rule 36 makes an
    # air facility an INSTALLATION with a Capacity Level (game.state.AirFacility), not a counter
    # that stacks, traces and starves. They are now lifted out of units[] by oob.air_facilities, so
    # the muster is the 10th Army and nothing else. The count that matters moved to
    # tests/test_air_facilities.py; what is asserted here is that they are GONE FROM THE MUSTER,
    # not that they are gone from the game.
    assert not [u for u in muster if u.steps[0].label in ("air", "sgsu")]
    assert len(oob.air_facilities("oob_italian.json", sections="ABCDE")) == 11   # 8 Axis + 3 CW
    assert all(u.cpa > 0 for u in muster)                             # Italian chart CPA, not the GE fallback
    roles = {sr.label for u in muster for sr in u.steps}
    # The 10th Army fields infantry / artillery / MG / tank (the Libyan Tank Command) and AA
    # (the Giarabub emplaced flak) -- the "(AA)" gun that used to stand in as its only "antitank"
    # is now correctly AA (rule 3.23); this Sept-1940 extraction carries no dedicated IT AT counter.
    assert {"infantry", "artillery", "mg", "tank", "aa"} <= roles
    infantry = [u for u in muster if u.steps[0].label == "infantry"]
    assert infantry and all(u.cpa == 10 for u in infantry)             # IT infantry CPA 10, not the GE 25


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
