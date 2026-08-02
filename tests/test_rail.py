"""Commonwealth railroad haulage (rule 54.3; CHUNK 4, dormant).

CW rail is INFRASTRUCTURE, not a counter (like Allied coastal shipping), so it is
modelled as a direct conserving dump->dump transfer -- RAIL_HAULED {from_dump, to_dump,
commodity, qty} -- gated on both dumps sitting on the one rail network (a rail-edge
reachability set, the twin of movement.reachable), capped at 1500 tons/OpStage of ONE
commodity (54.33). Conservation holds trivially: a single transfer, grand total
unchanged. Dormant until a scenario seeds TerrainMap.rails. Axis rail 54.4 rolling-stock
is DEFERRED. These tests pin the rails edge-set, the connectivity gate, the 1500-ton
cap, the conserving fold, and the byte-identity of rail-less scenarios."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game import calendar, rail, supply, wells
from game.apply import apply
from game.engine import determinism_signature, run
from game.events import Event, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap, edge
from game.policy import ScriptedPolicy
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.scenario import campaign, coastal_corridor
from game.state import GameState, SupplyUnit, TruckFormation, VP
from game.terrain import Terrain


def _rail_state(supplies, rails) -> GameState:
    terrain = {c: Terrain.CLEAR for e in rails for c in e}
    return GameState(
        turn=1, max_turns=4, phase=Phase.LOGISTICS, active_side=Side.SYSTEM,
        seed=1, weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terrain, rails=frozenset(rails)),
        control={}, units=(), target_hex=(0, 0), supplies=tuple(supplies),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: sum(getattr(s, c.lower()) for s in supplies)
                        for c in supply.COMMODITIES})


# --- the rails edge-set + connectivity gate ----------------------------------

def test_terrainmap_rails_default_empty():
    assert TerrainMap.__dataclass_fields__["rails"].default == frozenset()
    assert coastal_corridor().terrain.rails == frozenset()


def test_rail_reachable_is_network_connectivity():
    # A-B-C rail line, plus a disconnected D-E line.
    rails = [edge((0, 0), (1, 0)), edge((1, 0), (2, 0)), edge((5, 5), (6, 5))]
    tmap = TerrainMap(terrain={c: Terrain.CLEAR for e in rails for c in e}, rails=frozenset(rails))
    reach = supply.rail_reachable(tmap, (0, 0))
    assert reach == {(0, 0), (1, 0), (2, 0)}       # the whole connected line, not the D-E line
    assert (5, 5) not in reach
    assert supply.rail_reachable(tmap, (9, 9)) == {(9, 9)}   # off-network: only itself


# --- 54.3 / 54.5 the 1500-ton cap --------------------------------------------

def test_rail_haul_cap_is_1500_tons_crossed_to_points():
    # 54.33: 1500 tons of ONE commodity per OpStage, via the 54.5 Equivalent Weights.
    assert supply.RAIL_TONNAGE_54_3 == 1500
    assert supply.rail_haul_cap("AMMO") == supply.tons_to_points(1500, "AMMO")     # 375
    assert supply.rail_haul_cap("FUEL") == supply.tons_to_points(1500, "FUEL")     # 12000
    assert supply.rail_haul_cap("STORES") == 1500


def test_the_1500_tons_is_read_off_the_chart_data_like_every_sibling_magnitude():
    """"Code reads magnitudes from data, never from literals" (CLAUDE.md). 54.32's 1,500 tons was
    the ONE 54.3x/54.4x magnitude still typed into a .py file, while its own siblings -- 54.41's
    five hexes, 54.43's 250/100 activation and 300 tons, 54.44's 900, 54.34's one dead stage --
    all come out of data/logistics_rates.json. It now comes out of the same file, from the
    commonwealth_railroad_54_3 block that sits beside the Axis borrower's."""
    from game import logistics_data
    block = logistics_data.cw_railroad_54_3()
    assert block["tons_per_opstage"] == supply.RAIL_TONNAGE_54_3
    assert "1500 tons per Operations Stage in either direction" in block["_comment"]


