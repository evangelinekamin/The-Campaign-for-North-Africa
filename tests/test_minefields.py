"""[26.0] MINEFIELDS + [24.3]/[24.4] CONSTRUCTING MINEFIELDS/FORTIFICATIONS -- Phase 8.2.

Transcribed (scan-verified twice: scratchpad/port/transcriptions/26-minefields-and-24-
construction.md, and independently while wiring game/minefields.py against PDF p.38/p.36/p.70/
p.104) from:

  [26.0] MINEFIELDS -- existence (26.1: real/dummy, Friendly/Enemy), effects (26.2: the [8.37]
    entry-CP surcharge, the engineer-escort discount, the [26.25] destruction roll, the [26.26]/
    note-13 Anti-Armor/Close-Assault L1 defensive shift).
  [24.3] CONSTRUCTING MINEFIELDS -- one Op-Stage, 15 Stores + 15 Ammo (real) or 3 Stores (dummy),
    laid by a general-Engineering-capable unit ('ENGINEER', distinct from 'RAIL'/'ROAD').
  [24.4] CONSTRUCTING FORTIFICATIONS -- three Construction Segments, 30 Stores, an Engineering
    unit PLUS an Infantry battalion (3+ TOE), capped at Level 2 (field) or the hex's own printed
    Major-City cap (25.12).

FLAGGED, not silently assumed: no OOB in this repo seeds a unit with engineer='ENGINEER' (or
CW-HQ-Engineering) -- see game.minefields.is_engineer and game.construction.builds_engineering's
docstrings. Every test below builds its own synthetic Engineer/Infantry counters to exercise the
mechanism directly, exactly as game.minefields' module docstring says it must be exercised until
that OOB gap closes.

The OWNER RULINGS this file pins the ENGINE'S side of (data/minefields.json carries each, and the
conflicting text, in full):
  #2 24.35's minefield terrain list (Clear/Gravel/Rough) over the Construction Chart's
     Clear/Gravel/Salt-Marsh.
  #3 24.44's fortification exclusion list (mountain, salt marsh, desert, major city, delta) over
     the Construction Chart's shorter salt-marsh/delta/major-city cell.

NOT a ruling any more: the escorted entry cost. It was flagged as OWNER RULING #1 on the belief
that no chart carried the escorted cells; [6.3] CAPABILITY POINT EXPENDITURE SUMMARY (PDF p.96)
prints all seven, and the engine now implements them verbatim -- 2 CP for escorted non-Mot into an
Enemy belt, 4 for escorted Mot, 0 into a Friendly belt.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import combat, combat_tables as ct, construction, minefields as mf, supply
from game.engine import _Run, _construction, _movement, run
from game.events import Control, EventKind, Phase, Side
from game.movement import TerrainMap, reachable
from game.policy import BuildOrder, MoveOrder, Policy
from game.state import GameState, Minefield, StepRecord, SupplyUnit, Unit, VP
from game.terrain import Mobility, Terrain

# A short east-west line, CLEAR throughout unless a test overrides a hex -- long enough for a
# 2-hex move and for an engineer/infantry pair to stand together.
H = ((0, 0), (0, 1), (0, 2))


def _unit(uid, side, hx, *, mobility=Mobility.MOTORIZED, cpa=20, engineer='', is_combat=True,
         is_tank=False, dca=4, steps=1, fuel=999, water=999) -> Unit:
    # fuel=999/water=999: every unit in these tests carries its own 49.14 tank and 52.4 water --
    # so a MoveOrder never trips the (unrelated) 49.15 fuel gate, and a multi-turn construction
    # test never trips 52.53's water-shortfall attrition mid-build. These tests are about rule
    # 26/24.3/24.4, not rules 49/52.
    return Unit(uid, side, hx, (StepRecord("x", steps),), mobility, cpa, 1, 4, dca,
                engineer=engineer, is_combat=is_combat, is_tank=is_tank, fuel=fuel, water=water)


def _state(units=(), supplies=(), *, terrain=None, control=None, minefields_=None,
          construction_=None, max_turns=1) -> GameState:
    tmap = TerrainMap(terrain=terrain or {h: Terrain.CLEAR for h in H})
    supplies = tuple(supplies)
    units = tuple(units)
    initial = {c: sum(getattr(s, c.lower()) for s in supplies)
                    + sum(getattr(u, c.lower()) for u in units)
              for c in supply.COMMODITIES}
    return GameState(
        turn=1, max_turns=max_turns, phase=Phase.WEATHER, active_side=Side.SYSTEM, seed=7,
        weather="normal", vp=VP(),
        terrain=tmap, control=control or {}, units=units, target_hex=H[-1],
        supplies=supplies,
        consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply=initial,
        minefields=dict(minefields_ or {}),
        construction=dict(construction_ or {}))


class _Build(Policy):
    """Issues exactly the orders it is handed, filtered to its own side (test_construction.py's
    own _Build, restated here so this file stands alone)."""

    def __init__(self, orders=(), moves=()):
        self._orders, self._moves = list(orders), list(moves)

    def _mine(self, state, uid, side):
        u = state.unit(uid)
        return u is not None and u.side == side

    def movement(self, state, side):
        return [o for o in self._moves if self._mine(state, o.unit_id, side)]

    def combat(self, state, side):
        return []

    def construction(self, state, side):
        return [o for o in self._orders
                if o.unit_ids and self._mine(state, o.unit_ids[0], side)]


def _run(units, supplies, orders=(), moves=(), **kw):
    pol = _Build(orders, moves)
    return run(_state(units, supplies, **kw), pol, pol)


def _pin_die(r: _Run, subsystem: str, value: int) -> None:
    class _Fixed(random.Random):
        def randint(self, a, b):
            return value
    r.dice.load(subsystem, _Fixed())


# --- [26.21]/[26.22]/[26.24] ENTRY CP SURCHARGE (pure) -------------------------------------------

def test_friendly_minefield_surcharge_by_mobility():
    st = _state(minefields_={H[1]: Minefield(Side.AXIS, real=True)})
    assert mf.entry_surcharge(st, Side.AXIS, Mobility.FOOT, 20, H[0], H[1]) == 1     # non-Mot
    assert mf.entry_surcharge(st, Side.AXIS, Mobility.MOTORIZED, 20, H[0], H[1]) == 4  # Mot


def test_enemy_minefield_non_mot_is_flat_four():
    st = _state(minefields_={H[1]: Minefield(Side.AXIS, real=True)})
    assert mf.entry_surcharge(st, Side.ALLIED, Mobility.FOOT, 20, H[0], H[1]) == 4


def test_enemy_minefield_mot_spends_the_entire_cpa():
    """26.21's own worked example: 'an artillery unit would expend 15 Capability Points to enter
    an Enemy minefield' -- its whole 15-point CPA, not a flat number."""
    st = _state(minefields_={H[1]: Minefield(Side.AXIS, real=True)})
    assert mf.entry_surcharge(st, Side.ALLIED, Mobility.MOTORIZED, 15, H[0], H[1]) == 15
    assert mf.entry_surcharge(st, Side.ALLIED, Mobility.MOTORIZED, 40, H[0], H[1]) == 40


