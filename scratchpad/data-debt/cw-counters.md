# THE COMMONWEALTH COUNTER DEBT — measured, not inherited

> **STATUS 2026-08-04: PAID.** 90 of the 91 counters below are seeded (39 at Arrives `D` in
> `data/oob_campaign_extra.json`, 51 rule-20 arrivals in `data/reinforcements_campaign.json`), with
> nothing invented; the 91st (`200 Gds`) is absent because the book prints no arrival for it. The
> six transcription errors in §7 and §8 are repaired. Eighteen `[4.46a]` rows were added to
> `data/unit_stats.json` and `game.oob._make_unit` learned the charts' per-counter arrival TOE.
> **`scratchpad/data-debt/cw-counters-outcome.md` carries the measurement, the scored prediction and
> the debt this pass leaves** — the headline being that it is worth ~nothing on the 64.73 scoreboard
> and a great deal on the board: the Commonwealth holds and banks Mersa Matruh on 20 of 24 panel
> boards at Game-Turn 30 where it held it on 3, and the Axis railway stops being bought with
> captured Commonwealth stores. Builder: `scratchpad/data-debt/seed_4_44b.py`. Tests:
> `tests/test_cw_oob_4_44b.py`.

**Task:** locate the Commonwealth Order of Appearance charts, read every counter, diff against what
`game/oob.py` actually seeds, and produce the roster of what is missing.

**Verdict up front: the inherited "~175 unseeded Commonwealth counters" is WRONG, and so is the
inherited page citation "p.114-116".** The measured gap is **91 named counters absent outright**,
plus **11 named tank regiments collapsed into 4 aggregate counters**, for **102 charted counters with
no counterpart in the engine**. The charts are on PDF **p.116-132**, not p.114-116.

---

## 1. THE PAGE RANGE — verified by rendering, not inherited

The inherited citation "scan p.114-116" is wrong. Verified by eye at `pdftoppm -r 150` (and `-r 600`
for one disputed cell):

| PDF pages | Chart as the book heads it |
|---|---|
| p.114-115 | `[4.43a]` Commonwealth Land Unit Reinforcement & Withdrawal Schedule — **not** the OA chart |
| **p.116-132** | **`[4.44B]` COMMONWEALTH ORGANIZATION AT ARRIVAL CHART** — the roster, 38 sheets |
| p.133-134 | `[4.46a]` COMMONWEALTH UNIT CHARACTERISTICS CHART — the ID-code stat table |

Page 116 heads verbatim: `[4.44B] COMMONWEALTH ORGANIZATION AT ARRIVAL CHART`. So "p.114-116" caught
only the reinforcement schedule and the first OA page; **16 of the 17 roster pages were never in the
citation.** That is very likely how the "~175" was guessed rather than counted.

