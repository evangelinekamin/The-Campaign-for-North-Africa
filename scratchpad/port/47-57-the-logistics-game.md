# Chapters 47–57 — The Logistics Game: rulebook-vs-engine audit

Audited 2026-07-14 against `game/*.py` @ b99e460, `data/*.json`, and a full 111-turn campaign run
(seed 1941, `CampaignAxisPolicy` v `CampaignCommonwealthPolicy`, 78,761 events).
**Every chart in this slice was re-read from the original scan** (`tmp/The Campaign for North
Africa.pdf`, PDF pages 108–110 = charts-booklet pages 13–14), not from `docs/rules/90`.

---

## 0. BOTTOM LINE

Three things you should know before reading anything else.

**(a) The 54.17 OCR is NOT wrong. The 1979 PRINTING is wrong.** I rendered the page at 600 dpi. The
printed chart really does read `0 33 0 10 20 33 50 75 100 33 100`, values correctly aligned under
their die headers. `docs/rules/90` and `data/logistics_rates.json` transcribed it faithfully. The two
bad cells are a paste-up error in the original — and the correction is *forced*, because the two
corrupt cells are exactly the two whose values are pinned by their neighbours. Corrected table in §4.1.
**Do not "fix the OCR" — there is nothing to fix. Fix the DATA, and say why.**

