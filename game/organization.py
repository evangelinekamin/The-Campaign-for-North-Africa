"""Rule 19 -- ORGANIZATION AND REORGANIZATION, and the [9.2] unit-equivalent arithmetic.

    "The Organization of the various units -- i.e., which battalions are part of which
     Brigade, which Brigades and support units form which Division, etc. -- is important
     to the play of the game, particularly as pertains to Stacking." (19.0 Commentary)

THIS MODULE IS WHY [15.53] REACHES ITS BRIGADE AND DIVISION TIERS. No counter in this engine
ever carries more than one Stacking Point -- the ten HQ / gun-type roles are SP 0, everything
else is SP 1 (game.oob) -- so the Organization Size Close Assault Modifications chart, a chart
transcribed exactly and verified against the scan, could only ever reach its lowest row: the
(1,0) "battalion vs. a lone company or gun" edge, worth a two-column shift. It could never
reach the Brigade / Super-Brigade / Division rows (2 / 3 / 5 SP), which read the size of each
side's LARGEST unit -- and a division or a Kampfgruppe is not a counter you are dealt, it is a
counter you BUILD by attaching battalions to a headquarters (9.12/9.21). Rule 19 is that
construction, and until it existed those tiers were unreachable.

THE TWO RELATIONS, and they are not the same thing (19.1):
  * ASSIGNED (19.11) is on paper. The unit is part of the Parent's organization and occupies
    its TOE space wherever it physically stands (19.28). Bounded by the [19.3] Formation
    Organization Chart.
  * ATTACHED (19.12) is on the map. "Not only are both the attached unit and the Parent
    Formation in the same hex, but they are functionally combined into one unit" -- the
    Parent's counter represents both, so the subsidiary stacks at zero on its own account
    and the FORMATION's size is what every size-sensitive rule reads. Bounded, for units NOT
    assigned to that Parent, by the [19.5] Maximum Attachment Chart.

Both charts are transcribed into data/ (formation_organization.json, maximum_attachment.json)
and read here; the Capability Point prices are the four organization rows of the [6.3] chart
(game.cp_costs). No magnitude in this file is a literal.

WHAT IS DELIBERATELY NOT HERE, and why. The historical starting tree -- who begins the game
assigned to whom -- is on the [4.44]/[4.45] Organization at Arrival Charts, which are not
transcribed (port plan T1-2). So this module builds and polices the tree; it does not seed
one. Everything defaults to independent, which is exactly what the engine had before.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import replace
from functools import lru_cache

from .state import StepRecord, Unit

_DATA = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))

# [9.4] UNIT BASIC STACKING POINT VALUES, as a ladder. [9.28]: "a unit that is a shell is
# reduced one level to the next lowest-level formation... a division shell would be considered
# a brigade equivalent, a brigade shell a battalion equivalent, and a battalion shell a company
# equivalent" -- which on the [9.4] chart's own Shell column is 5 -> 3 -> 2 -> 1 -> 0.
_SHELL_STEP: dict[int, int] = {5: 3, 3: 2, 2: 1, 1: 0, 0: 0}

# [9.26] The shell fractions, printed: a DIVISION is a shell at 50% or less of its assignable
# brigade-equivalents attached; a BRIGADE below two-thirds of its assignable battalions; a
# BATTALION below 50% of its maximum TOE Strength Points, or below 25% if it is artillery.
_DIVISION_SHELL_AT_OR_BELOW = 0.5
_BRIGADE_SHELL_BELOW = 2.0 / 3.0
_BATTALION_SHELL_BELOW = 0.5
_ARTILLERY_SHELL_BELOW = 0.25

# [19.82] "...if, at that point in time, all of his anti-tank units on the map (which includes
# the Tripoli-Tunisia boxes for this purpose) are at at least 67% of their maximum permitted
# TOE Strength."
_AT_AUGMENT_FLOOR = 0.67
# [19.83] "The initial assignment must be at least three TOE Strength Points."  [19.81] "...may
# contain up to six TOE Strength Points of anti-tank guns."
_AT_MIN, _AT_MAX = 3, 6
# [19.91] "Starting with the 75th Game-Turn (April 1, 1942)..."
_CW_AT_FROM_TURN = 75
# [19.92] "Only those infantry battalions possessing a CPA Rating of 10 (whether or not they were
# historically motorized; i.e., CPA Rating of 10+) and Offensive/Defense Close Assault Ratings of
# either 1/2 or 2/2 may be so augmented."
_CW_AT_RATINGS = ((1, 2), (2, 2))
# [19.94] "Each historically motorized infantry battalion (CPA of 10+) may contain 2 TOE Strength
# Points of anti-tank guns. Each historically non-motorized infantry battalion (CPA of 10) may
# contain one TOE Strength Point."
_CW_AT_WALKING, _CW_AT_MOTORIZED = 1, 2
# The label the ad hoc anti-tank TOE rides under on its host counter's step record (19.83/19.93:
# the points are "a second weapons system", not a new counter).
AT_STEP = "AT"


@lru_cache(maxsize=1)
def _formations() -> dict:
    with open(os.path.join(_DATA, "formation_organization.json")) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _attachments() -> dict:
    with open(os.path.join(_DATA, "maximum_attachment.json")) as f:
        return json.load(f)


def formation(org_type: str) -> dict:
    """The [19.3] Formation Organization Chart row governing a Parent Formation counter --
    its [9.12] parenthesized Stacking Point value, its organizational level and the [9.26]
    shell denominators. {} for a counter that is not a Parent Formation."""
    return _formations()["formations"].get(org_type, {})


def battle_group_rules(nation: str) -> dict:
    """[19.72]/[19.73] plus the Kampfgruppen HQ's and Italian Battle Groups sheets."""
    return _formations()["battle_groups"].get(nation, {})


