"""EXTRA GATE for the delta-aware invariant checker (game.invariants.check_event).

The parity harness cannot see this optimisation: invariants are read-only, so the event log
is byte-identical whether the full O(state) sweep or the incremental checker runs. The risk is
COVERAGE -- a slice the incremental checker forgets to look at. These two tests bound it:

(1) EQUIVALENCE -- over recorded rommel + campaign logs, the incremental checker and the full
    sweep return an IDENTICAL raise/no-raise verdict at EVERY event. On legal play neither
    raises, so this proves check_event never spuriously fires on a real campaign (the
    "invariants must never raise on legal play" contract) AND that the per-EventKind slice
    mapping is complete for every kind the engine actually emits.

(2) FAULT INJECTION -- for each event family an INVALID outcome (a mutated post-state) is caught
    by check_event immediately, or -- for a cross-slice fault the per-slice checks cannot see --
    by the next STAGE/TURN boundary full sweep, and no later than that boundary.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import pytest                                                     # noqa: E402

from game.apply import apply                                     # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,            # noqa: E402
                                  CampaignCommonwealthPolicy)
from game.engine import run                                      # noqa: E402
from game.events import Event, EventKind, Phase, Side            # noqa: E402
from game.invariants import InvariantViolation, check, check_event  # noqa: E402
from game.policy import ScriptedPolicy                           # noqa: E402
from game.scenario import campaign, rommels_arrival             # noqa: E402
from game.state import StepRecord                                # noqa: E402


def _verdict(fn):
    """None if fn() does not raise InvariantViolation, else the raised message."""
    try:
        fn()
        return None
    except InvariantViolation as exc:
        return str(exc)


def _ev(kind: EventKind, payload: dict) -> Event:
    """A synthetic event; check_event reads only kind + payload (and pre/post), never the
    audit fields, so dummy seq/turn/phase/side/actor are sufficient."""
    return Event(0, 1, Phase.MOVEMENT, Side.AXIS, "TEST", kind, payload)


# --- (1) EQUIVALENCE ---------------------------------------------------------------------

def _recorded_logs():
    yield ("rommel:42",
           run(rommels_arrival(seed=42), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.AXIS)))
    yield ("campaign:4/mt8",
           run(campaign(seed=4, max_turns=8), CampaignAxisPolicy(), CampaignCommonwealthPolicy()))


def test_incremental_verdict_matches_full_sweep_at_every_event():
    seen: set[str] = set()
    for label, res in _recorded_logs():
        state = res.initial
        for e in res.events:
            pre = state
            state = apply(pre, e)
            full = _verdict(lambda: check(state))
            delta = _verdict(lambda: check_event(pre, state, e))
            assert (full is None) == (delta is None), (
                f"{label} seq={e.seq} kind={e.kind.value}: "
                f"full={full!r} delta={delta!r}")
            seen.add(e.kind.value)

    # The logs must have driven every guard family through the REAL engine (not a degenerate
    # log that trivially agrees). Byte-identity freezes these runs, so this coverage is stable.
    required = {
        "SUPPLY_CONSUMED", "SUPPLY_ARRIVED", "SUPPLY_CAPTURED", "SUPPLY_DUMP_ESTABLISHED",
        "SUPPLY_DUMP_BLOWN", "WELL_REFILLED", "TRUCK_LOADED", "TRUCK_UNLOADED", "TRUCK_MOVED",
        "UNIT_MOVED", "UNIT_RETREATED", "STEP_LOST", "CP_EXPENDED", "VEHICLE_BROKE_DOWN",
        "PORT_EFFICIENCY_CHANGED", "STAGE_ADVANCED", "TURN_ADVANCED",
    }
    assert required <= seen, f"equivalence logs did not exercise: {sorted(required - seen)}"


# --- (2) FAULT INJECTION -----------------------------------------------------------------

@pytest.fixture(scope="module")
def base():
    """A clean, fully-populated initial state (303 units, 233 dumps, 3 ports, 10 trucks);
    check(base) does not raise. Immutable, so the fault tests share one build safely."""
    b = campaign(seed=4)
    check(b)                                        # guard: the base itself must be legal
    return b


def test_fault_unit_negative_step(base):
    u = base.units[0]
    bad = replace(u, steps=(replace(u.steps[0], strength=-1),) + u.steps[1:])
    post = base.with_unit(bad)
    ev = _ev(EventKind.UNIT_MOVED,
             {"unit_id": u.id, "from": list(u.hex), "to": list(u.hex), "cp_spent": 0.0})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_unit_broken_down_negative(base):
    u = base.units[0]
    post = base.with_unit(replace(u, broken_down=-3))
    ev = _ev(EventKind.VEHICLE_REPAIRED, {"unit_id": u.id, "amount": 3})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_overstacked_destination(base):
    u = base.units[0]
    heavy = replace(u, stacking_points=6, arrival_turn=1,
                    is_garrison_home=False, is_pure_aa=False, is_first_line_truck=False)
    post = base.with_unit(heavy)
    ev = _ev(EventKind.UNIT_MOVED,
             {"unit_id": u.id, "from": list(u.hex), "to": list(u.hex), "cp_spent": 0.0})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_supply_negative_pool(base):
    su = base.supplies[0]
    post = base.with_supply(replace(su, fuel=-10))
    ev = _ev(EventKind.SUPPLY_CONSUMED,
             {"supply_id": su.id, "commodity": "FUEL", "qty": su.fuel + 10})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_conservation_mint(base):
    # 500 ammo appears in the dump with no matching initial/consumed credit -- a mint.
    su = base.supplies[0]
    post = base.with_supply(replace(su, ammo=su.ammo + 500))
    ev = _ev(EventKind.SUPPLY_ARRIVED, {"supply_id": su.id, "cargo": {}})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_truck_negative_cargo(base):
    t = base.trucks[0]
    post = base.with_truck(replace(t, fuel=-5))
    ev = _ev(EventKind.TRUCK_MOVED, {"truck_id": t.id, "to": list(t.hex), "fuel": 5})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_truck_load_non_conserving(base):
    # Cargo lands on the truck but is never taken off the dump -- the 2-entity conservation
    # delta must sum BOTH touched pools to see the mint (forgetting the truck would miss it).
    su, t = base.supplies[0], base.trucks[0]
    post = base.with_truck(replace(t, ammo=t.ammo + 50))
    ev = _ev(EventKind.TRUCK_LOADED,
             {"supply_id": su.id, "truck_id": t.id, "cargo": {"AMMO": 50}})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_rail_haul_non_conserving(base):
    # The from_dump/to_dump key path: supply lands at the destination but never leaves the source.
    a, b = base.supplies[0], base.supplies[1]
    post = base.with_supply(replace(b, ammo=b.ammo + 40))
    ev = _ev(EventKind.RAIL_HAULED,
             {"from_dump": a.id, "to_dump": b.id, "commodity": "AMMO", "qty": 40})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_port_eff_out_of_range(base):
    p = base.ports[0]
    post = base.with_port(replace(p, eff=p.max_eff + 5))
    ev = _ev(EventKind.PORT_EFFICIENCY_CHANGED, {"port_id": p.id, "level": p.max_eff + 5})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_fort_negative_level(base):
    coord = base.units[0].hex
    post = base.with_fort_level(coord, -1)
    ev = _ev(EventKind.FORT_REDUCED, {"hex": list(coord), "level": -1})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_duplicate_id(base):
    # SUPPLY_DUMP_ESTABLISHED is the one fold that mints a new entity id; collide it with a unit.
    from game.state import SupplyUnit
    dup = base.units[0].id
    newdump = SupplyUnit(dup, Side.AXIS, base.units[0].hex, ammo=0, fuel=0)
    post = replace(base, supplies=base.supplies + (newdump,))
    ev = _ev(EventKind.SUPPLY_DUMP_ESTABLISHED,
             {"supply_id": dup, "side": "AXIS", "hex": list(base.units[0].hex)})
    assert _verdict(lambda: check_event(base, post, ev)) is not None


def test_fault_cross_slice_caught_at_boundary_not_before(base):
    # A latent violation on a dump the current event does NOT touch: the per-slice delta of a
    # benign event cannot see it, but the next OpStage boundary's full sweep MUST -- bounding any
    # missed cross-slice violation to a single Operations Stage.
    su = base.supplies[0]
    tainted = base.with_supply(replace(su, fuel=-99))
    benign = _ev(EventKind.PHASE_ADVANCED, {"phase": "MOVEMENT", "active_side": "AXIS"})
    assert _verdict(lambda: check_event(tainted, tainted, benign)) is None      # delta skips it
    boundary = _ev(EventKind.STAGE_ADVANCED, {"stage": 2})
    assert _verdict(lambda: check_event(tainted, tainted, boundary)) is not None  # backstop catches
