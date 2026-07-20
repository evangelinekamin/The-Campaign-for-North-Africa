"""Orchestrator (brief §4.3, §4.4).

Walks the phase sequence, invokes the owning side's policy, validates orders at
the engine boundary (NOT via constrained decoding, §3.3), and emits events. The
only place RNG lives — outcomes are rolled here and baked into events so apply/
fold stay pure (§4.1).

MOVEMENT is now real: CPA-budget pathing over terrain with Zones of Control and
stacking (game.movement / game.zoc / game.stacking via game.tactics). COMBAT is
still a placeholder CRT (the real land combat — rule 11 — is the next slice).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol

from . import (combat, combat_tables, construction, cp_costs, initiative, logistics_data, stacking,
               supply, tactics, weather, wells)
from .apply import apply
from .dice import DiceBox
from .events import CONTROL_OF, Control, Event, EventKind, Phase, Side
from .hexmap import distance, is_adjacent, neighbors
from .invariants import check_event
from .policy import AttackOrder, MoveOrder, Policy
from .staff_events import clean_staff_payload
from .state import Coord, GameState
from .terrain import Terrain, is_motorized

# Siege of Tobruk tuning knob (rule 25.14): how many effective barrages (a Pin or a
# step loss) it takes to batter a fortification down one level. 1 = each effective
# barrage drops a level. Raise it to make cracking Tobruk harder; the lead tunes
# this (and the Axis ammo/dump schedule) with the benchmark harness.
BARRAGE_HITS_PER_FORT_LEVEL: int = 1

# Abstract air-superiority contest (rules 40/45 air-to-air + 40.27 interception + 46 flak,
# collapsed into ONE roll per arena). Each side commits its fighter Air Points in an arena
# and adds one die (7.14 idiom); the higher total holds the sky, the difference is the margin.
# AIR_SUPERIORITY_LOSER_SCALE is the fraction of its strike/recon Air Points the loser can
# still put over that arena this OpStage (the winner suppresses the rest); a FLAGGED PROXY dial
# like BARRAGE_HITS_PER_FORT_LEVEL, tuned with the benchmark harness. A tie leaves the sky
# contested (victor None) and neither side is scaled.
AIR_SUPERIORITY_LOSER_SCALE: float = 0.5

# Air-strike lethality (rule 41.31). Faithful 41.31 is PIN-ONLY -- the dive bomber suppresses a
# stack (12.44) so it cannot barrage / anti-armor / close-assault the segment, leaving step-losses
# to the artillery. This knob is the owner-tuned severity dial (the BARRAGE_HITS_PER_FORT_LEVEL
# analog): 0 = pin-only (default); >0 = that many TOE Strength Points also lost, riding the
# existing STEP_LOST(role='air_strike').
AIR_STRIKE_STEP_SEVERITY: int = 0

# 30.21 off-shore bombardment reach: a capital ship (Battleship / heavy Cruiser) may bombard one
# hex beyond its own, firing there at HALF its Gun Rating; lighter ships bombard their own hex only.
CAPITAL_SHIP_KINDS: frozenset = frozenset({"BB", "CA"})

# 55.2 harbour BLOCKING (a scuttled ship / air-laid mine) permanently cripples a port
# until Friendly engineers clear the wreck (55.26) -- it is NOT bomb damage, so the 55.18
# +1/OpStage regeneration does NOT restore it. This used to be a module-level frozenset of
# port ids that never regenerated at all, which conflated the scuttling with "the harbour
# can never recover from anything". It is now a per-port count of blocked Efficiency Levels
# (Port.blocked), so a blocked harbour still regenerates bomb damage up to its lowered
# ceiling (max_eff - blocked) -- the San Giorgio holds Tobruk's ceiling at 2 of the 55.3 listed
# 5 (scenario._tobruk_port seeds it, campaign and benchmark alike), but the besieging air force
# must keep bombing to suppress it below that. supply.regen_eff reads the ceiling.


@dataclass(frozen=True, slots=True)
class RunResult:
    initial: GameState
    events: list[Event]
    final: GameState
    winner: Side | None
    reason: str


class _Run:
    """Mutable driver wrapping immutable state — every change flows through apply()
    so live state equals fold(initial, events) by construction."""

    def __init__(self, initial: GameState):
        self.initial = initial
        self.state = initial
        # THE INSTRUMENT (game.dice). One INDEPENDENT stream per subsystem, all derived from
        # the master seed. This used to be a single random.Random shared by every die in the
        # game, and because subsystems draw CONDITIONALLY (_interdict rolls only when an
        # InterdictionOrder covers the lane), changing the number of draws in one subsystem
        # reshuffled the dice every other subsystem saw. Every A/B that toggled a
        # conditionally-drawing feature was measuring that reshuffle. See game/dice.py.
        self.dice = DiceBox(initial.seed)
        self.events: list[Event] = []
        self._seq = 0
        self.fort_hits: dict[Coord, int] = {}   # accumulated barrage hits per hex (25.14)
        # [24.12] The units BOOKED on a construction project this Operations Stage. "Units involved
        # in construction may not expend any Capability Points during an Operations Stage; otherwise
        # that construction is halted" (24.12), and 48 V.C.4.b: they "may not be moved (voluntarily)
        # during the remainder of the current Operations Stage". _movement drops their orders, so the
        # pin is structural rather than a penalty applied after the fact. Cleared at the OpStage
        # boundary, like the 15.81 Engaged marker -- and empty for every scenario that never builds,
        # which is what keeps them byte-identical.
        self.building: set[str] = set()
        # [55.18] the ports that lost one or more Efficiency Levels to Enemy bombs THIS
        # Operations Stage (populated by _air_port). A port in this set does not regenerate at
        # the end of the stage; one that was left alone (or only rolled a [41.5] result of 0)
        # does. Cleared at the OpStage boundary, so an unbombed stage always regenerates.
        self.ports_bombed_this_stage: set[str] = set()
        # [48 III / 48 V.D] each due convoy's SURVIVED manifest for the current Game-Turn:
        # convoy id -> {"dest": dump id|None, "cargo": remaining points, "rail": bool}. The
        # convoy is bombed at sea ONCE per turn (interdiction, strategic 39.13) and its 56.15
        # sail/cancel decision is taken once, both at Stage 1; the survived cargo then unloads
        # across the turn's three Operations Stages (48 V.D), each stage capped by the port's
        # per-OpStage tonnage budget. Rebuilt every turn at Stage 1.
        self.convoy_manifest: dict[str, dict] = {}
        # The VictorySpec's scratchpad, for a condition the board alone cannot answer: 64.71
        # asks whether the Axis has held Alexandria and Cairo "for one full Game-Turn", which
        # is a fact about the RUN, not about the state. It cannot live on the spec object -- a
        # spec is built once per built state (game.scenario.campaign) and two runs of that one
        # state must not share a clock -- so it lives here, with the rest of the per-run
        # bookkeeping, and dies with the run. Empty for every spec that needs no memory.
        self.victory_scratch: dict = {}

    def emit(self, kind: EventKind, side: Side, actor: str, payload: dict,
             rng_draws: tuple[int, ...] = ()) -> None:
        e = Event(self._seq, self.state.turn, self.state.phase, side, actor,
                  kind, payload, rng_draws, self.state.stage)   # stamp the Operations Stage (5.1)
        self._seq += 1
        pre = self.state
        self.state = apply(pre, e)
        check_event(pre, self.state, e)            # delta-aware: touched slice + boundary full sweep
        self.events.append(e)

    def d6(self, subsystem: str) -> int:
        """One die, from `subsystem`'s own stream (game.dice.SUBSYSTEMS). The subsystem is
        named at every call site on purpose: which stream a die comes off is a property of
        the rule being resolved, and it is the one thing that must never be guessed."""
        return self.dice.d6(subsystem)

    def go(self, phase: Phase, side: Side) -> None:
        self.emit(EventKind.PHASE_ADVANCED, Side.SYSTEM, "SYSTEM",
                  {"phase": phase.value, "active_side": side.value})


def run(initial: GameState, axis: Policy, allied: Policy) -> RunResult:
    r = _Run(initial)
    policies = {Side.AXIS: axis, Side.ALLIED: allied}
    r.emit(EventKind.GAME_INITIALIZED, Side.SYSTEM, "SYSTEM",
           {"seed": initial.seed, "max_turns": initial.max_turns})

    winner: Side | None = None
    reason = "campaign reached final turn"
    cursor = {Side.AXIS: 0, Side.ALLIED: 0}

    def _debrief(side: Side) -> None:
        # Hand the policy the events since it last acted (its rejected orders, losses,
        # ground changes, enemy sorties) -- a commander receives dispatches between
        # decisions. Optional (hasattr): scripted policies ignore it. Pure function of
        # the seeded event log, so replay stays deterministic.
        pol = policies[side]
        if hasattr(pol, "debrief"):
            pol.debrief(r.events[cursor[side]:])
        cursor[side] = len(r.events)

    # The real two-level clock (rules 5.1/5.2 + 48): each GAME-TURN opens with the once-
    # per-turn Stores Expenditure Stage (48 IV), then runs THREE Operations Stages (48 V),
    # each its own OpStage with its own weather (29.0), water (52) and CPA budget (6.16).
    done = False
    while not done:
        recalled = _rommel_recall(r)                    # 31 Berlin recall (the ONLY new RNG) -- BEFORE initiative
        _initiative(r, axis_recalled=recalled)          # 5.2 I / 7.14: who holds Initiative this game-turn
        _stores_setup(r)                                # 48 IV: Stores Expenditure + 6% base evaporation
        for stage in (1, 2, 3):
            r.ports_bombed_this_stage = set()            # 55.18: this stage's bomb ledger starts empty
            _rommel_arrival(r, stage)                    # 64.2: the Desert Fox lands (GT26.3) -- BEFORE the anchor
            _rommel_anchor(r)                            # 31.4: snapshot who he starts THIS stage with
            first, second = _declare_ab(r, policies, stage)   # 5.2.III.A / 7.11: the A/B activation order
            r.go(Phase.WEATHER, Side.SYSTEM)
            _weather(r)                                 # 29.0: weather is rolled per Operations Stage
            _well_refill(r)                             # 29.53: a rainstorm refills depleted wells
            _water_body(r)                              # 48 V.C.1: water draw + the +5% hot-evap slice
            if stage == 1:                              # reinforcement UNITS arrive once, in the 1st stage
                _reinforcements(r)
            _naval_convoys(r, policies)                  # 48 V.D: the Naval Convoy Arrival Phase runs
                                                         # EVERY Operations Stage (VI/VII repeat all of V) --
                                                         # the turn's manifest unloads across the stages
            _air_superiority(r)                          # 40/45/46: contest the sky this OpStage (per arena)
            for side in (first, second):                # 7.16: Player A (first) then Player B (last)
                _debrief(side)                          # enemy portion + own last combat
                _organization(r, policies[side], side)  # 32.32: the ONE beat MP may be attached to
                                                        # or detached from a dump -- BEFORE the
                                                        # Construction Segment, which is inside it
                _construction(r, policies[side], side)  # 48 V.C.4 / 24.11: the Construction Segment,
                                                        # BEFORE movement -- 24.12 pins whoever works
                _supply_distribution(r, side)           # 48 V.C.6: 0-CP top-up of unit pools from a
                                                        # co-located dump (the in-hex refill beat)
                _reserve_designation(r, policies[side], side)   # 48 V.G / 18.11: hold units back (phasing)
                r.go(Phase.MOVEMENT, side)
                _blow_dumps(r, policies[side], side)    # 54.14: deny the enemy your stocks -- BEFORE
                                                        # you move off them, and before he moves onto
                                                        # them ("blown in any segment of an OpStage")
                _movement(r, policies, side)            # segment 0 (ungated); Reaction (8.5) rides inside
                _capture_dumps(r)                       # 32.13: a dump entered by the enemy changes hands
                _rommel_move(r, policies[side], side)   # 31.1: the leader repositions (Axis only, self-guarded)
                _breakdown(r, side)                     # 21.24: check vehicles that ceased moving
                _supply_movement(r, policies[side], side)   # supply follows the army (32.3)
                _debrief(side)                          # which moves/pincers actually formed
                r.go(Phase.COMBAT, side)
                _combat(r, policies, side)
                _capture_dumps(r)                       # 32.13: retreats and advances-after-combat too
                _breakdown(r, _other(side))             # 21.22: the enemy's retreats accrued BP too
                _repair(r, side)                        # 22.12: the phasing side's Repair Phase
                _continual_movement(r, policies, side)  # 8.2/8.23 + 18.13: the exploitation pulse loop
                _capture_dumps(r)                       # 32.13: and the exploitation pulse
            for side in (first, second):
                _truck_convoys(r, policies[side], side)  # V.J: 2nd/3rd-line truck convoys (48)
            _port_regen(r)                               # 55.18: end of OpStage -- every port that lost
                                                         # NO Efficiency Levels to bombs this stage regains one
            r.go(Phase.RECORD, Side.SYSTEM)
            _record_control(r)
            victory = r.state.victory or _DEFAULT_VICTORY
            winner, reason = victory.check(r)
            if winner is not None:
                done = True
                break
            if stage == 3 and r.state.turn >= r.state.max_turns:
                winner, reason = victory.decide(r)
                done = True
                break
            _idle_recovery(r)                           # 6.24.1: reward a CP-idle stage (before the reset)
            if stage < 3:                               # next Operations Stage: refresh the CPA window (6.16)
                r.emit(EventKind.STAGE_ADVANCED, Side.SYSTEM, "SYSTEM", {"stage": stage + 1})
            else:                                       # a new game-turn re-opens at Operations Stage 1
                _defer_crowded_reinforcements(r, r.state.turn + 1)   # rule 20: wait for stacking room
                r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM", {"turn": r.state.turn + 1})
            r.building.clear()                          # 24.12: the pin lasts one Operations Stage

    return RunResult(r.initial, r.events, r.state, winner, reason)


# --- initiative (rule 7) -----------------------------------------------------

def _initiative(r: _Run, axis_recalled: bool = False) -> None:
    """Initiative Determination (rule 5.2 I / 7.14), once per GAME-TURN. While the scenario
    fixes the holder (7.15 / 61.5 / 64.4: e.g. Axis through GT27, or the Italians on GT1) no die
    is rolled; otherwise each side rolls 1 die + its Initiative Rating and the higher total wins,
    ties rerolled in the seeded stream (7.14). Folds into GameState.initiative_side, held for all
    three Operations Stages (7.12).

    The Initiative Ratings come from the transcribed [7.2] chart when the scenario opts in
    (GameState.initiative_chart -- the full campaign): the Commonwealth rating by date and the
    Axis rating by whether Rommel / German land combat units stand on the maps (game.initiative,
    docs/rules/90:607-617). A scenario that sets no chart -- the Desert Fox benchmarks, on their
    synthetic 1..12 clock -- reads its fixed initiative_ratings instead.

    `axis_recalled` fires on the game-turn General Rommel's Berlin recall sent him to Germany
    (31): the Axis Initiative Rating is clamped to min(rating, 3) AND the 7.15 predetermined
    hold is suspended so the determination is actually ROLLED -- so 'Axis Initiative falls to
    3' genuinely bites even in the fixed window, and can only ever HURT the Axis. (Under the
    [7.2] chart the clamp is already implied -- a Rommel in Germany is not on the maps, so
    axis_rating reads the rating-3 row -- but it is kept so the fixed-ratings path recalls too.)"""
    s = r.state
    if not axis_recalled and s.initiative_fixed is not None and s.turn <= s.initiative_fixed_until:
        r.emit(EventKind.INITIATIVE_DETERMINED, Side.SYSTEM, "SYSTEM",
               {"side": s.initiative_fixed.value, "fixed": True})     # 7.15: predetermined, no die
        return
    if s.initiative_chart:                               # [7.2], the transcribed chart (game.initiative)
        ax_rating = initiative.axis_rating(s)
        al_rating = initiative.commonwealth_rating(s.turn)
    else:                                                # a scenario's fixed proxy ratings (benchmarks)
        ax_rating = s.initiative_ratings.get("AXIS", 0)
        al_rating = s.initiative_ratings.get("ALLIED", 0)
    if axis_recalled:
        ax_rating = min(ax_rating, 3)                    # 31 Berlin recall: Axis Initiative falls to 3
    draws: list[int] = []
    while True:                                          # 7.14: ties reroll
        ad, ld = r.d6("initiative"), r.d6("initiative")
        draws += [ad, ld]
        axis_total, allied_total = ad + ax_rating, ld + al_rating
        if axis_total != allied_total:
            break
    winner = Side.AXIS if axis_total > allied_total else Side.ALLIED
    r.emit(EventKind.INITIATIVE_DETERMINED, Side.SYSTEM, "SYSTEM",
           {"side": winner.value, "axis_total": axis_total, "allied_total": allied_total},
           rng_draws=tuple(draws))


def _double_move_first(initiative_side: Side, stage: int) -> Side:
    """The default A/B declaration heuristic (rule 7.11/7.12): the Initiative side moves LAST
    in Operations Stage 2 and FIRST otherwise, so across the stage 2->3 boundary it acts last-
    in-2 then first-in-3 -- the consecutive-stage DOUBLE-MOVE (7.12). Returns who moves FIRST."""
    return _other(initiative_side) if stage == 2 else initiative_side


def _declare_ab(r: _Run, policies: dict, stage: int) -> tuple[Side, Side]:
    """Initiative Declaration (rule 5.2.III.A / 7.11), per Operations Stage: the Initiative
    holder declares whether it moves first (Player A) or last (Player B). An optional
    Policy.declare_ab(state, stage)->Side hook lets an agent choose (hasattr, like debrief);
    otherwise the scripted default exercises the 7.12 double-move. Emits INITIATIVE_DECLARED
    (folds to phasing_first) and returns the ordered (first, second) that replaces the old
    hardcoded (AXIS, ALLIED)."""
    init = r.state.initiative_side
    holder = policies[init]
    if hasattr(holder, "declare_ab"):
        first = holder.declare_ab(r.state, stage)       # 7.11: the holder's own choice
        if first not in (Side.AXIS, Side.ALLIED):        # boundary-validate the hook's answer
            first = _double_move_first(init, stage)
    else:
        first = _double_move_first(init, stage)
    r.emit(EventKind.INITIATIVE_DECLARED, init, "SYSTEM",
           {"stage": stage, "phasing_first": first.value})
    return first, _other(first)


# --- Rommel (rule 31) --------------------------------------------------------

def _rommel_arrival(r: _Run, stage: int) -> None:
    """64.2 / 31: General Rommel reaches Africa at his scheduled moment -- the 3rd OpStage of
    Game-Turn 26 in the full campaign (the fourth week of March 1941). Fires once: when a scenario
    schedules an arrival (GameState.rommel_arrival), the entity is not yet on the board, and
    (turn, stage) matches, lift him onto the map at the DAK's entry hex (ROMMEL_ARRIVED). From the
    NEXT game-turn's 7.14 determination the Axis then reads the [7.2] rating-6 row -- the tempo
    inverts the moment the Desert Fox lands. Self-guarded (no schedule, or already arrived, or the
    moment not reached => no event), so every scenario without a scheduled arrival stays
    byte-identical."""
    a = r.state.rommel_arrival
    if a is None or r.state.rommel is not None:
        return
    if r.state.turn == a.turn and stage == a.stage:
        r.emit(EventKind.ROMMEL_ARRIVED, Side.AXIS, "SYSTEM", {"hex": list(a.hex)})


def _rommel_anchor(r: _Run) -> None:
    """31.4: at each Operations-Stage boundary, snapshot the Axis COMBAT units stacked with
    General Rommel -- the set that, if it never leaves his hex and he never leaves it, draws his
    +5 CPA this stage (tactics.effective_cpa). Emits ROMMEL_ANCHORED (folds anchor_hex +
    companions). Silent -- no event -- when no Rommel is on the board or he is in Germany, so
    every non-Rommel scenario stays byte-identical."""
    rom = r.state.rommel
    if rom is None or rom.in_germany:
        return
    companions = sorted(u.id for u in r.state.units_at(rom.hex)
                        if u.side == Side.AXIS and u.is_combat)
    r.emit(EventKind.ROMMEL_ANCHORED, Side.AXIS, "SYSTEM",
           {"hex": list(rom.hex), "companions": companions})


def _rommel_recall(r: _Run) -> bool:
    """31 Berlin recall, once per GAME-TURN General Rommel is on the board -- the ONLY new RNG in
    rule 31, drawn HERE, before Initiative, so its stream position is pinned. If he is already in
    Germany from last turn, auto-return him first (ROMMEL_RECALLED in_germany=False, no dice),
    then roll normally. Roll 2d6 and emit ROMMEL_RECALLED UNCONDITIONALLY, carrying the dice so
    every game-turn's roll is certified in the log: a 12 folds in_germany=True and returns True
    so _initiative clamps the Axis rating to min(rating, 3) this game-turn; anything else folds
    in_germany=False (a no-op on the on-map Rommel) and returns False. Draws NO dice and returns
    False when no Rommel is present, so every non-Rommel scenario is byte-identical."""
    rom = r.state.rommel
    if rom is None:
        return False
    if rom.in_germany:
        r.emit(EventKind.ROMMEL_RECALLED, Side.AXIS, "SYSTEM", {"in_germany": False})
    d1, d2 = r.d6("rommel"), r.d6("rommel")
    recalled = d1 + d2 == 12
    # Emit UNCONDITIONALLY, carrying the 2d6, so the recall roll's dice are certified in the
    # log every game-turn (not only on a 12). A non-12 folds in_germany=False -- a no-op on the
    # already-on-map Rommel -- so state is untouched; only the RNG stream is now auditable.
    r.emit(EventKind.ROMMEL_RECALLED, Side.AXIS, "SYSTEM",
           {"in_germany": recalled}, rng_draws=(d1, d2))
    return recalled


def _rommel_move(r: _Run, policy: Policy, side: Side) -> None:
    """31.1: General Rommel's leader move in the Axis Movement Phase. An optional
    Policy.rommel_move(state)->Coord|None hook (hasattr, symmetric with declare_ab) names his
    destination; the engine validates it lies within his 60-MP medium-truck reach (tactics.
    rommel_reach, ignoring enemy ZOC + stacking per 31.2/27.14) and emits ROMMEL_MOVED {from,
    to}. He consumes NO fuel -- the 27.38 raider analog (FLAGGED). Silent for a non-Axis side,
    no Rommel, a Rommel in Germany, or no hook, so every non-Rommel scenario stays byte-
    identical."""
    if side != Side.AXIS:
        return
    rom = r.state.rommel
    if rom is None or rom.in_germany or not hasattr(policy, "rommel_move"):
        return
    dest = policy.rommel_move(r.state)
    if dest is None or tuple(dest) == rom.hex:
        return
    dest = tuple(dest)
    if dest not in tactics.rommel_reach(r.state):        # boundary-reject an unreachable destination
        return
    r.emit(EventKind.ROMMEL_MOVED, Side.AXIS, f"{side.value}/Front",
           {"from": list(rom.hex), "to": list(dest)})


# --- phases ------------------------------------------------------------------

def _reinforcements(r: _Run) -> None:
    """Bring on any units scheduled to enter this game-turn (rule 20). Each is
    already in state at its entry hex but dormant (off-map, state.on_map) until its
    arrival_turn; this records the arrival. The scenario must give entry hexes room
    to stack (checked by the invariant on arrival)."""
    for u in r.state.units:
        if u.arrival_turn == r.state.turn and u.alive:
            r.emit(EventKind.REINFORCEMENT_ARRIVED, u.side, "SYSTEM",
                   {"unit_id": u.id, "hex": list(u.hex), "turn": r.state.turn})


def _defer_crowded_reinforcements(r: _Run, next_turn: int) -> None:
    """Rule 20 -- reinforcements WAIT for stacking room. Before the game-turn advances (which
    would otherwise pop a scheduled unit on-map via state.on_map the instant turn >= arrival_turn),
    scan the units due to enter `next_turn` whose entry hex is already at the 9.31 hex limit and
    DEFER them: bump arrival_turn one game-turn so the unit stays dormant (off-board, uncounted by
    the stacking check) and retries next turn -- so the stacking invariant can never crash at the
    TURN_ADVANCED fold. Units that fit are admitted greedily in deterministic id order, each
    reserving its room, so two arrivals onto one hex cannot together over-stack. Fires ONLY when an
    entry hex is genuinely over-full for an arrival, so every scenario whose reinforcements have
    room at their arrival turn (the scripted seeds) emits nothing here and stays byte-identical."""
    due = sorted((u for u in r.state.units
                  if u.alive and not r.state.on_map(u) and u.arrival_turn == next_turn),
                 key=lambda u: u.id)
    admitted: dict = {}                                  # entry hex -> units that will fit this turn
    for u in due:
        terrain = r.state.terrain.terrain[u.hex]
        present = list(r.state.units_at(u.hex)) + admitted.get(u.hex, [])
        if stacking.within_hex_limit(present + [u], terrain):
            admitted.setdefault(u.hex, []).append(u)     # fits: leave it to arrive on schedule
        else:
            r.emit(EventKind.REINFORCEMENT_DELAYED, u.side, "SYSTEM",
                   {"unit_id": u.id, "hex": list(u.hex),
                    "arrival_turn": next_turn + 1, "reason": "no stacking room"})


def _interdiction_for(state: GameState, convoy):
    """The air-interdiction pressure on this convoy's lane this game-turn (rules 41.6 /
    32.63), or None. rng-free -- a static-schedule lookup keyed by lane + game-turn, the
    exact twin of a convoy's arrival_turn match."""
    for o in state.interdictions:
        if o.lane == convoy.lane and o.turn == state.turn:
            return o
    return None


