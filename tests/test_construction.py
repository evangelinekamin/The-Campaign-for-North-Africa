"""[24.0] CONSTRUCTION -- the Construction Segment the engine did not have.

Rule 24's opening sentence lists RAILROADS and SUPPLY DUMPS among the things that "come into
existence through construction", and neither could: the map's rail edge-set was frozen where rule
60.7 leaves it (Mersa Matruh), and a supply dump was either seeded in September 1940 or founded free
by a passing lorry. Two slices are built (game.construction), and these tests pin both:

  [24.6] THE RAILWAY, and the asymmetry the rulebook writes in by hand. "The only units that may
    build railroads are the two New Zealand railroad construction companies" (24.61) -- the
    Construction Chart's Build row for Railroad reads NZERC and there is no Axis row at all. One
    company takes two Operations Stages a hex, two stacked take one (24.62); each hex costs one Store
    Point present WITH the engineer and expended in the Segment (24.64); no enemy-held hex may be
    built (24.65); and the line grows westward from the last completed hex with NO HEX SKIPPED
    (24.67).

  [24.9] THE SUPPLY DUMP, and the distinction the engine had collapsed. "Any one TOE Strength Point
    of any type" expends 3 Capability Points and 20 Store Points -- no engineer, no elapsed time --
    and what that BUYS is the rule's own Note: "supplies may be placed in a hex not containing a
    constructed supply dump. The only restriction on the use of such supplies is that trucks 'in
    convoy' may not load such supplies." A pile is a one-way sink; a constructed dump is a LINK a
    bucket brigade can lift out of (53.14/54.16).

Plus the two rules that keep a construction unit honest: 24.12 (a unit involved in construction may
not expend Capability Points that Operations Stage) and 23.11 (an engineer may never voluntarily
enter an Enemy-controlled hex).
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import construction, supply
from game.engine import determinism_signature, run
from game.events import Control, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap, edge
from game.policy import BuildOrder, MoveOrder, Policy, ScriptedPolicy
from game.scenario import campaign, rommels_arrival
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain
from baselines import ROMMELS_ARRIVAL                               # noqa: E402


# --- a tiny surveyed line, so the rules can be pinned without a 111-turn campaign ---------------

LINE = ((0, 3), (0, 2), (0, 1), (0, 0))        # head at (0,3); build WEST, one hex at a time
OFF = (1, 3)                                   # a hex off the line, to walk to


def _unit(uid, side, hx, *, engineer="", cpa=30, combat=True, steps=1) -> Unit:
    return Unit(uid, side, hx, (StepRecord("x", steps),), Mobility.MOTORIZED, cpa, 1, 1, 1,
                engineer=engineer, is_combat=combat)


def _state(units=(), supplies=(), *, weather="normal", control=None) -> GameState:
    terrain = {c: Terrain.CLEAR for c in LINE}
    terrain[OFF] = Terrain.CLEAR
    return GameState(
        turn=1, max_turns=1, phase=Phase.WEATHER, active_side=Side.SYSTEM, seed=1,
        weather=weather, vp=VP(),
        terrain=TerrainMap(terrain=terrain, rails=frozenset({edge(LINE[0], OFF)})),
        control=control or {}, units=tuple(units), target_hex=(0, 0),
        supplies=tuple(supplies),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: sum(getattr(s, c.lower()) for s in supplies) for c in supply.COMMODITIES},
        rail_line=LINE)


class _Build(Policy):
    """A policy that issues exactly the orders it is handed, filtered to its own side, and nothing
    else. One instance serves BOTH sides -- the engine hands it the side it is acting for."""

    def __init__(self, orders=(), moves=()):
        self._orders, self._moves = list(orders), list(moves)

    def _mine(self, state, uid, side):
        u = state.unit(uid)
        return u is not None and u.side == side

    def movement(self, state, side):
        return [o for o in self._moves if self._mine(state, o.unit_id, side)]

    def combat(self, state, side):
        return []

    def construction(self, state, side):
        return [o for o in self._orders
                if o.unit_ids and self._mine(state, o.unit_ids[0], side)]


def _run(units, supplies, orders=(), moves=(), **kw):
    pol = _Build(orders, moves)
    return run(_state(units, supplies, **kw), pol, pol)


def _built(res):
    """The construction the engine actually banked (the 24.11 Initiation Step)."""
    return [e for e in res.events if e.kind == EventKind.CONSTRUCTION_ADVANCED]


def _rejected(res):
    return [e for e in res.events if e.kind == EventKind.ORDER_REJECTED
            and e.payload.get("order") == "construction"]


def _stores_spent_on_construction(res):
    """The Store Points expended in a Construction Segment (24.13/24.64) -- as against a unit's
    ordinary 51.11 ration, which is drawn by the Logistics beat under a different actor."""
    return sum(e.payload["qty"] for e in res.events
               if e.kind == EventKind.SUPPLY_CONSUMED
               and e.payload["commodity"] == supply.STORES
               and e.actor.endswith("/Engineers"))


# --- [24.6] THE RAILWAY -------------------------------------------------------------------------

def test_only_the_two_nz_railroad_construction_companies_may_build_railroad():
    """[24.61] "The only units that may build railroads are the two New Zealand railroad construction
    companies (the 10th and the 13th)." Not infantry, not a tank, not an Axis engineer -- and the
    Construction Chart's Build row for Railroad has no Axis entry at all. THIS IS THE HISTORICAL
    LOGISTICS ASYMMETRY OF THE DESERT WAR, and it is the rulebook's, not ours."""
    dump = SupplyUnit("AL-D", Side.ALLIED, LINE[0], ammo=0, fuel=0, stores=50, constructed=True)
    nzrrc = _unit("NZ", Side.ALLIED, LINE[0], engineer=construction.RAIL)
    infantry = _unit("PBI", Side.ALLIED, LINE[0])
    axis_eng = _unit("AX-E", Side.AXIS, LINE[0], engineer=construction.RAIL)

    assert _built(_run([nzrrc], [dump], [BuildOrder(construction.RAIL, LINE[1], ("NZ",))]))

    for bad in (infantry, axis_eng):
        res = _run([bad], [dump], [BuildOrder(construction.RAIL, LINE[1], (bad.id,))])
        assert not _built(res), f"{bad.id} laid railroad track: only the NZRRC may (24.61)"
        assert _rejected(res)


