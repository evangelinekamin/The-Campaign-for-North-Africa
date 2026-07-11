"""Campaign victory conditions (rule 64.7) as a pluggable VictorySpec.

The full campaign is not won by taking one hex -- it is a five-year point tally. This
module implements the faithful CORE of rule 64.7:

  - 64.71 (spatial core): the Axis auto-wins by occupying every hex of Alexandria AND
    Cairo with a combat unit.
  - annihilation: a side with no living unit loses.
  - 64.73: at the final turn, each side scores the Geographic Occupation Points of the
    cities its combat units hold (data/victory_cities.json).
  - 64.76: the two totals are graded as a ratio of most-to-least into Draw / Marginal /
    Decisive / Smashing.

DEFERRED to the faithfulness pass (they need the truck-MP supply trace, C1-5, and the
production economy, C3), documented so nothing is silently missing:
  - 64.71's "for one full Game-Turn" persistence and the <=90 truck-MP supply trace;
  - 64.72's Game-Turn-35 Commonwealth auto-win (no Axis unit can trace <=60 truck-MP);
  - 64.73's occupation quality-tests (a holding unit needs a week of Stores/Water and
    Fuel/Ammunition for three fires and 20 CP of movement);
  - 64.74 unused-Replacement-Point VPs and 64.75 Commonwealth Withdrawal VPs.
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from . import coords
from .events import Side

if TYPE_CHECKING:                       # avoid a runtime import cycle (engine owns _Run)
    from .engine import _Run

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "victory_cities.json")


def load_victory_cities() -> dict:
    with open(_DATA) as f:
        return json.load(f)


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


class CampaignVictory:
    """Rule 64.7 victory as a strategy. Construct once (parses the city table) and hand
    to GameState.victory; the engine calls check() each Record Phase and decide() at the
    final turn."""

    def __init__(self, data: "dict | None" = None):
        data = data or load_victory_cities()
        # (axial, axis_vp, cwlth_vp, name) per 64.73 city.
        self.cities = [(_ax(c["hex"]), c["axis_vp"], c["cwlth_vp"], c["name"])
                       for c in data["cities"]]
        # The 64.71 auto-win objective: every hex of Alexandria and Cairo.
        self.objective = [_ax(h) for h in
                          data["auto_win"]["alexandria"] + data["auto_win"]["cairo"]]

    def _occupier(self, state, ax) -> "Side | None":
        """The side holding a hex for victory purposes: a combat unit of at least 1 TOE
        Strength there (rule 64.73). Non-combat units (truck convoys, bare HQs) and
        supply dumps do not occupy. None if the hex is empty."""
        for u in state.units_at(ax):
            if u.is_combat and u.strength >= 1:
                return u.side
        return None

    def check(self, r: "_Run") -> tuple["Side | None", str]:
        s = r.state
        if all(self._occupier(s, ax) == Side.AXIS for ax in self.objective):
            return Side.AXIS, "Axis auto-victory: Alexandria and Cairo occupied (64.71)"
        if not s.living(Side.ALLIED):
            return Side.AXIS, "Axis victory by annihilation"
        if not s.living(Side.AXIS):
            return Side.ALLIED, "Allied victory by annihilation"
        return None, ""

    def decide(self, r: "_Run") -> tuple["Side | None", str]:
        s = r.state
        axis_vp = cwlth_vp = 0
        for ax, avp, cvp, _name in self.cities:
            side = self._occupier(s, ax)
            if side == Side.AXIS:
                axis_vp += avp
            elif side == Side.ALLIED:
                cwlth_vp += cvp
        return grade(axis_vp, cwlth_vp)


def grade(axis_vp: int, cwlth_vp: int) -> tuple["Side | None", str]:
    """Rule 64.76: compare the totals as a ratio of most-to-least. Even is a Draw;
    otherwise better-than-1:1 up to 1.5:1 is Marginal, up to 2.5:1 Decisive, beyond
    Smashing. A shutout (loser at 0) is a Smashing Victory."""
    if axis_vp == cwlth_vp:
        return None, f"Draw at {axis_vp}-{cwlth_vp} Victory Points (64.76)"
    winner = Side.AXIS if axis_vp > cwlth_vp else Side.ALLIED
    most, least = max(axis_vp, cwlth_vp), min(axis_vp, cwlth_vp)
    ratio = most / least if least > 0 else float("inf")
    if ratio <= 1.5:
        level = "Marginal Victory"
    elif ratio <= 2.5:
        level = "Decisive Victory"
    else:
        level = "Smashing Victory"
    name = "Axis" if winner == Side.AXIS else "Commonwealth"
    return winner, f"{name} {level}: {axis_vp}-{cwlth_vp} Victory Points (64.76)"
