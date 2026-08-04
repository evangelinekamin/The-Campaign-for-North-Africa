"""THE ONE PLACE the benchmark determinism signatures are written down.

These two hashes used to be copy-pasted into six test files. When the dice moved they had to be
found and changed in six places, which is how a baseline quietly becomes folklore. They live here
now; every guard imports them.

WHAT A SIGNATURE IS. sha256(determinism_signature(events))[:12] for the scenario run at seed 42
with axis=allied=ScriptedPolicy(AXIS). It is a fingerprint of the ENTIRE event log. It proves
DETERMINISM -- the same seed replays byte-for-byte -- and nothing else. It is not a correctness
claim, and pinning it must never become a reason to avoid fixing a rule.

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED 2026-08-03 -- THREE DEFECTS AT THE CPA SEAM: [19.68]'s CP TO A DEAD PARENT, THE
ASSAULT'S WATER DRAWN BEFORE ITS AMMUNITION, AND [10.36] RETREATING A VEHICLE [52.51] FORBIDS TO
MOVE. BOTH BENCHMARK SIGNATURES ARE BYTE-IDENTICAL across all three: rommel e1d1fa771ce3, siege
19693b23b988, unchanged. THE CAMPAIGN MOVES.

    Recipe, as ever: scenario.campaign(seed, max_turns=12) via its OWN kwarg, CampaignAxisPolicy
    vs CampaignCommonwealthPolicy, sha256(determinism_signature(events))[:12].

        1    52a69aec9ddb  UNCHANGED          4    b85cb778bd22 -> ebb2ff193892
        7    ab81428240bb  UNCHANGED          1941 2ed7ca890183 -> f5159116d16f
        777  73e777a74972  UNCHANGED          2026 c4f172350b45 -> 02eb0ac927a8

    And the FULL 111-turn war, same policies, because two of the three defects are too rare to
    reach inside twelve Game-Turns:

        1    c1097eb4de68 -> d5c593370acd      4    94fac6b942bf -> f4f98d831216
        7    a6a2b58e0177 -> 35bd93c4c7d0      777  f013bf6cd331 -> 4df02a291a8b
        1941 8fcc60690e8d -> 0ac39dc31a3b      2026 7314c46127c0 -> 6345c68e599b

    The "before" column is git HEAD (2f41e4b) measured through a tree with the three new guards
    neutered AT THEIR OWN CALL SITES; that tree reproduced HEAD's own eight signatures exactly,
    which is what makes it a legitimate control.

THE BOOK, every string re-rendered at 300/400 dpi for this entry and read character by character.
NOTE FOR THE NEXT READER: in this PDF the second booklet's offset is FOLIO + 47, not the +51 that
has been passed around -- rule 52 is at PDF p.68 and that page prints its own folio 21. Main-booklet
pages do match (PDF index == folio). Also: the book MISPRINTS [19.67] -- it reads "that Parent
Formation may be rebuilt by or Reassignments", a word short, re-rendered twice at 400 dpi to be
sure. Not repaired, not relied on.

  1. [19.68] "Rebuilding units takes place in the Organization Phase only... For every two
     Replacement TOE Strength Points added to a unit, that unit (and its parent, if such is the
     situation) uses one Capability Point." (PDF p.30 = folio 30)
     [19.62] "Units that have been completely eliminated because of attrition on combat -- not
     breakdown (i.e., no TOE Strength Points remaining) may not be rebuilt."
     [19.63] "If a HQ unit (counter) is eliminated, it may not be rebuilt unless at least 50% of
     its assigned units still exist and are not attached to other units. In such case, two Infantry
     Replacement Points may be used to revive the HQ. Otherwise it is gone for good."
     [19.67] "The HQ unit for a Parent Formation is, for play purposes, its Cadre."
     [6.11] "Each unit has a Capability Point Allowance (CPA)." (PDF p.12 = folio 12)
  2. [52.42] "Each TOE Strength Point of Vehicle (Tank, Recce, Artillery, etc.) or Truck Point
     requires one Water Point each Operations Stage, if it uses any of its CPA." (PDF p.68)
  3. [10.36] "If, for any reason, a unit can neither Assault nor Hold Off an Enemy unit, that
     Friendly unit must Retreat three hexes (playing all CP's for such movement) and earn three
     Disorganization Points, in addition to any garnered by the retreat." (PDF p.18 = folio 18)
     [52.51] "Vehicles without water may not move or close assault offensively."
     [8.12] a forced Retreat "is considered involuntary movement... However, involuntary movement
     also requires expenditure of CP's and checks for Breakdown." (folio 13 col 3 -> folio 14 col 1)
     [15.82] "For each hex of mandated Retreat that units cannot or chooses not to Retreat those
     units suffer an additional 10% loss." (PDF p.24 = folio 24)

WHAT CHANGED, AND WHAT EACH ONE COST.

  1. THE [19.68] PARENT CHARGE NOW ASKS WHETHER THE PARENT EXISTS (engine._rebuild). The 52.42
     water leg of that charge has always asked state.on_map; the CP leg asked nothing, so a Parent
     Formation the campaign had already destroyed drank nothing and was billed a Capability Point
     anyway. Two legs of ONE charge disagreeing about who exists.
     MEASURED, six full 111-turn campaigns: 66 / 87 / 109 / 120 / 140 / 148 such rows per campaign
     (seeds 1 / 4 / 7 / 2026 / 777 / 1941) -> ZERO on every seed. The dead parents are
     overwhelmingly HQ counters, i.e. exactly what 19.63 calls gone for good.
     AND IT IS PROVABLY INERT. On seed 7's full campaign the base log is 223,519 events and the
     repaired log is 223,410 -- the base log MINUS exactly the 109 dead-parent rows and nothing
     else, compared event for event on (kind, side, actor, turn, stage, phase, payload, rng_draws)
     with seq excluded because deleting a row renumbers it. IDENTICAL AFTER DELETION: True. With
     this fix ALONE, survivor counts and the 64.76 grade string are unchanged on all six seeds.
     So it was a ledger lie with no behavioural bite -- and it is fixed because it is wrong, which
     is the only reason this file accepts. FLAGGED, A READING: state.on_map is
     `alive and turn >= arrival_turn`, so the guard also declines to bill a Parent whose rule-20
     reinforcement turn has not come (~5 charges a campaign). 19.68 says nothing about arrival; what
     licenses it is that on_map is the predicate state.living -- and so every rule-52 water beat,
     including this charge's own other leg -- has always filtered on.
     This CLOSES the debt named at the bottom of the 52.42 round-2 entry further down this file.

  2. THE ASSAULT SETTLES ITS AMMUNITION BEFORE IT DRAWS ITS WATER (engine._resolve_combat). 52.42
     bills the Point "if it uses any of its CPA"; an attacker refused for want of ammunition is
     dropped from armed_atk, never reaches _charge_combat_cp, spends none of the [6.3] 5-CP Assault
     and owes nothing. _has_ammo -- the non-mutating [50.15] oracle already in the file for 15.15's
     capitulation test -- now stands ahead of the draw. _charge_ammo still stands BEHIND it, so a
     DRY attacker still never spends its scarce load on an assault 52.51 forbids: this is an insert,
     not a swap, and both tests that pin the dry case still pass unchanged.
     THE DOCSTRING'S OWN REASON FOR DEFERRING IT WAS FALSE WHEN WRITTEN -- it said "_charge_ammo has
     no such oracle, it decides and draws in one pass", and _has_ammo is that oracle, thirty lines
     away. Its "36 Points / 3% of the vehicle bill" no longer reproduces either: MEASURED over six
     full campaigns the phasing assault refuses for ammunition ZERO times, and both benchmarks
     likewise. Seed 7's full 111-turn log is BYTE-IDENTICAL with this fix alone -- all 223,519
     events. A latent hole closed at zero cost, not a live leak.

  3. A DRY VEHICLE NO LONGER TAKES THE [10.36] RETREAT; [15.82] PRICES ITS REFUSAL
     (engine._mandatory_retreat + the new engine._refused_retreat_losses). 10.36's "for any reason"
     genuinely fires on a dry vehicle -- it can neither Assault (52.51) nor Hold Off, and 10.32's
     exemption list (solely Guns/AT/AA/non-combat, or Pinned) does not reach thirst -- and 52.51
     then genuinely forbids the compliance, because a forced retreat IS movement by [8.12], by
     [6.0]'s General Rule ("movement (including retreats and advances)") and by 10.36's own
     "playing all CP's for such movement". 52.51 carries no voluntary/involuntary qualifier while
     its neighbour 52.52 expressly says infantry may not "voluntarily" exceed their CPA, so the
     asymmetry is the book's: DRY INFANTRY IS STILL FORCE-RETREATED, and there is a test for it.
     FLAGGED, A READING: 15.82 sits under [15.8] DETERMINING CASUALTIES, so pricing a rule-10
     obligation with it extends its scope. What licenses it is that 15.82's first sentence is
     DEFINITIONAL -- it says what "A Retreat of a specific number of hexes" MEANS -- and 10.36 uses
     exactly that construction; it is also the only price the book prints for a retreat that cannot
     be taken, and engine._retreat has billed it for the post-assault case all along. THE
     ALTERNATIVE, RECORDED SO IT CAN BE REOPENED: exempt a dry vehicle as if it were Pinned. It was
     rejected because it invents an exemption 10.32 does not list and REWARDS thirst by cancelling
     the three Disorganization Points and the CP burn as well. 10.36e's Surrender is deliberately
     NOT what a dry vehicle gets -- the book reserves that for no-legal-destination.
     MEASURED, six full campaigns: it fires on TWO seeds (1 and 777), 2 and 3 STEP_LOST rows, 2 and
     3 TOE Strength Points -- ~0.8 rows per campaign. Everything else on those two seeds is chaos
     downstream of two counters standing still: seed 1 survivors ALLIED 202->200 / AXIS 99->100 at
     an unchanged "Axis Smashing Victory: 386-10"; seed 777 ALLIED 234->223 / AXIS 102->101 and
     1219-20 -> 1199-10, still "Axis Smashing Victory". The other four seeds do not reach it at all.

THE BOARD, six full 111-turn campaigns, all three fixes together: WINNER AXIS AND GRADE "SMASHING
VICTORY" ON ALL SIX, BEFORE AND AFTER. The 64.76 string is character-identical on five of six
(386-10, 1187-20, 475-0, 772-20, 412-20); only seed 777 moves, and only within the same grade.
Survivor counts are identical on four of six. PREDICTED IN WRITING BEFORE MEASURING and the
prediction held on every line: benchmarks unchanged, every campaign signature moved, board unmoved.

THE NEUTER TABLE (each guard disabled AT ITS OWN CALL SITE, never a shared helper, over
tests/test_mandatory_attack.py + test_water_cpa.py + test_water.py + test_reorganization_segment.py
+ test_replacement_spend.py + test_desert.py + test_salt_marsh.py + test_fort_barrage.py +
test_organization.py + test_supply.py + test_combat.py, 0 failures with all three live):

    [19.68] the dead-parent CP guard (engine._rebuild)                   2 RED
    [50.15] the ammo oracle ahead of the water (engine._resolve_combat)  1 RED
    [52.51] the dry-vehicle split (engine._mandatory_retreat)            1 RED

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED 2026-08-02 -- [4.46], THE HEADQUARTERS CLOSE-ASSAULT DASH. Recorded here anyway,
because the entry below says in as many words that 3.36's population is empty and that "THOSE TWO
CHANGES ARE COUPLED", and this is the other half landing. BOTH BENCHMARK SIGNATURES ARE BYTE-
IDENTICAL across it: rommel e1d1fa771ce3, siege 19693b23b988, unchanged. Neither benchmark ever
puts an HQ in a defender list or leaves one alone in an enemy ZOC, so no event moved.

    THE CAMPAIGN SIGNATURES DID MOVE (recipe: scenario.campaign(seed, max_turns=12) via its OWN
    kwarg, CampaignAxisPolicy vs CampaignCommonwealthPolicy, sha256(determinism_signature)[:12]):

        1941 dd3ddecd056f -> e0d87db9c4e8        7    250b13e94052 -> 5398e7b611a6
        4    fbf8cf16a7ca -> 620d28a58be8        2026 77d929598c0b -> 8e1b9c5e17f9

THE CHANGE IS ONE DATA CELL x3, NO ENGINE CODE. data/unit_stats.json gave GE.hq, CW.hq and
CW.hq_engineer a Close Assault Defence of 1 while citing chart row 'a'. Row 'a' prints a DASH --
German [4.46c] PDF p.137 and Commonwealth [4.46a] p.133, both re-rendered at 300 dpi and read cell
by cell for this entry, and the dash runs across all seven rating columns INCLUDING Maximum TOE,
which is what makes it a rating that cannot exist rather than a placeholder. The chart key on the
same page: "- = Not applicable (e.g., an infantry unit has no Vulnerability and may therefore not
be harmed by Anti-Armor fire)." The Italian rows are deliberately NOT touched (their CPA is row b's
30, and row b prints "0/(1)", not a dash) -- data/unit_stats.json IT._hq_dash_comment says why.

MEASURED, four full 111-turn campaigns, CampaignAxisPolicy vs CampaignCommonwealthPolicy,
seeds 1941 / 7 / 4 / 2026:

    bare HQs in a defender stack       6 / 4 / 8 / 10  ->  2 / 5 / 6 / 9
    raw defensive points they added    6 / 4 / 8 / 10  ->  1 / 0 / 5 /  4   (all of it now ITALIAN)
    HQs captured by 3.36 / 10.29       0 / 0 / 0 /  0  ->  1 / 2 / 0 /  2   (the clause was inert)
    winner + 64.76 grade               Axis Smashing Victory on all four seeds, BEFORE and AFTER
    64.76 Victory Points               666-0 -> 772-20   815-0 -> 475-0
                                       861-10 -> 1187-20  419-20 -> 412-20

The grade does not move on any seed and the VP shift is RANDOM IN SIGN (+106, -340, +326, -7) --
single-seed chaos of the kind this file documents below, not a balance lever. 74 of the 84 HQ
counters in a campaign change (CW hq 50, CW hq_engineer 15, GE hq 9); the 10 Italian ones do not.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-08-02 -- CAUSE: [10.29], THE CAPTURE OF A STRENGTHLESS NON-COMBAT COUNTER. A hex
that could be neither entered nor flipped, because the one rule that resolves it was not built.

    rommel ca0eec96abbd -> e1d1fa771ce3      siege 76371e5939a0 -> 19693b23b988
    campaign  1941 d4fa0bd90ffc -> dd3ddecd056f    7    d107a13ab6de -> 250b13e94052
              4    9d1ce03d1b95 -> fbf8cf16a7ca    2026 5b5e5c38bc6a -> 77d929598c0b

THE BOOK, re-rendered at 300 dpi off PDF p.18 (the page prints its own folio 18) and read character
by character; the crop is scratchpad-only, the transcription is here and in engine._capture_noncombat:

    [10.29] "Truck Convoys may not enter an Enemy ZOC unless such hex is already occupied by a
            Friendly combat unit. Furthermore, no non-combat unit (i.e., bare HQ's, Engineers, Air
            Squadron Ground Support Units, etc.) may ever enter an unoccupied hex in an enemy ZOC
            voluntarily. If such a unit is alone in an Enemy ZOC at any time during the Enemy
            Movement/Combat Phase and it has no strength of any type, such Friendly non-combat unit
            is Captured."

    [8.13]  "A unit may never enter a hex containing an enemy unit (see, however, Case 27.4).
            Furthermore, movement from hex to hex must be consecutive; units may not skip hexes.
            (There are, of course, different rules for aircraft.)"   (PDF p.14 = folio 14)

    [3.36]  "An HQ unit that has no combat values, either with or without parentheses, is captured
            instantly if it is in a hex without any combat units and an Enemy combat unit places the
            HQ in its Zone of Control. There is no Capability Point expenditure required for such a
            capture, and the HQ is treated as one Prisoner Point."   (PDF p.6 = folio 6)

THE DEFECT WAS NOT IN EITHER RULE THE FREEZE WAS BLAMED ON. tactics.enemy_zoc_and_occupied bars
entry on ANY living enemy unit, combat or not -- that is [8.13] verbatim and it is untouched here.
engine._record_control banks ground only for combat units and campaign_victory._occupier asks
[64.73]'s own question -- also right ([10.11]: a bare HQ exerts no ZOC). What was missing was the
REMOVAL. A 0-rated defender cannot shed a step (engine._absorb_losses: "Units with no rating cannot
absorb") and never runs out of Close-Assault ammunition off its [50.0] basic load, so [15.15] never
fires either: the counter could not be entered, killed, starved or flipped. Measured over 32 full
campaigns before the fix: 281 such stalemates, 2,830 stage-closes, the longest 319 stages of a
332-stage war.

WHAT IS BUILT IS [10.29] AND NOTHING ELSE. The book legislates this situation four times -- [3.36]
bare HQs, [10.29] any strengthless non-combat unit, [35.12] SGSUs on MERE ADJACENCY, [22.63] Tank
Delivery Squadrons -- and this is the one clause whose trigger the engine already computes exactly,
off the same ZOC map movement is gated on. 35.12's adjacency trigger and 22.63 are deliberately NOT
built. 3.36's population was EMPTY here WHEN THIS ENTRY WAS WRITTEN and is not any more -- see the
[4.46] entry above, which is the coupled half this paragraph asked for. It read: data/unit_stats.json
prints "dca": 1 on every hq / hq_engineer row while citing chart row 'a', and that row prints a DASH
in the Close Assault column on all three national charts, each re-rendered at 300 dpi and read for
this entry: German [4.46c] PDF p.137, Commonwealth [4.46a] p.133, Italian [4.46b] p.136 (printed a*
there). THOSE TWO CHANGES ARE COUPLED -- fix that dca faithfully without landing 3.36 and every bare
HQ becomes as unkillable as the SGSU was. They landed in that order, and 3.36 now fires on German
and Commonwealth bare HQs (1/2/0/2 times per campaign on seeds 1941/7/4/2026); the Italian rows are
still outside the population and still flagged.

TWO READINGS FLAGGED AS JUDGEMENT CALLS, both pinned in tests/test_noncombat_capture.py:
  * "alone" = with no FRIENDLY COMBAT UNIT in the hex. 10.29's own previous sentence opposes an
    "unoccupied hex" to one "already occupied by a Friendly combat unit", and the three sibling
    clauses say combat unit outright ([3.36] "without any combat units", [35.12] "no Friendly combat
    unit stacked with it", [22.63] "alone in a hex"). It is also [10.26]'s negation condition.
  * "at any time during the Enemy Movement/Combat Phase" is sampled at the three beats where
    _capture_dumps already sweeps -- after movement, after combat, after the 8.2 exploitation pulse.

MEASURED, three full 111-turn campaigns, CampaignAxisPolicy vs CampaignCommonwealthPolicy, the
frozen population counted at every Operations Stage close exactly as the probe counted it (a hex
holding only non-combat units of one side with an enemy combat unit adjacent):

    seed   FROZEN stage-closes   distinct frozen stacks   counters captured   winner + 64.76 grade
    15          52 ->   8              10 -> 5                   10           Axis Smashing, both arms
    26         436 ->   8              11 -> 4                    9           Axis Smashing, both arms
    30          18 ->   7              10 -> 6                   11           Axis Smashing, both arms

THE RESIDUE IS HONEST AND IDENTIFIED. Every counter still frozen after the fix is one 10.29 cannot
reach: CW-SGSUs standing next to an enemy stack too small to exert a ZOC at all (10.11's one
Stacking Point / 10.15's ten raw defensive points -- [35.12]'s MERE-ADJACENCY trigger is the book's
answer to those and is not built), plus HQ-4-In-Div / HQ-7-Armd-Div / IT-1-Libyan, which are exactly
the "dca": 1 rows above. The 32-seed probe measured the same split: 2,830 frozen stage-closes of
which 1,282 were in an enemy ZOC.

Winner and 64.76 grade are UNCHANGED on all three full wars and on the four max_turns=12 boards
(Axis Smashing Victory everywhere, before and after). Victory Points move in both directions
(seed 15 Axis 787->980, seed 26 755->761, seed 30 390->778; at max_turns=12, 1941 1952->1845,
7 1959->1950, 4 1960->1960, 2026 1860->1956 with CW 10->0) -- the Axis is overrunning Commonwealth
forward airfields in every one of these wars, so it is the Commonwealth's Squadron Ground Support
Units that are collected.

THE ONE THING IT COSTS, AND IT IS BIG: THE COMMONWEALTH'S GRIP ON ITS OWN RAILHEAD. [60.5] seeds
three Commonwealth Squadron Ground Support Units ON Mersa Matruh, and under the old engine those
three could hold the terminus against the whole Panzerarmee while banking nothing with it. Swept
over ONE HUNDRED seeds to GT12 against the control tree: the Commonwealth still holds Mersa Matruh
on 60 of 100 boards before and 13 of 100 after, 51 held->lost against 4 lost->held. The full
argument, the spot-measured frozen-stage counts and the reason CAMPAIGN_SEED was NOT re-pinned to
one of the surviving thirteen are in this file's CAMPAIGN_SEED note.

TEST FALLOUT: eight, all restated, none weakened, each with its own measurement written into the
file it lives in. tests/test_siege.py re-pins the nearest-gun pair 52 -> 42 (still nowhere near a
wall; ONE counter is taken on that benchmark, AL-SGSU-250RAF at GT1.1, and it moves the whole log).
tests/test_rail_control.py re-sweeps its 54.4 witness seed 34 -> 31, which is a dual witness under
both instruments -- a property the previous re-pin had to record as unavailable.
tests/test_air_facilities.py drops a zero-tolerance "no squadron was ever denied for want of a fed
SGSU" that was passing on BEAT ALIGNMENT (the control tree's able-SGSU count already reaches zero
at the GT8/GT9 stage-2 closes) for two claims that are IDENTICAL on both trees: 51 Axis / 21 Allied
refits resolved, and no refit ever refused for an empty larder. The other five are the railhead
above.

RECIPE: the four campaign rows use scenario.campaign's OWN max_turns kwarg (see THE TRAP below);
the three 111-turn rows use campaign(seed) unmodified. Benchmarks seed 42, axis=allied=
ScriptedPolicy(AXIS). Every one of the six signatures above was read live TWICE on this tree and on
a pristine `git archive HEAD` control tree, byte-identical both passes; the control tree reproduced
all six PRE values exactly, first try, which is what makes it a control.
--------------------------------------------------------------------------------------------------
NOT RE-BASELINED 2026-08-02 (BYTE-IDENTICAL) -- THE LAST THREE PER-OPERATIONS-STAGE LEDGERS MOVED
ONTO engine._OpStageLedger, AND THE RESET LINES IN run()'s STAGE LOOP ARE GONE.

    ca0eec96abbd / 76371e5939a0 and campaign 1941 d4fa0bd90ffc / 7 d107a13ab6de / 4 9d1ce03d1b95 /
    2026 5b5e5c38bc6a   (all six UNCHANGED, measured on a tree carrying ONLY this conversion,
    read live twice, and identical to the `git archive HEAD` control on every board)

The entry below records why these three were left behind by the refactor that converted the other
three, and what it would take to move them: "converting them is a BEHAVIOUR change ... and exactly
what must be measured rather than assumed. Their own slice." This is that slice.

WHAT MOVED, all in game/engine.py. r.ports_bombed_this_stage ([55.18]), r.forts_bombed_this_stage
([41.37]) and r.building ([24.12]) become _OpStageLedger instances read through `.current`; the
three lines that reset them inside `for stage in (1, 2, 3)` are deleted, along with the
DO-NOT-ADD-A-RESET-HERE comment block, whose warning now lives in _OpStageLedger's docstring where
the next author will actually meet it. No test needed restating -- nothing outside engine.py ever
named these three.

WHAT IT FIXES, which is the whole point and is NOT visible in any signature above. Inside run() the
conversion is inert, because every read and every write of all three lies between the stage-loop's
first statement and the STAGE_ADVANCED/TURN_ADVANCED emit that ends it. For any OTHER caller -- a
test, a measurement driver, or one of run()'s own Game-Turn-level beats, which is how the [52.42]
water ledger leaked (49b00f2) -- the old shape was three live bugs: a harbour bombed once NEVER
regenerated, a fortification could be battered once per WAR instead of once per Operations Stage,
and an engineer booked on a project stayed pinned to its hex for the rest of the game. Each is now
pinned by a test that drives two Operations Stages by hand and never enters run()
(test_ports, test_fort_barrage, test_construction), and each of those tests fails when its own
read is neutered back to the non-expiring value at its own call site.
--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-08-02 -- CAUSE: [64.73], THE OCCUPATION QUALITY-TEST. The last abstract-game rule
standing in the victory module: it asked TWO of the rule's FOUR commodities, and asked them through
the section-32.16 half-CPA supply trace that CLAUDE.md rule 3 says does not apply here.

    campaign signatures  1941 8e5ca52dca17 -> d4fa0bd90ffc    7    312512305717 -> d107a13ab6de
                         4    f1c874bfbe7f -> 9d1ce03d1b95    2026 68be27e28f3f -> 5b5e5c38bc6a
    BENCHMARKS UNMOVED   rommel ca0eec96abbd   siege 76371e5939a0   (read live, twice)

The two benchmarks do not move because the rule is campaign-only by CONSTRUCTION, not by a gate:
rommels_arrival and siege_of_tobruk carry no 64.73 city table and their own VictorySpec, so
CampaignVictory._supplied is never called on either board.

THE BOOK, re-rendered at 300 dpi and read character by character (PDF p.88 = book folio 37, col. 3;
the misspelt "conditons" is the book's own):

    [64.73] "...Occupation for these purposes means having a combat unit of at least 1 TOE Strength
            in the hex. That combat unit, at the end of the game, must have enough Stores and Water
            for one Week, and enough Fuel and Ammunition to fire its weapons three times and move
            20 CP's. Any units failing these "tests" do not occupy for victory conditons."

    [5.1]   "In CNA each Game-Turn covers a period of approximately one week. However, to better
            handle combat operations, each Game-Turn is divided into three Operations Stages."
            (folio 11) -- which is how the WEEK is converted: supply.stores_cost is already a
            per-Game-Turn rate (51.11) and is taken once; supply.water_cost is a per-Operations-Stage
            rate (52.4) and is taken three times.

THE DEFECT, both halves in one sentence. campaign_victory._supplied tested Fuel and Ammunition only
-- the Stores and Water the rule puts FIRST were not asked at all -- and it tested them with
supply.plan_draw, the ABSTRACT game's supply range. It now asks all four through supply.in_hex_draw,
the full-game draw the S5/S6/S7 slices already switched Fuel, Ammunition and Stores onto.

WATER DID NOT RE-OPEN THE S8 FINDING, and the reason is measured rather than argued. The supply
layer's water draw stays on the trace (S8: the naive in-hex form gave 60% thirst against a faithful
12%, because [52.45]'s water-truck reservoir is unbuilt) and is UNTOUCHED by this slice. The victory
predicate can ask in-hex anyway because every one of the ten 64.73 cities carries a game.wells water
source for BOTH sides: over six campaign boards (seeds 3/4/7/30/1941/2026 at max_turns=12), of the
103 combat units standing on a 64.73 city the in-hex and trace readings of the Water clause agreed on
ALL 103. Away from the cities they differ on 24-44 units a board, which only observation.can_hold
sees.

THE A/B, four seeds, max_turns=12 through scenario.campaign's OWN kwarg, both arms LIVE RE-RUNS
(the predicate is shared with game.campaign_claim, so it moves the policy and not merely the score;
the BEFORE arm reproduces all four pinned signatures above exactly, which is what makes it a control):

    seed   64.73 geography AXIS   CW    winner + 64.76 grade        cities that CHANGE HANDS in the tally
    1941        465 ->  375        0->0  Axis Smashing, both arms    -SidiBarrani -Giarabub -Bardia
                                                                    -Sollum, +MersaMatruh(AXIS)
    7           415 ->  375        0->0  Axis Smashing, both arms    -Giarabub -Bardia -Sollum,
                                                                    +MersaMatruh(AXIS)
    4           565 ->  375        0->0  Axis Smashing, both arms    -SidiBarrani -Giarabub -Bardia
                                                                    -Sollum
    2026        415 ->  275       10->10 Axis Smashing, both arms    -Giarabub -Bardia -Sollum

("-" stops scoring, "+" starts. It is not purely subtractive: on two seeds the Axis GAINS Mersa
Matruh, because the trajectory itself moved -- the war is re-run in both arms, not re-scored.)

THE NEUTER / ATTRIBUTION TABLE -- which clause moved it, and which CALL SITE. Every arm is a live
campaign re-run at max_turns=12, each in a FRESH interpreter (max_tasks_per_child=1, because this
project has had a table of byte-identical arms out of ProcessPoolExecutor reusing a worker and
composing one arm's patch on the next). Cells are signature / Axis 64.73 geography / Commonwealth.

    arm  what it tests                    seed 1941       seed 7          seed 4          seed 2026
    A0   trace  FUEL(20CP)+AMMO(3)        8e5ca52dca17    312512305717    f1c874bfbe7f    68be27e28f3f
         (the predicate as it shipped)    ax465 cw0       ax415 cw0       ax565 cw0       ax415 cw10
    A1   A0 + STORES(one Game-Turn)       3ed3490f6024    9010601753b3    9099f0dc719d    609ac6991551
                                          ax290 cw10      ax290 cw0       ax390 cw0       ax290 cw10
    A2   A1 + WATER(3 OpStages)           3ed3490f6024    9010601753b3    9099f0dc719d    609ac6991551
                                          ax290 cw10      ax290 cw0       ax390 cw0       ax290 cw10
    A3   in-hex FUEL+AMMO (form only)     df2d6810edbb    65fcb22b27fc    05d9b767522c    ee4dad6ea4a9
                                          ax425 cw0       ax375 cw0       ax425 cw0       ax375 cw20
    A4   in-hex all four  (LIVE)          d4fa0bd90ffc    d107a13ab6de    9d1ce03d1b95    5b5e5c38bc6a
                                          ax375 cw0       ax375 cw0       ax375 cw0       ax275 cw10
    C1   A4, but campaign_claim._banking  8e5ca52dca17    312512305717    f1c874bfbe7f    68be27e28f3f
         reverted to A0                   ax275 cw0       ax275 cw0       ax375 cw0       ax275 cw10

TWO THINGS FALL OUT OF IT, and the second is the attribution this slice needed.

    * THE WATER CLAUSE IS MEASURABLY INERT TODAY. A1 and A2 are BYTE-IDENTICAL on all four seeds --
      adding 64.73's Week of Water changes not one event and not one Victory Point. It is added
      anyway, because the rule names it and because inert is a fact about today's map (every 64.73
      city carries a well for both sides), not about the rule. It will bite the day a scoring city
      has no water source under it. Both the STORES clause (A0 -> A1) and the FORM switch (A0 -> A3)
      move every seed on their own, so neither is carrying the other.
    * AND SO IS THE FUEL CLAUSE, which this table did not say and should have -- naming only Water's
      inertness read as if Water were the one unmeasured commodity of the four. ADDED 2026-08-02,
      neutered at its own call site in campaign_victory._supplied (that tuple's FUEL row rewritten to
      `(supply.FUEL, 0)`, game/__pycache__ deleted, PYTHONDONTWRITEBYTECODE=1):

        arm  what it tests                    seed 1941       seed 7          seed 4          seed 2026
        A5   A4 with the FUEL clause inert    d4fa0bd90ffc    d107a13ab6de    9d1ce03d1b95    5b5e5c38bc6a
                                              ax375 cw0       ax375 cw0       ax375 cw0       ax275 cw10

      Byte-identical to A4 on all four, geography included. THE REASON IS STRUCTURAL, NOT LUCK, and
      it is written down at the predicate and pinned in tests/test_campaign_victory.py (the Fuel
      magnitude and the [49.14] tank ceiling each have their own case now; every holder in that file
      used to be FOOT, so 49.12 made the clause vacuous and neutering it left the whole suite green).
      In short: 49.12 exempts foot units and 21 of the 22 garrisons that bank a city across five
      boards are foot; [49.14] sizes a unit's tank to its OWN CPA, so below cpa 16 a brim-full tank
      cannot pay 64.73's fixed 20 CP; and off a co-located dump [51.0]'s absent Stores pool and
      [50.0]'s single firing fail FIRST. MEASURED per clause on those five boards (the four above
      plus CAMPAIGN_SEED=23 at GT30): of every combat unit of >=1 TOE standing on a 64.73 city, TWO
      fail Fuel per board -- the same pair each time, Giarabub's artillery and AA battalions, both
      cpa 15 with full tanks at 18/24 and 12/16 Points -- and NOT ONE fails Fuel and nothing else.

      PER-CALL-SITE NEUTER TABLE for the predicate, every row rewriting ONE expression in
      game/campaign_victory.py (never a shared helper), game/__pycache__ deleted and
      PYTHONDONTWRITEBYTECODE=1 per row. Run against tests/test_campaign_victory.py:

        row  neuter                                          verdict   tests that go red
        A    the FUEL row -> `(supply.FUEL, 0)`               RED       3   <- new 2026-08-02
        B    _CP_64_73 20 -> 1                                RED       3   <- new
        C1   _CP_64_73 20 -> 15                               RED       3   <- new
        C2   _CP_64_73 20 -> 16                               GREEN     0   -- see below
        C3   _CP_64_73 20 -> 21                               RED       3   <- new
        D    _FIRINGS_64_73 3 -> 1                            RED       1
        E    the STORES row -> `(supply.STORES, 0)`           RED       2
        F    the WATER row -> 0 Operations Stages             RED       4
        G    supply.in_hex_draw -> supply.plan_draw           RED       3

      ROW C2 IS AN HONEST GREEN AND IT IS NOT A HOLE IN THE PIN. The sweep in
      test_64_73_the_fuel_clause_is_twenty_cp_and_a_motorised_holder_pays_it fixes the threshold at
      exactly 20 Fuel Points, which fixes _CP_64_73 to the closed band 16..20 -- and 16 through 20
      cannot be told apart by ANY test, because [49.13] charges rate x CEIL(CP/5) x TOE and all five
      values sit in one five-CP block. That is the rule's arithmetic, not a gap. Rows A, B, C1 and C3
      were all GREEN before this slice.
    * C1 REPRODUCES A0's SIGNATURE EXACTLY ON ALL FOUR SEEDS. With the faithful predicate live
      everywhere and only campaign_claim._banking reverted, the event log is byte-identical to the
      pre-change tree -- so _banking is the ONLY in-run reader of this predicate in a scripted
      campaign, and the whole signature movement is attributable to it and to nothing else.
      CampaignVictory._occupier moves the SCORE and emits nothing: C1's own geography column
      (ax275/275/375/275) is the faithful test scored on the unchanged board.

THE TRAP FIRED, AND IT IS REPORTED RATHER THAN SOFTENED. A stricter test makes the board emptier,
exactly as it might: the Axis loses 40-190 Geographic Occupation Points on every seed and the
Commonwealth gains none. The winner and the 64.76 grade are unchanged on all four (64.74's ~1,580
Axis replacement points dominate the tally). WHAT IT IS NOT is an army that moved: measured at
CAMPAIGN_SEED, GT30, the Axis OCCUPIES Giarabub, Bardia, Sollum, Tobruk and Benghazi -- EXACTLY the
five it BANKED before this change (the 2026-08-01 record in test_campaign_claim.py) -- and now BANKS
only Tobruk and Benghazi.

*** WHY, RE-DERIVED CLAUSE BY CLAUSE 2026-08-02. THE FIRST ANSWER PRINTED HERE NAMED THE WRONG
CLAUSE AND THE WRONG ARMY, AND IT IS STRUCK RATHER THAN SOFTENED. *** It read: "The three that stop
scoring are held by garrisons that cannot show a Week of Stores where they stand, and the reason it
bites the Axis and not the Commonwealth is an OOB debt this port already flags: German combat units
carry no first-line trucks ([4.43b]) ... This number is therefore a MEASUREMENT OF THE UNPAID OOB
DEBT". The tally it explained is right; the mechanism under it is not. MEASURED on five boards --
CAMPAIGN_SEED=23 at GT30 and the four A/B seeds above at max_turns=12 -- asking every combat unit of
>=1 TOE standing on a 64.73 city which of the four clauses it fails, keyed on the counter's own
Unit.nationality. Every board agrees, city for city:

    city          holder                     clause that FAILS      what stands under it
    Giarabub      6 x IT-Grbub (Italian)     AMMUNITION only        AX-Well-Giarabub ONLY: the oasis,
                                             (2 of the 6 also Fuel) holding 124,996,400 Stores -- so
                                                                    the STORES clause is SATISFIED here
    Bardia        Italian, 1-2 battalions    STORES only            AX-Stage-Bardia, holding 146-188
                                                                    Ammunition and 0-15 Stores
    Sollum        Italian, 1-8 battalions    AMMUNITION and STORES  AX-Well-Sollum ONLY: water, no
                                                                    Stores, no Ammunition
    Sidi Barrani  BR-2SctGds (Commonwealth)  STORES only            AL-Stage-Barrani, dry of Stores;
                  -- on all four A/B seeds                          its own ration 5/2/6/13 of a
                                                                    24-Point week

THREE CORRECTIONS. (1) THE CLAUSE IS NOT UNIFORMLY STORES: one city fails on Ammunition alone, one on
Stores alone, one on both. At GIARABUB the struck sentence is not merely unmeasured, it is refuted by
a printed rule -- [52.3] OASES, verbatim off a 300-dpi render of folio 21: "Units sitting in Oases
have all the stores and water they need to last them the entire game." Giarabub is an oasis, so its
Stores clause CANNOT fail; game.wells models that as the 124,996,400-Point figure above. (2) THE ARMY IS ITALIAN, NOT GERMAN, and not one German counter stands on
a 64.73 city on any of the five boards -- 17 German combat units are alive at CAMPAIGN_SEED/GT30 and
all 17 are elsewhere, so [4.43b] could not flip Giarabub, Bardia or Sollum whatever it landed. (The
other four boards stop at Game-Turn 12, before the DAK arrives: nationality GE does not appear on
them at all.) (3) IT DOES NOT SPARE THE COMMONWEALTH. Sidi Barrani fails the same STORES clause for
the Commonwealth on all four A/B seeds. "The Commonwealth gains none" stays true; "it bites the Axis
and not the Commonwealth" was false. The Axis loses more POINTS because its three failing cities are
worth 140 Axis V.P. on 64.73's own table against Sidi Barrani's 10 Commonwealth V.P. -- an asymmetry
of the victory TABLE, not of the lorries.

WHAT THE NUMBER ACTUALLY MEASURES IS THE LAST MILE. 64.73 asks for a WEEK, and no organic pool the
book gives a counter is a week deep: [51.0] gives no organic Stores at all (what a counter holds is
a [53.11] first-line buffer the war spends) and [50.0]'s load is ONE firing against 64.73's three.
So the clause that fails is decided by WHAT DUMP STANDS UNDER THE GARRISON -- a stocked dump banks
(Tobruk, Benghazi, Mersa Matruh), a bare well fails whatever the well does not hold (Giarabub's oasis
covers Stores, so Ammunition fails; Sollum's covers neither), a dump dry of one commodity fails that
one (Bardia). That is this project's FAUCET debt, not its OOB debt. A carriage asymmetry does exist
and is recorded here as a fact WITHOUT a cause attached to it -- at CAMPAIGN_SEED/GT30 the counters
holding any first-line Stores at all are 0 of 17 German, 1 of 57 Italian and 25 of 67 Commonwealth --
but it is not what decides these three hexes, and it must not be re-attributed to [4.43b] without
measuring: the reinforcement half of that schedule is WIRED (data/reinforcement_first_line.json,
437 German + 885 Italian Truck Points, tests/test_first_line.py), only the GT1 muster half withholds
the Axis line from German counters, and a first-line truck is CAPACITY rather than loaded rations in
any case. Two tests pin the tally so it fails loudly when the last mile reaches the border
(test_campaign_claim.py, Sollum and Bardia: "INVERT THIS"), and their messages now name the clause
each hex actually fails.

THE PLANNER WAS SPLIT OFF THE SCORING RULE, and it is the one design decision here.
game.campaign_claim asked this same predicate of a unit AS IF it already stood on a city, to decide
where to send it. With the faithful in-hex form that question is unanswerable-by-construction -- a
claim is a plan to BRING supply and the in-hex test asks whether the supplies are ALREADY standing on
an empty city nobody has reached -- and the module's `fed` cache is keyed on the unit's supply CLASS
alone, which in-hex supply (it counts the unit's own lorry load) no longer determines. MEASURED with
the planner left sharing the faithful predicate: the Commonwealth banks NO victory city at all in the
windows the suite pins, the railhead falls, and TEN behaviour tests covering the take-and-hold, the
[15.53] concentration tier, the Axis railway and the Commonwealth truck relay go inert together off
that one gate. Splitting it (campaign_claim.could_be_fed, which keeps the reach question the planner
has always asked, unchanged and flagged as the policy heuristic it is) takes that to FOUR: one is an
INSTRUMENT that was reading the scoring rule as if it were a can-I-fight-here test, two are WITNESS
SEEDS/FOLDS moved by the trajectory, and one is a city that is still occupied and no longer banked.
All four are restated below, and the SCORING rule is not softened anywhere.

FOUR TESTS RESTATED, none weakened, each onto the thing it is named for:
  * test_campaign_claim.py::test_both_sides_take_the_cities_they_used_to_sprint_past -- Sollum and
    Bardia split into OCCUPIED (asserted, and still exactly true: the take-and-hold thesis) and
    BANKED (asserted false, with an INVERT-ME note). It asserts strictly more than it did.
  * test_campaign_concentration.py::test_the_commonwealth_can_mount_a_supplied_offensive -- the
    INSTRUMENT moved, the thesis did not. It counted "supplied" with the 64.73 predicate, which is
    now the end-of-game HOLD-GROUND test, not the can-I-fight-here one. At CAMPAIGN_SEED over the
    same eleven Compass turn-closes: old _supplied 11/11, new _supplied 0/11, can-move-and-fire
    in-hex 11/11 (asserted), can-move-and-fire on the trace 11/11. The offensive is supplied where
    it is fought at every turn-close; it simply could not BANK ground sixty hexes up the coast.
  * test_organization_campaign.py -- the [15.53] fold widens 6 -> 8 Game-Turns and the SHOPPED SEED
    GOES AWAY: the canonical seed now carries both the attacker and the rarer defender leg on one
    campaign. Measured at CAMPAIGN_SEED by fold length: 6 -> 1 tier row, 7 -> 4, 8 -> 10 (defender
    tier at GT7/8), 9 -> 15, flat after. Threshold unchanged, seed unchanged.
  * test_rail_control.py -- the Axis-railway witness re-pinned 11 -> 34. Re-swept seeds 1-40 to
    Game-Turn 6: eighteen activate, five haul cleanly ({14, 15, 20, 34, 38}), and NONE of the
    previous tree's clean set {4, 11, 17, 26, 33} so much as activates, so no seed is a witness under
    both instruments this time and that is stated rather than glossed. Seed 34 is chosen on the
    property the 9 -> 11 re-pin ranked first -- its activation is paid by AX-Dump#4, the Axis's own
    dump, not by Commonwealth stores overrun at El Daba -- and it hauls the most of the Axis-paid
    candidates.

STILL OPEN, FLAGGED AT THE LINE, NOT DONE HERE:
  * "fire its weapons three times" is charged at the close-assault rate. A barrage unit's own weapon
    costs more (50.2: barrage 4, anti-armor 3, assault 2) and supply.ammo_capacity already computes
    "one firing of this unit's dearest function". A MAGNITUDE question; this slice was a FORM
    question; moving both at once makes the A/B unreadable. UNMEASURED, deliberately.
    (RANGE CORRECTED 2026-08-02: this entry and the flag at the code both put the ceiling at 2x the
    shipped bill, the dearest-weapon reading. The decisive evidence is on the SAME scanned page and
    was not cited -- [63.92], PDF p.88 col. 1, glosses the identical construction. Verbatim off a
    300-dpi render of that column: "Occupying means that all combat units in that City/Village must
    have at least one Game-Turn's worth of Stores, be able to fire all weapons twice, and have enough
    fuel for all units to move 20 CP's." ALL WEAPONS, TWICE -- the emphasis is this entry's, not the
    book's. Read 64.73 the way its own author reads it two columns away and
    "three times" means three firings of EACH function: a barrage + anti-armor + assault battalion
    owes 3 x (4+3+2) x TOE where the code charges 3 x 2 x TOE, i.e. 4.5x, not 2x. The magnitude
    slice must A/B 1x to 4.5x and cite 63.92. En passant, 63.92's "one Game-Turn's worth of Stores"
    independently corroborates the 5.1 Week -> Game-Turn conversion this entry makes above.)
  * THE IN-HEX FORM IS TRANSCRIBED FOR THREE COMMODITIES AND INFERRED FOR THE FOURTH, which the
    "(49.15/50.15/51.15)" citation at the code did not say. Those three clauses are Fuel, Ammunition
    and Stores. Section 52 read whole on the scan (folio 21, 52.0 through 52.52, and 52.53 on folio
    22) prints no in-hex clause for Water at all; the nearest support is [52.13], "To obtain water, a
    unit moves into a hex with a well", which is a MOVEMENT instruction. Applying supply.in_hex_draw
    to WATER is therefore an inference by analogy with the other three -- flagged per rule 1 of this
    port, and measured to cost nothing today (arms A1 and A2 above are byte-identical).
  * campaign_claim.could_be_fed is a proxy. The honest planning question is 64.73's own test asked of
    the board the plan CREATES -- the unit on the city with the depot the module is about to walk
    there. That changes what the policy proposes, so it is a measured slice of its own.
  * game.campaign_policy._can_trace still walks the 32.16 trace and its docstring used to claim it
    was this predicate. The claim is corrected; the heuristic is left, flagged as debt.
--------------------------------------------------------------------------------------------------
NOT RE-BASELINED 2026-08-02 (A PURE REFACTOR) -- THE THREE PER-OPERATIONS-STAGE LEDGERS NOW SHARE ONE
IMPLEMENTATION, engine._OpStageLedger. Nothing changes; the entry exists to record that nothing did,
and to keep the deleted symbols greppable from the entries below that still name them.

    ca0eec96abbd / 76371e5939a0   (UNCHANGED, read live twice on this tree)

WHY. The same defect had shipped TWICE from the same shape -- a per-Operations-Stage ledger cleared
by a line inside run()'s `for stage in (1, 2, 3)` loop, which any caller that drives the stages
itself reads as stale or spent. It was found and fixed in the [55.3] harbour tonnage ledger
(024d042) and then shipped again in the [52.42] water ledger (49b00f2), whose round-2 entry below
records that the correct pattern was named in this very file at the time. A pattern that lives in
each author's memory keeps recurring; this one now lives in a class, with both incidents in its
docstring and a DO-NOT-ADD-A-RESET-HERE note on the line in run() where the mistake gets made.

WHAT MOVED, all in game/engine.py. _Run.port_tons_this_stage/_stamp, water_billed_this_stage/_stamp
and the five _rail_* fields with _Run._expire_rail_stage (all now deleted, so a grep for them lands
here) become three _OpStageLedger instances -- r.port_tons, r.water_billed, r.rail_stage -- each
owning a private (turn, stage) stamp and exposing ONE door, `current`, so reads and writes expire
alike and there is no reset to call from outside. The railway's four facts are one _RailStage value
under one stamp, which is what the old comment "must never disagree about which stage that is" was
asking for. engine._port_tons() and engine._water_billed() keep their names and signatures, so every
call site and the tests that seed them are untouched.

PROVEN UNCHANGED, both benchmarks and four campaigns at max_turns=12 through scenario.campaign's own
kwarg (the recipe below), read on the pre-refactor tree and twice on this one, all six byte-identical:

    rommel ca0eec96abbd   siege 76371e5939a0
    campaign  1941 8e5ca52dca17   7 312512305717   4 f1c874bfbe7f   2026 68be27e28f3f

TWO TESTS RESTATED, neither weakened. tests/test_coastal_shipping.py read r.port_tons_this_stage
directly (now through engine._port_tons, the ledger's one accessor) and, in the partial-unload case,
wiped that dict from outside to stand in for a new Operations Stage -- which asserted only that the
remainder lands given an empty budget and said nothing about what empties it. It now emits
STAGE_ADVANCED and lets the stamp do the emptying, which is the mechanism the case is named for.

NOT CONVERTED, DELIBERATELY, AND FLAGGED AT THE LINE: r.ports_bombed_this_stage ([55.18]),
r.forts_bombed_this_stage ([41.37]) and r.building ([24.12]) are still cleared inside run() -- the
same shape, and the same latent leak. They are left because converting them is a BEHAVIOUR change
and this slice is a refactor. Under run() as it stands the conversion looks inert (_port_regen reads
the bomb ledger before STAGE_ADVANCED is emitted, and r.building.clear() lands after it), but that
is a fact about today's beat order, not a proof -- and for the callers the class exists to protect,
the ones that drive the Operations Stages themselves, converting them changes what they see, which
is exactly the fix they need and exactly what must be measured rather than assumed. Their own slice.
--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-08-02 -- CAUSE: [52.42], THE CPA CONDITION ON THE VEHICLE'S WATER POINT. A single
printed conditional clause that the engine did not carry, billed at the one beat in the Operations
Stage where it cannot be evaluated.

    d889e5b21c4e / 1f826374a883  ->  ca0eec96abbd / 76371e5939a0

THE BOOK, re-rendered at 400 dpi and read character by character (PDF p.68 = book folio 21, col. 3;
the crop is scratchpad-only, the transcription is here and in game/engine._draw_stage_water):

    [52.41] "Each infantry battalion or company regardless of its TOE Strength, requires one Water
            Point per Operations Stage. See also 52.6."
    [52.42] "Each TOE Strength Point of Vehicle (Tank, Recce, Artillery, etc.) or Truck Point
            requires one Water Point each Operations Stage, if it uses any of its CPA."

The asymmetry is the book's own, printed one line apart. [53.0]'s General Rule glosses it for the
lorries: "Trucks consume fuel and water when they move, and they suffer breakdown." Nothing in
[52.43]-[52.45] or [52.5] qualifies it -- 52.45 sends water to the [40.2] Truck Capacity Tables,
which is the CARRY and not the billing.

THE DEFECT. engine._water_distribution charged supply.water_cost to EVERY counter at the top of
every Operations Stage, vehicles included, and supply.water_cost's own docstring flagged it ("true
per-stage gating waits for CHUNK 5"). It cannot be evaluated there: engine._water_body runs from the
head of the stage loop and apply._reset_opstage has just cleared cp_used on every counter, so
52.42's condition is FALSE for the whole board at the moment the bill was drawn.

MEASURED on the pre-change tree, full 12-Game-Turn campaigns (CampaignAxisPolicy vs
CampaignCommonwealthPolicy), attributing each Water Point to the total CPA its counter spent
anywhere in that whole Operations Stage:

    seed   vehicle Water Points   of which the counter spent ZERO CPA   vehicle WATER_SHORTFALL rows
                                                                        (of which zero-CPA)
    1941        6,999                    6,219   88.9%                   271   (266, 98.2%)
    7           7,175                    6,377   88.9%                   448   (443, 98.9%)
    4           6,965                    6,149   88.3%                   311   (309, 99.4%)
    2026        6,901                    5,796   84.0%                   365   (362, 99.2%)

The shortfall column is the load-bearing half: a WATER_SHORTFALL sets stages_without_water, which
engine._waterless reads and [52.51]/[52.52] spend -- immobilised vehicle, no offensive close
assault, and _def_raw HALVING a defender's raw strength. Ninety-nine per cent of those were being
paid by a counter that had not moved a hex.

THE FIX, and its shape is the engine's own. engine._draw_move_fuel is [49.13]'s per-act draw that
returns a bool and refuses the order on failure; [52.42] gets its sibling, engine._draw_stage_water,
which draws ONCE per Operations Stage (the ledger read through engine._water_billed, self-expiring
on (turn, stage) like the 55.3 port ledger and the 54.43 rail one) at every site that raises
Unit.cp_used -- because cp_used IS this engine's encoding of "uses any of its CPA".
_water_distribution now bills 52.41's infantry Point only, and RESTORES a vehicle at the stage
boundary, without which 52.51 would be permanent by construction (a dry vehicle may not move, so it
could never take the act that clears it).

WIRED AT NINE SITES, found by enumerating the fold rather than by grepping the engine: exactly three
event kinds raise cp_used (apply.py UNIT_MOVED, REACTION_MOVED, CP_EXPENDED), and every emitter of
those three was wired or explicitly excluded. Movement (8.1 + the 8.2 pulse -- one function),
reaction (8.51), retreat before assault (13.21) REFUSE on failure, because 52.51 says "may not
move"; the offensive close assault drops the attacker, because 52.51 says "may not close assault
offensively"; _spend_cp (every [6.3] combat charge -- barrage, facility barrage, anti-armor, the
phasing Assault and the non-phasing DEFENCE -- plus 10.36's forced retreat), the [6.3] organization
rows, [19.68]'s rebuild, [54.14]'s demolition and [24.9]'s dump construction BILL ONLY, because
[52.5] forbids a dry vehicle to move and to assault offensively and nothing else. Deliberately NOT
wired: the two cp_spent=0 emitters (19.12's carried subsidiary, 18.22's CP-free Reserve I shuffle --
neither uses CPA) and adjudication.py's dry-run. _draw_stage_water's own first guard also carries an
`or supply.is_sgsu(u)` arm for 35.14 (an SGSU's 1 Water/Operations Stage is its own charge, drawn
whether its aeroplanes flew or not) -- BUT THAT ARM IS UNREACHABLE TODAY and this record used to
overstate it as a live exclusion: of the 53 SGSUs in campaign(1941) not one satisfies
supply._is_vehicle_type (all Mobility.MOTORIZED, is_gun/is_armor/is_first_line_truck all False), so
the first arm returns for every one of them. It is kept as belt and braces against a [53.11]
first-line truck being attached to a squadron, and the comment at the guard now says so.

ONE ORDERING DEFECT WAS FOUND BY THE MEASUREMENT ITSELF and is fixed in the same pass
(engine._can_fuel_move). With the water drawn before [49.13]'s fuel, a move the FUEL then refused
had already paid its water: 270 of campaign/1941's 1,179 vehicle Points, 23% of the whole bill, for
moves that never happened. The two draws are one affordability question -- a move that cannot be
fuelled uses no CPA and owes no water, and a vehicle that cannot water itself may not move and so
must not burn the fuel -- so the fuel is now TESTED (supply.in_hex_available, in_hex_draw's own
documented monotone oracle) before the water is DRAWN, and drawn after.

THE RECIPE FOR EVERY CAMPAIGN NUMBER IN THIS ENTRY, written down because leaving it out once made
the whole table unreproducible -- a reviewer swept max_turns 1-16, 18, 20, 24, 26, 30 and 111 across
three policy pairings and never hit a single one of these hashes:

    from game.scenario import campaign
    from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
    res = engine.run(campaign(seed, max_turns=12), CampaignAxisPolicy(), CampaignCommonwealthPolicy())
    sig = hashlib.sha256(engine.determinism_signature(res.events).encode()).hexdigest()[:12]

THE TRAP IS scenario.campaign's OWN max_turns KWARG. `campaign(seed, max_turns=12)` is NOT
`replace(campaign(seed), max_turns=12)`: the kwarg is passed on to _campaign_convoys,
_campaign_air_missions, _campaign_malta_interdiction and both halves of the Tobruk sea duel, each of
which builds its schedule over the horizon it is given (and the convoy schedule is seeded), so the
truncated build and the truncated clock are two different wars. On seed 1941 the two recipes give
DIFFERENT signatures on the very same tree -- which is exactly why an earlier gate exhausted a large
search space (max_turns 1-16, 18, 20, 24, 26, 30, 111, three policy pairings) and never hit. With
the kwarg, every row below -- the pre-change column included -- reproduces exactly, first try.

(Two hashes that stood here until 2026-08-02 were ROUND-ONE values this table then superseded, and
one of them was quoted as being "what this table says" when the table said no such thing. They are
struck rather than corrected: a worked example is not worth carrying if it has to be re-derived
every time the values below move. The RECIPE above is the durable part.)

Each Water Point is charged to the TOTAL CPA its counter raised anywhere in that whole Operations
Stage, i.e. the three cp_used raisers in apply.py: UNIT_MOVED, REACTION_MOVED, CP_EXPENDED.

MEASURED on this tree, the same four campaigns, every row reproduced twice byte-for-byte
(the numbers below are ROUND 2's -- see the round-2 entry beneath this one, which moved them):

    seed   vehicle Water Points   of which zero-CPA        vehicle WATER_SHORTFALL   52.51 refusals
    1941      6,999 ->   942         6,219 -> 30 (3.2%)        271 ->  60              132 ->  88
    7         7,175 ->   839         6,377 -> 29 (3.5%)        448 ->  80              245 ->  88
    4         6,965 -> 1,164         6,149 -> 39 (3.4%)        311 -> 110              162 -> 189
    2026      6,901 -> 1,208         5,796 -> 25 (2.1%)        365 ->  66               96 ->  87

    campaign signatures  1941 0716c0d9e327 -> 8e5ca52dca17    7    e76fa2c57be1 -> 312512305717
                         4    d12f8ddb0f0f -> f1c874bfbe7f    2026 bb9b353ecf79 -> 68be27e28f3f
    winner AXIS on all four seeds, before and after. This slice is not a balance change: the
    Commonwealth's surviving COMBAT units at Game-Turn 12 move 37/37/39/36 -> 34/37/36/41 -- down on
    two seeds, up on one, flat on one, which is chaos under a moved trajectory and not a bias.
    (That row previously read 312/312/314/311 -> 309/312/311/316 with no metric recorded beside it,
    and no reading of "surviving Commonwealth counters" reproduces it: measured on THIS tree the
    three candidates are 34/37/36/41 living combat units, 48/58/52/64 all living units, and
    380/390/384/396 counting every alive counter including the unarrived. So it is replaced by the
    one metric printed here with its expression:
    sum(1 for u in res.final.living(Side.ALLIED) if u.is_combat).)

THE RESIDUE IS NOT 52.42 AT ALL, and it was chased down rather than rounded off: all 30 of
campaign/1941's remaining zero-CPA vehicle Water Points are emitted in Phase.LOGISTICS, which is the
[52.6] ITALIAN PASTA RULE (engine._pasta_point, 1 Water Point per Italian battalion when Stores are
distributed) landing on Italian tank and gun counters. 52.6 carries no CPA condition and is not
touched here. Of the 52.42 leg proper, ZERO Points now go to a counter that spent no CPA.

A SMALLER RESIDUE IS DECLARED RATHER THAN FIXED: in _resolve_combat the water is drawn before
_charge_ammo, so an attacker that pays its water and is then found to have no ammunition has paid
for an assault it did not make. That ORDER is deliberate and pre-existing -- the `not _waterless(u)`
gate has always stood ahead of the ammo charge, and tests/test_water.py pins "a dry unit does not
even spend its load" -- so the alternative protects the nuisance commodity by spending the scarce
one. Measured at 36 Points on campaign/1941 to GT12 on the tree this entry was first written
against, 3% of that seed's vehicle bill; not re-measured in round 2, which does not touch the order.
The declaration now lives AT THE CODE as well as here -- _draw_stage_water's docstring carries it
under "A SECOND ORDERING NOTE, ON THE ATTACKER" -- because a reader of the call site would never
have found it in a baselines file.

A SECOND DEFECT WAS FOUND BY INSTRUMENTING THE CAMPAIGN, and it was one this slice introduced.
[19.68]'s rebuild and the [6.3] organization rows charge their Capability Points to the PARENT
FORMATION as well as to the unit, and a Parent may be a counter that has already been eliminated --
so on campaign/1941 to GT12 the first cut made four water draws for units that were not on the map,
one of which took real Water Points out of a dump for a DEAD Italian tank regiment. _draw_stage_water
now returns at once for any counter state.on_map rejects, which is exactly what state.living -- and
so the stage-start beat -- has always filtered on. It never fires on either benchmark (measured: 832
calls each, none off-map), which is why both signatures are unmoved by it.

NEUTER TABLE, per site, each neutered AT ITS OWN CALL SITE by rewriting that one call in
game/engine.py (never by patching _draw_stage_water, which would neuter every row at once and prove
nothing about any one of them -- the shared-helper mistake that shipped two untested guards in the
54.4 slice). RE-RUN IN FULL IN ROUND 2, every row RED: the listed tests in tests/test_water_cpa.py
fail with that one site inert and pass with it live, and the whole file is run per row so the
covering counts are measured rather than asserted.

    site                                                          covering tests   verdict
    _movement (8.1 + the 8.2 continual pulse)                            7          RED
    _react (8.51)                                                        2          RED
    _retreat_before_assault (13.21)                                      2          RED
    _resolve_combat armed_atk (the offensive Close Assault)              1          RED
    _spend_cp (every [6.3] combat CP + 10.36's forced retreat)           2          RED
    _reorganize.cp (the [6.3] organization rows)                         1          RED
    _rebuild [19.68]: the rebuilt unit's own draw                        1          RED  <- round 2
    _rebuild [19.68]: the PARENT Formation's draw                        1          RED  <- round 2
    _rebuild [19.68]: its LIVE-TOE re-read (bill the stale snapshot)     1          RED  <- round 2
    _blow_dumps ([54.14])                                                1          RED
    _build_dump ([24.9])                                                 1          RED
    _water_distribution: the vehicle no longer billed at stage start     1          RED
    _water_distribution: the vehicle RESTORED at stage start             1          RED
    _draw_stage_water's on_map guard (a destroyed Parent drinks nothing) 1          RED
    _draw_stage_water's _models_full_logistics scenario gate             1          RED
    _can_fuel_move at its _movement call site ([49.15] before [52.42])   1          RED  <- round 2
    _water_billed's (turn, stage) self-expiry                            2          RED  <- round 2

ONE TRAP IN RUNNING THIS TABLE, recorded because it produced a wrong table once. Python's
source-mtime .pyc check is (whole seconds, byte size), so two rows whose neuters change engine.py by
the SAME number of bytes inside the same second reuse the previous row's bytecode -- which is how
the _retreat_before_assault row first reported the _react row's failures. The harness now deletes
game/__pycache__ and runs each row under PYTHONDONTWRITEBYTECODE=1.

THE SCENARIO GATE IS NOT A CAMPAIGN GATE, and the distinction matters because CLAUDE.md rule 6
forbids the other kind. _models_full_logistics is the gate that ALREADY governs the whole of rule 52
-- engine._water_body returns at once for a scenario that seeds no Stores and no Water, so no
counter in one is ever dry -- and the new draw honours the same one. Without it a board that models
no water would immobilise every vehicle on it out of a commodity it does not have. Both benchmark
scenarios DO seed water (3,700 Points) and are fully in force here; that is why they moved.

FULL-REVERT PROOF: git-stashing game/engine.py and game/supply.py (the only two files changed)
reproduces d889e5b21c4e / 1f826374a883 EXACTLY, and reproduces all four pre-change campaign
signatures above, so this change and nothing else explains the move. Determinism holds: both new
benchmark signatures were read live twice, byte-for-byte. RE-CHECKED IN ROUND 2 from a clean
worktree at HEAD: the pre-change column (0716c0d9e327 / e76fa2c57be1 / d12f8ddb0f0f / bb9b353ecf79,
and 6,999 / 7,175 / 6,965 / 6,901 vehicle Points at 88.9% / 88.9% / 88.3% / 84.0% zero-CPA, 271 /
448 / 311 / 365 shortfalls, 132 / 245 / 162 / 96 refusals) reproduces to the digit under the recipe
above.

NAMED DEBT, PRE-EXISTING AND UNTOUCHED: 52.42 bills "or Truck Point", and the 2nd/3rd-line convoys
are TruckFormations rather than Units, so they lie outside every rule-52 draw this engine makes --
as they did before, when the stage beat also walked state.living(side). A unit's OWN first-line
lorries are billed (is_first_line_truck is on the counter, and supply._is_vehicle_type reads it).

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED 2026-08-02 (ROUND 2 OF [52.42]) -- THE PER-STAGE LEDGER LEAKED, AND TWO GUARDS AND
A STALE STRENGTH ARE NOW PINNED. The two benchmark signatures do NOT move and are NOT re-baselined:
ca0eec96abbd / 76371e5939a0 were read live on this tree and on the round-1 tree with the recipe at
the head of this file (seed 42, axis=allied=ScriptedPolicy(AXIS)) and are byte-identical. The FOUR
CAMPAIGN signatures above DO move, and the entry above carries the round-2 values.

THE LEAK. The [52.42] ledger was cleared by a line inside run()'s `for stage in (1, 2, 3)` loop --
the exact shape this engine rejects BY NAME twice, in _port_tons ([55.3]) and _Run._expire_rail_stage
([54.43]), each saying "any caller that drives the stages itself -- a test, a measurement driver --
would otherwise silently inherit a spent budget". It leaked two ways, both measured:

  * OUTSIDE THE LOOP, INSIDE run(). _replacement_spend -> _rebuild -> _draw_stage_water is a
    GAME-TURN-level beat, before the stage loop, so it read the PREVIOUS Game-Turn's Operations
    Stage 3 ledger: on campaign seed 4 to GT12 one vehicle's bill was suppressed outright
    (IT-Trvli---LTC, turn 7), on seed 7 another (IT-II(M)---LTC, turn 9). Conversely a bill TAKEN
    there was wiped by the stage-1 reset while cp_used was NOT (apply._reset_opstage fires at
    TURN_ADVANCED, before it), so one counter could be billed twice inside one 6.16 CPA window.
  * IN ANY CALLER THAT DRIVES THE STAGES ITSELF, which is every test in tests/test_water_cpa.py:
    drive two Operations Stages by hand and the tank pays 3 Water Points in stage 1 and moves in
    stage 2 for free.

THE FIX is the _port_tons pattern exactly: engine._water_billed(r) stamps on (r.state.turn,
r.state.stage) and expires on read and on write; the reset is deleted from the stage loop. The
stamp is cp_used's OWN window, which is what makes the two agree -- TURN_ADVANCED folds
turn=N+1, stage=1 and clears cp_used together, so the turn-level rebuild and Operations Stage 1
share one CPA window and now share one Water bill. Pinned by two tests that never enter run().

THREE GUARDS THAT SURVIVED THEIR OWN NEUTER ARE NOW PINNED, each proved at its own call site (the
last four rows of the neuter table above): _rebuild's two [19.68] draws -- deleting BOTH left the
whole suite green and both signatures unmoved -- and _can_fuel_move, the helper added to fix a
measured 23%-of-bill defect, which had no test at all and was watched only by a chaos-sensitive
campaign witness in tests/test_rail_control.py.

AND ONE MORE UNDER-BILL, found by the same pass: _rebuild drew the water on the CALLER'S pre-rebuild
snapshot, though UNIT_REBUILT had already folded and 52.42 bills "Each TOE Strength Point". Seven
settlements on campaign/1941 to GT12 were billed on a stale TOE, every one an under-bill (e.g.
IT-LXIII(L)---LTC billed 4 at a live 6). It re-reads live now, as the sibling parent draw always did.

MEASURED CONSEQUENCE, the four campaigns of the entry above, round 1 -> round 2: vehicle Water
Points 932 -> 942 / 818 -> 839 / 1,150 -> 1,164 / 1,201 -> 1,208 -- the suppressed bills coming back
plus the stale-TOE shortfall. Zero-CPA Points unchanged at 30/29/39/25 (the [52.6] Pasta residue,
untouched). Winner AXIS on all four, and the surviving Commonwealth combat units are IDENTICAL
before and after at 34/37/36/41: this repair costs the balance exactly nothing. Determinism holds --
all four campaign signatures and both benchmark signatures were read live twice, byte-for-byte.

NOT FIXED HERE, NAMED AS DEBT (CLAUDE.md rule 4). [19.68]'s CP_EXPENDED for the parent formation is
emitted unconditionally, so a dead Parent has cp_used folded onto a destroyed counter -- seen live
at campaign(seed=4) GT7 stage 1, IT-LTC with alive=False and on_map=False. The 52.42 leg is right
(the draw returns at once for a counter state.on_map rejects); the CHARGE predates this slice and is
flagged at the site in engine._rebuild.
    PAID 2026-08-03 -- see the entry at the top of this file. Measured at 66-148 rows per full
    campaign before the repair and zero after, and proved inert by log-diff on seed 7.

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED 2026-08-01 (THIRD ENTRY OF THE DAY) -- CAUSE: [25.14] FORTIFICATIONS, the campaign
gate removed and the invented magnitude replaced by the [41.5] chart. The two benchmarks do not
move. The CAMPAIGN does, on one of three measured seeds, and this is where that is written down.

    d889e5b21c4e / 1f826374a883   (UNCHANGED -- and the REASON is the finding, see below)

WHAT CHANGED IN THE ENGINE. Three things, all named by [25.14] and none of them a magnitude anyone
chose:

  1. THE GATE IS GONE. `GameState.siege_rules` gated both of 25.14's channels (engine._batter_fort
     and engine._air_fort). It was set by exactly ONE scenario (siege_of_tobruk) and never by
     campaign(), so across the 60 full campaigns Gate C measured, the fortification level of Tobruk,
     Bardia and Benghazi was a CONSTANT 2 for 111 turns and the [8.37] -3 close-assault shift it
     confers was irreducible by any action either player could take. Section 25 was then read off the
     scan in full (PDF p.38) and carries no scenario, campaign or optional-rule condition of any
     kind. Its own default comment said the quiet part -- "Default OFF / empty keeps the canonical
     benchmark exact" -- which is the exact debt CLAUDE.md rule 6 names. The field is deleted, not
     defaulted True: a flag whose only true value is True is not a flag.

  2. THE MAGNITUDE IS A PRINTED CHART. `BARRAGE_HITS_PER_FORT_LEVEL = 1` made every effective barrage
     flatten a level with certainty, and its own comment described itself as a knob "the lead tunes
     with the benchmark harness". [12.53] sends a facility barrage to the [41.5] Air Bombardment and
     Secondary Barrage Targets Table on the Artillery-Barrage-Points scale; [41.37] sends the B-F/C
     bombing mission to the same row on the Bomb-Points scale ("IF THE PLAYER OBTAINS A RESULT..."),
     and engine._air_fort had been taking a level with no die at all. That row is transcribed off a
     300-dpi render of chart folio 12 (PDF p.107) into data/logistics_rates.json and read by
     game.fortifications. A 9-Actual-point concentration now takes a level on 15 of 36 codes; it used
     to take one on 36 of 36. The Barrage-Points index scale is misprinted in the 1979 book (two
     cells run together, the last band's "2" dropped) and is corrected under a NAMED ERRATA KEY, the
     supply_dump_demolition_54_17 precedent -- never silently.

  3. THE TARGET IS DESIGNATED. [12.51] "Artillery may be used to Barrage facilities, RATHER THAN
     actual units"; [12.52] "the Target designated is the specific facility". The engine battered the
     wall as a SIDE EFFECT of a barrage aimed at a unit, which also meant [12.31]'s own exception
     could never fire -- an EMPTY enemy fortress was unbarrageable. A battery now declares one or the
     other, and which it declares is FLAGGED DOCTRINE (game.fortifications.barrage_target), because
     no Policy in this engine can order a barrage of any kind at any target.

WHY THE SIGNATURES DID NOT MOVE, AND WHY THAT IS THE FINDING RATHER THAN A DISAPPOINTMENT. Neither
benchmark scenario ever puts a gun beside a wall. MEASURED (seed 1941, re-measured 2026-08-02 and
CORRECTED -- this entry said 63): the nearest Axis battery opens 69 hexes from Tobruk and has closed only to 31 under
ScriptedPolicy(AXIS)+ScriptedPolicy(ALLIED), and to 63 under the axis=allied=ScriptedPolicy(AXIS)
pair the benchmark SIGNATURES are hashed with -- in rommels_arrival and siege_of_tobruk alike. The
conclusion is the same at either distance: no gun is ever adjacent to a wall, and both benchmarks
fire zero FORT_BARRAGED and zero FORT_REDUCED. So
siege_of_tobruk -- the scenario NAMED for this rule -- had never battered a fortification in this
repo's history either, gate or no gate. The gate
had been hiding behind a distance the whole time. A benchmark signature proves determinism and
nothing else, and this entry is the clearest case of it the project has: a rule can be dead for 111
turns of every campaign while both fingerprints stay byte-identical.

THE CAMPAIGN, MEASURED ON THREE FULL 111-TURN WARS (scripted policies, the Gate C arms):

    seed 1941   6 facility barrages, ALL Commonwealth: 3 on Tobruk, 3 on Bardia.
                Bardia 2 -> 1 (one reduction). 288,267 -> 288,402 events.
    seed 7      0 facility barrages.   284,545 events, unchanged.
    seed 4      0 facility barrages.   283,299 events.

    Air B-F/C missions across all three: ZERO. No Policy method in this engine ever constructs an
    AirMission -- kind="fort" is built only in tests and in two static scenario schedules, both
    kind="port" -- so the air half of 25.14 is correct, tested, and driverless. Declared debt.

    NO VICTORY CITY CHANGED HANDS, and the Axis still wins all three. This slice does NOT solve what
    Gate C found. It removes the gate and the invented number that were masking the real constraint,
    and the real constraint is PROXIMITY: on two of three seeds the Commonwealth never once stands a
    gun next to a fortification in 111 turns. That is reported, not tuned away.

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED 2026-08-01 (SECOND ENTRY OF THE DAY) -- CAUSE: [54.35] ON THE COMMONWEALTH RAIL
LANE, the named debt the 54.3 slice below did not pay. The two benchmarks do not move; the CAMPAIGN
does, on all four measured seeds, and this is where that is written down.

    d889e5b21c4e / 1f826374a883   (UNCHANGED, and for the structural reason the entry below gives:
                                   neither benchmark scenario seeds a railway at all)

THE DEFECT. engine._rail_deliver emitted its SUPPLY_ARRIVED and never called
_Run.record_rail_landing, so engine._rail_free_points -- the [54.35] ledger -- read a Commonwealth
station as holding its freight FREE the instant the train set it down.

    [54.35] "Like personnel, supplies may be moved from any one spot and dumped in another spot.
            Supplies are considered unloaded when they reach a specific hex. THEY MAY NOT BE MOVED
            THAT OPERATIONS STAGE."

engine.run puts _naval_convoys (which lands the train) at the HEAD of an Operations Stage and
_truck_convoys at the FOOT of it, so the window was open in every Operations Stage of every campaign.
The AXIS borrower has honoured the same rule since the 54.4 slice, at three call sites (a second rail
haul, a coastal ship's load, a lorry's load) -- so 54.35 bound the borrower of the railway and not
its owner, which is exactly what [54.46] forbids ("All rules concerning the movement of
troops/supplies and the use of the railroad that apply to the Commonwealth apply equally to the
Axis"). _rail_free_points' own docstring named the Commonwealth lane as declared debt.

THE FIX is one line beside the emit -- r.record_rail_landing(dump.id, commodity, qty) -- into the
ledger that already existed. NEUTERED AT ITS OWN CALL SITE (not through a shared helper, which is
the mistake that shipped two untested guards in the 54.4 slice), it kills exactly two tests and
nothing else: tests/test_rail.py::test_a_lorry_may_not_lift_what_the_commonwealth_train_has_only_
just_set_down and ::test_54_35_on_the_commonwealth_lane_pins_the_freight_and_not_the_station, both
hand-built one-station convoys rather than campaigns.

MEASURED, full 111-turn campaigns, four seeds, the pre-repair tree against this one. Every row was
run TWICE on each tree and reproduced byte-for-byte, and the four "before" signatures are exactly the
four the entry below recorded, which is the cross-check that this table is measuring what it says:

    seed   signature                 lorry lifts REFUSED (54.35)   CW rail Points LANDED
     4     0da89e99e965 -> 21870cb7d03f        0 ->  64            1,496,625 -> 1,496,625
     1941  30faefcceb35 -> dc90c6d39a3d        0 -> 112            1,496,625 -> 1,496,625
     7     31edc8e88669 -> 8bbf644def83        0 ->  53            1,496,625 -> 1,496,625
     2026  35cf55b02acf -> 48354c800ca6        0 ->  89            1,496,625 -> 1,496,625

THE REFUSALS WERE ZERO BEFORE, on every seed, which is the defect stated as a number. THE TONNAGE IS
UNTOUCHED, to the Point, on every seed -- 1,496,625 is exactly the schedule's own arithmetic
(111 x 375 Ammunition + 111 x 12,000 Fuel + 82 x 1,500 Stores), so the railway still lands every
Point it ever landed. What changed is only WHEN it may be picked up again. The Commonwealth lorry
pool's activity moves in BOTH directions across the four seeds (TRUCK_MOVED 412->615, 316->261,
1062->752, 813->422), which is chaos under a moved trajectory, not a bias.

Also re-measured on both trees, because the [54.43] census below was written on the pre-repair one:
seeds 1-24 to Game-Turn 16 activate a locomotive on 13 (unchanged, {3, 5, 6, 9, 10, 11, 12, 14, 15,
17, 21, 22, 24}) and run trains on 7 -> 8, seed 12 joining {3, 9, 11, 14, 17, 21, 24}.

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED 2026-08-01 -- CAUSE: [54.32]/[54.33]/[54.34], THE COMMONWEALTH RAILWAY'S
PER-OPERATIONS-STAGE SCHEDULE. Recorded here because a NON-move of the two benchmarks alongside a
large, measured move of the CAMPAIGN is exactly what this file exists to write down.

    d889e5b21c4e / 1f826374a883   (UNCHANGED, verified live after the change, each twice)

THE DEFECT. game.scenario._campaign_rail_cargo built ONE manifest per Game-Turn carrying AMMUNITION
AND FUEL AND STORES TOGETHER -- 4,500 tons, 3,000 on month-start turns -- and engine._unload_convoys
landed the whole of it in Operations Stage 1. Measured over full 111-turn campaigns on seeds 1941, 7
and 2026: Operations Stages 2 and 3 received NOTHING, ever, on any turn, in any campaign. Against a
book that prints two things and this engine obeyed neither:

    [54.32] "The Commonwealth supply capacity of the railroad is 1500 tons per Operations Stage in
            either direction."
    [54.33] "The railroad may transport only one type of supply at a given time. It may move fuel,
            ammunition, or stores -- not any combination of the three."

It is the SAME defect already found and fixed on the Axis side of the same railway (54.43).

THE FIX, and it moves the BEAT and not the TONNAGE. game.supply now owns the whole schedule
(RAIL_TONNAGE_54_3 / rail_haul_cap / RAIL_COMMODITIES_54_33 / rail_stage_commodity / rail_stage_load
-- the single source 54.46 already shares with the Axis borrower); _campaign_rail_cargo is the SUM of
the turn's live stage-loads; engine._unload_convoys lands ONE of them per Operations Stage; and
scenario's `if calendar.is_month_start(gt): stages.remove("STORES")` -- an independent second
encoding of 54.34 -- is deleted in favour of game.rail.dead_opstages_54_34, so both sides of the
board now stand the railway down through one function instead of two that happened to agree.

MEASURED, per Game-Turn OFFERED (before -> after): UNCHANGED, exactly. 4,500 t on an ordinary week
(375 Ammunition + 12,000 Fuel + 1,500 Stores), 3,000 t on the calendar month's first Game-Turn.
MEASURED, per OPERATIONS STAGE LANDED (seeds 1941 / 7 / 2026, GT1-111):

    before   stage 1: 111 of 111 turns, ~4,100 t/turn   stages 2 and 3: ZERO, all 111 turns
    after    stage 1: 111, stage 2: 111, stage 3: 82 (111 - 29 dead stages, one per calendar month)
             every landing exactly 1,500 t of exactly ONE commodity

Total LANDED rises 455,158-455,176 t -> 456,000 t over the war (+0.2%), and that is not new supply:
it is the same offered tonnage no longer being clipped by the 54.12 dump ceilings it used to hit
when a week's freight arrived at one stroke.

THE CAMPAIGN LOG MOVES UNDER IT, and the campaign is not signature-pinned (see CAMPAIGN_SEED below):

    campaign/4     1aaf0a218044 -> 0da89e99e965      (reproduced twice, byte-for-byte)
    campaign/1941  760a2fe14961 -> 30faefcceb35
    campaign/7     789f4281fc3b -> 31edc8e88669
    campaign/2026  82cd21d91529 -> 35cf55b02acf

NO ATTRIBUTION TABLE, because there is nothing separable to attribute: the manifest and the unloader
are two ends of one wire. Neutering either alone does not restore the old behaviour, it produces a
state this repository has never been in -- a week's manifest dribbled out one third at a time, or a
stage-load landed three times over. The neuter that means anything is the whole change, which is the
diff.

WHY THE TWO BENCHMARKS DO NOT MOVE, measured rather than assumed: neither rommels_arrival nor
siege_of_tobruk seeds the Commonwealth rail line at all. Convoy.rail is False on every convoy either
scenario carries and state.terrain.rails is empty in both, so engine._unload_convoys never enters the
branch this change rewrites (tests/test_rail.py::test_railless_scenario_byte_identical pins the
property directly). Both signatures were re-read live after the change and are the values above.

TWO CONSEQUENCES ELSEWHERE, both real, both recorded where they live rather than here:

  * THE EIGHTH ARMY HOLDS MERSA MATRUH. Fed three times a week instead of once, the Commonwealth
    keeps its own railhead at CAMPAIGN_SEED where it used to lose it on Game-Turn 3 -- the exact
    cascading failure the CAMPAIGN_SEED note below calls "THE FINDING". MEASURED at GT12/GT30:
    control AXIS -> ALLIED, no railhead retraction at all, AL-Stage-Matruh 0 -> 7,824 Fuel, the
    lorry pool 42 -> 100 moves and 14 -> 64 unloads. Three campaign-narrative tests carried
    tripwires reading "update this restatement, the finding reversed"; all three fired and are
    restated in place (test_campaign_concentration.py x2, test_campaign_claim.py).
  * THE AXIS LOSES HIS ONE MEASURED LOCOMOTIVE AT SEED 4, and the reason is 54.33 itself. He was
    buying it with COMMONWEALTH STORES CAPTURED AT AL-STAGE-ELDABA (32.13); a station only stood
    stocked in all three commodities at once because the mixed train put them there. Swept over
    seeds 1-24 to Game-Turn 16, THIRTEEN campaigns still activate ({3, 5, 6, 9, 10, 11, 12, 14, 15,
    17, 21, 22, 24}) and seven still run trains ({3, 9, 11, 14, 17, 21, 24}), so 54.4 is better
    measured, not less reachable -- tests/test_rail_control.py's campaign witness is re-pinned 4 -> 9,
    where the payer is the Axis's OWN forward dump. (CORRECTED 2026-08-01 by the review repair below,
    which re-swept the same window twice on this very tree: the count written here was "12 campaigns",
    and thirteen is what the sweep returns. The seven is exact for this tree. The repair's own tree
    reads 13 and 8 -- see its entry above.)
--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-31 -- CAUSE: the 22.3 REVIEW REPAIR. The adversarial review of the slice below
found four real rule defects in it; three move both benchmarks, the fourth is measurably inert, and
all four are attributed separately below.

    34e439545995 / 9c3565293760  ->  d889e5b21c4e / 1f826374a883

CAUSE B -- THE FIELD FALLBACK WAS MISSING, which made a Facility hex REPAIR LESS than the book
allows. engine._repair routed every broken vehicle/truck on a Major Facility hex into the Facility
path with no alternative, and that path simply returned when 22.35's 1 Fuel + 1 Stores per point
could not be paid. The book never makes Facility Repair mandatory or exclusive: 22.32 says such a
vehicle "MAY undergo Repairs", and 22.22 grants Field Repair "in ANY hex in which there is a Broken
down vehicle stacked with a Friendly unit of any type", excluding no Facility hex -- and the [22.15]
chart makes Field truck and AC/Recce repair FREE, so a Player on a drained Tobruk still has the
22.23 die by right. MEASURED on the shipped code: 4 of 34 facility truck-repair calls per benchmark,
209 broken Truck Points, now roll that free die where the slice below repaired nothing. The false
premise that licensed the routing ("no rational Player would ever prefer Field's worse odds when a
Facility is available") is deleted from the docstring with the behaviour.

CAUSE C -- NO PARTIAL ATTEMPT, against 22.35's own last sentence ("He may attempt to repair only
those points he has expended supplies for") and 22.26's verbatim twin for the Field tank's Fuel.
Both pre-paid the whole broken pool or nothing. engine._prepay_repairs now pays for as many points
as the hex can fund and the die's percentage applies to the points ATTEMPTED (22.25's "undergoing
repair"), which is also where the single-TOE 10% exception now keys.

CAUSE D -- ONE DIE PER COUNTER WHERE THE BOOK ROLLS ONE PER TYPE PER HEX (22.33). 22.24 is explicit
-- "the Player rolls one die for ALL the A/C's and Recce points in the hex" -- so AC/Recce now pool
per hex and per nationality (22.14: the Axis repairs German separately from Italian), exactly as
Truck Points already did under 22.23. TANKS DELIBERATELY DO NOT POOL and that refusal is reasoned in
game.repair's module docstring: 22.25 rolls per tank TYPE, this engine keeps no per-counter tank type
at play time, and grouping on oob.MODEL_DEFAULTS (one default per nationality+role) would MERGE the
types the book separates -- a larger error in the opposite direction, and an invented attribute the
order of battle does not print. On these two benchmarks the pooling itself never fires (measured:
zero hexes ever hold two broken AC/Recce counters of one nationality), so D's whole contribution
here is the ORDER in which counters draw from the repair stream, which the per-hex/per-type grouping
changes.

CAUSE A -- 22.13a's MAJOR-FACILITY EXCEPTION WAS DROPPED, and a test in the slice below enshrined
the inverse ("22.13a applies to a Major Facility exactly as it does to Field Repair"). The book:
"If the vehicles to be Repaired are in an Enemy-controlled hex... The only exception to this is if
the vehicles are in a Major Repair Facility, in which case the presence of an Enemy Zone of Control
has no effect", doubled by 22.37. Fixed, and the test restated to assert the printed rule. Note that
state.control_of is territorial last-sole-occupier control, not the book's ZOC-controlled hex (10.0),
i.e. a STRICTER proxy than the thing 22.13a exempts; the exemption is applied to the proxy because
the proxy is what stands in for 22.13a here. IT MOVES NEITHER BENCHMARK, twice over (below).

ATTRIBUTION, MEASURED (seed 42, ScriptedPolicy(AXIS) both sides, every row reproduced twice
byte-for-byte; the neuters patch the symbols the CALLER resolves -- engine._repair looks up
_facility_repair_units/_facility_repair_trucks and those look up _prepay_repairs as module globals
at call time, so assigning them on game.engine reaches the live call sites, unlike the
`from X import name` trap recorded further down this file):

    live (A+B+C+D)                                        -> d889e5b21c4e / 1f826374a883
    NEUTER B -- the field fallback off (a facility group
      that cannot pay claims the attempt anyway)          -> 684c9d8b0fd9 / 64ed1e7d2a70
    NEUTER B+C -- and the pre-pay back to all-or-nothing  -> c2ca2af11b88 / d96651673d90
    NEUTER B+C+D -- and engine._repair back to one die
      per counter in global id order                      -> 34e439545995 / 9c3565293760  (= OLD)
    NEUTER B+C+D+A -- and 22.13a re-applied to Facility
      hexes (the full behavioural revert)                 -> 34e439545995 / 9c3565293760  (= OLD)

So B, C and D each move both logs, the three together fully explain the move (B+C+D reproduces the
old baseline EXACTLY, so nothing else in this repair touches either log), and CAUSE A IS INERT ON
BOTH BENCHMARKS -- proven twice, once by the identical B+C+D and B+C+D+A rows and once by
instrumenting the live runs: zero facility repairs occur in an enemy-controlled hex on either log.
The 6 Alexandria facility calls a 36-turn campaign/4 makes (CampaignAxisPolicy vs
CampaignCommonwealthPolicy) are all funded in full, so none of B, C or A fires there either.
--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-30 -- CAUSE: rule 22.3 FACILITY REPAIRS (the Tier-2 slice), which lands with
one adjacent, pre-existing bug fix in the same function it restructures. SUPERSEDED by the review
repair above, which moved these two hashes again; the account below is kept because its two causes
are still live in the engine and its neuter table is still the proof of THAT move.

    87f3baeb4530 / b2a2f8bf6ab9  ->  34e439545995 / 9c3565293760

CAUSE A -- FACILITY REPAIR ITSELF. engine._repair now routes a broken-down vehicle standing on a
Major Repair Facility hex (22.31: Alexandria/Cairo/Tobruk, "already in existence" per 24.81 --
game.repair.major_facility_hexes) onto the 22.34 Facility die column instead of the 22.8 Field one
-- a different (better) percentage, a different (1 Fuel + 1 Stores per point, 22.35) cost, and no
weather gate (22.36). Tobruk (C4807) is a Major Repair Facility in EVERY scenario, including both
benchmarks, so any unit that breaks down while standing there now repairs differently than before.

CAUSE B -- THE ADJACENT BUG. Field Repair's tank/SPA Fuel draw (22.26, "present in the hex") was
reading supply.plan_draw -- rule 32.16's ABSTRACT ½-CPA trace, the exact bug class CLAUDE.md names
("the ½-CPA supply trace... has bitten this project twice"). Facility Repair (22.35, same "present
in the hex" wording) needed the correct supply.in_hex_draw regardless, and since this change already
restructures engine._repair function-by-function, the adjacent Field-tank draw was corrected in the
same pass rather than left inconsistent beside new code that gets it right. A tank funding its field
repair from a dump within half-CPA but off its own hex now correctly goes unfunded.

NEUTER-PROOF (seed 42, ScriptedPolicy(AXIS) both sides, each figure reproduced twice):

    live (A+B)                                                    -> 34e439545995 / 9c3565293760
    NEUTER A -- engine.repair.major_facility_hexes patched to
      return frozenset() (B still live)                           -> 9a6d888d6ae8 / 7f7bb79ef3c4
      i.e. NEITHER benchmark reproduces the old baseline with A alone neutered: B independently
      moves both logs too, so this is a two-cause move, not one masquerading as one.
    git-stash of every file this change touches (repair.py moved
      aside, engine/combat_tables/dice/breakdown_rates.json
      reverted) reproduces the documented OLD baseline exactly     -> 87f3baeb4530 / b2a2f8bf6ab9
      (the clean, whole-file neuter -- patching supply.in_hex_draw in-process to fall back onto
      plan_draw was tried FIRST and rejected: it also touches the movement-fuel/stores-distribution/
      ammo-draw call sites this change never modifies, which is a false neuter, not a true one --
      recorded so the trap is not re-walked-into next time this file needs a partial-B neuter).

Determinism holds: every figure above reproduces byte-for-byte across two runs. Full accounting,
scan cites and the two owner-visible chart-vs-prose rulings (the 22.34a die-modifier footnote; the
24.8 Construction Chart's Fuel/Op-Stage figures, moot because 24.8 stays unbuilt) live in
scratchpad/port/transcriptions/22.3-cw-rear-area-recovery.md and game/repair.py's module docstring.
--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-26 (FOURTH MOVE THE SAME DAY) -- CAUSE: the [8.45] DESERT REVIEW REPAIR, whose
first repair was to THE ENTRY THAT USED TO STAND HERE. That entry read "NOT RE-BASELINED... the
honest shape of a faithfully-transcribed rule with no live consumer yet", on the strength of a grep
that found no Unit and no TruckFormation carrying Mobility.LIGHT_TRUCK or MOTORCYCLE. THE GREP WAS
RIGHT AND THE CONCLUSION WAS WRONG: both classes the rule names exist in this engine today, and
[8.45] had been landed at a seam where neither of them lived.

    abc4300eccbb / a5da9203198d  ->  87f3baeb4530 / b2a2f8bf6ab9

CAUSE A -- LIGHT TRUCKS. game.supply.reachable_truck_moves pathed EVERY convoy at SUPPLY_MOBILITY
(Medium) whatever its own 54.2 truck_class, on a comment claiming "the classes differ only in
Breakdown Points, so the chosen path is the same". True until [8.45] landed; false after it. The
book distinguishes the classes in a PROHIBITION as well as a price, in BOTH directions at once, and
a Light convoy was being routed around both rules: denied [8.44]'s Salt Marsh exemption ("Vehicles,
EXCEPT FOR LIGHT TRUCKS, Recce-type units, and motorcycle infantry...") and granted [8.45]'s Desert
("forbidden to Light Trucks"). Five campaign and two benchmark formations are Light. Fixed by
supply.TRUCK_MOBILITY, the same table that already chose the Breakdown class, now also chosen for
the path (and for truck_bp_for_move's path RECONSTRUCTION, which must agree with it or the 21.21
accrual is billed over a route the convoy was never allowed to drive).

CAUSE B -- MOTORCYCLE INFANTRY, WHICH THE OOB HAD MIS-TYPED TWICE. The 15th Kradschutzen Bn was
`motor_infantry` in data/reinforcements_campaign.json and `recon` in data/reinforcements_desert_fox.
json -- the same historical battalion, two different counters, neither of them the book's. Read off
the scan: [4.45c] (PDF p.162) prints "Kradschutzen = Motorcycle infantry"; the OA sheet (p.163)
gives the battalion ID Code 'g'; [4.46c] (p.137) gives 'g' as Infantry Bn-Eq, CPA 25, Close Assault
3/2, Max TOE 7; and a census of every ID Code on the German OA sheets finds 'g' on EXACTLY ONE
counter -- this one. Now typed `motorcycle_infantry` (data/unit_stats.json), which makes three
rules live on it at once: [8.44] marsh exemption, [8.45] desert bar, and [49.12] "Fuel users... do
NOT INCLUDE MOTORCYCLES" (which in turn corrected data/logistics_rates.json's engine_proxy, where
MOTORCYCLE read 1 against oob._fuel_role_default's 0 -- a disagreement nothing could see until the
class had its first counter).

ATTRIBUTION, MEASURED (seed 42, ScriptedPolicy(AXIS) both sides, each figure reproduced twice):

    live (A+B)                                            -> 87f3baeb4530 / b2a2f8bf6ab9
    NEUTER A -- supply.reachable_truck_moves/truck_bp_for_move
      restored to HEAD's bodies (every convoy at Medium)   -> 87f3baeb4530 / b2a2f8bf6ab9
      i.e. CAUSE A MOVES NEITHER BENCHMARK AT ALL
    NEUTER B -- 15 Krad back to `recon` in the desert-fox
      OOB (data, swapped in place), A still live           -> abc4300eccbb / a5da9203198d
      i.e. EXACTLY the old baseline: CAUSE B IS THE WHOLE MOVE, and A+B off is the old baseline too

A NEW INSTANCE OF THE NEUTER TRAP, recorded because it cost an hour and would have been published
as an attribution: the first Cause-A neuter flattened supply.TRUCK_MOBILITY wholesale to MOTORIZED.
That is not HEAD -- HEAD accrued a Light convoy's Breakdown Points at LIGHT_TRUCK (the 54.2 off-road
+1) while pathing it at Medium -- so the "full revert" measured 86263f0ce5c0 / e26a61c0e277, a state
that has never existed in this repository. The trap here is not the import binding but the SHARED
TABLE: neutering a symbol that two rules read neuters both of them. The published neuter restores
the two function bodies instead.

WHY CAUSE A MOVES NOTHING, MEASURED RATHER THAN ASSUMED -- because an unchanged signature is equally
consistent with dead code, which is precisely the error the entry above made. Instrumented over the
real runs: reachable_truck_moves is asked for a LIGHT convoy 76 times in rommel/42 (56,553 hexes of
light reach flooded) and 2,433 times in campaign/1941 (1,557,322 hexes); the code is hot. What the
scripted convoy dispatcher never did was CHOOSE a Desert destination: light TRUCK_MOVED events
ending in a Desert hex number ZERO both before and after the repair, in all three scenarios. So
[8.45]'s bite on convoys is a reach/graph restriction, not a stream of lorries that had been
crossing the sand sea. It is not inert either -- in campaign/1941 the repair moves light convoy
relocations 784 -> 768, the [8.44] marsh exemption and the [8.45] bar together redrawing which hex
the dispatcher picks. The two benchmark scenarios each make only 4 light convoy moves, all
identical under both graphs, which is the whole reason their signatures sit still.

CORRECTED FROM THE SAME ENTRY, since a log that silently edits itself is worthless: the min-vertex-
cut probe's 27 -> 13 reproduces (scratchpad/gate845_desert.py, independently re-run by the review),
but its framing did not. That widening to 27 is mostly the Qattara -- pre-gate the LIGHT_TRUCK cut
is WIDER than VEHICLE's 12 only because [8.44] exempts light trucks INTO the marsh -- so [8.45]
collapses light trucks back toward the vehicle floor rather than sealing a front, and the passable
width at El Alamein's own meridian moves only 30 -> 28. The direction was right; "the desert seals
Alamein" is not what the graph says.

GATE ADDENDUM 2026-07-26, NO SIGNATURE MOVE (a measurement, not a change -- game/ and data/ are
untouched; drivers scratchpad/gate845_front.py, gate845_ab.py, gate845_compare.py). The block gate
ran the FULL 111-turn campaign A/B, seeds 1941 7 4 24 2026 99 1, against the pre-slice tree
4a08f4d, plus a THIRD arm: HEAD's bodies with ONLY the Desert gate switched off (neutered at
game.movement.desert_barred -- step_cost is the rule's sole call site, and the neuter is proven
live by reading the patched symbol back inside all 7 folds, all False, against True in an
unpatched HEAD process). Two published claims are corrected by it:

  * THE DESERT GATE MOVES THE CAMPAIGN BY EXACTLY NOTHING. HEAD == the gate-off arm on all 7
    campaign signatures, and on every derived figure (events, truck moves, rejections, survivors,
    victory reason, Axis high-water, Axis position at war's end). The whole BASE -> HEAD campaign
    delta -- all 7 signatures move -- is Cause A + Cause B, not the bar. Which also refines the
    paragraph above: campaign/1941's light convoy relocations 784 -> 768 are the [8.44] MARSH
    EXEMPTION arriving through the truck-class pathing fix, ALONE. "[8.44] and [8.45] together
    redrawing which hex the dispatcher picks" credited the Desert bar with a share it does not
    have; measured, its share is zero. The rule is faithfully transcribed and correctly wired and
    the scripted dispatcher simply never asks it a question: light TRUCK_MOVED events ending in
    Desert are 0/0, and Axis GROUND moves into Desert are 0/0, on every one of the 7 seeds.

  * THE FRONT NARROWS IN THE DEEP SOUTH, NOT AT ALAMEIN, and the 27 -> 13 is now verified rather
    than merely computed: deleting each cut disconnects the sector, and every one of its hexes is
    load-bearing (restoring any single one reopens a route) -- for all 5 mobility classes, both
    arms. WHERE it runs: pre-gate the LIGHT_TRUCK cut is two runs, a 7-hex coastal shoulder at El
    Alamein (E3001..D2431) and a 20-hex wall (E2003..D0127) that terminates ON THE RASTER'S
    SOUTHERN EDGE. Post-gate the coastal shoulder survives UNCHANGED and the southern wall
    collapses to 6 scattered choke hexes, none touching the map edge. So the gate does not build
    the Alamein position -- the coastal shoulder is identical before and after, and identical to
    what VEHICLE already had -- it removes the light truck's 20-hex desert highway around it. The
    cheapest west->east route is 75.5 CP for every class in both arms, unchanged.
--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-26 (THIRD MOVE THE SAME DAY) -- CAUSE: Phase 8.1b Block B, the [8.35]/[8.42]
escarpment HEXSIDE trace landing (tools/vassal/extract_hexsides.py -> data/hexsides_<section>.json,
wired in game.cna_map._load_hexsides), plus a section-seam adjacency bug this slice found and fixed
en route (game.coords._SEAM_SHIFT). THREE separable causes, all real, attributed below:

    b4f2e8e2c955 / 6e74c608b476  ->  abc4300eccbb / a5da9203198d

CAUSE 1 -- THE A/B AND D/E SECTION-SEAM BUG. Block A's read-only recon (scratchpad/port/
hexside-trace.md Sec 6) found that unlike the C/D join (21 hexes, already coincide under the plain
raw-grid formula), the A/B and D/E joins number the SAME physical hex two DIFFERENT board-global
axials apart (confirmed by pixel proximity: the two labels' game.coords.to_pixel outputs sit 2-4 px
apart, the same hex redrawn twice at the section boundary, not two different ones). Because
game.coords.to_axial is what DEFINES adjacency (game.hexmap.neighbors' six axial directions), every
hex on the wrong side of that one-column/row gap silently lost its true cross-seam neighbour -- not
just the 49 duplicate hexes themselves. Caught by this slice's own min-vertex-cut probe
(scratchpad/hexside/corridor2.py), which found the WHOLE El Alamein sector split into two
disconnected halves at exactly the D/E line before the fix.

Fixed at the source: game.coords._SEAM_SHIFT adds a per-section constant IN AXIAL SPACE (after the
odd-q offset->axial conversion, not before it -- axial neighbours are parity-independent constant
unit vectors, so a whole-section translation there preserves every internal adjacency exactly,
unlike nudging the raw offset grid, which flips column parity and was caught distorting a purely
Map-B-internal neighbour pair 147 px apart during development, tests/test_coords.py's own
test_pixel_lattice_consistency). The correction CASCADES (B, C and D all carry the same constant,
E an additional one) because B/C and C/D already agreed natively; shifting only the section on one
side of a broken seam un-fixes whichever OTHER seam that section already had right. game.coords.
to_pixel, and therefore every already-verified terrain sample, is completely untouched.

Consequence, MEASURED: 6,741 land hexes on the full board -> 6,699 (42 fewer -- the phantom
duplicates merge, mirroring C/D's existing 21); the Alamein/Alexandria corridor distances in
tests/test_map_terrain_fills.py's GATE 3 each read one hex SHORTER (11 -> 10 at El Alamein, 26 -> 25
at Alexandria) because a BFS crossing the old D/E gap no longer pays for a phantom extra hop; GATE 6
duplicate count 21 -> 70 (21 C/D + 28 A/B + 21 D/E, all agreeing on terrain class, zero clashes).
Both restated in place, port rule 5, with the reason in the docstring -- they were pinning the bug.

CAUSE 2 -- THE ESCARPMENT TRACE ITSELF. 194 hexsides traced, of which 189 load (5 have a down or an
up hex that colour-sampled as sea and are dropped rather than invented into land), i.e. 378 directed
UP_ESCARPMENT/DOWN_ESCARPMENT entries after Cause 1's fix -- 79 of them inside the ABC benchmark map
that rommels_arrival AND siege_of_tobruk both load (siege_of_tobruk is an ABC scenario, not a
single-section C one; a genuine C-only load carries 38). They go from `{}` (dead since
TerrainMap.hexsides was introduced) to real data for the first time, so FOUR consumers go live on
the real map at once: movement.step_cost's hexside CP, movement.breakdown_points' hexside BP,
zoc.py's ZOC_BLOCKING_HEXSIDES, and engine._assault_hexside_shift's [15.33/15.35/15.36] close-assault
differential. [8.42]: "No vehicle may ever move up an escarpment" -- and it really is unconditional,
road or track, because [8.33] excepts exactly this case from the road/track ignore-the-terrain rule
("...with the exception of vehicles crossing Escarpments (see 8.42)"); the code did NOT encode that
exception when this note first claimed it did, and now does (movement._escarpment_vehicle).
[8.35]: the escarpment symbol (solid band + splash) is drawn wholly on the DOWN side, confirmed
three independent ways (the rule's own words, PDF p.14; two ground truths of OPPOSITE compass sign,
the Mediterranean coast and the Qattara Depression floor; the named Sollum/Halfaya Pass escarpment,
every traced tick pointing out to sea) -- see scratchpad/port/hexside-trace.md and
tools/vassal/extract_hexsides.py's own docstring for the full extraction spec (exact-colour mask,
sample/accept thresholds, all measured not chosen).

MEASURED, not assumed: landing the rim changes NEITHER the Alamein sector's minimum vertex cut
(20 hexes for VEHICLE/MOTORIZED, 30 for FOOT, identical with and without the escarpment hexsides)
NOR the cheapest coastal motorized route's cost -- the Qattara rim sits entirely on the depression's
own north face, four hexes west of El Alamein's meridian, and only UP_ESCARPMENT/MAJOR_RIVER are
ever prohibited to a vehicle in the whole [8.37] table, so an army simply walks around the
depression's eastern tip on ground the rim never touches. tests/test_hexsides.py pins this finding
directly (test_the_alamein_rim_does_not_narrow_the_front). The Block-A premise "8.1a is the floor,
8.1b is the wall" is therefore false, and is recorded as such, not quietly dropped: what DOES
narrow the front is [8.45]/[8.37] note 3 (light trucks/motorcycle units barred from Desert hexes
outright), which the engine does not yet carry -- flagged, not implemented, here.

CAUSE 3 -- STALE BAKED AXIALS IN data/reinforcements_desert_fox.json (rommels_arrival/
siege_of_tobruk's default reinforcement schedule) AND data/reinforcements_campaign.json (the full
campaign's). Both are NOT hex labels but raw `[q, r]` axial tuples, baked once by
tools/vassal/build_campaign_reinforcements.py (or, for the desert-fox file, an undocumented earlier
process -- no committed builder reproduces it) under WHATEVER game.coords.to_axial was in effect at
generation time. Cause 1 changed to_axial, so every such baked tuple in a B/C/D/E-section hex now
names a DIFFERENT physical hex than it did when it was written -- a unit's committed "hex" silently
points 1 axial-row/column away from where it was actually meant to sit, with NO error, because the
new coordinate is usually still on the map (56/56 desert-fox, 541/541 campaign entries land on real
terrain either way -- confirmed, not assumed). Caught by tests/test_campaign_culmination.py::
test_the_commonwealth_garrisons_every_hex_of_the_delta: the Polish Brigade's static desert-fox-style
placement (recomputed fresh here as [43, 141]) newly LANDED on Cairo hex E1931 (63.71's own auto-win
objective, freshly recomputed the same axial post-fix), occupying a Delta hex the standing garrison
order expects empty at t0.

NOT fixed by re-running build_campaign_reinforcements.py: it reproduces only 176 of the committed
campaign file's 541 records (the file has been hand-extended since, by process this script's current
form does not capture) -- confirmed by trial, then reverted. Fixed instead by a lossless, targeted
migration (scratchpad/hexside/migrate_reinforcement_axials.py, not committed -- a one-off): for each
baked axial, recover which SECTION it belonged to under the OLD (pre-Cause-1) to_axial (unambiguous
for all 8,484 mainland hexes -- verified before writing, every physical hex's candidate section(s)
agree on their _SEAM_SHIFT value) and add that section's shift, the exact inverse of what changed.
541/541 and 56/56 records preserved; only "hex" moved (363 of 541 campaign entries, 5 of 56
desert-fox); every migrated hex still lands on real terrain (541/541, 56/56, checked after writing).

ATTRIBUTION, MEASURED (seed 42, ScriptedPolicy(AXIS) both sides, each reproduced twice; and the
false-neuter trap from the slice above still applies for Causes 1-2 -- these patch the CALLER's
binding, and both game.cna_map._load_hexsides and game.coords._SEAM_SHIFT are read via module-
attribute access at call time, not captured by a `from X import name` at import time, so a plain
monkeypatch of the defining module's own name is sufficient here, unlike movement.py's hexside_cost/
salt_marsh_barred; Cause 3 is DATA, neutered by swapping the file back in, not by patching code):

    live (all three causes)                               -> abc4300eccbb / a5da9203198d
    NEUTER C -- reinforcements_desert_fox.json reverted to
      its pre-migration content, Causes 1-2 still live      -> 7ceeabbcdf35 / a38f6b2fe5f7
    NEUTER A -- (of the Cause-3-neutered state) hexsides off
      too, seam fix still live                              -> 0b3b2f0c4d6d / 614fb9ecca4e
    NEUTER B -- hexsides off AND seam fix off (game.coords.
      _SEAM_SHIFT cleared) = FULL REVERT                    -> b4f2e8e2c955 / 6e74c608b476
      (exactly the old committed baseline -- confirms all three causes together, and only together
      with every one of them reverted, fully explain the move)

Determinism holds: every value above reproduces byte-for-byte across two runs, live and neutered.

NOT RE-BASELINED 2026-07-26 (the 8.1b REVIEW REPAIR) -- recorded here because a NON-move is a
measurement too, and this one changed data and two rules without touching either signature:

    abc4300eccbb / a5da9203198d   (unchanged, verified live after every fix below)

  * THE ACCEPTANCE RULE WAS RE-DERIVED and the data RE-TRACED, 190 -> 194 hexsides. The first cut
    filtered the mask by connected-component size on a claimed "empty trough at max-inscribed-radius
    3-4"; re-measured, the trough is NOT empty (r=3: 4 components / 452 px, r=4: 3 / 1,355 px) and
    the filter dropped FOUR REAL band segments (the Qattara north rim at the notch west of El
    Alamein, the Qara rim, and the Tobruk and Tocra coastal escarpments -- band broken up by the
    vegetation and lettering glyphs drawn over it), a fifth going to a PEAK_MIN the filter had
    pushed one bin too high, while still admitting one edge the map does not orient at all
    (C3526/C3527: a band CORNER whose ink straddles the hexside, side-ratio 0.91). Component size
    does not separate band from lettering; SIDEDNESS does, and sidedness is [8.35] itself ("the
    splash contours ... are always on the 'down' side"), so the rule that ORIENTS an edge is now
    also the rule that ACCEPTS it: one-sidedness <= 0.5 (measured gap: 194 edges at <= 0.341, then
    nothing until 0.809 and 0.912, which are the map's own lettering and that corner). Every added
    and every rejected edge was rendered and read by eye off the raster.
  * [8.33]'s ONE EXCEPTION was missing, and this note used to assert the opposite of what the code
    did. "Units which are moving along Roads or Tracks ignore, for movement purposes, any other
    terrain in the hex or hexside, with the exception of vehicles crossing Escarpments (see 8.42)."
    movement.step_cost/breakdown_points negated the hexside term on any dry road, so the ONE traced
    escarpment that a road crosses (A5533/B5400, Tocra) let a vehicle drive UP it. Fixed.
  * [8.37]'s Up Escarpment ANTI-ARMOR "P" was live-but-unimplemented, the same class of gap 8.1a's
    review found in [8.44]. A P is not a column shift, so combat_tables' shift-deferral note did not
    cover it; engine._anti_armor_step now drops any (firer hex -> target hex) pair that crosses one.

None of the three moves a benchmark: the affected geometry (Tocra, Sofafi, the Qattara rim) is
nowhere near either scenario's fighting, and no unit in either ever crosses an escarpment or fires
anti-armor across one. Re-measured live after the last fix landed, twice: still abc4300eccbb /
a5da9203198d, so the ATTRIBUTION table above and the constants at the foot of this file all stand
exactly as printed.
--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-26 (SECOND MOVE THE SAME DAY) -- CAUSE: the Phase-8.1a REVIEW REPAIR. The
adversarial review of the slice below found four defects; the two that move a signature are both
fixed here, and both are corrections to the slice below, not new behaviour.

  418ee22ffb61 / 63e08df24f84  ->  b4f2e8e2c955 / 6e74c608b476

CAUSE 1 -- [8.44] SALT MARSH WAS NOT IMPLEMENTED, which INVERTED the whole point of the slice. The
chart gives Salt Marsh 2 CP motorized entry and Breakdown Value 6, against the DESERT 4 / ROUGH 4 and
BV 24 / 8 that ring the Qattara Depression -- so with the fill landed and the RULE missing, the one
terrain that historically stopped an army was the best tank road on the board: the cheapest motorized
west-east route across the map ran TWELVE CONSECUTIVE HEXES through the depression. [8.44] (scan
PDF p.15, restated by [8.37] note 2): "Vehicles, except for Light Trucks, Recce-type units, and
motorcycle infantry may enter or leave a Salt Marsh hex only on a Road or Track." Now gated on the
EDGE (both ends, enter-or-leave) in movement.step_cost, with the three named classes exempt; Camel
falls out for free (non-motorized, so it pays the chart's non-Mot 3 CP "as infantry", which is
[8.44]'s own last sentence). FLAGGED AS NAMED DEBT, not silently half-built: [8.44]'s "a prohibited
vehicle that enters a Salt Marsh hex without using the Track, WHATEVER THE REASON, is Abandoned (see
5.33)" has no engine concept of Abandonment at all, so forced relocations (engine._retreat /
_mandatory_retreat, via the new tactics.may_step_into) EXCLUDE the hex instead -- which keeps both
things the rule guarantees (a barred vehicle never gains free passage, and never ends a retreat
frozen in a marsh) and leaves 5.33 as debt rather than an invented loss.

CAUSE 2 -- 54 GRAVEL HEXES WERE RECORDED AS CLEAR (extraction defect). Gravel has no fill colour,
only a sparse ring stipple, so its class is a DENSITY measurement and the 48x48 centre patch (2,304
px, ~37% of a hex) made GLYPH_MIN a coin flip. Re-measured over the largest disc that fits INSIDE a
hex (inradius 42.6 px, 5,025 px, cannot bleed into a neighbour) the histogram is cleanly bimodal --
6,307 hexes at 0-4 px, an empty gap, then 448 at 21-72 -- and EVERY threshold from 10 to 20 returns
the same 448. Committed count was 394; the 54 missed hexes are all inside the ABC benchmark map
(A 34 / B 20), some denser than accepted ones (A1309=53, A0711=49 vs accepted A1625=39). Gravel
394 -> 448. Nothing else moved: re-running the extractor changes exactly 54 hexes, all clear->gravel,
with an identical hex set and the coastline still byte-identical at 1,750 sea.

ATTRIBUTION, MEASURED (seed 42, ScriptedPolicy(AXIS) both sides, each reproduced twice; and note the
false-neuter trap recorded under the slice below -- these patch the CALLER's binding):

    pre-repair (the slice below, as committed b389399)  -> 418ee22ffb61 / 63e08df24f84
    repair code live, gravel data reverted to 394       -> 8cf9b5288a63 / e49d052d4efb
    repair code live, gravel 448 (= SHIPPED)            -> b4f2e8e2c955 / 6e74c608b476
    SHIPPED but game.movement.salt_marsh_barred neutered-> 4b0330a6ad9d / 135661f48c6b

So both causes are real and separable: the code repair moves the hashes off the pre-repair value on
its own, the gravel correction moves them again, and neutering the [8.44] gate at the binding
movement.step_cost actually resolved moves them a third way -- i.e. [8.44] is live on both
benchmarks, NOT invisible as a first (wrongly-targeted) neuter suggested.

DELIBERATELY *NOT* FIXED -- ROSETTA (E4019), and the reasoning is worth keeping because the wrong fix
was written first and reverted. E4019 is a PORT in the book's SUMMARY OF IMPORTANT LOCATIONS and a
village water source (data/wells.json); the new fill classifies it Swamp, [8.37]'s Swamp row is "may
enter only on road or railroad", and data/roads_E.json carries 0 road and 0 track edges touching any
swamp hex -- so a book-named Port is currently unreachable by every unit in the game (it was CLEAR
and reachable before this slice). The review filed that as a defect and proposed adding E4019 to
extract_terrain.KNOWN_TERRAIN as a forced `clear`; that override was written, and then REVERTED.

WHY: the five entries already in KNOWN_TERRAIN correct a SAMPLING ARTIFACT -- a harbour's water
dominates the port hex's centre patch and it mis-samples as sea. E4019 is not that. The raster
genuinely paints it the Terrain Key's swamp, tufts and all (rendered and read by eye). Forcing it
`clear` would make the terrain data LIE ABOUT THE MAP in order to paper over a MISSING ROAD LAYER,
which is the one thing this port's rules forbid: the debt is the road trace (Phase 8.1b), and the
faithful fix is to trace the road, not to falsify the fill. tests/test_map_terrain_fills.py pins
exactly this, and says so in its own docstring ("What must NOT happen is the debt being paid by
falsifying E4019's terrain"). Swamp stays 17. WHEN 8.1b TRACES THAT ROAD, restate that test to
assert the corridor exists.

-------------------------------------------------------------------------------------------------

RE-BASELINED 2026-07-26 -- CAUSE: Phase 8.1a, the [8.37] TERRAIN FILL RECLASSIFICATION (the Qattara
Depression / El Alamein anchor, Jebel Akhdar Mountain, the Nile Delta, Rock/Gravel) + the [8.37]
note-4 / [25.12] Major-City fort roster (Benghazi + Helwan added). Full account:
scratchpad/port/terrain-key.md (the Block-A spec this slice built from).

THE BUG THIS CLOSES: the map extractor (tools/vassal/extract_terrain.py) only ever classified 4 land
fills (clear/rough/desert/vegetation) against a raster the Terrain Key (images/TEC.png, the SAME
.vmod's own [8.37] swatch card, cross-checked verbatim against PDF page 70) prints FIFTEEN for. The
Qattara Depression -- the terrain that historically STOPPED the Axis at Alamein -- was silently
COARSENED into rough/desert, so no Salt Marsh existed on this map at all; the Nile Delta read as
plain clear/rough; Jebel Akhdar carried no Mountain hex despite [24.44] naming Mountain as real board
terrain and the anti-armor chart carrying a Mountain-hex shift. A whole-raster exact-colour census
(the map is FLAT VECTOR ART -- one exact RGB per class, no texture/CV problem at all) found the true
extent: gravel 394, delta 325, salt_marsh 270, mountain 109, swamp 17 (a genuinely new terrain -- see
below), all reclassified in place of a share of the old clear/rough. This is a CORRECTION to a
coarsened map (port rule 5), not new invented geography: the coastline is BYTE-IDENTICAL (sea stays
exactly 1,750 hexes) and every one of the 21 section-seam axials that carry two labels agrees on its
class under the new classifier.

MEASURED: 1,118 land hexes reclassify (16.6% of the land map); 604 of them sit inside the ABC
benchmark map both Desert Fox scenarios load. Verified by eye against the raster (not just by count):
the Qattara Depression forms one 69-hex connected salt_marsh body (plus a 26-hex southern lobe and an
8-hex Wadi Natrun component, both labelled "The Qatara Depression"/"WADI NATRUN" on the map) exactly
where the book's own place-names put it, with the real hex-graph distance from the Mediterranean
coast to that body narrowing to 9-11 hexes right at El Alamein (E3002 = 11, Alexandria E3714 = 26) --
the historically-correct ~65km Alamein bottleneck, at this map's ~8km/hex scale. The small outlying
Mountain hexes in sections C/D/E (flagged as possible escarpment-band artifacts by the Block-A spec)
were individually eyeballed at native resolution: each is a genuine solid dark-olive-brown blob
(exact RGB match, visually and numerically distinct from the charcoal-grey escarpment band) --
isolated real hillocks (El Mesceca in section C, small knolls on the Qattara rim in section D, the
Mokattam-hills analogue near Cairo in section E), not classifier contamination.

Two engine-side additions this exposed: (1) game/cna_map.py's terrain-string lookup now RAISES on an
unrecognised class instead of silently defaulting to CLEAR -- the exact bug class this slice exists
to close. (2) Terrain.SWAMP (game/terrain.py) -- the [8.37] chart prints a Swamp row (17 Delta-lagoon
hexes, section E) that had no engine member; off-road/off-rail entry is PROHIBITED to every mobility
class (the chart note carves out no foot-unit exception) and its Breakdown Value is faithfully 0 (the
chart's blank BV cell, read the same way Track's identically-blank cell reads -- "no independent BV
of its own", not a guessed number). See game/terrain.py and data/city_forts.json for the citations.

Separately, [8.37] note 4 / [25.12] ("Alexandria and Cairo hexes are Level Three Fortifications, all
others are Level Two") -- scan-verified off PDF page 73's SUMMARY OF IMPORTANT LOCATIONS -- adds
Benghazi and Helwan to game.scenario.MAJOR_CITIES (now data/city_forts.json, 4 Level-2 cities: Tobruk,
Bardia, Benghazi, Helwan). Benghazi's fort was PREVIOUSLY WITHHELD on the theory that granting it
would hand the Axis rear an unearned [15.82] retreat-immunity; that theory does not hold -- 15.82 keys
on Terrain.MAJOR_CITY, which Benghazi already carried for its unlimited dump ceiling, not on fort
level (game/engine.py) -- so the fort was faithful debt, paid here (port rule 6: never campaign-gate
a faithful rule). Helwan (E1430) was absent from the engine entirely.

NEUTER-PROOF, both causes isolated (scratchpad/map8/neuter_proof.py, seed 42,
axis=allied=ScriptedPolicy(AXIS), each measurement reproduced twice byte-for-byte):

    both reverted (old terrain, old fort roster)     -> 453f9ad1f231 / 42eedca02ae3  (= OLD baseline)
    terrain LIVE,     fort roster reverted            -> [SEE CORRECTION BELOW -- NOT MEASURED]
    terrain reverted, fort roster LIVE                -> 453f9ad1f231 / 42eedca02ae3  (= OLD baseline)
    both live (the actual change)                     -> 418ee22ffb61 / 63e08df24f84  (= NEW baseline)

*** CORRECTION, 2026-07-26 (the adversarial review of this very slice, finding 4). THE TWO
"fort roster reverted" ROWS ABOVE WERE NEVER ACTUALLY MEASURED.*** scratchpad/map8/neuter_proof.py
called importlib.reload(scenario) INSIDE its measure(), which re-executed
MAJOR_CITIES = _load_major_cities() and silently wiped the very override the row was testing -- so
all four rows ran with the LIVE fort roster. The CONCLUSION survives (the reviewer re-isolated the
fort roster properly at runtime, without the reload, and it is genuinely neuter on both benchmarks --
Benghazi sits west of the corridor either scenario fights over), but per port rule 4 a re-baseline
may not carry a proof that was not run, so the unmeasured cells are struck rather than trusted.

THE SAME TRAP BIT THE REPAIR PASS, and is recorded here because it will bite the next person too:
game/movement.py does `from .terrain import salt_marsh_barred`, so monkeypatching
game.terrain.salt_marsh_barred does NOT reach movement.step_cost's already-bound reference. A neuter
of the terrain-module symbol reported "[8.44] is invisible to both benchmarks"; neutering the REAL
binding (game.movement.salt_marsh_barred) shows it moves both. A neuter proof must patch the symbol
the CALLER resolved, not the one the definition lives under.

So the ENTIRE signature move is the terrain reclassification. The fort-roster change, though
faithful and real, is INVISIBLE to both benchmarks: Benghazi (A4827) sits deep in the Axis rear, well
west of the whole Tobruk corridor either scenario fights over, so ScriptedPolicy vs ScriptedPolicy
never generates an event anywhere near it and its terrain/fort change never enters either log. It
still belongs in this commit (it is the same [8.37] chart, the same slice, and the campaign scenario
-- not signature-pinned -- DOES route units near Benghazi), but it is not what moved these hashes.

    rommels_arrival   453f9ad1f231 -> 418ee22ffb61
    siege_of_tobruk   42eedca02ae3 -> 63e08df24f84

Each reproduced twice, byte-for-byte.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-25 -- CAUSE: rule [6.21]/[15.88] MOVEMENT DISCIPLINE -- the scripted policies
stop voluntarily marching a unit into the guaranteed-surrender band (scratchpad/port/movement-
discipline-spec.md, itself implementing scratchpad/port/cohesion-economy-audit.md's Q3).

THE BUG: every voluntary-advance destination pick (ScriptedPolicy.movement's candidates/firing
picks, ScriptedPolicy._defender_moves' sortie pick, CampaignCommonwealthPolicy._march's
concentration pick) chose "closest to the objective, CP cost only a tiebreak" with NO cohesion
awareness anywhere in the movement path -- so a motorized unit could dash to the 8.16 2x-CPA reach
ceiling and earn ~CPA Disorganization Points (6.21) in a single UNIT_MOVED, 0 -> -25 straight
through the [15.88]/[17.24] -17 auto-surrender floor in one move. Rules-legal (6.0 lets a motorized
unit exceed its CPA "at a price") but a price no rational commander pays.

THE FIX is a POLICY change -- the rulebook and the engine are untouched, no COHESION_CHANGED
magnitude moves and apply stays pure. game/tactics.py adds husbands_cohesion, a mirror of
engine._overage_dp/_disorganize_overage kept on the policy side of the engine<->policy import
break (as effective_cpa already is): a voluntary destination is disallowed iff the unit's Cohesion
after the 6.21 overage it would newly earn reaching it falls to <=-17. ANDed into ScriptedPolicy's
candidates/firing/sortie picks (game/policy.py) and CampaignCommonwealthPolicy._march's
concentration pick (game/campaign_policy.py) -- the one shared base, so the Axis campaign inherits
it too (CampaignAxisPolicy.movement -> super().movement()), with no campaign-gate (port rule 6).
Applied per-move the allowance is exactly `cohesion + 17`, so a healthy unit still spends the
rules-legal 8.16 dash and a battered one still above the floor keeps its full <=1x-CPA move. A unit
already AT or below the floor is held out of the forward advance entirely -- it would auto-surrender
on the contact every call site steers it toward, so the discipline keeps it back to recover in place
(6.24) rather than march it into that contact; the unhusbanded 10.31 retreat path still lets it fall
back.

Both benchmarks run ScriptedPolicy(AXIS) on both sides through the exact functions edited, and
both move: at seed 42, Rommel's Arrival's open-desert dash and the siege's own perimeter jockeying
each propose at least one voluntary move whose predicted post-Cohesion would have punched through
-17, which the fix now excludes in favour of a nearer destination.

ATTRIBUTION, CHECKED: monkeypatching tactics.husbands_cohesion to an unconditional `True` (a
no-op, every other change in this slice left in place) reproduces the OLD signatures EXACTLY on
both benchmarks (851b58b89246 / f91683c03dde). So the entire move is this one predicate -- the
reach search, the CP costs, the 6.21 rate and the -17 threshold itself are all unchanged.

    rommels_arrival   851b58b89246 -> 453f9ad1f231
    siege_of_tobruk   f91683c03dde -> 42eedca02ae3

Each reproduced twice, byte-for-byte. The CAMPAIGN is not signature-pinned (see CAMPAIGN_SEED
below); its measured effect is reported in the commit that lands this baseline.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-25 -- CAUSE: rule [8.37] THE PER-TERRAIN STACKING LIMIT (replacing the
DEFAULT_HEX_LIMIT=5 placeholder) + the delta-vs-full invariant mismatch it exposed.

game/stacking.py's DEFAULT_HEX_LIMIT=5 was a flagged placeholder ("verify per-terrain vs scan") --
it matched no real chart value. The [8.37] Terrain Effects Chart's Stacking-Points column (scan-
verified PDF page 70, scratchpad/port/transcriptions/8.37-terrain-effects-chart.md) is now wired
from data/stacking_limits.json: every terrain is 6 (clear/gravel/salt_marsh/heavy_vegetation/
rough/delta/desert -- everything reachable on the map today) EXCEPT Mountain (3, not yet reachable
-- no map hex is tagged Mountain) and Major City (8). within_hex_limit no longer takes a `limit`
override; it always resolves the true per-terrain cap (stacking.hex_stack_limit).

Raising the common case 5 -> 6 legalises the 6-stacks that were repeatedly crashing campaign folds
(game.invariants._check_stack_at raising "6 > limit 5" -- seed 7 at hex (24, 83), seed 24 at hex
(30, 103), scratchpad/ammo_ab_measure.py's own flagged note). Both are now clean: seed 7 folds to
GT111/111 (262,890 events), seed 24 to GT111/111 (262,074 events), each ending on a clean
invariants.check(final) sweep.

THE SECOND FIX, found fixing the first: test_invariants_delta's equivalence test documented a real
coverage hole -- UNIT_DETACHED changes a unit's [9.21] stacking contribution (organization.size
reads Unit.attached_to) WITHOUT moving its hex, so it is not a _UNIT_MOVE_KINDS case, and
check_event never re-checked the hex the full sweep (adjudication.stacking_violations) does.
game/invariants.py now checks UNIT_ATTACHED/UNIT_DETACHED's own (unmoved) hex too (_ATTACH_KINDS),
so check_event and check() agree at every event (test_incremental_verdict_matches_full_sweep_at_
every_event, plus two new fault-injection tests that exercise check_event directly on a manually
built over-stack).

THAT FIX ALONE CRASHED LIVE CAMPAIGNS, and did, in testing: [9.12]'s HQ Stacking Point value is a
hard binary ("'0' when it has no combat units of any type attached; the printed number ... when it
represents the division or brigade as a combat unit") -- so the unit that makes a Parent Formation's
FIRST attach can jump the Parent's own contribution from 0 straight to its full printed value,
RAISING a hex's total even though [9.13]'s whole point is that organizing SHRINKS it (true in
aggregate, not necessarily on the first counter folded in). game/campaign_policy.py's
concentrate_formations already gated its OWN proposals on exactly this ("the 9.14 stacking gate",
test_concentrate_respects_the_9_14_stacking_gate, restated here -- its "3 loose + a 3-SP HQ = 6, over
the 5-limit" scenario no longer overflows the real 6-limit, so it now uses 4 loose units) -- but
engine._reorganize, the shared acceptance point every policy's attach/detach order passes through
regardless of which policy proposed it, did not, so a live campaign could still walk an over-stack
into existence and then have check_event (correctly, per the fix above) refuse to let it stand.
engine._reorganize's "attach" and "detach" branches now carry the same [8.37] guard every movement
destination already gets -- simulate the fold/unfold and reject the order (no CP charged, retryable
next Reorganization Segment) rather than cross the limit -- a second, universal layer beside the
existing policy-level gate, exactly as the engine already validates movement regardless of which
policy proposed it.

OWNER RULING CANDIDATE, surfaced by this repair, not resolved by it: [9.14] caps a hex "at the end of
any Movement Segment" and [9.31] bars a unit from "ceasing movement" over the limit -- both textually
about MOVEMENT. Reading them to also gate the Reorganization Segment's attach/detach (as this fix and
the pre-existing concentrate_formations gate both do) is the CONSERVATIVE reading, not the only
defensible one: every OpStage runs Reorganization strictly BEFORE that side's Movement Segment
(game.engine.run), so a transient organizational bump would, on every case measured here, have self-
resolved before the next STAGE_ADVANCED boundary sweep even with no gate at all. This port took the
conservative reading -- never let the board go over-limit, by any path -- because the alternative risks
a live-engine crash on a rules-grey-area state, and the cost is small (an occasionally-deferred
consolidation, not a lost unit). One path is NOT covered: engine._maybe_disband_battle_group's FORCED
cascade of Italian detaches when a Kampfgruppe's last German leaves (Kampfgruppen HQ's sheet note 2,
a mandatory unwind with no sensible "reject") emits UNIT_DETACHED directly and bypasses the new gate.
Flagged as a residual risk, but currently STRUCTURALLY UNREACHABLE, not merely unobserved: no policy
in the codebase (CampaignAxisPolicy, CampaignCommonwealthPolicy, StaffPolicy, the LLM policy) issues a
"form_kg" order (grep-confirmed), so BATTLE_GROUP_FORMED never fires, no ge_battle_group HQ ever exists
on the board, and _maybe_disband_battle_group's own guard (hq.org_type != "ge_battle_group") can never
match -- matching test_organization_campaign.py's own note that the dynamic 19.71 Battle Group is
"flagged and deferred as speculative AI". Revisit this gate the day a policy forms one.

ATTRIBUTION, CHECKED: neither game/invariants.py's _ATTACH_KINDS fix nor engine.py's new attach/
detach guard reaches either Desert Fox benchmark -- both run ScriptedPolicy, whose .organization()
returns [] unconditionally (game/policy.py), so _reorganize is never even called and no UNIT_ATTACHED
/UNIT_DETACHED is ever emitted on either log. Neutering ONLY the terrain-limit change (monkeypatching
stacking.hex_stack_limit to return the old flat 5 unconditionally, leaving the data file, the [8.37]
lookup machinery, and both the invariants.py/engine.py fixes in place) reproduces the OLD signatures
EXACTLY (b03f538ccb8a / fb0b8678dc74). So the entire move is the terrain-limit number, 5 -> 6, and
nothing else in this slice touches either benchmark.

    rommels_arrival   b03f538ccb8a -> 851b58b89246
    siege_of_tobruk   fb0b8678dc74 -> f91683c03dde

Each reproduced twice, byte-for-byte.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-25 -- CAUSE: rule [50.17]/[53.11]/[54.2] THE CLOSE-ASSAULT-AMMO LAST MILE
(armour-elimination diagnosis, scratchpad/port/armour-elimination-diagnosis.md +
scratchpad/port/ammo-last-mile-spec.md). Part 1 of a two-part supply fix moves these logs; Part 2
does not, and that is CHECKED below rather than assumed.

  PART 1 (engine._fl_ammo_capacity, engine._supply_distribution's `caps` tuple). Rule 50.0 gives
  every combat unit an intrinsic 'fire once' basic ammo load, and 50.17/53.11 separately lets a
  unit's OWN first-line trucks carry MORE ammo on top of that ("available for use when in first
  line trucks"; 54.2's Light 2 / Medium 4 / Heavy 8 Ammo Points per Truck Point) -- a buffer this
  port had built (S0/S2, tests/test_first_line.py) but never wired into the 48 V.C.6 Supply
  Distribution refill, which topped AMMO to the bare intrinsic capacity only (mirroring FUEL, which
  correctly has no such buffer -- 49.14's tank IS the whole of a vehicle's organic fuel carry). A
  str-8 tank's intrinsic load affords exactly one close assault (50.14: rate 2 x strength, cost 16,
  against a 24-point load) and is then dry -- so on the SECOND assault [15.15]/[15.88] auto-
  surrenders the whole unit even at full strength and healthy cohesion, which the diagnosis measured
  as ~53% of every tank surrender in the campaign. The fix un-defers the buffer: AMMO now refills to
  `ammo_capacity(u) + first_line_capacity(u, AMMO)`, exactly mirroring how STORES already refills to
  its (organic-pool-less) first-line ceiling. Both Desert Fox benchmarks seed GT1 first-line trucks
  onto their Italian/Commonwealth units ([61.43]/[61.31], test_benchmark_first_line_totals_match_
  61_43_61_31 -- 315 + 133 = 448 Truck Points), so raising the AMMO refill ceiling changes what a
  unit standing on a dump draws the moment its intrinsic pool is not already full, and both logs
  move. This is the sanctioned "faithful close-assault-ammo change" category, not a leak.

  PART 2 (game.oob._seed_reinforcement_first_line, data/reinforcement_first_line.json) attaches
  first-line trucks to REINFORCEMENTS as they arrive, transcribed from the [4.43a]/[4.43b] "Attached
  Trucks" schedule column -- necessary because every one of the 39 Commonwealth armour counters in
  the full CAMPAIGN is a rule-20 reinforcement and so, before Part 2, carried a truck buffer of
  exactly zero regardless of Part 1's wire. It is wired ONLY into game.scenario.campaign
  (`reinforcement_first_line_file="reinforcement_first_line.json"`); oob.build's new parameter
  defaults to None and neither rommels_arrival nor siege_of_tobruk passes it -- Desert Fox's own
  rule-61 reinforcement schedule is a separate, untranscribed chart, and reusing the campaign's
  [4.43a]/[4.43b] data for it would be an invented cross-scenario leak, not a faithful reuse.

ATTRIBUTION, CHECKED: neutering Part 1 alone (patching engine._fl_ammo_capacity back to plain
supply.ammo_capacity, the pre-fix intrinsic-only ceiling) reproduces the PRE-fix signatures EXACTLY
(dda6faa445b4 / 5f02a0c4fb9e) on both benchmarks. Separately, neutering Part 2 alone (patching
oob._seed_reinforcement_first_line to the identity passthrough, Part 1 left active) reproduces the
POST-fix signatures EXACTLY (b03f538ccb8a / fb0b8678dc74) -- proving Part 2 is not merely small on
these two scenarios but STRUCTURALLY INERT on them, exactly as its own spec predicted ("siege/rommel
are short -- likely not").

    rommels_arrival   dda6faa445b4 -> b03f538ccb8a
    siege_of_tobruk   5f02a0c4fb9e -> fb0b8678dc74

Each reproduced twice, byte-for-byte. The CAMPAIGN is not signature-pinned (see CAMPAIGN_SEED below);
its measured effect is reported in the commit that lands this baseline.

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED BY RULE [20.62]/[20.64] THE AXIS CONVOY COUPLING (Block B of Gate 7A), 2026-07-25,
AND THAT WAS CHECKED RATHER THAN ASSUMED -- both signatures recomputed on the tree and are UNCHANGED
(the two test_rommel_and_siege_stay_byte_identical guards pass unmodified).

The block builds the mechanism that makes the Axis faucet PAY for its army's healing: every Axis
Infantry Replacement Point is now charged 30 Shipping Tons (the errata) against the [56.5] convoy
allowance, at PRIORITY over fuel/ammunition/stores (20.64), before the 56.22 supply split -- where
the Commonwealth's Replacement Points still simply arrive (20.75). The charge lives in
engine._axis_replacement_bring_in, called from engine._convoy_planning; its vehicle is a minimal
faithful INFANTRY flow-in (the [20.66] German 400 + Italian 1,200 pool), crediting the [20.43]
Training ledger with the [20.63] two-Game-Turn lead, from which Block A's spend heals the army.

It moves NEITHER benchmark log, and the reason is the same structure that gated 7.2a/7.2b:

  * THE COUPLING IS GATED behind GameState.replacement_production, which ONLY game.scenario.campaign
    sets. engine._axis_replacement_bring_in returns c.tons unchanged at its first guard for the two
    Desert Fox benchmarks, so the convoy split sees the identical allowance it always did and no
    REPLACEMENTS_PRODUCED is emitted on their logs.
  * THE ELECTION DRAWS NO DIE. The bring-in is need-driven point arithmetic (the infantry deficit,
    minus the pipeline, bounded by the [20.67] per-Game-Turn ceiling and the allowance) -- no RNG
    subsystem is touched, so nothing a benchmark draws can move even if the gate opened.
  * THE apply EDIT IS NIL. The Axis flow-in reuses REPLACEMENTS_PRODUCED, whose apply already credits
    the Training ledger; no new EventKind and no new fold. The extra tons_charged/convoy_id payload
    keys are recorded facts the fold ignores.

The CAMPAIGN log DOES move -- that is the whole point of the block -- and the campaign is not
signature-pinned (see CAMPAIGN_SEED below). Neutering the charge (return c.tons) restores the
pre-block campaign supply exactly, which is how the squeeze was measured (reported in the commit).

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED BY RULE 20 THE SPEND + THE COMMONWEALTH WITHDRAWALS (Block 7.2b), 2026-07-24, AND
THAT WAS CHECKED RATHER THAN ASSUMED -- both signatures recomputed on the tree and are UNCHANGED
(dda6faa445b4 / 5f02a0c4fb9e), each reproduced twice.

Block 7.2b closes the loop 7.2a opened. 7.2a filled GameState.replacement_pool and NOTHING consumed
it; this builds THE SPEND -- a depleted unit drawing Replacement Points from the pool to restore TOE
Strength Points, the FIRST additive write to Unit.steps -- through the 19.61/19.68 rebuild path now
gated on the [20.3] Replacement Point Conversion Chart (data/replacements.json, scan-verified PDF p.102,
where the docs/rules OCR had the Armored-Car/Tank rows scrambled). It also lands the 20.8/[4.43a]
Commonwealth mandatory withdrawals (data/withdrawals_campaign.json), 20.82/20.83 (the '(20.75)' ->
(20.82) cross-reference typo, under a named errata key, owner ruling 3), and the 20.9 voluntary hook
Block 7.3 scores under 64.75.

It moves NEITHER benchmark log, and the reason is STRUCTURAL and threefold:

  * BOTH new beats are GATED behind campaign-only flags. engine._replacement_spend returns at its
    replacement_production guard and engine._commonwealth_withdrawals at the new commonwealth_withdrawals
    guard -- and ONLY game.scenario.campaign sets either, exactly as the 7.2a flow-in was gated. The two
    Desert Fox benchmarks set neither, so both beats return before emitting.
  * THE ORDER PATHS EMIT NOTHING THERE. The now-pool-gated 'rebuild' and the new 'withdraw' organization
    orders are issued by no benchmark policy (ScriptedPolicy.organization returns []), so neither
    UNIT_REBUILT nor UNIT_WITHDRAWN is generated.
  * AND THE APPLY EDITS ONLY TOUCH THOSE TWO EVENTS. apply(UNIT_REBUILT) now also debits the pool, and
    apply(UNIT_WITHDRAWN) empties a counter (broken_down zeroed) -- events neither benchmark emits.

The CAMPAIGN log DOES move, and the campaign is not signature-pinned (see CAMPAIGN_SEED below). This is
the block whose whole point is a number that was structurally ZERO before it.

MEASURED, full campaign at CAMPAIGN_SEED=4 (CampaignAxis vs CampaignCommonwealth), the TOE Strength
Points a real campaign now RESTORES: 1,669 (716 UNIT_REBUILT events) -- the entire [20.78B] production
that seed (1,669 Infantry Points produced, pool ends at 0), because the crushed Eighth Army's infantry
losses exceed its replacement flood and absorb all of it. And the mandatory withdrawals that now
SUBTRACT the formations History sent to Greece/Crete/Syria: 76 UNIT_WITHDRAWN, 74 of them ELIMINATED
by 20.83 (the CW fights at the front, not in Cairo/Alexandria, so the anti-procrastination clause bites
-- the counter leaves either way). 23 of the 33 [4.43a] rows resolve against the current, still-
incomplete CW OOB; the other 10 are transcribed with an empty match and fire as the OOB completes.

The winner and 64.76 grade are UNCHANGED -- Axis Smashing Victory, and the Commonwealth's own Victory
Points hold at 20 (the Axis total eases 415 -> 390: the rebuilt Eighth Army is a touch harder to evict,
even as the withdrawals strip it). Determinism binds by construction: both beats are pure point-
arithmetic with NO die, so a die drawn elsewhere cannot move and the same seed replays byte-identically
(verified: campaign(4) folded twice is identical). The channel IS exercised by
tests/test_replacement_spend.py (20 tests) and tests/test_replacements.py's restated campaign-loop guard.

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED BY RULE [20.7]/[20.78B] THE REPLACEMENT ECONOMY'S FLOW IN (Block 7.2a), 2026-07-24,
AND THAT WAS CHECKED RATHER THAN ASSUMED -- both signatures recomputed on the tree and are UNCHANGED
(dda6faa445b4 / 5f02a0c4fb9e).

The block builds the PRODUCTION half of rule 20 -- the thing nothing in this engine had ever done, put
a Replacement Point into a pool from which a depleted unit can be rebuilt (the SPEND is Block 7.2b).
Its one live producer is the [20.78B] Commonwealth Infantry Production stream: ONE 2d6 roll per
Game-Turn (GT3-107, off the new `cw_production` dice subsystem), FREE (20.75), crediting
GameState.replacement_pool on the arrival turn (plan + the owner-ruled 4-Game-Turn lead). The Axis Pool
and the [20.78C] equipment chart are transcribed as draw-at-will DATA (data/replacements.json,
game.replacements), inert until 7.2b draws them.

It moves NEITHER benchmark log, and the reason is STRUCTURAL and doubly so:

  * PRODUCTION IS GATED behind GameState.replacement_production, which ONLY game.scenario.campaign
    sets -- the CW Production system is a 111-turn campaign subsystem (Cairo/Alexandria arrival,
    20.76), not a rule the tactical Desert Fox benchmarks model, exactly as motorized_supply /
    dump_capture / initiative_chart gate their own campaign-scale subsystems. Measured: rommels_arrival
    and siege_of_tobruk each emit ZERO REPLACEMENTS_PRODUCED events, so engine._replacement_production
    returns at its first guard and neither log gains a byte.
  * AND THE DIE COULD NOT REACH THEM IF IT FIRED. `cw_production` is its own game.dice subsystem,
    seeded independently of every other -- so a roll drawn there advances no weather, combat or
    breakdown stream. This is the whole point of game.dice: adding an 18th subsystem cannot re-index
    the other 17.

The CAMPAIGN log DOES move -- it gains 105 REPLACEMENTS_PRODUCED events (and their Phase.LOGISTICS
markers) -- and the campaign is not signature-pinned (see CAMPAIGN_SEED below). But its BOARD
trajectory is byte-identical: because `cw_production` perturbs no other stream and the pool is inert
(nothing spends it yet), every unit/supply/victory outcome is exactly what it was. Measured, full
campaign seed 4: winner unchanged (Axis Smashing Victory, 415-20 VP, 64.76), reached GT111, and the
stream produced 1,669 Infantry Replacement Points into the pool -- a single-seed sample of the
[20.78B] expected yield 1,615.9 (game.replacements.cw_infantry_expected_yield; empirical mean 1,617.1
over 1,000 seeds, matching the port plan's ~1,617). The channel IS exercised by tests/test_replacements.py.

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED BY RULE [19.0] ORGANIZATION AND KAMPFGRUPPEN (Block 7.1), 2026-07-24, AND THAT WAS
CHECKED RATHER THAN ASSUMED -- both signatures recomputed TWICE on the tree and are UNCHANGED
(dda6faa445b4 / 5f02a0c4fb9e).

Rule 19 -- the entire assign/attach/detach/Kampfgruppe hierarchy -- was MISSING: Unit had no
parent/assigned/attached field, so no division and no Battle Group could ever form, and the
[15.53] Organization Size Close Assault chart (transcribed exactly, verified against the scan)
could never reach its Brigade / Super-Brigade / Division rows -- no counter carries more than one
Stacking Point (the ten HQ / gun roles are SP 0, everything else SP 1), so the chart could fire
only on its lowest (1,0) 'battalion vs. a lone gun or company' edge and never on the 2 / 3 / 5 SP
tiers. The block adds the tree (game.state.Unit.assigned_to/attached_to/org_type), the [19.3]/[19.5] charts as
data (data/formation_organization.json, data/maximum_attachment.json), the [6.3] organization CP
rows, the [9.2] unit-equivalent + [9.26] shell arithmetic and the [19.6]/[19.8]/[19.9] rebuild and
ad-hoc-AT paths (game.organization), and rewires close assault to read a formation's size up its
attachment chain with 9.28's shell step-down (engine._parents_of + organization.combat_size).

It moves NEITHER benchmark log, and the reason is STRUCTURAL, not luck. Two independent facts:

  * NOTHING IS ATTACHED in either scenario. The historical starting tree lives on the [4.44]/[4.45]
    Organization at Arrival Charts, which are not transcribed (port plan T1-2), so game.oob seeds
    no org_type and no attachment; and ScriptedPolicy issues no organization order, so no division
    or Kampfgruppe forms. Every counter stays independent at SP 1 -- exactly what it was.
  * THE ONE LIVE CHANGE TO EXISTING COMBAT -- close assault now reads size_equivalent (9.28 shell
    step-down) instead of raw stacking_points, off the max_toe game.oob now seeds -- is never
    EXERCISED here. Instrumented over both full benchmark runs: organization.combat_size diverges
    from the old max(stacking_points) ZERO times. These two scripted scenarios resolve almost no
    close assault (their combat is Barrage / Anti-Armor / auto-Surrender, as the 15.84 note above
    records), and in none of it is a participant a shell. So the new path is handed only
    full-strength SP-1 battalions and returns 1, byte-for-byte as before.

The machinery IS proven to fire -- by tests/test_organization.py, whose headline
test_org_size_shift_fires_for_the_first_time_when_a_kampfgruppe_forms builds a four-battalion German
Battle Group and shows the [15.53] chart shift TWO columns off its brigade tier (2 SP vs 1 SP) --
the first time the chart reaches that tier, which no counter could do before rule 19 -- and
test_a_division_against_a_company_is_the_chart_s_eight_column_shift the 5-vs-0 eight-column case. It
will move the CAMPAIGN log (not signature-pinned) the moment either the T1-2 parent tree lands or a
policy forms a Kampfgruppe.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-24 -- CAUSE: rule [10.31-10.36] MANDATORY ATTACK (Phase 6.3, "make contact cost
something"). ONE rule moves these logs. (This supersedes the FIRST cut of Phase 6.3 earlier the same
day, which paired the sweep with a break-off change that a repair pass has since reverted -- see the
REPAIR note directly below; the pre-6.3 hashes df632af423c0 / b4c62a774318 are the anchor.)

  [10.31-10.36] the ZOC combat requirement. An Enemy hex whose ZOC touches the Phasing side's
  combat units must be answered each Combat Segment -- Close Assaulted, or Held Off by a Barrage of
  at least 10.34's Actual-Barrage-Point threshold. A stack that leaves one unanswered and is not
  10.32-exempt (solely Guns / Pinned / immobile) is force-retreated to a hex three hexes distant for
  all its remaining CP and three DP (10.36), or Surrenders if no ZOC-free destination three hexes
  distant exists (10.36e). Before this an army drifted up to the enemy, declined battle, and drifted
  on for free. engine._mandatory_attack, swept at the end of _combat off the POST-combat board.

REPAIR PASS, 2026-07-24 (three adversarial verifiers). The first cut of Phase 6.3 shipped two defects
that this re-baseline embodies the fix for:

  * [8.64-8.67] break-off was changed to charge the 2/4-CP toll on RAW enemy ZOC at the start hex,
    even when a Friendly combat unit shares the hex and negates that ZOC. That REVERSED the pre-6.3
    behaviour the transcription called "already faithfully wired" and cut against 10.26's plain text
    ("the presence of a Friendly combat unit ... negates the effect of an Enemy ZOC for ALL MOVEMENT
    PURPOSES") chained through 8.61 ("Breaking Off is a function of Movement") -> 8.62 (Contact is
    being in an Enemy ZOC) -> 8.64 (toll on a unit in Contact): a unit stacked with a negator is not
    in un-negated Contact and owes no toll. The sole cited support (8.67) is neutral -- it is equally
    satisfied by units each alone in the ZOC in DIFFERENT hexes. REVERTED to the 10.26-negated
    `controlled(start)` (zoc._zoc_search start_cost); it is no longer a signature mover.
  * [10.36] the forced retreat took THREE strictly-outward steps, so from an adjacent (distance-1)
    start it ended at distance 4, not the "three hexes distant" the rule specifies; and its strict
    "each step farther" test surrendered units that could reach distance 3 only via a legal sideways
    (equal-distance) step, though 10.36 bars only doubling back and Enemy-ZOC hexes. CORRECTED
    (engine._mandatory_retreat): a BFS to a stacking-legal hex EXACTLY three hexes from the anchor,
    steps non-decreasing in distance (sidesteps legal, backtracking barred), Surrender only when no
    such destination exists.

ATTRIBUTION, CHECKED: on the repaired tree (break-off start_cost already reverted to the 10.26-negated
form), re-running both benchmarks with engine._mandatory_attack neutered to a no-op reproduces the
pre-6.3 signatures EXACTLY (df632af423c0 / b4c62a774318). So the entire move is [10.31-10.36], and the
break-off revert is a clean return to pre-6.3 (it moves nothing on its own). The slice's other rules
are STRUCTURALLY INERT on these two scenarios: the 6.26 "may-not-DEFEND" gate (engine._resolve_combat
armed_def) never bites because no defender is assaulted at Cohesion -26 (a stack that far gone
auto-Surrenders at the 15.88 -17 floor first), and the 6.26 react gate never bites because neither
ScriptedPolicy benchmark issues a Reaction (0 REACTION_MOVED). Both are exercised by
tests/test_mandatory_attack.py instead.

    rommels_arrival   df632af423c0 -> dda6faa445b4
    siege_of_tobruk   b4c62a774318 -> 5f02a0c4fb9e

Each reproduced twice, byte-for-byte.

--------------------------------------------------------------------------------------------------
NOT RE-BASELINED BY RULE [15.84] GUN VULNERABILITY (Phase 6.2), 2026-07-24, AND THAT WAS CHECKED
RATHER THAN ASSUMED -- both signatures recomputed TWICE on the tree and are UNCHANGED
(df632af423c0 / b4c62a774318).

[15.84b/c] is the largest missing land-combat loss channel: a Forward GUN caught in a Close Assault
now sheds TOE on its VULNERABILITY Rating. That Rating was populated on every counter (game.oob, off
the [4.47]/[4.48]/[4.49] Characteristics Charts) and read by NO code, so artillery was IMMORTAL in
Close Assault -- it bled only to the 15.83 percentage pool. The channel fires in
engine._forward_gun_vuln_losses, AFTER the percentage losses (15.84c), sized off combat.resolve's
`column` (Overrun, 15.77) and `*_points_lost`; 12.18 halves an attacking Gun's Rating and AA/Flak
are exempt (15.84b).

It moves NEITHER benchmark log, and the reason is STRUCTURAL, not luck. The channel fires only when a
GUN is one of the units taking Close-Assault Raw-Point losses in a combat that reaches the 15.79 CRT.
Measured on both benchmark logs (ScriptedPolicy, seed 42): the WHOLE rommels_arrival run records ONE
close-assault attacker step-loss and ZERO defender step-losses, and siege_of_tobruk the same -- their
combat is overwhelmingly Barrage / Anti-Armor / auto-Surrender (15.88), and in neither is a Gun ever
the unit bleeding Close-Assault Raw Points. So _forward_gun_vuln_losses is handed a loss with no
Forward Gun to remove, emits nothing, and both logs stay byte-identical. (The channel IS exercised --
by tests/test_vulnerability.py, and by the campaign, which is not signature-pinned.)

MEASURED, full campaign (CampaignAxis vs CampaignCommonwealth) -- gun VULNERABILITY step-losses over
the whole 111-turn war, a channel that was structurally ZERO before this rule:

    seed 1941   2 events /  2 gun Points   (of def=12 atk=27 close-assault step-losses that war)
    seed    7   1 event  /  1 gun Point    (of def=4  atk=13)
    seed   99   1 event  /  1 gun Point    (of def=3  atk=7)
    seed 2026   2 events /  3 gun Points   (of def=15 atk=18)

The channel is LOW-FREQUENCY -- a Gun dies in Close Assault only when the enemy actually closes on it,
rare in these logistics-dominated campaigns where supply attrition and Surrender do the killing -- and
it does not flip the campaign winner. That is the faithful picture: artillery is no longer immortal,
but the desert's killers are still thirst and encirclement, not the bayonet.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-24 -- CAUSE: rule [21.11] THE MORTAL LORRY (Phase 6.1). Truck Points are named
FIRST among the vehicles subject to Breakdown, and for two years not one had ever been lost. Now a
2nd/3rd-line convoy accrues Breakdown Points as it relocates (21.21, the TRUCK_MOVED faucet), and
having ceased moving with more than three (21.27) rolls on the 21.38 table at BAR 2 Left (21.14); the
percentage breaks down into TruckFormation.broken_down (immobile, 21.44) and is field-repaired the
next Repair Phase on the 22.8 truck column (22.23, FREE). Both benchmarks field the [61.43] Axis
motor-transport pool and the relay cycles it across the desert, so both logs move.

ATTRIBUTION, CHECKED: re-running both benchmarks with engine._truck_breakdown neutered to a no-op AND
supply.truck_bp_for_move forced to 0 -- every other change in this slice left in place -- reproduces
the OLD signatures EXACTLY (dd7bf1df9cec / 0e2bc47ef7f4). So the move is entirely the 21.11 breakdown
check plus its 21.21 accrual and the 22.23 repair that answers it. The slice's other new dice source,
the 12.46 secondary BARRAGE-against-Trucks roll, is DORMANT in these two scenarios: their convoys sit
in the rear and are never in a barraged hex, so no second die is ever drawn for them here (it is
exercised by tests/test_lorry_mortal.py instead). The 29.34 truck-cargo evaporation and 49.3 CW rate
were already live (they moved the 07-23 / 07-22 baselines).

    rommels_arrival   dd7bf1df9cec -> df632af423c0
    siege_of_tobruk   0e2bc47ef7f4 -> b4c62a774318

Each reproduced twice, byte-for-byte.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-23 -- CAUSE: rule [53.11] FIRST-LINE TRUCKS, THE LAST MILE from the dump to the
man. Exactly one rule moves these two logs.

Until this slice the [60.31]/[61.43] first-line-truck allotment was SEEDED onto units (the
fl_light/fl_medium/fl_heavy carrying-ceiling fields) but DORMANT: the 48 V.C.6 Supply Distribution
top-up (engine._supply_distribution) refilled a unit's FUEL/AMMO intrinsic pools from a co-located
dump, and STORES -- which has no intrinsic 51.0 reservoir -- had no unit pool at all, so a unit had
to stand ON a dump every Stores Expenditure or go short (the binding constraint the faucet audit
measured: delivered Stores exceed eaten Stores threefold, yet ~53% of Axis unit-Game-Turns take a
stores shortfall).

This slice activates the tier the FAITHFUL way, and the draw stays STRICTLY IN-HEX (48 V.C.6
"supplies in the same hex"; 49.15; 53.24 loads first-line trucks IN PLACE during the segment -- they
do not drive a solo run, which is the 2nd/3rd-line convoy's job, already modelled by _truck_convoys).
STORES now BUFFERS onto a unit's own first-line trucks up to the 54.2 stores ceiling
(supply.first_line_capacity) from a CO-LOCATED dump, and RIDES FORWARD with the unit as it advances
(53.22: first-line trucks move with the parent) -- so the last mile is CARRIED, not reached: a unit
that topped up on a forward dump still eats next Game-Turn from its lorry-borne stores though it has
moved off. FUEL/AMMO refill their intrinsic 49.14/50.0 pools from the co-located dump as before.
WATER stays on the abstract half-CPA trace (the S8 proxy for the unbuilt 52.45 water trucks). German
combat units, reinforcements and static garrisons own no first-line trucks ([4.43b] Reinforcement-
Schedule attachment DEFERRED), so they stay strictly in-hex and still culminate.

REPAIR NOTE: the first cut of this slice gave first-line trucks a solo CPA/2 round-trip REACH to a
nearby dump during Supply Distribution -- that was rule 32.16, the ABSTRACT game's supply range
(Section 32, which rule 3 of this port says DOES NOT APPLY), re-imported under a first-line label. It
also broke the suite (a greedy cross-hex refill drained the Commonwealth's own railhead and rerouted
its trucks). The reach is REMOVED; the co-located stores buffer above is what survives, and it is the
half the verifiers found faithful. NO chart magnitude was bent: the 54.2 truck capacities, the
[60.31]/[60.41]/[61.43]/[61.31] allotments and the 53.11/53.22 mechanism ARE the book's. Determinism
holds -- each new hash reproduced byte-for-byte across two runs.

    rommels_arrival   c7853d6ae610 -> dd7bf1df9cec
    siege_of_tobruk   812528e2b95b -> 0e2bc47ef7f4

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-22 -- CAUSE: rule [49.3], the COMMONWEALTH'S OWN EVAPORATION RATE. Exactly one
rule moves these two logs, and it was checked rather than assumed (see below).

[49.3]: "...from Sept., 1940 until the last Game-Turn (inclusive) in August, 1941, the Commonwealth
spillage and evaporation rate is NINE PERCENT (9%) per Game-turn" -- the four-gallon petrol tin the
Eighth Army fought its first year on, before it copied the Afrikakorps' jerrican. The number was
transcribed into data/logistics_rates.json when chapter 49 was ported
(`commonwealth_penalty_percent_sept1940_to_aug1941: 9`) and NOTHING EVER READ IT; engine._evaporate
even carried a comment saying so ("the 9% Sep40-Aug41 Commonwealth container rate is deferred").
The faucet audit (scratchpad/port/faucet-audit.md, culprit 6) found it. It is a printed number, so
it is charged: the rate is now per SIDE (engine._base_evaporation), 9% for the Commonwealth inside
the window and 6% for everybody otherwise. The 29.34 hot +5% slice is NOT side-conditioned -- 49.3
gives the Commonwealth its own reading of the per-GAME-TURN rate, and the hot slice is a separate
charge on a separate clock.

Both benchmarks open inside the window (the engine's calendar anchors every scenario's Game-Turn 1
at September 1940, and both benchmarks are historically inside Sept 1940 - Aug 1941 anyway), and
both field Commonwealth dumps holding fuel and water, so both move.

ATTRIBUTION, CHECKED: re-running both benchmarks with `engine._EVAP["commonwealth_1940_41"]` set
back to the 6% base -- and every other change in the block left in place -- reproduces the OLD
signatures exactly (afe73c4ba92a / 2f2133eb37fd). The block's other two rules cannot reach these
logs and the reasons are structural: the [56.22] convoy doctrine's oasis fix is in
campaign_policy.convoy_plan_doctrine, and the benchmarks plan their sailings through the BASE
Policy.convoy_plan (they never call the campaign doctrine); the [56.21] per-Game-Turn shipping fix
is in scenario._campaign_convoys, which only campaign() calls (rommels_arrival sails on
_axis_convoy_tonnage, untouched).

    rommels_arrival   afe73c4ba92a -> c7853d6ae610
    siege_of_tobruk   2f2133eb37fd -> 812528e2b95b

Each reproduced twice, byte-for-byte.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-21 -- CAUSE: rule 56.21/56.22, the Axis Convoy Planning Phase (Phase 5.5).

ONE rule moved these logs, and it is the deletion of invention I11. `scenario._CONVOY_SPLIT_56_22 =
{FUEL 0.60, AMMO 0.25, STORES 0.15}` was a constant applied at scenario construction to every Axis
convoy in the game. 56.22 makes it the Axis Player's decision -- "having determined the allowable
tonnage for a given Game-Turn, the Axis Player MAY NOW PLAN TO SHIP ANY AMOUNTS (within the limits
of allowable tonnage) OF FUEL, AMMUNITION, AND STORES THAT HE WISHES" -- and 56.0 makes him take it
ONE GAME-TURN IN ADVANCE. So the scenario now schedules only the [56.4]x[56.5] TONNAGE, and the new
Convoy Planning Phase (engine._convoy_planning, at the top of each Game-Turn) asks Policy.convoy_plan
what to load.

BOTH benchmarks sail the Axis lane "1" on that tonnage -- they always did; the constant merely split
it at construction -- so both move, and they move for two compounding reasons: the split is now the
base Policy's (still 60/25/15, so the ARITHMETIC is unchanged) but it is applied to each sailing's own
allowance rather than folded in at build time, and the CONVOY_PLANNED events themselves are new
entries in the log the signature hashes. Nothing about the tonnage, the lanes, the ports or the dice
changed: `_axis_convoy_tonnage` draws the same 56.5 die off the same seeded `random.Random(seed)` in
the same order it always did.

The other four rules in Phase 5.5 do NOT move these two logs and it is worth saying why, because each
is genuinely inert here rather than accidentally so: 41.32/41.35 add two AIR MISSION KINDS no scenario
schedules; 39.19's ledger is written only by an Axis Malta raid, and neither benchmark seeds Malta;
and rule 43 speaks only about a BOMBER FORCE, which neither benchmark fields -- both run air=() by
default (scenario.rommels_arrival has no air at all; siege_of_tobruk takes its wings only under
port_bomb/raf), so there is no squadron for the Mediterranean basing to take a share of.

    rommels_arrival   b805053d4d26 -> afe73c4ba92a
    siege_of_tobruk   5c02a1f22398 -> 2f2133eb37fd

Each reproduced twice, byte-for-byte.

NOT RE-BASELINED BY [34.86] MALTA REINFORCEMENT + THE AIR-LARDER FAUCET (2026-07-22) OR BY ITS
REPAIR PASS THE SAME DAY, AND THAT WAS CHECKED RATHER THAN ASSUMED -- BOTH SIGNATURES RECOMPUTED ON
THE TREE, UNCHANGED.

This one is worth spelling out, because unlike the three air blocks before it, it DID touch the
byte-locked base relay and the campaign map: ScriptedPolicy.truck_orders now returns
campaign_truck_orders + relay.air_supply_orders (game/policy.py), and the campaign's [60.43]
Commonwealth air-facility lorry park moved from D3714 to D3516 (game/scenario.py). Neither reaches
these two logs, and the reasons are structural rather than lucky:

  * air_supply_orders returns [] on its first two lines unless the scenario seeds BOTH an air-dump
    larder and a faucet to reload at. Neither benchmark seeds an air dump at all, so the shuttle
    never gets as far as looking at a lorry, and truck_orders' other half is unchanged.
  * the [60.43] park hex is built by scenario._campaign_cw_trucks, which only the campaign calls.
  * the repair pass's unload ledger (relay.air_supply_orders._short) lives inside that same
    early-returning function; its Malta half needs facilities neither benchmark seeds; and its
    game.calendar correction -- 64.2's two-Game-Turn September, which moved the campaign's month map
    two turns and CAMPAIGN_SEASON_OFFSET 24 -> 26 -- is read by nothing outside a campaign scenario
    (the two benchmarks stamp no season_offset and run on the local weather clock).

The CAMPAIGN log moves under all of it, and the campaign is not signature-pinned (see CAMPAIGN_SEED
below, which pins a SEED and a set of narrative assertions, not a hash).

NOT RE-BASELINED BY THE [60.32] TRANSFER REPAIR PASS (2026-07-22, later the same day), AND THAT WAS
CHECKED RATHER THAN ASSUMED -- both signatures recomputed on the repaired tree.

Three adversarial reviews of the transfer block found real rule errors and they are fixed: 36.3/36.4
now refuse a landplane bomber the Derna flying-boat ALIGHTING AREA as a departure (it was offered,
and roster.deployment refused the same facility for placement in the same commit); [37.24] now caps
what may fly from one field at its Capacity Level in aeroplanes, so a redeployment spreads across
the fields he holds instead of flying 116 machines off a 72-plane airfield; the flight home is
tested against the same [37.4] chart and the same ceiling and names the field it lands at, and its
free fuel is cited to [36.5](a) rather than to 43.21, whose printed subject is GERMAN bombers;
and 39.19's second sentence now binds on the Mediterranean contingent, so the bombers that raid
Malta in the Strategic Phase may not fly home in an Operations Stage of that Game-Turn. NONE of it
reaches these two logs, for the reason the block itself did not: neither benchmark fields an
AirWing, so engine._air_transfer returns at its first guard and _malta_raid never runs.

NOT RE-BASELINED BY [60.32]'s MUSTER, THE [42.1] TRANSFER MISSION OR THE NINTH ITALIAN ROW
(2026-07-22), AND THAT WAS CHECKED RATHER THAN ASSUMED -- both signatures recomputed on the tree.

That block did three things a signature could plausibly notice, and none of them reaches these two
logs. (a) It added a new per-Operations-Stage beat, engine._air_transfer, which asks
Policy.air_transfer -- the base answers 0, ScriptedPolicy does not override it, and a zero emits no
event at all, so both benchmark logs gain nothing. (b) It seeded [60.32]'s ninth row, the Cant
Z. 501 Gabbiano ruled 2026-07-22, which moves the AXIS RECON establishment from 66 aeroplanes to 75
and so moves every roster ratio taken over it -- but NEITHER BENCHMARK FIELDS A RECON WING (both run
air=() by default; siege_of_tobruk's optional wings are fighters and strike), and the Gabbiano's
charted Fuel of 2 is the same as the two types it joins, so even the averaged 34.17 rate is
unchanged. (c) It replaced basing.discretionary_pct with the GameState.air_mediterranean ledger,
which is rule 43's business and rule 43 has no squadron to bite on here -- the same reason the 5.5
repair pass below did not move them either.

NOT RE-BASELINED BY THE [34.6]/[59.3] INITIAL AIR STRENGTHS (2026-07-22) OR BY ITS REPAIR PASS THE
SAME DAY, AND THAT WAS CHECKED RATHER THAN ASSUMED -- TWICE, for two different sets of changes.

The establishment block replaced game.air's representative-aircraft proxy with [60.32]/[60.42]'s real
musters and seeded GameState.air_unfit from [59.32]'s Refitted column; the repair pass then made
43.12 bind on a NATIONALITY rather than on three named types (basing.german_bombers), withdrew the
transplanted [63.46] Italy/Sicily posture to unseeded (basing.discretionary_pct answers 0), and BUILT
[59.36]/[60.32]'s "no maintenance in the first OpStage" as a gate at the top of engine.
_air_maintenance. NONE of it reaches these two logs, and the reason is one fact: NEITHER BENCHMARK
FIELDS AN AirWing (`scenario.rommels_arrival` has no air at all; `siege_of_tobruk` takes its wings
only under port_bomb/raf). With `state.air` empty, _air_maintenance returns before its new gate,
rule 43 has no squadron to take a share of, and no roster conversion is ever asked for. The CAMPAIGN
log does move -- that is the point of the block -- and the campaign is not signature-pinned (see
CAMPAIGN_SEED below, which pins a SEED and a set of narrative assertions, not a hash).

NOT RE-BASELINED BY THE 5.5 REPAIR PASS (2026-07-21), AND THAT WAS ALSO CHECKED RATHER THAN ASSUMED.
The
repair made rule 43 deduct from Africa exactly what it bases in the Mediterranean (game.basing --
before it, the same bombers were counted in Sicily for the Malta raid AND in Africa for Land
Support), moved the basing cut ahead of the air-superiority scale, and reordered the Convoy Planning
Phase behind the Strategic Air Planning Stage as 48 orders them. Both signatures were recomputed
twice each on the repaired tree and are UNCHANGED -- the basing arithmetic has no squadron to bite
on here, and the beat reorder swaps the convoy phase with two Malta beats that emit nothing when
there is no Malta in the scenario.

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-21 (earlier the same day) -- CAUSE: the 5.1 REPAIR PASS. 36.17 held in one scan
and leaked in three others, and 35.14's water was held to a stricter standard than the whole army's.

Three of the repairs move these logs, and each is a rule, not a tuning:

  * 36.17 -- "LAND UNITS MAY NOT USE AIRFIELD SUPPLY DUMPS." The 48 V.C.6 Supply Distribution top-up
    (engine._supply_distribution) enumerated active_supplies itself, filtered on the hex alone, so a
    land unit standing on an air facility refilled its 49.14 tank and 50.0 load off the squadron's
    larder. Measured on the previous tree, campaign seed 4 x 12 Game-Turns: 314 Fuel + 108 Ammo Points
    walked out of Axis air dumps into land combat units. It now asks supply.colocated_dumps -- the
    same enumeration in_hex_draw asks -- so the exclusion cannot drift apart from the draw again.
  * 36.17 -- "an AIRFIELD IS a supply dump for supplies to be used by the SGSU's ON THAT AIRFIELD."
    The rule-32.3 leapfrog drove the pile away: measured, all eleven campaign air dumps left their
    facility within six Game-Turns (four stacked on one desert hex) and the air force went
    permanently unsupplied beside its own empty fields; in the benchmark, Air-Strip-allied#2-Supply
    walked off its strip on rommels_arrival(42). The rejection now lives at the engine's acceptance
    boundary (_supply_movement), so it binds every policy, with the scripted/storm leapfrogs no
    longer proposing what must be rejected.
  * 35.14 water -- switched from supply.in_hex_draw to supply.plan_draw, the abstract half-CPA trace
    EVERY land unit's rule-52 water already rides, because the S8 investigation measured the naive
    in-hex water draw unfaithful until 52.45's water trucks are built. Holding an SGSU stricter than
    the infantry it services was that same unfaithfulness twice over: [60.44] charts the Commonwealth
    air facilities no water at all, so the in-hex rule denied every RAF squadron its 35.14 water on
    Game-Turn 1 of the campaign and permanently after, out of a chart's silence. Stores and Fuel stay
    IN HEX on the 36.17 pile; reachable_supplies is air-aware for an SGSU so the trace still sees the
    facility's own dump first.

(Also in the pass and NOT moving these two logs, because they are campaign-only or inert here: the
64.71/64.72 victory predicate no longer counts an air dump as a Supply Dump; [60.5]'s ownership rule
moved Sollum C4021 -- in Egypt -- to the Commonwealth; [59.52] one-hex-one-dump now constrains where
the air allotment is placed; the campaign stranded-column rescue no longer marches at an air dump.)

MEASURED, campaign seed 4 x 12 Game-Turns after the repairs: SUPPLY_MOVED on an air dump 0 (was 69),
UNIT_REFILLED from an air dump into a LAND unit 0 (was 332 events / 422 Points), SGSU_UNSUPPLIED 7
(was 318), SGSU_SUPPLIED 3 (was 0). Every air dump ends the run on its own facility hex. Determinism
holds byte-for-byte, each signature reproduced twice.

    rommels_arrival   9f5c4befd42b -> b805053d4d26
    siege_of_tobruk   81344040fade -> 5c02a1f22398

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-21 -- CAUSE: rules 36 + 35 -- air facilities and SGSUs became real (Phase 5.1).

The Air Landing Strips and flying-boat Alighting areas the order of battle has carried since Phase
3.1 were built as inert `air`-role UNITS with CPA 0. They are not units: rule 36 makes an air
facility an INSTALLATION with a Capacity Level bombs take down (36.14/41.36), and rule 35 makes the
Squadron Ground Support Unit the separate counter that works it. So the facilities left units[] for
GameState.air_facilities, the SGSU counters kept their place under a new `sgsu` role, and three
rules came on with them:

  * 36.17 -- an airfield IS a supply dump for its SGSUs. The [61.36]/[61.44] air-supply allotment
    (CW 250 Ammo / 180 Fuel / 50 Stores; Axis 50/50) is seeded into air_dump SupplyUnits on the
    facility hexes. Rule 59.61 suppressed that row only "without the Air Game"; we play it now.
    A land unit may not draw from an air dump, so the army's own ledger is untouched by the seeding.
  * 35.14 -- each SGSU expends 1 Stores per Game-Turn and 1 Fuel + 1 Water per Operations Stage,
    drawn IN HEX. Both benchmark SGSUs stand away from both strips (the extraction's hexes: A2629
    and B5504 against strips at B4006 and C4808), so they go short and carry the counter rule 35.14
    grounds a squadron on -- a faithful consequence of the OOB, not a tuning choice.
  * 59.61 T0-18 -- the [61.43] "10 Medium Trucks at air facilities" row is no longer gated off.

Two units left the board and one truck formation grew, so both logs move from their first event.
Determinism holds byte-for-byte (each signature reproduced twice, on the final tree).

    rommels_arrival   098e6d9539c1 -> 9f5c4befd42b
    siege_of_tobruk   99853cb45586 -> 81344040fade

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-19 -- CAUSE: 12.24/3.6 -- barrage fires BLIND, no longer at the strongest unit.

_barrage_target picked the defender's STRONGEST combat unit -- but the barraging Player fires "blind"
(12.24: states only the target's CLASS; 12.23/3.6: never its strength), so concentrating fire on the
best counter is a limited-intelligence violation. Owner-ruled (Eve) to a NEUTRAL, deterministic blind
pick: the lowest unit-id present, favouring neither side. All four callers (artillery barrage, the
barrage step, naval bombardment) inherit it; it is inert on single-unit hexes and only bites multi-
unit stacks. NO magnitude invented (the CRT resolution on the picked unit's class is unchanged). Both
benchmarks barrage multi-unit stacks, so both logs move; barrage is now markedly less punishing to a
stack's top unit. Determinism holds byte-for-byte. (The two other flagged rulings -- 54.17 demolition
modifiers and 51.23 half-rations -- were owner-ruled DEFER/SKIP, so they touch nothing.)

    rommels_arrival   d5c4f2138b0b -> 098e6d9539c1
    siege_of_tobruk   a38a2bd066e3 -> 99853cb45586

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-19 -- CAUSE: 15.21 -- an Anti-Armor firer may not also Close Assault.

Rule 14.0/14.26/15.21: "Units assigned to Anti-Armor may not participate in Close Assault... he may
not use a given TOE Strength Point for both in the same Segment." The engine fired anti-armor
(_anti_armor_step) and then let the SAME phasing units join the close assault (_resolve_combat's
armed_atk), double-counting their TOE and drawing their ammo twice. Now _combat threads a per-segment
`fired_anti_armor` set: _anti_armor_step records every PHASING firer, and _resolve_combat excludes
them from armed_atk (before the ammo draw). A stack whose only attackers fired anti-armor has its
assault rejected (15.29). The 15.84/12.11 defender-side symmetry (auto-firing armored defenders) is
deferred and flagged -- 15.21 names "Phasing units", and the engine gives the defender no assignment
agency. NO magnitude was invented. Both benchmarks field armored clashes, so both logs move; the
change nudges armored-assault balance toward the defender (the attacker's tanks no longer fire AND
assault). Determinism holds byte-for-byte.

    rommels_arrival   a2c8223bcdd8 -> d5c4f2138b0b
    siege_of_tobruk   1a3948403add -> a38a2bd066e3

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-19 -- CAUSE: the 52.51/52.52 effects of lack of water (movement + combat).

A unit out of water this Operations Stage (52.5, stages_without_water>0) now suffers the immediate
effects the rules give it, not just the 52.53 slow attrition: 52.51 a dry VEHICLE may not move (in
_movement's phasing/continual path AND _react's 8.5 reaction); 52.51/52.52 a dry unit may not
OFFENSIVELY close-assault (dropped from _resolve_combat's armed_atk before it charges ammo); and
52.51/52.52 a dry DEFENDER defends at HALF strength (engine._def_raw halves its raw_defense in the
15.79 differential + the 17.26 overwhelm test; the casualty pool keeps full TOE). Both benchmark
scenarios carry water and field thirsty vehicles, so both logs move. NO chart magnitude was invented
-- 52.51/52.52 ARE the book's rules. MEASURED (scratchpad/ab_water.py): campaign(1941) and campaign(7)
keep the SAME winner + 64.76 grade (Axis Smashing), with VP shifting CONSISTENTLY toward the
Commonwealth (the advancing DAK is thirstier than the coastal Eighth Army, so the desert hampers the
overextended attacker) at the faithful 12% campaign thirst. The benchmarks are hit harder by their
KNOWN 70% over-dryness (phase4-s8-water-finding: water's ½-CPA proxy is too dry at the Desert Fox
point) -- rommel's DAK closest-to-Tobruk 6 -> 32 hexes -- which amplifies a documented water-model gap,
not this rule. Determinism holds byte-for-byte.

    rommels_arrival   7a806c08679d -> a2c8223bcdd8
    siege_of_tobruk   ed4f7d1661c9 -> 1a3948403add

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-19 -- CAUSE: Phase 4 S7, in-hex STORES (rule 51.15; 51.0 gives NO organic pool).

Stores joined fuel (S5) and ammunition (S6) in the full-game in-hex model -- but stores are NOT shaped
like them, and getting that right was the whole slice. The 51.0 GENERAL RULE (verbatim): "Stores are
different from other types of supply in that they are distributed at the beginning of the Game-Turn,
rather than during each Operation Stage, and ... units may get along without them, albeit with limited
effectiveness and with the possibility of attrition." There is NO 49.14/50.0-style organic reservoir:
a unit carries zero stores of its own (51.15: "Stores must be present in the hex to be used. Stores on
truck convoys cannot be used until off-loaded"), so its whole 51.11/51.13 upkeep -- 4 Stores per TOE
Strength Point per Game-Turn, 1 flat for HQ/engineers -- is drawn wholly from a co-located dump. The
one change: the stores CONSUMER (engine._stores_expenditure, the 48-IV once-per-game-turn Stores
Expenditure Stage) switched from the abstract 32.16 half-CPA trace (supply.plan_draw) to
supply.in_hex_draw. A unit with no stores in its hex goes short, and the ALREADY-BUILT 51.21
disorganization + 51.22 progressive infantry-only attrition consequence bites -- that consequence code
did not change. Water (incl. the 52.6 pasta water) stays on the abstract trace until S8; the 64.73
victory-supply trace stays abstract (its own later slice); first-line trucks (fl_*) stay dormant for
stores exactly as for fuel/ammo -- stores have no organic pool to refill, so they do not even join the
48 V.C.6 refill beat; truck-borne stores headroom is the deferred last-mile slice.

NO chart magnitude was bent -- 51.11/51.13/51.15 ARE the book's rules; the abstract 32.16 half-CPA
trace (Section 32, which rule 3 of this port says DOES NOT APPLY) is replaced by the full-game in-hex
draw. MEASURED (scratchpad/ab_stores.py), an A/B of the S6 tree (94941cb, abstract) vs this one: strict
in-hex is SURVIVABLE and OUTCOME-NEUTRAL, not a starvation cliff. campaign(1941) lands the IDENTICAL
Axis Smashing Victory 440-20 both ways; rommels_arrival(42) is identical in units-alive / Tobruk-holder
/ surrenders. In-hex adds shortfall PRESSURE (+18% shortfall events on 1941, peak ~394 units short in a
single turn) but the extra shortfalls are TRANSIENT -- a mobile force briefly outrunning its dumps,
resupplied before the 51.22 two-consecutive-turn threshold -- so total attrition does NOT rise
(1475 -> 1378 steps on 1941) and both armies stay fully intact. That is the faithful picture of desert
logistics, not a front-wide melt. Determinism holds byte-for-byte.

    rommels_arrival   09047f3b3edd -> 7a806c08679d
    siege_of_tobruk   1432ddbe2e02 -> ed4f7d1661c9

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-19 -- CAUSE: Phase 4 S6, in-hex AMMUNITION (rule 50.0's intrinsic basic load).

Ammunition joined fuel in the full-game in-hex model. Rule 50.0 (GENERAL RULE, scan PDF p.67, verbatim)
gives every unit an intrinsic pool -- "Each TOE Strength Point may carry (i.e., transport by itself
WITHOUT trucks) only enough ammo to fire once" -- the exact dual of the 49.14 fuel tank. So:
  (1) supply.ammo_capacity(u) = max applicable 50.2 rate (barrage 4 / anti_armor 3 / assault 2) x
      strength -- one full firing -- is seeded onto every unit (oob._seed_ammo_loads) and credited to
      initial_supply, exactly as _seed_fuel_tanks does the tank. (This alone is byte-identical -- the
      abstract trace never reads unit.ammo.)
  (2) the ammo CONSUMERS switch from the abstract 32.16 trace (supply.plan_draw) to supply.in_hex_draw
      (engine._charge_ammo/_has_ammo + the policy/observation assault gates): a unit fires from its own
      50.0 load first (49.16), then a co-located dump (50.15 "consumed only if present in the hex"),
      never a traced dump. Firings now emit UNIT_SUPPLY_CONSUMED off the load / a co-located-dump
      SUPPLY_CONSUMED where they emitted a traced-dump SUPPLY_CONSUMED, and the 48 V.C.6 refill beat
      (engine._supply_distribution) tops AMMO as well as FUEL (new UNIT_REFILLED(AMMO) beats).
Both logs move wholesale. NO chart magnitude was bent -- 50.0/50.14 and the 50.2 rates ARE the book's
rules; the abstract 32.16 half-CPA trace (Section 32, which rule 3 of this port says DOES NOT APPLY)
is replaced by the full-game in-hex draw (50.15/50.17). MEASURED (scratchpad/ab_rommel.py): the abstract
trace was STARVING the advancing DAK -- forward German units beyond cpa/2 trace of a dump could not fire
and surrendered en masse (16 Axis surrenders, survivors 45 hexes back). The faithful 50.0 load fixes it:
the DAK fights forward to the Tobruk perimeter (closest 45 -> 6 hexes, combat units alive 12 -> 19,
Axis surrenders 16 -> 6) and Tobruk still HOLDS -- more faithful AND more competent. First-line trucks
(fl_*) stay dormant for ammo exactly as for fuel; truck-borne headroom is a separate later slice.
Determinism holds -- each new hash reproduced byte-for-byte on the verification VM.

    rommels_arrival   808baa7e75b3 -> 09047f3b3edd
    siege_of_tobruk   7fce3d6ab80b -> 1432ddbe2e02

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-18 -- CAUSE: Phase 4 S5, in-hex fuel + the competent baseline it requires.

The Logistics Game went in-hex, and the deterministic baseline was made competent under it:
  (1) Movement fuel is drawn IN THE HEX (game.supply.in_hex_draw) -- the unit's own 49.14 tank first,
      then a co-located dump -- not the abstract 32.16 half-CPA trace; every move now emits
      UNIT_SUPPLY_CONSUMED off the tank (or a co-located-dump SUPPLY_CONSUMED) where it emitted a
      traced-dump SUPPLY_CONSUMED.
  (2) ScriptedPolicy was made competent under that faithful rule (rule 53.0: "without a well-organized
      convoy system your entire military effort will fall apart"): its movement proposes only
      FUEL-AFFORDABLE hexes (supply.affordable_reach, so a unit is never ordered past its own fuel);
      its logistics run the shared multi-hop forward relay + 24.9 dump construction (game.relay,
      extracted from campaign_policy now the byte-lock is dropped, and made the base ScriptedPolicy
      doctrine) in place of the single-hop shuttle that could not follow an advance; and siege_of_tobruk
      fields the real [61.43] Axis 2nd/3rd-line truck OOB (95 L / 280 M / 50 H = 425 Truck Points) in
      place of a self-flagged 14-point placeholder.
Both logs move wholesale. NO chart magnitude was bent -- 32.16 (abstract) is replaced by the full-game
in-hex supply (49.15 / 53-54), and one placeholder is replaced by its transcribed [61.43] chart value.
Determinism holds -- each new hash reproduced byte-for-byte on the verification VM.

    rommels_arrival   08ae216a5c78 -> 808baa7e75b3
    siege_of_tobruk   1b380c501dcf -> 7fce3d6ab80b

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-17 -- CAUSE: Phase 3.1, the T0-6 Order-of-Battle reclassification (game/oob.py
classify() + data/oob_*.json). Both benchmarks build oob_desert_fox.json, and the change that moves
them is single and specific: the four Allied air-game counters that carried the OOB (two Squadron
Ground Support Units, two Air Landing Strips) were being DISCARDED by classify() (it returned None
for anything matching "Air Strip"/"SGSU"/"Alighting"); they are now KEPT as inert non-combat `air`
pieces (rule 3.21: is_combat False, sp 0 -- no ZOC, no city, no stacking cost, and supply-EXEMPT:
rule 35.14 draws an air piece's supply from the air game, never the land dumps, so engine._stores_
expenditure/_water_distribution skip them). They hold no ground either (_record_control is combat-
gated). But they ARE units in the built state, so (a) they change the initial-setup portion of the
event log and (b) the barrage/combat adjacent-hex target search reads every unit in a neighbouring
hex (state.enemies_at is not combat-filtered, exactly as it already reads a bare HQ), so on the
chaotic 12-turn siege their presence shifts which seeds reach the 25.14 wall-batter -- the same
single-seed chaos the two siege seed-pins in test_ports/test_convoys were re-pinned for. Both logs
therefore move wholesale. desert_fox fields NO phantom-tank/AA correction (those counters are all in
the campaign-only oob_italian.json), so nothing else in these two scenarios moved. NO chart magnitude
was bent -- the counters were already in the OOB and are simply no longer thrown away. Determinism
holds: each new hash reproduces byte-for-byte across two runs.

    rommels_arrival   bfedbc714c50 -> 08ae216a5c78
    siege_of_tobruk   e9ecbb40f2f8 -> 1b380c501dcf

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-16 -- CAUSE: the Tobruk port Efficiency, resolved to the [55.3] chart.

The book prints two irreconcilable starting Efficiencies for Tobruk, and both were verified against
the original scan (not the OCR): the [55.3] chart (PDF p110) lists "Tobruk† Efficiency Level 5 |
Maximum Tonnage 1,700", its dagger says the campaign "begins ... with an efficiency below the listed
five due to the San Girogio [sic] partially blocking the harbor", and 55.25 makes that block three
levels -> eff 2. But 60.7 (PDF p79) prints "Tobruk, which is at Efficiency Level 7" and 61.6 (p81)
"Tobruk (at seven-and San Giorgio is still there)" -- the digit on one page, the word on another, so
it is the book contradicting itself, not a mis-read.

THE ENGINE NOW FOLLOWS THE CHART, campaign and benchmark from one call (scenario._tobruk_port):
eff 2, max_eff 5, blocked 3. The 7 is unrepresentable in the chart's own machinery -- 55.18 forbids a
level above the 55.3 assigned maximum, and the legend defines capacity only as a reduction FROM the
listed level, so a 7 on a listed-5 port has no defined capacity. This REVERSES the previous commit,
which seeded 7/7 by raising max_eff to 7: that silently re-denominated the legend's charted per-level
damage fraction from 1/5 to 1/7 (each [41.5] harbour hit costing 243 t instead of 340 t) and left
55.25/55.26 and the charted Tobruk unblock cost as dead content. NO chart magnitude is bent now --
max_eff IS the listed level, and both benchmarks' Tobruk drops from a 1700 t/OpStage shared budget to
the charted 680 t (1700 at eff 2/5), so every ferry landing in both logs moves wholesale.

The acceptance survives the stricter harbour: Tobruk still holds 6/6 in test_ports, and the garrison's
~176 Stores/turn draw is still covered (94/OpStage x the 48 V.D three stages = 282). Determinism holds:
each new hash reproduces byte-for-byte across two runs.

    rommels_arrival   b07f0230d4d3 -> bfedbc714c50
    siege_of_tobruk   27dd33318b00 -> e9ecbb40f2f8

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-15 -- CAUSE: T0-11, weather localisation (29.7) + truck-cargo evaporation (29.34).
Foul weather no longer blankets the whole theatre: a Sandstorm/Rainstorm now lands on only the 2-3
map-sections the 29.7 Foul Weather Location Table names (29.41 keeps a sandstorm off the delta), every
section outside it reads Normal (29.1), and the WEATHER_ROLLED event carries the localised sections.
BOTH benchmarks play sections A/B/C, so a storm confined to some of them changes what their
movement/breakdown/repair do where before it blanketed all three. The same commit evaporates the
Fuel/Water CARRIED BY TRUCKS (29.34: the hot 5% "includes water and fuel in dumps as well as in
trucks"; 49.3: fuel evaporates "regardless of where it is kept", only convoys at sea exempt) -- both
benchmarks field two truck formations that pick up cargo during the run, so their freight now
evaporates too. Those two together move the whole log, and they move the rare 25.14 wall-batter onto
different seeds (see test_convoys / test_ports, re-pinned 197,220 -> 37,57). (The 29.53 rainstorm
well-refill is campaign-only -- the benchmarks seed no wells.) NO chart magnitude was bent -- 29.7's
section table, 29.41's delta exclusion, 29.1's normal-elsewhere, 29.34's explicit inclusion of trucks.
Determinism holds: each new hash reproduces byte-for-byte across two runs.

    rommels_arrival   c95e597471fc -> b07f0230d4d3
    siege_of_tobruk   14493e87b924 -> 27dd33318b00

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-15 -- CAUSE: the Tobruk-harbour block (T0-9 + 48 V.D + 55.18 + T0-10). The
Naval Convoy Arrival Phase now runs EVERY Operations Stage (48 V.D: the Second and Third Operations
Stages repeat all facets of the First, 48 VI/VII), so the turn's SURVIVED convoy manifest unloads
across the three stages instead of once at Stage 1 -- both benchmarks land the SEA-TOBRUK ferry and
the rear convoys through a harbour, so their delivery beats move wholesale. Port regeneration (55.18)
became an end-of-OpStage step conditional on the port not losing levels to Enemy bombs that stage,
where it was an unconditional once-per-turn step. And the San Giorgio block moved from a
never-regenerates HARBOUR_BLOCKED frozenset to a per-port blocked-levels count (Port.blocked), so a
bombed harbour recovers up to max_eff - blocked. (T0-10 -- _air_port rolling on the transcribed [41.5]
Ports row -- does not touch these two signatures: the DEFAULT rommels_arrival/siege_of_tobruk seed no
air, so no _air_port fires; it moves only the port_bomb=True variants and the campaign.) NO chart
magnitude was bent -- these ARE the rules the 1979 book prints (48 V.D, 55.18, 55.25/55.26).
Determinism holds: each new hash reproduces byte-for-byte across two runs.

    rommels_arrival   885fe7721583 -> c95e597471fc
    siege_of_tobruk   f1adc99b60b4 -> 14493e87b924

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-14 -- CAUSE: the Phase-0.3 supply-faucet block. Two of its six items move the
benchmark logs. T0-3: the 55.3 port throttle is ONE shared tonnage budget across ALL commodities per
Operations Stage (landed proportionally when the manifest outweighs it), not the whole tonnage spent
again on each commodity -- so every harbour delivery in both scenarios changes. T0-7: rule 29.35, hot
weather DOUBLES water requirements, where the engine had added a flat +1 -- so the water gate over
every multi-TOE vehicle moves. Both benchmarks land convoys through a port and run vehicles in hot
weather, so both logs move wholesale. The other four faucet items are campaign-only and touch neither
benchmark: T0-2 (section-60 pools -- the Desert Fox benchmarks correctly keep section 61 per 64.3),
T0-4 (charted port efficiencies, campaign ports), T0-12 (captured-supply tax, gated on dump_capture),
T0-17 (the Tobruk convoy size, campaign lanes). NO chart magnitude was bent -- these ARE the charted
magnitudes (55.3's total tonnage; 29.35's doubled water). Determinism holds: each new hash reproduces
byte-for-byte across two runs.

    rommels_arrival   6f3f33484911 -> 885fe7721583
    siege_of_tobruk   443e21f712cf -> f1adc99b60b4

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-14 -- CAUSE: the Phase-0.2 chart fixes (T0-1, T0-8, T0-19), the numbers we
mis-read off the 1979 scan. T0-1: broken-tank FIELD repair is 10% on a die of 2/3/4, not 100% -- the
OCR bled "10%*" into "100%" (combat_tables._FIELD_REPAIR + data/breakdown_rates.json; re-read off PDF
p103). T0-8: the close-assault fortification shift is L2/L3/L4 for Levels 1/2/3 (chart 8.37), not
level*(-2) = -2/-4/-6 (combat_tables.FORT_CA_SHIFT_BY_LEVEL; re-read off PDF p70). T0-19: field tank
repair expends one Fuel Point per BROKEN TOE Strength Point undergoing repair (22.26), not a flat 1.

All three change how armour breaks down, comes back, and how a Close Assault on a fortified hex
resolves, so both benchmark logs move wholesale. rommels_arrival carries broken-tank repair and close
assault; siege_of_tobruk adds the Tobruk (Level 2) wall. NO chart magnitude was bent -- these ARE the
charted magnitudes, replacing OCR/reading errors. Determinism holds: each new hash reproduces
byte-for-byte across two runs.

    rommels_arrival   0a64c64bd50f -> 6f3f33484911
    siege_of_tobruk   6ea7e495d772 -> 443e21f712cf

--------------------------------------------------------------------------------------------------
RE-BASELINED 2026-07-14 -- CAUSE: T0-5, rule 6.27 (Cohesion is AVERAGED over the largest units in a
Close Assault, not read off the single strongest unit) plus the two fixes it travels with -- 6.24.2
(a victorious assault that empties the defender's hex earns the attacker +3 Reorganization Points)
and 6.26 (a unit at Cohesion -26 or worse may not move or attack). engine.py: _stack_cohesion feeds
_adjusted_morale and _defenders_capitulate; _award_vacate_rp; the two -26 gates.

The Morale/Cohesion inputs to every Close Assault changed, so the 17.4 roll and the 15.88 auto-
surrender resolve differently and both benchmark logs move wholesale. No chart and no magnitude
changed -- only which combats reach the CRT instead of ending in an instant Surrender. Determinism
holds: each new hash reproduces byte-for-byte across two runs.

    rommels_arrival   25dab11970be -> 0a64c64bd50f
    siege_of_tobruk   75a988428896 -> 6ea7e495d772

RE-BASELINED 2026-07-14 -- CAUSE: T0-0, the per-subsystem dice streams (game/dice.py).

    rommels_arrival   9339d2b308d7 -> 25dab11970be
    siege_of_tobruk   5ba4da88d107 -> 75a988428896

The engine drew every die in the game -- weather, initiative, combat, breakdown, repair, morale,
demolition, interdiction, air -- from ONE random.Random seeded with the master seed. Subsystems draw
CONDITIONALLY, so the NUMBER of draws in one subsystem re-indexed the dice EVERY OTHER SUBSYSTEM
saw. That is not a rules bug, it is an INSTRUMENT bug, and it silently corrupted every A/B this
project ever ran: Malta was measured through it, found "causally inert", and written into project
memory as a settled dead end.

Each subsystem now has its own stream, derived from the master seed. Every die in the game is drawn
from a different (equally uniform) sequence than before, so both logs change wholesale. No rule, no
chart and no magnitude changed with them -- only which face each die came up. THE BYTE-LOCK IS
DROPPED (the owner has agreed); these hashes are a determinism check, not a constraint on the port.

WHY THE OLD DISCIPLINE FAILED, in one line: the byte-lock rewarded NOT drawing a die, and "do not
draw a die when the feature is off" is exactly what desynchronised the engine. It was good
discipline for a walking skeleton and it became the thing that broke the measurements.
--------------------------------------------------------------------------------------------------
"""
from __future__ import annotations

