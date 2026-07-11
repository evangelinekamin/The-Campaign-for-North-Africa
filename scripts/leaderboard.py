"""Model LEADERBOARD harness (composes scripts.benchmark + scripts.measure_siege).

For a given OpenRouter model slug, run the live 7-seat Axis StaffPolicy over N seeds on
BOTH scenarios and emit a per-model SCORECARD:

  * DEGREE-OF-SUCCESS on rommels_arrival -- how well the model runs the campaign. Reuses
    benchmark.game_metrics + benchmark._aggregate (advance%, reach/turn_invested, the
    generalship score, kill ratio, order-discipline reject rate) over N seeds.
  * CRACK-GENERALSHIP on siege_of_tobruk(port_bomb=True, raf=True, storm floor ON) -- the
    crack rate (winner==AXIS) PLUS the telemetry that separates a GOOD general from a TIMID
    one: the MIN AL-Tobruk garrison ammo reached (a good general drives it toward 0; the
    dev seat mercury-2 leaves it ~2200 RISING), the fraction of seeds where the garrison
    genuinely STARVED (its ammo was driven below STARVE_FLOOR -- the model sustained the
    storm), and the 15.15/15.88/17.25 surrender path. Reuses measure_siege._telemetry.
  * COST -- calls, prompt/completion tokens, and the dollar cost (benchmark.PRICES; a slug
    absent from PRICES has its price fetched from OpenRouter /models). Cost is reported in
    tokens + dollars, NEVER alongside the key.

    python3 -m scripts.leaderboard --mock                              # free dry-run (MockClient)
    python3 -m scripts.leaderboard --live --seeds 8 \
        --models inception/mercury-2,anthropic/claude-haiku-4.5
    python3 -m scripts.leaderboard --recache --seeds 8                 # zero-token replay

Plumbing is REUSED, not rebuilt: the env-only key launcher (measure_siege._load_key, which
FORCE-OVERWRITES any ambient OPENROUTER_API_KEY so this run bills the CFNA key), the
per-seat OpenRouterClient wrapped in the shared sha256(model+prompt) sidecar cache (so a
re-run is zero-token), the FAST_PROVIDER throughput routing, and the siege schedule +
telemetry. Before the first live call the loaded key is asserted (by hash, never printed)
to equal the as.txt contents.

SECURITY: the key is env-only, read straight into os.environ, NEVER printed/logged/committed.
The cache keys on sha256(model+prompt) -- never the key -- and cost is tokens + dollars only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import (FAST_PROVIDER, PRICES, _aggregate,          # noqa: E402
                               _mock_staff, game_metrics)
from scripts.measure_siege import (BASE_SEED, FERRY_BOMB, KEY_FILE,         # noqa: E402
                                   PORTBOMB_CADENCE, PORTBOMB_START,
                                   RAF_FIGHTERS, _load_key, _telemetry)

from game.apply import fold                                                 # noqa: E402
from game.engine import run                                                 # noqa: E402
from game.events import Side                                                # noqa: E402
from game.llm import (CachingClient, Journal, MockClient,                   # noqa: E402
                      OpenRouterClient, _atomic_write, compact, load_cache)
from game.policy import ScriptedPolicy                                      # noqa: E402
from game.scenario import rommels_arrival, siege_of_tobruk                  # noqa: E402
from game.staff_policy import LLM_SEATS, StaffPolicy                        # noqa: E402

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "out"
CACHE_PATH = OUT / "leaderboard.cache.json"


def _engine_sha() -> str:
    """The current engine git SHA (git rev-parse --short HEAD), read ONCE at import and stamped
    into every scorecard so runs are comparable across engine versions. 'unknown' off a repo."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:                                     # not a repo / git absent
        return "unknown"


ENGINE_SHA = _engine_sha()

# The garrison opens the siege on ~1500-2351 Ammo Points (the built-in 61.36 dump + the
# adjacent AL-Dump#3). A TIMID general lets the ferry outpace the storm and the dump plateaus
# high (mercury-2 leaves it ~2200, RISING); a GOOD general sustains the storm and drives the
# curve toward the 15.15 dry-stack fire at 0. A seed counts as STARVED when the garrison's ammo
# was driven below this floor -- cleanly below both the ~1500 opening and the timid plateau.
STARVE_FLOOR = 500

