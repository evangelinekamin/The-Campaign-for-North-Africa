#!/usr/bin/env python3
"""THE SIGNATURE-PARITY GATE -- the foundation every optimization block is measured against.

    python3 scripts/parity_harness.py --capture      # write scripts/parity_golden.json at HEAD
    python3 scripts/parity_harness.py --check        # re-run the panel; nonzero exit on ANY drift
    python3 scripts/parity_harness.py --check --workers 1   # serial (pristine per-run timing)

WHY THIS EXISTS. The one law of the optimization pass is: every engine change must produce a
BYTE-IDENTICAL event log. `determinism_signature(events)` is the canonical serialization of the whole
log; sha256(...)[:12] is its fingerprint. This harness pins that fingerprint for a PANEL of
(scenario, seed) runs, so any optimization can prove -- mechanically, in ~7 minutes -- that it moved
nothing. A moved fingerprint is a BUG IN THE CHANGE, never a reason to re-capture the golden.

THE PANEL is chosen to catch a determinism break FAST and to cover the campaign-only code where the
`dataclasses.replace(unit, hex=city)` cache-key landmine lives (victory / claims traces, rule 64.72):

  * rommel        x 15 seeds  -- fast (~4s), the widest net; scripted-vs-scripted, both ScriptedPolicy
  * siege         x  8 seeds  -- fast (~4s), the siege-artillery + ferry-interdiction paths
  * campaign24    x  3 seeds  -- max_turns=24 reaches the claims / city-control / victory code
  * campaign_full x  2 seeds  -- the whole GT1-111 war; reaches the GT35 64.72 supply-line trace

THE EXACT INVOCATIONS (matched to tests/baselines.py and scripts/measure_campaign.py):

  * rommel / siege: run(build(seed), ScriptedPolicy(AXIS), ScriptedPolicy(AXIS)) -- the canonical
    benchmark pin (tests/baselines.py, test_rommel_and_siege_stay_byte_identical). Seed 42 is in the
    panel for both, so its golden fingerprint must EQUAL the pinned ROMMELS_ARRIVAL / SIEGE_OF_TOBRUK
    (asserted after --capture; a disagreement means this harness is wrong, not the engine).
  * campaign*: run(campaign(seed, max_turns=...), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    -- byte-for-byte the scripted-vs-scripted invocation scripts/measure_campaign.py folds.

DETERMINISM. Each run is a pure function of (scenario, seed) -- the process pool only distributes
independent runs, it never touches a fingerprint. No network, no clock, no shared state.

TIMING. --check prints the per-scenario MEDIAN wall time so a block can measure its own speedup. The
heavy campaign runs get dedicated cores (only ~5 of them on a 16-core box), so their medians are
clean; the many short benchmark runs share the first scheduling wave, so read their medians as
approximate. For a pristine ruler use --workers 1 (serial, ~18 min).

FAILING HARDWARE (this box flips RAM bits). A SINGLE, non-reproducible drift is the RAM, not your
change: re-run --check once. A drift that reproduces is a real determinism break -- fix or revert.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from game.campaign_policy import (CampaignAxisPolicy,          # noqa: E402
                                  CampaignCommonwealthPolicy)
from game.engine import determinism_signature, run             # noqa: E402
from game.events import Side                                   # noqa: E402
from game.policy import ScriptedPolicy                         # noqa: E402
from game.scenario import (campaign, rommels_arrival,          # noqa: E402
                           siege_of_tobruk)

GOLDEN_PATH = _ROOT / "scripts" / "parity_golden.json"

# --- THE PANEL -------------------------------------------------------------------------------------
# Seed 42 leads rommel/siege so its fingerprint cross-checks against tests/baselines.py. The rest are
# a spread (the canonical measure_campaign seeds 1941/7/2026/99 + CAMPAIGN_SEED 4 + primes) so a
# break that only bites one dice branch still trips at least one panel entry.
_ROMMEL_SEEDS = (42, 1, 7, 99, 123, 1941, 2026, 5, 11, 13, 17, 23, 31, 55, 77)
_SIEGE_SEEDS = (42, 7, 99, 1941, 2026, 11, 23, 55)
_CAMPAIGN24_SEEDS = (4, 1941, 7)          # max_turns=24: into the claims/victory code
_CAMPAIGN_FULL_SEEDS = (1941, 4)          # full GT1-111: the GT35 64.72 cut-line trace

# Scenarios listed heaviest-first: submitting the long campaigns before the cheap benchmark runs lets
# them grab cores immediately and finish on dedicated cores (clean timing) while the short runs drain.
_SCENARIOS = ("campaign_full", "campaign24", "siege", "rommel")
_SEEDS = {"campaign_full": _CAMPAIGN_FULL_SEEDS, "campaign24": _CAMPAIGN24_SEEDS,
          "siege": _SIEGE_SEEDS, "rommel": _ROMMEL_SEEDS}


def _panel() -> list[tuple[str, int]]:
    """The full list of (scenario, seed) jobs, heaviest scenario first."""
    return [(sc, seed) for sc in _SCENARIOS for seed in _SEEDS[sc]]


def _key(scenario: str, seed: int) -> str:
    return f"{scenario}:{seed}"


def _run_job(job: tuple[str, int]) -> tuple[str, str, int, str, int, float]:
    """Run ONE (scenario, seed) and return (key, scenario, seed, sig, n_events, wall_seconds).

    Constructs the scenario and its policies here (inside the worker), so only the tiny (scenario,
    seed) tuple crosses the process boundary -- no GameState or Policy is ever pickled."""
    scenario, seed = job
    t0 = time.perf_counter()
    if scenario == "rommel":
        axis = ScriptedPolicy(Side.AXIS)
        res = run(rommels_arrival(seed=seed), axis, axis)
    elif scenario == "siege":
        axis = ScriptedPolicy(Side.AXIS)
        res = run(siege_of_tobruk(seed=seed), axis, axis)
    elif scenario == "campaign24":
        res = run(campaign(seed=seed, max_turns=24),
                  CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    elif scenario == "campaign_full":
        res = run(campaign(seed=seed),
                  CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    else:
        raise ValueError(f"unknown scenario {scenario!r}")
    sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
    return _key(scenario, seed), scenario, seed, sig, len(res.events), time.perf_counter() - t0


def _run_panel(workers: int) -> dict[str, tuple[str, str, int, str, int, float]]:
    """Run every panel job and return {key: record}. workers==1 runs serial (cleanest timing)."""
    jobs = _panel()
    records: dict[str, tuple] = {}
    if workers == 1:
        for job in jobs:
            rec = _run_job(job)
            records[rec[0]] = rec
            print(f"  {rec[0]:<20} {rec[3]}  {rec[4]:>7} ev  {rec[5]:7.2f}s", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_run_job, job) for job in jobs]   # submission order = heaviest first
            for fut in as_completed(futures):
                rec = fut.result()
                records[rec[0]] = rec
                print(f"  {rec[0]:<20} {rec[3]}  {rec[4]:>7} ev  {rec[5]:7.2f}s", flush=True)
    return records


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(_ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def _report_timing(records: dict, wall: float, workers: int) -> None:
    print(f"\n  PER-SCENARIO WALL TIME ({workers} worker(s); full-panel wall {wall:.1f}s)")
    print(f"    {'scenario':<15} {'runs':>4} {'median':>9} {'min':>9} {'max':>9}")
    for sc in _SCENARIOS:
        times = sorted(r[5] for r in records.values() if r[1] == sc)
        if not times:
            continue
        print(f"    {sc:<15} {len(times):>4} {statistics.median(times):>8.2f}s "
              f"{times[0]:>8.2f}s {times[-1]:>8.2f}s")


def _cross_check_baselines(sigs: dict[str, str]) -> None:
    """After --capture, prove seed 42 reproduces the project's own pinned benchmark fingerprints.
    tests/baselines.py is THE ONE PLACE those live; a disagreement means the harness is wrong."""
    try:
        sys.path.insert(0, str(_ROOT / "tests"))
        from baselines import ROMMELS_ARRIVAL, SIEGE_OF_TOBRUK   # noqa: E402
    except Exception as exc:                                     # pragma: no cover -- self-check only
        print(f"\n  (skipped baselines.py cross-check: {exc})")
        return
    print("\n  CROSS-CHECK vs tests/baselines.py (the pinned benchmark fingerprints):")
    ok = True
    for key, pinned in (("rommel:42", ROMMELS_ARRIVAL), ("siege:42", SIEGE_OF_TOBRUK)):
        got = sigs.get(key)
        match = got == pinned
        ok = ok and match
        print(f"    {key:<12} {got} {'==' if match else '!='} {pinned}  "
              f"{'OK' if match else 'MISMATCH'}")
    if not ok:
        raise SystemExit("FATAL: harness fingerprint disagrees with tests/baselines.py -- the harness "
                         "is computing the signature wrong; do NOT trust this golden file.")


def capture(workers: int) -> int:
    head = _git_head()
    print(f"CAPTURE at HEAD {head[:12] if head else '(unknown)'} -- {len(_panel())} runs, "
          f"{workers} worker(s)\n")
    t0 = time.perf_counter()
    records = _run_panel(workers)
    wall = time.perf_counter() - t0
    sigs = {k: r[3] for k, r in records.items()}
    golden = {
        "captured_at_head": head,
        "captured_at_head_short": head[:7] if head else None,
        "doc": ("sha256(determinism_signature(events))[:12] per (scenario:seed). "
                "rommel/siege = run(build(seed), ScriptedPolicy(AXIS), ScriptedPolicy(AXIS)); "
                "campaign24/campaign_full = run(campaign(seed, max_turns=24|None), "
                "CampaignAxisPolicy(), CampaignCommonwealthPolicy())."),
        "panel": dict(sorted(sigs.items())),
        "events": dict(sorted((k, r[4]) for k, r in records.items())),
    }
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")
    _report_timing(records, wall, workers)
    _cross_check_baselines(sigs)
    print(f"\n  wrote {GOLDEN_PATH.relative_to(_ROOT)} ({len(sigs)} fingerprints).")
    return 0


def check(workers: int) -> int:
    if not GOLDEN_PATH.exists():
        print(f"ERROR: no golden file at {GOLDEN_PATH} -- run --capture first.", file=sys.stderr)
        return 2
    golden = json.loads(GOLDEN_PATH.read_text())
    gsigs, gevents = golden["panel"], golden.get("events", {})
    print(f"CHECK vs golden captured at HEAD {golden.get('captured_at_head_short')} -- "
          f"{len(_panel())} runs, {workers} worker(s)\n")
    t0 = time.perf_counter()
    records = _run_panel(workers)
    wall = time.perf_counter() - t0
    cur = {k: r[3] for k, r in records.items()}
    cur_events = {k: r[4] for k, r in records.items()}

    drifts = [(k, gsigs[k], cur[k], gevents.get(k), cur_events[k])
              for k in sorted(cur) if k in gsigs and cur[k] != gsigs[k]]
    missing = sorted(set(gsigs) - set(cur))       # golden has it, this run didn't produce it
    extra = sorted(set(cur) - set(gsigs))          # this run produced it, golden lacks it

    _report_timing(records, wall, workers)

    if not drifts and not missing and not extra:
        print(f"\n  PASS -- all {len(cur)} fingerprints byte-identical to golden.")
        return 0

    print("\n  FAIL -- the event log is NOT byte-identical to golden:")
    for k, gsig, csig, gev, cev in drifts:
        ev = f"  events {gev} -> {cev}" if gev is not None else ""
        print(f"    DRIFT {k:<20} golden={gsig}  current={csig}{ev}")
    for k in missing:
        print(f"    MISSING {k:<20} in golden but not produced this run (panel changed?)")
    for k in extra:
        print(f"    EXTRA   {k:<20} produced this run but not in golden (panel changed?)")
    print("\n  A drift is a determinism break in the change under test -- fix or revert it; NEVER "
          "re-capture the golden to make it pass.\n  If this drift does NOT reproduce on a second "
          "--check, it is this box's RAM flipping a bit (not your change): re-run once.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", action="store_true",
                      help="run the panel and write scripts/parity_golden.json at the current HEAD")
    mode.add_argument("--check", action="store_true",
                      help="re-run the panel and assert every fingerprint matches golden (exit 1 on drift)")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4,
                    help="process pool size (default: all cores). --workers 1 runs serial with "
                         "pristine per-run timing (~18 min).")
    args = ap.parse_args()
    workers = max(1, args.workers)
    return capture(workers) if args.capture else check(workers)


if __name__ == "__main__":
    raise SystemExit(main())
