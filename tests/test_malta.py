"""[44.0] MALTA -- the island as a place with health, and the two-way loop that replaced a calendar.

These tests hold the line the whole of Phase 5.4 exists to draw: Malta's strength against the Axis
convoy must be a FUNCTION OF ITS FACILITY LEVELS AND ITS SURVIVING AEROPLANES, and the Axis must be
able to reach it and pay for reaching it out of a finite printed budget. The thing being replaced
was `game.scenario._malta_bomb_points`, a hand-typed month table; the first test in this file is
that no such function exists any more, because a deleted invention that comes back is worse than
one that never left.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import game.scenario as scenario
from game import air, logistics_data, malta
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.engine import _convoy_loss_pct, _malta_construction, _malta_raid, _Run, run
from game.events import EventKind, Side
from game.scenario import campaign


# --- the invention is gone ----------------------------------------------------------------------

def test_the_invented_malta_calendar_no_longer_exists():
    """I2, deleted. `_malta_bomb_points(gt)` returned 100/200/300/500/0/150/400 by month and was
    the single largest determinant of who won the campaign. Nothing may reintroduce it."""
    assert not hasattr(scenario, "_malta_bomb_points")


def test_every_malta_interdiction_order_is_live_sourced_and_carries_no_typed_strength():
    st = campaign(seed=1, max_turns=6)
    malta_orders = [o for o in st.interdictions if o.source == "malta"]
    assert malta_orders, "the campaign must still put Malta over the Axis convoy lane"
    assert {o.lane for o in malta_orders} == {"2"}
    assert all(o.bomb_points == 0 for o in malta_orders), "strength is read from the island, not typed"
    # one per Game-Turn: an order that is sometimes absent is a die sometimes not drawn
    assert sorted(o.turn for o in malta_orders) == list(range(1, 7))


# --- the island as printed ([44.12], the game-map) -----------------------------------------------

def test_the_six_printed_maltese_facilities_match_their_charted_maxima():
    """[44.12] the facilities are printed on the map; [36.12]/[36.3]/[36.4] print their ceilings.
    Four airfields at six, one flying boat basin at three, one alighting area at one -- and the
    total (28) must contain every scenario's printed initial capacity."""
    facs = malta.seed_facilities(0)
    assert len(facs) == 6
    assert sum(f.max_level for f in facs) == 28
    by_kind = {f.kind for f in facs}
    assert by_kind == {"airfield", "basin", "alighting"}
    assert {f.max_level for f in facs if f.kind == "airfield"} == {6}
    assert [f.max_level for f in facs if f.kind == "basin"] == [3]
    assert [f.max_level for f in facs if f.kind == "alighting"] == [1]


def test_the_campaign_opens_malta_at_its_printed_60_46_capacity_on_the_airfields():
    """[60.46] "The Malta bases have an initial capacity of five SGSU's... spread amongst the Malta
    facilities as the player wishes." Ours spreads over the AIRFIELDS first -- 60.46's roster is 31
    land planes and no flying boat, so a level in the basin would be a level nothing could use."""
    st = campaign(seed=1, max_turns=4)
    facs = malta.facilities(st)
    assert malta.capacity(st) == 5
    boats = [f for f in facs if f.kind != "airfield"]
    assert all(f.level == 0 for f in boats)
    assert sum(f.level for f in facs if f.kind == "airfield") == 5


def test_malta_opens_with_its_printed_establishment_of_aeroplanes():
    st = campaign(seed=1, max_turns=4)
    assert st.malta_planes == 31 == malta.initial_planes()      # 60.46: 15 + 12 + 3 + 1


# --- the Commonwealth half: levels -> 18 planes -> BOMB points -> the [41.5] CRT ------------------
#
# RESTATED, NOT WEAKENED (rules of this port, 5). The four tests below used to assert that Malta's
# strike reads the [41.5] table through its TORPEDO POINTS index, because [4.44A] gives the
# Swordfish Mk. I a Bombload Capacity of "-". The chart forbids exactly that: footnote (a), printed
# on the Torpedo Points header row itself (PDF p.107) and spelled out in the Key on the facing page
# (PDF p.108, rendered at 300 dpi and read with eyes), says VERBATIM "Use only when attacking ships
# of the Commonwealth Fleet... Attacks by planes armed with Torpedos against Ports or Axis Naval
# Convoys are carried out using the BOMB POINTS ROW (see Case 41.7)". 41.72 scopes the torpedo line
# to "Axis plane vs. Commonwealth Fleet" from the other side, 41.74 counts a torpedo "as normal
# bombs", and 41.73 adds 25% when at least half the attacking planes carry torpedoes. So these now
# assert the Bomb-Points row with 41.73's modifier -- which is a WEAKER attack than the tests used
# to pin, and that is the correction, not a concession.

def test_malta_enters_the_crt_on_the_bomb_points_row_with_41_73s_twenty_five_percent():
    """[41.66]/[41.73]/[41.74] Nine READY Swordfish (60.46 prints "12 Swordfish (1 SGSU) (9 ready)")
    at a Torpedo Capacity of 8 counted as normal bombs is 72 Bomb Points; 100% of them carry
    torpedoes, so 41.73's +25% rounding upward makes 90."""
    st = campaign(seed=1, max_turns=4)
    assert malta.strike_planes(st) == 9                  # 60.46: three of the twelve start unfit
    assert malta.bomb_points(st) == 90
    full = replace(st, malta_unfit=0)                    # ...and once they are all refit, twelve
    assert malta.strike_planes(full) == 12
    assert malta.bomb_points(full) == 120                # 96 x 1.25, exactly on the column boundary


