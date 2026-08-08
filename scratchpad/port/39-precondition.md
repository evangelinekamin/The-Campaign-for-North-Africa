# [39.19] PRECONDITION — measured at HEAD 46a5c9a, 2026-08-08

**READ-ONLY on `game/`, `data/`, `tests/`. No engine code was written.** Everything below is a
number off a real fold, or a `file:line` off HEAD. Prior work: `scratchpad/port/transcriptions/39-mission-assignment.md`
(the rule transcription — this file does not repeat it, it measures against it).

## Provenance

| What | How |
|---|---|
| Q1 / Q2 | `scratchpad/39-precondition/probe_39.py --mode instrumented`, seeds 1941 / 7 / 2026, **full 111-Game-Turn `campaign(seed)`** (no `max_turns` override), `CampaignAxisPolicy` vs `CampaignCommonwealthPolicy`. `_air_support` / `_air_points` / `_air_fuel` wrapped with delegating recorders. |
| instrumentation validity | `--mode control` (no wrappers) on seeds 1941 and 7: signature sha256 **identical** to the instrumented run. The recorders move no die. |
| Q3 | `--mode hooked`, seeds 1941 and 7, full campaign. |
| Q4 | `probe_kinds.py` — scenario census + the ten air-touching test files run in-process (`-n 0`) under resolver counters. `pytest_rc = 0`. |
| Q5 | `probe_39.py --mode q5`. |
| the crux | `probe_ledger.py` — four minimal single-stage folds. |
| [39.19] text | **re-rendered myself**, `pdftoppm -r 300 -f 56 -l 56`, PDF p. 56 col. 1 → `scratchpad/39-precondition/scan/p56_c1_top.png`, read at 2× zoom. |

Costs: one full-campaign fold is **347 s**; the seven folds above were run in parallel.

> **[39.19]** "Generally, a plane may fly only one mission per Operations Stage or Strategic Phase
> (with the exception of certain fighters and dive bombers; Case 39.2). A plane flying a mission in
> an Operations Stage may not fly in the Strategic Phase of that Game-Turn and vice versa."
> — verbatim, my own 300-DPI render of PDF p. 56 col. 1. `docs/rules/`'s lower-case `vice` is right;
> the speck above the glyph that Mistral read as a capital is scan noise, visible in the crop.

---

# THE HEADLINE

**A correct [39.19] within-stage ledger binds NOTHING today. The slice is a pure prerequisite and
must land byte-identical.** Every one of the 1,998 `_air_support` invocations across three full
campaigns tasked **exactly one** mission, and **no Operations Stage on any seed ever drew
`_air_points` more than once** (`max_draws_in_one_stage = 1`, all three seeds).

---

# 1. THE CRUX, SETTLED IN WRITING: THE LEDGER IS KEPT IN **PLANES**

The book binds planes and says so four times ([39.11], [39.12], [39.15], [39.16] — all quoted in the
transcription). `_air_points` returns Air Points. The conversions already exist and the campaign's
own pools convert exactly:

| wing | role | pool (Air Points) | `air.planes_flying` | back via `air.points_of_planes` | pts/plane |
|---|---|---|---|---|---|
| RA-land (AXIS) | strike | 2147 | **184** | 2147 ✔ | 11 |
| DAF-land (ALLIED) | strike | 382 | **56** | 382 ✔ | 6 |
| RA-land (AXIS) | recon | 75 | 75 | 75 ✔ | 1 |
| DAF-land (ALLIED) | recon | 32 | 32 | 32 ✔ | 1 |

**Ruling: keep the ledger in PLANES.** It is the book's unit, `_air_unfit` (`engine.py:2763`)
already does exactly this conversion for the [38.31] bill, and the full pools round-trip losslessly,
so the boundary case that matters for byte-identity is exact.

## ⚠ AND ONE MEASURED LANDMINE THE BUILDER MUST NOT STEP ON

**The points↔planes conversion is LOSSY IN BOTH DIRECTIONS AND ROUNDS OUTWARD.** `planes_flying`
rounds **up** ("a mission flown by a fraction of a plane is flown by a plane", `air.py:396`);
`points_of_planes` rounds **down** (`air.py`). Measured over points 0–399 plus the four pool values,
for both sides and both roles: **711 of 1616 values do not round-trip.** For Axis strike, *every*
value in 1..10 inflates to 11.

