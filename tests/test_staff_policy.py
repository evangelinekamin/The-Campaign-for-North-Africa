"""Step 3: the StaffPolicy skeleton -- deliberate-once / dispense-slices, driven by
a deterministic MockClient stub (zero tokens). A full Rommel's Arrival game runs to
completion, proposes only engine-legal orders, and is byte-deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import _mock_staff                         # noqa: E402

from game.engine import (_continual_movement, _react, _reserve_designation,   # noqa: E402
                         _reserve_release, _rommel_move, _Run, run)
from game.events import EventKind, Phase, Side                    # noqa: E402
from game.events import log_to_json                               # noqa: E402
from game.hexmap import Coord                                     # noqa: E402
from game.llm import MockClient                                   # noqa: E402
from game.movement import TerrainMap                              # noqa: E402
from game.policy import ScriptedPolicy                            # noqa: E402
from game.scenario import rommels_arrival                         # noqa: E402
from game.staff_policy import StaffPolicy, merge_attacks          # noqa: E402
from game.policy import AttackOrder                               # noqa: E402
from game.state import GameState, Rommel, StepRecord, SupplyUnit, Unit, VP   # noqa: E402
from game.terrain import Mobility, Terrain                        # noqa: E402


def _play():
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)
    return run(rommels_arrival(seed=4200), axis=axis,
               allied=ScriptedPolicy(attacker=Side.AXIS))


# --- Step 4 lever fixtures: a clear grid with the objective at (0, 0) ----------
_PANZER = "GE 15th Panzer Division"          # a MOBILE-lane formation


def _grid(n: int = 6) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _mobile(uid: str, hex_: Coord, *, sp: int = 3, cpa: int = 40, reserve: int = 0) -> Unit:
    return Unit(uid, Side.AXIS, hex_, (StepRecord("pz", 6),), Mobility.MOTORIZED,
                cpa=cpa, stacking_points=sp, oca=4, dca=4, cohesion=6,
                formation=_PANZER, reserve=reserve)


def _lever_state(units, *, supplies=(), rommel: Rommel | None = None,
                 target: Coord = (0, 0), seed: int = 7,
                 phase: Phase = Phase.MOVEMENT) -> GameState:
    fuel = sum(s.fuel for s in supplies)
    ammo = sum(s.ammo for s in supplies)
    return GameState(turn=1, max_turns=4, phase=phase, active_side=Side.AXIS,
                     seed=seed, weather="normal", vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=target, supplies=tuple(supplies),
                     consumed={"FUEL": 0, "AMMO": 0},
                     initial_supply={"FUEL": fuel, "AMMO": ammo}, rommel=rommel)


def _staff() -> StaffPolicy:
    return StaffPolicy(MockClient(_mock_staff), side=Side.AXIS)


def test_staff_game_completes_with_a_verdict():
    result = _play()
    assert result.winner is not None or result.reason
    assert result.final.turn >= 1


def test_staff_proposals_are_individually_engine_legal():
    """The GOCs propose only from can_move_to / attack_options, so no order bounces
    as unreachable or unknown -- the only rejections the engine may raise are the
    batch-interaction ones (fuel/stacking), never a malformed proposal."""
    result = _play()
    bad = [e for e in result.events
           if e.kind == EventKind.ORDER_REJECTED and e.side == Side.AXIS
           and any(w in e.payload.get("reason", "")
                   for w in ("unreachable", "no such living"))]
    assert bad == []


def test_staff_run_is_byte_deterministic():
    a = log_to_json(_play().events)
    b = log_to_json(_play().events)
    assert a == b


def test_combat_batch_merges_same_target_attacks():
    merged = merge_attacks([
        AttackOrder(("m1", "m2"), (5, 5)),
        AttackOrder(("i1",), (5, 5)),          # same target -> combined arms
        AttackOrder(("m3",), (7, 7)),
    ])
    by_target = {a.target: a.attacker_ids for a in merged}
    assert by_target[(5, 5)] == ("m1", "m2", "i1")   # union, first-seen order
    assert by_target[(7, 7)] == ("m3",)
    assert len(merged) == 2


# --- Step 4: the command levers each emit their engine event -------------------

def test_rommel_move_commits_to_the_densest_panzer_hex_at_the_perimeter():
    # two panzer stacks: a denser one adjacent to the objective is the schwerpunkt.
    schwerpunkt = _mobile("Pz-heavy", (1, 0), sp=4)
    lighter = _mobile("Pz-light", (2, 0), sp=1)
    st = _lever_state([schwerpunkt, lighter], rommel=Rommel(hex=(3, 0)))
    r = _Run(st)
    _rommel_move(r, _staff(), Side.AXIS)
    moved = [e for e in r.events if e.kind == EventKind.ROMMEL_MOVED]
    assert len(moved) == 1
    assert tuple(moved[0].payload["to"]) == (1, 0)       # the perimeter hex holding the panzers


def test_reserve_designation_holds_the_rearmost_panzer_only_with_an_echelon():
    # two panzers, no breach -> the Chief holds the REARMOST back in Reserve I (18.12).
    van = _mobile("Pz-van", (2, 0))
    rear = _mobile("Pz-rear", (5, 0))
    r = _Run(_lever_state([van, rear]))
    _reserve_designation(r, _staff(), Side.AXIS)
    desig = [e for e in r.events if e.kind == EventKind.RESERVE_DESIGNATED]
    assert [e.payload["unit_id"] for e in desig] == ["Pz-rear"]   # only the rear echelon
    # a lone panzer is NEVER held back (no advance guard would remain).
    r2 = _Run(_lever_state([_mobile("Pz-solo", (2, 0))]))
    _reserve_designation(r2, _staff(), Side.AXIS)
    assert not any(e.kind == EventKind.RESERVE_DESIGNATED for e in r2.events)


def test_reserve_release_fires_the_moment_a_breach_opens():
    # a held panzer + a van panzer ON the objective's perimeter (the breach) -> release (18.13).
    held = _mobile("Pz-held", (5, 0), reserve=1)
    breach = _mobile("Pz-breach", (1, 0))                # adjacent to the objective at (0, 0)
    r = _Run(_lever_state([held, breach]))
    released = _reserve_release(r, _staff(), Side.AXIS)
    assert "Pz-held" in released
    assert any(e.kind == EventKind.RESERVE_RELEASED and e.payload["unit_id"] == "Pz-held"
               for e in r.events)
    # no breach (both panzers well back) -> the reserve stays designated, no release.
    r2 = _Run(_lever_state([_mobile("Pz-held", (5, 0), reserve=1), _mobile("Pz-far", (4, 0))]))
    assert _reserve_release(r2, _staff(), Side.AXIS) == frozenset()


def test_continual_movement_presses_the_exploitation_pulse_on_a_breakthrough():
    # a panzer 2 hexes from the objective (inside the 8.23 zone, the enemy garrison on it) can
    # still advance -> continual_movement presses on, the engine opens a SEGMENT_ADVANCED pulse.
    panzer = _mobile("Pz-break", (2, 0), cpa=60)
    garrison = Unit("UK", Side.ALLIED, (0, 0), (StepRecord("in", 6),), Mobility.FOOT,
                    cpa=10, stacking_points=2, oca=5, dca=8)
    dump = SupplyUnit("AX", Side.AXIS, (2, 0), ammo=40, fuel=10_000)
    r = _Run(_lever_state([panzer, garrison], supplies=[dump]))
    staff = _staff()
    _continual_movement(r, {Side.AXIS: staff, Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.AXIS)
    segs = [e for e in r.events if e.kind == EventKind.SEGMENT_ADVANCED]
    assert segs and all(e.payload["side"] == "AXIS" for e in segs)
    assert r.state.unit("Pz-break").hex != (2, 0)        # the panzer pulsed onto the perimeter


def test_react_to_slides_an_eligible_motorized_unit_aside():
    # the enemy moves adjacent; the staff slides its eligible motorized unit out of contact (8.5).
    reactor = _mobile("Pz-react", (3, 0))
    mover = Unit("AL", Side.ALLIED, (2, 0), (StepRecord("cr", 6),), Mobility.MOTORIZED,
                 cpa=40, stacking_points=3, oca=4, dca=4, cohesion=6)
    dump = SupplyUnit("AX", Side.AXIS, (3, 0), ammo=0, fuel=10_000)
    r = _Run(_lever_state([reactor, mover], supplies=[dump]))
    staff = _staff()
    _react(r, {Side.AXIS: staff, Side.ALLIED: ScriptedPolicy(Side.AXIS)}, Side.ALLIED, "AL")
    reacted = [e for e in r.events if e.kind == EventKind.REACTION_MOVED]
    assert reacted and reacted[0].payload["unit_id"] == "Pz-react"
    assert r.state.unit("Pz-react").hex != (3, 0)        # it slid aside


# --- Step 5: the flagged storming floor batches the objective ------------------

def test_storm_floor_batches_the_objective_when_a_timid_model_omits_it():
    # a panzer adjacent to a garrison it can assault, but a mock that returns NO attacks.
    panzer = _mobile("Pz-storm", (1, 0))
    garrison = Unit("UK", Side.ALLIED, (0, 0), (StepRecord("in", 4),), Mobility.FOOT,
                    cpa=10, stacking_points=2, oca=5, dca=8)
    dumps = [SupplyUnit("AX", Side.AXIS, (1, 0), ammo=40, fuel=60),
             SupplyUnit("UK-D", Side.ALLIED, (0, 0), ammo=40, fuel=60)]
    st = _lever_state([panzer, garrison], supplies=dumps, phase=Phase.COMBAT)

    def timid(prompt: str) -> str:
        if "COMMANDER" in prompt and "INTENT" in prompt:
            return _mock_staff(prompt)
        return '{"attacks":[]}'                          # never proposes an assault

    # WITHOUT the floor: the timid model storms nothing.
    bare = StaffPolicy(MockClient(timid), side=Side.AXIS, storm_floor=False)
    assert bare.combat(st, Side.AXIS) == []
    # WITH the floor: the objective is batched as an AttackOrder anyway.
    floored = StaffPolicy(MockClient(timid), side=Side.AXIS, storm_floor=True)
    orders = floored.combat(st, Side.AXIS)
    assert any(a.target == (0, 0) and "Pz-storm" in a.attacker_ids for a in orders)


# --- A(c): supply orders dispatch against LIVE post-movement positions ----------

def test_supply_orders_recompute_against_live_positions():
    """The QM's dump-relocation is deliberated at movement time, but the units advance
    before the supply phase. Dispatching the STALE pre-move plan sends the dump to a hex
    the combat unit has since vacated -- the 'must end stacked' reject. supply_orders must
    recompute against the LIVE board it is handed at supply-phase."""
    from game.policy import SupplyMoveOrder

    dump = SupplyUnit("D", Side.AXIS, (3, 0), ammo=50, fuel=50)
    staff = _staff()
    # deliberate the side-turn against a board where the panzer sits at (2,0)
    s0 = _lever_state([_mobile("P", (2, 0))], supplies=[dump])
    staff.movement(s0, Side.AXIS)                        # caches the (turn,stage,side) plan
    # the panzer has since advanced to (1,0); the dump must FOLLOW it live, not chase (2,0)
    s1 = _lever_state([_mobile("P", (1, 0))], supplies=[dump])
    assert staff.supply_orders(s1, Side.AXIS) == [SupplyMoveOrder("D", (1, 0))]


def test_staff_game_has_no_stale_supply_rejects():
    """The whole mock staff game must never bounce a supply relocation as 'must end
    stacked' -- proof the cached-plan staleness is gone end to end."""
    result = _play()
    stale = [e for e in result.events
             if e.kind == EventKind.ORDER_REJECTED and e.actor == "AXIS/Logistics"
             and "must end stacked" in e.payload.get("reason", "")]
    assert stale == []


