# CNA rulebook port audit — chapters 12–20

Barrage · Retreat Before Assault · Anti-Armor · Close Assault · Patrols · Morale · Reserve ·
Organization · Reinforcements/Replacements/Withdrawals

Audited 2026-07-14 against the CODE and against RUNS, not against docstrings.
Engine at commit `b99e460`. Campaign run: `scenario.campaign(seed=1941, max_turns=45)`.

---

## VERDICT IN ONE PARAGRAPH

The **combat mathematics is the best-ported part of this engine.** Every CRT I could reach —
the 12.6 Barrage table (all 4 target classes × 9 columns), the 14.6 Anti-Armor table (all
306 cells), the 15.79 Close Assault table (both halves, all 18 columns, plus Capt/Eng/Retreat),
the 17.4 Morale Modifier table (all 25 rows), the 15.53 Organization-Size chart — is transcribed
**cell-for-cell correctly**, and the two OCR repairs the code made are independently verifiable
as right by a partition argument. Four of the rulebook's own worked examples reproduce exactly.
That is real work and it holds up.

**Everything wrapped around that mathematics is wrong, missing, or inert.** Rules 16 (Patrols),
19 (Organization) and 20.2–20.9 (Replacements, Production, Withdrawals) do not exist at all —
not one line. Rule 15's guns/vulnerability, prisoners, probes and overrun-rounding do not exist.
Rule 12's Forward/Back gun positions do not exist, so the entire 12.1 subsystem and its
consequences (12.16–12.19, 15.13, 15.84) are dead. Rule 18 is implemented but the campaign
policy never uses it (0 reserve events in 45 game-turns). And the OOB the whole thing runs on
gives the Commonwealth **one battalion where the book gives a brigade three**, hands the Desert
Rats **zero tanks**, and turns the Royal Horse Artillery into **A13 cruiser tanks**.

Three findings are of the "silently poisons every number" class and are called out in
**§WRONG** below: the fortification column-shift, the cohesion-averaging rule, and the OOB
misclassification.

---

## THE FIVE THINGS THAT WILL COST YOU THE MOST — read these first

### W-1. Fortification close-assault shift over-shifts by 1–2 columns (`combat_tables.py:328`)

```python
FORT_CA_SHIFT: int = -2          # applied as fortification_level * FORT_CA_SHIFT
```

Chart 8.37 grades the close-assault fortification benefit **L2 / L3 / L4** for fort levels
1 / 2 / 3. The engine computes `level × −2` → **−2 / −4 / −6**.

| Fort level | 8.37 says | engine gives | error |
|---|---|---|---|
| 1 | L2 (−2) | −2 | correct |
| 2 (Tobruk, Bardia, Benghazi, Derna, Mersa Matruh — 8.37 note 4: "all others are Level Two") | L3 (−3) | **−4** | **1 column too far toward the defender** |
| 3 (Alexandria, Cairo — 8.37 note 4) | L4 (−4) | **−6** | **2 columns too far toward the defender** |

Measured: a +15 differential assault on Alexandria resolves on **column 12 (+5..+6)**; the book
puts it on **column 14 (+9..+10)**. On the 15.79 defender table those two columns are the
difference between a 40–50% loss row existing and not existing.

The code's own comment at `combat_tables.py:326-327` flags this and says "out of scope here."
It is squarely in scope for 15.3/15.31/15.35 and it is **the reason cities cannot be cracked.**
Cross-reference memory `cna-tobruk-crackability`, which blamed the no-eviction rule alone;
this is a second, independent cause that was never found. **Fix: `FORT_CA_SHIFT_BY_LEVEL =
{1: -2, 2: -3, 3: -4}`.** Difficulty **S**. Campaign-critical: **YES**.

### W-2. Cohesion is not averaged over the largest units (6.27, invoked by 15.63 / 17.27)

`engine.py:2569` — `_adjusted_morale`:
```python
largest = max(live, key=lambda u: (u.stacking_points, u.strength))
mod = combat_tables.morale_modifier(largest.cohesion, d1 * 10 + d2)
```

Rule **6.27** (the Largest Unit Rule that 15.63 and 17.27 both defer to):

> "if there is more than one 'largest unit', then the Cohesion Levels of all 'largest units'
> are **added together and divided by the number of contributing counters**."
> *Example: three brigades at −4, −1 and +3 → (−4 −1 +3) ÷ 3 = −1. The Cohesion Level for that
> battle is thus −1.*

**Every combat unit in the engine has `stacking_points == 1`** (verified: `Counter({1: 281,
0: 22})` over the whole campaign OOB). So *every* participating unit is a "largest unit" and
6.27 mandates averaging. The engine instead picks the single **strongest** unit and uses its
cohesion alone. Basic Morale has the same bug (15.64c averages divisional morale: "+3 +1 ÷ 2 = 2").

**This is catastrophic in practice** because cohesion is unbounded downward. Measured cohesion of
the "largest" unit at the moment of assault, over 36 assaults in GT1–45:

```
-9  -23  -13  -13  -20  -5  -15  -15  -16  -8  -25  -31  -5  -10  -18  -20  -17  -30  -74  -75
                                                                   ... and defenders at -68, -52, -27
```

The 17.4 table bottoms out at **"−17 et seq"**, where SURR is **36/36 = 100%**. So:

| cohesion | SURR probability (17.4) |
|---|---|
| −7 | 13.9% |
| −11 | 55.6% |
| −15 | 88.9% |
| **−17 or worse** | **100%** |

Result: **20 of 36 close assaults in the run end in an instant morale SURRENDER** — 10 defender,
10 attacker — annihilating a whole stack before a die is rolled for losses. The last four
assaults of the run are attacking stacks at cohesion −17, −30, −74, −75 destroying themselves.
Under 6.27 a stack of ten units where one is at −75 and nine are at 0 fights at −7.5 → −8
(SURR 25%), not at −75 (SURR 100%).

The engine's *table lookup* correctly clamps to −17 (`combat_tables.py:210`), and 17.24/15.88
are faithfully implemented. The bug is that the **stack cohesion fed into it is a single
outlier instead of an average.** Difficulty **S** (average the cohesion/morale of all
`stacking_points == max` units, round to nearest). Campaign-critical: **YES**.

*(Adjacent, not in my slice but load-bearing: `_overage_dp` at `engine.py:2121` lets a unit reach
−75 in one Operations Stage, and `_idle_recovery` at `engine.py:2107` resets it to 0 when idle.
Cohesion is therefore a within-stage spike, not a campaign state — final spread at GT45 is all
zeros, both sides.)*

### W-3. The Commonwealth's guns are cruiser tanks (`oob.py:146`)

```python
if "Armoured" in g or "Tank" in g:
    return "tank"
```

`classify()` reads the **formation group string**. So every unit whose group contains
"Armoured" or "Tank" becomes a *tank* — and inherits `MODEL_DEFAULTS[("CW","tank")] = "a13"`
(oca 2, dca 3, `armor_protection` 2, `is_tank` True, 8 steps).

Casualties, all present in the campaign at Game-Turn 1:

| counter | what it is | engine makes it |
|---|---|---|
| `BR 3 RHA` | 3rd Royal Horse Artillery — **6 × 2-pounder anti-tank guns** | A13 cruiser tank |
| `BR 4 RHA` | 4th RHA — **6 × 18/25-pounder field artillery** | A13 cruiser tank |
| `BR 65`, `BR 149` | group *"Unassigned **Anti-Tank** Regiments"* | A13 cruiser tanks |
| `BR 1 KRRC` | 1st King's Royal Rifle Corps — **motor infantry** | A13 cruiser tank |

Consequences, all measured:
* The Commonwealth starts the campaign with **zero barrage points from 7 Armd Div** (4 RHA's
  barrage 8 × 6 TOE = 48 raw, gone) and **zero anti-tank guns**.
* All five are `is_tank`, so `_combined_arms_penalty` (`engine.py:2530`) counts **40 TOE of
  "unsupported tanks" with 0 infantry support** → the **maximum −4 Actual close-assault point
  penalty**, offensively *and* defensively, on the Commonwealth's entire starting army. Its raw
  offence of 80 → 8 Actual → **4 Actual**. Halved.
