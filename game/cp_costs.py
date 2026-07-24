"""Load the 6.3 Capability Point Expenditure costs from data/cp_costs.json.

Mirrors game.logistics_data / game.combat_tables: a thin, cached reader that turns
the transcribed 6.3 chart into the constants the combat engine charges at the
barrage / anti-armor / close-assault / defend / break-contact / disengage seams, so
the magnitudes are the RULEBOOK'S (one source of truth) rather than literals scattered
through game/*.py. Each accessor cites the 6.3 row it draws from.

Transcribed (6.3 CAPABILITY POINT EXPENDITURE SUMMARY):
  Phasing unit     -- Barrage and/or an Assault other than a Probe = 5; Undergo a
                      Barrage = 3; Probe = 2.
  Non-Phasing unit -- Barrage and/or undergo a Barrage and/or defend against an
                      Assault other than a Probe = 3; Defend against a Probe = 2.
  Break Contact    = 2;  Disengage = 4.

WIRED here: the assault/defend magnitudes (assault_cost) and the Contact/Engaged
break-off costs (break_contact_cost / disengage_cost). The chart's 'and/or' lumps a
unit's barrage + anti-armor + close-assault into ONE Assault charge, so the engine
charges each unit its combat CP once per Combat Segment (see engine._charge_combat_cp).

ALSO WIRED: the chart's four ORGANIZATION rows (detach 1 / attach an assigned unit 1 /
attach an unassigned unit 2 / absorb 2 TOE Replacement Strength Points 1), which rule 19
charges in the Reorganization Segment. Each is billed to BOTH counters the cell names --
"(Parent Formation and detaching unit)" -- exactly as 19.41-19.44 repeat in prose.

STILL UNCONSUMED (transcribed for the record): the Probe (2) and Undergo-Barrage (3)
rows -- the engine does not yet model a distinct Probe. Movement's own CP costs
(terrain/minefield TEC) are charged through UNIT_MOVED.cp_spent, not from here.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "cp_costs.json"))


@lru_cache(maxsize=1)
def _data() -> dict:
    with open(_PATH) as f:
        return json.load(f)


def assault_cost(phasing: bool) -> int:
    """6.3: the CP a unit spends on its combat this Segment. A Phasing unit pays the
    5-CP 'Barrage and/or an Assault other than a Probe'; a Non-Phasing unit pays the
    3-CP 'Barrage and/or undergo a Barrage and/or defend against an Assault'."""
    d = _data()
    return (d["phasing_unit"]["barrage_or_assault"] if phasing
            else d["non_phasing_unit"]["barrage_or_defend"])


def break_contact_cost() -> int:
    """6.3: Break Contact = 2 (leaving an enemy ZOC that a unit merely borders)."""
    return _data()["break_contact"]


def disengage_cost() -> int:
    """6.3: Disengage = 4 (leaving contact while carrying the 15.81 Engaged marker)."""
    return _data()["disengage"]


def detach_cost() -> int:
    """6.3: "Detach a unit (Parent Formation and detaching unit) = 1" -- charged to both
    counters (19.43/19.44: "a cost of one Capability Point each to both units")."""
    return _data()["organization"]["detach"]


def attach_cost(assigned: bool) -> int:
    """6.3: "Attach an assigned unit = 1", "Attach an unassigned unit = 2" -- each to both
    the Parent Formation and the attaching unit (19.41/19.42). The price of the ad hoc
    Kampfgruppe is the higher one: nothing is assigned to a Battle Group."""
    d = _data()["organization"]
    return d["attach_assigned"] if assigned else d["attach_unassigned"]


def absorb_cost() -> int:
    """6.3: "Absorb 2 TOE Replacement Strength Points (PF + absorbing unit) = 1" -- 19.68's
    price for rebuilding, per two Replacement Points added."""
    return _data()["organization"]["absorb_2_replacement_points"]
