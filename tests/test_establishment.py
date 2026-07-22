"""[34.6] / [59.3] THE INITIAL AIR STRENGTHS -- the transcription, and the bridge from a roster of
aeroplanes to Air Points.

    59.31 "Each scenario lists the starting Axis and Allied PLANE TYPES, NUMBERS, pilots, air
          facilities, and squadron ground support units."
    59.32 "Planes are listed by type, WITH THE READY PLANES INDICATED AS A PORTION OF THE TOTAL
          AVAILABLE."
    60.32 "The following planes may be placed at any Italian airfields... However, no planes start
          the game in Italy/Sicily."
    64.3  "If the entire campaign is being played, the Players use the information provided in
          SECTION 60.0 for the initial placement and distribution of their land, sea, and air
          forces."

WHAT THIS REPLACED: a four-aeroplane proxy. game.air named ONE representative type per side and
role -- a Ju. 87B at Bombload 5 stood for the whole Axis bomber arm -- and scenario._AXIS_AIR_STRIKE
seeded it 24 Bomb Points, of which rule 43 left a quarter in Africa: three aeroplanes before
Game-Turn 35 and one after. [60.32] musters 133 S.M. 79 Sparvieros alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import game.air as air
import game.roster as roster
from game.events import Side
from game.logistics_data import aircraft_characteristics_4_44, air_establishments_59_3
from game.scenario import campaign

ROLES = ("fighters", "strike", "recon")


# --- the transcription -------------------------------------------------------------------------

def test_60_32_the_italian_air_strengths_are_the_printed_rows():
    """[60.32], PDF page 78, rendered at 300 dpi and read with eyes -- nine printed rows, of which
    eight are seeded and the ninth ('2S01') is an owner ruling. The OCR in docs/rules/60 agrees on
    all eight, which is the cross-check."""
    printed = {"CR 42": (65, 25), "CR 32": (70, 28), "Ba 65": (10, 2), "Ba 88": (24, 6),
               "SM 79": (133, 35), "SM 81": (17, 4), "Ca 309": (56, 12), "Ro37Bis": (10, 6)}
    got = {m.printed: (m.available, m.refitted) for m in roster.roster(Side.AXIS)}
    assert got == printed
    assert sum(a for a, _ in printed.values()) == 385           # 394 less the unruled nine


def test_60_42_the_commonwealth_air_strengths_are_the_printed_rows():
    """[60.42], the same page and the same reading. NOTE the Morane row: the OCR in docs/rules/60
    leaves its Available cell EMPTY; the scan prints 4."""
    printed = {"Lysanders": (12, 8), "Bombays": (15, 12), "Sunderlands": (18, 11),
               "Blenheim Mk. I's": (26, 18), "Blenheim Mk. IV's": (12, 12),
               "Blenheim Mk. IVF's": (9, 5), "Gladiators": (36, 30), "Hurricane Mk. I's": (6, 4),
               "Morane 406's*": (4, 2), "Potez 63/11*": (2, 2), "Valentia's": (3, 1)}
    got = {m.printed: (m.available, m.refitted) for m in roster.roster(Side.ALLIED)}
    assert got == printed
    assert sum(a for a, _ in printed.values()) == 143


def test_every_muster_row_names_a_transcribed_chart_row():
    """THE BUG THIS GUARDS IS THE ONE THAT ALREADY HAPPENED ONCE: rule 43's constrained-type list
    was transcribed off the RULE's prose ("He 111", "FW 220") and matched exactly against the
    CHART's printed names, so it could never bind and failed silently. Every `type` here is the
    chart's own key, so the same mistake fails loudly instead."""
    chart = aircraft_characteristics_4_44()
    for side in (Side.AXIS, Side.ALLIED):
        for m in roster.roster(side):
            assert m.type in chart, (m.printed, m.type)


def test_the_role_column_is_a_reading_of_the_printed_mission_capability():
    """The three-way partition into game.state.AirWing's buckets is OURS (the book prints no such
    thing), but it is not free: a `fighters` type must possess the charted F cell, a `strike` type
    must possess D or B AND carry a Bombload, and a `recon` type must possess R. This is what makes
    the role column in data/air_establishments.json auditable against the scan."""
    chart = aircraft_characteristics_4_44()
    for side in (Side.AXIS, Side.ALLIED):
        for m in roster.roster(side):
            cells = chart[m.type]["mission_capability"]
            need = roster.CAPABILITY_FOR_ROLE[m.role]
            assert any(cells.get(c, "-") not in roster.NO_CAPABILITY for c in need), \
                (m.type, m.role, cells)
            if m.role == "strike":
                assert chart[m.type]["bombload"] > 0, m.type
        assert air.mission_capable(side, "fighters")


