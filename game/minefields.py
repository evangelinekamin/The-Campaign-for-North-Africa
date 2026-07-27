"""Rule 26.0 MINEFIELDS -- their existence, movement cost and combat effect.

Loads data/minefields.json (mirrors game.cp_costs / game.logistics_data: a thin, cached reader
so the magnitudes are the rulebook's, not literals scattered through game/*.py) and supplies the
pure functions game.movement / game.tactics / game.engine hook rule 26's effects through:

  26.21/26.22  entry_surcharge   -- the CP a mover pays ON TOP of ordinary terrain cost to enter
                                    a minefield hex, keyed off Friendly/Enemy from the MOVER's own
                                    side (the TEC's two minefield rows are one belt, read two ways).
  26.24/[6.3]  entry_surcharge   -- the Engineer-escort cells. [6.3] CAPABILITY POINT EXPENDITURE
                                    SUMMARY (PDF p.96) prints all seven minefield-entry cells and
                                    is the arbiter: escorted into an Enemy belt is 2 non-Mot / 4
                                    Mot, escorted into a Friendly belt is 0. 23.21's 6/3 is the
                                    outlier no chart carries and is NOT implemented.
  26.25        destroys          -- the vehicle-destruction die a mover not so escorted rolls
                                    entering an Enemy REAL minefield (a dummy rolls nothing).
  26.26/n.13   defender_shift    -- the L1 Anti-Armor / L1 Close-Assault the DEFENDER receives
                                    when a belt HE laid stands on the assaulted hex or on any hex
                                    the assault comes from.
  26.13/26.14/ minefield reveal/clearing predicates -- state transitions the engine applies as
  26.15/26.23  MINEFIELD_REVEALED / MINEFIELD_CLEARED events (game.engine._movement).

The magnitudes of the two combat cells live beside the rest of the [8.37] combat-shift chart in
game.combat_tables (MINEFIELD_AA_SHIFT / MINEFIELD_CA_SHIFT), matching how every other 8.37 combat
cell in this engine is transcribed as an inline Python constant rather than a JSON lookup; this
module owns the PREDICATE that decides when they apply (defender_shift), which is the half the
chart's note 13 actually governs. data/minefields.json documents both cells for provenance.

Breakdown Points for a minefield hexside are read straight out of data/breakdown_rates.json
(terrain_breakdown_values_8_37.hexside.friendly_minefield / .enemy_minefield), the same file every
other [8.37] Breakdown Value comes from -- once, at import, so nothing JSON-loads in the accrual.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from .hexmap import Coord
from .state import GameState, Minefield
from .terrain import Mobility, is_motorized

_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "minefields.json"))


@lru_cache(maxsize=1)
def _data() -> dict:
    with open(_PATH) as f:
        return json.load(f)


# --- [23.0] THE THREE (AND A HALF) KINDS OF ENGINEER -----------------------------------------------
#
# 23.0: "There are three types of Engineer units: Engineer Battalions, Engineer companies, and
# Headquarters Units with Engineer capability." The Construction Chart's key names them EBn / ECoy
# / HQ-with-Engineering, and distinguishes CHQ-E (an ALLIED HQ with engineering) from HQ-E (any
# HQ with engineering) row by row. Unit.engineer carries which of them a counter is:
#
#   'ENGINEER'      an Engineer battalion or company (EBn / ECoy)
#   'HQ_ENGINEER'   23.14's HQ with "a letter E next to their Stacking Points"
#   'SCORPION'      23.15's two refitted CW tank battalions -- engineers for ANTI-MINEFIELD
#                   PURPOSES ONLY, and only while they hold 6+ TOE of Scorpions
#   'RAIL' / 'ROAD' the NZRRC companies and the 1 SA Road Construction Bn, which 23.13 says are
#                   "used SOLELY for the construction and repair of Railroads" / "solely for Road
#                   work" (24.61: "may be used only for RR work"). They are NOT general engineers:
#                   they neither escort a mover through a belt nor clear one.
GENERAL_ENGINEER: str = 'ENGINEER'
HQ_ENGINEER: str = 'HQ_ENGINEER'
SCORPION: str = 'SCORPION'

SCORPION_MIN_TOE: int = _data()["scorpion"]["min_toe"]


def is_scorpion_engineer(u) -> bool:
    """[23.15]: a Scorpion battalion "is considered to possess engineer unit status WHILE IT
    CONTAINS AT LEAST SIX Scorpion TOE Strength Points". Read against effective_strength (21.44:
    a broken-down flail cannot flail), the same operational-TOE reading every other combat/ZOC
    test in this engine takes."""
    return u.engineer == SCORPION and u.effective_strength >= SCORPION_MIN_TOE


def is_engineer_counter(u) -> bool:
    """Is `u` an ENGINEER COUNTER in the sense of [23.11] -- the Case that says "Engineer counters
    have no real combat value, nor do they exert Zones of Control. They are NOT COMBAT UNITS IN ANY
    WAY, SHAPE, OR FORM. Engineer units may never enter Enemy-controlled hexes voluntarily"?

    That is 23.0's three kinds (EBn, ECoy, HQ-with-Engineering) plus 23.13's two rail/road
    engineering companies -- every `engineer` value EXCEPT 'SCORPION'.

    A 23.15 Scorpion battalion is NOT one. It is a Commonwealth TANK battalion (42/44 RTR, 8 TOE of
    flail tanks, is_combat=True) that "possesses engineer unit status" strictly "for ANTI-MINEFIELD
    capabilities" -- the exact clause game.minefields' own SCORPION docstring and
    data/minefields.json's _capabilities key both record. 23.11 is written about counters with no
    combat value; reading it onto a flail battalion would forbid the one unit in the Commonwealth
    order of battle whose entire purpose is to breach INTO an enemy position at El Alamein."""
    return bool(u.engineer) and u.engineer != SCORPION


def is_engineer(u) -> bool:
    """Does `u` carry the ANTI-MINEFIELD engineer capability rule 26 asks for -- 26.13/24.38's
    clearing, 26.24's escort discount, 26.25's exemption?

    Any general Engineering unit (EBn, ECoy, HQ-with-Engineering of either side) plus a 23.15
    Scorpion battalion at 6+ TOE. NOT 'RAIL'/'ROAD': 23.13 restricts those two counters to their
    one named job ("used solely for..."), and 24.61 repeats it ("may be used only for RR work"),
    so they are engineers for railway/road construction and for nothing else.

    FLAGGED, the one place the book disagrees with itself about WHO: [6.3] says "with an Eng unit"
    and 23.21 says "any Engineer unit (or HQ unit with Engineering capability)", while 26.24/26.25
    say "an Engineer battalion or Commonwealth HQs with Engineering capacity" -- excluding engineer
    COMPANIES and Axis HQ-Engineering. This engine takes the chart's + 23.21's breadth (see
    data/minefields.json's _escort_who_source)."""
    return u.engineer in (GENERAL_ENGINEER, HQ_ENGINEER) or is_scorpion_engineer(u)


def engineer_present(state: GameState, coord: Coord, side) -> bool:
    """[26.24]: does ANY friendly Engineer-capable unit currently stand at `coord`, stacked with
    the mover? Evaluated at the mover's OWN hex before the step (game.tactics builds the extra-
    cost closure once per move from the phase-start board), matching how every other escort/
    negation check in this engine (10.26 ZOC negation, e.g.) reads a snapshot rather than
    re-simulating stack composition hex by hex along a multi-hex path."""
    return any(is_engineer(u) for u in state.units_at(coord) if u.side == side)


# --- [26.2] EFFECTS OF MINEFIELDS ----------------------------------------------------------------

def entry_surcharge(state: GameState, mover_side, mobility: Mobility, cpa: int,
                    origin: Coord, dst: Coord) -> float:
    """[26.21]/[26.22]/[26.24]/[6.3] The CP `dst`'s minefield (if any) adds ON TOP of the ordinary
    terrain entry cost movement.step_cost already charges ("+ TEC" in every cell of [6.3]). 0.0 if
    `dst` carries no minefield.

    The seven cells, verbatim off [6.3] (PDF p.96, scan-verified):

        Friendly belt, any unit with an Eng unit ......... 0
        Friendly belt, non-motorized, no Eng unit ........ 1
        Friendly belt, motorized, no Eng unit ............ 4
        Enemy belt, non-motorized WITH an Eng unit ....... 2
        Enemy belt, motorized WITH an Eng unit ........... 4
        Enemy belt, non-motorized, no Eng unit ........... 4
        Enemy belt, motorized, no Eng unit ............... the mover's whole CPA

    The last is 26.21's own worked example ("an artillery unit would expend 15 Capability Points
    to enter an Enemy minefield"). The escorted cells REPLACE the unescorted cost, they do not
    stack with it (26.24: "rather than their listed cost")."""
    mf = state.minefields.get(dst)
    if mf is None:
        return 0.0
    d = _data()["entry_cp"]
    mot = is_motorized(mobility)
    escorted = engineer_present(state, origin, mover_side)
    if mf.side == mover_side:                            # Friendly Minefield row
        if escorted:
            return float(d["friendly"]["escorted"])
        return float(d["friendly"]["mot" if mot else "non_mot"])
    # Enemy Minefield row
    if escorted:
        return float(d["enemy"]["escorted_mot" if mot else "escorted_non_mot"])
    if mot:
        return float(cpa)
    return float(d["enemy"]["non_mot"])


def _hexside_bv(key: str) -> float:
    """The [8.37] Breakdown Value of one minefield hexside row, out of the file every other 8.37
    Breakdown Value in this engine comes from (data/breakdown_rates.json). Read once, at import."""
    with open(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data",
                                            "breakdown_rates.json"))) as f:
        return float(json.load(f)["terrain_breakdown_values_8_37"]["hexside"][key])