def test_engineer_escort_discount_is_two_non_mot_and_four_mot():
    """[6.3] (PDF p.96), the only chart in the book that prints the escorted cells: 'Enter an
    enemy minefield hex: Non-motorized unit WITH an Eng unit 2 + TEC / Motorized unit WITH an Eng
    unit 4 + TEC.' The discount REPLACES the unescorted cost (26.24: "rather than their listed
    cost"), so a Mot mover pays 4 rather than its whole CPA, and a foot mover pays 2 rather than 4.

    RESTATED, not weakened (port rule 5): this test previously asserted 4 for BOTH classes, which
    enshrined a 2-CP overcharge on escorted infantry -- the engine had read only the Terrain
    Effects Chart, which is silent on the escorted case, and had implemented 26.24's motorized
    figure flat across both."""
    escort = _unit("EN", Side.ALLIED, H[0], engineer='ENGINEER', is_combat=False)
    st = _state([escort], minefields_={H[1]: Minefield(Side.AXIS, real=True)})
    assert mf.entry_surcharge(st, Side.ALLIED, Mobility.MOTORIZED, 40, H[0], H[1]) == 4
    assert mf.entry_surcharge(st, Side.ALLIED, Mobility.FOOT, 40, H[0], H[1]) == 2


def test_scorpion_battalion_escorts_only_while_it_holds_six_toe():
    """[23.15]: the 42/44 RTR "are engineer units but possess only anti-minefield capabilities...
    considered to possess engineer unit status WHILE IT CONTAINS AT LEAST SIX Scorpion TOE Strength
    Points". So a full flail battalion buys the escort cells; one ground down to five does not."""
    full = _unit("SC42", Side.ALLIED, H[0], engineer='SCORPION', is_tank=True, steps=10)
    spent = _unit("SC44", Side.ALLIED, H[0], engineer='SCORPION', is_tank=True, steps=5)
    belt = {H[1]: Minefield(Side.AXIS, real=True)}
    assert mf.entry_surcharge(_state([full], minefields_=belt),
                              Side.ALLIED, Mobility.FOOT, 40, H[0], H[1]) == 2
    assert mf.entry_surcharge(_state([spent], minefields_=belt),
                              Side.ALLIED, Mobility.FOOT, 40, H[0], H[1]) == 4


def test_rail_and_road_companies_are_not_engineers_for_rule_26():
    """[23.13]: the NZRRC companies are "used SOLELY for the construction and repair of Railroads"
    and the 1 SA Road Construction Battalion "solely for Road work" (24.61 repeats it: "may be used
    only for RR work"). Neither escorts a mover through a belt nor clears one."""
    belt = {H[1]: Minefield(Side.AXIS, real=True)}
    for role in ('RAIL', 'ROAD', ''):
        gang = _unit("X", Side.ALLIED, H[0], engineer=role, is_combat=False)
        st = _state([gang], minefields_=belt)
        assert mf.entry_surcharge(st, Side.ALLIED, Mobility.FOOT, 40, H[0], H[1]) == 4
        assert not mf.is_engineer(gang)


def test_hq_with_engineering_escorts_either_side():
    """[23.14]/[23.21]: an HQ "with a letter E next to their Stacking Points" has Engineering
    capability, and 23.21's escort names "any Engineer unit (OR HQ unit with Engineering
    capability)" without restricting it by side."""
    hq = _unit("HQ", Side.AXIS, H[0], engineer='HQ_ENGINEER', is_combat=False)
    st = _state([hq], minefields_={H[1]: Minefield(Side.ALLIED, real=True)})
    assert mf.entry_surcharge(st, Side.AXIS, Mobility.MOTORIZED, 40, H[0], H[1]) == 4


