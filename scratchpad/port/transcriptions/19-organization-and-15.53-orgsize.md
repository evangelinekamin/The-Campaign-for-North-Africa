# Rule 19 (Organization/Reorganization, Kampfgruppen) + [15.53] Organization-Size Close Assault Modifications Chart

Sources read: `docs/rules/19-organization-and-reorganization.md`, `docs/rules/15-close-assault.md`
(Case 15.5), `docs/rules/09-stacking.md` (Case 9.2/9.4, cited because it defines the "SP" terms
15.53 uses), `docs/rules/90-charts-tables-and-play-aids.md`. Scan pages rendered at 300dpi from
`tmp/The Campaign for North Africa.pdf` and read directly: **PDF pp. 096, 097, 101, 135, 174, 175**
(the `<!-- page NNN -->` markers in docs/rules ARE these PDF page numbers, confirmed 1:1 by
rendering and cross-checking content). Renders + crops left in
`scratchpad/render/p-{096,097,101,135,174,175}.png` and `scratchpad/render/crop135_*.png`
(session scratchpad, not this repo's `scratchpad/`, so not included in this commit — re-render
from the cited page numbers if needed).

**Status up front:** Rule 19 (the assign/attach/detach/Kampfgruppe hierarchy) is **entirely
MISSING** from the engine — `game/state.py`'s `Unit` has no parent/assigned/attached field at
all. [15.53] the org-size close-assault shift **IS implemented** (`game/combat_tables.py`,
`org_size_shift()` + `_ORG_SIZE_SHIFT`), **verified verbatim correct against the scan**, but is
**inert in practice today**: every unit's `stacking_points` comes from `unit_stats.json` via
`game/oob.py:779` (`stacking_points=s.get("sp", 1)`), and no role in `unit_stats.json` sets `sp`
above 0 (10 HQ/gun-type roles are explicitly 0; everything else defaults to 1). Nothing in the
current OOB ever reaches the Brigade(2)/Super-Brigade(3)/Division(5) tiers, so `org_size_shift`
can only ever fire on the (1,0)->2 "battalion vs. company-or-shell" edge case — exactly what the
assigning brief means by "this is inert today because every counter is SP 1." (Two placeholder
toy scenarios in `game/scenario.py`, `rommels_arrival`/`battle_for_tobruk`'s ancestor code, hard-code
`stacking_points=2` on all four of their units uniformly — also produces zero shift since both
sides tie. These are not the benchmark scenarios read by `tests/baselines.py`.) The rule that
would eventually feed 15.53 real Division/Brigade aggregates is 15.55 + 19: "a brigade is attached
to a division only if the brigade HQ unit (counter) is attached to the division" (15.55) — i.e.
Rule 19's assign/attach bookkeeping is the prerequisite for 15.53 to ever shift beyond 2.

---

## PART A — Rule 19: Organization and Reorganization

Full case text is already cleanly OCR'd in `docs/rules/19-organization-and-reorganization.md`
(PDF pp. 029–031); I read it end to end and it is coherent prose with no chart/table cells in
it, so no scan render was needed for Part A (only the charts it references — Part B below —
needed the scan). Summarizing the mechanics faithfully, case by case:

### 19.0 General rule
Every counter is either independent or **assigned** and/or **attached** to a Parent Formation.
Companies/battalions/brigades may be assigned/attached; **division HQs are always independent**.
Divisions, brigades, battalions may themselves be Parent Formations. Historical starting
assignments are on the OA Chart (Case 4.4, not this transcription's scope); the maximum TOE a
Parent Formation may hold is the Formation Organization Chart (19.3, Part B below); additional
non-assigned attachments are capped by the Maximum Attachment Chart (19.5, Part B below).

### 19.1 Assigned vs. Attached [19.11]–[19.14]
- **Assigned**: the unit is considered part of that Parent's organization (e.g. 8th Panzer
  Regiment starts assigned to 15th Panzer Division). Need not be in the same hex.
- **Attached**: the Parent Formation's counter on the map *represents* the attached unit too —
  same hex, functionally combined into one counter.
- A unit may have **one** assigned parent and **one** attached parent simultaneously (never two of
  either). A unit attached to a Parent Formation that is itself in turn attached to a *bigger*
  Parent Formation is considered attached to the bigger one too [19.46] (exception: 19.45
  substitute-attachments don't propagate up).

### 19.2 Unit Assignments [19.21]–[19.28]
- [19.21] A Parent Formation under its max (19.3) may be assigned more independent units up to
  that max — but the unit must **already be attached** to it to become assigned.
- [19.22]/[19.23] If a Parent Formation is eliminated, its surviving assigned units become
  independent and re-assignable. If an assigned unit itself is eliminated, its "slot" opens for a
  new independent unit (eliminated units don't count against the 19.3 cap).
- [19.24] OA-Chart-noted historical assignment shifts (e.g. 115th Pz.Gren.Rgt.: 15th Pz. -> 21st
  Pz.) are optional, must happen in the OA-Chart-listed month or not at all.
- [19.25] Commonwealth armored division/brigade assignment caps changed three times historically;
  the CW player may assign up to the new cap when it rises, must un-assign excess when it falls.
- [19.26] **Commonwealth-only battalion shuffle**: CW brigades (infantry or armor) may swap
  assigned battalions freely with another brigade or the unassigned pool — battalions may be
  *reassigned/shuffled* but never simply unassigned into independence.
- [19.27] Units marked with an asterisk on their counter (assigned to a Parent Formation that
  never reached Africa) may not be reassigned except via 19.26.
- [19.28] Only independent units may be assigned; an assigned unit cannot be assigned to a
  *second* Parent (except via 19.26). Assigned units occupy their Parent's TOE "slot" even when
  not physically attached/co-located.

### 19.3 Formation Organization Chart — see Part B (19.31/19.32/19.33)
Lists each Parent Formation's max *assigned* unit counts by type. Units with a singular OA-Chart
structure are governed by the OA Chart instead.

### 19.4 Attachment/Detachment restrictions and costs [19.41]–[19.47]
Capability Point cost table (this is the **6.3 Capability Point Expenditure Summary** chart,
verified against the scan alongside 15.53 below — see Part C):
| Action | CP cost |
|---|---|
| Detach a unit (both Parent and detaching unit) | 1 |
| Attach an **assigned** unit (both) | 1 |
| Attach an **unassigned** unit (both) | 2 |

- [19.41] Assigned-but-unattached unit -> attach: 1 CP each side, any time, same hex required.
- [19.42] Non-assigned unit -> attach: 2 CP each side, **Reorganization Segment only**, subject to
  19.4/19.5 limits; the unit must already have moved into the hex in an earlier Movement Segment.
- [19.43] Assigned-and-attached -> detach: 1 CP each side, any time.
- [19.44] Attached-but-not-assigned -> detach: 1 CP each side, Reorganization or Movement Segment
  only; if detached mid-Movement-Segment, that unit's (or the Parent's) movement must then stop
  unless they continue on as one stack.
- [19.45] A unit may attach to a Parent under its assignment max **as a substitute** for a
  "missing" assigned unit, as long as it doesn't exceed the organizational limits of the slot it's
  filling.
- [19.46] Attachment to an attached unit's own Parent propagates up (with the 19.45-substitute
  exception, which does not propagate).
