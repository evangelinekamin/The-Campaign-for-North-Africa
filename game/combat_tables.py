"""The Close Assault Combat Results Table (rule 15.79) and Close-Assault terrain
column shifts (rule 8.37 / 15.3).

The loss-% rows are transcribed from the CRT and guarded by a partition test
(test_combat: every legal d6d6 roll maps to exactly one loss row per column) plus
the rulebook's worked example (§15.64). The Retreat / Engaged / Captured sub-rows
are now transcribed too — from the authoritative chart image (15.79 in the VASSAL
mod, read directly), which recovered what the OCR had lost.

DICE, read TWO ways from the same 2d6 per side (rule 15.79):
  * SEQUENTIALLY (large die first: a 2 and a 5 -> 25, range 11..66) for the LOSS %.
  * as an ARITHMETIC SUM (2 + 5 = 7, range 2..12) for the CAPT / ENG / RETREAT rows.
Columns are the Final Assault Differential; a column SHIFT (terrain/size/morale)
moves the differential left (toward the defender) or right (toward the attacker).
"""
from __future__ import annotations

import math

from .terrain import Hexside, Terrain

# Column order (index 0..17) = the differential headers of the CRT.
_COLUMNS = ("-11", "-8..-10", "-6..-7", "-4..-5", "-3", "-2", "-1", "0",
            "+1", "+2", "+3", "+4", "+5..+6", "+7..+8", "+9..+10",
            "+11..+13", "+14..+16", "+17")
N_COLS = len(_COLUMNS)
# [15.77] The +11..+17 columns (table indices 15, 16, 17) are the OVERRUN section of the CRT, where
# "all Defender losses are rounded up" (15.83c: "in an overrun, 1.1 Defender Points would equal 2").
OVERRUN_COL = 15


def diff_to_column(diff: int) -> int:
    if diff <= -11:
        return 0
    if diff <= -8:
        return 1
    if diff <= -6:
        return 2
    if diff <= -4:
        return 3
    if diff <= 3:               # -3,-2,-1,0,+1,+2,+3 are their own columns
        return 7 + diff
    if diff == 4:
        return 11
    if diff <= 6:
        return 12
    if diff <= 8:
        return 13
    if diff <= 10:
        return 14
    if diff <= 13:
        return 15
    if diff <= 16:
        return 16
    return 17


# Each grid: rows of (loss_pct, [18 cell strings]); a cell is a sequential-dice
# range "lo-hi" (or "" for no result). Copied cell-for-cell from the CRT.
_ATTACKER: list[tuple[int, list[str]]] = [
    (50, ["11-15", "11-12", "11", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]),
    (40, ["16-24", "13-16", "12-14", "11", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]),
    (30, ["25-33", "21-26", "15-23", "12-15", "11-12", "", "", "", "", "", "", "", "", "", "", "", "", ""]),
    (25, ["34-36", "31-34", "24-32", "16-23", "13-16", "11-12", "11", "11", "11", "11", "", "", "", "", "", "", "", ""]),
    (20, ["41-46", "35-43", "33-41", "24-33", "21-26", "13-18", "12-13", "12", "12", "12", "11-12", "11-12", "11", "", "", "", "", ""]),
    (15, ["51-56", "44-53", "42-51", "34-44", "31-36", "21-33", "14-26", "13-24", "13-22", "13-16", "13-16", "13-15", "12-13", "11-12", "11", "", "", ""]),
    (10, ["61-63", "54-62", "52-56", "45-53", "41-46", "34-44", "31-42", "25-36", "23-33", "21-31", "21-26", "16-25", "14-21", "13-21", "12-16", "11-16", "11-13", "11-12"]),
    (5,  ["64-66", "63-65", "61-63", "54-61", "51-56", "45-54", "43-52", "41-51", "34-46", "32-44", "31-42", "26-41", "22-35", "22-33", "21-31", "21-26", "14-21", "13-16"]),
    (0,  ["", "66", "64-66", "62-66", "61-66", "55-66", "53-66", "52-66", "51-66", "45-66", "43-66", "42-66", "36-66", "34-66", "32-66", "31-66", "22-66", "21-66"]),
]

