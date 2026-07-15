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
from .state import GameState, Port, Side, SupplyUnit, TruckFormation, Unit
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


def port_tonnage_budget(port: Port) -> int:
    """55.3/55.14: a port's TOTAL supply tonnage per Operations Stage, ACROSS ALL commodities,
    at its current Efficiency Level. The 55.3 'Maximum Tonnage' is a single total ("the TOTAL
    tonnage of supplies that may be shipped in and/or out in one Operations Stage"), NOT a
    per-commodity allowance -- so this is the ONE shared budget a port ships within, and the
    landing edge (game.engine._naval_convoys) crosses it to Points per commodity via 54.5.
    Reduced by damage to ceil(max_tons * eff / max_eff) -- the rulebook's own Benghazi worked
    example: 2500 t at Efficiency 1 of 3 -> ceil(2500 * 1/3) = 834 t (data 55.14 reduction rule)."""
    return math.ceil(port.cap_tons * port.eff / port.max_eff)


def port_landing_cap(port: Port, commodity: str) -> int:
    """55.14: a SECONDARY per-commodity sub-cap on receiving `commodity`, from the port's
    explicit per-commodity Point cap (cap_ammo..cap_water) scaled by eff/max_eff. The BINDING
    harbour throttle is the shared tonnage budget (port_tonnage_budget) -- 55.3's Maximum Tonnage
    is a total, not a per-commodity limit -- so this sub-cap is _UNLIMITED for the campaign's
    ports (tonnage the sole valve) and finite only where a scenario sets an explicit cap_k.
    'Round all reductions upward' (55.14)."""
    return math.ceil(getattr(port, "cap_" + commodity.lower()) * port.eff / port.max_eff)


def regen_eff(port: Port) -> int | None:
    """55.18: a port regains one Efficiency Level per OpStage, up to its regeneration
    CEILING. The ceiling is max_eff MINUS any permanent block (55.2 scuttled ship /
    55.27 mine, Port.blocked), because a block is not bomb damage and 55.18 never
    restores it -- only engineers do (55.26). So a bombed harbour recovers up to
    max_eff - blocked, never past the wreck. Returns the new level, or None if already
    at (or above) the ceiling -- nothing to regenerate."""
    ceiling = port.max_eff - port.blocked
    return port.eff + 1 if port.eff < ceiling else None

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
    """Stores a unit needs per GAME-TURN: 4 per TOE Strength Point (51.11), or a FLAT 1
    per Game-Turn for HQ/engineer units (51.13 -- one Stores Point regardless of TOE, NOT
    per point). Non-combat pieces (bare HQs, trucks) proxy the reduced rate; a dedicated
    engineer flag is deferred."""
    if unit.is_combat:
        return _STORES_RATE["combat"] * max(1, unit.strength)   # 51.11
    return _STORES_RATE["noncombat"]                            # 51.13: flat, not per TOE


def water_cost(unit: Unit, *, hot: bool = False) -> int:
    """Water a unit needs this Operations Stage (rule 52.4). Infantry: 1 flat (52.41,
    regardless of TOE). Vehicle/gun/truck: 1 per TOE Strength Point (52.42). Hot weather
    DOUBLES the requirement (rule 29.35: "During hot weather, water requirements for all
    units are doubled") -- so a 6-TOE panzer battalion pays 12, not 7; infantry's flat 1
    becomes 2 (unchanged from the old +1 proxy, which was only ever right for base 1).
    52.42's 'if it used any CPA' condition is charged for every on-map mobile unit under
    the one-Operations-Stage cadence; true per-stage gating waits for CHUNK 5."""
    base = max(1, unit.strength) if _is_vehicle_type(unit) else 1
    return base * 2 if hot else base


