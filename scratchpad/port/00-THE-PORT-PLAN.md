# 00 — THE PORT PLAN

**The one authoritative work plan. It consolidates the six rulebook-audit reports
(`05-11`, `12-20`, `21-31`, `33-46-58`, `47-57`, `01-04-59-64`) and supersedes their individual
TOP-FIVE sections, which conflict in three places (see §7).**

Written 2026-07-14 against engine commit `b99e460`. Every claim below carries a `file:line` or a
rule/chart citation. Where a report asserted something I could not confirm, it is marked
**UNVERIFIED**. Where two reports disagreed, §7 says which one I believe and why. I re-checked
every Tier-0 line against the code; the ones I checked are marked ✅.

---

## 0. THE VERDICT IN SEVEN LINES

* 🔴 **THE INSTRUMENT IS BROKEN. The engine has ONE shared RNG stream, and subsystems draw from it
  conditionally — so changing *anything* reshuffles the dice *everything else* sees.** ✅ Verified:
  `engine.py:84` (`self.rng = random.Random(initial.seed)` — one stream for weather, initiative,
  combat, breakdown, repair, demolition, air and interdiction) and `engine.py:411-414` (`_interdict`
  draws its two CRT dice **only when an order exists**). **A whole class of our "measured" findings is
  therefore corrupted, including one I had already written into this plan as fact.** Fix this
  **first**, before anything else, and take no measurement until it ships (§2.0).
* **The charts are in excellent shape. The engine's *use* of them is not.** Every CRT the auditors
  could reach — the 12.6 Barrage table, the 14.6 Anti-Armor table (all 306 cells), the 15.79 Close
  Assault table, the 17.4 Morale table, the 21.38 Breakdown table, the 29.61 Weather table, the
  41.66 convoy-bombing CRT, the whole of `data/logistics_rates.json` — is transcribed **cell for
  cell correctly**, several of them with OCR repairs that are independently provable. That is real
  work and it holds up.
* **What is wrong is everything wrapped around the charts.** 512 of 1,044 audited rule-rows are
  MISSING. 63 are WRONG.
* **A large amount of correct code and correct data never fires.** Nine whole subsystems and about
  fifteen charts are built, tested, transcribed — and dead in the campaign (§1.3). Several Tier-1
  items are *wiring* jobs, not build jobs.
* **The abstract game (§32/§47/§58) is still load-bearing in the full game, and one of the places is
  the supply trace itself** (`supply.py:229`). That is the deepest bug in the project (§5).
* **The balance problem is the Order of Battle. It is not a tuning problem and it never was.**
  Build the Commonwealth to its own chart and the force ratio inverts from 1.72:1 Axis to ~1.9:1
  Commonwealth — the stated balance target, reached by transcription rather than tuning.
* 🔴 **THE AIR GAME IS NOT DECORATION. MALTA IS THE STRONGEST SINGLE LEVER WE HAVE MEASURED.** With
  the dice stream held identical, cranking Malta's convoy interdiction swings the campaign by
  **~95 VP on seed 1941 and ~320 VP on seed 7 — where it FLIPS THE WINNER** (Axis Smashing 300-10 →
  CW Marginal 100-130). **And the number that currently sets that lever is `_malta_bomb_points` — a
  hardcoded calendar we invented.** The designer's *"why anyone would play a campaign game without
  the Air and/or Logistics Game(s) is beyond me"* is not a taste; it is a load-bearing statement.
* **Honest total size: six to nine months of one-person full-time work** to the point where a balance
  number means anything. There is no shortcut, but there is a good order (§6).

---

## 1. THE SCOREBOARD

### 1.1 Chapter reconciliation — there are 65 chapters, not 69

`docs/rules/` holds **65 numbered chapters** (`01-introduction` … `65-in-conclusion`). The brief's
"69" is off by four. Of the 65:

| | chapters | note |
|---|---|---|
| **Tabled rule-by-rule by the six reports** | **60** | 1–31, 33–46, 48–61, 64 |
| Declared N/A in prose, not tabled | 4 | **32** (abstract logistics — the alternative ruleset), **47** (~20 rules, abstract), **62 + 63** (78 rules; scenario groups 3 & 4, ruled out by 64.3/64.4/64.6/64.51) |
| No rule content | 1 | **65** — "In Conclusion", the designer's afterword |
| **TOTAL** | **65** | |

### 1.2 The count — 1,044 audited rule-rows

Statuses parsed mechanically from the six ledgers (precedence WRONG > MISSING > PARTIAL > DONE >
N/A, so `PARTIAL/WRONG` counts as WRONG). **One table:**

| Slice | Chapters | DONE | PARTIAL | MISSING | WRONG | N/A | **rows** | of which **DEAD** |
|---|---|---|---|---|---|---|---|---|
| **05–11** the land core | 7 | 69 | 39 | 56 | **12** | 8 | **184** | ~30 (all hexside terrain, reaction, continual movement) |
| **12–20** combat & reinforcements | 9 | 72 | 23 | **115** | 6 | 2 | **218** | 11 (all of ch.18 Reserve) + 15.52/15.53 |
| **21–31** attrition, terrain, specials | 11 | 68 | 13 | 70 | **14** | 9 | **174** | 12+ (ch.30 Fleet, ch.31 Rommel, 24.6 rail, 25.14 forts, 26.26) |
| **33–46 + 58** the air game | 15 | **7** | 13 | **204** | 6 | 13 | **243** | 3 of the 5 live behaviours never fire in the campaign |
| **47–57** the logistics game | 11 (10 tabled) | 47 | 22 | 33 | **16** | 0 | **118** | 54.12 Non-Dump row, 54.2 Water column, 22.23 truck repair |
| **01–04 + 59–64** setup & campaign | 10 (8 tabled) | 10 | 22 | 34 | 9 | 32 | **107** | — |
| **TOTAL** | **65** | **273** | **132** | **512** | **63** | **64** | **1,044** | **≥ 9 subsystems, ≥ 15 charts** |
| **%** | | **26%** | **13%** | **49%** | **6%** | **6%** | | |

*Counts are a mechanical parse of the six ledger tables and are reproducible. The air report's own
headline gives 7 / 12 / 187 / 6 for its slice against my 7 / 13 / 204 / 6; the difference is how the
33.0 sequence-of-play rows and the N/A column are folded. Immaterial — the shape is identical:
**the air game is ~157 lines of executable code standing in for 1,487 lines of rulebook.***

Chapters that are **wholly missing** — zero lines of code: **16** (Patrols), **19** (Organization /
Kampfgruppen), **27** (Desert Raiders), **28** (Prisoners), **35** (SGSUs), **36** (Air Facilities),
**38** (Aircraft Maintenance), **40** (Fighter Combat), **43** (Axis Aegean Bases), **45**
(Air-to-Air), **58** (Abstract Air). Chapter **26** (Minefields) has a one-line combat shim that can
never fire.

Chapters that are **DONE and clean**: **1**, **31** (Rommel — and he is not in the campaign),
**57** (the CW supply base), **2** (N/A), and the two chapters' worth of charts noted above.

### 1.3 The second axis nobody counted: DONE ON PAPER, DEAD IN THE CAMPAIGN

This is the most useful number in the document, because it tells you what you have **already paid
for** and are not using.

| Built / transcribed | Status in the campaign | Evidence |
|---|---|---|
| **Rule 30 — the Mediterranean Fleet** | `NavalUnit(` is constructed in exactly one place in the repo: `tests/test_naval.py:44`. `naval=` appears **nowhere** in `scenario.py`. `len(final.naval) == 0`. **Not one ship has ever reached a board.** 64.51 names the Fleet by name. | ✅ |
| **Rule 31 — Rommel** | Fully implemented and tested (CPA 60, the +1 morale outside the ±3 clamp, the +5 CPA anchor, the Berlin recall). `state.rommel is None` in the campaign. **No `EventKind` can create a `Rommel`** — there is no arrival path. 64.51 names him by name. | ✅ |
| **Rule 18 — Reserve Status** | 11 rules DONE. `RESERVE_DESIGNATED: 0`, `RESERVE_RELEASED: 0`, `RESERVE_FLIPPED: 0` in 45 game-turns. The policy never designates a reserve. | |
| **8.51–8.55 Reaction, 8.21–8.25 Continual Movement** | `0 REACTION_MOVED`, `0 SEGMENT_ADVANCED` in an 8-turn run. `campaign_policy.py` implements neither hook. **Every balance number ever taken was measured on a game where the defender never dodges and the attacker gets one movement segment per turn.** | |
| **All hexside terrain** (8.41–8.43, 10.21, and 8 hexside combat shifts) | Coded exactly and verified against the chart. `cna_map.py:52` builds the `TerrainMap` **without passing `hexsides` at all**. `HEXSIDES: 0` on the campaign map. | ✅ |
| **15.52/15.53 organization-size shift** | Chart transcribed EXACTLY. Every combat counter is SP 1 (`Counter({1: 281, 0: 22})`), so the shift is always 0. Rule 19 does not exist, so **no division ever forms**. | |
| **25.14 fort reduction** | `_batter_fort` and `_air_fort` exist, gated behind `state.siege_rules` = **False** in the campaign. `FORT_REDUCED = 0` in 111 turns. **Nothing in the campaign can reduce a fortification, ever.** | |
| **24.6 railroad construction** | Built yesterday, correct, elegant. `CONSTRUCTION_ADVANCED = 0` over 111 turns: the two NZRRC companies are seeded at `(47,140)`, forty-odd hexes from the railhead at `(26,100)`, and nothing moves them there. **Zero of 46 surveyed hexes laid.** | |
| **[7.2] Initiative Ratings chart** | Transcribed at `docs/rules/90:607-617`. Read by no code. `engine.py:208` and `state.py:261` both *claim* the chart is untranscribed — **both docstrings are false.** | ✅ |
| **[55.3] Port Efficiency Levels** | Correct in `data/logistics_rates.json`, verified cell-for-cell against the scan. `scenario.py:996-1004` reads only the `tons` key and hardcodes the rest. | ✅ |
| **[22.8] truck/AC repair columns, [54.12] Non-Dump row, [54.2] Water column, [54.2] BAR 2L** | All correctly transcribed. All read by nothing. The relay hauled **0 Water Points** in 111 turns; not one lorry has ever broken down. | ✅ |
| **`Unit.vulnerability` (11.12 / 15.84)** | Populated on **every unit** from the charts (`oob.py:294`). `grep vulnerability game/engine.py` → **nothing**. **Artillery is immortal in close assault.** | |
| **`Unit.is_first_line_truck` (53.11)** | Declared at `state.py:66`. **Never set True anywhere in the codebase.** Read only by `stacking.py:33` and `supply.py:172`. | ✅ |
| **`Unit.is_pure_aa`, `SupplyUnit.is_dummy`** | Declared. Never set True anywhere. | ✅ |
| **26.26 minefield column shift** | `MINEFIELD_CA_SHIFT = -1`, correct magnitude. `engine.py:2457` `mined = target in r.state.terrain.minefields` is **always False** — `TerrainMap.minefields` is assigned nowhere. | ✅ |

---

## 2. TIER 0 — THE FREE WINS

### 2.0 🔴 T0-0 — FIX THE RNG. THIS COMES BEFORE EVERYTHING ELSE IN THE PROJECT. 【M】

**This is not a rules bug. It is an instrument bug, and it invalidates measurements.**

✅ **Verified.** `game/engine.py:84`:
```python
self.rng = random.Random(initial.seed)      # ONE stream for the whole engine
```
Weather, initiative, combat, breakdown, repair, demolition, air superiority, convoy interdiction —
**every subsystem draws from the same `random.Random`.** And subsystems draw **conditionally**.
`game/engine.py:405-417`:
```python
def _interdict(convoy, state, rng):
    """...Draws the two [41.66] CRT dice on `rng` ONLY when an InterdictionOrder covers this
       lane+turn, so an interdiction-free lane draws no rng and returns the cargo verbatim
       with dice=() (BYTE-IDENTICAL)."""
    order = _interdiction_for(state, convoy)
    if order is None:
        return dict(convoy.cargo), None, 0, 0, ()          # <-- draws nothing
    d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
```

**The docstring names the cause and mistakes it for a virtue.** The byte-identity discipline —
"changing nothing must draw no dice" — is *exactly* what makes **changing something reshuffle the
entire downstream dice stream for every other subsystem.** Alter the *number* of interdiction orders
and you alter the weather, the breakdowns, the morale rolls and the CRT results for the remaining
111 turns. **±200 VP of pure noise is injected into any A/B that toggles a conditionally-drawing
subsystem.**

**THE MEASUREMENT THIS ALREADY DESTROYED — and it is the biggest finding in the project.**

The air audit concluded *"Malta is causally inert — cranked to the rule-41.66 ceiling it denies
342,000 Fuel Points and the victory score does not move."* **That is FALSE.** It was a desync
artefact, and it had already been written into project memory as a settled dead end. Re-run with the
**dice stream held identical** — 111 orders in both arms, with `bomb=1` (the CRT's flat-0% column:
it *draws* two dice and denies nothing) against `bomb=500`:

| seed | Malta OFF-equivalent (`bomb=1`) | Malta MAX (`bomb=500`) | swing |
|---|---|---|---|
| **1941** | CW Marginal **120 – 180** | CW **SMASHING** 75 – 230 | **~95 VP** |
| **7** | **AXIS SMASHING 300 – 10** | **CW Marginal 100 – 130** | **~320 VP — IT FLIPS THE WINNER** |

**Malta is one of the strongest levers in the engine. It is also the historically correct one** — the
strangling of Axis shipping from Malta is a large part of why the Axis lost North Africa. And the
number that currently *sets* that lever is `scenario.py:1060` `_malta_bomb_points`, **a hardcoded
month-by-month calendar we invented** (invention **I2**).

**THE FIX.** Independent, deterministic, per-subsystem random streams, derived from the master seed:
```python
self.rng = {sub: random.Random(hash_seed(initial.seed, sub))
            for sub in ("weather", "initiative", "combat", "breakdown", "repair",
                        "demolition", "interdiction", "air", "recon", "convoy", ...)}
```
so that a die drawn — or **not** drawn — in one subsystem cannot shift the dice any other subsystem
sees. This is standard determinism discipline for an event-sourced engine. **It is the instrument
every other decision in this project depends on.**

⚠️ **IT WILL BREAK BYTE-IDENTITY ON THE TWO LOCKED BENCHMARK SCENARIOS**
(`rommels_arrival` `9339d2b308d7`, `siege_of_tobruk` `5ba4da88d107`). **That is expected and
accepted. The owner has agreed to drop the byte-lock. Those hashes are no longer constraints and
the plan does not treat them as such.** Re-baseline them once, after T0-0, and move on. *(The
byte-lock was a good discipline for a walking skeleton and it became the thing that broke the
measurements. Retire it.)*

🔴 **NO BALANCE MEASUREMENT AND NO A/B IS VALID UNTIL T0-0 SHIPS. Take none.**

---

### 2.1 THE MEASUREMENT REGISTER — what survives T0-0 and what does not

Two *different* failure modes. Keep them apart or you will throw away good evidence.

**(P1) STRUCTURAL DESYNC — corrupted, and T0-0 fixes it.** An A/B that toggles a subsystem which
**conditionally draws dice** reshuffles every other subsystem. Anything measured this way is void.

| Claim | Verdict |
|---|---|
| *"Malta at its maximum changes the score by zero."* | 🔴 **KNOWN FALSE.** It swings 95–320 VP and flips seed 7. **Purge it from project memory.** |
| *"Doubling Commonwealth strength changes nothing."* | 🔴 **UNRELIABLE — PENDING RNG FIX.** Re-run after T0-0. |
| The 32.32 / `motorized_supply=False` **measurement** (`scenario.py:1290-1303`) | 🟡 **UNRELIABLE as a measurement** — but the **ruling stands on textual grounds regardless**: 32.32 is an abstract-game rule and does not apply to us (§5, A3). *Keep the decision; discard the number that justified it.* |
| Any other A/B in the six reports taken by switching a die-drawing feature on or off | 🔴 **UNRELIABLE — PENDING RNG FIX.** |

**(P2) SINGLE-SEED CHAOS — *not* fixed by T0-0, and never will be.** Even with perfect per-subsystem
streams, changing a *rule* changes outcomes, which changes later dice consumption. That is inherent
to a stochastic simulation. **The fix is methodological: after T0-0, every balance claim must be
reported as a DISTRIBUTION OVER N SEEDS, not a single-seed outcome.** Three seeds is not a
measurement.

| Claim | Verdict |
|---|---|
| *"The repair fix flips the winner on seed 1941 (ALLIED → AXIS)."* | 🟡 **SUGGESTIVE, NOT CONCLUSIVE.** One seed. The *mechanism* is solid (below). |
| *"Axis Smashing Victory in all three seeds; the war moves the score by −25 / −25 / +145."* | 🟡 Three seeds. Directionally overwhelming, but re-run at N ≥ 30 after T0-0. |

**(P3) SOLID — no dice involved. T0-0 changes none of these, and they carry the whole of Tier 0.**
*Closed-form arithmetic, chart diffs, state inspections and accounting sums.*

* Expected repair recovery **58.3% → 13.3%** (a closed-form read of the [22.8] column). ✅
* The Tobruk lane lands **exactly 595 Ammo** — `425 + 170`, closed-form, and it matches the run to
  the point. ✅
* Benghazi passes **4× its charted tonnage** — arithmetic on `port_landing_cap`. ✅
* The built state carries **9,600 Axis Fuel** where [60.34] charts 3,000 — a state inspection. ✅
* **Benghazi (75 VP) is empty at GT1**; the Tobruk garrison stands 4–5 hexes outside Tobruk. ✅
* **Force ratio 1.72:1 Axis** and the CW at **32% of its own chart** — pure OOB properties, no dice. ✅
* **The 17.4 table's SURR = 36/36 = 100% at cohesion ≤ −17** — closed-form. The *mechanism* behind
  "20 of 36 assaults end in surrender" is proven even if the count is one run. ✅
* **73% of all fuel evaporated; the Panzerarmee burnt 1,419 points in 111 turns** — an accounting sum
  over one run, and the ratio (1,600:1) is far too extreme for dice to explain. ✅
* Every "`X` is never set / never read / never fires" finding — `grep`, not dice. ✅

**Everything in the Tier-0 table below is P3 or P3-plus-a-suggestive-P2. None of it rests on a
corrupted A/B.**

---

### 2.2 THE TABLE

