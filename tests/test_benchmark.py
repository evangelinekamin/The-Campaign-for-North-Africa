"""Benchmark scoring attribution (scripts.benchmark.game_metrics / _score).

The order-rejection headline conflates two very different actors: the AXIS/Front
seat (the LLM's own movement/assault orders) and the AXIS/Logistics seat (the
SCRIPTED supply/truck reflexes the model never authored). Charging a model for the
scripted logistics rejects triples its apparent indiscipline. game_metrics must
split ORDER_REJECTED by actor and drive the reject-discipline score off the LLM's
own (Front) number only. Zero-token: proven on the deterministic MockClient staff
path, which fields BOTH actors' rejections.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import _mock_staff, game_metrics                # noqa: E402

from game.engine import run                                            # noqa: E402
from game.events import EventKind, Side                                # noqa: E402
from game.llm import MockClient                                        # noqa: E402
from game.policy import ScriptedPolicy                                 # noqa: E402
from game.scenario import rommels_arrival                             # noqa: E402
from game.staff_policy import StaffPolicy                              # noqa: E402


def _staff_result():
    """A full mock staff game -- fields both AXIS/Front and AXIS/Logistics rejects."""
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    return run(rommels_arrival(seed=4200), axis=axis,
               allied=ScriptedPolicy(attacker=Side.AXIS))


def _by_actor(result, actor: str) -> int:
    return sum(1 for e in result.events
               if e.kind == EventKind.ORDER_REJECTED and e.actor == actor)


def test_game_metrics_splits_rejects_by_actor():
    result = _staff_result()
    front = _by_actor(result, "AXIS/Front")
    logistics = _by_actor(result, "AXIS/Logistics")
    assert logistics > 0, "the staff game must field scripted-logistics rejects to test the split"

    g = game_metrics(result)
    assert g["llm_rejects"] == front
    assert g["logistics_rejects"] == logistics
    # the scoring 'rejections' field is the LLM-only number, NOT the conflated total.
    assert g["rejections"] == front
    assert g["rejections"] != front + logistics


def test_score_reject_discipline_ignores_logistics():
    result = _staff_result()
    g = game_metrics(result)
    # clean/reject_rate are computed off Front orders only: the denominator excludes
    # the scripted logistics rejects, so the discipline penalty tracks the LLM alone.
    axis_orders = g["moves"] + g["axis_assaults"] + g["llm_rejects"]
    expected_rate = 100 * g["llm_rejects"] / max(1, axis_orders)
    assert abs(g["reject_rate_game"] - round(expected_rate, 1)) < 0.05
