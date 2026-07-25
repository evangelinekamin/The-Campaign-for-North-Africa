"""Rule 20 -- the Replacement economy's FLOW IN (Block 7.2a).

These tests pin the TRANSCRIPTION (data/replacements.json) and the production LOGIC
(game.replacements) against the book, and prove the Commonwealth infantry random stream
(20.78B) is deterministic and reproducible with the ~1,617 expected yield the port plan
predicts. The SPEND (a unit absorbing a Replacement Point) is Block 7.2b, not tested here.
"""
from __future__ import annotations

import statistics

import pytest

import game.supply as supply
from game import replacements
from game.apply import apply
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.dice import DiceBox, stream_seed
from game.engine import _Run, _replacement_production, run
from game.events import Event, EventKind, Phase, Side, event_to_dict
from game.movement import TerrainMap
from game.scenario import campaign, rommels_arrival, siege_of_tobruk
from game.state import GameState, SupplyUnit, VP
from game.terrain import Terrain


# --- [20.78B] the Commonwealth infantry PRODUCTION STREAM -------------------------------

def test_cw_infantry_table_cells_match_the_scan():
    """Spot-check cells straight off the 20.78B transcription (PDF p.141), one per column."""
    assert replacements.cw_infantry_lookup(3, 12) == 20     # col 3..30, roll 12
    assert replacements.cw_infantry_lookup(30, 4) == 15     # col 3..30, roll 4
    assert replacements.cw_infantry_lookup(31, 5) == 22     # col 31..46, roll 5
    assert replacements.cw_infantry_lookup(47, 6) == 28     # col 47..102, roll 6
    assert replacements.cw_infantry_lookup(102, 11) == 35   # col 47..102, roll 11
    assert replacements.cw_infantry_lookup(103, 8) == 13    # col 103..107, roll 8


def test_cw_infantry_none_cells_are_zero():
    """The 'none' cells produce nothing (they are 0, not a skipped roll)."""
    assert replacements.cw_infantry_lookup(3, 2) == 0       # col 3..30, roll 2 = none
    assert replacements.cw_infantry_lookup(3, 5) == 0       # col 3..30, roll 5 = none
    assert replacements.cw_infantry_lookup(31, 12) == 0     # col 31..46, roll 12 = none
    assert replacements.cw_infantry_lookup(107, 7) == 0     # col 103..107, roll 7 = none


def test_cw_infantry_production_window_is_gt3_to_gt107():
    """Production runs GT3 through GT107 inclusive; GT1-2 and GT108-111 produce nothing
    (they fall outside all four columns), and an out-of-window plan turn yields 0 with no
    lookup at all -- section 6 of the transcription: GT107 + the 4-GT lead lands the last
    RP on the last Game-Turn."""
    assert list(replacements.cw_infantry_plan_turns()) == list(range(3, 108))
    for gt in (0, 1, 2, 108, 111, 200):
        for roll in range(2, 13):
            assert replacements.cw_infantry_lookup(gt, roll) == 0


def test_cw_infantry_expected_yield_matches_the_book():
    """The analytic 2d6 expectation over GT3-107 -- the number the port plan rounds to
    '~1,617' and the transcription computes as 1,615.9."""
    ev = replacements.cw_infantry_expected_yield()
    assert ev == pytest.approx(1615.89, abs=0.05)
    assert 1600 < ev < 1620


def test_cw_infantry_stream_is_deterministic_and_reproducible():
    """Same seed -> byte-identical stream. Rolled off the DiceBox 'cw_production' subsystem,
    two independent boxes at one seed produce the identical per-turn sequence and total."""
    def roll_campaign(seed: int) -> list[int]:
        box = DiceBox(seed)
        out = []
        for plan_gt in replacements.cw_infantry_plan_turns():
            d1, d2 = box.d6("cw_production"), box.d6("cw_production")
            out.append(replacements.cw_infantry_lookup(plan_gt, d1 + d2))
        return out

    a, b = roll_campaign(1941), roll_campaign(1941)
    assert a == b                                # reproducible
    assert roll_campaign(7) != a                 # seed-sensitive (not a constant)
    assert len(a) == 105                          # one roll per GT3..107


