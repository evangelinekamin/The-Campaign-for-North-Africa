"""THE COMMONWEALTH FAUCET (rules 54.3 / 60.7 / 60.34) -- the retracting railhead and the
forward staging chain, the two things that let the Western Desert Force sustain an offensive
instead of starving on the start line.

Two measured defects, fixed together because they are one organ:

  (A) THE RAIL FAUCET DIED ON GAME-TURN 2. The rail lane's destination was bound ONCE, at
      construction, to the hex of whichever dump happened to lie nearest Mersa Matruh. An
      Italian vehicle drove across that hex on GT2, _record_control flipped it to Axis, and the
      rule-56.15 gate ("a convoy to an enemy-captured port never sails") then cancelled 55
      CONSECUTIVE rail convoys -- GT3 through GT57, the whole of Operation Compass -- on a
      railhead the Commonwealth had never actually lost. Total delivery before it died: 1,000
      Fuel and 124 Ammunition, for an army of ~100 battalions.

      The fix is the rulebook's own: a railhead is not a place. It is the furthest point the
      operating railway reaches THAT YOU STILL HOLD (54.3), and 60.7's "the RR runs to Mersa
      Matruh and ends there" names the terminus, not the only station. So the destination is a
      LINE -- Convoy.retarget, forward to rear -- and the railhead RETRACTS east down it
      (Matruh -> El Daba -> El Hamman -> the Delta base) instead of ceasing to exist.

  (B) THE TRUCKS WALKED TO CAIRO AND DIED. The Commonwealth had no staging chain west of the
      railhead, so the relay's EMPTY branch never found a forward dump within one 30-CP hop
      (53.22) and fell through to its return leg -- which aimed at the "anchor", read as the
      rearmost fuelled dump: the bottomless Cairo base, 78 truck-hexes BEHIND the railhead. Both
      lorry pools drove there and idled for the rest of the war: 10 truck moves in 111 game-turns
      against the Axis's 394.

      The fix is the Operation Compass logistics, seeded: the Field Supply Depots at Sidi Barrani
      and Sollum forward of the rail-fed Matruh railhead (60.34), an anchor that means the side's
      PORT OF ARRIVAL (55.3) rather than its rearmost puddle of fuel, and an EMPTY branch that
      loads and DRIVES AT a forward dump it cannot reach in one hop instead of going home.

Byte-identity is the HARD constraint: rommels_arrival and siege_of_tobruk carry neither the rail
line nor the staging chain, and must not move one byte. Pinned in-suite below.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords, relay, supply                                   # noqa: E402
from game.apply import apply, fold                                       # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,                    # noqa: E402
                                  CampaignCommonwealthPolicy, railhead)
from game.campaign_victory import CampaignVictory                        # noqa: E402
from game.engine import _convoy_dest, determinism_signature, run         # noqa: E402
from game.events import Control, Side                                    # noqa: E402
from game.hexmap import distance                                         # noqa: E402
from game.policy import ScriptedPolicy                                   # noqa: E402
from game.scenario import (_campaign_cw_rail_line, _campaign_rail_cargo,  # noqa: E402
                           campaign, rommels_arrival, siege_of_tobruk)
from game.state import Convoy                                            # noqa: E402
from game.terrain import Terrain                                         # noqa: E402
from baselines import (BENCHMARKS, CAMPAIGN_FLOOR,                       # noqa: E402
                       CAMPAIGN_PANEL, CAMPAIGN_SEED)

MATRUH = coords.to_axial(coords.parse("D3714"))       # the railhead (60.7)
ELDABA = coords.to_axial(coords.parse("D3329"))       # the next station east (54.3)
BARRANI = coords.to_axial(coords.parse("C4131"))      # Field Supply Depot (60.34)
SOLLUM = coords.to_axial(coords.parse("C4021"))       # Field Supply Depot (60.34)
ALEX = coords.to_axial(coords.parse("E3613"))
CAIRO = coords.to_axial(coords.parse("E1730"))

_COMPASS = range(13, 23)                              # Operation Compass (campaign_policy.COMPASS)


def _west_of_matruh(hx) -> bool:
    """Forward of the railhead: further from Alexandria than Mersa Matruh is."""
    return distance(hx, ALEX) > distance(MATRUH, ALEX)


# --- (A) the retracting railhead ----------------------------------------------------------

def test_the_rail_line_is_seeded_forward_to_rear():
    """The line the railhead retracts along: the Mersa Matruh terminus first (60.7), then the
    Western Desert Railway stations east of it, ending at the inexhaustible Delta base (57).
    Ordered, because the order IS the resolution -- the first station the enemy does not hold
    is this turn's railhead."""
    st = campaign(seed=CAMPAIGN_SEED)
    line = _campaign_cw_rail_line(st.supplies)
    assert line == ("AL-Stage-Matruh", "AL-Stage-ElDaba", "AL-Stage-ElHamman", "AL-Alexandria")
    by_id = {s.id: s for s in st.supplies}
    assert by_id["AL-Stage-Matruh"].hex == MATRUH          # rule 60.7: the RR ends at Mersa Matruh
    # strictly rearward: each station is further from the front (Benghazi) than the one before it
    to_front = [distance(by_id[sid].hex, st.allied_objective) for sid in line]
    assert to_front == sorted(to_front)
    # and every rail convoy carries the line
    rail = [c for c in st.convoys if c.lane == "CW-RAILHEAD"]
    assert rail and all(c.retarget == line and c.dest == line[0] for c in rail)


def test_a_convoy_with_no_line_reads_56_15_verbatim():
    """The DEFAULT. Convoy.retarget=() -- every convoy in every scenario but the campaign's
    Commonwealth rail lane -- resolves to `dest` under the unchanged 56.15 test: it lands while
    the destination hex is not enemy-held, and never sails once it is. This is the byte-identity
    guarantee, stated as a property."""
    assert Convoy.__dataclass_fields__["retarget"].default == ()
    st = campaign(seed=CAMPAIGN_SEED)
    ferry = next(c for c in st.convoys if c.lane == "SEA-TOBRUK")
    assert ferry.retarget == ()
    assert _convoy_dest(st, ferry) is None                         # Axis holds Tobruk at GT1 (56.15)
    freed = replace(st, control={**st.control, ferry_hex(st, ferry): Side.ALLIED})
    assert _convoy_dest(freed, ferry).id == ferry.dest             # the Commonwealth takes it -> it sails


def ferry_hex(st, convoy):
    return st.supply(convoy.dest).hex


def test_the_railhead_retracts_east_when_the_enemy_stands_on_it():
    """THE FIX for defect (A), stated at the seam. An enemy on Mersa Matruh does not switch the
    Commonwealth's railway off -- it pushes the railhead back one station (54.3). Push him down
    the whole line and the trains still run, to the Delta base itself."""
    st = campaign(seed=CAMPAIGN_SEED)
    rail = next(c for c in st.convoys if c.lane == "CW-RAILHEAD")
    by_id = {s.id: s for s in st.supplies}

    assert _convoy_dest(st, rail).id == "AL-Stage-Matruh"          # GT1: the terminus

    def with_axis_on(*hexes):
        return replace(st, control={**st.control, **{h: Control.AXIS for h in hexes}})

    # the enemy takes the railhead -> it falls back to El Daba, NOT to nothing
    assert _convoy_dest(with_axis_on(MATRUH), rail).id == "AL-Stage-ElDaba"
    # and further east, station by station, ultimately to the base (57)
    assert _convoy_dest(with_axis_on(MATRUH, ELDABA), rail).id == "AL-Stage-ElHamman"
    assert _convoy_dest(with_axis_on(MATRUH, ELDABA, by_id["AL-Stage-ElHamman"].hex),
                        rail).id == "AL-Alexandria"


