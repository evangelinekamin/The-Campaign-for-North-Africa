"""[42.1] TRANSFER MISSIONS and [60.32] THE MUSTER ON THE MAP -- how Sicily becomes a decision.

For two blocks this engine carried an open owner ruling in the shape of a percentage. [60.32]
prints "no planes start the game in Italy/Sicily"; [44.21]/[44.25]/[44.27] make an Italy/Sicily
base the precondition for any Axis raid on Malta; and the engine had no way for an aeroplane to
change base at all, so a number in a data file stood in for the whole of the Axis Player's air
posture. The owner ruled on 2026-07-22 that the two rules were never in conflict -- [60.32] is a
SET-UP rule about Game-Turn 1 -- and the book prints the bridge:

  [42.11] "A transfer mission is flying a plane FROM ONE AIR FACILITY TO ANOTHER."
  [42.13] "Planes flying transfer missions MAY DOUBLE THEIR RANGE. Transfer is a ONE-WAY FLIGHT."
  [42.14] "Planes flying transfer NEED NOT BE REFITTED to fly... TRANSFER MISSIONS CONSUME FUEL."
  [42.15] "Transfers are flown ONLY IN TACTICAL LAND SUPPORT PHASES of the Operations Stage."
  [37.12] "...counts the distance in hexes... FROM THE BASE/AIR FACILITY to the target hex. If the
          number of hexes FALLS WITHIN THE RANGE of the plane, the plane may be flown to that hex."
  [37.4]  the Air Distance Chart: Benghazi 96 hexes to Sicily, Derna 105, and P -- "not possible to
          traverse air distance directly" -- from Tobruk, Bardia, Mersa Matruh and Alexandria.

So the Axis's Malta option has a geography, and it lives at Benghazi.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import game.air as air
import game.basing as basing
import game.logistics_data as logistics_data
import game.malta as malta
import game.roster as roster
from game.campaign_policy import (CampaignAxisPolicy, CampaignCommonwealthPolicy,
                                  air_transfer_doctrine, malta_raid_doctrine)
from game.engine import _air_transfer, _Run, determinism_signature, run
from game.events import EventKind, Side
from game.oob import charted_air_facilities
from game.policy import Policy
from game.scenario import campaign

AXIS_STRIKE = "AXIS/LAND/strike"


class _Transfer(Policy):
    """An Axis Player who asks for exactly `planes` (negative = fly them home)."""

    def __init__(self, planes: int):
        super().__init__()
        self.planes = planes

    def air_transfer(self, state, based, available):
        return self.planes


def _run_transfer(state, planes):
    r = _Run(state)
    _air_transfer(r, {Side.AXIS: _Transfer(planes), Side.ALLIED: Policy()})
    return r


# --- [37.4] the chart ---------------------------------------------------------------------------

def test_the_37_4_air_distance_chart_is_the_printed_one_and_P_is_not_a_number():
    """PDF page 71, rendered at 300 dpi and read with eyes. Section B is the only place the book
    prints a distance from Africa to Sicily or Italy. A prohibited pairing is carried as null, never
    as a large number, so that a range test can never quietly pass one."""
    b = logistics_data.air_distance_37_4()["n_mediterranean_off_map_areas_B"]
    assert b["Benghazi"] == {"Crete": 62, "Malta": 84, "Sicily": 96, "Italy": 138}
    assert b["Derna"] == {"Crete": 27, "Malta": 108, "Sicily": 105, "Italy": 147}
    assert b["Tobruk"] == {"Crete": 48, "Malta": 126, "Sicily": None, "Italy": None}
    assert b["Bardia"]["Sicily"] is None and b["Alexandria"]["Malta"] is None
    assert b["Malta"]["Sicily"] == 24
    # the OCR in docs/rules/90-charts drops a cell in section A; both are transcribed here
    a = logistics_data.air_distance_37_4()["axis_off_map_n_african_areas_A"]
    assert a["Malta"] == {"Tripolitania": 60, "Tripoli": 42, "Gabes": 58, "Tunis": 52}
    assert a["Benghazi"]["Tunis"] == 136


def test_43_25_the_transfer_targets_are_italy_and_sicily_and_never_crete():
    """[43.25] "Bombers based in Italy/Sicily... may also be used in raids on Malta" -- and 43.24
    gives the Crete contingent the opposite treatment. A transfer flown to raid Malta may therefore
    only be flown to the two boxes 43.25 names."""
    assert set(basing.mediterranean_areas()) == {"Sicily", "Italy"}
    assert basing.transfer_distance("Benghazi") == 96          # the nearer of 96 and 138
    assert basing.transfer_distance("Tobruk") is None          # P to both
    assert basing.transfer_distance("Mersa Matruh") is None


def test_42_13_the_transfer_range_is_the_charted_range_doubled():
    """[42.13]/[34.11] "Planes flying transfer missions may double their range." Averaged over the
    establishment and FLOORED (roster.range_per_plane), which is the conservative direction for a
    test that decides whether a flight is legal at all: the Regia Aeronautica's bomber arm averages
    110 hexes, so a transfer reaches 220 and Sicily is 96 away."""
    assert roster.range_per_plane(Side.AXIS, "strike") == 110
    assert basing.transfer_range(Side.AXIS, "strike") == 220
    assert basing.transfer_range(Side.AXIS, "strike") > basing.transfer_distance("Benghazi")


# --- [37.12] where he may fly it from -----------------------------------------------------------

def test_the_departure_points_are_benghazis_two_airfields_and_he_must_hold_them():
    """[37.12]/[36.15] FOUR conditions and each is printed: the chart must print a distance at all,
    it must fall within the transfer range, the side must HOLD an undestroyed air facility there
    ("air facilities may be used by anyone who controls them", 60.5), and the aeroplanes flying
    must be able to use a facility of that KIND (36.3/36.4 -- the next test).

    RESTATED 2026-07-22, NOT WEAKENED. It asserted a third departure, ("Derna", "B5925-Derna",
    105), which was wrong on the book: [60.5] puts exactly one facility at Derna and it is a FLYING
    BOAT ALIGHTING AREA, which 36.3/36.4 forbid to normal aircraft. The assertion enshrined the
    defect. Derna stays a transcribed departure PLACE -- the [37.4] chart prints its distance -- and
    the rule, not the transcription, is what refuses the flight."""
    st = campaign(seed=7, max_turns=3)
    got = basing.departures(st, Side.AXIS, "strike")
    assert [(d.place, d.facility, d.distance) for d in got] == [
        ("Benghazi", "A4728-El Berca", 96), ("Benghazi", "A4829-Benina", 96)]
    # 36.14: a field at zero Capacity Level "is considered destroyed for all purposes"
    gone = {d.facility for d in got}
    flat = replace(st, air_facilities=tuple(
        replace(f, level=0) if f.id in gone else f for f in st.air_facilities))
    assert basing.departures(flat, Side.AXIS, "strike") == ()
    # ...and with nowhere to fly from, no transfer happens however loudly the policy asks
    assert not _run_transfer(flat, 40).events


def test_36_3_a_bomber_may_not_take_off_from_a_flying_boat_alighting_area():
    """[36.3] "FLYING BOAT BASINS MAY NOT BE USED FOR NORMAL AIRCRAFT", and [36.4] "Alighting Areas
    are the same as flying boat basins" but for capacity and artillery immunity. [34.4] is the
    mirror clause, and the pair is two-way: the boat is confined to water and the water is closed
    to the landplane.

    THIS IS THE REGRESSION THE 2026-07-22 REVIEW FOUND. B5925-Derna is an alighting area; the
    [37.4] chart prints 105 hexes from Derna to Sicily, well inside the doubled range; and with no
    facility-KIND filter the transfer beat offered it to the S.M. 79s. It bit exactly where the
    block advertised its sharpest consequence -- lose Benghazi's two fields and the Axis was
    supposed to have no way to Sicily at all, which was false while Derna still answered."""
    st = campaign(seed=7, max_turns=3)
    derna = next(f for f in st.air_facilities if f.id == "B5925-Derna")
    assert derna.kind == "alighting"
    assert not roster.role_may_base(Side.AXIS, "strike", "alighting")   # 36.3/36.4
    assert not roster.role_may_base(Side.AXIS, "strike", "basin")
    assert roster.role_may_base(Side.AXIS, "strike", "airfield")
    assert "B5925-Derna" not in {d.facility for d in basing.departures(st, Side.AXIS, "strike")}
    # ...so losing Benghazi really does end the Malta option, which is what the block claims
    benghazi = ("A4728-El Berca", "A4829-Benina")
    lost = replace(st, air_facilities=tuple(
        replace(f, level=0) if f.id in benghazi else f for f in st.air_facilities))
    assert basing.departures(lost, Side.AXIS, "strike") == ()
    assert not _run_transfer(lost, 40).events
    # and the mirror, from the chart's own class cell: the Cant Z. 501 is refused the airfield
    assert roster.may_base("Cant Z. 501 Gabbiano", "basin")
    assert not roster.may_base("Cant Z. 501 Gabbiano", "airfield")
    assert not roster.may_base("S.M. 79 Sparviero", "basin")


def test_37_24_no_more_planes_fly_from_a_field_than_its_capacity_level_allows():
    """[37.24] "NO PLANES MAY FLY IN EXCESS OF THE AIR FACILITY'S CAPABILITY LEVEL." [36.12] fixes
    an airfield at six squadrons and [35.23] an Italian Squadriglia at twelve aeroplanes, so a
    level-6 field launches seventy-two and no more; 36.14 makes the CURRENT level the live number.

    MEASURED BEFORE THIS BOUND (campaign seed 4): single AIR_TRANSFERRED events of 74, 105 and 116
    aeroplanes out of A4728-El Berca, 1.6x its printed ceiling -- the code held both the level and
    the chart and read the level only as a held/destroyed flag."""
    # [59.32]'s Refitted column stands only 47 of the 184 bombers up at set-up, which is fewer than
    # one field's ceiling -- so the whole establishment is made serviceable here (38.31's blanket
    # "at the start of a Scenario, all planes are considered refitted") to put the FIELD in front of
    # the readiness bound. Otherwise this test would pass on 38.31 and prove nothing about 37.24.
    st = replace(campaign(seed=7, max_turns=3), air_unfit={})
    got = basing.departures(st, Side.AXIS, "strike")
    assert [d.capacity for d in got] == [72, 72]           # two level-6 fields, 6 x 12
    # a redeployment bigger than one field spills to the next, one mission per field (42.11)
    r = _run_transfer(st, 100)
    moved = [e.payload for e in r.events if e.kind == EventKind.AIR_TRANSFERRED]
    assert [(p["departure"], p["planes"]) for p in moved] == [
        ("A4728-El Berca", 72), ("A4829-Benina", 28)]
    assert moved[-1]["based"] == 100
    # 36.14: bomb the field down and the ceiling comes down with it, in whole squadrons
    hurt = replace(st, air_facilities=tuple(
        replace(f, level=2) if f.id == "A4728-El Berca" else f for f in st.air_facilities))
    assert basing.departures(hurt, Side.AXIS, "strike")[0].capacity == 24
    assert [e.payload["planes"] for e in _run_transfer(hurt, 100).events
            if e.kind == EventKind.AIR_TRANSFERRED] == [24, 72]


def test_the_commonwealth_has_no_mediterranean_box_to_transfer_to():
    """[43.1] is headed "AXIS MEDITERRANEAN BOMBER BASE REQUIREMENTS"; the Commonwealth's basing is
    rule 36's, entirely on the map. The beat is the Axis's, so a Commonwealth policy that asked
    would be asking nobody -- there is no Allied leg in engine._air_transfer at all."""
    st = campaign(seed=7, max_turns=3)
    r = _Run(st)
    _air_transfer(r, {Side.AXIS: Policy(), Side.ALLIED: _Transfer(40)})
    assert not r.events


# --- [42.14] what the flight costs, and what it moves --------------------------------------------

def test_the_outbound_transfer_draws_38_24_fuel_and_moves_the_bombers_off_the_desert():
    """[42.14] "Transfer missions consume fuel", at 34.17's Fuel Consumption Rating like any other
    sortie and out of the 36.17 air-facility larder (38.24). What it BUYS is the whole point: those
    bombers are in Sicily for rule 44 and gone from Africa for rule 41."""
    st = campaign(seed=7, max_turns=3)
    before = basing.africa_planes(st, Side.AXIS, 1)
    r = _run_transfer(st, 20)
    moved = [e for e in r.events if e.kind == EventKind.AIR_TRANSFERRED]
    fuel = [e for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]
    assert len(moved) == 1 and fuel
    p = moved[0].payload
    assert p["planes"] == 20 and p["to_mediterranean"] and p["based"] == 20
    assert p["departure"] == "A4728-El Berca" and p["distance"] == 96 and p["range"] == 220
    assert p["fuel"] == sum(e.payload["qty"] for e in fuel)
    assert p["fuel"] == 20 * air.fuel_per_plane(Side.AXIS, "strike")
    assert basing.transferred_planes(r.state, Side.AXIS, "LAND", "strike") == 20
    assert basing.italy_sicily_planes(r.state, 1) == 20
    assert basing.africa_planes(r.state, Side.AXIS, 1) == before - 20   # 39.19/43.11: not both
    assert malta.raid(r.state, "IV", 5, 1).bomb_points > 0              # 44.42 has a force at last


def test_the_return_transfer_is_free_because_36_5_feeds_the_box():
    """[36.5](a) An off-map air facility -- which the Italy/Sicily boxes are -- has "UNLIMITED
    SUPPLIES FOR AIRPLANE MAINTENANCE AND REPAIR". So the flight home draws nothing from an African
    dump, and 42.14's unconditional "transfer missions consume fuel" is still honoured: the fuel
    comes out of a box the book says cannot run out.

    RESTATED 2026-07-22, AND THE RESTATEMENT IS THE FINDING. This test and the code both cited
    [43.21] -- "GERMAN Bombers based in Italy/Sicily and Crete do not need SGSU's... The Axis
    Player does not expend fuel or ammo for these planes" -- whose printed subject is a
    NATIONALITY. The campaign force is Italian to the last aeroplane ([60.32] musters no German
    type), so 43.21 had nothing to exempt: it was the same nationality-blindness the sibling block
    corrected for 43.12 one commit earlier. 36.5(a) binds on the FACILITY, which is what he is
    flying out of, and is the citation that should have been given. The behaviour is unchanged and
    the reason for it is now the right one.

    THE FLIGHT HOME IS ALSO A FLIGHT, which is the other half of the repair: it is tested against
    the same [37.4] chart, the same 42.13 range and the same [37.24] ceiling as the outbound leg,
    and it names the field it lands at. Before, it named none and was tested against nothing."""
    st = campaign(seed=7, max_turns=3).with_air_mediterranean(AXIS_STRIKE, 30)
    r = _run_transfer(st, -12)
    moved = [e for e in r.events if e.kind == EventKind.AIR_TRANSFERRED]
    assert not [e for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]
    assert moved[0].payload["planes"] == 12 and not moved[0].payload["to_mediterranean"]
    assert moved[0].payload["based"] == 18 and moved[0].payload["fuel"] == 0
    # 37.12/37.24: the landing field is named, and it is one the chart and the rule both admit
    assert moved[0].payload["departure"] == "A4728-El Berca"
    assert moved[0].payload["distance"] == 96 and moved[0].payload["capacity"] == 72
    assert basing.italy_sicily_planes(r.state, 1) == 18
    # ...and he may never bring home more than he sent
    assert sum(e.payload["planes"] for e in _run_transfer(st, -500).events
               if e.kind == EventKind.AIR_TRANSFERRED) == 30
    # ...nor land anywhere at all once [37.4]/[36.3] leave him no field in Africa to land at
    benghazi = ("A4728-El Berca", "A4829-Benina")
    lost = replace(st, air_facilities=tuple(
        replace(f, level=0) if f.id in benghazi else f for f in st.air_facilities))
    assert not _run_transfer(lost, -12).events


def test_39_19_the_bombers_that_raided_malta_may_not_fly_home_the_same_game_turn():
    """[39.19] "A plane flying a mission in an Operations Stage may not fly in the Strategic Phase
    of that Game-Turn AND VICE VERSA." The Malta raid IS the Strategic Phase (44.24) and the flight
    home is a [42.1] mission flown in an Operations Stage (42.15), so the aeroplanes that bombed the
    island stay in the box until the Game-Turn ends.

    THIS IS THE BLOCK'S OWN CENTRAL TRADE, AND IT LEAKED. engine._malta_africa booked the AFRICAN
    contingent into GameState.air_strategic and always did; nothing booked the ITALY/SICILY force
    that actually flew the raid. Measured on campaign seed 4, Game-Turn 2: MALTA_RAID_ORDERED with
    56 based bombers and 1,960 Bomb Points, then AIR_TRANSFERRED bringing all 56 home in the SAME
    Game-Turn, then two AIR_STRIKE_RESOLVED and an AIR_SQUADRON_UNFIT of ten over the desert. The
    doctrine's return trigger fires precisely BECAUSE the raid knocked Malta down, so the leak was
    not a corner case -- it was the turn the raid happened, every time."""
    st = campaign(seed=7, max_turns=3).with_air_mediterranean(AXIS_STRIKE, 30)
    med = basing.mediterranean_squadron(Side.AXIS, "strike")
    assert basing.mediterranean_strategic(st, Side.AXIS, "strike") == 0
    flew = st.with_air_strategic(med, 30)                  # the whole box raided Malta this turn
    assert basing.mediterranean_strategic(flew, Side.AXIS, "strike") == 30
    assert not _run_transfer(flew, -30).events             # ...so not one of them comes home
    # ...and a raid that used only part of the box leaves the rest free to fly (39.19 is per plane)
    part = st.with_air_strategic(med, 18)
    assert [e.payload["planes"] for e in _run_transfer(part, -30).events
            if e.kind == EventKind.AIR_TRANSFERRED] == [12]


def test_39_19_binds_end_to_end_on_the_campaign_the_review_measured():
    """The same rule from the outside, on the run the defect was found in: in no Game-Turn does the
    Axis both raid Malta with his based bombers and fly those same bombers home."""
    st = campaign(seed=4, max_turns=6)
    r = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    raided = {e.turn: e.payload["med_strategic"] for e in r.events
              if e.kind == EventKind.MALTA_RAID_ORDERED and not e.payload["cancelled"]}
    assert any(v > 0 for v in raided.values()), "no raid ever flew, so nothing was tested"
    home = [e for e in r.events
            if e.kind == EventKind.AIR_TRANSFERRED and not e.payload["to_mediterranean"]]
    assert home, "the Axis never brought anybody home, so nothing was tested"
    for e in home:
        # `based` is the box AFTER the flight: whatever 39.19 committed must still be standing in it
        assert e.payload["based"] >= raided.get(e.turn, 0), (
            f"GT{e.turn}: {raided.get(e.turn)} bombers raided Malta and the box is down to "
            f"{e.payload['based']}")


def test_the_order_is_revalidated_against_38_31_and_39_19_like_every_other():
    """A policy is asked, never trusted. He may send no more than stand SERVICEABLE in Africa and
    are not already committed to this Game-Turn's Strategic Phase (39.19).

    THE SERVICEABILITY BOUND IS STRICTER THAN THE BOOK ON PURPOSE, and engine._air_transfer argues
    it: 42.14 lets an unrefitted plane fly a transfer, but our 38.31 ledger cannot follow an
    aeroplane to Sicily, so an unfit bomber flown to the box would leave its unserviceability behind
    in Africa and the [44.42] raid would count it fit. Refusing the flight is the smaller error."""
    st = campaign(seed=7, max_turns=3)
    standing = air.ready_planes(st, Side.AXIS, "LAND", "strike",
                                basing.establishment(st, Side.AXIS, "LAND", "strike"))
    r = _run_transfer(st, 10_000)
    assert r.events[-1].payload["planes"] == standing
    assert basing.italy_sicily_planes(r.state, 1) == standing
    # a policy that asks for nothing moves nothing, and emits nothing
    assert not _run_transfer(st, 0).events


def test_a_dry_larder_grounds_the_transfer_because_37_15_needs_fuel():
    """[37.15] "No plane may fly unless it has been FUELED." 42.14 exempts a transfer from the
    REFIT requirement and from nothing else, so an air force with an empty 36.17 larder cannot
    redeploy -- which is the [42.14] half of the same logistics grip 38.24 already has on bombing."""
    st = campaign(seed=7, max_turns=3)
    dry = replace(st, supplies=tuple(
        replace(su, fuel=0) if su.air_dump and su.side == Side.AXIS else su for su in st.supplies))
    assert not _run_transfer(dry, 40).events
    assert basing.italy_sicily_planes(dry, 1) == 0


def test_a_partly_funded_transfer_flies_the_planes_the_larder_can_pay_for():
    """[38.24] is per PLANE -- "this is done for each plane that a Player wishes to refuel" -- so a
    larder that cannot fund the whole redeployment funds part of it, exactly as air.refuel already
    does for a bombing sortie."""
    st = campaign(seed=7, max_turns=3)
    per = air.fuel_per_plane(Side.AXIS, "strike")
    thin = replace(st, supplies=tuple(
        replace(su, fuel=(5 * per if su.id.endswith("A4130-Soluch-Supply") else 0))
        if su.air_dump and su.side == Side.AXIS else su for su in st.supplies))
    r = _run_transfer(thin, 40)
    assert r.events[-1].payload["planes"] == 5


# --- [60.32] the muster on the map ---------------------------------------------------------------

def test_the_whole_60_32_muster_fits_the_air_facilities_it_is_placed_at():
    """[60.32] "The following planes may be placed at any Italian airfields, landing strips, flying
    boat basins, etc., WITHIN THE CAPACITIES OF THOSE FACILITIES." 394 aeroplanes, [36.12]'s six
    squadrons an airfield and [35.23]'s twelve aeroplanes a Squadriglia -- the placement is ours
    (the book leaves it free), the capacity it fits inside is the chart's."""
    axis = [f for f in charted_air_facilities(sections="ABCDE") if f.side == Side.AXIS]
    per = air.squadron_capacity("IT", 1940, 9)
    placed = roster.deployment(Side.AXIS, axis, per)
    assert per == 12
    assert sum(p.planes for p in placed) == 394 == sum(m.available for m in roster.roster(Side.AXIS))
    room = {f.id: f.level * per for f in axis}
    at = {}
    for p in placed:
        at[p.facility] = at.get(p.facility, 0) + p.planes
    assert all(at[fid] <= room[fid] for fid in at)             # 36.12/36.2/36.3/36.4
    # [34.4] a flying boat "may not be based in, take off from, or land in airfields or air landing
    # strips" -- and [36.3]/[36.4] close the water to everybody else, which is the OTHER direction
    # and is equally printed ("flying boat basins may not be used for normal aircraft"). CORRECTED
    # 2026-07-22: this comment said the nine Cant Z. 501s stand "at the Bomba basin and the Derna
    # alighting area", and they do not -- Bomba is three squadrons of room to Derna's one, and the
    # first in id order takes the whole row. All nine are at B5331-Bomba.
    boats = [p for p in placed if p.type == "Cant Z. 501 Gabbiano"]
    assert sum(p.planes for p in boats) == 9
    assert [(p.facility, p.kind, p.planes) for p in boats] == [("B5331-Bomba", "basin", 9)]
    assert all(p.kind not in roster.WATER_FACILITIES for p in placed
               if p.type != "Cant Z. 501 Gabbiano")