- [19.47] Units already attached to the same Parent may be re-detached so as to attach to *each
  other* instead, at only the detachment CP cost (no re-attachment charge). Worked example given:
  132° Rgt. Corazzato + Nizza Cavalleria detach from Ariete Division, then N.C. attaches to 132°
  R.C. for free (beyond the detach cost).

### 19.5 Maximum Attachment Chart — see Part B, verified against scan (Part B.3)

### 19.6 Rebuilding Depleted Units [19.61]–[19.68]
- No unit may ever exceed its OA-Chart-printed maximum TOE Strength.
- [19.62] A unit eliminated by *combat attrition* (not breakdown) cannot be rebuilt from nothing —
  but an HQ that lost all assigned battalions may have new ones assigned as long as the HQ itself
  survives as a cadre.
- [19.63] An eliminated HQ *counter* may be revived (2 Infantry Replacement Points) only if >=50%
  of its assigned units still exist and are unattached elsewhere; otherwise it's gone for good.
- [19.64] Replacement-point rebuild rules: (a) Infantry RPs rebuild infantry-type/HQ/Engineer
  units; (b) Artillery units may be rebuilt with any gun type (CW medium/field-gun purity is a
  house-rule suggestion, not a rule); (c) Tanks may be assigned to any tank battalion/regiment
  (historical I-tank/Cruiser/Light distinctions are flavor, not mechanics); (d) Heavy Weapons
  Points require both Infantry RPs and Gun RPs.
- [19.65] Armored Recce/Armored Car units rebuild with Recce Points (Light Tanks may substitute,
  20.6).
- [19.66] A battalion "slot" vacated by elimination/reassignment may be filled by a *different*
  previously-unassigned battalion that would not normally qualify (example: 7th RTR filling the
  42nd RTR's eliminated slot in 1st Army Tank Brigade).
- [19.67] The Parent Formation's HQ unit is its Cadre — the Parent may be rebuilt/reassigned as
  long as the HQ exists; see 19.62/19.63 if the HQ itself is gone.
- [19.68] Rebuilding happens **Organization Phase only**. Cost: 1 CP (to the unit and its Parent,
  if applicable) per 2 Replacement TOE Strength Points added. Large infusions in one OpStage risk
  Disorganization Points — severely depleted units should retreat to rear areas first.

### 19.7 Axis Battle Groups (Kampfgruppen) [19.71]–[19.73]
- [19.71] **German** (and, more restrictedly, **Italian**) player may form Battle Groups from ad
  hoc/mixed-division units, **Organization Phase only**, all component units co-located in the
  same hex that phase, subject to Stacking + the caps below. Battle Group counters supply HQ
  support; historically named but usable freely.
- [19.72] **German** Battle Group cap: max **4 battalion-sized units** of any type, of which **no
  more than 1 tank battalion and/or 2 infantry battalions**. Up to **2 additional companies** may
  be attached over this base limit.
- [19.73] **Italian** Battle Groups: no physical counters provided — formed on paper from the
  Italian OA Sheet's Battle Group list if the Italian player wishes. Max **3 battalion-sized
  units**, of which **only 2 may be infantry** and **only 1 may be armor**; **1 company-sized
  unit** may additionally attach. **No more than 2 Italian Battle Groups may exist at once.**

### 19.8 Ad Hoc Axis Anti-Tank Batteries [19.81]–[19.87]
- Axis player may spend AT-Gun Replacement Points (Marders especially useful) to form new
  ad hoc AT batteries of **3–6 TOE Strength Points** of any one AT gun type.
- [19.81] Axis Brigade-level HQs (incl. Kampfgruppe) bearing an infantry-type symbol may hold up
  to **6 TOE SP of AT guns**.
- [19.82] Augmentation is legal only when **all** AT units on the map (Tripoli-Tunisia boxes
  count) are at **>=67%** of max TOE.
- [19.83] Initial assignment must be **>=3 TOE SP**; the HQ is treated as an AT unit for this.
- [19.84] Assigned AT Replacement Points train at the Gun Replacement Point rate.
- [19.85] An HQ holding AT TOE SP has a CPA equal to that of those AT points.
- [19.86] Only **one** AT gun type per HQ (may restart with a different type only after total
  elimination). Captured AT guns may never be used to augment.
- [19.87] An augmented HQ's Stacking Point value stays **zero** regardless of AT point count.

### 19.9 Augmenting Commonwealth Battalions with Anti-Tank [19.91]–[19.98]
- [19.91] From **Game-Turn 75 (1 April 1942)** on, the CW player may add AT-gun TOE SP to certain
  infantry battalions.
- [19.92] Eligible only: infantry battalions with **CPA Rating of 10** (motorized or not — i.e.
  "10+") **and** Off/Def Close Assault Ratings of **1/2 or 2/2**.
- [19.93] Such battalions gain a second weapon system (AT TOE SP) as a characteristic change.
- [19.94] Motorized battalions (CPA 10+) get up to **2 TOE SP** of AT guns; non-motorized (CPA
  exactly 10) get up to **1 TOE SP**.
- [19.95] AT points are assigned/trained as ordinary Gun Replacement Points.
- [19.96] Prohibited while **any** AT regiment assigned to that battalion's parent(s) is below max
  TOE.
- [19.97] Once absorbed, the AT points take the infantry unit's own CPA (10 walking / 20 or 25
  motorized).