def test_the_garbled_60_32_row_is_transcribed_and_left_unseeded():
    """⚠ OWNER RULING NEEDED. [60.32]'s ninth row reads '2S01' and no aircraft chart prints such a
    name; the only candidate on [4.44b] is the Cant Z. 501 Gabbiano (a Z.501 typeset with Z as 2 and
    5 as S). That is the 43.11 "FW220" class of question and the owner rules it, not this code -- so
    the row is transcribed with its printed spelling, its nine aeroplanes are NOT in the
    establishment, and the candidate chart row IS transcribed so that seeding it is one line."""
    row = air_establishments_59_3()["campaign_64"]["AXIS"]["unresolved_type_60_32"]
    assert row["printed"] == "2S01" and (row["available"], row["refitted"]) == (9, 9)
    assert row["candidate_chart_row"] == "Cant Z. 501 Gabbiano"
    assert row["candidate_chart_row"] in aircraft_characteristics_4_44()
    assert row["candidate_chart_row"] not in [m.type for m in roster.roster(Side.AXIS)]
    assert row["_owner_ruling_needed"].startswith("OWNER RULING NEEDED")


# --- the points bridge -------------------------------------------------------------------------

def test_the_establishment_converts_to_air_points_and_back_exactly():
    """34.13/34.14: an Air Point is a charted rating, so the whole establishment is worth a fixed
    number of them and converts back to itself. Everything between is a share of it."""
    assert roster.points(Side.AXIS, "strike") == 2147        # 10x10 + 24x11 + 133x12 + 17x11
    assert roster.planes(Side.AXIS, "strike") == 184
    assert roster.points(Side.AXIS, "fighters") == 405       # 65x3 + 70x3
    assert roster.points(Side.ALLIED, "strike") == 382
    assert roster.points(Side.ALLIED, "recon") == 32         # flagged: one recon point, one plane
    assert roster.planes(Side.ALLIED, "recon") == 32
    for side in (Side.AXIS, Side.ALLIED):
        for role in ROLES:
            n, pts = roster.planes(side, role), roster.points(side, role)
            assert roster.planes_flying(side, role, pts) == n
            assert roster.points_of_planes(side, role, n) == pts


def test_59_32_the_refitted_column_is_the_readiness_ledger_at_game_turn_1():
    """"Planes are listed by type, with the READY PLANES INDICATED AS A PORTION of the total
    available" -- more specific than 38.31's blanket "at the start of a Scenario, all planes are
    considered refitted", so the scenario's column wins and the campaign opens with three quarters
    of both air forces in the hangars."""
    assert (roster.ready(Side.AXIS, "strike"), roster.unfit(Side.AXIS, "strike")) == (47, 137)
    assert (roster.ready(Side.ALLIED, "strike"), roster.unfit(Side.ALLIED, "strike")) == (43, 13)
    st = campaign(seed=4, max_turns=1)
    assert st.air_unfit == {air.squadron(side, "LAND", role): roster.unfit(side, role)
                            for side in (Side.AXIS, Side.ALLIED) for role in ROLES
                            if roster.unfit(side, role) > 0}
    assert st.air_unfit["AXIS/LAND/strike"] == 137


def test_the_campaign_wings_are_the_charted_establishments():
    """game.scenario seeds the campaign's two LAND wings straight off the muster -- no authored
    integer survives. The Regia Aeronautica outnumbers the Desert Air Force better than five to one
    in Bomb Points at Game-Turn 1, which is Graziani's offensive as the charts give it."""
    st = campaign(seed=4, max_turns=1)
    wings = {w.side: w for w in st.air}
    for side in (Side.AXIS, Side.ALLIED):
        for role in ROLES:
            assert getattr(wings[side], role) == roster.points(side, role)
    assert wings[Side.AXIS].strike == 2147 and wings[Side.ALLIED].strike == 382


def test_the_fuel_rating_averages_only_the_types_that_print_one():
    """[34.17] every plane has a Fuel Consumption Rating -- except that [4.44A] prints a DASH in the
    Gladiator Mk. II's Fuel column, where the chart's key gives that glyph no meaning at all. It is
    transcribed as null (an owner ruling on the row), excluded from the average, and cannot bite: the
    38.24 bill is drawn for strike and recon only and the Gladiator is a fighter."""
    chart = aircraft_characteristics_4_44()
    assert chart["Gladiator Mk. II"]["fuel"] is None
    assert chart["Sea Gladiator"]["fuel"] == 1           # the same airframe, navalised, priced
    assert roster.fuel_per_plane(Side.AXIS, "strike") == 3       # 542 / 184, rounded up
    assert roster.fuel_per_plane(Side.ALLIED, "fighters") == 2   # over the 19 priced fighters
    from game.engine import _REFITTABLE_ROLES
    assert "fighters" not in _REFITTABLE_ROLES


def test_a_role_with_no_establishment_fails_loud_rather_than_flying_for_free():
    """The house rule of this corner of the engine: an unknown key is an error, not a silent
    one-plane mission at rating 1 (game.air's _POINTS_PER_PLANE_RATING carried the same rule)."""
    import pytest
    with pytest.raises(KeyError):
        roster.by_role(Side.AXIS, "bombers")