def test_the_placement_is_deterministic_and_fails_loud_when_the_map_is_too_small():
    """It is a transcription, so it must be replay-stable; and a muster that did not fit its own
    chart would be a finding about the transcription, not a rounding to be swallowed."""
    axis = [f for f in charted_air_facilities(sections="ABCDE") if f.side == Side.AXIS]
    assert roster.deployment(Side.AXIS, axis, 12) == roster.deployment(Side.AXIS, axis, 12)
    with pytest.raises(ValueError, match=r"\[60.32\]"):
        roster.deployment(Side.AXIS, axis[:1], 12)


# --- the doctrine: redeploy, raid, come home -----------------------------------------------------

def test_the_raid_doctrine_does_not_roll_a_table_it_has_no_aircraft_for():
    """[44.29] "The raid is cancelled, but HE STILL HAS USED THE TABLE HE ROLLED FOR ONCE." The
    campaign's heavy budget is 25 + 12 + 12 Game-Turns out of 111, and with nobody based in Sicily
    [44.42] grants no planes whatever it rolls. Measured before this guard: 49 Game-Turns of II, III
    and IV spent on 49 raids in which not one aeroplane flew."""
    st = campaign(seed=7, max_turns=111)
    assert malta.italy_sicily_planes(st, 1) == 0
    assert malta_raid_doctrine(st) == "I"                      # free, unlimited, and 44.25's own
    flown = st.with_air_mediterranean(AXIS_STRIKE, 40)         # ...but with a force, he commits
    assert malta_raid_doctrine(flown) in ("II", "III", "IV")