The chart's own column order is `Notes | Unit | Counter Abbreviation | ID Code | TOE & Weapon
System(s) | Arrives`, and `Arrives` prints **OpStage/Game-Turn** (`3/58` = OpStage 3 of GT 58;
`D` = Deployed at start).

### Pages re-rendered and read character-by-character for this pass
p.116, p.117, p.118, p.121, p.122, p.123, p.124, p.125, p.126, p.129, p.132, plus p.133 and p.134
(the characteristics chart). Every one matched the existing transcription
(`scratchpad/port/transcriptions/4.45a-oa-allied.md`) **except one cell**, corrected in §7.

> **2026-08-04 second pass.** The count above is 11 of the 17 `[4.44B]` roster pages, not 13 — p.133
> and p.134 are the characteristics chart, not the roster. The **six** unverified roster pages
> (**p.119, p.120, p.127, p.128, p.130, p.131**) have now been rendered and read character by
> character; **all six match the transcription exactly**, including its two printed-as-is anomalies
> (p.120's lowercase `d` Arrives on the 1st Argyll & Sutherland and its capital `M` ID on the 1st
> Durham Light Inf) and p.131's duplicated `1 SA Plc` counter abbreviation. All 17 roster pages are
> now independently verified. Every ID code in the §5 missing-91 roster was additionally re-read at
> 600 dpi; see §7.

---

## 2. WHAT THE ENGINE ACTUALLY SEEDS

Commonwealth counters reach the campaign by three paths, all folded by `game/oob.py`:

| Source | Count | Note |
|---|---|---|
| `data/reinforcements_campaign.json` (side ALLIED) | 364 | of which **47 are `(Rtn)` re-arrivals** — the same counter returning from Syria/Palestine, not a new counter |
| `data/oob_italian.json` (ALLIED, `kind=="unit"`) | 28 | the on-map Sept-1940 start line, VASSAL-derived |
| `data/oob_campaign_extra.json` (ALLIED) | 4 | `HQ 7 Armd Div`, `HQ 4 In Div`, `HQ 6 Aus Div`, `HQ 2 NZ Div` |

**Distinct seeded Commonwealth counters = 364 − 47 + 28 + 4 = 349.**

The `[4.44B]` chart prints **434 unit rows** across 38 sheets, minus 1 duplicate row (the 13th DCO
Lancers prints twice — once on its own Unassigned Indian sheet, once blank-ID as an *attachment* on
the 18th Indian Brigade sheet), plus 3 counters named only in the two prose-only sheets
(Selby Force ×1; 22nd Guards ×2 — the sheet states "there are two counters (*22 Gds* and the
*200 Gds*) provided for this unit").

**Charted Commonwealth counters = 433 + 3 = 436.**

---

## 3. HEADLINE NUMBERS

| Measure | Count |
|---|---|
| Counters the `[4.44B]` chart prints | **436** |
| Distinct counters the engine seeds | **349** |
| **Named counters missing outright** | **91** |
| Named tank regiments collapsed into aggregate counters | **11** (→ 4 seeded counters) |
| **Total charted counters with no engine counterpart** | **102** |

Grouping of the 91 outright-missing:

| Split | Count |
|---|---|
| Combat counters | **78** |
| Non-combat (pure HQ, ID codes `a`/`b`/`c`/`d`, no CA or weapon TOE) | **13** |
| Arriving **at or before GT 30** | **62** |
| Arriving **after GT 30** | **29** |
| ID code resolves to a printed `[4.46a]` row | **91 — all of them** |
| ID code that does NOT resolve (would require inventing) | **0** |

**Nothing on this roster needs inventing.** Every missing counter's ID code is one of 24 distinct
codes, all of which are rows the `[4.46a]` chart actually prints. That is the single most important
result for whoever seeds this: the book supplies the whole answer.

**The debt is front-loaded.** 62 of 91 arrive by GT 30 — i.e. the shortfall is heaviest exactly where
the campaign opens, not in the 1942 tail.

---

## 4. THE `[4.46a]` STATS EACH MISSING ID CODE IMPLIES

Read by eye off PDF p.133 (codes `a`–`bb`) and p.134 (codes `cc`–`uu`). Columns as printed:
`Unit Type | ID Code | CPA | Anti-Air | Barrage | Anti-Armor | Vulnerability | Armor Prtctn |
Close Assault Off/Def | Maximum TOE`. `–` = not applicable, as the chart prints it.

Only the 24 codes used by missing counters are reproduced here.

| ID | Unit Type | CPA | AA | Barr | AntiArm | Vuln | ArmPr | CA Off/Def | Max TOE |
|---|---|---|---|---|---|---|---|---|---|
| `a` | Headquarters | 30 | – | – | – | – | – | – | – |
| `b` | Headquarters | 30\* | – | – | – | – | – | – | (1) — may assign one tank TOE SP |
| `c` | Headquarters | 30 | – | – | – | – | – | – | 3 — may assign up to three artillery TOE SP |
| `d` | Headquarters | 20\* | – | – | – | – | – | – | (1) — may assign one tank TOE SP |
| `e` | Headquarters | 20 | – | – | 1 | 1 | – | 0/1 | 1 |
| `f` | Headquarters | 20 | – | – | 2 | 1 | – | 0/1 | 1 |
| `g` | Tank Bn-Eq | 25 | – | – | – | – | – | – | 10† — may assign up to ten tank TOE SP |
| `k` | Infantry Bn-Eq | 10 | – | – | – | – | – | 2/2 | 7 |
| `l` | Infantry Bn-Eq | 10+ | – | – | – | – | – | 2/2 | 6 |
| `m` | Infantry Bn-Eq | 10 | – | – | – | – | – | 2/2 | 6 |
| `n` | Infantry Bn-Eq | 10+ | – | – | – | – | – | 1/2 | 6 |
| `p` | Infantry Bn-Eq | 10 | – | – | – | – | – | 1/2 | 6 |
| `u` | Infantry Bn-Eq | 8 | – | – | – | – | – | 4/6 | 3 |
| `v` | Infantry Company-Eq | 10+ | – | – | – | – | – | 1/1 | 1 |
| `w` | Infantry Company-Eq | 8 | – | – | – | – | – | 4/6 | 2 |
| `x` | Artillery Bn-Eq | 20 | – | – | – | – | – | – | 6 — may assign up to six artillery TOE SP |
| `y` | Artillery Bn-Eq | 20 | – | – | – | – | – | – | 4 — may assign up to four artillery TOE SP |
| `aa` | Anti-tank Bn-Eq | 15 | – | – | – | – | – | – | 8 — may assign up to eight anti-tank TOE SP |
| `bb` | Anti-tank Bn-Eq | 15 | – | – | – | – | – | – | 6 — four anti-tank + two Light AA TOE SP |
| `dd` | Anti-tank Company-Eq | 15 | – | – | – | – | – | – | 2 — may assign up to two anti-tank TOE SP |
| `ee` | Light Anti-air Bn-Eq | 15 | – | – | – | – | – | – | 6 — may assign up to six Light AA TOE SP |
| `ll` | Reconnaissance Bn-Eq | 45 | – | – | – | – | 1 | 2/3 | 8 |
| `pp` | Reconnaissance Bn-Eq | 45 | – | – | – | – | 2 | 2/3 | 6 |
| `ss` | Reconnaissance Bn-Eq | 45 | – | – | – | – | 1 | 1/2 | 4 |

Chart footnotes that bear on seeding (verbatim sense, p.134): `+` = "the unit was historically supplied
with enough trucks to entirely motorize its components… If motorized, only the unit's Capability Point
Allowance changes during the period of its motorization." `*` = "The unit retains this Capability Point
Allowance regardless of the CPA of the TOE Strength Points assigned." `†` = "If the unit is comprised
entirely of US tank TOE Strength Points, its maximum TOE Strength is nine points." `( )` = "May not use
that rating if there are any units in that hex that possess Ammo *and* non-parenthesized numbers for
that rating."

Note also p.134 Note 4: the two units with ID Codes `h` and `j` are **non-motorized** (the SAS may be
motorized by a Commonwealth LDG, Case 27.88) — relevant because both are already seeded.

---

## 5. THE ROSTER OF MISSING COUNTERS

Format: `Unit name | Counter Abbr | ID | TOE & Weapon System(s) | Arrives (OpStage/GT)`.
Every row below was read off the rendered page cited in its heading.

### 1st Armored Division — p.116 — 5 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 1st Rifle Brigade | `1 RflBde` | `l` | N | 3/58 |
| 2nd KRRC | `2 KRRC` | `l` | N | 3/59 |
| 76th Anti-tank Regt | `76` | `aa` | 8×2-pounders | 3/59 |
| 11th Royal Horse Arty | `11 RHA` | `x` | 6×25-pounders | 3/59 |
| 61st Light AA Regt | `61 LAA` | `ee` | 6×Light AA | 3/59 |

*(The 12th Lancers Bn IS seeded, as `12th Lancers [R]` under the engine's Corps Cavalry pool.)*

### 2nd Armored Division — p.117 — 7 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 3rd Armored Bde HQ | `3` | `d` | 1×Crusader Mk I | 1/15 |
| 2nd Support Group HQ | `2 Spt` | `a` | N | 1/15 |
| 1st Tower Hamlet Rifles | `1 THRf` | `l` | N | 1/15 |
| 1st Rangers | `1 Ranger` | `l` | N | 1/15 |
| 2nd Royal Horse Arty | `2 RHA` | `x` | 6×25-pounders | 1/15 |
| 102nd/NH Light Anti-Aircraft/Anti-Tank Regt | `102(NH)` | `bb` | 2×2-pounders, 2×Light AA | 1/15 |
| Kings Dragoon Guards | `KDGd` | `pp` | N | 1/15 |

> The engine's `102nd AT` (t43) is **not** this unit — the chart's own note b on the Unassigned
> Anti-tank sheet says the 102nd Anti-tank Regt (Northumberland Hussars) "is not the same unit as the
> 102(NH) Anti-tank/light anti-aircraft unit."

### 7th Armored Division — p.117 — 10 missing  ← **the single worst hole**
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 4th Armored Bde HQ | `4` | `b` | 1×Mark VI Light | D |
| 6th Royal Tank Regt | `6 RTR` | `g` | 10×Mark VI Lights | D |
| 7th Queens Own Hussars | `7 Hus` | `g` | 10×Mark VI Lights | D |
| 7th Armored Bde HQ | `7` | `d` | 1×A9 | D |
| 1st Royal Tank Regt | `1 RTR` | `g` | 7×A9 | D |
| 8th Hussars | `8 Hus` | `g` | 7×A10 | D |
| 7th Support Group HQ | `7 Spt` | `a` | N | D |
| 7th Motor Bde HQ | `7 Mtr` | `a` | N | 2/68 |
| 2nd Rifle Brigade | `2 RflBde` | `n` | N | D |
| 11th Hussars | `11 Hus` | `ll` | U@6 TOE | D |

**The Desert Rats have no tanks and no armoured cars in this engine.** The chart deploys the 7th
Armoured Division at `D` with two armoured brigades (4 tank regiments), a support group, and the
11th Hussars as divisional recon. The engine seeds only `HQ 7 Armd Div` plus three support-group
units (`3 RHA`, `1 KRRC`, `4 RHA`). Every tank regiment and both brigade HQs are absent from the
Commonwealth's *only* armoured formation present at the campaign start.

### 8th Armored Division — p.118 — 2 missing outright, 6 collapsed
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 7th Rifle Brigade | `7 RflBde` | `l` | N | 3/87 |
| 11th KRRC | `11 KRRC` | `l` | N | 1/88 |

Collapsed: `40 RTR`, `46 RTR`, `50 RTR` (each `g`, 1×Matilda 9×Valentine, 3/87) are represented by the
single seeded counter `23 Armd Bde`; `41 RTR`, `45 RTR`, `47 RTR` (each `g`, 1×Matilda 9×Valentine,
1/88) by the single seeded counter `24 Armd Bde`. Six charted counters → two seeded.

### 44th (Home Countries) Infantry Division — p.118 — 11 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 132nd Infantry Bde HQ | `132` | `a` | N | 2/90 |
| 4th Royal West Kents | `4 RWK` | `m` | N | 2/90 |
| 5th Royal West Kents | `5 RWK` | `m` | N | 2/90 |
| 2nd Buffs | `2 Buffs` | `m` | N | 2/90 |
| 133rd Infantry Bde HQ | `133` | `a` | N | 2/90 |
| 2nd Royal Sussex | `2 RSsx` | `m` | N | 2/90 |
| 4th Royal Sussex | `4 RSsx` | `m` | N | 2/90 |
| 5th Royal Sussex | `5 RSsx` | `m` | N | 2/90 |
| 6th Cheshire MG Bn | `6 Ches` | `u` | N | 2/90 |
| 44th Recce Regt | `44` | `ll` | N | 2/90 |
| 30th Light AA Regt | `30 LAA` | `ee` | 6×Light AA | 2/90 |

*Two of the division's three infantry brigades are entirely absent — this is the Alamein order of
battle.* (The engine's `44 RTR (Scorpion)` is the 1st Army Tank Brigade's 44th RTR refit, **not** the
44th Recce Regt.)

### 10th Armored Division — p.119 — 5 collapsed
`NottYeo` (9×Grant), `StffYeo` (8×Grant 2×Crusader Mk II), `SctsGry` (5×Grant 4×Stuart) — all `g`,
3/69 — are represented by the single seeded `8 Armd Bde`; `RWiYeo` (9×Grant) and `WkYeo` (9×Grant),
both `g`, 2/80, by the single seeded `9 Armd Bde`. Five charted counters → two seeded. This is the
Grant-equipped armour of Alam Halfa and Alamein.

### 1st Army Tank Brigade — p.119 — 1 missing + 2 mis-timed
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 8th Royal Tank Regt | `8 RTR` | `g` | 10×Matilda | 1/36 |

Mis-timed: the chart deploys `42 RTR` (10×Matilda) at **2/28** and `44 RTR` (10×Matilda) at **1/36**.
The engine seeds them only as `42 RTR (Scorpion)` / `44 RTR (Scorpion)` at **t99** — the Alamein
anti-mine refit (sheet note b). The base Matilda counters are absent for ~70 game-turns.

### 70th Infantry Division — p.120 — 3 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 14th Bde Anti-tank Coy | `14` | `dd` | 2×2-pounder | 1/47 |
| 16th Infantry Bde HQ | `16` | `c` | 3×3.7" Howitzer | D |
| 16th Bde Anti-tank Coy | `16` | `dd` | 2×2-pounder | 1/50 |

*The 16th Brigade's three battalions are on-map from turn 1 but their brigade HQ counter is not.*

### 22nd Guards Brigade (200th Guards Brigade) — p.121, prose sheet — 1 missing
The sheet states two counters are provided, `22 Gds` and `200 Gds`, `ID Code: a`. The engine seeds
only `HQ 22 Guards Bde`. The **`200 Gds`** counter (the January-1942 redesignation) is absent.

> **2026-08-04 flag — this is the one roster row whose arrival the book does not print.** Verified at
> 600 dpi: the sheet header reads `Basic Morale: None (that of attached units). ID Code: a`, and the
> prose reads "In January 1942, it became the 200th Guards Brigade" — a month, not an OpStage/GT.
> Every other row on the roster carries a printed `Arrives`. Seeding `200 Gds` therefore needs an
> owner ruling on the swap turn (or on modelling it as a rename of `22 Gds` rather than an arrival);
> it is the single entry that is not pure transcription. Same sheet, separate flag: it dates the
> 70th-Division attachment "February 1941 (2/21) until April 1941 (1/29)", where the 70th Division's
> own sheet (p.120, note b) prints "(2/20) through … (1/28)". The book disagrees with itself by one
> Game-Turn; neither is a roster row.

### Unassigned Anti-tank Regiments — p.121 — 1 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 84th Anti-tank Regt | `84` | `aa` | 8×6-pounder | 1/75 |

### Unassigned British Infantry-type Units — p.122 — 3 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 1st Buffs | `1 Buffs` | `p` | N | D |
| 1st Hampshire | `1 Hamp` | `p` | N | D |
| 1st South Staffordshires | `1 SoStff` | `p` | N | D |

### Unassigned Artillery Units — p.123 — 2 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 146th Field Artillery Regt | `146 Fld` | `x` | 6×25-pounder | 3/28 |
| 11th Royal Horse Arty Regt (Bishop refit counter) | `11 RHA` | `x` | 6×SP 25-pounder | 3/92 |

> The second is the sheet's note-b counter: "This unit is a refitted version of the 11 RHA assigned to
> the 1st Armored Division. It is not a unit per se." It is a physical counter the chart prints, and
> it is the engine's only route to self-propelled Bishops.

### Unassigned Anti-aircraft Units — p.124 — 2 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 27th Light AA Regt | `27 LAA` | `ee` | 6×Light AA | 3/28 |
| 37th Light AA Regt | `37 LAA` | `ee` | 6×Light AA | 2/30 |

### 6th Australian Division — p.124 — 9 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 16th Aus Infantry Bde HQ | `16 Aus` | `f` | N | D |
| 2/1 Aus Infantry Bn | `2/1 Aus` | `p` | N | D |
| 2/2 Aus Infantry Bn | `2/2 Aus` | `p` | N | D |
| 2/3 Aus Infantry Bn | `2/3 Aus` | `p` | N | D |
| 17th Aus Infantry Bde HQ | `17 Aus` | `e` | N | D |
| 2/5 Aus Infantry Bn | `2/5 Aus` | `p` | N | D |
| 2/6 Aus Infantry Bn | `2/6 Aus` | `p` | N | D |
| 2/7 Aus Infantry Bn | `2/7 Aus` | `p` | N | D |
| 6th Aus Div Cavalry Regt | `6 AusCav` | `ll` | N | D |

**Two of the division's three brigades, all six battalions, and its cavalry regiment are absent from
turn 1.** This is the infantry that took Bardia and Tobruk in Operation Compass.

### 9th Australian Division — p.125 — 4 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 2/7 Aus Field Artillery Regt | `2/7 AFld` | `x` | 6×25-pounder | 3/29 |
| 2/8 Aus Field Artillery Regt | `2/8 AFld` | `x` | 6×25-pounder | 3/29 |
| 2/12 Aus Field Arty Regt | `2/12 AFld` | `x` | 6×4.5" Howitzer | 3/29 |
| 2/3 Aus Light AA Regt | `2/3 LAA` | `ee` | 6×Light AA | 3/29 |

*The Tobruk garrison division has no divisional artillery in this engine.*

### 18th Australian Brigade — p.125 — 4 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 7th Aus Div Cavalry Regt | `7 AusCav` | `ll` | N | 3/14 |
| 2/1 Aus MG Bn | `2/1 Aus` | `u` | N | 3/14 |
| 2/1 Aus Anti-tank Regt | `2/1 Aus` | `aa` | 8×2-pounder | 3/14 |
| 2/3 Aus Field Artillery Regt | `2/3 AFld` | `x` | 6×25-pounder | 3/14 |

### 4th Indian Division — p.126 — 10 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 5th Indian Bde HQ | `5 In` | `a` | N | D |
| 1st Royal Fusiliers | `1 RFslr` | `p` | N | D |
| 3/1 Punjab Regt | `3/1 Pjb` | `p` | N | D |
| 4/6 Rajputana Rifles | `4/6 RajRf` | `p` | N | D |
| 11th Indian Bde HQ | `11 In` | `a` | N | D |
| 2nd Camerons | `2 Cmrn` | `p` | N | D |
| 1/6 Rajputana Rifles | `1/6 RajRf` | `p` | N | D |
| 4/7 Rajput Regt | `4/7 Rajpt` | `p` | N | D |
| Central India Horse | `1 CIH` | `ll` | N | D |
| 25th Field Artillery Regt | `25 Fld` | `x` | 6×3.7" Howitzer | D |

**Two of three brigades absent at turn 1.** Only the 7th Indian Bde (1/5) is seeded.

> `1 CIH` carries the standing owner ruling: its **row** prints ID `ll` (zoom-verified on p.126) while
> its **note c** says the trained unit converts to "a reconnaissance battalion, ID Code `kk` as
> listed." Row and note disagree; both are Recon Bn-Eq codes. Seed the row (`ll`) and flag.

### Unassigned Indian Units — p.127 — 2 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 2/5 Mahratta Light Inf | `2/5 Mah` | `p` | N | 3/29 |
| 13th DCO Lancers | `13 DCL` | `ll` | N | 1/86 |

### 2nd New Zealand Division — p.129 — 8 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 4th New Zealand Bde HQ | `4 NZ` | `a` | N | D |
| 18th NZ Bn | `18 NZ` | `m` | N | D |
| 19th NZ Bn | `19 NZ` | `m` | N | D |
| 20th NZ Bn | `20 NZ` | `m` | N | D |
| 28th Maori Inf Bn | `28 Mao` | `k` | U@2 | 1/35 |
| 27th New Zealand MG Bn | `27 NZ` | `u` | U@2 | D |
| 2nd New Zealand Cavalry | `2 NZ Cv` | `ll` | N | D |
| 4th NZ Field Artillery Regt | `4 NZ Fld` | `x` | 6×3.7" Howitzer | D |

*The entire 4th NZ Brigade, the divisional MG battalion, the cavalry and one artillery regiment are
absent from turn 1.* Note `28 Mao` is the only `k`-code counter on the whole Commonwealth chart
(CPA 10, CA 2/2, Max TOE **7** — the largest infantry TOE the chart grants).

### 1st Greek Infantry Brigade Group — p.132 — 1 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 1st Greek Field Arty Regt | `1 GrkFld` | `x` | 6×25-pounder | 1/93 |

### The Polish (Carpathian) Brigade — p.132 — 4 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| Kopanski MG Coy | `Kopnski` | `w` | U@1 | 3/1 |
| 1st Polish Cavalry Regt | `1 PolCv` | `ss` | N | 3/1 |
| 1st Polish Anti-tank Coy | `1 Pol` | `dd` | 1×2-pounder | 3/1 |
| 1st Polish Artillery Regt | `1 Pol` | `y` | 4×18-pounder | 3/1 |

*The engine seeds the Polish brigade as an HQ plus three anonymous rifle battalions; its MG company,
cavalry, anti-tank company and artillery — half the brigade's counters — are absent from turn 1.*

### Unassigned Allied Units — p.132 — 1 missing
| Unit | Ctr | ID | TOE | Arrives |
|---|---|---|---|---|
| 1st Company, Fr Mtr Marine | `"1"` | `v` | N | 3/65 |

*The only `v`-code counter (Infantry Company-Eq, CPA 10+, CA 1/1, Max TOE 1) on the chart.*

---

## 6. SHEETS THAT ARE COMPLETE — an honest negative

Sixteen of the 38 sheets reconcile with no missing counter. Naming them matters because it shows the
debt is concentrated, not uniform:

50th (Northumbrian) Inf Div (18/18) · 51st (Highland) Inf Div (20/20) · 22nd Armored Bde (4/4) ·
Unassigned Armor-Class Units (6/6) · 3rd Indian Motorized Bde Group (5/5) · 5th Indian Div (16/16) ·
10th Indian Div · 18th Indian Bde · 161st Indian Motor Bde · Unassigned New Zealand Units (2/2) ·
1st South African Inf Div (20/20) · Unassigned South Africa Units (3/3) · 2nd South African Inf Div
(20/20) · 1st Free French Bde (10/10) · 2nd Free French Bde (4/4) · Selby Force / Matruh Garrison.

**The pattern: the sheets that are complete are overwhelmingly the ones seeded from the campaign
reinforcement schedule; the sheets that are gutted are overwhelmingly the ones that arrive `D`
(Deployed at start) — the Sept-1940 / Operation-Compass order of battle.** 62 of the 91 missing
counters arrive by GT 30. The engine's Commonwealth is thin exactly where the campaign begins.

---

## 7. TRANSCRIPTION ERROR FOUND — `4.45a-oa-allied.md`

**Royal Yugoslav Guards, Unassigned British Infantry-type Units, p.122.**
The existing transcription records ID Code **`f`**. Re-rendered at `-r 600` and read
character-by-character, the book prints **`t`**.

This is not cosmetic: `f` is a *Headquarters* row (CPA 20, Anti-Armor 2, Vulnerability 1, CA 0/1,
Max TOE 1); `t` is an *Infantry Bn-Eq* row (CPA 10, CA 1/1, Max TOE 3). The unit is already seeded
(`Royal Yugoslav Guards`, infantry, t70), so no counter is missing — but the stat line implied by the
transcription is wrong. **`scratchpad/port/transcriptions/4.45a-oa-allied.md` line 512 should read
`| t |`.** (I am read-only on this pass and have not edited it.)

All other cells on the 13 pages re-rendered for this pass matched the transcription exactly.

> **2026-08-04 — CONFIRMED, and the fix is applied.** Re-rendered p.122 at 600 dpi and cropped to the
> row: the glyph has a crossbar and a curved foot and is unmistakably **`t`**, distinct from the
> plain-vertical `l` of `1 Frstrs` two rows above and from the top-hooked `f` printed on the 16th Aus
> Infantry Bde HQ row (p.124), which was rendered at the same magnification for comparison. The
> transcription now reads `| t |` with a dated comment.
>
> **The sweep for more of its kind found none.** Every one of the 91 missing counters' ID codes was
> re-read at 600 dpi on its own sheet. All 91 match §5 as written. The near-miss pairs were checked
> deliberately: `f` vs `t` (16 Aus is `f`, 17 Aus is `e`, RYugGd is `t`), `l` vs `1` (1 RflBde,
> 2 KRRC, 1 THRf, 1 Ranger, 7 RflBde, 11 KRRC all `l`), `ll` vs `kk` (1 CIH is `ll` — the row does
> **not** print the `kk` its note c says is "as listed", so the standing owner ruling holds), `m` vs
> `n` (2 RflBde is `n`; the 44th Div's six battalions and the three 4th NZ Bde battalions are `m`),
> `v` vs `y` (Fr Mtr Marine is `v`, 1st Polish Artillery is `y`), `k` vs `h`/`j` (28 Mao is `k`).

---

## 8. FIDELITY DEFECTS THAT ARE NOT MISSING COUNTERS

Found during the diff; each is a separate, smaller debt.

1. **Armoured brigades are aggregated.** `23 Armd Bde`, `24 Armd Bde`, `8 Armd Bde`, `9 Armd Bde` are
   each one seeded `tank` counter standing for three (or two) charted tank regiments; the 2nd Armoured
   Division's and 22nd Armoured Brigade's regiments are seeded as anonymous `… Regt I/II/III` slots.
   The chart gives each regiment its own counter, its own mixed tank TOE (e.g. `8×Grant, 2×Crusader
   Mk II`) and its own arrival. Aggregation erases both the per-regiment tank mix and the step count.

2. **Three brigade-group artillery regiments are seeded with the wrong role.** On the 10th Indian
   Division sheet the chart prints `97 Fld`, `157 Fld`, `164 Fld` (all ID `x`, 6×25-pounder) at L2
   under their brigade groups. The engine covers them with anonymous `20/21/25 In Bde Grp I/II/III`
   slots typed `infantry`. Three artillery regiments are being played as rifle battalions.

3. **Two more role mismatches.** `1st Bn de fusiliers` (`1 Fslrs`, ID `ff` = Light Anti-air Bn-Eq,
   4×Light AA) is seeded `infantry`; `23 NA Anti-tank Coy` (`23 NA`, ID `cc`, 3×2-pounder) is seeded
   `infantry`.

4. **Arrival-turn discrepancies against the chart.**
   - 22nd Armored Bde HQ + its three regiments: chart **3/20**, engine **t51** (verified on p.121).
   - 10th NZ RR Construction Coy: chart **1/32**, engine **t6**.
   - 13th NZ RR Construction Coy: chart **3/50**, engine **t6**.
   - 1st SA Road Construction Bn: chart **1/50**, engine **t6**.
   The three construction companies all arrive ~26-44 turns early, which matters because they are the
   only Commonwealth `uu` engineers in the game.

5. **Over-seeding.** The 161st Indian Motor Bde is seeded with three motor-infantry battalions where
   the chart prints two. The 10th Indian's 20th Bde Group is seeded with three where the chart prints
   two — the sheet's note b explains that brigade "is two battalions short on this Order at Arrival
   sheet" on purpose. Both cases invent force the chart does not print.

---

## 9. RECOMMENDED ORDER OF WORK

Ranked by campaign impact per counter seeded, not by count:

1. **7th Armored Division (10)** — the Commonwealth's only armour at start; currently an HQ with no tanks.
2. **6th Australian (9) + 4th Indian (10) + 2nd NZ (8)** — 27 counters, all `D`; this is the Operation
   Compass order of battle and it is more than half-absent.
3. **The armoured-brigade aggregation (11 regiments → 4 counters)** — de-aggregating restores the
   Grant/Crusader/Valentine mixes the chart prints.
4. **44th Infantry Division (11)** — two of three brigades; the Alamein order of battle.
5. **The 1st/2nd Armoured support groups and divisional AT/AA/artillery (12)**.
6. The long tail: Polish (4), 18th Australian (4), 9th Australian artillery (4), and the singletons.

Everything above is seedable directly from `[4.44B]` p.116-132 and `[4.46a]` p.133-134 with **no
invention required** — all 91 ID codes resolve to printed rows.

---

## 10. PROVENANCE

- Chart source: `tmp/The Campaign for North Africa.pdf`, PDF pages 116-132 (`[4.44B]`) and 133-134
  (`[4.46a]`), rendered with `pdftoppm -r 150` (and `-r 600` for the disputed Royal Yugoslav Guards
  cell) and read by eye.
- Roster source: `scratchpad/port/transcriptions/4.45a-oa-allied.md`, machine-parsed to 434 rows, then
  reconciled sheet-by-sheet against the engine by hand. 13 of its 17 pages independently re-verified
  here; one cell corrected (§7).
- Engine source: `data/reinforcements_campaign.json` (side ALLIED), `data/oob_italian.json`
  (`kind=="unit"`, side ALLIED), `data/oob_campaign_extra.json`, as folded by `game/oob.py::build`
  and dispatched by `game/scenario.py::campaign` (`scenario.py:1678`).
- This pass was read-only on `game/`, `data/` and `tests/`. Nothing was seeded.