def attachment_row(org_type: str, turn: int) -> dict:
    """The [19.5] Maximum Attachment Chart row in force for `org_type` on Game-Turn `turn`.

    Three Commonwealth rows change on a date -- the Armor Division and Tank Brigade at
    Game-Turn 68, the Matruh Garrison becoming Selby Force at 13 -- so the row is a function
    of the clock, not of the counter. {} when the chart names no row for this counter."""
    rows = _attachments()["rows"]
    for rid in _attachments()["org_type_rows"].get(org_type, ()):
        row = rows[rid]
        if turn >= row["gt_from"] and (row["gt_to"] == 0 or turn <= row["gt_to"]):
            return row
    return {}


# --- [9.2] what a counter is worth ------------------------------------------------------

def size(unit, attached=()) -> int:
    """[9.11]/[9.12]/[9.21] The Stacking Point value of this COUNTER as it currently stands.

    Three cases, all the book's:
      * a unit ATTACHED to a Parent is represented by the Parent's counter (19.12), so on its
        own account it is worth nothing -- 9.13's "a full division has a Stacking Point value
        of 5, while it may include units whose total Stacking Point values are much greater
        than five" is only true if the subsidiaries stop counting separately;
      * an HQ / Parent Formation counter is worth 0 "when it has no combat units of any type
        attached; the printed number is its Stacking Point value when it represents the
        division or brigade as a combat unit" (9.12, and the 9.25 Note repeats it);
      * everything else is worth what is printed on it (9.11).

    NO shell reduction here: [9.28]'s step-down is for "Unit Differentiation on Close Assault
    (see Case 15.5) and for any rule where unit size is important", not for the physical
    stacking limit, which 9.11/9.14 denominate in the printed value. See size_equivalent."""
    if unit.attached_to:
        return 0
    row = formation(unit.org_type) if unit.org_type else {}
    if row:
        return row["sp"] if any(u.attached_to == unit.id for u in attached) else 0
    return unit.stacking_points


