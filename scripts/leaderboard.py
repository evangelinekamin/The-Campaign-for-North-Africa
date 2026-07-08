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
import sys
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
from game.llm import CachingClient, MockClient, OpenRouterClient            # noqa: E402
from game.policy import ScriptedPolicy                                      # noqa: E402
from game.scenario import rommels_arrival, siege_of_tobruk                  # noqa: E402
from game.staff_policy import LLM_SEATS, StaffPolicy                        # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "out"
CACHE_PATH = OUT / "leaderboard.cache.json"

# The garrison opens the siege on ~1500-2351 Ammo Points (the built-in 61.36 dump + the
# adjacent AL-Dump#3). A TIMID general lets the ferry outpace the storm and the dump plateaus
# high (mercury-2 leaves it ~2200, RISING); a GOOD general sustains the storm and drives the
# curve toward the 15.15 dry-stack fire at 0. A seed counts as STARVED when the garrison's ammo
# was driven below this floor -- cleanly below both the ~1500 opening and the timid plateau.
STARVE_FLOOR = 500

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


def _seat_clients(model: str, cache: dict, *, live: bool) -> dict:
    """One client per LLM seat, each wrapped in the SHARED sidecar cache. Distinct inner
    clients so parallel seats never race on usage; live=False plugs a disconnected inner so a
    fully-cached re-run needs no network and no key."""
    def inner():
        return (OpenRouterClient(model, temperature=0.0, timeout=45, retries=1,
                                 provider=FAST_PROVIDER) if live else _Disconnected(model))
    return {seat: CachingClient(inner(), cache) for seat in LLM_SEATS}


def _staff(model: str, cache: dict, *, mock: bool, live: bool, floor: bool) -> StaffPolicy:
    """The Axis command staff for one game. In mock mode every seat falls back to the shared
    zero-token MockClient(_mock_staff); otherwise each LLM seat gets its own cached live/
    disconnected client. `floor` arms the storming floor (siege only)."""
    seats = None if mock else _seat_clients(model, cache, live=live)
    return StaffPolicy(MockClient(_mock_staff), side=Side.AXIS, seat_clients=seats,
                       max_workers=1 if mock else len(LLM_SEATS), storm_floor=floor)


def _play_rommel(model: str, seed: int, cache: dict, *, mock: bool, live: bool) -> tuple[dict, dict]:
    axis = _staff(model, cache, mock=mock, live=live, floor=False)
    result = run(rommels_arrival(seed=seed), axis=axis,
                 allied=ScriptedPolicy(attacker=Side.AXIS))
    assert fold(result.initial, result.events) == result.final, f"rommel replay FAILED seed={seed}"
    return game_metrics(result), axis.usage()


def _play_siege(model: str, seed: int, cache: dict, *, mock: bool, live: bool,
                floor: bool) -> tuple[dict, dict]:
    axis = _staff(model, cache, mock=mock, live=live, floor=floor)
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


def _price_for(model: str, fetch=_fetch_openrouter_price) -> tuple[tuple[float, float], str]:
    """(prompt, completion) per-1M-token price + its source. PRICES first (curated, offline);
    otherwise the OpenRouter catalogue."""
    if model in PRICES:
        return PRICES[model], "PRICES"
    return fetch(model), "openrouter"


def _cost_block(model: str, usage: dict, games: int) -> dict:
    ptok, ctok = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    if ptok == 0 and ctok == 0:                           # nothing to price -> stay offline
        (p_in, p_out) = PRICES.get(model, (0.0, 0.0))
        source = "PRICES" if model in PRICES else "unpriced"
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
    return block


