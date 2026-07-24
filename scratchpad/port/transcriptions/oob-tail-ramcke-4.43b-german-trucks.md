# OOB TAIL: Ramcke Brigade, Sonderverband 288, 300th Oasis Battalion, [4.43b] German first-line trucks

**Assignment:** rules 4/60/61 + the OOB charts. Scope: the Ramcke Brigade counters (GT86-93), the
[4.43b] Axis reinforcement rows, Sonderverband 288, the 300th Oasis Bn, and the German first-line
truck schedule [61.43].

**Method:** every cell below was read from the rendered scan at 300dpi, not from the OCR in
`docs/rules/90-charts-tables-and-play-aids.md` (which garbles this chart — see Finding F1). Pages
rendered: **080, 081, 145, 146, 162, 163, 164** of `tmp/The Campaign for North Africa.pdf` (the
`<!-- page NNN -->` markers are literal PDF page numbers, confirmed against the chapter-boundary
markers in `docs/rules/60-*.md` / `61-*.md`).

**Headline result: nothing here needs new OOB rows.** `data/reinforcements_campaign.json` already
carries the Ramcke Brigade, Sonderverband 288 and 300th Oasis Battalion, and every unit/GT/OpS/morale
cell verified **exactly** against the scan (details below). The actual gap is **trucks**: none of the
541 rows in that file carry a truck field, and the engine's first-line-truck mechanism (`fl_light` /
`fl_medium` / `fl_heavy` on `game.state.Unit`, seeded by `oob._seed_first_line`) is only wired at
scenario t0, never at reinforcement arrival. This transcription supplies the **verified** GT/OpS/L/M/H
table needed to wire that seam, and it **corrects one cell** and **confirms the rest** of a prior draft
(`scratchpad/port/phase4-german-first-line-trucks-DRAFT.md`, dated 2026-07-19, explicitly marked "OCR
draft, not scan-verified").

---

## 1. The 300th Oasis Battalion

### 1.1 Organization chart — [4.45c] "300th Oasis Battalion (a)", scan p.163 (book folio 163)

Basic Morale: **0**. Note (a), printed under the table: *"The 300th Oasis Battalion was an
administrative, not an operational headquarters. The companies are independent company-level units."*
— i.e. there is no HQ counter, only the 13 companies.

| Unit | Counter Abbreviation | ID Code | TOE & Weapon System(s) | Arrives (OpS/GT) |
|---|---|---|---|---|
| 1st Oasis Koy | 1 | r | N | 1/25 |
| 2nd Oasis Koy | 2 | r | N | 1/25 |
| 3rd Oasis Koy | 3 | r | N | 2/25 |
| 4th Oasis Koy | 4 | r | N | 1/27 |
| 5th Oasis Koy | 5 | r | N | 2/29 |
| 6th Oasis Koy | 6 | r | N | 2/30 |
| 7th Oasis Koy | 7 | r | N | 2/30 |
| 8th Oasis Koy | 8 | r | N | 2/31 |
| 9th Oasis Koy | 9 | r | N | 2/31 |
| 10th Oasis Koy | 10 | r | N | 3/33 |
| 11th Oasis Koy | 11 | r | N | 3/34 |
| 12th Oasis Koy | 12 | r | N | 2/35 |
| 13th Oasis Koy | 13 | r | N | 1/39 |

(`N` = no special weapon system; `r` = the OA-chart ID code column, cosmetic/counter-art reference only.)

### 1.2 Cross-check against [4.43b] "Axis Land Unit Reinforcement Schedule", scan p.145-146

Every company's GT/OpS in the schedule matches §1.1 exactly, and the schedule additionally shows which
companies arrive **with** attached German first-line trucks (see §4 for the full truck table; only two
companies get any):

| GT/OpS | Schedule row (verbatim) |
|---|---|
| 25/1 | "Gm: 1st & 2nd Coys of 300 Oasis Bn. It: 55 Savona Div [Att: 7 CCNN Regt]; Trucks: 10 L, 45 M, 5 H." — the trucks belong to the **Italian** 55 Savona Div (they follow the `It:` tag), not the Oasis companies. |
| 25/2 | "Gm: 3rd Coy of 300 Oasis Bn." — no trucks. |
| 27/1 | "Gm: 4th Coy of 300 Oasis Bn." — no trucks. |
| 29/2 | "GM: 5th Coy of 300 Oasis Bn; Trucks: 20 H." — **20 Heavy** trucks, unambiguous (only unit in the OpS). |
| 30/2 | "...6th & 7th Coys of 300 Oasis Bn." (trailing off a German artillery entry) — no trucks. |
| 31/2 | "...8th & 9th Coys of 300 Oasis Bn." (trailing off HQ 8 Panzer Regt) — no trucks. |
| 33/3 | "Gm: 10th Coy of 300 Oasis Bn; Trucks: 10 M." — **10 Medium**, unambiguous. |
| 34/3 | "Gm: 11th Coy of 300 Oasis Bn." — no trucks. |
| 35/2 | "Gm: 12th Coy of 300 Oasis Bn." — no trucks. |
| 39/1 | "Gm: 30 Flak Bty, 13th Coy of 300 Oasis Bn." — no trucks. |

### 1.3 data/reinforcements_campaign.json — VERIFIED, no discrepancy

All 13 companies are present as `"group": "GE 300th Oasis Battalion"`, `"role": "oasis"`,
`"morale": 0`, `"nationality": "GE"`, with `arrival_turn`/`arrival_stage` matching §1.1/§1.2 cell for
cell (1st & 2nd → 25/1, 3rd → 25/2, 4th → 27/1, 5th → 29/2, 6th & 7th → 30/2, 8th & 9th → 31/2, 10th →
33/3, 11th → 34/3, 12th → 35/2, 13th → 39/1). **No truck fields present** — that is the gap (§4).

### 1.4 Scenario-start placement — rule [61.41], scan p.081, and `data/oob_desert_fox.json`

Rule text (verbatim, scan-verified against `docs/rules/61-*.md:146`, no OCR drift):

> "One Oasis Company (German) is at Maaten Groter (A 1318) and one at Magadah (A 0817)."

That is the complete Oasis-Bn presence in the Desert Fox / Race-for-Tobruk scenario start (rule 61.2:
scenario begins 3rd OpStage of GT26 — after the 1st/2nd Koy's GT25 arrival but the rule text names only
these two, not both of GT25's arrivals plus the 3rd Koy that would also have "arrived" by GT26/OpS3 on
the campaign track). `data/wells.json` independently anchors both hexes as the "Oasis Coy station"
source for the same rule.

**FLAG — OWNER RULING NEEDED (data bug, not a book contradiction):** `data/oob_desert_fox.json` seeds
**three** Oasis companies, not two:

```
"GE 1 - 300 OAS"  hex A1318  (Maaten Groter)   — matches rule 61.41
"GE 2 - 300 OAS"  hex A0817  (Magadah)          — matches rule 61.41
"GE 3 - 300 OAS"  hex A2016  (stale_oldloc A1916) — NOT in rule 61.41 at all
```

`A2016` is **sea** terrain (`data/terrain_A.json:654`), as is its `stale_oldloc` `A1916`
(`terrain_A.json:620`). Two other units — `"GE 5 Le - none"` (5th Light Panzer Div HQ) and
`"GE Rommel - DAK"` (DAK HQ) — sit at the identical hex and identical VASSAL pixel coordinate
`[1400, 3093]`, which is consistent with a px→hex rounding/snap error in the VASSAL extraction (see
memory `VASSAL coordinate formula`) rather than a deliberate placement — Rommel and the 5 Le Div HQ are
legitimate Desert-Fox-start units (both arrive on the campaign track before GT26/OpS3), just mapped to
the wrong hex. The 3rd Oasis Koy riding along at the same bad coordinate looks like the same bug, not
a second oasis company the scenario actually wants. Recommend: drop `"GE 3 - 300 OAS"` from
`oob_desert_fox.json`, and separately re-derive the correct land hex for the Rommel/5-Le-HQ stack — but
that hex-geometry fix is outside this transcription's scope; flagging both here since they share a root
cause. **This is a data bug, not a footnote/errata case, so no page cite for "the other reading" — the
rule (verified twice, OCR and scan) is unambiguous at two companies.**

---

## 2. Sonderverband 288

### 2.1 Organization chart — [4.45c] "Sonderverband 288", scan p.162 (book folio 162)

Basic Morale: **+1**.

| Unit | Counter Abbreviation | ID Code | TOE & Weapon System(s) | Arrives (OpS/GT) |
|---|---|---|---|---|
| Sonderverband 288 HQ | 288 Son | e | N | 2/76 |
| 2/288 Gebergs Inf Bn | 2 | m | U@3 | 2/76 |
| 3/288 SchwInf Bn | 3 | p | N | 2/76 |
| 4/288 Machinegewehr | 4 | q | N | 2/76 |
| 288 Panzerjaeger Bn | 288 | y | 2×5cm | 2/76 |
| 288 Pioneer Coy | 288 | gg | N | 2/76 |

Notes (verbatim): (a) "This unit is really a 'formal' Kampfgruppe, and, as it retained its formation
for a good deal of its stay in Africa it has been included as a specific unit. It was renamed the
PanzerGrenadier-Regiment Afrika late in October, 1942 (3/102)." (b, on the Gebergs Bn) "A *motorized*
mountain infantry unit!"

### 2.2 [4.43b] Reinforcement Schedule entry — scan p.146, GT76

| GT/OpS | Row (verbatim) |
|---|---|
| 76/2 | "Gm: Sonderverband 288 Regt; Trucks: 5 L, 18 M, 4 H." |
| 76/3 | "Gm: 708 Heavy Weapons Coy." — a **different** unit (the "708 SchwInf Koy" of the Unassigned Infantry Units sheet, arrives 3/76 per [4.45c]); the 288/708 numbering is coincidental, it is not part of Sonderverband 288. |

The schedule attaches the truck total to "Sonderverband 288 Regt" as a whole (it does not break the
5L/18M/4H down per sub-unit the way the OA chart breaks the six counters out individually) — this is
the only OpS in the campaign where Sonderverband 288 units arrive, so the attachment is unambiguous.

### 2.3 data/reinforcements_campaign.json — VERIFIED, no discrepancy (except the missing trucks)

All 6 units present as `"group": "GE Sonderverband 288"`, `morale: 1`, `nationality: "GE"`,
`arrival_turn: 76`, `arrival_stage: 2`. Roles look reasonable against the TOE column (HQ, motor_infantry
×2 for the Gebergs/SchwInf Bns, mg for 4/288, antitank/pak38 for 288 Panzerjaeger Bn, motor_infantry for
288 Pioneer Coy). **Gap: no truck field** — 5 L / 18 M / 4 H is unseeded (§4).

---

## 3. Fallschirmjaeger-Brigade Ramcke

### 3.1 Organization chart — [4.45c] "Fallschirmjaeger-Brigade Ramcke (a)", scan p.164 (book folio 164)

Basic Morale: **+2**.

| Unit | Counter Abbreviation | ID Code | TOE & Weapon System(s) | Arrives (OpS/GT) |
|---|---|---|---|---|
| Ramcke Bde HQ | Ramcke | b | N | 2/86 |
| I Bn (Kroh) | I Kroh | h | N + 1×7.5cm Lt Gun | 1/91 |
| II Bn (von der Heydte) | II vdH | h | N + 1×7.5cm Lt Gun | 1/92 |
| III Bn (Hubner) | III Hub | h | N + 1×7.5cm Lt Gun | 1/93 |
| IV Bn (Schweiger) | IV Sch | h | N + 1×7.5cm Lt Gun | 2/87 |
| V Bn (Burchardt) | **V Brc** | h | N + 1×7.5cm Lt Gun | 2/86 |

Note (a), verbatim: *"The Ramcke was virtually an airborne heavy weapons brigade. It may be airdropped.
The battalions are always solely infantry-type units for Barrage and Air Bombardment purposes."*

**Minor OCR correction:** `docs/rules/90-charts-tables-and-play-aids.md:4919` (this same OA table row)
reads the abbreviation as "V Bre"; the scan (rendered fresh at 600dpi and confirmed at 4x zoom, this
session) clearly prints **"V Brc"** (for Burchardt — the "c" and "e" are unambiguous at that
magnification). Cosmetic only — does not affect any GT/OpS/morale field.

### 3.2 [4.43b] Reinforcement Schedule entries — scan p.146, GT85-93 (column 2 → column 3)

| GT/OpS | Row (verbatim) | Ramcke unit | Trucks for Ramcke? |
|---|---|---|---|
| 85/1 | "Gm: 13th Company of the Brandenburg Regt." | — (not Ramcke) | — |
| 86/2 | "Gm: HQ Ramcke Bde, V/Burchardt Bn [Ramcke]." | HQ + V Bn | none printed |
| 87/2 | "Gm: IV/Schweiger Bn." | IV Bn | none printed |
| 88/2 | "Gm: II/46 Flak Bn." | — (not Ramcke) | — |
| 89/2-3 | "Gm: I/54 Flak Bn." / "Gm: 211 Flak Bn." | — (not Ramcke) | — |
| 90/2 | "It: IV(M) Bn [T]" | — (Italian, not Ramcke) | — |
| 91/1 | "Gm: 190 Panzerjaeger Bn [AT, 90 Le], 243 Flak Bn, I/Kroh Bn [Ramcke]." | I Bn (Kroh) | none printed |
| 91/3 | "Gm: 329 Flak Bn." | — (not Ramcke) | — |
| 92/1 | "Gm: II/Heydte Bn [Ramcke]. It: XIII(M) Bn [T]." | II Bn (vdH) | none printed |
| 92/2 | "Gm: II/12 Flak Bn, 358 Flak Bn. It: 16 Pistoia Div [Less: 57 Brs Bn]; Trucks: 5 L, 45 M." | — | trucks belong to **Italian** 16 Pistoia Div |
| 92/3 | "Gm: 860 Flak Bn." | — (not Ramcke) | — |
| 93/1 | "Gm: HQ 164 Light Div, III/Hubner Bn [Ramcke], 609 Flak Bn [164 Le]; Trucks: 30 M." | III Bn (Hubner) | **shared pool, 30 M**, not exclusive to Ramcke — three German formations arrive in the same OpS and per [61.43] "may be distributed among those units freely" |

**Every Ramcke arrival cross-checks exactly against §3.1** (HQ+V Bn 2/86, IV Bn 2/87, I Bn 1/91, II Bn
1/92, III Bn 1/93). **Ramcke gets no first-line trucks of its own anywhere in the schedule** — the one
truck figure appearing on a Ramcke arrival row (30 M at 93/1) is a shared pool with the newly-arriving
164th Light Division HQ and its 609 Flak Bn, not earmarked for III/Hubner Bn specifically.

### 3.3 Finding F1 — docs/rules/90 OCR error: GT91 should read GT93

`docs/rules/90-charts-tables-and-play-aids.md:3797` transcribes the row above (with III/Hubner Bn and
HQ 164 Light Div) under **GT "91"**. The scan (p.146) unambiguously prints **"93"** — confirmed by
cross-reading against [4.45c] (164th Light Div HQ arrives 1/93, `page_164`) and against III Bn (Hubner)
arriving 1/93 in the same table. `data/reinforcements_campaign.json` already has `III/Hubner Bn` at
`(93, 1)` — i.e. **the seeded data is already correct**; only the `docs/rules/90-*.md` transcription of
this one cell is wrong (an easy 3↔1 OCR slip in that typeface — compare the "93" digit shapes on
`page_164` to convince yourself). Worth a one-line fix in `docs/rules/90-charts-tables-and-play-aids.md`
if anyone is doing OCR cleanup passes; not touched here per the read-only mandate.

**Second, same-class OCR error, different row:** `docs/rules/90-charts-tables-and-play-aids.md:3809`
transcribes the Italian "57 Brs Bn [I, 16 Pist]; Trucks: 15 M" reinforcement under GT **"90"**. The scan
(p.146) prints it under **GT "99"**, OpS 2 — the very last row of the schedule, immediately before the
"Arrives = ..." footnote block. Not a Ramcke/Oasis/Sonderverband/trucks-relevant unit itself (it's
Italian and out of my nationality scope), flagged only because it sits in the same badly-OCR'd
neighborhood and would mislead anyone trusting `docs/rules/90-*.md` line-for-line for that chart.

---

## 4. [61.43] Axis Trucks — the rule, and the German first-line truck schedule it points to

### 4.1 Rule text, verbatim (scan-verified p.081, matches `docs/rules/61-*.md:168-190` exactly, no OCR drift)

> **[61.43] Axis Trucks**
> All German first line Trucks (which are indicated on the Reinforcement Schedule as being attached to
> arrived German units) may be distributed among those units freely.
>
> The Italian Player receives the following First-Line Trucks, which may be assigned as he sees fit to
> his units: Light 45, Medium 220, Heavy 50.
>
> The following Second/Third Line Trucks are available (for any and all purposes): Light 95, Medium
> 280, Heavy 50. It is firmly suggested that the Axis Player use these as Second/Third Line Trucks,
> otherwise he will have a hard time moving his Supply around.
>
> Additional second/third line trucks: 10 Medium Trucks at air facilities.

61.43 itself hands the Axis player **no explicit German first-line number** — it is a pointer. The
German first-line total is whatever's printed in the "Trucks:" column of the [4.43b] Reinforcement
Schedule, attached to German units as they arrive across the campaign (this is a **campaign-scenario**
concept; the Desert-Fox and Race-for-Tobruk scenarios instead re-derive their own opening truck pools
in [61.35]/[61.43]/[61.71]-[61.73], which is why this section is titled "Axis Trucks" but the German
half of it defers to the campaign-length schedule rather than listing a number). Compare rule
[53.11]/[53.13] (`docs/rules/53-trucks-and-transport.md:20`): "These are trucks attached directly to
the parent combat unit... not represented by counters." — i.e. exactly the `fl_light`/`fl_medium`/
`fl_heavy` fields already modeled on `game.state.Unit`.

### 4.2 The German first-line truck schedule, GT9-99, cell-by-cell scan-verified

Every German-nationality truck figure printed anywhere in [4.43b] (both pages, all ~90 rows read and
cross-checked; Italian-tagged truck figures excluded — those are listed for completeness in §4.4). This
supersedes `scratchpad/port/phase4-german-first-line-trucks-DRAFT.md`, which flagged itself
"NOT YET SCAN-VERIFIED": **21 of its 22 rows check out exactly against the scan; one (GT22) was wrong
and is corrected below.**

| GT/OpS | Arriving German unit(s) | L | M | H | Verified against |
|---|---|--:|--:|--:|---|
| 21/1 | 3rd Aufklarungs Bn, 39 Panzerjaeger Bn [5 Le] | 0 | 40 | 0 | scan p.145, exact |
| 22/2 | I/5 Panzer Bn, 606 Flak Bn [5 Le] | 10 | 0 | 10 | scan p.145, exact — **CORRECTED** (draft had this at 22/1, bundled with "HQ 5 Panzer Regt"; the scan prints "HQ 5 Panzer Regt [5 Le]," alone under OpS **1** with no truck note, and the trucks under OpS **2** with "I/5 Panzer Bn, 606 Flak Bn". See Finding F2. |
| 24/2 | II/5 Panzer Bn, 529+532 CD Arty Bn [5 Le] | 0 | 10 | 0 | scan p.145, exact |
| 25/3 | 2 MG Bn [5 Le] | 0 | 40 | 0 | scan p.145, exact |
| 26/1 | 8 MG Bn [5 Le] | 10 | 0 | 5 | scan p.145, exact |
| 27/3 | (15 Panzer Div) — "alone" | 0 | 40 | 0 | scan p.146, exact |
| 28/2 | (15 Panzer Div) — "alone" | 25 | 0 | 0 | scan p.146, exact |
| 29/2 | 5th Coy 300 Oasis Bn | 0 | 0 | 20 | scan p.146, exact |
| 29/3 | HQ 15 Panzer Div | 0 | 40 | 0 | scan p.146, exact |
| 31/1 | (15 Panzer Div) — "alone" | 0 | 20 | 0 | scan p.146, exact |
| 32/3 | 155 Schutzen Regt, I/155 Arty Bn [90 Le / 155] | 0 | 25 | 10 | scan p.146, exact |
| 33/1 | 33 Arty Regt [15] | 0 | 20 | 0 | scan p.146, exact |
| 33/3 | 10th Coy 300 Oasis Bn | 0 | 10 | 0 | scan p.146, exact |
| 38/2 | (90th Leichte Div) — "alone" | 0 | 0 | 5 | scan p.146, exact |
| 43/2 | (90th Leichte Div) — "alone" | 0 | 15 | 0 | scan p.146, exact |
| 44/2 | HQ 90 Light Div | 10 | 10 | 0 | scan p.146, exact |
| 76/2 | **Sonderverband 288 Regt** | 5 | 18 | 4 | scan p.146, exact |
| 93/1 | HQ 164 Light Div, **III/Hubner Bn [Ramcke]**, 609 Flak Bn [164 Le] | 0 | 30 | 0 | scan p.146, exact; GT confirmed 93 not 91 (Finding F1) |
| 93/2 | II/5 Flak Bn | 10 | 30 | 0 | scan p.146, exact |
| 94/2 | 164 Aufklarungs Bn [164 Le] | 0 | 25 | 20 | scan p.146, exact (Italian 185 Folgore Div's separate 5L/30M/5H on the same line correctly excluded) |
| 95/3 | 433 Panzergrenadier Regt [164 Le] | 0 | 25 | 0 | scan p.146, exact |
| 96/1 | (164th Leichte Div) — "alone" | 10 | 0 | 10 | scan p.146, exact |

**I read every remaining German-tagged row in the schedule (GT9-99, both pages) looking for any further
truck note and found none** beyond the 22 above — the table is complete. Ramcke and 300th-Oasis-Bn
truck rows (29/2, 33/3, 93/1) are the ones already broken out in §1/§3; Sonderverband 288's (76/2) in
§2.

Totals (unchanged from the draft's arithmetic — the GT22 correction moves an OpS label, not an L/M/H
value):
- **All German first-line, including the "alone" 15th/90th/164th-Div rows: 80 L / 398 M / 84 H = 562 TP.**
- **Attached-only (excluding "alone"): 45 L / 323 M / 69 H = 437 TP.**
- Comparable in size to the seeded Italian campaign first-line pool (55 L / 260 M / 45 H = 360 TP,
  `oob.CAMPAIGN_FIRST_LINE`) — wiring this roughly doubles the Axis first-line reservoir.

### 4.3 Finding F2 — OWNER RULING NEEDED: [4.43b] vs [4.45c] disagree on the 5th Panzer Regiment's own arrival (adjacent to my scope, not resolved here)

While reading GT21-24 to verify the truck cells above, I found the schedule's unit list for the 5th
Panzer Regiment does not match [4.45c] on **three** points (none of them touch Ramcke/Sonderverband/
Oasis, but they sit in the same two pages I was asked to transcribe, so flagging for whoever owns the
5th Light/21st Panzer Division chart):

| Unit | [4.45c] OA chart (scan p.162) says | [4.43b] Reinforcement Schedule (scan p.145) says |
|---|---|---|
| 5th Panzer Regt HQ | Arrives 2/21 | Printed at GT **22**, OpS **1** ("Gm: HQ 5 Panzer Regt [5 Le],") |
| I/5 Panzer Bn | Arrives 1/22 | Printed at GT 22, OpS **2**, paired with 606 Flak Bn and the 10L/10H trucks |
| II/5 Panzer Bn | Arrives 2/22 | Printed at GT **24**, OpS 2, paired with 529+532 CD Arty Bn and 10M trucks |

Both readings are scan-confirmed (not OCR artifacts) — this is the book disagreeing with itself, the
same class of error as the 54.17 misprint already on record. I have not attempted to adjudicate it; it
does not affect any figure in §4.2 (the L/M/H totals at 22/2 and 24/2 are unambiguous regardless of
which unit name is "correct"), so it does not block wiring the truck schedule. Both page images are
saved for reference in this session's scratch dir if a future pass wants them
(`page_145-145.png`, `page_162-162.png`, 300dpi).

### 4.4 Italian first-line trucks embedded in [4.43b] (context only, not this transcription's nationality — listed so nothing looks silently dropped)

Every Italian-tagged truck note in the schedule was read and excluded from §4.2 by design (61.43 gives
Italian first-line trucks as flat totals, 45/220/50, not a per-GT schedule — the Italian entries below
are trucks attached to specific arriving Italian divisions, additional to that flat pool, exactly
mirroring how German "alone" trucks are additional to the German attached total):

GT10/3 (10L,35M,15H – 61 Sirte Div), 11/1 (2L,25M,3H – 10 Brs Regt), 12/1 (10L,35M,15H – 60 Sabratha
Div), 18/1 (25L,40M,5H – 132 Ariete Div), 21/1 (10L,95M,15H – 102 Trento Div), 21/2 (15L,40M,10H – 27
Brescia Div), 22/2 (25L,30M – 17 Pavia Div), 24/1 (10L,30M,10H – 25 Bologna Div), 25/1 (10L,45M,5H – 55
Savona Div), 45/1 (10M – RECAM), 50/3 (10L,65M,5H – 101 Trieste Div), 62/3 (40L,50M – 133 Littorio Div),
70/2 (5M – 8 Armored Bers Bn), 92/2 (5L,45M – 16 Pistoia Div), 94/2 (5L,30M,5H – 185 Folgore Div), 97/1
(5L,20M – 136 GGFF Div), 99/2 (15M – 57 Brs Bn, the row Finding F1 relocates from the mislabeled "GT90"
in `docs/rules/90-*.md`).

---

## 5. Summary of flags

1. **OWNER RULING NEEDED** — `data/oob_desert_fox.json` seeds a 3rd "300 OAS" company at hex A2016
   (sea terrain) alongside Rommel's and the 5 Le Div's HQ counters at the same bad coordinate; rule
   61.41 (scan-verified twice) names only two companies (Maaten Groter, Magadah). Recommend dropping
   the 3rd company; the underlying hex-geometry bug for the co-located HQs is a separate fix. §1.4.
2. **Correction to prior draft** — `phase4-german-first-line-trucks-DRAFT.md` row "22/1" merged two
   OpS cells; the 10L/10H trucks belong at GT22/**OpS2**, not OpS1. §4.2.
3. **docs/rules/90-*.md OCR errors** (not fixed here, read-only mandate) — GT "91" should read GT
   **93** for the III/Hubner Bn / HQ 164 Light Div row (line 3797); GT "90" should read GT **99** for
   the 57 Brs Bn Italian truck row (line 3809); the Ramcke "V Bre" abbreviation (line 5458) should read
   **V Brc**. None of these affect already-seeded data — `data/reinforcements_campaign.json` has
   III/Hubner Bn at the *correct* (93, 1) already. §3.1, §3.3.
4. **OWNER RULING NEEDED (adjacent, not resolved)** — [4.43b] and [4.45c] disagree on which OpS the
   5th Panzer Regiment HQ, I/5 Panzer Bn and II/5 Panzer Bn arrive in. Does not touch Ramcke/
   Sonderverband/Oasis and does not block wiring §4.2's truck totals. §4.3.
5. **Carried forward from the draft** — the "alone" 15th/90th/164th-Division trucks are, per the
   footnote itself, the Axis player's free choice to treat as first-line (attached) or 2nd-3rd-line;
   this transcription does not adjudicate that either, it just confirms the six L/M/H figures involved.
6. **Nothing unreadable.** Every cell cited above was legible at 300dpi; no page needed a re-render at
   higher resolution.

## 6. What a future implementation pass needs

- §4.2's table is ready to wire as a GT/OpS-triggered addition to `fl_light`/`fl_medium`/`fl_heavy` on
  the newly-arrived unit(s), the same fields `oob._seed_first_line` already sets at t0 — this is a new
  seam (reinforcement-time truck attachment), not a new field.
- §1-3 need no data changes; they are here as verification, not gap-fill.
- Resolve flags 1 and 4 (owner rulings) before wiring if their answers would change unit placement or
  the 22/24 GT assignment; flag 5 (the "alone" trucks' first-line-vs-2nd/3rd-line choice) before
  wiring if the engine needs a single deterministic default rather than exposing the choice to a policy.
