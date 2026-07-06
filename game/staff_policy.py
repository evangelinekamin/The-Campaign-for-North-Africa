"""StaffPolicy: a command-staff Policy that deliberates once per side-turn and
dispenses phase-slices (the prove-the-machine gate, driven by deterministic stubs).

The Policy interface is phase-sliced (movement / supply_orders / combat /
truck_orders) but staff deliberation is per-side-turn holistic. So StaffPolicy runs
the whole protocol lazily on the FIRST engine call of a side-turn (movement()),
caches a SideTurnPlan keyed by (turn, stage, side), and every later movement-turn
method just returns its cached slice. combat() is re-deliberated at combat() time
because the board has moved after movement + breakdown + supply; it reuses the same
seats (the two GOCs re-propose assaults) and merges same-target AttackOrders into
one combined-arms assault.

Five formation-scoped seats compose the plan (game.staff.lane_of partitions the
force): the CHIEF frames a STAFF_INTENT and the fuel priority; INTELLIGENCE reads
the fogged sightings into a STAFF_CONSTRAINT; the two GOCs propose in-lane through
the UNCHANGED build_movement_prompt / build_combat_prompt + parse_moves /
parse_attacks (only the client is a stub); the QUARTERMASTER runs the scripted
logistics reflexes. Deliberation accumulates cleaned staff artifacts that the
engine drains through the optional drain_staff() hook -- policies return Orders, not
Events, so only the engine's conservation-checked emit writes the log.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .adjudication import validate_batch
from .events import EventKind, Side
from .llm_policy import (
    _clean_intent,
    _extract_json,
    build_combat_prompt,
    build_movement_prompt,
    parse_attacks,
    parse_moves,
)
from .observation import observe
from .policy import AttackOrder, MoveOrder, ScriptedPolicy, SupplyMoveOrder, TruckOrder
from .staff import Lane, cross_lane_conflicts, role_brief, unit_lanes
from .state import GameState

# The Chief's fuel/reinforcement priority: the mobile formations drain the shared
# dumps first (armour is decisive), trailing infantry last. Draw-priority == batch
# position (see StaffPolicy.movement), so this list IS the fuel lever.
FUEL_PRIORITY = (
    "GE 15th Panzer Division",
    "GE 5th Light Panzer Division",
    "IT Ariete Armoured Division",
)


def _formation_rank(formation: str) -> int:
    """Chief fuel priority as a sort key: the ranked mobile formations first (in
    order), every other formation after, ties stable by original batch position."""
    return FUEL_PRIORITY.index(formation) if formation in FUEL_PRIORITY else len(FUEL_PRIORITY)


# --- static persona cards -----------------------------------------------------
# A frozen doctrine one-liner + bias per seat, injected as a prompt preamble so each
# seat argues in character. Flavour ONLY: the card text enters that seat's OWN prompt
# and never another seat's -- the control plane between seats stays the whitelisted
# structured fields (INTENT_FIELDS / engine-computed Conflicts), never persona prose.
CHIEF = "Chief"
INTEL = "Intel"


@dataclass(frozen=True, slots=True)
class PersonaCard:
    name: str
    doctrine: str
    bias: str


PERSONAS: dict[str, PersonaCard] = {
    CHIEF: PersonaCard(
        "the Axis Chief of Staff",
        "concentrate force at the decisive point and keep the initiative",
        "bold and offensive-minded; accepts risk to hold the tempo"),
    Lane.MOBILE.value: PersonaCard(
        "GOC Mobile Corps",
        "armour is decisive -- unleash the panzers before the enemy sets",
        "aggressive; demands the fuel and the point of main effort"),
    Lane.INFANTRY.value: PersonaCard(
        "GOC Infantry Corps",
        "hold the ground the armour takes and screen the open flank",
        "methodical; resents being starved to feed the panzers"),
    Lane.QM.value: PersonaCard(
        "the Quartermaster",
        "the desert eats trucks -- husband the fuel or the panzers strand",
        "cautious; hoards stores against the long coastal supply line"),
    INTEL: PersonaCard(
        "Staff Intelligence",
        "read the enemy from the little that is sighted; assume the unseen",
        "wary; warns of the stack the reconnaissance has not yet found"),
}

# The seats that actually drive an LLM in v1 (the Chief frames intent; the two GOCs
# propose in-lane). The Quartermaster runs scripted logistics reflexes and
# Intelligence a deterministic read of the fogged sightings, so neither spends a token.
LLM_SEATS = (CHIEF, Lane.MOBILE.value, Lane.INFANTRY.value)


def persona_preamble(seat: str) -> str:
    """The seat's static persona card as a one-line prompt preamble ('' if none)."""
    card = PERSONAS.get(seat)
    return f"You are {card.name}. Doctrine: {card.doctrine}. Bias: {card.bias}.\n" if card else ""