import hashlib

ROMMELS_ARRIVAL = "e1d1fa771ce3"     # re-baselined 2026-08-02, [10.29] (top of this file)
SIEGE_OF_TOBRUK = "19693b23b988"     # re-baselined 2026-08-02, [10.29] (top of this file)

BENCHMARKS = {"rommel": ROMMELS_ARRIVAL, "siege": SIEGE_OF_TOBRUK}


# --------------------------------------------------------------------------------------------------
# THE CAMPAIGN BEHAVIOUR SEED -- and the fragility it is hiding, which is a REAL FINDING, not a knob.
#
# The campaign behaviour suites (concentration / claim / faucet / campaign) each run ONE campaign and
# assert an emergent outcome of it: the Eighth Army concentrates on the Mersa Matruh railhead and
# HOLDS it, the rail faucet keeps running, the lorries cycle, cities get banked. All of them ran on
# seed 1941, and all of them went red when T0-0 corrected the dice.
#
# THEY WERE NOT ASSERTING THE WRONG THING. Measured over 8 seeds, at GT12, with the SAME policies:
#
#     the Commonwealth holds Mersa Matruh in 6/8 seeds under the OLD shared-stream engine
#     the Commonwealth holds Mersa Matruh in 6/8 seeds under the NEW per-subsystem engine
#
# The distribution is UNCHANGED -- the concentration works exactly as well as it did. What changed is
# WHICH seeds are the unlucky two: 1941 and 123 now lose the railhead, where 7 and 2026 used to. Seed
# 1941 simply stopped being a lucky seed. That is single-seed chaos, and no stream discipline removes
# it (game/dice.py): a rule change moves outcomes, outcomes move later dice, and a campaign pinned to
# one seed is measuring that seed's luck.
#
# So the seed moves and EVERY ASSERTION STAYS. Seed 99 is chosen because the Commonwealth holds the
# line on it under BOTH the corrupted and the corrected instrument (railhead garrison 5 -> 6 units,
# 2 cities banked either way) -- it is not a seed shopped for the new dice.
#
# 🔴 THE FINDING, AND IT SHOULD NOT BE BURIED IN A TEST FILE: when Mersa Matruh falls, the ENTIRE
# Commonwealth campaign unravels behind it -- the railhead retracts to Alexandria (54.3), the rail
# faucet switches off, the lorry relay has nothing to haul and nowhere to haul it, and the army banks
# no victory city at all. One lost combat on one hex, in roughly one campaign in four, and the
# Commonwealth's whole logistical spine is gone. That is a balance/robustness finding for the owner,
# not something to tune away here -- and it is only VISIBLE now that the instrument works.
#
# THE REAL FIX IS METHODOLOGICAL, and it is the plan's own Phase 0.3: a campaign claim must be a
# DISTRIBUTION OVER N >= 30 SEEDS, not one run. Until that lands, these suites remain single-seed
# narratives and this constant is the honest label on them.
#
# RE-PINNED 99 -> 7 (T0-5, rule 6.27 Cohesion averaging + 6.24.2 victory RP + 6.26 the -26 gate).
# The combat resolver changed, so seed 99's single campaign moved -- and it moved into the unlucky
# ~1-in-8 where the Commonwealth loses Mersa Matruh at GT12 (the railhead garrison can no longer
# trace supply; the spine unravels exactly as the FINDING above predicts). This is the same
# single-seed chaos, not a regression: measured over seeds 1..24 under the corrected engine, the
# Commonwealth HOLDS the railhead on 21 of 24. Seed 7 is one of them (near-railhead concentration 7,
# well clear of the >=3 floor), it is one of the canonical SEEDS, and it already held under the
# per-subsystem T0-0 engine -- it is not a seed shopped for these dice.
#
# RE-PINNED 7 -> 4 (T0-15, the [7.2] Initiative Ratings chart + Rommel's 64.2 arrival). The chart
# is what determines who holds the Initiative each game-turn, and the Initiative side sets the 7.11
# A/B move order -- so wiring it changed WHICH side moves first, every turn, and with it the whole
# campaign trajectory. Before, both sides rolled a bare d6 (rating 0): a fair coin. Now the early
# game is faithfully Commonwealth-tempo'd (the 1940 Italians are rating 1 to the Eighth Army's 3, so
# the Commonwealth holds the Initiative ~81% of GT2-26), and seed 7's single campaign moved into the
# unlucky ~1-in-5 that loses Mersa Matruh at GT12 -- the same spine-unravelling the FINDING above
# describes. Not a regression: measured over seeds 1..40 under the chart, the Commonwealth HOLDS the
# railhead on 32 of 40 (80%), the same distribution the T0-5 note found. Seed 4 is one of them, it
# passes every campaign-narrative assertion AS WRITTEN (no floor was lowered), and its near-railhead
# concentration is 9 -- the widest margin over the >=3 floor of any candidate, so it is chosen for
# robustness, not shopped for green. (The dump-network fixture in tests/test_dumps.py is pinned
# separately at seed 99; the chart moved its 30-turn slice too, and its one broken assertion was a
# fragile 'the FIRST founded dump is filled' -- restated in place to the thesis it always meant, that
# SOME founded dump is filled, true on 29 of 31 seeds. See that file.)
#
# RE-PINNED 4 -> 23 (2026-08-02, [52.42] -- the CPA condition on the vehicle's Water Point). Same
# mechanism as every re-pin above and the same discipline, but this time the DISTRIBUTION MOVED TOO
# and that is recorded rather than absorbed. Swept over ONE HUNDRED seeds, campaign to GT12,
# CampaignAxisPolicy vs CampaignCommonwealthPolicy, on both trees:
#
#     the Commonwealth still holds Mersa Matruh at GT12 on   87 of 100 seeds BEFORE
#                                                            72 of 100 seeds AFTER
#     it flips BOTH ways -- 23 held->lost, 8 lost->held -- so it is not a re-shuffle, it is a real
#     modest adverse lean of about fifteen points, roughly four standard errors.
#
# AND THE CAUSE IS THE CORRECTION DOING ITS JOB, measured on the same 100 seeds: the AXIS army at
# GT12 is 60.57 -> 65.96 combat units (+5.4) while the Commonwealth is 37.81 -> 37.31 (flat). The
# old stage-start bill was a tax on whoever owned the most vehicles, and that is the Axis: 1,616 of
# the order of battle's 2,057 Water Points a stage. Stop charging a rule the book does not print and
# the Italian 10th Army stops dying of thirst it never owed -- so it survives, and the Eighth Army
# faces more of it. This makes the KNOWN Axis lean slightly worse and it is NOT tuned away here
# (CLAUDE.md rule 1); it is the faithful consequence of the printed condition, and Gate C's balance
# work is where it belongs.
#
# Seed 23 is chosen the way seed 4 was: it holds the railhead under BOTH instruments (pre- and
# post-52.42), it passes every narrative assertion AS WRITTEN with no floor lowered, and of the four
# candidates that do (1, 8, 21, 23) it is the only one that also carries a Commonwealth unit within
# 15 hexes of the railhead on the PRE-change tree, and it fields the largest surviving Commonwealth
# force at GT12 (44 combat units). It is not a seed shopped for the new dice.
#
# *** DELIBERATELY NOT RE-PINNED 2026-08-02, CAUSE [10.29] -- AND THE REASON IS THE LARGEST FINDING
# OF THAT SLICE. *** engine._capture_noncombat takes a non-combat counter with no strength of any
# type when it is left alone in an enemy ZOC during the enemy's Movement/Combat Phase. Swept over
# ONE HUNDRED seeds, campaign to GT12, CampaignAxisPolicy vs CampaignCommonwealthPolicy, on both
# trees (the pre-change arm is a `git archive HEAD` control tree, not this one with a flag off):
#
#     the Commonwealth still holds Mersa Matruh at GT12 on   60 of 100 seeds BEFORE
#                                                            13 of 100 seeds AFTER
#     51 held->lost against 4 lost->held. This is not a re-shuffle and it is not modest.
#
# THE CAUSE IS THAT THE GRIP WAS SUBSTANTIALLY THE BUG. [60.5] seeds THREE Commonwealth Squadron
# Ground Support Units on the Mersa Matruh railhead. They have no rating of any type, so under the
# old engine they could hold the terminus against the whole Panzerarmee and bank nothing with it:
# [8.13] bars entry into a hex containing ANY enemy unit, [10.11]/[64.73] give a bare SGSU no ZOC,
# no ground and no city, engine._absorb_losses cannot take a step off a unit with no rating and
# [15.15] never fires off its [50.0] basic load -- the hex was unenterable, unflippable, unkillable
# and unstarvable. Spot-measured on the pre-change tree at seeds 1/5/6/8: the railhead spends 7, 27,
# 5 and 7 of its 35 Operations Stage closes in exactly that state, occupied ONLY by non-combat
# counters with an Axis combat unit adjacent. On those boards the Eighth Army's grip on its own
# railhead was an invisible garrison the book says is captured.
#
# NINE SEEDS STILL HOLD IT UNDER BOTH INSTRUMENTS ({2, 29, 32, 35, 41, 54, 58, 67, 84}; thirteen on
# this tree, adding {57, 61, 75, 80}), so a re-pin was available and was NOT taken. Re-pinning would
# have made five campaign-narrative tests pass as written while concealing the single most important
# thing this slice measured -- and this note's own discipline is that a moved distribution is
# "recorded rather than absorbed". The five are RESTATED instead, each with the trace and the
# measurement, and each keeps its INVERT-THIS instruction for the day a faithful forward Commonwealth
# garrison policy stops leaving the terminus to its ground crews:
#     test_campaign_concentration.py::test_the_railhead_is_held_and_the_faucet_keeps_running
#     test_campaign_concentration.py::test_the_standing_garrison_order_still_holds
#     test_campaign.py::test_campaign_commonwealth_can_attack
#     test_campaign_faucet.py::test_the_commonwealth_trucks_actually_run
#     test_campaign_claim.py::test_both_sides_take_the_cities_they_used_to_sprint_past
# Whoever re-pins CAMPAIGN_SEED next should read those five first: three of them now assert the
# LOSS, and a seed that holds the railhead will fail them in the good direction.
#
# *** AGAIN DELIBERATELY NOT RE-PINNED 2026-08-02, CAUSE [4.46] -- AND THIS TIME BECAUSE THE
# DISTRIBUTION DID NOT MOVE. *** The Headquarters Close-Assault dash (data/unit_stats.json
# _hq_dash_comment, tests/test_hq_close_assault.py) puts 74 of the campaign's 84 HQ counters into
# [3.36]/[10.29]'s capture population, which moves every trajectory from Game-Turn 1. THREE tests
# pinned to this seed go red on it, and all three were measured against a `git archive HEAD` control
# tree before anything was concluded:
#
#     the faucet test's OWN four assertions pass on   18 of 24 seeds BEFORE
#                                                     18 of 24 seeds AFTER
#     3 pass->fail ({10, 11, 23}) against 3 fail->pass ({15, 18, 21}); mean Commonwealth truck
#     moves 107.88 -> 108.33, late moves 14.71 -> 16.46, last move Game-Turn 18.79 -> 18.92.
#
#     the Commonwealth still holds Mersa Matruh at GT12 on   8 of 100 seeds BEFORE
#                                                           17 of 100 seeds AFTER
#     13 lost->held against 4 held->lost -- the CW distribution moves UP, not down. Mean combat
#     units at GT12: Commonwealth 311.35 -> 311.24, Axis 215.76 -> 214.50. Seed 23 does NOT hold
#     the railhead on EITHER tree.
#
# THAT IS SINGLE-SEED CHAOS EXACTLY AS THIS FILE DEFINES IT, and 23 has simply stopped being a lucky
# seed the way 1941 did. Decomposed at seed 23, both trees, so the three reds are diagnosed and not
# merely dismissed: eleven of eleven Compass turn-closes still put a Commonwealth combat unit
# FORWARD of Mersa Matruh (unchanged) but none of them can fight there (11 -> 0); the lorry pool
# runs 179 -> 51 moves and stops at Game-Turn 5 instead of 24; Sidi Barrani goes from BR-2SctGds to
# the Italian Mechili garrison. One lost combat at the railhead and the spine goes idle behind it --
# the cascade this note already names.
#
# NO RE-PIN IS ATTEMPTED AND THAT IS A DELIBERATE HANDOVER, NOT AN OVERSIGHT. The paragraph above
# says a seed that HOLDS the railhead fails three of this constant's consumers "in the good
# direction", so no single seed makes every CAMPAIGN_SEED test green -- the constant is
# over-subscribed, which is a pre-existing structural fact about the fixture and not something this
# three-cell data correction created or should silently settle. Weakening the three assertions was
# the other option and is refused (rules of this port, 5): the capabilities they name are intact on
# 18 of 24 seeds, so asserting less would enshrine one seed's luck. The three are:
#     test_campaign_faucet.py::test_the_commonwealth_trucks_actually_run
#     test_campaign_claim.py::test_both_sides_take_the_cities_they_used_to_sprint_past
#     test_campaign_concentration.py::test_the_commonwealth_can_mount_a_supplied_offensive
#
# *** AND THE HANDOVER WAS TAKEN, 2026-08-03: THE THREE MOVED OFF THE CONSTANT ENTIRELY. *** They
# are restated onto CAMPAIGN_PANEL below -- seeds 1..24, run whole -- so each asserts the CAPABILITY
# IT IS NAMED FOR over a distribution instead of pinning it to one board. Nothing was re-pinned and
# nothing was weakened:
#
#   * RE-PINNING WAS CONSIDERED AND REFUSED AS SHOPPING. The candidate list this note used to end
#     with ({1, 2, 3, 4, 6, 7, 8, 12, 13, 14, 16, 17, 20, 22, 24}) is a list of seeds on which the
#     evidence comes out the way the tests want, and choosing one is choosing the evidence: the very
#     next rule change flips whichever is chosen, exactly as it flipped 1941, then 4, then 23. The
#     defect this note has been naming for three re-pins is not the seed. It is that ONE constant
#     serves consumers with contradictory requirements, and the fix for an over-subscribed fixture
#     is to stop subscribing to it.
#   * EVERY ASSERTION SURVIVED. Each claim that holds on all 24 seeds of BOTH trees is now asserted
#     PER SEED -- checked twenty-four times where it used to be checked once. Each claim that is
#     seed-luck (the ones that flip) is asserted as a COUNT over the panel against CAMPAIGN_FLOOR,
#     with both trees' measurements written beside it in the test file so the headroom is visible.
#     Not one check was dropped, and the two arms of every count are recorded, control first.
#   * EACH IS TRIPWIRED. A panel test that only fails when a capability COLLAPSES is worth nothing
#     unless that has been demonstrated, so each of the three was run against a scratch tree with
#     its own capability neutered (the relay silenced after Game-Turn 3; the take-and-hold's moves
#     suppressed; the forward concentration pointed back at the rear base) and shown to go red. The
#     neuter and the resulting count are named in each test's docstring.
#
# CAMPAIGN_SEED IS NOT RETIRED. Twenty-nine other tests across five files still ride it, and for a
# test that reads a POSITION rather than an OUTCOME -- what the railhead resolves to, where a depot
# is staged, whether a policy constructs -- one deterministic board is the right and cheap
# instrument. What is retired is using it to certify that an ARMY CAN DO SOMETHING.
# --------------------------------------------------------------------------------------------------
CAMPAIGN_SEED = 23

