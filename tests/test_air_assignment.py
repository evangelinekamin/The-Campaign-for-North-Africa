"""[39.1] MISSION ASSIGNMENT -- the Air Marshal's seat, the within-stage plane ledger, and the
order-rejection boundary the seat's orders now cross.

Three rules are ported here, all re-rendered off the 1979 scan for this block (pdftoppm -r 300,
PDF pages 55 and 56 = printed folios 8 and 9):

  39.11 "Unless a plane is attempting emergency flight (see Case 37.3), no plane may fly unless it
        has been ASSIGNED A SPECIFIC MISSION. Nor may any plane be flown if an Enemy land combat
        unit is adjacent (see 37.3)."
  39.19 "Generally, a plane may fly only ONE MISSION PER OPERATIONS STAGE OR STRATEGIC PHASE (with
        the exception of certain fighters and dive bombers; Case 39.2). A plane flying a mission in
        an Operations Stage may not fly in the Strategic Phase of that Game-Turn and vice versa."
  39.2  "Planes can generally fly only one mission PER FLIGHT. However, certain fighter aircraft had
        the ability to carry small bombloads, dropping them as they strafed a target... Thus, any
        plane with a capability notation of D("dual") may strafe and bomb THE SAME TARGET as a
        combined mission."

WHAT THIS FILE IS FOR. Before this block the LAND air missions were a FIXED SCHEDULE baked into
game.scenario, read straight off GameState by the engine, and narrated -- but not decided -- by the
staff's Air Marshal seat. No Policy method was consulted, so "which missions fly" was the purest
case in the engine of a decision automated away from the commander who should be making it. The
hook (Policy.air_missions) hands it back; 39.19's within-stage half is the bound that makes handing
it back safe, and 39.11 is the boundary that refuses an order the engine cannot fly.

39.19's OTHER half -- Operations Stage versus Strategic Phase -- was already built, in
game.basing.strategic_planes, and this file pins that the two halves compose rather than replace
each other (they run on different clocks: the Strategic half on the Game-Turn, this one on the
Operations Stage; 40.0 lets a plane fly "three in one Game-Turn").
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.air as air
import game.supply as supply
from game.campaign_policy import CampaignAxisPolicy, air_mission_doctrine
from game.engine import _AIR_MISSIONS, _air_points, _air_support, _Run
from game.events import EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import Policy, ScriptedPolicy
from game.scenario import rommels_arrival, siege_of_tobruk
from game.state import (AirFacility, AirMission, AirWing, GameState, StepRecord, SupplyUnit,
                        Unit, VP)
from game.terrain import Mobility, Terrain

AXIS_STRIKE = "AXIS/LAND/strike"


# --- fixtures -----------------------------------------------------------------------------------

def _dump(sid="AF-Sup", side=Side.AXIS, hex_=(0, 0), fuel=999, stores=999) -> SupplyUnit:
    return SupplyUnit(sid, side, hex_, fuel=fuel, stores=stores, ammo=0, water=0, air_dump=True)


def _field(fid="FIELD", side=Side.AXIS, hex_=(0, 0)) -> AirFacility:
    cap = air.max_capacity(air.AIRFIELD)
    return AirFacility(fid, side, hex_, kind=air.AIRFIELD, level=cap, max_level=cap)


def _state(*, missions=(), strike=23, recon=0, based=True, turn=1, stage=2,
           unfit=None, strategic=None) -> GameState:
    """An Axis LAND strike wing of TWO aeroplanes (23 Bomb Points; [60.32]'s bombers average 11
    Bombload apiece -- game.roster), over an Allied stack at (1,0), with a fed air dump at (0,0).

    `based=False` removes the Axis air FACILITY and nothing else. That is the [36.5]/[61.42] data
    escape hatch (air.based_on_map): a side the scenario never based on the map is outside rule
    38's refit model AND outside rule 38.24's fuel model, so its missions fly free and unrefitted.
    It is the configuration this file exists for -- it is where 39.19 is the ONLY bound left.
    """
    foe = Unit("GAR", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=2, oca=5, dca=8)
    supplies = (_dump(),)
    return GameState(
        turn=turn, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR},
                           fortifications={}),
        control={}, units=(foe,), target_hex=(1, 0),
        supplies=supplies,
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: sum(getattr(su, c.lower()) for su in supplies)
                        for c in supply.COMMODITIES},
        air=(AirWing("LW", Side.AXIS, "LAND", fighters=0, strike=strike, recon=recon),),
        air_missions=tuple(missions),
        air_facilities=(_field(),) if based else (),
        air_unfit=dict(unfit or {}),
        air_strategic=dict(strategic or {}),
        stage=stage)


def _strikes(r: _Run) -> list[int]:
    """The Bomb Points every AIR_STRIKE_RESOLVED in this run actually delivered."""
    return [e.payload["strength"] for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED]


def _rejections(r: _Run) -> list[dict]:
    return [e.payload for e in r.events if e.kind == EventKind.ORDER_REJECTED]


def _n_strikes(n: int, turn: int = 1) -> tuple:
    return tuple(AirMission(Side.AXIS, "strike", (1, 0), turn) for _ in range(n))


class _Tasking(Policy):
    """A policy whose Air Marshal tasks exactly what it was constructed with -- the seam the
    scenario schedule used to occupy, in a commander's hands."""

    def __init__(self, missions):
        self._missions = list(missions)

    def air_missions(self, state: GameState, side: Side) -> list:
        return list(self._missions)


