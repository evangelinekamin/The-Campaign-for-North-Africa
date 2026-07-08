"""Crash-safe PARALLEL driver for the overnight 23-model CNA generalship leaderboard.

Runs each model as its OWN `python -m scripts.leaderboard` subprocess (composes, does NOT
rebuild the harness) with the per-tier seed count, a per-process cache/out file, and the
earned-crack floor-off pass for the top 4. Two lanes of parallelism run at once:

  * a POOL of model-processes (--parallel, default 5), and
  * concurrent seeds INSIDE each process (--workers, set to min(2*N, 8) by tier) -- so a slow
    reasoning model at N=5 finishes in ~ONE game of wall-clock, not the serial sum of ten.

OpenAI slugs (openai/*) run in a CONSTRAINED lane (--openai-parallel, default 2; W=2) to respect
OpenAI RPM/TPM. Total in-flight LLM calls stay ~30-40 so the whole run lands in ~1-1.5h.

RESUMABLE + CRASH-SAFE: a model whose out/card_<slug>.json already exists is SKIPPED (resume);
a model that errors or times out is logged and SKIPPED -- one bad model NEVER aborts the pool.
Every start/end/skip/fail is appended to out/leaderboard_run.log with a real wall-clock timestamp.

FINAL STEP merges all card files, prints the multi-axis ranked leaderboard (with the min/game +
tok/s columns), writes out/leaderboard_final.json, and runs a RANK-CORRELATION analysis (Spearman
rho + Kendall tau) between the CNA generalship ranking and the approximate generic-capability
ranking in data/generic_leaderboard.json, printing the biggest over/under-performers -- the direct
answer to "does wargame generalship differ from benchmark IQ".

    python3 -m scripts.run_leaderboard --live                       # the real overnight run
    python3 -m scripts.run_leaderboard --mock                       # zero-token end-to-end smoke
    python3 -m scripts.run_leaderboard --report-only                # just merge + rank + correlate

SECURITY: the key is billed by the child harness (leaderboard._load_key force-overwrites the
ambient key from as.txt); the driver asserts the hash ONCE up front (leaderboard._assert_key_billed)
and NEVER prints/logs/commits the key.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import BoundedSemaphore, Lock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import leaderboard as lb                                       # noqa: E402

REPO = lb.REPO
OUT = lb.OUT
GENERIC = REPO / "data" / "generic_leaderboard.json"
LOG_PATH = OUT / "leaderboard_run.log"
FINAL_PATH = OUT / "leaderboard_final.json"

# The roster. FRONTIER runs N=3 seeds; CHEAP_MID runs N=5. gpt-5.5-pro is intentionally EXCLUDED.
FRONTIER = (
    "google/gemini-3.5-flash", "anthropic/claude-sonnet-5",
    "google/gemini-3.1-pro-preview", "anthropic/claude-opus-4.8",
    "openai/gpt-5.5", "anthropic/claude-fable-5",
)
CHEAP_MID = (
    "z-ai/glm-5.2", "moonshotai/kimi-k2.7-code", "qwen/qwen3.7-max",
    "qwen/qwen3.6-27b", "qwen/qwen3.5-35b-a3b:nitro", "minimax/minimax-m3",
    "google/gemini-3.1-flash-lite", "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash",
    "xiaomi/mimo-v2.5-pro", "openai/gpt-5.4-mini", "qwen/qwen3-max-thinking",
    "moonshotai/kimi-k2.6", "z-ai/glm-5.1", "inception/mercury-2:nitro",
    "openai/gpt-oss-120b:nitro", "openai/gpt-oss-safeguard-20b:nitro",
)
ROSTER = FRONTIER + CHEAP_MID
# The top 4 also play the floor-OFF siege (earned-crack: did the staff crack Tobruk with NO help).
EARNED_CRACK = frozenset({
    "anthropic/claude-opus-4.8", "openai/gpt-5.5",
    "google/gemini-3.1-pro-preview", "anthropic/claude-sonnet-5",
})
FRONTIER_SEEDS = 3
CHEAP_MID_SEEDS = 5
OPENAI_WORKERS = 2          # constrained lane: keep per-model in-flight low for OpenAI RPM/TPM
MAX_WORKERS = 8             # non-OpenAI worker cap (a fast model still won't flood the endpoint)


# --- pure helpers (unit-tested) ------------------------------------------------

def safe_slug(model: str) -> str:
    """Filesystem-safe slug for a model's cache/card files ('/' and ':' -> '_')."""
    return model.replace("/", "_").replace(":", "_")


