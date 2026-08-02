"""Campaign victory conditions (rule 64.7) as a pluggable VictorySpec.

The full campaign is not won by taking one hex -- it is a five-year point tally. This
module implements the faithful CORE of rule 64.7:

  - 64.71: the Axis auto-wins by occupying every hex of Alexandria AND Cairo with a
    combat unit, holding them FOR ONE FULL GAME-TURN, with those occupying units tracing a
    line of supply of <=90 TRUCK Movement Points back to a Supply Dump that can in turn be
    supplied from Tobruk or Tripoli in any way.
  - 64.72: the COMMONWEALTH auto-wins from the first OpStage of Game-Turn 35 if no Axis combat
    unit can trace <=60 TRUCK Movement Points to a Supply Dump fed from Tobruk or Tripoli.
    The two auto-wins are mirrors: the Axis wins by ARRIVING on the end of a supply line, the
    Commonwealth by CUTTING one. This is the Commonwealth's PRINCIPAL win condition -- without it
    the campaign was settled on 64.73's geography alone, which is Axis-heavy by design (620 max
    against 370) because an Axis still holding Cyrenaica at the end is the "nothing happened"
    baseline. The Commonwealth's answer was never to out-point that table; it was this.
  - 64.73: at the final turn, each side scores the Geographic Occupation Points of the
    cities its combat units hold (data/victory_cities.json).
  - 64.76: the two totals are graded as a ratio of most-to-least into Draw / Marginal /
    Decisive / Smashing.

Rule 64.7 has NO annihilation clause, and this module no longer invents one. A side with
no living unit left does not lose the campaign the instant its last counter dies: the war
runs to Game-Turn 111 and is settled on the 64.73 tally, exactly as the book has it. (The
engine's built-in Race-for-Tobruk spec, engine._victory, still carries the same invented
branch under rule 61.8, which likewise does not define it -- out of scope here.)

64.74 and 64.75 -- the last two point categories -- ARE NOW SCORED (Block 7.3, decide()): 64.74 the
unused Replacement Points off the transcribed rule-20 charts less what the SPEND drew, 64.75 the
Commonwealth Withdrawal Points off the voluntary-withdrawal log. ONE thing about them stays open,
flagged at its method: 64.75-B's -2-on-return is dormant because no 20.9 return mechanism exists yet
(_withdrawal_points_64_75). 64.74's exclusion set is now book-faithful (planes/Trucks both sides,
Infantry CW-only): owner ruling 7 (2026-07-24, Eve) reverted the interim Axis-infantry proxy, and a
SPENDABLE-classes gate -- not an exclusion -- now withholds an unbuilt-spend class from scoring
(_unused_replacement_points_64_74).

64.73's OCCUPATION QUALITY-TEST IS NOW WHOLE AND IN-HEX (CampaignVictory._supplied). It was the
last abstract-game rule left standing in this module: it tested two of the rule's four commodities
and tested them through supply.plan_draw, the section-32.16 half-CPA trace that rule 3 of this port
says DOES NOT APPLY. It now asks 64.73's own question -- a Week of Stores and Water, three firings
of Ammunition and 20 CP of Fuel, HELD IN THE HEX. The in-hex form is TRANSCRIBED for three of the
four (49.15 Fuel / 50.15 Ammunition / 51.15 Stores) and INFERRED for Water, which section 52 gives
no in-hex clause of its own; the inference and its cost are argued at the method. TWO things inside
it are flagged rather than settled, both at the method: whether "fire its weapons three times" is
charged at the close-assault rate (as here), at the unit's dearest weapon's rate, or -- on [63.92]'s
gloss of the same construction -- at three firings of EACH function, which is 4.5x this bill; and
the FUEL clause, which is measured NON-DECISIVE on five campaign boards for a structural reason
that is written down there and pinned in tests/test_campaign_victory.py.

DEFERRED, documented so nothing is silently missing:
  - 64.74's used-subtraction bites only for AXIS infantry today (the [20.66] coupling + Block B flow-in
    + spend -- a real used>0). ALLIED tank/gun were scored by Block A's [20.78C] flow-in and REVERTED in
    its review-repair: the CW equipment spend is near-zero (gun is never even produced), so its ~865
    husbandry is unused-by-construction, and scoring it while the symmetric Axis equipment pool is
    unbuilt/unscored flipped the pinned campaign seed -- it returns with its Axis mirror (data key note).

THE TRIPOLI HOLE -- CLOSED 2026-07-16, WITH 64.72. The history is kept because the hole was a
BLOCKER for 64.72 and the record of why it was safe to close is the record of why 64.72 is faithful.

64.71 and 64.72 name TWO supply sources, Tobruk and Tripoli, and this map carried only Tobruk.
Tripoli is off-map (8.81: the Tripoli/Tunisia boxes sit on the western edge of Map A; 8.88 makes
them Supply Dumps of unlimited capacity), and the rulebook names its on-map gateway exactly once --
8.85: "For a unit to be moved off the game map towards Tripolitania it must start that Operations
Stage in hex A2802. A unit entering the game-map from the off-map region is simply placed in the
Road hex closest to the Tripolitania box." data/terrain_A.json colour-sampled A2802 as SEA: the
Gulf of Sirte coastline is sampled roughly one hex too far inland along that stretch.

WHAT THAT COST, MEASURED on the built campaign board, and it is why this had to be closed FIRST:
with Tobruk the only source, the Commonwealth CAPTURING Tobruk (56.15) took the Axis from 13 fed
dumps to 0 and every one of its combat units out of the 60-MP trace -- so wiring 64.72 would have
handed the Commonwealth an automatic win at Game-Turn 35 off a sampling error, in the exact
historical situation (Tobruk falls, January 1941) where the Axis fought on out of Tripoli for two
more years and retook Cyrenaica. That is not 64.72; it is "the Commonwealth wins if it holds
Tobruk", a rule the book does not contain. With the gateway restored the same board keeps its 13
fed dumps and 94 of its 96 tracing units when Tobruk falls, and 64.72 goes back to asking what it
actually asks: has Axis supply COLLAPSED?

(THE UNIT COUNTS WERE RESTATED 2026-07-16, and the restatement is a bug's epitaph, not a re-measure.
They read "all 177" and "94 of 177" because _axis_combat_units counted the FULL ROSTER -- including
81 units at GT1 that had not yet entered play. 64.72's set under test is the units on the GAME-MAP,
which at GT1 is 96. The fed-dump numbers are unaffected: they never depended on the unit set.)

THE FIX IS THE BOOK'S, NOT A BEND TO MAKE A VICTORY RULE FIRE, and that distinction is the whole
of it. 8.85 is a MOVEMENT rule that mentions no victory condition, and it states twice in one
breath that land units stand on A2802 -- a sea hex holds no Stacking Points and carries no road.
The override lives at the map layer (game.cna_map._RULEBOOK_LAND) because that is where this engine
already overrides the colour sample from independent evidence, twice: cna_map._load_edges from the
roads data ("a road runs on land, so any endpoint that colour-sampled as sea ... is added as
coastal CLEAR") and game.scenario._connect_pieces from the OOB ("a hex where a land unit stands is
land"). The rulebook is the third and strongest such source. A2802 is adjacent to A2801/A2702/A2703,
all already land, so the gateway joins the mainland with no bridging invented to reach it.

AND THE PROXY CARRIED A THIRD CATASTROPHE OF THE SAME FAMILY, CAUGHT BY A VERIFIER AND FIXED
2026-07-16. Hex A2802 stands proxy for the off-map boxes as a SOURCE -- and it was fed to the same
56.15 capture gate as Tobruk, which made an UNCAPTURABLE source capturable. The book's Tripoli
cannot be taken: it is off-map (8.81), and 8.82 says "No Commonwealth land or sea unit may ever
enter any of the boxes". A2802 is not Tripoli -- it is an ordinary desert road hex the Commonwealth
may walk onto, and walking onto it captures nothing. MEASURED on the built campaign board:
Control.ALLIED on BOTH C4807 and A2802 took fed_dumps from 13 to 0 and _line_is_cut to True -- i.e.
from GT35 one Commonwealth unit on one far-west hex, with Tobruk taken, ended the war outright with
every Axis combat unit alive and stocked. Precisely the class of defect this module refused to
ship as "the Commonwealth wins if it holds Tobruk", and precisely the class of the invented
adjacency gate supply.truck_supply_line had just been repaired to remove -- reintroduced one hex
west, with 56.15 cited for it a third time. The fix is the book's fact about the SOURCE
(supply.SupplySource.capturable): 56.15 is not switched off for Tripoli, its antecedent is
unsatisfiable. Re-measured after the repair, the same board keeps its 13 fed dumps and its line uncut.

THE COMMONWEALTH CAN STILL SHUT THE ROAD BY STANDING ON IT, which is the point: MEASURED, one
battalion on the gateway leaves all 13 dumps fed (10.11 exerts no ZOC below 2 Stacking Points) and
TWO take the Axis to 0 (10.29). That is a force holding a road under the book's own movement rule --
answerable by negation (10.26) or by driving it off -- where capture needed no force at all and no
Axis action could lift it. On the book's map that block would have to cover a road FRONTAGE
(8.85's 2802/2803/2804, plus El Agheila); the one-hex chokepoint is the map defect flagged below.

THE LESSON, THIRD TIME OF ASKING: a proxy may stand in for a hex; it may not inherit a rule the
thing it proxies is exempt from. The flag disclosed the geometry and stayed silent on the
behaviour -- and the behaviour was the bug. Both now live in data/victory_cities.json.

STILL OPEN, AND EVERY ONE OF THEM UNDERSTATES THE AXIS'S ROAD HOME rather than overstating it, so
each can only make 64.72 fire MORE readily than the book, never less:
  * A2803/A2804 (8.85's own "e.g., 5 points in hex 2802, 5 points in 2803, and 3 points in 2804")
    and A1816/El Agheila (61.43C names it a ROAD hex) are still sea. Tripoli therefore enters this
    map through a ONE-hex gateway where the book gives it a road -- a chokepoint of our making.
  * The gateway is CLEAR, not road: a road is an EDGE in this pipeline (data/roads_A.json), and
    seeding one would invent a road net the extraction does not carry.

A SECOND trigger of the same catastrophe lived IN THIS CODE and was fixed before it: supply's source
gate shut Tobruk for enemy ADJACENCY (an unnegated ZOC on the quay) while citing 56.15, which is a
rule about CAPTURE. Four Commonwealth units parked one hex from an Axis-held, empty Tobruk took
fed_dumps from 13 to 0 and every Axis unit out of the trace. See supply.truck_supply_line. The
lesson is why both notes stay: "the only thing stopping 64.72 is the geography" was FALSE when it
was written -- that hole was in the TRACE, not the map. A rule that hands one side the war on a
single predicate deserves both audits, and it got them.
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from . import coords, supply, wells
from .events import EventKind, Side

if TYPE_CHECKING:                       # avoid a runtime import cycle (engine owns _Run)
    from .engine import _Run

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "victory_cities.json")

# Rule 5.1 defines 64.71's unit of time in the book's own words: the Players "complete their
# operations within one Operations Stage, proceed to the second, and then the third, thus
# finishing ONE FULL GAME-TURN". So a full Game-Turn is three Operations Stages -- and since the
# engine tests victory in the Record Phase of every stage, it is three checks of elapsed time.
_STAGES_PER_TURN = 3

# 64.72: "Starting with the first OpStage of Game-Turn 35". The engine checks victory in the Record
# Phase of every Operations Stage, so the rule is live from the first check of Game-Turn 35 onward
# -- turn >= 35, at any stage. No end: it is asked again every stage for the rest of the war.
_AUTO_WIN_TURN_64_72 = 35

# [64.73]'s occupation quality-test, in the rule's own units: a holder must have "enough Fuel and
# Ammunition to fire its weapons three times and move 20 CP's" (and a Week of Stores and Water --
# see _supplied, where the Week is converted). Both numbers are the book's, printed in that
# sentence; neither is a proxy.
_FIRINGS_64_73 = 3
_CP_64_73 = 20

# 64.75-A Commonwealth Withdrawal Points: "1/2 point for each week that unit is gone, to a maximum
# of three points per unit." WEEK = one Game-Turn (owner ruling 4, scratchpad/port/PHASE-7-OWNER-
# RULINGS.md), so a battalion gone six-or-more Game-Turns caps at three points.
_WITHDRAWAL_VP_PER_WEEK = 0.5
_WITHDRAWAL_VP_MAX_PER_UNIT = 3.0


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
        # must be feedable from for the truck-MP line to be worth anything. Each carries the book's
        # fact about WHAT KIND of source it is (supply.SupplySource.capturable): Tobruk is an on-map
        # port 56.15 can shut, Tripoli an off-map box 8.82 puts permanently beyond Commonwealth
        # reach. A null hex is a source this map does not carry and is simply absent from the trace.
        self.supply_sources = tuple(
            supply.SupplySource(hex=_ax(src["hex"]), capturable=src["capturable"])
            for src in data["supply_sources"].values() if src["hex"])

    def _occupier(self, state, ax) -> "Side | None":
        """The side holding a hex for victory purposes: a SUPPLIED combat unit of at least 1
        TOE Strength there (rule 64.73). Non-combat units (truck convoys, bare HQs) and supply
        dumps do not occupy; nor does a unit that has OUTRUN its supply -- 64.73's occupation
        quality-test is that a holder HAS, in the hex, a Week of Stores and Water and the Fuel and
        Ammunition to fire three times and move 20 CP (_supplied), so a stranded spearhead on a city
        scores nothing. This is what makes the campaign a logistical contest and not a
        foot-race: the Axis must keep its advance supplied to bank the ground it takes."""
        for u in state.units_at(ax):
            if u.is_combat and u.strength >= 1 and self._supplied(state, u):
                return u.side
        return None

    @staticmethod
    def _supplied(state, u) -> bool:
        """[64.73]'s occupation quality-test, WHOLE and asked the way the rule asks it. Verbatim off
        the scan (PDF p.88 = book folio 37; the misspelt "conditons" is the book's own):

            "Occupation for these purposes means having a combat unit of at least 1 TOE Strength in
             the hex. That combat unit, at the end of the game, must have enough Stores and Water for
             one Week, and enough Fuel and Ammunition to fire its weapons three times and move
             20 CP's. Any units failing these "tests" do not occupy for victory conditons."

        FOUR commodities, and the verb is HAVE. Both halves of that sentence had been read short:

          * IT NAMED FOUR AND THIS TESTED TWO. Stores and Water -- the two the rule puts FIRST --
            were not asked at all, so a garrison with no rations and no water banked its city.
          * IT ASKS THE HEX AND THIS ASKED A TRACE. Every draw ran through supply.plan_draw, which
            is the SECTION 32.16 half-CPA supply range -- the ABSTRACT game, which 64.6 hands to the
            Players who are NOT running the Air and/or Logistics Games (it names 32.0, 47.0 and 58.0
            in as many words). We run the full game, in which there is no supply RANGE at all:
            supply is in the hex or it is not (49.15 / 50.15 / 51.15, transcribed at
            supply.in_hex_draw). Rule 3 of this port calls an abstract-game rule in force a BUG
            CLASS, not a shortcut, and this was one more of them.

            THAT CITATION COVERS THREE OF THE FOUR COMMODITIES, AND THE FOURTH IS AN INFERENCE --
            flagged here per rule 1 of this port rather than left to look like a transcription.
            49.15, 50.15 and 51.15 are the in-hex clauses for Fuel, Ammunition and Stores. Section
            52 has no counterpart: read whole on the scan (folio 21, 52.0 through 52.52, and 52.53
            on folio 22) it prints no "in the same hex" clause for Water at all. Its nearest support
            is [52.13], "To obtain water, a unit moves into a hex with a well" -- a MOVEMENT
            instruction, from which the in-hex FORM follows only by analogy with the other three.
            The analogy is a strong one (water is the least portable of the four and the book gives
            it no trace of its own), but it is an inference, and the WATER note below measures what
            it costs today: nothing.

        Each magnitude comes off its own rule, and the WEEK is converted at the two different rates
        the book prints, which is the one arithmetic judgement here:

          FUEL    supply.fuel_cost(u, 20) -- 49.13's rate x ceil(CP/5) x TOE Strength; a foot unit
                  walks and burns none (49.12), so "move 20 CP's" costs it nothing.
          AMMO    three firings x supply.ammo_cost (50.14).
          STORES  supply.stores_cost, which is ALREADY a per-Game-Turn rate (51.11's 4 per TOE),
                  taken once -- because 5.1 says "In CNA each Game-Turn covers a period of
                  approximately one week", so 64.73's Week IS a Game-Turn.
          WATER   supply.water_cost, a per-OPERATIONS-STAGE rate (52.4), taken _STAGES_PER_TURN
                  times -- the same Week, counted in the units 5.1 divides it into. [29.35] doubles
                  the requirement in hot weather, and engine._draw_stage_water reads the same
                  supply.water_cost(hot=...), so the doubling is the war's own. IT IS NOT A PARITY
                  WITH THE WAR'S BILL, and this line used to say it was ("the holder is tested on
                  the water the war actually charged it"). For INFANTRY the two do agree stage for
                  stage: [52.41] carries no condition and engine._water_distribution draws its flat
                  Point at the top of every Operations Stage. For a VEHICLE they diverge, because
                  [52.42] bills only "if it uses any of its CPA" (the clause corrected at HEAD
                  49b00f2) -- so a stationary vehicle garrison is charged NOTHING for the week and
                  this predicate still asks it for three stages' worth. THE DIVERGENCE IS THE
                  FAITHFUL SIDE: 64.73 says the holder "must have" the Week, which is a test of
                  STOCK, not of consumption, and a garrison that sat still all week is exactly the
                  one the rule means to ask. Inert today either way (every 64.73 city carries a
                  well, see the WATER note below), so stating it correctly costs nothing.

        FLAGGED, A READING NOT CHANGED HERE: "fire its weapons three times" is charged at
        supply.ammo_cost's default close-assault rate. A unit whose real weapon is a barrage fires at
        a DEARER rate (50.2: barrage 4, anti-armor 3, close-assault 2), and supply.ammo_capacity
        already computes "one firing of this unit's most demanding function" for exactly that reason.

        AND THE CEILING IS DEARER THAN THAT, on evidence printed on the same scanned page. [63.92]
        (PDF p.88 col. 1, the "Long Retreat" scenario) glosses the identical construction. Verbatim,
        off a 300-dpi render of that column, the emphasis below being this comment's and not the
        book's:

            "Occupying means that all combat units in that City/Village must have at least one
             Game-Turn's worth of Stores, be able to fire all weapons twice, and have enough fuel
             for all units to move 20 CP's."

        ALL WEAPONS, TWICE. Read 64.73's sentence the way its own author reads it two columns away
        and "fire its weapons three
        times" means three firings of EACH combat function the unit has -- so a battalion with a
        barrage, an anti-armor and a close-assault function owes 3 x (4 + 3 + 2) x TOE where this
        code charges 3 x 2 x TOE: FOUR AND A HALF times the shipped bill, not the two times the
        dearest-weapon reading gives. (63.92 also independently corroborates the STORES conversion
        above: "one Game-Turn's worth" is 64.73's "one Week" in the units 5.1 divides it into.)
        Left as it stands because it is a MAGNITUDE question and this was a FORM slice, and moving
        both at once makes the A/B unreadable. UNMEASURED, deliberately; when the magnitude slice is
        taken, 63.92 is the citation it turns on and the range it must A/B is 1x to 4.5x.

        WATER, AND WHY THIS DOES NOT RE-OPEN THE S8 FINDING -- read this before touching either.
        THIS IS THE VICTORY-SCORING PREDICATE, NOT THE SUPPLY LAYER. game.engine's per-stage water
        draw (_water_distribution) deliberately stays on the 32.16 trace: measured, the naive in-hex
        form gave 60% thirst against the campaign's faithful 12%, because the [52.45] water-truck
        reservoir is unbuilt (nothing ever fills Unit.water) and 52.0's General Rule says in
        substance that thirst is a nuisance rather than a killer -- verbatim, off a 300-dpi render of
        folio 21: "Players should find that they rarely run out of water, but that it is a nuisance
        as it is absolutely necessary." (This line used to print water "rarely runs out" INSIDE
        quotation marks, which is not a string the book contains -- the verb is "run" and the subject
        is the Players. The correct form was already in the tree at engine.py:3544; the wrong one was
        copied from its twin at engine.py:2273 and both are now the book's.)
        That trace is the honest proxy for a tier this engine has not built, and it is UNCHANGED.
        This predicate can ask the in-hex question anyway, and the reason is a measured fact about
        64.73's own geography rather than an opinion: every one of the ten cities in
        data/victory_cities.json carries a game.wells water source for BOTH sides, so the Week of
        Water is satisfiable in the hex at every hex this rule is ever asked about. MEASURED over six
        campaign boards (seeds 3/4/7/30/1941/2026 at max_turns=12): of the 103 combat units standing
        on a 64.73 city, the in-hex and trace readings of the Water clause agreed on ALL 103 -- zero
        disagreements. Away from the cities they differ on 24-44 units a board, which is what
        observation.can_hold sees when it asks this predicate of a unit in open desert; there the
        in-hex answer is the rule's ("no water here, no holding ground here") and the unbuilt 52.45
        is the reason it is stricter than the book would be. When 52.45 lands, this line does not
        change -- the supply layer's does.

        FUEL IS NON-DECISIVE TOO, AND FOR A DIFFERENT AND STRUCTURAL REASON -- recorded because an
        untested clause in a scoring predicate is how a scoreboard drifts without anyone noticing,
        and because leaving only the Water clause's inertness written down read as if Water were the
        one unmeasured commodity. NEUTERED AT ITS OWN CALL SITE (this tuple's FUEL row rewritten to
        `(supply.FUEL, 0)`), all four campaign signatures and all four 64.73 geography tallies are
        BYTE-IDENTICAL: 1941 d4fa0bd90ffc ax375/cw0, 7 d107a13ab6de ax375/cw0, 4 9d1ce03d1b95
        ax375/cw0, 2026 5b5e5c38bc6a ax275/cw10 (scenario.campaign's own max_turns=12 kwarg, the
        recipe in tests/baselines.py). MEASURED per clause on five boards -- CAMPAIGN_SEED=23 at
        GT30 plus those four -- of every combat unit of >=1 TOE standing on a 64.73 city, TWO fail
        Fuel on each board and NOT ONE fails Fuel and nothing else. Both are the same pair, the
        Giarabub oasis garrison's artillery and AA battalions, and both fail Ammunition as well.

        THE REASON IS ARITHMETIC, NOT LUCK, WHICH IS WHY IT IS SAFE TO LEAVE UNGUARDED-BY-CHANCE AND
        WHY IT IS NOW PINNED ANYWAY (tests/test_campaign_victory.py: the Fuel magnitude and the
        49.14 ceiling each have their own case, and the four-commodity loop asks a MOTORISED holder
        as well as a foot one -- every holder in that file used to be FOOT, which is why neutering
        this row left the whole suite green). Three facts compose:

          * 49.12 gives a FOOT unit no Fuel Consumption Rate, so its 20-CP bill is ZERO and the
            clause is vacuous. Sixteen city-slots are banked across these five boards, by twenty-two
            qualifying garrisons, and exactly ONE of the twenty-two is not foot: seed 4's Mersa
            Matruh, the Italian II(M) medium tank battalion, which stands on the railhead depot and
            draws 2,273 Fuel Points against a bill of 32.
          * [49.14]'s Note gives a unit "a fuel capacity rating exactly sufficient to allow all its
            CPA to be expended on movement" -- supply.fuel_capacity(u) == fuel_cost(u, u.cpa). 64.73
            asks for a FIXED 20 CP, so a BRIM-FULL tank covers the clause only from cpa 16 up
            (49.13 charges ceil(CP/5) five-CP blocks). The two Giarabub failures are cpa-15
            battalions holding full tanks: 18 of 24 Points and 12 of 16.
          * Off a co-located dump, STORES and AMMUNITION fail FIRST. Neither has an organic pool of
            the kind [49.14] gives Fuel: what Stores a counter holds is its [53.11] first-line truck
            buffer, which the war spends, and [50.0]'s basic load is ONE firing against 64.73's
            three. MEASURED at CAMPAIGN_SEED/GT30 -- counters holding a WEEK of Stores: 20 of 67
            Commonwealth, 0 of 57 Italian, 0 of 17 German; counters holding THREE firings: 24 / 10 /
            1. So Fuel can be the SOLE failure only where a dump holds a Week of Stores, three
            firings and a Week of Water but less than 20 CP of Fuel -- a fuel-specific shortfall in a
            dump that is otherwise stocked. Nothing on these five boards is in that state.

        It will bite the day a dump runs dry of Fuel alone under a motorised garrison, and the
        clause is charged, tested and left in force against that day. (Away from the cities it
        already bites: exactly one unit fails Fuel alone at seed 23 and one at seed 4, none on the
        other three -- 2-Armd-Div-Cruiser-Regt-I on Alexandria's well with 45 Points of an 80-Point
        tank against a 64-Point bill, and BR-8-Fld on Dekheila's with 18 of 24. That is what
        observation.can_hold reports to the staff layer, and nothing the scoreboard reads.)

        THIS IS 64.73's TEST AND ONLY 64.73's. It used to stand in for 64.71's <=90 truck-MP line as
        well, because that line was deferred; it no longer does (see check / _delta_held). 64.73
        writes its quality-test "for these purposes" -- the purposes being its own Geographic
        Occupation Point table -- and 64.71 asks a different question, in different units, over a
        different range.

        ONE POLICY SITE STILL READS IT AND ONE STOPPED. game.campaign_claim._banking asks it of the
        live board to know which city each side already banks -- that IS this question, it stays, and
        it is the reason a scoring rule moves the campaign's determinism signature at all (measured:
        reverting _banking alone reproduces the pre-change log byte for byte, tests/baselines.py).
        campaign_claim's take-and-hold GATE used to ask it too, of a unit as if it already stood on
        an empty city, and that is a question about a board the plan has not built yet: it now has
        its own predicate (campaign_claim.could_be_fed), because the faithful in-hex form answers
        "no" to every city the plan was going to open and takes the army off the board along with the
        points. The rule is not softened anywhere; the planner is named for what it is."""
        need = ((supply.FUEL, supply.fuel_cost(u, _CP_64_73)),
                (supply.AMMO, _FIRINGS_64_73 * supply.ammo_cost(u, phasing=True)),
                (supply.STORES, supply.stores_cost(u)),
                (supply.WATER, _STAGES_PER_TURN * supply.water_cost(
                    u, hot=state.weather == "hot")))
        return all(supply.in_hex_draw(state, u, c, qty) is not None for c, qty in need)

    # --- [64.71]/[64.72] THE TRUCK-MOVEMENT-POINT LINE OF SUPPLY -------------------------------

    @staticmethod
    def _is_supply_dump(su) -> bool:
        """Is this counter a rule-64.71 SUPPLY DUMP? Every dump on the map is, except a 32.18
        DUMMY (a bluff counter with nothing in it), a 52.1 well or pipeline, and a 36.17 air-facility
        dump.

        THE AIR DUMP IS EXCLUDED BY THE SAME ARGUMENT AS THE WELL, word for word. 64.71 asks whether
        an ARMY has a line of supply -- "within 90 Truck Movement Points of a supply dump which can in
        turn be supplied from Tobruk or Tripoli in any way". 36.17 forbids the army to draw a single
        Point from an airfield's pile ("LAND UNITS MAY NOT USE AIRFIELD SUPPLY DUMPS"), so no air dump
        is the Supply Dump this rule is asking for: a division that traced 90 Truck Movement Points to
        a landing strip's larder would arrive at supplies it may not touch. Phase 5.1 put eleven such
        piles on the campaign map and the [60.5] transcription put fourteen -- RE-MEASURED at seed
        4's set-up on the book's air map: the Axis has 13 fed_dumps hexes and 5 air-facility dumps
        standing inside the same flood, the Commonwealth 10 and 9. So counting them would still add
        half again to both sides' supply-dump count and quietly widen 64.71 (the Axis auto-win) and
        64.72 (the Commonwealth instant-win). (The forty-two this used to say was measured before
        the air allotment was placed to the words of its own chart: [60.34] restricts the Axis pool
        to AIRFIELDS, and both pools now follow the squadrons rather than spreading over every
        facility on the map -- see oob.air_dumps. Fewer piles, none of them stranded.)

        THE WELLS ARE THE LOAD-BEARING EXCLUSION, and they are not hypothetical. game.wells models
        a water source as a SupplyUnit -- a flagged proxy for geography -- and it seeds
        AX-Well-Alexandria ON Alexandria and five AX-Well-Cairo counters ON Cairo. Read as Supply
        Dumps they would hand every Delta occupier a nought-Movement-Point trace to a "dump" it is
        already standing on, and 64.71's whole supply clause would be satisfied by the geography of
        the objective itself. A well is a hole in the ground with water in it (52.11). No lorry from
        Tobruk ever filled one, so no well can "be supplied from Tobruk or Tripoli in any way", so no
        well is the Supply Dump this rule is asking for. The id-prefix idiom is game.wells's own, and
        game.campaign_claim.is_field_dump already draws the same line."""
        return not su.is_dummy and not su.air_dump and not wells.is_water_source(su)

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
        by a filter: this engine's air is a game.state.AirWing, its warships are NavalUnits and its
        [56.3] coastal fleet is a game.state.CoastalShip, none of which is a Unit, so none can ever
        reach `unit` at all. (Rule 3.23's own list of combat
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
        tracing = supply.tracing_hexes(state, Side.AXIS,
                                       {u.hex for us in occupiers for u in us},
                                       fed, supply.TRUCK_MP_64_71)
        return all(any(u.hex in tracing for u in us) for us in occupiers)

    # --- [64.72] THE COMMONWEALTH'S AUTOMATIC WIN ----------------------------------------------

    @staticmethod
    def _axis_combat_units(state) -> tuple:
        """64.72's set under test: "there are no Axis Combat units that can trace...".

        ON THE GAME-MAP -- state.living, which is state.units filtered by state.on_map (alive AND
        turn >= arrival_turn, rule 20). That is the rule's OWN qualifier, restored to the quote in
        check(): 64.72 reads "...to Tobruk or Tripoli as per case 64.71, GAME-MAP, the Commonwealth
        wins the game automatically". The word sits oddly and it is load-bearing -- it names WHICH
        Axis combat units are under test, and the reading taken here is the natural one: those ON
        the game-map, excluding the units that legitimately sit OFF it (8.81/8.83/8.84 -- the Axis
        reinforcement pipeline runs through the off-map Tripoli/Tunisia boxes). FLAGGED as a reading.

        THIS READ state.units -- THE FULL ROSTER -- AND IT DENIED THE COMMONWEALTH ITS WIN. The
        `strength >= 1` filter satisfies on_map's `alive` half but NOT its reinforcement half, so
        Axis units that had NOT YET ENTERED PLAY -- pre-placed at their scheduled entry hexes -- were
        counted as "Axis Combat units that can trace", and supply has no arrival_turn awareness
        anywhere, so truck_trace_reach traced happily from an unarrived unit's entry hex. MEASURED
        end to end on game.scenario.campaign() at GT35, and it is 64.72's OWN scenario (the Axis
        collapsed back onto Tripolitania): the board carries 31 Axis combat units with arrival_turn
        > 35 parked at A1616/A1617, ~20 hexes from the A2802 Tripoli gateway. Put an Axis dump on the
        gateway, take every ARRIVED Axis combat unit off the map, and the Axis has ZERO combat units
        in play -- yet all 31 ghosts traced <=60 to the fed dump, _line_is_cut was False, and 64.72
        did not fire. The off-map reinforcement queue was a permanent trace anchor precisely where
        the rule is meant to bite: an Axis driven back onto Tripolitania keeps its dumps near the
        gateway, which is where the unarrived units wait. With on_map applied the tracing count is 0
        and the Commonwealth wins, as 64.72 requires.

        THE FAILURE RAN THE UNSAFE WAY, which is why it outranked its size: every other open gap in
        this block can only make 64.72 fire MORE readily than the book. This one made the
        Commonwealth's PRINCIPAL win condition fire LESS readily -- a victory silently denied, the
        exact failure the block was written to avoid.

        Combat units at Strength, which is the definition _delta_occupiers already settled on for
        64.71 and which 64.73 writes out longhand ("a combat unit of at least 1 TOE Strength"). It
        excludes the truck convoys and bare HQs (is_combat False) that 3.23's own list of combat
        units -- Infantry, Tank, Recce, Artillery, Anti-tank, Anti-aircraft -- excludes anyway.

        "THIS DOES NOT INCLUDE AIR OR COASTAL SHIPPING UNITS" is honoured STRUCTURALLY rather than
        by a filter, and there is nothing to filter: this engine's air is a game.state.AirWing, its
        warships are NavalUnits and its [56.3] coastal fleet is a game.state.CoastalShip -- none of
        them a Unit, so none of them ever in state.units (verified: the built campaign's units are
        all Unit, state.naval is empty, and state.ships is its own field). What that
        sentence closes is the looser glossary reading of "Combat Unit" -- "any unit capable of
        engaging other units and/or aircraft in combat" -- under which a fighter squadron would
        qualify and a single airborne fighter could deny the Commonwealth its win. See
        axis_traces_within for the second reading of the same sentence and why the two are
        indistinguishable on this engine today."""
        return tuple(u for u in state.living(Side.AXIS) if u.is_combat and u.strength >= 1)

    def _line_is_cut(self, state) -> bool:
        """64.72's condition: NO Axis combat unit can trace a line of supply of 60 truck Movement
        Points or less to a Supply Dump that can in turn be fed from Tobruk or Tripoli.

        fed_dumps is computed ONCE, and the per-unit trace is INVERTED into a single flood:
        supply.tracing_hexes seeds one reversed-edge Dijkstra from the fed dumps and returns which of
        the Axis combat units' hexes settled within 60 truck-MP, in place of a forward 60-MP Dijkstra
        per unit (see there for the multi-source inversion and its blocked-start exemption). When the
        Axis has no fed dump at all it returns the empty set without walking the map, and the line is
        cut iff that set is empty. So the check is cheap in both of the cases it spends its life in.

        FLAGGED, A READING, AND IT IS VACUOUS TRUTH: with no Axis combat units left on the map at
        all, "there are no Axis Combat units that can trace" is satisfied trivially and the
        Commonwealth wins. That is the sentence's plain meaning and it is NOT the invented
        annihilation clause this module deleted -- it fires only from Game-Turn 35, on 64.72's own
        authority, where the invention fired on any turn on none. The two readings (plain, versus
        "the rule presumes an Axis army and asks about its supply") agree on the winner in every
        case but one: both sides annihilated, where the plain reading gives the Commonwealth the war
        and the 64.73 tally would give a 0-0 Draw.

        AND THE VACUOUS CASE NOW REACHES ONE BOARD IT DID NOT: an Axis whose ON-MAP army is gone at
        GT35+ with reinforcements still queued for a later turn loses, where before the unarrived
        counters held the war open from their entry hexes. That is not the fix over-reaching -- it is
        64.72's own "game-map" qualifier doing exactly what it says (_axis_combat_units), and the
        alternative was a rule that could never fire while the Axis had a single counter left in the
        box. FLAGGED because it is a reading of one oddly-placed word, and it is the reading that
        makes the rule mean something."""
        fed = self.fed_dumps(state, Side.AXIS)
        tracing = supply.tracing_hexes(state, Side.AXIS,
                                       {u.hex for u in self._axis_combat_units(state)},
                                       fed, supply.TRUCK_MP_64_72)
        return not tracing

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

        Both halves are the rule's own. The HOLD gives the Commonwealth a full Game-Turn of
        activations to throw the spearhead back out of one Delta hex, which denies the win rather
        than postponing it (_held_since -- a break restarts the clock).

        WHAT THE LINE IS WORTH IS NOT YET KNOWN, AND THE FIRST CUT OF THIS PORT SAID OTHERWISE. It
        shipped "Alexandria stands 138 truck-MP from Tobruk on this map, so the Axis cannot reach
        the Delta on its harbour's own trace -- it must push depots up the Via Balbia to within 90
        of the Delta". Its NUMBER reproduces and almost nothing else about it does. Corrected here
        rather than quietly deleted, because it was measured, published, and believed:

          * IT MEASURES A LEG THE RULE DOES NOT MEASURE, so the "so" is a non-sequitur. 64.71 never
            asks the unit's distance to the HARBOUR. It caps unit -> DUMP at 90 and then declines to
            measure dump -> harbour at all ("in any way"). Tobruk -> Alexandria really is 138.5
            truck-MP (with the GT1 trace blocking; 122.5 bare) -- it is simply not a distance 64.71
            has an opinion about.
          * THE DEPOTS ARE ALREADY THERE, so "it must push depots up the Via Balbia" is false where
            it is checkable. MEASURED on game.scenario.campaign() at GT1: the Axis's forward setup
            dump AX-Dump#4 (24,86) -- unmoved, Tobruk-fed, one of 13 -- stands 88.5 truck-MP from
            Alexandria (27,133). INSIDE the 90 the rule prints. Nothing needs pushing up the road to
            put Alexandria in supply; it was in supply on turn one.
          * WHAT ACTUALLY DENIES THE WIN AT GT1 IS CAIRO: 124.5-125.0 truck-MP from that same dump,
            some 35 MP outside the 90. 64.71 wants ALL SEVEN hexes of BOTH cities, so the rule does
            not fire today -- but on the second objective, not the one that was published, and by a
            margin nobody measured.
          * AND THE NUMBERS THEMSELVES ARE ~2-3x TOO DEAR, because the map's road net is a fragment
            of the book's (supply.TRUCK_MP_64_71 carries the measurement and the rule cites). On a
            faithfully transcribed Via Balbia the Delta may well sit inside 90 of the setup dumps
            outright, and 64.71's supply clause may cost the Axis nothing at all.

        So: the 90 is the book's and the trace is wired, but WHETHER THIS CLAUSE BITES IS AN OPEN
        QUESTION GATED ON THE ROAD NET, and no claim that it does should be made until that map job
        lands. Today the hold is the clause with teeth. That the designer meant the supply line to
        have them -- "the Axis had to take Alexandria (and the Delta)", and taking it is not the
        same as being able to stand in it -- is a reason to transcribe the roads, not a licence to
        report an untranscribed map's arithmetic as the rule's intent.

        Before this port the <=90 line was DEFERRED and the 64.73 quality-test (_occupier ->
        _supplied, the cpa/2 trace of 32.16) stood in its place. It no longer does: 64.73's test
        belongs to 64.73's point table ("for these purposes"), and 64.71 asks its own question.

        AND RULE 64.72, THE COMMONWEALTH'S OUTRIGHT WIN -- the mirror of it, and the Commonwealth's
        PRINCIPAL instrument: "Starting with the first OpStage of Game-Turn 35, if there are no Axis
        Combat units that can trace a line of supply of 60 Movement Points (Truck) to a Supply Dump
        and thence to Tobruk or Tripoli as per case 64.71, game-map, the Commonwealth wins the game
        automatically. This does not include air or coastal shipping units."

        "GAME-MAP" IS THE BOOK'S WORD AND THIS QUOTE HAD DELETED IT -- under a label saying verbatim,
        in the one docstring the next reader will trust. Caught by a verifier and checked against the
        SCAN (PDF page 88 / printed page 37), which reads "...as per case 64.71, game-map, the Com-
        monwealth wins the game automatically"; docs/rules/64's OCR carries it correctly, so the word
        was lost here and nowhere else. Restored, with the reading flagged rather than the word
        removed. It is load-bearing: it qualifies WHICH Axis combat units are under test, and
        _axis_combat_units takes the natural reading -- the ones ON the game-map, not the ones
        legitimately sitting in the off-map Tripoli/Tunisia boxes (8.81/8.83/8.84).

        The Axis wins by ARRIVING in the Delta on the end of a supply line; the
        Commonwealth wins by CUTTING one. Until this landed, the Commonwealth had no outright win at
        all and the campaign was scored on the 64.73 geography table alone -- which is Axis-heavy by
        design (620 max against 370), because an Axis still holding Cyrenaica at the end is the
        "nothing happened" baseline. The Commonwealth's answer was never to out-point the Axis on
        geography. It was this.

        NO HOLD CLOCK, and the asymmetry is the rule's own: 64.71 says "for one full Game-Turn" and
        64.72 says "Starting with the first OpStage of Game-Turn 35" and nothing more, so the
        Commonwealth's win lands on the first check that finds the line cut. 64.71's hold exists
        because ground can be retaken in a Game-Turn; 64.72 asks about a supply line that is already
        gone.

        ORDER, FLAGGED AS A READING: 64.71 is tested first. The two can in principle both hold --
        an Axis Delta garrison tracing <=90 but not <=60, with no other Axis unit inside 60 -- and
        the book does not say which governs. 64.71 is taken to, on its own words: it wins
        "regardless of the turn or date", where 64.72 is gated on one; and it is the earlier case.
        The board that satisfies both is pathological (an Axis army standing in Alexandria and Cairo
        has not suffered the supply collapse 64.72 describes).

        Rule 64.7 defines NO other automatic end: no annihilation, no concession. Failing these two
        clauses the campaign runs its full span and is counted, per 64.73."""
        s = r.state
        since = self._held_since(r, self._delta_held(s))
        if since is not None and _opstage(s) - since >= _STAGES_PER_TURN:
            return Side.AXIS, ("Axis auto-victory: Alexandria and Cairo held for one full "
                               "Game-Turn, supplied within 90 truck Movement Points (64.71)")
        if s.turn >= _AUTO_WIN_TURN_64_72 and self._line_is_cut(s):
            return Side.ALLIED, ("Commonwealth auto-victory: from Game-Turn 35 no Axis combat unit "
                                 "can trace 60 truck Movement Points to a Supply Dump fed from "
                                 "Tobruk or Tripoli (64.72)")
        return None, ""

    def decide(self, r: "_Run") -> tuple["Side | None", str]:
        """The 64.73-64.76 POINT TALLY -- reached only when neither 64.71 nor 64.72 fired (the engine
        calls decide() at the final turn, after check() returned no winner), which is 64.73's own
        opener "failing the above two cases". Three categories of points are totalled and then graded:

          - 64.73 Geographic Occupation Points: each side scores the cities its supplied combat units
            hold (self.cities / _occupier).
          - 64.75 Commonwealth Withdrawal Points (Commonwealth only).
          - 64.74 unused Replacement-Point Victory Points (both sides).

        THE ORDER IS 64.75 THEN 64.74, on the plan's instruction (00-THE-PORT-PLAN.md:1556) and this
        Block 7.3 task: 64.74 scores what is left UNUSED, and a voluntary 64.75 withdrawal is one of
        the things that leaves a unit's Replacement Points unspent. 64.74 today scores only the AXIS
        unused infantry (the [20.66] spend draws that pool); the Block A CW tank/gun scoring was REVERTED
        in its review-repair (premature -- see _unused_replacement_points_64_74). So the 64.75<->64.74
        data-flow is again DORMANT: a voluntarily-withdrawn CW armour/gun battalion is one fewer unit for
        the [20.78C] flow-in to heal and so leaves marginally more tank/gun unused, but CW tank/gun no
        longer SCORE, so that husbandry never reaches the tally. When CW equipment scoring returns (with
        its Axis mirror) this second-order flow returns with it. 64.76 compares the totals as a ratio."""
        s = r.state
        axis_vp = cwlth_vp = 0
        for ax, avp, cvp, _name in self.cities:                       # 64.73
            side = self._occupier(s, ax)
            if side == Side.AXIS:
                axis_vp += avp
            elif side == Side.ALLIED:
                cwlth_vp += cvp
        cwlth_vp += self._withdrawal_points_64_75(r)                  # 64.75 (Commonwealth only)
        axis_74, cwlth_74 = self._unused_replacement_points_64_74(r)  # 64.74 (both sides)
        return grade(axis_vp + axis_74, cwlth_vp + cwlth_74)

    def breakdown(self, r: "_Run") -> dict:
        """READ-ONLY: decide()'s tally, ITEMISED -- the same three 64.7 point categories per side,
        plus which side holds each 64.73 city. Added for the Gate-C measurement harness
        (scripts/gate_c.py), which needs to know WHICH condition moved a campaign's score and not
        merely the total. It is a projection, like a 64.73 tally read off the final board: the engine
        never calls it, it emits no event, it decides nothing, and it moves no determinism signature.

        `r` is the run decide() is handed -- or any read-only VIEW of one exposing `.state` and
        `.events`, e.g. SimpleNamespace(state=result.final, events=result.events). That view is
        exactly what decide() saw: engine.run calls decide() in the final Record Phase and emits
        nothing afterwards, so r.state there IS RunResult.final.

        IT DUPLICATES decide()'s 64.73 CITY LOOP, WHICH IS A DRIFT RISK, and the caller is required
        to close it: grade(b["total"]["AXIS"], b["total"]["ALLIED"]) must reproduce the run's own
        reason string VERBATIM whenever the campaign was settled by 64.76. scripts/gate_c.py asserts
        that per seed and records `breakdown_agrees`; a disagreement means this accessor is wrong --
        decide() is the scoreboard, never this. (On a board settled by the 64.71 or 64.72 auto-win
        the tally is still computed and still reportable, but it did not decide the war, so no
        agreement is asserted there.)"""
        s = r.state
        cities = []
        geo = {Side.AXIS.value: 0, Side.ALLIED.value: 0}
        for ax, avp, cvp, name in self.cities:                         # 64.73
            side = self._occupier(s, ax)
            if side == Side.AXIS:
                geo[Side.AXIS.value] += avp
            elif side == Side.ALLIED:
                geo[Side.ALLIED.value] += cvp
            cities.append({"name": name, "hex": list(ax), "axis_vp": avp, "cwlth_vp": cvp,
                           "holder": None if side is None else side.value})
        withdrawal = self._withdrawal_points_64_75(r)                  # 64.75 (Commonwealth only)
        axis_74, cwlth_74 = self._unused_replacement_points_64_74(r)   # 64.74 (both sides)
        return {
            "cities": cities,
            "geographic_64_73": dict(geo),
            "withdrawal_64_75": {Side.AXIS.value: 0, Side.ALLIED.value: withdrawal},
            "replacement_64_74": {Side.AXIS.value: axis_74, Side.ALLIED.value: cwlth_74},
            "total": {Side.AXIS.value: geo[Side.AXIS.value] + axis_74,
                      Side.ALLIED.value: geo[Side.ALLIED.value] + withdrawal + cwlth_74},
        }

    def _withdrawal_points_64_75(self, r: "_Run") -> float:
        """[64.75] Commonwealth WITHDRAWAL POINTS -- the Commonwealth's only non-geographic Victory
        Point source, and the counterweight to 64.74. 64.75-A pays HALF a point for each WEEK (owner
        ruling 4: one Game-Turn) that a VOLUNTARILY-withdrawn combat battalion of infantry, armour,
        artillery or anti-tank -- NOT AA -- is gone, to a maximum of three points per unit. It is
        summed from the UNIT_WITHDRAWN log (a read-only projection of the run, like a 64.73 tally --
        it re-enters no event stream).

        WHAT IS EXCLUDED, per the rule's own words:
          - MANDATORY withdrawals ([4.43a], voluntary False): "These are voluntary withdrawals, not
            mandatory withdrawals" -- the formations History sent to Greece/Crete/Syria do not score.
          - AA: 64.75-A lists "infantry, armour, artillery or anti-tank guns (not AA)", and those four
            arms are every combat arm EXCEPT anti-aircraft (rule 3.23), so the one filter is to drop
            an anti-aircraft counter (organization.replacement_kind == 'anti_air').
          - non-Commonwealth: "apply solely to the Commonwealth Player" -- honoured structurally (the
            engine's 'withdraw' order rejects a non-Allied voluntary withdrawal, engine._organization)
            and re-checked here (u.side).

        WHAT THE ACT ALREADY GUARANTEES, and this scoring therefore trusts: the 'withdraw' order path
        rejects a company, a unit below 75% TOE Strength, and one not in Alexandria/Cairo (64.75-A's
        other conditions). They CANNOT be re-verified here -- a withdrawn counter has steps=() (its
        strength gone) -- so the eligibility that survives withdrawal (its type, for the AA filter) is
        read off the still-intact Unit, and the rest is the act's contract.

        WEEKS GONE = final_turn - withdrawal_turn (FLAGGED, a fencepost judgement call): a unit
        withdrawn DURING Game-Turn T was present at the start of T, so it is counted absent for the
        whole Game-Turns after it (T+1..F), i.e. F - T weeks -- a last-turn withdrawal scores zero.
        The alternative (F - T + 1, counting the withdrawal week) differs by one week / half a point,
        and only below the three-point cap (a withdrawal in the final ~six turns); the cap makes it
        moot for every earlier one.

        64.75-B DORMANT, and deliberately not coded (no speculative branch): "every time a battalion
        withdrawn under A is returned to the game, the Commonwealth loses two points", and the
        gone-clock would stop at the return. NOTHING returns a voluntarily-withdrawn counter in this
        engine -- withdrawal empties its steps, the (Rtn) reinforcements are the MANDATORY returns
        under different ids, and no order re-raises a voluntary one -- so the -2 has no trigger and no
        withdrawal's clock is ever stopped early. When a 20.9 return mechanism is built, this is where
        the -2 and the clock-stop attach."""
        from . import organization                                   # local: replacements imports us
        final_turn = r.state.turn
        total = 0.0
        for e in r.events:
            if e.kind is not EventKind.UNIT_WITHDRAWN or not e.payload.get("voluntary"):
                continue
            u = r.state.unit(e.payload["unit_id"])
            if u is None or u.side != Side.ALLIED:                    # 64.75: Commonwealth only
                continue
            if organization.replacement_kind(u) == "anti_air":       # 64.75-A "(not AA)"
                continue
            weeks_gone = max(0, final_turn - e.payload["turn"])
            total += min(_WITHDRAWAL_VP_MAX_PER_UNIT, _WITHDRAWAL_VP_PER_WEEK * weeks_gone)
        return total

    def _unused_replacement_points_64_74(self, r: "_Run") -> tuple[int, int]:
        """[64.74] REPLACEMENT VICTORY POINTS -- one point per UNUSED Replacement Point allotted in a
        Player's Production Charts (unused = the charts' campaign total MINUS what the SPEND has drawn
        from the pool), excluding planes and Trucks for both and Infantry per the data key's flag.
        Returns (axis_vp, commonwealth_vp). The magnitudes and the exclusion set are the transcribed
        charts' (game.replacements); this method only measures USED off the UNIT_REBUILT log and hands
        it down.

        GATED ON GameState.replacement_production -- the rule-20 economy being in play. 64.74 scores
        "Replacement Points allotted ... in his Production Charts", so a scenario that runs no
        Production system (every non-campaign board -- the benchmark specs use their own VictorySpec,
        and the hand-built victory tests construct this one on synthetic boards) has none allotted and
        scores none. This is the rule's genuine precondition and the SAME boundary the flow-in already
        uses (engine._replacement_production), not a campaign-gate to dodge a signature -- decide()
        emits no event and moves no determinism signature at all. The live campaign sets the flag, so
        64.74 always fires there.

        SCORES ONLY SPENDABLE CLASSES (owner ruling 2026-07-24, Eve). A class scores its unused count
        only if the engine can actually SPEND it (replacements.replacement_vp_spendable_classes); a class
        with no rebuild beat is 100% unused by construction, which is an unmodelled spend, not the
        husbandry 64.74 rewards, and scoring it produced a fixed Axis+893 / CW+958 constant that
        compressed every grade toward 1:1 (the Gate 7A artifact). As of Block B (2026-07-25) two classes
        are spendable: the Commonwealth infantry rebuild (itself book-excluded, so it never scores) and
        the [20.66] Axis infantry rebuild the Block B flow-in + [20.62] coupling now feed -- which is NOT
        book-excluded, so the Axis scores his unused infantry husbandry (~13 of the 1,600-pool in the
        seed-1941 war, allotted minus the ~1,587 the spend drew). Block A (2026-07-25) added ALLIED
        'tank'/'gun' (the [20.78C] flow-in + spend), then REVERTED them in its review-repair: the CW
        equipment spend is near-zero (gun is never even produced), so the ~865 husbandry is unused-BY-
        CONSTRUCTION -- the used==0 artifact this ruling forbids -- and scoring the CW half of the book's
        SYMMETRIC equipment rule while the Axis half is unbuilt/unscored flipped the pinned CAMPAIGN_SEED
        from an Axis Smashing Victory to a Commonwealth one (MEASURED; the book-faithful symmetric score
        keeps the Axis ahead 1283-985). So the Commonwealth scores 0 replacement VP today; its equipment
        returns with its Axis mirror (data/replacements.json spendable_classes REVERTED note). The
        permanent exclusion set (replacements.replacement_vp_excluded_classes) is now book-faithful: the
        earlier proxy that also dropped Axis infantry was reverted with this ruling -- the spendable
        gate, not an exclusion, is what keeps an unbuilt-spend class from scoring."""
        if not r.state.replacement_production:
            return 0, 0
        from . import replacements
        used: dict = {}
        for e in r.events:
            if e.kind is not EventKind.UNIT_REBUILT:
                continue
            pool_key, cost = e.payload.get("pool_key"), e.payload.get("cost", 0)
            if pool_key and cost:
                side_v, cls = pool_key.split("/", 1)
                used[(side_v, cls)] = used.get((side_v, cls), 0) + cost
        return (replacements.unused_replacement_vp(Side.AXIS, used),
                replacements.unused_replacement_vp(Side.ALLIED, used))


def _fmt(v) -> "int | float":
    """Render a Victory-Point total for the reason string: an int (or whole-valued float, e.g. the
    4.0 two capped withdrawals make) as an int, a genuine half-point (64.75-A pays in halves) as
    itself. Keeps '200-0' reading '200-0' while '958 + 4.5' reads '962.5'."""
    return int(v) if float(v).is_integer() else v


def grade(axis_vp, cwlth_vp) -> tuple["Side | None", str]:
    """Rule 64.76: compare the totals as a ratio of most-to-least. Even is a Draw;
    otherwise better-than-1:1 up to 1.5:1 is Marginal, up to 2.5:1 Decisive, beyond
    Smashing. A shutout (loser at 0) is a Smashing Victory. Totals may carry a 64.75-A half-point,
    so they are numbers, not necessarily ints."""
    if axis_vp == cwlth_vp:
        return None, f"Draw at {_fmt(axis_vp)}-{_fmt(cwlth_vp)} Victory Points (64.76)"
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
    return winner, f"{name} {level}: {_fmt(axis_vp)}-{_fmt(cwlth_vp)} Victory Points (64.76)"
