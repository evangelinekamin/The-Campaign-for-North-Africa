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

from . import stacking, supply, tactics
from .events import Phase, Side
from .hexmap import distance, neighbors
from .state import GameState

REACH_LIMIT = 6            # legal destinations offered per unit (nearest to objective)
SIGHTING = 2              # flat sighting radius (hexes) -- the v1 fog-of-presence dial


def _other(side: Side) -> Side:
    return Side.ALLIED if side == Side.AXIS else Side.AXIS


def _sighted_hexes(state: GameState, side: Side) -> set:
    """The hexes within SIGHTING (hex distance) of ANY living friendly unit of
    `side` -- the fog-of-presence seam. A flat graph radius today (BFS over
    neighbors); a per-unit sighting range or true line-of-sight drops in here
    later without touching the observation schema."""
    sighted: set = set()
    for u in state.living(side):
        ring = {u.hex}
        sighted |= ring
        for _ in range(SIGHTING):
            ring = {n for h in ring for n in neighbors(h)} - sighted
            sighted |= ring
    return sighted


def observe(state: GameState, side: Side, reveal_all: bool = False) -> dict:
    target = state.target_hex
    moving = state.phase == Phase.MOVEMENT
    enemy_zoc, enemy_occ = tactics.enemy_zoc_and_occupied(state, side) if moving else (None, None)
    roster = state.living(side) if moving else None    # phase-start snapshot the engine also uses

    # Fuel is a SHARED, drainable dump resource: each unit's plan_draw succeeds
    # independently, but if a dump's total demand exceeds its fuel only some of the
    # units drawing on it actually move. Flag those as contended so the agent knows
    # to prioritise rather than trusting every "supplied" unit will move.
    fuel_ok: set = set()
    contended: set = set()
    friendly_sp: dict = {}          # stacking points already on each friendly hex (B3)
    if moving:
        for u in roster:
            friendly_sp[u.hex] = friendly_sp.get(u.hex, 0) + u.stacking_points
        dump_fuel = {s.id: s.fuel for s in state.supplies if s.side == side}
        demand: dict = {}
        dump_of: dict = {}
        for u in state.living(side):
            if not u.is_combat or u.cp_used > 0:
                continue
            draws = supply.plan_draw(state, u, supply.FUEL, supply.fuel_cost(u))
            if draws:
                fuel_ok.add(u.id)
                did = draws[0][0]
                demand[did] = demand.get(did, 0) + supply.fuel_cost(u)
                dump_of[u.id] = did
        contended = {uid for uid, did in dump_of.items() if demand[did] > dump_fuel.get(did, 0)}

    def unit_view(u) -> dict:
        # Lean view: cpa/cp_left/mobility are redundant with can_move_to (which
        # already encodes what this unit can reach this OpStage), so they're omitted
        # to keep the prompt -- and the benchmark's token cost -- down.
        v = {
            "id": u.id,
            "hex": list(u.hex),
            "dist_to_objective": distance(u.hex, target),
            "strength": u.strength,
            "oca": u.oca,
            "dca": u.dca,
        }
        # Combat arm, surfaced only when non-zero so the agent can place its
        # support weapons: barrage (artillery) + anti_armor auto-fire at ADJACENT
        # enemies (range 1); armor/tanks are the anti-armor targets.
        for key, val in (("barrage", u.barrage), ("anti_armor", u.anti_armor),
                         ("armor_protection", u.armor_protection)):
            if val:
                v[key] = val
        if u.is_tank:
            v["is_tank"] = True
        # Defensive-supply: a unit that can't draw ammo defends at ZERO strength (it
        # still takes losses). Surfacing this lets the agent avoid parking unarmed
        # units where they'll be sortied (32.21 / 15.15).
        if u.is_combat:
            v["defensible"] = supply.plan_draw(
                state, u, supply.AMMO, supply.ammo_cost(u, phasing=False)) is not None
        if moving and u.is_combat:
            # A unit whose first move can't draw fuel is out of supply -- it cannot
            # move this OpStage, so offer no destinations (32.23). Reflecting this
            # keeps the agent from wasting orders on stranded units.
            supplied = u.cp_used > 0 or u.id in fuel_ok
            v["supplied"] = supplied
            if u.id in contended:
                v["supply_contended"] = True     # dump oversubscribed; may not get fuel
            if supplied:
                reach = tactics.reachable_for(state, u, enemy_zoc, enemy_occ, roster)
                dests = sorted((h for h in reach if h != u.hex), key=lambda h: distance(h, target))
                support = u.barrage > 0 or u.anti_armor > 0
                entries = []
                for h in dests[:REACH_LIMIT]:
                    e = {"hex": list(h), "dist": distance(h, target)}
                    if friendly_sp.get(h):
                        e["points_used"] = friendly_sp[h]   # already-stacked SP here (B3)
                    if support and any(state.enemies_at(nb, side) for nb in neighbors(h)):
                        e["firing_position"] = True   # barrage / anti-armor fires from here
                    entries.append(e)
                v["can_move_to"] = entries
        return v

    # Limited intelligence: aggregate the enemy to per-hex stack sightings only.
    # Fog of presence: unless reveal_all (the viewer/god-view), an enemy stack is
    # listed only when it stands on a hex this side can currently see (within
    # SIGHTING of a living friendly). Unsighted stacks are simply omitted.
    sighted = None if reveal_all else _sighted_hexes(state, side)
    sightings: dict = {}
    for e in state.living(_other(side)):
        if sighted is not None and e.hex not in sighted:
            continue
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
            # Only offer a unit as an attacker if it can draw ammunition -- an
            # out-of-ammo unit cannot assault (32.21), so listing it just invites a
            # rejected order.
            if not u.is_combat or supply.plan_draw(
                    state, u, supply.AMMO, supply.ammo_cost(u, phasing=True)) is None:
                continue
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
        "stack_limit": stacking.DEFAULT_HEX_LIMIT,
        "objective": {"hex": list(target), "controlled_by": state.control_of(target).value},
        "your_units": [unit_view(u) for u in state.living(side)],
        "your_supplies": [
            {"id": s.id, "hex": list(s.hex), "ammo": s.ammo, "fuel": s.fuel}
            for s in state.active_supplies(side)
        ],
        "enemy_sightings": sorted(sightings.values(), key=lambda s: s["hex"]),
        "attack_options": attack_options,
    }
