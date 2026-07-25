"""Rule 20 -- the Replacement economy's SPEND, and the Commonwealth withdrawals (Block 7.2b).

Block 7.2a built the FLOW IN (production filled GameState.replacement_pool and NOTHING consumed
it). This file pins the loop 7.2b closes:

  * [20.3] the Replacement Point Conversion Chart -- data + reader (scan-verified, PDF p.102);
  * THE SPEND -- a depleted unit drawing Replacement Points from the pool to restore TOE Strength
    Points, the FIRST additive write to Unit.steps in this engine, via the 19.61/19.68 rebuild path;
  * 20.8 the Commonwealth MANDATORY withdrawals ([4.43a] WD column), 20.82/20.83, and the 20.9
    voluntary hook block 7.3 scores under 64.75.
"""
from __future__ import annotations

from dataclasses import replace

import game.supply as supply
from game import campaign_victory, coords, organization, replacements
from game.apply import apply
from game.engine import _Run, _commonwealth_withdrawals, _reorganize, _replacement_spend, run
from game.events import Event, EventKind, Phase, Side
from game.policy import OrganizationOrder, ScriptedPolicy
from game.state import GameState, StepRecord, Unit, VP
from game.movement import TerrainMap
from game.terrain import Mobility, Terrain


# --- [20.3] the Replacement Point Conversion Chart --------------------------------------

def test_20_3_chart_has_all_twenty_rows():
    assert len(replacements.conversion_rows()) == 20


def test_20_3_cells_match_the_scan():
    """Straight off the rendered scan (PDF p.102). The three rows the docs/rules OCR SCRAMBLED
    are asserted explicitly: it shifted the Armored-Car/Tank costs up a row."""
    assert replacements.conversion_charge("any_other_infantry") == {"infantry": 1}
    assert replacements.conversion_charge("any_headquarters_unit") == {"infantry": 2}
    assert replacements.conversion_charge("commando") == {"infantry": 3}
    assert replacements.conversion_charge("machinegun") == {"infantry": 2}
    assert replacements.conversion_charge("heavy_weapons") == {"infantry": 1, "gun": 1}
    assert replacements.conversion_charge("tank") == {"tank": 1}
    assert replacements.conversion_charge("artillery") == {"artillery": 1}
    assert replacements.conversion_charge("anti_tank") == {"anti_tank": 1}
    assert replacements.conversion_charge("anti_air") == {"anti_air": 1}
    # the OCR-scrambled rows, from the scan: Recce 1 ArmR, Armored Car 2 ArmR, Tank 1 Tank
    assert replacements.conversion_for("armored_reconnaissance")["requires"] == [
        [{"class": "armr", "count": 1}], [{"class": "lt_tank", "count": 1}]]
    assert replacements.conversion_for("armored_car")["requires"] == [
        [{"class": "armr", "count": 2}], [{"class": "lt_tank", "count": 1}]]


def test_20_3_road_railroad_construction_rebuilds_free():
    """Note f: the Road/Railroad Construction battalions cost NO Replacement Points."""
    assert replacements.conversion_charge("road_railroad_construction") == {}
    assert replacements.conversion_for("road_railroad_construction")["requires"] == []


# --- the unit -> [20.3] row classifier -------------------------------------------------

def _u(uid, **kw):
    kw.setdefault("nationality", "CW")
    return Unit(uid, kw.pop("side", Side.ALLIED), kw.pop("hex", (0, 0)),
                (StepRecord("s", kw.pop("strength", 8)),),
                mobility=Mobility.FOOT, cpa=kw.pop("cpa", 10),
                stacking_points=kw.pop("sp", 1), oca=kw.pop("oca", 1), dca=kw.pop("dca", 2), **kw)


def test_replacement_kind_maps_engine_units_to_chart_rows():
    # is_gun keys off the 11.12 Vulnerability rating, so every gun test unit carries one.
    assert organization.replacement_kind(_u("I", is_combat=True)) == "any_other_infantry"
    assert organization.replacement_kind(_u("T", is_tank=True)) == "tank"
    assert organization.replacement_kind(_u("A", barrage=3, vulnerability=2)) == "artillery"
    assert organization.replacement_kind(_u("AT", anti_armor=4, vulnerability=2)) == "anti_tank"
    # a Vulnerability-rated gun with neither barrage nor anti-armor is anti-air
    assert organization.replacement_kind(_u("AA", vulnerability=2)) == "anti_air"


