"""Phase 4, slice S1: the 49.14 Fuel Capacity tank.

Every unit is seeded with the fuel its own vehicles carry (supply.fuel_capacity), that fuel is
credited into the t0 conservation base (scenario._initial_supply), and it is INERT -- no consumer
drains Unit.fuel until the fuel switch (S5), so the event log stays byte-identical and only
initial_supply rises. Conservation OVER a fold is exercised by the existing campaign tests (the
invariant runs live during run()); these tests inspect the seeded state only, so they stay fast."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import supply
from game.scenario import campaign, coastal_corridor


def test_fuel_capacity_is_one_full_cpa_move():
    # 49.14 Note: the tank is "exactly sufficient to allow all its CPA to be expended on movement"
    # -- i.e. fuel_cost(unit, unit.cpa). DAK-5le: rate 2, cpa 25, strength 5 -> 2 x ceil(25/5) x 5.
    dak = coastal_corridor().unit("DAK-5le")
    assert supply.fuel_capacity(dak) == supply.fuel_cost(dak, dak.cpa) == 50


def test_foot_unit_has_no_tank():
    # 49.12: non-motorized units walk and burn nothing, so their Fuel Capacity is 0.
    foot = coastal_corridor().unit("UK-9Aus")            # FOOT
    assert supply.fuel_rate(foot) == 0
    assert supply.fuel_capacity(foot) == 0


def test_campaign_seeds_every_unit_to_capacity():
    # build() fills each unit's 49.14 tank -- for ALL of them (0 for foot), and motorized units
    # carry real fuel.
    s = campaign(seed=1941)
    for u in s.units:
        assert u.fuel == supply.fuel_capacity(u), f"{u.id} tank != capacity"
    assert any(u.fuel > 0 for u in s.units), "no unit carries fuel"


def test_tanks_credited_to_initial_supply():
    # the t0 conservation base credits every tank: initial_supply[FUEL] == dumps' fuel + Sigma tanks.
    s = campaign(seed=1941)
    dump_fuel = sum(su.fuel for su in s.supplies)
    tank_fuel = sum(u.fuel for u in s.units)
    assert tank_fuel > 0
    assert s.initial_supply["FUEL"] == dump_fuel + tank_fuel


def test_reinforcement_tanks_are_in_the_base_not_a_faucet():
    # a dormant rule-20 reinforcement (arrival_turn > 1) is already in state.units at t0 with a full
    # tank, so its fuel is in the conservation base from the start -- its arrival mints nothing.
    s = campaign(seed=1941)
    reinf = [u for u in s.units if u.arrival_turn > 1 and supply.fuel_rate(u) > 0]
    assert reinf, "campaign scheduled no motorized reinforcements?"
    for u in reinf:
        assert u.fuel == supply.fuel_capacity(u) > 0