# A card is ERRORED -- its score is the SCRIPTED-FALLBACK general's, not the model's -- when the
# model's API calls mostly failed: the StaffPolicy falls back to ScriptedPolicy on an empty
# completion, so a model whose calls errored (or barely landed) scores the scripted seat's play.
# A real 2-scenario game makes ~100-230 successful LLM calls; a handful means nearly every staff
# decision ran on the fallback. Two independent tripwires: the API failure rate exceeded
# MAX_FAILURE_RATE, OR successful calls-per-game fell below MIN_CALLS_PER_GAME (some failures never
# reach the counter -- a killed/timed-out process just leaves too few calls, so the call floor
# catches what the failure rate misses).
MAX_FAILURE_RATE = 0.35
MIN_CALLS_PER_GAME = 40

# OpenRouter's public model catalogue (pricing per-token, in USD). Fetched only for a slug
# absent from benchmark.PRICES; converted to PRICES' per-1M-token scale.
_MODELS_URL = "https://openrouter.ai/api/v1/models"


class _Disconnected:
    """Refuses to call the model -- used by --recache so a cache miss is a hard, visible
    failure. `model` matches the live client so the sha256 cache keys line up."""

    def __init__(self, model: str):
        self.model = model

    def complete(self, prompt: str) -> str:
        raise RuntimeError("model disconnected: cache miss during re-simulation")

    def usage(self) -> dict:
        return {}


def _assert_key_billed() -> None:
    """Before the first live call, ASSERT the loaded OPENROUTER_API_KEY equals the as.txt
    contents (compare sha256, never print the key) so this run bills the CFNA key, not the
    ambient one a shell profile exported for another project."""
    env = os.environ.get("OPENROUTER_API_KEY", "")
    disk = Path(KEY_FILE).read_text().strip()
    if hashlib.sha256(env.encode()).hexdigest() != hashlib.sha256(disk.encode()).hexdigest():
        raise SystemExit("loaded OPENROUTER_API_KEY does not match as.txt -- refusing to bill "
                         "the wrong account")
    print("key assertion: loaded OPENROUTER_API_KEY matches as.txt (billing the CFNA key) -- PASSED")


def _seat_clients(model: str, cache: dict, *, live: bool, journal: "Journal | None") -> dict:
    """One client per LLM seat, each wrapped in the SHARED sidecar cache + the SHARED durability
    journal. Distinct inner clients so parallel seats never race on usage; live=False plugs a
    disconnected inner so a fully-cached re-run needs no network and no key."""
    def inner():
        return (OpenRouterClient(model, temperature=0.0, timeout=45, retries=1,
                                 provider=FAST_PROVIDER) if live else _Disconnected(model))
    return {seat: CachingClient(inner(), cache, journal=journal) for seat in LLM_SEATS}


def _staff(model: str, cache: dict, *, mock: bool, live: bool, floor: bool,
           journal: "Journal | None" = None) -> StaffPolicy:
    """The Axis command staff for one game. In mock mode every seat falls back to the shared
    zero-token MockClient(_mock_staff); otherwise each LLM seat gets its own cached live/
    disconnected client sharing the durability journal. `floor` arms the storming floor (siege)."""
    seats = None if mock else _seat_clients(model, cache, live=live, journal=journal)
    return StaffPolicy(MockClient(_mock_staff), side=Side.AXIS, seat_clients=seats,
                       max_workers=1 if mock else len(LLM_SEATS), storm_floor=floor)


def _play_rommel(model: str, seed: int, cache: dict, *, mock: bool, live: bool,
                 journal: "Journal | None" = None) -> tuple[dict, dict]:
    axis = _staff(model, cache, mock=mock, live=live, floor=False, journal=journal)
    result = run(rommels_arrival(seed=seed), axis=axis,
                 allied=ScriptedPolicy(attacker=Side.AXIS))
    assert fold(result.initial, result.events) == result.final, f"rommel replay FAILED seed={seed}"
    return game_metrics(result), axis.usage()


