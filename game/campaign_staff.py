"""The live command staff on the FULL campaign. Identical to game.staff_policy.StaffPolicy -- the
five-seat LLM staff that decides movement and combat -- except the Quartermaster runs the campaign
multi-hop coastal haul instead of the base single-hop relay, so a live Axis staff can actually
project supply forward. The base StaffPolicy truck relay is left verbatim for staff-on-rommel
(byte-locked), so this campaign variant is a separate class rather than a change to StaffPolicy.
"""
from __future__ import annotations

from .campaign_policy import (_CampaignAxisSupplyMixin, convoy_plan_doctrine, hold_garrisons,
                              malta_africa_doctrine, malta_raid_doctrine)
from .events import Side
from .policy import MoveOrder
from .staff_policy import StaffPolicy
from .state import GameState


class CampaignStaffPolicy(_CampaignAxisSupplyMixin, StaffPolicy):
    """StaffPolicy's live LLM seats for movement/combat, PLUS the campaign forward-supply behaviour
    (the multi-hop coastal haul + staging-dump-aware leapfrog, see _CampaignAxisSupplyMixin). The
    Commonwealth fields no trucks, so the mixin is a no-op on that side and the one class serves both
    mirrors of the two-staff campaign. Constructed exactly like StaffPolicy (client, side, ...)."""

    def malta_raid(self, state: GameState) -> str:
        """[44.23] THE SAME MALTA DOCTRINE THE SCRIPTED CAMPAIGN AXIS FLIES. The Availability Level
        is a strategic-air decision, and the strategic-air seat of this staff is scripted -- exactly
        as the Quartermaster, naval and air seats already are (game.staff_policy). Without this the
        live-staff campaign inherited Policy.malta_raid's "I" and never touched the [44.41] budget,
        so the project's watchable-campaign path and its scripted twin diverged on the one rule
        Phase 5 exists to build. Which LEVEL to spend is a judgement an LLM seat could make, and
        and now that 39.19's desert opportunity cost has landed (block 5.5) it is worth asking
        one -- the trade the seat would be weighing is written out in malta_africa_doctrine."""
        return malta_raid_doctrine(state)

    def malta_africa_planes(self, state: GameState, available: int, level: str) -> int:
        """[44.25]/[39.19] THE SAME AFRICAN-CONTINGENT DOCTRINE THE SCRIPTED CAMPAIGN AXIS FLIES,
        for the same reason: it is a strategic-air decision on a scripted seat, and the two campaign
        variants must not diverge on the one rule Phase 5 exists to build."""
        return malta_africa_doctrine(state, available, level)

    def convoy_plan(self, state: GameState, side: Side, tons: int) -> dict:
        """[56.22] THE SAME CONVOY DOCTRINE THE SCRIPTED CAMPAIGN AXIS FLIES. This one belongs to
        the QUARTERMASTER seat, which is scripted in this staff (game.staff_policy) -- and it is the
        Axis Player's single most important recurring choice, so it is the most obvious candidate in
        the whole engine for promotion to a live seat once the QM seat is LLM-driven."""
        return convoy_plan_doctrine(state, side, tons)

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        # THE STANDING GARRISON ORDER APPLIES TO THE LIVE STAFF TOO (rule 64.73, campaign_claim):
        # whatever the seats propose, a unit BANKING a supplied victory city stays on it. A staff may
        # manoeuvre with everything else; it may not march the Tobruk and Bardia garrisons into the
        # desert -- measured, every staff tried did exactly that and ended the war with every victory
        # city empty. The scripted policies get the whole take-and-hold (campaign_policy.
        # take_and_hold_moves); a staff gets only its HOLD half, because deciding where the rest of
        # the army goes is the entire point of having one.
        return hold_garrisons(super().movement(state, side), state, side)
