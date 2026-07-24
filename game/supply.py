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
from collections import OrderedDict
from dataclasses import dataclass

from . import air, logistics_data, movement, tactics
from .events import CONTROL_OF
from .hexmap import Coord, neighbors
from .state import GameState, Port, Side, SupplyUnit, TruckFormation, Unit
from .terrain import Mobility, NON_MOT_CLASSES, Terrain

AMMO = "AMMO"
FUEL = "FUEL"
STORES = "STORES"
WATER = "WATER"
COMMODITIES = (AMMO, FUEL, STORES, WATER)
# [56.22] The three commodities an Axis naval convoy may carry: "the Axis Player may now plan to
# ship any amounts (within the limits of allowable tonnage) of FUEL, AMMUNITION, AND STORES that he
# wishes." Water is NOT among them -- it comes out of the ground (52.7 wells) and off the railway,
# never off a ship -- so the Convoy Planning Phase re-validates a plan against this tuple.
CONVOY_COMMODITIES = (AMMO, FUEL, STORES)

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


def fuel_capacity(unit: Unit) -> int:
    """[49.14] A unit's Fuel Capacity rating -- the fuel its own vehicles carry (the 49.15 in-hex
    tank). The rule prints "CPA x 1/5 x fuel-consumption-rate" per TOE Strength Point, and its Note
    is the operative identity: "a TOE Strength Point always has a fuel capacity rating exactly
    sufficient to allow all its CPA to be expended on movement." A full-CPA move costs exactly
    fuel_cost(unit, unit.cpa) (49.13, rate x ceil(CPA/5) x strength), so the tank "exactly
    sufficient" for it holds precisely that -- which also resolves the rule's fractional "CPA x 1/5"
    for a CPA not divisible by 5 (the move charges the ceil, so the tank must match). Non-motorized
    units walk and burn nothing (49.12, fuel_rate 0), so their capacity is 0."""
    return fuel_cost(unit, unit.cpa)


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


def ammo_capacity(unit: Unit) -> int:
    """[50.0] The intrinsic 'fire once' basic load a unit carries WITHOUT trucks -- rule 50.0 GENERAL
    RULE, scan PDF p.67: "Each TOE Strength Point may carry (i.e., transport by itself without trucks)
    only enough ammo to fire once." The exact dual of fuel_capacity (49.14, "a fuel capacity rating
    exactly sufficient to allow all its CPA to be expended on movement"): fuel_capacity holds one full
    MOVE, ammo_capacity one full FIRING. It is enough Ammo Points (50.14: rate x TOE Strength Points)
    for the unit's most-demanding combat function, so a full pool always affords exactly one firing of
    any function the unit has, and is empty after. First-line trucks and dumps hold MORE ammo (50.17)
    but are NOT this innate carry -- the unit draws this pool first (49.16), then a co-located dump. A
    non-combat unit (no barrage/anti-armor/assault strength) carries none. NOTE (flagged proxy): AA/flak
    (50.12's "AA points", 50.2's anti_air rate) is deliberately NOT sampled -- the land engine charges
    no flak ammo (no `anti_air` activity is ever drawn) and the 50.2 AA rate is per target group, not
    per TOE point, so `x strength` would not apply. Harmless in this OOB: every is_pure_aa counter also
    carries anti_armor/dca and so gets a nonzero pool here; a hypothetical PURE-flak unit (no other
    combat function) would compute 0 and needs the AA firing model before it can be sampled."""
    rates = []
    if unit.barrage > 0:
        rates.append(AMMO_RATE["barrage"])
    if unit.anti_armor > 0:
        rates.append(AMMO_RATE["anti_armor"])
    if unit.oca > 0 or unit.dca > 0:
        rates.append(AMMO_RATE["assault"])
    return max(rates) * max(1, unit.strength) if rates else 0


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


def is_sgsu(unit: Unit) -> bool:
    """[35.11] A Squadron Ground Support Unit. One definition, in game.air beside the rest of rules
    35/36; re-exported here so a logistics caller can ask the logistics question in logistics terms.
    An SGSU is NOT a land unit for supply purposes: its
    upkeep is 35.14's own (1 Stores/Game-Turn + 1 Fuel + 1 Water/Operations Stage, drawn from its
    facility's 36.17 dump), so it is exempt from the rule-51/52 land Stores/Water demand and is
    charged separately by engine._sgsu_upkeep."""
    return air.is_sgsu(unit)


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