_DEFENDER: list[tuple[int, list[str]]] = [
    (50, ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "11-13", "11-16"]),
    (40, ["", "", "", "", "", "", "", "", "", "", "", "", "", "11", "11-12", "11-13", "14-25", "21-26"]),
    (30, ["", "", "", "", "", "", "", "", "", "", "", "", "11", "12-14", "13-16", "14-22", "26-33", "31-36"]),
    (25, ["", "", "", "", "", "", "", "", "", "11", "11", "11-12", "12-14", "15-22", "21-26", "23-33", "34-43", "41-46"]),
    (20, ["", "", "", "", "", "11", "11", "11-12", "11-13", "12-13", "12-14", "13-16", "15-23", "23-31", "31-41", "34-46", "44-55", "51-56"]),
    (15, ["", "", "", "11", "11-13", "12-13", "12-16", "13-23", "14-22", "14-23", "15-25", "21-33", "24-36", "32-45", "42-56", "51-62", "56-63", "61-63"]),
    # col +4 (index 11): OCR "24-45" overlaps the 15% row (21-33); the worked
    # example fixes 21->15%, and neighbours put this row at 34-45 -> OCR 3->2.
    (10, ["11", "11", "11-13", "12-15", "14-21", "14-23", "21-26", "24-32", "23-33", "24-33", "26-42", "34-45", "41-54", "46-61", "61-63", "63-64", "64", "64-65"]),
    # col +2 (index 9): OCR read "41-52" but that leaves rolls 34-36 uncovered;
    # every neighbouring column's 5% row starts at 34 and loss% is monotonic in
    # the roll, so it is "34-52". Flagged for scan confirmation (caught by the
    # partition test).
    (5,  ["12-16", "12-23", "14-26", "16-31", "22-41", "24-44", "31-46", "33-51", "34-51", "34-52", "43-54", "46-56", "55-62", "62-64", "64-65", "65", "65-66", "66"]),
    (0,  ["21-66", "24-66", "31-66", "32-66", "42-66", "45-66", "51-66", "52-66", "52-66", "53-66", "55-66", "61-66", "63-66", "65-66", "66", "66", "", ""]),
]


def _valid(v: int) -> bool:
    return 1 <= v // 10 <= 6 and 1 <= v % 10 <= 6


def expand(cell: str) -> set[int]:
    """Sequential-dice values covered by a cell like '26-41' (only legal d6d6)."""
    if not cell:
        return set()
    if "-" in cell:
        lo, hi = (int(x) for x in cell.split("-"))
    else:
        lo = hi = int(cell)
    return {v for v in range(lo, hi + 1) if _valid(v)}


def _lookup(grid: list[tuple[int, list[str]]], col: int, roll: int) -> int:
    for pct, cells in grid:
        if roll in expand(cells[col]):
            return pct
    return 0


def attacker_loss_pct(col: int, roll: int) -> int:
    return _lookup(_ATTACKER, col, roll)


def defender_loss_pct(col: int, roll: int) -> int:
    return _lookup(_DEFENDER, col, roll)


# --- CRT special results (rule 15.79): read the SAME 2 dice as an ARITHMETIC SUM
# (2..12). Capt + Retreat are DEFENDER results; Capt + Eng are ATTACKER results
# (the attacker is never forced to retreat). Transcribed cell-for-cell from the
# 15.79 chart image and cross-checked vs the §15.73b worked example (+3 column:
# defender 1-hex retreat on 4-7, attacker Eng on 8-10/12). Least-certain cells:
# the 3-hex-retreat overrun row and a couple of overrun 1-hex cells.
_ATK_CAPT = ["2-7", "2-6", "2-5", "2-4", "2-3", "2", "", "", "", "", "", "", "", "", "", "", "", ""]
_ATK_ENG = ["10-12", "10-11", "11-12", "12", "11-12", "10-11", "10-12", "9-10,12",
            "9-11", "9-12", "8-10,12", "8-10", "9-10,12", "10-12", "9-11", "", "", ""]
_DEF_CAPT = ["", "", "", "", "", "", "", "2", "2", "2", "2-3", "2-3", "2-4", "2-4",
             "2-5", "2-6", "2-7", "2-8"]
_DEF_RET1 = ["", "", "", "", "10", "9", "8", "5-6", "4-6", "5-7", "4-7", "3-7", "7-9",
             "7-9,12", "4-7,12", "3-4,6-9", "2,5-7,9,11", "2-9,11"]
_DEF_RET2 = ["", "", "", "", "", "", "", "", "", "", "11", "11", "5", "5", "8", "12", "8,10", "10"]
_DEF_RET3 = ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "11", "12", "12"]


