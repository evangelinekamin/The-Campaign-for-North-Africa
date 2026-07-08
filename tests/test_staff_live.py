"""Steps 6-7: swap the deterministic stubs for LLM role-agents (persona cards + per-seat
clients + parallel specialists) and the determinism/replay backbone (recorded-log replay
+ a re-simulation response cache). Every test here is ZERO-token: the "live" swap is
proven client-only by holding the MockClient path byte-identical, and the caching /
replay guarantees are exercised with mock inners, so no API is ever touched.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import _mock_staff                           # noqa: E402

from game.engine import run                                         # noqa: E402
from game.events import Side, log_to_json                           # noqa: E402
from game.llm import CachingClient, MockClient                      # noqa: E402
from game.policy import ScriptedPolicy                              # noqa: E402
from game.scenario import rommels_arrival                          # noqa: E402
from game.staff_policy import (                                     # noqa: E402
    CHIEF, LLM_SEATS, PERSONAS, PersonaCard, StaffPolicy, intent_preamble,
    persona_preamble)
from game.staff import Lane                                          # noqa: E402


def _staff_game(axis: StaffPolicy):
    return run(rommels_arrival(seed=4200), axis=axis,
               allied=ScriptedPolicy(attacker=Side.AXIS))


# --- Step 6: persona cards ----------------------------------------------------

def test_persona_cards_cover_every_seat_and_are_frozen():
    """The three LLM seats (Chief + the two GOCs) and the four silent seats (QM, Intel,
    and the two resource seats Naval + Air) all carry a static persona; the card is
    immutable (a frozen dataclass)."""
    for seat in LLM_SEATS:
        assert seat in PERSONAS
    assert len(PERSONAS) == 7        # Chief, MOBILE, INFANTRY, QM, Intel, Naval, Air
    card = PERSONAS[LLM_SEATS[1]]
    assert isinstance(card, PersonaCard)
    with pytest.raises(dataclasses.FrozenInstanceError):
        card.doctrine = "mutated"                    # type: ignore[misc]


def test_persona_preamble_carries_the_doctrine_and_bias():
    for seat, card in PERSONAS.items():
        pre = persona_preamble(seat)
        assert card.name in pre and card.doctrine in pre and card.bias in pre
    assert persona_preamble("no-such-seat") == ""    # unknown seat -> no preamble


def test_persona_is_injected_into_each_seat_prompt():
    """Every prompt a seat sends is prefixed with its own persona card (and never
    another seat's), captured off a recording client."""
    seen: dict[str, list[str]] = {}

    def recorder(seat):
        def responder(prompt):
            seen.setdefault(seat, []).append(prompt)
            return _mock_staff(prompt)
        return MockClient(responder)

    seat_clients = {seat: recorder(seat) for seat in LLM_SEATS}
    _staff_game(StaffPolicy(MockClient(_mock_staff), side=Side.AXIS, seat_clients=seat_clients))
    for seat in LLM_SEATS:
        assert seen.get(seat), f"seat {seat} never called"
        doctrine = PERSONAS[seat].doctrine
        assert all(doctrine in p for p in seen[seat])          # its own card, every call
        others = [PERSONAS[s].doctrine for s in LLM_SEATS if s != seat]
        assert all(all(o not in p for o in others) for p in seen[seat])   # no cross-contamination


# --- Step 3: the top-down intent preamble (fix the cosmetic hierarchy) ---------

def test_intent_preamble_renders_only_the_whitelisted_fields():
    """The block carries ONLY the whitelisted intent fields + the standing priorities and
    the storm directive -- never free prose -- and is empty when no intent is framed."""
    assert intent_preamble({}) == ""
    intent = {"objective": "Seize Tobruk", "scheme": "armour leads the coastal push",
              "supply": "fuel the panzers first"}
    block = intent_preamble(intent)
    assert block.startswith("ORDERS FROM THE CHIEF OF STAFF")
    assert "Seize Tobruk" in block and "armour leads the coastal push" in block
    assert "STORM DIRECTIVE" in block                       # the schwerpunkt order rides down
    assert "lessons" not in block                           # non-whitelisted keys never leak


def test_chief_intent_reaches_the_gocs_but_not_the_chiefs_own_prompt():
    """The Chief's scheme is prepended to every SUBORDINATE seat's prompt (the GOCs now plan
    TO the intent) but NEVER to the Chief's own authoring prompt -- a real chain of command."""
    seen: dict[str, list[str]] = {}

    def recorder(seat):
        def responder(prompt):
            seen.setdefault(seat, []).append(prompt)
            return _mock_staff(prompt)
        return MockClient(responder)

    seat_clients = {seat: recorder(seat) for seat in LLM_SEATS}
    _staff_game(StaffPolicy(MockClient(_mock_staff), side=Side.AXIS, seat_clients=seat_clients))
    scheme = "combined-arms coastal push, armour leading"           # the canned mock intent scheme
    for goc in (Lane.MOBILE.value, Lane.INFANTRY.value):
        assert seen.get(goc), f"seat {goc} never called"
        assert all("ORDERS FROM THE CHIEF OF STAFF" in p for p in seen[goc])
        assert any(scheme in p for p in seen[goc])                  # the Chief's scheme reached the GOC
    assert seen.get(CHIEF)
    assert all("ORDERS FROM THE CHIEF OF STAFF" not in p for p in seen[CHIEF])  # the Chief authors it
    assert all(scheme not in p for p in seen[CHIEF])                # its own intent is never fed back


# --- Step 6: the swap is client-only (mock path stays byte-deterministic) ------

def test_mock_path_is_byte_deterministic_after_the_swap():
    a = log_to_json(_staff_game(StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)).events)
    b = log_to_json(_staff_game(StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)).events)
    assert a == b


