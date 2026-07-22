"""[44.0] MALTA -- the island as a PLACE WITH HEALTH, and the two-way duel that makes it one.

  44.0 COMMENTARY: "The importance of the tiny island of Malta to the campaign in North Africa
    cannot be understated. Lying, as it does, astride the Axis Shipping Lanes, it provided the
    Commonwealth with an excellent position from which to hinder the transport of Axis supplies
    and reinforcement. ... In retaliation, the Axis may attempt to reduce the effectiveness of
    Malta by bombing the island."

WHAT THIS REPLACES, AND WHY IT IS THE HEADLINE OF PHASE 5. Until this module the engine's Malta
was `game.scenario._malta_bomb_points(gt)` -- a hand-typed calendar (100 / 200 / 300 / 500 / 0 /
150 / 400 Bomb Points by month) with NO producer, NO Axis input and NO feedback. Measured with the
dice held identical it was worth 95-320 Victory Points and flipped the winner on seed 7: the single
largest determinant of who won this campaign was a constant we invented (invention I2 of the port
plan). Rule 44 is the loop that constant was crudely approximating, and both halves of it are here:

    Maltese air-facility LEVELS (44.12/44.13, six printed facilities, 28 levels maximum)
        |  18 planes per level (44.14)
        v
    the strike planes that reach the Axis convoy lane -- 60.46's twelve Swordfish (nine of them
    READY at the campaign's start, the rest refit on the [38.37] table like every other plane,
    44.16), each carrying a Torpedo Capacity of 8 ([4.44A]; it may not carry bombs at all)
        |  the [41.5] table's BOMB POINTS index -- the chart's footnote (a) sends a torpedo-armed
        |  plane attacking an Axis Naval Convoy to that row and away from the Torpedo row, 41.74
        |  counts the torpedo "as normal bombs", and 41.73 adds 25% for a torpedo-armed strike
        v
    2d6 -> the percentage of the Axis convoy's cargo destroyed (41.66/41.67)

    ...and back the other way:

    the Axis picks an Availability Level I-IV out of a FINITE budget (44.23 / [44.41] campaign
    row via 64.52: I unlimited, II x25 Game-Turns, III x12, IV x12)
        |  [44.42], 2d6: what percentage of the Italy/Sicily-based force flies (44.25)
        v
    the raid bombs a Maltese air facility (44.21/44.24) on the [41.5] Airfields row
        |  41.36: "the result is the number of capacity levels that facility is reduced. In
        |  addition, FOR EVERY LEVEL DESTROYED, REMOVE 10% OF THE PLANES ON THE GROUND"
        v
    fewer levels AND fewer planes -> fewer Bomb Points -> more Axis supply lands
        |
        v
    the Commonwealth repairs on the [44.5] table, one roll per facility per Game-Turn (44.13)

THE NUMBER THE WHOLE LOOP TURNS ON -- what a torpedo is WORTH in Bomb Points when the plane
carrying it may not carry bombs at all -- WAS RULED BY THE OWNER ON 2026-07-21 and is no longer an
open judgement call: the [4.44A] Swordfish row does read "-/T8" (PDF p.113, verified), and the
[41.5] Key prints "if at least 50% of the planes attacking an Axis Naval Convoy are armed with
Torpedos, INCREASE THE TOTAL BOMB POINTS BY 25%" (PDF p.108) -- a quarter added to nothing is
nothing, so the chart's own Key presupposes that a torpedo plane contributes Bomb Points, and 41.74
supplies the conversion. The evidence is written out in full at bomb_points() and in
data/malta_44.json. Behaviour is unchanged; the reading is now the book's, not a convenience.

THE THREE THINGS THIS MODULE DOES NOT MODEL, each named at its own function and each a data gap
rather than a rule we disagree with:

  * **MALTA'S PLANES ONLY EVER GO DOWN.** 34.81A caps Malta's replacement flow ("no more than 10%
    of a month's airplane reinforcements may be sent to Malta") off the [34.86] Commonwealth
    Airplane Reinforcement Schedule, which is untranscribed. So our Malta starts at its printed
    September-1940 establishment (60.46) and is only ever ground down. The book's Malta grows from
    31 planes to 118 and from 5 capacity levels to 28 -- the four printed scenario snapshots are
    recorded in data/malta_44.json as the acceptance test for whoever transcribes [34.86].
  * **NOTHING DEFENDS THE ISLAND.** 45.0 air-to-air and 46.0 flak are deferred by the port plan, so
    Malta's 19 fighters and 17 AA Points (60.46) are transcribed and unused, and every Axis raid
    arrives unopposed. That makes the Axis raid STRONGER than the book's, not weaker.
  * **THE RAID COSTS THE AXIS NO AIRFRAMES.** Nothing in this engine shoots an aeroplane down (45.0
    air-to-air and 46.0 flak are deferred), so 44.28's whole apparatus -- the pro-rata split of
    losses between planes in play and planes that are not -- has nothing to split. What the raid
    DOES now cost him is sorties: 39.19 and rule 43 arrived in block 5.5 (game.basing), so the
    Mediterranean-based bomber force is off the African battlefield and every African bomber he adds
    to a raid (44.21/44.25/44.27) flies nothing over the desert for the rest of that Game-Turn.
"""
from __future__ import annotations

