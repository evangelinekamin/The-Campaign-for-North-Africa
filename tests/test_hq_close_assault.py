"""[4.46] THE HEADQUARTERS ROW PRINTS A DASH, AND THE DASH IS NOT A ONE.

data/unit_stats.json gave GE.hq, CW.hq and CW.hq_engineer a Close Assault Defence of 1 while
citing chart row 'a'. That 1 is not on any chart. All three [4.46] Unit Characteristics Charts
were re-rendered at 300 dpi for this file and read cell by cell:

  German [4.46c], PDF p.137 (folio 137), row a -- "Headquarters | a | 60" and then a DASH in
  every one of the seven rating columns: Anti-Air, Barrage, Anti-Armor, Vulnerability, Armor
  Prtctn, Close Assault Off/Def, Maximum TOE. Row "b*" is the same shape at CPA 30.

  Commonwealth [4.46a], PDF p.133 (folio 133), row a -- "Headquarters | a | 30", dashes in the
  same seven columns. (Row b, CPA "30*", dashes the ratings too but carries a continuation line,
  "may assign one tank TOE Strength Point", and a Maximum TOE of "(1)".)

THE DASH IN MAXIMUM TOE IS WHAT MAKES ROW 'a' UNAMBIGUOUS, and it is why this is a transcription
error rather than a TOE placeholder. The charts' own key, read off the same render (p.137):

    "- = Not applicable (e.g., an infantry unit has no Vulnerability and may therefore not be
     harmed by Anti-Armor fire)."

Row a can never contain a TOE Strength Point, so no rating can come into existence for it. It is
the counter [3.36] calls an "HQ unit that has no combat values, either with or without
parentheses" -- and the book's own target-class list on the same folio 6 proves the distinction is
deliberate: "Infantry-class: All Infantry-Type, Engineers, Headquarters possessing a defensive
Close Assault Rating but not possessing an Armor Protection Rating, SGSU, and Recce-Type that do
not possess an Armor Protection Rating." There ARE HQs that possess one -- the parenthesized rows,
German "e*" and Italian "b", both 0/(1) -- and row 'a' is the other kind.

WHAT A DASH MEANS FOR A UNIT IN THE DEFENDER LIST -- decided from the scan, not from convenience.
The counter is NOT barred from Close Assault. [15.11], PDF p.22 (folio 22), verbatim:

    "[15.11] All units which possess a Close Assault Rating may use their ratings to aid in either
     Offensive Assault or Defense Against Assault. (Units without Ratings may also participate,
     even though they add nothing to the point total; see Case 15.17.)"

It defends at ZERO, and 15.11's own cross-reference carries the rest. [15.17]: "Such units do not
include their TOE Strength for determining losses when they occupy a hex with combat units unless
the "losing" Player so wishes. In such a case, units with parenthesized ratings may be used to
absorb losses but may not absorb more than 25% of such losses." So it is in the stack, it takes
the stack's retreat, and it is neither in the casualty pool nor able to shed a step for it.

ONE HALF OF 15.17 IS NOT BUILT AND IS FLAGGED RATHER THAN FAKED: the "unless the 'losing' Player
so wishes" ELECTION, by which an owner may volunteer such a counter to soak up to 25% of a loss.
engine._absorb_losses simply skips a 0-rated unit, so the election is never offered. That is the
narrower reading (the counter survives where the book would let its owner spend it) and it is the
engine's pre-existing shape for every 0-rated counter, not something this transcription chose.

AND WHEN ITS STACK IS GONE, the book collects it where it stands -- [3.36], PDF p.6 (folio 6):

    "An HQ unit that has no combat values, either with or without parentheses, is captured
     instantly if it is in a hex without any combat units and an Enemy combat unit places the HQ
     in its Zone of Control. There is no Capability Point expenditure required for such a capture,
     and the HQ is treated as one Prisoner Point."

THE ENGINE ALREADY BUILDS THAT, and this file is the other half of it. The [10.29] slice
(engine._capture_noncombat) landed the wider clause -- "If such a unit is alone in an Enemy ZOC at
any time during the Enemy Movement/Combat Phase and it has no strength of any type, such Friendly
non-combat unit is Captured" (PDF p.18 = folio 18) -- and recorded in its own docstring, in
tests/baselines.py and in tests/test_noncombat_capture.py that 3.36's POPULATION WAS EMPTY because
of exactly this invented 1, and that "THE TWO CHANGES ARE COUPLED". Transcribing the dash fills
that population. Nothing in engine.py changes: every consequence below is a rule the engine
already encodes, reading a rating that is finally the chart's.

THE ITALIAN ROWS ARE DELIBERATELY UNTOUCHED, and the second test below pins that so a later sweep
cannot "finish the job" by inventing. IT.hq claims ID 'a', but Italian
[4.46b] (PDF p.136) row a* prints CPA 45 while the engine writes 30 -- which is row b -- and row b
prints Close Assault Off/Def "0/(1)", NOT a dash. Writing a 0 there would be transcribing a row
this repo has not identified. The IT block's own _comment already flags the whole block unverified.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import supply                                            # noqa: E402
from game.engine import (_absorb_losses, _capture_noncombat, _def_raw,   # noqa: E402
                         _has_no_strength, _resolve_combat, _Run)
from game.events import EventKind, Phase, Side                     # noqa: E402
from game.movement import TerrainMap                               # noqa: E402
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP  # noqa: E402
from game.terrain import Mobility, Terrain                         # noqa: E402

STATS = json.loads((Path(__file__).resolve().parent.parent / "data" / "unit_stats.json").read_text())

# The three rows [4.46] prints as row 'a' -- German p.137, Commonwealth p.133 (and the CW HQ^E,
# which [23.14] puts on the same row: "Headquarters units with a letter E next to their Stacking
# Points have Engineering capability (see Section 24.0) but otherwise they are treated like any
# other HQ unit." -- PDF p.36 = folio 36, re-rendered and read for this file).
DASH_ROWS = (("GE", "hq"), ("CW", "hq"), ("CW", "hq_engineer"))


# --- the chart ------------------------------------------------------------------------------

def test_the_4_46_headquarters_row_prints_a_dash_in_close_assault_not_a_one():
    # Off/Def are both dashes. `oca` was already 0; `dca` was the invented 1.
    for nat, role in DASH_ROWS:
        row = STATS[nat][role]
        assert row["type"] == "a", f"{nat}.{role} no longer cites chart row 'a'"
        assert row["oca"] == 0, f"{nat}.{role} offensive close assault is a DASH on [4.46]"
        assert row["dca"] == 0, f"{nat}.{role} defensive close assault is a DASH on [4.46]"


def test_the_italian_hq_rows_are_left_alone_because_a_zero_there_would_be_invented():
    # Italian [4.46b] row a* prints CPA 45; the engine writes 30, which is row b; and row b prints
    # "0/(1)", not a dash. Until an Italian HQ ID Code is actually transcribed there is no chart
    # row to copy, so these keep the rating they have and the file says why.
    for role in ("hq", "hq_engineer"):
        assert STATS["IT"][role]["dca"] == 1
    assert "45" in STATS["IT"]["_hq_dash_comment"]          # the CPA that proves it is not row a
    assert "0/(1)" in STATS["IT"]["_hq_dash_comment"]       # the rating row b actually prints


# --- what the dash does, rule by rule -------------------------------------------------------

def _hq(uid, side, hx, nat="CW", role="hq") -> Unit:
    """A bare HQ built from the data file's own row, so this binds the transcription."""
    s = STATS[nat][role]
    return Unit(uid, side, hx, (StepRecord("hq", s["steps"]),), mobility=Mobility[s["mobility"]],
                cpa=s["cpa"], stacking_points=s["sp"], oca=s["oca"], dca=s["dca"],
                is_combat=s["is_combat"], morale=0, cohesion=0)


