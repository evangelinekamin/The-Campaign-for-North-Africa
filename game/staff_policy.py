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
from .staff import Lane, role_brief, unit_lanes
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

    def __init__(self, client, side: Side = Side.AXIS):
        super().__init__(attacker=side)
        self.side = side
        self.client = client
        self._move_key = None
        self._plan: SideTurnPlan | None = None
        self._combat_key = None
        self._combat_orders: list[AttackOrder] = []
        self._pending: list[tuple[EventKind, dict]] = []   # staff artifacts awaiting drain

    def reset(self) -> None:
        self._move_key = self._combat_key = None
        self._plan = None
        self._combat_orders = []
        self._pending = []

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
        # PROPOSE in-lane, then the constraints (intel / logistics) report up.
        intent = self._chief_intent(obs)                           # STAFF_INTENT
        mobile = self._goc_moves(obs, Lane.MOBILE, idl)            # STAFF_PROPOSAL
        infantry = self._goc_moves(obs, Lane.INFANTRY, idl)        # STAFF_PROPOSAL
        supply = tuple(ScriptedPolicy.supply_orders(self, state, side))   # QM lane
        truck = tuple(ScriptedPolicy.truck_orders(self, state, side))
        self._quartermaster(supply)                                # STAFF_PROPOSAL (supply)
        self._intelligence(obs)                                    # STAFF_CONSTRAINT (intel)
        movement = self._resolve(state, side, mobile, infantry, idl, intent)
        return SideTurnPlan(tuple(movement), supply, truck)

    def _resolve(self, state, side, mobile, infantry, idl, intent) -> list[MoveOrder]:
        """Concatenate the two GOCs' MoveOrders and apply the fuel lever: sort by the
        Chief's formation priority so the panzers drain the shared dump first and the
        trailing Italians hit the real 'no fuel' rejection (draw-priority == batch
        position; the engine charges fuel sequentially over this list). Step 5 layers
        the dry-run adjudication on top; here it is a stable priority sort."""
        combined = list(mobile) + list(infantry)
        return self._fuel_sort(state, combined)

    def _fuel_sort(self, state: GameState, orders: list[MoveOrder]) -> list[MoveOrder]:
        def key(item):
            i, o = item
            u = state.unit(o.unit_id)
            return (_formation_rank(u.formation) if u is not None else len(FUEL_PRIORITY), i)
        return [o for _, o in sorted(enumerate(orders), key=key)]

    # --- seats -------------------------------------------------------------------
    def _chief_intent(self, obs: dict) -> dict:
        raw = _extract_json(self.client.complete(build_intent_prompt(obs))).get("intent")
        intent = _clean_intent(raw) if isinstance(raw, dict) else {}
        self._stage(EventKind.STAFF_INTENT, {**intent, "seat": "Chief", "formation": "DAK"})
        return intent

    def _intelligence(self, obs: dict) -> None:
        sightings = obs.get("enemy_sightings", [])
        severity = "warn" if sightings else "info"
        line = (f"{len(sightings)} enemy stack(s) sighted"
                if sightings else "no enemy stacks in sight")
        self._stage(EventKind.STAFF_CONSTRAINT,
                    {"kind": "intel", "severity": severity, "seat": "Intel", "line": line})

    def _goc_moves(self, obs: dict, lane: Lane, idl: dict) -> list[MoveOrder]:
        brief = role_brief(obs, lane, idl)
        moves = parse_moves(self.client.complete(build_movement_prompt(brief)))
        self._stage(EventKind.STAFF_PROPOSAL, {
            "seat": lane.value, "formation": lane.value,
            "proposes": [{"order": "move", "units": [m.unit_id], "to": list(m.to)}
                         for m in moves],
            "rationale": f"{lane.value} corps advances {len(moves)} unit(s)",
        })
        return moves

    def _quartermaster(self, supply: tuple[SupplyMoveOrder, ...]) -> None:
        self._stage(EventKind.STAFF_PROPOSAL, {
            "seat": Lane.QM.value, "formation": Lane.QM.value,
            "proposes": [{"order": "supply_move", "units": [s.supply_id], "to": list(s.to)}
                         for s in supply],
            "rationale": f"quartermaster relocates {len(supply)} dump(s) forward",
        })

    def _deliberate_combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        obs = observe(state, side)
        if not obs.get("attack_options"):
            return []
        idl = unit_lanes(state, side)
        attacks: list[AttackOrder] = []
        for lane in (Lane.MOBILE, Lane.INFANTRY):
            brief = role_brief(obs, lane, idl)
            if not brief["attack_options"]:
                continue
            lane_attacks = parse_attacks(self.client.complete(build_combat_prompt(brief)))
            self._stage(EventKind.STAFF_PROPOSAL, {
                "seat": lane.value, "formation": lane.value,
                "proposes": [{"order": "attack", "units": list(a.attacker_ids), "to": list(a.target)}
                             for a in lane_attacks],
                "rationale": f"{lane.value} corps assaults {len(lane_attacks)} target(s)",
            })
            attacks += lane_attacks
        return merge_attacks(attacks)
