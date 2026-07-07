"""Step 8: the fog god-view split. Zero-token -- a pure diff of two observe() calls.
The seats reason off the fogged view; the narrator alone reads the god-view, and the
staff-vs-viewer irony (a stack the audience sees that the staff cannot) is computable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import narrator                                           # noqa: E402
from game.events import Side                                        # noqa: E402
from game.observation import observe                                # noqa: E402
from game.scenario import rommels_arrival                          # noqa: E402
from game.staff import Lane, role_brief, unit_lanes                 # noqa: E402


def test_god_view_reveals_stacks_absent_from_every_seat_brief():
    """The design irony, made computable: at the opening the Commonwealth stacks stand
    outside the flat SIGHTING radius, so they are ABSENT from every seat's role_brief
    enemy_sightings yet PRESENT in the narrator's god-view."""
    state = rommels_arrival(seed=4200)
    hidden = narrator.hidden_from_staff(state, Side.AXIS)
    assert hidden, "expected Commonwealth stacks beyond SIGHTING at the opening"
    hidden_hexes = {tuple(s["hex"]) for s in hidden}

    fogged = observe(state, Side.AXIS)               # what a seat actually reasons off
    idl = unit_lanes(state, Side.AXIS)
    for lane in (Lane.MOBILE, Lane.INFANTRY, Lane.QM):
        brief = role_brief(fogged, lane, idl)
        seat_hexes = {tuple(s["hex"]) for s in brief["enemy_sightings"]}
        assert hidden_hexes.isdisjoint(seat_hexes)   # absent from the seat's brief

    god = observe(state, Side.AXIS, reveal_all=True)
    god_hexes = {tuple(s["hex"]) for s in god["enemy_sightings"]}
    assert hidden_hexes <= god_hexes                 # present in the god-view


def test_hidden_is_exactly_god_view_minus_fogged():
    """hidden_from_staff is precisely the set difference (god-view enemy hexes minus the
    fogged staff's) -- a pure, total diff, nothing invented."""
    state = rommels_arrival(seed=4200)
    god = {tuple(s["hex"]) for s in observe(state, Side.AXIS, reveal_all=True)["enemy_sightings"]}
    fog = {tuple(s["hex"]) for s in observe(state, Side.AXIS)["enemy_sightings"]}
    hidden = {tuple(s["hex"]) for s in narrator.hidden_from_staff(state, Side.AXIS)}
    assert hidden == god - fog
