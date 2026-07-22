"""[34.6] / [59.3] THE INITIAL AIR STRENGTHS -- the real air force, by type, and the bridge from a
roster of aeroplanes to the Air Points the engine flies.

Until this module existed the Axis strike establishment was FOUR AEROPLANES. `game.air` expressed
the whole Regia Aeronautica and Luftwaffe as one representative type (a Ju. 87B) and
`scenario._AXIS_AIR_STRIKE` seeded it 24 Bomb Points, which rule 43 cut to a quarter: three Ju. 87B
before Game-Turn 35 and one after. [60.32] musters **one hundred and thirty-three S.M. 79
Sparvieros alone**, and 394 aeroplanes in all. Percentages of three round to zero, which is why 84
of 111 Malta raids delivered no bomb points -- the rules were built and the world they act on was
not.

  [59.31] "Each scenario lists the starting Axis and Allied PLANE TYPES, NUMBERS, pilots, air
    facilities, and squadron ground support units."
  [59.32] "Planes are listed by type, WITH THE READY PLANES INDICATED AS A PORTION OF THE TOTAL
    AVAILABLE."
  [34.19] "All aircraft Ratings are listed on the Aircraft Characteristics Chart, 34.6."

THE THREE THINGS THIS MODULE IS, AND EACH IS A NUMBER THE ENGINE HAD TO INVENT BEFORE:

  * **THE ESTABLISHMENT** -- how many aeroplanes of each type a side has, and how many of them
    start refitted (38.31's ledger at Game-Turn 1, which `game.scenario` seeds `air_unfit` from).
  * **THE ROLE PARTITION** -- which of `game.state.AirWing`'s three buckets each type is fielded in.
    It is the one judgement in the data file and it is argued there, per row, against the charts'
    printed Mission Capability cells; `tests/test_establishment.py` asserts every row against them.
  * **THE POINTS BRIDGE.** An Air Point is a charted RATING: a fighter Air Point is 34.13 TacAir, a
    strike Air Point is 34.14 Bombload, and a recon Air Point is one aeroplane (no rating on any
    chart is denominated in "recon points" -- flagged, as it was before). So an establishment of N
    aeroplanes is worth a fixed number of Air Points, and the conversion back is exact at the whole
    establishment and proportional below it. THIS REPLACES `air.REPRESENTATIVE_AIRCRAFT`: the
    denominator is no longer one hand-picked aeroplane's rating but the real roster's own, which is
    why 2,147 Axis strike Air Points are 184 bombers and not 430 Stukas.

⚠ ONE ESTABLISHMENT, USED EVERYWHERE, AND THAT IS A FLAGGED PROXY FOR THE OTHER SCENARIOS. Only the
campaign's muster is transcribed -- [64.3] sends the campaign to section 60, so [60.32]/[60.42] ARE
the campaign's Initial Air Strengths -- and the two benchmark scenarios (`rommels_arrival`,
`siege_of_tobruk`) keep the flagged Air-Point proxies they already had while converting them through
the campaign roster's ratios. Their own musters ([61.42], [61.33]) are half-untranscribable today:
[61.42] gives its German half as "all of the German planes listed in the Axis Airplane Reinforcement
Chart", which is [34.87] and is not transcribed anywhere. `SCENARIO` is the seam that closes when
they are.

⚠ AND THE ESTABLISHMENT DOES NOT GROW. [34.84]'s monthly airplane reinforcements ride on [34.86]
(Commonwealth) and [34.87] (Axis), neither of which is transcribed -- so there is NO GERMAN
AEROPLANE IN THE CAMPAIGN AT ALL, because [60.32] has none and nothing brings one. That is the
finding this block hands to the next one, and it is why rule 43's typed cases (43.11/43.13, written
about He. 111s, Ju. 88Ds and Fw. 200 Cs) still bind on nothing: not because the engine fields an
abstraction they miss, but because the September-1940 Axis air force in Africa IS the Regia
Aeronautica and the Luftwaffe has not arrived.
"""
from __future__ import annotations

from typing import NamedTuple

from . import logistics_data
from .events import Side

# The scenario whose [59.3] muster the engine reads. Only one is transcribed (see the module
# docstring); named rather than inlined so that the day [61.42]/[62.43]/[63.43] land, the scenario
# builder passes its own key instead of inheriting this one.
SCENARIO = "campaign_64"

# [34.13]/[34.14] WHICH CHARTED RATING AN AIR POINT OF EACH ROLE IS DENOMINATED IN. Explicit in all
# three roles and read with [], never .get(): an unknown role is a KeyError, not a silent one-plane
# mission at rating 1. `None` is the recon flag -- no rating on any of the three charts is
# denominated in "recon points", so one Air Point is one aeroplane.
RATING_FOR_ROLE: dict[str, "str | None"] = {
    "fighters": "tacair", "strike": "bombload", "recon": None}