def _play_siege(model: str, seed: int, cache: dict, *, mock: bool, live: bool,
                floor: bool, journal: "Journal | None" = None) -> tuple[dict, dict]:
    axis = _staff(model, cache, mock=mock, live=live, floor=floor, journal=journal)
    result = run(siege_of_tobruk(seed, port_bomb=True, raf=True, ferry_bomb=FERRY_BOMB,
                                 portbomb_start=PORTBOMB_START, portbomb_cadence=PORTBOMB_CADENCE,
                                 raf_fighters=RAF_FIGHTERS),
                 axis=axis, allied=ScriptedPolicy(attacker=Side.AXIS))
    assert fold(result.initial, result.events) == result.final, f"siege replay FAILED seed={seed}"
    return _telemetry(result), axis.usage()


def _starved(tel: dict) -> bool:
    """True when the garrison genuinely STARVED: the sustained storm drove its ammo curve
    below STARVE_FLOOR (toward the 15.15 dry-stack fire at 0), not merely dented a high plateau."""
    m = tel.get("al_tobruk_ammo_min")
    return m is not None and m <= STARVE_FLOOR


def _siege_seed_row(tel: dict) -> dict:
    """The slim per-seed crack-generalship telemetry (drops the full per-stage trajectory)."""
    return {
        "crack": tel["crack"],
        "winner": tel["winner"],
        "port_eff_zero_turn": tel["port_eff_zero_turn"],
        "axis_assaults": tel["axis_assaults"],
        "al_tobruk_ammo_final": tel["al_tobruk_ammo"],
        "al_tobruk_ammo_peak": tel["al_tobruk_ammo_peak"],
        "al_tobruk_ammo_min": tel["al_tobruk_ammo_min"],
        "starved": _starved(tel),
        "surrender_path": tel["surrender_path"],
    }


def _siege_summary(tels: list[dict]) -> dict:
    """Crack-generalship over N seeds: the crack rate + the drove-them-to-starvation signal."""
    n = len(tels)
    cracks = sum(1 for t in tels if t["crack"])
    starved = sum(1 for t in tels if _starved(t))
    ammo_mins = [t["al_tobruk_ammo_min"] for t in tels if t["al_tobruk_ammo_min"] is not None]
    paths = [t["surrender_path"] for t in tels if t["surrender_path"]]
    path_counts: dict = {}
    for p in paths:
        path_counts[p] = path_counts.get(p, 0) + 1
    return {
        "seeds": n,
        "cracks": cracks,
        "crack_rate_pct": round(100 * cracks / n, 1),
        "starved_seeds": starved,
        "starved_fraction": round(starved / n, 3),
        "ammo_min_reached": min(ammo_mins) if ammo_mins else None,   # deepest drive toward 0
        "mean_ammo_min": round(mean(ammo_mins), 1) if ammo_mins else None,
        "surrender_paths": path_counts,
        "seed_detail": [_siege_seed_row(t) for t in tels],
    }


def _fetch_openrouter_price(model: str) -> tuple[float, float]:
    """Fetch (prompt, completion) price for a slug absent from PRICES, in per-1M-token USD to
    match PRICES' scale. OpenRouter's /models catalogue is public (no key). (0, 0) on any miss."""
    try:
        with urllib.request.urlopen(_MODELS_URL, timeout=20) as resp:
            catalogue = json.loads(resp.read().decode())
    except Exception:                                     # network/parse failure -> unknown price
        return (0.0, 0.0)
    for entry in catalogue.get("data", []):
        if entry.get("id") == model:
            pr = entry.get("pricing", {})
            return (float(pr.get("prompt", 0.0)) * 1e6, float(pr.get("completion", 0.0)) * 1e6)
    return (0.0, 0.0)


def _base_slug(model: str) -> str:
    """The pricing slug WITHOUT an OpenRouter routing variant (':nitro', ':floor', ...). The
    variant selects an endpoint, not a different-priced model, but it is NOT in PRICES or the
    /models catalogue -- so 'openai/gpt-oss-120b:nitro' priced $0.000 until we stripped it."""
    return model.split(":", 1)[0]