def _convoy_loss_pct(bomb_points: int, d1: int, d2: int) -> int:
    """[41.66] resolve one convoy-bombing attack on the [41.5] Air Bombardment CRT: pick the
    Bomb-Point column, read the two dice SEQUENTIALLY as a two-digit code (tens=d1, units=d2),
    and return the tens-of-percent of cargo lost. Bomb Points below the table's floor never
    damage a convoy (returns 0)."""
    code = d1 * 10 + d2
    for col in logistics_data.convoy_bombing_crt_41_66():
        lo, hi = col["bomb_points"]
        if bomb_points >= lo and (hi is None or bomb_points <= hi):
            for entry in col["results"]:
                dlo, dhi = entry["die"]
                if dlo <= code <= dhi:
                    return entry["pct_lost"]
    return 0


def _port_bomb_levels(bomb_points: int, d1: int, d2: int) -> int:
    """[41.39B / 41.5] resolve one harbour-bombing attack on the Air Bombardment CRT's Ports
    row: pick the Bomb-Point column, read the two dice SEQUENTIALLY as a two-digit code
    (tens=d1, units=d2), and return the number of Efficiency Levels the port loses (0-4).
    Bomb Points below the table's floor lose nothing (returns 0). At the campaign's proxy
    six strike Air Points (column 1..20) the roll is a 0 on 32 of 36 codes and a 1 on 4 --
    which is what lets the harbour regenerate (55.18) between the bombs and makes the siege a
    duel rather than a one-way ratchet."""
    code = d1 * 10 + d2
    for col in logistics_data.air_port_bombing_crt_41_5():
        lo, hi = col["bomb_points"]
        if bomb_points >= lo and (hi is None or bomb_points <= hi):
            for entry in col["results"]:
                dlo, dhi = entry["die"]
                if dlo <= code <= dhi:
                    return entry["levels"]
    return 0


def _apply_convoy_loss(cargo: dict, pct: int) -> tuple[dict, int]:
    """[41.67] divide the CRT loss evenly across the convoy's commodities, rounding each LOST
    amount UP and flooring delivered at >= 0. Returns (reduced_cargo, tons_lost) -- tons via
    the 54.5 equivalent weights, for the CONVOY_INTERDICTED marker."""
    reduced: dict = {}
    tons_lost = 0
    for k, v in cargo.items():
        lost = math.ceil(v * pct / 100)
        reduced[k] = max(0, v - lost)
        tons_lost += supply.points_to_tons(lost, k)
    return reduced, tons_lost


def _interdict(convoy, state: GameState, rng):
    """The interdiction worker shared by interdict() and _naval_convoys: returns
    (reduced_cargo, order|None, pct_lost, tons_lost, dice). Draws the two [41.66] CRT dice on
    `rng` ONLY when an InterdictionOrder covers this lane+turn; an interdiction-free lane draws
    nothing and returns the cargo verbatim with dice=(). The dice ride out so the
    CONVOY_INTERDICTED marker can certify them in the log.

    THIS IS THE CONDITIONAL DRAW THAT BROKE THE INSTRUMENT, and the fix is that `rng` is now
    interdiction's OWN stream (game.dice), never the whole engine's. It used to be the shared
    one, and the docstring here defended the conditional draw as "byte-identical" -- which is
    exactly backwards: skipping a draw on the SHARED stream kept an unbombed lane's log stable
    while shifting every weather, breakdown, morale and CRT roll for the rest of the war the
    moment you DID bomb one. Malta was measured through that and pronounced inert. Whether this
    function draws or not must now be invisible to every other subsystem, and tests/test_dice.py
    holds that line."""
    order = _interdiction_for(state, convoy)
    if order is None:
        return dict(convoy.cargo), None, 0, 0, ()
    d1, d2 = rng.randint(1, 6), rng.randint(1, 6)      # 41.66: two dice, read sequentially
    pct = _convoy_loss_pct(order.bomb_points, d1, d2)
    reduced, tons_lost = _apply_convoy_loss(convoy.cargo, pct)
    return reduced, order, pct, tons_lost, (d1, d2)


def interdict(convoy, state: GameState, rng) -> dict:
    """Air interdiction of a convoy in transit (rules 41.6 / 32.63-32.66) -- the crack's
    ferry-cut, the convoys/ports/trucks idiom carried into the AIR arena. If no
    InterdictionOrder covers this convoy's lane this game-turn, the cargo arrives verbatim and
    no die is drawn. Otherwise the seam rolls 2d6 on the [41.5] Air Bombardment CRT (41.66) and
    skims that tens-of-percent off the cargo (41.67, split evenly, each LOST amount rounded up)
    before it lands. Returns the (possibly reduced) cargo; the paired CONVOY_INTERDICTED marker
    rides in _naval_convoys beside the smaller SUPPLY_ARRIVED. `rng` is interdiction's own
    stream -- pass r.dice.stream("interdiction"), never a stream another subsystem shares."""
    return _interdict(convoy, state, rng)[0]         # cargo only; the marker's dice ride separately


def _convoy_dest(state: GameState, convoy):
    """The dump a convoy actually lands its cargo in this game-turn, or None if it never sails.

    Rule 56.15 cancels a convoy whose destination is in enemy hands, and for a PORT that is the
    whole story -- a captured harbour receives nothing. A RAILHEAD is not a port. It is the
    furthest point the OPERATING railway reaches that you still hold (54.3), and rule 60.7's "the
    RR runs to Mersa Matruh and ends there" names the terminus, not the only station: let an enemy
    vehicle drive across Mersa Matruh and the railhead falls BACK east down the line -- the trains
    keep running, to the last station you control.

    So the destination is a LINE (Convoy.retarget, ordered forward to rear) and this walks it: the
    first station the enemy does not control is this turn's railhead. Deterministic by
    construction -- the seeded order IS the key, no sort to drift. A convoy with NO line (every
    convoy in every scenario but the campaign's Commonwealth rail lane) reads exactly `dest` under
    the verbatim 56.15 test, so nothing else moves one byte."""
    enemy = CONTROL_OF[_other(convoy.side)]
    for sid in convoy.retarget or (convoy.dest,):
        dump = state.supply(sid)
        if dump is not None and state.control_of(dump.hex) != enemy:
            return dump
    return None


# --- [54.3] THE RAILWAY UNLOADS ALONG ITS LINE --------------------------------------------------
def _rail_dump_id(side: Side, hex_: Coord) -> str:
    """The id a railway-established station takes on the hex it is unloaded at (54.11). Keyed on the
    hex, so the same station keeps the same counter for the whole war.

    IT MUST CARRY THE "-Stage-" PREFIX, and this is load-bearing, not cosmetic. campaign_claim.STAGING
    ("AX-Stage"/"AL-Stage") is how the whole campaign layer tells a PLACE ON THE SUPPLY LINE from an
    army's MOBILE FIELD DUMP, and a railway station is emphatically the former -- the same family as
    the Mersa Matruh railhead and the Operation Compass Field Supply Depots. Three separate rules key
    off it, and every one of them was wrong while these were called "AL-Rail-":

      * campaign_claim.is_field_dump would have called a station a mobile dump, and engine.
        _supply_movement (32.3) would have WALKED THE STATIONS OFF THE RAILWAY with the army;
      * campaign_policy._relay_source lets a lorry LIFT only from the supply line or a faucet -- so
        the railway was stocking forty stations THE TRUCK RELAY COULD NOT LOAD FROM, which severs
        the one chain this whole change exists to build (rail -> station -> lorry -> the front);
      * campaign_claim.hold_depots keeps a field dump from parking on top of a spine hex and masking
        it (measured, twice, and both times it cost the campaign a hundred Victory Points)."""
    return f"{'AX' if side == Side.AXIS else 'AL'}-Stage-Rail-{hex_[0]:02d}.{hex_[1]:03d}"


def _rail_stops(r: _Run, convoy, terminus) -> list:
    """[54.35] The hexes this game-turn's train unloads its freight at, FORWARD-FIRST.

    THE BUG THIS FIXES, and it is the one that made every knob downstream inert. The lane landed
    its whole 1500-tons-per-OpStage haul (54.32) on ONE dump -- the Mersa Matruh railhead -- and
    left every other station on four hundred miles of working railway at ZERO. Our supply trace
    runs to DUMPS and to nothing else (32.16), so the Nile Delta and the railhead were the only two
    hexes in Egypt where an Eighth Army battalion could eat, and the four hundred miles of Britain's
    own base area between them read as out-of-supply desert. The army could not march up its own
    railway, so it never consolidated an advance, so nothing ever changed hands, so the final score
    was the September-1940 depot geography read out 111 turns later.

    THE RULE. 54.35: "supplies may be moved from any one spot and DUMPED IN ANOTHER SPOT. Supplies
    are considered unloaded when they REACH A SPECIFIC HEX." 54.11: "ANY HEX can be used as a supply
    dump." So the railway's freight may be set down at any hex on the line, at the player's choice,
    every Operations Stage -- and 54.16 tells him to ("establishing a viable dump network should be
    TOP PRIORITY for logistics commanders"). There is no reason on earth for a rail hex with an army
    standing on it to be empty: the train simply stops there.

    THE STOPS, therefore, are: every OPERATING rail hex (52.22 -- one the enemy does not control;
    54.41 gives him control by being the last to pass a combat unit through it) that a friendly
    COMBAT UNIT IS STANDING ON, plus the `terminus` railhead, which is always served because it is
    the forward depot the army is heading for. Ordered forward-first (this map's axial r IS the
    east-west axis, so the smallest r is the westernmost hex = nearest the enemy).

    A unit standing on a stop ends up with a dump IN ITS OWN HEX, which satisfies not just the
    32.16 trace but the STRICTER rule the full logistics game actually asks for (49.15: "for fuel to
    be consumed, it must be present in the same hex with the consuming unit"; 51.15: "Stores must be
    present in the hex to be used"). Units NEAR the line then trace to those dumps at cpa/2.

    FLAGGED AS DOCTRINE, NOT RULE: WHICH hex the player unloads at is his free choice under 54.35,
    and "stop where the troops are" is our staff's standing order, not a magnitude out of the book.
    What is NOT ours is the tonnage -- the haul is exactly the 54.32 charted 1500 tons/OpStage it
    always was. This moves WHERE the freight lands, and not one point of HOW MUCH.

    With no combat unit on the line the stop list is just the terminus, which is precisely today's
    behaviour -- so a state with no rails (every scenario but the campaign) reads byte-identical."""
    state = r.state
    rails = state.terrain.rails
    if not rails:                                   # no railway: the vanilla single-destination lane
        return [terminus]
    enemy = CONTROL_OF[_other(convoy.side)]
    on_line = {h for e in rails for h in e}
    manned = {u.hex for u in state.living(convoy.side) if u.is_combat} & on_line

    def stop_at(h):
        dump = _dump_on(state, convoy.side, h)
        if dump is not None and dump.base:
            # RULE 57: the railway hauls supply AWAY from the bottomless base, never into it. The
            # Commonwealth "has an unlimited amount of supplies of all types in Cairo at all times;
            # HIS PROBLEM IS SOLELY TO GET IT TO WHERE HE WANTS IT." The Delta end of the line is a
            # SOURCE. Left as a stop, the garrison standing on Alexandria would make the base a
            # destination and throw a whole share of the 54.32 haul into a 125,000,000-point depot
            # that did not need it -- the one way this change could quietly cost the army supply.
            return None
        return dump or h

    # Forward-first: westernmost (smallest axial r) first. A dump object and a bare hex both answer
    # to the same key, so an established station and a fresh one sort into one line. The ORDER is
    # load-bearing: _rail_deliver gives each stop an even cut and then CASCADES the remainder down
    # this list, so whatever stands first gets the surplus of the whole train.
    out = [s for s in (stop_at(h) for h in sorted(h for h in manned
                                                  if state.control_of(h) != enemy))   # 52.22
           if s is not None]
    if terminus is not None and terminus.id not in {d.id for d in out if not isinstance(d, tuple)}:
        out.append(terminus)                        # the railhead is always served (60.7)
    out.sort(key=lambda d: (d if isinstance(d, tuple) else d.hex)[1])

    # [24.67] AND THE CONSTRUCTION RAILHEAD, wherever the New Zealanders have pushed it to -- LAST.
    # "A Railhead marker is provided to indicate the extent of construction": the end of the track is
    # where a train can go and no further, so it is a stop by definition, manned or not, and it has to
    # be, because the gang laying the next hex are ENGINEERS (23.11 -- not combat units "in any way,
    # shape, or form"), `manned` never sees them, and 24.64 wants a Store Point present WITH them. A
    # railway whose builders starve does not get built.
    #
    # BUT IT GOES ON THE END OF THE CASCADE, and this is not a nicety -- it is a measured regression.
    # Sorted forward-first with everything else, the construction railhead is by definition the
    # westernmost stop on the line, so it took the even cut AND the entire surplus of the train: at
    # Game-Turn 12 the whole 54.32 haul was running fifty miles past the Eighth Army to a hex with two
    # engineer companies on it, and MERSA MATRUH -- the railhead the army actually stands on and
    # fights from -- was left at ZERO Ammunition and ZERO Fuel. The freight goes to the TROOPS; the
    # work site gets its ration, which is one Store Point a hex. Both are 54.35's free choice of where
    # to set the load down, and this is the choice a staff would make.
    head = construction.rail_head(state)
    if head is not None and state.control_of(head) != enemy and head not in manned:
        stop = stop_at(head)
        if stop is not None and (isinstance(stop, tuple)
                                 or stop.id not in {d.id for d in out if not isinstance(d, tuple)}):
            out.append(stop)
    return out


def _dump_on(state: GameState, side: Side, hex_):
    """The friendly FIELD dump already standing on `hex_`, if any -- the existing Mersa Matruh
    railhead, an Operation Compass Field Supply Depot, a station the train founded last week.

    ONE DUMP PER HEX, which is the idiom _establish_dump already enforces for the lorries ("a
    friendly dump already stands on this hex (54.11)"), and here it is load-bearing: a second dump
    beside the first would hand that hex a SECOND 54.12 Supply Dump Capacity, silently doubling the
    ceiling the whole logistics chain is throttled by. 32.14 permits several Supply Units to stack,
    but our dump IS the hex's capacity, not a counter, so it must not be minted twice. A well or a
    pipeline hex is geography, never a freight depot, so it is skipped (game.wells.is_water_source)."""
    return next((s for s in sorted(state.supplies, key=lambda s: s.id)
                 if s.hex == hex_ and s.side == side and not s.is_dummy
                 and not wells.is_water_source(s)), None)


def _rail_deliver(r: _Run, convoy, terminus, cargo: dict) -> None:
    """Land one game-turn of railway freight (54.32) across the line's stops (_rail_stops).

    EQUAL SHARES, THEN CASCADE FORWARD. Each stop takes an even cut of the haul -- capped by its
    54.12 Supply Dump Capacity -- and whatever will not fit (or the integer remainder) cascades to
    the stops in forward-first order until the train is empty. A garrison on the line gets enough to
    eat; the surplus still runs up to the front, which is where a staff sends it.

    The total landed is UNCHANGED -- it is the 54.32 haul, to the point. Nothing is minted here that
    was not minted before; it merely gets off the train at more than one station."""
    stops = [d for d in (_rail_station(r, convoy, s) for s in _rail_stops(r, convoy, terminus))
             if d is not None]
    if not stops:
        return
    for commodity in sorted(cargo):
        left = cargo[commodity]
        if left <= 0:
            continue
        share = left // len(stops)
        for cut in (share, left):                   # even cut, then the forward cascade takes the rest
            for dump in stops:
                if left <= 0:
                    break
                cap = supply.dump_capacity_at(r.state, dump.hex)[commodity]
                onhand = getattr(r.state.supply(dump.id), commodity.lower())
                qty = min(cut, left, cap - onhand)
                if qty > 0:
                    left -= qty
                    r.emit(EventKind.SUPPLY_ARRIVED, convoy.side, "SYSTEM",
                           {"supply_id": dump.id, "cargo": {commodity: qty},
                            "lane": convoy.lane, "convoy_id": convoy.id})


def _rail_station(r: _Run, convoy, stop):
    """The dump a stop unloads into, ESTABLISHING it where the train first sets freight down
    (54.11: "any hex can be used as a supply dump"). Born EMPTY -- the SUPPLY_ARRIVED that follows
    fills it -- so nothing is minted and conservation is untouched. base=False: a railway station in
    the desert is a field dump and evaporates like one (49.3), can be captured (32.13) and blown
    (54.14).

    Returns None -- the train runs through without stopping -- when the station's counter EXISTS BUT
    IS THE ENEMY'S. That is not a corner case, it is the war: the Axis overruns a station, 32.13
    hands him the dump, he moves on, and the hex is ours again by control while the counter is still
    his. Re-founding "AL-Rail-26.100" there would put a SECOND Supply Unit with the SAME ID on the
    map -- and state.supply() resolves an id to the first match while the conservation invariant sums
    ALL of them, so the duplicate double-counts and game.invariants fails loud (it did: AMMO on_hand
    ran 299 points over initial). You cannot unload into a dump the enemy owns; you must retake it."""
    if not isinstance(stop, tuple):
        return stop
    sid = _rail_dump_id(convoy.side, stop)
    if r.state.supply(sid) is not None:             # the enemy holds our station's counter
        return None
    r.emit(EventKind.SUPPLY_DUMP_ESTABLISHED, convoy.side, "SYSTEM",
           {"supply_id": sid, "side": convoy.side.value, "hex": list(stop)})
    return r.state.supply(sid)


def _naval_convoys(r: _Run, policies: dict | None = None) -> None:
    """Naval Convoy Arrival (rule 48 V.C.7 Tactical Shipping + V.D Convoy Arrival). Runs EVERY
    Operations Stage: the sequence of play repeats all facets of the First Operations Stage in
    the Second and Third (48 VI/VII), so the Naval Convoy Arrival Phase happens three times a
    Game-Turn, and a harbour's per-OpStage tonnage capacity (55.16) is exercised each time.

    The two halves are split by cadence, because they have different ones. A convoy is bombed at
    sea and either sails or is cancelled (56.15) ONCE per Game-Turn -- interdiction is a Strategic
    mission (39.13, flown once per turn) -- so _schedule_convoys builds each convoy's SURVIVED
    manifest at Stage 1 only. That manifest then UNLOADS across the turn's three Operations Stages
    (_unload_convoys), each stage capped by the harbour's current Efficiency Level: bombed down in
    one stage, regenerated in the next, so what gets through depends on the siege. Fires only when
    convoys are due this game-turn, so every convoy-less scenario stays byte-identical (no
    Phase.LOGISTICS beat). Port regeneration (55.18) is NOT here any more -- it is an end-of-OpStage
    step (engine.run calls _port_regen after both players' Combat Segments), because whether a port
    regenerates depends on whether it lost levels to bombs DURING the stage."""
    due = [c for c in r.state.convoys if c.arrival_turn == r.state.turn]
    if not due:
        return                                          # convoy-less stays byte-identical
    r.go(Phase.LOGISTICS, Side.SYSTEM)
    if r.state.stage == 1:                              # the once-per-turn gauntlet + 56.15 decision
        _schedule_convoys(r, due, policies)
    _unload_convoys(r, due)                             # 48 V.D: the Arrival Phase, this Operations Stage


def _schedule_convoys(r: _Run, due: list, policies: dict | None) -> None:
    """[48 III / 56.13] The once-per-Game-Turn convoy gauntlet, run at Stage 1: stage the naval
    seat's interdiction decision, run each convoy through the [41.66] bombing at sea (a Strategic
    mission, 39.13 flown once per turn), take the 56.15 sail/cancel decision, and record the
    SURVIVED manifest that _unload_convoys then lands across the turn's Operations Stages.

    `policies` (optional, None for scripted callers) hands the naval seat its interdiction
    allocation; a policy without a naval seat stages nothing, so the interdiction stays as ambient
    as before -- byte-identical."""
    r.convoy_manifest = {}
    if policies is not None:                            # the naval command loop (early-return-guarded)
        for side in (Side.AXIS, Side.ALLIED):
            pol = policies[side]
            if hasattr(pol, "naval_command"):
                pol.naval_command(r.state, side)        # stages the officer's interdiction beats
                _drain_staff(r, pol, side)              # emitted before the CONVOY_INTERDICTED below
    for c in sorted(due, key=lambda c: c.id):           # deterministic arrival order
        dump = _convoy_dest(r.state, c)                 # 56.15, plus the 54.3/60.7 retracting railhead
        if dump is None:
            r.emit(EventKind.CONVOY_CANCELLED, c.side, "SYSTEM",
                   {"convoy_id": c.id, "lane": c.lane, "dest": c.dest, "reason": "port captured"})
            r.convoy_manifest[c.id] = {"dest": None, "cargo": {}, "rail": False}
            continue
        # 41.6/32.66: skim the CRT loss at sea BEFORE landing (identity + no rng if unbombed)
        cargo, itd_order, pct_lost, tons_lost, itd_dice = _interdict(
            c, r.state, r.dice.stream("interdiction"))
        # [54.3] a RAILWAY delivery is not a ship: it lands its whole 54.32 haul along the line at
        # once (_rail_deliver / _rail_stops), so it is flagged to unload only in the turn's 1st stage.
        rail = bool(c.rail and r.state.terrain.rails)
        r.convoy_manifest[c.id] = {"dest": dump.id, "cargo": dict(cargo), "rail": rail}
        if itd_order is not None:                       # 41.6/32.66: the bombing marker beside arrival
            interdictor = _other(c.side)
            r.emit(EventKind.CONVOY_INTERDICTED, interdictor, "SYSTEM",
                   {"lane": c.lane, "convoy_id": c.id, "interdictor": interdictor.value,
                    "bomb_points": itd_order.bomb_points, "pct_lost": pct_lost,
                    "tons_lost": tons_lost}, rng_draws=itd_dice)   # 41.66: certify the CRT dice
            # Route the cut ALSO through a SEA-arena air strike so a convoy interdiction is legibly
            # air-sourced (41.6) -- but ONLY when the interdictor fields SEA air, so an air-less
            # interdiction scenario (siege_of_tobruk) stays byte-identical.
            if any(w.side == interdictor and w.arena == "SEA" for w in r.state.air):
                r.emit(EventKind.AIR_STRIKE_RESOLVED, interdictor, "SYSTEM",
                       {"arena": "SEA", "target": c.lane, "strength": itd_order.bomb_points,
                        "pinned": [], "loss": 0})


