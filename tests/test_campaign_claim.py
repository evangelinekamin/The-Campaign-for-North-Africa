"""THE TAKE-AND-HOLD (rule 64.73, game.campaign_claim).

The campaign is scored on the victory CITIES a side holds with a SUPPLIED combat unit at the final
Game-Turn -- not on how far its spearhead got. The scripted Commonwealth used to drive every
battalion at objective_for(ALLIED) and bank nothing on the way: measured over the full campaign it
sprinted past Sollum, Bardia and Derna to Benghazi, garrisoned none of them, and finished 200-120
down with 250 Victory Points of EMPTY CITY lying behind its own front line.

These are the acceptance tests for the fix, and for the three things it must NOT do: strand a
garrison out of supply, strand a depot in the desert, or mask its own supply chain.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import campaign_claim, coords                                  # noqa: E402
from game.apply import fold                                              # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,                    # noqa: E402
                                  CampaignCommonwealthPolicy)
from game.engine import determinism_signature, run                       # noqa: E402
from game.events import Side                                             # noqa: E402
from game.policy import ScriptedPolicy, SupplyMoveOrder                  # noqa: E402
from game.scenario import campaign, rommels_arrival, siege_of_tobruk     # noqa: E402


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


SOLLUM, BARDIA, TOBRUK = _ax("C4021"), _ax("C4321"), _ax("C4807")
SIWA, JALO, GIARABUB = _ax("C0127"), _ax("B0513"), _ax("C1014")


def _run(max_turns: int):
    return run(campaign(seed=1941, max_turns=max_turns),
               CampaignAxisPolicy(), CampaignCommonwealthPolicy())


def _banked(state, side: Side) -> set:
    vic = state.victory
    return {name for ax, _a, _c, name in vic.cities if vic._occupier(state, ax) == side}


# --- TAKE ----------------------------------------------------------------------------------------

def test_the_commonwealth_takes_the_cities_it_used_to_sprint_past():
    """THE ACCEPTANCE. The old policy banked exactly Mersa Matruh, Sidi Barrani and Benghazi -- the
    two it happened to be standing on and the one it was aimed at -- and left SOLLUM, BARDIA, DERNA,
    TOBRUK and the three oases empty for a hundred and eleven Game-Turns. The take-and-hold goes and
    gets them, and keeps the ones it was already banking."""
    fin = _run(30).final
    banked = _banked(fin, Side.ALLIED)
    assert {"Mersa Matruh", "Sidi Barrani"} <= banked        # the old ones are not thrown away
    assert "Sollum" in banked, f"Sollum was never taken: {sorted(banked)}"
    assert "Derna" in banked, f"Derna was never taken: {sorted(banked)}"


def test_occupying_sollum_brings_the_supply_chain_up_to_it():
    """THE HINGE. Sollum carries the Commonwealth's OWN Field Supply Depot (60.34), seeded EMPTY one
    22-CP lorry hop beyond Sidi Barrani -- and the old policy swept past the hex for a hundred and
    eleven Game-Turns without once standing on it. So Sollum stayed AXIS-CONTROLLED to the last turn
    of the war, no lorry would deliver into it and no dump would leapfrog onto it, and the third link
    of the Commonwealth's own chain sat dry all campaign.

    Take the hex and the supply comes up behind it (spine_awaits_control: what was missing was never
    distance, it was CONTROL). And the ten points are the least of it -- a stocked depot ON Sollum is
    what puts BARDIA, three hexes away and worth FIFTY, inside a Commonwealth supply trace for the
    first time in the campaign."""
    res = _run(24)
    assert res.initial.supply("AL-Stage-Sollum").empty        # seeded empty: hauled into, not filled
    fin = res.final
    assert fin.control_of(SOLLUM) != res.initial.control_of(SOLLUM), "Sollum never changed hands"
    assert fin.victory._occupier(fin, SOLLUM) == Side.ALLIED, "Sollum is held but not SUPPLIED"

    fed = [d for d in fin.supplies
           if d.side == Side.ALLIED and d.hex == SOLLUM and d.ammo > 0]
    assert fed, "no Commonwealth depot came up to Sollum"

    # THE PAYOFF: Bardia is now inside a Commonwealth trace, which it never was before.
    from dataclasses import replace
    cw = [u for u in fin.living(Side.ALLIED) if u.is_combat and u.strength >= 1]
    assert any(fin.victory._supplied(fin, replace(u, hex=BARDIA)) for u in cw), \
        "taking Sollum did not bring Bardia into supply -- the 50 points stay out of reach"


def test_you_do_not_besiege_a_city_you_could_not_hold():
    """The ONE clause that sorts the two fortresses, with no fortress special-case anywhere. Rule
    15.82 grants Bardia and Tobruk NO EVICTION, so an assault will never move those garrisons and a
    policy that throws men at them forever is just bleeding. The take-and-hold does not know they are
    fortresses -- it only asks whether it could FEED a garrison there (the 64.73 trace test), and
    that answer, by itself, sends the army to Bardia and leaves Tobruk alone.

    Bardia is three hexes from the Sollum depot the take-and-hold has just filled; Tobruk is not near
    anything the Commonwealth owns."""
    fin = _run(30).final
    cw = [u for u in fin.living(Side.ALLIED) if u.is_combat and u.strength >= 1]
    plan = {c.city: c for c in campaign_claim.claims(fin, Side.ALLIED, escort=True)}

    from dataclasses import replace
    feedable = {ax: any(fin.victory._supplied(fin, replace(u, hex=ax)) for u in cw)
                for ax in (BARDIA, TOBRUK)}
    for ax, name in ((BARDIA, "Bardia"), (TOBRUK, "Tobruk")):
        if not feedable[ax] and fin.victory._occupier(fin, ax) != Side.ALLIED:
            assert ax not in plan, f"{name} is besieged but no unit could be supplied there"


def test_the_desert_oases_are_reachable_but_not_suppliable_so_no_depot_goes_there():
    """MEASURED, and the reason this clause exists: flying columns CAN reach Siwa and Jalo, and were
    banked on both by Game-Turn 24. By Game-Turn 111 both depots were dry, both garrisons had
    starved, both cities stood empty -- and the two dumps were gone from the army's park for good
    (32.33: a depot only relocates onto a hex a friendly COMBAT unit holds, so a depot alone in the
    desert is stranded there for the rest of the war). The lorry pool meanwhile quadrupled its
    mileage driving after them, and the Commonwealth lost BENGHAZI and SIDI BARRANI -- 110 Victory
    Points -- chasing 30 it could not keep.

    So a depot only marches to where the LORRIES can follow (within_a_lorry_hop, the rulebook's own
    53.22 convoy CPA). The oases are reachable. They are not SUPPLIABLE, and nothing is sent."""
    res = _run(30)
    for d in res.final.supplies:
        if d.side == Side.ALLIED and campaign_claim.is_field_dump(d):
            assert d.hex not in (SIWA, JALO, GIARABUB), \
                f"{d.id} was marched to a desert oasis it can never be refilled at ({d.hex})"


# --- HOLD ----------------------------------------------------------------------------------------

def test_a_depot_feeding_a_banked_city_never_leapfrogs_away_from_it():
    """The dual of the standing garrison order, and the half without which the other half is
    worthless: the base 32.3 bridge leapfrogs every fuelled dump toward the objective, so the turn
    after a depot arrives at Derna it would march straight off again to the head of the column and
    the city it had just made bankable would stop scoring."""
    fin = _run(24).final
    pol = CampaignCommonwealthPolicy()
    pinned = campaign_claim.garrison_depots(fin, Side.ALLIED)
    assert pinned, "no depot is feeding a banked city -- the check is vacuous"
    moved = {o.supply_id for o in pol.supply_orders(fin, Side.ALLIED)}
    assert not (pinned & moved), f"a garrison's own depot was ordered away: {sorted(pinned & moved)}"


def test_a_field_dump_never_parks_on_top_of_a_seeded_field_supply_depot():
    """THE MASKING GUARD (campaign_claim.keep_off_the_spine). The lorry relay picks its delivery
    address by (distance-to-objective, reach, id), and two dumps on one hex tie on the first two --
    so the tie breaks on the ID, 'AL-Dump#2' beats 'AL-Stage-Barrani', and every load lands in the
    field dump. And a field dump is exactly what the relay may NOT lift from again. Supply goes IN to
    a masked link and can never come OUT: the chain is severed at the very hex built to carry it.

    Measured, a field dump on Sidi Barrani took every one of AL-Stage-Barrani's deliveries, left the
    seeded depot at zero, starved the Sollum leg beyond it and lost the Commonwealth BENGHAZI -- a
    hundred Victory Points. That hex belongs to the chain."""
    fin = _run(24).final
    spine = {s.hex: s.id for s in fin.supplies
             if s.side == Side.ALLIED and s.id.startswith("AL-Stage")}
    assert spine
    for d in fin.supplies:
        if d.side == Side.ALLIED and campaign_claim.is_field_dump(d) and d.hex in spine:
            raise AssertionError(
                f"{d.id} is parked on {spine[d.hex]} and masks it from the lorries")

    # and the chain it protects actually carries: a seeded Field Supply Depot holds stock.
    chain = ("AL-Stage-Matruh", "AL-Stage-Barrani", "AL-Stage-Sollum")
    assert any(fin.supply(d).fuel > 0 for d in chain), \
        f"the spine carries nothing: {[(d, fin.supply(d).fuel) for d in chain]}"


def test_a_detached_unit_is_out_of_the_general_advance():
    """A detached unit is out of the advance -- EVERY unit in the plan, not merely the ones that
    happen to have a move order in it. A unit that has already REACHED its city emits no claim move
    (there is nowhere left to go), and if that left it in the attacker branch it would be marched
    straight back off toward Benghazi the same stage: the city taken and abandoned in one breath.

    So a claimed unit carries its claim's order or no order at all -- never the advance's."""
    fin = _run(14).final              # mid-Compass: detachments are in flight
    pol = CampaignCommonwealthPolicy()
    plan = campaign_claim.claims(fin, Side.ALLIED, escort=True)
    assert plan, "the take-and-hold claims nothing -- the check is vacuous"
    mine = {o.unit_id: o for o in campaign_claim.claim_moves(fin, Side.ALLIED, plan)}
    orders = {o.unit_id: o for o in pol.movement(fin, Side.ALLIED)}
    for c in plan:
        got = orders.get(c.unit_id)
        assert got is None or got == mine.get(c.unit_id), \
            f"{c.unit_id} was claimed for {c.name} but marched on the objective instead: {got}"


# --- conservation + byte identity ----------------------------------------------------------------

def test_conservation_holds_over_the_take_and_hold():
    """The take-and-hold only MOVES units and depots; it mints nothing. The recorded log folds
    byte-identically back to the final state, and game.invariants (on_hand + consumed == initial, per
    commodity) never raises -- the engine checks it after every applied event, so a clean run IS the
    conservation proof."""
    res = _run(24)
    assert fold(res.initial, res.events) == res.final
    for c, initial in res.final.initial_supply.items():
        on_hand = (sum(getattr(s, c.lower()) for s in res.final.supplies)
                   + sum(getattr(t, c.lower()) for t in res.final.trucks))
        assert on_hand + res.final.consumed.get(c, 0) == initial


def test_rommel_and_siege_stay_byte_identical():
    """THE HARD CONSTRAINT. Every helper in game.campaign_claim needs the rule-64.73 city table, and
    rommels_arrival / siege_of_tobruk do not carry one (_cities returns () for them), so the two
    benchmark scenarios must hash exactly as they did before this slice existed."""
    axis = ScriptedPolicy(Side.AXIS)
    baselines = {"rommel": "9339d2b308d7", "siege": "5ba4da88d107"}
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        st = build(seed=42)
        assert not campaign_claim._cities(st)                # no city table -> every helper is inert
        assert campaign_claim.garrison_units(st, Side.AXIS) == set()
        assert campaign_claim.claims(st, Side.AXIS) == ()
        res = run(st, axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baselines[name], f"{name} drifted: {sig} != {baselines[name]}"


def test_the_claim_helpers_are_inert_without_a_city_table():
    """The whole module is safe to call on any state: no city table, no orders, no crash."""
    st = rommels_arrival(seed=42)
    assert campaign_claim.garrison_depots(st, Side.AXIS) == set()
    assert campaign_claim.claim_moves(st, Side.AXIS, ()) == []
    assert campaign_claim.claim_supply(st, Side.AXIS, ()) == []
    orders = [SupplyMoveOrder("AX-Dump", (0, 0))]
    assert campaign_claim.hold_depots(orders, st, Side.AXIS) == orders
