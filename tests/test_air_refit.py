"""[38.3] AIRCRAFT MAINTENANCE AND THE REFIT TABLE -- Phase 5.3, the sortie-rate governor.

Before this block one AirWing could fly the same six strike points every Operations Stage for a
hundred and eleven Game-Turns, because nothing ever wore out. The rules ported here are:

  38.3  "Refitting aircraft is repairing and maintaining them so that they can fly ANOTHER MISSION.
        In order to fly any mission other than a transfer, a plane must be refitted."
  38.31 "As soon as a plane flies any mission other than transfer, IT MUST BE REFITTED AGAIN. A
        plane that is not refitted may fly no mission other than transfer, EVEN IF IT IS REFUELED."
  38.34 "Refitting is NOT A GUARANTEED PROCESS... Players must roll for each squadron undergoing
        refit... The table gives him the PERCENTAGE OF PLANES SUCCESSFULLY REFITTED (round up)."
  38.35 "...if the planes attempting refit are ITALIAN... ADDS TWO to the dieroll. If the planes
        are GERMAN, ADD ONE."  -- the rulebook's model of Axis unserviceability
  38.36 "For every squadron undergoing an attempted refit -- WHETHER SUCCESSFUL OR NOT -- the Player
        must have present and actually EXPEND ONE STORES POINT."
  35.14 "SGSUs without the required supplies (for themselves) MAY NOT REPAIR THEIR PLANES."
"""
from __future__ import annotations

import random
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.air as air
import game.supply as supply
from game.apply import fold
from game.engine import _air_maintenance, _air_points, _air_support, _Run, run
from game.events import EventKind, Phase, Side
from game.invariants import check
from game.logistics_data import aircraft_refit_table_38_37, squadron_capacity_35_23
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import campaign, rommels_arrival, siege_of_tobruk
from game.state import (AirFacility, AirMission, AirWing, GameState, StepRecord, SupplyUnit,
                        Unit, VP)
from game.terrain import Mobility, Terrain


# --- [38.37] / [35.23] the transcribed charts --------------------------------------------------

def test_the_refit_table_is_the_chart_on_page_10_of_the_scan():
    """[38.37B] AIRCRAFT REFIT TABLE, By Squadron -- eyes-verified off the 1979 scan (Charts and
    Tables page 10, PDF page 105, beside the [24.18] Demolition Chart and the [35.23] Squadron
    Capacity Chart):

        Dice Roll:              1    2    3    4    5   6,7  8,9
        % of Planes Refitted:  100   80   70   60   50   40   33
    """
    printed = {1: 100, 2: 80, 3: 70, 4: 60, 5: 50, 6: 40, 7: 40, 8: 33, 9: 33}
    for roll, pct in printed.items():
        assert air.refit_percent(roll) == pct, roll
    # the columns partition the printed 1..9 exactly, with no gap and no overlap
    cols = aircraft_refit_table_38_37()["columns"]
    covered = [d for c in cols for d in range(c["die"][0], c["die"][1] + 1)]
    assert covered == list(range(1, 10))
    # and 1..9 is exactly the span ONE d6 plus the chart's own modifiers can reach -- the internal
    # proof that 38.34's "throws one die" is a d6: 6 + 2 (Italian SGSU) + 1 (foreign squadron) = 9
    mods = aircraft_refit_table_38_37()["modifiers"]
    assert 6 + mods["italian_sgsu"] + mods["foreign_squadron"] == 9


def test_38_35_the_serviceability_modifiers_are_the_axis_unserviceability():
    """"German Squadron Ground Support Unit add 1. Italian Ground Support Unit add 2." A HIGHER
    modified roll is a WORSE row, so these two printed numbers are the whole asymmetry."""
    assert air.refit_drm("IT") == 2
    assert air.refit_drm("GE") == 1
    assert air.refit_drm("CW") == 0
    assert air.refit_drm("") == 0                    # a counter that states no nationality
    # and the asymmetry is real over the die: worse expected recovery for both Axis nationalities
    mean = lambda drm: sum(air.refit_percent(d + drm) for d in range(1, 7)) / 6
    assert mean(0) > mean(1) > mean(2)
    assert round(mean(0), 1) == 66.7 and round(mean(1), 1) == 56.7 and round(mean(2), 1) == 48.8


