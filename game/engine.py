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
import random
from dataclasses import dataclass

from . import combat, combat_tables, cp_costs, logistics_data, stacking, supply, tactics, weather
from .apply import apply
from .events import Control, Event, EventKind, Phase, Side
from .hexmap import distance, is_adjacent, neighbors
from .invariants import check
from .policy import AttackOrder, MoveOrder, Policy
from .staff_events import clean_staff_payload
from .state import Coord, GameState
from .terrain import Mobility, Terrain

CONTROL_OF: dict[Side, Control] = {Side.AXIS: Control.AXIS, Side.ALLIED: Control.ALLIED}

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

# 55.2 harbour BLOCKING (a scuttled ship) permanently cripples a port until Friendly
# engineers clear the wreck (55.26) -- it is NOT bomb damage, so the 55.18 +1/OpStage
# regeneration does NOT restore it. The San Giorgio scuttled in Tobruk (30.17 / 55.25,
# -3 levels) is such a block: it stays pinned at its seeded Efficiency Level. (The Axis
# rear harbour in the Desert Fox corridor is the WORKING PORT-Tripoli, not the scuttled
# Benghazi -- Step 5 -- so no Axis port is blocked here.)
# Bomb/mine reductions (41.3), which DO regenerate, arrive with the air subsystem (CHUNK 6).
HARBOUR_BLOCKED: frozenset = frozenset({"PORT-Tobruk"})


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
        self.rng = random.Random(initial.seed)
        self.events: list[Event] = []
        self._seq = 0
        self.fort_hits: dict[Coord, int] = {}   # accumulated barrage hits per hex (25.14)

    def emit(self, kind: EventKind, side: Side, actor: str, payload: dict,
             rng_draws: tuple[int, ...] = ()) -> None:
        e = Event(self._seq, self.state.turn, self.state.phase, side, actor,
                  kind, payload, rng_draws, self.state.stage)   # stamp the Operations Stage (5.1)
        self._seq += 1
        self.state = apply(self.state, e)
        check(self.state)
        self.events.append(e)

    def d6(self) -> int:
        return self.rng.randint(1, 6)

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
            _rommel_anchor(r)                            # 31.4: snapshot who he starts THIS stage with
            first, second = _declare_ab(r, policies, stage)   # 5.2.III.A / 7.11: the A/B activation order
            r.go(Phase.WEATHER, Side.SYSTEM)
            _weather(r)                                 # 29.0: weather is rolled per Operations Stage
            _water_body(r)                              # 48 V.C.1: water draw + the +5% hot-evap slice
            if stage == 1:                              # 48 V.D: arrivals land once, in the turn's 1st stage
                _reinforcements(r)
                _naval_convoys(r, policies)             # V.C.7 + V.D: convoy arrival + port regen (SYSTEM)
            _air_superiority(r)                          # 40/45/46: contest the sky this OpStage (per arena)
            for side in (first, second):                # 7.16: Player A (first) then Player B (last)
                _debrief(side)                          # enemy portion + own last combat
                _reserve_designation(r, policies[side], side)   # 48 V.G / 18.11: hold units back (phasing)
                r.go(Phase.MOVEMENT, side)
                _movement(r, policies, side)            # segment 0 (ungated); Reaction (8.5) rides inside
                _rommel_move(r, policies[side], side)   # 31.1: the leader repositions (Axis only, self-guarded)
                _breakdown(r, side)                     # 21.24: check vehicles that ceased moving
                _supply_movement(r, policies[side], side)   # supply follows the army (32.3)
                _debrief(side)                          # which moves/pincers actually formed
                r.go(Phase.COMBAT, side)
                _combat(r, policies, side)
                _breakdown(r, _other(side))             # 21.22: the enemy's retreats accrued BP too
                _repair(r, side)                        # 22.12: the phasing side's Repair Phase
                _continual_movement(r, policies, side)  # 8.2/8.23 + 18.13: the exploitation pulse loop
            for side in (first, second):
                _truck_convoys(r, policies[side], side)  # V.J: 2nd/3rd-line truck convoys (48)
            r.go(Phase.RECORD, Side.SYSTEM)
            _record_control(r)
            winner, reason = _victory(r)
            if winner is not None:
                done = True
                break
            if stage == 3 and r.state.turn >= r.state.max_turns:
                winner, reason = _final_decision(r)
                done = True
                break
            _idle_recovery(r)                           # 6.24.1: reward a CP-idle stage (before the reset)
            if stage < 3:                               # next Operations Stage: refresh the CPA window (6.16)
                r.emit(EventKind.STAGE_ADVANCED, Side.SYSTEM, "SYSTEM", {"stage": stage + 1})
            else:                                       # a new game-turn re-opens at Operations Stage 1
                r.emit(EventKind.TURN_ADVANCED, Side.SYSTEM, "SYSTEM", {"turn": r.state.turn + 1})

    return RunResult(r.initial, r.events, r.state, winner, reason)