- [19.98] AT TOE SP do **not** count toward that infantry unit's shell determination (9.26).

No internal contradictions or misprints found anywhere in the Rule 19 prose; OCR in
`docs/rules/19-organization-and-reorganization.md` reads clean and required no scan render.

---

## PART B — Formation Organization & Maximum Attachment Charts (19.3 / 19.5)

### B.0 ADVERSARIAL VERIFICATION CORRECTION (2026-07-23) — icon-prefix numbers are STACKING POINTS, not counts

A second reader independently re-rendered PDF pp. 101/135/174/175 at 300–500 dpi and read the
formation charts cell by cell. **Part C (15.53), and the 9.4 and 19.5 charts in B.1/C.2, are exact
— no change.** But the three Formation Organization charts (B.2/B.3/B.4) carry a systematic
mis-notation that must be corrected before anyone seeds TOE tables from them:

**The leading parenthesized number on every composition icon is that component's STACKING-POINT
VALUE** (the same `(5)/(3)/(2)/1/0` tier as the Unit-Type column and the 9.4 chart: division 5,
super-brigade 3, brigade/regiment/battle-group 2, battalion 1, company 0), **NOT a count.** The
*number* of each component is given by **how many times its icon physically repeats** in the row.
So `(2)[tankregt]` appearing once = *one* 2-SP tank regiment (which itself decomposes into two
1-SP tank battalions per the standalone "Armored Regiment" row), *not* "2× tank". This is confirmed
by the standalone regiment rows on every page (e.g. p.174 `(2)[tank] : 1[tank] 1[tank] 1[tank] =
Tank regiment`, and p.175 `(2)[inf] : 1[inf] 1[inf] 1[inf] = Infantry Regiment`).

Consequences for the transcription below:

- **B.4 German, row 1 (5th Light Panzer) — FLAT ERROR, corrected in place:** the leading icon was
  transcribed "2× ArtyHQ". It is a **`(2)`-SP tank regiment** — the identical icon that leads rows 2
  ("21") and 3 ("15") — i.e. Panzer Regiment 5. Corrected to "1× TankRegt (2-SP)". (The 5th Light
  has one 1-SP artillery *unit* later in the same row, slot 6, which is separate and was captured
  correctly.)
- **B.4 German, rows 2–5 and B.3 Italian, all division rows:** single `(2)`- and `(3)`-prefixed
  *regiment/brigade* icons are written with a leading "2×" / "3×" / "(2)×" / "(3)×". Read each as
  **one** component of that SP tier, not that many components. Specifically: B.3 Italian
  "Armored division" row reads **1× (2-SP) Tank Regt + 1× (2-SP) Infantry Regt** (+ armd-car + AT +
  arty), **not** "2× Tank Regt + 2× infantry-Regt"; B.4 German "15th Panzer" row reads **1× (2-SP)
  Tank Regt + 1× (3-SP) 15th Infantry Brigade + 1× TD + 1× (2-SP) Arty HQ + recon + eng**, **not**
  "2× TankBn + (3)× InfBde + … + (2)× ArtyUnit".
- **`0×` is the most dangerous case — it means "one 0-SP unit", never "zero units".** B.4 German
  "288 Son" ends `0[eng]` = *one* 0-SP engineer **company** (present), and B.3 Italian rows list
  `0[AT]`, `0[MGcoy]`, `0[recon]` = one 0-SP company each. The literal "0×" reading (absent) is
  wrong in every case.
- **B.2 Commonwealth (p.135) is unaffected** — that section already counted from icon repetition
  and read single `(2)`-prefixed icons as "1×" (e.g. "1× Armd Bde", "1× Support Gp"), which is the
  correct convention. Its earlier MEDIUM-confidence legibility flags still stand.

Where a `(2)`-SP regiment icon was expanded to "2× battalion" (e.g. B.4 "2× TankBn(III)"), that is a
defensible *decomposition* (a 2-SP regiment = 2 battalions) rather than a strict miscount, but the
`(3)×`/`(2)×`/`0×` brigade/HQ/company readings above are genuinely misleading and must be
re-counted from icon repetition at 600 dpi before use.

### B.1 [19.5] MAXIMUM ATTACHMENT CHART — PDF p. 101

**Verified verbatim against the scan — the existing `docs/rules/90-charts-tables-and-play-aids.md`
OCR (lines 916–958) is an EXACT match, cell for cell. No discrepancy.** Not in `data/`, and (per
Status note above) not wired into the engine at all — Rule 19 has zero code.