from typing import NamedTuple

from . import air, basing, coords, logistics_data
from .events import Side
from .state import AirFacility, GameState

# Every Maltese air facility carries this id prefix, and that is how the engine knows the island
# from the mainland. It is not cosmetic: rule 44 applies to Malta and to nothing else -- 44.14's
# 18-planes-per-level replaces the SGSU (35.17) that every African field needs, 44.16 exempts these
# planes from fuel and ammunition, and 44.5 is a construction table no other facility may use.
PREFIX = "Malta/"

# [44.41]'s four columns, in the chart's own order. The Roman numerals ARE the keys, in the data
# file and here, because they are what the book calls them.
LEVELS: tuple[str, ...] = ("I", "II", "III", "IV")

# [44.25] "If, at any time, the Axis Player does not wish to bomb Malta HE IS CONSIDERED TO HAVE
# USED LEVEL I (which is unlimited)." So there is no such thing as not consulting the chart, and
# Level I is the do-nothing choice as well as the cheapest raid.
DEFAULT_LEVEL = "I"


def is_malta(facility: AirFacility) -> bool:
    """Is this air facility on Malta (44.12) rather than on the African mainland?"""
    return facility.id.startswith(PREFIX)


def facilities(state: GameState) -> tuple[AirFacility, ...]:
    """The Maltese air facilities, id-ordered (deterministic). Empty in every scenario that does
    not seed the island, which is what keeps them all byte-identical."""
    return tuple(sorted((f for f in state.air_facilities if is_malta(f)), key=lambda f: f.id))


def in_play(state: GameState) -> bool:
    """Is Malta a place in this scenario at all?"""
    return bool(facilities(state))


def capacity(state: GameState) -> int:
    """[44.13]/[36.14] Malta's CURRENT total Capacity Level, summed over its facilities -- the
    island's health, the number both halves of the loop turn on."""
    return sum(f.level for f in facilities(state))


