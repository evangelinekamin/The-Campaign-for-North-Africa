# Rule 26 MINEFIELDS + Rule 24.3/24.4 CONSTRUCTION (minefields & fortifications) — transcription

Assignment: Rule 26 (all), Rule 24.3 (Constructing Minefields), Rule 24.4 (Constructing
Fortifications), plus the tables those sections cite: the Terrain Effects Chart (8.37, minefield
rows), the Construction Chart (24.17), and the Demolition Chart (24.18). "El Alamein's Devil's
Gardens."

## Sources read (scan, PDF = `tmp/The Campaign for North Africa.pdf`, 192 pages, letter, no rotation
flag honoured by pdftoppm except where noted)

| Content | PDF page | Rendered at | Legibility |
|---|---|---|---|
| Rule 23.12–23.26 (Engineers, incl. 23.21/23.22 minefield entry-cost reduction) | p.36 | 300dpi | clean |
| Rule 24.0–24.48 (Construction general, 24.1–24.4) | p.36 | 300dpi | clean |
| Rule 24.5–24.9 (Road/RR/Repair/Dump construction) | p.37 | *(read via docs/rules OCR only — outside assignment, not independently re-rendered)* | n/a |
| Rule 25.0 (Fortifications general) + Rule 26.0 (Minefields, all cases) + Rule 27.0 start | p.38 | 300dpi | clean |
| [8.37] Terrain Effects Chart (full chart, incl. Friendly/Enemy Minefield rows + note 13) | p.70 | 300dpi | clean |
| [24.17] Construction Chart | p.104 | 300dpi, **required a 90° rotation** (`PIL.Image.rotate(-90, expand=True)`) to read — the page is bound/scanned with the chart in landscape and no PDF `/Rotate` flag corrects it, unlike every other page in this doc | clean once rotated |
| [24.18] Demolition Chart | p.105 | 300dpi, upright as scanned | clean |
| [4.47] Commonwealth Tank & Gun Characteristics Chart, "Scorpion†" row + footnote (supporting cross-reference for the Demolition Chart's "tank bn with 6+ TOE of Scorpions") | p.138 | *(read via docs/rules OCR only — internally coherent, not independently re-rendered; peripheral to the assignment)* | n/a |

**Verdict on `docs/rules/*.md` OCR for this assignment:** the rule-text chapters (24.0–24.4, 26.0) are
OCR'd cleanly and match the scan verbatim — no corrections needed there. The **Construction Chart
(24.17) OCR is badly garbled** (e.g. "15 A/mms + 15 Stories", "Flake Minefield", "124:17" for
"[24.17]") because the chart is printed in landscape on a portrait page; the raw text extraction
scrambled it. The Demolition Chart (24.18) OCR is moderately garbled but the scan itself was easy to
read directly. **Do not use the docs/rules/90 markdown table for either chart — use the tables below,
read directly off the rotated/upright scans.**

---

## 1. Rule 26.0 MINEFIELDS (verbatim, PDF p.38)

### GENERAL RULE (26.0)
> In no place did the mine receive more notoriety than in the Libyan/Egyptian desert. Used sparingly
> in the early part of the war, minefields became a standard defensive feature by 1942. By El Alamein,
> they were ubiquitous. Minefields were more of a hindrance than a danger, at least on an operational
> level. (On tactical level it's a different question.) Therefore, in *CNA* minefields are obstacles;
> they rarely cause casualties. Units pay increased Capability Point costs to enter minefields.

### 26.1 TYPES OF MINEFIELDS
- **[26.11]** Two types: *dummy* and *real*. All minefield counters have the same front side; the
  reverse reveals real/dummy.
- **[26.12]** Distinction between *Friendly* minefields (paths through which are known) and *Enemy*
  minefields.
- **[26.13]** Real minefields may be removed by an Engineer unit (or unit with Engineer capability)
  spending one full Operations Stage in the hex — must *start* the Stage in the hex, expend **no**
  Capability Points, and remain to the end of the Stage. Applies to both Friendly and Enemy real
  minefields.
- **[26.14]** Dummy minefields are removed at the end of any Movement Segment in which an Enemy unit
  expends the CP to move into that hex (see 26.23).
- **[26.15]** A Friendly minefield is flipped to reveal real/dummy immediately on being entered by an
  Enemy unit.

### 26.2 EFFECTS OF MINEFIELDS
- **[26.21]** Movement costs to enter a minefield are on the Terrain Effects Chart (8.37 — table
  below). **"A motorized unit or vehicle entering an Enemy minefield expends Capability Points
  proportional to its given Capability Point Allowance. Thus, an artillery unit would expend 15
  Capability Points to enter an Enemy minefield."** — i.e. the TEC's "Mot = +CPA" cell means the
  *entire* CPA is spent on that single hex entry (the rule's own worked example: an artillery unit
  with a 15-point CPA, per the [4.47] chart, spends all 15 to step into one enemy-minefield hex). This
  is the "spends its entire allowance to enter one" behaviour named in the assignment.
- **[26.22]** All these costs are **in addition to** the terrain cost of the hex itself (minefield cost
  stacks on top of, does not replace, ordinary terrain entry cost). *Note: Units without Engineers will
  expend points far over their CPA* (→ Disorganization Points, rule 6.21).
- **[26.23]** Dummy minefields cost the **same** to enter as real ones. Difference: entering an Enemy
  dummy minefield reveals it immediately, but it is **not removed** until the end of that Movement
  *Phase* of the Operations Stage — so other units that move into that same dummy minefield during that
  Phase of Movement still pay the entry cost.
- **[26.24]** **Engineer units and combat units stacked with an Engineer battalion, or Commonwealth
  HQs with Engineering capacity, pay only FOUR additional Capability Points to enter an Enemy
  minefield, rather than their listed cost.** Engineer units / units stacked with an Engineer battalion
  pay **no extra cost** to enter a Friendly minefield. — **See OWNER RULING NEEDED #1 below**: this
  contradicts rule 23.21's numbers for the same situation.
- **[26.25]** Vehicle entering an Enemy minefield **not** accompanied by an Engineer battalion or CW HQ
  with Engineering capacity: possible destruction. Moving Player rolls **one die per battalion-sized
  (or smaller) combat unit, and/or per all 2nd- and 3rd-line trucks**. Roll of **5 or 6** = the mines
  destroy **one TOE Strength Point of tanks or motorized infantry, or one unattached Truck Point**.
- **[26.26]** Any anti-tank or close-assault combat where the **attacking** units are in an Enemy
  minefield, or where a Close Assault targets an Enemy unit that is in an Enemy Minefield: **the
  defending Player adjusts all columns ONE in his favor.** Does **not** apply to artillery barrage.

---

## 2. Rule 24.3 CONSTRUCTING MINEFIELDS (verbatim, PDF p.36)

- **[24.31]** Minefields built by any Engineering unit (or Commonwealth HQ Engineers). Engineers may
  build real and/or dummy minefields. Front sides of all minefield counters are identical; the reverse
  reveals real/dummy.
- **[24.32]** A minefield takes **one full Operations Stage** to lay (build), real or dummy alike. One
  started at the beginning of an Op Stage completes at the beginning of the Construction Segment of the
  **next** Op Stage.
- **[24.33]** To lay a **regular (real)** minefield: Engineering unit + **15 Store Points + 15
  Ammunition Points** in the hex, expended at the **start** of construction. Place an Under Construction
  marker.
- **[24.34]** A **dummy** minefield is built the same way, except the Player expends **no Ammunition
  Points and only 3 Stores Points.**
- **[24.35]** Minefields may be constructed in **clear, sand/gravel, or rough** hexes. Only one
  Minefield (real or dummy) per hex. **Minefields may not be constructed in major cities.** — **See
  OWNER RULING NEEDED #2 below**: the Construction Chart's Restrictions column for both Minefield rows
  instead reads "Clear, Sand/Gravel and Salt Marsh hexes" — Salt Marsh in place of Rough.
- **[24.36]** Minefields may **not** be constructed in Enemy-controlled hexes.
- **[24.37]** See Section 26.0 for minefield effects (cross-reference, transcribed above).
- **[24.38]** If an Engineer unit or HQ unit with Engineering capability spends an entire Operations
  Stage in a hex with a **real** minefield (Enemy or Friendly), that Minefield is removed (duplicate
  statement of 26.13/23.22). **Dummy** minefields are removed upon revelation of their status (i.e. per
  26.14/26.23, not by this clearing action).

## 3. Rule 24.4 CONSTRUCTING FORTIFICATIONS (verbatim, PDF p.36)

- **[24.41]** Fortifications are strongly protected defensive emplacements (cement-work etc.),
  represented by counters as Level 1 or Level 2. Major cities have built-in Fortification Levels,
  rebuildable by Engineer units once destroyed.
- **[24.42]** To construct **one Level**: one unit of any size with Engineering capability **plus** one
  Infantry battalion with **3+ TOE Strength Points**. Both spend **three complete Construction
  Segments** in the hex (Under Construction marker) **without expending any Capability Points**. At the
  start of the **fourth** Construction Segment the Level is complete; place the Fortification Level
  counter.
- **[24.43]** In addition to 24.42: the Player must have **30 Stores Points** present at the start of
  Construction. Expended immediately; construction begins.
- **[24.44]** New-fortification construction may take place in **any hex except mountain, salt marsh,
  desert, major city, and delta.** May **not** be built from scratch in an Enemy Zone of Control. — see
  note on the Construction Chart's abbreviated restatement of this list, below.
- **[24.45]** Fortification Levels — and major-city Levels — destroyed by air bombardment or artillery
  barrage may be **rebuilt** using the 24.42/24.43 guidelines. Difference: rebuilding/repairing **may**
  take place in an Enemy Zone of Control (new-build may not).
- **[24.46]** **No other construction — of any type — may take place in a hex undergoing fortification
  construction.** — **See OWNER RULING NEEDED #3 below**: the Construction Chart's Restrictions column
  for the Fortification row states a specific carve-out this flat prose rule does not mention.
- **[24.47]** Once emplaced, fortifications may not be voluntarily removed; reduced only by air
  bombardment or artillery barrage. No other combat type affects fortifications (they do affect combat
  — Section 25.0).
- **[24.48]** Fortifications built/rebuilt **one Level at a time**. Major-city Levels capped at their
  original Level of 2, except **Alexandria and Cairo** (Level 3 cities).

---

## 4. [8.37] Terrain Effects Chart — Minefield rows (verbatim, PDF p.70)

Full chart context: columns are `CP Cost to Enter or Cross (non-Mot / Mot)`, `Breakdown Value`,
`Combat Adjustment (Barrage / Anti Armor / Close Assault)`, `Stacking Limit`. `CP = Capability Point;
Mot = Motorized; non-Mot = non-Motorized; P = Prohibited; L/R = Column Shift(s) left/right.`

| Terrain Type | CP non-Mot | CP Mot | Breakdown Value | Barrage | Anti Armor | Close Assault | Stacking |
|---|---|---|---|---|---|---|---|
| Friendly Minefield¹³ | +1 | +4 | 0 | – | L1 | L1 | – |
| Enemy Minefield¹³ | +4 | +CPA | +2 | – | – | – | – |

**Note 13 (verbatim):** *"Engineer units reduce cost to enter (Case 26.2). If **assaulting** forces are
in an Enemy minefield, the non-Phasing forces receive L1 shifts for Anti-Armor and Close Assault if not
already receiving them for occupying a Friendly minefield."*

Reading: a unit **occupying and defending in** a Friendly minefield gets the L1/L1 defensive shifts
directly off this row. A unit **occupying an Enemy minefield while attacking out of it** gets no direct
row entry (dashes) — instead note 13 (which is the chart's encoding of rule 26.26) grants the
**defender** L1 Anti-Armor / L1 Close-Assault, *unless* the defender is already getting that shift for
being in its own Friendly minefield (no double-dipping). Breakdown Value: Friendly minefield hexside =
0 (no extra breakdown risk), Enemy minefield hexside = +2 Breakdown Points for a vehicle entering it.

**ALREADY IN `data/breakdown_rates.json`, key `terrain_breakdown_values_8_37.hexside.friendly_minefield`
(= 0) and `.enemy_minefield` (= 2) — verified against the scan, exact match, no discrepancy.**

**NOT in any data file yet** (confirmed by `data/cp_costs.json`'s own `_note`, which explicitly scopes
out "Terrain/minefield (TEC/CPA formulae)"): the CP-cost cells (+1/+4 Friendly, +4/+CPA Enemy) and the
combat-adjustment cells (L1/L1 Friendly; note-13's conditional L1/L1 for Enemy) are not yet transcribed
anywhere in `data/`. This document is their first transcription.

---

## 5. [24.17] Construction Chart — full transcription (verbatim, PDF p.104, chart-booklet page "9")

Columns: `Item | Situation | Unit(s) Required | Supplies Required* | Nr. Op Stages | Restrictions†`

| Item | Situation | Unit(s) Required | Supplies Required* | Nr. Op Stages | Restrictions† |
|---|---|---|---|---|---|
| 1 Level of Fortification | Build/Rebuild‡ | AnyE + Inf Bn with 3+ TOE | 30 Stores | 3 | May not be built in a Salt Marsh, Delta or Major City hex. May be rebuilt in a Major City hex in an enemy ZOC. No construction other than construction/demolition of ports and/or flying boat facilities may simultaneously occur in same hex. |
| **Real Minefield** | Build | EBn, ECoy or CHQᴱ | 15 Ammo + 15 Stores | 1 | May only be built in Clear, Sand/Gravel and Salt Marsh hexes. |
| **Fake Minefield** | Build | EBn, ECoy or CHQᴱ | 3 Stores | 1 | As above. |
| Railroad | Build | NZRRC | 1 Stores | 1 | Building limited to head of track. |
| Railroad | Rebuild | AnyE | 1 Stores/hex | 1 | One hex and any two adjacent hexes may be rebuilt simultaneously. |
| Road | Build/Rebuilt | a) Inf Bn with 3+ TOE *or* ECoy, HQᴱ; b) EBn *or* ECoy, HQᴱ + Inf Bn with 3+ TOE | 2 Stores/hex | 1 | May only build in "unfinished road" hexes. a) Only the hex occupied. b) The hex occupied and any two adjacent hexes. May combine building and rebuilding except as restricted above. |
| Temporary Repair Facility | Build | AnyE | 50 Fuel + 250 Stores | 1 | May only be built in a Major City or Village/Town hex. |
| Repair Facility | Rebuild 1 Level‡ | AnyE | 10 Fuel + 50 Stores | 1 | May be rebuilt in an enemy ZOC. |
| Water Pipeline | Build/Rebuild | EBn or CHQᴱ | 10 Stores | 1 | May only be built from a Major City hex. Building limited to head of pipe. |
| Airfield | Build | EBn or CSGSU | 50 Fuel + 100 Stores | 3 | May only be built in Clear, Major City, Desert and Sand/Gravel hexes. |
| Air Field *or* Air Landing Strip | Rebuild 1 Level‡ (Air Field) / Build (Air Landing Strip) | EBn, ECoy or SGSU | 10 Fuel + 20 Stores | 1 | As Airfield above. |
| Flying Boat Basin | Build | EBn or CSGSU | 25 Fuel + 50 Stores | 3 | In any Coastal hex (only) regardless of terrain. |
| Flying Boat Basin *or* Flying Boat Alighting Area | Rebuild 1 Level‡ (Basin) / Build (Alighting Area) | EBn, ECoy or SGSU | 10 Fuel + 10 Stores | 1 | As Flying Boat Basin above. |
| Port | Block 1 Level‡ | EBn or CHQᴱ | a) Tobruk: 50 Ammo + 25 Stores; b) Other: 25 Ammo + 10 Stores | 1 | The ports of Tripoli, Bizerta (Tunis), Alexandria (E3613), Aboukir (E3815) and Rosetta (E4019) may not be blocked. |
| Real Supply Dump | Build | Any unit with 1+ TOE | 10 Stores | 3 CP's | None. |
| Fake Supply Dump | Build | Any unit with 1+ TOE | none | 2 CP's | May not be constructed if the percentage of Fake Supply Dumps in play is, or would exceed, 50% of the Real Supply Dumps in play. |