@tactics._PositionMemo
def trace_blocked(state: GameState, side: Side) -> frozenset:
    """THE TRACE BLOCKING, in one place: the hexes no line of supply of `side` may run through --
    every hex an enemy unit stands on, plus every hex in an enemy combat unit's Zone of Control
    that no friendly unit is standing on to negate.

    Every trace in this module reads exactly this set and always did; it was written out three times
    (reachable_supplies, reachable_moves, reachable_truck_moves) and the 64.71 truck-MP line was
    about to make a fourth and a fifth. One expression -- the sets and the order are identical to
    the three copies it replaces, so no existing trace moves by a byte.

    TWO RULES SPECIFY THIS ONE SET, AND EACH CALLER CITES ITS OWN. That matters, because THE PORT
    PLAN names the abstract game's load-bearing presence in the full game as the deepest bug in the
    project, and a reader who follows one citation to chapter 32 would conclude every caller here is
    infected. They are not:
      * 32.16 (ABSTRACT logistics) -- "The supply line may not be traced thru impassable terrain or
        enemy ZOC's unoccupied by Friendly units." This is reachable_supplies's authority, and
        reachable_supplies is the abstract cpa/2 draw, so it is the right one there.
      * 10.29 + 10.26 (ZONES OF CONTROL -- a CORE chapter, and the FULL game) -- "Truck Convoys may
        not enter an Enemy ZOC unless such hex is already occupied by a Friendly combat unit", and
        "the presence of a Friendly combat unit in a hex negates the effect of an Enemy ZOC". This
        is the authority for every trace here that a LORRY drives: reachable_moves, the carry
        (reachable_truck_moves), and the 64.71/64.72 convoy route (truck_trace_reach,
        truck_supply_line). 64.71 glosses its own "line of supply" as "(i.e., convoy route)", and a
        convoy route is the route a Truck Convoy takes; 10.29 says where one may not go. So the
        blocking on the 64.71 line is the full game's own, not an abstract-game import.
    The two texts pick out nearly the same hexes, which is why one expression serves. The
    authorities are not the same and are not interchangeable.

    FLAGGED, THE ONE PLACE THE TWO TEXTS DIVERGE, and this code follows 32.16: the NEGATOR. 32.16
    negates a ZOC with "Friendly units" -- any of them -- and `friendly` below is state.living(side),
    which is exactly that. 10.26 and 10.29 both say "Friendly COMBAT unit". So a bare HQ or a lorry
    sitting in an enemy ZOC negates it here, where the full game says only a fighting unit can. The
    divergence is PRE-EXISTING (all three original traces read this set), it is small (10.29's own
    last sentence CAPTURES a lone non-combat unit in an enemy ZOC, so such a negator rarely survives
    to negate anything), and it is NOT repaired here because narrowing it would move three traces
    that are correctly on 32.16's authority and are not what this pass was opened to fix. Named so
    it is not mistaken for the rulebook: splitting the negator by caller is the fix when it matters."""
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(state, side)
    friendly = frozenset(u.hex for u in state.living(side))
    return (enemy_zoc - friendly) | enemy_occupied


class _ReachMemo:
    """Bounded LRU memo for the movement.reachable FLOOD under a supply trace.

    Every supply trace here (reachable_supplies / reachable_moves / reachable_truck_moves /
    truck_trace_reach) floods the SAME terrain with NO terminal/passable predicate and a zero
    start_cost, so each reach map is a pure function of (terrain, start, budget, mobility, blocked,
    weather). The commodity NEVER entered the search -- reachable_supplies filters the dumps LIVE,
    per commodity, AFTER the flood (dumps drain between draws, so that filter must stay live) -- so
    the search half is shared across all four commodities and across the policy-plans / engine-emits
    double evaluation. Measured 78% exact-key duplicates on the campaign; this memo removes them.

    THE KEY is (id(tmap), start, budget, mobility, blocked, start_cost, weather) and pointedly NOT
    any unit/truck id. The victory (64.71/64.72) and claims traces flood from
    `dataclasses.replace(piece, hex=...)` SYNTHETIC pieces that KEEP THE ORIGINAL id, so an id key
    would collapse two genuinely different start hexes onto one reach map and corrupt the event
    stream (a prototype keyed on id went 2561 -> 2884 events). The start HEX is in the key; the id is
    not. `blocked` is the frozenset ITSELF -- content-hashed and self-invalidating, because a unit
    that moves rebuilds trace_blocked to a different set and so to a different key (and trace_blocked
    already returns the SAME frozenset by reference within a phase, so the key hash is near-free).

    ID REUSE of id(tmap) is closed exactly as tactics._PositionMemo closes it for id(state.units):
    the entry holds a STRONG REFERENCE to tmap, so no live entry's id can be reused by another map.
    Terrain is rebuilt only by rail construction / scenario setup, and a rebuilt map takes a fresh id
    -> fresh entries; stale ones evict. maxsize bounds memory and never affects correctness -- an
    evicted key simply recomputes the identical flood.

    Determinism: the value is a pure function of the complete key, returned BY REFERENCE and only
    ever READ by callers (membership / indexed lookup -- audited at every call site) -> the event log
    is byte-identical to the un-memoized flood."""

    def __init__(self, maxsize: int = 1024) -> None:
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize

    def reach(self, tmap: movement.TerrainMap, start: Coord, budget: float, mobility: Mobility,
              blocked: frozenset, *, start_cost: float = 0.0, weather: str = "normal") -> dict:
        key = (id(tmap), start, budget, mobility, blocked, start_cost, weather)
        entry = self._cache.get(key)
        if entry is not None:
            self._cache.move_to_end(key)
            return entry[1]
        value = movement.reachable(tmap, start, budget, mobility, blocked=blocked,
                                   start_cost=start_cost, weather=weather)
        self._cache[key] = (tmap, value)          # hold the tmap ref: pins its id() against reuse
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)
        return value


_reach = _ReachMemo()


