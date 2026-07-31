"""GATE 8.1d, QUESTION 1 (static half) -- THE DIVISION-HQ CENSUS, before vs after.

Read-only.  Changes NOTHING in game/ or data/.  Runs UNMODIFIED in both arms -- BASE, the detached
worktree at a6c9700 (the last commit before the division-HQ pass), and HEAD at 607b63c.  Every
symbol it touches (game.oob._org_tree, Unit.assigned_to / org_type / is_combat,
campaign_policy.concentrate_formations) landed with the [4.45] parent-tree slice at 083f0dc, an
ancestor of both, so the only thing that can differ between the arms is the ORDER OF BATTLE.

WHAT IT ANSWERS.  "How many formations have an HQ now that had none?" is two different questions and
this file keeps them apart, because the slice's whole finding lives in the gap between them:

  ON PAPER   -- a formation is a counter string that some other counter names as its `parent` in
                data/oob_organization_4_45.json.  It "has an HQ" when that parent counter is
                actually mustered into the campaign order of battle, i.e. when
                oob._seed_organization could resolve it to a unit id at all.  An unresolved parent
                is a formation whose sub-units are on the map with nothing above them.
  ON THE MAP -- [19.12] attachment is a SAME-HEX relationship and engine._reorganize will only fold
                a unit into a parent that campaign_policy.concentrate_formations proposed; that
                proposer is confined to parents which are themselves COMBAT counters (a bare HQ is
                moved by no proposer in this engine, so a formation folded into one would freeze).
                So a formation can gain its chart-printed HQ and still be unable to concentrate.

Both counts are read through the engine's own symbols, never re-implemented here.  The t0 call to
concentrate_formations is the direct, executable form of the second question.

Usage:  PYTHONPATH=<tree> python3 <tree>/scratchpad/gate81d_formations.py --out <path.json>
"""
from __future__ import annotations

import argparse
import json
from collections import Counter


def _role(u) -> str:
    """The counter's kind, in the vocabulary this gate reports: HQ^E / HQ / combat / other."""
    if getattr(u, "engineer", "") == "HQ_ENGINEER":
        return "hq_engineer"
    if not u.is_combat and getattr(u, "org_type", ""):
        return "hq"
    if not u.is_combat:
        return "non_combat"
    return "combat"


def census(seed: int) -> dict:
    from game import oob
    from game.campaign_policy import (CampaignAxisPolicy, CampaignCommonwealthPolicy,
                                      concentrate_formations)
    from game.events import Side
    from game.scenario import campaign

    init = campaign(seed=seed)
    units = list(init.units)
    by_id = {u.id: u for u in units}

    # --- ON PAPER: the [4.45] tree's own parent edges, resolved against the mustered OOB. --------
    tree = oob._org_tree()
    counter_to_id = {}
    for u in units:
        c = getattr(u, "counter", None)
        if c:
            counter_to_id[c] = u.id
    # oob.build() owns the real counter->id map; reconstruct it the only way a read-only driver can,
    # and fall back to the seeded assigned_to edges (which ARE that map's output) for the census.
    formations: dict[str, dict] = {}
    for counter, spec in tree.items():
        parent = spec.get("parent", "")
        if not parent:
            continue
        formations.setdefault(parent, {"counter": parent, "children_on_paper": 0})
        formations[parent]["children_on_paper"] += 1

    # The AUTHORITATIVE resolution: assigned_to is what _seed_organization actually wrote, so a
    # formation whose HQ the OOB carries shows up as a live parent id on at least one unit.
    kids: dict[str, list] = {}
    for u in units:
        if u.assigned_to:
            kids.setdefault(u.assigned_to, []).append(u)

    resolved = []
    for pid, children in sorted(kids.items()):
        p = by_id.get(pid)
        resolved.append({
            "parent_id": pid,
            "parent_counter": getattr(p, "counter", None) if p else None,
            "parent_exists": p is not None,
            "parent_side": p.side.value if p else None,
            "parent_role": _role(p) if p else None,
            "parent_is_combat": bool(p.is_combat) if p else None,
            "parent_org_type": getattr(p, "org_type", "") if p else None,
            "parent_on_map_at_setup": bool(init.on_map(p)) if p else None,
            "parent_arrival_turn": getattr(p, "arrival_turn", None) if p else None,
            "children": len(children),
            "child_ids": sorted(u.id for u in children),
        })

    def side_counts(pred) -> dict:
        c = Counter(r["parent_side"] for r in resolved if pred(r))
        return {"AXIS": c.get("AXIS", 0), "ALLIED": c.get("ALLIED", 0),
                "total": sum(v for k, v in c.items() if k)}

    # --- ON THE MAP: what concentrate_formations can actually propose at t0. ---------------------
    ax_orders = concentrate_formations(init, Side.AXIS)
    al_orders = concentrate_formations(init, Side.ALLIED)

    def order_summary(orders) -> dict:
        att = [o for o in orders if o.kind == "attach"]
        return {"orders": len(orders),
                "attach": len(att),
                "detach": sum(1 for o in orders if o.kind == "detach"),
                "distinct_parents_attached_to": sorted({o.parent_id for o in att}),
                "attach_pairs": sorted((o.parent_id, o.unit_id) for o in att)}

    # The counters this slice claims to have seeded, named so a diff of the two arms is legible.
    hq_roster = [
        {"id": u.id, "counter": getattr(u, "counter", None), "side": u.side.value,
         "role": _role(u), "org_type": getattr(u, "org_type", ""),
         "is_combat": bool(u.is_combat), "engineer": getattr(u, "engineer", ""),
         "arrival_turn": getattr(u, "arrival_turn", None),
         "on_map_at_setup": bool(init.on_map(u)),
         "hex": list(u.hex) if init.on_map(u) else None,
         "children_assigned": len(kids.get(u.id, ()))}
        for u in sorted(units, key=lambda u: (u.side.value, u.id))
        if _role(u) in ("hq", "hq_engineer")
    ]

    return {
        "seed": seed,
        "units_the_war_ever_contains": len(units),
        "units_by_side": dict(sorted(Counter(u.side.value for u in units).items())),
        "role_census": dict(sorted(Counter(f"{u.side.value}/{_role(u)}" for u in units).items())),
        "paper_parent_counters_named_by_the_4_45_tree": len(formations),
        "formations_with_a_live_parent": side_counts(lambda r: r["parent_exists"]),
        "formations_whose_parent_is_a_COMBAT_counter": side_counts(
            lambda r: r["parent_exists"] and r["parent_is_combat"]),
        "formations_whose_parent_is_a_BARE_HQ": side_counts(
            lambda r: r["parent_exists"] and not r["parent_is_combat"]),
        "formations_with_a_DANGLING_parent_id": [r for r in resolved if not r["parent_exists"]],
        "formations": resolved,
        "hq_roster": hq_roster,
        "concentrate_formations_at_t0": {
            "AXIS": order_summary(ax_orders), "ALLIED": order_summary(al_orders)},
        "_policies_constructed": [CampaignAxisPolicy().__class__.__name__,
                                  CampaignCommonwealthPolicy().__class__.__name__],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=4)
    args = ap.parse_args()
    doc = census(args.seed)
    with open(args.out, "w") as f:
        json.dump(doc, f, indent=1)
    slim = {k: v for k, v in doc.items()
            if k not in ("formations", "hq_roster", "_policies_constructed")}
    print(json.dumps(slim, indent=1))
    print(f"hq_roster: {len(doc['hq_roster'])} HQ counters")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