**Key (verbatim):** *Nr. Op Stages = Number of Operations Stages of construction required. AnyE = Any
engineer battalion, engineer company or headquarters unit with engineering capability. EBn = Engineer
battalion. ECoy = Engineer company. HQᴱ = Any headquarters with engineering capability. CHQᴱ = Allied
headquarters with engineering capability. SGSU = Any Squadron Ground Support Unit. CSGSU = Allied
Squadron Ground Support Unit. Inf Bn with 3+ TOE = Any infantry-type battalion possessing at least
three TOE Strength Points. CP's = Capability Points.*

**Notes (verbatim):** *† = Unless otherwise stated, an item may not be constructed in an enemy ZOC. * =
If the hex is affected by Hot Weather, an additional 10 Water Points are required for each item, other
than a Supply Dump, under construction. ‡ = Only one may be built, rebuilt or blocked at a time.*

**Scan-verification correction (adversarial pass):** the Port row's Situation cell prints exactly **"Block 1 Level‡"** on the scan (PDF p.104). An earlier draft glossed this as "(i.e. *unblock*, see 24.18)" — that gloss was **wrong** and has been removed. *Blocking* a port is a **construction** action (obstruct your own port to deny its capacity; costs a) Tobruk 50 Ammo + 25 Stores, b) Other 25 Ammo + 10 Stores). *Unblocking* is the **distinct** action on the Demolition Chart (24.18, §6 below) with different costs (Tobruk 25 Ammo + 10 Stores; Benghazi 100 Ammo + 50 Stores; other 50 Ammo + 25 Stores). The two are not the same operation.

