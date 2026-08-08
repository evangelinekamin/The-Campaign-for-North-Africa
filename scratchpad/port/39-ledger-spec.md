# [39.19] THE WITHIN-STAGE PLANE LEDGER -- EXACT SPECIFICATION

Spec pass, 2026-08-08, HEAD 46a5c9a. **READ-ONLY on `game/`, `data/`, `tests/`. No engine code was
changed.** Companion to `scratchpad/port/39-air-mission-handback.md` (the slice brief) and
`scratchpad/port/transcriptions/39-mission-assignment.md` (the transcription). This file specifies
only the ledger: what it holds, what writes it, where it is read, and what must NOT be built.

---

# 0. SUMMARY, INCLUDING THE ONE FINDING THAT CHANGES THE SHAPE OF THE BUILD

1. **The transcription's [39.19] quote is verbatim-correct.** Re-rendered off the scan at 300 and
   600 DPI. **Zero characters differ.** ([37.24], [39.2], [40.0], [40.24] and [41.16] were
   re-verified too; all verbatim. §1.)
2. **The ledger holds PLANES, not Air Points.** Settled in §2 on the book's noun and on an
   arithmetic property of the engine's own conversions: points→planes→points is *lossy and not
   idempotent* (`planes_flying` ceils, `points_of_planes` floors), so a points ledger drifts.
3. ⚠ **MEASURED, AND IT IS THE FINDING: the within-stage bound IS ALREADY ENFORCED TODAY -- BY THE
   WRONG RULE.** [38.31]'s refit ledger, not [39.19], is what stops a second mission in a stage. In
   `campaign(seed=4)` four Axis missions tasked into one Operations Stage produce
   `_air_points -> 548, 0, 0, 0`. The build is therefore **not** "add a missing bound"; it is
   "disentangle a bound that is riding on an unrelated rule's escape hatch". §3.
4. ⚠ **The hole is real and is PROVEN, but it is the escape hatch, not the arithmetic.** With
   `air.refit_modelled` False -- a *data* gap ([61.42]/[36.5]), not a law -- five missions in one
   stage each read the full **2,147 Air Points (all 184 bombers)**. §3.3.
5. **[39.2] needs NO exemption clause in the ledger.** [41.16] settles it: "two missions
   *simultaneously*", one flight, one target. A plane-sortie ledger is untouched by it. §5.
6. **[37.24]'s "nine planes" is not a magic number** -- it is the [35.23] Italian Squadriglia's
   **Ready** column, already on disk at `squadron_capacity_35_23.italian.ready = 9` and read by
   nothing. It is a genuine second bound and it is **out of scope**; building it at this grain would
   cap a 184-plane national pool at nine. §6.
7. **Acceptance criterion is falsifiable and cheap: every baseline in `tests/baselines.py` must
   stay byte-identical.** §8 proves the new gate is provably inert wherever [38.31] is modelled.

---

# 1. TASK 1 -- THE SCAN VERIFICATION

Rendered with `pdftoppm -r 300` and `-r 600` from `tmp/The Campaign for North Africa.pdf`, cropped
to the column, read glyph by glyph.

### [39.19] -- PDF p.56 (printed folio 9), column 1

> **[39.19]** Generally, a plane may fly only one mission per Operations Stage or Strategic Phase
> (with the exception of certain fighters and dive bombers; Case 39.2). A plane flying a mission in
> an Operations Stage may not fly in the Strategic Phase of that Game-Turn and vice versa.

**ZERO CHARACTERS DIFFER** from `39-mission-assignment.md` lines 141-143 and 238-240.

The one disputed glyph was re-checked at 600 DPI under maximum magnification. The transcription's
note 2 is **correct and is confirmed**: the book prints lower-case `vice`, and there are two specks
of scan noise -- one resting on the left arm of the `v`, one floating above the line -- which is
what the Mistral corpus read as a capital `V`. `docs/rules/39-missions.md` is right here and the
newer corpus is wrong. Nothing about the reading is ambiguous at 600 DPI.

### Cross-checks, all verbatim, all zero-difference

| Rule | PDF page / folio | column | status |
|---|---|---|---|
| [37.24] sortie ceiling | 54 / 7 | col 2 | verbatim, incl. `capability level` and `Case 33.23` |
| [39.2] Combined Missions | 56 / 9 | col 1 | verbatim |
| [40.0] General Rule | 56 / 9 | col 2 | verbatim -- "only one mission in an Operations Stage (three in one Game-Turn)" |
| [40.24] tail | 57 / 10 | col 1 | verbatim -- "a plane flying CAP may not fly any other mission in that Stage" |
| [41.16] | 58 / 11 | col 2 | verbatim, **new to this pass**, and it is the decisive one for §5 |

[41.16], read for the first time in this slice because it is what settles [39.2] (PDF p.58, col 2):

> **[41.16]** Certain planes may undertake two missions simultaneously (see Case 39.2) dive bombers
> may strafe and bomb the same target and fighters with bombload capacities may both strafe and bomb
> a target, if they have a "D" capability. *However*, fighter-bombers may *either* bomb *or*
> undertake a fighter mission; they do not have the capacity to undertake both types of missions at
> once. If a fighter-bomber is flying a bombing mission,it is considered to have a parenthesized
> TacAir Rating (unless it jettisons bombload).