# --- [39.19] THE WITHIN-STAGE PLANE LEDGER ------------------------------------------------------

def test_39_19_a_squadron_flies_its_planes_once_per_operations_stage_and_no_more():
    """"Generally, a plane may fly only one mission per Operations Stage."

    THE REPRODUCTION OF THE HOLE, and it is measured, not hypothetical. The Axis wing is TWO
    aeroplanes carrying 23 Bomb Points between them. Five strike missions are tasked into ONE
    Operations Stage. Before this block every one of the five drew the WHOLE wing -- 115 Bomb
    Points out of a 23-point squadron, the air force flown five times over -- because the only
    thing bounding a second sortie was [38.31]'s refit ledger, which is switched off entirely for
    a side the scenario never based on the map (air.refit_modelled, the [36.5]/[61.42] data hatch).

    39.19 has NO preconditions in the book and has none here."""
    r = _Run(_state(based=False))
    _air_support(r, _Tasking(_n_strikes(5)), Side.AXIS, set())
    assert _strikes(r) == [23, 0, 0, 0, 0]              # the wing flies ONCE, then it is spent
    assert sum(_strikes(r)) == 23


def test_39_19_binds_a_side_that_rule_38_does_not_govern_at_all():
    """The bound must be gated by NOTHING. air.refit_modelled and engine._REFITTABLE_ROLES are
    rule 38's preconditions -- one a data escape hatch, one a fuel-billing decision about the
    fighter arm -- and neither belongs to rule 39. Pinned as a property of the ledger rather than
    of one fixture: the unrefitted, unbased Axis is exactly the side rule 38 says nothing about,
    and it is still held to one flight per plane per stage."""
    st = _state(based=False)
    assert not air.refit_modelled(st, Side.AXIS)        # rule 38 is not in force on this side
    r = _Run(st)
    assert _air_points(r, Side.AXIS, "LAND", "strike") == 23
    _air_support(r, _Tasking(_n_strikes(2)), Side.AXIS, set())
    assert not any(e.kind == EventKind.AIR_SQUADRON_UNFIT for e in r.events)   # 38.31 never fired
    assert _air_points(r, Side.AXIS, "LAND", "strike") == 0                    # 39.19 did