def _bn(uid, side, hx, *, oca=3, dca=3, steps=6) -> Unit:
    return Unit(uid, side, hx, (StepRecord("in", steps),), mobility=Mobility.FOOT,
                cpa=10, stacking_points=1, oca=oca, dca=dca, morale=1, cohesion=0)


def _div(uid, side, hx) -> Unit:
    """A division that exerts a ZOC: >1 Stacking Point (10.11), >=10 raw defence (10.15)."""
    return Unit(uid, side, hx, (StepRecord("in", 4),), mobility=Mobility.FOOT,
                cpa=30, stacking_points=5, oca=6, dca=8, fuel=500)


LINE = ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0))
TARGET, FROM = (2, 0), (3, 0)     # a target with room BEHIND it, so a 15.75 retreat is not a kill


def _state(units, supplies=(), *, seed=1) -> GameState:
    return GameState(turn=1, max_turns=4, phase=Phase.COMBAT, active_side=Side.AXIS, seed=seed,
                     weather="clear", vp=VP(),
                     terrain=TerrainMap(terrain={c: Terrain.CLEAR for c in LINE}),
                     control={}, units=tuple(units), target_hex=TARGET, supplies=tuple(supplies),
                     consumed={c: 0 for c in supply.COMMODITIES},
                     initial_supply={c: sum(getattr(u, c.lower(), 0) for u in (*units, *supplies))
                                     for c in supply.COMMODITIES})