**Definition: corrections to numbers we transcribed wrongly or never read. Not new subsystems.**
Ranked by measured impact. Every one is a day or less except T0-0, T0-10 and T0-11, which are marked.

| # | What | Where | Size | Measured effect |
|---|---|---|---|---|
| 🔴 **T0-0** | **One shared RNG; subsystems draw conditionally** | `engine.py:84`, `:411-414` | **M** | **CORRUPTS EVERY A/B. Malta's 320-VP swing was hidden by it. DO THIS FIRST.** |
| **T0-1** | Broken-tank repair 100% → 10% | `combat_tables.py:461` | S | 4.4× armour recovery; flips seed 1941 |
| **T0-2** | Wrong scenario group's supply pools | `oob.py:39-40` | S | **+6,600 Fuel to the Axis** |
| **T0-3** | Port tonnage gate is per-commodity | `supply.py:90-95`, `engine.py:666` | S | **4× charted tonnage**; 3,594 t/GT through a 2,500 t port |
| **T0-4** | Three port Efficiency Levels invented | `scenario.py:996,1001,1003` | S | Tobruk lands **425 vs a charted 170** Ammo/OpStage |
| **T0-5** | Cohesion not averaged (6.27) | `engine.py:2569` | S | **20 of 36 close assaults end in instant surrender** |
| **T0-6** | `classify()` substring-matches | `oob.py:145-146` | S | The CW's entire GT1 armour is fake; its AA arm is deleted |
| **T0-7** | Hot water +1 where 29.35 doubles | `supply.py:200` | S | 6-TOE panzer bn pays **7 vs a charted 12**, 30% of stages |
| **T0-8** | Fort close-assault shift L2/L4/L6 → L2/L3/L4 | `combat_tables.py:328` | S | Tobruk 1 column too strong; the Delta **2** |
| **T0-9** | One air mission buys three sorties | `engine.py:1003` | S | **Tobruk lands 595 Ammo in the whole war** |
| **T0-10** | The three bombing missions roll no dice | `engine.py:1015/1039/1057` | S+ | The [41.5] CRT was never transcribed |
| **T0-11** | Foul weather blankets the theatre | `engine.py:936` | M | **68/68** storms covered all 5 sections; chart says 2–3 |
| **T0-12** | Captured supply is 100% usable (32.13) | `apply.py:125` | S | Axis kept **3× its whole war's ammo expenditure** |
| **T0-13** | The 54.17 demolition table | `logistics_data.py:73-84` | S | **17% of demolitions mis-scored** — ⚠️ **ERRATA RULING** |
| **T0-14** | Air immunity for every Level-2 city | `engine.py:1021` | S | one character |
| **T0-15** | Initiative ratings are `{}` | `scenario.py` (campaign ctor) | S | coin-flip for 111 turns — ⚠️ **TRAP, see below** |
| **T0-16** | 64.73's occupation test, wrong magnitude | `campaign_victory.py:72-78` | S | **30–45 VP permanently dead on the table** |
| **T0-17** | Tobruk convoy seeded at 3.5× its harbour | `scenario.py` (lanes) | S | **21% of all planned tonnage never reaches Africa** |
| **T0-18** | 59.61 air-facility truck rows over-seeded | `scenario.py:812,818,851-854` | S | Axis +60 TP, CW +55 TP |
| **T0-19** | 22.26 repair fuel per attempt, not per TOE | `engine.py:1488` | S | 10-TOE bn repairs for 1 Fuel, not 10 |
| **T0-20** | 29.45 sandstorm breakdown, no 50% test | `combat_tables.py:476` | S | over-applied to every mover |
| **T0-21** | 51.13 HQ/engineer stores — wrong *formula* | `supply.py:189-190` | S | **currently harmless — see §7.D3** |

### 2.3 THE DETAIL

**T0-1 — Broken-tank field repair is 100% where the chart says 10%.** ✅
`game/combat_tables.py:461`:
```python
"tank":     {0: 25, 1: 25, 2: 100, 3: 100, 4: 100, 5: 0, 6: 0},   # WRONG
```
Chart **[22.8]**, read directly off the scan (PDF p103): `25% / 10%* / 10%* / 10%* / 0% / 0%`. The
OCR bled `10%*` into `100%` at `docs/rules/90:1214-1216`, and `data/breakdown_rates.json` copied
it — the data file even *documents what the asterisk means* and then transcribes `100%`. The `10%*`
single-TOE exception **is already coded** (`engine.py:1504`) and is unreachable because the result
is never 10.
**Correct value:** `{0: 25, 1: 25, 2: 10, 3: 10, 4: 10, 5: 0, 6: 0}`. Fix `data/breakdown_rates.json`
in the same commit.
**Measured:** expected recovery per attempt **58.3% → 13.3% (4.4×)** — **P3, closed-form off the
chart, and it is the number that matters.** Campaign armour recovery **86.4% → 72.2%**; net armour
lost **56 → 99 TOE**. On seed 1941 the campaign winner flipped ALLIED → AXIS — **🟡 P2: ONE SEED.
Suggestive, not conclusive; re-run at N ≥ 30 after T0-0.** Today `TOE still broken at end of
campaign: 0` — the desert has never permanently taken a tank from anybody. **Every balance number
taken in the last month was taken with this in.**

**T0-2 — The campaign seeds the WRONG SCENARIO GROUP's supply pools.** ✅
`game/oob.py:39-40`:
```python
_AXIS_DUMP_POOL = logistics_data.axis_dump_pool_61_44()   # [61.44] — DESERT FOX, GT26
_CW_DUMP_POOL   = logistics_data.cw_dump_pool_61_36()     # [61.36] — DESERT FOX, GT26
```
Rule **64.3** mandates **§60** for all initial placement in the full campaign. The built state
carries 5 × `AX-Dump` = **2,500 Ammo / 9,600 Fuel / 950 Stores / 1,100 Water** = **[61.44]
verbatim**, where [60.34]'s Dump 1 + Dump 2 give **2,000 / 3,000 / 2,500 / 400**.
**+6,600 Fuel Points to the Axis (9,600 vs a charted 3,000 — 3.2×), in a scenario it is not
playing.** The Commonwealth gets 5 × `AL-Dump` = 1,700 / 2,550 / 1,600 = **[61.36] verbatim**,
**3.4×** the charted [60.44] Dump I (500/750/500), plus **1,600 Water the chart does not grant**
(`oob.py:41` `_CW_WATER_PROXY = 1600`).
Also unseeded from [60.34]: **C0716** (100/50/50) and **2 dummy dumps**; from [60.44], **1 dummy
dump**. Tripoli's 250/5000/250 is off-map and defensibly skipped.

**T0-3 — The 55.14 port gate is applied per-commodity instead of as one shared tonnage budget.** ✅
`game/supply.py:90-95`:
```python
def port_landing_cap(port: Port, commodity: str) -> int:
    cap = min(getattr(port, "cap_" + commodity.lower()), tons_to_points(port.cap_tons, commodity))
    return math.ceil(cap * port.eff / port.max_eff)
```
and `game/engine.py:666,696,702` budget `port_landed[(port.id, k)]` **per (port, commodity)**. The
port's **whole** tonnage allowance is spent on **each** commodity separately.
The **[55.3] key** is explicit: *"**Maximum Tonnage:** the **TOTAL tonnage** of supplies that may be
shipped in and/or out in one Operations Stage."*
**Measured:** Benghazi (2,500 t) passes 625 Ammo **+** 20,000 Fuel **+** 2,500 Stores **+** 15,000
Water = **10,000 tons** in one OpStage. Tobruk (1,700 t) → 6,800. Tripoli (15,000 t) → 60,000.
Campaign-measured: Benghazi landed **398,917 tons over 111 GT = 3,594 t/GT** through a port rated
**2,500 t per OpStage**.
⚠️ **`tests/test_ports.py:110` (`test_two_convoys_share_one_port_cap_per_opstage`) locks the bug
in.** It asserts the per-commodity behaviour. Update it in the same commit.

**T0-4 — Three port Efficiency Levels are invented, and the correct values are already in the repo.** ✅
`game/scenario.py:996` (`PORT-Benghazi`, `max_eff=10, eff=10`), `:1001` (`PORT-Matruh`,
`max_eff=10, eff=10`), `:1003-1004` (`PORT-Tobruk`, `max_eff=5, eff=5`).

| Port | [55.3] / [55.25] | Seeded | Effect |
|---|---|---|---|
| **Tobruk** | max **5**, **starts at 2** (San Giorgio, −3 levels) | 5 / 5 | lands **425 Ammo/OpStage instead of 170** (2.5×); the besieger must bomb off 5 levels instead of 2 |
| **Benghazi** | **3** | 10 / 10 | one level of bomb damage costs 1/10 of throughput instead of **1/3** — the Axis port of arrival is **3.3× harder to shut** |
| **Mersa Matruh** | **1** | 10 / 10 | charted, **one hit closes it**. Seeded, it takes **ten** |

The 55.3 footnote is explicit: *"A loss of one level of efficiency decreases the port's capacity by
a fraction equal to one over the listed efficiency level."* **The Efficiency Level is not a
capacity — it is the damage denominator.** Setting it to 10 makes every harbour near-immune to the
air war the engine seeds specifically to shut harbours.
`data/logistics_rates.json` (`port_supply_tonnage_55_3`) **already carries the correct levels**,
verified cell-for-cell against the scan. `_campaign_ports()` reads only the `tons` key.
`game/state.py:321-323` *claims* "Tobruk seeds eff=2/max_eff=5". **The docstring is false. No
scenario does.**

**T0-5 — Cohesion is not averaged (6.27).** ✅
`game/engine.py:2569`:
```python
largest = max(live, key=lambda u: (u.stacking_points, u.strength))    # picks ONE unit
```
Rule **6.27**, which **15.63** and **17.27** both defer to: *"if there is more than one 'largest
unit', then the Cohesion Levels of all 'largest units' are **added together and divided by the
number of contributing counters**."* Its own worked example: three brigades at −4, −1 and +3 →
(−4 −1 +3) ÷ 3 = **−1**. 15.64c averages divisional **morale** the same way.
**Every combat counter in the campaign is SP 1** (`Counter({1: 281, 0: 22})`), so *every* stack is a
tie and averaging should fire in nearly every multi-unit assault. The engine instead borrows the
**strongest** unit's cohesion, hiding its broken companions.
**Measured:** cohesion of the "largest" unit at the moment of assault ran to **−74, −75**. The 17.4
table bottoms out at "−17 et seq", where **SURR = 36/36 = 100%**. Result: **20 of 36 close assaults
in a 45-turn run ended in an instant morale surrender — 10 defender, 10 attacker — annihilating a
whole stack before a die was rolled for losses.** The last four assaults of the run are attacking
stacks at −17, −30, −74 and −75 destroying themselves. Under 6.27 a stack of ten where one unit is
at −75 and nine are at 0 fights at **−8 (25% SURR)**, not −75 (100%).
**Until this is fixed the CRT barely rolls, and every combat number this engine produces is noise.**

**T0-6 — `classify()` substring-matches the formation name.** ✅
`game/oob.py:145-146`:
```python
if "Armoured" in g or "Tank" in g:
    return "tank"
```
`g` is the **formation-group string**. `"BR Unassigned Anti-Tank Regiments"` contains "Tank".
`"7th Armoured Division"` contains "Armoured" — and the 7th Armoured's *support group* carries its
anti-tank and artillery regiments. Verified by building the state; **every** `is_tank` Commonwealth
unit at GT1:

| counter | what it actually is | engine makes it |
|---|---|---|
| `BR-65`, `BR-149` | 65th / 149th **Anti-Tank Regiments** (2-pdr) | A13 cruiser tanks |
| `BR-3-RHA` | 3rd RHA — **anti-tank** | A13 cruiser tank |
| `BR-4-RHA` | 4th RHA — **field artillery** | A13 cruiser tank, **barrage 0** |
| `BR-1-KRRC` | 1st KRRC — **motor infantry** | A13 cruiser tank |

**Not one of the Commonwealth's five "tank" units at GT1 is a tank. And 1st RTR — the only real tank
battalion in the September-1940 Western Desert Force — is absent from the data entirely.** The
Commonwealth's 40 "tank TOE" is 100% phantom.
**Consequences, all measured:** 7 Armd Div starts with **zero barrage points** (4 RHA's 8 × 6 TOE =
48 raw, gone) and **zero anti-tank guns**. All five are `is_tank`, so `_combined_arms_penalty`
(`engine.py:2530`) counts **40 TOE of unsupported tanks with 0 infantry support → the maximum −4
Actual close-assault penalty**, offensively *and* defensively, on the Commonwealth's entire starting
army. Its raw offence of 80 → 8 Actual → **4**. Halved.
**Two more arms destroyed by the same chain:** `oob.py:144` (`if "Indian" in g … return
"motor_infantry"`) fires **before** the tank rule, so `IN-31-Fld` (**31st Field Artillery Regiment**)
loads as motor infantry with barrage 0. And **there is no AA role in the taxonomy at all** — rule
3.23 lists AA as a combat type; `oob.py:118` maps Italian `(AA)` counters to `"antitank"`, and
`BR-15-LAA` / `BR-57-LAA` / `BR-9-HAA` fall through the whole chain to `return "infantry"` (verified
in the built state: barrage 0, anti_armor 0, 6 steps).
🔴 **THIS FIX MUST LAND WITH THE OOB GAP-FILL (Tier 1, T1-2).** Fixing `classify()` alone strips the
Commonwealth of five phantom tank battalions and gives it nothing back.

**T0-7 — Hot weather adds +1 Water where rule 29.35 DOUBLES it.** ✅
`game/supply.py:199-200`:
```python
base = max(1, unit.strength) if _is_vehicle_type(unit) else 1
return base + (1 if hot else 0)          # docstring: "the exact addition is not charted -- PROXY +1"
```
`data/logistics_rates.json:113` asserts *"UNSPECIFIED — 52.43… charts no number."* **That is false.**
**29.35** gives the number: *"water requirements for all units are DOUBLED."*
**Measured:** a 6-TOE panzer battalion pays **7** where the book says **12**; a 10-TOE unit pays 11
where the book says 20. Infantry (base 1) is accidentally right. **Hot weather is 30% of all
Operations Stages, and the error lands squarely on the armour** — the panzers whose reach the whole
campaign is about.

**T0-8 — The fortification close-assault shift.** ✅
`game/combat_tables.py:328`: `FORT_CA_SHIFT: int = -2`, applied at `game/combat.py:84` as
`fortification_level * ct.FORT_CA_SHIFT` → **−2 / −4 / −6** for levels 1/2/3.
Chart **[8.37]** grades the close-assault fortification benefit **L2 / L3 / L4**. Confirmed on the
original scan (PDF p70) by **two independent auditors**, both of whom also confirm that the engine's
Barrage fort column (L1/L2/L2) and Anti-Armor fort column (L1/L2/L2) **are correct**.
**Correct value:** `FORT_CA_SHIFT_BY_LEVEL = {1: -2, 2: -3, 3: -4}`.
**Measured:** a +15-differential assault on Alexandria resolves on **column 12 (+5..+6)**; the book
puts it on **column 14 (+9..+10)**. On the 15.79 defender table those two columns are the difference
between a 40–50% loss row existing and not existing. Tobruk/Bardia (Level 2) are **one column** too
strong; the Delta (Level 3) is **two**.
The code's own comment at `combat_tables.py:325-327` flags this and says "out of scope here."
🔴 **This is the SECOND independent cause of "the Axis can never crack Tobruk."** Memory
`cna-tobruk-crackability` blamed only the 15.82 no-eviction rule. **There is a third: nothing in the
campaign can reduce a fortification at all** (`siege_rules = False`; `FORT_REDUCED = 0` in 111
turns; 12.5 barrage-against-facilities is missing; the [41.5] Fortification row was never
transcribed). All three must be named in that memory.

**T0-9 — One air mission buys three sorties.** ✅
`game/engine.py:1003`:
```python
due = [m for m in r.state.air_missions if m.side == side and m.turn == r.state.turn]
```
`_air_support` re-flies every **game-turn**-keyed mission in **all three Operations Stages**.
`_naval_convoys` right beside it *is* correctly gated `if stage == 1:` (`engine.py:148`) — **the
convoy author knew about the turn/stage distinction and guarded it; the air author did not.**
Rule **39.14**: tactical land support is flown **once per Operations Stage**, from a per-stage
assignment.
**Measured, compounded with T0-10's flat port-bomb and `HARBOUR_BLOCKED` (`engine.py:65`):** the
Commonwealth knocks **3 Efficiency Levels off Tobruk every game-turn**, and Tobruk never
regenerates. Tobruk goes **5 → 2 in GT1, 2 → 0 in GT2**, and stays at 0 for 109 turns.
```
GT1 stage 1: convoy lands at eff 5  -> 425 AMMO
GT1 stages 1-3: CW _air_port fires 3x, eff 5 -> 2
GT2 stage 1: convoy lands at eff 2  -> 170 AMMO
GT2 stages 1-3: eff 2 -> 0   (never regenerates)
GT3..GT111:                        ->   0 AMMO
-------------------------------------------------
TOTAL                                  595 AMMO
```
**Measured over the full 111-turn campaign: lane 6 (Axis → Tobruk) lands exactly 595 Ammunition
Points.** 425 + 170 = 595. The chain closes to the point. Meanwhile the Commonwealth ferry lands
**0** (56.15 correctly cancels it — the Axis holds Tobruk from GT1). **Tobruk is fed by nobody, all
war. There is no siege and no duel — just a harbour that was switched off on turn 2 by an air force
that rolled no dice.**

