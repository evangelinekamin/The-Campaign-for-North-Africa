"""[32.32] THIRTY MOTORIZATION POINTS -- AND THE LORRY POOL THEY COME OUT OF.

We shipped 32.33 (a supply dump may march with the army if it "begins and remains stacked with a
Friendly combat unit") and never shipped its PRICE, so the desert column was free: a depot moved 15
CP an OpStage -- faster than the infantry it feeds -- and cost the army nothing.

THE RULE, in full:

  * [32.32] "Supply Units may be transported by Motorization Points. THIRTY Motorization Points are
    required to transport one real supply unit... Motorization Points may be attached/detached to
    supply units ONLY DURING THE ORGANIZATION PHASE of an OpStage. A supply unit not assigned the
    minimum necessary number of Motorization Points MAY NOT BE MOVED."
  * [32.51] "Motorization Points are used IN PLACE OF Truck Points... Motorization Points are
    treated in all aspects as MEDIUM Truck Points except as modified in this Major Case."

ONE POOL, NOT TWO. Section 32's General Rule says it applies "if the Players are playing the Land
Game without the Air and Logistics Games" -- in the abstract game you are issued Motorization Points
and NO trucks; in the full Logistics Game (which we run) trucks and NO Motorization Points. 32.51 is
the exchange rate between the two, and it is exact: an MP IS a Medium Truck Point. So thirty
Motorization Points is THIRTY MEDIUM TRUCK POINTS out of the same finite 60.33/60.43 park that is
already hauling the army's fuel and ammunition forward. Every depot pushed forward is thirty Truck
Points not hauling freight. Nothing in the rulebook grants a second, separate pool, so we do not
model one.

A STANDING RESERVATION, NOT A PER-HEX TOLL. 32.32 hinges BOTH attach and detach on the Organization
Phase, and 32.56 speaks of "the unit they are ASSIGNED to" -- so the lorries stay under the depot,
out of the freight rotation, until their owner stands them down in a later Organization Phase.

THE ESCORT PAYS NOTHING EXTRA, and that is correct: 32.58C, the attached points "are not required to
expend CP's if stacked with combat units participating in combat", and 32.33 asks only that the dump
begin and remain stacked with one. The column's whole price is the thirty Truck Points (32.32) and
one Fuel Point (32.24), and both are now charged.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import supply                                              # noqa: E402
from game.engine import determinism_signature, run                   # noqa: E402
from game.events import EventKind                                    # noqa: E402
from game.policy import MotorizeOrder, ScriptedPolicy, SupplyMoveOrder   # noqa: E402
from game.scenario import campaign, rommels_arrival, siege_of_tobruk # noqa: E402
from game.state import Side, TruckFormation                          # noqa: E402
from baselines import ROMMELS_ARRIVAL, SIEGE_OF_TOBRUK              # noqa: E402


class _Column(ScriptedPolicy):
    """A policy that issues exactly the motorization + supply orders it is handed."""

    def __init__(self, side: Side, motor=(), moves=()):
        super().__init__(attacker=side)
        self._motor, self._moves = list(motor), list(moves)

    def movement(self, state, side):
        return []

    def combat(self, state, side):
        return []

    def truck_orders(self, state, side):
        return []

    def motorization(self, state, side):
        return self._motor if side == Side.AXIS else []

    def supply_orders(self, state, side):
        return self._moves if side == Side.AXIS else []


def _lab():
    """A campaign state with 32.32 SWITCHED ON.

    The campaign itself ships with it OFF (game.scenario.campaign), and that is a measured decision,
    not an oversight -- see test_the_campaign_leaves_this_rule_off_and_here_is_why below. The rule
    is complete and these tests hold it to the rulebook; what the campaign cannot yet afford is the
    dump POPULATION it is priced against."""
    return replace(campaign(seed=42), motorized_supply=True)


def _axis_medium(state):
    return next(t for t in state.trucks
                if t.side == Side.AXIS and t.truck_class == supply.MOTORIZATION_CLASS)


# --- the price itself --------------------------------------------------------------------------

def test_a_dump_with_no_lorries_under_it_may_not_be_moved():
    """[32.32] "A supply unit not assigned the minimum necessary number of Motorization Points may
    not be moved." The plainest sentence in Section 32, and the one we never enforced."""
    st = _lab()
    dump = next(s for s in st.supplies
                if s.side == Side.AXIS and not s.base and not s.is_dummy and not s.empty)
    dest = next(iter(supply.reachable_moves(st, dump)))
    res = run(st, _Column(Side.AXIS, moves=[SupplyMoveOrder(dump.id, dest)]),
              ScriptedPolicy(Side.AXIS))
    assert not [e for e in res.events if e.kind == EventKind.SUPPLY_MOVED
                and e.payload["supply_id"] == dump.id]
    why = [e for e in res.events if e.kind == EventKind.ORDER_REJECTED
           and e.payload.get("supply_id") == dump.id]
    assert why and "32.32" in why[0].payload["reason"]


