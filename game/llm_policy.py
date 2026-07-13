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

from .events import EventKind, Side
from .observation import observe
from .policy import AttackOrder, MoveOrder, ScriptedPolicy

# Briefing-mode intent: whitelisted fields + per-field char caps (a rambling model
# cannot smuggle a transcript back in through the intent field -- that's the stateful
# firehose re-entering by the back door).
_INTENT_FIELDS = {"objective": 140, "scheme": 200, "supply": 140, "milestone": 120, "risks": 140}
_INTENT_INSTRUCTION = (
    ' Also include "intent": an object with short-string fields objective, scheme, '
    'supply, milestone, risks, and lessons (<=3 short strings) -- your EVOLVING campaign '
    'plan, rewritten from scratch to fit the CURRENT board (never copy it forward verbatim).')


def _clean_intent(raw: dict) -> dict:
    out = {k: raw[k].strip()[:cap] for k, cap in _INTENT_FIELDS.items()
           if isinstance(raw.get(k), str) and raw[k].strip()}
    lessons = raw.get("lessons")
    if isinstance(lessons, list):
        clean = [str(x).strip()[:100] for x in lessons[:3] if isinstance(x, str) and str(x).strip()]
        if clean:
            out["lessons"] = clean
    return out
from .state import GameState


class LLMPolicy(ScriptedPolicy):
    """`mode` controls how much the model remembers between decisions -- the memory
    variable we benchmark separately from the model:
      * stateless -- each call is a fresh prompt, no memory (cheapest).
      * stateful  -- the full running conversation is sent each call (most tokens).
      * hybrid    -- fresh prompt + the model's own one-line plan carried forward.
    """

    def __init__(self, side: Side, client, mode: str = "stateless"):
        super().__init__(attacker=side)
        self.side = side
        self.client = client
        self.mode = mode
        self.history: list = []       # stateful: running [user/assistant] conversation
        self.plan = ""                # hybrid: the model's carried standing plan
        self.brief_events: list = []  # briefing: engine dispatches since the last decision
        self.intent: dict | None = None   # briefing: carried structured commander's intent
        self.intent_turn = 0
        self.stale_turns = 0          # turns the intent has gone unchanged
        self.steps_since_intent = 0   # own steps lost since the intent last changed

    def reset(self) -> None:          # clear memory between games (benchmark calls per game)
        self.history = []
        self.plan = ""
        self.brief_events = []
        self.intent = None
        self.intent_turn = 0
        self.stale_turns = 0
        self.steps_since_intent = 0

    def debrief(self, events: list) -> None:
        """Engine hook (briefing mode): the dispatches since this side last acted --
        rejected orders, losses, ground changes. Formatted into the next prompt."""
        self.brief_events = list(events)

    def _ask(self, prompt: str) -> str:
        if self.mode == "stateful":
            self.history.append({"role": "user", "content": prompt})
            text = self.client.chat(self.history)
            self.history.append({"role": "assistant", "content": text})
            return text
        if self.mode == "hybrid":
            if self.plan:
                prompt = f"Your standing plan (carried from last turn): {self.plan}\n\n{prompt}"
            text = self.client.complete(prompt)
            reasoning = _reasoning(text)
            if reasoning:
                self.plan = reasoning
            return text
        return self.client.complete(prompt)           # stateless

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        obs = observe(state, side)
        if self.mode in ("briefing", "brief_facts"):
            full = self.mode == "briefing"                       # brief_facts = Section A only
            prompt = self._briefing(state, full) + "\n" + build_movement_prompt(obs)
            text = self.client.complete(prompt + (_INTENT_INSTRUCTION if full else ""))
            if full:
                self._update_intent(text, state.turn)
            return parse_moves(text)
        return parse_moves(self._ask(build_movement_prompt(obs)))

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        obs = observe(state, side)
        if not obs.get("attack_options"):
            return []              # nothing adjacent to assault -- skip the API call entirely
        if self.mode in ("briefing", "brief_facts"):
            prompt = self._briefing(state, self.mode == "briefing") + "\n" + build_combat_prompt(obs)
            return parse_attacks(self.client.complete(prompt))
        return parse_attacks(self._ask(build_combat_prompt(obs)))

    # --- briefing mode: engine-authored FACTS + model-authored evolving INTENT -------

    def _briefing(self, state: GameState, full: bool = True) -> str:
        head = ("COMMANDER'S BRIEFING (staff facts since your last orders -- trust these):\n"
                + "\n".join(self._section_a(state)))
        return head + "\n" + "\n".join(self._section_b(state.turn)) if full else head

    def _section_a(self, state: GameState) -> list[str]:
        """Engine-authored, deterministic, identical quality for every model."""
        rej, mine, enemy = [], [], {}
        my_lost = 0
        for e in self.brief_events:
            p = e.payload
            if e.kind == EventKind.ORDER_REJECTED and e.side == self.side:
                who = p.get("unit_id") or ",".join(p.get("attacker_ids", []) or []) or "?"
                rej.append(f"{who}->{p.get('to') or p.get('target') or '?'}: {p.get('reason', '?')}")
            elif e.kind == EventKind.STEP_LOST:
                u = state.unit(p.get("unit_id", ""))
                if u is None:
                    continue
                if u.side == self.side:                          # my unit lost steps
                    mine.append(f"{u.id} -{p.get('amount', 0)} ({p.get('role', '?')})")
                    my_lost += p.get("amount", 0)
                else:                                            # enemy: per-hex counts only (3.6)
                    enemy[u.hex] = enemy.get(u.hex, 0) + p.get("amount", 0)
        self.steps_since_intent += my_lost
        vc = [e for e in self.brief_events if e.kind == EventKind.VICTORY_CHECKED]
        reinf = [f"{e.payload.get('unit_id', '?')}@{e.payload.get('hex', '?')}"
                 for e in self.brief_events
                 if e.kind == EventKind.REINFORCEMENT_ARRIVED and e.side == self.side]
        out = [
            "- FAILED orders (these units did NOT act -- reissue or work around them): "
            + ("; ".join(rej[:8]) + (f" (+{len(rej) - 8} more)" if len(rej) > 8 else "")
               if rej else "none"),
            "- Your losses: " + ("; ".join(mine[:6]) if mine else "none"),
            "- Enemy losses you inflicted: "
            + ("; ".join(f"{list(h)}:-{n}" for h, n in list(enemy.items())[:5]) if enemy else "none"),
        ]
        if vc:
            out.append(f"- Ground: advance {vc[-1].payload.get('axis', '?')}%")
        if reinf:
            out.append("- Reinforcements arrived: " + "; ".join(reinf[:2]))
        return out

    def _section_b(self, turn: int) -> list[str]:
        """Model-authored, carried, ADVISORY -- with challenge triggers (anti-anchor)."""
        if not self.intent:
            return ["YOUR STANDING INTENT: none yet -- author one this turn."]
        out = [f"YOUR STANDING INTENT (written turn {self.intent_turn}, "
               f"{turn - self.intent_turn} turn(s) ago; ADVISORY not binding -- the board "
               "has moved, revise it if it no longer fits):", json.dumps(self.intent)]
        n_rej = sum(1 for e in self.brief_events
                    if e.kind == EventKind.ORDER_REJECTED and e.side == self.side)
        if n_rej >= 3:
            out.append(f"  ! {n_rej} orders failed last turn -- this intent may assume moves that never happened.")
        if self.steps_since_intent >= 10:
            out.append(f"  ! you have lost {self.steps_since_intent} steps since writing this intent.")
        if self.stale_turns >= 3:
            out.append("  ! this intent is unchanged for 3 turns -- confirm it still fits the board.")
        return out

    def _update_intent(self, text: str, turn: int) -> None:
        raw = _extract_json(text).get("intent")
        if not isinstance(raw, dict) or not (new := _clean_intent(raw)):
            self.stale_turns += 1        # didn't (re)author -> carry the old, flag staleness
            return
        changed = json.dumps(new, sort_keys=True) != json.dumps(self.intent or {}, sort_keys=True)
        self.intent, self.intent_turn = new, turn
        if changed:
            self.stale_turns = self.steps_since_intent = 0
        else:
            self.stale_turns += 1

    # supply_orders(): inherited scripted logistics (dumps follow the advance).


