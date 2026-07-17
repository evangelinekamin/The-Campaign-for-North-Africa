"""Campaign victory conditions (rule 64.7) as a pluggable VictorySpec.

The full campaign is not won by taking one hex -- it is a five-year point tally. This
module implements the faithful CORE of rule 64.7:

  - 64.71: the Axis auto-wins by occupying every hex of Alexandria AND Cairo with a
    combat unit, holding them FOR ONE FULL GAME-TURN, with those occupying units tracing a
    line of supply of <=90 TRUCK Movement Points back to a Supply Dump that can in turn be
    supplied from Tobruk or Tripoli in any way.
  - 64.73: at the final turn, each side scores the Geographic Occupation Points of the
    cities its combat units hold (data/victory_cities.json).
  - 64.76: the two totals are graded as a ratio of most-to-least into Draw / Marginal /
    Decisive / Smashing.

Rule 64.7 has NO annihilation clause, and this module no longer invents one. A side with
no living unit left does not lose the campaign the instant its last counter dies: the war
runs to Game-Turn 111 and is settled on the 64.73 tally, exactly as the book has it. (The
engine's built-in Race-for-Tobruk spec, engine._victory, still carries the same invented
branch under rule 61.8, which likewise does not define it -- out of scope here.)

DEFERRED, documented so nothing is silently missing:
  - 64.72's Game-Turn-35 Commonwealth auto-win: no Axis Combat unit can trace <=60 truck-MP.
    The trace it needs is BUILT AND WIRED here (axis_traces_within at supply.TRUCK_MP_64_72);
    what stops it is the geography -- see THE TRIPOLI HOLE below, which must be closed FIRST or
    64.72 fires on a map artefact rather than on the rulebook.
  - 64.73's Stores/Water week-test and the in-hex "do you HAVE it" form of the occupation
    quality-test. The Fuel-for-20-CP and Ammunition-for-three-fires MAGNITUDES are faithful
    (CampaignVictory._supplied); the Stores/Water week and the in-hex form need the per-unit
    basic-load model (49.14 + 53.11, T1-1), so a holder is still tested by a reach-a-dump trace.
  - 64.74 unused-Replacement-Point VPs and 64.75 Commonwealth Withdrawal VPs.

🔴 THE TRIPOLI HOLE -- FLAGGED, AND IT IS A BLOCKER FOR 64.72, NOT FOR 64.71.

64.71 and 64.72 name TWO supply sources: Tobruk and Tripoli. This map has only Tobruk. Tripoli is
off-map (8.81: the Tripoli/Tunisia boxes sit on the western edge of Map A; 8.88 makes them Supply
Dumps of unlimited capacity), and the rulebook names its on-map gateway exactly once and exactly
once only -- 8.85: "For a unit to be moved off the game map towards Tripolitania it must start that
Operations Stage in hex A2802." That hex is one step from Nofilia (A2703) along the coast road, and
data/terrain_A.json transcribes it as SEA. So does A1816, El Agheila, which 61.43C names as a ROAD
hex. The coastline of the Gulf of Sirte is colour-sampled roughly one hex too far inland along that
stretch; game.scenario.campaign already patches the same class of defect where a piece stands on it
("coastal ports colour-sample as sea"), and A2802 has no piece on it. NOT FIXED HERE: the fix is to
the map transcription, and bending a hex into existence to make a victory rule fire is exactly the
invention this port is meant to stop. data/victory_cities.json records A2802 and the reason.

  * For 64.71 this is SAFE. Tripoli's absence can only ever make the Axis auto-win HARDER -- one of
    two sources is missing, so the trace is stricter than the book. It never fires spuriously.
  * For 64.72 IT IS NOT. 64.72 is the Commonwealth's automatic win for the COLLAPSE of Axis supply.
    With Tripoli missing, the Game-Turn the Commonwealth takes Tobruk the Axis has no source at all,
    every Axis unit fails the 60-MP trace, and the Commonwealth auto-wins at Game-Turn 35 -- off a
    coastline sampling error, in a war the historical Axis fought for two more years out of Tripoli.
    CLOSE THE HOLE BEFORE WIRING 64.72.
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from . import coords, supply, wells
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
        # 64.71/64.72's two named supply sources, "Tobruk or Tripoli" -- the harbours a Supply Dump
        # must be feedable from for the truck-MP line to be worth anything. A null is a source with
        # no hex on this map and is simply absent from the trace; today that is Tripoli, and the
        # module docstring says what that costs and what it does not.
        self.supply_sources = tuple(_ax(h) for h in data["supply_sources"].values() if h)

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
        this still asks 'can you REACH a dump that holds it?'.

        THIS IS 64.73's TEST AND ONLY 64.73's. It used to stand in for 64.71's <=90 truck-MP line as
        well, because that line was deferred; it no longer does (see check / _delta_held). 64.73
        writes its quality-test "for these purposes" -- the purposes being its own Geographic
        Occupation Point table -- and 64.71 asks a different question, in different units, over a
        different range."""
        return (supply.plan_draw(state, u, supply.FUEL, supply.fuel_cost(u, 20)) is not None
                and supply.plan_draw(state, u, supply.AMMO, 3 * supply.ammo_cost(u, phasing=True)) is not None)

    # --- [64.71]/[64.72] THE TRUCK-MOVEMENT-POINT LINE OF SUPPLY -------------------------------

    @staticmethod
    def _is_supply_dump(su) -> bool:
        """Is this counter a rule-64.71 SUPPLY DUMP? Every dump on the map is, except a 32.18
        DUMMY (a bluff counter with nothing in it) and a 52.1 well or pipeline.

        THE WELLS ARE THE LOAD-BEARING EXCLUSION, and they are not hypothetical. game.wells models
        a water source as a SupplyUnit -- a flagged proxy for geography -- and it seeds
        AX-Well-Alexandria ON Alexandria and five AX-Well-Cairo counters ON Cairo. Read as Supply
        Dumps they would hand every Delta occupier a nought-Movement-Point trace to a "dump" it is
        already standing on, and 64.71's whole supply clause would be satisfied by the geography of
        the objective itself. A well is a hole in the ground with water in it (52.11). No lorry from
        Tobruk ever filled one, so no well can "be supplied from Tobruk or Tripoli in any way", so no
        well is the Supply Dump this rule is asking for. The id-prefix idiom is game.wells's own, and
        game.campaign_claim.is_field_dump already draws the same line."""
        return not su.is_dummy and not wells.is_water_source(su)

    def fed_dumps(self, state, side: Side) -> frozenset:
        """The hexes of `side`'s Supply Dumps that "can in turn be supplied from Tobruk or Tripoli
        in any way" (64.71) -- the far end of every line of supply that can win or lose this war.

        NOT state.active_supplies, and the difference is the rule's own words. active_supplies is the
        DRAW list (what a unit may take supply FROM right now, 32.16) and it drops an EMPTY dump;
        64.71 asks for a dump that CAN BE SUPPLIED, which is a question about the road, not about
        the stock standing in the depot today. An empty depot at the end of an open road is exactly
        the supply line the rule means; a full one behind a cut road is not.

        Computed ONCE per victory check and passed down (axis_traces_within's `fed`): the flood is
        the same for every unit of the side, and 64.72 asks the question of every Axis combat unit
        on the map."""
        line = supply.truck_supply_line(state, side, self.supply_sources)
        return frozenset(su.hex for su in state.supplies
                         if su.side == side and self._is_supply_dump(su) and su.hex in line)

    def axis_traces_within(self, state, unit, budget: float,
                           fed: "frozenset | None" = None) -> bool:
        """THE RULE-64.71/64.72 PREDICATE: can `unit` trace a line of supply of `budget` TRUCK
        Movement Points or less back to a Supply Dump that can in turn be supplied from Tobruk or
        Tripoli in any way? `budget` is supply.TRUCK_MP_64_71 (90, the Axis auto-win) or
        supply.TRUCK_MP_64_72 (60, the Commonwealth's).

        Pass `fed` (from fed_dumps) when asking of many units in one check -- the dump-to-harbour
        flood does not depend on the unit and floods the whole map. Omitted, it is recomputed here,
        which is right for a one-off question and wasteful in a loop.

        64.72's "This does not include air or coastal shipping units" is honoured STRUCTURALLY, not
        by a filter: this engine's air is a game.state.AirWing and its ships are NavalUnits, neither
        of which is a Unit, so neither can ever reach `unit` at all. (Rule 3.23's own list of combat
        units -- Infantry, Tank, Recce, Artillery, Anti-tank, Anti-aircraft -- excludes both anyway;
        what 64.72's sentence closes is the looser glossary reading of "Combat Unit: any unit capable
        of engaging other units and/or aircraft in combat", under which a fighter squadron would
        qualify. FLAGGED as a reading: the sentence's head noun is "units", so it names the set of
        Axis units under test rather than restricting 64.71's "in any way" to exclude air transport
        and coastal shipping as MEANS. Under the other reading the dump-to-harbour leg would have to
        refuse those two means; this engine hauls supply by neither, so the two readings are
        indistinguishable here today, and 32.35 Axis Coastal Shipping is unbuilt.)"""
        fed = self.fed_dumps(state, Side.AXIS) if fed is None else fed
        if not fed:
            return False                              # no open source: nothing to trace to
        reach = supply.truck_trace_reach(state, unit, budget)
        return any(h in reach for h in fed)

    def _delta_occupiers(self, state, ax) -> tuple:
        """The Axis combat units OCCUPYING a Delta hex for 64.71 -- alive, combat, at Strength.

        64.71 does not define "occupies", and this is the definition the engine already settled on
        for the Delta (game.campaign_claim._occupied, which is what makes the Commonwealth garrison
        the seven hexes). It is NOT the 64.73 test: 64.73's Stores/Water/Fuel/Ammunition quality-test
        is written "for these purposes", the purposes being the Geographic Occupation Point table,
        and 64.71 asks its own supply question -- the <=90 truck-MP line -- instead. Before this port
        64.73's cpa/2 trace stood in for that line; it no longer has to."""
        return tuple(u for u in state.units_at(ax)
                     if u.side == Side.AXIS and u.is_combat and u.strength >= 1)

    def _delta_held(self, state) -> bool:
        """64.71's condition, whole: an Axis combat unit on EVERY hex of Alexandria and Cairo, each
        of them able to trace <=90 truck-MP to a Tobruk/Tripoli-fed dump.

        Per hex, SOME occupier must trace -- not all of them. That is 64.73's own construction two
        cases later ("Any units failing these tests do not occupy"): a unit that fails simply is not
        an occupier, and a stack-mate that passes still holds the hex. FLAGGED, because 64.71's
        "such occupying units can trace" is literally plural and a stricter reading is available.

        The bodies are counted first and the trace only if all seven hexes have one. That is the
        rule's own order ("If the Axis Player occupies all hexes ... AND such occupying units can
        trace"), and it is why the check costs nothing on the ~all game-turns where the Delta is
        Commonwealth."""
        occupiers = [self._delta_occupiers(state, ax) for ax in self.objective]
        if not all(occupiers):
            return False
        fed = self.fed_dumps(state, Side.AXIS)
        return all(any(self.axis_traces_within(state, u, supply.TRUCK_MP_64_71, fed) for u in us)
                   for us in occupiers)

    @staticmethod
    def _held_since(r: "_Run", held: bool) -> "int | None":
        """The 64.71 hold clock: the Operations Stage at which the Axis's CURRENT unbroken
        occupation of the Delta began, or None if the Delta is not held right now. Any break
        restarts it -- one hex retaken, or one holder's line of supply cut past 90 truck-MP, and
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
        """Rule 64.71, the Axis's outright win, WHOLE: every hex of Alexandria AND Cairo occupied,
        held FOR ONE FULL GAME-TURN, by units that can trace a line of supply of <=90 TRUCK
        Movement Points back to a Supply Dump which can in turn be supplied from Tobruk or Tripoli
        in any way -- regardless of the turn or date.

        Both halves are the rule's own, and each is the Commonwealth's answer to the other. The
        HOLD gives it a full Game-Turn of activations to throw the spearhead back out of one Delta
        hex, which denies the win rather than postponing it (_held_since -- a break restarts the
        clock). The LINE gives it the whole desert: Alexandria stands 138 truck-MP from Tobruk on
        this map, so the Axis cannot reach the Delta on its harbour's own trace -- it must push
        depots up the Via Balbia to within 90 of the Delta and keep the road behind them open, and
        one Commonwealth column across that road unwinds the win from four hundred miles away. That
        is the campaign the designer wrote: "the Axis had to take Alexandria (and the Delta)", and
        taking it is not the same as being able to stand in it.

        Before this port the <=90 line was DEFERRED and the 64.73 quality-test (_occupier ->
        _supplied, the cpa/2 trace of 32.16) stood in its place. It no longer does: 64.73's test
        belongs to 64.73's point table ("for these purposes"), and 64.71 asks its own question.

        Rule 64.7 defines NO other automatic end: no annihilation, no concession. Failing this
        one clause the campaign runs its full span and is counted, per 64.73."""
        s = r.state
        since = self._held_since(r, self._delta_held(s))
        if since is not None and _opstage(s) - since >= _STAGES_PER_TURN:
            return Side.AXIS, ("Axis auto-victory: Alexandria and Cairo held for one full "
                               "Game-Turn, supplied within 90 truck Movement Points (64.71)")
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
