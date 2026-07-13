"""The water SOURCES (rules 52.1-52.3) -- the wells, the oases and the Commonwealth pipeline.

The engine charged water DEMAND (52.4) and enforced the 52.53 attrition long before anything
modelled where water COMES FROM, so the campaign's armies drank from nothing and died of thirst:
~17.5k Axis water shortfalls, the Italian 10th Army gone by October 1940, and total Axis water
income across the whole 111-turn campaign of ZERO. These tests pin the supply side down.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords, supply, wells
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.engine import run
from game.events import EventKind, Side
from game.scenario import campaign, rommels_arrival, siege_of_tobruk
from game.terrain import Terrain

MAJOR_CITIES = ("C4807", "C4321", "A4827", "E1730", "E3613")   # Tobruk, Bardia, Benghazi, Cairo, Alexandria
OASES = ("C0127", "B0513", "C1014")                            # Siwa, Jalo, Giarabub


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


def _wells_at(state, coord):
    return [s for s in state.supplies if wells.is_water_source(s) and s.hex == coord]


def test_campaign_seeds_a_well_at_every_major_city_and_oasis():
    # [52.11] Water is found in wells and ONLY wells; major cities and oases each contain one.
    st = campaign(seed=1941)
    for label in MAJOR_CITIES + OASES:
        seeded = _wells_at(st, _ax(label))
        assert seeded, f"no well at {label}"
        # [52.13] unlimited: a reservoir no 111-turn draw can exhaust, on both sides of the hex.
        assert {w.side for w in seeded} == {Side.AXIS, Side.ALLIED}
        assert all(w.water >= wells.UNLIMITED_WELL for w in seeded)


def test_wells_are_water_only_immobile_and_do_not_evaporate():
    # [52.11] a well yields water and nothing else. base=True carries the other two properties
    # the rules demand: [52.44] water in wells and pipelines is NOT subject to evaporation, and
    # the engine refuses to relocate a base (rule 57) -- geography does not leapfrog.
    st = campaign(seed=1941)
    ws = [s for s in st.supplies if wells.is_water_source(s)]
    assert ws
    for w in ws:
        assert w.ammo == 0 and w.fuel == 0 and w.stores == 0 and w.water > 0
        assert w.base is True
        assert st.terrain.exists(w.hex)


def test_village_wells_are_a_finite_52_7_pool():
    # [52.7] villages/birs draw on the Water Availability Table and CAN deplete -- the [52.0]
    # "nuisance". Sized off the chart (mean draw x expected draws before the depletion die).
    assert wells._table_yield("village") == 4800        # Town row: 266.7 x 18 draws
    assert wells._table_yield("bir") == 2400            # Bir row:  200.0 x 12 draws
    st = campaign(seed=1941)
    barrani = _wells_at(st, _ax("C4131"))               # Sidi Barrani: a village, not a major city
    assert barrani and all(0 < w.water < wells.UNLIMITED_WELL for w in barrani)


def test_the_railhead_waters_the_commonwealth_but_not_the_axis():
    # The 52.22 asymmetry, at the one hex where it bites. Mersa Matruh is BOTH a village (a finite
    # 52.7 well) and the terminus of the Egyptian RR (60.7) -- and an operating RR hex IS a
    # pipeline, an unlimited source (52.23), for the COMMONWEALTH alone. So the Eighth Army drinks
    # its fill at the railhead while an Axis army that takes it inherits only the village well.
    st = campaign(seed=1941)
    matruh = _wells_at(st, _ax("D3714"))
    cw = [s for s in matruh if s.side == Side.ALLIED]
    axis = [s for s in matruh if s.side == Side.AXIS]
    assert max(s.water for s in cw) >= wells.UNLIMITED_WELL       # the pipeline terminus
    assert max(s.water for s in axis) == wells._table_yield("village")   # the village well alone


def test_commonwealth_pipeline_runs_the_rail_corridor():
    # [52.22] the Commonwealth may treat any operating RR hex as a pipeline; [52.23] a pipeline
    # hex is a source "similar to a major city" -- unlimited. [60.7] the RR runs to Mersa Matruh
    # and ends there. The Axis may NOT use the defunct Barce-Benghazi line (52.22).
    st = campaign(seed=1941)
    pipe = [s for s in st.supplies if wells.PIPE_ID_MARK in s.id]
    assert len(pipe) > 20                                        # Alexandria -> Matruh is ~40 hexes
    assert all(p.side == Side.ALLIED for p in pipe)              # 52.22: Commonwealth only
    assert all(p.water >= wells.UNLIMITED_WELL and p.base for p in pipe)
    ends = {p.hex for p in pipe}
    assert _ax("E3613") in ends and _ax("D3714") in ends         # both endpoints are on the line


def test_a_unit_on_a_major_city_can_trace_water():
    # The point of the whole subsystem: standing on Tobruk's well, a garrison drinks (52.13).
    st = campaign(seed=1941)
    tobruk = _ax("C4807")
    assert st.terrain.terrain[tobruk] == Terrain.MAJOR_CITY
    garrison = [u for u in st.units_at(tobruk) if u.is_combat]
    assert garrison
    for u in garrison:
        assert supply.plan_draw(st, u, supply.WATER, supply.water_cost(u)) is not None


def test_the_axis_army_is_not_destroyed_by_thirst():
    # The regression this subsystem exists to prevent. Before the wells, the Italian 10th Army
    # was 96 combat units at Game-Turn 1 and 28 by GT12 -- destroyed by 52.53 attrition inside a
    # month, with ZERO water ever drawn. The floor is set below the measured 72 (the residual is
    # combat loss plus the ~20 units the campaign's dump network already leaves outside EVERY
    # supply trace -- they can draw no ammo or stores either; see the module notes in game.wells).
    res = run(campaign(seed=1941, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    alive = [u for u in res.final.living(Side.AXIS) if u.is_combat]
    assert len(alive) >= 70

    drawn = sum(e.payload["qty"] for e in res.events
                if e.kind == EventKind.SUPPLY_CONSUMED and e.side == Side.AXIS
                and e.payload["commodity"] == supply.WATER)
    assert drawn > 1000                                  # was 892 across the ENTIRE 111-turn campaign


def test_benchmark_scenarios_have_no_wells():
    # Campaign-only content: rommels_arrival / siege_of_tobruk carry no well, so their event
    # streams stay byte-identical (they are the byte-locked benchmark scenarios).
    for build in (rommels_arrival, siege_of_tobruk):
        assert not [s for s in build(seed=42).supplies if wells.is_water_source(s)]
