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
refit die, 24.7 air-facility CONSTRUCTION (the rebuild LAW is here; no order routes to it yet), 36.5
off-map facilities, 36.18's intrinsic 1 AA point, and the 44.5 Malta construction table. Each is
named in the port plan under 5.2-5.5. (35.2's squadron CAPACITIES arrived with 5.3 -- the [35.23]
chart is transcribed and squadron_capacity reads it for 38.33; the squadron COMPOSITION SHEET, 34.72,
is still 5.4's.)

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
  * **NO SCENARIO OR POLICY GENERATES AN 'airfield' AIR MISSION** -- still true of the LAND SUPPORT
    channel. engine._air_facility_bomb is the 41.36 resolver for a tactical B-AF mission and the
    only caller in the tree is its test. What 5.4 built instead is the STRATEGIC one: engine.
    _malta_raid resolves 44.21's raid on the same [41.5] Airfields row and the same 41.36 rule, but
    it may not route through _air_facility_bomb, because that function sizes its attack from
    _air_points (the LAND arena's committed strike points, gated by air superiority and paid for
    with 38.24 fuel) and a Malta raid is sized by the [44.42] Availability Table out of a force
    that is largely NOT IN PLAY (44.22). Two callers, one rule, two different sources of strength.
  * **THE 35.14 UPKEEP HAS NO REFILL PATH, AND 5.3 HAS NOW HUNG THE REFIT TABLE ON IT.** See
    engine._sgsu_upkeep's own flag: 36.3, 35.15 and the [60.33]/[60.43] air-facility lorry rows are
    the rulebook's three ways to restock an airfield and none is built, so the charted allotment is a
    pot that only shrinks. 5.1 raised this as an OWNER RULING to make BEFORE 5.3, and 5.3 landed
    without it, deliberately: the faithful thing is to implement rule 38 as printed and let the
    consequence be visible rather than to invent a faucet. THE CONSEQUENCE, MEASURED over the full
    campaign (seeds 4/1941/7): the air-facility pot empties, every SGSU then reads unfed, and from
    roughly Game-Turn 13-33 every refit attempt is DENIED for want of an SGSU that may work --
    AIR_REFIT_DENIED(reason='no_sgsu') 280/299/65 times, after which that side's squadrons are
    permanently unfit and its air war is over. That is rule 35.14 doing exactly what it says to an
    air force nobody resupplies; the missing piece is the resupply, not the rule. **It is the
    binding constraint on Phase 5.4: Malta cannot be a lever pulled by an air force that stops
    flying in 1941.**

    CORRECTION, 2026-07-21 (the 5.3 repair pass): 35.14 is NOT the whole of that drain, and the
    5.3 commit's attribution of it was too clean. 38.36 charges a Stores Point for every refit
    ATTEMPT, and this engine attempts for every squadron with an unfit plane every Operations
    Stage because the rest of that case -- "A PLAYER IS NOT REQUIRED TO TRY TO REFIT ANY PLANE;
    THE CHOICE TO REFIT OR NOT IS UP TO HIM" -- has no order channel to route it through
    (flagged at engine._air_maintenance). MEASURED over the full campaign, Stores drawn out of
    the air-facility dumps: seed 7 Commonwealth 33 on compulsory refit attempts against 18 on
    35.14 upkeep -- the larger half of its drain; seed 4 Axis 28 against 73, Commonwealth 7
    against 46. So OUR default is a co-driver of the exhaustion, worth between a quarter and two
    thirds of it, and the owner ruling should be read with that in it.
"""
from __future__ import annotations

from typing import NamedTuple

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
    """[35.14] / [35.17] / [36.13] THE REFIT GATE -- the one the [38.37] Refit Table reads (5.3's
    able_sgsus is the side-wide scan built on it, and engine._air_maintenance denies the attempt
    outright when it comes back empty).

    Three conditions, each a rule:
      * 35.14 -- the SGSU drew its own upkeep. "SGSUs without the required supplies (for themselves)
        MAY NOT REPAIR THEIR PLANES." `stages_without_air_supply` is the consecutive count of
        Operations Stages it went short (game.engine._sgsu_upkeep); zero means it is fed.
      * 35.17 -- only an SGSU refits at all, and it refits AT a base: "planes may not be refueled or
        refitted beyond the capacity of the air facility (see Case 36.12, 36.2, 36.3 and 36.4)."
      * 36.13/36.14 -- and only within that facility's current Capacity Level.

    STILL NOT modelled, and now flagged in refit_drm as well: 35.17/38.33's +1 to the refit die when
    a plane refits at an SGSU other than its own squadron's. There is no plane-to-SGSU assignment to
    test until 34.72's Squadron Composition Sheet, so every refit here is a squadron's own."""
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
# data/logistics_rates.json and eyes-verified off the 1979 scan -- ratings AND the Mission
# Capability cells ("the types of missions the plane may be assigned"), which is the chart's own
# statement of what a type may be ORDERED to do:
#   Bf. 109E        (PDF p.144) TacAir 6, Fuel 1, F=! S=! R=- D=!  -- the Luftwaffe's fighter
#   Ju. 87B         (PDF p.145) Bomb 5,   Fuel 1, D=! R=- B=- T=-  -- the Stuka, the Axis bomber
#   Hs. 126         (PDF p.145) Fuel 1,           D=! R=! B=- T=-  -- German army-cooperation recon
#   Hurricane Mk. I (PDF p.112) TacAir 4, Fuel 1, F=! S=! R=- D=-  -- the Desert Air Force's fighter
#   Blenheim Mk. I  (PDF p.113) Bomb 5,   Fuel 2, D=- R=- B=! T=-  -- its light bomber
#   Lysander Mk. I  (PDF p.113) Fuel 1,           D=S R=! B=- T=-  -- its army-cooperation recon
REPRESENTATIVE_AIRCRAFT: dict[tuple[Side, str], str] = {
    (Side.AXIS, "fighters"): "Bf. 109E",
    (Side.AXIS, "strike"): "Ju. 87B",
    (Side.AXIS, "recon"): "Hs. 126",
    (Side.ALLIED, "fighters"): "Hurricane Mk. I",
    (Side.ALLIED, "strike"): "Blenheim Mk. I",
    (Side.ALLIED, "recon"): "Lysander Mk. I",
}

# Which charted rating an Air Point of each role is denominated in (see the block comment):
# fighters -> 34.13 TacAir, strike -> 34.14 Bombload, recon -> None, one point is one plane.
# EXPLICIT IN ALL THREE ROLES and read with [], never .get(): an unknown role is a KeyError, not a
# silent one-plane mission at rating 1.
_POINTS_PER_PLANE_RATING: dict[str, "str | None"] = {
    "fighters": "tacair", "strike": "bombload", "recon": None}

# [4.44A/b/c] MISSION CAPABILITY -- which printed cell each role's missions need. The chart prints
# F S R D beside every fighter and D R B Transport beside every bomber, and defines the block as
# "the types of missions the plane may be assigned":
#   F  "Offensive or Defensive Combat Air Patrol (CAP) or Strafing missions"   -> our fighters
#   R  "Reconnaissance (naval and/or land) missions"                           -> our recon
#   D  "Strafe and/or any type of bombing missions (see B below)"     \  either one is a bombing
#   B  "Axis Naval Convoy [Maltese, on the Axis chart] and Land Support Bombing missions"  /  order
# The D-vs-B split is a flagged JUDGEMENT CALL, argued at length in the data file's
# _comment_mission_capability_ruling: we read D as a superset of B (41.16 makes D the
# strafe-AND-bomb marker, and the alternative would leave the Luftwaffe bombing Malta and the
# Eighth Army with Ar. 196 flying boats, the only German airframe on the chart carrying B). Both
# our strike representatives pass either way for the missions the engine actually flies them on:
# the Ju. 87B carries D, the Blenheim Mk. I carries B, and 41.21 puts ports and airfields inside
# "Land Support". NOTHING GATES ON THIS YET -- it is transcribed for the 5.3/5.4 roster, and
# mission_capable is the read a test asserts the six representatives against.
_MISSION_CAPABILITY_FOR_ROLE: dict[str, tuple[str, ...]] = {
    "fighters": ("F",), "strike": ("D", "B"), "recon": ("R",)}

# The cells that mean "does not possess this capability": '-' as printed on the Axis charts, and
# 'S' which the Commonwealth key defines as "May only Strafe, MAY NOT BE ASSIGNED ANY BOMBING
# MISSIONS" (the Lysander's D cell -- it is a strafe permission, not a bombing one).
_NO_CAPABILITY = {"-", "S"}


def mission_capable(side: Side, role: str) -> bool:
    """[4.44A/b/c] Does the type `side` flies its `role` Air Points as possess the charted Mission
    Capability that role's missions need? Read off the transcribed cells, and true of all six
    representatives (tests/test_air_fuel.py asserts it). A pure data check: no engine path gates on
    it, because our Air Points are not a roster -- when 5.3/5.4 build the Squadron Composition
    Sheet, THAT is where a plane is refused a mission its chart row does not permit."""
    cells = AIRCRAFT[REPRESENTATIVE_AIRCRAFT[(side, role)]].get("mission_capability", {})
    return any(cells.get(c, "-") not in _NO_CAPABILITY
               for c in _MISSION_CAPABILITY_FOR_ROLE[role])


def points_per_plane(side: Side, role: str) -> int:
    """The charted rating one aeroplane of `side`'s `role` type carries an Air Point in: 34.13
    TacAir for a fighter, 34.14 Bombload for a strike, and 1 for recon (flagged -- no rating on the
    chart is denominated in "recon points", so one Air Point is one aeroplane)."""
    key = _POINTS_PER_PLANE_RATING[role]
    return 1 if key is None else AIRCRAFT[REPRESENTATIVE_AIRCRAFT[(side, role)]][key]


def fuel_per_plane(side: Side, role: str) -> int:
    """[34.17] One aeroplane's Fuel Consumption Rating -- "the number of Fuel Points required to
    enable ONE PLANE of that type to fly any one mission" (38.21). The unit the 38.24 draw is
    quantised in, because 38.24 refuels ONE PLANE AT A TIME."""
    return AIRCRAFT[REPRESENTATIVE_AIRCRAFT[(side, role)]]["fuel"]


def planes_flying(side: Side, role: str, points: int) -> int:
    """How many aeroplanes `points` committed Air Points of `role` are, for `side` (34.13/34.14).

    Rounded UP: a mission flown by a fraction of a plane is flown by a plane. Zero points are zero
    planes -- a side that has lost the sky to a scale of 0, or fields no wing of that role, puts
    nothing in the air and therefore burns nothing."""
    if points <= 0:
        return 0
    return -(-points // points_per_plane(side, role))   # ceil, in integers


def mission_fuel(side: Side, role: str, points: int) -> int:
    """[34.17]/[38.21] The Fuel Points ONE mission by `points` Air Points of `role` costs `side`:
    the number of planes flying times that plane's Fuel Consumption Rating. Distance is not in it
    -- "all Fuel Points are consumed during a mission, regardless of the type or distance"."""
    return planes_flying(side, role, points) * fuel_per_plane(side, role)


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


class Sortie(NamedTuple):
    """What [38.24] funded of one mission: `points` Air Points fly (0 = grounded), being `planes`
    of the `committed` aeroplanes the side wanted in the air, paid for by `draws` [(dump id, qty)]
    against a full bill of `need` out of `available` in the larder."""
    points: int
    planes: int
    committed: int
    draws: tuple[tuple[str, int], ...]
    need: int
    available: int


def refuel(state: GameState, side: Side, role: str, points: int) -> Sortie:
    """[38.24] Refuel as many of the aeroplanes `points` commits as `side`'s air-facility dumps can
    pay for, ONE PLANE AT A TIME, and report what flies.

        38.24 "To refuel a plane the necessary fuel must be in the hex containing the air facility
               ... the fuel is subtracted from the total supply in the air facility, and the plane
               is marked as refueled on the Squadron Composition Sheet. THIS IS DONE FOR EACH PLANE
               THAT A PLAYER WISHES TO REFUEL."
        38.21 "...the number of Fuel Points required to enable ONE PLANE of that type to fly ANY ONE
               MISSION."

    PER PLANE, NOT ALL-OR-NOTHING, and that is the rule's own last sentence. A larder holding one
    Fuel Point against a two-Stuka mission fuels ONE Stuka: the sortie flies at that plane's share
    of the committed Air Points (and, since strike Air Points ARE Bomb Points on this engine's
    bridge, delivers that share of the Bomb Points into the [41.5] column). Only a larder that
    cannot fuel a single plane grounds the mission outright (38.21: "planes must have fuel to fly";
    33 IV.F.1: "all planes THAT ARE FUELED may be assigned Missions"). This block previously
    refused any mission it could not fund in full, which is why a thinning air force read as a dead
    one; the rounding is the book's, not ours.

    Draws walk the dumps in id order, so the log is replay-stable.

    ⚠ FLAGGED, AND IT IS THE ONE PLACE THIS BLOCK IS WEAKER THAN THE RULE IT PORTS. 38.24's whole
    content is LOCALITY -- "the necessary fuel must be in THE HEX CONTAINING THE AIR FACILITY",
    singular, the field the plane stands on -- and we pool every air-facility dump the side holds
    anywhere on the map into one national larder. The proxy is forced, not chosen: game.state.AirWing
    is Air Points by ARENA, not a squadron based at a field, so there is no hex to be the plane's
    own. It is visible and it is not free: in campaign(seed=4) the Axis air-dump walk reaches the
    strip at (53,55) first, so a Stuka bombing Tobruk at (15,66) is fuelled 38 hexes away -- past its
    own charted Range of 36 (34.11) -- while the field one hex from the target sits untouched. It
    dissolves exactly when 34.72's Squadron Composition Sheet gives a squadron a base (5.3/5.4),
    which is also what 34.11 range-checking waits on. Until then this is one larder, and the number
    it reports is a national total.

    NOT modelled here either, and each is named where it will land: 38.22/38.23's requirement that
    an SGSU do the refuelling and its per-squadron cap (12 planes an Operations Stage for an Italian
    Squadriglia) -- that is the Refit Table's own bookkeeping in 5.3; 36.5's OFF-MAP air facilities,
    which is why a strategic mission flown from Malta or Egypt (the 41.6 convoy interdiction) draws
    from no on-map pile; and 38.4's Ammunition Points for bombs (38.44), which is a separate
    commodity and a separate block."""
    committed = planes_flying(side, role, points)
    dumps = facility_dumps(state, side)
    available = sum(su.fuel for su in dumps)
    per = fuel_per_plane(side, role)
    need = committed * per
    planes = min(committed, available // per) if committed > 0 else 0
    if planes <= 0:
        return Sortie(0, 0, committed, (), need, available)
    draws: list[tuple[str, int]] = []
    remaining = planes * per
    for su in dumps:
        if remaining <= 0:
            break
        take = min(remaining, su.fuel)
        if take > 0:
            draws.append((su.id, take))
            remaining -= take
    # the whole force flies at the points it was committed with; a part-funded one flies at its
    # planes' share of them (never more than was committed)
    flown = points if planes == committed else min(points, planes * points_per_plane(side, role))
    return Sortie(flown, planes, committed, tuple(draws), need, available)


# --- [38.3] REFITTING AIRCRAFT -- THE SORTIE-RATE GOVERNOR --------------------------------------
#
# This block is the answer to "why can one AirWing fly the same six strike points every Operations
# Stage for a hundred and eleven Game-Turns?" It could, because nothing wore out. Rule 38.3, whole:
#
#   38.3  "Refitting aircraft is repairing and maintaining them so that they can fly ANOTHER
#          MISSION. In order to fly any mission other than a transfer, a plane MUST BE REFITTED."
#   38.31 "At the start of a Scenario, all planes are considered refitted... AS SOON AS A PLANE
#          FLIES ANY MISSION other than transfer, IT MUST BE REFITTED AGAIN. A plane that is not
#          refitted MAY FLY NO MISSION other than transfer, even if it is refueled."
#   38.34 "Refitting is NOT A GUARANTEED PROCESS, like refueling. Players must roll for each
#          squadron undergoing refit... throws one die, making any adjustments (see Case 38.35) and
#          consulting the Aircraft Refit Table. The table gives him THE PERCENTAGE OF PLANES
#          SUCCESSFULLY REFITTED. (Round all fractions up.)"
#   38.35 "...If the planes attempting refit are ITALIAN, the Player (be he Axis or Commonwealth)
#          ADDS TWO to the dieroll. If the planes are GERMAN, ADD ONE."
#   38.36 "For every squadron undergoing an attempted refit -- WHETHER SUCCESSFUL OR NOT -- the
#          Player must have present and actually EXPEND ONE STORES POINT."
#
# So readiness is a STOCK that flying spends and a die roll returns a fraction of, and the fraction
# is worse for the Axis by two printed modifiers. That asymmetry is the rulebook's model of Axis
# unserviceability, and until this block the engine handed it away for nothing.
#
# WHAT A "SQUADRON" IS AT THIS GRAIN, AND IT IS FLAGGED. game.state.AirWing is Air Points by ARENA
# and ROLE, not a roster of squadrons -- and engine._air_points already POOLS every wing a side
# fields in an arena before anything reads them. So the smallest honest unit here is the pool
# itself: one squadron per (side, arena, role), which is exactly what the campaign and the siege
# each field. A scenario that seeded two wings of the same role in one arena would get ONE refit
# roll where the book would give it two. It dissolves with 34.72's Squadron Composition Sheet,
# which is the same thing air.refuel's pooled larder waits on.
REFIT_TABLE = logistics_data.aircraft_refit_table_38_37()
SQUADRON_CAPACITY = logistics_data.squadron_capacity_35_23()

# [38.37] "German Squadron Ground Support Unit add 1. Italian Ground Support Unit add 2." Keyed on
# the nationality game.oob built the SGSU counter under. A counter that states no nationality (every
# hand-built test unit) takes no modifier -- the Commonwealth's own row, which the chart prints no
# modifier for at all.
_REFIT_DRM_KEY: dict[str, str] = {"IT": "italian_sgsu", "GE": "german_sgsu"}

_CAPACITY_KEY: dict[str, str] = {"IT": "italian", "GE": "german"}

# [38.36] "For every squadron undergoing an attempted refit -- whether successful or not -- the
# Player must have present and actually EXPEND ONE STORES POINT." The rule's own quantity, named
# here beside the 35.14 upkeep rates rather than left inline at the point of expenditure.
REFIT_STORES_PER_ATTEMPT = 1


def refit_drm(nationality: str) -> int:
    """[38.35]/[38.37] The serviceability modifier the refitting SGSU's nationality adds to the
    refit die: +2 Italian, +1 German, none Commonwealth. A HIGHER modified roll is a WORSE result
    on the table, so these two numbers ARE the Axis's chronic unserviceability.

    ⚠⚠ TWO OWNER RULINGS RIDE ON THIS FUNCTION. Both are written out in full in the data file
    (aircraft_refit_38_37.by_squadron.modifiers), and neither is decided here.

    1. THE CHART AND THE CASE NAME DIFFERENT SUBJECTS: the chart modifies for the refitting SGSU's
       nationality, 38.35's prose for the PLANES'. These do NOT merely differ in cases this engine
       cannot reach -- [35.28] licenses "Italian squadrons ... entirely of German planes", so an
       Italian Squadriglia worked by its OWN Italian SGSU reads +2 on the chart and +1 in the prose.
       The book contradicts itself in its own normal case. We read the SGSU counter (the chart's
       subject, and a transcribed fact) rather than the plane type (game.air's flagged
       representative-aircraft proxy) -- but that is a choice, not a coincidence.

    2. AND IN THE CAMPAIGN THE CHOICE IS MADE BY A COUNTER THAT WAS NEVER TRANSCRIBED. The campaign
       order of battle holds SEVEN Axis SGSUs, all Italian ([60.32] "Italian SGSU Available: 39",
       Scenario Group One, Sept 1940 - Feb 1941) and NO German one, because no German SGSU
       availability is transcribed for the campaign at all (game.oob.seed_sgsus carries the same
       flag). So the Luftwaffe's Staffeln -- the Bf. 109E / Ju. 87B / Hs. 126 of
       REPRESENTATIVE_AIRCRAFT -- are refitted all war at the ITALIAN +2, when under EITHER reading
       above a German squadron worked by its own German ground crew takes +1. THE +2 THE AXIS ROLLS
       AT IN THIS ENGINE IS THEREFORE AN ARTEFACT OF A MISSING COUNTER, NOT A PRINTED FACT ABOUT THE
       GERMAN AIR FORCE, and it is worth about a sixth of the Axis air force (realised refit 48.6%
       at +2 against ~56.7% at +1). The 5.3 commit message called it "the printed size"; it is not.

    NOT modelled, and the same flag air.may_refit already carries: the chart's third modifier, +1 for
    "planes attempting refit not assigned to [the] Squadron Ground Support Unit attempting refit".
    There is no plane-to-SGSU assignment to test, so every refit here is a squadron's own -- the
    permissive reading, and the one 38.0 calls maximum efficiency."""
    key = _REFIT_DRM_KEY.get(nationality)
    return 0 if key is None else REFIT_TABLE["modifiers"][key]


def refit_percent(roll: int) -> int:
    """[38.37B] The percentage of the planes undergoing refit that a MODIFIED die roll refits:
    1->100, 2->80, 3->70, 4->60, 5->50, 6,7->40, 8,9->33. Read off the transcribed columns.

    One d6 plus the chart's own modifiers spans exactly the printed 1..9 (6 + 2 Italian + 1 foreign
    = 9), so no roll can fall outside the table. A roll that somehow did is a ValueError, NOT a
    clamp: this file's house rule twenty lines from its top is that an unknown key fails loud rather
    than silently answering (see _POINTS_PER_PLANE_RATING, read with [] and never .get()). The
    clamp this replaces would have answered 33% to a roll of 10 the day 35.17/38.33's +1
    foreign-squadron modifier lands and pushes the span past the printed table."""
    for col in REFIT_TABLE["columns"]:
        lo, hi = col["die"]
        if lo <= roll <= hi:
            return col["pct_refitted"]
    raise ValueError(f"[38.37] modified refit roll {roll} is off the printed table (1..9)")


def refitted_planes(undergoing: int, roll: int) -> int:
    """[38.34] How many of `undergoing` planes a modified `roll` refits -- the table's percentage,
    "round all fractions up"."""
    if undergoing <= 0:
        return 0
    return -(-undergoing * refit_percent(roll) // 100)      # ceil, in integers


def squadron_capacity(nationality: str, year: int, month: int) -> int:
    """[35.23]/[38.33] The most planes ONE Squadron Ground Support Unit may refit: its squadron's
    charted Ready plus Reserve -- "each SGSU can refit up to the maximum planes the SGSU can contain
    (Ready plus Reserve)". Italian 12 and German 16 undated; the Commonwealth squadron GROWS, so its
    row is chosen by the Game-Turn's (year, month).

    THE DATING IS TRANSCRIBED, NOT INFERRED HERE. Each Commonwealth row in the data file carries the
    `from`/`to` [year, month] span read off its own printed label, and this function selects the row
    whose span contains the date -- the boundary is a chart magnitude and lives with the chart. A
    date outside every printed row is a ValueError rather than a nearest-row guess (the book charts
    1940-43 because that is the war; nothing should be asking for 1944).

    ⚠ OWNER RULING NEEDED, WRITTEN OUT IN FULL AT squadron_capacity_35_23._owner_ruling_needed IN
    THE DATA FILE: the book prints this chart TWICE and the two printings disagree about BOTH
    Commonwealth numbers -- the play aid (PDF p.105) says 12+4=16 for 1940-41 and 18+6=24 from
    1942-43; case 35.23's own table (PDF p.53) says 15+5=20 for "1940-June '41" and 18+6=24 from
    "July 41-43", with the prose "starting with July 1941 Commonwealth Squadrons increase their
    capacity". BOTH were rendered and read with eyes. We apply the play aid pending the ruling,
    because every other 5.3 magnitude came off that same chart box; the rule-text printing is
    transcribed verbatim beside it under `rule_text_35_23_unapplied` and nothing reads it. The
    Italian and German rows are identical in both printings and are not in dispute."""
    key = _CAPACITY_KEY.get(nationality)
    if key is not None:
        return SQUADRON_CAPACITY[key]["total"]
    for row in SQUADRON_CAPACITY.values():
        if "from" not in row:                           # the undated Italian / German rows
            continue
        if tuple(row["from"]) <= (year, month) <= tuple(row["to"]):
            return row["total"]
    raise ValueError(f"[35.23] no charted Commonwealth squadron capacity for {year}-{month:02d}")


def squadron(side: Side, arena: str, role: str) -> str:
    """The key one squadron's readiness is carried under in GameState.air_unfit (see the block
    comment: at this grain a squadron IS the (side, arena, role) pool)."""
    return f"{side.value}/{arena}/{role}"


def refit_modelled(state: GameState, side: Side) -> bool:
    """Is `side`'s readiness governed by rule 38.3 in this scenario at all? THE SAME ESCAPE HATCH,
    FOR THE SAME REASON, AS air.based_on_map -- and it must stay the same one. A side the scenario
    never based on the map has no air facility for an SGSU to work at and no 36.17 pile to spend
    38.36's Stores Point out of, so 38.3 has nothing to bite on; grounding its air force for good
    because a COUNTER was never transcribed ([61.42]'s free Axis field west of El Agheila, [36.5]'s
    off-map bases) would enshrine a data gap as a rule. In the full campaign both sides are based on
    the map, so the governor binds where it matters."""
    return based_on_map(state, side)


def able_sgsus(state: GameState, side: Side) -> tuple[Unit, ...]:
    """[35.14]/[35.17]/[36.13] `side`'s SGSUs that may work on planes this Operations Stage, id
    ordered -- fed, at a facility their side holds, and inside its Capacity Level (see may_refit)."""
    return tuple(u for u in sorted(state.units, key=lambda u: u.id)
                 if u.side == side and is_sgsu(u) and may_refit(state, u))


def squadron_points(state: GameState, side: Side, arena: str, role: str) -> int:
    """The Air Points of `role` `side` has in `arena` -- the whole pool, BEFORE the 40/45/46
    superiority gate scales a commitment down. This is the squadron's establishment, not its
    tasking, so it is what a plane count is taken over."""
    return sum(getattr(w, role) for w in state.air if w.side == side and w.arena == arena)


def squadron_planes(state: GameState, side: Side, arena: str, role: str) -> int:
    """How many aeroplanes that establishment IS (34.13/34.14; see planes_flying)."""
    return planes_flying(side, role, squadron_points(state, side, arena, role))


def unfit_planes(state: GameState, side: Side, arena: str, role: str) -> int:
    """[38.31] The squadron's planes that have flown and not yet been refitted. Absent from the
    ledger means NONE -- "at the start of a Scenario, all planes are considered refitted" -- which
    is also why an air-less (or refit-less) scenario stays byte-identical."""
    return state.air_unfit.get(squadron(side, arena, role), 0)


def ready_planes(state: GameState, side: Side, arena: str, role: str) -> int:
    """[38.31] The squadron's planes that MAY fly a mission: its establishment less its unfit."""
    return max(0, squadron_planes(state, side, arena, role)
               - unfit_planes(state, side, arena, role))