**(b) The charts are in excellent shape. The ENGINE's use of them is not.** I diffed every number:
52.7, 54.12, 54.2, 54.5, 55.3 (incl. the tonnage column `docs/rules/90` lost), 50.2 (never OCR'd at
all), 58.5 (never OCR'd at all) — `data/logistics_rates.json` matches the scan **cell for cell, with
zero errors**. What is wrong is downstream: the port tonnage gate is applied **per commodity instead
of as one shared tonnage budget (4× breach)**; three of the campaign's port Efficiency Levels are
invented; the 54.12 Non-Dump row is transcribed and never read; and 29.35 (water *doubles* in hot
weather) is charted in the rulebook while `logistics_rates.json:113` says "UNSPECIFIED… charts no
number" and the engine proxies `+1`.

**(c) The abstract game (§32/§47) is still load-bearing in four places, and one of them is the
supply trace itself.** `game/supply.py:229` — `budget = unit.cpa / 2` — is rule **32.16**, the
abstract game's supply range. In the Logistics Game there is no supply range: 49.15/49.16, 50.15 and
51.15 all say supply must be **in the hex**. Everything downstream of that line is playing the
abstract game with full-game magnitudes.

And the campaign's measured fuel economy says the logistics game is not biting:

| Fuel, whole campaign (seed 1941) | Points |
|---|---|
| Landed (Axis convoy + CW rail + Tobruk lanes) | **3,106,208** |
| Evaporated (49.3) | **2,272,976  (73%)** |
| Burnt by lorries (49.18) | 389,465  (13%) |
| **Burnt by the two armies moving (49.13)** | **23,504  (0.8%)** |
| …of which the whole Panzerarmee, 111 turns | **1,419** |

Evaporation is **1,600×** the Axis army's entire fuel consumption. Fuel is not scarce; it is merely
*leaky*. That is not the campaign the designer wrote.

---

## 1. THE §47 / §32 TRAP — ABSTRACT-GAME RULES ILLEGITIMATELY IN FORCE

Chapter 47 is **N/A in its entirety**: it modifies §32, and §32's own General Rule says *"Players will
not receive any trucks but rather receive Motorization Points."* Abstract = points, no lorries. Full =
lorries, no points. 64.65 confirms they are the alternative package (*"use the rules in the appropriate
section(s) (32.0, 47.0, 58.0)"* — that is the **abstracted** set).

So the useful output of chapter 47 is the list of things that must **not** be here. Four are:

| # | Abstract rule in force | Where | Why it is WRONG | Full-game replacement |
|---|---|---|---|---|
| **A1** | **32.16 — supply traced within ½ CPA** | `game/supply.py:229` (`budget = unit.cpa / 2`), used by `plan_draw` → every fuel draw (`engine.py:1194`), ammo draw (`engine.py:2690`), stores (`engine.py:830`), water (`engine.py:895`), pasta (`engine.py:880`) | The Logistics Game has **no supply range**. 49.15: *"For fuel to be consumed, it must be present in the same hex with the consuming unit."* 49.16: *"a unit consumes fuel in the hex in which it begins Movement… It may draw fuel from any source in that hex."* 50.15: *"Ammunition is consumed only if present in the hex."* 51.15: *"Stores must be present in the hex to be used."* | Supply **in the hex**: the unit's own 49.14 Fuel Capacity, its **first-line trucks** (53.11 — the whole point of them), or a dump on the hex. |
| **A2** | **32.13 — captured supplies "used immediately and freely"** | `engine.py:1734` `_capture_dumps` (docstring quotes 32.13 verbatim), `apply.py:125` flips 100% of every commodity | The full game taxes capture: **50.16** — only **⅓ (round up)** of captured Ammo is usable, *the rest are lost*; **51.16** — only **50%** of captured Stores. Only Fuel is free (49.19: *"Fuel is non-denominational"*). Water is silent. | Destroy ⅔ of ammo and ½ of stores at the moment of capture. |
| **A3** | **32.32/32.51 — 30 Motorization Points to move a dump** | `game/supply.py:310-312`, `engine.py:1551` `_organization`, `engine.py:1629` `_supply_movement` | There **are no Motorization Points in the full game**. `_organization`'s own docstring states the contradiction and then rides straight through it: *"in the abstract game you are issued MP and no trucks, in the full Logistics Game trucks and no MP, and 32.51 is the exchange rate between them."* 32.51 is **not an exchange rate** — it is a note *inside the abstract rules* telling you to treat the MPs you were issued *instead of* trucks as medium truck points. Charging 30 Medium Truck Points is a hybrid rule that appears nowhere in the book. | **53.12 + 54.11/54.35**: a truck convoy LOADS (53.24), DRIVES at convoy CPA 30/40 (53.22), UNLOADS, and the load *is* a dump where it stops. No escort, no reservation, no thirty. |
| **A4** | **32.3 / 32.33 / 32.58A — the escorted teleporting dump** | `engine.py:1629` (`must end stacked with a friendly combat unit (32.33)`), `supply.py:103-104` (`SUPPLY_CPA = 15`, `SUPPLY_MOVE_FUEL = 1` ← 32.24) | In the full game a **dump does not move**. Supply moves; dumps are places. A depot 15 CP behind the spearhead every OpStage, for 1 Fuel Point, is the abstract game's counter-shuffle. | Same as A3 — the truck convoy. |

**A1 is the one that matters.** It is why the armies can eat without a functioning haulage chain, why
the 54.16 "dump network" is decorative, and why first-line trucks (`Unit.is_first_line_truck`, declared
in `state.py:66`, used **only** for stacking exclusion and a water class test) are a dead flag. It is
also, by a wide margin, the biggest job on this list.

**Chapter 47, rule by rule** — all N/A (abstract-only). Recorded so nothing is silently skipped:
47.11–47.14 (abstract supply units + the 180-Fuel/40-Ammo Depot counter), 47.21–47.23 (abstract air
ammo/fuel), 47.31–47.35 (moving depots by MP/rail/coastal/air), 47.41–47.42 (Depot availability),
47.51–47.53 (Motorization Points), 47.61–47.65 (simplified naval convoys), 47.7, 47.81–47.82 (printed
in the book as "42.81/42.82" — a numbering typo in the original). **Status for every one: N/A —
alternative ruleset. Campaign-critical: NO, except as the leak list above.**

---

## 2. RULE-BY-RULE

### Chapter 48 — SEQUENCE OF PLAY (Logistics Game)

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| 48 I | Initiative Determination, once per Game-Turn | **DONE** | `engine.py:137` `_initiative` inside the GT loop | YES |
| 48 II | Strategic Air Planning Stage (Air Game only) | **N/A / PARTIAL** | Air is played at the 32.0/58.0 abstract grain; `state.air_missions` is a static schedule | NO |
| 48 III | **Naval Convoy Stage** — A: roll 56.4/56.5 tonnage and plan lanes **one Game-Turn in advance**; B: convoy bombing | **PARTIAL** | No Convoy Stage exists. Convoy cargo is rolled **at scenario construction** (`scenario.py:655` `_campaign_axis_cargo`, seeded RNG), not one GT ahead; bombing is a static `InterdictionOrder` schedule | MAYBE — removes the Axis's central planning decision |
| 48 IV | **Stores Expenditure Stage**: distribute/expend Stores; **"Players also adjust fuel and water storage levels for any losses as a result of spillage or evaporation"** | **DONE** | `engine.py:749` `_stores_setup` → `_evaporate(6%)` then `_stores_stage` for both sides, once per GT (`engine.py:139`) | YES |
| 48 V.B | Weather; hot-weather evaporation applied here | **DONE** | `engine.py:142-145`; `_water_body` charges the +5% slice right after `_weather` (29.34: *"done during the Weather Determination Phase"*) | YES |
| 48 V.C.1 | Water Distribution Segment, **per OpStage** | **DONE** | `engine.py:763` `_water_body` → `_water_distribution`, inside the 3-stage loop | YES |
| 48 V.C.3 | Attrition Segment | **PARTIAL** | Attrition is folded into the shortfall handlers (`engine.py:850`, `:906`) rather than a distinct segment. Timing proxy, no magnitude effect | NO |
| 48 V.C.4 | Construction Segment | **DONE** | `engine.py:1960` `_construction`, before movement | YES |
| **48 V.C.6** | **Supply Distribution Segment** — *"Supplies in the same hex as land units may be redistributed at this time… Trucks may be loaded/unloaded"* (and per **6.3** this is the **0-CP** window) | **MISSING** | No such segment anywhere. `grep -n "Supply Distribution" game/` → nothing | **YES** — it is the free load/unload window, and the only beat at which first-line trucks are topped up |
| **48 V.C.7** | **Tactical Shipping Segment** — inter-port transport of cargo | **MISSING** | Cited in `_naval_convoys`'s docstring (`engine.py:640`) but not implemented. No coastal ships exist (see 56.3) | YES for the Axis |
| **48 V.D** | Naval Convoy Arrival Phase — **in every Operations Stage** | **WRONG** | `engine.py:149-150`: `if stage == 1: … _naval_convoys(...)`. Convoys land **once per GAME-TURN**. Two consequences: (i) a port's *per-OpStage* capacity is exercised ⅓ as often as the book allows; (ii) 55.18 regen fires once per GT instead of three times (`_port_regen` is called **only** from `_naval_convoys`, `engine.py:724`) | **YES** |
| 48 V.E | Commonwealth Fleet Phase | **PARTIAL** | `engine.py:1121` `_naval_bombardment` | NO |
| 48 V.G/H | Reserve Designation; Movement & Combat | **DONE** | `engine.py:154-172` | YES |
| **48 V.J** | **Truck Convoy Movement Phase** — 2nd/3rd-line trucks, POWs and Guards | **PARTIAL** | `engine.py:1812` `_truck_convoys` ✓. POWs/Guards do not exist (`grep -i prisoner game/` → nothing) | YES (trucks); NO (POWs) |
| 48 V.K | Commonwealth Movement Phase — **rail movement of land units** (8.9) | **MISSING** | The railway hauls freight only (`engine.py:582`); no unit ever rides a train | MAYBE — the Eighth Army walks to Alamein |
| 48 V.L | Repair Phase | **DONE** | `engine.py:1510` | NO |
| 48 VI–VII | Second and Third Operations Stages | **DONE** | `engine.py:140` `for stage in (1, 2, 3)` | YES |

### Chapter 49 — FUEL

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| 49.11 | Fuel Point = 250 lb / 35 gal | **DONE** (definitional) | `logistics_rates.json:6-7` | NO |
| 49.12 | Every vehicle burns fuel moving; HQs w/ non-parenthesised TOE and all gun-class included; **not** motorcycles, not towing | **PARTIAL** | `supply.py:117-124` `fuel_rate` returns 0 for `NON_MOT_CLASSES`. But `_FUEL_RATE_PROXY` (`logistics_rates.json:52`) gives **MOTORCYCLE: 1** — the chart says motorcycles burn nothing | NO (tiny) |
| **49.13** | **rate × ceil(CP/5) × TOE Strength Points**, movement only; combat CP burn no fuel | **DONE** | `supply.py:127-137` `fuel_cost` — exactly the law, including the ×TOE factor. Charged per move at `engine.py:1184` `_draw_move_fuel` | YES |
| 49.14 | **Fuel capacity rating = CPA × ⅕ × rate** — the fuel in the unit's own tanks | **MISSING** | `Unit` has no fuel pool (`state.py:32-100`). A unit draws from a *dump* at move time via the 32.16 trace. **This is A1's other half** | **YES** |
| 49.15 | Fuel must be **present in the same hex** | **WRONG** | `supply.py:229` — traced at ½ CPA instead. See **A1** | **YES** |
| 49.16 | Draw in the hex the move begins from; no CP to gas up; drawing again on a second move | **PARTIAL** | `_draw_move_fuel` charges per move ✓ and costs no CP ✓, but "in the hex" is the ½-CPA trace ✗ | YES |
| 49.17 | **Siphoning** — 3 CP to each unit, transfer fuel between co-located units (incl. from abandoned/broken-down **enemy** vehicles) | **MISSING** | `grep -rn siphon game/` → only prose in `campaign_policy.py` comments | NO (no per-unit fuel to siphon; blocked behind 49.14) |
| 49.18 | Trucks burn fuel moving and may burn their **cargo** fuel | **DONE** | `supply.py:280-286` `truck_move_fuel` = factor × ceil(CP/5) × Truck Points, drawn from cargo (`engine.py:1893`). Measured: lorries burn **389,465** of the **1,641,759** fuel they lift — 24%, right in the rule's *"possible for a truck to consume half of its cargo"* band | YES |
| 49.19 | Fuel is non-denominational — usable by either player | **DONE** | `engine.py:1801` capture flips fuel intact (this commodity only — see A2) | YES |
| 49.2 | Fuel moves by truck/train/plane; never by tanks; never by walking infantry | **DONE** | Only `TruckFormation` and the rail convoy carry fuel | YES |
| **49.3** | **6% of ALL fuel on the map per Game-Turn** (not convoys at sea), at the Stores Expenditure Stage; **+5% in hot weather**; **Commonwealth 9% from Sept 1940 to the last GT of Aug 1941** | **PARTIAL / WRONG** | 6% ✓ once per GT (`engine.py:758`), +5% ✓ per hot stage (`engine.py:772`), floor ✓ (`engine.py:820`). **Three defects:** (1) **the 9% Commonwealth rate does not exist** — `logistics_rates.json:48` transcribes it and **nothing reads it** (`grep commonwealth_penalty_percent game/` → nothing); `_evaporate` has no side split at all. The campaign opens Sept 1940, so this is live for ~48 GT. (2) **Truck cargo does not evaporate** — `engine.py:816` iterates `r.state.supplies` only; **29.34** is explicit: *"This includes water and fuel in dumps **as well as in trucks**."* (3) `base=True` dumps are skipped, which is right for wells/pipelines (52.44) but also exempts the rule-57 Delta base — harmless only because it is infinite | **YES** |

### Chapter 50 — AMMUNITION

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| 50.11 | Ammo Point ≈ 4 tons | **DONE** | `supply.py:77` `TONS_PER_POINT[AMMO] = 4.0` | YES |
| 50.12 | Barrage/anti-armour/AA/assault consume ammo. A unit **without ammo** is useless: it may not even defend, **surrenders** if fired on in an EZOC, and **has no ZOC** | **PARTIAL** | Surrender ✓ (`engine.py:2674` `_defenders_capitulate`, 15.15). **"Units without ammunition have NO ZOC" is not modelled** (`game/zoc.py` never consults supply) | MAYBE |
| 50.13 | A multi-role unit uses the rate of the function chosen | **DONE** | `supply.py:147` `ammo_cost(activity=…)` | YES |
| **50.14** | Ammo = **rate × TOE points committed**, regardless of actual barrage points | **DONE** | `supply.py:154` `AMMO_RATE[activity] * max(1, unit.strength)` | YES |
| 50.15 | Ammo consumed **only if present in the hex**; convoy ammo unusable until off-loaded | **PARTIAL / WRONG** | Convoy-ammo-is-locked ✓ (a `TruckFormation`'s pools are not a `plan_draw` source). "In the hex" ✗ — ½-CPA trace (**A1**) | YES |
| **50.16** | **Only ⅓ (round up) of captured Ammo is usable; the rest are LOST.** Same on recapture | **MISSING** | `engine.py:1801` + `apply.py:125` transfer **100%**. **Measured, seed 1941: the Axis captured 3,275 Ammo Points — 3× its entire ammunition expenditure for the whole war (1,078).** It should have got 1,092 and burnt 2,183 | **YES** |
| 50.17 | Ammo by truck/air; airdroppable; usable in first-line trucks and dumps | **PARTIAL** | Trucks ✓; first-line trucks and airdrop ✗ | NO |
| 50.2 | Ammunition Consumption Rates Chart | **PARTIAL** — see §4.4 | Rates ✓ (4/3/2). **The chart's class restriction on close assault is ignored** | MAYBE |

### Chapter 51 — STORES

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| **51.11** | 4 Stores per TOE Strength Point **per Game-Turn** | **DONE** | `supply.py:185-190`; `logistics_data.stores_rates()`; charged once per GT at `engine.py:758` | YES |
| 51.12 | Prisoners: 1 Stores per 5 Prisoner Points per **OpStage**; supplied **before all other units**; may draw from the **nearest dump at any distance** | **MISSING** | No POWs in the engine (`grep -i prisoner game/` → nothing) | NO (28.0 not modelled) |
| 51.13 | **HQ and engineer units require only ONE Stores Point per Game-Turn** (flat) | **WRONG** | `supply.py:189-190` charges `rate × strength` — i.e. **1 per TOE**, not 1 flat. Worse: the `combat`/`noncombat` split keys off `is_combat`, and engineers are combat units, so a 3-TOE engineer battalion pays **12**, not **1** | NO (small magnitude, but it is a wrong number) |
| 51.14 | Stores expended in construction (24.0) | **DONE** | `engine.py:2020` (rail: 1 Store/hex), `engine.py:2068` (dump: 20 Stores) | YES |
| 51.15 | 1 Stores = 1 ton; truckable/airdroppable; **must be present in the hex**; convoy stores unusable | **PARTIAL / WRONG** | Tonnage ✓ (`supply.py:77`). "In the hex" ✗ (**A1**) | YES |
| **51.16** | **Only 50% of captured Stores may be used; the rest are lost** | **MISSING** | `apply.py:125` transfers 100%. Measured: Axis captured **8,188** Stores (should have had 4,094) | **YES** |
| 51.17 | Guard points: 2 Stores/GT; may draw from the nearest dump | **MISSING** | No Guards | NO |
| 51.21 | 1 Disorganization Point per Game-Turn of stores shortfall | **DONE** | `apply.py` `STORES_SHORTFALL` → `disorganization + 1` | YES |
| 51.22 | Every **2 consecutive** GT without stores: lose 2% of TOE (nearest whole), progressive/cumulative (2%@2, 4%@4…). **Infantry-type TOE only** | **DONE** | `engine.py:864-869`; `supply.is_infantry` exempts guns/tanks | YES |
| 51.23 | **Half rations** — cut 4→2, at the cost of never voluntarily exceeding CPA and never voluntarily entering an EZOC | **MISSING** | `grep -i "half.ration" game/` → nothing | MAYBE — it is the player's answer to a stores crisis, and he has no other |

### Chapter 52 — WATER

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| 52.11 | Water is in **wells only** — major cities, villages, birs; plus oases. Tripoli/Tunis boxes unlimited | **DONE** | `game/wells.py:wells()`, `data/wells.json` (11 major cities, 49 villages, 7 birs, 3 oases) | YES |
| 52.12 | Yields + depletion from the 52.7 table | **PARTIAL** | `wells.py:_table_yield` seeds a **static finite pool** (village 4,800; bir 2,400) as a flagged proxy for the draw-and-deplete cycle | YES |
| **52.13** | Move onto a well, **spend 1 CP**, roll a die, read the 52.7 column. Major cities/oases: no die, unlimited | **MISSING** | No draw die, no CP. Wells are continuous dumps read through the ½-CPA trace. *(6.3 confirms the cost: "Draw Water other than during an Organization Phase — 1". Drawing in the Organization Phase is 0 CP, and the engine draws there, so the **CP** half is right by accident.)* | MAYBE |
| 52.14 | Depletion is secret until an enemy tries to draw | **MISSING** | No depletion | NO |
| 52.15 | **Rainstorms replenish every depleted well on the affected map section** | **MISSING** | No depletion to undo. Note: its absence makes the finite pool *more* conservative, not less | MAYBE |
| 52.16 / 52.17 / 52.8 | Poison a well (1 CP, roll a 1); sweeten it (5 CP, roll 1–3) | **MISSING** | `grep -i poison game/` → nothing. 6.3 charts both CP costs (1 / 5) | MAYBE — a cheap, permanent way to deny a desert axis, and neither AI has it |
| 52.21–52.24 | **Player-built pipelines** — from major-city wells only; any length; 1 Construction Phase + **10 Stores** per hex; 1 hex/OpStage. CW may treat any operating RR hex as a pipeline; **Axis may not use the Barce–Benghazi line** | **PARTIAL** | The **standing** CW RR-as-pipeline is seeded (`wells.py:pipeline`, Cairo→Alexandria→Mersa Matruh, unlimited, `base=True`) ✓ and it is Commonwealth-only ✓. **Player-built pipelines are MISSING** — the Axis can never extend water forward, which is exactly the constraint 52.2 exists to let him relieve | **YES for the Axis** |
| 52.25 | Pipelines destroyable by raiders / enemy presence / strafing; draw only from the farthest connected hex | **MISSING** | `wells.py` pipeline units are `base=True` and indestructible | MAYBE |
| 52.3 | **Oases** — unlimited water **and unlimited Stores**; never depleted, never poisoned; no pipelines from them | **PARTIAL** | Water ✓ (`wells._pool` → unlimited). **The Stores half is MISSING** — `wells.py:wells()` hard-sets `stores=0`. An oasis should feed a garrison indefinitely | MAYBE |
| 52.41 | Infantry battalion/company: **1 Water/OpStage regardless of TOE** | **DONE** | `supply.py:199` | YES |
| **52.42** | Each TOE point of **Vehicle** *or* **Truck Point**: 1 Water/OpStage, **if it uses any of its CPA** | **PARTIAL / WRONG** | Vehicles ✓ per TOE (`supply.py:199`). **Two errors:** (1) the *"if it uses any of its CPA"* condition is ignored — every on-map unit drinks every stage, moving or not (over-charge); (2) **Truck Points never drink at all** — `_water_distribution` (`engine.py:892`) iterates `state.living(side)` (Units), never `state.trucks`. The Axis's 215 and the CW's 195 Truck Points cost **zero water for 111 turns** (under-charge) | YES |
| **52.43** | Hot weather requires additional water — and **29.35 charts it: *"water requirements for all units are DOUBLED"*** | **WRONG** | `supply.py:200` — `base + (1 if hot else 0)`. `logistics_rates.json:113` asserts *"UNSPECIFIED — 52.43… charts no number"*. **That is false.** A 6-TOE tank battalion pays **7** where the book says **12**; a 10-TOE division pays 11 where the book says 20. Only 1-TOE infantry is right, by luck | **YES** |
| 52.44 | Water evaporates per 49.3 — **except water in wells and pipelines** | **DONE** | `engine.py:817` skips `base=True`; wells and pipeline hexes are `base=True` (`wells.py`). 29.34 adds "or oases" — also `base`. ✓ **But truck-borne water is not evaporated either** — see 49.3 defect (2) | YES |
| 52.45 | Water may be **transported by trucks** at the 54.2 rates | **MISSING** | The 54.2 Water column (L 40 / M 100 / H 200) is loaded into `supply.TRUCK_CHARS` and **never used**: measured over the whole campaign the relay hauled **0 Water Points**. Water reaches only what stands within ½ CPA of a well | **YES** — this is the *only* way an army in the deep desert drinks |
| 52.51 | Vehicles without water may not move / close-assault offensively; defend at half | **MISSING** | `engine.py:906` `_water_shortfall` applies attrition only | MAYBE |
| 52.52 | Infantry without water may not exceed CPA, no offensive close assault, defend at half | **MISSING** | as above | MAYBE |
| 52.53 | 1 TOE lost per consecutive OpStage after the first without water | **DONE** | `engine.py:914-917` | YES |
| **52.6** | **The Italian Pasta Rule** — +1 Water per Italian battalion at Stores distribution; denial caps CPA and disorganizes a ≤−10 cohesion battalion as if at −26; **restored on later receipt** | **PARTIAL** | `engine.py:870` `_pasta_point` ✓ including the −26 collapse. **The restoration half ("As soon as such units get their Pasta Point, they regain the original Cohesion Level") is MISSING** — the collapse is permanent | YES |
| 52.7 | Water Availability Table | **DONE — verified against the scan** | see §4.2 | YES |

### Chapter 53 — TRUCKS AND TRANSPORT

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| 53.11 | **First-line trucks** — attached to the parent unit, carry its men and supplies, no counter; detachable in the Organization Phase | **MISSING** | `Unit.is_first_line_truck` exists (`state.py:66`) but is read **only** by `stacking.py:33` (9.29 exclusion) and `supply.py:172` (water class). It carries **no cargo**. This is the vehicle by which supply is *in the hex* — i.e. the missing half of **A1** | **YES** |
| 53.12 | Second-line trucks — dump ↔ combat unit; counters; move in the Truck Convoy Segment | **DONE** | `state.TruckFormation`, `engine.py:1812` | YES |
| 53.13 | Third-line trucks — port ↔ forward dump; identical to 2nd line but for the name | **DONE** | `TruckFormation.line` is a label only, exactly as 53.13 says | YES |
| 53.14 | The three-tier relay (recommendation, not a rule) | **PARTIAL** | `campaign_policy.py:1126` `campaign_truck_orders` runs a 2-tier relay (port → staging dumps → forward). The 1st-line tier does not exist | YES |
| 53.21 | Convoy trucks move only in the Truck Convoy Movement Segment | **DONE** | `engine.py:1812`, called at `engine.py:174` after both sides' turns | YES |
| **53.22** | Convoy CPA: heavy/medium **30**, light **40**. **May never exceed it** — doing so is an instant breakdown (21.0) | **DONE** | `supply.py:264-267` reads the 54.2 "Supplies" CPA column; `engine.py:1880` `_truck_move` bounds by `reachable_truck_moves`. *(The breakdown-on-overrun branch is unreachable, which is fine.)* | YES |
| 53.23 | A unit at cohesion ≤ −5 may not detach first-line trucks; 2nd/3rd-line trucks attached as 1st-line take the parent's cohesion | **MISSING** | No first-line trucks | NO |
| **53.24** | **There is a CP cost to load/off-load** (6.3: **2 CP** outside the Organization Phase, **0** inside it). A truck at its full extended CPA **may not off-load** if that would push it over | **MISSING** | `_truck_load` (`engine.py:1860`) and `_truck_unload` (`engine.py:1900`) emit **no `CP_EXPENDED`**. A convoy may drive its **full 30 CP** and still unload — 32 CP against a 30 CPA. Faithful: 28 CP of driving if you intend to unload the same stage, or unload free next Organization Phase (which does not exist — see 48 V.C.6). Inflates lorry reach ~7% and, more importantly, removes the *decision* | MAYBE |
| **53.25** | **No leapfrogging** — cargo carries the CP of the truck that moved it and may never exceed the CPA of the *first* truck it started with that OpStage | **MISSING** | Nothing in `engine.py:1812-1955` tracks cargo provenance. In practice the policy's `_relay_source` (`campaign_policy.py:693`) restricts which dumps a lorry may lift from, which *incidentally* blocks most leapfrogs — but it is a policy accident, not an engine rule, and a live LLM staff can drive through it | MAYBE |
| 53.31/53.32 | Salt-marsh abandonment; engineer recovery at 10 CP | **MISSING** | `grep -i "salt.marsh" game/` → nothing | NO |
| 53.0 (GR) | *"Trucks consume fuel **and water** when they move, and they suffer **breakdown**"* | **PARTIAL / WRONG** | Fuel ✓ (49.18). **Water: never** (see 52.42). **Breakdown: never** — `_breakdown` (`engine.py:1459`) iterates `state.living(side)` (Units); a `TruckFormation` is not a Unit, so the 54.2 **BAR of 2L** and the light-truck off-road penalty are dead data. Neither army has ever lost a lorry to the desert | **YES** |

### Chapter 54 — SUPPLY CO-ORDINATION

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| **54.11** | **Any hex can be used as a supply dump**; all major cities are natural dumps | **DONE** | `engine.py:1936` `_establish_dump` (+ `engine.py:615` `_rail_station`); `apply.py` `SUPPLY_DUMP_ESTABLISHED`. Measured: **56 dumps founded** in the campaign. Major cities get the unlimited 54.12 row (`supply.py:58`) | YES |
| 54.12 (rules text) | **Dummy** dumps hold nothing; revealed on entry/bombing | **MISSING** | `SupplyUnit.is_dummy` exists and is honoured everywhere, but **nothing seeds one** (`grep "is_dummy=True" game/` → empty). 60.34 gives the Axis **2** dummies; 60.44 gives the CW **1** | MAYBE |
| 54.13 (chart [54.12]) | Supply Dump Capacity Chart | **PARTIAL** — see §4.3 | Village + Other + Major City rows live (`supply.py:51-68`). **The Non-Dump row (50/0/50/0) is transcribed at `logistics_rates.json:137` and never read** — `grep non_dump game/` → nothing | **YES** |
| **54.14** | Blowing a dump: non-gun units only; one phasing unit per hex per dump; ⅓ basic CPA (round up), never > CPA; may buy +1 per extra ⅓ (max 2); also as part of retreat-before-assault; any segment | **DONE** | `supply.py:414-489`, `engine.py:1677` `_blow_dumps`. The retreat-before-assault variant (13.25) is deferred and flagged. Measured: **18 attempts**, 4,827 Ammo / 24,608 Fuel / 6,434 Stores destroyed | YES |
| 54.15 | Any player may use any dump as a source | **DONE** | `_capture_dumps` flips ownership on entry | YES |
| 54.16 | *"Establishing a viable dump network should be top priority"* — each dump within one OpStage truck ride of the next | **DONE** (as doctrine) | `scenario.py:632` `_campaign_staging_dumps` + `_campaign_cw_depots` are spaced to one 30-CP hop and verified as such | YES |
| **54.17** | Supply Dump Demolition Table | **WRONG** — see §4.1 | `logistics_rates.json:146` faithfully transcribes a **misprinted 1979 chart**. It is **live**: 3 of the campaign's 18 demolitions rolled a natural **6 with a +1** → modified 7 → **33% destroyed where the ladder says 100%**. The best roll in the game is punished | **YES** |
| **54.2** | Truck Characteristics Chart | **DONE — verified cell-for-cell against the scan** | see §4.5 | YES |
| 54.31 | The CW railroad moves supplies **or** personnel, not both | **PARTIAL** | Supplies only; no personnel (48 V.K missing) | MAYBE |
| **54.32** | **1,500 tons per Operations Stage, either direction** | **DONE** | `scenario.py:761` `_RAIL_TONS_PER_OPSTAGE = 1500`, `supply.py:383`. Three stage-loads are packed into one GT convoy. Measured: **456,123 tons over 111 GT = 4,110 t/GT** against a charted 4,500 — the shortfall is exactly the 54.34 water stage. ✓ | YES |
| **54.33** | Only **one type** of supply at a time — fuel, ammo, **or** stores; water needs no train (RR hexes are pipelines) | **DONE** | `scenario.py:762` `_RAIL_STAGE_COMMODITIES = ("AMMO","FUEL","STORES")` — one per stage; water excluded and served by `wells.pipeline`. *(Which stage carries what is a flagged doctrine choice, not a magnitude.)* | YES |
| 54.34 | One OpStage per calendar month the railroad hauls **water for itself** and may not be used | **DONE** | `scenario.py:775-776` drops the STORES stage in each month's first GT | NO |
| **54.35** | Supplies may be dumped at **any hex** on the line; unloaded on arrival; may not move again that stage | **DONE** | `engine.py:475` `_rail_stops` + `:582` `_rail_deliver` — the train stops at every manned rail hex, the railhead, and the construction railhead | YES |
| **54.41–54.46** | **Axis use of the CW railroad** — 5 contiguous controlled rail hexes + 250 Stores/100 Fuel imported as rolling stock buys 300 t/OpStage; 900 t per stacking point of troops; stock destroyed if the 5-hex chain breaks | **MISSING** | Explicitly deferred and flagged (`construction.py:25`, `scenario.py:1224`). The Axis has **no** railway at all — it hauls from Benghazi by lorry for 111 turns | **YES** — it is the Axis's only lever against the CW's rail asymmetry, and the reason his 1942 advance historically stalled |
| **54.5** | Equivalent Weights Chart | **DONE — verified** | `supply.py:77` holds Fuel and Water as **exact fractions** (⅛, ⅙), which is better than the JSON's rounded 0.1667. see §4.6 | YES |

### Chapter 55 — PORTS AND SUPPLY

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| 55.11 | Major ports take men **and** supplies; minor ports supplies only; both ship out | **MISSING** | `Port.kind` is set ("major") and **never read** (`grep -n "\.kind" game/engine.py` → only air-mission kinds). Moot: reinforcements bypass ports entirely, which **55.3's own key permits** (*"reinforcements are never affected by a port's capacity or current efficiency"*) | NO |
| 55.12 | Every port has an Efficiency Level; **Tobruk's is 5** | **WRONG (campaign)** | `scenario.py:996` seeds **PORT-Benghazi `max_eff=10`** — the chart says **3**. `scenario.py:1001` seeds **PORT-Matruh `max_eff=10`** — the chart says **1**. A bomb hit therefore costs Benghazi 10% of its throughput instead of 33%, and Matruh 10% instead of **shutting it outright**. Tobruk's max_eff=5 ✓ | **YES** |
| 55.13 | Port capacity in stacking points **and tons** | **PARTIAL** | Tonnage ✓ (`scenario.py:338` `_caps_tonnage` sets per-commodity caps to `_UNLIMITED` and lets tonnage gate). **The stacking-point schedule is not modelled at all** — no troops or replacements ever cross a quay | MAYBE |
| **55.14** | *"A port operating at peak efficiency uses its listed capacity… reduced… directly proportionate to its reduced Level"* — and the 55.3 key defines **Maximum Tonnage** as *"the **TOTAL tonnage** of supplies that may be shipped in and/or out in one Operations Stage"* | **WRONG** | `supply.py:90-96` `port_landing_cap` converts the port's **whole tonnage allowance into EACH commodity separately** and `engine.py:693` budgets `port_landed[(port.id, k)]` **per (port, commodity)**. A convoy landing all four commodities pushes **4× the charted tonnage** through the quay in one OpStage. Verified: <br>• Benghazi (2,500 t) → 625 Ammo **+** 20,000 Fuel **+** 2,500 Stores **+** 15,000 Water = **10,000 tons** <br>• Tobruk (1,700 t) → **6,800 tons**;  Tripoli (15,000 t) → **60,000 tons** <br>Measured in the campaign: Benghazi landed **398,917 tons over 111 GT = 3,594 t/GT** through a port rated **2,500 t/OpStage**. The eff/max_eff scaling ✓ and the round-up ✓ are correct | **YES** |
| 55.15 | Debarking troops may reduce a port's efficiency for supplies that stage; **scheduled** reinforcements do not | **MISSING** | No troops cross a port | NO |
| 55.16 | A port's capacity applies to everything received in a Game-Turn | **PARTIAL** | Only one arrival phase per GT exists (48 V.D defect), so the question never arises | MAYBE |
| 55.17 | **Bizerta** — closed until 1 June 1941, then roll 12 on 2d6 each GT | **MISSING** | No Bizerta port. (The 55.3 chart rates it 10 / 10 / 15 / **3,333 t** — verified from the scan) | NO — off-map |
| **55.18** | **For every OpStage a port does not lose Efficiency to enemy bombs, it regains one point** (up to max). Exception: 55.26/55.27 (scuttling, mines) | **WRONG** | `_port_regen` (`engine.py:727`) is called **only** from `_naval_convoys` (`engine.py:724`), which fires only at `stage == 1` → **regen is 1/Game-Turn, not 1/OpStage (⅓ the rate)**. It also regens **unconditionally** — the *"did not lose levels to bombs this stage"* test does not exist. And the exemption is a **hard-coded id set**: `HARBOUR_BLOCKED = frozenset({"PORT-Tobruk"})` (`engine.py:65`) — so *bomb* damage at Tobruk is permanent (it should regen) while a *scuttled* Benghazi would regen (it should not). Measured: PORT-Tobruk fell to eff 2 and never recovered | **YES** |
| **55.25** | **The San Giorgio reduces Tobruk's efficiency by THREE levels at the start of the game** | **WRONG** | `scenario.py:1003-1004` seeds `PORT-Tobruk(max_eff=5, eff=5)` — **full efficiency**. It should open at **2 of 5**. `state.py:321-323` claims *"Tobruk seeds eff=2/max_eff=5 — the San Giorgio… costs it three levels"*. **The docstring is a lie.** Tobruk lands 425 Ammo Points/OpStage where the rules allow **170** | **YES** |
| 55.21–55.24, 55.26–55.28 | **Blocking harbours** — engineers scuttle for 25 Ammo + 10 Stores (Tobruk 50+25); one level/OpStage; unblocking costs 50+25 (Tobruk 25+10, Benghazi 100+50 **and two engineer units**); air-laid mines each cost a level and are cleared on a 1–3 | **MISSING** | Nothing. No player may ever block or unblock a harbour. `HARBOUR_BLOCKED` is a static frozenset, not a state | **YES** — 55.2 is a live strategic lever for both sides (the Axis historically scuttled Benghazi) and neither AI has it |
| 55.3 | Port Capacity and Efficiency Level Chart | **DONE (data) / WRONG (use)** | see §4.7 — the transcription is **perfect**; the *application* is 55.12/55.14/55.18 above | YES |

### Chapter 56 — THE AXIS NAVAL CONVOY SYSTEM

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| 56.11/56.12 | Six shipping lanes; a convoy is the tonnage assigned to one lane per GT; 1–6 convoys/GT | **PARTIAL** | `Convoy.lane` is a **label** (`state.py:228`). The campaign sails exactly **two** Axis lanes — "2" (Sicily→Tripoli, re-pointed at Benghazi) and "6" (Italy→Tobruk). No lane choice is ever made | MAYBE |
| 56.13 | Convoys may be bombed; the Axis must trade proximity for risk | **DONE** | `engine.py:405` `_interdict` + the [41.66] CRT (`logistics_rates.json:249`, transcribed from the scan) | YES |
| 56.14 | Lanes 4 & 5 (Greece) closed until the 2nd GT of May 1941 | **MISSING** | No lane gating | NO |
| **56.15** | A convoy sailing into a port **captured by the enemy is cancelled** | **DONE** | `engine.py:431` `_convoy_dest` + the retracting-railhead exception (54.3/60.7). Verified: the CW Tobruk ferry landed **0** points in the whole campaign because the Axis holds Tobruk from GT1 — exactly right | YES |
| 56.16 | Flak/AA points = convoy tonnage ÷ 1000 | **MISSING** | Convoys have no flak; `InterdictionOrder.bomb_points` is a static schedule | MAYBE |
| 56.17 | No tonnage limit per lane except 56.2 | **DONE** | n/a | NO |
| **56.21** | Tonnage = 56.4 monthly Level → 56.5 table → **+1 die**, planned **one GT in advance** | **PARTIAL** | `scenario.py:655` `_campaign_axis_cargo` does the 56.4 × 56.5 × die × 54.5 chain correctly — but **at scenario construction**, from a seeded RNG. There is no Convoy Planning Phase and no Axis *decision* | YES |
| **56.22** | The Axis splits the tonnage across fuel/ammo/stores as he wishes; **unlimited in Europe** | **PARTIAL / FLAGGED** | `scenario.py:406` `_CONVOY_SPLIT_56_22 = {FUEL 0.60, AMMO 0.25, STORES 0.15}` — a **fixed** split. It is the Axis player's single most important recurring decision and it is hard-coded | YES |
| 56.23 | Tonnage equivalencies from 54.5 | **DONE** | `supply.tons_to_points` | YES |
| 56.24 | Replacement points consume convoy tonnage | **MISSING** | Reinforcements/replacements arrive free of tonnage | MAYBE |
| 56.25 | Lanes and destinations fixed once chosen | **DONE** | Static timetable | NO |
| **56.27** | *"Ports have maximum capacities; they may not receive supplies over that capacity"* | **WRONG (as a sink)** | The engine ships the full 56.5 allocation at a port that cannot take it and **silently annihilates the remainder**. Measured: of **502,224 planned tons**, **103,308 tons (21%) never reach Africa** — 630,500 Fuel Points, 3,846 Ammo, 9,111 Stores. Under 56.27 a player simply *would not ship it that way* (he would rebalance the 56.22 split, or use Tripoli, which rates **15,000 t** to Benghazi's 2,500). This is the single largest **engine-only** destruction of supply in the game | **YES** |
| 56.28 | All ports of arrival have dumps built in | **DONE** | `Port` + a co-located `SupplyUnit`; `state.py:314` | YES |
| **56.31–56.35** | **Axis coastal shipping** — ship counters with printed tonnage, CPA 50, 1 pt/sea hex, move in the Truck Convoy Phase, 5 CP to load / 5 to unload, one cargo type, no fuel needed, cannot enter a neutralised or enemy port, cannot be attacked | **MISSING** | Nothing. `grep -i "coastal ship" game/` → nothing. The Axis's *only* way to move tonnage between African ports without lorries does not exist — so Benghazi's landed freight can **only** go forward on the 60.33 lorry park | **YES** |
| 56.4 / 56.5 | Convoy Level Chart / Convoy Capacity Table | **DONE (data)** — see §4.8 | `logistics_rates.json:231-247`; wired at `scenario.py:404` | YES |

### Chapter 57 — COMMONWEALTH SUPPLY BASE

| Rule | What it says | Status | Evidence | Critical? |
|---|---|---|---|---|
| 57 | The CW has **unlimited** fuel/ammo/water/stores **in Cairo at all times**; his problem is only getting it forward. No shipping. | **DONE** | `scenario.py:611` `_campaign_cw_base` seeds Cairo **and Alexandria** at 125,000,000 of each, `base=True` (immobile per `engine.py:1636`, capture-proof per `engine.py:1751`, evaporation-proof per `engine.py:817`). **Alexandria is rulebook-backed**, not an invention: 60.44's own note reads *"Remember that unlimited supply points are available in **Cairo and Alexandria**."* | YES |

---

## 3. WHERE MY CHAPTERS TOUCH RULES OUTSIDE THE SLICE (flagged, not audited)

* **24.9** (construct a dump: 3 CP + 20 Stores) is **DONE** (`engine.py:2068`) and is what should gate the
  54.12 **Non-Dump** capacity row — see §4.3.
* **29.34 / 29.35** are the *charted* magnitudes behind 52.43 and 49.3's hot slice. Both are in my
  findings because chapters 49 and 52 defer to them.
* **6.3** charts the CP costs my chapters reference: blow dump ⅓ CPA ✓; draw water 1 (0 in the
  Organization Phase) ✓; **load/unload trucks 2 (0 in the Organization Phase) ✗**; poison 1 ✗;
  sweeten 5 ✗; construct a real / dummy-or-non-dump dump **3 / 2** (the "2" variant is unused).
* **64.71 / 64.72** — the campaign's auto-win *and* auto-loss both hinge on a **90 / 60 Movement-Point
  truck supply trace to a dump and thence to Tobruk or Tripoli**. That is a §54 trace, and it is
  not the ½-CPA trace the engine uses. Worth a look by whoever owns chapter 64.

---

## 4. CHART FIDELITY

I re-rendered the original scan at 600 dpi and read every chart in this slice. **`data/logistics_rates.json`
does not contain a single transcription error.** Details:

### 4.1 [54.17] Supply Dump Demolition Table — **the misprint is in the 1979 book, not in our OCR**

The printed chart (PDF p.109, booklet p.14), at 600 dpi, values correctly centred under their headers:

```
DIE :        -2   -1    0    1    2    3    4    5    6    7   8 or more
% Supplies    0   33    0   10   20   33   50   75  100   33   100
```

So `docs/rules/90:1494` and `logistics_rates.json:146` are **faithful**. There is no column slip to fix
in the OCR pipeline. `logistics_data.py:demolition_percent_54_17` is right to refuse to "repair" it.

**But it must be repaired, and the repair is forced.** Strike the two anomalous cells and every
remaining cell is a clean monotone ladder — and the two struck cells are *exactly* the two whose values
are pinned by their neighbours: `-1` sits between two 0s, and `7` sits between two 100s. There is no
freedom in the reconstruction. Almost certainly a duplicated "33" slug in the paste-up.

**THE CORRECT TABLE:**

| DIE (modified) | −2 or less | −1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 or more |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **% of every commodity destroyed** | **0** | **0** | **0** | 10 | 20 | 33 | 50 | 75 | 100 | **100** | 100 |

(changed cells in bold: `-1: 33 → 0`, `7: 33 → 100`; all nine others unchanged.)

**It is live.** In seed 1941 the engine ran 18 demolition attempts. `(die, modifier) → %`:

```
(1,-1)→0   (1,+1)→20   (2,-1)→10   (2,+1)→33 ×4   (2,+2)→50   (3,+1)→50
(4,+1)→75 ×2   (4,+2)→100   (5,+1)→100   (6,-1)→75   (6,0)→100   (6,+1)→33 ×3   ← !!
```

**Three of eighteen attempts (17%) rolled a natural SIX with a +1 modifier — modified 7 — and destroyed
33% where the ladder says 100%.** The best possible roll in the game is punished. And with a modifier of
−3 (a lone battalion in a major city, which is where most dumps stand) a die of **2** burns a third of
the dump while a die of **3** burns nothing.

The 54.17 modifiers themselves are transcribed correctly and `supply.py:423-455` implements them
correctly, including the exclusive city/small-dump clause. Two are omitted and honestly flagged in the
code: *"+1 if the attempting unit is a full (non-shell) division"* (no org size on `Unit`) and
*"−1 if the dump has not just been captured and the nearest enemy unit is at least 20 CP (medium truck)
away"* — **the latter is NOT flagged and is missing**: `demolition_modifier` never tests enemy distance
or just-captured status, so both halves of the last cumulative clause (`+1 just captured` / `−1 enemy far`)
are absent. That is a swing of up to 2 on the die.

### 4.2 [52.7] Water Availability Table — **verified, correct**

| DIE | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Town (= village) | 100 | 150 | 200 | 300 | 350\* | 500\* |
| Bir | 50 | 100 | 150 | 200\* | 300\* | 400\* |

\* = roll again secretly; a '1' depletes. `logistics_rates.json:119-122` and `wells.py:_WATER_TABLE_52_7`
match exactly, including which entries carry the asterisk. **No error.**

### 4.3 [54.12] Supply Dump Capacity Chart — **verified, correct… and one row is dead**

| Location | Ammo | Fuel | Stores | Water |
|---|---|---|---|---|
| Tunis/Tripoli | U | U | U | U |
| Major City | U | U | U | U |
| Village | 2,500 | 8,000 | 3,000 | 1,000 |
| Other Terrain | 1,500 | 5,000 | 1,000 | 1,000 |
| **Non-Dump** | **50** | **0** | **50** | **0** |

`logistics_rates.json:133-137` matches the scan exactly. **But `logistics_data.py` exposes only
`dump_other_terrain_cap()` and `dump_village_cap()`** — `grep -rn non_dump game/` returns **nothing**.
The Non-Dump row is transcribed and never read.

Consequence: `SupplyUnit.constructed` (rule **24.9**, `state.py:188`) is honoured for *loading* (only a
constructed dump may give supply back to a convoy) but **not for capacity**. An unconstructed heap that
a lorry drops in the desert (`engine.py:1936` `_establish_dump`, `constructed=False`) gets the **full
Other-Terrain ceiling of 1,500/5,000/1,000/1,000** where the chart's Non-Dump row allows **50 Ammo,
50 Stores and NO fuel or water at all.** 56 such dumps were founded in the campaign. This is the row
that makes 24.9 a *decision* rather than a formality.
*(Honest caveat: "Non-Dump" is a genuinely ambiguous row — 6.3's `Construct a Real or Dummy/Non-Dump
Supply Dump | 3/2` implies it is a third **counter type** costing 2 CP, not merely "an unconstructed
pile". Either reading leaves the row unmodelled; the engine implements neither.)*

### 4.4 [50.2] Ammunition Consumption Rates Table — **recovered from the scan; rates correct, one restriction ignored**

This chart **never OCR'd into `docs/rules/90` at all** (only its index entry, line 1665). From PDF p.108:

**Logistics Game Played**

| Action | Ammo |
|---|---|
| Barrage | **4** |
| Anti-armor | **3** |
| **Close Assault: Armor-class, Gun-class, MG-inf, HvyWpn-inf** | **2** |
| Anti-air at single target group | **2** |
| Rearm any portion of a squadron's planes' tacair rating | 1 |
| Rearm *one* plane with bombs, torpedoes, or mines | 1 |
| Engage in air-to-air combat and/or strafe | TacAir / Bombload |

**Logistics Game Abstracted** *(recorded for completeness; NOT what we play)*: Barrage phasing bn-eq 4,
barrage non-phasing 2, assault phasing 1, assault non-phasing 1, AA gun-class 1, rearm non-fighter 1,
flight by a non-fighter plane = Bombload.

`logistics_rates.json:62-66` and `supply.py:144` (`AMMO_RATE`) are **correct: 4 / 3 / 2**.

**WRONG:** the chart restricts close-assault ammo to **Armor-class, Gun-class, MG-infantry and
Heavy-Weapons-infantry**. Ordinary rifle infantry close-assaults for **free**. `supply.py:154`
`ammo_cost` charges `2 × strength` to **every** unit. The engine has no MG/HvyWpn class flag to key on.
Direction: over-charges ammunition. Magnitude in practice is small (measured campaign ammo burn: Axis
1,078, Allied 1,768) — but it is a chart error, and it is exactly the kind that would bite once the
armies start actually fighting.

### 4.5 [54.2] Truck Characteristics Chart — **verified cell-for-cell, correct**

`docs/rules/90`'s OCR swapped the **sub-headers** "Water" and "Fuel Capacity" (it prints
`… Stores | Fuel Capacity | Water | | BAR`; the scan reads `… Stores | Water | Fuel Capacity | Fuel
Consumption Factor | BAR`). **The data rows are in the correct order and `logistics_rates.json:151-174`
reads them correctly.**

| Truck | CPA Inf | CPA Guns | **CPA Supplies** | TOE Inf | TOE Arty | TOE AA | Ammo | Fuel | Stores | Water | Fuel Cap | Fuel Factor | BAR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Light | 25 | na | **40** | ½ † | na | 1 | 2 | 50 | 6 | 40 | 8 | 1 | 2L ‡ |
| Medium | 20 | 15 | **30** | 1 | 1 | 2 | 4 | 120 | 15 | 100 | 6 | 1 | 2L |
| Heavy | 20 | 15 | **30** | 2 | 1 | 4 | 8 | 250 | 30 | 200 | 6 | 1 | 2L |

**Independent proof the transcription is right:** rule 49.14 says *fuel capacity = CPA × ⅕ × rate*.
Light: 40 × ⅕ × 1 = **8** ✓. Medium/Heavy: 30 × ⅕ × 1 = **6** ✓. The chart is internally consistent
with the rule, which confirms the column mapping.

**Not used by the engine:** the **Water** capacity column (52.45 — the relay hauled 0 water in 111
turns); the **Fuel Capacity** column (the truck's *own* tank — `engine.py:1893` makes a truck burn its
**cargo** fuel instead, so an empty lorry cannot move at all); and **BAR 2L** + the light-truck
off-road penalty (trucks never break down).

### 4.6 [54.5] Equivalent Weights Chart — **verified, correct**

Ammo **4** t/pt · Fuel **⅛** · Stores **1** · Water **⅙**. `supply.py:77` keeps Fuel and Water as exact
fractions rather than sourcing the JSON's rounded `0.1667` — correct, and correctly reasoned in the
comment. Interport truck/motorization point 50 t; air replacement point 2 t (infantry only); rail
stacking equivalents ⅒ / ⅕ / ½ / ½ — all transcribed, none used (no troops/replacements cross a quay
or ride a train).

### 4.7 [55.3] Port Capacity and Efficiency Level Chart — **the missing tonnage column, recovered; JSON is perfect**

`docs/rules/90:1560-1577` lost the **Maximum Tonnage** column entirely. From the scan (PDF p.110):

| Port | Efficiency Level | Stacking In | Stacking Out | **Maximum Tonnage** |
|---|---|---|---|---|
| Tripoli | 10 | 10 | 15 | **15,000** |
| Bizerta\* | 10 | 10 | 15 | **3,333** |
| Alexandria | 10 | 5 | 10 | **15,000** |
| Tobruk † | **5** | 1 | 3 | **1,700** |
| Benghazi | **3** | 2 | 5 | **2,500** |
| Mersa Matruh | **1** | 1 | 2 | **250** |
| Bardia | 1 | 0 ‡ | 1 | **400** |
| Sollum | 1 | 0 ‡ | 1 | **250** |
| Derna | 1 | na | 1 | **300** |
| All others | 1 | na | na | **100** |

Key: *"**Maximum Tonnage:** The **total tonnage** of supplies that may be shipped in and/or out in one
Operations Stage."* — the word **total** is what condemns `port_landing_cap`.

`logistics_rates.json:214-225` (`port_supply_tonnage_55_3`) matches **every cell, including the odd
3,333 for Bizerta.** The transcription is not in question. What is wrong is:

| | Chart | Engine (campaign) | |
|---|---|---|---|
| Benghazi max Efficiency | **3** | `10` (`scenario.py:996`) | **WRONG** |
| Mersa Matruh max Efficiency | **1** | `10` (`scenario.py:1001`) | **WRONG** |
| Tobruk **starting** Efficiency | **2** of 5 (55.25, San Giorgio −3) | `5` of 5 (`scenario.py:1004`) | **WRONG** |
| Tonnage gate | one **shared** budget | **per commodity** (`supply.py:94`) | **WRONG — 4×** |

### 4.8 [56.4]/[56.5] Axis Naval Convoy charts — plausible, **unverified**

These live on the oversized fold-outs (`docs/rules/99` = "not OCR-able") and I could not locate them in
the scan's chart pages within this pass. `logistics_rates.json:231-247` carries a monthly Level letter
per month 1940–42 and a `fixed + variable × die` capacity per Level A–G. The one anchor I *can* check is
the rulebook's own worked example (56.21): *"The Axis Monthly Shipping Table tells the Axis Player to use
row **E** for November 1941… he rolls a **4**… he may ship **21,000 tons**."* The JSON gives
1941/nov = **"E"** ✓ and E = 11,000 + 2,500 × 4 = **21,000** ✓. **Both halves of the book's own example
reproduce exactly.** That is strong, but it is one cell of each chart — the remaining 35 months and 6
levels are unverified. **Flagged, not cleared.**

### 4.9 [58.5] Abstract Truck Loss Chart — **recovered from the scan; NOT in docs, NOT in data, NOT implemented**

The task asked for it. It exists (PDF p.108) and has never been transcribed anywhere in this repo:

| Year | Jan | Feb | Mar | Apr | May | June | July | Aug | Sept | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **1940** | – | – | – | – | – | – | – | – | – | 6/2 | 5/3 | 4/4 |
| **1941** | 2/3 | 2/3 | **10/1** | 9/2 | 7/3 | 5/4 | 4/3 | 3/3 | 3/3 | 3/3 | 3/5 | 3/4 |
| **1942** | 2/4 | 3/3 | 3/3 | 3/3 | 3/3 | 3/4 | 3/4 | 3/4 | 3/4 | 3/4 | **4/6** | 3/5 |
| **1943** | 2/4 | – | – | – | – | – | – | – | – | – | – | – |

> `Nr/` = Percentage of **Commonwealth** Motorization Points in N. Africa destroyed.
> `/Nr` = Percentage of **Axis** Motorization Points in N. Africa (Tripoli/Tunis etc. are part of N. Africa) destroyed.

Per **58.42**, in the abstract air game these percentages apply **to the Players' TRUCKS** — and we *do*
play the abstract air game (`state.AirWing` is at the 32.0/58.0 grain). **It is not implemented**, so
neither lorry park has ever lost a truck to enemy air in 111 turns. Note the shape: it is a **pro-Axis
chart in 1941** (March: CW loses 10%, Axis 1%) and **pro-Commonwealth in late 1942** (Nov: CW 4%, Axis 6%)
— exactly the historical air balance. Its absence is a systematic thumb on the scale, in both directions,
at the two moments the campaign turns. **58.43** (10% of all arriving truck points lost on arrival) is
also missing.

*(Also on that page, and relevant to §55: the [41.5] key reads* **"Ports: Reduce the Port by that number
of Efficiency Levels"** *and* **"Supply Dump: Eliminate that percentage of all Supplies in that Dump. In
addition, lose 1 Truck Point for each 10%"**. *`engine.py:1057` `_air_port` always reduces by exactly **1**,
never reading a CRT.)*

---

## 5. CONSERVATION AND THE FAUCET

The invariant (`invariants.py:70-80`) is `on_hand(dumps + trucks) + consumed == initial`, and
`SUPPLY_ARRIVED` (`apply.py:60`) **raises `initial_supply` by the landed amount**. So the identity is
maintained *by construction* at the faucet and **cannot detect minting there**. It is a good check on the
drains and a blind spot at the sources. Tracing the whole path:

```
  56.5 die-rolled tonnage  ──[A]──►  PORT  ──[B]──►  DUMP  ──[C]──►  LORRY  ──[D]──►  UNIT  ──►  burn
        (mint, by design)                     ▲                          │
                                              └──[E] evaporation 6%/GT ──┘   [F] capture   [G] demolition
```

**MINTS (supply created that should not exist)**

| | Where | Size |
|---|---|---|
| **M1** | **[B] The port gate is per-commodity.** `supply.py:94` + `engine.py:693`. Up to **4× the charted tonnage** through a quay per OpStage. Measured at Benghazi: **3,594 t/GT through a 2,500 t/OpStage port**. | **large** |
| **M2** | **[F] Capture returns 100%.** 50.16 (⅓ ammo) and 51.16 (½ stores) are absent. Measured: the Axis kept **2,183 Ammo** and **4,094 Stores** it should have lost; the CW kept 514 Ammo, 1,078 Stores. Against an Axis war-long ammunition burn of **1,078**, the illegitimate ammo alone is **2×** its entire expenditure. | **large** |
| **M3** | **[B] The 54.12 Non-Dump row is never applied.** A lorry-dropped, unconstructed heap holds 5,000 Fuel where the chart allows **0**. 56 such heaps founded. | medium |
| **M4** | **Wells are minted once PER SIDE.** `wells.py:wells()` creates `AX-Well-X` *and* `AL-Well-X` on the same hex, each with the full pool — so the map holds **2× the charted water** (finite village/bir pools: 504,000 points where the geography holds 252,000) and both armies can drink the same well dry independently. Flagged in the module; still a mint. | medium |

**SILENT DESTRUCTION (supply that vanishes with no rule behind it)**

| | Where | Size |
|---|---|---|
| **D1** | **[A] Convoy overflow above the port cap is annihilated.** `engine.py:698-700` lands `room` and drops the rest; the un-landed cargo is never credited to `initial_supply`, so the invariant is silent. Measured: **103,308 of 502,224 planned tons (21%) never reach Africa** — 630,500 Fuel Points. **56.27 says a player may not ship over capacity — it does not say the tonnage evaporates.** He would rebalance the 56.22 split, or sail to Tripoli (15,000 t vs Benghazi's 2,500). This is the largest engine-only loss in the game. | **large** |
| **D2** | **[B] Rail overflow above a dump ceiling is dropped.** `engine.py:601-613`: after the even cut and the forward cascade, any `left` falls out of the loop. Same "never minted" mechanism, so also invisible to the invariant. Small, because the stops are villages (8,000 fuel) and the cascade is greedy. | small |
| **D3** | *(non-issue, recorded so it is not re-litigated)* Truck unload clips to the dump ceiling but the **truck keeps the remainder** (`engine.py:1911-1915`) — conserving. Rail/convoy/truck loads and unloads are all conserving transfers in `apply.py`. | — |

**[E] EVAPORATION — right rule, wrong surface, wrong sides**

* ✓ 6% base, once per Game-Turn, at the Stores Expenditure Stage (49.3, 48 IV) — `engine.py:758`.
* ✓ +5% hot, per Operations Stage, at Weather Determination (49.3, 29.34) — `engine.py:772`.
* ✓ Rounded **down** — `engine.py:820`.
* ✓ Fuel **and Water**, and nothing else (49.3, 52.44).
* ✓ **NOT applied to wells, pipelines or oases** — `engine.py:817` skips `base=True`, and `wells.py`
  marks every water source `base=True`. **52.44 and 29.34 are satisfied.** *(Your specific question:
  yes, this one is correct.)*
* ✗ **NOT applied to fuel or water riding on TRUCKS.** `engine.py:816` iterates `r.state.supplies` only.
  **29.34 is explicit: "This includes water and fuel in dumps as well as in trucks."** Parking freight on
  lorries currently makes it evaporation-proof, and 410 Truck Points hold a lot of freight.
* ✗ **No 9% Commonwealth rate for Sept 1940 – Aug 1941.** `logistics_rates.json:48` transcribes it; **no
  code reads it**; `_evaporate` has no side parameter at all. The campaign opens in Sept 1940, so this is
  live for roughly the first 48 Game-Turns.

**And the headline the ledger gives you:** evaporation removed **2,272,976** Fuel Points — **73% of every
fuel point that ever landed in Africa**, and **1,600× the entire Panzerarmee's movement consumption
(1,419)**. The faucets are so large that 49.3 is the only sink that matters. The armies are not starving;
the jerrycans are. Whatever else you fix, that ratio is the tell that **A1 (the ½-CPA trace) has removed
the cost of distance** — the thing the whole Logistics Game is about.

---

## 6. TOP FIVE

Ranked by **damage to the campaign per unit of work**.

1. **[55.14] Make the port tonnage gate ONE SHARED BUDGET, and fix the three seeded Efficiency Levels.
   — S**
   *Why:* the 55.3 key says **total** tonnage; the engine spends the whole allowance on every commodity
   separately, so every port passes up to **4×** what the chart allows (measured 3,594 t/GT through a
   2,500 t Benghazi) — and Benghazi's max efficiency is seeded at **10** where the chart says **3**,
   Matruh's at **10** where the chart says **1**, and Tobruk opens at **5/5** where 55.25's San Giorgio
   puts it at **2/5** (and `state.py:321` *claims* it does). Rewrite `port_landing_cap` to take the whole
   cargo and spend one tonnage budget across it; change three numbers in `scenario.py`. Note the tests at
   `tests/test_ports.py:110` currently **lock the bug in**.
   *Balance:* pushes **toward the Commonwealth** (the Axis loses ~40% of his landed tonnage, and his port
   becomes 3× more fragile to bombing).

2. **[50.16]/[51.16] Tax captured supply — ⅔ of ammo and ½ of stores are LOST. — S**
   *Why:* `_capture_dumps` transfers 100% on the strength of **32.13, an abstract-game rule**. Measured,
   the Axis captured **3,275 Ammo Points — three times its entire ammunition expenditure for the whole
   war** — and 8,188 Stores. This is a one-line change in the emitter plus a `destroyed` payload in
   `apply.py`, and it turns an overrun dump from a windfall into what the book makes it.
   *Balance:* pushes **toward the Commonwealth** (the Axis captured 4× as much as the CW did).

3. **[49.3]/[29.34]/[29.35] Fix the three evaporation & water magnitudes. — S**
   *Why:* three separate charted numbers are simply not in the engine, and one of our own data comments
   asserts the rulebook is silent when it is not. (a) **Truck cargo does not evaporate** — 29.34 says it
   must. (b) **The Commonwealth's 9% rate (Sept 40 – Aug 41) does not exist** — it is transcribed at
   `logistics_rates.json:48` and read by nothing; `_evaporate` has no side split. (c) **Hot weather
   DOUBLES water (29.35)**, it does not add 1 — `logistics_rates.json:113` says "UNSPECIFIED… charts no
   number", which is false. All three are small, local edits.
   *Balance:* (a) neutral-ish, (b) **toward the Axis** early, (c) **toward the Commonwealth** (he has the
   pipeline; the Axis carries his water).

4. **[54.17] Correct the demolition table — and record that the misprint is the BOOK's. — S**
   *Why:* the OCR is faithful; the 1979 chart is wrong; the correction is *forced* by its own neighbours
   (`-1: 33→0`, `7: 33→100`). It fires **17% of the time** in a live campaign — three of eighteen
   demolitions rolled a natural **6 with a +1** and burned **33% instead of 100%**. While you are in
   there, `demolition_modifier` is also missing the entire final cumulative clause (`+1 just captured` /
   `−1 nearest enemy ≥ 20 CP away`) — a swing of up to 2 on the die, and it is not flagged.
   *Balance:* helps whoever is **retreating** — i.e. the Commonwealth in 1940–41, the Axis in 1942.

5. **[A1 / 49.15 / 50.15 / 51.15] Kill the ½-CPA supply trace. Supply must be IN THE HEX. — L**
   *Why:* this is the one that actually matters, and it is why the other four are only worth 20 points
   each. `supply.py:229` is **rule 32.16 — the abstract game's supply range** — and every fuel, ammo,
   stores and water draw in the engine goes through it. In the Logistics Game there is no supply range:
   a unit eats what is in its own tanks (49.14), what its **first-line trucks** (53.11) carry, or what is
   in a dump on its hex. Until that is true, distance costs nothing, the 54.16 dump network is decoration,
   `Unit.is_first_line_truck` stays a dead flag, and the fuel economy keeps reading *73% evaporated,
   0.8% burnt by the army*. It needs a per-unit supply pool (49.14: `CPA × ⅕ × rate`), the first-line
   truck tier, and the 48 V.C.6 Supply Distribution Segment to fill them. It is the biggest job in the
   slice and it is the slice's whole point.
   *Balance:* unknown until measured — and it is the only item here for which that is the honest answer.

**Runners-up, in order:** [56.3] Axis coastal shipping (the Axis's only non-lorry way to move tonnage
between African ports — entirely absent, M); [58.5] the Abstract Truck Loss Chart (transcribed above,
never implemented; both parks are immortal, S); [53.0] truck breakdown (the 54.2 **BAR 2L** is dead data,
M); [52.45] hauling water by truck (the 54.2 Water column is loaded and never used — the relay moved
**0** water in 111 turns, S); [55.2] blocking and unblocking harbours (a live lever neither AI has, M).