# --- THE SPEND: the flow-out beat + apply -----------------------------------------------

def _state(units, *, turn=10, pool=None, production=True, withdrawals=False):
    """A minimal campaign-shaped GameState the flow-out / withdrawal beats read: on-map CW units
    (arrival_turn <= turn), a stocked pool, the two campaign gates. Zeroed supply keeps the
    conservation invariant trivially true, exactly as tests/test_replacements._repro_state does."""
    hexes = {u.hex for u in units} | {(0, 0)}
    tmap = TerrainMap(terrain={h: Terrain.CLEAR for h in hexes}, fortifications={})
    return GameState(
        turn=turn, max_turns=111, phase=Phase.ORGANIZATION, active_side=Side.SYSTEM, seed=1941,
        weather="clear", vp=VP(), terrain=tmap, control={}, units=tuple(units), target_hex=(0, 0),
        supplies=(), consumed={c: 0 for c in supply.COMMODITIES},
        initial_supply={c: 0 for c in supply.COMMODITIES}, stage=1,
        replacement_pool=dict(pool or {}), replacement_production=production,
        commonwealth_withdrawals=withdrawals)


def _inf(uid, hex_, strength, max_toe, **kw):
    kw.setdefault("is_combat", True)
    return _u(uid, hex=hex_, strength=strength, max_toe=max_toe, **kw)


def test_spend_rebuilds_depleted_cw_infantry_and_draws_the_pool():
    """The loop 7.2a opened, closed: depleted Commonwealth infantry absorb the arrived Infantry
    Replacement Points, restoring TOE Strength (the first additive write to Unit.steps), and the pool
    is drawn down by exactly what was absorbed ([20.3] 'any_other_infantry' = 1 Infantry Point/TOE)."""
    a = _inf("A", (1, 1), strength=4, max_toe=8)     # deficit 4
    b = _inf("B", (2, 2), strength=6, max_toe=8)     # deficit 2
    r = _Run(_state([a, b], pool={"ALLIED/infantry": 10}))
    _replacement_spend(r)
    assert r.state.unit("A").strength == 8 and r.state.unit("B").strength == 8   # both to max
    assert r.state.replacements_available("ALLIED/infantry") == 4                # 10 - (4 + 2)
    rebuilt = [e for e in r.events if e.kind == EventKind.UNIT_REBUILT]
    assert {e.payload["unit_id"] for e in rebuilt} == {"A", "B"}
    assert all(e.payload["pool_key"] == "ALLIED/infantry" for e in rebuilt)


def test_spend_is_bounded_by_the_pool_and_takes_the_most_depleted_first():
    """When the pool cannot fill everyone, the most-depleted battalion is rebuilt first, and the
    spend stops when the pool is dry -- so a scarce replacement flow reaches the neediest units."""
    a = _inf("A", (1, 1), strength=1, max_toe=8)     # deficit 7 (most depleted)
    b = _inf("B", (2, 2), strength=7, max_toe=8)     # deficit 1
    r = _Run(_state([a, b], pool={"ALLIED/infantry": 5}))
    _replacement_spend(r)
    assert r.state.unit("A").strength == 6           # 1 + 5, all of the pool
    assert r.state.unit("B").strength == 7           # untouched -- pool dry
    assert r.state.replacements_available("ALLIED/infantry") == 0


def test_spend_never_exceeds_max_toe_and_leaves_the_surplus_in_the_pool():
    a = _inf("A", (1, 1), strength=7, max_toe=8)     # headroom 1
    r = _Run(_state([a], pool={"ALLIED/infantry": 10}))
    _replacement_spend(r)
    assert r.state.unit("A").strength == 8           # 19.61: capped at the maximum
    assert r.state.replacements_available("ALLIED/infantry") == 9


