"""[34.17] / [38.21] / [38.24] AIRCRAFT CONSUME FUEL POINTS -- Phase 5.2.

Until this block no Fuel Point had ever left any dump for any aircraft anywhere: the air force
was fed on air. The rules being ported here are three sentences --

  34.17 "the number of Fuel Points a plane requires to perform ANY mission... all Fuel Points are
        consumed during a mission, regardless of the type or distance of the mission"
  38.21 "PLANES MUST HAVE FUEL TO FLY... that is the number of Fuel Points required to enable one
        plane of that type to fly any one mission"
  38.24 "the fuel is SUBTRACTED FROM THE TOTAL SUPPLY IN THE AIR FACILITY"

-- and their consequence: a mission the air-facility dumps cannot fuel is NOT FLOWN (33 IV.F.1
lets only "all planes that are fueled" be assigned missions).
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.air as air
import game.supply as supply
from game.apply import fold
from game.engine import _air_fuel, _air_support, _air_superiority, _Run, run
from game.events import Control, EventKind, Phase, Side
from game.invariants import check
from game.logistics_data import aircraft_characteristics_4_44
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import campaign, rommels_arrival, siege_of_tobruk
from game.state import (AirFacility, AirMission, AirWing, GameState, StepRecord, SupplyUnit,
                        Unit, VP)
from game.terrain import Mobility, Terrain


# --- [4.44A/b/c] the charted ratings ---------------------------------------------------------

def test_the_transcribed_aircraft_rows_are_the_charts():
    """Eyes-verified off the 1979 scan: Commonwealth PDF p.112/113, Axis PDF p.144/145. TacAir is
    34.13, Bomb is 34.14's Bombload Capacity, Fuel is 34.17's Fuel Consumption Rating."""
    ac = aircraft_characteristics_4_44()
    assert ac["Bf. 109E"] | {} and ac["Bf. 109E"]["tacair"] == 6 and ac["Bf. 109E"]["fuel"] == 1
    assert ac["Ju. 87B"]["bombload"] == 5 and ac["Ju. 87B"]["fuel"] == 1
    assert ac["Hurricane Mk. I"]["tacair"] == 4 and ac["Hurricane Mk. I"]["fuel"] == 1
    assert ac["Blenheim Mk. I"]["bombload"] == 5 and ac["Blenheim Mk. I"]["fuel"] == 2
    assert ac["Hs. 126"]["fuel"] == 1 and ac["Lysander Mk. I"]["fuel"] == 1
    # every type an Air Point may be expressed in is transcribed, and carries a usable rating in
    # the column its role is denominated in (a fighter's TacAir, a bomber's Bombload) plus a Fuel
    # Consumption Rating -- the three numbers the conversion needs
    for (side, role), name in air.REPRESENTATIVE_AIRCRAFT.items():
        assert name in ac and ac[name]["fuel"] > 0
        key = air._POINTS_PER_PLANE_RATING.get(role)
        assert key is None or ac[name][key] > 0


def test_air_points_convert_to_aeroplanes_by_the_charted_rating():
    """34.14: strike Air Points ARE Bomb Points (the engine feeds them to the [41.5] columns), so
    a Ju 87B carrying 5 of them is one aeroplane and 6 points need two. 34.13: fighter Air Points
    are TacAir, so 8 of them is two Bf 109Es (rating 6) but two Hurricanes (rating 4)."""
    assert air.planes_flying(Side.AXIS, "strike", 5) == 1
    assert air.planes_flying(Side.AXIS, "strike", 6) == 2        # rounded UP: a part-plane flies
    assert air.planes_flying(Side.AXIS, "fighters", 6) == 1
    assert air.planes_flying(Side.AXIS, "fighters", 8) == 2
    assert air.planes_flying(Side.ALLIED, "fighters", 8) == 2
    assert air.planes_flying(Side.ALLIED, "fighters", 9) == 3
    assert air.planes_flying(Side.ALLIED, "recon", 3) == 3       # flagged: 1 point = 1 recon plane
    assert air.planes_flying(Side.AXIS, "strike", 0) == 0


def test_the_mission_bill_is_planes_times_the_fuel_consumption_rating():
    """38.21: the bill is per plane per mission, and it does not vary with distance (34.17)."""
    assert air.mission_fuel(Side.AXIS, "strike", 6) == 2         # 2 Stukas x Fuel 1
    assert air.mission_fuel(Side.ALLIED, "strike", 6) == 4       # 2 Blenheims x Fuel 2
    assert air.mission_fuel(Side.AXIS, "fighters", 8) == 2       # 2 Bf 109Es x Fuel 1
    assert air.mission_fuel(Side.ALLIED, "recon", 2) == 2
    assert air.mission_fuel(Side.AXIS, "strike", 0) == 0         # no planes, no fuel


# --- fixtures ---------------------------------------------------------------------------------

def _dump(sid="AF-Sup", side=Side.AXIS, hex_=(0, 0), fuel=0, air_dump=True, **kw) -> SupplyUnit:
    base = {"ammo": 0, "stores": 0, "water": 0}
    return SupplyUnit(sid, side, hex_, fuel=fuel, air_dump=air_dump, **{**base, **kw})


def _field(fid="FIELD", side=Side.AXIS, hex_=(0, 0), kind=air.AIRFIELD, level=None) -> AirFacility:
    cap = air.max_capacity(kind)
    return AirFacility(fid, side, hex_, kind=kind, level=cap if level is None else level,
                       max_level=cap)


def _state(*, facilities=(), supplies=(), missions=(), strike=6, fighters=0, recon=0,
           control=None, weather="clear") -> GameState:
    """An Axis LAND wing over an Allied stack at (1,0), based on the facilities passed in."""
    foe = Unit("GAR", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=2, oca=5, dca=8)
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather=weather, vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR},
                           fortifications={}),
        control=control or {}, units=(foe,), target_hex=(1, 0), supplies=tuple(supplies),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES},
        air=(AirWing("LW", Side.AXIS, "LAND", fighters=fighters, strike=strike, recon=recon),),
        air_missions=tuple(missions), air_facilities=tuple(facilities))


def _strike_mission(target=(1, 0)):
    return (AirMission(Side.AXIS, "strike", target, 1),)


# --- [38.24] where the fuel comes from --------------------------------------------------------

def test_38_24_the_fuel_comes_out_of_the_air_facilitys_own_dump():
    st = _state(facilities=[_field()], supplies=[_dump(fuel=9)], missions=_strike_mission())
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    drawn = [e for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]
    assert [(e.payload["supply_id"], e.payload["commodity"], e.payload["qty"]) for e in drawn] \
        == [("AF-Sup", supply.FUEL, 2)]                  # 2 Stukas x Fuel 1
    assert drawn[0].actor == "AXIS/Air"
    assert r.state.supply("AF-Sup").fuel == 7
    assert any(e.kind == EventKind.AIR_STRIKE_RESOLVED for e in r.events)   # and it flew


def test_38_24_an_ordinary_field_dump_may_not_fuel_an_aeroplane():
    """36.17 runs both ways: the airfield's pile is "for supplies to be used by the SGSU's on that
    airfield", and the army's field dump is not in the hex of an air facility at all."""
    st = _state(facilities=[_field()], supplies=[_dump("ARMY", fuel=500, hex_=(1, 0),
                                                       air_dump=False)],
                missions=_strike_mission())
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.SUPPLY_CONSUMED for e in r.events)
    assert [e.kind for e in r.events if e.kind == EventKind.AIR_MISSION_GROUNDED]
    assert r.state.supply("ARMY").fuel == 500