def test_engineer_escort_makes_a_friendly_minefield_free():
    escort = _unit("EN", Side.AXIS, H[0], engineer='ENGINEER', is_combat=False)
    st = _state([escort], minefields_={H[1]: Minefield(Side.AXIS, real=True)})
    assert mf.entry_surcharge(st, Side.AXIS, Mobility.MOTORIZED, 40, H[0], H[1]) == 0.0


def test_no_minefield_no_surcharge():
    st = _state()
    assert mf.entry_surcharge(st, Side.AXIS, Mobility.MOTORIZED, 40, H[0], H[1]) == 0.0


def test_dummy_costs_the_same_as_real():
    """[26.23]: 'the costs to enter a dummy minefield are the same as those for a real one.'"""
    real = _state(minefields_={H[1]: Minefield(Side.AXIS, real=True)})
    dummy = _state(minefields_={H[1]: Minefield(Side.AXIS, real=False)})
    for st in (real, dummy):
        assert mf.entry_surcharge(st, Side.ALLIED, Mobility.FOOT, 20, H[0], H[1]) == 4


# --- [8.37] BREAKDOWN VALUE surcharge (pure) ------------------------------------------------------

def test_enemy_minefield_breakdown_surcharge_is_two_friendly_is_zero():
    st = _state(minefields_={H[1]: Minefield(Side.AXIS, real=True)})
    assert mf.breakdown_surcharge(st, Side.ALLIED, H[1]) == 2.0
    assert mf.breakdown_surcharge(st, Side.AXIS, H[1]) == 0.0
    assert mf.breakdown_surcharge(st, Side.ALLIED, H[0]) == 0.0    # no belt there


# --- [26.26]/[8.37] note 13 COMBAT SHIFT (pure) ---------------------------------------------------

def test_minefield_adds_l1_to_anti_armor_and_close_assault():
    base_aa = ct.anti_armor_terrain_shift(Terrain.CLEAR, 0)
    mined_aa = ct.anti_armor_terrain_shift(Terrain.CLEAR, 0, minefield=True)
    assert mined_aa == base_aa - 1

    plain = combat.resolve(attacker_raw=20, defender_raw=10, def_terrain=Terrain.CLEAR,
                           atk_roll=33, def_roll=33)
    mined = combat.resolve(attacker_raw=20, defender_raw=10, def_terrain=Terrain.CLEAR,
                           atk_roll=33, def_roll=33, in_enemy_minefield=True)
    assert mined.column == plain.column - 1


def test_the_shift_belongs_to_whoever_laid_the_belt():
    """[8.37]'s two Combat Adjustment rows are read from the NON-PHASING side: Friendly Minefield
    = L1 Anti-Armor / L1 Close Assault, Enemy Minefield = "-" / "-". So a belt the DEFENDER laid,
    standing on the hex being assaulted, gives him his column; the very same hex mined by the
    ATTACKER gives nobody anything."""
    target = H[1]
    defenders_own = _state(minefields_={target: Minefield(Side.AXIS, real=True)})
    attackers_own = _state(minefields_={target: Minefield(Side.ALLIED, real=True)})
    assert mf.defender_shift(defenders_own, Side.AXIS, target, [H[0]])
    assert not mf.defender_shift(attackers_own, Side.AXIS, target, [H[0]])


def test_assaulting_forces_standing_in_the_defenders_belt_grant_the_shift():
    """[8.37] note 13, verbatim: "If ASSAULTING forces are in an Enemy minefield, the non-Phasing
    forces receive L1 shifts for Anti-Armor and Close Assault if not already receiving them for
    occupying a Friendly minefield." 26.26 says it again from the other end ("on any anti-tank or
    close assault combat in which the attacking units are in an Enemy minefield... the defending
    Player adjusts all columns one in his favor"). This is the Devil's Gardens case: troops wading
    into a laid belt to assault the position behind it. The target hex itself carries nothing."""
    st = _state(minefields_={H[0]: Minefield(Side.AXIS, real=True)})     # under the ATTACKERS
    assert mf.defender_shift(st, Side.AXIS, H[1], [H[0]])                # defender (Axis) laid it
    assert not mf.defender_shift(st, Side.ALLIED, H[1], [H[0]])          # attacker's own belt: no


def test_the_shift_is_one_column_not_two():
    """note 13's grant is explicitly "IF NOT ALREADY RECEIVING them for occupying a Friendly
    minefield" -- a defender standing in his own belt while the attackers wade through another of
    his own belts still gets exactly one column (defender_shift is a boolean, not a count)."""
    st = _state(minefields_={H[0]: Minefield(Side.AXIS, real=True),
                             H[1]: Minefield(Side.AXIS, real=True)})
    assert mf.defender_shift(st, Side.AXIS, H[1], [H[0]]) is True


# --- [24.3]/[24.35]/[24.36] WHERE A MINEFIELD MAY BE LAID (pure) ---------------------------------

