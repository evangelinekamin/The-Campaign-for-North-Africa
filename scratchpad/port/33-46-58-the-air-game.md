# Rules 33-46 + 58 — THE AIR GAME — port audit

Audited 2026-07-14 against the CODE (not the docstrings) and against seven live 111-turn campaign
runs. Everything below is cited to `file.py:line`, `docs/rules/*`, or a measurement I ran.

---

## ⚠ HEADLINE — THE PREMISE OF THIS ASSIGNMENT IS WRONG, AND THAT IS THE BIGGEST FINDING

> *"MEASURED, our Malta is CAUSALLY INERT: cranking it to its rule-41.66 maximum … changes the Axis
> victory score by EXACTLY ZERO."*

**It is not inert. It is one of the strongest levers in the engine.** Held to an **identical dice
stream**, Malta at the CRT ceiling is worth:

| seed | Malta toothless | Malta at ceiling | swing |
|---|---|---|---|
| 1941 | Commonwealth Marginal **120-180** | Commonwealth Smashing **75-230** | **~95 VP** |
| 7 | **Axis Smashing 300-10** | Commonwealth Marginal **100-130** | **~320 VP — flips the winner** |

The "exactly zero" is a **measurement artefact**. `engine._interdict` draws its dice **only when an
interdiction order exists** (`engine.py:411-414`), and the engine shares one `rng` with weather, combat
and breakdown — so changing the *number* of Malta orders reshuffles the entire war and injects ±200 VP
of noise, which swamped the ~200 VP signal. **A real, decisive effect was invisible because of a
measurement bug, and the project was one step from concluding the opposite.** Full detail and the
controlled experiment: **§0a**. Fix it before tuning anything.

*(This does not let Malta off the hook — it makes it worse. Malta is a ~200-VP lever whose magnitude is
a hand-typed constant that neither player can influence. See the MALTA section.)*

---

## VERDICT (read this if you read nothing else)

**The air game is ~157 lines of executable code standing in for 1,487 lines of rulebook across
fifteen chapters.** It implements no aircraft, no squadrons, no air bases, no pilots, no flight,
no maintenance, no air-to-air combat and no flak. It is not the full Air Game (33-46) and it is
not the sanctioned abstract Air Game (58) either. It is a third, invented thing.

Line count, measured (`ast`-walked, docstrings/comments excluded):

| file | air/interdiction code |
|---|---|
| `game/engine.py` (`_air_*`, `_interdict*`, `interdict`, `_convoy_loss_pct`, `_apply_convoy_loss`) | 112 lines |
| `game/scenario.py` (`_campaign_air`, `_campaign_air_missions`, `_malta_bomb_points`, the 3 interdiction schedules) | 35 lines |
| `game/logistics_data.py` (`convoy_bombing_crt_41_66`) | 1 line |
| `game/state.py:236-286` (`InterdictionOrder`, `AirWing`, `AirMission`) | ~9 field lines |
| **TOTAL** | **~157 lines** |

The whole air force is three dataclasses:

```python
AirWing(id, side, arena in {"LAND","SEA"}, fighters: int, strike: int, recon: int)   # state.py:253
AirMission(side, kind in {"strike","fort","port","recon"}, target, turn)              # state.py:272
InterdictionOrder(lane, turn, bomb_points: int)                                       # state.py:236
```

and five behaviours: one d6 air-superiority roll per arena per OpStage (`engine.py:957` — **this
corresponds to no rule in the book**), a strike that pins exactly one unit with no die
(`engine.py:1015`), a fort-batter that always succeeds (`engine.py:1039`), a port-bomb that always
removes exactly one Efficiency Level with no die (`engine.py:1057`), and a recon that reveals
*everything* in the hex (`engine.py:1086`).

**And in the campaign, three of those five never fire at all.** Measured on `scenario.campaign()`:

```
campaign siege_rules = False        -> _air_fort  (41.37) returns immediately at engine.py:1049
air_missions kinds seeded: ['port'] -> _air_strike (41.31) and _air_recon (42.2) are never scheduled
AirWing recon values: [('LW-land', 0), ('DAF-land', 0)]   -> recon strength is zero on both sides
```

**So the entire air game of the full campaign is exactly two behaviours:** a flat −1 port-Efficiency
bomb on `PORT-Tobruk` (`_air_port`), and a CRT skim on three convoy lanes (`interdict`) — plus a d6
air-superiority roll that scales the first one. Everything else in `game/` is dead code as far as the
campaign is concerned.

**The decisive measurement.** I deleted the entire air force from the campaign state and re-ran the
convoy interdiction:

```
interdict WITH air force    : {'FUEL': 23940, 'AMMO': 311, 'STORES': 747} pct=5
interdict with NO air at all: {'FUEL': 23940, 'AMMO': 311, 'STORES': 747} pct=5
IDENTICAL -> True
```

**Convoy interdiction is byte-identical with the air force deleted.** `engine._interdict` reads
`state.interdictions` and never once reads `state.air` (`engine.py:405-417`). The campaign seeds
**zero SEA-arena air wings** (`scenario.py:1019` returns two `"LAND"` wings and nothing else), so the
`arena == "SEA"` guard at `engine.py:720` never fires either. **Malta's bombs are flown by no
aircraft.** They are an integer in a lookup table.

---

## WHICH AIR GAME ARE WE ENTITLED TO PLAY?

You asked whether ch.58 has the same exclusivity as 47/32. **It does, and it is stated more
explicitly than 47's.**

> **58.0 COMMENTARY:** "This Section covers the rules required for the Players to play the Land and
> Logistics Games **without utilizing the Air Game rules**." (`docs/rules/58-abstract-air-rules.md:6`)

> **59.61:** "If **only the Air Game is abstracted**, the Players simply ignore all Trucks and
> supplies available at/for Air facilities in the initial set-ups. Play is then governed by the rules
> in Section 58.0." (`docs/rules/59-introduction-to-scenarios.md:110`)

> **64.6:** "Why anyone would play a campaign game without the Air and/or Logistics Game(s) is beyond
> me. However, the Players should pick their start point ... and use the rules in the appropriate
> section(s) (32.0, 47.0, 58.0) and the abstracted set-up for that scenario group."
> (`docs/rules/64-...md:56`)

The four-cell matrix is:

| Playing | Abstraction section to use |
|---|---|
| Land only | **32.0** (abstract logistics AND air) |
| Land + **Air**, no Logistics | **47.0** (modifies 32.0) |
| Land + **Logistics**, no Air | **58.0** (defers to 32.0 for convoy attacks + fleet bombardment) |
| Land + Logistics + **Air** (what we are building) | **none — 33-46 and 48-57 in full** |

**So: 58 is exclusive with the Air Game, exactly as 47/32 are exclusive with the Logistics Game. We
play the full Logistics Game and intend the full Air Game, therefore neither 32 nor 58 applies to
us and we owe chapters 33-46 in full.**

Today we owe them and have not paid them — **and we have not taken the sanctioned shortcut either.**
Chapter 58 is only four rules and it is *causal*; we implement none of them (see the 58 ledger). In
particular **58.3 alone is a 4x change in Axis fuel** and it is missing. If you want a legitimate,
small, immediately-causal air game *this week*, 58 is it. If you want the one the designer meant,
it is 33-46, and — the good news of this audit — **the charts to build it are almost all present**
(see CHART FIDELITY).

---

## THE LEDGER

**Evidence shorthand, used where a rule has no implementation at all:**

> **`NO-AIR-OBJ`** = *not found.* `game/` contains no aircraft, squadron, SGSU, air-facility, pilot,
> TacAir, maneuver, bombload, flak or aircraft-ammo/fuel object of any kind. Grepped `game/` for
> `sgsu|airfield|air_facility|landing strip|squadron|pilot|tacair|maneuver|bombload|scramble|refit|rearm|flak|anti_air|sortie`
> — **every** hit is a false positive (`rearmost`, a *ground* unit's `sortie`, the rule-30.25 **ship**
> refit, or a comment). Positively: `game/oob.py:106-111` `classify()` returns `None` for every
> `"Air Strip"` / `"Airstrip"` / `"SGSU"` / `"Alighting"` counter — **the OOB loader discards air
> facilities and squadron bases at load**, and `data/oob_italian.json` + `data/oob_desert_fox.json`
> do carry them (10 Air Strips, 10 Airstrips, 2 Alighting areas, 4 SGSUs). `data/unit_stats.json`
> contains zero aircraft.

---

### 33.0 — SEQUENCE OF PLAY (AIR GAME)

Not numbered cases; audited by Stage.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 33 II.A Designation Phase | Players assign planes to Land Support **or** Strategic missions for the turn | **MISSING** | no designation step; `AirWing.arena` is a fixed seed-time label, not a per-turn choice (`state.py:265`) | YES |
| 33 II.B Axis Malta Availability Phase | Axis rolls for abstracted N-African airforce support for Malta raids | **MISSING** | `NO-AIR-OBJ`; no [44.42] table anywhere | YES |
| 33 II.C Strategic Mission Assignment | Axis → Malta raids / convoy CAP; CW → naval recon / bombing reserve | **MISSING** | `NO-AIR-OBJ` | YES |
| 33 II.D Malta Raid Phase | Axis resolves flak suppression, AA and bombing vs Maltese air facilities | **MISSING** | `NO-AIR-OBJ`; no Malta object exists — only `_malta_bomb_points()` (`scenario.py:1060`), a CW→Axis skim | YES |
| 33 III.B.1 Naval Convoy Recon Segment | CW resolves Strategic Convoy Recon | **MISSING** | 42.5 not implemented; the Axis convoy is always "located" (`engine.py:366`) | YES |
| 33 III.B.2 Convoy Lane Assignment | Axis assigns convoy CAP; CW assigns CAP / flak suppression / bombing per lane | **MISSING** | `NO-AIR-OBJ` | YES |
| 33 III.B.3 Convoy Bombing Segment | all air-to-air, flak suppression, AA, convoy bombing | **PARTIAL** | only the CRT skim survives: `engine._interdict` (`engine.py:405`) inside `_naval_convoys` (`engine.py:673-674`). No air-to-air, no flak, no losses | YES |
| 33 IV.F Land Support Air Phase (7 segments) | assign / deploy / air-to-air / flak / complete / return to base / tactical maintenance | **PARTIAL** | collapsed to `_air_support` (`engine.py:992`) at the top of the phasing side's Combat Segment. Segments 3, 4, 6, 7 (air-to-air, flak, RTB, maintenance) do not exist | YES |
| 33 VII.A Return to Base Phase | surviving strategic planes return to base | **MISSING** | `NO-AIR-OBJ` — planes have no base to return to | NO (no plane ledger to service) |
| 33 VII.B Aircraft Maintenance Phase | both players ready planes flown in the Strategic Stage | **MISSING** | `NO-AIR-OBJ`; 38.0 wholly absent | YES (it is the throttle on sortie rate) |

---