def test_cw_infantry_empirical_yield_lands_on_the_expectation():
    """Rolled over many seeds, the stream's mean total tracks the analytic expectation --
    proving the table AND the 'one 2d6 per Game-Turn, GT3-107' mechanic together."""
    ev = replacements.cw_infantry_expected_yield()
    totals = []
    for seed in range(200):
        box = DiceBox(seed)
        total = sum(
            replacements.cw_infantry_lookup(gt, box.d6("cw_production") + box.d6("cw_production"))
            for gt in replacements.cw_infantry_plan_turns()
        )
        totals.append(total)
    mean = statistics.mean(totals)
    assert mean == pytest.approx(ev, rel=0.02)   # within 2% of ~1,616 over 200 campaigns
    # every single-seed campaign is a wide but bounded draw around the mean
    assert all(1200 < t < 2100 for t in totals)


def test_cw_production_has_its_own_dice_subsystem():
    """The stream draws from a NAMED subsystem, so it cannot perturb any other stream
    (game.dice's whole reason to exist). A die drawn here leaves 'weather' untouched."""
    from game import dice
    assert "cw_production" in dice.SUBSYSTEMS
    box = DiceBox(1941)
    weather_before = box.stream("weather").getstate()
    box.d6("cw_production"); box.d6("cw_production")     # burn the production stream
    assert box.stream("weather").getstate() == weather_before


# --- [20.66] the AXIS REPLACEMENT POOL --------------------------------------------------

def test_axis_german_pool_totals():
    """[20.66] German Production Chart: 400 infantry (from GT38) + 131 tank points."""
    inf = replacements.axis_item("german", "infantry")
    assert inf["number"] == 400
    assert inf["plan_gt"] == 38
    assert replacements.axis_tank_total("german") == 131


def test_axis_italian_pool_totals():
    """[20.66] Italian Production Chart: 1200 infantry + 204 tank points; tier sub-rows sum
    to the item total (the printed '--' second infantry row adds no new pool)."""
    inf = replacements.axis_item("italian", "infantry")
    assert inf["number"] == 1200
    assert replacements.axis_tank_total("italian") == 204


def test_axis_truck_production_chart():
    """[20.66a] Axis Truck Production Chart -- the faucet into the last mile (faucet-audit.md).
    Two per-Game-Turn tiers per type, the higher from GT13."""
    trucks = {t["key"]: t for t in replacements.axis_trucks()}
    assert trucks["light"]["number"] == 835
    assert trucks["medium"]["number"] == 2890
    assert trucks["heavy"]["number"] == 525
    med = trucks["medium"]["tiers"]
    assert (med[0]["max"], med[0]["first_gt"]) == (20, 6)
    assert (med[1]["max"], med[1]["first_gt"]) == (50, 13)


def test_every_tiered_item_tier_numbers_sum_to_its_total():
    """Data integrity: an item's campaign total equals the sum of its tier numbers -- the
    Italian '--' dash sub-row carries number 0 so the invariant holds universally."""
    for chart in ("german", "italian"):
        for item in replacements.axis_items(chart):
            if "tiers" in item:
                assert sum(t["number"] for t in item["tiers"]) == item["number"], item["key"]


# --- [20.62]/[20.64]/[20.75] the TONNAGE CHARGE and the ASYMMETRY -----------------------

def test_axis_infantry_tonnage_is_the_errata_30_not_35():
    """OWNER RULING 6 (errata): 30 tons per Axis Infantry Replacement Point, both nationalities
    -- the chart's own Tonnage column and rule 56.24, against 20.62's own '350 for 10' example."""
    assert replacements.axis_tonnage_per_point("german", "infantry") == 30
    assert replacements.axis_tonnage_per_point("italian", "infantry") == 30
    errata = replacements.tonnage_errata()
    assert errata["reading_A_rule_20_62_example"]["implied_tons_per_point"] == 35
    assert errata["ruling"].startswith("USE 30")


def test_axis_nonvinfantry_tonnage_is_the_chart_value():
    """Every other row is charged its own printed Tonnage (no contradiction there)."""
    assert replacements.axis_tonnage_per_point("german", "pz3e") == 190     # PzIII E
    assert replacements.axis_tonnage_per_point("german", "pz4f2_special") == 235