(The missing colon after `(see Case 39.2)` and the missing space in `mission,it` are the book's own.)

---

# 2. TASK 2 -- THE UNIT. THE LEDGER HOLDS PLANES.

## 2.1 The ruling

**The ledger holds AEROPLANES, keyed by `air.squadron(side, arena, role)`, measured against
`basing.establishment(state, side, arena, role)`.** Four reasons, in decreasing order of force.

**(a) The book's noun is `plane`, in every case that binds.** [39.19] "a *plane* may fly only one
mission"; [39.11] "no *plane* may fly unless it has been assigned"; [39.12] "the mission that a
specific *plane* is undertaking"; [39.15] "no limit to the number of *planes*"; [40.0] "*Fighters*
may be assigned to only one mission"; [37.24] "no more than nine *planes* on a mission". A ledger in
Air Points would be a different rule from the one the book prints.

**(b) Air Points are not one currency, and are not conserved.** They are denominated in two
*different* charted ratings -- [34.13] TacAir for a fighter, [34.14] Bombload for a bomber
(`air.py:2451-2453` says so at the fuel bill). Worse, the round-trip is lossy **and asymmetric**:

* `roster.planes_flying` (roster.py:164) rounds **UP** -- "a mission flown by a fraction of an
  aeroplane is flown by an aeroplane".
* `roster.points_of_planes` (roster.py:187) rounds **DOWN** -- "so that a force cut to a number of
  planes never reads back as more Air Points than it left with".

So `points_of_planes(planes_flying(p)) != p` in general. A ledger that subtracted *points* per
mission and converted at the boundary would accumulate that drift across the three missions of a
stage; a ledger that holds the *plane count* converts exactly once, at the read, and cannot drift.

**(c) Every existing gate in `_air_points` is ALREADY plane-denominated internally.** Both of them
compute a plane count, then convert once on the way out:

```python
# basing.available_points (basing.py:584)   -- [43.11]/[43.12] + [39.19] Strategic half
left = max(0, establishment(...) - strategic_planes(...))          # PLANES
return min(points, air.points_of_planes(side, role, left))         # -> points, floored

# air.ready_points (air.py:747)             -- [38.31] refit
return min(points, air.points_of_planes(side, role, ready_planes(...)))   # PLANES -> points
```

The new gate must be the third instance of that identical shape, or it will not compose with them.

**(d) The precedent for the conversion exists and must be followed, not re-invented.** `_air_unfit`
(engine.py:2763) already bills [38.31] per sortie by converting the *flown* Air Points to a plane
count with `air.flying_planes` (air.py:767). Use the same call, at the same moment, on the same
argument.

## 2.2 What the ledger holds, exactly

```
key    : air.squadron(side, arena, role)      # "AXIS/LAND/strike" -- air.py:690
         the identical key GameState.air_unfit (38.31) and GameState.air_strategic (39.19's
         Game-Turn half) are already carried under, so the three ledgers speak one language
value  : int, the aeroplanes of that squadron that HAVE ALREADY FLOWN in this Operations Stage
absent : zero (same convention as air.unfit_planes / basing.strategic_planes)
```

## 2.3 How a POINTS-denominated resolver bills against a PLANE-denominated bound

Two directions, and each already has a working model in the file.

**READ (the cap), modelled exactly on `basing.available_points`:**

```python
left = max(0, basing.establishment(state, side, arena, role) - flown_this_stage)
return min(points, air.points_of_planes(side, role, left))
```

Flooring on the way out is what keeps a cap a cap -- `points_of_planes`'s own docstring argues this.

**WRITE (the decrement), modelled exactly on `_air_unfit`:**

```python
planes = air.flying_planes(state, side, arena, role, flown_points,
                           basing.establishment(state, side, arena, role))
```

`basing.establishment` -- **not** `air.squadron_planes` -- is the correct establishment, for the
reason `air.ready_planes`'s docstring already gives: rule 43 bases three quarters of the Axis bomber
force in the Mediterranean, and reading against the whole establishment would let the Sicilian
contingent act as a within-stage buffer for aeroplanes that are not in Africa.

## 2.4 ⚠ THE ONE PIECE OF DESIGN THIS SPEC INSISTS ON

**The [38.31] write and the [39.19] write must be ONE function computing the plane count ONCE.**

```python
def _air_sortie_flown(r, side, arena, role, points) -> None:
    """[38.31] + [39.19]: the aeroplanes that JUST FLEW, booked into both ledgers off ONE count."""
```

Two call sites that each convert points→planes are two chances to disagree about how many aeroplanes
left the ground, and the disagreement would be silent (§8's inertness proof depends on the two counts
being *equal*, not merely similar). The existing `fuel` closure in `_air_support` already calls
`_air_fuel` then `_air_unfit` back to back; this replaces the second call, and `_air_unfit` becomes
the private half of the new function. Note `_air_unfit` is not imported by any test (grep: no
`tests/` reference), so folding it is safe.

---

# 3. THE MEASURED STATE OF PLAY -- WHAT ACTUALLY HAPPENS TODAY

Every figure below was produced at HEAD with `rm -rf game/__pycache__ tests/__pycache__` and
`PYTHONDONTWRITEBYTECODE=1`.

## 3.1 The within-stage bound already binds in the campaign -- via [38.31], not [39.19]

`campaign(seed=4)`, `max_turns=1`, Game-Turn 1 with three extra Axis missions added alongside the
scheduled `port`, so four LAND missions share one Operations Stage. Instrumenting `_air_points`:

```
_air_points AXIS LAND/strike -> 548  | unfit=137 ready=47 est=184 turn=1 stage=1
_air_points AXIS LAND/strike -> 0    | unfit=184 ready=0  est=184 turn=1 stage=1
_air_points AXIS LAND/strike -> 0    | unfit=184 ready=0  est=184 turn=1 stage=1
_air_points AXIS LAND/strike -> 0    | unfit=184 ready=0  est=184 turn=1 stage=1
```

The first mission takes all 47 ready aeroplanes; the second, third and fourth get **nothing**. The
mechanism is the [38.31] chain: `_air_unfit` books the flown planes into `state.air_unfit` inside the
fuel callback, `_Run.emit` (engine.py:295) folds the event into `r.state` *immediately*, and the next
mission's `air.ready_points` reads `establishment - unfit`.

(The opening `unfit=137` is not a bug: `scenario._campaign_air_unfit` (scenario.py:1485) seeds
[59.32]'s printed muster -- 47 of the Axis's 184 bombers begin the campaign refitted.)

The ordering that makes this hold is `run()`'s stage loop: `_air_maintenance` is line **380**, at the
*top* of the stage, and `_air_support` runs at line **6327** inside `_combat`. **There is no refit
beat inside a stage**, so `unfit` is monotonically non-decreasing across a stage's missions. Measured
across all three stages of Game-Turn 1: refits at stage 2 (`refitted: 9`) and stage 3
(`refitted: 5`) precede that stage's sorties, never interleave with them.

## 3.2 Why that is nonetheless the wrong rule doing the job

[38.31] and [39.19] are two different rules that happen to coincide inside one Operations Stage:

| | [38.31] refit | [39.19] within-stage |
|---|---|---|
| what it forbids | flying **unrepaired** | flying **twice in a stage** |
| how it is released | a [38.37] die roll returns a percentage | the stage ends |
| clock | a persistent stock (`GameState.air_unfit`, never cleared at a stage boundary -- apply.py:612) | the Operations Stage |
| preconditions in the book | 38.36 needs a Stores Point and an SGSU | **none** |
| preconditions in the engine | `air.refit_modelled` **and** `role in _REFITTABLE_ROLES` | should be none |

The last row is the defect. **Two preconditions that belong to [38.31] are currently gating
[39.19].** Both are documented, deliberate, and about something else entirely:

* `air.refit_modelled` = `air.based_on_map` (air.py:430-446) is an escape hatch for two **data**
  gaps -- [36.5]'s off-map facilities and [61.42]'s untranscribed free Axis airfield. Its own
  docstring says grounding an air force "because a COUNTER was never transcribed would enshrine a
  data gap as a rule". Correct for refit; but it currently means **a missing counter switches off an
  allocation law**.
* `_REFITTABLE_ROLES = ("recon", "strike")` (engine.py:2721) excludes fighters for a *fuel-billing*
  reason argued at `_air_superiority`. Correct for refit; but the day CAP becomes an ordered mission
  (the deferred slice), fighters would fly with **no** [39.19] bound at all.

## 3.3 ⚠ THE HOLE, PROVEN

Same board, with `air.based_on_map(state, AXIS)` made False by reassigning the seeded
`AirFacility.side` -- i.e. the exact configuration the [36.5]/[61.42] hatch exists for -- and five
Axis missions tasked into Operations Stage 1:

```
AXIS refit_modelled now: False
AXIS _air_points calls in turn1/stage1:
  [('LAND','strike',2147), ('LAND','strike',2147), ('LAND','strike',2147),
   ('LAND','strike',2147), ('LAND','strike',2147)]
```

**2,147 Air Points is the entire Axis bomber establishment -- all 184 aeroplanes -- handed in full to
each of five missions in one Operations Stage.** The whole force flown five times over. Nothing
refuses it, nothing logs it. This is the owner's "flies its ENTIRE air force ten times over", and it
is reachable today by a data fix, never mind a Policy hook.

It does not bite at HEAD only because `rommels_arrival` and `siege_of_tobruk` seed `state.air = ()`
so `_air_support` returns at its first line, and `campaign` has both sides based on the map:

```
rommels_arrival  AXIS air=False refit_modelled=False | ALLIED air=False refit_modelled=True
siege_of_tobruk  AXIS air=False refit_modelled=False | ALLIED air=False refit_modelled=True
campaign         AXIS air=True  refit_modelled=True  | ALLIED air=True  refit_modelled=True
```

**Conclusion: [39.19] must be built as its own ledger with NO precondition of any kind.** It binds
every side, every arena, every role, every scenario. Where [38.31] is modelled it will be inert
(§8); where the hatch is open it is the only thing standing between a staff and its whole air force.

---

# 4. TASK 3 -- THE SEAM. THE FUEL CALLBACK IS RIGHT, AND HERE IS THE ARGUMENT.

**Yes. Book the decrement inside the `fuel` closure of `_air_support` (engine.py:2996-3002),
alongside the existing `_air_unfit` call, on the same `flown` argument.**

**(a) The rule's trigger word is FLY, and the callback is the engine's definition of flying.** [39.19]
"a plane may **fly** only one mission"; [38.31] "as soon as a plane **flies** any mission". Two rules,
one verb, one seam. The callback's own comment already states the property that makes it the right
one: "it is invoked exactly when a mission is really flown -- after every resolver's structural
refusal ... and never for a mission that was only tasked."

**(b) A mission merely TASKED must not consume planes, and the book agrees.** The resolvers' refusals
-- bombing a harbour your own side holds, a fort you hold, recon over a Major City -- are refusals to
*order*, and [39.31] defines an abort as cancelling "before any action is taken to complete that
mission". Those aeroplanes never left the ground.

**(c) A mission that finds an empty hex MUST consume planes, and the seam gets that right for free.**
[39.0]'s Note: players "assign missions 'blindly,' and only find out what target are present when the
planes arrive". `_air_strike`'s docstring already honours this. Placing the decrement anywhere
*before* the resolvers would break (b); placing it *after* the effect would break (c). The callback
is the only point that satisfies both.

**(d) It receives `flown`, not `committed`, and that is correct.** [38.24] refuels one plane at a
time, so a half-funded larder flies half the force. The unfuelled aeroplanes did not fly; [39.19]
does not bind them. Same argument as [38.31]'s, which is why the same argument is the same call.

**(e) Precedent over invention.** `_air_unfit` already hangs off this callback for the identical
reason. §2.4's single `_air_sortie_flown` makes them structurally one decision.

### ⚠ Two seam obligations to write down now, because they bite later

1. **[40.33]: a mission that produces no effect still flies.** "Even a failed Scramble means the
   planes have flown and they still must refuel and refit." When Scramble/CAP land, they **must**
   route through this same callback. A resolver that computes an effect without calling `fuel(...)`
   is a plane that flew for free -- in both ledgers.
2. **The write must be unconditional except on `points <= 0`.** `_air_unfit`'s three early returns
   (`points <= 0`, `role not in _REFITTABLE_ROLES`, `not refit_modelled`) are [38.31]'s. Only the
   first is [39.19]'s -- zero planes flew, so zero planes are booked.

---

# 5. TASK 4 -- [39.2]. THE LEDGER NEEDS NO EXEMPTION CLAUSE.

## 5.1 What [39.2] actually exempts

[39.19]'s parenthesis promises an exception for "certain fighters and dive bombers". [41.16] --
rendered off the scan for this pass (§1) -- says what it is in its first six words: **"Certain planes
may undertake two missions *simultaneously*."** [39.2] itself: a `D` plane "may strafe and bomb **the
same target** as a combined mission". The [39.5] chart's footnote repeats it: "certain planes may be
assigned two Land Support Missions in the same OpStage (See Combined Missions, Case 39.2 ...)".

**Two mission LABELS, ONE FLIGHT, ONE TARGET. Not two sorties.** The plane takes off once, burns one
[34.17] Fuel Consumption Rating ("all Fuel Points are consumed during a mission, regardless of the
type or distance"), and goes unfit once under [38.31].

**Therefore a ledger that counts AEROPLANES PUT IN THE AIR is untouched by [39.2] and needs no
exemption branch.** This is a direct consequence of §2's plane ruling -- a ledger denominated in
*missions* would have needed one; a ledger denominated in *planes* does not. Write it into the
ledger's docstring so nobody adds the branch back.

## 5.2 Precisely which aircraft it exempts

Those whose charted Mission Capability carries a `D` cell. The chart key, transcribed verbatim at
`aircraft_characteristics_4_44._comment_mission_capability`: "D = Strafe and/or any type of bombing
missions". [41.16] names the two classes: dive bombers, and fighters with bombload capacities.

Of the 28 transcribed rows in `data/logistics_rates.json`, **nine carry a D** and **eight can fly a
combined mission**:

| type | D | class | nation |
|---|---|---|---|
| Bf. 109E | `!` | fighter | german |
| Ju. 87B | `!` | dive_bomber | german |
| Fw. 200 C | `!` | bomber | german |
| He. 111 | `N` | bomber | german |
| Ju. 88D | `!` | bomber | german |
| Hs. 126 | `!` | reconnaissance | german |
| C.R. 32 | `!` | fighter | italian |
| Ba 65 | `!` | bomber | italian |
| *Lysander Mk. I* | `S` | reconnaissance | commonwealth |

The Lysander is the **exception to the exception**: the Commonwealth key defines `S` as "May only
Strafe, may not be assigned any bombing missions", so it holds the D column but is barred from the
bombing half and cannot fly a combined mission. Note the shape of the list: **every usable D row is
Axis.** (The remaining 19 transcribed rows print `-` in D. The chart is not fully transcribed -- the
P-40s, Spitfires, Wellingtons and Bf. 109F/G are still missing, per the file's own `_comment`.)

## 5.3 Can this engine express the exemption today? **NO. Three independent blockers.**

1. **Strafing does not exist.** [39.2] is a *strafe-and-bomb* rule and [40.5]/[40.6] strafing is
   unimplemented (`39-mission-assignment.md` §4). There is no strafe half for a combined mission to
   combine with. **[39.2] is unreachable, not merely unbuilt.**
2. **There is no individual plane to carry a `D`.** An `AirWing` is a hexless national
   `(side, arena, role)` pool of Air Points, not a roster ([34.72]). `air.mission_capable`
   (air.py:366) is explicit that it "is a pure data check: no engine path gates on it".
3. **[41.16]'s second half needs per-plane TacAir at mission time** -- a fighter-bomber flying a
   bombing mission "is considered to have a parenthesized TacAir Rating". The pooled AirWing has one
   averaged rating per role.

**FLAGGED.** All three dissolve at [34.72], the same blocker `air.refuel`'s pooled larder,
`_refit_stores_dump`'s locality defect and [34.11] range-checking all wait on. Until then, the
ledger's correct treatment of [39.2] is *silence with a docstring* -- and, as §5.1 shows, that
silence is not a proxy: it is the right answer.

### And the parenthesis's other half is already built

[39.19]'s "certain fighters" also points at the fighter arm generally, which sits outside
`_REFITTABLE_ROLES`. That exclusion is [38.31]'s, not [39.19]'s. Per §4's obligation 2, the new
ledger must **not** inherit it -- fighters must be counted the day a fighter flies anything.

---

# 6. TASK 5 -- [37.24]. A SECOND BOUND, NOT COVERED, AND OUT OF SCOPE.

## 6.1 Verbatim off the scan (PDF p.54, folio 7, col 2)

> **[37.24]** No planes may fly in excess of the air facility's capability level. Moreover, no planes
> may fly in excess of an SGSU's ready capacity (see Case 33.23). Thus, if there are five SGSU's on
> an airfield, but the capacity level of that airfield has been reduced to two, only two of those
> SGSU's may refit and ready their planes (thus enabling them to fly). The other three squadrons are
> forced to remain inactive because of the reduced field capacity. Likewise, an Italian squadron (for
> example) could send no more than nine planes on a mission, regardless of how many planes it has
> ready (as reserves).

Zero characters differ from `39-mission-assignment.md` §2.

## 6.2 ⚠ NEW FINDING: "nine planes" is not a magic number. It is the [35.23] READY column.

`data/logistics_rates.json`, `squadron_capacity_35_23`:

```
italian                    ready  9   reserve 3   total 12
german                     ready 12   reserve 4   total 16
commonwealth_1940_june_41  ready 15   reserve 5   total 20
commonwealth_july_41_43    ready 18   reserve 6   total 24
```

**The Italian Squadriglia's Ready column is exactly 9.** So 37.24's example sentence is a worked
instance of "an SGSU's ready capacity", and this **independently confirms the transcription's flag
that `Case 33.23` is a misprint for 35.23** -- 33.23 is a Sequence-of-Play segment and has no such
number; 35.23 has precisely it. That is now two pieces of evidence for the misprint, and the errata
key the transcription's owner-ruling 4 asks for is justified whenever anything reads the cell.

## 6.3 Is it covered? **No, and the two halves diverge.**

* **Field Capacity Level + SGSU eligibility: partly built, for REFIT only.** `air.may_refit`,
  `air.able_sgsus` (air.py:707) and `basing.facility_planes` implement the first three sentences as a
  gate on *refitting*, which is what those sentences are literally about ("only two of those SGSU's
  may **refit and ready** their planes"). They are not applied as a *sortie* ceiling.
* **The per-mission plane cap: NOT built, and the cell it needs is read by nothing.**
  `air.squadron_capacity` (air.py:656) returns `["total"]` -- 12 / 16 / 20 / 24 -- for [38.33]'s
  refit capacity. **Nothing in `game/` reads `["ready"]`.** Measured in the campaign trace: the
  Italian refit event carries `'attempting': 12`, i.e. `total`.

## 6.4 Ruling: OUT OF SCOPE, and it must not be built at this grain

It is a genuinely *different* bound from [39.19] -- per-**squadron** per-**mission**, where [39.19] is
per-**plane** per-**stage** -- so honouring one does not honour the other.

But at this engine's grain **a "squadron" IS the national `(side, arena, role)` pool** of 184
aeroplanes (`air.py:690`, and the block comment above `REFIT_TABLE` says so in full). Applying a
nine-plane per-mission cap to that object would cap the entire Regia Aeronautica's contribution to
any mission at nine aircraft. That is not transcribing the book's number; it is applying a
Squadriglia's number to an air force. **It would be an invention wearing a citation.**

This is `39-mission-assignment.md`'s owner ruling 3, and it stands. Blocked on [34.72]. **Do not
build it, and do not let its absence block the [39.19] ledger** -- the two are independent, and
[39.19] is the one that stops a staff flying its air force twice.

---

# 7. TASK 6 -- THE EXACT `_OpStageLedger` USAGE

## 7.1 Declaration, in `_Run.__init__` (engine.py, beside `self.port_tons` at line 229)

```python
# [39.19] "GENERALLY, A PLANE MAY FLY ONLY ONE MISSION PER OPERATIONS STAGE OR STRATEGIC PHASE."
# The aeroplanes of each squadron that have already flown a LAND mission this Operations Stage,
# keyed air.squadron(side, arena, role) -> planes. Written ONLY by the fuel callback in
# _air_support, i.e. only when a mission is really flown; read by _air_points as its last gate.
# An _OpStageLedger, so a caller that drives the Operations Stages itself -- a test, a measurement
# driver, one of run()'s own Game-Turn beats -- cannot inherit a spent one.
self.air_flown = _OpStageLedger(self, dict)
```

`dict` as the empty factory, exactly like `self.port_tons` (engine.py:229). Every read and write goes
through `.current` and nowhere else -- that is the class's "ONE DOOR" property, and it is what makes
reads expire with writes.

## 7.2 ⚠ WHY THIS IS A SECOND LEDGER AND NOT AN EXTENSION OF AN EXISTING ONE

The `_OpStageLedger` docstring's closing warning -- "A LEDGER WHOSE FACTS MUST AGREE ABOUT WHICH STAGE
THEY DESCRIBE HOLDS THEM IN ONE VALUE ... two ledgers are two stamps, and two stamps can disagree"
-- is a rule about facts sharing **one clock**. It does not apply across clocks, and all three air
ledgers run on different ones:

| ledger | rule | clock | cleared by | where it lives |
|---|---|---|---|---|
| `state.air_strategic` | [39.19] Strategic-vs-Operations half | **Game-Turn** | `TURN_ADVANCED` (apply.py:811) | event-sourced |
| `state.air_unfit` | [38.31] refit | **none** (a stock; a die roll returns it) | never at a boundary (apply.py:612) | event-sourced |
| **`r.air_flown`** | **[39.19] within-stage half** | **Operations Stage** | its own `(turn, stage)` stamp | run-scoped |

`basing.strategic_planes` (basing.py:547) says the same from its side: "the ledger is cleared at the
Game-Turn boundary (39.19 is a per-GAME-TURN exclusion, not a per-Operations-Stage one)". **Do not
unify them.** Folding the within-stage count into `air_strategic` would make a plane that flew in
Operations Stage 1 ineligible for Stages 2 and 3, which [40.0] forbids in as many words: "only one
mission in an Operations Stage (**three in one Game-Turn**)".

## 7.3 Run-scoped, not event-sourced -- with one consequence flagged

Run-scoped is right: a within-stage fact never needs to survive the stage, and a `GameState` field
would need an apply handler, an invariant, and a reset at `STAGE_ADVANCED` -- the exact reset-in-the-
loop pattern `_OpStageLedger` exists to abolish (engine.py:96-104, three shipped bugs).

⚠ **BUT: `game/observation.py` reads `GameState`, so a run-scoped ledger is INVISIBLE to a staff
seat.** When `Policy.air_missions()` lands, an Air Marshal will task missions without being able to
see how many aeroplanes it has left this stage, and will have them silently zeroed.
**RECOMMENDATION (flagged, for the hook slice, not this one):** put `remaining_planes` in the
`ORDER_REJECTED` payload for an overdrawn mission. `llm_policy.py:128` already feeds `ORDER_REJECTED`
back to the model, so the seat learns from the refusal. That is cheaper and more faithful than
promoting the ledger to state -- the book's own player learns the same way, by writing his mission
column and running out of rows.

## 7.4 The read gate, in `_air_points`

```python
def _air_points(r: _Run, side: Side, arena: str, role: str) -> int:
    ...
    points = basing.available_points(state, side, arena, role, total)  # 43.11/43.12 + 39.19 GT half
    points = int(points * scale)                                       # 40/45/46 loser-scale
    if role in _REFITTABLE_ROLES:                                      # 38.31 refit cap
        points = air.ready_points(state, side, arena, role, points,
                                  basing.establishment(state, side, arena, role))
    return _stage_available(r, side, arena, role, points)              # 39.19 WITHIN-STAGE -- LAST,
                                                                       # and gated by NOTHING
```

Four decisions embedded here, each deliberate:

1. **LAST, below the `_REFITTABLE_ROLES` early return.** The current `if role not in
   _REFITTABLE_ROLES: return points` must become a non-returning `if`, or the new gate is skipped for
   exactly the arm (fighters) that will need it most. Placing it last is also what makes it
   *provably* inert on the campaign (§8) -- placed earlier, inertness is merely probable.
2. **`min` composition, not subtraction.** A plane that flew this stage is in *both* `air_unfit` and
   `air_flown`. Taking the smaller of two plane-denominated caps over the same establishment is
   idempotent; subtracting both would double-charge it.
3. **Signature change `state` -> `r`.** Mechanical: all seven call sites (engine.py 3046, 3097, 3137,
   3199, 3304, 3368, 3396) already pass `r.state`, and all seven sit inside resolvers that hold `r`.
   Grep confirms **no test and no script calls `_air_points`** (`tests/test_air_fuel.py:104` is a test
   *name* about roster conversion, not a call). `_air_points` stops being a pure function of state,
   joining `_air_unfit` / `_air_fuel`; its docstring's "THREE gates, IN THIS ORDER" must become four.
4. **No `arena` special-casing.** The key carries the arena, so a future Mediterranean-arena land
   mission books itself separately and correctly. Only `_air_support`'s callback writes it, and
   `_air_support` is an Operations-Stage beat, so the Strategic-Phase Malta raid can never touch it.

## 7.5 The two helpers

```python
def _stage_available(r, side, arena, role, points) -> int:
    """[39.19] `points` capped by the aeroplanes of this squadron that have NOT yet flown this
    Operations Stage -- "generally, a plane may fly only one mission per Operations Stage or
    Strategic Phase" -- read back out in the rating those Air Points are denominated in
    (34.13 TacAir / 34.14 Bombload), the same conversion basing.available_points and
    air.ready_points make for the same reason.

    GATED BY NOTHING, and that is the point: 38.31's refit ledger enforces this bound today as a
    SIDE EFFECT, but only where air.refit_modelled is true and only for _REFITTABLE_ROLES -- two
    preconditions that belong to rule 38 and to a DATA gap ([36.5]/[61.42]), not to rule 39. With
    the hatch open, measured at HEAD, five missions in one Operations Stage each drew the whole
    2,147-point Axis bomber establishment. 39.19 has no preconditions in the book and has none here.

    39.2 NEEDS NO EXEMPTION HERE. Its "two missions" are two mission LABELS on ONE FLIGHT at ONE
    target -- 41.16 "certain planes may undertake two missions SIMULTANEOUSLY" -- so a ledger that
    counts AEROPLANES PUT IN THE AIR already prices it correctly at one. Do not add a branch."""
```

```python
def _air_sortie_flown(r, side, arena, role, points) -> None:
    """[38.31] + [39.19]: the aeroplanes that JUST FLEW. ONE plane count, TWO ledgers -- 38.31's
    persistent readiness stock (GameState.air_unfit, via AIR_SQUADRON_UNFIT) and 39.19's
    within-stage commitment (r.air_flown) -- because two conversions are two chances to disagree
    about how many aeroplanes left the ground, and the disagreement would be silent."""
```

---

# 8. ACCEPTANCE CRITERIA -- AND A PROOF THAT THE CAMPAIGN CANNOT MOVE

## 8.1 The inertness proof

Let `E = basing.establishment(state, side, arena, role)`, `U` = `air.unfit_planes(...)`, `F` =
`r.air_flown.current` for the same key. Within one Operations Stage:

* `F` starts at 0 and `U` starts at some `S >= 0` (the [59.32] seeding).
* Every write adds **the same count** `n = air.flying_planes(..., flown, E)` to both (§2.4's single
  function is what guarantees "the same").
* Therefore at every read, `U = S + sum(n) >= sum(n) = F`.
* `points_of_planes` is monotone non-decreasing in its count, so
  `points_of_planes(E - U) <= points_of_planes(E - F)`.
* The refit gate has already applied `min(points, points_of_planes(E - U))`, so the value entering
  `_stage_available` is already `<= points_of_planes(E - F)`, and the new `min` **returns it
  unchanged.**

**Wherever `air.refit_modelled` is true and `role in _REFITTABLE_ROLES`, the new gate is provably a
no-op.** That is every mission on every board that has air today.

## 8.2 The predictions, in falsifiable form

1. **All six signatures in `tests/baselines.py` stay byte-identical.** Both benchmark scenarios seed
   `state.air = ()` so `_air_support` returns at line 1; the campaign boards are covered by §8.1.
   *If any baseline moves, §8.1 is violated and the two ledgers are booking different counts --
   fix that, do not re-baseline.*
2. **`campaign(seed=4)` with four Axis missions in one stage still reads `548, 0, 0, 0`** (§3.1),
   now for two independent reasons instead of one.
3. **With `refit_modelled` False, five missions in one stage no longer read `2147` five times.** This
   is the test that must be written FIRST and must FAIL at HEAD -- §3.3 is the reproduction, and
   `replace(f, side=...)` over `state.air_facilities` is the whole fixture.

## 8.3 Tests to write, RED first

* **The hole, pinned.** Predication 3 above. This is the only test that fails at HEAD; write it
  first, watch it fail, then build.
* **The clock.** Two missions in Operations Stage 1 exhaust the squadron; a mission in Operations
  Stage 2 flies again after `_air_maintenance` -- [40.0]'s "three in one Game-Turn".
* **Self-expiry.** Drive the stages by hand (the idiom `tests/test_ports.py:312` and
  `tests/test_campaign_lifeline.py:278` already use) and assert the ledger does not leak across a
  `(turn, stage)` boundary. This is the failure `_OpStageLedger` exists for and it shipped twice.
* **The whitelist.** §9.
* ⚠ **Watch for a test that ENSHRINES the coupling.** Any existing air test that asserts a second
  mission gets zero is currently asserting **[38.31]**, not [39.19]. If one is found, it must be
  restated to say which rule it is testing, with a dated reason -- not deleted, and not left
  ambiguous. `tests/test_air_fuel.py` and `tests/test_air_bombing.py` are where to look.

---

# 9. DEFECT 2 -- THE MISSION-KIND WHITELIST

`_air_support`'s dispatch (engine.py:3004-3017) is a bare `if/elif` chain with **no `else`**, so an
unrecognised `kind` is silently dropped: no event, no refusal, no invariant.

## 9.1 The fix, and it needs no new vocabulary

Add an `else` that emits `ORDER_REJECTED` and `continue`s. **Do not add a separate frozenset**: a
whitelist held apart from the dispatch is a second source of truth that can drift, which is the very
defect being fixed. The chain's own branches ARE the vocabulary; the `else` is the boundary.

```python
else:                                    # 39.1: "no plane may fly unless it has been assigned a
    r.emit(EventKind.ORDER_REJECTED, side, f"{side.value}/Air",   # SPECIFIC mission"
           {"reason": "unknown air mission kind", "kind": m.kind,
            "target": _payload_target(m.target)})
    continue
```

## 9.2 Placement: FIRST in the loop body, before the weather test

The [29.43]/[29.52] grounding `continue` (engine.py:2976) must come *after* the kind check. An
unknown kind is not a mission at all; grounding it for weather would hide an order error behind a
sandstorm, and the rejection would appear or not appear depending on the sky.

## 9.3 Ruling: `ORDER_REJECTED` at the boundary, and **NO invariant**

`39-mission-assignment.md` §9.3 asks for "a mission-kind whitelist in `apply`/`invariants`. **This
spec rules against the `invariants` half.** `game/invariants.py` "must never raise -- a violation
means a rule is misencoded" (CLAUDE.md). A policy's bad order is not a misencoded rule; it is
untrusted input, and this engine rejects untrusted input at the boundary with `ORDER_REJECTED` --
which is what every other hook does (engine.py 4380, 4469, 4765, 5058, 5213, 5494, 5652, 6134, 6348,
7006). Crashing the fold on a staff's typo would be the wrong failure mode. One rejection path serves
both a bad policy order and a bad scenario seed, and both are loud in the log.

## 9.4 No baseline moves

engine.py:3505 warns that `ORDER_REJECTED` payloads are hashed into both benchmark signatures. This
branch fires only for a kind no scenario produces, so it emits nothing on any pinned board.

## 9.5 And fix the docstring drift while here

`state.AirMission` (state.py:476) documents **four** kinds -- strike/fort/port/recon -- and its
`kind` field comment repeats the four. The engine dispatches **seven**: `strike`, `fort`, `port`,
`airfield`, `dump`, `trucks`, `recon`. Restate the docstring to all seven, naming
`_air_facility_bomb` [41.36], `_air_dump_bomb` [41.35] and `_air_truck_bomb` [41.32]. Its "A static
schedule now, replaced by the Air Marshal seat's live orders later (P5 Step 6)" stays true until the
hook lands.

---

# 10. DEFECT 3 -- RANGE. NOT A BLOCKER FOR THE LEDGER. A LIVE EXPLOIT AT HOOK-OPEN.

**Answer to the task's question: the ledger can and should be built without a range gate, and the
hook can be opened without one -- but not safely, and the reason is new to the hook, not to the
ledger.**

* **[39.19] is a commitment rule with no geometry in it.** It counts aeroplanes; [34.11]/[37.21]
  range is a legality test on a flight that has an origin. They are orthogonal, and the ledger is
  correct with or without range.
* **The data is entirely on disk.** Per-aircraft `range` for all 28 transcribed types
  (`aircraft_characteristics_4_44.aircraft.<type>.range`) and the whole [37.4] Air Distance Chart
  (`air_distance_37_4`). The only consumer of either is `basing.transfer_range` (basing.py:260) for
  the [42.1] transfer test.
* **What is missing is an ORIGIN, not a number.** `AirMission` (state.py:476) carries
  `side / kind / target / turn` and no base; an `AirWing` is a hexless national pool. This is the
  same [34.72] blocker as `air.refuel`'s pooled larder (measured: a Stuka fuelled 38 hexes away, past
  its own charted Range of 36) and `_refit_stores_dump`'s locality defect.
* ⚠ **THE EXPOSURE IS NEW AT HOOK-OPEN, AND IT IS WORTH SAYING PLAINLY.** Today the static schedule
  only ever targets `PORT-Tobruk`, so rangelessness is invisible. The moment `Policy.air_missions()`
  lands, a staff can task a Stuka at any hex on the map from nowhere in particular -- Alexandria,
  Cairo, the far edge of the [37.4] chart. That is a *bigger* exploit than the one this ledger
  closes, and it is created by the hook, not by the ledger.

**RECOMMENDATION, FLAGGED, NOT BUILT:** the range gate and the hook should ship in the same slice, or
the hook should open range-gated on owner ruling 6's nearest-held-facility proxy (`state.air_facilities`
+ `basing.facility_planes` make it available today, and it is the conservative reading). **This slice
must not build it** -- it was not scoped, it needs an owner ruling on the origin, and building it
silently would be exactly the invention this port forbids.

---

# 11. WHAT THIS SLICE DOES NOT TOUCH

* **`Policy.air_missions()`** -- the hook. The ledger lands first and proves it bounds the fleet.
* **Ordered CAP / Scramble** -- blocked on sequencing ([40.27] interception is on the path of flight;
  `_air_support` runs inside each side's own Combat Segment, engine.py:6327), not on a missing rule.
  See the brief's "DEFERRED, WITH THE REASON".
* **[37.24]'s nine-plane per-mission cap** -- §6.4. Blocked on [34.72].
* **[39.2] combined missions** -- §5.3. Unreachable until strafing exists.
* **Range** -- §10.
* **`_air_superiority`'s always-on abstraction and `AIR_SUPERIORITY_LOSER_SCALE`** -- untouched. The
  new gate sits below the scale and does not interact with it.

---

# 12. FLAGS AND OWNER RULINGS RAISED BY THIS SPEC

1. ⚠ **A data escape hatch is currently switching off an allocation law.** `air.refit_modelled` =
   `air.based_on_map` exists for two untranscribed data gaps ([36.5], [61.42]). Because [38.31] is
   the only thing enforcing [39.19]'s within-stage half, that hatch removes the sortie bound
   entirely (§3.3, measured). The fix is this ledger. **The hatch itself is correct and stays** -- it
   is right for refit; it was never meant to gate rule 39.
2. ⚠ **`_REFITTABLE_ROLES` is a fuel-billing decision that is silently doing allocation work.** The
   day CAP becomes an ordered mission, fighters would fly with no [39.19] bound. The new ledger must
   not inherit the exclusion (§4 obligation 2).
3. **[37.24]'s `Case 33.23` is a misprint for 35.23 -- now confirmed twice.** The transcription
   argued it from the section numbering; §6.2 confirms it arithmetically (the Italian `ready` cell
   *is* 9). Wants a named errata key of the [54.17] kind whenever anything reads `["ready"]`.
4. **`squadron_capacity_35_23.*.ready` is transcribed and read by nothing.** Recorded so the [34.72]
   slice does not re-transcribe it.
5. **Run-scoped ledger => invisible to `observation.py`.** §7.3. Recommendation: `remaining_planes`
   in the `ORDER_REJECTED` payload when the hook lands. Owner's call on whether that is enough or
   the ledger should later be promoted to `GameState`.
6. **This spec rules against `39-mission-assignment.md` §9.3's `invariants` whitelist.** §9.3.
   Rejection at the boundary, not a fold-time raise. Flagged because it overrides a prior document.
7. **The [39.5] chart's own two defects stand as recorded** (`Flak Suppresiion` listed as a strafing
   target where [40.7] makes it a mission; [41.32] `B-TC` missing from the Bombing list). Neither
   touches this slice; both need named errata keys if the chart is ever transcribed to `data/`.