def test_minefield_buildable_terrain_gate():
    """OWNER RULING NEEDED #2: this engine follows 24.35's prose (Clear/Gravel/Rough), so a
    Mountain hex is barred and (per the ruling) so is a Salt Marsh hex, though the Construction
    Chart names Salt Marsh instead of Rough."""
    terrain = {H[0]: Terrain.CLEAR, H[1]: Terrain.ROUGH, H[2]: Terrain.MOUNTAIN}
    st = _state(terrain=terrain)
    assert construction.minefield_buildable(st, Side.AXIS, H[1])       # Rough: allowed (24.35)
    assert not construction.minefield_buildable(st, Side.AXIS, H[2])   # Mountain: barred


def test_minefield_buildable_bars_enemy_controlled_and_already_mined():
    st = _state(control={H[1]: Control.ALLIED}, minefields_={H[0]: Minefield(Side.AXIS, True)})
    assert not construction.minefield_buildable(st, Side.AXIS, H[1])   # 24.36 enemy-controlled
    assert not construction.minefield_buildable(st, Side.AXIS, H[0])   # 24.35 one per hex


# --- [24.3] CONSTRUCTION: laying a real and a dummy minefield (engine-level) ----------------------

def _dump(side, hx, **kw):
    # water=999: the 52.5 water beat runs off this dump every stage (supply.plan_draw's abstract
    # trace, unrelated to rule 26) -- generous headroom keeps a multi-stage construction test from
    # tripping 52.53 attrition on units that have nothing to do with minefields or fortifications.
    return SupplyUnit(f"{side.value}-D-{hx}", side, hx, ammo=kw.pop("ammo", 0),
                      fuel=0, stores=kw.pop("stores", 0), water=kw.pop("water", 999),
                      constructed=True)


def _engineer_spend(res, commodity):
    """Store/Ammo Points the /Engineers actor (game.engine._construction) spent -- as against
    the same dump's ordinary 50/51 upkeep draws, which ride a DIFFERENT actor and would otherwise
    pollute a raw SUPPLY_CONSUMED sum (test_construction.py's own _stores_spent_on_construction
    idiom, restated here for both commodities)."""
    return sum(e.payload["qty"] for e in res.events
              if e.kind == EventKind.SUPPLY_CONSUMED and e.payload["commodity"] == commodity
              and e.actor.endswith("/Engineers"))


def test_real_minefield_costs_fifteen_and_fifteen_and_completes_in_one_stage():
    eng = _unit("EN", Side.AXIS, H[0], engineer='ENGINEER', is_combat=False)
    # Generous headroom over the 15+15 construction needs: the engineer's own 50/51 upkeep
    # draws a little from this SAME dump every Logistics beat, unrelated to rule 26.
    dump = _dump(Side.AXIS, H[0], stores=115, ammo=115)
    res = _run([eng], [dump], [BuildOrder(construction.REAL_MINEFIELD, H[0], (eng.id,))])
    laid = [e for e in res.events if e.kind == EventKind.MINEFIELD_CONSTRUCTED]
    assert laid and laid[0].payload["real"] is True
    belt = res.final.minefields[H[0]]
    assert belt.side == Side.AXIS and belt.real is True
    assert (_engineer_spend(res, supply.STORES), _engineer_spend(res, supply.AMMO)) == (15, 15)
    assert not res.final.construction, "the Under Construction marker was not lifted (24.32)"


def test_dummy_minefield_costs_only_three_stores_no_ammo():
    eng = _unit("EN", Side.AXIS, H[0], engineer='ENGINEER', is_combat=False)
    dump = _dump(Side.AXIS, H[0], stores=103, ammo=100)
    res = _run([eng], [dump], [BuildOrder(construction.DUMMY_MINEFIELD, H[0], (eng.id,))])
    laid = [e for e in res.events if e.kind == EventKind.MINEFIELD_CONSTRUCTED]
    assert laid and laid[0].payload["real"] is False
    assert res.final.minefields[H[0]].real is False
    assert (_engineer_spend(res, supply.STORES), _engineer_spend(res, supply.AMMO)) == (3, 0)


def test_only_engineering_capable_units_may_lay_a_minefield():
    """[24.31]/[24.17]: "any Engineering unit (or Commonwealth HQ Engineers)" / "EBn, ECoy or
    CHQ-E". RAIL and ROAD are engineers for their own one job only (23.13 "solely", 24.61 "only
    for RR work"), and a Scorpion battalion "possesses only anti-minefield capabilities" (23.15),
    so it clears belts and lays none."""
    dump = _dump(Side.AXIS, H[0], stores=15, ammo=15)
    for bad_role in ('RAIL', 'ROAD', 'SCORPION', ''):
        bad = _unit("X", Side.AXIS, H[0], engineer=bad_role, is_combat=False, steps=10)
        res = _run([bad], [dump], [BuildOrder(construction.REAL_MINEFIELD, H[0], (bad.id,))])
        assert not res.final.minefields, f"engineer={bad_role!r} laid a minefield: 24.31 forbids it"
        assert any(e.kind == EventKind.ORDER_REJECTED for e in res.events)


