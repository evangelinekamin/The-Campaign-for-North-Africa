"""The campaign Axis multi-hop coastal supply haul (rules 60.33/60.34): seeded staging dumps
plus a CAMPAIGN-ONLY truck policy (game.campaign_policy.campaign_truck_orders / CampaignAxisPolicy)
that relays Benghazi's landed tonnage forward LEG BY LEG, where the shared single-hop base relay
can only shuttle the rear port. The linchpin of the balance slice.

Byte-identity is the HARD constraint: rommels_arrival / siege_of_tobruk must stay untouched
(they seed their trucks through the byte-locked base relay). test_rommel_and_siege_stay_byte_
identical pins their exact determinism_signature baselines in-suite.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords                                             # noqa: E402
from game.apply import fold                                         # noqa: E402
from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy  # noqa: E402
from game.campaign_victory import CampaignVictory                   # noqa: E402
from game.engine import determinism_signature, run                 # noqa: E402
from game.events import Side                                        # noqa: E402
from game.hexmap import distance                                   # noqa: E402
from game.policy import ScriptedPolicy                             # noqa: E402
from game.scenario import campaign, rommels_arrival, siege_of_tobruk  # noqa: E402
from game.state import TruckFormation                              # noqa: E402

_BENGHAZI = coords.to_axial(coords.parse("A4827"))
_ALEXANDRIA = coords.to_axial(coords.parse("E3613"))


def _hexes_east(hx) -> int:
    """How many hexes closer to the objective (Alexandria) than Benghazi -- a dump's depth
    down the haul. Positive = east of the port; the base relay tops out at ~+7 (the first
    staging dump), the campaign relay walks the whole chain."""
    return distance(_BENGHAZI, _ALEXANDRIA) - distance(hx, _ALEXANDRIA)


def test_gt1_campaign_relay_hauls_where_the_base_shuttle_strands():
    """Blueprint contrast (a), corrected to the shipped seeds. At GT1 the campaign relay is
    non-empty -- it lifts Benghazi's 60.34 stock onto the first staging dump. (With the dumps
    seeded one 30-CP hop from the port, the base relay is ALSO non-empty at GT1: it CAN make
    that first lift -- so the naive "base empty at GT1" does not hold once the chain is in
    reach.) The base's real inadequacy is that it can only ever reload at the rear PORT: a
    truck sitting on a forward staging dump, out of cargo fuel, can neither reload there nor
    afford the drive back -- so the base emits nothing, while the campaign relay loads from
    that forward dump and pushes the stock DEEPER east."""
    st = campaign(seed=1941)
    # (1) on GAME-TURN 1 the campaign relay hauls Benghazi's stock forward. Asked of a RUN, not of
    # the raw construction state: with the [60.33] park seeded to its charted strength the Axis pool
    # is 215 Truck Points, and the 150-Point Medium convoy burns 900 Fuel on a 30-CP hop (49.18)
    # against the 250 Fuel Points the 60.34 chart leaves at Benghazi -- so at the instant of
    # construction it genuinely cannot afford to roll. It rolls in the Truck Convoy Phase, once the
    # Logistics Phase has landed the month's convoy in the port beneath it, which is Game-Turn 1.
    res = run(campaign(seed=1941, max_turns=1), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert [e for e in res.events
            if e.kind.name == "TRUCK_MOVED" and e.side == Side.AXIS and e.turn == 1], \
        "the campaign relay hauled nothing on Game-Turn 1"

    # (2) a truck out of cargo fuel on the (now stocked) first staging dump W1.
    w1 = (5, 36)
    supplies = tuple(replace(s, ammo=40, fuel=400, stores=40) if s.id == "AX-Stage-W1" else s
                     for s in st.supplies)
    stranded = replace(st, supplies=supplies,
                       trucks=(TruckFormation("AX-Truck-H", Side.AXIS, w1, "heavy", points=8, line=3),))
    # the base can only reload at the port and cannot afford to get there -> nothing.
    assert ScriptedPolicy(Side.AXIS).truck_orders(stranded, Side.AXIS) == []
    # the campaign relay reloads from the co-located W1 and hauls the stock deeper east.
    camp = CampaignAxisPolicy().truck_orders(stranded, Side.AXIS)
    assert len(camp) == 1 and camp[0].load_from == "AX-Stage-W1"
    assert _hexes_east(camp[0].to) > _hexes_east(w1)


def test_acceptance_haul_runs_unfrozen_and_reaches_the_front():
    """Blueprint acceptance, CORRECTED. The old test asserted only unload DEPTH into dumps -- but
    the deep EARLY deliveries reach +40 hexes even when the pool then FREEZES (the shipped relay
    stranded both trucks out of cargo fuel by GT3-4, 16 lifetime moves). Depth alone masked the
    bug. The real acceptance is that the lean pool keeps RUNNING, supply reaches FORWARD along the
    chain, and the front is supplied while it is still within the chain's reach:

      (i)   NO FREEZE -- truck moves keep occurring well past GT10 (the buggy relay's last was GT3).
      (ii)  FORWARD REACH -- the relay lands fuel AND ammo deep east of Benghazi (the base shuttle
            tops out ~+7 hexes), and a deep staging dump still holds both commodities at GT24.
      (iii) FRONT SUPPLIED -- at least one Axis front combat unit traces supply near the chain in
            the opening, BEFORE the greedy scripted rush outruns its logistics (a faithful
            culmination: by ~GT10 the rush has driven the front ~110 hexes east, out of the cpa/2
            trace range of even its leapfrogging field dumps -- see campaign_truck_orders)."""
    res = run(campaign(seed=1941, max_turns=24), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    # The depot list is no longer FROZEN at construction: rule 54.11 lets an army found a dump on any
    # hex, and the relay now extends its chain forward onto the ground the army is standing on
    # (campaign_policy._forward_depot_sites). So a TRUCK_UNLOADED may name a depot that did not exist
    # at t0 -- fold the SUPPLY_DUMP_ESTABLISHED events in, or the lookup below KeyErrors on the first
    # dump the lorries build.
    dump_hex = {s.id: s.hex for s in res.initial.supplies}
    dump_hex.update({e.payload["supply_id"]: tuple(e.payload["hex"]) for e in res.events
                     if e.kind.name == "SUPPLY_DUMP_ESTABLISHED"})

    gt = moves_past_10 = deepest = 0
    fuel_east = ammo_east = False
    for e in res.events:
        if e.kind.name == "TURN_ADVANCED":
            gt = e.payload.get("turn", gt)
        elif e.kind.name == "TRUCK_MOVED" and gt > 10:
            moves_past_10 += 1
        elif e.kind.name == "TRUCK_UNLOADED":
            east = _hexes_east(dump_hex[e.payload["supply_id"]])
            if east > 0:                                    # deliveries strictly east of the port
                cargo = e.payload["cargo"]
                fuel_east = fuel_east or cargo.get("FUEL", 0) > 0
                ammo_east = ammo_east or cargo.get("AMMO", 0) > 0
                deepest = max(deepest, east)

    assert moves_past_10 > 0, "the truck pool froze -- no truck moves past GT10"
    assert fuel_east and ammo_east, "no fuel/ammo landed east of Benghazi"
    assert deepest >= 40, f"relay only reached +{deepest} hexes east (base shuttle stalls at ~+7)"
    bardia = next(s for s in res.final.supplies if s.id == "AX-Stage-Bardia")
    assert bardia.fuel > 0 and bardia.ammo > 0, "the deep chain is not kept fed"

    # (iii) at least one Axis front combat unit is supplied near the chain in the opening, before
    # the greedy rush drives it out of trace range (the final-GT count is 0 -- the culmination).
    early = run(campaign(seed=1941, max_turns=6),
                CampaignAxisPolicy(), CampaignCommonwealthPolicy()).final
    victory = CampaignVictory()
    supplied = [u for u in early.units if u.side == Side.AXIS and u.is_combat
                and early.on_map(u) and u.strength >= 1 and victory._supplied(early, u)]
    assert supplied, "no Axis combat unit supplied near the chain in the opening"


def test_conservation_holds_over_the_haul():
    """Blueprint (c): the haul only MOVES supply between dumps (load/move/unload) -- it mints
    and destroys nothing, so the recorded log folds byte-identically back to the final state."""
    res = run(campaign(seed=1941, max_turns=16), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert fold(res.initial, res.events) == res.final


def test_rommel_and_siege_stay_byte_identical():
    """Blueprint (d) + the HARD constraint: seeding the campaign's staging dumps and adding the
    campaign truck policy must not perturb the benchmark scenarios one byte. Their
    determinism_signature (axis=allied=ScriptedPolicy(AXIS), seed 42) must hold at the pre-change
    baseline, and no 'AX-Stage' campaign dump may leak into their supplies."""
    axis = ScriptedPolicy(Side.AXIS)
    baselines = {"rommel": "9339d2b308d7", "siege": "5ba4da88d107"}
    for name, build in (("rommel", rommels_arrival), ("siege", siege_of_tobruk)):
        res = run(build(seed=42), axis, axis)
        sig = hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
        assert sig == baselines[name], f"{name} byte-identity broken: {sig} != {baselines[name]}"
        assert not any(s.id.startswith("AX-Stage") for s in build(seed=42).supplies)
