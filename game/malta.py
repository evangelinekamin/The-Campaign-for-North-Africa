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

WHAT THIS MODULE DOES NOT MODEL, each named at its own function and each a data gap rather than a
rule we disagree with -- the first of the three is now struck through, because the data landed:

  * ~~**MALTA'S PLANES ONLY EVER GO DOWN.**~~ **FIXED 2026-07-22.** [34.86], the Commonwealth
    Airplane Reinforcement and Squadron Withdrawal Schedule, is transcribed whole
    (data/air_reinforcements_34_86.json) and 34.81's two caps are applied: no more than a tenth of a
    month's arrival to Malta (34.81A) and never past what its Capacity Levels can operate (34.81B at
    44.14's eighteen a level), and a third bound the book prints outright: the establishment its
    own later scenarios show the island holding at four dates. Malta grows 5 -> 8 -> 14 -> 28
    Capacity Levels and 31 -> 55 -> 74 -> 118 aeroplanes, reached from below at the rate the
    schedule and 44.13's construction die allow, and knocked back by every raid that lands, while
    its TORPEDO arm only falls -- which is the shape [61.34]/[62.36]/[63.37] print for it too
    (12 -> 10 -> 3 -> 6 torpedo aircraft against 31 -> 55 -> 74 -> 118 aeroplanes). See
    reinforcement and repair_ceiling for the two places this is a free choice rather than a
    transcription, and for the fixed point the first version of it collapsed to. STILL NOT WIRED, and
    deliberately: the MAINLAND ninety per cent of that schedule, which waits on [34.87]'s Axis twin
    so that the two air forces grow together or neither does; and 34.85's squadron withdrawals,
    which the Key lets the Commonwealth take from anywhere and which have no mainland ledger to come
    out of.
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

from . import air, basing, calendar, coords, logistics_data
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


def _date(state: GameState) -> tuple[int, int]:
    """The (year, month) this Game-Turn falls in (64.2 via game.calendar). Malta is seeded by the
    campaign scenario alone, so the campaign's calendar is the only clock this island ever reads --
    and it is the same one the [34.86] schedule's own printed Game-Turn labels follow."""
    return calendar.gt_to_month(state.turn)


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


def _is_torpedo(chart_type: str) -> bool:
    """[4.44A] Does this aircraft's chart row carry an "/T"? -- the chart's own test for whether it
    may carry a torpedo at all, and the whole membership rule for Malta's anti-shipping bucket."""
    return chart_type in logistics_data.torpedo_chart_types_4_44a()


def initial_strike() -> int:
    """[60.46] Malta's torpedo arm at the campaign's start: the printed Swordfish row, twelve
    aeroplanes of the island's thirty-one."""
    return sum(r["number"] for r in logistics_data.malta_setup_60_46()["planes"]
               if _is_torpedo(r["type"]))


