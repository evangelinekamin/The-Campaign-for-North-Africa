"""Role-scoped observations for an agent (brief §4.5, §8).

What a side's Front Commander sees this phase, as a JSON-safe dict an LLM (or any
policy) can reason over. Honors CNA limited intelligence (rule 3.6): your own
units are fully visible, but the enemy is seen only as STACK PRESENCE — a hex, its
stacking-point total and unit count — never their exact strengths, ratings, or
identities. (This corrects the design brief's "open information" assumption; see
memory: limited-intelligence-contradicts-brief.)

Crucially the view is ACTIONABLE: in the movement phase each unit is given the
legal hexes it can actually reach this OpStage (nearest-to-objective first), and in
the combat phase the adjacent enemy stacks it could assault. That is information,
not a constraint — the engine still validates every order (brief §3.3, engine-
boundary validation, not constrained decoding) — but without it an agent just
guesses destinations beyond its move budget and gets everything rejected.

Hexes are axial (q, r) — the same coordinates orders use — with a precomputed
distance-to-objective so the agent can tell which way is forward.
"""
from __future__ import annotations

from . import tactics
from .events import Phase, Side
from .hexmap import distance, neighbors
from .state import GameState

REACH_LIMIT = 8            # legal destinations offered per unit (nearest to objective)


def _other(side: Side) -> Side:
    return Side.ALLIED if side == Side.AXIS else Side.AXIS


def observe(state: GameState, side: Side) -> dict:
    target = state.target_hex
    moving = state.phase == Phase.MOVEMENT
    enemy_zoc, enemy_occ = tactics.enemy_zoc_and_occupied(state, side) if moving else (None, None)

    def unit_view(u) -> dict:
        v = {
            "id": u.id,
            "hex": list(u.hex),
            "dist_to_objective": distance(u.hex, target),
            "strength": u.strength,
            "cpa": u.cpa,
            "cp_left": round(u.cpa - u.cp_used, 1),
            "oca": u.oca,
            "dca": u.dca,
            "mobility": u.mobility.name,
            "is_combat": u.is_combat,
        }
        if moving and u.is_combat:
            reach = tactics.reachable_for(state, u, enemy_zoc, enemy_occ)
            dests = sorted((h for h in reach if h != u.hex), key=lambda h: distance(h, target))
            v["can_move_to"] = [{"hex": list(h), "dist": distance(h, target)}
                                for h in dests[:REACH_LIMIT]]
        return v

    # Limited intelligence: aggregate the enemy to per-hex stack sightings only.
    sightings: dict = {}
    for e in state.living(_other(side)):
        s = sightings.setdefault(e.hex, {
            "hex": list(e.hex), "dist_to_objective": distance(e.hex, target),
            "stacking_points": 0, "unit_count": 0,
        })
        s["stacking_points"] += e.stacking_points
        s["unit_count"] += 1

    # Combat phase: which enemy stacks a friendly unit is adjacent to (can assault).
    attack_options: list = []
    if state.phase == Phase.COMBAT:
        by_target: dict = {}
        for u in state.living(side):
            if u.is_combat:
                for nb in neighbors(u.hex):
                    if state.enemies_at(nb, side):
                        by_target.setdefault(nb, []).append(u.id)
        for tgt, ids in sorted(by_target.items()):
            pts = sum(e.stacking_points for e in state.enemies_at(tgt, side))
            attack_options.append({"target": list(tgt), "your_attackers": ids,
                                   "enemy_stacking_points": pts})

    return {
        "turn": state.turn,
        "max_turns": state.max_turns,
        "phase": state.phase.value,
        "weather": state.weather,
        "your_side": side.value,
        "objective": {"hex": list(target), "controlled_by": state.control_of(target).value},
        "your_units": [unit_view(u) for u in state.living(side)],
        "your_supplies": [
            {"id": s.id, "hex": list(s.hex), "ammo": s.ammo, "fuel": s.fuel}
            for s in state.active_supplies(side)
        ],
        "enemy_sightings": sorted(sightings.values(), key=lambda s: s["hex"]),
        "attack_options": attack_options,
    }