def test_only_a_commonwealth_engineering_hq_may_lay_a_minefield():
    """The asymmetry the book states twice: [24.17]'s Build rows for Real/Fake Minefield name
    "EBn, ECoy or CHQ-E" -- and its key reads CHQ-E = "ALLIED headquarters with engineering
    capability" -- while 24.31's prose says "any Engineering unit (or COMMONWEALTH HQ Engineers)".
    The Fortification row's AnyE, by contrast, is "any... headquarters unit with engineering
    capability", either side. So an Axis HQ-E raises walls and sows no mines."""
    cw_hq = _unit("CHQ", Side.ALLIED, H[0], engineer='HQ_ENGINEER', is_combat=False)
    ax_hq = _unit("AHQ", Side.AXIS, H[0], engineer='HQ_ENGINEER', is_combat=False)
    st = _state([cw_hq, ax_hq])
    assert construction.lays_minefield(cw_hq)
    assert not construction.lays_minefield(ax_hq)
    assert construction.builds_engineering(ax_hq), "an Axis HQ-E is still AnyE for 24.42"
    assert construction.can_lay_minefield(st, Side.ALLIED, cw_hq, H[0])
    assert not construction.can_lay_minefield(st, Side.AXIS, ax_hq, H[0])


def test_24_46_bars_a_second_project_on_a_hex_building_a_fortification():
    """[24.46], verbatim: "No other construction -- of any type -- may take place in a hex which is
    undergoing fortification construction." Both directions, because a minefield begun first would
    then be "taking place in" the hex the moment the fortification started."""
    st = _state(construction_={(construction.FORT, H[0]): 1})
    assert not construction.minefield_buildable(st, Side.AXIS, H[0])
    assert not construction.rail_buildable(st, Side.AXIS, H[0])
    other = _state(construction_={(construction.REAL_MINEFIELD, H[0]): 1})
    assert not construction.fort_buildable(other, Side.AXIS, H[0])
    assert construction.fort_buildable(_state(), Side.AXIS, H[0]), "an idle hex is buildable"


def test_a_fort_under_construction_rejects_a_concurrent_minefield_order():
    eng = _unit("EN", Side.AXIS, H[0], engineer='ENGINEER', is_combat=False)
    inf = _unit("PBI", Side.AXIS, H[0], mobility=Mobility.FOOT, cpa=10, steps=3)
    eng2 = _unit("EN2", Side.AXIS, H[0], engineer='ENGINEER', is_combat=False)
    bystander = _unit("BY", Side.ALLIED, H[2], mobility=Mobility.FOOT, cpa=10)
    dump = _dump(Side.AXIS, H[0], stores=200, ammo=100)
    res = _run([eng, inf, eng2, bystander], [dump, _dump(Side.ALLIED, H[2], stores=50)],
              [BuildOrder(construction.FORT, H[0], (eng.id, inf.id)),
               BuildOrder(construction.REAL_MINEFIELD, H[0], (eng2.id,))], max_turns=1)
    assert not res.final.minefields, "24.46: no belt may be laid under a fortification going up"
    assert any(e.kind == EventKind.ORDER_REJECTED and "24.46" in e.payload.get("reason", "")
              for e in res.events)


# --- [26.13]/[24.38] CLEARING A MINEFIELD (engine-level) -------------------------------------------

def test_engineer_clears_a_minefield_in_one_cp_free_opstage():
    eng = _unit("EN", Side.AXIS, H[0], engineer='ENGINEER', is_combat=False)
    res = _run([eng], [], [BuildOrder(construction.CLEAR_MINEFIELD, H[0], (eng.id,))],
              minefields_={H[0]: Minefield(Side.ALLIED, real=True)})
    assert H[0] not in res.final.minefields
    assert any(e.kind == EventKind.MINEFIELD_CLEARED for e in res.events)


def test_a_scorpion_battalion_clears_a_belt_and_a_spent_one_does_not():
    """[24.18] Demolition Chart, Real Minefield row: "Clear | Any E OR TANK BN WITH 6+ TOE OF
    SCORPIONS | 1 Op Stage" -- the second half of that cell, which the 42nd and 44th RTR carry
    into the campaign at GT99 (data/reinforcements_campaign.json) and into every El Alamein
    scenario. 23.15 puts the floor at six: below it the battalion is a tank battalion again."""
    belt = {H[0]: Minefield(Side.AXIS, real=True)}
    full = _unit("SC42", Side.ALLIED, H[0], engineer='SCORPION', is_tank=True, steps=10)
    # An idle Axis bystander: the Completion Step needs a SECOND Construction Segment to run, and
    # the engine would otherwise end the run by annihilation the moment one side has no units.
    # (H[1], not H[2]: H[2] is the scenario's target_hex, and an Axis unit standing on it would end
    # the run by capture before the Completion Step ever ran.)
    bystander = _unit("BY", Side.AXIS, H[1], mobility=Mobility.FOOT, cpa=10)
    res = _run([full, bystander], [_dump(Side.AXIS, H[1], stores=50)],
              [BuildOrder(construction.CLEAR_MINEFIELD, H[0], (full.id,))],
              minefields_=belt, max_turns=2)
    assert H[0] not in res.final.minefields

    spent = _unit("SC44", Side.ALLIED, H[0], engineer='SCORPION', is_tank=True, steps=5)
    st = _state([spent], minefields_=belt)
    assert not construction.can_clear_minefield(st, Side.ALLIED, spent, H[0])


def test_the_oob_actually_seeds_the_two_scorpion_battalions():
    """The one anti-minefield capability in this slice that is REACHABLE by a live scenario: the
    42/44 RTR arrive on the campaign Reinforcement Track (GT99) carrying engineer='SCORPION' off
    their model row, so [24.18]'s clearing route is not dead code."""
    from game import scenario
    st = scenario.campaign(seed=1)
    flails = [u for u in st.units if u.engineer == 'SCORPION']
    assert len(flails) == 2, [u.id for u in flails]
    assert all(mf.is_scorpion_engineer(u) for u in flails), "arriving below the 23.15 six-TOE floor"
    assert all(not construction.lays_minefield(u) for u in flails)   # 23.15: anti-minefield ONLY


