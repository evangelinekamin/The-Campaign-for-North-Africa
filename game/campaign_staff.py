"""The live command staff on the FULL campaign. Identical to game.staff_policy.StaffPolicy -- the
five-seat LLM staff that decides movement and combat -- except the Quartermaster runs the campaign
multi-hop coastal haul instead of the base single-hop relay, so a live Axis staff can actually
project supply forward. The base StaffPolicy truck relay is left verbatim for staff-on-rommel
(byte-locked), so this campaign variant is a separate class rather than a change to StaffPolicy.
"""
from __future__ import annotations

from .campaign_policy import _CampaignAxisSupplyMixin, hold_garrisons
from .events import Side
from .policy import MoveOrder
from .staff_policy import StaffPolicy
from .state import GameState


class CampaignStaffPolicy(_CampaignAxisSupplyMixin, StaffPolicy):
    """StaffPolicy's live LLM seats for movement/combat, PLUS the campaign forward-supply behaviour
    (the multi-hop coastal haul + staging-dump-aware leapfrog, see _CampaignAxisSupplyMixin). The
    Commonwealth fields no trucks, so the mixin is a no-op on that side and the one class serves both
    mirrors of the two-staff campaign. Constructed exactly like StaffPolicy (client, side, ...)."""

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        # THE STANDING GARRISON ORDER APPLIES TO THE LIVE STAFF TOO (rule 64.73, campaign_claim):
        # whatever the seats propose, a unit BANKING a supplied victory city stays on it. A staff may
        # manoeuvre with everything else; it may not march the Tobruk and Bardia garrisons into the
        # desert -- measured, every staff tried did exactly that and ended the war with every victory
        # city empty. The scripted policies get the whole take-and-hold (campaign_policy.
        # take_and_hold_moves); a staff gets only its HOLD half, because deciding where the rest of
        # the army goes is the entire point of having one.
        return hold_garrisons(super().movement(state, side), state, side)