def test_two_companies_lay_a_hex_in_one_opstage_and_one_company_takes_two():
    """[24.62] "One NZRRC company requires TWO OpStages to build one hex of new track. TWO NZRRC
    companies in the same hex can build one hex of new track in ONE OpStage." Both sentences are one
    number once the work is counted in COMPANY-STAGES: a hex is two of them, and each company on the
    railhead contributes one per Construction Segment. No pair special-case anywhere in the engine."""
    dump = SupplyUnit("AL-D", Side.ALLIED, LINE[0], ammo=0, fuel=0, stores=50, constructed=True)
    pair = [_unit("NZ10", Side.ALLIED, LINE[0], engineer=construction.RAIL),
            _unit("NZ13", Side.ALLIED, LINE[0], engineer=construction.RAIL)]
    solo = [_unit("NZ10", Side.ALLIED, LINE[0], engineer=construction.RAIL)]

    both = _run(pair, [dump], [BuildOrder(construction.RAIL, LINE[1], ("NZ10", "NZ13"))])
    assert _built(both)[0].payload["progress"] == construction.RAIL_COMPANY_STAGES   # ONE segment
    done = [e for e in both.events if e.kind == EventKind.CONSTRUCTION_COMPLETED]
    assert done and tuple(done[0].payload["hex"]) == LINE[1]

    one = _run(solo, [dump], [BuildOrder(construction.RAIL, LINE[1], ("NZ10",))])
    assert _built(one)[0].payload["progress"] == 1, "one company banks one company-stage a segment"
    assert construction.RAIL_COMPANY_STAGES == 2


