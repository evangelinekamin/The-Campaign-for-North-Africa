"""Abstract air -- the P5 "fidelity where the camera is" layer (rules 33-46 at the 32.0/58.0
grain). Step 3 is the SPINE: the AirWing force pool, the two-arena air-superiority gate (LAND +
SEA, forced apart by 41.63), the weather grounding (29.43/29.52), and the byte-identical default
(air=() draws no dice, fires no beat). Real EFFECTS via per-side Air Point scalars, NO per-plane
bookkeeping; the magnitudes are FLAGGED PROXY (the 34.6/59.3 chart is untranscribed)."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.engine as engine
from game.apply import apply, fold
from game.engine import (_air_arena_fighters, _air_grounded, _air_points, _air_support,
                         _air_superiority, _Run, determinism_signature, run)
from game.events import Event, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap
from game.observation import SIGHTING, observe
from game.policy import ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival, siege_of_tobruk
from game.state import AirMission, AirWing, GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


def _mini(air=(), *, weather="clear", turn=1, stage=1) -> GameState:
    """A unit-/dump-free state to exercise the air beat in isolation."""
    return GameState(
        turn=turn, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=1, weather=weather, vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0),
        supplies=(), consumed={}, initial_supply={},
        air=tuple(air), stage=stage)


# --- the state fields --------------------------------------------------------

def test_air_defaults_empty():
    assert GameState.__dataclass_fields__["air"].default == ()
    assert GameState.__dataclass_fields__["air_superiority"].default_factory() == {}
    for s in (coastal_corridor(), rommels_arrival(), siege_of_tobruk()):
        assert s.air == () and s.air_superiority == {}


# --- the gate fold + OpStage clearing ----------------------------------------

def test_superiority_folds_victor():
    s = _mini()
    e = Event(0, 1, Phase.LOGISTICS, Side.SYSTEM, "SYSTEM", EventKind.AIR_SUPERIORITY_RESOLVED,
              {"arena": "LAND", "axis_fighters": 8, "allied_fighters": 3,
               "victor": Side.AXIS.value, "margin": 5}, rng_draws=(4, 2))
    s2 = apply(s, e)
    assert s2.air_superiority == {"LAND": Side.AXIS.value}
    assert s2.air_superiority_of("LAND") == Side.AXIS.value
    assert s2.air_superiority_of("SEA") is None


def test_superiority_tie_folds_none():
    s = _mini().with_air_superiority("SEA", None)
    assert s.air_superiority == {"SEA": None}
    assert s.air_superiority_of("SEA") is None


def test_superiority_cleared_at_opstage_boundary():
    s = _mini(stage=1).with_air_superiority("LAND", Side.AXIS.value)
    stage_adv = Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", EventKind.STAGE_ADVANCED,
                      {"stage": 2})
    assert apply(s, stage_adv).air_superiority == {}
    turn_adv = Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM", EventKind.TURN_ADVANCED,
                     {"turn": 2})
    assert apply(s, turn_adv).air_superiority == {}


# --- the SYSTEM air-superiority beat -----------------------------------------

def _wings():
    return (AirWing("LW-land", Side.AXIS, "LAND", fighters=9, strike=6, recon=2),
            AirWing("DAF-land", Side.ALLIED, "LAND", fighters=3, strike=4, recon=3),
            AirWing("RA-sea", Side.AXIS, "SEA", fighters=2, strike=5, recon=1),
            AirWing("FAA-sea", Side.ALLIED, "SEA", fighters=7, strike=3, recon=4))


def test_arena_fighters_partition():
    s = _mini(_wings())
    assert _air_arena_fighters(s, "LAND") == (9, 3)
    assert _air_arena_fighters(s, "SEA") == (2, 7)


def test_beat_resolves_each_arena_and_folds():
    r = _Run(_mini(_wings()))
    _air_superiority(r)
    res = [e for e in r.events if e.kind == EventKind.AIR_SUPERIORITY_RESOLVED]
    assert {e.payload["arena"] for e in res} == {"LAND", "SEA"}
    for e in res:                                        # every roll records its two dice
        assert len(e.rng_draws) == 2
        margin = abs((e.payload["axis_fighters"] + e.rng_draws[0])
                     - (e.payload["allied_fighters"] + e.rng_draws[1]))
        assert e.payload["margin"] == margin
    # the folded gate matches the emitted victors
    assert r.state.air_superiority == {e.payload["arena"]: e.payload["victor"] for e in res}
    check(r.state)


def test_beat_is_grounded_by_foul_weather():
    for foul in ("sandstorm", "rainstorm"):
        assert _air_grounded(foul)
        r = _Run(_mini(_wings(), weather=foul))
        _air_superiority(r)
        assert not r.events                              # no beat, no dice, no phase
        assert r.state.air_superiority == {}
    assert not _air_grounded("clear") and not _air_grounded("hot")


def test_beat_noop_without_air():
    r = _Run(_mini(()))                                  # air=() -> byte-identical
    _air_superiority(r)
    assert not r.events


# --- byte-identity of the live scenarios (air=() everywhere) -----------------

def test_rommels_arrival_byte_identical_and_air_silent():
    a = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert not any(e.kind == EventKind.AIR_SUPERIORITY_RESOLVED for e in a.events)
    assert a.final.air_superiority == {}


def test_seeded_air_run_is_deterministic_and_fires():
    base = rommels_arrival(seed=7)
    scen = replace(base, air=(AirWing("LW", Side.AXIS, "LAND", 8, 6, 2),
                              AirWing("DAF", Side.ALLIED, "LAND", 4, 3, 3)))
    a = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    sup = [e for e in a.events if e.kind == EventKind.AIR_SUPERIORITY_RESOLVED]
    assert sup and all(e.payload["arena"] == "LAND" for e in sup)
    # live state equals the fold of its own log (the replay identity)
    assert fold(a.initial, a.events).air_superiority == a.final.air_superiority


# =============================================================================
# Step 4 -- MISSIONS: strike / fort / port bombing, air-sourced interdiction, recon
# =============================================================================

def _air_missions_default_empty():
    return None


def test_air_mission_state_defaults_empty():
    assert GameState.__dataclass_fields__["air_missions"].default == ()
    assert GameState.__dataclass_fields__["air_sighted"].default == frozenset()
    for s in (coastal_corridor(), rommels_arrival(), siege_of_tobruk()):
        assert s.air_missions == () and s.air_sighted == frozenset()


def _strike_state(*, fort: int = 0, air_strike: int = 6, siege: bool = False,
                  weather: str = "clear", superiority=None, missions=(), ports=()) -> GameState:
    """An Axis LAND air wing over an Allied stack at (1,0); (1,0) may be a fortified Major City."""
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.MAJOR_CITY if fort else Terrain.CLEAR}
    foe = Unit("GAR", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=2, oca=5, dca=8)
    wing = AirWing("LW", Side.AXIS, "LAND", fighters=9, strike=air_strike, recon=3)
    s = GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather=weather, vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={(1, 0): fort} if fort else {}),
        control={}, units=(foe,), target_hex=(1, 0), supplies=(), consumed={}, initial_supply={},
        siege_rules=siege, air=(wing,), air_missions=tuple(missions), ports=tuple(ports))
    if superiority is not None:
        s = s.with_air_superiority("LAND", superiority)
    return s


def _strike(target=(1, 0)):
    return (AirMission(Side.AXIS, "strike", target, 1),)


# --- STRIKE (41.31): pin joins the barrage set, identity fold ----------------

def test_strike_flies_nothing_without_a_mission():
    r = _Run(_strike_state())
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.AIR_STRIKE_RESOLVED for e in r.events)


def test_strike_pins_the_target_and_folds_identity():
    r = _Run(_strike_state(missions=_strike()))
    pinned: set = set()
    _air_support(r, Side.AXIS, pinned)
    strike = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert len(strike) == 1
    p = strike[0].payload
    assert p["arena"] == "LAND" and p["pinned"] == ["GAR"] and p["walled"] is False
    assert "GAR" in pinned                               # 12.44: joined the pin set
    # AIR_STRIKE_RESOLVED folds to identity (a marker); only the transient pin carries state
    e = Event(0, 1, Phase.COMBAT, Side.AXIS, "AXIS/Air", EventKind.AIR_STRIKE_RESOLVED, dict(p))
    assert apply(r.state, e) is r.state


def test_strike_blocked_behind_intact_major_city_wall():
    # 41.31: a garrison behind fort_level>1 is UN-STRIKABLE -- air alone cannot crack Tobruk.
    r = _Run(_strike_state(fort=2, missions=_strike()))
    pinned: set = set()
    _air_support(r, Side.AXIS, pinned)
    p = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED][0].payload
    assert p["walled"] is True and p["pinned"] == [] and not pinned


def test_strike_severity_default_is_pin_only():
    assert engine.AIR_STRIKE_STEP_SEVERITY == 0
    r = _Run(_strike_state(missions=_strike()))
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.STEP_LOST for e in r.events)   # pin-only


def test_strike_severity_dial_sheds_a_step():
    r = _Run(_strike_state(missions=_strike()))
    old = engine.AIR_STRIKE_STEP_SEVERITY
    try:
        engine.AIR_STRIKE_STEP_SEVERITY = 2
        _air_support(r, Side.AXIS, set())
    finally:
        engine.AIR_STRIKE_STEP_SEVERITY = old
    loss = [e for e in r.events if e.kind == EventKind.STEP_LOST]
    assert len(loss) == 1 and loss[0].payload["role"] == "air_strike"
    assert loss[0].payload["amount"] == 2 and r.state.unit("GAR").strength == 4


# --- FORT bombing (41.37): reuse FORT_REDUCED, capped, gated by siege --------

def test_fort_bombing_reduces_one_level_only_under_siege():
    fort_mission = (AirMission(Side.AXIS, "fort", (1, 0), 1),)
    r = _Run(_strike_state(fort=3, siege=True, missions=fort_mission))
    _air_support(r, Side.AXIS, set())
    fr = [e for e in r.events if e.kind == EventKind.FORT_REDUCED]
    assert len(fr) == 1 and fr[0].payload["level"] == 2          # one level/OpStage (41.37)
    assert r.state.fort_level((1, 0)) == 2
    # siege OFF -> no fort bombing (inert like _batter_fort)
    r2 = _Run(_strike_state(fort=3, siege=False, missions=fort_mission))
    _air_support(r2, Side.AXIS, set())
    assert not any(e.kind == EventKind.FORT_REDUCED for e in r2.events)


def test_fort_bombing_never_batters_your_own_works():
    # A mis-seeded mission over a FRIENDLY-controlled fort must not batter it (ownership guard).
    from game.events import Control
    fort_mission = (AirMission(Side.AXIS, "fort", (1, 0), 1),)
    s = replace(_strike_state(fort=3, siege=True, missions=fort_mission),
                control={(1, 0): Control.AXIS})
    r = _Run(s)
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.FORT_REDUCED for e in r.events)
    assert r.state.fort_level((1, 0)) == 3


# --- PORT bombing (41.39B): reuse PORT_EFFICIENCY_CHANGED --------------------

def test_port_bombing_rolls_the_41_5_ports_row():
    # 41.39B / 41.5: harbour bombing ROLLS on the [41.5] Ports row (T0-10) -- no more flat -1. The
    # committed strike Air Points pick the Bomb-Point column, and 2d6 read sequentially (41.22) give
    # the Efficiency Levels lost. This replaces the old test that pinned a flat -1 with no die.
    from game.state import Port
    from game.engine import _bombardment_result
    # (a) the pure lookup, transcribed and eyes-verified from PDF p107: at 6 bomb points (column
    # 1..20) it is 0 on codes 11..62 and 1 on 63..66; a big raid (column 471+) always hurts.
    # RENAMED from _port_bomb_levels: the [41.5] block is shared by Airfields / Air Landing Strips /
    # Ports and the Key (PDF p.108) gives the three of them three different meanings, so the lookup
    # returns the table's RESULT and only the Ports row reads it as Efficiency Levels.
    assert _bombardment_result(6, 1, 1) == 0                     # code 11 -> 0
    assert _bombardment_result(6, 6, 2) == 0                     # code 62 -> 0
    assert _bombardment_result(6, 6, 3) == 1                     # code 63 -> 1
    assert _bombardment_result(500, 1, 1) == 1 and _bombardment_result(500, 6, 6) == 4
    assert _bombardment_result(0, 6, 6) == 0                     # below the table floor: nothing
    # (b) integration: _air_port draws two air_bombard dice, certifies them on an AIR_STRIKE_RESOLVED
    # marker, and drops the port's Efficiency by exactly the [41.5] result -- a 0 emits NO change.
    port = Port("PORT-X", Side.ALLIED, (2, 0), kind="major", max_eff=5, eff=4,
                cap_ammo=400, cap_fuel=400, cap_stores=400, cap_water=400, cap_tons=1000)
    r = _Run(_strike_state(ports=(port,),
                           missions=(AirMission(Side.AXIS, "port", "PORT-X", 1),)))
    _air_support(r, Side.AXIS, set())
    marker = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED
              and e.payload.get("arena") == "PORT"]
    assert len(marker) == 1                                      # the roll is always logged
    d1, d2 = marker[0].rng_draws
    levels = _bombardment_result(marker[0].payload["strength"], d1, d2)
    assert marker[0].payload["levels"] == levels
    pe = [e for e in r.events if e.kind == EventKind.PORT_EFFICIENCY_CHANGED]
    if levels > 0:
        assert len(pe) == 1 and pe[0].payload["level"] == 4 - levels
        assert r.state.port("PORT-X").eff == 4 - levels
    else:                                                        # No Effect: no change, free to regen (55.18)
        assert not pe and r.state.port("PORT-X").eff == 4


def test_port_bombing_never_bombs_your_own_harbour():
    # A mis-seeded mission over a FRIENDLY (Axis) port must not knock it down (ownership guard).
    from game.state import Port
    port = Port("PORT-A", Side.AXIS, (2, 0), kind="major", max_eff=5, eff=4,
                cap_ammo=400, cap_fuel=400, cap_stores=400, cap_water=400, cap_tons=1000)
    r = _Run(_strike_state(ports=(port,),
                           missions=(AirMission(Side.AXIS, "port", "PORT-A", 1),)))
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.PORT_EFFICIENCY_CHANGED for e in r.events)
    assert r.state.port("PORT-A").eff == 4


# --- the air-superiority GATE on fort/port bombing (mirror _air_strike) ------

def test_fort_and_port_bombing_need_committed_strike_points():
    from game.state import Port
    port = Port("PORT-X", Side.ALLIED, (2, 0), kind="major", max_eff=5, eff=4,
                cap_ammo=400, cap_fuel=400, cap_stores=400, cap_water=400, cap_tons=1000)
    # A strike=0 wing fields no strike Air Points -> neither the works nor the harbour is battered.
    fort_mission = (AirMission(Side.AXIS, "fort", (1, 0), 1),)
    r = _Run(_strike_state(fort=3, siege=True, air_strike=0, missions=fort_mission))
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.FORT_REDUCED for e in r.events)
    assert r.state.fort_level((1, 0)) == 3
    r2 = _Run(_strike_state(air_strike=0, ports=(port,),
                            missions=(AirMission(Side.AXIS, "port", "PORT-X", 1),)))
    _air_support(r2, Side.AXIS, set())
    assert not any(e.kind == EventKind.PORT_EFFICIENCY_CHANGED for e in r2.events)
    assert r2.state.port("PORT-X").eff == 4


def test_losing_the_land_sky_below_a_point_grounds_fort_and_port_bombing():
    # strike=1 scaled by the LOSER factor (0.5) floors to int(0) -> the sky-lost side cannot batter.
    from game.state import Port
    port = Port("PORT-X", Side.ALLIED, (2, 0), kind="major", max_eff=5, eff=4,
                cap_ammo=400, cap_fuel=400, cap_stores=400, cap_water=400, cap_tons=1000)
    fort_mission = (AirMission(Side.AXIS, "fort", (1, 0), 1),)
    r = _Run(_strike_state(fort=3, siege=True, air_strike=1,
                           superiority=Side.ALLIED.value, missions=fort_mission))
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.FORT_REDUCED for e in r.events)
    r2 = _Run(_strike_state(air_strike=1, superiority=Side.ALLIED.value, ports=(port,),
                            missions=(AirMission(Side.AXIS, "port", "PORT-X", 1),)))
    _air_support(r2, Side.AXIS, set())
    assert not any(e.kind == EventKind.PORT_EFFICIENCY_CHANGED for e in r2.events)


def test_fort_and_port_bombing_carry_committed_strength():
    # winning/contested sky -> the committed strike points ride the payload for legibility.
    # A 6-point Axis bomber establishment is TWO Ju. 87B, of which rule 43.12 bases three quarters
    # (one, floored) in Italy/Sicily: the one aeroplane left in Africa carries its Bombload of 5.
    from game.state import Port
    port = Port("PORT-X", Side.ALLIED, (2, 0), kind="major", max_eff=5, eff=4,
                cap_ammo=400, cap_fuel=400, cap_stores=400, cap_water=400, cap_tons=1000)
    r = _Run(_strike_state(fort=3, siege=True, air_strike=6,
                           missions=(AirMission(Side.AXIS, "fort", (1, 0), 1),)))
    _air_support(r, Side.AXIS, set())
    fr = [e for e in r.events if e.kind == EventKind.FORT_REDUCED]
    assert len(fr) == 1 and fr[0].payload["strength"] == 5
    r2 = _Run(_strike_state(air_strike=6, ports=(port,),
                            missions=(AirMission(Side.AXIS, "port", "PORT-X", 1),)))
    _air_support(r2, Side.AXIS, set())
    marker = [e for e in r2.events if e.kind == EventKind.AIR_STRIKE_RESOLVED
              and e.payload.get("arena") == "PORT"]
    assert len(marker) == 1 and marker[0].payload["strength"] == 5   # committed strike rides the marker
    for pe in r2.events:                                             # and any efficiency drop carries it too
        if pe.kind == EventKind.PORT_EFFICIENCY_CHANGED:
            assert pe.payload["strength"] == 5


# --- superiority scaling (the Step-3 gate read at mission time) --------------

def test_air_points_scale_the_loser():
    """The superiority scale is taken on the AFRICAN contingent, not on the establishment: rule 43
    bases three quarters of an 8-point Axis bomber pool (2 Ju. 87B) in Italy/Sicily, so 5 Bomb
    Points are over the desert to be contested, and losing the sky halves THOSE. Scaling first and
    basing second would have made the whole air-superiority contest invisible for the Axis -- a
    loser-scale of 0.5 on top of a cap at 0.25 changes nothing (engine._air_points)."""
    s = _strike_state(air_strike=8, superiority=Side.ALLIED.value)   # Axis LOST the LAND sky
    assert _air_points(s, Side.AXIS, "LAND", "strike") == 2          # halved, from 5
    assert _air_points(s, Side.ALLIED, "LAND", "strike") == 0        # no Allied wing here
    s2 = _strike_state(air_strike=8, superiority=Side.AXIS.value)    # Axis WON
    assert _air_points(s2, Side.AXIS, "LAND", "strike") == 5         # the African contingent, whole
    s3 = _strike_state(air_strike=8, superiority=None)               # contested
    assert _air_points(s3, Side.AXIS, "LAND", "strike") == 5


# --- RECON (42.2): folds air_sighted, forbidden over a Major City ------------

def test_recon_lifts_fog_and_folds_air_sighted():
    r = _Run(_strike_state(missions=(AirMission(Side.AXIS, "recon", (1, 0), 1),)))
    _air_support(r, Side.AXIS, set())
    rec = [e for e in r.events if e.kind == EventKind.AIR_RECON_RESOLVED]
    assert len(rec) == 1
    p = rec[0].payload
    assert p["hex"] == [1, 0] and p["revealed"][0]["class"] == "infantry"
    assert abs(p["revealed"][0]["toe"] - 6) <= 2                # 42.24 TOE +-2
    assert (Side.AXIS.value, (1, 0)) in r.state.air_sighted
    assert r.state.air_sighted_for(Side.AXIS) == frozenset({(1, 0)})
    assert r.state.air_sighted_for(Side.ALLIED) == frozenset()  # scoped to the flying side


def test_recon_forbidden_over_major_city():
    # a fortified Major City (fort_level>1) may not be recon'd (42.22)
    r = _Run(_strike_state(fort=2, missions=(AirMission(Side.AXIS, "recon", (1, 0), 1),)))
    _air_support(r, Side.AXIS, set())
    assert not any(e.kind == EventKind.AIR_RECON_RESOLVED for e in r.events)  # 42.22
    assert r.state.air_sighted == frozenset()


def test_observation_reads_the_recon_fog_lift():
    # a far enemy hex beyond SIGHTING is invisible -- until recon lifts it.
    far = (SIGHTING + 5, 0)
    terr = {(0, 0): Terrain.CLEAR, far: Terrain.CLEAR}
    me = Unit("ME", Side.AXIS, (0, 0), (StepRecord("a", 4),), mobility=Mobility.FOOT,
              cpa=10, stacking_points=1, oca=3, dca=3)
    foe = Unit("FOE", Side.ALLIED, far, (StepRecord("b", 5),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=1, oca=3, dca=3)
    s = GameState(turn=1, max_turns=4, phase=Phase.MOVEMENT, active_side=Side.AXIS, seed=3,
                  weather="clear", vp=VP(),
                  terrain=TerrainMap(terrain=terr, fortifications={}),
                  control={}, units=(me, foe), target_hex=far, supplies=(), consumed={},
                  initial_supply={})
    assert not observe(s, Side.AXIS)["enemy_sightings"]         # beyond SIGHTING, fogged
    s2 = s.with_air_sighted(Side.AXIS.value, far)               # recon lifts it
    sightings = observe(s2, Side.AXIS)["enemy_sightings"]
    assert len(sightings) == 1 and sightings[0]["hex"] == list(far)


# --- air-sourced convoy interdiction (SEA) ----------------------------------

def test_interdiction_routes_through_a_sea_air_strike_only_with_sea_air():
    from game.state import Convoy, InterdictionOrder
    dump = SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0)
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 1000, "FUEL": 1000})
    order = InterdictionOrder("SEA-TOBRUK", 1, 500)
    base = dict(turn=1, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM, seed=1,
                weather="clear", vp=VP(),
                terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
                control={}, units=(), target_hex=(0, 0), supplies=(dump,),
                consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 0, "FUEL": 0},
                convoys=(conv,), interdictions=(order,))
    # no SEA air -> the interdiction fires but NO air-strike marker (byte-identical to Step 1-2)
    from game.engine import _naval_convoys
    r = _Run(GameState(**base))
    _naval_convoys(r)
    assert any(e.kind == EventKind.CONVOY_INTERDICTED for e in r.events)
    assert not any(e.kind == EventKind.AIR_STRIKE_RESOLVED for e in r.events)
    # with an Axis SEA wing (the interdictor of a CW ferry), the cut is air-sourced
    r2 = _Run(GameState(**{**base, "air": (AirWing("RA", Side.AXIS, "SEA", 3, 5, 1),)}))
    _naval_convoys(r2)
    sea = [e for e in r2.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]
    assert len(sea) == 1 and sea[0].payload["arena"] == "SEA"
    assert sea[0].payload["target"] == "SEA-TOBRUK" and sea[0].payload["strength"] == 500


# --- grounding + byte-identity ----------------------------------------------

def test_air_support_grounded_flies_nothing():
    for foul in ("sandstorm", "rainstorm"):
        r = _Run(_strike_state(weather=foul, missions=_strike()))
        _air_support(r, Side.AXIS, set())
        assert not r.events                             # 29.43/29.52 grounded


def test_seeded_air_missions_run_deterministic_and_scenarios_byte_identical():
    from game import coords
    tob = coords.to_axial(coords.parse("C4807"))
    base = siege_of_tobruk(seed=5)
    wings = (AirWing("LW", Side.AXIS, "LAND", 8, 6, 3), AirWing("RA", Side.AXIS, "SEA", 4, 5, 1))
    missions = tuple(AirMission(Side.AXIS, k, (tob if k != "port" else "PORT-Tobruk"), t)
                     for t in range(1, base.max_turns + 1)
                     for k in ("fort", "port", "recon", "strike"))
    scen = replace(base, air=wings, air_missions=missions)
    a = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(scen, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert fold(a.initial, a.events).air_sighted == a.final.air_sighted
    kinds = {e.kind for e in a.events}
    assert EventKind.AIR_STRIKE_RESOLVED in kinds and EventKind.AIR_RECON_RESOLVED in kinds
    check(a.final)
    # the air-less scenarios stay byte-identical (siege carries interdictions but air=())
    for scen0 in (rommels_arrival(seed=1941), siege_of_tobruk(seed=3)):
        x = run(scen0, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert not any(e.kind in (EventKind.AIR_STRIKE_RESOLVED, EventKind.AIR_RECON_RESOLVED)
                       for e in x.events)
