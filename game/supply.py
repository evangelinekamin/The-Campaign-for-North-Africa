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

import math

from . import movement, tactics
from .state import GameState, SupplyUnit, Unit
from .terrain import Mobility, NON_MOT_CLASSES, Terrain

AMMO = "AMMO"
FUEL = "FUEL"
STORES = "STORES"
WATER = "WATER"
COMMODITIES = (AMMO, FUEL, STORES, WATER)

# 54.12 Supply Dump Capacity Chart (points), keyed by the dump-hex terrain. A major
# city (and the Tunis/Tripoli off-map boxes) holds an unlimited amount; any other
# dump hex is "Other Terrain". Villages (2500/8000/3000/1000) are not distinctly
# modelled on the colour-sampled map, so a non-city dump reads the Other row. The
# faucet fills UP TO these ceilings (game.engine._naval_convoys); overflow is never
# credited, so conservation stays exact.
_UNLIMITED = 10 ** 9
_OTHER_CAP = {AMMO: 1500, FUEL: 5000, STORES: 1000, WATER: 1000}


def dump_capacity(terrain: Terrain) -> dict:
    """The 54.12 per-commodity ceiling for a dump on `terrain`."""
    if terrain == Terrain.MAJOR_CITY:
        return {c: _UNLIMITED for c in COMMODITIES}
    return dict(_OTHER_CAP)

SUPPLY_CPA = 15                     # CPA of an MP-carried supply unit (rule 32.58A)
SUPPLY_MOVE_FUEL = 1               # Fuel to relocate a real supply unit / OpStage (32.24)
SUPPLY_MOBILITY = Mobility.MOTORIZED  # carried as medium-truck points (rule 32.51)


# 49.19 Fuel Consumption Rate PROXY by mobility class. Transcription of the chart
# column is deferred (the field Unit.fuel_rate overrides this once transcribed); these
# are clearly-flagged placeholder magnitudes. Foot/camel consume no fuel (49.12).
# Scaled to the engine's 40/60-point proxy dumps (NOT the rulebook's literal tank
# rate of 4, which is sized for thousand-point dumps): these equal the old flat
# per-OpStage charge for a short move (<=5 CP), so the tuned benchmark stays
# harmless, while the faithful law rate x ceil(CP/5) makes a long dash cost more.
_FUEL_RATE_PROXY: dict = {
    Mobility.VEHICLE: 2,           # tanks / AFVs / SP artillery
    Mobility.MOTORIZED: 1,         # truck-borne infantry, towed guns
    Mobility.RECCE: 1,
    Mobility.LIGHT_TRUCK: 1,
    Mobility.MOTORCYCLE: 1,
}


def fuel_rate(unit: Unit) -> int:
    """The unit's Fuel Consumption Rate (49.13): Fuel Points burned per five CP (or
    fraction) spent on movement. A transcribed Unit.fuel_rate wins; otherwise a
    mobility-class proxy. Non-motorized classes walk and burn nothing (49.12)."""
    if unit.mobility in NON_MOT_CLASSES:
        return 0
    return unit.fuel_rate or _FUEL_RATE_PROXY.get(unit.mobility, 2)


def fuel_cost(unit: Unit, cp_spent: float) -> int:
    """Fuel consumed to move `unit` spending `cp_spent` Capability Points (rule
    49.13): rate x ceil(CP / 5). A dash that expends many CP outruns its fuel; a
    short hop is cheap. Fuel is charged only for movement, in the hex the move
    begins (49.16). cp_spent<=0 (a unit that did not move) costs nothing."""
    if cp_spent <= 0:
        return 0
    return fuel_rate(unit) * math.ceil(cp_spent / 5)


# 50.2 Ammunition Consumption Rates (Ammo Points per TOE Strength Point committed,
# rule 50.14). Barrage/flak = 4 is the only charted value; assault and anti-armor are
# clearly-flagged PROXY magnitudes until the 50.2 chart is transcribed.
AMMO_RATE: dict = {"barrage": 4, "anti_armor": 2, "assault": 1}


def ammo_cost(unit: Unit, *, phasing: bool = True, activity: str = "assault") -> int:
    """Ammunition to use `activity` this combat (rule 50.14): the per-function
    consumption rate times the TOE Strength Points committed, floored at one TOE so a
    spent single-step unit still expends ammo and stays supply-gated. Rule 50 draws no
    phasing distinction, so `phasing` is retained only for call-site symmetry with the
    fuel/combat gates and does NOT change the cost."""
    del phasing                                        # 50.14 ammo is phasing-independent
    return AMMO_RATE.get(activity, 1) * max(1, unit.strength)


_ITALIAN_FORMATIONS = ("Ariete", "Pavia", "Bologna", "Brescia", "Savona", "Trento",
                       "Sabratha", "Trieste", "Italian")


def is_italian(unit: Unit) -> bool:
    """PROXY nationality test for the 52.6 pasta rule: an Italian unit by id prefix or
    formation name (the OOB carries no explicit nationality field on Unit yet)."""
    return unit.id.startswith("IT") or any(k in unit.formation for k in _ITALIAN_FORMATIONS)


def _is_vehicle_type(unit: Unit) -> bool:
    """Water classing (52.42): tanks/AFVs (VEHICLE/armor), guns (artillery/AT) and
    first-line trucks are 'vehicle/truck' (1 Water per TOE); everything else -- foot
    and truck-borne infantry -- is 'infantry' (52.41: 1 Water flat, regardless of TOE)."""
    return (unit.mobility == Mobility.VEHICLE or unit.is_gun or unit.is_armor
            or unit.is_first_line_truck)


def stores_cost(unit: Unit) -> int:
    """Stores a unit needs per GAME-TURN (rule 51.11): 4 per TOE Strength Point, or 1
    per TOE for HQ/engineer units (51.13). Non-combat pieces (bare HQs, trucks) proxy
    the reduced rate; a dedicated engineer flag is deferred."""
    rate = 1 if not unit.is_combat else 4
    return rate * max(1, unit.strength)


def water_cost(unit: Unit, *, hot: bool = False) -> int:
    """Water a unit needs this Operations Stage (rule 52.4). Infantry: 1 flat (52.41,
    regardless of TOE). Vehicle/gun/truck: 1 per TOE Strength Point (52.42). Hot
    weather adds a further point (52.43; the exact addition is not charted -- PROXY +1).
    52.42's 'if it used any CPA' condition is charged for every on-map mobile unit under
    the one-Operations-Stage cadence; true per-stage gating waits for CHUNK 5."""
    base = max(1, unit.strength) if _is_vehicle_type(unit) else 1
    return base + (1 if hot else 0)


def _pool(su, commodity: str) -> int:
    return getattr(su, commodity.lower())          # one path for all four commodities


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