def test_spend_gated_off_without_production_is_byte_identical():
    a = _inf("A", (1, 1), strength=4, max_toe=8)
    r = _Run(_state([a], pool={"ALLIED/infantry": 10}, production=False))
    _replacement_spend(r)
    assert r.events == [] and r.state.unit("A").strength == 4


def test_spend_rebuilds_cw_tanks_from_tank_pool():
    """Block A: generalized spend now handles the tank class from [20.78C]."""
    tank = _u("T", hex=(1, 1), strength=4, max_toe=8, is_tank=True)
    r = _Run(_state([tank], pool={"ALLIED/tank": 10}))
    _replacement_spend(r)
    assert r.state.unit("T").strength == 8           # 4 + 4, all tank pool spent
    assert r.state.replacements_available("ALLIED/tank") == 6
    rebuilt = [e for e in r.events if e.kind == EventKind.UNIT_REBUILT]
    assert len(rebuilt) == 1
    assert rebuilt[0].payload["pool_key"] == "ALLIED/tank"


def test_spend_rebuilds_cw_guns_from_gun_pool():
    """Block A: the gun pool ([20.78C] artillery/AA/AT guns) rebuilds gun-type units."""
    artillery = _u("A", hex=(1, 1), strength=3, max_toe=8, barrage=3, vulnerability=2)
    antitank = _u("AT", hex=(2, 2), strength=2, max_toe=6, anti_armor=4, vulnerability=2)
    r = _Run(_state([artillery, antitank], pool={"ALLIED/gun": 12}))
    _replacement_spend(r)
    assert r.state.unit("A").strength == 8           # 3 + 5
    assert r.state.unit("AT").strength == 6          # 2 + 4
    assert r.state.replacements_available("ALLIED/gun") == 3  # 12 - 5 - 4
    rebuilt = [e for e in r.events if e.kind == EventKind.UNIT_REBUILT]
    assert len(rebuilt) == 2
    assert all(e.payload["pool_key"] == "ALLIED/gun" for e in rebuilt)


def test_spend_rebuilds_axis_infantry_from_pool():
    """Block A: Axis infantry pool ([20.66]) rebuilds Axis infantry units."""
    axis_inf = _inf("GE Inf", (1, 1), strength=3, max_toe=8, side=Side.AXIS, nationality="GE")
    r = _Run(_state([axis_inf], pool={"AXIS/infantry": 10}))
    _replacement_spend(r)
    assert r.state.unit("GE Inf").strength == 8      # 3 + 5
    assert r.state.replacements_available("AXIS/infantry") == 5
    rebuilt = [e for e in r.events if e.kind == EventKind.UNIT_REBUILT]
    assert len(rebuilt) == 1
    assert rebuilt[0].payload["pool_key"] == "AXIS/infantry"


def test_spend_rebuilds_axis_tanks():
    """Block A: Axis tank pool rebuilds Axis tanks."""
    axis_tank = _u("Pz III", hex=(1, 1), strength=2, max_toe=5, is_tank=True,
                   side=Side.AXIS, nationality="GE")
    r = _Run(_state([axis_tank], pool={"AXIS/tank": 8}))
    _replacement_spend(r)
    assert r.state.unit("Pz III").strength == 5      # 2 + 3 (headroom)
    assert r.state.replacements_available("AXIS/tank") == 5  # 8 - 3
    rebuilt = [e for e in r.events if e.kind == EventKind.UNIT_REBUILT]
    assert len(rebuilt) == 1
    assert rebuilt[0].payload["pool_key"] == "AXIS/tank"


def test_spend_most_depleted_first_across_classes():
    """Block A: within each class, most-depleted units rebuild first (existing behavior)."""
    inf1 = _inf("I1", (1, 1), strength=2, max_toe=8, side=Side.AXIS, nationality="GE")
    inf2 = _inf("I2", (2, 2), strength=6, max_toe=8, side=Side.AXIS, nationality="GE")
    r = _Run(_state([inf1, inf2], pool={"AXIS/infantry": 5}))
    _replacement_spend(r)
    assert r.state.unit("I1").strength == 7          # 2 + 5 (most depleted gets all)
    assert r.state.unit("I2").strength == 6          # untouched (pool empty)
    assert r.state.replacements_available("AXIS/infantry") == 0


