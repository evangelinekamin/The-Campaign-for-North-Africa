# Port audit — chapters 01-04, 59, 60, 61, 62, 63, 64

**Scope**: introduction, how-to-play, glossary/unit definitions, game equipment, introduction to
scenarios, and all five scenario groups — ending with **chapter 64, THE CAMPAIGN FOR NORTH AFRICA**,
the scenario we build.

**Audited against**: `git HEAD = a3bfbcf` (working tree had `game/campaign_policy.py` and
`scripts/measure_campaign.py` modified by another agent; both were read but not relied on).
Verified against **code and runs**, not docstrings. Where a docstring and the code disagree, the
code wins and the docstring is called out.

---

# 🔴 THE ONE FINDING THAT MATTERS

**The campaign is an Axis Smashing Victory at Game-Turn 1, before anybody moves.**

```
*** THE SCORE AT GAME-TURN 1, BEFORE ANYBODY MOVES ***
   AXIS 300   COMMONWEALTH 20
   grade: Axis Smashing Victory: 300-20 Victory Points (64.76)
```

After **111 Game-Turns × 3 Operations Stages = 333 stages of war**, measured over three seeds, the score
moves by **−25, −25, +145** for the Axis and **±0, +60, ±0** for the Commonwealth. **The grade is "Axis
Smashing Victory" in all four states — at GT1 and at GT111 in every seed.** The outcome of the campaign is
the September-1940 set-up, re-read at Game-Turn 111.

Four faults stack to produce it, and **all four are in this slice**:

1. **The Axis starts standing on the two biggest prizes** — Tobruk (200 VP) and Bardia (100) — and passes
   the occupation test *because the 60.34 staging dumps are underneath them*. The Commonwealth's two cities
   are worth **10 points each to it**.
2. **Benghazi (75 VP) is empty at GT1** and the 200-VP Tobruk fortress is held by a lone HQ counter — their
   garrisons are seeded 2 and 4-5 hexes away, because `data/oob_italian.json` is a **raw VASSAL save
   extraction**, not a transcription of rule 60.31.
3. **Giarabub and Derna are garrisoned and score nothing**, because the engine's 64.73 test asks *"can you
   reach a dump holding ammo?"* where the rule asks *"do you have ammunition for three fires?"*
4. **The Commonwealth cannot take anything back**, because its army is loaded at **32% of its own chart**,
   with **no real tanks, no artillery and no AA arm**. It ends the war with 28 / 17 / **10** combat units.