# --- the conserving fold -----------------------------------------------------

def test_rail_hauled_is_a_conserving_transfer():
    src = SupplyUnit("RAILHEAD", Side.ALLIED, (0, 0), ammo=0, fuel=0, stores=1500)
    dst = SupplyUnit("FORWARD", Side.ALLIED, (2, 0), ammo=0, fuel=0, stores=0)
    rails = [edge((0, 0), (1, 0)), edge((1, 0), (2, 0))]
    s = _rail_state([src, dst], rails)
    # both dumps are on the one network
    reach = supply.rail_reachable(s.terrain, src.hex)
    assert dst.hex in reach
    qty = supply.rail_haul_cap("STORES")            # 1500 pts, the full OpStage cap
    e = Event(0, 1, Phase.LOGISTICS, Side.ALLIED, "ALLIED/Logistics", EventKind.RAIL_HAULED,
              {"from_dump": "RAILHEAD", "to_dump": "FORWARD", "commodity": "STORES", "qty": qty})
    s2 = apply(s, e)
    assert s2.supply("RAILHEAD").stores == 0 and s2.supply("FORWARD").stores == 1500
    assert s2.initial_supply["STORES"] == 1500 and s2.consumed["STORES"] == 0
    check(s2)                                       # on_hand+consumed==initial holds
    on_hand = sum(su.stores for su in s2.supplies)
    assert on_hand + s2.consumed["STORES"] == s2.initial_supply["STORES"]


# --- byte-identity: no rails => every existing scenario unchanged ------------