def strike_establishment(state: GameState) -> int:
    """[60.46]/[34.86]/[4.44A] THE TORPEDO AIRCRAFT still standing on the island, serviceable or not
    -- Malta's anti-shipping arm, and the only aeroplanes on it this engine puts over the convoy
    lane.

    A TRACKED COUNT, NOT A FRACTION, AND THE [34.86] SCHEDULE IS WHY. Until Malta's replacement flow
    was transcribed this was `malta_planes x 12/31` -- the strike share of the September-1940 roster,
    frozen, because the only thing that ever moved the island's establishment was 41.36 killing 10%
    of it and a fraction of a shrinking whole is the same fraction. The moment reinforcements arrive
    that stops being true: the [34.86] schedule sends Malta Hurricanes and Spitfires by the hundred
    and Swordfish never again (it musters none in twenty-eight months), so an island growing at a
    fixed 38.7% anti-shipping share would have manufactured torpedo bombers out of fighters.

    ⚠ THE BUCKET IS THE /T ROWS AND NOTHING ELSE, NARROWED 2026-07-22. It first admitted every type
    the [4.44A] BOMBERS table gives a B capability -- Blenheims, Wellingtons, Baltimores -- and then
    priced each of them at the Swordfish's Torpedo Capacity of 8 with 41.73's +25% on top. Both
    halves of that were wrong against the printed page: the chart gives the Blenheim Mk. IV a
    Bombload of 6 and the Mk. I a 5, so 8 OVER-read the two most numerous arrivals by half; and
    41.73's modifier is a CONDITION -- "at least 50% of the planes are carrying torpedoes" -- which
    a force about 5% torpedo-armed does not meet. [4.44A] carries an "/T" on exactly three
    Commonwealth rows and all three at Torpedo Capacity 8 (Albacore 8/T8, Beaufort Mk. I -/T8,
    Swordfish Mk. I -/T8, read off both tables at 400 dpi), so a bucket of just those three is
    priced at a number printed on every aeroplane in it and satisfies 41.73 by construction.

    THE BOOK'S OWN LATER SCENARIOS ARE THE ACCEPTANCE TEST, and they print this bucket rather than
    the wider one: [60.46] 12 Swordfish of 31, [61.34] 10 Swordfish of 55, [62.36] 3 Swordfish of
    74, [63.37] 3 Swordfish and 3 Albacores of 118. Malta's torpedo arm SHRINKS as the island grows.

    ⚠ WHAT IS GIVEN UP, and it is an under-read in the AXIS'S favour: the Blenheims and Wellingtons
    Malta receives are real bombers that really did fly against convoys, and here they sit in
    `malta_planes` contributing no Bomb Points at all. Pricing them needs the per-type [4.44A] Bomb
    column, and three of those rows print two or three alternative loadouts (Wellington Mk. I "5 or
    23", Mk. IV "6 or 17 or 23") -- a readying CHOICE the Commonwealth Player makes each mission,
    which is the 34.72 Squadron Composition Sheet this engine does not have and an owner ruling when
    it does."""
    return state.malta_strike