def _unload_convoys(r: _Run, due: list) -> None:
    """[48 V.D] The Naval Convoy Arrival Phase, run each Operations Stage: unload each due convoy's
    REMAINING manifest into its destination dump. A railway (54.3) lands its whole 54.32 haul along
    the line at once, in the turn's first stage. A SEA convoy unloads over the harbour quay, capped
    by the port's per-OpStage tonnage budget (55.16, ceil(cap_tons * eff/max_eff)); whatever will
    not fit this stage stays on the manifest for the next one, at the Efficiency Level the port
    then has -- bombed down or regenerated -- which is the whole siege duel. The un-landed remainder
    is not annihilated (the old code silently dropped it): it simply waits for a later stage or, at
    end of turn, expires unshipped (56.27, may not ship over capacity)."""
    port_landed: dict[tuple[str, str], int] = {}        # 55.14: per-commodity sub-cap, per-port-per-OpStage
    port_tons: dict[str, float] = {}                    # 55.3: the ONE shared tonnage budget per port per OpStage
    for c in sorted(due, key=lambda c: c.id):           # deterministic arrival order
        m = r.convoy_manifest.get(c.id)
        if m is None or m["dest"] is None or not any(v > 0 for v in m["cargo"].values()):
            continue                                    # cancelled, or manifest already exhausted
        cargo = m["cargo"]
        dump = r.state.supply(m["dest"])
        if m["rail"]:
            if r.state.stage == 1:                      # the railway lands its whole haul at once (54.3)
                _rail_deliver(r, c, dump, cargo)
                m["cargo"] = {k: 0 for k in cargo}      # delivered -- nothing carries to later stages
            continue
        cap = supply.dump_capacity_at(r.state, dump.hex)   # 54.12, by dump terrain + village overlay
        port = r.state.port_at(dump.hex)               # 56.28: the built-in harbour dump throttles a ship
        # (a) what each commodity WANTS to land this stage: 54.12 dump headroom, then the port's
        # SECONDARY per-commodity sub-cap (_UNLIMITED for campaign ports; convoys sharing a port
        # this OpStage subtract what earlier ones already landed).
        want: dict = {}
        for k, v in cargo.items():
            if v <= 0:
                continue
            onhand = getattr(dump, k.lower())
            room = min(cap[k], onhand + v) - onhand     # 54.12 dump headroom
            if port is not None:
                already = port_landed.get((port.id, k), 0)
                room = min(room, supply.port_landing_cap(port, k) - already)
            if room > 0:
                want[k] = room
        # (b) 55.3/55.14 THE SHARED TONNAGE THROTTLE. A port ships ONE total tonnage per OpStage
        # across ALL commodities (55.3: "the TOTAL tonnage of supplies... in one Operations Stage"),
        # NOT the whole allowance per commodity. When the manifest outweighs the remaining budget,
        # every commodity lands the same fraction of what it wanted -- mix-preserving and order-
        # independent (the rules let the player pick the split; proportional is the least-biased
        # reading of a fixed cargo, and it avoids a commodity-ordering artefact that would starve
        # one commodity to feed another). 54.5 crosses each Point to its tonnage.
        if port is not None and want:
            remaining = supply.port_tonnage_budget(port) - port_tons.get(port.id, 0.0)
            want_tons = sum(q * supply.TONS_PER_POINT[k] for k, q in want.items())
            if want_tons > remaining:
                frac = remaining / want_tons if want_tons > 0 else 0.0
                want = {k: math.floor(q * frac) for k, q in want.items()}
            port_tons[port.id] = port_tons.get(port.id, 0.0) + sum(
                q * supply.TONS_PER_POINT[k] for k, q in want.items())
        landed = {k: q for k, q in want.items() if q > 0}
        if port is not None:
            for k, q in landed.items():
                port_landed[(port.id, k)] = port_landed.get((port.id, k), 0) + q
            for k in sorted(landed):                    # legible per-commodity landing beat
                r.emit(EventKind.PORT_UNLOADED, c.side, "SYSTEM",
                       {"port_id": port.id, "commodity": k, "qty": landed[k],
                        "tons": supply.points_to_tons(landed[k], k), "eff": port.eff})
        if landed:                                      # nothing to land into a full dump
            r.emit(EventKind.SUPPLY_ARRIVED, c.side, "SYSTEM",   # dump.id == c.dest unless the railhead retracted
                   {"supply_id": dump.id, "cargo": landed, "lane": c.lane, "convoy_id": c.id})
            for k, q in landed.items():                 # 48 V.D: draw the manifest down as it lands
                cargo[k] = cargo[k] - q


def _port_regen(r: _Run) -> None:
    """55.18: at the end of an Operations Stage, every port that did NOT lose any Efficiency Levels
    to Enemy bombs this stage (r.ports_bombed_this_stage, populated by _air_port) regains one
    Level, up to its regeneration ceiling (max_eff - blocked; supply.regen_eff). A permanent
    harbour BLOCK (55.2 San Giorgio / 55.27 mine) holds the ceiling below max_eff -- it is not
    bomb damage and never regenerates (55.26) -- but bomb damage below the ceiling DOES recover, so
    the besieger must keep bombing to keep the harbour shut. Deterministic (sorted by id); fires no
    event for a port at its ceiling or bombed this stage, so a port-less or unbombed-at-ceiling
    scenario stays byte-identical."""
    for p in sorted(r.state.ports, key=lambda p: p.id):
        if p.id in r.ports_bombed_this_stage:           # 55.18: lost levels to bombs this stage -- no regen
            continue
        level = supply.regen_eff(p)
        if level is not None:
            r.emit(EventKind.PORT_EFFICIENCY_CHANGED, p.side, "SYSTEM",
                   {"port_id": p.id, "level": level})


def _models_full_logistics(state: GameState) -> bool:
    """True iff the scenario seeds Stores/Water anywhere -- the gate that keeps every
    ammo/fuel-only scenario byte-identical (no Stores/Water beat, no LOGISTICS phase)."""
    return bool(state.initial_supply.get(supply.STORES, 0)
                or state.initial_supply.get(supply.WATER, 0))


def _stores_setup(r: _Run) -> None:
    """Stores Expenditure Stage (rule 48 IV / 51), ONCE per GAME-TURN: the 6% base fuel/water
    evaporation (49.3, taken at the Stores stage) then both sides expend STORES (51) with the
    51.21/51.22 shortfall attrition and the 52.6 Pasta Point. Water is NOT here -- it is drawn
    per Operations Stage (_water_body). Fires only for full-logistics scenarios (an ammo/fuel-
    only scenario skips it entirely)."""
    if not _models_full_logistics(r.state):
        return
    r.go(Phase.LOGISTICS, Side.SYSTEM)
    _evaporate(r, _EVAP["base"])                    # 49.3: 6% base evaporation, once per game-turn
    for side in (Side.AXIS, Side.ALLIED):
        _stores_stage(r, side, r.state.weather == "hot")


def _water_body(r: _Run) -> None:
    """Water Distribution (rule 48 V.C.1 / 52), per OPERATIONS STAGE: the +5% hot-weather
    evaporation slice (49.3/29.34, tied to THIS stage's weather) then both sides draw WATER
    (52) with the 52.53 shortfall attrition. Fires only for full-logistics scenarios."""
    if not _models_full_logistics(r.state):
        return
    r.go(Phase.LOGISTICS, Side.SYSTEM)
    hot = r.state.weather == "hot"
    if hot:
        _evaporate(r, _EVAP["hot_additional"])      # 49.3: +5% as soon as hot weather is determined
    for side in (Side.AXIS, Side.ALLIED):
        _water_stage(r, side, hot)


def _logistics(r: _Run) -> None:
    """The combined Stores+Water logistics beat for ONE Operations Stage (rule 48 IV + V.C.1),
    charging the full 6%+5% evaporation at once. Retained as the single-call entry point the
    logistics unit tests exercise; run() drives the faithful SPLIT cadence via _stores_setup
    (Stores + 6% base, per game-turn) and _water_body (Water + 5% hot slice, per Operations
    Stage). Fires only for full-logistics scenarios (ammo/fuel-only stays byte-identical)."""
    if not _models_full_logistics(r.state):
        return
    r.go(Phase.LOGISTICS, Side.SYSTEM)
    hot = r.state.weather == "hot"
    _evaporate(r, _EVAP["base"] + (_EVAP["hot_additional"] if hot else 0))
    for side in (Side.AXIS, Side.ALLIED):
        _stores_stage(r, side, hot)
        _water_stage(r, side, hot)


def _stores_stage(r: _Run, side: Side, hot: bool) -> None:
    """A side's Stores Expenditure (rule 48 IV / 51, faithfully once per GAME-TURN): draw
    STORES IN THE HEX (51.15: "Stores must be present in the hex to be used"), with the 51.21
    disorganization + 51.22 attrition on a sustained shortfall, and the 52.6 Pasta Point."""
    _stores_expenditure(r, side, hot)


def _water_stage(r: _Run, side: Side, hot: bool) -> None:
    """A side's Water Distribution (rule 48 V.C.1 / 52, faithfully per OPERATIONS STAGE): draw
    WATER from the traced dumps, with the 52.53 shortfall attrition. The dual of _stores_stage."""
    _water_distribution(r, side, hot)


_EVAP = logistics_data.evaporation_percent()   # 49.3/52.44, from the rulebook


def _evaporate(r: _Run, pct: int) -> None:
    """49.3 / 52.44 / 29.34: on-map Fuel and Water lose `pct`% (rounded down) to evaporation &
    spillage -- in DUMPS and in TRUCK CONVOYS alike (29.34: the hot 5% "includes water and fuel in
    dumps as well as in trucks"; 49.3: fuel evaporates "regardless of where it is kept", only
    convoys AT SEA exempt, and those are state.convoys, not on-map trucks). A strategic city base
    (57) and wells/pipelines (base=True) are exempt (52.44). A SINK into consumed[] (the 9%
    Sep40-Aug41 Commonwealth container rate is deferred). The 6% base (once per game-turn) and the
    +5% hot slice (per Operations Stage) are charged as SEPARATE calls under the faithful clock.
    Deterministic: sorted dumps then sorted trucks, fuel then water."""
    if pct <= 0:
        return
    for sid in sorted(su.id for su in r.state.supplies):
        if r.state.supply(sid).base:                    # 49.3: a strategic city depot (57) doesn't evaporate
            continue
        for commodity in (supply.FUEL, supply.WATER):
            amt = getattr(r.state.supply(sid), commodity.lower())
            loss = amt * pct // 100
            if loss > 0:
                r.emit(EventKind.SUPPLY_EVAPORATED, Side.SYSTEM, "SYSTEM",
                       {"supply_id": sid, "commodity": commodity, "qty": loss})
    for tid in sorted(t.id for t in r.state.trucks):    # 29.34: "as well as in trucks"
        for commodity in (supply.FUEL, supply.WATER):
            amt = getattr(r.state.truck(tid), commodity.lower())
            loss = amt * pct // 100
            if loss > 0:
                r.emit(EventKind.TRUCK_EVAPORATED, Side.SYSTEM, "SYSTEM",
                       {"truck_id": tid, "commodity": commodity, "qty": loss})


def _stores_expenditure(r: _Run, side: Side, hot: bool) -> None:
    """Each living unit draws its 51.11/51.13 Stores requirement IN THE HEX (51.15: "Stores must be
    present in the hex to be used. Stores on truck convoys cannot be used until off-loaded"), NOT
    through the abstract 32.16 ½-CPA trace. Stores have no organic per-unit reservoir (unlike the
    49.14 fuel tank / 50.0 ammo load), so the draw comes wholly from a co-located dump -- in_hex_draw's
    own-pool branch (unit.stores) is always 0 here; the "unit" tag is handled only for symmetry with
    the fuel/ammo idiom and never fires until first-line trucks are activated to carry stores. A unit
    with no stores in its hex goes short (51.2)."""
    actor = f"{side.value}/Logistics"
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        if supply.is_air_facility(u):
            continue                                    # 35.14: air pieces draw air supply, not land
        draws = supply.in_hex_draw(r.state, u, supply.STORES, supply.stores_cost(u))
        if draws is None:
            _stores_shortfall(r, side, actor, u)        # 51.21/51.22
            continue
        for tag, ref_id, qty in draws:                  # 51.15: stores drawn from sources ON the hex
            if tag == "unit":                           # (no organic stores pool -- always "dump")
                r.emit(EventKind.UNIT_SUPPLY_CONSUMED, side, actor,
                       {"unit_id": ref_id, "commodity": supply.STORES, "qty": qty})
            else:                                       # a co-located dump (54.11/54.15)
                r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                       {"supply_id": ref_id, "commodity": supply.STORES, "qty": qty, "unit_id": u.id})
        if u.turns_without_stores > 0:                  # resupplied -> reset the consecutive count
            r.emit(EventKind.STORES_RESTORED, side, actor, {"unit_id": u.id})
        _pasta_point(r, side, actor, u)                 # 52.6: got stores -> needs its pasta water


# A unit only DISORGANIZES (a cohesion hit that feeds the 15.88/17 surrender path) once
# its Stores shortfall is SUSTAINED, not on a single turn out of trace -- the rules stress
# "consecutive" shortfall, and a unit briefly outrunning its stores while advancing must
# not have its morale collapse (which would unravel the whole combat trajectory). The
# Disorganization Point itself (51.21) still accrues every short turn in the counter.
DISORGANIZED_AFTER: int = 6        # consecutive short game-turns before cohesion bites


def _stores_shortfall(r: _Run, side: Side, actor: str, u) -> None:
    """A unit that cannot draw its Stores this game-turn (51.2). It earns a
    Disorganization Point every turn (51.21, accrued in the counter); once sustained
    (>= DISORGANIZED_AFTER consecutive turns) it disorganizes, routed through
    COHESION_CHANGED so it feeds the live 15.88/17 surrender. Every second consecutive
    short turn an INFANTRY unit sheds that turn's percentage of its TOE Strength Points
    (51.22: 2% at 2 turns, 4% at 4 ...) via STEP_LOST role='attrition'. Guns/tanks are
    exempt from the step loss (51.22)."""
    r.emit(EventKind.STORES_SHORTFALL, side, actor, {"unit_id": u.id})
    cur = r.state.unit(u.id)
    n = cur.turns_without_stores
    if n >= DISORGANIZED_AFTER:                          # 51.21 disorganization bites (sustained)
        r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -1})
    if supply.is_infantry(cur) and n >= 2 and n % 2 == 0:
        loss = round(n / 100 * cur.strength)            # 51.22 n% of TOE, nearest whole
        if loss > 0:
            r.emit(EventKind.STEP_LOST, side, actor,
                   {"unit_id": u.id, "amount": min(loss, cur.strength), "role": "attrition"})


def _pasta_point(r: _Run, side: Side, actor: str, u) -> None:
    """52.6 the Italian Pasta Rule: an Italian battalion, when it receives its Stores,
    must also receive one Water Point to cook its pasta. Denied it, the battalion may
    not voluntarily exceed its CPA that turn (a no-op in the CPA-bounded engine, flagged
    by the PASTA_DENIED marker), and if it is already shaky (Cohesion -10 or worse) it
    immediately disorganizes as if at -26 -- feeding the live 15.88/17 surrender path.
    Recovery on later receipt of the Pasta Point (52.6) is deferred, like all Cohesion
    recovery."""
    if not supply.is_italian(u) or not u.is_combat:
        return
    draws = supply.plan_draw(r.state, u, supply.WATER, 1)
    if draws is not None:
        for sid, qty in draws:
            r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                   {"supply_id": sid, "commodity": supply.WATER, "qty": qty, "unit_id": u.id})
        return
    r.emit(EventKind.PASTA_DENIED, side, actor, {"unit_id": u.id})
    if u.cohesion <= -10:
        r.emit(EventKind.COHESION_CHANGED, side, actor,
               {"unit_id": u.id, "delta": -26 - u.cohesion})


def _water_distribution(r: _Run, side: Side, hot: bool) -> None:
    actor = f"{side.value}/Logistics"
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        if supply.is_air_facility(u):
            continue                                    # 35.14: air pieces draw air supply, not land
        draws = supply.plan_draw(r.state, u, supply.WATER, supply.water_cost(u, hot=hot))
        if draws is None:
            _water_shortfall(r, side, actor, u)         # 52.53
            continue
        for sid, qty in draws:
            r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                   {"supply_id": sid, "commodity": supply.WATER, "qty": qty, "unit_id": u.id})
        if u.stages_without_water > 0:                  # resupplied -> reset the consecutive count
            r.emit(EventKind.WATER_RESTORED, side, actor, {"unit_id": u.id})


def _water_shortfall(r: _Run, side: Side, actor: str, u) -> None:
    """A unit deprived of Water this Operations Stage (52.5). For every consecutive stage
    AFTER the first, an INFANTRY unit loses one TOE Strength Point (52.53), via the
    existing STEP_LOST role='attrition'. (Vehicles-can't-move / defend-at-half, 52.51-52,
    are deferred; the attrition is the load-bearing degradation.)"""
    r.emit(EventKind.WATER_SHORTFALL, side, actor, {"unit_id": u.id})
    cur = r.state.unit(u.id)
    if supply.is_infantry(cur) and cur.stages_without_water >= 2:    # after the first stage
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": u.id, "amount": min(1, cur.strength), "role": "attrition"})


def _waterless(u) -> bool:
    """A unit deprived of Water this Operations Stage (rule 52.5). The stage-start Water Distribution
    (52.4, _water_body) increments stages_without_water on a shortfall and resets it on resupply, so a
    positive count at movement/combat time -- both run AFTER the water beat -- means 'dry this stage',
    the trigger for the 52.51/52.52 effects (immobilised vehicle / no offensive assault / half defence).
    Zero for every ammo/fuel-only scenario (no water beat runs), so those stay byte-identical."""
    return u.stages_without_water > 0


def _def_raw(u) -> int:
    """A defender's raw defensive close-assault strength for the 15.79 differential -- HALVED if it is
    out of water this stage (52.51 vehicles "halve their total raw strength before determining actual
    strength"; 52.52 infantry "defend at half strength"). The casualty pool (defender_loss_raw) keeps
    the full TOE; only the defensive rating that sets the differential is halved."""
    return u.raw_defense // 2 if _waterless(u) else u.raw_defense


def _weather(r: _Run) -> None:
    """Weather Determination (rule 29.1): the season (from the Game-Turn) selects the 29.61
    Weather Table row; a sequential 2d6 gives the theatre-wide weather TYPE. Normal and Hot
    fall on every section (29.2 / 29.31), so their couplings read the scalar `weather`. A foul
    result (Sandstorm/Rainstorm) rolls one more die on the 29.7 Foul Weather Location Table and
    lands on only 2-3 sections of the theatre (29.41 keeps a sandstorm off the delta); the rest
    read Normal, and if the storm misses the theatre entirely the stage is Normal everywhere
    (29.1). The covered sections ride GameState.storm_sections, which weather_at localises per
    hex. A scenario with no section geometry (empty map_sections) keeps the pre-localisation
    theatre-wide behaviour, byte-identical."""
    season = weather.season_for_turn(r.state.turn + r.state.season_offset)
    d1, d2 = r.d6("weather"), r.d6("weather")
    label = weather.weather_for_roll(season, d1 * 10 + d2)
    draws = (d1, d2)
    storm: frozenset = frozenset()
    if weather.is_foul(label):
        d3 = r.d6("weather")
        draws = (d1, d2, d3)
        theater = r.state.map_sections
        if theater:
            storm = weather.affected_sections(label, d3, theater)   # 29.7 within theatre, less delta
            if not storm:                                           # 29.1: the storm missed the theatre
                label = weather.NORMAL
        else:                                                       # no section geometry -> theatre-wide
            storm = weather.foul_sections(d3)
    r.emit(EventKind.WEATHER_ROLLED, Side.SYSTEM, "SYSTEM",
           {"weather": label, "season": season, "sections": sorted(storm)},
           rng_draws=draws)


def _well_refill(r: _Run) -> None:
    """29.53 / 52.15: a Rainstorm refills every DEPLETED well in the sections it covers -- "all
    depleted wells on a game-map section with a rainstorm are automatically replenished at the
    instant the rainstorm occurs." A well is finite (depletable) only at a village or bir
    (game.wells sets water_capacity); the unlimited major-city/oasis wells never deplete (52.13),
    so they carry no capacity and are skipped. The refill is a FAUCET -- rain introduces water --
    so it rides WELL_REFILLED (the dual of SUPPLY_ARRIVED, raising initial_supply) and conservation
    holds. Fires only on a Rainstorm, so every other OpStage is byte-identical. Deterministic:
    sorted wells."""
    if r.state.weather != weather.RAINSTORM:
        return
    for su in sorted(r.state.supplies, key=lambda s: s.id):
        if su.water_capacity <= 0 or su.water >= su.water_capacity:    # not a finite well, or full
            continue
        if r.state.weather_at(su.hex) != weather.RAINSTORM:            # 52.15: only wells under the storm
            continue
        r.emit(EventKind.WELL_REFILLED, Side.SYSTEM, "SYSTEM",
               {"supply_id": su.id, "commodity": supply.WATER,
                "qty": su.water_capacity - su.water})


def _air_grounded(weather_label: str) -> bool:
    """29.43 / 29.52: no aircraft fly into or out of a sandstorm or rainstorm hex. Read off the
    same whole-map weather label _field_repair_blocked uses -- when the sky is foul, no air beat
    fires (no superiority contest, no missions), so a grounded OpStage stays byte-identical."""
    return weather_label in ("sandstorm", "rainstorm")


def _air_arena_fighters(state: GameState, arena: str) -> tuple[int, int]:
    """(axis_fighters, allied_fighters) committed to `arena` this OpStage."""
    axis = sum(w.fighters for w in state.air if w.arena == arena and w.side == Side.AXIS)
    allied = sum(w.fighters for w in state.air if w.arena == arena and w.side == Side.ALLIED)
    return axis, allied


