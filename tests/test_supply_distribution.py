"""Phase 4, slices S4/S6: the 48 V.C.6 Supply Distribution Segment (engine._supply_distribution) -- the
0-CP Organization-Phase beat that tops a unit's own pools back up from a co-located dump (UNIT_REFILLED,
a conserving dump->unit transfer). FUEL (49.14 tank) AND AMMO (50.0 'fire once' basic load) now; each
refills to its own intrinsic capacity.

coastal_corridor puts DAK-5le (Fuel Capacity 50, ammo_capacity 10) on the same hex as AX-Dump1 (fuel
60, ammo 40); its inline units start with empty pools (the pool-fill is oob.build only), which is
exactly the drained fixture this beat is for."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import invariants, supply
from game.engine import _Run, _supply_distribution
from game.events import EventKind, Side
from game.scenario import coastal_corridor


def _dak_refills(r, commodity="FUEL") -> list:
    return [e for e in r.events if e.kind == EventKind.UNIT_REFILLED
            and e.payload["unit_id"] == "DAK-5le"
            and e.payload["commodity"] == commodity]


def test_refills_a_drained_tank_from_a_colocated_dump():
    # DAK-5le (capacity 50, empty tank) sits on AX-Dump1 (fuel 60); the beat tops it to capacity,
    # draining the dump, and books a UNIT_REFILLED. Conservation is exact on a clean base (a transfer).
    s = coastal_corridor()
    assert s.unit("DAK-5le").fuel == 0 and supply.fuel_capacity(s.unit("DAK-5le")) == 50
    r = _Run(s)
    _supply_distribution(r, Side.AXIS)
    assert r.state.unit("DAK-5le").fuel == 50           # topped to capacity
    assert r.state.supply("AX-Dump1").fuel == 10        # 60 - 50 handed to DAK
    assert len(_dak_refills(r)) == 1                     # one FUEL refill
    # S6: the same beat now tops the 50.0 ammo basic load -- DAK's empty ammo pool fills to capacity
    # (10 = assault rate 2 x strength 5), draining the dump's ammo 40 -> 30.
    assert r.state.unit("DAK-5le").ammo == supply.ammo_capacity(s.unit("DAK-5le")) == 10
    assert r.state.supply("AX-Dump1").ammo == 30
    assert len(_dak_refills(r, "AMMO")) == 1
    invariants.check(r.state)                            # conservation + every invariant still holds


def test_no_refill_off_the_dump_network():
    # a unit that has outrun its dumps -- moved to a hex with no co-located dump -- refills nothing
    # (49.15: supply must be IN the hex). This is how distance costs fuel once S5 drains the tank.
    s = coastal_corridor()
    s = s.with_unit(replace(s.unit("DAK-5le"), hex=(2, 0)))   # bare desert, no dump
    r = _Run(s)
    _supply_distribution(r, Side.AXIS)
    assert r.state.unit("DAK-5le").fuel == 0            # still dry
    assert not _dak_refills(r)


def test_full_pools_draw_nothing():
    # a unit already at capacity in BOTH pools has no deficit -> the beat emits nothing for it.
    s = coastal_corridor()
    dak = s.unit("DAK-5le")
    s = s.with_unit(replace(dak, fuel=50, ammo=supply.ammo_capacity(dak)))   # both full
    r = _Run(s)
    _supply_distribution(r, Side.AXIS)
    assert not _dak_refills(r, "FUEL") and not _dak_refills(r, "AMMO")
    assert r.state.supply("AX-Dump1").fuel == 60            # DAK's dump untouched (both commodities)
    assert r.state.supply("AX-Dump1").ammo == 40


def test_refill_capped_by_dump_contents():
    # the dump gives only what it has: a 50-deficit against a 30-fuel dump drains the dump and leaves
    # the tank partly filled -- the transfer itself still conserves (dump -30, unit +30).
    s = coastal_corridor()
    s = s.with_supply(replace(s.supply("AX-Dump1"), fuel=30))    # only 30 in the dump
    r = _Run(s)
    _supply_distribution(r, Side.AXIS)
    assert r.state.unit("DAK-5le").fuel == 30           # got what the dump had
    assert r.state.supply("AX-Dump1").fuel == 0         # dump emptied
    assert len(_dak_refills(r)) == 1
