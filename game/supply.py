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

from . import logistics_data, movement, tactics
from .hexmap import Coord
from .state import GameState, Port, SupplyUnit, TruckFormation, Unit
from .terrain import Mobility, NON_MOT_CLASSES, Terrain

AMMO = "AMMO"
FUEL = "FUEL"
STORES = "STORES"
WATER = "WATER"
COMMODITIES = (AMMO, FUEL, STORES, WATER)

# 54.12 Supply Dump Capacity Chart (points). THREE of the chart's rows are live here: a major
# city (and the Tunis/Tripoli off-map boxes) holds an unlimited amount; a VILLAGE holds
# 2500/8000/3000/1000; any other dump hex is "Other Terrain" (1500/5000/1000/1000). A village is
# a LOCATION, not a terrain type ([8.37]: "Village/Bir/Oasis -- same as terrain in hex for all
# purposes"), so it rides as an overlay set of hexes on GameState -- see game.villages for the
# gazetteer and dump_capacity_at below for the lookup. The faucet fills UP TO these ceilings
# (game.engine._naval_convoys); overflow is never credited, so conservation stays exact. Sourced
# from data/logistics_rates.json so the ceilings are the rulebook's, not magic numbers.
_UNLIMITED = 10 ** 9
_OTHER_CAP = logistics_data.dump_other_terrain_cap()
_VILLAGE_CAP = logistics_data.dump_village_cap()


def dump_capacity(terrain: Terrain, *, village: bool = False) -> dict:
    """The 54.12 per-commodity ceiling for a dump on `terrain`, in a village or not.

    The rows are exclusive and Major City is the higher: a hex that is BOTH a city and a named
    place (Tobruk, Bardia, Benghazi) keeps the unlimited city row. `village` defaults False, so
    every caller that does not know the location -- and every byte-locked benchmark scenario --
    reads exactly the Other-Terrain row it read before."""
    if terrain == Terrain.MAJOR_CITY:
        return {c: _UNLIMITED for c in COMMODITIES}
    return dict(_VILLAGE_CAP if village else _OTHER_CAP)


def dump_capacity_at(state: GameState, hex: Coord) -> dict:
    """The 54.12 ceiling for a dump standing on `hex` of THIS map: the terrain row, overlaid with
    the Village row when the hex carries a village (state.villages, seeded by game.scenario.
    campaign). The single place the engine and the policies should ask -- passing a bare Terrain
    is village-blind by construction."""
    return dump_capacity(state.terrain.terrain[hex], village=hex in state.villages)


# 54.5 Equivalent Weights: tons per one supply Point (Ammo 4t, Fuel 1/8t, Stores 1t,
# Water 1/6t). The ONLY place tonnage meets points -- confined to the port/rail landing
# edge (the plan keeps the tonnage lever out of the per-hex model). Kept as EXACT
# rulebook fractions (Fuel 1/8, Water 1/6): the data file transcribes Water as the
# rounded decimal 0.1667, so sourcing it from JSON would inject a rounding error into
# the conservation math -- these are exact-faithful already, so they stay literals.
TONS_PER_POINT: dict = {AMMO: 4.0, FUEL: 1 / 8, STORES: 1.0, WATER: 1 / 6}


def tons_to_points(tons: float, commodity: str) -> int:
    """54.5: how many Points of `commodity` a tonnage allowance holds (floored)."""
    return math.floor(tons / TONS_PER_POINT[commodity])


def points_to_tons(points: int, commodity: str) -> int:
    """54.5: the tonnage a Point count of `commodity` weighs (for port narration)."""
    return math.ceil(points * TONS_PER_POINT[commodity])


def port_landing_cap(port: Port, commodity: str) -> int:
    """55.14: a port's effective per-OpStage receiving cap for `commodity` at its current
    Efficiency Level -- the smaller of the explicit per-commodity Point cap and the 54.5
    tonnage-derived cap, scaled by eff/max_eff. 'Round all reductions upward' (55.14)."""
    cap = min(getattr(port, "cap_" + commodity.lower()), tons_to_points(port.cap_tons, commodity))
    return math.ceil(cap * port.eff / port.max_eff)


