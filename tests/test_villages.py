"""The [54.12] VILLAGE capacity row and the location overlay that carries it (rules 8.37/54.12).

Every non-city dump in the game read the chart's Other-Terrain row, because a village was not
modelled at all. The chart has four location rows, not three, and the missing one is the row the
whole Commonwealth logistics chain stands on: Mersa Matruh, Sidi Barrani, Sollum, El Daba and
El Hamman are all villages, and so is the Axis relay's Derna.

The overlay is a SET OF HEXES on GameState, never a Terrain member -- [8.37] is explicit that a
Village/Bir/Oasis is "Same as terrain in hex for all purposes", so it must move no unit, shift no
combat and fortify nothing ([25.12]: "Villages are not fortifications").
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import coords, invariants, supply, villages           # noqa: E402
from game.apply import fold                                     # noqa: E402
from game.campaign_policy import (CampaignAxisPolicy,           # noqa: E402
                                  CampaignCommonwealthPolicy)
from game.engine import run                                     # noqa: E402
from game.scenario import campaign, rommels_arrival, siege_of_tobruk   # noqa: E402
from game.terrain import Terrain                                # noqa: E402


def _ax(label: str):
    return coords.to_axial(coords.parse(label))


_MATRUH = _ax("D3714")          # village + railhead (60.7)
_BARRANI = _ax("C4131")         # village (60.44 dump)
_SOLLUM = _ax("C4021")          # village (60.34 field depot)
_DERNA = _ax("B5925")           # village (the Axis relay's staging dump)
_TOBRUK = _ax("C4807")          # MAJOR CITY -- stays unlimited
_BARDIA = _ax("C4321")          # MAJOR CITY -- stays unlimited
_BENGHAZI = _ax("A4827")        # MAJOR CITY (stamped by campaign()) -- stays unlimited
_BIR_EL_GUBI = _ax("C4108")     # a BIR: the 54.12 chart has no Bir row -> Other Terrain


# --- the chart itself ---------------------------------------------------------

def test_village_row_is_the_54_12_chart():
    """[54.12] Village: 2,500 Ammo / 8,000 Fuel / 3,000 Stores / 1,000 Water. Transcribed, never
    invented -- and note the Water column is 1,000 in BOTH the Village and the Other-Terrain row,
    so the village row is a no-op for water STORAGE (the water gap, if any, is on the draw side)."""
    village = supply.dump_capacity(Terrain.CLEAR, village=True)
    assert village == {"AMMO": 2500, "FUEL": 8000, "STORES": 3000, "WATER": 1000}
    other = supply.dump_capacity(Terrain.CLEAR)
    assert other == {"AMMO": 1500, "FUEL": 5000, "STORES": 1000, "WATER": 1000}
    assert village["WATER"] == other["WATER"]           # the 54.12 water columns are equal


def test_the_village_row_sits_between_the_city_and_the_desert():
    """A village holds strictly more than open desert and strictly less than a major city."""
    city = supply.dump_capacity(Terrain.MAJOR_CITY)
    for c in ("AMMO", "FUEL", "STORES"):
        assert (supply.dump_capacity(Terrain.CLEAR)[c]
                < supply.dump_capacity(Terrain.CLEAR, village=True)[c] < city[c])


def test_a_major_city_stays_unlimited_even_if_flagged_a_village():
    """The 54.12 rows are exclusive and Major City is the higher: a hex stamped MAJOR_CITY reads
    the city row whatever the gazetteer calls it (Tobruk/Bardia/Benghazi are cities AND named
    places). Guards the overlay from ever DEMOTING a city dump."""
    assert (supply.dump_capacity(Terrain.MAJOR_CITY, village=True)
            == supply.dump_capacity(Terrain.MAJOR_CITY))


def test_default_is_the_other_terrain_row_byte_lock():
    """The kwarg defaults False, so every caller that does not know about villages -- and every
    byte-locked benchmark scenario -- reads exactly the row it read before."""
    assert supply.dump_capacity(Terrain.DESERT) == supply.dump_capacity(Terrain.DESERT,
                                                                        village=False)


# --- the overlay --------------------------------------------------------------

def test_a_village_is_not_a_terrain_type():
    """[8.37] 'Village/Bir/Oasis -- Same as terrain in hex for all purposes.' The overlay must
    never become a Terrain member, or it would silently change movement cost, breakdown and the
    combat shifts of every hex it lands on."""
    assert not hasattr(Terrain, "VILLAGE")


def test_the_gazetteer_names_the_villages_and_excludes_the_cities():
    st = campaign(seed=1941)
    for hx in (_MATRUH, _BARRANI, _SOLLUM, _DERNA):
        assert hx in st.villages
    for hx in (_TOBRUK, _BARDIA, _BENGHAZI):        # already MAJOR_CITY: a city, not a village
        assert hx not in st.villages
        assert st.terrain.terrain[hx] == Terrain.MAJOR_CITY


def test_a_bir_is_not_a_village():
    """[52.11] lists 'major cities, villages, and birs' as THREE kinds, and the 54.12 chart prints
    no Bir row. A bir therefore reads Other Terrain. Flagged as the conservative transcription."""
    assert _BIR_EL_GUBI not in campaign(seed=1941).villages


def test_the_overlay_changes_no_terrain_and_fortifies_nothing():
    """[8.37] the village hex keeps its own terrain; [25.12] 'Villages are not fortifications.'"""
    st = campaign(seed=1941)
    for hx in st.villages:
        assert st.terrain.terrain[hx] != Terrain.MAJOR_CITY
        assert hx not in st.terrain.fortifications      # 25.12: no fort at a village


def test_dump_capacity_at_reads_the_overlay():
    st = campaign(seed=1941)
    assert supply.dump_capacity_at(st, _MATRUH)["FUEL"] == 8000      # village
    assert supply.dump_capacity_at(st, _TOBRUK)["FUEL"] == supply._UNLIMITED   # major city
    assert supply.dump_capacity_at(st, _BIR_EL_GUBI)["FUEL"] == 5000  # other terrain


def test_the_railhead_ceiling_is_the_village_row():
    """The bug, named: rule 60.44 seeds the Commonwealth 1,000 Ammo / 3,000 Fuel / 4,000 Stores at
    Mersa Matruh, and the 54.3 railway lands 12,000 Fuel Points a Game-Turn on top of it -- into a
    hex the engine capped at the Other-Terrain row (1,500/5,000/1,000)."""
    st = campaign(seed=1941)
    cap = supply.dump_capacity_at(st, _MATRUH)
    assert (cap["AMMO"], cap["FUEL"], cap["STORES"]) == (2500, 8000, 3000)


# --- the byte-lock ------------------------------------------------------------

def test_the_benchmark_scenarios_stay_village_blind():
    """HARD CONSTRAINT. rommels_arrival / siege_of_tobruk are byte-locked benchmarks: they seed NO
    villages, so every dump in them keeps reading the Other-Terrain row bit-for-bit. This is a
    KNOWN, FLAGGED asymmetry pending a re-baseline decision -- not a claim that the engine is
    village-blind everywhere."""
    for build in (rommels_arrival, siege_of_tobruk):
        assert build(seed=42).villages == frozenset()


# --- conservation -------------------------------------------------------------

def test_raising_the_ceiling_mints_no_supply():
    """A higher ceiling lets the faucet fill FURTHER UP; it never creates a Point. Over a campaign
    slice the ledger still balances (on-hand + consumed == initial, per commodity) and the event
    log still folds byte-identically back to the final state."""
    res = run(campaign(seed=1941, max_turns=12),
              CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    assert fold(res.initial, res.events) == res.final
    invariants.check(res.final)
    for commodity, initial in res.final.initial_supply.items():
        on_hand = (sum(getattr(s, commodity.lower()) for s in res.final.supplies)
                   + sum(getattr(t, commodity.lower()) for t in res.final.trucks))
        assert on_hand + res.final.consumed.get(commodity, 0) == initial


def test_no_dump_ever_exceeds_its_54_12_ceiling():
    """The ceiling is enforced, not decorative: no dump on the map ends a campaign slice holding more
    than its location's row allows -- EXCEPT where it was seeded above the row at t0. Rule 60.44 puts
    4,000 Stores on Mersa Matruh (above even the Village row's 3,000) and the finite/oasis wells
    (52.7/52.13) seed Water far above the 1,000 Water cap, because 54.12 caps a single DUMP and a
    location may hold more than one. A seeded-high dump DRAINS; it never refills past the row.

    THE RELOCATION CLAMP (apply.py SUPPLY_MOVED), per the owner's 'listen to the rulebook' ruling: a
    dump hauled forward stores no more at its DESTINATION than that hex's row allows. A base-filled
    depot dragged off the unlimited Cairo city onto Other Terrain used to carry its whole ~17k-Fuel
    load over-cap; it now SHEDS the overflow, which STAYS AT THE ORIGIN as a dump (54.11: "Any hex can
    be used as a supply dump") rather than being destroyed -- supply is destroyed only by the rules
    that say so (demolition 54.14, the capture tax 49.19/50.16/51.16). So a RELOCATED dump is held to
    its row exactly as the FILL path already held a filled one, and the founding-hex exemption this
    test used to carry -- while the excess's fate was un-ruled -- is gone."""
    res = run(campaign(seed=1941, max_turns=12),
              CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    seeded = {s.id: s for s in res.initial.supplies}
    for s in res.final.supplies:
        cap = supply.dump_capacity_at(res.final, s.hex)
        for c in supply.COMMODITIES:
            held = getattr(s, c.lower())
            start = getattr(seeded[s.id], c.lower()) if s.id in seeded else 0
            assert held <= max(cap[c], start), f"{s.id} holds {held} {c} over its 54.12 ceiling"


def test_villages_module_reconciles_both_rulebook_enumerations():
    """The overlay is built from the two enumerations already transcribed in this repo, and from
    nothing else: data/wells.json (rule 52.11's named villages) and the rule-64.73 Geographic
    Occupation table (headed 'City/Village'). Siwa/Jalo/Giarabub are oases in wells.json but the
    64.73 table names them City/Village, so the table carries them in."""
    named = villages.named_villages()
    assert _MATRUH in named and _DERNA in named
    assert _ax("C0127") in named             # Siwa -- oasis in wells.json, village per 64.73
    assert _BIR_EL_GUBI not in named         # a bir is not a village
    # every 64.73 city that is not terrain-stamped MAJOR_CITY ends up in the overlay
    st = campaign(seed=1941)
    for hx in (_ax("C0127"), _ax("B0513"), _ax("C1014")):     # Siwa, Jalo, Giarabub
        assert hx in st.villages


def test_the_overlay_survives_a_state_replace():
    """GameState is frozen and rebuilt with dataclasses.replace on every event; the overlay is a
    plain field, so it must ride through untouched (a dropped overlay silently re-introduces the
    bug mid-campaign)."""
    st = campaign(seed=1941)
    assert replace(st, turn=5).villages == st.villages
