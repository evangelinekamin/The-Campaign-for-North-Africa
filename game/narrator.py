"""The narrator: the god-view side of the fog split (design Step 8), and -- from
Step 9 -- a deterministic diary over the recorded staff log.

Step 8 -- the fog god-view split. Every seat already reasons off
observe(reveal_all=False) (fogged; the flat SIGHTING=2 dial); the narrator alone
reads observe(reveal_all=True) (god-view). hidden_from_staff is the computable
staff-vs-viewer irony: the enemy stacks the audience is shown that the commander's
own map cannot -- the stacks standing outside SIGHTING of every friendly unit. The
narrator never touches the engine, the RNG, or the board.
"""
from __future__ import annotations

from .events import Side
from .observation import observe
from .state import GameState


# --- Step 8: the fog god-view split ------------------------------------------

def hidden_from_staff(state: GameState, side: Side) -> list[dict]:
    """The enemy stacks the god-view sees but `side`'s fogged staff cannot: the stacks
    outside SIGHTING, absent from every seat's brief yet plain to the narrator. A pure
    diff of two observe() calls (reveal_all=True minus the fogged default), ordered by
    hex like observe() -- the staff-vs-viewer irony as a computable list."""
    fogged = {tuple(s["hex"]) for s in observe(state, side)["enemy_sightings"]}
    return [s for s in observe(state, side, reveal_all=True)["enemy_sightings"]
            if tuple(s["hex"]) not in fogged]