def test_thirty_medium_truck_points_are_required_and_twenty_nine_are_not():
    """[32.32] THIRTY. The magnitude is the rulebook's and it is not negotiable: a park one Truck
    Point short of thirty raises no column at all, and the dump stays where it is."""
    st = _lab()
    med = _axis_medium(st)
    dump = next(s for s in st.supplies
                if s.side == Side.AXIS and not s.base and not s.is_dummy and not s.empty)

    for points, expect in ((supply.MOTORIZATION_POINTS - 1, False),
                           (supply.MOTORIZATION_POINTS, True)):
        park = tuple(replace(t, points=points) if t.id == med.id else t
                     for t in st.trucks if t.side != Side.AXIS or t.id == med.id)
        lab = replace(st, trucks=park)
        legs = supply.column_legs(lab, Side.AXIS, (med.id,))
        assert bool(legs) is expect, f"{points} Medium Truck Points -> column={bool(legs)}"
        if expect:
            assert sum(p for _, p in legs) == supply.MOTORIZATION_POINTS


def test_a_column_is_medium_truck_points_and_only_medium():
    """[32.51] "Motorization Points are treated in all aspects as MEDIUM Truck Points." The rulebook
    offers no Light/Heavy conversion, so none is modelled: a Heavy park cannot raise a column,
    however many Points it holds. FLAGGED in game.supply -- unmodelled because unruled, not because
    it is balanced."""
    st = _lab()
    heavy = [t for t in st.trucks if t.side == Side.AXIS and t.truck_class == "heavy"]
    light = [t for t in st.trucks if t.side == Side.AXIS and t.truck_class == "light"]
    assert heavy and light                                   # the 60.33 park fields both
    fat = replace(st, trucks=tuple(replace(t, points=500) if t.id in
                                   {heavy[0].id, light[0].id} else t for t in st.trucks))
    assert supply.column_legs(fat, Side.AXIS, (heavy[0].id,)) == ()
    assert supply.column_legs(fat, Side.AXIS, (light[0].id,)) == ()


# --- the pool it comes out of ------------------------------------------------------------------

def test_the_lorries_under_a_column_are_lorries_not_hauling_freight():
    """THE WHOLE POINT OF THE RULE. A formation with thirty Points booked under a depot drives the
    freight run as the SMALLER convoy it now is -- its 53.12 load ceiling falls with the lorries it
    no longer has. This is the contested pool: every depot pushed forward is thirty Medium Truck
    Points not carrying the army's fuel."""
    st = _lab()
    med = _axis_medium(st)
    dump = next(s for s in st.supplies
                if s.side == Side.AXIS and not s.base and not s.is_dummy and not s.empty)
    assert supply.free_points(st, med) == med.points         # nothing committed yet

    booked = replace(st, motorization={dump.id: ((med.id, supply.MOTORIZATION_POINTS),)})
    assert supply.committed_points(booked, med.id) == supply.MOTORIZATION_POINTS
    assert supply.free_points(booked, med) == med.points - supply.MOTORIZATION_POINTS

    # 53.12: the convoy may carry what its FREE Points can carry, and not a point more.
    cap = supply.truck_capacity(med.truck_class)["FUEL"]
    free = supply.free_points(booked, med)
    convoy = replace(med, points=free)
    assert supply.truck_load_admissible(convoy, {"FUEL": free * cap})
    assert not supply.truck_load_admissible(convoy, {"FUEL": (free + 1) * cap})


