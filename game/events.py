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


class Phase(str, Enum):
    WEATHER = "WEATHER"
    LOGISTICS = "LOGISTICS"        # naval-convoy arrival (rule 48 V.C.7/V.D); SYSTEM-owned
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
    # Full-logistics consumption (rules 49-52). SUPPLY_EVAPORATED (49.3/52.44: 6% of
    # on-map fuel + water per game-turn, +5% hot) folds like a consume -- it drains the
    # dump and adds to consumed[], so it "left the system" and conservation stays exact.
    # PASTA_DENIED (52.6) is a legible marker: an Italian battalion that got no water for
    # its pasta may not exceed its CPA that turn (a no-op in the CPA-bounded engine, so
    # the fold is identity; the cohesion collapse rides the existing COHESION_CHANGED).
    SUPPLY_EVAPORATED = "SUPPLY_EVAPORATED"
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
    # General Rommel (rule 31), all folding PURELY onto GameState.rommel -- no steps, no
    # supply, so invariants.check (conservation + stacking) is untouched. ROMMEL_ANCHORED
    # {hex, companions} snapshots the 31.4 'started-the-Operations-Stage-with-him' set at each
    # OpStage boundary (folds anchor_hex + companions); the +5 CPA holds only while he never
    # leaves it (hex == anchor_hex). All emit ONLY when a Rommel is on the board, so every non-
    # Rommel scenario stays byte-identical.
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
                                   # Legibility only: apply() ignores it and event_to_dict
                                   # omits it, so the determinism log stays byte-identical
                                   # until _Run.emit stamps it in a later step.


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
    }


def log_to_json(events: list[Event]) -> str:
    """Canonical serialisation of an event log; equality of two such strings is
    the determinism test (brief §7: same seed + log => identical game)."""
    return json.dumps([event_to_dict(e) for e in events], sort_keys=True)