def _air_superiority(r: _Run) -> None:
    """The air-superiority establishing shot (rules 40/45/46), once per OPERATIONS STAGE: for
    each arena a side fields air in, both sides add a die to their committed fighter Air Points
    and the higher total holds the sky for the stage (40.27/46 interception + flak collapsed into
    the one roll). The victor folds into air_superiority[arena]; the loser's strike/recon is scaled
    down at mission time (AIR_SUPERIORITY_LOSER_SCALE). The establishing contest is fought per ARENA
    (34/40), which owns no hex, so it reads the theatre-wide 29.1 type -- a documented hexless proxy:
    a storm anywhere disrupts the sky. The load-bearing per-hex 29.43/29.52 grounding is on the
    MISSIONS (_air_support, per the 29.7 section each flies over). Air-less OpStage stays byte-identical."""
    if not r.state.air or _air_grounded(r.state.weather):
        return
    r.go(Phase.LOGISTICS, Side.SYSTEM)                   # a SYSTEM housekeeping beat, like convoys
    for arena in sorted({w.arena for w in r.state.air}):
        axis_f, allied_f = _air_arena_fighters(r.state, arena)
        ad, ld = r.d6("air_superiority"), r.d6("air_superiority")
        axis_total, allied_total = axis_f + ad, allied_f + ld
        if axis_total > allied_total:
            victor, margin = Side.AXIS.value, axis_total - allied_total
        elif allied_total > axis_total:
            victor, margin = Side.ALLIED.value, allied_total - axis_total
        else:
            victor, margin = None, 0                     # a contested sky, nobody scaled
        r.emit(EventKind.AIR_SUPERIORITY_RESOLVED, Side.SYSTEM, "SYSTEM",
               {"arena": arena, "axis_fighters": axis_f, "allied_fighters": allied_f,
                "victor": victor, "margin": margin}, rng_draws=(ad, ld))


def _air_points(state: GameState, side: Side, arena: str, role: str) -> int:
    """Committed Air Points of `role` ("strike"|"recon") `side` can put over `arena` this OpStage,
    after the superiority gate scales the LOSER down (AIR_SUPERIORITY_LOSER_SCALE) -- the winner
    (or a contested sky) flies at full strength. The mission-time read of the Step-3 gate."""
    victor = state.air_superiority.get(arena)
    scale = 1.0 if victor is None or victor == side.value else AIR_SUPERIORITY_LOSER_SCALE
    total = sum(getattr(w, role) for w in state.air if w.side == side and w.arena == arena)
    return int(total * scale)


def _mission_hex(state: GameState, m) -> "Coord | None":
    """The map hex an air mission flies over, for the 29.43/29.52 per-section grounding check. A
    strike/fort/recon mission carries a Coord target; a Port mission carries a port_id, so read the
    harbour's hex. None when the port is unknown -- weather_at then falls back to theatre-wide."""
    if m.kind == "port":
        port = state.port(m.target)
        return port.hex if port is not None else None
    return tuple(m.target)


def _air_support(r: _Run, side: Side, pinned: set[str]) -> None:
    """The LAND air-support sub-segment (rules 41.31/41.37/41.39B/42.2) at the TOP of the phasing
    side's Combat Segment, before _barrage_step. Flies `side`'s due LAND air missions in a fixed,
    deterministic order. STRIKE pins the strongest enemy in the target hex (12.44, joining the same
    `pinned` set the barrage feeds) -- UN-STRIKABLE behind an intact Major-City wall (fort_level>1,
    41.31); FORT bombing batters a wall one level/OpStage (reusing FORT_REDUCED); PORT bombing knocks
    a harbour's Efficiency Level down one (reusing PORT_EFFICIENCY_CHANGED, 41.39B); RECON lifts the
    fog over a hex (42.2). Each mission is grounded when its OWN target hex lies under a Sandstorm/
    Rainstorm (29.43/29.52, keyed on the 29.7 section it flies over), so a storm confined to 2-3
    sections no longer grounds the whole air force; an air-less segment stays byte-identical."""
    if not r.state.air:
        return
    due = [m for m in r.state.air_missions if m.side == side and m.turn == r.state.turn]
    for m in sorted(due, key=lambda m: (m.kind, str(m.target))):
        if _air_grounded(r.state.weather_at(_mission_hex(r.state, m))):   # 29.43/29.52, per section
            continue
        if m.kind == "strike":
            _air_strike(r, side, tuple(m.target), pinned)
        elif m.kind == "fort":
            _air_fort(r, side, tuple(m.target))
        elif m.kind == "port":
            _air_port(r, side, m.target)
        elif m.kind == "recon":
            _air_recon(r, side, tuple(m.target))


def _air_strike(r: _Run, side: Side, tgt: Coord, pinned: set[str]) -> None:
    """41.31 B-CU: the committed strike Air Points pin the strongest enemy combat unit in the hex
    (blind assignment, 39.11) -- but a Major-City garrison is UN-STRIKABLE behind an intact wall
    (fort_level>1), the exact siege mirror, so air alone cannot crack Tobruk. Any step-loss rides
    STEP_LOST(role='air_strike') behind the AIR_STRIKE_STEP_SEVERITY dial (default 0 -> pin-only)."""
    strength = _air_points(r.state, side, "LAND", "strike")
    walled = r.state.fort_level(tgt) > 1                 # 41.31: intact Major-City wall shields it
    victim = None if walled else _barrage_target(r.state.enemies_at(tgt, side))
    actor = f"{side.value}/Air"
    pin_ids: list[str] = []
    loss = 0
    if victim is not None and strength > 0:
        pin_ids = [victim.id]
        loss = min(AIR_STRIKE_STEP_SEVERITY, victim.strength)
    r.emit(EventKind.AIR_STRIKE_RESOLVED, side, actor,
           {"arena": "LAND", "target": list(tgt), "strength": strength,
            "pinned": pin_ids, "loss": loss, "walled": walled})
    if loss > 0:
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": victim.id, "amount": loss, "role": "air_strike"})
    for uid in pin_ids:                                  # 12.44: joins the barrage pin set
        pinned.add(uid)


def _air_fort(r: _Run, side: Side, tgt: Coord) -> None:
    """41.37 B-F/C: air batters a fortification one level per Operations Stage -- the air twin of
    engine._batter_fort, gated behind siege_rules (inert in the canonical benchmark). Reuses
    FORT_REDUCED, so no new fold; air + barrage together open the works faster. Like _air_strike,
    it needs committed LAND strike Air Points (scaled by the superiority gate): a side that fields
    no strike or has lost the sky to a scale of 0 cannot batter the works -- winning the LAND sky
    is the precondition. The committed strength rides the payload for legibility."""
    strength = _air_points(r.state, side, "LAND", "strike")
    if strength <= 0:                                    # no committed strike / lost the sky
        return
    if not r.state.siege_rules or r.state.fort_level(tgt) <= 0:
        return
    if r.state.control_of(tgt) == CONTROL_OF[side]:      # never batter your OWN works
        return
    r.emit(EventKind.FORT_REDUCED, side, f"{side.value}/Air",
           {"hex": list(tgt), "level": r.state.fort_level(tgt) - 1, "strength": strength})


def _air_port(r: _Run, side: Side, port_id: str) -> None:
    """[41.39B / 41.5] B-P Bombing Ports: harbour bombing ROLLS on the [41.5] Air Bombardment CRT's
    Ports row (logistics_data.air_port_bombing_crt_41_5) for the number of Efficiency Levels the port
    loses (55.1). The committed strike Air Points pick the Bomb-Point column; 2d6 read sequentially
    (41.22) give the result. At the campaign's six proxy strike points that is a 0 on 32 of 36 codes
    and a 1 on 4 -- so most stages the quay takes no damage, and (because a 0 leaves the port unmarked)
    55.18 lets it regenerate. The besieger must roll well, and keep rolling, to hold the harbour shut;
    the holder is fed by sea between the bombs. That -- not a one-way ratchet where one bomb shuts the
    quay for good -- is the siege duel.

    Needs committed LAND strike Air Points scaled by the superiority gate: a side that fields no strike
    or has lost the sky to a scale of 0 cannot bomb the harbour. And it never bombs its OWN harbour --
    the Port serves whoever HOLDS the hex (56.15 gates the convoy lane the same way), so the game-turn
    the fortress changes hands, besieger and besieged swap. Falls back to the seeded side on a hex
    neither player has entered, so a scenario that records no control there reads as before."""
    strength = _air_points(r.state, side, "LAND", "strike")
    if strength <= 0:                                    # no committed strike / lost the sky
        return
    port = r.state.port(port_id)
    if port is None or port.eff <= 0:
        return
    holder = r.state.control_of(port.hex)
    if holder == CONTROL_OF[side] or (holder == Control.NEUTRAL and port.side == side):
        return                                           # never bomb your OWN harbour
    d1, d2 = r.d6("air_bombard"), r.d6("air_bombard")    # 41.22: two dice, read sequentially
    levels = min(_port_bomb_levels(strength, d1, d2), port.eff)
    new_eff = port.eff - levels
    r.emit(EventKind.AIR_STRIKE_RESOLVED, side, f"{side.value}/Air",   # certify the [41.5] CRT dice
           {"arena": "PORT", "target": port.id, "strength": strength,
            "levels": levels, "eff": new_eff}, rng_draws=(d1, d2))
    if levels > 0:                                        # a No-Effect (0) leaves the port free to regen
        r.ports_bombed_this_stage.add(port.id)           # 55.18: lost levels to bombs this stage
        r.emit(EventKind.PORT_EFFICIENCY_CHANGED, side, f"{side.value}/Air",
               {"port_id": port.id, "level": new_eff, "strength": strength})


def _air_recon(r: _Run, side: Side, tgt: Coord) -> None:
    """42.2 recon: reveal the target hex's unit TYPES + TOE (+-2 noise, 42.24), FORBIDDEN over a
    Major City (42.22, fort_level>1). The hex folds into the per-OpStage air_sighted set (the
    fog-lift observation reads); the typed detail rides in `revealed`, bounded to 'even less detail
    than Patrol' (3.6) -- unit CLASS, never id. The +-2 noise is baked here (rng), so apply stays pure."""
    if r.state.fort_level(tgt) > 1:                      # 42.22: no recon over a Major City
        return
    enemies = sorted(r.state.enemies_at(tgt, side), key=lambda u: u.id)
    revealed: list[dict] = []
    draws: list[int] = []
    for e in enemies:
        offset = r.dice.stream("recon").randint(-2, 2)   # 42.24: TOE +-2 (not a d6)
        draws.append(offset)
        revealed.append({"class": _barrage_class(e), "toe": max(0, e.strength + offset)})
    r.emit(EventKind.AIR_RECON_RESOLVED, side, f"{side.value}/Air",
           {"arena": "LAND", "hex": list(tgt), "revealed": revealed}, rng_draws=tuple(draws))


def _naval_target(state: GameState, side: Side, ship) -> "tuple | None":
    """The single hex `ship` bombards this OpStage (rule 30.24, once per ship): its OWN hex at
    full Gun Rating if an enemy combat unit stands there, else -- for a capital ship only (30.21)
    -- the nearest adjacent enemy hex at HALF Gun Rating. Returns (target_hex, victim, actual_pts)
    or None. Deterministic: adjacent hexes are scanned in sorted-coord order (blind assignment,
    39.11), so the fire plan is replay-stable."""
    own = _barrage_target(state.enemies_at(ship.hex, side))
    if own is not None:
        return ship.hex, own, ship.gun_rating
    if ship.kind in CAPITAL_SHIP_KINDS:                  # 30.21: reach one hex further, at half
        for nb in sorted(neighbors(ship.hex)):
            victim = _barrage_target(state.enemies_at(nb, side))
            if victim is not None:
                return nb, victim, ship.gun_rating // 2
    return None


def _naval_bombardment(r: _Run, side: Side, pinned: set[str]) -> None:
    """Commonwealth off-shore naval bombardment (rule 30.2), a fire-support beat at the TOP of the
    phasing side's Combat Segment -- beside air support, before barrage. Each of `side`'s READY
    ships (port_cooldown 0) fires ONCE this OpStage (30.24): its Gun Rating goes in as Actual
    Barrage Points -- NO ammo draw (30.22) -- on the 12.6 CRT, a Pin joining the same 12.44
    `pinned` set the barrage feeds and any step-loss riding STEP_LOST(role='naval'). A capital ship
    reaches one hex further at half Gun Rating (30.21). A ship that fires then owes two Operations
    Stages refitting in Alexandria (30.25, the port_cooldown counter). Fires ONLY when `side`
    fields naval (GameState.naval=() -> byte-identical); ship damage/repair (30.3) and the Chariot
    raid (30.4) are deferred. As the mirror-completeness camera it is off the crackability path --
    it never batters a fort, so no siege lever rides here."""
    if not r.state.naval:
        return
    state0 = r.state
    for ship in state0.naval:
        if ship.side != side or ship.port_cooldown > 0:  # 30.25: still refitting in Alexandria
            continue
        aim = _naval_target(state0, side, ship)
        if aim is None:
            continue
        tgt, victim, actual = aim
        cls = _barrage_class(victim)
        d1, d2 = r.d6("naval_bombardment"), r.d6("naval_bombardment")
        shift = combat_tables.barrage_terrain_shift(     # 12.33 terrain / fortification
            state0.terrain.terrain[tgt], state0.fort_level(tgt), cls)
        pin, loss = combat_tables.barrage_result(cls, actual, d1 * 10 + d2, column_shift=shift)
        actor = f"{side.value}/Fleet"
        r.emit(EventKind.NAVAL_BOMBARDMENT, side, actor,
               {"ship_id": ship.id, "target": list(tgt), "actual": actual,
                "target_class": cls, "target_unit": victim.id, "pinned": pin, "loss": loss,
                "half": tgt != ship.hex}, rng_draws=(d1, d2))
        if loss > 0:
            tu = r.state.unit(victim.id)
            if tu and tu.alive:
                r.emit(EventKind.STEP_LOST, side, actor,
                       {"unit_id": victim.id, "amount": min(loss, tu.strength), "role": "naval"})
        if pin:
            pinned.add(victim.id)


def _drain_staff(r: _Run, policy, side: Side) -> None:
    """Optional hook (hasattr, symmetric with debrief/declare_ab): a command-staff
    policy accumulates cleaned STAFF_* artifacts during deliberation and exposes them
    here; the engine emits each just BEFORE the orders it explains. STAFF_* fold as
    no-ops, so this is board- and dice-invariant -- the war diary rides the same log."""
    if not hasattr(policy, "drain_staff"):
        return
    for kind, payload in policy.drain_staff():
        seat = payload.get("seat", "Staff")
        r.emit(kind, side, f"{side.value}/{seat}", clean_staff_payload(kind, payload))


# The never-bind Continual-Movement guardrail (rule 8.2). The real terminators are the CP
# ceiling (tactics._cp_ceiling), the 6.21 cohesion bleed, the monotone-toward-objective proposer
# and the 8.23 two-hex freeze; this cap only stops a pathological non-terminating policy.
MAX_CONTINUAL_SEGMENTS: int = 20

# 8.53b Reaction pin (adopted conservative read): a phasing mover whose effective CPA outstrips
# the reactor's by this margin may not be reacted to -- a stand-in for the unknowable "announces a
# Close Assault" clause, which the engine cannot see because movement precedes combat orders.
REACTION_CPA_GAP: int = 6


def _draw_move_fuel(r: _Run, side: Side, actor: str, u, cp_spent: float,
                    order: MoveOrder, *, order_kind: str = "move",
                    reason: str = "out of supply: no fuel for this move") -> bool:
    """49.13/49.16: a unit draws fuel for EVERY move -- rate x ceil(CP/5) of that move's path
    cost -- in the hex it begins from. Per-move, NOT once-per-OpStage: a unit that moves again in
    the stage draws again (49.16), a unit already charged COMBAT CP still pays to move (6.3 CP
    folds into cp_used but is not movement, 49.13), and a one-hex hop no longer buys a free long
    dash later.

    THE FUEL SWITCH (Phase 4, S5): fuel is drawn IN THE HEX (supply.in_hex_draw) -- the unit's own
    49.14 tank first, then a co-located dump -- NOT via the abstract 32.16 half-CPA trace, which was
    the ABSTRACT game running in the full game (distance cost nothing). There is no supply range now:
    a unit that has spent its tank and stands on no dump has OUTRUN its fuel and cannot move (49.15),
    which is the cost of distance. Emits UNIT_SUPPLY_CONSUMED off its own tank / SUPPLY_CONSUMED off a
    co-located dump and returns True; emits ORDER_REJECTED and returns False when the hex cannot cover
    the move."""
    draws = supply.in_hex_draw(r.state, u, supply.FUEL, supply.fuel_cost(u, cp_spent))
    if draws is None:
        _reject(r, side, actor, order, reason, order_kind=order_kind)
        return False
    for tag, ref_id, qty in draws:
        if tag == "unit":
            r.emit(EventKind.UNIT_SUPPLY_CONSUMED, side, actor,
                   {"unit_id": ref_id, "commodity": supply.FUEL, "qty": qty})
        else:                                          # "dump" -- a co-located dump (54.11/54.15)
            r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                   {"supply_id": ref_id, "commodity": supply.FUEL, "qty": qty, "unit_id": u.id})
    return True


def _supply_distribution(r: _Run, side: Side) -> None:
    """The Supply Distribution Segment (48 V.C.6): before it moves, each of the side's on-map units
    tops its own supply pools back up from a dump ON ITS HEX, at 0 CP (the 53.24 Organization-Phase
    exception). A conserving dump->unit transfer (UNIT_REFILLED) -- the dual of loading a truck. It
    draws ONLY from a co-located dump, so a unit that has outrun the dump network refills nothing:
    that is how distance costs supply (49.15). An automatic quartermaster default -- 48 V.C.6 says
    supplies "may" be redistributed, and "top every co-located unit to full" is the faithful greedy
    reading, so no policy order is needed (flagged as a policy simplification: a live staff could
    choose partial fills).

    FUEL and AMMO: the 49.14 tank (a full move) and the 50.0 basic load (one firing) are the two
    intrinsic pools seeded and consumed so far (S5/S6); each refills to its own capacity from a
    co-located dump. Stores/water (S7/S8) join when their consumers switch. First-line trucks (fl_*)
    stay dormant here exactly as in the draw -- truck-borne headroom is a separate later slice -- so a
    unit tops up only to its intrinsic capacity. Ordered FUEL-then-AMMO per unit for a deterministic
    log; a unit whose pools are already full (the GT1 case -- every pool seeded to capacity) yields no
    deficit and emits nothing."""
    caps = ((supply.FUEL, supply.fuel_capacity), (supply.AMMO, supply.ammo_capacity))
    for u in r.state.living(side):
        for commodity, capacity in caps:
            attr = commodity.lower()
            need = capacity(u) - getattr(u, attr)
            if need <= 0:
                continue
            dumps = sorted((s for s in r.state.active_supplies(side)
                            if s.hex == u.hex and getattr(s, attr) > 0), key=lambda s: s.id)
            for su in dumps:
                if need <= 0:
                    break
                take = min(need, getattr(su, attr))
                r.emit(EventKind.UNIT_REFILLED, side, f"{side.value}/QM",
                       {"unit_id": u.id, "supply_id": su.id, "commodity": commodity, "qty": take})
                need -= take


def _movement(r: _Run, policies: dict, side: Side, eligible: frozenset | None = None) -> None:
    """Voluntary Movement (rule 8) for the phasing `side`. Segment 0 (eligible is None) moves the
    whole roster; a Continual-Movement pulse (eligible = the 8.23-eligible unit ids) moves only
    those. Takes the FULL policies dict (parallel to _combat) so later interrupts can reach the
    NON-phasing policy -- the phasing orders still come from policies[side].movement, filtered by
    `eligible`, so segment 0 is a pure refactor of the pre-exploitation loop.

    Fuel: EVERY move draws fuel for its own path cost (49.13/49.16, via _draw_move_fuel) -- there
    is no free first-or-subsequent move, so Continual Movement is not fuel-free after pulse 0 and a
    unit already charged COMBAT CP at the front still pays to move. Keeps the desert supply scarcity
    biting through an exploitation."""
    policy = policies[side]
    actor = f"{side.value}/Front"
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(r.state, side)
    roster = r.state.living(side)          # phase-start snapshot (matches the observation)
    orders = policy.movement(r.state, side)
    _drain_staff(r, policy, side)          # the deliberation that produced these orders
    for order in orders:
        u = r.state.unit(order.unit_id)
        if u is None or not u.alive or u.side != side:
            _reject(r, side, actor, order, "no such living unit under this command")
            continue
        if u.cohesion <= -26:                           # 6.26: a unit at Cohesion -26 or worse may
            _reject(r, side, actor, order,              # not move (nor attack, nor defend). The
                    "Cohesion -26 or worse: may not move (6.26)")   # surrender-on-enemy-adjacency
            continue                                    # half of 6.26 is deferred -- flagged.
        if eligible is not None and u.id not in eligible:
            _reject(r, side, actor, order,
                    "not eligible for continual movement (8.23 two-hex gate)")
            continue
        if u.reserve == 2:                              # 18.22: Reserve II never moves
            _reject(r, side, actor, order, "Reserve II units may not move (18.22)")
            continue
        if u.id in r.building:                          # 24.12 / 48 V.C.4.b: a unit booked on a
            _reject(r, side, actor, order,              # construction project this Operations Stage
                    "involved in construction: may not move or spend CP this OpStage (24.12)")
            continue
        if u.engineer and r.state.control_of(order.to) == CONTROL_OF[_other(side)]:
            _reject(r, side, actor, order,              # 23.11: "Engineer units may never enter
                    "an engineer may not voluntarily enter an enemy-controlled hex (23.11)")
            continue                                    # Enemy-controlled hexes voluntarily"
        if u.effective_strength == 0:                   # 21.44: all vehicles broken down
            _reject(r, side, actor, order, "all vehicles broken down, may not move (21.44)")
            continue
        if supply._is_vehicle_type(u) and _waterless(u):   # 52.51: a vehicle out of water may not move
            _reject(r, side, actor, order,
                    "out of water this Operations Stage: vehicles may not move (52.51)")
            continue
        if u.reserve == 1:                              # 18.22: Reserve I -- one hex, CP-free
            _reserve_shuffle(r, side, actor, order, u, enemy_zoc, enemy_occupied)
            continue
        # Reachability is computed against the phase-start roster so a unit's legal
        # set doesn't depend on the order earlier units moved (matches observe()).
        reach, prev = tactics.reachable_for_prev(r.state, u, enemy_zoc, enemy_occupied, roster)
        if order.to == u.hex or order.to not in reach:
            _reject(r, side, actor, order,
                    "destination unreachable within CPA or blocked by ZOC")
            continue
        present = [x for x in r.state.units_at(order.to) if x.side == side]
        if not stacking.within_hex_limit(present + [u], r.state.terrain.terrain[order.to]):
            _reject(r, side, actor, order, "destination over stacking limit")
            continue
        if r.state.enemies_at(order.to, side):          # 8.5 re-entrancy: a reactor may have slid
            _reject(r, side, actor, order,              # into this hex AFTER the phase-start snapshot
                    "destination now occupied by an enemy unit (reaction 8.5)")
            continue
        if not _draw_move_fuel(r, side, actor, u, reach[order.to], order):
            continue                                # 49.13/49.16: this move draws its own fuel
        payload = {"unit_id": u.id, "from": list(u.hex), "to": list(order.to),
                   "cp_spent": reach[order.to]}
        bp = tactics.bp_for_move(r.state, u, prev, order.to)     # 21.21 accrual (0 for non-vehicles)
        if bp:
            payload["bp"] = bp
        old_cp = r.state.unit(u.id).cp_used
        r.emit(EventKind.UNIT_MOVED, side, actor, payload)
        _disorganize_overage(r, side, actor, u.id, old_cp,        # 6.21: overrun past CPA (8.16/8.17)
                             old_cp + reach[order.to], tactics.effective_cpa(r.state, u))
        _react(r, policies, side, u.id)         # 8.5: the non-phasing side may slide aside


