"""Durability of the live-staff runner (the $95 lesson): a SIGKILL mid-run must lose at most the
one call in flight, and a resume must replay every finished turn FREE with the model disconnected.

This exercises the ACTUAL scripts/run_staff._seat_clients wiring -- proving it threads the shared
game.llm Journal through every seat -- with an injected inner client, so no network or key is
touched. The Journal/load_cache/compact primitives themselves are covered by test_llm_durability.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.llm import Journal, compact, load_cache        # noqa: E402
from game.staff_policy import LLM_SEATS                   # noqa: E402
from scripts.run_staff import MODEL, _seat_clients        # noqa: E402


class _Answerer:
    """A mock inner that records every paid call so the test can count model hits. Its `model`
    matches the live MODEL so the sha256(model + prompt) keys line up across a resume."""

    model = MODEL

    def __init__(self, paid: list):
        self._paid = paid

    def complete(self, prompt: str) -> str:
        self._paid.append(prompt)
        return f"ans:{prompt}"


class _Boom:
    """A disconnected inner: any call is a cache MISS that must never happen on a correct resume."""

    model = MODEL

    def complete(self, prompt: str) -> str:
        raise AssertionError(f"model called for {prompt!r} -- a resumed turn must hit the journal")


def test_a_crash_mid_run_loses_nothing_and_resume_is_free(tmp_path):
    cache_path = tmp_path / "staff.cache.json"
    journal_path = Path(str(cache_path) + ".jsonl")
    prompts = [f"deliberate-{seat}" for seat in LLM_SEATS]        # one distinct prompt per seat

    # --- pass 1: each seat pays for one completion, then the box is SIGKILLed: the journal's
    #     fsync'd lines survive, but the clean compact never runs (crash_durability.py's mode). ---
    cache = load_cache(cache_path)                               # empty -- a fresh start
    journal = Journal(str(journal_path))
    paid: list = []
    seats = _seat_clients(cache, journal, live=False, inner_factory=lambda: _Answerer(paid))
    for seat, prompt in zip(seats, prompts):
        seats[seat].complete(prompt)
    journal.close()                                             # NO compact: simulate the kill
    assert len(paid) == len(prompts)                            # every call was paid exactly once
    assert journal_path.exists()                                # the durable sidecar is on disk

    # --- resume: load_cache folds the journal back; every prior turn replays with the model OFF. ---
    resumed = load_cache(cache_path)
    assert len(resumed) == len(prompts)                         # nothing was lost to the crash
    seats2 = _seat_clients(resumed, None, live=False, inner_factory=_Boom)
    for seat, prompt in zip(seats2, prompts):
        assert seats2[seat].complete(prompt) == f"ans:{prompt}"  # a cache hit: _Boom never runs

    # --- a clean finish compacts the journal into the single file and drops it. ---
    compact(cache_path, resumed)
    assert not journal_path.exists()
    assert len(load_cache(cache_path)) == len(prompts)


def test_the_shared_journal_collects_every_seat(tmp_path):
    # The durability guarantee only holds if ALL seats fsync to the ONE journal -- a seat wired to
    # its own (or no) journal would silently lose its paid calls on a crash. One line per seat.
    cache_path = tmp_path / "staff.cache.json"
    journal = Journal(str(cache_path) + ".jsonl")
    seats = _seat_clients({}, journal, live=False, inner_factory=lambda: _Answerer([]))
    for seat in seats:
        seats[seat].complete(f"only-{seat}")
    journal.close()
    assert len(load_cache(cache_path)) == len(LLM_SEATS)         # every seat's call is recoverable