def size_equivalent(unit, attached=(), max_toe: int | None = None) -> int:
    """[9.28] The counter's size for every rule where unit size matters -- above all the
    [15.53] Organization Size Close Assault Modifications chart. Identical to size(), except
    that a shell "is reduced one level to the next lowest-level formation"."""
    sp = size(unit, attached)
    return _SHELL_STEP[sp] if is_shell(unit, attached, max_toe) else sp


def is_shell(unit, attached=(), max_toe: int | None = None) -> bool:
    """[9.26] Is this counter a shell?

      * A DIVISION "is considered a shell when 50% or less of the total number of brigade-
        equivalents that may be assigned to it are attached to it" -- and by 9.27 a brigade
        that is itself a shell does not count toward that total.
      * A BRIGADE "if less than 2/3rds of the total number of battalions (combat units) that
        may be assigned to it are attached to it. Exception: a brigade to which a maximum of
        two battalions may be assigned is not considered a shell if two battalions are
        attached to it and at least one of them is not itself a shell."
      * A BATTALION "when less than 50% of its maximum TOE Strength Points are attached to it,
        unless it is an Artillery battalion...; an artillery unit must be less than 25% of TOE
        strength to be a shell."

    `max_toe` overrides the counter's own printed maximum. A counter with no printed maximum
    (max_toe 0 -- every hand-built test unit, and any OOB record that carries no charted TOE)
    cannot be tested against the battalion clause and is not a shell."""
    row = formation(unit.org_type) if unit.org_type else {}
    if row:
        kids = tuple(u for u in attached if u.attached_to == unit.id)
        if row["level"] == "division":
            cap = row["max_brigades"]
            if cap <= 0:
                return False
            # 9.22: "Players should be guided... not by the unit designation on the counter but
            # rather through the printed Stacking Point value" -- a brigade-equivalent is a
            # 2-or-3-point counter. 9.27: one that is itself a shell does not count.
            full = sum(1 for u in kids
                       if printed_size(u) >= 2 and not is_shell(u, attached))
            return full <= _DIVISION_SHELL_AT_OR_BELOW * cap
        cap = row["max_battalions"]
        if cap <= 0:
            return False
        bns = [u for u in kids if u.is_combat]
        if cap == 2 and len(bns) == 2:                      # the printed 9.26 exception
            return all(is_shell(u, attached) for u in bns)
        return len(bns) < _BRIGADE_SHELL_BELOW * cap
    ceiling = unit.max_toe if max_toe is None else max_toe
    if ceiling <= 0:
        return False
    fraction = _ARTILLERY_SHELL_BELOW if unit.barrage > 0 else _BATTALION_SHELL_BELOW
    # [19.98] "Anti-Tank TOE Strength Points do not affect any shell determinations of the infantry
    # unit" -- the 19.9 second weapon system is excluded from the primary-strength shell test.
    primary = unit.effective_strength - at_points(unit)
    return primary < fraction * ceiling


def printed_size(unit) -> int:
    """[9.11]/[9.12] The Stacking Point value PRINTED on the counter, ignoring what is currently
    attached to it: the plain number on an ordinary counter, the parenthesized one on an HQ."""
    row = formation(unit.org_type) if unit.org_type else {}
    return row["sp"] if row else unit.stacking_points


def stack_points(units) -> int:
    """[9.2] The Stacking Points a group of counters occupies, with attached subsidiaries
    folded into the counters that represent them. The rule-9.3 exclusions (first-line trucks
    9.29, garrisons 9.16a, pure flak 9.16b) stay in game.stacking, which calls this."""
    return sum(size(u, units) for u in units)