def _react(r: _Run, policies: dict, phasing: Side, mover_id: str) -> None:
    """Reaction Movement (rule 8.5) -- the non-phasing tempo interrupt, the RBA template (13.0)
    relocated into the Movement Segment. When phasing unit `mover_id` has just moved, the NON-
    phasing side may slide eligible motorized units aside. 8.53 eligibility, read off the CURRENT
    board: (a) motorized only; (c) not already in the phasing side's ZOC; (d) not Engaged (15.81);
    (b) not pinned by a far heavier mover (effective CPA gap >= 6, the adopted conservative read of
    8.53b); plus the 8.54 size-pin (a reactor at least half the mover's stacking size). Validated
    against tactics.reachable_for PLAIN (8.55: no distance cap beyond CP -- NOT the 13.24 RBA cap);
    the reactor pays its per-move fuel (49.13) and REACTION_MOVED folds like UNIT_MOVED. (8.52 exempts the
    2-CP break-off surcharge; here the reactor is in the trigger mover's fresh ZOC so reachable_for
    charges it -- a small CONSERVATIVE overcharge consistent with the RBA sibling, flagged.)

    RE-ENTRANCY: the reactor's board change lands only on the NEXT pulse's fresh recompute -- the
    phasing movers still in this segment keep the frozen phase-start enemy_zoc snapshot in
    _movement, and REACTION_MOVED itself never triggers a further reaction, so there is no interrupt
    recursion. Inert (no event, no RNG) when no eligible reactor is adjacent or the policy declines,
    so every current scenario stays byte-identical."""
    reacting = _other(phasing)
    mover = r.state.unit(mover_id)
    if mover is None or not mover.alive:
        return
    adj = [u for u in r.state.living(reacting)          # cheap adjacency pre-filter (8.51 + 8.53a/d)
           if u.is_combat and is_motorized(u.mobility) and not u.engaged   # 8.53a: EVERY motorized class
           and is_adjacent(u.hex, mover.hex)]
    if not adj:
        return                                          # the common case -- no reaction possible
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(r.state, reacting)  # full board (8.55 reach)
    other_zoc = tactics.enemy_zoc_excluding(r.state, reacting, mover_id)   # 8.53c excludes the trigger mover
    mover_cpa = tactics.effective_cpa(r.state, mover)
    eligible = [u.id for u in sorted(adj, key=lambda u: u.id)
                if u.hex not in other_zoc                                    # 8.53c (no pre-existing pin)
                and mover_cpa - tactics.effective_cpa(r.state, u) < REACTION_CPA_GAP  # 8.53b
                and u.stacking_points * 2 >= mover.stacking_points]         # 8.54 size-pin
    if not eligible:
        return
    eligible_fs = frozenset(eligible)
    orders = policies[reacting].react_to(r.state, reacting, mover_id, eligible_fs)
    if not orders:
        return                                          # base [] declines -> byte-identical
    actor = f"{reacting.value}/Front"
    roster = r.state.living(reacting)
    for order in orders:
        u = r.state.unit(order.unit_id)
        if u is None or not u.alive or u.side != reacting or u.id not in eligible_fs:
            _reject(r, reacting, actor, order, "not an eligible reactor (8.53)",
                    order_kind="reaction")
            continue
        if supply._is_vehicle_type(u) and _waterless(u):    # 52.51: a dry vehicle may not move (8.5 too)
            _reject(r, reacting, actor, order,
                    "out of water this Operations Stage: vehicles may not move (52.51)",
                    order_kind="reaction")
            continue
        reach, prev = tactics.reachable_for_prev(r.state, u, enemy_zoc, enemy_occupied, roster)
        if order.to == u.hex or order.to not in reach:  # 8.55: plain reach, NO 13.24 cap
            _reject(r, reacting, actor, order,
                    "reaction destination unreachable within CPA or blocked by ZOC",
                    order_kind="reaction")
            continue
        present = [x for x in r.state.units_at(order.to) if x.side == reacting]
        if not stacking.within_hex_limit(present + [u], r.state.terrain.terrain[order.to]):
            _reject(r, reacting, actor, order, "reaction destination over stacking limit",
                    order_kind="reaction")
            continue
        if not _draw_move_fuel(r, reacting, actor, u, reach[order.to], order,     # 49.13/49.16
                               order_kind="reaction", reason="out of supply: no fuel to react"):
            continue
        payload = {"unit_id": u.id, "from": list(u.hex), "to": list(order.to),
                   "cp_spent": reach[order.to]}
        bp = tactics.bp_for_move(r.state, u, prev, order.to)     # 21.22: reaction accrues BP too
        if bp:
            payload["bp"] = bp
        old_cp = r.state.unit(u.id).cp_used
        r.emit(EventKind.REACTION_MOVED, reacting, actor, payload)   # 8.51: reaction IS movement
        _disorganize_overage(r, reacting, actor, u.id, old_cp,      # 6.21: reacting past CPA earns DP
                             old_cp + reach[order.to], tactics.effective_cpa(r.state, u))


def _reserve_shuffle(r: _Run, side: Side, actor: str, order: MoveOrder, u,
                     enemy_zoc: frozenset, enemy_occupied: frozenset) -> None:
    """18.22: a Reserve I unit may move ONE hex 'regardless of Capability Point expenditure' -- the
    CP-FREE administrative shuffle (adopted). The destination must be an adjacent, in-bounds,
    stacking-legal hex that is neither enemy-occupied nor in an enemy Zone of Control. Emits a
    UNIT_MOVED with cp_spent 0 (no fuel, no 6.21 overage). Because the destination is out of enemy
    ZOC it can never sit adjacent to an enemy combat unit, so no Reaction (8.5) can follow."""
    dest = tuple(order.to)
    if not is_adjacent(u.hex, dest) or not r.state.terrain.exists(dest):
        _reject(r, side, actor, order, "Reserve I may move at most one hex (18.22)")
        return
    if dest in enemy_occupied or dest in enemy_zoc or r.state.enemies_at(dest, side):
        # enemy_occupied/enemy_zoc are the phase-start snapshot; enemies_at is the LIVE board,
        # catching a non-phasing unit that reacted (8.5) into `dest` earlier this segment.
        _reject(r, side, actor, order, "Reserve I may not shuffle into enemy control (18.22)")
        return
    present = [x for x in r.state.units_at(dest) if x.side == side]
    if not stacking.within_hex_limit(present + [u], r.state.terrain.terrain[dest]):
        _reject(r, side, actor, order, "destination over stacking limit")
        return
    r.emit(EventKind.UNIT_MOVED, side, actor,
           {"unit_id": u.id, "from": list(u.hex), "to": list(dest), "cp_spent": 0})


def _exploitation_eligible(state: GameState, side: Side,
                           also: frozenset = frozenset()) -> frozenset:
    """8.23: which units may move in a Continual-Movement pulse -- the phasing COMBAT units within
    two hexes of an enemy combat unit (the exploitation zone), UNIONED with `also` (the Reserve
    seam: units just released from Reserve are the 18.25 exception to 8.23). Segment 0 is ungated
    (eligible=None)."""
    enemy = _other(side)
    enemy_hexes = [u.hex for u in state.living(enemy) if u.is_combat]
    out = set(also)
    for u in state.living(side):
        if u.is_combat and any(distance(u.hex, eh) <= 2 for eh in enemy_hexes):
            out.add(u.id)
    return frozenset(out)


def _reserve_designation(r: _Run, policy: Policy, side: Side) -> None:
    """Reserve Designation Phase (rule 48 V.G / 18.11-18.12), the phasing side only: before it
    moves, a side may hold living combat units back in Reserve I. Emits Phase.RESERVE once and a
    RESERVE_DESIGNATED per validated unit (18.26: no CP). Fires nothing -- no phase, no event --
    when the policy designates nothing, so every current scenario stays byte-identical."""
    ids = policy.reserve_designation(r.state, side)
    valid = [uid for uid in dict.fromkeys(ids)
             if (u := r.state.unit(uid)) is not None and u.alive and u.side == side
             and u.is_combat and u.reserve == 0]
    if not valid:
        return
    r.go(Phase.RESERVE, side)
    actor = f"{side.value}/Front"
    for uid in valid:
        r.emit(EventKind.RESERVE_DESIGNATED, side, actor, {"unit_id": uid})


def _reserve_release(r: _Run, policy: Policy, side: Side) -> frozenset:
    """Reserve Release Segment (rule 48 V.H.4 / 18.13), at each inter-pulse boundary: the phasing
    side releases chosen reserves (RESERVE_RELEASED at their current tier, 18.26 no CP), then every
    UNRELEASED Reserve I advances to Reserve II (RESERVE_FLIPPED, 18.13). Returns the released ids
    so the caller feeds them into the NEXT pulse's exploitation-eligible set (18.25, the exception
    to 8.23). Emits nothing when the side holds no reserves, so byte-identity holds."""
    actor = f"{side.value}/Front"
    chosen = set(policy.reserve_release(r.state, side))
    released = []
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        if u.reserve in (1, 2) and u.id in chosen:
            r.emit(EventKind.RESERVE_RELEASED, side, actor,
                   {"unit_id": u.id, "from_tier": u.reserve})
            released.append(u.id)
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        if u.reserve == 1:                              # 18.13: an unreleased Reserve I -> Reserve II
            r.emit(EventKind.RESERVE_FLIPPED, side, actor, {"unit_id": u.id})
    return frozenset(released)


def _continual_movement(r: _Run, policies: dict, side: Side) -> None:
    """The Continual-Movement pulse loop (rule 8.2/8.23 + the 48 V.H repeat), appended after a
    side's segment-0 Movement/Combat. First the segment-0 Reserve Release (48 V.H.4). Then each
    pulse: ask the policy whether to press on (continual_movement -- base [] declines, so a scripted
    scenario runs ZERO pulses and stays byte-identical); if so, open a SEGMENT_ADVANCED marker and
    re-run gated Movement (only the 8.23-eligible + just-released units), Breakdown, and a FRESH
    Combat Segment (8.25 re-attack); then release reserves again, feeding the NEXT pulse's 18.25
    eligible set. CP/BP persist across pulses (only the OpStage boundary resets them), so the CP
    ceiling, the 6.21 cohesion bleed, the monotone proposer and the 8.23 freeze terminate the loop
    long before MAX_CONTINUAL_SEGMENTS."""
    released = _reserve_release(r, policies[side], side)     # 48 V.H.4 after segment 0
    for seg in range(1, MAX_CONTINUAL_SEGMENTS + 1):
        if not policies[side].continual_movement(r.state, side):    # 8.2 go/no-go gate
            break
        r.emit(EventKind.SEGMENT_ADVANCED, side, "SYSTEM",
               {"segment": seg, "side": side.value})
        r.go(Phase.MOVEMENT, side)
        _movement(r, policies, side,
                  eligible=_exploitation_eligible(r.state, side, also=released))
        _breakdown(r, side)
        r.go(Phase.COMBAT, side)
        _combat(r, policies, side)
        released = _reserve_release(r, policies[side], side)   # 48 V.H.4 feeds the NEXT pulse


def _broken_count(pct: int, effective: int) -> int:
    """TOE Strength Points that break down: `pct` of the operational vehicles, fractions
    rounded UP (21.35), capped at the operational count. Exception (21.35): a unit of a
    single TOE point ignores a 10% result."""
    if pct <= 0 or effective <= 0:
        return 0
    if effective == 1 and pct == 10:
        return 0
    return min(effective, math.ceil(pct / 100 * effective))


def _breakdown(r: _Run, side: Side) -> None:
    """Breakdown check (rule 21.24): every vehicle unit of `side` that has ceased moving
    with more than three accumulated Breakdown Points (21.27) rolls on the 21.38 table,
    but only if it has climbed into a HIGHER column than its last check this OpStage
    (21.26 -- the geometric moving/stopping penalty). The rolled percentage of its
    operational TOE breaks down (21.35 rounding), moving into Unit.broken_down. Inert on
    non-vehicle scenarios (no vehicle accrues BP -> no roll -> byte-identical)."""
    actor = f"{side.value}/Front"
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        if not u.breaks_down or u.bp_accumulated <= 3:                       # 21.11 / 21.27
            continue
        # 21.37: +1 Breakdown column in Hot (theatre-wide, 29.31) or a Sandstorm -- per the unit's
        # section (29.7), so only vehicles standing under the storm take the sandstorm shift.
        wshift = combat_tables.weather_breakdown_shift(r.state.weather_at(u.hex))
        col = combat_tables.breakdown_column(u.bp_accumulated, u.bar, wshift)
        if col <= u.bp_checked_column:                                       # 21.26 gate
            continue
        d1, d2 = r.d6("breakdown"), r.d6("breakdown")
        pct = combat_tables.breakdown_result(u.bp_accumulated, u.bar, wshift, d1 * 10 + d2)
        broken = _broken_count(pct, u.effective_strength)
        r.emit(EventKind.BREAKDOWN_CHECKED, side, actor,
               {"unit_id": u.id, "column": col, "bar": u.bar,
                "weather_shift": wshift, "pct": pct}, rng_draws=(d1, d2))
        if broken > 0:
            r.emit(EventKind.VEHICLE_BROKE_DOWN, side, actor,
                   {"unit_id": u.id, "amount": broken})


# Field tank/SPA repair expends Fuel before rolling (22.15/22.26): ONE Fuel Point per
# tank TOE Strength Point undergoing repair -- "He may attempt to repair only those Tank
# TOE Strength Points he has expended Fuel for" (22.26). Armored-car / recce field repair
# is free (22.24).
_REPAIR_FUEL_PER_TOE: int = 1


def _field_repair_blocked(weather_label: str) -> bool:
    """22.13d: no Field Repair while the Weather is Rainstorm or Sandstorm. Called with the
    weather in the repairing unit's OWN section (state.weather_at), so a localised storm (29.7)
    blocks repair only where it actually falls."""
    return weather_label in ("rainstorm", "sandstorm")


def _repaired_count(vclass: str, result: int, broken: int) -> int:
    """TOE Strength Points a 22.8 field result repairs, capped at the broken pool. A
    tank result is a percentage (fractions round up, 22.25); an armored-car/recce or
    truck result is a flat point count (22.23/22.24)."""
    if broken <= 0:
        return 0
    if vclass == "tank":
        if broken == 1 and result == 10:                # 22.25 single-TOE ignores 10%
            return 0
        return min(broken, math.ceil(result / 100 * broken))
    return min(result, broken)


def _repair(r: _Run, side: Side) -> None:
    """Repair Phase (rule 22.12): the phasing side field-repairs its broken-down vehicles.
    Each such unit in a non-enemy hex (22.13a), weather permitting (22.13d), expends the
    22.15 Fuel and rolls one die on the 22.8 Field column; the repaired TOE flows back to
    the operational pool (VEHICLE_REPAIRED). Fires only when the side actually has broken
    vehicles to repair, so every pre-breakdown scenario stays byte-identical."""
    enemy_ctrl = CONTROL_OF[_other(side)]
    repairable = [u for u in r.state.living(side)
                  if u.broken_down > 0 and u.breaks_down
                  and r.state.control_of(u.hex) != enemy_ctrl                 # 22.13a
                  and not _field_repair_blocked(r.state.weather_at(u.hex))]   # 22.13d, per section
    if not repairable:
        return
    r.go(Phase.REPAIR, side)
    actor = f"{side.value}/Repair"
    for u in sorted(repairable, key=lambda u: u.id):
        cur = r.state.unit(u.id)
        vclass = "tank" if cur.is_tank else "ac_recce"
        if vclass == "tank":                            # 22.26: one Fuel Point per broken TOE, before rolling
            draws = supply.plan_draw(r.state, cur, supply.FUEL, _REPAIR_FUEL_PER_TOE * cur.broken_down)
            if draws is None:
                continue                                # 22.13b: no supplies -> no repair
            for sid, qty in draws:
                r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                       {"supply_id": sid, "commodity": supply.FUEL, "qty": qty, "unit_id": cur.id})
        die = r.d6("repair")
        cur = r.state.unit(u.id)                        # re-read after the fuel draw
        repaired = _repaired_count(vclass, combat_tables.field_repair(vclass, die), cur.broken_down)
        if repaired > 0:
            r.emit(EventKind.VEHICLE_REPAIRED, side, actor,
                   {"unit_id": cur.id, "amount": repaired}, rng_draws=(die,))   # 22.8: certify the roll


def _reject(r: _Run, side: Side, actor: str, order: MoveOrder, reason: str,
            order_kind: str = "move") -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": order_kind, "unit_id": order.unit_id, "to": list(order.to),
            "reason": reason})


def _organization(r: _Run, policy: Policy, side: Side) -> None:
    """[32.32] THE ORGANIZATION PHASE: detail lorries to carry a depot, or stand them down.

    "Supply Units may be transported by Motorization Points. THIRTY Motorization Points are required
    to transport one real supply unit... Motorization Points may be attached/detached to supply
    units ONLY DURING THE ORGANIZATION PHASE of an OpStage. A supply unit not assigned the minimum
    necessary number of Motorization Points may not be moved."

    THIS IS THE PRICE OF THE DESERT COLUMN, AND UNTIL NOW WE TOOK THE PERMISSION AND NEVER PAID IT.
    32.33 lets a dump march with the army; 32.32 says what that costs, and 32.51 says whose pocket
    it comes out of -- "Motorization Points are used IN PLACE OF Truck Points... treated in all
    aspects as MEDIUM Truck Points". One pool, not two: in the abstract game you are issued MP and
    no trucks, in the full Logistics Game trucks and no MP, and 32.51 is the exchange rate between
    them. So thirty Motorization Points is thirty MEDIUM Truck Points out of the same 60.33/60.43
    park that hauls the army's fuel and ammunition, and every depot pushed forward is thirty Truck
    Points of freight that does not reach the front. Free, the Axis carpeted the desert with depots
    that chased its own spearhead (a dump moves 15 CP/OpStage, faster than the infantry it feeds).

    A STANDING RESERVATION, NOT A PER-HEX TOLL. The rule hinges BOTH halves on the Organization
    Phase and 32.56 speaks of "the unit they are ASSIGNED to", so the lorries stay under the depot,
    out of the freight rotation, until their owner stands them down here in a later Organization
    Phase. The column keeps costing for as long as it stands.

    THE RELEASE SWEEP first: a column whose depot has been captured (32.13), blown empty (54.14) or
    otherwise stopped being a carriable field dump has nothing left to carry, and its lorries would
    otherwise be hostage to it for the rest of the war. They come back HERE, in the Organization
    Phase, because that is the only beat the rule lets them come back in -- so a depot lost on
    Game-Turn 20 still ties up thirty Truck Points until the next Organization Phase, which is
    friction the rule genuinely implies.

    FLAGGED (32.56): "If their assigned unit is captured, the Motorization Points are also captured
    and may be used by the Enemy." We give them back to their owner rather than to the captor. The
    captor's half means minting Truck Points for the enemy on a captured hex -- a truck-OOB change,
    not this slice."""
    if not r.state.motorized_supply:      # the flagged campaign gate (game.state.motorized_supply)
        return
    r.go(Phase.ORGANIZATION, side)
    actor = f"{side.value}/Logistics"
    for sid, legs in sorted(r.state.motorization.items()):
        if not any(t.side == side for tid, _ in legs for t in (r.state.truck(tid),) if t):
            continue                                   # not this side's lorries
        su = r.state.supply(sid)
        if su is not None and su.side == side and not su.empty and not su.base:
            continue                                   # still a live field dump: the column stands
        r.emit(EventKind.MOTORIZATION_DETACHED, side, actor,
               {"supply_id": sid, "legs": [list(x) for x in legs],
                "points": sum(p for _, p in legs), "reason": "lost"})

    for order in policy.motorization(r.state, side):
        su = r.state.supply(order.supply_id)
        if not order.truck_ids:                        # the detach: stand the column down
            if order.supply_id in r.state.motorization:
                legs = r.state.motorization[order.supply_id]
                r.emit(EventKind.MOTORIZATION_DETACHED, side, actor,
                       {"supply_id": order.supply_id, "legs": [list(x) for x in legs],
                        "points": sum(p for _, p in legs), "reason": "orders"})
            continue
        if su is None or su.side != side or su.empty or su.base or su.is_dummy:
            _reject_motorize(r, side, actor, order, "no such carriable field dump")
            continue
        if order.supply_id in r.state.motorization:
            continue                                   # already under a column -- nothing to do
        legs = supply.column_legs(r.state, side, order.truck_ids)
        if not legs:                                   # 32.32: short of the thirty -> no column
            _reject_motorize(r, side, actor, order,
                             "fewer than thirty free Medium Truck Points (32.32/32.51)")
            continue
        r.emit(EventKind.MOTORIZATION_ATTACHED, side, actor,
               {"supply_id": order.supply_id, "truck_ids": list(order.truck_ids),
                "legs": [list(x) for x in legs], "points": sum(p for _, p in legs)})


def _reject_motorize(r: _Run, side: Side, actor: str, order, why: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "motorize", "supply_id": order.supply_id,
            "truck_ids": list(order.truck_ids), "reason": why})


def _supply_movement(r: _Run, policy: Policy, side: Side) -> None:
    """Relocate supply units with the advancing army (rule 32.3): a carried dump
    moves up to CPA 15 as medium-truck (32.58A), costs a flat 1 Fuel Point (32.24) drawn
    from its own trucks, and must end stacked with a friendly combat unit (32.33).
    Validated at the boundary like every other order.

    AND IT MUST HAVE ITS THIRTY MOTORIZATION POINTS (32.32) -- the lorries booked onto it back in
    the Organization Phase (_organization). "A supply unit not assigned the minimum necessary number
    of Motorization Points may not be moved" is the plainest sentence in Section 32, and without it
    the desert column is free: a depot that outruns the infantry it feeds, at no cost to the army's
    freight. The escorting combat unit still pays NOTHING extra, and that is correct -- 32.58C, the
    attached points "are not required to expend CP's if stacked with combat units participating in
    combat", and 32.33 asks only that the dump begin and remain stacked with one. The column's whole
    price is the thirty Truck Points and the one Fuel Point, and both are now charged."""
    actor = f"{side.value}/Logistics"
    moved: set = set()               # a dump relocates at most once per OpStage (32.58A)
    for order in policy.supply_orders(r.state, side):
        su = r.state.supply(order.supply_id)
        if su is None or su.side != side or su.empty:
            _reject_supply(r, side, actor, order, "no such active supply unit")
            continue
        if su.base:
            _reject_supply(r, side, actor, order, "a strategic rear base is immobile (rule 57)")
            continue
        if r.state.motorized_supply and not supply.motorized(r.state, su.id):
            _reject_supply(r, side, actor, order,
                           "no Motorization Points assigned -- thirty are required (32.32)")
            continue
        if su.id in moved:
            _reject_supply(r, side, actor, order, "already moved this OpStage (CPA 15/stage)")
            continue
        if order.to == su.hex or order.to not in supply.reachable_moves(r.state, su):
            _reject_supply(r, side, actor, order, "beyond CPA 15 or blocked by ZOC")
            continue
        if not any(u.side == side and u.is_combat for u in r.state.units_at(order.to)):
            _reject_supply(r, side, actor, order, "must end stacked with a friendly combat unit")
            continue
        if su.fuel < supply.SUPPLY_MOVE_FUEL:
            _reject_supply(r, side, actor, order, "out of fuel to move")
            continue
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": su.id, "commodity": supply.FUEL,
                "qty": supply.SUPPLY_MOVE_FUEL, "unit_id": su.id})
        r.emit(EventKind.SUPPLY_MOVED, side, actor,
               {"supply_id": su.id, "from": list(su.hex), "to": list(order.to)})
        moved.add(su.id)


