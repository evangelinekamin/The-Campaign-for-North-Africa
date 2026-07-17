# Rules 21-31 audit: breakdown, repair, engineers, construction, fortifications, minefields, raiders, prisoners, weather, the Fleet, Rommel

Audited 2026-07-14 against `game/*.py` @ b99e460, `data/*.json`, and — where the OCR was
untrustworthy — **against the scan itself** (`tmp/The Campaign for North Africa.pdf`, rendered
at 190-400 dpi: chart-booklet pages = PDF pages 70, 101, 102, 103, 104, 105, 109).

Every status below is from the CODE or from a RUN, never from a docstring. Where a docstring
and the code disagree, the code wins and I say so.

**The run of record**: full campaign, seed 1941, GT1-111, `CampaignAxisPolicy` vs
`CampaignCommonwealthPolicy`, 81,908 events. Cited below as *[RUN]*.

---

## Headline

Six of my eleven chapters do not exist in the campaign at all, and two of the ones that
"exist" are wrong in ways that move the result:

1. **`combat_tables.py:461` repairs 100% of a hex's broken-down tanks on a die of 2, 3 or 4.
   The chart says 10%.** I re-read the scan: the OCR bled `10%*` into `100%`, and both
   `data/breakdown_rates.json` and the engine inherited it. Measured: 86.4% of all broken armour
   comes back. With the true chart, 72.2%. On seed 1941 **the campaign winner flips** (ALLIED →
   AXIS).
2. **`supply.py:200` charges +1 Water for Hot weather. Rule 29.35 says water requirements are
   DOUBLED.** A 6-TOE panzer battalion pays 7 where the book says 12, on 30% of all
   Operations Stages.
3. **Trucks never break down** (21.11 names Truck Points first). 380 Truck Points cross the
   desert for 111 turns and not one is ever lost to it.
4. **Chapters 26 (minefields), 27 (raiders), 28 (prisoners) have zero code.** Chapter 30 (the
   Fleet) has a full implementation and **not one ship is ever placed on the board**. Chapter 31
   (Rommel) is implemented and **not wired into the campaign** — `state.rommel is None`.
5. **Rule 24's construction segment, built yesterday, never fires.** *[RUN]*
   `CONSTRUCTION_ADVANCED = 0` over 111 turns: the two NZ Railroad Construction companies are
   seeded at hex `(47,140)`, forty-odd hexes from the railhead at `(26,100)`, and nothing ever
   moves them there. Zero hexes of the 46-hex surveyed line are laid.
6. **Foul weather covers the whole theatre.** *[RUN]* 68 of 68 sandstorm/rainstorm rolls
   blanketed all five map sections; the 29.7 table puts them on 2-3 of 5.

The good news, and it is real: **the Breakdown Table (21.38), the Weather Table (29.61), the
Foul Weather Location Table (29.7), the terrain Breakdown Values (8.37) and the barrage/anti-armor
fortification shifts are all transcribed EXACTLY right** — I checked every cell against the scan.
Desert Breakdown Value = 24 is correct (I looked: two full-size baseline digits, unlike the raised
footnote on the `4³` beside it).

---

## 21.0 BREAKDOWN

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 21.11 | Truck Points, tanks, armored recce/AC and SP guns break down | **WRONG** | `state.py:130-134` `breaks_down = is_armor` — tanks/recce/AC/SP ✓. But **Truck Points do not**: `TruckFormation` (`state.py:340-362`) has no `bar`, no `bp_accumulated`, no `broken_down`, and `_truck_move` accrues no BP. *[RUN]* 380 Truck Points, 0 lost to breakdown in 111 turns | **YES** |
| 21.12 | Each TOE type has a Breakdown Adjustment Rating | DONE | `data/breakdown_rates.json:bar_by_model`; `unit_stats.json` `bar`; read at `oob.py:304`-ish. *[RUN]* CW cruisers +1, German/Lend-Lease 0 | YES |
| 21.13 | BAR shifts the Breakdown Point column | DONE | `combat_tables.py:431` `breakdown_column` | YES |
| 21.14 | BAR summary: Trucks 2L, AC 1L, SP/Tanks 1L-2R | PARTIAL | Tank/AC BARs transcribed and live. Truck BAR (2L, from the 54.2 chart, p109) is transcribed and **unreachable** — see 21.11 | YES |
| 21.15 | No breakdown check to/from/among the Tripoli/Tunisia boxes | **N/A** | The off-map boxes are not movement space in this engine — Tripoli exists only as a port + dump (`scenario.py:241,386`). No hex to exempt | NO |
| 21.21 | Terrain/hexside Breakdown Point Values (8.37); weather may modify | DONE | `terrain.py:110-134`. **VERIFIED cell-for-cell on the scan (p70)**: clear 4, gravel 6, salt marsh 6, heavy veg 3, rough 8, mountain 12, delta 2, **desert 24**, major city ½; ridge/slope 2, down-escarp 6, wadi 8, minor river 1 | YES |
| 21.22 | Combat causes no BP; any movement (retreat, reaction) does | DONE | `apply.py:81` (UNIT_MOVED), `:90` (REACTION_MOVED), `:111` (UNIT_RETREATED) all fold `bp_accumulated += bp`; `engine.py:173` re-checks the *enemy* after combat | YES |
| 21.23 | All vehicles in a stack/parent accrue the terrain's BP | DONE (proxy) | Per-unit accrual along each unit's own path — equivalent under the engine's per-unit movement | NO |
| 21.24 | Check whenever a vehicle ceases movement | DONE | `engine.py:1459` `_breakdown`, called after movement and after the enemy's combat | YES |
| 21.25 | BP cumulative within an OpStage, across BOTH players' portions; reset at stage end | DONE | `apply.py:393` `_reset_opstage` zeroes `bp_accumulated`/`bp_checked_column` on STAGE_ADVANCED and TURN_ADVANCED | YES |
| 21.26 | Re-check only on climbing into a HIGHER column (even a 0% check moves the gate) | DONE | `engine.py:1471-1473`; BREAKDOWN_CHECKED folds `bp_checked_column` at any pct (`apply.py:226`) | YES |
| 21.27 | No check until more than three BP accumulated | DONE | `engine.py:1469` `u.bp_accumulated <= 3` | YES |
| 21.28-21.29 | Separate rolls per vehicle type, per BAR group, per BP column | DONE (proxy) | One roll per unit, one BAR per unit — finer-grained than the rule, same distribution | NO |
| 21.31 | Column by accumulated BP; fractions round UP | DONE | `combat_tables.py:421` `math.ceil` | YES |
| 21.32 | BAR and Weather shifts are cumulative | DONE | `combat_tables.py:434` `band + bar + weather_shift` | YES |
| 21.33 | 71+ is the ceiling; adjusted below 4-10 = no breakdown | DONE | `combat_tables.py:443-445` | YES |
| 21.34 | Two dice read sequentially → % of that type's TOE | DONE | `engine.py:1474-1475` | YES |
| 21.35 | Fractions round up; a 1-TOE unit ignores a 10% result | DONE | `engine.py:1448-1456` `_broken_count` | YES |
| 21.36 | Distribute breakdown evenly across types and units | N/A | The engine has no sub-type mix inside a unit; per-unit rolls make it moot | NO |
| 21.37a-c | Hot = +1 column; Rainstorm = road BP treated as track BP | DONE | `combat_tables.py:472-476`; `movement.py:118-127` road-as-track under rain | YES |
| 21.37d | Sandstorm = +1 column **only if ≥50% of the unit's movement was in sandstorm sections** | **WRONG** | `combat_tables.py:476` shifts on the bare label — every unit that moved at all gets +1 whenever the (theatre-wide) weather is sandstorm. No 50% test exists. Over-applies | YES |
| 21.38 | The Breakdown Table | DONE | `combat_tables.py:407-414`. **VERIFIED cell-for-cell on the scan (p102)**, including the col-41-50 / 75%-row `66` the OCR dropped. The transcription is correct | YES |
| 21.41 | If the move began within 2 hexes of a >battalion enemy, ≥50% of the breakdowns are placed in the START hex | **MISSING** | Not found: grepped `21.41`, `start_hex`, `_breakdown`. All breakdowns occur where the unit stopped | NO |
| 21.42 | Broken Down Vehicle markers, tracked on a sheet | DONE (proxy) | `Unit.broken_down` counter | NO |
| 21.43 | A broken truck's cargo stays with it; a motorized infantry bn that loses a Truck Point is un-motorized | **MISSING** | Follows from 21.11 — no truck breakdown, so no cargo stranding and no de-motorization | MAYBE |
| 21.44 | Broken vehicles have NO CPA and may not move, defend or attack | **PARTIAL/WRONG** | The no-combat half is right: `Unit.effective_strength` (`state.py`) subtracts `broken_down` and 10 call sites read it. But **`broken_down` is read by no movement path** (grepped `engine.py`, `policy.py`, `tactics.py`, `movement.py`) — a battalion with 5 of 6 TOE broken still moves at full CPA and **drags its wrecks with it**. Breakdown is therefore a travelling, fully-recoverable combat debuff, not the trail of dead tanks the rule describes. This is also *why* 21.5 and 21.6 cannot exist | **YES** |
| 21.45 | Transfer supplies/infantry off broken trucks | MISSING | Follows from 21.11 | NO |
| 21.5 (21.51-.55) | Capturing broken-down vehicles (adjacent bn-size unit captures; tow up to 3 hexes) | **MISSING** | Not found: grepped `captur`, `21.5`, `tow`. Impossible while 21.44 lets wrecks travel | MAYBE |
| 21.6 (21.61-.67) | Towing to a Repair Facility at 10 CP/Repair Phase | **MISSING** | Not found: grepped `tow`, `towing`. Also moot: there are no Repair Facilities (22.3) | MAYBE |