def test_39_19_a_half_spent_squadron_flies_only_the_planes_it_has_left():
    """The ledger is denominated in AEROPLANES, so a mission that put one of two bombers in the
    air leaves exactly one -- and the second mission flies at THAT plane's Bombload (11), not at
    the squadron's 23. The cap is taken in planes and read back out in the rating the Air Points
    are denominated in ([34.14]), which is the identical arithmetic basing.available_points and
    air.ready_points already make for rule 43 and rule 38."""
    r = _Run(_state(based=False, strike=11))            # one aeroplane's worth committed first
    _air_support(r, _Tasking(_n_strikes(1)), Side.AXIS, set())
    assert r.air_flown.current[AXIS_STRIKE] == 1
    # now let the same run see the full two-plane wing: one plane has flown, one has not
    r.state = replace(r.state, air=(AirWing("LW", Side.AXIS, "LAND",
                                            fighters=0, strike=23, recon=0),))
    assert _air_points(r, Side.AXIS, "LAND", "strike") == 11


def test_40_0_a_plane_flies_again_in_the_NEXT_operations_stage_three_in_one_game_turn():
    """[40.0] "...only one mission in an Operations Stage (THREE IN ONE GAME-TURN)." The bound is
    per Operations Stage, so it must expire with the stage and not with the Game-Turn -- which is
    precisely what separates it from the Strategic-Phase half of the same sentence, whose ledger
    (GameState.air_strategic) is cleared at TURN_ADVANCED."""
    r = _Run(_state(based=False, stage=1))
    for stage in (1, 2, 3):
        r.state = replace(r.state, stage=stage)
        _air_support(r, _Tasking(_n_strikes(2)), Side.AXIS, set())
    assert _strikes(r) == [23, 0, 23, 0, 23, 0]         # one full sortie per stage, never two


def test_the_within_stage_ledger_expires_by_its_own_stamp_and_never_leaks():
    """An _OpStageLedger, for the reason that class exists: this bound is read a long way from
    run()'s stage loop, so a caller that drives the Operations Stages itself -- a test, a
    measurement driver, one of run()'s own Game-Turn beats -- must not inherit a spent one. Three
    ledgers shipped with exactly that latent bug before the class did (see _OpStageLedger)."""
    r = _Run(_state(based=False, stage=1))
    _air_support(r, _Tasking(_n_strikes(1)), Side.AXIS, set())
    assert r.air_flown.current == {AXIS_STRIKE: 2}
    r.state = replace(r.state, stage=2)                 # a new Operations Stage, driven by hand
    assert r.air_flown.current == {}
    r.state = replace(r.state, turn=2, stage=1)         # and a new Game-Turn
    assert r.air_flown.current == {}


def test_the_38_31_and_39_19_ledgers_book_THE_SAME_plane_count():
    """ONE plane count, TWO ledgers. [38.31]'s persistent readiness stock and [39.19]'s
    within-stage commitment are written by one function off one conversion, because two call
    sites that each convert Air Points to aeroplanes are two chances to disagree about how many
    machines left the ground -- and the disagreement would be silent.

    It is also the premise of the inertness argument: because the same n is added to both, the
    unfit count is always >= the flown count within a stage, so the 39.19 gate can never bind
    where 38.31 is modelled, and no signature moves."""
    r = _Run(_state(strike=23))                          # based -> rule 38 IS in force
    _air_support(r, _Tasking(_n_strikes(1)), Side.AXIS, set())
    unfit = [e.payload["planes"] for e in r.events if e.kind == EventKind.AIR_SQUADRON_UNFIT]
    assert unfit == [2]
    assert r.air_flown.current[AXIS_STRIKE] == unfit[0]


