"""Rule 20.43 / [17.6] -- REPLACEMENT-POINT TRAINING, the delay before an arrived Replacement Point
may be absorbed (Block 7.4).

Block 7.2b built the FLOW OUT (a depleted unit drawing Replacement Points from the pool to restore
TOE Strength) but SKIPPED the 20.43 Training delay -- it flagged, in engine._replacement_spend, that
"with no training clock we treat it as absorbable on arrival ... 7.4 adds the delay". This file pins
that delay:

  * [17.6] the Training Chart -- data + reader (scan-verified, transcription section 4, PDF p.100):
    Infantry 3 / Gun 1 / Tank,AC,Recce 6 / Commando 12 Operations Stages;
  * the maturation: an arrived point enters GameState.replacement_training and only reaches the
    absorbable GameState.replacement_pool after ceil(OpStages / 3) Game-Turns (3 OpStages = 1
    Game-Turn, rule 5.1), so it is NOT spendable the Game-Turn it arrives, and IS the next.

17.3 UNIT-MORALE Training (the CW unit climbing its Untrained Basic Morale to its designed rating) is
a SEPARATE track and is NOT built here -- its per-unit Untrained ratings live on the OA Sheets, which
are not in the rulebook scan (see the block report / flag). This file is the 20.43 RP track only.
"""
from __future__ import annotations

import math

import game.supply as supply
from game import replacements
from game.apply import apply
from game.engine import _Run, _replacement_production, _replacement_spend, _replacement_training
from game.events import Event, EventKind, Phase, Side
from game.state import GameState, StepRecord, SupplyUnit, Unit, VP
from game.movement import TerrainMap
from game.terrain import Mobility, Terrain


# --- [17.6] the TRAINING CHART: data + readers ------------------------------------------

def test_17_6_training_chart_opstages_match_the_scan():
    """The [17.6] Training Chart cell values, straight off the transcription (PDF p.100): the number
    of Operations Stages an arrived Replacement Point of each type must Train. 20.43's own inline
    table (Gun 1 / Infantry 3 / Tank,AC,Recce 6) agrees on every row it shares; [17.6] adds Commando."""
    assert replacements.training_opstages("infantry") == 3
    assert replacements.training_opstages("gun") == 1
    assert replacements.training_opstages("tank") == 6
    assert replacements.training_opstages("recce") == 6
    assert replacements.training_opstages("ac") == 6
    assert replacements.training_opstages("commando") == 12
    # the 17.3 UNIT-morale row (raise an untrained CW unit's Basic Morale one point per 6 OpStages,
    # rule 17.34); transcribed for completeness -- its consumer (the morale climb) is DEFERRED.
    assert replacements.training_opstages("commonwealth_unit") == 6


def test_training_delay_gt_is_ceil_opstages_over_three():
    """The whole Game-Turns an arrived point spends in Training before the once-per-Game-Turn
    Reorganization spend may absorb it: ceil(OpStages / 3), because a Game-Turn is 3 Operations
    Stages (rule 5.1) and the spend runs at the turn's head, before its stages. Infantry 3->1,
    Tank/Recce 6->2, Commando 12->4, Gun 1->1 (a sub-turn 1-OpStage training rounds UP to a full
    Game-Turn's wait at this per-Game-Turn grain -- no Gun producer is wired, so it is inert)."""
    assert replacements.training_delay_gt("infantry") == 1
    assert replacements.training_delay_gt("gun") == 1
    assert replacements.training_delay_gt("tank") == 2
    assert replacements.training_delay_gt("recce") == 2
    assert replacements.training_delay_gt("commando") == 4
    for t in ("infantry", "gun", "tank", "recce", "commando"):
        assert replacements.training_delay_gt(t) == math.ceil(replacements.training_opstages(t) / 3)


# --- the GameState training ledger (credit / mature / graduate) --------------------------

