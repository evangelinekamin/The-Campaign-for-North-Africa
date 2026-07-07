"""Rule 31 -- General Rommel, the Axis named leader as a conservation-invisible entity.

Step 1: the frozen Rommel entity + the 17.28 +1 morale hook (clamp-first, add-outside).
Step 2: the 31.4 +5 CPA companion bonus, snapshotted at the OpStage boundary.
Step 3: 31.1 leader movement + the Berlin recall (the only new RNG).
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import oob, tactics
from game.apply import fold
from game.engine import (_adjusted_morale, _initiative, _rommel_move, _rommel_recall,
                         _Run, determinism_signature, run)
from game.events import EventKind, Phase, Side
from game.hexmap import Coord
from game.movement import TerrainMap
from game.policy import Policy, ScriptedPolicy
from game.scenario import coastal_corridor, rommels_arrival
from game.state import GameState, Rommel, StepRecord, Unit, VP
from game.terrain import Mobility, Terrain


# --- tiny fixtures -----------------------------------------------------------

def _unit(uid: str, side: Side, hex_: Coord, *, morale: int = 0, cohesion: int = 6,
          sp: int = 3, strength: int = 6, cpa: int = 20) -> Unit:
    return Unit(uid, side, hex_, (StepRecord("x", strength),), Mobility.MOTORIZED,
                cpa=cpa, stacking_points=sp, oca=4, dca=4, morale=morale, cohesion=cohesion)


def _grid(n: int = 6) -> TerrainMap:
    return TerrainMap(terrain={(q, r): Terrain.CLEAR for q in range(-n, n + 1)
                               for r in range(-n, n + 1)})


def _state(units, rommel: Rommel | None = None, seed: int = 7) -> GameState:
    return GameState(turn=1, max_turns=12, phase=Phase.COMBAT, active_side=Side.AXIS,
                     seed=seed, weather="normal", vp=VP(), terrain=_grid(), control={},
                     units=tuple(units), target_hex=(0, 0), supplies=(),
                     consumed={}, initial_supply={}, rommel=rommel)


# --- Step 1: the +1 morale (17.28) -------------------------------------------

def test_rommel_plus_one_applies_to_the_axis_stack():
    hx = (2, 0)
    stack = [_unit("GE-Pz", Side.AXIS, hx, morale=1)]
    without = _adjusted_morale(_Run(_state(stack)), stack)
    boosted = _adjusted_morale(_Run(_state(stack, Rommel(hex=hx))), stack)
    assert boosted[1] == without[1]                 # same seed -> identical 2d6 roll
    assert boosted[0] == without[0] + 1             # 17.28: exactly +1


def test_rommel_plus_one_breaks_the_17_23_ceiling():
    hx = (2, 0)
    stack = [_unit("GE-Pz", Side.AXIS, hx, morale=3, cohesion=8)]     # a +3 unit
    for seed in range(60):
        base = _adjusted_morale(_Run(_state(stack, seed=seed)), stack)[0]
        if base == 3:                                # a roll whose Adjusted Morale hits the ceiling
            boosted = _adjusted_morale(
                _Run(_state(stack, Rommel(hex=hx), seed=seed)), stack)[0]
            assert boosted == 4                      # 17.28 lifts it OUTSIDE the 17.23 clamp
            return
    raise AssertionError("no ceiling-hitting roll found in 60 seeds")


def test_rommel_plus_one_is_silent_when_absent_away_or_in_germany():
    hx = (2, 0)
    axis = [_unit("GE-Pz", Side.AXIS, hx, morale=1)]
    base = _adjusted_morale(_Run(_state(axis)), axis)[0]
    assert _adjusted_morale(_Run(_state(axis, Rommel(hex=hx, in_germany=True))), axis)[0] == base
    assert _adjusted_morale(_Run(_state(axis, Rommel(hex=(5, 5)))), axis)[0] == base
    # A Commonwealth stack draws no bonus even if Rommel shares its hex (31 is Axis-only).
    allied = [_unit("BR-Tk", Side.ALLIED, hx, morale=1)]
    ally_base = _adjusted_morale(_Run(_state(allied)), allied)[0]
    assert _adjusted_morale(_Run(_state(allied, Rommel(hex=hx))), allied)[0] == ally_base


# --- Step 1: the entity is seeded, the DAK-HQ Unit survives -------------------

def test_rommels_arrival_seeds_the_entity_and_keeps_the_dak_hq():
    st = rommels_arrival()
    assert st.rommel is not None and not st.rommel.in_germany
    # The merged 'GE Rommel - DAK' counter still materialises the is_combat=False DAK-HQ Unit
    # (morale 1) -- only the leader is lifted OUT to the conservation-invisible entity.
    dak = next(u for u in st.units if "Rommel" in u.id)
    assert not dak.is_combat and dak.morale == 1
    assert st.rommel.hex == dak.hex                  # the entity sits at the DAK-HQ start hex


def test_non_rommel_scenario_has_no_leader():
    assert coastal_corridor().rommel is None         # default None keeps toy scenarios byte-identical


# --- Step 2: the +5 CPA (31.4) -----------------------------------------------

def test_effective_cpa_plus_five_for_a_companion_on_the_anchor():
    hx = (2, 0)
    u = _unit("GE-Pz", Side.AXIS, hx, cpa=20)
    rom = Rommel(hex=hx, anchor_hex=hx, companions=frozenset({"GE-Pz"}))
    assert tactics.effective_cpa(_state([u], rom), u) == 25


def test_effective_cpa_unchanged_off_anchor_or_not_a_companion():
    hx = (2, 0)
    u = _unit("GE-Pz", Side.AXIS, hx, cpa=20)
    # walked in mid-stage -> not in the boundary snapshot -> no bonus (31.4 'started with')
    assert tactics.effective_cpa(_state([u], Rommel(hex=hx, anchor_hex=hx)), u) == 20
    # a companion, but Rommel has moved off the anchor -> voided (hex != anchor_hex)
    moved = Rommel(hex=(3, 0), anchor_hex=hx, companions=frozenset({"GE-Pz"}))
    assert tactics.effective_cpa(_state([u], moved), u) == 20
    # a companion that itself left the anchor hex -> voided
    away = replace(u, hex=(4, 0))
    stayed = Rommel(hex=hx, anchor_hex=hx, companions=frozenset({"GE-Pz"}))
    assert tactics.effective_cpa(_state([away], stayed), away) == 20
    # in Germany (Berlin recall) -> voided
    berlin = Rommel(hex=hx, in_germany=True, anchor_hex=hx, companions=frozenset({"GE-Pz"}))
    assert tactics.effective_cpa(_state([u], berlin), u) == 20


def test_rommel_widens_the_reachable_set():
    hx = (0, 0)
    u = _unit("GE-Pz", Side.AXIS, hx, cpa=6)
    plain = tactics.reachable_for(_state([u]), u, frozenset(), frozenset())
    rom = Rommel(hex=hx, anchor_hex=hx, companions=frozenset({"GE-Pz"}))
    boosted = tactics.reachable_for(_state([u], rom), u, frozenset(), frozenset())
    assert len(boosted) > len(plain)                 # +5 CPA reaches strictly farther


def test_rommels_arrival_snapshots_the_anchor_each_stage():
    res = run(rommels_arrival(), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    anchors = [e for e in res.events if e.kind == EventKind.ROMMEL_ANCHORED]
    assert anchors and all(e.side == Side.AXIS for e in anchors)


def test_non_rommel_run_emits_no_rommel_events():
    res = run(coastal_corridor(), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert not any(e.kind.name.startswith("ROMMEL") for e in res.events)


def test_rommels_arrival_runs_deterministically_with_the_entity():
    res = run(rommels_arrival(), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert res.winner in (Side.AXIS, Side.ALLIED)
    assert fold(res.initial, res.events) == res.final
    res2 = run(rommels_arrival(), ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
    assert determinism_signature(res.events) == determinism_signature(res2.events)


# --- Step 3: 31.1 leader movement --------------------------------------------

class _RommelMover(Policy):
    """A scripted policy that names a fixed destination for General Rommel's 31.1 move."""

    def __init__(self, dest):
        self.dest = dest

    def movement(self, state, side):
        return []

    def combat(self, state, side):
        return []

    def rommel_move(self, state):
        return self.dest