def is_openai(model: str) -> bool:
    """OpenAI slugs run in the constrained RPM/TPM lane (this includes the gpt-oss:* models)."""
    return model.startswith("openai/")


def seeds_for(model: str) -> int:
    """Per-tier seed count: FRONTIER N=3, everything else N=5."""
    return FRONTIER_SEEDS if model in FRONTIER else CHEAP_MID_SEEDS


def workers_for(model: str) -> int:
    """Concurrent seeds inside the model's process. OpenAI is throttled to OPENAI_WORKERS; every
    other model runs min(2*N, MAX_WORKERS) so its N-seeds x 2-scenarios collapse to ~one game of
    wall-clock instead of a serial long-pole."""
    if is_openai(model):
        return OPENAI_WORKERS
    return min(2 * seeds_for(model), MAX_WORKERS)


def wants_earned_crack(model: str) -> bool:
    return model in EARNED_CRACK


def card_path(out_dir: Path, model: str) -> Path:
    return Path(out_dir) / f"card_{safe_slug(model)}.json"


def cache_path(out_dir: Path, model: str) -> Path:
    return Path(out_dir) / f"lb_cache_{safe_slug(model)}.json"


def pending_models(models, out_dir: Path) -> list:
    """Resume-skip: drop any model whose card file already exists (a finished run)."""
    return [m for m in models if not card_path(out_dir, m).exists()]


def build_command(model: str, out_dir: Path, *, mock: bool) -> list:
    """The per-model subprocess: one leaderboard run with the tiered seeds/workers, its OWN cache
    and card file, and --earned-crack for the top 4."""
    cmd = [sys.executable, "-m", "scripts.leaderboard",
           "--mock" if mock else "--live",
           "--models", model,
           "--seeds", str(seeds_for(model)),
           "--workers", str(workers_for(model)),
           "--cache", str(cache_path(out_dir, model)),
           "--out", str(card_path(out_dir, model))]
    if wants_earned_crack(model):
        cmd.append("--earned-crack")
    return cmd


def merge_cards(out_dir: Path) -> list:
    """Union every per-process card_*.json in out_dir into one card list (latest write wins per
    model). The final card file itself is never globbed back in."""
    out_dir = Path(out_dir)
    by_model: dict = {}
    for p in sorted(out_dir.glob("card_*.json")):
        try:
            for c in json.loads(p.read_text()).get("cards", []):
                by_model[c["model"]] = c
        except (ValueError, OSError):
            continue
    return list(by_model.values())


def cna_ranking(cards) -> list:
    """The CNA generalship order (best first) via the harness's multi-axis _rank_key."""
    return [c["model"] for c in sorted(cards, key=lb._rank_key, reverse=True)]


def load_generic_ranking(path=GENERIC) -> list:
    return json.loads(Path(path).read_text())["ranking"]


def _common_ranks(order_a, order_b):
    """0-based ranks of the models common to both orderings, re-ranked within each ordering."""
    setb, seta = set(order_b), set(order_a)
    common = [m for m in order_a if m in setb]
    ra = {m: i for i, m in enumerate(common)}
    rb = {m: i for i, m in enumerate([m for m in order_b if m in seta])}
    return common, ra, rb


def spearman(order_a, order_b) -> float:
    """Spearman rho over the models common to both orderings (distinct ranks, no ties)."""
    common, ra, rb = _common_ranks(order_a, order_b)
    n = len(common)
    if n < 2:
        return 0.0
    d2 = sum((ra[m] - rb[m]) ** 2 for m in common)
    return round(1 - 6 * d2 / (n * (n * n - 1)), 4)