def initial_unfit() -> int:
    """[60.46]/[44.16] The Swordfish that are UNSERVICEABLE at the campaign's start: the printed
    roster count less the printed READY count, "12 Swordfish (1 SGSU) (9 ready)" -- three of them.

    44.16 is why the ready column is a magnitude rather than colour: "Planes based on Malta do not
    need fuel or ammo; they are automatically refueled and rearmed each Stage. HOWEVER, THEY MUST BE
    REFIT LIKE ALL OTHER PLANES, USING THE SAME METHOD AS ALL OTHER PLANES." The same method is the
    [38.37] Refit Table (game.air), and until this pass Malta was exempt from it -- the island put
    its whole surviving strike force over the lane every Game-Turn for 111 turns, which is exactly
    the "one wing flies the same points forever" defect block 5.3 exists to kill."""
    return sum(r["number"] - r["ready"] for r in logistics_data.malta_setup_60_46()["planes"]
               if _is_torpedo(r["type"]))


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
      * 60.46/[4.44A] -- and it cannot fly more torpedo aircraft than it has (strike_establishment:
        the /T rows of the chart, which is what an Axis Naval Convoy attack is priced from).
      * 38.31 via 44.16 -- and of those, only the ones that have been REFIT.

    The capacity is spent on the torpedo aircraft FIRST (a Commonwealth player's free choice, and
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
        by 25%, ROUNDING UPWARD." The Key reprints it under this table's own Axis-Naval-Convoys
        heading. THE CONDITION IS TESTED, NOT ASSUMED -- see strike_establishment. The bucket
        priced here admits only the three [4.44A] rows that carry an "/T" (Albacore, Beaufort Mk. I,
        Swordfish Mk. I), so 100% of the planes flying carry torpedoes and the modifier is live on
        every mission by construction. That sentence was an assumption until 2026-07-22, and the
        [34.86] schedule had already made it false: the wider bucket it briefly stood for was about
        5% torpedo-armed, well under 41.73's printed half.

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

    THE ESTABLISHMENT IT IS A PERCENTAGE OF IS NOW THE BOOK'S. [60.32] musters 133 S.M. 79s, 56
    Ca 309s, 24 Ba 88s, 17 S.M. 81s and five more types, and game.roster carries all of them, so the
    raid is sized off 184 real bombers rather than off five representative Stukas -- which is the
    whole of why a Malta raid can now deliver Bomb Points at all. The previous note here said "the
    AXIS's half is live at one one-hundredth" of the island's; that is fixed.

    ⚠⚠ AND THE SECOND TERM OF IT IS NOW A DECISION, NOT A FRACTION -- THE OWNER RULING OF
    2026-07-22. [60.32] prints "no planes start the game in Italy/Sicily" while [44.21]/[44.25]/
    [44.27] make an Italy/Sicily base the precondition for any raid at all, and for two blocks that
    stood open with a percentage (or a null) standing in for it. The owner ruled that [60.32] is a
    SET-UP rule -- a fact about Game-Turn 1, not a repeal of rule 44 -- and that the bridge is the
    one the book prints: a [42.1] TRANSFER MISSION. So this returns rule 43's REQUIREMENT (zero
    while [60.32] musters no German aeroplane) plus the bombers the Axis Player has actually FLOWN
    to Sicily, out of Benghazi or Derna, at 42.13's doubled range and 42.14's fuel. A raid on Malta
    is now something he has to have decided on, one Operations Stage earlier, at the cost of his
    Land Support over the desert. Written out in full at `_owner_ruling_60_32_vs_44_21_ANSWERED` in
    data/malta_44.json."""
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
    # [34.14] the Bomb Points those aeroplanes carry, at the charted Bombload of the establishment
    # they are drawn from ([60.32] -- game.roster, where a bomber is an S.M. 79 far more often than
    # it is anything else, not the single representative type this used to divide by).
    return Raid(level, dice, row[0], row[1], planes, air.points_of_planes(Side.AXIS, "strike", planes))


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
    and it is no longer the only channel by which Malta's air force changes size: [34.86] now
    replaces aeroplanes as well (see reinforcement)."""
    pct = logistics_data.malta_planes_lost_pct_41_36()      # 41.36's 10%, from the data file
    return state.malta_planes * pct * levels // 100


def strike_lost(state: GameState, levels: int) -> int:
    """[41.36] The same 10%-per-level, taken over the anti-shipping arm. "The planes on the ground"
    draws no distinction by type, so the bombs fall across the island's two buckets at one rate --
    which is exactly what the old strike FRACTION did implicitly, now that the strike arm is a
    tracked count that reinforcements can move on its own."""
    pct = logistics_data.malta_planes_lost_pct_41_36()
    return state.malta_strike * pct * levels // 100


def repair_levels(die: int) -> int:
    """[44.5] MALTESE AIR FACILITY CONSTRUCTION TABLE: one die, "the total number of levels of Air
    Facility repaired and/or constructed" -- 1 gives nothing, 2-5 give one, 6 gives two."""
    return logistics_data.malta_construction_table_44_5()[str(die)]


def may_construct(year: int, month: int) -> bool:
    """[60.46] "Construction on increasing the capacity of Malta Air Facilities may begin in
    October, 1940." The campaign opens in the THIRD WEEK of September 1940 (64.2), so the island
    spends its first fortnight -- Game-Turns 1 and 2, and no more -- unable to repair anything the
    Axis knocks off it, and October I is Game-Turn 3.

    That sentence used to be false in the engine even though it was true in the book: this gate
    reads game.calendar, which mapped four Game-Turns to September and so refused construction until
    Game-Turn 5 while this island's own [34.86] reinforcement rows called Game-Turn 3 October. The
    calendar now implements 64.2's two-week September and the two clocks are one."""
    begins = logistics_data.malta_setup_60_46()["construction_begins"]
    return (year, month) >= tuple(begins)