def captured_usable(commodity: str, qty: int) -> int:
    """How many Points of `commodity` an enemy may USE when he captures a dump holding `qty`
    (49.19 / 50.16 / 51.16). Ammunition is specialized: only one-third, ROUNDED UP, is usable
    and the rest are lost (50.16 -- and again, on the remaining third, at each recapture). Stores:
    fifty per cent (51.16). Fuel is non-denominational and passes intact (49.19); Water is untaxed
    (no rule names a capture loss for it). NB 50.16 says 'rounded up' explicitly while 51.16 gives
    no rounding, so the usable Stores half is FLOORED -- a flagged reading of the silence, not the
    round-up 50.16 spells out."""
    if commodity == AMMO:
        return math.ceil(qty / 3)      # 50.16: one-third, rounded up
    if commodity == STORES:
        return qty // 2                # 51.16: fifty per cent (usable half floored; see docstring)
    return qty                         # 49.19 Fuel non-denominational; Water untaxed


def _pool(su, commodity: str) -> int:
    return getattr(su, commodity.lower())          # one path for all four commodities


def reachable_supplies(state: GameState, unit: Unit, commodity: str):
    """Friendly supply units holding `commodity`, within half the unit's CPA,
    nearest first (deterministic). Trace blocked by enemy ZOC / units (32.16).

    THE WELL-CONTROL GATE, MEASURED AND REJECTED (kept as a note so it is not re-invented). game.wells
    models a well as one Supply Unit PER SIDE -- a flagged proxy for side-neutral geography -- which
    hands an invader a private, bottomless, Axis-owned well on every hex of the defender's homeland
    (AX-Well-Cairo, AX-Well-Alexandria: 125,000,000 Water Points apiece). The obvious repair is to
    deny a side any water source on a hex the enemy CONTROLS (54.41). Implemented and measured over
    5 seeds, it does not earn its place:

      * it changes NOTHING about the Delta, because the blocking above already does the job -- a
        GARRISONED city hex is enemy-OCCUPIED, so no trace ever reaches the well standing on it.
        With the rule-64.71 Delta garrison in place (campaign_claim.delta_garrison), Axis unit-turns
        on Alexandria/Cairo are ZERO in 5/5 seeds with the gate and ZERO without it;
      * and it is PERVERSE, because engine._record_control flips control to whoever last STOOD on a
        hex (54.41 is a rail-transport rule). One Italian column driving through El Daba therefore
        poisons the well against the Commonwealth for the rest of the war -- measured, the Eighth
        Army was denied ITS OWN WELLS IN ITS OWN COUNTRY behind the Axis rush, and its Game-Turn-12
        strength fell from 23 combat units to 17.

    What actually denies the enemy a well is standing on it. That is already modelled."""
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


# --- [32.32] MOTORIZATION POINTS -- what a desert column costs the lorry pool -------------------
# "THIRTY Motorization Points are required to transport one real supply unit" [32.32], and
# "Motorization Points are used IN PLACE OF Truck Points... treated in all aspects as MEDIUM Truck
# Points" [32.51]. One pool, one exchange rate, straight off the page: a desert column costs THIRTY
# MEDIUM TRUCK POINTS out of the same 60.33/60.43 park that hauls the army's freight.
#
# FLAGGED, the single interpolation in this rule: 32.51 denominates a Motorization Point as a MEDIUM
# Truck Point and the rulebook offers NO Light/Heavy conversion, so none is modelled -- a column is
# raised from Medium Truck Points or it is not raised. (A side with only Heavy lorries could not
# form one. Both charted parks are Medium-heavy -- Axis 150 M of 215 on-map, Commonwealth 130 of 195
# -- so the constraint bites where the rulebook aims it, at the freight backbone, and nowhere else.)
# FLAGGED PROXY, and it is the biggest one in this rule: THE COLUMN HAS NO GEOGRAPHY. The thirty
# Points are a SIDE-WIDE claim on the Medium park -- the ledger does not require the lorries to be
# anywhere near the depot they are carrying, because routing lorries to depots is a truck-dispatch
# subsystem this engine does not have. The consequence is that only the SIZE of the Medium park
# matters, and that collides with a flagged omission: [60.33] charts 140 Medium Truck Points at
# TRIPOLI, which game.scenario._campaign_axis_trucks cannot seed because Tripoli has no hex on the
# playable map. So the Axis fights on 150 of its charted 290 Medium Points -- and 150 is EXACTLY
# five columns. A staff that raises five therefore has NOTHING left to haul with, and its Benghazi
# lifeline stops dead (measured: Axis freight 1,143,908 -> 298,489 in seed 99). That knife-edge is
# ours, not the rulebook's. Seeding the Tripoli row, or modelling co-location, is the next lever.
MOTORIZATION_POINTS = 30                 # [32.32] per REAL supply unit (a dummy needs 6 -- deferred
                                         # with the rest of the 32.18 dummy-counter game)