---

## 22.0 REPAIR

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 22.11 | Repair any broken vehicle or destroyed tank you control, any nationality | PARTIAL | `engine.py:1519-1521` — own broken units only. No destroyed tanks, no captured equipment | MAYBE |
| 22.12 | Repairs in the Repair Phase; phasing player only | DONE | `engine.py:174` `_repair(r, side)` inside the phasing side's block; `Phase.REPAIR` | YES |
| 22.13a | No repair in an enemy-controlled hex (except a Major Facility) | DONE | `engine.py:1521` | YES |
| 22.13b | No supplies → no repair | DONE | `engine.py:1530-1532` (fuel draw, `continue` on failure) | YES |
| 22.13c | No repair for a vehicle towed this phase | N/A | No towing exists | NO |
| 22.13d | No repair in Rainstorm/Sandstorm (Major Facilities exempt) | DONE | `engine.py:1491-1494`, `:1516`. But theatre-wide — see 29.7 | YES |
| 22.14 | Axis repairs German separately from Italian; captured separately | N/A | Per-unit rolls; no captured equipment | NO |
| 22.21 | Field repair of broken vehicles; destroyed tanks may not be field-repaired | DONE | Vacuously — no destroyed tanks exist anywhere in the engine | NO |
| 22.22 | Field repair in any hex holding a broken vehicle + any friendly unit | DONE (proxy) | The broken unit repairs itself in place | NO |
| 22.23 | Truck field repair: die 2 → 1 Lt/Md point; die 1 → 2 Lt/Md or 1 Heavy; no supplies | **MISSING (dead code)** | `combat_tables.py:459` `_FIELD_REPAIR["truck"]` is transcribed correctly and **never called**: `engine.py:1528` only ever passes `"tank"` or `"ac_recce"`, and trucks are not Units. Follows from 21.11 | **YES** |
| 22.24 | AC/Recce field repair: 1 TOE on a die of 1; no supplies | DONE | `combat_tables.py:460`; `engine.py:1529` charges fuel only for tanks | YES |
| 22.25 | Tank/SPA field repair on the 22.8 Field column; round up; a single TOE point ignores 10% | **WRONG** | `combat_tables.py:461`: `{0:25, 1:25, 2:100, 3:100, 4:100, 5:0, 6:0}`. **The scan (p103) reads `25% / 10%* / 10%* / 10%* / 0% / 0%`.** The `10%*` was OCR'd as `100%` (docs/rules/90:1214-1216) and `data/breakdown_rates.json` copied it. The 10%\* single-TOE exception IS coded (`engine.py:1504`) but is unreachable because the result is never 10. **Expected recovery per attempt: 58.3% (engine) vs 13.3% (book) — 4.4x** | **YES** |
| 22.26 | ONE Fuel Point **per tank TOE Strength Point**, expended before rolling | **WRONG** | `engine.py:1488` `_REPAIR_FUEL = 1` charged **per attempt (per unit)**, not per TOE. A 10-TOE battalion repairs for 1 Fuel instead of 10. Documented as a proxy at `engine.py:1485-1487` | MAYBE |
| 22.27 | Weather affects field repair | DONE | See 22.13d | YES |
| 22.28 | "Field repairs are a risky proposition" | N/A | Flavour — and currently false, see 22.25 | — |
| 22.3 (22.31-.38) | **FACILITY REPAIRS**: Temporary facilities (buildable) + Major facilities at **Tripoli, Tobruk, Alexandria, Cairo**; 50-75% repair rates; Stores+Fuel per point; die modified by the city's fort level; ZOC/weather immunity for Major facilities | **MISSING** | Not found: grepped `facility`, `Repair Facility`, `temporary`, `major_facility` across `game/`. No facility entity exists. `data/breakdown_rates.json` transcribes the Temporary/Major columns (50/33/25/25/10/10 and 75/50/50/50/33/33/25/10) and the die modifiers, and **nothing reads them**. **A broken tank sitting in Cairo repairs at the FIELD rate.** This is the Commonwealth's entire rear-area recovery economy | **YES** |
| 22.4 (22.41-.44) | Repairing destroyed tanks (2 Stores + 2 Fuel each; R/J/– on the 22.44 table) | **MISSING** | Not found: no Destroyed Tank marker exists — a killed tank TOE is simply gone. `22.44` is transcribed nowhere in the engine | MAYBE |
| 22.5 | Repaired vehicles return as Replacement Points (no re-training) | PARTIAL | `engine.py:1540` returns repaired TOE straight into the unit; no Replacement-Point round trip | NO |
| 22.6 | Desert Tank Delivery Organization (3 squadrons: -1 DRM, tow at 20 CP, 3 TOE reserve) | **MISSING** | Not found: grepped `TDS`, `Tank Delivery`, `delivery`. The -1 DRM is transcribed in `data/breakdown_rates.json:die_modifiers` and unused | MAYBE |
| 22.7 | German Mobile Tank Repair Squad | **MISSING** | As 22.6 | MAYBE |
| 22.8 | Broken Down Vehicle Repair Table | **WRONG (Field/Tank column)** | See 22.25. The Truck, AC/R, Temporary and Major columns are transcribed correctly (verified on p103) — but three of the four are never read | **YES** |
| 22.15 | Vehicle Repair Supply Costs Chart | DONE (data) | `data/breakdown_rates.json:vehicle_repair_supply_costs_22_15` — verified against the scan (p102): Field/Bd/Truck-AC-Recce = none; Field/Bd/Tank = 1 Fuel; Facility/Bd/All = 1 Fuel + 1 Stores; De/Tank = 2 Stores + 2 Fuel. Only the first two rows are reachable | YES |

---

## 23.0 ENGINEERS