def test_15_11_a_bare_hq_adds_nothing_to_the_defensive_close_assault_point_total():
    # "Units without Ratings may also participate, even though they add nothing to the point
    # total" -- so its contribution to the 15.26 differential is exactly zero, not one.
    hq = _hq("AL-HQ", Side.ALLIED, (0, 0))
    assert _def_raw(hq) == 0
    assert hq.raw_defense == 0


def test_15_17_a_bare_hq_is_not_in_the_casualty_pool_and_cannot_absorb_a_step():
    # 15.17 (which 15.11 points at for units without Ratings): "Such units do not include their
    # TOE Strength for determining losses when they occupy a hex with combat units". The engine
    # computes both off the same rating, so a dash removes it from both.
    hq = _hq("AL-HQ", Side.ALLIED, (0, 0))
    assert _absorb_losses([hq], 99, lambda u: u.dca) == []       # 15.83d cannot take its step
    assert hq.raw_defense == 0                                   # nor is it in defender_loss_raw


def test_3_36_a_bare_hq_has_no_combat_values_and_10_29_can_finally_reach_it():
    # [3.36] "an HQ unit that has no combat values, either with or without parentheses"; [10.29]
    # "it has no strength of any type". The invented 1 was what kept every HQ out of this
    # population -- the coupling engine._capture_noncombat, tests/baselines.py and
    # tests/test_noncombat_capture.py all name.
    for nat, role in DASH_ROWS:
        assert _has_no_strength(_hq("X", Side.ALLIED, (0, 0), nat, role)) is True
    # ...and the Italian row, which prints a rating, still is not reached.
    assert _has_no_strength(_hq("Y", Side.ALLIED, (0, 0), "IT", "hq")) is False


def test_3_36_a_bare_hq_alone_in_an_enemy_zoc_is_captured_where_it_stands():
    # The whole point of the coupling: an Axis division at (0,0) projects a ZOC into (1,0), where a
    # Commonwealth HQ stands with no combat unit. 3.36 captures it instantly; 10.29 is the clause
    # the engine builds, and its condition is strictly wider.
    r = _Run(_state([_div("AX-DIV", Side.AXIS, (0, 0)), _hq("AL-HQ", Side.ALLIED, (1, 0))]))
    _capture_noncombat(r, Side.AXIS)
    captured = [e.payload["unit_id"] for e in r.events
                if e.kind == EventKind.STEP_LOST and e.payload.get("role") == "captured"]
    assert captured == ["AL-HQ"]
    assert not r.state.unit("AL-HQ").alive


