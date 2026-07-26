"""Movement discipline (game.tactics.husbands_cohesion / voluntary_overage_dp).

The audit (scratchpad/port/cohesion-economy-audit.md) found the cohesion ECONOMY faithful --
every sink and source fires at the book's rate -- but the scripted policies pick a voluntary
move's destination by "closest to the objective, CP cost only a tiebreak" with NO cohesion
awareness anywhere in the movement path. A motorized unit can therefore earn enough 6.21
Disorganization in a single UNIT_MOVED to punch straight through the 15.88 auto-surrender floor
(measured: a healthy CPA-25 unit dashed to the 2x-CPA reach ceiling, 0 -> -25 in one move).

tactics.husbands_cohesion is the fix: a competent commander's self-restraint, not a rule change.
It forecasts the SAME overage the engine will charge (a byte-exact mirror of
engine._overage_dp/_disorganize_overage, kept apart to preserve the engine<->policy import
break) and refuses a destination whose predicted post-move Cohesion would fall to <=-17 (rule
15.88/17.24, a rulebook constant, not a balance dial). Applied per-move, the allowed overage is
exactly `cohesion + 17`, so a healthy unit still dashes, a battered one creeps, and a unit is
never frozen out of a CPA-respecting move.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import tactics                                     # noqa: E402
from game.campaign_policy import CampaignCommonwealthPolicy   # noqa: E402
from game.engine import _movement, _Run                       # noqa: E402
from game.events import EventKind, Phase, Side                # noqa: E402
from game.hexmap import Coord                                 # noqa: E402
from game.movement import TerrainMap                          # noqa: E402
from game.policy import MoveOrder, Policy, ScriptedPolicy      # noqa: E402
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP  # noqa: E402
from game.terrain import Mobility, Terrain                    # noqa: E402


# --- tiny fixtures (mirrors tests/test_rommel.py's _unit/_grid/_state idiom) ------------------

def _unit(uid: str = "CW-Spearhead", *, side: Side = Side.AXIS, cpa: int = 25,
          cohesion: int = 0, cp_used: float = 0.0, hex_: Coord = (0, 0),
          mobility: Mobility = Mobility.VEHICLE) -> Unit:
    return Unit(uid, side, hex_, (StepRecord("x", 3),), mobility,
                cpa=cpa, stacking_points=2, oca=6, dca=6, cohesion=cohesion, cp_used=cp_used)


def _grid(n: int = 30) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _state(units, *, target_hex: Coord = (0, 0), supplies=(), seed: int = 7) -> GameState:
    return GameState(turn=1, max_turns=12, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                     seed=seed, weather="normal", vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=target_hex, supplies=tuple(supplies),
                     consumed={}, initial_supply={})


# --- voluntary_overage_dp: the predictor is byte-exact against the engine's own charge --------

class _FixedMover(Policy):
    """A scripted policy that names one fixed destination for one unit and nothing else."""

    def __init__(self, dest: Coord):
        self.dest = dest

    def movement(self, state, side):
        return [MoveOrder(state.living(side)[0].id, self.dest)]

    def combat(self, state, side):
        return []


def test_voluntary_overage_dp_matches_the_engines_charged_overage():
    """(iv) The predictor must equal what engine._disorganize_overage actually charges for the
    identical move -- guards tactics._overage_dp against silently drifting from
    engine._overage_dp (the two are separate copies by design, see tactics.py's module
    docstring on the engine<->policy import break)."""
    # FOOT sidesteps the 49.13 fuel draw (49.12: no fuel burned) while a printed cpa of 25
    # still gets the 8.16 motorized 2x-CPA ceiling (tactics._cp_ceiling keys off cpa alone) --
    # CLEAR costs the same 2 CP/hex either way (8.37), so a plain 21-hex dash is exactly 42 CP,
    # an uncomplicated round number to hand-verify.
    u = _unit(cpa=25, cohesion=0, cp_used=0.0, hex_=(0, 0), mobility=Mobility.FOOT)
    dest = (21, 0)
    state = _state([u])
    predicted = tactics.voluntary_overage_dp(state, u, 42.0)
    assert predicted == 17          # floor(42-25) - floor(0-25) = 17 - 0

    r = _Run(state)
    _movement(r, {Side.AXIS: _FixedMover(dest), Side.ALLIED: Policy()}, Side.AXIS)

    moved = [e for e in r.events if e.kind == EventKind.UNIT_MOVED]
    assert len(moved) == 1 and moved[0].payload["cp_spent"] == 42.0
    changed = [e for e in r.events if e.kind == EventKind.COHESION_CHANGED]
    assert len(changed) == 1
    assert changed[0].payload["delta"] == -predicted
    assert r.state.unit(u.id).cohesion == -predicted


# --- husbands_cohesion: the graduated husbanding table (spec Q2) ------------------------------

def test_dash_into_the_surrender_band_is_disallowed():
    """The audit's own measured case: a healthy (cohesion 0) CPA-25 unit offered the full
    2x-CPA dash (50 CP) must be refused -- 50 CP earns 25 DP, and 0 - 25 = -25 <= -17."""
    u = _unit(cpa=25, cohesion=0)
    state = _state([u])
    assert not tactics.husbands_cohesion(state, u, 50.0)


def test_high_cohesion_unit_still_dashes_the_full_ceiling():
    """At cohesion +10 the 2x-CPA ceiling itself binds before the -17 floor does (26 DP of
    allowance vs the ceiling's 25) -- a fresh unit is never second-guessed for a rules-legal
    8.16 dash."""
    u = _unit(cpa=25, cohesion=10)
    state = _state([u])
    assert tactics.husbands_cohesion(state, u, 50.0)      # the full 2x-CPA ceiling


def test_battered_unit_at_minus_sixteen_is_never_frozen():
    """A unit already at -16 still gets its full <=1x-CPA move (0 overage, always affordable)
    -- the floor only ever removes OVER-CPA candidates, never the CPA-respecting move itself."""
    u = _unit(cpa=25, cohesion=-16)
    state = _state([u])
    assert tactics.husbands_cohesion(state, u, 25.0)      # exactly 1x CPA: 0 overage
    assert not tactics.husbands_cohesion(state, u, 26.0)  # one CP over: 1 DP, -16-1=-17, disallowed


def test_the_allowance_is_cohesion_plus_seventeen():
    """The spec's table, at cohesion 0: 16 DP of overage (a 41-CP move on a CPA-25 unit) is
    still affordable; 17 DP (42 CP) is not -- the exact 0 -> -17-through-the-floor bug the fix
    exists to stop, calibrated one CP either side of the line."""
    u = _unit(cpa=25, cohesion=0)
    state = _state([u])
    assert tactics.husbands_cohesion(state, u, 41.0)      # 16 DP: 0-16=-16 > -17
    assert not tactics.husbands_cohesion(state, u, 42.0)  # 17 DP: 0-17=-17, not > -17


def test_surrender_floor_is_the_rulebook_constant():
    assert tactics.SURRENDER_FLOOR == -17


# --- policy-level integration: the two shared pick-sites stop proposing the suicide dash ------

def test_scripted_attacker_does_not_dash_a_healthy_unit_into_surrender():
    """Site A (ScriptedPolicy.movement's candidates pick) is the base BOTH the Axis campaign
    (CampaignAxisPolicy.movement -> super().movement()) and the CW offensive branch
    (CampaignCommonwealthPolicy._advance) route through. A healthy CPA-25 attacker offered a
    distant objective well past its 2x-CPA reach must not be ordered the farthest-forward hex
    if that predicts a post-move Cohesion <=-17 -- it must still advance, just not that far."""
    target = (30, 0)
    u = _unit("GE-Spearhead", cpa=25, cohesion=0, hex_=(0, 0), mobility=Mobility.FOOT)
    state = _state([u], target_hex=target)

    orders = ScriptedPolicy(Side.AXIS).movement(state, Side.AXIS)

    assert orders, "a healthy unit should still advance -- just not into the floor"
    order = next(o for o in orders if o.unit_id == u.id)
    reach = tactics.reachable_for(state, u, frozenset(), frozenset())
    predicted = u.cohesion - tactics.voluntary_overage_dp(state, u, reach[order.to])
    assert predicted > tactics.SURRENDER_FLOOR


def test_campaign_commonwealth_march_does_not_order_a_self_surrender():
    """The audit's dominant contributor: CampaignCommonwealthPolicy._march (site C), the
    forward-concentration pick. A CW unit at healthy cohesion, co-located with a fuel dump (so
    it CAN afford the 2x-CPA dash -- the audit's own 'the bug bites units that can fund the
    excess' case) and marching toward a distant assembly hex, must not be ordered a destination
    that predicts Cohesion <=-17. `held=True` skips the (deliberately ungated, owner-ruled)
    one-time railhead CLAIM hop and exercises the general march the bug lives in."""
    assembly = (21, 0)                              # 42 CP away: the exact -17 boundary case
    u = _unit("2-Armd-Cruiser", side=Side.ALLIED, cpa=25, cohesion=0, hex_=(0, 0),
             mobility=Mobility.MOTORIZED)
    dump = SupplyUnit("CW-Dump", Side.ALLIED, (0, 0), ammo=100, fuel=9999)
    state = _state([u], target_hex=assembly, supplies=[dump])
    pol = CampaignCommonwealthPolicy()

    orders = pol._march(state, Side.ALLIED, [u], assembly, held=True)

    assert orders, "a healthy unit should still march -- just not all the way into the floor"
    order = next(o for o in orders if o.unit_id == u.id)
    reach = tactics.reachable_for(state, u, frozenset(), frozenset())
    predicted = u.cohesion - tactics.voluntary_overage_dp(state, u, reach[order.to])
    assert predicted > tactics.SURRENDER_FLOOR
    assert order.to != assembly, "the full 42-CP dash straight to the assembly must be refused"


def test_battered_reserve_is_not_frozen_by_the_march():
    """Companion to the -16 unit test, at the policy layer: a unit already battered (-16) but
    still above the hard -26 move ban gets a real, CPA-respecting order out of _march, not
    silence -- husbanding removes only the over-CPA candidates."""
    assembly = (21, 0)
    u = _unit("Battered-Recce", side=Side.ALLIED, cpa=25, cohesion=-16, hex_=(0, 0),
             mobility=Mobility.MOTORIZED)
    dump = SupplyUnit("CW-Dump", Side.ALLIED, (0, 0), ammo=100, fuel=9999)
    state = _state([u], target_hex=assembly, supplies=[dump])
    pol = CampaignCommonwealthPolicy()

    orders = pol._march(state, Side.ALLIED, [u], assembly, held=True)

    assert orders and orders[0].unit_id == u.id
    reach = tactics.reachable_for(state, u, frozenset(), frozenset())
    assert reach[orders[0].to] <= u.cpa, "a -16 unit may only take a CPA-respecting (0-overage) step"
