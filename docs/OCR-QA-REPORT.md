# OCR QA Report — The Campaign for North Africa

Automated quality review of the machine-OCR'd rulebook. Every section (and the charts appendix) was read by an independent reviewer and judged for coherence, OCR garbles, broken numbers, structural problems, and table integrity.

> **Bottom line:** the rules prose is solid and usable. Of 68 sections, **7 are clean, 42 have only minor issues, and 19 have at least one significant issue** — almost all of which are recoverable OCR typos a human reader corrects on sight (e.g. *Asis*→Axis, *Beniheim*→Blenheim). A handful are real structural problems worth a targeted fix (listed below). For exact numbers in dense charts, the original scan remains the source of truth.

## Health at a glance

| Verdict | Sections | Meaning |
| --- | --- | --- |
| clean | 7 | Reads well; at most trivial typos. |
| minor | 42 | A few low/medium issues; fully usable. |
| significant | 19 | At least one high-severity garble/structure issue. |

**238 issues** flagged in total — 48 high, 101 medium, 89 low. By type: 143 OCR garbles, 40 structural, 19 table, 18 number, 13 truncation, 5 other.

## How to read this

- **OCR garbles** (by far the most common) are misread letters/words — *Navel*→Naval, *sucn*→such, *In-ative*→Initiative. They don't change rules logic and are obvious in context.
- **Table pointers** flagged as "missing data" (e.g. *7.2 Initiative Ratings Chart (see Separate Sheets)*) are **by design** — the 1979 rulebook prints those values on separate chart sheets, which are captured in the **Charts, Tables & Play Aids** section (`rules/90-charts-tables-and-play-aids.md`). Not an OCR failure.
- **Structural** issues (mis-numbered cases, spliced/jumbled content) are the ones worth a real fix — they're listed in their own section below.
- **Dense reference charts** (CRTs, unit-characteristics) were recovered as markdown where OCR was reliable; a few remain pointers to the scan. Always verify exact chart values against the original PDF before relying on them for adjudication.

## Corrections already applied

All of the report's recommended next steps have been carried out and the docs rebuilt:

- **~130 OCR typos corrected** across two passes — faction/term/aircraft/place garbles (*Asis*→Axis, *Navel*→Naval, *Beniheim*→Blenheim, *Mel09*→Me109, *crusiers*→cruisers, *Valetta*→Valletta, *In-ative*→Initiative, *Mirsielles*→Marseille, *birds*→birs, *Sidi Birani/Baranni*→Sidi Barrani, *Bobrida*→Bardia, …) plus scoped grammar fixes (*rot use*→not use, *Such tangs*→tanks, *no 20C*→no ZOC, …). Every change was logged.
- **LaTeX/notation artifacts cleaned** — the model's math rendering of counter symbols and fractions (`\frac{1}{2}`→1/2, `\xrightarrow{xx}`→xx, `\boxed{1}`→[1], `\dagger`→†, `^{E}`→E) is gone; 0 remain. The garbled dice-read notation became *10's figure / 1's figure*, and the §11.32 combat formula now correctly divides (`÷ 10`).
- **Case-number corruptions fixed** — §47.7/47.8 (were `[42.7]/[42.8]`), §52.3 OASES (was `[53.]`), and a §38.39 cross-reference (was a LaTeX-garbled `Case 38.35`).
- **§54 Supply Co-ordination de-spliced** — pages 70–73 are a 4-page reference-chart insert (Terrain Effects, Air/Land/Road Distance charts) bound mid-rules; they are now routed to the charts appendix, so §54 reads continuously (54.14 → 54.15).
- **Page 108** (looped garbage) is a clean pointer; **4 sideways charts** were re-OCR'd upright into real tables.

**Two items could not be auto-resolved** (no recoverable value in the scan-less text) and are left for manual lookup against the original:

- `see Case 00.00` in **[27.88]** (the LRDG "removed from physical sight" rule) and in **[30.5]** (sea transport of supplies) — the real case numbers were illegible to OCR.
- A handful of **place-name/number ambiguities** the reviewers flagged where the correct value needs the scan (e.g. *Scledima/Scledelima*, author-name spellings, a few chart values noted below).

Everything in the sections below is what the reviewers found *before* these fixes — kept for the record. The verdict tallies therefore reflect the pre-fix state.

## Structural issues worth a targeted fix

These genuinely affect navigation or meaning (not just a typo):

- **[04-game-equipment]** `4.52 Field Commander's Group (TOE Log Sheets)` — Seven labeled sections (A–G) presented in scrambled order: A, E, F, D, G, C, B instead of A–G sequentially
- **[08-land-movement]** `8.97` — Sentence ends mid-thought: 'In such a case any portion of the total number of attached trucks to that newly detached unit.' Missing verb/completion; reader cannot determine what happens in this scenario.
- **[11-the-combat-system]** `11.23` — Case 11.23 item 2 states Barrage costs 3 CP's for Phasing units, contradicting case 11.22 and 11.26 which establish 5 CP's; "undergoes" appears incorrect
- **[12-barrage-artillery-combat]** `12.17` — Second sentence starts 'All non-Phasing (Forward or Back) are subject...' but is missing the object noun (should be 'All non-Phasing Players' Guns...'). Makes rule grammatically incorrect and ambiguous.
- **[34-the-aircraft]** `34.84 (lines 134–136)` — Line 134 ends with "The" after "divide the total by four, not twelve). The" — line 135 is blank, line 136 resumes with "individual planes arriving..." Text is missing between the trailing article and the continuation.
- **[38-aircraft-maintenance]** `between 38.33 and 38.34` — 'SGSU 274RAF 25' appears with no context or label, breaks logical flow
- **[47-abstract-logistics-rules]** `47.7 (line 76)` — [42.7] BOMBARDMENT OF THE COMMONWEALTH FLEET — case number is 42.7 but should be 47.7; sequence jumps backward from 47.6 to 42.7
- **[47-abstract-logistics-rules]** `47.8 (line 80)` — [42.8] STACKING MODIFICATIONS — case number is 42.8 but should be 47.8; continues wrong sequence
- **[48-sequence-of-play-logistics-game]** `Lines 128–144, H. Movement And Combat Phase` — Segment numbering corrupted: declared as 'four segments' but reads \1, \2, ### 3, \4, then \3 again. Segment 3 appears twice; 'Truck Convoy Movement Phase' is misformatted or misplaced.
- **[52-water]** `52.3 (OASES section)` — Heading mis-labeled "[53.]" instead of "[52.3]" — jumps to section 53 then back to 52.4, breaking case sequence.
- **[54-supply-co-ordination]** `Pages 070–074 (lines 22–247)` — Content from sections 8.37, 36.53, 37.4, 37.42, 56.26, 56.18 spliced into middle of section 54, breaking document continuity. File should contain only 54.0–54.5.
- **[54-supply-co-ordination]** `[54.14] (line 18–20)` — Case sentence cuts off at 'Only one Phasing unit per' and resumes only after 225 lines of wrong sections.
- **[60-scenario-group-one-the-italians]** `60.93, lines 458–460` — Cross-references cite '60.82 "B"' and '60.82 "C"' but should cite '60.92' — section 60.92 contains the subsections A, B, C being referenced; 60.82 is victory conditions.
- **[65-in-conclusion]** `65.0 main paragraph, line 4` — "CNA was playtested for nearly two years an extensive list of"—missing word(s) between "years" and "an". Should read "...two years by/with an extensive list..."
- **[90-charts-tables-and-play-aids]** `page 108, lines 1241-2819` — Massive corrupted section beginning with garbled 'Key of ABB/Obbard/Perfetti' text, followed by repeated '[46.3] ANNUAL AREARTER COMMERCIAL COMBINABLE PLUMBING' headers and spam repetitions of 'The following table provides the information in the English:' — entire section is unusable nonsense.

## All high-severity findings

### OCR garbles (clear misreads)

- **[20-reinforcements-replacements-and-commonwealth-withdrawals]** `Case 20.15, line 24` — "Asis Player may divert forces" — should be "Axis Player"; critical faction name error
- **[20-reinforcements-replacements-and-commonwealth-withdrawals]** `Case 20.63, line 102` — "Navel Convoy Arrival Phase" — should be "Naval Convoy Arrival Phase"; game term garble
- **[32-abstract-logistics-and-air-rules]** `Case 32.37` — "westernnot hexrow" should be "westernmost hex row"; nonsense word clearly misread
- **[34-the-aircraft]** `34.11 (line 18)` — "An Mel09E based on a Landing Strip" — "Mel09E" should be "Me109E" (Messerschmitt Bf 109E aircraft designation). Appears three times in the same sentence.
- **[34-the-aircraft]** `34.82 (line 117)` — "planes at on-manufactiles divided by twelve" — "on-manufactiles" is nonsense; should be "on-map facilities" (which appears correctly two lines below in the same paragraph).
- **[38-aircraft-maintenance]** `38.39` — \( ^{33} \) .35 — LaTeX artifact, should read 'Case 38.35'
- **[41-bombing-missions]** `[41.92]` — "engage in commit but voluntarily" — should be "engage in combat voluntarily"; garbled syntax impedes rule clarity
- **[52-water]** `52.16` — "birds" should be "birs" — document uses "birs" (North African wells term) throughout; "birds" breaks meaning.
- **[52-water]** `52.22` — "rot use" should be "not use" — "The Axis Player may rot use the defunct..." is nonsensical.
- **[53-trucks-and-transport]** `53.24` — "ammunition and fuel loaded in trucks that hex may be expanded" — grammatically broken, likely should be "in that hex may be expended"
- **[55-ports-and-supply]** `[55.14]` — "operates at 3/5 (or 60%) **or** its assigned capacity" should be "**of** its assigned capacity" — word substitution changes rule meaning entirely
- **[60-scenario-group-one-the-italians]** `60.32, lines 196–198` — Aircraft type 'Beniheim Mk. I/IV/IVF' (3× repeated) should be 'Blenheim' — well-known WWII fighter.
- **[60-scenario-group-one-the-italians]** `60.31–60.82, multiple lines` — Location 'Sidi Barrani' spelled three inconsistent ways: 'Sidi Birani' (382), 'Sidi Baranni' (228, 447), 'Sidi Barrani' (338 — correct). Same location needs consistent spelling.
- **[62-scenario-group-three-operation-crusader]** `62.62, line 413` — Table header shows '\( \Delta t \)' (LaTeX math symbol) instead of 'Fuel' — incomprehensible in supply context
- **[62-scenario-group-three-operation-crusader]** `62.62, line 422` — 'two regular py units' should be 'supply units' — word severely garbled
- **[62-scenario-group-three-operation-crusader]** `62.8, line 447` — 'Bobrida' should be 'Bardia' (referenced as major location in 62.5, line 375) — geographical name corrupted
- **[63-scenario-group-four-el-alamein]** `63.2 SCENARIO LENGTH AND DURATION` — "Both scenarios begin with the 1st OptStage of Game-Turn 1OZ. "The Last Chance" Scenario ends with the completion of the 3rd OpStage of Game Turn 102 1st OpStage of Game-Turn 111." - '1OZ' is garbled; the end date is contradictory (102 vs 111).
- **[64-scenario-group-five-the-campaign-for-north-africa]** `Case 64.4` — "In-ative is determined normally" should be "Initiative"; broken OCR of key rule statement
- **[64-scenario-group-five-the-campaign-for-north-africa]** `Case 64.71` — "sucn occupying units" should be "such"; OCR h/n confusion in victory condition
- **[64-scenario-group-five-the-campaign-for-north-africa]** `Case 64.75` — "(Unit, not Drug)" is nonsensical; appears to be corrupted clarification of withdrawal rules
- **[90-charts-tables-and-play-aids]** `line 295, heading` — 'THE CAMPAGN FOR NORTH AFRICA' — missing 'I' in CAMPAIGN

### Broken numbers / notation

- **[03-glossary-and-unit-definitions]** `3.1 — Sequential Dice Roll` — "\( 10^{3} \) s figure and the smaller die yields the \( 1^{3} \) s figure" is garbled notation; should be "tens figure" and "ones figure" for a d6+d6 read as 11–66
- **[11-the-combat-system]** `11.32` — Formula shows "Combat Rating × TOE Strength used + 10 =" but should be "/" (divide); text and examples confirm division (e.g., "108 ÷ 10 = 10.8")
- **[45-air-to-air-combat]** `Aircraft table (line 40)` — "Messerschmitt Bf. 100" — no such aircraft; context suggests Bf 109 (table lists Bf 110, 109E, 109F elsewhere)
- **[53-trucks-and-transport]** `53.24` — [53,24] — case number uses comma instead of period
- **[54-supply-co-ordination]** `8.37 TERRAIN EFFECTS CHART, Desert row (line 36)` — Mot column shows '43'; implausible movement cost (should be single digit).
- **[54-supply-co-ordination]** `8.37 TERRAIN EFFECTS CHART, Road row (line 41)` — Costs show '16' and '126'; implausible (normal costs 1–4).
- **[61-scenario-group-two-the-desert-fox]** `61.73, line 242` — Cross-reference As in 61.62 C should be 61.72 C — section 61.62 does not exist.
- **[63-scenario-group-four-el-alamein]** `63.2 SCENARIO LENGTH AND DURATION` — Scenario end-date statement is incoherent: claims completion at both 'Game Turn 102' and 'Game-Turn 111' in the same sentence.

### Structure & case-numbering

- **[04-game-equipment]** `4.52 Field Commander's Group (TOE Log Sheets)` — Seven labeled sections (A–G) presented in scrambled order: A, E, F, D, G, C, B instead of A–G sequentially
- **[11-the-combat-system]** `11.23` — Case 11.23 item 2 states Barrage costs 3 CP's for Phasing units, contradicting case 11.22 and 11.26 which establish 5 CP's; "undergoes" appears incorrect
- **[38-aircraft-maintenance]** `between 38.33 and 38.34` — 'SGSU 274RAF 25' appears with no context or label, breaks logical flow
- **[47-abstract-logistics-rules]** `47.7 (line 76)` — [42.7] BOMBARDMENT OF THE COMMONWEALTH FLEET — case number is 42.7 but should be 47.7; sequence jumps backward from 47.6 to 42.7
- **[47-abstract-logistics-rules]** `47.8 (line 80)` — [42.8] STACKING MODIFICATIONS — case number is 42.8 but should be 47.8; continues wrong sequence
- **[48-sequence-of-play-logistics-game]** `Lines 128–144, H. Movement And Combat Phase` — Segment numbering corrupted: declared as 'four segments' but reads \1, \2, ### 3, \4, then \3 again. Segment 3 appears twice; 'Truck Convoy Movement Phase' is misformatted or misplaced.
- **[52-water]** `52.3 (OASES section)` — Heading mis-labeled "[53.]" instead of "[52.3]" — jumps to section 53 then back to 52.4, breaking case sequence.
- **[54-supply-co-ordination]** `Pages 070–074 (lines 22–247)` — Content from sections 8.37, 36.53, 37.4, 37.42, 56.26, 56.18 spliced into middle of section 54, breaking document continuity. File should contain only 54.0–54.5.
- **[60-scenario-group-one-the-italians]** `60.93, lines 458–460` — Cross-references cite '60.82 "B"' and '60.82 "C"' but should cite '60.92' — section 60.92 contains the subsections A, B, C being referenced; 60.82 is victory conditions.

### Table integrity

- **[15-close-assault]** `[15.53]` — Organizational size adjustment table rows 1–4 are malformed. 'Division | 3-point | 1' and 'Division | 3-point | Brigade' don't align with schema; 'Division | 2-point | 2' is incomplete; row '| | Brigade' is a dangling fragment.
- **[38-aircraft-maintenance]** `38.38` — 'Aircraft Refit Table (see Charts and Tables)' — only a pointer, actual table data missing
- **[45-air-to-air-combat]** `Figures A & B (lines 28–34)` — Headers present ("Figure A:", "PLAYER A", "Figure B:", "PLAYER B") but no actual table/plane-listing data, just bare labels. Figure C has a table; A/B tables are missing.

### Truncated text

- **[08-land-movement]** `8.97` — Sentence ends mid-thought: 'In such a case any portion of the total number of attached trucks to that newly detached unit.' Missing verb/completion; reader cannot determine what happens in this scenario.
- **[12-barrage-artillery-combat]** `12.17` — Second sentence starts 'All non-Phasing (Forward or Back) are subject...' but is missing the object noun (should be 'All non-Phasing Players' Guns...'). Makes rule grammatically incorrect and ambiguous.
- **[34-the-aircraft]** `34.84 (lines 134–136)` — Line 134 ends with "The" after "divide the total by four, not twelve). The" — line 135 is blank, line 136 resumes with "individual planes arriving..." Text is missing between the trailing article and the continuation.
- **[54-supply-co-ordination]** `[54.14] (line 18–20)` — Case sentence cuts off at 'Only one Phasing unit per' and resumes only after 225 lines of wrong sections.
- **[65-in-conclusion]** `65.0 main paragraph, line 4` — "CNA was playtested for nearly two years an extensive list of"—missing word(s) between "years" and "an". Should read "...two years by/with an extensive list..."
- **[90-charts-tables-and-play-aids]** `page 108, lines 1241-2819` — Massive corrupted section beginning with garbled 'Key of ABB/Obbard/Perfetti' text, followed by repeated '[46.3] ANNUAL AREARTER COMMERCIAL COMBINABLE PLUMBING' headers and spam repetitions of 'The following table provides the information in the English:' — entire section is unusable nonsense.

### Other

- **[27-desert-raiders-commandos]** `27.88` — see Case 00.00 — non-standard case number, likely broken cross-reference

## Per-section verdicts

| Section | Verdict | Issues | Reviewer note |
| --- | --- | --- | --- |
| `06-the-capability-point-system` | clean | 0 | No significant OCR errors; well-rendered rulebook section with proper terminology, plausible numbers, and logical game mechanics. |
| `26-minefields` | clean | 0 | Section 26.0 reads coherently with proper case numbering, plausible rules mechanics, and no OCR garbles—acceptable for 1979 wargame prose. |
| `42-non-combat-missions` | clean | 0 | All rules coherent and well-structured; case numbering orderly; only trivial abbreviation inconsistency ("OpStage" vs. "Operations Stage"). |
| `49-fuel` | clean | 0 | Section 49.0 (FUEL) is clean OCR with correct structure, sensible game mechanics, and no material issues. |
| `56-the-axis-naval-convoy-system` | clean | 0 | A coherent, logically structured convoy supply system with proper case hierarchy, sensible numbers, and no OCR garbles that impede meaning. |
| `57-commonwealth-supply-base` | clean | 0 | No issues detected; OCR is clean, case numbering correct, rules fully coherent. |
| `58-abstract-air-rules` | clean | 0 | Section 58.0 reads as coherent wargame rules with correct case numbering, sensible mechanics, verified math in the truck-loss example, and no OCR garbles or ... |
| `00-front-matter` | minor | 1 | One OCR colon-for-period error in case numbering (3:1 should be 3.1); otherwise fully coherent and usable. |
| `01-introduction` | minor | 1 | One likely OCR error (formative/formidable), otherwise well-structured and coherent. |
| `02-how-to-play-the-game` | minor | 2 | Minor grammatical corruption (line 30) and an atypical but plausible turn count; otherwise coherent and usable wargame rules. |
| `03-glossary-and-unit-definitions` | minor | 8 | Several OCR typos (parachod, Cost/Coastal) and notation garble (10^3/1^3 for dice) plus one broken sentence structure, but rules remain coherent and usable.<... |
| `05-the-sequence-of-play-land-game` | minor | 3 | One meaningful OCR garble ("Pashing" for "Phasing") and multiple markdown escaping artifacts; otherwise fully functional rulebook section. |
| `07-initiative` | minor | 1 | Section 7.1 mechanics excellently OCR'd and coherent; section 7.2 data table missing but clearly marked as external reference. |
| `08-land-movement` | minor | 5 | OCR'd rulebook section with mostly clean structure but one truncated rule sentence, one wrong case reference, and three minor typos. |
| `09-stacking` | minor | 4 | Solid OCR with one garbled/mislabeled rule item ([9.16c]) featuring undefined "CPA" acronym and contradictory motorization logic. |
| `10-zones-of-control` | minor | 1 | One OCR garble (terrain term) in exception list; otherwise coherent and usable. |
| `13-retreat-before-assault` | minor | 1 | Section is coherent with one low-severity grammatical error in a subheading. |
| `14-anti-armor-combat` | minor | 2 | Two minor structure issues (inconsistent heading levels; page break mid-sentence in 14.34) but text is fully coherent and usable. |
| `16-patrols-and-reconnaissance` | minor | 2 | Two low-to-medium OCR errors (space loss, grammar) but text remains fully usable and rules are clearly intelligible. |
| `17-morale` | minor | 4 | A few low/med garbles and one "three areas but six listed" contradiction, but fully usable as-is. |
| `18-reserve-status` | minor | 5 | Five OCR/formatting errors (mostly term inconsistencies and one garbled notation), but mechanics remain coherent and usable. |
| `19-organization-and-reorganization` | minor | 3 | Generally solid OCR with three localized issues: a duplicated sentence fragment (19.47), an incomplete phrase (19.67), and a heading hyphenation error (19.9). |
| `21-breakdown` | minor | 1 | One missing table value (ArmRecce rating), otherwise well-structured and logically coherent rules. |
| `22-repair` | minor | 4 | Four low-to-moderate OCR spelling errors (Brokenown, Rockendown, beings, DTS/TDS inconsistency) that don't impede understanding; structure and logic are sound. |
| `23-engineers` | minor | 2 | Two low-severity issues (OCR formatting and subject-verb agreement) don't impede readability; otherwise coherent rules section. |
| `24-construction` | minor | 3 | Construction rules read coherently with orderly case numbering and sound game mechanics; three minor OCR artifacts (spaced word, wrong verb, stray hyphen) do... |
| `25-fortifications` | minor | 2 | Minor OCR artifacts (Cairo misspelled as "Cario", stray quote mark) but otherwise clean, orderly, and coherent as wargame rules. |
| `27-desert-raiders-commandos` | minor | 6 | Several OCR garbles (Reccce, aos, LRLDG, thereofused) and a non-standard cross-reference (Case 00.00) require correction, but rules remain understandable. |
| `28-prisoners` | minor | 2 | Two low-severity OCR artifacts ("aDeparture" spacing, "each 1" redundancy) that do not materially impede understanding or usability. |
| `29-weather` | minor | 2 | Section 29.0 reads coherently as valid wargame rules; two low-severity issues (one OCR garble, one expected table pointer) don't impede usability. |
| `30-the-mediterranean-fleet-commonwealth` | minor | 3 | Three low-severity OCR artifacts (missing preposition, spelling flip-flop, odd hex coord) in otherwise coherent naval rules section. |
| `31-rommel` | minor | 1 | One truncated parenthetical in rule 31.1 (vehicle definition ends mid-phrase), otherwise clean and coherent Rommel rules section. |
| `32-abstract-logistics-and-air-rules` | minor | 6 | Section reads coherently as wargame logistics rules with orderly case numbering, but contains one clear garble ("westernnot"), one case-number format violati... |
| `33-sequence-of-play-air-game` | minor | 3 | Air game sequence-of-play section with minor formatting inconsistencies and one missing auxiliary verb, otherwise coherent and fully usable. |
| `35-squadron-ground-support-units` | minor | 4 | Section reads coherently with mostly clear rules; two low-severity OCR errors and one medium structural table issue present but don't block understanding. |
| `36-air-facilities` | minor | 1 | One enumeration error in Case 36.5 (list shows "a) b) 3)" instead of "a) b) c)"); otherwise coherent and sensible. |
| `37-flight` | minor | 1 | Clean OCR with orderly cases and sensible mechanics; one minor incomplete sentence in 37.31 does not impede understanding. |
| `39-missions` | minor | 4 | A few clear OCR errors (garbled rule sentence, spacing issue) that don't break overall coherence but would flag a careful proofreader. |
| `40-fighter-combat` | minor | 4 | Coherent fighter combat rules with four scattered OCR garbles (proper name, word merger, digit substitution, duplication) that moderately impede clarity but ... |
| `41-bombing-missions` | minor | 5 | Five localized OCR errors (bomblood/bombload, doubled "that", period typo, Axi/Axis, garbled combat syntax) in otherwise coherent rules section. |
| `43-axis-italian-aegean-air-bases` | minor | 1 | One clear OCR garble (FW220 for Fw200), otherwise clean and well-structured. |
| `44-malta` | minor | 3 | Three minor OCR errors (punctuation, preposition, sentence structure) in an otherwise coherent and usable Malta air rules section. |
| `46-anti-aircraft-fire-flak` | minor | 3 | Three fixable OCR/structure issues (one low, two med) that don't break overall coherence; section is fully usable with minor cleanup. |
| `50-ammunition` | minor | 3 | Minor OCR/parsing issues (one heading misspelling, one grammar garble, one table pointer) but fully usable and sensible. |
| `51-stores` | minor | 1 | One structural anomaly (POW/10 fragment) that doesn't belong; otherwise coherent, well-numbered rules with plausible mechanics. |
| `59-introduction-to-scenarios` | minor | 4 | Three garbled abbreviations/words (one serious: "Conps" → Corps) and one formatting inconsistency; text remains coherent and usable. |
| `61-scenario-group-two-the-desert-fox` | minor | 5 | Five scattered OCR errors (one broken cross-reference, three location-name garbles, one apostrophe artifact) in otherwise coherent scenario setup. |
| `65-in-conclusion` | minor | 5 | Five minor issues (missing word, inconsistent author names ×2, numeral garble, orphaned fragment) that don't prevent understanding but require cleanup. |
| `99-foldout-charts` | minor | 1 | Section is structurally sound but page 187 counter back is severely truncated—only category labels with no actual counter type names listed for a 200-piece s... |
| `04-game-equipment` | significant | 3 | Out-of-order lettering in TOE Log Sheets, missing chart tables, and incomplete Counter Summary section significantly degrade usability. |
| `11-the-combat-system` | significant | 4 | Two OCR garbles and one formula error are manageable, but the 11.23/11.22 CP cost contradiction for Barrage creates substantive rule ambiguity. |
| `12-barrage-artillery-combat` | significant | 4 | Coherent barrage rules undermined by high-severity grammatical truncation in 12.17, plus terminology and syntax errors in 12.33 and 12.46. |
| `15-close-assault` | significant | 6 | Critical organizational-size table is misaligned; otherwise coherent but with scattered OCR garbles including one mid-rule corruption ('Xsurers'). |
| `20-reinforcements-replacements-and-commonwealth-withdrawals` | significant | 7 | Section has multiple OCR garbles including critical game term "Asis" for "Axis" and "Navel" for "Naval", plus a questionable case cross-reference; overall us... |
| `34-the-aircraft` | significant | 3 | Two OCR garbles (aircraft designation, facility name) and a sentence-level truncation break rule clarity and would mislead an AI system or careful reader. |
| `38-aircraft-maintenance` | significant | 9 | LaTeX artifact, missing refit table, misplaced fragment, and multiple OCR word errors that impede understanding. |
| `45-air-to-air-combat` | significant | 5 | Five issues: three OCR garbles (my→may, divi-dually→individually, Henkels→Heinkels), one broken aircraft model (Bf. 100), and missing table data for Figures ... |
| `47-abstract-logistics-rules` | significant | 3 | Two case numbers (42.7, 42.8) appear where 47.7 and 47.8 belong, plus one colon/period notation error; rules text itself is coherent and plausible. |
| `48-sequence-of-play-logistics-game` | significant | 5 | Mostly coherent wargame rules spoiled by a jumbled segment numbering error in the Movement & Combat Phase that would confuse play execution. |
| `52-water` | significant | 5 | Three high-severity garbles (birds/birs, rot/not use) and a critical structural error (section 52.3 mis-labeled as 53) impede clarity. |
| `53-trucks-and-transport` | significant | 3 | Significant issues: case number with comma (53,24 not 53.24) and incoherent phrase "loaded in trucks that hex may be expanded" in 53.24; also spurious period... |
| `54-supply-co-ordination` | significant | 8 | File contains section 54 content interrupted by ~5 pages of wrongly included sections (8, 36, 37, 56) with embedded OCR number garbles. |
| `55-ports-and-supply` | significant | 3 | 3 significant issues: critical or/of swap in [55.14], OCR garble "Optage" for "OpStage", and page-break interruption in [55.22] splitting a sentence with met... |
| `60-scenario-group-one-the-italians` | significant | 11 | Multiple persistent OCR errors in aircraft names, geographic location spellings (same place spelled 3 ways), broken cross-references in abstraction rules, an... |
| `62-scenario-group-three-operation-crusader` | significant | 11 | Multiple OCR garbles (Bobrida/Bardia, py/supply, Delta-t for Fuel) and table formatting issues impede clear reading, though wargame structure remains followa... |
| `63-scenario-group-four-el-alamein` | significant | 14 | 63.0 El Alamein scenario section reads coherently but suffers from multiple OCR garbles affecting unit names, corrupted table headers, and a critical ambigui... |
| `64-scenario-group-five-the-campaign-for-north-africa` | significant | 6 | Four high-severity OCR garbles (Initiative → "In-ative", such → "sucn", unclear Drug fragment, malformed victory table) impede rule comprehension. |
| `90-charts-tables-and-play-aids` | significant | 5 | Large swathes of pages 108-110 are corrupted with nonsensical prose, repeated false headers, and spam text; smaller issues include OCR garbles and structural... |

## Status of the recommended next steps

1. ~~Safe global typo fixes~~ — **done** (~130 corrections, logged).
2. ~~Fix case-numbering corruptions~~ — **done** for §47.7/47.8 and §52.3; the two `see Case 00.00` references remain (illegible in OCR — need the scan).
3. ~~Re-knit §54~~ — **done** (chart insert routed to the appendix).
4. ~~Pointer the page-108 garbage~~ — **done**.
5. **Spot-verify dense charts** (CRTs, unit-characteristics, terrain effects) against the original scan before using exact values in the game engine — this remains a human step; OCR of dense grids is good but not guaranteed cell-perfect.

*Generated from 68 independent section reviews; corrections applied and verified afterward.*