# --- prompts ----------------------------------------------------------------

_RULES = ("The Campaign for North Africa, a hex wargame. Hexes are axial [q,r]. "
          "Enemy stacks are seen only as presence + stacking_points (limited "
          "intelligence). The engine rejects illegal orders, so state your intent.")


def build_movement_prompt(obs: dict) -> str:
    obj = obs["objective"]
    # CAMPAIGN vs RUSH framing, keyed on the observation carrying the rule-64.73 victory
    # cities (present only under CampaignVictory; see observation.observe). The campaign is a
    # POSITIONAL, LOGISTICAL game -- hold the cities you can keep SUPPLIED -- so its mission,
    # movement directive and supply caution are reframed away from racing the single far
    # objective. Rommel's Arrival carries no victory_cities, so it takes the else branch and
    # its prompt (byte-locked by the staff-on-rommel tests) is reproduced verbatim.
    if obs.get("victory_cities"):
        head = (f"MISSION (rule 64.73): the campaign is decided by which VICTORY CITIES each "
                f"side HOLDS SUPPLIED at the final turn, not by reaching one far hex. The "
                f"victory_cities list gives each city's vp (your points for holding it), "
                f"controlled_by, and held_supplied (who holds it with a supplied unit -- only "
                f"a supplied holder scores). Hex {obj['hex']} is a direction, not the prize.")
        directive = ("FIRST, garrison every victory city with supply_on_hex true -- a stocked "
                     "friendly dump stands ON it, so a combat unit there is supplied by definition "
                     "and BANKS its vp: those are points you already own, and leaving them empty "
                     "scores nothing. THEN advance only as far as your supply follows. A unit whose "
                     "can_hold is false has outrun its fuel/ammo -- consolidate it back onto a "
                     "suppliable line rather than pressing deeper. Keep stacks together.")
        supply_note = ("A unit that outruns its supply, or a city you take but cannot keep "
                       "supplied, scores NOTHING (64.73) -- prefer a shorter line you can hold; "
                       "can_hold is whether a unit can trace BOTH fuel and ammo to hold ground "
                       "(distinct from ammo-only defensible). CRITICAL: a supply dump can only "
                       "advance onto a hex held by one of your combat units (32.33), so it CANNOT "
                       "follow a spearhead that races off alone -- if you sprint every unit forward, "
                       "your dumps strand behind you and your whole army goes unsupplied for the "
                       "rest of the war. Keep units back along the line so the dumps can leapfrog. ")
    else:
        head = (f"Objective: hex {obj['hex']} (controlled by "
                f"{obj['controlled_by']}); aim to control it by the final turn.")
        directive = "Advance toward the objective and keep stacks together."
        supply_note = ""
    return (
        f"You command the {obs['your_side']} forces. {_RULES}\n"
        f"MOVEMENT phase, game-turn {obs['turn']}/{obs['max_turns']}, "
        f"Operations Stage {obs['stage']}/3, weather "
        f"{obs['weather']}. {head}\n"
        f"Situation (JSON):\n{json.dumps(obs)}\n"
        "For each combat unit you move, pick its destination FROM that unit's "
        "can_move_to list (those are the only hexes it can legally reach this turn; "
        "lower dist = closer to the objective). NEVER invent a hex not in can_move_to, "
        "and SKIP any unit whose can_move_to is empty or that carries a cannot_move "
        f"field -- it cannot act this turn. {directive} Combined arms: units with a "
        "'barrage' (artillery) or "
        "'anti_armor' (guns/tanks) rating automatically bombard ADJACENT enemies -- "
        "move them onto a can_move_to hex marked firing_position to soften a target "
        "before assaulting it. Tanks (is_tank) need at least an equal infantry "
        "strength stacked with them or they lose close-assault power. Supply: a unit "
        "with supplied:false cannot move this turn; supply_contended:true means its "
        "dump is oversubscribed, so prioritise -- not every contended unit gets fuel. "
        f"{supply_note}"
        "Don't exceed stack_limit stacking points on one hex (a destination's "
        "points_used is the SP already there).\n"
        'Reply with ONLY JSON: {"reasoning":"one sentence","moves":'
        '[{"unit":"<id>","to":[q,r]}]}. Use a [q,r] taken from that unit\'s '
        "can_move_to; omit units that should hold.")


def build_combat_prompt(obs: dict) -> str:
    return (
        f"You command the {obs['your_side']} forces. {_RULES}\n"
        f"COMBAT phase, game-turn {obs['turn']}/{obs['max_turns']}, "
        f"Operations Stage {obs['stage']}/3. Close-assault "
        f"using attack_options: each entry gives a target hex, the your_attackers "
        f"adjacent to it, and the enemy_stacking_points there. Attack where your "
        f"attackers outweigh the defender. A unit with defensible:false is out of ammo "
        f"and defends at 0 strength, so don't leave such units exposed adjacent to the "
        f"enemy.\nSituation (JSON):\n{json.dumps(obs)}\n"
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


def _reasoning(text: str) -> str:
    """The model's one-line 'reasoning' field, for the hybrid mode's carried plan."""
    r = _extract_json(text).get("reasoning")
    return r if isinstance(r, str) else ""


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
