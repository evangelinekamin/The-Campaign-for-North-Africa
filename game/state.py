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
    fuel_rate: int = 0             # 49.19 Fuel Consumption Rate; 0 -> supply.fuel_rate proxy
    # Consecutive-shortfall counters (rules 51/52), folded via replace. Reset when the
    # unit is resupplied; drive 51.21 disorganization + 51.22/52.53 attrition.
    turns_without_stores: int = 0  # consecutive game-turns without Stores (51.22)
    stages_without_water: int = 0  # consecutive Operations Stages without Water (52.53)
    disorganization: int = 0       # accumulated Disorganization Points (51.21)
    # --- Vehicle breakdown (rules 21/22). bar is a static column shift on the 21.38
    # table (+ = Right/more breakdown, - = Left); the three counters below fold via
    # replace. bp_accumulated + bp_checked_column reset each OpStage (TURN_ADVANCED);
    # broken_down (immobile TOE) PERSISTS across turns until repaired. Defaults 0 keep
    # every pre-breakdown scenario byte-identical.
    bar: int = 0                   # Breakdown Adjustment Rating (21.12/21.14)
    bp_accumulated: float = 0.0    # Breakdown Points this OpStage (21.25)
    bp_checked_column: int = -1    # highest 21.38 column already checked (21.26 gate)
    broken_down: int = 0           # TOE Strength Points broken down / immobile (21.44)

    @property
    def strength(self) -> int:
        return sum(s.strength for s in self.steps)

    @property
    def effective_strength(self) -> int:
        """Operational TOE: total strength less the broken-down vehicles, which may
        not move, defend, attack or barrage (rule 21.44). The single choke point every
        combat/ZOC read passes through, so a broken vehicle contributes nothing."""
        return self.strength - self.broken_down

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

    @property
    def empty(self) -> bool:
        return self.ammo <= 0 and self.fuel <= 0 and self.stores <= 0 and self.water <= 0


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
    Default False = every existing convoy is a ship, so every scenario stays byte-identical."""
    id: str
    side: Side
    arrival_turn: int
    lane: str
    dest: str
    cargo: dict
    retarget: tuple[str, ...] = ()
    rail: bool = False


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
    cargo, so every scenario without a seeded schedule stays byte-identical."""
    lane: str
    turn: int
    bomb_points: int


@dataclass(frozen=True, slots=True)
class AirWing:
    """A side's abstract air force in one ARENA (rules 33-46 played at the 32.0/58.0
    abstract grain -- "fidelity where the camera is", NO per-plane/pilot/sortie ledger).
    `arena` is "LAND" (tactical land support, per Operations Stage) or "SEA" (strategic
    convoy work); the split is FORCED by 41.63 (N-Africa Axis fighters may not CAP convoys),
    so the two contests are separate. `fighters`/`strike`/`recon` are Air Points by role --
    fighters contest air superiority (40/45/46 abstracted into one roll), strike flies the
    41.31 bombing missions, recon the 42.2 fog-lift. The magnitudes are FLAGGED PROXY (the
    34.6/59.3 Initial Air Strengths chart is untranscribed, like initiative_ratings and the
    55.3 port caps). Default GameState.air=() means no air beat fires (byte-identical)."""
    id: str
    side: Side
    arena: str                     # "LAND" | "SEA" (41.63 keeps them separate)
    fighters: int
    strike: int
    recon: int


