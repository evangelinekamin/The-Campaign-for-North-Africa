"""THE TOBRUK SEA LIFELINE, BOTH HALVES (rules 30 / 55.3 / 56.3 / 56.11 / 56.15) -- and the
symmetric take-and-hold that goes with it (rule 64.73).

THE ASYMMETRY. The campaign gave the Tobruk harbour to the Commonwealth alone: an ALLIED
PORT-Tobruk and an ALLIED ferry, correctly cancelled by the 56.15 gate while the Axis held the
city. But THE AXIS HOLDS TOBRUK FROM GAME-TURN 1 -- it was an Italian port and Italy supplied its
army through it -- so the side actually standing in the harbour had no sea supply at all, only a
sixty-hex truck haul from Benghazi. Measured over five seeds, that made the Axis's ENTIRE score one
hex: it banked Tobruk (200 VP) and nothing else, the Commonwealth took Benghazi and the 56.15 gate
then killed the Mediterranean convoy for the rest of the war (95 of 111 Game-Turns cancelled), the
Tobruk staging dump ran dry and the garrison surrendered to 15.15. Tobruk supplied -> Axis 200;
Tobruk cut -> Axis 0 and a shutout. The 64.76 grade was a coin-flip on a single hex: Commonwealth
Smashing in three seeds, Axis Decisive/Marginal in the other two.

THE FIX IS THE RULEBOOK'S OWN. The 56.18 Convoy Air Distance chart names six Axis convoy lanes, and
TWO OF THEM RUN TO TOBRUK (5 Greece->Tobruk, 6 Italy->Tobruk). So the Axis sails lane 6 into the
harbour it holds, through the same ONE 55.3 Tobruk port (1700 t, Efficiency 5) the ferry lands
through, and the 56.15 gate hands the harbour from one side to the other the Game-Turn the city
changes hands. The siege of Tobruk becomes the duel it historically was: the holder is fed by sea,
and the besieger must CUT THE SEA LANE (_campaign_tobruk_axis_interdiction -- the Mediterranean
Fleet and the Desert Air Force, the exact twin of the Luftwaffe's gauntlet over the ferry) and
starve the garrison to a 15.15 surrender.

AND BOTH SIDES NOW PLAY THE POINTS. Only the Commonwealth had the rule-64.73 take-and-hold; the
Axis never garrisoned a city it took and lost BARDIA -- a hundred Victory Points it OPENS HOLDING --
in every seed. A campaign whose grade depends on which side we made competent is not balanced, it is
broken. game.campaign_claim was already side-generic; campaign_policy.take_and_hold_moves /
take_and_hold_supply are the transforms that let both scripted staffs keep the same standing orders.

Byte-identity is the HARD constraint: rommels_arrival and siege_of_tobruk carry neither the campaign
city table nor the campaign convoys, and must not move one byte. Pinned in-suite below.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import campaign_claim, coords                                  # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,                    # noqa: E402
                                  CampaignCommonwealthPolicy,
                                  _CampaignAxisSupplyMixin, _without_staging,
                                  take_and_hold_moves, take_and_hold_supply)
from game.campaign_staff import CampaignStaffPolicy                      # noqa: E402
from game.engine import (HARBOUR_BLOCKED, _air_support, _convoy_dest,   # noqa: E402
                         _Run, determinism_signature, run)
from game.events import Control, EventKind, Side                         # noqa: E402
from game.policy import ScriptedPolicy                                   # noqa: E402
from game.scenario import (_AXIS_TOBRUK_LANE, campaign,                  # noqa: E402
                           rommels_arrival, siege_of_tobruk)
from game.state import AirMission                                        # noqa: E402
from game.supply import port_landing_cap                                 # noqa: E402
from baselines import ROMMELS_ARRIVAL, SIEGE_OF_TOBRUK              # noqa: E402

TOBRUK = coords.to_axial(coords.parse("C4807"))
BARDIA = coords.to_axial(coords.parse("C4321"))
FERRY, AXIS_LANE = "SEA-TOBRUK", _AXIS_TOBRUK_LANE
AL_DUMP, AX_DUMP = "AL-Tobruk", "AX-Stage-Tobruk"


# --- (A) ONE HARBOUR, TWO LANES ------------------------------------------------------------------

def test_tobruk_is_one_harbour_not_two():
    """A port is a PLACE. GameState.port_at is keyed by HEX, engine._naval_convoys throttles
    whatever lands there with no side test at all, and 56.15 gates the sailing on CONTROL -- so the
    55.3 chart's ONE Tobruk (1700 t, Efficiency Level 5) is ONE Port object, serving whoever holds
    the city. A second, duplicate Port on the same hex would only make port_at ambiguous."""
    st = campaign(max_turns=4)
    at_tobruk = [p for p in st.ports if p.hex == TOBRUK]
    assert len(at_tobruk) == 1                            # one harbour, not one per side
    tob = at_tobruk[0]
    assert st.port_at(TOBRUK) is tob                      # ...so port_at is unambiguous
    assert tob.id == "PORT-Tobruk"                        # the id the San Giorgio block keys off
    assert tob.id in HARBOUR_BLOCKED                      # 55.25/55.26: no 55.18 regen, ever
    assert tob.cap_tons == 1700                           # [55.3] the chart, verbatim
    assert (tob.eff, tob.max_eff) == (5, 5)               # [55.3] Efficiency Level 5
    # ...and it is flagged with the side that HOLDS Tobruk on Game-Turn 1 (rule 64.2): the Axis.
    assert tob.side == Side.AXIS
    assert st.control_of(TOBRUK) == Control.AXIS
    # The 1700 t crosses (54.5) to the real gate on EITHER side's lifeline: 425 Ammunition
    # Points per Operations Stage -- which is what the besieger must cut to force a 15.15 surrender.
    assert port_landing_cap(tob, "AMMO") == 425


def test_both_sides_have_a_tobruk_sea_lane():
    """The mirror: the Commonwealth ferry into AL-Tobruk (56.3), and the AXIS lane 6 (Italy ->
    Tobruk, one of the two Tobruk lanes the 56.18 chart names) into the 60.34 staging dump standing
    ON the city -- so an Axis garrison traces to it at distance 0, exactly as the ferry feeds a
    Commonwealth one. Both run every Game-Turn; 56.15 decides which of them actually sails."""
    st = campaign(max_turns=12)
    ferry = [c for c in st.convoys if c.lane == FERRY]
    axis = [c for c in st.convoys if c.lane == AXIS_LANE]
    assert len(ferry) == len(axis) == 12                  # one apiece, every Game-Turn
    assert {c.side for c in ferry} == {Side.ALLIED} and {c.dest for c in ferry} == {AL_DUMP}
    assert {c.side for c in axis} == {Side.AXIS} and {c.dest for c in axis} == {AX_DUMP}
    assert st.supply(AX_DUMP).hex == st.supply(AL_DUMP).hex == TOBRUK   # both dumps ON the city
    assert [c.cargo for c in ferry][0] == [c.cargo for c in axis][0]    # the same Supply-Unit load


def test_5615_hands_the_harbour_over_in_both_directions():
    """THE HANDOFF. Rule 56.15 cancels a convoy whose destination hex the enemy controls -- so while
    the Axis holds Tobruk its lane sails and the ferry is dead, and the moment the Commonwealth takes
    the fortress the two swap. Automatic, in both directions, for as many times as the city changes
    hands. Asked of the engine's own gate (_convoy_dest), so no test-only reimplementation."""
    st = campaign(max_turns=4)
    ferry = next(c for c in st.convoys if c.lane == FERRY)
    axis = next(c for c in st.convoys if c.lane == AXIS_LANE)

    axis_holds = replace(st, control={**st.control, TOBRUK: Control.AXIS})
    assert _convoy_dest(axis_holds, axis) is not None     # the Axis lane lands...
    assert _convoy_dest(axis_holds, ferry) is None        # ...and the ferry never sails

    cw_holds = replace(st, control={**st.control, TOBRUK: Control.ALLIED})
    assert _convoy_dest(cw_holds, axis) is None           # taken: the Axis lane dies...
    assert _convoy_dest(cw_holds, ferry) is not None      # ...and the ferry comes alive


