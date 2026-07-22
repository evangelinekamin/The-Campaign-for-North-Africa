"""Immutable game state (brief §4.2), now on the real land model.

The static map is a TerrainMap (game.movement); only `control` changes during
play, so it is the lone dynamic map field. Units carry the real CNA attributes
the land game needs — CPA, mobility, stacking points, defensive strength,
cohesion — and structurally satisfy the ZocUnit / StackUnit protocols so the
engine can hand them straight to game.zoc / game.stacking.

Multi-commodity supply (fuel/water/ammo/food) and combat ratings are added in
their own slices; this model carries movement + ZOC + stacking + placeholder
combat. All updates return new objects (frozen dataclasses + replace).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .events import Control, Phase, Side
from .hexmap import Coord
from .movement import TerrainMap
from .terrain import Mobility


@dataclass(frozen=True, slots=True)
class StepRecord:
    """One sub-unit's step (brief §4.2): a counter is a record, not a scalar —
    combat step-losses live here."""
    label: str
    strength: int


@dataclass(frozen=True, slots=True)
class Unit:
    id: str
    side: Side
    hex: Coord
    steps: tuple[StepRecord, ...]
    mobility: Mobility
    cpa: int                       # Capability Point Allowance per OpStage (rule 6.0)
    stacking_points: int
    oca: int                       # offensive close-assault rating (rule 11.15)
    dca: int                       # defensive close-assault rating (rule 11.15)
    # The other four Land combat characteristics (rule 11.1). Barrage/anti-armor are
    # Ratings used as Rating x TOE / 10 (11.3); armor-protection + vulnerability are
    # CONSTANTS used directly for loss counts (11.38 -> 14.42 / 15.85).
    barrage: int = 0               # Barrage Rating (artillery only, 11.11)
    anti_armor: int = 0            # Anti-Armor Rating (11.13)
    armor_protection: int = 0      # Armor Protection, constant (11.14; tanks/recce/SP)
    vulnerability: int = 0         # Vulnerability, constant (11.12; guns)
    morale: int = 0                # Basic Morale, -3..+3 (rule 17.1, from the OA sheet)
    cohesion: int = 0              # Cohesion Level (17.2); feeds the deferred 17.4 roll
    cp_used: float = 0.0           # CP spent this OpStage; reset each turn
    engaged: bool = False          # 15.81 Engaged marker (was in a Close Assault); leaving
                                   # costs 4 CP (Disengage) not 2 (Break Contact). Cleared at
                                   # the OpStage boundary. Default False keeps scenarios intact.
    # Reserve Status (rule 18), two per-OpStage scalars mirroring `engaged` (reset at the
    # OpStage boundary in apply._reset_opstage, 18.14). `reserve` is the current tier -- 0 none,
    # 1 Reserve I (may move one hex regardless of CP, 18.22), 2 Reserve II (frozen, 18.22).
    # `reserve_released` records the tier a unit was RELEASED from this stage (0 not released,
    # 1 from-I, 2 from-II), driving the 18.24 half-CPA voluntary cap. Defaults 0 keep every
    # non-reserve scenario byte-identical.
    reserve: int = 0
    reserve_released: int = 0
    is_combat: bool = True         # False for truck convoys / bare HQs / air
    is_tank: bool = False          # a Tank (combined arms 15.4 -- NOT recce/SP)
    arrival_turn: int = 0          # game-turn it enters play (<=start = on-map; rule 20)
    is_first_line_truck: bool = False
    is_pure_aa: bool = False
    is_garrison_home: bool = False
    # [23.0]/[24.61] ENGINEER CAPABILITY, and what it may be used FOR. '' is every ordinary unit.
    # 'RAIL' is the two New Zealand Railroad Construction companies -- "the only units that may
    # BUILD railroads" (24.61) and, per 23.13, "used solely for the construction and repair of
    # Railroads". 'ROAD' is the 1st South African Road Construction Battalion, "used solely for
    # Road work" (23.13). An engineer is NOT a combat unit "in any way, shape or form" (23.11), so
    # it carries is_combat=False and never banks a city, exerts a ZOC or is assaulted. Default ''
    # keeps every scenario without engineers byte-identical.
    engineer: str = ''             # '' | 'RAIL' (NZRRC, 24.61) | 'ROAD' (1 SA RC Bn, 23.13)
    formation: str = ''            # OOB organisational group; the staff layer addresses by it
    # The counter's NATIONALITY as the order of battle built it ('IT' Italian, 'GE' German, 'CW'
    # Commonwealth; game.oob._nat). Nationality is already what selects a counter's stats at build
    # time; it is carried onto the counter because rules read it at PLAY time too -- [38.37]'s refit
    # modifiers are printed per nationality of the Squadron Ground Support Unit ("German Squadron
    # Ground Support Unit add 1. Italian Ground Support Unit add 2"), and [35.23] caps how many
    # planes one may work by the same key. Default '' is "unstated", which every hand-built test
    # counter and every scenario that never asks is; game.air.refit_drm reads '' as no modifier.
    nationality: str = ''
    fuel_rate: int = 0             # 49.19 Fuel Consumption Rate; 0 -> supply.fuel_rate proxy
    # Consecutive-shortfall counters (rules 51/52), folded via replace. Reset when the
    # unit is resupplied; drive 51.21 disorganization + 51.22/52.53 attrition.
    turns_without_stores: int = 0  # consecutive game-turns without Stores (51.22)
    stages_without_water: int = 0  # consecutive Operations Stages without Water (52.53)
    disorganization: int = 0       # accumulated Disorganization Points (51.21)
    # [35.14] The SGSU's own shortfall counter -- consecutive Operations Stages in which a Squadron
    # Ground Support Unit could not draw its own upkeep (1 Stores/Game-Turn + 1 Fuel + 1 Water per
    # Operations Stage) from the dumps on its hex. "SGSUs without the required supplies (for
    # themselves) may not repair their planes", so a positive count is what grounds a squadron:
    # game.air.may_refit is the gate, and Phase 5.3's Refit Table is what reads it. The exact
    # sibling of stages_without_water, on the one counter class that has its own supply rule.
    # Zero on every non-SGSU counter and in every scenario that fields none (byte-identical).
    stages_without_air_supply: int = 0
    # --- Vehicle breakdown (rules 21/22). bar is a static column shift on the 21.38
    # table (+ = Right/more breakdown, - = Left); the three counters below fold via
    # replace. bp_accumulated + bp_checked_column reset each OpStage (TURN_ADVANCED);
    # broken_down (immobile TOE) PERSISTS across turns until repaired. Defaults 0 keep
    # every pre-breakdown scenario byte-identical.
    bar: int = 0                   # Breakdown Adjustment Rating (21.12/21.14)
    bp_accumulated: float = 0.0    # Breakdown Points this OpStage (21.25)
    bp_checked_column: int = -1    # highest 21.38 column already checked (21.26 gate)
    broken_down: int = 0           # TOE Strength Points broken down / immobile (21.44)
    # --- PHASE 4 IN-HEX SUPPLY (Option B: the supply pools live ON the unit, per rule 53.11:
    # first-line trucks are "attached directly to the parent combat unit... not represented by
    # counters; the Player notes on his TOE Sheet the number and type"). `fl_light/medium/heavy`
    # are the first-line Truck-Point CARRYING CEILING by 54.2 class -- the [60.31]/[60.41] (campaign,
    # rule 64.3) / [61.43]/[61.31] (Desert Fox) allotment, freely divisible among a hex's units
    # (59.42). `fuel/ammo/stores/water` are the current CONTENTS drawn in-hex (49.15/50.15/51.15):
    # fuel is the 49.14 tank (cpa x 1/5 x fuel_rate x strength), the rest first-line-borne.
    #
    # THIS SLICE SEEDS ONLY fl_* (the truck allotment); contents stay 0. The 49.14 fuel-tank fill
    # and the 59.66B basic load are a later slice (they need an owner ruling on the start-load
    # convention + fuel-tank evaporation). Seeded BESIDE the abstract 32.16 trace and NOT YET
    # CONSUMED -- no consumer, invariant or determinism-signature reads these, so every run stays
    # byte-identical and conservation-exact until a consumer is switched (design sec 3, the
    # parallel-run). Defaults 0 keep every unit inert.
    fuel: int = 0                  # 49.14 tank contents (49.15 in-hex)
    ammo: int = 0                  # first-line-borne ammunition on hand (50.15)
    stores: int = 0                # first-line-borne stores on hand (51.15)
    water: int = 0                 # first-line-borne water on hand (52.4)
    fl_light: int = 0              # 53.11 first-line Truck Points by 54.2 class -- the 59.42
    fl_medium: int = 0             #   allotment; the unit's carrying ceiling (supply.truck_capacity),
    fl_heavy: int = 0              #   the way Port.cap_* is a port's.
    # Derived TOE totals, cached at construction (rule 11.32 reads them ~38M times a run).
    # steps + broken_down are the only inputs and change ONLY via replace(), which re-runs
    # __post_init__ -- so the cache can never go stale. compare/repr=False keeps eq/hash/repr
    # byte-identical to the un-cached class. Pinned field == recompute by test_state_cache.py.
    _strength: int = field(init=False, repr=False, compare=False)
    _effective_strength: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        total = sum(s.strength for s in self.steps)
        object.__setattr__(self, "_strength", total)
        object.__setattr__(self, "_effective_strength", total - self.broken_down)

    @property
    def strength(self) -> int:
        return self._strength

    @property
    def effective_strength(self) -> int:
        """Operational TOE: total strength less the broken-down vehicles, which may
        not move, defend, attack or barrage (rule 21.44). The single choke point every
        combat/ZOC read passes through, so a broken vehicle contributes nothing."""
        return self._effective_strength

    @property
    def alive(self) -> bool:
        return self.strength > 0

    @property
    def raw_offense(self) -> int:  # raw offensive close-assault points (rule 11.32)
        return self.oca * self.effective_strength

    @property
    def raw_defense(self) -> int:  # raw defensive CA points (ZOC §10.15, combat §15.4)
        return self.dca * self.effective_strength

    @property
    def raw_barrage(self) -> int:  # raw barrage points (rule 11.32; artillery)
        return self.barrage * self.effective_strength

    @property
    def raw_anti_armor(self) -> int:  # raw anti-armor points (rule 11.32)
        return self.anti_armor * self.effective_strength

    @property
    def is_armor(self) -> bool:    # has Armor Protection -> a valid anti-armor target (11.14)
        return self.armor_protection > 0

    @property
    def breaks_down(self) -> bool:
        """Subject to Breakdown (21.11): tank / armored-car-recce / SP-gun vehicles
        (all carry Armor Protection). Gun units have inherent transport that never
        breaks (21.11), foot/camel are not vehicles -- neither is is_armor."""
        return self.is_armor

    @property
    def is_gun(self) -> bool:      # Artillery / Anti-Tank -- has a Vulnerability rating (11.12)
        return self.vulnerability > 0


@dataclass(frozen=True, slots=True)
class VP:
    axis: int = 0
    allied: int = 0


@dataclass(frozen=True, slots=True)
class SupplyUnit:
    """A supply dump holding the four full-logistics commodities (rules 49-52):
    Ammunition, Fuel, Stores, Water. Ceilings come from the 54.12 Supply Dump
    Capacity Chart keyed by the dump-hex terrain (game.supply.dump_capacity), not
    from the field itself. Stores/Water default 0 so every pre-full-logistics
    scenario stays byte-identical. Stacking value 0 (rule 32.14)."""
    id: str
    side: Side
    hex: Coord
    ammo: int
    fuel: int
    stores: int = 0
    water: int = 0
    is_dummy: bool = False
    # A strategic rear base (a city depot, rule 57) rather than a desert field dump: exempt
    # from the 49.3 evaporation loss. Defaults False so every field dump -- and every
    # pre-C3 scenario -- evaporates exactly as before (byte-identical).
    base: bool = False
    # [24.9] A CONSTRUCTED supply dump, as against a heap of supplies lying in a hex.
    #
    # Rule 24.9 draws a distinction the engine had collapsed, and it is the difference between a
    # LINK in a supply chain and a one-way sink. A dump is CONSTRUCTED by "any one TOE Strength
    # Point of any type" expending three Capability Points and 20 Store Points in the hex -- no
    # engineer, no elapsed time. Its Note then says what that buys:
    #
    #   "Supplies may be placed in a hex NOT containing a constructed supply dump. The only
    #    restriction on the use of such supplies is that trucks 'in convoy' may not load such
    #    supplies."
    #
    # So a lorry may always SET DOWN a load anywhere (54.11/54.35 -- that is the pile a truck
    # unload founds, game.engine._establish_dump, and it is free because the rulebook makes it
    # free); a unit standing near it may always eat from it (32.16). What only a CONSTRUCTED dump
    # can do is give supply BACK to a truck in convoy -- which is precisely what a bucket brigade
    # needs of its intermediate depots (53.14/54.16). The 60.34 staging depots, the rule-57 bases
    # and the ports of arrival are constructed by construction; a depot the army founds in the
    # desert is not, until somebody builds it.
    #
    # Default False = an unconstructed pile, so every dump the trucks and the railway have ever
    # founded reads exactly as it did (the relay was already refusing to lift from them by policy;
    # see campaign_policy._relay_source). game.scenario stamps the seeded depots True.
    constructed: bool = False
    # [52.7]/[29.53] The FULL water level a finite well (a village or bir, game.wells) refills to
    # when a rainstorm passes over its section (52.15: "all depleted wells on a map-section with a
    # rainstorm are automatically replenished"). Zero on everything else -- ordinary dumps, and the
    # unlimited major-city/oasis wells that may never deplete (52.13) -- so only a depletable well
    # carries a refill ceiling, and every non-well scenario is byte-identical (game.engine._well_refill).
    water_capacity: int = 0
    # [36.17] AN AIRFIELD IS A SUPPLY DUMP -- but not the army's. "An airfield is a supply dump for
    # supplies to be used by the SGSU's on that airfield. Fuel, ammunition, stores, etc., may be
    # stored at an airfield as if it were a dump. LAND UNITS MAY NOT USE AIRFIELD SUPPLY DUMPS
    # unless it is an emergency (exactly what constitutes an emergency is left to the Player). Any
    # SGSU at an airfield may make use of the supplies there to maintain and ready its planes."
    #
    # So an air-facility dump is an ordinary SupplyUnit in most mechanical respects -- it evaporates
    # (49.3), it is capped by 54.12, an enemy may capture or blow it -- and differs in TWO. The LAND
    # army may not eat from it: game.supply hides it from the land trace (reachable_supplies) and
    # from the land in-hex draw (colocated_dumps), and shows both to an SGSU's 35.14 draw. And IT
    # DOES NOT MOVE: 36.17's subject is the AIRFIELD ("an airfield IS a supply dump"), so the pile
    # belongs to the installation and the rule-32.3 leapfrog may not carry it away -- rejected at the
    # engine's own acceptance boundary (engine._supply_movement), not merely skipped by the policies.
    # The 36.17 "emergency" exception is the PLAYER'S call by the rule's own words and is deliberately
    # not modelled -- there is no non-arbitrary trigger for it. (A lorry ordered to unload into one
    # still may -- 36.3's "bring supplies... simply by bringing trucks into the hex" -- but no built
    # policy issues that order; see engine._sgsu_upkeep's flag on the missing refill path.)
    #
    # Default False = every dump the game has ever had, so nothing existing moves.
    air_dump: bool = False
    # Cached at construction from the four commodity pools, which change only via replace()
    # (re-runs __post_init__, never stale). compare/repr=False keeps eq/hash/repr identical.
    _empty: bool = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_empty",
                           self.ammo <= 0 and self.fuel <= 0 and self.stores <= 0 and self.water <= 0)

    @property
    def empty(self) -> bool:
        return self._empty


@dataclass(frozen=True, slots=True)
class Convoy:
    """A scheduled naval-convoy delivery (rules 48/56) -- the supply SOURCE, the
    exact dual of the SUPPLY_CONSUMED drain. A static timetable entry (the twin of
    Unit.arrival_turn): on its arrival_turn it lands whole Supply Units of cargo at
    a destination dump. `lane` is a legible label ("1".."6" Axis convoy lanes 56.11,
    "SEA-TOBRUK" the Tobruk ferry 56.3, "CW-RAILHEAD" the Cairo-forwarded rail 57);
    `dest` is the destination dump id; `cargo` maps commodity -> points
    ({"AMMO": 40, "FUEL": 60}). The die-rolled tonnage-planning layer (56.21) and
    interdiction (56.13/41.6) are later refinements; this is the deterministic
    56.2 timetable ("reflect Axis supplies as they actually occurred").

    `retarget` is the LINE the destination may retract along (rules 54.3 / 60.7), ordered
    FORWARD (the terminus) to REAR (the base). A port is a place -- capture it and the
    convoy never sails (56.15). A RAILHEAD is not: it is the furthest point the operating
    railway reaches that you still hold, so an enemy vehicle standing on Mersa Matruh pushes
    the railhead BACK east down the line rather than abolishing it. game.engine._convoy_dest
    lands the cargo in the first station on this line the enemy does not control. Default ()
    = no line, i.e. `dest` under the verbatim 56.15 test -- so every scenario but the
    campaign's Commonwealth rail lane stays byte-identical.

    `rail` marks a delivery that arrives BY RAILWAY (rule 54.3) rather than by sea. It is not a
    ship, so it is not unloaded over a quay: the rule-55.14 harbour throttle (a port's tonnage
    rating scaled by its Efficiency Level) does not apply to it, and game.engine._naval_convoys
    skips the port gate. This is the difference between rule 54.3 -- which gives the Commonwealth
    railroad its OWN charted capacity, 1,500 tons per Operations Stage (54.32) -- and rule 55,
    which rates what a HARBOUR can land from ships. Mersa Matruh is both a 250-ton harbour (55.3)
    and the Western Desert Railway terminus (60.7); without this flag the engine put the whole
    railway through the quayside cranes and clipped it to a twenty-fourth of its charted capacity.
    Default False = every existing convoy is a ship, so every scenario stays byte-identical.

    `tons` is [56.21]'s ALLOWABLE TONNAGE for this sailing -- what the Axis Convoy Capacity Table
    and the month's Tonnage Determination Table rolled up to, before anybody decided what to put in
    it. A convoy carrying tons > 0 sails EMPTY until the Axis Player plans it: 56.22 gives him the
    split ("he may now plan to ship any amounts... of fuel, ammunition, and stores that he wishes"),
    the engine takes it in the Convoy Planning Phase one Game-Turn ahead (56.15/56.21), and the
    result lands in GameState.convoy_plans. Default 0 means the cargo is fixed by the schedule --
    the Tobruk ferry, the Commonwealth railway, every hand-built test convoy -- so nothing that does
    not opt in changes."""
    id: str
    side: Side
    arrival_turn: int
    lane: str
    dest: str
    cargo: dict
    retarget: tuple[str, ...] = ()
    rail: bool = False
    tons: int = 0


@dataclass(frozen=True, slots=True)
class InterdictionOrder:
    """A scheduled air-interdiction of a convoy lane (rules 41.6 / 32.63-32.66): the
    convoys/ports/trucks idiom applied to the AIR arena. On a game-turn `turn`, `lane`
    is under `bomb_points` of Commonwealth-CRT bombing pressure -- the Bomb-Point column
    of the [41.5] Air Bombardment table the convoy attack resolves on. A static schedule
    entry (the twin of Convoy.arrival_turn): when a convoy on this lane arrives this turn,
    game.engine.interdict rolls 2d6 on the CRT (41.66) and skims that tens-of-percent off
    its cargo before it lands (41.67), leaving a smaller SUPPLY_ARRIVED beside a marker
    CONVOY_INTERDICTED. The interdictor is the side OPPOSING the convoy (derived at the
    seam, not stored). Default GameState.interdictions=() draws no dice and reduces no
    cargo, so every scenario without a seeded schedule stays byte-identical.

    `source` names a LIVE producer for the attack's strength, and the only one is "malta":
    rule 44 makes the Maltese effort a function of the island's current Capacity Levels and
    surviving, refit aeroplanes (game.malta), not of a number typed into a schedule. An order
    with no source is a static one and uses `bomb_points` as printed; a sourced order ignores
    that field, and EVERY reader must go through malta.interdiction_points rather than read it
    -- the log, the engine and the naval staff seat alike."""
    lane: str
    turn: int
    bomb_points: int
    source: str = ""


@dataclass(frozen=True, slots=True)
class AirWing:
    """A side's abstract air force in one ARENA (rules 33-46 played at the 32.0/58.0
    abstract grain -- "fidelity where the camera is", NO per-plane/pilot/sortie ledger).
    `arena` is "LAND" (tactical land support, per Operations Stage) or "SEA" (strategic
    convoy work); the split is FORCED by 41.63 (N-Africa Axis fighters may not CAP convoys),
    so the two contests are separate. `fighters`/`strike`/`recon` are Air Points by role --
    fighters contest air superiority (40/45/46 abstracted into one roll), strike flies the
    41.31 bombing missions, recon the 42.2 fog-lift. THE MAGNITUDES ARE THE BOOK'S: the campaign
    seeds each wing from the [34.6]/[59.3] Initial Air Strengths ([60.32]/[60.42] -- game.roster),
    every aeroplane at its own charted TacAir or Bombload, and game.roster converts the points back
    to aeroplanes at the same establishment's ratio. (The two benchmark scenarios keep authored
    Air-Point proxies: their own muster, [61.42], is half-untranscribable until [34.87] lands.)
    Default GameState.air=() means no air beat fires (byte-identical)."""
    id: str
    side: Side
    arena: str                     # "LAND" | "SEA" (41.63 keeps them separate)
    fighters: int
    strike: int
    recon: int


@dataclass(frozen=True, slots=True)
class AirFacility:
    """[36.0] An air facility on the map -- an airfield, an air landing strip, a flying boat basin
    or a flying boat alighting area. A conservation-invisible INSTALLATION, carried in its own
    tuple exactly as a Port is: it holds no TOE and no supply ledger of its own, so it never
    touches invariants' strength/stacking/supply checks, and being off units[] it needs no ZOC,
    stacking, combat or targeting special-casing. (Its SUPPLY is a separate SupplyUnit standing on
    the same hex with air_dump=True -- rule 36.17; see that field.)

    `kind` is one of game.air's four (AIRFIELD/STRIP/BASIN/ALIGHTING); `max_level` is that kind's
    charted ceiling (36.12 six / 36.2 one / 36.3 three / 36.4 one) and `level` its CURRENT Capacity
    Level, "the number of SGSU's and airplanes which can use an air facility" (36.0). Bombing takes
    the level down (36.14 / 41.36 -- "the result is the number of capacity levels that facility is
    reduced"); 24.76 builds an airfield back up one level at a time, while a strip or flying-boat
    facility at zero is removed from the map and must be built from scratch.

    `side` is the SEEDED owner ONLY. 36.15 makes ownership a fact about the ground rather than about
    the counter -- "airfields are, in essence, non-denominational; they may be used by anyone... Land
    combat units may capture or destroy (entirely) an airfield by occupying its hex" -- and 60.5
    agrees ("air facilities may be used by anyone who controls them"), so the CURRENT holder is
    derived from the hex's control by game.air.holder and this field is only the fallback for a hex
    neither player has entered. That is exactly how a Port already serves whoever holds its hex.
    Default GameState.air_facilities=() fields none, so every scenario without a seeded facility is
    byte-identical."""
    id: str
    side: Side
    hex: Coord
    kind: str                      # game.air: "airfield" | "strip" | "basin" | "alighting"
    level: int                     # current Capacity Level (36.14), 0 = destroyed
    max_level: int                 # the kind's charted maximum (36.12/36.2/36.3/36.4)


@dataclass(frozen=True, slots=True)
class AirMission:
    """A scheduled LAND-arena air TASKING (rules 41.31/41.36/41.37/41.39B/42.2): the convoys/
    interdictions idiom carried to air support. `kind` is "strike" (41.31 pin a stack),
    "fort" (41.37 batter a fortification one level/OpStage), "port" (41.39B knock a harbour's
    Efficiency Level down), "airfield" (41.36 knock an air facility's Capacity Level down) or
    "recon" (42.2 fog-lift). `target` is the hex (q, r) for strike/fort/airfield/recon, or the
    port id for "port". On game-turn `turn`, side `side`'s LAND air
    flies it in that side's Combat Segment (game.engine._air_support) -- the committed strike/
    recon Air Points come from its AirWings, scaled by the superiority gate. A static schedule
    now, replaced by the Air Marshal seat's live orders later (P5 Step 6); default
    GameState.air_missions=() flies nothing, so every air-mission-less scenario stays byte-identical."""
    side: Side
    kind: str                      # "strike" | "fort" | "port" | "recon"
    target: object                 # (q, r) hex, or a port id str (kind == "port")
    turn: int


@dataclass(frozen=True, slots=True)
class NavalUnit:
    """A Commonwealth Mediterranean-Fleet ship (rule 30), carried as a conservation-invisible
    ENTITY (like Rommel) rather than a Unit: it holds no TOE and no supply ledger, sits off
    units[], and so needs no ZOC / stacking / step bookkeeping. `hex` is the coastal hex it is
    stationed in -- placed within Range 100 of Alexandria (30.15), a SEED-time constraint the
    scenario honours (the engine does not re-derive Alexandria's position). `gun_rating` is fed
    straight in as Actual Barrage Points when it bombards (30.22, NO ammo), `aa_rating` its 30.16
    anti-aircraft value (carried for the deferred air game). `kind` is the ship class ("BB"/"CA"/
    "CL"/"DD"); a capital ship (BB / heavy cruiser) may reach one hex further at half Gun Rating
    (30.21). `port_cooldown` is the 30.25 counter -- a ship that fires owes two Operations Stages
    refitting in Alexandria, so it may bombard only while this is 0; `at_sea_stages` tracks the
    30.11 at-sea cadence (carried for the deferred 30.3 damage/repair). Default GameState.naval=()
    fields no fleet, so every naval-less scenario stays byte-identical."""
    id: str
    side: Side
    hex: Coord
    gun_rating: int
    aa_rating: int
    kind: str                      # "BB" | "CA" | "CL" | "DD" (capital = BB/CA, 30.21)
    at_sea_stages: int = 0
    port_cooldown: int = 0


@dataclass(frozen=True, slots=True)
class Port:
    """A port and its built-in supply dump (rule 56.28 -- every port of arrival has a
    dump 'built in, as it were'). The port THROTTLES what a convoy lands: its effective
    per-OpStage receiving capacity is ceil(cap * eff / max_eff) (rule 55.14), so a
    harbour crippled by a scuttled ship lands only a fraction of a convoy's cargo. Each
    commodity has a Point cap (cap_ammo..cap_water, proxy magnitudes for the untranscribed
    55.3 chart); cap_tons is the port's tonnage rating (55.13), crossed to Points at the
    landing edge via the 54.5 Equivalent Weights (game.supply). `eff` is the current
    Efficiency Level, `max_eff` the assigned maximum (55.12) -- which is the [55.3] chart's LISTED
    level, the same value the chart legend denominates damage on ("a loss of one level of efficiency
    decreases the port's capacity by a fraction equal to one over the listed efficiency level"), so
    max_eff is a charted magnitude and not a free dial. Both are seeded per scenario: campaign and
    benchmark alike start Tobruk at eff 2 of max 5 (scenario._tobruk_port, which also records why the
    60.7/61.6 printed "Efficiency 7" is not followed). `kind` is "major" (men + supplies) or "minor"
    (supplies only, 55.11).

    `blocked` is the number of Efficiency Levels permanently removed by a harbour BLOCK
    (55.2 scuttled ship / 55.27 air-laid mine) -- as opposed to bomb damage, which lowers
    `eff` directly. The distinction is 55.18 vs 55.26: bomb damage REGENERATES (+1/OpStage
    that the port loses no levels to bombs, up to its ceiling), but a block does NOT -- only
    engineers clear it (55.26, deferred). So the regeneration ceiling is `max_eff - blocked`,
    not `max_eff`: a port with max_eff 5 and blocked 3 may be bombed below 2 and recover UP TO 2,
    but never past the wreck. Default 0 = an unblocked harbour, which regenerates all the way to
    its assigned maximum. Tobruk seeds blocked=3 -- the San Giorgio, 55.25 verbatim ("reduces the
    efficiency level of Tobruk by three levels") -- and the field also carries an in-play block
    (a player scuttling a ship in a port he holds, 55.21/55.22)."""
    id: str
    side: Side
    hex: Coord
    kind: str
    max_eff: int
    eff: int
    cap_ammo: int
    cap_fuel: int
    cap_stores: int
    cap_water: int
    cap_tons: int
    blocked: int = 0


@dataclass(frozen=True, slots=True)
class TruckFormation:
    """An unattached 2nd/3rd-line truck convoy (rules 53-54): the inland DISTRIBUTION
    layer that hauls supply forward from a rear port/base dump to the forward dumps front
    units trace to (54.16). `truck_class` is Light/Medium/Heavy (the 54.2 Truck
    Characteristics rows); `points` is Truck Points (1 Point = 10 trucks, 53.0); `line`
    is a legible 2|3 label only -- 53.13 makes 3rd-line 'similar in all ways to 2nd, the
    sole exception the name'. The four carried-cargo pools ride ON the formation between a
    TRUCK_LOADED and a TRUCK_UNLOADED (demanded by the 53.24/53.25 load/leapfrog rules);
    each defaults 0 so a truck-less scenario stays byte-identical. is_combat is implicitly
    False (stacking value 0). A load is admissible iff sum_c(qty_c / cap_per_point_c) <=
    points (53.12; game.supply.truck_load_admissible)."""
    id: str
    side: Side
    hex: Coord
    truck_class: str               # 'light' | 'medium' | 'heavy' (the 54.2 chart rows)
    points: int                    # Truck Points; 1 Point = 10 trucks (53.0)
    line: int = 2                  # 2nd or 3rd line -- a legible label only (53.13)
    ammo: int = 0
    fuel: int = 0
    stores: int = 0
    water: int = 0


@dataclass(frozen=True, slots=True)
class Rommel:
    """General Rommel (rule 31): the Axis-only named leader, modelled as a conservation-
    invisible ENTITY rather than a Unit. He carries no TOE and no supply ledger, so he never
    touches invariants.check (strength/stacking/supply), and being off units[] he needs zero
    ZOC / stacking / combat / targeting special-casing (31.1 no combat ratings, 31.2 EZOC
    impunity + cannot be close-assaulted). `hex` is his current axial position; `in_germany`
    is True while the Berlin recall (31) holds him off-map -- the only modelled absence, since
    the 27.6 Raid-on-Rommel capture is deferred. `anchor_hex` + `companions` snapshot the 31.4
    'started-the-Operations-Stage-with-him-AND-stayed' set, taken at each OpStage boundary and
    voided the instant he moves (hex != anchor_hex)."""
    hex: Coord
    in_germany: bool = False
    anchor_hex: Coord | None = None
    companions: frozenset = frozenset()


@dataclass(frozen=True, slots=True)
class RommelArrival:
    """Rule 64.2 / 64.51: General Rommel and the Deutsches Afrika Korps reach Africa at a
    scheduled moment -- the fourth week of March 1941, i.e. the 3rd OpStage of Game-Turn 26, in
    the full campaign. The scenario schedules his entry the way an OOB schedules a reinforcement's
    arrival_turn: game.engine._rommel_arrival lifts the Rommel entity onto `hex` when (turn, stage)
    is reached, folding GameState.rommel from None to the leader on the board (ROMMEL_ARRIVED), so
    that from the NEXT game-turn's 7.14 determination the Axis reads the [7.2] rating-6 row. Default
    GameState.rommel_arrival=None schedules nothing, so the Desert Fox scenarios (which seed Rommel
    on the board from t0) and every Rommel-less scenario are untouched."""
    turn: int
    stage: int
    hex: Coord


@dataclass(frozen=True, slots=True)
class GameState:
    turn: int
    max_turns: int
    phase: Phase
    active_side: Side
    seed: int
    weather: str                   # rule-29 label: normal | hot | sandstorm | rainstorm
    vp: VP
    terrain: TerrainMap            # static map (terrain + hexsides + roads/tracks)
    control: dict                  # Coord -> Control (dynamic)
    units: tuple[Unit, ...]
    target_hex: Coord
    supplies: tuple[SupplyUnit, ...]
    consumed: dict                 # commodity -> int spent so far ("AMMO"/"FUEL")
    initial_supply: dict           # commodity -> int total EVER INTRODUCED (t0 dumps +
                                   # every SUPPLY_ARRIVED faucet); conservation check
    # The hex the COMMONWEALTH advances toward when offensive (its "forward"). The Axis
    # drives on target_hex (Alexandria/Tobruk, far east); an offensive Commonwealth drives
    # WEST on the Axis rear (Benghazi). Default None -> objective_for falls back to
    # target_hex, so every scenario that seeds no Commonwealth objective is byte-identical.
    allied_objective: "Coord | None" = None
    # Siege of Tobruk (rule 25.14 / 25.16): when siege_rules is on, artillery barrage
    # batters fortifications down. fort_levels is the dynamic overlay of reduced
    # levels (hex -> current level); an absent hex reads its static base from
    # terrain.fortifications. Default OFF / empty keeps the canonical benchmark exact.
    siege_rules: bool = False
    fort_levels: dict = field(default_factory=dict)
    # Naval-convoy timetable (rules 48/56): the supply SOURCE. Default () keeps every
    # convoy-less scenario byte-identical; the engine fires the faucet only on a
    # convoy's arrival_turn (game.engine._naval_convoys).
    convoys: tuple[Convoy, ...] = ()
    # Ports (rules 55/56.28): the harbour-efficiency throttle a convoy lands through.
    # Default () keeps every port-less scenario byte-identical (the engine applies the
    # throttle only when a landing dump belongs to a port; game.engine._naval_convoys).
    ports: tuple[Port, ...] = ()
    # Truck convoys (rules 53-54): the inland distribution layer that hauls supply forward
    # from rear dumps. Default () keeps every truck-less scenario byte-identical -- the V.J
    # Truck Convoy Phase fires only when a side fields formations (game.engine._truck_convoys).
    trucks: tuple[TruckFormation, ...] = ()
    # Air interdiction schedule (rules 41.6 / 32.63-32.66): the AIR arena's static faucet-
    # throttle. Default () draws no dice and reduces no convoy cargo, so every scenario
    # without a seeded schedule stays byte-identical (the engine skims a lane's cargo only
    # when an InterdictionOrder matches an arriving convoy's lane+turn; game.engine.interdict).
    interdictions: tuple[InterdictionOrder, ...] = ()
    # [56.21]/[56.22] THE AXIS CONVOY PLAN -- convoy id -> {commodity: Points}, the cargo the Axis
    # Player DECIDED to load into a sailing whose allowable TONNAGE the [56.4]x[56.5] charts fixed
    # ("having determined the allowable tonnage for a given Game-Turn, the Axis Player may now plan
    # to ship ANY AMOUNTS -- within the limits of allowable tonnage -- of fuel, ammunition, and
    # stores THAT HE WISHES"). Folded by CONVOY_PLANNED in the Convoy Planning Phase, ONE GAME-TURN
    # before the convoy sails (56.21). A convoy with no entry here sails with its scheduled
    # Convoy.cargo, so every fixed-cargo lane -- the Tobruk ferry, the Commonwealth railway -- and
    # every scenario that plans nothing stays byte-identical.
    convoy_plans: dict = field(default_factory=dict)
    # Abstract air (rules 33-46 at the 32.0/58.0 grain). `air` is the per-side force pool by
    # arena; `air_superiority` is the per-OpStage gate result (arena -> victor Side value | None),
    # rolled by the SYSTEM air beat (game.engine._air_superiority) and CLEARED at every OpStage
    # boundary (apply._reset_opstage's callers), exactly like the 15.81 Engaged marker. Defaults
    # (air=(), air_superiority={}) fire no air beat, so every air-less scenario stays byte-identical.
    air: tuple[AirWing, ...] = ()
    air_superiority: dict = field(default_factory=dict)
    # [38.31] THE REFIT LEDGER -- squadron key (game.air.squadron: "<side>/<arena>/<role>") -> the
    # number of that squadron's aeroplanes that have flown and are NOT YET REFITTED. Unlike
    # air_superiority this is a STOCK and is NOT cleared at the OpStage boundary: "as soon as a
    # plane flies any mission other than transfer, it must be refitted again", and it stays unfit
    # until a [38.37] Refit Table roll brings it back. An ABSENT key means none unfit, which is the
    # rule's own opening state ("at the start of a Scenario, all planes are considered refitted"),
    # so the default {} is byte-identical for every scenario that never flies.
    air_unfit: dict = field(default_factory=dict)
    # [39.19] THE STRATEGIC-PHASE LEDGER -- squadron key (game.air.squadron) -> the number of that
    # squadron's aeroplanes that flew in the STRATEGIC PHASE of the current Game-Turn: for us, the
    # African-based bombers the Axis added to his Malta raid (44.21/44.25). "A plane flying a
    # mission in an Operations Stage may not fly in the Strategic Phase of that Game-Turn AND VICE
    # VERSA", so those planes are out of the Land Support arena until the Game-Turn ends -- which is
    # why, unlike air_superiority (an OpStage gate) and unlike air_unfit (a stock that only a refit
    # roll clears), this ledger is cleared at the GAME-TURN boundary alone. game.basing reads it.
    # Default {} commits nothing, so every scenario without an Axis Malta raid is byte-identical.
    air_strategic: dict = field(default_factory=dict)
    # [42.1]/[43.1] THE BASING LEDGER -- squadron key (game.air.squadron) -> the number of that
    # squadron's aeroplanes the Axis Player has flown a TRANSFER MISSION to the Italy/Sicily boxes
    # ([36.5] off-map air facilities). It is the CHOICE half of rule 43's Mediterranean basing:
    # 43.11/43.12/43.13 REQUIRE a percentage of the German bombers to sit there and game.basing
    # computes that from the establishment, while everything else the Axis bases there he flew
    # there himself ("the Axis Player may base any portion of his airforce at Italy/Sicily within
    # the minimum German plane restrictions of Case 43.1", 61.42). It replaced a seeded percentage:
    # [60.32] starts every Axis aeroplane in Africa, so the only way to Sicily is to fly there, and
    # a bomber standing on a Sicilian field is one that is not over the desert (39.19/43.11).
    # A STOCK, cleared by nothing: an aeroplane stays where it was flown until it is flown back.
    # Default {} bases nobody in the Mediterranean beyond what rule 43 compels, so every scenario
    # that flies no transfer is byte-identical.
    air_mediterranean: dict = field(default_factory=dict)
    # Air missions (rules 41/42) + the recon fog-lift. `air_missions` is the per-side LAND
    # tasking schedule (game.engine._air_support). `air_sighted` is the per-OpStage recon lift:
    # a set of (recon_side_value, hex) pairs observation.py reads ALONGSIDE _sighted_hexes (42.2),
    # CLEARED at the OpStage boundary like air_superiority. Defaults (air_missions=(),
    # air_sighted=frozenset()) fly nothing and lift no fog, so every scenario stays byte-identical.
    air_missions: tuple[AirMission, ...] = ()
    air_sighted: frozenset = frozenset()
    # [36.0] Air facilities on the map (game.state.AirFacility): the airfields, landing strips,
    # flying boat basins and alighting areas the Air Game flies from, is maintained at and bombs.
    # Default () fields none, so every scenario that seeds no facility is byte-identical -- the
    # 35.14 SGSU upkeep beat and the 41.36 facility-bombing mission both fire only when one exists.
    air_facilities: tuple[AirFacility, ...] = ()
    # [44.0] MALTA, the two numbers the island's half of the war turns on (game.malta).
    # `malta_planes` is the aeroplanes standing on it -- 60.46's printed establishment, reduced by
    # 41.36's "for every level destroyed, remove 10% of the planes on the ground" and RAISED by the
    # [34.86] Commonwealth Airplane Reinforcement Schedule under 34.81's two caps (game.malta.
    # reinforcement). Its LEVELS are not here: they are ordinary AirFacility Capacity Levels carried
    # in air_facilities above, which is what lets 36.14, 41.36 and the invariants apply to Malta
    # unchanged.
    # `malta_strike` is how many of those aeroplanes are the ANTI-SHIPPING arm -- the bucket that
    # sets the island's Bomb Points. It is carried separately because [34.86] sends Malta fighters
    # by the hundred and torpedo aircraft never again, so the September-1940 strike SHARE stops
    # being true the moment a reinforcement lands (see malta.strike_establishment).
    # `malta_raids` is the Axis's [44.41] ledger -- Availability Level ("I".."IV") -> the Game-Turns
    # he has spent it on, counted for a raid he cancels as well (44.29).
    # `malta_unfit` is 38.31's readiness ledger for the island's anti-shipping arm, which 44.16
    # subjects to the [38.37] Refit Table like every other squadron ("they must be refit like all
    # other planes, using the same method as all other planes") even though 44.16 exempts them from
    # fuel and ammunition. It opens at 60.46's printed shortfall -- "12 Swordfish (1 SGSU) (9
    # ready)" -- so three of the twelve start unserviceable. Defaults (0, {}, 0) put no island in
    # the scenario and spend no budget, so every non-campaign scenario is byte-identical.
    malta_planes: int = 0
    malta_strike: int = 0
    malta_raids: dict = field(default_factory=dict)
    malta_unfit: int = 0
    # Commonwealth Mediterranean Fleet (rule 30): the off-shore naval-bombardment fire support.
    # Default () fields no ship, so every naval-less scenario stays byte-identical -- the CW
    # Fleet-Assignment beat fires only when a side carries naval (game.engine._naval_bombardment).
    naval: tuple[NavalUnit, ...] = ()
    # Map sections (A-E) this scenario is played on (rule 29.1 / 29.7). A Sandstorm or
    # Rainstorm from the 29.7 Foul Weather Location Table lands on 2-3 of these sections and
    # the rest read Normal (29.1); the covered ones are recorded in `storm_sections` below.
    # An empty set means "unlocalized" (a synthetic map with no section geometry), so a foul
    # result stays theatre-wide -- byte-identical to before localisation. See weather_at.
    map_sections: frozenset = frozenset()
    # The map-sections a Sandstorm/Rainstorm actually covers THIS Operations Stage (rule 29.7,
    # 29.41 delta-exclusion applied), the localised subset of `weather` -- set by the WEATHER_ROLLED
    # fold and cleared to Normal weather. Empty whenever the weather is Normal/Hot (both theatre-
    # wide, 29.31) or a foul result missed the theatre. weather_at reads it to answer the weather
    # in a given hex; the whole-map hot couplings keep reading the scalar `weather`.
    storm_sections: frozenset = frozenset()
    # --- The two-level turn clock (rules 5.1/5.2 + 7.0). `turn` above stays the
    # GAME-TURN (~1 week; every game-turn-keyed read -- on_map/arrival_turn,
    # season_for_turn, convoy arrival_turn, turns_without_stores -- keeps reading it).
    # `stage` is the Operations Stage within the game-turn (1..3, rule 5.1: the basic
    # unit of time); the CPA/BP reset boundary (6.16/21.25) is an OP-STAGE boundary.
    # initiative_side is who holds Initiative this game-turn (7.12, fixed for all three
    # stages); phasing_first is the side that declared to move first THIS stage (7.11),
    # from which the 7.12 double-move emerges. Defaults keep the flat loop byte-identical.
    stage: int = 1
    initiative_side: Side | None = None
    phasing_first: Side | None = None
    # Initiative determination (rule 7.14 / 7.15 / 61.5 / 64.4). While `initiative_fixed` is set
    # and `turn <= initiative_fixed_until`, that side holds Initiative with NO die (the scenario-
    # predetermined holder, 7.15; e.g. 61.5 Axis through GT27, or 64.4->60.6 the Italians on GT1).
    # Afterwards each game-turn rolls 1 die + the side's Initiative Rating (7.14). When
    # `initiative_chart` is set the ratings come from the transcribed [7.2] chart (game.initiative:
    # the Commonwealth rating by date, the Axis by Rommel/German-unit presence) -- this is the full
    # campaign. Otherwise a scenario reads its fixed {"AXIS": int, "ALLIED": int}
    # `initiative_ratings`, a flagged proxy the Desert Fox benchmarks use on their synthetic clock.
    # Defaults (None / 0 / empty / False) mean "roll every game-turn at rating 0" -- a fair coin
    # the toy scenarios inherit.
    initiative_fixed: Side | None = None
    initiative_fixed_until: int = 0
    initiative_ratings: dict = field(default_factory=dict)
    initiative_chart: bool = False
    # Rule 64.2: General Rommel's scheduled arrival (game.state.RommelArrival), or None for a
    # scenario that seeds him on the board from t0 (the Desert Fox benchmarks) or fields no Rommel.
    rommel_arrival: "RommelArrival | None" = None
    # General Rommel (rule 31): the Axis leader carried as a conservation-invisible ENTITY
    # (NOT a Unit), the exact idiom of siege_rules/convoys/ports/trucks. Default None keeps
    # every non-Rommel scenario byte-identical -- no morale +1 (17.28), no +5 CPA (31.4), no
    # Berlin-recall roll, and zero Rommel events.
    rommel: "Rommel | None" = None
    # Victory conditions (rules 61.8 / 64.7): a pluggable strategy object exposing
    # check(run) -> the per-turn auto-win test, and decide(run) -> the max-turns point
    # tally. Annihilation is no part of this seam's contract -- it is one spec's own
    # branch (engine._ScenarioVictory, under 61.8), not a rule the campaign shares.
    # Default None routes to the engine's built-in Race-for-Tobruk logic
    # (engine._DEFAULT_VICTORY), so every scenario that does not name a spec stays
    # byte-identical; the campaign supplies its own (game.campaign_victory).
    victory: "object | None" = None
    # Weather-clock shift (rule 64.2 / 29.1). The weather season model anchors its own
    # turn 1 to spring; a scenario whose Game-Turn 1 is not spring (the campaign opens in
    # September = fall) stamps the offset so weather.season_for_turn reads turn +
    # season_offset. Default 0 leaves every local-clock scenario byte-identical.
    season_offset: int = 0
    # The [54.12]/[8.37] VILLAGE overlay: the hexes carrying a village. A village is a LOCATION,
    # never a terrain type ("Village/Bir/Oasis -- same as terrain in hex for all purposes", 8.37),
    # so it changes no movement cost, no combat shift and no fortification (25.12) -- it raises the
    # 54.12 dump ceiling of its hex, and nothing else (game.supply.dump_capacity_at).
    #
    # Default frozenset() reads the Other-Terrain row everywhere, so every scenario that seeds no
    # gazetteer is byte-identical. ONLY game.scenario.campaign seeds it: the benchmark scenarios
    # (rommels_arrival / siege_of_tobruk) are BYTE-LOCKED to a published determinism_signature and
    # are therefore still village-BLIND -- a known, flagged asymmetry pending a re-baseline
    # decision, not a claim that the rule is universal. See game.villages.
    villages: frozenset = frozenset()

    # [32.13]/[54.15]/[49.19] DUMP CAPTURE: an enemy combat unit entering a FIELD dump's hex takes
    # it, supplies and all. See engine._capture_dumps for the rule and for why a rule-57 base and a
    # 52.1 well (base=True) are not capturable counters.
    #
    # DEFAULT FALSE, AND THIS IS A FLAGGED ASYMMETRY PENDING A DECISION -- not a claim that 32.13 is
    # campaign-only. It is a general rule and it fires immediately in the benchmark scenarios:
    # measured, on GAME-TURN 1 of BOTH rommels_arrival and siege_of_tobruk the Axis walks onto
    # AL-Dump#2 and takes 567 Ammo / 799 Fuel / 509 Stores / 501 Water off the Commonwealth, moving
    # each scenario's determinism_signature (9339d2b308d7 -> 50f594d7cdb5, 5ba4da88d107 ->
    # 8d866769c834). Those two signatures are the regression lock the LLM generalship leaderboard is
    # published against, so turning 32.13 on for them is a re-baseline decision for Eve, not one to
    # take inside a task. Only game.scenario.campaign sets it.
    dump_capture: bool = False

    # --- [24.0] CONSTRUCTION -------------------------------------------------------------------
    # `construction` is the Under Construction marker (24.33/24.42): hex -> COMPANY-STAGES of work
    # accrued on the project standing there. Rule 24.62 is stated in exactly those units -- "one
    # NZRRC company requires two OpStages to build one hex of new track; TWO NZRRC companies in the
    # same hex can build one hex in one OpStage" -- so a hex needs two company-stages and each
    # company present contributes one per Construction Segment. One counter, no special case for
    # the pair. Completed work is popped (24.11: "construction is completed at the beginning of the
    # Construction Segment of a succeeding Operations Stage").
    #
    # `rail_line` is the SURVEYED route the Alexandria-Mersa Matruh-Tobruk railway may be built
    # along, ordered from the first unbuilt hex WESTWARD to Tobruk. Rule 24.67: "construction must
    # start from the last completed hex extending from Mersa Matruh and grow westward towards
    # Tobruk. NO HEX MAY BE SKIPPED... Unbuilt railroad hexes simply do not exist." A line, not a
    # freedom: neither Player may invent new stretches of railway any more than of road (24.51).
    #
    # Both default empty -- no scenario but the campaign surveys a line, and with no line and no
    # engineers no construction order can ever validate, so every other scenario is byte-identical.
    construction: dict = field(default_factory=dict)
    rail_line: tuple = ()

    # --- [32.32] MOTORIZATION POINTS: THE LORRIES UNDER THE DESERT COLUMN -----------------------
    # `motorization` is the ATTACHMENT LEDGER: supply_id -> ((truck_id, points), ...), the Truck
    # Points of the side's own 60.33/60.43 park currently standing under that supply dump. Rule
    # 32.32 in full: "Supply Units may be transported by Motorization Points. THIRTY Motorization
    # Points are required to transport one real supply unit... Motorization Points may be
    # attached/detached to supply units only during the Organization Phase of an OpStage. A supply
    # unit not assigned the minimum necessary number of Motorization Points MAY NOT BE MOVED."
    #
    # THE READING, and it is the whole point of this field. 32.51: "Motorization Points are used IN
    # PLACE OF Truck Points... treated in all aspects as Medium Truck Points." In the abstract game
    # you are issued MP and no trucks; in the full Logistics Game you are issued trucks and no MP.
    # There is ONE transport pool either way, and 32.51 gives its exchange rate outright -- an MP IS
    # a Medium Truck Point. So thirty Motorization Points is THIRTY MEDIUM TRUCK POINTS out of the
    # same finite lorry park that is already hauling the army's fuel and ammunition forward
    # (game.supply.MOTORIZATION_POINTS / MOTORIZATION_CLASS). Every dump pushed forward is 30 medium
    # Truck Points not hauling freight. That is the central logistical decision of the desert war
    # and this ledger is where it is paid.
    #
    # A STANDING RESERVATION, NOT A PER-HEX TOLL: 32.32 hinges attach/detach on the Organization
    # Phase and 32.56 speaks of "the unit they are ASSIGNED to", so the points stay committed across
    # Game-Turns until the owner detaches them in a later Organization Phase (engine._organization).
    # An entry here is a claim on the pool for as long as it stands, not a fare paid per move.
    #
    # `motorized_supply` is the campaign gate, and it is a FLAGGED ASYMMETRY pending a re-baseline
    # decision -- NOT a claim that 32.32 is campaign-only. It is a general rule. It is gated because
    # rommels_arrival / siege_of_tobruk seed a truck pool that is an explicitly FLAGGED PLACEHOLDER
    # (game.scenario._rommel_trucks: "REPRESENTATIVE strength, pending the real rule-61 truck OOB...
    # a plausible-DAK placeholder, not a transcribed chart value") -- 6 Medium Truck Points against
    # this rule's 30, so under 32.32 no dump in either benchmark scenario could EVER move, and both
    # published determinism_signatures (9339d2b308d7 / 5ba4da88d107) would shift. Measuring a
    # rulebook magnitude against a placeholder pool measures the placeholder. The campaign's parks
    # ARE the transcribed 60.33/60.43 charts, so only game.scenario.campaign turns this on.
    motorization: dict = field(default_factory=dict)
    motorized_supply: bool = False

    # --- lookups -------------------------------------------------------------
    def unit(self, uid: str) -> Unit | None:
        for u in self.units:
            if u.id == uid:
                return u
        return None

    def on_map(self, u: Unit) -> bool:
        return u.alive and self.turn >= u.arrival_turn      # reinforcements (rule 20)

    def units_at(self, coord: Coord) -> tuple[Unit, ...]:
        return tuple(u for u in self.units if u.hex == coord and self.on_map(u))

    def living(self, side: Side) -> tuple[Unit, ...]:
        return tuple(u for u in self.units if u.side == side and self.on_map(u))

    def enemies_at(self, coord: Coord, side: Side) -> tuple[Unit, ...]:
        return tuple(u for u in self.units_at(coord) if u.side != side)

    def control_of(self, coord: Coord) -> Control:
        return self.control.get(coord, Control.NEUTRAL)

    def objective_for(self, side: Side) -> Coord:
        """The hex a side advances toward -- its 'forward'. The Axis drives on target_hex
        (Alexandria/Tobruk); the Commonwealth, when offensive, on allied_objective (the Axis
        rear). Falls back to target_hex, so every scenario that seeds no Commonwealth
        objective -- rommel/siege included -- is unchanged for both sides."""
        if side == Side.ALLIED and self.allied_objective is not None:
            return self.allied_objective
        return self.target_hex

    def fort_level(self, coord: Coord) -> int:
        """Current fortification level of a hex (rule 15.82 / 25.14): the dynamic
        overlay if the wall has been battered, else the static base from the map."""
        return self.fort_levels.get(coord, self.terrain.fortifications.get(coord, 0))

    def supply(self, sid: str) -> "SupplyUnit | None":
        for s in self.supplies:
            if s.id == sid:
                return s
        return None

    def active_supplies(self, side: Side) -> tuple["SupplyUnit", ...]:
        return tuple(s for s in self.supplies
                     if s.side == side and not s.is_dummy and not s.empty)

    def port(self, pid: str) -> "Port | None":
        for p in self.ports:
            if p.id == pid:
                return p
        return None

    def port_at(self, coord: Coord) -> "Port | None":
        """The port whose built-in dump sits on `coord` (56.28), or None."""
        for p in self.ports:
            if p.hex == coord:
                return p
        return None

    def truck(self, tid: str) -> "TruckFormation | None":
        for t in self.trucks:
            if t.id == tid:
                return t
        return None

    def air_facility(self, fid: str) -> "AirFacility | None":
        for f in self.air_facilities:
            if f.id == fid:
                return f
        return None

    def naval_of(self, nid: str) -> "NavalUnit | None":
        for n in self.naval:
            if n.id == nid:
                return n
        return None

    def trucks_at(self, coord: Coord) -> tuple["TruckFormation", ...]:
        return tuple(t for t in self.trucks if t.hex == coord)

    def weather_at(self, hex: Coord) -> str:
        """Rule 29.1: the weather in `hex`'s map-section. Normal and Hot are theatre-wide
        (29.2 / 29.31, so hot couplings may read the scalar `weather` directly); a Sandstorm
        or Rainstorm is confined to the 29.7 `storm_sections`, and every other section reads
        Normal (29.41 / 29.51). Falls back to the theatre-wide label when the hex's section is
        unknown -- a synthetic map with no section geometry -- so every geometry-less scenario
        keeps the pre-localisation whole-map behaviour (byte-identical)."""
        if self.weather not in ("sandstorm", "rainstorm") or not self.storm_sections:
            return self.weather                    # 29.31: Normal/Hot fall on every section
        section = self.terrain.sections.get(hex)
        if section is None:
            return self.weather                    # no geometry -> theatre-wide (byte-identical)
        return self.weather if section in self.storm_sections else "normal"

    # --- functional updates (return new state) -------------------------------
    def with_unit(self, unit: Unit) -> "GameState":
        units = tuple(unit if u.id == unit.id else u for u in self.units)
        return replace(self, units=units)

    def with_control(self, coord: Coord, ctrl: Control) -> "GameState":
        control = dict(self.control)
        control[coord] = ctrl
        return replace(self, control=control)

    def with_fort_level(self, coord: Coord, level: int) -> "GameState":
        fort_levels = dict(self.fort_levels)
        fort_levels[coord] = level
        return replace(self, fort_levels=fort_levels)

    def with_construction(self, coord: Coord, stages: int) -> "GameState":
        """Set (or, at 0, clear) the company-stages of work accrued on `coord` (rule 24.11)."""
        work = dict(self.construction)
        if stages > 0:
            work[coord] = stages
        else:
            work.pop(coord, None)
        return replace(self, construction=work)

    def with_supply(self, su: "SupplyUnit") -> "GameState":
        supplies = tuple(su if s.id == su.id else s for s in self.supplies)
        return replace(self, supplies=supplies)

    def with_port(self, p: "Port") -> "GameState":
        ports = tuple(p if q.id == p.id else q for q in self.ports)
        return replace(self, ports=ports)

    def with_truck(self, tf: "TruckFormation") -> "GameState":
        trucks = tuple(tf if t.id == tf.id else t for t in self.trucks)
        return replace(self, trucks=trucks)

    def with_air_facility(self, af: "AirFacility") -> "GameState":
        facilities = tuple(af if f.id == af.id else f for f in self.air_facilities)
        return replace(self, air_facilities=facilities)

    def without_air_facility(self, fid: str) -> "GameState":
        """[36.2]/[24.76]: a destroyed landing strip or flying-boat facility is "eliminated and
        removed from the game-map" -- the counter comes off and must be built from scratch."""
        return replace(self, air_facilities=tuple(f for f in self.air_facilities if f.id != fid))

    def with_naval(self, nu: "NavalUnit") -> "GameState":
        naval = tuple(nu if n.id == nu.id else n for n in self.naval)
        return replace(self, naval=naval)

    def with_air_superiority(self, arena: str, victor: "str | None") -> "GameState":
        """Record the OpStage's air-superiority victor for an arena (mirrors with_control):
        arena -> the winning Side's value, or None for a contested sky. Cleared at the
        Operations-Stage boundary (game.apply STAGE/TURN_ADVANCED)."""
        sup = dict(self.air_superiority)
        sup[arena] = victor
        return replace(self, air_superiority=sup)

    def with_air_strategic(self, squadron: str, planes: int) -> "GameState":
        """[39.19] Set how many of `squadron`'s aeroplanes have flown in the Strategic Phase of this
        Game-Turn. Zero drops the key rather than recording a zero, exactly as with_air_unfit does,
        so "no key" keeps its one meaning."""
        flown = dict(self.air_strategic)
        if planes > 0:
            flown[squadron] = planes
        else:
            flown.pop(squadron, None)
        return replace(self, air_strategic=flown)

    def with_air_mediterranean(self, squadron: str, planes: int) -> "GameState":
        """[42.1]/[43.1] Set how many of `squadron`'s aeroplanes are based in the Italy/Sicily
        boxes. Zero drops the key rather than recording a zero, exactly as with_air_strategic and
        with_air_unfit do, so "no key" keeps its one meaning -- nobody there but whoever rule 43
        compels."""
        based = dict(self.air_mediterranean)
        if planes > 0:
            based[squadron] = planes
        else:
            based.pop(squadron, None)
        return replace(self, air_mediterranean=based)

    def convoy_cargo(self, convoy: "Convoy") -> dict:
        """What a convoy is actually carrying: the Axis Player's [56.22] plan for it if one was
        made, otherwise its scheduled Convoy.cargo. THE ONE PLACE the two are reconciled -- the
        interdiction skim, the arrival manifest and the Quartermaster's projection all come through
        here, so a planned convoy can never be reported as an empty one."""
        return dict(self.convoy_plans.get(convoy.id, convoy.cargo))

    def with_convoy_plan(self, convoy_id: str, cargo: dict) -> "GameState":
        """[56.22] Record the cargo the Axis Player planned into one convoy (see convoy_plans)."""
        plans = dict(self.convoy_plans)
        plans[convoy_id] = dict(cargo)
        return replace(self, convoy_plans=plans)

    def with_air_unfit(self, squadron: str, planes: int) -> "GameState":
        """[38.31] Set how many of `squadron`'s aeroplanes stand UNREFITTED (mirrors
        with_air_superiority). A squadron back to zero is dropped from the ledger rather than
        recorded as a zero, so "no key" keeps its one meaning -- nothing unfit -- however the
        squadron got there."""
        unfit = dict(self.air_unfit)
        if planes > 0:
            unfit[squadron] = planes
        else:
            unfit.pop(squadron, None)
        return replace(self, air_unfit=unfit)

    def with_malta_planes(self, planes: int) -> "GameState":
        """[41.36] Set how many aeroplanes stand on Malta. Never below zero: a raid that would
        remove more planes than the island holds removes the island's air force and stops."""
        return replace(self, malta_planes=max(0, planes))

    def with_malta_strike(self, planes: int) -> "GameState":
        """[41.36]/[34.86] Set how many of Malta's aeroplanes are its torpedo arm.

        FAILS LOUD RATHER THAN CLAMPING, corrected 2026-07-22. It used to be
        `max(0, min(planes, self.malta_planes))`, which silently truncated a bucket bigger than the
        whole it is a bucket of -- so a generator that mis-split an arrival, or wrote the two fields
        in the wrong order, produced a plausible state instead of a stack trace, and
        invariants._check_malta_unfit's "strike <= planes" guard was close to unfalsifiable through
        apply. A bucket over its whole is a misencoded rule, and this port fails loud on those."""
        if not 0 <= planes <= self.malta_planes:
            raise ValueError(
                f"malta_strike={planes} out of [0, malta_planes={self.malta_planes}]: the torpedo "
                f"arm is a bucket of the island's establishment and may not exceed it (34.86/41.36)")
        return replace(self, malta_strike=planes)

    def with_malta_raid(self, level: str) -> "GameState":
        """[44.23]/[44.29] Book one Game-Turn of Axis Strategic Bombardment of Malta against an
        Availability Level -- spent whether the raid was flown or cancelled."""
        raids = dict(self.malta_raids)
        raids[level] = raids.get(level, 0) + 1
        return replace(self, malta_raids=raids)

    def with_malta_unfit(self, planes: int) -> "GameState":
        """[38.31]/[44.16] Set how many of Malta's anti-shipping aircraft stand unrefitted. The
        exact twin of with_air_unfit, one scalar with two ends: flying spends readiness and a
        [38.37] roll returns a percentage of it. Never below zero."""
        return replace(self, malta_unfit=max(0, planes))

    def air_superiority_of(self, arena: str) -> "str | None":
        """The Side value that holds the sky in `arena` this OpStage, or None (contested /
        not yet contested). The precondition every air mission reads (game.engine)."""
        return self.air_superiority.get(arena)

    def with_air_sighted(self, recon_side: str, coord: Coord) -> "GameState":
        """Record a hex a side's air reconnaissance has lifted this OpStage (rule 42.2). Cleared
        at the Operations-Stage boundary (game.apply STAGE/TURN_ADVANCED)."""
        return replace(self, air_sighted=self.air_sighted | {(recon_side, coord)})

    def air_sighted_for(self, side: Side) -> frozenset:
        """The hexes `side`'s air recon has revealed this OpStage -- the fog-lift observation.py
        unions with the fog-of-presence radius (42.2)."""
        return frozenset(c for s, c in self.air_sighted if s == side.value)