def test_the_torpedo_index_exists_in_the_data_and_nothing_reads_it():
    """[41.5] footnote (a) / [41.72]: the Torpedo-Points scale is transcribed against the day an
    AXIS torpedo strike on the Commonwealth Fleet is built, and the convoy path must never enter
    through it. The two scales are genuinely different columns of one grid -- 96 points is the
    6th torpedo bracket and only the 4th bomb bracket -- so reading the wrong one is worth real
    cargo, which is why this pins that the convoy resolver has no torpedo door at all."""
    columns = logistics_data.convoy_bombing_crt_41_66()
    assert [c["torpedo_points"] for c in columns][:4] == [[1, 5], [6, 12], [13, 24], [25, 50]]
    assert [c["bomb_points"] for c in columns][:4] == [[1, 20], [21, 40], [41, 80], [81, 120]]
    with pytest.raises(TypeError):                       # no `weapon` argument to switch scales
        _convoy_loss_pct(96, 1, 1, "torpedo")
    codes = [(d1, d2) for d1 in range(1, 7) for d2 in range(1, 7)]
    # the whole magnitude of the defect: the same strike on the row the book names is milder
    assert sum(_convoy_loss_pct(120, d1, d2) for d1, d2 in codes) \
        < sum(_convoy_loss_pct(200, d1, d2) for d1, d2 in codes)


def test_a_flattened_malta_sends_nothing_and_that_is_the_earned_1942_blitz():
    """[44.14] 18 planes per level: an island at zero total capacity operates no aeroplane, so it
    puts no bomb over the lane. The invented calendar handed the Axis exactly this for four
    months of 1942 for free; now he has to bomb it."""
    st = campaign(seed=1, max_turns=4)
    flat = replace(st, air_facilities=tuple(
        replace(f, level=0) if malta.is_malta(f) else f for f in st.air_facilities))
    assert malta.capacity(flat) == 0
    assert malta.strike_planes(flat) == 0
    assert malta.bomb_points(flat) == 0
    assert max(_convoy_loss_pct(malta.bomb_points(flat), d1, d2)
               for d1 in range(1, 7) for d2 in range(1, 7)) == 0


def test_one_level_binds_the_44_14_capacity_below_the_strike_establishment():
    """[44.14] one level handles 18 planes; the strike aircraft are served first, so all twelve
    Swordfish still fly at one level -- and every plane the raids have killed is one that does
    not. Taken with the readiness ledger cleared, because 44.16's refit is the OTHER limit.

    RESTATED 2026-07-22 (rules of this port, 5). The second half used to write `malta_planes=15`
    and assert the strike arm was `int(15 * 12 / 31)` -- the September-1940 SHARE of a shrunken
    island. That share stopped being the rule when [34.86] landed: Malta's anti-shipping arm is a
    tracked count now (state.malta_strike), because the schedule reinforces the island with
    fighters and never with a torpedo aircraft, so a fixed 12/31 would have manufactured Swordfish
    out of Spitfires. The claim worth pinning is unchanged and is asserted on the new ledger: an
    island whose raids have taken it down to five anti-shipping aircraft flies five."""
    st = replace(campaign(seed=1, max_turns=4), malta_unfit=0)
    one = replace(st, air_facilities=tuple(
        replace(f, level=1 if f.id.endswith("Hal Far") else 0) if malta.is_malta(f) else f
        for f in st.air_facilities))
    assert malta.capacity(one) == 1
    assert malta.strike_planes(one) == 12
    halved = replace(one, malta_planes=15, malta_strike=5)      # 41.36 took ~60% of the island
    assert malta.strike_planes(halved) == 5


# --- 44.16: Malta refits like all other planes ---------------------------------------------------

def test_the_printed_ready_column_is_the_opening_readiness_ledger():
    """[60.46]/[44.16] "12 Swordfish (1 SGSU) (9 ready)" -- three unserviceable at the campaign's
    start, and 44.16 says they "must be refit like all other planes, USING THE SAME METHOD AS ALL
    OTHER PLANES". Before this the island flew its whole surviving force every Game-Turn forever."""
    st = campaign(seed=1, max_turns=4)
    assert malta.initial_unfit() == 3
    assert st.malta_unfit == 3
    assert malta.strike_establishment(st) == 12 and malta.ready_strike(st) == 9


def test_the_strike_spends_readiness_and_the_38_37_table_gives_it_back():
    """[38.31]/[38.34] via [44.16]: flying the convoy lane makes those planes unfit, and one
    unmodified die on the Refit Table returns the charted percentage of them (44.14 removes the
    SGSU whose nationality would modify it, and the Commonwealth row carries no modifier anyway)."""
    st = campaign(seed=7, max_turns=4)
    r = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    flown = [e for e in r.events if e.kind == EventKind.MALTA_STRIKE_UNFIT]
    refits = [e for e in r.events if e.kind == EventKind.MALTA_REFIT_RESOLVED]
    assert flown and refits
    assert all(e.payload["unfit"] == e.payload["planes"] + (e.payload["unfit"] - e.payload["planes"])
               for e in flown)
    for e in refits:
        assert e.payload["refitted"] == air.refitted_planes(e.payload["undergoing"], e.payload["die"])
        assert len(e.rng_draws) == 1                     # 38.34: ONE die per attempt, certified
    assert 0 <= r.final.malta_unfit <= malta.strike_establishment(r.final)


# --- the Axis half: the finite budget, the [44.42] roll, 41.36 -----------------------------------

