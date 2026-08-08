"""[25.14] FORTIFICATIONS ARE REDUCED BY ARTILLERY BARRAGE AND BY BOMBING -- and by nothing else.

    [25.14] "Fortifications may be reduced in Level strength by air bombardment (see Case 39.37)
            or artillery barrage (Case 12.5). No other type of combat affects fortifications.
            Reduced fortifications may be rebuilt."   (PDF p.38, read off the scan)

THREE THINGS THIS FILE GUARDS, each of which was broken before it was written.

1. NO SCENARIO CONDITION. Section 25 carries none -- not a campaign clause, not an optional-rule
   clause, nothing. Both channels used to sit behind `GameState.siege_rules`, a flag set in exactly
   one scenario (siege_of_tobruk) and never by campaign(), whose own comment said it existed to keep
   "the canonical benchmark exact". That is the debt CLAUDE.md rule 6 names in as many words, so the
   flag is GONE and these tests hold the door shut behind it.

2. THE MAGNITUDE IS A PRINTED CHART, NOT A CONSTANT. `BARRAGE_HITS_PER_FORT_LEVEL = 1` made every
   effective barrage flatten a level with certainty, and its own comment called itself a knob "the
   lead tunes with the benchmark harness". [12.53] sends a facility barrage to the [41.5] Air
   Bombardment and Secondary Barrage Targets Table on the Artillery-Barrage-Points scale; [41.37]
   sends the bombing mission to the same row on the Bomb-Points scale. That row is transcribed in
   data/logistics_rates.json and read here.

3. THE TARGET IS DESIGNATED, NOT INCIDENTAL. [12.51] "Artillery may be used to Barrage facilities,
   RATHER THAN ACTUAL UNITS"; [12.52] "the Target designated is the specific facility". The old code
   battered the wall as a side effect of a barrage aimed at a unit, which also meant [12.31]'s own
   exception ("Artillery units may not Barrage non-occupied hexes -- however, see Case 12.5") could
   never fire: an EMPTY fortress was unbarrageable.

WHAT IS NOT TESTED HERE BECAUSE IT MUST NOT CHANGE: [15.82] no-eviction. Battering Tobruk flat
removes the [8.37] close-assault shift and unlocks the 41.31 bombing ladder; it does NOT make the
garrison evictable, and test_barrage_never_evicts_the_garrison below pins that.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataclasses import replace

from game import coords, fortifications, logistics_data
from game.apply import fold
from game.engine import _Run, _barrage_step, determinism_signature, run
from game.events import Control, EventKind, Phase, Side
from game.movement import TerrainMap
from game.policy import Policy, ScriptedPolicy
from game.scenario import rommels_arrival
from game.state import AirMission, AirWing, GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain

# every code a pair of dice can make when they are read SEQUENTIALLY (41.22: tens = first die).
# NOT the 21-code larger-first read [12.42] imposes on the [12.6] Artillery Barrage Table.
CODES = [d1 * 10 + d2 for d1 in range(1, 7) for d2 in range(1, 7)]

# THE [41.5] FORTIFICATION ROW, LEFT TO RIGHT, re-read cell by cell off a 300-dpi render of chart
# folio 12 (PDF p.107). One tuple per printed column:
#     (Barrage-Points bracket, Bomb-Points bracket, the "No Effect" cell, the "Reduced" cell)
# The Barrage-Points brackets are the CORRECTED scale (fortification._errata: the 1979 ink runs
# "7,8" and "9,10" together and drops the "2" off the last band); every result cell below is the
# book's own ink with nothing overridden. The eleventh column prints "-" under No Effect, which is
# None here: at 471+ Bomb Points / 21+ Actual Barrage Points there is no code that fails.
FORTIFICATION_ROW = [
    ([1, 2],     [1, 20],     (11, 65), (66, 66)),
    ([3, 4],     [21, 40],    (11, 63), (64, 66)),
    ([5, 6],     [41, 80],    (11, 56), (61, 66)),
    ([7, 8],     [81, 120],   (11, 52), (53, 66)),
    ([9, 10],    [121, 160],  (11, 43), (44, 66)),
    ([11, 12],   [161, 200],  (11, 33), (34, 66)),
    ([13, 14],   [201, 260],  (11, 24), (25, 66)),
    ([15, 16],   [261, 320],  (11, 16), (21, 66)),
    ([17, 18],   [321, 390],  (11, 13), (14, 66)),
    ([19, 20],   [391, 470],  (11, 11), (12, 66)),
    ([21, None], [471, None], None,     (11, 66)),
]


# --------------------------------------------------------------------------------------------
# 1. THE CHART
# --------------------------------------------------------------------------------------------

def test_every_cell_of_the_fortification_row_is_the_cell_the_scan_prints():
    """THE WHOLE ROW, LITERALLY, and it is here because the partition self-check cannot do this job.

    A column partitions the 36 sequential codes as long as its two bands meet somewhere, so a
    misread boundary that still meets -- 11..24 / 25..66 mistyped as 11..23 / 24..66 -- passes the
    partition test, passes the two-outcome test, and passes every count assertion in this file
    except at the four columns a count happens to pin (1, 3, 5 and 11). Seven of the eleven columns
    had no literal assertion anywhere. The chart IS the slice, so the chart is asserted literally."""
    cols = logistics_data.fortification_bombardment_crt_41_5()
    assert len(cols) == len(FORTIFICATION_ROW) == 11
    for i, (barrage, bomb, no_effect, reduced) in enumerate(FORTIFICATION_ROW):
        col = cols[i]
        assert col["barrage_points"] == barrage, f"column {i + 1} Barrage-Points bracket"
        assert col["bomb_points"] == bomb, f"column {i + 1} Bomb-Points bracket"
        cells = {e["reduced"]: tuple(e["die"]) for e in col["results"]}
        assert len(cells) == len(col["results"]), f"column {i + 1} repeats an outcome"
        assert cells.get(0) == no_effect, f"column {i + 1} No Effect cell"
        assert cells.get(1) == reduced, f"column {i + 1} Reduced cell"


def test_the_41_5_fortification_row_is_transcribed():
    cols = logistics_data.fortification_bombardment_crt_41_5()
    assert len(cols) == 11, "the [41.5] table prints ELEVEN result columns"
    # the Key (PDF p.108, verbatim): "Fortification: Reduced one Level or not affected."
    # TWO outcomes, and no cell of this row ever takes two levels.
    assert {e["reduced"] for c in cols for e in c["results"]} == {0, 1}


def test_every_column_partitions_all_36_sequential_codes_exactly_once():
    # the same self-check data/logistics_rates.json already applies to the Ports row: a misread
    # cell breaks the partition. 35+1, 33+3, 30+6, 26+10, 21+15, 15+21, 10+26, 6+30, 3+33, 1+35, 0+36.
    for i, col in enumerate(logistics_data.fortification_bombardment_crt_41_5()):
        hits = [c for c in CODES
                for e in col["results"] if e["die"][0] <= c <= e["die"][1]]
        assert sorted(hits) == CODES, f"column {i} does not partition the 36 codes"


def test_the_two_index_scales_ride_the_same_eleven_columns():
    # [41.5] prints three parallel index scales over ONE set of result columns. Artillery enters on
    # Barrage Points (12.53), air on Bomb Points (41.3/41.37) -- and they must land on the SAME row.
    cols = logistics_data.fortification_bombardment_crt_41_5()
    assert [c["barrage_points"] for c in cols][:3] == [[1, 2], [3, 4], [5, 6]]
    assert [c["bomb_points"] for c in cols][:3] == [[1, 20], [21, 40], [41, 80]]
    assert cols[-1]["barrage_points"] == [21, None] and cols[-1]["bomb_points"] == [471, None]


def test_the_barrage_points_scale_misprint_is_recorded_as_named_errata_not_applied_silently():
    # THE 1979 INK (600 dpi, and re-read at 300 dpi for this slice) prints only TEN cells on the
    # Barrage-Points scale of an ELEVEN-column table: "7,89,10" run together under the 81..120
    # column, and a final "1+" under 391..470 with 471+ left blank. "1+" is impossible when band 1
    # already reads "1,2". We regularise it -- and we say so, in the file, the way the 54.17
    # demolition misprint is recorded. Never silently.
    err = logistics_data.fortification_bombardment_errata_41_5()
    assert "printed_1979" in err and "corrected" in err
    assert err["printed_1979"][3] == "7,89,10"      # the two cells the compositor ran together
    assert err["printed_1979"][-1] == "1+"          # ...and the "2" it dropped off the last band
    assert err["corrected"][3] == "7,8" and err["corrected"][-1] == "21+"


def test_the_artillery_scale_reads_actual_barrage_points():
    # [12.53]: a facility barrage refers to "the Artillery Barrage Points column" -- ACTUAL points,
    # which [12.54] confirms by explicitly switching to RAW for dumps and air facilities alone.
    # 9 Actual points is column 5 (9,10): Reduced on 44..66 = 15 of 36.
    hits = sum(fortifications.reduced_by_barrage(9, c // 10, c % 10) for c in CODES)
    assert hits == 15
    assert fortifications.reduced_by_barrage(9, 4, 3) == 0     # 43 -- No Effect
    assert fortifications.reduced_by_barrage(9, 4, 4) == 1     # 44 -- Reduced
    # and the invented certainty is gone: at 5 Actual points (column 3) it is 6 of 36, not 36 of 36.
    assert sum(fortifications.reduced_by_barrage(5, c // 10, c % 10) for c in CODES) == 6


def test_the_air_scale_reads_bomb_points():
    # [41.3]: "All Land Support bombing missions except 'mining harbors' are resolved using the Air
    # Bombardment and Secondary Barrage Target Combat Results Table (41.5)." Bomb Points, not
    # Barrage Points -- 9 BOMB points is the FIRST column (1..20), 1 of 36, not the fifth.
    assert sum(fortifications.reduced_by_bombing(9, c // 10, c % 10) for c in CODES) == 1
    assert sum(fortifications.reduced_by_bombing(500, c // 10, c % 10) for c in CODES) == 36


def test_points_below_the_table_floor_find_no_column():
    assert fortifications.reduced_by_barrage(0, 6, 6) == 0
    assert fortifications.reduced_by_bombing(0, 6, 6) == 0


# --------------------------------------------------------------------------------------------
# 2. THE GATE IS GONE
# --------------------------------------------------------------------------------------------

def test_no_scenario_flag_survives_anywhere_in_the_state():
    # Section 25 carries no scenario condition, so nothing in GameState may carry one either.
    # If this ever comes back it will come back as a field, and this is the tripwire.
    assert not hasattr(rommels_arrival(), "siege_rules")


# --------------------------------------------------------------------------------------------
# 3. THE ARTILLERY CHANNEL -- a DESIGNATED facility target ([12.51]/[12.52]/[12.53])
# --------------------------------------------------------------------------------------------

def _works_state(*, fort: int = 2, atk_barrage: int = 26, garrison: bool = True,
                 ammo: int = 200, control: dict | None = None,
                 fort_levels: dict | None = None) -> GameState:
    """Axis artillery in (0,0), an Allied-held Level-`fort` Major City in (1,0).

    atk_barrage=26 x TOE 8 = 208 RAW -> 21 ACTUAL Barrage Points -> the [41.5] 21+ column, where
    every one of the 36 sequential codes reads "Reduced" -- so the wall comes down on any die and
    the test is seed-independent. Drop atk_barrage to 2 for the 2-Actual-point column, where only
    a 66 reduces, and the same battery mostly misses."""
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.MAJOR_CITY}
    arty = Unit("AR", Side.AXIS, (0, 0), (StepRecord("ar", 8),), mobility=Mobility.MOTORIZED,
                cpa=20, stacking_points=1, oca=0, dca=1, barrage=atk_barrage, vulnerability=5)
    units = [arty]
    if garrison:
        units.append(Unit("GAR", Side.ALLIED, (1, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
                          cpa=10, stacking_points=2, oca=5, dca=8, is_garrison_home=True))
    dump = SupplyUnit("D", Side.AXIS, (0, 0), ammo=ammo, fuel=60)
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={(1, 0): fort}),
        control=dict(control if control is not None else {(1, 0): Control.ALLIED}),
        units=tuple(units), target_hex=(1, 0), supplies=(dump,),
        consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": ammo, "FUEL": 60},
        fort_levels=dict(fort_levels or {}))


def _fire(state: GameState) -> _Run:
    r = _Run(state)
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
    return r


def _kinds(r: _Run, kind) -> list:
    return [e for e in r.events if e.kind == kind]


def test_a_gun_beside_an_enemy_fortification_designates_the_works_and_not_the_garrison():
    # [12.51] "rather than actual units" -- the gun fires ONE barrage, and it is at the wall.
    r = _fire(_works_state())
    assert _kinds(r, EventKind.FORT_BARRAGED), "the battery never declared a facility barrage"
    assert not _kinds(r, EventKind.BARRAGE_RESOLVED), \
        "[12.51] is exclusive: a gun that barrages the works does not also barrage the garrison"
    assert r.state.fort_level((1, 0)) == 1


def test_the_facility_barrage_is_rolled_on_41_5_and_can_miss():
    # THE POINT OF THE SLICE. At 2 Actual Barrage Points the chart reduces on 66 alone; the old
    # BARRAGE_HITS_PER_FORT_LEVEL=1 reduced on every effective barrage, with certainty.
    r = _fire(_works_state(atk_barrage=2))
    fired = _kinds(r, EventKind.FORT_BARRAGED)
    assert fired, "a barrage that MISSES must still be on the record (the dice are certified)"
    assert fired[0].payload["actual"] == 2
    assert len(fired[0].rng_draws) == 2, "the [41.5] roll must be certified in the log"
    # THE ENGINE'S ANSWER MUST BE THE CHART'S ANSWER FOR THE DICE IT ACTUALLY DREW. Asserting only
    # "a level came off" cannot tell the chart apart from the certainty it replaced, because the old
    # constant also took a level; this cross-check is what makes the substitution detectable.
    d1, d2 = fired[0].rng_draws
    assert fired[0].payload["reduced"] == fortifications.reduced_by_barrage(2, d1, d2)
    if fired[0].payload["reduced"] == 0:
        assert not _kinds(r, EventKind.FORT_REDUCED)
        assert r.state.fort_level((1, 0)) == 2      # the wall stood


def test_a_light_battery_really_does_miss_most_of_the_time():
    # the distribution, driven through the whole engine rather than asserted on the chart alone: a
    # 2-Actual-point battery reduces on 1 of 36 codes, so over thirty seeds the wall mostly stands.
    from dataclasses import replace as _replace
    outcomes = [_fire(_replace(_works_state(atk_barrage=2), seed=s))
                    .state.fort_level((1, 0)) for s in range(1, 31)]
    assert outcomes.count(2) > outcomes.count(1), \
        "a 2-point barrage that flattens walls more often than not is not reading [41.5]"


def test_12_31_an_empty_enemy_fortification_may_be_barraged():
    # [12.31] "Artillery units may not Barrage non-occupied hexes (however, see Case 12.5)."
    # The old side-effect model required an enemy UNIT in the hex, so this could never fire.
    r = _fire(_works_state(garrison=False))
    assert _kinds(r, EventKind.FORT_BARRAGED)
    assert r.state.fort_level((1, 0)) == 1


def test_a_gun_that_cannot_pay_its_ammunition_does_not_batter_the_wall():
    # [12.52] "follows all the rules of normal Barrage" -- including 50.12/50.15: no ammunition in
    # the hex, no barrage. (barrage costs 4 x TOE = 32; the dump holds 4.)
    r = _fire(_works_state(ammo=4))
    assert not _kinds(r, EventKind.FORT_BARRAGED)
    assert r.state.fort_level((1, 0)) == 2


def test_a_gun_never_batters_its_own_works():
    r = _fire(_works_state(control={(1, 0): Control.AXIS}, garrison=False))
    assert not _kinds(r, EventKind.FORT_BARRAGED)
    assert r.state.fort_level((1, 0)) == 2


def test_a_gun_never_batters_its_own_works_even_with_the_enemy_standing_in_them():
    # THE CASE THAT MAKES THE OWNERSHIP TEST LOAD-BEARING ON ITS OWN, and it is a real board state
    # rather than a contrivance: [15.82] never evicts a garrison from a Major City, so an enemy stack
    # can sit in a hex whose control record is still mine. Without a separate ownership test the
    # "must be enemy-held" test would wave this through on the strength of the occupants -- and my
    # own guns would be knocking down my own walls for the enemy sitting behind them.
    r = _fire(_works_state(control={(1, 0): Control.AXIS}))       # garrison present, hex is MINE
    assert not _kinds(r, EventKind.FORT_BARRAGED)
    assert r.state.fort_level((1, 0)) == 2
    s = _works_state(control={(1, 0): Control.AXIS})
    assert fortifications.barrage_target(s, s.unit("AR"), Side.AXIS) is None


def test_the_battery_reverts_to_the_garrison_once_the_wall_is_flat():
    # [25.16] takes a fortification "to a Fortification Level of zero" and no further, so at zero
    # there is nothing left to batter and the guns go back to shelling the men. Self-limiting, with
    # no knob. (This comment used to say "below Level One", the reading the module docstring records
    # as a paraphrase that shipped inside quotation marks; the book never contemplates below.)
    r = _fire(_works_state(fort_levels={(1, 0): 0}))
    assert not _kinds(r, EventKind.FORT_BARRAGED)
    assert _kinds(r, EventKind.BARRAGE_RESOLVED)


def test_barrage_never_evicts_the_garrison():
    # [15.82] is FAITHFUL and is not what this slice touches. Flattening the works removes the
    # [8.37] close-assault shift; it does not move the garrison, and it never touches the static map.
    r = _fire(_works_state())
    assert r.state.unit("GAR").hex == (1, 0)
    assert not _kinds(r, EventKind.UNIT_RETREATED)
    assert r.state.terrain.fortifications[(1, 0)] == 2       # the printed map is sacred


def test_the_wall_floors_at_zero():
    r = _fire(_works_state(fort=1))
    assert r.state.fort_level((1, 0)) == 0
    r2 = _fire(_works_state(fort=1, fort_levels={(1, 0): 0}))
    assert not _kinds(r2, EventKind.FORT_REDUCED)


def test_a_gun_shelling_the_works_pays_the_same_combat_cp_as_one_shelling_the_men():
    # [12.52] "Barrage against Facilities follows ALL the rules of normal Barrage" and [6.3] is one
    # of them: a unit that barrages pays its combat CP once per Combat Segment. _barrage_step's own
    # docstring makes "pays the same ammunition and the same combat CP either way" load-bearing --
    # the ammunition half is pinned by test_a_gun_that_cannot_pay_its_ammunition..., and this is the
    # CP half, which had nothing on it. The Axis is phasing here, so the charge is the 5-CP Assault.
    r = _fire(_works_state())
    cp = [e for e in r.events
          if e.kind == EventKind.CP_EXPENDED and e.payload["unit_id"] == "AR"]
    assert len(cp) == 1, "a facility barrage must be billed its 6.3 combat CP exactly once"
    assert cp[0].payload["activity"] == "assault"
    assert r.state.unit("AR").cp_used == cp[0].payload["cp"] > 0
    # and it is the SAME bill the unit barrage pays: the same gun, the same segment, no wall.
    men = _fire(_works_state(fort_levels={(1, 0): 0}))
    men_cp = [e for e in men.events
              if e.kind == EventKind.CP_EXPENDED and e.payload["unit_id"] == "AR"]
    assert [e.payload["cp"] for e in men_cp] == [cp[0].payload["cp"]]


def test_the_points_fired_at_the_works_are_credited_to_the_10_34_holding_off_ledger():
    """The FLAGGED JUDGEMENT CALL in engine._barrage_step, and it has teeth.

    `held_off` is what discharges the [10.31] mandatory-attack obligation in _mandatory_attack, and
    a hex that receives no points can cost its would-be attacker a three-hex retreat or the whole
    stack under [10.36]. So a battery that switched from the men to the wall must not silently drop
    the obligation it had. The reading is the Note at the end of [12.0]'s PROCEDURE (PDF p.20):
    "Holding-off" Barrages are resolved in the same fashion as normal Barrage (see Case 10.3).
    The book does not settle whether shelling the works holds off the men; this pins the reading
    the engine actually took, so that changing it is a decision and not an accident."""
    r = _Run(_works_state())
    held: dict = {}
    _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set(), held_off=held)
    fired = _kinds(r, EventKind.FORT_BARRAGED)
    assert held == {(1, 0): fired[0].payload["actual"]} and held[(1, 0)] > 0
    # the NON-phasing side's facility barrage is not credited (10.34 is the phasing player's beat).
    r2 = _Run(_works_state())
    held2: dict = {}
    _barrage_step(r2, Side.ALLIED, Side.AXIS, set(), set(), held_off=held2)
    assert held2 == {}


def test_only_one_side_can_ever_designate_the_same_works():
    """WHY engine._batter_fort NEEDS NO `level <= 0` FLOOR GUARD, asserted rather than asserted-in-
    a-comment. A works hex enters fort_plan at most once per side, and the ownership and enemy-held
    tests cannot both pass for both sides of the same hex: whoever controls it is refused by the
    ownership test, and a NEUTRAL fortification can only be "enemy-held" for the side whose enemy is
    standing in it. So `level` is >= 1 (barrage_target already refused 0) whenever a reduction is
    emitted, and the wall cannot be taken below zero by this path.

    The one board state that would break the argument -- BOTH sides' units in one neutral fortified
    hex -- is not a legal position in this engine, and building it here to prove the point would be
    testing an illegal state rather than the rule."""
    axis_gun = _works_state().unit("AR")
    allied_gun = replace(axis_gun, id="AL-GUN", side=Side.ALLIED)
    for control in ({(1, 0): Control.ALLIED}, {(1, 0): Control.AXIS}, {}):
        s = _works_state(control=control)
        picks = [fortifications.barrage_target(s, axis_gun, Side.AXIS),
                 fortifications.barrage_target(s, allied_gun, Side.ALLIED)]
        assert picks.count((1, 0)) <= 1, f"both sides designated the same works under {control}"


# --------------------------------------------------------------------------------------------
# 4. THE DOCTRINE SEAM (flagged: an opinion a commander may hold, not a law of the world)
# --------------------------------------------------------------------------------------------

def test_the_doctrine_picks_an_enemy_held_fortification_and_nothing_else():
    s = _works_state()
    gun = s.unit("AR")
    assert fortifications.barrage_target(s, gun, Side.AXIS) == (1, 0)
    # a hex the firer controls is not a target...
    own = _works_state(control={(1, 0): Control.AXIS}, garrison=False)
    assert fortifications.barrage_target(own, own.unit("AR"), Side.AXIS) is None
    # ...nor is an unfortified one...
    flat = _works_state(fort_levels={(1, 0): 0})
    assert fortifications.barrage_target(flat, flat.unit("AR"), Side.AXIS) is None
    # ...nor a NEUTRAL fortification with nobody in it (nobody is defending it).
    empty = _works_state(garrison=False, control={})
    assert fortifications.barrage_target(empty, empty.unit("AR"), Side.AXIS) is None


def test_a_neutral_fortification_an_enemy_stands_in_is_an_enemy_fortification():
    held = _works_state(control={})            # no control record, but the garrison is in it
    assert fortifications.barrage_target(held, held.unit("AR"), Side.AXIS) == (1, 0)


# --------------------------------------------------------------------------------------------
# 5. THE AIR CHANNEL -- [41.37] B-F/C, which now ROLLS
# --------------------------------------------------------------------------------------------

def _bomb_state(*, fort: int = 3, strike: int = 500, control: dict | None = None,
                missions=None) -> GameState:
    """An Axis LAND air wing tasked against an Allied Level-`fort` Major City at (1,0).

    strike=500 Bomb Points is the [41.5] 471+ column, where every one of the 36 codes reads
    "Reduced" -- deterministic. strike=6 is the 1..20 column, where only a 66 does."""
    from game.state import AirMission, AirWing
    wing = AirWing("LW", Side.AXIS, "LAND", fighters=9, strike=strike, recon=3)
    if missions is None:
        missions = (AirMission(Side.AXIS, "fort", (1, 0), 1),)
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR, (1, 0): Terrain.MAJOR_CITY},
                           fortifications={(1, 0): fort}),
        control=dict(control if control is not None else {(1, 0): Control.ALLIED}),
        units=(), target_hex=(1, 0), supplies=(), consumed={}, initial_supply={},
        air=(wing,), air_missions=tuple(missions))


def _bomb(state: GameState) -> _Run:
    from game.engine import _air_support
    r = _Run(state)
    _air_support(r, Policy(), Side.AXIS, set())
    return r


def test_bombing_a_fortification_rolls_on_41_5_and_is_certified_in_the_log():
    # [41.37] "IF THE PLAYER OBTAINS A RESULT that would reduce the fortification level by one..."
    # -- a die. This resolver used to emit FORT_REDUCED unconditionally, the only [41.5] land-bombing
    # resolver in the engine that never consulted the chart, while its own sibling _air_port rolled
    # the Ports row of that same table correctly.
    r = _bomb(_bomb_state())
    rolls = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED
             and e.payload["arena"] == "FORT"]
    assert len(rolls) == 1 and len(rolls[0].rng_draws) == 2
    assert rolls[0].payload["levels"] == 1                # 471+ column: every code reduces
    assert r.state.fort_level((1, 0)) == 2


def test_a_bombing_mission_that_misses_leaves_the_wall_standing_and_still_records_its_dice():
    r = _bomb(_bomb_state(strike=6))                      # column 1..20: reduced on 66 alone
    rolls = [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED
             and e.payload["arena"] == "FORT"]
    assert len(rolls) == 1 and len(rolls[0].rng_draws) == 2
    # the same cross-check the artillery channel gets: the engine's answer must BE the chart's
    # answer for the dice it drew, which is what distinguishes a chart from a constant.
    d1, d2 = rolls[0].rng_draws
    assert rolls[0].payload["levels"] == fortifications.reduced_by_bombing(6, d1, d2)
    if rolls[0].payload["levels"] == 0:
        assert not _kinds(r, EventKind.FORT_REDUCED)
        assert r.state.fort_level((1, 0)) == 3


def test_a_weak_bombing_campaign_really_does_miss_most_of_the_time():
    from dataclasses import replace as _replace
    outcomes = [_bomb(_replace(_bomb_state(strike=6), seed=s)).state.fort_level((1, 0))
                for s in range(1, 31)]
    assert outcomes.count(3) > outcomes.count(2), \
        "six Bomb Points that flatten walls more often than not are not reading [41.5]"


def test_41_37_only_one_level_of_fortification_per_operations_stage():
    # "Only one level of fortification may be destroyed in any Operations Stage." Two B-F/C missions
    # against the same works in one stage take ONE level between them, not two.
    from game.state import AirMission
    twice = (AirMission(Side.AXIS, "fort", (1, 0), 1), AirMission(Side.AXIS, "fort", (1, 0), 1))
    r = _bomb(_bomb_state(missions=twice))
    assert len(_kinds(r, EventKind.FORT_REDUCED)) == 1
    assert r.state.fort_level((1, 0)) == 2


def test_bombing_never_batters_your_own_works():
    r = _bomb(_bomb_state(control={(1, 0): Control.AXIS}))
    assert not _kinds(r, EventKind.FORT_REDUCED)
    assert r.state.fort_level((1, 0)) == 3


def test_39_11_a_sortie_over_an_unfortified_hex_takes_no_level_and_leaves_no_negative_wall():
    """_air_fort's `if r.state.fort_level(tgt) <= 0: return` is LOAD-BEARING and had nothing on it.

    [39.0] flies the mission blind -- the crews "only find out what target are present when the
    planes arrive" -- so arriving over a hex with no works is a real, billed sortie and not a
    refusal to order one (test_air_fuel pins the billing). What the guard prevents is the step
    after: at 500 Bomb Points every one of the 36 codes reads "Reduced", so without it the resolver
    emits FORT_REDUCED with a level of -1 and invariants._check_fort raises. Neutering the guard
    passed every test in the suite, including the blind-sortie test that flies exactly this
    mission, and the 25.14 slice now rolls a die behind it where it previously did not."""
    r = _bomb(_bomb_state(fort=0, strike=500))
    assert not _kinds(r, EventKind.FORT_REDUCED)
    assert r.state.fort_level((1, 0)) == 0
    assert not [e for e in r.events if e.kind == EventKind.AIR_STRIKE_RESOLVED
                and e.payload.get("arena") == "FORT"], \
        "no fortification, no [41.5] roll -- the chart has no row for a hex with no works"


def test_41_37_the_per_stage_cap_is_cleared_at_the_operations_stage_boundary():
    """[41.37] caps a fortification at ONE level per Operations Stage -- and an Operations Stage
    ENDS. The cap itself is pinned above; its RESET (engine.run's stage loop) was unreachable by
    every test in the suite, because no scenario and no Policy ever builds an AirMission of
    kind="fort" and every other fort test calls _air_support directly inside a single stage.
    Replacing the reset with `pass` -- a hex bombed once can never be bombed again for 111 turns --
    passed 295 tests.

    So this one goes through engine.run: ONE Game-Turn is three Operations Stages (48 V/VI/VII),
    an AirMission is due in each of them, and Tobruk's Level 2 wall comes down one level per stage
    until [25.16]'s floor stops the third. With a broken reset only the first stage bombs."""
    tobruk = coords.to_axial(coords.parse("C4807"))
    wing = AirWing("LW", Side.AXIS, "LAND", fighters=9, strike=500, recon=3)
    st = replace(rommels_arrival(seed=1941), max_turns=1, air=(wing,),
                 air_missions=(AirMission(Side.AXIS, "fort", tobruk, 1),))
    res = run(st, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    drops = [e for e in res.events
             if e.kind == EventKind.FORT_REDUCED and tuple(e.payload["hex"]) == tobruk]
    assert [e.stage for e in drops] == [1, 2], \
        "one level per Operations Stage, in successive stages -- the cap must not survive the reset"
    assert [e.payload["level"] for e in drops] == [1, 0]
    assert res.final.fort_level(tobruk) == 0
    # ...and the third stage's mission still FLEW; it found nothing left to take (25.16's floor).
    rolls = [e for e in res.events if e.kind == EventKind.AIR_STRIKE_RESOLVED
             and e.payload.get("arena") == "FORT"]
    assert [e.stage for e in rolls] == [1, 2]


def test_41_37_the_per_stage_cap_expires_by_itself_for_a_caller_that_drives_the_stages():
    """The test above proves the cap lifts inside engine.run(). This one proves it lifts for
    EVERYBODY -- because a per-Operations-Stage ledger cleared by a line inside run()'s
    `for stage in (1, 2, 3)` loop is stale for every other caller there is: a test, a measurement
    driver, or one of run()'s own Game-Turn-level beats. That shape has already shipped the same
    live bug twice (the [55.3] harbour ledger, 024d042; the [52.42] water ledger, 49b00f2), and the
    fix both times was engine._OpStageLedger, which expires on its own (turn, stage) stamp.

    So: ONE _Run, two Operations Stages driven by hand, STAGE_ADVANCED between them and nothing
    else. Against the reset-in-the-loop shape the second mission is refused by a cap that was set
    in Stage 1 and never lifted, and Tobruk's wall can be battered ONCE PER WAR."""
    from game.engine import _air_support
    r = _Run(_bomb_state(fort=2))
    _air_support(r, Policy(), Side.AXIS, set())                     # Operations Stage 1: one level (41.37)
    assert r.state.fort_level((1, 0)) == 1
    r.emit(EventKind.STAGE_ADVANCED, Side.SYSTEM, "SYSTEM", {"stage": 2})
    _air_support(r, Policy(), Side.AXIS, set())                     # Operations Stage 2: the NEXT level
    assert r.state.fort_level((1, 0)) == 0, \
        "the cap is one level per Operations Stage, not one level per run"
    assert [e.stage for e in _kinds(r, EventKind.FORT_REDUCED)] == [1, 2]


def test_air_and_artillery_read_the_same_row_and_mean_the_same_level():
    # [25.14] names two channels into one chart. A wall opened by bombs is as open as one opened by
    # guns -- both emit FORT_REDUCED, both fold into fort_levels, and neither can take two at once.
    by_air = _bomb(_bomb_state(fort=2))
    by_gun = _fire(_works_state(fort=2))
    assert by_air.state.fort_level((1, 0)) == by_gun.state.fort_level((1, 0)) == 1


# --------------------------------------------------------------------------------------------
# 6. DETERMINISM
# --------------------------------------------------------------------------------------------

def test_the_facility_barrage_draws_its_own_subsystem_stream():
    # game/dice.py's whole thesis: a die drawn in one subsystem must never move another's. The
    # [41.5] facility roll is a different chart read by a different procedure from the [12.6]
    # unit barrage, so it gets its own stream and cannot re-index the unit barrages.
    from game.dice import SUBSYSTEMS
    assert "fort_barrage" in SUBSYSTEMS


def _two_front_state(*, wall: bool) -> GameState:
    """TWO barrages in one Barrage Step, far apart and independent of each other.

    (0,0) Axis gun + Axis dump, beside an Allied-held Level-2 Major City at (1,0) with NOBODY in
    it -- a pure [12.5] facility barrage, and when `wall` is False the wall is already flat so that
    gun fires NOTHING at all (no adjacent enemy unit to fall back on).
    (10,0) Allied gun + Allied dump, beside an Axis infantry battalion at (11,0) -- a pure [12.6]
    unit barrage, on the far side of the map, in the OTHER side's portion of the same step."""
    terr = {(0, 0): Terrain.CLEAR, (1, 0): Terrain.MAJOR_CITY,
            (10, 0): Terrain.CLEAR, (11, 0): Terrain.CLEAR}
    ax_gun = Unit("AX-GUN", Side.AXIS, (0, 0), (StepRecord("ar", 8),), mobility=Mobility.MOTORIZED,
                  cpa=20, stacking_points=1, oca=0, dca=1, barrage=26, vulnerability=5)
    al_gun = Unit("AL-GUN", Side.ALLIED, (10, 0), (StepRecord("ar", 8),),
                  mobility=Mobility.MOTORIZED, cpa=20, stacking_points=1, oca=0, dca=1,
                  barrage=26, vulnerability=5)
    ax_inf = Unit("AX-INF", Side.AXIS, (11, 0), (StepRecord("in", 6),), mobility=Mobility.FOOT,
                  cpa=10, stacking_points=2, oca=5, dca=8)
    return GameState(
        turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=3,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terr, fortifications={(1, 0): 2}),
        control={(1, 0): Control.ALLIED},
        units=(ax_gun, al_gun, ax_inf), target_hex=(1, 0),
        supplies=(SupplyUnit("AX-D", Side.AXIS, (0, 0), ammo=200, fuel=60),
                  SupplyUnit("AL-D", Side.ALLIED, (10, 0), ammo=200, fuel=60)),
        consumed={"AMMO": 0, "FUEL": 0}, initial_supply={"AMMO": 400, "FUEL": 120},
        fort_levels={} if wall else {(1, 0): 0})


def test_a_facility_roll_never_re_indexes_a_unit_barrage_on_the_other_side_of_the_map():
    """THE CALL SITE, not the roster. `assert "fort_barrage" in SUBSYSTEMS` proves the stream
    EXISTS; it does not prove engine._barrage_step draws from it, and swapping the facility roll
    back to r.d6("barrage") -- which re-indexes every unit barrage in the war, the exact bug class
    CLAUDE.md says game/dice.py exists to kill -- passed the whole suite.

    The two draws are ordered so the swap would bite: the PHASING side's facility barrage resolves
    before the NON-PHASING side's unit barrage in the same step. Fire an Allied battery at an Axis
    battalion with and without an Axis facility barrage happening first, and its dice must be the
    same dice both times."""
    dice = []
    for wall in (True, False):
        r = _Run(_two_front_state(wall=wall))
        _barrage_step(r, Side.AXIS, Side.ALLIED, set(), set())
        assert bool(_kinds(r, EventKind.FORT_BARRAGED)) is wall, \
            "the facility barrage must fire in exactly one of the two arms, or nothing is compared"
        unit_barrages = [e for e in r.events if e.kind == EventKind.BARRAGE_RESOLVED]
        assert len(unit_barrages) == 1 and unit_barrages[0].payload["target"] == [11, 0]
        dice.append(unit_barrages[0].rng_draws)
    assert dice[0] == dice[1], (
        f"the [12.6] unit barrage saw {dice[0]} with a facility barrage and {dice[1]} without: "
        "the [41.5] facility roll is drawing from the unit-barrage stream")


def test_the_benchmark_replays_byte_identically():
    a = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert fold(a.initial, a.events) == a.final