def seed_facilities(levels: int) -> list[AirFacility]:
    """[44.12]/[60.46] The island as the game-map prints it, opened at the scenario's initial total
    capacity.

    44.12 makes these permanent installations rather than counters ("printed directly on the
    game-map... they are permanent and may never be moved. No further air facilities may be built
    on Malta"), so their SET is fixed and only their levels move. 60.46 gives the campaign's total:
    "The Malta bases have an initial capacity of five SGSU's. THESE MAY BE SPREAD AMONGST THE MALTA
    FACILITIES AS THE PLAYER WISHES."

    That last clause is a free choice, and ours is: round-robin over the AIRFIELDS first, then the
    flying-boat facilities. Deterministic (id order within each group), and it is the choice a
    Commonwealth player makes for a reason -- 60.46's roster is 31 land planes and not one flying
    boat, so capacity put in the basin at Kalafrana or the alighting area at Valetta would be
    capacity no aeroplane on the island could use. Spreading rather than concentrating is likewise
    deliberate and likewise the player's: a raid that takes two levels off one field costs less when
    the island's five levels sit on four airfields than when they sit on one.

    A facility opens at level 0 rather than at its charted maximum -- which is the one place Malta
    differs from oob.air_facilities, and it is 44.13's doing: on the mainland a scenario's set-up
    facility is an intact one, while on Malta the scenario prints the CAPACITY ITSELF (five of a
    possible twenty-eight) and the rest is what the Commonwealth has yet to build."""
    printed = logistics_data.malta_facilities_44_12()
    seeded = [AirFacility(id=PREFIX + rec["name"], side=Side.ALLIED,
                          hex=coords.to_axial(coords.parse(rec["hex"])),
                          kind=rec["kind"], level=0, max_level=rec["max_level"])
              for rec in sorted(printed, key=lambda r: r["name"])]
    given = {f.id: 0 for f in seeded}
    remaining = levels
    for group in ([f for f in seeded if f.kind == air.AIRFIELD],
                  [f for f in seeded if f.kind != air.AIRFIELD]):
        while remaining > 0 and any(given[f.id] < f.max_level for f in group):
            for f in group:
                if remaining <= 0:
                    break
                if given[f.id] < f.max_level:
                    given[f.id] += 1
                    remaining -= 1
    return [AirFacility(f.id, f.side, f.hex, f.kind, given[f.id], f.max_level) for f in seeded]


def initial_planes() -> int:
    """[60.46] The number of aeroplanes on Malta at the campaign's start -- all types, because
    41.36's 10% falls on "the planes on the ground" without regard to type."""
    return sum(row["number"] for row in logistics_data.malta_setup_60_46()["planes"])


def _strike_fraction() -> float:
    """[60.46] The share of Malta's establishment that is its anti-shipping arm -- twelve Swordfish
    of thirty-one aeroplanes. Held as a FRACTION, not a count, because 41.36 kills planes off the
    island as a whole and the composition of what survives is not something the book tracks at this
    grain; the alternative (a per-type ledger) waits on 34.72's Squadron Composition Sheet."""
    setup = logistics_data.malta_setup_60_46()
    strike = sum(r["number"] for r in setup["planes"] if r["role"] == "strike")
    return strike / sum(r["number"] for r in setup["planes"])


def strike_establishment(state: GameState) -> int:
    """[60.46] The anti-shipping aircraft still standing on the island -- the strike share of what
    has survived the Axis raids, whether or not it is serviceable."""
    return int(state.malta_planes * _strike_fraction())


def initial_unfit() -> int:
    """[60.46]/[44.16] The Swordfish that are UNSERVICEABLE at the campaign's start: the printed
    roster count less the printed READY count, "12 Swordfish (1 SGSU) (9 ready)" -- three of them.

    44.16 is why the ready column is a magnitude rather than colour: "Planes based on Malta do not
    need fuel or ammo; they are automatically refueled and rearmed each Stage. HOWEVER, THEY MUST BE
    REFIT LIKE ALL OTHER PLANES, USING THE SAME METHOD AS ALL OTHER PLANES." The same method is the
    [38.37] Refit Table (game.air), and until this pass Malta was exempt from it -- the island put
    its whole surviving strike force over the lane every Game-Turn for 111 turns, which is exactly
    the "one wing flies the same points forever" defect block 5.3 exists to kill."""
    row = next(r for r in logistics_data.malta_setup_60_46()["planes"] if r["role"] == "strike")
    return row["number"] - row["ready"]


def ready_strike(state: GameState) -> int:
    """[38.31] The anti-shipping aircraft that MAY fly: the establishment less the unserviceable.
    "In order to fly any mission other than a transfer, a plane must be refitted."

    state.malta_unfit can never exceed the establishment -- 41.36's bombs fall on the unserviceable
    machines too, so MALTA_PLANES_LOST carries the ledger down with the aeroplanes -- and
    invariants._check_malta_unfit fails loud if it ever does, rather than a max() here quietly
    papering over a rule that had come unstuck."""
    return strike_establishment(state) - state.malta_unfit