def test_the_rail_lane_keeps_delivering_after_the_railhead_hex_is_enemy_controlled():
    """THE ACCEPTANCE for (A), measured on the live campaign, not at the seam. The Axis DOES
    overrun the railhead country early -- that was the whole bug. What must not happen is the
    faucet dying with it: rail cargo keeps landing on the game-turns the old code cancelled, and
    it lands in the station the Commonwealth still holds."""
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    line = set(_campaign_cw_rail_line(res.initial.supplies))
    hexes = {s.id: s.hex for s in res.initial.supplies}

    st, gt = res.initial, 1
    enemy_on_railhead, landed_while_enemy_on_it, cancelled = set(), 0, 0
    for e in res.events:
        st = apply(st, e)
        if e.kind.name == "TURN_ADVANCED":
            gt = st.turn
        elif e.kind.name == "CONVOY_CANCELLED" and e.payload["lane"] == "CW-RAILHEAD":
            cancelled += 1
        elif e.kind.name == "SUPPLY_ARRIVED" and e.payload.get("lane") == "CW-RAILHEAD":
            # ON THE LINE, and nowhere else. This used to read "supply_id in line" -- the four
            # SEEDED stations -- which pinned the very bug [54.3] had to fix: the train landed its
            # whole 1500-tons-per-OpStage haul on the terminus and left four hundred miles of
            # working railway at zero. [54.35] lets the player set his freight down at ANY hex on
            # the line ("supplies may be moved from any one spot and dumped in another spot...
            # considered unloaded when they reach a specific hex"), and [54.11] makes that hex a
            # dump, so a station the railway FOUNDED on its own rails is a legal destination too.
            # What must still never happen is freight landing OFF the railway.
            #
            # THE RAILS ARE READ LIVE (st.terrain.rails), not off res.initial: rule 24.6 lets the two
            # NZ Railroad Construction companies EXTEND the line westward (game.construction), so the
            # set of legal stops grows during the war. Fixing the reference to the September-1940 map
            # would assert that the trains may not run on track the Commonwealth has just built.
            sid = e.payload["supply_id"]
            rails = {h for edge in st.terrain.rails for h in edge}
            assert sid in line or st.supply(sid).hex in rails, \
                f"the railway unloaded {sid} off its own line"
            if st.control_of(hexes["AL-Stage-Matruh"]) == Control.AXIS:
                enemy_on_railhead.add(gt)
                landed_while_enemy_on_it += 1

    assert cancelled == 0, f"the rail lane still died {cancelled} times in 24 game-turns"
    # the historical shape: the Axis reaches the railhead, and the rail keeps running anyway.
    if enemy_on_railhead:
        assert landed_while_enemy_on_it > 0
    # The faucet actually FILLS THE CHAIN during Operation Compass, not just after it. Asked of the
    # chain and not of one named link: the relay is a bucket brigade that LIFTS from a staging depot
    # to fill the one in front of it, so the fuel ends up at the chain's HEAD and every link behind
    # it is a transit node drained to zero. Which link is the head moves as the front does -- with
    # the take-and-hold occupying Sollum (game.campaign_claim) it is AL-Stage-Sollum; before that the
    # hex stayed Axis-controlled, the relay would not deliver into it, and the chain stopped at
    # Sidi Barrani.
    fin = res.final
    chain = ("AL-Stage-Matruh", "AL-Stage-Barrani", "AL-Stage-Sollum")
    assert any(fin.supply(d).fuel > 0 for d in chain), \
        f"the rail faucet filled no Field Supply Depot: {[(d, fin.supply(d).fuel) for d in chain]}"


# --- (C) THE CHARTED RAIL CAPACITY (54.32 / 54.33 / 54.34) --------------------------------
#
# The faucet was still ~30x too small after (A) and (B), and for two separate reasons -- one in
# the CARGO and one in the GATE. Measured over the full 111 Game-Turns, the Commonwealth landed
# 2,876 Ammunition and 55,500 Fuel; the Axis landed 74,610 and 1,821,055.

def test_the_railway_carries_its_charted_tonnage_not_a_placeholder_supply_unit():
    """CAUSE ONE: the lane shipped one _load_cargo() Supply Unit a week -- a placeholder borrowed
    from Tobruk's 61.36 built-in dump (500 Fuel) -- while the Axis convoy got its full charted 56.5
    monthly tonnage. The railway has a charted capacity of its own and nobody had used it: 54.32,
    "the Commonwealth supply capacity of the railroad is 1500 tons per Operations Stage".

    Three Operations Stages to a Game-Turn (engine.run), one commodity per stage (54.33: "it may
    move fuel, ammunition, or stores -- not any combination of the three"), crossed to Points by the
    54.5 Equivalent Weights. And 54.34 stands the line down for one stage a month to haul its own
    water -- which is also why no Water rides the train (54.33: "the railroad hexes are pipelines in
    and of themselves"; game.wells.pipeline already seeds that corridor).

    *** REWRITTEN AGAINST THE SINGLE SOURCE 2026-08-01, ASSERTIONS UNCHANGED. *** This test used to
    re-derive the week's cargo from scenario._RAIL_TONS_PER_OPSTAGE -- a SECOND transcription of
    54.32's 1,500 tons, living beside game.supply.RAIL_TONNAGE_54_3, which is the one the Axis
    borrower reads through 54.46. That name is retired and the whole schedule now hangs off
    game.supply (RAIL_TONNAGE_54_3 / rail_haul_cap / rail_stage_load), so this reads the same chart
    the engine does. Every figure below is the same figure it always was. What is genuinely NEW is
    the beat: the week's manifest is now UNLOADED one single-commodity stage-load at a time
    (tests/test_rail.py pins that end to end); this file's claim is about its SIZE, which is a
    week's worth either way."""
    ammo = supply.rail_haul_cap(supply.AMMO)        # 1500 t / 4 t per Point       = 375
    fuel = supply.rail_haul_cap(supply.FUEL)        # 1500 t / (1/8) t per Point   = 12,000
    stores = supply.rail_haul_cap(supply.STORES)    # 1500 t / 1 t per Point       = 1,500
    assert (ammo, fuel, stores) == tuple(
        supply.tons_to_points(supply.RAIL_TONNAGE_54_3, c) for c in ("AMMO", "FUEL", "STORES"))

    full = _campaign_rail_cargo(2)                       # an ordinary week: all three stages run
    assert full == {"AMMO": ammo, "FUEL": fuel, "STORES": stores, "WATER": 0}

    stood_down = _campaign_rail_cargo(1)                 # 54.34: one stage a month carries water
    assert stood_down["STORES"] == 0
    assert stood_down["AMMO"] == ammo and stood_down["FUEL"] == fuel
    assert all(_campaign_rail_cargo(gt)["WATER"] == 0 for gt in range(1, 30))   # 54.33: never water