def _price_for(model: str, fetch=_fetch_openrouter_price) -> tuple[tuple[float, float], str]:
    """(prompt, completion) per-1M-token price + its source. PRICES first (curated, offline),
    trying the full slug then the variant-stripped base; otherwise the OpenRouter catalogue keyed
    by the base slug (so a ':nitro' variant still resolves)."""
    base = _base_slug(model)
    for slug in (model, base):
        if slug in PRICES:
            return PRICES[slug], "PRICES"
    return fetch(base), "openrouter"


def _cost_block(model: str, usage: dict, games: int) -> dict:
    ptok, ctok = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    if ptok == 0 and ctok == 0:                           # nothing to price -> stay offline
        base = _base_slug(model)
        priced = model in PRICES or base in PRICES
        (p_in, p_out) = PRICES.get(model, PRICES.get(base, (0.0, 0.0)))
        source = "PRICES" if priced else "unpriced"
    else:
        (p_in, p_out), source = _price_for(model)
    cost = (ptok * p_in + ctok * p_out) / 1e6
    return {
        "price_source": source,
        "price_per_1m": [p_in, p_out],
        "calls": usage.get("calls", 0),
        "failures": usage.get("failures", 0),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "cache_hits": usage.get("cache_hits", 0),
        "cache_misses": usage.get("cache_misses", 0),
        "est_cost_usd": round(cost, 4),
        "cost_per_game_usd": round(cost / max(1, games), 4),
    }


def _sum_usage(usages: list[dict]) -> dict:
    keys = ("calls", "failures", "prompt_tokens", "completion_tokens", "cache_hits", "cache_misses")
    return {k: sum(u.get(k, 0) for u in usages) for k in keys}


def _campaign_block(model: str, per_game: list[dict]) -> dict:
    """The rommels_arrival degree-of-success block. Reuses benchmark._aggregate for the score
    + advance% + reach + kill ratio + order-discipline, then strips its cost keys so the single
    source of truth for cost is the scorecard's own (both-scenario) cost block."""
    block = _aggregate(model, per_game, {}, mode="staff")
    for k in ("est_cost_usd", "cost_per_game_usd", "llm_calls", "llm_failures",
              "prompt_tokens", "completion_tokens"):
        block.pop(k, None)
    # Each seed's own campaign score, so a real confidence interval is computable from the card
    # (not just the min/max the aggregate exposes).
    block["per_seed_scores"] = [g["score"] for g in per_game]
    return block


def _timed(call):
    """Run `call` on a MONOTONIC clock; return (result, elapsed_seconds)."""
    t0 = time.monotonic()
    out = call()
    return out, time.monotonic() - t0


def _timing_block(secs: float, games: int, completion_tokens: int) -> dict:
    """Wall-clock throughput over the games played -- the speed signal the dev-model pick is
    unreadable without: mean minutes/game and mean completion tok/s (completion tokens over the
    total generation seconds). Zero elapsed / zero games never divides by zero."""
    return {
        "wall_seconds": round(secs, 1),
        "mean_minutes_per_game": round(secs / max(1, games) / 60, 2),
        "completion_tok_per_s": round(completion_tokens / secs, 1) if secs > 0 else 0.0,
    }


