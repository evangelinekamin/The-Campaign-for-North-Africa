"""LLM client seam for the agent layer (brief §4.5).

An `LLMClient` just turns a prompt into text. Tests use `MockClient` (deterministic,
free, and able to return adversarial/malformed output to exercise the engine's
order-rejection boundary). `OpenRouterClient` is the real provider, used only for
the live smoke test; its API key comes from the OPENROUTER_API_KEY environment
variable and is NEVER logged, persisted, or written to disk.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable, Protocol


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class MockClient:
    """Deterministic stand-in: `responder` is either a fixed string or a
    prompt->string function (so a test can vary the reply by phase/content)."""

    def __init__(self, responder: "str | Callable[[str], str]"):
        self._responder = responder

    def complete(self, prompt: str) -> str:
        r = self._responder
        return r(prompt) if callable(r) else r


class OpenRouterClient:
    """Chat-completions against OpenRouter. Key read from OPENROUTER_API_KEY (never
    logged/committed). Kept dependency-free (urllib) so no install is needed."""

    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str, *, temperature: float = 0.3, timeout: float = 60.0,
                 retries: int = 2):
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.retries = retries
        self.calls = 0                 # usage accumulators (for benchmarking cost)
        self.failures = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def complete(self, prompt: str) -> str:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        body = json.dumps({
            "model": self.model,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
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