def test_parallel_specialists_match_sequential_byte_for_byte():
    """Parallelising the specialist calls is an I/O win ONLY: results are re-collected in
    fixed lane order before the fold, so max_workers changes nothing in the log."""
    seq = log_to_json(_staff_game(
        StaffPolicy(MockClient(_mock_staff), side=Side.AXIS, max_workers=1)).events)
    par = log_to_json(_staff_game(
        StaffPolicy(MockClient(_mock_staff), side=Side.AXIS, max_workers=4)).events)
    assert seq == par


# --- Step 7: recorded-log replay is pure (client disconnected) -----------------

def test_recorded_replay_reproduces_final_state_without_a_client():
    """Recorded-log replay = fold(initial, events): the orders and STAFF_* are baked into
    the seeded log, so replay needs NO client and reproduces the exact final state."""
    from game.apply import fold
    result = _staff_game(StaffPolicy(MockClient(_mock_staff), side=Side.AXIS))
    assert fold(result.initial, result.events) == result.final


# --- Step 7: the re-simulation response cache ----------------------------------

class _CountingClient:
    """A mock inner that counts calls and can be told to hard-fail if called at all."""

    def __init__(self, responder, *, forbid: bool = False):
        self._responder = responder
        self.forbid = forbid
        self.calls = 0

    def complete(self, prompt: str) -> str:
        if self.forbid:
            raise AssertionError("inner client called on a cache hit")
        self.calls += 1
        return self._responder(prompt)


def test_caching_client_hit_skips_the_inner_and_keys_on_model_plus_prompt():
    import hashlib
    inner = _CountingClient(lambda p: "reply")
    cache: dict = {}
    client = CachingClient(inner, cache)
    assert client.complete("prompt-A") == "reply"
    assert client.complete("prompt-A") == "reply"          # served from cache
    assert inner.calls == 1                                 # inner hit exactly once
    assert client.hits == 1 and client.misses == 1
    key = hashlib.sha256(f"{client.model}\nprompt-A".encode()).hexdigest()
    assert key in cache and cache[key] == "reply"


def test_resimulation_reproduces_the_log_with_the_model_disconnected():
    """Populate the sidecar cache on a first run, then re-run against the SAME cache with a
    FORBIDDEN inner: the cached replies reproduce byte-identical STAFF_* + orders and the
    model is never touched (the re-simulation guarantee, model disconnected)."""
    cache: dict = {}
    populate = {seat: CachingClient(_CountingClient(_mock_staff), cache) for seat in LLM_SEATS}
    first = log_to_json(_staff_game(
        StaffPolicy(MockClient(_mock_staff), side=Side.AXIS,
                    seat_clients=populate, max_workers=1)).events)
    assert cache                                            # the run cached its prompts

    forbidden = {seat: CachingClient(_CountingClient(_mock_staff, forbid=True), cache)
                 for seat in LLM_SEATS}
    axis2 = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS,
                        seat_clients=forbidden, max_workers=1)
    second = log_to_json(_staff_game(axis2).events)
    assert second == first                                  # cache reproduced the exact log
    assert all(c.misses == 0 for c in forbidden.values())  # every prompt was a hit; model off


def test_usage_sums_across_seat_clients():
    class _U:
        def complete(self, p): return "{}"
        def usage(self): return {"calls": 2, "prompt_tokens": 5}

    seats = {seat: _U() for seat in LLM_SEATS}
    pol = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS, seat_clients=seats)
    u = pol.usage()
    assert u["calls"] == 2 * len(LLM_SEATS)
    assert u["prompt_tokens"] == 5 * len(LLM_SEATS)