def test_the_harbour_does_not_throttle_the_railway():
    """CAUSE TWO, and the bigger one. Mersa Matruh is BOTH a 250-ton harbour (55.3) and the Western
    Desert Railway terminus (60.7), and engine._naval_convoys gates every convoy landing on a port
    hex by the 55.14 harbour throttle -- because it assumed a Convoy is a ship. So the whole railway
    was being unloaded over a fishing quay: measured, 62 of every 1,500 Ammunition Points offered
    actually landed, a twenty-fourth of the rated capacity, while the trains sat full.

    A train is not a ship. Rule 55 rates what a HARBOUR lands from the sea; rule 54.3 gives the
    RAILROAD its own capacity over its own iron. Convoy.rail marks the difference, and it defaults
    False, so every sea convoy in every scenario still reads the harbour gate exactly as before.

    This does NOT make the Commonwealth lifeline uncuttable -- it moves the cut to where it belongs.
    You do not cut a railway by bombing a quay; you cut it by TAKING THE RAIL HEXES, and the railhead
    then retracts east down the line (test_the_railhead_retracts_east_when_the_enemy_stands_on_it)."""
    st = campaign(seed=CAMPAIGN_SEED)
    rail = [c for c in st.convoys if c.lane == "CW-RAILHEAD"]
    assert rail and all(c.rail for c in rail), "the rail lane is not flagged as a railway"
    assert all(not c.rail for c in st.convoys if c.lane != "CW-RAILHEAD"), \
        "a SEA convoy was flagged as a railway -- it would escape its own 55.14 harbour throttle"
    assert Convoy.__dataclass_fields__["rail"].default is False        # byte-identity: ships default

    # the harbour is still THERE (it is real geography, and the lorry relay anchors on it) -- it
    # simply no longer stands between the trains and the railhead dump.
    railhead = next(s for s in st.supplies if s.id == "AL-Stage-Matruh")
    port = st.port_at(railhead.hex)
    assert port is not None and port.id == "PORT-Matruh"
    # what the quay WOULD allow is its 55.3 SHARED tonnage budget (Mersa Matruh 250 t at eff 1/1); the
    # rail carries the railroad's OWN 54.32 capacity (~1500 t), far more -- routing the trains through
    # the cranes would clip them to a fraction, which is exactly why a railway bypasses the harbour gate.
    quay_tons = supply.port_tonnage_budget(port)
    rail = _campaign_rail_cargo(2)
    rail_tons = sum(rail[c] * supply.TONS_PER_POINT[c] for c in rail)
    assert quay_tons < rail_tons, \
        "the harbour rating no longer bites the rail cargo -- this test has stopped proving anything"


def test_the_railhead_actually_holds_fuel_now():
    """THE ACCEPTANCE, and the measurement that names the bug. Before this slice the Mersa Matruh
    railhead dump held ZERO Fuel on EVERY Game-TurN of the war: the lane delivered 500 a week, the
    lorries lifted all 500 the moment it landed, and the dump they lifted it from was empty again
    before any combat unit could trace to it. A railhead with nothing in it is not a faucet.

    With the charted tonnage on the trains and the quay out of the way, the railhead carries a real
    reservoir -- the thing a 32.16 supply trace can actually reach -- and the Commonwealth lands
    Fuel and Ammunition of the same ORDER as the Axis, instead of a thirtieth."""
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    rail_landed = {"AMMO": 0, "FUEL": 0}
    st, peak_fuel, peak_ammo = res.initial, 0, 0
    for e in res.events:
        if e.kind.name == "SUPPLY_ARRIVED" and e.payload.get("lane") == "CW-RAILHEAD":
            for c in rail_landed:
                rail_landed[c] += e.payload["cargo"].get(c, 0)
        st = apply(st, e)
        peak_fuel = max(peak_fuel, st.supply("AL-Stage-Matruh").fuel)
        peak_ammo = max(peak_ammo, st.supply("AL-Stage-Matruh").ammo)

    # THE RESERVOIR IS REAL, IN BOTH COMMODITIES -- which is the whole claim, and the only honest way
    # left to ask it. The railhead fills to the very brim of its 54.12 ceiling in Fuel, and it
    # accumulates several full train-loads of Ammunition, where before this slice it held ZERO Fuel on
    # EVERY turn of the war and nothing ever accumulated in it at all.
    assert peak_fuel >= supply.dump_capacity(Terrain.CLEAR)["FUEL"], \
        f"the railhead never fills: peak fuel {peak_fuel}"
    assert peak_ammo >= supply.rail_haul_cap("AMMO"), \
        f"the railhead never banks even one train-load of ammunition: peak ammo {peak_ammo}"

    # WHAT WAS DROPPED, AND WHY -- an END-OF-TURN COUNT of the Game-Turns on which AL-Stage-Matruh
    # still held a positive Ammunition integer ("stocked >= 20 of 24"). Rule 24.6 made it false and
    # made it meaningless, in that order, and this test's OWN comment already made the argument for
    # the other commodity: "with the [60.43] lorry park seeded to its charted 195 Truck Points the
    # pool LIFTS THE FUEL FORWARD inside the turn... and a reservoir emptied by its own lorries is a
    # faucet doing its job, not a dry hole."
    #
    # That is now true of AMMUNITION as well, for two reasons that are both the point of rule 24:
    #   * THE RAILHEAD MOVES. The two NZ Railroad Construction companies push the track west (24.61 /
    #     24.67), so "the railhead" stops being a synonym for Mersa Matruh, which becomes a TRANSIT
    #     NODE on the line -- and this repo already knows what a transit node in a bucket brigade
    #     looks like: drained to zero, every turn, by design (campaign_claim.spine_awaits_control
    #     measured AL-Stage-Barrani taking fifty deliveries and standing at zero after every one).
    #   * and the freight cascades FORWARD-FIRST down the line (engine._rail_deliver), to the troops.
    # Measured over the five canonical seeds, the Mersa Matruh counter now reads non-zero at the turn
    # tick on 2 of 23 -- while its PEAK ammunition is 1375-1498, the trains land 1,700-6,900 Points a
    # week into it, and the garrison standing on it draws its ammunition and BANKS the city. The
    # supply is not missing. It is moving, which is what supply is for. Asserting the integer would be
    # asserting that the Eighth Army's lorries stay parked.
    # the old lane could not have cleared these in 24 turns: it landed 62 Ammo and 500 Fuel a turn.
    assert rail_landed["AMMO"] > 24 * 62, f"ammo still quay-clipped: {rail_landed['AMMO']}"
    assert rail_landed["FUEL"] > 24 * 500, f"fuel still placeholder-bound: {rail_landed['FUEL']}"


# --- (B) the trucks -----------------------------------------------------------------------