def test_where_rule_38_is_modelled_the_new_gate_is_inert_and_both_rules_agree():
    """The campaign's own configuration: both sides based on the map, so [38.31] already stops the
    second sortie in a stage. After this block it is stopped for TWO independent reasons instead
    of one -- and the number does not change, which is the whole acceptance criterion for the
    slice (tests/baselines.py must not move)."""
    r = _Run(_state(strike=23))
    _air_support(r, _Tasking(_n_strikes(3)), Side.AXIS, set())
    assert _strikes(r) == [23, 0, 0]
    assert r.state.air_unfit == {AXIS_STRIKE: 2}         # 38.31 says no
    assert r.air_flown.current == {AXIS_STRIKE: 2}       # 39.19 says no, independently


def test_39_19_the_strategic_phase_half_still_excludes_the_malta_contingent():
    """"A plane flying a mission in an Operations Stage may not fly in the Strategic Phase of that
    Game-Turn AND VICE VERSA." The second half is game.basing.strategic_planes and predates this
    block; the two halves COMPOSE (both are caps on the same establishment, taken with min), they
    do not replace one another. One of the wing's two bombers went to Malta this Game-Turn, so one
    is left for the desert -- and after it flies, none is."""
    r = _Run(_state(based=False, strategic={AXIS_STRIKE: 1}))
    assert _air_points(r, Side.AXIS, "LAND", "strike") == 11      # 43/39.19-strategic: one plane
    _air_support(r, _Tasking(_n_strikes(2)), Side.AXIS, set())
    assert _strikes(r) == [11, 0]
    assert r.air_flown.current == {AXIS_STRIKE: 1}


def test_39_2_combined_missions_need_no_exemption_from_a_PLANE_ledger():
    """[39.19]'s parenthesis promises an exception "for certain fighters and dive bombers; Case
    39.2", and [41.16] says in six words what it is: "Certain planes may undertake TWO MISSIONS
    SIMULTANEOUSLY". [39.2] itself: a D("dual") plane "may strafe and bomb THE SAME TARGET as a
    combined mission" -- two mission LABELS on ONE FLIGHT at ONE target, not two sorties.

    So a ledger that counts AEROPLANES PUT IN THE AIR already prices it at one and needs no branch.
    A mission-denominated ledger would have needed one; this is a direct payoff of the plane ruling.

    THE ENGINE CANNOT EXPRESS IT ANYWAY, and this pins the reason so the exemption is a decision on
    record and not an oversight: [39.2] is a STRAFE-and-bomb rule, and strafing ([40.5]/[40.6]) is
    unimplemented -- there is no strafe half for a combined mission to combine with. The D column
    is transcribed and read by nothing; air.mission_capable is a pure data check that gates no
    engine path, because an AirWing is a hexless national pool with no individual plane to carry a
    capability letter. All of it dissolves at [34.72]."""
    from game.logistics_data import aircraft_characteristics_4_44
    rows = aircraft_characteristics_4_44()
    dual = {t for t, row in rows.items()
            if isinstance(row, dict) and row.get("mission_capability", {}).get("D", "-") != "-"}
    assert "Ju. 87B" in dual and len(dual) == 9        # the D column IS transcribed...
    assert "strafe" not in _AIR_MISSIONS               # ...and there is no strafing mission to fly
    # and the ledger carries no exemption branch for any of them: the count is aeroplanes, so a
    # combined mission is one aeroplane in the air, which is what it is.
    r = _Run(_state(based=False))
    _air_support(r, _Tasking(_n_strikes(2)), Side.AXIS, set())
    assert r.air_flown.current == {AXIS_STRIKE: 2}     # two planes, not four "missions"


# --- [39.11] THE MISSION-KIND BOUNDARY ----------------------------------------------------------

def test_39_11_an_unknown_mission_kind_is_REJECTED_not_silently_dropped():
    """"No plane may fly unless it has been assigned A SPECIFIC MISSION." A kind this engine has no
    resolver for is not a specific mission, and before this block the dispatch was a bare if/elif
    with no else: an unrecognised kind vanished with no event, no refusal and no invariant. Harmless
    while the only author was game.scenario; an order-validation hole the moment a policy can author
    missions, which is what Policy.air_missions makes true."""
    r = _Run(_state(based=False))
    _air_support(r, _Tasking([AirMission(Side.AXIS, "napalm", (1, 0), 1)]), Side.AXIS, set())
    assert _strikes(r) == []
    assert [(p["reason"], p["kind"]) for p in _rejections(r)] == [
        ("unknown air mission kind", "napalm")]