def _assault(defenders, *, ammo=99):
    """One Close Assault on TARGET by one strong battalion from FROM, both sides supplied by a
    co-located dump. Returns the _Run so a test can read the whole event stream."""
    attacker = _bn("AX-BN", Side.AXIS, FROM, oca=8, dca=8)
    dumps = [SupplyUnit("AXD", Side.AXIS, FROM, ammo=99, fuel=0),
             SupplyUnit("ALD", Side.ALLIED, TARGET, ammo=ammo, fuel=0)]
    r = _Run(_state([attacker, *defenders], dumps))
    resolved = _resolve_combat(r, Side.AXIS, "AXIS/Front", [attacker], list(defenders),
                               TARGET, set(), set())
    return r, resolved


def test_15_11_the_bare_hq_is_not_barred_it_stands_in_the_assault_and_sheds_no_step():
    # "may also participate" -- it is NOT dropped from the defence. It is in the resolved
    # assault's defender list, it takes whatever the stack takes, and because it has no rating it
    # neither raises the differential nor pays for it with a step (15.17).
    r, ok = _assault([_bn("AL-BN", Side.ALLIED, TARGET), _hq("AL-HQ", Side.ALLIED, TARGET)])
    assert ok is True
    resolved = [e for e in r.events if e.kind == EventKind.COMBAT_RESOLVED][-1]
    assert "AL-HQ" in resolved.payload["defenders"]              # 15.11: it participated
    steps = [e.payload["unit_id"] for e in r.events if e.kind == EventKind.STEP_LOST]
    assert "AL-HQ" not in steps                                  # 15.17: it absorbs nothing
    assert r.state.unit("AL-HQ").strength == 1


def test_15_11_the_hq_does_not_change_the_differential_it_stands_in():
    # The same assault with and without the HQ in the hex, END TO END through _resolve_combat. The
    # Assault Differential (15.26) is roll-independent (combat.resolve computes it before any die
    # is read), so this is a clean A/B: a counter that "adds nothing to the point total" must
    # leave it untouched.
    #
    # THE GARRISON IS SIZED SO THAT ONE POINT MATTERS, and that is the whole point of the fixture.
    # 15.28's Actual Points are raw/10 rounded half up, so at raw 18 a spurious +1 is invisible
    # (1.8 and 1.9 both round to 2) and this test could not fail. dca 7 x 2 TOE = raw 14 sits on
    # the boundary: 1.4 rounds to 1, and the invented rating's 1.5 would round to 2 and move the
    # differential by a whole point. Verified by neuter -- see the table at the foot of this file.
    def differential(defenders):
        r, _ = _assault(defenders)
        return [e for e in r.events
                if e.kind == EventKind.COMBAT_RESOLVED][-1].payload["differential"]

    def garrison():
        return _bn("AL-BN", Side.ALLIED, TARGET, dca=7, steps=2)

    alone = differential([garrison()])
    with_hq = differential([garrison(), _hq("AL-HQ", Side.ALLIED, TARGET)])
    assert with_hq == alone


