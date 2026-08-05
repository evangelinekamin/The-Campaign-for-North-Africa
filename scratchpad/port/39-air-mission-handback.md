# Handing the air force back to the staff -- [39.19] and Policy.air_missions()

Owner, 2026-08-03, on the doctrine gaps: *"this reads like stuff the ai/staff should have to do
themselves rather than something that should be just automated away (and it makes me worried that
we've automated away other parts of the game that they should have to decide)"*.

Air is the sharpest instance. `scenario._campaign_air_missions` (scenario.py:1518) bakes a fixed
schedule -- both sides bomb PORT-Tobruk every Game-Turn for the whole war -- and
`engine._air_support` (engine.py:2975) reads it straight off `state.air_missions`. **No Policy
method is consulted anywhere.** The Axis air seat has no say over its own air force.

## THE ALLOCATION RULE EXISTS. IT IS [39.19].

Verbatim off the scan (PDF p.56, folio 9):

> "Generally, a plane may fly only one mission per Operations Stage or Strategic Phase (with the
> exception of certain fighters and dive bombers; Case 39.2). A plane flying a mission in an
> Operations Stage may not fly in the Strategic Phase of that Game-Turn and vice versa."

Restated at [40.0] and [40.24]. **The unit of assignment is the individual PLANE** -- [39.16]
explicitly permits one squadron to split across different missions; the only split it forbids is
strategic vs land-support. **Mission COUNT is explicitly uncapped ([39.15]/[39.17])**: the plane
ledger is the entire bound. Three further printed ceilings apply per sortie: [37.24] (field
Capacity Level and SGSU ready capacity, "no more than nine planes on a mission"), [38.31] (refit
consumed per sortie, already implemented), [37.15]/[37.16] (fuel, already implemented).

## WHY THE LEDGER MUST LAND BEFORE THE HOOK

`engine._air_points` (engine.py:2730) returns the side's **whole** available pool of a role to
**every** mission -- it is never decremented. Today the one-mission-per-turn schedule is the only
thing bounding sorties. Open a Policy hook without [39.19] and a staff tasks ten missions and flies
its entire air force ten times over. **Build the ledger first, and prove it bounds the fleet.**

## THE SLICE

1. **[39.19] per-OpStage plane-commitment ledger. HALF OF IT IS ALREADY BUILT -- scope this
   narrowly.** `basing.available_points` (basing.py:584) already implements [39.19]'s
   *Strategic-Phase-versus-Operations-Stage* half: it deducts `strategic_planes(...)` from the
   establishment, so a plane that flew in the Strategic Phase is already excluded from a land
   mission, and its docstring says it is "the one function engine._air_points calls, so the two
   rules can never be applied in only one of the places a mission is sized from."
   **What is missing is only the WITHIN-STAGE half:** several land missions in one Operations Stage
   each draw the full, undeducted pool. That is the ledger to build, and it is the whole of it.
   Use `_OpStageLedger` (engine.py:84) -- its docstring says outright "build one of these, do not
   hand-roll a fourth", after this exact defect (a per-OpStage ledger reset in `run()`'s stage loop
   instead of self-expiring on a `(turn, stage)` stamp) shipped TWICE.
   NOTE FOR WHOEVER REVIEWS IT: the ledger's docstring warns that facts which must agree about the
   stage belong in ONE value, because "two ledgers are two stamps, and two stamps can disagree."
   That warning does NOT apply here. The within-stage commitment and the Strategic-Phase exclusion
   run on genuinely different clocks (Operations Stage vs Game-Turn), so they are correctly two
   mechanisms -- and the second one already exists in `basing`. Do not "unify" them.
2. **A kind whitelist, which is a live gap in its own right.** engine.py:3002's `if/elif` chain
   **silently DROPS an unknown mission kind** -- no rejection, no event. Harmless while the only
   author is the scenario; an order-validation hole the moment a policy can author missions. Emit
   ORDER_REJECTED, matching every other hook.
3. **`Policy.air_missions(state, side) -> list[AirMission]`**, consulted at engine.py:2975. Default
   returns the scenario-scheduled missions for this side and turn, so every existing scenario and
   policy stays byte-identical and `ScriptedPolicy` needs no change.
4. Wire the staff air seat (today scripted, per CLAUDE.md).

## DEFERRED, WITH THE REASON

