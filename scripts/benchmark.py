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

# Route to the fastest HIGH-PRECISION endpoint. Many DeepSeek providers serve at
# 15-20 tok/s and stall runs; and fp4 (4-bit) endpoints vary model quality game-to-
# game, which would be unfair for a benchmark. Sorting by throughput needs no
# provider list to maintain; the quantization floor keeps quality consistent.
FAST_PROVIDER = {"sort": "throughput", "quantizations": ["fp8", "bf16", "fp16"]}


def _strength(state, side: Side) -> int:
    return sum(u.strength for u in state.units if u.side == side)


# --- Axis-generalship score (0-125) --------------------------------------------
# The scenario's real skill is cracking a hard defense with sustained combined arms.
# advance% saturates (~99% for all) and a naive beeliner invests FASTEST, so scoring
# on advance/speed rewards NON-fighting -- an adversarial review broke the first
# attempt (a pacifist marcher and a one-kill farmer out-scored a real assaulter).
# This rewards DESTROYING the defense efficiently, gates tempo on real combat, and
# treats advance as a qualifier. Constants calibrated to the measured distribution:
# D0~163 defender steps; capable models inflict ~45-51 & lose ~64-70; a naive
# scripted charge nets ~29 (allied_lost - 0.5*axis_lost).
_LAMBDA = 0.5         # own losses discounted vs enemy destroyed (attacker's loss disadvantage)
_SCALE = 0.25         # net-destroying this fraction of the defense = full combat score
_TMIN = 6             # fastest realistic investment turn (measured)
_FIGHT_FLOOR = 0.20   # tempo counts only above this much real combat (defeats farm-one-kill)
_CLEAN_CAP = 20.0     # Axis reject% at/above which cleanliness scores 0


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _score(g: dict, max_turns: int) -> dict:
    """Per-game generalship score (0-125) + its 0-1 components. combat (net defence
    destroyed) is primary; clean (order discipline) secondary; tempo (speed) a minor
    term GATED on having actually fought; advance is a multiplier + a capture bonus."""
    d0 = max(1, g["defender_strength"])
    combat = _clamp((g["allied_losses"] - _LAMBDA * g["axis_losses"]) / (_SCALE * d0))
    axis_orders = g["moves"] + g["axis_assaults"] + g["rejections"]
    reject_rate = 100 * g["rejections"] / max(1, axis_orders)
    clean = _clamp(1 - reject_rate / _CLEAN_CAP)
    tempo = (_clamp((max_turns - g["turn_invested"]) / (max_turns - _TMIN))
             if combat > _FIGHT_FLOOR else 0.0)
    adv_mult = 0.5 + 0.5 * g["advance_pct"] / 100
    capture = 25.0 if g["advance_pct"] >= 100 else 0.0
    score = adv_mult * 100 * (0.60 * combat + 0.25 * clean + 0.15 * tempo) + capture
    return {"combat": round(combat, 3), "clean": round(clean, 3), "tempo": round(tempo, 3),
            "reject_rate_game": round(reject_rate, 1), "score": round(score, 1)}