def regen_eff(port: Port) -> int | None:
    """55.18: a port regains one Efficiency Level per OpStage, up to its assigned maximum.
    Returns the new level, or None if already at max_eff (nothing to regenerate)."""
    return port.eff + 1 if port.eff < port.max_eff else None

SUPPLY_CPA = 15                     # CPA of an MP-carried supply unit (rule 32.58A)
SUPPLY_MOVE_FUEL = 1               # Fuel to relocate a real supply unit / OpStage (32.24)
SUPPLY_MOBILITY = Mobility.MOTORIZED  # carried as medium-truck points (rule 32.51)


# 49.19 Fuel Consumption Rate FALLBACK by mobility class (sourced from the engine_proxy
# block of data/logistics_rates.json). Foot/camel consume no fuel (49.12). This is the
# fallback ONLY for units carrying no transcribed Unit.fuel_rate -- the toy coastal
# corridor; the real Desert Fox OOB carries the per-model [4.47-4.49] rate (game.oob via
# logistics_data.fuel_rate_by_model), which the 49.13 x-TOE-strength law in fuel_cost
# then scales. See logistics_data.
_FUEL_RATE_PROXY: dict = logistics_data.fuel_rate_proxy()


def fuel_rate(unit: Unit) -> int:
    """The unit's Fuel Consumption Rate (49.13): Fuel Points burned per five CP (or
    fraction) per TOE Strength Point spent on movement. A transcribed Unit.fuel_rate
    (the per-model [4.47-4.49] rate) wins; otherwise a mobility-class fallback.
    Non-motorized classes walk and burn nothing (49.12)."""
    if unit.mobility in NON_MOT_CLASSES:
        return 0
    return unit.fuel_rate or _FUEL_RATE_PROXY.get(unit.mobility, 2)


def fuel_cost(unit: Unit, cp_spent: float) -> int:
    """Fuel consumed to move `unit` spending `cp_spent` Capability Points (rule
    49.13): rate x ceil(CP / 5) x TOE Strength Points. The full-logistics (Regime B)
    law -- every TOE Strength Point of vehicles burns its rate, so a full-strength
    formation costs strength-fold more than a single step (49.13 worked example). A
    dash that expends many CP outruns its fuel; a short hop is cheap. Fuel is charged
    only for movement, in the hex the move begins (49.16). cp_spent<=0 (a unit that
    did not move) costs nothing."""
    if cp_spent <= 0:
        return 0
    return fuel_rate(unit) * math.ceil(cp_spent / 5) * max(1, unit.strength)


# [50.2] Ammunition Consumption Rates (Ammo Points per TOE Strength Point committed to
# the function, rule 50.14), sourced from data/logistics_rates.json ('Logistics Game
# Played' land rates). Now FAITHFUL to the chart: barrage 4, anti-armor 3, close-assault
# 2 -- the earlier proxy under-charged anti-armor (was 2) and close-assault (was 1).
AMMO_RATE: dict = logistics_data.ammo_rates()


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


def is_infantry(unit: Unit) -> bool:
    """An infantry-type combat unit -- the only kind whose TOE Strength Points may be
    eliminated by stores/water shortfall attrition (51.22 / 52.53). Guns and tanks are
    exempt (51.22)."""
    return unit.is_combat and not _is_vehicle_type(unit)


_STORES_RATE = logistics_data.stores_rates()   # 51.11/51.13, from the rulebook chart


def stores_cost(unit: Unit) -> int:
    """Stores a unit needs per GAME-TURN (rule 51.11): 4 per TOE Strength Point, or 1
    per TOE for HQ/engineer units (51.13). Non-combat pieces (bare HQs, trucks) proxy
    the reduced rate; a dedicated engineer flag is deferred."""
    rate = _STORES_RATE["combat"] if unit.is_combat else _STORES_RATE["noncombat"]
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


