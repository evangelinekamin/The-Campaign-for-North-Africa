# THE [4.44B] COMMONWEALTH COUNTER DEBT — PAID, AND MEASURED

**2026-08-04.** 90 of the 91 counters the survey (`cw-counters.md`) found missing are seeded; the
91st (`200 Gds`) is absent because the book prints no arrival for it. Six transcription errors
repaired beside them. Full suite green (1722 passed, 2 skipped). Both benchmark determinism
signatures **byte-identical** — `rommel e1d1fa771ce3`, `siege 19693b23b988` — because the Desert Fox
scenarios read neither campaign OOB file and the eighteen new `[4.46a]` rows are additive.

---

## 1. THE PREDICTION, SCORED

Written before anything was built (`cw-counters-prediction.md`). Recipe for every number below:
`scenario.campaign(seed)` run whole (111 Game-Turns) with `CampaignAxisPolicy` /
`CampaignCommonwealthPolicy`, seeds 42 / 1941 / 7 / 2026, control tree = a `git worktree` at the
parent commit built OUTSIDE the repo. Driver: `scratchpad/data-debt/ab_4_44b.py`.

| seed | control (Axis-CW VP) | this tree | grade |
|---|---|---|---|
| 42   | 1070-20 | 1006-10 | Axis Smashing, both |
| 1941 | 772-20  | 738-20  | Axis Smashing, both |
| 7    | 475-0   | 1083-10 | Axis Smashing, both |
| 2026 | 412-20  | 1259-10 | Axis Smashing, both |

| | control | this tree |
|---|---|---|
| Commonwealth GT1 combat units the [60.41] truck pool splits over | 27 | **57** |
| ...Truck Points each (the pool is fixed at 177) | 6.556 | **3.105** |
| Commonwealth WATERLESS_MOVE refusals (42/1941/7/2026) | 767 / 547 / 0 / 2331 | 366 / 490 / 926 / 666 |
| Axis high-water mark, axial r (42/1941/7/2026) | 133 / 133 / 133 / 133 | 133 / 134 / 133 / **121** |
| Commonwealth combat units alive at GT111 | 185 / 240 / 180 / 220 | 289 / 282 / 187 / 279 |
| Axis combat units alive at GT111 | 108 / 96 / 112 / 94 | 103 / 98 / 97 / 91 |

- **P1 — winner and 64.76 grade unchanged. HELD.** Axis Smashing Victory on all four seeds of both
  trees. Nothing about the scoreboard's verdict moved.
- **P2 — Commonwealth VP change small and NOT reliably positive. HELD.** −10, 0, +10, −10. It is
  the S7-stores result again: random in sign, at the granularity of a single 10-point city.
- **P3 — the dilution effects are the measurable ones. HALF HELD, HALF FAILED, and the failure is
  the more interesting half.**
  - *First-line trucks: HELD exactly.* [60.41] charts a fixed 177 Truck Points and
    `oob._seed_first_line` splits them evenly over the Game-Turn-1 combat muster. 30 more counters
    on that muster cut every Commonwealth unit's carrying ceiling by 53%, from 6.556 Truck Points
    to 3.105. Nothing in the book changed; the divisor did. **This is a real, unpaid consequence
    and it is named as debt in §4.**
  - *Thirst: FAILED.* I predicted the Commonwealth's WATERLESS_MOVE refusals would rise roughly in
    proportion to the extra mouths. They are random in sign (−401, −57, +926, −1665) and the mean
    FALLS, 911 → 612. A thirsty army that is not marching is not refused a march.
- **P4 — the Axis high-water mark barely moves. HELD.** 133 on every control seed; 133 / 134 / 133
  / 121 here. One seed (2026) culminates twelve hexes short of Alexandria, three do not move at
  all. The rout is still governed upstream.
