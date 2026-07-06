"""Pure fold: apply(state, event) -> state (brief §4.1).

No RNG, no I/O — outcomes are already facts in the event. fold(initial, events)
reconstructs state from scratch (the replay/visualisation path, §4.7).
"""
from __future__ import annotations

from dataclasses import replace

from .events import Control, Event, EventKind, Phase, Side
from .state import GameState, StepRecord, VP


def apply(state: GameState, event: Event) -> GameState:
    k = event.kind
    p = event.payload

    if k in (EventKind.GAME_INITIALIZED, EventKind.ORDER_REJECTED,
             EventKind.COMBAT_RESOLVED, EventKind.BARRAGE_RESOLVED,
             EventKind.ANTI_ARMOR_RESOLVED, EventKind.REINFORCEMENT_ARRIVED,
             EventKind.CONVOY_CANCELLED, EventKind.PASTA_DENIED, EventKind.PORT_UNLOADED,
             EventKind.STAFF_INTENT, EventKind.STAFF_PROPOSAL, EventKind.STAFF_CONSTRAINT,
             EventKind.STAFF_ADJUDICATION, EventKind.STAFF_DISSENT):
        return state  # markers / audit records — PORT_UNLOADED's top-up rides SUPPLY_ARRIVED

    if k == EventKind.PORT_EFFICIENCY_CHANGED:
        # 55.14/55.18: set a port's Efficiency Level (regen, or later bomb/mine damage).
        port = state.port(p["port_id"])
        return state.with_port(replace(port, eff=p["level"]))

    if k == EventKind.SUPPLY_EVAPORATED:
        # 49.3 / 52.44: fuel/water lost to evaporation & spillage. Folds exactly like a
        # consume -- drain the dump, credit consumed[] -- so on_hand+consumed==initial holds.
        su = state.supply(p["supply_id"])
        commodity = p["commodity"]
        attr = commodity.lower()
        drained = replace(su, **{attr: getattr(su, attr) - p["qty"]})
        consumed = dict(state.consumed)
        consumed[commodity] = consumed.get(commodity, 0) + p["qty"]
        return replace(state.with_supply(drained), consumed=consumed)

    if k == EventKind.SUPPLY_ARRIVED:
        # Faucet, the dual of SUPPLY_CONSUMED (cargo is ALREADY post-cap -- the engine
        # baked the landed amounts, per the event-sourcing rule that outcomes are facts).
        # Top up the dump AND raise initial_supply by the same qty, so the conservation
        # identity on_hand+consumed==initial holds untouched.
        su = state.supply(p["supply_id"])
        init = dict(state.initial_supply)
        for commodity, qty in p["cargo"].items():
            attr = commodity.lower()
            su = replace(su, **{attr: getattr(su, attr) + qty})
            init[commodity] = init.get(commodity, 0) + qty
        return replace(state.with_supply(su), initial_supply=init)

    if k == EventKind.WEATHER_ROLLED:
        return replace(state, weather=p["weather"], move_modifier=p["move_modifier"])

    if k == EventKind.UNIT_MOVED:
        u = state.unit(p["unit_id"])                   # 21.25: BP accrue into the move faucet
        return state.with_unit(replace(u, hex=tuple(p["to"]),
                                       cp_used=u.cp_used + p["cp_spent"],
                                       bp_accumulated=u.bp_accumulated + p.get("bp", 0.0)))

    if k == EventKind.UNIT_RETREATED:
        u = state.unit(p["unit_id"])                   # 21.22: retreat also accrues BP
        return state.with_unit(replace(u, hex=tuple(p["to"]),
                                       bp_accumulated=u.bp_accumulated + p.get("bp", 0.0)))

    if k == EventKind.SUPPLY_MOVED:
        su = state.supply(p["supply_id"])
        return state.with_supply(replace(su, hex=tuple(p["to"])))

    if k == EventKind.SUPPLY_CONSUMED:
        su = state.supply(p["supply_id"])
        commodity = p["commodity"]
        attr = commodity.lower()                       # "AMMO"->ammo, "FUEL"->fuel
        drained = replace(su, **{attr: getattr(su, attr) - p["qty"]})
        consumed = dict(state.consumed)
        consumed[commodity] = consumed.get(commodity, 0) + p["qty"]
        return replace(state.with_supply(drained), consumed=consumed)

    if k == EventKind.TRUCK_LOADED:
        # 53.24: conserving transfer dump -> truck (both on the same hex). The grand total
        # is unchanged and initial/consumed untouched (invariants.check sums truck cargo).
        su = state.supply(p["supply_id"])
        tf = state.truck(p["truck_id"])
        for commodity, qty in p["cargo"].items():
            attr = commodity.lower()
            su = replace(su, **{attr: getattr(su, attr) - qty})
            tf = replace(tf, **{attr: getattr(tf, attr) + qty})
        return state.with_supply(su).with_truck(tf)

    if k == EventKind.TRUCK_UNLOADED:
        # 53.24: conserving transfer truck -> dump (the exact dual of TRUCK_LOADED).
        su = state.supply(p["supply_id"])
        tf = state.truck(p["truck_id"])
        for commodity, qty in p["cargo"].items():
            attr = commodity.lower()
            tf = replace(tf, **{attr: getattr(tf, attr) - qty})
            su = replace(su, **{attr: getattr(su, attr) + qty})
        return state.with_supply(su).with_truck(tf)

    if k == EventKind.TRUCK_MOVED:
        # 53.21 / 49.18: relocate the formation, burning `fuel` of its OWN cargo fuel to
        # move -- folds like a consume (truck fuel down, consumed[FUEL] up) so conservation
        # holds with truck cargo summed into on_hand.
        tf = state.truck(p["truck_id"])
        fuel = p["fuel"]
        st = state.with_truck(replace(tf, hex=tuple(p["to"]), fuel=tf.fuel - fuel))
        if fuel:
            consumed = dict(st.consumed)
            consumed["FUEL"] = consumed.get("FUEL", 0) + fuel
            st = replace(st, consumed=consumed)
        return st

    if k == EventKind.RAIL_HAULED:
        # 54.3: conserving transfer between two rail-connected dumps. Grand total unchanged,
        # so on_hand+consumed==initial holds untouched.
        src = state.supply(p["from_dump"])
        dst = state.supply(p["to_dump"])
        attr = p["commodity"].lower()
        qty = p["qty"]
        src = replace(src, **{attr: getattr(src, attr) - qty})
        dst = replace(dst, **{attr: getattr(dst, attr) + qty})
        return state.with_supply(src).with_supply(dst)

    if k == EventKind.BREAKDOWN_CHECKED:
        # 21.26: record the column just checked so the unit re-checks only when it later
        # stops in a HIGHER column (even a 0% check moves the gate). Folds nothing else.
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, bp_checked_column=p["column"]))

    if k == EventKind.VEHICLE_BROKE_DOWN:
        # 21.44: move TOE from operational to broken-down. Total strength is unchanged
        # (not a loss), so supply conservation and the step counts are untouched.
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, broken_down=u.broken_down + p["amount"]))

    if k == EventKind.VEHICLE_REPAIRED:
        # 22.5: return repaired TOE to the operational pool (the dual of the breakdown).
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, broken_down=u.broken_down - p["amount"]))

    if k == EventKind.STEP_LOST:
        u = state.unit(p["unit_id"])
        u2 = replace(u, steps=_apply_step_loss(u.steps, p["amount"]))
        if u2.broken_down > u2.strength:               # a shrinking unit loses broken hulks too
            u2 = replace(u2, broken_down=u2.strength)
        return state.with_unit(u2)

    if k == EventKind.COHESION_CHANGED:
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, cohesion=u.cohesion + p["delta"]))

    if k == EventKind.STORES_SHORTFALL:
        u = state.unit(p["unit_id"])                   # 51.21/51.22: +1 turn short, +1 disorg
        return state.with_unit(replace(u, turns_without_stores=u.turns_without_stores + 1,
                                       disorganization=u.disorganization + 1))

    if k == EventKind.WATER_SHORTFALL:
        u = state.unit(p["unit_id"])                   # 52.53: +1 op-stage short of water
        return state.with_unit(replace(u, stages_without_water=u.stages_without_water + 1))

    if k == EventKind.STORES_RESTORED:                 # resupplied: consecutive count resets
        u = state.unit(p["unit_id"])                   # (Disorganization persists; recovery is 19/20)
        return state.with_unit(replace(u, turns_without_stores=0))

    if k == EventKind.WATER_RESTORED:
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, stages_without_water=0))

    if k == EventKind.FORT_REDUCED:
        return state.with_fort_level(tuple(p["hex"]), p["level"])

    if k == EventKind.HEX_CONTROL_CHANGED:
        return state.with_control(tuple(p["coord"]), Control(p["control"]))

    if k == EventKind.VICTORY_CHECKED:
        return replace(state, vp=VP(axis=p["axis"], allied=p["allied"]))

    if k == EventKind.PHASE_ADVANCED:
        return replace(state, phase=Phase(p["phase"]), active_side=Side(p["active_side"]))

    if k == EventKind.TURN_ADVANCED:
        # New OpStage: every unit's CPA refreshes (rule 6.16 — CP do not carry over) and
        # the Breakdown-Point accumulator + 21.26 re-check gate reset (21.25: BP are
        # cumulative WITHIN an Operations Stage only). broken_down persists (21.44).
        units = tuple(replace(u, cp_used=0.0, bp_accumulated=0.0, bp_checked_column=-1)
                      for u in state.units)
        return replace(state, turn=p["turn"], units=units)

    raise ValueError(f"unhandled event kind {k}")


def _apply_step_loss(steps: tuple[StepRecord, ...], amount: int) -> tuple[StepRecord, ...]:
    """Peel `amount` strength off the back of the step list (last sub-unit absorbs
    losses first) — a deterministic, replayable loss rule."""
    out = list(steps)
    i = len(out) - 1
    while amount > 0 and i >= 0:
        take = min(amount, out[i].strength)
        out[i] = replace(out[i], strength=out[i].strength - take)
        amount -= take
        i -= 1
    return tuple(out)


def fold(initial: GameState, events: list[Event]) -> GameState:
    state = initial
    for e in events:
        state = apply(state, e)
    return state