def test_the_kind_a_mission_may_carry_IS_the_dispatch_table():
    """ONE source of truth for the vocabulary. A whitelist held apart from the dispatch is a second
    source that can drift -- which is the very defect being fixed -- so the dispatch table IS the
    whitelist, and this test pins the seven kinds it must hold. game.state.AirMission's docstring
    names the same seven; it used to name four while the engine flew seven."""
    assert set(_AIR_MISSIONS) == {"strike", "fort", "port", "airfield", "dump", "trucks", "recon"}
    from game.state import AirMission as _AM
    for kind in _AIR_MISSIONS:
        assert kind in _AM.__doc__, kind


def test_an_unknown_kind_is_rejected_even_when_the_sky_has_grounded_the_air_force():
    """The kind check comes FIRST in the loop body, before the [29.43]/[29.52] grounding continue.
    An unknown kind is not a mission at all; grounding it for weather would hide an order error
    behind a sandstorm, and the rejection would appear or not appear depending on the sky."""
    st = replace(_state(based=False), weather="sandstorm")
    r = _Run(st)
    _air_support(r, _Tasking([AirMission(Side.AXIS, "napalm", (1, 0), 1),
                              AirMission(Side.AXIS, "strike", (1, 0), 1)]), Side.AXIS, set())
    assert [p["reason"] for p in _rejections(r)] == ["unknown air mission kind"]
    assert _strikes(r) == []                             # the well-formed one is merely grounded


# --- Policy.air_missions -- THE HANDBACK --------------------------------------------------------

def test_the_default_hook_returns_exactly_the_scenario_schedule():
    """THE ENTIRE SAFETY ARGUMENT FOR OPENING THE HOOK. Policy.air_missions' default is the
    comprehension the engine used to run inline, so every scenario and every policy that does not
    override it flies precisely what it flew before -- ScriptedPolicy included, unchanged."""
    sched = (AirMission(Side.AXIS, "port", "PORT-Tobruk", 1),
             AirMission(Side.ALLIED, "port", "PORT-Tobruk", 1),
             AirMission(Side.AXIS, "strike", (1, 0), 2))
    st = _state(missions=sched, turn=1)
    assert Policy().air_missions(st, Side.AXIS) == [sched[0]]        # this side, this Game-Turn
    assert Policy().air_missions(st, Side.ALLIED) == [sched[1]]
    assert ScriptedPolicy(attacker=Side.AXIS).air_missions(st, Side.AXIS) == [sched[0]]
    assert Policy().air_missions(replace(st, turn=2), Side.AXIS) == [sched[2]]


def test_the_engine_flies_what_the_POLICY_returns_not_what_the_scenario_scheduled():
    """The seat holds the decision now. A commander who declines to task the scheduled mission
    flies nothing -- there is no such thing as a compulsory sortie in rule 39, and 39.32 lets a
    Player abort one he has already written down."""
    st = _state(missions=_n_strikes(1), based=False)
    flown = _Run(st)
    _air_support(flown, Policy(), Side.AXIS, set())
    assert _strikes(flown) == [23]                       # the default: the schedule, as before
    declined = _Run(st)
    _air_support(declined, _Tasking([]), Side.AXIS, set())
    assert _strikes(declined) == []                      # the Air Marshal stood his squadron down


