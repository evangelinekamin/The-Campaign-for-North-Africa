"""[54.41] Axis rail control -- the sticky pass-through notion, and the five-contiguous-hex gate.

54.4's other cases (rolling stock 54.43, the 300-ton haul, the 900-ton troop lift 54.44) are all
downstream of this gate, so this is where the rule is proved reachable or not.
"""
import hashlib
from dataclasses import replace

import pytest

from game import rail
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
    edges = frozenset(frozenset((rails[i], rails[i + 1])) for i in range(len(rails) - 1))
    tm = replace(base.terrain, rails=edges)
    return replace(base, terrain=tm, units=tuple(units), rail_control={})


def _line(n, start=(0, 0)):
    """n hexes in a straight, mutually adjacent line on the odd-q grid."""
    from game import hexmap
    out = [start]
    while len(out) < n:
        nxt = next(h for h in hexmap.neighbors(out[-1]) if h not in out and h[1] >= out[-1][1])
        out.append(nxt)
    return out


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
    line = _line(9)
    s = _rail_state(line)
    u = next(x for x in rommels_arrival().units if x.side is Side.AXIS and x.is_combat)
    s = replace(s, units=(replace(u, hex=line[0]),))
    r = _Run(s)
    _rail_control_claim(r, r.state.unit(u.id), [line[0], line[2], line[4], line[6], line[8]])
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