| Allied Unit Type | Maximum Attachment(s) |
|---|---|
| Armor Division (GT 1–67) | 2 units. 1 Infantry; no Tank. |
| Armor Division (GT 68+) | 3 units. 1 Infantry and/or 1 Tank. |
| Infantry Division | 2 units. 1 Infantry; no Tank. |
| Tank Brigade (GT 1–67) | 2 units. 1 Infantry; no Tank. |
| Tank Brigade (GT 68+) | 1 unit. No Tank. |
| other Brigade | 1 unit. |
| any Battalion | 1 Company. |
| Matruh Garrison (GT 1–12) | 6 units. No tank, 1 gun class. |
| Selby Force (GT 13+) | 5 units. No tank, no Recce, 3 infantry. |

| German Unit Type | Maximum Attachment(s) |
|---|---|
| Armor Division | 1 Brigade and 1 unit, **or** 4 units. No Tank. |
| Infantry Division | 1 Brigade, **or** 3 units. No Tank. |
| Infantry or Armor Regiment | 1 unit. |
| Battle Group | 4 units. |
| Artillery Brigade HQ | 1 Artillery unit. |
| any Battalion | 1 Company. |

| Italian Unit Type | Maximum Attachment(s) |
|---|---|
| Armor Division/Tank Group | 2 units. |
| Infantry Division | 2 units. 1 Infantry or 1 Tank. |
| Brigade/Regiment | 1 unit. |
| Battle Group | 3 units. |
| any Battalion | No units. |

**Key (quoted verbatim):** "Unit = Refers to a counter which is at full strength, a
Battalion—or Company-Equivalent. Tank = Specifically Bn-Eq units composed of tank TOE Strength
Points. Infantry = All Infantry-type units with the exception of Machinegun and Heavy Weapons
units (whether or not they are motorized)."

**Modifications (quoted verbatim):** "Any nation's Division- and Brigade-equivalent units may
attach two non-Shell company-Equivalent units at no cost to the maximum attachments. Note that
three company-eq are equal to one Bn-eq unit and that the company-equivalents must comply with any
restrictions as to the type of units which may be attached to that Division or Brigade."

This chart directly matches German Battle Group max = 4 units (19.72's own text: "max four
battalion-sized units... no more than one tank battalion and/or two infantry battalions") and
Italian Battle Group max = 3 units (19.73's text: "maximum of three battalion-sized units"). No
contradiction between the case text and this chart.

### B.2 [19.31] COMMONWEALTH FORMATION ORGANIZATION CHART — PDF p. 135

`docs/rules/90-charts-tables-and-play-aids.md` (lines ~3066–3128) explicitly **punts on this
chart**: `"> **Dense chart/table — see PDF page 135.** This grid did not OCR cleanly enough to
reproduce reliably here; consult the original scan for exact values."` I rendered PDF p.135 at
300dpi and read it directly (whole page + 4 zoomed horizontal-band crops for the icon column).
The chart uses small NATO-style unit-branch icons (tank/infantry/artillery/AT/AA/MG/armored-car/
recon/engineer, each carrying its own echelon bar — I, II, III, X, XX) inline in prose rather than
a strict grid; markdown can't reproduce the glyphs, so each is named via the chart's own printed
KEY (quoted below, itself fully legible and NOT the part that failed OCR). Confidence is **HIGH**
for the Armored Division / Armored Brigade / Support Group rows (unambiguous icon shapes, clean
crops); **MEDIUM** for the three named-brigade rows at the bottom (18th Australian/1st Free
French/Polish; 3rd Indian/161st Indian Motor Brigade Group; 2nd Free French/1st Greek) where
several small "or"-branched icons cluster tightly — flagged per row below.

**Icon key, quoted/paraphrased from the chart's own legend (both columns, PDF p.135):**
- `(5)DivTank` = Armored division, Organization Type I/II/III/IV depending on time period.
- `(2)BdeTank` = Armored brigade, Organization Type I/II/III depending on time period.
- `1 TankBn` = Tank battalion.
- `(5)DivInf` = Infantry division. (No I–IV period variants — single organization throughout.)
- `(2)SptGp` = Support Group, Organization Type I/II/III depending on time period. "Technically
  the formation's name was changed to Motor Brigade Group after Game-Turn 70. However, the
  counter symbol has been retained so as to avoid confusion with the 'other' Commonwealth Motor
  Brigade Group, which was simply a motorized infantry brigade."
- `(3)InfBde` = Infantry brigade (effectively a battle group): the 18th Australian, 1st Free
  French, and Polish brigades.
- `(2)InfBde` = Infantry brigade (also the 3rd Indian Motor Brigade Group or 161st Indian Motor
  Brigade Group).
- `(2)InfBde·A` = Allied infantry brigade: 2nd Free French or 1st Greek brigades.
- `1 InfBn` = Infantry battalion (also 1 motorized infantry battalion, or 1 Marine infantry
  battalion, or 1 Commando infantry battalion).
- `1 ArtyUnit` = Artillery unit: any of Artillery regiment (III), artillery battalion (II), or
  self-propelled artillery regiment (III).
- `1 ATRegt` = Anti-tank regiment: any of Anti-tank regiment (III), anti-tank/anti-aircraft
  regiment (III), or tank destroyer regiment (II).
- `ATUnit` (no numeral prefix) = Anti-tank unit: any of the immediately preceding, or an anti-tank
  company (0 SP).
- `LtAAUnit` = Light anti-aircraft unit: either a light AA regiment (III) or a light AA battalion
  (II).
- `1 MGBn` = Machinegun infantry battalion.
- `1 ArmdCarUnit` = Armored car unit: either an armored car regiment (III) or an armored car
  battalion (II).
- `1 ArmdReconUnit` = Armored reconnaissance unit: either an armored recon regiment (III) or an
  armored recon battalion (II).
- `1 EngBn` = Engineer battalion: either the 2/1 Australian Pioneer Battalion, or a tank battalion
  comprised solely of Scorpion (flail) tanks.
- `[ ]` (blank box) = "Unit. Any unit, other than a tank battalion, whose counter bears a
  Stacking Point value of one or zero."

(Correction to my own first-pass read: I initially mis-copied the "Armored reconnaissance unit"
legend line as printed twice — a re-crop of that exact region confirms it is printed **once**.
That was my transcription error, not a book misprint; noting it so nobody chases a phantom
duplicate.)

**Composition rows** (HIGH confidence unless flagged):

| Unit Type (SP, icon) | GT range | Composition |
|---|---|---|
| Armored Division (5) | I: GT 1–18 | 2× Armd Bde (I) + 1× Support Gp (I) |
| Armored Division (5) | II: GT 19–70 | 2× Armd Bde (II) + 1× Support Gp (II) + 1×(Armd Car unit **or** Armd Recon unit) |
| Armored Division (5) | III: GT 71–91 | 1× Armd Bde (III) + 1× Support Gp (III) + 1× Armd Car unit |
| Armored Division (5) | IV: GT 92+ | 1× Armd Bde ("II"-marked in the source, see note) + 1× Support Gp + 3× Artillery unit + 1× AT Regt (III) + 1× Lt AA unit (III) + 1× MG Bn (II) + 1× Eng Bn + 1×(Armd Car unit **or** Armd Recon unit) |
| Infantry Division (5) | *(no period variant)* | 3× Support Gp (X-echelon icon, i.e. the same "Support Group" glyph as above, **not** the plain Infantry-Brigade glyph — see flag below) + 3× Artillery unit + 1× AT Regt (III) + 1× Lt AA unit (III, numeral prefix faint/possibly elided — flagged) + 1× MG Bn (II) + 1× Eng Bn + 1×(Armd Car unit **or** Armd Recon unit) |
| Armored Brigade (2) | I: GT 1–18 | 3× Tank Bn |
| Armored Brigade (2) | II: GT 19–70, 92+ | 3× Tank Bn + 1× infantry-type Bn (icon ambiguous between plain Infantry Bn and MG Bn at this resolution — flagged) |
| Armored Brigade (2) | III: GT 71–91 | 3× Tank Bn + 1× infantry-type Bn (same ambiguity) + 1× Artillery unit |
| Support Group (2) | I: GT 1–18 | 2× infantry-type Bn + 1× Artillery unit + 1× AT Regt (III) + 1×(Armd Car unit **or** Armd Recon unit) |
| Support Group (2) | II: GT 19–70 | 1× infantry-type Bn + 1× Artillery unit + 1× AT Regt (III) |
| Support Group (2) | III: GT 71–91 | 3× infantry-type Bn + 1× Artillery unit |
| Infantry Brigade (3) — 18th Australian/1st Free French/Polish | *(none)* | 3× Infantry Bn + 1× Artillery unit + 1× AT unit + 1×(Lt AA unit **or** MG Bn) + 1×(Armd Car unit **or** Armd Recon unit) + 1× "Unit" (blank-box, SP 0/1) — **MEDIUM confidence**, several tight "or" icon clusters |
| Infantry Brigade (2) — 3rd Indian / 161st Indian Motor Bde Gp | *(none)* | 3× Infantry Bn |
| Allied Infantry Brigade (2)·A — 2nd Free French/1st Greek | *(none)* | 3× Infantry Bn + 1×(Artillery unit **or** AT unit) + 1× "Unit" (blank-box) — **MEDIUM confidence** |

**Flags on this specific chart (not book contradictions — legibility flags at the icon level):**
1. The Armored Division Type IV row's first composition icon is printed with a small **"II"**
   echelon-adjacent numeral where I would have expected "IV" for consistency with the row's own
   period label; I've transcribed exactly what's printed rather than "correcting" it — a future
   implementer pulling exact TOE tables should re-crop this one cell at higher zoom to confirm
   whether that's a genuine period cross-reference (Type IV reusing a Type II sub-brigade
   structure) or a print quirk.
2. The Infantry Division row's Light AA icon has no clearly legible "1" numeral prefix (every
   neighboring icon in that row does); most likely elided by line-wrap, transcribed as "1" by
   analogy with the identical item in the Armored Division IV row directly above it.