def test_spend_ignores_a_full_strength_or_axis_unit():
    full = _inf("F", (1, 1), strength=8, max_toe=8)
    axis = _inf("X", (2, 2), strength=2, max_toe=8, side=Side.AXIS, nationality="GE")
    r = _Run(_state([full, axis], pool={"ALLIED/infantry": 10}))
    _replacement_spend(r)
    assert r.events == []                             # nothing depleted on the CW infantry side


def test_apply_unit_rebuilt_debits_the_pool_and_adds_the_steps():
    """The apply fold in isolation: UNIT_REBUILT both grows steps[0] and debits the pool bucket."""
    u = _inf("A", (0, 0), strength=4, max_toe=8)
    st = _state([u], pool={"ALLIED/infantry": 6})
    ev = Event(0, st.turn, Phase.ORGANIZATION, Side.ALLIED, "ALLIED/Command",
               EventKind.UNIT_REBUILT,
               {"unit_id": "A", "points": 3, "strength": 7, "pool_key": "ALLIED/infantry", "cost": 3})
    out = apply(st, ev)
    assert out.unit("A").strength == 7
    assert out.replacements_available("ALLIED/infantry") == 3


# --- Block A: 64.74 scoring of non-excluded classes ----

def test_64_74_will_score_cw_tank_once_added_to_spendable_classes():
    """RESTATED (rule 5): Block A LANDED 'tank' and 'gun' in spendable_classes.ALLIED (the [20.78C]
    flow-in engine._cw_equipment_production + the generalized spend), so 64.74 now scores the unused
    tank/gun pools (neither is book-excluded, unlike CW infantry). This test verifies the pool setup;
    the actual 64.74 scoring is in test_campaign_victory. 'recce' stays OUT -- it is structurally
    unspendable (organization.replacement_kind never emits a recce kind)."""
    spendable_now = replacements.replacement_vp_spendable_classes(Side.ALLIED)
    assert "infantry" in spendable_now              # was always here (but book-excluded)
    assert "tank" in spendable_now                  # Block A: the [20.78C] flow-in + spend landed
    assert "gun" in spendable_now
    assert "recce" not in spendable_now             # structurally unspendable -- no rebuild beat
    # tank/gun are NOT book-excluded, so being spendable, they score their unused count in 64.74:
    excluded = replacements.replacement_vp_excluded_classes(Side.ALLIED)
    assert "infantry" in excluded                   # book-excluded (CW only)
    assert "tank" not in excluded and "gun" not in excluded


# --- 20.8 the mandatory withdrawals -----------------------------------------------------

# Cairo is a FIVE-hex city (Alexandria two); the withdrawal gate must recognise every hex of both,
# not one per city -- so tests derive the real hexes from the canonical enumeration and prove the
# multi-hex geography, rather than trusting a single representative hex (Block 7.2b repair).
_CAIRO_HEXES = [coords.to_axial(coords.parse(h))
                for h in campaign_victory.load_victory_cities()["auto_win"]["cairo"]]
_ALEX_HEXES = [coords.to_axial(coords.parse(h))
               for h in campaign_victory.load_victory_cities()["auto_win"]["alexandria"]]
_CAIRO = _CAIRO_HEXES[0]                                        # one of Cairo's five hexes


def _withdrawn(r) -> dict:
    return {e.payload["unit_id"]: e.payload for e in r.events
            if e.kind == EventKind.UNIT_WITHDRAWN}


def test_withdrawal_removes_the_named_formation_at_its_scheduled_turn():
    """Row 21 (GT63): the Polish Brigade is pulled -- every counter matching 'Polish Bde' (its HQ
    and battalions) leaves the board."""
    units = [_u("HQ Polish Bde", hex=(3, 3), is_combat=False),
             _inf("Polish Bde I", (3, 3), 8, 8), _inf("Polish Bde II", (3, 4), 8, 8),
             _inf("Other Bde I", (5, 5), 8, 8)]                 # a bystander that must NOT leave
    r = _Run(_state(units, turn=63, withdrawals=True))
    _commonwealth_withdrawals(r)
    gone = _withdrawn(r)
    assert set(gone) == {"HQ Polish Bde", "Polish Bde I", "Polish Bde II"}
    assert r.state.unit("Polish Bde I").alive is False         # steps emptied -> off the board
    assert r.state.unit("Other Bde I").alive is True


