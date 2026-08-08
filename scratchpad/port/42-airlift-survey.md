# [42.3]/[42.4] AIR TRANSPORT AND AIRDROP -- READ-ONLY SURVEY, 2026-08-08

Produced by the [39.19] air-handback workflow (wf_32595c2d-bf6) alongside the slice that
opened Policy.air_missions. NOTHING HERE IS BUILT. It exists to answer one question --
is the unmodelled airlift a decisive second last mile or a rounding error -- and to record
the sequencing constraint the answer turns on ([34.53]: transports must have heavy CAP).

---

# [42.3]/[42.4] AIR TRANSPORT & AIRDROP — READ-ONLY SURVEY. No engine code written.

**VERDICT UP FRONT: THIS IS NOT A ROUNDING ERROR. It is the largest unbuilt logistics channel in the book, and it is lopsidedly COMMONWEALTH.** One Commonwealth transport squadron delivers ~160 tons/Operations Stage — **5× the entire Commonwealth truck last mile (31.7 t/OpS measured over 30 seeds)**. The full 1942 Commonwealth transport establishment the book schedules is 254 ten-ton aircraft. The claim in the task brief is confirmed with room to spare.

**But I recommend a SEQUENCING condition, not an unconditional "build it next" — see §6.**

---

## 1. [42.3] AND [42.4], TRANSCRIBED VERBATIM OFF THE SCAN

Rendered `tmp/The Campaign for North Africa.pdf` **PDF p. 60 (printed folio 13)** at 300 dpi, cropped to columns 2 and 3, read glyph by glyph. Cross-checked against `/home/eve/projects/tcfnatdw-ocr/ocr/markdown/page-0060.md` (Mistral) and `/home/eve/Projects/tcfnatdw/docs/rules/42-non-combat-missions.md`. **The Mistral corpus is character-accurate here on every case.** `docs/rules/42-*.md` has one typo the scan refutes: it prints `motorcycle infantry/rece units`; the scan prints `recce`.

### [42.3] TRANSPORT MISSIONS

> **[42.31]** Certain planes with transport capability may transport personnel or supplies by air. The cargo capacity of each transport is listed on the Aircraft Characteristics Chart in terms of TOE Strength Points or tons of supplies.

> **[42.32]** For a Transport to carry a TOE Strength Point or supplies to a given hex, that ``cargo'' must start the Operations Stage in the hex with the transport. The transport may then fly one type of transport mission:
> a. The Transport flies to the target hex, lands the cargo, and flies back; or
> b. The transport flies to the target hex and lands, remaining in that hex. In this case, the transport may use its transfer range (double its normal range).

> **[42.33]** Transport missions must be flown to Friendly air facilities, as the planes have to land. Supplies and personnel may be *airdropped* under special circumstances (See 42.4)

> **[42.34]** Personnel transported by air may not voluntarily move in the Operations Stage they are transported in, having used their allotted CPA. Personnel may be flown into a hex in an Enemy Zone of Control; however, such units may not be used for any attacks. That is, they may not voluntarily expend CP's on combat. They may defend. Personnel air-transported may never voluntarily exceed their basic CPA, through reaction or retreat before assault.

> **[42.35]** Supplies air-transported may be used as soon as they can be assigned to a dump or specific units. They cannot be used directly ``off the plane.'' They must be distributed in the Organization Phase first.

> **[42.36]** Transport missions may be flown only in Operations Stages. Planes require refitting,even when flying Transport Missions.