def _sum_in(cell: str, s: int) -> bool:
    """Is arithmetic dice-sum s in a cell like '2-4', '7-9,12' or '2,5-7,9,11'?"""
    if not cell:
        return False
    for part in cell.split(","):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            if lo <= s <= hi:
                return True
        elif int(part) == s:
            return True
    return False


def attacker_result(col: int, dice_sum: int) -> tuple[bool, bool]:
    """(captured, engaged) from the attacker's dice SUM (rule 15.79). Independent
    results (though the chart's ranges make them mutually exclusive per sum)."""
    return (_sum_in(_ATK_CAPT[col], dice_sum), _sum_in(_ATK_ENG[col], dice_sum))


def defender_result(col: int, dice_sum: int) -> tuple[bool, int]:
    """(captured, retreat_hexes) from the defender's dice SUM. Both can occur from
    one sum — some already-counted losses become prisoners AND the unit retreats
    (rule 15.73; the §15.2xx example rolls sum 3 at +4 = captured + retreat 1)."""
    capt = _sum_in(_DEF_CAPT[col], dice_sum)
    retreat = 0
    for hexes, row in ((3, _DEF_RET3), (2, _DEF_RET2), (1, _DEF_RET1)):
        if _sum_in(row[col], dice_sum):
            retreat = hexes
            break
    return (capt, retreat)


# [17.4] MORALE MODIFIER TABLE: row = Cohesion/Disorganization level, columns =
# the modifier applied to Basic Morale for one combat. Cells are sequential-dice
# ranges (11-66). Transcribed from the 17.4 chart image; every row partitions the
# 36 legal rolls (guarded by test_combat) and the rulebook's four in-text rolls
# validate (43@-4 -> -2, 63@+2 -> NO, 21@-2 -> NO, 53@-3 -> -2). The one cell the
# image left ambiguous, -4's "-2" column, is 42-56 (partition-forced: else roll 56
# maps nowhere).
_MORALE_MODS = (4, 3, 2, 1, 0, -1, -2, -3, -4, "SURR")
_MORALE_TABLE: dict[int, list[str]] = {
    8:   ["11-26", "31-46", "51-65", "66", "", "", "", "", "", ""],
    7:   ["11-16", "21-36", "41-56", "61-66", "", "", "", "", "", ""],
    6:   ["11-12", "13-25", "26-36", "41-66", "", "", "", "", "", ""],
    5:   ["11", "12-21", "22-33", "34-65", "66", "", "", "", "", ""],
    4:   ["", "11-14", "15-31", "32-56", "61-66", "", "", "", "", ""],
    3:   ["", "11-13", "14-21", "22-44", "45-66", "", "", "", "", ""],
    2:   ["", "", "11-12", "13-36", "41-66", "", "", "", "", ""],
    1:   ["", "", "", "11-26", "31-66", "", "", "", "", ""],
    0:   ["", "", "", "11", "12-65", "66", "", "", "", ""],
    -1:  ["", "", "", "", "11-54", "55-65", "66", "", "", ""],
    -2:  ["", "", "", "", "11-46", "51-56", "61-66", "", "", ""],
    -3:  ["", "", "", "", "11-42", "43-46", "51-66", "", "", ""],
    -4:  ["", "", "", "", "11-33", "34-41", "42-56", "61-66", "", ""],
    -5:  ["", "", "", "", "11-23", "24-32", "33-46", "51-66", "", ""],
    -6:  ["", "", "", "", "11-12", "13-25", "26-36", "41-63", "64-66", ""],
    -7:  ["", "", "", "", "11", "12-16", "21-33", "34-51", "52-63", "64-66"],
    -8:  ["", "", "", "", "", "11-13", "14-31", "32-44", "45-61", "62-66"],
    -9:  ["", "", "", "", "", "11", "12-26", "31-41", "42-55", "56-66"],
    -10: ["", "", "", "", "", "", "11-21", "22-34", "35-53", "54-66"],
    -11: ["", "", "", "", "", "", "11-14", "15-33", "34-46", "51-66"],
    -12: ["", "", "", "", "", "", "11", "12-26", "31-44", "45-66"],
    -13: ["", "", "", "", "", "", "11", "12-21", "22-36", "41-66"],
    -14: ["", "", "", "", "", "", "", "11-16", "21-33", "34-66"],
    -15: ["", "", "", "", "", "", "", "11", "12-26", "31-66"],
    -16: ["", "", "", "", "", "", "", "", "11-21", "22-66"],
    -17: ["", "", "", "", "", "", "", "", "", "11-66"],
}