def test_an_adversarial_policy_is_refused_at_the_boundary():
    """game.llm.MockClient can return adversarial output, and the order-rejection boundary exists
    for exactly that. The engine re-validates SIDE, GAME-TURN, KIND and TARGET SHAPE rather than
    trusting the policy -- the same posture every other hook in this engine takes."""
    r = _Run(_state(based=False))
    _air_support(r, _Tasking([
        AirMission(Side.ALLIED, "strike", (1, 0), 1),        # the enemy's air force
        AirMission(Side.AXIS, "strike", (1, 0), 7),          # a Game-Turn that is not this one
        AirMission(Side.AXIS, "strike", "PORT-Tobruk", 1),   # a port id where a hex belongs
        AirMission(Side.AXIS, "port", (1, 0), 1),            # a hex where a port id belongs
        AirMission(Side.AXIS, "strike", (1, 2, 3), 1),       # not a hex at all
    ]), Side.AXIS, set())
    assert _strikes(r) == []
    assert sorted(p["reason"] for p in _rejections(r)) == sorted([
        "air mission belongs to the other side",
        "air mission is not due this Game-Turn",
        "malformed air mission target",
        "malformed air mission target",
        "malformed air mission target",
    ])


def test_a_policy_that_hands_back_something_that_is_not_a_mission_is_refused_not_fatal():
    """An untrusted seat can return anything at all. It must be refused at the boundary, not crash
    the fold: this engine rejects a bad ORDER and raises only on a misencoded RULE
    (game.invariants), and a staff's typo is the former."""
    r = _Run(_state(based=False))
    _air_support(r, _Tasking(["fly to Cairo", 17]), Side.AXIS, set())
    assert [p["reason"] for p in _rejections(r)] == ["not an air mission"] * 2


def test_the_engine_and_not_the_policy_fixes_the_order_missions_fly_in():
    """The sort stays inside the engine, so a policy's ORDERING is not load-bearing: two seats that
    task the same missions in different orders produce the same log. That is what keeps a live LLM
    seat deterministic when it shuffles its own list."""
    a = AirMission(Side.AXIS, "fort", (1, 0), 1)
    b = AirMission(Side.AXIS, "strike", (1, 0), 1)
    forward, backward = _Run(_state(based=False)), _Run(_state(based=False))
    _air_support(forward, _Tasking([a, b]), Side.AXIS, set())
    _air_support(backward, _Tasking([b, a]), Side.AXIS, set())
    assert [(e.kind, e.payload) for e in forward.events] == \
           [(e.kind, e.payload) for e in backward.events]


def test_a_scenario_that_schedules_no_air_mission_flies_nothing():
    """Both benchmark scenarios seed air=() and air_missions=(), so _air_support returns at its
    first line and no ledger, hook or whitelist can reach their signatures."""
    for build in (rommels_arrival, siege_of_tobruk):
        st = build(1941)
        assert st.air == () and st.air_missions == ()
        r = _Run(st)
        _air_support(r, ScriptedPolicy(attacker=Side.AXIS), Side.AXIS, set())
        assert r.events == []


# --- THE AIR MARSHAL'S SEAT ---------------------------------------------------------------------

def test_the_campaign_air_doctrine_is_shared_by_both_campaign_variants():
    """[39.1] The scripted campaign Axis and the LIVE-STAFF campaign must not diverge on rule 39,
    the same way they already cannot diverge on rule 44 (malta_raid_doctrine), rule 56
    (convoy_plan_doctrine) or rule 54 (axis_rail_doctrine). One doctrine function, wired into
    both."""
    from game.campaign_policy import CampaignCommonwealthPolicy
    from game.campaign_staff import CampaignStaffPolicy
    st = _state(missions=_n_strikes(1))
    want = air_mission_doctrine(st, Side.AXIS)
    assert want == [AirMission(Side.AXIS, "strike", (1, 0), 1)]
    for cls in (CampaignAxisPolicy, CampaignCommonwealthPolicy, CampaignStaffPolicy):
        # each WIRES the shared doctrine rather than silently inheriting Policy's default -- which
        # is the property that stops the two campaign variants drifting apart on rule 39
        assert cls.air_missions is not Policy.air_missions, cls.__name__
        assert cls.air_missions(cls, st, Side.AXIS) == want, cls.__name__