def establishment(year: int, month: int) -> dict:
    """THE BOOK'S OWN SNAPSHOT OF MALTA IN FORCE AT THIS DATE -- `capacity_levels`, total `planes`
    and `torpedo_planes`, the latest of the four printed sets whose date has arrived.

    ([60.46] Sept 1940 5/31/12, [61.34] Mar 1941 8/55/10, [62.36] Nov 1941 14/74/3, [63.37] Oct 1942
    28/118/6.) These are the only statements the book makes about how big the island actually was,
    and between two of them THE EARLIER ONE STANDS -- a step function of printed values, never an
    interpolation, because a number between two printed numbers is one the book does not print.

    THIS IS THE AIMING POINT FOR THE HALF OF MALTA'S GROWTH THE BOOK DOES NOT METER: 44.13 gives the
    Commonwealth a free construction die per facility per Game-Turn with no cost and no limit but
    the standard levels, so an engine aiming anywhere ahead of the printed date would simply BE
    ahead of the book. See `planned_planes` for the other half, which the book meters itself."""
    now = (year, month)
    snaps = logistics_data.malta_establishment_snapshots()
    reached = [s for s in snaps if tuple(s["date"]) <= now]
    return reached[-1] if reached else snaps[0]


def planned_planes(year: int, month: int) -> int:
    """The AEROPLANE establishment the Commonwealth is building Malta toward at this date: the NEXT
    printed snapshot ahead of it, or the last one once they are all behind.

    THE ASYMMETRY WITH `establishment` IS THE BOOK'S, NOT A PREFERENCE. 34.81's airplane flow is
    METERED BY THE BOOK -- a printed 28-row schedule, of which Malta may take at most a tenth of any
    month (34.81A) -- so the aiming point here need only be a CEILING, and the ceiling that lets the
    book's own rate do the work is the establishment he is heading for rather than the one he has
    already passed. Aim at the snapshot already in force and the island freezes between printed
    dates, receiving nothing at all for the twenty-two Game-Turns from September 1940 to March 1941
    and then filling in a burst; aim at the next one and it grows continuously at the schedule's own
    pace. 44.13's construction has no such meter, which is why `establishment` does not do this.

    THE CEILING BARELY BINDS, and that is the evidence it is the right one: run the schedule out
    with no Axis raid at all and 34.81A's own tenth carries Malta to 58 aeroplanes by the end of
    March 1941 against [61.34]'s printed 55. The book's rate and the book's establishment agree to
    within a handful of aircraft without either being fitted to the other."""
    now = (year, month)
    snaps = logistics_data.malta_establishment_snapshots()
    ahead = [s for s in snaps if tuple(s["date"]) > now]
    return (ahead[0] if ahead else snaps[-1])["planes"]


def structural_capacity(state: GameState) -> int:
    """[44.13]/[36.12] "The standard levels" -- the total Capacity Level Malta's six printed
    facilities can stand at, which is the absolute ceiling 44.13's construction table builds
    toward and the 28 the book's [63.37] October-1942 set-up reaches."""
    return sum(f.max_level for f in facilities(state))


def repair_ceiling(state: GameState) -> int:
    """[44.13] The total Capacity Level the Commonwealth builds Malta UP TO -- his half of the
    island's growth, and the number the [44.5] construction table is rolled toward.

    44.13 sets the law and leaves the decision: capacity "MAY be increased -- up to the standard
    levels -- by using the Maltese Air Facility Construction Table", one roll per facility per
    Game-Turn, and "NO SUPPLIES NEED BE EXPENDED". Nothing in the book meters that beyond the
    player's judgement, so an engine that simply ran the table would stand at twenty-eight levels by
    Game-Turn five and hold there for the rest of the war.

    OUR ASSIGNMENT OF THAT FREE CHOICE: THE COMMONWEALTH BUILDS MALTA TO THE SIZE THE BOOK PRINTS
    FOR THE DATE -- five Capacity Levels from [60.46], eight from March 1941 ([61.34]), fourteen
    from November 1941 ([62.36]), twenty-eight from October 1942 ([63.37]), never past the standard
    levels the six printed facilities can stand at. Every number is one the book prints and the
    island still has to ROLL for it, one die per facility per Game-Turn, so it climbs at 44.13's
    rate and every raid that lands knocks it back down.

    ⚠ WHAT THIS REPLACES, RECORDED BECAUSE IT WAS PRESENTED AS A LIVE MECHANISM AND WAS NOT ONE.
    The first version read "the Commonwealth builds the capacity his aeroplanes need" --
    max(printed 5, ceil(malta_planes / 18)) -- while reinforcement admitted planes only up to
    18 x capacity. The two capped each other into a FIXED POINT: planes could never exceed
    18 x capacity, so ceil(planes / 18) could never exceed capacity, so the ceiling never rose above
    [60.46]'s five and Malta was pinned at 5 levels and 90 aeroplanes for the whole war --
    numerically identical to the invented 5-level ceiling the commit said it had deleted. The
    growth branch was unreachable from any campaign state and the tests that exercised it did so by
    hand-setting `malta_planes` to values the engine could not produce."""
    return min(structural_capacity(state), establishment(*_date(state))["capacity_levels"])