# --- initiative (rule 7) -----------------------------------------------------

def _initiative(r: _Run, axis_recalled: bool = False) -> None:
    """Initiative Determination (rule 5.2 I / 7.14), once per GAME-TURN. While the scenario
    fixes the holder (7.15 / 61.5: e.g. Axis through GT27) no die is rolled; otherwise each
    side rolls 1 die + its Initiative Rating and the higher total wins, ties rerolled in the
    seeded stream (7.14). Folds into GameState.initiative_side, held for all three Operations
    Stages (7.12). The 7.2 Initiative Ratings are an untranscribed chart -- initiative_ratings
    is a representative PROXY (flagged in scenario.py).

    `axis_recalled` fires on the game-turn General Rommel's Berlin recall sent him to Germany
    (31): the Axis Initiative Rating is clamped to min(rating, 3) AND the 7.15 predetermined
    hold is suspended so the determination is actually ROLLED -- so 'Axis Initiative falls to
    3' genuinely bites even in the fixed window, and can only ever HURT the Axis."""
    s = r.state
    if not axis_recalled and s.initiative_fixed is not None and s.turn <= s.initiative_fixed_until:
        r.emit(EventKind.INITIATIVE_DETERMINED, Side.SYSTEM, "SYSTEM",
               {"side": s.initiative_fixed.value, "fixed": True})     # 7.15: predetermined, no die
        return
    ax_rating = s.initiative_ratings.get("AXIS", 0)
    if axis_recalled:
        ax_rating = min(ax_rating, 3)                    # 31 Berlin recall: Axis Initiative falls to 3
    al_rating = s.initiative_ratings.get("ALLIED", 0)
    draws: list[int] = []
    while True:                                          # 7.14: ties reroll
        ad, ld = r.d6(), r.d6()
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
    d1, d2 = r.d6(), r.d6()
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
    `rng` ONLY when an InterdictionOrder covers this lane+turn, so an interdiction-free lane
    draws no rng and returns the cargo verbatim with dice=() (byte-identical). The dice ride out
    so the CONVOY_INTERDICTED marker can certify them in the log."""
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
    InterdictionOrder covers this convoy's lane this game-turn, the cargo arrives verbatim
    and NO die is drawn (byte-identical). Otherwise the seam rolls 2d6 on the [41.5] Air
    Bombardment CRT (41.66) and skims that tens-of-percent off the cargo (41.67, split evenly,
    each LOST amount rounded up) before it lands. Returns the (possibly reduced) cargo; the
    paired CONVOY_INTERDICTED marker rides in _naval_convoys beside the smaller SUPPLY_ARRIVED."""
    return _interdict(convoy, state, rng)[0]         # cargo only; the marker's dice ride separately


