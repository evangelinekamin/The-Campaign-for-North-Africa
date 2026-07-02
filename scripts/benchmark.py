"""Benchmark LLM models on Rommel's Arrival (brief §8).

Each model commands the AXIS -- the decision-rich attacker: it must advance the
combined German-Italian force up the coast, use combined arms (barrage, anti-armor,
close assault), manage supply, and crack the Commonwealth defence -- against a fixed
SCRIPTED Commonwealth defender. Because the scenario is faithfully Axis-hard (Tobruk
historically held), the primary metric is NOT win/lose but DEGREE OF SUCCESS: the
Axis advance % (fraction of the El-Agheila->Tobruk gap closed), plus kill ratio,
decision quality (order-rejection rate), and cost.

    python3 -m scripts.benchmark --mock                    # free dry-run (no API, MockClient)
    python3 -m scripts.benchmark --games 5 \
        --models deepseek/deepseek-chat,google/gemini-2.0-flash-001,openai/gpt-4o-mini

Results are written to a JSON file (--out) for the visualiser and printed as a
leaderboard sorted by mean advance %. LLM games are not bit-deterministic (the model
varies), so N games per model are averaged; the engine dice are still seeded per game.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.engine import run                                     # noqa: E402
from game.events import EventKind, Side                         # noqa: E402
from game.llm import MockClient, OpenRouterClient               # noqa: E402
from game.llm_policy import LLMPolicy                           # noqa: E402
from game.policy import ScriptedPolicy                          # noqa: E402
from game.scenario import rommels_arrival                       # noqa: E402

# Rough OpenRouter prices (USD per 1M tokens, prompt/completion) for cost estimates.
# Approximate + will drift -- treat as ballpark, not billing. Unknown models -> 0.
PRICES = {
    "deepseek/deepseek-chat":            (0.28, 0.88),
    "google/gemini-2.0-flash-001":       (0.10, 0.40),
    "openai/gpt-4o-mini":                (0.15, 0.60),
    "meta-llama/llama-3.3-70b-instruct": (0.12, 0.30),
    "anthropic/claude-3.5-haiku":        (0.80, 4.00),
    "openai/gpt-4o":                     (2.50, 10.00),
    "google/gemini-2.5-pro":             (1.25, 10.00),
    "anthropic/claude-3.7-sonnet":       (3.00, 15.00),
    "openai/o4-mini":                    (1.10, 4.40),
    # mode-test roster (real OpenRouter prices, mid-2026)
    "anthropic/claude-haiku-4.5":        (1.00, 5.00),
    "openai/gpt-5.4-mini":               (0.75, 4.50),
    "deepseek/deepseek-v4-flash":        (0.09, 0.18),
    "deepseek/deepseek-v4-pro":          (0.435, 0.87),
}


def _strength(state, side: Side) -> int:
    return sum(u.strength for u in state.units if u.side == side)


def game_metrics(result) -> dict:
    ev = result.events

    def count(kind: EventKind) -> int:
        return sum(1 for e in ev if e.kind == kind)

    def count_axis(kind: EventKind) -> int:                     # LLM-side only (decision quality)
        return sum(1 for e in ev if e.kind == kind and e.side == Side.AXIS)

    victory = [e for e in ev if e.kind == EventKind.VICTORY_CHECKED]
    advance = victory[-1].payload.get("axis", 0) if victory else 0
    axis_lost = _strength(result.initial, Side.AXIS) - _strength(result.final, Side.AXIS)
    allied_lost = _strength(result.initial, Side.ALLIED) - _strength(result.final, Side.ALLIED)
    return {
        "winner": result.winner.value,
        "advance_pct": advance,
        "turns": result.final.turn,
        "barrages": count(EventKind.BARRAGE_RESOLVED),
        "anti_armor": count(EventKind.ANTI_ARMOR_RESOLVED),
        "close_assaults": count(EventKind.COMBAT_RESOLVED),
        "rejections": count_axis(EventKind.ORDER_REJECTED),
        "moves": count_axis(EventKind.UNIT_MOVED),
        "axis_losses": axis_lost,
        "allied_losses": allied_lost,
    }


def run_model(model: str, games: int, mock: bool, mode: str = "stateless",
              base_seed: int = 4200) -> dict:
    """N games of LLM(Axis) vs scripted(Commonwealth) in the given memory `mode`.
    Returns the aggregate row. A fresh client per model accumulates usage; the
    policy is reset between games so stateful/hybrid memory doesn't leak across them."""
    client = MockClient(_mock_axis) if mock else OpenRouterClient(model)
    axis = LLMPolicy(Side.AXIS, client, mode=mode)
    defender = ScriptedPolicy(Side.ALLIED)
    per_game = []
    for i in range(games):
        axis.reset()
        result = run(rommels_arrival(seed=base_seed + i), axis=axis, allied=defender)
        per_game.append(game_metrics(result))
        print(f"    [{mode}] {model}  game {i + 1}/{games}: advance "
              f"{per_game[-1]['advance_pct']}% ({result.winner.value}), "
              f"{per_game[-1]['rejections']} rejects", flush=True)
    usage = client.usage() if hasattr(client, "usage") else {}
    return _aggregate(model, per_game, usage, mode)


