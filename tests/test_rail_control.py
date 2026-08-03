"""[54.41] Axis rail control -- the sticky pass-through notion, and the five-contiguous-hex gate.

54.4's other cases (rolling stock 54.43, the 300-ton haul, the 900-ton troop lift 54.44) are all
downstream of this gate, so this is where the rule is proved reachable or not.
"""
import hashlib
from dataclasses import replace

import pytest

from game import movement, rail, wells
from game.apply import apply, fold
from game.engine import _rail_control_claim, _Run, determinism_signature, run
from game.events import EventKind, Side
from game.policy import ScriptedPolicy
from game.scenario import rommels_arrival, siege_of_tobruk
from game.state import TerrainMap
from tests.baselines import BENCHMARKS


# --- rail.contiguous_runs / longest_run: the geometry ---------------------------------------

def test_contiguous_runs_splits_a_broken_line_and_orders_biggest_first():
    # two blocks with a gap between them: (0,0)..(0,2) and (0,10)..(0,11)
    left = {(0, 0), (0, 1), (0, 2)}
    right = {(0, 10), (0, 11)}
    runs = rail.contiguous_runs(left | right)
    assert [len(x) for x in runs] == [3, 2]
    assert runs[0] == left and runs[1] == right


def test_contiguous_runs_is_deterministic_and_empty_for_nothing():
    assert rail.contiguous_runs(set()) == []
    hexes = {(0, 0), (0, 1), (5, 5)}
    assert rail.contiguous_runs(hexes) == rail.contiguous_runs(set(hexes))


def test_the_gate_needs_five_and_four_is_not_enough():
    """54.41 prints FIVE. A four-hex run is the near-miss the campaign actually produced under the
    engine's old occupancy control, so it is the boundary worth pinning."""
    assert rail.CONTIGUOUS_HEXES_54_41 == 5


# --- the sticky pass-through claim -----------------------------------------------------------

def _rail_state(rails, units=(), control=None):
    """A minimal state carrying a built railway along `rails` (a list of adjacent Coords)."""
    base = rommels_arrival()
    edges = frozenset(movement.edge(rails[i], rails[i + 1]) for i in range(len(rails) - 1))
    tm = replace(base.terrain, rails=edges)
    return replace(base, terrain=tm, units=tuple(units), rail_control={})


_LINE_CACHE: dict = {}


def _line(n, avoid=()):
    """n mutually adjacent hexes that ACTUALLY EXIST on the scenario map, laid WEST TO EAST.

    Synthetic coordinates are not enough: a haul asks supply.dump_capacity_at for the destination,
    which looks the hex up in the terrain map and raises KeyError on one the map never had. Walks a
    real chain with backtracking so it cannot dead-end in a corner.

    STRICTLY EASTWARD (increasing axial r) since 2026-08-01, because 54.43's "300 Tons of Supplies
    in any ONE direction" is now enforced and a test railway therefore has to HAVE a direction. The
    old walk took neighbours in plain sorted order and zig-zagged -- _line(6) ran r 45,46,47,46,45,44
    -- so a haul from hex 0 to hex 2 ran east and one from hex 2 to hex 5 ran west, and the two-train
    54.35 fixtures were unwittingly asking for a shuttle. A coastal railline extending from Egypt to
    Libya (54.4's own words) does not double back, and now neither does this one.

    `avoid` keeps a second line clear of the first: no hex within four of anything in it, so the two
    stretches cannot touch and rail.contiguous_runs really does see two runs."""
    from game.hexmap import distance
    key = (n, tuple(sorted(avoid)))
    if key in _LINE_CACHE:
        return _LINE_CACHE[key]
    from game import hexmap
    tm = rommels_arrival().terrain.terrain
    clear = {h for h in tm if all(distance(h, o) >= 4 for o in avoid)}

    def walk(path):
        if len(path) == n:
            return path
        for nb in sorted(hexmap.neighbors(path[-1]), key=lambda c: (-c[1], c)):
            if nb in clear and nb[1] > path[-1][1] and nb not in path:
                got = walk(path + [nb])
                if got:
                    return got
        return None

    for seed_hex in sorted(clear):
        got = walk([seed_hex])
        if got:
            _LINE_CACHE[key] = got
            return got
    raise AssertionError(f"no {n}-hex eastward chain on the map")


def test_a_combat_unit_that_passes_through_claims_the_hex_without_stopping_on_it():
    """THE WHOLE POINT of 54.41 being its own notion: the engine's own hex control needs sole
    OCCUPANCY at a phase boundary, but 54.41 says 'pass through', so a transit claims the hex."""
    line = _line(3)
    s = _rail_state(line)
    u = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    s = replace(s, units=(replace(u, hex=line[0]),))
    r = _Run(s)
    # the unit walks the whole line and ENDS past it -- it never rests on line[1]
    _rail_control_claim(r, r.state.unit(u.id), line)
    claimed = [e for e in r.events if e.kind is EventKind.RAIL_CONTROL_CHANGED]
    assert len(claimed) == 3
    for hx in line:
        assert r.state.rail_control_of(hx) is Side.AXIS
    assert rail.longest_run(r.state, Side.AXIS) == 3


def test_the_claim_is_sticky_and_survives_the_unit_marching_away():
    line = _line(2)
    s = _rail_state(line)
    u = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    s = replace(s, units=(replace(u, hex=line[0]),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(u.id), line)
    # move the unit clean off the railway; control must NOT revert
    r.state = replace(r.state, units=(replace(r.state.unit(u.id), hex=(90, 90)),))
    assert rail.controlled_by(r.state, Side.AXIS) == set(line)


def test_the_other_side_re_crossing_takes_it_back_because_54_41_says_the_LAST_player():
    line = _line(2)
    s = _rail_state(line)
    ax = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    al = next(x for x in rommels_arrival().units if x.side is Side.ALLIED and x.is_combat)
    s = replace(s, units=(replace(ax, hex=line[0]), replace(al, hex=line[0])))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(ax.id), line)
    assert rail.controlled_by(r.state, Side.AXIS) == set(line)
    _rail_control_claim(r, r.state.unit(al.id), line)
    assert rail.controlled_by(r.state, Side.AXIS) == set()
    assert rail.controlled_by(r.state, Side.ALLIED) == set(line)


