"""Rule 20 -- the Replacement economy's FLOW IN (Block 7.2a).

These tests pin the TRANSCRIPTION (data/replacements.json) and the production LOGIC
(game.replacements) against the book, and prove the Commonwealth infantry random stream
(20.78B) is deterministic and reproducible with the ~1,617 expected yield the port plan
predicts. The SPEND (a unit absorbing a Replacement Point) is Block 7.2b, not tested here.
"""
from __future__ import annotations

import statistics

import pytest

from game import replacements
from game.dice import DiceBox, stream_seed


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