def _naval_convoys(r: _Run, policies: dict | None = None) -> None:
    """Naval Convoy Arrival (rule 48 V.C.7 Tactical Shipping + V.D Convoy Arrival): the
    supply SOURCE lands each due convoy's cargo into its destination dump, capped at the
    dump capacity (32.15 -- overflow is simply never credited, a miniature port throttle,
    CHUNK 3 makes it the real 55.14 efficiency gauge). A convoy to an enemy-captured port
    never sails (56.15). Fires ONLY when convoys are due this game-turn, so every convoy-
    less scenario stays byte-identical (no Phase.LOGISTICS is emitted).

    `policies` (optional, backward-compatibly None for the scripted callers) hands the naval
    seat its per-turn interdiction allocation (P5 Step 6): before the convoys run the gauntlet,
    each side's Convoy officer commits the seeded schedule as a CONTINGENT command decision,
    whose STAFF_* beats the engine drains just before the CONVOY_INTERDICTED markers they
    explain. A policy without a naval seat (every scripted policy) stages nothing, so the
    interdiction stays exactly as ambient as before -- byte-identical."""
    due = [c for c in r.state.convoys if c.arrival_turn == r.state.turn]
    regenable = [p for p in r.state.ports
                 if p.id not in HARBOUR_BLOCKED and p.eff < p.max_eff]
    if not due and not regenable:
        return                                          # convoy-/port-less stays byte-identical
    r.go(Phase.LOGISTICS, Side.SYSTEM)
    if policies is not None:                            # the naval command loop (early-return-guarded)
        for side in (Side.AXIS, Side.ALLIED):
            pol = policies[side]
            if hasattr(pol, "naval_command"):
                pol.naval_command(r.state, side)        # stages the officer's interdiction beats
                _drain_staff(r, pol, side)              # emitted before the CONVOY_INTERDICTED below
    port_landed: dict[tuple[str, str], int] = {}        # 55.14: cap is per-port-per-OpStage, not per-convoy
    for c in sorted(due, key=lambda c: c.id):           # deterministic arrival order
        dump = r.state.supply(c.dest)
        enemy_ctrl = CONTROL_OF[_other(c.side)]
        if dump is None or r.state.control_of(dump.hex) == enemy_ctrl:   # 56.15
            r.emit(EventKind.CONVOY_CANCELLED, c.side, "SYSTEM",
                   {"convoy_id": c.id, "lane": c.lane, "dest": c.dest, "reason": "port captured"})
            continue
        # 41.6/32.66: skim the CRT loss at sea BEFORE landing (identity + no rng if unbombed)
        cargo, itd_order, pct_lost, tons_lost, itd_dice = _interdict(c, r.state, r.rng)
        cap = supply.dump_capacity(r.state.terrain.terrain[dump.hex])   # 54.12, keyed by dump terrain
        port = r.state.port_at(dump.hex)                # 56.28: a port's built-in dump
        landed: dict = {}
        for k, v in cargo.items():
            onhand = getattr(dump, k.lower())
            room = min(cap[k], onhand + v) - onhand     # 54.12 dump headroom
            if port is not None:
                # 55.14 harbour throttle: several convoys sharing one port this OpStage draw
                # from ONE cap, so subtract what earlier convoys already landed there.
                already = port_landed.get((port.id, k), 0)
                room = min(room, supply.port_landing_cap(port, k) - already)
            if room > 0:
                landed[k] = room
        if port is not None:
            for k, q in landed.items():
                port_landed[(port.id, k)] = port_landed.get((port.id, k), 0) + q
        if port is not None:                            # legible per-commodity landing beat
            for k in sorted(landed):
                r.emit(EventKind.PORT_UNLOADED, c.side, "SYSTEM",
                       {"port_id": port.id, "commodity": k, "qty": landed[k],
                        "tons": supply.points_to_tons(landed[k], k), "eff": port.eff})
        if landed:                                      # nothing to land into a full dump
            r.emit(EventKind.SUPPLY_ARRIVED, c.side, "SYSTEM",
                   {"supply_id": c.dest, "cargo": landed, "lane": c.lane, "convoy_id": c.id})
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
    _port_regen(r)      # 55.18: the port worked this OpStage at its current eff, then recovers


