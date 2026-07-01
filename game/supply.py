"""Abstract logistics (rule 32) — the supply trace and consumption that gate
movement and combat.

A combat unit may draw on a friendly Supply Unit within half its CPA (rule
32.16), traced as medium-truck movement (foot for leg infantry), never through
impassable terrain or enemy ZOC unoccupied by a friendly unit. Moving costs Fuel
(rule 32.23-24, once per OpStage); fighting costs Ammo (rule 32.21). This is the
heart of CNA — "less about combat, more about logistics".

MOBILE SUPPLY (rule 32.3) is now modelled: a supply unit relocates up to CPA 15
(rule 32.58A) as medium-truck movement, costing a flat 1 Fuel Point per OpStage
(rule 32.24), and must end stacked with a friendly combat unit (rule 32.33 — it
moves with the army). See engine._supply_movement / policy.supply_orders.

DEFERRED + FLAGGED: the 30-Motorization-Point requirement to carry a unit (32.32)
and the MP pool itself (32.5) are abstracted (any dump with fuel may move); the
separate Truck Convoy Phase and the "begins stacked" strictness of 32.33 (we
require only "ends stacked"); availability & convoy arrival (32.4/32.6); dummies
(32.18); capture (32.13) and destruction (32.17) of dumps; MP attrition (32.57-59,
values not in OCR); and the defender out-of-ammo auto-surrender (15.15). Draw
costs approximate per-battalion-equivalent rates via mobility class + stacking.
"""
from __future__ import annotations

from . import movement, tactics
from .state import GameState, SupplyUnit, Unit
from .terrain import Mobility, NON_MOT_CLASSES

AMMO = "AMMO"
FUEL = "FUEL"

SUPPLY_CPA = 15                     # CPA of an MP-carried supply unit (rule 32.58A)
SUPPLY_MOVE_FUEL = 1               # Fuel to relocate a real supply unit / OpStage (32.24)
SUPPLY_MOBILITY = Mobility.MOTORIZED  # carried as medium-truck points (rule 32.51)


def fuel_cost(unit: Unit) -> int:
    """Fuel to move this unit in an OpStage (rule 32.24, bn-eq approximation)."""
    if unit.mobility in NON_MOT_CLASSES:
        return 0                       # leg infantry walks — no fuel
    if unit.mobility == Mobility.VEHICLE:
        return 2                       # tank battalion-equivalent
    return 1                           # motorized / recce / gun battalion-equivalent


def ammo_cost(unit: Unit, *, phasing: bool) -> int:
    """Ammo to take part in a Close Assault (rule 32.21): 1 per non-phasing
    bn-eq, doubled for the phasing attacker. We proxy bn-eq count by stacking."""
    return (2 if phasing else 1) * unit.stacking_points


def _pool(su, commodity: str) -> int:
    return su.ammo if commodity == AMMO else su.fuel


def reachable_supplies(state: GameState, unit: Unit, commodity: str):
    """Friendly supply units holding `commodity`, within half the unit's CPA,
    nearest first (deterministic). Trace blocked by enemy ZOC / units (32.16)."""
    budget = unit.cpa / 2
    mob = Mobility.FOOT if unit.mobility in NON_MOT_CLASSES else Mobility.MOTORIZED
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, unit.side)
    friendly_occupied = frozenset(u.hex for u in state.living(unit.side))
    blocked = (enemy_zoc - friendly_occupied) | enemy_occupied
    reach = movement.reachable(state.terrain, unit.hex, budget, mob, blocked=blocked)
    out = [su for su in state.active_supplies(unit.side)
           if su.hex in reach and _pool(su, commodity) > 0]
    out.sort(key=lambda su: (reach[su.hex], su.id))
    return out


def reachable_moves(state: GameState, dump: SupplyUnit) -> dict:
    """Hexes a carried supply unit can relocate to this OpStage: within CPA 15
    (rule 32.58A) as medium-truck movement, blocked by enemy ZOC not negated by a
    friendly unit (the 32.16 trace blocking, reused for the carry)."""
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, dump.side)
    friendly = frozenset(u.hex for u in state.living(dump.side))
    blocked = (enemy_zoc - friendly) | enemy_occupied
    return movement.reachable(state.terrain, dump.hex, SUPPLY_CPA, SUPPLY_MOBILITY,
                              blocked=blocked)


def plan_draw(state: GameState, unit: Unit, commodity: str, need: int):
    """A list of (supply_id, qty) drawing `need` of commodity from reachable
    dumps (nearest first), or None if the unit cannot be supplied that much."""
    if need <= 0:
        return []
    draws: list[tuple[str, int]] = []
    remaining = need
    for su in reachable_supplies(state, unit, commodity):
        if remaining <= 0:
            break
        take = min(remaining, _pool(su, commodity))
        if take > 0:
            draws.append((su.id, take))
            remaining -= take
    return draws if remaining <= 0 else None