# [4.44A/b/c] The cells that mean "does not possess this capability": '-' as printed on the Axis
# charts, and 'S' which the Commonwealth key defines as "May only Strafe, MAY NOT BE ASSIGNED ANY
# BOMBING MISSIONS" (the Lysander Mk. I's D cell -- a strafe permission, not a bombing one).
NO_CAPABILITY = frozenset({"-", "S"})

# [4.44A/b/c] MISSION CAPABILITY -- which printed cell each role's missions need, as the charts
# define them: "F = Offensive or Defensive Combat Air Patrol (CAP) or Strafing missions",
# "R = Reconnaissance (naval and/or land) missions", "D = Strafe and/or any type of bombing
# missions (see B below)" / "B = Axis Naval Convoy [Maltese, on the Axis chart] and Land Support
# Bombing missions". The D-vs-B split is the flagged judgement call argued at length in
# data/logistics_rates.json (_comment_mission_capability_ruling): D is read as a superset of B.
CAPABILITY_FOR_ROLE: dict[str, tuple[str, ...]] = {
    "fighters": ("F",), "strike": ("D", "B"), "recon": ("R",)}


class Muster(NamedTuple):
    """One printed row of a scenario's Initial Air Strengths: `available` aeroplanes of `type` (the
    [4.44] chart's printed name), of which `refitted` begin the game serviceable (59.32), fielded in
    `role`. `printed` is the scenario's own spelling of the name, kept because it is what a reader
    checking the transcription against the book will be looking at."""
    type: str
    printed: str
    available: int
    refitted: int
    role: str


def _establishments() -> dict:
    return logistics_data.air_establishments_59_3()


def _side_key(side: Side) -> str:
    return side.value


def roster(side: Side, scenario: str = SCENARIO) -> tuple[Muster, ...]:
    """[59.3] `side`'s whole printed muster, in the order the book prints it (which is the order it
    is transcribed in, so every walk over it is replay-stable)."""
    rows = _establishments()[scenario][_side_key(side)]["planes"]
    return tuple(Muster(r["type"], r["printed"], r["available"], r["refitted"], r["role"])
                 for r in rows)


def by_role(side: Side, role: str, scenario: str = SCENARIO) -> tuple[Muster, ...]:
    """The muster rows `side` fields in `role` (see the data file's `_role_assignment`)."""
    if role not in RATING_FOR_ROLE:
        raise KeyError(f"[34.6] no such air role: {role!r}")
    return tuple(m for m in roster(side, scenario) if m.role == role)


def _chart(name: str) -> dict:
    return logistics_data.aircraft_characteristics_4_44()[name]


def nation(name: str) -> str:
    """[4.44A/b/c] The nationality the chart prints against a type. It is read because ONE rule in
    this port has a NATIONALITY for its subject rather than a type: [43.12] "75% of ALL GERMAN
    BOMBERS must be based in Italy/Sicily" (game.basing.german_bombers), which is a strictly wider
    population than 43.11/43.13's three named heavies."""
    return _chart(name)["nation"]


def rating(name: str, role: str) -> int:
    """[34.13]/[34.14] The Air Points ONE aeroplane of `name` carries in `role`: its charted TacAir
    for a fighter, its charted Bombload for a strike, and 1 for recon (the flagged scale)."""
    key = RATING_FOR_ROLE[role]
    return 1 if key is None else _chart(name)[key]


def planes(side: Side, role: str, scenario: str = SCENARIO) -> int:
    """[59.32] The aeroplanes `side`'s establishment fields in `role` -- its Total Available."""
    return sum(m.available for m in by_role(side, role, scenario))


def ready(side: Side, role: str, scenario: str = SCENARIO) -> int:
    """[59.32] Of those, the ones that begin the game refitted -- the Total Refitted column, which
    is 38.31's readiness ledger at Game-Turn 1."""
    return sum(m.refitted for m in by_role(side, role, scenario))


def unfit(side: Side, role: str, scenario: str = SCENARIO) -> int:
    """[38.31]/[59.32] The establishment's planes that start UNSERVICEABLE -- what game.scenario
    seeds GameState.air_unfit with. The scenario's Refitted column is the more specific rule and it
    overrides 38.31's blanket "at the start of a Scenario, all planes are considered refitted"; the
    same reading data/malta_44.json already applies to [60.46]'s three unserviceable Swordfish."""
    return planes(side, role, scenario) - ready(side, role, scenario)


