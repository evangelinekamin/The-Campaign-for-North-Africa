# Phase 7 owner rulings docket

Open rulings Phase 7 (the replacement economy) needed. **ALL FIVE RULED BY EVE, 2026-07-24 -- she agreed
with every recommendation.** Recorded here as the binding reading; the detail lives in
scratchpad/port/transcriptions/. A sixth (item 6) surfaced after the docket was written and is assumed,
not ruled -- flagged for override.

## 1. REPLACEMENT / EQUIPMENT LEAD TIME = **FOUR GAME-TURNS**  [RULED -- Eve]
The book prints it three ways: [20.72] (PDF p.032) prose "two months in advance"; [20.72]'s OWN worked
example plan-July -> arrive-August = one month; [20.21]/[20.78B] footnote (PDF p.031/141) **four
Game-Turns**; [20.63] Axis Pool 2 Game-Turns.
**RULING: four Game-Turns** (the [20.21]/[20.78B] value, ~1 month, consistent with 20.72's own example);
"two months" is loose prose. The `Date` column on [20.78B/C] is the PLAN turn, so on-map arrival =
Date + 4. **The Shermans land ~GT93, not GT89.** Axis Pool keeps its own printed [20.63] 2-GT lead.

## 2. TANK RP TOTAL = **332** (all 13 printed rows)  [RULED -- Eve]
The port plan's "306 tank RP" is a derived number that is not in the book. The [20.78C] chart's 13
armour rows sum to **332** (scan-verified, PDF p.141).
**RULING: seed all 13 rows at their printed `#` values (332). Ignore the plan's 306.**

## 3. [20.83] TOE cross-reference = **a typo for 20.82**  [RULED -- Eve]
20.83 cites "(20.75)" for the >=75%-TOE rule; 20.75 is CW Production, unrelated. The 75% rule is
**20.82** (20.85 cites it correctly). PDF p.032.
**RULING: printed typo. Wire 20.82; record under a named errata key** (54.17 class, never silent).

## 4. 64.75 "per week" = **one Game-Turn**  [RULED -- Eve]
64.75-A pays 1/2 pt per WEEK a battalion is voluntarily withdrawn; CNA Game-Turns are weekly.
**RULING: week = one Game-Turn, NOT one OpStage.**

## 5. 5th-Panzer arrival = **the [4.43b] Reinforcement Schedule**  [RULED -- Eve]
[4.43b] (PDF p.145) and the [4.45c] OA chart (PDF p.162) disagree on the 5 Pz Regt HQ / I/5 / II/5
arrival OpStages (22/1, 22/2, 24/2 vs 2/21, 1/22, 2/22). Both scan-confirmed; a genuine book
self-contradiction. **RULING: take [4.43b], the Reinforcement Schedule -- it is what the campaign
set-up consumes.**

## 6. [20.62] SHIPPING TONNAGE PER REPLACEMENT POINT = **30**  [ASSUMED -- flagged, not yet ruled]
Surfaced in the 20.66 transcription AFTER this docket was written, so it carries no ruling yet.
- **Reading A** -- [20.62]'s worked example (PDF p.032): "10 Italian Infantry Replacement Points ...
  **350 Tons**" -> 35 tons/point.
- **Reading B** -- the [20.66] Italian Production Chart's own Tonnage column (PDF p.176), read at 4x
  zoom to exclude an OCR misread: **30**. German Infantry prints 30 too.
- **Third source** -- rule 56.24 (PDF p.075): "10 Infantry Points ... **300 tons**." Agrees with B.
Two independent citations (the operative chart + a second worked example) say 30; only 20.62's own
example says 35 -- the same shape as ruling 1 (a loose prose example against a printed case value).
**ASSUMED: 30 tons/point, under a named errata key. Trivially reversible -- one constant in data/.**

## 7. [64.74] EXCLUSION = **score only SPENDABLE classes**  [RULED -- Eve, 2026-07-24]
Surfaced by Gate 7A/7B as D-1 (it was not in this docket when Phase 7's tail was built). The as-committed
64.74 used a flagged proxy that ALSO dropped Axis infantry (deviating from the scan, which excludes
infantry for the Commonwealth only), and still scored unused EQUIPMENT on both sides -- a fixed
Axis+893 / CW+958 constant that compressed every campaign grade toward 1:1 (an artifact of the unbuilt
equipment/Axis spend, not the flow).
**RULING: 64.74 scores UNUSED Replacement Points only for classes the engine can actually SPEND** --
"unused" presupposes "usable"; a class with no rebuild beat is 100% unused by construction, which is an
unmodelled spend, not the husbandry 64.74 rewards. Today the only live spend is Commonwealth infantry
(itself book-excluded), so **64.74 correctly scores 0/0** until a non-infantry spend lands; the grade
returns to geography-driven. IMPLEMENTED (data `spendable_classes`, `replacement_vp_spendable_classes`):
the drop-Axis-infantry proxy was REVERTED so `excluded_classes` is again exactly the printed rule, and
the engine-state truth lives in the spendable gate. Grows one data edit at a time as each spend lands
(CW equipment -> add ALLIED tank/gun; Axis spend -> add AXIS infantry/tank/gun).

## Already resolved / moot (recorded so they are not re-litigated)
- [60.32] Italy/Sicily basing: RULED (Eve) -- a placement rule with two exclusions; 394 planes take the
  field in Africa, basing in Sicily is a wartime redeployment DECISION. Done.
- FW220 = Fw. 200 C (Eve). [35.23] CW squadron = 15/5/20 July-1941 (Eve). 54.17 demolition errata (Eve).
- 38.35/[38.37] refit modifier crew-vs-planes: MOOT for now (the campaign fields only Italian crew AND
  Italian planes -> both readings give +2); returns when German aeroplanes reach Africa.
- [4.43a] GT numbering is the Reinforcement-Track GT index, not calendar -- a wiring fact, not a ruling;
  map to the same `arrival_turn` axis the campaign reinforcement data already uses.

See [[cna-bug-backlog]], scratchpad/port/00-THE-PORT-PLAN.md Phase 7, and the transcription docs.
