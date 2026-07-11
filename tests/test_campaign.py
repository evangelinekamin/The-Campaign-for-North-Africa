"""C1-7: the campaign shell. The full A-E theatre runs the GT1..111 clock end to end
under scripted play and terminates through the rule-64.7 campaign victory, exercising
the eastern geography, the September-1940 calendar, and the pluggable victory seam that
C1-3/C1-4/C1-6 put in place -- all without the C2 army or C3 economy.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords
from game.calendar import CAMPAIGN_SEASON_OFFSET, FINAL_GT
from game.campaign_victory import CampaignVictory
from game.engine import determinism_signature, run
from game.events import Side
from game.policy import ScriptedPolicy
from game.scenario import campaign


def test_builds_full_theatre():
    st = campaign(seed=1941)
    assert st.map_sections == frozenset("ABCDE")
    assert st.season_offset == CAMPAIGN_SEASON_OFFSET     # September 1940 = fall
    assert st.max_turns == FINAL_GT                        # GT111
    assert isinstance(st.victory, CampaignVictory)
    # Eastern geography is present and occupiable: Mersa Matruh (D) and Alexandria (E).
    for lbl in ("D3714", "E3613"):
        assert coords.to_axial(coords.parse(lbl)) in st.terrain.terrain


def test_max_turns_truncates():
    assert campaign(max_turns=8).max_turns == 8


def test_campaign_is_deterministic():
    # Same seed -> byte-identical event stream (a short slice keeps the test fast).
    a = run(campaign(seed=7, max_turns=8), axis=ScriptedPolicy(), allied=ScriptedPolicy())
    b = run(campaign(seed=7, max_turns=8), axis=ScriptedPolicy(), allied=ScriptedPolicy())
    assert determinism_signature(a.events) == determinism_signature(b.events)


def test_runs_full_span_to_campaign_victory():
    # The headline: the engine runs the entire GT1..111 campaign and terminates through
    # rule 64.7 (a graded 64.76 result or an auto-win/annihilation), not the built-in
    # Race-for-Tobruk logic.
    res = run(campaign(seed=1941), axis=ScriptedPolicy(), allied=ScriptedPolicy())
    assert res.final.turn == FINAL_GT                      # reached December 1942
    assert res.winner in (Side.AXIS, Side.ALLIED, None)    # None = a 64.76 draw
    assert "64.7" in res.reason