def test_38_34_the_percentage_is_of_the_planes_undergoing_refit_rounded_up():
    """"The table gives him the percentage of planes successfully refitted. (Round all fractions
    up.)" -- so a squadron never loses a plane to arithmetic."""
    assert air.refitted_planes(10, 1) == 10          # 100%
    assert air.refitted_planes(10, 5) == 5           # 50%
    assert air.refitted_planes(10, 8) == 4           # 33% of 10 = 3.3 -> 4
    assert air.refitted_planes(3, 8) == 1            # 33% of 3 = 0.99 -> 1
    assert air.refitted_planes(1, 9) == 1            # the last plane always has a chance back
    assert air.refitted_planes(0, 1) == 0


def test_the_squadron_capacity_chart_is_transcribed():
    """[35.23] SQUADRON CAPACITY CHART, same scanned page: Ready + Reserve = Total, and the Total
    is what 38.33 caps one SGSU's refitting at."""
    chart = squadron_capacity_35_23()
    assert (chart["italian"]["ready"], chart["italian"]["reserve"]) == (9, 3)
    assert (chart["german"]["ready"], chart["german"]["reserve"]) == (12, 4)
    assert (chart["commonwealth_1940_41"]["ready"], chart["commonwealth_1940_41"]["reserve"]) \
        == (12, 4)
    assert (chart["commonwealth_1942_43"]["ready"], chart["commonwealth_1942_43"]["reserve"]) \
        == (18, 6)
    for row in chart.values():
        assert row["ready"] + row["reserve"] == row["total"]
    # 38.33 reads the Total, and the Commonwealth squadron grows mid-war
    assert air.squadron_capacity("IT", 1941) == 12
    assert air.squadron_capacity("GE", 1941) == 16
    assert air.squadron_capacity("CW", 1941) == 16
    assert air.squadron_capacity("CW", 1942) == 24


# --- fixtures ---------------------------------------------------------------------------------

def _sgsu(uid="SGSU", side=Side.AXIS, hex_=(0, 0), nationality="IT", **kw) -> Unit:
    """An SGSU exactly as game.oob builds one (35.12: no combat values, no stacking points), with
    the nationality the [38.37] modifiers are printed per."""
    return Unit(uid, side, hex_, (StepRecord(air.SGSU_ROLE, 1),), Mobility.MOTORIZED,
                cpa=30, stacking_points=0, oca=0, dca=0, is_combat=False,
                nationality=nationality, **kw)


def _field(fid="FIELD", side=Side.AXIS, hex_=(0, 0), kind=air.AIRFIELD, level=None) -> AirFacility:
    cap = air.max_capacity(kind)
    return AirFacility(fid, side, hex_, kind=kind, level=cap if level is None else level,
                       max_level=cap)


def _dump(sid="AF-Sup", side=Side.AXIS, hex_=(0, 0), fuel=99, stores=99, **kw) -> SupplyUnit:
    base = {"ammo": 0, "water": 0}
    return SupplyUnit(sid, side, hex_, fuel=fuel, stores=stores, air_dump=True, **{**base, **kw})


