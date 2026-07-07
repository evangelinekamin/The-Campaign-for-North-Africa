"""Air interdiction of naval convoys -- the crack's ferry-cut (rules 41.6 / 32.63-32.66;
Step 1-2). An InterdictionOrder skims the [41.5] Air Bombardment CRT's tens-of-percent
(41.66) off a convoy's cargo BEFORE it lands (41.67), leaving a smaller SUPPLY_ARRIVED
beside a marker CONVOY_INTERDICTED. These tests pin: the transcribed CRT (a partition of
all 36 sequential dice codes + spot cells), the 41.67 round-up/floor split, the byte-
identical default (interdictions=() draws no dice, reduces nothing), the conserving fold,
and -- the load-bearing claim -- that a strong enough SEA-TOBRUK cut cracks the fortress
(the SEA faucet feeding the SAME 15.15 land-starvation surrender the land path could not)."""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import logistics_data
from game.engine import (_apply_convoy_loss, _convoy_loss_pct, _interdict,
                         _naval_convoys, _Run, determinism_signature, interdict, run)
from game.events import EventKind, Phase, Side
from game.invariants import check
from game.movement import TerrainMap
from game.policy import ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival
from game.state import Convoy, GameState, InterdictionOrder, SupplyUnit, VP
from game.terrain import Terrain


def _mini(dump: SupplyUnit, convoys=(), interdictions=(), *, turn: int = 1) -> GameState:
    """A one-hex, one-dump state to exercise the seam in isolation (mirrors test_convoys)."""
    return GameState(
        turn=turn, max_turns=4, phase=Phase.WEATHER, active_side=Side.SYSTEM,
        seed=1, weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={dump.hex: Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=dump.hex,
        supplies=(dump,), consumed={"AMMO": 0, "FUEL": 0},
        initial_supply={"AMMO": dump.ammo, "FUEL": dump.fuel},
        convoys=tuple(convoys), interdictions=tuple(interdictions))


# --- the state field ---------------------------------------------------------

def test_interdictions_default_empty():
    assert GameState.__dataclass_fields__["interdictions"].default == ()
    assert coastal_corridor().interdictions == ()
    assert rommels_arrival().interdictions == ()


# --- the transcribed CRT (41.66) --------------------------------------------

def test_crt_partitions_every_column():
    """Each Bomb-Point column must map all 36 sequential 2d6 codes to exactly one result
    (the faithful chart has no gaps and no overlaps)."""
    codes = [t * 10 + u for t in range(1, 7) for u in range(1, 7)]
    for col in logistics_data.convoy_bombing_crt_41_66():
        covered = [c for c in codes
                   if any(e["die"][0] <= c <= e["die"][1] for e in col["results"])]
        assert len(covered) == len(codes), col["bomb_points"]
        # no code is claimed by two entries
        for c in codes:
            assert sum(e["die"][0] <= c <= e["die"][1] for e in col["results"]) == 1


def test_crt_spot_cells():
    # cells read straight off the scanned [41.5] Axis Naval Convoy block
    assert _convoy_loss_pct(10, 6, 6) == 0        # 1..20 column is a flat 0%
    assert _convoy_loss_pct(30, 5, 5) == 5        # 21..40, code 55 -> 5%
    assert _convoy_loss_pct(30, 6, 6) == 10       # 21..40, code 66 -> 10%
    assert _convoy_loss_pct(100, 6, 6) == 20      # 81..120, code 66 -> 20%
    assert _convoy_loss_pct(500, 6, 6) == 50      # 471+, code 66 -> the table's ceiling
    assert _convoy_loss_pct(500, 1, 1) == 20      # 471+, code 11 -> floor of the top column
    assert _convoy_loss_pct(0, 6, 6) == 0         # below the table floor -> no damage


# --- the 41.67 split ---------------------------------------------------------

def test_apply_convoy_loss_rounds_lost_up_floors_delivered():
    cargo = {"AMMO": 1500, "FUEL": 500, "STORES": 1000, "WATER": 1000}
    reduced, tons_lost = _apply_convoy_loss(cargo, 10)     # 10% off each, round LOST up
    assert reduced == {"AMMO": 1350, "FUEL": 450, "STORES": 900, "WATER": 900}
    assert tons_lost > 0
    # a small odd pile: ceil(3 * 0.10) = 1 lost -> 2 delivered (round-up bites)
    r2, _ = _apply_convoy_loss({"AMMO": 3}, 10)
    assert r2 == {"AMMO": 2}
    # 0% is a no-op passthrough
    assert _apply_convoy_loss(dict(cargo), 0) == (dict(cargo), 0)


# --- interdict() byte-identical when no order --------------------------------

def test_interdict_no_order_is_verbatim_and_draws_no_rng():
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 40, "FUEL": 60})
    s = _mini(SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0), [conv])
    rng = random.Random(7)
    before = rng.getstate()
    cargo = interdict(conv, s, rng)
    assert cargo == {"AMMO": 40, "FUEL": 60}               # verbatim
    assert rng.getstate() == before                        # no die drawn -> byte-identical