def _port_regen(r: _Run) -> None:
    """55.18: every port regains one Efficiency Level per OpStage (up to its assigned
    maximum), emitted as PORT_EFFICIENCY_CHANGED -- except a permanent harbour BLOCK
    (HARBOUR_BLOCKED: San Giorgio, scuttled Benghazi), which only engineers clear (55.26).
    Deterministic (sorted by id). No bomb/mine reductions exist yet (CHUNK 6), so in the
    current scenarios only bomb-free ports below max would climb -- the seeded blocks stay."""
    for p in sorted(r.state.ports, key=lambda p: p.id):
        if p.id in HARBOUR_BLOCKED:
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
    STORES from the traced dumps, with the 51.21 disorganization + 51.22 attrition on a
    sustained shortfall, and the 52.6 Pasta Point."""
    _stores_expenditure(r, side, hot)


def _water_stage(r: _Run, side: Side, hot: bool) -> None:
    """A side's Water Distribution (rule 48 V.C.1 / 52, faithfully per OPERATIONS STAGE): draw
    WATER from the traced dumps, with the 52.53 shortfall attrition. The dual of _stores_stage."""
    _water_distribution(r, side, hot)


_EVAP = logistics_data.evaporation_percent()   # 49.3/52.44, from the rulebook


def _evaporate(r: _Run, pct: int) -> None:
    """49.3 / 52.44: on-map Fuel and Water lose `pct`% (rounded down) to evaporation & spillage.
    A SINK into consumed[] (the 9% Sep40-Aug41 Commonwealth container rate is deferred). The
    6% base (once per game-turn) and the +5% hot slice (per Operations Stage) are charged as
    SEPARATE calls under the faithful clock. Deterministic: sorted dumps, fuel then water."""
    if pct <= 0:
        return
    for sid in sorted(su.id for su in r.state.supplies):
        for commodity in (supply.FUEL, supply.WATER):
            amt = getattr(r.state.supply(sid), commodity.lower())
            loss = amt * pct // 100
            if loss > 0:
                r.emit(EventKind.SUPPLY_EVAPORATED, Side.SYSTEM, "SYSTEM",
                       {"supply_id": sid, "commodity": commodity, "qty": loss})


def _stores_expenditure(r: _Run, side: Side, hot: bool) -> None:
    actor = f"{side.value}/Logistics"
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        draws = supply.plan_draw(r.state, u, supply.STORES, supply.stores_cost(u))
        if draws is None:
            _stores_shortfall(r, side, actor, u)        # 51.21/51.22
            continue
        for sid, qty in draws:
            r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                   {"supply_id": sid, "commodity": supply.STORES, "qty": qty, "unit_id": u.id})
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


def _weather(r: _Run) -> None:
    """Weather Determination (rule 29.1): the season (from the Game-Turn) selects the
    29.61 Weather Table row; a sequential 2d6 gives the weather type. A foul result
    (sandstorm/rainstorm) rolls one more die on the 29.7 Foul Weather Location Table for
    the affected map sections -- if none of the scenario's own sections are hit, the
    theater stays Normal (29.1: unaffected sections have normal weather). Hot occurs on
    every section (29.31), so it needs no location roll. The single emitted label is
    what every downstream coupling (breakdown shift, evaporation, movement cost) reads."""
    season = weather.season_for_turn(r.state.turn)
    d1, d2 = r.d6(), r.d6()
    label = weather.weather_for_roll(season, d1 * 10 + d2)
    draws = (d1, d2)
    sections: frozenset = frozenset()
    if weather.is_foul(label):
        d3 = r.d6()
        draws = (d1, d2, d3)
        sections = weather.foul_sections(d3)
        theater = r.state.map_sections
        if theater and theater.isdisjoint(sections):        # 29.1: foul missed this theater
            label = weather.NORMAL
    r.emit(EventKind.WEATHER_ROLLED, Side.SYSTEM, "SYSTEM",
           {"weather": label, "season": season, "sections": sorted(sections)},
           rng_draws=draws)


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
    down at mission time (AIR_SUPERIORITY_LOSER_SCALE). Fires ONLY when a side fields air and the
    weather is flyable (29.43/29.52), so every air-less or grounded OpStage stays byte-identical."""
    if not r.state.air or _air_grounded(r.state.weather):
        return
    r.go(Phase.LOGISTICS, Side.SYSTEM)                   # a SYSTEM housekeeping beat, like convoys
    for arena in sorted({w.arena for w in r.state.air}):
        axis_f, allied_f = _air_arena_fighters(r.state, arena)
        ad, ld = r.d6(), r.d6()
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


