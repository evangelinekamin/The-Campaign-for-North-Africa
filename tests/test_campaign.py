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


def test_campaign_fields_the_september_1940_army():
    # C2: the campaign opens with the real Italian 10th Army (the oob_italian extraction
    # plus the rule-60.31 gap-fill) -- not the Desert-Fox placeholder. The partial setup
    # save omitted two infantry divisions and nearly all the armour; the gap-fill restores
    # them, so the reconstructed divisions and the Libyan Tank Command are on the board.
    ax = [u for u in campaign(seed=1941).units if u.side == Side.AXIS]
    assert len(ax) >= 90                                   # ~95: 61 extracted + ~34 gap-fill
    formations = {u.formation for u in ax}
    assert any("Cirene" in f for f in formations)          # reconstructed 63rd Cirene
    assert any("Marmarica" in f for f in formations)       # reconstructed 62nd Marmarica
    assert len([u for u in ax if u.is_tank]) >= 10         # the Libyan Tank Command armour


def test_campaign_runs_the_reinforcement_flow():
    # C2-3: the rule-20 reinforcement schedule ([4.43b]/[4.43a]) is wired in -- Rommel and
    # the DAK arrive from Tripoli from GT20, the 8th Army builds up from Cairo. Checked at
    # build time; the full-span arrival is exercised by test_runs_full_span_to_campaign_victory.
    st = campaign(seed=1941)
    reinf = [u for u in st.units if u.arrival_turn > 0]
    assert len(reinf) >= 150                              # the major formations of both schedules
    rommel = next(u for u in st.units if "Rommel" in u.id)
    assert rommel.arrival_turn == 20                      # [4.43b]: Rommel [DAK] arrives GT20
    # the DAK panzer battalions arrive from February 1941 (GT >= 20) at +2 morale.
    dak_tanks = [u for u in reinf if u.is_tank and ("Light" in u.formation or "Panzer" in u.formation)]
    assert dak_tanks
    assert all(u.morale == 2 and u.arrival_turn >= 20 for u in dak_tanks)
    # the 136 Giovani Fascisti division arrives late (GT97) at its -3 morale.
    ggff = [u for u in reinf if "GGFF" in u.formation]
    assert ggff and all(u.morale == -3 for u in ggff)


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
    assert res.final.turn <= FINAL_GT                      # by December 1942 (earlier if 64.7 auto-win)
    assert res.winner in (Side.AXIS, Side.ALLIED, None)    # None = a 64.76 draw
    assert "64.7" in res.reason