def test_a_column_draws_from_the_slackest_formation_first():
    """A REGRESSION, and it cost the Commonwealth 40% of its freight. Drawn in the order the caller
    named them, the first column took ALL TWENTY Medium Points of the Alexandria row and left it
    with none -- and a formation with nothing free hauls nothing at all, so one thirty-point column
    DELETED A WHOLE LORRY GROUP from the relay. Thirty of the Commonwealth's 130 Medium Points is
    23% of the class, not 40% of its deliveries. A quartermaster details lorries off the group that
    has them to spare."""
    st = _lab()
    small = TruckFormation("AX-Small", Side.AXIS, (0, 0), "medium", points=20)
    big = TruckFormation("AX-Big", Side.AXIS, (0, 0), "medium", points=70)
    lab = replace(st, trucks=(small, big))

    legs = dict(supply.column_legs(lab, Side.AXIS, (small.id, big.id)))
    assert legs == {big.id: 30}, "the slack formation pays, and the small one is left able to haul"
    assert supply.free_points(replace(lab, motorization={"D": tuple(legs.items())}), small) == 20


def test_the_reservation_is_standing_not_a_per_move_toll():
    """[32.32] "Motorization Points may be attached/detached to supply units ONLY during the
    Organization Phase of an OpStage", and [32.56] speaks of "the unit they are ASSIGNED to". The
    lorries stay under the depot across OpStages until their owner stands them down -- they are not
    a fare paid per hex. So an attach, followed by NO detach, is still holding the pool later."""
    st = _lab()
    med = _axis_medium(st)
    dump = next(s for s in st.supplies
                if s.side == Side.AXIS and not s.base and not s.is_dummy and not s.empty)
    res = run(st, _Column(Side.AXIS, motor=[MotorizeOrder(dump.id, (med.id,))]),
              ScriptedPolicy(Side.AXIS))
    assert res.final.motorization.get(dump.id)               # still booked at the end of the run
    assert supply.free_points(res.final, res.final.truck(med.id)) == \
        med.points - supply.MOTORIZATION_POINTS
    # and it was booked exactly ONCE -- a standing reservation is not re-paid every OpStage
    attaches = [e for e in res.events if e.kind == EventKind.MOTORIZATION_ATTACHED
                and e.payload["supply_id"] == dump.id]
    assert len(attaches) == 1


def test_a_column_whose_depot_is_lost_gives_its_lorries_back():
    """No leak. A depot captured (32.13), blown empty (54.14) or otherwise no longer a carriable
    field dump has nothing left to carry, and its lorries would otherwise be hostage to it for the
    rest of the war. They come back in the Organization Phase -- the only beat 32.32 lets them come
    back in.

    FLAGGED (32.56): "if their assigned unit is captured, the Motorization Points are also captured
    and may be used by the Enemy." We release them to their OWNER rather than to the captor. The
    captor's half means minting Truck Points for the enemy on a captured hex -- a truck-OOB change,
    not this slice."""
    st = _lab()
    med = _axis_medium(st)
    dump = next(s for s in st.supplies
                if s.side == Side.AXIS and not s.base and not s.is_dummy and not s.empty)
    # Book the column, then lose the depot out from under it (32.13: the enemy walked onto it). A
    # pure OWNERSHIP flip, so the fixture mints and destroys nothing and conservation still holds.
    booked = replace(st, motorization={dump.id: ((med.id, supply.MOTORIZATION_POINTS),)},
                     supplies=tuple(replace(s, side=Side.ALLIED) if s.id == dump.id else s
                                    for s in st.supplies))
    assert supply.committed_points(booked, med.id) == supply.MOTORIZATION_POINTS
    res = run(booked, _Column(Side.AXIS), ScriptedPolicy(Side.AXIS))
    assert dump.id not in res.final.motorization
    assert supply.free_points(res.final, res.final.truck(med.id)) == med.points
    freed = [e for e in res.events if e.kind == EventKind.MOTORIZATION_DETACHED]
    assert freed and freed[0].payload["reason"] == "lost"


# --- the constraints ----------------------------------------------------------------------------