def _blow_dumps(r: _Run, policy: Policy, side: Side) -> None:
    """[54.14] "Players may attempt to BLOW supply dumps and their supplies." The defender's answer
    to 32.13, and the rule that turns an overrun depot from a WINDFALL into a DECISION.

    Without it, dump capture is strictly a one-way gift to whoever is advancing -- and in September
    1940 that is the Axis, all the way to the wire. The rulebook does not leave a retreating army
    its stocks to hand over: it lets it burn them, at a price, with a die.

    THE RULE, in full. Only NON-GUN units may attempt (54.14). Only one Phasing unit per hex may
    attempt a particular dump per Player-Turn (enforced by `done` below). The attempt costs one
    third of the unit's BASIC CPA, rounded up, and may never cost more than its whole CPA. The
    Player may announce, BEFORE rolling, that he is spending an additional one-third or two-thirds
    for +1 on the die each. One die, modified by 54.17, cross-indexed on the Supply Dump Demolition
    Table, gives the percentage of EVERY commodity in the dump that is destroyed.

    WHOSE dump: 54.14 says "supply dumps", not "your supply dumps", and 54.15 makes any dump usable
    by any player -- so an ATTACKER may blow a dump he cannot carry off just as a defender may deny
    his own. The order names the dump; the engine only checks the unit is standing on it. What it
    will NOT blow is a rule-57 strategic base or a 52.1 well (neither is a Supply Dump counter --
    the same exemption _capture_dumps makes, for the same reason).

    DEFERRED and flagged: 13.25's blow-as-you-retreat-before-assault (the same attempt at a flat 1/3
    CPA, vacating the hex regardless of the result) -- the retreat path is a separate segment and
    the standing order below already fires a stage earlier, when the enemy first comes adjacent.
    Also 32.17, the abstract game's simpler destroy-a-Supply-Unit roll, which this supersedes."""
    done: set = set()
    for order in policy.demolition(r.state, side):
        u, dump = r.state.unit(order.unit_id), r.state.supply(order.supply_id)
        if u is None or dump is None or not r.state.on_map(u) or u.side != side:
            continue
        if dump.base or dump.is_dummy or dump.empty:   # 57 / 52.1: not a Supply Dump counter
            continue
        if (u.hex, dump.id) in done or not supply.can_blow(u, dump):
            continue                                   # 54.14: one Phasing unit per hex per dump
        done.add((u.hex, dump.id))
        # 54.14 twice over ("may never expend more than the unit's basic CPA... may not exceed its
        # CPA"): the +1s bought before the roll are bounded by the CP the unit actually has left.
        thirds = supply.affordable_thirds(u, order.extra_thirds)
        cp = supply.demolition_cp(u, thirds)
        # 54.17: "-1 if the attempting unit(S) TOTAL one Stacking Point or less" -- the STACK on the
        # dump's hex, not the one counter (see supply.demolition_modifier: every combat counter here
        # is a 1-Stacking-Point battalion, so a per-unit reading would make the -1 a constant).
        stack = sum(x.stacking_points for x in r.state.units_at(dump.hex)
                    if x.side == side and x.is_combat)
        mod = supply.demolition_modifier(dump, r.state.terrain.terrain[dump.hex],
                                         extra_thirds=thirds, stack_points=stack)
        die = r.d6("demolition")
        pct = supply.demolition_percent(die + mod)
        destroyed = supply.demolition_loss(dump, pct)
        r.emit(EventKind.SUPPLY_DUMP_BLOWN, side, f"{side.value}/Engineers",
               {"supply_id": dump.id, "unit_id": u.id, "cp": cp, "die": die, "modifier": mod,
                "pct": pct, "destroyed": destroyed}, rng_draws=(die,))
        if cp > 0:                                     # 54.14: the CPA bill, whatever the die said
            r.emit(EventKind.CP_EXPENDED, side, f"{side.value}/Engineers",
                   {"unit_id": u.id, "activity": "blow_dump", "cp": cp})


def _capture_dumps(r: _Run) -> None:
    """[32.13] "If any enemy combat unit enters a Supply Unit's hex, that unit is CAPTURED (and its
    supplies used immediately and freely)." The full logistics game says the same thing twice more:
    [54.15] "Dumps may be used by any Player as supply sources", and [49.19] "Fuel is
    non-denominational. It can be used by either player, MAKING A SUPPLY DUMP A WORTHWHILE
    OBJECTIVE."

    THIS IS THE HISTORICAL ENGINE OF OPERATION COMPASS, and it is the feedback loop without which no
    desert offensive is ever sustainable: an advance beyond your own chain starves, so nothing is
    ever taken, so the score is the September-1940 setup frozen for 111 Game-Turns. Measured before
    it existed: a Commonwealth combat unit stood ON AX-Stage-Derna, holding 36,209 Fuel Points, at
    Game-Turn 15 -- and drew nothing, because the dump belonged to the enemy. One captured Derna
    dump is ten to twenty-six times the Commonwealth's entire forward delivery rate.

    A SWEEP, not a hook on UNIT_MOVED: a unit enters a hex through five different doors (movement,
    Reaction 8.5, Retreat Before Assault 13.21, combat retreat, the 8.2 exploitation pulse) and the
    rule does not care which. Idempotent and deterministic (dumps in id order), so running it after
    movement, after combat and after the exploitation pulse costs nothing when nothing changed.

    A BASE IS NOT CAPTURABLE, and this is a FLAGGED PROXY. `base=True` marks the rule-57 strategic
    rear base (AL-Cairo / AL-Alexandria) and the 52.1 wells. Neither is a Supply Dump counter that
    32.13 can pick up: the base is OUR ABSTRACTION of an off-map Nile Delta / Suez source of
    unlimited capacity (54.12), seeded at 125,000,000 points precisely because it stands for a
    faucet rather than a pile, and a well is geography. Leaving an infinite dump lying on the map as
    a capturable prize is not faithfulness, it is a bug with a rules citation: measured under a
    laboratory capture rule that did not exempt it, the Axis took the Commonwealth's base depots and
    its score went 380 -> 434 with its supplied strength jumping from 4 units to 23-41. The engine
    already treats `base` as "immobile strategic source, not a field dump" in _supply_movement
    (rule 57) and _evaporate (49.3); this is the third clause of the same distinction.

    THE DEFENDER'S ANSWER IS NOW LIVE: [54.14] blowing the dump (_blow_dumps, above). Capture is no
    longer a one-way gift to whoever is advancing -- a non-gun unit standing on a depot the enemy has
    come adjacent to may spend a third of its CPA, roll on the 54.17 Demolition Table, and burn the
    percentage it rolls. That makes an overrun depot a DECISION ("do I burn my own fuel?") rather
    than a windfall, which is what the rules always said it was.

    GATED on state.dump_capture, which ONLY game.scenario.campaign sets. 32.13 is a general rule and
    this is not a claim otherwise -- it fires on Game-Turn 1 of both byte-locked benchmark scenarios
    and moves their published determinism_signature. See the field's comment in game.state."""
    if not r.state.dump_capture:
        return
    for su in sorted(r.state.supplies, key=lambda s: s.id):
        if su.base or su.is_dummy:               # 57 / 52.1: a base and a well are not counters
            continue
        if su.empty:
            # AN EMPTY DUMP IS NOT A PRIZE. 32.13 captures a Supply Unit "and its supplies", and by
            # 32.15 a Supply Unit with nothing left in it is REMOVED from the map altogether -- there
            # is no counter there to take. Skipping it is not a softening of the rule, it is the rule:
            # what 32.13 transfers is the supplies.
            #
            # AND IT IS LOAD-BEARING. The campaign deliberately parks the Commonwealth's Operation
            # Compass Field Supply Depots INSIDE cities the Axis is holding on Game-Turn 1 -- an empty
            # AL-Stage-Sollum under the Italian garrison at Sollum, an empty AL-Tobruk under the one in
            # Tobruk (60.34) -- because what keeps those depots dry is not distance but CONTROL, and
            # taking the city is what fixes it (campaign_claim.spine_awaits_control). Capturing them on
            # Game-Turn 1 does not loot one Point, and it severs the Commonwealth's supply spine before
            # the war starts: measured, the take-and-hold then claimed NO CITY AT ALL for the whole
            # campaign, because no city could be fed. Nobody "enters" a dump that was under their feet
            # at the setup.
            continue
        here = [u for u in r.state.units_at(su.hex) if u.is_combat and u.strength >= 1]
        if not here:
            continue
        holders = {u.side for u in here}
        if su.side in holders or len(holders) != 1:   # contested, or the owner is still standing on it
            continue
        captor = next(iter(holders))
        # 49.19/50.16/51.16: capture is TAXED. Only one-third (round up) of the Ammunition and 50%
        # of the Stores are usable by the captor; the rest are LOST. Fuel passes intact (non-
        # denominational) and Water is untaxed. Bake the per-commodity loss so the SUPPLY_CAPTURED
        # handler drains it and credits consumed[] -- conservation holds, exactly as SUPPLY_DUMP_BLOWN
        # bakes its destroyed amounts. (This is the FULL-GAME tax; the old code cited 32.13, the
        # ABSTRACT game's "used immediately and freely", which 47.0/32.0 do not license here.)
        lost = {c: getattr(su, c.lower()) - supply.captured_usable(c, getattr(su, c.lower()))
                for c in supply.COMMODITIES}
        lost = {c: q for c, q in lost.items() if q > 0}
        r.emit(EventKind.SUPPLY_CAPTURED, captor, f"{captor.value}/Front",
               {"supply_id": su.id, "from": su.side.value, "to": captor.value,
                "ammo": su.ammo, "fuel": su.fuel, "stores": su.stores, "water": su.water,
                "lost": lost})


def _reject_supply(r: _Run, side: Side, actor: str, order, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "supply_move", "supply_id": order.supply_id,
            "to": list(order.to), "reason": reason})


def _truck_convoys(r: _Run, policy: Policy, side: Side) -> None:
    """Truck Convoy Movement Phase (rule 48 Stage V.J): the unattached 2nd/3rd-line truck
    convoys (rule 53) haul supply forward. Each order may LOAD from a co-located dump, MOVE
    up to the 53.22 extended convoy CPA (Light 40, Medium/Heavy 30) reusing the 32.16
    trace-blocking verbatim while burning its OWN cargo fuel (49.18), then UNLOAD into a
    forward dump (respecting the 54.12 ceiling). Fires ONLY when the side fields truck
    formations, so every truck-less scenario stays byte-identical."""
    if not any(t.side == side for t in r.state.trucks):
        return
    r.go(Phase.LOGISTICS, side)
    actor = f"{side.value}/Logistics"
    moved: set = set()               # a formation relocates at most once per phase (53.21)
    for order in policy.truck_orders(r.state, side):
        _truck_order(r, side, actor, order, moved)


def _truck_order(r: _Run, side: Side, actor: str, order, moved: set) -> None:
    """One truck-convoy order, run against the formation's FREE Truck Points (32.32).

    THE CONTENDED POOL, and it is the whole reason this rule earns its keep. A formation with thirty
    of its Points booked under a desert column (game.supply.free_points) drives the freight run as
    the SMALLER convoy it now is: its 53.12 load ceiling falls with the lorries it no longer has,
    and so does the 49.18 fuel it burns getting there. Book five columns out of the Axis's 150
    Medium Points at Benghazi and there is no Axis medium freight at all.

    `_convoy` re-reads state each leg (the load leg folds cargo onto the formation, so the move leg
    must see it) and shrinks it to what is actually free. With no columns standing this is the
    formation itself, unchanged -- which is why every truck-bearing scenario stays byte-identical."""
    def _convoy():
        t = r.state.truck(order.truck_id)
        return replace(t, points=supply.free_points(r.state, t))

    truck = r.state.truck(order.truck_id)
    if truck is None or truck.side != side:
        _reject_truck(r, side, actor, order, "no such truck formation under this command")
        return
    if supply.free_points(r.state, truck) <= 0:
        _reject_truck(r, side, actor, order,
                      "every Truck Point of this formation is under a supply column (32.32)")
        return
    if order.load and not _truck_load(r, side, actor, order, _convoy()):
        return
    if order.to is not None and not _truck_move(r, side, actor, order, _convoy(), moved):
        return
    if order.unload:
        _truck_unload(r, side, actor, order, _convoy())


def _truck_load(r: _Run, side: Side, actor: str, order, truck) -> bool:
    dump = r.state.supply(order.load_from)
    if dump is None or dump.side != side or dump.hex != truck.hex:
        _reject_truck(r, side, actor, order, "no co-located friendly dump to load from")
        return False
    cargo = {c: q for c, q in order.load.items() if q > 0}
    if not set(cargo).issubset(supply.COMMODITIES):     # a live seat may name a bogus commodity
        _reject_truck(r, side, actor, order, "load names an unknown commodity")
        return False
    if any(getattr(dump, c.lower()) < q for c, q in cargo.items()):
        _reject_truck(r, side, actor, order, "dump lacks the ordered load")
        return False
    if not supply.truck_load_admissible(truck, cargo):
        _reject_truck(r, side, actor, order, "load exceeds truck capacity (53.12)")
        return False
    r.emit(EventKind.TRUCK_LOADED, side, actor,
           {"truck_id": truck.id, "supply_id": dump.id, "cargo": cargo})
    return True


def _truck_move(r: _Run, side: Side, actor: str, order, truck, moved: set) -> bool:
    if truck.id in moved:
        _reject_truck(r, side, actor, order, "already moved this Truck Convoy Phase")
        return False
    reach = supply.reachable_truck_moves(r.state, truck)
    to = tuple(order.to)
    if to == truck.hex or to not in reach:
        _reject_truck(r, side, actor, order, "beyond convoy CPA or blocked by ZOC")
        return False
    fuel = supply.truck_move_fuel(truck, reach[to])
    if truck.fuel < fuel:
        _reject_truck(r, side, actor, order, "out of cargo fuel to move (49.18)")
        return False
    r.emit(EventKind.TRUCK_MOVED, side, actor,
           {"truck_id": truck.id, "from": list(truck.hex), "to": list(to),
            "cp_spent": reach[to], "fuel": fuel})
    moved.add(truck.id)
    return True


def _truck_unload(r: _Run, side: Side, actor: str, order, truck) -> None:
    """Unload a convoy into the dump at its hex -- ESTABLISHING that dump first if the hex has
    none (rule 54.11: "Any hex can be used as a supply dump").

    THE MISSING SUBSYSTEM. Until now this rejected any unload whose `unload_to` named no existing
    dump, NO EventKind ever created one, and game.apply never appended to state.supplies -- so the
    depot list was FROZEN AT CONSTRUCTION for the whole 111-turn campaign. An army could not build
    the network rule 54.16 calls "top priority" for a logistics commander, could not extend its
    chain forward as it advanced, and therefore could never CONSOLIDATE an advance: measured, both
    armies ended ~9 hexes beyond the nearest stocked dump -- just outside the 32.16 cpa/2 trace --
    and stayed there, with 5-8% of the Axis and 29% of the Commonwealth able to draw a single point
    of supply, from Game-Turn 10 to Game-Turn 111.

    A dump is established only where the convoy is STANDING (54.11) and only if the hex holds no
    friendly dump already. It is born EMPTY and the TRUCK_UNLOADED below fills it, so nothing is
    minted and conservation is untouched."""
    dump = r.state.supply(order.unload_to)
    if dump is None:                                    # 54.11: establish it where the lorries are
        dump = _establish_dump(r, side, actor, order, truck)
        if dump is None:
            return
    if dump.side != side or dump.hex != truck.hex:
        _reject_truck(r, side, actor, order, "no co-located friendly dump to unload into")
        return
    cap = supply.dump_capacity_at(r.state, dump.hex)                  # 54.12 ceiling
    cargo: dict = {}
    for c, q in order.unload.items():
        onhand = getattr(dump, c.lower())
        landed = min(q, getattr(truck, c.lower()), min(cap[c], onhand + q) - onhand)
        if landed > 0:
            cargo[c] = landed
    if cargo:
        r.emit(EventKind.TRUCK_UNLOADED, side, actor,
               {"truck_id": truck.id, "supply_id": dump.id, "cargo": cargo})


def _establish_dump(r: _Run, side: Side, actor: str, order, truck):
    """[54.11] Found a new, EMPTY supply dump on the hex the convoy is standing on, under the id
    the order named. Refused if the hex already carries a friendly dump (unload into that one) or
    if an enemy combat unit is standing there. Returns the new dump, or None on rejection."""
    here = [s for s in r.state.supplies if s.hex == truck.hex and s.side == side
            and not wells.is_water_source(s)]
    if here:
        _reject_truck(r, side, actor, order, "a friendly dump already stands on this hex (54.11)")
        return None
    if r.state.enemies_at(truck.hex, side):
        _reject_truck(r, side, actor, order, "cannot establish a dump under an enemy unit (54.11)")
        return None
    r.emit(EventKind.SUPPLY_DUMP_ESTABLISHED, side, actor,
           {"supply_id": order.unload_to, "side": side.value, "hex": list(truck.hex)})
    return r.state.supply(order.unload_to)


def _reject_truck(r: _Run, side: Side, actor: str, order, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "truck_convoy", "truck_id": order.truck_id, "reason": reason})


# --- [24.0] THE CONSTRUCTION SEGMENT (rule 48 V.C.4) --------------------------------------------

def _construction(r: _Run, policy: Policy, side: Side) -> None:
    """The Construction Segment of the Organization Phase (48 V.C.4), in its two charted Steps.

    THE ENGINE HAD NO CONSTRUCTION AT ALL. Rule 24's opening sentence lists railroads and supply
    dumps among the things that "come into existence through construction", and neither could: the
    map's rail edge-set was frozen at Mersa Matruh where rule 60.7 leaves it, and a supply dump was
    either seeded in September 1940 or founded free by a passing lorry. So the Commonwealth could
    not do the one thing that won it this campaign -- push its railhead west and eat off it -- and
    neither side could turn a heap of supplies in the desert into a depot its lorries could lift
    from again (24.9's Note).

      a. COMPLETION STEP (24.11): "any work scheduled for completion is finished". A railroad hex
         with its two company-stages banked (24.62) joins the map.
      b. INITIATION / CONTINUATION STEP: work is booked for this Operations Stage. Every gate the
         rule names is checked here and nowhere else -- who may build (24.61/24.9), the surveyed
         line and no skipped hex (24.67), the enemy's control (24.65), the Store Points on hand in
         the hex (24.64/24.13/24.9), the weather (24.22).

    THE 24.12 PIN is honoured by CONSTRUCTION COMING FIRST. "Units involved in construction may not
    expend any Capability Points during an Operations Stage; otherwise that construction is halted",
    and 48 V.C.4.b: "any units involved in such work may not be moved during the remainder of the
    current Operations Stage". So the Segment runs BEFORE the side's Movement Phase, and the units
    it books are struck from that stage's movement (r.building) -- the pin is structural, not a
    check after the fact. A unit that is not booked is free to move, which is 24.16's voluntary cease.

    Fires only when a policy issues a BuildOrder, so every scenario in this repo that does not
    construct emits no Phase.CONSTRUCTION and stays byte-identical."""
    orders = policy.construction(r.state, side)
    projects = [h for h, n in sorted(r.state.construction.items())
                if n >= construction.RAIL_COMPANY_STAGES]
    if not orders and not projects:
        return
    r.go(Phase.CONSTRUCTION, side)
    actor = f"{side.value}/Engineers"
    for hx in projects:                                  # a. the Construction Completion Step (24.11)
        _complete_rail(r, side, actor, hx)
    booked: set = set()
    for order in orders:                                 # b. Initiation / Continuation
        if order.item == construction.RAIL:
            _build_rail(r, side, actor, order, booked)
        elif order.item == construction.DUMP:
            _build_dump(r, side, actor, order)
    r.building |= booked                                 # 24.12: they may not move this stage


def _complete_rail(r: _Run, side: Side, actor: str, hx: Coord) -> None:
    """[24.11]a / [24.67] The track is laid: the hex joins the map's rail edge-set, extending the
    line from the head it grew out of, and its Under Construction marker comes off. From this
    Operations Stage the trains run to it (54.35 / _rail_stops), which is the whole point."""
    link = construction.rail_edge(r.state, hx)
    if link is None:                                     # the line moved on without it: drop the work
        r.emit(EventKind.CONSTRUCTION_ADVANCED, side, actor,
               {"item": construction.RAIL, "hex": list(hx), "unit_ids": [], "stages": 0,
                "progress": 0})
        return
    frm = link[0] if link[1] == hx else link[1]
    r.emit(EventKind.CONSTRUCTION_COMPLETED, side, actor,
           {"item": construction.RAIL, "hex": list(hx), "from": list(frm)})


def _build_rail(r: _Run, side: Side, actor: str, order, booked: set) -> None:
    """[24.6] Lay one hex of new track. Every clause of the rule is a line of this function.

    THE GANG WORKS FROM THE RAILHEAD, NOT FROM THE HEX IT IS LAYING. The Construction Chart's Build
    row for Railroad restricts it in three words -- "building limited to HEAD or track" -- and 24.63
    says the same of a rebuild: "the unit may rebuild the hex IT OCCUPIES plus any two hexes ADJACENT
    to the Engineer unit". So the companies stand on the last completed hex and push the line out in
    front of them, which is how a railway has always been built.

    It is also the only reading that works, and the rule is coherent because of it: 24.64 wants one
    Store Point "PRESENT WITH THE ENGINEER UNIT and actually expended in the Construction Segment",
    and the hex about to be railed is a patch of empty desert with nothing in it. The railhead is
    where the trains stop (54.35 / _rail_stops), so the railhead is where the stores are. The railway
    feeds its own construction, hex by hex, and that is exactly what it did."""
    hx = tuple(order.hex)
    head = construction.rail_head(r.state)
    if hx != construction.rail_next(r.state) or head is None:
        _reject_build(r, side, actor, order, "no hex may be skipped: build from the railhead (24.67)")
        return
    if not construction.rail_buildable(r.state, side, hx):
        _reject_build(r, side, actor, order,
                      "enemy-held hex (24.65) or foul weather (24.22)")
        return
    gang = [u for u in (r.state.unit(uid) for uid in order.unit_ids)
            if u is not None and u.side == side and r.state.on_map(u)
            and construction.builds_rail(u) and u.hex == head and u.cp_used == 0]
    if not gang:
        _reject_build(r, side, actor, order,
                      "only the two NZ Railroad Construction companies, standing on the railhead, "
                      "may build railroad (24.61 / Construction Chart: 'limited to head or track')")
        return
    progress = r.state.construction.get(hx, 0)
    if progress == 0:                                     # 24.64/24.13: the Stores are expended AT THE
        dump = construction.dump_at(r.state, side, head)  # START, out of the pile the gang stands on
        if dump is None or dump.stores < construction.RAIL_STORES:
            _reject_build(r, side, actor, order,
                          "one Store Point must be present with the engineer and expended (24.64)")
            return
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": dump.id, "commodity": supply.STORES,
                "qty": construction.RAIL_STORES, "unit_id": gang[0].id})
    stages = len(gang)                                   # 24.62: one company-stage per company
    r.emit(EventKind.CONSTRUCTION_ADVANCED, side, actor,
           {"item": construction.RAIL, "hex": list(hx), "unit_ids": [u.id for u in gang],
            "stages": stages, "progress": progress + stages})
    booked.update(u.id for u in gang)