def test_ten_italian_infantry_points_cost_300_tons_the_reconciled_rate():
    """The 20.62 worked example, at the errata rate: 10 Italian Infantry RP = 300 tons
    (agreeing with rule 56.24), not the 350 the 20.62 example itself prints."""
    assert 10 * replacements.axis_tonnage_per_point("italian", "infantry") == 300


def test_commonwealth_points_are_free_the_20_75_asymmetry():
    """[20.75] 'The Commonwealth Player has no Shipping Problems; his Replacement Points simply
    arrive.' Every Commonwealth point -- infantry stream and equipment chart alike -- costs 0
    tonnage. This asymmetry IS the Commonwealth's structural advantage."""
    for item in replacements.commonwealth_equipment_items():
        assert replacements.commonwealth_tonnage_per_point(item["key"]) == 0
    assert replacements.commonwealth_tonnage_per_point("infantry") == 0


# --- [20.78C] the COMMONWEALTH PRODUCTION CHART -----------------------------------------

def test_cw_equipment_tank_total_is_the_ruled_332():
    """OWNER RULING 2: all 13 armour rows at their printed # sum to 332 (NOT the plan's derived
    306). And the full 24-row equipment pool is 958 (64.74-eligible)."""
    assert replacements.commonwealth_tank_total() == 332
    assert sum(i["number"] for i in replacements.commonwealth_equipment_items()) == 958


def test_sherman_is_the_sharpest_tooth_and_lands_gt93():
    """62 Shermans, Max 12 per GAME-TURN (no per-month marker), first plan-GT 89 -> on-map
    arrival GT93 under the 4-Game-Turn lead (ruling 1). The port plan's 'from GT89' read the
    Shermans ~4 GT early by treating the plan turn as the arrival turn."""
    sh = replacements.commonwealth_item("sherman")
    assert (sh["number"], sh["max"], sh["max_period"], sh["plan_first"]) == (62, 12, "game_turn", 89)
    assert replacements.commonwealth_arrival_turn(sh["plan_first"]) == 93


def test_cw_equipment_named_rows_present_at_printed_values():
    """The rows the block names explicitly: 25-pounder, 6-pounder and the AA rows."""
    assert replacements.commonwealth_item("25_pounder")["number"] == 250
    assert replacements.commonwealth_item("6_pounder")["number"] == 80
    assert replacements.commonwealth_item("light_aa")["number"] == 75
    assert replacements.commonwealth_item("heavy_aa")["number"] == 15


def test_the_20_78C_marker_semantics_are_the_reverse_of_the_german_chart():
    """A faithfulness trap the transcription flags: on 20.78C '*' = per MONTH and dagger = per
    two weeks, the REVERSE of the German 20.66 chart. Crusader III is the only two-weeks item."""
    assert replacements.commonwealth_item("crusader_3")["max_period"] == "two_weeks"
    assert replacements.commonwealth_item("stuart")["max_period"] == "month"     # '*'
    # German '*' is two_weeks, its dagger is month -- opposite mapping
    assert replacements.axis_item("german", "armed_recce")["max_period"] == "two_weeks"   # '*'
    assert replacements.axis_item("german", "heavy_aa")["max_period"] == "month"          # dagger


# --- lead times -------------------------------------------------------------------------

def test_lead_times():
    """CW 4 Game-Turns (ruling 1); Axis 2 Game-Turns (20.63's own printed lead)."""
    assert replacements.CW_ARRIVAL_LEAD == 4
    assert replacements.AXIS_ARRIVAL_LEAD == 2
    assert replacements.commonwealth_arrival_turn(89) == 93
    assert replacements.axis_arrival_turn(38) == 40


# --- reconciliation with logistics_rates.json -------------------------------------------

def test_replacement_point_tons_key_is_reconciled_to_this_chart():
    """data/logistics_rates.json:equivalent_weights_54_5.replacement_point_tons must FORWARD-
    REFERENCE this chart, not carry a second source of truth for the per-point tonnage."""
    from game import logistics_data
    rpt = logistics_data._data()["equivalent_weights_54_5"]["replacement_point_tons"]
    assert "Axis Replacement Pool" in rpt["axis_naval_convoy"]        # varies -- see the pool
    assert "replacements.json" in rpt["_comment"]                     # points at the real file
    assert rpt["air"] == 2                                            # 54.5 infantry-only air rate