The campaign fields **three** engineer units, all Commonwealth: `10-NZ-RR-Constr-Coy`,
`13-NZ-RR-Constr-Coy`, `1-SA-Road-Constr-Bn` *[RUN]*. There is **not one Engineer Battalion, not
one Engineer Company, and not one HQ with Engineer capability on either side** — so even if
24.3/24.4/24.8 were implemented, nobody could execute them, and the Axis could never lay a
minefield or build a fort.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 23.11 | Engineers have no combat value, no ZOC, are not combat units, may not enter enemy hexes | DONE | `unit_stats.json:24-25` `is_combat: false, oca 0, dca 0`; `Unit.is_combat` gates ZOC/assault/city-banking | NO |
| 23.12 | Eliminated engineers are rebuilt per 20.3 | MISSING | The 20.3 chart (scan p102) says Road/Railroad Construction = "none", footnote f: returned as a reinforcement 6 OpStages after elimination. No such re-entry path exists (grepped `reinforc` + engineer roles) | NO |
| 23.13 | Two NZ RR Construction units (railroads only); 1 SA Road Construction (roads only) | DONE | `state.py` `Unit.engineer ∈ {'', 'RAIL', 'ROAD'}`; `construction.py:83-89` `builds_rail`. *[RUN]* all three present | YES |
| 23.14 | HQs with an "E" have Engineer capability | **MISSING** | `Unit.engineer` has no HQ-E value; no HQ in any OOB carries one. The Construction Chart's `CHQᴱ`/`HQᴱ` rows are therefore unbuildable by anyone | **YES** |
| 23.21 | A unit stacked with an Engineer enters an enemy minefield for 6 CP (mot) / 3 CP (non-mot) | MISSING | No minefields (ch 26). *Note a rulebook self-contradiction: 26.24 says the cost is a flat 4 extra CP. Pick one when implementing* | NO (blocked on 26) |
| 23.22 | An Engineer spending a whole OpStage in an enemy minefield removes it | MISSING | No minefields | NO (blocked on 26) |
| 23.23 | Engineers build forts, rebuild bombed roads, build/dismantle Temporary Repair Facilities, build railroads and air facilities | **PARTIAL** | Only railroad (24.6), only by NZRRC. `construction.py:44-46` confesses the ROAD engineer "is seeded and idle" | YES |
| 23.24 | An unpinned Engineer Bn attached to a close assault on a fortified (non-city) hex shifts the differential **one column to the attacker** | **MISSING** | Not found: grepped `engineer` in `combat.py`/`combat_tables.py` — no hits. One of the few levers for cracking a fort, and it is absent | MAYBE |
| 23.25-23.26 | Misc. capabilities; no bridges/escarpments | N/A | Vacuously satisfied | NO |

---

## 24.0 CONSTRUCTION

Only **two of the Construction Chart's fifteen rows exist**: Railroad-Build and Real-Supply-Dump.
`construction.py:43-54` says so itself, and the code confirms it: `construction.py:63-64` defines
exactly two items, `RAIL` and `DUMP`, and `engine.py:1996-2000` dispatches on exactly those two.

**Construction Chart [24.17] verified against the scan (p104)** — full transcription below the table.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 24.11 | Construction Segment of the Organization Phase; completion at the start of a later Segment | DONE | `engine.py:1960-2000`, `Phase.CONSTRUCTION`, run before Movement | YES |
| 24.12 | Any CP expended halts construction; construction units ignore road/track stacking limits | DONE (first half) | The pin is structural: the Segment runs before Movement and booked units are struck from that stage (`r.building`, `engine.py:2000`). The road/track stacking exemption is not modelled | YES |
| 24.13 | Supplies must BEGIN the Segment in the hex and are expended in it | DONE | `construction.py:142-174` `stores_at`/`stores_draw` | YES |
| 24.14 | Normal supply consumption continues | DONE | Units still draw Stores/Water | YES |
| 24.15 | One project per unit; stacking applies | DONE | Implicit (one BuildOrder per gang) | NO |
| 24.16 | Construction may be ceased voluntarily | DONE | No order → no work | NO |
| 24.17 | **The Construction Chart** | **PARTIAL** | Two of fifteen rows. **CONFLICT FOUND**: the chart (p104) prices a Real Supply Dump at **10 Stores + 3 CP**; rule text 24.9 says **20 Store Points**. `construction.py:74` uses 20. Flag for a ruling | YES |
| 24.18 | **The Demolition Chart** | **MISSING** | Verified on the scan (p105); nothing in the engine demolishes anything (rail, road, pipeline, facility, fort, minefield). The 54.17 dump-blow is a different rule and is implemented | MAYBE |
| 24.21 | Hot weather: **+10 Water Points per construction site** (chart: "other than a Supply Dump") | **MISSING** | Not found: `_construction` (`engine.py:1960`) makes no water draw. Confessed at `construction.py:48` | MAYBE |
| 24.22 | No construction in a sandstorm/rainstorm hex; leaving the hex during one **restarts from scratch** | PARTIAL | `construction.py:128` blocks rail under `FOUL` ✓. But (a) `_build_dump` never checks weather, (b) the restart-from-scratch clause is absent (progress never resets), (c) the storm is theatre-wide (see 29.7) | MAYBE |
| 24.23 | Units pinned by artillery/air bombardment may not construct | **MISSING** | Not found: `_construction` never reads the pin set. Confessed at `construction.py:48` | MAYBE |
| 24.24 | Friendly non-constructing units don't interfere | DONE | Vacuous | NO |
| **24.3** (24.31-.38) | **CONSTRUCTING MINEFIELDS** — EBn/ECoy/CHQᴱ, 15 Ammo + 15 Stores, 1 OpStage; dummies 3 Stores; clear/sand-gravel/salt-marsh only; not in enemy-controlled hexes | **MISSING** | No `MINEFIELD` item exists (`construction.py:63-64`). **There is no way for a minefield to enter the game.** See ch 26 | **YES** |
| **24.4** (24.41-.48) | **CONSTRUCTING FORTIFICATIONS** — AnyE + Inf Bn (3+ TOE), 30 Stores, 3 Construction Segments; rebuild of bombed city levels allowed in an EZOC; never above Level 2 (3 at Cairo/Alex) | **MISSING** | No `FORT` item. **Neither side can build or rebuild a fortification, ever** | **YES** |
| **24.5** (24.51-.56) | **ROAD CONSTRUCTION** — unfinished-road hexes only; 2 Stores/hex; Inf Bn / ECoy 1 hex, EBn 3 hexes | **MISSING** | No `ROAD` item. The map has no unfinished-road overlay to build on (`construction.py:44-46`), and the 1 SA Road Construction Bn sits idle for 111 turns | MAYBE |
| 24.61 | Only the two NZRRC companies may BUILD rail; any engineer may REPAIR destroyed track | DONE / PARTIAL | `construction.py:83-89` ✓ build. Repair of destroyed track: MISSING (nothing destroys track — 24.66) | YES |
| 24.62 | One NZRRC = 2 OpStages/hex; two together = 1 OpStage | DONE | `construction.py:70` `RAIL_COMPANY_STAGES = 2`, one company-stage per company per Segment. Elegant and correct | YES |
| 24.63 | Any Engineer may rebuild 3 destroyed rail hexes per Segment (occupied + 2 adjacent) | MISSING | No rail destruction exists, so no repair | NO |
| 24.64 | One Store Point per rail hex, present with the engineer, expended in the Segment | DONE | `construction.py:71`; `engine.py:2050-2058` draws it from the dump on the railhead | YES |
| 24.65 | No enemy-controlled or enemy-occupied rail hex may be built | DONE | `construction.py:119-132` `rail_buildable` | YES |
| 24.66 | Rail hexes may be destroyed by air/barrage, or by an Engineer/HQᴱ/Inf-3-TOE spending one OpStage | **MISSING** | Not found: no DESTROY item, no `Destroyed RR Hex` marker. Confessed at `construction.py:47` | MAYBE |
| 24.67 | The Alexandria-Matruh-Tobruk line grows WESTWARD from the last completed hex; no hex may be skipped; unbuilt rail hexes do not exist | DONE | `construction.py:92-116` `rail_head`/`rail_next`; `engine.py:2020-2030` rejects a skip | YES |
| **24.6 as a whole** | — | **DONE BUT INERT** | *[RUN]* `CONSTRUCTION_ADVANCED = 0`, `CONSTRUCTION_COMPLETED = 0` over 111 turns. **Root cause (verified):** the NZRRC companies start at `(47,140)`; the railhead is `(26,100)`; `campaign_policy.py:389` only issues a BuildOrder for a gang *standing on the railhead*, and nothing ever marches them there. A second gate would also block it: the policy requires the next site to be ALLIED-controlled and it starts NEUTRAL. **Zero of 46 surveyed hexes are laid** | **YES** |
| 24.7 (24.71-.78) | Air facilities (airfields, strips, flying-boat basins) | **MISSING** | No `AIRFIELD` item. Air is played at the abstract 32.0/58.0 grain, so this is coherent — but 27.53 raids and 29.47 sandstorm damage both depend on it | NO |
| 24.8 (24.81-.88) | Constructing/dismantling **Temporary Repair Facilities** (250 Stores + 150 Fuel, 3 Segments; max two per player; dismantle recovers 120 Stores + 25 Fuel) | **MISSING** | No `FACILITY` item. Blocks all of 22.3 | **YES** |
| 24.9 | **Supply dumps**: 1 TOE point, 3 CP + 20 Stores. A pile of supplies you can eat from is free; what construction buys is the right for trucks *in convoy* to LOAD from it | DONE | `construction.py:177-198`, `engine.py:2068-2095`. *[RUN]* 8 dumps constructed. The Note's distinction (sink vs. link) is honoured. **Dummy supply dumps (chart: 2 CP, ≤50% of real dumps) are MISSING** — `SupplyUnit.is_dummy` exists and `is_dummy=True` is assigned nowhere | YES |