def test_withdrawal_20_83_eliminates_a_unit_not_at_a_base_or_below_75pct_toe():
    """20.83 (its (20.75) reference corrected to (20.82) under the errata key): a scheduled unit not
    at Cairo/Alexandria, OR below 75% of maximum TOE, is ELIMINATED rather than cleanly withdrawn."""
    at_base = _inf("HQ 10 Armd Div", _CAIRO, 8, 8, is_combat=False)   # at Cairo, full -> clean
    off_base = _inf("9 Armd Bde I", (7, 7), 8, 8)                     # away from base -> eliminated
    weak_at_base = _inf("9 Armd Bde II", _CAIRO, 5, 8)                # at base but 62% -> eliminated
    r = _Run(_state([at_base, off_base, weak_at_base], turn=110, withdrawals=True))
    _commonwealth_withdrawals(r)
    gone = _withdrawn(r)
    assert gone["HQ 10 Armd Div"]["eliminated"] is False
    assert gone["9 Armd Bde I"]["eliminated"] is True
    assert gone["9 Armd Bde II"]["eliminated"] is True


def test_withdrawal_recognises_every_hex_of_the_multi_hex_delta_cities():
    """Cairo is FIVE hexes and Alexandria TWO (data/victory_cities.json auto_win). A withdrawing unit
    standing in ANY of them is 'at a base' and cleanly withdrawn. The earlier single-hex base table
    saw only ONE hex per city and wrongly eliminated (20.83) a unit in the other four/one -- proven
    here on a SECOND, non-representative hex of each city (which the old table did NOT contain, so
    this asserts the Block 7.2b repair, not merely the happy path)."""
    assert len(_CAIRO_HEXES) == 5 and len(_ALEX_HEXES) == 2         # the canonical multi-hex geography
    bases = replacements.withdrawal_base_hexes()
    assert set(_CAIRO_HEXES) <= bases and set(_ALEX_HEXES) <= bases
    at_cairo2 = _inf("HQ 10 Armd Div", _CAIRO_HEXES[1], 8, 8, is_combat=False)  # Cairo's 2nd hex
    at_alex2 = _inf("9 Armd Bde I", _ALEX_HEXES[1], 8, 8)                       # Alexandria's 2nd hex
    r = _Run(_state([at_cairo2, at_alex2], turn=110, withdrawals=True))
    _commonwealth_withdrawals(r)
    gone = _withdrawn(r)
    assert gone["HQ 10 Armd Div"]["eliminated"] is False
    assert gone["9 Armd Bde I"]["eliminated"] is False


def test_by_type_withdrawal_takes_three_battalions_at_75pct_toe_first_20_82():
    """Row 29 (GT97): the Guards Bde HQ plus 'any three infantry battalions' -- the by-type count is
    filled 20.82's way, battalions at >=75% TOE before any below it, highest TOE first."""
    units = [_u("HQ 22 Guards Bde", hex=(3, 3), is_combat=False),
             _inf("Bn full", (4, 4), 8, 8),        # 100%
             _inf("Bn high", (4, 5), 7, 8),        # 87.5%
             _inf("Bn ok", (4, 6), 6, 8),          # 75%
             _inf("Bn weak", (4, 7), 3, 8)]        # 37.5% -- must be passed over
    r = _Run(_state(units, turn=97, withdrawals=True))
    _commonwealth_withdrawals(r)
    gone = set(_withdrawn(r))
    assert gone == {"HQ 22 Guards Bde", "Bn full", "Bn high", "Bn ok"}
    assert r.state.unit("Bn weak").alive is True


def test_withdrawal_of_a_unit_with_broken_down_vehicles_zeroes_them():
    """A withdrawn combat unit may carry broken-down vehicles; removing its steps must zero
    broken_down too, or the 21.44 invariant 0 <= broken_down <= strength fires (0 vs strength 0)."""
    u = _inf("Polish Bde I", (3, 3), 8, 8, broken_down=3)
    r = _Run(_state([u], turn=63, withdrawals=True))
    _commonwealth_withdrawals(r)
    out = r.state.unit("Polish Bde I")
    assert out.alive is False and out.broken_down == 0