**Row-pairing note (not a contradiction):** the "Air Field or Air Landing Strip" and "Flying Boat Basin
or Flying Boat Alighting Area" rows each compress two Situations into one data row. This is the chart's
encoding of rule **24.76** — *"The cost and time to rebuild one Capacity Level of an airfield is the
same as it costs to build an air landing strip"* — extended by the chart (not stated in 24.7x's prose)
to the Flying Boat Basin/Alighting Area pair by exact analogy.

---

## 6. [24.18] Demolition Chart — full transcription (verbatim, PDF p.105, chart-booklet page "10")

Columns: `Item | Situation | Unit Required | Nr. Op Stages | Restrictions/Commentary`

| Item | Situation | Unit Required | Nr. Op Stages | Restrictions/Commentary |
|---|---|---|---|---|
| Fortification | Reduce 1 Level | Not allowed | — | May be reduced by air bombardment or barrage. |
| **Fake Minefield** | Clear | Any unit | 1 | Cleared at the end of the Movement Segment in which it is entered. |
| **Real Minefield** | Clear | Any E or tank bn with 6+ TOE of Scorpions | 1 | *(blank)* |
| Railroad | Destroy | Any E or inf bn with 3+ TOE | 1 | May also be destroyed by air bombardment or barrage. |
| Road | Destroy | Not allowed | 1 | May only be destroyed by air bombardment or barrage. |
| Repair Facility | Dismantle | Any E | 1 | May also be reduced by barrage or air bombardment. Recover 25 Fuel and 120 Stores when dismantled. |
| Water Pipeline | Destroy | HQ E or any units with 1+ TOE | 1 | May also be destroyed by barrage, strafing, and desert raider raids. |
| Air Facility | Reduce 1 Level | Not allowed | — | Airfields may be reduced, but not destroyed, by desert raider raids and may be reduced by air bombardment. |
| Port of Tobruk | Unblock 1 Level | E bn or CHQ E | 1 | As "other" port, except unblocking 1 Level requires 25 Ammo + 10 Stores. |
| Port of Benghazi | Unblock 1 Level | Total 2 E bn and/or CHQ E | 1 | As "other" port, except unblocking 1 Level requires 100 Ammo + 50 Stores. |
| Port (other) | Unblock 1 Level | E bn or CHQ E | 1 | Applies whether the port was blocked by mines or ships. Air bombardment damage is automatic. Requires 50 Ammo + 25 Stores to unblock 1 Level. |
| Fake Supply Dump | Destroy | Any unit | upon entry | May also be eliminated by a desert raider. |
| Real Supply Dump | Blow | Any unit | % of CP's | May be damaged by a desert raider raid, air bombardment, or barrage. |