def test_the_new_hex_joins_the_map_and_the_railhead_moves_west():
    """[24.67] "Construction must start from the last completed hex extending from Mersa Matruh and
    grow WESTWARD towards Tobruk... a Railhead marker is provided to indicate the extent of
    construction. UNBUILT RAILROAD HEXES SIMPLY DO NOT EXIST; they serve no function until actually
    built." So a completed hex joins the map's rail edge-set -- the one dynamic thing on an otherwise
    static TerrainMap -- and the railhead moves onto it."""
    dump = SupplyUnit("AL-D", Side.ALLIED, LINE[0], ammo=0, fuel=0, stores=50, constructed=True)
    pair = [_unit("NZ10", Side.ALLIED, LINE[0], engineer=construction.RAIL),
            _unit("NZ13", Side.ALLIED, LINE[0], engineer=construction.RAIL)]
    st = _state(pair, [dump])
    assert construction.rail_head(st) == LINE[0]
    assert construction.rail_next(st) == LINE[1]

    res = _run(pair, [dump], [BuildOrder(construction.RAIL, LINE[1], ("NZ10", "NZ13"))])
    assert edge(LINE[0], LINE[1]) in res.final.terrain.rails, "the track is not on the map"
    assert construction.rail_head(res.final) == LINE[1], "the railhead did not move onto the new hex"
    assert construction.rail_next(res.final) == LINE[2], "the line did not advance"
    assert not res.final.construction, "the Under Construction marker was not lifted (24.11)"


def test_no_hex_may_be_skipped():
    """[24.67] "NO HEX MAY BE SKIPPED." The line is a line: you may not jump the gang forward and lay
    track at Tobruk while the ground before it is bare."""
    dump = SupplyUnit("AL-D", Side.ALLIED, LINE[0], ammo=0, fuel=0, stores=50, constructed=True)
    pair = [_unit("NZ10", Side.ALLIED, LINE[0], engineer=construction.RAIL),
            _unit("NZ13", Side.ALLIED, LINE[0], engineer=construction.RAIL)]
    res = _run(pair, [dump], [BuildOrder(construction.RAIL, LINE[2], ("NZ10", "NZ13"))])
    assert not _built(res)
    assert any("skipped" in e.payload["reason"] for e in _rejected(res))


def test_a_railroad_hex_costs_one_store_point_present_with_the_engineer():
    """[24.64] "For each Railroad hex to be built or rebuilt there must be present with the Engineer
    unit -- AND ACTUALLY EXPENDED IN THE CONSTRUCTION SEGMENT -- one Store Point." [24.13] adds that
    the supplies "must BEGIN the Construction Segment in the given hex": construction is not fed down
    a supply trace, it is fed out of the pile the gang is standing on."""
    pair = [_unit("NZ10", Side.ALLIED, LINE[0], engineer=construction.RAIL),
            _unit("NZ13", Side.ALLIED, LINE[0], engineer=construction.RAIL)]
    order = [BuildOrder(construction.RAIL, LINE[1], ("NZ10", "NZ13"))]

    dry = SupplyUnit("AL-D", Side.ALLIED, LINE[0], ammo=0, fuel=0, stores=0, constructed=True)
    res = _run(pair, [dry], order)
    assert not _built(res), "track was laid with no Store Point to expend (24.64)"
    assert any("Store Point" in e.payload["reason"] for e in _rejected(res))

    stocked = SupplyUnit("AL-D", Side.ALLIED, LINE[0], ammo=0, fuel=0, stores=50, constructed=True)
    res = _run(pair, [stocked], order)
    assert _stores_spent_on_construction(res) == construction.RAIL_STORES == 1
    check(res.final)                                     # and it conserves


def test_no_track_on_enemy_ground():
    """[24.65] "No Enemy-controlled or Enemy-occupied railroad hex may be built or rebuilt." This is
    what makes the railway FOLLOW the army rather than lead it: the Eighth Army takes the ground, the
    railhead comes up behind it, and the trains then feed the ground it took. Neither half moves
    without the other, which is the desert war."""
    dump = SupplyUnit("AL-D", Side.ALLIED, LINE[0], ammo=0, fuel=0, stores=50, constructed=True)
    pair = [_unit("NZ10", Side.ALLIED, LINE[0], engineer=construction.RAIL),
            _unit("NZ13", Side.ALLIED, LINE[0], engineer=construction.RAIL)]
    order = [BuildOrder(construction.RAIL, LINE[1], ("NZ10", "NZ13"))]

    held = _run(pair, [dump], order, control={LINE[1]: Control.AXIS})
    assert not _built(held), "track was laid on an enemy-controlled hex (24.65)"

    occupied = _run(pair + [_unit("IT", Side.AXIS, LINE[1])], [dump], order)
    assert not _built(occupied), "track was laid on an enemy-OCCUPIED hex (24.65)"


