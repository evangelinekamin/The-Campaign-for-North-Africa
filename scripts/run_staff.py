"""Launcher for the live command-staff (design Steps 6-7). This script is NOT part of
the immutable core: it loads the OpenRouter key into the environment ONCE, wires a real
OpenRouterClient per staff seat (openai/gpt-oss-120b, throughput-routed) behind
the SAME StaffPolicy the MockClient proves, and writes the event log plus a
sha256(model+prompt)->text sidecar cache BESIDE it, so a re-simulation reproduces
byte-identical STAFF_* + orders with the model disconnected.

    python3 -m scripts.run_staff --mock                # deterministic dry-run, zero tokens
    python3 -m scripts.run_staff --live --campaign     # the live campaign (reads the key file)
    python3 -m scripts.run_staff --live --campaign --both-staffs   # BOTH sides live (the CW mirror)
    python3 -m scripts.run_staff --live --fresh        # ignore any prior cache, start clean
    python3 -m scripts.run_staff --recache             # re-run against the populated cache, model OFF

DURABILITY (a multi-hour campaign must survive a kill): every paid completion is fsync'd to a
Journal sidecar the instant it returns, so --live RESUMES BY DEFAULT -- a SIGKILL loses at most
the one call in flight, and re-running replays every finished turn FREE (model off for the cached
prefix, live only past the crash point). A clean finish compacts the journal away.

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
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import FAST_PROVIDER, _mock_staff, game_metrics   # noqa: E402

from game import narrator                                               # noqa: E402
from game.apply import fold                                              # noqa: E402
from game.engine import run                                             # noqa: E402
from game.events import Side, log_to_json                               # noqa: E402
from game.llm import (CachingClient, Journal, MockClient,               # noqa: E402
                      OpenRouterClient, compact, load_cache)
from game.policy import ScriptedPolicy                                  # noqa: E402
from game.scenario import campaign, rommels_arrival                    # noqa: E402
from game.staff_events import staff_log                                 # noqa: E402
from game.staff_policy import LLM_SEATS, StaffPolicy                    # noqa: E402

KEY_FILE = "/mnt/c/Users/evang/OneDrive/Desktop/as.txt"
MODEL = "openai/gpt-oss-120b"   # dev seat per the generalship leaderboard: command #9, ~$0.026/game,
                                # 507 tok/s, 3.6% illegal, N=5 (mercury-2 is the faster/pricier alternate)
SEED = 4200
OUT = Path(__file__).resolve().parent.parent / "out"


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


def _seat_clients(cache: dict, journal: "Journal | None", *, live: bool,
                  inner_factory: "Callable[[], object] | None" = None) -> dict:
    """One client per LLM seat, each wrapped in the SHARED sidecar cache AND durability journal:
    distinct inner clients so parallel seats never race on usage, but the SAME cache dict + journal,
    so every seat's paid call is fsync'd to the one journal. live=False plugs a disconnected inner
    so a fully-cached re-run needs no network and no key; inner_factory overrides the inner (a test
    injects a mock or a crashing double)."""
    def default_inner():
        return (OpenRouterClient(MODEL, temperature=0.0, timeout=45, retries=1,
                                 provider=FAST_PROVIDER) if live else _Disconnected())
    make = inner_factory or default_inner
    return {seat: CachingClient(make(), cache, journal=journal) for seat in LLM_SEATS}


def _default_allied(campaign_mode: bool):
    """The scripted opponent the Axis staff faces when the Commonwealth is not itself a live staff:
    the offensive-capable Commonwealth on the campaign, the pure defender on Rommel's Arrival."""
    if campaign_mode:
        from game.campaign_policy import CampaignCommonwealthPolicy
        return CampaignCommonwealthPolicy()
    return ScriptedPolicy(attacker=Side.AXIS)


def _default_axis(campaign_mode: bool):
    """The scripted Axis opponent -- the twin of _default_allied for when the Commonwealth is the
    live staff and the Axis is scripted: on the campaign the multi-hop coastal haul (60.33/60.34)
    so the Panzerarmee actually fights east of Benghazi, on Rommel's Arrival the byte-locked base
    attacker. This is the canonical scripted Axis of the campaign; keeping the two _default_*
    helpers symmetric means either side can be the live staff against a faithful scripted foe."""
    if campaign_mode:
        from game.campaign_policy import CampaignAxisPolicy
        return CampaignAxisPolicy()
    return ScriptedPolicy(attacker=Side.AXIS)