def refitted(undergoing: int, die: int) -> int:
    """[38.34]/[38.37] How many of `undergoing` unserviceable Swordfish one die refits, rounding up.

    THE DIE IS UNMODIFIED, and that is 44.14 rather than a favour: [38.35]'s serviceability
    modifiers are the refitting SGSU's (+2 Italian, +1 German, none Commonwealth) and "the
    Commonwealth Player does not need -- nor does he use -- SGSU's on Malta". So the island rolls
    the bare Commonwealth row of the same table every other squadron reads.

    ⚠ FLAGGED: [38.36]'s Stores Point per refit attempt is NOT charged here. It is charged for
    every other squadron in the engine (engine._refit_stores_dump), but it attaches to the SGSU
    attempting the refit -- the counter 44.14 removes from this island -- and Malta has no supply
    dump on the map at all: 44.16 exempts its planes from fuel and ammunition and no rule in 44
    puts Stores on the island. Charging one would mean inventing a Maltese dump."""
    return air.refitted_planes(undergoing, die)


def strike_planes(state: GameState) -> int:
    """[44.14]/[60.46]/[38.31] How many of Malta's aeroplanes fly the convoy lane this Game-Turn.

    Three limits, and the rule each comes from:
      * 44.14 -- "each level of air facility can handle up to 18 planes of any type", so the island
        can operate at most 18 x its current total Capacity Level. AN ISLAND AT ZERO CAPACITY FLIES
        NOTHING, which is the Axis's whole objective and the thing the invented calendar used to
        hand him free for four months of 1942.
      * 60.46 -- and it cannot fly more anti-shipping aircraft than it has. The strike share of the
        surviving establishment, from the printed roster.
      * 38.31 via 44.16 -- and of those, only the ones that have been REFIT.

    The capacity is spent on the strike aircraft FIRST (a Commonwealth player's free choice, and
    the obvious one -- 44.0's Malta exists to hinder the convoys). At the campaign's five levels
    that is moot: 90 slots against 31 aeroplanes. It binds when the Axis has bombed the island down
    to one level, and it bites absolutely at zero."""
    if not in_play(state):
        return 0
    operable = logistics_data.malta_planes_per_level_44_14() * capacity(state)
    return min(ready_strike(state), operable)


