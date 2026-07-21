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

AND THREE MORE, NAMED HERE BECAUSE THEY ARE EASY TO MISTAKE FOR BUILT:

  * **THE ARTILLERY HALF OF 36.14 IS UNBUILT.** The rule reads "the capacity of an airfield (its
    levels) may be reduced by enemy bombardment (AIR OR ARTILLERY)", and 36.4 gives the alighting
    area an immunity that only means something once guns can hit a field ("they are immune to
    artillery barrage"). 12.51/12.54 are the procedure -- an Air Facility is an explicit barrage
    target and "he uses his Raw Barrage Points... to correspond to the Bombload column", i.e. the
    SAME [41.5] column set the bombing path already reads. Nothing in game/ implements 12.5 against a
    facility, so only the AIR half of 36.14 exists. Note what this does and does not need from the
    data: [41.5] is printed on THREE index scales side by side (Torpedo Points, Barrage Points, Bomb
    Points) and data/logistics_rates.json transcribes only bomb_points -- but 12.54 sends the barrage
    at a facility to the Bombload column, so the facility path needs no new transcription. The
    Barrage-Points scale is owed to the OTHER target rows of that table.
  * **NO SCENARIO OR POLICY GENERATES AN 'airfield' AIR MISSION.** engine._air_facility_bomb is the
    41.36 resolver and it is real and tested, but the only caller in the tree is the test. It is
    5.4's foundation (44.21's suppression of Malta is what will fly these), not a live channel.
  * **THE 35.14 UPKEEP HAS NO REFILL PATH.** See engine._sgsu_upkeep's own flag: 36.3, 35.15 and the
    [60.33]/[60.43] air-facility lorry rows are the rulebook's three ways to restock an airfield and
    none is built, so the charted allotment is a pot that only shrinks. OWNER RULING before 5.3
    hangs the Refit Table on may_refit.
