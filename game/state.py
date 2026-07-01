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

from dataclasses import dataclass, replace

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
    is_first_line_truck: bool = False
    is_pure_aa: bool = False
    is_garrison_home: bool = False

    @property
    def strength(self) -> int:
        return sum(s.strength for s in self.steps)

    @property
    def alive(self) -> bool:
        return self.strength > 0

    @property
    def raw_offense(self) -> int:  # raw offensive close-assault points (rule 11.32)
        return self.oca * self.strength

    @property
    def raw_defense(self) -> int:  # raw defensive CA points (ZOC §10.15, combat §15.4)
        return self.dca * self.strength

    @property
    def raw_barrage(self) -> int:  # raw barrage points (rule 11.32; artillery)
        return self.barrage * self.strength

    @property
    def raw_anti_armor(self) -> int:  # raw anti-armor points (rule 11.32)
        return self.anti_armor * self.strength

    @property
    def is_armor(self) -> bool:    # has Armor Protection -> a valid anti-armor target (11.14)
        return self.armor_protection > 0

    @property
    def is_gun(self) -> bool:      # Artillery / Anti-Tank -- has a Vulnerability rating (11.12)
        return self.vulnerability > 0


@dataclass(frozen=True, slots=True)
class VP:
    axis: int = 0
    allied: int = 0


@dataclass(frozen=True, slots=True)
class SupplyUnit:
    """Abstract-logistics supply (rule 32.1): a dump holding <=40 Ammo + <=60 Fuel
    that combat units draw on to move and fight. Stacking value 0 (rule 32.14)."""
    id: str
    side: Side
    hex: Coord
    ammo: int
    fuel: int
    is_dummy: bool = False

    @property
    def empty(self) -> bool:
        return self.ammo <= 0 and self.fuel <= 0


@dataclass(frozen=True, slots=True)
class GameState:
    turn: int
    max_turns: int
    phase: Phase
    active_side: Side
    seed: int
    weather: str
    move_modifier: int             # this turn's weather effect on effective CPA (placeholder)
    vp: VP
    terrain: TerrainMap            # static map (terrain + hexsides + roads/tracks)
    control: dict                  # Coord -> Control (dynamic)
    units: tuple[Unit, ...]
    target_hex: Coord
    supplies: tuple[SupplyUnit, ...]
    consumed: dict                 # commodity -> int spent so far ("AMMO"/"FUEL")
    initial_supply: dict           # commodity -> int total at t0 (conservation check)

    # --- lookups -------------------------------------------------------------
    def unit(self, uid: str) -> Unit | None:
        for u in self.units:
            if u.id == uid:
                return u
        return None

    def units_at(self, coord: Coord) -> tuple[Unit, ...]:
        return tuple(u for u in self.units if u.hex == coord and u.alive)

    def living(self, side: Side) -> tuple[Unit, ...]:
        return tuple(u for u in self.units if u.side == side and u.alive)

    def enemies_at(self, coord: Coord, side: Side) -> tuple[Unit, ...]:
        return tuple(u for u in self.units_at(coord) if u.side != side)

    def control_of(self, coord: Coord) -> Control:
        return self.control.get(coord, Control.NEUTRAL)

    def supply(self, sid: str) -> "SupplyUnit | None":
        for s in self.supplies:
            if s.id == sid:
                return s
        return None

    def active_supplies(self, side: Side) -> tuple["SupplyUnit", ...]:
        return tuple(s for s in self.supplies
                     if s.side == side and not s.is_dummy and not s.empty)

    # --- functional updates (return new state) -------------------------------
    def with_unit(self, unit: Unit) -> "GameState":
        units = tuple(unit if u.id == unit.id else u for u in self.units)
        return replace(self, units=units)

    def with_control(self, coord: Coord, ctrl: Control) -> "GameState":
        control = dict(self.control)
        control[coord] = ctrl
        return replace(self, control=control)

    def with_supply(self, su: "SupplyUnit") -> "GameState":
        supplies = tuple(su if s.id == su.id else s for s in self.supplies)
        return replace(self, supplies=supplies)
