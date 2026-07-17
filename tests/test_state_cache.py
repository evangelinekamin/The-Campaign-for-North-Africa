"""Pins the derived-total caches on Unit and SupplyUnit (the perf(state) optimization).

Unit.strength / effective_strength and SupplyUnit.empty are cached at construction via
__post_init__ instead of recomputed on every read (rule 11.32 reads them ~38M times a run).
The cache is only safe because these are frozen dataclasses whose inputs change EXCLUSIVELY
through dataclasses.replace(), which re-runs __post_init__. These tests are the guard that the
cached field always equals the from-scratch recompute -- including across replace() -- and that
adding the compare/repr=False cache fields left equality, hash and repr byte-identical.
"""
from dataclasses import replace

from game.state import Side, StepRecord, SupplyUnit, Unit
from game.terrain import Mobility


def _unit(steps, broken_down=0):
    return Unit("u", Side.AXIS, (0, 0), steps, mobility=Mobility.MOTORIZED,
                cpa=10, stacking_points=1, oca=3, dca=3, broken_down=broken_down)


def _recompute_strength(u):
    return sum(s.strength for s in u.steps)


def test_unit_strength_cache_equals_recompute():
    u = _unit((StepRecord("a", 3), StepRecord("b", 4)))
    assert u.strength == _recompute_strength(u) == 7
    assert u._strength == u.strength


def test_unit_effective_strength_subtracts_broken_down():
    u = _unit((StepRecord("a", 5), StepRecord("b", 5)), broken_down=3)
    assert u.strength == 10
    assert u.effective_strength == u.strength - u.broken_down == 7
    assert u._effective_strength == u.effective_strength


def test_unit_cache_refreshes_on_replace_steps():
    u = _unit((StepRecord("a", 5), StepRecord("b", 5)))
    v = replace(u, steps=(StepRecord("a", 1),))
    assert v.strength == _recompute_strength(v) == 1
    assert v.effective_strength == 1


def test_unit_cache_refreshes_on_replace_broken_down():
    u = _unit((StepRecord("a", 5), StepRecord("b", 5)))
    v = replace(u, broken_down=4)
    assert v.strength == 10                    # steps unchanged
    assert v.effective_strength == 6           # cache followed broken_down


def test_unit_replace_hex_keeps_derived_totals():
    # The victory/claims landmine passes replace(u, hex=city); the derived totals must be
    # recomputed from the (unchanged) steps, not carried from a stale id-keyed cache.
    u = _unit((StepRecord("a", 5), StepRecord("b", 5)), broken_down=2)
    v = replace(u, hex=(9, 9))
    assert v.strength == 10 and v.effective_strength == 8


def test_unit_cache_fields_do_not_change_equality_or_repr():
    a = _unit((StepRecord("a", 3),))
    b = _unit((StepRecord("a", 3),))
    assert a == b and hash(a) == hash(b)
    assert "_strength" not in repr(a) and "_effective_strength" not in repr(a)


def _supply(ammo=0, fuel=0, stores=0, water=0):
    return SupplyUnit("d", Side.AXIS, (0, 0), ammo=ammo, fuel=fuel, stores=stores, water=water)


def test_supply_empty_cache_equals_recompute():
    for ammo, fuel, stores, water in [(0, 0, 0, 0), (1, 0, 0, 0), (0, 0, 3, 0), (-2, 0, 0, 0)]:
        su = _supply(ammo, fuel, stores, water)
        assert su.empty == (ammo <= 0 and fuel <= 0 and stores <= 0 and water <= 0)
        assert su._empty == su.empty


def test_supply_empty_cache_refreshes_on_replace():
    full = _supply(ammo=10)
    assert not full.empty
    drained = replace(full, ammo=0)
    assert drained.empty
    assert not full.empty                      # original untouched (immutability)


def test_supply_cache_field_does_not_change_equality():
    a = _supply(ammo=5)
    b = _supply(ammo=5)
    assert a == b and hash(a) == hash(b)
    assert "_empty" not in repr(a)