def test_the_air_marshal_seat_now_FLIES_what_it_proposes():
    """The sharpest instance of the owner's standing objection, closed. staff_policy._air_plan was
    a PURE PROJECTION: it read the pre-baked schedule off GameState and staged it as a
    STAFF_PROPOSAL with the rationale "air marshal tasks N mission(s) this turn" -- a seat
    narrating a decision it never made, because no Policy method was consulted and the engine read
    the schedule for itself.

    After this block the seat's air_missions() IS what the engine flies, and _air_plan proposes
    the very list the seat returns -- one source, so the narration and the order can never
    disagree."""
    from game.llm import MockClient
    from game.observation import observe
    from game.staff_policy import AIR, StaffPolicy
    st = _state(missions=_n_strikes(1))
    seat = StaffPolicy(MockClient(""), side=Side.AXIS)
    tasked = seat.air_missions(st, Side.AXIS)
    assert tasked == [AirMission(Side.AXIS, "strike", (1, 0), 1)]
    seat._air_plan(st, observe(st, Side.AXIS))
    proposal = next(p for k, p in seat._pending
                    if k == EventKind.STAFF_PROPOSAL and p["seat"] == AIR)
    assert len(proposal["proposes"]) == len(tasked)
    assert [p["units"][0] for p in proposal["proposes"]] == [m.kind for m in tasked]


# --- THE THREE DEFECTS THE ADVERSARIAL REVIEWS FOUND, each reproduced before it was fixed -------
# All three lenses AND the independent gate reproduced #1 separately; #2 and #3 came from the
# blast-radius and correctness lenses. Added 2026-08-08.

def _recons(n: int, turn: int = 1) -> tuple:
    return tuple(AirMission(Side.AXIS, "recon", (q, 0), turn) for q in range(1, n + 1))


def _sighted(r: _Run) -> list:
    return [tuple(e.payload["hex"]) for e in r.events
            if e.kind == EventKind.AIR_RECON_RESOLVED]


def test_39_19_binds_RECON_too_and_a_spent_arm_lifts_no_fog():
    """[39.19] BOUNDS THE RECONNAISSANCE ARM, and until this test it did not.

    `_air_recon` opened `if committed > 0 and fuel(committed) <= 0: return`, which SHORT-CIRCUITS
    at committed == 0 -- so once the ledger had spent the arm, the guard was False and the function
    walked straight on to the [42.2] fog-lift. Its six sibling resolvers all open `if strength <= 0:
    return`; recon was the sole exception.

    THIS IS THE LARGEST-CONSEQUENCE HOLE A LIVE AIR MARSHAL HAD. Rule 3.6 limited intelligence is
    the thing recon defeats (game.observation unions air_sighted_for), so an unbounded recon arm is
    unbounded free intelligence -- and it was newly reachable by exactly the untrusted seat this
    slice opens, while three fresh docstrings asserted the opposite.

    Measured before the fix: five recon missions in ONE Operations Stage revealed ALL FIVE hexes,
    the ledger booked the arm on the first, and only one mission's fuel was ever drawn -- four
    hexes de-fogged by zero aeroplanes burning zero fuel."""
    r = _Run(_state(based=False, recon=11))
    _air_support(r, _Tasking(_recons(5)), Side.AXIS, set())
    assert _sighted(r) == [(1, 0)], (
        "a recon arm spent by [39.19] must not keep lifting fog -- rule 3.6 is what this defeats")


def test_39_19_a_side_with_no_reconnaissance_aeroplanes_lifts_no_fog_at_all():
    """The sharper half of the same defect: a wing carrying NO reconnaissance aircraft revealed
    every tasked hex, because nothing ever consulted the committed points at all."""
    r = _Run(_state(based=False, recon=0))
    _air_support(r, _Tasking(_recons(3)), Side.AXIS, set())
    assert _sighted(r) == [], "a side with zero recon aeroplanes cannot reconnoitre anything"


