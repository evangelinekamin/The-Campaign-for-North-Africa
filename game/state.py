"""Immutable game state (brief §4.2).

Never serialised whole into an LLM context — the Phase-1 agent layer receives
role-scoped *views*, not this object. State is rebuilt by folding events
(game.apply). All updates return new objects (frozen dataclasses +
dataclasses.replace); for the toy scenario the O(n) copy on each change is
irrelevant. The brief's perf note (§5) defers optimising the engine step until
it is proven a bottleneck (Phase 3 / RL only) — correctness single-threaded
first.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .events import Control, Phase, Side

Coord = tuple[int, int]


def adjacent(a: Coord, b: Coord) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def neighbors(coord: Coord) -> tuple[Coord, ...]:
    x, y = coord
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))


@dataclass(frozen=True, slots=True)
class StepRecord:
    """One sub-unit's step. The brief's load-bearing fact (§4.2): a counter is a
    *record*, not a scalar — step losses live here, not in a single strength."""
    label: str
    strength: int


@dataclass(frozen=True, slots=True)
class Unit:
    id: str
    side: Side
    hex: Coord
    steps: tuple[StepRecord, ...]
    fuel: float

    @property
    def strength(self) -> int:
        return sum(s.strength for s in self.steps)

    @property
    def alive(self) -> bool:
        return self.strength > 0


@dataclass(frozen=True, slots=True)
class Hex:
    coord: Coord
    terrain: str
    move_cost: int
    control: Control


@dataclass(frozen=True, slots=True)
class VP:
    axis: int = 0
    allied: int = 0


@dataclass(frozen=True, slots=True)
class GameState:
    turn: int
    max_turns: int
    phase: Phase
    active_side: Side
    seed: int
    weather: str
    move_modifier: int          # this turn's weather effect on movement allowance
    vp: VP
    hexes: tuple[Hex, ...]
    units: tuple[Unit, ...]
    target_hex: Coord
    fuel_consumed: float        # running total, for the supply-conservation invariant

    # --- lookups -------------------------------------------------------------
    def unit(self, uid: str) -> Unit | None:
        for u in self.units:
            if u.id == uid:
                return u
        return None

    def hex_at(self, coord: Coord) -> Hex | None:
        for h in self.hexes:
            if h.coord == coord:
                return h
        return None

    def units_at(self, coord: Coord) -> tuple[Unit, ...]:
        return tuple(u for u in self.units if u.hex == coord and u.alive)

    def living(self, side: Side) -> tuple[Unit, ...]:
        return tuple(u for u in self.units if u.side == side and u.alive)

    def enemies_at(self, coord: Coord, side: Side) -> tuple[Unit, ...]:
        return tuple(u for u in self.units_at(coord) if u.side != side)

    # --- functional updates (return new state) -------------------------------
    def with_unit(self, unit: Unit) -> "GameState":
        units = tuple(unit if u.id == unit.id else u for u in self.units)
        return replace(self, units=units)

    def with_hex(self, hex_: Hex) -> "GameState":
        hexes = tuple(hex_ if h.coord == hex_.coord else h for h in self.hexes)
        return replace(self, hexes=hexes)
