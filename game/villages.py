"""The VILLAGE location overlay (rules 8.37 / 54.12) -- which hexes carry a village.

A VILLAGE IS NOT A TERRAIN TYPE. The [8.37] Terrain Effects Chart says so in one line:

    Village/Bir/Oasis | Same as terrain in hex for all purposes

-- so a village must change no CP cost, no Breakdown Value, no Barrage/Anti-Armor/Close-Assault
shift and no spotting. It is a LOCATION printed ON a hex, whatever the hex's terrain. Adding a
Terrain.VILLAGE member would silently move every unit that walked through one. Hence a frozenset
of hexes carried on GameState (state.villages) and consulted by the one chart that keys off it.

WHAT KEYS OFF IT HERE: the [54.12] Supply Dump Capacity Chart. Its Village row --

    Village       | 2,500 Ammo | 8,000 Fuel | 3,000 Stores | 1,000 Water
    Other Terrain | 1,500 Ammo | 5,000 Fuel | 1,000 Stores | 1,000 Water

-- was never modelled, so EVERY non-city dump on the map, both sides, all 111 turns, read the
Other-Terrain row. That is not a rounding error: the Commonwealth's whole logistics chain stands
on villages (Mersa Matruh, Sidi Barrani, Sollum, El Daba, El Hamman) and so does the Axis relay's
Derna. The 54.3 railway lands 12,000 Fuel Points a Game-Turn onto the Mersa Matruh railhead --
into a dump the engine capped at 5,000, throwing the overflow away. The rulebook's own setup chart
is the tell: [60.44] seeds the Commonwealth 4,000 Stores at Mersa Matruh, four times the ceiling
our terrain model gave that hex.

THE GAZETTEER: RECONCILING THE TWO ENUMERATIONS ALREADY IN THIS REPO. Neither is complete alone.

  (a) data/wells.json -- [52.11] ("Wells are located in major cities, villages, and birs. Water is
      also found in oases") transcribes every NAMED on-map location the rulebook gives a hex for,
      each tagged major_city / village / bir / oasis, with a citation. Its `village` entries are
      the backbone of this set.
  (b) The [64.73] Geographic Occupation table (docs/rules/64:68) is headed "City/ Village": every
      hex in it is, by the rulebook's own words, a city or a village. It is already transcribed as
      data/victory_cities.json and seeded into state.victory.

They agree on Mersa Matruh, Sidi Barrani, Sollum and Derna. They differ on exactly three hexes --
Siwa, Jalo and Giarabub -- which wells.json tags `oasis` (its tag answers "which [52.7] water
column?", not "is there a settlement?") while the 64.73 table calls them City/Village. The 64.73
table is the one talking about locations, so it carries them in. The union, minus every hex the
scenario stamps MAJOR_CITY (Tobruk, Bardia, Benghazi, Cairo, Alexandria -- a city stays a city and
keeps its unlimited row), is the overlay.

FLAGGED PLACEMENT CHOICES, so nothing is silently invented:
  * A BIR IS NOT A VILLAGE. [52.11] lists "major cities, villages, and birs" as three distinct
    kinds and the 54.12 chart prints no Bir row, so the seven transcribed birs read Other Terrain.
    The alternative (birs share the Village row) is an invention beyond the chart; it is also
    close to unobservable -- no seeded dump stands on a bir.
  * THE SET IS A LOWER BOUND, inherited from wells.json: the printed map marks a village symbol on
    more hexes than the rulebook NAMES, and our terrain pipeline colour-samples the map background
    and cannot see printed symbols. Every hex here is rulebook-named with a citation; hexes the
    map draws a village on but the text never names are missing, and read Other Terrain.
  * WATER IS UNAFFECTED. The 54.12 Water column is 1,000 in the Village row AND the Other-Terrain
    row, so the overlay changes no water ceiling anywhere. Village water is a DRAW-side rule
    ([52.7] Town column) and game.wells already models it.
"""
from __future__ import annotations

from . import campaign_victory, coords, wells
from .hexmap import Coord
from .terrain import Terrain


def _ax(label: str) -> Coord:
    return coords.to_axial(coords.parse(label))


def named_villages() -> frozenset:
    """Every hex the rulebook NAMES as a village: the [52.11] gazetteer's `village` entries
    (data/wells.json) united with the [64.73] "City/Village" table (data/victory_cities.json).
    Major-city hexes are NOT filtered here -- village_hexes does that against the live map, which
    is the only place that knows which hexes a scenario stamped MAJOR_CITY."""
    from_wells = {_ax(w["hex"]) for w in wells.load()["wells"] if w["kind"] == "village"}
    from_64_73 = {_ax(c["hex"]) for c in campaign_victory.load_victory_cities()["cities"]}
    return frozenset(from_wells | from_64_73)


def village_hexes(terrain: dict) -> frozenset:
    """The [54.12] village overlay for a map: every rulebook-named village that the scenario has
    not stamped MAJOR_CITY. The 54.12 rows are exclusive and Major City is the higher of the two,
    so Tobruk / Bardia / Benghazi -- named places that are also cities -- keep their unlimited
    ceiling and never appear here."""
    return frozenset(h for h in named_villages()
                     if terrain.get(h) is not None and terrain[h] != Terrain.MAJOR_CITY)