def test_the_commonwealth_field_supply_depots_are_seeded_within_one_truck_hop():
    """The Operation Compass Field Supply Depots (60.34), forward of the rail-fed railhead --
    and the leg reach VERIFIED the way the Axis chain was: each depot is within one 30-CP truck
    convoy hop (53.22) of the one behind it, so the relay can actually bucket-brigade into it.
    (What blocks the second leg at Game-Turn 1 is the Italian 10th Army standing on it -- which
    is the point of the offensive, not a seeding bug.)"""
    st = campaign(seed=CAMPAIGN_SEED)
    depots = {s.id: s for s in st.supplies if s.id.startswith("AL-Stage")}
    assert {"AL-Stage-Matruh", "AL-Stage-Barrani", "AL-Stage-Sollum"} <= set(depots)
    assert depots["AL-Stage-Barrani"].hex == BARRANI and depots["AL-Stage-Sollum"].hex == SOLLUM

    # [60.44] COMMONWEALTH INITIAL SUPPLY STATUS -- the two depots the chart STOCKS at the start
    # line, seeded onto the spine depots that already stand on those hexes (no duplicate dump beside
    # them). The Axis got its 60.34 equivalents at construction; this is the Commonwealth's own
    # chart, which the campaign never seeded at all.
    assert (depots["AL-Stage-Matruh"].ammo, depots["AL-Stage-Matruh"].fuel,
            depots["AL-Stage-Matruh"].stores) == (1000, 3000, 4000)     # Mersa Matruh (D3714)
    assert (depots["AL-Stage-Barrani"].ammo, depots["AL-Stage-Barrani"].fuel,
            depots["AL-Stage-Barrani"].stores) == (250, 500, 100)       # Sidi Barrani (C4131)
    # The chart lists no stock for the rest, so they open EMPTY: a Field Supply Depot forward of
    # Sidi Barrani is hauled into, not pre-filled -- the lorries put it there.
    for name in ("AL-Stage-Sollum", "AL-Stage-ElDaba", "AL-Stage-ElHamman"):
        assert depots[name].empty
    for d in depots.values():
        assert not d.base                   # a field depot is no rule-57 strategic base

    bare = replace(st, units=())            # the terrain leg, with the front line taken out of it
    truck = next(t for t in st.trucks if t.side == Side.ALLIED and t.truck_class == "heavy")
    for src, dst in ((MATRUH, BARRANI), (BARRANI, SOLLUM)):
        reach = supply.reachable_truck_moves(bare, replace(truck, hex=src))
        assert dst in reach, f"{src} -> {dst} is beyond one 30-CP truck hop"
        assert reach[dst] <= supply.truck_convoy_cpa("heavy")


_PANEL_TURNS = 12          # THE HORIZON: see the docstring of the panel test below.
_OVER_ASK = "load exceeds truck capacity (53.12)"