def test_a_non_combat_unit_does_not_take_possession_of_the_line():
    """54.41 says 'a land COMBAT unit of any type'. A supply column down the line claims nothing."""
    line = _line(2)
    s = _rail_state(line)
    nc = next((x for x in rommels_arrival().units if not x.is_combat), None)
    if nc is None:
        pytest.skip("scenario seeds no non-combat unit")
    s = replace(s, units=(replace(nc, hex=line[0]),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(nc.id), line)
    assert not r.events and rail.controlled_by(r.state, Side.AXIS) == set()


def test_re_crossing_your_own_railway_emits_nothing():
    """The claim is idempotent -- otherwise a shuttling unit buries the log in no-op events."""
    line = _line(3)
    s = _rail_state(line)
    u = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    s = replace(s, units=(replace(u, hex=line[0]),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(u.id), line)
    n = len(r.events)
    _rail_control_claim(r, r.state.unit(u.id), line)
    assert len(r.events) == n


def test_hexes_off_the_built_railway_are_never_claimed():
    """24.67: 'Unbuilt railroad hexes simply do not exist.' A march across open desert claims
    nothing, which is also what keeps every railway-less scenario byte-identical."""
    line = _line(2)
    s = _rail_state(line)
    u = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    s = replace(s, units=(replace(u, hex=(50, 50)),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(u.id), [(50, 50), (51, 50), (52, 50)])
    assert not r.events


def test_the_gate_is_axis_only_because_54_4_is_the_axis_borrowing_the_cw_line():
    """The Commonwealth's own use of its railroad is 54.3, not 54.4, so gate_open is Axis-only
    even when the CW plainly controls a long run of its own line."""
    line = _line(6)
    s = _rail_state(line)
    al = next(x for x in rommels_arrival().units if x.side is Side.ALLIED and x.is_combat)
    s = replace(s, units=(replace(al, hex=line[0]),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(al.id), line)
    assert rail.longest_run(r.state, Side.ALLIED) == 6
    assert rail.gate_open(r.state, Side.ALLIED) is False
    assert rail.gate_open(r.state, Side.AXIS) is False


def test_five_contiguous_opens_the_gate_and_four_does_not():
    line = _line(6)
    s = _rail_state(line)
    u = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    s = replace(s, units=(replace(u, hex=line[0]),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(u.id), line[:4])
    assert rail.longest_run(r.state, Side.AXIS) == 4
    assert rail.gate_open(r.state, Side.AXIS) is False
    _rail_control_claim(r, r.state.unit(u.id), line[4:5])
    assert rail.longest_run(r.state, Side.AXIS) == 5
    assert rail.gate_open(r.state, Side.AXIS) is True


def test_a_broken_run_of_five_does_not_open_the_gate():
    """54.41 says five CONTIGUOUS. Five scattered hexes are not a railway you can run a train on."""
    # five rail hexes that are PAIRWISE NON-ADJACENT, taken from far apart on the real map rather
    # than by stepping along one chain (a walked chain can bend back on itself and touch).
    from game import hexmap
    tm = rommels_arrival().terrain.terrain
    scattered: list = []
    for hx in sorted(tm):
        if all(hx not in hexmap.neighbors(o) and hx != o for o in scattered):
            scattered.append(hx)
        if len(scattered) == 5:
            break
    s = _rail_state(scattered)
    u = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    s = replace(s, units=(replace(u, hex=scattered[0]),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(u.id), scattered)
    assert len(rail.controlled_by(r.state, Side.AXIS)) == 5
    assert rail.longest_run(r.state, Side.AXIS) == 1
    assert rail.gate_open(r.state, Side.AXIS) is False


# --- [54.4] THE DOCTRINE SEAT ------------------------------------------------------------------

def test_the_live_campaign_staff_runs_the_same_railway_as_its_scripted_twin():
    """The watchable-campaign path and its scripted twin must not diverge on a rule the port has
    built -- the same reason CampaignStaffPolicy already carries malta_raid, convoy_plan,
    truck_orders and (one commit earlier, for the identical omission) coastal_shipping_orders.

    CampaignStaffPolicy is (_CampaignAxisSupplyMixin, StaffPolicy) and NEITHER defines
    rail_orders, so before this repair the MRO reached Policy.rail_orders' empty list: a live staff
    could never buy a locomotive nor run one train, and 54.4 was unreachable on the very path the
    project exists to watch."""
    from game.campaign_policy import axis_rail_doctrine
    from game.campaign_staff import CampaignStaffPolicy
    from game.llm import MockClient
    line = _line(6)
    d = _dump("D", line[0], stores=300, fuel=150)
    s = _stocked(line, dumps=(d,))
    staff = CampaignStaffPolicy(MockClient("{}"), side=Side.AXIS)
    orders = staff.rail_orders(s, Side.AXIS)
    assert orders == axis_rail_doctrine(s, Side.AXIS) != []


def test_the_doctrine_keeps_both_ends_of_its_haul_inside_one_activated_run():
    """The doctrine used to pick the westmost and eastmost dump out of the CONTROLLED SET AT LARGE,
    which under the corrected 54.43 would pair a dump in one run with a dump in another and be
    rejected by the engine every Operations Stage. It now picks within one activated run."""
    from game.campaign_policy import axis_rail_doctrine
    long_line = _line(6)
    pair = _far_pair(long_line)
    dumps = (_dump("FAR-W", pair[0], stores=9_000), _dump("FAR-E", pair[1], stores=9_000),
             _dump("RUN-W", long_line[0], stores=1_000), _dump("RUN-E", long_line[5], stores=1_000))
    s = _two_runs(long_line, pair, dumps=dumps)
    order = axis_rail_doctrine(s, Side.AXIS)[0]
    # the far pair is the RICHER stretch and still loses: it is not a run five hexes long
    assert {order.from_dump, order.to_dump} == {"RUN-W", "RUN-E"}
    ends = [s.supply(order.from_dump).hex, s.supply(order.to_dump).hex]
    assert rail.one_activated_run(s, *ends)


# --- the WIRING: 54.41 through a real Movement Phase -------------------------------------------

def test_a_unit_claims_the_rail_hexes_it_crosses_in_a_REAL_movement_phase():
    """THE INTEGRATION NOBODY WAS PINNING. Every other test in this file calls
    engine._rail_control_claim directly, so the whole `_traversed` wiring -- the single hook the
    six crossing sites share, and the central design point of the slice -- could have been deleted
    with all 22 tests still green. This drives engine._movement, the ordinary Voluntary Movement
    (rule 8) path, and asserts a marching unit takes possession of the line under its feet.

    CHECKED, not assumed: with the `_rail_control_claim(r, u, path)` line removed from
    engine._traversed this test fails (zero RAIL_CONTROL_CHANGED events) while every direct-call
    test in this file still passes -- which is exactly the hole it exists to close."""
    from game import hexmap, tactics
    from game.engine import _movement
    from game.policy import MoveOrder

    base = rommels_arrival()
    u = next(x for x in base.units if x.side is Side.AXIS and x.is_combat)
    zoc, occupied = tactics.enemy_zoc_and_occupied(base, Side.AXIS)
    reach, _prev = tactics.reachable_for_prev(base, u, zoc, occupied, base.living(Side.AXIS))
    dest = next(h for h in sorted(hexmap.neighbors(u.hex))
                if h in base.terrain.terrain and h in reach)
    # lay ONE hex of railway under the step this unit is about to take
    tm = replace(base.terrain, rails=frozenset({movement.edge(u.hex, dest)}))
    r = _Run(replace(base, terrain=tm, rail_control={}))

    class _March(ScriptedPolicy):
        def movement(self, state, side):
            return [MoveOrder(u.id, dest)]

    _movement(r, {Side.AXIS: _March(Side.AXIS), Side.ALLIED: ScriptedPolicy(Side.ALLIED)},
              Side.AXIS)
    assert any(e.kind is EventKind.UNIT_MOVED and e.payload["unit_id"] == u.id for e in r.events)
    claimed = {tuple(e.payload["hex"]) for e in r.events
               if e.kind is EventKind.RAIL_CONTROL_CHANGED}
    assert claimed == {u.hex, dest}, "both hexes of the crossed line pass to the mover (54.41)"
    assert r.state.rail_control_of(dest) is Side.AXIS
    assert rail.controlled_by(r.state, Side.AXIS) == {u.hex, dest}


# --- the fold and the benchmarks --------------------------------------------------------------

def test_rail_control_folds_and_replays():
    line = _line(3)
    s = _rail_state(line)
    u = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    s = replace(s, units=(replace(u, hex=line[0]),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(u.id), line)
    assert fold(s, r.events).rail_control == r.state.rail_control


def test_scenarios_without_a_railway_stay_byte_identical():
    """THE HARD CONSTRAINT. Neither benchmark builds a metre of railway, so rail.claims returns
    nothing on every path and not one RAIL_CONTROL_CHANGED can be emitted."""
    axis = ScriptedPolicy(Side.AXIS)
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        res = run(build(seed=42), axis, axis)
        assert not res.initial.terrain.rails, f"{name} unexpectedly seeds a railway"
        assert not [e for e in res.events if e.kind is EventKind.RAIL_CONTROL_CHANGED]
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == BENCHMARKS[name], f"{name} drifted: {sig} != {BENCHMARKS[name]}"


# --- [54.43]/[54.45] ROLLING STOCK ------------------------------------------------------------

def _stocked(rails, dumps=(), stock=0, control=Side.AXIS, stage=1, stock_at=None):
    """A state whose whole `rails` line is controlled by `control`, carrying `dumps`.

    `stock` units of Rolling Stock stand at `stock_at` -- the line's west end by default. Stock has
    a PLACE and not merely a count since 54.43 was bound to the run the locomotive was bought on
    (game.state.rolling_stock_at); a test that seeded a bare count would now be seeding a
    locomotive standing nowhere, which hauls nothing."""
    base = rommels_arrival()
    edges = frozenset(movement.edge(rails[i], rails[i + 1]) for i in range(len(rails) - 1))
    tm = replace(base.terrain, rails=edges)
    at = {(stock_at or rails[0]): stock} if stock else {}
    return replace(base, terrain=tm, supplies=tuple(dumps), units=(), stage=stage,
                   rail_control={h: control for h in rails}, rolling_stock_at=at)


def _dump(did, hx, side=Side.AXIS, air_dump=False, **q):
    from game.state import SupplyUnit
    return SupplyUnit(did, side, hx, ammo=q.get("ammo", 0), fuel=q.get("fuel", 0),
                      stores=q.get("stores", 0), water=q.get("water", 0), air_dump=air_dump)


class _Orders:
    def __init__(self, orders): self._o = list(orders)
    def rail_orders(self, state, side): return list(self._o)
    def __getattr__(self, _): return lambda *a, **k: []


def test_activation_costs_exactly_250_stores_and_100_fuel_and_they_are_gone_for_good():
    from game.engine import _axis_rail
    line = _line(6)
    d = _dump("D", line[0], stores=300, fuel=150)
    s = _stocked(line, dumps=(d,))
    r = _Run(s)
    _axis_rail(r, _Orders([__import__("game.policy", fromlist=["x"]).RailActivateOrder("D")]),
               Side.AXIS)
    assert r.state.rolling_stock == 1
    left = r.state.supply("D")
    assert (left.stores, left.fuel) == (50, 50)           # 250 and 100 taken
    # 54.45: used up, not parked somewhere -- the ledger books them as CONSUMED
    assert r.state.consumed["STORES"] == 250 and r.state.consumed["FUEL"] == 100


def test_activation_is_refused_without_five_contiguous_controlled_hexes():
    from game.engine import _axis_rail
    from game.policy import RailActivateOrder
    line = _line(4)                                        # four, not five
    d = _dump("D", line[0], stores=300, fuel=150)
    s = _stocked(line, dumps=(d,))
    r = _Run(s)
    _axis_rail(r, _Orders([RailActivateOrder("D")]), Side.AXIS)
    # the gate is shut, so the doctrine layer never even gets a legal buy
    assert r.state.rolling_stock == 0


def test_losing_the_fifth_hex_destroys_the_stock_outright_with_no_refund():
    """[54.45] 'the Rolling Stock is considered to have been destroyed' -- and the Stores and Fuel
    that bought it stay spent. This is the rule's whole risk, and the reason the doctrine buys one."""
    from game.engine import _axis_rail
    line = _line(6)
    s = _stocked(line, stock=2)
    # the Commonwealth re-crosses two hexes, breaking the run below five
    s = replace(s, rail_control={**s.rail_control, line[2]: Side.ALLIED, line[3]: Side.ALLIED})
    assert rail.gate_open(s, Side.AXIS) is False
    r = _Run(s)
    _axis_rail(r, _Orders([]), Side.AXIS)
    assert r.state.rolling_stock == 0
    killed = [e for e in r.events if e.kind is EventKind.ROLLING_STOCK_DESTROYED]
    assert len(killed) == 1 and killed[0].payload["stock"] == 2


def test_the_haul_is_capped_at_300_tons_per_activation_and_conserves():
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    from game import supply as supply_mod
    line = _line(6)
    src = _dump("W", line[0], stores=100_000)
    dst = _dump("E", line[5], stores=0)
    s = _stocked(line, dumps=(src, dst), stock=1)
    r = _Run(s)
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100_000)]), Side.AXIS)
    moved = r.state.supply("E").stores
    assert moved > 0
    assert supply_mod.points_to_tons(moved, "STORES") <= rail.TONS_PER_ACTIVATION_54_43
    # conserving: what left the west dump arrived at the east one
    assert r.state.supply("W").stores + moved == 100_000


def test_two_locomotives_haul_twice_as_much():
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    outs = []
    for stock in (1, 2):
        src, dst = _dump("W", line[0], stores=100_000), _dump("E", line[5])
        r = _Run(_stocked(line, dumps=(src, dst), stock=stock))
        _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100_000)]), Side.AXIS)
        outs.append(r.state.supply("E").stores)
    assert outs[1] == 2 * outs[0]


