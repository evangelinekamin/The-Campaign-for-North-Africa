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
from game.events import Control, Side                                    # noqa: E402
from game.policy import ScriptedPolicy, SupplyMoveOrder                  # noqa: E402
from game.scenario import campaign, rommels_arrival, siege_of_tobruk     # noqa: E402
from baselines import BENCHMARKS, CAMPAIGN_SEED                                    # noqa: E402


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


SOLLUM, BARDIA, TOBRUK = _ax("C4021"), _ax("C4321"), _ax("C4807")
SIWA, JALO, GIARABUB = _ax("C0127"), _ax("B0513"), _ax("C1014")


def _run(max_turns: int):
    return run(campaign(seed=CAMPAIGN_SEED, max_turns=max_turns),
               CampaignAxisPolicy(), CampaignCommonwealthPolicy())


def _banked(state, side: Side) -> set:
    vic = state.victory
    return {name for ax, _a, _c, name in vic.cities if vic._occupier(state, ax) == side}


# --- TAKE ----------------------------------------------------------------------------------------

def test_both_sides_take_the_cities_they_used_to_sprint_past():
    """THE ACCEPTANCE, now asked of BOTH armies -- because both of them have the take-and-hold, and
    it is the same side-generic code (campaign_policy.take_and_hold_moves).

    *** AND THE ANSWER CHANGED WHEN THE AXIS GOT IT. *** With the Commonwealth alone playing the
    64.73 points, this test asserted the CW banked SOLLUM and DERNA by Game-Turn 30 -- and it did.
    It was WALKING INTO EMPTY CITIES. The Axis had marched off them and garrisoned nothing, so
    Operation Compass never had to fight for a hex. Give the Axis the same standing orders and it
    puts IT-1-Libyan on Sollum before Compass even opens; a garrisoned hex cannot be walked onto; and
    the Commonwealth -- measured across the full campaign, seed 1941 -- now takes exactly ONE city in
    the entire war: BARDIA, on Game-Turn 57, Operation Crusader.

    That is not a regression in the mechanism. It is the mechanism telling the truth: the
    Commonwealth's offensive could only ever take ground the enemy had abandoned. What it reveals --
    that the Western Desert Force cannot break a defended city -- is a BALANCE finding, and it is
    recorded in the commit that made both sides competent, not papered over here.

    So what this test now pins is the thing that must stay true on both sides: an army keeps the
    cities it banks, and goes and gets the ones it does not."""
    fin = _run(30).final
    cw, ax = _banked(fin, Side.ALLIED), _banked(fin, Side.AXIS)
    # The Commonwealth keeps the two its own seeded spine feeds and it stands on.
    assert {"Mersa Matruh", "Sidi Barrani"} <= cw
    # The AXIS -- which used to bank whatever the garrison order happened to pin and throw the rest
    # away -- now holds its own rear: BENGHAZI (its port of arrival, never once garrisoned in 111
    # Game-Turns) and SOLLUM, on top of the Tobruk and Bardia it opens the war standing on.
    assert {"Tobruk", "Bardia"} <= ax, f"the Axis threw away what it opened holding: {sorted(ax)}"
    assert "Benghazi" in ax, f"the Axis still does not garrison its own port: {sorted(ax)}"
    assert not (cw & ax)                                    # a city is banked by at most one side


