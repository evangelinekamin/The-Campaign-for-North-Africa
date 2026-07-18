# PHASE 3 — ORDER OF BATTLE: SCAN TRANSCRIPTION + GAP ANALYSIS

**Purpose.** Front-load the slow part of Phase 3 (the OOB) by transcribing the order-of-battle charts
directly from the 1979 scan (`tmp/The Campaign for North Africa.pdf`, no text layer) and diffing them
against what the engine currently seeds. This is a **transcription + gap document**, not an
implementation. Phase 3 proper consumes it and edits the JSON.

**Method / provenance.** Every rating below was **read off a rendered scan page with my own eyes**, not
from OCR, except where explicitly marked `(transcription only — scan-verify)`. The rulebook's printed
page number equals the PDF page index in the chart region (proven: the `<!-- page 107/108/109 -->`
markers in `docs/rules/90` line up with the audits' "PDF page 107/109" and the existing `p-107`/`p-109`
renders). So **"page N" below = PDF page N = rulebook page N.** Renders live in this session's
scratchpad (`oob_p138/139/140`, `uc_p133/134/136/137`, `setup_p78`, `summary_p73`, `pz3e_crop`,
`benghazi_crop`).

**Engine data model recap** (`data/unit_stats.json`): each nationality (`GE`/`CW`/`IT`) has ~9-10
**roles** (hq, infantry, motor_infantry, mg, tank, recon, artillery, antitank, oasis, +CW engineers);
each role names an ID-code `type` and default `cpa/oca/dca/steps/mobility`. A unit may name a **`model`**
that overrides combat ratings. `models` currently holds **24 entries**. Engine fields per model:
`oca` (offensive close assault), `dca` (defensive CA), `anti_armor`, `armor_protection`, `is_tank`,
`bar` (Breakdown Adj. Rating: signed, **+N = N cols RIGHT = more breakdown**, so chart `1R`→`+1`,
`2R`→`+2`, `1L`→`-1`, `0`→`0`), `barrage`, `vulnerability`. The chart's **CPA**, **AA (anti-air
rating)** and **Fuel Rate** columns are **not stored per model today** (CPA comes from the role; there is
no AA field and no per-model fuel field — see the AA-role gap, item 1.4, and T0-6).

---

# ITEM 1 — UNIT CHARACTERISTICS (the highest-value transcription)

## 1.0 Headline result