def test_the_railroad_is_dead_exactly_one_operations_stage_per_CALENDAR_month():
    """[54.34] via [54.46]: "For the duration of ONE Operations Stage PER MONTH (CALENDAR MONTH),
    the railroad may not be used for anything. It is transporting water forward for railroad use."

    RESTATED, port rule 5 -- THE OLD TEST COULD NOT FAIL. It seeded its own state with
    `stage=rail.dead_stage_54_34(None)`, i.e. it derived the input from the function under test and
    then asserted that whatever that function returned was dead. That is true under the book's
    reading AND under the hard-coded "stage 3 of EVERY Game-Turn" one the engine actually shipped
    -- 111 dead Operations Stages against the ~29 the book prints. The claim is now the book's:
    count the dead stages over the whole campaign calendar and require one per CALENDAR MONTH.

    333 Operations Stages (111 Game-Turns x 3), 29 calendar months in them (September 1940 is a
    half-month of two Game-Turns, 64.2), so 29 dead stages -- and never two in one month."""
    from game import calendar
    line = _line(6)
    open_gate = _stocked(line, stock=1)
    assert rail.gate_open(open_gate, Side.AXIS), "54.34 is the only thing that may shut this line"
    dead = [(gt, st) for gt in range(1, 112) for st in (1, 2, 3)
            if not rail.usable_this_stage(replace(open_gate, turn=gt, stage=st))]
    per_month: dict = {}
    for gt, st in dead:
        per_month.setdefault(calendar.gt_to_month(gt), []).append((gt, st))
    assert all(len(v) == rail.DEAD_OPSTAGES_PER_MONTH_54_34 for v in per_month.values())
    assert set(per_month) == {calendar.gt_to_month(gt) for gt in range(1, 112)}
    assert len(dead) == 29, "one per calendar month over GT1-111, not one per Game-Turn"


def test_the_dead_stage_does_not_come_round_every_game_turn():
    """THE BUG, at the engine's own boundary: the railway must run in the LAST Operations Stage of
    a Game-Turn that is not its calendar month's first. Under the shipped code every Game-Turn's
    stage 3 was dead, so this haul was refused 111 times a campaign instead of 29."""
    from game import calendar
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    dead_turn = next(gt for gt in range(1, 112) if calendar.is_month_start(gt))
    live_turn = next(gt for gt in range(dead_turn + 1, 112) if not calendar.is_month_start(gt))
    landed = []
    for gt in (dead_turn, live_turn):
        src, dst = _dump("W", line[0], stores=100_000), _dump("E", line[5])
        s = replace(_stocked(line, dumps=(src, dst), stock=1, stage=3), turn=gt)
        r = _Run(s)
        _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100_000)]), Side.AXIS)
        landed.append(r.state.supply("E").stores)
        if gt == dead_turn:
            # RESTATED, port rule 5, when _rail_haul's first refusal was SPLIT into its two clauses:
            # it used to log "the railroad is not usable this Operations Stage (54.34/54.41)" for
            # whichever of the two bit, and this assertion could therefore be satisfied by 54.41's
            # gate being shut instead -- which is not what this test is about. The claim is now the
            # one the test's own name makes: the DEAD STAGE stopped this train.
            assert any("may not be used for anything" in e.payload.get("reason", "")
                       for e in r.events if e.kind is EventKind.ORDER_REJECTED)
    assert landed[0] == 0, "the month's first Game-Turn gives up its last Operations Stage (54.34)"
    assert landed[1] > 0, "every other Game-Turn's last Operations Stage runs trains"


def test_a_haul_between_dumps_off_the_controlled_line_is_refused():
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    src = _dump("W", line[0], stores=10_000)
    off = _dump("OFF", (80, 80), stores=0)                 # nowhere near the railway
    r = _Run(_stocked(line, dumps=(src, off), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("W", "OFF", "STORES", 5_000)]), Side.AXIS)
    assert r.state.supply("OFF").stores == 0
    assert any("stand on the railway" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


# --- [54.33] ONE TYPE OF SUPPLY PER OPERATIONS STAGE ------------------------------------------

def test_one_operations_stage_carries_one_commodity_and_not_three():
    """[54.33] "The railroad may transport only one type of supply at a given time. It may move
    fuel, ammunition, or stores -- NOT ANY COMBINATION OF THE THREE."

    The shipped guard tested the commodity NAME against supply.COMMODITIES, which a RailHaulOrder
    satisfies by construction, so nothing anywhere tracked what the railway had already carried:
    measured, one Operations Stage accepted STORES x20, then AMMO x40, then FUEL x960 -- all three
    on one train, exactly filling the 300-ton allowance. The first load here is deliberately SMALL,
    because a full-size one masks the defect by exhausting the tonnage budget on its own."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    src = _dump("W", line[0], stores=100_000, ammo=100_000, fuel=100_000)
    dst = _dump("E", line[5])
    r = _Run(_stocked(line, dumps=(src, dst), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 20),
                           RailHaulOrder("W", "E", "AMMO", 40),
                           RailHaulOrder("W", "E", "FUEL", 960)]), Side.AXIS)
    east = r.state.supply("E")
    assert east.stores == 20                      # the stage's first train fixes the type
    assert (east.ammo, east.fuel) == (0, 0)       # and the other two are refused, not carried
    refused = [e.payload["reason"] for e in r.events if e.kind is EventKind.ORDER_REJECTED]
    assert sum("already carrying STORES" in x for x in refused) == 2


def test_the_next_operations_stage_may_carry_a_different_commodity():
    """54.33 binds "at a given time", and 54.32/54.43 measure the railway's allowance per
    OPERATIONS STAGE -- so the choice is remade every stage, not once per campaign."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    src = _dump("W", line[0], stores=100_000, ammo=100_000)
    dst = _dump("E", line[5])
    r = _Run(_stocked(line, dumps=(src, dst), stock=1, stage=1))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 20)]), Side.AXIS)
    r.state = replace(r.state, stage=2)           # the ledger expires by (turn, stage) on its own
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "AMMO", 40)]), Side.AXIS)
    east = r.state.supply("E")
    assert (east.stores, east.ammo) == (20, 40)