def test_38_24_never_the_enemys_larder_nor_a_field_he_has_taken():
    # (a) the Commonwealth's air dump is not the Luftwaffe's
    st = _state(facilities=[_field(side=Side.ALLIED)],
                supplies=[_dump(side=Side.ALLIED, fuel=99)], missions=_strike_mission())
    assert air.facility_dumps(st, Side.AXIS) == ()
    # (b) 36.15: a facility belongs to whoever holds the hex, so an overrun field feeds nobody
    #     of the side that lost it
    st2 = _state(facilities=[_field()], supplies=[_dump(fuel=99)], missions=_strike_mission(),
                 control={(0, 0): Control.ALLIED})
    assert air.facility_dumps(st2, Side.AXIS) == ()


def test_36_14_a_destroyed_field_launches_nothing():
    """36.14: an airfield reduced to zero capacity "is considered DESTROYED for all purposes"."""
    st = _state(facilities=[_field(level=0)], supplies=[_dump(fuel=99)])
    assert air.facility_dumps(st, Side.AXIS) == ()


def test_the_draw_spreads_over_the_fields_in_id_order_and_is_all_or_nothing():
    st = _state(facilities=[_field("F1", hex_=(0, 0)), _field("F2", hex_=(1, 0))],
                supplies=[_dump("F1-Sup", fuel=1, hex_=(0, 0)),
                          _dump("F2-Sup", fuel=5, hex_=(1, 0))])
    assert air.refuel(st, Side.AXIS, 4) == [("F1-Sup", 1), ("F2-Sup", 3)]
    assert air.refuel(st, Side.AXIS, 6) == [("F1-Sup", 1), ("F2-Sup", 5)]
    assert air.refuel(st, Side.AXIS, 7) is None            # short: nothing is drawn at all
    assert air.refuel(st, Side.AXIS, 0) == []


