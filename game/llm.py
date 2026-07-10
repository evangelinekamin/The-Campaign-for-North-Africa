"""LLM client seam for the agent layer (brief §4.5).

An `LLMClient` just turns a prompt into text. Tests use `MockClient` (deterministic,
free, and able to return adversarial/malformed output to exercise the engine's
order-rejection boundary). `OpenRouterClient` is the real provider, used only for
the live smoke test; its API key comes from the OPENROUTER_API_KEY environment
variable and is NEVER logged, persisted, or written to disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Protocol


def _atomic_write(path: "str | Path", text: str) -> None:
    """Write `text` to `path` so a reader NEVER sees a partial file: write a sibling `.tmp`,
    then os.replace it into place (atomic rename on POSIX). A SIGKILL between the two steps
    leaves the previous whole file intact -- the crash that corrupted card_z-ai_glm-5.2.json
    by writing straight into it cannot recur."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Journal:
    """Append-only durability sidecar for one cache file, SHARED by every CachingClient that
    fills it (all seats, all concurrent seeds). One JSON line per paid completion, appended
    under a shared lock and fsync'd before it is acknowledged, so a SIGKILL at any instant
    loses at most the single in-flight line. The worker threads share this object; the lock
    serializes their appends onto the one file handle."""

    def __init__(self, path: "str | Path"):
        self.path = str(path)
        self._lock = threading.Lock()
        self._fh = None

    def append(self, key: str, value: str) -> None:
        line = json.dumps({"k": key, "v": value}) + "\n"
        with self._lock:
            if self._fh is None:
                self._fh = open(self.path, "a", encoding="utf-8")
            self._fh.write(line)
            self._fh.flush()
            os.fsync(self._fh.fileno())            # the paid call is now durably on disk

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None


def load_cache(path: "str | Path") -> dict:
    """Recover a journaled cache: the compacted JSON dict at `path` (if any), then every durable
    line of `path`+'.jsonl' folded on top. A kill mid-append can leave a final truncated line;
    it is tolerated (skipped), never raised. A plain-JSON cache with no journal (the already-
    completed models) loads intact."""
    path = Path(path)
    cache: dict = {}
    if path.exists():
        try:
            cache.update(json.loads(path.read_text()))
        except ValueError:                         # a corrupt compacted file -- start from empty
            cache = {}
    journal = Path(str(path) + ".jsonl")
    if journal.exists():
        for line in journal.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue                           # a torn final append -- tolerate and drop it
            cache[rec["k"]] = rec["v"]
    return cache


def compact(path: "str | Path", cache: dict) -> None:
    """Fold the journal into the compacted dict on CLEAN completion: atomically rewrite `path`
    from the full cache, then drop the now-redundant journal. After this the journal is empty
    and every paid call lives in the single compact file."""
    _atomic_write(path, json.dumps(cache))
    journal = Path(str(path) + ".jsonl")
    if journal.exists():
        journal.unlink()


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...
    def chat(self, messages: list) -> str: ...


class MockClient:
    """Deterministic stand-in: `responder` is either a fixed string or a
    prompt->string function (so a test can vary the reply by phase/content)."""

    def __init__(self, responder: "str | Callable[[str], str]"):
        self._responder = responder

    def complete(self, prompt: str) -> str:
        r = self._responder
        return r(prompt) if callable(r) else r

    def chat(self, messages: list) -> str:
        """Respond to the latest user turn (stateful mode sends a message list)."""
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return self.complete(last)


class CachingClient:
    """Wraps any LLMClient with a sha256(model + prompt) -> text cache so a
    re-simulation reproduces byte-identical replies -- and therefore byte-identical
    STAFF_* payloads and orders -- with the model DISCONNECTED for every cached prompt.

    The cache is a plain dict the caller owns and persists as a SIDECAR beside the
    event log (never inside the immutable core). A cache hit never touches the inner
    client, so a fully-cached re-run needs no network and no key. The key is
    sha256(model + prompt); it never contains the API key, and the cached text is the
    model's reply, never a secret.

    Durability: given a shared `journal`, every MISS (a real, paid completion) is appended
    as one fsync'd line BEFORE it is returned. A SIGKILL then loses at most the one call in
    flight -- every earlier paid reply replays FREE from the journal via load_cache(). Without
    a journal the client is purely in-memory (the mock / test path)."""

    def __init__(self, inner: LLMClient, cache: "dict[str, str] | None" = None,
                 journal: "Journal | None" = None):
        self._inner = inner
        self.cache = cache if cache is not None else {}
        self._journal = journal
        self.hits = 0
        self.misses = 0

    @property
    def model(self) -> str:
        return getattr(self._inner, "model", "")

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(f"{self.model}\n{prompt}".encode()).hexdigest()

    def complete(self, prompt: str) -> str:
        key = self._key(prompt)
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        text = self._inner.complete(prompt)
        if self._journal is not None:
            self._journal.append(key, text)        # durable on disk BEFORE we return the paid reply
        self.cache[key] = text
        return text

    def chat(self, messages: list) -> str:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return self.complete(last)

    def usage(self) -> dict:
        u = self._inner.usage() if hasattr(self._inner, "usage") else {}
        return {**u, "cache_hits": self.hits, "cache_misses": self.misses}


class OpenRouterClient:
    """Chat-completions against OpenRouter. Key read from OPENROUTER_API_KEY (never
    logged/committed). Kept dependency-free (urllib) so no install is needed."""

    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str, *, temperature: float = 0.3, timeout: float = 60.0,
                 retries: int = 2, reasoning_effort: str | None = None,
                 provider: dict | None = None):
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.retries = retries
        self.reasoning_effort = reasoning_effort   # "low"/"medium"/"high" or None (provider default)
        # OpenRouter provider routing (e.g. {"sort": "throughput"} to always pick the
        # fastest live endpoint -- many DeepSeek providers run 15-20 tok/s and stall runs).
        self.provider = provider
        self.calls = 0                 # usage accumulators (for benchmarking cost)
        self.failures = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def complete(self, prompt: str) -> str:
        return self.chat([{"role": "user", "content": prompt}])

    def chat(self, messages: list) -> str:
        """Multi-turn completion (the stateful mode sends the running conversation).
        Usage accumulates across calls regardless of turn count."""
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": messages,
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        if self.provider:
            payload["provider"] = self.provider
        body = json.dumps(payload).encode()
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(
                    self.URL, data=body, method="POST",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode())
                usage = data.get("usage") or {}
                self.calls += 1
                self.prompt_tokens += usage.get("prompt_tokens", 0)
                self.completion_tokens += usage.get("completion_tokens", 0)
                return data["choices"][0]["message"]["content"]
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
                if attempt < self.retries:
                    time.sleep(1.0 + attempt)          # brief backoff, then retry
                    continue
                self.failures += 1                     # give up: caller gets no orders this phase
                return ""

    def usage(self) -> dict:
        return {"calls": self.calls, "failures": self.failures,
                "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}
