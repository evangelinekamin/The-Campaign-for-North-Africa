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
    # (1) at GT1 the campaign relay hauls Benghazi's stock forward.
    assert CampaignAxisPolicy().truck_orders(st, Side.AXIS)

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


def test_acceptance_haul_lands_fuel_and_ammo_deep_east_of_benghazi():
    """Blueprint acceptance (b): over ~16 GT with the canonical scripted campaign pairing, the
    truck relay lands BOTH fuel and ammo into dumps strictly EAST of Benghazi -- and walks the
    chain DEEP (the base shuttle tops out at the first staging dump ~+7 hexes; the relay reaches
    tens of hexes farther), the whole point of the multi-hop haul."""
    res = run(campaign(seed=1941, max_turns=16), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    dump_hex = {s.id: s.hex for s in res.initial.supplies}

    fuel_east = ammo_east = False
    deepest = 0
    for e in res.events:
        if e.kind.name != "TRUCK_UNLOADED":
            continue
        hx = dump_hex[e.payload["supply_id"]]
        east = _hexes_east(hx)
        if east <= 0:                                      # only deliveries strictly east of the port
            continue
        cargo = e.payload["cargo"]
        fuel_east = fuel_east or cargo.get("FUEL", 0) > 0
        ammo_east = ammo_east or cargo.get("AMMO", 0) > 0
        deepest = max(deepest, east)

    assert fuel_east, "no fuel landed east of Benghazi"
    assert ammo_east, "no ammo landed east of Benghazi"
    assert deepest >= 40, f"relay only reached +{deepest} hexes east (base shuttle stalls at ~+7)"


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