3. Within the Armored Brigade Type II/III and Support Group rows, the "infantry-type battalion"
   icon is visually similar between the chart's "plain Infantry Bn" and "Machinegun Bn" glyphs at
   this render resolution; I default to "infantry-type Bn" generically rather than force a
   specific branch call.
4. The two named-brigade special rows at the very bottom (Australian/French/Polish; Free
   French/Greek) pack several small "X or Y" icon pairs into a tight space — MEDIUM confidence,
   flagged above.

None of this rises to "OWNER RULING NEEDED" — there's no printed contradiction, only small-glyph
legibility at 300dpi. Given Rule 19 is wholly unimplemented and 15.53 is inert (Status note
above), I did not spend further passes re-cropping at higher DPI; a future phase that actually
builds Rule-19 aggregation should re-render p.135 at 600dpi and crop tightly on flags 1–4 before
trusting exact battalion counts.

### B.3 [19.32] ITALIAN FORMATION ORGANIZATION CHART — PDF p. 174

This chart prints a plain-English name directly after each composition (e.g. "= Armored
division."), so it is unambiguous and I transcribe it at **HIGH confidence** throughout.

**Icon key (bottom of page, quoted):**
- `1 TankBn` = Tank battalion.
- `1 InfBn` = Infantry battalion: any of (Leg) infantry battalion, motorized infantry battalion, or
  parachute infantry battalion. "Note that an infantry regiment is normally comprised of infantry
  battalions of the same 'style'."
- `1 InfBn·Brs` = Bersaglieri motorized infantry battalion.
- `1 InfBn·Brs` (different glyph) = Bersaglieri motorcycle infantry battalion.
- `1 MGBn` = Machinegun infantry battalion.
- `0 MGCoy` = Motorized machinegun infantry company.
- `1 ATBn` = Anti-tank battalion: either an anti-tank battalion, or up to three anti-tank companies.
- `0 ATCoy` = Anti-tank company.
- `ATUnit` = Anti-tank unit: either an anti-tank battalion or an anti-tank company.
- `1 ArtyRegt` = Artillery regiment: either an artillery regiment, up to three artillery
  battalions, or a parachute artillery regiment.
- `1 ArtyBn` = Artillery battalion. "Armored divisions may assign SP artillery battalions."
- `AAUnit` = Anti-aircraft unit: any anti-aircraft unit.
- `1 CavBn` = Cavalry battalion: either a cavalry battalion or a camel cavalry battalion.
- `ArmdCarRegt` = Armored car regiment.
- `ArmdCarBn` = Armored car battalion.
- `0 ReconCoy` = (Bersaglieri) motorcycle reconnaissance company.
- `1 EngBn` = Engineer battalion.

**Composition rows** (verbatim, "=" plain-English name is the chart's own):

| Unit Type (SP) | Composition | Name |
|---|---|---|
| (5) Armored div. icon | 2× Tank Regt + 2× infantry-Regt-icon + 1× ArmdCar unit + 1× AT unit + 1× Arty Regt | **= Armored division.** |
| (5) Tank Group, GT 1–26 | 3× Tank Regt + 3× Tank Regt | **= Tank Group. In CNA, specifically the Libyan Tank Command.** |
| (5) Motorized inf. div. icon | 2×+2×+2× infantry-Regt-icon + 1× AT unit + 1× Arty Regt + AA unit + 1× MG Bn + 1× Eng Bn | **= Motorized infantry division.** |
| (5) Semi-motorized inf. div. icon | 2×+2× infantry-Regt-icon + AT unit + 1× Arty Regt + 1× MG Bn + 1× Eng Bn + 1× InfBn(Brs) **or** 0× ReconCoy(Brs) | **= Semi-motorized infantry division.** |
| (5)+(5) Libyan/parachute div. icons | 2×+2× infantry-Regt-icon + 0× AT unit + 1× Arty Regt | **= Libyan infantry and parachute infantry divisions. Note that the Gruppo Maletti may assign a third regiment.** |
| (3) icon | 4× Tank Bn + 1× Tank Bn (5 total) | **= Tank regiment. Historically, this consisted of four battalions of "Light" tanks and one battalion of "Medium" tanks.** |
| (2) icon | 3× Tank Bn | **= Tank regiment.** *(a smaller, 3-battalion regiment variant, distinct SP from the (3) version above)* |
| (2) icon | 3× InfBn(Brs) **or** 1× InfBn(Brs, other glyph) | **= Bersaglieri infantry regiment.** |
| (2) icon | 3× InfBn | **= Infantry regiment. Any of the following: Infantry Regiment, motorized infantry regiment, parachute infantry regiment. Note that the 54th Territorial and 4th of the 10th Army regiments are comprised of a single counter, not four.** |
| (2) icon | 3× Cavalry Bn | **= Cavalry regiment.** |
| (2) "Sahara" icon | 3× InfBn **or** 1× CavBn, + 1× MGBn + 0× MGCoy + 1× ArtyRegt | **= Specifically the Saharan detachment, an infantry regiment.** |
| (2) "RECAM" icon | 1× ArmdCarRegt + 0× ReconCoy + 1× ArtyBn + 1× EngBn | **= Specifically the Reggruppamento Esplorante del Corps Di Manovra. Note that this unit is not an armored regiment for the purposes of armored division assignment.** |

(The infantry-Regt-icon used inline within the division rows above is the chart's own
"(2)InfRegt" composite, itself expanded 3 rows down; I did not re-expand it recursively in the
division rows' cell to avoid a combinatorial transcription — a future implementer wanting the
literal battalion count under an Armored/Motorized/Semi-motorized/Libyan division should chain
through the "Infantry regiment" row above.)

No ambiguity flags on this chart — every row states its own English name, resolving any icon
uncertainty by cross-reference.

### B.4 [19.33] GERMAN FORMATION ORGANIZATION CHART — PDF p. 175

Also names each row explicitly; **HIGH confidence** throughout.

**Icon key (bottom of page, quoted):**
- `(2)ArtyHQ` = "Either any artillery headquarters, except the ArKo, and all its units; or any
  three artillery units whose counters possess one Stacking Point indicators."
- `1 TankBn` = Tank battalion.
- `1 TankDestroyerBn` = Tank destroyer battalion, or an anti-tank battalion.
- `1 ATBn` = Anti-tank battalion.
- `1 InfBn` = Any infantry-type battalion except a heavy weapons parachute infantry battalion.
- `1 HvyWpnParaBn` = Heavy weapons parachute infantry battalion.
- `1 ArtyUnit` = Any artillery unit whose counter possesses a one Stacking Point indicator.
- `1 ArmdReconBn` = Armored Reconnaissance battalion.
- `1 HvyAAUnit` = Heavy Anti-aircraft unit.
- `1 LtAAUnit` = Light anti-aircraft unit.
- `1 EngBn` = Engineer battalion.
- `0 EngCoy` = Engineer company.

**Composition rows (named divisions/brigades/regiments, verbatim SP + named units):**

| Unit (SP, ID) | Composition | Name |
|---|---|---|
| (5) "5 Le" | 1× TankRegt (2-SP) + 1× InfBn + 1× InfBn + 1× TankDestroyerBn + 1× ATBn + 1× ArtyUnit + 1× HvyAAUnit + 1× LtAAUnit + 1× ArmdReconBn + 1× EngBn | **= 5th Light Panzer Division (becomes the 21st Panzer Division.)** |
| (5) "21" | 2× TankBn(III) + (2)× InfBn-Regt + 1× TankDestroyerBn + 1× ATBn + 1× ArtyUnit + 1× ArtyUnit + 1× HvyAAUnit + 1× LtAAUnit + 1× ArmdReconBn + 1× EngBn | **= 21st Panzer Division.** |
| (5) "15" | 2× TankBn(III) + (3)× InfBde"15" + 1× TankDestroyerBn + (2)× ArtyUnit + 1× ArmdReconBn + 1× EngBn | **= 15th Panzer Division** |
| (5) "90 Le" | (2)× InfBde + (2)× InfBde + 1× InfBn + 1× InfBn + 1× ATBn + 1× ArtyUnit + 1× ArmdReconBn + 1× EngBn | **= 90th Leichte Afrika Division.** |
| (5) "164 Le" | (2)× InfBde + (2)× InfBde + (2)× InfBde + 1× ATBn + (2)× ArtyUnit + 1× LtAAUnit + 1× ArmdReconBn + 1× EngBn | **= 164th Leichte Afrika Division.** |
| (2) | 2× TankBn | **= Armored Regiment.** |
| (3) "15" | (2)× InfBn-Regt + (2)× InfBn-Regt + (2)× InfBn-Regt | **= 15th Infantry Brigade. The brigade may never contain more than six battalions of infantry.** |
| (3) "Ramcke" | 5× InfBn | **= Ramcke Brigade.** |
| (2) | 3× InfBn | **= Infantry Regiment. The 28th Sonderverband and 361st Afrika regiments may be freely substituted for any 'normal' infantry regiment. No Battle Group may be assigned to a division.** |
| (2) "288 Son" | 3× InfBn + 1× ATBn + 0× EngCoy | *(288th Sonderverband, substitutable per the row above)* |
| (2) "361 Af / 90 Le" | 2× InfBn + 1× ArtyUnit | *(361st Afrika, substitutable per the row above; the "90 Le" sub-label ties it to the 90th Leichte Afrika Division)* |

No ambiguity flags on this chart either — icons and named units are all clearly legible at 300dpi
and every division/brigade is individually named (this is a roster of the actual historical
formations, not an abstract type-by-organization-period table like the Commonwealth chart).

---

## PART C — [15.53] ORGANIZATION SIZE CLOSE ASSAULT MODIFICATIONS CHART

**PDF p. 096.** Rendered at 300dpi and read directly. **Result: the existing
`docs/rules/90-charts-tables-and-play-aids.md` OCR (lines 572–583) is an EXACT verbatim match to
the scan.** No discrepancy.

| Largest Unit On — Larger Side Is | Smaller Side Is | Adjustment |
|---|---|---|
| 5 SP's | 3 SP's | 1 |
| 5 SP's | 2 SP's | 2 |
| 5 SP's | 1 SP | 4 |
| 5 SP's | 0 SP | 8 |
| 3 SP's | 2 SP's | 0 |
| 2 or 3 SP's | 1 SP | 2 |
| 2 or 3 SP's | 0 SP | 4 |
| 1 SP | 0 SP | 2 |

**Key, quoted verbatim:** "**Largest Unit On** = Each Player's largest unit, in size-equivalents,
actually taking part in the combat in the hex. Note that only those TOE Strength Points actually
partaking of combat (although not necessarily Close Assault) in *that* hex contribute toward
determining size-equivalency. If, for example, a battalion did not contribute at least 50% of its
maximum TOE Strength Point Limit (due to being understrength, engaging in a Probe, contributing to
attacks in other hexes, whatever), that battalion is considered a shell, and may therefore affect
the size-equivalent of any brigade or division it is currently attached to. **Larger Side Is/
Smaller Size Is** = Either Player may possess the largest unit in that combat. Note that the
numbers of the various size-equivalent units engaging in this Close Assault do not matter. Only
the size of the largest unit. **5,3,2,1,0 SP's** = The largest unit's size in Stacking Points.
**Adjustment** = The number of columns to be shifted in the Larger Size Player's favor in that
Close Assault."

### C.1 The garbled inline duplicate in `docs/rules/15-close-assault.md` — RESOLVED, not a book contradiction
`docs/rules/15-close-assault.md`, under case [15.53] itself, carries a *second*, badly-OCR'd
rendering of this same chart using unit-type-name labels instead of SP labels:

```
| Larger Side | Smaller Side | Adjustment |
| Division | 3-point | 1 |
| Division | 3-point | Brigade |
| Division | 2-point | 2 |
|  |  | Brigade |
| Division | Battalion | 4 |
| Division | Company | 8 |
| Any Brigade | Battalion | 2 |
| Any Brigade | Company | 4 |
| Battalion | Company | 2 |
```

This looked, at first glance, like the "two readings, book prints it twice differently" pattern
that burned this project before (54.17). **It is not that.** Cross-referencing 9.4 STACKING POINT
VALUES (below) — Division=5 SP, "Super Brigade"=3 SP, (Standard) Brigade/Battle Group=2 SP,
Battalion=1 SP, Company=0 SP — the garbled table's rows map 1:1 onto the clean SP-based chart:
"Division vs. 3-point (Brigade)" = "5 SP's vs. 3 SP's" -> 1; "Division vs. 2-point (Brigade)" =
"5 SP's vs. 2 SP's" -> 2; "Division vs. Battalion" = "5 SP's vs. 1 SP" -> 4; "Division vs.
Company" = "5 SP's vs. 0 SP" -> 8; "Any Brigade vs. Battalion" = "2 or 3 SP's vs. 1 SP" -> 2; "Any
Brigade vs. Company" = "2 or 3 SP's vs. 0 SP" -> 4; "Battalion vs. Company" = "1 SP vs. 0 SP" -> 2.
The only row the garbled OCR dropped outright is "3 SP's vs. 2 SP's -> 0" (Super-Brigade vs.
standard Brigade — no shift), presumably lost to the same column-splitting OCR damage that broke
the "3-point / Brigade" and "2-point / Brigade" header cells across two visual rows. **Verdict: one
physical chart, one clean transcription (the 90-charts-tables version, now scan-verified) and one
badly-OCR'd duplicate of the same numbers in the prose file. No OWNER RULING needed; the
90-charts-tables transcription is authoritative and matches the scan exactly.**

### C.2 Supporting reference — [9.4] STACKING POINT VALUES (PDF p. 097, verified)
Not this transcription's primary assignment, but read and verified against the scan because it is
the chart that *defines* the "SP" vocabulary 15.53 uses, and because case 15.53 itself says "All
of the above are equivalents (9.2)":

| Full | Shell | Stacking Point Value |
|---|---|---|
| Division | – | 5 |
| Super* Brigade | Division | 3 |
| (Standard) Brigade, Battle Group | – | 2 |
| Battalion | Any Brigade Battle-Group | 1 |
| Company | Battalion, HQ any attached units | 0 |
| Truck Points in Convoy | – | 1/2 for ea. 5 or fraction thereof |
| Replacement Points | – | 1 for ea. 5 or fraction thereof |

Footnote, quoted: "*Term coined in order to distinguish those brigades which were in effect,
infantry-light divisions from 'standard' brigades. †Only comes into play when determining
Road/Track CP movement cost applicability." Reading confirmed exact match to the existing OCR in
`docs/rules/90-charts-tables-and-play-aids.md` (lines ~628–637).

Also cross-checked against rule 9.28 (`docs/rules/09-stacking.md`): "A unit that is a shell is
reduced one level to the next lowest-level formation for purposes of Unit Differentiation on
Close Assault (see Case 15.5)... Thus a division shell would be considered a brigade equivalent, a
brigade shell a battalion equivalent, and a battalion shell a company equivalent." — consistent
with the "Shell" column above: a shell Division reads as 3 SP (the "Super Brigade" tier, not the
generic 2-SP "standard Brigade" tier — the footnote explains "Super Brigade" exists specifically to
name this shell-division equivalence).

### C.3 Engine cross-check — ALREADY IN `game/combat_tables.py`, verified, no discrepancy
`game/combat_tables.py` lines 317–335 (`_ORG_SIZE_SHIFT` dict + `org_size_shift()`) already
encodes exactly this table:
```python
_ORG_SIZE_SHIFT: dict[tuple[int, int], int] = {
    (5, 3): 1, (5, 2): 2, (5, 1): 4, (5, 0): 8,
    (3, 2): 0, (3, 1): 2, (3, 0): 4, (2, 1): 2, (2, 0): 4, (1, 0): 2,
}
```
This is byte-for-byte the same eight (larger, smaller) -> adjustment pairs as the scan. `game/
combat.py:81` wires it into the Close Assault column shift (`shift += ct.org_size_shift
(attacker_size, defender_size)`), and `game/engine.py:4238-4239` computes `attacker_size`/
`defender_size` as `max(u.stacking_points for u in <participating units>)` — a faithful reading of
15.53's "Largest Unit On" definition **for the units actually in the fight**, though (per the
Status note up top) it can't yet reach the Division/Super-Brigade tiers because Rule 19's
assign/attach hierarchy (which is what would let a division HQ's `stacking_points` reflect its
attached brigades, per 15.55) doesn't exist in `game/state.py` yet. Nothing to fix here — this is
a correct, verified transcription already in code; the gap is Rule 19 itself, documented in Part A.

---

## Flags summary

- **OWNER RULING NEEDED:** none. The one thing that looked like a 54.17-class contradiction (the
  two differently-labeled 15.53 tables) is resolved in C.1 above — same chart, one clean OCR, one
  badly corrupted OCR of the identical numbers, not a book misprint.
- **Unreadable cells:** none. All six target scan pages (096, 097, 101, 135, 174, 175) rendered
  legibly at 300dpi.
- **Adversarial verification correction (2026-07-23):** the primary charts (15.53 in Part C, plus
  9.4 and 19.5) re-verified against a fresh 300–500 dpi render — **exact, no change.** One flat
  error corrected on the German Formation Organization chart (B.4 row 1: "2× ArtyHQ" → the (2)-SP
  tank regiment / Panzer Regiment 5) and a systematic notation fix documented in **B.0**: the
  parenthesized icon-prefix numbers on the Formation Organization charts are STACKING-POINT VALUES,
  not counts (component count = icon repetition). The Italian (B.3) and German (B.4) division rows
  overstate single (2)/(3)-SP regiment/brigade icons as "2×"/"3×", and "0×" means "one 0-SP unit"
  not "none". B.2 Commonwealth used the correct convention and is unaffected.
- **Lower-confidence transcription (not a contradiction, a legibility caveat):** the Commonwealth
  Formation Organization Chart (B.2, PDF p.135) — see the four numbered flags there. Recommend a
  600dpi re-crop of that page before any implementation phase treats its exact battalion counts as
  load-bearing.
- **Already verified against `data/`/code, no changes made (read-only task):** 15.53
  (`game/combat_tables.py`) and 19.5 Max Attachment / 15.53 / 9.4 (all exact matches to the
  existing `docs/rules/90-charts-tables-and-play-aids.md` OCR — that file needs no correction from
  this pass, only its own explicit "see PDF page 135" punt on the Commonwealth chart, which this
  document now fills in).
- **Implementation status (informational, no code touched — read-only task):** Rule 19
  (assign/attach/detach/Kampfgruppen) has no representation in `game/state.py` / `game/events.py`
  at all. `Unit.stacking_points` exists and 15.53's shift is correctly coded, but every unit in the
  live OOB (`data/unit_stats.json` via `game/oob.py:779`) defaults to `stacking_points=1` (10 HQ/
  gun roles are explicitly 0; nothing is 2, 3, or 5), so the org-size shift is currently inert
  above the trivial (1,0)->2 case — matching the assigning brief's framing exactly.