def _state(*, units=None, facilities=None, supplies=None, missions=(), strike=6, recon=0,
           fighters=0, stage=2, turn=1, unfit=None) -> GameState:
    """An Axis LAND wing based on an airfield at (0,0) with a fed Italian SGSU, over an Allied
    stack at (1,0). Stage 2 by default, past [59.32]'s free opening tank."""
    foe = Unit("GAR", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=2, oca=5, dca=8)
    units = (foe,) + ((_sgsu(),) if units is None else tuple(units))
    supplies = tuple([_dump()] if supplies is None else supplies)
    return GameState(
        turn=turn, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR},
                           fortifications={}),
        control={}, units=units, target_hex=(1, 0),
        supplies=supplies,
        consumed={c: 0 for c in supply.COMMODITIES},
        # the conservation base (rule 32): on_hand + consumed == initial, so the fixture's own
        # larder is what it starts with -- otherwise game.invariants would read every Point the
        # air force draws as one conjured out of nothing
        initial_supply={c: sum(getattr(su, c.lower()) for su in supplies)
                        for c in supply.COMMODITIES},
        air=(AirWing("LW", Side.AXIS, "LAND", fighters=fighters, strike=strike, recon=recon),),
        air_missions=tuple(missions),
        air_facilities=tuple([_field()] if facilities is None else facilities),
        air_unfit=dict(unfit or {}), stage=stage)


def _pin_die(r: _Run, value: int) -> None:
    """Pin the refit stream to one known die and leave every other stream alone (game.dice.load)."""
    class _Fixed(random.Random):
        def randint(self, a, b):
            return value
    r.dice.load("air_refit", _Fixed())


AXIS_STRIKE = "AXIS/LAND/strike"


# --- [38.31] flying spends readiness -----------------------------------------------------------

def test_38_31_a_mission_flown_leaves_its_planes_unfit():
    """"As soon as a plane flies any mission other than transfer, it must be refitted again." Six
    strike Air Points are two Ju 87Bs (34.14, bombload 5), so two aeroplanes come back unfit."""
    r = _Run(_state(missions=(AirMission(Side.AXIS, "strike", (1, 0), 1),)))
    _air_support(r, Side.AXIS, set())
    unfit = [e for e in r.events if e.kind == EventKind.AIR_SQUADRON_UNFIT]
    assert [e.payload["planes"] for e in unfit] == [2]
    assert unfit[0].payload["squadron"] == AXIS_STRIKE
    assert r.state.air_unfit == {AXIS_STRIKE: 2}
    assert air.ready_planes(r.state, Side.AXIS, "LAND", "strike") == 0


def test_38_31_an_unrefitted_squadron_may_fly_no_mission_even_when_fuelled():
    """"A plane that is not refitted may fly no mission other than transfer, EVEN IF IT IS
    REFUELED." The larder is full; the squadron is not."""
    st = _state(unfit={AXIS_STRIKE: 2}, missions=(AirMission(Side.AXIS, "strike", (1, 0), 1),))
    assert _air_points(st, Side.AXIS, "LAND", "strike") == 0
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.SUPPLY_CONSUMED for e in r.events)   # no fuel drawn
    assert r.state.supply("AF-Sup").fuel == 99
    # the tasking still records itself -- a strike with nothing in the air, exactly as a side that
    # has LOST THE SKY to a scale of 0 already did -- but it delivers no Bomb Points and pins nobody
    strike = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert [(e.payload["strength"], e.payload["pinned"]) for e in strike] == [(0, [])]
    assert not any(e.kind == EventKind.AIR_SQUADRON_UNFIT for e in r.events)


def test_38_31_a_half_refitted_squadron_flies_at_its_refitted_planes_share():
    """One Ju 87B of two ready carries its own Bombload of 5 into the [41.5] column, not the
    squadron's 6 -- the same arithmetic air.refuel uses for a part-fuelled force."""
    st = _state(unfit={AXIS_STRIKE: 1})
    assert air.ready_planes(st, Side.AXIS, "LAND", "strike") == 1
    assert _air_points(st, Side.AXIS, "LAND", "strike") == 5
    # and flying it un-fits that ONE plane, never more than were ready
    r = _Run(replace(st, air_missions=(AirMission(Side.AXIS, "strike", (1, 0), 1),)))
    _air_support(r, Side.AXIS, set())
    ev = [e for e in r.events if e.kind == EventKind.AIR_SQUADRON_UNFIT]
    assert [e.payload["planes"] for e in ev] == [1]
    assert r.state.air_unfit == {AXIS_STRIKE: 2}