def _staff(side: Side, cache: dict, journal: "Journal | None", *, live: bool) -> StaffPolicy:
    """One live command staff for `side`: a StaffPolicy whose seats share the durable cache/journal
    (keyed by sha256(model+prompt), so the two staffs never collide) -- the CW mirror is a second
    of these on Side.ALLIED."""
    return StaffPolicy(MockClient(_mock_staff), side=side,
                       seat_clients=_seat_clients(cache, journal, live=live), max_workers=len(LLM_SEATS))


def _play(axis, allied, *, campaign_mode: bool = False, max_turns: "int | None" = None) -> object:
    scenario = campaign(seed=SEED, max_turns=max_turns) if campaign_mode else rommels_arrival(seed=SEED)
    return run(scenario, axis=axis, allied=allied)


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


def _mock(*, campaign_mode: bool = False, max_turns: "int | None" = None,
          both_staffs: bool = False) -> int:
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    allied = (StaffPolicy(MockClient(_mock_staff), side=Side.ALLIED) if both_staffs
              else _default_allied(campaign_mode))
    _report(_play(axis, allied, campaign_mode=campaign_mode, max_turns=max_turns), "MOCK")
    return 0


def _run(*, live: bool, campaign_mode: bool = False, max_turns: "int | None" = None,
         fresh: bool = False, both_staffs: bool = False) -> int:
    if live:
        _load_key()
    OUT.mkdir(exist_ok=True)
    prefix = "staff_2sided" if both_staffs else ("staff_campaign" if campaign_mode else "staff_smoke")
    log_path = OUT / f"{prefix}.log.json"
    cache_path = OUT / f"{prefix}.cache.json"
    journal_path = Path(str(cache_path) + ".jsonl")
    # Durability + resume-by-default: load_cache recovers the compacted cache PLUS any journal a
    # prior kill left mid-run (folded on top, a torn final line tolerated), so a crashed live run
    # re-simulates with every finished turn replaying FREE -- only calls past the crash point reach
    # the model. --fresh first wipes both files for a deliberately clean run.
    if fresh:
        cache_path.unlink(missing_ok=True)
        journal_path.unlink(missing_ok=True)
    cache = load_cache(cache_path)
    journal = Journal(str(journal_path)) if live else None
    axis = _staff(Side.AXIS, cache, journal, live=live)
    allied = _staff(Side.ALLIED, cache, journal, live=live) if both_staffs else _default_allied(campaign_mode)
    result = _play(axis, allied, campaign_mode=campaign_mode, max_turns=max_turns)
    _report(result, "LIVE" if live else "RECACHE")
    for name, pol in ([("axis", axis), ("cw", allied)] if both_staffs else [("axis", axis)]):
        u = pol.usage()
        print(f"  usage[{name}]: model={MODEL} calls={u.get('calls', 0)} "
              f"prompt_tok={u.get('prompt_tokens', 0)} completion_tok={u.get('completion_tokens', 0)} "
              f"failures={u.get('failures', 0)} cache_hits={u.get('cache_hits', 0)} "
              f"cache_misses={u.get('cache_misses', 0)}")
    log_path.write_text(log_to_json(result.events))
    if journal is not None:
        journal.close()
    compact(cache_path, cache)                          # clean finish: fold the journal in, drop it
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
    ap.add_argument("--fresh", action="store_true",
                    help="wipe any prior cache/journal and start a clean live run (default: resume)")
    ap.add_argument("--both-staffs", action="store_true",
                    help="run BOTH sides as live command staffs -- the CW staff mirror, not a scripted CW")
    args = ap.parse_args()
    if args.fresh and not args.live:
        ap.error("--fresh only applies to --live")
    if args.live:
        return _run(live=True, campaign_mode=args.campaign, max_turns=args.turns, fresh=args.fresh,
                    both_staffs=args.both_staffs)
    if args.recache:
        return _run(live=False, campaign_mode=args.campaign, max_turns=args.turns,
                    both_staffs=args.both_staffs)
    return _mock(campaign_mode=args.campaign, max_turns=args.turns, both_staffs=args.both_staffs)


if __name__ == "__main__":
    raise SystemExit(main())