**Key (verbatim):** *Nr. OpStages = Number of Operations Stages required to demolish the item. Any E =
Any engineer battalion, engineer company, or headquarters with engineering capability. E bn = Engineer
battalion. HQ E = Headquarters with engineering capability. CHQ E = Allied headquarters with
engineering capability. Inf bn with 3+ TOE = Any infantry-type unit with at least 3 TOE Strength
Points.*

**Cross-reference (not a contradiction, additional detail):** the "6+ TOE of Scorpions" clearing method
for a Real Minefield is explained by the **[4.47] Commonwealth Tank & Gun Characteristics Chart**
footnote (PDF p.138, dagger on the "Scorpion†" row, CPA 25 / AA 0 / Anti-Armor 0 / Armor Protection 7 /
Close Assault 0/(2) / Rate 3): *"These are mine-clearing tanks based on a modified Valentine chassis.
**They are treated as engineer units for all entering and clearing of minefields purposes** (see
Section 26.0). They do not arrive via the Commonwealth Production schedule but rather as the complement
of two tank battalions returning (from refitting) in October of 1942 (the tanks start with these units
in the El Alamein scenarios, Section 63.0)."* Note the footnote's scope is explicitly **entering and
clearing** — it does not say Scorpion-equipped tank battalions may *construct* (lay) minefields; 24.31
still requires an Engineering unit (or CW HQ Engineers) for that. **ALREADY IN `data/unit_stats.json`
key `scorpion`** (oca 0, dca 2, anti_armor 0, armor_protection 7, is_tank true — matches the [4.47]
chart on every field transcribed there; the chart's CPA 25 and Fuel Rate 3 are not yet in that file,
peripheral to this assignment so not further chased).