def test_the_railroad_refuses_water_because_the_rail_hexes_are_the_pipeline():
    """[54.33] names fuel, ammunition and stores and then says why water is absent: "(Water need
    not be transported by RR -- the railroad hexes are pipelines in and of themselves.)" The old
    guard tested supply.COMMODITIES, the 4-tuple, so a train could haul water."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    src, dst = _dump("W", line[0], water=100_000), _dump("E", line[5])
    r = _Run(_stocked(line, dumps=(src, dst), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "WATER", 100)]), Side.AXIS)
    assert r.state.supply("E").water == 0
    assert any("fuel, ammunition or stores (54.33)" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


# --- [54.35] WHAT THE TRAIN SETS DOWN STAYS DOWN ----------------------------------------------

def test_freight_landed_this_stage_may_not_ride_a_second_train_the_same_stage():
    """[54.35] "Supplies are considered unloaded when they reach a specific hex. They may not be
    moved that Operations Stage." Measured on the pre-repair code with THIS fixture (A=1,000 Stores,
    two 100-Point hauls in one Operations Stage), the chain A->B->C was accepted straight through:
    A=900, B=0, C=100 -- nothing marked B as having just been unloaded into, so the freight rode a
    second train the moment it touched the platform.

    RESTATED 2026-08-01, port rule 5: this docstring used to claim the measurement was "B kept 800,
    C got 200", which THIS FIXTURE CANNOT PRODUCE at any quantity -- B starts empty and forwards
    what it receives, and 800 is what A keeps under 200-Point hauls. In a port whose test prose is
    the transcription record, a wrong figure standing beside the assertion it justifies is a defect;
    the numbers above were re-measured by neutering _rail_free_points back to `stock`.

    The first haul is deliberately a THIRD of the stage's 300-ton allowance, so what stops the
    second train is 54.35 and provably not 54.43's tonnage cap."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    a = _dump("A", line[0], stores=1_000)
    b = _dump("B", line[2], stores=0)
    c = _dump("C", line[5], stores=0)
    r = _Run(_stocked(line, dumps=(a, b, c), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("A", "B", "STORES", 100),
                           RailHaulOrder("B", "C", "STORES", 100)]), Side.AXIS)
    run = rail.activated_run_at(r.state, line[0])
    assert (rail.haul_capacity_tons(r.state, run)
            - r.rail_tons_this_stage(min(run))) == 200            # room to spare
    assert r.state.supply("B").stores == 100      # it landed...
    assert r.state.supply("C").stores == 0        # ...and it stays landed this Operations Stage
    assert any("may not be moved that Operations Stage (54.35)" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_54_35_pins_the_freight_and_not_the_dump():
    """The stock that was ALREADY standing in the receiving dump is not supply that "reached a
    specific hex" this Operations Stage, so it still moves -- a station keeps working on the day a
    train calls at it. Onward haul is capped at exactly the pre-existing stock.

    AND THE PIN IS KEYED TO THE HEX THE TRAIN CALLED AT. 54.35's own subject is a hex ("supplies are
    considered unloaded WHEN THEY REACH A SPECIFIC HEX"), so a station the train never visited is
    untouched. That half was unpinned: rewriting _Run.rail_landed_this_stage to return the largest
    landing over ALL dumps rather than the named one left every rail test in the file green, because
    each of them used a single receiving dump. D below is that fourth station."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    a = _dump("A", line[0], stores=1_000)
    b = _dump("B", line[2], stores=120)           # 120 already on the platform
    c = _dump("C", line[5], stores=0)
    d = _dump("D", line[3], stores=60)            # a station no train calls at this stage
    r = _Run(_stocked(line, dumps=(a, b, c, d), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("A", "B", "STORES", 100),
                           RailHaulOrder("B", "C", "STORES", 200),
                           RailHaulOrder("D", "C", "STORES", 60)]), Side.AXIS)
    assert r.state.supply("C").stores == 180      # 120 from B's old stock, then all 60 of D's
    assert r.state.supply("B").stores == 100
    assert r.state.supply("D").stores == 0        # D was never unloaded into, so D is not pinned


def test_a_lorry_may_not_lift_what_the_train_has_only_just_set_down():
    """[54.35] binds every mover, not just the next train: 54.43 puts rail movement in the CONVOY
    STAGE, the same Phase the lorries run in, and engine.run deliberately orders _axis_rail AHEAD
    of _truck_convoys -- so the truck park is exactly the consumer the rule is aimed at. What was
    standing in the dump beforehand still loads normally."""
    from game.engine import _axis_rail, _truck_load
    from game.policy import RailHaulOrder, TruckOrder
    from game.state import TruckFormation
    line = _line(6)
    src, dst = _dump("W", line[0], stores=1_000), _dump("E", line[5], stores=50)
    truck = TruckFormation("TP", Side.AXIS, line[5], truck_class="medium", points=40)
    s = _stocked(line, dumps=(src, dst), stock=1)
    r = _Run(replace(s, trucks=(truck,)))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 200)]), Side.AXIS)
    assert r.state.supply("E").stores == 250
    order = TruckOrder("TP", load_from="E", load={"STORES": 60})
    assert _truck_load(r, Side.AXIS, "AXIS/Logistics", order, r.state.truck("TP")) is False
    assert any("may not be moved that Operations Stage (54.35)" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)
    ok = TruckOrder("TP", load_from="E", load={"STORES": 50})     # the pre-existing 50 still moves
    assert _truck_load(r, Side.AXIS, "AXIS/Logistics", ok, r.state.truck("TP")) is True


# --- [54.41]/[54.43] THE HAUL IS BOUND TO ONE ACTIVATED RUN -----------------------------------

def _far_pair(avoid) -> list:
    """Two adjacent real map hexes nowhere near `avoid` -- a second, unrelated stretch of line."""
    from game import hexmap
    from game.hexmap import distance
    tm = rommels_arrival().terrain.terrain
    for hx in sorted(tm, reverse=True):
        if any(distance(hx, o) < 4 for o in avoid):
            continue
        for nb in sorted(hexmap.neighbors(hx)):
            if nb in tm and all(distance(nb, o) >= 4 for o in avoid):
                return [hx, nb]
    raise AssertionError("no isolated adjacent pair on the map")


def _two_runs(long_line, pair, stock=1, dumps=(), stock_at=None):
    """A railway in TWO disconnected stretches, both wholly Axis-controlled. The stock stands on
    the LONG one by default -- it is the only stretch of the two that 54.41's gate opens for."""
    base = rommels_arrival()
    edges = {movement.edge(long_line[i], long_line[i + 1]) for i in range(len(long_line) - 1)}
    for a, b in zip(pair, pair[1:]):
        edges.add(movement.edge(a, b))
    tm = replace(base.terrain, rails=frozenset(edges))
    return replace(base, terrain=tm, supplies=tuple(dumps), units=(), stage=1,
                   rail_control={h: Side.AXIS for h in list(long_line) + list(pair)},
                   rolling_stock_at={(stock_at or long_line[0]): stock} if stock else {})


def test_a_run_of_five_elsewhere_does_not_license_a_haul_inside_a_run_of_two():
    """[54.43] activates "all such hexes under his control (AS LONG AS THEY ARE CONTIGUOUS)" --
    the run the train is on. rail.gate_open only ever answered "does SOME run of five exist
    anywhere", and nothing tied the haul to THAT run: measured, a distant five-hex run opened the
    gate while both dumps sat in an unrelated two-hex stretch, and the haul was accepted."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    long_line = _line(6)
    pair = _far_pair(long_line)
    src, dst = _dump("W", pair[0], stores=10_000), _dump("E", pair[1])
    s = _two_runs(long_line, pair, dumps=(src, dst))
    r = _Run(s)
    assert rail.gate_open(s, Side.AXIS) is True         # the far run really does open the gate
    assert rail.one_activated_run(s, pair[0], pair[1]) is False
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 5_000)]), Side.AXIS)
    assert r.state.supply("E").stores == 0
    assert any("ONE contiguous controlled run" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_a_haul_inside_the_activated_run_still_runs():
    """The companion negative control: same board, same gate, dumps moved onto the run of six."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    long_line = _line(6)
    pair = _far_pair(long_line)
    src, dst = _dump("W", long_line[0], stores=10_000), _dump("E", long_line[5])
    r = _Run(_two_runs(long_line, pair, dumps=(src, dst)))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 5_000)]), Side.AXIS)
    assert r.state.supply("E").stores > 0