def _aggregate(model: str, per_game: list[dict], usage: dict, mode: str = "stateless") -> dict:
    n = len(per_game)
    axis_wins = sum(1 for g in per_game if g["winner"] == "AXIS")
    kill_ratio = mean(g["allied_losses"] / max(1, g["axis_losses"]) for g in per_game)
    orders = sum(g["moves"] + g["close_assaults"] + g["rejections"] for g in per_game)
    reject_rate = round(100 * sum(g["rejections"] for g in per_game) / max(1, orders), 1)
    p_in, p_out = PRICES.get(model, (0.0, 0.0))
    cost = (usage.get("prompt_tokens", 0) * p_in + usage.get("completion_tokens", 0) * p_out) / 1e6
    return {
        "model": model,
        "mode": mode,
        "games": n,
        "axis_win_rate": round(100 * axis_wins / n, 1),
        "mean_advance_pct": round(mean(g["advance_pct"] for g in per_game), 1),
        "best_advance_pct": max(g["advance_pct"] for g in per_game),
        "mean_kill_ratio": round(kill_ratio, 2),
        "mean_close_assaults": round(mean(g["close_assaults"] for g in per_game), 1),
        "reject_rate_pct": reject_rate,
        "llm_calls": usage.get("calls", 0),
        "llm_failures": usage.get("failures", 0),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "est_cost_usd": round(cost, 4),
        "cost_per_game_usd": round(cost / n, 4),
        "games_detail": per_game,
    }


def _mock_axis(prompt: str) -> str:
    """Cheap deterministic Axis for --mock: each unit advances to the nearest
    unclaimed reachable hex (dedup avoids self-stacking), and assaults every option."""
    obj = _extract(prompt)
    if not obj:
        return "{}"
    if "MOVEMENT" in prompt:
        claimed, moves = set(), []
        for u in obj.get("your_units", []):
            for dest in u.get("can_move_to", []):
                h = tuple(dest["hex"])
                if h not in claimed:
                    claimed.add(h)
                    moves.append({"unit": u["id"], "to": dest["hex"]})
                    break
        return json.dumps({"reasoning": "advance", "moves": moves})
    attacks = [{"attackers": o["your_attackers"], "target": o["target"]}
               for o in obj.get("attack_options", [])]
    return json.dumps({"reasoning": "assault", "attacks": attacks})


def _extract(prompt: str) -> dict:
    """Pull the embedded observation object out of a prompt: the first BALANCED
    {...} after the 'Situation (JSON):' marker (the naive first-brace/last-brace
    span would swallow the example-reply JSON and prose and fail to parse)."""
    start = prompt.find("{", prompt.find("Situation (JSON):"))
    if start == -1:
        return {}
    depth = 0
    for j in range(start, len(prompt)):
        depth += (prompt[j] == "{") - (prompt[j] == "}")
        if depth == 0:
            try:
                return json.loads(prompt[start:j + 1])
            except ValueError:
                return {}
    return {}


def leaderboard(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: r["mean_advance_pct"], reverse=True)
    print("\n=== LEADERBOARD (Axis on Rommel's Arrival, higher advance = better) ===")
    hdr = (f"{'model':<28}{'mode':>10}{'adv%':>6}{'best':>6}{'kill':>6}"
           f"{'rej%':>6}{'calls':>7}{'$/game':>9}")
    print(hdr + "\n" + "-" * len(hdr))
    for r in rows:
        print(f"{r['model']:<28}{r.get('mode', ''):>10}{r['mean_advance_pct']:>6}"
              f"{r['best_advance_pct']:>6}{r['mean_kill_ratio']:>6}{r['reject_rate_pct']:>6}"
              f"{r['llm_calls']:>7}{r['cost_per_game_usd']:>9}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="deepseek/deepseek-chat",
                    help="comma-separated OpenRouter model slugs")
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--mode", default="stateless",
                    help="memory mode(s), comma-list: stateless,stateful,hybrid")
    ap.add_argument("--mock", action="store_true", help="free dry-run, no API calls")
    ap.add_argument("--out", default="benchmark_results.json")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    modes = [m.strip() for m in args.mode.split(",") if m.strip()]
    rows = []
    for mode in modes:
        for model in models:
            print(f"\n>>> [{mode}] {model} ({args.games} games){'  [MOCK]' if args.mock else ''}")
            rows.append(run_model(model, args.games, args.mock, mode))
    Path(args.out).write_text(json.dumps({"rows": rows}, indent=2))
    leaderboard(rows)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
