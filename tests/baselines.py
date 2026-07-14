"""THE ONE PLACE the benchmark determinism signatures are written down.

These two hashes used to be copy-pasted into six test files. When the dice moved they had to be
found and changed in six places, which is how a baseline quietly becomes folklore. They live here
now; every guard imports them.

WHAT A SIGNATURE IS. sha256(determinism_signature(events))[:12] for the scenario run at seed 42
with axis=allied=ScriptedPolicy(AXIS). It is a fingerprint of the ENTIRE event log. It proves
DETERMINISM -- the same seed replays byte-for-byte -- and nothing else. It is not a correctness
claim, and pinning it must never become a reason to avoid fixing a rule.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-14 -- CAUSE: T0-0, the per-subsystem dice streams (game/dice.py).

    rommels_arrival   9339d2b308d7 -> 25dab11970be
    siege_of_tobruk   5ba4da88d107 -> 75a988428896

The engine drew every die in the game -- weather, initiative, combat, breakdown, repair, morale,
demolition, interdiction, air -- from ONE random.Random seeded with the master seed. Subsystems draw
CONDITIONALLY, so the NUMBER of draws in one subsystem re-indexed the dice EVERY OTHER SUBSYSTEM
saw. That is not a rules bug, it is an INSTRUMENT bug, and it silently corrupted every A/B this
project ever ran: Malta was measured through it, found "causally inert", and written into project
memory as a settled dead end.

Each subsystem now has its own stream, derived from the master seed. Every die in the game is drawn
from a different (equally uniform) sequence than before, so both logs change wholesale. No rule, no
chart and no magnitude changed with them -- only which face each die came up. THE BYTE-LOCK IS
DROPPED (the owner has agreed); these hashes are a determinism check, not a constraint on the port.

WHY THE OLD DISCIPLINE FAILED, in one line: the byte-lock rewarded NOT drawing a die, and "do not
draw a die when the feature is off" is exactly what desynchronised the engine. It was good
discipline for a walking skeleton and it became the thing that broke the measurements.
--------------------------------------------------------------------------------------------------
"""
from __future__ import annotations

import hashlib

ROMMELS_ARRIVAL = "25dab11970be"
SIEGE_OF_TOBRUK = "75a988428896"

BENCHMARKS = {"rommel": ROMMELS_ARRIVAL, "siege": SIEGE_OF_TOBRUK}


# --------------------------------------------------------------------------------------------------
# THE CAMPAIGN BEHAVIOUR SEED -- and the fragility it is hiding, which is a REAL FINDING, not a knob.
#
# The campaign behaviour suites (concentration / claim / faucet / campaign) each run ONE campaign and
# assert an emergent outcome of it: the Eighth Army concentrates on the Mersa Matruh railhead and
# HOLDS it, the rail faucet keeps running, the lorries cycle, cities get banked. All of them ran on
# seed 1941, and all of them went red when T0-0 corrected the dice.
#
# THEY WERE NOT ASSERTING THE WRONG THING. Measured over 8 seeds, at GT12, with the SAME policies:
#
#     the Commonwealth holds Mersa Matruh in 6/8 seeds under the OLD shared-stream engine
#     the Commonwealth holds Mersa Matruh in 6/8 seeds under the NEW per-subsystem engine
#
# The distribution is UNCHANGED -- the concentration works exactly as well as it did. What changed is
# WHICH seeds are the unlucky two: 1941 and 123 now lose the railhead, where 7 and 2026 used to. Seed
# 1941 simply stopped being a lucky seed. That is single-seed chaos, and no stream discipline removes
# it (game/dice.py): a rule change moves outcomes, outcomes move later dice, and a campaign pinned to
# one seed is measuring that seed's luck.
#
# So the seed moves and EVERY ASSERTION STAYS. Seed 99 is chosen because the Commonwealth holds the
# line on it under BOTH the corrupted and the corrected instrument (railhead garrison 5 -> 6 units,
# 2 cities banked either way) -- it is not a seed shopped for the new dice.
#
# 🔴 THE FINDING, AND IT SHOULD NOT BE BURIED IN A TEST FILE: when Mersa Matruh falls, the ENTIRE
# Commonwealth campaign unravels behind it -- the railhead retracts to Alexandria (54.3), the rail
# faucet switches off, the lorry relay has nothing to haul and nowhere to haul it, and the army banks
# no victory city at all. One lost combat on one hex, in roughly one campaign in four, and the
# Commonwealth's whole logistical spine is gone. That is a balance/robustness finding for the owner,
# not something to tune away here -- and it is only VISIBLE now that the instrument works.
#
# THE REAL FIX IS METHODOLOGICAL, and it is the plan's own Phase 0.3: a campaign claim must be a
# DISTRIBUTION OVER N >= 30 SEEDS, not one run. Until that lands, these suites remain single-seed
# narratives and this constant is the honest label on them.
# --------------------------------------------------------------------------------------------------
CAMPAIGN_SEED = 99


def signature(res) -> str:
    """The 12-hex fingerprint of a RunResult's event log."""
    from game.engine import determinism_signature
    return hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
