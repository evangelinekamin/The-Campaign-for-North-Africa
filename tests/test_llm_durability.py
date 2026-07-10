"""Journal-backed durability of the sidecar cache (game.llm).

The $90 bug: the CachingClient held its completions in an in-memory dict that
scripts.leaderboard flushed exactly ONCE, at clean model exit. A SIGKILL (a failing RAM
stick) dropped the whole dict -- every paid LLM call had to be paid for again on resume.

These tests pin the JOURNAL-BACKED fix: every paid completion is a single durably-fsync'd
line on disk BEFORE it is returned, so a kill at any instant loses at most the one call in
flight. All tests are ZERO-token (MockClient); the mandatory SIGKILL crash-test lives in
tests/crash_durability.py and is invoked as a subprocess here.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.llm import CachingClient, Journal, _atomic_write, compact, load_cache  # noqa: E402


class _Counting:
    """Records how many real completions it served (a proxy for paid calls)."""

    def __init__(self):
        self.model = "mock/model"
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return f"reply-{prompt}"


# --- append-durability: one fsync'd line per paid call ------------------------

def test_a_cache_miss_appends_one_durable_journal_line(tmp_path):
    cache_path = tmp_path / "c.json"
    journal = Journal(str(cache_path) + ".jsonl")
    client = CachingClient(_Counting(), {}, journal=journal)

    client.complete("A")
    client.complete("B")
    journal.close()

    lines = [json.loads(x) for x in Path(str(cache_path) + ".jsonl").read_text().splitlines()]
    assert len(lines) == 2                                  # one line per paid completion
    assert {rec["v"] for rec in lines} == {"reply-A", "reply-B"}


def test_a_cache_hit_writes_no_journal_line(tmp_path):
    cache_path = tmp_path / "c.json"
    journal = Journal(str(cache_path) + ".jsonl")
    shared: dict = {}
    client = CachingClient(_Counting(), shared, journal=journal)

    client.complete("A")
    client.complete("A")                                    # served from cache -- no new spend
    journal.close()

    lines = Path(str(cache_path) + ".jsonl").read_text().splitlines()
    assert len(lines) == 1                                  # the hit added nothing


def test_journal_is_optional_and_absent_by_default(tmp_path):
    # a client with no journal behaves exactly as before (in-memory only, no file written).
    client = CachingClient(_Counting(), {})
    assert client.complete("A") == "reply-A"
    assert not list(tmp_path.iterdir())


# --- recovery: replay the journal on top of the compacted dict ----------------

def test_load_cache_replays_the_journal_over_the_compacted_dict(tmp_path):
    cache_path = tmp_path / "c.json"
    cache_path.write_text(json.dumps({"old": "compacted"}))
    Path(str(cache_path) + ".jsonl").write_text(
        json.dumps({"k": "fresh", "v": "journaled"}) + "\n")

    recovered = load_cache(cache_path)
    assert recovered == {"old": "compacted", "fresh": "journaled"}


def test_load_cache_of_a_plain_json_cache_with_no_journal_still_works(tmp_path):
    # the 9 already-completed models have a plain-JSON cache and NO journal -- must load intact.
    cache_path = tmp_path / "legacy.json"
    cache_path.write_text(json.dumps({"k1": "v1", "k2": "v2"}))
    assert load_cache(cache_path) == {"k1": "v1", "k2": "v2"}


def test_load_cache_of_a_missing_path_is_empty(tmp_path):
    assert load_cache(tmp_path / "nope.json") == {}


def test_load_cache_tolerates_a_truncated_final_line(tmp_path):
    # a SIGKILL mid-append leaves a good line then a half-written one. load must return the good
    # entry and NOT raise on the partial tail.
    cache_path = tmp_path / "c.json"
    good = json.dumps({"k": "good", "v": "kept"}) + "\n"
    half = '{"k": "partial", "v": "trunc'          # no closing brace/newline -- torn write
    Path(str(cache_path) + ".jsonl").write_text(good + half)

    recovered = load_cache(cache_path)                      # must not raise
    assert recovered == {"good": "kept"}                    # the good line survived; tail dropped


# --- compact: fold the journal into the dict, then drop it --------------------

def test_compact_rewrites_the_dict_and_clears_the_journal(tmp_path):
    cache_path = tmp_path / "c.json"
    journal_path = Path(str(cache_path) + ".jsonl")
    journal_path.write_text(json.dumps({"k": "x", "v": "y"}) + "\n")
    cache = {"a": "1", "x": "y"}

    compact(cache_path, cache)

    assert json.loads(cache_path.read_text()) == cache      # P holds the full dict
    assert not journal_path.exists()                        # the folded journal is gone


def test_compact_is_a_noop_safe_when_no_journal_exists(tmp_path):
    cache_path = tmp_path / "c.json"
    compact(cache_path, {"a": "1"})                         # no journal -- must not raise
    assert json.loads(cache_path.read_text()) == {"a": "1"}


# --- _atomic_write: never leaves a partial file -------------------------------

def test_atomic_write_leaves_no_tmp_and_writes_whole(tmp_path):
    target = tmp_path / "card.json"
    _atomic_write(target, '{"cards": []}')
    assert target.read_text() == '{"cards": []}'
    assert list(tmp_path.iterdir()) == [target]             # the .tmp was renamed away, not left


def test_atomic_write_replaces_existing_content_wholesale(tmp_path):
    target = tmp_path / "c.json"
    target.write_text("OLD")
    _atomic_write(target, "NEW")
    assert target.read_text() == "NEW"


def test_atomic_write_never_exposes_a_partial_file(tmp_path, monkeypatch):
    # simulate a crash BETWEEN writing the tmp and the atomic replace: the target keeps its old,
    # whole content -- a reader never sees a half-written file.
    target = tmp_path / "c.json"
    target.write_text("WHOLE-OLD")
    import game.llm as llm

    def boom(_src, _dst):
        raise KeyboardInterrupt("killed before replace")

    monkeypatch.setattr(llm.os, "replace", boom)
    try:
        _atomic_write(target, "PARTIAL-NEW")
    except KeyboardInterrupt:
        pass
    assert target.read_text() == "WHOLE-OLD"                # the reader still sees the old whole file


# --- the mandatory SIGKILL crash-test (real fresh subprocess, no clean exit) --

def test_sigkill_mid_run_recovers_every_paid_call(tmp_path):
    """Spend K>=8 completions through a journaled client, SIGKILL the process with NO compact,
    then recover in a FRESH process. At most the single in-flight call may be lost."""
    K = 8
    cache_path = tmp_path / "crash.json"
    crasher = Path(__file__).resolve().parent / "crash_durability.py"
    subprocess.run([sys.executable, str(crasher), str(cache_path), str(K)])  # SIGKILLs itself

    recovered = load_cache(cache_path)
    assert len(recovered) >= K - 1                          # lost at most the in-flight call
    assert len(recovered) <= K
    for v in recovered.values():
        assert v.startswith("reply-")                       # every recovered entry is a real reply
