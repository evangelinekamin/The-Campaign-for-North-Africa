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

from .terrain import Hexside, Terrain

# Column order (index 0..17) = the differential headers of the CRT.
_COLUMNS = ("-11", "-8..-10", "-6..-7", "-4..-5", "-3", "-2", "-1", "0",
            "+1", "+2", "+3", "+4", "+5..+6", "+7..+8", "+9..+10",
            "+11..+13", "+14..+16", "+17")
N_COLS = len(_COLUMNS)


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


def morale_modifier(cohesion: int, roll: int) -> "int | str":
    """Rule 17.4: the modifier applied to Basic Morale for one combat, from the
    unit's Cohesion level and a sequential 2d6 roll. Returns an int, or 'SURR'
    (surrender). Cohesion is clamped to the table's [-17, +8]."""
    cells = _MORALE_TABLE[max(-17, min(8, cohesion))]
    for mod, cell in zip(_MORALE_MODS, cells):
        if roll in expand(cell):
            return mod
    return 0


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
