"""Step 1-2: the formation-scoped lanes + the cross-lane conflict filter.

lane_of partitions living(AXIS) into three DISJOINT lanes whose union is every
combat unit; role_brief slices the single observation to a lane; cross_lane_
conflicts keeps only the collisions that span >= 2 lanes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.adjudication import Conflict, validate_batch
from game.events import Side
from game.observation import observe
from game.policy import MoveOrder
from game.scenario import rommels_arrival
from game.staff import (
    MOBILE_FORMATIONS,
    Lane,
    cross_lane_conflicts,
    lane_of,
    role_brief,
    unit_lanes,
)


def _axis():
    s = rommels_arrival(seed=4200)
    return s, s.living(Side.AXIS)


def test_lanes_partition_the_living_combat_units():
    s, living = _axis()
    lanes = {Lane.MOBILE: set(), Lane.INFANTRY: set(), Lane.QM: set()}
    for u in living:
        if u.is_combat:
            lanes[lane_of(u)].add(u.id)
    # pairwise DISJOINT
    ids = [v for v in lanes.values()]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            assert ids[i].isdisjoint(ids[j])
    # union == EVERY combat unit in living(AXIS)
    union = lanes[Lane.MOBILE] | lanes[Lane.INFANTRY] | lanes[Lane.QM]
    assert union == {u.id for u in living if u.is_combat}


def test_role_brief_mobile_ids_are_exactly_the_panzer_and_ariete_formations():
    s, living = _axis()
    obs = observe(s, Side.AXIS)
    idl = unit_lanes(s, Side.AXIS)
    brief = role_brief(obs, Lane.MOBILE, idl)
    got = {u["id"] for u in brief["your_units"]}
    expected = {u.id for u in living if u.formation in MOBILE_FORMATIONS}
    assert got == expected
    assert expected                       # non-empty (5th Light + Ariete on-map at t0)


def test_role_brief_is_a_pure_projection_that_keeps_shared_context():
    s, _ = _axis()
    obs = observe(s, Side.AXIS)
    idl = unit_lanes(s, Side.AXIS)
    before = len(obs["your_units"])
    brief = role_brief(obs, Lane.INFANTRY, idl)
    assert len(obs["your_units"]) == before          # obs not mutated
    assert brief["objective"] == obs["objective"]     # shared context preserved
    assert brief["your_supplies"] == obs["your_supplies"]
    assert all(idl[u["id"]] == Lane.INFANTRY for u in brief["your_units"])


def test_cross_lane_filter_keeps_two_lane_collision_drops_intra_lane():
    s, living = _axis()
    idl = unit_lanes(s, Side.AXIS)
    mobile = [u for u in living if lane_of(u) == Lane.MOBILE]
    infantry = [u for u in living if lane_of(u) == Lane.INFANTRY]
    m1, m2 = mobile[0].id, mobile[1].id
    inf = infantry[0].id
    cross = Conflict("over-stack", (0, 0), (m1, inf))     # MOBILE + INFANTRY
    same = Conflict("over-stack", (0, 0), (m1, m2))       # MOBILE only
    kept = cross_lane_conflicts([cross, same], idl)
    assert kept == [cross]


def test_cross_lane_filter_over_a_real_validate_batch_collision():
    """A cross-lane over-stack the dry-run actually detects: pile several INFANTRY
    battalions and one MOBILE unit onto a single hex until the stacking limit breaks.
    validate_batch flags the over-stack; cross_lane_conflicts surfaces it (spans the
    MOBILE and INFANTRY lanes) rather than dropping it as an intra-lane bug."""
    s, living = _axis()
    idl = unit_lanes(s, Side.AXIS)
    mobile = next(u for u in living if lane_of(u) == Lane.MOBILE and u.is_combat)
    infantry = [u for u in living if lane_of(u) == Lane.INFANTRY and u.is_combat]
    target = infantry[0].hex
    # Everyone converges on infantry[0]'s hex -- far beyond any hex limit, so the fold
    # is guaranteed to over-stack, and the pile mixes both lanes.
    orders = [MoveOrder(mobile.id, target)] + [MoveOrder(u.id, target) for u in infantry[1:]]
    conflicts = validate_batch(s, orders)
    over = [c for c in conflicts if c.kind == "over-stack" and c.hex == target]
    assert over                                           # the pile over-stacks
    kept = cross_lane_conflicts(conflicts, idl)
    assert any(c.hex == target for c in kept)             # surfaced as cross-lane


def test_campaign_mobile_formations_route_to_the_mobile_corps():
    # Staff-on-campaign convergence: the full-campaign OOB uses different group strings than
    # Rommel's Arrival ("GE 5th Light Division", "IT 132 Ariete Division", "IT The Libyan Tank
    # Command"), so lane_of matches the mobile MARKERS -- keeping the panzer/light divisions,
    # the Italian armour and the Libyan Tank Command in the Mobile Corps, not the Infantry.
    from game.scenario import campaign
    st = campaign(seed=1941)   # over all units: the panzers arrive as reinforcements (GT18+)
    axis = [u for u in st.units if u.side == Side.AXIS]
    mob = {u.formation for u in axis if lane_of(u) == Lane.MOBILE}
    assert any("Panzer" in f for f in mob)                 # 15 Panzer Division (reinforcement)
    assert any("Light Division" in f for f in mob)         # 5th / 90th / 164th Light
    assert any("Ariete" in f for f in mob)                 # Italian armour
    assert any("Tank Command" in f for f in mob)           # the Libyan Tank Command (on-map GT1)
    inf = {u.formation for u in axis if lane_of(u) == Lane.INFANTRY}
    assert any("Catanzaro" in f for f in inf)              # Italian foot -> Infantry Corps
    assert not any("Panzer" in f or "Tank Command" in f for f in inf)