def test_the_fighter_arm_is_deliberately_outside_the_ledger():
    """The always-on air-superiority contest is not an ORDERED mission -- no order routes to it and
    nothing can decline it (40.21/40.3's Scramble, 38.25) -- so it neither pays fuel nor spends
    readiness. It joins the ledger when CAP is a real assignable mission (Phase 5.5). This test
    exists so the exemption is a decision on record rather than an oversight."""
    from game.engine import _REFITTABLE_ROLES
    assert _REFITTABLE_ROLES == ("recon", "strike")
    st = _state(fighters=8, unfit={"AXIS/LAND/fighters": 99})
    assert _air_points(st, Side.AXIS, "LAND", "fighters") == 8       # untouched by the ledger


# --- [38.34] / [38.36] the maintenance beat ----------------------------------------------------

def test_38_34_the_refit_roll_returns_the_tables_percentage():
    """A die of 3 at an Italian SGSU is a modified 5 -> 50% of the two unfit Stukas -> one back."""
    r = _Run(_state(unfit={AXIS_STRIKE: 2}))
    _pin_die(r, 3)
    _air_maintenance(r)
    ev = [e for e in r.events if e.kind == EventKind.AIR_REFIT_RESOLVED]
    assert len(ev) == 1
    p = ev[0].payload
    assert (p["die"], p["drm"], p["roll"], p["percent"]) == (3, 2, 5, 50)
    assert (p["undergoing"], p["refitted"], p["unfit"]) == (2, 1, 1)
    assert ev[0].rng_draws == (3,)                     # the die is certified in the log
    assert r.state.air_unfit == {AXIS_STRIKE: 1}
    assert air.ready_planes(r.state, Side.AXIS, "LAND", "strike") == 1


def test_38_34_a_full_refit_clears_the_squadron_from_the_ledger():
    r = _Run(_state(unfit={AXIS_STRIKE: 2}))
    _pin_die(r, 1)                                     # 1 + 2 Italian = 3 -> 70% of 2 -> 2 (round up)
    _air_maintenance(r)
    assert r.state.air_unfit == {}                     # no key means nothing unfit (38.31)
    assert air.ready_planes(r.state, Side.AXIS, "LAND", "strike") == 2


def test_38_36_one_stores_point_per_attempt_whether_it_succeeds_or_not():
    """"For every squadron undergoing an attempted refit -- whether successful or not -- the Player
    must have present and actually expend one Stores Point." It comes off the 36.17 air dump."""
    for die in (1, 6):                                 # a good roll and the worst one
        r = _Run(_state(unfit={AXIS_STRIKE: 2}))
        _pin_die(r, die)
        _air_maintenance(r)
        drawn = [e for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]
        assert [(e.payload["supply_id"], e.payload["commodity"], e.payload["qty"])
                for e in drawn] == [("AF-Sup", supply.STORES, 1)]
        assert drawn[0].actor == "AXIS/Air"
        assert r.state.supply("AF-Sup").stores == 98


def test_38_36_without_the_stores_point_there_is_no_attempt_and_no_die():
    st = _state(unfit={AXIS_STRIKE: 2}, supplies=[_dump(stores=0)])
    r = _Run(st)
    _air_maintenance(r)
    denied = [e for e in r.events if e.kind == EventKind.AIR_REFIT_DENIED]
    assert [e.payload["reason"] for e in denied] == ["no_stores"]
    assert not any(e.rng_draws for e in r.events)      # 38.34's die is never thrown
    assert r.state.air_unfit == {AXIS_STRIKE: 2}       # and the squadron stays as unfit as it was


