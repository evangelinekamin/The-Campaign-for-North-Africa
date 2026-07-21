"""Event-sourcing core types (brief §4.1).

The engine is an append-only log of Events; GameState is a deterministic fold
over that log (see game.apply). Every Event is a *fact* — outcomes (die rolls,
losses) are baked in at generation time and the die rolls that produced them are
recorded in `rng_draws`, so that `apply` is pure and replay needs no RNG. This
is what makes runs reproducible: same seed -> identical event stream ->
byte-identical state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class Side(str, Enum):
    AXIS = "AXIS"
    ALLIED = "ALLIED"
    SYSTEM = "SYSTEM"


class Control(str, Enum):
    AXIS = "AXIS"
    ALLIED = "ALLIED"
    NEUTRAL = "NEUTRAL"


# Which Control a Side holds ground under. It lives here, beside the two enums it joins, because
# more than the engine needs it: game.supply asks the rule-56.15 question ("is this harbour in
# enemy hands?") of the 64.71 supply trace, and game.supply may not import game.engine.
CONTROL_OF: dict[Side, Control] = {Side.AXIS: Control.AXIS, Side.ALLIED: Control.ALLIED}


class Phase(str, Enum):
    WEATHER = "WEATHER"
    LOGISTICS = "LOGISTICS"        # naval-convoy arrival (rule 48 V.C.7/V.D); SYSTEM-owned
    ORGANIZATION = "ORGANIZATION"  # the Organization Phase proper (rule 32.32): the ONE beat of an
                                   # OpStage in which Motorization Points may be attached to or
                                   # detached from a supply unit. Entered only where the rule is
                                   # live (GameState.motorized_supply), so no other scenario sees it.
    CONSTRUCTION = "CONSTRUCTION"  # Construction Segment of the Organization Phase (48 V.C.4 /
                                   # rule 24.11); the phasing side's own beat, BEFORE it moves --
                                   # "units involved in such work may not be moved (voluntarily)
                                   # during the remainder of the current Operations Stage" (48 V.C.4.b)
    RESERVE = "RESERVE"            # Reserve Designation Phase (rule 48 V.G / 18.12); phasing side
    MOVEMENT = "MOVEMENT"
    COMBAT = "COMBAT"
    REPAIR = "REPAIR"              # vehicle repair (rule 22.12); the active side's own beat
    RECORD = "RECORD"


# System owns WEATHER, LOGISTICS and RECORD; the active side's Front Commander owns
# MOVEMENT and COMBAT. This is the seam the orchestrator uses to decide which
# role/agent to invoke per phase (brief §4.3).
SYSTEM_PHASES = (Phase.WEATHER, Phase.LOGISTICS, Phase.RECORD)


class EventKind(str, Enum):
    GAME_INITIALIZED = "GAME_INITIALIZED"
    WEATHER_ROLLED = "WEATHER_ROLLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    REINFORCEMENT_ARRIVED = "REINFORCEMENT_ARRIVED"
    # Rule 20: a scheduled unit whose entry hex has no stacking room this game-turn WAITS -- its
    # arrival_turn is bumped one game-turn (game.engine._defer_crowded_reinforcements, run before
    # the TURN_ADVANCED fold), so state.on_map keeps it dormant (off-board, uncounted by the 9.31
    # stacking check) until room opens. The load-bearing dual of the marker REINFORCEMENT_ARRIVED:
    # it folds by relocating the arrival in time rather than recording it.
    REINFORCEMENT_DELAYED = "REINFORCEMENT_DELAYED"
    UNIT_MOVED = "UNIT_MOVED"
    UNIT_RETREATED = "UNIT_RETREATED"
    SUPPLY_MOVED = "SUPPLY_MOVED"
    SUPPLY_CONSUMED = "SUPPLY_CONSUMED"
    # Naval-convoy faucet (rules 48/56). SUPPLY_ARRIVED is the LOAD-BEARING dual of
    # SUPPLY_CONSUMED: it tops up a dump with the (post-cap) landed cargo and raises
    # initial_supply by the same qty, so conservation holds untouched. CONVOY_CANCELLED
    # (56.15: a convoy to an enemy-captured port never sails) is a marker / no-op fold.
    SUPPLY_ARRIVED = "SUPPLY_ARRIVED"
    CONVOY_CANCELLED = "CONVOY_CANCELLED"
    # Air interdiction of a convoy in transit (rules 41.6 / 32.63-32.66). CONVOY_INTERDICTED
    # {lane, convoy_id, interdictor, bomb_points, pct_lost, tons_lost} is the legible marker
    # of a bombing attack: the CRT (41.66) tens-of-percent of cargo skimmed at sea. It folds
    # to IDENTITY -- the load-bearing change rides the paired, already-reduced SUPPLY_ARRIVED
    # (the skimmed supply simply never enters the system, so conservation holds untouched).
    CONVOY_INTERDICTED = "CONVOY_INTERDICTED"
    # Full-logistics consumption (rules 49-52). SUPPLY_EVAPORATED (49.3/52.44: 6% of
    # on-map fuel + water per game-turn, +5% hot) folds like a consume -- it drains the
    # dump and adds to consumed[], so it "left the system" and conservation stays exact.
    # PASTA_DENIED (52.6) is a legible marker: an Italian battalion that got no water for
    # its pasta may not exceed its CPA that turn (a no-op in the CPA-bounded engine, so
    # the fold is identity; the cohesion collapse rides the existing COHESION_CHANGED).
    SUPPLY_EVAPORATED = "SUPPLY_EVAPORATED"
    # [29.34]/[49.3]/[52.44] Truck-cargo evaporation. 49.3 evaporates Fuel "regardless of where it
    # is kept" (only convoys AT SEA are exempt) and 29.34 spells it out -- "as well as in trucks" --
    # so a truck's Fuel and Water lose the same 6%+5% as a dump. TRUCK_EVAPORATED {truck_id,
    # commodity, qty} folds like SUPPLY_EVAPORATED but off the truck (cargo down, consumed[] up),
    # so on_hand+consumed==initial holds.
    TRUCK_EVAPORATED = "TRUCK_EVAPORATED"
    # [29.53]/[52.15] Rain refills a depleted well. WELL_REFILLED {supply_id, commodity, qty} is a
    # FAUCET (a rainstorm introduces water), the dual of SUPPLY_ARRIVED: it tops the finite well up
    # AND raises initial_supply by the same qty, so on_hand+consumed==initial holds.
    WELL_REFILLED = "WELL_REFILLED"
    PASTA_DENIED = "PASTA_DENIED"
    # Shortfall counters (51/52). A SHORTFALL increments the unit's consecutive counter
    # (STORES also +1 Disorganization, 51.21); a RESTORED resets it when supply resumes.
    # Attrition (51.22 stores / 52.53 water) rides the existing STEP_LOST role='attrition'
    # and the 51.21 disorganization rides COHESION_CHANGED, feeding the live 17.x surrender.
    STORES_SHORTFALL = "STORES_SHORTFALL"
    WATER_SHORTFALL = "WATER_SHORTFALL"
    STORES_RESTORED = "STORES_RESTORED"
    WATER_RESTORED = "WATER_RESTORED"
    # Ports (rules 55/56.28). PORT_UNLOADED is the legible per-commodity beat of a convoy
    # coming ashore through the harbour throttle {port_id, commodity, qty, tons, eff} -- a
    # marker whose load-bearing state change rides the paired SUPPLY_ARRIVED (so it folds
    # to identity). PORT_EFFICIENCY_CHANGED {port_id, level} sets a port's Efficiency Level
    # (55.14): the 55.18 +1/OpStage regeneration, and later bomb/mine reductions (41.3).
    PORT_UNLOADED = "PORT_UNLOADED"
    PORT_EFFICIENCY_CHANGED = "PORT_EFFICIENCY_CHANGED"
    # Truck convoys (rules 53-54, the inland DISTRIBUTION layer). All three fold PURELY:
    # TRUCK_LOADED {truck_id, supply_id, cargo} and TRUCK_UNLOADED {truck_id, supply_id,
    # cargo} are CONSERVING transfers between a dump and a co-located truck formation (the
    # grand total is unchanged -- invariants.check sums truck cargo alongside the dumps).
    # TRUCK_MOVED {truck_id, from, to, cp_spent, fuel} relocates a formation and burns
    # `fuel` of its OWN cargo fuel (49.18) -- folded like a consume (truck fuel down,
    # consumed[FUEL] up), so on_hand+consumed==initial holds.
    TRUCK_LOADED = "TRUCK_LOADED"
    TRUCK_MOVED = "TRUCK_MOVED"
    TRUCK_UNLOADED = "TRUCK_UNLOADED"
    # [49.14]/[49.16]/[53.11] IN-HEX SUPPLY (Phase 4, Option B: supply pools live ON the unit).
    # These are the unit-pool duals of the dump events above, for the full-game draw where supply
    # must be IN THE HEX (49.15/50.15/51.15), not within a ½-CPA trace. Both are DORMANT until a
    # consumer is switched onto in_hex_draw (design sec 3, the parallel-run):
    #   UNIT_SUPPLY_CONSUMED {unit_id, commodity, qty} -- a unit burns its OWN pool (the 49.14 fuel
    #     tank on a move, or first-line-borne ammo/stores/water). The dual of SUPPLY_CONSUMED: the
    #     unit pool drops and consumed[] rises, so on_hand+consumed==initial holds once unit pools
    #     are summed into on_hand.
    #   UNIT_REFILLED {unit_id, supply_id, commodity, qty} -- the 48 V.C.6 Supply Distribution top-up:
    #     a CONSERVING transfer from a co-located dump into the unit's pool (the dual of TRUCK_LOADED,
    #     dump -> unit instead of dump -> truck). Mints nothing; initial/consumed untouched.
    UNIT_SUPPLY_CONSUMED = "UNIT_SUPPLY_CONSUMED"
    UNIT_REFILLED = "UNIT_REFILLED"
    # [54.11] "ANY HEX CAN BE USED AS A SUPPLY DUMP." SUPPLY_DUMP_ESTABLISHED {supply_id, side,
    # hex} appends a NEW, EMPTY dump to state.supplies -- the missing engine subsystem. Until it
    # existed the depot list was FROZEN AT CONSTRUCTION for all 111 Game-Turns: no EventKind
    # created a dump, apply.py never appended to state.supplies, and _truck_unload rejected any
    # unload with "no co-located friendly dump to unload into". An army therefore could not build
    # the dump network rule 54.16 calls its "top priority", could not extend its chain forward as
    # it advanced, and so could never consolidate an advance. Folds to a pure append of an EMPTY
    # dump -- it mints nothing, so conservation holds trivially; the supplies arrive by the
    # TRUCK_UNLOADED that follows.
    SUPPLY_DUMP_ESTABLISHED = "SUPPLY_DUMP_ESTABLISHED"
    # [32.13]/[49.19]/[50.16]/[51.16] DUMP CAPTURE. SUPPLY_CAPTURED {supply_id, from, to, ammo, fuel,
    # stores, water, lost:{commodity: qty}} flips a field dump's OWNER when an enemy combat unit
    # enters its hex ("if any enemy combat unit enters a Supply Unit's hex, that unit is captured"
    # [32.13]), and TAXES what he may use: the full game keeps only one-third (round up) of the
    # captured Ammunition [50.16] and 50% of the Stores [51.16] -- the rest are LOST -- while Fuel
    # passes intact (non-denominational [49.19]) and Water is untaxed. (The abstract game's "used
    # immediately and freely" is 32.13/47.0, which do not license the full game.) The `lost` amounts
    # are drained and credited to consumed[], so on_hand+consumed==initial holds -- a taxed handover,
    # folded like a consume, not a mint.
    SUPPLY_CAPTURED = "SUPPLY_CAPTURED"
    # [54.14]/[54.17] BLOW THE DUMP. SUPPLY_DUMP_BLOWN {supply_id, unit_id, cp, die, modifier, pct,
    # destroyed:{commodity: qty}} with rng_draws=(die,) is the DEFENDER'S ANSWER TO 32.13: "Players
    # may attempt to BLOW supply dumps and their supplies" -- expend a third of a non-gun unit's
    # basic CPA, roll one die, cross-index the 54.17 Supply Dump Demolition Table, and that
    # percentage of EVERY commodity in the dump is destroyed. Without it, capture is a one-way gift
    # to whoever is advancing, and in September 1940 that is the Axis. With it, an overrun dump is a
    # DECISION -- burn your own fuel, or leave it to the enemy who is one hex away.
    # A pure SINK, folded exactly like 49.3 evaporation (dump down, consumed up), so the
    # conservation identity on_hand+consumed==initial holds.
    SUPPLY_DUMP_BLOWN = "SUPPLY_DUMP_BLOWN"
    # [24.0] CONSTRUCTION -- the Construction Segment of the Organization Phase (48 V.C.4).
    # "Fortifications, minefields, air facilities, repair facilities, roads, RAILROADS and SUPPLY
    # DUMPS all come into existence (for the most part) through construction. Construction entails
    # the use of manpower under the leadership of Engineers, along with the expenditure of time and
    # supplies."
    #
    # CONSTRUCTION_ADVANCED {item, hex, unit_ids, stages, progress} folds one Construction Segment
    # of work onto GameState.construction[hex] -- `stages` company-stages accrued this segment (one
    # per working company, 24.62), `progress` the running total. The Store Points it costs (24.64:
    # one per railroad hex, "actually expended in the Construction Segment") ride the existing
    # SUPPLY_CONSUMED, so conservation is untouched.
    #
    # CONSTRUCTION_COMPLETED {item, hex, from} is 24.11's Construction Completion Step. For a
    # RAILROAD it folds the new hex into the map's rail edge-set -- the ONE dynamic thing on an
    # otherwise static TerrainMap, and the rulebook's own idiom: 24.67's Railhead marker "indicates
    # the extent of construction", and "unbuilt railroad hexes simply do not exist". It clears the
    # hex's Under Construction marker. Emitted only where a line is surveyed (GameState.rail_line),
    # which is the campaign alone.
    #
    # SUPPLY_DUMP_CONSTRUCTED {supply_id, unit_id, cp, stores} is rule 24.9, and it is NOT a
    # multi-stage project: "a supply dump may be constructed by having any one TOE Strength Point of
    # any type expend three Capability Points and 20 Store Points in a hex". No engineer, no elapsed
    # time. It folds SupplyUnit.constructed=True -- which is what lets a truck in convoy LOAD from
    # the hex (24.9's Note), turning a heap of supplies the army dropped in the desert into a LINK
    # the bucket brigade can lift from. The 3 CP ride CP_EXPENDED and the 20 Stores SUPPLY_CONSUMED.
    CONSTRUCTION_ADVANCED = "CONSTRUCTION_ADVANCED"
    CONSTRUCTION_COMPLETED = "CONSTRUCTION_COMPLETED"
    SUPPLY_DUMP_CONSTRUCTED = "SUPPLY_DUMP_CONSTRUCTED"
    # [32.32] MOTORIZATION -- the thirty Truck Points under a desert column, and the freight they
    # are therefore not hauling. "Motorization Points may be attached/detached to supply units ONLY
    # DURING THE ORGANIZATION PHASE of an OpStage. A supply unit not assigned the minimum necessary
    # number of Motorization Points may not be moved."
    #
    # MOTORIZATION_ATTACHED {supply_id, truck_ids, legs, points} books thirty Medium Truck Points
    # (32.51) of the side's own 60.33/60.43 park onto a dump; MOTORIZATION_DETACHED {supply_id,
    # legs, points, reason} gives them back. Both fold GameState.motorization and NOTHING ELSE: the
    # lorries are neither minted nor consumed, they are RESERVED, so conservation is untouched and
    # the whole cost is opportunity cost (game.supply.free_points -- the freight convoy is handed a
    # formation shrunk by exactly what is committed, so its 53.12 load ceiling AND its 49.18 fuel
    # burn both fall).
    #
    # `reason` on the detach is legible only: 'orders' (the staff stood the column down in the
    # Organization Phase) or 'lost' (the dump was captured or blown out from under it -- the column
    # has nothing left to carry). FLAGGED DEFERRAL: 32.56 says that when the unit MPs are assigned
    # to is captured "the Motorization Points are also captured and may be used by the Enemy". We
    # release them to their owner instead of transferring them to the captor -- half of 32.56, the
    # safe half. Doing it properly means minting Truck Points for the enemy at the captured hex,
    # which is a truck-OOB change and not this slice.
    MOTORIZATION_ATTACHED = "MOTORIZATION_ATTACHED"
    MOTORIZATION_DETACHED = "MOTORIZATION_DETACHED"
    # Commonwealth railroad (rule 54.3, the inland rail DISTRIBUTION layer). RAIL_HAULED
    # {from_dump, to_dump, commodity, qty} is a CONSERVING dump->dump transfer over the
    # rail network (both dumps rail-connected; qty <= 1500 tons/OpStage of ONE commodity,
    # 54.33) -- conservation holds trivially (a single transfer, grand total unchanged).
    RAIL_HAULED = "RAIL_HAULED"
    # Vehicle breakdown (rule 21, the desert grinding armor down). BREAKDOWN_CHECKED
    # {unit_id, column, bar, weather_shift, pct} with rng_draws=(d1,d2) is the legible
    # audit beat of a stopping vehicle's 21.38 roll; its fold sets bp_checked_column so
    # the 21.26 re-check gate persists across both players' portions of the OpStage (a
    # check with 0% still moves the gate, 21.26). VEHICLE_BROKE_DOWN {unit_id, amount}
    # moves `amount` TOE from the operational pool into Unit.broken_down (NOT a loss --
    # broken vehicles still exist, immobile, until repaired), so total strength and
    # supply conservation are untouched.
    BREAKDOWN_CHECKED = "BREAKDOWN_CHECKED"
    VEHICLE_BROKE_DOWN = "VEHICLE_BROKE_DOWN"
    # Vehicle repair (rule 22, the counter-beat). VEHICLE_REPAIRED {unit_id, amount}
    # returns `amount` broken-down TOE to the operational pool (the dual of
    # VEHICLE_BROKE_DOWN); the Fuel it costs (22.15) rides the existing SUPPLY_CONSUMED.
    VEHICLE_REPAIRED = "VEHICLE_REPAIRED"
    BARRAGE_RESOLVED = "BARRAGE_RESOLVED"
    ANTI_ARMOR_RESOLVED = "ANTI_ARMOR_RESOLVED"
    COMBAT_RESOLVED = "COMBAT_RESOLVED"
    STEP_LOST = "STEP_LOST"
    # CP-for-all-actions (rule 6.3). CP_EXPENDED {unit_id, activity, cp} charges a unit
    # its Capability Points at the combat seams (barrage / anti-armor / close-assault /
    # defend), folding cp_used += cp into the SAME per-Operations-Stage accumulator that
    # movement (UNIT_MOVED.cp_spent) feeds and _reset_opstage clears at the stage boundary
    # (6.16 / 6.14). A pure scalar fold -- no supply surface touched, conservation untouched.
    # The 6.21 overage -> Disorganization consequence rides the existing COHESION_CHANGED.
    CP_EXPENDED = "CP_EXPENDED"
    COHESION_CHANGED = "COHESION_CHANGED"
    FORT_REDUCED = "FORT_REDUCED"
    HEX_CONTROL_CHANGED = "HEX_CONTROL_CHANGED"
    PHASE_ADVANCED = "PHASE_ADVANCED"
    TURN_ADVANCED = "TURN_ADVANCED"
    VICTORY_CHECKED = "VICTORY_CHECKED"
    # The two-level turn clock (rules 5.1/5.2 + 7.0). STAGE_ADVANCED {stage} advances the
    # Operations Stage within a game-turn (1->2->3) and performs the per-OpStage CP/BP reset
    # (6.16/21.25) via the shared _reset_opstage helper; TURN_ADVANCED now shares that same
    # reset, bumps the game-turn, and re-opens at stage=1. INITIATIVE_DETERMINED {side,
    # axis_total, allied_total} (rng_draws=(ax_d, al_d, ...rerolls)) folds to set
    # GameState.initiative_side once per game-turn (7.14); INITIATIVE_DECLARED {stage,
    # phasing_first} folds to set GameState.phasing_first, the per-stage A/B choice (7.11)
    # that drives the double-move. Nothing emits the initiative events yet (Step 4 wires them).
    STAGE_ADVANCED = "STAGE_ADVANCED"
    INITIATIVE_DETERMINED = "INITIATIVE_DETERMINED"
    INITIATIVE_DECLARED = "INITIATIVE_DECLARED"
    # Continual Movement (rule 8.2/8.23), the exploitation pulse loop. SEGMENT_ADVANCED
    # {segment, side} is the legibility marker opening a pulse: the CP/BP accumulators
    # deliberately PERSIST across it (only STAGE/TURN_ADVANCED reset them, 6.16), so it folds to
    # identity. It emits ONLY when a Policy opts into continual_movement, so every current scenario
    # stays byte-identical.
    SEGMENT_ADVANCED = "SEGMENT_ADVANCED"
    # Reserve Status (rule 18), all folding PURELY (no steps, no supply) so invariants.check is
    # untouched, and all emitted ONLY when a Policy designates via the base-[] hooks -- so every
    # current scenario stays byte-identical. RESERVE_DESIGNATED {unit_id} sets reserve=1 (18.12
    # always places Reserve I); RESERVE_FLIPPED {unit_id} advances an unreleased Reserve I to II
    # (18.13); RESERVE_RELEASED {unit_id, from_tier} clears reserve to 0 and records the tier in
    # reserve_released (0/1/2), which drives the 18.24 half-CPA cap. None costs CP (18.26).
    RESERVE_DESIGNATED = "RESERVE_DESIGNATED"
    RESERVE_FLIPPED = "RESERVE_FLIPPED"
    RESERVE_RELEASED = "RESERVE_RELEASED"
    # Reaction Movement (rule 8.5), the non-phasing tempo interrupt. REACTION_MOVED folds
    # IDENTICALLY to UNIT_MOVED (hex + cp_used + bp): 8.51 'Reaction follows all the standard rules
    # of movement' and 8.52 'expends CP', so it feeds the same 6.14 accumulator -- a distinct kind
    # only for camera legibility (the same rationale that keeps UNIT_RETREATED separate). Emits ONLY
    # when the non-phasing policy opts into react_to, so every current scenario is byte-identical.
    REACTION_MOVED = "REACTION_MOVED"
    # General Rommel (rule 31), all folding PURELY onto GameState.rommel -- no steps, no
    # supply, so invariants.check (conservation + stacking) is untouched. ROMMEL_ARRIVED {hex}
    # is his 64.2 entry -- the Desert Fox reaching Africa (the 3rd OpStage of Game-Turn 26 in the
    # full campaign) -- folding rommel from None to the leader on the board at his arrival hex.
    # ROMMEL_ANCHORED
    # {hex, companions} snapshots the 31.4 'started-the-Operations-Stage-with-him' set at each
    # OpStage boundary (folds anchor_hex + companions); the +5 CPA holds only while he never
    # leaves it (hex == anchor_hex). All emit ONLY when a Rommel is on the board, so every non-
    # Rommel scenario stays byte-identical.
    ROMMEL_ARRIVED = "ROMMEL_ARRIVED"
    ROMMEL_ANCHORED = "ROMMEL_ANCHORED"
    # ROMMEL_MOVED {from, to} is his 31.1 leader move (a 60-MP medium truck ignoring enemy ZOC
    # + stacking); it folds rommel.hex and thereby VOIDS the stage's 31.4 anchor (hex != anchor_
    # hex). ROMMEL_RECALLED {in_germany} is the 31 Berlin recall (2d6, a 12 -> Germany, the ONLY
    # new RNG); True carries the recall dice, False is the auto-return next turn. Both fold onto
    # rommel alone. ROMMEL_CAPTURED is RESERVED for the deferred 27.6 Raid-on-Rommel outcome
    # (never emitted yet). All emit ONLY when a Rommel is on the board.
    ROMMEL_MOVED = "ROMMEL_MOVED"
    ROMMEL_RECALLED = "ROMMEL_RECALLED"
    ROMMEL_CAPTURED = "ROMMEL_CAPTURED"
    # Abstract air (rules 40/45/46 played at the 32.0/58.0 grain). AIR_SUPERIORITY_RESOLVED
    # {arena, axis_fighters, allied_fighters, victor, margin} (rng_draws=(axis_die, allied_die)) is
    # the per-OpStage establishing shot -- who holds the sky over an arena (40/45 air-to-air + 40.27
    # interception + 46 flak abstracted into ONE roll) -- folding air_superiority[arena]=victor (a
    # Side value or None); cleared at the OpStage boundary like the 15.81 Engaged marker. Emits ONLY
    # when a side fields air (GameState.air) and the weather is not foul (29.43/29.52), so every
    # air-less scenario stays byte-identical.
    AIR_SUPERIORITY_RESOLVED = "AIR_SUPERIORITY_RESOLVED"
    # AIR_STRIKE_RESOLVED {arena, target, strength, pinned, loss} is the 41.31 dive-bomber-as-
    # artillery beat: its PIN joins the transient _combat pinned set (12.44, NOT GameState) and any
    # step-loss rides the existing STEP_LOST(role='air_strike'), so the event itself folds to
    # IDENTITY -- a marker like BARRAGE_RESOLVED. Strike is UN-STRIKABLE behind an intact Major-City
    # wall (fort_level>1, 41.31); fort/port bombing REUSE FORT_REDUCED / PORT_EFFICIENCY_CHANGED (no
    # new kind). The naval interdiction seam ALSO emits it (arena='SEA', target=lane) so a convoy cut
    # is legibly air-sourced. AIR_RECON_RESOLVED {arena, hex, revealed} is the 42.2 fog-lift: it folds
    # the (recon-side, hex) pair into the per-OpStage air_sighted set observation.py reads alongside
    # _sighted_hexes; the typed detail (unit class + TOE +-2, bounded by 3.6/42.24) rides in `revealed`
    # (rng_draws = the per-unit noise) for the camera. Both emit ONLY when a side fields air.
    AIR_STRIKE_RESOLVED = "AIR_STRIKE_RESOLVED"
    AIR_RECON_RESOLVED = "AIR_RECON_RESOLVED"
    # [34.17]/[38.21]/[38.24] AIRCRAFT BURN FUEL. "This is the number of Fuel Points a plane requires
    # to perform any mission... all Fuel Points are consumed during a mission, regardless of the type
    # or distance" (34.17); "the fuel is subtracted from the total supply in the air facility"
    # (38.24). The Points themselves ride the existing SUPPLY_CONSUMED off a 36.17 air dump (actor
    # SIDE/Air), so conservation is untouched and no new fold exists for the DRAW.
    #
    # AIR_MISSION_GROUNDED {arena, kind, target, role, points, need, available} is the other half:
    # "planes must have fuel to fly" (38.21) and the Sequence of Play lets only "all planes that are
    # fueled" be assigned missions (33 IV.F.1), so a mission whose bill the side's air-facility dumps
    # cannot cover is NOT FLOWN -- nothing is drawn, no CRT die is rolled, the target is untouched.
    # A marker: it folds to identity and records what the sortie would have cost against what was in
    # the larder. Emitted for a CAP (the per-OpStage air-superiority commitment) as well as for a
    # tasked mission; a side that cannot fuel its fighters commits none and concedes the sky.
    AIR_MISSION_GROUNDED = "AIR_MISSION_GROUNDED"
    # [36.0] AIR FACILITIES -- the base an air force flies from, and the thing bombs take away.
    #
    # AIR_FACILITY_LEVEL_CHANGED {facility_id, level, ...} sets a facility's current Capacity Level
    # -- the exact twin of PORT_EFFICIENCY_CHANGED, and for the same reason: 36.14 ("if bombing has
    # reduced the capacity of an airfield from six to three, that airfield may handle only three
    # squadrons at a time, until it is built back up to six") and 24.76's level-by-level rebuild are
    # one scalar moving both ways. 41.36's bombing result IS this number: "the result is the number
    # of capacity levels that facility is reduced."
    #
    # AIR_FACILITY_DESTROYED {facility_id, kind} takes the counter OFF the map -- 36.2 for a landing
    # strip ("if that capacity level is destroyed, the strip is eliminated and removed from the
    # game-map") and 24.76 for the flying-boat pair, both of which "must be built from scratch if
    # destroyed". An AIRFIELD at zero is NOT removed: it is "considered destroyed for all purposes"
    # (36.14) and stays on the map to be rebuilt a level at a time, so it never emits this.
    #
    # Both fold onto GameState.air_facilities alone -- no TOE, no supply pool -- so conservation and
    # the stacking checks are untouched. 41.36's second clause ("for every level destroyed, remove
    # 10% of the planes on the ground") is DEFERRED with the per-plane ledger it needs (Phase 5.3/5.4).
    AIR_FACILITY_LEVEL_CHANGED = "AIR_FACILITY_LEVEL_CHANGED"
    AIR_FACILITY_DESTROYED = "AIR_FACILITY_DESTROYED"
    # [35.14] SQUADRON GROUND SUPPORT UNIT UPKEEP -- "each SGSU must expend one Stores Point per
    # Game-Turn. In addition, each SGSU requires one Fuel Point and one Water Point per Operations
    # Stage. SGSUs without the required supplies (for themselves) MAY NOT REPAIR THEIR PLANES."
    # SGSU_UNSUPPLIED {unit_id, commodity} increments the unit's stages_without_air_supply counter
    # (the sibling of stages_without_water) and SGSU_SUPPLIED {unit_id} resets it when the upkeep is
    # drawn again -- exactly the WATER_SHORTFALL/WATER_RESTORED pair, on the one counter class with
    # its own supply rule. The supplies themselves ride the existing SUPPLY_CONSUMED (off the 36.17
    # air-facility dump) / UNIT_SUPPLY_CONSUMED (off the SGSU's own pool), so conservation is
    # untouched. game.air.may_refit reads the counter; Phase 5.3's Refit Table reads may_refit.
    SGSU_SUPPLIED = "SGSU_SUPPLIED"
    SGSU_UNSUPPLIED = "SGSU_UNSUPPLIED"
    # Commonwealth off-shore naval bombardment (rule 30.2). NAVAL_BOMBARDMENT {ship_id, target,
    # actual, target_class, target_unit, pinned, loss, half} (rng_draws=(d1,d2)) feeds a ship's
    # Gun Rating as Actual Barrage Points into the 12.6 CRT with NO ammo draw (30.22): the Pin
    # joins the transient _combat pinned set (12.44, NOT GameState) and any step-loss rides the
    # existing STEP_LOST(role='naval'), exactly like a land barrage. Its ONE load-bearing fold is
    # the 30.25 refit -- the ship that fired now owes two Operations Stages in Alexandria, so the
    # fold sets its port_cooldown=2 (ticked back down at each OpStage boundary). Emits ONLY when a
    # side fields naval (GameState.naval), so every naval-less scenario stays byte-identical.
    NAVAL_BOMBARDMENT = "NAVAL_BOMBARDMENT"
    # STAFF_* are narrative / no-op audit events: staff chatter the board is
    # invariant to (they fold to state unchanged; see game.apply, game.staff_events).
    STAFF_INTENT = "STAFF_INTENT"
    STAFF_PROPOSAL = "STAFF_PROPOSAL"
    STAFF_CONSTRAINT = "STAFF_CONSTRAINT"
    STAFF_ADJUDICATION = "STAFF_ADJUDICATION"
    STAFF_DISSENT = "STAFF_DISSENT"


@dataclass(frozen=True, slots=True)
class Event:
    seq: int                       # global total order, 0-based
    turn: int                      # 1..max_turns
    phase: Phase                   # phase active when the event was emitted
    side: Side                     # acting side (or SYSTEM)
    actor: str                     # role id, or "SYSTEM"
    kind: EventKind
    payload: dict                  # json-safe values only (no enums/sets)
    rng_draws: tuple[int, ...] = ()
    stage: int = 1                 # Operations Stage active when emitted (1..3, rule 5.1).
                                   # _Run.emit stamps it from state.stage; apply() ignores it
                                   # (it is derived, not load-bearing) but event_to_dict now
                                   # projects it, so the determinism log certifies the OpStage
                                   # each event was emitted in.


def event_to_dict(e: Event) -> dict:
    """Stable, json-safe projection of an event (for hashing/serialisation)."""
    return {
        "seq": e.seq,
        "turn": e.turn,
        "phase": e.phase.value,
        "side": e.side.value,
        "actor": e.actor,
        "kind": e.kind.value,
        "payload": e.payload,
        "rng_draws": list(e.rng_draws),
        "stage": e.stage,
    }


def log_to_json(events: list[Event]) -> str:
    """Canonical serialisation of an event log; equality of two such strings is
    the determinism test (brief §7: same seed + log => identical game)."""
    return json.dumps([event_to_dict(e) for e in events], sort_keys=True)
