"""C1-4: the campaign victory conditions (rule 64.7). Each clause tested in isolation --
the 64.71 Alexandria+Cairo auto-win, its one-full-Game-Turn hold and its <=90 TRUCK-Movement-Point
line of supply back to a Tobruk/Tripoli-fed dump, the 64.73 geographic tally, and the 64.76 ratio
grading -- on hand-built board states.

64.7 defines no annihilation clause; the test that asserted the invented one now asserts
its absence (test_no_annihilation_victory).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords, movement, supply
from game.campaign_victory import CampaignVictory, grade
from game.events import CONTROL_OF, Control, Phase, Side
from game.hexmap import line
from game.movement import TerrainMap
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain

ALEX = ("E3613", "E3714")
CAIRO = ("E1730", "E1829", "E1830", "E1930", "E1931")
TOBRUK = "C4807"          # data/victory_cities.json supply_sources: the FIRST of 64.71's two named
TRIPOLI = "A2802"         # sources; the second is Tripoli's 8.85 on-map gateway, land since the
                          # TRIPOLI HOLE was closed (game.cna_map._RULEBOOK_LAND). These synthetic
                          # boards carry only the hexes they name, so Tripoli is simply absent from
                          # their terrain and Tobruk is the only source that can feed them.
CLEAR_TRUCK_CP = 2        # [8.37] Terrain Effects Chart: a truck pays 2 CP to enter a clear hex
GT_64_72 = 35             # 64.72: "Starting with the first OpStage of Game-Turn 35"


class _R:
    """Minimal engine-run stand-in: CampaignVictory reads r.state and remembers the 64.71
    hold clock in r.victory_scratch (engine._Run). Reassign `state` to advance the run."""

    def __init__(self, state):
        self.state = state
        self.victory_scratch: dict = {}


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


def _unit(uid: str, side: Side, where, *, combat: bool = True, strength: int = 5,
          arrival_turn: int = 0) -> Unit:
    # arrival_turn defaults 0 -- every unit on these boards is ON THE MAP unless a test says
    # otherwise. That default is why the 64.72 witnesses could not see the roster/on-map bug:
    # see test_64_72_ignores_axis_reinforcements_that_have_not_arrived, which sets it.
    return Unit(uid, side, _ax(where) if isinstance(where, str) else where,
                (StepRecord("inf", strength),),
                mobility=Mobility.FOOT, cpa=10, stacking_points=1, oca=3, dca=3,
                is_combat=combat, arrival_turn=arrival_turn)


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


# --- 64.72: the Commonwealth's automatic win from Game-Turn 35 ------------------

def _cut_board(turn: int, *, tracing: tuple = (), stranded: tuple = (40, 45, 50),
               stage: int = 1) -> GameState:
    """The 64.72 board: one Axis Supply Dump on the Tobruk quay, fed by the source, and Axis combat
    battalions strung out along the clear road east of it. `stranded` are hexes-along-the-road for
    units OUTSIDE the 60-MP line (>30 hexes at the chart's 2 CP); `tracing` are units inside it.

    So the whole board turns on one question and nothing else: is there an Axis combat unit within
    60 truck Movement Points of a dump the Tobruk source can fill?"""
    units = [_unit(f"A{n}", Side.AXIS, _road_hex(n)) for n in (*stranded, *tracing)]
    return _state(units, turn=turn, stage=stage,
                  terrain={_road_hex(i): Terrain.CLEAR for i in range(61)},
                  supplies=[SupplyUnit("AX-Dump", Side.AXIS, _road_hex(0), ammo=999, fuel=999)])


def test_64_72_fires_when_the_axis_line_is_cut():
    # 🔴 THE HEADLINE: the Commonwealth's PRINCIPAL win condition, and the campaign was played
    # without it. 64.72 -- "Starting with the first OpStage of Game-Turn 35, if there are no Axis
    # Combat units that can trace a line of supply of 60 Movement Points (Truck) to a Supply Dump
    # and thence to Tobruk or Tripoli ... the Commonwealth wins the game automatically."
    # Three Axis battalions at 40/45/50 hexes out are 80/90/100 truck-MP from the only fed dump --
    # every one of them outside the 60. Axis supply has collapsed and the war ends on the spot.
    cv = CampaignVictory()
    winner, reason = cv.check(_R(_cut_board(GT_64_72)))
    assert winner is Side.ALLIED
    assert "64.72" in reason and "Commonwealth" in reason


def test_64_72_does_not_fire_while_one_axis_unit_still_traces():
    # The companion, and it is the rule's own word: "there are NO Axis Combat units that can trace".
    # ONE is enough to deny the Commonwealth the war. The identical cut board plus a single
    # battalion 30 hexes out -- exactly 60 truck-MP, the boundary -- and the Panzerarmee fights on
    # with three of its four battalions still stranded in the desert.
    cv = CampaignVictory()
    assert cv.check(_R(_cut_board(GT_64_72, tracing=(30,))))[0] is None
    # ...and it is that one unit's line that is holding the war open: take it one hex further out
    # (62 truck-MP, outside the 60) and the same board is a Commonwealth victory.
    assert cv.check(_R(_cut_board(GT_64_72, tracing=(31,))))[0] is Side.ALLIED


def test_64_72_is_gated_on_game_turn_35():
    # "STARTING WITH THE FIRST OPSTAGE OF GAME-TURN 35". The Axis may be cut off for the first 34
    # Game-Turns and lose nothing by it -- the rule is not live yet. It bites from the first check
    # of GT35 (the engine tests victory in the Record Phase of every Operations Stage, so the first
    # OpStage of GT35 is stage 1), and every stage thereafter.
    cv = CampaignVictory()
    assert cv.check(_R(_cut_board(GT_64_72 - 1, stage=3)))[0] is None      # GT34: not yet
    assert cv.check(_R(_cut_board(GT_64_72, stage=1)))[0] is Side.ALLIED   # GT35.1: the first check
    assert cv.check(_R(_cut_board(GT_64_72 + 20)))[0] is Side.ALLIED       # and it stays live


def test_64_72_needs_a_dump_the_source_can_actually_fill():
    # 64.72 traces "to a Supply Dump and thence to Tobruk or Tripoli AS PER CASE 64.71" -- so it
    # inherits 64.71's far leg whole, and a dump with no road home is not a dump this rule counts.
    # The units are parked ON their depot (0 truck-MP away) and it wins the Axis nothing, because
    # the road back to Tobruk has been taken off the board.
    cv = CampaignVictory()
    stranded = _state([_unit("A1", Side.AXIS, _road_hex(40))], turn=GT_64_72,
                      terrain={_road_hex(i): Terrain.CLEAR for i in range(40, 61)},
                      supplies=[SupplyUnit("AX-Dump", Side.AXIS, _road_hex(40), ammo=999, fuel=999)])
    assert cv.check(_R(stranded))[0] is Side.ALLIED


def test_64_72_ignores_axis_reinforcements_that_have_not_arrived():
    # 🔴 THE REGRESSION, and it ran the UNSAFE way: it made the Commonwealth's PRINCIPAL win
    # condition fire LESS readily than the book -- a victory silently DENIED. _axis_combat_units
    # read state.units, the FULL ROSTER, so Axis units that had not yet entered play (rule 20
    # reinforcements, pre-placed at their scheduled entry hexes) were counted as "Axis Combat units
    # that can trace", and game.supply has no arrival_turn awareness anywhere -- truck_trace_reach
    # traced happily from a unit that was not on the map.
    #
    # 64.72's own qualifier is the answer, and it is a word this port had dropped from the quote:
    # "...to Tobruk or Tripoli as per case 64.71, GAME-MAP, the Commonwealth wins the game
    # automatically" (scan, PDF page 88 / printed page 37). The units under test are the ones ON THE
    # GAME-MAP -- state.living, which is state.on_map: alive AND turn >= arrival_turn.
    #
    # The board: the cut board, plus one Axis battalion sitting ON the fed dump -- 0 truck-MP away,
    # as inside the 60 as a unit can be -- that does not arrive until GT40. The Axis has nothing on
    # the map that can trace, so the Commonwealth wins; the ghost in the reinforcement queue must
    # not hold the war open. MEASURED end to end on the real scenario.campaign() board before the
    # fix, in 64.72's OWN scenario (the Axis collapsed onto Tripolitania at GT35): 31 unarrived
    # units parked ~20 hexes from the A2802 gateway kept _line_is_cut False with ZERO Axis combat
    # units in play.
    cv = CampaignVictory()
    board = _cut_board(GT_64_72)
    ghost = _unit("A-Reinf", Side.AXIS, _road_hex(0), arrival_turn=GT_64_72 + 5)
    with_ghost = _state([*board.units, ghost], turn=GT_64_72,
                        terrain=dict(board.terrain.terrain), supplies=list(board.supplies))
    assert not with_ghost.on_map(ghost), "the fixture must actually hold an unarrived unit"
    assert ghost not in cv._axis_combat_units(with_ghost), "64.72 tests the game-map, not the roster"
    assert cv.check(_R(with_ghost))[0] is Side.ALLIED
    # ...and the SAME unit, once it has arrived, holds the war open from the same hex. That is the
    # control: what is being tested is arrival, not the unit, the hex or the trace.
    arrived = _state([*board.units, _unit("A-Reinf", Side.AXIS, _road_hex(0), arrival_turn=GT_64_72)],
                     turn=GT_64_72, terrain=dict(board.terrain.terrain), supplies=list(board.supplies))
    assert cv.check(_R(arrived))[0] is None


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


# --- THE TRIPOLI HOLE: 64.72's second source, on the real campaign board ---------

def test_tripoli_is_a_supply_source_on_the_real_map():
    # 64.71/64.72 name TWO harbours, "Tobruk or Tripoli", and this map used to carry only Tobruk:
    # A2802 -- the hex 8.85 says a unit "must start that Operations Stage in", and the Road hex a
    # unit entering from the Tripolitania box is placed on -- colour-sampled as SEA.
    from game import cna_map
    tmap, _ = cna_map.load_sections("A")
    assert _ax(TRIPOLI) in tmap.terrain, "8.85's Tripolitania gateway must be land"
    assert {(s.hex, s.capturable) for s in CampaignVictory().supply_sources} == {
        (_ax(TOBRUK), True),        # an on-map port the Commonwealth can take -- 56.15 is live
        (_ax(TRIPOLI), False),      # the off-map box's gateway proxy -- 8.82 forbids its capture
    }


def test_the_commonwealth_cannot_capture_the_off_map_tripoli_box():
    # 🔴 THE SECOND "COMMONWEALTH WINS IF IT HOLDS ONE HEX", caught by a verifier one hex west of
    # the first. A2802 is a PROXY for the off-map Tripoli/Tunisia boxes, and it was fed to the same
    # 56.15 capture gate as Tobruk -- which made an UNCAPTURABLE source capturable. The book's
    # Tripoli cannot be taken: 8.81 puts the boxes off the western edge of Map A, and 8.82 says "No
    # Commonwealth land or sea unit may ever enter any of the boxes". A2802 is not Tripoli; it is an
    # ordinary desert road hex (8.85's gateway) the Commonwealth may walk onto, and walking onto it
    # captures nothing.
    #
    # MEASURED on the real GT1 board before the fix: Control.ALLIED on BOTH Tobruk and the gateway
    # took fed_dumps 13 -> 0 and _line_is_cut -> True, i.e. from GT35 one Commonwealth unit on one
    # far-west hex, with Tobruk taken, ended the war with every Axis combat unit alive and stocked.
    # A proxy may stand in for a hex; it may not inherit a rule the thing it proxies is exempt from.
    #
    # The Commonwealth can still SHUT the road by standing on it -- two battalions on the gateway
    # exert a ZOC (10.11) and take the Axis to 0 fed dumps (10.29). That block is the book's: it
    # needs a force, and the Axis can negate it (10.26) or drive it off. Capture needed neither.
    from dataclasses import replace as _replace

    from game import scenario
    st = scenario.campaign()
    cv = CampaignVictory()
    taken = _replace(st, control={**st.control, _ax(TOBRUK): Control.ALLIED,
                                  _ax(TRIPOLI): Control.ALLIED})
    assert cv.fed_dumps(taken, Side.AXIS), "8.82: the off-map box cannot be captured, so it feeds on"
    assert not cv._line_is_cut(taken), "holding the gateway hex is not a 64.72 Commonwealth win"


def test_losing_tobruk_does_not_hand_the_commonwealth_the_war():
    # 🔴 THE REGRESSION THIS RULE EXISTS TO AVOID, on the real GT1 campaign board. With Tripoli
    # missing, the Commonwealth CAPTURING Tobruk (56.15) was the whole Axis supply system: it took
    # the Axis from 13 fed dumps to 0 and EVERY ONE of its combat units out of the 60-MP trace, so
    # 64.72 handed the Commonwealth an automatic win at Game-Turn 35 -- off a coastline sampling
    # error, in the exact situation (Tobruk falls, January 1941) where the historical Axis fought on
    # out of Tripoli for two more years and retook Cyrenaica. That is not 64.72; it is "the
    # Commonwealth wins if it holds Tobruk", which the book does not contain.
    from dataclasses import replace as _replace

    from game import scenario
    st = scenario.campaign()
    cv = CampaignVictory()
    fallen = _replace(st, control={**st.control, _ax(TOBRUK): Control.ALLIED})
    assert cv.fed_dumps(fallen, Side.AXIS), "Tripoli must still feed the Axis with Tobruk gone"
    assert not cv._line_is_cut(fallen), "losing Tobruk alone must not collapse the 64.72 trace"


# --- 64.7 defines no annihilation clause ---------------------------------------

def test_no_annihilation_victory():
    # The invented "victory by annihilation" is gone: rule 64.7 has no such clause. A board on
    # which one side has no living unit left ends nothing -- the campaign runs its full span and
    # is settled on the 64.73 tally, which is where a wiped-out side loses anyway (it holds no
    # city). This test asserted the invention in both directions; it now asserts its absence.
    #
    # RESTATED when 64.72 landed, and the restatement is the point rather than a concession. The
    # invention was SYMMETRIC -- either side losing its last counter ended the war, on any turn, on
    # no rule at all. What the book actually gives is an ASYMMETRY, and the two halves are tested
    # here on the two boards that used to be one assertion each:
    #   * A wiped-out COMMONWEALTH ends nothing, ever. 64.71 is the Axis's only automatic win and
    #     it demands Alexandria and Cairo held for a full Game-Turn; there is no mirror of 64.72,
    #     so the Axis must still go and take the Delta. Turn 111 with the Commonwealth gone: None.
    #   * A wiped-out AXIS at GT35+ IS a Commonwealth win -- but under 64.72's own words, not under
    #     an annihilation clause. "There are no Axis Combat units that can trace" is satisfied
    #     trivially when there are no Axis Combat units. See CampaignVictory._line_is_cut, which
    #     flags the vacuous truth. Before GT35 the same board still ends nothing, and that is
    #     exactly what separates the rule from the invention: 64.72 has a date on it.
    cv = CampaignVictory()
    assert cv.check(_R(_state([_unit("A1", Side.AXIS, "C4807")])))[0] is None
    assert cv.check(_R(_state([_unit("C1", Side.ALLIED, "C4807")], turn=GT_64_72 - 1)))[0] is None
    assert cv.check(_R(_state([_unit("C1", Side.ALLIED, "C4807")])))[0] is Side.ALLIED   # GT111
    # ...and the tally still names the survivor: the lone Axis unit holds Tobruk, 200-0.
    winner, reason = cv.decide(_R(_state([_unit("A1", Side.AXIS, "C4807")])))
    assert winner is Side.AXIS and "200-0" in reason


# --- PASS B: the multi-source reversed-edge trace is byte-for-byte the per-unit trace ------------
# The 64.71/64.72 line-of-supply trace was INVERTED for speed: one reversed-edge Dijkstra seeded from
# the fed dumps (supply.tracing_hexes / movement.reverse_reachable) in place of a 60-or-90-MP forward
# Dijkstra per Axis combat unit, and truck_supply_line made a connectivity BFS (movement.connected).
# The byte-identity harness catches a MOVED verdict (a wrong trace fires an auto-win differently and
# shifts the event log), but it cannot see a verdict that only WOULD move on a board the panel never
# reaches. This is that extra gate: an A/B predicate-equality check that the optimized path returns the
# IDENTICAL result -- same tracing units, same _line_is_cut, same _delta_held -- as the original
# per-unit functions, which are kept unchanged (axis_traces_within / truck_trace_reach) for exactly it.

def _orig_truck_supply_line(cv, s, side):
    """The pre-optimization truck_supply_line body: a math.inf forward Dijkstra per still-open source,
    unioned. The reference the connectivity BFS (movement.connected) must reproduce as a set."""
    enemy_side = Side.ALLIED if side == Side.AXIS else Side.AXIS
    enemy = CONTROL_OF[enemy_side]
    held = frozenset(u.hex for u in s.living(enemy_side) if u.is_combat)
    blocked = supply.trace_blocked(s, side)
    line_ = set()
    for src in cv.supply_sources:
        if not s.terrain.exists(src.hex):
            continue
        if src.capturable and (s.control_of(src.hex) == enemy or src.hex in held):
            continue
        line_ |= movement.reachable(s.terrain, src.hex, math.inf, supply.SUPPLY_MOBILITY,
                                    blocked=blocked).keys()
    return frozenset(line_)


def _orig_line_is_cut(cv, s):
    """64.72 the pre-inversion way: the per-unit forward trace, short-circuited by any()."""
    fed = cv.fed_dumps(s, Side.AXIS)
    return not any(cv.axis_traces_within(s, u, supply.TRUCK_MP_64_72, fed)
                   for u in cv._axis_combat_units(s))


def _orig_delta_held(cv, s):
    """64.71's supply clause the pre-inversion way: per Delta hex, some occupier's forward trace."""
    occ = [cv._delta_occupiers(s, ax) for ax in cv.objective]
    if not all(occ):
        return False
    fed = cv.fed_dumps(s, Side.AXIS)
    return all(any(cv.axis_traces_within(s, u, supply.TRUCK_MP_64_71, fed) for u in us) for us in occ)


def _assert_trace_parity(cv, s):
    """The optimized victory trace equals the per-unit original on state `s`, in every particular:
    the connectivity set, the tracing verdict of every Axis combat unit at BOTH the 64.72 (60) and
    64.71 (90) budgets, and the two auto-win verdicts the whole campaign turns on."""
    for side in (Side.AXIS, Side.ALLIED):                       # (a) BFS == the math.inf Dijkstra union
        assert supply.truck_supply_line(s, side, cv.supply_sources) == _orig_truck_supply_line(cv, s, side)
    fed = cv.fed_dumps(s, Side.AXIS)
    units = cv._axis_combat_units(s)
    for budget in (supply.TRUCK_MP_64_72, supply.TRUCK_MP_64_71):   # (c) identical set of tracing units
        opt = supply.tracing_hexes(s, Side.AXIS, {u.hex for u in units}, fed, budget)
        for u in units:
            assert (u.hex in opt) is bool(cv.axis_traces_within(s, u, budget, fed)), (u.id, budget)
    assert cv._line_is_cut(s) == _orig_line_is_cut(cv, s)
    assert cv._delta_held(s) == _orig_delta_held(cv, s)


_PARITY_SEEDS = (1941, 4, 7, 2026, 99, 1)                       # >= 5 seeds, per the extra-gate spec


def test_trace_inversion_matches_the_per_unit_trace_on_live_campaign_boards():
    # (i) THE HEALTHY LIVE CAMPAIGN BOARD, on six seeds. This is where the START-HEX EXEMPTION bites
    # and where a naive reverse flood would silently move a verdict: the GT1 setup stacks Axis
    # battalions with the enemy they are fighting (the Maletti group on (24,76)), so their hexes are
    # enemy-OCCUPIED and thus in the trace blocking -- yet the forward trace floods OUT of a unit's own
    # start hex, so they trace, and the inverted path (which never ENTERS a blocked hex) must restore
    # that by hand. Measured: with the exemption, all 96 units agree; without it, (24,76) flips.
    cv = CampaignVictory()
    from game import scenario
    for seed in _PARITY_SEEDS:
        _assert_trace_parity(cv, scenario.campaign(seed=seed))


def test_trace_inversion_matches_the_per_unit_trace_on_a_cut_board():
    # (ii) A CONSTRUCTED BOARD WHERE 64.72 FIRES (the Axis line is cut) and the boards on either side
    # of it. The last is the exemption reproduced on a cut board and made LOAD-BEARING: an Axis unit
    # stacked under a lone Commonwealth unit (1 Stacking Point -> no ZOC, 10.11) sits on a blocked hex,
    # is the ONLY Axis unit that can still reach the dump behind it, and so is the single verdict the
    # whole 64.72 check turns on -- a broken exemption would drop it and hand the Commonwealth the war.
    cv = CampaignVictory()
    cut = _cut_board(GT_64_72)
    assert cv._line_is_cut(cut) is True                        # the headline: all units stranded > 60
    _assert_trace_parity(cv, cut)
    _assert_trace_parity(cv, _cut_board(GT_64_72, tracing=(20,)))   # one unit back inside 60: not cut
    stacked = _state([_unit("A-strand", Side.AXIS, _road_hex(40)),
                      _unit("A-stack", Side.AXIS, _road_hex(10)),
                      _unit("C-on-top", Side.ALLIED, _road_hex(10))],
                     turn=GT_64_72,
                     terrain={_road_hex(i): Terrain.CLEAR for i in range(61)},
                     supplies=[SupplyUnit("AX-Dump", Side.AXIS, _road_hex(0), ammo=999, fuel=999)])
    assert _road_hex(10) in supply.trace_blocked(stacked, Side.AXIS)          # the stacked hex IS blocked
    assert cv.axis_traces_within(stacked, stacked.units[1], supply.TRUCK_MP_64_72) is True  # yet it traces
    assert cv._line_is_cut(stacked) is False                  # so the line is NOT cut -- on that one unit
    _assert_trace_parity(cv, stacked)


def test_trace_inversion_matches_the_per_unit_trace_on_the_delta_board():
    # (iii) THE 64.71 BOARD -- the whole Delta occupied -- so _delta_held actually runs its <=90 trace
    # (on the cut/live boards above the Delta is Commonwealth, so it returns before the trace). Both a
    # fed board (the occupiers trace 0 MP to the dump under them) and one with Tobruk captured (56.15
    # shuts the only source, so nothing is fed and the clause fails) -- the optimized and original
    # paths must agree on each.
    cv = CampaignVictory()
    _assert_trace_parity(cv, _delta_board(turn=50, stage=1))
    _assert_trace_parity(cv, _delta_board(turn=50, stage=1, tobruk=Side.ALLIED))