def _build_dump(r: _Run, side: Side, actor: str, order) -> None:
    """[24.9] Construct a supply dump: three Capability Points and twenty Store Points, spent by any
    one TOE Strength Point of any type standing in the hex. What it buys is the Note -- from now on
    "trucks in convoy" MAY load from this hex, so the heap of supplies the army dropped in the desert
    becomes a LINK its bucket brigade can lift out of (53.14/54.16) instead of a one-way sink."""
    hx = tuple(order.hex)
    dump = construction.dump_at(r.state, side, hx)
    u = next((u for u in (r.state.unit(uid) for uid in order.unit_ids)
              if u is not None and u.side == side and r.state.on_map(u)
              and construction.can_construct_dump(r.state, side, u, dump)), None)
    if u is None:
        _reject_build(r, side, actor, order,
                      "needs 1 TOE Strength Point with 3 CP and 20 Stores in the hex (24.9)")
        return
    # [24.13]/[32.15] The twenty Store Points come OUT OF THE HEX, not out of one counter. The
    # can_construct_dump check counts every friendly pile standing here (construction.stores_at), so
    # the charge must be drawn the same way or a hex whose stores are SPLIT between two co-located
    # dumps passes the check and over-drains the one the engine happened to name -- an
    # InvariantViolation, and one that predates rule 32.32 (see construction.stores_draw).
    for sid, qty in construction.stores_draw(r.state, side, hx, construction.DUMP_STORES):
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": sid, "commodity": supply.STORES, "qty": qty, "unit_id": u.id})
    r.emit(EventKind.CP_EXPENDED, side, actor,
           {"unit_id": u.id, "activity": "construct_dump", "cp": construction.DUMP_CP})
    r.emit(EventKind.SUPPLY_DUMP_CONSTRUCTED, side, actor,
           {"supply_id": dump.id, "unit_id": u.id, "cp": construction.DUMP_CP,
            "stores": construction.DUMP_STORES})


def _reject_build(r: _Run, side: Side, actor: str, order, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "construction", "item": order.item, "hex": list(order.hex),
            "unit_ids": list(order.unit_ids), "reason": reason})


def _other(side: Side) -> Side:
    return Side.ALLIED if side is Side.AXIS else Side.AXIS


def _idle_recovery(r: _Run) -> None:
    """Reorganization for a CP-idle Operations Stage (rule 6.24.1): every on-map unit that
    used absolutely no Capability Points this stage earns five Reorganization Points (a
    Cohesion gain), but this method may NEVER carry a unit above Cohesion 0. Fired at the
    OpStage boundary BEFORE _reset_opstage zeroes cp_used -- the counter-weight to the 6.21
    overage bleed, so the CP economy is not a monotonic collapse. Units still in Disorganization
    (negative Cohesion) that sat out the whole stage climb back toward 0, five RP at a time."""
    for u in r.state.units:
        if r.state.on_map(u) and u.cp_used == 0 and u.cohesion < 0:
            delta = min(5, -u.cohesion)                 # 6.24.1: capped so it never exceeds 0
            r.emit(EventKind.COHESION_CHANGED, u.side, "SYSTEM",
                   {"unit_id": u.id, "delta": delta})


def _overage_dp(cp_used: float, cpa: int) -> int:
    """6.21: Disorganization Points a unit has accrued this OpStage from CP spent OVER its
    CPA -- one DP per whole Capability Point above the allowance (0 while within CPA)."""
    return max(0, math.floor(cp_used - cpa))


def _disorganize_overage(r: _Run, side: Side, actor: str, unit_id: str,
                         old_cp: float, new_cp: float, cpa: int) -> None:
    """6.21/6.22: after a CP charge, immediately bleed Cohesion by the INCREMENTAL overage
    -- each whole CP that has just crossed the unit's CPA earns one Disorganization Point,
    credited at once (6.22, before the ensuing morale roll) through the existing COHESION_
    CHANGED channel. Only the increment is charged, so a unit already over its CPA is never
    re-penalised for CP it has already paid DP on."""
    dp = _overage_dp(new_cp, cpa) - _overage_dp(old_cp, cpa)
    if dp > 0:
        r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": unit_id, "delta": -dp})


def _spend_cp(r: _Run, side: Side, actor: str, unit, activity: str, cp: int) -> None:
    """Charge a unit `cp` Capability Points for `activity` (rule 6.3): emit CP_EXPENDED,
    which folds cp_used += cp into the same per-Operations-Stage accumulator movement
    feeds (6.14); then apply the 6.21 overage -> Disorganization consequence at once. The
    live cp_used is re-read so a second charge this stage stacks on the first."""
    old = r.state.unit(unit.id).cp_used
    r.emit(EventKind.CP_EXPENDED, side, actor,
           {"unit_id": unit.id, "activity": activity, "cp": cp})
    _disorganize_overage(r, side, actor, unit.id, old, old + cp,
                         tactics.effective_cpa(r.state, unit))


def _charge_combat_cp(r: _Run, phasing: Side, unit, charged: set[str]) -> None:
    """6.3: charge a unit its combat CP ONCE per Combat Segment. The chart's 'and/or'
    folds a unit's barrage + anti-armor + close-assault into a single charge -- a Phasing
    unit pays the 5-CP Assault, a Non-Phasing unit the 3-CP defence -- so `charged` (the
    per-segment ledger) suppresses any second charge across the barrage/anti-armor/close-
    assault seams. cp_used still accrues across BOTH players' portions of the stage (6.14)."""
    if unit.id in charged:
        return
    charged.add(unit.id)
    is_phasing = unit.side == phasing
    _spend_cp(r, unit.side, f"{unit.side.value}/Front", unit,
              "assault" if is_phasing else "defend", cp_costs.assault_cost(is_phasing))


def _combat(r: _Run, policies: dict, side: Side) -> None:
    """One Combat Segment (rule 11.0), the Phasing side = `side`. Barrage and Anti-
    Armor are fought by BOTH players (their losses land before Close Assault); then
    the Phasing player Close Assaults. Retreat-Before-Assault (13.0) slots in after
    all Barrages and before the ensuing Anti-Armor / Close Assault sub-segments
    (13.28): the NON-PHASING side may slip UNPINNED units out of contact."""
    enemy = _other(side)
    pinned: set[str] = set()          # units Pinned by barrage this segment (12.44)
    charged: set[str] = set()         # 6.3 per-segment CP ledger (one combat charge/unit)
    _air_support(r, side, pinned)     # 41.31: air strikes pin BEFORE barrage, joining the 12.44 set
    _naval_bombardment(r, side, pinned)   # 30.2: off-shore gunfire, another pre-barrage 12.44 pin
    _barrage_step(r, side, enemy, pinned, charged)
    _retreat_before_assault(r, policies[enemy], enemy, side, pinned)
    _anti_armor_step(r, side, enemy, pinned, charged)
    actor = f"{side.value}/Front"
    assaulted: set = set()            # 15.23: each hex is close-assaulted at most once/segment
    committed: set = set()            # 15.24: each unit joins at most one assault/segment
    combat_orders = policies[side].combat(r.state, side)
    _drain_staff(r, policies[side], side)     # the combat-segment deliberation
    for order in combat_orders:
        target = order.target
        # Dedupe attacker ids (else a repeated id multiplies strength), drop units
        # already committed to another assault this segment, and require is_combat
        # (an HQ costs 0 ammo and would otherwise farm assaults / Rommel's +1).
        ids = [a for a in dict.fromkeys(order.attacker_ids) if a not in committed]
        attackers = [r.state.unit(a) for a in ids]
        attackers = [u for u in attackers if u and u.alive and u.is_combat
                     and u.side == side and is_adjacent(u.hex, target)]
        defenders = list(r.state.enemies_at(target, side))
        if target in assaulted:
            r.emit(EventKind.ORDER_REJECTED, side, actor,
                   {"order": "attack", "target": list(target),
                    "reason": "hex already close-assaulted this segment"})
            continue
        if not attackers or not defenders:
            r.emit(EventKind.ORDER_REJECTED, side, actor,
                   {"order": "attack", "target": list(target),
                    "reason": "no valid attackers or empty target"})
            continue
        # 15.23/15.24: only a resolved assault locks the hex and commits its attackers.
        # A REJECTED assault (every attacker out of ammo or Pinned) spent no round, so
        # it must not burn the hex or tie down units that could still assault elsewhere.
        if _resolve_combat(r, side, actor, attackers, defenders, target, pinned, charged):
            assaulted.add(target)
            committed.update(u.id for u in attackers)


def _retreat_before_assault(r: _Run, policy: Policy, side: Side, phasing: Side,
                            pinned: set[str]) -> None:
    """Retreat Before Assault (rule 13.0): once all Barrages are complete, the NON-
    PHASING side (`side`) may pull units out of contact before the assault lands. It
    is Voluntary Movement (13.21) -- it spends CP (and Fuel for vehicles) and obeys
    enemy ZOC, break-off cost and the no-ZOC-to-ZOC rule (13.22 / 13.26) exactly as
    ordinary movement does (tactics.reachable_for already models all three). So an
    unpinned reserve can slip an assault while the Pinned garrison stays and is
    close-assaulted -- the elastic desert defense. Units Pinned by barrage, or at a
    Cohesion Level of -26 or worse, may NOT retreat before assault (13.1). Suscep-
    tibility of a unit that retreats INTO an attacked hex (13.28) is deferred."""
    actor = f"{side.value}/Front"
    enemy_zoc, enemy_occupied = tactics.enemy_zoc_and_occupied(r.state, side)
    roster = r.state.living(side)          # phase-start snapshot (matches reachability)
    for order in policy.retreat_before_assault(r.state, side, frozenset(pinned)):
        u = r.state.unit(order.unit_id)
        if u is None or not u.alive or u.side != side:
            _reject(r, side, actor, order, "no such living unit under this command",
                    order_kind="retreat_before_assault")
            continue
        if u.id in pinned:                                      # 13.1: Pinned may not retreat
            _reject(r, side, actor, order, "pinned units may not retreat before assault (13.1)",
                    order_kind="retreat_before_assault")
            continue
        if u.cohesion <= -26:                                   # 13.1: -26 or worse may not
            _reject(r, side, actor, order,
                    "cohesion -26 or worse may not retreat before assault (13.1)",
                    order_kind="retreat_before_assault")
            continue
        reach_all, prev = tactics.reachable_for_prev(r.state, u, enemy_zoc, enemy_occupied, roster)
        reach = _rba_cp_cap(r.state, u, reach_all)
        if order.to == u.hex or order.to not in reach:
            _reject(r, side, actor, order,
                    "destination unreachable within CPA or blocked by ZOC",
                    order_kind="retreat_before_assault")
            continue
        present = [x for x in r.state.units_at(order.to) if x.side == side]
        if not stacking.within_hex_limit(present + [u], r.state.terrain.terrain[order.to]):
            _reject(r, side, actor, order, "destination over stacking limit",
                    order_kind="retreat_before_assault")
            continue
        if not _draw_move_fuel(r, side, actor, u, reach[order.to], order,       # 49.13/49.16
                               order_kind="retreat_before_assault"):
            continue
        payload = {"unit_id": u.id, "from": list(u.hex), "to": list(order.to),
                   "cp_spent": reach[order.to]}
        bp = tactics.bp_for_move(r.state, u, prev, order.to)     # 21.22: reaction/retreat accrues BP
        if bp:
            payload["bp"] = bp
        old_cp = r.state.unit(u.id).cp_used
        r.emit(EventKind.UNIT_MOVED, side, actor, payload)   # 13.21: retreat-before-assault IS movement
        _disorganize_overage(r, side, actor, u.id, old_cp,       # 6.21: retreat past CPA earns DP too
                             old_cp + reach[order.to], tactics.effective_cpa(r.state, u))


def _rba_cp_cap(state: GameState, unit, reach: dict) -> dict:
    """CP ceiling on a Retreat Before Assault (13.23 / 13.24): a unit that BEGINS the
    step adjacent to an enemy combat unit may expend as many CP as it likes (13.23);
    one that does not may expend at most four CP -- or move a single hex, whichever
    is greater (13.24). The reachable set from tactics.reachable_for already bounds
    the unit's remaining CPA; this trims it to the 13.24 allowance when out of
    contact, but always leaves any directly-adjacent hex it can afford."""
    in_contact = any(e.is_combat for nb in neighbors(unit.hex)
                     for e in state.enemies_at(nb, unit.side))
    if in_contact:
        return reach
    return {c: cost for c, cost in reach.items()
            if cost <= 4.0 or distance(unit.hex, c) == 1}


def _barrage_class(u) -> str:
    return "armor" if u.is_armor else "gun" if u.is_gun else "infantry"


def _barrage_target(enemies) -> "object | None":
    """The firer bombards one target in the hex; blind, so a reasonable default is
    the strongest combat unit present."""
    combatants = [u for u in enemies if u.is_combat and u.alive]
    return max(combatants, key=lambda u: u.strength, default=None)


def _barrage_step(r: _Run, phasing: Side, enemy: Side, pinned: set[str],
                  charged: set[str]) -> None:
    """Barrage (rule 12): both sides' artillery bombard adjacent enemy hexes first,
    simultaneously (strengths read pre-loss). Each barrage resolves against one
    target unit's class on the 12.6 CRT -> Pin and/or step loss; a Pin suppresses
    that unit for the rest of the segment (no anti-armor, no close assault, 12.44).
    Terrain column-shifts and the separate truck roll (12.46) are deferred."""
    state0 = r.state
    plan: list[tuple] = []
    for firing in (phasing, enemy):
        actor = f"{firing.value}/Front"
        is_phasing = firing is phasing
        by_target: dict[Coord, list] = {}
        for u in state0.living(firing):
            if u.barrage <= 0 or not u.is_combat:
                continue
            for nb in neighbors(u.hex):
                if state0.enemies_at(nb, firing):
                    by_target.setdefault(nb, []).append(u)
                    break
        for tgt, firers in by_target.items():
            armed = [u for u in firers
                     if _charge_ammo(r, firing, actor, u, phasing=is_phasing, activity="barrage")]
            for u in armed:                              # 6.3: barrage folds into the combat CP
                _charge_combat_cp(r, phasing, u, charged)
            raw = sum(u.raw_barrage for u in armed)
            target_unit = _barrage_target(state0.enemies_at(tgt, firing))
            if raw <= 0 or target_unit is None:
                continue
            cls = _barrage_class(target_unit)
            d1, d2 = r.d6("barrage"), r.d6("barrage")
            shift = combat_tables.barrage_terrain_shift(          # 12.33 terrain / fortification
                state0.terrain.terrain[tgt], state0.fort_level(tgt), cls)
            pin, loss = combat_tables.barrage_result(
                cls, combat.actual_points(raw, False), d1 * 10 + d2, column_shift=shift)
            plan.append((firing, actor, tgt, [u.id for u in armed],
                         combat.actual_points(raw, False), cls, target_unit.id, (d1, d2), pin, loss))
    for firing, actor, tgt, firer_ids, actual, cls, tgt_id, dice, pin, loss in plan:
        r.emit(EventKind.BARRAGE_RESOLVED, firing, actor,
               {"target": list(tgt), "firers": firer_ids, "actual": actual,
                "target_class": cls, "target_unit": tgt_id, "pinned": pin, "loss": loss},
               rng_draws=dice)
        if loss > 0:
            tu = r.state.unit(tgt_id)
            if tu and tu.alive:
                r.emit(EventKind.STEP_LOST, firing, actor,
                       {"unit_id": tgt_id, "amount": min(loss, tu.strength), "role": "barrage"})
        if pin:
            pinned.add(tgt_id)
        _batter_fort(r, firing, actor, tgt, effective=pin or loss > 0)


def _batter_fort(r: _Run, firing: Side, actor: str, tgt: Coord, *, effective: bool) -> None:
    """Siege of Tobruk (rule 25.14): an EFFECTIVE artillery barrage (a Pin or a step
    loss) on a fortified hex batters its wall. After BARRAGE_HITS_PER_FORT_LEVEL such
    hits the fortification drops one level (floored at 0), emitted as FORT_REDUCED so
    the reduction folds into GameState.fort_levels and close assault reads the lower
    wall. Gated behind siege_rules -- inert (and silent) in the canonical benchmark.
    Barrage NEVER evicts and NEVER touches the static base map: only the level falls."""
    if not r.state.siege_rules or not effective or r.state.fort_level(tgt) <= 0:
        return
    r.fort_hits[tgt] = r.fort_hits.get(tgt, 0) + 1
    if r.fort_hits[tgt] >= BARRAGE_HITS_PER_FORT_LEVEL:
        r.fort_hits[tgt] = 0
        r.emit(EventKind.FORT_REDUCED, firing, actor,
               {"hex": list(tgt), "level": r.state.fort_level(tgt) - 1})


def _anti_armor_step(r: _Run, phasing: Side, enemy: Side, pinned: set[str],
                     charged: set[str]) -> None:
    """Anti-Armor Fire (rule 14): both sides fire at each other's adjacent armor,
    simultaneously (target strengths are read before any loss lands), and all armor
    losses precede Close Assault. Each unit with an Anti-Armor rating fires at one
    adjacent enemy hex holding armor, combining with others onto that target; firing
    costs ammunition (14.24). Voluntary withholding and splitting TOE between anti-
    armor and assault are deferred -- all committed armor fires and is a target."""
    state0 = r.state
    plan: list[tuple] = []
    for firing in (phasing, enemy):
        is_phasing = firing is phasing
        actor = f"{firing.value}/Front"
        by_target: dict[Coord, list] = {}
        for u in state0.living(firing):
            if u.anti_armor <= 0 or not u.is_combat or u.id in pinned:   # 12.44 pinned can't fire
                continue
            for nb in neighbors(u.hex):
                if any(t.is_armor for t in state0.enemies_at(nb, firing)):
                    by_target.setdefault(nb, []).append(u)
                    break
        for tgt, firers in by_target.items():
            armed = [u for u in firers                       # 14.24/50.2: anti-armor fire draws
                     if _charge_ammo(r, firing, actor, u, phasing=is_phasing,
                                     activity="anti_armor")]  # the anti-armor rate (3/TOE)
            for u in armed:                              # 6.3: anti-armor folds into the combat CP
                _charge_combat_cp(r, phasing, u, charged)
            raw = sum(u.raw_anti_armor for u in armed)
            if raw <= 0:
                continue
            d1, d2 = r.d6("anti_armor"), r.d6("anti_armor")
            shift = combat_tables.anti_armor_terrain_shift(      # 14.32 terrain / fortification
                state0.terrain.terrain[tgt], state0.fort_level(tgt))
            dmg = combat_tables.anti_armor_damage(combat.actual_points(raw, False),
                                                   d1 * 10 + d2, phasing=is_phasing,
                                                   terrain_shift=shift)
            plan.append((firing, actor, tgt, [u.id for u in armed], raw, (d1, d2), dmg))
    for firing, actor, tgt, firer_ids, raw, dice, dmg in plan:
        r.emit(EventKind.ANTI_ARMOR_RESOLVED, firing, actor,
               {"target": list(tgt), "firers": firer_ids, "raw": raw,
                "actual": combat.actual_points(raw, False), "damage": dmg},
               rng_draws=dice)
        _apply_armor_losses(r, firing, actor, tgt, dmg)


def _apply_armor_losses(r: _Run, firing: Side, actor: str, target: Coord, damage: int) -> None:
    """Remove armored TOE from the target hex to absorb >= `damage` Armor-Protection
    Points; each step absorbs that unit's Armor Protection rating (rule 14.42/43).
    Excess beyond destroying all armor there is ignored (14.45)."""
    remaining = damage
    for u in r.state.enemies_at(target, firing):
        if remaining <= 0:
            break
        if not u.is_armor or not u.alive:
            continue
        steps = min(u.strength, math.ceil(remaining / u.armor_protection))
        if steps > 0:
            r.emit(EventKind.STEP_LOST, firing, actor,
                   {"unit_id": u.id, "amount": steps, "role": "armor"})
            remaining -= steps * u.armor_protection