### [24.17] Construction Chart — transcribed from the scan (PDF p104)

| Item | Situation | Units | Supplies | OpStages | Restrictions |
|---|---|---|---|---|---|
| 1 Level of Fortification | Build/Rebuild‡ | AnyE + Inf Bn 3+ TOE | 30 Stores | 3 | Not in Salt Marsh, Delta or Major City hex. May be rebuilt in a Major City hex in an enemy ZOC |
| Real Minefield | Build | EBn, ECoy or CHQᴱ | 15 Ammo + 15 Stores | 1 | Clear, Sand/Gravel and Salt Marsh only |
| Fake Minefield | Build | EBn, ECoy or CHQᴱ | 3 Stores | 1 | As above |
| Railroad | Build | NZRRC | 1 Stores | 1 | Building limited to head of track |
| Railroad | Rebuild | AnyE | 1 Stores/hex | 1 | One hex + any two adjacent |
| Road | Build/Rebuild | a) Inf Bn 3+ TOE or ECoy/HQᴱ; b) EBn, or ECoy/HQᴱ + Inf Bn 3+ TOE | 2 Stores/hex | 1 | "Unfinished road" hexes only. a) occupied hex only; b) occupied + 2 adjacent |
| Temporary Repair Facility | Build | AnyE | 50 Fuel + 250 Stores | 1 | Major City or Village/Town hex only |
| Repair Facility | Rebuild 1 Level‡ | AnyE | 10 Fuel + 50 Stores | 1 | May be rebuilt in an enemy ZOC |
| Water Pipeline | Build/Rebuild | EBn or CHQᴱ | 10 Stores | 1 | From a Major City hex; limited to head of pipe |
| Airfield | Build | EBn or CSGSU | 50 Fuel + 100 Stores | 3 | Clear/Major City/Desert/Sand-Gravel |
| Airfield or Air Landing Strip | Rebuild 1 Level‡ / Build | EBn, ECoy or SGSU | 10 Fuel + 20 Stores | 1 | As Airfield |
| Flying Boat Basin | Build | EBn or CSGSU | 25 Fuel + 50 Stores | 3 | Coastal hex only |
| Flying Boat Basin/Alighting Area | Rebuild 1 Level‡ / Build | EBn, ECoy or SGSU | 10 Fuel + 10 Stores | 1 | As above |
| Port | Block 1 Level‡ | EBn or CHQᴱ | Tobruk 50 Ammo + 25 Stores; other 25 Ammo + 10 Stores | 1 | Tripoli, Bizerta, Alexandria, Aboukir, Rosetta may not be blocked |
| **Real Supply Dump** | Build | Any unit 1+ TOE | **10 Stores** | **3 CP's** | None |
| Fake Supply Dump | Build | Any unit 1+ TOE | none | 2 CP's | May not exceed 50% of the Real Supply Dumps in play |

Notes: † an item may not be constructed in an enemy ZOC unless stated. **\* if the hex is affected by Hot
Weather, an additional 10 Water Points are required for each item under construction, other than a Supply
Dump** (= rule 24.21). ‡ only one may be built/rebuilt/blocked at a time.

---

