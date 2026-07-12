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
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
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


def test_campaign_supply_economy():
    # C3-1: the convoy/supply economy is wired -- the Commonwealth's inexhaustible Suez base
    # (Cairo + Alexandria on MAJOR_CITY hexes, exempt from evaporation) and the Axis
    # Mediterranean convoy faucet (56.4, landing at Benghazi in the west, to be hauled east).
    st = campaign(seed=1941)
    assert st.convoys and st.ports                          # the engine faucet is seeded
    cw_base = [s for s in st.supplies if s.base]
    assert len(cw_base) == 2 and all(s.side == Side.ALLIED for s in cw_base)
    assert all(s.fuel > 1_000_000 for s in cw_base)         # a reservoir no 111-turn draw exhausts
    axis_convoys = [c for c in st.convoys if c.side == Side.AXIS]
    assert axis_convoys and all(c.dest == "AX-Benghazi" for c in axis_convoys)


def test_campaign_commonwealth_can_attack():
    # Offensive-CW: on a Compass Game-Turn (GT13-22) the Commonwealth is not a static sandbag -- it
    # runs the ALLIED ATTACKER branch (driving toward Benghazi), where between offensives it is the
    # rear-oriented defender. We assert the SWITCH on a real mid-campaign board. Whether the
    # deliberately tight CW forward supply lets that advance REACH Benghazi under crude scripted play
    # is a balance question, not an invariant: the greedy script culminates at once, as both sides do.
    from dataclasses import replace
    board = run(campaign(seed=1941, max_turns=13), CampaignAxisPolicy(),
                CampaignCommonwealthPolicy()).final
    pol = CampaignCommonwealthPolicy()
    attacker = ScriptedPolicy(attacker=Side.ALLIED)
    on = replace(board, turn=15)          # mid-Compass (13-22): offensive
    off = replace(board, turn=30)         # between Compass and Crusader: defensive
    assert pol._on_offensive(on) and not pol._on_offensive(off)
    # On an offensive turn the CW emits the ALLIED attacker branch's moves verbatim (toward Benghazi).
    assert pol.movement(on, Side.ALLIED) == attacker.movement(on, Side.ALLIED)


def test_campaign_defensive_supply_integrity():
    # Two supply-integrity fixes verified on one pre-Compass (defensive) run:
    #  bug 1 -- the Suez base depots (rule 57) are immobile: they never leave Cairo/Alexandria.
    #           (The scripted policy had walked the 125M-point base to the front, supplying the CW
    #           everywhere and collapsing the supply-traced victory into a CW rout.)
    #  bug 3 -- CW field dumps fall back EAST with the front, never leapfrogging WEST toward the
    #           advancing Axis (the offensive-CW objective change had reversed this on defense).
    from game import coords
    from game.hexmap import distance
    beng = coords.to_axial(coords.parse("A4827"))
    res = run(campaign(seed=1941, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    seeded = {s.id: s.hex for s in res.initial.supplies if s.base}
    assert seeded and {s.id: s.hex for s in res.final.supplies if s.base} == seeded   # bases pinned
    for su in res.final.supplies:
        if su.side == Side.ALLIED and not su.base and not su.is_dummy:
            start = next(s for s in res.initial.supplies if s.id == su.id)
            assert distance(su.hex, beng) >= distance(start.hex, beng)   # never drifted west


def test_campaign_railhead_port_uses_the_chart_tonnage():
    # Bug 2: PORT-Matruh was silently throttled at Alexandria's 15000t via a "mersa matruh" vs
    # "mersa_matruh" data-key miss; the 55.3 chart value is 250t -- and tonnage is the sole 55.14
    # gate, so this one number is the entire CW rail throttle.
    matruh = next(p for p in campaign(seed=1941).ports if p.id == "PORT-Matruh")
    assert matruh.cap_tons == 250


def test_campaign_malta_throttles_the_axis_convoy():
    # C4 counterweight: rule 44 (Malta) abstracted -- the Axis Mediterranean convoy (60.37 lane "2")
    # is under a Commonwealth interdiction schedule, so it no longer lands its full tonnage
    # uncontested; each monthly arrival is skimmed on the 41.66 CRT.
    st = campaign(seed=1941, max_turns=24)
    assert any(o.lane == "2" for o in st.interdictions)          # Malta is seeded on the Axis lane
    res = run(campaign(seed=1941, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert [e for e in res.events if e.kind.name == "CONVOY_INTERDICTED"]   # the convoy is skimmed


def test_max_turns_truncates():
    assert campaign(max_turns=8).max_turns == 8


def test_campaign_is_deterministic():
    # Same seed -> byte-identical event stream, on the canonical scripted pairing (Axis haul +
    # offensive-CW). A short slice keeps the test fast.
    a = run(campaign(seed=7, max_turns=8), axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    b = run(campaign(seed=7, max_turns=8), axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    assert determinism_signature(a.events) == determinism_signature(b.events)


def test_runs_full_span_to_campaign_victory():
    # The headline: the engine runs the entire GT1..111 campaign and terminates through
    # rule 64.7 (a graded 64.76 result or an auto-win/annihilation), not the built-in
    # Race-for-Tobruk logic.
    res = run(campaign(seed=1941), axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    assert res.final.turn <= FINAL_GT                      # by December 1942 (earlier if 64.7 auto-win)
    assert res.winner in (Side.AXIS, Side.ALLIED, None)    # None = a 64.76 draw
    assert "64.7" in res.reason