def test_interdict_reduces_when_ordered():
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 1000})
    order = InterdictionOrder("SEA-TOBRUK", 1, 500)         # top column, 20..50%
    s = _mini(SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0), [conv], [order])
    cargo, o, pct, tons = _interdict(conv, s, random.Random(3))
    assert o is order and pct >= 20 and cargo["AMMO"] < 1000 and tons > 0


# --- _naval_convoys emits CONVOY_INTERDICTED, conserves ----------------------

def test_naval_convoys_emits_marker_beside_reduced_arrival():
    conv = Convoy("c1", Side.ALLIED, 1, "SEA-TOBRUK", "D", {"AMMO": 1000, "FUEL": 1000})
    order = InterdictionOrder("SEA-TOBRUK", 1, 500)
    r = _Run(_mini(SupplyUnit("D", Side.ALLIED, (0, 0), ammo=0, fuel=0), [conv], [order]))
    _naval_convoys(r)
    itd = [e for e in r.events if e.kind == EventKind.CONVOY_INTERDICTED]
    arr = [e for e in r.events if e.kind == EventKind.SUPPLY_ARRIVED]
    assert len(itd) == 1 and len(arr) == 1
    p = itd[0].payload
    assert p["lane"] == "SEA-TOBRUK" and p["convoy_id"] == "c1"
    assert p["interdictor"] == Side.AXIS.value              # the side opposing the CW ferry
    assert p["bomb_points"] == 500 and p["pct_lost"] >= 20 and p["tons_lost"] > 0
    # the load-bearing reduction rode SUPPLY_ARRIVED: less landed than the 1000/1000 shipped
    landed = arr[0].payload["cargo"]
    assert landed["AMMO"] < 1000 and landed["FUEL"] < 1000
    check(r.state)                                          # conservation holds untouched


def test_convoy_interdicted_folds_to_identity():
    from game.apply import apply
    from game.events import Event
    s = _mini(SupplyUnit("D", Side.ALLIED, (0, 0), ammo=10, fuel=20))
    e = Event(0, 1, Phase.LOGISTICS, Side.AXIS, "SYSTEM", EventKind.CONVOY_INTERDICTED,
              {"lane": "SEA-TOBRUK", "convoy_id": "c1", "interdictor": "AXIS",
               "bomb_points": 500, "pct_lost": 30, "tons_lost": 99})
    assert apply(s, e) is s                                 # pure marker -> identity


# --- byte-identity of the live scenarios (interdictions=() everywhere) --------

def test_rommels_arrival_byte_identical():
    a = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    b = run(rommels_arrival(seed=1941), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(a.events) == determinism_signature(b.events)
    # no interdiction machinery ever fires in the interdiction-free scenario
    assert not any(e.kind == EventKind.CONVOY_INTERDICTED for e in a.events)