## 25.0 FORTIFICATIONS

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 25.11 | Each level gives an increasing defensive benefit (T.E.C.) | PARTIAL | See 25.22 — two of the three combat columns are right, one is wrong | YES |
| 25.12 | **Every major city is a Level 2 fortification. Cairo and Alexandria are Level 3.** Villages are not | **PARTIAL/WRONG** | `scenario.py:56` `MAJOR_CITIES = {"C4807": 2, "C4321": 2}` — **Tobruk and Bardia only**. The campaign adds the 7 Delta hexes at Level 3 (`scenario.py:1203-1205`, yesterday's fix, correct). **Benghazi is deliberately excluded** (`scenario.py:1206-1209`: "NOT added to _MAJOR_CITIES, so no 15.82 no-eviction fort"). Derna, Sollum, Mersa Matruh, Sidi Barrani, Barce, Tripoli: **all fort level 0**. *[RUN]* 9 fortified hexes in the entire campaign | **YES** |
| 25.13 | Constructed forts are Level 1 or 2 only | N/A | No fort construction (24.4) | — |
| 25.14 | Forts are reduced ONLY by air bombardment (39.37) or artillery barrage (12.5); reduced forts may be rebuilt | **PARTIAL + INERT** | `engine.py:2345-2359` `_batter_fort` and `:1039` `_air_fort` exist but are **gated behind `state.siege_rules`**, which is `True` only in `siege_of_tobruk` (`scenario.py:573`) and **`False` in the campaign** (`state.py:406` default). *[RUN]* `FORT_REDUCED = 0` in 111 turns. Also the mechanism is invented: `BARRAGE_HITS_PER_FORT_LEVEL` effective hits, not the 12.5 / Air Bombardment Table. Rebuilding: MISSING | **YES** |
| 25.15 | A reduced fort level changes the repair-facility rate | N/A | No facilities. The DRMs are transcribed (`breakdown_rates.json:die_modifiers`) and unused | NO |
| 25.16 | Forts may be reduced to Level zero | DONE | `engine.py:2357` floors at 0 | YES |
| 25.21 | **Fortifications have no effect on movement or breakdown** | **DONE** | Correct by omission — `movement.py`/`terrain.py` never read `fortifications`. A truthful pass | YES |
| 25.22 | Combat effects per the T.E.C. | **WRONG (close assault)** | **Verified on the scan (p70)**: fort L1/L2/L3 give Barrage `L1/L2/L2`, Anti-Armor `L1/L2/L2`, **Close Assault `L2/L3/L4`**. Engine: Barrage `combat_tables.py:399` `{1:-1,2:-2,3:-2}` ✓; Anti-Armor `:372` `{1:-1,2:-2,3:-2}` ✓ (correctly gated on MAJOR_CITY per note 12). **Close Assault `combat.py:84` = `level × FORT_CA_SHIFT(-2)` → -2 / -4 / -6.** Level 2 over-shifts by one column, **Level 3 by two**. The code's own comment at `combat_tables.py:325-327` admits it. Since yesterday's 25.12 fix put Cairo/Alexandria at Level 3, **the Delta now defends at -6 columns instead of -4** | **YES** |
| 25.23 | Air bombardment does not affect units/trucks/flak/dumps **in a Level 3 city**; it must be reduced to Level 2 first | **WRONG** | `engine.py:1021` `walled = r.state.fort_level(tgt) > 1` — this grants the immunity to **every Level-2 major city**, not just the Level-3 Delta. Should be `>= 3` | MAYBE |
| 25.24 | All units in Level 3 cities **ignore all pinned results** from any combat | **MISSING** | Not found: grepped `pinned` × `fort` — no hit. Cairo/Alexandria garrisons are pinnable | MAYBE |

---

## 26.0 MINEFIELDS

**The chapter does not exist.** `TerrainMap.minefields` is declared (`movement.py:37`) and
**assigned nowhere** — I grepped `minefields=` across `game/`: zero hits outside the dataclass
default. *[RUN]* `len(final.terrain.minefields) == 0`; the same in every scenario. There is no
construction path (24.3), so no minefield can ever come into being. **El Alamein without the
Devil's Gardens.**

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 26.11 | Real and dummy minefields | MISSING | No minefield entity beyond a bare `frozenset` of Coords — no real/dummy distinction | YES |
| 26.12 | Friendly vs enemy minefields differ in movement | MISSING | — | YES |
| 26.13 | An Engineer spending one full OpStage removes a real minefield (chart also allows a tank bn with 6+ TOE of Scorpions) | MISSING | Not found. Note the Scorpion flail path exists only on the Demolition Chart (p105) — `unit_stats.json` already carries a `scorpion` model | YES |
| 26.14 | Dummy minefields removed at the end of the Movement Segment they are entered in | MISSING | — | NO |
| 26.15 | A friendly minefield is flipped (revealed) when an enemy enters | MISSING | — | NO |
| 26.21 | Movement costs (T.E.C.): friendly +1 non-mot / +4 mot; **enemy +4 non-mot / +CPA motorized** | **MISSING** | `movement.step_cost` (`movement.py:57-102`) never reads `tmap.minefields`. Even a seeded minefield would be free to enter. The "+CPA" cost — a motorized unit spends its *entire allowance* to enter one hex — is the whole operational point of a minefield and it is absent | **YES** |
| 26.22 | Costs are additive with terrain; units without engineers overspend their CPA | MISSING | — | YES |
| 26.23 | A dummy costs the same to enter until revealed | MISSING | — | NO |
| 26.24 | Engineers (and units stacked with an Engineer Bn / CW HQᴱ) pay only 4 extra CP into an enemy minefield, and nothing extra into a friendly one | MISSING | — (and see the 23.21 contradiction) | YES |
| 26.25 | A vehicle entering an enemy minefield without engineers: one die per battalion / per 2nd-3rd line trucks; **5 or 6 destroys 1 TOE point** | **MISSING** | Not found: grepped `26.25`, "mines have destroyed" | YES |
| 26.26 | The defender adjusts **all** anti-armor and close-assault columns one in his favour | **PARTIAL (dead)** | `combat.py:85-86` + `combat_tables.py:335` `MINEFIELD_CA_SHIFT = -1` — correct magnitude, close assault only. `_anti_armor_step` (`engine.py:2361`) applies **no** minefield shift. Both are unreachable: `engine.py:2457` `mined = target in r.state.terrain.minefields` is always `False` | YES |

---

## 27.0 DESERT RAIDERS & COMMANDOS

**The chapter does not exist. Zero code, zero data.** I grepped `game/` and `data/` for
`lrdg`, `long range desert`, `almasy`, `sonderkommando`, `layforce`, `special air service`, `SAS`,
`raider` — **not one hit.** The only trace anywhere is `events.py:270`: "ROMMEL_CAPTURED is
RESERVED for the deferred 27.6 Raid-on-Rommel outcome (never emitted yet)".

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 27.1 (27.11-.16) | Two LRDG units, formed from max-morale Recce/AC TOE; 50 CPA; no combat | MISSING | not found (greps above) | NO |
| 27.2 | Die Sonderkommando Almasy (one unit, German ArmR/AC only) | MISSING | not found | NO |
| 27.3 (27.31-.38) | Hidden movement; no ZOC; don't stop in EZOC; **weekly resupply from a dump/oasis/bir (1 Ammo + 2 Fuel + water, or eliminated)**; never breakdown | MISSING | not found | NO |
| 27.4 (27.41-.44) | Spotting: a 6 eliminates the raider | MISSING | not found | NO |
| 27.51 | Raids happen behind enemy lines | MISSING | not found | NO |
| 27.52 | **Blow a water pipeline** (die 1-4 destroys it) | MISSING | not found. The engine does model a water pipeline (52.22 Egyptian pipeline) — it just cannot be attacked | **MAYBE** |
| 27.53 | Destroy an airfield (1-2: -1 capacity level) | MISSING | No airfield entities (24.7) | NO |
| 27.54 | Destroy grounded planes (1-2: 10%) | MISSING | Abstract air has no grounded-plane surface | NO |
| 27.55-27.56 | **Raid a supply dump** (1-2: 10% of supplies; guarded dumps roll 2d6 vs the Raw Defensive CA Points) | MISSING | not found. This is the one raid with real logistical bite | **MAYBE** |
| 27.57-27.59 | Raid unescorted truck convoys (1-2: 1 Truck Point + cargo); interception within 4 CP | MISSING | not found | MAYBE |
| 27.6 (27.61-.65) | **Raid on Rommel** (max 4 per campaign) | MISSING | `ROMMEL_CAPTURED` is declared and never emitted. Moot anyway — the campaign has no Rommel | NO |
| 27.7 (27.71-.77) | Layforce: amphibious landing from Alexandria into any coastal hex; 3 OpStages of free supply | MISSING | not found. Depends on 30.5, also missing | NO |
| 27.8 (27.81-.89) | SAS Brigade: airfield/plane raids; 30 CPA when escorted by an LRDG | MISSING | not found | NO |
| 27.9 | Desert Raider Raids Table / Raid on Rommel Table / SAS Raid Table | MISSING | The 27.91 table is cleanly OCR'd (verified on the scan p103) and transcribed nowhere | NO |

**Honest scoping**: the designers themselves say raiders "had little effect on the war" at the
operational level. The two that matter for the *logistics* game are **27.52 (blow the pipeline)**
and **27.55 (blow a dump)** — both attack the supply chain the whole campaign turns on. The rest
is colour.

---

## 28.0 PRISONERS

**The chapter does not exist. Zero code, zero data.** Grepped `prisoner`, `guard point`,
`departure point`, `escapee`, `detention`, `POW` across `game/` and `data/`: the only hits are
`combat.py:20-21`, whose own docstring says the CRT's `Capt` result "just records that some
already-counted losses are prisoners, **no board effect**", and `combat.py:43-44`
(`attacker_captured` / `defender_captured` booleans that nothing consumes).

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 28.11 | Each surrendering infantry TOE point becomes a Prisoner Point | MISSING | No Prisoner entity | MAYBE |
| 28.12 | Prisoners may be moved 3 hexes free at capture | MISSING | — | NO |
| 28.13 | Prisoners have a CPA of 8; move in the captor's Convoy Segment | MISSING | — | NO |
| 28.14 | Max 40 Prisoner Points per hex; POW Detention Camp marker | MISSING | — | NO |
| 28.15 | **One Store Point per five Prisoner Points per Operations Stage, expended before any other stores** | **MISSING** | The real cost of a big bag. CNA's campaign is full of them (Beda Fomm, Gazala, Tobruk '42) — the winner of an encirclement should be *punished* logistically, and here he is not | **MAYBE** |
| 28.16 | March them to a Departure Point (Axis: Sirte box; CW: Alexandria or Cairo) then remove | MISSING | — | NO |
| 28.17 | One Guard Point per camp, one per prisoner point when moving | MISSING | — | NO |
| 28.18 | Prisoners may be trucked | MISSING | — | NO |
| 28.2 (28.21-.26) | Guards (formed from an infantry TOE point, 0/1 assault, CPA 10) and escapes | MISSING | — | NO |
| 28.3 | Captured equipment may be used once repaired | MISSING | No captured-equipment path (22.11/22.14) | MAYBE |

