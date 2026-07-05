"""One-decision-at-a-time driver so an interactive agent (e.g. a Fable subagent) can
PLAY the Axis through a whole game, without an API client.

It replays Rommel's Arrival from a fixed seed, feeding the Axis LLM calls from
numbered reply files (resp_0.txt, resp_1.txt, ...) in RESP_DIR. It stops at the
first call that has no reply file yet and prints `CALL <n>` followed by that exact
prompt. Write your JSON reply to RESP_DIR/resp_<n>.txt and run the script again;
because the run is deterministic (fixed seed + recorded replies) it replays to the
same point and advances one decision. When every call is answered and the game
ends it prints `GAME OVER` + the result line.

    RESP_DIR=/tmp/fable_play SEED=4200 python3 -m scripts.benchmark_step
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.engine import run                                     # noqa: E402
from game.events import EventKind, Side                         # noqa: E402
from game.llm_policy import LLMPolicy                           # noqa: E402
from game.policy import ScriptedPolicy                          # noqa: E402
from game.scenario import rommels_arrival                       # noqa: E402

RESP_DIR = Path(os.environ.get("RESP_DIR", "fable_play"))
SEED = int(os.environ.get("SEED", "4200"))
RESP_DIR.mkdir(parents=True, exist_ok=True)

_replies: list[str] = []
_i = 0
while (f := RESP_DIR / f"resp_{_i}.txt").exists():
    _replies.append(f.read_text())
    _i += 1


class _Stop(Exception):
    def __init__(self, idx: int, prompt: str):
        self.idx, self.prompt = idx, prompt


class _Replay:
    """Serves recorded Axis replies in order; raises at the first unanswered call."""

    def __init__(self):
        self.i = 0

    def complete(self, prompt: str) -> str:
        if self.i < len(_replies):
            r = _replies[self.i]
            self.i += 1
            return r
        raise _Stop(self.i, prompt)


def main() -> int:
    try:
        result = run(rommels_arrival(seed=SEED),
                     axis=LLMPolicy(Side.AXIS, _Replay()),
                     allied=ScriptedPolicy(attacker=Side.AXIS))
    except _Stop as s:
        print(f"CALL {s.idx}")
        print(s.prompt)
        return 0
    vp = [e for e in result.events if e.kind == EventKind.VICTORY_CHECKED][-1].payload
    print("GAME OVER")
    print(f"winner={result.winner.value} advance={vp['axis']}% "
          f"reach={vp.get('axis_reach')} reason={result.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