def kendall_tau(order_a, order_b) -> float:
    """Kendall tau-a over the models common to both orderings."""
    common, ra, rb = _common_ranks(order_a, order_b)
    n = len(common)
    if n < 2:
        return 0.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            mi, mj = common[i], common[j]
            s = (ra[mi] - ra[mj]) * (rb[mi] - rb[mj])
            concordant += s > 0
            discordant += s < 0
    return round((concordant - discordant) / (n * (n - 1) / 2), 4)


def divergence_report(cna_order, generic_order, *, top: int = 5) -> dict:
    """Models whose CNA rank most diverges from their generic rank. divergence = generic_rank -
    cna_rank: positive = OVER-performs at the wargame relative to benchmark IQ, negative = UNDER."""
    common, ra, rb = _common_ranks(cna_order, generic_order)
    rows = [{"model": m, "cna_rank": ra[m] + 1, "generic_rank": rb[m] + 1,
             "divergence": rb[m] - ra[m]} for m in common]
    return {
        "overperformers": sorted(rows, key=lambda r: r["divergence"], reverse=True)[:top],
        "underperformers": sorted(rows, key=lambda r: r["divergence"])[:top],
    }


# --- execution (subprocess pool) ----------------------------------------------

def _log(log_path: Path, msg: str) -> None:
    """Append a real-wall-clock-stamped line to the run log (real time is fine in the driver)."""
    line = f"{datetime.now().isoformat(timespec='seconds')}  {msg}\n"
    with open(log_path, "a") as fh:
        fh.write(line)
    print(line, end="", flush=True)


def run_one(model: str, out_dir: Path, *, mock: bool, timeout: float, log_path: Path,
            build_cmd=build_command, fault=()) -> dict:
    """Run ONE model's leaderboard subprocess. Never raises: an error/timeout/non-zero exit is
    caught, logged with the child's stderr tail, and returned as a failed status so the pool lives."""
    cmd = list(fault[model]) if model in fault else build_cmd(model, out_dir, mock=mock)
    _log(log_path, f"START  {model}  seeds={seeds_for(model)} workers={workers_for(model)} "
                   f"earned_crack={wants_earned_crack(model)}")
    try:
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout)
        status = "ok" if proc.returncode == 0 else f"exit_{proc.returncode}"
        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
            _log(log_path, f"FAIL   {model} {status}\n{tail}")
    except subprocess.TimeoutExpired:
        status = "timeout"
        _log(log_path, f"FAIL   {model} timeout after {timeout}s")
    except Exception as exc:                                       # never abort the pool
        status = "error"
        _log(log_path, f"FAIL   {model} error {exc!r}")
    if status == "ok":
        _log(log_path, f"END    {model} ok")
    return {"model": model, "status": status}


def run_pool(models, out_dir: Path, *, parallel: int, openai_parallel: int, mock: bool,
             timeout: float, log_path: Path, build_cmd=build_command, fault=()) -> list:
    """Two-lane subprocess pool: general models fill `parallel` slots, OpenAI models a separate
    `openai_parallel` lane. Resume-skips finished models. One failure never stops the others."""
    out_dir = Path(out_dir)
    todo = pending_models(models, out_dir)
    for m in models:
        if m not in todo:
            _log(log_path, f"SKIP   {m} (card exists -- resume)")
    sem_general = BoundedSemaphore(max(1, parallel))
    sem_openai = BoundedSemaphore(max(1, openai_parallel))
    results, lock = [], Lock()

    def work(model: str) -> None:
        sem = sem_openai if is_openai(model) else sem_general
        with sem:
            res = run_one(model, out_dir, mock=mock, timeout=timeout, log_path=log_path,
                          build_cmd=build_cmd, fault=fault)
        with lock:
            results.append(res)

    if todo:
        with ThreadPoolExecutor(max_workers=parallel + openai_parallel) as ex:
            list(ex.map(work, todo))
    return results


# --- final merge + rank + correlation -----------------------------------------

