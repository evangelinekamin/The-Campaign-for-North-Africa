"""C1-4: the campaign victory conditions (rule 64.7). Each clause tested in isolation --
the 64.71 Alexandria+Cairo auto-win and its one-full-Game-Turn hold, the 64.73 geographic
tally, and the 64.76 ratio grading -- on hand-built board states.

64.7 defines no annihilation clause; the test that asserted the invented one now asserts
its absence (test_no_annihilation_victory).
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
    """Minimal engine-run stand-in: CampaignVictory reads r.state and remembers the 64.71
    hold clock in r.victory_scratch (engine._Run). Reassign `state` to advance the run."""

    def __init__(self, state):
        self.state = state
        self.victory_scratch: dict = {}


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


def _unit(uid: str, side: Side, label: str, *, combat: bool = True, strength: int = 5) -> Unit:
    return Unit(uid, side, _ax(label), (StepRecord("inf", strength),),
                mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=3, dca=3,
                is_combat=combat)


def _state(units, *, supplied: bool = True, turn: int = 111, stage: int = 1) -> GameState:
    # C3-3: a holder must trace supply (rule 64.73). By default co-locate a dump with each
    # combat unit so the tally / auto-win tests exercise OCCUPATION; supplied=False strands the
    # units (no dump) to test the supply gate itself. Terrain carries the unit hexes so the
    # cpa/2 trace (game.supply.reachable_supplies) can reach a co-located dump.
    terrain = {u.hex: Terrain.CLEAR for u in units}
    supplies = (tuple(SupplyUnit(f"D-{u.id}", u.side, u.hex, ammo=999, fuel=999)
                      for u in units if u.is_combat) if supplied else ())
    return GameState(turn=turn, max_turns=111, phase=Phase.RECORD, active_side=Side.SYSTEM,
                     seed=1, weather="normal", vp=VP(), terrain=TerrainMap(terrain=terrain),
                     control={}, units=tuple(units), target_hex=(0, 0), supplies=supplies,
                     consumed={}, initial_supply={}, stage=stage)


def _delta_board(*, turn: int, stage: int, hexes: tuple = ALEX + CAIRO,
                 supplied: bool = True) -> GameState:
    """The Axis standing on every hex of `hexes` (the whole 64.71 objective by default), plus
    a token Commonwealth unit on Tobruk, at Game-Turn `turn` Operations Stage `stage`."""
    axis = [_unit(f"A{i}", Side.AXIS, h) for i, h in enumerate(hexes)]
    return _state(axis + [_unit("C0", Side.ALLIED, "C4807")],
                  turn=turn, stage=stage, supplied=supplied)


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


# --- 64.71 auto-win: the whole Delta, held for one full Game-Turn --------------

def test_autowin_requires_all_of_alexandria_and_cairo():
    # One Delta hex short is no occupation at all, so the 64.71 clock never starts: a whole
    # Game-Turn of checks still wins nothing. (This used to assert that the FULL objective wins
    # on the instant it is occupied. It does not -- 64.71 wants it held for one full Game-Turn,
    # which is what test_autowin_needs_the_delta_held_for_one_full_game_turn now pins.)
    short = (ALEX + CAIRO)[:-1]                            # one Delta hex still Commonwealth
    cv, r = CampaignVictory(), _R(_delta_board(turn=5, stage=1, hexes=short))
    for turn, stage in ((5, 2), (5, 3), (6, 1), (6, 2)):
        assert cv.check(r)[0] is None
        r.state = _delta_board(turn=turn, stage=stage, hexes=short)
    assert cv.check(r)[0] is None                          # a full Game-Turn on: still nothing


def test_autowin_needs_the_delta_held_for_one_full_game_turn():
    # 64.71: the Axis "occupies all hexes of Alexandria and Cairo FOR ONE FULL GAME-TURN". The
    # instant of occupation wins nothing -- it starts the clock. A Game-Turn is three Operations
    # Stages (5.1) and victory is tested in each one's Record Phase, so the win lands on the
    # fourth consecutive check: exactly one full Game-Turn of held ground later.
    cv, r = CampaignVictory(), _R(_delta_board(turn=5, stage=1))
    assert cv.check(r)[0] is None                          # GT5.1: the Delta falls. No win.
    for stage in (2, 3):
        r.state = _delta_board(turn=5, stage=stage)
        assert cv.check(r)[0] is None                      # still inside the first Game-Turn
    r.state = _delta_board(turn=6, stage=1)
    winner, reason = cv.check(r)
    assert winner is Side.AXIS and "64.71" in reason and "Game-Turn" in reason


def test_a_break_in_the_occupation_restarts_the_hold():
    # The Commonwealth's answer to 64.71: it has one full Game-Turn to throw the Axis out of a
    # single Delta hex, and doing so does not merely delay the win -- it restarts the clock.
    cv, r = CampaignVictory(), _R(_delta_board(turn=5, stage=1))
    assert cv.check(r)[0] is None
    r.state = _delta_board(turn=5, stage=2, hexes=(ALEX + CAIRO)[:-1])   # one hex retaken
    assert cv.check(r)[0] is None
    for turn, stage in ((5, 3), (6, 1), (6, 2)):           # re-taken at 5.3: the clock restarts
        r.state = _delta_board(turn=turn, stage=stage)
        assert cv.check(r)[0] is None
    r.state = _delta_board(turn=6, stage=3)                 # one full Game-Turn after 5.3
    assert cv.check(r)[0] is Side.AXIS


def test_an_unsupplied_holder_does_not_run_the_hold_clock():
    # The hold is of OCCUPATION as 64.73 defines it (_occupier): a holder that cannot trace
    # supply occupies nothing, so a stranded Delta garrison never starts the 64.71 clock.
    cv, r = CampaignVictory(), _R(_delta_board(turn=5, stage=1, supplied=False))
    for turn, stage in ((5, 2), (5, 3), (6, 1)):
        assert cv.check(r)[0] is None
        r.state = _delta_board(turn=turn, stage=stage, supplied=False)
    assert cv.check(r)[0] is None                          # a full Game-Turn on: still nothing


# --- 64.7 defines no annihilation clause ---------------------------------------

def test_no_annihilation_victory():
    # The invented "victory by annihilation" is gone: rule 64.7 has no such clause. A board on
    # which one side has no living unit left ends nothing -- the campaign runs its full span and
    # is settled on the 64.73 tally, which is where a wiped-out side loses anyway (it holds no
    # city). This test asserted the invention in both directions; it now asserts its absence.
    cv = CampaignVictory()
    assert cv.check(_R(_state([_unit("A1", Side.AXIS, "C4807")])))[0] is None
    assert cv.check(_R(_state([_unit("C1", Side.ALLIED, "C4807")])))[0] is None
    # ...and the tally still names the survivor: the lone Axis unit holds Tobruk, 200-0.
    winner, reason = cv.decide(_R(_state([_unit("A1", Side.AXIS, "C4807")])))
    assert winner is Side.AXIS and "200-0" in reason
