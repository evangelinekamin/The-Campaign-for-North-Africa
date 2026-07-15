"""Vehicle Breakdown + Repair (rules 21/22, Fork B faithful proxy).

Every magnitude here is the rulebook's own -- the terrain/hexside Breakdown Values,
the 21.38 Breakdown Table, the 22.8 field-repair schedule -- and a chart-of-record
test binds the code constants to data/breakdown_rates.json so they cannot drift.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import combat_tables as ct
from game import terrain as T
from game.movement import TerrainMap, breakdown_points, edge
from game.terrain import Hexside, Mobility, Terrain

_BRK = json.load(open(os.path.join(
    os.path.dirname(__file__), "..", "data", "breakdown_rates.json")))


# --- Step 1: terrain Breakdown Values + breakdown_points ---------------------

# JSON chart keys -> engine enum (the one spelling mismatch: heavy_vegetation).
_TERRAIN_KEY = {
    "clear": Terrain.CLEAR, "gravel": Terrain.GRAVEL, "salt_marsh": Terrain.SALT_MARSH,
    "heavy_vegetation": Terrain.HEAVY_VEG, "rough": Terrain.ROUGH,
    "mountain": Terrain.MOUNTAIN, "delta": Terrain.DELTA, "desert": Terrain.DESERT,
    "major_city": Terrain.MAJOR_CITY,
}
_HEXSIDE_KEY = {
    "ridge": Hexside.RIDGE, "up_slope": Hexside.UP_SLOPE, "down_slope": Hexside.DOWN_SLOPE,
    "up_escarpment": Hexside.UP_ESCARPMENT, "down_escarpment": Hexside.DOWN_ESCARPMENT,
    "wadi": Hexside.WADI, "major_river": Hexside.MAJOR_RIVER, "minor_river": Hexside.MINOR_RIVER,
}


def test_terrain_breakdown_values_match_chart_of_record():
    hexes = _BRK["terrain_breakdown_values_8_37"]["hex_terrain"]
    for key, terrain in _TERRAIN_KEY.items():
        assert T.breakdown_value(terrain) == hexes[key], key
    assert T.breakdown_value(Terrain.DESERT) == 24         # the load-bearing recovery


def test_hexside_breakdown_values_match_chart_of_record():
    sides = _BRK["terrain_breakdown_values_8_37"]["hexside"]
    for key, feature in _HEXSIDE_KEY.items():
        want = None if sides[key] == "P" else sides[key]
        assert T.hexside_breakdown(feature) == want, key


def test_road_breakdown_value_matches_chart():
    assert T.ROAD_BREAKDOWN == _BRK["terrain_breakdown_values_8_37"]["road"]["breakdown_value"]


def _line(*coords, terrain, hexsides=None, roads=(), tracks=()):
    return TerrainMap(terrain={c: terrain for c in coords},
                      hexsides=hexsides or {},
                      roads=frozenset(roads), tracks=frozenset(tracks))


def test_foot_never_breaks_down():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.DESERT)
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.FOOT) == 0.0
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.CAMEL) == 0.0


def test_desert_step_is_the_tank_killer():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.DESERT)
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 24


def test_54_2_worked_example_is_ten():
    # A Light Truck along a Track, across a Wadi hexside, into a Rough hex:
    # 1/2x8 (rough) + 1/2x8 (wadi) + 1 (hex off-road) + 1 (hexside off-road) = 10.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.ROUGH,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 tracks=[edge((0, 0), (1, 0))])
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.LIGHT_TRUCK) == 10
    example = _BRK["terrain_breakdown_values_8_37"]["light_truck_offroad_54_2"]
    assert "10 BP" in example["worked_example_54_2"]


def test_road_negates_hexside_breakdown():
    # On a road across a wadi into desert: only the road's own 1/2 value, hexside negated.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.DESERT,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 roads=[edge((0, 0), (1, 0))])
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 0.5
    # a light truck ON a road gets no off-road penalty either
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.LIGHT_TRUCK) == 0.5


def test_track_halves_hex_and_hexside():
    tmap = _line((0, 0), (1, 0), terrain=Terrain.ROUGH,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 tracks=[edge((0, 0), (1, 0))])
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 4 + 4


def test_track_does_not_halve_down_escarpment():
    # note-8 exception: a vehicle's Breakdown down an escarpment is NOT halved by a track.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.CLEAR,
                 hexsides={((0, 0), (1, 0)): Hexside.DOWN_ESCARPMENT},
                 tracks=[edge((0, 0), (1, 0))])
    # entry clear=4 halved to 2, escarpment 6 NOT halved.
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE) == 2 + 6


def test_rainstorm_treats_road_as_track():
    # 29.56: in a rainstorm the road no longer negates; it halves like a track.
    tmap = _line((0, 0), (1, 0), terrain=Terrain.ROUGH,
                 hexsides={((0, 0), (1, 0)): Hexside.WADI},
                 roads=[edge((0, 0), (1, 0))])
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "normal") == 0.5
    assert breakdown_points(tmap, (0, 0), (1, 0), Mobility.VEHICLE, "rainstorm") == 4 + 4


# --- Step 2: Unit breakdown state + effective_strength + BAR -----------------

from dataclasses import replace

from game.events import Side
from game.invariants import InvariantViolation, check
from game.state import StepRecord, Unit


def _tank(broken: int = 0, strength: int = 10, **kw) -> Unit:
    fields = dict(mobility=Mobility.VEHICLE, cpa=20, stacking_points=1,
                  oca=4, dca=3, barrage=0, anti_armor=5, armor_protection=6,
                  is_tank=True, broken_down=broken)
    fields.update(kw)
    return Unit("T1", Side.AXIS, (0, 0), (StepRecord("tank", strength),), **fields)


def test_effective_strength_deducts_broken():
    u = _tank(broken=4, strength=10)
    assert u.strength == 10
    assert u.effective_strength == 6


def test_broken_vehicles_neither_attack_defend_nor_fire():
    full = _tank(broken=0)
    half = _tank(broken=5)
    assert half.raw_offense == full.raw_offense // 2 == 4 * 5
    assert half.raw_defense == 3 * 5
    assert half.raw_anti_armor == 5 * 5
    dead = _tank(broken=10)
    assert dead.raw_offense == dead.raw_defense == dead.raw_anti_armor == 0


def test_breaks_down_is_armor_only():
    assert _tank().breaks_down                                   # a tank
    gun = Unit("G", Side.AXIS, (0, 0), (StepRecord("atg", 6),), mobility=Mobility.MOTORIZED,
               cpa=10, stacking_points=1, oca=1, dca=2, anti_armor=8, vulnerability=4)
    assert not gun.breaks_down                                   # inherent transport (21.11)


def test_invariant_rejects_broken_over_strength():
    from game.movement import TerrainMap
    from game.state import GameState, VP
    from game.events import Phase
    tmap = TerrainMap(terrain={(0, 0): Terrain.CLEAR})
    bad = _tank(broken=12, strength=10)
    st = GameState(turn=1, max_turns=2, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                   seed=1, weather="clear", vp=VP(), terrain=tmap,
                   control={}, units=(bad,), target_hex=(0, 0), supplies=(),
                   consumed={}, initial_supply={})
    with pytest.raises(InvariantViolation):
        check(st)


def test_bar_sourced_from_unit_stats_in_oob():
    from game import oob
    units, _ = oob.build()
    by_bar = {u.bar for u in units if u.is_tank}
    assert by_bar                                                # tanks exist and carry a BAR
    # Italian CV33 = +2R, German panzers = 0 (post-gate); every gun carries none.
    assert all(u.bar == 0 for u in units if u.is_gun)


# --- Step 3: BP accrual into the move faucet --------------------------------

from game.apply import apply, fold
from game.events import Event, EventKind, Phase


def _state_with(units, *, weather="clear", tmap=None, turn=1):
    from game.movement import TerrainMap
    from game.state import GameState, VP
    tmap = tmap or TerrainMap(terrain={(q, 0): Terrain.DESERT for q in range(6)})
    return GameState(turn=turn, max_turns=9, phase=Phase.MOVEMENT, active_side=Side.AXIS,
                     seed=1, weather=weather, vp=VP(), terrain=tmap,
                     control={}, units=tuple(units), target_hex=(5, 0), supplies=(),
                     consumed={}, initial_supply={})


def _ev(kind, payload):
    return Event(0, 1, Phase.MOVEMENT, Side.AXIS, "AXIS/Front", kind, payload)


def test_unit_moved_accrues_bp():
    st = _state_with([_tank()])
    st2 = apply(st, _ev(EventKind.UNIT_MOVED,
                        {"unit_id": "T1", "from": [0, 0], "to": [1, 0], "cp_spent": 2, "bp": 24.0}))
    assert st2.unit("T1").bp_accumulated == 24.0
    assert st2.unit("T1").hex == (1, 0)


def test_retreat_accrues_into_same_accumulator():
    st = _state_with([_tank(bp_accumulated=24.0)])
    st2 = apply(st, _ev(EventKind.UNIT_RETREATED,
                        {"unit_id": "T1", "from": [1, 0], "to": [0, 0], "hexes": 1, "bp": 10.0}))
    assert st2.unit("T1").bp_accumulated == 34.0        # 21.25 cumulative across portions


def test_move_without_bp_is_byte_identical():
    st = _state_with([_tank()])
    st2 = apply(st, _ev(EventKind.UNIT_MOVED,
                        {"unit_id": "T1", "from": [0, 0], "to": [1, 0], "cp_spent": 2}))
    assert st2.unit("T1").bp_accumulated == 0.0         # omitted bp -> unchanged


def test_turn_advanced_resets_bp_but_not_broken():
    st = _state_with([_tank(broken=3, bp_accumulated=40.0, bp_checked_column=5)])
    st2 = apply(st, Event(0, 1, Phase.RECORD, Side.SYSTEM, "SYSTEM",
                          EventKind.TURN_ADVANCED, {"turn": 2}))
    u = st2.unit("T1")
    assert u.bp_accumulated == 0.0 and u.bp_checked_column == -1   # OpStage boundary (21.25)
    assert u.broken_down == 3                                      # persists (21.44)


def test_engine_bp_matches_hand_computed_desert_dash():
    # A tank dashing four hexes of open desert accrues 4 x 24 BP in its UNIT_MOVED.
    from game import tactics
    st = _state_with([_tank(cpa=99)])
    u = st.unit("T1")
    reach, prev = tactics.reachable_for_prev(st, u, frozenset(), frozenset(), st.living(Side.AXIS))
    bp = tactics.bp_for_move(st, u, prev, (4, 0))
    assert bp == 4 * 24


def test_infantry_move_emits_no_bp():
    from game import tactics
    inf = Unit("I1", Side.AXIS, (0, 0), (StepRecord("inf", 6),), mobility=Mobility.FOOT,
               cpa=10, stacking_points=1, oca=3, dca=3)
    st = _state_with([inf])
    reach, prev = tactics.reachable_for_prev(st, inf, frozenset(), frozenset(), st.living(Side.AXIS))
    assert tactics.bp_for_move(st, inf, prev, (3, 0)) == 0.0


# --- Step 4: the breakdown check + the 21.38 table --------------------------

_ROLLS = [d1 * 10 + d2 for d1 in range(1, 7) for d2 in range(1, 7)]   # 36 legal 2d6


def test_21_38_table_partitions_every_column():
    for col in range(ct._N_BP_COLS):
        hits = {roll: [pct for pct, cells in ct._BREAKDOWN if roll in ct.expand(cells[col])]
                for roll in _ROLLS}
        for roll, pcts in hits.items():
            assert len(pcts) == 1, (col, roll, pcts)     # exactly one result per roll


def test_21_38_table_matches_chart_of_record():
    chart = _BRK["breakdown_table_21_38"]["cells_by_pct"]
    for pct, cells in ct._BREAKDOWN:
        want = [("" if c == "-" else c) for c in chart[str(pct)]]
        assert cells == want, pct


def test_21_34_worked_example_trucks_and_crusaders():
    # The rulebook's own 21.34 example, at 35 BP in Hot weather:
    #   Trucks (BAR 2L): 31-40 col shifted -2+1 = -1 -> 21-30 col; roll 33 -> 10%.
    assert ct.breakdown_result(35, -2, 1, 33) == 10
    #   Crusader I (BAR 1R): 31-40 col shifted +1+1 = +2 -> 51-60 col; roll 61 -> 33%.
    assert ct.breakdown_result(35, 1, 1, 61) == 33


def test_21_33_clamps():
    # Adjusted below the 4-10 column -> no breakdown (a reliable truck on light wear).
    assert ct.breakdown_result(5, -2, 0, 66) == 0
    # 71+ is the ceiling; a huge BAR cannot push past it.
    assert ct.breakdown_result(200, 2, 1, 11) == ct.breakdown_result(200, 0, 0, 11)


def test_bp_bands_round_up():
    assert ct.breakdown_band(20.5) == 3          # 21.31: 20.5 -> 21 -> 21-30 band
    assert ct.breakdown_band(3) == 0 and ct.breakdown_band(4) == 1
    assert ct.breakdown_band(71) == 8 and ct.breakdown_band(999) == 8


def test_hot_weather_shifts_one_column_right():
    assert ct.weather_breakdown_shift("hot") == 1
    assert ct.weather_breakdown_shift("sandstorm") == 1
    assert ct.weather_breakdown_shift("clear") == 0


def _run_breakdown(tank, weather="clear", seed=1):
    from game.engine import _Run, _breakdown
    st = _state_with([tank], weather=weather)
    r = _Run(st)
    r.state = st
    _breakdown(r, Side.AXIS)
    return r


def test_engine_strands_tanks_in_the_desert():
    r = _run_breakdown(_tank(strength=20, bp_accumulated=71.0))   # 71+ column: always > 0%
    checked = [e for e in r.events if e.kind == EventKind.BREAKDOWN_CHECKED]
    assert len(checked) == 1
    u = r.state.unit("T1")
    assert u.broken_down > 0                                      # armor thins without a shot
    assert u.bp_checked_column == checked[0].payload["column"]    # 21.26 gate advanced


def test_engine_21_27_floor_skips_low_bp():
    r = _run_breakdown(_tank(bp_accumulated=3.0))                 # not > 3
    assert not r.events


def test_engine_21_26_gate_no_recheck_in_same_column():
    already = _tank(strength=20, bp_accumulated=71.0, bp_checked_column=8)
    r = _run_breakdown(already)
    assert not r.events                                          # same 71+ column -> no re-check


def test_engine_no_breakdown_for_non_vehicles():
    inf = Unit("I1", Side.AXIS, (0, 0), (StepRecord("inf", 6),), mobility=Mobility.MOTORIZED,
               cpa=10, stacking_points=1, oca=3, dca=3, bp_accumulated=99.0)
    r = _run_breakdown(inf)
    assert not r.events                                          # inherent transport (21.11)


# --- Step 5: the Repair beat + 22.8 / 22.15 ---------------------------------

from game.state import SupplyUnit


class _FixedDie:                                                # force a known 22.8 field die
    """Loaded into the REPAIR stream alone (_Run.dice.load, game.dice), so pinning the field-
    repair die cannot reach the weather or breakdown dice this scenario also rolls."""

    def __init__(self, val):
        self.val = val

    def randint(self, a, b):
        return self.val


def test_field_repair_table_matches_chart_of_record():
    by_die = _BRK["broken_down_vehicle_repair_22_8"]["by_die"]
    for die_str, row in by_die.items():
        die = int(die_str)
        if die > 6:
            continue                                            # 7/8 are 'na' for field
        assert ct.field_repair("truck", die) == int(row[0])
        assert ct.field_repair("ac_recce", die) == int(row[1])
        assert ct.field_repair("tank", die) == int(row[2].rstrip("%*"))   # "10%*" -> 10


def test_field_repair_tank_schedule():
    # 22.8 Field/Tank column off the scan (PDF p103): 25% / 10%* / 10%* / 10%* / 0% / 0%
    # for dice 1..6. The OCR bled the "10%*" of dice 2/3/4 into "100%" (T0-1); the 10%*
    # single-TOE exception is enforced in _repaired_count, not in this schedule.
    assert [ct.field_repair("tank", d) for d in range(1, 7)] == [25, 10, 10, 10, 0, 0]


def _repair_run(tank, *, weather="clear", die=3, fuel=50):
    from game.engine import _Run, _repair
    from game.movement import TerrainMap
    from game.state import GameState, VP
    tmap = TerrainMap(terrain={(0, 0): Terrain.DESERT})
    dump = SupplyUnit("AX-Dump", Side.AXIS, (0, 0), ammo=0, fuel=fuel)
    st = GameState(turn=1, max_turns=9, phase=Phase.COMBAT, active_side=Side.AXIS,
                   seed=1, weather=weather, vp=VP(), terrain=tmap,
                   control={}, units=(tank,), target_hex=(0, 0), supplies=(dump,),
                   consumed={}, initial_supply={"FUEL": fuel})
    r = _Run(st)
    r.state = st
    r.dice.load("repair", _FixedDie(die))
    _repair(r, Side.AXIS)
    return r


def test_field_workshop_revives_a_fraction():
    r = _repair_run(_tank(broken=8, strength=10), die=3)          # die 3 -> 10% (22.8, T0-1)
    assert r.state.unit("T1").broken_down == 7                    # 10% of 8 broken, rounded up = 1
    assert any(e.kind == EventKind.VEHICLE_REPAIRED for e in r.events)


def test_field_repair_charges_fuel_and_conserves():
    r = _repair_run(_tank(broken=6, strength=10), die=3, fuel=50)
    consumed = [e for e in r.events if e.kind == EventKind.SUPPLY_CONSUMED]
    assert consumed and consumed[0].payload["commodity"] == "FUEL"
    # conservation is asserted inside every emit(); on_hand + consumed == initial holds.
    assert r.state.consumed["FUEL"] + r.state.supply("AX-Dump").fuel == 50


def test_no_field_repair_in_rain_or_sandstorm():
    for w in ("rainstorm", "sandstorm"):
        r = _repair_run(_tank(broken=6), weather=w, die=3)
        assert not r.events                                      # 22.13d
        assert r.state.unit("T1").broken_down == 6


def test_no_repair_without_fuel():
    r = _repair_run(_tank(broken=6), die=3, fuel=0)
    assert r.state.unit("T1").broken_down == 6                   # 22.13b: no supplies, no repair


def test_failed_roll_leaves_broken_untouched():
    r = _repair_run(_tank(broken=6, strength=10), die=5)          # die 5 -> 0%
    assert r.state.unit("T1").broken_down == 6
    assert not any(e.kind == EventKind.VEHICLE_REPAIRED for e in r.events)


def test_repair_skipped_in_enemy_controlled_hex():
    from game.events import Control
    from game.engine import _Run, _repair
    from game.movement import TerrainMap
    from game.state import GameState, VP
    tmap = TerrainMap(terrain={(0, 0): Terrain.DESERT})
    tank = _tank(broken=6, strength=10)
    dump = SupplyUnit("AX-Dump", Side.AXIS, (0, 0), ammo=0, fuel=50)
    st = GameState(turn=1, max_turns=9, phase=Phase.COMBAT, active_side=Side.AXIS,
                   seed=1, weather="clear", vp=VP(), terrain=tmap,
                   control={(0, 0): Control.ALLIED}, units=(tank,), target_hex=(0, 0),
                   supplies=(dump,), consumed={}, initial_supply={"FUEL": 50})
    r = _Run(st)
    r.state = st
    r.dice.load("repair", _FixedDie(3))
    _repair(r, Side.AXIS)
    assert not r.events                                          # 22.13a
    assert r.state.unit("T1").broken_down == 6
