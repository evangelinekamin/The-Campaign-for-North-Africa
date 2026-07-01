"""Tests for the LLM agent layer (game.observation / game.llm / game.llm_policy).

The load-bearing property (brief §3.3) is engine-boundary validation, NOT
constrained decoding: an agent may propose anything, and the engine must accept
legal orders, reject illegal ones without mutating state, and never crash on
garbage. We prove that with a deterministic MockClient — no API calls, no spend.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import fold
from game.engine import determinism_signature, run
from game.events import EventKind, Side
from game.llm import MockClient
from game.llm_policy import (LLMPolicy, _extract_json, build_movement_prompt,
                             parse_attacks, parse_moves)
from game.observation import observe
from game.policy import MoveOrder
from game.scenario import coastal_corridor

PASSIVE = '{"reasoning":"hold","moves":[],"attacks":[]}'


def _run(axis_reply):
    """Run the corridor with an LLM axis (fixed reply) vs a passive LLM allied."""
    axis = LLMPolicy(Side.AXIS, MockClient(axis_reply))
    allied = LLMPolicy(Side.ALLIED, MockClient(PASSIVE))
    return run(coastal_corridor(), axis=axis, allied=allied)


# --- observation: limited intelligence --------------------------------------

def test_observation_hides_enemy_details():
    obs = observe(coastal_corridor(), Side.AXIS)
    assert obs["your_units"] and "strength" in obs["your_units"][0]   # own = full
    for sighting in obs["enemy_sightings"]:                           # enemy = presence only
        assert set(sighting) == {"hex", "dist_to_objective", "stacking_points", "unit_count"}
        assert "strength" not in sighting and "oca" not in sighting


# --- tolerant parsing -------------------------------------------------------

def test_parse_moves_and_attacks_from_clean_json():
    moves = parse_moves('{"moves":[{"unit":"DAK-5le","to":[1,0]}]}')
    assert moves == [MoveOrder("DAK-5le", (1, 0))]
    atks = parse_attacks('{"attacks":[{"attackers":["A","B"],"target":[7,0]}]}')
    assert atks[0].attacker_ids == ("A", "B") and atks[0].target == (7, 0)


def test_parse_tolerates_prose_and_fences():
    reply = 'Sure!\n```json\n{"moves":[{"unit":"DAK-5le","to":[1,0]}]}\n```\nGood luck.'
    assert parse_moves(reply)[0].unit_id == "DAK-5le"


def test_parse_drops_malformed_orders():
    assert parse_moves("no json here at all") == []
    assert parse_moves('{"moves":[{"unit":"X"},{"to":[1,0]},{"unit":"Y","to":[1]}]}') == []
    assert _extract_json("{bad json,,}") == {}


# --- engine-boundary validation (the load-bearing property) ------------------

def test_valid_llm_move_is_accepted():
    result = _run('{"moves":[{"unit":"DAK-5le","to":[1,0]}]}')
    assert result.final.unit("DAK-5le").hex != (0, 0)               # the move happened
    assert fold(result.initial, result.events) == result.final     # replay-equivalent


def test_illegal_llm_move_is_rejected_without_mutating_state():
    result = _run('{"moves":[{"unit":"DAK-5le","to":[99,99]}]}')    # off-map teleport
    rejects = [e for e in result.events if e.kind == EventKind.ORDER_REJECTED]
    assert rejects
    assert result.final.unit("DAK-5le").hex == (0, 0)              # never moved


def test_garbage_llm_output_never_crashes_and_is_deterministic():
    a = _run("the vibes are off today, no orders from me")
    b = _run("the vibes are off today, no orders from me")
    assert a.winner in (Side.AXIS, Side.ALLIED)
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert fold(a.initial, a.events) == a.final


def test_prompt_contains_observation_and_format():
    p = build_movement_prompt(observe(coastal_corridor(), Side.AXIS))
    assert "MOVEMENT phase" in p and "your_units" in p and '"moves"' in p
