"""Zones of Control (rule 10.0).

A unit projects a ZOC into the six surrounding hexes, but only if it qualifies
(size + strength + cohesion, §10.11/10.14/10.15) and only into hexes the ZOC can
actually reach (§10.21: blocked by escarpment / major-river / sea hexsides, and
not into a hex the unit could not itself enter). ZOC makes movement tactical:
a unit must stop on entering an enemy-controlled hex (§10.23) and may not step
from one controlled hex into another (§10.24); a friendly combat unit negates
enemy ZOC in its hex (§10.26).

This module computes the control map and a ZOC-aware reachability; it operates on
a light ZocUnit protocol so it stays decoupled from the full engine Unit until
the wiring slice.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Protocol

from .hexmap import Coord, neighbors
from .movement import TerrainMap, reachable, step_cost
from .terrain import Hexside, Mobility

# ZOC does not extend through these hexsides (§10.21a/b). Lake / all-sea hexsides
# also block it but are not modelled yet.
ZOC_BLOCKING_HEXSIDES = frozenset({
    Hexside.UP_ESCARPMENT, Hexside.DOWN_ESCARPMENT, Hexside.MAJOR_RIVER,
})

ZOC_MIN_DEFENSE = 10  # §10.15: units totalling < 10 raw defensive CA points exert no ZOC


class ZocUnit(Protocol):
    stacking_points: int
    raw_defense: int          # raw defensive close-assault points (§10.15)
    cohesion: int
    is_combat: bool           # False for truck convoys, bare HQs, air/SGSU/ships (§10.11/10.12)
    mobility: Mobility


def unit_eligible(u: ZocUnit) -> bool:
    return u.is_combat and u.cohesion > -26          # §10.11/10.12, §10.14


def hex_exerts_zoc(units: Iterable[ZocUnit]) -> bool:
    elig = [u for u in units if unit_eligible(u)]
    if not elig:
        return False
    total_sp = sum(u.stacking_points for u in elig)
    total_def = sum(u.raw_defense for u in elig)
    # §10.11: need more than one stacking point present; §10.15: >= 10 raw defense.
    return total_sp > 1 and total_def >= ZOC_MIN_DEFENSE


def zoc_extends(origin: Coord, nb: Coord, tmap: TerrainMap, mobility: Mobility) -> bool:
    if tmap.hexsides.get((origin, nb)) in ZOC_BLOCKING_HEXSIDES:   # §10.21a/b
        return False
    return step_cost(tmap, origin, nb, mobility) is not None       # §10.21c


def controlled_from(units: Iterable[ZocUnit], origin: Coord,
                    tmap: TerrainMap) -> frozenset:
    units = list(units)
    if not hex_exerts_zoc(units):
        return frozenset()
    out: set[Coord] = set()
    for u in units:
        if not unit_eligible(u):
            continue
        for nb in neighbors(origin):
            if tmap.exists(nb) and zoc_extends(origin, nb, tmap, u.mobility):
                out.add(nb)
    return frozenset(out)


def control_map(units_by_hex: Mapping[Coord, Iterable[ZocUnit]],
                tmap: TerrainMap) -> frozenset:
    """All hexes controlled by the given side's units."""
    out: set[Coord] = set()
    for origin, units in units_by_hex.items():
        out |= controlled_from(units, origin, tmap)
    return frozenset(out)


def reachable_with_zoc(tmap: TerrainMap, start: Coord, budget: float,
                       mobility: Mobility, *, enemy_zoc: frozenset,
                       friendly_negators: frozenset = frozenset(),
                       enemy_occupied: frozenset = frozenset(),
                       break_off: float = 2.0) -> dict[Coord, float]:
    """Movement reachability under enemy ZOC (§10.22-10.26, §8.64-8.66):
    enter a controlled hex but stop there; never step controlled->controlled; a
    friendly combat unit negates ZOC in its hex; leaving a ZOC you start in costs
    `break_off` CP (2 Contact / 4 Engaged); enemy-occupied hexes are impassable."""
    def controlled(h: Coord) -> bool:
        return h in enemy_zoc and h not in friendly_negators      # §10.26 negation

    return reachable(
        tmap, start, budget, mobility,
        blocked=enemy_occupied,                                   # §8.13
        terminal=controlled,                                      # §10.23
        passable=lambda here, nb: not (controlled(here) and controlled(nb)),  # §10.24
        start_cost=break_off if controlled(start) else 0.0,       # §8.64-8.66
    )