def _air_support(r: _Run, side: Side, pinned: set[str]) -> None:
    """The LAND air-support sub-segment (rules 41.31/41.37/41.39B/42.2) at the TOP of the phasing
    side's Combat Segment, before _barrage_step. Flies `side`'s due LAND air missions in a fixed,
    deterministic order. STRIKE pins the strongest enemy in the target hex (12.44, joining the same
    `pinned` set the barrage feeds) -- UN-STRIKABLE behind an intact Major-City wall (fort_level>1,
    41.31); FORT bombing batters a wall one level/OpStage (reusing FORT_REDUCED); PORT bombing knocks
    a harbour's Efficiency Level down one (reusing PORT_EFFICIENCY_CHANGED, 41.39B); RECON lifts the
    fog over a hex (42.2). Fires ONLY when `side` fields air and the sky is flyable (29.43/29.52), so
    every air-less or grounded segment stays byte-identical."""
    if not r.state.air or _air_grounded(r.state.weather):
        return
    due = [m for m in r.state.air_missions if m.side == side and m.turn == r.state.turn]
    for m in sorted(due, key=lambda m: (m.kind, str(m.target))):
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
    FORT_REDUCED, so no new fold; air + barrage together open the works faster."""
    if not r.state.siege_rules or r.state.fort_level(tgt) <= 0:
        return
    r.emit(EventKind.FORT_REDUCED, side, f"{side.value}/Air",
           {"hex": list(tgt), "level": r.state.fort_level(tgt) - 1})


def _air_port(r: _Run, side: Side, port_id: str) -> None:
    """41.39B B-P: harbour bombing knocks a port's Efficiency Level down one (reusing
    PORT_EFFICIENCY_CHANGED, which apply.py already anticipates as 'bomb/mine damage'). The 55.18
    +1/OpStage regen contests it -- except a HARBOUR_BLOCKED port (PORT-Tobruk), which does not
    regen, so a bombed harbour there stays down: THE lever that chokes the ~425-Ammo/OpStage cap."""
    port = r.state.port(port_id)
    if port is None or port.eff <= 0:
        return
    r.emit(EventKind.PORT_EFFICIENCY_CHANGED, side, f"{side.value}/Air",
           {"port_id": port.id, "level": port.eff - 1})


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
        offset = r.rng.randint(-2, 2)                    # 42.24: TOE +-2
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
        d1, d2 = r.d6(), r.d6()
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
    dash later. Emits the SUPPLY_CONSUMED draws and returns True; emits an ORDER_REJECTED and
    returns False when no fuel source in the hex can cover the move."""
    draws = supply.plan_draw(r.state, u, supply.FUEL, supply.fuel_cost(u, cp_spent))
    if draws is None:
        _reject(r, side, actor, order, reason, order_kind=order_kind)
        return False
    for sid, qty in draws:
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": sid, "commodity": supply.FUEL, "qty": qty, "unit_id": u.id})
    return True


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
        if eligible is not None and u.id not in eligible:
            _reject(r, side, actor, order,
                    "not eligible for continual movement (8.23 two-hex gate)")
            continue
        if u.reserve == 2:                              # 18.22: Reserve II never moves
            _reject(r, side, actor, order, "Reserve II units may not move (18.22)")
            continue
        if u.effective_strength == 0:                   # 21.44: all vehicles broken down
            _reject(r, side, actor, order, "all vehicles broken down, may not move (21.44)")
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
           if u.is_combat and u.mobility == Mobility.MOTORIZED and not u.engaged
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
    wshift = combat_tables.weather_breakdown_shift(r.state.weather)          # 21.37
    for u in sorted(r.state.living(side), key=lambda u: u.id):
        if not u.breaks_down or u.bp_accumulated <= 3:                       # 21.11 / 21.27
            continue
        col = combat_tables.breakdown_column(u.bp_accumulated, u.bar, wshift)
        if col <= u.bp_checked_column:                                       # 21.26 gate
            continue
        d1, d2 = r.d6(), r.d6()
        pct = combat_tables.breakdown_result(u.bp_accumulated, u.bar, wshift, d1 * 10 + d2)
        broken = _broken_count(pct, u.effective_strength)
        r.emit(EventKind.BREAKDOWN_CHECKED, side, actor,
               {"unit_id": u.id, "column": col, "bar": u.bar,
                "weather_shift": wshift, "pct": pct}, rng_draws=(d1, d2))
        if broken > 0:
            r.emit(EventKind.VEHICLE_BROKE_DOWN, side, actor,
                   {"unit_id": u.id, "amount": broken})


