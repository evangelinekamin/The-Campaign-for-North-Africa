"""The Commonwealth's scripted policy for the FULL campaign: a defender that goes over to the
offensive on the historical Game-Turn windows (Operation Compass, Crusader, Second Alamein), so
the desert war SEE-SAWS instead of the Commonwealth sandbagging for 111 turns.

Campaign-ONLY: rommels_arrival / siege_of_tobruk keep the base ScriptedPolicy defender, so their
event streams stay byte-identical. On an offensive Game-Turn the Commonwealth simply runs the base
ATTACKER branch verbatim -- advancing toward state.objective_for(ALLIED) (Benghazi, the Axis rear,
far WEST), gated by the attacker branch's own per-move fuel check, so it culminates where it
outruns its supply (the historical "culminate short"). Between offensives it holds and gives
ground; the pushback comes free from the scripted Axis (and Rommel/the DAK arriving GT20) driving
east, so only the ATTACK windows need encoding.
"""
from __future__ import annotations

from dataclasses import dataclass

from .events import Side
from .policy import AttackOrder, MoveOrder, ScriptedPolicy, SupplyMoveOrder
from .state import GameState


@dataclass(frozen=True)
class OffensiveSchedule:
    """The Game-Turns the Commonwealth is on the offensive (inclusive windows on state.turn).
    Empty windows -> never offensive -> byte-identical to the pure defender."""
    windows: tuple[tuple[int, int], ...] = ()

    def is_offensive(self, gt: int) -> bool:
        return any(a <= gt <= b for a, b in self.windows)


# The three Commonwealth offensives of the desert war on the campaign calendar (game.calendar:
# GT1 = Sep 1940, 4 GT/month): Operation Compass (Dec 1940 - Feb 1941, destroys the 10th Army and
# reaches El Agheila), Operation Crusader (Nov 1941 - Jan 1942, relieves Tobruk), Second El Alamein
# (Oct - Dec 1942, the decisive drive). Cross-checked to the game's own scenario start-turns
# (Rommel GT20/26, Crusader GT57, El Alamein GT102).
COMPASS = (13, 22)
CRUSADER = (57, 64)
ALAMEIN = (102, 111)
CAMPAIGN_CW_OFFENSIVES = OffensiveSchedule((COMPASS, CRUSADER, ALAMEIN))


class CampaignCommonwealthPolicy(ScriptedPolicy):
    """A scripted Commonwealth DEFENDER (attacker=AXIS, so every inherited reflex -- defender
    moves and sorties, counter-assault, elastic retreat, initiative -- is unchanged) that switches
    to the ATTACKER branch on the scheduled offensive Game-Turns, driving west toward
    objective_for(ALLIED)."""

    def __init__(self, schedule: OffensiveSchedule = CAMPAIGN_CW_OFFENSIVES):
        super().__init__(attacker=Side.AXIS)                     # defender wiring, exactly like the base
        self._schedule = schedule
        self._offensive = ScriptedPolicy(attacker=Side.ALLIED)   # the attacker branch for offensive turns

    def _on_offensive(self, state: GameState) -> bool:
        return self._schedule.is_offensive(state.turn)

    def movement(self, state: GameState, side: Side) -> list[MoveOrder]:
        return (self._offensive if self._on_offensive(state) else super()).movement(state, side)

    def combat(self, state: GameState, side: Side) -> list[AttackOrder]:
        return (self._offensive if self._on_offensive(state) else super()).combat(state, side)

    def supply_orders(self, state: GameState, side: Side) -> list[SupplyMoveOrder]:
        # On the offensive the dumps must leapfrog WEST behind the advance, not hold in the rear.
        return (self._offensive if self._on_offensive(state) else super()).supply_orders(state, side)