def test_the_basing_doctrine_surges_to_sicily_and_brings_them_home_when_malta_is_down():
    """[42.1]/[44.21] The trade, in both directions: bombers go to Sicily while there is a Capacity
    Level on Malta worth taking, and come home to the desert once the island is knocked down."""
    st = campaign(seed=7, max_turns=6)
    assert malta.capacity(st) == malta.repair_ceiling(st)
    assert air_transfer_doctrine(st, 0, 47) == 47              # whole: go and knock it down
    hurt = replace(st, air_facilities=tuple(
        replace(f, level=0) if malta.is_malta(f) else f for f in st.air_facilities))
    assert air_transfer_doctrine(hurt, 47, 12) == -47          # down: back to the desert


def test_the_campaign_axis_actually_redeploys_and_the_raid_lands():
    """End to end, on the scripted campaign: the Axis flies bombers to Sicily out of Benghazi, the
    [44.42] table sizes a raid off them, the bombs reach a Maltese field, and the aeroplanes come
    home. Before this block the same run produced 111 raids of nothing."""
    st = campaign(seed=4, max_turns=8)
    r = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    moved = [e for e in r.events if e.kind == EventKind.AIR_TRANSFERRED]
    out = [e for e in moved if e.payload["to_mediterranean"]]
    home = [e for e in moved if not e.payload["to_mediterranean"]]
    assert out and home, "the Axis never redeployed, or never came back"
    assert {e.payload["departure"] for e in out} == {"A4728-El Berca"}
    raids = [e for e in r.events if e.kind == EventKind.MALTA_RAID_ORDERED]
    assert any(not e.payload["cancelled"] and e.payload["bomb_points"] > 0 for e in raids)
    assert any(e.kind == EventKind.MALTA_PLANES_LOST for e in r.events)
    # 44.29's budget is spent on raids that fly, not on empty tables
    assert all(e.payload["based"] > 0 for e in raids if e.payload["level"] != "I")


def test_the_transfer_is_deterministic():
    """Rule 4 of this port: same seed, byte-identical log -- including the new beat."""
    st = campaign(seed=4, max_turns=4)
    a = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    b = run(st, axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert any(e.kind == EventKind.AIR_TRANSFERRED for e in a.events)
