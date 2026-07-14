"""Commonwealth railroad haulage (rule 54.3; CHUNK 4, dormant).

CW rail is INFRASTRUCTURE, not a counter (like Allied coastal shipping), so it is
modelled as a direct conserving dump->dump transfer -- RAIL_HAULED {from_dump, to_dump,
commodity, qty} -- gated on both dumps sitting on the one rail network (a rail-edge
reachability set, the twin of movement.reachable), capped at 1500 tons/OpStage of ONE
commodity (54.33). Conservation holds trivially: a single transfer, grand total
unchanged. Dormant until a scenario seeds TerrainMap.rails. Axis rail 54.4 rolling-stock
is DEFERRED. These tests pin the rails edge-set, the connectivity gate, the 1500-ton
cap, the conserving fold, and the byte-identity of rail-less scenarios."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game import supply, wells
from game.apply import apply
from game.engine import determinism_signature, run
from game.events import Event, EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap, edge
from game.policy import ScriptedPolicy
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
from game.scenario import campaign, coastal_corridor
from game.state import GameState, SupplyUnit, VP
from game.terrain import Terrain


def _rail_state(supplies, rails) -> GameState:
    terrain = {c: Terrain.CLEAR for e in rails for c in e}
    return GameState(
        turn=1, max_turns=4, phase=Phase.LOGISTICS, active_side=Side.SYSTEM,
        seed=1, weather="clear", vp=VP(),
        terrain=TerrainMap(terrain=terrain, rails=frozenset(rails)),
        control={}, units=(), target_hex=(0, 0), supplies=tuple(supplies),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: sum(getattr(s, c.lower()) for s in supplies)
                        for c in supply.COMMODITIES})


# --- the rails edge-set + connectivity gate ----------------------------------

def test_terrainmap_rails_default_empty():
    assert TerrainMap.__dataclass_fields__["rails"].default == frozenset()
    assert coastal_corridor().terrain.rails == frozenset()


def test_rail_reachable_is_network_connectivity():
    # A-B-C rail line, plus a disconnected D-E line.
    rails = [edge((0, 0), (1, 0)), edge((1, 0), (2, 0)), edge((5, 5), (6, 5))]
    tmap = TerrainMap(terrain={c: Terrain.CLEAR for e in rails for c in e}, rails=frozenset(rails))
    reach = supply.rail_reachable(tmap, (0, 0))
    assert reach == {(0, 0), (1, 0), (2, 0)}       # the whole connected line, not the D-E line
    assert (5, 5) not in reach
    assert supply.rail_reachable(tmap, (9, 9)) == {(9, 9)}   # off-network: only itself


# --- 54.3 / 54.5 the 1500-ton cap --------------------------------------------

def test_rail_haul_cap_is_1500_tons_crossed_to_points():
    # 54.33: 1500 tons of ONE commodity per OpStage, via the 54.5 Equivalent Weights.
    assert supply.RAIL_TONNAGE_54_3 == 1500
    assert supply.rail_haul_cap("AMMO") == supply.tons_to_points(1500, "AMMO")     # 375
    assert supply.rail_haul_cap("FUEL") == supply.tons_to_points(1500, "FUEL")     # 12000
    assert supply.rail_haul_cap("STORES") == 1500


# --- the conserving fold -----------------------------------------------------

def test_rail_hauled_is_a_conserving_transfer():
    src = SupplyUnit("RAILHEAD", Side.ALLIED, (0, 0), ammo=0, fuel=0, stores=1500)
    dst = SupplyUnit("FORWARD", Side.ALLIED, (2, 0), ammo=0, fuel=0, stores=0)
    rails = [edge((0, 0), (1, 0)), edge((1, 0), (2, 0))]
    s = _rail_state([src, dst], rails)
    # both dumps are on the one network
    reach = supply.rail_reachable(s.terrain, src.hex)
    assert dst.hex in reach
    qty = supply.rail_haul_cap("STORES")            # 1500 pts, the full OpStage cap
    e = Event(0, 1, Phase.LOGISTICS, Side.ALLIED, "ALLIED/Logistics", EventKind.RAIL_HAULED,
              {"from_dump": "RAILHEAD", "to_dump": "FORWARD", "commodity": "STORES", "qty": qty})
    s2 = apply(s, e)
    assert s2.supply("RAILHEAD").stores == 0 and s2.supply("FORWARD").stores == 1500
    assert s2.initial_supply["STORES"] == 1500 and s2.consumed["STORES"] == 0
    check(s2)                                       # on_hand+consumed==initial holds
    on_hand = sum(su.stores for su in s2.supplies)
    assert on_hand + s2.consumed["STORES"] == s2.initial_supply["STORES"]


# --- byte-identity: no rails => every existing scenario unchanged ------------

def test_railless_scenario_byte_identical():
    a = run(coastal_corridor(seed=11), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(coastal_corridor(seed=11), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    assert not any(e.kind == EventKind.RAIL_HAULED for e in a.events)


# --- [54.3]/[54.35] THE RAILWAY UNLOADS ALONG ITS LINE ---------------------------------------
# The campaign seeds the Western Desert Railway (Alexandria -> Mersa Matruh) as a real rails
# edge-set, and the rail lane now sets its freight down at the stations the army is standing on
# (engine._rail_stops) instead of piling all 1500 tons/OpStage on the one forward railhead. These
# pin the geography, the "unload where the troops are" rule, and the two things that must NOT move:
# the total hauled, and the byte-identity of every rail-less scenario.

@pytest.fixture(scope="module")
def rail_run():
    return run(campaign(seed=1941, max_turns=25), CampaignAxisPolicy(), CampaignCommonwealthPolicy())


def test_the_campaign_lays_a_real_railway():
    """[54.3]/[52.22] The rails and the water pipeline are the SAME hexes -- the rulebook says so
    ("the railroad hexes are pipelines in and of themselves", 54.33), so both read one corridor."""
    st = campaign(seed=1941)
    assert st.terrain.rails, "the campaign must lay the Western Desert Railway"
    rail_hexes = {h for e in st.terrain.rails for h in e}
    pipe_hexes = {su.hex for su in st.supplies if wells.PIPE_ID_MARK in su.id}
    assert rail_hexes == pipe_hexes, "the rails and the 52.22 pipeline must be one line"


def test_the_railway_stocks_stations_along_its_length(rail_run):
    """THE BUG THIS FIXES: the lane used to land its whole haul on ONE dump (Mersa Matruh) and leave
    four hundred miles of working railway at ZERO, so the only hexes in Egypt an Eighth Army
    battalion could eat on were the Delta and that railhead."""
    fed = {e.payload["supply_id"] for e in rail_run.events
           if e.kind == EventKind.SUPPLY_ARRIVED and e.payload["lane"] == "CW-RAILHEAD"}
    assert len(fed) > 1, "the railway must stock more than the terminus"
    assert any(sid.startswith("AL-Stage-Rail-") for sid in fed), "it must found stations on its line (54.11)"


def test_a_railway_station_is_founded_where_the_army_stands(rail_run):
    """[54.35] "supplies may be moved from any one spot and DUMPED IN ANOTHER SPOT... considered
    unloaded when they reach A SPECIFIC HEX." The train stops where the troops are."""
    st = campaign(seed=1941)
    rail_hexes = {h for e in st.terrain.rails for h in e}
    made = [e for e in rail_run.events if e.kind == EventKind.SUPPLY_DUMP_ESTABLISHED
            and e.payload["supply_id"].startswith("AL-Stage-Rail-")]
    assert made, "the railway must found stations"
    assert all(tuple(e.payload["hex"]) in rail_hexes for e in made), "a station must sit ON the line"


def test_the_railway_hauls_no_more_than_it_ever_did(rail_run):
    """The 54.32 magnitude is UNTOUCHED. This moves WHERE the freight lands, not one point of HOW
    MUCH: a game-turn of trains is still the charted 1500 tons/OpStage, crossed at 54.5."""
    from game.scenario import _campaign_rail_cargo
    landed: dict = {}
    for e in rail_run.events:
        if e.kind == EventKind.SUPPLY_ARRIVED and e.payload["lane"] == "CW-RAILHEAD" and e.turn == 5:
            for c, q in e.payload["cargo"].items():
                landed[c] = landed.get(c, 0) + q
    for c, q in landed.items():
        assert q <= _campaign_rail_cargo(5)[c], f"{c}: the railway landed more than 54.32 allows"


def test_the_railway_conserves(rail_run):
    check(rail_run.final)