def reachable_supplies(state: GameState, unit: Unit, commodity: str):
    """Friendly supply units holding `commodity`, within half the unit's CPA,
    nearest first (deterministic). Trace blocked by enemy ZOC / units (32.16).

    [36.17] AIR DUMPS ARE INVISIBLE HERE TO EVERY LAND UNIT, and visible to an SGSU -- the identical
    `air_ok` split colocated_dumps makes, for the identical reason ("land units may not use airfield
    supply dumps... any SGSU at an airfield may make use of the supplies there"). The SGSU half is
    load-bearing for the one commodity its 35.14 upkeep still draws down this trace (WATER -- see
    engine._sgsu_upkeep): without it a squadron could not drink from the dump it is standing on.

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
    reach = _reach.reach(state.terrain, unit.hex, budget, mob,
                         trace_blocked(state, unit.side))
    air_ok = air.is_sgsu(unit)                                       # 36.17, see the docstring
    out = [su for su in state.active_supplies(unit.side)
           if su.hex in reach and _pool(su, commodity) > 0 and (air_ok or not su.air_dump)]
    out.sort(key=lambda su: (reach[su.hex], su.id))
    return out


def reachable_moves(state: GameState, dump: SupplyUnit) -> dict:
    """Hexes a carried supply unit can relocate to this OpStage: within CPA 15
    (rule 32.58A) as medium-truck movement, blocked by enemy ZOC not negated by a
    friendly unit (the 32.16 trace blocking, reused for the carry)."""
    return _reach.reach(state.terrain, dump.hex, SUPPLY_CPA, SUPPLY_MOBILITY,
                        trace_blocked(state, dump.side))


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


def first_line_capacity(unit: Unit, commodity: str) -> int:
    """[54.2] The carrying CEILING of a unit's organic first-line trucks (53.11) for one commodity:
    the sum over the three classes of its Truck Points times that class's 54.2 per-Point capacity
    (Light 2 Ammo / 50 Fuel / 6 Stores / 40 Water; Medium 4/120/15/100; Heavy 8/250/30/200). This is
    what the [60.31]/[60.41] fl_light/fl_medium/fl_heavy allotment BUYS -- the amount of `commodity`
    the unit's own lorries may hold, buffered from a co-located dump and carried forward with the unit
    (the way Port.cap_* is a port's ceiling). A unit with no first-line trucks has capacity 0 and
    carries nothing of its own beyond the intrinsic 49.14 fuel tank / 50.0 ammo load.

    FLAGGED SIMPLIFICATION (53.12): each commodity is given the trucks' FULL point-capacity
    independently, rather than the shared fractional cap truck_load_admissible enforces on a real
    convoy (Sigma_c cargo_c/cap_c <= points) -- a lorry cannot in fact carry a full load of fuel AND
    a full load of stores at once. Over-generous in the direction the design (phase4 sec 3.3) argues
    for erring, and it never binds for fuel/ammo (which refill only to their small intrinsic pool);
    it is load-bearing only as the stores/water buffer ceiling, where the true mix is the player's
    free choice anyway."""
    return (unit.fl_light * truck_capacity("light")[commodity]
            + unit.fl_medium * truck_capacity("medium")[commodity]
            + unit.fl_heavy * truck_capacity("heavy")[commodity])


def truck_load_admissible(truck: TruckFormation, added: dict) -> bool:
    """53.12 load admissibility: a formation of N Truck Points may carry any mix whose
    fractional capacity use sums to <= N -- sum_c(cargo_c / cap_per_point_c) <= points,
    evaluated on the cargo the truck would hold AFTER adding `added`. (A truck 'may carry
    anything', 53.12, so the four commodities share the Points fractionally.)"""
    cap = truck_capacity(truck.truck_class)
    frac = sum((getattr(truck, c.lower()) + added.get(c, 0)) / cap[c] for c in COMMODITIES)
    return frac <= truck.effective_points + 1e-9      # 21.44: a broken lorry carries nothing


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
    with it). Broken-down Truck Points (21.44) are already off effective_points, so they neither
    haul freight nor may be detailed under a 32.32 column."""
    return truck.effective_points - committed_points(state, truck.id)


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
    friendly unit (the identical 32.16 trace-blocking reused from reachable_moves).

    NOT the 64.71 line of supply -- see truck_trace_reach below. This is one lorry's MOVE in one
    Phase, budgeted at the formation's own convoy CPA (30 or 40); that is a trace of an army's
    supply line, budgeted at the rulebook's 90 or 60."""
    return _reach.reach(state.terrain, truck.hex,
                        truck_convoy_cpa(truck.truck_class), SUPPLY_MOBILITY,
                        trace_blocked(state, truck.side))


# [21.11]/[54.2] The mobility class a truck accrues Breakdown Points AS -- only Light Trucks
# carry the 54.2 off-road +1 BP/hex+hexside penalty; Medium/Heavy accrue the plain motorized
# value. (Movement COST is Medium for every class, SUPPLY_MOBILITY -- the classes differ only
# in Breakdown Points, so the chosen path is the same and only the accrual differs.)
_TRUCK_BP_MOBILITY = {"light": Mobility.LIGHT_TRUCK,
                      "medium": Mobility.MOTORIZED, "heavy": Mobility.MOTORIZED}


def truck_bp_for_move(state: GameState, truck: TruckFormation, dst: Coord) -> float:
    """Breakdown Points a convoy accrues relocating to `dst` this Truck Convoy Phase (21.21),
    over the same min-CP path reachable_truck_moves reached it by, accrued at the truck's own
    54.2 class (light trucks pay the off-road +1). The engine feeds this into the TRUCK_MOVED
    faucet the way bp_for_move feeds UNIT_MOVED. Zero for a hop with no motorized accrual, so a
    scenario whose trucks never leave a road stays byte-identical."""
    _, prev = movement.reachable_prev(state.terrain, truck.hex,
                                      truck_convoy_cpa(truck.truck_class), SUPPLY_MOBILITY,
                                      blocked=trace_blocked(state, truck.side))
    path = movement.reconstruct_path(prev, truck.hex, dst)
    if len(path) < 2:
        return 0.0
    mob = _TRUCK_BP_MOBILITY[truck.truck_class]
    weather = state.weather_at(truck.hex)               # 29.7: the storm the convoy set out under
    return sum(movement.breakdown_points(state.terrain, a, b, mob, weather)
               for a, b in zip(path, path[1:]))


# --- [64.71]/[64.72] THE LINE OF SUPPLY, IN TRUCK MOVEMENT POINTS ------------------------------
# Rules 64.71 and 64.72 both turn on ONE trace, and it is not any of the three above. A combat unit
# must "trace a line of supply (i.e., convoy route) back to a Supply Dump which in turn can be
# supplied from Tobruk or Tripoli in any way, and that line is 90 movement points by truck or less"
# (64.71); 64.72 asks the same question of every Axis combat unit at 60. So the trace has TWO legs
# and the rulebook budgets them differently, which is the whole shape of the rule:
#
#   * UNIT -> DUMP is CAPPED, at 90 Truck Movement Points (64.71) or 60 (64.72). This is the leg
#     that decides whether a spearhead is on the end of a supply line or on the end of a rope.
#   * DUMP -> TOBRUK/TRIPOLI is NOT CAPPED. "In any way" is the magnitude: the book does not care
#     how far back the harbour is, or by what means the depot is filled -- only that the road home
#     is open. So that leg is pure truck-passable CONNECTIVITY, at any length (truck_supply_line).
#
# Denominated in MEDIUM truck movement (SUPPLY_MOBILITY), which is how this engine already carries
# every supply point (32.51: a Motorization Point is "treated in all aspects as a Medium Truck
# Point"). FLAGGED: 64.71 says "by truck" and 64.72 "(Truck)" without naming a class, and the 8.37
# Terrain Effects Chart charges Light/Medium/Heavy the same CP anyway (the classes differ in
# Breakdown Points, 54.2, which a trace does not accrue) -- so the class is immaterial to the cost
# and Medium is the engine's own denomination, not a choice made here.
#
# 🔴 FLAGGED -- THE ROAD NET DECIDES THIS RULE AND THE ROAD NET IS NOT TRANSCRIBED. The two
# constants below are the book's, to the digit. The METRIC they are compared against is not yet the
# book's, and on this rule that is the whole ball game, because a 90-MP line's cost is almost
# entirely road entry (ROAD_ENTRY[motorized] = 0.5 against 2.0 for a clear hex off-road).
# MEASURED on game.scenario.campaign():
#   * the whole map carries 277 road edges across 6770 hexes;
#   * the min-cost Tobruk -> Alexandria trace runs 90 steps: 32 on road, 8 on track, and 50 on
#     NOTHING -- open desert at 4x the road rate (ROAD_ENTRY 0.5 against a clear hex's 2.0);
#   * it therefore costs 122.5 truck-MP, where those same 90 steps on a continuous road would cost
#     45. That counterfactual walks the engine's OWN coastal path and changes only the surface
#     under it, which is the honest comparison. It is NOT the [37.42] Land Distance Chart's 78
#     hexes for this stretch: 37.42 sits in chapter 37, FLIGHT, and its own footnote says its
#     distances "include cutting across the Mediterranean (assuming an all-sea hex grid) where
#     necessary" -- a crow-flies air distance no lorry can drive, and not a road length.
# The book asserts road continuity along exactly this coast: 8.85 strings arriving Stacking Points
# "on the Road in consecutive hexes (road) from the Tripolitania box; e.g., 5 points in hex 2802, 5
# points in 2803, and 3 points in 2804", and 61.43C distributes dumps "in any of the road hexes
# between El Agheila (A 1816) and Nofilia (A 2703) inclusive". Both name a CONTINUOUS road where
# this map has a dotted line. (61.43C is a Desert Fox rule, not the campaign's -- cited only as the
# book's evidence about the MAP, which every scenario shares.) So the Via Balbia is a road in the
# book, and every truck-MP number this trace yields is roughly 2-3x too dear.
# This is the SAME map-transcription defect game.campaign_victory flags for the Gulf of Sirte
# coastline (A2802/A1816 colour-sampling as sea), applied to roads instead. NOT FIXED HERE, and for
# the same reason: it is a map job, and bending a road into existence to make a victory rule fire is
# the invention this port exists to stop. FIXED IN THE RECORD, though -- the first cut of this port
# adopted the inflated number as design intent and shipped "MEASURED -- the rule bites" on the back
# of it. It does not bite for the reason claimed; see game.campaign_victory.CampaignVictory.check.
TRUCK_MP_64_71 = 90       # 64.71: the Axis Delta occupiers' line back to a Tobruk/Tripoli-fed dump
TRUCK_MP_64_72 = 60       # 64.72: every Axis combat unit's line, from Game-Turn 35


@dataclass(frozen=True, slots=True)
class SupplySource:
    """One of 64.71/64.72's two named supply sources -- "Tobruk or Tripoli" -- and WHICH KIND of
    thing it is, because the book's two are not the same kind and 56.15 only reaches one of them.

    `capturable` is the rulebook fact, not an engine dial:
      * TOBRUK (C4807) is an on-map PORT. The Commonwealth can take it, and when it does 56.15
        cancels the convoys -- "a convoy scheduled to arrive at a port that is captured by the
        Commonwealth is cancelled. It never sails." So: capturable=True, and the gate is live.
      * TRIPOLI is an off-map BOX (8.81 puts the Tripoli/Tunisia boxes on the western edge of Map A;
        8.88 makes them Supply Dumps of unlimited capacity). 56.15 is not switched off for it -- its
        ANTECEDENT IS UNSATISFIABLE. 8.82: "Only Axis units and Commonwealth airplanes may enter the
        Tripoli/Tunisia region. NO COMMONWEALTH LAND OR SEA UNIT MAY EVER ENTER ANY OF THE BOXES."
        A port no Commonwealth unit may ever enter is a port the Commonwealth may never capture, so
        the convoy is never cancelled and the source never shuts. capturable=False.

    AND HEX A2802 IS NOT TRIPOLI. It is the on-map GATEWAY the book names for the box (8.85), and
    this engine has no off-map box, so the source is anchored there as a PROXY (flagged in
    data/victory_cities.json and game.campaign_victory). A2802 is an ordinary desert road hex: the
    Commonwealth may stand on it, and standing on it captures nothing. Gating the proxy hex on 56.15
    made an UNCAPTURABLE source capturable and handed the Commonwealth a win 8.82 forbids -- see
    truck_supply_line for what that measured.

    THE COMMONWEALTH CAN STILL SHUT THE ROAD BY STANDING ON IT, and that is the rule that actually
    governs a unit in a hex: 10.29 bars a Truck Convoy from entering an unnegated enemy ZOC, and
    `blocked` is applied to every hex the flood ENTERS. MEASURED on the GT1 campaign board, with
    Tobruk captured so the box is the only source left:
      * ONE Commonwealth battalion on A2802 leaves the Axis all 13 fed dumps -- it exerts no ZOC at
        all. That is 10.11's own gate ("more than one Stacking Point"), not a hole: one battalion is
        1 Stacking Point.
      * TWO put the gateway's three existing neighbours in ZOC and take the Axis to 0 fed dumps.
    So the road CAN be cut at the gateway -- by a force, standing there, under the book's own
    movement rule. That is categorically not what the capture gate did, and the difference is why
    this distinction is worth a field: a ZOC needs a force to hold and the Axis can answer it (10.26
    negates it with a combat unit of its own, or it can be driven off), where CAPTURE needs no force
    at all -- a control marker outlives the column that set it and no Axis action lifts it.

    FLAGGED, AND IT IS THE MAP, NOT THE RULE: two units shut Tripolitania here because the gateway is
    ONE hex. The book gives it a road frontage -- 8.85 strings arriving Stacking Points "in
    consecutive hexes (road) from the Tripolitania box; e.g., 5 points in hex 2802, 5 points in 2803,
    and 3 points in 2804", and 61.43C names El Agheila (A1816) a road hex -- and A2803/A2804/A1816
    all colour-sample as SEA on this map. So the chokepoint is ours, the block is the book's, and the
    fix is the map job already flagged in game.campaign_victory, not a thumb on this scale."""
    hex: Coord
    capturable: bool


def truck_trace_reach(state: GameState, unit: Unit, budget: float) -> dict:
    """The hexes `unit` can trace a 64.71/64.72 line of supply to within `budget` TRUCK Movement
    Points: medium-truck movement over the terrain, blocked by the trace blocking -- here on
    10.29's authority (a Truck Convoy may not enter an unnegated enemy ZOC), which is the FULL
    game's own rule, not 32.16's abstract one. See trace_blocked.

    TRUCK movement for EVERY unit, foot battalions included, and that is the rule's own word. The
    32.16 tactical draw asks how far the UNIT can go (reachable_supplies walks leg infantry at
    Mobility.FOOT, since a marching battalion carries its own load); 64.71 asks how far the LORRIES
    can come, which is a question about the road, not about the boots. "A line of supply (i.e.,
    convoy route) ... 90 movement points by truck" measures the convoy, and the convoy is a convoy
    whoever is waiting at the end of it.

    DEFERRED, WEATHER (29.44 / 29.56), AND NAMED HERE BECAUSE IT IS WORTH MORE ON THIS TRACE THAN
    ON ANY OTHER. movement.reachable takes a `weather=` argument and no trace in this module passes
    it, so all four take the default "normal". 29.44 DOUBLES every movement cost in a Sandstorm and
    29.56 degrades a Road to a Track in a Rainstorm -- which on a 90-MP line, whose cost is almost
    all road entry, is worth roughly half the ground. NOT coupled here, deliberately and for two
    reasons: (1) the gap is the same in all four traces and coupling one of them alone would make
    this module inconsistent with itself, so it is one job (a T0-11 follow-up: TerrainMap.sections
    and state.weather_at already exist, which is why the note is a deferral and not a design); and
    (2) 64.71 asks whether a line CAN be traced, which is a hypothetical about the road and names no
    weather to evaluate it in -- so which weather a hypothetical convoy drives through is a real
    open question of reading, not an oversight to be silently closed. It is flagged, not adopted."""
    return _reach.reach(state.terrain, unit.hex, budget, SUPPLY_MOBILITY,
                        trace_blocked(state, unit.side))


def truck_supply_line(state: GameState, side: Side,
                      sources: "tuple[SupplySource, ...]") -> frozenset:
    """64.71's "which in turn can be supplied from Tobruk or Tripoli IN ANY WAY": every hex a lorry
    of `side` could carry supplies to from any of `sources` -- the Tobruk and Tripoli harbours --
    over ANY length of open road. Unbudgeted by construction: "in any way" is the rule declining to
    measure this leg at all, where it measures the unit's own leg at 90 or 60.

    A CAPTURABLE SOURCE IN ENEMY HANDS SUPPLIES NOBODY, and the test is not invented here -- it is
    56.15's, verbatim, the one the engine's own convoy gate already reads (engine._convoy_dest):
    "a convoy scheduled to arrive at a port that is CAPTURED by the Commonwealth is cancelled. It
    never sails." A harbour that receives no convoy fills no dump behind it. So the Commonwealth
    RETAKING Tobruk does not merely lengthen the Axis road home: it switches the source off, and
    every dump behind it stops being a dump the Axis can win the war through.

    ADJACENCY IS NOT CAPTURE, AND THIS GATE USED TO SAY IT WAS. Until this repair the source was
    ALSO shut by `src in trace_blocked(...)` -- i.e. by an unnegated enemy ZOC on the quay -- with
    56.15 cited as the authority. 56.15's whole text is the sentence above; it says captured, and a
    unit standing NEXT TO Tobruk has not captured Tobruk. No rule shuts a port for adjacency. The
    invented gate was measured on the real GT1 campaign board and it was CATASTROPHIC: four
    Commonwealth combat units on (16,66) -- one hex from Tobruk (15,66), not on it, with the quay
    Axis-controlled and 56.15's own test therefore PASSING -- collapsed fed_dumps from 13 to 0 and
    every one of the Axis's 96 combat units out of the 60-MP trace. The moment 64.72 is wired that
    is a Commonwealth automatic win at Game-Turn 35 bought with one recce stack. It is now gone.

    AND IT REACHES ONLY A SOURCE THE COMMONWEALTH CAN ACTUALLY CAPTURE (SupplySource.capturable),
    WHICH IS THE SECOND HALF OF THE SAME LESSON. Until this repair the gate ran over every source
    alike, and the moment Tripoli was wired in that shut the OFF-MAP BOX -- a source 8.82 puts
    permanently beyond Commonwealth reach ("No Commonwealth land or sea unit may ever enter any of
    the boxes") -- because this engine anchors it at its on-map gateway PROXY hex, A2802, which is an
    ordinary desert hex the Commonwealth may walk onto. MEASURED on the real GT1 campaign board:
    Control.ALLIED on BOTH C4807 (Tobruk) and A2802 took fed_dumps from 13 to 0 and cut every one of
    the Axis's 96 on-map combat units out of the 60-MP trace -- i.e. from Game-Turn 35 one
    Commonwealth unit on one far-west desert hex, with Tobruk taken, ended the war outright with the
    whole Panzerarmee alive and stocked. That is "the Commonwealth wins if it holds Tobruk" wearing a hat:
    the same class of defect as the invented ADJACENCY gate two paragraphs down, reintroduced one hex
    further west, and 56.15 was cited for it in both cases. A proxy may stand in for a hex. It may not
    inherit a rule the thing it proxies is exempt from. Re-measured after the repair: the same board
    with BOTH hexes Commonwealth-controlled keeps its 13 fed dumps and its line uncut.

    The live gates are the rulebook's, and nothing else:
      * the hex is not on this map; or
      * the source is CAPTURABLE and the enemy has CAPTURED it (56.15). Capturable is the book's
        fact about the source, not a dial -- see SupplySource. Capture is true two ways and both are
        capture: the enemy CONTROLS the hex, or an enemy COMBAT unit is standing on the quay. The two
        agree on a real board -- game.engine._record_control flips control to the side whose combat
        units hold a hex and runs in the Record Phase immediately before the victory check -- but they
        are not one test and neither implies the other. Control OUTLIVES the capturing column, which
        is what a control marker is for: Tobruk does not revert to the Axis because the garrison that
        took it marched on. And occupation PRECEDES the marker on any board the engine has not just
        recorded. Only COMBAT units take ground -- _record_control's own rule ("only combat units
        hold ground", engine.py), applied here so the two halves of this test agree: a lorry or a
        bare HQ parked on the quay captures nothing and shuts nothing.
    The flood OUT of an open source is still blocked normally -- 10.29 bars a Truck Convoy from
    ENTERING an unnegated enemy ZOC, and `blocked` is applied to every hex the search enters. A
    besieged-but-unfallen Tobruk therefore still feeds whatever road is still open out of it, which
    is exactly the siege the campaign is about.

    FLAGGED READING: no test is made of the harbour's 55.3 Efficiency Level. A quay bombed to
    Efficiency 0 lands nothing THIS Operations Stage, but 55.18 regenerates it, and 64.71 refuses to
    enumerate the means ("in any way") -- gating the source on a number the rule does not name would
    be inventing a condition, so the rule's silence is kept."""
    enemy_side = Side.ALLIED if side == Side.AXIS else Side.AXIS
    enemy = CONTROL_OF[enemy_side]
    held = frozenset(u.hex for u in state.living(enemy_side) if u.is_combat)
    open_sources = [
        src.hex for src in sources
        if state.terrain.exists(src.hex)                    # no hex on this map: absent from the trace
        and not (src.capturable                             # 56.15: a CAPTURED harbour feeds nothing
                 and (state.control_of(src.hex) == enemy or src.hex in held))
    ]
    # "In any way" caps nothing, so this leg is pure CONNECTIVITY, not distance: one multi-source flood
    # over the truck-passable edges from every still-open source returns the identical set that unioning
    # a math.inf Dijkstra per source did (movement.connected), for a fraction of the work.
    return movement.connected(state.terrain, open_sources, SUPPLY_MOBILITY,
                              blocked=trace_blocked(state, side))


def tracing_hexes(state: GameState, side: Side, hexes,
                  fed: frozenset, budget: float) -> frozenset:
    """Of `hexes` -- each a combat unit's position -- the ones that can trace a 64.71/64.72 line of
    supply of <= `budget` TRUCK Movement Points back to one of the already-computed fed dumps `fed`.

    THE INVERSION. truck_trace_reach floods forward FROM one unit and asks whether any fed dump lies
    within budget; asked of every Axis combat unit that is 96 near-identical 60-MP Dijkstras, and most
    expensive on exactly the collapsed endgame boards 64.72 exists to judge. The question is symmetric:
    a unit at h traces iff h lies within budget of a fed dump. So ONE multi-source Dijkstra seeded from
    the dumps over REVERSED edges (movement.reverse_reachable) settles every hex at its least-CP line
    to the nearest dump at once, and a unit traces iff its hex settled -- 96 searches collapse to 1.

    THE START-HEX EXEMPTION, restored per query hex and load-bearing on the real board. The forward
    truck_trace_reach floods FROM the unit and never blocks its START hex, so a unit traces OUT of its
    own hex even when that hex is in the trace blocking. On the GT1 setup that is not hypothetical:
    wherever an Axis battalion is stacked with the enemy it is fighting the hex is enemy-OCCUPIED, and
    10.29 enemy occupation (unlike an enemy ZOC, 10.26) is NOT negated by the friendly unit -- so the
    hex is blocked though the battalion plainly traces from it (measured: the Maletti group on (24,76)
    traces <=60, and a naive reverse flood, which never ENTERS a blocked hex, would wrongly drop it and
    move the 64.72 verdict). The reverse flood is therefore corrected by hand for a blocked query hex:
    the unit traces if its own hex is a fed dump, or if some non-blocked neighbour n is within budget
    after paying the forward step into it (reach[n] + step_cost(h -> n) <= budget)."""
    if not fed:
        return frozenset()
    blocked = trace_blocked(state, side)
    reach = movement.reverse_reachable(state.terrain, fed, budget, SUPPLY_MOBILITY, blocked=blocked)
    tmap = state.terrain
    out = set()
    for h in hexes:
        if h in reach or (h in blocked and _blocked_start_traces(tmap, h, fed, reach, budget)):
            out.add(h)
    return frozenset(out)


def _blocked_start_traces(tmap: movement.TerrainMap, h: Coord, fed: frozenset,
                          reach: dict, budget: float) -> bool:
    """The 64.71 start-hex exemption for a unit whose OWN hex `h` is in the trace blocking (it is
    stacked with the enemy): it still traces OUT of `h`. True if `h` is itself a fed dump (the forward
    search reaches its own 0-MP start), or if some non-blocked neighbour n -- one already settled by
    the reverse flood, so n is not blocked -- is within `budget` of a fed dump after the forward step
    into it: reach[n] + step_cost(h -> n) <= budget. Weather is left at the trace's default (Normal),
    as truck_trace_reach leaves it, so the step cost here matches the flood's."""
    if h in fed:
        return True
    for n in neighbors(h):
        r = reach.get(n)
        if r is not None:
            c = movement.step_cost(tmap, h, n, SUPPLY_MOBILITY)
            if c is not None and r + c <= budget:
                return True
    return False


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
                other = e[0] if e[1] == here else e[1]
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


def colocated_dumps(state: GameState, unit: Unit):
    """Friendly ACTIVE supply dumps on the unit's OWN hex -- the co-located 54.11/54.15 in-hex draw
    sources (a well is one of these; a 2nd/3rd-line Truck Convoy is NOT, 49.16, until it unloads).
    Sorted by id for determinism. THE single source enumeration shared by in_hex_draw,
    in_hex_available and the 48 V.C.6 Supply Distribution top-up (engine._supply_distribution), so an
    affordability check the movement AI runs can never drift from what the engine's draw actually
    funds -- and so the 36.17 exclusion below cannot be honoured in one of the three and forgotten in
    another, which is exactly how the airfield's fuel ended up in the Panzerarmee's tanks once.

    [36.17] EXCEPT THE AIRFIELD'S OWN PILE. "An airfield is a supply dump for supplies to be used by
    the SGSU's on that airfield... LAND UNITS MAY NOT USE AIRFIELD SUPPLY DUMPS unless it is an
    emergency. Any SGSU at an airfield may make use of the supplies there." So an air_dump is a
    source for an SGSU standing on it and for nobody else -- which is what keeps the 60.34/60.44 air
    allotment (1200 Ammo / 850 Fuel for the Axis alone) out of the land army's fuel tanks. The rule's
    "emergency" escape is explicitly the Player's judgement ("exactly what constitutes an emergency
    is left to the Player") and is deliberately unmodelled: there is no non-arbitrary trigger.

    ⚠⚠ OWNER RULING NEEDED -- THE REVERSE DIRECTION IS OURS, NOT THE BOOK'S, and since [60.5] it is
    the campaign's dominant air-supply flow. `air_ok` opens EVERY friendly dump under an SGSU's feet
    to it, including the ARMY's ordinary field depots, purely because no rule forbids it: 36.17
    designates the airfield as the squadron's dump and restricts only land units out of the air
    pile, and 35.14 names no source at all. That was a corner case while the campaign's air map was
    the VASSAL extraction. [60.5] puts landing strips on Sollum C4021 and Sidi Barrani C4131 and an
    airfield on Mersa Matruh D3714 -- the exact hexes of the [60.44] Commonwealth Field Supply
    Depots -- so three Commonwealth squadron bases get no air dump of their own (oob.air_dumps
    honours [59.52] by not stacking two dumps on one hex) and eat the army's instead: measured over
    30 Game-Turns of campaign(seed=4), 273 Fuel and 121 Stores. The book's own answer to that
    co-location is to COMBINE the two piles into one dump ([59.52], "the totals are combined and it
    becomes one dump (see Case 36.17)"), and what it does not say is which pile's RESTRICTION the
    combined dump then carries -- 36.17's, which would take the Commonwealth's field depots away
    from the Commonwealth army, or none, which would put the air allotment in its tanks. Until that
    is ruled, this reading stands and is flagged in both places (see oob.air_dumps)."""
    air_ok = air.is_sgsu(unit)
    return sorted((su for su in state.active_supplies(unit.side)
                   if su.hex == unit.hex and (air_ok or not su.air_dump)),
                  key=lambda su: su.id)


def in_hex_available(state: GameState, unit: Unit, commodity: str) -> int:
    """Total of `commodity` a unit can draw IN ITS HEX (49.15/49.16): its own pool plus every
    co-located friendly dump. in_hex_draw is MONOTONE in `need` (it succeeds iff need <= this), so
    this integer is the affordability oracle a competent policy uses to propose only fundable moves --
    fuel_cost(u, reach[c]) <= in_hex_available(state, u, FUEL) iff in_hex_draw would return a plan."""
    return (_pool(unit, commodity)
            + sum(_pool(su, commodity) for su in colocated_dumps(state, unit)))


def affordable_reach(state: GameState, unit: Unit, reach: dict) -> dict:
    """The subset of a movement `reach` (hex -> CP path cost) whose FUEL a unit can actually draw IN
    ITS HEX (49.15/49.16) -- so a competent policy proposes only moves the engine's _draw_move_fuel will
    fund, never a rule-6.1 over-CPA dash it cannot fuel. tactics.reachable_for budgets by the 8.16
    over-CPA allowance (1.5x/2x CPA); the 49.14 tank funds exactly 1x CPA, so the far end of `reach` is
    unfundable unless a co-located dump covers the excess -- which is exactly what in_hex_available
    measures. Affordability is monotone in CP (fuel_cost is non-decreasing), so this is one comparison
    per hex against a single precomputed budget. The unit's own hex (cost 0) is always affordable."""
    avail = in_hex_available(state, unit, FUEL)
    return {c: cost for c, cost in reach.items() if fuel_cost(unit, cost) <= avail}


def in_hex_draw(state: GameState, unit: Unit, commodity: str, need: int):
    """The FULL-GAME in-hex supply draw (49.15/50.15/51.15): satisfy `need` of `commodity` from
    sources ON unit.hex ONLY, in the 49.16 priority order --

        1. the unit's OWN pool  (FUEL: the 49.14 tank; AMMO/STORES/WATER: first-line-borne),
        2. any co-located friendly supply dump on unit.hex (54.11/54.15 -- incl. a captured dump
           and a well, both of which already sit as Supply Units on their hex),

    -- and NOT a 2nd/3rd-line Truck Convoy sitting on the hex (49.16: "such fuel from convoying
    trucks must be off-loaded first" -- a truck is not a source until it unloads into a dump).

    Returns the draw list as TAGGED tuples ("unit"|"dump", ref_id, qty) so the caller emits
    UNIT_SUPPLY_CONSUMED (own pool) / SUPPLY_CONSUMED (dump) respectively, or None if the hex
    cannot cover `need`. This is the replacement for reachable_supplies/plan_draw: there is NO
    supply RANGE in the full game (32.16's ½-CPA trace is the ABSTRACT game) -- supply is either in
    the hex or it is not, so this is a pure dictionary filter, no trace, no flood, no _reach memo."""
    if need <= 0:
        return []
    draws: list[tuple[str, str, int]] = []
    remaining = need
    own = _pool(unit, commodity)                       # 1. the unit's own in-hex pool, first (49.16)
    if own > 0:
        take = min(remaining, own)
        draws.append(("unit", unit.id, take))
        remaining -= take
    if remaining > 0:                                  # 2. co-located dumps (the shared enumeration);
        for su in colocated_dumps(state, unit):        # same hex so distance is moot
            if remaining <= 0:
                break
            take = min(remaining, _pool(su, commodity))
            if take > 0:
                draws.append(("dump", su.id, take))
                remaining -= take
    return draws if remaining <= 0 else None