def test_no_construction_in_a_sandstorm_or_a_rainstorm():
    """[24.22] "No construction may occur in a hex affected by a SANDSTORM or a RAINSTORM. This does
    not stop construction entirely; it only prohibits that Operations Stage from counting towards
    construction time costs."

    Asked of the predicate, not of a run: the engine re-rolls the weather every Operations Stage
    (29.0, engine._weather) BEFORE the Construction Segment opens, so a seeded storm never survives
    to the seam. rail_buildable is where the rule lives and where it can be pinned honestly."""
    st = _state([], [], control={})
    for foul in construction.FOUL:
        assert not construction.rail_buildable(replace(st, weather=foul), Side.ALLIED, LINE[1]), \
            f"track was laid in a {foul} (24.22)"
    assert construction.rail_buildable(replace(st, weather="normal"), Side.ALLIED, LINE[1])
    assert construction.rail_buildable(replace(st, weather="hot"), Side.ALLIED, LINE[1]), \
        "24.22 stops a storm, not the heat (24.21's ten Water Points are deferred and flagged)"


# --- [24.12] / [23.11] the two rules that keep a construction unit honest -----------------------

def test_a_unit_involved_in_construction_may_not_move_that_opstage():
    """[24.12] "If units involved in construction expend any Capability Points during the Operations
    Stage construction is HALTED." [48 V.C.4.b] "any units involved in such work may not be moved
    (voluntarily) during the remainder of the current Operations Stage." The Construction Segment runs
    BEFORE the Movement Phase, so the pin is structural: the engine simply refuses the move."""
    dump = SupplyUnit("AL-D", Side.ALLIED, LINE[0], ammo=0, fuel=0, stores=50, constructed=True)
    pair = [_unit("NZ10", Side.ALLIED, LINE[0], engineer=construction.RAIL),
            _unit("NZ13", Side.ALLIED, LINE[0], engineer=construction.RAIL)]
    res = _run(pair, [dump], [BuildOrder(construction.RAIL, LINE[1], ("NZ10", "NZ13"))],
               moves=[MoveOrder("NZ10", OFF)])
    assert any(e.kind == EventKind.ORDER_REJECTED and "24.12" in e.payload.get("reason", "")
               for e in res.events), "a unit booked on construction was allowed to march off"
    assert res.final.unit("NZ10").hex == LINE[0]


def test_an_engineer_never_enters_an_enemy_controlled_hex():
    """[23.11] "Engineer units may NEVER enter Enemy-controlled hexes voluntarily." They are not
    combat units "in any way, shape, or form" -- no combat value, no Zone of Control."""
    nz = _unit("NZ10", Side.ALLIED, LINE[0], engineer=construction.RAIL, combat=False)
    res = _run([nz], [], moves=[MoveOrder("NZ10", OFF)], control={OFF: Control.AXIS})
    assert any(e.kind == EventKind.ORDER_REJECTED and "23.11" in e.payload.get("reason", "")
               for e in res.events)
    assert res.final.unit("NZ10").hex == LINE[0], "the engineer walked into enemy ground"


# --- [24.9] THE SUPPLY DUMP ---------------------------------------------------------------------