(`refitting,even` — the book's own missing space.)

> **[42.37]** Only infantry (without trucks), motorcycle infantry/recce units, and airborne units may be transported by air. **Exception:** *dead* camels may be transported by air. *Live* camels may *not* be transported by air.

### [42.4] AIRDROP MISSIONS (PARATROOPS)

Unnumbered preamble, verbatim:

> Although there were several airborne units in the desert campaign (The Ramcke Brigade and the Folgore Division), there were no major airborne missions. The following rules are, in essence, hypothetical.

> **[42.41]** Units capable of being airdropped are so noted on the OA Sheets. Such units may be airdropped by transport planes during a tactical land support Air Phase, under certain circumstances.

> **[42.42]** An airborne mission is the same as a transport mission (42.32a). The only difference is that the units are *dropped* into the hex, not landed, so an air facility is not needed for the transports. However, they must start from a Friendly air facility.

> **[42.43]** Units may be airdropped into any clear, gravel or desert hex. They may not be airdropped into major cities and they may not be airdropped into hexes occupied by Enemy units or hexes in an Enemy Zone of Control. Units may be airdropped into a Friendly occupied hex, within stacking restrictions, as long as such hex is not in an Enemy ZOC. In addition, the drop-zone hex may not be more than two hexes from a recognizable land feature (42.44).

> **[42.44]** A recognizable land feature is a major city, a road (unfinished, destroyed or not) or railroad hex, a village, air facility, or oasis.

> **[42.45]** Airdrops may not occur in sandstorms or rainstorms. However, there is no drift; units always drop in the target hex. There are no casualties in an airdrop.

> **[42.46]** Airdropped units require and use supplies the same as any unit: they are *not* commandos. Thus, only certain types of supplies may be airdropped: ammunition and stores may be airdropped (using the precepts of 42.42 and 42.43). Supplies may be airdropped into a *Friendly-occupied hex* even if it is in an Enemy Zone of Control. In the latter case, there is no need to use the recognizable land feature provision of the airdrop rule. Airdropped supplies may be used as soon as they arrive, unlike transported supplies (42.35).

> **[42.47]** Airdropped combat units may move and fight normally, with one exception: they may not voluntarily exceed their CPA in the Operations Stage in which they are dropped.

> **[42.48]** There is no limit to the number of TOE Strength Points that may be dropped (within the limits of how many transport planes you can muster). However, no unit may be airdropped more than once a month (every 12 Operations Stages).

**§3 of the task brief is CONFIRMED VERBATIM.** Airborne resupply of a besieged garrison is real, is usable the Operations Stage it lands, and needs no recognizable land feature when it goes into a Friendly-occupied hex in an enemy ZOC. **The one thing the brief did not anticipate: [42.46] restricts airdropped supplies to AMMUNITION AND STORES. Fuel and water may not be airdropped at all.** They can only arrive by a [42.3] transport mission landing at a friendly air facility.

---

## 2. THE TRANSPORT CELLS, VERIFIED — AND THE NOTATION DECODED

Rendered **PDF p. 113** ([4.44A] Commonwealth Bombers/Flying Boats/Transports/Recon) and **PDF p. 144–145** ([4.44b] Italian, [4.44c] German) at 300 and 600 dpi.

### Every cell in `data/logistics_rates.json` is CORRECT as transcribed

| Type | Transport cell (scan) | file | ✓ |
|---|---|---|---|
| Bombay Mk. I | `1 or 10 tons` (on the **88-range** row only) | `1 or 10 tons` | ✓ |
| Valentia | `1/4 or 5 tons` | `1/4 or 5 tons` | ✓ |
| S.M. 81 Pipistrello | `1P or 2½` | `1P or 2 1/2` | ✓ |
| Ca 309 Ghibli | `0 or ½` | `0 or 1/2` | ✓ |
| every other charted type in the file | `-` / `.` | `-` | ✓ |

One nuance worth recording: **the Bombay's two rows differ in the Transport column.** The `203**` transfer-configuration row prints `. . . .` (four dots — *no* transport capability); the `or 88` row prints `. . !` plus `1 or 10 tons`. Verified at 600 dpi. The engine already fields the Bombay on the 88 row.

### THE NOTATION, decoded off the two printed keys (verbatim)

**Commonwealth key, PDF p. 113:**
> `1/4,1` = The number of TOE Strength Points or Replacement Points the aircraft may transport. `5,10` = The number of tons of supplies the aircraft may transport. **Note that the plane may not transport troops and supplies at the same time.**

**German key, PDF p. 145:**
> `0,1` = The number of TOE Strength Points or Replacement Points the aircraft may transport. **`1P` = May only transport one TOE Strength Point of troops that will be paradropped.** `1/2, 2 1/2` = The number of tons of supplies the aircraft may transport.

Also on p. 145, left column: **"A plane may not carry bombs and supplies at the same time."**

So:
* **The `or` is EXCLUSIVE.** A sortie carries *either* N TOE Strength Points (or Replacement Points) of personnel *or* M tons of supplies. Never both, and never with bombs.
* **`1P` means paradrop-only troops.** The S.M. 81 Pipistrello may carry one TOE SP *only if that SP is going to jump*; it may not land troops. It may still haul 2½ tons of supplies.
* `0` (Ca 309) means it may carry no personnel at all — supplies only, ½ ton.

### AND THE BOOK GIVES THE TONS↔POINTS CONVERSION ITSELF — [34.52], PDF p. 52, verbatim

> **[34.52]** Transports are given a Transport Capacity, expressed in TOE strength points or Supply tons they can carry. Thus, a Ju52 can carry up to 2½ tons (or 20 Points) of Fuel or 1 TOE point of infantry. Transports can never transport vehicles or motorized units of any type (except motorcycle units).

**2½ tons = 20 Fuel Points → 8 Fuel Points per ton. `game/supply.py:85` already carries `TONS_PER_POINT[FUEL] = 1/8`.** The book's own worked example and the engine's [54.5] Equivalent Weights agree exactly. That is an independent cross-validation of a conversion nothing had ever checked against a second printing, and it means a transport slice needs **no new magnitude at all** to price its cargo.

---

## 3. TWO CHARTED TRANSPORT TYPES ARE MISSING FROM `data/`

**`data/logistics_rates.json::aircraft_characteristics_4_44` has 28 rows and neither of the two aircraft that ARE the transport arm is one of them.**

| missing type | chart | Range | Fuel | Transport | D R B |
|---|---|---|---|---|---|
| **Ju. 52/3m** (Junkers) | [4.44c] German, PDF p. 145 | 72 | 2 | `1 or 2 1/2` | `. . .` |
| **A-28 Hudson** (Lockheed) | [4.44A] CW, PDF p. 113 | 145 | 2 | `1 or 10 tons` | `. . .` |

Both carry **no D, R or B cell at all** — they are pure transports, the only two on any of the three charts. `data/air_reinforcements_34_86.json::_role_assignment` already says so of the Hudson ("carries NO D/R/B cell at all, only a transport tonnage, so it is `transport` — a fourth bucket game.state.AirWing does not have"), so half of this is already known to the port; the Ju 52 half is not.

**Yes, the Luftwaffe fields a transport arm here.** It arrives on the **[34.85] AXIS AIRPLANE REINFORCEMENT CHART, PDF p. 177**, which is **still untranscribed** in `data/`. Rendered at 600 dpi and read column by column; every Ju 52 cell verified:

| month | GT | Ju 52 | | month | GT | Ju 52 |
|---|---|---|---|---|---|---|
| Apr 1941 | 27–30 | 12 | | Jan 1942 | 63–66 | 12 |
| May 1941 | 31–34 | 15 | | Mar 1942 | 71–74 | 12 |
| Jul 1941 | 39–42 | 15 | | May 1942 | 79–82 | 18 |
| Oct 1941 | 51–54 | 18 | | Jun 1942 | 83–86 | 15 |
| Nov 1941 | 55–58 | 12 | | Jul 1942 | 87–90 | 12 |
| | | | | Sept 1942 | 95–98 | 18 |

**159 Ju 52/3m over the war.** Same chart also delivers 12 × SM 81 (May 1941) and 6 × SM 81 (Oct 1941).

⚠ **Chart-label defect, same class as the one `data/air_reinforcements_34_86.json::_chart_label` already records.** The chart's own printed heading on PDF p. 177 reads **`[34.85] AXIS AIRPLANE REINFORCEMENT CHART`**. `data/air_establishments.json` and `game/air.py:refit_drm` both call it `[34.87]`. One of the two is wrong; the printed heading is what I read.

---

## 4. WHAT EACH SIDE CAN ACTUALLY LIFT

### At setup ([60.32]/[60.42], `data/air_establishments.json`)

| side | type | available | ×tons | ceiling |
|---|---|---|---|---|
| **AXIS** | S.M. 81 Pipistrello | 17 | 2.5 | 42.5 t |
| | Ca 309 Ghibli | 56 | 0.5 | 28.0 t |
| | | | | **70.5 t/OpStage** |
| **CW** | Bombay Mk. I | 15 | 10 | 150 t |
| | Valentia | 3 | 5 | 15 t |
| | | | | **165 t/OpStage** |

### At full 1942 strength (setup + the two reinforcement charts, no losses)

| side | fleet | ceiling |
|---|---|---|
| **AXIS** | 159 Ju 52 + 35 SM 81 + 56 Ca 309 | **513 t/OpStage** |
| **CW** | 254 Hudson + 16 Bombay + 3 Valentia | **2,715 t/OpStage** (≈2,475 after [34.81]'s ≤10% Malta share) |

**The ten-ton Bombay is Commonwealth, and so is the ten-ton Hudson, and there are 254 of the latter.** The starved side is holding the entire heavy-lift fleet. `data/air_reinforcements_34_86.json` already carries all 254 Hudson arrivals, transcribed and eyes-verified, doing nothing.

### THE FOUR SETUP TRANSPORTS ARE ALREADY COUNTED SOMEWHERE ELSE — this is a trap

`data/air_establishments.json` fields **Bombay → `strike`** (Bomb 10), **Valentia → `strike`** (Bomb 10), **S.M. 81 → `strike`** (Bomb 11), **Ca 309 → `recon`**. All four already contribute Air Points to another bucket. Combined with the German key's *"A plane may not carry bombs and supplies at the same time"* and [39.19]'s one-mission-per-plane-per-OpStage, **a `transport` bucket must MOVE these aeroplanes out of `strike`/`recon`, never add them.** Only the Ju 52 and the Hudson are net additions, and neither is in the engine.

---

## 5. MATERIALITY, HONESTLY

### The measured baseline (`scratchpad/15.53-driver/gate_c.after1553.json`, 30 seeds, 333 OpStages)

| | Axis | Allied |
|---|---|---|
| truck last mile | **15,493 t/campaign = 46.5 t/OpStage** | **10,544 t = 31.7 t/OpStage** |
| landed at the quay | 840,863 t = 2,525 t/OpStage | 0 (sea 456,000 t) |
| **total supply consumed** | **35,435 t = 106.4 t/OpStage** | **178,614 t = 536.4 t/OpStage** |
| — of which STORES | 70.4 t/OpS | 444.0 t/OpS |
| — WATER | 16.2 | 41.8 |
| — AMMO | 13.1 | 29.3 |
| — FUEL | 6.6 | 21.3 |

### Sustained airlift, after the refit governor

[38.32] puts refit in the Tactical Maintenance Segment — **one attempt per squadron per Operations Stage**. In steady state (everything refitted flies, everything that flies goes unfit) the sustained sortie fraction equals the mean refit percentage off the [38.37] table:
* Commonwealth (DRM 0, d6 → 100/80/70/60/50/40) = **66.7 %**
* Axis worked by an Italian SGSU (DRM +2 → 70/60/50/40/40/33) = **48.8 %** — and `game/air.py:refit_drm` documents that all 39 campaign Axis SGSUs are Italian, so the Luftwaffe's Ju 52s would refit at the Italian rate under the current counter gap.

| unit of force | sustained t/OpStage | vs its side's truck last mile | vs its side's total consumption |
|---|---|---|---|
| 1 CW squadron (24 Hudsons, from Jul 1941 [35.23]) | **160** | **5.0×** | 30 % |
| 2 CW squadrons (48 Hudsons) | **320** | **10.1×** | 60 % |
| CW setup fleet (15 Bombay + 3 Valentia) | **110** | **3.5×** | 21 % |
| 1 Italian squadriglia (12 Ju 52) | **14.6** | 0.31× | 14 % |
| 5 squadriglie (60 Ju 52) | **73** | **1.6×** | 69 % |
| Axis setup fleet (17 SM 81 + 56 Ca 309) | **34** | 0.74× | 32 % |

**Even the smallest credible commitment on either side is the same order of magnitude as that side's entire truck last mile.** For the Commonwealth it is 3–10× it *from Game-Turn 1*, before a single Hudson arrives.

### The real deflators, stated against my own case

1. **[42.46] bars fuel and water from the airdrop channel.** The engine's binding scarcities are exactly those: the seed-1 order-rejection census shows Allied `no fuel for this move` 3,583 and `out of water … vehicles may not move (52.51)` 1,748; Axis `out of water` 913. Airdrop can relieve neither. It relieves AMMO (13–29 t/OpS) and STORES (70–444 t/OpS) — stores being by far the largest tonnage in the game.
2. **[36.17] land units may not use airfield supply dumps.** A [42.3] transport lands at an air facility, and `game/supply.py:reachable_supplies` already makes air dumps invisible to every land unit. [42.35] is the release valve — the cargo is *assigned to a dump or specific units* in the Organization Phase — but the delivery path is a design question, not a free win.
3. **WATER is on the ½-CPA trace, not on tonnage.** Per the S8 finding, water is drawn by trace from any friendly dump within half CPA. Flying water forward relieves the water gate only if it lands in a *land* dump inside somebody's trace radius. Fuel, ammo and stores are in-hex (S5/S6/S7) and are relieved directly.
4. **SGSU capacity is the hard ceiling and it is Commonwealth-tight.** Measured on `scenario.campaign(7)`: **39 Axis SGSUs (×12 = 468 planes) and 14 Allied SGSUs (×24 from Jul 1941 = 336 planes)**, with no SGSU reinforcement transcribed for either side. The Commonwealth's *entire* mainland air force is capped at 336 aeroplanes; 254 Hudsons would consume 11 of its 14 squadrons. So the 2,715 t/OpStage ceiling is unreachable and the realistic figure is the 1–2 squadron row of the table above. **This is the honest cut, and it still leaves 5–10×.**
5. **Fuel cost is negligible.** [38.21]/[34.17]: Ju 52 and Hudson both cost 2 Fuel Points to fly. A Hudson carrying 10 tons of fuel delivers 80 Fuel Points for 2 — net +78. The channel is enormously net-positive in the book's own economy; fuel is not a governor.
6. **The geography is already seeded and it is forward.** `scenario.campaign(7)` puts **55 air facilities** on the map — Axis 8 airfields at level 6 plus 17 strips, Allied 11 airfields plus 14 strips — including `C4807-Tobruk` (strip, level 1), `C4507-El Adem` (airfield, level 6), `C4414-Gambut`, `C4131-Sidi Barrani`, `D3714-Mersa Matruh` (airfield 6). **The besieged-garrison scenario has a real airstrip in the real Tobruk hex (14,66).** Capacity Level caps concentration (a strip holds one squadron) but the destinations exist.
7. **Range is not a limit, and the brief's range concern is real but small.** Bombay 88, Hudson 145, Ju 52 72, SM 81 90, Ca 309 84 hexes, doubled under [42.32b]/[42.13]. Those cover the theatre. **The hook can be opened without a range gate** — but `AirMission` carrying no origin means the engine could not *check* one even if it wanted to, and a transport mission is the first mission kind whose ORIGIN is load-bearing ([42.32] cargo must start co-located; [42.42] drops must start from a friendly air facility). I did not build a range gate.

---

## 6. RECOMMENDATION

**Build it — but not before the air-to-air half, and here is why that is not timidity.**

[34.53], verbatim off PDF p. 52:
> Transports may never initiate air-to-air combat. They receive no benefit from formation flying, as do bombers. **Transports are relatively helpless in the air and must have heavy CAP to insure their arrival.**

A transport channel built today flies **unopposed**: ordered CAP is deferred by this slice's own reasoning, [40.27] interception is deferred with it, and no flak resolver touches a transport. Given the measured size — 5–10× the Commonwealth truck last mile — **an unopposed air bridge would be the single largest unfaithful lever ever added to this engine, and it would favour the Commonwealth, the side the owner wants helped.** That makes it both the most attractive and the most dangerous thing on the board. It is exactly the shape of debt that has bitten this project before.

Two viable orderings:

* **PREFERRED — build it in the slice immediately after ordered CAP.** [42.3]/[42.4] is then a genuinely faithful second last mile, opposed by the same interception the book puts on the path of flight, and the CAP restructuring (lifting the Land Support Air Phase out of `_combat` per [33] IV.F) is a prerequisite this slice already identified for its own reasons. Two slices, one restructuring.
* **ACCEPTABLE — build it now, sized through the existing `_air_superiority` gate.** Every other air mission in the engine is already scaled by that abstraction; applying it uniformly to transport is *consistency with an existing flagged proxy*, not a new invention. Cheaper, and it prevents the unopposed-bridge failure mode. Flag it as the stand-in for [34.53]'s CAP requirement and [40.27]'s interception, and retire it when CAP lands.

**Do NOT park it.** The arithmetic is the rare case where the standing "paying a debt moves nothing" prior is wrong, and predicting that in advance was the point of this survey: **this debt moves the campaign, by 5–10× on the axis the project has established governs everything.**

### Prerequisites the transport slice needs, in order

1. **This slice's Policy air-mission hook and mission-kind whitelist.** A transport mission is authored by a staff seat or it is authored by nobody; and `engine.py:3004-3017`'s silent `else`-less drop is exactly the hole a `kind: "transport"` order would fall through.
2. **Transcribe the two missing chart rows** — Ju. 52/3m (PDF p. 145) and A-28 Hudson (PDF p. 113) — into `data/logistics_rates.json::aircraft_characteristics_4_44`. Both are read and verified above; neither exists in the file.
3. **Transcribe [34.85] AXIS AIRPLANE REINFORCEMENT CHART (PDF p. 177).** It is the only source of the 159 Ju 52s, and `data/air_reinforcements_34_86.json::_what_is_not_wired` already states the two schedules "land together or neither does" — this is the second one, and it unblocks the mainland ninety per cent of the Commonwealth schedule at the same time.
4. **A fourth `AirWing` bucket, denominated in TONS and TOE Strength Points, not Air Points.** [42.31]'s rating is not TacAir and not Bombload; `air.points_of_planes` does not apply. This is also the cleanest argument for the crux the brief asks you to settle first: **keep the [39.19] ledger in PLANES.** A points ledger cannot express a transport at all, because a transport has no points.

### Owner rulings this survey raises

1. **[42.48]'s "no unit may be airdropped more than once a month (every 12 Operations Stages)" — does it bind SUPPLY drops?** The sentence sits in the paratroop section and its subject reads naturally as an airborne *unit* recovering between jumps. But read against the receiving hex it would cap a besieged garrison at one resupply a month, which guts the channel. **Natural reading: it binds jumping units only. Flagged, not decided.**
2. **[42.35] delivery path vs [36.17].** Air-transported supplies land at an air facility whose dump land units may not use. [42.35] permits assignment "to a dump or specific units" in the Organization Phase. Which dump, and does [54.11]'s one-dump-per-hex bite? A build question, but it decides whether the transport half is materially different from the airdrop half.
3. **The [34.85]/[34.87] chart label.** The printed heading is `[34.85]`; `data/air_establishments.json` and `game/air.py` say `[34.87]`. Same off-by-N class the Commonwealth file already records for `[34.84]`/`[34.86]`.

### One faithfulness note, flagged and NOT acted on

**The book's ten-ton Hudson is historically absurd** (a real A-28 carried ~1½ tons of freight), and it prints the same ten tons for the Bombay. **Transcribe, never invent — the number stands.** Recording it only so that when 254 ten-ton freighters visibly reshape the 1942 Commonwealth campaign, nobody mistakes a printed number for a transcription error and "fixes" it.

---

## FILES

* Survey basis, read-only: `/home/eve/Projects/tcfnatdw/scratchpad/port/transcriptions/39-mission-assignment.md` (thorough; its §4 [39.5] chart lists Airdrop/Transport under *Non-Combat*, confirming both are Land Support missions)
* Scan pages rendered and read: PDF **60** (42.3/42.4), **52** (34.52), **113** ([4.44A] CW bombers/transports + key), **144** ([4.44b] Italian + key), **145** ([4.44c] German + key), **177** ([34.85] Axis reinforcements). Crops under `/tmp/air42/`.
* Data verified: `/home/eve/Projects/tcfnatdw/data/logistics_rates.json`, `/home/eve/Projects/tcfnatdw/data/air_establishments.json`, `/home/eve/Projects/tcfnatdw/data/air_reinforcements_34_86.json`
* Engine read: `/home/eve/Projects/tcfnatdw/game/supply.py:85` (`TONS_PER_POINT`), `/home/eve/Projects/tcfnatdw/game/air.py` (refit/squadron/SGSU), `/home/eve/Projects/tcfnatdw/game/state.py:422` (`AirWing`), `:476` (`AirMission`)
* Measurements: `/home/eve/Projects/tcfnatdw/scratchpad/15.53-driver/gate_c.after1553.json`; setup facility/SGSU counts from `scenario.campaign(7)` with `PYTHONDONTWRITEBYTECODE=1` after clearing `game/__pycache__` and `tests/__pycache__`.

No files were modified. No engine code written.