- **P5 — signatures move. HELD for the campaign, and BETTER THAN PREDICTED for the benchmarks:**
  both `rommels_arrival` and `siege_of_tobruk` are byte-identical, so `tests/baselines.py` needs no
  new hash.

## 2. THE THING THE SCOREBOARD CANNOT SEE — and it is the finding

The prediction's own "surprise watch" said the honest way this debt could matter was an effect in
the campaign that the end-of-game scoreboard is structurally unable to show. That is exactly what
happened, and it is much larger than anything in §1.

**THE EIGHTH ARMY KEEPS ITS OWN RAILHEAD NOW.** Panel 1..24 at Game-Turn 30 (the same panel
`tests/test_campaign_claim.py` folds; control arm re-run and it reproduces that test's recorded
column exactly, which is what licenses the comparison):

|  | control | this tree |
|---|---|---|
| the Axis stands on Mersa Matruh | 18/24 | **4/24** |
| the Commonwealth stands on Mersa Matruh | 3/24 | **20/24** |
| the Commonwealth BANKS Mersa Matruh (64.73) | 3/24 | **20/24** |
| the Commonwealth stands on Sidi Barrani | 18/24 | **23/24** |
| the Axis stands on Sollum | 23/24 | 22/24 |
| the Axis stands on Bardia | 24/24 | 22/24 (hex still Control.AXIS on both misses) |
| the Axis stands on / banks Tobruk, banks Benghazi | 24/24 | 24/24 |

**The cause is one counter the chart prints and the engine did not carry.** [60.41] Commonwealth
Initial Deployment reads `D3714: Matruh Garrison (I; Att: 1 Essex 23/70; 1st Durham Lt Inf 23/70;
1st South Staffordshires`. The 1st South Staffordshires was one of the 91. At CAMPAIGN_SEED=23,
Game-Turn 12, `garrison_units(fin, ALLIED)` is exactly `{'1-SoStff'}` — the counter this pass
seeded is the counter banking the city — Mersa Matruh goes AXIS → ALLIED, and the Commonwealth rail
lane's railhead goes `AL-Alexandria` → `AL-Stage-Matruh`, undoing the deepest retraction
`tests/test_campaign_concentration.py` had ever recorded.

**AND THE AXIS RAILWAY TURNS OUT TO HAVE BEEN A CAPTURED RAILWAY.** Seeds 1-40 to Game-Turn 6, both
trees (control arm reproduces `tests/test_rail_control.py`'s own recorded entry exactly):

|  | control | this tree |
|---|---|---|
| seeds where the Axis activates rolling stock ([54.43]) | 29 | 7 |
| ...of those, paid for by **AL-Stage-Matruh or AL-Stage-ElDaba** (Commonwealth stores, overrun) | **26** | **0** |
| ...paid for by an Axis dump of his own | 3 | 7 |

The 29 → 7 collapse is not rule 54.4 becoming less reachable. It is the rule finally being asked of
the Axis's own logistics instead of a windfall, because the Eighth Army no longer loses the depots
that were paying for his trains.

**Read together with §1 this is the whole result:** the debt is worth roughly nothing on the 64.73
scoreboard and a great deal on the board. The scoreboard is an end-of-game supplied-occupier test
and by Game-Turn 111 the Axis is at Alexandria on every seed either way; what changed is the first
half of the war, which the scoreboard never looks at.

## 3. WHAT WAS SEEDED

**90 counters, nothing invented.** 39 at Arrives `D` into `data/oob_campaign_extra.json`, 51
rule-20 arrivals into `data/reinforcements_campaign.json`. Eighteen `[4.46a]` stat rows added to
`data/unit_stats.json` (`hq_b/c/d/e/f`, `infantry_k/m/n/t/v/w`, `artillery_y`,
`antitank_bb/cc/dd`, `light_aa_ff`, `recon_ll/ss`), every one a row the chart prints. Two
Maximum-TOE cells transcribed onto pre-existing rows (`g` 10, `ee` 6). One engine change:
`oob._make_unit` reads a per-record `toe`, the chart's "TOE & Weapon System(s)" arrival strength,
so `U@2` finally means understrength-at-two against the ID Code's ceiling rather than full strength.

**Six repairs:** the Royal Yugoslav Guards' ID Code `f` → `t` (600-dpi crop; `f` is a Headquarters
row and `t` an infantry battalion); the 10th Indian Division's `97/157/164 Fld` artillery regiments,
seeded as anonymous infantry; `1 Fslrs` (ID `ff`, Light Anti-air) and `23 NA` (ID `cc`, anti-tank),
both seeded as infantry; the 22nd Armoured Brigade's arrival, chart `3/20` against the engine's
Game-Turn 51; and the three Commonwealth construction companies, charted `1/32`, `3/50` and `1/50`
against a flagged Game-Turn-6 proxy.

