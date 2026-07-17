"""C1-4: the campaign victory conditions (rule 64.7). Each clause tested in isolation --
the 64.71 Alexandria+Cairo auto-win, its one-full-Game-Turn hold and its <=90 TRUCK-Movement-Point
line of supply back to a Tobruk/Tripoli-fed dump, the 64.73 geographic tally, and the 64.76 ratio
grading -- on hand-built board states.

64.7 defines no annihilation clause; the test that asserted the invented one now asserts
its absence (test_no_annihilation_victory).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords, supply
from game.campaign_victory import CampaignVictory, grade
from game.events import Control, Phase, Side
from game.hexmap import line
from game.movement import TerrainMap
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain

ALEX = ("E3613", "E3714")
CAIRO = ("E1730", "E1829", "E1830", "E1930", "E1931")
TOBRUK = "C4807"          # data/victory_cities.json supply_sources: the one 64.71 source ON THIS
                          # MAP (Tripoli's 8.85 gateway A2802 is transcribed as sea -- see
                          # game.campaign_victory's module docstring, THE TRIPOLI HOLE)
CLEAR_TRUCK_CP = 2        # [8.37] Terrain Effects Chart: a truck pays 2 CP to enter a clear hex


class _R:
    """Minimal engine-run stand-in: CampaignVictory reads r.state and remembers the 64.71
    hold clock in r.victory_scratch (engine._Run). Reassign `state` to advance the run."""

    def __init__(self, state):
        self.state = state
        self.victory_scratch: dict = {}


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


def _unit(uid: str, side: Side, where, *, combat: bool = True, strength: int = 5) -> Unit:
    return Unit(uid, side, _ax(where) if isinstance(where, str) else where,
                (StepRecord("inf", strength),),
                mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=3, dca=3,
                is_combat=combat)


def _state(units, *, supplied: bool = True, turn: int = 111, stage: int = 1,
           terrain: "dict | None" = None, supplies=None, control=None) -> GameState:
    # C3-3: a holder must trace supply (rule 64.73). By default co-locate a dump with each
    # combat unit so the tally / auto-win tests exercise OCCUPATION; supplied=False strands the
    # units (no dump) to test the supply gate itself. Terrain carries the unit hexes so the
    # cpa/2 trace (game.supply.reachable_supplies) can reach a co-located dump.
    terrain = dict(terrain or {})
    for u in units:
        terrain.setdefault(u.hex, Terrain.CLEAR)
    if supplies is None:
        supplies = (tuple(SupplyUnit(f"D-{u.id}", u.side, u.hex, ammo=999, fuel=999)
                          for u in units if u.is_combat) if supplied else ())
    return GameState(turn=turn, max_turns=111, phase=Phase.RECORD, active_side=Side.SYSTEM,
                     seed=1, weather="normal", vp=VP(), terrain=TerrainMap(terrain=terrain),
                     control=control or {}, units=tuple(units), target_hex=(0, 0),
                     supplies=tuple(supplies), consumed={}, initial_supply={}, stage=stage)


def _road_to_tobruk(*ends) -> dict:
    """Clear hexes along the straight lines from Tobruk to each of `ends` -- the open truck road
    64.71 needs behind a dump for it to be one "which in turn can be supplied from Tobruk ... in
    any way". Without it a synthetic board is a scatter of disconnected hexes and no dump on it is
    fed by anything."""
    return {h: Terrain.CLEAR for e in ends for h in line(_ax(TOBRUK), e)}


def _delta_board(*, turn: int, stage: int, hexes: tuple = ALEX + CAIRO,
                 supplied: bool = True, tobruk: "Side | None" = None,
                 control: "dict | None" = None) -> GameState:
    """The whole 64.71 board: the Axis standing on every hex of `hexes` (the entire objective by
    default) with a Supply Dump under each, and an open truck road running back from the Delta to
    Tobruk -- so the occupiers trace 0 truck-MP to a dump the source can fill, and the rule's supply
    clause is satisfied. `supplied=False` takes the dumps away; `tobruk=Side.ALLIED` puts an enemy
    battalion on the source hex; `control` sets the 56.15 control of hexes.

    Two things this board is NOT, and both were true of the board it replaces. It no longer stands a
    token Commonwealth unit on Tobruk -- that unit CAPTURES the 64.71 supply source and shuts it
    (56.15), which was harmless while the rule's supply clause was deferred and is the whole rule
    now. And its hexes are no longer a disconnected scatter: 64.71 is a question about a ROAD."""
    axis = [_unit(f"A{i}", Side.AXIS, h) for i, h in enumerate(hexes)]
    units = axis + ([_unit("C0", Side.ALLIED, TOBRUK)] if tobruk == Side.ALLIED else [])
    return _state(units, turn=turn, stage=stage, supplied=supplied, control=control,
                  terrain=_road_to_tobruk(*(u.hex for u in axis)))


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
    # 64.71's OTHER half: the occupying units must trace a line of supply of <=90 truck Movement
    # Points back to a Supply Dump the source can fill. A Delta garrison with no dump behind it
    # traces nothing, so it never starts the hold clock -- it can sit in Alexandria for the rest of
    # the war and win nothing. (This used to test the 64.73 cpa/2 quality-test, which stood in for
    # the truck-MP line while that was deferred. Same thesis, the rule's own line.)
    cv, r = CampaignVictory(), _R(_delta_board(turn=5, stage=1, supplied=False))
    for turn, stage in ((5, 2), (5, 3), (6, 1)):
        assert cv.check(r)[0] is None
        r.state = _delta_board(turn=turn, stage=stage, supplied=False)
    assert cv.check(r)[0] is None                          # a full Game-Turn on: still nothing


def test_a_delta_dump_that_tobruk_cannot_fill_wins_nothing():
    # The dump under the spearhead is not enough. 64.71 wants "a Supply Dump WHICH IN TURN CAN BE
    # SUPPLIED from Tobruk or Tripoli in any way" -- so a depot the Axis is standing on, with no
    # road home, is a heap of supplies in the sand and not a line of supply. Same board as the
    # winning one but with the road to Tobruk taken away.
    axis = [_unit(f"A{i}", Side.AXIS, h) for i, h in enumerate(ALEX + CAIRO)]
    cv, r = CampaignVictory(), _R(_state(axis, turn=5, stage=1))    # no _road_to_tobruk terrain
    for turn, stage in ((5, 2), (5, 3), (6, 1)):
        assert cv.check(r)[0] is None
        r.state = _state(axis, turn=turn, stage=stage)
    assert cv.check(r)[0] is None


def test_the_commonwealth_holding_tobruk_denies_the_delta_auto_win():
    # 56.15, and it is the campaign in one line: a harbour whose hex the enemy holds receives no
    # convoy, so it fills no dump behind it, so no dump behind it is one the Axis can trace to for
    # 64.71. The Panzerarmee can stand in Alexandria and Cairo for a full Game-Turn -- and win
    # nothing at all, because the Eighth Army is sitting on its source four hundred miles back.
    cv, r = CampaignVictory(), _R(_delta_board(turn=5, stage=1, tobruk=Side.ALLIED))
    for turn, stage in ((5, 2), (5, 3), (6, 1), (6, 2), (6, 3)):
        assert cv.check(r)[0] is None
        r.state = _delta_board(turn=turn, stage=stage, tobruk=Side.ALLIED)
    assert cv.check(r)[0] is None
    # ...and the identical board with Tobruk free is the win, so it is the SOURCE that denied it.
    cv2, r2 = CampaignVictory(), _R(_delta_board(turn=5, stage=1))
    for turn, stage in ((5, 2), (5, 3), (6, 1)):
        cv2.check(r2)
        r2.state = _delta_board(turn=turn, stage=stage)
    assert cv2.check(r2)[0] is Side.AXIS


def test_an_enemy_controlled_tobruk_denies_the_delta_auto_win():
    # The 56.15 test is of CONTROL, not of bodies: the Commonwealth takes Tobruk and marches on,
    # leaving the hex empty behind it. The harbour is still theirs (engine._record_control), so it
    # still supplies nobody -- the Axis road home ends at a quay it does not own.
    control = {_ax(TOBRUK): Control.ALLIED}
    cv, r = CampaignVictory(), _R(_delta_board(turn=5, stage=1, control=control))
    for turn, stage in ((5, 2), (5, 3), (6, 1), (6, 2), (6, 3)):
        assert cv.check(r)[0] is None
        r.state = _delta_board(turn=turn, stage=stage, control=control)
    assert cv.check(r)[0] is None


# --- 64.71/64.72: the truck-MP line of supply itself ----------------------------

def _road_hex(n: int):
    """`n` hexes along the straight clear road east from Tobruk, the 64.71 supply source."""
    q, r = _ax(TOBRUK)
    return (q + n, r)


def _road_board(unit_at: int, *, dump_at: int = 0, length: int = 60,
                dump_id: str = "AX-Dump", **dump_kw) -> GameState:
    """A straight clear road `length` hexes long running east out of Tobruk, and nothing else on
    the map: an Axis battalion `unit_at` hexes along it, one Axis dump `dump_at` hexes along it.

    A truck pays 2 CP to enter a clear hex ([8.37]), so the line of supply from the unit to the dump
    is exactly 2 x |unit_at - dump_at| Truck Movement Points and the arithmetic in these tests is the
    chart's, not a fit. The battalion is FOOT and traces by TRUCK anyway -- 64.71 measures the convoy
    route, not the boots (supply.truck_trace_reach)."""
    dump_kw.setdefault("ammo", 999)
    dump_kw.setdefault("fuel", 999)
    return _state([_unit("A1", Side.AXIS, _road_hex(unit_at))],
                  terrain={_road_hex(i): Terrain.CLEAR for i in range(length + 1)},
                  supplies=[SupplyUnit(dump_id, Side.AXIS, _road_hex(dump_at), **dump_kw)])


def test_ninety_truck_movement_points_is_the_boundary():
    # 64.71: "that line is 90 movement points by truck OR LESS". 45 clear hexes at the chart's 2 CP
    # is exactly 90 and passes; one hex further is 92 and does not.
    cv = CampaignVictory()
    assert 45 * CLEAR_TRUCK_CP == supply.TRUCK_MP_64_71
    s = _road_board(45)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is True
    s = _road_board(46)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is False


def test_sixty_truck_movement_points_is_the_boundary_for_64_72():
    # The same trace at 64.72's tighter budget -- the Commonwealth's automatic win asks it of every
    # Axis combat unit from Game-Turn 35. 30 clear hexes = 60 exactly; 31 = 62.
    cv = CampaignVictory()
    assert 30 * CLEAR_TRUCK_CP == supply.TRUCK_MP_64_72
    s = _road_board(30)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_72) is True
    s = _road_board(31)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_72) is False


def test_the_dump_leg_home_carries_no_budget():
    # The two legs are budgeted differently and that IS the rule. The unit's leg is capped at 90;
    # the dump's leg back to the harbour is "in any way" -- uncapped. So a battalion 2 hexes from a
    # dump that is itself 120 truck-MP down the road from Tobruk traces fine: 4 MP, not 124.
    cv = CampaignVictory()
    s = _road_board(62, dump_at=60, length=62)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is True


def test_an_empty_dump_still_carries_the_line():
    # "a Supply Dump which in turn CAN BE SUPPLIED from Tobruk or Tripoli" is a question about the
    # road, not about the stock in the depot today -- so an empty depot on an open road is exactly
    # the supply line the rule means. (game.state.active_supplies, the 32.16 DRAW list, drops an
    # empty dump; this trace must not read it.)
    cv = CampaignVictory()
    s = _road_board(10, ammo=0, fuel=0, stores=0, water=0)
    assert s.supplies[0].empty and not s.active_supplies(Side.AXIS)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is True


def test_a_well_is_not_a_supply_dump():
    # game.wells models a water source as a SupplyUnit and seeds one ON Alexandria and five ON
    # Cairo. Read as 64.71 Supply Dumps they would hand every Delta occupier a 0-MP trace to a
    # "dump" it is standing on and the rule's supply clause would be satisfied by the geography of
    # the objective itself. A well is a hole in the ground (52.11): no lorry from Tobruk fills one.
    cv = CampaignVictory()
    s = _road_board(10, dump_at=10, dump_id="AX-Well-Alexandria", water=999)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is False
    s = _road_board(10, dump_at=10, dump_id="AX-Dump", water=999)      # the same counter, a dump
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is True


def test_a_dummy_dump_is_not_a_supply_dump():
    # 32.18: a dummy is a bluff counter with nothing in it and nothing behind it.
    cv = CampaignVictory()
    s = _road_board(10, is_dummy=True)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is False


def test_an_enemy_across_the_road_cuts_the_line():
    # 32.16, the blocking every trace in game.supply reads: the line of supply may not run through
    # a hex an enemy unit stands on. One Commonwealth battalion on the road between the spearhead
    # and its dump, and the spearhead is on the end of a rope -- with the dump 4 MP away.
    cv = CampaignVictory()
    s = _road_board(10, dump_at=8)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is True
    cut = _state([_unit("A1", Side.AXIS, _road_hex(10)), _unit("C1", Side.ALLIED, _road_hex(9))],
                 terrain={_road_hex(i): Terrain.CLEAR for i in range(61)},
                 supplies=[SupplyUnit("AX-Dump", Side.AXIS, _road_hex(8), ammo=999, fuel=999)])
    assert cv.axis_traces_within(cut, cut.units[0], supply.TRUCK_MP_64_71) is False


# --- 56.15: WHAT SHUTS THE SOURCE. Capture, and only capture. -------------------

def _siege_board(*besiegers) -> GameState:
    """The road board of _road_board(10, dump_at=8) -- an Axis battalion 10 hexes out, its dump at
    8, both fed down the road from Tobruk -- with Commonwealth units added at `besiegers`.

    _road_hex(-1) is adjacent to TOBRUK and NOT adjacent to _road_hex(1), so a stack there puts the
    quay in an enemy ZOC without touching the road east of it. TWO battalions, because rule 10.11
    exerts a ZOC only from more than one Stacking Point in the hex -- one lone battalion projects
    nothing and would test nothing."""
    cw = [_unit(f"C{i}", Side.ALLIED, h) for i, h in enumerate(besiegers)]
    return _state([_unit("A1", Side.AXIS, _road_hex(10))] + cw,
                  terrain={_road_hex(i): Terrain.CLEAR for i in range(-1, 61)},
                  supplies=[SupplyUnit("AX-Dump", Side.AXIS, _road_hex(8), ammo=999, fuel=999)])


def test_an_enemy_beside_the_source_does_not_shut_it():
    # 🔴 THE REGRESSION, and it was a 64.72 catastrophe. The source gate used to shut Tobruk when
    # the quay stood in an unnegated enemy ZOC, citing 56.15 -- whose whole text is "a convoy
    # scheduled to arrive at a port that is CAPTURED by the Commonwealth is cancelled. It never
    # sails." Standing NEXT TO a port does not capture it, and no rule in the book shuts a port for
    # adjacency. MEASURED on the real GT1 campaign board, the invented gate took the Axis from 13
    # fed dumps to 0 and all 96 of its combat units out of the 60-MP trace -- so the turn 64.72 is
    # wired, one Commonwealth stack parked outside an Axis-held, empty Tobruk would have handed the
    # Commonwealth the war at Game-Turn 35.
    cv = CampaignVictory()
    besieged = _siege_board(_road_hex(-1), _road_hex(-1))
    assert _ax(TOBRUK) in supply.trace_blocked(besieged, Side.AXIS)     # the quay IS in enemy ZOC
    assert besieged.control_of(_ax(TOBRUK)) is not Control.ALLIED       # and is NOT captured
    assert cv.axis_traces_within(besieged, besieged.units[0], supply.TRUCK_MP_64_71) is True


def test_an_enemy_standing_on_the_source_shuts_it():
    # The other half of the same rule: a combat unit ON the quay HAS captured it (56.15), and a
    # captured port cancels the convoy, so it fills no dump behind it and no dump behind it carries
    # a 64.71 line. This is the campaign in one line -- the Panzerarmee can stand in Alexandria and
    # Cairo for a full Game-Turn and win nothing, because the Eighth Army is sitting on its source
    # four hundred miles back.
    cv = CampaignVictory()
    taken = _siege_board(_ax(TOBRUK))
    assert cv.axis_traces_within(taken, taken.units[0], supply.TRUCK_MP_64_71) is False


def test_enemy_control_of_the_source_shuts_it_with_no_one_standing_there():
    # Capture OUTLIVES the capturing column, which is what a control marker is for: Tobruk does not
    # revert to the Axis because the garrison that took it marched on. 56.15 asks whether the port
    # is captured, not whether anyone is currently standing in it.
    cv = CampaignVictory()
    s = _road_board(10, dump_at=8)
    assert cv.axis_traces_within(s, s.units[0], supply.TRUCK_MP_64_71) is True
    flipped = _state([_unit("A1", Side.AXIS, _road_hex(10))],
                     terrain={_road_hex(i): Terrain.CLEAR for i in range(61)},
                     supplies=[SupplyUnit("AX-Dump", Side.AXIS, _road_hex(8), ammo=999, fuel=999)],
                     control={_ax(TOBRUK): Control.ALLIED})
    assert not flipped.units_at(_ax(TOBRUK))
    assert cv.axis_traces_within(flipped, flipped.units[0], supply.TRUCK_MP_64_71) is False


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
