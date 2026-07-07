"""The narrator: a deterministic diary over a recorded staff log + the god-view fog
diff (design Steps 8-9).

Step 8 -- the fog god-view split. Every seat already reasons off
observe(reveal_all=False) (fogged; the flat SIGHTING=2 dial); the narrator alone
reads observe(reveal_all=True) (god-view). hidden_from_staff is the computable
staff-vs-viewer irony: the enemy stacks the audience is shown that the commander's
own map cannot -- the stacks standing outside SIGHTING of every friendly unit.

Step 9 -- the diary. A PURE query over the RECORDED log the engine already
produced: NO LLM, no authored content. Every DiaryLine anchors to a specific event
seq, and a warning line also carries the downstream seq that vindicates or refutes
it (its `refs`). The narrator never touches the engine, the RNG, or the board -- it
folds nothing and rolls nothing; a frontier prose pass over these grounded lines is
reserved for later.

The devices, each traced to real events:
  * named STAKES         -- STAFF_INTENT, deduped to each reframing (before outcomes).
  * the FUEL-STARVATION  -- a panzer FUEL SUPPLY_CONSUMED that leaves a trailing
    chain                   formation's ORDER_REJECTED with no fuel to move.
  * DISSENT quotes       -- STAFF_DISSENT, resolved to the downstream no-fuel reject
                            that vindicates the protest (or noted refuted if none).
  * the VERDICT          -- the final VICTORY_CHECKED (and last COMBAT_RESOLVED),
                            read back against the opening intent's objective.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import supply
from .events import Event, EventKind, Side
from .observation import observe
from .staff import MOBILE_FORMATIONS, lane_of
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


# --- Step 9: the diary --------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DiaryLine:
    """One grounded diary beat. `seq` is the event it is anchored to; `refs` are the
    downstream/linked event seqs (a warning's vindication, a chain's cause) -- so every
    line traces, and a claim's payoff traces too."""
    seq: int
    turn: int
    beat: str                       # fog | stakes | starvation | dissent | verdict
    text: str
    refs: tuple[int, ...] = ()


def _is_fuel_consume(e: Event) -> bool:
    return e.kind == EventKind.SUPPLY_CONSUMED and e.payload.get("commodity") == supply.FUEL


def _is_no_fuel_reject(e: Event) -> bool:
    """A UNIT's move rejected for want of fuel -- the trailing-formation end of the
    starvation chain. A dump's own 'out of fuel to move' relocation is a different beat
    (no unit stalls), so restrict to move orders, which always name a unit_id."""
    return (e.kind == EventKind.ORDER_REJECTED
            and e.payload.get("order") == "move"
            and "fuel" in str(e.payload.get("reason", "")).lower())


def _staff_side(events: list[Event]) -> Side:
    """The side whose staff authored the log (the STAFF_* events' side), defaulting to
    the Axis -- StaffPolicy's default seat."""
    for e in events:
        if e.kind.name.startswith("STAFF_"):
            return e.side
    return Side.AXIS


def _intent_text(p: dict) -> str:
    parts = [f"the Chief sets the stakes -- {p.get('objective') or 'hold the line'}"]
    if p.get("scheme"):
        parts.append(f"scheme: {p['scheme']}")
    if p.get("risks"):
        parts.append(f"foreseen risk: {p['risks']}")
    return ". ".join(parts) + "."


def _fog_line(result) -> list[DiaryLine]:
    """The opening irony: how many enemy stacks stand on the board already, unseen by
    the staff -- anchored to GAME_INITIALIZED (the log's first fact)."""
    if not result.events:
        return []
    opener = result.events[0]
    hidden = hidden_from_staff(result.initial, _staff_side(result.events))
    if not hidden:
        return []
    return [DiaryLine(opener.seq, opener.turn, "fog",
                      f"The staff open blind: {len(hidden)} enemy stack(s) already on "
                      f"the board, none yet within sight.")]


def _stakes_lines(events: list[Event]) -> list[DiaryLine]:
    """Each STAFF_INTENT, deduped to the moments the frame actually changes: one line
    per reframing, so a stable intent is stated once and a shift re-states the stakes."""
    out: list[DiaryLine] = []
    last_key = None
    for e in events:
        if e.kind != EventKind.STAFF_INTENT:
            continue
        p = e.payload
        key = (p.get("objective"), p.get("scheme"), p.get("risks"))
        if key == last_key:
            continue
        last_key = key
        out.append(DiaryLine(e.seq, e.turn, "stakes", f"Turn {e.turn}: {_intent_text(p)}"))
    return out