# --- [38.21] no fuel, no flight ---------------------------------------------------------------

def test_38_21_a_dry_larder_grounds_the_mission_and_the_target_is_untouched():
    st = _state(facilities=[_field()], supplies=[_dump(fuel=1)], missions=_strike_mission())
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    grounded = [e for e in r.events if e.kind == EventKind.AIR_MISSION_GROUNDED]
    assert len(grounded) == 1
    p = grounded[0].payload
    assert p["kind"] == "strike" and p["role"] == "strike"
    assert p["need"] == 2 and p["available"] == 1 and p["points"] == 6
    # nothing flew, nothing was drawn, and the 1 Fuel Point still stands on the field
    assert not any(e.kind == EventKind.AIR_STRIKE_RESOLVED for e in r.events)
    assert not any(e.kind == EventKind.SUPPLY_CONSUMED for e in r.events)
    assert r.state.supply("AF-Sup").fuel == 1


def test_a_grounded_bombing_mission_rolls_no_crt_die():
    """The [41.5] dice are the CONSEQUENCE of a sortie. A sortie that never took off draws none --
    which is also what keeps a grounded air force out of the air_bombard stream."""
    from game.state import Port
    port = Port("PORT-X", Side.ALLIED, (1, 0), kind="major", max_eff=5, eff=4,
                cap_ammo=400, cap_fuel=400, cap_stores=400, cap_water=400, cap_tons=1000)
    st = replace(_state(facilities=[_field()], supplies=[_dump(fuel=0)],
                        missions=(AirMission(Side.AXIS, "port", "PORT-X", 1),)),
                 ports=(port,))
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert not any(e.rng_draws for e in r.events)
    assert r.state.port("PORT-X").eff == 4


def test_a_mission_that_is_never_flown_burns_no_fuel():
    """The resolvers refuse a mission a side cannot legally fly -- here, bombing a harbour its own
    control holds. No aeroplane leaves the ground, so no Fuel Point leaves the larder. (This is why
    the draw is handed to the resolver: the campaign tasks Tobruk from BOTH sides every turn and
    the holder's mission is refused, so charging before the guard billed the garrison for a sortie
    it never flew.)"""
    from game.state import Port
    port = Port("PORT-A", Side.AXIS, (1, 0), kind="major", max_eff=5, eff=4,
                cap_ammo=400, cap_fuel=400, cap_stores=400, cap_water=400, cap_tons=1000)
    st = replace(_state(facilities=[_field()], supplies=[_dump(fuel=9)],
                        missions=(AirMission(Side.AXIS, "port", "PORT-A", 1),)),
                 ports=(port,))
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert not r.events                                  # nothing flew, nothing was billed
    assert r.state.supply("AF-Sup").fuel == 9


def test_zero_committed_points_cost_nothing_and_emit_nothing():
    """A side that fields no strike -- or has lost the sky to a scale of 0 -- puts no plane in the
    air, so there is no bill, no draw and no grounding event. This is what keeps every air-less
    scenario byte-identical."""
    st = _state(facilities=[_field()], supplies=[_dump(fuel=0)], strike=0,
                missions=_strike_mission())
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind in (EventKind.SUPPLY_CONSUMED, EventKind.AIR_MISSION_GROUNDED)
                   for e in r.events)


def test_the_marker_folds_to_identity():
    st = _state(facilities=[_field()], supplies=[_dump(fuel=0)], missions=_strike_mission())
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert fold(st, r.events) == r.state


# --- [40.21] the Combat Air Patrol is a mission too --------------------------------------------

def _cap_run(fuel: int, fighters: int = 8) -> _Run:
    st = _state(facilities=[_field()], supplies=[_dump(fuel=fuel)], strike=0, fighters=fighters)
    st = replace(st, air=st.air + (AirWing("DAF", Side.ALLIED, "LAND", fighters=4, strike=0,
                                           recon=0),))
    r = _Run(st)
    _air_superiority(r)
    return r


def test_40_21_a_cap_burns_fuel_like_any_other_mission():
    r = _cap_run(fuel=9)
    drawn = [e for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]
    assert len(drawn) == 1 and drawn[0].payload["qty"] == 2      # 2 Bf 109Es x Fuel 1
    sup = [e for e in r.events if e.kind == EventKind.AIR_SUPERIORITY_RESOLVED]
    assert sup[0].payload["axis_fighters"] == 8                  # the full force contested