def test_railless_scenario_byte_identical():
    a = run(coastal_corridor(seed=11), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(coastal_corridor(seed=11), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert not any(e.kind == EventKind.RAIL_HAULED for e in a.events)


# --- [54.3]/[54.35] THE RAILWAY UNLOADS ALONG ITS LINE ---------------------------------------
# The campaign seeds the Western Desert Railway (Alexandria -> Mersa Matruh) as a real rails
# edge-set, and the rail lane now sets its freight down at the stations the army is standing on
# (engine._rail_stops) instead of piling all 1500 tons/OpStage on the one forward railhead. These
# pin the geography, the "unload where the troops are" rule, and the two things that must NOT move:
# the total hauled, and the byte-identity of every rail-less scenario.

@pytest.fixture(scope="module")
def rail_run():
    return run(campaign(seed=1941, max_turns=25), CampaignAxisPolicy(), CampaignCommonwealthPolicy())


def test_the_campaign_lays_a_real_railway():
    """[54.3]/[52.22] The rails and the water pipeline are the SAME hexes -- the rulebook says so
    ("the railroad hexes are pipelines in and of themselves", 54.33), so both read one corridor."""
    st = campaign(seed=1941)
    assert st.terrain.rails, "the campaign must lay the Western Desert Railway"
    rail_hexes = {h for e in st.terrain.rails for h in e}
    pipe_hexes = {su.hex for su in st.supplies if wells.PIPE_ID_MARK in su.id}
    assert rail_hexes == pipe_hexes, "the rails and the 52.22 pipeline must be one line"


def test_the_railway_stocks_stations_along_its_length(rail_run):
    """THE BUG THIS FIXES: the lane used to land its whole haul on ONE dump (Mersa Matruh) and leave
    four hundred miles of working railway at ZERO, so the only hexes in Egypt an Eighth Army
    battalion could eat on were the Delta and that railhead."""
    fed = {e.payload["supply_id"] for e in rail_run.events
           if e.kind == EventKind.SUPPLY_ARRIVED and e.payload["lane"] == "CW-RAILHEAD"}
    assert len(fed) > 1, "the railway must stock more than the terminus"
    assert any(sid.startswith("AL-Stage-Rail-") for sid in fed), "it must found stations on its line (54.11)"


def test_a_railway_station_is_founded_where_the_army_stands(rail_run):
    """[54.35] "supplies may be moved from any one spot and DUMPED IN ANOTHER SPOT... considered
    unloaded when they reach A SPECIFIC HEX." The train stops where the troops are.

    THE LINE IS READ OFF THE FINAL MAP, NOT THE INITIAL ONE, and that is a change rule 24.6 forced,
    not a loosened assertion. The railway now GROWS: the two New Zealand Railroad Construction
    companies lay new track westward from Mersa Matruh (24.61/24.67, game.construction), so a station
    founded at Game-Turn 40 legitimately stands on a hex that was open desert at Game-Turn 1. Reading
    the rails off `campaign(seed=1941)` asserted that the railway may only stop where the railway ran
    in September 1940 -- which is the very thing rule 24 exists to end. The claim is unchanged and
    still exact: a station sits ON the line, and never anywhere else."""
    rail_hexes = {h for e in rail_run.final.terrain.rails for h in e}
    made = [e for e in rail_run.events if e.kind == EventKind.SUPPLY_DUMP_ESTABLISHED
            and e.payload["supply_id"].startswith("AL-Stage-Rail-")]
    assert made, "the railway must found stations"
    assert all(tuple(e.payload["hex"]) in rail_hexes for e in made), "a station must sit ON the line"


def test_the_railway_hauls_no_more_than_it_ever_did(rail_run):
    """The 54.32 magnitude is UNTOUCHED. This moves WHERE the freight lands, not one point of HOW
    MUCH: a game-turn of trains is still the charted 1500 tons/OpStage, crossed at 54.5.

    *** RESTATED 2026-08-01 (port rule 5), BECAUSE IT WAS BOUNDING THE WRONG UNIT. *** It asked
    whether a whole GAME-TURN's landings stayed inside _campaign_rail_cargo(5) -- the whole turn's
    manifest, which is THREE stage-loads wide. That bound is satisfied by a lane that lands all
    three stage-loads in a single Operations Stage, which is exactly what the engine was doing:
    ~4,500 tons in Stage 1, nothing in Stages 2 and 3, ever, in any campaign. The test could not
    see it, and a bound that cannot fail on the defect it is guarding proves nothing.

    54.32 rates the railroad PER OPERATIONS STAGE -- "1500 tons per Operations Stage in either
    direction" -- so the bound is restated at the beat the rule prints, and in the rule's own unit
    (TONS, crossed back through the [54.5] Equivalent Weights) rather than in Points of whatever
    commodity happened to ride. The claim is unchanged and now exact: no train ever ran heavier
    than the book's train."""
    per_stage = _landed_per_stage(rail_run)
    assert per_stage, "the railway landed nothing at all -- this test has stopped proving anything"
    for (turn, stage), cargo in sorted(per_stage.items()):
        tons = sum(q * supply.TONS_PER_POINT[c] for c, q in cargo.items())
        assert tons <= supply.RAIL_TONNAGE_54_3, \
            f"GT{turn} stage {stage}: the railway landed {tons} t, over 54.32's " \
            f"{supply.RAIL_TONNAGE_54_3}"


# --- [54.32]/[54.33]/[54.34] ONE TRAIN, ONE COMMODITY, EVERY OPERATIONS STAGE ------------------
# THE DEFECT THESE PIN, measured over full 111-turn campaigns on three seeds before the fix: the
# lane built ONE manifest per Game-Turn carrying ammunition AND fuel AND stores together (~4,500 t,
# 3,000 t on month-start turns) and engine._unload_convoys landed the whole of it in Operations
# Stage 1. Stages 2 and 3 received NOTHING, ever, in any campaign -- against a book that prints
# 1,500 tons PER OPERATIONS STAGE and "only one type of supply at a given time... not any
# combination of the three". It is the same defect already found and fixed on the Axis side of the
# same railway (54.43, game.rail / engine._axis_rail).

def _landed_per_stage(res) -> dict:
    """Every (Game-Turn, Operations Stage) the Commonwealth rail lane landed freight in, and what
    it landed. Read off Event.stage, which _Run.emit stamps from state.stage."""
    per_stage: dict = {}
    for e in res.events:
        if e.kind == EventKind.SUPPLY_ARRIVED and e.payload["lane"] == "CW-RAILHEAD":
            cargo = per_stage.setdefault((e.turn, e.stage), {})
            for c, q in e.payload["cargo"].items():
                cargo[c] = cargo.get(c, 0) + q
    return per_stage


def test_the_stage_schedule_is_one_commodity_at_the_full_54_32_capacity():
    """[54.32]/[54.33] at the source: one Operations Stage of Commonwealth railway freight is a
    SINGLE commodity at the line's whole 1,500-ton capacity, crossed to Points at [54.5]."""
    seen = set()
    for stage in range(1, calendar.OPSTAGES_PER_GAME_TURN + 1):
        load = supply.rail_stage_load(stage)
        carried = {c for c, q in load.items() if q > 0}
        assert len(carried) == 1, f"stage {stage} carries {carried} -- 54.33 forbids a mixed train"
        c = carried.pop()
        assert load[c] == supply.rail_haul_cap(c)
        assert load["WATER"] == 0, "54.33: water is piped, it never rides the train"
        seen.add(c)
    assert seen == set(supply.RAIL_COMMODITIES_54_33), \
        "a Game-Turn of trains must run each of 54.33's three types once"


def test_an_operations_stage_off_the_clock_raises_rather_than_answering():
    """The schedule is indexed by a 1-BASED Operations Stage, so `RAIL_COMMODITIES_54_33[stage - 1]`
    turns stage 0 into Python's -1 and hands back STORES, and stage -1 into -2 and hands back FUEL.
    A silent wrong answer out of the one function that decides what a train is carrying is worse
    than a crash: nothing reaches it with a bad stage today, and the day something does, 54.33 would
    be decided by an off-by-one instead of by the clock. [5.1] prints three Operations Stages a
    Game-Turn and there is no fourth, so anything off that clock is a caller's bug, not a load."""
    for stage in range(1, calendar.OPSTAGES_PER_GAME_TURN + 1):
        assert supply.rail_stage_commodity(stage) in supply.RAIL_COMMODITIES_54_33
    for bad in (0, -1, calendar.OPSTAGES_PER_GAME_TURN + 1):
        with pytest.raises(ValueError):
            supply.rail_stage_commodity(bad)
        with pytest.raises(ValueError):
            supply.rail_stage_load(bad)


def test_a_game_turn_of_trains_is_the_sum_of_its_live_stage_loads():
    """scenario._campaign_rail_cargo is now composed OF the per-stage loads rather than typing the
    tonnage a second time, and 54.34 subtracts the calendar month's dead stage from the sum."""
    from game.scenario import _campaign_rail_cargo
    for gt in (1, 2, 3, 4, 5, 11, 12):
        dead = {stage for t, stage in rail.dead_opstages_54_34(gt) if t == gt}
        want = {c: 0 for c in supply.COMMODITIES}
        for stage in range(1, calendar.OPSTAGES_PER_GAME_TURN + 1):
            if stage in dead:
                continue
            for c, q in supply.rail_stage_load(stage).items():
                want[c] += q
        assert _campaign_rail_cargo(gt) == want, f"GT{gt}"


def test_the_month_s_dead_stage_always_costs_the_stores_load():
    """*** THE COMPOSED PROXY, ASSERTED SO IT CANNOT DRIFT OUT FROM UNDER ITS DISCLOSURE. ***

    Two separately-flagged judgement calls meet here. game.rail.dead_opstages_54_34 fixes 54.34's
    dead beat at the LAST Operations Stage; game.supply.rail_stage_commodity runs 54.33's three
    types in the fixed order AMMO, FUEL, STORES. Compose them and the LAST stage is always the
    STORES stage, so THE COMMONWEALTH GIVES UP THE STORES LOAD EVERY CALENDAR MONTH AND NEVER
    AMMUNITION OR FUEL -- a systematic outcome the book leaves to the Player twice over ("Players
    must state each month which Operations Stage they are not using the railroad"; 54.33 fixes no
    running order and does not even print the types in ours).

    This test does not argue the choice is right. It pins the disclosure to the behaviour: if
    either proxy is ever changed, the paragraph in rail.dead_opstages_54_34 that says what the
    Commonwealth loses stops being true, and this fails and sends the reader to it.

    MEASURED here rather than narrated: 29 dead Operations Stages over GT1-111, 26.1% of the
    Stores lane's whole war-long lift (43,500 of 166,500 Points), and zero Ammunition or Fuel."""
    from game.scenario import _campaign_rail_cargo
    assert supply.rail_stage_commodity(calendar.OPSTAGES_PER_GAME_TURN) == supply.STORES

    turns = range(1, 112)                                  # the full campaign, GT1-111
    dead = [gt for gt in turns if rail.is_dead_stage_54_34(
        _StageProbe(gt, calendar.OPSTAGES_PER_GAME_TURN))]
    assert len(dead) == 29, f"29 calendar months in the war, {len(dead)} dead stages"

    offered = {c: 0 for c in supply.COMMODITIES}
    for gt in turns:
        for c, q in _campaign_rail_cargo(gt).items():
            offered[c] += q
    for c in supply.RAIL_COMMODITIES_54_33:
        full = len(list(turns)) * supply.rail_haul_cap(c)
        lost = full - offered[c]
        if c == supply.STORES:
            assert lost == len(dead) * supply.rail_haul_cap(c) == 43_500, \
                f"the Stores lane lost {lost} Points, not the 29 dead loads"
            assert full == 166_500 and round(100 * lost / full, 1) == 26.1
        else:
            assert lost == 0, \
                f"{c} lost {lost} Points to 54.34 -- the composed proxy has moved and the " \
                f"disclosure in game.rail.dead_opstages_54_34 is now wrong: restate it"


class _StageProbe:
    """The two fields rail.is_dead_stage_54_34 reads, without folding a state to ask a calendar
    question -- the whole point being that this composition is decided by the schedule and not by
    anything that happens on the board."""

    def __init__(self, turn: int, stage: int):
        self.turn, self.stage = turn, stage


def test_every_operations_stage_runs_a_train(rail_run):
    """THE DEFECT ITSELF. 54.32 rates the railroad per OPERATIONS STAGE and [48 VI/VII] repeats
    every facet of the First Operations Stage in the Second and Third, so the trains run three
    times a Game-Turn. Before this fix stages 2 and 3 landed nothing in 111 Game-Turns."""
    stages = {stage for _, stage in _landed_per_stage(rail_run)}
    assert stages == set(range(1, calendar.OPSTAGES_PER_GAME_TURN + 1)), \
        f"the railway only ever ran in Operations Stage(s) {sorted(stages)}"


def test_no_operations_stage_lands_two_commodities(rail_run):
    """[54.33] "The railroad may transport only one type of supply at a given time. It may move
    fuel, ammunition, or stores -- not any combination of the three." Satisfied BY CONSTRUCTION --
    the schedule puts one commodity on each stage -- so this asserts it end to end rather than
    trusting the construction, and it needs no bookkeeping in the engine to hold."""
    for (turn, stage), cargo in sorted(_landed_per_stage(rail_run).items()):
        carried = {c for c, q in cargo.items() if q > 0}
        assert len(carried) == 1, f"GT{turn} stage {stage}: mixed train {sorted(carried)}"


def test_the_calendar_months_dead_operations_stage_lands_nothing(rail_run):
    """[54.34] "For the duration of one Operations Stage per month (calendar month), the railroad
    may not be used for anything. It is transporting water forward for railroad use."

    ONE PER CALENDAR MONTH, NOT ONE PER GAME-TURN -- the parenthetical is the book's own, and the
    weekly reading would kill ~111 Operations Stages against the book's ~29. So the two halves of
    the claim are asserted together: nothing lands on a dead stage, and the LAST Operations Stage
    of every OTHER Game-Turn in the month still runs its train."""
    per_stage = _landed_per_stage(rail_run)
    turns = {t for t, _ in per_stage}
    dead = {ts for gt in turns for ts in rail.dead_opstages_54_34(gt)} & {
        (t, s) for t in turns for s in range(1, calendar.OPSTAGES_PER_GAME_TURN + 1)}
    assert dead, "no dead Operations Stage in the measured window -- nothing is being proved"
    for ts in sorted(dead):
        assert ts not in per_stage, f"GT{ts[0]} stage {ts[1]} is 54.34's dead stage and it hauled"
    live_last = [(t, calendar.OPSTAGES_PER_GAME_TURN) for t in sorted(turns)
                 if (t, calendar.OPSTAGES_PER_GAME_TURN) not in dead]
    assert all(ts in per_stage for ts in live_last), \
        "54.34 stood the railway down on a Game-Turn that is not its calendar month's first: " \
        f"{[ts for ts in live_last if ts not in per_stage]}"


def test_the_railway_conserves(rail_run):
    check(rail_run.final)


# --- THE COMMONWEALTH LANE, ASKED DIRECTLY WITH A HAND-BUILT CONVOY ----------------------------
# Everything above drives the lane THROUGH A CAMPAIGN, which is the right way to prove a schedule
# and the wrong way to prove a GUARD: a campaign only ever presents the manifest the campaign
# builds, so a refusal the manifest already makes unnecessary is never exercised and rots. These
# hand a rail convoy a manifest of their own choosing and call engine._unload_convoys on it.

def _cw_rail_run(stage=1, cargo=None, terminus_stock=None, trucks=()):
    """A one-station Commonwealth railway with a hand-built manifest on it.

    The line is a real eastward chain off the benchmark map (tests.test_rail_control._line), so
    supply.dump_capacity_at can look its hexes up; the terminus is the line's east end and there
    are no combat units, so engine._rail_stops resolves to exactly that one stop and the whole
    stage-load lands in a place the test names."""
    from game.engine import _Run
    from game.scenario import rommels_arrival
    from game.state import Convoy
    from tests.test_rail_control import _line
    line = _line(6)
    base = rommels_arrival()
    rails = frozenset(edge(line[i], line[i + 1]) for i in range(len(line) - 1))
    stock = {"ammo": 0, "fuel": 0, "stores": 0, "water": 0, **(terminus_stock or {})}
    terminus = SupplyUnit("AL-Rail-Terminus", Side.ALLIED, line[-1], **stock)
    convoy = Convoy("CW", Side.ALLIED, arrival_turn=1, lane="CW-RAILHEAD", dest=terminus.id,
                    cargo=dict(cargo or {}), rail=True)
    st = replace(base, terrain=replace(base.terrain, rails=rails), units=(),
                 supplies=(terminus,), convoys=(convoy,), stage=stage, trucks=tuple(trucks))
    r = _Run(st)
    r.convoy_manifest[convoy.id] = {"dest": terminus.id, "cargo": dict(cargo or {}), "rail": True}
    return r, convoy


def test_a_lorry_may_not_lift_what_the_commonwealth_train_has_only_just_set_down():
    """*** [54.35] ON THE COMMONWEALTH LANE -- the debt this whole slice was named to pay. ***

    "Like personnel, supplies may be moved from any one spot and dumped in another spot. Supplies
    are considered unloaded when they reach a specific hex. THEY MAY NOT BE MOVED THAT OPERATIONS
    STAGE." The Axis borrower has honoured this since 54.4 (engine._rail_free_points, three call
    sites: a second haul, a coastal ship's load, a lorry's load), and _rail_free_points' own
    docstring named the Commonwealth lane as declared debt belonging to THIS slice.

    THE DEFECT, measured before the fix with this fixture: engine._rail_deliver emitted its
    SUPPLY_ARRIVED and never called _Run.record_rail_landing, so _rail_free_points read the station
    as holding 40 free Ammunition Points and engine._truck_load ACCEPTED a 40-Point lift -- freight
    the train set down at the start of the same Operations Stage, back on the road before the end
    of it. engine.run puts _naval_convoys (which lands the train) at the head of the stage and
    _truck_convoys at the foot of it, so the window is every Operations Stage of every campaign.

    The load is deliberately far under the 54.12 dump ceiling and the truck far under its 53.12
    capacity, so what refuses the lift is 54.35 and provably nothing else."""
    from game.engine import _truck_load, _unload_convoys
    from game.policy import TruckOrder
    r, convoy = _cw_rail_run(stage=1, cargo={"AMMO": 40, "FUEL": 0, "STORES": 0, "WATER": 0})
    lorry = TruckFormation("AL-Truck", Side.ALLIED, r.state.supply("AL-Rail-Terminus").hex,
                           truck_class="medium", points=100)
    _unload_convoys(r, [convoy])
    assert r.state.supply("AL-Rail-Terminus").ammo == 40, "the train did not land its load"

    r.state = replace(r.state, trucks=(lorry,))
    order = TruckOrder("AL-Truck", load_from="AL-Rail-Terminus", load={"AMMO": 40})
    assert _truck_load(r, Side.ALLIED, "ALLIED/Logistics", order,
                       r.state.truck("AL-Truck")) is False
    assert any("may not be moved that Operations Stage (54.35)" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)
    assert r.state.supply("AL-Rail-Terminus").ammo == 40, "the lorry took it anyway"


def test_54_35_on_the_commonwealth_lane_pins_the_freight_and_not_the_station():
    """The mirror of the Axis test of the same name, and the half that keeps the rule honest: what
    was ALREADY standing on the platform is not supply that "reached a specific hex" this
    Operations Stage, so a station the train calls at keeps working. 25 Points were there before
    the train; 40 came off it; exactly 25 may be lifted."""
    from game.engine import _truck_load, _unload_convoys
    from game.policy import TruckOrder
    r, convoy = _cw_rail_run(stage=1, cargo={"AMMO": 40, "FUEL": 0, "STORES": 0, "WATER": 0},
                             terminus_stock={"ammo": 25})
    lorry = TruckFormation("AL-Truck", Side.ALLIED, r.state.supply("AL-Rail-Terminus").hex,
                           truck_class="medium", points=100)
    _unload_convoys(r, [convoy])
    assert r.state.supply("AL-Rail-Terminus").ammo == 65
    r.state = replace(r.state, trucks=(lorry,))
    ok = _truck_load(r, Side.ALLIED, "ALLIED/Logistics",
                     TruckOrder("AL-Truck", load_from="AL-Rail-Terminus", load={"AMMO": 25}),
                     r.state.truck("AL-Truck"))
    assert ok is True, "the station's own pre-existing stock was pinned too"
    assert r.state.supply("AL-Rail-Terminus").ammo == 40      # the 25 left; the train's 40 stayed
    assert _truck_load(r, Side.ALLIED, "ALLIED/Logistics",
                       TruckOrder("AL-Truck", load_from="AL-Rail-Terminus", load={"AMMO": 1}),
                       r.state.truck("AL-Truck")) is False    # ...and not one Point more


def test_the_54_34_refusal_in_the_unloader_stops_a_train_the_manifest_still_offers():
    """*** THE DOUBLE GATE, RESOLVED AND PINNED. *** [54.34] "For the duration of one Operations
    Stage per month (calendar month), the railroad may not be used for anything."

    engine._unload_convoys refuses to run a train on the dead stage, AND scenario._campaign_rail_
    cargo already leaves that stage's load off the week's manifest -- so in a campaign the engine
    guard is byte-inert (neutered alone at its own call site, seeds 1941/4/7 replay byte-identical;
    on a month-start Game-Turn the manifest is exhausted by stage 3 and _unload_convoys' own
    "nothing left to land" continue fires before the guard is even reached).

    THE DECISION, deliberately: THE MANIFEST IS THE REAL ONE and this guard is defence in depth.
    54.34's own sentence is a DECLARATION made in advance -- "Players must state each month which
    Operations Stage they are not using the railroad" -- so the seat that makes the week's plan is
    where the declaration belongs, and the plan is the manifest. What the engine owes is that the
    declaration is HONOURED whoever built the manifest, which is this guard. Neither is deleted:
    a rule that is only true because one caller happens to be careful is not encoded at all.

    And a guard no test can reach is a guard that will rot, so this reaches it the only way a
    campaign cannot: by handing the unloader a manifest that still carries the dead stage's load."""
    from game.engine import _unload_convoys
    last = calendar.OPSTAGES_PER_GAME_TURN
    dead_gt = next(gt for gt in range(1, 20) if (gt, last) in rail.dead_opstages_54_34(gt))
    carried = supply.rail_stage_commodity(last)
    cargo = {c: (40 if c == carried else 0) for c in supply.COMMODITIES}

    r, convoy = _cw_rail_run(stage=last, cargo=cargo)
    r.state = replace(r.state, turn=dead_gt)
    assert rail.is_dead_stage_54_34(r.state), "the fixture is not standing on a dead stage"
    _unload_convoys(r, [convoy])
    assert r.state.supply("AL-Rail-Terminus").empty, \
        "54.34 says the railroad may not be used for ANYTHING this Operations Stage"
    assert not r.events, "a dead stage founded a station or emitted an arrival"
    assert r.convoy_manifest["CW"]["cargo"][carried] == 40, \
        "the dead stage consumed the load it was forbidden to carry"

    # ...and the SAME manifest on the SAME stage of a live Game-Turn does run its train, so what
    # refused it above is 54.34 and not the fixture.
    live_gt = next(gt for gt in range(1, 20) if (gt, last) not in rail.dead_opstages_54_34(gt))
    r2, convoy2 = _cw_rail_run(stage=last, cargo=cargo)
    r2.state = replace(r2.state, turn=live_gt)
    _unload_convoys(r2, [convoy2])
    assert r2.state.supply("AL-Rail-Terminus").stores == 40


def test_an_empty_stage_load_founds_no_station_and_the_stage_s_remainder_expires():
    """The 54.34 guard's two siblings in the same block of engine._unload_convoys, also byte-inert
    in a campaign for the same reason, also reached here directly rather than deleted.

    (a) `if cargo.get(commodity, 0) > 0` -- WITHOUT it, _rail_deliver is called for a train
        carrying nothing, and _rail_deliver founds its stations (SUPPLY_DUMP_ESTABLISHED) BEFORE it
        looks at any quantity. An empty train would build railway stations down the line.
    (b) `cargo[commodity] = 0` -- a stage's train is a stage's train, so whatever the 54.12 dump
        ceilings would not take EXPIRES with the stage instead of rolling into the next one. Driven
        here by a station already at its Ammunition ceiling: the train calls, lands nothing, and
        the manifest entry is spent all the same."""
    from game.engine import _unload_convoys
    r, convoy = _cw_rail_run(stage=1, cargo={"AMMO": 0, "FUEL": 0, "STORES": 0, "WATER": 0})
    _unload_convoys(r, [convoy])
    assert not r.events, "an empty stage-load founded a station or landed freight"

    full = supply.dump_capacity_at(r.state, r.state.supply("AL-Rail-Terminus").hex)["AMMO"]
    assert full > 0, "the fixture's terminus has no 54.12 Ammunition ceiling to fill"
    r2, convoy2 = _cw_rail_run(stage=1, cargo={"AMMO": 40, "FUEL": 0, "STORES": 0, "WATER": 0},
                               terminus_stock={"ammo": full})
    _unload_convoys(r2, [convoy2])
    assert r2.state.supply("AL-Rail-Terminus").ammo == full, "the 54.12 ceiling was overrun"
    assert r2.convoy_manifest["CW"]["cargo"]["AMMO"] == 0, \
        "the stage's undelivered remainder rolled forward instead of expiring with its train"