# --- [34.86] / [34.81] MALTA'S REPLACEMENT FLOW -------------------------------------------------

class Reinforcement(NamedTuple):
    """[34.86] one Game-Turn's Commonwealth airplane reinforcement to Malta: `planes` aeroplanes
    of which `strike` are torpedo-armed, out of the `allotted` the month's 34.81A ceiling gave the
    island (`month_total` being the month's whole arrival) and against the `headroom` the island's
    capacity (34.81B) and the book's own establishment for the date leave between them."""
    planes: int
    strike: int
    allotted: int
    month_total: int
    headroom: int


def _schedule() -> list:
    return logistics_data.cw_air_reinforcements_34_86()


def month_row(turn: int) -> "dict | None":
    """The [34.86] row this Game-Turn arrives on, or None for a Game-Turn the schedule names at
    all. The 1940 rows name a single Game-Turn ("Sept IV (GT 2)"), the rest a month's four
    ("Jan (GT 15...18)"), and both are carried as an explicit `turns` list."""
    return next((row for row in _schedule() if turn in row["turns"]), None)


def _share(total: int, n: int, i: int) -> int:
    """[34.84] "The planes must be DIVIDED AMONGST THE WEEKS AS EVENLY AS POSSIBLE" -- share `i` of
    `n`, remainder to the earliest weeks. The same convention game.oob uses for every other charted
    allotment split over a set the book leaves the player to choose."""
    return total // n + (1 if i < total % n else 0)