@dataclass(frozen=True, slots=True)
class SideTurnPlan:
    """The resolved movement-turn slices, deliberated once and dispensed by phase."""
    movement: tuple[MoveOrder, ...]
    supply: tuple[SupplyMoveOrder, ...]
    truck: tuple[TruckOrder, ...]


def build_intent_prompt(obs: dict) -> str:
    """The Chief's structured-intent prompt (staff-specific; the specialists reuse the
    unchanged movement/combat prompts). Embeds the same observation shape so a stub or
    a live model can ground its frame, and asks for the whitelisted INTENT_FIELDS."""
    obj = obs["objective"]
    return (
        f"COMMANDER'S INTENT. You are the Axis Chief of Staff, game-turn "
        f"{obs['turn']}/{obs['max_turns']}, Operations Stage {obs['stage']}/3, "
        f"weather {obs['weather']}. Objective: hex {obj['hex']} (controlled by "
        f"{obj['controlled_by']}).\nSituation (JSON):\n{json.dumps(obs)}\n"
        'Reply with ONLY JSON: {"intent":{"objective":"...","scheme":"...",'
        '"supply":"...","milestone":"...","risks":"..."}} -- one short sentence each.')


def merge_attacks(attacks: list[AttackOrder]) -> list[AttackOrder]:
    """Merge same-target AttackOrders into one combined-arms assault (union of the
    attacker ids, first-seen order preserved) -- matching engine _combat's one-assault-
    per-hex dedupe, so no lane's attackers are wasted on an 'already assaulted' reject."""
    by_target: dict = {}
    for a in attacks:
        ids = by_target.setdefault(a.target, [])
        for aid in a.attacker_ids:
            if aid not in ids:
                ids.append(aid)
    return [AttackOrder(tuple(ids), tgt) for tgt, ids in by_target.items()]