def run_model(model: str, seeds: int, *, mock: bool, live: bool, floor: bool,
              cache: dict, base_seed: int = BASE_SEED, workers: int = 5,
              earned_crack: bool = False, journal: "Journal | None" = None) -> dict:
    """N seeds of the live 7-seat Axis StaffPolicy on BOTH scenarios -> one SCORECARD dict.
    The two scenarios run CONCURRENTLY over their own seats sharing the sidecar cache; the
    engine is pure per-game, so concurrency is an I/O win only and never perturbs the fold.
    `earned_crack` ALSO plays each seed's siege with the storm floor OFF -- the real-generalship
    signal (did the staff crack Tobruk with NO scripted assault help). Each game is wall-clocked."""
    par = 1 if mock else workers

    def one(i: int) -> tuple:
        seed = base_seed + i
        (rg, ru), rt = _timed(
            lambda: _play_rommel(model, seed, cache, mock=mock, live=live, journal=journal))
        (st, su), st_t = _timed(
            lambda: _play_siege(model, seed, cache, mock=mock, live=live, floor=floor,
                                journal=journal))
        secs = rt + st_t
        ec_tel, ec_u = None, {}
        if earned_crack:
            (ec_tel, ec_u), et = _timed(
                lambda: _play_siege(model, seed, cache, mock=mock, live=live, floor=False,
                                    journal=journal))
            secs += et
        mark = "CRACK" if st["crack"] else "held"
        print(f"    {model}  seed {seed}: rommel score {rg['score']} adv {rg['advance_pct']}% | "
              f"siege {mark} AL-ammo peak {st['al_tobruk_ammo_peak']}->min {st['al_tobruk_ammo_min']} "
              f"surr={st['surrender_path']}", flush=True)
        return rg, ru, st, su, ec_tel, ec_u, secs

    with ThreadPoolExecutor(max_workers=par) as ex:
        outs = list(ex.map(one, range(seeds)))

    per_game = [o[0] for o in outs]
    tels = [o[2] for o in outs]
    ec_tels = [o[4] for o in outs if o[4] is not None]
    usage = _sum_usage([o[1] for o in outs] + [o[3] for o in outs] + [o[5] for o in outs])
    total_secs = sum(o[6] for o in outs)
    games = 2 * seeds + (seeds if earned_crack else 0)
    card = {
        "model": model,
        "seeds": seeds,
        "floor": floor,
        "engine_sha": ENGINE_SHA,                            # cross-version comparability
        "campaign": _campaign_block(model, per_game),        # rommels_arrival degree-of-success
        "siege": _siege_summary(tels),                       # crack-generalship (floor as configured)
        "earned_crack": _siege_summary(ec_tels) if earned_crack else None,  # floor-OFF, no help
        "cost": _cost_block(model, usage, games=games),      # both scenarios (+ earned-crack pass)
        "timing": _timing_block(total_secs, games, usage["completion_tokens"]),
    }
    return {**card, **_validity(card)}                       # flag a scripted-fallback (errored) run


def _calls_per_game(card: dict) -> float:
    """Successful LLM calls per game (2 scenarios/seed) -- 0 when the seed count is unknown."""
    seeds = card.get("seeds", 0)
    return card.get("cost", {}).get("calls", 0) / (2 * seeds) if seeds else 0.0


def _validity(card: dict) -> dict:
    """(errored, failure_rate) computed from a card's OWN cost block + seed count -- pure, so it
    flags EXISTING cards at merge/display time without re-running. Errored when the API failure rate
    exceeds MAX_FAILURE_RATE OR successful calls-per-game fall below MIN_CALLS_PER_GAME. A card with
    no usage to judge (no attempts, no seeds) is never errored -- we do not exclude blind."""
    cost = card.get("cost", {})
    calls, failures = cost.get("calls", 0), cost.get("failures", 0)
    attempts = calls + failures
    failure_rate = failures / attempts if attempts else 0.0
    starved_calls = card.get("seeds", 0) > 0 and _calls_per_game(card) < MIN_CALLS_PER_GAME
    errored = failure_rate > MAX_FAILURE_RATE or starved_calls
    return {"errored": errored, "failure_rate": round(failure_rate, 4)}


def _games_played(card: dict) -> int:
    """Games behind a card's cost block: 2 scenarios/seed, +1 more/seed for the earned-crack pass."""
    seeds = card.get("seeds", 0)
    return 2 * seeds + (seeds if card.get("earned_crack") else 0)


def _reprice(card: dict) -> dict:
    """Correct a card whose dollar cost is $0.000 despite real tokens (the ':nitro' base slug whose
    live /models fetch returned $0 at card time). Re-resolves the price from the CURATED PRICES table
    ONLY (fetch stubbed to zero, so a card priced live keeps its number and no network is hit), and
    rewrites only when a nonzero price now resolves. Returns a NEW card; healthy cards pass through
    unchanged (same object)."""
    cost = card.get("cost", {})
    ptok, ctok = cost.get("prompt_tokens", 0), cost.get("completion_tokens", 0)
    if (ptok or ctok) and not cost.get("est_cost_usd", 0.0):
        (p_in, p_out), source = _price_for(card["model"], fetch=lambda _m: (0.0, 0.0))
        if p_in or p_out:
            usd = (ptok * p_in + ctok * p_out) / 1e6
            games = _games_played(card) or 1
            new_cost = {**cost, "price_source": source, "price_per_1m": [p_in, p_out],
                        "est_cost_usd": round(usd, 4), "cost_per_game_usd": round(usd / games, 4)}
            return {**card, "cost": new_cost}
    return card


