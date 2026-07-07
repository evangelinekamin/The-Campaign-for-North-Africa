"""Formation-scoped staff lanes (the command-hierarchy scoping key).

The staff layer partitions a side's forces into DISJOINT lanes keyed on
Unit.formation (the OOB group string carried at state.py:61). Each lane maps 1:1
to an order-type seat:

  * MOBILE   -- GOC Mobile Corps: the panzer + Ariete armoured formations.
  * INFANTRY -- GOC Infantry Corps: the Italian/German foot, the Oasis battalions,
    the non-divisional artillery, and the unassigned-infantry HQ counters.
  * QM       -- Quartermaster: the first-line truck carriers (the dumps + 2nd/3rd-
    line trucks it also owns are SupplyUnit/TruckFormation, not Unit, so they never
    appear here).

Disjointness guarantees no illegal cross-lane order: a GOC can only ever name a
unit in its own set, and the engine's u.side/ownership re-check is the backstop.
role_brief is a PURE PROJECTION over the single observe() call -- it slices
your_units / attack_options to a lane while keeping the shared context; observe()
itself is never touched. cross_lane_conflicts filters adjudication.validate_batch
to the collisions the Chief must actually rule on (an intra-lane over-stack is a
specialist's own bug the engine rejects anyway).
"""
from __future__ import annotations

import enum

from .events import Side
from .state import GameState, Unit


class Lane(enum.Enum):
    MOBILE = "MOBILE"
    INFANTRY = "INFANTRY"
    QM = "QM"


# The armoured/mobile formations -- verbatim rommels_arrival OOB group strings.
# IT Ariete is placed with the panzers (ADOPTED DECISION: Ariete -> GOC Mobile Corps).
MOBILE_FORMATIONS = frozenset({
    "GE 5th Light Panzer Division",
    "GE 15th Panzer Division",
    "IT Ariete Armoured Division",
})


def lane_of(unit: Unit) -> Lane:
    """The staff lane that owns `unit`, keyed on its formation (ground truth).
    First-line trucks are the Quartermaster's carriers; the mobile formations are
    the Mobile Corps; everything else is Infantry Corps."""
    if unit.is_first_line_truck:
        return Lane.QM
    if unit.formation in MOBILE_FORMATIONS:
        return Lane.MOBILE
    return Lane.INFANTRY


def unit_lanes(state: GameState, side: Side) -> dict[str, Lane]:
    """The lane of every on-map unit of `side` (id -> Lane) -- the partition the
    GOCs and the cross-lane filter both read."""
    return {u.id: lane_of(u) for u in state.living(side)}


# Shared context every seat keeps regardless of lane (the Chief's frame + the map
# picture); only your_units / attack_options are lane-scoped.
def role_brief(obs: dict, lane: Lane, id_lanes: dict[str, Lane]) -> dict:
    """A seat's brief: the single observe() view with your_units and attack_options
    FILTERED to `lane`'s units, all shared context (weather / objective / enemy
    sightings / supplies / ports / convoys) kept. A pure projection -- returns a NEW
    dict, never mutating obs."""
    ids = {uid for uid, ln in id_lanes.items() if ln == lane}
    units = [u for u in obs["your_units"] if u["id"] in ids]
    attacks = [a for a in obs.get("attack_options", [])
               if any(x in ids for x in a["your_attackers"])]
    return {**obs, "your_units": units, "attack_options": attacks}


# The two order-type resource seats (P5 Step 6) command NON-Unit resources -- the air
# force and the fleet/convoys -- so they carry no lane in the Unit partition (the Lane
# enum, unit_lanes and cross_lane_conflicts are all untouched, and a resource seat can
# never over-stack or clash on a dump with a GOC by construction). Their briefs are the
# same pure projection over the single observe() view, with your_units / attack_options
# emptied (they hold no ground units) and every shared field -- weather, objective,
# enemy_sightings, pending_convoys, your_ports -- kept for their non-Unit reasoning.
def _resource_brief(obs: dict) -> dict:
    return {**obs, "your_units": [], "attack_options": []}


def naval_brief(obs: dict) -> dict:
    """The Convoy officer's brief: the shared observation with the ground roster emptied.
    pending_convoys is its routing timetable, your_ports its harbour gauge, weather its
    sea state, enemy_sightings the lanes it may interdict -- a pure projection, never
    mutating obs."""
    return _resource_brief(obs)


def air_brief(obs: dict) -> dict:
    """The Air Marshal's brief: the shared observation with the ground roster emptied.
    weather gates flying (29.43/29.52), enemy_sightings are strike/recon targets, the
    objective frames the point of main effort -- a pure projection, never mutating obs."""
    return _resource_brief(obs)


def cross_lane_conflicts(conflicts: list, id_lanes: dict[str, Lane]) -> list:
    """Keep only the Conflicts whose contenders span >= 2 lanes -- the collisions the
    Chief must adjudicate. An intra-lane collision (all contenders one lane) is a
    single specialist's own over-reach; it drops silently (the engine rejects it)."""
    return [c for c in conflicts
            if len({id_lanes.get(uid) for uid in c.unit_ids} - {None}) >= 2]
