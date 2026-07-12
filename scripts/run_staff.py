"""Launcher for the live command-staff (design Steps 6-7). This script is NOT part of
the immutable core: it loads the OpenRouter key into the environment ONCE, wires a real
OpenRouterClient per staff seat (openai/gpt-oss-120b, throughput-routed) behind
the SAME StaffPolicy the MockClient proves, and writes the event log plus a
sha256(model+prompt)->text sidecar cache BESIDE it, so a re-simulation reproduces
byte-identical STAFF_* + orders with the model disconnected.

    python3 -m scripts.run_staff --mock       # deterministic dry-run, zero tokens
    python3 -m scripts.run_staff --live        # ONE live smoke game (reads the key file)
    python3 -m scripts.run_staff --recache     # re-run against the populated cache, model OFF

Two determinism regimes are demonstrated:
  * RECORDED-LOG REPLAY = fold(initial, events) -- pure, no client (checked every run).
  * RE-SIMULATION       = the CachingClient sidecar; --recache proves a fully-cached
    re-run reproduces the exact log with a DISCONNECTED inner client.

SECURITY: the key is read from the key file straight into os.environ ONCE and is NEVER
printed, logged, written to the log/cache, or committed. The cache keys on
sha256(model+prompt) -- never the key -- and OpenRouterClient reads the env var only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import FAST_PROVIDER, _mock_staff, game_metrics   # noqa: E402

from game import narrator                                               # noqa: E402
from game.apply import fold                                              # noqa: E402
from game.engine import run                                             # noqa: E402
from game.events import Side, log_to_json                               # noqa: E402
from game.llm import CachingClient, MockClient, OpenRouterClient        # noqa: E402
from game.policy import ScriptedPolicy                                  # noqa: E402
from game.scenario import campaign, rommels_arrival                    # noqa: E402
from game.staff_events import staff_log                                 # noqa: E402
from game.staff_policy import LLM_SEATS, StaffPolicy                    # noqa: E402

KEY_FILE = "/mnt/c/Users/evang/OneDrive/Desktop/as.txt"
MODEL = "openai/gpt-oss-120b"   # dev seat per the generalship leaderboard: command #9, ~$0.026/game,
                                # 507 tok/s, 3.6% illegal, N=5 (mercury-2 is the faster/pricier alternate)
SEED = 4200
OUT = Path(__file__).resolve().parent.parent / "out"
LOG_PATH = OUT / "staff_smoke.log.json"
CACHE_PATH = OUT / "staff_smoke.cache.json"


def _load_key(path: str = KEY_FILE) -> None:
    """Force THIS project's OpenRouter key from the key FILE into the environment,
    OVERWRITING any ambient OPENROUTER_API_KEY (e.g. a different key a shell profile
    exported for another project) -- otherwise an inherited key silently bills the wrong
    account. The raw string goes straight into os.environ, never returned/printed/logged."""
    import os
    key = Path(path).read_text().strip()
    if not key:
        raise SystemExit(f"key file {path} is empty")
    os.environ["OPENROUTER_API_KEY"] = key


class _Disconnected:
    """A client that refuses to call the model -- used by --recache so a cache miss is a
    hard, visible failure ('the model was needed but is disconnected'). model matches the
    live client so the sha256 cache keys line up."""
    model = MODEL

    def complete(self, prompt: str) -> str:
        raise RuntimeError("model disconnected: cache miss during re-simulation")

    def chat(self, messages: list) -> str:
        raise RuntimeError("model disconnected")

    def usage(self) -> dict:
        return {}


def _seat_clients(cache: dict, *, live: bool) -> dict:
    """One client per LLM seat, each wrapped in the SHARED sidecar cache. Distinct inner
    clients so parallel seats never race on usage. live=False plugs a disconnected inner
    so a fully-cached re-run needs no network and no key."""
    def inner():
        return (OpenRouterClient(MODEL, temperature=0.0, timeout=45, retries=1,
                                 provider=FAST_PROVIDER) if live else _Disconnected())
    return {seat: CachingClient(inner(), cache) for seat in LLM_SEATS}


def _play(axis, *, campaign_mode: bool = False, max_turns: "int | None" = None) -> object:
    scen = (campaign(seed=SEED, max_turns=max_turns) if campaign_mode
            else rommels_arrival(seed=SEED))
    return run(scen, axis=axis, allied=ScriptedPolicy(attacker=Side.AXIS))


def _report(result, tag: str) -> None:
    g = game_metrics(result)
    diary = staff_log(result.events)
    print(f"\n[{tag}] winner={result.winner.value if result.winner else 'draw'} advance={g['advance_pct']}% "
          f"turns={g['turns']} axis_moves={g['moves']} axis_assaults={g['axis_assaults']} "
          f"rejects={g['rejections']} reject_rate={g['reject_rate_game']}%")
    print(f"  staff_log: {len(diary)} STAFF_* events "
          f"({sum(1 for e in diary if e.kind.name == 'STAFF_DISSENT')} dissent)")
    assert fold(result.initial, result.events) == result.final, "replay-equivalence FAILED"
    print("  replay-equivalence: OK (fold(initial, events) == final, no client)")
    # The story layer (design Steps 8-9): a deterministic diary projected over the
    # recorded log + the god-view fog diff -- no LLM, every line tracing to an event seq.
    story = narrator.diary(result)
    hidden = narrator.hidden_from_staff(result.initial, Side.AXIS)
    print(f"  narrator: {len(story)} diary line(s); god-view sees {len(hidden)} "
          f"stack(s) the opening staff cannot")
    for ln in story:
        print(f"    [{ln.beat}] {ln.text}")


def _mock(*, campaign_mode: bool = False, max_turns: "int | None" = None) -> int:
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    _report(_play(axis, campaign_mode=campaign_mode, max_turns=max_turns), "MOCK")
    return 0


def _run(*, live: bool, campaign_mode: bool = False, max_turns: "int | None" = None) -> int:
    if live:
        _load_key()
    OUT.mkdir(exist_ok=True)
    log_path = OUT / ("staff_campaign.log.json" if campaign_mode else LOG_PATH.name)
    cache_path = OUT / ("staff_campaign.cache.json" if campaign_mode else CACHE_PATH.name)
    cache = json.loads(cache_path.read_text()) if (not live and cache_path.exists()) else {}
    seats = _seat_clients(cache, live=live)
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS,
                       seat_clients=seats, max_workers=len(LLM_SEATS))
    result = _play(axis, campaign_mode=campaign_mode, max_turns=max_turns)
    _report(result, "LIVE" if live else "RECACHE")
    u = axis.usage()
    print(f"  usage: model={MODEL} calls={u.get('calls', 0)} "
          f"prompt_tok={u.get('prompt_tokens', 0)} completion_tok={u.get('completion_tokens', 0)} "
          f"failures={u.get('failures', 0)} cache_hits={u.get('cache_hits', 0)} "
          f"cache_misses={u.get('cache_misses', 0)}")
    log_path.write_text(log_to_json(result.events))
    cache_path.write_text(json.dumps(cache))
    print(f"  wrote {log_path.name} + {cache_path.name} ({len(cache)} cached prompts) under {OUT}/")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="deterministic dry-run, zero tokens")
    ap.add_argument("--live", action="store_true", help="one live smoke game on the dev model")
    ap.add_argument("--recache", action="store_true",
                    help="re-run against the populated cache with the model disconnected")
    ap.add_argument("--campaign", action="store_true",
                    help="run the full-campaign scenario (default: Rommel's Arrival)")
    ap.add_argument("--turns", type=int, default=None,
                    help="cap the run at N Game-Turns (campaign smoke tests)")
    args = ap.parse_args()
    if args.live:
        return _run(live=True, campaign_mode=args.campaign, max_turns=args.turns)
    if args.recache:
        return _run(live=False, campaign_mode=args.campaign, max_turns=args.turns)
    return _mock(campaign_mode=args.campaign, max_turns=args.turns)


if __name__ == "__main__":
    raise SystemExit(main())