class StaffPolicy(ScriptedPolicy):
    """A five-seat command staff over the existing Policy seam. Plays one side (the
    Axis by default); the scripted reflexes (declare_ab, retreat_before_assault) are
    inherited unchanged. `client` is any LLMClient -- a MockClient stub proves the
    machine at zero token cost."""

    def __init__(self, client, side: Side = Side.AXIS, *,
                 seat_clients: "dict[str, object] | None" = None, max_workers: int = 1):
        super().__init__(attacker=side)
        self.side = side
        self.client = client                               # shared fallback (mock path)
        self._seat_clients = dict(seat_clients or {})      # per-seat live clients (live path)
        self._workers = max_workers                        # >1 parallelises the specialist calls
        self._move_key = None
        self._plan: SideTurnPlan | None = None
        self._combat_key = None
        self._combat_orders: list[AttackOrder] = []
        self._pending: list[tuple[EventKind, dict]] = []   # staff artifacts awaiting drain
        self._lane_rationale: dict[Lane, str] = {}         # captured GOC rationale (for dissent)

    # --- LLM seam ---------------------------------------------------------------
    def _client_for(self, seat: str):
        """The seat's own client (live path) or the shared fallback (mock path)."""
        return self._seat_clients.get(seat, self.client)

    def _ask(self, seat: str, prompt: str) -> str:
        """One seat's call: its static persona card is prepended to the prompt (so it
        argues in character) and routed to that seat's client."""
        return self._client_for(seat).complete(persona_preamble(seat) + prompt)

    def _map_lanes(self, fn, lanes):
        """Run each lane's specialist call, re-collected keyed by lane so the caller
        reads them back in FIXED lane order. Parallel across lanes when max_workers > 1:
        the calls are independent I/O and mutate no shared state (staging happens in the
        caller, post-join), so concurrency is an I/O win only and never perturbs the
        deterministic fold."""
        if self._workers <= 1 or len(lanes) <= 1:
            return {lane: fn(lane) for lane in lanes}
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(self._workers, len(lanes))) as ex:
            futures = {lane: ex.submit(fn, lane) for lane in lanes}
        return {lane: fut.result() for lane, fut in futures.items()}

    def usage(self) -> dict:
        """Summed usage across every seat's client (+ the shared fallback); clients
        without a usage() (e.g. MockClient) contribute nothing. For cost reporting."""
        clients = list(self._seat_clients.values())
        if self.client not in clients:
            clients.append(self.client)
        total: dict = {}
        for c in clients:
            if hasattr(c, "usage"):
                for k, v in c.usage().items():
                    total[k] = total.get(k, 0) + v
        return total

    def reset(self) -> None:
        self._move_key = self._combat_key = None
        self._plan = None
        self._combat_orders = []
        self._pending = []
        self._lane_rationale = {}

    # --- the drain hook (symmetric with debrief / declare_ab) --------------------
    def drain_staff(self) -> list[tuple[EventKind, dict]]:
        """The staff artifacts accumulated since the last drain, cleared on read. The
        engine emits them (conservation-checked) just before the orders they explain."""
        out = self._pending
        self._pending = []
        return out

    def _stage(self, kind: EventKind, payload: dict) -> None:
        self._pending.append((kind, payload))

    # --- phase slices ------------------------------------------------------------
    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        return list(self._ensure_plan(state, side).movement)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        return list(self._ensure_plan(state, side).supply)

    def truck_orders(self, state: GameState, side: Side) -> list[TruckOrder]:
        return list(self._ensure_plan(state, side).truck)

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        key = (state.turn, state.stage, side)
        if key != self._combat_key:
            self._combat_key = key
            self._combat_orders = self._deliberate_combat(state, side)
        return list(self._combat_orders)

    # --- deliberation ------------------------------------------------------------
    def _ensure_plan(self, state: GameState, side: Side) -> SideTurnPlan:
        key = (state.turn, state.stage, side)
        if key != self._move_key or self._plan is None:
            self._move_key = key
            self._plan = self._deliberate_movement(state, side)
        return self._plan

    def _deliberate_movement(self, state: GameState, side: Side) -> SideTurnPlan:
        obs = observe(state, side)
        idl = unit_lanes(state, side)
        # Narrative order per side-turn: the Chief frames the INTENT, the specialists
        # PROPOSE in-lane (in parallel, re-collected in FIXED lane order), then the
        # constraints (intel / logistics) report up.
        self._chief_intent(obs)                                    # STAFF_INTENT
        lanes = (Lane.MOBILE, Lane.INFANTRY)
        proposals = self._map_lanes(lambda ln: self._goc_propose_moves(obs, ln, idl), lanes)
        lane_moves: dict[Lane, list[MoveOrder]] = {}
        for ln in lanes:                                           # STAFF_PROPOSAL (fixed order)
            moves, payload = proposals[ln]
            lane_moves[ln] = moves
            self._lane_rationale[ln] = payload["rationale"]
            self._stage(EventKind.STAFF_PROPOSAL, payload)
        supply = tuple(ScriptedPolicy.supply_orders(self, state, side))   # QM lane
        truck = tuple(ScriptedPolicy.truck_orders(self, state, side))
        self._quartermaster(supply)                                # STAFF_PROPOSAL (supply)
        self._intelligence(obs)                                    # STAFF_CONSTRAINT (intel)
        movement = self._resolve(state, lane_moves[Lane.MOBILE], lane_moves[Lane.INFANTRY], idl)
        return SideTurnPlan(tuple(movement), supply, truck)

    def _resolve(self, state, mobile, infantry, idl) -> list[MoveOrder]:
        """Dry-run the combined batch (the Step-2 filtered validate_batch), let the
        Chief rule each cross-lane Conflict structurally, then apply the fuel lever.

        A cross-lane collision is favored to the higher fuel-priority formation:
          * over-stack / road-cap -- a hard physical clash: the denied order is DROPPED.
          * oversubscribed-dump    -- fuel scarcity: NOTHING is dropped. The favored
            formation is sorted to the FRONT so the engine's sequential SUPPLY_CONSUMED
            drains the shared dump first, and the trailing (denied) formation hits the
            real 'no fuel' rejection. The simulated desert -- not a special case --
            enforces scarcity (draw-priority == batch position, zero engine change).
        Every ruling emits a STAFF_ADJUDICATION and synthesizes the denied lane's
        STAFF_DISSENT from its captured rationale (no extra call)."""
        combined = list(mobile) + list(infantry)
        conflicts = cross_lane_conflicts(validate_batch(state, combined), idl)
        drop: set[str] = set()
        for c in conflicts:
            favored, denied, denied_ids = self._rule(state, c)
            self._adjudicate(c, favored, denied, denied_ids, idl)
            if c.kind in ("over-stack", "road-cap"):
                drop |= denied_ids
        kept = [o for o in combined if o.unit_id not in drop]
        return self._fuel_sort(state, kept)

    def _rule(self, state, conflict) -> tuple[str, str, set[str]]:
        """The Chief's structural ruling: among the conflict's contending formations,
        the highest fuel priority is favored, the lowest denied. Returns (favored
        formation, denied formation, the denied contenders' unit ids)."""
        by_formation: dict[str, list[str]] = {}
        for uid in conflict.unit_ids:
            u = state.unit(uid)
            if u is not None:
                by_formation.setdefault(u.formation, []).append(uid)
        ranked = sorted(by_formation, key=_formation_rank)
        favored, denied = ranked[0], ranked[-1]
        denied_ids = {uid for uid in conflict.unit_ids
                      if state.unit(uid) is not None and state.unit(uid).formation != favored}
        return favored, denied, denied_ids

    def _adjudicate(self, conflict, favored, denied, denied_ids, idl) -> None:
        ruling = (f"fuel priority: {favored} drains the dump first, {denied} waits"
                  if conflict.kind == "oversubscribed-dump"
                  else f"{favored} holds the hex, {denied} stands off")
        self._stage(EventKind.STAFF_ADJUDICATION, {
            "seat": "Chief", "conflict": conflict.kind,
            "favored": favored[:48], "denied": denied[:48],
            "ruling": ruling, "hexes": [list(conflict.hex)],
        })
        lane = idl.get(next(iter(sorted(denied_ids)), None), Lane.INFANTRY)
        self._stage(EventKind.STAFF_DISSENT, {
            "seat": lane.value, "formation": denied[:48],
            "against": f"Chief favours {favored}"[:120],
            "stance": self._lane_rationale.get(lane, "the corps protests the priority"),
        })

    def _fuel_sort(self, state: GameState, orders: list[MoveOrder]) -> list[MoveOrder]:
        def key(item):
            i, o = item
            u = state.unit(o.unit_id)
            return (_formation_rank(u.formation) if u is not None else len(FUEL_PRIORITY), i)
        return [o for _, o in sorted(enumerate(orders), key=key)]

    # --- seats -------------------------------------------------------------------
    def _chief_intent(self, obs: dict) -> dict:
        raw = _extract_json(self._ask(CHIEF, build_intent_prompt(obs))).get("intent")
        intent = _clean_intent(raw) if isinstance(raw, dict) else {}
        self._stage(EventKind.STAFF_INTENT, {**intent, "seat": CHIEF, "formation": "DAK"})
        return intent

    def _intelligence(self, obs: dict) -> None:
        sightings = obs.get("enemy_sightings", [])
        severity = "warn" if sightings else "info"
        line = (f"{len(sightings)} enemy stack(s) sighted"
                if sightings else "no enemy stacks in sight")
        self._stage(EventKind.STAFF_CONSTRAINT,
                    {"kind": "intel", "severity": severity, "seat": INTEL, "line": line})

    def _goc_propose_moves(self, obs: dict, lane: Lane, idl: dict) -> tuple[list[MoveOrder], dict]:
        """A pure specialist movement call: returns (moves, STAFF_PROPOSAL payload). It
        stages NOTHING -- the caller stages in fixed lane order after the (possibly
        parallel) calls join, so concurrency never reorders the log."""
        brief = role_brief(obs, lane, idl)
        moves = parse_moves(self._ask(lane.value, build_movement_prompt(brief)))
        payload = {
            "seat": lane.value, "formation": lane.value,
            "proposes": [{"order": "move", "units": [m.unit_id], "to": list(m.to)}
                         for m in moves],
            "rationale": f"{lane.value} corps advances {len(moves)} unit(s)",
        }
        return moves, payload

    def _quartermaster(self, supply: tuple[SupplyMoveOrder, ...]) -> None:
        self._stage(EventKind.STAFF_PROPOSAL, {
            "seat": Lane.QM.value, "formation": Lane.QM.value,
            "proposes": [{"order": "supply_move", "units": [s.supply_id], "to": list(s.to)}
                         for s in supply],
            "rationale": f"quartermaster relocates {len(supply)} dump(s) forward",
        })

    def _goc_propose_attacks(self, obs: dict, lane: Lane, idl: dict) -> tuple[list[AttackOrder], dict | None]:
        """A pure specialist combat call: returns (attacks, STAFF_PROPOSAL payload or
        None if the lane has no targets). Stages nothing -- the caller stages in fixed
        lane order after the (possibly parallel) calls join."""
        brief = role_brief(obs, lane, idl)
        if not brief["attack_options"]:
            return [], None
        lane_attacks = parse_attacks(self._ask(lane.value, build_combat_prompt(brief)))
        payload = {
            "seat": lane.value, "formation": lane.value,
            "proposes": [{"order": "attack", "units": list(a.attacker_ids), "to": list(a.target)}
                         for a in lane_attacks],
            "rationale": f"{lane.value} corps assaults {len(lane_attacks)} target(s)",
        }
        return lane_attacks, payload

    def _deliberate_combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        obs = observe(state, side)
        if not obs.get("attack_options"):
            return []
        idl = unit_lanes(state, side)
        lanes = (Lane.MOBILE, Lane.INFANTRY)
        results = self._map_lanes(lambda ln: self._goc_propose_attacks(obs, ln, idl), lanes)
        attacks: list[AttackOrder] = []
        for ln in lanes:                                          # STAFF_PROPOSAL (fixed order)
            lane_attacks, payload = results[ln]
            if payload is not None:
                self._stage(EventKind.STAFF_PROPOSAL, payload)
                attacks += lane_attacks
        return merge_attacks(attacks)