def combat_size(units) -> int:
    """[15.53] "Largest Unit On = Each Player's largest unit, in size-equivalents, actually
    taking part in the combat in the hex."

    A battalion attached to a Kampfgruppe is not a battalion in that fight -- it IS the
    Kampfgruppe (19.12: "functionally combined into one unit"), so each participant is
    resolved up its attachment chain to the topmost Parent present, and the answer is the
    largest size-equivalent among those. [19.46]'s transitivity falls out of the walk: a unit
    attached to a Parent which is in turn attached to a larger Parent is attached to the
    larger one too."""
    by_id = {u.id: u for u in units}
    tops = {}
    for u in units:
        top, seen = u, {u.id}
        while top.attached_to and top.attached_to in by_id and top.attached_to not in seen:
            seen.add(top.attached_to)
            top = by_id[top.attached_to]
        tops[top.id] = top
    return max((size_equivalent(t, units) for t in tops.values()), default=0)


# --- [19.4] / [19.5] attachment ---------------------------------------------------------

def _is_infantry(u) -> bool:
    """[19.5] Key: "Infantry = All Infantry-type units with the exception of Machinegun and
    Heavy Weapons units (whether or not they are motorized)." A gun unit (Vulnerability, 11.12)
    is artillery or anti-tank, a tank is a tank, and everything else that fights on foot or in
    a lorry with a close-assault punch is infantry. FLAGGED: the engine carries no Machinegun /
    Heavy Weapons discriminator on the counter (the OOB's `mg` role is not on Unit), so an MG
    battalion counts as infantry here -- narrower than the chart, in the restrictive direction."""
    return u.is_combat and not u.is_tank and not u.is_gun


def _is_company(u) -> bool:
    return u.stacking_points == 0 and u.is_combat


def may_attach(parent, attached, unit, turn: int, board=()) -> str:
    """[19.41]/[19.42]/[19.5] May `unit` attach to `parent`? '' if it may, else the reason.

    `attached` is what is already attached to the parent; `board` is every unit in play, which
    only the Kampfgruppen sheet's cross-formation Italian cap needs."""
    row = formation(parent.org_type) if parent.org_type else {}
    if not row:
        return "not a Parent Formation (19.0: divisions, brigades and battalions may be Parents)"
    if unit.id == parent.id:
        return "a counter may not attach to itself"
    if unit.attached_to:
        return "already attached to a Parent Formation -- never more than one at once (19.13)"
    if tuple(unit.hex) != tuple(parent.hex):
        return "must be in the same hex as its Parent Formation (19.13/19.41)"
    cap = attachment_row(parent.org_type, turn)
    if not cap:
        return "the [19.5] Maximum Attachment Chart names no row for this Parent Formation"

    if unit.assigned_to == parent.id:
        # 19.4: "Any units assigned to a particular Parent Formation may freely be attached to
        # or detached from that Parent Formation." The [19.5] maxima govern the ADDITIONAL
        # non-assigned units only, so an assigned unit coming home is bounded by [19.3] instead
        # -- and it already holds one of the Parent's TOE slots (19.28), so it costs nothing new.
        return ""

    guests = [u for u in attached if u.assigned_to != parent.id]
    bns = [u for u in guests if not _is_company(u)]
    coys = [u for u in guests if _is_company(u)]
    if _is_company(unit):
        # [19.5] Modifications: "Any nation's Division- and Brigade-equivalent units may attach
        # two non-Shell company-Equivalent units at no cost to the maximum attachments. Note that
        # three company-eq are equal to one Bn-eq unit."
        free = cap.get("free_companies", 0)
        over = max(0, len(coys) + 1 - free)
        if len(bns) + math.ceil(over / 3) > cap["units"]:
            return (f"over the [19.5] maximum of {cap['units']} attached units "
                    f"({cap['printed']}) -- three company-equivalents equal one battalion")
        return ""
    if len(bns) + 1 > cap["units"]:
        n = cap["units"]
        return (f"a {row['name']} may attach at most {_words(n)} units ([19.5]: {cap['printed']})")
    if unit.is_tank:
        limit = cap.get("max_tank", -1)
        if limit == 0:
            return f"no Tank unit may attach to this Parent Formation ([19.5]: {cap['printed']})"
        if 0 < limit <= sum(1 for u in bns if u.is_tank):
            return (f"at most {_words(limit)} tank battalion may attach "
                    f"([19.5]/[19.72]: {cap['printed']})")
    elif _is_infantry(unit):
        limit = cap.get("max_infantry", -1)
        if limit == 0:
            return f"no Infantry unit may attach to this Parent Formation ([19.5]: {cap['printed']})"
        if 0 < limit <= sum(1 for u in bns if _is_infantry(u)):
            return (f"at most {_words(limit)} infantry battalions may attach "
                    f"([19.5]/[19.72]: {cap['printed']})")

    return _battle_group_extras(parent, bns, unit, board)


