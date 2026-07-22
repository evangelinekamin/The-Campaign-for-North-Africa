# THE FAUCET AUDIT

**Where twelve times the burn rate comes from.**

> **RESOLUTION, 2026-07-22 (commit "fix(supply): the faucet, corrected to the charts").** Culprits
> **1** (the oasis sentinel in `convoy_plan_doctrine`), **3** ([56.21]'s per-Game-Turn allowance in
> `_campaign_convoys`) and **6** ([49.3]'s 9% Commonwealth rate in `engine._base_evaporation`) are
> FIXED, each pinned by a test. Culprits **5** (the Tobruk lane outside the [56.5] allowance), **7**
> (the 55.14/55.16 owner ruling) and **8** (the rule-57 base riding the wells' evaporation exemption)
> are FLAGGED in place, unchanged. Culprit **4** is confirmed not a defect.
>
> Culprit **2, THE LAST MILE, IS THE WHOLE OF WHAT IS LEFT, and the measurement after the fixes says
> which third of it to build first.** Seed 1941, before -> after: Stores LANDED 56,214 -> 261,297
> Points, Stores DELIVERED forward by lorry 57,093 -> 58,339 (flat -- the 60/25/15 `_TRUCK_LOAD_MIX`
> caps it), Stores EATEN 23,893 -> 19,695, stores shortfalls 8,362 -> 8,000. **Delivered stores
> already exceed eaten stores threefold**, so the binding constraint is not the pipe but the last
> hex: supply is drawn strictly in-hex and there is no [53.11] first-line tier to close it. Build
> the first-line trucks; do NOT re-derive the load mix first, which would only grow the forward
> piles. The landed/burned headline moved 12.3x -> 22.0x (seed 7: 11.1x -> 19.7x) for exactly the
> reason this audit predicted: a correct faucet on a chain that still cannot move it.

> **REPAIR, 2026-07-22 (commit "fix(supply): the faucet repair").** Three adversarial verifiers read
> the resolution commit and found that the RANK-3 fix, correct in reading the [56.5] allowance as a
> Game-Turn's, then sailed the WHOLE allowance -- the licence for all six [56.11] lanes -- into the
> ONE modelled harbour and let the overflow expire, citing [56.27]. **[56.27] is an ADVISORY to the
> planner; [56.25] is the operative rule** ("the Axis Player ... ALLOCATES his available tonnage to
> the lanes -- and ports -- he wants them to use"). Fixed: the Benghazi lane now carries
> `min(allowance, Benghazi's Game-Turn throughput = 3 x 2,500 t)` and the balance sails the
> Tripoli/Bizerta lanes this engine does not model -- planned around, not annihilated. **This is what
> makes 41.6/44 convoy interdiction able to reduce Axis LANDED supply again**: with the manifest at
> the quay's size rather than 2-3x it, tonnage skimmed at sea no longer comes off a surplus the quay
> would have expired anyway. Measured, seed 1941, Malta live vs neutralised: **AFTER the repair the
> island denies 47,108 Fuel Points over the campaign (2,664,528 vs 2,711,636); BEFORE it, +4,322 of
> random sign -- inert**, which is precisely this audit's "clincher". The faucet itself is NOT
> reduced: with Malta off, landed Fuel is 2,711,636 after the repair vs 2,716,544 before -- the clip
> is landed-neutral, and what the Axis EATS is unchanged (138,862 Points), because the last mile
> (culprit 2) is still the binding constraint. Full campaign, seed 1941 (resolution -> repair):
> shipped 2,113,429 -> 899,929 t (Benghazi's 56.25 share), landed Fuel 2,716,544 -> 2,664,528, Ammo
> 71,500 -> 70,325, Stores 261,297 -> 256,510, evaporated 2,142,319 -> 2,094,868, landed/burned
> 21.96x -> 21.54x (seed 7: -> 19.19x).
>
> **CONSEQUENCE STATED (the verifiers' problem 2), which the resolution left unsaid:** because the
> licence almost always exceeds one harbour's Game-Turn throughput, the [56.4]/[56.5] month-to-month
> variation ABOVE that throughput does not reach LANDED tonnage on the single modelled lane -- it is
> absorbed by the 56.25 allocation to the unmodelled lanes. The charts still decide which Game-Turns
> sail at all and the total licence; the harbour is the binding gate on what lands, which is
> hypothesis (f). Also in the repair: `_evaporate` now INDEXES its per-side rate (KeyError on an
> unknown side, not a silent .get-default exemption -- the verifiers' problem 5); [49.3]'s hot-slice
> stacking is raised as an **OWNER RULING** in `_base_evaporation` rather than decided silently
> (problem 4, scan PDF p.67 = book p.20); and the Benghazi lane, mislabelled "2" (Sicily -> Tripoli)
> against the [56.11] chart, is corrected to "3" (Italy -> Benghazi) in lockstep with its Malta
> interdiction order (problem 6 -- a labelling fix, since malta.interdiction_points reads no distance
> yet). The two benchmark signatures are BYTE-IDENTICAL through all of it.

Block 2, 2026-07-22. **Measurement only — no engine behaviour was changed by this work.**
Instrument: `scratchpad/faucet_audit.py` (read-only; folds a full 111-Game-Turn campaign and
tallies every stage of the supply chain). Numbers below are seed 1941, 281,906 events, winner
AXIS. Scan evidence rendered at 200-220 dpi from `tmp/The Campaign for North Africa.pdf` pages
74, 75, 108 and 110 and read with eyes.

---

## THE ANSWER

**The Axis is not over-supplied. He is drowning in fuel and ammunition and STARVING for stores —
and the single largest cause is a policy bug, not a rule.**

The "12x" decomposes, and the decomposition is the whole finding:

| Commodity | Landed (Points) | Burned (Points) | Ratio | What it means |
|---|---:|---:|---:|---|
| **Fuel** | 1,702,083 | 19,443 | **87.5x** | a lake nobody can drink |
| **Ammunition** | 66,507 | 892 | **74.6x** | ditto |
| **Stores** | 56,214 | 23,893 | **2.4x** | **the only scarce thing in the war** |
| Water | 9,047 (convoy) | 105,034 | — | drawn from wells, not convoys |
| **All four** | 1,833,851 | 149,262 | **12.3x** | the headline, and it is an average of a lake and a drought |

Against that, the army's *licensed* Stores requirement at Game-Turn 1 alone is **2,344 Points every
Game-Turn** ([51.11], 4 per TOE Strength Point x 586 TOE) — call it 260,000 Points across the war
and rising as the army grows. **It ate 23,893. Nine per cent.** `STORES_SHORTFALL` fired **8,362
times** — better than half of all Axis unit-Game-Turns spent with no stores at all.

So the honest verdict against the six hypotheses:

* **(a) over-shipping — NO, the reverse.** The engine ships **25%** of what [56.21] licenses,
  because it reads the [56.5] roll as a *monthly* allowance and quarters it. Scan-confirmed
  defect.
* **(b) over-generous port gate — NO.** [55.3]/[55.14] are implemented exactly, one shared
  tonnage per port per Operations Stage. Benghazi already hits its cap in **94 of 230** quay
  beats.
* **(c) wrong Equivalent-Weights divisor — NO.** [54.5] verified cell by cell off the scan, both
  directions, cross-checked against [49.11]'s "250 pounds".
* **(d) mis-applied evaporation — NO.** 6% once per Game-Turn (measured: exactly one hit per
  Game-Turn per dump), +5% per hot Operations Stage, dumps and trucks, wells exempt. Faithful.
  It is enormous — **2,292,567 Fuel Points, 76% of all the fuel landed in the war** — but that is
  the *equilibrium of a reservoir with a blocked outlet*, not a leak.
* **(e) under-consumption — YES, and structurally.** The rates are all faithful. The army is not
  fed: the convoy ships the wrong thing, and the lorries that carry it are 28% of the charted
  park with the [53.11] last rung missing entirely.
* **(f) genuinely faithful over-supply — YES, and it is a major finding.** On the book's own
  numbers the [56.5] licence is **13,500-50,000 tons a Game-Turn** against an army whose absolute
  theoretical maximum appetite is **~7,955 tons a Game-Turn** and whose realistic appetite is
  ~2,500-3,000. **The book hands the Axis 5-15x what he can eat at the quay, and always did.**
  Rule 53.0 says why, out loud: *"Trucks are the game; without a well-organized and efficient
  truck convoy system your entire military effort will fall apart."*

**Why the score does not track the cargo.** What feeds the army is Stores, and the Stores that
reach it are set by (i) a convoy split that allots Stores its 10% floor, and (ii) 155 general-
haulage Truck Points. Neither number moves when a convoy is sunk. Malta can sink 7% or 70% of the
tonnage and the tap at the far end still runs at the same rate, because **the pipe, not the
reservoir, is what is full.**

---

## PER-STAGE TABLE: LICENSED vs ACTUAL

| # | Stage | What the book licenses | What the engine did (seed 1941, GT1-111) | Verdict |
|---|-------|------------------------|------------------------------------------|---------|
| 1 | **Shipped** [56.4]/[56.5]/[56.21] | fixed + variable x die **per GAME-TURN**: **1,550,000 - 2,544,000 tons** (expected ~2,038,000) | one roll per calendar month, quartered across its Game-Turns: **507,000 tons** | **DEFECT — under-ships 4.0x** |
| 1b | **What is IN it** [56.22] | the Axis Player's free choice within the tonnage | **45% fuel / 45% ammo / 10% stores**, every sailing, all war | **DEFECT — the doctrine is poisoned (see below)** |
| 1c | **Lanes** [56.11]/[56.12] | six lanes, up to six convoys a Game-Turn | one allowance lane (2 -> Benghazi) + a fixed-manifest Tobruk lane (6) at 680 t/GT **outside the allowance** | PARTIAL + a small unlicensed faucet |
| 2 | **Landed** [55.3]/[55.14] | Benghazi 2,500 t / Tobruk 1,700 t / Matruh 250 t per Operations Stage, x eff/max_eff, rounded up, ONE shared tonnage across commodities | exactly that; 536,510 t of 582,429 t shipped landed (92%); Benghazi at cap in **94 of 230** quay beats | **FAITHFUL** |
| 3 | **Converted** [54.5] | Ammo 4 t, Fuel 1/8 t, Stores 1 t, Water 1/6 t per Point | `supply.TONS_PER_POINT` identical; `tons_to_points` floors, `points_to_tons` ceils | **FAITHFUL — verified on the scan** |
| 4 | **Evaporated** 49.3/52.44/29.34 | 6% of on-map Fuel+Water once per **Game-Turn**, +5% per **hot Operations Stage**; wells/pipelines and sea convoys exempt; trucks included | exactly that (probe dump: **1 hit per Game-Turn**). 2,236,633 Points from dumps + 55,934 from trucks | **FAITHFUL** (two small gaps below) |
| 5 | **Eaten** 49.13/50.14/51.11/52.41-42 | Fuel = rate x ceil(CP/5) x TOE; Ammo 4/3/2 per TOE; Stores 4 per TOE per GT (HQ 1); Water 1 flat inf / 1 per TOE veh, doubled hot | every law present and correct, per-model fuel rates wired | **RATES FAITHFUL** |
| 5b | **Delivered to the unit** 53.11/53.14/54.16 | three-tier chain: port -> forward dump -> unit -> the unit's own first-line lorries | 215 of **780** charted Axis Truck Points; **no [53.11] tier at all**; 57,093 Stores Points delivered forward in 111 Game-Turns = **514 a turn against 2,344 needed** | **THE BINDING CONSTRAINT** |

---

## STAGE 1a — WHAT IS SHIPPED. **THE ENGINE SHIPS A QUARTER OF THE LICENCE.**

### The book, verbatim off the scan (PDF p.75 = book p.24)

> **[56.21]** "... The figures given on the Tonnage Determination Table are the tonnage of
> supplies that the Axis may ship **in that Game-Turn** (for which he is planning)."
>
> **Example** "... The Axis Monthly Shipping Table tells the Axis Player to use row E on the
> Tonnage Capacity Table for November 1941. The Player refers to that Table and column and rolls a
> die; he rolls a 4. That means he may ship **21,000 tons of supplies and Replacement Points ...
> on Game-Turn 55.**"
>
> **[56.22]** "Having determined the allowable tonnage **for a given Game-Turn** ..."
>
> **[56.24]** "... this would subtract 300 tons from the available tonnage **for that Game-Turn**."

Four sentences, one of them a worked example with a number in it. The [56.4] chart is indexed *by
month* — that is what "Axis **Monthly** Shipping Table" means, it selects the ROW — but the
tonnage the row yields is a **per-Game-Turn** allowance.

### What the engine does

`game/scenario.py::_campaign_convoys` rolls `_campaign_axis_tonnage` **once per calendar month**
(`if not calendar.is_month_start(gt): continue`) and splits that single roll across the month's
Game-Turns (`per = month_tons // len(weeks)`).

| | tons, GT1-111 |
|---|---:|
| [56.21] licensed, die minimum | 1,550,000 |
| [56.21] licensed, expected | 2,038,000 |
| [56.21] licensed, die maximum | 2,544,000 |
| **engine schedules (seed 1941)** | **507,000** |
| **share of licence** | **24.9%** |

### The corroboration that settles it

The Axis actually shipped roughly **2.1 million tons** to North Africa across the campaign. The
per-Game-Turn reading lands on 1.55-2.54 million; the monthly reading lands on 0.5 million. Rule
56.2 says in its own voice that the rules "reflect the arrival of Axis supplies **as they actually
occurred**". **The per-Game-Turn reading is the one the designer calibrated against history.** This
is not interpretation — it is arithmetic against the data the chart was built from.

### Fix

Roll `_campaign_axis_tonnage` **per Game-Turn** in `_campaign_convoys`, each Game-Turn getting its
own full allowance. Cite [56.21] + the worked example. **Expect the [55.3] quay to start binding
hard**: Benghazi passes at most 7,500 t a Game-Turn (2,500 x 3 OpStages) out of a ~18,500-t
sailing, so ~60% of every sailing would expire unshipped under [56.27]. **That is the correct
picture, and it is the first thing in this chain that would give Malta something real to bite** —
once the quay is the constraint, tonnage denied at sea is tonnage that never queues.

---

## STAGE 1b — WHAT IS IN IT. **THE OASIS SENTINEL POISONS THE [56.22] CONVOY SPLIT.**

**This is the largest single defect in the audit and it is a five-line bug.**

`campaign_policy.convoy_plan_doctrine` implements [56.22] soundly on paper: convert every larder to
**tonnage** on the [54.5] chart (the book's own common unit), then allot each commodity a share
proportional to what the *other* larders hold, so "a commodity the army is out of is the one every
other commodity's abundance votes for". Correct doctrine. But it counts **every** `SupplyUnit` on
the side:

```python
for su in state.supplies:
    if su.side == side and not su.is_dummy:
        for c in stock:
            stock[c] += getattr(su, c.lower())
```

and rule **52.3**'s oases (`game/wells.py:143`, committed cd233ac) each hold
`UNLIMITED_WELL = _UNLIMITED // 8 = 125,000,000` **Stores** Points. Three oases —
Siwa, Jalo, Giarabub — put **375,000,000 Stores Points** on the Axis books. A Stores Point weighs
one ton, so the quartermaster looks at his larder and sees **375 million tons of food**, concludes
the army will never want for stores again, and ships the flagged 10% floor. Forever.

**Proven arithmetically against the measurement.** Feeding the campaign's own end-state larder
(Fuel 153,987 / Ammo 66,828 / Stores 375,032,246) back through the doctrine:

| | Fuel | Ammo | Stores |
|---|---:|---:|---:|
| **predicted** share of every sailing | 45.00% | 44.98% | **10.03%** (the floor) |
| **measured** share, all 110 sailings | 45.02% | 44.97% | **10.01%** |

Two decimal places. There is no doubt about the mechanism — and **the split is identical on both
measured seeds, to two decimals**, because 375 million tons swamps every real quantity in the
comparison so completely that the dice cannot move it:

| | Fuel | Ammo | Stores |
|---|---:|---:|---:|
| seed 1941, 110 sailings | 45.02% | 44.97% | 10.01% |
| seed 7, 110 sailings | 45.02% | 44.97% | 10.01% |

A supply doctrine whose output is bit-identical across two campaigns that differ in every battle is
not making a decision. It is reading a sentinel.

**Measured consequence.** Over the war the Axis planned **1,825,078 Fuel Points** (against a
whole-army maximum burn of 1,866 a Game-Turn, i.e. ~207,000 for the entire war if every unit
sprinted every stage) and **50,730 Stores Points** (against a requirement of 260,000+). He shipped
**nine times his lifetime fuel need and a fifth of his food.**

### Fix

`convoy_plan_doctrine` must tally only **finite** stock. The repo already knows how to make this
distinction and makes it two modules away: `relay._is_faucet` / `_relay_source` separate "a
bottomless source" from "a finite depot whose stock belongs to somebody". Apply the same test
here — exclude `base=True` wells and rule-57 strategic bases from the larder count. No rule
changes; this is the [56.22] decision the book explicitly hands to the player, and the player
should not be reading an oasis as a granary.

**Audit every other consumer of `state.supplies` for the same sentinel leak.** The unlimited
sentinel is a legitimate device, but any code that *sums* or *compares* larders will be swamped by
it. This one cost the Axis his bread for 111 Game-Turns and nobody noticed, because the symptom
appeared 3 stages downstream as "the Axis lands twelve times what he burns".

---

## STAGE 2 — WHAT LANDS. FAITHFUL, WITH ONE BOOK CONTRADICTION FLAGGED.

`supply.port_tonnage_budget(port) = ceil(cap_tons * eff / max_eff)` reproduces the rulebook's own
Benghazi worked example exactly (`ceil(2500 * 1/3) = 834`). `engine._unload_convoys` runs **one
shared tonnage budget per port per Operations Stage** across all commodities, apportioning
proportionally when a manifest outweighs the remaining budget; per-commodity sub-caps are
`_UNLIMITED` for campaign ports. **The per-commodity-instead-of-shared gate bug has stayed
fixed** — verified by reading `_unload_convoys`, and confirmed by measurement: no quay beat ever
exceeded its charted budget, and Benghazi sat *at* its 2,500-t cap in **94 of 230** beats (41%)
even at the current 25% shipping rate.

The [55.3] tonnage column was re-read off the scan (PDF p.110, chart page 15) and matches
`data/logistics_rates.json` cell for cell: Tripoli 15,000 / Bizerta 3,333 / Alexandria 15,000 /
Tobruk 1,700 / Benghazi 2,500 / Mersa Matruh 250 / Bardia 400 / Sollum 250 / Derna 300 / all
others 100.

### OWNER RULING NEEDED (3x on every harbour in the game)

The book contradicts itself, in the 54.17 class:

* **[55.14]** (PDF p.74, book p.23): "Example: **Benghazi has a supply tonnage capacity of 2500
  tons per OpStage.**"
* **[55.3] chart legend** (PDF p.110): "**Maximum Tonnage:** The total tonnage of supplies that
  may be shipped in and/or out **in one Operations Stage.**"
* **[55.16]** (PDF p.74): "**A port's capacity applies to *all* shipments received in a Game-Turn
  (including OpStages)**, except as stated in Case 55.15."

Two witnesses say per-OpStage; one says per-Game-Turn. The engine follows the two, which is what
it should do. **Recommendation: keep the per-OpStage reading** — the chart legend is the chart's
own definition of its own column, and 55.16 sits in a case about *which phases* a port may receive
in, a different question. But it is a 3x on the throughput of every harbour in the game and the
owner should rule on it, especially in combination with the Stage-1a fix, which is what will make
the quay binding.

---

## STAGE 3 — THE TONNAGE-TO-POINTS CONVERSION. **CLEAN — AND IT IS WHERE THE LEVERAGE LIVES.**

[54.5] read directly off the scan (PDF p.110):

| One Point of | Book | `supply.TONS_PER_POINT` | Independent cross-check |
|---|---|---|---|
| Ammo | 4 | 4.0 | [50.11] ~4 tons |
| Fuel | 1/8 | 0.125 | [49.11] "250 pounds or 35 gallons" = 1/8 short ton |
| Stores | 1 | 1.0 | [51.15] "Each Stores Point weighs one ton" |
| Water | 1/6 | 1/6 | ~333 lb, ~40 gallons |

Directions verified: `tons_to_points(t, c) = floor(t / TONS_PER_POINT[c])` at the [56.22] planning
edge; `points_to_tons(p, c) = ceil(p * TONS_PER_POINT[c])` at the [55.14] quay. Both correct, and
the floor/ceil pair errs against the shipper, which is the right way to be wrong.

**No fix needed — but the finding is that this chart is a 32:1 amplifier.** One ton of freight
becomes **8 Fuel Points** or **0.25 Ammunition Points**. The number of *Points* a faucet produces
is therefore almost entirely a function of the commodity split, not of the tonnage. **Every split
decision in the engine must be read in tons and audited for what it does in Points.** There are
two, and both matter:

* the [56.22] convoy split (`convoy_plan_doctrine`) — sound doctrine, **poisoned input** (Stage 1b);
* the lorry's load mix (`relay._TRUCK_LOAD_MIX`) — a flagged constant with no chart behind it
  (Stage 5b).

---

## STAGE 4 — WHAT EVAPORATES. FAITHFUL. IT IS THE SYMPTOM, NOT THE DISEASE.

**[49.3], verbatim:** "During the Stores Expenditure Stage of each game-turn, each Player reduces
all fuel levels on the game-map (not in convoys at sea) by six percent (6%), rounded down. In
addition, if the weather for an operations stage is 'hot weather', an additional reduction of five
per-cent (5%) is taken as soon as the hot weather is determined." **[52.44]:** water, except in
wells and pipelines, likewise. **[29.34]:** the hot 5% "includes water and fuel in dumps as well as
in trucks".

`engine._evaporate`, driven from `_stores_setup` (once per Game-Turn, `engine.py:179`) and
`_water_body` (once per Operations Stage, `engine.py:188`):

* 6% **once per Game-Turn** — **measured directly: a probe dump takes exactly one evaporation hit
  per Game-Turn across the whole campaign. There is no 3x error here.**
* +5% per hot Operations Stage, as a separate call — correct;
* Fuel and Water, in **dumps and trucks** — correct (29.34);
* wells and pipelines exempt via `base=True` — correct (52.44);
* sea convoys untouched — correct.

**Measured: 2,236,633 Fuel Points evaporated from dumps + 55,934 from trucks = 2,292,567, which is
76% of all the fuel landed by both sides in the entire war.** That number is not evidence of a
bug. A 6%/Game-Turn geometric drain on a stock with inflow `I` and no other outlet settles at
`stock = I/0.06`; evaporation dominating is precisely what a blocked outlet looks like from the
outside. **Fixing evaporation would only raise the pile.**

**Two gaps, both flagged, neither causal:**

1. **[49.3]'s Commonwealth exception is transcribed but unread.** "from Sept., 1940 until the last
   Game-Turn (inclusive) in August, 1941, the Commonwealth spillage and evaporation rate is nine
   percent (9%) per Game-turn" — the British petrol tins before the jerrican. The value sits in
   `data/logistics_rates.json` as `commonwealth_penalty_percent_sept1940_to_aug1941: 9` and
   **nothing reads it**. Fix: a side-and-date-conditioned rate in `_evaporate`. Expect little
   behavioural change (the CW fuel stock is itself far beyond anything it can burn) — do it
   anyway, because it is a printed number.
2. **The rule-57 Cairo base is exempted from evaporation** — `base=True` covers both wells and the
   strategic base, and 49.3 grants no exemption to a city depot ("regardless of where it is
   kept"). Harmless today because the base is bottomless, but it is an unflagged deviation riding
   on a flag that means something else.

---

## STAGE 5 — WHAT THE ARMY EATS. RATES FAITHFUL. ARMY NOT FED.

### The rates, checked against the charts

| Rule | Book | Engine (`game/supply.py`) | Verdict |
|---|---|---|---|
| [49.13] | Fuel = consumption rate x ceil(CP/5) x **TOE Strength Points**, movement only; foot/camel/motorcycle nil [49.12] | `fuel_cost = fuel_rate(u) * ceil(cp/5) * max(1, u.strength)`, per-model [4.47-4.49] rates on `Unit.fuel_rate` | **FAITHFUL** |
| [49.14] | capacity = CPA x 1/5 x rate, "exactly sufficient to allow all its CPA to be expended" | `fuel_capacity = fuel_cost(u, u.cpa)` | FAITHFUL |
| [50.14]/[50.2] | rate x TOE committed: barrage 4, anti-armor 3, close assault 2 (**re-verified on the scan, PDF p.108**) | `AMMO_RATE` read from that chart | FAITHFUL |
| [51.11]/[51.13] | 4 Stores per TOE per Game-Turn; HQ/engineer 1 flat | `stores_cost` | FAITHFUL |
| [52.41]/[52.42]/[29.35] | 1 Water flat per infantry unit per OpStage; 1 per TOE for vehicles/guns/trucks; doubled hot | `water_cost` | FAITHFUL |

**No number in this table should be touched.** (Note: the "ENGINE PROXY ... no x-TOE multiply"
comment in `data/logistics_rates.json:fuel_consumption` is **stale** — the 49.13 law is fully
present in `fuel_cost`. Worth a docs pass, separately.)

### The denominator nobody had written down

The Game-Turn-1 Axis army is **96 land units / 586 TOE Strength Points** (135 living pieces
including SGSUs; 149 at the end). Its *entire licensed appetite*, if every unit ate its full ration
and moved its full CPA every stage:

| Commodity | Points/Game-Turn | Tons/Game-Turn [54.5] |
|---|---:|---:|
| Stores (51.11, 4/TOE/GT) | 2,344 | 2,344 |
| Water (52.41/52.42, x3 stages) | 684 | 114 |
| Fuel (49.13, whole army at full CPA, x3 stages) | 1,866 | 233 |
| Ammo (50.14, whole army firing once) | 1,316 | 5,264 |
| **absolute theoretical maximum** | | **~7,955 t/GT** |
| **realistic (stores + water + some fuel/ammo)** | | **~2,500-3,000 t/GT** |

Against a **[56.5] licence of 13,500 - 50,000 tons per Game-Turn.**

**THE BOOK GIVES THE AXIS BETWEEN FIVE AND FIFTEEN TIMES WHAT HIS ARMY CAN EAT, AT THE QUAY, ON
THE BOOK'S OWN NUMBERS. THAT IS NOT A BUG — IT IS THE DESERT WAR.** The Axis problem was never
Italy's ability to load ships; it was Benghazi's cranes and 1,500 km of coast road. The book models
exactly that, with the [55.3] port caps and the [54.2] truck park, and rule 53.0 states the design
intent in one sentence:

> **"Trucks are the game; without a well-organized and efficient truck convoy system your entire
> military effort will fall apart."**

**Hypothesis (f) is confirmed, and the binding constraint is the lorry, not the quay.**

### 5b. THE LAST MILE, MEASURED

The engine fields **215 Axis Truck Points**. The charts print **780** at Game-Turn 1:
[60.33] second/third-line **420** (25/140/40 Tripoli + 30/100/25 anywhere in Libya + 10/50/0 air
facility) and **[60.31] first-line 360** (55 L / 260 M / 45 H — transcribed cell by cell off the
scan in `scratchpad/port/phase4-first-line-trucks.md` and never seeded). **The Axis hauls his war
on 28% of his charted motor transport; the general-freight pool that actually runs the Benghazi
road is 155 Truck Points of a charted 420.**

Measured over 111 Game-Turns, that pool lifted and delivered:

| | loaded (Points) | delivered forward | lost in transit |
|---|---:|---:|---:|
| Fuel | 1,265,090 | 941,255 | **323,835 (26%)** |
| Ammo | 27,555 | 27,555 | 0 |
| Stores | 57,093 | 57,093 | 0 |

The 26% fuel loss in transit is [49.18] working exactly as written — *"It is possible for a truck
to consume half of its cargo getting from a port to a forward area"* — plus 29.34 evaporation off
the lorry. Faithful, and a nice confirmation the haul model has teeth.

**But look at the Stores row against the demand: 57,093 Points delivered over 111 Game-Turns is
514 a Game-Turn, against 2,344 needed at Game-Turn 1 and more later. 22%.** And note that
57,093 delivered ~= 56,214 landed: **the lorries move essentially every Stores Point that arrives.
The Stores famine is not a haulage failure — it is the Stage-1b convoy-split bug. The haulage
failure is what stops the fix from being enough on its own.**

Three causes of the haulage shortfall, in descending magnitude:

1. **[53.11] First Line Trucks do not exist.** Supply is drawn strictly in-hex
   (`supply.in_hex_draw`, faithful to 49.15/50.15/51.15) — so **a unit not physically stacked on a
   dump eats nothing, ever.** The book's answer is 53.14's three-tier chain whose last rung is the
   parent unit's own attached lorries. Without it, the engine's **20 non-well Axis dumps** must
   each be *stood on* to be eaten, by an army of 135-149 pieces spread over 46+ hexes. The
   allotment is **already transcribed and waiting** (`scratchpad/port/phase4-first-line-trucks.md`,
   slices S0/S1/S2 of `phase4-in-hex-supply-design.md`). **This is the highest-value unbuilt thing
   in the port.**
2. **[60.33]'s Tripoli row — 205 of 420 second/third-line Truck Points — is not on the board.**
   Already flagged honestly in `_campaign_axis_trucks`: Tripoli is the off-map box and there is no
   truck-arrival scheduler ([4.43b] deferred). Defensible as written; it is nonetheless half the
   freight pool.
3. **`relay._TRUCK_LOAD_MIX = 60% fuel / 25% ammo / 15% stores`** — a **flagged policy constant,
   not a chart** — devotes most of the pipe to the commodity the army cannot burn and 15% to the
   one that is pure, unavoidable demand. Cheapest fix in the audit and not a rules change: what a
   lorry loads is the quartermaster's choice, and one who loaded by *what the army is short of*
   (the doctrine `convoy_plan_doctrine` already applies at sea, compared in tons — **once its
   input is fixed**) would multiply delivered Stores several-fold with no new lorries.

### 5c. THE SAME DISEASE ON THE COMMONWEALTH SIDE

The Commonwealth faucet is the Western Desert Railway and it is **faithful**: [54.32] rates it at
1,500 tons per Operations Stage, [54.33] allows one commodity at a time, [54.34] stands it down one
Operations Stage a month. `_campaign_rail_cargo` builds exactly that — 375 Ammunition, 12,000 Fuel,
1,500 Stores, i.e. 4,500 tons a Game-Turn — and 54.3 correctly exempts a train from the [55.14]
quay.

It produces the same flood from a correct chart, for the same reason: **1,500 tons declared as Fuel
is 12,000 Fuel Points**, against a Commonwealth army burning 73,587 Fuel Points in the entire war.
Measured: the CW landed **1,325,180 Fuel Points and 123,000 Stores**, ate **73,587 Fuel** and
**114,069 Stores**, and took **15,716 Stores shortfalls**. Note the shape is *different* from the
Axis's: the CW's Stores supply is roughly adequate (123,000 landed, 114,069 eaten) because a train
is not subject to the poisoned convoy split — **which is itself a clean natural experiment
confirming that Stage 1b, not Stage 5, is what starves the Axis.**

---

## CULPRITS, RANKED BY MAGNITUDE

| Rank | Finding | Magnitude | Class | Fix | Citation |
|---|---|---|---|---|---|
| **1** | **The [52.3] oasis `UNLIMITED_WELL` Stores sentinel is counted as real larder by `convoy_plan_doctrine`**, so every Axis sailing ships the 10% Stores floor and 90% fuel+ammo | Axis ships **9x his lifetime fuel need and 20% of his food**; explains the 12x directly | **BUG** (policy, not rules) | exclude `base=True` / unlimited sources from the larder tally, as `relay._is_faucet` already does; audit every other summation over `state.supplies` | [56.22]; `game/wells.py:143`; `game/campaign_policy.py:951` |
| **2** | The last mile: 215 of 780 charted Axis Truck Points, **no [53.11] first-line tier**, a 60/25/15 load mix | 22% of the Stores requirement reaches the front; **53% of Axis unit-Game-Turns take a stores shortfall** | 2 rule gaps + 1 policy constant | build the first-line tier (data already transcribed); seed the Tripoli row behind a truck-arrival path; re-derive the load mix from demand in tons | 53.0, 53.11, 53.14, 54.16, [60.31], [60.33] |
| **3** | The [56.5] roll is quartered across a month; the book grants it **per Game-Turn** | **4.0x under-ship** (507 kt vs 2,038 kt) | defect | roll per Game-Turn in `_campaign_convoys` | [56.21] + worked example, [56.22], [56.24] — scan PDF p.75 |
| **4** | Genuinely faithful over-supply at the quay: the licence is 5-15x the army's maximum appetite | 5-15x | **NOT A DEFECT** | none — but **every balance reading must be taken forward of the quay, never at it** | [56.5], [55.3], 53.0 |
| 5 | The Axis Tobruk lane ships 680 t/GT outside the [56.5] allowance, straight to the front | ~75,000 t over the war, but landed *at the front* | flagged proxy | allocate it from the allowance under [56.25] | [56.12], [56.25] |
| 6 | [49.3]'s 9% Commonwealth evaporation rate (Sept 1940 - Aug 1941) transcribed but unread | +50% CW leakage for ~48 Game-Turns | rule gap | date-and-side condition in `_evaporate` | [49.3] |
| 7 | 55.14 + chart legend vs 55.16: port budget per OpStage or per Game-Turn? | **3x on every harbour** | **book contradiction — OWNER RULING NEEDED** | recommend keeping per-OpStage (2 witnesses to 1) | scan PDF p.74 + p.110 |
| 8 | The rule-57 Cairo base rides the wells' evaporation exemption | nil today (base is bottomless) | unflagged deviation | separate the flags, or comment it | [49.3], [52.44] |

---

## OPEN RULINGS FOR THE OWNER

**OWNER RULING NEEDED — [55.14]/[55.3-legend] vs [55.16]: is a port's tonnage capacity per
Operations Stage or per Game-Turn?** Scan pages: PDF 74 (book 23) for 55.14 and 55.16, PDF 110
(chart page 15) for the legend. Two witnesses print "in one Operations Stage", including the
chart's own definition of its own column; 55.16 says "applies to all shipments received in a
Game-Turn (including OpStages)". The engine follows the majority and nothing is unseeded — but the
factor is 3x on every harbour, and it becomes load-bearing the moment the Stage-1a shipping fix
lands and the quay starts binding. **Not decided here.**

*(Two lesser judgement calls are recorded in place rather than raised: the [56.12] six-lane
allocation, and whether the Tobruk lane's 680 t/GT should be drawn from the [56.5] allowance. Both
are implementation shape, not contradictions in the book.)*

---

## WHAT THIS MEANS FOR MALTA, AND FOR EVERY BALANCE NUMBER TAKEN SO FAR

Gate 5.6's verdict — *"sinking 7% of the convoys of an army that eats 8% of what arrives cannot
change a campaign"* — is right, and this audit says why in one sentence: **the army's ration is set
by a poisoned convoy split and 155 lorries, and neither number can see the sea.**

That gives a clean order of work, and it is the reverse of the intuitive one:

1. **Fix the convoy split (rank 1).** Cheapest, largest, and it is a bug rather than a rule
   change. It should move the Axis from 20% to ~100% of his Stores requirement *shipped* — and
   then the truck pool becomes the visible constraint instead of hiding behind the split.
2. **Build the last mile (rank 2)** — [53.11] first-line trucks above all, whose data is already
   transcribed and sitting in `scratchpad/port/`. Until the army can eat its licensed ration,
   every measurement in this project is measuring the lorry pool.
3. **Then fix the shipping (rank 3)**, which will immediately make the [55.3] quay bind, because a
   per-Game-Turn allowance is ~2.5x what Benghazi can pass in a Game-Turn.
4. **Then re-measure Malta.** With the quay binding and the chain tight, tonnage denied at sea is
   tonnage that never queues — and the island finally has a denominator worth attacking.

Doing (3) first would land a 4x larger faucet on a chain that cannot move it, and the only
measurable consequence would be a larger evaporation figure.

---

## APPENDIX A — HOW THIS WAS MEASURED, AND ONE TRAP IN THE INSTRUMENT

`scratchpad/faucet_audit.py` folds one campaign and tallies the event log. It changes nothing; it
runs the stock `campaign(seed)` against `CampaignAxisPolicy` / `CampaignCommonwealthPolicy`.

**THE TRAP, AND IT MATTERS FOR EVERY EARLIER SUPPLY NUMBER IN THIS PROJECT.** There are two
terminal consumption events, not one:

* `SUPPLY_CONSUMED` — drawn off a **dump**;
* `UNIT_SUPPLY_CONSUMED` — drawn off the unit's **own** pool (the 49.14 fuel tank, the 50.0 ammo
  load), introduced by the Phase-4 in-hex work;

and one that is **not** a burn at all:

* `UNIT_REFILLED` — a dump-to-unit *transfer* (48 V.C.6). Counting it as consumption double-counts;
  ignoring `UNIT_SUPPLY_CONSUMED` under-counts.

True burn = `SUPPLY_CONSUMED + UNIT_SUPPLY_CONSUMED`. The "133,470 points consumed" figure that
opened this block was `SUPPLY_CONSUMED` alone (`scratchpad/gate56_convoy_share.py`); the corrected
Axis figure is **149,262**, and the headline ratio moves from 13.3x to **12.3x**. No conclusion
changes, but the next instrument should count both.

**Memory note.** A 111-Game-Turn campaign holds ~282,000 Events plus the folded state; four in
parallel OOM'd a 16 GB box. The driver is sequential by design and flushes each seed as it lands.

## APPENDIX B — SCAN PAGES READ WITH EYES FOR THIS AUDIT

| PDF page | Book page | What it settled |
|---|---|---|
| 74 | 23 | [55.14] "2500 tons **per OpStage**"; [55.16] "applies to *all* shipments received in a Game-Turn"; [54.16] the one-OpStage-truck-ride dump network |
| 75 | 24 | **[56.21] + the worked example + [56.22] + [56.24]: the [56.5] tonnage is PER GAME-TURN** |
| 108 | 13 | [50.2] Ammunition Consumption Rates: barrage 4, anti-armor 3, close assault 2 — matches `data/logistics_rates.json` |
| 110 | 15 | **[54.5] Equivalent Weights** (Ammo 4 / Fuel 1/8 / Stores 1 / Water 1/6) and the **[55.3] Port Capacity chart + legend** ("Maximum Tonnage: ... in one Operations Stage") |

## APPENDIX C — REPLICATION ACROSS SEEDS

Every headline number reproduces. Two full campaigns, 111 Game-Turns each, different battles,
different weather, same disease:

| | seed 1941 | seed 7 |
|---|---:|---:|
| winner | AXIS | AXIS |
| Axis tonnage shipped, share of the [56.21] licence | 24.9% | 24.2% |
| convoy split (fuel / ammo / stores, by tonnage) | 45.02 / 44.97 / **10.01** | 45.02 / 44.97 / **10.01** |
| Fuel landed / Fuel burned | **87.5x** | **85.0x** |
| Stores landed / Stores burned | 2.35x | 2.24x |
| all commodities landed / burned | **12.3x** | **11.1x** |
| Fuel evaporated (dumps + trucks) | 2,292,567 | 2,221,566 |
| Axis `STORES_SHORTFALL` events | 8,362 | 8,593 |
| Axis unit-Game-Turns with no stores | **~53%** | **~55%** |
| Benghazi quay beats at the 2,500 t cap | 94 / 230 | 74 / 218 |
| Stores Points delivered forward by lorry | 57,093 | 59,169 |

## APPENDIX D — THE RAW LEDGER, SEED 1941, GT1-111

```
events 281,906   winner AXIS   Axis living 135 -> 149   CW living 46 -> 289

SHIPPED   Axis 582,429 t on 221 convoys   (allowance lane 507,000 t + Tobruk lane 75,480 t)
          [56.21] licence 1,550,000 - 2,544,000 t     -> engine ships 24.9%
PLANNED   Fuel 1,825,078 pts / Ammo 56,970 / Stores 50,730     = 45.0 / 45.0 / 10.0 % by tonnage
LANDED    Axis  Fuel 1,702,083  Ammo 66,507  Stores 56,214  Water 9,047   (536,510 t)
          CW    Fuel 1,325,180  Ammo 41,625  Stores 123,000            (455,148 t)
QUAY      Benghazi 230 beats, 94 at the 2,500 t cap;  Tobruk 151 beats, 0 at its 680 t cap
EVAPORATED  dumps Fuel 2,236,633  Water 7,622   trucks Fuel 55,934
            cadence probe: exactly 1 hit per Game-Turn
BURNED    Axis  dump Stores 23,893 Water 105,034 Fuel 13,162 Ammo 134
                unit Fuel 6,281 Ammo 758                       TOTAL 149,262
          CW    dump Stores 114,069 Water 204,025 Fuel 21,182 Ammo 142
                unit Fuel 52,405 Ammo 1,432                    TOTAL 393,255
SHORTFALL Axis stores 8,362  water 10,971      CW stores 15,716  water 5,675
TRUCKS    Axis loaded Fuel 1,265,090 Ammo 27,555 Stores 57,093
               delivered Fuel 941,255 Ammo 27,555 Stores 57,093   (26% of fuel lost in transit, 49.18)
```