# Field tank/SPA repair expends Fuel (22.15/22.26). Fork B charges it per repair
# ATTEMPT (one unit's roll) rather than per TOE point -- the design's documented proxy;
# armored-car / recce field repair is free (22.24).
_REPAIR_FUEL: int = 1


def _field_repair_blocked(weather_label: str) -> bool:
    """22.13d: no Field Repair while the Weather is Rainstorm or Sandstorm (keyed off the
    single global 29.1 label -- the per-section coupling stays a documented Fork-B proxy)."""
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
    if _field_repair_blocked(r.state.weather):          # 22.13d: whole-map proxy, no field repair
        return
    enemy_ctrl = CONTROL_OF[_other(side)]
    repairable = [u for u in r.state.living(side)
                  if u.broken_down > 0 and u.breaks_down
                  and r.state.control_of(u.hex) != enemy_ctrl]     # 22.13a
    if not repairable:
        return
    r.go(Phase.REPAIR, side)
    actor = f"{side.value}/Repair"
    for u in sorted(repairable, key=lambda u: u.id):
        cur = r.state.unit(u.id)
        vclass = "tank" if cur.is_tank else "ac_recce"
        if vclass == "tank":                            # 22.26: expend Fuel before rolling
            draws = supply.plan_draw(r.state, cur, supply.FUEL, _REPAIR_FUEL)
            if draws is None:
                continue                                # 22.13b: no supplies -> no repair
            for sid, qty in draws:
                r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
                       {"supply_id": sid, "commodity": supply.FUEL, "qty": qty, "unit_id": cur.id})
        die = r.d6()
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


def _supply_movement(r: _Run, policy: Policy, side: Side) -> None:
    """Relocate supply units with the advancing army (rule 32.3): a carried dump
    moves up to CPA 15 as medium-truck, costs a flat 1 Fuel Point (32.24) drawn
    from its own trucks, and must end stacked with a friendly combat unit (32.33).
    Validated at the boundary like every other order."""
    actor = f"{side.value}/Logistics"
    moved: set = set()               # a dump relocates at most once per OpStage (32.58A)
    for order in policy.supply_orders(r.state, side):
        su = r.state.supply(order.supply_id)
        if su is None or su.side != side or su.empty:
            _reject_supply(r, side, actor, order, "no such active supply unit")
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
    truck = r.state.truck(order.truck_id)
    if truck is None or truck.side != side:
        _reject_truck(r, side, actor, order, "no such truck formation under this command")
        return
    if order.load and not _truck_load(r, side, actor, order, r.state.truck(truck.id)):
        return
    if order.to is not None and not _truck_move(r, side, actor, order, r.state.truck(truck.id), moved):
        return
    if order.unload:
        _truck_unload(r, side, actor, order, r.state.truck(truck.id))


def _truck_load(r: _Run, side: Side, actor: str, order, truck) -> bool:
    dump = r.state.supply(order.load_from)
    if dump is None or dump.side != side or dump.hex != truck.hex:
        _reject_truck(r, side, actor, order, "no co-located friendly dump to load from")
        return False
    cargo = {c: q for c, q in order.load.items() if q > 0}
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
    dump = r.state.supply(order.unload_to)
    if dump is None or dump.side != side or dump.hex != truck.hex:
        _reject_truck(r, side, actor, order, "no co-located friendly dump to unload into")
        return
    cap = supply.dump_capacity(r.state.terrain.terrain[dump.hex])     # 54.12 ceiling
    cargo: dict = {}
    for c, q in order.unload.items():
        onhand = getattr(dump, c.lower())
        landed = min(q, getattr(truck, c.lower()), min(cap[c], onhand + q) - onhand)
        if landed > 0:
            cargo[c] = landed
    if cargo:
        r.emit(EventKind.TRUCK_UNLOADED, side, actor,
               {"truck_id": truck.id, "supply_id": dump.id, "cargo": cargo})


