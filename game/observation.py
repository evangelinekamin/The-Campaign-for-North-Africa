"""Role-scoped observations for an agent (brief §4.5, §8).

What a side's Front Commander sees this phase, as a JSON-safe dict an LLM (or any
policy) can reason over. Honors CNA limited intelligence (rule 3.6): your own
units are fully visible, but the enemy is seen only as STACK PRESENCE — a hex, its
stacking-point total and unit count — never their exact strengths, ratings, or
identities. (This corrects the design brief's "open information" assumption; see
memory: limited-intelligence-contradicts-brief.)

Hexes are axial (q, r) — the same coordinates orders use — with a precomputed
distance-to-objective so the agent can tell which way is forward without knowing
the lattice. The engine still validates every order the agent returns, so the
observation is guidance, not a constraint.
"""
from __future__ import annotations

from .events import Side
from .hexmap import distance
from .state import GameState


def _other(side: Side) -> Side:
    return Side.ALLIED if side == Side.AXIS else Side.AXIS


def observe(state: GameState, side: Side) -> dict:
    target = state.target_hex

    def unit_view(u) -> dict:
        return {
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

    # Limited intelligence: aggregate the enemy to per-hex stack sightings only.
    sightings: dict = {}
    for e in state.living(_other(side)):
        s = sightings.setdefault(e.hex, {
            "hex": list(e.hex),
            "dist_to_objective": distance(e.hex, target),
            "stacking_points": 0,
            "unit_count": 0,
        })
        s["stacking_points"] += e.stacking_points
        s["unit_count"] += 1

    return {
        "turn": state.turn,
        "max_turns": state.max_turns,
        "phase": state.phase.value,
        "weather": state.weather,
        "your_side": side.value,
        "objective": {
            "hex": list(target),
            "controlled_by": state.control_of(target).value,
        },
        "your_units": [unit_view(u) for u in state.living(side)],
        "your_supplies": [
            {"id": s.id, "hex": list(s.hex), "ammo": s.ammo, "fuel": s.fuel}
            for s in state.active_supplies(side)
        ],
        "enemy_sightings": sorted(sightings.values(), key=lambda s: s["hex"]),
    }