def test_35_14_an_unfed_sgsu_may_not_repair_its_planes():
    """"SGSUs without the required supplies (for themselves) may not repair their planes" -- the
    gate rule 35.14 sets and engine._sgsu_upkeep counts (stages_without_air_supply)."""
    st = _state(units=[_sgsu(stages_without_air_supply=1)], unfit={AXIS_STRIKE: 2})
    assert air.able_sgsus(st, Side.AXIS) == ()
    r = _Run(st)
    _air_maintenance(r)
    denied = [e for e in r.events if e.kind == EventKind.AIR_REFIT_DENIED]
    assert [e.payload["reason"] for e in denied] == ["no_sgsu"]
    assert r.state.supply("AF-Sup").stores == 99       # 38.36's Point is not spent on a non-attempt
    assert r.state.air_unfit == {AXIS_STRIKE: 2}


def test_35_17_and_36_13_an_sgsu_off_its_field_or_over_capacity_may_not_work():
    """35.17: only an SGSU refits, and it refits AT a base. 36.13/36.14: only within the field's
    CURRENT Capacity Level -- six may stand at a battered field, `level` of them functioning."""
    # (a) an SGSU standing in the desert, not at a facility
    st = _state(units=[_sgsu(hex_=(1, 0))], unfit={AXIS_STRIKE: 2})
    assert air.able_sgsus(st, Side.AXIS) == ()
    # (b) a facility bombed to zero capacity is "destroyed for all purposes" (36.14)
    st = _state(facilities=[_field(level=0)], unfit={AXIS_STRIKE: 2})
    assert air.able_sgsus(st, Side.AXIS) == ()
    # (c) a landing strip works ONE squadron: the second SGSU on it does not function (36.2/36.14)
    st = _state(facilities=[_field(kind=air.STRIP)],
                units=[_sgsu("SGSU-A"), _sgsu("SGSU-B")], unfit={AXIS_STRIKE: 2})
    assert [u.id for u in air.able_sgsus(st, Side.AXIS)] == ["SGSU-A"]


def test_38_33_one_sgsu_refits_at_most_its_charted_ready_plus_reserve():
    """"Each SGSU can refit up to the maximum planes the SGSU can contain (Ready plus Reserve)" --
    [35.23]'s 12 for an Italian Squadriglia. It does not bind at the proxy Air-Point establishments
    the scenarios seed (a squadron here is one or two aeroplanes); it binds the moment 34.6/59.3's
    real Initial Air Strengths land, so it is asserted on a squadron big enough to feel it."""
    st = _state(strike=100, unfit={AXIS_STRIKE: 20})    # 100 Bomb Points = 20 Stukas, all unfit
    r = _Run(st)
    _pin_die(r, 1)                                      # 1 + 2 = 3 -> 70%
    _air_maintenance(r)
    p = [e for e in r.events if e.kind == EventKind.AIR_REFIT_RESOLVED][0].payload
    assert p["undergoing"] == 20 and p["attempting"] == 12          # capped by the chart
    assert p["refitted"] == 9                                       # 70% of 12 = 8.4 -> 9
    assert r.state.air_unfit == {AXIS_STRIKE: 11}


def test_38_23_the_sgsus_allowance_is_shared_across_the_squadrons_it_works():
    """"An Italian SGSU can handle refueling chores for a total of 12 planes, REGARDLESS OF SQUADRON
    ASSIGNMENT, in a given Operations Stage" (38.23), and 38.33 gives refitting the same allowance.
    So it is ONE budget per counter per stage, not a fresh 12 for every squadron it touches: with a
    single Squadriglia on the field, the strike squadron takes all twelve and the recon squadron is
    turned away until another SGSU can work."""
    st = _state(strike=100, recon=30, unfit={AXIS_STRIKE: 20, "AXIS/LAND/recon": 20})
    r = _Run(st)
    _pin_die(r, 1)
    _air_maintenance(r)
    got = [(e.payload["role"], e.payload.get("attempting"), e.payload.get("reason"))
           for e in r.events
           if e.kind in (EventKind.AIR_REFIT_RESOLVED, EventKind.AIR_REFIT_DENIED)]
    assert got == [("recon", None, "sgsu_capacity"), ("strike", 12, None)] \
        or got == [("recon", 12, None), ("strike", None, "sgsu_capacity")]
    # and a second SGSU on a field with room for it works the squadron the first could not
    st2 = _state(strike=100, recon=30, units=[_sgsu("SGSU-A"), _sgsu("SGSU-B")],
                 unfit={AXIS_STRIKE: 20, "AXIS/LAND/recon": 20})
    r2 = _Run(st2)
    _pin_die(r2, 1)
    _air_maintenance(r2)
    resolved = [e for e in r2.events if e.kind == EventKind.AIR_REFIT_RESOLVED]
    assert [e.payload["sgsu_id"] for e in resolved] == ["SGSU-A", "SGSU-B"]
    assert not [e for e in r2.events if e.kind == EventKind.AIR_REFIT_DENIED]