def test_23_11_binds_engineer_counters_and_never_a_scorpion_battalion():
    """[23.11] (scan, PDF p.35, verbatim): "Engineer counters have no real combat value, nor do
    they exert Zones of Control. They are NOT COMBAT UNITS IN ANY WAY, SHAPE, OR FORM. Engineer
    units may never enter Enemy-controlled hexes voluntarily."

    That Case is written about the counters 23.0 enumerates -- Engineer Battalions, Engineer
    companies, HQs with Engineer capability -- plus 23.13's two rail/road engineering companies.
    It is NOT written about a 23.15 Scorpion battalion, which is a Commonwealth TANK battalion
    (is_combat=True, 8 TOE of flails) granted engineer status strictly "for ANTI-MINEFIELD
    capabilities". Reading 23.11 onto it would forbid the one Commonwealth unit whose whole
    purpose is to breach INTO an Axis position -- and the engine's gate did exactly that, because
    it keyed on `u.engineer` being truthy and the 8.2 slice had just tagged the flails 'SCORPION'.
    """
    for role in ('ENGINEER', 'HQ_ENGINEER', 'RAIL', 'ROAD'):
        assert mf.is_engineer_counter(_unit("E", Side.ALLIED, H[0], engineer=role)), role
    assert not mf.is_engineer_counter(
        _unit("SC42", Side.ALLIED, H[0], engineer='SCORPION', is_tank=True, steps=10))
    assert not mf.is_engineer_counter(_unit("PBI", Side.ALLIED, H[0]))     # no engineer row at all


def test_a_scorpion_battalion_may_advance_into_an_enemy_controlled_hex():
    """The live half of the Case above, through the engine's own movement gate: a flail battalion
    ordered onto an Axis-controlled hex MOVES (23.15/23.11), while a genuine Engineer counter
    given the identical order is rejected. Both are on the board at once so the two verdicts come
    out of one Movement Phase and one board."""
    flail = _unit("SC42", Side.ALLIED, H[0], engineer='SCORPION', is_tank=True, steps=10)
    sapper = _unit("EN", Side.ALLIED, H[0], engineer='ENGINEER', is_combat=False)
    r = _Run(_state([flail, sapper], control={H[1]: Control.AXIS}))
    policy = _Build(moves=[MoveOrder(flail.id, H[1]), MoveOrder(sapper.id, H[1])])
    _movement(r, {Side.ALLIED: policy, Side.AXIS: policy}, Side.ALLIED)
    moved = {e.payload["unit_id"] for e in r.events if e.kind == EventKind.UNIT_MOVED}
    rejected = {e.payload.get("unit_id") for e in r.events if e.kind == EventKind.ORDER_REJECTED}
    assert flail.id in moved, "23.15: a Scorpion battalion is a tank battalion, not an engineer counter"
    assert sapper.id in rejected, "23.11: an Engineer counter may not voluntarily enter one"


# --- [24.4] CONSTRUCTION: a fortification Level (engine-level) -------------------------------------

def test_fortification_needs_engineer_and_infantry_together_thirty_stores_three_stages():
    eng = _unit("EN", Side.AXIS, H[0], engineer='ENGINEER', is_combat=False)
    inf = _unit("PBI", Side.AXIS, H[0], mobility=Mobility.FOOT, cpa=10, steps=3)
    # A token Allied unit, far from the build site and idle: FORT needs a FOURTH Construction
    # Segment call to observe completion (three to bank progress, one more to complete it,
    # 24.42), and the engine's annihilation check would otherwise end the run after stage 1 the
    # moment one side has no living units at all.
    bystander = _unit("BY", Side.ALLIED, H[2], mobility=Mobility.FOOT, cpa=10)
    dump = _dump(Side.AXIS, H[0], stores=130, ammo=100)
    bystander_dump = _dump(Side.ALLIED, H[2], stores=50, ammo=50)
    res = _run([eng, inf, bystander], [dump, bystander_dump],
              [BuildOrder(construction.FORT, H[0], (eng.id, inf.id))], max_turns=2)
    built = [e for e in res.events if e.kind == EventKind.FORT_LEVEL_BUILT]
    assert built and built[0].payload["level"] == 1        # the first Level completes...
    # ...and with the standing order kept in force for the rest of the two-turn budget, the SAME
    # engineer/infantry pair goes straight on to a second Level (24.48's field cap is TWO, not
    # one) -- proving the cap holds rather than weakening this test to stop watching after Level 1.
    assert res.final.fort_level(H[0]) == mf.FORT_FIELD_CAP
    assert _engineer_spend(res, supply.STORES) == 2 * mf.FORT_STORES
    advanced = [e for e in res.events if e.kind == EventKind.CONSTRUCTION_ADVANCED
               and e.payload["item"] == construction.FORT and e.payload["progress"]]
    assert [e.payload["progress"] for e in advanced] == [1, 2, 3, 1, 2, 3]