def test_the_commonwealth_can_fight_the_axis_tobruk_lane():
    """THE CUT. Without it the sea lifeline would make the fortress INVULNERABLE: 15.82 grants
    Tobruk no eviction, so it falls only to a 15.15 dry-ammunition surrender, and a garrison fed by
    an uncontested sea lane never goes dry. So the Axis run is under Commonwealth interdiction
    (41.6/41.66) at the SAME 200 Bomb Points as the Luftwaffe's gauntlet over the ferry -- no new
    magnitude on either side of the duel."""
    st = campaign(max_turns=30)
    axis_itd = [o for o in st.interdictions if o.lane == AXIS_LANE]
    ferry_itd = [o for o in st.interdictions if o.lane == FERRY]
    assert axis_itd and ferry_itd
    assert {o.bomb_points for o in axis_itd} == {o.bomb_points for o in ferry_itd} == {200}
    # The Mediterranean Fleet is at Alexandria in September 1940; the Luftwaffe has to ARRIVE (with
    # the DAK, GT20). That is the only difference between the two schedules, and it is a fact about
    # the war, not a thumb on the scale.
    assert min(o.turn for o in axis_itd) == 1
    assert min(o.turn for o in ferry_itd) == 20
    # ...and it fires: the Axis lane runs a real CRT gauntlet in a real game.
    res = run(campaign(seed=1941, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    cut = [e for e in res.events
           if e.kind == EventKind.CONVOY_INTERDICTED and e.payload["lane"] == AXIS_LANE]
    assert cut and all(e.side == Side.ALLIED for e in cut)      # the interdictor is the Commonwealth


def test_the_axis_tobruk_garrison_is_fed_by_sea_until_the_harbour_is_bombed_shut():
    """The point of the whole exercise, in BOTH halves. The Axis holding Tobruk is supplied FROM THE
    SEA -- not by a sixty-hex truck haul out of a Benghazi the Commonwealth can switch off -- and
    that lifeline is CUTTABLE. Both halves, or it is not a siege: it is a freehold.

    The lane lands into the staging dump under the fortress while the harbour works. Then the Desert
    Air Force bombs the harbour (41.39B, engine._air_port), and because PORT-Tobruk is
    HARBOUR_BLOCKED -- the scuttled San Giorgio, which only engineers clear (55.26) -- the
    Efficiency it loses never comes back. The 425-Point/OpStage throat ratchets shut and the lane
    stops sailing for the rest of the war.

    UNTIL THIS SLICE THIS TEST ASSERTED THE LANE LANDED ON ALL TWELVE TURNS, and that was precisely
    the bug. campaign() seeded air=(), so no AirWing existed, so engine._air_port could never fire,
    so no harbour could ever fall below full efficiency and NO SEA LANE COULD EVER BE CUT. Measured:
    the Axis lane landed 425 Ammunition Points a turn into a garrison drawing three and a half -- a
    121x oversupply -- and the Commonwealth interdicted it on 111 turns out of 111 while denying it
    exactly ZERO Ammunition, because the 41.66 CRT skims a percentage off a cargo the 55.14 port cap
    has already clipped back to 425 anyway. Tobruk's 200 Victory Points belonged permanently to
    whoever stood there on Game-Turn 1. Only efficiency 0 cuts a sea lifeline."""
    res = run(campaign(seed=1941, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    landed = [e for e in res.events
              if e.kind == EventKind.SUPPLY_ARRIVED and e.payload["lane"] == AXIS_LANE]

    # (1) THE LIFELINE IS REAL: it sails while the harbour works, into the dump under the fortress.
    assert landed, "the Axis never got a single sea delivery into the Tobruk it holds"
    assert all(e.payload["supply_id"] == AX_DUMP for e in landed)
    assert sum(e.payload["cargo"].get("AMMO", 0) for e in landed) > 0

    # (2) AND IT IS CUTTABLE: the Commonwealth bombs the harbour to nothing, and it STAYS there.
    bombs = [e for e in res.events
             if e.kind == EventKind.PORT_EFFICIENCY_CHANGED
             and e.payload["port_id"] == "PORT-Tobruk" and e.side == Side.ALLIED]
    assert bombs, "the Desert Air Force never touched the harbour"
    assert res.final.port("PORT-Tobruk").eff == 0, "the harbour was never actually shut"
    assert "PORT-Tobruk" in HARBOUR_BLOCKED                      # 55.26: no 55.18 regen, ever

    # (3) SO THE LANE STOPS. Nothing lands once the throat is closed -- that is the whole siege.
    shut = min(e.turn for e in bombs if e.payload["level"] == 0)
    assert not [e for e in landed if e.turn > shut], \
        "the sea lane went on landing supply into a harbour that had been bombed shut"
    assert len(landed) < 12, "the lane was never cut -- the fortress is still invulnerable"


# --- (A2) THE HARBOUR DUEL: WHOEVER BESIEGES, BOMBS ------------------------------------------------

def test_both_air_forces_exist_and_the_besieger_is_the_one_who_bombs():
    """campaign() seeded air=(). One empty tuple, and the consequence ran all the way down: no
    AirWing, so no air beat fires; no air beat, so engine._air_port is unreachable; no _air_port, so
    no port can ever lose Efficiency; and no port can lose Efficiency, so NO HARBOUR CAN EVER BE CUT.
    Tobruk was invulnerable by construction and its 200 Victory Points were a Game-Turn-1 gift.

    Both air forces are seeded now, and the SCHEDULE is symmetric: each side flies a port mission at
    PORT-Tobruk every turn, all war. The ENGINE decides who is besieging -- _air_port reads CONTROL
    of the hex and refuses the side standing in the city ("never bomb your own harbour"). So the
    roles hand off automatically, in both directions, every time the fortress changes hands, exactly
    as the 56.15 convoy lane already hands the sea route over. One Tobruk, one harbour, one Port."""
    st = campaign(seed=1941, max_turns=8)
    assert {w.side for w in st.air} == {Side.AXIS, Side.ALLIED}, "an air force is missing"
    assert all(w.arena == "LAND" and w.strike > 0 for w in st.air), "a wing cannot bomb anything"

    missions = [m for m in st.air_missions if m.kind == "port"]
    assert missions and all(m.target == "PORT-Tobruk" for m in missions)
    assert {m.side for m in missions} == {Side.AXIS, Side.ALLIED}, "the duel is one-sided"

    # the Axis HOLDS Tobruk at Game-Turn 1, so the Commonwealth is the besieger and bombs; the Axis
    # mission is refused against its own harbour. The engine reads control, not the seeded flag.
    res = run(campaign(seed=1941, max_turns=8), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    bombs = [e for e in res.events if e.kind == EventKind.PORT_EFFICIENCY_CHANGED
             and e.payload["port_id"] == "PORT-Tobruk"]
    assert bombs, "nobody bombed the harbour"
    assert {e.side for e in bombs} == {Side.ALLIED}, \
        "the Axis bombed the harbour of the city it is standing in"
    assert res.initial.control_of(TOBRUK) == Control.AXIS


def test_a_side_never_bombs_the_harbour_of_a_city_it_holds():
    """The rule the duel turns on, stated directly at the seam: _air_port refuses the HOLDER. Take
    Tobruk with the Commonwealth and the Commonwealth's own standing mission goes quiet, while the
    Axis's -- which has been a no-op all war -- comes alive. That is what makes it a duel and not a
    one-way ratchet, and it is why the harbour is read from CONTROL and not from the side stamped on
    the Port at setup (there is only ONE Tobruk in the 55.3 chart, and it serves whoever holds it)."""
    st = campaign(seed=1941, max_turns=4)
    both = tuple(AirMission(s, "port", "PORT-Tobruk", 1) for s in (Side.AXIS, Side.ALLIED))

    def bombers(holder: Control) -> set:
        """Who actually gets a bomb through, with `holder` standing in the city."""
        state = replace(st, control={**st.control, TOBRUK: holder}, air_missions=both)
        out = set()
        for side in (Side.AXIS, Side.ALLIED):
            r = _Run(state)
            _air_support(r, side, set())                  # the side flies its due LAND missions
            if any(e.kind == EventKind.PORT_EFFICIENCY_CHANGED
                   and e.payload["port_id"] == "PORT-Tobruk" for e in r.events):
                out.add(side)
        return out

    assert bombers(Control.AXIS) == {Side.ALLIED}, "the holder bombed its own harbour (Axis-held)"
    assert bombers(Control.ALLIED) == {Side.AXIS}, "the holder bombed its own harbour (CW-held)"


# --- (B) BOTH SIDES PLAY THE 64.73 POINTS ---------------------------------------------------------

def test_the_axis_plays_the_points_too():
    """The exact mirror of the Commonwealth's take-and-hold (tests/test_campaign.py). The Axis
    movement is the base attacker's drive on Alexandria with rule 64.73's standing orders laid over
    it: the take-and-hold detaches units to go and get the victory cities it does not bank, and the
    standing garrison order keeps the ones it does."""
    st = campaign(seed=1941)
    base = ScriptedPolicy(attacker=Side.AXIS)
    assert (CampaignAxisPolicy().movement(st, Side.AXIS)
            == take_and_hold_moves(st, Side.AXIS, base.movement(st, Side.AXIS), escort=True))


def test_the_axis_depots_follow_the_take_and_hold():
    """The dual, on the depots (32.33): the Axis supply orders are its ordinary staging-aware
    leapfrog with take_and_hold_supply over the top -- a depot marches with a garrison to a city
    that has none, never leapfrogs off a city it is banking (hold_depots), and never parks on top of
    a staging depot and masks it from the lorries (keep_off_the_spine)."""
    st = campaign(seed=1941)
    pol = CampaignAxisPolicy()
    army = ScriptedPolicy.supply_orders(pol, _without_staging(st), Side.AXIS)
    assert (pol.supply_orders(st, Side.AXIS)
            == take_and_hold_supply(st, Side.AXIS, army, escort=True))


def test_the_axis_goes_and_gets_the_cities_it_never_garrisoned():
    """THE MEASURED DEFECT. The Axis opens the campaign CONTROLLING Benghazi (75 VP -- its own port
    of arrival, where every Mediterranean convoy lands) and Derna (25), and in a hundred and eleven
    Game-Turns it never put a single battalion on either of them. It claims them now, and never
    strips a city it is already banking to do it."""
    st = campaign(seed=1941)
    claimed = {c.name for c in campaign_claim.claims(st, Side.AXIS, escort=True)}
    banked = {name for ax, _a, _c, name in st.victory.cities
              if st.victory._occupier(st, ax) == Side.AXIS}
    assert "Benghazi" in claimed
    assert {"Tobruk", "Bardia"} <= banked          # the two it opens holding, supplied
    assert not (claimed & banked)                  # never strip one city to garrison another


def test_the_axis_ends_the_war_holding_benghazi():
    """...and it is still standing there at the final Game-Turn (measured, all five seeds). This is
    the single biggest consequence of the Axis take-and-hold, and it is NOT the 75 points: a
    garrisoned hex cannot be driven over, so the Commonwealth can no longer flip Benghazi's control
    and the rule-56.15 gate can no longer cancel the Axis Mediterranean convoy. Before, the
    Commonwealth walked over Benghazi and killed that convoy for 95 of 111 Game-Turns; now it lands
    all 111. See the balance note in the commit -- this is the finding, not a side effect."""
    res = run(campaign(seed=1941), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    fin = res.final
    beng = coords.to_axial(coords.parse("A4827"))
    assert fin.victory._occupier(fin, beng) == Side.AXIS
    assert fin.control_of(beng) == Control.AXIS
    cancelled = [e for e in res.events
                 if e.kind == EventKind.CONVOY_CANCELLED and e.payload["lane"] == "2"]
    assert not cancelled, "the Commonwealth still switches off the Axis Mediterranean convoy"


def test_the_live_staff_still_keeps_its_garrisons():
    """A REGRESSION GUARD on the mixin refactor. The standing garrison order used to ride on
    _CampaignAxisSupplyMixin.movement, which the live CampaignStaffPolicy inherits; the scripted
    policies now get the whole take-and-hold instead, so the staff carries its own HOLD half (a
    staff must still decide where the REST of the army goes -- that is the point of having one)."""
    assert "movement" in vars(CampaignStaffPolicy)
    assert "movement" not in vars(_CampaignAxisSupplyMixin)


# --- THE HARD CONSTRAINT -------------------------------------------------------------------------

def _sig(scenario) -> str:
    res = run(scenario(seed=42), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.AXIS))
    return hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]


def test_benchmark_scenarios_byte_identical():
    """Everything above is campaign-only: the Tobruk lanes and ports are seeded in scenario.campaign
    (rommels_arrival keeps its own _rommel_ports / _rommel_convoys), and the take-and-hold needs the
    64.73 city table, which campaign_claim._cities returns () for in every other scenario."""
    assert _sig(rommels_arrival) == ROMMELS_ARRIVAL     # tests/baselines.py -- the ONE place
    assert _sig(siege_of_tobruk) == SIEGE_OF_TOBRUK
