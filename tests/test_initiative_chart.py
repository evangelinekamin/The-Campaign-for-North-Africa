"""The [7.2] Initiative Ratings chart, and General Rommel's 64.2 arrival that makes it bite.

Two coupled fixes that must ship together (the plan's Item 0.5): the [7.2] chart (game.initiative)
and Rommel's arrival (rule 64.2). Wiring the chart WITHOUT Rommel would hand the tempo to the
Commonwealth, because the Axis rating-6 row ("Rommel on the maps") is dead paper until he lands --
so the two are tested together here.

  * The Commonwealth rating is a function of the DATE: 3 / 4 / 5 across the three bands.
  * The Axis rating is a function of PRESENCE: 6 with Rommel on the maps, 3 with German land
    combat units but no Rommel, 1 with neither (the 1940 Italians alone).
  * Rommel (the rule-31 entity) is None in the campaign until the 3rd OpStage of Game-Turn 26,
    when game.engine._rommel_arrival lifts him onto the DAK's entry hex; from GT27 the Axis reads
    the rating-6 row.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import initiative
from game.engine import _initiative, _rommel_arrival, _Run, run
from game.events import EventKind, Phase, Side
from game.policy import ScriptedPolicy
from game.scenario import campaign, rommels_arrival
from game.hexmap import Coord
from game.state import GameState, Rommel, RommelArrival, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain
from game.movement import TerrainMap


# --- fixtures ----------------------------------------------------------------

def _unit(uid: str, formation: str, hex_: Coord = (0, 0), *, is_combat: bool = True) -> Unit:
    return Unit(uid, Side.AXIS, hex_, (StepRecord("x", 6),), Mobility.MOTORIZED,
                cpa=20, stacking_points=1, oca=4, dca=4, is_combat=is_combat,
                arrival_turn=1, formation=formation)


def _grid(n: int = 3) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _state(units=(), *, turn: int = 1, rommel: Rommel | None = None,
           rommel_arrival: RommelArrival | None = None, chart: bool = True) -> GameState:
    return GameState(turn=turn, max_turns=111, phase=Phase.WEATHER, active_side=Side.SYSTEM,
                     seed=7, weather="normal", vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=(0, 0), supplies=(), consumed={},
                     initial_supply={}, rommel=rommel, rommel_arrival=rommel_arrival,
                     initiative_chart=chart)


class _FixedDice:
    """A pinned d6 sequence loaded into one subsystem's stream (game.dice), raising if over-drawn."""

    def __init__(self, seq):
        self.seq = list(seq)

    def randint(self, a, b):
        return self.seq.pop(0)


# --- [7.2] Commonwealth rows: the DATE bands ---------------------------------

def test_commonwealth_rating_climbs_across_the_three_bands():
    # docs/rules/90:611-613 -- 3 (GT1-42), 4 (GT43-90), 5 (GT91-111), tested at every boundary.
    assert [initiative.commonwealth_rating(t) for t in (1, 42, 43, 90, 91, 111)] == [3, 3, 4, 4, 5, 5]


# --- [7.2] Axis rows: PRESENCE on the game-maps ------------------------------

def test_axis_rating_is_one_for_the_1940_italians_alone():
    # No German land unit, no Rommel -> the Italians roll at rating 1 (docs/rules/90:616).
    assert initiative.axis_rating(_state()) == 1


def test_axis_rating_is_three_with_german_combat_units_but_no_rommel():
    st = _state([_unit("GE-recon", "GE 5th Light Division")])
    assert initiative.axis_rating(st) == 3


def test_a_german_hq_alone_does_not_reach_rating_three():
    # is_combat=False: a headquarters is not a "combat unit" (docs/rules/90:615).
    st = _state([_unit("GE-DAK-HQ", "GE DAK", is_combat=False)])
    assert initiative.axis_rating(st) == 1


def test_axis_rating_is_six_with_rommel_on_the_maps():
    st = _state([_unit("GE-recon", "GE 5th Light Division")], rommel=Rommel(hex=(0, 0)))
    assert initiative.axis_rating(st) == 6


def test_rommel_in_germany_is_not_on_the_maps_so_the_rating_falls_to_three():
    # 31.5 recall: Germany is not part of the game-maps, so [7.2] reads the rating-3 row while
    # German combat units remain -- the chart implies the recall clamp on its own.
    st = _state([_unit("GE-recon", "GE 5th Light Division")],
                rommel=Rommel(hex=(0, 0), in_germany=True))
    assert initiative.axis_rating(st) == 3


# --- rule 64.2: the arrival mechanism (game.engine._rommel_arrival) -----------