MOTORIZATION_CLASS = "medium"            # [32.51] "treated in all aspects as Medium Truck Points"


def committed_points(state: GameState, truck_id: str) -> int:
    """[32.32] Truck Points of `truck_id` standing under a supply column right now -- lorries that
    are carrying a depot and are therefore NOT hauling freight. The whole cost of the rule."""
    return sum(pts for legs in state.motorization.values()
               for tid, pts in legs if tid == truck_id)


def free_points(state: GameState, truck: TruckFormation) -> int:
    """The Truck Points of `truck` still available to the freight relay: its strength less whatever
    32.32 has reserved under a desert column. This is the contested pool, and it is why pushing a
    depot forward is a DECISION rather than a free gift (engine._truck_order feeds the convoy a
    formation reduced to exactly this, so both the 53.12 load ceiling and the 49.18 fuel burn shrink
    with it)."""
    return truck.points - committed_points(state, truck.id)


def motorized(state: GameState, dump_id: str) -> bool:
    """[32.32] "A supply unit not assigned the minimum necessary number of Motorization Points MAY
    NOT BE MOVED." Does this dump have its thirty?"""
    legs = state.motorization.get(dump_id, ())
    return sum(pts for _, pts in legs) >= MOTORIZATION_POINTS


def column_legs(state: GameState, side: Side, truck_ids: tuple) -> tuple:
    """Draw MOTORIZATION_POINTS from the named formations: ((truck_id, points), ...), or () if they
    cannot muster the thirty between them (32.32).

    ACROSS formations deliberately. A column is thirty Truck Points, not one lorry group: the
    Commonwealth's charted park is dispersed over Cairo / Alexandria / the railhead by 60.43's own
    restrictions, and forcing each column to come out of a single formation would strand its 20-point
    Alexandria row forever and cost the Commonwealth a column the CHART gives it -- an artefact of
    how we pooled the rows into formations, not a rule.

    THE SLACKEST FORMATION FIRST, and this is not cosmetic. Drawn in the order the caller happened to
    name them, the first column took ALL TWENTY of the Alexandria row's Medium Points and left it with
    none -- and a formation with nothing free hauls nothing at all (engine._truck_order), so a single
    thirty-point column DELETED A WHOLE LORRY GROUP from the relay. Measured: one column cost the
    Commonwealth 40% of its freight, when thirty of its 130 Medium Points is 23% of the class. A
    quartermaster details lorries off the group that has them to spare; taking the last twenty from a
    twenty-point group is not a rule, it is a bug."""
    need, legs = MOTORIZATION_POINTS, []
    pool = sorted((t for t in (state.truck(tid) for tid in truck_ids)
                   if t is not None and t.side == side          # 32.51: a column is MEDIUM Truck
                   and t.truck_class == MOTORIZATION_CLASS),    # Points, and only those
                  key=lambda t: (-free_points(state, t), t.id))
    for t in pool:
        take = min(need, free_points(state, t))
        if take > 0:
            legs.append((t.id, take))
            need -= take
        if need == 0:
            return tuple(legs)
    return ()                                          # 32.32: short of thirty -> no column at all


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


# --- [54.14]/[54.17] BLOWING A SUPPLY DUMP ------------------------------------
_DEMOLITION_54_17: dict = logistics_data.demolition_percent_54_17()
DEMOLITION_MAX_THIRDS = 2      # 54.14: "an additional one-third or two-thirds" of basic CPA


def demolition_cp(unit: Unit, extra_thirds: int = 0) -> int:
    """54.14: the Capability Points an attempt to blow a dump costs -- one-third of the attempting
    unit's BASIC CPA (rounded up), plus each `extra_thirds` the Player announces before rolling to
    buy a +1 on the die. "The attempting Player may never expend more than the unit's basic CPA
    attempting to blow a dump", so the whole bill is clamped at the CPA."""
    third = math.ceil(unit.cpa / 3)
    return min(unit.cpa, third * (1 + max(0, min(extra_thirds, DEMOLITION_MAX_THIRDS))))