def _bare(*, turn: int = 10) -> GameState:
    """A minimal GameState carrying only what the training-ledger methods read."""
    return GameState(
        turn=turn, max_turns=111, phase=Phase.LOGISTICS, active_side=Side.SYSTEM, seed=1941,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0), supplies=(),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES}, stage=1)


def test_credit_training_is_an_immutable_accumulating_cohort():
    """state.credit_training never mutates: it returns a NEW state, an absent bucket reads empty,
    and two credits at the SAME maturity turn accumulate while different maturity turns stay
    separate cohorts."""
    st = _bare()
    assert st.replacement_training == {}
    once = st.credit_training("ALLIED/infantry", 11, 6)
    twice = once.credit_training("ALLIED/infantry", 11, 4)          # same maturity -> accumulate
    later = twice.credit_training("ALLIED/infantry", 13, 5)         # different maturity -> new cohort
    assert st.replacement_training == {}                            # original never mutated
    assert once.replacement_training == {"ALLIED/infantry": {11: 6}}
    assert twice.replacement_training == {"ALLIED/infantry": {11: 10}}
    assert later.replacement_training == {"ALLIED/infantry": {11: 10, 13: 5}}


def test_matured_training_sums_only_cohorts_due_by_the_given_turn():
    """matured_training(turn) is the points whose Training completes BY `turn` (mature_turn <= turn);
    a cohort maturing later is still in Training and is not counted."""
    st = (_bare().credit_training("ALLIED/infantry", 11, 6)
          .credit_training("ALLIED/infantry", 13, 5))
    assert st.matured_training(10) == {}                            # nothing due yet
    assert st.matured_training(11) == {"ALLIED/infantry": 6}        # the GT11 cohort only
    assert st.matured_training(13) == {"ALLIED/infantry": 11}       # both cohorts
    assert st.matured_training(99) == {"ALLIED/infantry": 11}       # never more than what exists


def test_graduate_training_drops_the_matured_cohorts_and_keeps_the_rest():
    """graduate_training(key, up_to_turn) removes exactly the cohorts of `key` matured by
    `up_to_turn`, leaving the still-training ones; a key emptied of cohorts drops out entirely."""
    st = (_bare().credit_training("ALLIED/infantry", 11, 6)
          .credit_training("ALLIED/infantry", 13, 5))
    after11 = st.graduate_training("ALLIED/infantry", 11)
    assert after11.replacement_training == {"ALLIED/infantry": {13: 5}}
    after13 = after11.graduate_training("ALLIED/infantry", 13)
    assert after13.replacement_training == {}                       # emptied key removed


# --- the apply folds: PRODUCED -> training, TRAINED -> pool -------------------------------

def _produced_event(points: int, *, mature_turn: int = 11) -> Event:
    return Event(0, 10, Phase.LOGISTICS, Side.ALLIED, "ALLIED/QM",
                 EventKind.REPLACEMENTS_PRODUCED,
                 {"side": Side.ALLIED.value, "type": "infantry", "points": points,
                  "plan_turn": 6, "arrival_turn": 10, "mature_turn": mature_turn}, (3, 4), 1)


def test_produced_fold_credits_the_training_ledger_not_the_pool():
    """RESTATED for Block 7.4: the FLOW IN no longer lands in the absorbable pool. An arrived point
    enters replacement_training at its maturity turn (arrival + the 20.43 delay); the absorbable
    replacement_pool stays empty until graduation. This is the 7.2b flag closed at the fold."""
    out = apply(_bare(), _produced_event(6, mature_turn=11))
    assert out.replacement_pool == {}                              # not absorbable on arrival
    assert out.replacement_training == {"ALLIED/infantry": {11: 6}}
    assert out.replacements_available("ALLIED/infantry") == 0


def test_a_none_cell_produced_fold_is_a_pure_identity():
    """A 'none' cell (points 0) still emits its certified 2d6 event, but the fold trains nobody: no
    pool credit AND no training cohort -- a pure identity, unlike the old 0-credited pool key."""
    out = apply(_bare(), _produced_event(0, mature_turn=11))
    assert out.replacement_pool == {}
    assert out.replacement_training == {}