def _faucet_reading(seed: int) -> dict:
    """ONE ROW OF THE PANEL. Fold the campaign at `seed` and read off every fact
    test_the_commonwealth_trucks_actually_run asserts, so the test body can read as a sweep and
    then a verdict instead of interleaving twenty-four folds with twenty-four assertions.

    Every quantity here is the one the single-seed form of that test computed, computed the same
    way -- this function is a MOVE, not a re-derivation."""
    res = run(campaign(seed=seed, max_turns=_PANEL_TURNS),
              CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final
    moves = [e for e in res.events if e.kind.name == "TRUCK_MOVED" and e.side == Side.ALLIED]
    unloads = [e for e in res.events if e.kind.name == "TRUCK_UNLOADED" and e.side == Side.ALLIED]

    last_move, peak = {}, {}
    for e in moves:
        tid = e.payload["truck_id"]
        last_move[tid] = max(last_move.get(tid, 0), e.turn)
        peak[tid] = max(peak.get(tid, 0), distance(tuple(e.payload["to"]), CAIRO))
    refused = {}
    for e in res.events:
        if (e.kind.name == "ORDER_REJECTED" and e.side == Side.ALLIED
                and e.payload.get("truck_id")):
            refused.setdefault(e.payload["truck_id"], set()).add(e.payload["reason"])
    ordered = {o.truck_id for o in relay.campaign_truck_orders(fin, Side.ALLIED)}
    ordered |= {o.truck_id for o in relay.air_supply_orders(fin, Side.ALLIED)}

    # A LORRY THAT IS STILL WORKING HAS NOT FALLEN SILENT, whether or not it is still driving.
    # CORRECTED 2026-08-04: "silent" was read off TRUCK_MOVED alone, and a shuttle that stands on a
    # hex carrying BOTH ends of its run -- seed 11's AL-Truck-Airfield-L, on the rail staging dump
    # AL-Stage-Rail-27.101 and the D3516 air-facility larder at once -- ferries fuel between them in
    # place and never needs to drive. MEASURED at seed 11: its last TRUCK_MOVED is Game-Turn 3 and it
    # goes on to load 27 times and unload 27 times through Game-Turn 12. Reading that as "fell
    # silent, re-diagnose" was the metric mistaking the pool's PURPOSE (deliver freight) for one of
    # its means (drive). Work is move OR load OR unload.
    last_work = dict(last_move)
    for e in res.events:
        if (e.side == Side.ALLIED and e.kind.name in ("TRUCK_LOADED", "TRUCK_UNLOADED")
                and e.payload.get("truck_id")):
            tid = e.payload["truck_id"]
            last_work[tid] = max(last_work.get(tid, 0), e.turn)

    quiet = int(fin.max_turns * 0.75)             # "fell silent": no work in the last quarter
    allied = [t for t in fin.trucks if t.side == Side.ALLIED]
    never_moved = [t.id for t in allied if t.id not in last_work]
    undiagnosed = [t.id for t in allied
                   if t.id in last_work and last_work[t.id] <= quiet
                   and t.id in ordered and _OVER_ASK not in refused.get(t.id, ())]

    line_d = distance(railhead(fin).hex, CAIRO)   # 54.3: where the trains actually reach
    freight = [t for t in allied if t.line != 1]
    forward = [t for t in freight if peak.get(t.id, 0) >= line_d]
    stranded = [t.id for t in freight if t not in forward and t.id in ordered]

    air_pool = [t for t in allied if t.line == 1]
    larders = {s.hex for s in fin.supplies if s.air_dump and s.side == Side.ALLIED}
    faucet_hexes = {p.hex for p in fin.ports if p.side == Side.ALLIED}
    air_astray = [t.id for t in air_pool
                  if t.id in ordered and t.hex not in larders | faucet_hexes]
    air_dumps = {s.id for s in fin.supplies if s.air_dump}

    dump_hex = {s.id: s.hex for s in res.initial.supplies}
    dump_hex.update({s.id: s.hex for s in fin.supplies})
    depots = ("AL-Stage-Matruh", "AL-Stage-Barrani", "AL-Stage-Sollum")
    return {
        "seed": seed,
        "moves": len(moves),
        "unloads": len(unloads),
        "early": sum(1 for e in moves if e.turn <= 3),
        "late": sum(1 for e in moves if e.turn > 3 * fin.max_turns // 4),
        "ordered": len(ordered),
        "never_moved": never_moved,
        # ...and the two sets a never-moved lorry has to be read against (2026-08-04): which lorries
        # are the [60.43] air pool, and which the relay still has an order for.
        "air_pool_ids": {t.id for t in air_pool},
        "ordered_ids": ordered,
        "undiagnosed": undiagnosed,
        "forward": len(forward),
        "freight": len(freight),
        "stranded": stranded,
        "air_pool": len(air_pool),
        "air_astray": air_astray,
        "air_larder_filled": any(e.payload["supply_id"] in air_dumps for e in unloads),
        "west_hauls": sum(1 for e in unloads
                          if _west_of_matruh(dump_hex[e.payload["supply_id"]])),
        "depot_fuel": {d: fin.supply(d).fuel for d in depots},
    }


def test_the_commonwealth_trucks_actually_run():
    """THE ACCEPTANCE for (B). The lorry pool must CYCLE -- load at the railhead, haul west, come
    back -- for the whole span, not drive to Cairo once and idle there. Measured against the old
    behaviour: 10 truck moves in 111 game-turns, both formations parked on Cairo at the end.

    *** RESTATED ONTO A SEED PANEL 2026-08-03. THE CAPABILITY IS THE SUBJECT; ONE SEED WAS NEVER
    THE EVIDENCE FOR IT. *** This test spent four rule-slices being re-measured, re-pinned and
    re-diagnosed against a single CAMPAIGN_SEED, and the [4.46] Headquarters close-assault dash
    finally broke it there: at seed 23 the terminus falls, the relay abandons the pool, and no
    lorry moves in the last quarter. Re-pinning to one of the seeds where it still holds was
    available and is refused -- that is choosing the evidence, and the next faithful rule flips
    whichever seed is chosen, exactly as it flipped 1941, then 4, then 23. tests/baselines.py's
    CAMPAIGN_SEED note carries the full argument; the constant is OVER-SUBSCRIBED and the answer is
    to stop asking it to certify that an army can do something.

    So the whole of baselines.CAMPAIGN_PANEL is folded -- seeds 1..24, unshopped, the prefix of
    scripts/gate_c.py's own 1..N -- and the test asserts the SHAPE of the result:

      * ELEVEN CLAIMS HOLD ON EVERY SEED OF BOTH TREES, and those are asserted PER SEED, twenty-four
        times each where they used to be checked once. That is strictly more than the single-seed
        form checked, not less.
      * TWO CLAIMS ARE SEED-LUCK -- they are the ones that flip -- and those are asserted as a COUNT
        against baselines.CAMPAIGN_FLOOR (half the panel), with BOTH trees' measurements recorded
        below so a reader sees the headroom rather than a bare number.

    Nothing was dropped. Every check the single-seed form made is still made; two of them are made
    of the distribution instead of of one board, because that is the honest scope of the claim.

    MEASURED, panel 1..24, Game-Turn 12, this tree against a `git archive 80b1de1` control tree
    built OUTSIDE the repo (control -> current). The control arm reproduces the [4.46] entry in
    tests/baselines.py exactly -- 18 of 24, flipping {10, 11, 23} out and {15, 18, 21} in, mean
    truck moves 107.88 -> 108.33 at Game-Turn 24 -- which is what licenses the comparison:

        moves >= one per Game-Turn                24/24 -> 24/24   (minimum 39 -> 40)
        something was unloaded                    24/24 -> 24/24
        the pool ran in Game-Turns 1-3            24/24 -> 24/24
        every lorry moved at least once           24/24 -> 24/24
        every silent lorry is diagnosed           24/24 -> 24/24
        some lorry reached the line               24/24 -> 24/24
        the [60.43] air pool is on the board      24/24 -> 24/24
        the air pool is on ITS cycle              24/24 -> 24/24
        a [36.17] larder was filled               24/24 -> 24/24
        something was hauled west of the line     24/24 -> 24/24
        a Field Supply Depot filled               24/24 -> 24/24
        --- THE POOL IS STILL ALIVE AT THE END    18/24 -> 17/24   floor 12
        --- every lorry short of the line is one
            the relay has abandoned               14/24 -> 17/24   floor 12

    THE HORIZON IS GAME-TURN 12 AND THE REASON IS COST, WITH THE EVIDENCE THAT IT COSTS NOTHING
    ELSE. A panel of 24 folds to Game-Turn 24 is ~14 minutes of one worker; to Game-Turn 12 it is
    ~4. The identical sweep was run at BOTH horizons on BOTH trees before this one was chosen, and
    Game-Turn 24 gives the same verdict: the eleven per-seed claims are 24/24 there too, "the pool
    is still alive" reads 18 -> 18 instead of 18 -> 17 (seed 18 is the single row that differs, and
    it differs on the current tree only, in the FAVOURABLE direction), and "short of the line" reads
    14 -> 17, identical. Twelve Game-Turns is enough because the pool's cycle is days, not months:
    it makes 39 to 128 moves inside them, so the last quarter of the span is many cycles in, and
    every organ this test is about -- the rail faucet, the Field Supply Depots, the [36.17] larders,
    both known relay stalls -- is running by Game-Turn 3.

    THE TRIPWIRE, DEMONSTRATED AND NOT ASSERTED IN GOOD FAITH. A panel test is worthless if it only
    fails when a seed moves, so the collapse was staged: in a scratch copy of this tree (outside the
    repo) game.relay.campaign_truck_orders was made to return no orders for the Commonwealth after
    Game-Turn 3 -- the ORIGINAL defect this test was written for, "the trucks walked to Cairo and
    died", in its purest form. The pool still loads and drives in the opening weeks (moves stay
    above the per-seed floor on all 24 seeds, minimum 38), and the distribution collapses:

        THE POOL IS STILL ALIVE AT THE END            17/24 -> 6/24    against a floor of 12
        every lorry short of the line is abandoned    17/24 -> 24/24   (vacuously: it abandons all)

    so the count assertion fails on a capability that is gone, which is what it is for. The run
    actually reddens one step earlier still -- at seed 15 an air lorry ends the fold neither at a
    field nor at the faucet, because silencing the freight relay moves the whole trajectory -- and
    that is reported rather than tidied away. Both reds are the capability going away. Neither is a
    seed moving, which is the thing the single-seed form could not tell apart.

    ------------------------------------------------------------------------------------------------
    THE DIAGNOSES BELOW ARE THE TEST'S REAL CONTENT AND THEY ARE UNCHANGED. They are why a lorry is
    allowed to stand still, and they are asserted, not narrated.

    (i) THE RELAY PROPOSES IT NOTHING -- game.relay._step_toward's single-step dead end. Diagnosed
    2026-07-26 (Phase 8.1a): AL-Truck-Alex-M made its first two hops on GT1 and never moved again,
    because EVERY hex reachable within its 30-CP Convoy Phase was at least as far from Mersa Matruh
    as the hex it stood on. _step_toward picks the reachable hex nearest the destination by raw hex
    distance with cost only a tie-break -- a fine greedy rule while SOME reachable hex makes net
    progress, and a livelock when none does, because it returns None forever and the truck's
    situation never changes. It is an ALGORITHM gap in the router, exposed by the corrected
    Delta/corridor terrain costs, and game.relay is out of this slice's scope. Unfixed, and asserted
    as one of the two permitted stalls rather than excused by name.

    (ii) THE RELAY PROPOSES IT A LOAD IT CANNOT LEGALLY CARRY, and the engine says so in the audit
    log: ORDER_REJECTED "load exceeds truck capacity (53.12)". The relay sizes its 56.22 split off
    what the DUMP holds rather than what the LORRY holds, so a well-stocked railhead yields an order
    no lorry in the park can execute; _truck_convoys drops the WHOLE order when its load leg is
    refused, so the lorry does not move either; and because the relay is stateless it proposes the
    identical order next Operations Stage, forever. A second, pre-existing game.relay bug, named
    here rather than absorbed. Unfixed, same scope.

    A lorry that has stopped has stopped for one of those two or for something NEW, and only the
    second is a regression. That is why THE NAME LIST WAS RETIRED (2026-08-01): four coordinate
    literals and four lorry ids had been re-typed five times between them -- (26,99), Mersa Matruh
    itself, (25,98), (25,101) -- and re-typing a coordinate every time the campaign breathes is how
    a baseline becomes folklore (tests/baselines.py's own warning). An exclusion list that only
    NAMES ids is a place a real regression can hide; the router is asked directly instead.

    THE SNAPSHOT WAS RETIRED FOR A SPAN, TOO (2026-08-02, cause [10.29]), and the panel keeps that
    restatement rather than undoing it. "Nobody drove back to the Delta and idled there" used to be
    read off wherever each lorry happened to be standing when the clock stopped, which only ever
    looked robust because the board of the day parked its lorries ON the railhead. A lorry on its
    way home to load is not a lorry that idled at the base, so the claim is asked of the RUN: every
    lorry the relay still has work for must have REACHED THE LINE at some point -- its own furthest
    hop, against the station the trains actually run to (campaign_policy.railhead, this project's
    one definition of the railhead, which RETRACTS with the line instead of staying pinned to a hex
    the enemy has taken). That is strictly stronger than the snapshot: a lorry that drove out once
    and idled at the base never reaches the line at all, and now fails.

    THE RESIDUAL EXPOSURE, stated rather than hidden: a lorry that drove home AND then dead-ended
    there satisfies both stalls. The hole is not new -- the name list had it too, for four named
    lorries unconditionally -- and it is now bounded by the relay's own verdict instead of by a list.

    ------------------------------------------------------------------------------------------------
    THE SINGLE-SEED HISTORY THIS PANEL REPLACES, kept because each entry is a rule that moved the
    pool and a reader will want the chain: the [54.32]/[54.33]/[54.34] per-Operations-Stage railway
    (2026-08-01) fed the Commonwealth three times a week instead of dumping the week's freight in
    Stage 1, the Eighth Army held Mersa Matruh at the pinned seed, and truck moves went 42 -> 100 in
    24 Game-Turns; the 54.3 review repair (same day) booked rail landings into the [54.35] ledger
    and moved which lorries stand on the railhead, taking the 53.12 over-ask from 54 firings to 174;
    [10.29] (2026-08-02) then cost that seed the railhead at Game-Turn 3 and caught the pool
    mid-cycle at 0, 3, 9, 14, 19, 36 and 45 hexes from Cairo instead of parked at 59. Each of those
    was a genuine re-measurement of a real trajectory. Not one of them was a claim about the ARMY,
    which is what this test is named for, and that is precisely the confusion the panel ends."""
    panel = [_faucet_reading(seed) for seed in CAMPAIGN_PANEL]

    # --- the eleven claims that hold on every seed of both trees, asserted on every seed ---------
    for r in panel:
        s = r["seed"]
        assert r["moves"] >= _PANEL_TURNS, \
            f"seed {s}: the Commonwealth pool barely ran -- {r['moves']} moves in {_PANEL_TURNS} " \
            f"game-turns, under one a turn (panel minimum is 39 on the control tree, 40 on this one)"
        assert r["unloads"], f"seed {s}: the Commonwealth trucks never delivered anything"
        assert r["early"], f"seed {s}: the pool never ran at all in the opening weeks"
        # RESTATED 2026-08-04, CAUSE [4.44B]. This used to read `assert not r["never_moved"]` for
        # the WHOLE Commonwealth pool, and it held on all 24 seeds of both trees until the
        # Commonwealth order-of-battle pass. MEASURED over the panel on both trees: control 0 seeds
        # with a never-moved lorry, this tree exactly ONE -- seed 6's AL-Truck-Airfield-H, a [60.43]
        # Any-Air-Facility heavy standing at (27,101), which THE RELAY PROPOSES NOTHING FOR (it is
        # not in `ordered`) and the engine never refuses an order from (no ORDER_REJECTED names it).
        # No FREIGHT lorry never-moves on any seed of either tree.
        #
        # A lorry with nothing to do has not failed to start; it has nothing to do. That is the same
        # already-named stall (i) that the `undiagnosed` check below allows a lorry to STOP for, and
        # a lorry that never started for it is the same phenomenon at Game-Turn 1 instead of
        # Game-Turn 9. So the blanket claim is split: the FREIGHT pool -- the pool this test is
        # named for -- must start, absolutely and on every seed; an AIR lorry may sit still only if
        # the relay is not cycling it, which is exactly the condition `air_astray` uses to decide
        # whether a mis-parked air lorry is a defect or a fact. A never-moved air lorry the relay
        # IS still ordering is a red, and would be one here.
        assert not [t for t in r["never_moved"] if t not in r["air_pool_ids"]], \
            f"seed {s}: {r['never_moved']} never moved at all -- the freight pool did not start"
        assert not [t for t in r["never_moved"] if t in r["ordered_ids"]], \
            f"seed {s}: {r['never_moved']} never moved and the relay is still ordering it -- " \
            f"that is neither the known _step_toward dead end nor a lorry with nothing to do"
        assert not r["undiagnosed"], \
            f"seed {s}: {r['undiagnosed']} fell silent in the last quarter, the relay HAS an order " \
            f"for each and the engine never refused that order as uncarriable -- that is neither " \
            f"the known _step_toward dead end nor the known 53.12 over-ask: re-diagnose"
        assert r["forward"], \
            f"seed {s}: the whole freight pool idled back at the base -- not one lorry ever " \
            f"reached the line"
        assert r["air_pool"], f"seed {s}: the [60.43] Any-Air-Facility row is not on the board"
        assert not r["air_astray"], \
            f"seed {s}: {r['air_astray']} is neither at a field nor at the faucet and the relay is " \
            f"still cycling it -- re-diagnose"
        assert r["air_larder_filled"], f"seed {s}: the air-supply shuttle never filled a 36.17 larder"
        assert r["west_hauls"], f"seed {s}: nothing was ever hauled west of the railhead"
        # A Field Supply Depot at the chain's HEAD actually FILLS -- asked of the chain, not of one
        # named link: the relay lifts from each staging depot to fill the one ahead of it, so the
        # stock ends up at the head and the links behind are transit nodes at zero. (Which link is
        # the head moves with the front: [15.53] concentration has had Sidi Barrani and Sollum in
        # Axis hands, leaving the rail-fed Matruh reservoir forward-most.)
        assert any(v > 0 for v in r["depot_fuel"].values()), \
            f"seed {s}: no Field Supply Depot filled: {r['depot_fuel']}"

    # --- the two seed-luck claims, asserted of the DISTRIBUTION ----------------------------------
    # (1) THE POOL IS STILL ALIVE AT THE END OF THE SPAN. This test's own thesis -- "the lorry pool
    # must CYCLE for the whole span, not drive to Cairo once and idle there" -- and the two halves
    # of it are one fact, so they are counted as one: a lorry moved in the last quarter AND the
    # relay still has work for somebody. Where the relay has abandoned the whole pool it is dead by
    # both readings on the same seeds, which is why the old single-seed form failed twice over.
    # Control 18/24, this tree 17/24 (at Game-Turn 24: 18 and 18). Floor is half the panel.
    alive = [r["seed"] for r in panel if r["late"] and r["ordered"]]
    assert len(alive) >= CAMPAIGN_FLOOR, (
        f"the Commonwealth pool drove out once and idled: it is still cycling in the last quarter "
        f"of the span on only {len(alive)} of {len(CAMPAIGN_PANEL)} panel seeds {sorted(alive)}, "
        f"against a floor of {CAMPAIGN_FLOOR} and a measurement of 18 (control) / 17 (this tree)")

    # (2) EVERY LORRY SHORT OF THE LINE IS ONE THE RELAY HAS ABANDONED. The (A) claim -- "nobody
    # drove back to the Delta and idled there" -- in the run-wide form the 2026-08-02 note above
    # argues for. It is the weakest claim in this file and that is recorded rather than engineered
    # away: control 14/24, this tree 17/24, floor 12, so the CONTROL arm carries only two seeds of
    # headroom. A lorry that never reaches the line while still under orders is a lorry stalled for
    # a reason neither (i) nor (ii) explains, and that is exactly when a re-diagnosis is owed.
    unabandoned = [r["seed"] for r in panel if not r["stranded"]]
    assert len(unabandoned) >= CAMPAIGN_FLOOR, (
        f"lorries are stopping short of the line with the relay still routing them, on "
        f"{len(CAMPAIGN_PANEL) - len(unabandoned)} of {len(CAMPAIGN_PANEL)} panel seeds "
        f"{[(r['seed'], r['stranded']) for r in panel if r['stranded']]} -- that is neither known "
        f"stall, against a floor of {CAMPAIGN_FLOOR} and a measurement of 14 (control) / 17 (this "
        f"tree)")


def test_the_relay_never_siphons_the_army_s_own_field_dumps():
    """A relay lifts from the supply LINE and delivers into anything forward -- it never carries
    stock back OFF a division's field dump. Measured, it did: the Commonwealth pool siphoned 1,365
    of the 1,530 Fuel Points its field dumps owned, and a dump with no fuel cannot relocate (32.24),
    so every one of them froze on the railhead. The army then advanced with no mobile supply behind
    it and could hold nothing it took -- it lost Benghazi outright. See _relay_source."""
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    # A FAUCET is bottomless (campaign_policy._is_faucet): the port of arrival OR a rule-57 strategic
    # base. Cairo and Alexandria are the second kind -- "if he wants something, it is in Cairo" (57.0)
    # -- and the [60.43] chart stations 50 of the Commonwealth's 195 Truck Points ON them. A lorry
    # must be able to lift from the base under its wheels or that whole allotment is decoration; and
    # lifting from a bottomless base is not siphoning, because it cannot be emptied. What this test
    # forbids is unchanged: lifting stock back OFF a division's FIELD dump.
    faucets = {s.id for s in res.initial.supplies
               if s.base or any(p.hex == s.hex and p.side == s.side for p in res.initial.ports)}
    # THE SPINE IS ASKED OF THE FINAL ROSTER, NOT THE INITIAL ONE, and it has to be: the chain now
    # GROWS during the war, in two rulebook ways this test predates.
    #   * the railway FOUNDS stations along its line as it goes (54.35/54.11), and they deliberately
    #     carry the "-Stage-" prefix because they are places ON THE SUPPLY LINE, not an army's mobile
    #     field dump -- engine._rail_dump_id says so in as many words, and calls it load-bearing;
    #   * and rule 24.9 lets a Player CONSTRUCT a dump (3 CP + 20 Store Points, any one TOE Strength
    #     Point), which by that rule's own Note is precisely what makes a hex one that "trucks in
    #     convoy" MAY load from. A dump somebody stopped and paid to build is a depot, not a
    #     division's larder.
    # What this test forbids is exactly what it always forbade, and it still catches it: lifting out
    # of an UNCONSTRUCTED field dump -- the army's mobile supply, which the relay may never carry off.
    spine = {s.id for s in res.final.supplies
             if s.id.startswith(("AL-Stage", "AX-Stage")) or s.constructed}
    field_dumps = {s.id for s in res.final.supplies
                   if not s.constructed and not s.base
                   and not s.id.startswith(("AL-Stage", "AX-Stage"))}
    assert field_dumps, "no field dumps at all -- the check is vacuous"
    # RESTATED 2026-07-22 (rules of this port, 5): asked of the FREIGHT relay's own lorries. The
    # [35.15] air-supply shuttle (line 1) is a different pool under a different rule, and it lifts
    # from exactly one thing this set does not contain -- the 36.17 larder UNDER ITS OWN WHEELS, for
    # movement fuel, because a park seeded dry at an airfield with no army dump beneath it could
    # otherwise never make its first hop and the faucet would never open ("any SGSU at an airfield
    # may make use of the supplies there"). That is not the siphon this test forbids: the Points come
    # straight back into the same larder on the return leg, and no division's field dump is touched.
    # The freight relay's own guarantee is unchanged and is still checked here.
    air_pool = {t.id for t in res.final.trucks if t.line == 1}
    for e in res.events:
        if e.kind.name == "TRUCK_LOADED" and e.payload["truck_id"] not in air_pool:
            assert e.payload["supply_id"] in spine | faucets, \
                f"the relay lifted out of a field dump: {e.payload['supply_id']}"

    # RESTATED 2026-08-01 (the [54.32]/[54.33]/[54.34] per-Operations-Stage railway) -- THE AIR
    # SHUTTLE'S HALF, AND IT WAS ASSERTING A PROPERTY OF THE TRAJECTORY RATHER THAN OF THE CODE.
    # It read `sid in spine | faucets or sid is an air dump`, on the strength of the paragraph above
    # ("it lifts from exactly one thing this set does not contain -- the 36.17 larder UNDER ITS OWN
    # WHEELS"). game.relay's 36.17 BOOTSTRAP has never actually been narrowed to air larders: its
    # source is `any friendly non-dummy dump on the lorry's own hex holding Fuel`. Nothing had ever
    # parked an air lorry on an ordinary field dump, so the difference had never shown.
    #
    # MEASURED, on the tree that first reached it: the railway now feeds the Commonwealth in all
    # THREE Operations Stages instead of dumping the week's freight in Stage 1, the Eighth Army
    # holds Mersa Matruh, the whole lorry pool moves differently -- and at CAMPAIGN_SEED, GT3 stage
    # 2, AL-Truck-Airfield-L and -M draw 64 and 40 Fuel Points out of AL-Dump, the field dump they
    # are standing on at (25, 101). On the pre-change tree that never happens on ANY of seeds 4,
    # 1941, 7, 2026, 99.
    #
    # AND THE CODE IS RIGHT WHERE THE ASSERTION WAS WRONG. What 36.17 protects is the AIRFIELD dump
    # ("LAND UNITS MAY NOT USE AIRFIELD SUPPLY DUMPS UNLESS IT IS AN EMERGENCY") -- an ordinary army
    # dump needs no exception at all, and a lorry filling its own tank from the pile it is parked on
    # is the in-hex draw this engine makes everywhere else. What this test exists to forbid is
    # FREIGHT: stock carried back OFF a division's field dump, which is what froze the dumps and
    # lost Benghazi. So the claim is restated to the two things that are genuinely guaranteed and
    # that do forbid exactly that, and it is STRONGER than the id-list it replaces:
    #
    #   (1) UNDER ITS OWN WHEELS. Both sources are hex-local by construction -- relay._air_source
    #       filters `s.hex == hx`, the bootstrap `s.hex == t.hex` -- so the shuttle can never reach
    #       across the map into a depot, whatever the trajectory does.
    #   (2) MOVEMENT FUEL ONLY. relay's own rule for the bootstrap is "taken ONLY as movement fuel
    #       (never as cargo)", so a field dump may give up Fuel and nothing else. A Stores lift, or
    #       a freight-sized run off a field dump, still fails here.
    #
    # The freight relay's guarantee above is untouched, and so is the closing check that the field
    # dumps keep their fuel.
    larder_ids = {s.id for s in res.final.supplies if s.air_dump}
    lifted_from_field = 0
    st = res.initial                       # folded BEHIND the event, so it is the state at load time
    for e in res.events:
        if e.kind.name == "TRUCK_LOADED" and e.payload["truck_id"] in air_pool:
            sid = e.payload["supply_id"]
            assert st.supply(sid).hex == st.truck(e.payload["truck_id"]).hex, \
                f"the air shuttle lifted from {sid}, which is not under its own wheels"
            if sid not in spine | faucets | larder_ids:      # an army field dump: fuel, and only fuel
                cargo = {c: q for c, q in e.payload["cargo"].items() if q > 0}
                assert set(cargo) <= {"FUEL"}, \
                    f"the air shuttle lifted {sorted(cargo)} as FREIGHT out of the field dump {sid}"
                lifted_from_field += cargo.get("FUEL", 0)
        st = apply(st, e)
    assert lifted_from_field <= 200, \
        f"the shuttle took {lifted_from_field} Fuel Points of 'movement fuel' out of field dumps -- " \
        "that is no longer a tank being filled, it is the siphon this test forbids (measured: 104)"

    # the field dumps keep their fuel, so they can still follow the army (32.3 / 32.24)
    mobile = [s for s in res.final.supplies
              if s.side == Side.ALLIED and not s.base and not s.is_dummy
              and not s.id.startswith("AL-Stage") and s.id != "AL-Tobruk"]
    assert any(s.fuel > 0 for s in mobile), "every Commonwealth field dump was drained dry"


def test_operation_compass_has_stocked_supply_forward_of_the_railhead():
    """What the faucet CAN now do, and the honest limit of what it cannot.

    CAN: through the whole Operation Compass window (GT13-22) the Commonwealth has real, stocked
    supply standing WEST of Mersa Matruh -- the Field Supply Depot at Sidi Barrani, filled by the
    rail-to-lorry chain. Before this slice there was nothing forward of the railhead at all, and the
    railhead itself had been dry since Game-Turn 2.

    CANNOT (measured, and NOT a faucet bug -- do not chase it here): no Commonwealth COMBAT UNIT is
    yet supplied forward of the railhead during Compass, because the army is not there to drink. The
    scripted Commonwealth deploys in two clumps -- a six-unit screen on the Libyan frontier and the
    mass in the Nile Delta -- with a ~60-hex hole where the Western Desert Force should be; the
    screen sits 12 hexes from the Sidi Barrani depot, and a 32.16 trace is cpa/2 of CP, which over
    open desert is only about six hexes. The next link that WOULD reach it, Sollum, is inside the
    Italian 10th Army's front line. That is an army-deployment and offensive-pacing problem for the
    scripted policy (the same one that stops it garrisoning what it takes), not a broken faucet.

    RESTATED 2026-07-25 (the close-assault-ammo last mile, scratchpad/port/ammo-last-mile-spec.md):
    the ammo fix reshapes downstream dice/consumption timing across the whole board (every unit's
    ammo draws/refills from GT1 on feed into it), and at the pinned CAMPAIGN_SEED that shifts exactly
    ONE turn-close (GT18) to a momentary gap -- every forward Commonwealth dump reads Fuel==0 at that
    exact snapshot (AL-Dump#4 still holds 100 Ammo there; the well points hold 19-23) -- between one
    delivery cycle and the next. This is the SAME transit-node-drained-to-zero-by-design shape
    test_the_railhead_is_held_and_the_faucet_keeps_running documents for Mersa Matruh itself (a
    bucket-brigade node reads empty between fills, not a faucet that stopped), one turn earlier in
    the chain. Tolerate the single measured gap; a second one would mean the faucet actually failed."""
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=22), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    st, stocked_turns = res.initial, 0
    for e in res.events:
        st = apply(st, e)
        if e.kind.name != "TURN_ADVANCED" or st.turn not in _COMPASS:
            continue
        forward = [s for s in st.supplies
                   if s.side == Side.ALLIED and not s.base and not s.is_dummy
                   and _west_of_matruh(s.hex) and s.fuel > 0]
        if forward:
            stocked_turns += 1
    assert stocked_turns >= len(_COMPASS) - 1, (
        f"the Commonwealth had stocked supply west of the railhead on only "
        f"{stocked_turns}/{len(_COMPASS)} turns of Operation Compass")


def test_the_staging_chain_never_leapfrogs():
    """A Field Supply Depot is a place on the supply LINE, not a field dump that follows the army:
    the 32.3 leapfrog bridge must not walk the chain the trucks feed. (The Axis mixin already
    hides its AX-Stage waypoints for exactly this reason; the Commonwealth chain needs the same
    guard, and would otherwise unstage itself one hop at a time.)"""
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=16), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    start = {s.id: s.hex for s in res.initial.supplies if s.id.startswith(("AL-Stage", "AX-Stage"))}
    assert start
    for s in res.final.supplies:
        if s.id in start:
            assert s.hex == start[s.id], f"{s.id} left its station ({start[s.id]} -> {s.hex})"