def test_a_squadron_with_nothing_unfit_attempts_nothing():
    """38.31 opens with every plane refitted, and 38.36's Stores Point is owed only by a squadron
    "undergoing an attempted refit". So a stage in which nothing flew emits NOTHING -- which is also
    59.36 ("maintenance may not be performed on planes during the first OpStage of a Scenario") for
    free, and is why every scenario that never flies stays byte-identical."""
    r = _Run(_state())
    _air_maintenance(r)
    assert r.events == []
    assert r.state.supply("AF-Sup").stores == 99


def test_the_beat_is_silent_for_a_side_the_scenario_never_based_on_the_map():
    """The same escape hatch air.based_on_map opens for the 38.24 fuel bill, for the same reason:
    [61.42]'s free Axis field west of El Agheila and [36.5]'s off-map bases are untranscribed, and
    grounding an air force for good because a COUNTER is missing would enshrine a data gap as a
    rule. Both sides ARE based on the map in the full campaign."""
    st = _state(facilities=[], supplies=[], units=[], unfit={AXIS_STRIKE: 2})
    assert not air.refit_modelled(st, Side.AXIS)
    assert _air_points(st, Side.AXIS, "LAND", "strike") == 6        # ungoverned, as before 5.3
    r = _Run(st)
    _air_maintenance(r)
    assert r.events == []


# --- the cycle, end to end ---------------------------------------------------------------------

def test_the_cycle_turns_over_stage_after_stage():
    """Fly, go unfit, refit part of the force, fly what came back. Three OpStages of one squadron,
    with the die pinned, is the governor in miniature."""
    r = _Run(_state(missions=(AirMission(Side.AXIS, "strike", (1, 0), 1),)))
    _pin_die(r, 4)                                      # 4 + 2 Italian = 6 -> 40%
    _air_support(r, Side.AXIS, set())                   # stage 2: both Stukas fly
    assert r.state.air_unfit == {AXIS_STRIKE: 2}
    _air_maintenance(r)                                 # 40% of 2 = 0.8 -> 1 back
    assert r.state.air_unfit == {AXIS_STRIKE: 1}
    strikes = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    _air_support(r, Side.AXIS, set())                   # and the one refitted plane flies alone
    strikes2 = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert strikes[0].payload["strength"] == 6          # the whole squadron
    assert strikes2[-1].payload["strength"] == 5        # one Ju 87B's own Bombload
    assert r.state.air_unfit == {AXIS_STRIKE: 2}
    assert fold(r.initial, r.events) == r.state
    check(r.state)


def test_the_axis_flies_less_than_the_commonwealth_over_the_same_dice():
    """38.35 is a HISTORICALLY LOADED asymmetry and this is it, measured: hand both sides the same
    sequence of dice and the Italian squadron gets fewer aeroplanes back than the Commonwealth one,
    every time, because +2 shifts every roll onto a worse row."""
    undergoing = 12
    axis = [air.refitted_planes(undergoing, d + air.refit_drm("IT")) for d in range(1, 7)]
    cw = [air.refitted_planes(undergoing, d + air.refit_drm("CW")) for d in range(1, 7)]
    assert all(a <= c for a, c in zip(axis, cw)) and sum(axis) < sum(cw)
    assert sum(axis) / len(axis) < sum(cw) / len(cw)


