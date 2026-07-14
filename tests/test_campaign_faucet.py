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

from game import coords, supply                                          # noqa: E402
from game.apply import apply, fold                                       # noqa: E402
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy  # noqa: E402
from game.campaign_victory import CampaignVictory                        # noqa: E402
from game.engine import _convoy_dest, determinism_signature, run         # noqa: E402
from game.events import Control, Side                                    # noqa: E402
from game.hexmap import distance                                         # noqa: E402
from game.policy import ScriptedPolicy                                   # noqa: E402
from game.scenario import (_campaign_cw_rail_line, _campaign_rail_cargo,  # noqa: E402
                           _RAIL_TONS_PER_OPSTAGE, campaign, rommels_arrival,
                           siege_of_tobruk)
from game.state import Convoy                                            # noqa: E402

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
    st = campaign(seed=1941)
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
    st = campaign(seed=1941)
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
    st = campaign(seed=1941)
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
    res = run(campaign(seed=1941, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
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
            assert e.payload["supply_id"] in line                 # only ever into a station on the line
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
    and of themselves"; game.wells.pipeline already seeds that corridor)."""
    ammo = supply.tons_to_points(_RAIL_TONS_PER_OPSTAGE, supply.AMMO)      # 1500 t / 4 t = 375
    fuel = supply.tons_to_points(_RAIL_TONS_PER_OPSTAGE, supply.FUEL)      # 1500 t x 8 = 12,000
    stores = supply.tons_to_points(_RAIL_TONS_PER_OPSTAGE, supply.STORES)  # 1500 t x 1 = 1,500

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
    st = campaign(seed=1941)
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
    clipped = supply.port_landing_cap(port, supply.AMMO)               # what the quay WOULD allow
    assert clipped < _campaign_rail_cargo(2)["AMMO"], \
        "the harbour rating no longer bites the rail cargo -- this test has stopped proving anything"


def test_the_railhead_actually_holds_fuel_now():
    """THE ACCEPTANCE, and the measurement that names the bug. Before this slice the Mersa Matruh
    railhead dump held ZERO Fuel on EVERY Game-TurN of the war: the lane delivered 500 a week, the
    lorries lifted all 500 the moment it landed, and the dump they lifted it from was empty again
    before any combat unit could trace to it. A railhead with nothing in it is not a faucet.

    With the charted tonnage on the trains and the quay out of the way, the railhead carries a real
    reservoir -- the thing a 32.16 supply trace can actually reach -- and the Commonwealth lands
    Fuel and Ammunition of the same ORDER as the Axis, instead of a thirtieth."""
    res = run(campaign(seed=1941, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    rail_landed = {"AMMO": 0, "FUEL": 0}
    st, stocked = res.initial, 0
    for e in res.events:
        if e.kind.name == "SUPPLY_ARRIVED" and e.payload.get("lane") == "CW-RAILHEAD":
            for c in rail_landed:
                rail_landed[c] += e.payload["cargo"].get(c, 0)
        st = apply(st, e)
        if e.kind.name == "TURN_ADVANCED" and st.supply("AL-Stage-Matruh").fuel > 0:
            stocked += 1

    assert stocked >= 20, f"the railhead is still a dry hole: fuelled on only {stocked}/24 turns"
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
    st = campaign(seed=1941)
    depots = {s.id: s for s in st.supplies if s.id.startswith("AL-Stage")}
    assert {"AL-Stage-Matruh", "AL-Stage-Barrani", "AL-Stage-Sollum"} <= set(depots)
    assert depots["AL-Stage-Barrani"].hex == BARRANI and depots["AL-Stage-Sollum"].hex == SOLLUM
    for d in depots.values():
        assert d.empty and not d.base       # hauled into, not pre-filled; and not a rule-57 base

    bare = replace(st, units=())            # the terrain leg, with the front line taken out of it
    truck = next(t for t in st.trucks if t.side == Side.ALLIED and t.truck_class == "heavy")
    for src, dst in ((MATRUH, BARRANI), (BARRANI, SOLLUM)):
        reach = supply.reachable_truck_moves(bare, replace(truck, hex=src))
        assert dst in reach, f"{src} -> {dst} is beyond one 30-CP truck hop"
        assert reach[dst] <= supply.truck_convoy_cpa("heavy")


def test_the_commonwealth_trucks_actually_run():
    """THE ACCEPTANCE for (B). The lorry pool must CYCLE -- load at the railhead, haul west, come
    back -- for the whole span, not drive to Cairo once and idle there. Measured against the old
    behaviour: 10 truck moves in 111 game-turns, both formations parked on Cairo at the end."""
    res = run(campaign(seed=1941, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    moves = [e for e in res.events if e.kind.name == "TRUCK_MOVED" and e.side == Side.ALLIED]
    unloads = [e for e in res.events if e.kind.name == "TRUCK_UNLOADED" and e.side == Side.ALLIED]
    assert len(moves) >= 24, f"the Commonwealth pool barely ran: {len(moves)} moves in 24 game-turns"
    assert unloads, "the Commonwealth trucks never delivered anything"

    late = [e for e in moves if e.turn > 12]
    assert late, "the Commonwealth pool froze in the first half of the run"

    for t in res.final.trucks:              # nobody drove back to the Delta and idled there
        if t.side == Side.ALLIED:
            assert distance(t.hex, CAIRO) >= distance(MATRUH, CAIRO), \
                f"{t.id} idled back at the base ({t.hex})"

    # and the haul reaches a FORWARD depot: supply is west of the railhead, where the front is
    forward = [e for e in unloads
               if _west_of_matruh(next(s.hex for s in res.initial.supplies
                                       if s.id == e.payload["supply_id"]))]
    assert forward, "nothing was ever hauled west of the railhead"

    # A forward Field Supply Depot actually FILLS. Asked of the chain, not of one named link: the
    # relay lifts from each staging depot to fill the one ahead of it, so the stock ends up at the
    # chain's HEAD and the links behind are transit nodes at zero. With the take-and-hold occupying
    # SOLLUM (game.campaign_claim) the head is AL-Stage-Sollum -- the third link, which the old code
    # could never fill at all: the Commonwealth swept past the hex for the whole war, it stayed
    # Axis-CONTROLLED, and the relay will not deliver into a hex the enemy holds.
    depots = ("AL-Stage-Barrani", "AL-Stage-Sollum")
    assert any(res.final.supply(d).fuel > 0 for d in depots), \
        f"no Field Supply Depot filled: {[(d, res.final.supply(d).fuel) for d in depots]}"


def test_the_relay_never_siphons_the_army_s_own_field_dumps():
    """A relay lifts from the supply LINE and delivers into anything forward -- it never carries
    stock back OFF a division's field dump. Measured, it did: the Commonwealth pool siphoned 1,365
    of the 1,530 Fuel Points its field dumps owned, and a dump with no fuel cannot relocate (32.24),
    so every one of them froze on the railhead. The army then advanced with no mobile supply behind
    it and could hold nothing it took -- it lost Benghazi outright. See _relay_source."""
    res = run(campaign(seed=1941, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    spine = {s.id for s in res.initial.supplies if s.id.startswith(("AL-Stage", "AX-Stage"))}
    faucets = {s.id for s in res.initial.supplies
               if any(p.hex == s.hex and p.side == s.side for p in res.initial.ports)}
    for e in res.events:
        if e.kind.name == "TRUCK_LOADED":
            assert e.payload["supply_id"] in spine | faucets, \
                f"the relay lifted out of a field dump: {e.payload['supply_id']}"

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
    scripted policy (the same one that stops it garrisoning what it takes), not a broken faucet."""
    res = run(campaign(seed=1941, max_turns=22), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
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
    assert stocked_turns == len(_COMPASS), (
        f"the Commonwealth had stocked supply west of the railhead on only "
        f"{stocked_turns}/{len(_COMPASS)} turns of Operation Compass")


def test_the_staging_chain_never_leapfrogs():
    """A Field Supply Depot is a place on the supply LINE, not a field dump that follows the army:
    the 32.3 leapfrog bridge must not walk the chain the trucks feed. (The Axis mixin already
    hides its AX-Stage waypoints for exactly this reason; the Commonwealth chain needs the same
    guard, and would otherwise unstage itself one hop at a time.)"""
    res = run(campaign(seed=1941, max_turns=16), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
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
    res = run(campaign(seed=1941, max_turns=16), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert fold(res.initial, res.events) == res.final
    for c, initial in res.final.initial_supply.items():
        on_hand = (sum(getattr(s, c.lower()) for s in res.final.supplies)
                   + sum(getattr(t, c.lower()) for t in res.final.trucks))
        assert on_hand + res.final.consumed.get(c, 0) == initial


def test_rommel_and_siege_stay_byte_identical():
    """THE HARD CONSTRAINT. The Convoy field is DEFAULTED and the depots are campaign-only, so the
    two benchmark scenarios must hash exactly as they did before this slice existed."""
    axis = ScriptedPolicy(Side.AXIS)
    baselines = {"rommel": "9339d2b308d7", "siege": "5ba4da88d107"}
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        st = build(seed=42)
        assert all(c.retarget == () for c in st.convoys)              # no rail line leaks in
        assert not any(s.id.startswith("AL-Stage") for s in st.supplies)   # no CW depot leaks in
        res = run(st, axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baselines[name], f"{name} byte-identity broken: {sig} != {baselines[name]}"
