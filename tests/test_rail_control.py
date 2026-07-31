"""[54.41] Axis rail control -- the sticky pass-through notion, and the five-contiguous-hex gate.

54.4's other cases (rolling stock 54.43, the 300-ton haul, the 900-ton troop lift 54.44) are all
downstream of this gate, so this is where the rule is proved reachable or not.
"""
import hashlib
from dataclasses import replace

import pytest

from game import movement, rail
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


def _line(n):
    """n mutually adjacent hexes that ACTUALLY EXIST on the scenario map.

    Synthetic coordinates are not enough: a haul asks supply.dump_capacity_at for the destination,
    which looks the hex up in the terrain map and raises KeyError on one the map never had. Walks a
    real chain with backtracking so it cannot dead-end in a corner."""
    if n in _LINE_CACHE:
        return _LINE_CACHE[n]
    from game import hexmap
    tm = rommels_arrival().terrain.terrain

    def walk(path):
        if len(path) == n:
            return path
        for nb in sorted(hexmap.neighbors(path[-1])):
            if nb in tm and nb not in path:
                got = walk(path + [nb])
                if got:
                    return got
        return None

    for seed_hex in sorted(tm):
        got = walk([seed_hex])
        if got:
            _LINE_CACHE[n] = got
            return got
    raise AssertionError(f"no {n}-hex connected chain on the map")


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

def _stocked(rails, dumps=(), stock=0, control=Side.AXIS, stage=1):
    """A state whose whole `rails` line is controlled by `control`, carrying `dumps`."""
    base = rommels_arrival()
    edges = frozenset(movement.edge(rails[i], rails[i + 1]) for i in range(len(rails) - 1))
    tm = replace(base.terrain, rails=edges)
    return replace(base, terrain=tm, supplies=tuple(dumps), units=(), stage=stage,
                   rail_control={h: control for h in rails}, rolling_stock=stock)


def _dump(did, hx, side=Side.AXIS, **q):
    from game.state import SupplyUnit
    return SupplyUnit(did, side, hx, ammo=q.get("ammo", 0), fuel=q.get("fuel", 0),
                      stores=q.get("stores", 0), water=q.get("water", 0))


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


def test_the_railroad_is_dead_one_operations_stage_a_month():
    """[54.34] via [54.46]: 'For the duration of one Operations Stage per month the railroad may
    not be used for anything. It is transporting water forward for railroad use.'"""
    from game.engine import _axis_rail
    from game.policy import RailHaulOrder
    line = _line(6)
    src, dst = _dump("W", line[0], stores=100_000), _dump("E", line[5])
    r = _Run(_stocked(line, dumps=(src, dst), stock=1, stage=rail.dead_stage_54_34(None)))
    _axis_rail(r, _Orders([RailHaulOrder("W", "E", "STORES", 100_000)]), Side.AXIS)
    assert r.state.supply("E").stores == 0
    assert any("not usable this Operations Stage" in e.payload.get("reason", "")
               for e in r.events if e.kind is EventKind.ORDER_REJECTED)


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