def bomb_points(state: GameState) -> int:
    """[41.66]/[41.73]/[41.74] The BOMB POINTS Malta puts over the Axis convoy lane this Game-Turn.

    THE COLUMN IS THE BOMB POINTS COLUMN, AND THE CHART ITSELF SAYS SO. Footnote (a) of the [41.5]
    table -- the superscript on its "Torpedo Points" header row (PDF p.107), spelled out in the Key
    on the facing page (PDF p.108) and read there with eyes -- is verbatim: "Use only when attacking
    ships of the Commonwealth Fleet. Attacks consisting of Bomb and Torpedo Points are performed as
    two attacks. ATTACKS BY PLANES ARMED WITH TORPEDOS AGAINST PORTS OR AXIS NAVAL CONVOYS ARE
    CARRIED OUT USING THE BOMB POINTS ROW (see Case 41.7)." Commonwealth Swordfish against an Axis
    Naval Convoy is precisely the case the footnote excludes from the Torpedo scale, and 41.72
    confirms the scope from the other side ("this refers to AXIS PLANE VS. COMMONWEALTH FLEET").

    Two magnitudes then enter that column:
      * 41.74 -- "Torpedoes may be used against port facilities, but AS SUCH COUNT AS NORMAL BOMBS",
        which is the only conversion the book prints: the Torpedo Capacity of 8 on the Swordfish's
        [4.44A] row IS its Bomb Points for this attack.
      * 41.73 -- "When Commonwealth planes fly against Axis convoys and AT LEAST 50% OF THE PLANES
        ARE CARRYING TORPEDOES, in determining the level (Case 41.66), increase the bombing tonnage
        by 25%, ROUNDING UPWARD." Malta's strike is 100% torpedo-armed, so the modifier is always
        live; the Key reprints it under this table's own Axis-Naval-Convoys heading.

    OWNER RULING MADE 2026-07-21, WRITTEN OUT IN FULL AT initial_setup_60_46.strike_weapon.
    _owner_ruling_settled IN data/malta_44.json: THE TORPEDO READING IS CONFIRMED. Read 41.66
    strictly and a plane whose Bombload Capacity is "-" totals ZERO Bomb Points; 0 x 1.25 = 0 falls
    below the table's [1..20] floor, and Malta's only 1940 anti-shipping aircraft could not scratch
    a convoy for the whole war -- against 41.71 ("torpedoes... are effective against ships") and
    against 44.0's entire premise. THE CHART SETTLES IT FROM ITS OWN KEY: the [41.5] Key (PDF p.108,
    read with eyes) prints "if at least 50% of the planes attacking an Axis Naval Convoy are armed
    with Torpedos, increase the total Bomb Points by 25%", and a 25% increase of zero is meaningless
    -- so a torpedo-armed plane MUST contribute Bomb Points, and 41.74 ("as such count as normal
    bombs") is the only conversion the book prints. The owner verified the "-/T8" reading on
    [4.44A] (PDF p.113) as well. So this is a ruled reading of two printed values, not a guess."""
    weapon = logistics_data.malta_setup_60_46()["strike_weapon"]
    points = strike_planes(state) * weapon["points_per_plane"]     # 41.74: the torpedo as bombs
    bonus = 100 + weapon["torpedo_increase_pct_41_73"]             # 41.73: +25%, rounding UP
    return -(-points * bonus // 100)


def interdiction_points(state: GameState, order) -> int:
    """The [41.5] Bomb-Point column an InterdictionOrder is resolved on -- the ONE place the
    engine, the naval staff seat and the event log all read a convoy attack's strength from.

    A plain scheduled order carries its own Bomb Points. A MALTA-sourced one (rule 44) has none to
    carry, because the strength of the Maltese effort is a LIVE fact about the island: its current
    Capacity Levels, 18 planes per level (44.14), the strike aircraft that survive and have been
    refit, and the torpedoes they carry counted as bombs (41.74) with 41.73's 25%. This one branch
    is the whole difference between a Malta that is a rule and the calendar it replaced."""
    return bomb_points(state) if order.source == "malta" else order.bomb_points


# --- [44.2] / [44.4] THE AXIS RAID --------------------------------------------------------------

def budget(scenario: str = "campaign_64") -> dict:
    """[44.41]/[64.52] The scenario's Availability Level budget: Level -> the number of Game-Turns
    it may be used, None for unlimited. The campaign row is I unlimited / II 25 / III 12 / IV 12."""
    return logistics_data.malta_commitment_44_41(scenario)


def spent(state: GameState, level: str) -> int:
    """How many Game-Turns of Axis Strategic Bombardment of Malta `level` has already been used
    for (44.23). Counted for a raid the Axis CANCELS as well -- 44.29: "The Axis Player may, after
    rolling on the Table, decide not to raid. The raid is cancelled, but HE STILL HAS USED THE
    TABLE HE ROLLED FOR ONCE -- regardless of whether he cancels or not." """
    return state.malta_raids.get(level, 0)


def available(state: GameState, level: str, scenario: str = "campaign_64") -> bool:
    """[44.23] "No Availability Level may ever be used more Game-Turns than it is listed as
    available." """
    cap = budget(scenario).get(level, 0)
    if cap is None:
        return True                                  # the chart's U
    return spent(state, level) < cap


def italy_sicily_planes(state: GameState, turn: int) -> int:
    """[43.12]/[43.13] The Axis bomber force based in Italy/Sicily -- the force [44.42]'s two
    percentages are percentages OF, and the reason a slice of rule 43 had to arrive with rule 44.

    THE WHOLE OF RULE 43 NOW LIVES IN game.basing (Phase 5.5), and this function is the one line
    that reads it. The raid's SIZING and the battlefield's DEDUCTION are the SAME NUMBER, subtracted
    once: basing.africa_planes is the squadron less exactly what this returns (plus Crete). That was
    not a tidying -- while the two halves ran on different readings, three quarters of the bomber arm
    raided Malta in the Strategic Air Phase and all of it bombed Tobruk in the three Operations Stages
    of the same Game-Turn, which is 35 aeroplanes out of a force of 20.

    ⚠ THE ESTABLISHMENT IT IS A PERCENTAGE OF IS OUR PROXY, NOT THE BOOK'S, and the flag is argued
    in full in game.basing: the campaign seeds the Axis two dozen strike Air Points -- five Ju. 87B
    on the 34.14 Bombload bridge -- where [60.32] musters 133 SM 79s, 56 Ca 309s, 24 Ba 88s and 17 SM
    81s, and 43.11/43.13 name GERMAN HEAVY BOMBER types this engine does not field separately (the
    owner ruling, at basing.typed_requirement_applies; 43.12's untyped sentence, which is what sizes
    this number before Game-Turn 35, needs no ruling at all).
    Until [34.6]/[59.3] is transcribed the Axis raid is a shadow of the book's raid, and the honest
    reading of any Malta measurement taken today is that the ISLAND'S half of the loop is live at
    the book's scale and the AXIS's half is live at one one-hundredth of it."""
    return basing.italy_sicily_planes(state, turn)


class Raid(NamedTuple):
    """[44.24]-[44.28] one Game-Turn's Axis strategic raid on Malta: the Availability `level`
    spent, the [44.42] `dice` total, the two percentages it printed, the `planes` that flew (0 = the
    chart's na, no forces available) and the `bomb_points` they carry into the [41.5] Airfields
    row."""
    level: str
    dice: int
    in_play_pct: int
    strategic_pct: int
    planes: int
    bomb_points: int


def raid(state: GameState, level: str, dice: int, turn: int) -> Raid:
    """[44.25]/[44.42] Resolve how big this Game-Turn's raid is, given the Availability Level the
    Axis committed and the two dice he rolled.

        44.25 "To compute how many -- and what types -- of planes he may use, the Axis Player uses
               the Axis Malta Table (44.42). ... the Table shows the Axis Player how many of his
               planes in the game, but in Italy/Sicily, he may use PLUS how many planes not in the
               game (for normal use) but available nonetheless that may be added to this total."
        [44.42] key "rounding fractions down (e.g., 200 = 200%, or double the number of each type
               of plane in play)."

    THIS IS THE MEDITERRANEAN HALF OF THE RAID ONLY. 44.25's third term -- "he may then add in --
    up to the maximums he gets from the Table -- ANY PLANES HE WISHES FROM AFRICA", bounded by
    44.27 -- is the Axis Player's decision and is taken in engine._malta_africa (block 5.5), which
    adds its Bomb Points to `bomb_points` before the [41.5] roll and books the aeroplanes out of the
    desert for the rest of the Game-Turn (39.19). 44.27's per-TYPE cap is enforced at the grain we
    have: one abstract bomber type, so the cap is the table's whole plane count.

    STILL ABSENT: 44.28's pro-rata split of losses between planes that are in play and planes that
    are not -- which cannot matter until something shoots an aeroplane down (45/46, deferred; the
    debt is written out in full in game.basing)."""
    row = logistics_data.malta_availability_44_42()[str(dice)][level]
    if row is None:                                  # [44.42] na -- no forces available this turn
        return Raid(level, dice, 0, 0, 0, 0)
    based = italy_sicily_planes(state, turn)
    planes = based * row[0] // 100 + based * row[1] // 100
    bombload = logistics_data.aircraft_characteristics_4_44()[
        air.REPRESENTATIVE_AIRCRAFT[(Side.AXIS, "strike")]]["bombload"]
    return Raid(level, dice, row[0], row[1], planes, planes * bombload)


def raid_target(state: GameState) -> "AirFacility | None":
    """[44.24] "He assigns each squadron to a specific airfield in Malta." Ours goes to the
    facility standing at the highest Capacity Level (id order breaks the tie) -- the field with the
    most to lose, and the one 41.36's 10%-of-the-planes-on-the-ground clause pays best against.
    None when the island is already flat: 41.36 has nothing to reduce."""
    live = sorted((f for f in facilities(state) if f.level > 0), key=lambda f: (-f.level, f.id))
    return live[0] if live else None


def planes_lost(state: GameState, levels: int) -> int:
    """[41.36] "In addition, for every level destroyed, REMOVE 10% OF THE PLANES ON THE GROUND
    (e.g., 2 levels, 20% planes), ROUNDED DOWN."

    Taken over the island's whole establishment rather than over one field's share of it, because
    our Malta has no plane-to-field assignment to take a share of (34.72's Squadron Composition
    Sheet again). That is the one place this reading is more generous to the Axis than the book,
    and it is also the only channel by which Malta's air force can be permanently reduced."""
    pct = logistics_data.malta_planes_lost_pct_41_36()      # 41.36's 10%, from the data file
    return state.malta_planes * pct * levels // 100


def repair_levels(die: int) -> int:
    """[44.5] MALTESE AIR FACILITY CONSTRUCTION TABLE: one die, "the total number of levels of Air
    Facility repaired and/or constructed" -- 1 gives nothing, 2-5 give one, 6 gives two."""
    return logistics_data.malta_construction_table_44_5()[str(die)]


def may_construct(year: int, month: int) -> bool:
    """[60.46] "Construction on increasing the capacity of Malta Air Facilities may begin in
    October, 1940." The campaign opens in the third week of September 1940, so the island spends
    its first fortnight unable to repair anything the Axis knocks off it."""
    begins = logistics_data.malta_setup_60_46()["construction_begins"]
    return (year, month) >= tuple(begins)


def repair_ceiling(state: GameState) -> int:
    """The total Capacity Level the Commonwealth repairs Malta back UP TO, and no further.

    ⚠ THIS IS THE ONE PLACE RULE 44 IS DELIBERATELY UNDER-BUILT, AND THE REASON IS THAT THE
    ALTERNATIVE WOULD BE A SECOND INVENTED CALENDAR. 44.13 lets the Commonwealth build capacity
    "up to the standard levels" -- twenty-eight of them -- at one roll per facility per Game-Turn,
    which is about six levels a turn: unchecked, our Malta would stand at its structural maximum by
    Game-Turn five and stay there for the rest of the war. The book's own scenarios say that is not
    what happens (5 levels in September 1940, 8 in March 1941, 14 in November 1941), because in the
    book capacity is worth building only for planes you have, and Malta's planes arrive on the
    untranscribed [34.86] schedule. So the Commonwealth REPAIRS bomb damage back to the
    establishment the scenario printed and does not build past it -- a strict subset of what 44.13
    permits (its own table is titled "repaired and/or constructed"), chosen because it needs no
    number we do not have. When [34.86] is transcribed, this ceiling comes off and the growth
    becomes the Commonwealth's decision, which is what the book intends."""
    return logistics_data.malta_setup_60_46()["capacity_levels"]


def repairable(state: GameState) -> tuple[AirFacility, ...]:
    """[44.13] The Maltese facilities that may take a [44.5] roll this Game-Turn, id-ordered: those
    standing below both their own charted maximum (36.12/36.3/36.4) and the island's repair ceiling.

    Every facility gets its own roll in the book -- "once each Game-Turn FOR EACH air facility on
    Malta" -- so a facility already at its ceiling is skipped rather than rolled for and discarded.
    That is a DIE NOT DRAWN, which is exactly the conditional-draw hazard game.dice exists to
    contain: rule 44's dice come off Malta's own stream and move nothing else in the engine."""
    if capacity(state) >= repair_ceiling(state):
        return ()
    return tuple(f for f in facilities(state) if f.level < f.max_level)