**Absent, with the reason recorded:** `200 Gds`. Its sheet is prose and prints "In January 1942, it
became the 200th Guards Brigade" — a month, not an Arrives cell. Seeding it means inventing a swap
turn. Owner ruling.

## 4. THE DEBT THIS PASS LEAVES, NAMED

1. **THE FIRST-LINE TRUCK POOL IS NOT A PER-UNIT ENTITLEMENT AND IS NOW SPLIT 57 WAYS.** [60.41]
   charts 177 Truck Points for the Western Desert Force and `_seed_first_line` divides them evenly
   — our assignment of a free choice ([59.42] "may be freely divided"), and it was written when the
   muster was 27 counters. The per-unit ceiling fell 6.556 → 3.105 Truck Points. The book lists the
   allotment BY HEX; a faithful per-hex placement against the [60.41] setup lines is now
   reconstructible for the counters this pass seeds, because it seeds them at [60.41]'s own hexes.
   That is the single largest unpaid consequence of this slice.
2. **The armoured brigades are still aggregated.** `23/24/8/9 Armd Bde` are one counter apiece for
   two or three charted tank regiments (11 regiments → 4 counters). De-aggregating restores the
   per-regiment Grant/Crusader/Valentine mixes; it is a structural change to how a brigade is
   modelled and deserves its own measured slice. Deliberately out of scope here.
3. **The over-seeding is untouched.** The 161st Indian Motor Bde carries three battalions where the
   chart prints two; the 10th Indian's 20th Bde Group two where the chart prints one and its own
   note b says it is short on purpose. Removing a seeded counter is a different risk from adding a
   charted one.

   **CORRECTED AND COMPLETED 2026-08-04 (this paragraph named two of four removals, and filed them
   under the wrong heading).** Exactly four counter names disappear in this pass, and *none* of them
   is an over-seeding deletion — every one is a 1:1 ROLE REPAIR whose slot became the charted unit
   it was always standing in for:

   | removed | became | the chart cell that forced it |
   |---|---|---|
   | `20 In Bde Grp III` | `97 Fld [20 In]` | 10th Indian, ID `x` — Artillery Bn-Eq, seeded infantry |
   | `21 In Bde Grp III` | `157 Fld [21 In]` | same |
   | `25 In Bde Grp III` | `164 Fld [25 In]` | same |
   | `2 Free French Bde III` | `23 NA AT Coy [2 FF]` | ID `cc` — Anti-tank Company-Eq, played as a third rifle battalion |

   Net record count 560 → 611 (+51 reinforcements), plus 39 deployed-at-GT1 records in
   `oob_campaign_extra.json` = the +90 counters the gate measured. **The over-seeding named above is
   therefore still untouched and still real**: the 161st Indian Motor Bde keeps three battalions
   against the chart's two, and the 20th Brigade Group keeps two against the chart's one (its third
   slot became `97 Fld`, which fixes the role but not the count).
