#!/usr/bin/env python3
"""GATE C -- THE FIRST HONEST BALANCE READING: a DISTRIBUTION over N >= 30 campaign seeds.

    python3 scripts/gate_c.py --seeds 3                     # smoke: seeds 1-3, ~1 campaign of wall
    python3 scripts/gate_c.py                               # the gate: seeds 1-30, 14 workers
    python3 scripts/gate_c.py --seed 4 1941 7               # an explicit panel
    python3 scripts/gate_c.py --arm cw-max-aggression       # the control arm (see THE ARM below)

WHY THIS EXISTS. Every campaign claim this project has made was a SINGLE SEED, and tests/baselines.py
(CAMPAIGN_SEED) already wrote down what that costs: "one lost combat on one hex, in roughly one
campaign in four, and the Commonwealth's whole logistical spine is gone... THE REAL FIX IS
METHODOLOGICAL, and it is the plan's own Phase 0.3: a campaign claim must be a DISTRIBUTION OVER
N >= 30 SEEDS, not one run." 00-THE-PORT-PLAN.md:1571 makes that the gate itself -- "After PHASE 8.
N >= 30 seeds. Report a distribution, not a seed."

The standing finding this is built to test: Tier-2 (22.3, 56.3, 54.4, 30.5) each improved the
NARRATIVE and none moved the SCOREBOARD -- every campaign seed ends Axis Smashing Victory and the
per-item A/B shifts are random in sign. Gate C asks whether that is the ENGINE or the POLICIES, so it
reports the SHAPE of the result (which 64.7 condition decided it, how far the Axis got, what each army
ate, what was left alive) beside the grade. A grade alone cannot tell those two apart.

NOTHING IS TUNED HERE. This driver only reads. It runs the scripted policies exactly as
scripts/measure_campaign.py and scripts/parity_harness.py fold them, changes no rule, and writes no
state back into the engine.

THE SEED PANEL IS 1..N, UNSHOPPED, AND THAT IS THE POINT. A distribution taken over a curated list of
"canonical" seeds is a distribution over seeds somebody once found interesting; the baselines note
above measured its own claims over "seeds 1..24" and "seeds 1..40" for exactly that reason. 1..N also
gives the prefix property: `--seeds 3` is the first three ROWS of `--seeds 30`, so a smoke run's
numbers are literally a subset of the gate's, and it contains CAMPAIGN_SEED=4 and the canonical 1/7.

THE ARM SELECTS THE POLICIES. `--arm` names a row of the ARMS registry below, and that row supplies
the two policy factories the campaign is actually fought with: 'scripted' is the shipped pair,
'cw-max-aggression' is the same pair with ONE knob turned (the Commonwealth's own OffensiveSchedule,
opened from its three historical windows to every Game-Turn). It was a bare LABEL until 2026-08-01,
and what ended that is the question the arms exist to ask: the scripted sweep found the Commonwealth
forfeiting ~330 Victory Points BY ABSENCE -- no CW combat unit stands on Siwa, Jalo, Bardia, Tobruk,
Derna or Benghazi at GT111 on any of 30 seeds -- while ending every war with 2.0x the Axis combat
units. Is it absent because the ENGINE will not let it take ground, or because the POLICY never
tries? A label cannot ask that; a policy factory can.

WHAT THE OLD LABEL WAS GUARDING AGAINST STILL HOLDS, and is now guarded by the output rather than by
impotence. scripts/measure_malta.py records what a driver that announces a posture it does not apply
costs (the deleted `--discretionary-pct` knob: it printed a ruling, patched a key nothing read, and
changed not one die). So an unknown arm is an ERROR and not a label, and every output carries the
`policies` block naming the classes ACTUALLY constructed beside the arm's own one-line statement of
what it changes -- a mislabelled arm is still caught by reading the file it wrote.

AND AN ARM IS A CONTROL, NOT A TUNING. Nothing here edits a rule, a chart or a number; an arm may
only reach for a seam the policy already exposes to its own constructor. cw-max-aggression turns
CampaignCommonwealthPolicy's `schedule` argument, whose docstring already says what an empty window
list means -- so the arm is the same code the campaign ships, asked to attack on 111 Game-Turns
instead of 28.

DETERMINISM. Each seed is a pure function of its seed: same seeds in, same numbers out. The process
pool only distributes independent runs. `--verify K` (default 2) re-runs the first K seeds a SECOND
time in the same sweep and asserts the two records are identical field for field -- so every sweep
carries its own determinism proof, and a break exits nonzero instead of being reported as a result.
The JSON separates the deterministic payload ("seeds", "aggregate") from the wall-clock and
provenance envelope ("timing", "git_head"), so two runs' payloads diff clean.

COST, MEASURED not estimated (3 seeds + 2 verify re-runs = 5 campaigns, 5 workers, 2026-08-01, HEAD
c567d3a): wall 390s, ~365 CPU-seconds per campaign, per-run 333-391s. So ONE campaign is ~6 minutes,
not the ~4 the older notes assume, and the sweep is one campaign per worker. Extrapolating to the
gate: 30 seeds + 2 verify = 32 jobs ~= 11,700 CPU-seconds; the box is 16 THREADS over 8 physical
cores, so 14 workers oversubscribe the cores and each run slows -- budget 25-40 minutes, not 15.
NEVER run this and the pytest suite at once.

A SEED THAT RAISES IS A RESULT, NOT A GAP. The worker returns the traceback, main prints a FAILED row,
the JSON keeps it under "failures", and the exit status is nonzero. A dropped seed would silently
bias the very distribution this exists to measure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from game import supply                                            # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,              # noqa: E402
                                  CampaignCommonwealthPolicy, OffensiveSchedule)
from game.campaign_victory import grade                            # noqa: E402
from game.engine import determinism_signature, run                 # noqa: E402
from game.events import EventKind, Side                            # noqa: E402
from game.scenario import campaign                                 # noqa: E402

DEFAULT_SEEDS = 30            # the plan's own floor for a campaign claim (00-THE-PORT-PLAN.md:1573)
DEFAULT_WORKERS = 14          # 16-thread box, shared: leave two threads for everything else
DEFAULT_VERIFY = 2            # re-run the first K seeds and prove the sweep reproduces itself

# [64.73] EVERY GAME-TURN IS AN OFFENSIVE ONE. OffensiveSchedule's windows are inclusive on
# state.turn and its own docstring makes the empty tuple "never offensive", so this is the far end of
# the same dial: the Commonwealth is on the offensive for the whole war, which is the posture
# CampaignAxisPolicy already holds ("It is on the offensive at all times"). Bounded far past
# max_turns rather than at 111 so the arm does not quietly depend on the scenario's length.
ALWAYS_OFFENSIVE = OffensiveSchedule(((1, 10 ** 9),))


@dataclass(frozen=True)
class Arm:
    """One measurable ARM of the gate: what it changes, in one line a later reader can check, and
    the two factories the campaign is actually fought with. The factories are called INSIDE the
    worker (only the arm's name crosses the process boundary), so no Policy is ever pickled."""
    what: str
    axis: object
    allied: object


ARMS = {
    "scripted": Arm(
        "the shipped campaign policies, unchanged -- the baseline every other arm is diffed against",
        CampaignAxisPolicy, CampaignCommonwealthPolicy),
    "cw-max-aggression": Arm(
        "IDENTICAL to 'scripted' but for one argument: the Commonwealth's OffensiveSchedule is "
        "opened from its three historical windows (Compass GT13-22, Crusader GT57-64, Alamein "
        "GT102-111 -- 28 of 111 Game-Turns) to EVERY Game-Turn. The Eighth Army therefore runs its "
        "attacker branch, drives on objective_for(ALLIED)=Benghazi, escorts its 32.33 desert columns "
        "and plans its supply against the objective instead of the railhead, for the whole war.",
        CampaignAxisPolicy, lambda: CampaignCommonwealthPolicy(ALWAYS_OFFENSIVE)),
}

SIDES = (Side.AXIS, Side.ALLIED)
AX, CW = Side.AXIS.value, Side.ALLIED.value

# The three event kinds that carry a unit to a new hex (game/apply.py: every other kind leaves
# Unit.hex alone), so between them they are the whole of "where the Axis got to".
_MOVE_KINDS = frozenset({EventKind.UNIT_MOVED, EventKind.REACTION_MOVED, EventKind.UNIT_RETREATED})

# The east-west axis of this map IS the axial r-coordinate (scripts/measure_campaign.py): Benghazi
# r=20, Tobruk 66, Sollum 76, Bardia 77, Sidi Barrani 86, Mersa Matruh 100, El Daba 113,
# El Hamman 124, Alexandria 133, Cairo 140.
_EAST_LEGEND = ("Benghazi r=20, Tobruk 66, Sollum 76, Sidi Barrani 86, Mersa Matruh 100, "
                "Alexandria 133, Cairo 140")


# --- one campaign, measured ---------------------------------------------------------------------

def _tons(points: dict) -> int:
    """[54.5] The tonnage an AGGREGATE per-commodity point count weighs, converted ONCE at the end.
    supply.points_to_tons CEILS, so summing it per event would inflate a war's haul by up to a ton
    per unload; the rates themselves (supply.TONS_PER_POINT) are the engine's own."""
    return round(sum(qty * supply.TONS_PER_POINT[c] for c, qty in points.items()))


def _harvest(initial, result) -> dict:
    """The structural metrics, in ONE pass over the log plus a read of the final board.

    Read off the EVENTS rather than by re-folding the state (scripts/measure_campaign.py folds; it
    needs mid-war snapshots and this does not), so the measurement costs one walk of a ~285,000-event
    list on top of a ~6-minute campaign instead of a second fold of the whole war.

    _MOVE_KINDS IS THE COMPLETE SET of kinds that relocate a unit -- verified against game/apply.py,
    where exactly three folds assign Unit.hex (UNIT_MOVED, REACTION_MOVED, UNIT_RETREATED); the other
    `hex=` folds move a dump, a truck formation or Rommel, none of which is a Unit. So the high-water
    mark cannot be understated by a movement path this misses.

    ATTRIBUTION. Event.side is the ACTING side, which is what supply/haul events want -- but a
    STEP_LOST is emitted by the side running the combat, so a surrender is attributed by the
    SURRENDERING UNIT's own side (initial.units), never by the emitter.

    THE ORDER_REJECTED CENSUS is what tells an army that DIED trying apart from one that never
    tried: every order the rules refused, counted per side by '<order kind>: <reason>'. Both halves
    of that key are static strings written at the emit site in game/engine.py (there are ~30 of them
    and none interpolates a unit, a hex or a quantity), so the catalogue is bounded and two arms'
    censuses are directly comparable. game/engine.py:6437 records the one known blind spot: the
    close-assault refusal is a single string standing for six distinct causes (ammo, Pin, water,
    marsh, anti-armor, Cohesion) and cannot say which fired."""
    side_of = {u.id: u.side.value for u in initial.units}
    axis_combat = {u.id for u in initial.units if u.side == Side.AXIS and u.is_combat}

    # The Axis high-water mark: the furthest-east hex any Axis COMBAT unit ever stood on. Seeded
    # from the GT1 setup (living() = on-map, rule 20) so an army that never moves still reports the
    # ground it started on, then carried forward by every hex any of them was moved to.
    east_reached = max((u.hex[1] for u in initial.living(Side.AXIS) if u.is_combat), default=0)

    from_dump = {AX: {}, CW: {}}          # SUPPLY_CONSUMED: drawn out of a supply dump
    from_pool = {AX: {}, CW: {}}          # UNIT_SUPPLY_CONSUMED: burnt from the unit's own in-hex pool
    hauled = {AX: {}, CW: {}}             # TRUCK_UNLOADED: the last mile, into a forward dump
    landed = {AX: {}, CW: {}}             # PORT_UNLOADED: the quay
    # SUPPLY_ARRIVED is THE FAUCET -- events.py calls it "the LOAD-BEARING dual of SUPPLY_CONSUMED":
    # it is what actually enters the system by sea, already net of the 41.66 interdiction skim.
    # PORT_UNLOADED is only its through-a-modelled-HARBOUR subset (engine._naval_convoys emits it
    # `if port is not None`), so reading the faucet off the quay alone reports the Commonwealth --
    # whose convoys land where this map carries no Port -- as landing NOTHING ALL WAR. It lands
    # plenty; it just does not land it through a harbour counter.
    arrived = {AX: {}, CW: {}}
    surrenders = {AX: {"events": 0, "steps": 0}, CW: {"events": 0, "steps": 0}}
    rejected = {AX: {}, CW: {}}           # ORDER_REJECTED: what the rules refused, by reason
    # Anything this attribution could not place on a side, counted rather than dropped: a
    # SYSTEM-emitted supply beat, or a step lost by a unit absent from the initial roster.
    unattributed: dict = {}

    def _add(bucket: dict, side: str, commodity: str, qty, kind: str) -> None:
        if side not in bucket:
            unattributed[f"{side}:{kind}"] = unattributed.get(f"{side}:{kind}", 0) + 1
            return
        bucket[side][commodity] = bucket[side].get(commodity, 0) + qty

    for e in result.events:
        k, p = e.kind, e.payload
        if k in _MOVE_KINDS:
            if p["unit_id"] in axis_combat:
                east_reached = max(east_reached, p["to"][1])
        elif k is EventKind.SUPPLY_CONSUMED:
            _add(from_dump, e.side.value, p["commodity"], p["qty"], k.value)
        elif k is EventKind.UNIT_SUPPLY_CONSUMED:
            _add(from_pool, e.side.value, p["commodity"], p["qty"], k.value)
        elif k is EventKind.TRUCK_UNLOADED:
            for commodity, qty in p["cargo"].items():
                _add(hauled, e.side.value, commodity, qty, k.value)
        elif k is EventKind.PORT_UNLOADED:
            _add(landed, e.side.value, p["commodity"], p["qty"], k.value)
        elif k is EventKind.SUPPLY_ARRIVED:
            for commodity, qty in p["cargo"].items():
                _add(arrived, e.side.value, commodity, qty, k.value)
        elif k is EventKind.ORDER_REJECTED:
            # engine._reject_rail is the one emit site with no "order" key (it refuses a rail order
            # before it has one to name), so it is labelled here rather than counted as an anomaly.
            key = f"{p.get('order', 'rail')}: {p.get('reason', '(no reason recorded)')}"
            book = rejected.get(e.side.value)
            if book is None:
                unattributed[f"{e.side.value}:{k.value}"] = (
                    unattributed.get(f"{e.side.value}:{k.value}", 0) + 1)
            else:
                book[key] = book.get(key, 0) + 1
        elif k is EventKind.STEP_LOST and p.get("role") == "surrender":
            side = side_of.get(p["unit_id"])
            if side in surrenders:
                surrenders[side]["events"] += 1
                surrenders[side]["steps"] += p.get("amount", 0)
            else:
                unattributed[f"{side}:SURRENDER"] = unattributed.get(f"{side}:SURRENDER", 0) + 1

    consumed = {s: {"dump": from_dump[s], "unit": from_pool[s]} for s in (AX, CW)}
    final = result.final
    army = {}
    for s in SIDES:
        live = final.living(s)
        combat = [u for u in live if u.is_combat]
        army[s.value] = {"units": len(live), "combat_units": len(combat),
                         "steps": sum(u.strength for u in combat)}
    axis_east_end = max((u.hex[1] for u in final.living(Side.AXIS) if u.is_combat), default=0)

    return {
        "axis_east_reached": east_reached,
        "axis_east_at_end": axis_east_end,
        "army_at_end": army,
        "surrenders": surrenders,
        # sorted by count so the file reads as a census, and so two arms' books line up by eye
        "order_rejected": {s: dict(sorted(rejected[s].items(), key=lambda kv: (-kv[1], kv[0])))
                           for s in rejected},
        "order_rejected_total": {s: sum(rejected[s].values()) for s in rejected},
        "supply_consumed": consumed,
        "truck_unloaded_points": hauled,
        "truck_unloaded_tons": {s: _tons(hauled[s]) for s in hauled},
        "port_landed_points": landed,
        "port_landed_tons": {s: _tons(landed[s]) for s in landed},
        "sea_arrived_points": arrived,
        "sea_arrived_tons": {s: _tons(arrived[s]) for s in arrived},
        "unattributed": unattributed,
    }


def _decided_by(reason: str) -> str:
    """Which clause of rule 64.7 ended this war: 64.71 (Axis auto-win), 64.72 (the Commonwealth's),
    or 64.76 (the game ran its span and was graded on the tally)."""
    for rule in ("64.71", "64.72", "64.76"):
        if rule in reason:
            return rule
    return "unknown"


def _grade_label(reason: str) -> str:
    """The grade, without its point tally: 'Axis Smashing Victory', 'Draw', 'Axis auto-victory'."""
    return "Draw" if reason.startswith("Draw") else reason.split(":")[0]


def _measure(job: tuple[str, int, int]) -> dict:
    """Run ONE campaign seed and return its record. `job` is (arm, seed, repeat) -- repeat is the
    --verify index and changes NOTHING about the run, which is the whole point of it.

    The scenario and the policies are constructed HERE, inside the worker, so only the (arm, seed,
    repeat) tuple and the plain-dict record cross the process boundary (parity_harness.py's idiom):
    no GameState, Policy or Event is ever pickled."""
    arm, seed, repeat = job
    t0 = time.perf_counter()
    try:
        initial = campaign(seed=seed)
        result = run(initial, ARMS[arm].axis(), ARMS[arm].allied())
        victory = result.final.victory
        view = SimpleNamespace(state=result.final, events=result.events)
        breakdown = victory.breakdown(view)
        axis_vp, cwlth_vp = breakdown["total"][AX], breakdown["total"][CW]
        decided = _decided_by(result.reason)
        # THE ACCESSOR IS CHECKED AGAINST THE ENGINE'S OWN VERDICT, every seed: CampaignVictory.
        # breakdown duplicates decide()'s 64.73 loop, so re-grading its totals must reproduce the
        # reason string the run actually ended on. Only asserted where 64.76 decided -- an auto-win
        # never ran decide() at all (the tally is still reported; it just did not settle the war).
        agrees = None if decided != "64.76" else grade(axis_vp, cwlth_vp)[1] == result.reason
        held = {s: [c["name"] for c in breakdown["cities"] if c["holder"] == s] for s in (AX, CW)}
        record = {
            "seed": seed,
            "repeat": repeat,
            "ok": True,
            "winner": None if result.winner is None else result.winner.value,
            "reason": result.reason,
            "grade": _grade_label(result.reason),
            "decided_by": decided,
            "axis_vp": axis_vp,
            "allied_vp": cwlth_vp,
            "margin": axis_vp - cwlth_vp,
            "victory_64_7": breakdown,
            "breakdown_agrees": agrees,
            "cities_held": {s: {"count": len(held[s]), "names": held[s]} for s in held},
            "final_turn": result.final.turn,
            "final_stage": result.final.stage,
            "events": len(result.events),
            "signature": hashlib.sha256(
                determinism_signature(result.events).encode()).hexdigest()[:12],
            **_harvest(initial, result),
        }
        return {"arm": arm, "seed": seed, "repeat": repeat, "wall_s": time.perf_counter() - t0,
                "record": record}
    except Exception as exc:                       # a seed that raises is a RESULT, never a drop
        return {"arm": arm, "seed": seed, "repeat": repeat, "wall_s": time.perf_counter() - t0,
                "record": {"seed": seed, "repeat": repeat, "ok": False,
                           "error": f"{type(exc).__name__}: {exc}",
                           "traceback": traceback.format_exc()}}


# --- the sweep ------------------------------------------------------------------------------------

def _sweep(jobs: list[tuple[str, int, int]], workers: int) -> list[dict]:
    """Run every job, printing each as it lands (a 30-seed sweep is ~15 minutes of silence
    otherwise). Results are returned in JOB order, not completion order, so the output file is
    independent of how the pool happened to schedule."""
    out: dict[tuple[str, int, int], dict] = {}
    if workers == 1:
        for job in jobs:
            res = _measure(job)
            out[job] = res
            _print_progress(res, len(out), len(jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_measure, job) for job in jobs]
            for fut in as_completed(futures):
                res = fut.result()
                out[(res["arm"], res["seed"], res["repeat"])] = res
                _print_progress(res, len(out), len(jobs))
    return [out[job] for job in jobs]


def _print_progress(res: dict, done: int, total: int) -> None:
    r = res["record"]
    tag = f"seed {res['seed']:<5}" + (f" (verify #{res['repeat']})" if res["repeat"] else "")
    if not r["ok"]:
        print(f"  [{done:>3}/{total}] {tag} FAILED  {r['error']}  {res['wall_s']:7.1f}s", flush=True)
        return
    print(f"  [{done:>3}/{total}] {tag:<22} {r['grade']:<28} "
          f"{_vp(r['axis_vp']):>7}-{_vp(r['allied_vp']):<7} {r['signature']}  "
          f"{r['events']:>7} ev  {res['wall_s']:7.1f}s", flush=True)


def _verify(results: list[dict]) -> dict:
    """The determinism proof: every seed run twice must produce an IDENTICAL record, field for
    field (the record excludes wall-clock by construction -- that lives in the timing envelope).
    Compares on the record with `repeat` removed, since that is the only field meant to differ."""
    firsts = {r["seed"]: r["record"] for r in results if r["repeat"] == 0}
    checked, mismatched = [], []
    for res in results:
        if res["repeat"] == 0:
            continue
        a = dict(firsts.get(res["seed"], {}))
        b = dict(res["record"])
        a.pop("repeat", None)
        b.pop("repeat", None)
        checked.append(res["seed"])
        if a != b:
            differing = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
            mismatched.append({"seed": res["seed"], "fields": differing})
    return {"seeds_rerun": checked, "identical": not mismatched, "mismatches": mismatched}


def _stats(values: list) -> dict:
    """mean / median / stdev / min / max of a sample. stdev is the SAMPLE stdev and needs two
    points; with one seed it is None rather than a fabricated 0."""
    if not values:
        return {"n": 0, "mean": None, "median": None, "stdev": None, "min": None, "max": None}
    return {"n": len(values),
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else None,
            "min": min(values), "max": max(values)}


def _tally(values: list) -> dict:
    counts: dict = {}
    for v in values:
        key = "None" if v is None else str(v)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _aggregate(records: list[dict]) -> dict:
    """The distribution -- the only thing Gate C is entitled to report. Computed over the SUCCEEDING
    seeds; the failures are counted separately and never silently thin the sample."""
    ok = [r for r in records if r["ok"]]
    if not ok:
        return {"seeds": 0}

    def col(path) -> list:
        return [path(r) for r in ok]

    per_side_consumed = {
        s: {c: _stats([r["supply_consumed"][s]["dump"].get(c, 0)
                       + r["supply_consumed"][s]["unit"].get(c, 0) for r in ok])
            for c in supply.COMMODITIES}
        for s in (AX, CW)}
    return {
        "seeds": len(ok),
        "by_winner": _tally(col(lambda r: r["winner"])),
        "by_grade": _tally(col(lambda r: r["grade"])),
        "by_deciding_rule": _tally(col(lambda r: r["decided_by"])),
        "axis_vp": _stats(col(lambda r: r["axis_vp"])),
        "allied_vp": _stats(col(lambda r: r["allied_vp"])),
        "margin": _stats(col(lambda r: r["margin"])),
        "geographic_64_73": {s: _stats(col(lambda r, s=s: r["victory_64_7"]["geographic_64_73"][s]))
                             for s in (AX, CW)},
        "replacement_64_74": {s: _stats(col(lambda r, s=s: r["victory_64_7"]["replacement_64_74"][s]))
                              for s in (AX, CW)},
        "withdrawal_64_75": {s: _stats(col(lambda r, s=s: r["victory_64_7"]["withdrawal_64_75"][s]))
                             for s in (AX, CW)},
        "final_turn": _stats(col(lambda r: r["final_turn"])),
        "events": _stats(col(lambda r: r["events"])),
        "axis_east_reached": _stats(col(lambda r: r["axis_east_reached"])),
        "axis_east_at_end": _stats(col(lambda r: r["axis_east_at_end"])),
        "cities_held": {s: _stats(col(lambda r, s=s: r["cities_held"][s]["count"])) for s in (AX, CW)},
        "combat_units_at_end": {s: _stats(col(lambda r, s=s: r["army_at_end"][s]["combat_units"]))
                                for s in (AX, CW)},
        "steps_at_end": {s: _stats(col(lambda r, s=s: r["army_at_end"][s]["steps"]))
                         for s in (AX, CW)},
        "surrender_events": {s: _stats(col(lambda r, s=s: r["surrenders"][s]["events"]))
                             for s in (AX, CW)},
        "surrender_steps": {s: _stats(col(lambda r, s=s: r["surrenders"][s]["steps"]))
                            for s in (AX, CW)},
        "order_rejected_total": {s: _stats(col(lambda r, s=s: r["order_rejected_total"][s]))
                                 for s in (AX, CW)},
        # Over the UNION of reasons seen on any seed, a seed that never emitted one counting 0 --
        # the seed ran, that refusal simply never fired, and dropping it would make the mean of a
        # rare rejection read as though it were common.
        "order_rejected_by_reason": {
            s: {reason: _stats([r["order_rejected"][s].get(reason, 0) for r in ok])
                for reason in sorted({k for r in ok for k in r["order_rejected"][s]})}
            for s in (AX, CW)},
        "truck_unloaded_tons": {s: _stats(col(lambda r, s=s: r["truck_unloaded_tons"][s]))
                                for s in (AX, CW)},
        "port_landed_tons": {s: _stats(col(lambda r, s=s: r["port_landed_tons"][s]))
                             for s in (AX, CW)},
        "sea_arrived_tons": {s: _stats(col(lambda r, s=s: r["sea_arrived_tons"][s]))
                             for s in (AX, CW)},
        "supply_consumed": per_side_consumed,
        "breakdown_disagreements": [r["seed"] for r in ok if r["breakdown_agrees"] is False],
    }


# --- the report -----------------------------------------------------------------------------------

def _n(v) -> str:
    """A number for a report column: thousands-separated, and never rounding a genuine fraction
    away (64.75 pays in half-points, and a mean of anything is a fraction)."""
    if v is None:
        return "--"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.2f}"
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def _vp(v) -> str:
    """A Victory-Point total for a table column, campaign_victory._fmt's convention: a whole total
    reads whole ('30', not '30.0'), a genuine 64.75-A half-point reads as itself."""
    return f"{int(v)}" if float(v).is_integer() else f"{v}"