* 5.5" medium regiments (`BR 7 Med`, `BR 8 Med`) get `MODEL_DEFAULTS[("CW","artillery")] =
  "25pdr"`, giving them `anti_armor` 5 — rule 15.54 explicitly names *"Commonwealth 5.5"
  howitzers"* as units with **no** close-assault rating at all.
* AA/Flak (`BR 15 LAA`, `BR 57 LAA`, `BR 9 HAA`, group "Unassigned Air units") fall through to
  `infantry` — 18 free TOE of line infantry, where 15.17 gives them parenthesized ratings worth
  nothing and 15.84b exempts them from gun losses.

Difficulty **S** (classify on the *counter*, not the group; add explicit `role` to the OOB
records). Campaign-critical: **YES**.

### W-4. The Commonwealth brigade is one battalion (rule 20.11)

> **20.11** "the Commonwealth Player receives the 6th New Zealand Brigade **(and its three
> battalions)**"

The `[4.44B]` Organization at Arrival Chart is unambiguous — e.g. 4th Indian Division:
`5th Indian Bde HQ` + `1st Royal Fusiliers` + `3/1 Punjab` + `4/6 Rajputana Rifles`; then
`7th Indian Bde HQ` + `1 Royal Sussex` + `4/11 Sikhs` + `4/16 Punjab`; etc.

`data/reinforcements_campaign.json` models **36 Commonwealth infantry/motor brigades as ONE
6-TOE counter each** (Polish, 7 In, 6 NZ, 19/20/18/26/24 Aus, 3 In Mot, 11 In, 5/2/1/3/6 SA,
14 Inf, 5 NZ, 150 Inf, 9/10/29 In, 16 Inf, 151/69 Inf, 161 In Mot, 2 FF, 20/21/25 In Bde Grp,
131 Inf, 152/153/154 Inf, 1 Greek — plus "4 In Div core" and "44 Inf Div body", which are entire
**divisions** as single 6-TOE counters).

* Engine: 36 × 6 = **216 TOE**
* Book: 36 × 3 battalions × 6 = **648 TOE**, plus 36 brigade-HQ counters
* **Shortfall: 432 TOE strength points of Commonwealth infantry.**

Meanwhile the Italian on-map OOB *does* model regiments **and** their battalions
(`IT 157 - 63 Cir` + `IT I/157` + `IT II/157` + `IT III/157`). The two sides are modelled at
different levels of granularity with no rule behind the choice.

**Measured campaign-wide force ratio (Axis : Commonwealth):**

| | n units | TOE | raw offence | raw defence | barrage | anti-armor | tank TOE |
|---|---|---|---|---|---|---|---|
| Axis | 184 | 1138 | 1556 | 2445 | 1008 | 948 | 176 |
| Commonwealth | 119 | 673 | 952 | 1548 | 624 | 1082 | 144 |
| **ratio** | 1.55 | **1.69** | 1.63 | 1.58 | 1.62 | 0.88 | 1.22 |

**1.69 : 1 in the Axis's favour** — the brief's 1.7:1, confirmed to the decimal. History is
roughly the other way. Fixing *only* the brigade collapse takes the Commonwealth to 1105 TOE →
**1.03 : 1**; adding the missing armour (below) puts it decisively the other way.

Difficulty **M**. Campaign-critical: **YES**.

### W-5. There is no replacement system at all — and it is the Commonwealth's whole advantage

Rules **20.2, 20.3, 20.4, 20.6, 20.7** — Replacement Points, the Conversion Chart, the Axis
Replacement Pool, Commonwealth Production — **do not exist**. Verified structurally: the only
writes to `Unit.steps` in the entire package are `apply.py:241` and `apply.py:398-408`
(`_apply_step_loss`), which are **strictly subtractive**. Nothing in this engine has ever put a
strength point back into a unit. A battalion ground down on Game-Turn 10 is ground down on
Game-Turn 111.

*(Trap for anyone re-auditing: `engine.py:2107` `_idle_recovery` grants **"5 RP"** — that is
**Reorganization** Points, a cohesion gain (rule 6.24.1). It is not a Replacement Point and it
restores no strength.)*

The charts exist and are fully legible:

* **[20.78C] Commonwealth Production** — 62 **Sherman** (max 12/turn, from **GT89**), 56 Grant,
  44 Stuart, 35 Crusader I, 30 Crusader II, 18 Crusader III, 25 Matilda, 20 Valentine, 15 Mk VI,
  10 A10, 8 A9, 8 A13 = **306 tank replacement points**; 250 × 25-pounders; 80 × 6-pounders;
  90 Armoured Recce; 1 Churchill.
* **[20.78B] Commonwealth Infantry Production** — a 2d6 roll every turn. Expected yield:
  6.0/turn (GT3–30), 14.0/turn (GT31–46), **21.4/turn (GT47–102)**, 5.0/turn (GT103–107) →
  **≈1617 Infantry Replacement Points across the campaign.** That is more than twice the
  Commonwealth's entire modelled order of battle.
* **[20.66] Axis Pool** — German 400 infantry (from GT38) + 131 tank points; Italian 1200
  infantry + ~200 tank points.

And the asymmetry that makes the campaign a campaign:

> **20.62** "each Replacement Point is counted against the **Shipping Tonnage** allowance for
> that Game-Turn… 10 Italian Infantry Replacement Points would need 350 Tons of Shipping."
> **20.64** "Replacement Points have priority in Shipping Space over any type of supplies."
> **20.75** "The Commonwealth Player **has no Shipping Problems**; his Replacement Points
> simply arrive."

Every Axis replacement point competes with fuel and ammunition for convoy tonnage and runs the
Malta gauntlet. Every Commonwealth one is free. **This is the historical engine of the campaign
and the engine does not have it.** It also gates victory rule **64.74** (unused-RP victory
points), which `campaign_victory.py:20` lists as deferred.

Difficulty **L**. Campaign-critical: **YES**.

**And there is no Sherman.** `data/unit_stats.json:41-66` `models` block contains no `sherman`,
no `valentine`, no `crusader1`, no `crusader3`, no `churchill`, no `a10`, no `17pdr`, no `bishop`,
no `4.5in`, no `5.5in`. Axis side is missing PzIII E, PzIV E, Marder III, Semovente 75/18,
7.62cm Pak(R), M14/41, Autoblinda 41 and the whole corps-artillery park.

---

# RULE-BY-RULE LEDGER

Status is one of **DONE / PARTIAL / MISSING / WRONG / N/A**.

## 12.0 BARRAGE (Artillery Combat)

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 12.0 GR | Barrage is the first step of the Combat Segment; both sides fire, results simultaneous | **DONE** | `engine.py:2176` `_barrage_step` runs before RBA/anti-armor/assault; `engine.py:2300-2330` builds a `plan` from a pre-loss snapshot `state0` and applies it after | YES |
| 12.11 | Artillery must be placed Forward or Back; whole unit in one position | **MISSING** | no such state. grepped `forward`, `back_position`, `gun_position` in `state.py`/`engine.py` — nothing. `Unit` (`state.py:32-92`) has no position field | YES |
| 12.12 | Position may change only at the start of a Combat Segment | **MISSING** | consequence of 12.11 | NO |
| 12.13 | Forward artillery may **coordinate fire** with other Forward artillery from same or different hexes | **PARTIAL** | `engine.py:2313-2318` combines **all** firers on a target hex unconditionally — coordination is free and universal, never gated on Forward | MAYBE |
| 12.14 | **Italian** Forward artillery may coordinate only **within the same hex** | **MISSING** | `engine.py:2313` pools firers across hexes with no nationality test. Italy is the Axis's artillery arm for GT1–20 | YES |
| 12.15 | Forward artillery may **split** TOE across multiple targets | **MISSING** | `engine.py:2309-2311` — each firer `break`s at the first adjacent enemy hex; one unit → one target, no splitting | NO |
| 12.16 | Back artillery may not coordinate or split; a Back Heavy-Weapons unit **cannot do anti-armor or close assault** | **MISSING** | no Forward/Back state, so every gun always fights. This is a **standing buff to both sides' artillery** | YES |
| 12.17 | Non-phasing **Forward guns take Close Assault losses** even if not participating; all guns do so in an Overrun | **MISSING** | `vulnerability` is set on units (`oob.py:294`) but **never read by any engine code** — grep `vulnerability` in `engine.py` returns nothing. See 15.84 | YES |
| 12.18 | Artillery in **Offensive** Close Assault has Vulnerability halved (round up) | **MISSING** | as 12.17 — no vulnerability consumer | NO |
| 12.19 | Artillery in an **Anti-Armor** role has automatic Vulnerability 2 | **MISSING** | as 12.17 | NO |
| 12.21 | Target Selection: a Parent Formation is many battalion-sized units | **N/A** | descriptive; no engine surface | — |
| 12.22 | All counters with a Stacking Point indicator are targets; **not** HQs without TOE or with parenthesized CA | **PARTIAL** | `engine.py:2289` filters targets to `u.is_combat` (HQs are `is_combat=False`, `unit_stats.json:4,15,29`) ✓ — but Dummy Tank formations (16.4) and warships are not targets because neither exists | NO |
| 12.23 | Barrage is **blind**: defender states only the target's **class**, not its identity or strength | **WRONG** | `engine.py:2286-2290` `_barrage_target` returns `max(combatants, key=lambda u: u.strength)` — the firer gets **perfect information** and always hits the strongest unit in the hex. The book gives him a class label ("Infantry #2") unless he has patrol/combat intel | MAYBE |
| 12.24 | Firer fires "blind" at a numbered target of a given type | **WRONG** | same as 12.23 | MAYBE |
| 12.31 | May barrage any adjacent enemy hex regardless of terrain; may not barrage empty hexes | **DONE** | `engine.py:2309-2311` requires `state0.enemies_at(nb, firing)` | NO |
| 12.32 | No target barraged more than once per Combat Segment from each adjacent enemy hex | **DONE** | `engine.py:2311` `by_target.setdefault(nb, []).append(u)` + the `break` — each side barrages each hex at most once per segment (stricter than the book, which is per firing hex) | NO |
| 12.33 | Terrain / fortification shifts the Barrage **column band** left | **DONE** | `combat_tables.py:479-488` `barrage_terrain_shift`; `engine.py:2324-2325` calls it. Verified vs the 12.33 worked example (12 pts = the 11-12 band, Level-Two fort → the 7-8 band): `min(8,(12-1)//2)=5`, `5 + (-2) = 3` = the 7,8 column ✓ | YES |
| 12.34 | Shifts not cumulative — defender takes the **best**; shifted below the 1-2 column = no effect | **DONE** | `combat_tables.py:488` `min(terrain_shift, fort_shift)`; `combat_tables.py:277-278` `if col < 0: return (False, 0)` | YES |
| 12.35 | No Line-of-Sight restrictions | **DONE** | no LOS code exists — vacuously faithful | NO |
| 12.41 | The 12.6 table covers personnel / armor / artillery / trucks | **PARTIAL** | `combat_tables.py:250-264` has infantry/armor/gun; **truck row absent** | NO |
| 12.42 | Two-dice sequential read-out (larger die first) | **DONE** | `engine.py:2327` `d1 * 10 + d2` where `d1, d2 = r.d6(), r.d6()` — **NOTE:** this is *not* "larger first"; it is first-drawn first. Distributionally harmless only because the CRT rows are the sequential 11-66 space and both dice are uniform — but it means rolls like `16` and `61` are both reachable with the *same* physical dice, i.e. the engine samples the 36 d66 cells uniformly, which is exactly what "larger first" produces over the full space. Faithful in distribution | NO |
| 12.43 | Cross-reference points × dice × target type | **DONE** | `combat_tables.py:267-284` `barrage_result` | YES |
| 12.44 | "P" = **Pinned**: may not move, may not do anti-armor or close assault this segment | **DONE** | `engine.py:2341` adds to `pinned`; enforced at `engine.py:2376` (anti-armor), `engine.py:2430` (assault), `engine.py:2232` (no RBA). Chart note confirms a numeric loss **also** Pins infantry/armor but not guns — `combat_tables.py:281` `return (target_class != "gun", int(loss))` ✓ | YES |
| 12.45 | A number result = that many TOE Strength Points destroyed | **DONE** | `engine.py:2335-2339` emits `STEP_LOST` | YES |
| 12.46 | **Second roll for Trucks** every time you barrage; motorized infantry lose their trucks too | **MISSING** | `combat_tables.py:248-249` documents it as deferred. The 12.6 truck row (`90-charts:716-718`) is not transcribed. Trucks are the campaign's scarcest asset — barrage cannot touch them | YES |
| 12.51–12.55 | **Barrage against Facilities** — cities, forts, roads, railroads, supply dumps, air facilities, via the 41.5 Air Bombardment Table (Raw points for dumps/airfields, 12.54) | **MISSING** | grepped `41.5`, `facility`, `facilities` in `engine.py` — only convoy bombing (`engine.py:377`, `424`). `_batter_fort` (`engine.py:2345`) is rule **25.14** siege wall-battering, gated behind `siege_rules`, and is *not* 12.5. **You cannot shell a supply dump.** | YES |
| 12.6 | Artillery Barrage Table | **DONE** | `combat_tables.py:250-264` — see §CHART FIDELITY, matches `90-charts:705-718` exactly for infantry/armor/gun | YES |

## 13.0 RETREAT BEFORE ASSAULT

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 13.0 GR | RBA happens after all Barrages; non-phasing, non-Pinned units only; it is movement and costs CP | **DONE** | `engine.py:2177` slots `_retreat_before_assault` between `_barrage_step` and `_anti_armor_step`, for `enemy` (the non-phasing side) | YES |
| 13.1 | Any non-Phasing unit that is not Pinned may RBA. **Cohesion −26 or worse may not** | **DONE** | `engine.py:2232-2235` (Pinned reject), `engine.py:2236-2240` (`u.cohesion <= -26` reject) | YES |
| 13.21 | RBA is **Voluntary Movement**: expends CP and Fuel; vehicles subject to Breakdown | **DONE** | `engine.py:2253` `_draw_move_fuel`, `engine.py:2258` `tactics.bp_for_move`, `engine.py:2262` emits `UNIT_MOVED`, `engine.py:2263` charges 6.21 overage. **This is the rule that walked the Alexandria garrison out of the city** — it is correctly implemented; the fault was the policy, not the rule | YES |
| 13.22 | Units in enemy ZOC pay Break-Off cost (8.6) | **DONE** | `engine.py:2241` `tactics.reachable_for_prev(...)` already models break-off | YES |
| 13.23 | Units **beginning** the step adjacent to an enemy combat unit may spend **any** CP | **DONE** | `engine.py:2274-2277` `_rba_cp_cap` — `in_contact` returns the full reach | YES |
| 13.24 | Units **not** adjacent may spend at most **4 CP** (or move one hex, whichever is greater) | **DONE** | `engine.py:2278-2279` — `cost <= 4.0 or distance(...) == 1` | YES |
| 13.25 | During RBA units may only move (exception: blowing supply dumps) | **PARTIAL** | `engine.py:2226` only consumes `MoveOrder`s from `policy.retreat_before_assault`, so nothing else can happen ✓ — but the 54.14/32.3 dump-blowing **exception** is not offered in this step (`_blow_dumps` is a separate phase, `engine.py:1677`) | NO |
| 13.26 | Must cease on entering an enemy ZOC; may not retreat ZOC→ZOC | **DONE** | `engine.py:2241` — `reachable_for_prev` enforces both | YES |
| 13.27 | RBA is voluntary, handled differently from a CRT retreat | **DONE** | separate code path from `_retreat` (`engine.py:2606`) | NO |
| 13.28 | Units that RBA **into an attacked hex** are hit by Anti-Armor fire (but may not return it) and their TOE counts for the assault's percentage losses, though their CA ratings do not | **MISSING** | `engine.py:2222` docstring admits: *"Susceptibility of a unit that retreats INTO an attacked hex (13.28) is deferred."* There is no "retreated-in" marker; such a unit simply defends normally with full ratings — **it is treated as an ordinary defender, not a suppressed one** | MAYBE |

## 14.0 ANTI-ARMOR COMBAT

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 14.0 GR | Both sides fire; all anti-armor losses land **before** Close Assault; units assigned to anti-armor **or** assault, never both; TOE may be split | **PARTIAL** | `engine.py:2178` runs `_anti_armor_step` before assault, both sides, simultaneous (`state0` snapshot, `plan` applied after) ✓. **But there is no assignment step**: `engine.py:2367-2368` docstring — *"Voluntary withholding and splitting TOE between anti-armor and assault are deferred — all committed armor fires and is a target."* Every anti-armor unit fires **and** close-assaults, which the rule forbids | YES |
| 14.11 | Only units assigned to the Anti-Armor sub-segment may fire; only committed units are affected | **PARTIAL** | as 14.0 — no assignment; `engine.py:2375-2380` fires every unarmoured-rated, unpinned unit | YES |
| 14.12 | Phasing fire is directed at an entire hex; non-phasing fire at the assaulting armor. Units that RBA'd into the hex **are** affected and may not be withheld | **PARTIAL** | `engine.py:2378-2380` — both sides target a hex, not the assaulting stack. 13.28's RBA'd-in clause missing (see 13.28) | MAYBE |
| 14.13 | **Back** artillery may not fire anti-armor nor be affected by it; anti-armor guns are always Forward | **MISSING** | no Forward/Back state (see 12.11) | YES |
| 14.14 | Artillery in an anti-armor role has automatic Vulnerability 2 | **MISSING** | vulnerability never read | NO |
| 14.21 | Units withheld from **both** are not affected by anti-armor fire | **MISSING** | no withholding | MAYBE |
| 14.22 | **No hex may be anti-armor attacked more than once per Combat Segment**; firers from different hexes may combine | **DONE** | `engine.py:2380` — `by_target` keyed by hex, one resolution per hex per side; `engine.py:2388` sums `raw_anti_armor` across all firers ✓ | YES |
| 14.23 | If the target hex has **no armor**, the firer may reassign up to ½ (round down) of those anti-armor points to Close Assault | **MISSING** | `engine.py:2379` only ever targets a hex that already contains armor (`any(t.is_armor ...)`), so the situation never arises — but the *reassignment* mechanic does not exist either. Also blocks 16.46 (Dummy Tanks) | NO |
| 14.24 | Ammunition removed as expended | **DONE** | `engine.py:2383-2385` `_charge_ammo(..., activity="anti_armor")` | YES |
| 14.25 | Terrain affects effectiveness; column adjustments made **before** firing | **DONE** | `engine.py:2392-2396` computes the shift then rolls | YES |
| 14.31 | Certain terrain shifts, certain hexsides prohibit | **PARTIAL** | hex/fort shifts done (`combat_tables.py:375-384`); hexside effects and the 14.34 prohibition **missing** | MAYBE |
| 14.32 | Terrain shifts the Actual Anti-Armor Points **column** left, in the defender's favour | **DONE** | `combat_tables.py:360-372` — Heavy Veg L1, Rough L1, Mountain L2. Matches 8.37 (`90-charts:12-14`) ✓ | YES |
| 14.33 | Terrain effects **not cumulative** (take the best); **hexside** effects **are** additional to the hex | **PARTIAL** | `combat_tables.py:384` `min(terrain_shift, fort_shift)` gives the best-of ✓; hexside additions **deferred** (`combat_tables.py:380-381` docstring: the step pools firers from several hexes so no single hexside exists) | MAYBE |
| 14.34 | **No anti-armor fire** through un-tracked Ridge / down un-roaded Slope / down un-tracked Escarpment | **MISSING** | grepped — no prohibition anywhere in `_anti_armor_step`. Guns shoot through mountains | MAYBE |
| 14.35 | A shift below the '1' column uses the '0' column | **DONE** | `combat_tables.py:299` `max(0, min(16, actual_points + terrain_shift))` | NO |
| 14.41 | Results are Damage Points applied to Armor Protection Ratings | **DONE** | `engine.py:2406-2420` `_apply_armor_losses` | YES |
| 14.42 | Armor Protection = Damage Points a step can absorb before destruction | **DONE** | `engine.py:2416` `steps = min(u.strength, math.ceil(remaining / u.armor_protection))` | YES |
| 14.43 | Must remove **at least** enough steps to absorb the damage | **DONE** | `engine.py:2416` uses `ceil` ✓. Verified vs the 14.43 worked example (7 damage vs M13 AP3 + M11 AP2 → 1×M13 + 2×M11) | YES |
| 14.44 | Losses may come from any armor in the hex regardless of assignment; withheld armor is exempt | **PARTIAL** | `engine.py:2411-2419` takes from any armor in the hex ✓; no withholding | MAYBE |
| 14.45 | Excess Damage Points beyond destroying all armor are ignored | **DONE** | `engine.py:2410-2420` — the loop simply ends | NO |
| 14.46 | Destroyed Tank markers; retrievable in the Repair Segment | **MISSING** | `engine.py:2418` emits a plain `STEP_LOST`; no Destroyed-Tank entity. Rule 22 repair of destroyed tanks (22.44 chart exists at `90-charts:1194`) has nothing to act on | MAYBE |
| 14.47 | **Self-propelled guns** absorb at Armor Protection **+ Vulnerability** | **MISSING** | `engine.py:2416` uses `armor_protection` only. No SP role exists in `unit_stats.json` anyway | NO |
| 14.48 | **Halftracks double their Armor Protection** when they are the only anti-armor-able TOE in the hex | **MISSING** | grepped `halftrack` — not found | NO |
| 14.51–14.55 | **Capturing enemy Destroyed Tanks** (capture-or-destroy decision, 3-hex tow, repair) | **MISSING** | no Destroyed Tank entity (14.46) | NO |
| 14.6 | Anti-Armor CRT + the Phasing-player row modifier | **DONE** | `combat_tables.py:222-241` (all 18×17 cells) + `combat_tables.py:287-299`. Phasing modifier `row = max(0, row - 1)` ✓ (11/12 unaffected). See §CHART FIDELITY | YES |

## 15.0 CLOSE ASSAULT

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 15.0 GR | Differential = attacker Actual CA − defender Actual CA, modified by terrain/morale/combined-arms/org-size; both sides roll 2d6 | **DONE** | `combat.py:61-115` `resolve`; `engine.py:2482-2496` | YES |
| 15.11 | All units with a CA Rating may use it; unrated units may participate | **DONE** | `engine.py:2484-2485` sums `raw_offense`/`raw_defense` | YES |
| 15.12 | **Pinned** and **RBA'd-in** units add **no** rating to the defence but **their TOE is still in the casualty pool** | **PARTIAL** | Pinned half is exactly right: `engine.py:2449-2450` excludes pinned from `armed_def`; `engine.py:2488` passes `defender_loss_raw=sum(u.raw_defense for u in defenders)` (all defenders) into `combat.py:107` as the wider casualty pool ✓. The **RBA'd-in** half is missing (13.28) | YES |
| 15.13 | **Back guns are not affected by Close Assault** unless Overrun; Forward guns may participate but their Vulnerability is affected | **MISSING** | no Forward/Back state; no vulnerability consumer | YES |
| 15.14 | Only committed units add ratings; some non-phasing units are affected without participating | **PARTIAL** | see 15.12 | YES |
| 15.15 | Out-of-ammo units may not Close Assault; if **all** non-phasing defenders are out of CA ammo they **automatically Surrender en masse** | **DONE** | `engine.py:2445-2448` + `engine.py:2674-2687` `_defenders_capitulate` — `all(not _has_ammo(...))` → surrender. Phasing units out of ammo are simply dropped (`engine.py:2430-2436`) ✓ | YES |
| 15.16 | A phasing unit may **split** TOE across assaults or withhold; the same hex may never be assaulted more than once per segment | **PARTIAL** | The "once per hex" half is enforced (`engine.py:2194-2198`, `assaulted` set) ✓. TOE **splitting/withholding does not exist** — `engine.py:2189-2192` commits whole units; `engine.py:2181` `committed` set forbids a unit joining two assaults, which is *stricter* than 15.24 allows | MAYBE |
| 15.17 | Units with **parenthesized** CA ratings may only use them in a hex with no combat units; they do not add TOE to the loss pool and may absorb ≤25% of losses | **MISSING** | no parenthesized-rating concept. `engine.py:2193` `defenders = list(r.state.enemies_at(target, side))` — **no `is_combat` filter**, so `is_combat=False` HQs *do* add `dca` and *do* absorb losses without limit. AA/Flak have no parenthesized ratings either (they are plain infantry, see W-3) | MAYBE |
| 15.18 | vs parenthesized-only defenders at 3:1 raw: attacker ignores first 20% losses; defenders taking ≥20% casualties are **captured** | **MISSING** | grepped — not found | NO |
| 15.21 | Phasing units may assault any adjacent enemy hex; **units assigned to Anti-Armor may not Close Assault** | **MISSING** | `engine.py:2361-2403` and `engine.py:2423` — a unit fires anti-armor **and** then close-assaults in the same segment. **This is a direct violation of 14.0/14.26/15.21 and it double-counts every tank battalion's contribution to the segment.** | YES |
| 15.22 | Phasing player announces hexes; states Close Assault or Probe; resolved sequentially | **PARTIAL** | `engine.py:2182-2209` iterates orders sequentially ✓; **Probe never declared** (15.9) | MAYBE |
| 15.23 | A hex may be assaulted/probed **only once** per Combat Segment | **DONE** | `engine.py:2180` `assaulted: set`, checked at `2194`, added at `2208` only on a resolved assault | YES |
| 15.24 | Many units from many hexes may attack one hex; **a phasing unit may assault more than one hex** if the targets are mutually adjacent | **WRONG** | `engine.py:2181` `committed` set and `engine.py:2189` `if a not in committed` **forbid** a unit joining a second assault. The book explicitly allows it. The engine is *more restrictive* than the rule, throttling the attacker | MAYBE |
| 15.25 | Committing **<50%** of available TOE makes the assault a **Probe** | **MISSING** | no Probe (15.9) | MAYBE |
| 15.26 | Basic Assault Differential = attacker Actual − defender Actual | **DONE** | `combat.py:71-73` | YES |
| 15.27 | Adjust the differential **column** (not the number) for terrain/morale/size | **DONE** | `combat.py:75-88` — all shifts accumulate into `shift`, then `col = diff_to_column(diff) + shift` ✓ | YES |
| 15.28 | <5 Raw → 0 Actual; if **both** sides <10 Raw, Raw is used as Actual | **DONE** | `combat.py:53-58` `actual_points`. Verified against four rulebook worked examples (48→5, 24→2, 63→6, 38→4) — round-half-up ✓ | YES |
| 15.29 | Defender allocating **no** units → all his units retreat 3 hexes + 3 DP. Attacker allocating none → no assault | **MISSING** | no allocation step; every defender always defends | NO |
| 15.31 | Terrain adjusts the differential | **DONE** | `combat.py:75-77`; `combat_tables.py:340-353` | YES |
| 15.32 | Defender's hex terrain shifts columns (Salt Marsh shifts **toward the attacker**) | **DONE** | `combat_tables.py:340-347` — Clear/Gravel/Delta/Desert 0, Salt Marsh **+1**, Heavy Veg −1, Rough −2, Mountain −3. Matches 8.37 exactly | YES |
| 15.33 | Hexside crossings adjust the differential; if **any** unit attacks through a hexside, treat all as doing so | **PARTIAL** | `combat_tables.py:349-353` has the right values (Ridge −2, Up Slope −2, Down Slope +1, Up Escarp −3, Down Escarp +1, Wadi −1, Major River −6, Minor River −2 — all match 8.37) ✓. But `engine.py:2455` reads the hexside of **`armed_atk[0]`** only — the *first attacker in list order*, not "any". A stack attacking from three hexes gets whichever hexside the first-listed unit happens to sit on | MAYBE |
| 15.34 | Motorized may not assault up an Escarpment or into Salt Marsh; a unit in a ZOC it cannot attack must retreat 1 hex | **MISSING** | grepped `_resolve_combat` — no mobility/terrain prohibition on assault | NO |
| 15.35 | Terrain effects on Close Assault **are cumulative** (one hexside only) | **DONE** | `combat.py:75-77` adds hex + one hexside ✓ | YES |
| 15.36 | Down-slope/down-escarpment assaults benefit the attacker; up+down offset | **PARTIAL** | values right (`combat_tables.py:351-352`), but only one hexside is ever read (15.33) so no offsetting | NO |
| **15.4** | **Combined Arms**: unsupported tanks lose 1 Actual CA point per 1–3 unsupported tank TOE, cap 4; support must be infantry/MG/heavy-weapons **from the same hex**; applies offensively and defensively | **PARTIAL** | `engine.py:2530-2541` `_combined_arms_penalty`. Maths correct: `min(4, ceil(unsupported/3))` reproduces the 15.4 worked example (2 unsupported tanks @ CA 7 → Actual 1 − 1 = 0) ✓, applied both sides (`combat.py:71-72`) ✓. **Two faults:** (a) **"from the same hex" is not enforced** — support is pooled across every attacking hex; (b) the penalty is subtracted from the side's **total** Actual, not from the tanks' own contribution (`combat.py:71`), which over-penalises when the tank share is small. **And see W-3 — the Commonwealth's artillery and AT regiments are `is_tank`, so this rule fires against them at maximum strength** | YES |
| 15.51 | ≥2:1 in **Raw** CA points → **two columns** to the superior side | **DONE** | `combat.py:78-81` ✓. Edge case: guarded on `defender_raw > 0`, so a defenceless hex gets no +2 (and 15.54 is missing, so it gets nothing at all) | YES |
| 15.52 | Larger **organizational size** → column shift | **INERT** | `combat.py:82` calls `org_size_shift`, but **every combat unit has `stacking_points == 1`** (`Counter({1: 281, 0: 22})` across the campaign OOB) so the shift is always 0 except against a bare HQ. Because rule 19 attachment does not exist, **no division or brigade ever forms**, so this rule can never fire between two real stacks | YES |
| 15.53 | The Organization-Size chart | **DONE (chart) / INERT (use)** | `combat_tables.py:308-320` `_ORG_SIZE_SHIFT` matches `90-charts:576-585` **exactly** (5→3:1, 5→2:2, 5→1:4, 5→0:8, 3→2:0, 2or3→1:2, 2or3→0:4, 1→0:2). Correct data, unreachable | YES |
| 15.54 | A **zero-CA-rated** unit alone in a hex: attacker takes **no casualties**, **+3 columns** to the attacker, 15.51 does not apply | **MISSING** | grepped — not found. Engine artillery has `dca 1`, so the case is rare, but a stack of only pinned/out-of-ammo defenders hits `defender_raw == 0` and gets **neither** 15.51 **nor** 15.54 | NO |
| 15.55 | A brigade counts toward a division only if the **brigade HQ counter** is attached; a division with no infantry-brigade HQ is a **shell** | **MISSING** | no attachment (rule 19) | YES |
| 15.61 | Final Adjusted Morale = attacker's Adjusted Morale − defender's | **DONE** | `engine.py:2491` `morale_shift=atk_m - def_m` | YES |
| 15.62 | + shifts right (attacker), − shifts left (defender) | **DONE** | `combat.py:83` `shift += morale_shift` | YES |
| 15.63 | Use the **Largest Unit rule (6.27)** for units of differing Morale | **WRONG** | `engine.py:2569` takes the single strongest unit's morale; 6.27 requires **averaging over all largest units**, and 15.64c's worked example averages divisional morale ("+3 +1 ÷ 2 = 2"). See **W-2** | YES |
| 15.64 | Worked example of morale in an assault | **DONE (verified)** | all four in-text rolls reproduce against `combat_tables.py:176-203`: 43@−4→−2, 63@+2→NO, 21@−2→NO, 53@−3→−2 ✓ | — |
| 15.71–15.76 | Two dice per player, read **sequentially** for losses and as a **sum** for Capt/Eng/Retreat; Retreat beats Engaged (15.74) | **DONE** | `combat.py:89-96` — `atk_roll`/`def_roll` sequential for `%`, `atk_roll//10 + atk_roll%10` summed for specials; `combat.py:95-96` retreat overrides engaged ✓ | YES |
| 15.77 | The **+11..+17 columns are the Overrun section**; in an Overrun **all defender losses round UP** | **MISSING** | `combat.py:98-99` comment: *"(overrun rounds the defender up under 15.77 — deferred)"*. `combat.py:112` always `math.floor`. Costs the attacker up to one full step per overrun | MAYBE |
| 15.79 | The Close Assault CRT | **DONE** | `combat_tables.py:57-85` + `124-132`. See §CHART FIDELITY — matches `90-charts:805-833` cell-for-cell, two OCR repairs independently verified | YES |
| 15.81 | **Engaged**: units locked; extended CP penalty to leave the ZOC; marker cleared at end of Operations Stage | **DONE** | `combat.py:93` reads it; `state.py:52` `engaged` field; `apply.py` folds it; 8.6 disengage cost is charged. **Note: 0 Engaged results fired in 45 game-turns** — 20 of 36 assaults ended in surrender before the roll | YES |
| 15.82 | **Retreat** n hexes toward supply; 10% extra loss per un-retreated hex; retreats cost CP; **units in a major city may ignore retreat results** | **PARTIAL** | `engine.py:2606-2663` `_retreat`: path away from the attacker, avoids enemy ZOC, prefers the nearest supply ✓; 10% per un-retreated hex ✓ (`engine.py:2657-2663`); major-city exemption ✓ (`engine.py:2615-2618`). **CP is not charged** — `engine.py:2611` admits *"Retreat CP cost (15.82) is not charged yet (flagged)."* A free retreat is a free 6.21 pass | MAYBE |
| 15.83a–c | Loss % × **total Raw assault points**; **attacker rounds up, defender rounds down** | **DONE** | `combat.py:111-112` — `math.ceil` attacker, `math.floor` defender ✓ exactly as 15.83c states | YES |
| 15.83b | Defender's pool **adds** the Raw points of Pinned/withheld units | **DONE** | `combat.py:107` + `engine.py:2488` `defender_loss_raw` ✓ | YES |
| 15.83d | Remove enough steps to **absorb** the Raw points lost, at each unit's CA rating | **DONE** | `engine.py:2702-2720` `_absorb_losses` — `ceil(remaining / rating)`, largest units first ✓ | YES |
| 15.83e | Losses distributed **proportionally** across the hexes involved | **MISSING** | `engine.py:2711` sorts by strength descending and drains greedily — no per-hex proportionality | NO |
| **15.84** | **Guns take Close Assault losses**: (a) Overrun → all guns add Defensive CA and absorb losses; (b) **Forward guns lose ≥50% as many Vulnerability Points as the side lost Raw Points**, minimum 1; AA/Flak exempt; (c) Overrun → all guns take (b) | **MISSING** | **`vulnerability` is populated on every unit (`oob.py:294`) and read by NO engine code.** grep `vulnerability game/engine.py` → nothing. Artillery is **immortal in close assault**. The 15.0 worked example turns on this (the Axis loses 1 TOE of 105mm guns to a 5% loss). This is the single largest missing *loss* channel in the combat model | YES |
| 15.85 | Captured % of losses become prisoners/captured equipment, **rounded up** | **MISSING** | `combat.py:20-21` docstring: *"the Prisoners Captured % table (15.89 — Capt here just records that some already-counted losses are prisoners, no board effect)"*. Measured: 3 attacker-captured and 1 defender-captured results fired in the run, **all inert** | MAYBE |
| 15.86 | How to determine Captured TOE; infantry → Prisoner Points; guns/tanks usable by the enemy | **MISSING** | as 15.85; grepped `prisoner` in `game/` — nothing | MAYBE |
| 15.87 | Losses ≥30% → **all** that player's involved units gain **3 Disorganization Points** | **DONE** | `engine.py:2519-2524` — `if res.attacker_loss_pct >= 30: ... delta: -3` for each unit, and the same for the defender ✓ | YES |
| 15.88 | A player may voluntarily Surrender; units **out of ammo** or at **Cohesion −17 or worse** that are **assaulted** automatically Surrender | **PARTIAL** | The involuntary half is right: `engine.py:2674-2687` `_defenders_capitulate` — `largest.cohesion <= -17` **or** all defenders dry → surrender, applied to the **defender** only, exactly as "that are assaulted" requires ✓. **Voluntary** surrender (17.5) is missing. **And the `largest`-not-`average` bug of W-2 applies here too** | YES |
| 15.89 | Prisoners Captured Results Table (die 1→10%, 2→25%, 3→33%, 4→50%, 5→50%, 6→75%) | **MISSING** | chart at `90-charts:756-762`; grepped `15.89` → only the "deferred" comment in `combat.py:20` | MAYBE |
| 15.91–15.96 | **PROBE**: assault with <50% of available TOE; Engaged results ignored; not in Contact; all-Recce probes take 10% fewer losses; at worse than −3 the defender spends no CP | **MISSING** | `cp_costs.py:21-22`: *"STILL UNCONSUMED… the Probe (2) and Undergo-Barrage (3) rows — the engine does not yet model a distinct Probe."* Probe is the *only* way to attack without committing, and the reconnaissance-in-force is a staple of desert play | MAYBE |

## 16.0 PATROLS AND RECONNAISSANCE

**The entire chapter is missing.** There is no `Phase.PATROL` — the enum at `events.py:29-44` is
`WEATHER, LOGISTICS, ORGANIZATION, CONSTRUCTION, RESERVE, MOVEMENT, COMBAT, REPAIR, RECORD`. The
sequence-of-play loop (`engine.py:140-180`) has no patrol beat.

Grepped: `patrol`, `Patrol Points`, `patrol_points`, `Patrol Segment`, `Patrol Survival`,
`reconnaissance`, `recce`, `Objective Loss`, `Dummy Tank`, `survival`, `16.[0-9]`.
The only literal "Patrol" in `game/` is a docstring at `engine.py:1090` comparing *air* recon to
it. **Decoys:** air recon (rule 42, `engine.py:1086`, fully implemented) is not rule 16; the
`recon` unit **role** (`unit_stats.json:10,20,35`) is a stat block; `is_dummy` (`state.py:161`)
is a dummy **supply dump** (32.18), not a Dummy Tank.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 16.0 GR | Patrols reveal enemy identity/strength; only in an Operations Stage with **no** anti-armor or close assault | **MISSING** | not found: grepped `patrol`, `Patrol Segment`, `Phase.PATROL` | MAYBE |
| 16.11 | Only Recce, Light Tank, or Motorized Infantry may supply Patrol Points | **MISSING** | as above | MAYBE |
| 16.12 | Detach TOE points as Patrol Points | **MISSING** | as above | MAYBE |
| 16.13 | Max 2 TOE Points from any one hex | **MISSING** | as above | NO |
| 16.14 | Max 3 Patrol Points against one hex; may combine from different hexes | **MISSING** | as above | NO |
| 16.15 | No unit at Cohesion −8 or worse may patrol | **MISSING** | as above | NO |
| 16.16 | Each Patrol Point costs **1 Ammunition + 2 Fuel**, present in the origin hex | **MISSING** | as above — a real supply drain the logistics game never pays | MAYBE |
| 16.17 | No patrols into/out of Rainstorm or Sandstorm hexes | **MISSING** | as above | NO |
| 16.21 | May patrol only in a stage with no anti-armor/close assault; may not recon a hex that was barraged or bombed | **MISSING** | as above | MAYBE |
| 16.22 | Patrol range 5 hexes; path may not cross enemy-controlled hexes | **MISSING** | as above | NO |
| 16.31–16.34 | Both sides take losses; Patrol Survival Table (16.6) then Objective Loss Table (16.8); −1 to the die if all Recce | **MISSING** | charts exist at `90-charts:589-599` and `787-797`; no code | NO |
| 16.41–16.47 | **Dummy Tank Formations** — 10 Stores to build, max 3, none Italian, eliminated by close assault or by anti-armor with no real armor present | **MISSING** | grepped `Dummy Tank` — not found. (`is_dummy` on `SupplyUnit` is 32.18, a different rule) | NO |
| 16.51–16.55 | What information must be revealed (designation, type, motorized, TOE ±2) | **MISSING** | as above. **NOTE:** this is the *counterpart* to memory `limited-intelligence-contradicts-brief` — rule 3.6 hides information and 16.5 is the only way to buy it back. Neither side exists | MAYBE |
| 16.6 | Patrol Survival Table | **MISSING** | chart at `90-charts:589-599` | NO |
| 16.7 | Reconnaissance Table | **MISSING** | chart at `90-charts:772-785` | NO |
| 16.8 | Objective Loss Table | **MISSING** | chart at `90-charts:787-797` | NO |

## 17.0 MORALE

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 17.1 | Every unit has a Basic Morale Rating, −3..+3, from its OA Sheet; a battalion's is its Parent Formation's | **PARTIAL** | `state.py:49` `morale`; seeded per-formation by `oob.py:70-103` `FORMATION_MORALE` + `_morale_for`, or stated directly on reinforcement records (`oob.py:298`). Values are plausible but come from a **substring table over formation names**, not a transcription of the OA sheets — and the parenthesized **untrained** rating (17.31) is thrown away | YES |
| 17.21 | Every Close Assault/Probe adjusts Basic Morale by Cohesion | **DONE** | `engine.py:2557-2582` `_adjusted_morale`, called for both sides at `engine.py:2460`/`2467` | YES |
| 17.22 | Use the Morale Modification Table (17.4): row = Cohesion, column = the modifier, 2d6 sequential | **DONE** | `combat_tables.py:206-214` `morale_modifier` | YES |
| 17.23 | Adjusted Morale clamped to **+3 / −3** (exception: 17.28) | **DONE** | `engine.py:2576` `max(-3, min(3, largest.morale + mod))`, with Rommel's +1 added **outside** the clamp at `engine.py:2577-2581` ✓ — exactly the 17.28 exception | YES |
| 17.24 | Cohesion ≤ −17 uses the "−17 et seq" row; ≥ +8 uses the "+8" row | **DONE** | `combat_tables.py:210` `max(-17, min(8, cohesion))` ✓ | YES |
| 17.25 | The **SURR** column → the affected units immediately Surrender; **mutual surrender is ignored** (no assault, both Engaged) | **PARTIAL** | `engine.py:2572-2575` + `engine.py:2478-2481` `_resolve_surrender` ✓. Mutual-surrender is handled at `engine.py:2468-2477` but **emits no Engaged result** — the code comment says *"no assault occurs, so NO ENG (8.63)"*, whereas 17.25 says *"no assault occurs, and **both sides are Engaged**"*. Minor **WRONG** | MAYBE |
| 17.26 | A unit/Formation with Basic Morale **+1 or better** ignores SURR (treats as −4) — **unless** (a) Cohesion ≤ −11 or (b) the enemy has ≥3× the strength | **DONE** | `engine.py:2544-2554` `_honors_surrender` — both exceptions present; `engine.py:2465-2466` computes `overwhelms` as `sum(raw_offense of attackers) >= 3 * sum(raw_defense of armed defenders)` ✓ exactly as 17.26b specifies | YES |
| 17.27 | **Largest Unit Rule** (6.27) for differing Cohesion Levels | **WRONG** | `engine.py:2569` picks a **single** unit; 6.27 mandates **averaging over all largest units**. See **W-2** — this is the difference between a stack fighting at −8 (25% SURR) and at −75→clamped −17 (**100% SURR**) | YES |
| 17.28 | Axis units stacked with **Rommel** get a further **+1**, outside the 17.23 clamp | **DONE** | `engine.py:2577-2581` — keyed on the Rommel **entity** hex, applies to attacking stacks, can break +3 ✓ | YES |
| 17.31 | Units needing Training have **two** Basic Morale ratings; the parenthesized one is the **Untrained** rating on arrival | **MISSING** | `state.py:49` has a **single** `morale: int`. The model cannot express it. `[4.44B]` gives e.g. 4th Indian "**+1 (0)**" and 1st/2nd Armoured "**+2 (+1)**"; `reinforcements_campaign.json` sets `morale: 1` and `morale: 2` — **the trained values, granted free on arrival** | YES |
| 17.32 | Training only at Cairo / Helwan (1430) / Alexandria / Amiriya / Abouqir / Deghelia | **MISSING** | grepped `training`, `trained` in `game/`, `data/`, `tests/` — **zero hits**. *(Caution: `engine.py:2560` mis-cites "17.32" for the Largest Unit Rule, which is 17.27. Grepping `17.3` gives a false positive.)* | YES |
| 17.33 | Training is interrupted by spending **any** CP in an Operations Stage | **MISSING** | as 17.32 | YES |
| 17.34 | **Six Operations Stages** of Training raise the Untrained rating **one point**, never above the designated Basic Morale | **MISSING** | as 17.32. Matches the [17.6] Training Chart ("Commonwealth Unit | 6") | YES |
| 17.35 | A trained instruction battalion (≥⅓ TOE) must be present each stage; tank units need a tank battalion | **MISSING** | as 17.32 | NO |
| 17.36 | Training is optional; **only** Training can permanently raise Basic Morale | **MISSING** | as 17.32 | NO |
| 17.37 | Training Areas are on the maps (Axis: see 20.43) | **MISSING** | as 17.32 | NO |
| 17.4 | The Morale Modification Table | **DONE** | `combat_tables.py:176-203`. Matches `90-charts:846-871` on all 25 rows, with one partition-forced repair (see §CHART FIDELITY). All four rulebook worked rolls reproduce ✓ | YES |
| 17.51–17.56 | **Voluntary Surrender** — all units in a hex, adjacent to an enemy, enemy pays 2 CP to accept; owner may destroy materiel (d6−1)×10% of tanks/guns, ×20% of trucks | **MISSING** | grepped `voluntary surrender`, `17.5` — not found. `_resolve_surrender` (`engine.py:2585`) is the *involuntary* 17.25 path only | NO |
| 17.6 | Training Chart | **MISSING** | chart at `90-charts:875-885` (Inf 3, Tank/Recce 6, Gun 1, Commando 12, CW Unit 6) | YES |

## 18.0 RESERVE STATUS

Implemented — and **completely unexercised**: the 45-turn campaign run produced
`RESERVE_DESIGNATED: 0`, `RESERVE_RELEASED: 0`, `RESERVE_FLIPPED: 0`. The campaign policy never
designates a reserve, so none of this code has ever run in anger.

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 18.11 | Only the **Phasing** player may place units in Reserve | **DONE** | `engine.py:1386-1400` `_reserve_designation` is called for the phasing side only | NO |
| 18.12 | Designated in the Reserve Designation Phase; Reserve I marker | **DONE** | `engine.py:1397` `r.go(Phase.RESERVE, side)`; `apply.py:92-95` → `reserve=1` | NO |
| 18.13 | Unreleased Reserve I units **flip to Reserve II** at the first Reserve Release Segment | **DONE** | `engine.py:1417-1419` `RESERVE_FLIPPED`; `apply.py:97-100` → `reserve=2` | NO |
| 18.14 | Reserve II persists until released or the Operations Stage ends | **DONE** | `apply.py:390-394` `_reset_opstage` zeroes `reserve`/`reserve_released` | NO |
| 18.15 | Units may be placed in Reserve **only** in the Designation Phase | **DONE** | `_reserve_designation` is the sole `RESERVE_DESIGNATED` emitter | NO |
| 18.21 | Two states, marked | **DONE** | `state.py:56-62` | NO |
| 18.22 | Reserve I may move **one hex regardless of CP**, not into enemy-controlled hexes; **Reserve II may never move** | **DONE** | `engine.py:1347-1368` `_reserve_shuffle` — adjacency, in-bounds, stacking, no enemy ZOC/occupied, `cp_spent: 0` ✓; the Reserve II freeze at `engine.py:1229-1243` | NO |
| 18.23-1 | Released from Reserve I: **may not voluntarily exceed its CPA** | **DONE** | `tactics.py:65-66` — `reserve_released == 1` → `return float(cpa)` | NO |
| 18.23-2 | Released from Reserve I: **only ONE offensive Close Assault** that stage | **MISSING** | `tactics.py:62-64`: *"FLAGGED (not yet wired): the companion 18.23-2 / 18.24-2 'one offensive Close Assault (or Probe) only' limit … deferred."* `reserve_released` **never reaches `engine.py`** | NO |
| 18.24-1 | Released from Reserve II: capped at **½ CPA, rounded down** | **DONE** | `tactics.py:67-68` — `float(cpa // 2)`; tested `tests/test_engine.py:337-341` | NO |
| 18.24-2 | Released from Reserve II: only one offensive Close Assault | **MISSING** | as 18.23-2 | NO |
| 18.24-3 | Released from Reserve II: **+1 Disorganization Point** if it does any Close Assault / Anti-Armor / Barrage | **MISSING** | as 18.23-2 | NO |
| 18.25 | Released units may move even if not within 2 hexes of an enemy (exception to 8.23) | **DONE** | `engine.py:1371-1383` `_exploitation_eligible(..., also=released)`; `engine.py:1441` | NO |
| 18.26 | Placing in / releasing from Reserve costs **no CP** | **DONE** | neither `_reserve_designation` nor `_reserve_release` calls `_spend_cp` | NO |

## 19.0 ORGANIZATION AND REORGANIZATION

**The entire chapter is missing.** `engine.py:1551` `_organization` is named for the Organization
Phase but its docstring opens *"[32.32] THE ORGANIZATION PHASE: detail lorries to carry a depot"*
— it attaches **Motorization Points to supply dumps** and never touches a combat unit.
`events.py:32-35` scopes `Phase.ORGANIZATION` to exactly that.

There is **no `parent`, `attached_to` or `assigned_to` field on `Unit`.** The `formation: str`
field (`state.py:77`) is used for morale seeding (`oob.py:97`), Italian-nationality detection
(`supply.py:163`), a staff fuel-priority sort (`staff_policy.py:74`) and narration — **never as a
parent pointer.**

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 19.11–19.14 | Assigned vs Attached; a unit may have both, one of each, never two of either | **MISSING** | not found: grepped `attach`, `detach`, `assigned`, `parent_formation` | YES |
| 19.21–19.28 | Unit Assignments; reassignment in the Reorganization Segment; the special Commonwealth battalion-shuffle rule (19.26) | **MISSING** | as above | MAYBE |
| 19.3 / 19.31–19.33 | Formation Organization Charts (Allied / Italian / German) | **MISSING** | charts not transcribed into `data/` at all | YES |
| 19.41–19.47 | Attachment/Detachment CP costs (1 CP assigned, 2 CP non-assigned, Reorganization Segment only) | **MISSING** | `cp_costs.py` has no attach/detach row consumed | MAYBE |
| 19.5 | Maximum Attachment Chart | **MISSING** | not transcribed | MAYBE |
| 19.61–19.62 | Depleted units may be rebuilt by Replacements; **totally eliminated units may not**; an HQ cadre may be given new battalions | **MISSING** | **Nothing in this engine adds strength to a unit.** The only writes to `Unit.steps` are `apply.py:241` and `apply.py:398-408`, both subtractive | YES |
| 19.63 | An eliminated HQ may be revived with **2 Infantry Replacement Points** if ≥50% of its units survive | **MISSING** | no Replacement Points | NO |
| 19.64 | Which Replacement Point types rebuild which units | **MISSING** | this is the 20.3 Conversion Chart; see 20.3 | YES |
| 19.65 | Recce units rebuilt with Recce points (or Light Tanks) | **MISSING** | as above | NO |
| 19.66 | An eliminated battalion's "space" may be taken by another | **MISSING** | no assignment model | NO |
| 19.67 | The HQ is the Parent Formation's **cadre** | **MISSING** | as above | MAYBE |
| 19.68 | Rebuilding happens **only** in the Organization Phase; 1 CP per 2 Replacement TOE points | **MISSING** | `_organization` (`engine.py:1551`) does supply motorization only | YES |
| 19.71–19.73 | **Axis Battle Groups (Kampfgruppen)**: German max 4 battalions (≤1 tank, ≤2 infantry) + 2 companies; Italian max 3 (≤2 inf, ≤1 armor), max 2 in existence | **MISSING** | grepped `battle group`, `kampfgruppe` — only a stacking-point size label at `combat_tables.py:304`. **This is the German player's signature tool** and it is also the only way to build a 2-SP formation, i.e. the only way to make rule 15.52/15.53 fire | YES |
| 19.81–19.87 | Ad-hoc **Axis Anti-Tank Batteries** on brigade HQs (3–6 TOE of one AT gun, gated on all AT units being ≥67% strength) | **MISSING** | grepped `ad hoc`, `anti-tank batter` — not found | NO |
| 19.91–19.98 | **Augmenting Commonwealth Battalions with Anti-Tank** from GT75 (CPA-10 battalions with 1/2 or 2/2 CA ratings get 1–2 AT TOE points) | **MISSING** | as above. Directly relevant to the 1942 Commonwealth defensive | MAYBE |

## 20.0 REINFORCEMENTS, REPLACEMENTS AND COMMONWEALTH WITHDRAWALS

| Rule | What it says | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 20.11 | Reinforcements are **whole units** arriving per the Reinforcement Track — *"the 6th New Zealand Brigade **(and its three battalions)**"* | **WRONG** | `engine.py:330-338` `_reinforcements` brings on whatever is in the data. **The data is wrong**: `reinforcements_campaign.json` models **36 Commonwealth brigades as one 6-TOE counter each**, and two entire **divisions** ("4 In Div core", "44 Inf Div body") likewise. Shortfall **432 TOE**. See **W-4** | YES |
| 20.12 | Arrive at the start of the Naval Convoy Arrival Phase; **no CP cost to debark**; may move the stage they arrive | **DONE** | `engine.py:149` `_reinforcements(r)` at the turn head; no CP charged | NO |
| 20.13 | Reinforcements are normal units at once | **DONE** | `state.py:573` `on_map` gate — `turn >= arrival_turn` | NO |
| 20.14 | Commonwealth arrive at **Cairo**; Layforce (GT19) and the **Tiger Convoy** (GT32) at **Alexandria**; returning units at either | **PARTIAL** | entry hexes are baked into each record's `hex` field. Tiger Convoy records exist (GT32) but are modelled as **whole tank units**, not as the **tank Replacement Points** the book specifies ("4 × Mk VI Light, 13 × Crusader I, 27 × Matilda, 3 × A13"). **Layforce is absent** | MAYBE |
| 20.15 | **All Axis reinforcements arrive in Tripoli**; may divert 1 battalion-equivalent + ≤10 Truck Points to **Benghazi** if no CW units west of Mersa Matruh and Benghazi is ≥ Level-3 efficiency | **MISSING** | arrival hexes are static per record; no Tripoli→front march, no Benghazi diversion rule. grepped `20.15`, `Benghazi divert` — not found. **The Axis reinforcement march from Tripoli is a major logistical cost the engine skips entirely** | YES |
| 20.21 | All Replacement Points arrive in the Naval Convoy Arrival Phase; Axis planned 2 turns ahead, CW 4 turns ahead | **MISSING** | no Replacement Points exist | YES |
| 20.22 | CW Replacement Points are occasionally on the Reinforcement Track, by **type** | **MISSING** | as above | MAYBE |
| 20.23 | Axis Pool points designated by type, capped per turn | **MISSING** | as above | YES |
| 20.24 | CW Production points designated by type and availability | **MISSING** | as above | YES |
| 20.3 | **Replacement Point Conversion Chart** (HQ = 2 Inf; MG = 2 Inf; Heavy Weapons = 1 Inf + 1 Gun; other Infantry = 1 Inf; Armored Recce = 1 ArmR or 1 Lt Tank; Tank = 1 Tank; …) | **MISSING** | chart at `90-charts:1059-1163`; not in `data/` | YES |
| 20.41 | Trained Replacement Points may be assigned anywhere on the map, same hex as the unit | **MISSING** | no RP | YES |
| 20.42 | RP counters: may not enter enemy ZOC alone; may only defend against Close Assault; **Basic Morale −3**; exceeding CPA → Cohesion −26 | **MISSING** | no RP | MAYBE |
| 20.43 | **Replacement Points must be TRAINED**: Gun **1** OpStage, Infantry **3**, Tank/AC/Recce **6**. Axis train in Tripoli or any major city; CW per 17.32. **5 RP = 1 battalion** | **MISSING** | grepped `training` — zero hits. Chart at `90-charts:875-885`. *(Trap: `engine.py:2107` `_idle_recovery` says "five Reorganization Points" — a **cohesion** gain, rule 6.24.1, **not** a Replacement Point.)* | YES |
| 20.44 | Trained Infantry RPs are trucked forward; Tank/Gun/Recce move on their own or by rail | **MISSING** | no RP | MAYBE |
| 20.45 | RPs need Stores and Fuel when moving; 5 RP = a battalion for all purposes | **MISSING** | no RP | MAYBE |
| 20.46 | RPs moving forward are **Truck Convoys** and move only in the Truck Convoy Movement Phase | **MISSING** | no RP | MAYBE |
| 20.47 | Use the RP Availability and Assignment Sheets | **N/A** | bookkeeping aid | — |
| 20.48 | CP cost to attach RPs is on the 6.3 chart | **MISSING** | no RP | NO |
| 20.49 | RPs may be absorbed **only in the Reorganization Segment**; they then take the unit's cohesion/breakdown levels | **MISSING** | no RP; and `_organization` (`engine.py:1551`) does supply motorization only | YES |
| 20.51–20.55 | **Upgrading Armored Car Effectiveness** — add 1 Light Tank TOE to a Recce/AC unit → Anti-Armor 0→1, Offensive CA 2→3; CW uses Stuarts, Germans Pz II, Italians M11/L6; not before 1/39 | **MISSING** | grepped `upgrade` — not found | NO |
| 20.61 | The Axis Pool caps total and per-turn Replacement Points | **MISSING** | charts at `90-charts:5492-5580`: German 400 Inf + 131 tank pts; Italian 1200 Inf + ~200 tank pts; trucks 835 L / 2890 M / 525 H | YES |
| 20.62 | **Each Replacement Point counts against the Axis Shipping Tonnage allowance** (e.g. 10 Italian Inf RP = 350 tons) | **MISSING** | `data/logistics_rates.json:180` has an unused `replacement_point_tons` key, read by **no** Python file. **This is the Axis's core constraint and it is absent** | YES |
| 20.63 | Axis replacements must be planned **2 turns** in advance | **MISSING** | no RP | YES |
| 20.64 | **Replacement Points have priority in Shipping Space over supplies** | **MISSING** | no RP; the convoy cargo model (`scenario.py:655` `_campaign_axis_cargo`) ships only commodities | YES |
| 20.65 | RPs may not be absorbed by units with no room | **MISSING** | no RP | NO |
| 20.66 | Axis Replacement Pool Table | **MISSING** | `90-charts:5492-5580` | YES |
| 20.67 | Axis Replacement Point Type Limitations Chart | **MISSING** | as above | YES |
| **20.7 / 20.71–20.78** | **COMMONWEALTH PRODUCTION** — most CW replacements arrive **randomly** via the [20.78B] Infantry table (2d6/turn) and the [20.78C] equipment chart; **"The Commonwealth Player has no Shipping Problems; his Replacement Points simply arrive"** (20.75) | **MISSING** | grepped `production`, `Commonwealth Production` — **zero hits in `game/`**. Charts at `90-charts:3391-3480`. Expected yield ≈**1617 Infantry RP** + **306 tank RP** (incl. **62 Shermans from GT89**) + **250 × 25-pounders** across the campaign. **This is the Commonwealth's entire structural advantage and it does not exist** | YES |
| 20.72 | CW plans 2 months ahead, reading the table for the **arrival** month | **MISSING** | as above | YES |
| 20.73 | Infantry and Truck Points are **randomly rolled**; everything else works like the Axis pools | **MISSING** | as above | YES |
| 20.74 | RPs for a turn are divided as evenly as possible among Operations Stages | **MISSING** | as above | NO |
| 20.75 | Reinforcement-Track RPs are **in addition to** Production; CW has **no shipping problem** | **MISSING** | as above | YES |
| 20.76 | CW Planned Replacements arrive in Cairo or Alexandria and must Train | **MISSING** | as above | YES |
| 20.77 | **Upgrading CW Infantry** from GT75 (1/2 → 2/2 CA) using 1 Infantry RP per TOE point; must upgrade the whole unit; no Training needed | **MISSING** | grepped `upgrade` — not found | MAYBE |
| 20.78 | Commonwealth Production System charts | **MISSING** | `90-charts:3391-3480` | YES |
| 20.81 | **Mandatory Withdrawals** are listed on the Reinforcement Schedule, by unit or by type | **MISSING** | grepped `withdrawal`, `MANDATORY_WITHDRAWAL` — not found. `[4.43a]` (`90-charts:1786-1913`) lists **~30 WD rows**: 5 In Bde, 7 In Bde, 4 In Div, 1st Armd Bde, 4 NZ Bde, 2 NZ Div, 16/17 Aus Bde, 6 Aus Div, 150 Inf Bde, 18 Aus Bde, 5 In Div, 10 In Bde, HQ 70 Inf Div, 16 Inf Bde, 14 Inf Bde, Polish Bde, HQ 7 Armd Bde, 70 Inf Div, 3rd In Mot Bde, 25 In Bde Grp + 42/44 RTR, 22nd Guards Bde, 9 In Bde, 9 Aus Div, HQ 10 Armd Div, 9 Armd Bde | YES |
| 20.82 | A withdrawal by type must take a unit at **≥75% TOE** (or the strongest available) | **MISSING** | as above | NO |
| 20.83 | Units must reach Cairo/Alexandria by the due stage or be **eliminated** | **MISSING** | as above | YES |
| 20.84 | Once there, they are removed from play | **MISSING** | as above | YES |
| 20.85 | Under-strength withdrawals must be brought to 75% by Replacement Points first | **MISSING** | as above; no RP | NO |
| 20.9 | **Voluntary Commonwealth Withdrawals** for Victory Points; returning them penalises the CW | **MISSING** | grepped; `campaign_victory.py:20` lists **64.75 Commonwealth Withdrawal VPs** as deferred | MAYBE |
| — | **Returning units (`Rtn`)** — ~12 rows on `[4.43a]`, arriving at max TOE, auto-upgraded, tanks/guns refittable | **PARTIAL** | 4 records exist ("4 In Div core (Rtn)", "11 In Bde (Rtn)", "16 Inf Bde (Rtn)", 32 Army Tank Bde). The other ~8 (6 NZ Bde, rest of 2 NZ Div, 10 In Bde + 28 Fld, HQ 5 In Div + 9 In Bde + 144 Fld, 2 NZ Div, 9 Aus Div, 42+44 RTR with Scorpions) are **missing**, and none of them are tied to a prior withdrawal | MAYBE |

---

# CHART FIDELITY

I compared every chart my chapters reach, cell by cell, against `docs/rules/90-charts-tables-and-play-aids.md`.
`99-foldout-charts.md` contains **no OCR'd content at all** — the six fold-outs are marked
*"oversized foldout; not OCR-able"*. Fortunately the two Reinforcement Schedules and every CRT I
needed live in `90-charts`, not the fold-outs.

## Charts that are CORRECT — verified cell for cell

| Chart | Where | Engine | Verdict |
|---|---|---|---|
| **12.6 Barrage vs Land Units** | `90-charts:705-718` | `combat_tables.py:250-264` | **EXACT** for Infantry (Pin/1/2), Armor (Pin/1), Gun (1/2), all 9 columns. Chart note *"1 = Infantry or Armor: Lose one TOE Strength Point **and Pinned**. Guns or Trucks: Lose one TOE Strength Point"* is correctly implemented at `combat_tables.py:281`. **The Truck row is not transcribed** (see 12.46) |
| **14.6 Anti-Armor Fire CRT** | `90-charts:726-748` | `combat_tables.py:222-241` | **EXACT** — all 18 rows × 17 columns (306 cells) verified. The `0*` column, the row-pairing (`row = (roll//10 - 1)*3 + (roll%10 - 1)//2`) and the Phasing-player −1-row modifier all correct |
| **15.79 Close Assault CRT** | `90-charts:805-833` | `combat_tables.py:57-85`, `124-132` | **EXACT** — attacker 9 loss rows × 18 cols + Capt + Eng; defender 9 loss rows × 18 cols + Capt + Retreat 1/2/3. Confirmed against the rulebook's own 15.73 worked example (+3 column: defender 1-hex retreat on sums 4-7 ✓, attacker Eng on 8-10,12 ✓, defender Capt on 2-3 ✓, attacker Capt none ✓) |
| **17.4 Morale Modifier Table** | `90-charts:846-871` | `combat_tables.py:176-203` | **EXACT** on all 25 rows × 10 columns. All four rulebook in-text rolls reproduce (43@−4→−2, 63@+2→NO, 21@−2→NO, 53@−3→−2) |
| **15.53 Organization Size** | `90-charts:576-585` | `combat_tables.py:308-320` | **EXACT** (5→3:1, 5→2:2, 5→1:4, 5→0:8, 3→2:0, 2or3→1:2, 2or3→0:4, 1→0:2). *(The rulebook **prose** table at `15-close-assault.md:108-119` is OCR-garbled; the engine correctly followed the chart, not the prose.)* |
| **8.37 Close Assault hex shifts** | `90-charts:9-30` | `combat_tables.py:340-353` | **EXACT** for hexes (Salt Marsh R1, Heavy Veg L1, Rough L2, Mountain L3) and hexsides (Ridge L2, Up Slope L2, Down Slope R1, Up Escarp L3, Down Escarp R1, Wadi L1, Major River L6, Minor River L2) |
| **8.37 Barrage shifts** | `90-charts:13-14, 32-34` | `combat_tables.py:390-399`, `479-488` | **EXACT** (Rough L1, Mountain L2; Fort L1/L2/L2). Note 12 (armor targets only get the fort benefit in a Major City) correctly applied at `combat_tables.py:486` |
| **8.37 Anti-Armor hex/fort shifts** | `90-charts:12-14, 32-34` | `combat_tables.py:360-372` | **EXACT** values (Heavy Veg L1, Rough L1, Mountain L2; Fort L1/L2/L2) |

## Two OCR repairs the engine made — both INDEPENDENTLY VERIFIED CORRECT

These are worth recording because they are the *good* kind of finding: the chart's OCR is wrong
and the code caught it.

1. **15.79 defender 10% row, +4 column.** OCR (`90-charts:827`) reads **`24-45`**, which overlaps
   the 15% row's `21-33`. Engine (`combat_tables.py:78`) uses **`34-45`**. I verified by partition:
   with `34-45` the +4 column covers exactly 36 legal d66 rolls (2+4+9+8+7+6); with `24-45` it
   double-covers 24-33. **The engine is right; the book's scan is wrong.**
2. **15.79 defender 5% row, +2 column.** OCR (`90-charts:828`) reads **`41-52`**, leaving rolls
   34, 35, 36 uncovered. Engine (`combat_tables.py:83`) uses **`34-52`** → exactly 36 rolls.
   **The engine is right.**
3. **17.4 Morale, Cohesion −4, "−2" column.** OCR (`90-charts:858`) reads **`42-55`**, leaving
   roll 56 uncovered (35 of 36). Engine (`combat_tables.py:189`) uses **`42-56`**. **Correct.**

*One cell remains genuinely uncertain:* the **15.79 defender 3-hex-retreat row** (`combat_tables.py:132`)
— the OCR at `90-charts:833` has ragged cell alignment and the engine's comment already flags it as
"least-certain". It only affects the three Overrun columns. **Recommend confirming against the
chart image.**

## THE REINFORCEMENT SCHEDULE AND THE ORDER OF BATTLE — TOP PRIORITY

### Axis `[4.43b]` (`90-charts:3683-3813`) vs `data/reinforcements_campaign.json`

I checked 46 identifiable schedule rows. **45 are missing.** Complete list:

```
GT9   It: XXV Corps Arty Regt              GT51  It: IV Genoa MG Bn
GT10  It: 22 Brs Coy [R]                   GT55  It: III(M) Bn [T], I + II Artc Regt
GT10  It: XXXIII Lib Bn                    GT55  It: LII(M) Bn [T]
GT11  It: 10 Brs Regt                      GT59  It: VI Aosta MG Bn
GT12  It: XXXIV Lib Bn                     GT62  It: 5 + 23 Desert Patrol
GT13  It: V(M) Bn [T], 140 CCNN Bn         GT66  Gm: 707 Heavy Wpns Coy, 778 Naval Eng Coy
GT15  It: XXXV Lib Bn, II/87 Bn            GT71  It: LI(M) Bn [T], DLIV + DLVI Arty Bn
GT17  It: XXII(M) Bn [T]                   GT76  Gm: Sonderverband 288 Regt
GT21  Gm: 200 Eng Bn [5 Le]                GT76  Gm: 708 Heavy Weapons Coy
GT22  Gm: I/33 Flak Bn [5 Le]              GT80  Gm: HQ 1st Afrika Arty Regt
GT24  Gm: 529 + 532 CD Arty Bn             GT85  Gm: 13th Coy Brandenburg Regt
GT24  Gm: 528 Arty, 523 CD Arty, Tank Rcvy GT86  Gm: HQ Ramcke Bde, V/Burchardt Bn
GT25  Gm: 300 Oasis Bn (13 coys, GT25-39)  GT87  Gm: IV/Schweiger Bn
GT26  It: 4 Bns, 2nd Arty Raggruppamento   GT90  It: IV(M) Bn [T]
GT27  Gm: HQ 200 Schutzen Regt [15]        GT91  Gm: I/Kroh Bn [Ramcke]
GT28  Gm: HQ 15 Schutzen Bde, HQ 104        GT92  Gm: II/Heydte Bn; It: XIII(M) Bn [T]
      Schutzen Regt, 33 Eng Bn             GT93  Gm: III/Hubner Bn; 220 Eng Bn [164]
GT30  Gm: I/115 Arty, 408 Arty, 362 Arty   GT94  It: I/78 Infantry Bn
GT31  Gm: HQ ArKo 104 Regt                 GT97  It: III/133 Inf Bn; Gm: HQ 2 Afrika Arty
GT32  Gm: I/155 Arty Bn                    GT98  It: 57 Brs Bn [16 Pistoia]
GT34  Gm: 900 Eng Bn [90 Le]
GT34  Gm: III/155 Arty Bn, 140 Arty Regt   PLUS ~19 German Flak battalions across 14 rows
GT35  Gm: HQ 155 Arty Regt                       (GT52 I/18, GT58 612, GT59 II/25+I/53,
GT36  Gm: 557 Arty Bn                             GT60 368, GT61 841+192, GT66 114+442,
GT39  Gm: 30 Flak Bty                             GT67 I/43, GT68 I/6, GT70 617, GT88 II/46,
GT40  Gm: 1/902 Arty Bty                          GT89 I/54+211, GT91 243+329,
GT45  Gm: 149 CD Arty Bn; It: RECAM               GT92 II/12+358+860, GT93 II/5) — NONE present
```

The combat-relevant losses are the **seven Italian M-tank battalions** (V, XXII, III, LII, LI, IV,
XIII (M)), the **Ramcke Brigade** (4 parachute battalions), **Sonderverband 288**, the **300 Oasis
Battalion** (13 companies), the **Libyan battalions**, **10 Bersaglieri Regiment**, and the entire
**corps/coastal-defence artillery park**. The Flak battalions matter less (15.84b exempts AA from
gun losses; 15.17 gives them parenthesized ratings), but they are 19 counters of stacking and
supply demand.

### Commonwealth `[4.43a]` (`90-charts:1781-1915`)

The OCR of this chart is a **two-column layout that the scanner interleaved**, so a mechanical
row-by-row diff is unsafe. What is unambiguous:

* **36 infantry/motor brigades are single 6-TOE counters** where the book gives each a brigade HQ
  + **three battalions** (20.11, and `[4.44B]` shows it explicitly). **Shortfall 432 TOE.** (W-4)
* **The 7th Armoured Division has no tanks.** `[4.44B]` (`90-charts:2000-2014`) deploys at
  Game-Turn 1 ("D"): 6 RTR (10 × Mk VI), 7 Hussars (10 × Mk VI), 1 RTR (7 × A9), 8 Hussars
  (7 × A10) = **34 tank TOE**, plus 2 Rifle Bde, 11 Hussars (recce), 3 bde/div HQs. The engine has
  **three** counters for the whole division — and all three are the misclassified `3 RHA`, `4 RHA`,
  `1 KRRC` (W-3).
* **The 1st Armoured Division is 1/12 present.** `[4.44B]` (`90-charts:1943-1954`) lists 12
  counters arriving GT56–59 (Div HQ, 2 Armd Bde HQ, 2 Bays, 10 Royal Hussars, 9 Lancers, 1 Rifle
  Bde, 1 Spt Gp HQ, 2 KRRC, 76 AT, 11 RHA, 61 LAA, 12 Lancers). The engine has **only**
  `1 Support Group` (GT59).
* **~30 Mandatory Withdrawal rows and ~8 Return rows are absent** (see 20.81).
* **Layforce (GT19)** is absent.
* The **Tiger Convoy** (GT32) is modelled as whole tank units rather than the tank **Replacement
  Points** the book specifies.

### `data/unit_stats.json` model coverage

Missing Commonwealth models named on the [20.78C] Production Chart: **Sherman** (62 pts, GT89),
**Valentine** (20, GT39), **Crusader I** (35), **Crusader III** (18, GT88), **Churchill** (1),
**A10**, **17-pounder**, **SP 6-pounder**, **4.5" gun**, **5.5" howitzer**, **155mm howitzer**,
**Bishop** (SP 25-pdr, per `[4.43a]` note b), **Scorpion** (per `[4.43a]` GT99).
Missing Axis models named on the [20.66] pools: **PzIII E**, **PzIV E**, **Marder III**,
**7.62cm Pak(R)**, **2.8cm sPzB41**, **Semovente 75/18**, **M14/41**, **Autoblinda 41**, and the
whole German heavy-artillery park (10.5cm K18, 15cm K18/sIG33, 17cm K18, 21cm Mrs.18, 7.5cm IG18).

---

# THE SECTION-32 TRAP

Section 32 (Abstract Logistics) applies **only** when playing *without* the Logistics Game. We run
the full game. Within chapters 12–20 I found **one clear hit and one boundary case**:

1. **`engine.py:2299` (`_barrage_step` docstring) — CONFIRMED TRAP.**
   > *"Terrain column-shifts and the separate truck roll (12.46) are deferred."*

   and `combat_tables.py:248-249`:
   > *"Trucks (a separate 12.46 roll) are deferred (**abstract logistics 32.56 says barrage never
   > hits trucks**)."*

   **This is exactly the trap.** Rule 12.46 is a full-game rule: *"Every time a Player fires at a
   given target… he must roll a second time to determine whether any Trucks attached to the Target
   unit… are affected."* The engine declined to implement it by citing **32.56**, an abstract-game
   rule that does not apply to us. In the full Logistics Game, **barrage destroys trucks** — and
   trucks are the scarcest thing on the board. The 12.6 chart's Truck row (`90-charts:716-718`) is
   sitting there untranscribed. **This is a WRONG, not a DONE.**
   *(The terrain column-shift half of that docstring is stale — it **is** implemented, at
   `engine.py:2324`.)*

