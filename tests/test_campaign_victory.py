"""C1-4: the campaign victory conditions (rule 64.7). Each clause tested in isolation --
the 64.71 Alexandria+Cairo auto-win, annihilation, the 64.73 geographic tally, and the
64.76 ratio grading -- on hand-built board states.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords
from game.campaign_victory import CampaignVictory, grade
from game.events import Phase, Side
from game.movement import TerrainMap
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain

ALEX = ("E3613", "E3714")
CAIRO = ("E1730", "E1829", "E1830", "E1930", "E1931")


class _R:
    """Minimal engine-run stand-in: CampaignVictory only reads r.state."""

    def __init__(self, state):
        self.state = state


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


def _unit(uid: str, side: Side, label: str, *, combat: bool = True, strength: int = 5) -> Unit:
    return Unit(uid, side, _ax(label), (StepRecord("inf", strength),),
                mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=3, dca=3,
                is_combat=combat)


def _state(units, *, supplied: bool = True) -> GameState:
    # C3-3: a holder must trace supply (rule 64.73). By default co-locate a dump with each
    # combat unit so the tally / auto-win tests exercise OCCUPATION; supplied=False strands the
    # units (no dump) to test the supply gate itself. Terrain carries the unit hexes so the
    # cpa/2 trace (game.supply.reachable_supplies) can reach a co-located dump.
    terrain = {u.hex: Terrain.CLEAR for u in units}
    supplies = (tuple(SupplyUnit(f"D-{u.id}", u.side, u.hex, ammo=999, fuel=999)
                      for u in units if u.is_combat) if supplied else ())
    return GameState(turn=111, max_turns=111, phase=Phase.RECORD, active_side=Side.SYSTEM,
                     seed=1, weather="normal", vp=VP(), terrain=TerrainMap(terrain=terrain),
                     control={}, units=tuple(units), target_hex=(0, 0), supplies=supplies,
                     consumed={}, initial_supply={})


# --- 64.76 ratio grading -------------------------------------------------------

def test_grade_draw_on_equal():
    assert grade(200, 200)[0] is None
    assert grade(0, 0)[0] is None


def test_grade_marginal_decisive_smashing():
    assert grade(140, 100)[0] is Side.AXIS and "Marginal" in grade(140, 100)[1]   # 1.4:1
    assert grade(200, 100)[0] is Side.AXIS and "Decisive" in grade(200, 100)[1]   # 2.0:1
    assert grade(300, 100)[0] is Side.AXIS and "Smashing" in grade(300, 100)[1]   # 3.0:1


def test_grade_boundaries_are_inclusive():
    assert "Marginal" in grade(150, 100)[1]    # exactly 1.5:1 -> Marginal
    assert "Decisive" in grade(250, 100)[1]    # exactly 2.5:1 -> Decisive


def test_grade_shutout_is_smashing():
    winner, reason = grade(0, 100)
    assert winner is Side.ALLIED and "Smashing" in reason


# --- 64.73 geographic tally ----------------------------------------------------

def test_geographic_tally_scores_occupied_cities():
    cv = CampaignVictory()
    # Axis holds Tobruk (200), Commonwealth holds Derna (50 cwlth).
    winner, reason = cv.decide(_R(_state([
        _unit("A1", Side.AXIS, "C4807"),
        _unit("C1", Side.ALLIED, "B5925"),
    ])))
    assert winner is Side.AXIS                 # 200 vs 50 -> 4:1
    assert "Smashing" in reason and "200-50" in reason


def test_noncombat_and_empty_do_not_occupy():
    cv = CampaignVictory()
    # A non-combat unit on Tobruk scores nothing; nobody else holds a city -> draw.
    winner, _ = cv.decide(_R(_state([_unit("A1", Side.AXIS, "C4807", combat=False)])))
    assert winner is None


def test_stranded_unit_does_not_occupy():
    # C3-3 (rule 64.73 quality-test): a combat unit on a city that cannot trace supply has
    # outrun its logistics and scores nothing -- the same unit, supplied, holds Tobruk.
    cv = CampaignVictory()
    assert cv.decide(_R(_state([_unit("A1", Side.AXIS, "C4807")], supplied=False)))[0] is None
    assert cv.decide(_R(_state([_unit("A1", Side.AXIS, "C4807")], supplied=True)))[0] is Side.AXIS


# --- 64.71 auto-win + annihilation --------------------------------------------

def test_autowin_requires_all_of_alexandria_and_cairo():
    cv = CampaignVictory()
    objective = ALEX + CAIRO
    axis_full = [_unit(f"A{i}", Side.AXIS, h) for i, h in enumerate(objective)]
    # Add a token Commonwealth unit so annihilation is not what fires.
    cw = [_unit("C0", Side.ALLIED, "C4807")]
    assert cv.check(_R(_state(axis_full + cw)))[0] is Side.AXIS

    # Drop one objective hex -> no auto-win (play on).
    assert cv.check(_R(_state(axis_full[:-1] + cw)))[0] is None


def test_annihilation_both_directions():
    cv = CampaignVictory()
    assert cv.check(_R(_state([_unit("A1", Side.AXIS, "C4807")])))[0] is Side.AXIS
    assert cv.check(_R(_state([_unit("C1", Side.ALLIED, "C4807")])))[0] is Side.ALLIED