---

## OWNER RULING NEEDED

### #1 — Engineer-escort discount to enter an Enemy minefield: two different numbers, two different framings
- **Rule 23.21 (PDF p.36, verbatim):** *"The cost for a unit that is stacked with any Engineer unit (or
  HQ unit with Engineering capability) to enter an Enemy Minefield is reduced to **six CP's for
  Motorized units and three CP's for non-motorized units** (see Terrain Effects Chart, Case 8.37)."*
  — reads as a **total, replacement** cost, split by Mot/non-Mot.
- **Rule 26.24 (PDF p.38, verbatim):** *"Engineer units and combat units stacked with an Engineer
  battalion or Commonwealth HQs with Engineering capacity pay only **four additional** Capability
  Points to enter an Enemy minefield, rather than their listed cost."* — reads as a flat **+4 on top
  of** the normal terrain cost, and does not distinguish Mot/non-Mot.
- Both are numbered Cases in force (not draft text), both cite the same Terrain Effects Chart, and they
  disagree on both the number and the arithmetic (total-cost-of-6-or-3 vs. terrain-plus-4). This is the
  same class of internal contradiction as the 54.17 demolition-table misprint the project has already
  found and overridden once — but unlike that case, nothing on the Terrain Effects Chart itself (p.70)
  resolves it: the TEC's own Enemy Minefield row just says "+4 / +CPA" for the *unescorted* cost and
  is silent on the escorted discount, deferring to "Case 26.2" (per note 13) without printing a number.