def test_rommel_arrives_once_at_the_scheduled_turn_and_stage():
    sched = RommelArrival(turn=26, stage=3, hex=(45, -7))
    r = _Run(_state(turn=26, rommel_arrival=sched))
    _rommel_arrival(r, 1)                                     # wrong stage -> no-op
    _rommel_arrival(r, 2)                                     # wrong stage -> no-op
    assert r.state.rommel is None
    _rommel_arrival(r, 3)                                     # the scheduled moment
    assert r.state.rommel == Rommel(hex=(45, -7))
    arr = [e for e in r.events if e.kind == EventKind.ROMMEL_ARRIVED]
    assert len(arr) == 1 and arr[0].payload == {"hex": [45, -7]}
    _rommel_arrival(r, 3)                                     # already on the board -> no second arrival
    assert len([e for e in r.events if e.kind == EventKind.ROMMEL_ARRIVED]) == 1


def test_no_arrival_scheduled_is_a_silent_noop():
    r = _Run(_state(turn=26, rommel_arrival=None))
    _rommel_arrival(r, 3)
    assert r.state.rommel is None and not r.events


# --- the chart drives the roll (game.engine._initiative) ---------------------

def test_initiative_roll_reads_the_chart_ratings():
    # GT27, Rommel on the maps -> Axis 6 vs Commonwealth 3; pin the dice and read the totals back.
    st = _state([_unit("GE-recon", "GE 5th Light Division")], turn=27, rommel=Rommel(hex=(0, 0)))
    r = _Run(st)
    # axis 2 + 6 = 8 vs allied 5 + 3 = 8 -> a 7.14 tie, rerolled: axis 4 + 6 = 10 vs allied 1 + 3 = 4.
    r.dice.load("initiative", _FixedDice([2, 5, 4, 1]))
    _initiative(r)
    ev = next(e for e in r.events if e.kind == EventKind.INITIATIVE_DETERMINED)
    assert ev.payload["axis_total"] == 10 and ev.payload["allied_total"] == 4
    assert ev.payload["side"] == Side.AXIS.value


# --- the campaign wires both; the Desert Fox benchmark does not --------------

def test_campaign_opts_into_the_chart_and_schedules_rommel():
    st = campaign(seed=7, max_turns=30)
    assert st.initiative_chart is True
    assert st.initiative_fixed == Side.AXIS and st.initiative_fixed_until == 1   # 64.4/60.6: Italians hold GT1
    assert st.rommel is None                                                     # not yet arrived
    assert st.rommel_arrival == RommelArrival(turn=26, stage=3, hex=(45, -7))    # 64.2, at the DAK entry hex


def test_desert_fox_benchmark_keeps_its_proxy_untouched():
    # rommels_arrival runs a synthetic clock and seeds Rommel from t0: it must NOT opt into the
    # date-banded chart, or its byte-locked determinism signature would move.
    st = rommels_arrival(seed=42)
    assert st.initiative_chart is False
    assert st.rommel_arrival is None
    assert st.rommel is not None                                                 # seeded on the board


# --- the full loop: Rommel lands at GT26.3 and the tempo inverts --------------

def _rating_at(events, turn: int) -> tuple[int, int]:
    """Recover (axis_rating, allied_rating) a game-turn rolled at, from its INITIATIVE_DETERMINED
    event: total minus the deciding die (the last drawn pair, after any 7.14 tie rerolls)."""
    ev = next(e for e in events if e.kind == EventKind.INITIATIVE_DETERMINED and e.turn == turn)
    return ev.payload["axis_total"] - ev.rng_draws[-2], ev.payload["allied_total"] - ev.rng_draws[-1]


def test_campaign_run_arrives_rommel_and_the_axis_rating_climbs_1_3_6():
    res = run(campaign(seed=7, max_turns=27), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))

    # Rommel reaches Africa exactly once, at the 3rd OpStage of Game-Turn 26 (rule 64.2).
    arr = [e for e in res.events if e.kind == EventKind.ROMMEL_ARRIVED]
    assert len(arr) == 1 and arr[0].turn == 26 and arr[0].stage == 3
    assert res.final.rommel is not None and res.final.rommel.hex == (45, -7)

    # Game-Turn 1 is the Italians' predetermined hold (64.4 -> 60.6): no die.
    gt1 = next(e for e in res.events if e.kind == EventKind.INITIATIVE_DETERMINED and e.turn == 1)
    assert gt1.payload.get("fixed") is True and gt1.payload["side"] == Side.AXIS.value

    # The Axis Initiative Rating climbs 1 -> 3 -> 6 exactly on the [7.2] transitions, against a
    # Commonwealth fixed at 3 through GT42.
    assert _rating_at(res.events, 10) == (1, 3)     # the 1940 Italians alone
    assert _rating_at(res.events, 24) == (3, 3)     # German land combat units, no Rommel (arrived GT21)
    assert _rating_at(res.events, 27) == (6, 3)     # Rommel on the maps