So a ledger that **re-derives** a mission's Air Points from its remaining plane count will inflate
every partial commitment and move the signature even in a one-mission stage. The only safe shape is
the one `air.ready_points` (`air.py:747`) already uses and is the reason it is safe today:

```python
return min(points, points_of_planes(side, role, <uncommitted planes>))
```

**Cap the points asked for. Never recompute them.**

---

# 2. Q1 — HOW MANY MISSIONS ACTUALLY FLY PER OPERATIONS STAGE (full 111-GT campaign)

`_air_support` is called at `engine.py:6327`, at the head of `_combat`, once per side per Operations
Stage. 111 GT × 3 OpStages = **333 invocations per side**, on every seed.

`due` (`engine.py:2975`) filters on **turn only, not stage**, so the campaign's one mission per side
per Game-Turn (`scenario.py:1518`) is re-tasked in all three Operations Stages of that turn.

| | seed 1941 | seed 7 | seed 2026 |
|---|---|---|---|
| `_air_support` invocations | 666 (333/side) | 666 | 666 |
| missions tasked per invocation | **always exactly 1** | **always 1** | **always 1** |
| ...of which grounded ([29.43]/[29.52]) | 40/side | 28/side | 41/side |
| **AXIS missions that FLEW** | **0** | **0** | **0** |
| ALLIED missions that FLEW | 160 | 189 | 246 |
| ALLIED refused after the points draw | 133 | 116 | 46 |
| AXIS refused after the points draw | 293 | 305 | 292 |

**The Axis never bombs, on any seed, in 111 Game-Turns.** `holder_census` shows the Tobruk port hex
under `Side.AXIS` control in all 333 stages of all three campaigns, so `_air_port`'s "never bomb your
OWN harbour" (`engine.py:3145`) refuses the Axis every single stage. The symmetric schedule works
exactly as `_campaign_air_missions` documents — but the roles never hand off on these seeds, so the
whole Axis air-support channel is a 111-turn no-op that draws its pool and throws it away.

**Verdict: at most one mission per Operations Stage per side, and in practice at most one per
OpStage in the whole war.** A [39.19] ledger has nothing to refuse. **The slice must land
byte-identical, and that is a testable acceptance criterion, not a hope.**

---

# 3. Q2 — WHAT THE SEVEN `_air_points` CALL SITES ACTUALLY DRAW

The seven sites (`engine.py` 3046, 3097, 3137, 3199, 3304, 3368, 3396) are six `strike` and one
`recon`. **In a real campaign fold only ONE of the seven is ever reached: `_air_port` (3137).** The
other six are dead in `campaign(seed)`, because the schedule only ever tasks `port`.

Committed points per draw, per side, per role (role is `strike` for every draw; `recon` is never
drawn because no recon mission is ever scheduled):

| seed | side | draws | min | median | mean | max | zero draws | total points drawn |
|---|---|---|---|---|---|---|---|---|
| 1941 | AXIS | 293 | 0 | 338 | 725.5 | **2147** | 83 | **212,571** |
| 1941 | ALLIED | 293 | 0 | 102 | 98.9 | 382 | 89 | 28,990 |
| 7 | AXIS | 305 | 0 | 781 | 867.1 | 2147 | 74 | 264,473 |
| 7 | ALLIED | 305 | 0 | 20 | 95.2 | 382 | 112 | 29,032 |
| 2026 | AXIS | 292 | 0 | 910 | 888.3 | 2147 | 79 | 259,378 |
| 2026 | ALLIED | 292 | 0 | 163 | 151.7 | 382 | 20 | 44,284 |

Every one of those Axis points is drawn and discarded at the holder check. And **`max` = 2147 is the
whole Regia Aeronautica LAND strike wing, 184 aeroplanes** — the number a second mission in the same
stage would draw again if the schedule ever carried one.

Committed → fuelled, for the missions that reached the [38.24] draw:

| seed | n | committed mean | flown mean | under-fuelled |
|---|---|---|---|---|
| 1941 | 160 | 147.9 | 135.8 | 12 |
| 7 | 189 | 151.2 | **11.4** | **174 of 189** |
| 2026 | 246 | 167.4 | 84.4 | 90 |

