"""Campaign staff framing (rule 64.73): the campaign observation -- and the staff prompts it
feeds -- reframe the seats from RUSHING the single far objective to HOLDING the victory cities
SUPPLIED. The whole reframing is gated on the observation carrying `victory_cities` (present only
under CampaignVictory), so Rommel's Arrival keeps its byte-locked single-objective framing.

The per-unit hold-ground flag is `can_hold` (= CampaignVictory._supplied, traces BOTH fuel and
ammo). It is named distinctly from the movement-phase fuel-gate `supplied` (can this unit pay to
MOVE this stage -- byte-locked on rommel) and the ammo-only `defensible` (defends at full strength).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.events import Side                                    # noqa: E402
from game.llm_policy import build_movement_prompt               # noqa: E402
from game.observation import observe                            # noqa: E402
from game.scenario import campaign, rommels_arrival            # noqa: E402
from game.staff import Lane, role_brief, unit_lanes            # noqa: E402
from game.staff_policy import build_intent_prompt, intent_preamble  # noqa: E402


def test_campaign_observation_carries_victory_cities_and_can_hold():
    st = campaign(seed=1941)
    obs = observe(st, Side.AXIS)
    # (a) the victory_cities section: one entry per rule-64.73 city, each with its hex, name,
    # THIS side's VP value, nominal control, and who (if anyone) holds it SUPPLIED.
    vc = obs["victory_cities"]
    assert vc and len(vc) == len(st.victory.cities)
    for c in vc:
        assert set(c) == {"hex", "name", "vp", "controlled_by", "held_supplied"}
        assert c["controlled_by"] in ("AXIS", "ALLIED", "NEUTRAL")
        assert c["held_supplied"] in ("AXIS", "ALLIED", None)   # None = nobody banks it (unsupplied)
    # VP is THIS side's Geographic Occupation Points: Tobruk is 200 to the Axis, 100 to the CW.
    assert next(c for c in vc if c["name"] == "Tobruk")["vp"] == 200
    assert next(c for c in observe(st, Side.ALLIED)["victory_cities"]
                if c["name"] == "Tobruk")["vp"] == 100

    # (b) every combat unit carries can_hold, the 64.73 hold-ground supply flag -- the SAME gate
    # as the ammo-only `defensible` (both are is_combat-only), so the two key-sets coincide.
    assert all(("can_hold" in u) == ("defensible" in u) for u in obs["your_units"])
    combat_views = [u for u in obs["your_units"] if "can_hold" in u]
    assert combat_views
    # can_hold is EXACTLY the predicate the campaign scores on (CampaignVictory._supplied): the
    # agent sees the very test it will be graded by (traces both fuel AND ammo).
    for u in st.living(Side.AXIS):
        if u.is_combat:
            view = next(v for v in obs["your_units"] if v["id"] == u.id)
            assert view["can_hold"] == st.victory._supplied(st, u)


def test_staff_seat_brief_and_prompts_carry_the_hold_framing():
    # A GOC seat plans off role_brief (the lane-scoped projection of observe). It must keep the
    # shared victory_cities and each of its units' can_hold flag, and the prompts built from it
    # must carry the HOLD-the-cities framing, not the rush-the-objective one.
    st = campaign(seed=1941)
    obs = observe(st, Side.AXIS)
    brief = role_brief(obs, Lane.MOBILE, unit_lanes(st, Side.AXIS))
    assert brief["victory_cities"] == obs["victory_cities"]
    assert brief["your_units"] and all("can_hold" in u for u in brief["your_units"])

    move_prompt = build_movement_prompt(brief)
    assert "HOLD" in move_prompt and "64.73" in move_prompt and "can_hold" in move_prompt
    assert "Advance toward the objective" not in move_prompt
    assert "Mission (rule 64.73)" in build_intent_prompt(brief)
    assert "HOLD DIRECTIVE" in intent_preamble({"objective": "hold the coast"}, campaign=True)


def test_rommel_staff_observation_has_no_campaign_framing():
    # Byte-locked framing intact: Rommel's Arrival carries no victory_cities and no can_hold, and
    # its seat prompts keep the single-objective RUSH framing (Advance / STORM, never HOLD).
    st = rommels_arrival(seed=42)
    obs = observe(st, Side.AXIS)
    assert "victory_cities" not in obs
    assert all("can_hold" not in u for u in obs["your_units"])

    move_prompt = build_movement_prompt(obs)
    assert "Advance toward the objective" in move_prompt
    assert "victory_cities" not in move_prompt and "HOLD DIRECTIVE" not in move_prompt
    assert "STORM DIRECTIVE" in intent_preamble({"objective": "seize Tobruk"})
    assert "Objective: hex" in build_intent_prompt(obs)