def test_occupying_sollum_brings_the_supply_chain_up_to_it():
    """THE HINGE. Sollum carries the Commonwealth's OWN Field Supply Depot (60.34), seeded EMPTY one
    22-CP lorry hop beyond Sidi Barrani -- and the old policy swept past the hex for a hundred and
    eleven Game-Turns without once standing on it. So Sollum stayed AXIS-CONTROLLED to the last turn
    of the war, no lorry would deliver into it and no dump would leapfrog onto it, and the third link
    of the Commonwealth's own chain sat dry all campaign.

    Take the hex and the supply comes up behind it (spine_awaits_control: what was missing was never
    distance, it was CONTROL). And the ten points are the least of it -- a stocked depot ON Sollum is
    what puts BARDIA, three hexes away and worth FIFTY, inside a Commonwealth supply trace for the
    first time in the campaign.

    *** PINNED ON THE HINGE ITSELF, NOT ON WINNING THE FIGHT FOR IT. *** The Axis now garrisons
    Sollum (it has the take-and-hold too), so the Commonwealth no longer walks onto the hex by
    Game-Turn 24 -- and an outcome test would then be measuring the Axis's defence, not this
    shortcut. What must hold, and what actually failed before spine_awaits_control existed, is the
    JUDGEMENT: a city carrying our OWN empty Field Supply Depot on an ENEMY-CONTROLLED hex is dry
    because of CONTROL, not distance, so it is claimed and a unit is sent -- and NO field dump is
    sent with it (the depot is already there; a second one would only mask it from the lorries)."""
    res = _run(24)
    assert res.initial.supply("AL-Stage-Sollum").empty        # seeded empty: hauled into, not filled
    fin = res.final

    # The hinge: our own depot, empty, on a hex the enemy holds -- distance is not the problem.
    assert campaign_claim.spine_awaits_control(fin, Side.ALLIED, SOLLUM)
    assert campaign_claim.depot_on(fin, Side.ALLIED, SOLLUM).empty
    assert fin.control_of(SOLLUM) == Control.AXIS

    # ...so a unit is claimed for it -- ALONE, with no field dump in tow.
    plan = {c.city: c for c in campaign_claim.claims(fin, Side.ALLIED, escort=True)}
    assert SOLLUM in plan, "Sollum is not even claimed -- the shortcut is dead"
    assert plan[SOLLUM].depot_id is None, "a field dump was sent to MASK the depot already on Sollum"

    # THE SHORTCUT'S EVIDENCE -- AND WHAT CHANGED UNDERNEATH IT. The hinge is untouched and asserted
    # above: the depot ON Sollum is still EMPTY and the hex is still ENEMY-HELD, which is what
    # spine_awaits_control reads and why Sollum is claimed with no dump in tow.
    #
    # What is no longer true is the old COROLLARY -- that a Commonwealth battalion standing on Sollum
    # today could not be fed there either, so gating the claim on can_be_fed alone would decline
    # Sollum for ever. It would not, now: the railway finally carries its charted 54.32 tonnage, so
    # the link BEHIND Sollum -- the Sidi Barrani Field Supply Depot -- is stocked, and a 32.16 trace
    # from Sollum reaches it. Before that fix the entire Commonwealth chain was dry (the railhead
    # held ZERO Fuel on every turn of the war) and the honest trace test said NO everywhere. The
    # judgement was right then and is right now; the ground under it is finally supplied.
    assert campaign_claim.depot_on(fin, Side.ALLIED, SOLLUM).empty      # the depot ON it: still dry
    # THE LINK BEHIND SOLLUM IS STOCKED -- which is the claim, and the only form of it that was ever
    # true. The Sidi Barrani Field Supply Depot now carries a real reservoir (the charted [60.44]
    # start-line stock, kept topped up by the [60.43] lorry park off the rail-fed railhead), so the
    # chain the offensive advances along is alive and the ground under this claim is supplied.
    #
    # What this used to assert -- that the claimed battalion could be FED standing on Sollum -- was a
    # latent falsehood that happened to pass. The unit the claim sends is 24-Aus-Bde: FOOT, CPA 10,
    # so a 32.16 trace of cpa/2 reaches FIVE Capability Points on foot. Sidi Barrani is TEN HEXES from
    # Sollum. It was never reachable, and never could be. The old assertion passed only because one of
    # the army's MOBILE field dumps (32.3) happened to be parked one hex off Sollum on Game-Turn 24 of
    # this one seed -- the army's own baggage, not "the chain behind Sollum" at all. A unit standing
    # on Sollum is fed by the depot ON Sollum, which is what the lorries fill once the offensive takes
    # the hex; that is the whole reason the depot is seeded there empty.
    barrani = fin.supply("AL-Stage-Barrani")
    assert barrani.ammo > 0 and barrani.fuel > 0, \
        "the chain behind Sollum is dry -- the rail faucet or the lorry park is dead"


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
    after a depot arrives at Sollum it would march straight off again to the head of the column and
    the city it had just made bankable would stop scoring.

    ASKED OF THE AXIS, because that is where a depot is now doing this job. Both policies run the
    identical side-generic transform (campaign_policy.take_and_hold_supply), and the Axis is the side
    that at Game-Turn 24 is feeding a banked city off a FIELD dump (AX-Dump#5, standing on Sollum);
    the Commonwealth banks only cities its seeded SPINE already feeds, which garrison_depots
    deliberately does not pin (a staging depot is immobile anyway -- see the docstring there). Asking
    the Commonwealth here would be a vacuous test, and it says so out loud."""
    fin = _run(24).final
    pol = CampaignAxisPolicy()
    pinned = campaign_claim.garrison_depots(fin, Side.AXIS)
    assert pinned, "no depot is feeding a banked city -- the check is vacuous"
    moved = {o.supply_id for o in pol.supply_orders(fin, Side.AXIS)}
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
                   + sum(getattr(t, c.lower()) for t in res.final.trucks)
                   + sum(getattr(u, c.lower()) for u in res.final.units))   # 49.14 unit tanks (Phase 4)
        assert on_hand + res.final.consumed.get(c, 0) == initial


def test_rommel_and_siege_stay_byte_identical():
    """THE HARD CONSTRAINT. Every helper in game.campaign_claim needs the rule-64.73 city table, and
    rommels_arrival / siege_of_tobruk do not carry one (_cities returns () for them), so the two
    benchmark scenarios must hash exactly as they did before this slice existed."""
    axis = ScriptedPolicy(Side.AXIS)
    baselines = BENCHMARKS            # tests/baselines.py -- the ONE place, and why they moved
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
