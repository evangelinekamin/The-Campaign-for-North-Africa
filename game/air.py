"""[36.0] AIR FACILITIES and [35.0] SQUADRON GROUND SUPPORT UNITS -- the ground the air game
stands on.

Everything the Air Game does, it does FROM somewhere and THROUGH somebody. Rule 36 is the
somewhere and rule 35 is the somebody, and until this module existed neither was on the map:
`game.state.AirWing` is a hexless pool of Air Points, so a bombing campaign had no base to fly
from, no base to bomb, and no way to run out of anything.

  [36.0] "Air facilities include airfields, air landing strips, flying boat basins and flying
    boat alighting areas. These facilities are differentiated by the TYPE and NUMBER of planes
    they can handle in terms of flight and maintenance... Air facilities may be damaged and/or
    destroyed by Enemy bombardment. The number of SGSU's and airplanes which can use an air
    facility is dependent upon its current CAPACITY LEVEL."

  [35.0] "Squadrons -- specifically the SGSU's -- are used to MAINTAIN AND SUPPLY the aircraft
    assigned to them... The SGSU counters are considered vehicles (medium trucks) and have their
    own Capability Point Allowance printed on the counter. They have no combat values."

THE THREE LOAD-BEARING FACTS, and each one is a lever the campaign has never had:

  * **CAPACITY IS A LEVEL, AND BOMBS TAKE IT DOWN** (36.14). "If bombing has reduced the capacity
    of an airfield from six to three, that airfield may handle only three squadrons at a time,
    until it is built back up to six... If an airfield is reduced to zero capacity, it is
    considered destroyed for all purposes." 41.36 says what a bombing mission produces: "the
    result is the NUMBER OF CAPACITY LEVELS that facility is reduced." This is the mechanism by
    which the Axis suppresses Malta (44.21) -- Phase 5.4 consumes it.

  * **AN AIRFIELD IS A SUPPLY DUMP** (36.17). "An airfield is a supply dump for supplies to be
    used by the SGSU's on that airfield. Fuel, ammunition, stores, etc., may be stored at an
    airfield as if it were a dump. LAND UNITS MAY NOT USE AIRFIELD SUPPLY DUMPS unless it is an
    emergency." So the air-facility dump is a real `SupplyUnit` standing in the facility's hex,
    flagged `air_dump` -- visible to an SGSU's in-hex draw and INVISIBLE to the land army's.
    38.24's "fuel is subtracted from the air facility's dump" (Phase 5.2) reads this same pile.

  * **WITHOUT AN SGSU THERE IS NO REFIT** (35.14 / 35.17). "Each SGSU must expend one Stores
    Point per Game-Turn. In addition, each SGSU requires one Fuel Point and one Water Point per
    Operations Stage. SGSUs WITHOUT THE REQUIRED SUPPLIES (for themselves) MAY NOT REPAIR THEIR
    PLANES" (35.14); "SGSUs are necessary to refuel and refit airplanes; ONLY SGSUs can perform
    such tasks" (35.17). That is the sortie-rate governor the Refit Table (Phase 5.3) hangs on,
    and `may_refit` below is the gate it reads.

WHAT IS DELIBERATELY NOT HERE (5.1 is the ground floor, not the building): 35.17's +1 foreign-base
refit die, 35.2 squadron composition/capacities, 24.7 air-facility CONSTRUCTION (the rebuild LAW is
here; no order routes to it yet), 36.5 off-map facilities, 36.18's intrinsic 1 AA point, and the
44.5 Malta construction table. Each is named in the port plan under 5.2-5.5.
"""
from __future__ import annotations

from .events import Control, Side
from .state import AirFacility, GameState, Unit

# --- [36.1]-[36.4] THE FOUR KINDS, AND THE ONE NUMBER THAT DISTINGUISHES THEM ------------------
# "These facilities are differentiated by the type and number of planes they can handle" (36.0),
# and every difference below is the rulebook's own sentence:
#   36.12  "Each Airfield has a capacity level of six (maximum). This means that it may handle a
#           maximum of six squadrons (regardless of squadron size) at any one time."
#   36.2   air landing strips are "treated exactly as airfields except that each air landing strip
#           has a maximum squadron capacity of ONE."
#   36.3   flying boat basins have "the same features as an airfield, with the exception that their
#           Capacity is THREE Squadrons."
#   36.4   "Alighting Areas are the same as flying boat basins, except that they have a capacity of
#           ONE Squadron and they are immune to artillery barrage."
AIRFIELD = "airfield"
STRIP = "strip"
BASIN = "basin"
ALIGHTING = "alighting"