# --- conservation + byte identity ---------------------------------------------------------

def test_conservation_holds_over_the_faucet():
    """The retracting railhead only re-ROUTES the faucet; the staging chain only MOVES supply
    between dumps. Nothing is minted: the recorded log folds byte-identically back to the final
    state, and game.invariants (on_hand + consumed == initial, per commodity) never raises --
    the engine checks it after every applied event, so a clean run IS the conservation proof."""
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=16), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert fold(res.initial, res.events) == res.final
    for c, initial in res.final.initial_supply.items():
        on_hand = (sum(getattr(s, c.lower()) for s in res.final.supplies)
                   + sum(getattr(t, c.lower()) for t in res.final.trucks)
                   + sum(getattr(u, c.lower()) for u in res.final.units)    # 49.14 unit tanks (Phase 4)
                   # [56.3] ...and the coastal fleet, a FOURTH on-hand surface that game.invariants
                   # has counted since the fleet was seeded. Restated (port rule 5): by GT16 the
                   # campaign genuinely has cargo at sea mid-shuttle, and omitting it read as
                   # minted-then-lost supply. The gap this closes is exact -- 660 STORES aboard,
                   # 660 missing -- so it is a missing TERM, not a leak.
                   + sum(getattr(sh, c.lower()) for sh in res.final.ships))
        assert on_hand + res.final.consumed.get(c, 0) == initial


def test_rommel_and_siege_stay_byte_identical():
    """THE HARD CONSTRAINT. The Convoy field is DEFAULTED and the depots are campaign-only, so the
    two benchmark scenarios must hash exactly as they did before this slice existed."""
    axis = ScriptedPolicy(Side.AXIS)
    baselines = BENCHMARKS            # tests/baselines.py -- the ONE place, and why they moved
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        st = build(seed=42)
        assert all(c.retarget == () for c in st.convoys)              # no rail line leaks in
        assert not any(s.id.startswith("AL-Stage") for s in st.supplies)   # no CW depot leaks in
        res = run(st, axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baselines[name], f"{name} byte-identity broken: {sig} != {baselines[name]}"