def _stat_row(label: str, st: dict) -> str:
    return (f"    {label:<26} n={st['n']:<3} mean {_n(st['mean']):>12}  median {_n(st['median']):>12}"
            f"  sd {_n(st['stdev']):>10}  [{_n(st['min'])} .. {_n(st['max'])}]")


def _report(records: list[dict], agg: dict, verify: dict, arm: str, workers: int,
            wall: float, walls: list[float], out_path: Path) -> None:
    ok = [r for r in records if r["ok"]]
    bad = [r for r in records if not r["ok"]]

    print(f"\n=== GATE C -- arm '{arm}': {len(ok)} campaign(s) of GT1-111, "
          f"{type(ARMS[arm].axis()).__name__} vs {type(ARMS[arm].allied()).__name__} ===")
    print(f"    {ARMS[arm].what}\n")
    hdr = (f"{'seed':>5} {'winner':>7} {'grade':<28} {'AxVP':>7} {'CwVP':>7} "
           f"{'rule':>6} {'GT':>4} {'east':>9} {'cities':>7} {'surr':>9} {'signature':>13}")
    print(hdr)
    print("-" * len(hdr))
    for r in ok:
        east = f"{r['axis_east_reached']:>3}/{r['axis_east_at_end']:<3}"
        cities = f"{r['cities_held'][AX]['count']:>2}/{r['cities_held'][CW]['count']:<2}"
        surr = f"{r['surrenders'][AX]['events']:>4}/{r['surrenders'][CW]['events']:<4}"
        print(f"{r['seed']:>5} {str(r['winner']):>7} {r['grade']:<28} {_vp(r['axis_vp']):>7} "
              f"{_vp(r['allied_vp']):>7} {r['decided_by']:>6} {r['final_turn']:>4} {east:>9} "
              f"{cities:>7} {surr:>9} {r['signature']:>13}")
    print("      (east = furthest-east r reached / at end, Axis combat units.  "
          f"{_EAST_LEGEND})")
    print("      (cities = 64.73 cities held Axis/CW at the end -- by a SUPPLIED occupier, "
          "which is the rule's own test)")
    print("      (surr = surrender events Axis/CW, attributed to the surrendering unit's side)")

    if bad:
        print(f"\n!!! {len(bad)} SEED(S) RAISED -- the distribution below is missing them !!!")
        for r in bad:
            print(f"  seed {r['seed']:<5} {r['error']}")
            print("    " + "\n    ".join(r["traceback"].rstrip().splitlines()[-6:]))

    if not ok:
        print("\nno successful seed: nothing to aggregate.\n")
        return

    print(f"\n=== THE DISTRIBUTION (n={agg['seeds']}) ===")
    print(f"  by winner        {agg['by_winner']}")
    print(f"  by grade         {agg['by_grade']}")
    print(f"  by 64.7 clause   {agg['by_deciding_rule']}   "
          "(64.71 Axis auto-win / 64.72 CW auto-win / 64.76 the tally)")
    print("\n  VICTORY POINTS")
    for label, key in (("Axis VP", "axis_vp"), ("Commonwealth VP", "allied_vp"),
                       ("margin (Ax - CW)", "margin")):
        print(_stat_row(label, agg[key]))
    print("\n  THE 64.7 BREAKDOWN, per condition")
    for label, key in (("64.73 geographic", "geographic_64_73"),
                       ("64.74 replacement", "replacement_64_74"),
                       ("64.75 withdrawal", "withdrawal_64_75")):
        for s in (AX, CW):
            print(_stat_row(f"{label} {s}", agg[key][s]))
    if agg["breakdown_disagreements"]:
        print(f"\n  !!! FATAL: CampaignVictory.breakdown DISAGREES with the run's own 64.76 verdict "
              f"on seeds {agg['breakdown_disagreements']}.\n      The accessor is wrong -- decide() "
              "is the scoreboard. Do NOT trust the 64.7 numbers in this file.")
    else:
        agree = sum(1 for r in ok if r["breakdown_agrees"])
        print(f"\n    (the itemisation was re-graded and reproduced the engine's own verdict "
              f"verbatim on {agree} of {len(ok)} seeds; the rest were settled by 64.71/64.72, "
              "where decide() never ran)")

    print("\n  THE SHAPE OF THE WAR")
    print(_stat_row("game-turns run", agg["final_turn"]))
    print(_stat_row("events per campaign", agg["events"]))
    print(_stat_row("Axis east reached (r)", agg["axis_east_reached"]))
    print(_stat_row("Axis east at end (r)", agg["axis_east_at_end"]))
    for label, key in (("64.73 cities held", "cities_held"),
                       ("combat units alive", "combat_units_at_end"),
                       ("TOE steps alive", "steps_at_end"),
                       ("surrender events", "surrender_events"),
                       ("surrendered steps", "surrender_steps")):
        for s in (AX, CW):
            print(_stat_row(f"{label} {s}", agg[key][s]))

    print("\n  THE LOGISTICS: what entered the theatre, what reached the front (54.5 tons), what "
          "the army ate (Points)")
    for label, key in (("sea arrived tons", "sea_arrived_tons"),
                       ("  over a quay", "port_landed_tons"),
                       ("truck unloaded tons", "truck_unloaded_tons")):
        for s in (AX, CW):
            print(_stat_row(f"{label} {s}", agg[key][s]))
    for s in (AX, CW):
        for c in supply.COMMODITIES:
            print(_stat_row(f"consumed {c} {s}", agg["supply_consumed"][s][c]))
    print("      (sea arrived = SUPPLY_ARRIVED, THE FAUCET -- what entered the system by sea, net")
    print("       of the 41.66 skim. 'over a quay' is its PORT_UNLOADED subset, and the")
    print("       Commonwealth's is 0 by construction: its convoys land where no Port counter")
    print("       stands. truck unloaded = TRUCK_UNLOADED, the last mile into a forward dump.")
    print("       consumed = SUPPLY_CONSUMED off a dump + UNIT_SUPPLY_CONSUMED off the unit's own")
    print("       in-hex pool, which is where fuel/ammo/stores now live. EVAPORATION is not")
    print("       consumption and is not counted here.)")
    print("\n  WHAT THE RULES REFUSED (ORDER_REJECTED, per campaign, by reason)")
    for s in (AX, CW):
        print(_stat_row(f"orders rejected {s}", agg["order_rejected_total"][s]))
    for s in (AX, CW):
        book = agg["order_rejected_by_reason"][s]
        print(f"    -- {s}, {len(book)} distinct reason(s) --")
        for reason, st in sorted(book.items(), key=lambda kv: -kv[1]["mean"]):
            print(f"      {_n(st['mean']):>12} mean  [{_n(st['min'])} .. {_n(st['max'])}]  {reason}")

    odd = [r["seed"] for r in ok if r["unattributed"]]
    if odd:
        print(f"      !! supply/surrender events attributed to neither side on seeds {odd} "
              "-- see 'unattributed' in the JSON")

    print("\n=== DETERMINISM ===")
    if not verify["seeds_rerun"]:
        print("  --verify 0: this sweep carries NO determinism proof.")
    elif verify["identical"]:
        print(f"  PASS -- seeds {verify['seeds_rerun']} each ran twice and produced "
              "byte-identical records (signature, VP, and every structural metric).")
    else:
        print(f"  FAIL -- {verify['mismatches']}")

    per = sorted(walls)
    print(f"\n=== COST === {len(walls)} run(s) on {workers} worker(s): wall {wall:.1f}s "
          f"({wall/60:.1f} min); per-campaign median {statistics.median(per):.1f}s, "
          f"min {per[0]:.1f}s, max {per[-1]:.1f}s")
    print(f"  wrote {out_path}\n")


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(_ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--seeds", type=int, default=DEFAULT_SEEDS,
                    help=f"how many seeds to run: 1..N, unshopped (default {DEFAULT_SEEDS})")
    ap.add_argument("--seed", type=int, nargs="+", default=None,
                    help="an explicit seed panel, overriding --seeds")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help=f"process pool size (default {DEFAULT_WORKERS}; the box has 16 threads "
                         "and is shared). --workers 1 runs serial.")
    ap.add_argument("--verify", type=int, default=DEFAULT_VERIFY,
                    help=f"re-run the first K seeds and prove the records are identical "
                         f"(default {DEFAULT_VERIFY}; 0 disables the proof)")
    ap.add_argument("--arm", default="scripted", choices=sorted(ARMS),
                    help="which arm to fight -- it SELECTS THE POLICIES (see ARMS in the module "
                         "docstring); the run prints what the arm changes before it starts")
    ap.add_argument("--out", default=None,
                    help="output JSON (default scratchpad/gate_c/gate_c.<arm>.json)")
    args = ap.parse_args()

    # dict.fromkeys de-duplicates an explicit panel while keeping its order: a seed named twice is
    # one campaign, not two identical rows silently inflating n in the distribution.
    seeds = (list(dict.fromkeys(args.seed)) if args.seed
             else list(range(1, max(1, args.seeds) + 1)))
    arm = ARMS[args.arm]
    verify_seeds = seeds[:max(0, args.verify)]
    jobs = [(args.arm, s, 0) for s in seeds] + [(args.arm, s, 1) for s in verify_seeds]
    workers = max(1, min(args.workers, len(jobs)))
    out_path = Path(args.out) if args.out else _ROOT / "scratchpad" / "gate_c" / f"gate_c.{args.arm}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"GATE C -- arm '{args.arm}': {len(seeds)} seed(s) x GT1-111, {workers} worker(s), "
          f"{len(verify_seeds)} verify re-run(s).\n  One campaign is ~6 min (measured: ~365 CPU-s); "
          f"{len(jobs)} job(s) over {workers} worker(s) on 8 physical cores.\n"
          f"  ARM: {arm.what}\n"
          f"  seeds: {seeds}", flush=True)
    t0 = time.perf_counter()
    results = _sweep(jobs, workers)
    wall = time.perf_counter() - t0

    primary = [r for r in results if r["repeat"] == 0]
    records = [r["record"] for r in primary]
    agg = _aggregate(records)
    verify = _verify(results)
    payload = {
        "arm": args.arm,
        "arm_changes": arm.what,
        "generated_by": "scripts/gate_c.py",
        "scenario": "game.scenario.campaign(seed) -- GT1-111",
        # The classes ACTUALLY constructed by this arm's factories, so a mislabelled arm is caught
        # by reading the file it wrote (see THE ARM in the module docstring).
        "policies": {AX: type(arm.axis()).__name__, CW: type(arm.allied()).__name__},
        "seeds": [r for r in records if r["ok"]],
        "failures": [r for r in records if not r["ok"]],
        "aggregate": agg,
        "verify": verify,
        # The envelope: NOT part of the deterministic payload above, so two sweeps of the same
        # seeds diff clean on "seeds"/"aggregate" while still carrying their provenance and cost.
        "timing": {"wall_s": round(wall, 1), "workers": workers,
                   "per_run_s": {f"{r['seed']}:{r['repeat']}": round(r["wall_s"], 1)
                                 for r in results}},
        "git_head": _git_head(),
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")

    _report(records, agg, verify, args.arm, workers, wall, [r["wall_s"] for r in results], out_path)

    failed = [r for r in records if not r["ok"]]
    if failed:
        print(f"EXIT 1: {len(failed)} seed(s) raised.", file=sys.stderr)
        return 1
    if verify_seeds and not verify["identical"]:
        print("EXIT 2: the sweep did not reproduce itself -- determinism is broken.", file=sys.stderr)
        return 2
    if agg.get("breakdown_disagreements"):
        print("EXIT 3: CampaignVictory.breakdown disagrees with the engine's own verdict.",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
