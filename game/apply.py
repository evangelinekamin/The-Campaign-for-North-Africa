"""Pure fold: apply(state, event) -> state (brief §4.1).

No RNG, no I/O — outcomes are already facts in the event. fold(initial, events)
reconstructs state from scratch (the replay/visualisation path, §4.7).
"""
from __future__ import annotations

from dataclasses import replace

from . import supply
from .events import Control, Event, EventKind, Phase, Side
from .movement import edge
from .state import GameState, Rommel, StepRecord, SupplyUnit, VP


def apply(state: GameState, event: Event) -> GameState:
    k = event.kind
    p = event.payload

    if k in (EventKind.GAME_INITIALIZED, EventKind.ORDER_REJECTED,
             EventKind.BARRAGE_RESOLVED,
             EventKind.ANTI_ARMOR_RESOLVED, EventKind.REINFORCEMENT_ARRIVED,
             EventKind.CONVOY_CANCELLED, EventKind.CONVOY_INTERDICTED,
             EventKind.PASTA_DENIED, EventKind.PORT_UNLOADED,
             EventKind.SEGMENT_ADVANCED, EventKind.AIR_STRIKE_RESOLVED,
             EventKind.STAFF_INTENT, EventKind.STAFF_PROPOSAL, EventKind.STAFF_CONSTRAINT,
             EventKind.STAFF_ADJUDICATION, EventKind.STAFF_DISSENT):
        # markers / audit records. SEGMENT_ADVANCED (8.2) opens a Continual-Movement pulse but
        # the CP/BP accumulators PERSIST across it (only STAGE/TURN_ADVANCED reset them), so it
        # folds to identity -- PORT_UNLOADED's top-up likewise rides SUPPLY_ARRIVED.
        return state

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

    if k == EventKind.TRUCK_EVAPORATED:
        # 29.34 / 49.3: Fuel/Water carried by a truck convoy evaporates exactly as in a dump.
        # Folds like SUPPLY_EVAPORATED but off the truck -- drain the cargo, credit consumed[] --
        # so on_hand+consumed==initial holds (invariants.check sums truck cargo alongside dumps).
        tf = state.truck(p["truck_id"])
        commodity = p["commodity"]
        attr = commodity.lower()
        drained = replace(tf, **{attr: getattr(tf, attr) - p["qty"]})
        consumed = dict(state.consumed)
        consumed[commodity] = consumed.get(commodity, 0) + p["qty"]
        return replace(state.with_truck(drained), consumed=consumed)

    if k == EventKind.WELL_REFILLED:
        # 29.53 / 52.15: a rainstorm refills a depleted well. A FAUCET (rain introduces water),
        # the dual of SUPPLY_ARRIVED -- top the finite well up AND raise initial_supply by the same
        # qty, so on_hand+consumed==initial holds.
        su = state.supply(p["supply_id"])
        commodity = p["commodity"]
        attr = commodity.lower()
        filled = replace(su, **{attr: getattr(su, attr) + p["qty"]})
        init = dict(state.initial_supply)
        init[commodity] = init.get(commodity, 0) + p["qty"]
        return replace(state.with_supply(filled), initial_supply=init)

    if k == EventKind.SUPPLY_DUMP_BLOWN:
        # 54.14 / 54.17: the owner burns his own dump rather than hand it to the enemy one hex away.
        # The engine baked the destroyed amounts (the 54.17 roll is a fact, not a re-derivation), so
        # this folds exactly like evaporation -- drain each commodity, credit consumed[] -- and
        # on_hand+consumed==initial holds. Every commodity in the dump goes at the same percentage.
        su = state.supply(p["supply_id"])
        consumed = dict(state.consumed)
        for commodity, qty in p["destroyed"].items():
            attr = commodity.lower()
            su = replace(su, **{attr: getattr(su, attr) - qty})
            consumed[commodity] = consumed.get(commodity, 0) + qty
        return replace(state.with_supply(su), consumed=consumed)

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
        # 29.1 / 29.7: the theatre-wide TYPE plus the 2-3 sections a foul result covers (empty
        # for Normal/Hot, both theatre-wide). weather_at reads both to localise the weather per hex.
        return replace(state, weather=p["weather"],
                       storm_sections=frozenset(p.get("sections", ())))

    if k == EventKind.UNIT_MOVED:
        u = state.unit(p["unit_id"])                   # 21.25: BP accrue into the move faucet
        return state.with_unit(replace(u, hex=tuple(p["to"]),
                                       cp_used=u.cp_used + p["cp_spent"],
                                       bp_accumulated=u.bp_accumulated + p.get("bp", 0.0)))

    if k == EventKind.REACTION_MOVED:
        # 8.51/8.52: Reaction Movement follows all the standard rules of movement and expends CP,
        # so it folds IDENTICALLY to UNIT_MOVED -- relocate the reactor and feed its cp_spent + bp
        # into the same 6.14 per-OpStage accumulators. A distinct kind only for camera legibility.
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, hex=tuple(p["to"]),
                                       cp_used=u.cp_used + p["cp_spent"],
                                       bp_accumulated=u.bp_accumulated + p.get("bp", 0.0)))

    if k == EventKind.RESERVE_DESIGNATED:
        # 18.12: designation always places the unit in Reserve I. No CP (18.26).
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, reserve=1))

    if k == EventKind.RESERVE_FLIPPED:
        # 18.13: an unreleased Reserve I advances to Reserve II at the first Release Segment.
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, reserve=2))

    if k == EventKind.RESERVE_RELEASED:
        # 18.13/18.26: release clears the reserve tier (no CP) and records which tier the unit
        # was released FROM, so the 18.24 half-CPA cap (reserve_released==2) can bind downstream.
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, reserve=0, reserve_released=p["from_tier"]))

    if k == EventKind.UNIT_RETREATED:
        u = state.unit(p["unit_id"])                   # 21.22: retreat also accrues BP
        return state.with_unit(replace(u, hex=tuple(p["to"]),
                                       bp_accumulated=u.bp_accumulated + p.get("bp", 0.0)))

    if k == EventKind.SUPPLY_MOVED:
        # [54.12] A relocated dump stores no more at its DESTINATION than that hex's row allows: a
        # base-filled depot hauled off an unlimited city onto Other Terrain sheds its overflow. The
        # excess it cannot store forward STAYS AT THE ORIGIN as a dump ([54.11]: "Any hex can be used
        # as a supply dump") -- it is never destroyed, because supply is destroyed only by the rules
        # that say so (demolition [54.14], the capture tax [49.19]/[50.16]/[51.16]). So the clamp
        # SPLITS the load, exactly as the FILL path clamps a delivery to the 54.12 headroom and leaves
        # the overflow at its source (engine._naval_convoys / _truck_unload -- "overflow is never
        # credited"). The forward dump keeps its id; the remainder is a fresh pile at the origin, under
        # a per-move-unique id (the split marker is flat, so a remainder that is itself hauled on and
        # sheds again does not nest). Conserves on-hand exactly, so the ledger identity is untouched.
        su = state.supply(p["supply_id"])
        cap = supply.dump_capacity_at(state, tuple(p["to"]))
        fwd = {c: min(getattr(su, c.lower()), cap[c]) for c in supply.COMMODITIES}
        left = {c: getattr(su, c.lower()) - fwd[c] for c in supply.COMMODITIES}
        moved = state.with_supply(replace(su, hex=tuple(p["to"]), ammo=fwd["AMMO"],
                                          fuel=fwd["FUEL"], stores=fwd["STORES"], water=fwd["WATER"]))
        if not any(left.values()):
            return moved
        rem = SupplyUnit(f"{su.id.split('~')[0]}~{event.seq}", su.side, su.hex,
                         ammo=left["AMMO"], fuel=left["FUEL"],
                         stores=left["STORES"], water=left["WATER"])
        return replace(moved, supplies=moved.supplies + (rem,))

    if k == EventKind.SUPPLY_DUMP_ESTABLISHED:
        # 54.11: "Any hex can be used as a supply dump." A pure APPEND of an EMPTY dump -- it
        # mints nothing, so conservation (on_hand + consumed == initial) holds trivially; the
        # supplies arrive by the TRUCK_UNLOADED that follows it.
        su = SupplyUnit(p["supply_id"], Side(p["side"]), tuple(p["hex"]),
                        ammo=0, fuel=0, stores=0, water=0)
        return replace(state, supplies=state.supplies + (su,))

    if k == EventKind.SUPPLY_CAPTURED:
        # 32.13 / 54.15: an enemy combat unit entered the dump's hex, so the dump changes hands.
        # But capture is TAXED (49.19 / 50.16 / 51.16): only 1/3 (round up) of the Ammunition and
        # 50% of the Stores are usable by the captor -- the rest are LOST -- while Fuel passes intact
        # and Water is untaxed. Flip the owner AND drain the baked `lost`, crediting consumed[] so
        # on_hand + consumed == initial holds (the loss folds exactly like a consume/demolition).
        su = replace(state.supply(p["supply_id"]), side=Side(p["to"]))
        consumed = dict(state.consumed)
        for commodity, qty in p.get("lost", {}).items():
            attr = commodity.lower()
            su = replace(su, **{attr: getattr(su, attr) - qty})
            consumed[commodity] = consumed.get(commodity, 0) + qty
        return replace(state.with_supply(su), consumed=consumed)

    if k == EventKind.MOTORIZATION_ATTACHED:
        # 32.32: thirty Medium Truck Points (32.51) book onto the dump and out of the freight pool.
        # The lorries are RESERVED, never minted or spent, so conservation is untouched -- the whole
        # cost of this rule is the freight those Truck Points are now not hauling (supply.free_points).
        legs = tuple((tid, pts) for tid, pts in p["legs"])
        return replace(state, motorization={**state.motorization, p["supply_id"]: legs})

    if k == EventKind.MOTORIZATION_DETACHED:
        # 32.32's other hinge: the column stands down and the lorries go back on the freight run.
        book = {k2: v for k2, v in state.motorization.items() if k2 != p["supply_id"]}
        return replace(state, motorization=book)

    if k == EventKind.SUPPLY_DUMP_CONSTRUCTED:
        # 24.9: the heap of supplies in this hex is now a CONSTRUCTED supply dump, which by the
        # rule's own Note is the one thing that lets a truck "in convoy" LOAD from it -- a link in
        # the chain rather than a one-way sink. A pure flag: the 3 CP ride CP_EXPENDED and the 20
        # Store Points SUPPLY_CONSUMED, so conservation is untouched here.
        su = state.supply(p["supply_id"])
        return state.with_supply(replace(su, constructed=True))

    if k == EventKind.CONSTRUCTION_ADVANCED:
        # 24.11/24.62: one Construction Segment of work banked on the site, counted in COMPANY-
        # STAGES. Pure bookkeeping onto the Under Construction marker; the Store Points it costs
        # ride the SUPPLY_CONSUMED emitted beside it.
        return state.with_construction(tuple(p["hex"]), p["progress"])

    if k == EventKind.CONSTRUCTION_COMPLETED:
        # 24.11a/24.67: the track is laid. The new hex joins the map's rail edge-set, extending the
        # line from the head it grew out of ("construction must start from the last completed hex...
        # no hex may be skipped"), and the Under Construction marker comes off. The ONE dynamic
        # thing on an otherwise static TerrainMap -- because a built railroad hex is exactly that:
        # "unbuilt railroad hexes simply do not exist" until they are built (24.67).
        hx, frm = tuple(p["hex"]), tuple(p["from"])
        tmap = replace(state.terrain, rails=state.terrain.rails | {edge(frm, hx)})
        return replace(state, terrain=tmap).with_construction(hx, 0)

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

    if k == EventKind.UNIT_SUPPLY_CONSUMED:
        # 49.16/50.14/51.11/52.4: a unit burns its OWN in-hex pool (the 49.14 fuel tank on a move,
        # or first-line-borne ammo/stores/water). The exact dual of SUPPLY_CONSUMED off a unit
        # rather than a dump: pool down, consumed[] up, so on_hand+consumed==initial holds once
        # unit pools are summed into on_hand (Phase-4 seeding slice).
        u = state.unit(p["unit_id"])
        commodity = p["commodity"]
        attr = commodity.lower()
        drained = replace(u, **{attr: getattr(u, attr) - p["qty"]})
        consumed = dict(state.consumed)
        consumed[commodity] = consumed.get(commodity, 0) + p["qty"]
        return replace(state.with_unit(drained), consumed=consumed)

    if k == EventKind.UNIT_REFILLED:
        # 48 V.C.6: the 0-CP Supply Distribution top-up -- a conserving transfer dump -> unit pool
        # (both on the same hex), the exact dual of TRUCK_LOADED (dump -> truck). Grand total
        # unchanged, initial/consumed untouched.
        su = state.supply(p["supply_id"])
        u = state.unit(p["unit_id"])
        commodity = p["commodity"]
        attr = commodity.lower()
        su = replace(su, **{attr: getattr(su, attr) - p["qty"]})
        u = replace(u, **{attr: getattr(u, attr) + p["qty"]})
        return state.with_supply(su).with_unit(u)

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

    if k == EventKind.COMBAT_RESOLVED:
        # 8.63/15.81: Engaged is a COMBAT RESULT -- it locks the participants only when the
        # 15.79 CRT produced an ENG, which combat.resolve reports as payload["attacker_engaged"]
        # (retreat has already voided it, 15.74). On an ENG, EVERY unit involved in that assault
        # (both sides, 15.81) carries the Engaged marker for the rest of the Operations Stage --
        # leaving contact then costs 4 CP (Disengage) instead of 2 (Break Contact). Without it,
        # the still-adjacent assault veterans are merely in Contact (2 CP), NOT Engaged (the 15.81
        # parenthetical), so no marker is set. A pure marker fold (no supply surface); cleared by
        # _reset_opstage at the stage boundary. Dead participants are skipped (harmless).
        if not p.get("attacker_engaged"):
            return state
        st = state
        for uid in list(p.get("attackers", [])) + list(p.get("defenders", [])):
            u = st.unit(uid)
            if u is not None and u.alive and not u.engaged:
                st = st.with_unit(replace(u, engaged=True))
        return st

    if k == EventKind.CP_EXPENDED:
        # 6.3: charge a unit its combat Capability Points. Folds into cp_used -- the same
        # per-OpStage accumulator movement feeds (6.14) and _reset_opstage clears (6.16).
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, cp_used=u.cp_used + p["cp"]))

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

    if k == EventKind.AIR_SUPERIORITY_RESOLVED:
        # 40/45/46: bake the OpStage's air-superiority victor for an arena (a Side value or None
        # for a contested sky). A pure scalar fold onto air_superiority -- no supply surface, no
        # unit -- cleared at the OpStage boundary by _reset_opstage's callers below.
        return state.with_air_superiority(p["arena"], p["victor"])

    if k == EventKind.AIR_RECON_RESOLVED:
        # 42.2: a recon flight lifts the fog over a hex for the flying side this OpStage. Fold the
        # (recon-side, hex) pair into air_sighted (observation reads it alongside _sighted_hexes);
        # the typed detail rides in the payload for the camera. Cleared at the OpStage boundary.
        return state.with_air_sighted(event.side.value, tuple(p["hex"]))

    if k == EventKind.NAVAL_BOMBARDMENT:
        # 30.2 off-shore bombardment: the Pin/step-loss ride the transient combat pinned set +
        # STEP_LOST(role='naval') exactly like a land barrage, so the ONLY GameState fold here is
        # the 30.25 refit -- the ship that fired now owes two Operations Stages in Alexandria.
        ship = state.naval_of(p["ship_id"])
        return state.with_naval(replace(ship, port_cooldown=2))

    if k == EventKind.FORT_REDUCED:
        return state.with_fort_level(tuple(p["hex"]), p["level"])

    if k == EventKind.HEX_CONTROL_CHANGED:
        return state.with_control(tuple(p["coord"]), Control(p["control"]))

    if k == EventKind.VICTORY_CHECKED:
        return replace(state, vp=VP(axis=p["axis"], allied=p["allied"]))

    if k == EventKind.PHASE_ADVANCED:
        return replace(state, phase=Phase(p["phase"]), active_side=Side(p["active_side"]))

    if k == EventKind.INITIATIVE_DETERMINED:
        # 7.14: who holds Initiative this game-turn, fixed for all three Operations Stages
        # (7.12). A pure scalar fold -- no supply surface touched, conservation untouched.
        return replace(state, initiative_side=Side(p["side"]))

    if k == EventKind.INITIATIVE_DECLARED:
        # 7.11: the initiative side's per-stage choice of who moves first, from which the
        # 7.12 double-move emerges. Pure scalar fold.
        return replace(state, phasing_first=Side(p["phasing_first"]))

    if k == EventKind.ROMMEL_ARRIVED:
        # 64.2 / 31: General Rommel reaches Africa -- the entity is lifted onto the board at his
        # arrival hex (rommel None -> the leader on `hex`). A conservation-invisible fold (no
        # steps, no supply), so invariants.check is untouched; the hex rides the event so
        # fold(initial, events) reconstructs him exactly.
        return replace(state, rommel=Rommel(hex=tuple(p["hex"])))

    if k == EventKind.ROMMEL_ANCHORED:
        # 31.4: snapshot the companions Rommel starts this Operations Stage with, anchored to
        # his current hex. The +5 CPA (tactics.effective_cpa) holds only while a unit is in this
        # set AND still stacked on the anchor AND Rommel has not moved off it (hex==anchor_hex).
        return replace(state, rommel=replace(state.rommel, anchor_hex=tuple(p["hex"]),
                                             companions=frozenset(p["companions"])))

    if k == EventKind.ROMMEL_MOVED:
        # 31.1: General Rommel's leader move. Fold his hex only -- and because effective_cpa
        # keys the 31.4 +5 on hex == anchor_hex == rommel.hex, stepping off the anchor voids
        # that stage's companion bonus automatically (no separate anchor clear needed).
        return replace(state, rommel=replace(state.rommel, hex=tuple(p["to"])))

    if k == EventKind.ROMMEL_RECALLED:
        # 31 Berlin recall: True sends him to Germany (the +1/+5 hooks read in_germany and go
        # silent), False is the auto-return next turn. A pure scalar fold onto the entity.
        return replace(state, rommel=replace(state.rommel, in_germany=p["in_germany"]))

    if k == EventKind.STAGE_ADVANCED:
        # New Operations Stage within the game-turn (rule 5.1): bump the stage and refresh
        # the per-OpStage CP/BP counters -- the same reset semantics as TURN_ADVANCED, now
        # firing at every stage boundary (3x/game-turn), spanning both players' portions (6.14).
        return replace(state, stage=p["stage"], units=_reset_opstage(state.units),
                       air_superiority={}, air_sighted=frozenset(),
                       naval=_refit_naval(state.naval))

    if k == EventKind.TURN_ADVANCED:
        # A new game-turn opens a new Operations Stage: share the OpStage reset (6.16 — CP do
        # not carry over; 21.25 — BP + the 21.26 re-check gate are cumulative within a stage
        # only), bump the game-turn, and re-open at stage 1. broken_down persists (21.44). The
        # per-OpStage air-superiority gate clears too (a fresh sky is contested each stage).
        return replace(state, turn=p["turn"], stage=1, units=_reset_opstage(state.units),
                       air_superiority={}, air_sighted=frozenset(),
                       naval=_refit_naval(state.naval))

    if k == EventKind.REINFORCEMENT_DELAYED:
        # Rule 20: a scheduled unit whose entry hex has no stacking room waits -- its
        # arrival_turn is bumped one game-turn so state.on_map keeps it dormant (off-board,
        # uncounted by the 9.31 stacking check) until room opens next game-turn. The event
        # carries the new arrival_turn so fold(initial, events) reconstructs it exactly.
        u = state.unit(p["unit_id"])
        return state.with_unit(replace(u, arrival_turn=p["arrival_turn"]))

    raise ValueError(f"unhandled event kind {k}")


def _refit_naval(naval: tuple) -> tuple:
    """30.25 Alexandria refit countdown, ticked at each Operations-Stage boundary: a ship that
    fired owes two Operations Stages in port, so its port_cooldown steps down toward readiness
    (floored at 0). Ships that never fired (port_cooldown 0) are untouched, so naval=() and an
    idle fleet stay byte-identical."""
    return tuple(replace(n, port_cooldown=max(0, n.port_cooldown - 1)) for n in naval)


def _reset_opstage(units: tuple) -> tuple:
    """The Operations-Stage boundary reset (rules 6.16 / 21.25): every unit's CPA refreshes
    and the Breakdown-Point accumulator + 21.26 re-check gate clear. broken_down (immobile
    TOE) persists across the boundary until repaired (21.44). The 15.81 Engaged marker is
    also removed here (it lasts one Operations Stage). Reserve status + the release tier (rule
    18.14: Reserve ends when the OpStage ends) reset here too. Shared by STAGE_ADVANCED and
    TURN_ADVANCED so the two clock boundaries carry one reset semantic."""
    return tuple(replace(u, cp_used=0.0, bp_accumulated=0.0, bp_checked_column=-1, engaged=False,
                         reserve=0, reserve_released=0)
                 for u in units)


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
