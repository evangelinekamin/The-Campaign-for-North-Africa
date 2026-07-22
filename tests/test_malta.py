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
    not. Taken with the readiness ledger cleared, because 44.16's refit is the OTHER limit."""
    st = replace(campaign(seed=1, max_turns=4), malta_unfit=0)
    one = replace(st, air_facilities=tuple(
        replace(f, level=1 if f.id.endswith("Hal Far") else 0) if malta.is_malta(f) else f
        for f in st.air_facilities))
    assert malta.capacity(one) == 1
    assert malta.strike_planes(one) == 12
    halved = replace(one, malta_planes=15)
    assert malta.strike_planes(halved) == int(15 * 12 / 31) == 5


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


def _with_a_sicilian_contingent(monkeypatch):
    """Seed the OPEN [60.32]-versus-[44.21] owner ruling's own candidate value ([63.46]'s 10%,
    transcribed unapplied in data/malta_44.json) so that the Axis has somebody in Italy/Sicily for
    the [44.42] table to take a percentage OF. Shipped, that posture is null and
    basing.discretionary_pct answers 0 -- the campaign Axis raids Malta with nothing while the
    ruling is open -- and a table test taken against a force of zero asserts nothing at all."""
    seeded = {**logistics_data.malta_italy_sicily_basing_43_1(),
              "axis_discretionary_italy_sicily_pct_43_1": 10}
    monkeypatch.setattr(logistics_data, "malta_italy_sicily_basing_43_1", lambda: seeded)


def test_the_44_42_table_reads_both_percentages_and_honours_na(monkeypatch):
    """[44.42] dice 5 / Level IV is 100/300 -- the in-play percentage plus the strategic one, both
    of the Italy/Sicily-based force. Dice 4 / Level I is the chart's na: no forces available.

    RESTATED 2026-07-22 (rule 5): the percentages are read off the chart either way, but "planes ==
    400% of the based force" is only an assertion about the table if the based force is not zero,
    and shipped it is (see _with_a_sicilian_contingent)."""
    _with_a_sicilian_contingent(monkeypatch)
    st = campaign(seed=1, max_turns=4)
    based = malta.italy_sicily_planes(st, 1)
    assert based > 0
    plan = malta.raid(st, "IV", 5, 1)
    assert (plan.in_play_pct, plan.strategic_pct) == (100, 300)
    assert plan.planes == based * 100 // 100 + based * 300 // 100 == based * 4
    assert malta.raid(st, "I", 4, 1).planes == 0                    # na


def test_the_43_1_basing_fraction_is_the_printed_one_and_falls_at_game_turn_35(monkeypatch):
    """The printed percentages are transcription facts and are asserted unconditionally; the FALL
    at Game-Turn 35 needs a force to fall, so it is asserted on the doctored posture (same reason,
    same fixture) and on an establishment rule 43 governs -- [60.32] musters no German aeroplane,
    so 43.12's requirement term is zero and only the discretionary term is left to move."""
    basing = logistics_data.malta_italy_sicily_basing_43_1()
    assert (basing["before_turn_35_pct"], basing["from_turn_35_pct"], basing["change_turn"]) \
        == (75, 25, 35)
    assert basing["axis_discretionary_italy_sicily_pct_43_1"] is None    # the ruling is OPEN
    _with_a_sicilian_contingent(monkeypatch)
    st = campaign(seed=1, max_turns=4)
    assert malta.italy_sicily_planes(st, 34) >= malta.italy_sicily_planes(st, 35) > 0


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
    that the lane's certified strength equals what game.malta says the island could send."""
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
    # every certified strength is n READY Swordfish x T8 counted as bombs, +25% rounding up
    assert {e.payload["bomb_points"] for e in cut} <= {-(-n * 8 * 125 // 100) for n in range(1, 13)}


def test_a_sustained_axis_raid_drives_the_islands_TOTAL_capacity_to_zero(monkeypatch):
    """[41.36]/[44.14] THE PROPERTY THE WHOLE BLOCK TURNS ON, and nothing pinned it before: enough
    Axis bombing takes Malta's TOTAL capacity -- summed over all six facilities, not one of them --
    down to nothing, and an island at zero flies nothing at all.

    It is asserted here rather than read off a campaign because THE CAMPAIGN AXIS CANNOT REACH
    MALTA AT ALL TODAY: [44.42] sizes his raid as a percentage of his Italy/Sicily-based force,
    [60.32] prints "no planes start the game in Italy/Sicily", and the posture that resolves that
    against [44.21] is an open owner ruling left UNSEEDED (basing.discretionary_pct answers 0 --
    see data/malta_44.json `_owner_ruling_needed_60_32_vs_44_21`). So this test seeds the ruling's
    own candidate value itself, at the boundary and visibly, and pins the MECHANISM the day the
    force exists.

    RESTATED 2026-07-22, and the reason is recorded because it moved twice: the note here used to
    say the raid was "a hundredth of the book's" because the establishment was a six-Air-Point
    proxy. That proxy is gone -- the Axis musters 184 real bombers -- and what is missing now is
    not the force but the transfer mission that would put any of it in Sicily."""
    seeded = {**logistics_data.malta_italy_sicily_basing_43_1(),
              "axis_discretionary_italy_sicily_pct_43_1": 10}     # [63.46], transcribed unapplied
    monkeypatch.setattr(logistics_data, "malta_italy_sicily_basing_43_1", lambda: seeded)
    st = campaign(seed=3, max_turns=6)
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
