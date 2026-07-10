"""SIGKILL crash-test child (invoked as a subprocess; NOT a pytest module).

Makes K MockClient misses through a JOURNAL-BACKED CachingClient -- each paid completion is
fsync'd to disk as one journal line BEFORE it returns -- then hard-kills itself with
os.kill(getpid, SIGKILL) and NO clean shutdown (no compact, no flush-on-exit). The parent
proves a fresh process recovers every fsync'd call from the journal alone.

    python3 tests/crash_durability.py <cache_path> <K>
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.llm import CachingClient, Journal, MockClient   # noqa: E402


def main() -> None:
    cache_path, k = sys.argv[1], int(sys.argv[2])
    journal = Journal(str(cache_path) + ".jsonl")
    # each distinct prompt is a fresh MISS -> a real (paid) completion -> one fsync'd line.
    client = CachingClient(MockClient(lambda p: f"reply-{p}"), {}, journal=journal)
    for i in range(k):
        client.complete(f"prompt-{i}")
    # NO compact(), NO journal.close(): simulate the RAM stick SIGKILLing the box mid-run.
    os.kill(os.getpid(), signal.SIGKILL)


if __name__ == "__main__":
    main()