(Seed 7's Commonwealth air force is fuel-starved: 171 of 189 tasked sorties flew **zero** points.
Not this slice's business, but it is the same last-mile the faucet note names, and it means the
harbour bombing that seed is nearly inert.)

## Is `_air_points` really unbounded within a stage? Measured — it depends, and the dependency is an escape hatch

`probe_ledger.py`, four minimal single-stage folds, Axis wing = 6 strike Air Points:

| case | `air.refit_modelled` | missions | what each draw returned | total committed |
|---|---|---|---|---|
| A: 2 × strike | **False** | 2 | 6, 6 | **12 from a 6-point wing** |
| B: 2 × strike | True | 2 | 6, 0 | 6 |
| C: strike + recon | False | 2 | recon 3, strike 6 | 9 (two separate pools) |
| D: **5 × strike** | **False** | 5 | 6, 6, 6, 6, 6 | **30 from a 6-point wing — the air force flew five times over** |

So there **is** an accidental partial brake, and it is the wrong rule: [38.31]'s `air.ready_points`
(`air.py:747`). Because a mission commits the **whole** pool, `_air_unfit` marks the whole arm unfit
and the next mission in that stage draws 0. Confirmed in a real campaign fold too — `probe_multi.py`
adds five extra Axis strike missions per Game-Turn to `campaign(1941, max_turns=4)` and every
multi-draw stage reads `(X, X, 0, 0, 0, 0)`: one draw for the refused `port` mission (no flight → no
[38.31] bill), one for the first strike, then zeros.

**Three holes in that accidental brake, all measured:**

1. **It is off entirely wherever `air.refit_modelled` is False**, i.e. `air.based_on_map`
   (`air.py:430`) — the documented escape hatch for [61.42]/[36.5]. Measured:
   `siege_of_tobruk(port_bomb=True)` has **`refit_modelled(AXIS) = False`**. That is the one
   benchmark-family scenario that flies air missions, and its Axis has **no within-stage brake at
   all**. Only `campaign()` has both sides refit-modelled (55 seeded facilities).
2. **It excludes fighters.** `_REFITTABLE_ROLES = ("recon", "strike")` (`engine.py:2727`). The day
   CAP is an ordered mission there is no brake on the fighter arm whatsoever.
3. **It is all-or-nothing, not a split.** `AirMission` carries no plane/point count, so mission 1
   always takes 100% and mission 2 gets 0. [39.15] explicitly permits any number of planes on a
   mission and [39.16] permits splitting a squadron across missions — a commander who wants two
   simultaneous missions cannot express it. That is owner ruling 2 in the transcription and it is
   **unavoidable**: a `Policy.air_missions()` hook worth having needs a size field, and a size field
   needs the ledger.

---

# 4. Q3 — THE `Policy.air_missions()` DEFAULT IS BYTE-IDENTICAL. PROVEN.

The shadow `_air_support` in `probe_39.py` is a character-for-character copy of `engine.py:2960`'s
body with exactly **one** line changed:

```python
due = [m for m in r.state.air_missions if m.side == side and m.turn == r.state.turn]   # engine.py:2975
# becomes
due = hook(r.state, side)          # default: the same comprehension, in a Policy method
```

Full 111-Game-Turn campaigns, `determinism_signature` sha256:

| seed | control (HEAD) | hooked | events | identical |
|---|---|---|---|---|
| 1941 | `e98efd60…50a4d3` | `e98efd60…50a4d3` | 270,991 / 270,991 | **YES** |
| 7 | `95658f90…6c8a15d` | `95658f90…6c8a15d` | 256,790 / 256,790 | **YES** |

**The safety argument for opening the hook holds.** Proposed signature:

```python
def air_missions(self, state: GameState, side: Side) -> list[AirMission]:
    return [m for m in state.air_missions if m.side == side and m.turn == state.turn]
```

Two notes for the builder:
* The engine **sorts** what the hook returns (`key=lambda m: (m.kind, str(m.target))`,
  `engine.py:2976`). That sort must stay inside the engine, not inside the hook — it is what makes a
  policy's ordering non-load-bearing and therefore deterministic.