def _starvation_lines(events: list[Event], by_id: dict) -> list[DiaryLine]:
    """The fuel-starvation chain: within an Operations Stage a panzer FUEL
    SUPPLY_CONSUMED drains the shared dump, then a trailing formation's move is
    ORDER_REJECTED for want of fuel. One line per (turn, stage) group, anchored to the
    first starved order, referencing the panzer draw that emptied the dump."""
    out: list[DiaryLine] = []
    groups: dict[tuple[int, int], list[Event]] = {}
    for e in events:
        if _is_no_fuel_reject(e):
            groups.setdefault((e.turn, e.stage), []).append(e)
    for (turn, stage), rejects in sorted(groups.items()):
        first = min(rejects, key=lambda e: e.seq)
        # the nearest panzer fuel draw in this same stage that preceded the starvation
        draw = max((e for e in events
                    if _is_fuel_consume(e) and (e.turn, e.stage) == (turn, stage)
                    and e.seq < first.seq
                    and getattr(by_id.get(e.payload.get("unit_id")), "formation", None)
                    in MOBILE_FORMATIONS),
                   key=lambda e: e.seq, default=None)
        if draw is None:
            continue                                    # no panzer draw to blame; no chain
        u = by_id.get(first.payload.get("unit_id"))
        who = getattr(u, "formation", None) or first.payload.get("unit_id", "a unit")
        n = len(rejects)
        tail = f"{n} trailing unit(s) found no fuel" if n > 1 else "the trailing unit found no fuel"
        out.append(DiaryLine(
            first.seq, turn, "starvation",
            f"Turn {turn}.{stage}: the panzers drank the dump first (seq {draw.seq}); "
            f"{tail} to move -- {who} stalled.",
            refs=(draw.seq,)))
    return out


def _dissent_lines(events: list[Event], by_id: dict) -> list[DiaryLine]:
    """Each STAFF_DISSENT quoted, then resolved: the first downstream no-fuel reject of
    the DENIED formation (or, failing that, any Infantry-lane unit) vindicates the
    protest -- 'the Infantry GOC warned the fuel would not reach' resolving to a concrete
    later event. With no such reject the protest is noted refuted."""
    out: list[DiaryLine] = []
    for e in events:
        if e.kind != EventKind.STAFF_DISSENT:
            continue
        p = e.payload
        denied = p.get("formation")
        vindicator = _first_starved(events, by_id, after=e.seq, formation=denied)
        stance = p.get("stance", "the corps protests the priority")
        against = p.get("against", "the ruling")
        head = f'Turn {e.turn}: {denied or "a corps"} dissents -- "{stance}" (against {against})'
        if vindicator is not None:
            who = getattr(by_id.get(vindicator.payload.get("unit_id")), "formation", None) \
                or vindicator.payload.get("unit_id", "the unit")
            out.append(DiaryLine(
                e.seq, e.turn, "dissent",
                f"{head} -- vindicated turn {vindicator.turn}: {who} found no fuel (seq "
                f"{vindicator.seq}).", refs=(vindicator.seq,)))
        else:
            out.append(DiaryLine(e.seq, e.turn, "dissent",
                                 f"{head} -- refuted: the corps got its fuel after all."))
    return out


def _first_starved(events, by_id, *, after: int, formation: str | None) -> Event | None:
    """The first no-fuel reject after `after` for `formation` (else any Infantry-lane
    unit) -- the concrete event that a fuel dissent resolves to."""
    named = None
    for e in events:
        if e.seq <= after or not _is_no_fuel_reject(e):
            continue
        u = by_id.get(e.payload.get("unit_id"))
        if u is None:
            continue
        if formation and u.formation == formation:
            return e
        if named is None and lane_of(u).name == "INFANTRY":
            named = e
    return named


def _verdict_lines(events: list[Event]) -> list[DiaryLine]:
    """The reckoning: the final VICTORY_CHECKED read back against the opening intent's
    objective, referencing that intent and the last close-assault (COMBAT_RESOLVED) so
    the scheme's payoff or refutation traces both to the decision and to the fighting."""
    victories = [e for e in events if e.kind == EventKind.VICTORY_CHECKED]
    if not victories:
        return []
    v = victories[-1]
    intent = next((e for e in events if e.kind == EventKind.STAFF_INTENT), None)
    combats = [e for e in events if e.kind == EventKind.COMBAT_RESOLVED]
    objective = (intent.payload.get("objective") if intent else None) or "the objective"
    refs = tuple(e.seq for e in (intent, combats[-1] if combats else None) if e is not None)
    reach = v.payload.get("axis_reach")
    verdict = "held" if v.payload.get("axis", 0) >= 100 else "fell short"
    return [DiaryLine(
        v.seq, v.turn, "verdict",
        f"Verdict turn {v.turn}: the intent aimed to {objective}; the drive closed at "
        f"Axis advance {v.payload.get('axis', 0)}% (reach {reach}) -- the scheme {verdict}.",
        refs=refs)]


def diary(result) -> list[DiaryLine]:
    """The full diary over a recorded RunResult, chronological (by anchor seq). Pure: it
    reads result.initial (for the god-view fog beat) and result.events; it never runs the
    engine. Every line anchors to a real event seq, and every ref is a real downstream
    seq -- the projection is entirely traceable back to the log."""
    events = result.events
    by_id = {u.id: u for u in result.initial.units}
    lines = (_fog_line(result)
             + _stakes_lines(events)
             + _starvation_lines(events, by_id)
             + _dissent_lines(events, by_id)
             + _verdict_lines(events))
    return sorted(lines, key=lambda ln: ln.seq)