# --------------------------------------------------------------------------------------------------
# THE CAMPAIGN PANEL -- seeds 1..24, UNSHOPPED, and the unshoppedness is the whole point.
#
# A capability claim ("the Commonwealth lorry pool runs", "both armies take and hold cities", "the
# offensive is supplied where it is fought") is a claim about what the campaign DOES, and the note
# above is this project's own record of what happens when such a claim is pinned to one seed: it
# survives until the next faithful rule lands, then it is re-pinned to a seed on which it still
# holds -- 1941, then 4, then 23 -- and the re-pin is indistinguishable from choosing the evidence.
#
# 1..N, not a curated list, for the reason scripts/gate_c.py already gives at length: "a distribution
# taken over a curated list of 'canonical' seeds is a distribution over seeds somebody once found
# interesting". 1..24 is also a PREFIX of that driver's own 1..30 panel, so any row measured here is
# literally one of its rows, and it is the panel the [4.46] entry above already swept -- which is why
# the numbers in the three test files can be checked against it line for line.
#
# N = 24 IS A COST CHOICE AND IT IS STATED AS ONE. A panel test folds 24 campaigns; at the horizons
# the three consumers use that is 4 + 14 + 17 minutes measured (faucet to GT12, concentration to
# GT22, claim to GT30), three workers busy while the rest of the suite runs -- the whole suite
# measures 41 minutes at `-n 8` with them in it. It was NOT chosen to make a number come out: the
# panel was fixed before anything was measured, and no threshold below is derived from where the
# panel's own count happened to land.
#
# CAMPAIGN_FLOOR IS HALF THE PANEL AND IS NOT DERIVED FROM THE MEASUREMENT. Deriving a threshold from
# the number you just measured is re-pinning at panel scale -- it makes today's tree the definition
# of correct and leaves no room for the next faithful rule to move anything. So the floor comes from
# the CLAIM instead: "this is what the campaign normally does" means it must hold on more boards than
# not. Every count assertion in the three consumers is written against this constant, every one of
# them records what the control tree and this tree actually measure, and the headroom is therefore
# on the page rather than in the threshold.
# --------------------------------------------------------------------------------------------------
CAMPAIGN_PANEL = tuple(range(1, 25))
CAMPAIGN_FLOOR = len(CAMPAIGN_PANEL) // 2


def signature(res) -> str:
    """The 12-hex fingerprint of a RunResult's event log."""
    from game.engine import determinism_signature
    return hashlib.sha256(determinism_signature(res.events).encode()).hexdigest()[:12]
