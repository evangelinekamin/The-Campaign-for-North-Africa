"""Independent, deterministic random streams -- one per subsystem. The INSTRUMENT.

THE BUG THIS EXISTS TO KILL. The engine used to draw every die in the game -- weather,
initiative, combat, breakdown, repair, demolition, interdiction, air -- from ONE
random.Random seeded with the master seed. Subsystems draw CONDITIONALLY: engine._interdict
rolls its two [41.66] dice only when an InterdictionOrder covers the lane, engine._repair
only when a side has something broken, engine._air_superiority only when a side fields air.
So changing the NUMBER of draws in ONE subsystem reshuffled the dice EVERY OTHER SUBSYSTEM
saw for the rest of the war. An A/B that toggled a conditionally-drawing subsystem was
measuring the reshuffle, not the change.

WHAT IT COST. The air audit recorded "Malta is causally inert -- cranked to its rule-41.66
ceiling the victory score does not move", and that went into project memory as a settled
dead end. It was an artefact of this desync. With the dice held still, Malta is one of the
strongest levers in the engine (scripts/measure_malta.py) -- and the historically correct
one. We hid it behind a broken thermometer.

THE PROPERTY THIS MODULE GUARANTEES, and the only one that matters:

    A DIE DRAWN, OR NOT DRAWN, IN ONE SUBSYSTEM CANNOT SHIFT THE DICE ANY OTHER
    SUBSYSTEM SEES.

Each subsystem gets its own random.Random, seeded from a stable digest of (master seed,
subsystem name). Toggling interdiction now consumes the interdiction stream and nothing
else; weather, combat and breakdown roll on, undisturbed. Guarded by tests/test_dice.py,
which fails on the pre-fix engine.

WHAT THIS DOES NOT FIX, and cannot. Changing a RULE changes outcomes, which changes how
many dice a subsystem later consumes and when. That is inherent to a stochastic simulation
and no stream discipline removes it. The remedy is methodological: report a balance claim
as a DISTRIBUTION OVER N SEEDS, never as a single-seed outcome.

WHY hashlib AND NOT hash(). The builtin hash() is salted per process (PYTHONHASHSEED), so
seeding a stream from it would make the same seed produce a different game in a different
process -- the exact opposite of what this module is for.
"""
from __future__ import annotations

import hashlib
import random

# Every die the engine rolls, routed to its own stream. Adding a die to the engine means
# adding its subsystem here: DiceBox rejects an unknown name rather than inventing a stream
# for a typo. (The scenario builders' convoy-cargo dice -- scenario._axis_convoy_cargo,
# scenario._campaign_axis_cargo -- are already independent random.Random instances drawn to
# completion at BUILD time, before the engine rolls anything, so they cannot desync it.)
SUBSYSTEMS: tuple[str, ...] = (
    "initiative",         # [7.14] Initiative Determination, and its tie rerolls
    "rommel",             # [31.5] the Berlin recall
    "weather",            # [29.61] the weather type + [29.7] the foul-weather location die
    "air_superiority",    # [40/45/46] who holds the sky this Operations Stage
    "recon",              # [42.24] the +-2 TOE noise on an air recon
    "naval_bombardment",  # [30.2] the Commonwealth fleet's off-shore fire
    "interdiction",       # [41.66] convoy bombing at sea -- THE conditional drawer (Malta)
    "air_bombard",        # [41.5] land air bombardment (41.39B harbour bombing rolls the Ports row)
    "breakdown",          # [21.38] the vehicle Breakdown Table
    "repair",             # [22.8] the field-repair columns
    "demolition",         # [54.17] blowing a supply dump
    "barrage",            # [12.6] the Barrage CRT
    "anti_armor",         # [14.6] the Anti-Armor CRT
    "close_assault",      # [15.79] the Close Assault CRT
    "morale",             # [17.4] the Morale Table
)


def stream_seed(master: int, subsystem: str) -> int:
    """The deterministic seed for one subsystem's stream: a stable 64-bit digest of
    (master seed, subsystem name). Stable across processes, machines and Python versions --
    which the builtin hash() is not."""
    digest = hashlib.blake2b(f"{master}:{subsystem}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


class DiceBox:
    """The engine's dice: one independent random.Random per subsystem, every one of them
    derived from the master seed, so the game is reproducible from the seed alone and no
    subsystem can perturb another."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._streams: dict[str, random.Random] = {
            sub: random.Random(stream_seed(seed, sub)) for sub in SUBSYSTEMS
        }

    def stream(self, subsystem: str) -> random.Random:
        """The generator for one subsystem. Raises on an unknown name -- a typo must not
        silently share another subsystem's dice."""
        try:
            return self._streams[subsystem]
        except KeyError:
            raise KeyError(f"unknown dice subsystem {subsystem!r} -- "
                           f"add it to game.dice.SUBSYSTEMS") from None

    def d6(self, subsystem: str) -> int:
        """One die, drawn from `subsystem`'s own stream."""
        return self.stream(subsystem).randint(1, 6)

    def load(self, subsystem: str, rng) -> None:
        """Replace one subsystem's stream. THE TEST SEAM: a test that needs a known die pins
        exactly the subsystem it is exercising and leaves every other stream alone -- so a
        pinned repair die can no longer bend a weather roll."""
        self.stream(subsystem)                     # reject a typo'd name before installing
        self._streams[subsystem] = rng