def final_report(out_dir: Path, generic_path=GENERIC, *, top: int = 5) -> dict:
    """Merge all cards, print the multi-axis leaderboard, write leaderboard_final.json, and run the
    Spearman/Kendall correlation vs the generic-capability ranking with the top over/under-performers."""
    cards = merge_cards(out_dir)
    if not cards:
        print("no cards to merge -- nothing ran")
        return {}
    lb.leaderboard(cards)
    cna_order = cna_ranking(cards)
    generic_order = load_generic_ranking(generic_path)
    rho, tau = spearman(cna_order, generic_order), kendall_tau(cna_order, generic_order)
    div = divergence_report(cna_order, generic_order, top=top)
    correlation = {"n": len(_common_ranks(cna_order, generic_order)[0]),
                   "spearman_rho": rho, "kendall_tau": tau, **div}
    final = {"engine_sha": lb.ENGINE_SHA, "cards": cards, "cna_ranking": cna_order,
             "generic_ranking": generic_order, "correlation": correlation}
    Path(FINAL_PATH).write_text(json.dumps(final, indent=2))
    _print_correlation(correlation)
    print(f"\nwrote {FINAL_PATH}")
    return final


def _print_correlation(correlation: dict) -> None:
    print("\n=== CNA generalship vs generic capability (does wargame IQ differ from benchmark IQ) ===")
    print(f"  models compared: {correlation['n']}   "
          f"Spearman rho: {correlation['spearman_rho']}   Kendall tau: {correlation['kendall_tau']}")
    print("  OVER-performers (rank higher at the wargame than on generic benchmarks):")
    for r in correlation["overperformers"]:
        print(f"    {r['model']:<34} CNA #{r['cna_rank']:<3} generic #{r['generic_rank']:<3} "
              f"(+{r['divergence']})")
    print("  UNDER-performers (rank lower at the wargame than on generic benchmarks):")
    for r in correlation["underperformers"]:
        print(f"    {r['model']:<34} CNA #{r['cna_rank']:<3} generic #{r['generic_rank']:<3} "
              f"({r['divergence']})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="zero-token end-to-end smoke (MockClient)")
    ap.add_argument("--live", action="store_true", help="the real billed run (asserts the key)")
    ap.add_argument("--report-only", action="store_true", help="skip running; just merge+rank+correlate")
    ap.add_argument("--parallel", type=int, default=5, help="general model-process lane width")
    ap.add_argument("--openai-parallel", type=int, default=2, help="OpenAI (openai/*) lane width")
    ap.add_argument("--timeout", type=float, default=2700.0, help="per-model wall-clock timeout (s)")
    ap.add_argument("--top", type=int, default=5, help="over/under-performers to print")
    ap.add_argument("--out-dir", default=str(OUT))
    ap.add_argument("--generic", default=str(GENERIC))
    ap.add_argument("--fault-inject", default="",
                    help="comma-list of slugs to force-FAIL (chaos test of pool crash-safety)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)
    if not args.report_only and not (args.mock or args.live):
        ap.error("pass --mock, --live, or --report-only")

    if args.live:
        lb._load_key()
        lb._assert_key_billed()                                   # bill the CFNA key, ONCE, up front

    if not args.report_only:
        fault = {s.strip(): [sys.executable, "-c", "import sys; sys.exit(7)"]
                 for s in args.fault_inject.split(",") if s.strip()}
        _log(LOG_PATH, f"RUN START mock={args.mock} models={len(ROSTER)} parallel={args.parallel} "
                       f"openai_parallel={args.openai_parallel} engine_sha={lb.ENGINE_SHA}")
        results = run_pool(ROSTER, out_dir, parallel=args.parallel,
                           openai_parallel=args.openai_parallel, mock=args.mock,
                           timeout=args.timeout, log_path=LOG_PATH, fault=fault)
        ok = sum(1 for r in results if r["status"] == "ok")
        _log(LOG_PATH, f"RUN END ran={len(results)} ok={ok} failed={len(results) - ok}")

    final_report(out_dir, args.generic, top=args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