MAX_CAPACITY: dict[str, int] = {AIRFIELD: 6, STRIP: 1, BASIN: 3, ALIGHTING: 1}

# [36.12] "There may never be more than six SGSU's in a given airfield hex" -- and 36.14 keeps that
# ceiling even on a battered field: "regardless of the capacity of an airfield, each airfield may
# still have six SGSU's with it, even though some may not be able to FUNCTION because of a reduced
# capacity level." So the six is a STACKING limit on the counters and the LEVEL is a functioning
# limit; they are two different numbers and this is the first.
SGSU_HEX_LIMIT = 6

# [35.14] The SGSU's own upkeep, verbatim: "Each SGSU must expend ONE STORES POINT PER GAME-TURN.
# In addition, each SGSU requires ONE FUEL POINT and ONE WATER POINT PER OPERATIONS STAGE."
SGSU_STORES_PER_TURN = 1
SGSU_FUEL_PER_STAGE = 1
SGSU_WATER_PER_STAGE = 1

# The `role` an SGSU counter is built under (game.oob), carried as its single StepRecord label --
# the same idiom every other role uses. An SGSU is NOT an air unit ("SGSU's are the mechanics,
# trucks, equipment, etc... They are not 'air' units", 35.11) and it is not a land combat unit
# either (35.12: no combat strength of any type, no Stacking Point Value).
SGSU_ROLE = "sgsu"


def is_sgsu(unit: Unit) -> bool:
    """[35.11] Is this counter a Squadron Ground Support Unit? Keyed on the built role, exactly as
    every other role test in the engine is. An SGSU is exempt from the rule-51/52 LAND Stores/Water
    demand -- its upkeep is 35.14's, drawn from its facility's own dump (36.17) -- so this predicate
    is what the land logistics beat skips on and what the 35.14 beat selects on."""
    return bool(unit.steps) and unit.steps[0].label == SGSU_ROLE


def max_capacity(kind: str) -> int:
    """The kind's charted maximum Capacity Level (36.12 / 36.2 / 36.3 / 36.4)."""
    return MAX_CAPACITY[kind]


def destroyed(facility: AirFacility) -> bool:
    """[36.14] "If an airfield is reduced to zero capacity, it is considered DESTROYED for all
    purposes." True of every kind: a strip/basin/alighting area has only the one level to lose."""
    return facility.level <= 0


def removed_when_destroyed(kind: str) -> bool:
    """[36.2] / [24.76] Does a destroyed facility come OFF the map, or stay on it to be rebuilt?

    The two rules agree and they draw the line by kind. 36.2 on landing strips: "If that capacity
    level is destroyed, the strip is ELIMINATED AND REMOVED FROM THE GAME-MAP." 24.76 generalises
    it and names the exception: "Air landing strips, and flying boat facilities (both) MUST BE
    BUILT FROM SCRATCH if destroyed. AIRFIELDS ARE REBUILT CAPACITY LEVEL BY CAPACITY LEVEL (see
    Air Rules, Case 36.12)... Only one Level may be rebuilt at a time."

    So an airfield is a wounded installation and everything else is a binary."""
    return kind != AIRFIELD


def rebuilt_level(facility: AirFacility) -> "int | None":
    """[24.76] The Capacity Level `facility` stands at after ONE completed rebuild step, or None if
    it may not be rebuilt in place. "Airfields are rebuilt Capacity Level by Capacity Level... ONLY
    ONE LEVEL MAY BE REBUILT AT A TIME", and the cost of one level "is the same as it costs to build
    an air landing strip" (24.75's Construction Chart -- the cost side is 24.7 and is deferred).

    A strip / basin / alighting area at zero is no longer on the map to rebuild (36.2), and no
    facility is ever rebuilt past its charted ceiling (36.12's "six (maximum)")."""
    if facility.level >= facility.max_level:
        return None                                    # 36.12: six is the maximum, full stop
    if destroyed(facility) and removed_when_destroyed(facility.kind):
        return None                                    # 24.76: built from scratch, not rebuilt
    return facility.level + 1


