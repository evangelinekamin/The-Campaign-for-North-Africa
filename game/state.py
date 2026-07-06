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
    is_combat: bool = True         # False for truck convoys / bare HQs / air
    is_tank: bool = False          # a Tank (combined arms 15.4 -- NOT recce/SP)
    arrival_turn: int = 0          # game-turn it enters play (<=start = on-map; rule 20)
    is_first_line_truck: bool = False
    is_pure_aa: bool = False
    is_garrison_home: bool = False
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
    56.2 timetable ("reflect Axis supplies as they actually occurred")."""
    id: str
    side: Side
    arrival_turn: int
    lane: str
    dest: str
    cargo: dict


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
    # Map sections (A-E) this scenario is played on (rule 29.1 / 29.7). Foul weather
    # from the 29.7 Foul Weather Location Table only reaches the theater when it lands
    # on one of these sections; an empty set means "unlocalized" (a synthetic map), so
    # foul weather is not filtered out. Purely informs weather determination.
    map_sections: frozenset = frozenset()

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

    def with_supply(self, su: "SupplyUnit") -> "GameState":
        supplies = tuple(su if s.id == su.id else s for s in self.supplies)
        return replace(self, supplies=supplies)

    def with_port(self, p: "Port") -> "GameState":
        ports = tuple(p if q.id == p.id else q for q in self.ports)
        return replace(self, ports=ports)

    def with_truck(self, tf: "TruckFormation") -> "GameState":
        trucks = tuple(tf if t.id == tf.id else t for t in self.trucks)
        return replace(self, trucks=trucks)