- **Needs an owner ruling**, not an engine guess. I did not resolve this; both readings are transcribed
  above at 26.24 and here for cross-reference.

### #2 — Minefield construction terrain: "rough" (rule) vs. "Salt Marsh" (chart)
- **Rule 24.35 (PDF p.36, verbatim):** *"Minefields may be constructed in **clear, sand/gravel, or
  rough** hexes... Minefields may not be constructed in major cities."*
- **Construction Chart 24.17 (PDF p.104), Restrictions column, both the Real Minefield and Fake
  Minefield rows (verbatim):** *"May only be built in **Clear, Sand/Gravel and Salt Marsh** hexes."*
  ("As above" for Fake Minefield.)
- Rough vs. Salt Marsh is not a plausible OCR slip in either direction (different words, and both were
  read directly off 300dpi scans, the chart cell re-zoomed at 3x to confirm the "Salt Marsh" reading
  specifically). This is the assignment's most load-bearing discrepancy: it determines whether the
  Alamein "Devil's Gardens" belt can be laid in a Salt Marsh hex at all, and whether Rough terrain
  (common in the escarpment country) can carry minefields. **Needs an owner ruling** on which terrain
  list governs; I did not resolve it.

### #3 — Fortification construction: chart's port/flying-boat carve-out vs. rule 24.46's flat prohibition
- **Rule 24.46 (PDF p.36, verbatim):** *"No other construction — of any type — may take place in a hex
  which is undergoing fortification construction."* No exception stated.