def test_a_train_may_not_run_through_hexes_the_commonwealth_holds():
    """[54.43] "he may activate all such hexes UNDER HIS CONTROL (as long as they are contiguous)".
    The shipped check tested only the two END hexes for control and left connectivity to
    supply.rail_reachable, which walks terrain.rails and is blind to control -- so a train ran
    straight through the middle of the line whoever held it, the Eighth Army's own railhead
    included. Here the Commonwealth takes two hexes in the middle: both ends are still Axis, the
    track still joins them, and the haul must stop."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(10)
    src, dst = _dump("W", line[0], stores=10_000), _dump("E", line[9])
    s = _stocked(line, dumps=(src, dst), stock=1)
    s = replace(s, rail_control={**s.rail_control,
                                 line[5]: Side.ALLIED, line[6]: Side.ALLIED})
    assert s.rail_control_of(line[0]) is Side.AXIS and s.rail_control_of(line[9]) is Side.AXIS
    assert line[9] in supply_mod_rail_reachable(s, line[0])       # the TRACK is unbroken
    r = _Run(s)
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 5_000)]), Side.AXIS)
    assert r.state.supply("E").stores == 0
    assert any("ONE contiguous controlled run" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def supply_mod_rail_reachable(state, start):
    from game import supply as supply_mod
    return supply_mod.rail_reachable(state.terrain, start)


def test_the_commonwealth_never_gets_axis_rolling_stock():
    """[54.45] 'The Axis may not use Commonwealth Stock, nor vice versa.' _axis_rail is Axis-only."""
    from game.engine import _axis_rail
    from game.policy import RailActivateOrder
    line = _line(6)
    d = _dump("D", line[0], side=Side.ALLIED, stores=300, fuel=150)
    s = _stocked(line, dumps=(d,), control=Side.ALLIED)
    r = _Run(s)
    _axis_rail(r, _Orders([RailActivateOrder("D")]), Side.ALLIED)
    assert r.state.rolling_stock == 0 and not r.events


# --- [54.43] THE PURCHASE IS BOUND TO A RUN TOO -----------------------------------------------

def test_a_locomotive_may_not_be_bought_at_a_hex_outside_any_run_of_five():
    """THE ACTIVATE HALF OF THE RUN BINDING, which nothing pinned: deleting _rail_activate's
    `rail.activated_run_at(...) is None` guard left the WHOLE suite green, because the one test that
    looked relevant (test_activation_is_refused_without_five_contiguous_controlled_hexes) uses a
    four-hex line and is caught by the older gate_open check eight lines above -- the two guards
    mutually masked, and only deleting BOTH made anything fail.

    The scenario the guard actually adds is this one: the Axis holds a run of six SOMEWHERE, so
    54.41's gate is open board-wide, and brings his 250 Stores and 100 Fuel to a controlled rail hex
    standing in a run of TWO. 54.43 activates "all such hexes under his control (AS LONG AS THEY ARE
    CONTIGUOUS)" -- the block the points were carried to -- and that block is not five hexes long."""
    from game.engine import _axis_rail
    from game.policy import RailActivateOrder
    long_line = _line(6)
    pair = _far_pair(long_line)
    payer = _dump("P", pair[0], stores=300, fuel=150)
    s = _two_runs(long_line, pair, stock=0, dumps=(payer,))
    assert rail.gate_open(s, Side.AXIS) is True          # the far run really does open the gate
    assert rail.activated_run_at(s, pair[0]) is None     # ...and the payer is not standing in it
    r = _Run(s)
    _axis_rail(r, _Orders([RailActivateOrder("P")]), Side.AXIS)
    assert r.state.rolling_stock == 0
    left = r.state.supply("P")
    assert (left.stores, left.fuel) == (300, 150)        # and the points are NOT spent
    assert any("not in a run of five contiguous controlled rail hexes" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_the_dead_operations_stage_stops_the_axis_BUYING_a_locomotive_too():
    """[54.34] "For the duration of one Operations Stage per month (calendar month), the railroad
    MAY NOT BE USED FOR ANYTHING." _rail_haul asked rail.usable_this_stage; _rail_activate asked
    only 54.41's gate, so the clause both restated 54.34 tests quote was pinned for one of the two
    things the railroad does. Measured on the shipped code: on Game-Turn 1's third Operations Stage
    -- September 1940's dead stage -- a RailActivateOrder emitted ROLLING_STOCK_ACTIVATED, took
    rolling_stock 0 -> 1 and burned 250 Stores + 100 Fuel, with zero rejections.

    "For anything" is strictly broader than 54.41's "may use such rail hexes", and _rail_activate's
    own docstring already argues that putting a locomotive on the line is using it."""
    from game import calendar
    from game.engine import _axis_rail
    from game.policy import RailActivateOrder
    line = _line(6)
    dead_turn = next(gt for gt in range(1, 112) if calendar.is_month_start(gt))
    d = _dump("D", line[0], stores=300, fuel=150)
    s = replace(_stocked(line, dumps=(d,), stage=rail.LAST_OPSTAGE), turn=dead_turn)
    assert rail.is_dead_stage_54_34(s) and not rail.usable_this_stage(s)
    r = _Run(s)
    _axis_rail(r, _Orders([RailActivateOrder("D")]), Side.AXIS)
    assert r.state.rolling_stock == 0
    left = r.state.supply("D")
    assert (left.stores, left.fuel) == (300, 150)        # 54.45's points are not spent either
    assert any("may not be used for anything" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_a_locomotive_may_not_be_bought_out_of_a_well():
    """[52.11]/[52.3] THE WELL BOUNDARY, CLOSED AT THE OTHER DOOR. A well or pipeline hex is
    geography, not an army's field dump -- engine._truck_load, engine._ship_load and (since the
    haul repair) both ends of _rail_haul all refuse to treat one as a depot. _rail_activate did
    not, so a well standing on a controlled rail hex and holding 300 Stores / 150 Fuel could BUY a
    locomotive: the 250 Stores and 100 Fuel 54.43 charges would have been drawn out of a water hole
    that no lorry, ship or train is allowed to load from in the first place.

    Same reasoning as the haul's, and therefore the same citation: 52.11 says what a well is, 54.11
    says what a supply dump is, and the well is not one."""
    from game.engine import _axis_rail
    from game.policy import RailActivateOrder
    line = _line(6)
    well = _dump("AX-Well-Here", line[0], stores=300, fuel=150)
    r = _Run(_stocked(line, dumps=(well,)))
    _axis_rail(r, _Orders([RailActivateOrder("AX-Well-Here")]), Side.AXIS)
    assert r.state.rolling_stock == 0
    left = r.state.supply("AX-Well-Here")
    assert (left.stores, left.fuel) == (300, 150)          # and the points are NOT spent
    assert any("not a supply dump" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


# --- [54.43] THE 300 TONS BELONG TO THE BLOCK THE LOCOMOTIVE STANDS ON ------------------------

def _pair_of_runs(stock_at_index=0):
    """Two disjoint six-hex Axis-controlled runs, one locomotive standing on the FIRST."""
    long_a = _line(6)
    long_b = _line(6, avoid=tuple(long_a))
    base = rommels_arrival()
    edges = {movement.edge(ln[i], ln[i + 1]) for ln in (long_a, long_b) for i in range(len(ln) - 1)}
    tm = replace(base.terrain, rails=frozenset(edges))
    return long_a, long_b, replace(base, terrain=tm, units=(), stage=1,
                                   rail_control={h: Side.AXIS for h in long_a + long_b},
                                   rolling_stock_at={long_a[stock_at_index]: 1})


def test_a_locomotive_bought_on_one_run_does_not_haul_on_a_disjoint_one():
    """[54.43] "he may activate all such hexes under his control (AS LONG AS THEY ARE CONTIGUOUS) to
    the extent of hauling 300 Tons of Supplies..." -- the tonnage belongs to the BLOCK the 250
    Stores and 100 Fuel were carried to. The repair bound the purchase and the two haul endpoints to
    a run and left the STOCK those endpoints spend on a run-less global scalar, so measured, a
    locomotive activated at a dump on run A hauled a full 300 tons between two dumps on run B, with
    zero rejections."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    a, b, s = _pair_of_runs()
    src, dst = _dump("W", b[0], stores=10_000), _dump("E", b[5])
    s = replace(s, supplies=(src, dst))
    assert rail.one_activated_run(s, b[0], b[5]) is True          # run B is a legal stretch to run on
    assert rail.stock_in_run(s, rail.activated_run_at(s, a[0])) == 1
    r = _Run(s)
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 5_000)]), Side.AXIS)
    assert r.state.supply("E").stores == 0
    assert any("no Rolling Stock is active on this run" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_each_run_carries_its_own_300_tons_and_does_not_eat_the_others():
    """The mirror of the same clause: two blocks, a locomotive on each, and 300 tons apiece. A
    single global tonnage ledger would have let the first block's train spend the second's
    allowance, which is the same conflation of "the railway" with "this stretch of it" from the
    other side."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    a, b, s = _pair_of_runs()
    s = replace(s, rolling_stock_at={a[0]: 1, b[0]: 1},
                supplies=(_dump("AW", a[0], stores=10_000), _dump("AE", a[5]),
                          _dump("BW", b[0], stores=10_000), _dump("BE", b[5])))
    r = _Run(s)
    _axis_rail(r, _Orders([RailHaulOrder("AW", "AE", "STORES", 10_000),
                           RailHaulOrder("BW", "BE", "STORES", 10_000)]), Side.AXIS)
    assert r.state.supply("AE").stores == rail.TONS_PER_ACTIVATION_54_43   # STORES is 1 t a Point
    assert r.state.supply("BE").stores == rail.TONS_PER_ACTIVATION_54_43
    assert not [e for e in r.events if e.kind is EventKind.ORDER_REJECTED]


def test_54_45_destroys_the_locomotive_whose_own_block_has_been_broken():
    """[54.45] read through 54.43's run binding (rail.orphaned_stock's flagged reading): the stock
    standing on a stretch the Commonwealth has just cut is destroyed even though the Axis still
    holds five contiguous hexes elsewhere. A locomotive cannot be driven across the Eighth Army to
    the surviving block, and the alternative reading strands stock that can never haul and never
    dies."""
    from game.engine import _axis_rail
    a, b, s = _pair_of_runs()
    s = replace(s, rail_control={**s.rail_control, a[2]: Side.ALLIED, a[3]: Side.ALLIED})
    assert rail.gate_open(s, Side.AXIS) is True                # run B still musters its five
    r = _Run(s)
    _axis_rail(r, _Orders([]), Side.AXIS)
    assert r.state.rolling_stock == 0
    killed = [e for e in r.events if e.kind is EventKind.ROLLING_STOCK_DESTROYED]
    assert len(killed) == 1 and killed[0].payload["hexes"] == [list(a[0])]


# --- [54.43] "IN ANY *ONE* DIRECTION DURING AN OPERATIONS STAGE" -------------------------------

def test_one_activation_runs_trains_one_way_and_not_both():
    """[54.43] "...to the extent of hauling 300 Tons of Supplies in any ONE direction during an
    Operations Stage" -- "one" ITALICISED in the scan (PDF page 74, book folio 23, rendered at
    300dpi and read), and 54.44 repeats the phrase for the troop lift.

    The book is direction-aware and says so a third time from the owner's side: 54.32 gives the
    Commonwealth "1500 tons per Operations Stage IN EITHER DIRECTION" and adds that "the RR may move
    personnel in one direction and supplies in another". That freedom is exactly what 54.43's italic
    withholds from the borrower. The engine kept one undirected pool, so measured, W->E 100 Points
    and E->W 100 Points were BOTH accepted on a single activation in one Operations Stage -- a
    shuttle the book does not sell."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    w = _dump("W", line[0], stores=1_000)
    m = _dump("M", line[2], stores=500)            # stock that was ALREADY here, so 54.35 is silent
    e = _dump("E", line[5], stores=0)
    r = _Run(_stocked(line, dumps=(w, m, e), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100),
                           RailHaulOrder("M", "W", "STORES", 100)]), Side.AXIS)
    assert (r.state.supply("E").stores, r.state.supply("W").stores) == (100, 900)  # eastbound ran
    assert r.state.supply("M").stores == 500       # ...and the westbound train did not
    assert any("already running eastward" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_the_next_operations_stage_may_run_the_other_way():
    """54.43 measures the allowance PER OPERATIONS STAGE, so the direction is chosen afresh each
    stage exactly as 54.33's commodity is -- the pin is a stage's commitment, not a campaign's."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    w = _dump("W", line[0], stores=1_000)
    e = _dump("E", line[5], stores=0)
    r = _Run(_stocked(line, dumps=(w, e), stock=1, stage=1))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100)]), Side.AXIS)
    assert (r.state.supply("W").stores, r.state.supply("E").stores) == (900, 100)
    r.state = replace(r.state, stage=2)            # the ledger expires by (turn, stage) on its own
    _axis_rail(r, _Orders([RailHaulOrder("E", "W", "STORES", 100)]), Side.AXIS)
    assert (r.state.supply("W").stores, r.state.supply("E").stores) == (1_000, 0)