def demolition_modifier(dump: SupplyUnit, terrain: Terrain, *,
                        extra_thirds: int = 0, stack_points: int = 1) -> int:
    """54.17's cumulative die-roll modifiers for an attempt on `dump`.

      +1  for each additional 1/3 of basic CPA expended (54.14)
      -1  if the attempting unit(s) total one Stacking Point or less
      -2  if the attempt is made in a Major City hex.  IF NOT, THEN
      +1  if the total of the dump's supplies is 500 points or less

    Two readings that are load-bearing, and both are the chart's own words:

      * "the attempting UNIT(S) TOTAL one Stacking Point or less" is a test on the STACK, not on the
        counter -- `stack_points` is the total Stacking Points of the friendly units on the dump's
        hex. It has to be. EVERY combat counter in this OOB is a battalion-equivalent of exactly ONE
        Stacking Point, so reading it per-unit would fire the -1 on every attempt in the game and
        the modifier would be a constant, not a modifier. A lone battalion gets the -1; a proper
        stack does not, which is the distinction the chart is drawing.
      * the city clause and the small-dump clause are EXCLUSIVE ("-2 if in a Major City hex. IF NOT,
        THEN +1 if the dump is 500 or less") -- the one piece of structure in the modifier list.

    DEFERRED AND FLAGGED: the chart's "+1 if the attempting unit is a full (non-shell) division".
    game.state.Unit carries no organisation size and no division-shell status -- every counter here
    is a battalion-equivalent -- so the modifier has nothing to key off. Omitting it is the
    CONSERVATIVE half (it can only ever help the demolisher), which is the right way to be wrong
    about a rule that lets a retreating army deny its stocks."""
    mod = max(0, min(extra_thirds, DEMOLITION_MAX_THIRDS))
    if stack_points <= 1:
        mod -= 1
    if terrain == Terrain.MAJOR_CITY:
        mod -= 2
    elif dump.ammo + dump.fuel + dump.stores + dump.water <= 500:
        mod += 1
    return mod


def demolition_percent(modified_die: int) -> int:
    """54.17: the percentage of EVERY commodity in the dump destroyed, by modified die. Clamped to
    the chart's end rows ("-2" and "8 or more")."""
    return _DEMOLITION_54_17[max(-2, min(8, modified_die))]


def demolition_loss(dump: SupplyUnit, pct: int) -> dict:
    """The Points of each commodity a `pct` demolition destroys. Rounded DOWN, so a blown dump that
    still holds a point still holds it -- the conservative half, and the one that keeps a 33% result
    from quietly emptying a nearly-empty dump."""
    return {c: _pool(dump, c) * pct // 100 for c in COMMODITIES if _pool(dump, c) * pct // 100 > 0}


def can_blow(unit: Unit, dump: SupplyUnit) -> bool:
    """54.14: who may attempt. "Only NON-GUN units may attempt to blow dumps" -- and the unit must
    be alive, a combat unit standing ON the dump's hex, with the CP left to pay the 1/3-CPA bill."""
    return (unit.is_combat and not unit.is_gun and unit.hex == dump.hex
            and unit.cpa - unit.cp_used >= demolition_cp(unit))


def affordable_thirds(unit: Unit, requested: int) -> int:
    """The largest number of EXTRA thirds of basic CPA (0..`requested`, capped at the 54.14 maximum
    of two) that `unit` can still pay for this Operations Stage.

    54.14 twice: "the attempting Player may never expend more than the unit's basic CPA attempting
    to blow a dump", and "a unit may not exceed its CPA to blow a dump". So the +1s the Player buys
    before rolling are bounded by the CP he actually has left, not merely by the chart. A unit that
    has spent most of its stage retreating gets the bare attempt and no bonus -- which is exactly
    the tension the rule is for."""
    left = unit.cpa - unit.cp_used
    return max((n for n in range(min(requested, DEMOLITION_MAX_THIRDS), -1, -1)
                if demolition_cp(unit, n) <= left), default=0)


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