def _battle_group_extras(parent, guests, unit, board) -> str:
    """The two Kampfgruppen HQ's sheet restrictions the [19.5] chart does not carry (PDF p.165,
    notes 3 and 4)."""
    if parent.org_type != "ge_battle_group":
        return ""
    rules = battle_group_rules("GE")
    arty = rules.get("max_artillery_units", 0)
    if arty and unit.barrage > 0 and sum(1 for u in guests if u.barrage > 0) >= arty:
        return ("the German Player may never attach more than two artillery-type units to a "
                "Kampfgruppe (Kampfgruppen HQ's sheet, note 3)")
    italians = rules.get("max_italian_units_total", 0)
    if italians and unit.nationality == "IT":
        in_play = sum(1 for u in board if u.nationality == "IT" and u.attached_to)
        if in_play >= italians:
            return ("no more than three Italian units may be attached to all of the German "
                    "Kampfgruppen in play at any time (Kampfgruppen HQ's sheet, note 4)")
    return ""


def may_detach(parent, unit, *, segment: str) -> str:
    """[19.43]/[19.44] May `unit` detach from `parent`? An ASSIGNED-and-attached unit may
    detach "at any time"; one attached but not assigned "only during the owning Player's
    Reorganization Segment or Movement Segment"."""
    if unit.attached_to != parent.id:
        return "not attached to that Parent Formation"
    if unit.assigned_to == parent.id:
        return ""
    if segment not in ("REORGANIZATION", "MOVEMENT"):
        return ("a unit attached but not assigned may be detached only in the Reorganization "
                "or Movement Segment (19.44)")
    return ""


def may_form_battle_group(board, nation: str) -> str:
    """[19.71]/[19.73] May this side form another Battle Group? Only the Italians are capped:
    "No more than two Italian Battle Groups may be in existence at one time." The Germans are
    explicitly uncapped -- "If the Axis Player wishes to form more Kampfgruppen than he has
    battlegroup counters, he may do so" (Kampfgruppen HQ's sheet, note a)."""
    rules = battle_group_rules(nation)
    if not rules:
        return f"no Battle Groups are provided for {nation} (19.7 is an AXIS rule)"
    cap = rules.get("max_in_play", 0)
    if cap and sum(1 for u in board if u.org_type == rules["org_type"] and u.alive) >= cap:
        return (f"no more than {_words(cap)} {nation} Battle Groups may be in existence at "
                f"one time (19.73)")
    return ""


# --- [19.2] assignment -------------------------------------------------------------------

def may_assign(parent, assigned, unit) -> str:
    """[19.21]/[19.28] May `unit` be assigned to `parent`? "In order to be assigned to a Parent
    Formation, an independent unit must be currently attached to it" (19.21), and "only
    independent units may be assigned... no unit assigned to one Parent Formation may be
    assigned to another" (19.28), up to the [19.3] chart's maximum.

    NOT MODELLED, and flagged rather than guessed: 19.24's optional historical assignment
    shifts, 19.25's three Commonwealth cap changes and 19.27's asterisk units all live in the
    [4.45] OA Chart notes, which are not transcribed (port plan T1-2). 19.26's Commonwealth
    battalion shuffle is the one exception to 19.28 and is granted below."""
    row = formation(parent.org_type) if parent.org_type else {}
    if not row:
        return "not a Parent Formation (19.0)"
    if unit.assigned_to and not _cw_shuffle(unit, parent):
        return "already assigned to a Parent Formation (19.28)"
    if unit.attached_to != parent.id:
        return "must already be attached to the Parent Formation to be assigned to it (19.21)"
    cap = row["max_brigades"] + row["max_battalions"]
    if cap and len(tuple(assigned)) >= cap:
        return (f"a {row['name']} may have at most {_words(cap)} units assigned "
                f"([19.3]: {row['composition']})")
    return ""