def game_metrics(result) -> dict:
    ev = result.events

    def count(kind: EventKind) -> int:
        return sum(1 for e in ev if e.kind == kind)

    def count_axis(kind: EventKind) -> int:                     # LLM-side only (decision quality)
        return sum(1 for e in ev if e.kind == kind and e.side == Side.AXIS)

    reject_reasons: dict = {}                                   # why the LLM's orders bounced
    for e in ev:
        if e.kind == EventKind.ORDER_REJECTED and e.side == Side.AXIS:
            key = e.payload.get("reason", "?")[:44]
            reject_reasons[key] = reject_reasons.get(key, 0) + 1

    victory = [e for e in ev if e.kind == EventKind.VICTORY_CHECKED]
    advance = victory[-1].payload.get("axis", 0) if victory else 0
    # Speed discriminator: first turn the Axis invests Tobruk (reach <= 2). Advance %
    # is saturated (~99% for every capable model), so *how fast* separates them.
    invested = next((i + 1 for i, e in enumerate(victory)
                     if e.payload.get("axis_reach", 99) <= 2), None)
    turn_invested = invested if invested is not None else result.final.turn + 1
    axis_lost = _strength(result.initial, Side.AXIS) - _strength(result.final, Side.AXIS)
    allied_lost = _strength(result.initial, Side.ALLIED) - _strength(result.final, Side.ALLIED)
    supply_rejects = sum(v for k, v in reject_reasons.items()
                         if any(w in k for w in ("supply", "fuel", "ammo")))
    g = {
        "winner": result.winner.value,
        "advance_pct": advance,
        "turns": result.final.turn,
        "barrages": count(EventKind.BARRAGE_RESOLVED),
        "anti_armor": count(EventKind.ANTI_ARMOR_RESOLVED),
        "close_assaults": count(EventKind.COMBAT_RESOLVED),
        "axis_assaults": count_axis(EventKind.COMBAT_RESOLVED),   # Axis-initiated only
        "rejections": count_axis(EventKind.ORDER_REJECTED),
        "reject_reasons": reject_reasons,
        "supply_rejects": supply_rejects,
        "turn_invested": turn_invested,
        "moves": count_axis(EventKind.UNIT_MOVED),
        "axis_losses": axis_lost,
        "allied_losses": allied_lost,
        "defender_strength": _strength(result.initial, Side.ALLIED),
    }
    g.update(_score(g, result.final.max_turns))
    return g