def test_flagged_the_bare_hq_still_pays_the_6_3_defence_cp_and_a_dump_ammo_round():
    # NOT A FIX -- A FLAG, RECORDED SO IT IS NOT FOLKLORE. This is what the corrected counter does
    # today and it is left alone deliberately.
    #
    # [15.11] lets a unit without Ratings "participate", so the engine keeps it in `armed_def`, and
    # membership there costs it the [6.3] defence CP (3) and one [50.14] Close-Assault ammunition
    # round. Its OWN [50.0] basic load is now 0 (test_50_0 above), so it can only pay that round
    # out of a CO-LOCATED DUMP -- which means a bare HQ's ammunition draw now depends on whether a
    # dump happens to share its hex. The book does not settle this: 15.0's General Rule says
    # "Close Assault expends ammunition for both sides", [50.14] rates ammunition per COMBAT
    # FUNCTION, and the [4.46] key calls this counter's function "Not applicable" -- so an
    # inference is required either way, and none is made here.
    #
    # IT IS ALSO PRE-EXISTING AND WIDER THAN HQs: every already-0-rated non-combat counter in
    # data/unit_stats.json (GE/CW sgsu, GE engineer, CW rr_engineer/road_engineer) has done exactly
    # this since it was seeded. Changing it is a separate slice about `armed_def` membership, on a
    # population this transcription does not own; folding it in here would also make this slice's
    # A/B unreadable. MEASURED over four full 111-turn campaigns AS SHIPPED (seeds 1941/7/4/2026):
    # 2/5/6/9 assaults per war hold a bare HQ at all, so the whole exposure is at most nine 2-point
    # dump draws in a 111-turn war -- and only in those of them that have a dump in the hex.
    r, _ = _assault([_bn("AL-BN", Side.ALLIED, TARGET), _hq("AL-HQ", Side.ALLIED, TARGET)])
    drew = [e.payload for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED
            and e.payload.get("unit_id") == "AL-HQ"]
    assert drew and drew[0]["commodity"] == supply.AMMO           # ...off the dump, not its own load
    assert not [e for e in r.events if e.kind == EventKind.UNIT_SUPPLY_CONSUMED
                and e.payload.get("unit_id") == "AL-HQ"]
    assert [e.payload["cp"] for e in r.events if e.kind == EventKind.CP_EXPENDED
            and e.payload["unit_id"] == "AL-HQ"] == [3]

    # With no dump to draw from, [15.15]'s gate drops it out of `armed_def` entirely -- so the
    # rating is the only thing keeping it in, and either way it adds nothing.
    dry, _ = _assault([_bn("AL-BN", Side.ALLIED, TARGET), _hq("AL-HQ", Side.ALLIED, TARGET)],
                      ammo=12)          # exactly one round: the battalion's, none left for the HQ
    assert not [e for e in dry.events if e.kind == EventKind.CP_EXPENDED
                and e.payload["unit_id"] == "AL-HQ"]


def test_50_0_a_counter_with_no_rating_carries_no_ammunition():
    # [50.0] "Each TOE Strength Point may carry (i.e., transport by itself without trucks) only
    # enough ammo to fire once" -- supply.ammo_capacity samples the unit's combat functions, and a
    # counter with none has nothing to fire. The invented 1 was giving every bare HQ a basic load
    # for an assault it cannot make.
    for nat, role in DASH_ROWS:
        assert supply.ammo_capacity(_hq("X", Side.ALLIED, (0, 0), nat, role)) == 0


# --- THE NEUTER TABLE ---------------------------------------------------------------------------
#
# The change is ONE DATA CELL x3 and no engine code, so the "call sites" are the READERS of that
# cell. Each was neutered in turn -- put back to reading a 0-rated non-combat counter as 1 -- and
# every test above re-run. A reader with no red test is a reader this file does not really pin.
#
#   state.Unit.raw_defense     (15.11 sum / 15.17 casualty pool)   3 RED
#   engine._def_raw            (15.11 differential)                2 RED
#   engine._absorb_losses      (15.83d / 15.17 step absorption)    1 RED
#   engine._has_no_strength    (3.36 / 10.29 population)           2 RED
#   supply.ammo_capacity       (50.0 basic load)                   1 RED
#   data/unit_stats.json cell  (the transcription itself)          7 RED
#   -> SITES WITH NO RED TEST: none
#
# IT TOOK ONE REAL REPAIR TO GET THERE, recorded because it is the failure mode this table exists
# to catch. test_15_11_the_hq_does_not_change_the_differential_it_stands_in first ran on a garrison
# of raw defence 18, where neutering _def_raw changed NOTHING: 15.28 rounds Actual Points to
# raw/10 half-up, and 1.8 and 1.9 are both 2. The test passed under its own negation. Re-sized to
# raw 14 (dca 7 x 2 TOE), the boundary where 1.4 -> 1 and the invented 1.5 -> 2, it fails under
# the neuter as it should.
#
# THREE TESTS ARE PINNED BY NO NEUTER, deliberately, because they assert something the neuters do
# not model: test_the_italian_hq_rows_are_left_alone (a cell this slice does NOT change),
# test_flagged_the_bare_hq_still_pays_the_6_3_defence_cp (behaviour left alone on purpose), and
# test_15_11_the_bare_hq_is_not_barred (corroborates end-to-end that the counter is still IN the
# assault -- the "may also participate" half, which every neuter above leaves true).
