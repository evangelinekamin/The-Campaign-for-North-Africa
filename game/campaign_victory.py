"""Campaign victory conditions (rule 64.7) as a pluggable VictorySpec.

The full campaign is not won by taking one hex -- it is a five-year point tally. This
module implements the faithful CORE of rule 64.7:

  - 64.71: the Axis auto-wins by occupying every hex of Alexandria AND Cairo with a
    combat unit, and holding them FOR ONE FULL GAME-TURN.
  - 64.73: at the final turn, each side scores the Geographic Occupation Points of the
    cities its combat units hold (data/victory_cities.json).
  - 64.76: the two totals are graded as a ratio of most-to-least into Draw / Marginal /
    Decisive / Smashing.

Rule 64.7 has NO annihilation clause, and this module no longer invents one. A side with
no living unit left does not lose the campaign the instant its last counter dies: the war
runs to Game-Turn 111 and is settled on the 64.73 tally, exactly as the book has it. (The
engine's built-in Race-for-Tobruk spec, engine._victory, still carries the same invented
branch under rule 61.8, which likewise does not define it -- out of scope here.)

DEFERRED to the faithfulness pass (they need the truck-MP supply trace, C1-5, and the
production economy, C3), documented so nothing is silently missing:
  - 64.71's <=90 truck-MP line of supply back to a Tobruk/Tripoli-fed dump (the "for one
    full Game-Turn" half is now implemented -- see CampaignVictory._held_since);
  - 64.72's Game-Turn-35 Commonwealth auto-win (no Axis unit can trace <=60 truck-MP);
  - 64.73's Stores/Water week-test and the in-hex "do you HAVE it" form of the occupation
    quality-test. The Fuel-for-20-CP and Ammunition-for-three-fires MAGNITUDES are now faithful
    (CampaignVictory._supplied); the Stores/Water week and the in-hex form still need the
    truck-MP supply trace, C1-5, so a holder is still tested by a reach-a-dump trace (32.16);
  - 64.74 unused-Replacement-Point VPs and 64.75 Commonwealth Withdrawal VPs.
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from . import coords, supply
from .events import Side

if TYPE_CHECKING:                       # avoid a runtime import cycle (engine owns _Run)
    from .engine import _Run

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "victory_cities.json")

# Rule 5.1 defines 64.71's unit of time in the book's own words: the Players "complete their
# operations within one Operations Stage, proceed to the second, and then the third, thus
# finishing ONE FULL GAME-TURN". So a full Game-Turn is three Operations Stages -- and since the
# engine tests victory in the Record Phase of every stage, it is three checks of elapsed time.
_STAGES_PER_TURN = 3


def load_victory_cities() -> dict:
    with open(_DATA) as f:
        return json.load(f)


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


def _opstage(state) -> int:
    """A strictly monotone ordinal for the Operations Stage the state stands in (rule 5.1),
    so two victory checks can be subtracted to give the elapsed game time between them."""
    return state.turn * _STAGES_PER_TURN + state.stage


class CampaignVictory:
    """Rule 64.7 victory as a strategy. Construct once (parses the city table) and hand
    to GameState.victory; the engine calls check() each Record Phase and decide() at the
    final turn.

    The instance is READ-ONLY once built -- it is the charts, not the game. What 64.71's hold
    needs to remember across checks belongs to the run, not to the spec (see _held_since), so
    one built state may be run any number of times and every run starts with its own clock."""

    def __init__(self, data: "dict | None" = None):
        data = data or load_victory_cities()
        # (axial, axis_vp, cwlth_vp, name) per 64.73 city.
        self.cities = [(_ax(c["hex"]), c["axis_vp"], c["cwlth_vp"], c["name"])
                       for c in data["cities"]]
        # The 64.71 auto-win objective: every hex of Alexandria and Cairo.
        self.objective = [_ax(h) for h in
                          data["auto_win"]["alexandria"] + data["auto_win"]["cairo"]]

    def _occupier(self, state, ax) -> "Side | None":
        """The side holding a hex for victory purposes: a SUPPLIED combat unit of at least 1
        TOE Strength there (rule 64.73). Non-combat units (truck convoys, bare HQs) and supply
        dumps do not occupy; nor does a unit that has OUTRUN its supply -- 64.73's occupation
        quality-test is that a holder can trace Fuel and Ammunition, so a stranded spearhead on
        a city scores nothing. This is what makes the campaign a logistical contest and not a
        foot-race: the Axis must keep its advance supplied to bank the ground it takes."""
        for u in state.units_at(ax):
            if u.is_combat and u.strength >= 1 and self._supplied(state, u):
                return u.side
        return None

    @staticmethod
    def _supplied(state, u) -> bool:
        """Rule 64.73 quality-test, FAITHFUL MAGNITUDES. At the end of the game a holder must have the
        Fuel to MOVE 20 CP (supply.fuel_cost applies the 49.13 rate x ceil(CP/5) x TOE-strength law;
        foot units need none) and the Ammunition to FIRE ITS WEAPONS THREE TIMES (3 x supply.ammo_cost,
        50.14). Both are traced to a reachable dump over the cpa/2 trace (32.16). A unit that cannot
        has outrun its logistics.

        The magnitudes were wrong before this port: Fuel was tested at one turn's bare rate (not 20 CP
        of movement) and Ammunition at a SINGLE fire (not three). STILL DEFERRED to T1-1 (the in-hex
        supply model, 49.14 + 53.11): 64.73 also names a WEEK of Stores and Water first, which needs
        the per-unit basic-load model to test; and the rule asks 'do you HAVE it in the hex?' where
        this still asks 'can you REACH a dump that holds it?'. The MAGNITUDES are corrected here; the
        Stores/Water week and the in-hex FORM wait on the truck-MP supply trace."""
        return (supply.plan_draw(state, u, supply.FUEL, supply.fuel_cost(u, 20)) is not None
                and supply.plan_draw(state, u, supply.AMMO, 3 * supply.ammo_cost(u, phasing=True)) is not None)

    @staticmethod
    def _held_since(r: "_Run", held: bool) -> "int | None":
        """The 64.71 hold clock: the Operations Stage at which the Axis's CURRENT unbroken
        occupation of the Delta began, or None if the Delta is not occupied right now. Any
        break restarts it -- one hex retaken, or one holder outrunning its supply (64.73), and
        the Axis must hold the full Game-Turn again from scratch.

        The clock lives in the run's scratch, not on this object: a VictorySpec is built once
        per built state (game.scenario.campaign) and two runs of that one state must not share
        a clock. It is not GameState either -- it is a fact about the run, and folding it into
        the state would put a derived counter in the event log for a condition that can be
        recomputed from the checks themselves."""
        scratch = r.victory_scratch
        if not held:
            scratch.pop("delta_held_since", None)
            return None
        return scratch.setdefault("delta_held_since", _opstage(r.state))

    def check(self, r: "_Run") -> tuple["Side | None", str]:
        """Rule 64.71, the Axis's outright win: every hex of Alexandria AND Cairo occupied,
        held FOR ONE FULL GAME-TURN, regardless of the turn or date. Before this port the win
        fired the instant the last hex was entered. The persistence is the rule's own clause,
        and it is what gives the Commonwealth an answer: a full Game-Turn of activations to
        throw the spearhead back out of one Delta hex, which denies the win rather than merely
        postponing it (see _held_since -- a break restarts the clock).

        The rule's other half -- that the occupying units trace a line of supply of <=90 truck
        movement points back to a dump fed in any way from Tobruk or Tripoli -- is still
        DEFERRED (the truck-MP trace, C1-5). What stands in its place is the 64.73 quality-test
        (_occupier -> _supplied), a different line: the cpa/2 trace of 32.16.

        Rule 64.7 defines NO other automatic end: no annihilation, no concession. Failing this
        one clause the campaign runs its full span and is counted, per 64.73."""
        s = r.state
        held = all(self._occupier(s, ax) == Side.AXIS for ax in self.objective)
        since = self._held_since(r, held)
        if since is not None and _opstage(s) - since >= _STAGES_PER_TURN:
            return Side.AXIS, ("Axis auto-victory: Alexandria and Cairo held for one full "
                               "Game-Turn (64.71)")
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