"""
from __future__ import annotations

from . import logistics_data
from .events import Control, Side
from .state import AirFacility, GameState, SupplyUnit, Unit

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


# --- [34.17] / [38.21] / [38.24] WHAT IT COSTS TO PUT A PLANE IN THE AIR -----------------------
#
# The rulebook's three sentences, verbatim, and they are the whole of this block:
#
#   34.17 "This is the number of Fuel Points a plane requires to perform ANY mission or emergency
#          flight. ALL FUEL POINTS ARE CONSUMED DURING A MISSION, REGARDLESS OF THE TYPE OR
#          DISTANCE OF THE MISSION."
#   38.21 "Planes must have fuel to fly. The amount of fuel needed to refuel a plane is its FUEL
#          CONSUMPTION RATING, listed on the Aircraft Characteristics Chart. That is the number of
#          Fuel Points required to enable one plane of that type to fly ANY ONE MISSION."
#   38.24 "To refuel a plane the necessary fuel MUST BE IN THE HEX CONTAINING THE AIR FACILITY
#          (which usually acts as a supply dump for its planes). THE FUEL IS SUBTRACTED FROM THE
#          TOTAL SUPPLY IN THE AIR FACILITY."
#
# So the bill is per PLANE per MISSION, it does not vary with distance, and it comes out of the
# 36.17 pile Phase 5.1 put on the map. Until this block, no Fuel Point had ever left any dump for
# any aircraft anywhere: the air force was fed on air.
#
# THE ONE THING THAT IS NOT IN THE BOOK IS OUR OWN ABSTRACTION. game.state.AirWing is not a roster
# of planes; it is Air Points by role, and the engine already commits itself to what two of those
# roles MEAN:
#   * STRIKE Air Points are BOMB POINTS -- _air_port / _air_facility_bomb feed them straight into
#     the Bomb-Point columns of the [41.5] CRT, and 34.14 defines Bombload Capacity as "the number
#     of Bomb Points... that a Plane can carry".
#   * FIGHTER Air Points are TACAIR -- _air_superiority adds a die to them and compares, and 34.13
#     defines TacAir as "the aircraft's combat rating vis a vis other aircraft".
# Both of those ratings belong to a PLANE. So the conversion is forced once you name the plane:
# planes = ceil(points / that plane's rating), and each plane burns its Fuel Consumption Rating.
#
# ⚠ FLAGGED, TWICE. (a) WHICH plane represents a wing is OUR judgement call -- the 34.6/59.3 Initial
# Air Strengths roster is untranscribed (state.AirWing says so of its own magnitudes), so we name the
# type each air force actually flew in this theatre and cite the chart row. (b) RECON has no charted
# per-point scale at all -- no rating on the chart is denominated in "recon points" -- so one recon
# Air Point is read as one aeroplane. Both dissolve when 5.3/5.4 build the Squadron Composition Sheet
# (34.72) and the real roster; the RULE above does not depend on either.
AIRCRAFT = logistics_data.aircraft_characteristics_4_44()

# The type each side's abstract wing is expressed in. Every row is transcribed in
# data/logistics_rates.json and eyes-verified off the 1979 scan:
#   Bf. 109E        (PDF p.144) TacAir 6, Fuel 1  -- the Luftwaffe's fighter over the desert
#   Ju. 87B         (PDF p.145) Bomb 5,   Fuel 1  -- the Stuka, the Axis tactical bomber
#   Hs. 126         (PDF p.145) Fuel 1            -- the German army-cooperation recon plane
#   Hurricane Mk. I (PDF p.112) TacAir 4, Fuel 1  -- the Desert Air Force's fighter
#   Blenheim Mk. I  (PDF p.113) Bomb 5,   Fuel 2  -- its light bomber
#   Lysander Mk. I  (PDF p.113) Fuel 1            -- its army-cooperation recon plane
REPRESENTATIVE_AIRCRAFT: dict[tuple[Side, str], str] = {
    (Side.AXIS, "fighters"): "Bf. 109E",
    (Side.AXIS, "strike"): "Ju. 87B",
    (Side.AXIS, "recon"): "Hs. 126",
    (Side.ALLIED, "fighters"): "Hurricane Mk. I",
    (Side.ALLIED, "strike"): "Blenheim Mk. I",
    (Side.ALLIED, "recon"): "Lysander Mk. I",
}

# Which charted rating an Air Point of each role is denominated in (see the block comment):
# fighters -> 34.13 TacAir, strike -> 34.14 Bombload, recon -> one point is one plane.
_POINTS_PER_PLANE_RATING = {"fighters": "tacair", "strike": "bombload"}


def planes_flying(side: Side, role: str, points: int) -> int:
    """How many aeroplanes `points` committed Air Points of `role` are, for `side` (34.13/34.14).

    Rounded UP: a mission flown by a fraction of a plane is flown by a plane. Zero points are zero
    planes -- a side that has lost the sky to a scale of 0, or fields no wing of that role, puts
    nothing in the air and therefore burns nothing."""
    if points <= 0:
        return 0
    plane = AIRCRAFT[REPRESENTATIVE_AIRCRAFT[(side, role)]]
    rating_key = _POINTS_PER_PLANE_RATING.get(role)
    rating = plane[rating_key] if rating_key else 1     # recon: one Air Point is one aeroplane
    return -(-points // rating)                        # ceil, in integers


def mission_fuel(side: Side, role: str, points: int) -> int:
    """[34.17]/[38.21] The Fuel Points ONE mission by `points` Air Points of `role` costs `side`:
    the number of planes flying times that plane's Fuel Consumption Rating. Distance is not in it
    -- "all Fuel Points are consumed during a mission, regardless of the type or distance"."""
    plane = AIRCRAFT[REPRESENTATIVE_AIRCRAFT[(side, role)]]
    return planes_flying(side, role, points) * plane["fuel"]


def facility_dumps(state: GameState, side: Side) -> tuple[SupplyUnit, ...]:
    """[38.24]/[36.17] The air-facility dumps `side` may refuel out of, id-ordered: the air_dump
    Supply Units standing in the hex of a facility this side HOLDS (36.15) and that is not
    destroyed (36.14 -- a field at zero capacity "is considered destroyed for all purposes", and
    nothing takes off from it). A dump on a facility hex the enemy has walked onto is his now,
    which is the same rule 32.13 already applies to every other pile on the map."""
    hexes = {f.hex for f in facilities_of(state, side) if not destroyed(f)}
    return tuple(sorted((su for su in state.active_supplies(side)
                         if su.air_dump and su.hex in hexes), key=lambda su: su.id))


def based_on_map(state: GameState, side: Side) -> bool:
    """Does this scenario give `side` an air base ON THE MAP at all -- i.e. is there a rule-38.24
    hex for its fuel to be in? Read off the SEEDED owner (AirFacility.side), never off current
    holdings, and that distinction is the whole point: a side that HAS fields and loses them all
    is grounded (its fuel is gone with them), while a side the scenario never based on the map is
    outside the model and is not charged at all.

    ⚠ FLAGGED, AND IT IS THE ONE ESCAPE HATCH IN THIS BLOCK. It exists because two real basing
    rules are unbuilt and BOTH are data, not law: 36.5's OFF-MAP air facilities (Sicily, Crete,
    the Delta, Malta -- where a strategic mission is flown from), and, in the Desert Fox benchmarks
    specifically, 61.42's free Axis "one airfield and one air landing strip in any hex west of El
    Agheila", which the extraction never placed (game.oob.air_dumps says so of the missing [61.44]
    allotment). Grounding an air force because a COUNTER was never transcribed would enshrine a
    data gap as a rule, so where the map holds no base for a side, 38.24 has nothing to subtract
    from and the fuel chain does not exist. In the FULL CAMPAIGN both sides are based on the map,
    so the rule binds where it matters. Closing 61.42/36.5 closes the hatch."""
    return any(f.side == side for f in state.air_facilities)


def refuel(state: GameState, side: Side, need: int) -> "list[tuple[str, int]] | None":
    """[38.24] Draw `need` Fuel Points out of `side`'s air-facility dumps, or None if they cannot
    cover it -- in which case NOTHING is drawn and the planes do not fly (38.21: "planes must have
    fuel to fly"; 33 IV.F.1: "all planes THAT ARE FUELED may be assigned Missions").

    Returns [(supply_id, qty)] in facility-dump id order, so the draw is replay-stable. All or
    nothing: our Air Points are one indivisible commitment per mission, and part-funding a mission
    (fewer planes, fewer Bomb Points) needs the per-plane ledger of 34.72 -- deferred with it.

    NOT modelled here, and each is named where it will land: 38.22/38.23's requirement that an SGSU
    do the refuelling and its per-squadron cap (12 planes an Operations Stage for an Italian
    Squadriglia) -- that is the Refit Table's own bookkeeping in 5.3; 36.5's OFF-MAP air facilities,
    which is why a strategic mission flown from Malta or Egypt (the 41.6 convoy interdiction) draws
    from no on-map pile; and 38.4's Ammunition Points for bombs (38.44), which is a separate
    commodity and a separate block."""
    if need <= 0:
        return []
    draws: list[tuple[str, int]] = []
    remaining = need
    for su in facility_dumps(state, side):
        if remaining <= 0:
            break
        take = min(remaining, su.fuel)
        if take > 0:
            draws.append((su.id, take))
            remaining -= take
    return draws if remaining <= 0 else None