# [8.37] Friendly Minefield BV = 0 (no extra risk), Enemy Minefield BV = +2 -- ADDED to the hex's
# ordinary terrain BV (26.22: "in addition to the terrain in the hex"), exactly as
# movement.breakdown_points already adds a hexside's own BV.
FRIENDLY_MINEFIELD_BV: float = _hexside_bv("friendly_minefield")
ENEMY_MINEFIELD_BV: float = _hexside_bv("enemy_minefield")


def breakdown_surcharge(state: GameState, mover_side, dst: Coord) -> float:
    """[8.37]/26.22: the Breakdown Points `dst`'s minefield (if any) adds on top of the hex's
    ordinary terrain BV. Friendly is the chart's own 0 cell, so a Friendly belt costs nothing."""
    mf = state.minefields.get(dst)
    if mf is None:
        return 0.0
    return FRIENDLY_MINEFIELD_BV if mf.side == mover_side else ENEMY_MINEFIELD_BV


MINE_DESTROY_ROLLS: frozenset = frozenset(_data()["destruction_roll"]["hit_on"])


def destroys(die: int) -> bool:
    """[26.25]: does this one d6 (rolled per battalion-sized-or-smaller vehicle unit, or once for
    all 2nd/3rd-line trucks, entering an unescorted Enemy REAL minefield) destroy a TOE Strength
    Point / Truck Point? "If the Player rolls a 5 or 6..." """
    return die in MINE_DESTROY_ROLLS