def points(side: Side, role: str, scenario: str = SCENARIO) -> int:
    """[34.13]/[34.14] The Air Points `side`'s whole `role` establishment is worth: every aeroplane
    at its own charted rating. This is what game.scenario seeds an AirWing with, and it is the
    numerator of the points-to-planes bridge below."""
    return sum(m.available * rating(m.type, role) for m in by_role(side, role, scenario))


def planes_flying(side: Side, role: str, air_points: int, scenario: str = SCENARIO) -> int:
    """How many aeroplanes `air_points` of `role` ARE, for `side`.

    The establishment's own ratio, in exact integers: at the whole establishment it returns the
    whole establishment (2,147 Axis strike Air Points are exactly 184 bombers), and below it, that
    share of it. Rounded UP -- a mission flown by a fraction of an aeroplane is flown by an
    aeroplane -- and zero points are zero planes: a side that has lost the sky to a scale of 0, or
    fields no establishment of that role, puts nothing in the air and therefore burns nothing.

    ⚠ THE AVERAGING IS THE ABSTRACTION, and it is the one this module inherits rather than invents.
    game.state.AirWing is Air Points by arena and role, not a squadron composition sheet (34.72), so
    an Air Point buys the establishment's AVERAGE aeroplane rather than a named one. What changed is
    the denominator: it used to be one hand-picked representative type's rating and it is now the
    real roster's. It dissolves with 34.72, exactly as air.refuel's pooled larder does."""
    if air_points <= 0:
        return 0
    total = points(side, role, scenario)
    if total <= 0:
        raise ValueError(f"[59.3] {side.value} fields no {role} establishment to fly {air_points} "
                         f"Air Points of")
    return -(-air_points * planes(side, role, scenario) // total)      # ceil, in integers


def points_of_planes(side: Side, role: str, count: int, scenario: str = SCENARIO) -> int:
    """The inverse: the Air Points `count` aeroplanes of `side`'s `role` establishment carry.
    Rounded DOWN, so that a force cut to a number of planes never reads back as more Air Points
    than it left with -- the direction that keeps every cap in the engine a cap."""
    if count <= 0:
        return 0
    return count * points(side, role, scenario) // planes(side, role, scenario)


def fuel_per_plane(side: Side, role: str, scenario: str = SCENARIO) -> int:
    """[34.17]/[38.21] The Fuel Points ONE aeroplane of this establishment burns to fly ANY ONE
    mission -- "all Fuel Points are consumed during a mission, regardless of the type or distance"
    -- as the establishment's own average, rounded UP (the same direction planes_flying rounds, and
    the conservative one: an air force is charged for the tank it fills).

    ⚠ AVERAGED OVER THE TYPES THAT PRINT A RATING. One row of [4.44A] does not: the book puts a
    DASH in the Gladiator Mk. II's Fuel column, where the chart's key gives that glyph no meaning at
    all, and it is transcribed as null and raised as an owner ruling on the row itself rather than
    guessed at. It cannot bite today -- 38.24's bill is drawn for the strike and recon roles only
    (engine._REFITTABLE_ROLES) and the Gladiator is a fighter -- and if it ever does, this average
    silently omits thirty-six aeroplanes, which is why it says so here."""
    priced = [m for m in by_role(side, role, scenario) if _chart(m.type)["fuel"] is not None]
    total_planes = sum(m.available for m in priced)
    if total_planes <= 0:
        raise ValueError(f"[34.17] no {side.value} {role} type prints a Fuel Consumption Rating")
    total_fuel = sum(m.available * _chart(m.type)["fuel"] for m in priced)
    return -(-total_fuel // total_planes)                              # ceil, in integers


def mission_capable(side: Side, role: str, scenario: str = SCENARIO) -> bool:
    """[4.44A/b/c] Does EVERY type `side` fields in `role` possess the charted Mission Capability
    that role's missions need? True of the whole transcribed establishment, and asserted by
    tests/test_establishment.py -- which is the check that the role column in the data file is a
    reading of the printed cells and not an opinion about aeroplanes."""
    return all(any(_chart(m.type).get("mission_capability", {}).get(c, "-") not in NO_CAPABILITY
                   for c in CAPABILITY_FOR_ROLE[role])
               for m in by_role(side, role, scenario))


def types(side: Side, role: str, scenario: str = SCENARIO) -> tuple[str, ...]:
    """The chart names `side` fields in `role`, in printed order -- what rule 43's TYPED cases are
    matched against (game.basing.constrained_planes)."""
    return tuple(m.type for m in by_role(side, role, scenario))


def counts_by_type(side: Side, scenario: str = SCENARIO) -> dict[str, int]:
    """The establishment as the book prints it: chart name -> Total Available. The measurement
    read (scripts/measure_air.py) and nothing in the engine reads it."""
    return {m.type: m.available for m in roster(side, scenario)}