class _FixedDice:
    """A drop-in for _Run.rng returning a pinned d6 sequence (raises if over-drawn)."""

    def __init__(self, seq):
        self.seq = list(seq)

    def randint(self, a, b):
        return self.seq.pop(0)


def test_rommel_move_repositions_and_voids_the_31_4_anchor():
    hx, dest = (0, 0), (2, 0)
    u = _unit("GE-Pz", Side.AXIS, hx, cpa=6)
    rom = Rommel(hex=hx, anchor_hex=hx, companions=frozenset({"GE-Pz"}))
    r = _Run(_state([u], rom))
    assert tactics.effective_cpa(r.state, u) == 11        # +5 while he stands on the anchor
    _rommel_move(r, _RommelMover(dest), Side.AXIS)
    moved = [e for e in r.events if e.kind == EventKind.ROMMEL_MOVED]
    assert len(moved) == 1 and tuple(moved[0].payload["to"]) == dest
    assert r.state.rommel.hex == dest
    assert tactics.effective_cpa(r.state, u) == 6         # 31.4 voided: hex != anchor_hex


def test_rommel_move_rejects_an_unreachable_destination():
    r = _Run(_state([_unit("GE-Pz", Side.AXIS, (0, 0))], Rommel(hex=(0, 0))))
    _rommel_move(r, _RommelMover((99, 99)), Side.AXIS)    # off the map, past the 60-MP reach
    assert not any(e.kind == EventKind.ROMMEL_MOVED for e in r.events)
    assert r.state.rommel.hex == (0, 0)