def test_the_campaign_budget_is_the_printed_44_41_row():
    """[44.41] via [64.52]: Campaign Game (either) -- I unlimited, II 25, III 12, IV 12."""
    assert malta.budget() == {"I": None, "II": 25, "III": 12, "IV": 12}


def test_an_availability_level_runs_out_and_level_one_never_does():
    st = campaign(seed=1, max_turns=4)
    assert malta.available(st, "IV")
    spent = replace(st, malta_raids={"IV": 12})
    assert not malta.available(spent, "IV")
    assert malta.available(replace(st, malta_raids={"I": 999}), "I")


SICILIAN_CONTINGENT = 18


def _with_a_sicilian_contingent(state):
    """Put a bomber contingent in the Italy/Sicily boxes THE WAY THE ENGINE DOES -- the [42.1]
    transfer ledger (GameState.air_mediterranean, written by engine._air_transfer) -- so that the
    [44.42] table has a based force to take a percentage OF. A table test taken against a force of
    zero asserts nothing at all.

    RESTATED 2026-07-22, NOT WEAKENED: this used to monkeypatch [63.46]'s 10% into the rule-43
    basing data, standing in for an unbuilt order channel while the [60.32]-versus-[44.21] owner
    ruling was open. The ruling is answered ([60.32] is a SET-UP rule; the Axis flies his bombers
    to Sicily), the percentage is deleted, and the fixture now seeds the same state a transfer
    mission produces."""
    return state.with_air_mediterranean(air.squadron(Side.AXIS, "LAND", "strike"),
                                        SICILIAN_CONTINGENT)


def test_the_44_42_table_reads_both_percentages_and_honours_na():
    """[44.42] dice 5 / Level IV is 100/300 -- the in-play percentage plus the strategic one, both
    of the Italy/Sicily-based force. Dice 4 / Level I is the chart's na: no forces available.

    RESTATED 2026-07-22 (rule 5): the percentages are read off the chart either way, but "planes ==
    400% of the based force" is only an assertion about the table if the based force is not zero,
    and a scenario's opening state has nobody there ([60.32]: no plane STARTS in Italy/Sicily)."""
    st = _with_a_sicilian_contingent(campaign(seed=1, max_turns=4))
    based = malta.italy_sicily_planes(st, 1)
    assert based > 0
    plan = malta.raid(st, "IV", 5, 1)
    assert (plan.in_play_pct, plan.strategic_pct) == (100, 300)
    assert plan.planes == based * 100 // 100 + based * 300 // 100 == based * 4
    assert malta.raid(st, "I", 4, 1).planes == 0                    # na


def test_the_43_1_basing_fraction_is_the_printed_one_and_the_transferred_force_does_not_fall():
    """The printed percentages are transcription facts and are asserted unconditionally.

    RESTATED 2026-07-22 (rule 5), AND THE RESTATEMENT IS THE 2026-07-22 RULING. This test used to
    assert that the Italy/Sicily force FALLS at Game-Turn 35, which is 43.12/43.13's law about the
    REQUIREMENT -- 75% of the German bombers before it, 25% of three named heavies after. [60.32]
    musters no German aeroplane at all, so that term is zero at every turn of this campaign and the
    fall was being read off a percentage of the ITALIAN force that rule 43 never governed. What is
    true, and is asserted instead: a bomber the Axis FLEW to Sicily under [42.1] stays there --
    Game-Turn 35 moves a requirement, not a transfer ledger -- and the requirement term itself is
    zero on both sides of the boundary while the muster is Italian."""
    from game import basing as basing_mod
    b = logistics_data.malta_italy_sicily_basing_43_1()
    assert (b["before_turn_35_pct"], b["from_turn_35_pct"], b["change_turn"]) == (75, 25, 35)
    assert "axis_discretionary_italy_sicily_pct_43_1" not in b       # the percentage is DELETED
    st = _with_a_sicilian_contingent(campaign(seed=1, max_turns=4))
    assert basing_mod.required_planes(st, Side.AXIS, 34) == 0        # [60.32] musters no German
    assert basing_mod.required_planes(st, Side.AXIS, 35) == 0
    assert malta.italy_sicily_planes(st, 34) == malta.italy_sicily_planes(st, 35) \
        == SICILIAN_CONTINGENT


def test_41_36_takes_ten_percent_of_the_planes_on_the_ground_per_level():
    """[41.36] "for every level destroyed, remove 10% of the planes on the ground (e.g., 2 levels,
    20% planes), rounded down." """
    st = campaign(seed=1, max_turns=4)
    assert malta.planes_lost(st, 1) == 3            # 10% of 31, rounded down
    assert malta.planes_lost(st, 2) == 6
    assert malta.planes_lost(replace(st, malta_planes=9), 1) == 0


def test_the_raid_target_is_the_fullest_field_and_none_when_the_island_is_flat():
    st = campaign(seed=1, max_turns=4)
    heavy = replace(st, air_facilities=tuple(
        replace(f, level=4) if f.id.endswith("Takali") else f for f in st.air_facilities))
    assert malta.raid_target(heavy).id == "Malta/Takali"
    flat = replace(st, air_facilities=tuple(
        replace(f, level=0) if malta.is_malta(f) else f for f in st.air_facilities))
    assert malta.raid_target(flat) is None