def test_a_side_that_cannot_fuel_its_fighters_concedes_the_sky():
    """"Planes must have fuel to fly" (38.21). It commits nothing to the contest -- but the dice
    are still thrown, so the contest resolves exactly as it always did, against a force of zero."""
    r = _cap_run(fuel=0)
    sup = [e for e in r.events if e.kind == EventKind.AIR_SUPERIORITY_RESOLVED]
    assert len(sup) == 1 and sup[0].payload["axis_fighters"] == 0
    assert len(sup[0].rng_draws) == 2                            # both dice still drawn
    assert [e.payload["kind"] for e in r.events
            if e.kind == EventKind.AIR_MISSION_GROUNDED] == ["cap"]
    # the Commonwealth (unbased in this fixture -- see based_on_map) flies and takes the sky
    assert r.state.air_superiority["LAND"] == Side.ALLIED.value


# --- the ONE escape hatch, and it is a data gap, not a rule -----------------------------------

def test_a_side_the_scenario_never_based_on_the_map_is_outside_the_model():
    """36.5's off-map facilities and (in the Desert Fox benchmarks) 61.42's free Axis airfield are
    untranscribed, so a side with no facility on the map has no 38.24 hex for its fuel to be in.
    Grounding it would enshrine a missing COUNTER as a rule. Flagged in air.based_on_map."""
    st = _state(missions=_strike_mission())                      # no facilities at all
    assert not air.based_on_map(st, Side.AXIS)
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert any(e.kind == EventKind.AIR_STRIKE_RESOLVED for e in r.events)
    assert not any(e.kind == EventKind.AIR_MISSION_GROUNDED for e in r.events)


def test_a_side_that_LOSES_its_last_field_is_grounded_not_freed():
    """The hatch reads the SEEDED owner, never current holdings -- so an air force whose fields
    are all overrun is grounded (its fuel went with them), which is the opposite of free."""
    st = _state(facilities=[_field()], supplies=[_dump(fuel=99)], missions=_strike_mission(),
                control={(0, 0): Control.ALLIED})
    assert air.based_on_map(st, Side.AXIS)                       # seeded Axis, currently lost
    r = _Run(st)
    _air_support(r, Side.AXIS, set())
    assert [e.payload["kind"] for e in r.events
            if e.kind == EventKind.AIR_MISSION_GROUNDED] == ["strike"]


def test_air_fuel_helper_reports_the_two_outcomes():
    st = _state(facilities=[_field()], supplies=[_dump(fuel=2)])
    r = _Run(st)
    assert _air_fuel(r, Side.AXIS, "strike", 6, {"arena": "LAND", "kind": "strike"}) is True
    assert r.state.supply("AF-Sup").fuel == 0
    assert _air_fuel(r, Side.AXIS, "strike", 6, {"arena": "LAND", "kind": "strike"}) is False


# --- integration ------------------------------------------------------------------------------

def test_the_air_less_benchmarks_are_untouched():
    """Neither benchmark fields an AirWing, so no plane is fuelled and no log moves."""
    for scen in (rommels_arrival(seed=1941), siege_of_tobruk(seed=3)):
        res = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert not any(e.kind == EventKind.AIR_MISSION_GROUNDED for e in res.events)
        assert not any(e.actor.endswith("/Air") and e.kind == EventKind.SUPPLY_CONSUMED
                       for e in res.events)


def test_the_fuelled_campaign_replays_byte_for_byte():
    """Determinism binds absolutely: the draw is a pure dictionary walk over id-ordered dumps and
    rolls no die, so the log of a campaign whose air force eats is byte-identical run to run."""
    from game.engine import determinism_signature
    runs = [run(campaign(seed=4, max_turns=2), ScriptedPolicy(Side.AXIS),
                ScriptedPolicy(Side.ALLIED)) for _ in range(2)]
    assert determinism_signature(runs[0].events) == determinism_signature(runs[1].events)


def test_the_campaign_air_force_now_eats_and_the_ledger_holds():
    """The end of "the Axis air force is fed on air": over the campaign's opening turns, Fuel
    Points leave the 36.17 air-facility dumps for the aeroplanes -- and the conservation identity
    (on_hand + consumed == initial) still holds, because the draw rides the ordinary
    SUPPLY_CONSUMED."""
    res = run(campaign(seed=4, max_turns=2), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    air_fuel = [e for e in res.events
                if e.kind == EventKind.SUPPLY_CONSUMED and e.actor.endswith("/Air")]
    assert air_fuel and all(e.payload["commodity"] == supply.FUEL for e in air_fuel)
    assert {e.side for e in air_fuel} == {Side.AXIS, Side.ALLIED}      # both air forces pay
    check(res.final)
    assert fold(res.initial, res.events) == res.final