def facility_at(state: GameState, hex_) -> "AirFacility | None":
    """The air facility standing on `hex_`, or None. One per hex (a facility is an installation,
    not a counter a player may stack), so the first by id is the answer and the scan is stable."""
    return next((f for f in sorted(state.air_facilities, key=lambda f: f.id) if f.hex == hex_), None)


def holder(state: GameState, facility: AirFacility) -> Side:
    """[36.15] / [60.5] WHO OWNS AN AIR FACILITY: whoever holds the ground it stands on.

        "Land combat units may CAPTURE or destroy (entirely) an airfield by occupying its hex.
         Airfields are, in essence, NON-DENOMINATIONAL; they may be used by anyone." (36.15)
        "Players will note that Air facilities may be used by anyone WHO CONTROLS THEM." (60.5)

    So the holder is derived, never stored and never transferred by an event -- the exact idiom a
    Port already uses (engine._air_port: the harbour serves whoever controls the hex, and the
    game-turn the fortress changes hands, besieger and besieged swap). AirFacility.side is only the
    SEEDED owner, the fallback for a hex neither player has yet entered, so a scenario that records
    no control there reads as it was set up."""
    control = state.control_of(facility.hex)
    if control == Control.NEUTRAL:
        return facility.side
    return Side.AXIS if control == Control.AXIS else Side.ALLIED


def facilities_of(state: GameState, side: Side) -> tuple[AirFacility, ...]:
    """The air facilities `side` currently HOLDS (36.15, see holder), id-ordered."""
    return tuple(sorted((f for f in state.air_facilities if holder(state, f) == side),
                        key=lambda f: f.id))


def sgsus_at(state: GameState, hex_, side: Side) -> tuple[Unit, ...]:
    """A side's on-map SGSU counters standing on `hex_`, id-ordered (deterministic)."""
    return tuple(sorted((u for u in state.units_at(hex_) if u.side == side and is_sgsu(u)),
                        key=lambda u: u.id))


def functioning_sgsus(state: GameState, facility: AirFacility) -> tuple[Unit, ...]:
    """[36.13] / [36.14] The SGSUs at `facility` that its CURRENT Capacity Level can actually work:
    the first `level` of them, id-ordered.

    36.13: "no more than six squadron's worth of planes may be readied at a given airfield"; 36.14
    spells out what a battered field means -- six SGSUs may still STAND there, "even though some may
    not be able to function because of a reduced capacity level". So the counter limit (SGSU_HEX_LIMIT)
    and the working limit (`level`) are separate, and this is the working one. Which SGSUs work is the
    owner's free choice; id order is OUR deterministic assignment of it, the same convention the
    first-line truck split and the blind barrage pick use."""
    return sgsus_at(state, facility.hex, holder(state, facility))[:max(0, facility.level)]


def may_refit(state: GameState, sgsu: Unit) -> bool:
    """[35.14] / [35.17] / [36.13] THE REFIT GATE -- the one Phase 5.3's Refit Table reads.

    Three conditions, each a rule:
      * 35.14 -- the SGSU drew its own upkeep. "SGSUs without the required supplies (for themselves)
        MAY NOT REPAIR THEIR PLANES." `stages_without_air_supply` is the consecutive count of
        Operations Stages it went short (game.engine._sgsu_upkeep); zero means it is fed.
      * 35.17 -- only an SGSU refits at all, and it refits AT a base: "planes may not be refueled or
        refitted beyond the capacity of the air facility (see Case 36.12, 36.2, 36.3 and 36.4)."
      * 36.13/36.14 -- and only within that facility's current Capacity Level.

    NOT modelled here (5.3's job, flagged): 35.17's +1 to the refit die when a plane refits at an
    SGSU other than its own squadron's."""
    if sgsu.stages_without_air_supply > 0:
        return False
    facility = facility_at(state, sgsu.hex)
    if facility is None or destroyed(facility) or holder(state, facility) != sgsu.side:
        return False
    return sgsu.id in {u.id for u in functioning_sgsus(state, facility)}