def ready_points(state: GameState, side: Side, arena: str, role: str, points: int) -> int:
    """[38.31] `points` capped by what the squadron's REFITTED planes can carry: "a plane that is
    not refitted may fly no mission other than transfer, EVEN IF IT IS REFUELED."

    The cap is taken in planes and read back out in the rating those Air Points are denominated in
    (34.13 TacAir / 34.14 Bombload), never above what was asked for -- the identical arithmetic
    air.refuel uses when a larder fuels only part of a force, because it is the identical question
    asked of a different shortage.

    A squadron with NO establishment needs no special case and no longer carries one: its
    ready_planes is zero, so the cap grounds it -- which is the right answer to "how many of a
    squadron that has no aeroplanes may fly", not a fallback. (It is also unreachable: the only
    caller reads its commitment off the same pool, so points > 0 implies an establishment.)"""
    if points <= 0 or not refit_modelled(state, side):
        return points
    return min(points, ready_planes(state, side, arena, role) * points_per_plane(side, role))


def flying_planes(state: GameState, side: Side, arena: str, role: str, points: int) -> int:
    """[38.31] The planes `points` of a flown mission put in the air, never more than the squadron
    had refitted -- the count that goes UNFIT the moment the mission is flown."""
    return min(planes_flying(side, role, points), ready_planes(state, side, arena, role))
