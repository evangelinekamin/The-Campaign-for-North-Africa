# Rules 05-11 audit: the land core (sequence, CP, initiative, movement, stacking, ZOC, combat)

Audited against the CODE and against RUNS, not against docstrings. Every DONE/PARTIAL/WRONG row
carries a `file:line`. Every MISSING row names what was grepped. Verified on the CAMPAIGN state
(`scenario.campaign()`, 6770 hexes, 303 units, GT1-111), not on the toy scenarios.

## Headline

The combat arithmetic (11.3), the CP/cohesion ledger (6.1/6.2) and the ZOC predicate (10.1/10.2)
are ported carefully and mostly correctly. **What is missing is the tempo, the terrain and the
friction.** Five whole subsystems that the book uses to make contact expensive do not exist or do
not fire:

1. **Initiative ratings are literally zero.** `initiative_ratings: {}` on the campaign state -- both
   sides roll a bare d6. The 7.2 chart (CW 3/4/5 by date; Axis **6** with Rommel, 3 with Germans,
   **1** with neither) is transcribed in `docs/rules/90:607-617` and never read. Rommel should hold
   the initiative in ~91% of game-turns; he holds it in 50%. The 1940 Italians should hold it in
   ~19%; they hold 50%.
2. **The campaign map has ZERO hexside features.** No escarpments, no wadis, no slopes, no rivers.
   `cna_map.py:52` never passes `hexsides` to the TerrainMap. Rule 8.42 ("no vehicle may EVER move
   up an escarpment") is dead; so is 8.41, 8.43, 10.21a/b and every hexside combat shift. And five
   of the chart's nine hex-terrain classes (gravel, salt marsh, mountain, delta, major city) do not
   exist in the terrain data -- there is no Qattara salt marsh and no Jebel Akhdar mountain.
3. **Contact is free.** A unit stacked with any friendly combat unit pays **0 CP** to break off
   (8.65's 2 CP and 8.66's 4 CP both evaporate) -- proven by probe below. And 10.31-10.36 (you MUST
   attack an enemy hex whose ZOC touches you, or Hold Off with a barrage, or retreat 3 hexes and eat
   3 DP) is not implemented at all. You can walk up to a stack, not fight, and walk away for nothing.
4. **Reaction and Continual Movement never fire.** 0 REACTION_MOVED and 0 SEGMENT_ADVANCED in an
   8-turn campaign run: the scripted campaign policies implement neither hook. And even if they did,
   `engine.py:1297` bars every tank and every armoured car from reacting (39 VEHICLE + 8 RECCE units
   locked out by a `mobility == MOTORIZED` test where the book bars only NON-motorized units).
5. **Cohesion is a one-way ratchet.** 6.24.2 (+3 RP when your close assault empties the enemy hex)
   is missing, so only units that sit idle recover. Units reach cohesion **-68** in the campaign and
   6.26 ("-26 or worse may not move, attack, or defend; surrenders if an enemy moves adjacent") is
   not enforced anywhere.

---

# 5.0 THE SEQUENCE OF PLAY (Land Game)

Note 5.2's own preamble: "This Sequence of Play applies when playing the Land Game **without** the
Air and Logistics Games." We run the full game, so 48.0 is the operative sequence; 5.2's phase
skeleton is nevertheless the spine and is audited as such.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 5.1 | Game-Turn = 3 Operations Stages; the OpStage is the basic unit of time | **DONE** | `engine.py:142` `for stage in (1,2,3)`; OpStage stamped on every event `engine.py:100`; CPA window resets per stage `apply.py:386` | YES |
| 5.2 I | Initiative Determination Stage, once per Game-Turn | **DONE** (but see 7.2) | `engine.py:139-140`, `_initiative` `engine.py:203` | YES |
| 5.2 II.A | Naval Convoy Schedule Phase | **PARTIAL** | `_naval_convoys` `engine.py:150`, stage 1 only; schedule is static (`state.py:240`) | YES (hand to 56 auditor) |
| 5.2 II.B | Tactical Shipping Phase (cargo between African ports) | **MISSING** | not found: grepped `coastal`, `tactical shipping`, `inter.port` -- only Italy->Africa convoys exist | MAYBE |
| 5.2 III.A | Initiative Declaration Phase (holder picks A or B each stage) | **DONE** | `_declare_ab` `engine.py:244`; `Policy.declare_ab` hook `policy.py:163` | YES |
| 5.2 III.B | Weather Determination Phase | **DONE** | `engine.py:145-146`, `_weather` `engine.py:918` | YES |
| 5.2 III.C.1 | Reorganization Segment: attach/detach units, reinforcements, trucks | **MISSING** | `_organization` `engine.py:1551` returns immediately (`if not r.state.motorized_supply`, False in campaign) and only ever handles supply-dump motorization. No unit attach/detach exists anywhere | MAYBE |
| 5.2 III.C.2 | Construction Segment (Completion, then Initiation/Continuation) | **DONE** | `_construction` `engine.py:157,1960`; 24.12 pin via `r.building` `engine.py:95,1232` | YES |
| 5.2 III.C.3 | Training Segment (Completion + Initiation; Morale effects) | **MISSING** | not found: grepped `train`, `Training` across `game/` -- zero hits | MAYBE |
| 5.2 III.D | Naval Convoy Arrival Phase (each OpStage) | **PARTIAL** | `engine.py:148-150`: arrivals fire in **stage 1 only**, not each stage | MAYBE |
| 5.2 III.E | Commonwealth Fleet Phase (Assignment + Repair segments) | **MISSING** | ships bombard (`_naval_bombardment` `engine.py:1121`) but are never re-assigned or repaired | NO (rule 30) |
| 5.2 III.F | Reserve Designation Phase | **DONE** | `_reserve_designation` `engine.py:159,1386` (inert: campaign policy designates nothing) | MAYBE |
| 5.2 III.G.1 | Movement Segment | **DONE** | `_movement` `engine.py:1203` | YES |
| 5.2 III.G.2 | Breakdown Determination Segment | **DONE** | `_breakdown` `engine.py:172-173,1459` (also runs for the enemy, catching retreat BP) | YES |
| 5.2 III.G.3.a | Position Determination Step (Forward/Back for all Gun/Armor units) | **MISSING** | not found: grepped `forward`, `back`, `position` -- `_barrage_class` `engine.py:2282` classifies the TARGET only | MAYBE |
| 5.2 III.G.3.b | Barrage Step (both sides, secret, simultaneous) | **DONE** | `_barrage_step` `engine.py:2293`; both sides fire, results applied after `engine.py:2330` | YES |
| 5.2 III.G.3.c | Retreat Before Assault Step | **DONE** | `_retreat_before_assault` `engine.py:2177,2212` -- correctly after barrage, before anti-armor | YES |
| 5.2 III.G.3.d | Force Assignment Step (secret split of TOE between AA/CA; Probe; withhold) | **MISSING** | `engine.py:2367-2368` docstring: "Voluntary withholding and splitting TOE ... are deferred -- all committed armor fires and is a target" | YES |
| 5.2 III.G.3.e | Anti-Armor Step (simultaneous, losses before Close Assault) | **DONE** | `_anti_armor_step` `engine.py:2361`; plan-then-apply `engine.py:2398` | YES |
| 5.2 III.G.3.f | Close Assault Step (Player A's chosen order) | **DONE** | `_resolve_combat` `engine.py:2423` | YES |
| 5.2 III.G.4 | Reserve Release Segment | **DONE** | `_reserve_release` `engine.py:1403`, called at `engine.py:1433,1445` | MAYBE |
| 5.2 III.H | Truck Convoy Movement Phase (inside each player's portion) | **PARTIAL** | `_truck_convoys` `engine.py:177-178` runs for BOTH sides AFTER both sides' movement+combat -- so convoys always move last and can never be caught mid-stage by the enemy's own turn | MAYBE |
| 5.2 III.J | Commonwealth Rail Movement Phase | **MISSING** | not found: grepped `rail_move`, `8.7`, `rail movement` -- rail exists only as a supply lane inside `_naval_convoys` (`_rail_stops` `engine.py:475`). No units, no player choice | YES |
| 5.2 III.K.1 | Towing Segment | **MISSING** | not found: grepped `tow` -- `_repair` `engine.py:1510` is maintenance only | NO (rule 22) |
| 5.2 III.K.2 | Maintenance Segment | **DONE** | `_repair` `engine.py:174,1510` | MAYBE |
| 5.2 III.L | Patrol Phase | **MISSING** | not found: grepped `patrol` -- only air recon (`engine.py:1086`) | MAYBE (rule 16) |
| 5.2 IV/V | Second and Third Operations Stages repeat all of III | **DONE** | `engine.py:142` | YES |
| 5.2 VI | End of Game-Turn | **DONE** | `TURN_ADVANCED` `engine.py:195` | YES |

**Sequence deviation worth naming:** phases C (Organization) and C.2 (Construction) are stage-level
in the book (done once, before the A/B split) but the engine runs them **inside the per-side loop**
(`engine.py:155-157`), so Player B organizes and starts construction *after* watching Player A's
entire movement and combat. That is an information advantage the book does not grant.

---

# 6.0 THE CAPABILITY POINT SYSTEM

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 6.11 | Each unit has a CPA; a Gun with CPA "0" counts as 10 for everything but movement | **PARTIAL** | `Unit.cpa` `state.py:39`. The 0->10 clause is unimplemented; no CPA-0 unit exists in the OOB (min CPA = 10) | NO |
| 6.12 | Every function costs CP per the 6.3 table | **PARTIAL** | Only movement (`UNIT_MOVED.cp_spent`), combat (`_charge_combat_cp` `engine.py:2151`), dump construction and dump demolition charge CP. 8-turn run's CP_EXPENDED census: `{assault, defend, construct_dump, blow_dump}` only | YES |
| 6.13 | CPA = the CP a unit may spend in an OpStage without earning DP | **DONE** | `_overage_dp` `engine.py:2121` | YES |
| 6.14 | The CPA window spans BOTH players' portions of the stage | **DONE** | `cp_used` is reset only at the stage boundary (`apply.py:386-393`); reaction/RBA/defence CP accumulate into it | YES |
| 6.15 | A Parent Formation's CPA = the LOWEST CPA among its units | **MISSING** | not found: no parent formations exist. `supply.py:443-444`: "Unit carries no organisation size and no division-shell status" | NO (no formations) |
| 6.16 | CP do not carry over between OpStages; not transferable | **DONE** | `_reset_opstage` `apply.py:386-393` on STAGE_ADVANCED and TURN_ADVANCED | YES |
| 6.17 | Infantry (base CPA <=10) motorized by trucks **assume the truck's CPA** (e.g. 8 -> 20) | **MISSING** | not found: grepped `motoriz` -- the only motorization in the engine is 32.32 supply-dump motorization. No combat unit can be motorized. Worse, the OOB ships 18 units with `mobility=MOTORIZED, cpa=10` -- below the engine's own <=10 non-motorized test (`tactics.py:69`) | YES |
| 6.21 | 1 DP per CP over CPA; 3 DP for 30%+ losses in one Close Assault | **DONE** | `_overage_dp` `engine.py:2121`, `_disorganize_overage` `engine.py:2127`; 30% rule `engine.py:2519-2524` | YES |
| 6.22 | DP are credited IMMEDIATELY, before the assault resolves | **DONE** | `_resolve_combat` charges CP (`engine.py:2437,2451`) before `_adjusted_morale` reads cohesion (`engine.py:2460`) | YES |
| 6.23 | RP raise Cohesion; **never above +10** | **PARTIAL** | `apply.py:270-272` adds the delta with **no +10 clamp**. Moot today: no RP source can push above 0 | NO |
| 6.24.1 | 5 RP for an OpStage in which a unit spends zero CP; never above 0 | **DONE** | `_idle_recovery` `engine.py:2107-2118`, capped `min(5, -cohesion)` | YES |
| 6.24.2 | **3 RP for each Close Assault in which the defender vacates the hex** | **MISSING** | not found: grepped `6.24`, `vacate`, `reorganization point` -- only 6.24.1 exists. `engine.py:2517-2518` admits "Recovery ... is deferred, so Cohesion only falls" | YES |
| 6.25 | Cohesion adjusts Basic Morale at the instant of combat | **DONE** | `combat_tables.morale_modifier` via `_adjusted_morale` `engine.py:2571` | YES |
| 6.26 | Cohesion -26: **may not move, attack, or defend**; surrenders if an enemy combat unit moves adjacent | **MISSING** | Only the ZOC clause (10.14) exists: `zoc.py:41`. `_movement` `engine.py:1220-1272` has **no cohesion gate**; `_resolve_combat` has none. No adjacency-surrender anywhere. Run evidence: units finish at **-27, -31, -37, -52, -68** and keep moving and fighting | YES |
| 6.27 | Largest unit's Cohesion prevails; **if several are equally largest, AVERAGE them** | **WRONG** | `engine.py:2569` `largest = max(live, key=(stacking_points, strength))` -- picks ONE unit, no averaging. Every campaign counter is SP 1, so "several equally largest" is the NORM and the averaging rule should fire in nearly every multi-unit assault. Instead the stack borrows the *strongest* unit's cohesion, hiding its broken companions | YES |
| 6.28 | Same rule applied inside a Parent Formation | **MISSING** | no parent formations (see 6.15) | NO |
| 6.29 | Cohesion is tracked per unit | **DONE** | `Unit.cohesion` `state.py:50` | YES |
| 6.3 | Capability Point Cost Summary (chart) | **PARTIAL** | `data/cp_costs.json` transcribes 6 of ~25 rows, wires 4. See CHART FIDELITY | YES |

---

# 7.0 INITIATIVE

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 7.11 | The Initiative holder chooses first or last each Operations Stage | **DONE** | `_declare_ab` `engine.py:244`; `_double_move_first` `engine.py:237` exercises the 7.12 double-move | YES |
| 7.12 | Initiative is determined per GAME-TURN and held for all three stages | **DONE** | `_initiative` called once per turn `engine.py:140`; `state.initiative_side` | YES |
| 7.13 | Each side has an Initiative Rating that depends on the date | **MISSING** | `scenario.campaign()` passes **no** `initiative_ratings` -- the campaign state carries `{}` (verified by probe) | YES |
| 7.14 | 1d6 + Initiative Rating; high total wins; ties reroll | **WRONG** | Dice + tie-reroll are right (`engine.py:224-234`) but both ratings resolve to **0** via `.get(..., 0)` `engine.py:220-223`. Run evidence, GT1-5: `axis_total` always == the raw die. **Initiative is a coin flip for 111 turns** | YES |
| 7.15 | The first Game-Turn's Initiative is predetermined per scenario | **MISSING** | `initiative_fixed=None` on the campaign (set only in the two Desert Fox scenarios, `scenario.py:158,318`) | MAYBE |
| 7.16 | Player A moves first; Player B moves last | **DONE** | `engine.py:152` `for side in (first, second)` | YES |
| 7.2 | **Initiative Ratings Chart** | **MISSING** | The chart IS transcribed (`docs/rules/90:607-617`). No code reads it; `scenario.py:39` invents `{"AXIS": 3, "ALLIED": 2}` for two scenarios and the campaign passes nothing. `engine.py:208` and `state.py:261` both *claim* the chart is "untranscribed" -- **the docstrings are wrong** | YES |

The chart, for the fix: CW = 3 (GT1-42), 4 (GT43-90), 5 (GT91-111). Axis = 6 with the Rommel
counter on the maps, 3 with German land combat units but no Rommel, 1 with neither. (Tripoli/Tunisia
holding boxes do not count as "on the Game-Maps".) The engine already special-cases the recall clamp
to 3 (`engine.py:222`) -- it hand-coded one row of a chart it says does not exist.

---

# 8.0 LAND MOVEMENT

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 8.11 | Voluntary movement only in Movement Segments / RBA; all movement costs CP; vehicles check Breakdown; may move through friendly units | **DONE** | `_movement` `engine.py:1203`; BP accrual `engine.py:1265` | YES |
| 8.12 | Retreat is involuntary movement -- **still costs CP** and checks Breakdown | **WRONG** | `_retreat` `engine.py:2606` accrues BP (`engine.py:2653`) but charges **zero CP**: `engine.py:2611` "Retreat CP cost (15.82) is not charged yet (flagged)". A routed unit pays nothing, earns no DP, and keeps its whole CPA | YES |
| 8.13 | Never enter an enemy-occupied hex; hexes must be consecutive | **DONE** | `blocked=enemy_occupied` `zoc.py:122`; Dijkstra over `neighbors` `movement.py:199` | YES |
| 8.14 | On entering an enemy ZOC, stop -- no further movement that Segment | **PARTIAL** | Enforced within ONE order (`terminal` `zoc.py:123`). But `_movement` has no per-unit "already moved" guard: **a second MoveOrder for the same unit in the same Segment walks it back out.** Probe: (2,1)->(0,1)->(-3,1), 12 CP, one Movement Segment, both accepted | YES |
| 8.15 | Leaving a ZOC: not directly into another; 2 CP if in Contact, 4 if Engaged | **PARTIAL** | ZOC->ZOC blocked `zoc.py:124`. Costs correct for a LONE unit, **free when stacked** (see 8.64) | YES |
| 8.16 | A unit may exceed its CPA (paying Cohesion) | **PARTIAL** | `tactics.py:69` imposes an invented **2x CPA hard ceiling** on motorized units; the book has no ceiling above CPA 10. Self-limiting in practice (2x CPA = CPA worth of DP), and the run shows it binding at exactly 50.0 CP | MAYBE |
| 8.17 | Non-motorized (CPA <=10) may never *voluntarily* spend more than 150% of **base** CPA | **PARTIAL** | `tactics.py:69` `1.5 if cpa <= 10` -- correct magnitude. Two deviations: it is applied to TOTAL `cp_used` including **involuntary** spend in the enemy's portion (which 8.17 explicitly exempts), and to the Rommel-effective CPA rather than the base | MAYBE |
| 8.17 (2nd clause) | No unit at Cohesion -26 or worse may move | **MISSING** | see 6.26 | YES |
| 8.18 | 2nd/3rd-line trucks move only in the Truck Convoy Phase | **DONE** | `TruckFormation` is a separate entity moved only by `_truck_convoys` `engine.py:1812` | YES |
| 8.19 | **No Commonwealth land unit may ever be west of Marble Arch (A2109)** | **MISSING** | not found: grepped `marble`, `2109`, `west of` -- no such constraint | MAYBE |
| 8.21 | Unlimited move/fight cycles except 6.26 / 8.17 / 8.23 | **PARTIAL** | Loop exists (`_continual_movement` `engine.py:1423`, `MAX_CONTINUAL_SEGMENTS=20` `engine.py:1176`) but **the campaign policies never invoke it**: 0 SEGMENT_ADVANCED in 8 turns. `campaign_policy.py` implements no `continual_movement` | YES |
| 8.22 | Move -> resolve combat -> move again, repeating | **PARTIAL** | Structure correct `engine.py:1434-1445`; inert in the campaign | YES |
| 8.23 | Only phasing units finishing within **two hexes** of an enemy may move again (Reserve excepted) | **DONE** (bypassable) | `_exploitation_eligible` `engine.py:1371-1383`. Bypassed by the 8.14 duplicate-order hole, which is ungated | YES |
| 8.24 | 2 CP to break Contact / 4 CP if Engaged, at the start of a Movement/Combat Phase | **WRONG** | free when stacked -- see 8.64 | YES |
| 8.25 | The same enemy may be attacked repeatedly with no movement | **PARTIAL** | A fresh Combat Segment per pulse `engine.py:1444`; inert (no pulses run) | MAYBE |
| 8.31 | Hex-entry and hexside CP costs per the TEC | **PARTIAL** | Hex entry: `terrain.py:66-76` -- **every cell matches the chart** (I checked all 9). Hexside: `terrain.py:79-88` matches too, but **the campaign map carries 0 hexsides** so they never fire | YES |
| 8.32 | Certain terrain is prohibited to certain unit types | **MISSING** | `hex_entry_cost` `terrain.py:95` splits only non-Mot/Mot; no sub-class prohibition. `terrain.py:23-24` admits: footnotes 2/3 "applied once units have real OOB data" | YES |
| 8.33 | Road/Track benefit needs a connecting Road/Track hexside | **DONE** | `movement.py:67-78` keys on `edge(src,dst) in tmap.roads/tracks` | YES |
| 8.34 | A vehicle on a road may not pass through friendly units beyond the road limit | **MISSING** | see 9.33 | MAYBE |
| 8.35 | Slopes/escarpments are directional (up/down); ridges are not | **DONE** (dead) | directional `Hexside` `terrain.py:52-62`; no hexsides on the map | YES |
| 8.36 | Terrain restricts/benefits combat | **PARTIAL** | Hex shifts live (`combat_tables.py:340-347`); hexside shifts dead (no hexsides) | YES |
| 8.37 | Terrain Effects Chart | **PARTIAL** | see CHART FIDELITY | YES |
| 8.41 | Wadis: +1/+4 CP, BP 8, roads negate, tracks halve (BP 4), rainstorm closes them except by road (+2 CP) | **PARTIAL** | Coded exactly: `terrain.py:85,131`, `movement.py:88-99`. **Dead: no wadi hexside exists on the campaign map** | YES |
| 8.42 | Escarpments: **no vehicle may EVER move up**; down by track = +8 CP, 6 BP | **PARTIAL** | Coded: `terrain.py:83` (`UP_ESCARPMENT: (6, PROHIBITED)`), note-8 exception `movement.py:96`. **Dead: 0 hexsides on the map -- vehicles drive up the Sollum escarpment freely** | YES |
| 8.43 | Slopes and ridges at various CP/BP costs | **PARTIAL** | `terrain.py:80-82,126-128` correct; dead on the map | YES |
| 8.44 | Salt Marsh: vehicles (except light trucks/recce/motorcycle inf) only on road or track; else **Abandoned**; no motorized unit or AFV may assault into/out of it | **MISSING** | `_HEX_ENTRY[SALT_MARSH] = (3, 2)` `terrain.py:69` lets any vehicle enter at 2 CP. No abandonment, no assault ban. Moot anyway: **there is no salt-marsh hex in the terrain data** (Qattara does not exist) | YES |
| 8.45 | Desert is forbidden to light trucks and motorcycle units | **MISSING** | `_HEX_ENTRY[DESERT] = (3, 4)` `terrain.py:74` -- no prohibition | MAYBE |
| 8.46 | Tracks: 1 CP/hex, halve hexside costs, half Breakdown | **DONE** | `TRACK_ENTRY` `terrain.py:92`; halving `movement.py:96-99`, `movement.py:120-137` | YES |
| 8.47 | Unconstructed rail is ignored; unconstructed roads are treated as tracks | **PARTIAL** | Rail construction exists (24.6, `_build_rail` `engine.py:2020`). Unconstructed **roads** are not modelled -- `unit_stats.json` admits "rule 24.5 road construction is not implemented (the map's unfinished-road hexes are untranscribed)" | MAYBE |
| 8.48 | Oases do not affect movement; they are nondiminishing Water+Stores dumps | **DONE** | `game/wells.py`, `game/villages.py` (the wells slice); detail belongs to the 52 auditor | YES |
| 8.49 | Terrain affects combat (15.3) | **PARTIAL** | see 8.36 | YES |
| 8.51 | Reaction: a non-phasing unit moves in response to an enemy moving adjacent | **DONE** (never fires) | `_react` `engine.py:1275`, invoked `engine.py:1272`. **0 REACTION_MOVED in an 8-turn campaign run** -- `campaign_policy.py` implements no `react_to` | YES |
| 8.52 | May React repeatedly; a reactor does **not** pay the Break Contact / Disengage surcharge | **WRONG** | `tactics.reachable_for` charges `_break_off_cost` (`tactics.py:117`) and the reactor is by construction inside the trigger mover's fresh ZOC. Admitted at `engine.py:1284-1285` | MAYBE |
| 8.53 | Eligibility: (a) non-motorized/SGSU/loose convoys may never react; (b) pinned by a CPA gap >=6 **when a Close Assault is announced**; (c) not if already in an enemy ZOC; (d) not if in combat/Engaged | **WRONG** | (a) `engine.py:1297` requires `mobility == Mobility.MOTORIZED` -- **every tank (39 VEHICLE) and every armoured car (8 RECCE) in the campaign is barred from reacting**, though the book bars only NON-motorized units. The CPA-45 recce battalion, the book's own example reactor, cannot react. (b) `REACTION_CPA_GAP=6` `engine.py:1181,1306` is right but ignores the "announces a Close Assault" condition (conservative). (c) DONE `engine.py:1305` + `tactics.enemy_zoc_excluding`. (d) DONE `engine.py:1297` | YES |
| 8.54 | **No battalion may pin a division; no company may pin a brigade or larger** | **WRONG (inverted)** | `engine.py:1307` `u.stacking_points * 2 >= mover.stacking_points`, ANDed with 8.53b. The book's rule is an EXCEPTION that *restores* reaction to a big unit ("notwithstanding anything said in 8.53"); the engine turns it into a standalone *denial* -- a battalion may not react to a moving division even at zero CPA gap, and a division still cannot react to a CPA-45 recce battalion. Inert today (every unit is SP 1) | NO (inert) |
| 8.55 | A reacting unit may never enter an enemy ZOC; no distance cap | **PARTIAL** | No distance cap ✓ (`engine.py:1323`). But `reachable_for` lets a reactor ENTER a controlled hex (it merely stops there); the book forbids entering one at all | NO (inert) |
| 8.56 | A unit may detach from its parent to react (paying the detach CP) | **MISSING** | no attachment model | NO |
| 8.61 | Break Off happens when a Movement Segment starts in Contact or Engaged | **DONE** | `Unit.engaged` `state.py:51`; ZOC at segment start `zoc.py:125` | YES |
| 8.62 | Contact = in an enemy ZOC at the start of a Movement Segment | **DONE** | `zoc.py:117-118` | YES |
| 8.63 | Engaged = a Close Assault result; not necessarily in a ZOC | **DONE** | `Unit.engaged` set by COMBAT_RESOLVED, cleared at the OpStage boundary `apply.py:393` | YES |
| 8.64 | A unit in Contact or Engaged **may not move until it pays** to break off | **WRONG** | `zoc.py:125` `start_cost = break_off if controlled(start) else 0.0`, and `controlled()` is False when the hex holds another friendly combat unit (the 10.26 negator, `tactics.py:113`). **Probe:** lone unit pays 2.0 (Contact) / 4.0 (Engaged); the SAME unit stacked with one friendly combat unit pays **0.0 in both cases.** 8.67 ("when ALL of the Friendly units that were in Contact ... Break Off") proves the book expects each unit in a stack to be in Contact and to pay | YES |
| 8.65 | Contact = 2 CP | **DONE** (lone) / **WRONG** (stacked) | `cp_costs.json` `break_contact: 2`; see 8.64 | YES |
| 8.66 | Engaged = 4 CP | **DONE** (lone) / **WRONG** (stacked) | `cp_costs.json` `disengage: 4`; see 8.64 | YES |
| 8.67 | When ALL friendly units break off, the enemy unit is no longer Contact/Engaged | **MISSING** | `Unit.engaged` is a per-unit flag cleared only at the OpStage boundary (`apply.py:393`); no notion of the enemy's status | MAYBE |
| 8.68 | Contact/Engaged markers bind only the units present at placement | **DONE** | per-unit flag, not a hex marker | MAYBE |
| 8.71 | Two rail lines: Alexandria-Matruh (CW only, extendable); Soluch-Benghazi is decorative | **PARTIAL** | The CW rail line exists and is extendable (`rail_line`, `_build_rail` `engine.py:2020`); it hauls **supply only** | YES |
| 8.72 | CW may rail-move **units and/or supplies**, one stack any distance each direction, once per OpStage | **MISSING** | not found: no rail phase for units. Supply rail is a different rule (54.3, `supply.rail_haul_cap`) | YES |
| 8.73 | A rail-moving unit must start on a rail hex, have spent 0 CP, and not be in an enemy ZOC | **MISSING** | as 8.72 | YES |
| 8.74 | Once in each direction per OpStage | **MISSING** | as 8.72 | YES |
| 8.75 | Max 2 Stacking Points per rail move | **MISSING** | as 8.72 | YES |
| 8.76 | Destroyed / unbuilt rail hexes may not be used | **PARTIAL** | Unbuilt: DONE (`_complete_rail` `engine.py:2005`). Destroyed/bombed rail: not modelled | MAYBE |
| 8.77 | Pick up / drop off anywhere along the line | **MISSING** | as 8.72 | MAYBE |
| 8.78 | No rail hex west of an Axis-occupied rail hex may be used | **MISSING** | not found: grepped `8.78`, `west of` | YES |
| 8.81-8.88 | The Tripoli/Tunisia boxes: 4 regions + In-Transit boxes, unlimited stacking/water, unlimited supply dumps, no breakdown, CPA-exact movement | **MISSING** | `victory_cities.json` `_tripoli_note`: "Tripoli is off-map ... No hex exists in sections A-E, so it is null". The Axis reinforcement pipeline lands at Benghazi instead | MAYBE |
| 8.89 | Off-Map Land Unit Movement Distance Chart | **MISSING** | chart at `docs/rules/90:84-93`, transcribed nowhere | MAYBE |
| 8.91 | A motorized unit carries enough vehicles for the whole unit | **DONE** | `Mobility` `terrain.py:21-33` | YES |
| 8.92 | Non-motorized units may be motorized by adding Truck Points; CPA becomes the truck's | **MISSING** | see 6.17 | YES |
| 8.93 | Historically-motorized infantry are marked "+" on the chart | **MISSING** | not found: grepped `historically`, `"+"` -- no such flag | MAYBE |
| 8.94 | A motorized unit keeps its CPA even when doing something impossible in a vehicle | **N/A** | no motorization exists to keep | NO |
| 8.95 | Truck Points carry TOE Strength Points or supplies | **PARTIAL** | Convoys carry supplies (`_truck_load` `engine.py:1860`); no truck ever carries troops | YES |
| 8.96 | Truck Points attach to any unit bearing a historical designation | **MISSING** | `Unit.is_first_line_truck` exists (`state.py:63`) but **the OOB never sets it** (grepped `oob.py`, `scenario.py`, `data/*.json`) | YES |
| 8.97 | Trucks attach/detach only in the Organization Phase; no unit at Cohesion -5 or worse may detach trucks | **MISSING** | see 8.96 and 5.2 III.C.1 | MAYBE |
| 8.98 | Attached trucks move with their unit; convoys move in the Convoy Phase and may never exceed their extended CPA (else captured) | **PARTIAL** | Convoy CPA cap DONE (`supply.reachable_truck_moves` bounds by the 53.22 CPA `supply.py:370-379`). First-line trucks do not exist | YES |
| 8.99 | Truck marker representation | **N/A** | a physical-counter rule with no engine analogue | NO |

---

# 9.0 STACKING

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 9.11 | Every unit has a printed Stacking Point value | **DONE** | `Unit.stacking_points` `state.py:40` | YES |
| 9.12 | HQ SP is parenthesized: 0 with nothing attached, the printed value when it represents the division | **PARTIAL** | HQs are hard-coded `sp: 0, is_combat: false` (`unit_stats.json`); the "represents the division" half is unmodelled | MAYBE |
| 9.13 | SP represent organizational ability, not just men | **N/A** | flavour text | NO |
| 9.14 | **Each terrain type has a maximum SP that may be in the hex** (per 8.37) | **WRONG** | `stacking.py:22` `DEFAULT_HEX_LIMIT = 5  # PLACEHOLDER` -- one invented limit for EVERY terrain, enforced at `engine.py:1254,1329,1364,2249,2629` and `invariants.py:62-65`. The chart's own leaked cells give **Major City = 8** and Road/Track = 5. A 5-SP division would fill a clear hex by itself | YES |
| 9.15 | Markers and air units have no SP | **DONE** | not units | NO |
| 9.16a | Garrison units stack free in their assigned city/village | **DONE** | `oob.py:311` `is_garrison_home="Garrison" in rec["group"]`; `stacking.py:35-36` | YES |
| 9.16b | Pure AA stacks free in Major Cities (3 free at an airfield, 1 at a landing strip) | **MISSING** | `stacking.counts_in_hex` supports `is_pure_aa` (`stacking.py:37`) but **the OOB never sets it** | NO |
| 9.16c | (OCR-garbled) unmotorized "0+" CPA guns have zero SP | **N/A** | no CPA-0 units in the OOB | NO |
| 9.21 | A Division = its HQ plus everything attached to it | **MISSING** | no divisions exist. Probe: 281 of 303 campaign units are SP 1, the other 22 are SP 0. **No unit anywhere has SP 2, 3 or 5** | YES |
| 9.22 | Brigade equivalents (Italian regiments count; British "brigades" often do not) | **MISSING** | as 9.21 | YES |
| 9.23 | The battalion equivalent is the basic combat unit | **DONE** (by accident) | every counter is a battalion | YES |
| 9.24 | Every artillery unit has SP 1 | **DONE** | `unit_stats.json` artillery has no `sp` override -> default 1 (`oob.py:290`) | YES |
| 9.25 | At most **five** 0-SP companies per hex (unlimited in a Major City) | **MISSING** | `stacking.hex_points` sums SP only -> unlimited 0-SP units anywhere | NO |
| 9.26 | Shell definitions (div <=50% of brigades; bde <2/3 of battalions; bn <50% TOE; artillery <25%) | **MISSING** | `supply.py:443-444`: "Unit carries no organisation size and no division-shell status" | MAYBE |
| 9.27 | A shell sub-unit does not count toward its parent's full strength | **MISSING** | as 9.26 | MAYBE |
| 9.28 | **A shell is reduced one size level** for the 15.53 Close Assault size shift | **MISSING** | as 9.26. `combat.resolve` passes raw `stacking_points` (`engine.py:2494-2495`) with no shell reduction | MAYBE |
| 9.29 | First-line trucks never count for stacking or road space; loose convoys count for **road space only** | **PARTIAL** | Coded (`stacking.py:32-54`) but no unit is ever a first-line truck, and convoys are not StackUnits | MAYBE |
| 9.31 | A unit may never END movement over the stacking limit | **DONE** | `within_hex_limit` at `engine.py:1254,1329,1364,2249` + retreat `engine.py:2629` + `invariants.py:62` | YES |
| 9.32 | Units may always move THROUGH friendly units; the limit binds at rest | **DONE** | no stacking test inside `movement._search` | YES |
| 9.33 | **A motorized unit on a Road/Track may not exceed the 5-point Road/Track limit by moving through friendlies** | **MISSING** | `stacking.within_road_track_limit` exists (`stacking.py:57`) but is called **only** from `adjudication.py:138` (`validate_batch`), which the engine never calls -- and even there it is flagged an "approximation". The road/track limit is not enforced in play | MAYBE |
| 9.34 | You may not split a unit to dodge 9.33 | **N/A** | 9.33 is unenforced | NO |
| 9.35 | Stacking applies during involuntary retreats; a stack may SPLIT into different hexes; any part that cannot retreat must Stand and take extra losses | **PARTIAL** | `_retreat` `engine.py:2627-2629` checks the limit and applies the 10%-per-hex Stand loss (`engine.py:2657-2663`), but **never splits** the stack -- it all stands or all goes | MAYBE |
| 9.4 | Stacking Point Values chart (Div 5 / Super Bde 3 / Bde 2 / Bn 1 / Coy 0; shell = one level down; trucks 1/2 per 5) | **PARTIAL** | The ladder is unused: no counter above SP 1 exists. Truck/Replacement-Point SP unmodelled | YES |

---

# 10.0 ZONES OF CONTROL

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 10.11 | Units above battalion (>1 SP) exert ZOC; so does any hex with >1 SP total. Never convoys or bare HQs | **DONE** | `zoc.py:44-51` `total_sp > 1`; `is_combat` excludes convoys/HQs | YES |
| 10.12 | Aircraft, SGSU and warships exert no ZOC | **DONE** | not Units / `is_combat` | YES |
| 10.13 | Informational markers exert no ZOC | **DONE** | dumps/minefields are not Units | YES |
| 10.14 | Cohesion -26 or worse -> no ZOC | **DONE** | `zoc.py:41` `u.cohesion > -26` | YES |
| 10.15 | A hex totalling <10 **raw** defensive Close Assault points exerts no ZOC | **DONE** | `zoc.py:29,51` `ZOC_MIN_DEFENSE = 10`; `raw_defense = dca * effective_strength` `state.py:113` | YES |
| 10.16 | The non-phasing player must disclose whether a unit exerts ZOC | **N/A** | perfect information at the engine boundary; rule 3.6 limited intel is handled in `observation.py` | NO |
| 10.21a | ZOC does not cross all-sea, major-river or lake hexsides | **PARTIAL** | `ZOC_BLOCKING_HEXSIDES` `zoc.py:25-27` has MAJOR_RIVER; sea/lake hexsides are not modelled at all (admitted `zoc.py:23-24`). **Dead: the map has 0 hexsides** | MAYBE |
| 10.21b | ZOC does not cross escarpment hexsides | **PARTIAL** | coded `zoc.py:26`; dead (no hexsides) | YES |
| 10.21c | ZOC does not reach a hex the unit could not itself enter | **DONE** | `zoc.py:57` `step_cost(...) is not None`, per unit mobility | YES |
| 10.22 | No CP cost to enter an enemy ZOC | **DONE** | no surcharge in `step_cost` | YES |
| 10.23 | Stop on entry; may not exit until the NEXT Movement Segment; leaving a ZOC you start in costs the break-off; **units may not be retreated into an enemy ZOC** | **PARTIAL** | Stop: `zoc.py:123`. Retreat-blocking: DONE `engine.py:2622` `blocked = (enemy_zoc - friendly) | enemy_occ`. **But the exit ban is bypassable via a second MoveOrder in the same Segment (see 8.14)** | YES |
| 10.24 | No step from one controlled hex directly into another; you may always advance into a hex the enemy has just vacated | **DONE** | `zoc.py:124` `passable`; the "advance" is simply the vacated hex being reachable in the next segment | YES |
| 10.25 | You may move through hexes adjacent to an enemy that are not controlled | **DONE** | falls out of the control map | YES |
| 10.26 | A friendly combat unit in a hex negates the enemy ZOC **for movement purposes** | **WRONG (over-applied)** | `zoc.py:118` + `tactics.py:113`. Correct for through-movement; but the same negation also zeroes the 8.64-8.66 **break-off cost** for any unit stacked with a friendly combat unit -- which contradicts 8.67 | YES |
| 10.27 | Opposing units exerting ZOC on each other are in each other's ZOC; a hex may be controlled by both | **DONE** | control maps are computed per side | YES |
| 10.28 | Multiple ZOCs into a hex have no extra effect | **DONE** | `frozenset` of hexes | YES |
| 10.29 | Convoys may not enter an enemy ZOC unless a friendly combat unit is there; no non-combat unit may voluntarily enter an unoccupied ZOC hex; alone in a ZOC it is **Captured** | **PARTIAL** | Trucks: DONE (`supply.reachable_truck_moves` `supply.py:374-376`). Bare HQs are NOT blocked (only engineers are, `engine.py:1236`). The capture rule is MISSING | MAYBE |
| 10.31 | **Every enemy hex exerting ZOC on your units MUST be attacked** (barrage or close assault) | **MISSING** | not found: grepped `10.3`, `must attack`, `mandatory`, `holding.off`, `soak` -- zero hits in `game/` | YES |
| 10.32 | Exception: friendly stacks that are artillery/AT/AA-only, or pinned | **MISSING** | moot without 10.31 | MAYBE |
| 10.33 | A "Holding Off" barrage may satisfy 10.31 | **MISSING** | as 10.31 | YES |
| 10.34 | Holding Off needs >= 1 Actual Barrage Point per enemy non-Gun battalion-equivalent in the hex | **MISSING** | as 10.31 | YES |
| 10.35 | If you cannot Hold Off, you must Close Assault (no minimum strength) | **MISSING** | as 10.31 | YES |
| 10.36 | If you can neither assault nor hold off: **retreat 3 hexes, spend all CP, earn 3 DP**; surrender entirely if forced into a ZOC | **MISSING** | as 10.31 | YES |

---

# 11.0 THE COMBAT SYSTEM

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 11.11 | Barrage Rating (artillery only) | **DONE** | `Unit.barrage` `state.py:44`; `raw_barrage` `state.py:117` | YES |
| 11.12 | Vulnerability Rating (all Guns) | **PARTIAL** | Stored (`state.py:47`, from the charts) but used **only** as the `is_gun` flag (`state.py:139`). Its actual function -- gun losses in Close Assault (15.84/15.85) -- is deferred (`combat.py:22`) | MAYBE |
| 11.13 | Anti-Armor Rating | **DONE** | `state.py:45`, `raw_anti_armor` `state.py:121` | YES |
| 11.14 | Armor Protection (a constant, not a per-TOE rating) | **DONE** | `state.py:46`; used as the loss divisor `engine.py:2416` | YES |
| 11.15 | Offensive and Defensive Close Assault Ratings | **DONE** | `oca`/`dca` `state.py:41-42` | YES |
| 11.16 | AA Rating (mostly AA/Flak units, but some tanks and HQs have one) | **MISSING** | `Unit` has **no** `aa_rating` field (only ships do, `state.py:306`); land flak is folded into the abstract air-superiority roll (`engine.py:38-45`) | MAYBE |
| 11.21 | A non-phasing unit spends **3 CP** if it undergoes an attack: (a) barraging, (b) undergoing any assault (Probe = 2), (c) undergoing a Holding-Off barrage | **PARTIAL** | 3 CP is charged (`cp_costs.assault_cost(False)`, `engine.py:2451`) **only** to defenders that actually defend a close assault or that fire. A unit that merely **undergoes a Barrage pays 0**; pinned and out-of-ammo defenders pay 0 (`armed_def` filter `engine.py:2449`) | YES |
| 11.22 | A phasing unit spends 5 CP per attack; never more than 5 in one combat | **DONE** | `_charge_combat_cp` `engine.py:2151-2162` with a per-segment `charged` ledger | YES |
| 11.23 | Phasing: Probe = 2 CP; undergoing a Barrage = 3 CP | **MISSING** | `cp_costs.py:21-23` admits both rows are "STILL UNCONSUMED"; no Probe exists | MAYBE |
| 11.24 | Caps: non-phasing <=3 CP, phasing <=5 CP per Combat Segment | **DONE** | the `charged` set `engine.py:2157-2159` | YES |
| 11.25 | **CP expenditure applies to ALL units in the hex, even those that did not participate** | **MISSING** | `_charge_combat_cp` is called only for `armed`/`armed_atk`/`armed_def` (`engine.py:2316,2386,2437,2451`). A stack can attack with one battalion and the rest keep their full CPA -- and their movement | YES |
| 11.26 | (restates 11.21/11.22) | **PARTIAL** | as above | YES |
| 11.27 | A defender facing a final differential of **-4 or worse spends only 1 CP** | **MISSING** | not found: grepped `11.27`, `reacquire`, `-4` -- `assault_cost(False)` is a flat 3 | NO |
| 11.31 | Combat strengths are Actual Strength Points | **DONE** | `combat.actual_points` `combat.py:53` | YES |
| 11.32 | Actual = Rating x TOE / 10, rounded to nearest (11.4->11, 11.5->12) | **DONE** | `_round_half_up` `combat.py:49-50`, `combat.py:58` | YES |
| 11.33 | <5 raw points -> 0 Actual. If **both** sides of a Close Assault have <10 raw, use Raw as Actual | **DONE** | `combat.py:54-57`; `both_small` `combat.py:69` | YES |
| 11.34 | Total ALL raw points before dividing -- within a hex and across hexes attacking one target | **DONE** | `sum(u.raw_offense ...)` then `actual_points` (`engine.py:2484`, `engine.py:2318`, `engine.py:2388`) | YES |
| 11.35 | (worked example) | **N/A** | -- | NO |
| 11.36 | (bookkeeping advice) | **N/A** | -- | NO |
| 11.37 | AA/Flak Actual Points = TOE x Rating, **NOT divided by ten** | **MISSING** | no land AA rating exists (see 11.16) | MAYBE |
| 11.38 | Vulnerability and Armor Protection do not use the x TOE / 10 formula | **PARTIAL** | Armor Protection: DONE (`engine.py:2416`). Vulnerability: stored, never used | MAYBE |

---

# CHART FIDELITY

### 8.37 Terrain Effects Chart (`docs/rules/90:4-66`)

| Column | Where it lives | Verdict |
|---|---|---|
| CP to enter (non-Mot / Mot), 9 hex types | `terrain.py:66-76` | **EXACT MATCH** -- I checked all 18 cells against the chart. But hard-coded with **no chart-of-record JSON and no binding test** (unlike the Breakdown column), and the file still says "PROVISIONAL VALUES -- VERIFY AGAINST THE SCAN" |
| CP to cross, 8 hexside features | `terrain.py:79-88` | **EXACT MATCH** (Ridge +2/+4, Up Slope +2/+4, Down Slope +1/+2, Up Esc +6/P, Down Esc +4/+8, Wadi +1/+4, Major River +8/P, Minor River +3/+6). **Never fires: the map has 0 hexsides** |
| Breakdown Values | `data/breakdown_rates.json` -> `terrain.py:110-134`, bound by `tests/test_breakdown.py:43-51` | **EXACT MATCH**, incl. the contested `desert = 24`. This column is done right: chart-of-record JSON + a test that pins the code to it. **The model to copy.** |
| Close Assault shifts (hex) | `combat_tables.py:340-347` | **EXACT MATCH** (Salt Marsh R1, Heavy Veg L1, Rough L2, Mountain L3) |
| Close Assault shifts (hexside) | `combat_tables.py:349-353` | **EXACT MATCH** (Ridge L2, Up Slope L2, Down Slope R1, Up Esc L3, Down Esc R1, Wadi L1, Major River L6, Minor River L2). Never fires |
| Anti-Armor shifts | `combat_tables.py:360-372` | **MATCH** for hex terrain + forts. Hexside AA shifts (Ridge L2, Up Slope L1, Down Slope L1, Down Esc L2) are **deferred** (`combat_tables.py:380-381`) |
| Barrage shifts | `combat_tables.py:390-397` | **EXACT MATCH** (Rough L1, Mountain L2; forts L1/L2/L2) |
| **Fortification Close-Assault shift** | `combat.py:84` | **WRONG.** `fortification_level * FORT_CA_SHIFT(-2)` yields **L2 / L4 / L6** for levels 1/2/3. The chart says **L2 / L3 / L4**. A Level-2 city is 1 column harder than the book; Alexandria/Cairo (Level 3) are **2 columns** harder. Already flagged at `combat_tables.py:326-327` and never fixed. This is a live suspect in "the Axis can never crack Tobruk" |
| **Stacking Points column** | **absent from the OCR AND from the engine** | `stacking.py:22` `DEFAULT_HEX_LIMIT = 5  # PLACEHOLDER`, applied to every terrain and enforced by `invariants.py:62`. Two cells DID leak through the OCR: **Major City = 8** (`docs/rules/90:17`) and **Road/Track = 5** (`docs/rules/90:22`, footnote 7). The rest must be read off the scan |
| Note 4: every Major City is a **Level 2** fortification; Alexandria/Cairo **Level 3** | `scenario.py:56` | **WRONG.** `MAJOR_CITIES = {"C4807": 2, "C4321": 2}` -- only Tobruk and Bardia. The Delta gets Level 3 (`scenario.py:1203-1205`). **Benghazi is MAJOR_CITY terrain with NO fort** (`scenario.py:1206-1210`); Derna, Mersa Matruh, Sollum and Sidi Barrani are not Major Cities at all |
| Notes 2 and 3 (Salt Marsh / Desert vehicle prohibitions) | -- | **MISSING**; `terrain.py:23-24` admits it |

**And the chart's rows mostly cannot be reached at all.** Measured on `scenario.campaign()`:

```
terrain classes on the map: {CLEAR: 4996, ROUGH: 1072, DESERT: 686, MAJOR_CITY: 10, HEAVY_VEG: 6}
HEXSIDES: 0            roads: 277   tracks: 216   rails: 66   minefields: 0
fortifications: 9 hexes (Tobruk 2, Bardia 2, seven Delta hexes 3)
```

`data/terrain_A-E.json` only ever emits `clear | rough | desert | sea | vegetation`. **GRAVEL, SALT
MARSH, MOUNTAIN and DELTA do not exist on the map** -- there is no Qattara Depression to anchor the
Alamein line and no Jebel Akhdar to slow the Cyrenaica pursuit. And `cna_map.py:52` constructs the
TerrainMap **without passing `hexsides` at all**, so ten more chart rows (both escarpments, both
slopes, ridge, wadi, both rivers, both minefields) are unreachable.

### 6.3 Capability Point Expenditure Summary (`docs/rules/90:525-570`)

`data/cp_costs.json` transcribes **6 of ~25 rows** and wires **4**. Every value present is correct
(assault 5, defend 3, undergo-barrage 3, probe 2, defend-probe 2, break contact 2, disengage 4).

Two further rows ARE charged, at the correct magnitude, but sourced from their home rules rather
than from this chart: construct a real dump = **3** (`construction.py:73` `DUMP_CP`, cited to 24.9;
matches 6.3's "3/2") and blow a dump = **1/3 CPA** (`supply.py:414-420`, cited to 54.14). Correct --
just not bound to the 6.3 chart-of-record.

Charged nowhere: detach 1 / attach-assigned 1 / attach-unassigned 2 / absorb-2-replacements 1 /
friendly-minefield entry (0, 1, 4 + TEC) / enemy-minefield entry (2, 4, 4, **CPA** + TEC -- a
motorized unit's *entire* allowance to enter a mined hex without engineers) / patrol 0 /
desert-raider raid 5 / poison water 1 / sweeten 5 / draw water 0 or 1 / load-unload 0 or 2 /
dummy dump 2 / other construction 0 / rail or air transport of troops 0 / paradrop 0 or 5 /
amphibious landing 5-10 + TEC / ready aircraft 10. The chart's footnote (the -4-differential 2-CP
refund = rule 11.27) is transcribed nowhere.

### 7.2 Initiative Ratings Chart (`docs/rules/90:607-617`)

Transcribed in the docs. **Not in `data/`. Not read by any code.** `scenario.py:39` invents
`{"AXIS": 3, "ALLIED": 2}` for the two Desert Fox scenarios; the campaign passes nothing at all, so
both ratings resolve to 0 through `.get(..., 0)` (`engine.py:220-223`). A **WRONG chart is a WRONG
rule**; an absent one is worse.

### 9.4 Stacking Point Values (`docs/rules/90:641-655`)

Not in `data/`. The ladder (Division 5, Super Brigade 3, Brigade 2, Battalion 1, Company 0; a shell
drops one rung; Truck Points 1/2 per 5; Replacement Points 1 per 5) is unmodelled -- every campaign
counter is SP 1 (281) or SP 0 (22).

### 15.53 Organization Size chart (referenced from 9.28)

`combat_tables.py:308-311` is an **EXACT MATCH** to `docs/rules/90:576-585`. It can never fire: with
every unit at SP 1, `org_size_shift(1, 1)` is always 0.

### 8.89 Off-Map Land Unit Movement Distance Chart

At `docs/rules/90:84-93`. Not transcribed, not used (rule 8.8 is missing).

---

# THE SECTION-32 TRAP

Section 32's own General Rule: *"This Section applies if the Players are playing the Land Game
**without** the Air and Logistics Games... Players will not receive any trucks but rather receive
Motorization Points."* We play the FULL game. Three Section-32 rules are load-bearing in my slice:

1. **`supply.py:229` -- `budget = unit.cpa / 2`. THE BIG ONE.** Every unit's fuel and ammunition
   draw in the campaign is gated on rule **32.16** ("A Supply Unit may be drawn upon by any Friendly
   combat unit if it is within one-half of that combat unit's CPA"). This fires through *my* slice on
   every single move (`_draw_move_fuel` `engine.py:1193`) and every combat (`_charge_ammo`
   `engine.py:2692`). In the full Logistics Game a unit does not trace a radius to a dump -- it eats
   from its **own first-line trucks**, which 2nd-line trucks drive up to it (53.14), and first-line
   trucks **do not exist in this engine** (`is_first_line_truck` is never set). The abstract game's
   supply-range law is doing the full game's job. **Hand to the 52-57 auditor -- but it is the
   single most consequential Section-32 import in the codebase.**
2. **`_supply_movement` `engine.py:1629`** moves a supply dump at **CPA 15** (32.58A: "Motorization
   Points transporting a supply unit... possess a CPA of 15") for a flat **1 Fuel Point** (32.24).
   Both are abstract-game magnitudes. Live in the campaign.
3. **`_organization` `engine.py:1551`** implements 32.32's "thirty Motorization Points per supply
   unit" via the 32.51 MP<->Medium-Truck-Point exchange rate. **Correctly gated OFF**
   (`motorized_supply=False`) with an excellent diagnosis at `scenario.py:1290-1303` -- someone
   already walked into this trap and walked back out. The residue: with it off, a dump now moves for
   1 Fuel Point and **no trucks at all** -- 32.33's permission with neither 32.32's price nor the
   full game's.

Cleared: `supply.fuel_cost` cites 49.13 and `ammo_cost` cites 50.14 -- both full-game (`supply.py:127,147`).
The comment at `engine.py:2425` ("rule 32.21") is stale, but the code under it is the full-game rule.

---

# TOP FIVE

1. **Wire the 7.2 Initiative Ratings Chart.** (S) The campaign runs 111 game-turns of coin-flip
   initiative because `initiative_ratings` is an empty dict. The chart is sitting in
   `docs/rules/90:607-617`: it is date-dependent for the Commonwealth (3/4/5) and *presence*-dependent
   for the Axis (6 with Rommel / 3 with Germans / 1 with neither). Rommel should hold the tempo in
   ~91% of turns and the 1940 Italians in ~19%; both currently sit at 50%. Nothing else in my slice
   is this cheap to fix or this distorting to leave. Delete the two "untranscribed chart" docstrings
   at `engine.py:208` and `state.py:261` while you are in there -- they are false.

2. **Give the map its hexsides and its missing terrain classes.** (L) `cna_map.py:52` builds the
   TerrainMap without `hexsides`, so escarpments, wadis, slopes, ridges and rivers do not exist --
   rule 8.42's "no vehicle may EVER move up an escarpment" is dead, and so is every hexside combat
   shift the engine has already correctly transcribed. The terrain data itself carries only
   clear/rough/desert/vegetation, so there is no salt marsh (no Qattara anchor at Alamein), no
   mountain (no Jebel Akhdar), no delta, no gravel, and only 2 of the map's Major Cities. The combat
   and movement code is *ready* for all of this; the data layer never delivers it. This is the
   largest single gap in the slice and the one that most changes how the campaign plays.

3. **Make contact cost something again: fix the break-off negation and implement 10.31-10.36.** (M)
   Two independent bugs compose into one hole. (a) `zoc.py:125` zeroes the 2-CP/4-CP break-off for
   any unit stacked with a friendly combat unit (proven by probe) -- and since a lone SP-1 battalion
   exerts no ZOC at all, *every* real front-line stack qualifies. 8.67 proves the book intends each
   unit in a stack to pay. (b) 10.31-10.36 -- you MUST attack a hex whose ZOC touches you, or Hold
   Off with a barrage (10.34's point formula), or retreat 3 hexes and take 3 DP -- is absent
   entirely. Together they mean an army can drift up to the enemy, decline battle, and drift away
   for free. This is the friction the whole operational game is built on.

4. **Let armour react, and stop cohesion from being a one-way ratchet.** (S each, one commit) Two
   one-line-ish fixes with outsized effects: `engine.py:1297` should test `is_motorized(u.mobility)`
   (8.53a bars only NON-motorized units) instead of `== Mobility.MOTORIZED`, which currently locks
   **all 39 tanks and all 8 armoured cars** out of Reaction -- including the CPA-45 recce battalion
   the rulebook itself uses as its example reactor. And 6.24.2 (+3 RP whenever your close assault
   empties the enemy hex) is missing, so only *idle* units recover cohesion: the run ends with units
   at -68, sailing past 6.26's -26 threshold, which is itself unenforced (`_movement` has no cohesion
   gate). While there: 6.27's tie-averaging (`engine.py:2569` picks one unit instead of averaging all
   equally-largest ones -- and with every counter at SP 1, *every* stack is a tie).

5. **Charge combat CP to the whole hex (11.25), and charge retreats (8.12).** (S) `_charge_combat_cp`
   bills only the units that actually fired or defended, so a stack attacks with one battalion and
   the other four keep their entire CPA -- and their movement. The book bills every unit in the hex,
   participant or not. Likewise `_retreat` (`engine.py:2611`) charges **zero CP** for an involuntary
   retreat, so a routed unit pays nothing and earns no Disorganization. Both leaks inflate the CP
   economy exactly where the book meant to squeeze it. (Also cheap while you are here: 11.27's 1-CP
   defence at a -4 differential, and the fortification close-assault shift at `combat.py:84`, which
   should be the chart's L2/L3/L4 and is currently L2/L4/L6.)

---

## Two things worth knowing that are not rule rows

- **A unit can be given several MoveOrders in one Movement Segment and the engine executes them
  all.** Probe: (2,1)->(0,1)->(-3,1), 12 CP, one segment, both accepted. This bypasses 8.14 ("stop on
  entering a ZOC"), 10.23 ("may not exit until the next Movement Segment") and, most importantly, the
  8.23 two-hex exploitation gate -- which only guards `_continual_movement` pulses, not segment 0. An
  LLM policy that emits duplicate orders for its best unit gets ungated multi-hop movement no
  scripted policy uses. Boundary-validation hole, not a rules gap.
- **Reaction and Continual Movement have never actually run in the campaign.** 0 REACTION_MOVED, 0
  SEGMENT_ADVANCED across an 8-turn run: `campaign_policy.py` implements neither `react_to` nor
  `continual_movement` (only `staff_policy.py` does). Every balance number taken on the scripted
  campaign was measured on a game where the phasing player gets exactly one movement segment and one
  combat segment per turn, and the defender never dodges. The engine's machinery is there; the
  campaign never pulls the trigger.