- **Construction Chart 24.17 (PDF p.104), Fortification row, Restrictions column (verbatim, in full):**
  *"May not be built in a Salt Marsh, Delta or Major City hex. May be rebuilt in a Major City hex in an
  enemy ZOC. **No construction other than construction/demolition of ports and/or flying boat
  facilities may simultaneously occur in same hex.**"*
- The chart's final sentence reads as a carve-out: while a fortification is under construction in a
  hex, port and/or flying-boat facility construction/demolition may still proceed there, contrary to
  24.46's unqualified "no other construction of any type." Lower confidence than #1/#2 (it's plausibly
  the chart author's shorthand for "the general enemy-ZOC restriction, except for ports/flying-boats,"
  a different axis entirely, rather than a real exception to 24.46) — but it is exactly the kind of
  chart-vs-prose mismatch this project has learned not to silently pick a side on. **Flagging, not
  resolving.**

### Minor note (not a ruling item — chart is simply less complete than the rule, no conflict)
Rule 24.44 excludes **five** terrain types from new fortification construction (mountain, salt marsh,
desert, major city, delta). The Construction Chart's Fortification-row restriction text names only
**three** of them (Salt Marsh, Delta, Major City) before moving on to the ZOC/simultaneous-construction
sentence. Nothing in the chart contradicts mountain/desert also being excluded — it just doesn't
repeat the full list. Rule 24.44 should govern here; no ruling needed.

---

## Current engine state (informational only — I did not touch `game/` or `data/`, read-only per assignment)