def test_constructing_a_dump_costs_three_cp_and_twenty_stores_and_needs_no_engineer():
    """[24.9] "A supply dump may be constructed by having ANY ONE TOE STRENGTH POINT OF ANY TYPE
    expend three Capability Points and 20 Store Points in a hex." No engineer. No elapsed time. It is
    a Capability Point expenditure, not a project."""
    pile = SupplyUnit("AL-Field", Side.ALLIED, LINE[0], ammo=10, fuel=10, stores=50)
    pbi = _unit("PBI", Side.ALLIED, LINE[0])            # no engineer -- any TOE Strength Point
    assert not pile.constructed

    res = _run([pbi], [pile], [BuildOrder(construction.DUMP, LINE[0], ("PBI",))])
    built = [e for e in res.events if e.kind == EventKind.SUPPLY_DUMP_CONSTRUCTED]
    assert built, "no engineer is needed to construct a supply dump (24.9)"
    assert res.final.supply("AL-Field").constructed
    assert _stores_spent_on_construction(res) == construction.DUMP_STORES == 20
    cp = [e for e in res.events if e.kind == EventKind.CP_EXPENDED
          and e.payload["activity"] == "construct_dump"]
    assert cp and cp[0].payload["cp"] == construction.DUMP_CP == 3
    assert len(built) == 1, "an already-constructed dump is not built twice"
    check(res.final)                                     # a transfer + a sink: conservation holds


def test_a_dump_with_too_few_stores_is_not_constructed():
    """[24.9]/[24.13] The twenty Store Points must be ON HAND in the hex and actually expended."""
    pile = SupplyUnit("AL-Field", Side.ALLIED, LINE[0], ammo=10, fuel=10, stores=19)
    res = _run([_unit("PBI", Side.ALLIED, LINE[0])], [pile],
               [BuildOrder(construction.DUMP, LINE[0], ("PBI",))])
    assert not any(e.kind == EventKind.SUPPLY_DUMP_CONSTRUCTED for e in res.events)
    assert not res.final.supply("AL-Field").constructed
    assert _stores_spent_on_construction(res) == 0       # and nothing was spent on it


def test_only_a_constructed_dump_may_be_loaded_by_a_truck_in_convoy():
    """[24.9]'s NOTE, which is the whole point of the rule and the reason the Commonwealth chain could
    never grow past a depot somebody placed in September 1940:

        "Supplies may be placed in a hex NOT containing a constructed supply dump. The only
         restriction on the use of such supplies is that TRUCKS 'IN CONVOY' MAY NOT LOAD SUCH
         SUPPLIES."

    So a lorry may always set a load DOWN in the desert (54.11/54.35 -- engine._establish_dump, free,
    because the rulebook makes it free) and the army may eat off it at once (32.16). What three
    Capability Points and twenty Store Points BUY is the right to give supply BACK to a lorry. A pile
    is a one-way sink; a constructed dump is a LINK a bucket brigade can lift out of (53.14/54.16).

    Pinned at the POLICY seam, because that is where the rule lives: campaign_policy._relay_source is
    what a truck asks "may I load here?", and it now answers yes to a constructed dump and no to a
    pile."""
    from game.campaign_policy import _relay_source
    pile = SupplyUnit("AL-Field", Side.ALLIED, LINE[0], ammo=10, fuel=99, stores=50)
    st = _state([], [pile])
    assert _relay_source(st, Side.ALLIED, LINE[0], None) is None, \
        "a truck in convoy loaded from an UNconstructed pile (24.9's Note)"
    st = st.with_supply(replace(pile, constructed=True))
    assert _relay_source(st, Side.ALLIED, LINE[0], None) is not None, \
        "a truck in convoy could not load from a CONSTRUCTED dump (24.9)"


# --- the guard rails ----------------------------------------------------------------------------

def test_construction_conserves_and_the_campaign_still_runs():
    """game.invariants over a live campaign slice: the Store Points construction expends leave the
    system exactly like 49.3 evaporation (a sink), and nothing is minted."""
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    res = run(campaign(seed=1941, max_turns=10), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    check(res.final)


def test_a_scenario_that_surveys_no_line_can_never_build_and_stays_byte_identical():
    """Every scenario but the campaign surveys no rail_line and fields no engineer, so no
    construction order can ever validate -- no Phase.CONSTRUCTION is emitted and the two byte-locked
    benchmarks are untouched. This is the guard that lets rule 24 exist at all."""
    st = rommels_arrival(seed=42)
    assert st.rail_line == ()
    assert construction.rail_next(st) is None
    assert not [u for u in st.units if u.engineer]
    res = run(st, ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.AXIS))
    assert not any(e.phase == Phase.CONSTRUCTION for e in res.events)
    sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
    assert sig == ROMMELS_ARRIVAL, f"rule 24 moved the benchmark: {sig}"   # tests/baselines.py