# --- truck convoys (rules 53-54, the inland distribution layer) ---------------
# [54.2] Truck Characteristics: per-Truck-Point commodity capacity, the 53.22 extended
# convoy CPA, the truck's own Fuel Capacity and its Fuel Consumption Factor, keyed by
# class. Sourced once from the JSON so the numbers stay the rulebook's.
TRUCK_CHARS: dict = logistics_data.truck_characteristics()


def truck_capacity(truck_class: str) -> dict:
    """54.2 per-Truck-Point supply-point capacity of each commodity for `truck_class`."""
    return TRUCK_CHARS[truck_class]["capacity"]


def truck_convoy_cpa(truck_class: str) -> int:
    """53.22 extended convoy CPA of a truck formation (the 54.2 'Supplies' column): Light
    40, Medium/Heavy 30."""
    return TRUCK_CHARS[truck_class]["convoy_cpa"]


def truck_load_admissible(truck: TruckFormation, added: dict) -> bool:
    """53.12 load admissibility: a formation of N Truck Points may carry any mix whose
    fractional capacity use sums to <= N -- sum_c(cargo_c / cap_per_point_c) <= points,
    evaluated on the cargo the truck would hold AFTER adding `added`. (A truck 'may carry
    anything', 53.12, so the four commodities share the Points fractionally.)"""
    cap = truck_capacity(truck.truck_class)
    frac = sum((getattr(truck, c.lower()) + added.get(c, 0)) / cap[c] for c in COMMODITIES)
    return frac <= truck.points + 1e-9


def truck_move_fuel(truck: TruckFormation, cp_spent: float) -> int:
    """49.13 / 49.18: Fuel a truck formation burns to relocate, drawn from its OWN cargo
    fuel -- Fuel Consumption Factor (1 for every class, 54.2) x ceil(CP / 5) x Truck
    Points. A short hop is cheap; a long convoy leg over the desert eats its own load."""
    if cp_spent <= 0:
        return 0
    return TRUCK_CHARS[truck.truck_class]["fuel_factor"] * math.ceil(cp_spent / 5) * truck.points


def reachable_truck_moves(state: GameState, truck: TruckFormation) -> dict:
    """Hexes a truck convoy can relocate to this Truck Convoy Phase: within its 53.22
    extended convoy CPA as medium-truck movement, blocked by enemy ZOC not negated by a
    friendly unit (the identical 32.16 trace-blocking reused from reachable_moves)."""
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, truck.side)
    friendly = frozenset(u.hex for u in state.living(truck.side))
    blocked = (enemy_zoc - friendly) | enemy_occupied
    return movement.reachable(state.terrain, truck.hex,
                              truck_convoy_cpa(truck.truck_class), SUPPLY_MOBILITY,
                              blocked=blocked)


# --- Commonwealth railroad (rule 54.3) ----------------------------------------
RAIL_TONNAGE_54_3 = 1500          # 54.3: tons of ONE commodity hauled per Operations Stage


def rail_haul_cap(commodity: str) -> int:
    """54.3 / 54.33: the Points of `commodity` the Commonwealth rail may haul in one
    Operations Stage -- 1500 tons crossed to Points at the 54.5 Equivalent Weights."""
    return tons_to_points(RAIL_TONNAGE_54_3, commodity)


def rail_reachable(tmap: movement.TerrainMap, start: Coord) -> frozenset:
    """The hexes rail-connected to `start` over the map's rail edge-set (54.3) -- a
    graph-reachability twin of movement.reachable, but over rails rather than terrain
    cost. Gates a RAIL_HAULED transfer: both dumps must sit on the one network."""
    seen = {start}
    frontier = [start]
    while frontier:
        here = frontier.pop()
        for e in tmap.rails:
            if here in e:
                other = next(iter(e - {here}))
                if other not in seen:
                    seen.add(other)
                    frontier.append(other)
    return frozenset(seen)


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