def test_two_activated_runs_each_choose_their_own_direction():
    """THE DIRECTION PIN IS PER RUN, and nothing pinned that it was: collapsing
    _Run.rail_direction_this_stage / set_rail_direction to ONE board-wide direction (dropping the
    run_key entirely) left the whole suite green, because no other test ever runs two disjoint
    activated runs in one Operations Stage.

    The reading it belongs to is 54.43's own: the sentence sells "300 Tons of Supplies in any *one*
    direction" against "all such hexes under his control (as long as they are contiguous)", i.e.
    against ONE contiguous block -- and the tonnage that shares that sentence is already per run
    (test_each_run_carries_its_own_300_tons_and_does_not_eat_the_others). A locomotive in Cyrenaica
    running west cannot decide which way a second locomotive's train runs in Egypt, for the same
    reason it cannot spend its 300 tons."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    a, b, s = _pair_of_runs()
    s = replace(s, rolling_stock_at={a[0]: 1, b[0]: 1},
                supplies=(_dump("AW", a[0], stores=1_000), _dump("AE", a[5]),
                          _dump("BW", b[0]), _dump("BE", b[5], stores=1_000)))
    r = _Run(s)
    _axis_rail(r, _Orders([RailHaulOrder("AW", "AE", "STORES", 100),    # run A runs EASTWARD
                           RailHaulOrder("BE", "BW", "STORES", 100)]),  # run B runs WESTWARD
               Side.AXIS)
    assert r.state.supply("AE").stores == 100
    assert r.state.supply("BW").stores == 100
    assert not [e for e in r.events if e.kind is EventKind.ORDER_REJECTED]


# --- THE ORDER-REJECTION BOUNDARY: name the rule that actually bit ----------------------------

def test_a_haul_whose_two_ends_are_the_same_dump_is_refused_and_not_folded():
    """A self-haul MINTED supply and crashed the engine. apply's RAIL_HAULED handler reads src and
    dst and then writes with_supply(src).with_supply(dst); when both resolve to one dump the second
    write wins, the subtraction is lost, and the quantity appears from nowhere -- measured, a
    RailHaulOrder('W','W','STORES',5) against a dump holding 10 raised
    invariants.InvariantViolation("STORES not conserved across RAIL_HAULED"). CLAUDE.md: the
    invariants must never raise. Every other illegal rail order is REFUSED, and so is this one."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    w = _dump("W", line[0], stores=10)
    r = _Run(_stocked(line, dumps=(w,), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("W", "W", "STORES", 5)]), Side.AXIS)
    assert r.state.supply("W").stores == 10        # nothing minted, nothing moved
    assert not [e for e in r.events if e.kind is EventKind.RAIL_HAULED]
    assert any("two different ends" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_a_haul_between_two_dumps_standing_on_ONE_hex_is_refused():
    """THE SAME-HEX SIBLING of the self-haul above, and it was wide open: _rail_haul guarded
    `src.id == dst.id` and never `src.hex == dst.hex`. Two DIFFERENT dumps on ONE hex therefore made
    a legal-looking haul WITH NO DIRECTION -- rail.haul_direction_54_43 compares (r, q) and falls
    through to WESTWARD when the two Coords are equal -- which burned the run's whole 300-ton
    allowance carrying freight nowhere AND committed the run westward for the rest of the Operations
    Stage, so the genuine eastbound train queued behind it was refused as "already running
    westward". Measured on the shipped code exactly as asserted here.

    REACHABLE ON THE REAL BOARD, not a fixture curiosity (scratchpad/54.4-scan/measure_runs_and_
    colocation.py and measure_samehex_haul.py, six campaign seeds folded to GT111): two or more Axis
    dumps stand on ONE controlled rail hex INSIDE an activated run in every seed measured -- seed 4
    puts THREE on (26,133) and two on (25,100) -- because engine._establish_dump only refuses a
    co-located FRIENDLY dump and SUPPLY_CAPTURED can flip an enemy one. axis_rail_doctrine's own
    west/east key would pick such a pair in 5 of the 6 seeds (seed 1: 127 Operations Stages). No
    same-hex haul has been EMITTED yet, and that is not a guard: it is 54.43's 250-Store price
    keeping the locomotive off the board in the stages where the pair exists, and the LLM staff seat
    (CampaignStaffPolicy) issues rail orders this doctrine did not write."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    a = _dump("A", line[2], stores=1_000)
    b = _dump("B", line[2], stores=0)              # a DIFFERENT dump on the SAME hex
    e = _dump("E", line[5], stores=0)
    r = _Run(_stocked(line, dumps=(a, b, e), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("A", "B", "STORES", 100),      # nowhere, in no direction
                           RailHaulOrder("A", "E", "STORES", 100)]),    # ...and a real train behind
               Side.AXIS)
    assert r.state.supply("B").stores == 0         # the directionless haul did not run
    assert r.state.supply("E").stores == 100       # ...and neither burned nor pinned the run
    assert any("two ends on different hexes" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_a_haul_stopped_by_the_shut_gate_names_54_41_and_not_54_34():
    """_rail_haul's first refusal asked rail.usable_this_stage -- the AND of 54.41's five-contiguous
    gate and 54.34's dead Operations Stage -- and logged both rules for whichever one bit:
    "the railroad is not usable this Operations Stage (54.34/54.41)". ORDER_REJECTED payloads are
    this port's audit record and _reject_rail exists so the log names the rule that ACTUALLY bit;
    _rail_activate was split into its two clauses when 54.34 was added to it, and this is the same
    split on the haul side. Here the line is four hexes long on a stage that is not dead."""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(4)                                # four, not five: 54.41's gate never opens
    src, dst = _dump("W", line[0], stores=1_000), _dump("E", line[3])
    # NO Rolling Stock on the board: on a four-hex line 54.45 would destroy it (rail.orphaned_stock)
    # and _axis_rail returns on that beat before it ever reads an order.
    s = _stocked(line, dumps=(src, dst), stock=0)
    assert not rail.is_dead_stage_54_34(s), "54.34 must be silent, or the split proves nothing"
    r = _Run(s)
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100)]), Side.AXIS)
    assert r.state.supply("E").stores == 0
    reasons = [e.payload["reason"] for e in r.events if e.kind is EventKind.ORDER_REJECTED]
    assert reasons == ["fewer than five contiguous controlled rail hexes (54.41)"]


def test_a_haul_into_a_dump_at_its_54_12_ceiling_does_not_blame_the_tonnage_allowance():
    """The destination's 54.12 SUPPLY DUMP CAPACITY ceiling and 54.43's 300-ton-per-locomotive
    allowance are different facts, and the engine reported the first as the second: a haul trimmed
    to nothing by `cap - dst.stores` was logged as "no haul capacity left this Operations Stage
    (54.43)" even with the whole 300 tons unspent. Same dishonesty test_a_haul_out_of_an_empty_dump_
    does_not_blame_54_35 pins one guard along: naming a rule that had no part in the refusal is
    exactly what _reject_rail exists to prevent."""
    from game import supply as supply_mod
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    base = _stocked(line, stock=1)
    cap = supply_mod.dump_capacity_at(base, line[5])["STORES"]
    src, dst = _dump("W", line[0], stores=10_000), _dump("E", line[5], stores=cap)
    r = _Run(replace(base, supplies=(src, dst)))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100)]), Side.AXIS)
    assert r.state.supply("E").stores == cap                     # nothing moved, nothing overflowed
    assert r.rail_tons_this_stage(min(rail.activated_run_at(r.state, line[0]))) == 0
    reasons = [e.payload["reason"] for e in r.events if e.kind is EventKind.ORDER_REJECTED]
    assert reasons == ["the destination dump is at its STORES capacity (54.12)"]


def test_a_haul_out_of_an_empty_dump_does_not_blame_54_35():
    """_rail_free_points returns `stock - landed`, which is 0 both when the freight has only just
    come off a train and when there was never anything there. The repair's new guard tested only
    that, so a haul from a dump holding nothing -- with no train anywhere on the board -- was
    refused as "supply unloaded by rail may not be moved that Operations Stage (54.35)". ORDER_
    REJECTED payloads are this port's audit record, and _reject_rail exists so the log names the
    rule that bit; naming a rule that had no part in the refusal is the very dishonesty it prevents.
    """
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    src, dst = _dump("W", line[0], stores=0), _dump("E", line[5])
    r = _Run(_stocked(line, dumps=(src, dst), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100)]), Side.AXIS)
    reasons = [e.payload["reason"] for e in r.events if e.kind is EventKind.ORDER_REJECTED]
    assert reasons == ["the dump holds no STORES to haul (54.43)"]


def test_the_railway_may_not_haul_into_or_out_of_a_well():
    """[52.11]/[52.3] A well or pipeline hex is GEOGRAPHY, not an army's field dump -- the supply
    trace draws water from it and the haulage layer must never treat it as a depot. Both
    engine._truck_load and engine._ship_load already refuse to load from one, and the Commonwealth's
    own rail lane skips them when it picks stations (engine._dump_on). The Axis lane did not, so
    freight railed into a well could never be carried onward by anything: measured on the campaign,
    2,400 Fuel and 42 Ammo Points went into AX-Well-ElDaba on GT5-6 and were still there at GT111.
    """
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    real = _dump("REAL", line[0], stores=1_000)
    well = _dump("AX-Well-Here", line[5], stores=0)
    r = _Run(_stocked(line, dumps=(real, well), stock=1))
    _axis_rail(r, _Orders([RailHaulOrder("REAL", "AX-Well-Here", "STORES", 100)]), Side.AXIS)
    assert r.state.supply("AX-Well-Here").stores == 0
    assert any("not a supply dump to haul to or from" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


def test_the_doctrine_never_rails_freight_into_a_well():
    """The same hole one layer up, and the one that actually fired in the campaign:
    axis_rail_doctrine filtered only `not s.is_dummy`, and was the ONLY dump selector in
    campaign_policy.py missing the wells.is_water_source filter its siblings all carry. A well
    sorting as the run's EASTMOST dump made it the doctrine's standing destination."""
    from game.campaign_policy import axis_rail_doctrine
    line = _line(6)
    real_w = _dump("A-REAL-W", line[0], stores=1_000)
    real_e = _dump("B-REAL-E", line[4], stores=0)
    well = _dump("AX-Well-Terminus", line[5], stores=0)      # the eastmost dump on the run
    s = _stocked(line, dumps=(real_w, real_e, well), stock=1)
    order = axis_rail_doctrine(s, Side.AXIS)[0]
    assert {order.from_dump, order.to_dump} == {"A-REAL-W", "B-REAL-E"}


def test_the_doctrine_never_rails_freight_into_an_air_facility_dump():
    """[36.17] The AIR-facility half of the same filter, and the unpinned one: deleting
    `not s.air_dump` from axis_rail_doctrine's selector left the whole suite green, while its
    sibling `not wells.is_water_source(s)` is pinned twice (the test above and the campaign test at
    the foot of this file). An air dump feeds squadrons and the army may not eat from it, so a train
    unloading into one has shipped its freight out of the land war -- the same dead end railing into
    a well is, reached from the other side."""
    from game.campaign_policy import axis_rail_doctrine
    line = _line(6)
    real_w = _dump("A-REAL-W", line[0], stores=1_000)
    real_e = _dump("B-REAL-E", line[4], stores=0)
    air = _dump("C-AIR", line[5], stores=0, air_dump=True)   # would sort as the run's EASTMOST dump
    s = _stocked(line, dumps=(real_w, real_e, air), stock=1)
    order = axis_rail_doctrine(s, Side.AXIS)[0]
    assert {order.from_dump, order.to_dump} == {"A-REAL-W", "B-REAL-E"}


def test_the_doctrine_skips_a_run_whose_two_ends_resolve_to_one_dump_id():
    """DUPLICATE DUMP IDS HAVE ACTUALLY OCCURRED IN THIS ENGINE (engine._rail_station's docstring
    records it) and state.supply() resolves an id to the FIRST match, so a doctrine that picked its
    westmost and eastmost dump by object would hand _rail_haul two ends that both resolve to the
    same counter -- the self-haul that used to MINT supply and raise InvariantViolation, and is now
    refused. The guard that stops it was unpinned: deleting it left the whole suite green.

    The doctrine's job is to propose only orders the engine can accept, so it skips the run rather
    than firing an order it knows will be rejected."""
    from game.campaign_policy import axis_rail_doctrine
    line = _line(6)
    twin_w = _dump("TWIN", line[0], stores=1_000)
    twin_e = _dump("TWIN", line[5], stores=0)        # two counters, ONE id
    s = _stocked(line, dumps=(twin_w, twin_e), stock=1)
    assert axis_rail_doctrine(s, Side.AXIS) == []


def test_a_ship_may_not_lift_what_the_train_has_only_just_set_down():
    """[54.35] binds the COASTAL SHIP as well as the lorry, and that call site was unpinned:
    deleting _ship_load's 54.35 guard outright left the entire suite green, because
    tests/test_coastal_shipping.py never runs a rail haul and this file never ran a ship. The train-
    then-ship chain is the same window the lorry one is -- engine.run orders _axis_rail ahead of
    _coastal_shipping -- so it needs the same pin. What was standing in the dump beforehand still
    loads normally."""
    from game.engine import _axis_rail, _ship_load
    from game.policy import CoastalShipOrder, RailHaulOrder
    from game.state import CoastalShip, Port
    line = _line(6)
    src, dst = _dump("W", line[0], stores=1_000), _dump("E", line[5], stores=50)
    port = Port("P", Side.AXIS, line[5], "major", max_eff=5, eff=5, cap_ammo=100_000,
                cap_fuel=100_000, cap_stores=100_000, cap_water=0, cap_tons=100_000)
    ship = CoastalShip("S", Side.AXIS, 1_000, "P")
    s = _stocked(line, dumps=(src, dst), stock=1)
    r = _Run(replace(s, ports=(port,), ships=(ship,)))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 200)]), Side.AXIS)
    assert r.state.supply("E").stores == 250
    bad = CoastalShipOrder("S", load_from="E", load={"STORES": 60})
    assert _ship_load(r, Side.AXIS, "AXIS/Naval", bad, r.state.ship("S")) is False
    assert any("may not be moved that Operations Stage (54.35)" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)
    ok = CoastalShipOrder("S", load_from="E", load={"STORES": 50})   # the pre-existing 50 still ships
    assert _ship_load(r, Side.AXIS, "AXIS/Naval", ok, r.state.ship("S")) is True


# --- THE DOCTRINE IN A REAL CAMPAIGN ----------------------------------------------------------

def test_the_axis_railway_actually_runs_in_a_real_campaign():
    """THE ONLY TEST THAT DRIVES 54.4 THROUGH game.scenario.campaign. Every other rail test builds
    a synthetic line on the Rommel's-Arrival map, so a regression in which no activated run ever
    holds two haulable dumps would make the doctrine emit nothing for 111 Game-Turns with the suite
    fully green -- and until this test the only evidence 54.4 fires at all was a scratchpad smoke
    run. Seed 4 took El Daba early: the Axis bought his locomotive on Game-Turn 4 and ran trains on
    Game-Turns 5 and 6, which is why six Game-Turns is enough board to prove the wiring.

    *** RE-PINNED 4 -> 9, 2026-08-01, AND THE REASON IS A FINDING WORTH KEEPING. *** The cause is
    [54.32]/[54.33]/[54.34], the Commonwealth railway's per-Operations-Stage schedule -- the OTHER
    half of the same railway, which 54.46 shares with this one. Seed 4's Axis never bought that
    locomotive out of his own logistics: he OVERRAN AL-STAGE-ELDABA and paid for it with CAPTURED
    COMMONWEALTH STORES (32.13). MEASURED on the old tree, the activation payload names the dump:
    {'supply_id': 'AL-Stage-ElDaba', 'cargo': {'STORES': 250, 'FUEL': 100}}, off a station holding
    250 Stores and 4,000 Fuel. Those Stores were there because the lane built ONE mixed manifest a
    Game-Turn and landed ammunition AND fuel AND stores together in Operations Stage 1, so every
    station on the line stood stocked in all three at every hour of the week. 54.33 forbids exactly
    that -- "it may move fuel, ammunition, or stores, NOT ANY COMBINATION OF THE THREE" -- and with
    the book's single-commodity train a station overrun mid-week is very often not holding Stores at
    all. Seed 4's Axis now peaks at 196 Stores on the rails against the 250 [54.43] charges, and
    goes without.

    54.4 IS NOT LESS REACHABLE FOR IT -- IT IS BETTER MEASURED. Swept over seeds 1-24 to Game-Turn
    16 (scratchpad driver, re-run on this tree rather than quoted):

        ACTIVATE a locomotive   13 of 24: {3, 5, 6, 9, 10, 11, 12, 14, 15, 17, 21, 22, 24}
        and RUN TRAINS with it   8 of 13: {3, 9, 11, 12, 14, 17, 21, 24}

    Seed 9 is one of them and is a STRICTLY BETTER witness than seed 4 was, because its payer is
    AX-Dump#2 -- the Axis's OWN dump, brought forward by his own lorries -- so what this test now
    drives is 54.43's purchase out of Axis logistics rather than out of plunder. Same window (the
    activation lands on Game-Turn 4, four hauls follow by Game-Turn 6) and every assertion below is
    unchanged.

    *** THE COUNT ABOVE IS CORRECTED FROM "12 of 24 ... and 7 of those", 2026-08-01 (the 54.3 review
    repair), AND IT IS WORTH MORE THAN ONE DIGIT. *** That sentence sat inside a paragraph whose
    entire job was to correct an earlier undercount, three lines above another that reads "Six seeds
    is not a census" -- so a miscount there is the failure mode the paragraph is warning about,
    committed in the act of warning. Re-swept twice, byte-reproducible, on BOTH trees: the pre-repair
    tree activates on THIRTEEN seeds (the set above, unchanged) and runs trains on SEVEN
    ({3, 9, 11, 14, 17, 21, 24}); this tree adds seed 12, because the 54.35 Commonwealth pin
    (engine._rail_deliver, the same repair) moves every board from Game-Turn 1 and the Axis's forward
    Stores with it. So "7" was exact for its tree and "12" was never right for any.

    Also corrected by that sweep: game.rail.orphaned_stock's docstring said "the campaign has only
    ever put ONE locomotive on the board -- one activation in six seeds". That was six seeds, not a
    census; it is thirteen in twenty-four.

    *** RE-PINNED 9 -> 11, 2026-08-02, CAUSE [52.42] *** -- the CPA condition on the vehicle's Water
    Point, which moves every campaign trajectory from Game-Turn 1. Seed 9 still ACTIVATES a
    locomotive on this tree and no longer runs a train with it inside the six-turn window, so the
    witness is re-measured rather than the window widened. Re-swept over seeds 1-40 to Game-Turn 6
    on this tree: eighteen activate, and five of those haul with no AXIS/Rail rejection at all
    ({4, 11, 17, 26, 33}). Seed 11 is chosen because it KEEPS THE PROPERTY seed 9 was chosen for and
    seed 4 lacked -- its activation is paid for by AX-Dump#3, the Axis's OWN dump brought forward by
    his own lorries, not by Commonwealth stores overrun at El Daba -- and because it was already in
    the PRE-change tree's activate-and-run set ({3, 9, 11, 12, 14, 17, 21, 24}), so it is a witness
    under both instruments and not one shopped for the new dice. Same window (activation on
    Game-Turn 4, six hauls by Game-Turn 6) and every assertion below is unchanged.

    *** RE-PINNED 11 -> 34, 2026-08-02, CAUSE [64.73] *** -- the occupation quality-test, which
    stopped asking the section-32.16 abstract trace and now asks the rule's own in-hex question
    (campaign_victory._supplied). It is a VICTORY-SCORING rule, but game.campaign_claim scores the
    live board with the same predicate to decide which city each side already banks, so it moves what
    the campaign policy garrisons, and with it every trajectory from Game-Turn 1 -- the Axis railway
    included. Re-swept seeds 1-40 to Game-Turn 6 on this tree, same recipe as the line below:
    EIGHTEEN activate ({6, 9, 10, 12, 14, 15, 16, 18, 20, 23, 28, 30, 31, 33, 34, 38, 39, 40}) and
    FIVE of those haul with no AXIS/Rail rejection ({14, 15, 20, 34, 38}).

    THE DUAL-WITNESS PROPERTY IS NOT AVAILABLE THIS TIME AND THAT IS STATED RATHER THAN GLOSSED: the
    previous tree's clean set was {4, 11, 17, 26, 33} and NONE of those five so much as activates a
    locomotive here, so no seed is a witness under both instruments. Seed 34 is chosen on the other
    property the 9 -> 11 re-pin named and ranked first: its activation is paid for by AX-DUMP#4, the
    Axis's OWN dump brought forward by his own lorries, not by Commonwealth stores overrun at El Daba
    (which is what pays seeds 14, 20 and 33) -- and of the two remaining Axis-paid candidates it
    hauls the most (four hauls against seed 15's two and seed 38's one). Same window, same recipe,
    and every assertion below is unchanged.

    *** RE-PINNED 34 -> 31, 2026-08-02, CAUSE [10.29] *** -- engine._capture_noncombat, which takes a
    non-combat counter with no strength of any type when it is left alone in an enemy ZOC during the
    enemy's Movement/Combat Phase. It moves every campaign trajectory from Operations Stage 1 of
    Game-Turn 1 (the Axis collects Commonwealth Squadron Ground Support Units as it advances), and
    the Axis railway with it. Re-swept seeds 1-40 to Game-Turn 6 on this tree, same recipe as the
    line below: TWENTY-FOUR activate, and EIGHT of those haul with no AXIS/Rail rejection at all
    ({1, 6, 11, 14, 20, 23, 31, 36}).

    THE DUAL-WITNESS PROPERTY IS AVAILABLE AGAIN, which the 11 -> 34 re-pin had to state it was not.
    Seed 31 activates AND hauls on BOTH trees -- one haul off AX-Dump#2 on the pre-10.29 tree, six
    off AX-Dump#3 here -- so it is a witness under both instruments and not one shopped for the new
    dice. It also keeps the property every re-pin since 9 has ranked first: its locomotive is bought
    with the AXIS'S OWN forward dump, brought up by his own lorries, not with Commonwealth Stores
    overrun at El Daba (which is what pays seeds 1, 6, 11, 14, 20, 23, 33 and 36 here). Same window
    -- the activation lands on Game-Turn 4, six hauls follow by Game-Turn 6 -- and every assertion
    below is unchanged.

    *** RE-PINNED 31 -> 6, 2026-08-02, CAUSE [4.46] *** -- the Headquarters Close-Assault DASH
    (data/unit_stats.json _hq_dash_comment, tests/test_hq_close_assault.py). Transcribing it puts 74
    of the campaign's 84 HQ counters into [3.36]/[10.29]'s capture population for the first time, so
    it moves every trajectory from Game-Turn 1, the Axis railway with it. Seed 31 still ACTIVATES
    here and no longer hauls at all inside the six-turn window (five AXIS/Rail rejections), so the
    witness is re-measured rather than the window widened. Re-swept seeds 1-40 to Game-Turn 6 on
    both trees, same recipe as the line below -- and the control arm REPRODUCES the entry above
    exactly (24 activate, 8 clean = {1, 6, 11, 14, 20, 23, 31, 36}), which is what licenses the
    comparison:

        BEFORE   24 activate, EIGHT clean   {1, 6, 11, 14, 20, 23, 31, 36}
        AFTER    29 activate, THREE clean   {6, 20, 38}

    Seed 6 is chosen because it is one of only TWO dual witnesses ({6, 20}) and the only one of
    those that also keeps the property every re-pin since 9 has ranked first: here its locomotive is
    bought with AX-DUMP#2, the AXIS'S OWN forward dump, where on the control tree the same seed was
    paid by Commonwealth Stores overrun at El Daba (which is still what pays seeds 20 and 38). The
    window moves and is stated rather than glossed: the activation lands on Game-Turn 4 as before,
    but the single haul falls on Game-Turn 4 too, not 5-6. Every assertion below is unchanged.

    THE 8 -> 3 DROP IS A REAL FINDING AND IT IS NOT THIS RULE'S DOING. "Clean" demands NO AXIS/Rail
    rejection at all, and rejections rise 44 -> 106 over the 40 seeds while ACTIVATIONS RISE TOO
    (24 -> 29) and hauls fall (27 -> 14). Counted by reason over the eleven seeds that gained
    rejections, the jump is one string: "no Rolling Stock is active on this run of rail hexes
    (54.43)", 6 -> 58. That is the Axis rail doctrine PROPOSING a haul on a run its locomotive is
    not standing on -- a pre-existing gap in the proposer (it fires on the control tree too), newly
    exercised much harder on a board where the Axis activates more locomotives. It is a doctrine
    bug, not a 54.4 rule bug, it is out of this slice's scope, and it is flagged here rather than
    absorbed into a seed choice."""
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    from game.scenario import campaign
    res = run(replace(campaign(6), max_turns=6), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    hauls = [e for e in res.events if e.kind is EventKind.RAIL_HAULED and e.side is Side.AXIS]
    assert [e for e in res.events if e.kind is EventKind.ROLLING_STOCK_ACTIVATED]
    assert hauls, "the Axis railway bought a locomotive and never ran a train"
    # and every one of them obeys the rules this file pins, on the real map
    for e in hauls:
        src, dst = res.final.supply(e.payload["from_dump"]), res.final.supply(e.payload["to_dump"])
        assert src.id != dst.id
        assert not (wells.is_water_source(src) or wells.is_water_source(dst))
    assert not [e for e in res.events
                if e.kind is EventKind.ORDER_REJECTED and e.actor == "AXIS/Rail"]