**Ordered CAP is blocked on SEQUENCING, not on a missing rule.** [40.21] puts CAP in the mission
column and [40.3] names why a player would decline it, so the engine's always-on superiority
abstraction is unfaithful -- exactly as its own docstring at engine.py:2679 already argues against
itself. But [40.27] puts interception on the **path of flight**, between both sides' missions being
placed and either resolving, and `_air_support` runs inside **each side's** Combat Segment
(engine.py:6369) -- so the two sides' missions are never on the map simultaneously. Ordered CAP
needs the Land Support Air Phase lifted out of `_combat` and run once per OpStage for both sides,
per the [33] Sequence of Play IV.F. That is a real restructuring and it is its own slice.

## THE BIGGER PORT GAP THIS UNCOVERED

The [39.5] Aircraft Mission Summary was transcribed off the scan at PDF p.101 -- **neither OCR
corpus had located it as a chart.** The engine's seven kinds (strike, fort, port, airfield, dump,
trucks, recon) are the **bombing half only**. Not implemented: CAP (offensive/defensive), Scramble,
Strafing (8 target types), Fighter Flak Suppression, Flak Destruction (41.33), Mining Harbors
(41.39A), Bombing Ships (41.34), Bombing Railroad/Road (41.38), Torpedoes (41.7), all Night
missions (39.4), **Transport (42.3)** and **Airdrop (42.4)**.

**The largest single gap is the air-transport/airdrop channel, and it is a LOGISTICS channel.**
This project's keystone finding is that the campaign is governed by the last mile -- the Axis lands
12x what he can eat at the quay, and trucks are the binding constraint. **Air lift is a SECOND last
mile, and the engine models none of it.** Checked against the rules rather than assumed:

- **[42.31]** "Certain planes with transport capability may transport personnel or supplies by air.
  The cargo capacity of each transport is listed on the Aircraft Characteristics Chart in terms of
  TOE Strength Points or **tons of supplies**." So the capacity numbers are charted, and this
  project already holds per-aircraft data in `data/logistics_rates.json`.
- **[42.35]** transported supplies "cannot be used directly 'off the plane'. They must be
  distributed in the Organization Phase first" -- but **[42.46]** airdropped **ammunition and
  stores** "may be used **as soon as they arrive**", and "may be airdropped into a Friendly-occupied
  hex **even if it is in an Enemy Zone of Control**", with no recognizable-land-feature requirement
  in that case.

That last clause is an **airborne resupply of a besieged garrison**, usable the turn it lands. It is
the historical picture, it is exactly the mechanic that bears on Tobruk, and it is a documented
bypass of the truck last mile that no measurement in this project has ever accounted for. It also
has real costs the book prints: [42.36] transports still require refitting, [42.48] caps a unit at
one drop per month (12 Operations Stages), and [42.43] bars drops into enemy-occupied hexes or
enemy ZOC and into major cities.

**THE CAPACITY DATA IS ALREADY TRANSCRIBED AND ENTIRELY UNUSED**, checked in
`data/logistics_rates.json -> aircraft_characteristics_4_44.aircraft[*].mission_capability.Transport`:
Bombay Mk. I `"1 or 10 tons"`, Valentia `"1/4 or 5 tons"` (both Commonwealth), S.M. 81 Pipistrello
`"1P or 2 1/2"` and Ca 309 Ghibli `"0 or 1/2"` (Italian); every other charted type prints `"-"`.
So the chart half of [42.31] is done -- what is missing is the mission, not the numbers. Note the
**ten-ton Bombay is COMMONWEALTH**, which points this channel at the side this project has
repeatedly measured as starved. Note also there is **no Ju 52 in the roster at all**: the file's own
comment says it transcribes every type the [34.6]/[59.3] initial air strengths actually field plus
three German types, so whether the Luftwaffe fields a transport arm here is a question for
`data/air_establishments.json`, not an omission to assume.

**Do not treat this as a footnote.** Measure it before ranking it.

(For the record, [42.37] is also the rule that reads "Exception: dead camels may be transported by
air. Live camels may not be transported by air." It is genuinely in the book.)

**Range is transcribed and unused.** Per-aircraft `range` for all 28 types and the [37.4] Air
Distance Chart are already in `data/logistics_rates.json`; the only consumer is the [42.1] transfer
test in `basing.py:260`. `AirMission` carries no origin, so no mission is range-gated -- a bomber
can be tasked at any hex on the map. Cheap to fix once missions have an origin.

Full transcription: `scratchpad/port/transcriptions/39-mission-assignment.md`.