* `staff_policy._air_plan` (`staff_policy.py:647`) becomes the natural implementer. Today it reads
  the same schedule and stages it as a `STAFF_PROPOSAL` that nothing consumes — a seat narrating a
  decision it never makes. Returning that list *is* the fix, and it is a one-line change of
  direction, not new machinery.

---

# 5. Q4 — MISSION-KIND CENSUS

**Scheduled by scenarios:**

| scenario | kinds scheduled |
|---|---|
| `rommels_arrival(seed)` | none (`air_missions = ()`) |
| `siege_of_tobruk(seed)` default | none |
| `siege_of_tobruk(port_bomb=True)` | `port` × 12 |
| `campaign(seed)` | `port` × 222 |

**`port` is the only kind ever scheduled anywhere in `game/`.** `strike`, `fort`, `airfield`,
`dump`, `trucks` and `recon` — six of the seven implemented resolvers — are dead code in every
shipped scenario.

**Exercised by tests** (ten air-touching files, run in-process, `rc = 0`):

| kind | resolver | resolver calls | tasked *through `_air_support`* |
|---|---|---|---|
| port | `_air_port` | 1292 | 1440 |
| fort | `_air_fort` | 118 | 120 |
| strike | `_air_strike` | 87 | 93 |
| recon | `_air_recon` | 70 | 74 |
| dump | `_air_dump_bomb` | 8 | **1** |
| trucks | `_air_truck_bomb` | 8 | **1** |
| airfield | `_air_facility_bomb` | 6 | **1** |

**No resolver is completely unexercised** — so a whitelist cannot silently kill a kind that nothing
tests. But `dump`, `trucks` and `airfield` are each tasked as a real `AirMission` exactly **once** in
the whole suite (`tests/test_air_bombing.py:365` parametrised, `test_air_facilities.py:383`); their other
hits are tests calling the resolver directly. Those three are the thin ice. **A whitelist should be
built with a test that asserts the whitelist set equals the dispatch chain's set**, so the two can
never drift.

---

# 6. Q5 — THE BENCHMARK SCENARIOS CARRY NO AIR AT ALL

| scenario | `air` | `air_missions` |
|---|---|---|
| `rommels_arrival(1941)` | `()` | `()` |
| `siege_of_tobruk(1941)` (defaults) | `()` | `()` |
| `siege_of_tobruk(1941, port_bomb=True)` | 1 wing | 12 × `port` |
| `campaign(1941)` | 2 wings | 222 × `port` |