def test_withdrawal_gated_off_is_byte_identical():
    units = [_inf("Polish Bde I", (3, 3), 8, 8)]
    r = _Run(_state(units, turn=63, withdrawals=False))
    _commonwealth_withdrawals(r)
    assert r.events == [] and r.state.unit("Polish Bde I").alive is True


def test_the_unresolved_rows_target_nothing_but_are_still_transcribed():
    """The schedule is COMPLETE (33 rows) even where the current OOB lacks the named formation --
    e.g. row 1's 5th Indian Brigade -- so those rows carry an empty match and remove nobody."""
    rows = replacements.withdrawal_rows()
    assert len(rows) == 33
    assert next(w for w in rows if w["n"] == 1)["match"] == []          # 5th In Bde, not seeded
    assert next(w for w in rows if w["n"] == 2)["match"] == ["7 In Bde"]


# --- 20.82 the named errata key ---------------------------------------------------------

def test_20_82_errata_key_records_the_20_75_typo():
    """Owner ruling 3: 20.83's '(20.75)' is a printed typo for (20.82). Wired under a named errata
    key (the 54.17 class), never silently."""
    err = replacements._withdrawals()["toe_threshold_errata_20_82"]
    assert err["printed_reference"] == "20.75"
    assert err["correct_reference"] == "20.82"
    assert replacements.withdrawal_toe_fraction() == 0.75


# --- 20.9 the voluntary withdrawal hook (block 7.3 scores it) ----------------------------

def _try_withdraw(unit):
    r = _Run(_state([unit], turn=50, withdrawals=True))
    _reorganize(r, Side.ALLIED, OrganizationOrder("withdraw", unit_id=unit.id))
    return r


def test_voluntary_withdrawal_removes_an_eligible_battalion_and_flags_it():
    """20.9/64.75-A: the CW may voluntarily withdraw a combat battalion at >=75% TOE standing in
    Cairo/Alexandria. It leaves the board tagged voluntary, for Block 7.3 to score."""
    r = _try_withdraw(_inf("1 Buffs", _CAIRO, 8, 8))
    gone = _withdrawn(r)
    assert gone["1 Buffs"]["voluntary"] is True and gone["1 Buffs"]["eliminated"] is False
    assert r.state.unit("1 Buffs").alive is False


def test_voluntary_withdrawal_rejects_below_75pct_or_away_from_base():
    weak = _try_withdraw(_inf("Weak Bn", _CAIRO, 5, 8))                # 62% at Cairo
    off = _try_withdraw(_inf("Field Bn", (7, 7), 8, 8))               # full but in the field
    for r in (weak, off):
        assert not _withdrawn(r)
        assert [e for e in r.events if e.kind == EventKind.ORDER_REJECTED
                and e.payload["order"] == "withdraw"]


def test_voluntary_withdrawal_is_commonwealth_only():
    axis = _u("DAK Bn", hex=_CAIRO, strength=8, max_toe=8, is_combat=True,
              side=Side.AXIS, nationality="GE")
    r = _Run(_state([axis], turn=50, withdrawals=True))
    _reorganize(r, Side.AXIS, OrganizationOrder("withdraw", unit_id="DAK Bn"))
    assert not _withdrawn(r)
    assert [e for e in r.events if e.kind == EventKind.ORDER_REJECTED]


def test_voluntary_withdrawal_rejects_a_company_64_75_A():
    """64.75-A names 'a combat battalion (not company)'. A company (rule 9.4: zero Stacking Points),
    full-strength in Cairo and thus eligible on every other test, is refused for its size."""
    company = _u("A Coy", hex=_CAIRO, strength=8, max_toe=8, is_combat=True, sp=0)
    assert organization.is_company(company)                        # the 9.4 discriminator
    r = _try_withdraw(company)
    assert not _withdrawn(r)
    assert [e for e in r.events if e.kind == EventKind.ORDER_REJECTED
            and e.payload["order"] == "withdraw"]
