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

import game.scenario as scenario
from game import logistics_data, malta
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


# --- the Commonwealth half: levels -> 18 planes -> torpedo points -> the [41.5] CRT --------------

def test_malta_strikes_with_torpedoes_because_the_swordfish_may_not_carry_bombs():
    """[4.44A] Swordfish Mk. I Bomb '-/T8': Bombload Capacity "-" (may not carry bombs), Torpedo
    Capacity 8. Twelve of them (60.46) is 96 Torpedo Points, and the [41.5] table is entered
    through its Torpedo-Points index, not its Bomb-Points one."""
    st = campaign(seed=1, max_turns=4)
    points, weapon = malta.convoy_column_points(st)
    assert weapon == "torpedo"
    assert malta.strike_planes(st) == 12
    assert points == 96


def test_the_torpedo_index_is_a_different_column_of_the_same_table():
    """96 points is the 81-120 TORPEDO column -- the same result cells the 161-200 BOMB column
    reads -- so the identical dice give a harder result than 96 Bomb Points would."""
    codes = [(d1, d2) for d1 in range(1, 7) for d2 in range(1, 7)]
    torp = sum(_convoy_loss_pct(96, d1, d2, "torpedo") for d1, d2 in codes)
    bomb = sum(_convoy_loss_pct(96, d1, d2, "bomb") for d1, d2 in codes)
    assert torp > bomb > 0
    assert _convoy_loss_pct(96, 1, 1, "torpedo") == _convoy_loss_pct(200, 1, 1, "bomb")


def test_a_flattened_malta_sends_nothing_and_that_is_the_earned_1942_blitz():
    """[44.14] 18 planes per level: an island at zero total capacity operates no aeroplane, so it
    puts no torpedo over the lane. The invented calendar handed the Axis exactly this for four
    months of 1942 for free; now he has to bomb it."""
    st = campaign(seed=1, max_turns=4)
    flat = replace(st, air_facilities=tuple(
        replace(f, level=0) if malta.is_malta(f) else f for f in st.air_facilities))
    assert malta.capacity(flat) == 0
    assert malta.strike_planes(flat) == 0
    points, weapon = malta.convoy_column_points(flat)
    assert points == 0
    assert max(_convoy_loss_pct(points, d1, d2, weapon)
               for d1 in range(1, 7) for d2 in range(1, 7)) == 0


def test_one_level_binds_the_44_14_capacity_below_the_strike_establishment():
    """[44.14] one level handles 18 planes; the strike aircraft are served first, so 12 Swordfish
    still fly at one level -- and every plane the raids have killed is one that does not."""
    st = campaign(seed=1, max_turns=4)
    one = replace(st, air_facilities=tuple(
        replace(f, level=1 if f.id.endswith("Hal Far") else 0) if malta.is_malta(f) else f
        for f in st.air_facilities))
    assert malta.capacity(one) == 1
    assert malta.strike_planes(one) == 12
    halved = replace(one, malta_planes=15)
    assert malta.strike_planes(halved) == int(15 * 12 / 31) == 5


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


def test_the_44_42_table_reads_both_percentages_and_honours_na():
    """[44.42] dice 5 / Level IV is 100/300 -- the in-play percentage plus the strategic one, both
    of the Italy/Sicily-based force. Dice 4 / Level I is the chart's na: no forces available."""
    st = campaign(seed=1, max_turns=4)
    based = malta.italy_sicily_planes(st, 1)
    plan = malta.raid(st, "IV", 5, 1)
    assert (plan.in_play_pct, plan.strategic_pct) == (100, 300)
    assert plan.planes == based * 100 // 100 + based * 300 // 100
    assert malta.raid(st, "I", 4, 1).planes == 0                    # na


def test_the_43_1_basing_fraction_is_the_printed_one_and_falls_at_game_turn_35():
    st = campaign(seed=1, max_turns=4)
    basing = logistics_data.malta_italy_sicily_basing_43_1()
    assert (basing["before_turn_35_pct"], basing["from_turn_35_pct"], basing["change_turn"]) \
        == (75, 25, 35)
    assert malta.italy_sicily_planes(st, 34) >= malta.italy_sicily_planes(st, 35)


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
    """Both halves fire, the budget depletes, the island loses levels and aeroplanes, and the
    convoy is still being interdicted by whatever Malta has left."""
    st = campaign(seed=7, max_turns=10)
    r = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    raids = [e for e in r.events if e.kind == EventKind.MALTA_RAID_ORDERED]
    assert len(raids) == 10                            # 44.24: exactly one raid per Game-Turn
    assert sum(r.final.malta_raids.values()) == 10
    assert r.final.malta_planes <= st.malta_planes     # 41.36 only ever takes planes away
    assert [e for e in r.events if e.kind == EventKind.CONVOY_INTERDICTED]


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
                                                  EventKind.MALTA_PLANES_LOST)]