**And the deepest point: we implemented exactly the subset of rule 64.7 that favours the Axis.** The
rulebook gives each side an outright-win instrument. **64.71 (the Axis's) is implemented. 64.72 (the
Commonwealth's) is not.** Nor is **64.75**, the Commonwealth's only non-geographic VP source. The 64.73
point table is *supposed* to be Axis-heavy — an Axis still holding Cyrenaica at the end is the "nothing
happened" baseline — and the Commonwealth's answer to it was never to out-point the Axis on geography. It
was to **strangle the Axis supply and win outright under 64.72**. We removed its only weapon and then spent
weeks measuring the balance.

*Full working: §11. Ranked fixes: §12.*

---

## 0. READ THIS FIRST — what has moved since the brief was written

Three of the four seeding gaps in the brief **have been fixed** (commit `3d9dbff`, "the charted lorry
parks (60.33/60.43) + the Commonwealth's initial dumps (60.44)"). Verified by building the state:

| Brief's claim | Status now | Evidence |
|---|---|---|
| 60.44 CW dumps (Matruh 1000/3000/4000; Barrani 250/500/100) never placed | **FIXED** | `game/scenario.py:701-704` `_CW_DUMPS_60_44`; built state shows `AL-Stage-Matruh ammo=1000 fuel=3000 stores=4000`, `AL-Stage-Barrani 250/500/100` |
| 60.33/60.43 lorry parks at ~1/10 the charted allotment | **FIXED** | `game/scenario.py:809-819` `_TRUCKS_60_33`/`_TRUCKS_60_43`; built state = Axis 215 TP, CW 195 TP |
| 60.34 Axis staging dumps stand on the victory cities | **STILL TRUE, and still the whole score** | `game/scenario.py:645-652` — `AX-Stage-Tobruk` on C4807 (200 VP), `AX-Stage-Bardia` on C4321 (100 VP), `AX-Stage-Derna` on B5925 (25 VP). This is *faithful to 60.34* (the chart really does put dumps there); the problem is that nothing else scores. |
| OOB is thin; no Sherman; 1.7:1 Axis force ratio | **STILL TRUE — and it is the #1 fidelity gap** | measured below |

**So the remaining work is (a) the order of battle, (b) rule 64 itself, which has never been audited,
and (c) a set of seeds that are still missing or wrong — several of them larger than the ones just
fixed.**

### The five things this audit found that nobody was looking for

1. **The campaign is seeded from the WRONG SCENARIO GROUP's supply charts.** Rule 64.3 says the full
   campaign takes its supplies from **section 60.0**. `game/oob.py:39-40` seeds them from
   **61.44 / 61.36** — the *Desert Fox (GT26)* allotments. Exact match confirmed: the five `AX-Dump`
   counters carry 2,500 Ammo / 9,600 Fuel / 950 Stores / 1,100 Water = **61.44 verbatim**; the five
   `AL-Dump` counters carry 1,700 / 2,550 / 1,600 = **61.36 verbatim**. The Axis is getting **3.2x the
   charted 60.34 desert-dump fuel** (9,600 vs 3,000) in a scenario it is not playing.
2. **Every port's Efficiency Level is wrong, and the correct values are already in the repo.**
   `data/logistics_rates.json` carries the charted 55.3 levels (Tobruk 5, Benghazi 3, Mersa Matruh 1).
   `game/scenario.py:996-1004` reads only the `tons` key and **hardcodes `eff=10/max_eff=10`** for
   Benghazi and Matruh and `eff=5` for Tobruk. Consequences, computed: Tobruk lands **425 Ammo/OpStage
   instead of the charted 170** (2.5x — rule 55.25's San Giorgio penalty of −3 levels is simply not
   applied); Benghazi needs **10 levels of bomb damage to shut instead of 3**; Mersa Matruh **10
   instead of 1**. The `Port` docstring at `game/state.py:321-323` *claims* "Tobruk seeds
   eff=2/max_eff=5". **The docstring lies.**
3. **There are no first-line trucks anywhere in the engine.** `is_first_line_truck` is never set True
   in any file. The 60.31/60.41 charts allot **~360 Axis and ~177 Commonwealth Truck Points** of
   first-line transport, hex by hex, to every starting formation — *more than the 2nd/3rd-line parks
   that were just fixed*. None of it is seeded, and with it goes 59.66B (each attached Motorization
   Point may start loaded with 1 Ammo or 3 Fuel).
4. **The campaign has no initiative rule and no Initiative Ratings.** `campaign()` is the only
   scenario that sets none of `initiative_fixed` / `initiative_fixed_until` / `initiative_ratings`
   (contrast `game/scenario.py:158-159`, `318-319`). So rule **60.6** (Italian Initiative for the whole
   of Game-Turn 1, which 64.4 imports) never fires, and every one of the 111 turns is decided by a
   bare d6 with **both ratings at 0**.
5. **Rommel is not in the campaign.** `campaign()` sets `rommel=None`. The `Rommel` entity, the Berlin
   recall, the anchor and the raid machinery all exist (`game/engine.py:266-330`) and are seeded only
   by `rommels_arrival`. Rule **64.51 explicitly names "Raids on Rommel"** as permitted in the campaign.
   The same is true of the **Commonwealth Mediterranean Fleet**, which 64.51 also names: `naval` is
   **never seeded by any scenario** (`grep -rn "naval=" game/scenario.py` → nothing).

---

## 1. CHAPTER 64 — THE CAMPAIGN FOR NORTH AFRICA, RULE BY RULE

This chapter has never been audited. Here is the complete gap list.

| Rule | What it says (one line) | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 64.1 | Prose: the campaign needs ≥10 players, a commander per division plus Air/Logistics/Supreme. | **N/A** — designer's note, no rule content. (It *is* the charter for the 5-agent AI staff, which exists: `game/staff.py`, `game/staff_policy.py`.) | `docs/rules/64:6` | NO |
| 64.2 | **Two** campaign scenarios: (a) full, from GT1.1 (Sep 1940); (b) "shorter", from GT26.3 (Rommel). **Both end at the completion of GT111 OpStage 3.** | **PARTIAL** — (a) is DONE and exact: `calendar.FINAL_GT=111`, `season_offset=24` → GT1 = Sep 1940, `for stage in (1,2,3)`. **(b) the SHORT CAMPAIGN IS NOT IMPLEMENTED** — `campaign()` is the only builder and starts at GT1. (`rommels_arrival` is the 61.2 *Race for Tobruk*, a 13-turn scenario ending GT38 — not the short campaign.) | `game/calendar.py:20`; `game/scenario.py:1154,1274`; `game/engine.py:142`; `grep -rn "def campaign\|short_campaign" game/scenario.py` → one hit | **(a) YES / (b) NO** — we build the full campaign; (b)'s absence is *why* 64.53/64.54 are moot |
| 64.3 | Full campaign takes initial placement of land, sea, air, **supplies and construction** from **§60.0**; short campaign from §61.0. | **WRONG** — the land OOB and the 60.34/60.44 dumps come from §60, but **the mobile dump supply POOLS come from §61**. `game/oob.py:39-40` calls `axis_dump_pool_61_44()` and `cw_dump_pool_61_36()`. Built state: `AX-Dump`×5 = 2,500A/9,600F/950S/1,100W (**61.44 verbatim**); `AL-Dump`×5 = 1,700/2,550/1,600 (**61.36 verbatim**). The 60.34 chart's own free-placement dumps (Dump 1 + Dump 2 = 2,000A/3,000F/2,500S/400W) are **not** seeded; the 61.44 pool stands in for them at **3.2x the fuel**. | `game/oob.py:39-40,222-229,233-251`; `game/logistics_data.py:157-170`; built state | **YES — the single largest supply-fidelity error** |
| 64.4 | Determine Initiative using §60.0 (or §61.0). [→ **60.6**: the Italian has the Initiative for the **entire first Game-Turn**; roll normally from GT2.] | **MISSING** — `campaign()` sets **no** `initiative_fixed`, **no** `initiative_fixed_until` and **no** `initiative_ratings`. It is the only scenario that doesn't (cf. `scenario.py:158-159`, `318-319`, which set `initiative_fixed=AXIS, until=2, ratings={"AXIS":3,"ALLIED":2}`). Result: GT1 initiative is **rolled**, not given to the Axis; and all 111 turns roll a bare d6 with **both ratings 0** (`engine.py:220-222` `.get("AXIS", 0)`). | `game/scenario.py:1268-1285` (no initiative kwarg); `game/engine.py:203-234` | **YES** |
| 64.5 | Header: special rules / adjustments. | N/A — header | `docs/rules/64:20` | — |
| 64.51 | **No restrictions on normal game actions** — "Raids on Rommel, the Commonwealth Fleet, etc. may be performed as per the appropriate rules". | **MISSING (both named systems)** — `campaign()` sets `rommel=None`, so **Rommel is not in the campaign at all** (and with him the 31.x Berlin recall + the raid). `naval=()`: the **Commonwealth Mediterranean Fleet is never seeded by any scenario** — `NavalUnit` and `engine._naval_bombardment` are live code with no caller. | `game/scenario.py` campaign ctor (no `rommel=`/`naval=`); `grep -rn "naval=" game/scenario.py` → 0 hits; `game/state.py:290,442,472`; `game/engine.py:266-330` | **YES** — 64.51 names both by name |
| 64.52 | Axis **Malta Air Availability** uses the **campaign row** of the Axis Strategic Airforce Commitment Chart [44.41]. That row is: **Level I = Unlimited, II = 25 GT, III = 12 GT, IV = 12 GT**. | **MISSING, and what stands in its place is INVENTED** — there is no Malta availability system anywhere (`grep -in malta game/engine.py game/state.py` → 0 hits). In its place, `scenario._malta_bomb_points(gt)` is a **hardcoded month-by-month Bomb-Point schedule of our own devising** (100/200/300/500/0/150/400), whose own docstring calls it "a FLAGGED proxy" and **"a primary calibration lever for the Axis faucet"**. This is exactly the invention the port is meant to remove. | `docs/rules/90:6007` (the chart row); `game/scenario.py:1060-1079`; `game/scenario.py:1081-1091` | **YES** |
| 64.53 | **IF the shorter campaign is being played**, adjust the Axis Replacement Pool: A German — no change. B Axis trucks reduced **to** 800 L / 2,400 M / 500 H. C Italian — half of all RPs plannable through GT24 removed (round fractions up), **except** 60 CV L.3 / CV 33-35 tank RPs remain. | **N/A — short-campaign only.** The rule text opens "If the shorter campaign game is being played"; we build the GT1 campaign, so none of it applies. (For the record, if it were: Axis pool 2,493 → 2,401.) | `docs/rules/64:26`; verified against `docs/rules/90:5494` (Axis Truck Production), `:5539` (Italian Production) | **NO** (gated on a scenario we don't build) |
| 64.54 | **IF the shorter campaign is being played**, adjust the Commonwealth Production System: A trucks — no change. B infantry — no change. C nine rows reduced **to** the listed numbers (Armd Car 75, Lt AA 70, 25-pdr 230, 2-pdr 50, Mk VI 5, A9 3, A10 3, A13 5, Matilda 20). | **N/A — short-campaign only**, same gate. (If it were: CW pool 958 → 878.) | `docs/rules/64:34`; `docs/rules/90:3428` [20.78C] | **NO** |
| 64.6 | Pick a start point and use §32.0 / §47.0 / §58.0 as appropriate, plus the **abstracted set-up for that scenario group** and the 64.5 replacement adjustments. | **PARTIAL** — the engine plays **Land + full Logistics + abstract Air (58.0)**, which is exactly 59.61/60.91 ("Air Abstracted (Land & Logistics Games): **None**" — no adjustments needed). That reading is correct and clean. **But 59.61 also says to "ignore all Trucks and supplies available at/for Air facilities in the initial set-ups", and the engine seeds the air-facility TRUCK rows anyway** — 60.33's `Any Air Facility` (10 L / 50 M) onto Benghazi and 60.43's (5 L / 30 M / 20 H) onto the railhead. It correctly *drops* the air-facility *supply* allotments. So the same rule is obeyed for supplies and disobeyed for trucks. Over-seeds Axis +60 TP, CW +55 TP. | `docs/rules/59:110` (59.61); `docs/rules/60:415` (60.91); `game/scenario.py:812,818,851-854,866,876-877,893` | **YES** (a small but self-inconsistent over-seed) |
| **64.7** | Header: victory conditions. | — | `docs/rules/64:58` | — |
| **64.71** | Axis wins **regardless of turn or date** if it occupies **all hexes of Alexandria AND Cairo** **for one full Game-Turn**, and the occupiers can trace a supply line back to a Supply Dump supplied from **Tobruk or Tripoli**, that line being **≤90 truck movement points**. | **PARTIAL — the spatial core only.** `CampaignVictory.check()` tests `all(self._occupier(s, ax) == AXIS for ax in self.objective)` over the 7 Delta hexes (2 Alexandria + 5 Cairo — correct, `data/victory_cities.json:16-17`). **MISSING: (a) the "one full Game-Turn" persistence** — it fires the instant the last hex is occupied; **(b) the ≤90-truck-MP trace** — `_supplied()` uses `supply.plan_draw`, which is the **rule-32.16 `cpa/2` land trace**, not a truck-MP trace, and **never checks that the dump is fed from Tobruk or Tripoli at all**. | `game/campaign_victory.py:80-88` (check), `:60-78` (`_occupier`/`_supplied`); `game/supply.py:207-239,492-505` (the `cpa/2` trace) | **YES** |
| **64.72** | **From the 1st OpStage of Game-Turn 35**: if there are **no Axis combat units** that can trace ≤**60** truck MP to a Supply Dump and thence to **Tobruk or Tripoli**, the **Commonwealth wins automatically**. (Excludes air and coastal shipping units.) | **MISSING ENTIRELY.** No GT35 gate, no 60-MP trace, no Commonwealth auto-win anywhere. `check()` offers only an *annihilation* fallback (`not s.living(AXIS)` → ALLIED), which is **not in the rulebook** — it is an invention standing where 64.72 should be. | `game/campaign_victory.py:80-88`; `grep -rn "64.72\|GT35\|turn.*35" game/campaign_victory.py` → only the deferred-list docstring at `:18` | **YES** |
| **64.73** | Geographic Occupation Points. Occupation = a **combat unit of ≥1 TOE** in the hex which, **at the end of the game**, has **Stores and Water for one Week** and **Fuel and Ammunition to fire its weapons three times and move 20 CP**. Ten cities, Axis/CW VP table. | **PARTIAL — and the quality-test is WRONG.** ✔ The city table is **exact** (all 10 rows, both columns, `data/victory_cities.json:4-13` matched line by line against `docs/rules/64:68-79`). ✔ Combat unit + ≥1 TOE enforced. ✘ **The quality-test checks the wrong things at the wrong magnitude**: `_supplied()` tests Fuel at `fuel_rate(u)` (**one turn's rate**, not 20 CP of movement) and Ammunition at `ammo_cost(u, phasing=True)` (**ONE fire, not three**), and **does not check Stores or Water at all** — though the rule names them first. So a unit with a single round and no food or water still banks the city. | `game/campaign_victory.py:60-78`, esp. `:77-78`; `data/victory_cities.json`; `game/supply.py:117-201` | **YES** |
| **64.74** | Each player gets **1 VP per UNUSED Replacement Point** allotted on his Production Charts — **excluding planes and Trucks**, and **excluding Infantry for the Commonwealth only**. | **MISSING — and it is a landmine. DO NOT IMPLEMENT IT ALONE.** Pools transcribed and confirmed: **Axis 2,493 vs Commonwealth 958**. There is **no replacement economy of any kind** in the engine — the string `replacement` occurs **once** in all of `game/*.py`, in the deferred-list docstring. Nothing spends RPs; nothing even *restores lost TOE* (`Unit.strength` is a one-way ratchet: the only mutation is `_apply_step_loss`). So 64.74 alone scores **every** RP as unused → **Axis 2,493 – CW 958 = 2.60:1 = a Smashing Victory decided at GT0**, invariant to play. Even with the Commonwealth holding **all ten cities** it is 2,493 – 1,328 = 1.88:1, an Axis **Decisive** win *while losing every hex on the map*. | `game/campaign_victory.py:20` (the only `replacement` in game/); `game/state.py:95`, `game/apply.py:241` (one-way ratchet); pools from `docs/rules/90:5512-5535` (German 783), `:5543-5578` (Italian 1,710), `:3433-3456` (CW 958) | **YES — but blocked on 20.6/20.7** |
| **64.75** | **Commonwealth only**: Withdrawal Points. ½ pt per week per **combat battalion (not company) or battalion-equivalent** of infantry/armour/artillery/AT (**not AA**) at **≥75% TOE** voluntarily withdrawn, **max 3 pts/unit**; the unit must **start the Stage in Alexandria or Cairo**. **−2 pts** if it is returned, and it may not be re-withdrawn for **six months**. | **MISSING ENTIRELY.** `grep -rn "withdraw" game/*.py` → **one hit**, the deferred-list docstring. Neither 64.75 nor the rule-20.9 *voluntary withdrawal* mechanism it scores, nor rule **20.8 mandatory withdrawals** (which the Reinforcement Schedule lists), exists. | `game/campaign_victory.py:20`; `docs/rules/20:130` (20.8), `:144` (20.9) | **YES** (it is the CW's only non-geographic VP source, and the counterweight to 64.74) |
| **64.76** | Victory levels: compare the totals as a **ratio of most to least**. Even = Draw; better than 1:1 up to 1½:1 = Marginal; better than 1½:1 up to 2½:1 = Decisive; beyond 2½:1 = Smashing. | **DONE — clean, and it matches the book exactly.** Exact equality → Draw; `ratio <= 1.5` → Marginal; `<= 2.5` → Decisive; else Smashing; a shutout (`least == 0`) → `inf` → Smashing. | `game/campaign_victory.py:102-118` | YES (and it is correct) |

### 64.7 scorecard: **1 of 6 done** (64.76), 2 partial (64.71, 64.73), 3 missing (64.72, 64.74, 64.75).
The engine's own docstring (`campaign_victory.py:1-21`) claims it implements "the 64.71 spatial core,
64.73 and 64.76" and lists the rest as deferred. That is honest as far as it goes — **but it does not
say that 64.73's quality-test is implemented at the wrong magnitude**, and that is a live bug, not a
deferral.

---

## 2. THE SET-UP CHARTS — every dump, every truck park, every port

Rule 64.3 sends the full campaign to **§60.0** for all initial placement. This is the complete diff of
§60's charts against `game/scenario.py` + `game/oob.py`, as the state actually builds.

### 2.1 [60.34] Axis Initial Supply Status — the dump chart

| Chart row | Ammo | Fuel | Stores | Water | Seeded? | Evidence |
|---|---|---|---|---|---|---|
| Tobruk (C4807) | 200 | 2000 | 500 | – | **YES, exact** | `scenario.py:646` `AX-Stage-Tobruk` |
| Bardia (C4321) | 100 | 1000 | 200 | – | **YES, exact** | `scenario.py:647` `AX-Stage-Bardia` |
| Benghazi | 100 | 250 | 100 | – | **YES, exact** | `scenario.py:628-629` `AX-Benghazi` |
| Derna (B5925) | – | 250 | 50 | – | **YES, exact** | `scenario.py:650` `AX-Stage-Derna` |
| **Tripoli (box)** | **250** | **5000** | **250** | – | **NO** | off-map; `victory_cities.json:21` `tripoli: null`. Defensible — but see §2.4 |
| **Dump 1\*** | **1000** | **1500** | **1500** | **200** | **NO — substituted** | replaced by the 61.44 pool, see below |
| **Dump 2\*** | **1000** | **1500** | **1000** | **200** | **NO — substituted** | ditto |
| **C0716** (Saharan) | **100** | **50** | **50** | – | **NO** | not found: grepped `C0716`, `0716` in `game/`, `data/` → 0 hits |
| **2 dummy dumps** | – | – | – | – | **NO** | `SupplyUnit.is_dummy` exists (`state.py:161`) but **is never set True anywhere** |
| **Airfield allotment** | **1200** | **850** | **100** | **100** | **NO** | correctly dropped per 59.61 (air abstracted) |

**THE SUBSTITUTION BUG.** Dump 1 + Dump 2 (charted **2,000 A / 3,000 F / 2,500 S / 400 W**) are not
seeded. In their place `game/oob.py` mints five `AX-Dump` counters carrying the **61.44** (Desert Fox)
pool: **2,500 A / 9,600 F / 950 S / 1,100 W**. Measured from the built state (5 × 500/1920/190/220).
That is **3.2× the charted desert-dump Fuel** — +6,600 Fuel Points the Axis should not have, in a
scenario whose supply chapter is §60, not §61.

### 2.2 [60.44] Commonwealth Initial Supply Status

| Chart row | Ammo | Fuel | Stores | Seeded? | Evidence |
|---|---|---|---|---|---|
| Mersa Matruh (D3714) | 1000 | 3000 | 4000 | **YES, exact** (new) | `scenario.py:702` `AL-Stage-Matruh` |
| Sidi Barrani (C4131) | 250 | 500 | 100 | **YES, exact** (new) | `scenario.py:703` `AL-Stage-Barrani` |
| **Dump I** | **500** | **750** | **500** | **NO — substituted** | replaced by the 61.36 pool |
| **1 dummy dump** | – | – | – | **NO** | `is_dummy` never set |
| **Air Supply** | **200** | **250** | **50** | **NO** | correctly dropped per 59.61 |
| Unlimited supply in Cairo/Alexandria (rule 57) | ∞ | ∞ | ∞ | **YES** | `scenario.py:611-619` `_campaign_cw_base`, `base=True` on `MAJOR_CITY` |

Same substitution: Dump I (charted **500/750/500**) is replaced by five `AL-Dump` counters carrying the
**61.36** pool = **1,700 A / 2,550 F / 1,600 S / 1,600 W** — **3.4× the charted amount**, plus 1,600
Water the chart does not grant at all (`oob.py:224` layers a flagged `_CW_WATER_PROXY`).

### 2.3 [60.33] / [60.43] The 2nd/3rd-line truck parks — **now correct, with one over-seed**

| Chart | Row | Restriction | Seeded to | Verdict |
|---|---|---|---|---|
| 60.33 | 25 L / 140 M / 40 H | **Tripoli** | **NOT SEEDED** | correct-ish: Tripoli is off-map. **But this is 205 of the Italian park's 420 Truck Points — nearly half — silently absent.** Flagged in `scenario.py:879-888`. |
| 60.33 | 30 L / 100 M / 25 H | Anywhere in Libya | Benghazi | **OK** (our assignment of a free placement) |
| 60.33 | 10 L / 50 M | Any Air Facility | Benghazi | **OVER-SEEDED** — 59.61 says *ignore* air-facility trucks when the Air Game is abstracted |
| 60.43 | 40 M / 10 H | Any hex in Cairo | Cairo | **OK** |
| 60.43 | 10 L / 20 M | Alexandria | Alexandria | **OK** |
| 60.43 | 15 L / 40 M / 5 H | Anywhere, maps | Mersa Matruh railhead | **OK** |
| 60.43 | 5 L / 30 M / 20 H | Any Air Facility | Mersa Matruh railhead | **OVER-SEEDED** — same 59.61 problem |

Built state totals: **Axis 215 TP, Commonwealth 195 TP.** Both charts are otherwise transcribed
faithfully (`scenario.py:809-819`). The 59.61 inconsistency is small (Axis +60 TP, CW +55 TP) but it is
the *same rule* the engine obeys for the supply allotments and disobeys for the truck rows.

### 2.4 [60.31] / [60.41] FIRST-LINE TRUCKS — **entirely missing, and bigger than the parks above**

Both deployment charts allot first-line trucks **per hex, to every starting formation** (59.42: "These
trucks must be assigned to units in their listed hex"). Totalled from the rulebook:

| Side | Light | Medium | Heavy | **Total TP** | Motorization Points (59.63A = M+H) |
|---|---|---|---|---|---|
| **Italian (60.31)** | 55 | 260 | 45 | **360** | **305** |
| **Commonwealth (60.41)** | 30 | 125 | 22 | **177** | **147** |

**Seeded: zero.** `is_first_line_truck` is never set True in any file; every `TruckFormation` the
campaign builds is hardcoded `line=3` (`scenario.py:829`). With them go:

* **59.63A** attached Motorization Points (the thing that makes Motorized Infantry actually motorized —
  rule 3.4: "Motorized Infantry units must actually have Trucks in order to use their Motorized CPA");
* **59.66B** — each attached MP not carrying men/guns may **start loaded with 1 Ammo or 3 Fuel Point**.
  That is up to **305 Ammo / 915 Fuel** (Axis) and **147 Ammo / 441 Fuel** (CW) of start-line supply
  *sitting with the troops at the front*, which the dump charts do not include.

**Total charted transport vs seeded**: Axis 780 TP charted (360 first-line + 420 park) → **215 seeded
(28%)**. Commonwealth 372 TP charted (177 + 195) → **195 seeded (52%)**.

### 2.5 [60.7] / [55.3] Construction and ports at the start

| Chart / rule | Says | Status | Evidence |
|---|---|---|---|
| 60.7 | RR runs to Mersa Matruh (D3714) and ends there | **DONE** | `scenario.py:677` `_CW_RAILHEAD="D3714"`; 66 rail edges built |
| 60.7 | No minefields | **DONE** (vacuously — 0 minefields, and `construction.py:44-47` says 24.3 minefields are "DELIBERATELY NOT BUILT", so none can ever be created either) | built state: `minefields: 0` |
| 60.7 | No fortifications | **DONE, defensibly** — the 9 forts in the built state are the **25.12 intrinsic city** fortifications (7 × Level 3 Delta, 2 × Level 2), not constructed works | `scenario.py:59-70,600,1216-1218`; built state `Counter({3: 7, 2: 2})` |
| 60.7 | No pipeline other than the RR's | **DONE** | `scenario.py:1245` `wells.pipeline(tmap.terrain)` laid on the rail corridor only |
| 60.7 / 55.3 / 55.25 | **All ports at listed Efficiency, except Tobruk (San Giorgio blocks the harbour). 55.12: Tobruk's Efficiency Level is 5. 55.25: the San Giorgio reduces it by THREE levels → it starts at 2.** 55.3 lists Benghazi **3**, Mersa Matruh **1**. | **WRONG — all three ports** | see table below |

**The port-efficiency error, quantified.** `data/logistics_rates.json` already carries the correct 55.3
levels; `_campaign_ports()` reads only the `tons` key and hardcodes the rest.

| Port | Charted (55.3 / 55.25) | Seeded (`scenario.py`) | Effect |
|---|---|---|---|
| **Tobruk** | max 5, **starts at 2** (−3 San Giorgio) | `max_eff=5, eff=5` (`:1003-1004`) | lands **425 Ammo/OpStage instead of 170** — **2.5× oversupply** from GT1. And the besieger must bomb off **5** levels instead of **2** to shut it. |
| **Benghazi** | **3** | `max_eff=10, eff=10` (`:996`) | one level of bomb damage costs **1/10** of capacity instead of **1/3** → the Axis port of arrival is **3.3× harder to shut**. |
| **Mersa Matruh** | **1** | `max_eff=10, eff=10` (`:1001`) | charted, **one hit closes it**. Seeded, it takes **ten**. |

The 55.3 footnote is explicit: *"A loss of one level of efficiency decreases the port's capacity by a
fraction equal to one over the listed efficiency level."* The Efficiency Level is not a capacity — it is
the **damage denominator**. Setting it to 10 makes every harbour on the map near-immune to the air war
the engine seeds specifically to shut harbours (`_campaign_air`, whose own docstring says "Only
efficiency 0 — a bombed-shut harbour — actually cuts a sea lane").

`game/state.py:321-323` claims *"Tobruk seeds eff=2/max_eff=5"*. **No scenario does.** `campaign()`
seeds 5/5 and `siege_of_tobruk` seeds 7/7 (`scenario.py:380`).

### 2.6 Other §60 set-up rows

| Rule | Says | Status | Evidence |
|---|---|---|---|
| 60.32 / 60.42 / 60.46 | Initial air strengths by plane type, refits, pilots, SGSU counts; Malta's planes/AA/facility capacity | **MISSING** — `AirWing` is a hexless 2-scalar abstraction (fighters/strike) with **proxy magnitudes**, admitted at `state.py:261` and `scenario.py:1006-1014`. No plane types, no pilots, no SGSUs, no air facilities. | `scenario.py:1015-1032`; `oob.py:109` *skips* every airfield/SGSU counter |
| 60.35 | Axis coastal shipping counters, all in Tripoli | **MISSING** | not found: grepped `coastal ship`, `Coastal Shipping` in `game/` → 0 |
| 60.36 | Axis Malta strategic attacks limited to **Availability Level I** | **MISSING** (and superseded for us by 64.52) | no Malta availability system — see 64.52 |
| 60.37 | Italian must pre-plan convoys for Sept 1940; **may only use lanes 2, 3 and 6** | **PARTIAL/WRONG** — the Benghazi convoy is labelled lane `"2"` (`scenario.py:967`), which by the 56.18 chart is *Sicily→Tripoli*, not Benghazi (that is lane 3 or 4). `scenario.py:1094-1098` **admits the mislabel** and leaves it. No convoy *planning* exists. | `scenario.py:967,1094-1098` |
| 60.45 | CW Fleet: 2 BB, 2 CA, 4 AA-CA, 6 DD at Alexandria + 1 CA, 1 AA-CA, 2 DD at Malta; may not move until GT2 | **MISSING** — `naval=()` in every scenario | `grep -rn "naval=" game/scenario.py` → 0 hits |
| 60.47 | CW takes reinforcements off the track; **some units need Training**, so other units must be assigned as Training Units. No RPs before Nov 1940. | **MISSING** — no training system (rule 20.4), no RP arrival gate | not found: grepped `training`, `trained`, `Training` in `game/*.py` → 0 functional hits |
| 60.5 | The air-facility list (20 airfields, 30 landing strips, 2 flying-boat basins) | **N/A** — air is abstracted (59.61); no air facilities modelled | `oob.py:107-110` |
| 60.6 | **Italian has the Initiative for the entire first Game-Turn**; roll from GT2 | **MISSING in the campaign** (imported by 64.4) | `campaign()` sets no initiative fields |
| 60.8 | Scenario Group One victory conditions | **N/A** — the campaign uses 64.7 | `campaign_victory.py` |
| 60.9 | Air/Logistics abstractions for Group One | **DONE by 60.91** ("Air Abstracted: None") — but see the 59.61 truck over-seed in §2.3 | `scenario.py` |

---

## 3. CHAPTERS 01-04 — introduction, how to play, glossary, game equipment

Chapters 1, 2 and 4 are overwhelmingly **physical-component and procedural** text (how to lay the maps
out, what a Log Sheet looks like, how many dice are in the box). They contain almost no simulable rule.
The exceptions are **4.44-4.49**, which define the charts that *are* the engine's data, and **3.2-3.5**,
which define the unit taxonomy the engine either models or does not.

| Rule | What it says (one line) | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 1.0 | Simulation of Libya/Egypt 1940-43; hex ≈ 8 km; Game-Turn = 1 week; units company→division. | **DONE** | `calendar.py:19` (`GT_PER_MONTH=4` ≈ 1 week/GT); `cna_map.py`, `coords.py` (hex grid A-E) | YES (frame) |
| 2.1 | How the rules are organised; Land = 6-32, Air = 33-47, Logistics = 48-58, Scenarios = 59-65. | **N/A** — reader's guide | `docs/rules/02:22` | NO |
| 2.2 | How the game is set up: TOE Log Sheets, one per counter, tracked on paper. | **N/A** — the engine *is* the log sheet (`state.Unit`) | `game/state.py:32-96` | NO |
| 2.3 | How to run a game: 4-5 players/side; C-in-C, Logistics, Rear Area, Air, Front-Line commanders. | **N/A** — designer's note. Realised (not required) by the 5-seat AI staff. | `game/staff.py`, `game/staff_policy.py` | NO |
| 2.4 | Playing time ≥1200 hours; ~10 hrs/Game-Turn. | **N/A** — prose | `docs/rules/02:60` | NO |
| 3.1 | Glossary of ~30 terms (Actual Combat Value, Assault, Breakdown, Cohesion, CP, ZOC…). | **PARTIAL** — most are modelled. **Not modelled: Battle Group** (a bde-eq HQ that may attach anything — and 61.41 explicitly invites the Axis to use them), **Shell Unit** (a unit below minimum TOE), **Desert Raider** (rule 27 — only a fuel-analog comment survives). | grepped `battle_group\|BattleGroup` → 0; `shell_unit\|is_shell` → 0; `raider` → only `engine.py:310` (a Rommel fuel comment) | MAYBE |
| 3.21 | 12 unit categories, incl. **Tank Recovery Squadrons**, **Dummy Tank Formations**, SGSUs, Trucks. | **PARTIAL** — Dummy Tank Formations: **MISSING** (grepped `dummy_tank\|DummyTank` → 0). Tank Recovery Squadrons: **MISSING** as a unit type (the `recovery` hits in `engine.py`/`apply.py` are rule-22 *breakdown* repair, not the squadron). SGSUs: **skipped at load** (`oob.py:109`). | `game/oob.py:105-148` (the role taxonomy: hq, oasis, infantry, motor_infantry, mg, tank, recon, artillery, antitank, rr_engineer, road_engineer — **no AA, no recovery, no dummy**) | MAYBE |
| 3.22 | Barrage/air targets grouped into Infantry-, Armor-, Gun- and Truck-class. | **PARTIAL** — `combat_tables.py` distinguishes armour/infantry/gun for CA and anti-armor; the **Truck-class** target does not exist. | `game/combat_tables.py`; `game/state.py:64` (`is_tank`) | MAYBE |
| 3.23 | Combat units = Inf, Tank, Recce, Arty, AT **and AA** types. | **WRONG** — **there is no Anti-Aircraft role in the engine.** `oob.py:118` maps `(AA)` counters to `"antitank"`, and CW `15 LAA`/`57 LAA`/`9 HAA` fall through to plain **infantry** (verified in the built state: barrage 0, anti_armor 0, 6 steps). `is_pure_aa` exists (`state.py:67`) but is never set from the OOB. | `game/oob.py:118,138-148`; built state | **YES** (see §4) |
| 3.3 / 3.31-3.36 | HQ units: represent attached units; CPA of the slowest; 5 stacking points at full division; Italian regimental HQs carry guns; armoured HQs carry a tank platoon; a valueless HQ is captured instantly by a ZOC. | **PARTIAL** — an `hq` role exists (`unit_stats.json`), and `is_combat=False` models the bare HQ. **3.32** (parent CPA = slowest), **3.33** (stacking scales with strength), **3.35** (HQ tank platoons) and **3.36** (instant HQ capture) are not implemented. The engine has **no assignment/attachment tree at all** — every counter is an independent `Unit`. | `game/state.py:32-96`; grepped `parent\|attach\|assign` in `state.py` → 0 structural fields | MAYBE (it is why 20.11 brigades collapse) |
| 3.4 | Unit-type descriptions. Notably: **Motorized Infantry must actually have Trucks to use its Motorized CPA**; artillery has intrinsic transport; emplaced guns (CPA 0) may never move; garrison units stack free in their home city. | **PARTIAL** — `Mobility` is a **static field** baked in at load (`state.py:37`), so motorized infantry is motorized whether or not it has trucks — and it never has any (§2.4). `is_garrison_home` exists (`state.py:68`). Emplaced/CD guns: **immobility deferred** (`oob.py:118` comment says so). | `game/state.py:37,68`; `game/oob.py:118` | MAYBE |
| 3.5 | Unit characteristics: CPA, Barrage, Vulnerability, Anti-armor, Armor Protection, Off/Def Close Assault, **Anti-aircraft**, Max TOE, Basic Morale, **Fuel Rate**, **Breakdown Adjustment**. | **PARTIAL** — 9 of 11 are real fields on `Unit` (`state.py:38-50`). **Anti-aircraft Rating: no field.** (`anti_armor` is a different thing.) Fuel Rate and Breakdown are modelled per-model. | `game/state.py:32-96`; `data/unit_stats.json` | MAYBE |
| 4.1 | Five map sections A-E, laid west→east; 01xx of a section overlays 39xx of the previous. | **DONE** | `game/cna_map.py:load_sections("ABCDE")`; `game/coords.py` (the decoded VASSAL stitch) | YES |
| 4.2 / 4.21-4.23 | Counters; sample units; unit-type symbols; the Counter Manifest. | **N/A** — physical components | `docs/rules/04:14-128` | NO |
| **4.44 / 4.45** | **The three Organization-at-Arrival (OA) Charts** — Allied, German, Italian: name, counter abbr, **ID Code**, **TOE & weapons systems**, **arrival Stage/Game-Turn**, and the assignment tree (which units belong to which parent). | **PARTIAL — this is the OOB, and it is the project's biggest gap.** See §4. | `docs/rules/90:1919` (CW), `:3817` (Italian), `:4754` (German); `data/oob_italian.json`, `data/reinforcements_campaign.json` | **YES** |
| **4.43a / 4.43b** | **The Reinforcement Schedules** (CW incl. **Withdrawals**; Axis). | **PARTIAL** — 179 arrival records exist; **274 of 365 CW counters and all 32 CW Withdrawal events are missing**. See §4. | `docs/rules/90:1781`, `:3683`; `data/reinforcements_campaign.json` | **YES** |
| **4.46** | **Unit Characteristics Charts** — each ID Code's max TOE and its ratings; a unit may comprise several weapons systems and fires each at its own rating. | **PARTIAL** — `data/unit_stats.json` holds 9-11 roles per nationality plus 24 `models`. **A unit is a flat list of `StepRecord`s with ONE model**; the "several weapons systems, each firing at its own rating" structure is not modelled. | `data/unit_stats.json`; `game/state.py:24-29,95` | **YES** |
| **4.47 / 4.48 / 4.49** | **Commonwealth / Italian / German Tank & Gun Characteristics Charts** — the per-model stat block. | **PARTIAL — 22 of 32 Commonwealth models are missing** (incl. **Sherman, Valentine, Crusader I & III, Churchill, A10, Scorpion, Priest, Bishop, Deacon, 17-pdr, 6" How, 60-pdr, and BOTH AA models**). See §4.4. | `docs/rules/90:3264-3303` [4.47]; `data/unit_stats.json` `models` (24 entries) | **YES** |
| 4.5 / 4.51-4.55 | Log Sheets (Field Commander, TOE, Vehicle Repair, Naval Convoy, POW, SGSU, Air Mission, Trucks, Supply Dumps, Supply Requisition). | **N/A** — paper play-aids; the engine's `GameState` is their union | `game/state.py` | NO |
| 4.6 | Inventory of game parts (maps, 1800 counters, dice, booklets). | **N/A** — physical | `docs/rules/04:236` | NO |

---

## 4. CHAPTER 59 — INTRODUCTION TO SCENARIOS

| Rule | What it says (one line) | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 59.11 | Five scenario groups; the fifth is the campaign. | **N/A** — organisational | `docs/rules/59:18` | NO |
| 59.12 | Each of the first four groups lists: length, victory, land/air placement, supplies, trucks, Malta/Crete forces, abstractions, special rules. | **N/A** — organisational | `docs/rules/59:20-36` | NO |
| 59.2 | How to read the set-ups (Hex; Unit Type; Parent; Less/Assg/Det/Att/Consists-of; abbreviations). | **N/A** — notation. **But it is the notation the OOB transcription must parse**, and the `Less/Assg/Det/Att` parent-tree it describes is exactly what the engine does not model (see 3.3). | `docs/rules/59:38-70` | NO (MAYBE as a transcription spec) |
| 59.31 | Each scenario lists Axis/Allied plane types, numbers, pilots, air facilities, SGSUs. | **MISSING** — `AirWing` is 2 scalars, flagged as a proxy | `game/state.py:261`; `game/scenario.py:1006-1032` | MAYBE (air is abstracted by choice) |
| 59.32 | Planes listed by type with ready/total; all start fuelled and armed at no cost. | **MISSING** | as above | NO |
| 59.33 | Planes distributed among SGSUs per 35.2. | **MISSING** — no SGSU | `game/oob.py:109` (SGSU counters skipped) | NO |
| 59.34 | Pilots assigned as the player desires. | **MISSING** — no pilots | grepped `pilot` in `game/` → 0 | NO |
| 59.35 | SGSUs placed on air facilities within readying capability. | **MISSING** | as above | NO |
| 59.36 | No maintenance in the first OpStage of a scenario. | **MISSING** | as above | NO |
| 59.41 | Trucks divided into **1st line**, 2nd-3rd line for supplies, 2nd-3rd line for air facilities. | **PARTIAL** — only 2nd/3rd-line exists; `TruckFormation.line` is "a legible 2\|3 label only" (`state.py:344-346`). **No 1st line at all.** | `game/state.py:340-355`; `game/scenario.py:829` (`line=3` hardcoded) | **YES** |
| **59.42** | **1st-line trucks are listed by hex in the land deployment and must be assigned to units in that hex.** | **MISSING ENTIRELY** — ~360 Axis + ~177 CW Truck Points unseeded. See §2.4. | `is_first_line_truck` never set True anywhere | **YES** |
| 59.43 | 2nd/3rd-line air-facility trucks must be placed on an air facility. | **N/A under 59.61** (air abstracted → ignore them) — **but the engine seeds them anyway.** See §2.3. | `game/scenario.py:812,818,851-854` | **YES** (inconsistency) |
| 59.44 | 2nd/3rd-line supply trucks placed on a hex with a friendly combat unit, a dump, or a major city/town/oasis. | **DONE** — all parks sit on Benghazi / Cairo / Alexandria / the Matruh railhead | `game/scenario.py:833-893` | YES |
| 59.45 | Trucks may start transporting supplies or motorizing troops at no cost; any type of supply. | **PARTIAL** — `TruckFormation` has cargo pools (`state.py:347`) but the campaign seeds every park **empty**. | built state: all `AX-Truck-*`/`AL-Truck-*` carry 0 | MAYBE |
| 59.51 | Each scenario lists location and amount of initial supplies. | **PARTIAL** — see §2.1/§2.2 | | YES |
| 59.52 | Supplies split between air facilities and supply dumps; an air facility automatically has a dump. | **N/A under 59.61** | | NO |
| **59.53** | Certain scenarios list **non-active (dummy) dumps**; dummies may not share a hex with an air facility. | **MISSING** — `SupplyUnit.is_dummy` exists (`state.py:161`) and is **never set True**. 60.34 grants the Axis **2 dummies**, 60.44 the CW **1**. | `grep -rn "is_dummy" game/` → 2 hits, both *reads* | MAYBE (dummies only bite under limited intelligence) |
| 59.54 | Axis coastal shipping starts empty. | **N/A** — no coastal shipping modelled | grepped → 0 | NO |
| 59.61 | **If only the Air Game is abstracted: ignore all Trucks and supplies at/for Air facilities.** Play by §58.0. | **PARTIAL / SELF-INCONSISTENT** — the engine *is* at this abstraction level (Land + Logistics + abstract air), and it correctly drops the air-facility **supply** allotments (60.34's 1200/850/100/100 and 60.44's 200/250/50). It then **seeds the air-facility TRUCK rows anyway** (Axis +60 TP, CW +55 TP). | `docs/rules/59:110`; `game/scenario.py:851-854,876-877` | **YES** |
| 59.62 | If the **Logistics** Game is abstracted, use Motorization Points and Supply Units. | **N/A** — we play the **full** Logistics Game (real trucks, dumps, ports, four commodities), so the §32 abstraction does not apply. Correctly so, and `scenario.py:1290-1310` says why (`motorized_supply=False`). | `game/scenario.py:1290-1310` | NO |
| 59.63 A/B | Initial Motorization Points computed from the scenario's trucks: **each Medium and each Heavy Truck = 1 MP**; attached MPs from 1st-line, unattached from 2nd/3rd-line. | **N/A for the unattached half** (we run real trucks, not MPs). **MISSING for the attached half** — there are no 1st-line trucks to compute from. | `game/supply.py:310` (`MOTORIZATION_POINTS=30`, the *32.32* rule, a different thing) | MAYBE |
| 59.64 | Initial MP distributions may be freely altered once play starts. | **N/A** | | NO |
| 59.65 | Supply Units: number, location, contents; initial placement may exceed stacking if unavoidable. | **PARTIAL** — dumps are seeded but from the wrong chart (§2.1/2.2) | | YES |
| 59.66 A | MPs may begin loaded with supplies, over and above the dump chart. | **MISSING** | | MAYBE |
| **59.66 B** | **Each attached MP not carrying men/guns may start loaded with 1 Ammo Point or 3 Fuel Points**, which must be consumed first. | **MISSING** — up to **305 Ammo / 915 Fuel** (Axis) and **147 / 441** (CW) of front-line start-line supply. | no 1st-line trucks exist | **YES** |
| 59.66 C | Unattached MPs may begin carrying supply units (1 per 30 MP; 1 depot per 50 air-facility MP). | **N/A / MISSING** — parks seed empty | built state | MAYBE |

---

## 5. THE ORDER OF BATTLE AND THE REINFORCEMENT SCHEDULE

> *This is the single biggest fidelity gap in the project, and it is the reason our Eighth Army can
> never fight Alamein.*

### 5.1 The measured force ratio — confirmed, and it is worse than 1.7:1 where it matters

Measured off the built state (`game.scenario.campaign(seed=1941)`, all `is_combat` units, TOE =
Σ`StepRecord.strength`):

| Game-Turn | Axis units / TOE | Commonwealth units / TOE | **Axis : CW** | Historical reality |
|---|---|---|---|---|
| GT1 (Sep 1940) | 96 / **588** | 29 / **181** | **3.25 : 1** | ≈4:1 Italian — *roughly right* |
| GT26 (Rommel) | 137 / 856 | 45 / 283 | 3.02 : 1 | |
| GT57 (Crusader) | ~154 / ~980 | ~74 / ~472 | ~2.08 : 1 | Crusader was a CW *superiority* offensive |
| **GT90-100 (El Alamein)** | 160-177 / **1020-1131** | 96-104 / **611-658** | **1.67-1.72 : 1** | **≈2:1 the OTHER WAY** (Eighth Army ~195k men / 1,029 tanks vs Panzerarmee ~116k / 547) |
| GT111 (end) | 177 / 1131 | 104 / 658 | **1.72 : 1** | |

**The engine is off by a factor of ~3 at Alamein.** The GT1 ratio is approximately correct — Graziani
really did outnumber O'Connor. **The Commonwealth simply never builds up.** It arrives at the decisive
battle of the campaign with 58% of the Axis's TOE, when it should have ~190%.

### 5.2 The Commonwealth OOB: loaded at **32%** of its own chart

| | engine | rulebook [4.43a]/[4.44B] | engine / chart |
|---|---|---|---|
| GT1 counters | 28 | **66** | 42% |
| GT1 TOE | 175 | **328** | 53% |
| GT1 tank TOE | 40 — **all phantom** (see 5.3) | 37 | **0% real** |
| GT1 gun TOE | 18 | **77** | 23% |
| **Cumulative counters** | **119** | **431** | **28%** |
| **Cumulative TOE** | **673** | **2,121** | **32%** |
| Cumulative tank TOE | 144 | 307 | 47% |
| Cumulative gun TOE | 118 | **692** | **17%** |

**Build the Commonwealth to its own chart, leave the Axis untouched, and the ratio inverts to 0.54:1 —
Commonwealth 1.9:1.** Which is the historical Alamein, and Eve's stated balance target.

### 5.3 🔴 THE CLASSIFICATION BUG — the Commonwealth's armour is entirely fake

`game/oob.py:145-146`:

```python
if "Armoured" in g or "Tank" in g:
    return "tank"
```

A **substring match on the formation-group name**. `"BR Unassigned Anti-Tank Regiments"` contains
"Tank". `"BR 7th Armoured Division"` contains "Armoured" — and the 7th Armoured's *support group*
(`7Spt/7`) carries its anti-tank and artillery regiments. **Verified by building the state**; every
`is_tank=True` Commonwealth unit at GT1:

| unit | what it actually is (60.41 / [4.44B]) | engine role |
|---|---|---|
| `BR-65` | **65th Anti-Tank Regiment** (6 × 2-pdr) | **tank**, 8 steps, `is_tank` |
| `BR-149` | **149th Anti-Tank Regiment** (8 × 2-pdr) | **tank** |
| `BR-3-RHA---7Spt-7` | **3rd RHA — anti-tank** (60.41: *"3rd RHA (AT; 7Spt/7)"*) | **tank** |
| `BR-4-RHA---7Spt-7` | **4th RHA — field artillery** | **tank**, and **barrage = 0** |
| `BR-1-KRRC---7Spt-7` | **1st King's Royal Rifle Corps — motor infantry** | **tank** |

**Not one of the Commonwealth's five "tank" units at GT1 is a tank.** And **1st RTR** (60.41 C3520:
*"1st RTR (7/7)"*, 7 × A9 Cruiser) — the *only* real tank battalion in the September-1940 Western
Desert Force — **is absent from the data entirely**. The Commonwealth's 40 "tank TOE" is 100% phantom.

The same bug destroys two other arms:
* **Artillery** — `oob.py:144` `if "Indian" in g … return "motor_infantry"` fires before the tank rule,
  so `IN-31-Fld` (**31st Field Artillery Regiment**, 4th Indian Div) loads as **motor infantry with
  barrage 0**.
* **Anti-aircraft** — **there is no AA role in the taxonomy at all** (rule 3.23 lists AA as a combat
  type). `oob.py:118` maps Italian `(AA)` counters to `"antitank"`; Commonwealth `BR-15-LAA`,
  `BR-57-LAA`, `BR-9-HAA` fall through the whole chain to the `return "infantry"` default and load as
  **plain 6-step infantry** (verified: barrage 0, anti_armor 0). `Unit.is_pure_aa` exists
  (`state.py:67`) and is **never set from the OOB**. **All 27 unassigned CW AA regiments + 6 divisional
  LAA regiments are missing from the reinforcement schedule outright.**

This bug is **actively arming the Commonwealth with five fake tank battalions while its real armour is
missing** — which flatters the CW tank count in any audit that trusts `is_tank`, and simultaneously
deletes its anti-tank screen, its divisional artillery and its entire AA arm.

### 5.4 Missing formations and arrivals (Commonwealth)

**Initial deployment (60.41): 43 of 66 counters missing (200 TOE).** Absent wholesale:
* the **entire 7th Armoured Division armour** — 7 Armd Div HQ, 4 Armd Bde HQ, 7 Armd Bde HQ, 6 RTR
  (10 × Mk VI), 7 Hus (10 × Mk VI), **1 RTR (7 × A9)**, 8 Hus (7 × A10), 7 Spt HQ, 2 Rifle Bde, 11 Hus
  — `docs/rules/90:2006-2019`;
* the **entire 6th Australian Division** (10 counters) — `90:2457-2470`;
* the **entire 2nd New Zealand Division** (8 counters) — `90:2749-2766`;
* **10 of 12** 4th Indian Division counters — `90:2555-2571`;
* 16 Inf Bde HQ, 1st Buffs, 1st Hampshire, 1st South Staffordshires, 1st Coy French Motor Marines.

**Wrongly placed (9)**: the 16th Infantry Brigade's battalions sit at D3106/D3206/D3307 — **64 hexes
from Cairo (E1829)**, where 60.41:171 puts them. They are seeded *on the front line* instead of in the
rear. 1 Essex / 1 DurLt at D2807/D2908 instead of the Matruh Garrison (D3714). The four "Cairo" units
sit at E4115/E4116 — 26 hexes from Cairo.

**Wrongly present (4)**: `1 B&H`, `1 Y&L`, `2 BlkWa` (14 Inf Bde — arrives 1/35) and `4 Bord` (arrives
3/51) are on the map at GT1.

**Reinforcement schedule [4.43a]: 274 of 365 counters missing (1,295 TOE).**

| year | chart counters / TOE | data counters / TOE | gap |
|---|---|---|---|
| 1940 | 62 / 314 | 16 / 85 | −46 |
| 1941 | 169 / 802 | 45 / 252 | −124 |
| 1942 | 134 / 677 | 30 / 161 | −104 |
| **total** | **365 / 1,793** | **91 / 498** | **−274 / −1,295** |

**29 Game-Turns deliver rulebook units and nothing at all in the data**: GT 4, 11, 12, 16, 19, 27, 31,
33, 40, 42, 44, 47, 48, 50, 52, 53, 55, 56, 58, 60, 65, 66, 70, 83, 85, 86, 89, 94, 98.

Absent formations include the **1st Armoured Division** (only its Support Group is present — the whole
2nd Armd Bde, 30 tank TOE, is gone), the **2nd Armoured Division** (only 1 RHA — 4 Hus / 3 RTR / 5 RTR,
25 tank TOE, gone), the **22nd Armoured Brigade** (30 tank TOE), **all 33 AA regiments**, most
unassigned AT and artillery regiments, Layforce, the SAS, the Royals, 3rd Hussars.

**8 arrival-turn mismatches**, the worst: `13 NZ RR Constr` at GT6 vs the chart's 3/50 (**−44 turns**);
`1 SA Road Constr` GT6 vs 1/50 (**−44**); `10 NZ RR Constr` GT6 vs 1/32 (**−26**); `32 Army Tank Bde`
GT76 vs 1/51 (**+25**).

**Withdrawals: zero of 32.** [4.43a] mandates **32 WD events** (rule 20.8 mandatory withdrawals). The
data has **none**. Of 14 `Rtn` (return) events, 3 exist. OpStage is discarded entirely — every arrival
is keyed to a Game-Turn only.

### 5.5 🔴 THE BRIGADE-BATTALION COLLAPSE (rule 20.11)

Rule 20.11, verbatim (`docs/rules/20:14`):

> **[20.11]** Reinforcements are new, whole units that arrive as specified by the Reinforcement Track.
> Thus, in the September 3/2, Operations Stage, the Commonwealth Player receives the 6th New Zealand
> Brigade **(and its three battalions)** as well as the 6th NZ Field Artillery Regiment.

**34 of 34** Commonwealth infantry/motor brigades are modelled as a **single 6-step battalion**. Not one
is modelled with three. Each is one JSON record → one `Unit` → one `StepRecord`, `stacking_points=1`,
which `game/oob.py:291` itself annotates `# 1=battalion (rule 9.4)`.

Worst offenders — one counter standing in for a whole formation:

| data counter | stands for | ratio |
|---|---|---|
| `44 Inf Div body` | 12 counters / 53 TOE | **8.8×** |
| `4 In Div core` | 7 counters | 5.3× |
| `23 Armd Bde` / `24 Armd Bde` | 5 counters / 37 TOE each | 4.6× |
| `Polish Bde` | 8 counters | 4.2× |

**44 data counters stand in for 187 rulebook counters; 276 TOE against 865.** Understated **3.1×**.
And rule 20.11's *own worked example* — the 6th NZ Brigade — is one of the units the engine gets wrong.

**Root cause is structural**: the Axis OOB is built at **battalion resolution** (45 units carry explicit
battalion designators — `I/157`, `II/116`, `III/141`), the Commonwealth at **brigade resolution**.
`data/oob_campaign_extra.json` is a 331-line **Axis-only** gap-fill layer; there is **no Commonwealth
gap-fill at all**, and `data/reinforcements_campaign_source.json` is **Axis-only** (176 entries, 0
Allied) — so the Commonwealth schedule has no traceable provenance.

### 5.6 Missing weapon models — 22 of 32 Commonwealth systems

`data/unit_stats.json` `models` carries **24 models total** and only **10 of the 32** on the [4.47]
Commonwealth Tank & Gun Chart (`docs/rules/90:3264-3303`). The 10 that are present are **faithfully
rated**; this is a coverage gap, not a correctness gap.

| class | missing | rulebook line |
|---|---|---|
| **Tanks (7/14)** | **Sherman**, **Valentine Mk.II**, **Crusader Mk.I**, **Crusader Mk.III**, **Churchill II**, **A10 Cruiser**, **Scorpion** | `90:3270-3282` |
| **Artillery (11/12)** | 18-pdr, 18/25-pdr, 4.5" Gun, 5.5" Gun/How, 60-pdr, **Bishop** (SP 25-pdr), 3.7" How, 4.5" How, 6" How, 155mm How, **Priest** (105mm SP How) | `90:3283-3295` |
| **Anti-tank (2/4)** | **17-pounder**, **Deacon** (SP 6-pdr) | `90:3299-3300` |
| **Anti-air (2/2 — BOTH)** | Light AA, Heavy AA | `90:3302-3303` |

Consequences that bite *inside the campaign's own clock*:
* **A10** equips 8 Hussars at **GT1**. **Valentine** is 54 TOE across 23/24 Armd Bde.
* The Production Chart releases **6-pdrs from GT75, Crusader III GT88, Sherman GT89, Churchill GT90,
  17-pdrs GT103** (`docs/rules/90:3438-3457`) — all inside GT1-111.
* `MODEL_DEFAULTS` (`oob.py:270`) forces **every** CW artillery unit to `25pdr`, so 7 Medium (6 × 60-pdr,
  barrage 12) and 8 Medium fire as 25-pdrs (barrage 8).
* **Without the Scorpion the campaign has no mine-clearing capability at all** (`90:1329`: *"Real
  Minefield | Clear | Any E or tank bn with 6+ TOE of Scorpions"*).

### 5.7 Axis OOB gaps

* 🔴 **The Ramcke Brigade does not exist in the engine.** `grep -rni "ramcke" game/ data/ scripts/ tests/`
  → **0 hits**. The rulebook has it in full: OA sheet `docs/rules/90:4908-4923` (*Fallschirmjaeger-Brigade
  Ramcke*, Basic Morale **+2**, **6 counters** — HQ + I/Kroh, II/von der Heydte, III/Hübner, IV/Schweiger,
  V/Burchardt, each `N + 1 × 7.5cm L Gun`, airdroppable); and the Axis Reinforcement Schedule places it at
  **GT86-93** (`90:3784, 3790, 3794, 3797`) — **directly into the Alamein window**.
* Late-war Axis models missing from `unit_stats.json`: **Marder III SP**, **7.62cm Pak(R)**, **Semovente
  75/18**, **90/53** (`90:3374, 3376, 3883-3894, 3339`).
* The Axis *is* built at battalion resolution and is the healthier of the two OOBs — but it is drawing
  its supply from the wrong scenario group (§2.1) and its Tripoli truck park is absent (§2.3).

### 5.8 The Axis OOB: **wrong hexes**, and a data file that was never a transcription

`data/oob_italian.json` is a **raw VASSAL extraction of a saved game whose counters had been fanned out
along a diagonal ladder for legibility** — it is *not* a transcription of rule 60.31. Measured
displacement from the rulebook hex:

| Formation | 60.31 hex | Data hexes | Off by |
|---|---|---|---|
| 2nd Libyan Div | **C3920** | C4014…C4814 | **6-10 hexes, all 9 counters** |
| 64th Catanzaro Div | **C4707** | C3714…C4814 | **7-12 hexes, all 12** |
| 4th CCNN Div | **C4507** | C3814…C4815 | **7-11 hexes, 11 of 12** |
| Gruppo Maletti | **C3617** | C3822…C4123 | **6-8 hexes, all 4** |
| 🔴 **Tobruk Garrison** | **C4807** | C4410, C4511, C4611, C4811 | **4-5 hexes — the garrison is NOT IN TOBRUK** |
| 🔴 **Benghazi Garrison** | **A4827** | A4926 | **2 hexes** |
| 🔴 **Bardia Garrison** | **C4321** | C4220 | **1 hex** |

The three city garrisons are cross-confirmed wrong by the engine's own `data/victory_cities.json`
(Tobruk C4807 = 200 VP, Bardia C4321 = 100 VP, Benghazi A4827 = 75 VP). **The garrisons of the three
biggest victory cities on the board do not stand in them.** And rule 9.16a's `is_garrison_home` stacking
exemption (`game/oob.py:311`) is being granted to units that are not in their home hex.

**Axis counter coverage: 96 of ~218 charted at GT1 (44%); 88 of 355 reinforcements (24%).**
Arrival *timing* is **perfect** — zero mismatches across all 18 modelled formations (Ariete GT18,
Rommel GT20, 5 Le GT21, 15 Pz GT24, 90 Le GT32, Trieste GT50, Littorio GT62, 164 Le GT93, Folgore GT94,
GGFF GT97…). Arrival *content* is a quarter of the chart.

Missing wholesale: **Ramcke Brigade** (6), **Sonderverband 288** (6), **300th Oasis Battalion** (13
companies — and `oob.py` *has* an unused `oasis` role), **21 Pz Div HQ** (the 5 Le → 21 Pz
reorganisation is not modelled at all), **all 19 German non-divisional artillery counters**, **all 22
unassigned Flak battalions**, all 4 pioneer battalions, **8 of the 9 unassigned Italian armoured
battalions (~53 tank TOE of Italian armour silently deleted)**, XXV Corps Artillery (the very first
Axis reinforcement in the game, GT9), RECAM, and the 2 TOE of Autoblinda 40 recce that 60.31 grants
outright. *(Note: **Centauro is not in CNA at all** — 0 hits in the rulebook. It went to Tunisia.
Drop it from any wishlist.)*

### 5.9 🔴 WHAT THE RATIO SHOULD BE — and why 1.7:1 is an artifact, not a design

The charts do **not** say the Axis outweighs the Commonwealth. Summing tank/gun TOE from the explicit
weapon-system counts printed on [4.44b] / [4.45c] / [4.44B]:

| Measure | **Rulebook** | Engine | Error |
|---|---|---|---|
| Counters @ GT1 | **3.41 : 1 Axis** | 3.31 : 1 | ✅ faithful |
| Reinforcement counters | **0.97 : 1 (parity)** | 0.97 : 1 | ✅ faithful |
| Counters, cumulative | **1.33 : 1 Axis** | 1.55 : 1 | +17% Axis |
| **Tank TOE, cumulative** | **0.64 : 1 — the COMMONWEALTH has 1.56× the Axis armour** | **1.22 : 1 Axis** | **a 1.9× swing to the Axis** |
| Gun/AA TOE, cumulative | **1.14 : 1 (near parity)** | 1.88 : 1 | +65% Axis |
| **Combat TOE, cumulative** | — | **1.72 : 1 Axis** | the measured figure |

**The mechanism, stated plainly.** The charts give the Axis a large *start-line* edge (the Italian 10th
Army against a thin Western Desert Force — historically correct, and the engine reproduces it) and then
**parity-or-better for the Commonwealth in the build-up**. The engine reproduces the start-line edge
faithfully and then **fails to deliver the Commonwealth's build-up**: Axis GT1 seeding is 44% of chart
while the Commonwealth's armour stream lands at **52% of its charted tank TOE (144 of 275)** and its gun
park at **17%**. So the Axis's September-1940 edge **never erodes**, and a campaign the charts intend to
swing toward the Commonwealth stays pinned at 1.7:1 Axis for 111 turns.

Per the charts the cumulative ratio should sit near **1.33:1 by counters, 1.14:1 by guns, and 0.64:1 by
armour** — *a toss-up leaning Commonwealth in the decisive arm*. Which is precisely the stated balance
target. **The balance problem is the OOB. It is not a tuning problem and it never was.**

---

## 6. WHAT A FULL RUN ACTUALLY DOES (measured, GT1→111, 3 seeds)

`game.scenario.campaign(seed)` + `CampaignAxisPolicy` / `CampaignCommonwealthPolicy`, run to GT111:

| seed | result | 64.73 tally | Axis cities held | CW cities held | CW combat units left |
|---|---|---|---|---|---|
| 1941 | **Axis Smashing Victory** | **275 – 20** (13.75:1) | Tobruk, Benghazi | Matruh, Barrani | 28 / 175 TOE |
| 7 | **Axis Smashing Victory** | **275 – 80** (3.4:1) | Tobruk, Benghazi | Matruh, Barrani, Bardia, Sollum | 17 / 101 TOE |
| 2026 | **Axis Smashing Victory** | **445 – 20** (22.25:1) | Tobruk, Benghazi, Siwa, Bardia, Sollum, Derna | Matruh, Barrani | **10 / 62 TOE** |

Three findings fall straight out:

1. **The Axis's score is the cities it starts on.** Tobruk (200) + Benghazi (75) = **275**, in every
   seed, and those are exactly the two cities with a 60.34 staging dump underneath them. The
   Commonwealth's 20 is Mersa Matruh (10) + Sidi Barrani (10) — the two 60.44 depots it starts on. **The
   final score is very nearly the September-1940 set-up, re-read at GT111.** This reproduces the brief's
   ablation exactly.
2. **Jalo and Giarabub never score for anyone, in any seed.** Nor does Siwa in 2/3. The desert oases are
   never garrisoned by a *supplied* combat unit, so 30-45 VP on the table is permanently dead.
3. **The Eighth Army is being annihilated.** It ends with 28 / 17 / **10** combat units. At seed 2026 the
   Commonwealth finishes the war with **62 TOE on the whole map**. This is not a campaign that leans
   Axis; it is a campaign the Commonwealth cannot fight — which is exactly what a 32%-strength OOB
   with no real tanks, no AA and no artillery predicts.

---

## 7. THE VICTORY CONDITIONS (64.7) — GAP LIST AND THE ORDER TO BUILD THEM

| # | Rule | Gap | Difficulty |
|---|---|---|---|
| 1 | **64.73 quality-test** | Implemented at the **wrong magnitude**: 1 fire instead of **three**; the unit's fuel *rate* instead of **20 CP of movement**; **Stores and Water not checked at all** though the rule names them first. | **S** |
| 2 | **64.71 persistence** | "for one full Game-Turn" — not implemented; fires instantly. | **S** |
| 3 | **64.71 / 64.72 supply trace** | The **≤90 / ≤60 truck-MP** trace back to a dump **fed from Tobruk or Tripoli** does not exist. `_supplied()` uses the rule-32.16 `cpa/2` land trace and never checks the dump's source. Note `supply.reachable_truck_moves` already exists — the machinery is there, it is just not wired to victory. | **M** |
| 4 | **64.72** | The **Commonwealth's Game-Turn-35 automatic win** — entirely missing. An *annihilation* rule (not in the book) sits where it should be. | **M** (needs #3) |
| 5 | **64.75** | Commonwealth **Withdrawal Points** — entirely missing, as is rule **20.9** (voluntary withdrawal) and **20.8** (the 32 mandatory withdrawals the Reinforcement Schedule lists). | **M** |
| 6 | **64.74** | **Replacement VPs — DO NOT BUILD THIS YET.** | **L** (blocked) |

### The recommended order — and the 64.74 landmine, quantified

**Build 1 → 2 → 3 → 4 → 5. Build 6 LAST, and only after rule 20.6/20.7.**

Rules 1 and 2 are cheap and immediately make the 64.73 score *mean* something (today a unit with one
round and no water banks a 200-VP city). Rule 3 unlocks 4. Rule 5 (64.75) is the Commonwealth's **only
non-geographic VP source** and is the natural counterweight to 64.74 — it should land *before* it.

**Why 64.74 is a landmine.** The pools are confirmed transcribed: **Axis 2,493** (German 783 + Italian
1,710) vs **Commonwealth 958**. There is **no replacement economy in the engine at all** — the string
`replacement` appears **once** in all of `game/*.py`, in a deferred-list docstring; nothing spends RPs
and nothing even restores lost TOE (`Unit.strength` is a one-way ratchet — the only mutation is
`_apply_step_loss`, `apply.py:241`). So:

* **64.74 alone** scores *every* RP as unused → **Axis 2,493 – CW 958 = 2.60:1 = a Smashing Victory
  decided at GT0**, invariant to every decision either side makes.
* **Even with the Commonwealth holding all ten cities**: 2,493 – (958 + 370) = **1.88:1, an Axis
  Decisive victory while it loses every hex on the map.** The geography pot (Axis 620 max / CW 370 max)
  is dwarfed **4:1** by 64.74.
* The Commonwealth's *ceiling* under 64.74-as-written (958 + 370 + ~126 withdrawal ≈ **1,454**) is below
  the Axis's *floor*. **The Commonwealth cannot win.**

**And the asymmetry is not a balance dial — it is a bookkeeping artifact.** The entire 1,535-point gap
is **infantry**: Axis 1,600 infantry RP vs a Commonwealth that has **no infantry pool to leave unused**
(CW infantry comes from a random 2d6 table, 20.78B, not a fixed allotment — which is *why* 64.74
excludes it "for the Commonwealth Player only"). **Like-for-like, dropping Axis infantry too: Axis 893
vs CW 958 — the Commonwealth has more.** Guns are 508 v 536 and tanks 335 v 332: near-identical.

**Recommendation**: implement 64.74 only alongside an abstract replacement economy (pool + planning lead
time + arrival at a supply city + spend to restore TOE steps — **M**, skipping the on-map RP counters
and training clock of the full 20.2-20.5), and **exclude infantry for both sides**, which yields the
near-symmetric 893 v 958. Note that even a *perfect* economy leaves 64.74 structurally Axis-favouring:
shipping the whole Axis pool costs **106,439 tons** (20.62), ~959 tons/GT for 111 turns *dedicated to
replacements*, and 20.64 gives RPs priority over supply — so a maximalist Axis starves its own army and
banks the remainder as VPs regardless.

---

## 8. CHAPTER 60 — SCENARIO GROUP ONE: THE ITALIANS

**Rule 64.3 sends the full campaign here for all initial placement, so almost every row is
campaign-critical** — with the exception of 60.2 and 60.8 (that group's own scenario length and victory
conditions, which 64.2/64.7 replace).

| Rule | What it says (one line) | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 60.1 | Sep 1940 – Feb 1941; the Italian offensive and O'Connor's counter-attack. | N/A — prose | `docs/rules/60:8` | NO |
| 60.21 | Two scenarios in the group. | N/A | `60:12` | NO |
| 60.22 | *Graziani's Offensive*: GT1.1 → GT6.3. | **N/A** — not implemented, and not needed (the campaign supersedes it) | no builder: `grep "def " game/scenario.py` | NO |
| 60.23 | *The Italian Campaign*: GT1.1 → GT20.3, incl. Operation Compass. | **N/A** — not implemented; superseded | as above | NO |
| **60.31** | **Italian initial deployment, by hex** — 9 divisional hexes + 12 garrisons/cities + "Anywhere in Libya" + "Anywhere on Map A/B" + Tripoli/Tripolitania; **first-line trucks per hex**; 2 TOE of Autoblinda 40. | **WRONG** — 96 of ~218 counters (44%); **7 formations + all 3 city garrisons on the wrong hexes** (Tobruk Garrison 4-5 hexes outside Tobruk); ~18 on-map "Anywhere" artillery counters missing; the Autoblinda 40 TOE missing; **all ~360 first-line Truck Points missing**. `data/oob_italian.json` is a raw VASSAL save extraction, not a transcription. | `data/oob_italian.json`; `game/oob.py:311`; §5.8 | **YES** |
| 60.32 | Italian air strengths: 9 plane types, refits, 28 pilots, 39 SGSUs; no refit until GT1.2. | **MISSING** — air is a 2-scalar `AirWing` proxy | `game/state.py:261`; `game/scenario.py:1015-1032` | NO (air abstracted by choice) |
| **60.33** | **Italian 2nd/3rd-line trucks**: Tripoli 25L/140M/40H; Anywhere in Libya 30L/100M/25H; Any Air Facility 10L/50M. Repair facilities at Tripoli (major), Tobruk & Benghazi (temporary). | **PARTIAL** — Libya row **seeded exactly**; **Tripoli row (205 TP, half the park) not seeded** (off-map, flagged); Air Facility row seeded **contrary to 59.61**. Repair facilities: not modelled. | `game/scenario.py:809-813, 869-893` | **YES** |
| **60.34** | **Axis initial supply**: Tobruk 200/2000/500; Bardia 100/1000/200; Benghazi 100/250/100; Derna 0/250/50; **Tripoli 250/5000/250**; **Dump 1 1000/1500/1500/200**; **Dump 2 1000/1500/1000/200**; **C0716 100/50/50**; **2 dummies**; **airfield allotment 1200/850/100/100**. | **WRONG** — the four city dumps are exact. **Dump 1 + Dump 2 are replaced by the 61.44 (Desert Fox) pool at 3.2× the charted Fuel.** Tripoli, C0716 and both dummies unseeded. | §2.1; `game/oob.py:39-40`; `game/scenario.py:645-652` | **YES** |
| 60.35 | All Axis coastal shipping counters; start in Tripoli. | **MISSING** | grepped `coastal ship` → 0 | MAYBE |
| 60.36 | Axis Malta attacks limited to **Availability Level I**. | **MISSING** — superseded for the campaign by 64.52, which is also missing | `game/scenario.py:1060-1091` | NO (64.52 governs) |
| 60.37 | Italian must plan Sept-1940 convoys in advance; **may use only lanes 2, 3, 6**. Reinforcements per the track. | **PARTIAL/WRONG** — the Benghazi convoy is labelled lane `"2"`, which the 56.18 chart calls *Sicily→Tripoli*. The engine **admits the mislabel and leaves it** (`scenario.py:1094-1098`). No convoy planning. | `game/scenario.py:967, 1094-1098` | MAYBE |
| **60.41** | **Commonwealth initial deployment, by hex** — 12 hexes + Cairo/Alexandria/Helwan + "Anywhere on Map D/E"; **first-line trucks per hex**; 2 TOE A9 + 1 TOE A10 broken down at Alexandria. | **WRONG** — 28 of 66 counters (42%); the **entire 7th Armoured, 6th Australian and 2nd New Zealand Divisions absent**; **1st RTR (the only real tank battalion) absent**; 9 units on the wrong hexes (16 Bde 64 hexes from Cairo); 4 units present that arrive later; **all ~177 first-line Truck Points missing**; the broken-down A9/A10 pool missing. | §5.2-5.4 | **YES** |
| 60.42 | Commonwealth N. African air force: 11 plane types, 14 pilots, 14 SGSUs. | **MISSING** — air abstracted | as 60.32 | NO |
| **60.43** | **CW 2nd/3rd-line trucks**: Cairo 40M/10H; Alexandria 10L/20M; Anywhere-maps 15L/40M/5H; Any Air Facility 5L/30M/20H. | **PARTIAL** — first three rows **seeded exactly** (`scenario.py:814-818, 833-866`); the Air Facility row seeded **contrary to 59.61**. | `game/scenario.py:814-818` | **YES** |
| **60.44** | **CW initial supply**: Mersa Matruh 1000/3000/4000; Sidi Barrani 250/500/100; **Dump I 500/750/500**; **1 dummy**; **air supply 200/250/50**. Unlimited supply in Cairo/Alexandria. Major repair facility Alexandria, temporary Mersa Matruh. | **PARTIAL** — Matruh and Barrani **now exact** (`scenario.py:701-704`). **Dump I replaced by the 61.36 pool at 3.4× the charted amount** (+1,600 Water the chart does not grant). Dummy unseeded. Rule-57 unlimited base **DONE**. Repair facilities not modelled. | §2.2 | **YES** |
| 60.45 | **CW Fleet**: 1 BB + 3 CA + 7 DD available; 2 BB, 2 CA, 4 AA-CA, 6 DD in Alexandria; 1 CA, 1 AA-CA, 2 DD in Valletta. No movement before Sep 1/IV. | **MISSING** — `naval=()` in **every** scenario. `NavalUnit` + `engine._naval_bombardment` are live code with **no caller**. **64.51 names the Fleet explicitly.** | `grep -rn "naval=" game/scenario.py` → 0; `game/state.py:290,442` | **YES** |
| 60.46 | Malta: 31 planes, 5 SGSUs, 10 pilots, 17 AA points; facility capacity 5; construction from Oct 1940. | **MISSING** — Malta is an abstract Bomb-Point schedule, not a place | `game/scenario.py:1060-1091` | NO (see 64.52) |
| 60.47 | CW takes the Reinforcement Track as printed; **some units need Training** (others must be assigned as Training Units); **no Replacement Points before Nov 1940**. | **MISSING** — no training system, no RP system, and the track itself is at 25% | grepped `training\|trained` in `game/*.py` → 0 functional hits; §5.4 | **YES** |
| 60.5 | The air-facility list: 20 airfields, 30 landing strips, 2 flying-boat basins, 1 alighting area. | **N/A** — air abstracted; `oob.py:109` skips every airfield counter at load | `game/oob.py:105-110` | NO |
| **60.6** | **The Italian Player has the Initiative for the entire first Game-Turn**; roll from GT2. | **MISSING** — imported by 64.4; `campaign()` sets no initiative fields at all, so GT1 is rolled and **both Initiative Ratings are 0 for all 111 turns** | `game/scenario.py` campaign ctor; `game/engine.py:216-222` | **YES** |
| **60.7** | **Construction at start**: no minefields, fortifications or pipeline (other than the RR's). RR runs to Mersa Matruh and ends there. **All ports at listed Efficiency except Tobruk** (San Giorgio partially blocks the harbour). | **PARTIAL / WRONG** — RR ✔, minefields ✔, pipeline ✔, city forts defensible (25.12). **Ports WRONG on all three**: Tobruk seeded `eff=5` where 55.12+55.25 give **5 max, starting at 2**; Benghazi seeded `10` where 55.3 charts **3**; Mersa Matruh seeded `10` where 55.3 charts **1**. The correct values are already in `data/logistics_rates.json` and are not read. | §2.5; `game/scenario.py:996-1004`; `game/logistics_data.py` | **YES** |
| 60.81 | Graziani's Offensive victory conditions. | **N/A** — the campaign uses 64.7 | `game/campaign_victory.py` | NO |
| 60.82 | The Italian Campaign victory conditions (a different 8-city VP table). | **N/A** — the campaign uses the 64.73 10-city table | `data/victory_cities.json` | NO |
| 60.91 | **Air Abstracted (Land & Logistics Games): None.** | **DONE — this is the engine's abstraction level, and it needs no adjustments.** The clean reading. | `game/scenario.py` (full logistics + abstract air) | **YES** |
| 60.92 A/B/C | Air **&** Logistics abstracted: MPs = Medium Trucks; Axis/CW supply replaced by Supply Units. | **N/A** — we play the **full** Logistics Game, not the §32 abstraction | `game/scenario.py:1290-1310` (`motorized_supply=False`, with the measurement that rejects 32.32) | NO |
| 60.93 A/B/C | Logistics abstracted (Land & Air): MPs = Medium + Heavy. | **N/A** — same | as above | NO |

---

## 9. CHAPTER 61 — SCENARIO GROUP TWO: THE DESERT FOX

**Campaign relevance**: 64.3/64.4/64.6 send the **short campaign** (GT26 start) here. **We do not build
the short campaign**, so every row is NO — *with one enormous exception*: **61.36 and 61.44 are being
consumed by the FULL campaign, wrongly** (§2.1/§2.2). `rommels_arrival()` implements 61.2 (the *Race for
Tobruk*), which is a separate 13-turn scenario, not the short campaign.

| Rule | What it says (one line) | Status | Evidence | Campaign-critical? |
|---|---|---|---|---|
| 61.1 | The DAK and Rommel arrive; two scenarios from one set-up. | N/A — prose | `61:6` | NO |
| 61.2 | *Race for Tobruk*: GT26.3 → GT38.3. | **DONE** — this is `rommels_arrival()` | `game/scenario.py:214` (docstring cites 61.2) | NO |
| 61.31 | CW land deployment at GT26 (2 Armd Div, 9 Aus, Tobruk garrison, Alexandria refit pool…). | **DONE for `rommels_arrival`** | `data/oob_desert_fox.json` | NO |
| 61.32 | CW tank TOE at GT26 (3 Hus 3× Mk VI; 5 RTR 1×A9 + 4×A13; 6 RTR 5×M13/40 captured). | **PARTIAL** — `rommels_arrival` OOB | `data/oob_desert_fox.json` | NO |
| 61.33 | CW air: 5 squadrons by base; air facilities. | MISSING — air abstracted | | NO |
| 61.34 | Malta: capacity 8, 26 AA, 55 planes. | MISSING | | NO |
| 61.35 | CW trucks: 45L/100M/25H free + 25L/175M/35H in Alexandria/Cairo. | PARTIAL — `_rommel_trucks` is a **flagged placeholder** | `game/scenario.py:454-480, 555-557` | NO |
| **61.36** | **CW supply**: 9 dumps + 3 dummies; Benghazi 100F/50A/150S; Tobruk 500F/1500A/1000S; **2550 Fuel / 1700 Ammo / 1600 Stores** to distribute (≤25% per dump, ≥50 each). | **🔴 LEAKING INTO THE FULL CAMPAIGN.** `game/oob.py:40` `cw_dump_pool_61_36()` seeds this pool into `campaign()`, where **rule 64.3 mandates §60.44 instead**. Built state: 5 × `AL-Dump` = 1,700/2,550/1,600 — **61.36 verbatim**, 3.4× the 60.44 chart. | `game/oob.py:40,224`; `game/logistics_data.py:164-170`; built state | **YES — as a BUG** |
| 61.37 | CW Fleet in Alexandria; no movement before GT27. | MISSING — `naval=()` | | NO |
| 61.38 | CW reinforcements/replacements; the release schedule; 7th Armoured refit (all tanks broken down). | PARTIAL — `rommels_arrival` | | NO |
| 61.41 | Axis land forces at GT26: German units within 1 hex of El Agheila; 6 Italian divisions; **Battle Groups permitted**; Sabratha reduced. | PARTIAL — `rommels_arrival` OOB. **Battle Groups are not modelled at all.** | grepped `battle_group` → 0 | NO |
| 61.42 | Axis air: German planes per the chart + 155 Italian planes; pilots; facilities. | MISSING | | NO |
| 61.43 | Axis trucks: Italian 1st-line 45L/220M/50H; 2nd/3rd 95L/280M/50H; +10M at air facilities. | PARTIAL — placeholder | `game/scenario.py:454-480` | NO |
| **61.44** | **Axis supply**: 5 dumps (2 dummy); **9600 Fuel / 2500 Ammo / 950 Stores / 1100 Water** across 3 active dumps (≤50% each); Tripoli 3000F/1500A/500S; 50F/50A to air facilities; no convoy in GT1. | **🔴 LEAKING INTO THE FULL CAMPAIGN.** `game/oob.py:39` `axis_dump_pool_61_44()`. Built state: 5 × `AX-Dump` = 2,500 A / **9,600 F** / 950 S / 1,100 W — **61.44 verbatim**, vs the 60.34 chart's Dump 1+2 = 2,000 / **3,000** / 2,500 / 400. **+6,600 Fuel Points the Axis should not have.** | `game/oob.py:39,223`; `game/logistics_data.py:157-161`; built state | **YES — as a BUG** |
| 61.45 | Axis reinforcements taken normally off the track. | DONE | `data/reinforcements_desert_fox.json` | NO |
| 61.5 | **Axis has the Initiative through GT27**; roll from GT28. | **DONE for `rommels_arrival`** (`initiative_fixed=AXIS, until=2` — the scenario is re-based to GT1) — **and it is exactly the mechanism `campaign()` fails to use for 60.6.** | `game/scenario.py:318-319`; `game/engine.py:203-234` | NO (but it is the fix pattern for 64.4) |
| 61.6 | Construction: RR to Mersa Matruh; no minefields/pipeline; **Benghazi at Efficiency 0, Tobruk at 7** (sic — see note); CW may place 4 Level-1 forts near Tobruk; Sollum–Barrani roads and the Tobruk network built. | **PARTIAL** — see the port note below | `game/scenario.py:380` (`rommels_arrival` seeds Tobruk `eff=7/max 7`) | NO |
| 61.71 | Air abstracted: revised 2nd/3rd-line truck totals. | N/A | | NO |
| 61.72 A-D | Air & Logistics abstracted: MPs; Axis 290 MP / CW 150+90; Supply Units. | N/A — full logistics | | NO |
| 61.73 A-C | Logistics abstracted: MPs = M+H; +1 supply unit per air facility. | N/A | | NO |
| 61.8 | *Race for Tobruk* victory: hold Tobruk. | DONE for `rommels_arrival` | | NO |

> **Note on the "Efficiency 7" in 60.7 and 61.6.** Both scenario chapters say Tobruk starts at
> "Efficiency Level 7". This **contradicts the rules proper**: 55.12 states *"Tobruk has an Efficiency
> Level of **5**"*, 55.25 states *"the San Giorgio reduces the efficiency level of Tobruk by **three**
> levels"* (→ **2**), and the 55.3 chart lists Tobruk at **5** with footnote † *"Begins the campaign with
> an efficiency **below** the listed five due to the San Giorgio"*. `7` is almost certainly an OCR
> corruption of `2` (5 − 3 = 2, and 2/7 are a classic OCR confusion in this typeface). **`data/logistics_rates.json`
> already encodes the correct reading (level 5, "starts below eff 5").** The engine's `campaign()` seeds
> neither — it seeds `eff=5`, i.e. no San Giorgio penalty at all.

---

## 10. CHAPTERS 62 & 63 — SCENARIO GROUPS THREE (CRUSADER) & FOUR (EL ALAMEIN)

**All 78 numbered rules across both chapters are N/A to the campaign, and the reasoning is airtight:**

* **64.3** (`docs/rules/64:14`) sends the campaign's initial deployment to **§60.0 or §61.0**. 62/63 are
  never named. **64.4** and **64.6** likewise.
* **64.51** (`64:22`) — *"There are no restrictions on normal game actions (Raids on Rommel, the
  Commonwealth Fleet, etc.)"* — **explicitly countermands 63.5's prohibitions**. Direct proof that 63's
  special rules are scenario-local.
* Neither scenario is implemented (`grep -riE "crusader|alamein|gazala|last_chance|long_retreat"` over
  `game/ data/ scripts/` → zero scenario hits), and none is called for.

The engine's five builders map as: `coastal_corridor` (synthetic toy), `battle_for_tobruk` (terrain
proof), `rommels_arrival` = **61.2**, `siege_of_tobruk` (house scenario), `campaign` = **64.0**.
**Scenario Group ONE has no standalone builder** (its GT1 set-up is consumed inside `campaign()`);
**Groups THREE and FOUR have none, correctly.**

**What 62/63 are actually worth to this project** — three things, none of them a rule to port:

1. **Clock anchors, already consumed.** `game/campaign_policy.py:259-260` hardcodes `CRUSADER = (57, 64)`
   and `ALAMEIN = (102, 111)`, taken from 62.2 and 63.2. *(Nit: 62.2 runs Crusader to **GT65**; the
   engine window ends at 64. Immaterial for an AI posture heuristic.)*
2. **63.32 / 63.42 are the best available VALIDATION FIXTURE in the whole rulebook.** They state exactly
   what every tank battalion holds at **GT102**. A campaign that plays GT1→102 can be diffed against them
   to prove the production/replacement pipeline actually produced the historical force. **That is worth
   more than any rule in the chapter** — wire it as an integration test, don't port it.
3. **63.47 is the rulebook's only model of the post-Alamein Axis replacement chokehold** (RPs cut to 5%,
   forced to Tripoli, released 25% at a time — *"the Allied Landings … almost all manpower was being
   diverted to Tunisia"*). **64.5 gives the full campaign no equivalent.** If the campaign ever needs a
   *sanctioned* Axis throttle, this is it — a lever the rulebook itself provides, rather than an invented
   one. **MAYBE campaign-critical.**

Two live gaps surfaced by the 62/63 sweep, both sourced from **ch. 90, not 62/63**, both already folded
into §5 above: the **Ramcke Brigade** (absent entirely, GT86-93) and the **late-war model table**
(no Sherman / Crusader III / Scorpion / Churchill / 17-pdr — released by the Production Chart at GT75-103,
*inside the campaign's own clock*). **Without the Scorpion the campaign has no mine-clearing capability
at all** (`90:1329`) — moot today only because **nothing can build a minefield either**
(`game/construction.py:44-47`: *"DELIBERATELY NOT BUILT … 24.3 minefields, 24.4 fortifications, 24.5
roads"*).

---

## 11. 🔴 THE HEADLINE: THE CAMPAIGN IS AN AXIS SMASHING VICTORY AT GAME-TURN 1, BEFORE ANYBODY MOVES

Scoring the 64.73 table against the **initial state**, with no moves played:

```
*** THE SCORE AT GAME-TURN 1, BEFORE ANYBODY MOVES ***
   AXIS 300   COMMONWEALTH 20
   grade: Axis Smashing Victory: 300-20 Victory Points (64.76)
```

And after **111 Game-Turns × 3 Operations Stages = 333 stages of war**:

| seed | GT1 → GT111 (Axis) | GT1 → GT111 (CW) | Axis Δ | CW Δ | grade at GT1 | grade at GT111 |
|---|---|---|---|---|---|---|
| 1941 | 300 → **275** | 20 → **20** | **−25** | **±0** | Axis Smashing | Axis Smashing |
| 7 | 300 → **275** | 20 → **80** | **−25** | +60 | Axis Smashing | Axis Smashing |
| 2026 | 300 → **445** | 20 → **20** | +145 | **±0** | Axis Smashing | Axis Smashing |

**The whole war moves the score by 25 points in two seeds out of three, and the grade never changes.**
The campaign's outcome is the September-1940 set-up, re-read at Game-Turn 111.

### Why — and it is not one bug, it is four stacking

Scoring the ten cities at GT1 (`_occupier` = a supplied combat unit of ≥1 TOE on the hex):

| city | VP (Ax/CW) | units on the hex at GT1 | scores? |
|---|---|---|---|
| **Tobruk** | **200**/100 | `IT-LTC` — the *Libyan Tank Command HQ*, alone | **AXIS 200** |
| **Bardia** | **100**/50 | 4 Italian tank counters | **AXIS 100** |
| Mersa Matruh | 100/**10** | `BR-Selby` (Matruh Garrison) | CW 10 |
| Sidi Barrani | 50/**10** | 2 CW counters | CW 10 |
| **Benghazi** | **75**/100 | **NONE — the hex is EMPTY** | — |
| **Giarabub** | 15/10 | **6 Italian garrison counters** | **— they FAIL the supply test** |
| **Derna** | 25/50 | 1 Italian garrison counter, **standing on its own dump** | **— it FAILS the supply test** |
| Sollum | 25/10 | none | — |
| Siwa | 20/10 | none | — |
| Jalo | 10/20 | none | — |

1. **The Axis starts standing on the two biggest prizes** (Tobruk 200 + Bardia 100 = 300 of its 620
   maximum) — and it starts standing on them *because the 60.34 staging dumps are underneath them*,
   which is what makes its occupiers pass the supply test. The Commonwealth's two cities are worth
   **10 points each to it**. The 64.73 table is deliberately asymmetric.
2. **Benghazi (75 VP) is empty at GT1** — its garrison is seeded 2 hexes away at A4926 (§5.8). So is the
   Tobruk Garrison (4-5 hexes out) — the 200-VP fortress is held by a lone HQ counter.
3. **Giarabub and Derna are garrisoned and score nothing.** Derna's garrison is standing *on its own
   supply dump* — but the 60.34 chart gives that dump **zero Ammunition**, so `_supplied()` cannot trace
   ammo and the unit does not "occupy". **The engine's 64.73 test asks "can you REACH a dump holding
   ammo?" where the rule asks "do you HAVE ammunition for three fires?"** — a structurally different
   question, and one a garrison sitting on its basic load would pass.
4. **The Commonwealth cannot take anything back**, because its army is a 32%-strength OOB with no real
   tanks, no artillery and no AA arm (§5.2-5.6). It ends the war with 28 / 17 / **10** combat units.

### And the deepest point: we implemented exactly the subset of rule 64.7 that favours the Axis

The rulebook's victory design has **three** instruments, and they balance each other:

| instrument | whose win | status |
|---|---|---|
| **64.71** — Axis takes Alexandria + Cairo | **Axis outright** | **PARTIAL — implemented** |
| **64.72** — from GT35, no Axis unit can trace 60 truck-MP to a Tobruk/Tripoli-fed dump | **Commonwealth outright** | **MISSING** |
| **64.73** — count geographic points (Axis-weighted: 620 max vs CW 370) | tiebreak | **PARTIAL — implemented** |
| **64.74** — unused Replacement Points | Axis-weighted (2,493 v 958) | MISSING |
| **64.75** — Commonwealth Withdrawal Points | **Commonwealth only** | **MISSING** |

**The two instruments that are implemented are the Axis's. Both of the Commonwealth's — the 64.72
automatic win and the 64.75 withdrawal points — are missing.** The 64.73 table is *supposed* to be
Axis-heavy: an Axis still holding Cyrenaica at the end is the "nothing happened" baseline, and the
Commonwealth's answer to it is not to out-point the Axis on geography — it is to **strangle the Axis
supply and win outright under 64.72**. We removed its only weapon and then measured the balance.

---

## 12. TOP FIVE — what I would fix first

### 1. THE COMMONWEALTH ORDER OF BATTLE — starting with the `classify()` substring bug &nbsp;&nbsp;**[L]**
The charts say the Commonwealth should finish the war with **1.56× the Axis's armour** (0.64:1) and it
finishes with **0.82×** (1.22:1 Axis), because it is loaded at **32% of its own chart** — and its entire
GT1 "armour" is five units misclassified by `if "Armoured" in g or "Tank" in g` at `game/oob.py:145-146`
(two anti-tank regiments, one artillery regiment and one motor-infantry battalion), while **1st RTR, its
only real tank battalion, is absent**. *This is the balance problem; it is not a tuning problem and it
never was, and every hour spent tuning on top of this OOB is spent on sand.*
**Order within it**: (a) the `classify()` bug + an AA role (S — but it must land *with* (b), or the CW
loses its phantom tanks and gets nothing back); (b) a `oob_campaign_extra`-style **Commonwealth gap-fill
layer** (there is none — the existing one is Axis-only, and `reinforcements_campaign_source.json` has
**zero Allied entries**); (c) the missing models (Sherman, Valentine, A10, Crusader I/III, 17-pdr, the
two AA rows…); (d) rule 20.11 brigade → three battalions.
**Do NOT do the Axis half alone** (the 7 missing Italian tank battalions, the 3× gun park) — that is the
BALANCE TRAP and it swings the campaign harder Axis.

### 2. RULE 64.7's VICTORY CONDITIONS — fix the scoreboard before you measure anything with it &nbsp;&nbsp;**[S → M]**
The campaign is an **Axis Smashing Victory at GT1 before a single move**, five of the ten cities score for
nobody in any seed, and a garrison standing on its own dump fails the occupation test — *you cannot tune
toward a balance target with an instrument this broken.*
**Order**: (a) 64.73's quality-test at the **right magnitude** — *three* fires not one, *20 CP* of
movement not one turn's rate, and **Stores + Water for a week**, which are not checked at all (**S**);
(b) 64.71's "for one full Game-Turn" persistence (**S**); (c) the **≤90/≤60 truck-MP trace to a
Tobruk/Tripoli-fed dump** — `supply.reachable_truck_moves` already exists, it is simply not wired to
victory (**M**); (d) **64.72, the Commonwealth's automatic win** (**M**) — today an *annihilation* rule
that is nowhere in the rulebook sits in its place.

### 3. THE THREE INVENTED SUPPLY MAGNITUDES — every one is a number we made up, and all three favour the Axis &nbsp;&nbsp;**[S, S, M]**
*"Let's stop inventing things and just port the rulebook."* These are the inventions, in ascending cost:
* **The port Efficiency Levels** (**S**) — `data/logistics_rates.json` **already holds the correct 55.3
  values** (Tobruk 5, Benghazi 3, Matruh 1) and `_campaign_ports()` reads only the `tons` key, hardcoding
  `eff=10/10`. Tobruk lands **2.5× the charted tonnage** (no San Giorgio penalty, 55.25); Benghazi is
  **3.3× harder to bomb shut**; Matruh **10×**. It also unblocks the air war, which was built specifically
  to shut harbours and currently cannot.
* **The 61.44/61.36 dump pools** (**S**) — rule **64.3** mandates §60.0; `game/oob.py:39-40` seeds the
  **Desert Fox** pools, handing the Axis **+6,600 Fuel Points** (9,600 vs the charted 3,000).
* **`_malta_bomb_points`** (**M**) — an invented month-by-month schedule whose own docstring calls it
  *"a primary calibration lever for the Axis faucet"*. Rule **64.52** names the chart to use instead: the
  campaign row of [44.41] is **I = Unlimited, II = 25 GT, III = 12, IV = 12**.

### 4. THE AXIS GARRISON HEXES — the Tobruk, Bardia and Benghazi garrisons do not stand in Tobruk, Bardia or Benghazi &nbsp;&nbsp;**[S]**
`data/oob_italian.json` is a **raw VASSAL save extraction whose counters were fanned out along a diagonal
for legibility**, not a transcription of rule 60.31 — so the garrisons of the **200-, 100- and 75-VP
cities** sit 4-5, 1 and 2 hexes outside them (Benghazi's hex is **empty at GT1**), five more formations
are 6-12 hexes off, and `is_garrison_home`'s 9.16a stacking exemption is being granted to units that are
not in their home hex. *Pure data, no engine change, and it is 90% of the final score.*

### 5. THE FIRST-LINE TRUCKS (59.42 / 60.31 / 60.41) &nbsp;&nbsp;**[M]**
`is_first_line_truck` is **never set True anywhere in the codebase**, so the ~**360 Axis** and ~**177
Commonwealth** Truck Points the deployment charts allot hex-by-hex to every starting formation — *more
than the 2nd/3rd-line parks that were just fixed* — do not exist, and neither does **59.66B**'s start-line
load of **1 Ammo or 3 Fuel per attached Motorization Point** (up to 305 A / 915 F Axis, 147 A / 441 F CW,
sitting with the troops at the front). *Without them rule 3.4's "Motorized Infantry must actually have
Trucks to use its Motorized CPA" is unenforceable, and `Mobility` stays a free static field.*

### Honourable mentions (the next five)
6. **Rommel and the Commonwealth Fleet** (**M**) — `rommel=None` and `naval=()` in the campaign, though
   **64.51 names both explicitly**. Both are live, tested engine systems with no caller.
7. **Initiative** (**S**) — `campaign()` is the only scenario that sets no initiative fields, so rule
   **60.6** (Axis Initiative for all of GT1, imported by 64.4) never fires and **both Initiative Ratings
   are 0 for 111 turns**. `rommels_arrival` already shows the fix pattern (`scenario.py:318-319`).
8. **The Ramcke Brigade** (**S**) — 6 counters, morale +2, airdroppable, **GT86-93 — straight into the
   Alamein window** — and **0 hits** across `game/ data/ scripts/ tests/`.
9. **59.61's air-facility truck rows** (**S**) — the engine obeys 59.61 for the supply allotments and
   disobeys it for the truck rows, over-seeding Axis +60 TP and CW +55 TP.
10. **64.74 + rules 20.6/20.7** (**L**) — *last*, and only together. 64.74 alone is a **2.60:1 Axis
    Smashing Victory decided at GT0**; and even with a perfect economy the pools (Axis 2,493 v CW 958) are
    structurally Axis-favouring **only because of infantry** — like-for-like it is **Axis 893 v CW 958**.
    Excluding infantry for *both* sides is the obvious house rule.

---

## APPENDIX — rulebook defects found while auditing (do NOT "fix" the engine to match these)

The OCR'd rulebook contains internal contradictions. Where the engine already has the right value, it is
recorded here so a later pass does not "correct" it back to the typo.

| Defect | Rulebook says | The correct reading | Engine |
|---|---|---|---|
| **Benghazi's hex** | ch. 60 says **B4827** twice (`60:50`, `60:427`) | **A4827** — the authoritative *Summary of Important Locations* (`90:198`) and chapters 61 (`61:232`), 62 (`62:332,404`) and 63 (`63:446`) all agree, and Benghazi's own airfields (Benina A4829, El Berca A4728) are on map A. | ✅ **A4827 — correct.** `data/victory_cities.json:13`. Do not change it. |
| **Tobruk's start Efficiency** | 60.7 and 61.6 both say **"Efficiency Level 7"** | **2**. 55.12: *"Tobruk has an Efficiency Level of 5"*; 55.25: *"the San Giorgio reduces the efficiency level of Tobruk by three levels"*; the 55.3 chart lists **5** with footnote † *"Begins the campaign with an efficiency **below** the listed five"*. 5 − 3 = **2**; `7` is an OCR corruption of `2`. | ❌ seeds **5** (no penalty at all). `data/logistics_rates.json` already carries the right reading. |
| **63.83 B/C** | cites *"as in **63.72** B/C"* — 63.72 is the railroad rule | means **63.82** B/C | N/A (63 unimplemented) |
| **[4.43b] print errors** | GT93 printed as "91"; GT99 as "90"; "XXII(M)" where [4.44b] writes "XXI(M)" | per [4.44b] | data follows [4.43b] where they conflict |
| **5 Panzer Regt HQ / 2nd MG Bn** | [4.43b] says GT22/1 and GT25/3; [4.45c] says 2/21 and 2/24 | genuinely ambiguous | data follows [4.43b] |
| **20.72's "two months"** | contradicted by its own worked example | **four Game-Turns** (20.21, and both table notes) | N/A (no RP economy) |
| **"Centauro"** | — | **not in CNA at all** (0 hits in the whole rulebook). It went to Tunisia, off-map. | correctly absent — drop it from any OOB wishlist |