def run_model(model: str, seeds: int, *, mock: bool, live: bool, floor: bool,
              cache: dict, base_seed: int = BASE_SEED, workers: int = 5) -> dict:
    """N seeds of the live 7-seat Axis StaffPolicy on BOTH scenarios -> one SCORECARD dict.
    The two scenarios run CONCURRENTLY over their own seats sharing the sidecar cache; the
    engine is pure per-game, so concurrency is an I/O win only and never perturbs the fold."""
    par = 1 if mock else workers

    def one(i: int) -> tuple[dict, dict, dict, dict]:
        seed = base_seed + i
        rg, ru = _play_rommel(model, seed, cache, mock=mock, live=live)
        st, su = _play_siege(model, seed, cache, mock=mock, live=live, floor=floor)
        mark = "CRACK" if st["crack"] else "held"
        print(f"    {model}  seed {seed}: rommel score {rg['score']} adv {rg['advance_pct']}% | "
              f"siege {mark} AL-ammo peak {st['al_tobruk_ammo_peak']}->min {st['al_tobruk_ammo_min']} "
              f"surr={st['surrender_path']}", flush=True)
        return rg, ru, st, su

    with ThreadPoolExecutor(max_workers=par) as ex:
        outs = list(ex.map(one, range(seeds)))

    per_game = [rg for rg, _, _, _ in outs]
    tels = [st for _, _, st, _ in outs]
    usage = _sum_usage([ru for _, ru, _, _ in outs] + [su for _, _, _, su in outs])
    return {
        "model": model,
        "seeds": seeds,
        "floor": floor,
        "campaign": _campaign_block(model, per_game),        # rommels_arrival degree-of-success
        "siege": _siege_summary(tels),                       # crack-generalship
        "cost": _cost_block(model, usage, games=2 * seeds),  # both scenarios
    }


def leaderboard(cards: list[dict]) -> None:
    """Combined ranked table: crack rate first (did the general take Tobruk), the campaign
    generalship score as the tie-break, with the starve signal + cost alongside."""
    rows = sorted(cards, key=lambda c: (c["siege"]["crack_rate_pct"],
                                        c["campaign"]["mean_score"]), reverse=True)
    print("\n=== LEADERBOARD (crack rate, then campaign generalship score) ===")
    hdr = (f"{'model':<26}{'crack%':>7}{'starv%':>7}{'ammoMin':>8}{'SCORE':>7}{'adv':>5}"
           f"{'invT':>6}{'kill':>6}{'$/gm':>8}")
    print(hdr + "\n" + "-" * len(hdr))
    for c in rows:
        s, cam, co = c["siege"], c["campaign"], c["cost"]
        am = s["ammo_min_reached"]
        print(f"{c['model'][:25]:<26}{s['crack_rate_pct']:>7}{100 * s['starved_fraction']:>7.0f}"
              f"{('-' if am is None else am):>8}{cam['mean_score']:>7}{cam['mean_advance_pct']:>5.0f}"
              f"{cam['mean_turn_invested']:>6}{cam['mean_kill_ratio']:>6}{co['cost_per_game_usd']:>8}")


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
    p.write_text(json.dumps({"cards": merged}, indent=2))


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
    ap.add_argument("--workers", type=int, default=5, help="concurrent seeds in flight")
    ap.add_argument("--out", default=str(OUT / "leaderboard.json"))
    args = ap.parse_args()

    if not (args.mock or args.live or args.recache):
        ap.error("pass --mock, --live, or --recache")
    live = args.live
    if live:
        _load_key()
        _assert_key_billed()                              # bill the CFNA key, not the ambient one

    OUT.mkdir(exist_ok=True)
    cache = (json.loads(CACHE_PATH.read_text())
             if (not args.mock and CACHE_PATH.exists()) else {})
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    cards = []
    for model in models:
        print(f"\n>>> {model} ({args.seeds} seeds x 2 scenarios)"
              f"{'  [MOCK]' if args.mock else ''}")
        card = run_model(model, args.seeds, mock=args.mock, live=live, floor=args.floor,
                         cache=cache, workers=args.workers)
        cards.append(card)
        if not args.mock:
            CACHE_PATH.write_text(json.dumps(cache))
        _write(args.out, [card])                          # crash-safe: persist after each model

    leaderboard(cards)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
