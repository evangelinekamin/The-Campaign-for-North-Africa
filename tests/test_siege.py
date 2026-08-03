"""Siege of Tobruk (rule 25.14 / 25.16): a sustained artillery BARRAGE batters a
fortification's level down one step at a time.

Verifies the faithful crackable siege -- the wall reduces and emits FORT_REDUCED
(folding into a dynamic per-hex fort level), close assault reads the CURRENT
(possibly reduced) level, barrage never evicts, and close assault never reduces the
wall.

RESTATED 2026-08-01 (the 25.14 slice). This file used to end its docstring "...and the canonical
rommels_arrival benchmark is byte-identical with the rule OFF (the default)", and three of its tests
asserted the OFF posture: that `GameState.siege_rules` defaulted False, that a barrage under it
reduced nothing, and that `BARRAGE_HITS_PER_FORT_LEVEL` could be monkeypatched to make the wall take
two hits. ALL THREE ENSHRINED THE BUG. Section 25 was read off the scan in full (PDF p.38) and
carries no scenario condition of any kind, so the flag was CLAUDE.md-rule-6 debt and is deleted; the
hits-per-level constant was an invented certainty standing in for the printed [41.5] Fortification
row and is deleted too. The three are restated below to assert what is actually true -- there is no
posture in which 25.14 is inert, and how fast a wall falls is a chart's answer. The mechanism itself
is unchanged and every other assertion here stands as written. tests/test_fort_barrage.py owns the
new chart, doctrine and air-channel coverage."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords
from game.apply import apply, fold
from game.engine import _barrage_step, _resolve_combat, _Run, determinism_signature, run
from game.events import Event, EventKind, Phase, Side
from game.hexmap import distance
from game.movement import TerrainMap
from game.policy import ScriptedPolicy, StormPolicy
from game.scenario import rommels_arrival, siege_of_tobruk
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain


def _siege_state(*, fort: int = 2, atk_barrage: int = 26,
                 fort_levels: dict | None = None) -> GameState:
    """Axis artillery in (0,0) adjacent to a fortified Allied garrison in (1,0).

    atk_barrage RAISED 25 -> 26 (2026-08-01) TO PRESERVE THIS HELPER'S OWN STATED INTENT, which is
    seed-independence. It used to read "25 x TOE 8 -> 20 Actual Barrage Points -> CRT column 8, where
    EVERY d66 roll yields a Pin or a loss" -- true of the [12.6] table, which is where a barrage
    against the GARRISON is resolved. A barrage against the WORKS is resolved on the [41.5]
    Fortification row instead ([12.53]), and 20 Actual points sits in its 19,20 column, which reduces
    on 35 of 36 codes -- nearly always, but not always. 26 x TOE 8 = 208 Raw = 21 Actual is the 21+
    column, where all 36 codes read "Reduced", so the wall comes down on any die exactly as this
    helper has always promised. The magnitude is not a balance choice: it is the smallest input that
    makes the chart deterministic, and no assertion below was relaxed to meet it."""
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.MAJOR_CITY}
    arty = Unit("AR", Side.AXIS, (0, 0), (StepRecord("ar", 8),), mobility=Mobility.MOTORIZED,
                cpa=20, stacking_points=1, oca=0, dca=1, barrage=atk_barrage, vulnerability=5)
    gar = Unit("GAR", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=2, oca=5, dca=8, is_garrison_home=True)
    # Ammo sized for several barrages: barrage now costs 4 x TOE (50.14) = 4*8 = 32.
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=200, fuel=60)
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={(1, 0): fort}),
        control={}, units=(arty, gar), target_hex=(1, 0), supplies=(dump,),
        consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 200, "FUEL": 60},
        fort_levels=dict(fort_levels or {}))


# --- the dynamic fort level (state layer) ------------------------------------

def test_fort_level_falls_back_to_static():
    # with no dynamic overlay, the current level IS the static terrain fortification.
    s = _siege_state(fort=2)
    assert s.fort_level((1, 0)) == 2
    assert s.fort_level((0, 0)) == 0            # unfortified hex


def test_fort_reduced_event_folds():
    s = _siege_state(fort=2)
    e = Event(0, 1, Phase.COMBAT, Side.AXIS, "AXIS/Front",
              EventKind.FORT_REDUCED, {"hex": [1, 0], "level": 1})
    s2 = apply(s, e)
    assert s2.fort_level((1, 0)) == 1
    assert s.fort_level((1, 0)) == 2            # original state untouched (immutability)
    assert fold(s, [e]).fort_level((1, 0)) == 1


# --- barrage batters the wall (ungated: section 25 carries no scenario condition) -------------

def test_barrage_reduces_fort_and_emits_event():
    r = _Run(_siege_state(fort=2))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    reduced = [e for e in r.events if e.kind == EventKind.FORT_REDUCED]
    assert reduced, "a successful barrage on a fortified hex must emit FORT_REDUCED"
    assert reduced[0].payload == {"hex": [1, 0], "level": 1}
    assert r.state.fort_level((1, 0)) == 1


def test_there_is_no_posture_in_which_the_wall_is_safe():
    """RESTATED FROM test_barrage_never_reduces_when_siege_off, which asserted the opposite and was
    the tripwire holding the bug in place: "default (benchmark) posture: the wall-reduction mechanic
    is inert". There is no such posture. [25.14] carries no scenario, campaign or optional-rule
    condition (PDF p.38, read off the scan), so the SAME battery on the SAME wall batters it in the
    small benchmark scenario, in the siege scenario and in the 111-turn campaign alike. What can
    still leave a wall standing is the [41.5] chart -- a low-point barrage mostly misses -- and that
    is asserted in tests/test_fort_barrage.py, where the chart lives."""
    for build in (rommels_arrival, siege_of_tobruk):
        assert not hasattr(build(seed=1941), "siege_rules")
    r = _Run(_siege_state(fort=2))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    assert any(e.kind == EventKind.FORT_REDUCED for e in r.events)
    assert r.state.fort_level((1, 0)) == 1


def test_barrage_never_evicts_the_garrison():
    # rule 25.14 is sacred: barrage brings the wall down but never moves the garrison
    # nor its base fort in the static map -- only the dynamic overlay drops.
    r = _Run(_siege_state(fort=2))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    gar = r.state.unit("GAR")
    assert gar.hex == (1, 0)                                   # not evicted
    assert not any(e.kind == EventKind.UNIT_RETREATED for e in r.events)
    assert r.state.terrain.fortifications[(1, 0)] == 2         # static base sacred


def test_barrage_floors_fort_at_zero():
    # a barrage on an already-open (level 0) fortified hex emits nothing.
    r = _Run(_siege_state(fort=0))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    assert not any(e.kind == EventKind.FORT_REDUCED for e in r.events)


def test_how_many_barrages_a_wall_takes_is_the_charts_answer_and_not_a_knobs():
    """RESTATED FROM test_hits_per_level_knob, which monkeypatched engine.BARRAGE_HITS_PER_FORT_LEVEL
    to 2 and asserted the wall then needed two barrages. That constant was an INVENTED MAGNITUDE
    ("the lead tunes this with the benchmark harness", by its own comment) sitting where the [41.5]
    Fortification row belonged, and a test that exercised the knob was a test that certified the
    invention. It is deleted; nothing in the engine now decides how hard a wall is.

    The chart decides, and it decides by WEIGHT OF FIRE rather than by a count of hits: the same wall
    facing 21 Actual Barrage Points falls to the first shoot (36 of 36 codes), facing 2 falls only to
    a 66 (1 of 36). Asserted as a distribution over all 36 sequential codes, so no seed is involved."""
    from game import fortifications
    codes = [d1 * 10 + d2 for d1 in range(1, 7) for d2 in range(1, 7)]
    heavy = sum(fortifications.reduced_by_barrage(21, c // 10, c % 10) for c in codes)
    light = sum(fortifications.reduced_by_barrage(2, c // 10, c % 10) for c in codes)
    assert (heavy, light) == (36, 1)
    # and the engine really reads it: the light battery's shoot is on the record, hit or miss.
    r = _Run(_siege_state(fort=2, atk_barrage=2))
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    fired = [e for e in r.events if e.kind == EventKind.FORT_BARRAGED]
    assert len(fired) == 1 and fired[0].payload["actual"] == 2


# --- close assault reads the CURRENT (reduced) level -------------------------

def _assault_state(fort_levels: dict) -> GameState:
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.CLEAR}
    atk = Unit("A", Side.AXIS, (0, 0), (StepRecord("i", 5),), mobility=Mobility.FOOT,
               cpa=25, stacking_points=1, oca=6, dca=2)
    dfd = Unit("D", Side.ALLIED, (1, 0), (StepRecord("i", 3),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=1, oca=2, dca=2)
    sup = (SupplyUnit("DA", Side.AXIS, (0, 0), ammo=40, fuel=60),
           SupplyUnit("DL", Side.ALLIED, (1, 0), ammo=40, fuel=60))
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=11,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={(1, 0): 2}),
        control={}, units=(atk, dfd), target_hex=(1, 0), supplies=sup,
        consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 80, "FUEL": 120},
        fort_levels=dict(fort_levels))


def _assault_column(fort_levels: dict) -> int:
    r = _Run(_assault_state(fort_levels))
    atk = [r.state.unit("A")]
    dfd = [r.state.unit("D")]
    _resolve_combat(r, Side.AXIS, "AXIS/Front", atk, dfd, (1, 0), set(), set())
    resolved = [e for e in r.events if e.kind == EventKind.COMBAT_RESOLVED]
    return resolved[0].payload["column"]


def test_close_assault_tracks_reduced_fort_level():
    # identical assault + identical seed: a reduced wall (overlay 0) yields a column
    # further toward the attacker than the intact wall (static 2). Same dice, so the
    # ONLY difference is the fortification shift -- proving the engine reads the
    # dynamic level, not the static one.
    intact = _assault_column({})              # falls back to static level 2
    breached = _assault_column({(1, 0): 0})   # wall battered open
    assert breached > intact


# --- the benchmark: nothing reaches a wall inside twelve turns ----------------

def test_no_gun_reaches_a_wall_inside_the_twelve_turn_clock():
    """RESTATED FROM test_rommels_arrival_defaults_to_siege_off + test_benchmark_byte_identical_and_
    emits_no_fort_reduction. The assertions are unchanged and still pass; THEIR REASON IS NOT, and
    that is the whole point of restating them rather than deleting them.

    They used to hold because a scenario flag switched 25.14 off. The flag is gone and both channels
    are live in every scenario, and these two benchmarks STILL emit no FORT_REDUCED and still hash to
    the same signatures they did before the slice. The cause is PROXIMITY, and it is MEASURED HERE
    rather than asserted in prose, because prose is what got it wrong the first time (this docstring
    said "63 hexes"): on seed 1941 the nearest Axis battery opens 69 hexes from Tobruk and has closed
    only to 31 when the clock runs out, so no battery is ever adjacent to a fortification to
    designate one. The gate had been hiding behind a distance the whole time -- which is why removing
    it moved neither benchmark by a byte, and why a benchmark signature is a determinism check and
    never evidence that a rule is inert.

    RE-MEASURED 2026-08-02, [52.42] (the CPA condition on the vehicle's Water Point): the closing
    distance moves 31 -> 52, and this docstring's own warning -- "if the guns now close, this test
    is measuring something else" -- is answered the RIGHT way round. The guns do not close; they
    stall FURTHER OUT, so the thesis holds with more room than it had, and the pinned pair is
    re-measured rather than the claim re-read. THE CAUSE IS THE RULE ITSELF and it is worth
    recording: [52.42] names Artillery outright ("Each TOE Strength Point of Vehicle (Tank, Recce,
    Artillery, etc.)... requires one Water Point each Operations Stage, if it uses any of its CPA"),
    so a battery that moves now draws its water where it stands, and [52.51] refuses the move when
    it cannot. Measured on this very run: 199 of the Axis batteries' move orders are refused for
    want of water. The guns are the thing that outruns the wells -- which is why they are still 52
    hexes from Tobruk's wall when the twelve-turn clock runs out.

    RE-MEASURED 2026-08-02, [10.29] (engine._capture_noncombat: a non-combat counter with no
    strength of any type, alone in an enemy ZOC during the enemy's Movement/Combat Phase, is
    Captured). The closing distance moves 52 -> 42, and the docstring's own warning is answered the
    same way as last time: the guns do NOT close on the wall -- 42 hexes is not adjacency, no
    battery ever designates a fortification, and the two FORT assertions above still hold -- so the
    pinned pair is re-measured and the thesis is left standing.

    THE CAUSE IS ONE COUNTER. This benchmark fields exactly two counters with no strength of any
    type, both Commonwealth Squadron Ground Support Units, and exactly ONE of them is taken:
    AL-SGSU-250RAF, at Operations Stage 1 of Game-Turn 1. That single removal is the whole reason
    both benchmark signatures move (tests/baselines.py's 2026-08-02 [10.29] entry) -- one counter
    off the board on the first stage reshapes twelve Game-Turns of scripted movement and combat
    behind it. It is also why the number moved TOWARD Tobruk rather than away: this is a different
    war, not a slower one."""
    for build in (rommels_arrival, siege_of_tobruk):
        assert not hasattr(build(), "siege_rules")
    a = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert not any(e.kind == EventKind.FORT_BARRAGED for e in a.events)
    assert not any(e.kind == EventKind.FORT_REDUCED for e in a.events)
    # ...and THIS is why, stated as a measurement so it cannot quietly stop being true.
    tobruk = coords.to_axial(coords.parse("C4807"))

    def nearest_gun(st):
        return min(distance(u.hex, tobruk) for u in st.living(Side.AXIS)
                   if u.barrage > 0 and u.is_combat)

    assert (nearest_gun(a.initial), nearest_gun(a.final)) == (69, 42), (
        "the benchmark is silent on 25.14 because no gun gets near a wall; if the guns now close, "
        "this test is measuring something else and must be re-read, not re-pinned")


# --- the new scenario --------------------------------------------------------

def test_siege_of_tobruk_constructible():
    s = siege_of_tobruk(seed=1941)
    # same battle: identical OOB / placement to rommels_arrival. It used to differ from it by the
    # siege_rules flag and NOTHING ELSE ON THIS AXIS; now it differs only by the ferry interdiction.
    base = rommels_arrival(seed=1941)
    assert [u.id for u in s.units] == [u.id for u in base.units]
    assert {u.id: u.hex for u in s.units} == {u.id: u.hex for u in base.units}


def test_siege_of_tobruk_runs_full_game():
    a = run(siege_of_tobruk(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert a.winner in (Side.AXIS, Side.ALLIED)
    assert fold(a.initial, a.events) == a.final               # replay-exact
    b = run(siege_of_tobruk(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)


def test_siege_of_tobruk_deterministic_across_seeds():
    from game.hexmap import distance  # noqa: F401 (ensures import health)
    for seed in range(1, 4):
        a = run(siege_of_tobruk(seed=seed), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
        assert a.winner in (Side.AXIS, Side.ALLIED)
        assert fold(a.initial, a.events) == a.final


# --- the parameterized air choke (Step 2 checkpoint) -------------------------

def test_siege_defaults_are_air_less_and_byte_identical():
    # the DEFAULT siege carries the ferry interdiction but NO air -- byte-identical to pre-choke.
    s = siege_of_tobruk(seed=1941)
    assert s.air == () and s.air_missions == ()
    assert all(o.lane == "SEA-TOBRUK" and o.bomb_points == 200 for o in s.interdictions)


def test_port_bomb_fields_the_luftwaffe_and_a_full_harbour_schedule():
    s = siege_of_tobruk(seed=1941, port_bomb=True)
    lw = [w for w in s.air if w.side == Side.AXIS and w.arena == "LAND"]
    assert len(lw) == 1 and lw[0].strike > 0                      # a strike wing to batter it
    assert not any(w.side == Side.ALLIED for w in s.air)          # no RAF unless asked
    assert {m.kind for m in s.air_missions} == {"port"}
    assert all(m.target == "PORT-Tobruk" for m in s.air_missions)
    assert len(s.air_missions) == s.max_turns                     # one per game-turn
    # raf adds a genuine contesting fighter wing for the LAND-sky superiority roll.
    sr = siege_of_tobruk(seed=1941, port_bomb=True, raf=True)
    daf = [w for w in sr.air if w.side == Side.ALLIED and w.arena == "LAND"]
    assert len(daf) == 1 and daf[0].fighters > 0


def test_port_bomb_contests_the_harbour_which_regenerates_between_the_bombs():
    # THE DUEL (T0-9 / T0-10 / 55.18), replacing the old one-way ratchet. The Axis harbour-bombing
    # schedule now ROLLS on the transcribed [41.5] Ports row -- at six proxy strike points (column
    # 1..20) a level comes off on 4 of 36 rolls -- and 55.18 REGENERATES the harbour +1 every OpStage
    # it is not bombed down. So PORT-Tobruk's Efficiency is CONTESTED (it dips to the bombs and climbs
    # back between them), NOT a monotone ratchet to 0. The besieger must roll well and keep rolling to
    # hold it shut; the benchmark's proxy air does not, so the harbour survives -- that is a MEASUREMENT
    # of the proxy air strength, not a defect (the real 34.6/59.3 strengths are deferred to Phase 5).
    s = siege_of_tobruk(seed=1941, port_bomb=True, raf=True)
    # WAS eff 7 / blocked 0. The harbour now seeds at its charted [55.3] Efficiency 2 of a listed max
    # 5 with the San Giorgio blocking three levels (55.25, scenario._tobruk_port) -- so the duel is
    # fought over a SHORTER ladder (two levels above zero, and 55.18 climbs back only to the blocked
    # ceiling of 2, never to 5). The thesis below is unchanged and still holds on it.
    assert (s.port("PORT-Tobruk").eff, s.port("PORT-Tobruk").max_eff) == (2, 5)
    assert s.port("PORT-Tobruk").blocked == 3
    a = run(s, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    changes = [e for e in a.events if e.kind == EventKind.PORT_EFFICIENCY_CHANGED
               and e.payload["port_id"] == "PORT-Tobruk"]
    bombs = [e for e in changes if "strength" in e.payload]       # _air_port losses (41.39B)
    regens = [e for e in changes if "strength" not in e.payload]  # 55.18 SYSTEM recovery
    assert bombs, "the Axis air force never knocked a level off the harbour"
    assert regens, "55.18 never regenerated the harbour -- it is still a one-way ratchet"
    levels = [e.payload["level"] for e in changes]
    assert levels != sorted(levels, reverse=True)                 # NOT monotone: it both falls and rises
    assert a.final.port("PORT-Tobruk").eff > 0                     # recovered -- never bombed shut for good
    # deterministic + replay-exact
    b = run(siege_of_tobruk(seed=1941, port_bomb=True, raf=True),
            ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert fold(a.initial, a.events) == a.final


# --- the storming payoff: the floor cracks a choked garrison (Step 5) ---------

def _dry_tobruk_storm(seed: int = 1941):
    """battle_for_tobruk with the Tobruk garrison's ammo dried out (the port-bomb/ferry-cut
    endgame the choke drives toward): the panzers stand on the perimeter, a surviving CW
    mobile unit keeps the game alive, and the garrison is out of Close-Assault ammunition."""
    from game.scenario import battle_for_tobruk, _initial_supply
    base = battle_for_tobruk(seed=seed)
    sup = tuple(replace(s, ammo=0) if s.id == "UK-Dump" else s for s in base.supplies)
    return replace(base, supplies=sup, initial_supply=_initial_supply(sup), max_turns=4)


def _timid_storm_client(prompt: str) -> str:
    """A staff 'model' that manoeuvres (advances toward the objective) but NEVER proposes an
    assault -- the measured mercury-2 failure mode the storming floor exists to backstop."""
    import json
    from scripts.benchmark import _mock_axis, _mock_staff
    if "COMMANDER" in prompt and "INTENT" in prompt:
        return _mock_staff(prompt)
    if "MOVEMENT" in prompt:
        return _mock_axis(prompt)                       # advance, incl. onto the vacated objective
    return json.dumps({"reasoning": "hold", "attacks": []})   # never storms on its own


def test_storm_floor_cracks_the_dry_garrison_but_a_timid_staff_never_does():
    from game.llm import MockClient
    from game.staff_policy import StaffPolicy
    from game.state import Control
    st = _dry_tobruk_storm()
    target = st.target_hex

    # A timid staff that never assaults manoeuvres to the wall and stalls: Tobruk holds.
    timid = StaffPolicy(MockClient(_timid_storm_client), side=Side.AXIS, storm_floor=False)
    held = run(st, axis=timid, allied=ScriptedPolicy(attacker=Side.AXIS))
    assert held.winner == Side.ALLIED
    assert held.final.control_of(target) != Control.AXIS

    # WITH the storming floor the same timid staff drives sustained assaults: the dry garrison
    # hits the 15.15 capitulation -- "cracks", the test's own name for it -- on Game-Turn 1.
    #
    # RESTATED 2026-07-26 (Phase 8.1b, the [8.35]/[8.42] escarpment hexside trace): this toy scenario
    # (battle_for_tobruk, real Map C terrain but placeholder unit stats) sits DAK-15Pz on C4707, which
    # MEASURED now carries a genuine UP_ESCARPMENT hexside to C4706 -- dead data before this slice,
    # live for the first time. The panzer's GT1 move (into contact, [8.42]: +8 CP / 6 BP for a vehicle
    # crossing DOWN, the cheaper direction, still real money) now drains AX-Dump2's fuel one turn
    # sooner than the pre-hexside map did; MEASURED, the unit is "out of fuel" (game.observation's own
    # can_move_to reports it) on every turn from GT2 on, including the turn the just-surrendered hex
    # sits empty and adjacent. So the garrison still CRACKS (15.15/15.88 fires below, unweakened -- the
    # storm floor's actual thesis), but nobody is left with the fuel to walk into the vacated fortress
    # and finish the capture: Tobruk holds NEUTRAL, and the scripted Commonwealth's marginal-victory
    # scoring (nobody threatens Tobruk, nobody has taken it) wins the game turn count out from under
    # the stalled Axis. A toy scenario's placeholder fuel seeding meeting a newly-faithful terrain
    # cost, not a capability regression -- the mechanism this test exists to prove (a dry, sustained-
    # assault garrison must capitulate) is intact and asserted immediately below.
    floored = StaffPolicy(MockClient(_timid_storm_client), side=Side.AXIS, storm_floor=True)
    cracked = run(st, axis=floored, allied=ScriptedPolicy(attacker=Side.AXIS))
    surrender = [e for e in cracked.events
                 if e.kind == EventKind.COMBAT_RESOLVED and e.payload.get("surrender") == "defender"]
    assert surrender, "the garrison must fall by the 15.15/15.88 assault surrender, not attrition"
    assert cracked.winner == Side.ALLIED          # the panzer cracks the garrison but runs dry
    assert cracked.final.control_of(target) == Control.NEUTRAL   # before it can walk in and hold it
    # deterministic + replay-exact
    again = run(st, axis=StaffPolicy(MockClient(_timid_storm_client), side=Side.AXIS, storm_floor=True),
                allied=ScriptedPolicy(attacker=Side.AXIS))
    assert determinism_signature(cracked.events) == determinism_signature(again.events)
    assert fold(cracked.initial, cracked.events) == cracked.final


# --- the SUPPLY-DRIVEN crack: a sustained scripted storm STARVES the garrison (rule 15.15) ----
#
# The full siege on real Maps A/B/C, no artificial dry-out (unlike _dry_tobruk_storm above): the
# garrison opens on its faithful 61.36 built-in dump (1500 Ammo) plus the adjacent AL-Dump#3, and
# the ONLY thing standing between it and starvation is the sea lifeline. StormPolicy -- a scripted
# strong-general proxy, zero tokens -- drives the perimeter and assaults every stage; the harbour
# choke (port_bomb) shuts the ferry; and the garrison dump drains to 0 over the campaign, firing the
# 15.15 dry-stack surrender. seed 4210 is the locked deterministic witness (peak 2351 -> 0 by T9).

def _storm(seed: int = 66, *, port_bomb: bool = True, raf: bool = True, lw_strike: int | None = None):
    """The scripted storm siege. `lw_strike`, when set, overrides the Axis Luftwaffe LAND strike
    ESTABLISHMENT (a FLAGGED proxy for the deferred 34.6/59.3 Initial Air Strengths, cranked high
    enough to clear the [41.5] Ports floor every stage and actually shut the harbour). Left None it
    keeps the scenario's own seeded proxy, which cannot cut a full-Efficiency harbour.

    IT IS AN ESTABLISHMENT AND NOT A SORTIE, which is why the number is four times the bombs that
    fall: [43.12] bases 75% of every German bomber pool in Italy/Sicily (game.basing), so 2000 Bomb
    Points of establishment is 400 Ju. 87B of which 100 are in Africa -- the 500 Bomb Points that
    reach Tobruk, the [41.5] 471+ column, and the same air campaign this test has always run."""
    st = siege_of_tobruk(seed, port_bomb=port_bomb, raf=raf)
    if lw_strike is not None:
        air = tuple(replace(w, strike=lw_strike) if w.id == "LW-land" else w for w in st.air)
        st = replace(st, air=air)
    return st, run(st, axis=StormPolicy(attacker=Side.AXIS),
                   allied=ScriptedPolicy(attacker=Side.AXIS))


def test_a_sustained_air_campaign_shuts_the_harbour_and_chokes_the_ferry():
    """The harbour choke, faithful (T0-9 / T0-10 / 48 V.D / 55.18). A SUSTAINED strong-air campaign
    -- the deferred 34.6/59.3 Initial Air Strengths, proxied high enough to clear the [41.5] Ports
    floor every stage -- bombs PORT-Tobruk to Efficiency 0 and holds it there, so the ferry lands a
    fraction of what it does over an open quay. That is the choke, and it is load-bearing.

    It no longer fires the 15.15 dry-stack surrender inside the 12-turn Race-for-Tobruk clock, and
    that is a FAITHFUL FINDING, not a regression. 48 V.D lands the ferry three times a Game-Turn, so
    the built-in harbour reservoir (AL-Tobruk) banks a deep reserve in the two or three turns before
    the campaign shuts the quay -- and a sea-fed Tobruk resists starvation, exactly as it historically
    did through an eight-month siege. The full dry-stack payoff is now gated on a longer siege and the
    deferred stronger/earlier air (Phase 5); this test guards the MECHANISM the payoff will stand on.

    It replaces a test that asserted a 12-turn 15.15 surrender -- which only fired because the
    pre-48-V.D ferry under-fed the garrison AND the pre-T0-10 harbour ratcheted shut on a flat -1 with
    no regen. Both were bugs; with the harbour rolling on [41.5] and regenerating (55.18), only a real
    air campaign can shut it, and a sea-fed fortress survives the clock."""
    from game.state import Control
    st, r = _storm(lw_strike=2000)
    target = st.target_hex

    # (1) the sustained campaign bombs the harbour to Efficiency 0: it clears the [41.5] Ports floor
    # every stage, so it outpaces the 55.18 regen (which needs an un-bombed stage it never gets).
    effs = [e.payload["level"] for e in r.events if e.kind == EventKind.PORT_EFFICIENCY_CHANGED
            and e.payload["port_id"] == "PORT-Tobruk"]
    assert effs and min(effs) == 0, "the air campaign never shut the harbour"

    # (2) the choke is load-bearing: over the shut quay the ferry lands far less than over an open one.
    #
    # THE BAR MOVED 0.3 -> 0.4 BECAUSE THE LADDER DID, not because the choke got weaker. Tobruk now
    # seeds at its charted [55.3] Efficiency 2 of a listed max 5 (scenario._tobruk_port), so BOTH runs
    # are throttled: the open quay lands 680 t/OpStage (2/5 of 1700), not 1700. The bombed harbour
    # oscillates 0 <-> 1 (bombed to 0, 55.18 claws one level back on the next stage, bombed to 0
    # again), and an eff-1 stage lands 340 t = EXACTLY HALF an eff-2 stage -- 1/5 against 2/5 of the
    # same 1700 t rating. So 0.5 is the arithmetic CEILING this duel can approach and only the stages
    # bombed clean to 0 push it below; measured 0.346 (4683 vs 13536 cargo points). Under the old 7/7
    # seed the same 0 <-> 1 oscillation scored 1/7 of an open 7/7 quay, which is why 0.3 fit then and
    # cannot now. 0.4 keeps real regression teeth: it still demands the bombs zero a large share of
    # stages, and a choke that decayed to "harbour merely at eff 1" would score 0.5 and trip it.
    def ferry(res):
        return sum(sum(e.payload["cargo"].values()) for e in res.events
                   if e.kind == EventKind.SUPPLY_ARRIVED and e.payload.get("lane") == "SEA-TOBRUK")
    _, open_run = _storm(port_bomb=False)                  # same seed, harbour never touched
    assert ferry(r) < ferry(open_run) * 0.4, "the shut harbour did not choke the ferry"

    # (3) FAITHFUL FINDING: the 48-V.D-fed reservoir outlasts the 12-turn clock, so no 15.15 dry-stack
    # surrender fires and the fortress HOLDS -- a sea-fed Tobruk is hard to starve.
    assert not any(e.kind == EventKind.COMBAT_RESOLVED and e.payload.get("surrender") == "defender"
                   and e.payload.get("target") == list(target) for e in r.events)
    assert r.final.control_of(target) != Control.AXIS
    assert r.winner == Side.ALLIED

    # deterministic + replay-exact
    _, again = _storm(lw_strike=2000)
    assert determinism_signature(r.events) == determinism_signature(again.events)
    assert fold(r.initial, r.events) == r.final


def test_the_harbour_choke_is_load_bearing_not_atmospheric():
    # THE baseline: the SAME storm on the SAME seed with the harbour left OPEN (port-bomb OFF). The
    # ferry lands tens of thousands of supply Points (48 V.D, three landings a Game-Turn) and the
    # garrison dump RISES far out of the storm's reach, so the fortress is never even pressured. The
    # eff->0 choke is what THROTTLES the sea lane -- the sibling test above shuts the harbour and
    # lands a fraction of this -- and it is the sea lane, not the storm alone, that decides the siege.
    from game.state import Control
    st, held = _storm(port_bomb=False)
    target = st.target_hex
    assert held.winner == Side.ALLIED
    assert held.final.control_of(target) != Control.AXIS
    assert held.final.supply("AL-Tobruk").ammo > 1500      # the open ferry outpaced the storm: dump grew
    assert not any(e.kind == EventKind.COMBAT_RESOLVED
                   and e.payload.get("target") == list(target)
                   and e.payload.get("surrender") == "defender" for e in held.events)