4. **`recon` (ID `pp`) carries `anti_armor: 2` and the chart prints a dash there.** One value copied
   into two fields — the signature of a column slip, `armor_protection` and `anti_armor` both 2.
   The two rows added here (`recon_ll`, `recon_ss`) transcribe the dash, so the file is now visibly
   inconsistent ON PURPOSE. Fix it by deleting the 2, in a slice that measures the result.
5. **A `b`/`c`/`d` Headquarters' one tank or three artillery TOE Strength Points are not modelled.**
   The chart's rating columns on those rows are all dashes, so nothing is invented by leaving them,
   but the 7th and 4th Armoured Brigade HQs are a tank point lighter than the chart and the 16th
   Infantry Brigade HQ carries no Barrage. [19.x] TOE assignment onto a Headquarters exists in this
   engine only for [19.8] ad hoc anti-tank.
6. **Rows `e`/`f` are seeded `is_combat: false`,** matching row `a`, although the chart gives them a
   defensive Close Assault of 1, an Anti-Armor rating and a Vulnerability. Promoting a Headquarters
   to a ZOC-exerting, city-banking combat unit is a ruling, not a transcription. Owner ruling.
7. **Arrival and ID-code divergences found but NOT repaired** (each is a counter that EXISTS, so it
   is a different class of defect from a missing one): `1 KRRC` is ID `n` and seeded `l`;
   `12 Lancers` is `ll` and seeded `pp`; `HQ 22 Armd Bde` is `d` and seeded `a`, its three regiments
   10 TOE and seeded 8; `102nd AT` arrives 1/45 and is seeded t43; `32 Army Tank Bde` arrives 1/51
   and is seeded t76; the 161st Indian's two battalions are `n` and seeded `l`; the 1st Free
   French's `1 Regt d'artillerie` is `y` with 4 × French 149mm and is seeded `x` with 25-pounders;
   the two remaining `2 Free French Bde` battalions stand for `5 Mrch`/`11 Mrch` at ID `s`, a row
   this file does not carry.
8. **[60.41] and [4.44B] disagree about ONE counter and the disagreement is recorded, not resolved:**
   [60.41] deploys "1st Coy French Motor Marines" at C3926 on Game-Turn 1; [4.44B] prints Arrives
   `3/65`. The Arrives column is followed.
9. **The [4.45] formation tree does not know these 90 counters.** `data/oob_organization_4_45.json`
   is keyed by counter string and none of the new names is in it, so they carry no `assigned_to`
   and their brigade HQs no `org_type`. [15.53] Organization Size cannot see the 7th Armoured
   Division's brigades. A small, purely-additive follow-up.
10. **`[60.41]` puts more Stacking Points on D3615 (8) than [8.37] allows a Rough hex (6).** [9.14]
    caps a hex "at the end of any Movement Segment", which a set-up is not — so the book is legal
    and this engine's at-rest invariant sweep, which runs at run start, is the stricter reader. The
    11th Indian Brigade stands on D3614 because of it. Teaching the sweep 9.14's own qualifier
    would put the brigade back where the book prints it.
11. **The untrained Morale Rating is not modelled.** Six of the sheets seeded here print a
    parenthesised morale — the 6th Australian arrives at −3, the 1st South African at −3, the Polish
    at −1 — which [17.32] In Training would lift. Untranscribed; the trained value is seeded, which
    is what every pre-existing Commonwealth counter in this OOB already does.

## 5. PROVENANCE

Every counter row was read off a 300-dpi `pdftoppm` render of its own page (600 dpi for the Royal
Yugoslav Guards ID glyph and the 22nd Armoured Brigade Arrives column, cropped and compared against
neighbouring glyphs). Charts: `[4.44B]` PDF p.116-132, `[4.46a]` p.133-134, `[60.41]` p.78, all in
`tmp/The Campaign for North Africa.pdf`. Builder: `scratchpad/data-debt/seed_4_44b.py`. Tests:
`tests/test_cw_oob_4_44b.py`.