# Every row must carry exactly one cell per modifier column: morale_modifier zips the
# row against _MORALE_MODS, and zip() silently truncates a SHORT row -- a mis-transcribed
# row would drop the surrender column unseen (the 54.17-misprint failure mode). Assert the
# lengths at load so a bad transcription fails on import, not silently in play.
assert all(len(cells) == len(_MORALE_MODS) for cells in _MORALE_TABLE.values()), \
    "17.4 morale table: every row must have exactly len(_MORALE_MODS) cells"


def morale_modifier(cohesion: int, roll: int) -> "int | str":
    """Rule 17.4: the modifier applied to Basic Morale for one combat, from the
    unit's Cohesion level and a sequential 2d6 roll. Returns an int, or 'SURR'
    (surrender). Cohesion is clamped to the table's [-17, +8]."""
    coh = max(-17, min(8, cohesion))
    for mod, cell in zip(_MORALE_MODS, _MORALE_TABLE[coh]):
        if roll in expand(cell):
            return mod
    # Every row partitions the 36 legal 2d6 rolls (guarded by test_combat), so a
    # fall-through is an illegal roll or a misprinted table -- fail loud, never return
    # a plausible-wrong 0.
    raise ValueError(
        f"morale_modifier: roll {roll} matched no cell of cohesion row {coh}; "
        f"the 17.4 rows partition the 36 legal 2d6 rolls (11..66)")


# [14.6] ANTI-ARMOR FIRE CRT: rows = the 36 d66 outcomes paired (11,12 / 13,14 /
# ... / 65,66) -> 18 rows; columns = Actual Anti-Armor Points fired (0* then 1..16+,
# capped). Cell = Damage Points (Armor Protection Points the target must lose).
# Transcribed from the chart; verified against the worked example (5 pts, roll 35
# -> 7). The 0* column is usable only when the firer has 1-4 RAW points (Actual 0).
_ANTI_ARMOR: tuple[tuple[int, ...], ...] = (
    (0, 0, 0, 1, 2, 3, 4, 6, 8, 10, 11, 12, 14, 16, 18, 20, 22),   # 11,12
    (0, 0, 0, 1, 3, 4, 5, 6, 8, 10, 11, 13, 15, 17, 19, 20, 22),   # 13,14
    (0, 0, 1, 1, 3, 4, 5, 7, 9, 10, 12, 13, 15, 17, 19, 21, 23),   # 15,16
    (0, 0, 1, 2, 4, 5, 6, 8, 9, 11, 12, 14, 16, 18, 20, 21, 23),   # 21,22
    (0, 0, 1, 2, 4, 5, 6, 8, 10, 11, 13, 14, 16, 18, 20, 22, 24),  # 23,24
    (0, 0, 2, 3, 4, 6, 7, 9, 10, 12, 13, 15, 17, 19, 20, 22, 24),  # 25,26
    (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 19, 21, 23, 25),  # 31,32
    (0, 1, 2, 3, 5, 7, 8, 10, 11, 13, 14, 16, 18, 20, 21, 23, 25),  # 33,34
    (0, 1, 3, 4, 5, 7, 9, 10, 12, 13, 15, 16, 18, 20, 22, 24, 26),  # 35,36
    (0, 2, 3, 4, 6, 7, 9, 11, 12, 14, 15, 17, 19, 21, 22, 24, 26),  # 41,42
    (0, 2, 3, 5, 6, 8, 10, 11, 13, 14, 16, 17, 19, 21, 23, 25, 27),  # 43,44
    (0, 2, 4, 5, 7, 8, 10, 12, 13, 15, 16, 18, 20, 22, 23, 25, 27),  # 45,46
    (1, 3, 4, 6, 7, 9, 11, 12, 14, 15, 17, 19, 20, 22, 24, 26, 28),  # 51,52
    (1, 3, 4, 6, 8, 9, 11, 13, 14, 16, 17, 20, 21, 23, 25, 27, 29),  # 53,54
    (1, 3, 5, 7, 8, 10, 12, 13, 15, 16, 19, 21, 22, 24, 26, 28, 30),  # 55,56
    (1, 4, 5, 7, 8, 10, 12, 14, 15, 17, 19, 22, 23, 25, 27, 29, 31),  # 61,62
    (1, 4, 6, 8, 9, 11, 13, 14, 16, 18, 21, 22, 24, 26, 28, 29, 32),  # 63,64
    (2, 4, 6, 8, 9, 11, 13, 15, 17, 19, 21, 23, 24, 26, 28, 30, 32),  # 65,66
)