* **All 24 existing `models` entries were re-verified against the scan and are CORRECT.** No existing
  model needs a rating change. (This settles one OCR conflict: `docs/rules/90` has two copies of [4.47];
  they disagree on A9 Cruiser Armor Protection — copy-1 says `1`, copy-2 says `-`. **Scan = `1`.** The
  engine's `a9.armor_protection = 1` is right.)
* **22 of 32 Commonwealth weapon systems are absent** from `data/unit_stats.json` — confirmed
  cell-by-cell against [4.47]. Ratings for all 22 are given verbatim in §1.1.
* The three tank/gun charts are **[4.47] p.138 (CW), [4.48] p.139 (Italian), [4.49] p.140 (German)**.
* One source misprint found: the **Pz III E** row of [4.49] is typeset wrong in the book (duplicated
  `4/4`, shifted columns) — flagged UNVERIFIED in §1.3.

## 1.1 [4.47] COMMONWEALTH TANK & GUN CHARACTERISTICS CHART — verbatim from scan (PDF p.138)

Columns as printed: **Type | CPA | AA | Barrage | Anti-Armor | Vul | Armor Prtctn | Close Assault
Off/Def | Fuel Rate | BAR\***. `-` = not applicable/zero. `( )` = may not use if ammo-bearing units share
the hex.

| Type | CPA | AA | Barr | AntiArm | Vul | Armor | CA Off/Def | Fuel | BAR | engine model key | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A9 Cruiser | 25 | 1 | - | 3 | - | **1** | 3/3 | 2 | 1R | `a9` | ✅ seeded, correct |
| **A10 Cruiser** | 15 | 1 | - | 3 | - | 2 | 3/3 | 2 | 1R | `a10` | **MISSING** — equips 8 Hussars @GT1 |
| A13 Cruiser | 30 | 0 | - | 3 | - | 2 | 2/3 | 2 | 1R | `a13` | ✅ seeded, correct |
| **Churchill II** | 15 | 1 | - | 6 | - | 7 | 5/6 | 7 | 0 | `churchill` | **MISSING** — GT90 |
| **Crusader Mk.I** | 25 | 1 | - | 3 | - | 3 | 3/4 | 3 | 1R | `crusader1` | **MISSING** — GT31 |
| Crusader Mk.II | 25 | 1 | - | 3 | - | 4 | 4/4 | 3 | 1R | `crusader2` | ✅ seeded, correct |
| **Crusader Mk.III** | 25 | 1 | - | 6 | - | 4 | 4/5 | 3 | 1R | `crusader3` | **MISSING** — GT88 |
| Grant M3\* | 20 | 1 | - | 7 | - | 4 | 6/5 | 7 | 0 | `grant` | ✅ seeded, correct |
| Mark VI Light | 35 | 1 | - | 0 | - | 1 | 2/2 | 1 | 0 | `mk6` | ✅ seeded, correct |
| Matilda Mk.II | 15 | 0 | - | 3 | - | 6 | 3/4 | 3 | 1R | `matilda2` | ✅ seeded, correct |
| **Sherman\*** | 20 | 1 | - | 6 | - | 6 | 5/5 | 6 | 0 | `sherman` | **MISSING — the big one, GT89** |
| Stuart M3\* | 35 | 1 | - | 4 | - | 3 | 4/4 | 4 | 0 | `stuart` | ✅ seeded, correct |
| **Valentine Mk.II** | 15 | 0 | - | 3 | - | 5 | 3/4 | 3 | 0 | `valentine` | **MISSING** — GT39 |
| **Scorpion†** | 25 | 0 | - | 0 | - | 7 | 0/(2) | 3 | 1L | `scorpion` | **MISSING — mine-clearer; no minefield clearing without it** |
| **18-pounder Gun** | 15 | - | 7 | (2) | 4 | - | 0/1 | 1 | - | `18pdr` | **MISSING** |
| **18/25-pounder Gun** | 15 | - | 8 | 2 | 5 | - | 1/1 | 1 | - | `18_25pdr` | **MISSING** |
| 25-pounder Gun | 15 | - | 8 | 5 | 6 | - | 1/1 | 1 | - | `25pdr` | ✅ seeded, correct |
| **4.5" Gun** | 15 | - | 11 | 1 | 9 | - | 1/0 | 1 | - | `4_5in_gun` | **MISSING** |
| **5.5" Gun/Howitzer** | 15 | - | 15 | 1 | 7 | - | 1/0 | 1 | - | `5_5in` | **MISSING** — medium regt fires as 25pdr today |
| **60-pounder Gun** | 15 | - | 12 | 1 | 7 | - | 1/0 | 1 | - | `60pdr` | **MISSING** |
| **SP 25-pounder Gun‡** (Bishop) | 15 | - | 8 | 4 | 3 | 5 | 2/1 | 3 | 2R | `bishop` | **MISSING** — SP arty, armor 5 |
| **3.7" Howitzer** | 15 | - | 7 | 0 | 3 | - | 0/0 | 1 | - | `3_7in_how` | **MISSING** |
| **4.5" Howitzer** | 15 | - | 9 | 0 | 3 | - | 1/0 | 1 | - | `4_5in_how` | **MISSING** |
| **6" Howitzer** | 15 | - | 15 | 1 | 5 | - | 1/0 | 1 | - | `6in_how` | **MISSING** |
| **155mm Howitzer** | 15 | - | 15 | 1 | 6 | - | 1/0 | 1 | - | `155mm_how` | **MISSING** |
| **105mm SP Howitzer‡** (Priest) | 20 | 1 | 9 | 2 | 4 | 4 | 2/3 | 3 | 0 | `priest` | **MISSING** — SP arty, armor 4, AA 1 |
| **2-pounder** | 15 | - | - | 4 | 2 | - | 1/1 | 1 | - | `2pdr` | ✅ seeded, correct |
| **6-pounder** | 15 | - | - | 7 | 2 | - | 1/1 | 1 | - | `6pdr` | ✅ seeded, correct |
| **17-pounder** | 15 | - | - | 13 | 2 | - | 1/1 | 1 | - | `17pdr` | **MISSING** — GT103, anti_armor 13 |
| **SP 6-pounder‡** (Deacon) | 20 | - | - | 7 | 2 | 1 | 2/2 | 1 | 1L | `deacon` | **MISSING** — SP AT, armor 1 |
| **Light AA (Bofors 40mm)** | 15 | 1 | - | (1) | 2 | - | (1)/(1) | 1 | - | `light_aa` | **MISSING — needs AA role** |
| **Heavy AA (3.7")** | 15 | 4 | - | (7) | 2 | - | (1)/(1) | 1 | - | `heavy_aa` | **MISSING — needs AA role** |

Footnotes as printed: `*` US tank (affects only how many TOE a CW tank bn-eq may hold — US tanks cap at
**9**, see [4.46a] `g` code note †). `†` Scorpion = mineclearing tank on a Valentine chassis, treated as
an **engineer** unit for entering/clearing minefields (§26); arrives as the complement of two tank
battalions returning Oct 1942, **not via production**. `‡` SP 25-pdr = "Bishop"; 105mm SP How = "Priest";
SP 6-pdr = "Deacon".

## 1.2 [4.48] ITALIAN TANK & GUN CHARACTERISTICS CHART — verbatim from scan (PDF p.139)

Columns: **Type | CPA | AA | Barrage | Anti-Armor | Vul | Armor Prtctn | Off/Def | Fuel Rate | BAR**.

| Type | CPA | AA | Barr | AntiArm | Vul | Armor | Off/Def | Fuel | BAR | engine model | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CV 33 (L3/35) | 25 | 0 | - | 0 | - | 1 | 1/2 | 1 | 2R | `cv33` | ✅ seeded, correct |
| L 6/40 | 25 | 0 | - | 1 | - | 2 | 2/2 | 2 | 0 | `l6` | ✅ seeded, correct |
| M 11/39 | 20 | 1 | - | 2 | - | 2 | 3/3 | 2 | 1R | `m11_39` | ✅ seeded, correct |
| M 13/40 | 20 | 1 | - | 3 | - | 3 | 3/3 | 2 | 1R | `m13` | ✅ seeded, correct |
| **M 14/41** | 20 | 1 | - | 3 | - | 3 | 3/3 | 2 | 0 | `m14_41` | **MISSING** — Ariete/Littorio late tank (as m13 but BAR 0) |
| **65/17 Gun** | 15 | - | 5 | 0 | 3 | - | 1/1 | 1 | - | `65_17` | MISSING (Tobruk CD arty) |
| **75/18 Gun-Howitzer** | 15 | - | 6 | 0 | 5 | - | 1/0 | 1 | - | `75_18_gh` | MISSING |
| **75/18 Gun\*** (Semovente SP) | 20 | - | 6 | 6 | 4 | 3 | 3/3 | 2 | 1R | `semovente_75_18` | **MISSING — "one of the best weapons the Italians had"; SP AT, armor 3** |
| **75/27 Gun** | 15 | - | 6 | 2\*\* | 4 | - | 1/1 | 1 | - | `75_27` | MISSING (\*\* anti-armor 0 until GT63) |
| **100/17 Howitzer** | 15 | - | 8 | 0 | 5 | - | 1/0 | 1 | - | `100_17` | MISSING |
| **105/28 Gun** | 15 | - | 9 | 1 | 7 | - | 1/1 | 1 | - | `105_28` | MISSING |
| **149/13 Howitzer** | 15 | - | 15 | 0 | 5 | - | 1/0 | 1 | - | `149_13` | MISSING |
| **ParaArt\*\*\*** | 15 | - | 2 | 2 | 1 | - | 1/1 | 1 | - | `para_art` | MISSING (Folgore, GT94; only airdroppable IT gun) |
| **149mm Vichy French** | 15 | - | 10 | 1 | 5 | - | 0/1 | 1 | - | `149_vichy` | MISSING |
| **155mm Rimhailo (Fr.)** | 15 | - | 13 | 0 | 3 | - | 0/0 | 1 | - | `155_rimhailo` | MISSING |
| **47/32 Mod. 37** (AT) | 15 | - | - | 4 | 2 | - | 1/1 | 1 | - | `47_32` | MISSING (Italian AT gun) |
| **Light (20mm M/35 Breda)** AA | 15 | 1 | - | 2 | 2 | - | (1)/(1) | 1 | - | `it_light_aa` | MISSING — needs AA role |
| **"I" Light** AA (0+CPA) | 0+ | 1 | - | 2 | 2 | - | (1)/(1) | 1 | - | `it_light_aa_emplaced` | MISSING — emplaced, Tobruk/Benghazi/Benina |
| **Heavy (75/46 Mod.34)** AA | 15 | 2 | - | (5) | 2 | - | (1)/(1) | 1 | - | `it_heavy_aa` | MISSING — needs AA role |
| **"I" Heavy** AA (0+CPA) | 0+ | 2 | - | (5) | 2 | - | (1)/(1) | 0 | - | `it_heavy_aa_emplaced` | MISSING — emplaced |
| **Heavy (90/53)** AA | 15 | 3 | - | 9 | 2 | - | (1)/(1) | 1 | - | `it_90_53` | MISSING — anti_armor 9 (the Italian "88") |

Note (`****`): `0+` CPA AA points are without organic transport (not in bunkers); may be motorized, but
those in the **Tobruk 1st–5th CD Artillery Groups are immobile**. The only `0+` CPA points in the whole
game deploy at **Tobruk, Benghazi and Benina**.

## 1.3 [4.49] GERMAN TANK & GUN CHARACTERISTICS CHART — verbatim from scan (PDF p.140)

Columns: **Type | CPA | AA | Barrage | Anti-Armor | Vul | Armor Prtctn | Off/Def | Fuel Rate | BAR\***.
`*` All German **tanks** carry BAR **1R until GT 1/31**, then 0 (a turn-gate; the engine stores `bar:0`
and honours the +1 in the reader — keep that).

| Type | CPA | AA | Barr | AntiArm | Vul | Armor | Off/Def | Fuel | BAR | engine model | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **PZ I** | 24 | 1 | - | 0 | - | 1 | 2/2 | 2 | 0 | `pz1` | MISSING (early DAK) |
| Pz II | 35 | 0 | - | 1 | - | 2 | 2/3 | 2 | 0 | `pz2` | ✅ seeded, correct |
| **Pz III E** | 25 | 1 | - | 4 | **?3** | **?4** | **?4/4** | **?3** | **?3** | `pz3e` | ⚠️ **SOURCE MISPRINT — UNVERIFIED, see below** |
| Pz III H | 25 | 1 | - | 4 | - | 4 | 4/4 | 3 | 0 | `pz3h` | ✅ seeded, correct |
| Pz III J (Special) | 26 | 1 | - | 6 | - | 4 | 7/5 | 3 | 0 | `pz3j` | ✅ seeded, correct |
| Pz IV D | 25 | 1 | - | 6 | - | 3 | 5/4 | 4 | 0 | `pz4d` | ✅ seeded, correct |
| **Pz IV E** | 25 | 1 | - | 6 | - | 3 | 5/5 | 4 | 0 | `pz4e` | MISSING (as pz4d but Off/Def 5/5) |
| Pz IV F2 (Special) | 25 | 1 | - | 8 | - | 4 | 6/5 | 4 | 0 | `pz4f2` | ✅ seeded, correct |
| **7.5cm IG18 Lt Inf Gun** | 15 | - | 6 | 3\*\* | 2 | - | 1/1 | 1 | - | `de_75_ig18` | MISSING (\*\* anti-armor 0 until GT63; air-droppable) |
| **10.5cm K18 Med Gun** | 15 | - | 9 | 1 | 9 | - | 1/1 | 1 | - | `de_105_k18` | MISSING |
| 10.5cm leFH18 Lt Fld How | 15 | - | 9 | 2 | 5 | - | 1/1 | 1 | - | `lefh18` | ✅ seeded, correct |
| **10.5cm SP K18 Gun** | 15 | - | 9 | 2 | 4 | 2 | 2/2 | 2 | 0 | `de_105_sp_k18` | MISSING (SP, armor 2) |
| **149mm Vichy French** | 15 | - | 10 | 1 | 5 | - | 0/1 | 1 | - | `de_149_vichy` | MISSING |
| **15cm sIG33 Med Inf Gun** | 15 | - | 14 | 1 | 2 | - | 1/1 | 1 | - | `de_150_sig33` | MISSING |
| 15cm sFH18 Med Fld How | 15 | - | 15 | 1 | 7 | - | 0/1 | 1 | - | `sfh18` | ✅ seeded, correct |
| **15cm K18 Gun** | 15 | - | 15 | 1 | 11 | - | 1/1 | 1 | - | `de_150_k18` | MISSING |
| **15cm SP Gun** | 25 | - | 14 | 1 | 2 | 2 | 2/2 | 2 | 0 | `de_150_sp` | MISSING (SP) |
| **155mm (french 1915)** | 15 | - | 13 | 0 | 5 | - | 1/1 | 1 | - | `de_155_fr` | MISSING |
| **17cm K18 Gun** | 15 | - | 15 | 0 | 13 | - | 1/0 | 1 | - | `de_170_k18` | MISSING |
| **21cm mrs18 Howitzer** | 15 | - | 18 | 0 | 8 | - | 1/0 | 1 | - | `de_210_mrs18` | MISSING (barrage 18, the heaviest) |
| **2.8cm sPzB.41 / 28/20 Pak** | 15 | - | - | 4 | 2 | - | 1/1 | 1 | - | `de_28_pak` | MISSING (air-droppable AT) |
| 3.7cm Pak 35/36 | 15 | - | - | 2 | 1 | - | 1/1 | 1 | - | `pak36` | ✅ seeded, correct |
| 5cm Pak 38 | 15 | - | - | 5 | 2 | - | 1/1 | 1 | - | `pak38` | ✅ seeded, correct |
| **7.62cm Pak(R)\*\*\*** | 15 | - | - | 9 | 2 | - | 1/1 | 1 | - | `de_762_pakr` | MISSING (captured Russian AT, anti_armor 9) |
| **Pzjg 1 (SP)\*\*\*\*** | 30 | - | - | 4 | 2 | 1 | 2/2 | 1 | 0 | `pzjg1` | MISSING (SP AT, armor 1) |
| **Marder III (SP)** | 15 | - | - | 9 | 2 | 2 | 3/2 | 2 | 0 | `marder3` | MISSING (SP AT, anti_armor 9, armor 2; ~GT63) |
| **Light (20mm & 37mm Flak)** | 15 | 1 | - | (1) | (1) | - | (1)/(1) | 1 | - | `de_light_flak` | MISSING — needs AA role |
| Heavy (88mm Flak) | 15 | 3 | - | 13 | 2 | - | 2/1 | 1 | - | `flak88` | ✅ seeded, correct |

**⚠️ Pz III E is misprinted in the source (UNVERIFIED — do NOT seed a rating silently).** Read at 400 dpi
(`pz3e_crop`), the row prints, positionally: CPA 25, AA 1, Barrage –, Anti-Armor 4, and then a garbled
tail — a **duplicated `4/4`** (appearing under both Armor Prtctn and Fuel Rate) with single `3`s under
Vul, Off/Def and BAR. The adjacent, near-identical **Pz III H** is clean: AntiArm 4, Vul –, Armor 4,
Off/Def 4/4, Fuel 3, BAR 0. **Best inference for Pz III E:** AntiArm 4, Armor 4, Off/Def 4/4, Fuel 3,
with Vul 3 and BAR 3 (an early, less-reliable model) — but this is a **judgement call on a broken
print**. Recommend a second human render + ruling before seeding; the engine has no `pz3e` today, so
nothing regresses by leaving it out until ruled. (Pz III E likely arrives with 5 Le Div ~GT21-26.)

## 1.4 [4.46a-c] UNIT (ROLE) CHARACTERISTICS — engine role stats verified against the scan

These charts give the **ID-code / role** stats (CPA, CA Off/Def, Max TOE) the OA charts reference by
letter `a`…`uu`. I read **[4.46a] CW (p.133-134)** and **[4.46c] German (p.137)** directly; **[4.46b]
Italian (p.135-136)** is rendered (`uc_p136`) but transcribed here from `docs/rules/90` — **scan-verify
before trusting the Italian role numbers.**

**Commonwealth [4.46a] role verification** (engine `type` → chart code → verdict):

| engine role | type | chart code | chart CPA / Off-Def / MaxTOE | verdict |
|---|---|---|---|---|
| hq | a | a | 30 / – / – | ✅ |
| infantry | p | p | 10 / 1/2 / 6 | ✅ (oca1 dca2 steps6) |
| motor_infantry | l | l | 10+ / 2/2 / 6 | ✅ |
| **mg** | u | u | **8** / 4/6 / 3 | ⚠️ engine `cpa:20` — **chart code u is CPA 8** (oca/dca/steps match). Flag. |
| tank | g | g | 25 / – / **10†** (9 if US) | ✅ (engine steps 8 = arrival; role max should be 10) |
| recon | pp | pp | 45 / 2/3 / 6 | ✅ |
| artillery | x | x | 20 / – / 6 | ✅ (barrage from the gun model) |
| antitank | aa | aa | 15 / – / 8 | ✅ |
| — (**no AA role**) | — | ee/ff/gg | Light AA 6/4, Heavy AA 2 | ❌ **CW AA battalions have NO engine role** (T0-6) |

Other CW codes worth carrying for the OA gap-fill: `g`=Tank Bn-Eq (max 10†); `x`=Arty Bn-Eq (max 6);
`z`=AT Bn-Eq (8 AT + 3 arty, max 11); `hh/jj/kk/ll`=recon max 8; `tt`=recon CPA 35 4/4 max 3;
`uu`=Construction Road/RR CPA 25, 0/(1), max (1).

**German [4.46c] role verification** — engine roles match the chart well:

| engine role | type | chart code | chart CPA / Off-Def / MaxTOE | verdict |
|---|---|---|---|---|
| hq | a | a | 60 / – / – | ✅ |
| oasis | r | r | 25 / 1/1 / 1 (Inf Coy-Eq) | ✅ |
| infantry | g | g | 25 / 3/2 / 7 | ✅ |
| motor_infantry | j | j | 10+ / 2/2 / 7 (AntiArm 1, Armor 1) | ✅ |
| mg | mg | (n or q) | 8+ / 4/6 / 9 or 4 | ⚠️ no exact code `mg`; engine cpa 10 vs chart 8+; oca/dca 4/6 match |
| tank | f | f | 25 / – / **15** | ✅ (German tank bn max **15**, vs CW 10) |
| recon | ee | ee | 45 / 3/3 / 8 (AntiArm 1, Armor 2) | ✅ |
| artillery | u | u | 20 / – / 6 | ✅ |
| antitank | x | x | 20 / – / 8 | ✅ |

German AA codes for gap-fill: `z/aa/bb`=Light AA (max 6/12/6), `cc/dd`=Heavy AA (max 4/2), `gg`=Engineer
Bn/Coy-Eq (CPA 25, 0/(1), max (1)).

**Italian [4.46b]** *(transcription only — scan-verify from `uc_p136`)*: HQ codes `a`=45, `b`=30; the
engine's `IT.hq` uses `type:"a"` but `cpa:30` — that matches **code b (30)**, not code a (45). Flag the
Italian role→code mapping for a pass: `k/l`=Tank Bn-Eq CPA 30 (max 9); `m`=Inf Bde-Eq CPA 10, 1/1,
max 10; `jj/kk/ll/mm`=Arty Bn-Eq; `qq/rr`=AT; `ss/tt/uu`=AA Bn/Coy-Eq; `pp`=emplaced guns CPA 0 + up to
8 AA (the Tobruk/Benghazi/Benina immobile CD arty); `vv/ww`=recce (Autoblinda 41/40, BAR 1L).

---

# ITEM 2 — THE GAP LIST vs WHAT IS SEEDED

Cross-read of `data/unit_stats.json`, `oob_italian.json`, `oob_desert_fox.json`,
`oob_campaign_extra.json`, `reinforcements_campaign*.json`, and `game/oob.py::classify()`.

## 2.1 Missing weapon-system models (the 22 CW + the Axis set)

* **Commonwealth: 22 missing** — all listed with ratings in §1.1. Priority order for balance:
  **Sherman (GT89), Grant is present**, Crusader I/III, A10, Valentine, Churchill; then the gun park
  (5.5"/60-pdr/6"/155mm — today every CW medium regiment fires as a 25-pdr because `MODEL_DEFAULTS`
  forces `25pdr`); then Bishop/Priest/Deacon (SP); then 17-pdr; then **Scorpion** (without it the
  campaign has **no mine-clearing capability at all**); then **both AA rows** (blocked on the AA role).
* **Axis: ~12 German + ~17 Italian missing** — listed in §1.2/§1.3. Highest-value: **Semovente 75/18**
  (Italian SP AT), **M14/41**, **Marder III** (German SP AT ~GT63), the emplaced Italian CD/AA guns for
  the Tobruk/Benghazi/Benina garrisons, and the German medium/heavy artillery park (17cm, 21cm, 15cm).
  Most Axis *infantry/AT* is already covered by role-level proxies, so the Axis model gap is less
  balance-critical than the CW one.

## 2.2 The AA role does not exist (rule 3.23) — T0-6 / 3.1

`classify()` emits only **8 roles**: hq, mg, antitank, artillery, oasis, infantry, motor_infantry, tank.
**No AA role**, and it **never emits recon / rr_engineer / road_engineer** (those reach the engine only
through files that set `role` explicitly). Consequences confirmed in the built state: CW `9 HAA`,
`15 LAA`, `57 LAA` fall through to plain infantry; German Flak Bns are typed `antitank`. Phase 3.1 must
add an `aa` role + set `is_pure_aa`, and classify on the **counter**, not the group substring (the
`"Tank" in "Anti-Tank"` bug — T0-6). **This must ship WITH the model/gap-fill, never alone** (fixing
classify() alone strips the CW of 5 phantom tanks and gives nothing back).

## 2.3 Brigade → HQ + 3 battalions (rule 20.11)

Every Commonwealth infantry/motor **brigade is one 6-TOE counter**; none is modelled as HQ + three
battalions. The reinforcement data has **no CW unit pre-split** into I/II/III (contrast the Italian
`I/157`, `IX(L)` etc. which are pre-split in `oob_campaign_extra`). Rule 20.11's own example — *"the 6th
NZ Brigade (and its three battalions)"* — is `6 NZ Bde` in the data, a single counter. **~34-36 CW
brigades need splitting**; shortfall ≈ 432 TOE. This is the biggest single TOE gap after the missing
reinforcements.

## 2.4 Counters / reinforcements — measured seeded totals

| file | records | notes |
|---|---|---|
| `oob_italian.json` | 100 unit + 10 dump | **raw VASSAL extraction, NO role/model** — relies on `classify()`. Both sides live here (Axis 66 / Allied 36 / 8 air `?`). |
| `oob_desert_fox.json` | 28 unit + 10 dump + 3 feature | Rommel's-Arrival setup; German units only on the Axis side (Italian lives in oob_italian). Carries **300th Oasis Bn** (2/300,1/300,3/300) as *setup*, not campaign. |
| `oob_campaign_extra.json` | 35 unit (all AXIS/IT) | hand-authored gap-fill; **carries role+model**; 63 Cirene, 62 Marmarica (reconstructed), the 10-unit Libyan Tank Command (cv33×8, m11_39×2), and the **Derna/Bardia/Bir-Scheferzen garrisons**. |
| `reinforcements_campaign.json` | **179** (ALLIED 91 / AXIS 88) | keyed to **Game-Turn only — OpStage discarded**; GT1→GT97; **zero withdrawal events**. |
| `reinforcements_campaign_source.json` | 176 (CW 88 / GE 39 / IT 49 = **88 CW / 88 Axis**) | **NOT Axis-only** — the plan/audit's "Axis-only, no CW provenance" claim is WRONG; both sides have provenance here. |

Against [4.43a]/[4.44B] the plan measures **274 of 365 CW reinforcement counters** and **43 of 66 CW
initial counters** missing, CW loaded at **32% of its own chart**. The specific absent hardware
(confirmed by name-search): **Sherman, Valentine, Churchill, 17-pdr, Priest/Bishop/Deacon, Scorpion,
Ramcke Bde, Sonderverband 288, 1 RTR, 22 Armoured Bde, and all dedicated CW LAA/HAA reinforcements**
(the only LAA/HAA counters anywhere are 3 in the 1940 `oob_italian` setup).

## 2.5 Named Axis gap-fill items (rule cites)

* **Ramcke Brigade** — 0 hits anywhere. 6 counters, Basic Morale **+2**, airdroppable, **GT86-93 (into
  the Alamein window)**.
* **Sonderverband 288** — absent.
* **300th Oasis Battalion** — present only in `oob_desert_fox` setup (13 companies); **not in the
  campaign reinforcements**; `oob.py` has an unused `oasis` role ready for it.
* **8 of 9 unassigned Italian armoured battalions** (~53 tank TOE) — the Libyan Tank Command in
  `oob_campaign_extra` covers 10 tank counters, but the plan flags 8 non-divisional armoured bns still
  missing; cross-check against [4.44b] Italian OA (`docs/rules/90:3817`, PDF ~p.142+).
* **German non-divisional artillery (19 counters)**, **22 unassigned Flak battalions**, **21 Pz Div HQ**
  (the 5 Le → 21 Pz reorganisation) — absent.
* **Withdrawals: 0 of 32** (rule 20.8) and **OpStage precision lost** — see item 4.

---

# ITEM 3 — THE AXIS GARRISON HEXES [60.31] (pure data, ~90% of the GT1 score)

**Source: [60.31] Italian Initial Deployment, read directly off the scan, PDF p.78 (`setup_p78`,
`benghazi_crop`).** Every hex below is verbatim from the scan. `data/oob_italian.json` is a raw VASSAL
extraction whose counters were fanned along a diagonal for legibility, so the garrisons of the biggest
victory cities **do not stand in the correct hexes**.

## 3.1 The canonical [60.31] hexes vs what is seeded

| Garrison | [60.31] scan hex | VP (64.73) | currently seeded at | delta | fix |
|---|---|---|---|---|---|
| **Tobruk Garrison** (+ HQ Libyan Tank Command) | **C4807** | 200 Axis | C4410, C4511, C4611, C4811 (`oob_italian`) | **3-4 hexes SW** | move to C4807 |
| **Bardia Garrison** (+ Trivoli Regt) | **C4321** | 100 Axis | C4220 (`oob_campaign_extra`, labelled "Barka") | **1 hex off; wrong file** | move to C4321; put in main OOB |
| **Benghazi Garrison** | **B4827** *(see 3.2 conflict)* | 75 Axis | A4926 (`oob_italian`) | **victory hex empty** | move onto the victory hex |
| **Derna Garrison** | **B5925** | 25 Axis | B5925 (`oob_campaign_extra`) | ✅ correct | — |
| **Benina Garrison** | **A4829** | (airfield) | A4829 (`oob_italian`) | ✅ correct | — |
| **Giaribub Garrison** (6 counters) | **C1014** | 15 Axis | C1014 (`oob_italian`) | ✅ correct | — |
| **Mechili Garrison** | **B4921** | — | B4921 (`oob_italian`) | ✅ correct | — |
| Bir Scheferzen Garrison | C3419 | — | C3419 (`oob_campaign_extra`) | ✅ correct | — |
| Fort Maddelena Garrison | C3019 | — | (verify) | — | check |
| el Grein Garrison | C1715 | — | (verify) | — | check |
| Soluch Garrison (+ X Cp) | A4130 | — | A4130 (`oob_italian`) | ✅ correct | — |

**The two hexes that matter for the score are Tobruk (C4807) and Benghazi (its victory hex).** Bardia
is also victory-bearing (100 VP). Fixing these three is the "90% of the final score" data change the
plan cites — and it is pure data, no engine change.

## 3.2 ⚠️ BENGHAZI HEX CONFLICT — an internal source inconsistency, rule on it

The 1979 book prints **two different hexes for Benghazi**, and both are faithful scans (this is a 54.17-
class errata, not an OCR error):

* **[60.31] Italian Deployment (PDF p.78, `benghazi_crop`): Benghazi = `B4827`.** Neighbours in the same
  chart — Barce `B5504`, Derna `B5925`, Mechili `B4921` — are all section **B**.
* **Summary of Important Locations (PDF p.73, `summary_p73`): Benghazi = `A4827`.** This is what
  `data/victory_cities.json` uses (`A4827`, 75/100 VP). **Benina = `A4829` in BOTH charts.**

Geographic reasoning favours **A4827**: Benina (A4829) is Benghazi's own airfield, immediately adjacent,
and both charts agree Benina is section A — so Benghazi two rows away at A4827 (same section) is the
consistent reading, and A4827 is already a valid hex in the engine's coordinate map. **Recommendation:
seed the Benghazi garrison on the SAME hex the victory test uses (`A4827` today) so Benghazi is not empty
for scoring — the invariant that matters is garrison-hex == victory-hex, whatever value is chosen.** Flag
`_errata_benghazi_hex` (A4827 vs B4827) for the owner to rule, exactly like the 54.17 demolition errata.
`oob_italian` currently seeds the garrison at `A4926` — one column/hex off `A4827` either way.

## 3.3 Full [60.31] Italian setup (for the Axis gap-fill, item 3.5) — from scan p.78

Field formations (hex : formation): C4218 1 CCNN Div · C4120 63 Cirene Div · C4020 1 Libyan Div ·
C3920 2 Libyan Div · C3919 Aresca Regt (Tank; LTC) · C3918 62 Marmarica Div · C3617 Maletti Div ·
C4707 64 Catanzaro Div · C4507 4 CCNN Div. Garrisons per §3.1. Free-placement: Barce (B5504) Libyan
Parachute Regt; "Anywhere in Libya" 1/1AR…4/1AR + XXI/XXVI Cp; "Within 3 hexes of C0716" Saharan Det;
"Anywhere Map A/B" XVIII Lib, XXX-II Lib + 147/131/2-24/5-1/6 GaF/16 GaF/22 GaF/42 GaF/350 GaF (all Ar);
**Tripoli (off-map): 2 CCNN Div, 3 CCNN Div, XXII/XXIII Cp**; Tripolitania 4/10 Army. Plus 2 TOE of
Autoblinda 40 (recce, code "WW") free-attach or as Tobruk replacements.

`classify()` morale note (`oob.py`): Libyan −2, Maletti −2, CCNN 0, Rommel/DAK +1; the **3rd CCNN**
needs its own key if it enters.

---

# ITEM 4 — THE REINFORCEMENT SCHEDULE

## 4.1 [4.43a] COMMONWEALTH LAND UNIT REINFORCEMENT & WITHDRAWAL SCHEDULE — scan PDF **p.114-116**

*(Rendered/legible; transcribed here from `docs/rules/90:1781-1916`, which tracks the scan. Full verbatim
transcription of all 365 counters is the body of Phase 3.3 — this section fixes the structure, the entry
rule, and the specific missing high-value rows.)*

**Structural gaps the seeded data has (all confirmed):**

1. **OpStage is in the chart and dropped in the data.** The chart key is **GT/OpStage** (e.g. `1 3` =
   GT1 OpStage 3; `9 2`; `15 1`). `reinforcements_campaign.json` stores **`arrival_turn` only**. Rule
   20.11 pins arrivals to a specific OpStage; restore it.
2. **Entry hex.** The chart footnote: *"Reinforcements arrive in any hex(es) of **Cairo** unless
   specifically indicated otherwise. A Returning unit may be placed in Alexandria or Cairo."* A handful
   are exceptions (e.g. GT19/2 `"A" SpecSrvc in Alexandria`). The seeded records carry axial-pair hexes
   that should be reconciled to the Cairo hexes (`E1730/1829/1830/1930/1931`).
3. **Withdrawals: 0 of ~32.** [4.43a] lists `WD:` events throughout (e.g. GT13/3 WD 5 In Bde[4 In];
   GT15/1 WD 7 In Bde; GT16/1 WD 4 In Div; GT23/3 WD 1 Armd Bde; GT26/1 WD 16 Aus Bde; …; GT97/2 WD
   22/200 Guards Bde). Rule 20.8 makes them mandatory; the data has none. These are a **CW VP source via
   64.75** and a force-level check — must be transcribed with their `Tpt:` (transport) values.
4. **`Rtn:` (returns)** are also listed (e.g. GT28/1 Rtn 4 In Div; GT31/1 Rtn 6 NZ Bde; GT99/1 Rtn 42 &
   44 RTR **each with 10 TOE of Scorpion mine-clearing tanks**) — only 3 of 14 seeded.

**Key high-value arrivals with the model/turn the port must add:**

| GT/OpS | Unit | Model / note |
|---|---|---|
| 1/3 | Polish Bde | inf |
| 15/1 | 2nd Armored Div (+1 RHA, 51 Fld Arty, 2 HAA) | the whole 2 Armd — mostly missing |
| 32/3 | **Tiger Convoy (Alexandria)**: 4× Mk VI Light, **13× Crusader I**, 27× Matilda, 3× A13 | needs `crusader1`, `mk6`, `matilda2`, `a13` |
| 69/3 | 8 Armored Bde | `grant` |
| 80/2 | 9 Armored Bde | `crusader2` |
| 87/3 | 23 Armored Bde | `matilda2` |
| 88/1 | 24 Armored Bde | `grant` |
| 95/2 | 57 AT Regt [44] | `6pdr` |
| 99/1 | 42 & 44 RTR **return** | **`scorpion`** (10 TOE each) |

## 4.2 [20.78C] COMMONWEALTH PRODUCTION — the tank/gun RELEASE CLOCK — scan `docs/rules/90:3438-3456`

The Sherman etc. arrive as **Replacement Points via [20.78C]**, not as named reinforcement counters.
(qty / RP-cost / first-GT):

| system | qty | cost | first GT | model to add |
|---|---|---|---|---|
| **Sherman** | 62 | 12 | **89** | `sherman` |
| Grant | 56 | 8 | 66 | `grant` (present) |
| Crusader Mk I | 35 | 5 | 31 | `crusader1` |
| Crusader Mk II | 30 | 5 | 41 | `crusader2` (present) |
| **Crusader Mk III** | 18 | 6 | 88 | `crusader3` |
| **Valentine** | 20 | 3 | 39 | `valentine` |
| **Churchill** | 1 | - | 90 | `churchill` |
| Stuart | 44 | 10 | 35 | `stuart` (present) |
| Matilda | 25 | 2 | 9 | `matilda2` (present) |
| A9 / A10 / A13 / Mk VI | 8/10/8/15 | — | 3/3/9/3 | `a9`(✓)/`a10`/`a13`(✓)/`mk6`(✓) |
| **17-pounders** | 6 | 3 | **103** | `17pdr` |
| 6-pounders | 80 | 5 | 75 | `6pdr` (present) |
| **SP 6-pounders (Deacon)** | 7 | 3 | 76 | `deacon` |
| 2-pounders | 60 | 5 | 5 | `2pdr` (present) |

*(This is the balance clock: the CW armour build-up the engine "never delivers" is exactly this table.
Every dated row is a model the port must know. Note [20.78C] is a Phase-7 economy item, but the **model
ratings** it needs belong to Phase 3.)*

## 4.3 [4.43b] AXIS LAND UNIT REINFORCEMENT SCHEDULE — scan PDF **p.146-147** (`docs/rules/90:3683`)

*(Not transcribed verbatim here — TODO for Phase 3.5. Seeded side already has 88 Axis reinforcement
records, GE+IT, so the Axis reinforcement gap is smaller than the plan's "45 of 46 rows" headline
implies; the real Axis gap is the **named formations** in §2.5, not the schedule skeleton.)* The German
5 Le / 15 Pz / 90 Le / 164 Le and the Italian divisional blocks (Ariete GT18, Trieste GT50, Littorio
GT62, Folgore GT94…) are present. **Cross-render p.146-147 to diff the Ramcke Bde (GT86-93),
Sonderverband 288, the corps artillery park and the Flak battalions.**

## 4.4 OA charts still to render for Phase 3.3/3.5 (locations confirmed)

| chart | content | scan page |
|---|---|---|
| [4.44B] CW Organization-at-Arrival | which counters make up each CW formation, ID codes, arrival | PDF **p.116+** (`docs/rules/90:1919`) |
| [4.44b] Italian OA | Italian formation tree | PDF ~**p.142** (`docs/rules/90:3817`) |
| [4.44?] German OA | German formation tree | (`docs/rules/90:4754`) |

---

# HANDOFF TO PHASE 3 — ranked, with the numbers already read

1. **Add the 22 CW models to `data/unit_stats.json` `models`** (all ratings in §1.1; also in
   `phase3-oob-gap.json`). Highest balance leverage: `sherman`, `crusader1`, `crusader3`, `a10`,
   `valentine`, then the gun park (`5_5in`, `60pdr`, `6in_how`, `155mm_how` — today all fire as 25-pdr),
   then `bishop`/`priest`/`deacon`, `17pdr`, `scorpion`, `light_aa`/`heavy_aa`.
2. **Add the AA role** (rule 3.23) and set `is_pure_aa`; **classify on the counter, not the group
   substring** (T0-6). **Ship this in the SAME change as (1)+(3)** — never alone. Stop `oob.py:106-111`
   discarding the air counters.
3. **Fix `CW.mg` role CPA 20 → 8** ([4.46a] code u). Verify Italian role→ID-code mapping against
   `uc_p136` (engine `IT.hq cpa:30` matches code b(30), not code a(45)).
4. **Move the Axis garrisons to their [60.31] hexes (§3.1): Tobruk→C4807, Bardia→C4321 (into the main
   OOB), Benghazi→its victory hex.** Pure data, ~90% of the GT1 score. **Rule on the Benghazi
   A4827/B4827 errata (§3.2) first** and record `_errata_benghazi_hex`.
5. **Split every CW brigade into HQ + 3 battalions (rule 20.11).** ~34-36 brigades, ≈432 TOE.
6. **Transcribe [4.43a] fully (p.114-116): restore OpStage, the Cairo entry rule, and all ~32
   withdrawals + returns.** Add the ~15 missing Axis models (§1.2/§1.3) and the named Axis formations
   (§2.5): Ramcke Bde, Sonderverband 288, 300th Oasis Bn, Semovente/M14/41, the corps artillery.
7. 🔴 **NEVER ship the Axis half (3.5) without the CW half (3.3).** That is the BALANCE TRAP — it swings
   the campaign *harder* Axis.

**GATE B (a transcription check, not a balance reading):** after (1)-(5), the force ratio should invert
from **1.72:1 Axis → ~1.9:1 Commonwealth** as a dice-free property of the built OOB. Check that; do not
read the campaign result off it.

**Renders in scratchpad for re-verification:** `oob_p138/139/140` (tank-gun charts),
`uc_p133/134/136/137` (unit-char role charts), `setup_p78` + `benghazi_crop` ([60.31]),
`summary_p73` (important-locations, the A4827 print), `pz3e_crop` (the Pz III E misprint).