def test_trained_fold_moves_matured_points_into_the_pool_and_clears_the_cohort():
    """apply(REPLACEMENTS_TRAINED{key, points, up_to_turn}) credits the absorbable pool by `points`
    and removes the cohorts of `key` matured by `up_to_turn` -- the graduation the spend then draws."""
    st = (_bare(turn=11).credit_training("ALLIED/infantry", 11, 6)
          .credit_training("ALLIED/infantry", 13, 5))
    ev = Event(0, 11, Phase.LOGISTICS, Side.ALLIED, "ALLIED/QM", EventKind.REPLACEMENTS_TRAINED,
               {"key": "ALLIED/infantry", "points": 6, "up_to_turn": 11}, (), 1)
    out = apply(st, ev)
    assert out.replacements_available("ALLIED/infantry") == 6      # matured -> absorbable
    assert out.replacement_training == {"ALLIED/infantry": {13: 5}}  # the GT13 cohort still trains


# --- the beats: production -> training -> graduation -------------------------------------

def _campaign_state(*, turn: int, seed: int = 1941, training=None) -> GameState:
    """A minimal campaign-shaped state the production/training beats read: the campaign gate on,
    a zeroed dump so the supply-conservation invariant is trivially true."""
    dump = SupplyUnit("AX-Port", Side.AXIS, (0, 0), ammo=0, fuel=0, stores=0, water=0)
    return GameState(
        turn=turn, max_turns=111, phase=Phase.LOGISTICS, active_side=Side.SYSTEM, seed=seed,
        weather="clear", vp=VP(),
        terrain=TerrainMap(terrain={(0, 0): Terrain.CLEAR}, fortifications={}),
        control={}, units=(), target_hex=(0, 0), supplies=(dump,),
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES}, stage=1,
        replacement_production=True, replacement_training=dict(training or {}))


def test_production_beat_lands_the_flow_in_in_training_maturing_next_game_turn():
    """engine._replacement_production credits the TRAINING ledger, at arrival + the infantry delay
    (turn + 1), not the absorbable pool. GT34 seed 1941 plans GT30 -> a nonzero cohort (lookup(30) == 5),
    maturing GT35."""
    r = _Run(_campaign_state(turn=34))
    _replacement_production(r)
    prod = [e for e in r.events if e.kind == EventKind.REPLACEMENTS_PRODUCED][0]
    pts = replacements.cw_infantry_lookup(30, sum(prod.rng_draws))
    assert pts > 0                                                  # a live, nonzero arrival
    assert r.state.replacement_pool == {}                          # NOT absorbable this turn
    assert r.state.replacement_training == {"ALLIED/infantry": {35: pts}}
    prod = [e for e in r.events if e.kind == EventKind.REPLACEMENTS_PRODUCED][0]
    assert prod.payload["mature_turn"] == 35                       # arrival 34 + delay 1


def test_graduation_beat_moves_matured_training_into_the_pool_before_the_spend():
    """engine._replacement_training is the graduation beat: at the turn a cohort matures it emits
    REPLACEMENTS_TRAINED, moving those points from replacement_training into the absorbable pool. A
    cohort maturing LATER is untouched."""
    r = _Run(_campaign_state(turn=11, training={"ALLIED/infantry": {11: 6, 13: 5}}))
    _replacement_training(r)
    trained = [e for e in r.events if e.kind == EventKind.REPLACEMENTS_TRAINED]
    assert len(trained) == 1 and trained[0].payload == {
        "key": "ALLIED/infantry", "points": 6, "up_to_turn": 11}
    assert r.state.replacements_available("ALLIED/infantry") == 6
    assert r.state.replacement_training == {"ALLIED/infantry": {13: 5}}