---

## 29.0 WEATHER

**The 29.61 Weather Table is CORRECT.** The `docs/rules/90` OCR of it is garbage (it dropped the
Sandstorm and Rainstorm columns entirely and folded the three multi-year Game-Turn sub-columns into
Normal/Hot). `game/weather.py:33-38` recovered it, and **I re-read PDF page 101 and confirm every
cell**:

| Season | Game-Turn | Normal | Hot | Sandstorm | Rainstorm |
|---|---|---|---|---|---|
| Spring | 1-12, 49-60, 97-108 | 11-42 | 43-55 | 56-64 | 65-66 |
| Summer | 13-24, 61-72, 109-110 | 11-23 | 24-55 | 56-66 | – |
| Fall | 25-36, 73-84 | 11-35 | 36-54 | 55-61 | 62-66 |
| Winter | 37-48, 85-96 | 11-52 | – | – | 53-66 |

Two independent checks pass: every row partitions all 36 sequential-2d6 outcomes exactly, and
29.1's worked example ("a diceroll of 53 during summer results in Hot Weather") lands in
summer's 24-55 Hot band.

**On the Game-Turn column**: it says GT 1-12 = *Spring*, but 29.1's season **dates** (Spring =
March III → June II) with a Sept-III-1940 campaign start (64.2) make GT 1-12 *Fall*. The printed
GT column's season labels are rotated two seasons — and the weather content proves the labels are
right and the GT column is the misprint (a "Summer" with 56% Hot and no rain, a "Winter" with no
Hot and 28% rain are meteorologically unambiguous). `calendar.py:26`
`CAMPAIGN_SEASON_OFFSET = 24` resolves it correctly. *[RUN]* the campaign's season sequence is
fall 36 GT / winter 27 / spring 24 / summer 24 — **exactly** a Sept-III start on 12-turn seasons.
This is right, and non-obviously so.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 29.1 | Weather rolled **per Operations Stage** by season; foul → the 29.7 location roll | DONE | `engine.py:918-940`, called at `:146` inside the stage loop. *[RUN]* 333 rolls = 111 GT × 3 stages ✓ | YES |
| 29.2 | Normal: no effect | DONE | — | — |
| 29.31 | Hot occurs on **all** map sections | DONE | `engine.py:931` — no location roll for hot | YES |
| 29.32 | Hot: construction sites need water rations (24.21) | **MISSING** | See 24.21 | MAYBE |
| 29.33 | Hot: Breakdown column +1 (right) | DONE | `combat_tables.py:476` | YES |
| 29.34 | Hot: all Fuel and Water levels -5%, **in dumps as well as in trucks** | **PARTIAL/WRONG** | `engine.py:809-824` `_evaporate` iterates `state.supplies` **only**. `TruckFormation.fuel` / `.water` (`state.py:358-361`) **never evaporate.** The Axis's entire forward stock rides in lorries | **YES** |
| 29.35 | Hot: **water requirements for all units are DOUBLED** | **WRONG** | `supply.py:193-200` `water_cost` returns `base + (1 if hot else 0)` — a flat **+1**, not ×2. Its docstring blames "52.43 gives no number"; **29.35 gives the number.** A 6-TOE vehicle battalion pays 7 instead of 12. Infantry (base 1) is accidentally right. The error lands squarely on the armour, on 30% of all stages *[RUN]* | **YES** |
| 29.41 | Sandstorms occur only on certain sections; never on delta hexes | **WRONG (scope)** | `engine.py:936` `if theater and theater.isdisjoint(sections)` — the campaign's `map_sections` is `{A,B,C,D,E}`, and **every row of the 29.7 table names sections inside A-E**, so the filter never fires. *[RUN]* **68 of 68 foul rolls covered the whole theatre.** The chart puts a storm on 2-3 of 5 sections (mean 2.17). The Delta exemption is not applied either | **YES** |
| 29.42 | No construction in a sandstorm hex | DONE | `construction.py:128` — but theatre-wide | YES |
| 29.43 | No aircraft into/out of a sandstorm | DONE | `engine.py:943-947` `_air_grounded` | YES |
| 29.44 | All movement costs **doubled** in a sandstorm | DONE | `movement.py:102` `cost * 2` — but theatre-wide | YES |
| 29.45 | Sandstorm: Breakdown column +1 **if ≥50% of the unit's CP was spent in sandstorm hexes** | **WRONG** | `combat_tables.py:476` applies it to every mover unconditionally. No 50% test | YES |
| 29.46 | Sandstorms stop at the coastal hexes | N/A | No sea movement | NO |
| 29.47 | Sandstorms damage grounded aircraft (38.5) | MISSING | Abstract air has no grounded-plane surface | NO |
| 29.51 | Rainstorms occur only on certain maps | WRONG (scope) | As 29.41 | YES |
| 29.52 | No aircraft into/out of rain | DONE | `engine.py:943-947` | YES |
| 29.53 | **All depleted wells are filled during a rainstorm** | **MISSING** | `wells.py:90` states it outright: "Conservative in two ways, both deliberate: it **ignores [52.15]** (a rainstorm replenishes EVERY depleted well on the map-section, and a 111-turn campaign sees many)". *[RUN]* 38 rainstorms in the campaign, 0 wells refilled. Water is the binding constraint and this is a faucet both armies are denied | **YES** |
| 29.54 | No construction in a rainstorm | DONE | `construction.py:128` | YES |
| 29.55 | Wadi hexsides uncrossable in rain except by road; may not draw water from wadis | DONE (movement) | `movement.py:88-89`. The water half is N/A — wadis are not water sources in `wells.py` | YES |
| 29.56 | Roads have the movement cost **and breakdown rate** of tracks in rain | DONE | `movement.py:72-80` (CP) and `:118-127` (BP). Both halves — correct | YES |
| 29.57 | **River hexsides not crossed by road/rail are impassable in a rainstorm** | **MISSING** | `movement.step_cost` closes only `Hexside.WADI` under rain (`movement.py:88`). `MINOR_RIVER` and `MAJOR_RIVER` stay open | MAYBE |
| 29.58 | **No vehicle may enter a delta hex in a rainstorm** except on road/rail; units in the delta must stay | **MISSING** | Not found: no delta/rain interaction in `movement.py`. The Delta is the ground the campaign's auto-win is fought on | MAYBE |
| 29.61 | The Weather Table | **DONE — verified on the scan** | `weather.py:33-38`; `data/breakdown_rates.json:weather_table_29_61`. See above | YES |
| 29.7 | Foul Weather Location Table | DONE (data) / **INERT (engine)** | `weather.py:43-50` `{1:AB, 2:CD, 3:DE, 4:BC, 5:BD, 6:BCD}` — verified on the scan (p103). The die is rolled and the sections computed, then discarded (see 29.41) | **YES** |

---

## 30.0 THE MEDITERRANEAN FLEET (Commonwealth)