@dataclass(frozen=True, slots=True)
class AirMission:
    """A scheduled LAND-arena air TASKING (rules 41.31/41.37/41.39B/42.2): the convoys/
    interdictions idiom carried to air support. `kind` is "strike" (41.31 pin a stack),
    "fort" (41.37 batter a fortification one level/OpStage), "port" (41.39B knock a harbour's
    Efficiency Level down) or "recon" (42.2 fog-lift). `target` is the hex (q, r) for
    strike/fort/recon, or the port id for "port". On game-turn `turn`, side `side`'s LAND air
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
    landing edge via the 54.5 Equivalent Weights (game.supply.port_landing_cap). `eff` is
    the current Efficiency Level, `max_eff` the assigned maximum (55.12); Tobruk seeds
    eff=2/max_eff=5 -- the San Giorgio scuttled in the harbour costs it three levels
    (30.17 / 55.25). `kind` is "major" (men + supplies) or "minor" (supplies only, 55.11).
    Efficiency regenerates +1/OpStage up to max_eff (55.18), except a permanent harbour
    BLOCK that only engineers clear (55.26; see game.engine.HARBOUR_BLOCKED)."""
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
    # Abstract air (rules 33-46 at the 32.0/58.0 grain). `air` is the per-side force pool by
    # arena; `air_superiority` is the per-OpStage gate result (arena -> victor Side value | None),
    # rolled by the SYSTEM air beat (game.engine._air_superiority) and CLEARED at every OpStage
    # boundary (apply._reset_opstage's callers), exactly like the 15.81 Engaged marker. Defaults
    # (air=(), air_superiority={}) fire no air beat, so every air-less scenario stays byte-identical.
    air: tuple[AirWing, ...] = ()
    air_superiority: dict = field(default_factory=dict)
    # Air missions (rules 41/42) + the recon fog-lift. `air_missions` is the per-side LAND
    # tasking schedule (game.engine._air_support). `air_sighted` is the per-OpStage recon lift:
    # a set of (recon_side_value, hex) pairs observation.py reads ALONGSIDE _sighted_hexes (42.2),
    # CLEARED at the OpStage boundary like air_superiority. Defaults (air_missions=(),
    # air_sighted=frozenset()) fly nothing and lift no fog, so every scenario stays byte-identical.
    air_missions: tuple[AirMission, ...] = ()
    air_sighted: frozenset = frozenset()
    # Commonwealth Mediterranean Fleet (rule 30): the off-shore naval-bombardment fire support.
    # Default () fields no ship, so every naval-less scenario stays byte-identical -- the CW
    # Fleet-Assignment beat fires only when a side carries naval (game.engine._naval_bombardment).
    naval: tuple[NavalUnit, ...] = ()
    # Map sections (A-E) this scenario is played on (rule 29.1 / 29.7). Foul weather
    # from the 29.7 Foul Weather Location Table only reaches the theater when it lands
    # on one of these sections; an empty set means "unlocalized" (a synthetic map), so
    # foul weather is not filtered out. Purely informs weather determination.
    map_sections: frozenset = frozenset()
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
    # Initiative determination (rule 7.14 / 7.15 / 61.5). While `initiative_fixed` is set and
    # `turn <= initiative_fixed_until`, that side holds Initiative with NO die (the scenario-
    # predetermined holder, 7.15; e.g. 61.5 Axis through GT27). Afterwards each game-turn rolls
    # 1 die + the side's Initiative Rating (7.14). `initiative_ratings` are a representative
    # {"AXIS": int, "ALLIED": int} PROXY for the untranscribed 7.2 chart. Defaults (None / 0 /
    # empty) mean "roll every game-turn at rating 0" -- a fair coin the toy scenarios inherit.
    initiative_fixed: Side | None = None
    initiative_fixed_until: int = 0
    initiative_ratings: dict = field(default_factory=dict)
    # General Rommel (rule 31): the Axis leader carried as a conservation-invisible ENTITY
    # (NOT a Unit), the exact idiom of siege_rules/convoys/ports/trucks. Default None keeps
    # every non-Rommel scenario byte-identical -- no morale +1 (17.28), no +5 CPA (31.4), no
    # Berlin-recall roll, and zero Rommel events.
    rommel: "Rommel | None" = None
    # Victory conditions (rules 61.8 / 64.7): a pluggable strategy object exposing
    # check(run) -> the per-turn auto-win/annihilation test, and decide(run) -> the
    # max-turns point tally. Default None routes to the engine's built-in Race-for-
    # Tobruk logic (engine._DEFAULT_VICTORY), so every scenario that does not name a
    # spec stays byte-identical; the campaign supplies its own (game.campaign_victory).
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

    def naval_of(self, nid: str) -> "NavalUnit | None":
        for n in self.naval:
            if n.id == nid:
                return n
        return None

    def trucks_at(self, coord: Coord) -> tuple["TruckFormation", ...]:
        return tuple(t for t in self.trucks if t.hex == coord)

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