- `game/construction.py` module docstring **explicitly** lists "24.3 minefields, 24.4 fortifications...
  DELIBERATELY NOT BUILT" — confirms this chart/rule pair is genuinely unimplemented, consistent with
  the port-plan audit. The file *does* implement 24.6 (railroads) and 24.9 (supply dumps) as its two
  built slices, and its `DUMP_STORES = 20` / `DUMP_CP = 3` constants follow **rule 24.9's** numbers, not
  the Construction Chart's (10 Stores / 3 CP real, 2 CP fake). This is a **fourth** discrepancy of the
  same shape as #1–#3 above, found incidentally while transcribing the full Construction Chart per the
  assignment's "any tables" clause; flagging for completeness even though supply dumps are outside the
  Rule 24.3/24.4/26 core (see Owner Ruling #4 below):
  - Rule 24.9 (PDF p.37, read via docs/rules OCR, not independently re-rendered — outside the assigned
    page range): *"A supply dump may be constructed by having any one TOE Strength Point of any type
    expend three Capability Points and 20 Store Points in a hex. A dummy supply dump may be constructed
    in a hex with an expenditure of three Capability Points only."*
  - Construction Chart 24.17 (PDF p.104, scan-verified above): Real Supply Dump = 3 CP's + **10**
    Stores; Fake Supply Dump = **2** CP's + none.
  - Two of three numbers disagree (Real Stores 20/10, Fake CP 3/2); only Real CP (3) matches. **OWNER
    RULING NEEDED #4**, same shape as #1–#3, not resolved here.
- `game/combat.py::resolve()` (the Close Assault resolver) already applies `MINEFIELD_CA_SHIFT = -1`
  (`game/combat_tables.py:350`) when `in_enemy_minefield=True`, matching rule 26.26 / TEC note 13 for
  the **Close Assault** half of that shift. `game/combat_tables.py::anti_armor_terrain_shift` has **no**
  equivalent minefield term, so the **Anti-Armor** L1 shift that the same note 13 / rule 26.26 grants
  the defender is not currently wired for anti-armor combat. Not my call to fix under this read-only
  assignment; flagging for whoever picks up 24.3/26 implementation.
- `game/movement.py` carries a `minefields: frozenset` field on the movement-relevant terrain state
  (consumed today only for the Close-Assault shift via `game/engine.py:4193`); none of 26.21's CP-cost
  formula, 26.24's engineer discount, or 26.25's destruction-roll are wired yet.
- No code or data currently reads the Construction Chart's Real/Fake Minefield rows, the Demolition
  Chart's minefield-clearing rows, or the `scorpion` role's chart-only "treated as engineer" minefield
  privilege.

## Flags summary (for the "OWNER RULING NEEDED" / unreadable-cell triage pass)
1. **OWNER RULING NEEDED** — 23.21 (6 Mot/3 non-Mot, total) vs 26.24 (+4 flat, additional) for the
   Engineer-escort cost to enter an Enemy minefield.
2. **OWNER RULING NEEDED** — 24.35 ("rough") vs Construction Chart ("Salt Marsh") for where minefields
   may be built.
3. **OWNER RULING NEEDED** (lower confidence) — 24.46 (flat prohibition) vs Construction Chart
   (ports/flying-boat carve-out) for concurrent construction in a fortification hex.
4. **OWNER RULING NEEDED** (found incidentally, outside core scope) — 24.9 (20 Stores / 3 CP dummy) vs
   Construction Chart (10 Stores / 2 CP dummy) for Supply Dump construction costs.
- No unreadable cells: every cell in the TEC minefield rows, the full Construction Chart, and the full
  Demolition Chart was legible at 300dpi (the Construction Chart only after a 90° rotation).
- Rule 24.5–24.9 body text and the [4.47] Scorpion chart row were read from `docs/rules/` OCR only (not
  independently re-rendered) since they sit outside the assigned page range and the OCR read
  internally-coherently; flagging this lower-confidence provenance rather than silently presenting them
  as scan-verified.
