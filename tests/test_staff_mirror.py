"""The Commonwealth staff mirror: BOTH sides played by a live command staff (StaffPolicy), so the
campaign is two 5-seat staffs across the fog of war -- not one staff vs a scripted opponent. Mock-
driven here (zero tokens); the guarantee is the MECHANISM: both sides deliberate, and the two-staff
event log folds byte-identically (STAFF_* events are pure no-op markers in the fold).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import fold                             # noqa: E402
from game.engine import run                             # noqa: E402
from game.events import Side                            # noqa: E402
from game.llm import MockClient                         # noqa: E402
from game.scenario import campaign                      # noqa: E402
from game.staff_events import staff_log                 # noqa: E402
from game.staff_policy import StaffPolicy               # noqa: E402
from scripts.benchmark import _mock_staff               # noqa: E402


def test_both_sides_play_as_command_staffs():
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    allied = StaffPolicy(MockClient(_mock_staff), side=Side.ALLIED)
    res = run(campaign(seed=1941, max_turns=6), axis=axis, allied=allied)
    by_side = Counter(e.side for e in staff_log(res.events))
    assert by_side[Side.AXIS] > 0 and by_side[Side.ALLIED] > 0   # BOTH staffs deliberated
    assert fold(res.initial, res.events) == res.final            # the two-staff log folds cleanly


def test_the_campaign_staff_runs_the_coastal_haul():
    # CampaignStaffPolicy = the live LLM staff PLUS the campaign multi-hop coastal haul (the base
    # StaffPolicy truck relay is left byte-locked for staff-on-rommel). So a campaign Axis staff's
    # trucks actually run the leg-by-leg relay, where the base relay would freeze -- the fix that
    # makes a live-staff balance game meaningful instead of a dead Axis economy.
    from game.campaign_staff import CampaignStaffPolicy
    axis = CampaignStaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    allied = CampaignStaffPolicy(MockClient(_mock_staff), side=Side.ALLIED)
    res = run(campaign(seed=4200, max_turns=16), axis=axis, allied=allied)
    assert sum(1 for e in res.events if e.kind.name == "TRUCK_MOVED") > 0   # the haul is active
    assert fold(res.initial, res.events) == res.final