**T0-10 — The three bombing missions roll no dice, because the table was never transcribed.** ✅
`engine.py:1057` `_air_port` removes **exactly one** Efficiency Level, unconditionally, with no die
and no bomb-point column — [41.5]'s Ports row gives **0–4**, very often **0**.
`engine.py:1039` `_air_fort` reduces the fort by exactly 1 level with no die — it **always
succeeds**; [41.5]'s Fortification row is binary **No Effect / Reduced**, i.e. a coin-flip turned
into a certainty.
`engine.py:1015` `_air_strike` pins **exactly one** unit — the single strongest, via
`_barrage_target` — with no die; [41.5] gives **0–7** battalion-equivalents pinned.
**Root cause: the [41.5] Air Bombardment & Secondary Barrage CRT is 1/8th transcribed.** Only the
Axis-Naval-Convoy row exists (and it is **exact**, verified cell-by-cell). The other **seven** target
rows — Airfields/Strips/**Ports**, **Supply Dump** (0/10/20/30/40/50/**75%** + 1 truck per 10%),
**Fortification** (binary), **Railroad**, **Road**, **Trucks/Flak/Combat-Units/CW-Fleet** (0–7) — are
on **PDF page 107** and are legible.
**Size S+** (a chart transcription plus three call sites), and it is the **single highest-leverage
transcription job in the project**: it fixes three WRONG rules, unlocks four MISSING ones (41.32
trucks, 41.35 dumps, 41.36 air facilities, 41.38 rail/road), and **unblocks 12.5 — barrage against
facilities — which is the missing fort-reduction mechanism of T0-8.** It is also the prerequisite
for a real Malta.

**T0-11 — Foul weather blankets all five map sections.** ✅
`game/engine.py:931-937` rolls the die, computes the sections, and throws them away:
```python
sections = weather.foul_sections(d3)
theater = r.state.map_sections
if theater and theater.isdisjoint(sections):        # never true: theater IS {A,B,C,D,E}
    label = weather.NORMAL
```
Every row of the **[29.7]** table names sections inside A–E, so the filter never fires.
`weather.foul_sections` (`{1:AB, 2:CD, 3:DE, 4:BC, 5:BD, 6:BCD}`) is **verified correct against the
scan**.
**Measured: 68 of 68 foul rolls covered the whole theatre.** The chart puts a storm on **2–3 of 5**
sections (mean 2.17). Six couplings are therefore over-applied by **~2.3×**: construction halts
(24.22), field repair blocked (22.13d), movement doubles (29.44), roads become tracks (29.56), the
breakdown column shifts (21.37d), air is grounded (37.22).
**Size M, not S**: `GameState.weather` is a **scalar** and must become a per-section map, touching
~6 call sites. Every hex knows its section (the coordinate labels are `A`–`E`-prefixed), so a
`weather_at(hex)` is well-defined. The die is already rolled and the sections already computed.
**Also missing, and cheap while you are in there: 29.53 — "all depleted wells are filled during a
rainstorm."** `wells.py:90` states it outright as deliberately ignored. **38 rainstorms in the
campaign, 0 wells refilled.** Water is the binding constraint and this is a faucet both armies are
denied.

**T0-12 — Captured supply is 100% usable (32.13, an abstract-game rule).** ✅
`game/apply.py:125` — the comment cites **32.13** verbatim and flips every commodity intact.
The full game **taxes capture**: **50.16** — only **⅓ (round up)** of captured Ammunition is usable,
*the rest are lost*. **51.16** — only **50%** of captured Stores. Only Fuel is free (49.19: fuel is
non-denominational). Water is silent.
**Measured, seed 1941: the Axis captured 3,275 Ammunition Points — three times its entire ammunition
expenditure for the whole war (1,078)** — and 8,188 Stores. It should have kept 1,092 and 4,094. The
Commonwealth captured 514 Ammo / 1,078 Stores. **Balance: pushes toward the Commonwealth** (the Axis
captured 4× as much as the CW did).

**T0-13 — The 54.17 Supply Dump Demolition Table. ⚠️ AN ERRATA RULING FOR YOU, NOT A SILENT FIX.**
`game/logistics_data.py:73-84` and `data/logistics_rates.json:146` transcribe the printed chart
**faithfully**:
```
DIE:        -2   -1    0    1    2    3    4    5    6    7   8+
% destroyed  0   33    0   10   20   33   50   75  100   33  100
```
**The OCR is not wrong. The 1979 printing is wrong.** Two auditors rendered PDF page 109
independently (at 400 dpi and at 600 dpi) and read the column alignment directly. **The values
really are printed under those headers.** `logistics_data.py`'s docstring already flags the anomaly
and **deliberately declines to "fix" it — which is the correct instinct for a port.**
**The correction is FORCED by the neighbours.** Strike the two anomalous cells and everything else
is a clean monotone ladder (0/10/20/33/50/75/100), and the two struck cells are exactly the two
whose values are pinned on both sides: `−1` sits between two 0s; `7` sits between two 100s. Almost
certainly a duplicated "33" slug in the paste-up.
**Corrected: `−1: 33 → 0`, `7: 33 → 100`.** All nine other cells unchanged.
**It is live.** In seed 1941 the engine ran 18 demolition attempts. **Three of eighteen (17%) rolled
a natural SIX with a +1 modifier — modified 7 — and destroyed 33% where the ladder says 100%. The
best possible roll in the game is punished.** And at a modifier of −3 (a lone battalion in a major
city, which is where most dumps stand) a die of **2** burns a third of the dump while a die of **3**
burns nothing.
**RECOMMENDATION: apply the correction and record it as an errata**, with an `_errata_54_17` key in
`data/logistics_rates.json` carrying the printed values, the corrected values, and this reasoning.
That satisfies both auditors (§7.D2) and leaves an audit trail. **But it is your ruling.**
While in there: `demolition_modifier` is **missing the entire final cumulative clause** — `+1 if the
dump was just captured` / `−1 if the nearest enemy is ≥ 20 CP (medium truck) away`. **A swing of up
to 2 on the die, and it is not flagged in the code.**

**T0-14 — Air immunity is granted to every Level-2 city.** ✅
`game/engine.py:1021`: `walled = r.state.fort_level(tgt) > 1`. Rule **25.23** grants the
air-bombardment immunity to **Level 3** cities only (it must be reduced to Level 2 first).
→ `>= 3`. One character. (Related and missing: **25.24** — all units in a Level-3 city **ignore all
pinned results** from any combat. Cairo and Alexandria's garrisons are currently pinnable.)

**T0-15 — Initiative: both ratings are 0 for 111 turns. ⚠️ AND THIS ONE HAS A TRAP.** ✅
`campaign()` is the **only** scenario that sets none of `initiative_fixed` / `initiative_fixed_until`
/ `initiative_ratings`, so `engine.py:220-223` resolves both sides to 0 via `.get(..., 0)` and both
armies roll a bare d6 for **111 game-turns**. `rommels_arrival` already shows the fix pattern
(`scenario.py:318-319`).
The **[7.2] chart IS transcribed** (`docs/rules/90:607-617`) and read by no code:
**Commonwealth 3 (GT1–42), 4 (GT43–90), 5 (GT91–111). Axis 6 with the Rommel counter on the maps,
3 with German land combat units but no Rommel, 1 with neither.**
Rule **64.4 → 60.6**: *the Italian Player has the Initiative for the entire first Game-Turn*; roll
from GT2.
🔴 **THE TRAP: wiring the chart alone hands the tempo to the COMMONWEALTH for most of the war.**
`state.rommel is None` in the campaign — rule 31 is fully implemented and **has no arrival path**.
So the chart gives the Axis **1** until German land units arrive (5 Le, GT21) and **3** thereafter,
against a Commonwealth on 3 → 4 → 5. Rommel should hold the initiative in **~91%** of game-turns; he
currently holds 50%; wired-without-Rommel the Axis would hold well *under* 50%.
**Wire [7.2] and Rommel's arrival (rule 31, ~GT20–22) IN THE SAME COMMIT.** Rommel is **S** — the
entity, the +1 morale (17.28, correctly applied *outside* the ±3 clamp), the +5 CPA anchor (31.4)
and the Berlin recall (31.5) are all built and tested; there is simply no `EventKind` that creates a
`Rommel`, and **64.51 names him explicitly**. Delete the false "untranscribed chart" docstrings at
`engine.py:208` and `state.py:261` while you are there.

**T0-16 — 64.73's occupation quality-test asks the wrong question at the wrong magnitude.** ✅
`game/campaign_victory.py:72-78` — and its own docstring names the bug:
```python
"""...can trace both Fuel (its per-model rate...) and Ammunition to a reachable dump
   (game.supply.plan_draw over the cpa/2 trace, 32.16)."""
```
Rule **64.73**: occupation requires a combat unit of ≥1 TOE which, **at the end of the game**, has
**Stores and Water for one Week** and **Fuel and Ammunition to fire its weapons three times and move
20 CP**.
The engine tests Fuel at `fuel_rate(u)` (**one turn's rate**, not 20 CP of movement) and Ammunition
at `ammo_cost(u, phasing=True)` (**ONE fire, not three**), and **does not check Stores or Water at
all** — though the rule names them first. And it asks *"can you REACH a dump holding ammo?"* where
the rule asks *"do you HAVE it?"*
**Measured: Giarabub (6 Italian garrison counters) and Derna (a garrison standing on its own supply
dump) score for nobody, in any seed.** Derna's [60.34] dump carries **zero Ammunition**, so the trace
fails — though a garrison sitting on its basic load would pass the rule as written. **30–45 VP are
permanently dead on the table.** Jalo and Siwa likewise.
**The magnitudes are S and can be fixed today.** The *form* of the test ("do you HAVE") is only
expressible once the in-hex supply model lands (49.14 + 53.11) — see **T1-1**.

**T0-17 — The Tobruk convoy is seeded at 3.5× its harbour, and the overflow is annihilated.** ✅
The scenario ships **1500 AMMO** into a harbour rated **425 AMMO/OpStage**, and `engine.py:698-700`
lands `room` and **silently drops the rest**. The un-landed cargo is never credited to
`initial_supply`, **so the conservation invariant (`invariants.py:70-80`) is structurally blind to
it.**
**Measured: 103,308 of 502,224 planned tons (21%) never reach Africa** — 630,500 Fuel Points, 3,846
Ammo, 9,111 Stores. **This is the largest engine-only destruction of supply in the game.**
**56.27** says a player *may not ship over capacity* — it does **not** say the tonnage evaporates. He
would rebalance the 56.22 split, or sail to **Tripoli (15,000 t** vs Benghazi's 2,500).
Seed at or below the rated capacity now (**S**). The real fix is 56.21/56.22 — make the Axis *choose*
the split and the lane — see **T1-9**.
*(Side note the air auditor proved: because the CRT's maximum result is 50% and denying one
Ammunition Point at Tobruk needs a 72% skim, **Malta's interdiction of the Tobruk lanes is
arithmetically inert**. The order in the code is right — bomb at sea, then unload over the quay. The
defect is the seeding.)*

**T0-18 — 59.61's air-facility truck rows are seeded contrary to the rule.** ✅
**59.61**: with the Air Game abstracted, *"ignore all Trucks and supplies available at/for Air
facilities in the initial set-ups."* The engine correctly drops the air-facility **supply**
allotments and then seeds the air-facility **truck** rows anyway ([60.33]'s `Any Air Facility`
10 L / 50 M onto Benghazi; [60.43]'s 5 L / 30 M / 20 H onto the railhead) — `scenario.py:812, 818,
851-854, 866, 876-877, 893`. **Over-seeds Axis +60 TP, CW +55 TP.** The same rule is obeyed for the
supplies and disobeyed for the trucks.
⚠️ **This only holds while air is abstracted. When the Air Game lands, these rows come back** (and
SGSUs need them). **Gate them on the air-game flag; do not delete the data.**

**T0-19 / T0-20 / T0-21 — three small wrong numbers.**
* **22.26** (`engine.py:1488` `_REPAIR_FUEL = 1`): the rule is **ONE Fuel Point per tank TOE
  Strength Point**, expended before rolling. A 10-TOE battalion repairs for **1** Fuel instead of 10.
* **29.45 / 21.37d** (`combat_tables.py:476`): the sandstorm breakdown **+1 column** is applied to
  **every mover unconditionally**. The rule applies it only if **≥50% of the unit's CP was spent in
  sandstorm hexes**. Over-applies.
* **51.13** (`supply.py:189-190`): the rule is *"HQ and engineer units require only ONE Stores Point
  per Game-Turn"* — **flat**. The engine charges `rate × strength`. **It is currently harmless:
  every HQ and engineer counter in the OOB is a 1-step unit (verified: all 22 non-combat units have
  strength 1), and `is_combat: false` correctly selects the noncombat rate of 1.** It becomes a real
  bug the moment rule 19 gives an HQ real TOE (3.31: an HQ "represents the division"). **Fix the
  formula now so it does not bite later.** *(This corrects the 47-57 report — see §7.D3.)*

---

## 3. TIER 1 — THE LOAD-BEARING MISSING SUBSYSTEMS

**This is a CATALOGUE, not a running order. The running order is §6.** Sizes: **S** ≤ 1 day,
**M** = days, **L** = 1–3 weeks, **XL** = 1–3 months.

> 🔴 **Read T1-9 (THE AIR GAME) before you plan around this list.** It was going to be last. It is now
> **Phase 5 of 8**, because with the dice held identical Malta swings **95–320 VP and flips the winner
> on seed 7**, and the number that sets it is a calendar we invented. **The air game is not decoration
> and it is not deferrable.**

---

### T1-1. 53.14 FIRST-LINE TRUCKS + IN-HEX SUPPLY — kill the ½-CPA trace 【L】

**This is the deepest bug in the project.**

**What it is.** `game/supply.py:229`:
```python
budget = unit.cpa / 2
```
✅ That is **rule 32.16** — *the abstract game's supply range*. It fires through **every fuel draw**
(`engine.py:1194`), **every ammo draw** (`engine.py:2690`), stores (`engine.py:830`), water
(`engine.py:895`) and the pasta point (`engine.py:880`). The Logistics Game **has no supply range**:

> **49.15** *"For fuel to be consumed, it must be present in the same hex with the consuming unit."*
> **49.16** *"a unit consumes fuel in the hex in which it begins Movement… It may draw fuel from any
> source in that hex."*
> **50.15** *"Ammunition is consumed only if present in the hex."*
> **51.15** *"Stores must be present in the hex to be used."*

A unit eats from (a) **its own tanks** — 49.14: fuel capacity = **CPA × ⅕ × rate**, a field `Unit`
does not have; (b) **its own organic first-line trucks** — 53.11, the whole reason they exist; or
(c) **a dump on its hex** — 54.11.

**Measured today:**

| Fuel, whole campaign (seed 1941) | Points |
|---|---|
| Landed (Axis convoy + CW rail + Tobruk lanes) | **3,106,208** |
| Evaporated (49.3) | **2,272,976 — 73%** |
| Burnt by lorries (49.18) | 389,465 — 13% |
| **Burnt by the two armies moving (49.13)** | **23,504 — 0.8%** |
| …of which **the whole Panzerarmee, 111 turns** | **1,419** |

**Evaporation is 1,600× the Axis army's entire fuel consumption. Fuel is not scarce; it is merely
leaky. DISTANCE COSTS NOTHING.** That is not the campaign the designer wrote, and it is why the
54.16 dump network is decorative and `Unit.is_first_line_truck` is a dead flag.

**What it needs.**
1. **49.14 per-unit fuel capacity** — a fuel pool on `Unit` (`CPA × ⅕ × rate`).
2. **53.11 first-line trucks** — **~360 Axis + ~177 Commonwealth Truck Points**, seeded hex-by-hex to
   every starting formation per [60.31]/[60.41] (59.42: *"These trucks must be assigned to units in
   their listed hex"*). **That is larger than the 2nd/3rd-line lorry parks we just seeded** (Axis 215
   TP, CW 195 TP). Charted transport vs seeded: **Axis 780 → 215 (28%)**; **CW 372 → 195 (52%)**.
3. **59.66B** — each attached Motorization Point may start loaded with **1 Ammo or 3 Fuel Points**:
   up to **305 Ammo / 915 Fuel** (Axis) and **147 / 441** (CW) sitting *with the troops at the front*,
   which the dump charts do not include.
4. **48 V.C.6 the Supply Distribution Segment** — the **0-CP** window (per the 6.3 chart) in which
   supplies in a hex are redistributed and trucks are loaded/unloaded. It does not exist:
   `grep "Supply Distribution" game/` → nothing. **It is the only beat at which first-line trucks are
   topped up.**
5. **53.24** load/unload CP (2 outside the Organization Phase, **0** inside it) and **53.25**
   no-leapfrogging (cargo carries the CP of the truck that moved it).
6. **54.12's Non-Dump capacity row** (50 Ammo / **0** Fuel / 50 Stores / **0** Water) — transcribed at
   `logistics_rates.json:137`, `grep non_dump game/` → **nothing**. An unconstructed heap a lorry
   drops in the desert currently gets the full Other-Terrain ceiling of **1,500/5,000/1,000/1,000**.
   **56 such heaps were founded in the campaign.** This row is what makes rule 24.9 a *decision*.

**WHAT IT LETS YOU DELETE** — say this out loud, because it is the payoff:
* `supply.py:229` — the 32.16 ½-CPA trace, and every `plan_draw` call site that depends on it.
* `supply.py:103-104` — `SUPPLY_CPA = 15` (32.58A) and `SUPPLY_MOVE_FUEL = 1` (32.24), and
  `engine.py:1629` `_supply_movement` — **the escorted teleporting dump (32.33)**. In the full game
  **a dump does not move.** Supply moves; dumps are places.
* `supply.py:310-355` — `MOTORIZATION_POINTS = 30` (32.32) and the whole MP↔truck exchange, and the
  `motorized_supply` flag that gates it, and `engine.py:1551-1570` `_organization`'s motorization
  body. **`_organization` then becomes what its name says: the rule-19/20 Reorganization Segment.**
* `campaign_policy.py`'s **leapfrog relay** and `_relay_source` (`campaign_policy.py:693`) — a policy
  heuristic that *incidentally* blocks most 53.25 leapfrogs. **It is a policy accident, not an engine
  rule, and a live LLM staff can drive straight through it.** Once 53.25 is an engine rule, delete it.
* The **consolidation constraint** and the escorted-teleport guard at `engine.py:1629` (*"must end
  stacked with a friendly combat unit (32.33)"*).

**What it fixes.** Distance starts costing something. The dump network becomes load-bearing. The
truck haul becomes the Axis's real constraint (which is what the whole campaign is *about*), and for
the first time the fuel economy is *legible* — which is the precondition for judging whether Malta
and the Air Game matter at all. It also makes **64.73's "do you HAVE"** test expressible (T0-16) and
**64.71/64.72's truck-MP traces** meaningful (T1-4).
**Balance direction: unknown until measured. It is the only Tier-1 item for which that is the honest
answer.**

---

### T1-2. THE ORDER OF BATTLE 【L】

**This is the balance problem.** Force ratio **1.72:1 AXIS** at Alamein where the charts give the
**Commonwealth 1.56× the Axis's armour**.

| Measure | Rulebook | Engine | Error |
|---|---|---|---|
| Counters @ GT1 | 3.41 : 1 Axis | 3.31 : 1 | ✅ faithful (Graziani really did outnumber O'Connor) |
| Reinforcement counters | **0.97 : 1 (parity)** | 0.97 : 1 | ✅ faithful |
| **Tank TOE, cumulative** | **0.64 : 1 — the CW has 1.56× the Axis armour** | **1.22 : 1 Axis** | **a 1.9× swing** |
| Gun/AA TOE, cumulative | 1.14 : 1 (near parity) | 1.88 : 1 | +65% Axis |
| **Combat TOE, cumulative** | — | **1.72 : 1 Axis** | the measured figure |

**The mechanism, stated plainly:** the charts give the Axis a large *start-line* edge and then
**parity-or-better for the Commonwealth in the build-up**. The engine reproduces the start-line edge
faithfully and then **fails to deliver the Commonwealth's build-up**. So the September-1940 edge
never erodes, and a campaign the charts intend to swing toward the Commonwealth stays pinned at
1.7:1 Axis for 111 turns.

**Commonwealth: loaded at 32% of its own chart.**

| | engine | chart [4.43a]/[4.44B] | ratio |
|---|---|---|---|
| **Cumulative counters** | **119** | **431** | **28%** |
| **Cumulative TOE** | **673** | **2,121** | **32%** |
| Cumulative gun TOE | 118 | **692** | **17%** |
| GT1 tank TOE | 40 — **all phantom** | 37 | **0% real** |

* **34–36 infantry/motor brigades are modelled as ONE 6-TOE counter each**, where **20.11** gives
  each a brigade HQ **and three battalions** (*"the 6th New Zealand Brigade **(and its three
  battalions)**"* — and 20.11's own worked example is one of the units the engine gets wrong).
  **Shortfall: ~432 TOE.** Worst offenders: `44 Inf Div body` stands for **12 counters / 53 TOE**;
  `4 In Div core` for 7; `Polish Bde` for 8. **44 data counters stand in for 187 rulebook counters —
  understated 3.1×.**
  *(The two auditors count 34 and 36 brigades; the difference is whether "X Bde Grp" rows count.
  Both agree on ~430 TOE and ~3×.)*
* **The 7th Armoured Division has no tanks.** [4.44B] deploys it at GT1 with 6 RTR, 7 Hussars, **1
  RTR**, 8 Hussars = **34 tank TOE**. The engine has three counters for the whole division, and all
  three are the T0-6 misclassifications.
* **NO SHERMAN.** [20.78C] releases **62 Shermans from GT89** — *inside the campaign's own clock*.
  Also missing: Valentine, Crusader I, Crusader III (GT88), Churchill (GT90), A10 (equips 8 Hussars
  at **GT1**), 17-pdr (GT103), Bishop, Deacon, Priest, Scorpion, and **both AA models**. **22 of 32
  Commonwealth weapon systems are absent from `data/unit_stats.json`.** `MODEL_DEFAULTS` forces
  **every** CW artillery unit to `25pdr`, so the 5.5"/60-pdr medium regiments fire as 25-pdrs.
  **Without the Scorpion the campaign has no mine-clearing capability at all** (`90:1329`).
* **`data/oob_italian.json` is a raw VASSAL save extraction** whose counters were fanned out along a
  diagonal for legibility — **not a transcription of rule 60.31**. **The garrisons of the three
  biggest victory cities do not stand in them**: Tobruk Garrison is **4–5 hexes out** (the 200-VP
  fortress is held by a lone HQ counter); Benghazi Garrison is 2 hexes out and **BENGHAZI (75 VP) IS
  EMPTY AT GT1**; Bardia Garrison is 1 hex out. Five more formations are 6–12 hexes off. And
  9.16a's `is_garrison_home` stacking exemption is being granted to units **not in their home hex**.
* **The Ramcke Brigade does not exist.** `grep -rni ramcke game/ data/ scripts/ tests/` → **0 hits**.
  6 counters, Basic Morale **+2**, airdroppable, arriving **GT86–93 — straight into the Alamein
  window**. Also missing: Sonderverband 288, the 300th Oasis Battalion (13 companies — and `oob.py`
  *has* an unused `oasis` role), **8 of the 9 unassigned Italian armoured battalions (~53 tank TOE
  of Italian armour silently deleted)**, all 19 German non-divisional artillery counters, all 22
  unassigned Flak battalions, and the 21 Pz Div HQ (the 5 Le → 21 Pz reorganisation is not modelled).
* **Withdrawals: zero of 32.** [4.43a] mandates **32 mandatory-withdrawal events** (rule 20.8). The
  data has none. **8 arrival-turn mismatches**, the worst **−44 turns**.
* `data/reinforcements_campaign_source.json` is **Axis-only** (176 entries, 0 Allied) —
  **the Commonwealth schedule has no traceable provenance.**

**🔴 MEASURED: build the Commonwealth to its own chart, leave the Axis untouched, and the force ratio
INVERTS to 1.9:1 Commonwealth — the stated balance target, reached by transcription rather than
tuning.**

**Order within T1-2:** (a) T0-6's `classify()` fix **+ an AA role** — but it MUST land with (b);
(b) a Commonwealth gap-fill layer (there is none — the existing `oob_campaign_extra.json` is
Axis-only); (c) the 22 missing models; (d) 20.11 brigade → HQ + three battalions; (e) the Axis
garrison hexes (pure data, no engine change, **and it is 90% of the final score**); (f) the Axis
gap-fill.

🔴 **DO NOT DO THE AXIS HALF ALONE.** That is the BALANCE TRAP: adding the 7 Italian tank battalions,
the Ramcke Brigade and the 3× gun park to the current Commonwealth swings the campaign **harder
Axis**. Build the Commonwealth first or build both together.

---

### T1-3. THE MAP'S TERRAIN 【L — and possibly XL. Spike this first.】

`game/cna_map.py:52` constructs the `TerrainMap` **without passing `hexsides` at all**. ✅
Measured on the campaign map:
```
terrain classes: {CLEAR: 4996, ROUGH: 1072, DESERT: 686, MAJOR_CITY: 10, HEAVY_VEG: 6}
HEXSIDES: 0     roads: 277   tracks: 216   rails: 66   minefields: 0
```
**Consequences — every one of them is code that is already CORRECTLY TRANSCRIBED and never fires:**
* **NO ESCARPMENT.** 8.42 — *"no vehicle may EVER move up an escarpment"* — is coded
  (`terrain.py:83` `UP_ESCARPMENT: (6, PROHIBITED)`) and dead. **There is no Halfaya Pass.** Vehicles
  drive up the Sollum escarpment freely.
* **NO SALT MARSH.** So **there is no Qattara Depression, and therefore no Alamein line.** The most
  important piece of ground in the campaign does not exist.
* **NO MOUNTAIN.** No Jebel Akhdar to slow the Cyrenaica pursuit.
* No wadis (8.41), no ridges, no slopes, no rivers, no gravel, no delta.
* **Only 2 of the map's Major Cities are Major Cities.** [8.37] note 4: *every* major city is a
  **Level 2** fortification; Alexandria and Cairo are **Level 3**. `scenario.py:56`
  `MAJOR_CITIES = {"C4807": 2, "C4321": 2}` — **Tobruk and Bardia only.** Derna, Sollum, Mersa
  Matruh, Sidi Barrani, Barce and Benghazi are all fort level 0.
* **NO MINEFIELDS.** `TerrainMap.minefields` is assigned nowhere. **El Alamein without the Devil's
  Gardens.**
* **All eight hexside combat shifts** and all four hexside anti-armor shifts — transcribed exactly,
  never fire.
* `stacking.py:22` `DEFAULT_HEX_LIMIT = 5  # PLACEHOLDER` — **one invented limit for every terrain.**
  The [8.37] Stacking Points column never OCR'd; two cells leaked (**Major City = 8**,
  **Road/Track = 5**). The rest must be read off the scan. A 5-SP division would fill a clear hex by
  itself.

🔴 **THE BIGGEST UNKNOWN IN THIS PLAN — SPIKE IT BEFORE COMMITTING.** No report says whether the
hexside data (escarpments, wadis, slopes) **exists anywhere**. `data/terrain_A-E.json` only emits
`clear | rough | desert | sea | vegetation`. Memory `vassal-map-source` says the VASSAL source gives
a structured hex grid and a 14310×4632 map image, but says nothing about hexside features. **If the
hexsides can be extracted from the VASSAL map data, this is L. If they must be traced by hand off a
14310×4632 scan, it is XL.** Budget **one day** to find out, and re-scope on the answer.

---

### T1-4. VICTORY — RULE 64.7 【S → M】

**We implemented exactly the subset of rule 64.7 that favours the Axis.**

| instrument | whose win | status |
|---|---|---|
| **64.71** — Axis takes Alexandria + Cairo | **Axis outright** | PARTIAL — implemented |
| **64.72** — from GT35, no Axis unit can trace 60 truck-MP to a Tobruk/Tripoli-fed dump | **Commonwealth outright** | **MISSING** |
| **64.73** — geographic points (Axis 620 max / CW 370 max) | tiebreak | PARTIAL — implemented, wrong magnitude |
| **64.74** — unused Replacement Points (Axis 2,493 v CW 958) | Axis-weighted | MISSING — ⚠️ **LANDMINE** |
| **64.75** — Commonwealth Withdrawal Points | **Commonwealth only** | **MISSING** |
| **64.76** — victory levels by ratio | — | **DONE, and correct** |

**The 64.73 table is *supposed* to be Axis-heavy.** An Axis still holding Cyrenaica at the end is the
"nothing happened" baseline. **The Commonwealth's answer was never to out-point it on geography — it
was to strangle the Axis supply and win outright under 64.72. We removed its only weapon and then
spent weeks measuring the balance.**

And in place of 64.72, `campaign_victory.py:84-88` carries an **invented annihilation rule** (*"Axis
victory by annihilation"* / *"Allied victory by annihilation"*) that is **nowhere in the rulebook**. ✅

**Order: 1 → 2 → 3 → 4 → 5. Build 64.74 LAST, and only after rule 20.**
1. **64.73's quality-test at the right magnitude** (**S**, = T0-16).
2. **64.71's "for one full Game-Turn" persistence** — it currently fires the instant the last hex is
   occupied (**S**).
3. **The ≤90 / ≤60 truck-MP trace to a dump fed from Tobruk or Tripoli** (**M**).
   `supply.reachable_truck_moves` **already exists** — it is simply not wired to victory. Today
   `_supplied()` uses the ½-CPA land trace and **never checks the dump's source at all.**
4. **64.72 — the Commonwealth's Game-Turn-35 automatic win** (**M**, needs 3).
5. **64.75 — Commonwealth Withdrawal Points** (**M**, needs rule 20.9 voluntary withdrawal). ½ pt per
   week per combat battalion at ≥75% TOE voluntarily withdrawn through Alexandria/Cairo, max 3/unit;
   −2 if returned. **It is the CW's only non-geographic VP source and the natural counterweight to
   64.74 — it should land BEFORE it.**

🔴 **WHY 64.74 IS A LANDMINE — quantified.** Pools confirmed transcribed: **Axis 2,493** (German 783 +
Italian 1,710) vs **Commonwealth 958**. There is **no replacement economy of any kind**: the string
`replacement` occurs **once** in all of `game/*.py`, in a deferred-list docstring; nothing spends RPs
and nothing restores lost TOE. So 64.74 alone scores *every* RP as unused →
**Axis 2,493 – CW 958 = 2.60:1 = a Smashing Victory decided at GT0, invariant to play.** Even with the
Commonwealth holding **all ten cities** it is 2,493 – 1,328 = **1.88:1, an Axis Decisive win while it
loses every hex on the map.** **The Commonwealth cannot win.**
**And the asymmetry is a bookkeeping artifact, not a balance dial.** The entire 1,535-point gap is
**infantry** — the Axis has a fixed infantry pool and the Commonwealth's infantry comes from a random
2d6 table (20.78B), *which is exactly why 64.74 excludes infantry "for the Commonwealth Player only"*.
**Like-for-like, dropping Axis infantry too: Axis 893 v CW 958 — the Commonwealth has more.** Guns are
508 v 536, tanks 335 v 332. **Recommendation: implement 64.74 only alongside rule 20, and exclude
infantry for BOTH sides.**

---

### T1-5. RULE 20 — REPLACEMENTS AND COMMONWEALTH PRODUCTION 【L】

**Nothing in this engine has ever put a strength point back into a unit.** Verified structurally: the
only writes to `Unit.steps` in the whole package are `apply.py:241` and `apply.py:398-408`
(`_apply_step_loss`), **both strictly subtractive**. A battalion ground down on GT10 is ground down on
GT111.
*(Trap for a re-auditor: `engine.py:2107` `_idle_recovery` grants "5 RP" — those are **Reorganization**
Points, a cohesion gain, rule 6.24.1. Not a Replacement Point. It restores no strength.)*

**This is the Commonwealth's entire structural advantage, and the engine does not have it.**

> **20.62** *"each Replacement Point is counted against the **Shipping Tonnage** allowance… 10 Italian
> Infantry Replacement Points would need 350 Tons of Shipping."*
> **20.64** *"Replacement Points have priority in Shipping Space over any type of supplies."*
> **20.75** *"The Commonwealth Player **has no Shipping Problems**; his Replacement Points simply
> arrive."*

Every Axis replacement point competes with **fuel and ammunition** for convoy tonnage, at priority
over them, and runs the Malta gauntlet. Every Commonwealth one is **free**.

The charts are fully legible and untranscribed:
* **[20.78B] CW Infantry Production** — a 2d6 roll every turn. Expected yield **≈1,617 Infantry
  Replacement Points across the campaign** — *more than twice the Commonwealth's entire modelled order
  of battle*.
* **[20.78C] CW Equipment Production** — **306 tank replacement points**, including **62 Shermans from
  GT89**; 250 × 25-pounders; 80 × 6-pounders.
* **[20.66] Axis Pool** — German 400 infantry (from GT38) + 131 tank points; Italian 1,200 infantry +
  ~200 tank points.
* **[20.3] Replacement Point Conversion Chart** (`90-charts:1059-1163`) — not in `data/`.
* `data/logistics_rates.json:180` has an unused `replacement_point_tons` key, **read by no Python
  file.**

It also **gates victory rule 64.74** (T1-4) and **64.75** (via 20.8/20.9 withdrawals).

**Scope recommendation:** implement an **abstract replacement economy** — pool + planning lead time +
arrival at a supply city + spend to restore TOE steps + the 20.62 tonnage charge against the convoy —
and **skip the on-map RP counters and the 20.4 training clock for now** (that is the difference
between **L** and **XL**). Rule **17.3/20.43 Training** is a separate M and can follow.

---

### T1-6. MAKE THE LORRY MORTAL 【M】

**Trucks are the binding constraint of this entire campaign, and nothing can kill one.** 380–410 Truck
Points cross the desert for two years and not one is ever lost. Five rules, one theme:

| Rule | Gap | Where |
|---|---|---|
| **21.11 / 53.0** | **Trucks never break down.** `TruckFormation` (`state.py:340-362`) has no `bar`, no `bp_accumulated`, no `broken_down`; `_breakdown` (`engine.py:1459`) iterates `state.living(side)` and a `TruckFormation` is not a `Unit`. The 54.2 chart's **BAR 2L** and the light-truck off-road penalty are **dead data**. | `state.py:340`, `engine.py:1459` |
| **22.23** | The truck field-repair column is **transcribed correctly and never called** — `engine.py:1528` only ever passes `"tank"` or `"ac_recce"`. **It comes alive for free** the moment 21.11 lands. | `combat_tables.py:459` |
| **12.46** | **Barrage destroys trucks.** Declined by the engine **citing 32.56 — an abstract-game rule.** The 12.6 chart's Truck row (`90-charts:716-718`) is untranscribed. **This is an abstract-game bug, not a deferral.** | `combat_tables.py:248-249` |
| **41.32 / 41.35 / 40.62** | **Air destroys zero trucks.** Bombing truck convoys, bombing dumps (*"+1 Truck Point lost for each 10%"*), strafing convoys — none implemented. | (blocked on T0-10's [41.5] CRT) |
| **52.42 / 29.34** | **Trucks never drink and their cargo never evaporates.** `_water_distribution` (`engine.py:892`) iterates `state.living(side)` (Units), never `state.trucks`: **the Axis's 215 and the CW's 195 Truck Points cost ZERO water for 111 turns.** And `_evaporate` (`engine.py:816`) iterates `state.supplies` only — **29.34 is explicit: *"This includes water and fuel in dumps as well as in trucks."*** Parking freight on lorries currently makes it evaporation-proof. | `engine.py:816, 892` |
| **52.45** | **Water is never hauled by truck.** The 54.2 Water column (L 40 / M 100 / H 200) is loaded into `supply.TRUCK_CHARS` and **never used**: the relay hauled **0 Water Points** in 111 turns. **This is the only way an army in the deep desert drinks.** | `supply.py` |

Also here, and free: **49.3's Commonwealth 9% evaporation rate (Sept 1940 – Aug 1941)** is transcribed
at `logistics_rates.json:48` and read by nothing; `_evaporate` has no side parameter at all. **The
campaign opens in Sept 1940, so this is live for ~48 Game-Turns.** *(Balance: toward the Axis, early.)*

---

### T1-7. FORWARD/BACK GUNS + VULNERABILITY — 12.1 and 15.84 【M】

**`Unit.vulnerability` is populated on every unit from the charts (`oob.py:294`) and read by NO engine
code.** `grep vulnerability game/engine.py` → nothing. **Artillery is immortal in close assault: it
cannot be overrun, cannot be lost, cannot be captured.**

**15.84b** is the loss channel the rulebook's own worked example turns on: *Forward guns lose at least
50% as many Vulnerability Points as the side lost Raw Points, minimum 1* (AA/Flak exempt; Overrun hits
all guns). **It is the single largest missing loss channel in the combat model**, and the counterweight
that stops both sides stacking guns forward with impunity.

It cannot be built without **12.11–12.19 Forward/Back** — the same subsystem. Bringing them together
also fixes:
* **12.14** — *Italian* Forward artillery may coordinate **only within the same hex.** Today
  `engine.py:2313` pools firers across hexes with **no nationality test**. Italy is the Axis's artillery
  arm for GT1–20.
* **12.16** — a Back Heavy-Weapons unit **cannot do anti-armor or close assault**. Today every gun
  always fights: **a standing buff to both sides' artillery.**
* **14.13** — Back artillery may not fire anti-armor nor be affected by it.
* **15.13** — Back guns are not affected by Close Assault unless Overrun.

**Adjacent and in the same commit, because it is the same violation:** **15.21 / 14.0** — *"units
assigned to Anti-Armor may not Close Assault."* Today a unit fires anti-armor **and then close-assaults
in the same segment** (`engine.py:2367-2368` admits it), **double-counting every tank battalion's
contribution to the segment.**

---

### T1-8. MAKE CONTACT COST SOMETHING — 8.6 and 10.31–10.36 【M】

**An army can drift up to the enemy, decline battle, and drift away for free.** Three composing bugs:

1. **Break-off is free when stacked.** ✅ `zoc.py:125` `start_cost = break_off if controlled(start)
   else 0.0`, and `controlled()` is False when the hex holds another friendly combat unit (the 10.26
   negator). **Probe: a lone unit pays 2.0 (Contact) / 4.0 (Engaged); the SAME unit stacked with one
   friendly combat unit pays 0.0 in both cases.** And since a lone SP-1 battalion exerts no ZOC at all,
   **every real front-line stack qualifies.** 8.67 (*"when ALL of the Friendly units that were in
   Contact… Break Off"*) proves the book expects each unit in a stack to be in Contact and to pay.
   10.26's negation is correct for *through-movement* and is being over-applied to the break-off cost.
2. **10.31–10.36 do not exist.** *You MUST attack an enemy hex whose ZOC touches you, or Hold Off with
   a barrage (10.34's ≥1 Actual Barrage Point per enemy non-Gun battalion), or retreat 3 hexes, spend
   all your CP and take 3 DP.* `grep "10.3|must attack|holding.off" game/` → **zero hits.**
   **This is the friction the whole operational game is built on.**
3. **The CP economy leaks at both ends.** **11.25** — *CP expenditure applies to ALL units in the hex,
   even those that did not participate* — is not implemented: a stack attacks with one battalion and
   the other four keep their entire CPA **and their movement**. **8.12/15.82** — a retreat **still costs
   CP** — is not charged (`engine.py:2611` admits it). **A routed unit pays nothing, earns no
   Disorganization, and keeps its whole CPA.**

Cheap and in the same commit: **8.53a** — `engine.py:1297` requires `u.mobility == Mobility.MOTORIZED`
✅ where the book bars only **NON**-motorized units, **locking all 39 tanks and all 8 armoured cars out
of Reaction** — including the CPA-45 recce battalion the rulebook itself uses as its example reactor.
**Honest caveat: this changes nothing today** — `campaign_policy.py` implements no `react_to` and the
campaign logs **0 REACTION_MOVED**. It is a latent bug, not a live one.
And **6.24.2** — *+3 Reorganization Points whenever your close assault empties the enemy hex* — is
missing, so only **idle** units recover cohesion; and **6.26** (*Cohesion −26: may not move, attack or
defend; surrenders if an enemy moves adjacent*) is **enforced nowhere** except the ZOC clause.
Units finish the campaign at −27, −31, −37, −52, −68 and keep moving and fighting.

---

### T1-9. THE AIR GAME 🔴 【XL — AND IT IS NOT OPTIONAL. IT MAY BE THE LARGEST LEVER ON BALANCE.】

**The air game is ~157 lines of executable code standing in for 1,487 lines of rulebook across fifteen
chapters** — **7 DONE, 13 PARTIAL, 204 MISSING, 6 WRONG.** No aircraft, no squadrons, no air bases,
no pilots, no flight, no maintenance, no air-to-air, no flak. **It is not the full Air Game (33–46)
and it is not the sanctioned abstract Air Game (58) either. It is a third, invented thing.**

**And `oob.classify()` (`oob.py:106-111`) ACTIVELY DISCARDS every SGSU and air-facility counter the
OOB hands it** — `data/oob_italian.json` and `data/oob_desert_fox.json` carry **10 Air Strips, 10
Airstrips, 2 Alighting areas and 4 SGSUs**, and the loader throws them on the floor. `data/unit_stats.json`
contains **zero aircraft**.

🔴 **THE MEASUREMENT THAT CHANGES THE PRIORITY OF THIS WHOLE CHAPTER.** The air audit originally
concluded that Malta was *causally inert* — cranked to the CRT ceiling it denied 342,000 Fuel Points
and *"the victory score does not move."* **THAT WAS A DESYNC ARTEFACT (T0-0) AND IT IS FALSE.** With
the dice stream held identical:

| seed | Malta OFF-equivalent | Malta MAX | swing |
|---|---|---|---|
| **1941** | CW Marginal 120 – 180 | CW **SMASHING** 75 – 230 | **~95 VP** |
| **7** | **AXIS SMASHING 300 – 10** | **CW Marginal 100 – 130** | **~320 VP — THE WINNER FLIPS** |

**Malta is one of the strongest levers in the engine, and it is the historically correct one.** The
strangling of Axis shipping from Malta is a large part of why the Axis lost North Africa.

**Which makes the following intolerable.** The number that *sets* that 320-VP lever today is
`scenario.py:1060`:
```python
def _malta_bomb_points(gt: int) -> int:      # a hardcoded calendar. WE MADE THIS UP.
    if year <= 1940: return 100
    if year == 1941: ...  return 500          # "Force K at its peak"
    if month <= 4:  return 0                  # "the Luftwaffe blitz"
```
Its own docstring calls it *"a primary calibration lever for the Axis faucet."* **It has no producer**
(no aircraft, no airfield, no level, no squadron — the Bomb Points are typed in), **no Axis input**
(the Axis literally cannot raid Malta; the Jan–Apr 1942 suppression is not *earned* by the Luftwaffe,
it is written into an `if`), and **no feedback** (nothing the CW does strengthens Malta, nothing the
Axis does weakens it).

**Delete the entire air force from the campaign state and convoy interdiction is byte-identical** —
`_interdict` reads `state.interdictions` and **never once reads `state.air`**; the campaign seeds
**zero SEA-arena air wings**. **Malta's bombs are flown by no aircraft.**

**So: the single largest measured determinant of who wins this campaign is a function we invented, and
it is causally disconnected from every aeroplane in the game. That is the whole thesis of "stop
inventing things", in one object.**

**The good news of the whole audit: the charts to build it are almost all present.** [41.5] is on PDF
p107; [46.3] and [58.5] were recovered from PDF p108; the Aircraft Characteristics Charts, the Refit
Table, the Strafing Table, the Malta charts ([44.41], [44.42], [44.5]) and the Recon tables are all
already in `docs/rules/90`. **The blocker was never the data.**

**SCOPE RECOMMENDATION — split the chapter.**

**The CAUSAL CORE (L) — port this:**
* **[41.5], all 8 rows** (= T0-10) and the three bombing missions rolling on it.
* **34.17 / 38.21 / 38.24 — aircraft consume Fuel Points, drawn from the air-facility dump.**
  🔴 **Measured: the Axis lands 1,884,000 Fuel Points at Benghazi over 111 turns and keeps 100% of
  them. The Axis air force is fed on air.**
* **36 — Air Facilities** (capacity levels, reduced by bombing, an airfield is a dump for its SGSUs).
  `oob.classify()` (`oob.py:106-111`) **currently discards every Air Strip / Airstrip / Alighting /
  SGSU counter at load**, and `data/oob_italian.json` **has them** (10 Air Strips, 10 Airstrips, 2
  Alighting areas, 4 SGSUs).
* **35 — SGSUs** (35.14: 1 Stores/GT + 1 Fuel + 1 Water per OpStage; without them, no refit).
* **38 — Aircraft Maintenance / the Refit Table.** *This is the throttle on the sortie rate*, and its
  absence is why an `AirWing` can fly the same 6 strike points every OpStage for 111 turns. 38.35's
  refit DRMs (**+2 Italian planes, +1 German**) are the rulebook's model of Axis serviceability — a
  large, historically-loaded asymmetry we currently give away for free.
* **44 — MALTA AS A PLACE**, with the two-way loop the whole air game exists for: Malta's facility
  levels → **18 planes per level (44.14)** → bomb points over the convoy lanes → the [41.5] CRT → % of
  the Axis convoy destroyed; and back the other way, the Axis spends from a **fixed budget** (64.52 →
  [44.41] campaign row: **Level I unlimited, II × 25 turns, III × 12, IV × 12**) to raid Malta and
  knock its levels down, while the CW rebuilds them on the [44.5] table. **Today the Axis literally
  cannot attack Malta. The arrow only points one way.**
* **41.32 / 41.35 — bombing trucks and dumps** (part of T1-6).
* **39.19** — *one mission per plane per OpStage; a plane flying in an OpStage may not fly in the
  Strategic Phase.* **This is the Axis's central air dilemma: Malta OR the desert.** Our LAND wing and
  the (nonexistent) SEA wing never compete for the same airframes.

**The DETAIL TAIL (defer, and say so): 40 (fighter combat), 45 (air-to-air), 46 (flak), pilots,
maneuver, night missions, torpedoes, paradrops.** The air auditor's own caveat is the right frame:
*individually these are dogfight detail; collectively they are the attrition engine that makes an air
force a wasting asset.* **`AirWing.fighters` is a constant that never dies.** Something must kill
aeroplanes eventually — but it need not be 45.0 in full and it need not be first.

**SIZING — and the good news.** The air game is **PORTABLE. The blocker was never the data.**
* The **[41.66] convoy-bombing CRT is transcribed EXACTLY** — verified cell-by-cell against the scan,
  every column partitioning all 36 sequential 2d6 codes. The one air chart we have, we got right.
* **Nearly every other air chart is already OCR'd in `docs/rules/90`**: the three Aircraft
  Characteristics Charts (`:1691`, `:3609`, `:3638` — header shifted, data intact), the Refit Table
  (`:1354`), the Strafing Table (`:901`), the Scramble Table (`:1382`), the Recon tables (`:1390`,
  `:3531`), the Flak Adjustment Chart (`:1436`), the Maneuver and TacAir Kill charts (`:1428`,
  `:1445`), and **all three Malta charts** ([44.41] `:6002`, [44.42] `:6016`, [44.5] `:5954`).
* The **two that were missing from the OCR corpus entirely** — **[46.3]** (the AA Combat Results
  Table) and **[58.5]** (the Abstract Truck Loss Chart) — **were recovered from the scan at PDF p108.**
* **The [41.5] Air Bombardment table is only 1/8th transcribed** (PDF p107) — **and that is precisely
  WHY `_air_port`, `_air_fort` and `_air_strike` roll no dice: there was no table for them to roll
  on, so they invented flat results instead.**

🔴 **A RULING YOU MUST NOT GET WRONG: DO NOT IMPLEMENT 58.3.** The air report's TOP-FIVE #1 recommends
it ("the Axis loses ¾ of all fuel at the instant of unloading — 8 lines of code"). **Its own §"Which
air game are we entitled to play?" section proves that 58 is exclusive with the Air Game, exactly as
47/32 are exclusive with the Logistics Game**, and its own TOP-FIVE #4 says *"I would go straight to
[rule 44] and skip the fork."* **The report contradicts itself.** 58.3 is an **abstract-air rule**;
adding it would be adding a *new* instance of precisely the bug class we are purging. **The full-game
equivalent — aircraft burn Fuel Points out of the air-facility dump (34.17/38.24) — delivers the same
causal effect and IS on the port path.** If you want the *measurement* today, run 58.3 on a throwaway
experiment branch. Do not put it in the engine. *(See §7.D1.)*

---

### T1-10. RULE 19 — ORGANIZATION AND KAMPFGRUPPEN 【M–L】

**The entire chapter is missing.** There is **no `parent`, `attached_to` or `assigned_to` field on
`Unit`.** `engine.py:1551` `_organization` is named for the Organization Phase and its docstring opens
*"[32.32] THE ORGANIZATION PHASE: detail lorries to carry a depot"* — **it attaches Motorization Points
to supply dumps and never touches a combat unit.**

**This is WHY the 15.52/15.53 org-size rules are inert: no division ever forms.** Every combat counter
is SP 1, so `org_size_shift(1, 1)` is always 0 — the chart is transcribed EXACTLY and can never fire.
It also blocks **9.21–9.28** (divisions, brigade-equivalents, shell units), **6.15/6.28** (a Parent
Formation's CPA), **3.31–3.36** (HQ semantics), **19.61–19.68** (rebuilding depleted units — the
absorption path rule 20's Replacement Points need), and **19.71–19.73 Axis Battle Groups
(Kampfgruppen)** — *the German player's signature tool, and the only way to build a 2-SP formation,
i.e. the only way to make 15.52/15.53 fire at all.*

Depends on: T1-2 (the OOB must carry the parent tree from [4.44]/[4.45] before there is anything to
attach). Gates: T1-5's 19.68/20.49 absorption.

---

## 4. TIER 2 — THE MISSING CHAPTERS

| Chapter | What it is | Campaign-criticality | Size | Notes |
|---|---|---|---|---|
| **16 — Patrols** | The only way to buy information back. There is no `Phase.PATROL`; the sequence loop has no patrol beat. 16.16 charges **1 Ammo + 2 Fuel per Patrol Point** — a real supply drain nobody pays. | **MEDIUM.** It is the counterpart to rule 3.6's limited intelligence: *the rulebook hides information and 16.5 is the only way to buy it back.* Neither side exists. | **M** | Three charts (16.6/16.7/16.8) already OCR'd. |
| **19 — Organization** | See **T1-10**. | **HIGH** | M–L | *Promoted to Tier 1.* |
| **26 — Minefields** | `TerrainMap.minefields` is assigned nowhere. **No construction path (24.3), so no minefield can ever come into being.** 26.21's *"+CPA to enter an enemy minefield"* — a motorized unit spends its **entire allowance** to enter one hex — is the whole operational point, and it is absent. | **HIGH — El Alamein without the Devil's Gardens.** | **L** | **Blocked on T1-3** (terrain), 24.3 (construction), engineers (23.14: no HQ carries an "E") and the **Scorpion** model (T1-2). |
| **27 — Desert Raiders** | Zero code. `grep lrdg\|SAS\|raider` → 0 hits. | **LOW — except two rules.** The designers themselves call raiders operationally marginal. **27.52 (blow a water pipeline)** and **27.55 (raid a supply dump — 10% of its supplies)** attack the supply chain the whole campaign turns on. | **M** (S for just 27.52 + 27.55) | `ROMMEL_CAPTURED` is declared in `events.py:270` and never emitted. |
| **28 — Prisoners** | Zero code. The CRT's `Capt` result *"just records that some already-counted losses are prisoners, no board effect"* (`combat.py:20-21`). | **MEDIUM — one rule.** **28.15: one Store Point per five Prisoner Points per OpStage, expended before any other stores.** CNA's campaign is full of big bags (Beda Fomm, Gazala, Tobruk '42) — **the winner of an encirclement should be *punished* logistically, and here he is not.** | **S–M** | [15.89] Prisoners Captured table is charted and untranscribed. |
| **30 — The Mediterranean Fleet** | A **fully-built, fully-tested subsystem that has never been switched on.** `NavalUnit(` is constructed in exactly one place in the repo: `tests/test_naval.py:44`. **64.51 names the Fleet by name.** | **HIGH for 30.5** | **S to seed** / **L for 30.5** | **30.5 (naval transport of troops between ports) is the real Tobruk sea lifeline**, which the engine currently fakes with a hand-seeded convoy. **30.17 — the San Giorgio operates as an artillery unit** in Tobruk harbour: the harbour-blocking half is live, the gun half does not exist. |
| **31 — Rommel** | **Fully implemented. Not in the campaign.** `state.rommel is None`; `ROMMEL_ANCHORED`, `ROMMEL_MOVED`, `ROMMEL_RECALLED` all **0** across 111 turns. **There is no door for him to walk through** — no `EventKind` creates a `Rommel`. He lands in Feb 1941 (~GT20–22). **64.51 names him by name.** | **HIGH** | **S** | **Must land with T0-15 (initiative).** |
| **15.84 — Vulnerability** | See **T1-7**. | **HIGH** | M | *Promoted to Tier 1.* |
| **21.11 / 12.46 — the mortal lorry** | See **T1-6**. | **HIGH** | M | *Promoted to Tier 1.* |
| **17.3 / 20.43 / 60.47 — Training** | `grep training\|trained game/` → **zero functional hits.** Units needing training have **two** Basic Morale ratings; the parenthesized one is the **Untrained** rating on arrival. `state.py:49` has a single `morale: int` — **the model cannot express it**, and `reinforcements_campaign.json` grants the **trained** value free on arrival. Six OpStages of training raise it one point (17.34), at Cairo/Helwan/Alexandria/Amiriya/Abouqir/Deghelia only. | **MEDIUM** — a free morale gift to the Commonwealth on every arrival. | **M** | [17.6] Training Chart is OCR'd. Also gates 20.43 (RPs must be trained: Gun 1 / Infantry 3 / Tank 6 OpStages). |
| **22.3 — Repair Facilities** | No facility entity exists. **A broken tank sitting in Cairo repairs at the FIELD rate.** The Temporary/Major columns (50/33/25/25/10/10 and 75/50/50/50/33/33/25/10) and the die modifiers **are transcribed in `data/breakdown_rates.json` and nothing reads them.** | **HIGH — this is the Commonwealth's entire rear-area recovery economy.** | **L** | Needs 24.8 (constructing Temporary Repair Facilities: 250 Stores + 150 Fuel). |
| **24.3 / 24.4 / 24.5 / 24.8 — Construction** | Only **2 of the Construction Chart's 15 rows exist** (Railroad, Real Supply Dump). **Neither side can build or rebuild a fortification, ever** (24.4). **There is no way for a minefield to enter the game** (24.3). The 1 SA Road Construction Bn sits idle for 111 turns. **23.14: no HQ in any OOB carries an "E"**, so the chart's `CHQᴱ`/`HQᴱ` rows are unbuildable by anyone. | **HIGH** | **L** | The full [24.17] chart is transcribed from the scan in the 21-31 report. Two rulebook contradictions to rule on — see §8. |
| **55.2 — Blocking / unblocking harbours** | Nothing. `HARBOUR_BLOCKED` is a **static frozenset**, not a state. **No player may ever block or unblock a harbour.** The Axis historically scuttled Benghazi. | **MEDIUM — a live strategic lever neither AI has.** | **M** | Also fixes **55.18**: regen is `1/Game-Turn` where the rule says `1/OpStage` (⅓ the rate), it regens **unconditionally** (the *"did not lose levels to bombs this stage"* test does not exist), and the exemption is hardcoded so **bomb** damage at Tobruk is permanent (it should regen) while a **scuttled** Benghazi would regen (it should not). |
| **56.3 — Axis coastal shipping** | Nothing. `grep "coastal ship" game/` → nothing. | **HIGH — it is the Axis's ONLY way to move tonnage between African ports without lorries.** Benghazi's landed freight can currently *only* go forward on the 60.33 lorry park. | **M** | 60.35 seeds them all in Tripoli. |
| **54.4 — Axis use of the CW railroad** | Explicitly deferred and flagged. **The Axis has no railway at all — it hauls from Benghazi by lorry for 111 turns.** | **HIGH — it is the Axis's only lever against the CW's rail asymmetry, and the reason his 1942 advance historically stalled.** | **M** | 5 contiguous controlled rail hexes + 250 Stores / 100 Fuel of imported rolling stock buys 300 t/OpStage. |
| **8.7 / 48 V.K — rail movement of UNITS** | The railway hauls **freight only**. No unit ever rides a train. | **MEDIUM — the Eighth Army walks to Alamein.** | **M** | Note **8.19**: no Commonwealth land unit may ever be west of Marble Arch (A2109). Also unimplemented. |
| **52.2 — Player-built pipelines** | The standing CW rail-as-pipeline is seeded and correct. **Player-built pipelines are missing, so the Axis can never extend water forward** — which is exactly the constraint 52.2 exists to let him relieve. | **HIGH for the Axis** | **M** | Also **52.3**: an oasis should give **unlimited Stores** as well as water; `wells.py` hard-sets `stores=0`. |
| **52.13 / 52.16 / 52.17** | No water-draw die (52.7 table, 1 CP), no depletion, **no poisoning (1 CP, roll a 1) and no sweetening (5 CP)** — *a cheap, permanent way to deny a desert axis, and neither AI has it.* | MEDIUM | **M** | |
| **51.23 — Half rations** | Missing. **It is the player's answer to a stores crisis, and he has no other.** | MEDIUM | **S** | Cut 4 → 2 Stores, at the cost of never voluntarily exceeding CPA and never voluntarily entering an EZOC. |
| **56.21 / 56.22 — the Axis convoy decision** | `_campaign_axis_cargo` does the 56.4 × 56.5 × die × 54.5 chain **correctly — but at scenario construction, from a seeded RNG.** `_CONVOY_SPLIT_56_22 = {FUEL 0.60, AMMO 0.25, STORES 0.15}` is **hard-coded**. **It is the Axis player's single most important recurring decision, and it is a constant.** | **HIGH** | **M** | Needs a Naval Convoy Planning Phase (48 III), planned **one Game-Turn in advance**. |
| **48 V.D — convoys land once per Game-Turn** | The rule says **every Operations Stage**. `engine.py:149-150`: `if stage == 1`. **A port's per-OpStage capacity is exercised ⅓ as often as the book allows, and 55.18 regen fires once per GT instead of three times.** | **HIGH** | **S** | Interacts with T0-3 and T0-9. Fix all three together. |

---

## 5. THE ABSTRACT-GAME PURGE

**This is a category of bug, not a list of bugs, and it needs one owner.**

Section 32's own General Rule: *"This Section applies if the Players are playing the Land Game
**without** the Air and Logistics Games… Players will not receive any trucks but rather receive
Motorization Points."* Section 47 modifies §32. Section 58's Commentary: *"This Section covers the
rules required for the Players to play the Land and Logistics Games **without utilizing the Air Game
rules**."*

The four-cell matrix:

| Playing | Abstraction to use |
|---|---|
| Land only | **32.0** |
| Land + Air, no Logistics | **47.0** |
| Land + Logistics, no Air | **58.0** |
| **Land + Logistics + Air — what we build** | **NONE. 33–46 and 48–57 in full.** |

**So: 32, 47 and 58 are all out of scope, and any of their rules currently in force is a BUG.**

### 5.1 Abstract-game rules illegitimately IN FORCE

| # | Abstract rule | Where (verified ✅) | Full-game replacement |
|---|---|---|---|
| **A1** | **32.16 — supply traced within ½ CPA** | `supply.py:229` (`budget = unit.cpa / 2`) ✅ → every draw: fuel `engine.py:1194`, ammo `engine.py:2690`, stores `engine.py:830`, water `engine.py:895`, pasta `engine.py:880`. Cited by name at `engine.py:481, 501`. | **49.15 / 49.16 / 50.15 / 51.15 — supply must be IN THE HEX.** Plus 49.14 (the unit's own tanks) and 53.11 (first-line trucks). = **T1-1.** |
| **A2** | **32.13 — captured supplies "used immediately and freely"** | `engine.py:1734` `_capture_dumps` (docstring quotes 32.13); `apply.py:125` ✅ flips 100%. Cited at `engine.py:165, 172, 176, 619, 623`. | **50.16** (only ⅓ of captured Ammo usable, round up; the rest LOST) + **51.16** (only 50% of Stores). Fuel is free (49.19). = **T0-12.** |
| **A3** | **32.32 / 32.51 — 30 Motorization Points to move a dump** | `supply.py:310-355` ✅ (`MOTORIZATION_POINTS = 30`); `engine.py:1551-1570` `_organization` ✅ (its docstring states the contradiction and rides through it). | **53.12 + 54.11/54.35** — a truck convoy LOADS, DRIVES at convoy CPA 30/40, UNLOADS, and the load *is* a dump where it stops. **No escort, no reservation, no thirty.** *(32.51 is **not** an exchange rate — it is a note inside the abstract rules telling you to treat the MPs you were issued **instead of** trucks as medium truck points. Charging 30 Medium Truck Points is a hybrid rule that appears nowhere in the book.)* |
| **A4** | **32.3 / 32.33 / 32.58A / 32.24 — the escorted teleporting dump** | `supply.py:103-104` ✅ (`SUPPLY_CPA = 15` ← 32.58A; `SUPPLY_MOVE_FUEL = 1` ← 32.24); `engine.py:1629` `_supply_movement` (*"must end stacked with a friendly combat unit (32.33)"*). | Same as A3. **In the full game a dump does not move.** A depot 15 CP behind the spearhead every OpStage, for 1 Fuel Point, is the abstract game's counter-shuffle. |
| **A5** | **32.56 — "barrage never hits trucks"** | `combat_tables.py:248-249` ✅ — the engine **declines to implement rule 12.46 by citing 32.56.** | **12.46 — every barrage rolls a second time for the target's Trucks**, and motorized infantry lose their trucks too. The 12.6 chart's Truck row (`90-charts:716-718`) is untranscribed. **This is a WRONG, not a deferral.** = part of **T1-6.** |
| **A6** | **32.15 — dump-capacity overflow is silently annihilated** | `engine.py:642` ✅ (*"overflow is simply never credited, a miniature port throttle"*); `engine.py:601-613` (rail overflow). | **54.12** capacity is a *ceiling*, not an incinerator — and **56.27** says a player may not *ship* over capacity, not that the tonnage evaporates. = **T0-17.** |
| **A7** | **32.63–32.66 — the abstract convoy-bombing chart** | `engine.py:368, 421` ✅ cite `32.63–32.66` for `_interdict`. The **41.66 CRT** it rolls on is correct and exact; but the **bomb-point producer** is `_malta_bomb_points`, which is **neither 32.66 nor rule 44**. | **41.62 / 41.64 / 44** — bomb points are the sum of the **bombload capacities of the planes that actually fly**, and the CW may only attack a convoy he has **LOCATED** (42.5 recon). = **T1-9.** |
| **A8** | **Stale 32.x citations over full-game code** *(harmless, delete so a future audit does not false-positive)* | `observation.py:146, 216` (cite 32.21); `engine.py:2425` (cites 32.21); `engine.py:574` (cites 32.14). | The code under all three **is** the full-game rule. Just fix the comments. |

### 5.2 THE INVENTIONS — things in the engine that correspond to NO rule at all

*"Let's stop inventing things."* Here is the list.

| # | Invention | Where | The rule it displaces |
|---|---|---|---|
| **I1** | The **d6 air-superiority roll** and `AIR_SUPERIORITY_LOSER_SCALE = 0.5` | `engine.py:45, 957-979` ✅ | **Corresponds to no rule in the book** — not in 45, and not in 58 either (ch.58 has no air-to-air mechanic of any kind). |
| 🔴 **I2** | **`_malta_bomb_points` — a hardcoded month-by-month Bomb-Point schedule. MEASURED WORTH: ~95 VP on seed 1941, ~320 VP on seed 7, where it FLIPS THE WINNER. This is the single most consequential invention in the engine.** | `scenario.py:1060-1079` ✅ | **64.52 → [44.41]** (campaign row: I unlimited / II × 25 GT / III × 12 / IV × 12), producing bomb points from **planes that actually fly** (44.14: 18 planes per facility level). Its own docstring calls it *"a primary calibration lever for the Axis faucet"* — **and it is, which is exactly the problem.** |
| **I3** | `DEFAULT_HEX_LIMIT = 5  # PLACEHOLDER` — one stacking limit for **every** terrain | `stacking.py:22` ✅ | The **[8.37] Stacking Points column** (Major City 8, Road/Track 5 leaked through the OCR; the rest must be read off the scan). |
| **I4** | `FORT_CA_SHIFT = -2`, applied as `level × -2` | `combat_tables.py:328` ✅ | **[8.37]: L2 / L3 / L4.** = T0-8. |
| **I5** | The **annihilation victory** (*"Axis victory by annihilation"* / *"Allied victory by annihilation"*) | `campaign_victory.py:84-88` ✅ | **Nowhere in the rulebook.** It sits where **64.72** should be. |
| **I6** | `_batter_fort` / `BARRAGE_HITS_PER_FORT_LEVEL` — "N effective hits reduce a fort level" | `engine.py:2345` | **12.5** (barrage against facilities) resolved on the **[41.5] CRT**. And it is gated behind `siege_rules`, **False** in the campaign — so nothing can reduce a fort at all. |
| **I7** | `_air_port` (flat −1 level), `_air_fort` (always succeeds), `_air_strike` (pins exactly 1 unit) — **none rolls a die** | `engine.py:1015, 1039, 1057` ✅ | **The [41.5] CRT, which was never transcribed.** = T0-10. |
| **I8** | `_air_recon` reveals **everything** in the hex | `engine.py:1086-1099` | **42.23**: roll 1d6 on the [42.27] table; the result is the **number** of battalion-equivalents revealed (0–8). We are strictly more generous than the rulebook. |
| **I9** | `_barrage_target` returns the **strongest** unit in the hex | `engine.py:2286-2290` | **12.23/12.24: barrage is BLIND.** The defender states only the target's **class**. The firer currently gets perfect information and always hits the biggest thing. |
| **I10** | Wells are minted **once per side** — `AX-Well-X` *and* `AL-Well-X` on the same hex, each with the full pool | `wells.py` | The map holds **2× the charted water** (504,000 points where the geography holds 252,000), and both armies can drink the same well dry independently. Flagged in-module; still a mint. |
| **I11** | ~~`_CONVOY_SPLIT_56_22 = {FUEL 0.60, AMMO 0.25, STORES 0.15}` — a fixed split~~ **✅ DELETED, Phase 5.5.** The constant is gone; the scenario schedules only the 56.4 × 56.5 **tonnage** and `engine._convoy_planning` takes the split from `Policy.convoy_plan` one Game-Turn ahead (56.0/56.21). | ~~`scenario.py:406`~~ | **56.22**: the Axis splits his tonnage **as he wishes**. It is his single most important recurring decision. *(The base `Policy` still defaults to 60/25/15 — flagged in place as an opinion a commander may hold, not a law of the world; the campaign Axis overrides it with a board-reading doctrine. `relay._TRUCK_LOAD_MIX` keeps the same three numbers for the unrelated question of how a **lorry** apportions its own capacity, under its own name and its own flag.)* |
| **I12** | The **largest**-unit cohesion | `engine.py:2569` ✅ | **6.27: AVERAGE all equally-largest units.** = T0-5. |
| **I13** | `_CW_WATER_PROXY = 1600` | `oob.py:41` ✅ | **[60.44] grants no water at all.** |
| **I14** | `water_cost = base + 1` when hot | `supply.py:200` ✅ | **29.35: DOUBLED.** = T0-7. |
| **I15** | `_REPAIR_FUEL = 1` per repair **attempt** | `engine.py:1488` | **22.26: 1 Fuel Point per tank TOE Strength Point.** |
| **I16** | `HARBOUR_BLOCKED = frozenset({"PORT-Tobruk"})` — a hardcoded id set | `engine.py:65` ✅ | **55.25** (a starting condition: the San Giorgio, −3 levels) and **55.2** (a *player action*: engineers scuttle for 25 Ammo + 10 Stores). |
| **I17** | `tactics.py:69` — a **2× CPA hard ceiling** on motorized units | `tactics.py:69` | **8.16 has no ceiling above CPA 10.** (Self-limiting in practice; the run shows it binding at exactly 50.0 CP.) |
| **I18** | `engine.py:1307` — **8.54 inverted.** The book's rule is an *exception* that RESTORES reaction to a big unit; the engine turns it into a standalone **denial**. | `engine.py:1307` ✅ | **8.54.** Inert today (every unit is SP 1), live the moment rule 19 forms a division. |

---

## 6. THE RECOMMENDED ORDER OF WORK

Sizes assume **one person**. **⏱** is a working-days estimate, honestly.

---

### 🟥 PHASE 0 — THE INSTRUMENT ⏱ **3–5 days** — **NOTHING ELSE HAPPENS FIRST**

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **0.1** | **T0-0 — INDEPENDENT, DETERMINISTIC RNG STREAMS PER SUBSYSTEM.** Weather / initiative / combat / breakdown / repair / demolition / interdiction / air / recon, each seeded from the master seed, so a die drawn (or **not** drawn) in one subsystem cannot shift what any other subsystem sees. | — | 3 |
| **0.2** | **Re-baseline the two byte-locked benchmarks** (`rommels_arrival` `9339d2b308d7`, `siege_of_tobruk` `5ba4da88d107`). **They WILL break. That is expected and accepted — the owner has agreed to drop the byte-lock. Retire it and stop treating those hashes as constraints.** The byte-lock was good discipline for a walking skeleton and it became the thing that broke the measurements. | 0.1 | 1 |
| **0.3** | **Adopt the N-seed protocol.** A balance claim is a **distribution over N ≥ 30 seeds**, not a single-seed outcome. Wire it into `scripts/measure_campaign.py`. Three seeds is not a measurement. | 0.1 | 1 |

> ### 🟥 GATE 0 — **YOU MAY NOW MEASURE AT ALL**
> Before Phase 0, **no A/B comparison in this project is valid**, and one of them (*"Malta is causally
> inert"*) was not merely wrong but **had already been written into project memory as a settled dead
> end.** **Purge it.** Re-run anything that was measured by toggling a die-drawing feature (§2.1).

---

### 🟩 PHASE 1 — TIER 0 ⏱ **10–14 days**

> *Every item is a number we got wrong or never read.*

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **1.1** | **T0-5 cohesion averaging (6.27).** *Do this first of the rules fixes.* Until it lands the CRT barely rolls: 20 of 36 assaults end in a morale surrender before a die is thrown for losses. **Combat is not being simulated.** | Ph 0 | 1 |
| **1.2** | **T0-1 repair 100 → 10**, T0-8 fort shift, T0-14 air immunity, T0-19/20/21. Pure numbers. Re-pin `data/breakdown_rates.json`. | Ph 0 | 1 |
| **1.3** | **The supply-faucet block: T0-2** (60.34/60.44 pools) **+ T0-3** (one shared tonnage budget — **and update `tests/test_ports.py:110`, which locks the bug in**) **+ T0-4** (three port Efficiency Levels) **+ T0-12** (tax captured supply) **+ T0-7** (hot water doubles) **+ T0-17** (re-seed the Tobruk convoy). | Ph 0 | 3 |
| **1.4** | 🔴 **TRANSCRIBE THE [41.5] AIR BOMBARDMENT CRT — ALL EIGHT TARGET ROWS** (PDF p107) and make `_air_port` / `_air_fort` / `_air_strike` **roll on it**. *This is a Tier-0-class job — a chart we never read — and it is the highest-leverage transcription in the project.* It kills three inventions (I7), unlocks four MISSING rules (41.32 trucks, 41.35 dumps, 41.36 air facilities, 41.38 rail/road), **and unblocks 12.5 — the missing fort-reduction mechanism.** Delete `_batter_fort` and `siege_rules` (I6). | Ph 0 | 4 |
| **1.5** | **The Tobruk-harbour block: T0-9** (one sortie per OpStage) **+ 48 V.D** (convoys arrive **every** OpStage) **+ 55.18** (regen per OpStage, only if not bombed this stage). *These interlock with 1.3 and 1.4; do them together or you will chase the 595.* | 1.3, 1.4 | 1 |
| **1.6** | **T0-15 initiative + Rommel's arrival, IN THE SAME COMMIT.** Wiring [7.2] without Rommel hands the tempo to the Commonwealth. Delete the two false "untranscribed chart" docstrings. | Ph 0 | 2 |
| **1.7** | **T0-11 weather as a per-section map.** Fixes six couplings at once. Add **29.53** (rainstorms refill depleted wells) while you are in `weather.py`. | Ph 0 | 2 |
| **1.8** | **T0-13 the 54.17 errata** ⚠️ (owner ruling, §8) · **T0-18** (59.61 air-facility trucks — *gate, don't delete*) · **T0-16** (64.73's magnitudes). | ruling | 1.5 |
| | **NOT YET: T0-6 (`classify()`).** It strips the Commonwealth of five phantom tank battalions and gives it nothing back. **It ships with PHASE 3.** | | |

---

### 🟩 PHASE 2 — THE SCOREBOARD ⏱ **5 days**

> *The campaign is an Axis Smashing Victory at GT1, before anybody moves (300–20), and the whole
> 111-turn war moves the score by ±25. You have no instrument.*

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **2.1** | **64.71's "for one full Game-Turn" persistence.** | — | 1 |
| **2.2** | **Delete the invented annihilation victory (I5).** | — | 0.5 |
| **2.3** | **The ≤90 / ≤60 truck-MP trace to a dump fed from Tobruk or Tripoli.** `supply.reachable_truck_moves` **already exists** — wire it. | — | 2 |
| **2.4** | **64.72 — the Commonwealth's GT35 automatic win.** | 2.3 | 1.5 |
| | **64.73's *form* ("do you HAVE") waits for Phase 4. 64.74 waits for Phase 7. 64.75 waits for rule 20.9.** | | |

> ### 🔵 GATE A — CORRECTNESS, NOT BALANCE
> You may now measure **mechanism**: does combat resolve on the CRT instead of by mass surrender? Does
> the Tobruk harbour survive turn 2? Do foul-weather penalties land on 2–3 sections? Does a garrison
> on its own dump bank its city? **You may NOT read a balance number.** The OOB is still at 32%,
> distance still costs nothing, nothing heals, and **Malta — a ~320-VP lever — is still a `dict`.**

---

### 🟩 PHASE 3 — THE ORDER OF BATTLE ⏱ **15–20 days**

> *The balance lever. Pure data + one classifier + an AA role. **The largest single thing you can do to
> the campaign, and it needs no new engine subsystem.***

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **3.1** | **T0-6 `classify()`** — classify on the *counter*, not the group; add an explicit `role` to the OOB records; **add an AA role** (rule 3.23) and set `is_pure_aa`. **AND STOP IT DISCARDING THE AIR COUNTERS** — `oob.py:106-111` currently throws away 10 Air Strips, 10 Airstrips, 2 Alighting areas and 4 SGSUs that the OOB already carries. *One function; it unblocks Phase 5 for free.* | — | 2 |
| **3.2** | **The 22 missing Commonwealth models** (Sherman, Valentine, Crusader I/III, Churchill, A10, 17-pdr, Bishop, Deacon, Priest, Scorpion, both AA rows…) from [4.47], and the missing Axis models from [4.48]/[4.49]. | — | 3 |
| **3.3** | **The Commonwealth gap-fill layer** — there is none. Transcribe [4.43a] + [4.44B]: 274 of 365 reinforcement counters and 43 of 66 initial counters are missing. Includes **20.11: brigade → HQ + three battalions.** | 3.1, 3.2 | 8 |
| **3.4** | **The Axis garrison hexes.** `data/oob_italian.json` is a raw VASSAL extraction. **Pure data, no engine change — and it is 90% of the final score.** | — | 2 |
| **3.5** | **The Axis gap-fill** — 45 of 46 reinforcement rows, the **Ramcke Brigade**, Sonderverband 288, the 300th Oasis Bn, the 8 missing Italian armoured battalions, the corps artillery park. | 3.3 | 4 |
| | 🔴 **NEVER SHIP 3.5 WITHOUT 3.3.** That is the BALANCE TRAP. | | |

> ### 🔵 GATE B — A TRANSCRIPTION CHECK, NOT A BALANCE READING
> **Predicted, measurable: the force ratio inverts from 1.72:1 Axis to ~1.9:1 Commonwealth.** That is a
> property of the built OOB with **no dice in it** — it verifies the transcription against the chart.
> **Check it. Do not read the campaign result off it.**

---

### 🟩 PHASE 4 — IN-HEX SUPPLY ⏱ **15–20 days**

> *The deepest bug. Do it before more code accretes on the ½-CPA API.*

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **4.1** | **49.14 per-unit fuel capacity** + **53.11 first-line trucks** (seeded per [60.31]/[60.41], hex by hex) + **59.66B** start-line load. | Ph 3 (the OOB carries the hexes) | 7 |
| **4.2** | **48 V.C.6 the Supply Distribution Segment** (the 0-CP load/unload window) + **53.24** load/unload CP + **53.25** no-leapfrogging. | 4.1 | 4 |
| **4.3** | **Kill the ½-CPA trace.** 49.15/50.15/51.15 — supply must be **in the hex**. | 4.2 | 4 |
| **4.4** | **DELETE:** the escorted teleporting dump (32.33/32.58A/32.24), the 32.32 MP price, `MOTORIZATION_POINTS`, the `motorized_supply` flag, `_organization`'s motorization body, the policy leapfrog relay and `_relay_source`. **Wire the [54.12] Non-Dump capacity row.** | 4.3 | 3 |
| **4.5** | **Re-form 64.73's quality-test as an inventory check** ("do you HAVE"), now that it is expressible. | 4.3, Ph 2 | 1 |

---

### 🟥 PHASE 5 — THE AIR GAME AND MALTA ⏱ **30–45 days**

> 🔴 **PROMOTED. This was going to be last. It is not last.** With the dice held identical, Malta swings
> **95–320 VP and flips the winner on seed 7** — and the number that sets it is a calendar we invented
> (**I2**). **The single largest measured determinant of who wins this campaign is currently not a
> rule.** The designer's *"why anyone would play a campaign game without the Air and/or Logistics
> Game(s) is beyond me"* is a load-bearing statement, not a preference.
>
> *Dependencies are only Phase 1.4 (the [41.5] CRT) and Phase 3.1 (the air counters). **It does NOT
> depend on Phase 4** — 38.24's "fuel is subtracted from the air facility's dump" is already an in-hex
> draw, so the air fuel model survives the supply rewrite unchanged.*

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **5.1** | **36 — air facilities** (capacity levels; reduced by bombing; **36.17: an airfield is a supply dump for its SGSUs**) **+ 35 — SGSUs** (35.14: 1 Stores/GT + 1 Fuel + 1 Water per OpStage; **without them, no refit**). Un-gate T0-18's air-facility truck rows. | 1.4, 3.1 | 8 |
| **5.2** | **34.17 / 38.21 / 38.24 — aircraft consume Fuel Points, drawn from the air-facility dump.** **The Axis currently lands 1,884,000 Fuel Points and keeps 100% of them: the Axis air force is fed on air.** *(NOT 58.3 — see §7.D1.)* | 5.1 | 4 |
| **5.3** | **38 — Aircraft Maintenance / the Refit Table.** *The sortie-rate governor* — it is why one `AirWing` can fly the same 6 strike points every OpStage for 111 turns. Includes 38.35's **+2 Italian / +1 German** serviceability DRMs — the rulebook's model of Axis unserviceability, which we currently give away free. | 5.2 | 6 |
| **5.4** | 🔴 **44 — MALTA AS A PLACE.** Both halves of the loop: facility **levels** → **18 planes per level (44.14)** → bomb points → the [41.5] CRT → % of the Axis convoy destroyed; and back the other way, the Axis spends from a **finite budget** (64.52 → [44.41] campaign row: **I unlimited / II × 25 GT / III × 12 / IV × 12**) to **raid Malta** (44.21/41.36) and knock its levels down, while the CW rebuilds them on the [44.5] table. **DELETE `_malta_bomb_points`.** | 5.3 | 10 |
| **5.5** | **41.32 / 41.35 — bombing trucks and supply dumps** (*"+1 Truck Point lost per 10%"*). **56.21 / 56.22 — the Axis convoy planning decision** (his single most important recurring choice, currently a hardcoded 60/25/15 split, **I11**). **39.19 — one mission per plane per OpStage: Malta OR the desert.** **43 — the Aegean basing constraints** that force the Axis to keep a Malta-capable bomber force off the battlefield. | 5.4 | 10 |
| | **DEFER, and record the debt: 40 (fighter combat), 45 (air-to-air), 46 (flak), pilots, maneuver, night, torpedoes, paradrops.** `AirWing.fighters` is a constant that never dies. **Something must eventually kill aeroplanes**, or Malta is a lever with no cost to pull. | | |

#### 5.5 LANDED — 2026-07-21, plus the REPAIR PASS the same day. What it built, what it refused to build, and the two rulings it left.

**BUILT.**

* **The [41.5] Supply Dump and Trucks rows are transcribed** (PDF p107 at 300 dpi, rotated, cropped
  and read row by row; the Key on p108 gives the semantics verbatim). Every one of the twenty-two
  columns partitions all 36 sequential 2d6 codes exactly, which is the self-check they were accepted
  on. That leaves **four** rows of the eight still untranscribed — Fortification, Railroad, Road, and
  the Torpedo-Points / Barrage-Points index scales — each named in the data file's own `_comment`.
* **41.35 B-SD and 41.32 B-TC are missions.** `AirMission(kind="dump"|"trucks")`, resolved in
  `engine._air_dump_bomb` / `_air_truck_bomb`, fuelled and un-refitted through the identical seam
  every other bombing mission uses. With them, **for the first time in this engine a bomb can destroy
  a lorry** — which is what Phase 6.1's "now that Phase 5 exists, air can kill a lorry too" was
  waiting for.
* **56.21/56.22 — invention I11 is deleted.** `scenario._CONVOY_SPLIT_56_22` is gone. The scenario
  builder now schedules an **allowance** (`Convoy.tons`, the 56.4 × 56.5 × die tonnage) and the
  **Convoy Planning Phase** (`engine._convoy_planning`, once per Game-Turn, planning one Game-Turn
  ahead per 56.0) asks `Policy.convoy_plan` what to put in it. `campaign_policy.convoy_plan_doctrine`
  reads the army's own larders, compared in the book's own common unit (the [54.5] Equivalent Weight
  Chart), and ships what it is shortest of.
* **39.19 binds.** `GameState.air_strategic` books the African bombers the Axis adds to a Malta raid
  (44.21/44.25, capped by 44.27) out of the LAND arena for the **rest of that Game-Turn**, cleared at
  the Game-Turn boundary alone. The Axis policy now has a real trade: `malta_africa_doctrine` strips
  the desert only for a raid it has paid a [44.41] budget Game-Turn for.
* **43 is a module** (`game/basing.py`), and rule 44 reads its basing off it, so the raid's sizing and
  the battlefield's deduction are **the same number, subtracted once**: `africa_planes = the squadron
  − (italy_sicily_planes + crete_planes)`. Its two live effects today: **43.12 keeps three quarters of
  the Axis bomber arm off the desert until Game-Turn 35** ("75% of ALL GERMAN BOMBERS must be based in
  Italy/Sicily" — untyped, so it binds on our abstract pool on any reading), and **43.13 + 43.25
  collapse the Malta-capable force from 75% to 25% at Game-Turn 35**, because Crete takes at least half
  and Crete may not raid Malta.

**THE 5.5 REPAIR PASS — 2026-07-21, three adversarial verifiers.** What it found and fixed:

* **THE SAME BOMBERS WERE IN SICILY AND IN AFRICA AT ONCE.** `italy_sicily_planes` applied 43.12's 75%
  to the whole pool for the Malta raid while `africa_planes` returned the pool whole, so a 20-plane
  force produced **35 aeroplanes of basing**, in the direction that gave the Axis both arenas. The
  conservation identity above replaced it, and `tests/test_basing.py` pins it.
* **THE CONSTRAINED-TYPE LIST COULD NEVER MATCH.** It was transcribed off 43.11's *prose*
  (`"He 111"`, `"FW 220"`) and is matched **exactly** against the keys of `air.AIRCRAFT`, which are the
  **chart's** printed names. PDF p145 rendered at 300 dpi reads `Fw. 200 C`, `He. 111`, `Hs. 126`,
  `Ju. 52/3m`, `Ju. 87B`, `Ju. 87D`, `Ju. 88D`. Two of the three entries could never have bound, and
  the failure was silent. Now `["He. 111", "Ju. 88D"]`, with a test that every entry is a name the
  chart prints.
* **THE BASING CUT NOW PRECEDES THE AIR-SUPERIORITY SCALE** (`engine._air_points`). Scaling the whole
  establishment first and capping at rule 43's African quarter second made the loser-scale (0.5)
  arithmetically invisible under the cap (0.25): the Axis flew the same strength whether it held the
  sky or lost it.
* **48's beat order.** The Convoy Planning Phase ran *before* the Strategic Air Planning Stage; 48
  orders them I → II (Malta) → III.A (Naval Convoy Schedule). Corrected, and the Malta beats now carry
  their own `Phase.STRATEGIC_AIR` tag instead of borrowing whichever phase happened to precede them.
* **41.31/41.32's shelter is a MAJOR CITY test** (`engine._city_wall`), not a bare fortification level.
  Latent today (every fortification in the tree stands on a city), live the moment 24.4 builds a field
  work.
* Two **dead `hasattr` guards** on methods that are defined on the base `Policy` (`malta_africa_planes`,
  `convoy_plan`) removed — the `convoy_plan` one would have silently sailed an **empty** convoy rather
  than failing loud (56.22 is a mandatory input).
* **THE AXIS AIR PROXIES ARE NOW DENOMINATED IN THE ESTABLISHMENT RULE 43 SPEAKS ABOUT.** With the
  deduction live, `AirWing.strike` for a German pool is the whole bomber arm and a quarter of it flies;
  the campaign and Tobruk seeds were re-expressed 6 → 24 (`scenario._AXIS_AIR_STRIKE`,
  `_TOBRUK_LW_STRIKE`), which puts **the same two Ju. 87B and the same [41.5] column over the desert as
  before**. The Commonwealth wing is unchanged — rule 36 bases the Desert Air Force on the map. Both
  magnitudes remain flagged proxies for the untranscribed [34.6]/[59.3]; what changed is the unit, so
  that a basing rule cannot silently halve a scenario's designed air campaign. Every air test fixture
  in the suite carries the same note.

**🔴 OWNER RULING NEEDED — 43.11/43.13, and it is TWO questions.** `game/basing.py:typed_requirement_applies`,
`data/malta_44.json`, and asserted in `tests/test_basing.py`.

1. **From Game-Turn 35, does rule 43 bind on a Ju. 87B at all?** 43.12's untyped sentence expires there;
   what replaces it is typed (43.11's Mediterranean 75%, 43.13's Crete 50%) and this engine fields none
   of those types. Read strictly — which is what the code does, leaving the Crete term **unseeded** —
   **the Luftwaffe's African bomber force TRIPLES in June 1941** (25% of the pool before GT35, 75%
   after), a discontinuity produced by a type list rather than by the war. Read as a stand-in (our one
   abstract bomber represents the whole German bomber arm), Crete takes its half and Africa stays at 25%
   all war. Flipping the list in `data/malta_44.json` is the whole of the affirmative ruling.
2. **What is "FW220"?** 43.11 and 43.13 both name it and **no such aircraft is in the game**. The
   [4.44b] chart (PDF p145, read with eyes) prints eight German types and the nearest Focke Wulf bomber
   is the **Fw. 200 C** (Range 205, Bomb 14). This is a book-internal inconsistency of the 54.17 class;
   it is left unseeded under `unresolved_type_43_11` rather than guessed.

**THE DEFERRED AIR DEBT IS WRITTEN DOWN IN THE CODE**, at the top of `game/basing.py` (the last module
of Phase 5, where the next person will look). Restated here: 40, 45, 46, pilots, maneuver, night,
torpedoes and paradrops are unbuilt; **nothing on the African mainland can be shot down**; the only
channel that permanently removes aircraft anywhere is 41.36's 10%-per-level, on **Malta alone**; so
44.28's loss apportionment has nothing to apportion and Malta's 19 fighters and 17 AA Points ([60.46],
transcribed) never fire. **Until something kills aeroplanes, every Malta number this engine produces is
an upper bound on the Axis's ability to suppress the island and a lower bound on what it costs him.**
[46.3]'s Anti-Aircraft CRT (recovered, PDF p108, legible) and the [45.4]/[45.5] TacAir tables are the
precondition for all of it.

**Also deferred, and each named at its own function:** **39.16** ("planes from the same squadron may not
be divided between strategic and land support missions") — *newly reachable*, because 5.5 is what starts
splitting the single `AXIS/LAND/strike` squadron between a Malta raid and the desert; inert under the
shipped doctrine (which commits every available African bomber, an all-or-nothing split) and possibly
moot under 43.22's "groups of 6 to 12 = a squadron", but written down rather than left silent; 41.32's
*first-line* (attached) truck bombing, which needs a Truck-Point ledger on a unit that does not exist
(the same roster work rule 19 and 34.72 wait on); **42.22's recon ban, which reads a fortification level
where the rule says "any hex except for MAJOR CITIES" flat** (`engine._air_recon` — the sibling of the
41.31/41.32 shelter, left alone here because correcting it drops a fort clause the rule does not print);
43.23's four Suez OpStages a month (a tax on a Crete force that does nothing in this engine);
43.21's fuel/ammo exemption applied to the *African* contingent, which makes that contingent slightly
cheaper than the book's; and 41.35's silence about the cargo on a bombed-out lorry, which we destroy
pro rata because 53.12 would otherwise be violated.

---

### 🟩 PHASE 6 — MAKE THE DESERT BITE ⏱ **10–14 days**

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **6.1** | **T1-6 the mortal lorry**: 21.11 truck breakdown (22.23's repair column comes alive free), **12.46 barrage destroys trucks** (the 32.56 trap), 52.42 trucks drink, 29.34 truck cargo evaporates, 52.45 water hauled by truck, 49.3's CW 9% rate. **Now that Phase 5 exists, air can kill a lorry too.** | Ph 4, Ph 5 | 5 |
| **6.2** | **T1-7 Forward/Back guns + 15.84 Vulnerability** — the largest missing loss channel in the combat model. Brings 12.14 / 12.16 / 14.13 / 15.13 with it. **And 15.21: a unit may not fire anti-armor *and* close-assault in the same segment.** | — | 5 |
| **6.3** | **T1-8 make contact cost something**: the 8.64–8.67 break-off negation, 10.31–10.36 (mandatory attack / Holding Off / retreat-3-and-take-3-DP), 11.25 (charge the whole hex), 8.12 (retreats cost CP), 6.24.2, 6.26, 8.53a, 8.19. | — | 4 |

---

### 🟩 PHASE 7 — THE ARMY THAT HEALS ⏱ **15–20 days**

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **7.1** | **T1-10 rule 19** — the parent/attachment tree, Kampfgruppen, shells. **Makes 15.52/15.53 fire for the first time.** `_organization` becomes the real Reorganization Segment. | Ph 3 | 7 |
| **7.2** | **T1-5 rule 20** — the replacement economy. [20.66] Axis pool, [20.78B/C] CW Production, [20.3] conversion, **20.62's tonnage charge (RPs have priority over fuel)**, 20.8's 32 mandatory withdrawals, 20.9 voluntary withdrawal. | 7.1, Ph 4 | 10 |
| **7.3** | **64.75** (CW Withdrawal Points) **then 64.74** (unused RPs, **excluding infantry for BOTH sides**). **In that order.** | 7.2 | 2 |
| **7.4** | 17.3 / 20.43 **Training** (the CW currently gets its trained morale free on arrival). | 7.2 | 3 |

---

### 🟩 PHASE 8 — THE GROUND ⏱ **10–30 days — SPIKE FIRST**

| # | Item | Deps | ⏱ |
|---|---|---|---|
| **8.0** | 🔴 **ONE-DAY SPIKE: does the hexside data exist?** Escarpments, wadis, slopes, salt marsh, mountain. If the VASSAL source carries them → **L**. If they must be traced off a 14310×4632 map scan → **XL**, and re-scope. | — | 1 |
| **8.1** | **T1-3 the map's terrain** — hexsides, salt marsh (**the Qattara Depression / the Alamein line**), escarpment (**Halfaya**), mountain (**Jebel Akhdar**), gravel, delta, and all ten Major Cities at their [8.37] note-4 fort levels. Read the **[8.37] Stacking Points column** off the scan and delete `DEFAULT_HEX_LIMIT` (**I3**). | 8.0 | 9–29 |
| **8.2** | **24.3 / 24.4 construction of minefields and fortifications** + **26 minefields**. **El Alamein gets its Devil's Gardens.** Needs the Scorpion (3.2) and an engineer HQᴱ (23.14). | 8.1 | 8 |

---

> ## 🔴 GATE C — **THE FIRST HONEST BALANCE READING**
>
> ### **After PHASE 8. N ≥ 30 seeds. Report a distribution, not a seed.**
>
> **Not before.** The justification, phase by phase:
>
> * Before **Phase 0** **no comparison you make is valid at all** — one shared RNG, conditional draws.
>   This is not a caveat; it is a disqualification. *(It already cost us: "Malta is inert" was false,
>   and it went into memory as settled.)*
> * Before **Phase 1.1** the CRT barely rolls — 20 of 36 assaults end in a morale surrender before a
>   die is thrown. **Combat is not being simulated.**
> * Before **Phase 2** the scoreboard reads *Axis Smashing Victory* at GT1 before anybody moves, and
>   30–45 VP are permanently unreachable. **You have no instrument.**
> * Before **Phase 3** the Commonwealth is at **32% of its own chart** with **no real tanks, no
>   artillery and no AA arm.** It ends the war with 10–28 combat units. **You are measuring an army
>   that cannot fight.**
> * Before **Phase 4** distance costs nothing — the Panzerarmee spent **1,419 Fuel Points in 111 turns**
>   while **73% of all fuel evaporated.** **You are measuring a logistics game with no logistics in it.**
> * Before **Phase 5** the Axis lands ~**1.9 million Fuel Points and keeps every one**, and **the
>   single largest lever on the outcome — worth up to 320 VP and a flipped winner — is a hardcoded
>   calendar we invented.** **Any balance number taken before Phase 5 is a measurement of our own
>   arbitrary constant.**
> * Before **Phase 7** nothing heals, and **the Commonwealth's entire structural advantage (~1,617 free
>   infantry RPs + 306 tank points, including 62 Shermans from GT89) does not exist.**
> * Before **Phase 8** there is no Qattara Depression, therefore **no Alamein line**, and no Halfaya.
>
> **NOTHING GETS TUNED AT GATE C EITHER.** Gate C is where you first *read* an honest number. Several
> load-bearing Tier-2 items will still move it — **22.3** (the CW's whole rear-area recovery economy),
> **56.3** (the Axis's only non-lorry inter-port transport), **54.4** (the Axis's rail lever), **30.5**
> (the real Tobruk sea lifeline). Land those, then:
>
> ## 🟢 GATE D — **TUNING**
> ### After the load-bearing Tier-2 set. *"Once that's done we can talk about tuning again."* This is
> ### the point the owner's own sentence was pointing at, and it is the first time the word is legitimate.

---

### The honest total

| | ⏱ working days |
|---|---|
| **Phase 0 — THE INSTRUMENT (RNG)** | **3–5** |
| Phase 1 — Tier 0 (incl. the [41.5] CRT) | 10–14 |
| Phase 2 — the scoreboard | 5 |
| Phase 3 — the Order of Battle | 15–20 |
| Phase 4 — in-hex supply | 15–20 |
| **Phase 5 — the Air Game and Malta** | **30–45** |
| Phase 6 — make the desert bite | 10–14 |
| Phase 7 — the army that heals | 15–20 |
| Phase 8 — the ground | **10–30 (spike first)** |
| **➜ TO GATE C — the first honest balance reading** | **≈ 115–175 working days** |
| Load-bearing Tier 2 (22.3, 56.3, 54.4, 30.5, 55.2, 52.2) | +30–45 |
| **➜ TO GATE D — tuning** | **≈ 145–220 working days** |
| Tier 2 remainder (16, 27, 28, 8.7, 51.23, 52.13/16/17) | +15–25 |
| The air detail tail (40, 45, 46, pilots, night) | +30–50 |
| **THE WHOLE PORT** | **≈ 190–295 working days** |

**That is six to nine months of one-person full-time work to Gate C, and roughly a year to a complete
port.** Phases 3, 4 and 8.1 are large **data** jobs and are the most parallelisable — they are where a
second pair of hands (or a swarm) buys the most. **Phase 5 is the only true XL, and it is no longer
optional.**

---

## 7. WHERE THE REPORTS DISAGREE — AND MY RULINGS

**D0 — 🔴 THE AIR REPORT'S CENTRAL NEGATIVE FINDING IS FALSE, AND IT WAS FALSE FOR AN INSTRUMENT
REASON.**
The air audit's flagship conclusion — *"Malta is causally inert; cranked to the rule-41.66 ceiling it
denies 342,000 Fuel Points and **the victory score does not move**"* — is **wrong**. It was produced by
an A/B that changed the **number of interdiction orders**, which changed the number of dice
`_interdict` drew from the **single shared RNG** (`engine.py:84`, `:411-414` ✅), which reshuffled
weather, breakdown, morale and every CRT roll for the remaining 111 turns. **±200 VP of pure noise
swamped the signal.**
Re-run with the dice stream held identical (111 orders in both arms; `bomb=1` is the CRT's flat-0%
column — it *draws* and denies nothing) against `bomb=500`: **~95 VP on seed 1941; ~320 VP on seed 7,
where the winner FLIPS** (Axis Smashing 300-10 → CW Marginal 100-130).
**RULING: Malta is one of the strongest levers in the engine, and the historically correct one.** The
air report's own §"MALTA, SPECIFICALLY" — *"Fix the fuel first. Malta cannot strangle an army that
isn't breathing through the pipe"* — was reasoning correctly from a corrupted number and reached the
wrong priority. **The air game is promoted from last to Phase 5.**
**This is also the reason §2.1 exists.** Any finding in any of the six reports produced by toggling a
conditionally-drawing subsystem is void until re-measured. **And this one had already been written into
project memory as a settled dead end. Purge it.**

**D1 — 58.3, the ¾ fuel tax. THE AIR REPORT CONTRADICTS ITSELF.**
Its **TOP-FIVE #1** says *"Make aircraft consume fuel — 58.3 now… eight lines of code at the port seam.
**Do this first, then re-measure everything.**"* Its **§"Which air game are we entitled to play?"**
proves that **58 is exclusive with the Air Game, exactly as 47/32 are exclusive with the Logistics
Game** (58.0's own Commentary; 59.61; 64.6). Its **TOP-FIVE #4** then says *"Given the owner's goal is
the full Air Game, I would go straight to [rule 44] and skip the fork."*
**RULING: believe the §-analysis and TOP-FIVE #4. Do NOT implement 58.3.** It is an abstract-air rule;
adding it would create a *new* instance of exactly the bug class §5 exists to purge, and would need
ripping out again in Phase 7. The full-game equivalent — **34.17/38.21/38.24: aircraft burn Fuel Points
out of the air-facility dump** — delivers the same causal effect, is on the port path, and is **Phase
7.3**. If you want the *measurement* before then, run 58.3 on a throwaway experiment branch and record
the number; do not put it in the engine.
*(The underlying fact both halves agree on is not in dispute and is damning: **the Axis lands 1,884,000
Fuel Points at Benghazi over 111 turns and keeps 100% of them.**)*

**D2 — the 54.17 demolition table: fix it, or flag it?**
Both auditors independently rendered PDF p109 (at 400 dpi and 600 dpi) and **agree completely on the
facts**: the OCR is faithful, the **1979 printing** is misprinted, and the correction (`−1: 33 → 0`,
`7: 33 → 100`) is **forced by the neighbouring cells**. They disagree on the action. The 21-31 report:
*"keep the faithful transcription; add an `_errata` note; **do not silently reconcile them** — this is a
rules question for the owner."* The 47-57 report: *"it must be repaired, and the repair is forced. **Fix
the DATA, and say why.**"*
**RULING: they are both right, and the synthesis is trivial.** Apply the correction **and** record it as
a named errata (`_errata_54_17`) carrying the printed values, the corrected values and the reasoning.
Nothing is silent; nothing is left broken. **But it is on the owner's docket (§8), because it is a rules
ruling and not a bug fix.**

**D3 — 51.13, the engineer stores rate. THE 47-57 REPORT IS WRONG. ✅ VERIFIED.**
It claims: *"the `combat`/`noncombat` split keys off `is_combat`, and **engineers are combat units**, so
a 3-TOE engineer battalion pays **12**, not **1**."*
**That is false.** `data/unit_stats.json:24-25` sets `rr_engineer` and `road_engineer` to
**`is_combat: false`** (and the 21-31 report says so correctly). `supply.stores_cost` therefore selects
the **noncombat** rate of 1. **And I built the campaign state: all 22 non-combat units (HQs +
engineers) have `strength == 1`, so every one of them pays exactly 1 Stores Point per Game-Turn — which
is exactly what 51.13 requires.**
**The residual defect is real but latent:** the *formula* is `rate × strength`, where 51.13 says a
**flat 1**. It bites the moment rule 19 gives an HQ real TOE (3.31: an HQ "represents the division").
**Fix the formula in Phase 0; it changes no number today.**

**D4 — the force ratio: 1.69:1 or 1.72:1?** Not a conflict. The 12-20 report measures **1.69:1** on
cumulative TOE across the whole campaign OOB; the 01-04 report measures **1.72:1** on units on the map
at GT111 and **1.67–1.72:1** in the Alamein window. Different denominators, same story. **Quote 1.72:1
at Alamein — it is the one that matters.**

**D5 — 34 or 36 collapsed Commonwealth brigades?** 12-20 counts 36, 01-04 counts 34. The difference is
whether the "X Bde Grp" rows count. **Both agree on ~432 TOE of shortfall and a 3.1× understatement.
Do not spend time reconciling it — the transcription in Phase 2.3 settles it.**

**D6 — cohesion floor −68 or −75?** Different runs (8-turn vs 45-turn). Not a conflict.

**D7 — `is_first_line_truck` at `state.py:63` or `:66`?** ✅ It is **`state.py:66`**. `is_pure_aa` is
`:67`. The 05-11 report's `:63` is stale.

---

## 8. THE ERRATA DOCKET — RULINGS ONLY THE OWNER CAN MAKE

The 1979 rulebook contradicts itself in five places that block code. **Rule on all of them before the
code is written, not after.**

| # | The contradiction | The auditors' reading | Ruling? |
|---|---|---|---|
| **E1** | **[54.17] Supply Dump Demolition.** The printed chart reads `… -1: 33, 0: 0, … 6: 100, 7: 33, 8+: 100`. | **A print error.** Both anomalous cells are pinned by their neighbours. **`−1: 33 → 0`, `7: 33 → 100`.** Verified on the scan at 400 and 600 dpi by two independent auditors. **17% of live demolitions hit the bad cell.** | ☐ |
| **E2** | **Supply-dump construction cost.** Rule text **24.9** says **20 Store Points**. Chart **[24.17]** says **10 Stores + 3 CP**. Engine uses **20**. | Unresolved. The chart is usually the authority in this book (cf. 15.53). | ☐ |
| **E3** | **Minefield entry cost with engineers.** **23.21** says 6 CP (mot) / 3 CP (non-mot). **26.24** says a flat **4 extra CP**. | Unresolved. Blocks rule 26. | ☐ |
| **E4** | **Where minefields may be laid.** **24.35** says *"clear, sand/gravel, or **rough**"*. The **[24.17]** chart says *"Clear, Sand/Gravel and **Salt Marsh**"*. | Unresolved. Blocks rule 24.3. | ☐ |
| **E5** | **[35.23] squadron capacity.** Rule text: CW **15 ready / 5 reserve**, "1940–June '41". Chart: CW **12 / 4**, "1940–41". *Both the numbers and the date break disagree.* | Unresolved. Blocks rule 35. (Italian 9/3 and German 12/4 agree in both places.) | ☐ |

**And three rulebook defects where the engine is ALREADY RIGHT — do not "correct" them back:**

| Defect | Book says | Correct reading | Engine |
|---|---|---|---|
| **Tobruk's starting Efficiency** | 60.7 and 61.6 both print **"Efficiency Level 7"** | **2.** 55.12 gives Tobruk **5**; 55.25's San Giorgio takes **three levels**; the [55.3] footnote says Tobruk *"begins the campaign with an efficiency **below** the listed five."* 5 − 3 = 2, and `7`/`2` is a classic OCR confusion in this typeface. | ❌ seeds **5**. **Fix to 2/5 (T0-4). Do not port the 7.** |
| **Benghazi's hex** | ch.60 says **B4827** twice | **A4827** — the authoritative *Summary of Important Locations* (`90:198`) and chapters 61, 62, 63 all agree, and Benghazi's airfields are on map A. | ✅ **correct.** Do not change it. |
| **The 29.61 Weather Table's Game-Turn column** | GT 1–12 = "Spring" | The season **labels** are right and the **GT column** is the misprint (a "Summer" with 56% Hot and no rain is meteorologically unambiguous). `calendar.py:26 CAMPAIGN_SEASON_OFFSET = 24` resolves it. | ✅ **correct, and non-obviously so.** |
| **"Centauro"** | — | **Not in CNA at all** — 0 hits in the whole rulebook. It went to Tunisia, off-map. | ✅ correctly absent. **Drop it from any OOB wishlist.** |

---

## 9. UNVERIFIED / OPEN

* 🔴 **EVERY A/B IN THE SIX REPORTS THAT TOGGLED A DIE-DRAWING SUBSYSTEM IS UNRELIABLE-PENDING-RNG-FIX.**
  See §2.1. Known-false already: *"Malta is causally inert."* Suspect: *"doubling Commonwealth strength
  changes nothing"*, the 32.32 `motorized_supply` measurement, and anything else measured by switching a
  feature on or off. **Re-run all of them after Phase 0, at N ≥ 30 seeds.**
* 🔴 **THE BYTE-LOCK IS RETIRED.** `rommels_arrival` `9339d2b308d7` and `siege_of_tobruk`
  `5ba4da88d107` **will** break at Phase 0. **That is expected and accepted; the owner has agreed.**
  Nothing in this plan treats those hashes as a constraint. *(Determinism is still required — the same
  seed must still reproduce the same run. What is retired is the demand that a **new rule** reproduce an
  **old** run.)*
* 🔴 **THREE SEEDS IS NOT A MEASUREMENT.** Every balance claim in the six reports rests on seeds 1941 / 7
  / 2026. Even with per-subsystem streams, changing a *rule* changes outcomes and diverges the
  trajectory — that is inherent, not a bug. **After Phase 0, a balance claim is a distribution over
  N ≥ 30 seeds or it is not a claim.**
* 🔴 **Does the hexside terrain data exist anywhere?** No report says. It determines whether Phase 8 is
  **L or XL**. **UNVERIFIED. Spike it (8.0).**
* **[56.4] / [56.5] Axis convoy charts.** They live on the oversized fold-outs
  (`docs/rules/99` = *"not OCR-able"*). `logistics_rates.json:231-247` reproduces the rulebook's own
  worked example **exactly** (Nov 1941 = row E; E = 11,000 + 2,500 × 4 = **21,000 tons** ✓). **That is
  one cell of each chart. The remaining 35 months and 6 levels are UNVERIFIED — flagged, not cleared.**
* **[15.79] defender 3-hex-retreat row** (`combat_tables.py:132`). The OCR has ragged cell alignment and
  the engine's own comment flags it "least-certain". Affects only the three Overrun columns. **Confirm
  against the chart image.**
* **[45.5] TacAir Kill Table.** 3 of the rulebook's 4 worked examples reproduce; the Hurricane at +2
  differential does not. **Probably a rulebook typo (11-22 for 11-16), but re-read PDF p11 before
  trusting the OCR.** Low priority — we implement none of ch.45.
* **`docs/rules/99-foldout-charts.md` contains NO OCR'd content at all** — all eleven fold-outs are
  stubbed *"not OCR-able; see the original scan."* **Anything the audit trail says lives in "99" lives
  nowhere.**
* **Rule 8.19** — *no Commonwealth land unit may ever be west of Marble Arch (A2109)* — is entirely
  unimplemented and unmentioned in any plan above. Cheap; add it to Phase 4.
* **The two OCR repairs the engine already made are independently verified CORRECT** (15.79's defender
  10%/+4 row `34-45` and 5%/+2 row `34-52`; 17.4's Cohesion −4 `42-56`), each by a partition argument.
  **Do not "fix" them back.**

---

## 10. THE SIX SENTENCES

1. 🔴 **The instrument is broken.** One shared RNG with conditional draws means **every A/B we have ever
   run is suspect** — and the one we trusted most (*"Malta is causally inert"*) was not just wrong, it
   was **backwards**, and it went into project memory as a settled dead end. **Fix the RNG first. Take
   no measurement until it ships.**
2. **The charts are right; the engine's use of them is wrong** — 26% DONE, 49% MISSING, 6% WRONG across
   1,044 audited rule-rows, and nine already-built subsystems that never fire.
3. **Tier 0 is twenty-two numbers we got wrong or never read**, and they can be fixed in about three
   weeks.
4. **The balance problem is the Order of Battle** — the Commonwealth is loaded at 32% of its own chart,
   and building it to that chart inverts the force ratio to the stated target *by transcription rather
   than by tuning*.
5. **The deepest bug is `supply.py:229`** — the abstract game's ½-CPA supply range doing the full game's
   job, which is why the Panzerarmee spent 1,419 Fuel Points in 111 turns while 73% of all fuel
   evaporated. **Distance costs nothing.** And **the largest lever is Malta — worth up to 320 VP and a
   flipped winner — which is currently a hardcoded calendar we invented.**
6. **Do not look at a balance number until Gate C, and do not tune until Gate D.** Before those points
   every number is noise, and the engine will tell you a confident, precise, entirely fictional story.
   **It already has.**