def test_the_ledger_mints_nothing():
    """Lorries are RESERVED, never created or spent, so the conservation identity (on_hand +
    consumed == initial, per commodity) is untouched by this rule. The engine checks it after every
    applied event, so a clean run IS the proof -- this only states it."""
    st = _lab()
    med = _axis_medium(st)
    dump = next(s for s in st.supplies
                if s.side == Side.AXIS and not s.base and not s.is_dummy and not s.empty)
    res = run(st, _Column(Side.AXIS, motor=[MotorizeOrder(dump.id, (med.id,))]),
              ScriptedPolicy(Side.AXIS))
    for c, initial in res.final.initial_supply.items():
        on_hand = (sum(getattr(s, c.lower()) for s in res.final.supplies)
                   + sum(getattr(t, c.lower()) for t in res.final.trucks))
        assert on_hand + res.final.consumed.get(c, 0) == initial
    # the park is the same size it started -- a reservation is not a loss (32.55/32.56)
    assert {t.id: t.points for t in res.final.trucks} == {t.id: t.points for t in st.trucks}


def test_the_campaign_leaves_this_rule_off_and_here_is_why():
    """THE MEASUREMENT THAT REJECTED IT, recorded so nobody re-imports it hopefully.

    Rule 32.32 is implemented above, in full, at the rulebook's own magnitude. Switched ON in the
    campaign it BREAKS it, in all five canonical seeds:

      * Commonwealth freight delivered collapses 62% (440,293 -> 167,853 supply points, seed 1941),
        while the Axis loses 2.7% and does not change its depot movement at all (55 -> 54 moves).
        It is a Commonwealth-only tax: the Commonwealth is the side whose operational method IS the
        lorried dump (60.34 -- "weeks lorrying dumps forward into the desert first, and THEN
        attacking out of them"), and its charted 60.43 Medium park buys exactly FOUR columns.
      * Eight behaviour tests fail, among them test_the_commonwealth_can_mount_a_supplied_offensive
        and test_acceptance_haul_runs_unfrozen_and_reaches_the_front.
      * And it does not move the lean it was imported to move: Axis 4/5 before, Axis 4/5 after.

    WHY: 32.32 prices a SCARCE COUNTER and this engine has an ABUNDANT PILE POPULATION. In the
    abstract game a Supply Unit is a counter you own a handful of (32.41-32.47; 32.14 caps them at
    five per major city), so thirty Motorization Points apiece is affordable. In the full Logistics
    Game, 54.11 ("any hex can be used as a supply dump") + truck-unload dump creation + 24.9
    construction leave dozens of dumps on the map. Section 32's General Rule is the warning we walked
    past: it applies "if the Players are playing the Land Game WITHOUT the Air and Logistics Games".
    The two systems are alternatives; the price cannot be imported without the population it prices.

    This test does not assert a rule. It asserts that the decision is DELIBERATE, so that flipping
    the flag is a choice somebody makes with the numbers in front of them."""
    assert campaign(seed=42).motorized_supply is False


def test_rommel_and_siege_stay_byte_identical():
    """THE HARD CONSTRAINT. 32.32 is a GENERAL rule, not a campaign one -- but it is gated behind
    GameState.motorized_supply and only game.scenario.campaign turns it on. That is a FLAGGED
    ASYMMETRY pending a re-baseline decision, and the reason is not balance: rommels_arrival and
    siege_of_tobruk seed a truck pool that game.scenario._rommel_trucks itself flags as "a plausible
    DAK placeholder, not a transcribed chart value" -- SIX Medium Truck Points against this rule's
    thirty. Under 32.32 no dump in either benchmark scenario could ever move, and both published
    signatures would shift. Measuring a rulebook magnitude against a placeholder pool measures the
    placeholder. The campaign's parks ARE the transcribed 60.33/60.43 charts."""
    axis = ScriptedPolicy(Side.AXIS)
    for name, build, baseline in (("rommel", rommels_arrival, ROMMELS_ARRIVAL),
                                  ("siege", siege_of_tobruk, SIEGE_OF_TOBRUK)):
        st = build(seed=42)
        assert not st.motorized_supply and not st.motorization
        res = run(st, axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baseline, f"{name} drifted: {sig} != {baseline}"