# --- the FLOW IN, end to end: engine._replacement_production -> apply -> the pool -------
#
# Everything above pins the DATA reader (game.replacements) and the standalone 2d6 stream.
# These pin the one genuinely NEW behaviour of Block 7.2a -- the engine beat that emits
# REPLACEMENTS_PRODUCED, the apply() fold that credits GameState.replacement_pool, and the
# two pool accessors -- so the wiring is guarded against regression, not merely measured
# once by hand. (Before this section nothing invoked engine._replacement_production, the
# apply REPLACEMENTS_PRODUCED branch, or state.credit_replacements at all.)

def _repro_state(*, turn: int, seed: int = 1941, production: bool = True) -> GameState:
    """The minimal valid GameState engine._replacement_production reads: a turn, a seed (which
    the 'cw_production' stream derives from), and the replacement_production gate. One zeroed
    dump keeps the supply-conservation invariant trivially true (on_hand + consumed == initial
    == 0), the same minimal shape tests/test_convoy_planning.py builds for its sibling beat."""
    dump = SupplyUnit("AX-Port", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=0, water=0)
    return GameState(
        turn=turn, max_turns=111, phase=Phase.LOGISTICS, active_side=Side.SYSTEM, seed=seed,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0), supplies=(dump,),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES},
        convoys=(), stage=1, replacement_production=production)


def _fire(*, turn: int, seed: int = 1941, production: bool = True) -> _Run:
    r = _Run(_repro_state(turn=turn, seed=seed, production=production))
    _replacement_production(r)
    return r


def _produced(r: _Run) -> list:
    return [e for e in r.events if e.kind == EventKind.REPLACEMENTS_PRODUCED]


def test_production_beat_emits_on_the_arrival_turn_for_plan_turn_minus_four():
    """GT7 is the first productive Game-Turn: plan_turn = 7 - CW_ARRIVAL_LEAD = 3 (the window's
    open edge). The beat rolls 2d6 off the 'cw_production' stream, looks the total up against the
    PLAN turn's column, and emits REPLACEMENTS_PRODUCED{ALLIED, infantry, plan_turn 3, arrival 7}
    with both dice on the record (rng_draws), so replay needs no RNG."""
    r = _fire(turn=7)
    box = DiceBox(1941)
    d1, d2 = box.d6("cw_production"), box.d6("cw_production")   # the same fresh stream the beat drew
    ev = _produced(r)
    assert len(ev) == 1
    p = ev[0].payload
    assert (p["side"], p["type"]) == (Side.ALLIED.value, "infantry")
    assert (p["plan_turn"], p["arrival_turn"]) == (3, 7)
    assert ev[0].side is Side.ALLIED
    assert ev[0].rng_draws == (d1, d2)
    assert p["points"] == replacements.cw_infantry_lookup(3, d1 + d2)


def test_the_lookup_column_is_the_plan_turn_not_the_arrival_turn():
    """plan_turn and arrival_turn can fall in DIFFERENT [20.78B] columns: GT34 plans GT30 (the
    3..30 column) but arrives inside the 31..46 range. The RP must be read off the PLAN column --
    'the roll is made when its RP arrive, deterministically the same draw as rolling four turns
    earlier'. This guards against keying the table off r.state.turn (arrival), which reads the
    wrong column: for this seed lookup(30) == 5 but lookup(34) == 13, so the distinction bites."""
    r = _fire(turn=34)
    box = DiceBox(1941)
    total = box.d6("cw_production") + box.d6("cw_production")
    p = _produced(r)[0].payload
    assert (p["plan_turn"], p["arrival_turn"]) == (30, 34)
    assert p["points"] == replacements.cw_infantry_lookup(30, total)
    # a live distinction, not a tautology: GT30 and GT34 index different columns
    assert (replacements.cw_infantry_column(30)["plan_first"]
            != replacements.cw_infantry_column(34)["plan_first"])


