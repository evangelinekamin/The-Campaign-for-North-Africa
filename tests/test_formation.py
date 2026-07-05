"""Primitive A: Unit.formation -- a tail-appended shared field carrying the OOB
organisational group, so the staff layer can address units by formation without
re-deriving it. Adding the field must not disturb _morale_for (which already keys
on the same group string)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import oob
from game.events import Side
from game.state import StepRecord, Unit
from game.terrain import Mobility


def _bare_unit() -> Unit:
    return Unit("X", Side.AXIS, (0, 0), (StepRecord("s", 1),), mobility=Mobility.FOOT,
                cpa=1, stacking_points=1, oca=1, dca=1)


def test_oob_unit_exposes_nonempty_formation_group_string():
    units = oob.build(sections="ABC")[0]
    assert all(isinstance(u.formation, str) and u.formation for u in units)  # group carried


def test_formation_is_the_group_morale_keys_on():
    units = oob.build(sections="ABC")[0]
    aus = next(u for u in units if "Australian" in u.formation)
    assert aus.morale == oob._morale_for(aus.formation, aus.id)  # formation IS rec['group']


def test_bare_unit_defaults_formation_to_empty():
    assert _bare_unit().formation == ""


def test_formation_tail_default_leaves_existing_construction_intact():
    # every existing positional/keyword Unit(...) call is unaffected by the tail default
    assert _bare_unit().strength == 1