def run_model(model: str, games: int, mock: bool, mode: str = "stateless",
              reasoning: str | None = None, base_seed: int = 4200) -> dict:
    """N games of LLM(Axis) vs scripted(Commonwealth) in the given memory `mode`.
    Returns the aggregate row. A fresh client per model accumulates usage; the
    policy is reset between games so stateful/hybrid memory doesn't leak across them."""
    client = (MockClient(_mock_axis) if mock else
              OpenRouterClient(model, reasoning_effort=reasoning, timeout=45, retries=1,
                               provider=FAST_PROVIDER))
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
    # AXIS-only order denominator (close_assaults counted BOTH sides -- a bug that let
    # provoking enemy counterattacks lower your reject rate).
    orders = sum(g["moves"] + g["axis_assaults"] + g["rejections"] for g in per_game)
    reject_rate = round(100 * sum(g["rejections"] for g in per_game) / max(1, orders), 1)
    reasons: dict = {}
    for g in per_game:
        for k, v in g.get("reject_reasons", {}).items():
            reasons[k] = reasons.get(k, 0) + v
    reasons = dict(sorted(reasons.items(), key=lambda kv: -kv[1]))
    p_in, p_out = PRICES.get(model, (0.0, 0.0))
    cost = (usage.get("prompt_tokens", 0) * p_in + usage.get("completion_tokens", 0) * p_out) / 1e6
    return {
        "model": model,
        "mode": mode,
        "games": n,
        "axis_win_rate": round(100 * axis_wins / n, 1),
        "mean_score": round(mean(g["score"] for g in per_game), 1),
        "mean_combat": round(mean(g["combat"] for g in per_game), 3),
        "mean_clean": round(mean(g["clean"] for g in per_game), 3),
        "mean_tempo": round(mean(g["tempo"] for g in per_game), 3),
        "score_spread": [min(g["score"] for g in per_game), max(g["score"] for g in per_game)],
        "mean_advance_pct": round(mean(g["advance_pct"] for g in per_game), 1),
        "best_advance_pct": max(g["advance_pct"] for g in per_game),
        "mean_turn_invested": round(mean(g["turn_invested"] for g in per_game), 1),
        "mean_kill_ratio": round(kill_ratio, 2),
        "mean_supply_rejects": round(mean(g["supply_rejects"] for g in per_game), 1),
        "reject_rate_pct": reject_rate,
        "reject_reasons": reasons,
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
    rows = sorted(rows, key=lambda r: r.get("mean_score", 0), reverse=True)
    print("\n=== LEADERBOARD (Axis generalship score; combat=net defence destroyed) ===")
    hdr = (f"{'model':<23}{'mode':>9}{'SCORE':>7}{'cbt':>6}{'cln':>6}{'tmp':>6}"
           f"{'adv':>5}{'invT':>6}{'rej%':>6}{'$/gm':>7}")
    print(hdr + "\n" + "-" * len(hdr))
    for r in rows:
        print(f"{r['model'][:22]:<23}{r.get('mode', ''):>9}{r.get('mean_score', 0):>7}"
              f"{r.get('mean_combat', 0):>6}{r.get('mean_clean', 0):>6}{r.get('mean_tempo', 0):>6}"
              f"{r['mean_advance_pct']:>5.0f}{r.get('mean_turn_invested', 0):>6}"
              f"{r['reject_rate_pct']:>6}{r['cost_per_game_usd']:>7}")


def paired_ranking(rows: list[dict]) -> None:
    """Primary ranking (subagent's rec): matched-seed head-to-head on the combat
    metric. Every entrant plays the same seeds (identical engine dice), so pairing
    cancels the dice luck that a raw composite at small n launders into a point score."""
    import itertools
    entries = [(f"{r['model']}/{r.get('mode', '')}", [g["combat"] for g in r.get("games_detail", [])])
               for r in rows]
    entries = [(name, c) for name, c in entries if c]
    if len(entries) < 2:
        return
    wins = {name: 0.0 for name, _ in entries}
    played = {name: 0 for name, _ in entries}
    for (na, ca), (nb, cb) in itertools.combinations(entries, 2):
        for i in range(min(len(ca), len(cb))):                  # same index == same seed
            played[na] += 1
            played[nb] += 1
            if ca[i] > cb[i]:
                wins[na] += 1
            elif cb[i] > ca[i]:
                wins[nb] += 1
            else:
                wins[na] += 0.5
                wins[nb] += 0.5
    print("\n=== PAIRED SAME-SEED RANKING (combat metric win-rate vs the field) ===")
    for name in sorted(wins, key=lambda k: -wins[k] / max(1, played[k])):
        print(f"  {name:<42} {100 * wins[name] / max(1, played[name]):>3.0f}%  "
              f"({wins[name]:.1f}/{played[name]})")


def _merge_write(path: str, new_rows: list[dict]) -> list[dict]:
    """Merge rows into the output by (model, mode) key, replacing any match. Called
    after each config so a crash (this env segfaults / restarts often) never loses a
    completed config."""
    p = Path(path)
    existing = []
    if p.exists():
        try:
            existing = json.loads(p.read_text()).get("rows", [])
        except ValueError:
            existing = []
    keys = {(r["model"], r.get("mode")) for r in new_rows}
    merged = [r for r in existing if (r["model"], r.get("mode")) not in keys] + new_rows
    p.write_text(json.dumps({"rows": merged}, indent=2))
    return merged


def _done_configs(path: str) -> set:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        return {(r["model"], r.get("mode")) for r in json.loads(p.read_text()).get("rows", [])}
    except ValueError:
        return set()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="deepseek/deepseek-chat",
                    help="comma-separated OpenRouter model slugs")
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--mode", default="stateless",
                    help="memory mode(s), comma-list: stateless,stateful,hybrid")
    ap.add_argument("--mock", action="store_true", help="free dry-run, no API calls")
    ap.add_argument("--reasoning", default=None,
                    help="reasoning effort for reasoning models: low|medium|high (default: provider)")
    ap.add_argument("--resume", action="store_true",
                    help="skip (model,mode) configs already present in --out (crash recovery)")
    ap.add_argument("--out", default="benchmark_results.json")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    modes = [m.strip() for m in args.mode.split(",") if m.strip()]
    done = _done_configs(args.out) if args.resume else set()
    rows = []
    for mode in modes:
        for model in models:
            if (model, mode) in done:
                print(f"\n>>> [{mode}] {model}: SKIP (already in {args.out})")
                continue
            print(f"\n>>> [{mode}] {model} ({args.games} games){'  [MOCK]' if args.mock else ''}")
            row = run_model(model, args.games, args.mock, mode, args.reasoning)
            rows.append(row)
            _merge_write(args.out, [row])       # crash-safe: persist after each config
    all_rows = json.loads(Path(args.out).read_text())["rows"] if Path(args.out).exists() else rows
    leaderboard(all_rows)
    paired_ranking(all_rows)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