**Not one ship is ever placed on the board.** `NavalUnit(` is constructed in exactly one place in
the whole repository — `tests/test_naval.py:44`. `naval=` appears **nowhere** in `scenario.py`.
*[RUN]* `len(final.naval) == 0`; `NAVAL_BOMBARDMENT = 0`; the same in `rommels_arrival` and
`siege_of_tobruk`. `engine.py:1130` `if not r.state.naval: return`. The chapter is a fully-built,
fully-tested subsystem that has never been switched on.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 30.11-30.13 | Named ships; Gun Rating = Actual Barrage Points; AA rating; gun points = damage capacity | DONE (dead) | `state.py:289-310` `NavalUnit` — never instantiated | MAYBE |
| 30.14 | No stacking points; stack freely in coastal/sea hexes | DONE (dead) | Entity, off `units[]` | NO |
| 30.15 | Range 100 sea hexes from Alexandria (no further west than xx29 on map B) | PARTIAL (dead) | A seed-time constraint the scenario "honours" — and no scenario seeds one | NO |
| 30.16 | 2 OpStages in port per 1 at sea; max 3 consecutive at sea | PARTIAL (dead) | Only the 30.25 post-fire cooldown; `at_sea_stages` exists and is never ticked | NO |
| 30.17 | **The San Giorgio**: scuttled in Tobruk harbour; **operates as an artillery unit**, fires into adjacent hexes and at CW ships | **PARTIAL** | The harbour-blocking half is real and live (`engine.py:60`, `scenario.py:1045`, `logistics_rates.json:191` — `HARBOUR_BLOCKED`, never regenerates). **The gun half does not exist** | NO |
| 30.18 | Valletta as a second port (max 5 ships); 1 OpStage to Alexandria | MISSING | not found | NO |
| 30.21 | Ships bombard their own coastal hex; battleships/heavy cruisers reach 1 hex further | DONE (dead) | `engine.py:1104-1119` `_naval_target`, `CAPITAL_SHIP_KINDS` | MAYBE |
| 30.22 | Gun Rating = Actual Artillery Points, **no ammunition**; halved at 2 hexes | DONE (dead) | `engine.py:1121-1159` — no ammo draw; `gun_rating // 2` at range | MAYBE |
| 30.24 | One bombardment per ship per OpStage | DONE (dead) | one pass over `state.naval` | NO |
| 30.25 | A ship that bombards spends the next **two** OpStages in Alexandria | DONE (dead) | `port_cooldown = 2` | NO |
| 30.3 (30.31-.39) | Ships damaged by air/coastal guns; 6 consecutive OpStages in Alexandria per Gun Rating repaired; sunk at 0 | **MISSING** | Stated deferred at `engine.py:1129` — and true | NO |
| 30.4 (30.41-.46) | The Italian 10th Light Flotilla "Chariot" raid on Alexandria (once per campaign, planned 6 OpStages ahead) | **MISSING** | not found | NO |
| 30.5 (30.51-.59) | **Naval transport of troops between ports** — Port Personnel Capacity in Stacking Points; one transfer per port per OpStage; transporting troops cuts that port's supply capacity | **MISSING** | not found: grepped `transport`, `embark`, `debark`, `personnel`. **This is the Tobruk sea lifeline**, which the engine currently fakes with a hand-seeded convoy (`scenario.py:1124` `_campaign_tobruk_ferry_interdiction`) | **YES** |

---

## 31.0 ROMMEL

**Fully implemented. Not in the campaign.** *[RUN]* `final.rommel is None`; `ROMMEL_ANCHORED`,
`ROMMEL_MOVED`, `ROMMEL_RECALLED` all **0** across 111 turns. He exists in `rommels_arrival` and
`siege_of_tobruk` only. And there is **no way for him to arrive mid-campaign**: `GameState.rommel`
is seeded at scenario construction or never, and no `EventKind` creates him (the four ROMMEL_*
events all fold onto an existing `Rommel`). The campaign opens in September 1940 with the Italians;
Rommel lands in February 1941 (~GT 22) and the engine has no door for him.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 31.1 | CPA 60; treated as a 4WD medium truck; no combat ratings | DONE (not in campaign) | `tactics.py:34-44` `rommel_reach` — 60.0 CP, `Mobility.MOTORIZED`. He burns no fuel (flagged in-code as the 27.38 raider analogue — a small unfaithfulness) | YES |
| 31.2 | May react and retreat before assault (except vs an LRDG); retreats through EZOC with impunity | DONE-by-construction | He is an entity off `units[]` (`state.py:364-379`), so he cannot be assaulted at all and ignores EZOC (`tactics.py:41-44`). Over-satisfied rather than wrong | NO |
| 31.3 | A unit stacked with him in combat gets **+1 Morale** | DONE (not in campaign) | `engine.py:2570-2576` — added **outside** the 17.23 ±3 clamp, which is the correct exception | YES |
| 31.4 | A unit that starts and stays the OpStage with him gets **+5 CPA** | DONE (not in campaign) | `engine.py:266-279` `_rommel_anchor` → `tactics.effective_cpa` (`tactics.py:22-31`) | YES |
| 31.5 (untitled) | 2d6 each Game-Turn; a **12** sends him to Berlin and **Axis Initiative falls to 3**; he returns next turn | DONE (not in campaign) | `engine.py:281-302` `_rommel_recall` → `_initiative(axis_recalled=True)` clamps to `min(rating, 3)`. Note "falls to 3" is implemented as a **cap**, which is a no-op whenever the Axis rating is already ≤3 (the 7.2 ratings are an admitted proxy) | MAYBE |
| — | **Rommel must be able to ARRIVE (Feb 1941 / ~GT 22)** | **MISSING** | No reinforcement path creates a `Rommel`. The campaign therefore gets none of chapter 31 | **YES** |

---

## CHART FIDELITY

Everything below was checked **against the scan**, not the OCR.