def test_a_cancelled_raid_still_spends_the_availability_level():
    """[44.29] "The raid is cancelled, but he still has used the table he rolled for once --
    regardless of whether he cancels or not." Here the island is already flat, so nothing is
    bombed; the Game-Turn of Level IV is gone all the same."""
    st = campaign(seed=3, max_turns=4)
    flat = replace(st, air_facilities=tuple(
        replace(f, level=0) if malta.is_malta(f) else f for f in st.air_facilities))
    r = _Run(flat)

    class _Always(CampaignAxisPolicy):
        def malta_raid(self, state):
            return "IV"

    _malta_raid(r, {Side.AXIS: _Always(), Side.ALLIED: CampaignCommonwealthPolicy()})
    ordered = [e for e in r.events if e.kind == EventKind.MALTA_RAID_ORDERED]
    assert len(ordered) == 1 and ordered[0].payload["cancelled"] is True
    assert r.state.malta_raids == {"IV": 1}
    assert not [e for e in r.events if e.kind == EventKind.AIR_FACILITY_LEVEL_CHANGED]


def test_the_engine_refuses_an_availability_level_the_budget_no_longer_holds():
    st = campaign(seed=3, max_turns=4)
    broke = replace(st, malta_raids={"IV": 12})
    r = _Run(broke)

    class _Always(CampaignAxisPolicy):
        def malta_raid(self, state):
            return "IV"

    _malta_raid(r, {Side.AXIS: _Always(), Side.ALLIED: CampaignCommonwealthPolicy()})
    assert r.state.malta_raids == {"IV": 12, "I": 1}       # fell back to the unlimited level


# --- the Commonwealth repairs ([44.5]) -----------------------------------------------------------

def test_the_44_5_construction_table_is_the_printed_one():
    assert [malta.repair_levels(d) for d in range(1, 7)] == [0, 1, 1, 1, 1, 2]


def test_construction_may_not_begin_before_october_1940():
    """[60.46] "Construction on increasing the capacity of Malta Air Facilities may begin in
    October, 1940" -- and the campaign opens in the third week of September."""
    assert not malta.may_construct(1940, 9)
    assert malta.may_construct(1940, 10) and malta.may_construct(1942, 1)


def test_repair_restores_bomb_damage_up_to_the_printed_establishment_and_no_further():
    st = campaign(seed=5, max_turns=8)
    hurt = replace(st, turn=8, air_facilities=tuple(
        replace(f, level=0) if malta.is_malta(f) else f for f in st.air_facilities))
    r = _Run(hurt)
    for _ in range(40):                               # many Game-Turns of repair
        _malta_construction(r)
    assert malta.capacity(r.state) == malta.repair_ceiling(r.state) == 5
    assert not malta.repairable(r.state)


# --- the loop, end to end ------------------------------------------------------------------------