def reinforcement(state: GameState, turn: int) -> Reinforcement:
    """[34.86]/[34.81] THE AEROPLANES MALTA RECEIVES THIS GAME-TURN -- the faucet that turns the
    island from a stock that only ever went down into a place that gets stronger as the war does.

        34.81A "NO MORE THAN 10% OF A MONTH'S AIRPLANE REINFORCEMENTS MAY BE SENT TO MALTA."
        34.81B "No airplane reinforcements may be sent to a Malta/N African Off-map air facility
                IN EXCESS OF THE FACILITY'S CURRENT SQUADRON CAPACITY."
        34.84  "Airplane reinforcements arrive in the Naval Convoy Arrival Phase... The planes must
                be divided amongst the weeks as evenly as possible."
        44.14  "Each level of air facility can handle UP TO 18 PLANES of any type."

    Both caps are the book's and both are applied: the month's allotment is a tenth of the month's
    printed arrival, rounded DOWN (34.81A is a ceiling, and a ceiling rounded up is not one), and
    what lands is bounded by the aeroplanes the island's current Capacity Levels can operate.

    ...AND BY THE ESTABLISHMENT THE BOOK PRINTS FOR THE DATE, which is the third bound and the one
    that usually bites. 34.81 leaves the DIVISION of a month's arrivals entirely to the Commonwealth
    Player -- 34.81A's tenth of this schedule is 669 aeroplanes over the campaign, onto an island
    the book's own four scenarios never show holding more than 118 -- so the free choice needs an
    aiming point, and `planned_planes` takes the book's own: the island is built toward the NEXT
    establishment the book prints for it -- 55 until March 1941, then 74, then 118. See
    repair_ceiling for the same assignment made over Capacity Levels (where the book meters nothing,
    so it aims at the snapshot already in force instead) and for the no-op it replaced.

    THE COMPOSITION IS PRO RATA OVER THE MONTH'S OWN TYPES, which is the most neutral exercise of
    34.81's "in any distribution the Commonwealth Player chooses" available: Malta's share of a
    month looks like that month. The torpedo bucket takes the FLOOR of its proportional share (the
    remainder goes to the rest), so the arm that sets the island's Bomb Points is never rounded up.
    Where the headroom bites, the torpedo aircraft are landed FIRST -- the same free choice, made
    the same way and for the same reason as strike_planes' spending of the 44.14 capacity: 44.0's
    Malta exists to hinder the convoys.

    ⚠ WHAT THE FLOOR ACTUALLY DOES TO THE TORPEDO ARM, STATED PLAINLY BECAUSE IT IS AN EDGE AND NOT
    A ROUNDING. This schedule musters 116 torpedo aircraft against 6,691 in all -- 1.7% -- and they
    arrive a handful at a time (12 Albacores in a month of 205, 7 Beauforts in one of 217). A tenth
    of that, floored, is ZERO in twelve of the sixteen months that carry any and one or two in the
    rest: SIX aeroplanes over the whole war against a true pro-rata share of about twelve. And
    because the island is usually sitting at the establishment it is building toward, the headroom
    is nil on most of those months and the six do not land either -- measured over the full campaign
    on seed 4, Malta receives NO replacement torpedo aircraft at all and its arm only ever decays
    under 41.36.

    THAT UNDER-READ IS KEPT, AND THE BOOK'S OWN SNAPSHOTS ARE WHY: [60.46] 12 torpedo aircraft,
    [61.34] 10, [62.36] 3, [63.37] 6. Malta's torpedo arm FALLS through the war in the book even as
    the island grows 31 -> 55 -> 74 -> 118 aeroplanes, and a decaying twelve tracks 10 and 3 closely;
    what it will not reproduce is [63.37]'s small recovery to 6. The alternative -- rounding the arm
    UP, or landing the month's torpedo aircraft on Malta first -- would put Bomb Points over the
    convoy lane that no printed number supports, and 41.73's +25% multiplies every one of them. An
    under-read here runs in the AXIS's favour, which is the direction a flagged edge should run.

    ⚠ THE ARRIVALS ARE REFITTED. [59.32] makes a scenario's planes arrive fuelled and armed and
    38.31 makes every plane refitted until it flies, and the schedule prints no readiness column at
    all (unlike [60.46]/[61.34]/[62.36], which do) -- so a new aeroplane joins the establishment
    without joining `malta_unfit`. The engine's own [38.37] governor then wears it down like every
    other."""
    row = month_row(turn)
    if row is None or not in_play(state):
        return Reinforcement(0, 0, 0, 0, 0)
    total = row["total"]
    allotted = total * logistics_data.malta_share_pct_34_81a() // 100   # 34.81A, rounded DOWN
    torpedo_total = sum(p["number"] for p in row["planes"] if _is_torpedo(p["chart_type"]))
    strike_month = allotted * torpedo_total // total         # pro rata, the torpedo arm floored
    turns = row["turns"]
    i = turns.index(turn)
    strike = _share(strike_month, len(turns), i)             # 34.84: evenly amongst the weeks
    other = _share(allotted - strike_month, len(turns), i)
    # The date is read off the ARGUMENT, not off state.turn: this function is asked what a given
    # Game-Turn brings and the caller may ask about one the state has not reached.
    room = max(0, min(logistics_data.malta_planes_per_level_44_14() * capacity(state),
                      planned_planes(*calendar.gt_to_month(turn))) - state.malta_planes)
    strike = min(strike, room)                               # 44.0: the torpedo arm first
    other = min(other, room - strike)
    return Reinforcement(strike + other, strike, allotted, total, room)


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