def _cw_shuffle(unit, parent) -> bool:
    """[19.26] "the Commonwealth Player is permitted to pull assigned battalions from a Brigade
    and replace them with others from another Brigade (or from the unassigned group)... Battalions
    may only be reassigned or shuffled; they may not simply be 'unassigned' and made independent."
    The one licence to re-assign an already-assigned unit."""
    return (unit.nationality == "CW" and unit.stacking_points <= 1
            and formation(parent.org_type).get("level") == "brigade")


# --- [19.6] rebuilding depleted units ----------------------------------------------------

def rebuild_headroom(unit, max_toe: int | None = None) -> int:
    """[19.61] "No unit may ever be increased above its stated maximum TOE Strength Level."
    The number of Replacement TOE Strength Points this counter can still absorb."""
    ceiling = unit.max_toe if max_toe is None else max_toe
    return max(0, ceiling - unit.strength)


def may_rebuild(unit, max_toe: int | None = None, points: int = 0) -> str:
    """[19.61]/[19.62]/[19.68] May this counter absorb `points` Replacement TOE Strength Points
    in this Organization Phase? The other half of the rule -- where the points come from and
    which type rebuilds which unit (19.64/19.65) -- is rule 20's Replacement Points, which this
    engine does not yet have; this is the ABSORPTION side that they plug into."""
    if points <= 0:
        return "no Replacement Points offered"
    if not unit.alive:
        return ("a unit completely eliminated by attrition or combat may not be rebuilt (19.62); "
                "only an HQ cadre survives to have new battalions assigned")
    ceiling = unit.max_toe if max_toe is None else max_toe
    if ceiling <= 0:
        return "no printed maximum TOE Strength for this counter ([4.44] ID Code, not transcribed)"
    if points > rebuild_headroom(unit, ceiling):
        return f"would exceed the printed maximum TOE Strength of {ceiling} (19.61)"
    return ""


def rebuild_cp(points: int) -> int:
    """[19.68] "For every two Replacement TOE Strength Points added to a unit, that unit (and
    its parent, if such is the situation) uses one Capability Point." A part-pair still costs
    its Point -- the chart's row is priced per two points begun, not per point."""
    from . import cp_costs
    return math.ceil(points / 2) * cp_costs.absorb_cost()


def absorb(unit, points: int) -> Unit:
    """[19.61]/[20.4] Fold `points` Replacement TOE Strength Points into a counter's PRIMARY
    weapon system -- steps[0], the role the OOB built it from. A unit may carry a second weapon
    system (19.93's ad hoc anti-tank rides its own AT step, appended after), and a rebuild tops
    up the primary rather than the bolt-on."""
    steps = (replace(unit.steps[0], strength=unit.steps[0].strength + points),) + unit.steps[1:]
    return replace(unit, steps=steps)


# --- [19.8] ad hoc Axis anti-tank batteries ----------------------------------------------

def at_points(unit) -> int:
    """The anti-tank TOE Strength Points carried on a counter by 19.8 / 19.9 augmentation."""
    return sum(s.strength for s in unit.steps if s.label == AT_STEP)


