"""THE FAUCET AUDIT (measurement only -- changes no engine behaviour).

Traces the Axis (and, for contrast, the Commonwealth) supply chain stage by stage over a full
111-Game-Turn campaign and reports, for each stage, WHAT THE BOOK LICENSES against WHAT THE
ENGINE ACTUALLY DID:

  1. SHIPPED   -- [56.4]x[56.5] the allowable tonnage per Game-Turn, vs the tons the engine puts
                  on the water (Convoy.tons / CONVOY_PLANNED).
  2. LANDED    -- [55.3]/[55.14] the port's tonnage budget per quay-beat, vs PORT_UNLOADED tons;
                  how often the budget BINDS, and how much manifest expires unshipped (56.27).
  3. CONVERTED -- [54.5] Equivalent Weights: the points<->tons crossing, both directions.
  4. EVAPORATED-- 49.3 6%/Game-Turn + 5%/hot-OpStage on Fuel and Water, in dumps (SUPPLY_EVAPORATED)
                  and trucks (TRUCK_EVAPORATED); counted per Game-Turn so the cadence is visible.
  5. EATEN     -- 49.x/50.x/51.x/52.x. The army's TRUE burn is SUPPLY_CONSUMED (off a dump) PLUS
                  UNIT_SUPPLY_CONSUMED (off the 49.14 tank / 50.0 load); UNIT_REFILLED is a
                  dump->unit TRANSFER, not a burn, and double-counting it inflates the burn.
                  Shortfalls (STORES_SHORTFALL / WATER_SHORTFALL) measure the last mile FAILING.
  6. STOCK     -- where the surplus is standing at the end, rear vs front, so "it piles up at the
                  quay" is a number and not a story.

Usage:  python3 scratchpad/faucet_audit.py [seed ...]      (default 1941 7 2026)
Writes one JSON blob per seed to stdout, one line per seed, flushed as each lands.
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import calendar, logistics_data, supply                     # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,                # noqa: E402
                                  CampaignCommonwealthPolicy)
from game.engine import run                                          # noqa: E402
from game.events import EventKind, Side                              # noqa: E402
from game.scenario import campaign                                   # noqa: E402

COMMODITIES = ("AMMO", "FUEL", "STORES", "WATER")
_MON = ["jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec"]


def licensed_tonnage(seed: int, max_turns: int = 111) -> dict:
    """[56.21] read STRICTLY: 'the figures given on the Tonnage Determination Table are the
    tonnage of supplies that the Axis may ship in that GAME-TURN (for which he is planning)',
    and the worked example ships 21,000 t on Game-Turn 55 alone. So the licence is PER GAME-TURN.
    Rolls its own die stream (a measurement, not the engine's) purely to get the expected scale;
    also reports the die-independent min/max envelope, which is what the comparison rests on."""
    levels = logistics_data.convoy_level_56_4()
    caps = logistics_data.convoy_capacity_56_5()
    rng = random.Random(seed)
    total = lo = hi = 0
    per_turn = {}
    for gt in range(1, max_turns + 1):
        year, month = calendar.gt_to_month(gt)
        lvl = levels.get(str(year), {}).get(_MON[month - 1], "-")
        if lvl == "-":
            continue
        cap = caps[lvl]
        f, v = cap["fixed_tons"], cap["variable_tons_per_die"]
        rolled = math.ceil((f + v * rng.randint(1, 6)) / 1000) * 1000
        per_turn[gt] = rolled
        total += rolled
        lo += math.ceil((f + v * 1) / 1000) * 1000
        hi += math.ceil((f + v * 6) / 1000) * 1000
    return {"total_expected": total, "min": lo, "max": hi, "turns_with_convoy": len(per_turn)}


def _one(seed: int) -> dict:
    st0 = campaign(seed=seed)
    res = run(st0, CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    ev = res.events

    out: dict = {"seed": seed, "events": len(ev), "winner": res.winner.value if res.winner else None}

    # ---- 1. SHIPPED ------------------------------------------------------------------
    shipped_tons = defaultdict(int)              # side -> tons put on the water
    convoy_count = Counter()
    planned_points = defaultdict(Counter)        # side -> commodity -> points planned
    for c in st0.convoys:
        if c.tons:
            shipped_tons[c.side.value] += c.tons
            convoy_count[c.side.value] += 1
        elif c.cargo:                            # fixed-manifest lane (ferry / rail)
            convoy_count[c.side.value] += 1
            shipped_tons[c.side.value] += sum(
                q * supply.TONS_PER_POINT[k] for k, q in c.cargo.items())
    for e in ev:
        if e.kind is EventKind.CONVOY_PLANNED:
            for k, q in (e.payload.get("cargo") or {}).items():
                planned_points[e.side.value][k] += q
    out["shipped_tons"] = {k: round(v) for k, v in shipped_tons.items()}
    out["convoys"] = dict(convoy_count)
    out["planned_points"] = {s: dict(c) for s, c in planned_points.items()}
    out["licensed_per_game_turn"] = licensed_tonnage(seed, st0.max_turns)

    # ---- 2. LANDED -------------------------------------------------------------------
    landed_pts = defaultdict(Counter)            # side -> commodity -> points
    port_tons = defaultdict(float)               # port id -> tons landed all campaign
    port_beat = defaultdict(float)               # (port, turn, stage) -> tons
    turn = stage = 1
    for e in ev:
        if e.kind is EventKind.TURN_ADVANCED:
            turn = e.payload.get("turn", turn + 1)
            stage = 1
        elif e.kind is EventKind.STAGE_ADVANCED:
            stage = e.payload.get("stage", stage)
        elif e.kind is EventKind.PORT_UNLOADED:
            port_tons[e.payload["port_id"]] += e.payload["tons"]
            port_beat[(e.payload["port_id"], turn, stage)] += e.payload["tons"]
        elif e.kind is EventKind.SUPPLY_ARRIVED:
            for k, q in (e.payload.get("cargo") or {}).items():
                landed_pts[e.side.value][k] += q
    out["landed_points"] = {s: dict(c) for s, c in landed_pts.items()}
    out["landed_tons_by_port"] = {p: round(t) for p, t in sorted(port_tons.items())}
    out["landed_tons_total"] = {
        s: round(sum(q * supply.TONS_PER_POINT[k] for k, q in c.items()))
        for s, c in landed_pts.items()}

    # how hard does the quay bind?  compare each quay-beat against that port's charted budget
    budgets = {p.id: supply.port_tonnage_budget(p) for p in st0.ports}
    binding = Counter()
    beats = Counter()
    for (pid, _t, _s), tons in port_beat.items():
        beats[pid] += 1
        b = budgets.get(pid)
        if b and tons >= b - 1.0:
            binding[pid] += 1
    out["quay_beats"] = {p: [beats[p], binding[p], round(budgets.get(p, 0))]
                         for p in sorted(beats)}    # port -> [beats used, beats at cap, budget t]

    # ---- 4. EVAPORATED ---------------------------------------------------------------
    evap = Counter()
    evap_truck = Counter()
    turn = 1
    for e in ev:
        if e.kind is EventKind.TURN_ADVANCED:
            turn = e.payload.get("turn", turn + 1)
        elif e.kind is EventKind.SUPPLY_EVAPORATED:
            evap[e.payload["commodity"]] += e.payload["qty"]
        elif e.kind is EventKind.TRUCK_EVAPORATED:
            evap_truck[e.payload["commodity"]] += e.payload["qty"]
    out["evaporated_dump"] = dict(evap)
    out["evaporated_truck"] = dict(evap_truck)

    # cadence: how many times per Game-Turn does ONE named dump lose fuel to evaporation?
    probe = None
    per_turn_hits = Counter()
    turn = 1
    for e in ev:
        if e.kind is EventKind.TURN_ADVANCED:
            turn = e.payload.get("turn", turn + 1)
        elif e.kind is EventKind.SUPPLY_EVAPORATED and e.payload["commodity"] == "FUEL":
            if probe is None:
                probe = e.payload["supply_id"]
            if e.payload["supply_id"] == probe:
                per_turn_hits[turn] += 1
    out["evap_cadence_probe"] = {"dump": probe,
                                 "hits_per_turn_histogram": dict(Counter(per_turn_hits.values()))}

    # ---- 5. EATEN --------------------------------------------------------------------
    dump_draw = defaultdict(Counter)              # side -> commodity -> points off a dump
    unit_draw = defaultdict(Counter)              # side -> commodity -> points off a unit pool
    refill = defaultdict(Counter)                 # side -> commodity -> dump->unit transfer
    shortfalls = Counter()
    for e in ev:
        if e.kind is EventKind.SUPPLY_CONSUMED:
            dump_draw[e.side.value][e.payload["commodity"]] += e.payload["qty"]
        elif e.kind is EventKind.UNIT_SUPPLY_CONSUMED:
            unit_draw[e.side.value][e.payload["commodity"]] += e.payload["qty"]
        elif e.kind is EventKind.UNIT_REFILLED:
            refill[e.side.value][e.payload["commodity"]] += e.payload["qty"]
        elif e.kind is EventKind.STORES_SHORTFALL:
            shortfalls[("stores", e.side.value)] += 1
        elif e.kind is EventKind.WATER_SHORTFALL:
            shortfalls[("water", e.side.value)] += 1
    out["consumed_off_dump"] = {s: dict(c) for s, c in dump_draw.items()}
    out["consumed_off_unit"] = {s: dict(c) for s, c in unit_draw.items()}
    out["refilled_dump_to_unit"] = {s: dict(c) for s, c in refill.items()}
    out["shortfalls"] = {f"{a}_{b}": n for (a, b), n in shortfalls.items()}

    # the denominator for the shortfall rate: living units per side at the end, and the
    # number of stores beats (one per Game-Turn) / water beats (one per OpStage)
    out["living_final"] = {s.value: len(res.final.living(s)) for s in (Side.AXIS, Side.ALLIED)}
    out["living_initial"] = {s.value: len(st0.living(s)) for s in (Side.AXIS, Side.ALLIED)}

    # what actually MOVES -- fuel is only ever charged for movement (49.13)
    out["unit_moves"] = sum(1 for e in ev if e.kind is EventKind.UNIT_MOVED)
    out["cp_expended"] = sum(e.payload.get("cp", 0) for e in ev
                             if e.kind is EventKind.CP_EXPENDED)

    # ---- 5b. THE LAST MILE: what the lorries actually carry forward (53/54.2) ----------
    truck_load = defaultdict(Counter)
    truck_unload = defaultdict(Counter)
    for e in ev:
        if e.kind is EventKind.TRUCK_LOADED:
            for k, q in (e.payload.get("cargo") or {}).items():
                truck_load[e.side.value][k] += q
        elif e.kind is EventKind.TRUCK_UNLOADED:
            for k, q in (e.payload.get("cargo") or {}).items():
                truck_unload[e.side.value][k] += q
    out["truck_loaded"] = {s: dict(c) for s, c in truck_load.items()}
    out["truck_unloaded"] = {s: dict(c) for s, c in truck_unload.items()}

    # ---- 5c. TIME SERIES: landed / evaporated / burned per Game-Turn, Axis ------------
    series = defaultdict(lambda: Counter())
    turn = 1
    for e in ev:
        if e.kind is EventKind.TURN_ADVANCED:
            turn = e.payload.get("turn", turn + 1)
        elif e.kind is EventKind.SUPPLY_ARRIVED and e.side is Side.AXIS:
            series[turn]["landed"] += sum((e.payload.get("cargo") or {}).values())
        elif e.kind is EventKind.SUPPLY_EVAPORATED:
            series[turn]["evap"] += e.payload["qty"]
        elif e.kind in (EventKind.SUPPLY_CONSUMED, EventKind.UNIT_SUPPLY_CONSUMED) \
                and e.side is Side.AXIS:
            series[turn]["burn"] += e.payload["qty"]
    out["axis_series"] = {t: dict(c) for t, c in sorted(series.items())
                          if t % 10 == 1 or t in (2, 5, 111)}

    # ---- 6. STOCK ---------------------------------------------------------------------
    stock = defaultdict(Counter)
    biggest = []
    for su in res.final.supplies:
        for k in COMMODITIES:
            stock[su.side.value][k] += getattr(su, k.lower())
        biggest.append((sum(getattr(su, k.lower()) for k in COMMODITIES), su.id,
                        su.side.value, str(su.hex),
                        {k: getattr(su, k.lower()) for k in COMMODITIES}))
    biggest.sort(reverse=True)
    out["final_stock"] = {s: dict(c) for s, c in stock.items()}
    out["biggest_dumps"] = [b[1:] for b in biggest[:12]]
    truck_stock = defaultdict(Counter)
    for t in res.final.trucks:
        for k in COMMODITIES:
            truck_stock[t.side.value][k] += getattr(t, k.lower())
    out["final_truck_stock"] = {s: dict(c) for s, c in truck_stock.items()}
    return out


def main() -> None:
    """SEQUENTIAL BY DESIGN, and the reason is stated so nobody 'fixes' it: a 111-Game-Turn
    campaign holds ~280,000 Events plus the folded state, and four of them at once OOM'd a 16 GB
    box. One seed at a time, flushed as it lands, so a kill never costs the seeds already done."""
    seeds = [int(a) for a in sys.argv[1:]] or [1941, 7, 2026]
    for seed in seeds:
        print(json.dumps(_one(seed)), flush=True)


if __name__ == "__main__":
    main()