def _reject_truck(r: _Run, side: Side, actor: str, order, reason: str) -> None:
    r.emit(EventKind.ORDER_REJECTED, side, actor,
           {"order": "truck_convoy", "truck_id": order.truck_id, "reason": reason})


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
        _resolve_combat(r, side, actor, attackers, defenders, target, pinned, charged)
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
            d1, d2 = r.d6(), r.d6()
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
            d1, d2 = r.d6(), r.d6()
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
                    target: Coord, pinned: set[str], charged: set[str]) -> None:
    # Ammo gates participation (rule 32.21 / 15.15) and Pin suppresses it (12.44):
    # a unit that cannot draw ammo or is Pinned cannot assault; a Pinned or unarmed
    # defender adds no defensive strength but still suffers losses. Charged before
    # resolution (conservation holds per event).
    armed_atk = [u for u in attackers
                 if u.id not in pinned and _charge_ammo(r, side, actor, u, phasing=True)]
    if not armed_atk:
        r.emit(EventKind.ORDER_REJECTED, side, actor,
               {"order": "attack", "target": list(target),
                "reason": "attackers out of ammo or pinned"})
        return
    for u in armed_atk:                         # 6.3: the phasing Assault CP (5), once/segment
        _charge_combat_cp(r, side, u, charged)
    # 15.15 / 15.88: an assaulted stack that is entirely out of Close-Assault ammo,
    # or whose (largest) unit's Cohesion has collapsed to -17 or worse, automatically
    # Surrenders the instant it is assaulted -- BEFORE it rolls morale or spends a
    # round of ammunition. This is the fix that lets a besieged, cut-off garrison
    # (a dry Tobruk) finally be forced to capitulate instead of holding at zero
    # defensive strength in perpetuity.
    if _defenders_capitulate(r, defenders):
        _resolve_surrender(r, side, actor, target, armed_atk, defenders,
                           atk_surr=False, def_surr=True, morale_shift=0, dice=())
        return
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
    # 17.26(b): a defender whose largest unit has Basic Morale +1 or better may NOT
    # shrug off a rolled SURR when the assaulting enemy fields at least three times
    # its strength (Enemy Raw Offensive Assault : Friendly Raw Defensive). The
    # cohesion-based 17.26(a) reprieve-void is handled per-unit in _adjusted_morale.
    overwhelms = (sum(u.raw_offense for u in armed_atk)
                  >= 3 * sum(u.raw_defense for u in armed_def))
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
        return
    if atk_surr or def_surr:                                    # rule 17.25: the stack surrenders
        _resolve_surrender(r, side, actor, target, armed_atk, defenders,
                           atk_surr, def_surr, atk_m - def_m, (*atk_md, *def_md))
        return
    ab, asm, db, dsm = r.d6(), r.d6(), r.d6(), r.d6()
    res = combat.resolve(
        attacker_raw=sum(u.raw_offense for u in armed_atk),
        defender_raw=sum(u.raw_defense for u in armed_def),     # unarmed defenders -> 0
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
    # Cohesion: 30%+ losses disorganize the involved units (rule 15.87). Recovery
    # (Reorganization Points, rule 20) is deferred, so Cohesion only falls -- flagged.
    if res.attacker_loss_pct >= 30:
        for u in armed_atk:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -3})
    if res.defender_loss_pct >= 30:
        for u in defenders:
            r.emit(EventKind.COHESION_CHANGED, side, actor, {"unit_id": u.id, "delta": -3})
    if res.retreat_hexes > 0:                                   # rule 15.8 / 15.82
        _retreat(r, side, actor, [d.id for d in defenders], armed_atk[0].hex, res.retreat_hexes)


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