# [12.6] BARRAGE AGAINST LAND UNITS CRT. Columns = Actual Barrage Points banded
# (1-2, 3-4, ... 17+); roll is a sequential d66 (11-66). Result by the target's
# class: No effect / Pinned / lose 1 / lose 2. For Infantry + Armor a numeric loss
# ALSO Pins; Guns and Trucks are never Pinned (12.44). The No-effect band is the
# complement, so only the Pin / 1 / 2 roll-ranges are stored. The Truck row is the
# 12.46 secondary roll -- every barrage rolls a second, independent d66 for any Trucks
# in the target hex. Its "deferral" cited rule 32.56, an ABSTRACT-game rule about
# Motorization Points; in the full Logistics Game barrage DOES kill real Truck Points
# (54.2). Truck row transcribed from PDF p.097 (12.46 transcription, adversarially
# re-verified cell-by-cell) and bound by test_lorry_mortal.
_BARRAGE: dict[str, dict[str, list[str]]] = {
    "infantry": {
        "pin": ["54-66", "45-66", "42-65", "35-64", "25-61", "21-44", "11-35", "11-32", "11-31"],
        "1":   ["", "", "66", "65-66", "62-66", "45-66", "36-64", "33-56", "32-55"],
        "2":   ["", "", "", "", "", "", "65-66", "61-66", "56-66"],
    },
    "armor": {
        "pin": ["63-66", "55-66", "46-66", "41-66", "32-66", "23-66", "15-63", "11-62", "11-54"],
        "1":   ["", "", "", "", "", "", "64-66", "63-66", "55-66"],
    },
    "gun": {   # never Pinned
        "1": ["62-66", "55-66", "51-66", "41-66", "31-66", "23-64", "13-56", "11-54", "11-36"],
        "2": ["", "", "", "", "", "65-66", "61-66", "55-66", "41-66"],
    },
    "truck": {   # 12.46 secondary roll; never Pinned; result = Truck Points destroyed
        "1": ["", "65-66", "63-66", "61-66", "56-63", "54-63", "51-61", "43-61", "33-61"],
        "2": ["", "", "", "", "64-66", "64-66", "62-66", "62-66", "62-66"],
    },
}