2. **`engine.py:1551` `_organization` — boundary case, not my call.**
   The Organization Phase is implemented purely as rule **32.32** (Motorization Points carrying
   supply dumps), a Section-32 rule, while rules **19.68** ("Rebuilding units takes place in the
   Organization Phase only") and **20.49** ("Replacement Points may be absorbed only during the
   Reorganization Segment") — the *full-game* content of that phase — are absent. Whether 32.32's
   motorization is itself a trap belongs to the logistics slice; but the fact that the phase named
   for rule 19 contains **none of rule 19** is squarely mine, and it is recorded above.

No other Section-32 code touches chapters 12–20. The ammunition gate in `_charge_ammo`
(`engine.py:2690`) cites 32.21 in a comment but calls `supply.plan_draw` against the real
multi-commodity dump model, which is the full game.

---

# TOP FIVE — what I would fix first

### 1. The fortification close-assault shift (`combat_tables.py:328`) — **S**
`level × −2` should be `{1: −2, 2: −3, 3: −4}`. One dict. It is currently making every Level-Two
city **one column** and Alexandria/Cairo **two columns** harder to take than the book allows, and
it has been silently under every "can the Axis crack Tobruk" measurement ever taken. Cheapest
possible fix, largest possible distortion removed.

### 2. Average the cohesion/morale over the largest units, per 6.27 (`engine.py:2569`) — **S**
Twenty of thirty-six close assaults in a 45-turn run end in an instant morale **surrender**
because one outlier unit at cohesion −75 speaks for the whole stack. 6.27 says average; the
engine says "pick the strongest". Until this is fixed, **every combat number this engine produces
is noise** — the CRT barely gets to roll. Fix this before you tune anything.

### 3. Fix the OOB classifier and give the Commonwealth its battalions (`oob.py:146`, `data/reinforcements_campaign.json`) — **S** then **M**
Two separate bugs, same file family. (a) `classify()` reads the *formation group*, so
"Unassigned **Anti-Tank** Regiments" and "7th **Armoured** Division" both return `"tank"` — the
Royal Horse Artillery is an A13 cruiser and the Commonwealth eats a maximum combined-arms penalty
on its own guns. (b) 36 Commonwealth brigades are one battalion each (20.11 says three), which is
the whole of the 1.69:1 force ratio. Also restore the 7th Armoured Division's 34 tank TOE — the
Desert Rats currently have **no tanks**.

### 4. Guns and Vulnerability in close assault — rule 15.84 (`engine.py:_resolve_combat`) — **M**
`vulnerability` is populated on every unit and **read by no code in the engine**. Artillery is
immortal in close assault: it cannot be overrun, cannot be lost, cannot be captured. 15.84b (the
Forward-gun 50%-of-raw-points-lost Vulnerability toll) is the loss channel the rulebook's own
worked example turns on, and it is the counterweight that stops both sides from stacking guns
forward with impunity. Bring 12.11–12.19 (Forward/Back) with it — they are the same subsystem, and
without Forward/Back, 12.14 (Italians may only coordinate within a hex), 12.16, 14.13 and 15.13
are all unenforceable.

### 5. Rule 20.6/20.7 — the Replacement economy — **L**
Nothing in this engine has ever put a strength point back into a unit. The Commonwealth's real
advantage is not on the reinforcement track — it is **≈1617 free Infantry Replacement Points and
306 tank points (62 of them Shermans) that "simply arrive" (20.75)**, against an Axis pool that
must buy every point with convoy tonnage at 30–235 tons apiece, at priority over its own fuel
(20.62/20.64), through Malta. That asymmetry *is* the campaign. It also gates victory rule 64.74,
which cannot be scored without it. Do this **after** 1–4, but know that the balance will not be
real until it is done — and that the 1.7:1 ratio you are looking at now is measuring an army that
cannot bleed and cannot heal.

---

## Appendix — how the runs were made

* Campaign: `game.scenario.campaign(seed=1941, max_turns=45)` with `CampaignAxisPolicy` /
  `CampaignCommonwealthPolicy`, ~3 min.
* Event census over GT1–45: `COMBAT_RESOLVED` 36, `BARRAGE_RESOLVED` 6, `ANTI_ARMOR_RESOLVED` 6,
  `RESERVE_*` 0, `STEP_LOST` 866 (of which **attrition 629**, surrender 191, attacker 29, armor 9,
  defender 7, barrage 1).
* Combat is a **rounding error** next to supply attrition in this campaign: 46 steps lost to all
  land combat combined, against 629 to starvation. Worth remembering when reading any balance
  number.
* Force totals computed directly from `oob.build(oob_file="oob_italian.json",
  extra_file="oob_campaign_extra.json", sections="ABCDE",
  reinforcements_file="reinforcements_campaign.json")`.
* Scratch scripts under `$CLAUDE_JOB_DIR/tmp/` (`probe.py`, `aud1220_coh.py`); nothing was written
  to `game/`, `data/` or `tests/`.