def _honors_surrender(morale: int, cohesion: int, enemy_overwhelms: bool) -> bool:
    """Does a rolled SURR (17.4 Surrender column) actually stick? By 17.25 the stack
    Surrenders -- UNLESS its (largest) unit's Basic Morale is +1 or better, in which
    case 17.26 lets it treat the SURR as a mere -4 adjustment and fight on. That
    reprieve is voided, and the Surrender enforced, when either 17.26 exception holds:
    (a) the unit's Cohesion has collapsed to -11 or worse, or (b) the assaulting enemy
    brings at least three times the strength (Enemy Raw Offensive : Friendly Raw
    Defensive), passed in as `enemy_overwhelms`."""
    if morale < 1:
        return True
    return cohesion <= -11 or enemy_overwhelms


def _adjusted_morale(r: _Run, units, *,
                     enemy_overwhelms: bool = False) -> tuple[int, tuple[int, int], bool]:
    """Adjusted Morale of a close-assault stack (rule 15.6): the LARGEST unit's Basic Morale
    (17.32) plus the 17.4 modifier rolled at its Cohesion level, clamped to -3..+3 (17.23),
    THEN General Rommel's +1 (17.28) added OUTSIDE that clamp -- the one explicit 17.23
    exception, so a +3 unit stacked with Rommel reaches +4. Returns (morale, the two dice,
    surrendered). A SURR result eliminates the stack (17.25); the 17.26 reprieve and its
    (a) cohesion / (b) enemy-3x exceptions are decided by _honors_surrender. When SURR is
    shrugged off it counts as the -4 penalty."""
    live = [u for u in units if u.strength > 0]
    if not live:
        return 0, (0, 0), False
    largest = max(live, key=lambda u: (u.stacking_points, u.strength))
    d1, d2 = r.d6(), r.d6()
    mod = combat_tables.morale_modifier(largest.cohesion, d1 * 10 + d2)
    surrendered = mod == "SURR" and _honors_surrender(
        largest.morale, largest.cohesion, enemy_overwhelms)
    if mod == "SURR":
        mod = -4
    m = max(-3, min(3, largest.morale + mod))          # 17.23: clamp the Adjusted Morale FIRST
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
    """Can this unit draw its Close-Assault ammunition right now (rule 32.21 / 50)?
    A non-mutating mirror of the _charge_ammo supply gate, used to detect the 15.15
    all-out-of-ammunition condition without expending anything."""
    return supply.plan_draw(state, unit, supply.AMMO,
                            supply.ammo_cost(unit, phasing=phasing, activity="assault")) is not None


def _defenders_capitulate(r: _Run, defenders) -> bool:
    """Hard surrender thresholds on an assaulted defending stack, ahead of the 17.4
    roll (15.88 -- units so afflicted automatically Surrender). Returns True when:
      - 15.15: EVERY defender is out of Close-Assault ammunition, so a cut-off, dry
        garrison capitulates en masse rather than defend on at zero strength; or
      - 15.88: the stack's largest unit's Cohesion has collapsed to -17 or worse
        (17.24 '-17 et seq'; 17.27 Largest Unit Rule)."""
    live = [u for u in defenders if u.strength > 0]
    if not live:
        return False
    largest = max(live, key=lambda u: (u.stacking_points, u.strength))
    if largest.cohesion <= -17:                                        # 15.88
        return True
    return all(not _has_ammo(r.state, u, phasing=False) for u in live)  # 15.15


def _charge_ammo(r: _Run, side: Side, actor: str, unit, *, phasing: bool,
                 activity: str = "assault") -> bool:
    draws = supply.plan_draw(r.state, unit, supply.AMMO,
                             supply.ammo_cost(unit, phasing=phasing, activity=activity))
    if draws is None:
        return False
    for sid, qty in draws:
        r.emit(EventKind.SUPPLY_CONSUMED, side, actor,
               {"supply_id": sid, "commodity": supply.AMMO, "qty": qty, "unit_id": unit.id})
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
    for coord in r.state.terrain.terrain:
        occ = [u for u in r.state.units_at(coord) if u.is_combat]   # only combat units hold ground
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


def determinism_signature(events: list[Event]) -> str:
    from .events import log_to_json
    return log_to_json(events)