# --- D: reject feedback to the seats (StaffPolicy.debrief) ----------------------

from game.events import Event                                     # noqa: E402


def _front_reject(uid="P", to=(1, 0), reason="destination unreachable"):
    return Event(0, 1, Phase.MOVEMENT, Side.AXIS, "AXIS/Front",
                 EventKind.ORDER_REJECTED, {"unit_id": uid, "to": list(to), "reason": reason})


def test_debrief_stashes_only_own_front_rejects():
    staff = _staff()
    staff.debrief([
        _front_reject("P"),                                                        # kept
        Event(1, 1, Phase.LOGISTICS, Side.AXIS, "AXIS/Logistics",                  # dropped (scripted)
              EventKind.ORDER_REJECTED, {"supply_id": "D", "reason": "must end stacked"}),
        Event(2, 1, Phase.MOVEMENT, Side.ALLIED, "ALLIED/Front",                   # dropped (enemy)
              EventKind.ORDER_REJECTED, {"unit_id": "E", "reason": "nope"}),
        Event(3, 1, Phase.MOVEMENT, Side.AXIS, "AXIS/Front",                       # dropped (not a reject)
              EventKind.UNIT_MOVED, {"unit_id": "Q"}),
    ])
    assert [e.payload["unit_id"] for e in staff._rejects] == ["P"]


def test_reject_feedback_line_names_unit_hex_and_reason():
    staff = _staff()
    staff.debrief([_front_reject("P", (3, 1), "destination over stacking limit")])
    line = staff._reject_feedback()
    assert line.startswith("REJECTED last stage (do NOT reissue): ")
    assert "P->[3, 1]: destination over stacking limit" in line
    # a clean stage prepends nothing (byte-identical prompt)
    staff.debrief([])
    assert staff._reject_feedback() == ""


class _Capturing:
    def __init__(self, fn):
        self._fn = fn
        self.prompts: list = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._fn(prompt)


def test_goc_movement_prompt_carries_the_reject_feedback():
    cap = _Capturing(_mock_staff)
    staff = StaffPolicy(cap, side=Side.AXIS)
    staff.debrief([_front_reject("GE 15th Panzer Division-1", (9, 9), "destination unreachable")])
    staff.movement(_lever_state([_mobile("P", (2, 0))]), Side.AXIS)
    assert any("REJECTED last stage (do NOT reissue)" in p for p in cap.prompts), \
        "the GOC movement prompt must carry the do-not-reissue feedback"