def test_a_rejected_mission_payload_is_deterministic_for_any_target_whatsoever():
    """[CLAUDE.md rule 4] DETERMINISM BINDS ABSOLUTELY: same seed -> byte-identical event log.

    The rejection payload rendered an unrecognised target with `repr()` -- the only repr() in all
    of game/. A set reorders under PYTHONHASHSEED and a plain object carries its memory address,
    so two runs of the same seed produced DIFFERENT event logs. ORDER_REJECTED payloads are hashed
    into both benchmark signatures (engine.py), so this sat directly on the seam built for
    untrusted input, which is precisely where an adversarial LLM order arrives."""
    weird = [AirMission(Side.AXIS, "strike", {"b", "d", "c", "a"}, 1),
             AirMission(Side.AXIS, "strike", object(), 1)]
    seen = []
    for _ in range(2):
        r = _Run(_state(based=False))
        _air_support(r, _Tasking(weird), Side.AXIS, set())
        seen.append([p["target"] for p in _rejections(r)])
    assert seen[0] == seen[1], f"the rejection payload is not deterministic: {seen}"
    for t in seen[0]:
        assert "0x" not in t, f"a memory address reached the event log: {t!r}"


def test_missions_sort_by_their_coordinates_not_by_their_python_repr():
    """The dispatch order must not depend on whether a policy hands back a tuple or a list.
    `str(target)` puts '(' (0x28) before '[' (0x5B), so a tuple target always sorted ahead of a
    list one whatever the coordinates -- and with one aeroplane left, sort order decides WHICH hex
    is reconnoitred. _is_hex deliberately accepts both shapes, so the key must canonicalise."""
    as_tuple = [AirMission(Side.AXIS, "recon", (2, 0), 1), AirMission(Side.AXIS, "recon", (1, 0), 1)]
    as_list = [AirMission(Side.AXIS, "recon", [2, 0], 1), AirMission(Side.AXIS, "recon", [1, 0], 1)]
    out = []
    for missions in (as_tuple, as_list):
        r = _Run(_state(based=False, recon=11))
        _air_support(r, _Tasking(missions), Side.AXIS, set())
        out.append(_sighted(r))
    assert out[0] == out[1] == [(1, 0)], f"tuple/list targets dispatched differently: {out}"


def test_a_side_with_no_air_force_still_hears_that_its_order_was_junk():
    """THE FEEDBACK HOLE, closed 2026-08-08 (faithfulness review). `_air_support` returned on
    `if not r.state.air` BEFORE the rejection boundary ran, so a side the scenario seeded with no
    AirWing -- which is BOTH Desert Fox benchmarks -- swallowed a malformed order entirely: no
    rejection, no event, no feedback. That is precisely the defect class this slice exists to
    close, and a live seat learns nothing from silence.

    Byte-identity is untouched because the DEFAULT hook returns the scenario's own missions and an
    air-less scenario carries air_missions=(), so nothing is ever tasked there -- which the
    benchmark signature guards prove independently."""
    st = replace(_state(based=False), air=())
    r = _Run(st)
    _air_support(r, _Tasking([AirMission(Side.AXIS, "no-such-kind", (1, 0), 1)]), Side.AXIS, set())
    assert [p["reason"] for p in _rejections(r)], (
        "an air-less side must still be told its order was malformed")


def test_an_air_less_side_that_tasks_nothing_still_emits_nothing():
    """The other half of the guarantee above: the air-less path must stay silent when the mission
    column is empty, which is what keeps every air-less scenario byte-identical."""
    r = _Run(replace(_state(based=False), air=()))
    _air_support(r, ScriptedPolicy(Side.AXIS), Side.AXIS, set())
    assert r.events == []