| Chart | Source | Engine | Verdict |
|---|---|---|---|
| **[21.38] Breakdown Table** | PDF p102 | `combat_tables.py:407-414` | **CORRECT**, cell for cell, all 9 columns × 6 rows. The `_ocr_correction_note` in `breakdown_rates.json` is right: docs/rules/90:1176 dropped the col-41-50 `66` in the 75% row, and the engine restored it. Every column partitions all 36 rolls |
| **[8.37] Terrain Breakdown Values** | PDF p70 | `terrain.py:110-134` | **CORRECT**. **Desert = 24 confirmed** — two full-size baseline digits; contrast the `4³` in the Mot column of the same row, where the 3 is visibly a raised footnote. The long-held "Desert = 2" reading is wrong and the engine is right |
| **[8.37] Fortification combat columns** | PDF p70 | `combat_tables.py:372,399` / `combat.py:84` | **Barrage CORRECT** (L1/L2/L2). **Anti-Armor CORRECT** (L1/L2/L2, gated on Major City per note 12). **CLOSE ASSAULT WRONG** — chart is **L2/L3/L4**, engine computes `level × -2` = -2/-4/-6 |
| **[8.37] Minefield rows** | PDF p70 | — | Chart: Friendly `+1/+4 CP, 0 BP, –/L1/L1`; Enemy `+4/+CPA CP, +2 BP, –/–/–` (+ note 13's L1/L1 to the non-phasing side). **Nothing is transcribed** except a `-1` close-assault shim that never fires |
| **[22.8] Broken Down Vehicle Repair** | PDF p103 | `combat_tables.py:458-462`, `breakdown_rates.json` | **WRONG (Field/Tank): `10%*` → `100%` on die 2, 3, 4.** OCR bleed at docs/rules/90:1214-1216, inherited by the data file (which even *documents* what `10%*` means, then transcribes `100%`). Truck / AC-R / Temporary / Major columns are all correct — three of the four are never read |
| **[22.44] Destroyed Tanks Repair** | PDF p103 | — | OCR is correct. Transcribed nowhere (22.4 missing) |
| **[22.15] Vehicle Repair Supply Costs** | PDF p102 | `breakdown_rates.json` | **CORRECT.** Only the two Field rows are reachable |
| **[24.17] Construction Chart** | PDF p104 | `construction.py:70-74` | Rail row **CORRECT** (NZRRC, 1 Store, head of track). **CONFLICT: Real Supply Dump = 10 Stores + 3 CP on the chart; rule text 24.9 says 20 Store Points. Engine uses 20.** The docs/rules/90 OCR of this chart is unusable garbage ("30 Stories", "Salt Branch", "Flake Minefield") — full clean transcription is in the §24 section above |
| **[24.18] Demolition Chart** | PDF p105 | — | Nothing transcribed. Notable content: real minefields are cleared by "Any E **or tank bn with 6+ TOE of Scorpions**"; dismantling a repair facility recovers 25 Fuel + 120 Stores |
| **[29.61] Weather Table** | PDF p101 | `weather.py:33-38` | **CORRECT — all four rows, all four columns.** The docs/rules/90 OCR is unusable (it dropped both storm columns). The engine's recovery is exact. See the table reproduced in §29 |
| **[29.7] Foul Weather Location** | PDF p103 | `weather.py:43-50` | **CORRECT** as data. Functionally inert (§29.41) |
| **[27.91] Desert Raider Raids** | PDF p103 | — | OCR is clean. Transcribed nowhere |
| **[54.17] Supply Dump Demolition** | PDF p109 | `logistics_data.py:73-84` | **THE FLAGGED "OCR COLUMN-SLIP" IS NOT AN OCR ERROR — see below** |

### The 54.17 Supply Dump Demolition Table: the chart itself is broken, our transcription is right

The brief flagged this table as a suspected OCR column-slip ("a modified -1 destroys 33% while a 0
destroys nothing; a 7 undoes a 6"). **It is not a slip.** I rendered PDF page 109 at 400 dpi and
read the column alignment directly. The 1979 chart prints, with the `%` row aligned 1:1 under the
`DIE` header:

| DIE | -2 | -1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8+ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| % Supplies | 0 | **33** | 0 | 10 | 20 | 33 | 50 | 75 | 100 | **33** | 100 |

`docs/rules/90:1494-1496` reproduces this exactly. `data/logistics_rates.json`
(`supply_dump_demolition_54_17`) reproduces it exactly. `game/logistics_data.py:73-84` reproduces
it exactly **and its docstring already flags the anomaly and deliberately declines to "fix" it** —
which is the correct call for a port.

**The correct column mapping is the one we have.** The two anomalous cells (`-1 → 33` and
`7 → 33`) are almost certainly SPI print errors: the surrounding progression is strictly monotone
(0 / 10 / 20 / 33 / 50 / 75 / 100), the modifier list is explicitly cumulative and designed so a
bigger die = more destruction, and the obvious intended values are `-1 → 0` and `7 → 100`.
**Recommendation: keep the faithful transcription; add a single `_errata` note naming the two
cells, and do not silently reconcile them.** This is a rules question for the owner, not a bug.

---

## Three cross-cutting notes

1. **The weather is a scalar, and it should be a map.** `GameState.weather` is one label for the
   whole theatre. The 29.7 table exists to localise storms to 2-3 of 5 sections, and *[RUN]* the
   localisation never fires. Consequences, all of them in my chapters and all of them ~2.3x
   over-applied: construction halts (24.22), field repair is blocked (22.13d), movement doubles
   (29.44), roads become tracks (29.56), the breakdown column shifts (21.37d), air is grounded.
   The fix is contained — the engine **already rolls the die and computes the sections**
   (`engine.py:931-937`); it throws them away. Every hex knows its map section (the coordinate
   labels are `A`/`B`/`C`/`D`/`E`-prefixed), so a per-hex `weather_at(hex)` is a small,
   well-defined change to a handful of call sites.

2. **Breakdown is a debuff, not attrition.** Because `broken_down` blocks combat but not movement
   (21.44), and because field repair recovers 86% of it *[RUN]*, the desert never actually takes a
   tank away from anybody. `TOE still broken at end of campaign: 0`. Fix 22.25 and 21.44 together
   and the whole 21/22 loop — break down, leave the wreck, tow it back or lose it to the enemy —
   starts existing.

3. **The rulebook contradicts itself twice in my slice.** (a) 23.21 says a unit stacked with an
   engineer enters an enemy minefield for 6/3 CP; 26.24 says a flat 4 extra CP. (b) 24.9 prices a
   supply dump at 20 Stores; the 24.17 chart prices it at 10. (c) 24.35 permits minefields in
   "clear, sand/gravel, or **rough**" hexes; the chart says "Clear, Sand/Gravel and **Salt Marsh**".
   Someone should rule on all three before the code is written, not after.

---

## TOP FIVE — what I would fix first

1. **`combat_tables.py:461`: the 22.8 field-tank column, `100%` → `10%` on die 2/3/4.** *(S)*
   One dict. It is a straight OCR corruption of the chart, it makes armour recovery 4.4x too fast,
   and on seed 1941 it **flips the winner of the campaign** (ALLIED as-is → AXIS with the true
   chart; armour recovery 86.4% → 72.2%; net armour lost 56 → 99 TOE). Every balance number taken
   in the last month was taken with this in. Fix `data/breakdown_rates.json` in the same commit —
   the 10%\* single-TOE exception at `engine.py:1504` is already coded and becomes reachable the
   moment the cell is right.

2. **`supply.py:200`: hot weather DOUBLES water (29.35), it does not add one.** *(S)*
   `base + 1` → `base * 2`. Water is the binding constraint of the whole desert and Hot is 30% of
   all Operations Stages *[RUN]*; the error falls entirely on multi-TOE vehicle units, i.e. exactly
   the panzers whose reach the campaign is about. The docstring blaming "52.43 gives no number" is
   answered by 29.35, which gives the number.

3. **`combat.py:84` / `combat_tables.py:328`: fortification close-assault is L2/L3/L4, not
   level × 2.** *(S)*
   Replace the scalar with `FORT_CA_SHIFT = {1: -2, 2: -3, 3: -4}`. Verified against the scan.
   Level 2 currently over-shifts by one column and **Level 3 by two** — and since yesterday's 25.12
   fix put Cairo and Alexandria at Level 3, the two cities the entire war is fought for are now
   defending at -6 columns instead of -4. This gates the Axis auto-win condition (64.71). While in
   there: `engine.py:1021` `walled = fort_level > 1` should be `>= 3` (25.23 grants air immunity to
   Level 3 only), and `siege_rules` is `False` in the campaign, so **nothing can reduce a fort at
   all** — *[RUN]* `FORT_REDUCED = 0` in 111 turns.

4. **Truck Points must break down (21.11 / 22.23).** *(M)*
   380 Truck Points cross the desert for two years and the desert never touches one. Add
   `bar` (2L, already in the 54.2 chart), `bp_accumulated` and `broken_down` to `TruckFormation`,
   accrue BP in `_truck_move`, and check on stopping. The 22.23 truck-repair column is **already
   transcribed and already dead** in `combat_tables.py:459` — it comes alive for free. This is the
   single biggest missing pressure on the logistics game, and the logistics game is the game.

5. **Localise foul weather to map sections (29.7).** *(M)*
   *[RUN]* 68 of 68 storms blanketed all five sections; the chart says 2-3 of 5. The die is already
   rolled and the sections already computed at `engine.py:931-937` and then discarded. Making the
   weather a per-section map (rather than one scalar) fixes six couplings at once — 21.37d, 22.13d,
   24.22, 29.44, 29.56 and air grounding — and stops the engine from over-applying every foul-weather
   penalty by a factor of ~2.3.

**Close behind, and cheap:** the railway that never gets laid (*[RUN]* zero of 46 hexes — the NZRRC
are seeded 40 hexes from the railhead at `(47,140)` vs `(26,100)`; **S**, a data fix), and Rommel's
total absence from the campaign (**M**, needs an arrival path around GT 22).

**The big rocks, honestly scoped:** repair facilities (22.3 — the Commonwealth's whole rear-area
recovery economy; **L**), minefields (24.3 + 26 — El Alamein has none; **L**), the Mediterranean
Fleet's troop transport (30.5 — the real Tobruk lifeline; **L**). Chapters 27 (raiders) and 28
(prisoners) are the only two I would genuinely defer: the designers themselves call the raiders
operationally marginal, and prisoners cost the winner a Store Point per five points captured
(28.15) and little else. Everything else in 21-31 is load-bearing.