def test_the_fold_credits_the_training_ledger_not_the_pool():
    """RESTATED for Block 7.4 (20.43 Training): apply(REPLACEMENTS_PRODUCED) no longer credits the
    absorbable pool. An arrived point enters the TRAINING ledger at arrival + the [17.6] delay
    (Infantry +1 Game-Turn), and reaches the pool only after it has Trained (REPLACEMENTS_TRAINED).
    GT34 plans GT30 (a nonzero cohort), maturing GT35. The old assertion enshrined 7.2b's
    'absorbable on arrival' shortcut."""
    r = _fire(turn=34)
    p = _produced(r)[0].payload
    assert p["points"] > 0 and p["mature_turn"] == 35
    assert r.state.replacement_pool == {}                          # NOT absorbable this Game-Turn
    assert r.state.replacement_training == {"ALLIED/infantry": {35: p["points"]}}
    assert r.state.replacements_available("ALLIED/infantry") == 0


def test_the_beat_is_gated_off_by_default_so_the_benchmarks_stay_byte_identical():
    """replacement_production defaults False; the tactical Desert Fox benchmarks never set it, so
    the beat returns at its first guard -- no PHASE_ADVANCED, no die drawn, no event. This is the
    structural reason Block 7.2a re-baselined NEITHER signature (tests/baselines.py)."""
    r = _fire(turn=7, production=False)
    assert r.events == []
    assert r.state.replacement_pool == {}
    assert r.state.replacement_training == {}


def test_off_window_game_turns_draw_no_die_and_emit_nothing():
    """A plan_turn outside GT3..107 plans nothing, so the beat returns before drawing (the stream
    is untouched) and emits nothing: the opening turns (plan < 3) and, symmetrically, any turn
    whose plan_turn would exceed 107. GT111 (plan 107) is the last productive Game-Turn."""
    for turn in (1, 4, 6, 112, 200):        # plan_turn -3, 0, 2, 108, 196 -- all outside [3, 107]
        r = _fire(turn=turn)
        assert r.events == [], turn
        assert r.state.replacement_pool == {}
        assert r.state.replacement_training == {}


def test_the_production_beat_is_deterministic():
    """Same seed -> byte-identical draw and emit (determinism binds absolutely). The 105-roll
    stream test above proves seed-sensitivity across a campaign; this proves the engine beat's
    single fold replays identically."""
    a, b = _fire(turn=7), _fire(turn=7)
    assert [event_to_dict(e) for e in a.events] == [event_to_dict(e) for e in b.events]


def test_a_none_cell_still_emits_a_certified_identity_fold():
    """A 'none' cell is points 0 (e.g. GT3, roll 5): apply() Trains nobody -- a pure identity on BOTH
    ledgers -- but the event, with its 2d6 on the record, is still in the log, like
    TRUCK_BREAKDOWN_CHECKED. Built as a bare fold so the assertion does not depend on hunting a
    seed whose live roll lands on a none cell."""
    assert replacements.cw_infantry_lookup(3, 5) == 0          # the none cell this fold represents
    st = _repro_state(turn=7)
    ev = Event(0, 7, Phase.LOGISTICS, Side.ALLIED, "ALLIED/QM",
               EventKind.REPLACEMENTS_PRODUCED,
               {"side": Side.ALLIED.value, "type": "infantry", "points": 0,
                "plan_turn": 3, "arrival_turn": 7, "mature_turn": 8}, (2, 3), 1)
    out = apply(st, ev)
    assert out.replacements_available("ALLIED/infantry") == 0
    # RESTATED for Block 7.4: the old fold credited a 0-point pool KEY; the 20.43 fold lands in the
    # training ledger, and a 0-point arrival Trains nobody -- a pure identity on both ledgers.
    assert out.replacement_pool == {}
    assert out.replacement_training == {}