def rolls_destruction(belt: Minefield, mover_side, mobility: Mobility, escorted: bool) -> bool:
    """[26.25] Does entering `belt` put a 26.25 die in the mover's hand at all? Only a vehicle
    ("whenever a VEHICLE (tank, truck, etc.) enters"), only an ENEMY belt, only unescorted by an
    Engineer -- and only a REAL one. A dummy belt has no mines in it: 26.11 makes real-vs-dummy
    the whole distinction of rule 26, and 26.23's "the only difference" clause is scoped to the
    COST of entry, not to the destruction of vehicles."""
    return (belt.real and belt.side != mover_side and is_motorized(mobility) and not escorted)


# --- [26.26] + [8.37] note 13: THE DEFENDER'S COLUMN ----------------------------------------------

def defender_shift(state: GameState, defender_side, target: Coord, attacker_hexes) -> bool:
    """[26.26]/[8.37] note 13: does the DEFENDER of `target` get his one column for the mines?

    The shift turns on the belt being the DEFENDER'S OWN, and it is granted by either of two
    situations the book states twice over:

      * the defender is "occupying a Friendly minefield" -- his own belt lies on the hex being
        assaulted ([8.37]'s Friendly Minefield row: L1 Anti-Armor, L1 Close Assault; 26.26's
        "a Close Assault against an Enemy unit in an Enemy Minefield", read from the attacker);
      * "if ASSAULTING forces are in an Enemy minefield" (note 13) / "the attacking units are in
        an Enemy minefield" (26.26) -- the defender's belt lies under the attackers, who are
        wading through it to get at him. THIS is the Devil's Gardens case.

    A belt the ATTACKER laid grants nothing at all: that is [8.37]'s Enemy Minefield row, whose
    Anti-Armor and Close Assault cells both print "-".

    One column, never two: note 13's grant is explicitly "IF NOT ALREADY RECEIVING them for
    occupying a Friendly minefield", so this is a boolean, not a count."""
    if not state.minefields:
        return False
    belt = state.minefields.get(tuple(target))
    if belt is not None and belt.side == defender_side:
        return True
    return any(b is not None and b.side == defender_side
               for b in (state.minefields.get(tuple(h)) for h in attacker_hexes))


# --- [24.3] CONSTRUCTING MINEFIELDS: the magnitudes (game.construction owns the BuildOrder flow) -

REAL_STORES: int = _data()["construction"]["real"]["stores"]
REAL_AMMO: int = _data()["construction"]["real"]["ammo"]
DUMMY_STORES: int = _data()["construction"]["dummy"]["stores"]
DUMMY_AMMO: int = _data()["construction"]["dummy"]["ammo"]
MINEFIELD_OP_STAGES: int = _data()["construction"]["real"]["op_stages"]      # 1, both kinds (24.32)
MINEFIELD_TERRAIN: frozenset = frozenset(_data()["construction"]["terrain_allowed"])

# --- [24.4] CONSTRUCTING FORTIFICATIONS: the magnitudes ------------------------------------------

FORT_STORES: int = _data()["fortification"]["stores"]
FORT_OP_STAGES: int = _data()["fortification"]["op_stages"]
FORT_FIELD_CAP: int = _data()["fortification"]["field_cap"]
FORT_EXCLUDED_TERRAIN: frozenset = frozenset(_data()["fortification"]["terrain_excluded"])