def test_fortification_excluded_terrain_and_field_cap():
    terrain = {H[0]: Terrain.DESERT, H[1]: Terrain.CLEAR}
    st = _state(terrain=terrain)
    assert not construction.fort_buildable(st, Side.AXIS, H[0])    # 24.44: Desert excluded
    assert construction.fort_buildable(st, Side.AXIS, H[1])
    capped = _state(terrain=terrain, construction_=None)
    # simulate a field fort already at its Level-2 cap
    from dataclasses import replace
    capped = replace(capped, fort_levels={H[1]: mf.FORT_FIELD_CAP})
    assert not construction.fort_buildable(capped, Side.AXIS, H[1])   # 24.48: field cap is 2


# --- [26.25] THE DESTRUCTION ROLL (engine-level, dice pinned) --------------------------------------

def test_unescorted_vehicle_hit_on_five_or_six_loses_a_step():
    tank = _unit("TK", Side.ALLIED, H[0], mobility=Mobility.VEHICLE, cpa=40)
    r = _Run(_state([tank], minefields_={H[1]: Minefield(Side.AXIS, real=True)}))
    _pin_die(r, "minefield", 5)
    policy = _Build(moves=[MoveOrder("TK", H[1])])
    _movement(r, {Side.ALLIED: policy, Side.AXIS: policy}, Side.ALLIED)
    hits = [e for e in r.events if e.kind == EventKind.MINEFIELD_TRIGGERED]
    losses = [e for e in r.events if e.kind == EventKind.STEP_LOST and e.payload.get("role") == "minefield"]
    assert hits and hits[0].payload["hit"] is True
    assert losses and losses[0].payload["amount"] == 1


def test_unescorted_vehicle_miss_on_one_to_four_loses_nothing():
    tank = _unit("TK", Side.ALLIED, H[0], mobility=Mobility.VEHICLE, cpa=40)
    r = _Run(_state([tank], minefields_={H[1]: Minefield(Side.AXIS, real=True)}))
    _pin_die(r, "minefield", 1)
    policy = _Build(moves=[MoveOrder("TK", H[1])])
    _movement(r, {Side.ALLIED: policy, Side.AXIS: policy}, Side.ALLIED)
    hits = [e for e in r.events if e.kind == EventKind.MINEFIELD_TRIGGERED]
    losses = [e for e in r.events if e.kind == EventKind.STEP_LOST and e.payload.get("role") == "minefield"]
    assert hits and hits[0].payload["hit"] is False
    assert not losses


def test_escorted_vehicle_rolls_no_destruction_die_at_all():
    tank = _unit("TK", Side.ALLIED, H[0], mobility=Mobility.VEHICLE, cpa=40)
    escort = _unit("EN", Side.ALLIED, H[0], engineer='ENGINEER', is_combat=False)
    r = _Run(_state([tank, escort], minefields_={H[1]: Minefield(Side.AXIS, real=True)}))
    _pin_die(r, "minefield", 5)               # would hit every time if rolled at all
    policy = _Build(moves=[MoveOrder("TK", H[1])])
    _movement(r, {Side.ALLIED: policy, Side.AXIS: policy}, Side.ALLIED)
    assert not [e for e in r.events if e.kind == EventKind.MINEFIELD_TRIGGERED]


def test_a_dummy_belt_destroys_nothing():
    """[26.11] makes real-vs-dummy THE distinction of rule 26, and 26.23's "the only difference"
    clause is scoped to the COST of entry ("the costs to enter a dummy minefield are the same as
    those for a real minefield"). 26.25 is written about mines physically destroying vehicles, and
    a dummy belt has none. A fake field that killed tanks would erase the whole bluff mechanic --
    and make the 3-Store dummy strictly better value than the 15+15 real one."""
    tank = _unit("TK", Side.ALLIED, H[0], mobility=Mobility.VEHICLE, cpa=40)
    r = _Run(_state([tank], minefields_={H[1]: Minefield(Side.AXIS, real=False)}))
    _pin_die(r, "minefield", 6)                # would destroy every time if the die were rolled
    policy = _Build(moves=[MoveOrder("TK", H[1])])
    _movement(r, {Side.ALLIED: policy, Side.AXIS: policy}, Side.ALLIED)
    assert not [e for e in r.events if e.kind == EventKind.MINEFIELD_TRIGGERED]
    assert r.state.unit("TK").strength == 1, "a dummy minefield took a real TOE Strength Point"


def test_foot_units_never_roll_the_destruction_die():
    """[26.25]: 'whenever a VEHICLE (tank, truck, etc.) enters...' -- infantry is exempt."""
    inf = _unit("PBI", Side.ALLIED, H[0], mobility=Mobility.FOOT, cpa=10)
    r = _Run(_state([inf], minefields_={H[1]: Minefield(Side.AXIS, real=True)}))
    _pin_die(r, "minefield", 5)
    policy = _Build(moves=[MoveOrder("PBI", H[1])])
    _movement(r, {Side.ALLIED: policy, Side.AXIS: policy}, Side.ALLIED)
    assert not [e for e in r.events if e.kind == EventKind.MINEFIELD_TRIGGERED]


# --- [26.15]/[26.23]/[26.14] REVEAL + DUMMY EXPIRY (engine-level) ----------------------------------

