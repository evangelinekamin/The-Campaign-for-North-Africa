"""LLM Front-Commander policy (brief §4.5, §8).

Same Policy interface the engine already validates against: the LLM proposes
movement and close-assault orders from a role-scoped observation; the engine
rejects anything illegal (brief §3.3 — engine-boundary validation, NOT constrained
decoding). Supply logistics inherit the scripted doctrine (rule-mechanical), so
the agent spends its reasoning on the interesting decisions.

Parsing is deliberately tolerant: an LLM reply is mined for a JSON object and any
well-formed order is kept; malformed or illegal ones are simply dropped or
rejected downstream — never crashing the run. That tolerance is the whole point of
validating at the boundary instead of constraining the model's output.
"""
from __future__ import annotations

import json

from .events import Side
from .observation import observe
from .policy import AttackOrder, MoveOrder, ScriptedPolicy
from .state import GameState


class LLMPolicy(ScriptedPolicy):
    def __init__(self, side: Side, client):
        super().__init__(attacker=side)
        self.side = side
        self.client = client

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        text = self.client.complete(build_movement_prompt(observe(state, side)))
        return parse_moves(text)

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        text = self.client.complete(build_combat_prompt(observe(state, side)))
        return parse_attacks(text)

    # supply_orders(): inherited scripted logistics (dumps follow the advance).


# --- prompts ----------------------------------------------------------------

_RULES = ("The Campaign for North Africa, a hex wargame. Hexes are axial [q,r]. "
          "Enemy stacks are seen only as presence + stacking_points (limited "
          "intelligence). The engine rejects illegal orders, so state your intent.")


def build_movement_prompt(obs: dict) -> str:
    obj = obs["objective"]
    return (
        f"You command the {obs['your_side']} forces. {_RULES}\n"
        f"MOVEMENT phase, game-turn {obs['turn']}/{obs['max_turns']}, weather "
        f"{obs['weather']}. Objective: hex {obj['hex']} (controlled by "
        f"{obj['controlled_by']}); aim to control it by the final turn.\n"
        f"Situation (JSON):\n{json.dumps(obs)}\n"
        "For each combat unit you move, pick its destination FROM that unit's "
        "can_move_to list (those are the only hexes it can legally reach this turn; "
        "lower dist = closer to the objective). Advance toward the objective and "
        "keep stacks together.\n"
        'Reply with ONLY JSON: {"reasoning":"one sentence","moves":'
        '[{"unit":"<id>","to":[q,r]}]}. Use a [q,r] taken from that unit\'s '
        "can_move_to; omit units that should hold.")


def build_combat_prompt(obs: dict) -> str:
    return (
        f"You command the {obs['your_side']} forces. {_RULES}\n"
        f"COMBAT phase, game-turn {obs['turn']}/{obs['max_turns']}. Close-assault "
        f"using attack_options: each entry gives a target hex, the your_attackers "
        f"adjacent to it, and the enemy_stacking_points there. Attack where your "
        f"attackers outweigh the defender.\nSituation (JSON):\n{json.dumps(obs)}\n"
        'Reply with ONLY JSON: {"reasoning":"one sentence","attacks":'
        '[{"attackers":["<id>"],"target":[q,r]}]}. Take target + attackers from '
        "attack_options; omit if you should not attack.")


# --- tolerant parsing -------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Mine the first JSON object out of an LLM reply (tolerant of prose / code
    fences). Returns {} if none parses."""
    if not text:
        return {}
    i, j = text.find("{"), text.rfind("}")
    if i == -1 or j <= i:
        return {}
    try:
        obj = json.loads(text[i:j + 1])
        return obj if isinstance(obj, dict) else {}
    except (ValueError, TypeError):
        return {}


def _hex(v) -> tuple | None:
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(c, int) for c in v):
        return (v[0], v[1])
    return None


def parse_moves(text: str) -> list[MoveOrder]:
    out: list[MoveOrder] = []
    for m in _extract_json(text).get("moves", []) or []:
        if not isinstance(m, dict):
            continue
        dest = _hex(m.get("to"))
        uid = m.get("unit")
        if dest is not None and isinstance(uid, str):
            out.append(MoveOrder(uid, dest))
    return out


def parse_attacks(text: str) -> list[AttackOrder]:
    out: list[AttackOrder] = []
    for a in _extract_json(text).get("attacks", []) or []:
        if not isinstance(a, dict):
            continue
        tgt = _hex(a.get("target"))
        ids = a.get("attackers")
        if tgt is not None and isinstance(ids, list) and all(isinstance(i, str) for i in ids) and ids:
            out.append(AttackOrder(tuple(ids), tgt))
    return out