def _resolve_combat(r: _Run, side: Side, actor: str, attackers, defenders,
                    target: Coord, pinned: set[str], charged: set[str]) -> bool:
    # Ammo gates participation (rule 32.21 / 15.15) and Pin suppresses it (12.44):
    # a unit that cannot draw ammo or is Pinned cannot assault; a Pinned or unarmed
    # defender adds no defensive strength but still suffers losses. Charged before
    # resolution (conservation holds per event). Returns True if the assault RESOLVED
    # (so the caller locks the hex and commits the attackers), False if it was rejected.
    armed_atk = [u for u in attackers
                 if u.id not in pinned and u.cohesion > -26          # 6.26: -26 or worse may not attack
                 and not _waterless(u)                               # 52.51/52.52: no offensive assault when dry
                 and _charge_ammo(r, side, actor, u, phasing=True)]
    if not armed_atk:
        r.emit(EventKind.ORDER_REJECTED, side, actor,
               {"order": "attack", "target": list(target),
                "reason": "attackers out of ammo, pinned, out of water (52.51/52.52), "
                          "or Cohesion -26 or worse (6.26)"})
        return False
    for u in armed_atk:                         # 6.3: the phasing Assault CP (5), once/segment
        _charge_combat_cp(r, side, u, charged)
    # 15.15 / 15.88: an assaulted stack that is entirely out of Close-Assault ammo,
    # or whose (6.27-averaged) Cohesion has collapsed to -17 or worse, automatically
    # Surrenders the instant it is assaulted -- BEFORE it rolls morale or spends a
    # round of ammunition. This is the fix that lets a besieged, cut-off garrison
    # (a dry Tobruk) finally be forced to capitulate instead of holding at zero
    # defensive strength in perpetuity.
    if _defenders_capitulate(r, defenders):
        _resolve_surrender(r, side, actor, target, armed_atk, defenders,
                           atk_surr=False, def_surr=True, morale_shift=0, dice=())
        _award_vacate_rp(r, side, actor, armed_atk, target)        # 6.24.2
        return True
    armed_def = [u for u in defenders
                 if u.id not in pinned and _charge_ammo(r, side, actor, u, phasing=False)]
    for u in armed_def:                         # 6.3: the non-phasing defence CP (3), once/segment
        _charge_combat_cp(r, side, u, charged)

    # Close Assault via the real differential engine (rule 15 / §15.79 CRT).
    feature = r.state.terrain.hexsides.get((armed_atk[0].hex, target))  # §15.33
    fort = r.state.fort_level(target)          # §15.82 current level (25.14 may have reduced it)
    mined = target in r.state.terrain.minefields                # defensive minefield belt
    # Morale is rolled FIRST (rule 15 order): each side's 17.4 roll adjusts its
    # Basic Morale by Cohesion, and the difference shifts the assault column (15.62).
    atk_m, atk_md, atk_surr = _adjusted_morale(r, armed_atk)
    # 17.26(b): a defender whose (15.63-averaged) Basic Morale is +1 or better may NOT
    # shrug off a rolled SURR when the assaulting enemy fields at least three times
    # its strength (Enemy Raw Offensive Assault : Friendly Raw Defensive). The
    # cohesion-based 17.26(a) reprieve-void is handled inside _adjusted_morale.
    overwhelms = (sum(u.raw_offense for u in armed_atk)
                  >= 3 * sum(_def_raw(u) for u in armed_def))       # 52.51/52.52: dry defenders at half
    def_m, def_md, def_surr = _adjusted_morale(r, defenders, enemy_overwhelms=overwhelms)
    if atk_surr and def_surr:                                   # 17.25: mutual surrender is IGNORED --
        r.emit(EventKind.COMBAT_RESOLVED, side, actor,          # no assault occurs, so NO ENG (8.63)
               {"target": list(target), "attackers": [u.id for u in armed_atk],
                "defenders": [u.id for u in defenders], "surrender": "mutual-ignored",
                "differential": 0, "column": 0, "morale_shift": atk_m - def_m,
                "attacker_loss_pct": 0, "defender_loss_pct": 0,
                "attacker_captured": False, "defender_captured": False,
                "attacker_engaged": False, "retreat_hexes": 0},
               rng_draws=(*atk_md, *def_md))
        return True
    if atk_surr or def_surr:                                    # rule 17.25: the stack surrenders
        _resolve_surrender(r, side, actor, target, armed_atk, defenders,
                           atk_surr, def_surr, atk_m - def_m, (*atk_md, *def_md))
        _award_vacate_rp(r, side, actor, armed_atk, target)     # 6.24.2 (self-guards if atk surrendered)
        return True
    ab, asm, db, dsm = (r.d6("close_assault"), r.d6("close_assault"),
                        r.d6("close_assault"), r.d6("close_assault"))
    res = combat.resolve(
        attacker_raw=sum(u.raw_offense for u in armed_atk),
        defender_raw=sum(_def_raw(u) for u in armed_def),      # unarmed -> 0; dry -> half (52.51/52.52)
        # 15.12/15.15: pinned + out-of-ammo defenders add no Ratings to defender_raw
        # (the differential/15.51 shift) but their TOE strengths ARE in the casualty pool.
        defender_loss_raw=sum(u.raw_defense for u in defenders),
        def_terrain=r.state.terrain.terrain[target], attack_feature=feature,
        atk_roll=ab * 10 + asm, def_roll=db * 10 + dsm,
        morale_shift=atk_m - def_m,
        attacker_ca_penalty=_combined_arms_penalty(armed_atk),      # rule 15.4
        defender_ca_penalty=_combined_arms_penalty(armed_def),
        attacker_size=max((u.stacking_points for u in armed_atk), default=0),  # 15.53
        defender_size=max((u.stacking_points for u in defenders), default=0),  # incl. pinned (15.12)
        fortification_level=fort, in_enemy_minefield=mined)
    r.emit(EventKind.COMBAT_RESOLVED, side, actor,
           {"target": list(target), "attackers": [u.id for u in armed_atk],
            "defenders": [u.id for u in defenders],
            "differential": res.differential, "column": res.column,
            "morale_shift": atk_m - def_m,
            "attacker_loss_pct": res.attacker_loss_pct,
            "defender_loss_pct": res.defender_loss_pct,
            "attacker_captured": res.attacker_captured,
            "defender_captured": res.defender_captured,
            "attacker_engaged": res.attacker_engaged,
            "retreat_hexes": res.retreat_hexes},
           rng_draws=(*atk_md, *def_md, ab, asm, db, dsm))
    # 15.83d: steps are removed to ABSORB the raw points lost, each step soaking up
    # its unit's close-assault rating (dca defending, oca attacking) worth of points.
    for uid, amount in _absorb_losses(defenders, res.defender_points_lost, lambda u: u.dca):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "defender"})
    for uid, amount in _absorb_losses(armed_atk, res.attacker_points_lost, lambda u: u.oca):
        r.emit(EventKind.STEP_LOST, side, actor,
               {"unit_id": uid, "amount": amount, "role": "attacker"})
    # Cohesion: 30%+ losses disorganize the involved units (6.21b/15.29b), -3 each. A
    # winning attacker recovers this via the 6.24.2 award below (a costly victory nets 0).
    if res.attacker_loss_pct >= 30:
        for u in armed_atk:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -3})
    if res.defender_loss_pct >= 30:
        for u in defenders:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -3})
    if res.retreat_hexes > 0:                                   # rule 15.8 / 15.82
        _retreat(r, side, actor, [d.id for d in defenders], armed_atk[0].hex, res.retreat_hexes)
    _award_vacate_rp(r, side, actor, armed_atk, target)        # 6.24.2: RP if the hex is now empty
    return True


def _award_vacate_rp(r: _Run, side: Side, actor: str, attackers, target: Coord) -> None:
    """6.24.2: each attacker whose Close Assault leaves the defender's hex COMPLETELY
    vacated -- the defenders eliminated or retreated as a direct result of THIS assault
    (Reaction and Retreat Before Assault, 8.5 / 13.0, never reach here) -- earns three
    Reorganization Points, a Cohesion gain capped at the 6.23 +10 ceiling. This is the
    counter-weight that lets a WINNING stack climb back out of Disorganization; without it
    Cohesion was a one-way ratchet and only CP-idle units (6.24.1) ever recovered."""
    if any(u.is_combat and u.alive for u in r.state.enemies_at(target, side)):
        return                                          # the defender still holds -- hex not vacated
    for u in attackers:
        live = r.state.unit(u.id)
        if live is None or not live.alive:
            continue                                    # a destroyed attacker earns nothing
        gain = min(3, 10 - live.cohesion)               # 6.23: Cohesion may never exceed +10
        if gain > 0:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": gain})


def _combined_arms_penalty(units) -> int:
    """Combined arms (rule 15.4): tanks unsupported by an equal TOE of infantry /
    MG / heavy-weapons units lose Actual close-assault points -- 1 for every 1-3
    unsupported tank TOE points, capped at 4. Tanks only (recce and SP artillery,
    which have Armor Protection but are not tanks, are exempt). Off and def alike."""
    tank_toe = sum(u.strength for u in units if u.is_tank)
    if tank_toe == 0:
        return 0
    support = sum(u.strength for u in units
                  if u.is_combat and not u.is_tank and not u.is_armor and not u.is_gun)
    unsupported = max(0, tank_toe - support)
    return min(4, math.ceil(unsupported / 3))


def _largest_units(units):
    """6.27's 'largest unit rule': the largest units in a Close Assault -- those with the
    most Stacking Points (organizational size: division, brigade, ...). BOTH the Cohesion
    (6.27) and the Basic Morale (15.63) the stack fights at are read off exactly this set:
    when one unit is largest it alone prevails, and when several tie for largest their
    levels are averaged. Every CNA combat counter is one Stacking Point, so a multi-unit
    stack is always a tie and every counter contributes."""
    live = [u for u in units if u.strength > 0]
    if not live:
        return []
    top = max(u.stacking_points for u in live)
    return [u for u in live if u.stacking_points == top]


def _stack_cohesion(units) -> int:
    """6.27 (invoked by 17.27): the Cohesion Level a Close-Assault stack fights at -- the
    largest unit's level, or the average over the largest units when several tie, rounded
    to the nearest whole number. Worked example (6.27): three brigades at -4, -1, +3 ->
    (-4 -1 +3)/3 = -0.667 -> -1. Averaging replaces reading the single strongest unit's
    Cohesion, which let one shattered counter drag an otherwise-steady stack past the
    17.24 '-17 et seq' Surrender floor."""
    largest = _largest_units(units)
    if not largest:
        return 0
    return round(sum(u.cohesion for u in largest) / len(largest))


def _stack_morale(units) -> int:
    """15.63: the Basic Morale a Close-Assault stack fights at uses the SAME largest-unit
    rule (6.27) as Cohesion -- the largest unit's Morale prevails, and when several tie for
    largest their Morale Ratings are averaged, rounded to the nearest whole number. Worked
    example (15.64c, read off the scan p24): the 15th Panzer (+3) and the Ariete (+1), both
    divisions, fight at (+3 +1)/2 = +2; with a single largest unit (15.64d, the 2 NZ
    Division) it lends its own Morale and an attached smaller battalion contributes nothing.
    Reading only the single strongest unit's Morale was the un-ported half of 15.63/17.27."""
    largest = _largest_units(units)
    if not largest:
        return 0
    return round(sum(u.morale for u in largest) / len(largest))


def _honors_surrender(morale: int, cohesion: int, enemy_overwhelms: bool) -> bool:
    """Does a rolled SURR (17.4 Surrender column) actually stick? By 17.25 the stack
    Surrenders -- UNLESS its Basic Morale (17.26's '(individual or combined)', i.e. the
    15.63-averaged Morale of the largest units) is +1 or better, in which case 17.26 lets
    it treat the SURR as a mere -4 adjustment and fight on. That reprieve is voided, and
    the Surrender enforced, when either 17.26 exception holds:
    (a) the unit's Cohesion has collapsed to -11 or worse, or (b) the assaulting enemy
    brings at least three times the strength (Enemy Raw Offensive : Friendly Raw
    Defensive), passed in as `enemy_overwhelms`."""
    if morale < 1:
        return True
    return cohesion <= -11 or enemy_overwhelms


def _adjusted_morale(r: _Run, units, *,
                     enemy_overwhelms: bool = False) -> tuple[int, tuple[int, int], bool]:
    """Adjusted Morale of a close-assault stack (rule 15.6): the stack's Basic Morale
    (15.63/6.27 -- averaged over the largest units, NOT the single strongest) plus the 17.4
    modifier rolled at its 6.27-averaged Cohesion, clamped to -3..+3 (17.23), THEN General
    Rommel's +1 (17.28) added OUTSIDE that clamp -- the one explicit 17.23 exception, so a
    +3 unit stacked with Rommel reaches +4. Returns (morale, the two dice, surrendered). A
    SURR result eliminates the stack (17.25); the 17.26 reprieve and its (a) cohesion /
    (b) enemy-3x exceptions are decided by _honors_surrender. When SURR is shrugged off it
    counts as the -4 penalty."""
    live = [u for u in units if u.strength > 0]
    if not live:
        return 0, (0, 0), False
    morale = _stack_morale(live)                         # 15.63/6.27: averaged over largest units
    cohesion = _stack_cohesion(live)                     # 17.27/6.27: averaged over largest units
    largest = max(live, key=lambda u: (u.stacking_points, u.strength))   # 17.28 Rommel-hex probe
    d1, d2 = r.d6("morale"), r.d6("morale")
    mod = combat_tables.morale_modifier(cohesion, d1 * 10 + d2)
    surrendered = mod == "SURR" and _honors_surrender(morale, cohesion, enemy_overwhelms)
    if mod == "SURR":
        mod = -4
    m = max(-3, min(3, morale + mod))                  # 17.23: clamp the Adjusted Morale FIRST
    rom = r.state.rommel                               # 17.28: then add Rommel's +1 OUTSIDE the
    if (rom is not None and not rom.in_germany         # clamp, keyed on his ENTITY position (not
            and largest.side == Side.AXIS              # an is_combat-filtered Unit id-scan), so it
            and rom.hex == largest.hex):               # lands on attacking stacks too and can break
        m += 1                                         # the +3 ceiling (17.23 exception)
    return m, (d1, d2), surrendered


def _resolve_surrender(r: _Run, side: Side, actor: str, target: Coord, attackers,
                       defenders, atk_surr: bool, def_surr: bool,
                       morale_shift: int, dice: tuple) -> None:
    """A side whose morale collapses to Surrender (17.25) is eliminated in place.
    Recorded as a normal COMBAT_RESOLVED + STEP_LOST so replay + conservation hold."""
    surr = "both" if (atk_surr and def_surr) else "attacker" if atk_surr else "defender"
    r.emit(EventKind.COMBAT_RESOLVED, side, actor,
           {"target": list(target), "attackers": [u.id for u in attackers],
            "defenders": [u.id for u in defenders], "surrender": surr,
            "differential": 0, "column": 0, "morale_shift": morale_shift,
            "attacker_loss_pct": 0, "defender_loss_pct": 0,
            "attacker_captured": False, "defender_captured": False,
            "attacker_engaged": False, "retreat_hexes": 0},
           rng_draws=dice)
    for u in (attackers if atk_surr else []) + (defenders if def_surr else []):
        cur = r.state.unit(u.id)
        if cur and cur.alive:
            r.emit(EventKind.STEP_LOST, side, actor,
                   {"unit_id": u.id, "amount": cur.strength, "role": "surrender"})


def _retreat(r: _Run, atk_side: Side, actor: str, defender_ids: list[str],
             attacker_hex: Coord, n: int) -> None:
    """Retreat the surviving defenders n hexes away from the attacker, toward the
    nearest friendly supply/city, never into enemy ZOC or enemy units (rule 15.82);
    each hex that cannot be retreated costs an extra 10% loss. The stack retreats
    together. Retreat CP cost (15.82) is not charged yet (flagged)."""
    survivors = [u for u in (r.state.unit(uid) for uid in defender_ids) if u and u.alive]
    if not survivors:
        return
    # Rule 15.82: a unit invested in a MAJOR CITY is not evicted -- it holds the
    # city (Tobruk/Bardia sit out the siege) rather than retreat or take losses.
    if r.state.terrain.terrain.get(survivors[0].hex) == Terrain.MAJOR_CITY:
        return
    def_side = survivors[0].side
    enemy_zoc, enemy_occ = tactics.enemy_zoc_and_occupied(r.state, def_side)
    friendly = frozenset(u.hex for u in r.state.living(def_side))
    blocked = (enemy_zoc - friendly) | enemy_occ
    supplies = [s.hex for s in r.state.active_supplies(def_side)]

    surv_ids = {u.id for u in survivors}

    def _fits(nb: Coord) -> bool:                    # the retreating stack must fit (rule 9.31)
        here = [x for x in r.state.units_at(nb) if x.side == def_side and x.id not in surv_ids]
        return stacking.within_hex_limit(here + survivors, r.state.terrain.terrain[nb])

    cur = survivors[0].hex
    path = [cur]                                      # the hexes crossed, for Breakdown Points
    done = 0
    for _ in range(n):
        cands = [nb for nb in neighbors(cur)
                 if nb in r.state.terrain.terrain and nb not in blocked
                 and distance(nb, attacker_hex) > distance(cur, attacker_hex)
                 and _fits(nb)]
        if not cands:
            break
        occupied = frozenset(u.hex for u in r.state.living(def_side))

        def _key(nb):
            sup = min((distance(nb, s) for s in supplies), default=0)
            return (nb in occupied, sup, -distance(nb, attacker_hex), nb)
        cur = min(cands, key=_key)
        path.append(cur)
        done += 1

    if done > 0:
        for u in survivors:
            payload = {"unit_id": u.id, "from": list(u.hex), "to": list(cur), "hexes": done}
            bp = tactics.breakdown_points_over(r.state, u, path)    # 21.22 retreat accrues BP
            if bp:
                payload["bp"] = bp
            r.emit(EventKind.UNIT_RETREATED, atk_side, actor, payload)
    for _ in range(n - done):                                   # 15.82: 10% per un-retreated hex
        for u in survivors:
            cur_u = r.state.unit(u.id)
            extra = math.ceil(0.10 * cur_u.strength)
            if extra > 0:
                r.emit(EventKind.STEP_LOST, atk_side, actor,
                       {"unit_id": u.id, "amount": min(extra, cur_u.strength), "role": "defender"})


def _has_ammo(state: GameState, unit, *, phasing: bool) -> bool:
    """Can this unit draw its Close-Assault ammunition right now IN ITS HEX (rule 50.15)?
    A non-mutating mirror of the _charge_ammo supply gate, used to detect the 15.15
    all-out-of-ammunition condition without expending anything: True iff the unit's own
    50.0 basic load plus any co-located dump can cover one assault (49.16)."""
    return supply.in_hex_draw(state, unit, supply.AMMO,
                              supply.ammo_cost(unit, phasing=phasing, activity="assault")) is not None


def _defenders_capitulate(r: _Run, defenders) -> bool:
    """Hard surrender thresholds on an assaulted defending stack, ahead of the 17.4
    roll (15.88 -- units so afflicted automatically Surrender). Returns True when:
      - 15.15: EVERY defender is out of Close-Assault ammunition, so a cut-off, dry
        garrison capitulates en masse rather than defend on at zero strength; or
      - 15.88: the stack's (6.27-averaged) Cohesion has collapsed to -17 or worse
        (17.24 '-17 et seq'; 17.27 Largest Unit Rule -> 6.27)."""
    live = [u for u in defenders if u.strength > 0]
    if not live:
        return False
    if _stack_cohesion(live) <= -17:                      # 15.88 / 17.24 / 17.27 -> 6.27 averaged
        return True
    return all(not _has_ammo(r.state, u, phasing=False) for u in live)  # 15.15


def _charge_ammo(r: _Run, side: Side, actor: str, unit, *, phasing: bool,
                 activity: str = "assault") -> bool:
    """Expend this unit's ammunition for `activity` (rule 50.14), drawn IN THE HEX (50.15: "consumed
    only if present in the hex") -- its own 50.0 basic load first (49.16), then a co-located dump --
    NOT the abstract 32.16 trace. There is no supply range: a unit whose hex cannot cover the cost
    has fired out its load and cannot fire (50.12), and this returns False. Emits UNIT_SUPPLY_CONSUMED
    off its own load / SUPPLY_CONSUMED off a co-located dump, exactly like _draw_move_fuel does fuel."""
    draws = supply.in_hex_draw(r.state, unit, supply.AMMO,
                               supply.ammo_cost(unit, phasing=phasing, activity=activity))
    if draws is None:
        return False
    for tag, ref_id, qty in draws:
        if tag == "unit":
            r.emit(EventKind.UNIT_SUPPLY_CONSUMED, side, actor,
                   {"unit_id": ref_id, "commodity": supply.AMMO, "qty": qty})
        else:                                          # "dump" -- a co-located dump (54.11/54.15)
            r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                   {"supply_id": ref_id, "commodity": supply.AMMO, "qty": qty, "unit_id": unit.id})
    return True


def _absorb_losses(units, points: int, rating_of) -> list[tuple[str, int]]:
    """Rule 15.83d: remove enough TOE steps to ABSORB the raw points lost. Each step
    soaks up its unit's close-assault rating worth of raw points, so a high-rated
    (elite) unit sheds fewer steps than a weak one for the same points. Steps come
    off the largest units first; a fractional remainder still costs a whole step
    (enough must be removed to fully absorb the loss). Units with no rating cannot
    absorb (they contribute nothing to the raw total either)."""
    out: list[tuple[str, int]] = []
    remaining = points
    for u in sorted(units, key=lambda x: -x.strength):
        if remaining <= 0:
            break
        rating = rating_of(u)
        if rating <= 0 or u.strength <= 0:
            continue
        take = min(u.strength, math.ceil(remaining / rating))
        out.append((u.id, take))
        remaining -= take * rating
    return out


def _record_control(r: _Run) -> None:
    # Group combat units by hex ONCE (O(units)) instead of scanning every unit for every
    # terrain hex (O(hexes x units)). The terrain dict is then iterated in its original order,
    # skipping unoccupied hexes -- so HEX_CONTROL_CHANGED emission order is byte-for-byte as before.
    by_hex: dict[Coord, list] = {}
    for u in r.state.units:
        if u.is_combat and r.state.on_map(u):                      # only combat units hold ground
            by_hex.setdefault(u.hex, []).append(u)
    for coord in r.state.terrain.terrain:
        occ = by_hex.get(coord)
        if not occ:
            continue
        sides = {u.side for u in occ}
        new = CONTROL_OF[next(iter(sides))] if len(sides) == 1 else r.state.control_of(coord)
        if new != r.state.control_of(coord):
            r.emit(EventKind.HEX_CONTROL_CHANGED, Side.SYSTEM, "SYSTEM",
                   {"coord": list(coord), "control": new.value})


BARDIA: Coord = (20, 77)          # C4321, east of Tobruk -> Axis Decisive Victory (61.8)


def _degree_of_success(r: _Run) -> tuple[int, int, bool, bool]:
    """The Axis high-water mark toward Tobruk, as a graded signal (rule 61.8 is a
    binary hold, but this scenario's interest is HOW FAR the Axis got -- the Race
    for Tobruk). Returns (advance %, closest-reach hexes, holds Tobruk, holds
    Bardia). Advance % = fraction of the opening Axis->Tobruk gap closed by the
    furthest Axis-controlled or Axis-occupied hex."""
    s = r.state
    tobruk = s.target_hex
    axis = [h for h, c in s.control.items() if c == Control.AXIS]
    axis += [u.hex for u in s.living(Side.AXIS)]
    reach = min((distance(h, tobruk) for h in axis), default=99)
    start = min((distance(u.hex, tobruk) for u in r.initial.living(Side.AXIS)), default=99)
    advance = max(0, min(100, round(100 * (start - reach) / max(1, start))))
    return advance, reach, s.control_of(tobruk) == Control.AXIS, s.control_of(BARDIA) == Control.AXIS


def _axis_win_reason(holds_bardia: bool) -> str:
    return ("Axis Decisive Victory: Tobruk and Bardia held (61.8)" if holds_bardia
            else "Axis Victory: Tobruk captured and held (61.8)")


def _victory(r: _Run) -> tuple[Side | None, str]:
    s = r.state
    advance, reach, holds_tobruk, holds_bardia = _degree_of_success(r)
    r.emit(EventKind.VICTORY_CHECKED, Side.SYSTEM, "SYSTEM",
           {"axis": advance, "allied": 100 - advance, "axis_reach": reach})
    if holds_tobruk:
        return Side.AXIS, _axis_win_reason(holds_bardia)
    if not s.living(Side.ALLIED):
        return Side.AXIS, "Axis victory by annihilation"
    if not s.living(Side.AXIS):
        return Side.ALLIED, "Allied victory by annihilation"
    return None, ""


def _final_decision(r: _Run) -> tuple[Side, str]:
    advance, reach, holds_tobruk, holds_bardia = _degree_of_success(r)
    if holds_tobruk:
        return Side.AXIS, _axis_win_reason(holds_bardia)
    if reach <= 2:
        return Side.ALLIED, f"Commonwealth marginal victory: Tobruk held but invested (Axis {advance}% of the way)"
    if advance >= 50:
        return Side.ALLIED, f"Commonwealth victory: Tobruk held, Axis reached within {reach} hexes ({advance}% advance)"
    return Side.ALLIED, f"Commonwealth decisive victory: Axis advance stalled {reach} hexes short ({advance}% advance)"


class VictorySpec(Protocol):
    """A scenario's victory conditions as a strategy (rules 61.8 / 64.7). `check` is
    the per-turn test run every Record Phase (the auto-win; returns the winning Side
    or None to play on); `decide` is the terminal tally at max_turns (always names a
    winner). Both receive the live `_Run` so a spec may read the full board, emit its
    own events, and remember across checks in `_Run.victory_scratch` (64.71's hold
    clock). A scenario selects a spec via GameState.victory; None routes to
    _DEFAULT_VICTORY below."""

    def check(self, r: "_Run") -> tuple["Side | None", str]: ...

    def decide(self, r: "_Run") -> tuple["Side | None", str]: ...   # None = draw (rule 64.76)


class _ScenarioVictory:
    """The engine's built-in Race-for-Tobruk victory (rule 61.8): capture-and-hold
    Tobruk or annihilate per turn, else a graded advance tally at the final turn.
    This is the default for every scenario that does not name its own spec, so the
    two benchmark scenarios stay byte-identical (check/decide delegate verbatim to
    the module functions _victory / _final_decision)."""

    def check(self, r: "_Run") -> tuple["Side | None", str]:
        return _victory(r)

    def decide(self, r: "_Run") -> tuple["Side", str]:
        return _final_decision(r)


_DEFAULT_VICTORY = _ScenarioVictory()


def determinism_signature(events: list[Event]) -> str:
    from .events import log_to_json
    return log_to_json(events)