def may_augment_at(hq, points: int, at_units=()) -> str:
    """[19.81]-[19.86] May this Axis Brigade-Level HQ take on `points` of ad hoc anti-tank?

    `at_units` is every anti-tank unit on the map as (unit, printed maximum TOE) pairs -- 19.82
    bars the whole programme while any one of them is below 67% of its maximum.

    FLAGGED PROXIES, both in the restrictive direction: 19.81 says "bearing an infantry-type
    symbol", and the engine carries no branch symbol on a counter, so any Axis brigade-level
    Parent Formation qualifies; and 19.86's single-gun-type rule is unmodellable while the
    engine has no gun MODELS (all AT TOE is one pool), so re-augmenting an HQ that already
    holds points is allowed up to the 19.81 ceiling and the type restriction is not policed."""
    row = formation(hq.org_type) if hq.org_type else {}
    if not row or row.get("level") != "brigade":
        return "only a Brigade-Level HQ (including a Kampfgruppe) may be augmented (19.81)"
    if row.get("nation") not in ("GE", "IT"):
        return "19.8 is an AXIS rule"
    held = at_points(hq)
    if not held and points < _AT_MIN:
        return f"the initial assignment must be at least {_AT_MIN} TOE Strength Points (19.83)"
    if held + points > _AT_MAX:
        return (f"a Brigade-Level HQ may contain up to {_AT_MAX} TOE Strength Points of "
                f"anti-tank guns (19.81)")
    for unit, ceiling in at_units:
        if ceiling > 0 and unit.effective_strength < _AT_AUGMENT_FLOOR * ceiling:
            return (f"{unit.id} is below 67% of its maximum TOE Strength -- no anti-tank "
                    f"augmentation while any anti-tank unit on the map is (19.82)")
    return ""


def augment_at(hq, points: int, at_cpa: int | None = None) -> Unit:
    """[19.83]/[19.85]/[19.87] Fold anti-tank TOE Strength Points onto an HQ counter. The points
    ride as their own step record (19.93 calls them "a second weapons system"); [19.85] gives
    the HQ "a CPA equal to that of those Anti-Tank Points"; and [19.87] leaves its Stacking
    Point value at zero "regardless of the number of AT points it currently contains" -- which
    falls out of 9.12 without a special case, since an HQ is worth zero until units attach."""
    for i, s in enumerate(hq.steps):
        if s.label == AT_STEP:
            steps = hq.steps[:i] + (replace(s, strength=s.strength + points),) + hq.steps[i + 1:]
            break
    else:
        steps = hq.steps + (StepRecord(AT_STEP, points),)
    out = replace(hq, steps=steps)
    return out if at_cpa is None else replace(out, cpa=at_cpa)


# --- [19.9] augmenting Commonwealth battalions with anti-tank -----------------------------

def cw_at_allowance(unit, turn: int) -> int:
    """[19.91]-[19.94] How many anti-tank TOE Strength Points this Commonwealth infantry
    battalion may contain: two if it is motorized (CPA above 10), one if it walks (CPA exactly
    10), none before Game-Turn 75 or if its Close Assault Ratings are not 1/2 or 2/2.

    [19.96] -- barred while any anti-tank regiment assigned to the battalion's parent is below
    maximum TOE -- is NOT YET ENFORCED (FLAGGED): it needs the [4.44]/[4.45] OA parent tree that
    names which anti-tank regiments are assigned to that battalion's parent, which is not
    transcribed (port plan T1-2), so no caller can yet see them. [19.97] (the points take the
    infantry unit's own CPA) and [19.98] (they do not affect shell determination) both fall out of
    carrying the points on the infantry counter itself."""
    if turn < _CW_AT_FROM_TURN or unit.nationality != "CW" or not unit.is_combat:
        return 0
    if unit.cpa < 10 or unit.is_tank or unit.is_gun:
        return 0
    if (unit.oca, unit.dca) not in _CW_AT_RATINGS:
        return 0
    return _CW_AT_WALKING if unit.cpa == 10 else _CW_AT_MOTORIZED


_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def _words(n: int) -> str:
    return _WORDS.get(n, str(n))