def test_graduation_beat_emits_nothing_when_no_cohort_has_matured():
    """Nothing due -> no REPLACEMENTS_TRAINED, no pool credit: a future-only training ledger is inert."""
    r = _Run(_campaign_state(turn=10, training={"ALLIED/infantry": {11: 6}}))
    _replacement_training(r)
    assert r.events == []
    assert r.state.replacement_pool == {}
    assert r.state.replacement_training == {"ALLIED/infantry": {11: 6}}


# --- THE DELAY, end to end: an arrived point is not spendable until it has trained -------

def _inf(uid, hex_, strength, max_toe):
    return Unit(uid, Side.ALLIED, hex_, (StepRecord("inf", strength),), mobility=Mobility.FOOT,
                cpa=10, stacking_points=1, oca=1, dca=2, is_combat=True, max_toe=max_toe,
                nationality="CW")


def _spend_state(units, *, turn: int, training=None):
    hexes = {u.hex for u in units} | {(0, 0)}
    tmap = TerrainMap(terrain={h: Terrain.CLEAR for h in hexes}, fortifications={})
    return GameState(
        turn=turn, max_turns=111, phase=Phase.ORGANIZATION, active_side=Side.SYSTEM, seed=1941,
        weather="clear", vp=VP(), terrain=tmap, control={}, units=tuple(units), target_hex=(0, 0),
        supplies=(), consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES}, stage=1,
        replacement_production=True, replacement_training=dict(training or {}))


def test_an_arrived_point_is_not_absorbable_the_turn_it_arrives_but_is_the_next():
    """The 20.43 delay, end to end. A 6-point Infantry cohort maturing GT11 sits in Training on GT10:
    graduation moves nothing, the spend finds an empty pool, the depleted battalion is NOT rebuilt.
    On GT11 the cohort graduates and the SAME beats rebuild it. This is exactly what Block 7.2b's
    'absorbable on arrival' skipped."""
    u10 = _inf("A", (1, 1), strength=4, max_toe=8)                 # deficit 4
    r10 = _Run(_spend_state([u10], turn=10, training={"ALLIED/infantry": {11: 6}}))
    _replacement_training(r10)
    _replacement_spend(r10)
    assert r10.state.unit("A").strength == 4                       # STILL depleted -- point untrained
    assert r10.state.replacements_available("ALLIED/infantry") == 0

    u11 = _inf("A", (1, 1), strength=4, max_toe=8)
    r11 = _Run(_spend_state([u11], turn=11, training={"ALLIED/infantry": {11: 6}}))
    _replacement_training(r11)
    _replacement_spend(r11)
    assert r11.state.unit("A").strength == 8                       # rebuilt once the point trained
    assert r11.state.replacements_available("ALLIED/infantry") == 2  # 6 arrived - 4 absorbed


def test_the_training_ledger_is_deterministic_under_replay():
    """Same seed -> byte-identical production + graduation folds (determinism binds absolutely)."""
    from game.events import event_to_dict

    def _fold(turn):
        r = _Run(_campaign_state(turn=turn, training={"ALLIED/infantry": {turn: 6}}))
        _replacement_production(r)
        _replacement_training(r)
        return [event_to_dict(e) for e in r.events]

    assert _fold(34) == _fold(34)


# --- the campaign gate: the benchmarks never train (byte-identical) ----------------------

def test_the_training_beats_are_a_campaign_only_subsystem():
    """Both beats gate on replacement_production, which ONLY game.scenario.campaign sets. With it
    off, production and graduation return at their first guard -- no event, no ledger -- so every
    Desert Fox benchmark stays byte-identical (this is why baselines.py re-baselines NEITHER sig)."""
    from dataclasses import replace as _replace
    off = _replace(_campaign_state(turn=34, training={"ALLIED/infantry": {34: 6}}),
                   replacement_production=False)
    rp = _Run(off)
    _replacement_production(rp)
    _replacement_training(rp)
    assert rp.events == []