`_air_support` returns immediately on `if not r.state.air` (`engine.py:2973`), so **both benchmark
signatures are structurally immune to anything this slice does to the air channel** — no ledger, no
hook and no whitelist can reach them. `tests/test_air.py:514` already pins that ("the air-less
scenarios stay byte-identical"). The only signatures at risk are the campaign ones, and Q3 shows the
default hook does not move them.

---

# 7. THE OTHER TWO DEFECTS

## 7a. No mission-kind whitelist — CONFIRMED

`engine.py:3004–3017` is a bare `if/elif` chain with **no `else`**. An unknown `kind` is silently
dropped: no `ORDER_REJECTED`, no event, no invariant. `game/apply.py` and `game/invariants.py`
contain no `AirMission` kind check. Harmless while the only author is `scenario.py`; an
order-validation hole the moment a policy can author missions, and every other hook in this engine
emits `ORDER_REJECTED` at its boundary. **Build it in the same slice as the hook — it is the
boundary the hook creates.**

## 7b. Range is transcribed and unused — and it is NOT a blocker

Verified by grep at HEAD: the per-aircraft `range` (`data/logistics_rates.json`,
`aircraft_characteristics_4_44.*.range`, via `roster.range_per_plane`, `roster.py:216`) and the
[37.4] Air Distance Chart (`air_distance_37_4`, via `logistics_data.py:443`) have **exactly one**
consumer between them: the [42.1] transfer test, `basing.transfer_range` / `basing.transfer_distance`
(`basing.py:260`/`267`), called from `basing.py:364` ← `engine.py:2663`. Nothing else reads either.
`AirMission` (`state.py:476`) carries `side`/`kind`/`target`/`turn` and **no origin**, so
`_air_support` performs no range test.

**Report as asked: the hook CAN be opened without a range gate, and a range gate must NOT be built
in this slice.** Reasons:

1. A range gate is a *behaviour change*, not a prerequisite. It would refuse missions the engine
   flies today and move the campaign signature — the opposite of what this slice is for.
2. It is **not transcribable as it stands**. [34.11] measures from the squadron's field; an
   `AirWing` is a hexless national `(side, arena, role)` pool with no base. Any origin is an
   invention (owner ruling 6: nearest-held-facility is *available* and *conservative*, but it is a
   choice). Building it silently would be exactly the invention CLAUDE.md rule 1 forbids.
3. It is the same root cause as two defects already flagged in-tree — `_refit_stores_dump`
   (`engine.py:2780`) and `air.refuel` billing a Staffel to a dump 38 hexes away — and all three
   dissolve together when [34.72]'s Squadron Composition Sheet exists. **Range belongs to the
   basing slice, not the assignment slice.**

The honest consequence to record: **with the hook open and no range gate, a staff can task a bomber
at any hex on the map from nowhere in particular.** That is true *today* of the scenario schedule, so
the hook does not create the hole — but it does hand it to a model. Flag it in the hook's docstring
and put it on the [34.72] dependency list.

## 7c. `AirMission`'s docstring drift — CONFIRMED, fix it in this slice

`state.py:476–493` says `kind` is one of `"strike" | "fort" | "port" | "airfield" | "recon"` in the
prose and `"strike" | "fort" | "port" | "recon"` in the field comment. The engine dispatches
**seven** (`dump` and `trucks` are both missing from the prose, `airfield`/`dump`/`trucks` from the
comment). The same docstring says "A static schedule now, replaced by the Air Marshal seat's live
orders later (P5 Step 6)" — this slice is that step, so the sentence has to be rewritten anyway.

---

# 8. VERDICT FOR THE BUILDER

**This is a pure prerequisite slice and it must land byte-identical on `campaign()` for at least
seeds 1941 and 7 (control sha256s in §4), and structurally on both benchmarks (§6).**

Acceptance criteria, in order:

1. `Policy.air_missions(state, side)` with the §4 default. Byte-identity is *proven* for that exact
   default — do not "improve" it (no filtering, no sorting, no dedup) in the same slice.
2. A [39.19] commitment ledger **in planes**, per `(side, arena, role)` per Operations Stage, applied
   as `min(points_asked, points_of_planes(uncommitted_planes))` — **never** as a re-derivation
   (§1, the round-trip landmine). It refuses nothing today (§2), which is how you know it is right.
   Build it as an `_OpStageLedger` (`engine.py:84`); do not hand-roll a fourth stamp.
3. A mission-kind whitelist emitting `ORDER_REJECTED`, plus a test asserting the whitelist equals the
   dispatch chain (§5).
4. Fix `state.AirMission`'s docstring (§7c).

**Do NOT build in this slice:** ordered CAP (needs the Land Support Air Phase lifted out of `_combat`
per [33] IV.F — the brief's own deferral, and I confirm `_air_support` is still called inside
`_combat` at `engine.py:6327`), the range gate (§7b), a mission size field (needs an owner ruling),
or [39.2] combined missions (unreachable — strafing does not exist).

**The one thing that will surprise whoever builds it:** the [38.31] refit ledger is *already* acting
as an accidental within-stage brake in `campaign()` (§3), so a naive [39.19] ledger will look like it
does nothing there — and then the day someone tasks two missions in
`siege_of_tobruk(port_bomb=True)`, where `refit_modelled(AXIS)` is **False**, the real hole opens
(case D: five missions, thirty Air Points out of a six-point wing). **Test the ledger against a
refit-unmodelled side, or the test will pass for the wrong reason.**

---

## Artefacts

All under `scratchpad/39-precondition/`:
`probe_39.py` (Q1/Q2/Q3/Q5) · `probe_kinds.py` (Q4) · `probe_multi.py` (in-campaign counterfactual) ·
`probe_ledger.py` (the crux) · `out_*.json` · `scan/p56_c1_top.png` (the [39.19] render).