def annotate(cards: list[dict]) -> list[dict]:
    """Reprice any stale $0 card, then stamp (errored, failure_rate) -- the merge/display pass that
    flags the existing cards WITHOUT re-running. Immutable: returns new cards, inputs untouched."""
    out = []
    for card in cards:
        card = _reprice(card)
        out.append({**card, **_validity(card)})
    return out


def _rank_key(card: dict) -> tuple:
    """The discriminating multi-axis rank. The validated degree-of-success score leads; when it
    CLUSTERS (a wall of zeros -- every net-negative / high-reject general scores exactly 0) the
    continuous play-quality signals break the tie in priority order: crack rate, then combat
    efficiency (kill ratio), order discipline (lower reject is better), garrison drawdown (a lower
    mean ammo-min means the storm was driven harder toward the 15.15 dry stack), and only THEN
    ground gained. advance% ranks LAST -- so a mauled advancer never outranks a real fighter: we
    do not pay for marching into a massacre. This is the re-weight the single score can't give."""
    cam, s = card["campaign"], card["siege"]
    ammo = s.get("mean_ammo_min")
    return (
        cam["mean_score"],
        s["crack_rate_pct"],
        cam["mean_kill_ratio"],
        -cam["reject_rate_pct"],                          # fewer bounced orders = better
        -(ammo if ammo is not None else float("inf")),    # lower ammo-min = drove harder = better
        cam["mean_advance_pct"],                          # ground LAST: never rewards a massacre
        -cam["mean_turn_invested"],                       # faster investment breaks a final tie
    )


def leaderboard(cards: list[dict]) -> None:
    """MULTI-AXIS ranked scorecard (the owner's #1 concern -- don't ship a wall of zeros). Only VALID
    models are ranked (by _rank_key, so they SEPARATE even when the single degree-of-success score
    collapses to 0); ERRORED models -- whose calls mostly failed, so their score is the scripted
    fallback's, not real play -- are listed separately below with their failure rate. Validity is
    (re)computed here at DISPLAY time, so the existing cards are flagged without re-running."""
    cards = annotate(cards)                                   # reprice stale $ + flag errored
    valid = [c for c in cards if not c["errored"]]
    errored = [c for c in cards if c["errored"]]
    rows = sorted(valid, key=_rank_key, reverse=True)
    print("\n=== LEADERBOARD (multi-axis: score, then crack / kill / reject / ammo-drive) ===")
    hdr = (f"{'model':<26}{'SCORE':>7}{'crack%':>7}{'kill':>6}{'rej%':>6}{'mAmmo':>7}"
           f"{'starv%':>7}{'adv':>5}{'invT':>6}{'tok/s':>7}{'min/gm':>7}{'$/gm':>8}")
    print(hdr + "\n" + "-" * len(hdr))
    for c in rows:
        s, cam, co = c["siege"], c["campaign"], c["cost"]
        tm = c.get("timing", {})
        am = s.get("mean_ammo_min")
        print(f"{c['model'][:25]:<26}{cam['mean_score']:>7}{s['crack_rate_pct']:>7}"
              f"{cam['mean_kill_ratio']:>6}{cam['reject_rate_pct']:>6}"
              f"{('-' if am is None else am):>7}{100 * s['starved_fraction']:>7.0f}"
              f"{cam['mean_advance_pct']:>5.0f}{cam['mean_turn_invested']:>6}"
              f"{tm.get('completion_tok_per_s', 0):>7}{tm.get('mean_minutes_per_game', 0):>7}"
              f"{co['cost_per_game_usd']:>8}")
    if errored:
        print("\n=== EXCLUDED -- errored (high API-failure rate; score is scripted fallback, "
              "not real play) ===")
        print(f"{'model':<26}{'fail%':>7}{'calls/gm':>10}")
        for c in sorted(errored, key=lambda c: (-c["failure_rate"], -_calls_per_game(c))):
            print(f"{c['model'][:25]:<26}{100 * c['failure_rate']:>7.1f}"
                  f"{_calls_per_game(c):>10.1f}")


