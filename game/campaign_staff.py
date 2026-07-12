"""The live command staff on the FULL campaign. Identical to game.staff_policy.StaffPolicy -- the
five-seat LLM staff that decides movement and combat -- except the Quartermaster runs the campaign
multi-hop coastal haul instead of the base single-hop relay, so a live Axis staff can actually
project supply forward. The base StaffPolicy truck relay is left verbatim for staff-on-rommel
(byte-locked), so this campaign variant is a separate class rather than a change to StaffPolicy.
"""
from __future__ import annotations

from .campaign_policy import _CampaignAxisSupplyMixin
from .staff_policy import StaffPolicy


class CampaignStaffPolicy(_CampaignAxisSupplyMixin, StaffPolicy):
    """StaffPolicy's live LLM seats for movement/combat, PLUS the campaign forward-supply behaviour
    (the multi-hop coastal haul + staging-dump-aware leapfrog, see _CampaignAxisSupplyMixin). The
    Commonwealth fields no trucks, so the mixin is a no-op on that side and the one class serves both
    mirrors of the two-staff campaign. Constructed exactly like StaffPolicy (client, side, ...)."""