def test_enemy_dummy_is_revealed_on_entry_and_swept_at_phase_end():
    scout = _unit("SC", Side.ALLIED, H[0], mobility=Mobility.MOTORIZED, cpa=40)
    r = _Run(_state([scout], minefields_={H[1]: Minefield(Side.AXIS, real=False)}))
    policy = _Build(moves=[MoveOrder("SC", H[1])])
    _movement(r, {Side.ALLIED: policy, Side.AXIS: policy}, Side.ALLIED)
    revealed = [e for e in r.events if e.kind == EventKind.MINEFIELD_REVEALED]
    cleared = [e for e in r.events if e.kind == EventKind.MINEFIELD_CLEARED]
    assert revealed and revealed[0].payload["hex"] == list(H[1])
    assert cleared, "26.14/26.23: a revealed dummy is swept at the end of the Movement Phase"
    assert H[1] not in r.state.minefields


def test_friendly_minefield_flips_to_reveal_status_when_enemy_enters():
    scout = _unit("SC", Side.ALLIED, H[0], mobility=Mobility.MOTORIZED, cpa=40)
    r = _Run(_state([scout], minefields_={H[1]: Minefield(Side.AXIS, real=True)}))
    policy = _Build(moves=[MoveOrder("SC", H[1])])
    _movement(r, {Side.ALLIED: policy, Side.AXIS: policy}, Side.ALLIED)
    assert any(e.kind == EventKind.MINEFIELD_REVEALED for e in r.events)
    assert H[1] in r.state.minefields                # real belts are NOT swept, only dummies
    assert r.state.minefields[H[1]].revealed is True


def test_a_reaction_move_reveals_the_belt_and_rolls_the_die():
    """[8.51]: "Reaction IS movement" -- and 26.25 is written "WHENEVER a vehicle enters an Enemy
    minefield", not "whenever it is ordered to". The reactor pays the CP surcharge already (it
    routes through tactics.reachable_for_prev); this pins the other half, the reveal and the
    destruction roll, which fired only out of the main Movement loop before."""
    line = [(0, 0), (0, 1), (0, 2), (0, 3)]              # one hex longer than H: mover, then reactor
    mover = _unit("AX", Side.AXIS, line[0], mobility=Mobility.MOTORIZED, cpa=20)
    reactor = _unit("CW", Side.ALLIED, line[2], mobility=Mobility.VEHICLE, cpa=40)

    class _Reactor(_Build):
        def react_to(self, state, side, mover_id, eligible):
            return [MoveOrder("CW", line[3])] if "CW" in eligible else []

    r = _Run(_state([mover, reactor], minefields_={line[3]: Minefield(Side.AXIS, real=True)},
                    terrain={h: Terrain.CLEAR for h in line}))
    _pin_die(r, "minefield", 5)
    pol = _Reactor(moves=[MoveOrder("AX", line[1])])     # the Axis step that triggers the 8.5 slide
    _movement(r, {Side.AXIS: pol, Side.ALLIED: pol}, Side.AXIS)
    reacted = [e for e in r.events if e.kind == EventKind.REACTION_MOVED]
    triggered = [e for e in r.events if e.kind == EventKind.MINEFIELD_TRIGGERED]
    assert reacted, "the reaction did not happen -- this test is not exercising 8.5 at all"
    assert triggered and triggered[0].payload["hit"] is True
    assert any(e.kind == EventKind.MINEFIELD_REVEALED for e in r.events)


# --- [8.37] the two minefield Breakdown Value cells are the chart's, not a literal ----------------

def test_minefield_breakdown_values_come_from_the_chart_file():
    """game.minefields reads both cells out of data/breakdown_rates.json -- the same file every
    other [8.37] Breakdown Value in this engine comes from -- so the two can never drift apart."""
    import json
    from pathlib import Path
    cells = json.loads((Path(__file__).resolve().parent.parent
                        / "data" / "breakdown_rates.json").read_text())
    hexside = cells["terrain_breakdown_values_8_37"]["hexside"]
    assert mf.FRIENDLY_MINEFIELD_BV == hexside["friendly_minefield"] == 0
    assert mf.ENEMY_MINEFIELD_BV == hexside["enemy_minefield"] == 2


# --- INTEGRATION: the movement CP surcharge actually gates a real move ----------------------------

def test_reachable_charges_the_enemy_minefield_surcharge():
    """A bare movement.reachable check (no engine) confirms the extra_cost hook is wired end to
    end: a MOTORIZED mover's cost to CROSS an Enemy minefield hex is terrain + its own full CPA
    (26.21), so a low-budget mover cannot afford to enter it even though the underlying terrain
    (Clear, 2 CP) would otherwise leave headroom."""
    tmap = TerrainMap(terrain={h: Terrain.CLEAR for h in H})
    from game.tactics import _mine_extra_cost
    st = _state(minefields_={H[1]: Minefield(Side.AXIS, real=True)})
    mover = _unit("TK", Side.ALLIED, H[0], mobility=Mobility.MOTORIZED, cpa=6)
    extra = _mine_extra_cost(st, mover)
    reach = reachable(tmap, H[0], 6.0, Mobility.MOTORIZED, extra_cost=extra)
    assert H[1] not in reach, "2 CP terrain + 6 CP full-CPA mine surcharge exceeds a 6-CP budget"
    reach_big = reachable(tmap, H[0], 100.0, Mobility.MOTORIZED, extra_cost=extra)
    assert reach_big[H[1]] == 2 + 6                    # terrain entry + the mover's own CPA (26.21)
