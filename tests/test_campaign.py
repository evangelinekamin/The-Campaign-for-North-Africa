"""C1-7: the campaign shell. The full A-E theatre runs the GT1..111 clock end to end
under scripted play and terminates through the rule-64.7 campaign victory, exercising
the eastern geography, the September-1940 calendar, and the pluggable victory seam that
C1-3/C1-4/C1-6 put in place -- all without the C2 army or C3 economy.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords, wells
from game.calendar import CAMPAIGN_SEASON_OFFSET, FINAL_GT
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.campaign_victory import CampaignVictory
from game.engine import determinism_signature, run
from game.events import Side
from game.policy import ScriptedPolicy
from game.scenario import campaign
from baselines import CAMPAIGN_SEED                                 # noqa: E402


def test_builds_full_theatre():
    st = campaign(seed=CAMPAIGN_SEED)
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
    ax = [u for u in campaign(seed=CAMPAIGN_SEED).units if u.side == Side.AXIS]
    assert len(ax) >= 90                                   # ~95: 61 extracted + ~34 gap-fill
    formations = {u.formation for u in ax}
    assert any("Cirene" in f for f in formations)          # reconstructed 63rd Cirene
    assert any("Marmarica" in f for f in formations)       # reconstructed 62nd Marmarica
    assert len([u for u in ax if u.is_tank]) >= 10         # the Libyan Tank Command armour


def test_campaign_runs_the_reinforcement_flow():
    # C2-3: the rule-20 reinforcement schedule ([4.43b]/[4.43a]) is wired in -- Rommel and
    # the DAK arrive from Tripoli from GT20, the 8th Army builds up from Cairo. Checked at
    # build time; the full-span arrival is exercised by test_runs_full_span_to_campaign_victory.
    st = campaign(seed=CAMPAIGN_SEED)
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
    st = campaign(seed=CAMPAIGN_SEED)
    assert st.convoys and st.ports                          # the engine faucet is seeded
    # base=True marks BOTH the rule-57 strategic depots and the 52.1 wells (52.44: water in a
    # well does not evaporate either) -- the two rear DEPOTS are the ones this test is about.
    cw_base = [s for s in st.supplies if s.base and not wells.is_water_source(s)]
    assert len(cw_base) == 2 and all(s.side == Side.ALLIED for s in cw_base)
    assert all(s.fuel > 1_000_000 for s in cw_base)         # a reservoir no 111-turn draw exhausts
    # The Axis lands at TWO ports of arrival, not one (56.11/56.18: the Convoy Air Distance chart
    # names six Axis lanes, and two of them run to TOBRUK -- the harbour the Axis has held since
    # Game-Turn 1). Benghazi takes the Mediterranean convoy the lorries haul east; Tobruk takes the
    # sea lifeline that feeds the fortress garrison at distance 0.
    axis_convoys = [c for c in st.convoys if c.side == Side.AXIS]
    assert axis_convoys
    assert {c.dest for c in axis_convoys} == {"AX-Benghazi", "AX-Stage-Tobruk"}


def test_campaign_commonwealth_can_attack():
    # Offensive-CW: on a Compass Game-Turn (GT13-22) the Commonwealth is not a static sandbag -- it
    # runs the ALLIED ATTACKER branch (driving toward Benghazi), where between offensives it is the
    # rear-oriented defender. We assert the SWITCH on a real mid-campaign board. Whether the
    # deliberately tight CW forward supply lets that advance REACH Benghazi under crude scripted play
    # is a balance question, not an invariant: the greedy script culminates at once, as both sides do.
    from dataclasses import replace
    board = run(campaign(seed=CAMPAIGN_SEED, max_turns=13), CampaignAxisPolicy(),
                CampaignCommonwealthPolicy()).final
    pol = CampaignCommonwealthPolicy()
    attacker = ScriptedPolicy(attacker=Side.ALLIED)
    on = replace(board, turn=15)          # mid-Compass (13-22): offensive
    off = replace(board, turn=30)         # between Compass and Crusader: defensive
    assert pol._on_offensive(on) and not pol._on_offensive(off)
    # On an offensive turn the CW runs the ALLIED attacker branch (driving toward Benghazi), with the
    # two standing orders of rule 64.73 laid over it:
    #   * THE TAKE-AND-HOLD (game.campaign_claim) DETACHES units to go and get the victory cities the
    #     army does not yet bank -- the whole point of the offensive being the POINTS, not the far
    #     objective hex. A detached unit is out of the general advance (it has its own orders).
    #   * THE STANDING GARRISON ORDER, which no offensive countermands: a unit BANKING a supplied
    #     victory city keeps banking it. That order bites because the forward concentration means the
    #     Commonwealth actually holds one -- the rail-fed railhead at Mersa Matruh is itself a 64.73
    #     city, and its garrison does not join the attack.
    from game import campaign_claim
    from game.campaign_policy import (_standing_plan, garrison_units, hold_garrisons,
                                      keep_in_trace)
    assert garrison_units(on, Side.ALLIED), "the CW banks no victory city -- the check is vacuous"
    assert campaign_claim.claims(on, Side.ALLIED, escort=True), \
        "the take-and-hold claims no city -- the check is vacuous"
    # THE PIPELINE GREW TWO STAGES, and the reconstruction has to grow with it or it is asserting
    # last week's code. Both are rules this repo did not have when the test was written:
    #   * [54.16]/[32.16] keep_in_trace -- the general advance may not outrun its supply. It is laid
    #     over the ARMY half only; the standing orders' detachments are not filtered by it, because
    #     each has already answered the same question better (a city claim only goes where the unit
    #     could be FED; a 32.33 desert column carries its larder). See keep_in_trace.
    #   * [24.6] the railway gang -- the two NZ Railroad Construction companies march to the railhead
    #     and lay track. They are ENGINEERS, not combat units (23.11), so no other proposer in this
    #     repo will ever emit an order for them and their orders simply ride alongside.
    # The claim is unchanged and just as tight: on a Compass Game-Turn the Commonwealth runs the
    # ALLIED ATTACKER branch, with the rule-64.73 standing orders laid over it, and the composition
    # is exactly this and nothing else.
    plan = _standing_plan(on, Side.ALLIED, escort=True)
    take = campaign_claim.claim_moves(on, Side.ALLIED, plan)
    busy = {c.unit_id for c in plan}
    march = keep_in_trace([o for o in attacker.movement(on, Side.ALLIED) if o.unit_id not in busy],
                          on, Side.ALLIED)
    assert pol.movement(on, Side.ALLIED) == (
        pol._railway(on, Side.ALLIED) + hold_garrisons(take + march, on, Side.ALLIED))


def test_campaign_defensive_supply_integrity():
    # Two supply-integrity fixes verified on one pre-Compass (defensive) run:
    #  bug 1 -- the Suez base depots (rule 57) are immobile: they never leave Cairo/Alexandria.
    #           (The scripted policy had walked the 125M-point base to the front, supplying the CW
    #           everywhere and collapsing the supply-traced victory into a CW rout.)
    #  bug 3 -- a CW field dump never gets AHEAD OF THE ARMY. The original bug was a dump chasing
    #           the offensive objective (Benghazi) into the advancing Axis on a DEFENSIVE turn, and
    #           the original guard was "no dump ever moves one hex west". That guard also forbade
    #           the dumps coming FORWARD to the line the army now concentrates on -- which is the
    #           whole point of them (32.33) -- so it is restated as the invariant it was really
    #           protecting: the supply never leapfrogs out into the desert in front of the troops.
    #           It follows them, to the railhead and to the units it must feed, and no further.
    from game import coords
    from game.hexmap import distance
    beng = coords.to_axial(coords.parse("A4827"))
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    seeded = {s.id: s.hex for s in res.initial.supplies if s.base}
    assert seeded and {s.id: s.hex for s in res.final.supplies if s.base} == seeded   # bases pinned
    spearhead = min(distance(u.hex, beng) for u in res.final.living(Side.ALLIED) if u.is_combat)
    moved = 0
    seeded_hex = {s.id: s.hex for s in res.initial.supplies}
    for su in res.final.supplies:
        if su.side == Side.ALLIED and not su.base and not su.is_dummy:
            if su.id not in seeded_hex:
                continue      # FOUNDED mid-campaign (rule 54.11): it never "relocated" anywhere --
                              # the depot list is no longer frozen at construction
            start = res.initial.supply(su.id)
            if su.hex == start.hex:
                continue      # never relocated: the seeded spine, and the Tobruk garrison dump that
                              # sits inside the Axis-held fortress waiting for the CW to take it
            moved += 1
            assert distance(su.hex, beng) >= spearhead, \
                f"{su.id} leapfrogged past the army toward Benghazi"
    assert moved, "no field dump relocated at all -- the 32.3 bridge is not under test"


def test_campaign_railhead_port_uses_the_chart_tonnage():
    # Bug 2: PORT-Matruh was silently throttled at Alexandria's 15000t via a "mersa matruh" vs
    # "mersa_matruh" data-key miss; the 55.3 chart value is 250t -- and tonnage is the sole 55.14
    # gate, so this one number is the entire CW rail throttle.
    matruh = next(p for p in campaign(seed=CAMPAIGN_SEED).ports if p.id == "PORT-Matruh")
    assert matruh.cap_tons == 250


def test_campaign_malta_throttles_the_axis_convoy():
    # C4 counterweight: rule 44 (Malta) abstracted -- the Axis Mediterranean convoy (60.37 lane "2")
    # is under a Commonwealth interdiction schedule, so it no longer lands its full tonnage
    # uncontested; each monthly arrival is skimmed on the 41.66 CRT.
    st = campaign(seed=CAMPAIGN_SEED, max_turns=24)
    assert any(o.lane == "2" for o in st.interdictions)          # Malta is seeded on the Axis lane
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert [e for e in res.events if e.kind.name == "CONVOY_INTERDICTED"]   # the convoy is skimmed


def test_campaign_tobruk_lifeline_holds_only_when_the_commonwealth_takes_it():
    # C4 Tobruk sea lifeline (rule 30/56.3): the SEA-TOBRUK ferry + PORT-Tobruk + the empty AL-Tobruk
    # garrison dump are seeded, but 56.15 CANCELS the ferry while the Axis holds Tobruk (seeded
    # control C4807=AXIS at GT1). Nothing lands in the garrison dump until the Commonwealth takes the
    # fortress -- the historical shape (the siege lifeline serves a CW-held Tobruk, not day one).
    #
    # The harbour itself is a PLACE, not a possession: ONE Port on the hex (the 55.3 chart lists one
    # Tobruk), flagged with the side that HOLDS the city at Game-Turn 1 -- the Axis, which is what
    # engine._air_port reads to decide whose harbour may be bombed. The 56.15 gate, keyed on CONTROL,
    # is what actually decides which side's convoy sails into it. See tests/test_campaign_lifeline.py.
    st = campaign(seed=CAMPAIGN_SEED, max_turns=12)
    assert any(c.lane == "SEA-TOBRUK" for c in st.convoys)              # the ferry is seeded every turn
    tobruk_ports = [p for p in st.ports if p.id == "PORT-Tobruk"]
    assert len(tobruk_ports) == 1 and tobruk_ports[0].side == Side.AXIS   # one harbour, the GT1 holder's
    tob = coords.to_axial(coords.parse("C4807"))
    assert st.control.get(tob) == Side.AXIS                             # Axis holds Tobruk in Sep 1940
    res = run(campaign(seed=CAMPAIGN_SEED, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    alt = next(s for s in res.final.supplies if s.id == "AL-Tobruk")
    assert alt.ammo == 0 and alt.fuel == 0 and alt.stores == 0          # empty: the ferry never landed while Axis-held


def test_the_standing_garrison_order_keeps_the_cities_it_banks():
    # THE fix for the campaign's largest source of value destruction. The Axis OPENS the campaign
    # banking Tobruk (200 VP) and Bardia (100 VP) -- the Libyan Tank Command garrisons them, supplied
    # by the 60.34 staging dumps beneath them. Every policy tried (scripted AND live LLM staffs)
    # marched those garrisons east and finished GT111 with every victory city EMPTY, a 0-0 draw --
    # while a side that did NOTHING AT ALL simply held them and won 300-10. So a unit that is banking
    # a city (on it and supplied = the exact 64.73 occupier test) is never given a move order.
    from game.campaign_policy import garrison_units, hold_garrisons
    from game.policy import MoveOrder
    st = campaign(seed=CAMPAIGN_SEED)
    cv = st.victory
    banked = [n for ax, a, c, n in cv.cities if cv._occupier(st, ax) == Side.AXIS]
    assert {"Tobruk", "Bardia"} <= set(banked)          # the Axis opens holding them, supplied
    keep = garrison_units(st, Side.AXIS)
    assert keep                                          # a garrison is pinned on each
    # a move order for a garrison is dropped; every other unit still manoeuvres freely
    held = next(iter(keep))
    other = next(u.id for u in st.living(Side.AXIS) if u.is_combat and u.id not in keep)
    orders = [MoveOrder(held, (0, 0)), MoveOrder(other, (0, 0))]
    kept = hold_garrisons(orders, st, Side.AXIS)
    assert [o.unit_id for o in kept] == [other]


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
    # rule 64.7 (a graded 64.76 result, or the 64.71 auto-win -- the only automatic end the
    # rule defines), not the built-in Race-for-Tobruk logic.
    res = run(campaign(seed=CAMPAIGN_SEED), axis=CampaignAxisPolicy(), allied=CampaignCommonwealthPolicy())
    assert res.final.turn <= FINAL_GT                      # by December 1942 (earlier if 64.7 auto-win)
    assert res.winner in (Side.AXIS, Side.ALLIED, None)    # None = a 64.76 draw
    assert "64.7" in res.reason