### 34.0 — THE AIRCRAFT

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 34.11 | Range = max hexes flown to a mission hex; also the return distance | **MISSING** | `NO-AIR-OBJ`. Air has no geometry at all: `AirMission.target` is a hex but nothing checks range from any base | YES (range is what makes Malta/Crete/Sicily basing matter) |
| 34.12 | Some planes have multiple ranges (extra tanks / bombload); player chooses | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.13 | TacAir = air-to-air rating; parenthesised (3) may not *initiate* | **MISSING** | `NO-AIR-OBJ` | MAYBE (needed only for a real 45.0) |
| 34.14 | Bombload Capacity in Bomb Points ("tonnage") | **MISSING** | `NO-AIR-OBJ`. `InterdictionOrder.bomb_points` is hand-set, not summed from any plane | **YES — this is the input to every bombing CRT** |
| 34.15 | Transport Capacity in TOE points / tons | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.16 | Maneuver rating, used to modify TacAir differentials | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.17 | **Fuel Consumption: Fuel Points a plane needs per mission; all consumed regardless of distance** | **MISSING** | `NO-AIR-OBJ`. Aircraft consume **zero** fuel. Measured: Axis lands **1,884,000 Fuel Points** at Benghazi over 111 turns and keeps every one | **YES — see TOP FIVE #1** |
| 34.18 | Mission Capability codes gate which missions a plane may fly | **MISSING** | `NO-AIR-OBJ` | MAYBE |
| 34.19 | All ratings live on the Aircraft Characteristics Chart 34.6 | **MISSING** | no aircraft in `data/` (grepped all `data/*.json`) | YES |
| 34.21 | Fighters class = F + FB; FB flies as fighter **or** bomber, not both | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.22 | Fighters usually fly CAP; some may strafe | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.23 | Every fighter/FB is assigned a pilot | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.24 | Some fighters may fly recon (may not initiate air-to-air, may not bomb) | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.31 | Bomber class = bombers + dive-bombers + fighter-bombers | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.32 | Bombing missions drop bombs on targets | **PARTIAL** | 4 hardcoded mission kinds exist (`state.py:283`), but no bomber and no bombload | YES |
| 34.33 | Bombers sub-typed NB / DB / TB | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.34 | Dive-bombers may bomb **and** strafe the same target | **MISSING** | `NO-AIR-OBJ`; no strafing at all | NO |
| 34.35 | Bombers may never initiate air-to-air; may gain TacAir from formation (45.36) | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.36 | Some bombers can transport (TT) | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.4 | Flying boats may only use basins / alighting areas | **MISSING** | `NO-AIR-OBJ`; `oob.py:109-111` drops "Alighting" counters | NO |
| 34.51 | Both sides get low-value transport planes | **MISSING** | `NO-AIR-OBJ` | MAYBE (Axis air-bridge fuel to the front) |
| 34.52 | Transport capacity; no vehicles/motorised (except motorcycles) | **MISSING** | `NO-AIR-OBJ` | MAYBE |
| 34.53 | Transports never initiate air-to-air, get no formation bonus | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.6 | Aircraft Characteristics Charts | **MISSING (data)** | charts **exist** in `docs/rules/90:1691` (CW), `:3609` (Italian), `:3638` (German) — **never transcribed** to `data/` | YES |
| 34.71-34.75 | Aircraft counters are location markers only; losses tracked on sheets | **N/A** | counter-handling / physical-play convenience; nothing for a computer to model | NO |
| 34.8 | Airforce reinforcements = pilots + planes + SGSUs | **MISSING** | `data/reinforcements_campaign.json` has **no aircraft** (grepped) | YES |
| 34.81 | CW air reinforcement placement; **max 10%/month to Malta**; facility-capacity cap | **MISSING** | `NO-AIR-OBJ` | YES (it is the cap on Malta's strength) |
| 34.82 | SGSU arrival + the per-nation SGSU-count formulas | **MISSING** | `NO-AIR-OBJ` | NO |
| 34.83 | Pilot reinforcements once a month via the Pilot Arrival Tables | **MISSING** | tables exist (`docs/rules/90:3511`, `:5962`, `:5982`); untranscribed | NO |
| 34.84 | Airplane reinforcements on a fixed monthly schedule, split across weeks | **MISSING** | schedules exist (`docs/rules/90:3541` CW, `:5628` Axis); untranscribed | YES |
| 34.85 | CW must **withdraw** squadrons on schedule | **MISSING** | `NO-AIR-OBJ` | MAYBE |
| 34.86-34.89 | The four reinforcement/pilot charts | **MISSING (data)** | all four present in `docs/rules/90`; none in `data/` | YES (34.86/34.87 only) |

---

### 35.0 — SQUADRON GROUND SUPPORT UNITS

**Every rule in ch.35 is MISSING. There is no squadron and no SGSU in the engine, and the OOB loader
deletes the SGSU counters it is given (`game/oob.py:106-111`).**

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 35.11 | SGSU is the base counter for a squadron; placed at an air facility | **MISSING** | `NO-AIR-OBJ` | YES (no SGSU ⇒ no refit ⇒ no sortie throttle) |
| 35.12 | SGSUs are medium-truck vehicles with a CPA; move in Truck Convoy Phase; **eliminated if an enemy unit moves adjacent and it cannot react** | **MISSING** | `NO-AIR-OBJ` | YES (overrunning airfields is a real Axis lever) |
| 35.13 | SGSUs arrive per player order; may return one GT after loss | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.14 | **Each SGSU expends 1 Stores/GT + 1 Fuel + 1 Water per OpStage; without them it may not repair planes** | **MISSING** | `NO-AIR-OBJ`; no air draw exists in `game/supply.py` | YES (a real supply drain, and the lever that grounds an air force) |
| 35.15 | Trucks may attach to an SGSU as First Line Transport | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.16 | SGSUs may build air landing strips / alighting areas (24.7) | **MISSING** | `game/construction.py` has no air-facility project (grepped) | MAYBE |
| 35.17 | **Only SGSUs can refuel/refit; refit at a foreign SGSU adds +1 to the die** | **MISSING** | `NO-AIR-OBJ` | YES |
| 35.18 | USAAF SGSUs not before 1 Aug 1942 | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.21 | One aircraft class per squadron | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.22 | Planes may not change squadron (2 exceptions) | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.23 | **Squadron ready/reserve capacities by nationality** | **MISSING** | `NO-AIR-OBJ`. **NOTE: rule text and chart CONTRADICT — see CHART FIDELITY #4** | YES (it is the sortie cap) |
| 35.24 | Pilots assigned to squadrons, not planes | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.25 | Assignment/transfer in Organization Phase, else as a transfer mission | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.26 | Reserve planes may not fly if ready capacity is flying; may not scramble | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.27 | **SGSU eliminated with planes on the ground ⇒ the planes are CAPTURED** | **MISSING** | `NO-AIR-OBJ` | MAYBE (a real event in this campaign) |
| 35.28 | Italian and German planes may not share a squadron (Italian sqns may be all-German) | **MISSING** | `NO-AIR-OBJ` | NO |
| 35.29 | Historical note on German SGSU types | **N/A** | explicitly "Players need not follow this" | NO |

---

### 36.0 — AIR FACILITIES

**Every rule MISSING. There is no air facility object.** The map data *has* them
(`data/wells.json` names 17 Landing Strips and 8 Airfields as terrain; `data/oob_italian.json` has
10 Air Strips) and `oob.classify()` throws them away.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 36.11 | Airfields are built (24.7), marked by a counter | **MISSING** | `NO-AIR-OBJ`; no air-facility project in `game/construction.py` | YES |
| 36.12 | **Airfield capacity level = 6 (max 6 squadrons / 6 SGSUs)** | **MISSING** | `NO-AIR-OBJ` | YES |
| 36.13 | Capacity limits landings and readying | **MISSING** | `NO-AIR-OBJ` | YES |
| 36.14 | **Capacity is reduced by enemy bombardment; at 0 the field is destroyed** | **MISSING** | `NO-AIR-OBJ`. This is the *mechanism by which the Axis suppresses Malta* (44.21) and it does not exist | **YES** |
| 36.15 | Desert raiders may damage airfields; land units capture/destroy by occupation | **MISSING** | `NO-AIR-OBJ`; `game/engine.py` raider code has no airfield target | MAYBE |
| 36.16 | The field has the capacity, the SGSU does the work | **MISSING** | `NO-AIR-OBJ` | NO |
| 36.17 | **An airfield is a supply dump for its SGSUs** | **MISSING** | `NO-AIR-OBJ`; no dump is flagged as an air facility | YES |
| 36.18 | Airfields have an intrinsic 1 AA Strength Point (vs strafing/dive-bombing only) | **MISSING** | `NO-AIR-OBJ`; no AA anywhere | NO |
| 36.2 | Air landing strips: capacity 1; destroyed at 0 | **MISSING** | `NO-AIR-OBJ` | YES |
| 36.3 | Flying boat basins: capacity 3, coastal | **MISSING** | `NO-AIR-OBJ` | NO |
| 36.4 | Alighting areas: capacity 1, immune to barrage | **MISSING** | `NO-AIR-OBJ` | NO |
| 36.5 | **Off-map facilities: unlimited supplies; may exceed SGSU limit; never destroyed by bombing (only reduced to 0); Axis Mediterranean bases may not be bombed at all** | **MISSING** | `NO-AIR-OBJ`. Note the last clause: **the Axis Italy/Sicily/Crete bases are bomb-proof** — the CW can never suppress the Malta raiders at source | YES |

---

### 37.0 — FLIGHT

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 37.11 | Planes have a range; transfer doubles it | **MISSING** | `NO-AIR-OBJ`; no range check exists | YES |
| 37.12 | Count hexes base→target; any path | **MISSING** | `NO-AIR-OBJ` | YES |
| 37.13 | Place a counter per class in the target hex | **N/A** | physical counter handling | NO |
| 37.14 | Scramble is a form of flight (40.3) | **MISSING** | `NO-AIR-OBJ` | NO |
| 37.15 | **No plane may fly unless fueled; and (except transfer) unless refitted** | **MISSING** | `NO-AIR-OBJ`. Our air flies free, forever | **YES — the sortie-rate throttle** |
| 37.16 | A fueled plane that flies expends all its fuel | **MISSING** | `NO-AIR-OBJ` | YES |
| 37.17 | Planes may fly without ammunition (dangerous) | **MISSING** | `NO-AIR-OBJ` | NO |
| 37.21 | Never exceed range (except transfer) | **MISSING** | `NO-AIR-OBJ` | YES |
| 37.22 | **No plane may fly into or out of a sandstorm or rainstorm hex** | **DONE** | `engine._air_grounded` (`engine.py:943-947`) gates `_air_superiority` (`:964`) and `_air_support` (`:1001`) on `weather in ("sandstorm","rainstorm")` | YES |
| 37.23 | Return to base of origin; else land elsewhere; else crash-land (die roll for plane/pilot) | **MISSING** | `NO-AIR-OBJ` | NO |
| 37.24 | **No more planes may fly than the air facility's capacity level and the SGSU's ready capacity** | **MISSING** | `NO-AIR-OBJ`. Our `AirWing.strike/fighters` is a constant integer with no cap and no attrition | **YES** |
| 37.31-37.35 | Emergency flight when an enemy unit closes on a field | **MISSING** | `NO-AIR-OBJ` | NO |
| 37.4 | Air Distance Charts | **MISSING (data)** | chart present at `docs/rules/90:95`; untranscribed | YES (needed for 41.62/42.52 range tracing) |

---

### 38.0 — AIRCRAFT MAINTENANCE

**Wholly MISSING.** This is the chapter that decides *how many sorties an air force can fly*, and
its absence is why our `AirWing` can fly the same 6 strike points every OpStage for 111 turns.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 38.1 | A ready plane is refitted + fueled (arming optional) | **MISSING** | `NO-AIR-OBJ` | YES |
| 38.21 | Refuel cost = the plane's Fuel Consumption Rating | **MISSING** | `NO-AIR-OBJ` | **YES** |
| 38.22 | Planes refueled at facilities by SGSUs | **MISSING** | `NO-AIR-OBJ` | YES |
| 38.23 | An SGSU may refuel any squadron's planes, up to its own max capacity | **MISSING** | `NO-AIR-OBJ` | NO |
| 38.24 | **Fuel is subtracted from the air facility's dump** | **MISSING** | `NO-AIR-OBJ`. No fuel leaves any dump for any aircraft, anywhere | **YES** |
| 38.25 | Planes need not be refueled; fuel never goes stale | **N/A** | permissive | NO |
| 38.26 | Extra fuel tanks trade maneuver for range; jettisonable | **MISSING** | `NO-AIR-OBJ` | NO |
| 38.31 | All planes start refitted; any non-transfer mission un-refits them | **MISSING** | `NO-AIR-OBJ` | YES |
| 38.32 | Refit in the Tactical Maintenance Segment / Strategic Maintenance Phase | **MISSING** | neither segment exists | YES |
| 38.33 | SGSU refits up to its own capacity; +1 die for foreign planes | **MISSING** | `NO-AIR-OBJ` | NO |
| 38.34 | **Roll per squadron on the Aircraft Refit Table; result is the % refitted** | **MISSING** | table present (`docs/rules/90:1354`); untranscribed | **YES — this is the sortie-rate governor** |
| 38.35 | Refit die modifiers: +1 foreign squadron, **+2 Italian planes, +1 German planes** | **MISSING** | `NO-AIR-OBJ`. (This is the rulebook's model of Axis serviceability — a large, historically-loaded asymmetry we currently give away for free) | YES |
| 38.36 | **Each squadron attempting refit expends 1 Stores Point** | **MISSING** | `NO-AIR-OBJ` | YES |
| 38.37 | Sandstorm un-refits 20% of refitted planes on the ground | **MISSING** | `NO-AIR-OBJ` | NO |
| 38.38 | Aircraft Refit Table | **MISSING (data)** | `docs/rules/90:1354` (labelled `[38.37]`); untranscribed | YES |
| 38.39 | Optional per-plane refit (2d6: CW 2-8, Ge 2-7, It 2-6) | **N/A** | explicitly optional; the by-squadron table is the rule | NO |
| 38.41 | Arming provides ammo for combat + bombs for bombing | **MISSING** | `NO-AIR-OBJ` | YES |
| 38.42 | Rearm by SGSU; **ammunition comes from the air facility dump** | **MISSING** | `NO-AIR-OBJ`. No ammunition leaves any dump for any aircraft | **YES** |
| 38.43 | **1 Ammo Point per squadron to use its TacAir; without it TacAir = 0** | **MISSING** | `NO-AIR-OBJ` | YES |
| 38.44 | **1 Ammo Point arms a bomber's entire bombload** | **MISSING** | `NO-AIR-OBJ` | YES |
| 38.45 | Bombload is expended whether used or not (incl. emergency flight) | **MISSING** | `NO-AIR-OBJ` | NO |
| 38.46 | Armament noted on the sheet | **N/A** | bookkeeping | NO |
| 38.47 | Mines / torpedoes cost 1 Ammo Point | **MISSING** | `NO-AIR-OBJ` | NO |

---

### 39.0 — MISSIONS

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 39.11 | No plane flies without a specific mission; none may fly if an enemy unit is adjacent | **PARTIAL** | `AirMission` (`state.py:272`) is a mission, but only 4 kinds and no adjacency test | NO |
| 39.12 | Shorthand notation | **N/A** | bookkeeping | NO |
| 39.13 | **Two mission areas: Strategic (CW-vs-convoy, Axis-vs-Malta) flown ONCE per Game-Turn in the Strategic Air Phase** | **PARTIAL** | interdiction *is* once/GT (`engine.py:371` matches `o.turn == state.turn`), but there is no Strategic Air Phase and no Axis-vs-Malta direction at all | YES |
| 39.14 | Tactical land support flown up to 3x/GT (once per OpStage) | **WRONG** | `AirMission.turn` is keyed to the **GAME-TURN**, and `_air_support` (`engine.py:1003`) re-selects `m.turn == r.state.turn` **in every Operations Stage** — so one scheduled mission fires **3x per game-turn**. Compare `engine.py:148-150`, where `_naval_convoys` is explicitly gated `if stage == 1:` — **the convoy author knew about the turn/stage distinction and guarded it; the air author did not.** Consequence quantified in 41.39B below | **YES** |
| 39.15 | No limit on planes per mission; capability gates mission type | **MISSING** | `NO-AIR-OBJ` | NO |
| 39.16 | Squadrons may split across missions but **not between strategic and land support** | **MISSING** | `NO-AIR-OBJ` | NO |
| 39.17 | No limit on mission types per hex | **N/A** | permissive | NO |
| 39.18 | Five mission types: fighter, bomber, transport, recon, transfer | **PARTIAL** | we have strike/fort/port/recon (`state.py:283`) — an orthogonal, invented taxonomy | NO |
| 39.19 | **One mission per plane per OpStage/Strategic Phase; a plane flying in an OpStage may not fly in the Strategic Phase** | **MISSING** | `NO-AIR-OBJ` — nothing tracks a plane, so nothing can be double-booked. Our LAND wing and the (nonexistent) SEA wing never compete for the same airframes | **YES — this is the Axis's central air dilemma: Malta *or* the desert** |
| 39.2 | Combined missions ("D" capability): strafe + bomb the same target | **MISSING** | `NO-AIR-OBJ` | NO |
| 39.31-39.37 | Voluntary aborts; maneuver test; the 25% fighter-screen rule | **MISSING** | `NO-AIR-OBJ` | NO |
| 39.38 | Involuntary abort from flak (46.3) | **MISSING** | `NO-AIR-OBJ`; the [46.3] CRT has a whole "Planes Aborted" half we do not model | NO |
| 39.41-39.44 | Night missions: separate resolution, no interception, no formation bonus, reduced flak | **MISSING** | `NO-AIR-OBJ` | NO |
| 39.5 | Air Mission Summary | **N/A (index)** | present at `docs/rules/90:961`; it is a table of contents for the missions | NO |

---

### 40.0 — FIGHTER COMBAT

**Wholly MISSING.** No pilot, no CAP, no scramble, no strafing, no flak suppression.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 40.11-40.18 | Pilots: ratings 1/2/3/4/6, assigned to squadrons, added to TacAir, retraining, bail-out recovery, the optional ace rule | **MISSING** | `NO-AIR-OBJ` | NO (pure dogfight detail; a scripted air policy never touches it) |
| 40.21-40.22 | CAP, offensive vs defensive | **MISSING** | `NO-AIR-OBJ` | MAYBE |
| 40.23 | 3+ fighters on offensive CAP project an air ZOC over 7 hexes | **MISSING** | `NO-AIR-OBJ` | NO |
| 40.24 | **No Africa-based plane may fly CAP for/against Axis convoys; Malta CW planes may fly CAP vs convoys ONLY; Axis Italy/Sicily/Crete planes may CAP for convoys** | **MISSING** | `NO-AIR-OBJ`. `AirWing.arena` LAND/SEA gestures at this (`state.py:265`) but the campaign seeds no SEA wing at all | YES (it is what makes Malta a *place* and not a number) |
| 40.25-40.27 | CAP examples; offensive CAP must engage; interception on the flight path | **MISSING** | `NO-AIR-OBJ` | NO |
| 40.31-40.34 | Scramble; the Scramble Table | **MISSING** | table present (`docs/rules/90:1382`); untranscribed | NO |
| 40.4 | Scramble Table | **MISSING (data)** | `docs/rules/90:1382` | NO |
| 40.51-40.55 | Strafing: targets are infantry, trucks-in-convoy, 1st-line trucks, **supply dumps**, grounded aircraft, tanks, **ports**, **water pipeline**; not in major cities | **MISSING** | `NO-AIR-OBJ`. **Strafing supply dumps and trucks is a direct attack on the logistics game we now model in full** | YES |
| 40.61-40.67 | Strafing procedures per target type | **MISSING** | Strafing Table present (`docs/rules/90:901`); untranscribed | YES (40.62 trucks, 40.64 dumps, 40.66 ports) |
| 40.66 | Port strafing: add ½ TacAir to the bombload, resolve on the Air Bombardment CRT | **MISSING** | `NO-AIR-OBJ` | MAYBE |
| 40.71-40.77 | Fighter flak suppression: 3 fighters neutralise 1 light/ship AA point; heavy AA cannot be suppressed | **MISSING** | `NO-AIR-OBJ` | NO |
| 40.8 | Strafing Table | **MISSING (data)** | `docs/rules/90:901` — fully OCR'd and usable | YES |
| 40.91-40.94 | Night fighters | **MISSING** | `NO-AIR-OBJ` | NO |

---

### 41.0 — BOMBING MISSIONS

**The one chapter with any implementation — and only its convoy half.**

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 41.11 | Bombers may not scramble; no air ZOC | **N/A** | vacuous — no scramble/ZOC exists | NO |
| 41.12 | One target per mission, chosen before flight | **DONE** | `AirMission.target` is a single hex/port fixed at seed time (`state.py:284`) | NO |
| 41.13 | Bombers may abort but still expend their bombload | **MISSING** | `NO-AIR-OBJ` | NO |
| 41.14 | A bomber must be refueled + refitted + armed to fly | **MISSING** | `NO-AIR-OBJ` | YES (38.0) |
| 41.15 | Bombers have parenthesised TacAir | **MISSING** | `NO-AIR-OBJ` | NO |
| 41.16 | Dual ("D") planes may strafe + bomb; FB is either fighter or bomber | **MISSING** | `NO-AIR-OBJ` | NO |
| 41.17 | Torpedoes only vs ships and ports | **MISSING** | `NO-AIR-OBJ` | NO |
| 41.21 | Land support bombing assigned in the Mission Assignment Segment; interceptable en route | **PARTIAL** | `_air_support` (`engine.py:992`) flies them; no interception exists | NO |
| 41.22 | **Resolve: air-to-air → flak → survivors drop → total Bomb Points → 2d6 read sequentially on the 41.5 CRT** | **WRONG** | `_air_strike`/`_air_fort`/`_air_port` (`engine.py:1015/1039/1057`) **roll no dice at all** and never touch the 41.5 CRT. There is no air-to-air, no flak, and no bomb-point total | **YES** |
| 41.31 | **B-CU: bomb personnel → CRT result = number of battalion-equivalents PINNED; tank/gun units count 2; major-city garrisons immune until fort ≤ 1** | **WRONG** | `engine._air_strike` (`engine.py:1015-1036`) pins **exactly one** unit — the single strongest (`_barrage_target`) — with **no die roll** and no CRT. The 41.5 CRT gives **0-7**. The fort>1 immunity **is** correctly implemented (`engine.py:1021`) | YES |
| 41.32 | B-TC: bomb truck convoys → truck units destroyed; 1st-line trucks only by "D" planes | **MISSING** | `NO-AIR-OBJ`. Trucks are the heart of our logistics game and **cannot be bombed** | **YES** |
| 41.33 | B-FS: flak destruction | **MISSING** | `NO-AIR-OBJ` | NO |
| 41.34 | B-CF: bomb ships → Damage Points | **MISSING** | `NO-AIR-OBJ`; `NavalUnit.aa_rating` exists but is explicitly "carried for the deferred air game" (`state.py:297`) | MAYBE |
| 41.35 | **B-SD: bomb supply dumps → % of each supply destroyed; +1 truck lost per 10%** | **MISSING** | `NO-AIR-OBJ`. The 41.5 CRT has a full Supply Dump row (0/10/20/30/40/50/75%) we ignore | **YES** |
| 41.36 | **B-AF: bomb air facilities → capacity levels reduced; −10% of grounded planes per level** | **MISSING** | `NO-AIR-OBJ`. **This is the entire Axis-vs-Malta mechanism (44.21) and it does not exist** | **YES** |
| 41.37 | B-F/C: bomb fortifications/cities; **only one level per OpStage** | **WRONG** | `engine._air_fort` (`engine.py:1039-1054`) reduces the fort by exactly 1 level with **no die roll**, i.e. it *always succeeds*. The 41.5 Fortification row is binary **"No Effect / Reduced"** — so we have turned a coin-flip into a certainty. (Gated behind `siege_rules`, so inert in the canonical campaign — `engine.py:1049`) | YES (when siege is on) |
| 41.38 | B-R / B-RR: bomb roads and railroads | **MISSING** | `NO-AIR-OBJ`. **We now model the Western Desert Railway as the Commonwealth's lifeline and the Axis cannot bomb it** | YES |
| 41.39A | B-MH: mining harbours (Harbor Mining Table) | **MISSING** | table present (`docs/rules/90:1420`); untranscribed | MAYBE |
| 41.39B | **B-P: bomb ports → CRT result = the number of Efficiency Levels lost (0-4)** | **WRONG** | `engine._air_port` (`engine.py:1057-1083`) removes **exactly one** Efficiency Level, **unconditionally, with no die roll and no bomb-point column**. The 41.5 Ports row gives **0-4** depending on Bomb Points and 2d6 — very often **0**. Compounded by the 39.14 bug (3 sorties/GT) and by `_port_regen` running only at stage 1, a bombed harbour loses **3 levels/game-turn and regains at most 1**. **See THE 595 below — this is fully quantified and it destroys the Tobruk siege** | **YES** |
| 41.41-41.49 | Night bombing: halved bombload, search procedure, flak shifted one column left | **MISSING** | `NO-AIR-OBJ` | NO |
| 41.51 | Air Bombardment & Secondary Barrage Table | **PARTIAL (data)** | **only the Axis-Naval-Convoy row is transcribed** (`data/logistics_rates.json` → `air_convoy_bombing_crt_41_66`). The other 7 target rows (Airfields, Landing Strips, Ports, Supply Dump, Fortification, Railroad, Road, Trucks/Flak/Combat-Units/CW-Fleet) are **not**. Full table recovered from the scan: **PDF page 107** | **YES** |
| 41.52 | Mining Harbors by Plane Table | **MISSING (data)** | `docs/rules/90:1420` | NO |
| 41.61 | Convoy lanes have listed air distances from key cities | **MISSING** | `NO-AIR-OBJ`; lanes are bare string labels (`state.py:228`) | YES |
| 41.62 | **CW bombers (Africa-based AND Malta-based) may bomb Axis convoys, within range** | **MISSING** | no bomber flies. `InterdictionOrder.bomb_points` is a hand-written constant (`scenario.py:1088`) | **YES** |
| 41.63 | Axis N-Africa fighters may not CAP convoys; Axis Med fighters may; CW may CAP or flak-suppress | **MISSING** | `NO-AIR-OBJ`; **no SEA-arena air wing is seeded at all** (verified: `[w.id for w in st.air if w.arena=="SEA"] == []`) | YES |
| 41.64 | **The CW may only attack convoys he has LOCATED (via 42.5 recon)** | **MISSING** | `engine._interdiction_for` (`engine.py:366-373`) always finds the convoy. Recon is not a precondition | YES |
| 41.65 | The 7-step convoy resolution procedure (A-G) | **PARTIAL** | only step G (bombing) exists; A-F (designation, recon, lane assignment, air-to-air, flak suppression, AA fire) do not | YES |
| 41.66 | **Convoy bombing on the 41.5 CRT: total Bomb Points → column; 2d6 read sequentially → % of cargo lost** | **DONE** | `engine._convoy_loss_pct` (`engine.py:376-389`) + `data/logistics_rates.json`. **Chart verified cell-by-cell against the scan — EXACT. See CHART FIDELITY #1** | YES |
| 41.67 | Losses divided evenly among cargo types, fractions rounded **up** | **DONE** | `engine._apply_convoy_loss` (`engine.py:392-402`): `lost = math.ceil(v * pct / 100)` per commodity | YES |
| 41.68 | Convoy bombing never affects listed reinforcements | **DONE** (vacuously) | `Convoy.cargo` carries commodities only; `Unit` arrivals come from a separate reinforcement track, untouched by `_interdict` | NO |
| 41.71-41.75 | Torpedoes | **MISSING** | `NO-AIR-OBJ`. Note **41.73**: ≥50% torpedo-armed ⇒ **+25% Bomb Points** vs a convoy — confirmed on the scan's Key (PDF p.108) | MAYBE |
| 41.81-41.86 | Bombing Tripoli/Tunisia boxes (port capacity + grounded planes only) | **MISSING** | `NO-AIR-OBJ` | MAYBE (Tripoli is the Axis's other lung) |
| 41.91 | Pinned "A" player: ½ CPA, no voluntary ZOC entry/exit, no voluntary combat | **PARTIAL** | `_air_strike` adds the victim to the shared `pinned` set (`engine.py:1035`), which is the **barrage** pin (12.44) — not the distinct 41.91 air pin | MAYBE |
| 41.92 | Pinned "B" player: no voluntary movement/combat during A's OpStage, then 41.91 applies | **MISSING** | same shared barrage pin; no A/B distinction | NO |

---

### 42.0 — NON-COMBAT MISSIONS

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 42.11-42.15 | Transfer missions (double range, one-way, no refit needed) | **MISSING** | `NO-AIR-OBJ` | NO |
| 42.21 | Recon flown by planes with "R" capability | **MISSING** | `NO-AIR-OBJ`; `AirWing.recon` is an int, seeded **0** for both sides in the campaign (`scenario.py:1029-1031`) — so recon never actually flies | NO |
| 42.22 | Recon over any hex **except major cities** | **DONE** | `engine._air_recon` (`engine.py:1091`): `if r.state.fort_level(tgt) > 1: return` | NO |
| 42.23 | **Roll 1d6 on the 42.27 table (+1 per 4 planes); the result is the NUMBER of battalion-equivalents revealed** | **WRONG** | `engine._air_recon` (`engine.py:1093-1099`) reveals **every enemy unit in the hex**, with no die roll and no count limit. The rule reveals 0-8 (or All at 13+). **We are strictly more generous than the rulebook** | MAYBE |
| 42.24 | Reveal order tanks→infantry→artillery; **defender may LIE by ±2 TOE** | **PARTIAL** | the ±2 noise is implemented (`engine.py:1097`, `rng.randint(-2,2)`) but as a *symmetric random error*, not the defender's *choice*; the reveal ORDER is not implemented | NO |
| 42.25 | No recon over a hex undergoing air bombardment | **MISSING** | `NO-AIR-OBJ` | NO |
| 42.26 | Land recon in the Tactical Land Support Phase; planes require refit | **PARTIAL** | flown in `_air_support`; no refit | NO |
| 42.27 | Air Reconnaissance of Land Units Table | **MISSING (data)** | `docs/rules/90:1390` — fully OCR'd | MAYBE |
| 42.31-42.37 | Transport missions (cargo must start in the hex; land at a friendly facility) | **MISSING** | `NO-AIR-OBJ`. **No air transport of supply exists** | MAYBE (the Axis air-bridge was real and is a fuel lever) |
| 42.41-42.48 | Airdrop / paratroops | **MISSING** | `NO-AIR-OBJ` | NO (rulebook itself calls these "in essence, hypothetical") |
| 42.51 | **CW may fly recon in convoy lanes to find the convoy and its size** | **MISSING** | `NO-AIR-OBJ`. Coupled with 41.64, this means our CW gets free perfect convoy intel every turn | YES |
| 42.52 | Range tracing from N-Africa: to a key city, then to the lane | **MISSING** | `NO-AIR-OBJ` | YES |
| 42.53 | Resolved on the Air Recon of Axis Naval Convoys Table | **MISSING (data)** | table present at `docs/rules/90:3531` | YES |
| 42.54 | Naval recon planes may not be attacked (air-to-air or AA) | **N/A** | vacuous (no air-to-air, no AA) | NO |
| 42.55-42.56 | Naval recon is Strategic; assigned in the Strategic Mission Assignment Phase | **MISSING** | no such phase | YES |

---

### 43.0 — AXIS ITALIAN-AEGEAN AIR BASES

**Wholly MISSING.** There is no Italy/Sicily/Crete box and no Axis bomber to put in it.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 43.11 | **≥75% of German He111/Ju88D/FW220 must be based in Mediterranean bases** | **MISSING** | `NO-AIR-OBJ` | YES (it is the constraint that *forces* the Axis to keep a Malta-capable bomber force off the desert battlefield) |
| 43.12 | Until GT35 (1941), 75% of German bombers in Italy/Sicily | **MISSING** | `NO-AIR-OBJ` | YES |
| 43.13 | From GT35, ≥50% of He111/Ju88/FW220 in **Crete** | **MISSING** | `NO-AIR-OBJ` | YES |
| 43.14 | One OpStage to transfer Italy↔Sicily↔Crete | **MISSING** | `NO-AIR-OBJ` | NO |
| 43.21 | **Med-based German bombers need no SGSU and expend no fuel/ammo — but must still be refitted** | **MISSING** | `NO-AIR-OBJ` | YES (it is the exemption that makes the Malta raid affordable) |
| 43.22 | Group Med bombers into notional squadrons of 6-12 for refit | **MISSING** | `NO-AIR-OBJ` | NO |
| 43.23 | **Crete bombers must raid Suez each month: 4 OpStages/month with no Crete bombing missions, no effect, no losses** | **MISSING** | `NO-AIR-OBJ`. A pure tax on Axis Crete sorties | MAYBE |
| 43.24 | Crete bombers get no CAP from Africa — they fly "naked" | **MISSING** | `NO-AIR-OBJ` | NO |
| 43.25 | Italy/Sicily bombers may coordinate with African fighters and **may raid Malta** | **MISSING** | `NO-AIR-OBJ` | YES |

---

### 44.0 — MALTA

**Wholly MISSING as a place.** See the dedicated section below.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 44.11 | The Malta map is off-scale; only the air facilities and Valletta matter | **N/A** | map presentation | NO |
| 44.12 | **Maltese air facilities are printed, permanent, unbuildable, indestructible — but may be REDUCED TO ZERO by Axis bombing** | **MISSING** | `NO-AIR-OBJ`. There is no Malta object in `game/` at all — only `_malta_bomb_points(gt)` (`scenario.py:1060`), a function of the calendar | **YES** |
| 44.13 | **Initial capacity per scenario; the CW may rebuild levels each GT via the 44.5 table (no supplies needed)** | **MISSING** | `NO-AIR-OBJ`; [44.5] table present at `docs/rules/90:5954` | **YES** |
| 44.14 | **No SGSUs on Malta; each facility LEVEL handles 18 planes (a 6-level airfield = 108 planes)** | **MISSING** | `NO-AIR-OBJ`. **This is the conversion from "Malta's health" to "how many bombers reach the convoy"** — the missing link in the whole causal chain | **YES** |
| 44.15 | Planes move freely between Maltese fields, outside the sequence | **N/A** | convenience | NO |
| 44.16 | **Malta planes need no fuel or ammo (auto-refuelled/rearmed) — but must still be REFIT like all others** | **MISSING** | `NO-AIR-OBJ`. Note: this makes Malta's *refit* (38.3) the sole throttle on its sortie rate | YES |
| 44.17 | CW planes may transfer to/from Malta and Africa within range | **MISSING** | `NO-AIR-OBJ` | MAYBE |
| 44.18 | **CW may divert AA to Malta: 1 light AA point → 1 Malta AA point; 1 heavy → 4. Max 1 replacement point/month; Malta caps at 48 AA points** | **MISSING** | `NO-AIR-OBJ`; no AA anywhere | MAYBE |
| 44.21 | **Axis bombers based in Italy/Sicily + any African plane in range may raid Malta, bombing its air facilities to reduce its refit capability** | **MISSING** | `NO-AIR-OBJ`. **The Axis literally cannot attack Malta in our engine. The arrow only points one way** | **YES** |
| 44.22 | Plus Italian/German aircraft permanently based in Italy/Sicily and otherwise not in play | **MISSING** | `NO-AIR-OBJ` | YES |
| 44.23 | **Four Availability Levels; each usable only a limited number of Game-Turns per the 44.41 chart** | **MISSING** | [44.41] present at `docs/rules/90:6002`: **Campaign Game = Level I unlimited, II ×25 turns, III ×12, IV ×12**. Untranscribed | **YES — this is the Axis's Malta budget, and the central strategic choice of the whole air game** |
| 44.24 | Malta raids happen in the Strategic Air Phase, once per GT; resolved normally (air-to-air, AA, bombing) | **MISSING** | `NO-AIR-OBJ` | YES |
| 44.25 | Compute planes available from the 44.42 table, then add map-based planes | **MISSING** | [44.42] present at `docs/rules/90:6016`; untranscribed | YES |
| 44.26 | Assign map-based planes only after rolling the table | **MISSING** | `NO-AIR-OBJ` | NO |
| 44.27 | May not add more map-based planes of a type than the table granted | **MISSING** | `NO-AIR-OBJ` | NO |
| 44.28 | Losses fall only on planes actually in play, pro-rata | **MISSING** | `NO-AIR-OBJ` | NO |
| 44.29 | May cancel a raid after rolling — the Level is still spent | **MISSING** | `NO-AIR-OBJ` | NO |
| 44.3 | **The Axis may NOT invade Malta** | **DONE** (vacuously) | there is no Malta hex and no invasion path; the prohibition holds trivially | NO |
| 44.41 | Axis Strategic Airforce Commitment Chart | **MISSING (data)** | `docs/rules/90:6002` — fully OCR'd and usable | **YES** |
| 44.42 | Axis Malta Availability Table | **MISSING (data)** | `docs/rules/90:6016` — fully OCR'd and usable | **YES** |
| 44.5 | Maltese Air Facility Construction Table | **MISSING (data)** | `docs/rules/90:5954` — fully OCR'd (DIE 1→0, 2-5→1, 6→2 levels) | **YES** |

---

### 45.0 — AIR-TO-AIR COMBAT

**Wholly MISSING**, and *replaced* by an invention: `engine._air_superiority` (`engine.py:957-979`)
adds one d6 to each side's `fighters` integer per arena and scales the loser's strike/recon by
`AIR_SUPERIORITY_LOSER_SCALE = 0.5` (`engine.py:45`). **This corresponds to no rule in the book** —
not in 45, and not in 58 either (ch.58 has no air-to-air mechanic of any kind).

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 45.11-45.19 | Air-to-air occurs in a hex, before flak and before missions; screening; who is the attacker; per-plane match-ups | **MISSING** | replaced by one d6 roll (`engine.py:969`) | NO (dogfight detail; a scripted air policy never exercises it — but see the caveat below) |
| 45.21-45.25 | Fighter vs fighter: defender lays out planes, attacker must cover every one | **MISSING** | `NO-AIR-OBJ` | NO |
| 45.31-45.35 | Fighter vs screened non-fighters, with the excess-fighters rule | **MISSING** | `NO-AIR-OBJ` | NO |
| 45.36 | **Formation flying: 6-17 bombers +1 TacAir each; 18+ bombers +2** | **MISSING** | `NO-AIR-OBJ` | NO |
| 45.4 | Maneuver Adjustment Chart | **MISSING (data)** | `docs/rules/90:1428` — OCR'd, and **I verified it against all three worked examples in rule 45: 3/3 exact** | NO |
| 45.5 | TacAir Kill Table | **MISSING (data)** | `docs/rules/90:1445` — OCR'd; verified 3/4 against the rulebook's worked examples (**see CHART FIDELITY #5**) | NO |
| 45.61-45.66 | Plane and pilot recovery (1 Stores + 1 Fuel per repair attempt) | **MISSING** | Recovery table present at `docs/rules/90:1371` | NO |
| 45.7 | Extended range trades maneuver; jettison to recover it | **MISSING** | `NO-AIR-OBJ` | NO |

> **Caveat on "NO".** Individually, 45's cases are dogfighting detail. **Collectively they are the
> attrition engine of the air war** — the thing that makes an air force a wasting asset you must
> husband. Our `AirWing.fighters` is a constant that never dies. If you want the Malta duel to have
> *stakes*, something must kill aeroplanes; it need not be 45.0 in full, but it must exist.

---

### 46.0 — ANTI-AIRCRAFT FIRE (FLAK)

**Wholly MISSING. There is no AA/flak anywhere in the engine.** No unit carries an AA rating; the
[46.3] CRT is not transcribed; flak consumes no ammunition.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 46.11 | Many units have an AA rating; **AA Points = TOE × AA rating (no ÷10)** | **MISSING** | `NO-AIR-OBJ`; `data/unit_stats.json` has **zero** AA/flak/anti_air keys (grepped) | YES (it is what makes bombing *cost* something) |
| 46.12 | Flak units with a parenthesised defence rating defend only if alone; 88s/90mms are artillery-like | **MISSING** | `game/oob.py:119` maps Italian `(AA)` counters to `"antitank"` — **AA units are loaded as anti-tank guns** | MAYBE |
| 46.13 | Flak treated as artillery for transport | **MISSING** | `NO-AIR-OBJ` | NO |
| 46.14 | **Flak units consume supplies and expend ammunition when firing** | **MISSING** | `NO-AIR-OBJ`; `data/logistics_rates.json` **does** carry `ammunition_consumption/…/anti_air_single_target_group` (the 50.2 rate) — transcribed, but **nothing reads it** | YES |
| 46.15 | Certain tanks/recce have AA points per TOE | **MISSING** | `NO-AIR-OBJ` | NO |
| 46.16 | Tanks may fire AA only at strafers/dive-bombers | **MISSING** | `NO-AIR-OBJ` | NO |
| 46.17 | Pure AA units stack free in cities; 1 free at a strip, 3 at an airfield | **PARTIAL** | `game/stacking.py:37` implements the **city** half (`u.is_pure_aa and terrain == MAJOR_CITY`) and its own comment says *"(city; airfield/strip later)"* — the airfield/strip half is explicitly deferred | NO |
| 46.21 | AA only at planes flying missions in the same hex | **MISSING** | `NO-AIR-OBJ` | YES |
| 46.22 | Infantry/recce/tanks may fire AA only at the fighter/strafe/dive-bomb target group | **MISSING** | `NO-AIR-OBJ` | NO |
| 46.23 | AA fires after air-to-air and flak suppression | **MISSING** | `NO-AIR-OBJ` | NO |
| 46.24 | Flak-suppression and naval-recon planes may not be hit by AA | **MISSING** | `NO-AIR-OBJ` | NO |
| 46.25-46.27 | Target groups (5 kinds); AA may fire at as many as it likes | **MISSING** | `NO-AIR-OBJ` | NO |
| 46.28 | Replacement Points may not use AA ratings until absorbed | **MISSING** | `NO-AIR-OBJ` | NO |
| 46.3 | **Anti-Aircraft Combat Results Table** | **MISSING (data)** | **not in `docs/rules/90` at all** — only the index entry at `:1659` ("page 13"). **I recovered it from the scan: PDF page 108.** It has two halves (Planes Destroyed / Planes Aborted) × 10 flak-point columns | YES |
| 46.4 | Flak Adjustment Chart (AA density) | **MISSING (data)** | `docs/rules/90:1436` — OCR'd (1-23→0, 24-47→1, 48-71→2, 72+→3 columns) | NO |

---

### 58.0 — ABSTRACT AIR RULES

**All four rules MISSING.** This is the *sanctioned* shortcut and we have not taken it. Note again
that 58 is **exclusive** with the Air Game — implementing it is a fork, not a stepping stone —
**except** that 58.3's fuel tax has a direct analogue in the full game (aircraft eat Fuel Points),
so "aircraft consume fuel" is on the path to both.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 58.1 | **Convoy attacks per 32.0: Bomb Points come from the [32.66] chart, keyed on the westernmost qualifying Allied DIVISION; resolved on the 41.5 CRT. Axis coastal + both sides' tactical shipping may NOT be attacked** | **MISSING** | `engine._interdiction_for` (`engine.py:366`) reads a **static hand-written schedule** (`scenario.py:1088`). The [32.66] chart is present at `docs/rules/90:5610` and **is not transcribed**. Under 32.64 the CW's convoy bomb strength is a **live function of how far west his army has pushed** — a real causal loop from the ground war to the sea lane. We have replaced it with a calendar | **YES** |
| 58.2 | Axis attacks on the CW fleet per 32.7 (1 die + 2 in a campaign = number of attacks; column = 1d6+2 in from the left) | **MISSING** | `NO-AIR-OBJ`; no Axis-vs-fleet path exists | MAYBE |
| 58.3 | **"The Axis Player loses three-quarters of all fuel actually brought into a port on the instant of its unloading (considered to be used for airplanes). This loss is incurred BEFORE any loss for evaporation."** | **MISSING** | **not found**: grepped `game/` for `58.3`/`0.75`/`75%`/`three.quarter`/fuel-tax — nothing. **Measured: the Axis lands 1,884,000 Fuel Points at Benghazi over 111 turns and keeps 100% of them.** Under 58.3 he keeps 471,000. Under the full Air Game his aircraft eat it (34.17/38.2/38.24). **We model neither. The Axis air force is fed on air.** | **YES — TOP FIVE #1** |
| 58.41 | Initial setups reduced by the Truck Points that would supply air facilities | **MISSING** | `NO-AIR-OBJ` | MAYBE |
| 58.42 | **Both sides lose trucks each month to abstracted strafing/bombing, per the Abstract Truck Loss Chart** | **MISSING** | **not found**: no truck-loss-to-air anywhere. Chart **[58.5]** recovered from the scan: **PDF page 108** (monthly %CW/%Axis, 1940-1943) | **YES — trucks are the binding constraint of this campaign and air currently costs zero of them** |
| 58.43 | **Both sides lose 10% (round up) of all truck points arriving in N. Africa** (CW Truck Production Table + Axis Replacement Pool) | **MISSING** | not found | YES |
| 58.44 | Abstract Truck Loss Chart | **MISSING (data)** | **not in `docs/rules/90`**; recovered from the scan at **PDF page 108** as `[58.5]` | YES |

---

## 0a. ⚠ MEASUREMENT HAZARD — the interdiction schedule DESYNCHRONISES THE RNG STREAM

**Read this before you A/B anything else in this engine.** It invalidates a class of experiment you
are almost certainly already running.

`engine._interdict` (`engine.py:405-417`) draws its two CRT dice **only when an `InterdictionOrder`
covers the lane and turn**:

```python
    order = _interdiction_for(state, convoy)
    if order is None:
        return dict(convoy.cargo), None, 0, 0, ()          # <-- NO rng draw
    d1, d2 = rng.randint(1, 6), rng.randint(1, 6)          # <-- 2 draws, only if an order exists
```

The docstring calls this a *feature* ("an interdiction-free lane draws no rng ... byte-identical").
It is a feature for **byte-identity of untouched scenarios**. It is a **trap for A/B testing**,
because the engine shares **one `rng`** across weather, combat, breakdown and everything else. Change
the *number* of interdiction orders and you change the *length* of the draw stream, and every
downstream roll in the campaign shifts.

I hit this directly. Three 111-turn runs at seed 1941, varying only the lane-2 schedule:

| variant | lane-2 orders | rng draws | 64.73 result |
|---|---|---|---|
| Malta **OFF** | 0 | 0 | **Axis Smashing Victory, 300-70** |
| Malta **as-shipped** | 95 | 190 | **Commonwealth Smashing Victory, 75-230** |
| Malta **MAX** (500 bp) | 111 | 222 | **Axis Decisive Victory, 275-130** |

**Non-monotone and incoherent**: *more* Malta bombing swings the game back to the Axis. That is not a
causal effect — **these are three different random campaigns.** The VP spread is the campaign's
seed-to-seed variance (±200 VP), and it **completely swamps and masks** the real Malta signal.

### And when you control for it properly, Malta turns out to be MASSIVELY causal.

The correct A/B holds the draw count **fixed** and varies only the CRT column. Bomb Points **1-20** is
the flat-0% column (verified against the scan): it draws the same two dice and denies nothing. So
`bomb=1` vs `bomb=500` gives **111 orders and 222 draws in both arms** — an identical dice stream, with
only Malta's teeth differing. Two seeds, full 111-turn campaigns:

| seed | arm | lane-2 FUEL landed | AMMO | STORES | **64.73 RESULT** |
|---|---|---|---|---|---|
| **1941** | Malta toothless (bomb=1) | 1,884,000 | 31,134 | 75,338 | Commonwealth **Marginal** Victory **120-180** |
| **1941** | Malta at ceiling (bomb=500) | 1,551,440 | 22,522 | 54,119 | Commonwealth **Smashing** Victory **75-230** |
| | **⇒ Malta is worth** | | | | **−45 Axis VP, +50 Allied VP (~95 VP swing)** |
| **7** | Malta toothless (bomb=1) | 1,808,800 | 29,260 | 72,788 | **Axis Smashing Victory 300-10** |
| **7** | Malta at ceiling (bomb=500) | 1,427,840 | 21,312 | 51,228 | Commonwealth **Marginal** Victory **100-130** |
| | **⇒ Malta is worth** | | | | **−200 Axis VP, +120 Allied VP — IT FLIPS THE WINNER** |

*(Control check: the toothless arm lands **1,884,000** Fuel at seed 1941 — byte-identical to the
Malta-OFF arm's 1,884,000. The dice are drawn and discarded exactly as intended. The control is clean.)*

**So the finding is the opposite of the premise.** Malta is not causally inert. Held to the same dice,
**Malta swings the campaign by 95 to 320 Victory Points and flips the winner outright at seed 7.** The
"cranking Malta to its maximum changes the Axis score by EXACTLY ZERO" measurement was **an artefact of
the RNG desynchronisation** — the naive A/B reshuffled the war, and the ±200 VP of noise it injected
hid a ~200 VP signal.

**Consequences.**

1. **Every experiment that adds or removes a conditionally-drawn die is measuring RNG-stream position,
   not the thing you changed.** This is a live, load-bearing measurement bug and it has *already*
   produced one badly wrong conclusion about the most important mechanic in the campaign.
2. **The structural fix** is to give interdiction (and every other optional roll) its **own
   `random.Random`**, or to draw-and-discard unconditionally, so that adding a feature cannot reshuffle
   the rest of the war. **Do this before you tune anything.**
3. Note the irony worth recording: the `_interdict` docstring *advertises* the conditional draw as a
   feature ("an interdiction-free lane draws no rng ... byte-identical"). Byte-identity of untouched
   scenarios is a fine goal; it was bought here at the price of every A/B the project wants to run.

### What this does NOT excuse

Malta being *potent* does not make it *right*. It is still a hand-typed calendar with **no producer and
no Axis counterplay** (see the MALTA section). The corrected picture is worse, not better: **Malta is a
200-Victory-Point lever whose magnitude is an arbitrary constant that neither player can influence.**
A decisive mechanic that is neither earned nor contestable is the least defensible thing in the engine.

---

## 0. THE 595 — the flat port-bomb × the 3x-per-turn bug kills the Tobruk siege on Game-Turn 2

This one is worth its own section because it is a complete, airtight causal chain from two small code
defects to "the campaign's centrepiece never happens", and because the arithmetic closes **exactly**.

**The two defects.**

1. `engine._air_port` (`engine.py:1057`) removes a **flat 1 Efficiency Level per call**, with no die
   and no CRT (should be a 2d6 roll on the [41.5] Ports row for **0-4**, most often 0).
2. `engine._air_support` (`engine.py:1003`) re-flies every `turn`-keyed mission **in all three
   Operations Stages** (39.14). `_naval_convoys` is correctly gated `if stage == 1:` (`engine.py:148`);
   `_air_support` is not.

`scenario._campaign_air_missions` (`scenario.py:1055`) seeds one `port` mission against `PORT-Tobruk`
per side per game-turn. `_air_port` refuses the side that *holds* the port, so only the Commonwealth
actually bombs it. Net: **the Axis's own Tobruk harbour takes 3 Efficiency Levels of damage every
game-turn** — and `PORT-Tobruk` is `HARBOUR_BLOCKED` (`engine.py:65`), so it **never regenerates**.

**The arithmetic, and the measurement.**

`PORT-Tobruk` is the 55.3 chart's 1,700-ton harbour at Efficiency 5/5. At 4 tons per Ammunition Point
(54.5) that is a landing ceiling of 425 AMMO/OpStage, scaling with efficiency:

```
   eff 5/5 -> 425      eff 3/5 -> 255      eff 1/5 ->  85
   eff 4/5 -> 340      eff 2/5 -> 170      eff 0/5 ->   0
```

```
  GT1 stage 1 : convoy lands at eff 5                        -> 425 AMMO
  GT1 stages 1,2,3 : CW _air_port fires 3x   eff 5 -> 2
  GT2 stage 1 : convoy lands at eff 2                        -> 170 AMMO
  GT2 stages 1,2,3 : CW _air_port fires 3x   eff 2 -> 0      (never regenerates)
  GT3 .. GT111 :                                             ->   0 AMMO
  ----------------------------------------------------------------------
  TOTAL                                                          595 AMMO
```

**Measured over the full 111-turn campaign: lane 6 (Axis → Tobruk) lands exactly 595 Ammunition
Points.** 425 + 170 = 595. The chain closes to the point.

**What this destroys.** The whole "siege of Tobruk as a duel" that `scenario.py:1034-1057` is written
to stage — *"the holder is fed by sea, the besieger must bomb the quay shut"* — **does not happen.**
The harbour is shot to zero on Game-Turn 2 and stays there for 109 turns. Meanwhile the Commonwealth
ferry (`SEA-TOBRUK`) lands **0** all game, because the Axis holds Tobruk from GT1 and rule 56.15
cancels it. **Tobruk is fed by nobody, all war.** There is no duel, no lifeline, and no siege — just a
harbour that was switched off on turn 2 by an air force that rolled no dice.

Fixing 41.39B (roll on the CRT) and 39.14 (fire once per OpStage, not three times per turn) is what
turns this back into the contest the scenario was written to be.

---

## 1. CHART FIDELITY

I pulled the source scan (`tmp/The Campaign for North Africa.pdf`, 134 MB) and rendered the chart
pages with `pdftoppm` to check every air chart we reference.

**The headline is good news, and it is the opposite of the 54.17 story.**

### #1 — The [41.66] convoy-bombing CRT is **EXACT**. Verified cell-by-cell against the scan.

This is the only air chart we have transcribed, and it is right. `data/logistics_rates.json` →
`axis_naval_convoys_56.air_convoy_bombing_crt_41_66` matches the **Axis Naval Convoy** row of the
[41.5] Air Bombardment & Secondary Barrage Targets Table on **PDF page 107**, cell for cell:

| Result | 1-20 | 21-40 | 41-80 | 81-120 | 121-160 | 161-200 | 201-260 | 261-320 | 321-390 | 391-470 | 471+ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0% | 11-66 | 11-54 | 11-33 | 11-22 | – | – | – | – | – | – | – |
| 5% | – | 55-64 | 34-64 | 23-54 | 11-45 | 11-32 | 11-21 | 11-14 | – | – | – |
| 10% | – | 65-66 | 65-66 | 55-64 | 46-63 | 33-56 | 22-51 | 15-42 | 11-23 | 11-15 | – |
| 20% | – | – | – | 65-66 | 64-66 | 61-66 | 52-63 | 43-56 | 24-51 | 16-34 | 11-24 |
| 25% | – | – | – | – | – | – | 64-66 | 61-66 | 52-63 | 35-52 | 25-36 |
| 30% | – | – | – | – | – | – | – | – | 64-66 | 53-63 | 41-54 |
| 40% | – | – | – | – | – | – | – | – | – | 64-66 | 55-63 |
| 50% | – | – | – | – | – | – | – | – | – | – | 64-66 |

Bomb-point brackets match. Every column partitions all 36 sequential 2d6 codes. Expected loss is
monotone increasing (1.4% → 29.2%). **No column slip. No transcription error.**

One wording note worth recording: rule 41.66 says the result is *"in tens of percent of the cargo"*.
It is **not** — the chart's own Result column reads `0% 5% 10% 20% 25% 30% 40% 50%`, and rule 47.65
("a result of 10%… a result of 20%… a result of 30% or greater") confirms these are plain
percentages. **`engine._apply_convoy_loss` follows the chart, which is correct**; 41.66's phrasing is
a rulebook infelicity. Leave the code alone.

### #2 — The [41.5] table is only **1/8th** transcribed.

The Bomb-Points column headers on the scan are exactly our brackets. But the table has **eight target
rows** and we have transcribed **one**:

| Target row | Result semantics (from the Key, PDF p.108) | In `data/`? |
|---|---|---|
| Airfields / Air Landing Strips / **Ports** | 0-4. *"Ports: reduce the Port by that number of Efficiency Levels."* | **NO** |
| Supply Dump | 0/10/20/30/40/50/**75%** of all supplies + 1 truck per 10% | **NO** |
| Fortification | **No Effect / Reduced** (binary!) | **NO** |
| Railroad | No Effect / Destroyed | **NO** |
| Road | No Effect / Destroyed | **NO** |
| Trucks, Flak Suppression, Combat Units, CW Fleet | 0-7 (trucks destroyed / TOE killed / **battalions pinned** / damage points) | **NO** |
| **Axis Naval Convoy** | **% of cargo** | **YES — exact** |

The same table also carries **Torpedo Points** and **Barrage Points** header rows mapping onto the
same columns — so transcribing [41.5] also unblocks **41.7** (torpedoes) and **12.5** (barrage
against secondary targets, another slice's problem).

The Key also confirms **41.73** verbatim: *"If at least 50% of the planes attacking an Axis Naval
Convoy are armed with Torpedos, increase the total Bomb Points by 25%."*

**This missing 7/8ths is why `_air_port`, `_air_fort` and `_air_strike` roll no dice: there was no
table for them to roll on.** They invented flat results instead. That is the single highest-leverage
transcription job in the air game.

### #3 — Two charts are **absent from the OCR corpus entirely** and I recovered both from the scan.

- **[46.3] Anti-Aircraft Combat Results Table** — *not in `docs/rules/90`* (only the index line at
  `:1659`, "page 13"). **It is on PDF page 108**, and it is legible: two halves ("No. Planes
  Destroyed" / "No. Planes Aborted") × ten flak-point columns (1-4, 5-8, 9-12, 13-16, 17-20, 21-24,
  25-28, 29-32, 33-36, 37+), plus a third block for "Planes on fighter missions".
- **[58.5] Abstract Truck Loss Chart** — *not in `docs/rules/90`*. Also on **PDF page 108**: a
  month × year grid (1940-1943) of `%CW/%Axis` truck losses. This is the chart rule 58.42/58.44 needs.

`docs/rules/99-foldout-charts.md` is **entirely empty of data** — all eleven foldouts are stubbed
*"not OCR-able; see the original scan"*. Anything the audit trail says lives in "99" lives nowhere.

### #4 — **A genuine rules-vs-chart contradiction in the source: [35.23] squadron capacity.**

| Source | CW squadron 1940→mid-41 | CW squadron later |
|---|---|---|
| **Rule text** (`docs/rules/35-...md:55-57`) | **15 ready / 5 reserve (20)**, "1940-June '41" | 18/6 (24), "July 41-43" |
| **Chart [35.23]** (`docs/rules/90:1351-1352`) | **12 ready / 4 reserve (16)**, "1940-41" | 18/6 (24), "1942-43" |

Both the *numbers* and the *date break* disagree. Whoever ports ch.35 must pick one and record the
choice. (Italian 9/3 and German 12/4 agree in both places.)

### #5 — [45.5] TacAir Kill: 3 of the rulebook's 4 worked examples match; one does not.

I checked the OCR'd [45.4] and [45.5] charts against the worked examples inside rules 45.0 and 45.36:

```
45.4  maneuver diff 4  -> adj 2   (rule says 2)   OK
45.4  maneuver diff 11 -> adj 3   (rule says 3)   OK
45.4  maneuver diff 16 -> adj 4   (rule says 4)   OK
45.5  CR42  diff -2 -> kill<=12   (rule: "an 11 or 12")  OK
45.5  Hurr  diff +2 -> kill<=16   (rule: "an 11-22")     ** MISMATCH **
45.5  Ju88  diff -5 -> kill<=11   (rule: "rolls an 11")  OK
45.5  Hurr  diff +5 -> kill<=26   (rule: "an 11-26")     OK
```

[45.4] is verified 3/3. [45.5] is verified 3/4; the lone mismatch is example 45(a)'s Hurricane at
+2 differential. Given the other three match the chart *exactly*, the chart is almost certainly right
and the example text is a rulebook typo (11-22 for 11-16) — but **re-read PDF page 11 before
trusting the OCR here.** Low priority (we implement none of 45).

### #6 — The Aircraft Characteristics Charts are **present and usable**, with a shifted header.

`docs/rules/90:1691` (Commonwealth), `:3609` (Italian), `:3638` (German). The OCR'd header row has a
spurious blank column and dropped "Manufacturer", so the columns *look* misaligned — but the **data
is intact**. Decoded against the rulebook's own examples:

```
| Hurricane Mk. I | 52 | 4 | 32 | - | 1 | ! | Hawker |
   -> Range 52, TacAir 4, Maneuver 32, Bomb -, Fuel 1, Capability !, Mfr Hawker
```
Rule 45's example (a) states the Hurricane I has "a tacair of 4" and "Maneuver Rating… 32". **Match.**
Rule 45's example (b) gives the Hurricane IIB TacAir 6 and an 11-point maneuver edge over the Ju88.
**Match.** So the charts can be transcribed as-is; just re-map the header.

**Net chart verdict: the air game is PORTABLE. Nearly every chart is either already in
`docs/rules/90` or recoverable from `tmp/The Campaign for North Africa.pdf` (pages 107-108). The
blocker was never the data.**

---

## 2. MALTA, SPECIFICALLY

### What the rulebook's Malta is

A **place with health**, sitting in a two-way causal loop:

```
   Malta air-facility LEVELS  (44.12, 44.13, 36.14)
        |  each level = 18 planes  (44.14)
        v
   bombers/torpedo planes over the convoy lanes  (41.62, 40.24)
        |  sum of their BOMBLOAD CAPACITIES = Bomb Points  (34.14, 41.66)
        v
   the [41.5] CRT column  ->  2d6  ->  % of the Axis convoy's cargo destroyed  (41.66, 41.67)

   ...and back the other way:

   Axis picks a Malta Availability LEVEL (I-IV) from a FIXED BUDGET  (44.23, 44.41:
        campaign = I unlimited, II x25 turns, III x12, IV x12)
        v
   rolls 44.42 for how many Italy/Sicily planes + how many free "off-board" planes
        v
   raids Malta: air-to-air, flak, then bombs the AIR FACILITIES  (44.21, 44.24, 41.36)
        v
   Malta's LEVELS drop  ->  fewer planes  ->  fewer Bomb Points  ->  more Axis supply lands
        v
   CW rebuilds levels each GT on the 44.5 table (1d6: 0/1/1/1/1/2)  (44.13)
```

Malta is therefore **the Axis player's central strategic dilemma**: every Availability Level spent on
Malta is a bomber not over the desert, and the budget is finite (25/12/12 turns). It is a *duel*.

### What our Malta is

```python
def _malta_bomb_points(gt: int) -> int:          # scenario.py:1060
    year, month = calendar.gt_to_month(gt)
    if year <= 1940: return 100
    if year == 1941:
        if month <= 6:  return 200
        if month <= 10: return 300
        return 500                                # Nov-Dec 1941: Force K at its peak
    if month <= 4: return 0                       # Jan-Apr 1942: the Luftwaffe blitz
    if month <= 7: return 150
    return 400
```

**A hardcoded calendar.** It has:

- **no producer** — no aircraft, no air facility, no level, no squadron. The Bomb Points are typed in.
- **no Axis input** — the Axis cannot raid Malta. The Jan-Apr 1942 suppression is not *earned* by the
  Luftwaffe; it is written into an `if`. Rule 44's entire Availability Level budget (the thing the
  Axis player is supposed to *spend*) does not exist.
- **no feedback** — nothing the CW does can strengthen Malta, nothing the Axis does can weaken it.
- **no aircraft at all**: I deleted the entire air force and re-ran the interdiction — **byte-identical**.

It is not the rulebook's Malta under the **full** Air Game (44.0), and it is not the rulebook's Malta
under the **abstract** Air Game either — **because under 58/32 Malta does not exist at all.** Under
32.64/32.66 the CW's convoy Bomb Points are read off the **[32.66] Simple Axis Naval Convoy Bombing
Chart** (`docs/rules/90:5610`), keyed on **the westernmost hexrow beyond which a qualifying Allied
division sits**:

| Route 2 | Bomb Pts |
|---|---|
| Allied division at Dxx01 | 21-40 |
| … at Cxx16 | 41-80 |
| … at Cxx01 | 81-120 |
| … at Bxx16 | 121-160 |
| … at Bxx01 | 161-200 |
| … at Axx18 | 201-260 |

i.e. **the designer's abstraction is "airfields follow the army"** — a live causal loop from the ground
war to the sea lane. We implement neither loop. **Our `_malta_bomb_points` is a third, invented
thing that is causally inert by construction.**

### Does it change the score? — YES, HUGELY. The "zero" was a measurement artefact.

**Correcting the premise first.** Held to an identical dice stream (§0a), **Malta swings the campaign by
95-320 Victory Points and flips the winner at seed 7.** The reported "exactly zero" came from an A/B
that changed the number of RNG draws and therefore reshuffled the whole war; the ±200 VP of injected
noise hid the signal. **Malta's interdiction machinery is one of the most powerful levers in the
engine.** What is wrong with it is not that it does nothing — it is that *its strength is a hand-typed
constant, the Axis cannot fight it, and no aircraft flies it.*

Two structural defects remain, and both matter.

**(a) On the Tobruk lanes, the skim cannot deny a single Ammunition Point — provably.**

`engine._naval_convoys` skims at sea (41.66, correct order) and *then* clips to the 55.14 port cap
(`engine.py:673-699`). The scenario seeds the Tobruk convoys at **1500 AMMO** into a harbour rated
**425 AMMO/OpStage**. So:

```
lane            commodity  cargo  portcap  @50% skim  verdict
6 (Axis->Tobruk)  AMMO      1500      425        750  INERT (needs 72% skim; CRT max is 50%)
SEA-TOBRUK (CW)   AMMO      1500      425        750  INERT (needs 72% skim; CRT max is 50%)
2 (Malta->Bengh)  AMMO       328      625        164  bites
2 (Malta->Bengh)  FUEL     25200    20000      12600  bites
```

**The CRT's maximum result is 50%. Denying one Ammunition Point at Tobruk needs 72%. It is
arithmetically impossible.** No amount of convoy bombing can reduce the Tobruk lanes' ammunition by a
single point; only *bombing the harbour itself to Efficiency 0* can — which is exactly what §0 shows
happens, by accident, on Game-Turn 2. **So the two Tobruk lanes are governed entirely by the port bug
and not at all by the interdiction that is nominally aimed at them.** (This is the latent bug you
flagged: it is real, and this is its exact shape.)

*But note the correction to your framing:* the **order** in the code is right — the rulebook does bomb
the convoy at sea and *then* unload it over the quay. The defect is that **the scenario ships a
convoy 3.5x the harbour's rated capacity and silently vaporises the excess**. Fix the seeding (or
model what happens to un-unloaded cargo), not the interdiction seam.

**(b) Malta's strength is a fiat constant, and the Axis has no answer to it.**

`_malta_bomb_points` is worth up to ~320 Victory Points (§0a), and **not one input to it is a player
decision.** The Axis cannot raid Malta (44.2 does not exist), cannot spend an Availability Level
(44.23/44.41 do not exist), cannot bomb a Maltese air facility (41.36 does not exist), and cannot
reduce a single Bomb Point by any action available to him. The Commonwealth cannot reinforce Malta
either (34.81, 44.13, 44.18 do not exist). **The single most decisive number in the campaign is typed
into a function and is untouchable by both players.**

That is why fixing rule 44 matters. Not to *make* Malta matter — it already does — but to make its
strength something a player **earns and can contest**, which is the entire point of the chapter.

**A note on which commodity actually binds.** Fuel is *not* the constraint: even at the CRT ceiling the
Axis still lands **1.4-1.6 million Fuel Points**, which is absurd and confirms the missing 58.3 tax
(TOP FIVE #1). What Malta actually strangles is **Ammunition and Stores** — 31,134 → 22,522 AMMO and
75,338 → 54,119 STORES at seed 1941 — and *that* is what moves the score. So the 58.3 fuel fix and the
rule-44 Malta fix are **independent**, and both are needed: one corrects an absurd Axis economy, the
other makes a decisive mechanic playable.

(Note also that lane 6 lands **595** in *every* variant — the Tobruk lane is dead from GT2 regardless,
per §0 — so Malta could not matter there even in principle.)

### The answer to your question

> *"Find out whether that is because Malta is modelled wrongly, or because the thing it is supposed to
> strangle is modelled wrongly."*

**Neither — the MEASUREMENT was wrong.** Malta is not causally inert; it is one of the strongest levers
in the engine (95-320 VP, flips the winner). The "exactly zero" was produced by an A/B that changed the
RNG draw count and reshuffled the entire war (§0a). **This is the single most important thing in this
audit: a real, ~200-VP effect was invisible because of a measurement bug, and the project was about to
conclude the opposite.**

That said, *both* things you suspected are also true, and both still need fixing:

- **Malta IS modelled wrongly** — a calendar with no producer, no Axis counterplay, and no aircraft.
  Worse than inert: a decisive lever set by fiat.
- **The thing it strangles IS modelled wrongly** — the Axis keeps 100% of ~1.9M Fuel Points, where the
  rulebook gives him a quarter (58.3) or burns it in his aircraft (34.17/38.24).

**But fix the RNG stream first, or you will not be able to see whether any of the rest worked.**

---

## 3. TOP FIVE

Ranked by *how much of the campaign is currently wrong*, not by how interesting the rule is.

### 1. Stop conditional dice from desynchronising the RNG stream. **(S)**
**This one already cost you a wrong conclusion about the most important mechanic in the campaign.**
`engine._interdict` (`engine.py:411-414`) draws its two CRT dice **only when an order exists**, and the
engine shares one `rng` with weather, combat and breakdown. Adding or removing interdiction orders
therefore **reshuffles the entire rest of the war**, injecting ±200 VP of noise. That noise is what
produced "cranking Malta to its maximum changes the Axis score by EXACTLY ZERO". **Held to an identical
dice stream, Malta is worth 95-320 Victory Points and flips the winner at seed 7** (§0a). Fix:
draw-and-discard unconditionally, or give interdiction its own `random.Random`. **Do this before you
measure or tune anything else** — it is small, and everything below is unverifiable without it.

### 2. Make aircraft consume fuel — 58.3 now, 34.17/38.24 later. **(S)**
The Axis lands **1,884,000 Fuel Points** over the campaign and keeps 100% of them. Rule 58.3 says he
loses **three-quarters of all fuel at the instant of unloading, before evaporation** — a 4x change to
the single largest number in the Axis economy, and it is **a few lines at the port seam** in
`engine._naval_convoys`. (In the full Air Game the same fuel leaves the same dumps via 38.24; 58.3 is
the abstract shadow of exactly that.) Note the nuance the controlled A/B revealed: fuel is *not*
currently the binding commodity — ammunition and stores are — so this fix will not move the score on
its own. It fixes an **absurd economy**, which is a precondition for the numbers meaning anything.

### 3. Transcribe the [41.5] Air Bombardment CRT (all 8 target rows) and make the bombing missions roll on it. **(M)**
`_air_port` removes exactly 1 Efficiency Level, `_air_fort` removes exactly 1 fort level, `_air_strike`
pins exactly 1 unit — **none of them rolls a die, because the table they should roll on was never
transcribed.** The chart is on **PDF page 107** and I have already verified its convoy row is exact,
so the rendering pipeline works. This one job fixes three WRONG rules (41.39B, 41.37, 41.31), unlocks
four MISSING ones (**41.32 trucks**, **41.35 supply dumps**, 41.36 air facilities, 41.38 rail/road), and
incidentally unblocks 41.7 and 12.5 for other slices. It is also the prerequisite for a real Malta.
**Note especially the two bolded ones: trucks are the binding constraint of this whole campaign and air
currently destroys zero of them.** Until air can kill a lorry (40.62 strafing, 41.32 bombing, 41.35 dump
bombing, 58.42's monthly truck tax), an air force cannot affect this campaign however faithfully we model
its dogfights.

### 4. Fix the 39.14 mission-frequency bug — one schedule entry currently buys three free sorties. **(S)**
`AirMission.turn` is keyed to the **game-turn**, but `_air_support` (`engine.py:1003`) re-flies every
due mission **in all three Operations Stages**, while `_naval_convoys` right beside it *is* correctly
gated `if stage == 1:` (`engine.py:148`). Together with #3's flat port-bomb this shoots the Tobruk
harbour from Efficiency 5 to 0 by **Game-Turn 2** and — because `PORT-Tobruk` is `HARBOUR_BLOCKED` and
never regenerates — keeps it there for 109 turns. **The Axis Tobruk lane lands 595 Ammunition Points in
the entire war (425 + 170, exactly), and the CW ferry lands 0.** The campaign's centrepiece siege duel
never happens. Fold in the seeding fix while you are there: the scenario ships **1500 AMMO** into a
**425-cap** harbour, so 70% evaporates at the quay every turn and the interdiction aimed at that lane is
arithmetically inert (MALTA §(a)). Cheapest large correction on this list.

### 5. Give the convoy interdiction a *producer* — rule 44, Malta proper. **(L)**
Today `bomb_points` is typed into `scenario._malta_bomb_points`, a calendar with no inputs and no
feedback. Build the real loop: Malta air-facility **levels** (44.12/44.13), **18 planes per level**
(44.14) converting Malta's health into Bomb Points, Axis raids reducing those levels via 41.36 out of a
**finite Availability budget** (44.23/44.41: campaign = I unlimited / II×25 turns / III×12 / IV×12), the
44.42 availability roll, and CW reconstruction on the 44.5 table. **All four charts are already OCR'd**
(`docs/rules/90:5954`, `:6002`, `:6016`) — the data was never the blocker.

*If you want a sanctioned stopgap instead (M):* implement **58.1 → 32.64 → the [32.66] chart**
(`docs/rules/90:5610`, fully OCR'd), which makes convoy Bomb Points a live function of **how far west
the Eighth Army has pushed** — the designer's own "airfields follow the army" abstraction, and a real
causal loop. But **58 forbids the Air Game**, so this is a fork, not a stepping stone. Given your goal is
the full Air Game, I would go straight to rule 44 and skip it.

---

## APPENDIX — what I ran

- `python3 -m` inline: campaign state inspection (convoys, ports, landing caps, air wings).
- **Decoupling proof**: `engine._interdict(c, st, rng)` vs `engine._interdict(c, replace(st, air=()), rng)`
  → identical cargo and identical `pct_lost`.
- **Absorption proof**: closed-form — `landed = min(cargo·(1−pct), dump_room, port_cap)`; with
  `cargo=1500`, `port_cap=425`, and the CRT's max `pct=0.50`, `landed` is `425` for every possible roll.
- **Malta A/B (naive)**: three full 111-turn campaign runs (seed 1941), lane-2 interdiction OFF /
  as-shipped / cranked to 500 Bomb Points (`CampaignAxisPolicy` vs `CampaignCommonwealthPolicy`).
  Cargo denial is real (342k Fuel at the ceiling); **the victory tallies are NOT comparable** — see §0a.
- **Malta A/B (RNG-stable)**: the same, but holding the order count fixed at 111 and varying only
  `bomb_points` between **1** (the CRT's flat-0% column — draws the dice, denies nothing) and **500**
  (the ceiling). Identical dice stream in both arms; the only valid Malta A/B on this engine today.
- **`_air_port` / `_air_fort` / `_air_recon` liveness**: `scenario.campaign()` seeds `siege_rules=False`
  and only `kind == "port"` missions, so 41.37 and 41.31/42.2 never execute in the campaign at all.
- **Chart recovery**: `pdftoppm -r 400 -f 107 -l 108` on `tmp/The Campaign for North Africa.pdf`,
  rotated and cropped to read [41.5], [46.3] and [58.5] off the scan.
- Chart cross-checks of [45.4]/[45.5] against the three worked examples inside rules 45.0/45.36.