def test_the_whole_loop_turns_over_a_short_campaign():
    """Both halves fire, the budget depletes down a REAL ledger, and the convoy is still being
    interdicted at a strength the island's own state produced.

    RESTATED (rules of this port, 5). This test used to promise "the island loses levels and
    aeroplanes, the budget depletes" and then assert only that ten Game-Turns booked ten raids
    (trivially true -- 44.24 gives exactly one per turn) and that malta_planes never rose (vacuous
    -- 41.36 is its only writer and it only subtracts). Neither claim could fail. What is actually
    worth pinning is that the budget lands on the LEVELS the doctrine chose (not just any ten) and
    that the lane's certified strength equals what game.malta says the island could send.

    RESTATED AGAIN 2026-07-22 (rules of this port, 5): the certified-strength bound used to range
    over 1..12 Swordfish, which was the whole island's establishment only while nothing replaced it.
    [34.86] does now, so the bound ranges over the anti-shipping arm the island actually ends with --
    and the assertion that a raid's Bomb Points are ALWAYS some whole number of aeroplanes at
    torpedo-8 plus 41.73's quarter is exactly as tight as it was.

    RESTATED A THIRD TIME 2026-07-22 (the [60.32] transfer block), NOT WEAKENED. It asserted
    `final.malta_strike >= malta.initial_strike()` -- "34.81A: the island GAINED aircraft" -- which
    was never a claim about the faucet at all: [34.86] sends the island no torpedo aircraft (a tenth
    of a month of them, floored, is none), so the ONLY writer of that bucket is 41.36, and the
    inequality held because the Axis had no way to fly a raid. He has one now ([42.1], to Benghazi's
    fields and on to Sicily), so the arm falls when he lands one. What is pinned instead is the
    bucket's true law -- it never grows, it falls exactly when a raid takes planes off the ground --
    and the strengths certified DURING the run are bounded by the arm at its largest, which for the
    same reason is the one the island started with."""
    st = campaign(seed=7, max_turns=10)
    r = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    raids = [e for e in r.events if e.kind == EventKind.MALTA_RAID_ORDERED]
    assert len(raids) == 10                            # 44.24: exactly one raid per Game-Turn
    assert sum(r.final.malta_raids.values()) == 10
    assert set(r.final.malta_raids) <= set(malta.LEVELS)
    assert all(malta.spent(r.final, lvl) <= (malta.budget()[lvl] or 10) for lvl in malta.LEVELS)
    cut = [e for e in r.events if e.kind == EventKind.CONVOY_INTERDICTED
           and e.payload["lane"] == "2"]
    assert cut
    # 11: the log certifies the strength that produced the result, not the order's empty field
    assert all(e.payload["bomb_points"] > 0 for e in cut)
    # every certified strength is n READY anti-shipping aircraft x T8 counted as bombs, +25%
    # rounding up -- n bounded by the arm [34.86] has grown the island to by the last Game-Turn
    lost = [e for e in r.events if e.kind == EventKind.MALTA_PLANES_LOST]
    assert r.final.malta_strike <= malta.initial_strike()      # [34.86] sends this arm nothing:
    assert (r.final.malta_strike < malta.initial_strike()) == bool(lost)   # 41.36 is its one writer
    assert {e.payload["bomb_points"] for e in cut} <= {
        -(-n * 8 * 125 // 100) for n in range(1, malta.initial_strike() + 1)}


def test_a_sustained_axis_raid_drives_the_islands_TOTAL_capacity_to_zero(monkeypatch):
    """[41.36]/[44.14] THE PROPERTY THE WHOLE BLOCK TURNS ON, and nothing pinned it before: enough
    Axis bombing takes Malta's TOTAL capacity -- summed over all six facilities, not one of them --
    down to nothing, and an island at zero flies nothing at all.

    It is asserted here rather than read off a campaign because it is a property of the MECHANISM
    at its limit -- sixty consecutive raids by a bomber arm forty times the establishment's -- and
    no campaign the doctrine actually flies puts that much over the island at once.

    RESTATED 2026-07-22 (the [60.32] transfer block), NOT WEAKENED, and the reason is that its
    set-up became real. It used to monkeypatch a percentage into the rule-43 basing data
    (`axis_discretionary_italy_sicily_pct_43_1`, the stand-in for an unbuilt order channel) because
    "the campaign Axis cannot reach Malta at all today". He can: the owner ruled [60.32] a set-up
    rule on 2026-07-22 and [42.1]'s transfer mission is built, so the Italy/Sicily force is a
    LEDGER, and this test now seeds it the way the engine does -- state.with_air_mediterranean, the
    same field engine._air_transfer writes. The deleted key is gone with the percentage."""
    st = campaign(seed=3, max_turns=6)
    st = st.with_air_mediterranean(air.squadron(Side.AXIS, "LAND", "strike"), 18)   # [42.1] flown
    assert malta.capacity(st) == 5
    r = _Run(st)

    class _Heavy(CampaignAxisPolicy):
        def malta_raid(self, state):
            return "I"                                  # unlimited, so the budget cannot stop us

    heavy = {Side.AXIS: _Heavy(), Side.ALLIED: CampaignCommonwealthPolicy()}
    for _ in range(60):
        # [44.42] the raid's size is a percentage of the Italy/Sicily-based force; give it the
        # bombers [60.32] actually musters instead of the engine's six proxy Air Points.
        r.state = replace(r.state, air=tuple(
            replace(w, strike=w.strike * 40) if w.side == Side.AXIS and w.arena == "LAND" else w
            for w in r.state.air))
        _malta_raid(r, heavy)
    assert malta.capacity(r.state) == 0                 # 44.12: reduced to zero, never destroyed
    assert len(malta.facilities(r.state)) == 6
    assert malta.strike_planes(r.state) == 0 and malta.bomb_points(r.state) == 0
    assert r.state.malta_planes < st.malta_planes       # 41.36's second clause bit as well


def test_malta_never_leaves_the_map_however_hard_it_is_bombed():
    """[44.12] "Although they may not be destroyed, Maltese air facilities may be reduced (by Axis
    bombing) to zero effectiveness" -- so 36.2's removal of a flattened strip or boat facility must
    never fire on this island."""
    st = campaign(seed=7, max_turns=10)
    r = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    assert len(malta.facilities(r.final)) == 6
    assert not [e for e in r.events if e.kind == EventKind.AIR_FACILITY_DESTROYED
                and str(e.payload.get("facility_id", "")).startswith(malta.PREFIX)]


def test_no_island_no_rule_44_and_the_small_scenarios_stay_untouched():
    """Every scenario that seeds no Malta draws no rule-44 die and folds no rule-44 event -- the
    property that keeps the two benchmarks byte-identical through this block."""
    from game.scenario import rommels_arrival
    st = rommels_arrival(seed=2)
    assert not malta.in_play(st) and st.malta_planes == 0
    r = run(st, axis=__import__("game.policy", fromlist=["ScriptedPolicy"]).ScriptedPolicy(Side.AXIS),
            allied=__import__("game.policy", fromlist=["ScriptedPolicy"]).ScriptedPolicy(Side.AXIS))
    assert not [e for e in r.events if e.kind in (EventKind.MALTA_RAID_ORDERED,
                                                  EventKind.MALTA_PLANES_LOST,
                                                  EventKind.MALTA_STRIKE_UNFIT,
                                                  EventKind.MALTA_REFIT_RESOLVED)]


def test_the_maltese_hexes_can_never_alias_an_african_one():
    """[44.11] "The map of Malta represented on GameMap 'A' is not in the same scale as the African
    portions of the game-maps, nor is it in scale in terms of geographic location" -- it is an
    OFF-SCALE BOX drawn inside section A's corner of the board image, so its raw VASSAL grid indices
    are section A's indices over again.

    That is not cosmetic and this test is not decoration: the engine keys air facilities, hex
    control and air-facility dumps BY HEX (air.facility_at / air.holder / air.facility_dumps), so an
    unshifted Malta means an Axis unit standing on a clear hex of section A silently becomes the
    holder of a Maltese airfield -- and every one of those paths would have failed SILENTLY.
    game.coords translates off-scale sections into their own disjoint slice of the axial space;
    this pins that they land there, that the island stays a connected patch of its own, and that
    the four labels that used to collide (A5504/A5405/A5306/A5507) no longer do."""
    from game import air, coords
    st = campaign(seed=1, max_turns=2)
    island = {f.hex for f in malta.facilities(st)}
    assert len(island) == 6
    assert not island & set(st.terrain.terrain)           # no Maltese hex is a hex of the map
    for label in ("A5504", "A5405", "A5306", "A5507"):    # the four that used to alias
        african = coords.to_axial(coords.parse(label))
        assert african not in island
        assert air.facility_at(st, african) is None
    for label in ("M0505", "M0805"):                      # and the labels still round-trip
        assert coords.from_axial("M", *coords.to_axial(coords.parse(label))).label == label
    assert coords.distance(coords.parse("M0505"), coords.parse("M0506")) == 1


# --- [34.86] / [34.81] the island GROWS ----------------------------------------------------------

def test_the_34_86_schedule_is_transcribed_whole_and_its_row_totals_add_up():
    """[34.86] Every printed row, in the chart's own order, with the arithmetic self-check the data
    file carries: a `total` that disagrees with the sum of its own `planes` is a transcription slip,
    and it fails here rather than in a campaign three hours later."""
    rows = logistics_data.cw_air_reinforcements_34_86()
    assert len(rows) == 28                                  # 4 Game-Turn rows in 1940 + 24 months
    assert [(r["year"], r["month"]) for r in rows] == sorted((r["year"], r["month"]) for r in rows)
    for row in rows:
        assert row["total"] == sum(p["number"] for p in row["planes"]), row["label"]
        assert row["turns"] == sorted(row["turns"]) and row["turns"]
        assert all(p["role"] in ("fighters", "strike", "recon", "transport") for p in row["planes"])
    # the chart's Game-Turns never overlap and never run past the campaign's 111
    seen: set = set()
    for row in rows:
        assert not seen & set(row["turns"])
        seen |= set(row["turns"])
    assert max(seen) <= 111
    assert sum(r["total"] for r in rows) == 6691            # the whole Commonwealth arrival


def test_the_chart_rows_carry_the_names_the_scan_prints():
    """THE REGRESSION TEST FOR THE THREE CELLS THE FIRST TRANSCRIPTION GOT WRONG, 2026-07-22.

    docs/rules/90's OCR of this chart misreads four aircraft names, and the first pass carried three
    of them through -- 1942 May "Beaufighter IIF", 1942 Jul "Beaufighter II" and 1942 Jul "Hurricane
    IC" -- while recording, in the data file that exists to be the arbiter, that the book prints
    those names and that none of them is on the [4.44A] chart. The scan (PDF p.143, 300 dpi, read at
    8x) prints Beaufighter IF, Beaufighter IF and Hurricane IIC, and all three ARE on [4.44A]. The
    tell is exactly that: a name absent from the aircraft chart is a misread until the scan says
    otherwise, so no row may carry one."""
    rows = logistics_data.cw_air_reinforcements_34_86()
    printed = {p["printed"] for r in rows for p in r["planes"]}
    assert not printed & {"Beaufighter IIF", "Beaufighter II", "Hurricane IC", "Hurricane IIIC"}
    by_turn = {t: r for r in rows for t in r["turns"]}
    may42 = {p["printed"]: p["number"] for p in by_turn[79]["planes"]}
    jul42 = {p["printed"]: p["number"] for p in by_turn[87]["planes"]}
    assert may42["Beaufighter IF"] == 3 and jul42["Beaufighter IF"] == 4
    assert jul42["Hurricane IIC"] == 30
    assert {p["printed"]: p["number"] for p in by_turn[31]["planes"]}["Beaufighter IF"] == 16
    # ...and each correction is on the record, which is the other half of what went wrong.
    trail = " ".join(logistics_data._air_reinforcements()["_ocr_corrections"])
    for cell in ("1941 May", "1942 May", "1942 Jul", "1942 Sep", "1942 Nov"):
        assert cell in trail, f"{cell} correction is not in the file's own audit trail"


def test_34_81A_caps_maltas_share_at_a_tenth_of_the_month_rounded_down():
    """[34.81A] "No more than 10% of a month's airplane reinforcements may be sent to Malta." A
    CEILING, so the share rounds DOWN -- and a month whose whole arrival is four aeroplanes (Nov II
    1940, 4 B17Ds) sends the island none at all."""
    st = campaign(seed=1, max_turns=4)
    nov = malta.reinforcement(st, 8)                        # 1940 Nov II (GT 8): 4 planes
    assert nov.month_total == 4 and nov.allotted == 0 and nov.planes == 0
    dec = malta.reinforcement(st, 11)                       # 1940 Dec I (GT 11): 52 planes
    assert dec.month_total == 52 and dec.allotted == 5 and dec.planes == 5


def test_a_months_allotment_is_divided_amongst_its_weeks():
    """[34.84] "The planes must be divided amongst the weeks as evenly as possible." January 1941
    is 57 aeroplanes over Game-Turns 15-18, a fifth of which is Malta's 5 -- so 2 + 1 + 1 + 1."""
    st = campaign(seed=1, max_turns=4)
    weeks = [malta.reinforcement(st, t) for t in (15, 16, 17, 18)]
    assert [w.allotted for w in weeks] == [5, 5, 5, 5]      # the MONTH's ceiling, on every row
    assert [w.planes for w in weeks] == [2, 1, 1, 1] and sum(w.planes for w in weeks) == 5


def _at_levels(st, levels: int):
    """The same campaign with Malta standing at `levels` total Capacity Levels -- what an Axis raid
    (41.36) or a run of [44.5] construction dice leaves behind."""
    mainland = tuple(f for f in st.air_facilities if not malta.is_malta(f))
    return replace(st, air_facilities=mainland + tuple(malta.seed_facilities(levels)))


def test_34_81B_stops_the_island_filling_past_what_it_can_operate():
    """[34.81B]/[44.14] "No airplane reinforcements may be sent... in excess of the facility's
    current squadron capacity", and a Capacity Level operates eighteen planes. An island already
    holding 18 x its levels takes nothing, however large the month's ceiling.

    RESTATED 2026-07-22, NOT WEAKENED. It used to bomb-proof the island at 18 x its FIVE printed
    levels -- ninety aeroplanes -- which no longer isolates 34.81B, because the establishment the
    book prints for the date (55 in this month) now bites first and would carry the assertion on its
    own. So the island is knocked down to two Capacity Levels, where 44.14's thirty-six is the
    binding number and 34.81B is the only cap under test."""
    st = _at_levels(campaign(seed=1, max_turns=4), 2)
    per_level = logistics_data.malta_planes_per_level_44_14()
    operable = per_level * malta.capacity(st)              # 2 levels x 18 = 36, under the book's 55
    assert operable == 36 < malta.planned_planes(1940, 12)
    full = replace(st, malta_planes=operable)
    assert malta.reinforcement(full, 11).headroom == 0
    assert malta.reinforcement(full, 11).planes == 0
    one_seat = replace(full, malta_planes=operable - 1)
    assert malta.reinforcement(one_seat, 11).planes == 1    # and exactly the one seat that is free


def test_34_81_also_stops_at_the_establishment_the_book_prints_for_the_date():
    """THE THIRD BOUND, and the one that usually governs: 34.81 leaves the DIVISION of a month's
    arrivals wholly to the Commonwealth Player, and our assignment of that free choice aims at the
    establishment the book prints for Malta -- [61.34]'s 55 aeroplanes until March 1941, then
    [62.36]'s 74, then [63.37]'s 118 (game.malta.planned_planes). An island already at the figure it
    is building toward takes nothing even with capacity to spare."""
    st = campaign(seed=1, max_turns=4)                     # five levels: ninety operable
    assert malta.planned_planes(1940, 12) == 55            # the next printed snapshot ahead of Dec
    assert malta.planned_planes(1941, 3) == 74             # ...and once March 1941 is reached
    assert malta.planned_planes(1942, 11) == 118           # ...and the last one stands thereafter
    at_plan = replace(st, malta_planes=55)
    assert malta.capacity(at_plan) * logistics_data.malta_planes_per_level_44_14() == 90
    assert malta.reinforcement(at_plan, 11).planes == 0    # room to fly them, no plan to send them


def test_the_torpedo_arm_grows_only_with_torpedo_arrivals():
    """[34.86]/[4.44A] The composition is pro rata over the month's own types, and the bucket that
    sets Malta's Bomb Points admits only the aircraft the chart lets carry a torpedo.

    RESTATED AND RENAMED 2026-07-22, NOT WEAKENED. It used to assert that October 1940's thirty
    Blenheim Mk. Is put two aeroplanes into that bucket, which enshrined the defect: the bucket is
    priced at the Swordfish's Torpedo Capacity of 8 with 41.73's +25% on top, and [4.44A] gives the
    Blenheim Mk. I a Bombload of 5 and no torpedo at all. 41.73's modifier is a CONDITION -- "at
    least 50% of the planes are carrying torpedoes" -- so a bucket of Blenheims was being paid a
    quarter more for torpedoes it did not carry, on top of a rating it did not have. The bucket is
    now the three /T rows of the chart (Albacore, Beaufort Mk. I, Swordfish Mk. I), so October 1940
    -- thirty Blenheim Mk. Is and six Skua Mk. IIs, not a torpedo between them -- adds none."""
    st = campaign(seed=1, max_turns=4)
    oct40 = malta.reinforcement(st, 3)                     # "Oct I (GT 3)", the chart's own label
    assert (oct40.planes, oct40.strike) == (3, 0)          # a tenth of 36, and no torpedo aircraft
    assert malta.reinforcement(st, 2).planes == 0          # Sept IV: 5 aeroplanes, a tenth is zero
    jul41 = malta.reinforcement(st, 39)                    # 12 Albacores in a month of 205
    assert any(p["chart_type"] == "Albacore" for p in malta.month_row(39)["planes"])
    assert jul41.strike == 1        # a tenth of twelve, floored -- and the arm is landed FIRST out
    #                                 of what headroom there is (44.0: Malta hinders the convoys)


def test_the_island_actually_gains_aeroplanes_over_a_campaign():
    """The whole point of the block, end to end: run the schedule out and Malta's establishment
    RISES, where before [34.86] the only writer of it was 41.36 and it only ever subtracted.

    RESTATED 2026-07-22, NOT WEAKENED: it also asserted that the anti-shipping arm rises with the
    establishment, which was only true while that arm counted every bomber the schedule sent. It
    counts the aircraft [4.44A] lets carry a torpedo, the schedule musters 116 of those against
    6,691 aeroplanes, and a tenth of a month floored is none -- so Malta's torpedo arm never grows
    and only 41.36 moves it. That is the book's own shape ([60.46] 12 torpedo aircraft, [61.34] 10,
    [62.36] 3) and it is argued at malta.reinforcement; what is asserted here is that the arm stays
    a HONEST BUCKET of the establishment however either of them moves.

    RESTATED AGAIN 2026-07-22 (the [60.32] transfer block), AND THE REASON IS THE OTHER SIDE OF THE
    LEDGER STARTING TO WORK. It used to assert `final.malta_planes > initial` -- the island's
    establishment strictly RISES over twelve Game-Turns -- and that was true only while the Axis
    raid delivered nothing: [60.32] bases every Axis aeroplane in Africa, the engine had no [42.1]
    transfer mission, so 44.42's percentages were percentages of zero and the only writer of this
    number was the faucet. The Axis can now fly his bombers to Sicily and raid, so BOTH writers are
    live and the net direction is a fact about the war rather than about the engine. What is
    asserted is therefore the ACCOUNTING, which is the thing this block put on the map and is
    strictly more than the old inequality: every arrival is positive, the schedule delivers, and the
    island's final establishment is exactly what arrived less what 41.36 took."""
    st = campaign(seed=4, max_turns=12)
    r = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    got = [e for e in r.events if e.kind == EventKind.MALTA_REINFORCED]
    assert got, "the [34.86] schedule delivered nothing in twelve Game-Turns"
    assert all(e.payload["arrived"] > 0 for e in got)
    arrived = sum(e.payload["arrived"] for e in got)
    lost = sum(e.payload["lost"] for e in r.events if e.kind == EventKind.MALTA_PLANES_LOST)
    assert arrived > 0
    assert r.final.malta_planes == st.malta_planes + arrived - lost
    assert r.final.malta_strike <= r.final.malta_planes     # the invariant, from the outside


def test_the_growth_lands_inside_the_books_own_printed_snapshots():
    """THE ACCEPTANCE TEST data/malta_44.json carried unused since rule 44 landed, and which the
    engine now aims at: the book prints Malta's establishment in four scenarios -- 31 aeroplanes and
    5 Capacity Levels in September 1940, 55 and 8 in March 1941, 74 and 14 in November 1941, 118 and
    28 in October 1942. Run the [34.86] schedule out with no Axis raid at all (the upper bound on
    our growth), letting 44.13's construction stand at its ceiling, and the island tracks that curve
    from below.

    RESTATED 2026-07-22. It used to assert saturation at ninety aeroplanes and five Capacity Levels
    for the whole war, which was the fixed point malta.repair_ceiling collapsed to -- numerically
    the invented ceiling the block said it had deleted."""
    st = campaign(seed=4, max_turns=111)
    seen = {}
    for turn in range(1, 112):
        st = replace(st, turn=turn)
        st = _at_levels(st, malta.repair_ceiling(st))       # 44.13 built up to its dated ceiling
        got = malta.reinforcement(st, turn)
        if got.planes:
            st = replace(st, malta_planes=st.malta_planes + got.planes,
                         malta_strike=st.malta_strike + got.strike)
        seen[turn] = (st.malta_planes, malta.capacity(st))
    # Each pair is (aeroplanes, Capacity Levels) at the end of the month the book photographs.
    assert seen[26] == (58, 8)          # March 1941: [61.34] prints 55 and 8
    assert seen[54] == (74, 8)          # October 1941, a month EARLY on [62.36]'s 74; capacity
    #                                     waits for November, which is the date the book prints it
    assert seen[58] == (93, 14)         # November 1941: [62.36] prints 74 and 14 -- the aeroplanes
    #                                     run ahead as soon as the next printed target (118) opens
    assert seen[98] == (118, 14)        # September 1942, a month early on [63.37]'s 118
    assert seen[102] == (118, 28)       # October 1942: [63.37] prints 118 and 28 exactly
    assert st.malta_strike == malta.initial_strike()        # the torpedo arm: no raid, no decay,
    #                                                         and no replacement (see reinforcement)
    assert st.malta_strike < st.malta_planes // 2           # and Malta is mostly FIGHTERS, as the
    #                                                         book's own snapshots are ([63.37]: 3
    #                                                         Swordfish and 54 Spitfire VBs)


def test_the_build_ceiling_follows_the_books_own_dated_snapshots():
    """[44.13] "It may be increased -- up to the standard levels", one free die per facility per
    Game-Turn with no supplies expended. Nothing in the book meters that but the player's judgement,
    so our Commonwealth builds Malta to the capacity the book prints for the date -- [60.46]'s five,
    [61.34]'s eight from March 1941, [62.36]'s fourteen from November 1941, [63.37]'s twenty-eight
    from October 1942 -- and never past the twenty-eight the six printed facilities can stand at.

    REPLACES test_the_build_ceiling_follows_the_aeroplanes..., 2026-07-22, and the reason is in the
    old test's own two assertions: it pinned repair_ceiling == 6 at 91 aeroplanes and == 28 at
    10,000, states the engine could not produce, because reinforcement admitted planes only up to
    18 x capacity. ceil(planes / 18) could therefore never exceed capacity and the ceiling could
    never rise above five. The suite read green over dead code."""
    st = campaign(seed=1, max_turns=4)
    assert malta.structural_capacity(st) == 28
    assert malta.repair_ceiling(replace(st, turn=1)) == 5            # September 1940: [60.46]
    assert malta.repair_ceiling(replace(st, turn=22)) == 5           # February 1941, still [60.46]
    assert malta.repair_ceiling(replace(st, turn=23)) == 8           # March 1941: [61.34]
    assert malta.repair_ceiling(replace(st, turn=55)) == 14          # November 1941: [62.36]
    assert malta.repair_ceiling(replace(st, turn=99)) == 28          # October 1942: [63.37]
    assert malta.repair_ceiling(replace(st, turn=111)) == 28         # and never past the standard
    # ...and it does not move with the aeroplanes at all any more, which is what broke it before.
    assert malta.repair_ceiling(replace(st, turn=1, malta_planes=10_000)) == 5