def test_credit_replacements_is_an_immutable_accumulating_credit():
    """state.credit_replacements never mutates: it returns a NEW state with the bucket raised, an
    absent bucket reads 0, and successive credits accumulate. The matching debit is Block 7.2b."""
    st = _repro_state(turn=7)
    assert st.replacements_available("ALLIED/infantry") == 0   # absent bucket -> 0
    once = st.credit_replacements("ALLIED/infantry", 10)
    twice = once.credit_replacements("ALLIED/infantry", 5)
    assert once.replacements_available("ALLIED/infantry") == 10
    assert twice.replacements_available("ALLIED/infantry") == 15
    assert st.replacement_pool == {}                           # the original is never mutated
    assert once.replacement_pool == {"ALLIED/infantry": 10}    # nor the intermediate


def test_the_campaign_run_wires_the_beat_into_the_loop_and_accumulates():
    """End to end on the real campaign: run() calls the beat every Game-Turn (engine.run), so a
    short campaign fires on GT7 (plan 3) and GT8 (plan 4), each event well-formed, and the pool is
    the running sum. This is the guard the block lacked -- that the FLOW IN is actually plumbed
    into the loop, not merely callable in isolation.

    RESTATED for Block B (20.62 the Axis convoy coupling): REPLACEMENTS_PRODUCED is no longer a
    Commonwealth-only event -- the Axis now ALSO brings in Infantry Replacement Points, charged
    tonnage against the convoy (its own test file). This test owns the COMMONWEALTH flow-in, so it
    filters to the ALLIED events and scopes the conservation identity to the Commonwealth pool; the
    Axis events are asserted well-formed but their accounting lives with the coupling."""
    res = run(campaign(seed=4, max_turns=8), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    ev = [e for e in res.events if e.kind == EventKind.REPLACEMENTS_PRODUCED]
    cw = [e for e in ev if e.payload["side"] == Side.ALLIED.value]
    assert cw, "the campaign must roll the CW Infantry Production stream"
    assert min(e.payload["plan_turn"] for e in cw) == 3        # the first productive plan turn
    for e in cw:
        p = e.payload
        assert p["type"] == "infantry"
        assert p["arrival_turn"] == p["plan_turn"] + replacements.CW_ARRIVAL_LEAD
        assert p["plan_turn"] in replacements.cw_infantry_plan_turns()
        assert p["points"] == replacements.cw_infantry_lookup(p["plan_turn"], sum(e.rng_draws))
    # Block B: the Axis coupling emits its own REPLACEMENTS_PRODUCED -- infantry, 30 tons/point, the
    # [20.63] two-Game-Turn lead. It is a charged flow-in where the Commonwealth's is free (20.75).
    for e in (e for e in ev if e.payload["side"] == Side.AXIS.value):
        p = e.payload
        assert p["type"] == "infantry" and p["tons_charged"] == p["points"] * 30
        assert p["arrival_turn"] == p["plan_turn"] + replacements.AXIS_ARRIVAL_LEAD
    # Conservation stays THREE-way (Block 7.4's 20.43 Training) but SCOPED to the Commonwealth pool:
    # every CW Infantry Point produced is either still Training, or trained-and-absorbable in the pool,
    # or already drawn by a UNIT_REBUILT. (The Axis pool is a separate ledger; mixing the two summed a
    # CW-produced total against an all-sides training ledger.)
    produced = sum(e.payload["points"] for e in cw)
    drawn = sum(e.payload["cost"] for e in res.events if e.kind == EventKind.UNIT_REBUILT
                and e.payload["pool_key"] == "ALLIED/infantry")
    in_pool = res.final.replacements_available("ALLIED/infantry")
    in_training = sum(res.final.replacement_training.get("ALLIED/infantry", {}).values())
    assert produced == in_pool + in_training + drawn
    assert drawn > 0, "Block 7.2b: the campaign must actually SPEND replacement points now"
    assert in_training > 0, "Block 7.4: the last Game-Turn's arrivals have not finished Training"


def test_the_production_gate_is_a_campaign_only_subsystem():
    """Only campaign() models the CW Production system (Cairo/Alexandria arrival, 20.76); the two
    tactical benchmarks leave replacement_production False. Combined with the gated-off beat test,
    this pins WHY neither benchmark log gained a byte (tests/baselines.py), without paying for a
    full benchmark run here -- the signature guards already prove byte-identity."""
    assert campaign(seed=4).replacement_production is True
    assert rommels_arrival(seed=42).replacement_production is False
    assert siege_of_tobruk(seed=42).replacement_production is False