def test_rommel_does_not_move_for_the_allied_side_or_when_in_germany():
    r = _Run(_state([_unit("GE-Pz", Side.AXIS, (0, 0))], Rommel(hex=(0, 0))))
    _rommel_move(r, _RommelMover((1, 0)), Side.ALLIED)    # 31 is Axis-only
    assert not any(e.kind == EventKind.ROMMEL_MOVED for e in r.events)
    berlin = _Run(_state([_unit("GE-Pz", Side.AXIS, (0, 0))], Rommel(hex=(0, 0), in_germany=True)))
    _rommel_move(berlin, _RommelMover((1, 0)), Side.AXIS)
    assert not any(e.kind == EventKind.ROMMEL_MOVED for e in berlin.events)


# --- Step 3: the Berlin recall (the only new RNG) ----------------------------

def test_berlin_recall_sends_rommel_to_germany_and_signals_the_clamp():
    r = _Run(_state([_unit("GE-Pz", Side.AXIS, (0, 0))], Rommel(hex=(0, 0))))
    r.rng = _FixedDice([6, 6])                             # a 12
    assert _rommel_recall(r) is True                      # -> _initiative clamps the Axis rating
    ev = [e for e in r.events if e.kind == EventKind.ROMMEL_RECALLED]
    assert len(ev) == 1 and ev[0].payload["in_germany"] is True and ev[0].rng_draws == (6, 6)
    assert r.state.rommel.in_germany is True


def test_berlin_recall_stays_put_on_a_non_twelve():
    r = _Run(_state([_unit("GE-Pz", Side.AXIS, (0, 0))], Rommel(hex=(0, 0))))
    r.rng = _FixedDice([3, 4])
    assert _rommel_recall(r) is False
    # The roll is now emitted UNCONDITIONALLY so its dice are certified even on a non-12; the
    # in_germany=False fold is a no-op on the on-map Rommel.
    ev = [e for e in r.events if e.kind == EventKind.ROMMEL_RECALLED]
    assert len(ev) == 1 and ev[0].payload["in_germany"] is False and ev[0].rng_draws == (3, 4)
    assert r.state.rommel.in_germany is False


def test_berlin_recall_auto_returns_then_rolls_normally():
    r = _Run(_state([_unit("GE-Pz", Side.AXIS, (0, 0))], Rommel(hex=(0, 0), in_germany=True)))
    r.rng = _FixedDice([2, 5])                             # returns, then a non-12 roll
    assert _rommel_recall(r) is False
    # Two beats now: the dice-free auto-return, then the certified (non-12) roll.
    ev = [e for e in r.events if e.kind == EventKind.ROMMEL_RECALLED]
    assert len(ev) == 2
    assert ev[0].payload["in_germany"] is False and ev[0].rng_draws == ()
    assert ev[1].payload["in_germany"] is False and ev[1].rng_draws == (2, 5)
    assert r.state.rommel.in_germany is False


def test_recall_draws_no_dice_and_is_silent_when_no_rommel():
    r = _Run(_state([_unit("GE-Pz", Side.AXIS, (0, 0))]))  # rommel None
    r.rng = _FixedDice([])                                 # would IndexError if any die were drawn
    assert _rommel_recall(r) is False
    assert not any(e.kind.name.startswith("ROMMEL") for e in r.events)


def test_recall_clamps_axis_initiative_to_three_and_forces_a_roll():
    st = replace(_state([_unit("GE-Pz", Side.AXIS, (0, 0))]),
                 initiative_fixed=Side.AXIS, initiative_fixed_until=99,
                 initiative_ratings={"AXIS": 5, "ALLIED": 0})
    r = _Run(st)
    r.rng = _FixedDice([6, 1])                             # axis 6 + min(5,3)=9 ; allied 1 + 0 = 1
    _initiative(r, axis_recalled=True)
    ev = next(e for e in r.events if e.kind == EventKind.INITIATIVE_DETERMINED)
    assert "fixed" not in ev.payload                      # 7.15 hold suspended -> a real roll
    assert ev.payload["axis_total"] == 9 and ev.payload["side"] == Side.AXIS.value
