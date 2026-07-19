"""Step 5: dry-run adjudication + the QM fuel lever. When a panzer and an Italian
formation contend for one under-fuelled dump, the Chief rules the oversubscribed
dump structurally (one STAFF_ADJUDICATION), and the fuel lever -- draw-priority ==
batch position -- lets the panzer drain the dump first while the trailing Italian
hits the engine's real 'no fuel' rejection. A STAFF_DISSENT records the protest.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

# The QM seat's oversubscribed-dump adjudication (below) is built on the ABSTRACT 32.16 half-CPA trace:
# it detects two units "tracing" to one dump and rations it. The Phase-4 in-hex switch (S5) makes that
# premise obsolete -- only a CO-LOCATED unit draws, and the 48 V.C.6 Supply Distribution beat now tops
# co-located units up automatically -- so this adjudication needs a co-location-based redesign. That is a
# coherent piece of the DEFERRED staff-layer in-hex pass (the design's S11 policy rewrite), not a bolt-on:
# the whole StaffPolicy supply reasoning moves to in_hex together. The engine's in-hex fuel + refill are
# fully covered by test_in_hex_draw / test_supply_distribution / test_fuel_tank. Tracked in memory
# (cna-s5-benchmark-degeneracy) and the port plan.
_STAFF_SUPPLY_IN_HEX_DEFERRED = "staff QM supply adjudication awaits the in-hex staff-layer redesign (S11)"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import _mock_staff                         # noqa: E402

from game.engine import run                                       # noqa: E402
from game.events import EventKind, Phase, Side                    # noqa: E402
from game.llm import MockClient                                   # noqa: E402
from game.policy import ScriptedPolicy                            # noqa: E402
from game.scenario import coastal_corridor                        # noqa: E402
from game.staff_policy import StaffPolicy                         # noqa: E402
from game.state import StepRecord, SupplyUnit, Unit               # noqa: E402
from game.supply import COMMODITIES                               # noqa: E402
from game.terrain import Mobility                                 # noqa: E402

PANZER = "GE-Pz"
ITALIAN = "IT-Inf"


def _oversubscribed_state(phase: Phase = Phase.WEATHER):
    """A panzer and an Italian battalion both trace to ONE dump holding fuel for just
    one move. Both are motorized (they burn fuel); the dump is co-located with the
    panzer and one hex from the Italian (inside its supply trace)."""
    base = coastal_corridor()
    panzer = Unit(PANZER, Side.AXIS, (2, 0), (StepRecord("pz", 1),),
                  mobility=Mobility.VEHICLE, cpa=20, stacking_points=1, oca=6, dca=6,
                  formation="GE 5th Light Panzer Division")
    italian = Unit(ITALIAN, Side.AXIS, (1, 0), (StepRecord("inf", 1),),
                   mobility=Mobility.VEHICLE, cpa=20, stacking_points=1, oca=5, dca=5,
                   formation="IT Pavia Division")
    garrison = Unit("UK-Gar", Side.ALLIED, base.target_hex, (StepRecord("inf", 4),),
                    mobility=Mobility.FOOT, cpa=10, stacking_points=2, oca=5, dca=8)
    supplies = (
        SupplyUnit("AX-Shared", Side.AXIS, (2, 0), ammo=40, fuel=2),   # fuel for ONE move
        SupplyUnit("UK-Dump", Side.ALLIED, base.target_hex, ammo=40, fuel=60),
    )
    initial = {c: sum(getattr(s, c.lower()) for s in supplies) for c in COMMODITIES}
    return replace(base, phase=phase, units=(panzer, italian, garrison),
                   supplies=supplies, initial_supply=initial)


@pytest.mark.skip(reason=_STAFF_SUPPLY_IN_HEX_DEFERRED)
def test_chief_rules_the_oversubscribed_dump_and_sorts_the_panzer_first():
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    state = _oversubscribed_state(phase=Phase.MOVEMENT)
    moves = axis.movement(state, Side.AXIS)
    staff = axis.drain_staff()
    adj = [p for k, p in staff if k == EventKind.STAFF_ADJUDICATION]
    assert len(adj) == 1
    assert adj[0]["conflict"] == "oversubscribed-dump"
    assert adj[0]["favored"] == "GE 5th Light Panzer Division"
    assert adj[0]["denied"] == "IT Pavia Division"
    assert any(k == EventKind.STAFF_DISSENT for k, _ in staff)
    ids = [m.unit_id for m in moves]
    assert ids.index(PANZER) < ids.index(ITALIAN)         # draw-priority == batch position


@pytest.mark.skip(reason=_STAFF_SUPPLY_IN_HEX_DEFERRED)
def test_engine_drains_the_dump_panzer_first_italian_rejected_no_fuel():
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    result = run(_oversubscribed_state(), axis=axis,
                 allied=ScriptedPolicy(attacker=Side.AXIS))
    ev = result.events

    def first(pred):
        return next((i for i, e in enumerate(ev) if pred(e)), None)

    consumed = first(lambda e: e.kind == EventKind.SUPPLY_CONSUMED
                     and e.payload.get("unit_id") == PANZER
                     and e.payload.get("commodity") == "FUEL")
    rejected = first(lambda e: e.kind == EventKind.ORDER_REJECTED
                     and e.payload.get("unit_id") == ITALIAN
                     and "no fuel" in e.payload.get("reason", ""))
    assert consumed is not None and rejected is not None
    assert consumed < rejected                            # panzer drains first, Italian starves
    adj = [e for e in ev if e.kind == EventKind.STAFF_ADJUDICATION
           and e.payload.get("conflict") == "oversubscribed-dump"]
    assert len(adj) == 1                                  # exactly one, on the first side-turn
    assert any(e.kind == EventKind.STAFF_DISSENT for e in ev)