def barrage_result(target_class: str, actual_points: int, roll: int,
                   *, column_shift: int = 0) -> tuple[bool, int]:
    """Rule 12.6: (pinned, steps_lost) for a barrage of `actual_points` Actual
    Barrage Points against a target of the given class ('infantry'/'armor'/'gun'/
    'truck'), on a sequential d66 roll. Numeric losses also Pin infantry and armor
    (12.6). For a 'truck' target the loss count is Truck Points (12.46); guns and
    trucks are never Pinned (12.44). `column_shift` (<= 0) moves the Barrage-Points
    band left for a target in protective terrain or a fortification (12.33); shifted
    off the low end of the table the barrage has no effect (rule 12.34)."""
    col = min(8, (actual_points - 1) // 2) + column_shift
    if col < 0:
        return (False, 0)
    block = _BARRAGE[target_class]
    for loss in ("2", "1"):
        if loss in block and roll in expand(block[loss][col]):
            return (target_class not in ("gun", "truck"), int(loss))   # guns/trucks not pinned
    if "pin" in block and roll in expand(block["pin"][col]):
        return (True, 0)
    return (False, 0)


def anti_armor_damage(actual_points: int, roll: int, *, phasing: bool = False,
                      terrain_shift: int = 0) -> int:
    """Rule 14.6: Armor-Protection Points the target must lose, from Actual Anti-
    Armor Points and a d66 roll (10*dieA + dieB). The Phasing firer decreases his
    dice roll one row (14.6 CRT Modifiers: "Phasing Player decreases his dice roll
    by one row (an 11 or 12 is unaffected)"). `terrain_shift` (<= 0) shifts the
    Actual Anti-Armor Points column LEFT when the target sits in protective terrain
    or a fortification (rule 14.32/14.33); a shift below the '0' column is treated as
    zero Anti-Armor Points (rule 14.35)."""
    row = (roll // 10 - 1) * 3 + (roll % 10 - 1) // 2
    if phasing:
        row = max(0, row - 1)
    return _ANTI_ARMOR[row][max(0, min(16, actual_points + terrain_shift))]


# [15.53] Organization-Size Close Assault Modifications: the column shift in favour
# of the side whose largest participating unit is bigger, keyed by (larger SP,
# smaller SP). Stacking points: 5=Division, 3=Super-Brigade, 2=Brigade/Battle Group,
# 1=Battalion, 0=Company (rule 9.4). Division-level aggregation of a formation's
# battalions (15.55, via the parent HQ) is deferred, so this fires only when the
# participating units' own sizes differ (e.g. a battalion assaulting a company).
_ORG_SIZE_SHIFT: dict[tuple[int, int], int] = {
    (5, 3): 1, (5, 2): 2, (5, 1): 4, (5, 0): 8,
    (3, 2): 0, (3, 1): 2, (3, 0): 4, (2, 1): 2, (2, 0): 4, (1, 0): 2,
}


def org_size_shift(attacker_sp: int, defender_sp: int) -> int:
    """Column shift from organizational size (rule 15.53): + toward the attacker if
    its largest unit is bigger, - toward the defender if the defender's is bigger."""
    if attacker_sp == defender_sp:
        return 0
    shift = _ORG_SIZE_SHIFT.get((max(attacker_sp, defender_sp), min(attacker_sp, defender_sp)), 0)
    return shift if attacker_sp > defender_sp else -shift


# Static fortification defense (rule 15.82): the Close Assault column shift toward the
# defender by fortification level. Chart 8.37 grades the close-assault fortification
# benefit L2 / L3 / L4 for Levels 1 / 2 / 3 (RE-READ off PDF page 70) -- NOT level*(-2),
# which over-shifts Level 2 by one column and Level 3 by two (T0-8). Dynamic fort-
# reduction by successive assault (rule 25.14) is DEFERRED.
FORT_CA_SHIFT_BY_LEVEL: dict[int, int] = {1: -2, 2: -3, 3: -4}

# Defensive minefield belt: a flat column shift toward the defender when the
# assault crosses into a mined hex. Rule 26.26 ("the defending Player adjusts all
# columns ONE in his favor") and 8.37 (minefield close-assault = L1) both fix this
# at a single column. The clearing / reveal minigame (rule 26.1) is DEFERRED --
# this models only the belt's static one-column drag on the assault.
MINEFIELD_CA_SHIFT: int = -1


# Close-Assault column shifts from the Terrain Effects Chart (8.37): negative =
# columns left (favours defender), positive = right (favours attacker).
HEX_CA_SHIFT: dict[Terrain, int] = {
    Terrain.CLEAR: 0, Terrain.GRAVEL: 0, Terrain.DELTA: 0, Terrain.DESERT: 0,
    Terrain.SALT_MARSH: +1,        # R1
    Terrain.HEAVY_VEG: -1,         # L1
    Terrain.ROUGH: -2,             # L2
    Terrain.MOUNTAIN: -3,          # L3
    Terrain.MAJOR_CITY: 0,         # chart shows a fortification ref; deferred
}

HEXSIDE_CA_SHIFT: dict[Hexside, int] = {
    Hexside.RIDGE: -2, Hexside.UP_SLOPE: -2, Hexside.DOWN_SLOPE: +1,
    Hexside.UP_ESCARPMENT: -3, Hexside.DOWN_ESCARPMENT: +1,
    Hexside.WADI: -1, Hexside.MAJOR_RIVER: -6, Hexside.MINOR_RIVER: -2,
}


# Anti-Armor Fire terrain column shifts from the Terrain Effects Chart (8.37) and
# the 14.6 CRT Modifiers: negative = the Actual Anti-Armor Points column moves LEFT
# (fewer points -> the defending armor is harder to kill, rule 14.32). Fortification
# and hexside additions are handled by anti_armor_terrain_shift.
HEX_AA_SHIFT: dict[Terrain, int] = {
    Terrain.CLEAR: 0, Terrain.GRAVEL: 0, Terrain.SALT_MARSH: 0,
    Terrain.DELTA: 0, Terrain.DESERT: 0,
    Terrain.HEAVY_VEG: -1,         # L1
    Terrain.ROUGH: -1,             # L1
    Terrain.MOUNTAIN: -2,          # L2
    Terrain.MAJOR_CITY: 0,         # fortification benefit applied separately (8.37 note 12)
}

# Anti-Armor fortification column shifts (8.37): Level 1 = L1, Levels 2/3 = L2.
# By 8.37 note 12 armour targets get this ONLY in a Major City hex -- and every
# anti-armor target IS armour -- so anti_armor_terrain_shift gates it on MAJOR_CITY.
FORT_AA_SHIFT: dict[int, int] = {1: -1, 2: -2, 3: -2}


def anti_armor_terrain_shift(terrain: Terrain, fort_level: int) -> int:
    """Rule 14.32/14.33: the Actual-Anti-Armor-Points column shift (<= 0, columns
    left) protecting armour in a target hex. The defender takes the BEST of the hex
    terrain OR the fortification -- they are NOT cumulative (14.33). The fortification
    anti-armor benefit reaches armour targets only in a Major City hex (8.37 note 12).
    Hexside additions (14.33) are deferred: the anti-armor step combines firers from
    several hexes, so no single 'all attackers through this hexside' feature exists."""
    terrain_shift = HEX_AA_SHIFT.get(terrain, 0)
    fort_shift = FORT_AA_SHIFT.get(fort_level, -2) if terrain == Terrain.MAJOR_CITY and fort_level > 0 else 0
    return min(terrain_shift, fort_shift)


# Barrage terrain column-band shifts from the Terrain Effects Chart (8.37): negative
# = the Barrage-Points band moves LEFT, benefitting the defender (rule 12.33). Only
# Rough (L1) and Mountain (L2) shift barrage; every other terrain is "-" on the chart.
HEX_BARRAGE_SHIFT: dict[Terrain, int] = {
    Terrain.CLEAR: 0, Terrain.GRAVEL: 0, Terrain.SALT_MARSH: 0, Terrain.HEAVY_VEG: 0,
    Terrain.DELTA: 0, Terrain.DESERT: 0, Terrain.MAJOR_CITY: 0,
    Terrain.ROUGH: -1,             # L1
    Terrain.MOUNTAIN: -2,          # L2
}

# Barrage fortification column-band shifts (8.37): Level 1 = L1, Levels 2/3 = L2
# (matching the 12.33 worked example: Level Two Fortification = two bands left).
FORT_BARRAGE_SHIFT: dict[int, int] = {1: -1, 2: -2, 3: -2}


# [21.38] BREAKDOWN TABLE. Columns 0..8 = the Accumulated-Breakdown-Point bands
# (0-3, 4-10, 11-20, 21-30, 31-40, 41-50, 51-60, 61-70, 71+); each cell is a
# sequential-2d6 range (11..66). Transcribed from data/breakdown_rates.json (the
# chart-of-record, RE-READ off PDF page 102 to recover the col 41-50 / 75%-row 66 the
# OCR dropped) and bound to it by test_breakdown; every column partitions all 36 rolls.
_BREAKDOWN: list[tuple[int, list[str]]] = [
    (0,  ["11-66", "11-42", "11-32", "11-26", "11-23", "11-16", "11-14", "",      ""]),
    (10, ["",      "43-64", "33-62", "31-55", "24-53", "21-46", "15-42", "11-33", "11-25"]),
    (25, ["",      "65",    "63-64", "56-62", "54-61", "51-56", "43-54", "34-52", "26-43"]),
    (33, ["",      "66",    "65",    "63-65", "62-64", "61-63", "55-63", "53-62", "44-55"]),
    (50, ["",      "",      "66",    "66",    "65-66", "64-65", "64-65", "63-64", "56-63"]),
    (75, ["",      "",      "",      "",      "",      "66",    "66",    "65-66", "64-66"]),
]
_N_BP_COLS = 9

# Upper bound of each Accumulated-Breakdown-Point band (21.31: fractions round up).
_BP_BAND_HI = (3, 10, 20, 30, 40, 50, 60, 70)


def breakdown_band(bp: float) -> int:
    """The 21.38 column index (0..8) for `bp` accumulated Breakdown Points, before any
    BAR / weather adjustment. Fractions round up (21.31: 20.5 -> 21 -> the 21-30 band)."""
    n = math.ceil(bp)
    for idx, hi in enumerate(_BP_BAND_HI):
        if n <= hi:
            return idx
    return _N_BP_COLS - 1                     # 71+


def breakdown_column(bp: float, bar: int, weather_shift: int) -> int:
    """The adjusted 21.38 column (21.32: BAR + Weather are cumulative), UNCLAMPED so the
    21.26 re-check gate can tell when a stopping unit has climbed into a higher column."""
    return breakdown_band(bp) + bar + weather_shift


def breakdown_result(bp: float, bar: int, weather_shift: int, roll: int) -> int:
    """Rule 21.38: the percentage of a vehicle type's TOE that breaks down, from its
    accumulated Breakdown Points adjusted by BAR + Weather (21.32) on a sequential 2d6.
    Per 21.33 a column adjusted below the 4-10 column suffers no Breakdown, and 71+ is
    the ceiling."""
    col = breakdown_column(bp, bar, weather_shift)
    if col < 1:                               # 21.33: below the 4-10 column -> no breakdown
        return 0
    col = min(_N_BP_COLS - 1, col)            # 21.33: cannot adjust above 71+
    for pct, cells in _BREAKDOWN:
        if roll in expand(cells[col]):
            return pct
    return 0


# [22.8] BROKEN DOWN VEHICLE REPAIR TABLE, the two FIELD columns (Fork B repairs only
# in the field; the Temporary/Major Facility columns are deferred). One die: for a tank/
# SPA the cell is a PERCENTAGE of that type repaired; for an armored-car/recce it is a
# number of TOE Strength Points; for a truck a number of Truck Points. Transcribed from
# data/breakdown_rates.json (chart-of-record) and bound to it by test_breakdown. Die 0
# is reachable only via the deferred TDS/Major-city modifiers; a bare d6 rolls 1..6.
# The Tank 2/3/4 cells are 10 (the chart's "10%*"), RE-READ off PDF page 103: the OCR
# bled "10%*" into "100%" (T0-1). The 10%* single-TOE exception is enforced by
# _repaired_count (22.25), not encoded here.
_FIELD_REPAIR: dict[str, dict[int, int]] = {
    "truck":    {0: 2, 1: 2, 2: 1, 3: 0, 4: 0, 5: 0, 6: 0},   # Truck Points
    "ac_recce": {0: 1, 1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},   # TOE Strength Points
    "tank":     {0: 25, 1: 25, 2: 10, 3: 10, 4: 10, 5: 0, 6: 0},  # percentage of the type (10%* = 10)
}


def field_repair(vclass: str, die: int) -> int:
    """Rule 22.8 Field column: for a 'tank' (tank/SPA/TD) the percentage of that type
    repaired; for 'ac_recce' the TOE Strength Points repaired; for 'truck' the Truck
    Points repaired. Rolls off the table are 0 (no repair)."""
    return _FIELD_REPAIR[vclass].get(die, 0)


# [21.14]/[54.2] Truck Breakdown Adjustment Rating: ALL Truck Points are "2 Left" -- a
# favourable static shift of the 21.38 column (fewer breakdowns), the same for Light,
# Medium and Heavy. The Light-truck off-road +1 BP/hex is a separate accrual in
# movement.breakdown_points (54.2 note), not a BAR shift. Bound to
# data/breakdown_rates.json.bar_by_model.trucks_54_2 by test_lorry_mortal.
TRUCK_BAR: int = -2


def weather_breakdown_shift(weather: str) -> int:
    """Rule 21.37: Hot Weather and Sandstorms each shift the Breakdown column one higher
    (1R). Keyed off the weather label; Rainstorm acts on Breakdown Points via road-as-
    track (movement.breakdown_points), not as a column shift."""
    return 1 if weather in ("hot", "sandstorm") else 0


def barrage_terrain_shift(terrain: Terrain, fort_level: int, target_class: str) -> int:
    """Rule 12.33/12.34: the Barrage-Points column-band shift (<= 0, bands left)
    benefitting a barraged unit in protective terrain or a fortification. The defender
    takes the BEST of terrain OR fortification -- they are NOT cumulative (12.34).
    Armour-class targets receive the fortification benefit only in a Major City hex
    (8.37 note 12); infantry/gun targets get it in any fortified hex."""
    terrain_shift = HEX_BARRAGE_SHIFT.get(terrain, 0)
    fort_applies = fort_level > 0 and (target_class != "armor" or terrain == Terrain.MAJOR_CITY)
    fort_shift = FORT_BARRAGE_SHIFT.get(fort_level, -2) if fort_applies else 0
    return min(terrain_shift, fort_shift)
