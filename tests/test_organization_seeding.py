"""[4.45] THE HISTORICAL SETUP FORMATION TREE -- the seeding that makes [15.53] REACHABLE.

Rule 19 (Block 7.1) built the assign/attach machinery and the [15.53] Organization Size chart, but
Gate 7A found it UNDRIVEN: game.oob seeded no org_type and no parent, so every campaign counter was
an independent SP-1 battalion and the chart's Brigade / Super-Brigade / Division rows were physically
unreachable -- it could only ever fire on its lowest (1,0) battalion-vs-company edge.

This block seeds the tree from the three [4.45a/b/c] Organization at Arrival Charts
(data/oob_organization_4_45.json, applied by game.oob._seed_organization): each mapped counter gets
its [19.11] paper parent (assigned_to) and each formation HQ its [19.3] org_type. The org_type is the
load-bearing bit -- it lifts an HQ counter's Stacking-Point tier above 1 -- so the moment a formation
concentrates and its units attach (19.12), organization.combat_size returns the formation's size and
[15.53] reaches a tier no counter could reach before.

`attached_to` is NOT seeded (the extraction scatters each formation one unit per hex; 19.12 attachment
is same-hex), so the campaign log gains no attachment until a policy forms one -- these tests prove the
tree makes the tier REACHABLE, which is the block's whole claim.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import combat_tables, oob, organization


def _campaign_units():
    units, _ = oob.build(oob_file="oob_italian.json", extra_file="oob_campaign_extra.json",
                         sections="ABCDE", reinforcements_file="reinforcements_campaign.json",
                         dump_pools=oob.CAMPAIGN_DUMP_POOLS, first_line=oob.CAMPAIGN_FIRST_LINE)
    return {u.id: u for u in units}


# --- the tree is seeded onto the OOB ------------------------------------------------------

def test_the_4_45_tree_seeds_org_type_on_hqs_and_parents_on_children():
    by = _campaign_units()
    div = by["HQ-50-Inf-Div"]
    assert div.org_type == "cw_infantry_division"           # [19.3] division row -> SP tier 5
    bde = by["HQ-69-Inf-Bde"]
    assert bde.org_type == "cw_infantry_brigade"            # [19.3] brigade row -> SP tier 2
    assert bde.assigned_to == div.id                        # [19.11] brigade assigned to the division
    assert by["69-Inf-Bde-I"].assigned_to == bde.id         # battalion assigned to its brigade
    # a German panzer regiment nested under its division
    assert by["HQ-8-Pz-Regt"].org_type == "ge_armored_regiment"
    assert by["I/8-Pz-Bn"].assigned_to == "HQ-8-Pz-Regt"
    assert by["HQ-8-Pz-Regt"].assigned_to == "HQ-15-Panzer-Div"


def test_seeding_touches_the_campaign_but_not_the_desert_fox_benchmarks():
    campaign = _campaign_units()
    assert sum(1 for u in campaign.values() if u.org_type) > 60      # the seeded formation HQs
    # the two signature-pinned benchmarks build oob_desert_fox.json, whose counters are NOT in the
    # [4.45] tree -- so they gain no org_type and their determinism signatures are untouched.
    df, _ = oob.build()
    assert sum(1 for u in df if u.org_type) == 0
    assert sum(1 for u in df if u.assigned_to) == 0


# --- [15.53] is now REACHABLE: a concentrated seeded formation reads its tier ---------------

def _concentrate(by, div_id, tree):
    """Put a division HQ + the given {brigade_id: [battalion_ids]} in one hex, ATTACHED up the
    chain (19.12) -- the map act a player performs to fight as a division. Returns the stack."""
    H = (20, 20)
    div = replace(by[div_id], hex=H, attached_to="")
    stack = [div]
    for bde_id, bns in tree.items():
        stack.append(replace(by[bde_id], hex=H, attached_to=div.id))
        stack += [replace(by[b], hex=H, attached_to=bde_id) for b in bns]
    return stack


def test_a_seeded_division_fully_concentrated_reads_combat_size_five():
    by = _campaign_units()
    # the 50th (Northumbrian) Division: HQ + three infantry brigades, each with its three battalions.
    stack = _concentrate(by, "HQ-50-Inf-Div", {
        "HQ-69-Inf-Bde": ["69-Inf-Bde-I", "69-Inf-Bde-II", "69-Inf-Bde-III"],
        "HQ-151-Inf-Bde": ["151-Inf-Bde-I", "151-Inf-Bde-II", "151-Inf-Bde-III"],
        "HQ-150-Inf-Bde": ["150-Inf-Bde-I", "150-Inf-Bde-II", "150-Inf-Bde-III"],
    })
    # [15.53] Largest Unit On: the division, in size-equivalents -- 5, the Division tier, NOT 1.
    assert organization.combat_size(stack) == 5
    # and the chart it feeds yields a real shift: a division over a lone battalion is +4 columns.
    assert combat_tables.org_size_shift(5, 1) == 4
    assert combat_tables.org_size_shift(5, 0) == 8      # division over a company


def test_a_seeded_regiment_with_two_battalions_reads_the_brigade_tier():
    by = _campaign_units()
    # the 64th Catanzaro's 141st Infantry Regiment (an it_infantry_regiment, SP 2). No division-HQ
    # counter exists for the Catanzaro (melded), but the regiment alone lifts [15.53] off SP 1.
    reg = replace(by["IT-141---64-Cat"], hex=(9, 9), attached_to="")
    b1 = replace(by["IT-I-141---64-Cat"], hex=(9, 9), attached_to=reg.id)
    b2 = replace(by["IT-II-141---64-Cat"], hex=(9, 9), attached_to=reg.id)
    assert organization.combat_size([reg, b1, b2]) == 2         # Brigade tier, not 1
    assert combat_tables.org_size_shift(2, 0) == 4              # regiment over a company


def test_without_the_tree_the_same_battalions_are_stuck_at_the_battalion_tier():
    """The neuter: strip org_type off the HQs and detach -- the pre-slice state, where every counter
    is an independent SP-1 battalion and [15.53] cannot leave its (1,0)/(1,1) edge. This is exactly
    what the chart saw for 111 turns before this block."""
    by = _campaign_units()
    battalions = [by["69-Inf-Bde-I"], by["69-Inf-Bde-II"], by["151-Inf-Bde-I"]]
    independent = [replace(u, org_type="", attached_to="", assigned_to="") for u in battalions]
    assert organization.combat_size(independent) == 1          # the ceiling before the tree
    assert combat_tables.org_size_shift(1, 1) == 0             # equal battalions: no shift at all