def merge_caches(sources: list[str], dest: str) -> dict:
    """Union per-process cache files into one shared cache. Each model process runs with its OWN
    --cache file, so N models can run as N PARALLEL processes without racing/clobbering the shared
    sidecar; this folds them back together afterwards. The sha256(model+prompt) keys never collide
    across distinct models, so the union is loss-free (a later source still wins any exact-key
    repeat). Missing source files are skipped. Returns + writes the merged cache."""
    merged: dict = {}
    for src in sources:
        p = Path(src)
        if p.exists():
            merged.update(json.loads(p.read_text()))
    Path(dest).write_text(json.dumps(merged))
    return merged


def _write(path: str, cards: list[dict]) -> None:
    p = Path(path)
    existing = []
    if p.exists():
        try:
            existing = json.loads(p.read_text()).get("cards", [])
        except ValueError:
            existing = []
    keys = {c["model"] for c in cards}
    merged = [c for c in existing if c["model"] not in keys] + cards
    _atomic_write(p, json.dumps({"cards": merged}, indent=2))     # never leave a half-written card


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="inception/mercury-2",
                    help="comma-separated OpenRouter model slugs")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--mock", action="store_true", help="free dry-run, no API calls (MockClient)")
    ap.add_argument("--live", action="store_true", help="live scorecard (reads the key file)")
    ap.add_argument("--recache", action="store_true", help="replay against the cache, model OFF")
    ap.add_argument("--no-floor", dest="floor", action="store_false",
                    help="storm floor OFF -- the model-only 'did the staff earn the crack' signal")
    ap.add_argument("--earned-crack", action="store_true",
                    help="ALSO play each seed's siege with the storm floor OFF into a separate "
                         "'earned_crack' scorecard block -- did the staff crack Tobruk with NO "
                         "scripted assault help (the real-generalship signal)")
    ap.add_argument("--workers", type=int, default=5, help="concurrent seeds in flight")
    ap.add_argument("--cache", default=str(CACHE_PATH),
                    help="per-process sidecar cache file -- give each parallel model its OWN so "
                         "N models run as N processes without racing the shared cache")
    ap.add_argument("--merge-caches", default=None,
                    help="comma-list of cache files to union into --cache, then exit "
                         "(fold the per-process caches back after a parallel run)")
    ap.add_argument("--out", default=str(OUT / "leaderboard.json"))
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(line_buffering=True)       # a slow model stays observable, not hung
    except (AttributeError, ValueError):
        pass

    OUT.mkdir(exist_ok=True)
    if args.merge_caches:
        srcs = [s.strip() for s in args.merge_caches.split(",") if s.strip()]
        merged = merge_caches(srcs, args.cache)
        print(f"merged {len(srcs)} cache file(s) -> {args.cache} ({len(merged)} entries)")
        return 0

    if not (args.mock or args.live or args.recache):
        ap.error("pass --mock, --live, or --recache")
    live = args.live
    if live:
        _load_key()
        _assert_key_billed()                              # bill the CFNA key, not the ambient one

    cache_path = Path(args.cache)
    # Recover the compacted cache PLUS any journal a prior kill left mid-run (load_cache tolerates
    # a torn final line). Mock runs never touch disk.
    cache = {} if args.mock else load_cache(cache_path)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    cards = []
    for model in models:
        print(f"\n>>> {model} ({args.seeds} seeds x 2 scenarios)"
              f"{'  [MOCK]' if args.mock else ''}")
        # A shared journal fsyncs every paid completion to disk before it returns, so a SIGKILL
        # mid-model loses ~$0 -- the finished calls replay FREE via load_cache on resume.
        journal = None if args.mock else Journal(str(cache_path) + ".jsonl")
        card = run_model(model, args.seeds, mock=args.mock, live=live, floor=args.floor,
                         cache=cache, workers=args.workers, earned_crack=args.earned_crack,
                         journal=journal)
        cards.append(card)
        if journal is not None:
            journal.close()
            compact(cache_path, cache)                     # clean finish: fold journal into P, drop it
        _write(args.out, [card])                           # crash-safe: persist after each model

    leaderboard(cards)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