# --- the scenarios -----------------------------------------------------------------------------

def test_the_campaign_refits_and_the_ledger_is_replayable():
    """Over the campaign's opening turns both air forces fly, go unfit and roll on the table; the
    ledger folds from the log alone and the invariants hold."""
    res = run(campaign(seed=4, max_turns=3), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    unfit = [e for e in res.events if e.kind == EventKind.AIR_SQUADRON_UNFIT]
    refits = [e for e in res.events if e.kind == EventKind.AIR_REFIT_RESOLVED]
    assert unfit and refits
    # 38.36: every attempt spent its Stores Point off an air dump, and nothing else did
    air_dumps = {su.id for su in res.initial.supplies if su.air_dump}
    stores = [e for e in res.events if e.kind == EventKind.SUPPLY_CONSUMED
              and e.actor.endswith("/Air") and e.payload["commodity"] == supply.STORES]
    assert len(stores) == len(refits)
    assert {e.payload["supply_id"] for e in stores} <= air_dumps
    # 38.35: the modifier each roll carries is the nationality of the SGSU that did the work, and
    # the campaign's are the charted ones -- [60.32]'s Italian SGSUs in Libya, [60.42]'s
    # Commonwealth in Egypt. So the Axis rolls at +2 all war and the Eighth Army's air force at +0.
    assert {(e.side, e.payload["nationality"], e.payload["drm"]) for e in refits} \
        == {(Side.ALLIED, "CW", 0)}
    # ONLY the Commonwealth refits over these three turns, and that is the schedule rather than a
    # bug -- the same fact test_air_fuel records about the fuel bill. In September 1940 the Axis
    # HOLDS Tobruk, so _air_port refuses its half of the symmetric duel ("never bomb your own
    # harbour"); it flies nothing, so nothing of its goes unfit and nothing needs refitting. It
    # starts paying the game-turn the fortress changes hands, at [60.32]'s Italian SGSUs and +2.
    assert {e.side for e in refits} == {Side.ALLIED}
    assert air.refit_drm("IT") == 2
    assert fold(res.initial, res.events) == res.final
    check(res.final)


def test_the_campaign_is_deterministic_with_the_refit_die_in_the_stream():
    """38.34 draws CONDITIONALLY -- only for a squadron with planes to refit -- which is exactly
    the pattern game.dice exists to isolate. Same seed, byte-identical log."""
    from game.engine import determinism_signature
    runs = [run(campaign(seed=4, max_turns=2), ScriptedPolicy(Side.AXIS),
                ScriptedPolicy(Side.ALLIED)) for _ in range(2)]
    assert determinism_signature(runs[0].events) == determinism_signature(runs[1].events)


def test_an_air_less_scenario_never_touches_the_ledger():
    """rommels_arrival fields no air at all, so not one refit event exists and air_unfit stays
    empty -- the byte-identity the default {} is there to preserve."""
    res = run(rommels_arrival(seed=42), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert res.final.air_unfit == {}
    assert not [e for e in res.events if e.kind in (EventKind.AIR_REFIT_RESOLVED,
                                                    EventKind.AIR_REFIT_DENIED,
                                                    EventKind.AIR_SQUADRON_UNFIT)]


def test_the_siege_axis_is_unbased_so_its_bombers_are_ungoverned():
    """The Desert Fox order of battle carries NO Axis air facility on maps A-C (61.42's free field
    west of El Agheila is untranscribed), so the hatch is open for the Axis there and its harbour
    bombing is unchanged by 5.3. Recorded as a fact about the DATA, not a rule."""
    st = siege_of_tobruk(seed=42, port_bomb=True)
    assert not air.refit_modelled(st, Side.AXIS)
    assert air.refit_modelled(st, Side.ALLIED)          # the RAF strips ARE on the map
    res = run(st, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert not [e for e in res.events if e.kind == EventKind.AIR_SQUADRON_UNFIT
                and e.side == Side.AXIS]
    check(res.final)
