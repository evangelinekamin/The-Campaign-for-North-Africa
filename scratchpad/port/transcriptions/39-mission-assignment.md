# [39.0] MISSIONS — mission assignment, allocation, and what bounds a sortie

Transcription and survey pass, 2026-08-04. **READ-ONLY on `game/`, `data/`, `tests/`.** No engine
code was changed.

## Provenance

Every string quoted below was rendered from the scan at 300 DPI (`pdftoppm -r 300`), cropped to the
column, and read character by character. PDF page numbers are the 192-page PDF's own; the book's
printed folio (the "OCR header" the Mistral corpus records) is given beside it.

| Rule | PDF page | printed folio | read from |
|---|---|---|---|
| 34.11 Range | 51 | 4 | scan, cols 2 — verified verbatim |
| 37.24 sortie ceiling | 54 | 7 | scan, col 2 — verified verbatim |
| 39.0 General Rule / Note / Procedure / 39.11–39.17 | 55 | 8 | scan, cols 2–3 — verified verbatim |
| 39.18–39.5, 40.0 General Rule, 40.1–40.24 | 56 | 9 | scan, cols 1–3 — verified verbatim |
| 40.24 (cont.)–40.34 | 57 | 10 | scan, cols 1–2 — verified verbatim |
| 41.0 Procedure, 41.21 | 58 | 11 | scan, cols 1–2 — verified verbatim |
| 39.5 AIRCRAFT MISSION SUMMARY (chart) | 101 | (chart booklet p. 6) | scan, col 2 — verified verbatim |

Both OCR corpora were used throughout:

* **`/home/eve/projects/tcfnatdw-ocr/ocr/`** (Mistral OCR 4) — `markdown/page-0051.md`,
  `page-0054.md`, `page-0055.md`, `page-0056.md`, `page-0057.md`, `page-0058.md`, `page-0059.md`,
  `page-0101.md`.
* **`docs/rules/`** — `39-missions.md`, `40-fighter-combat.md`, `41-bombing-missions.md`,
  `42-non-combat-missions.md`, `33-sequence-of-play-air-game.md`, `34-the-aircraft.md`,
  `37-flight.md`.

### Where the two corpora disagree

A case-by-case diff of rule 39 across the two corpora found **no substantive disagreement** — only
typography. Three points are worth recording because two of them are places a corpus silently
"corrected" the book:

1. **39.44 — the new corpus is RIGHT and `docs/rules/` is wrong.** The scan prints
   `may not be In-tercepted`, with a capital `I` (line-broken across `In-` / `tercepted`).
   `docs/rules/39-missions.md:84` prints lower-case `intercepted`; Mistral prints `Intercepted`.
   Verified by crop of PDF p. 56 col. 2. Immaterial to any rule, but it is a data point on corpus
   reliability that runs *against* the usual direction.
2. **39.19 — `docs/rules/` is right and the new corpus is wrong.** The scan prints
   `and vice versa` (lower-case `v`; there is a speck of scan noise above the glyph that Mistral
   appears to have read as a capital). Mistral prints `and Vice versa`. Verified by crop.
3. **The 39.5 chart — Mistral silently corrects two of the book's own typos.** The scan's chart
   heading reads `Commonweath` (no `l`) and its strafing list reads `Flak Suppresiion`. Mistral
   renders both as correct English. `docs/rules/90-charts-tables-and-play-aids.md` was not used —
   per CLAUDE.md it is unreliable for charts, and the chart was read off the scan directly.

`docs/rules/39-missions.md` reproduces the book's own errors faithfully in the load-bearing places:
39.18's missing comma (`transport recon and transfers`) and its `The later mission` for *latter* are
in the printed book.

---

# 1. RULE 39 (MISSIONS), TRANSCRIBED CASE BY CASE

All of the following is verbatim from the scan unless marked otherwise.

## [39.0] MISSIONS

### GENERAL RULE (PDF p. 55, col. 2)

> No plane may fly without being given a specific mission. A mission is a one or two word
> description of the undertaking, the reason the plane is flying and what it is supposed to do.
> Generally, no plane may perform more than one mission at any one time. There are a large variety
> of missions, and they are all dependent on the class of plane and the target. The various missions
> and their descriptions are covered in a series of Cases following 39.1, which is general in
> nature. Missions may be aborted, or discontinued before completion.

### Note (PDF p. 55, col. 3)

> **Note:** Often players may not know precisely what is in a hex, but will have to assign missions
> "blindly," and only find out what target are present when the planes arrive.

(`target are present` is the book's own grammar.)

### PROCEDURE (PDF p. 55, col. 3)

> Most missions involve different planes going after different types of targets. However, virtually
> all missions (except transfer) follow the same pattern. The sequence below should be followed for
> all missions, with exceptions taken as specifically noted in a mission description.
>
> a. All Planes are placed in their mission target hex.
>
> b. Resolve all interception and scramble.
>
> c. Any air-to-air combat between fighters is resolved.
>
> d. Fighters on CAP that survive air-to-air may, under certain circumstances, attack Enemy
> non-fighter planes.
>
> e. Any planes remaining in hex after air-to-air undergo flak fire if there are Enemy AA/Flak units
> in that hex.
>
> f. Each mission is run in any order the Player wishes, the opposing Player noting and taking any
> damage inflicted.
>
> g. All surviving planes return to base.

## CASES

### [39.1] MISSIONS IN GENERAL (PDF p. 55 col. 3 → p. 56 col. 1)

> **[39.11]** Unless a plane is attempting emergency flight (see Case 37.3), no plane may fly unless
> it has been assigned a specific mission. Nor may any plane be flown if an Enemy land combat unit
> is adjacent (see 37.3).

> **[39.12]** Each Player may use any shorthand he wishes to note which mission is which. Each
> Squadron Composition Sheet has a section for listing the mission that a specific plane is
> undertaking in a given Operations Stage or Strategic Air Phase. The Player simply writes the
> mission next to the plane, and that plane will attempt that mission.

> **[39.13]** There are two major areas of missions: strategic air missions and Tactical Land
> Support. The former refers to any Commonwealth Missions flown against Axis Naval Convoys as well
> as any Axis Missions flown *against* Malta. Both of these Missions are flown *only* in the
> Strategic Air Phase of the Sequence of Play; moreover, they are flown only once per Game-Turn.

> **[39.14]** Tactical land support missions are missions flown during an Operations Stage of the
> Game-Turn, affecting the movements and usage of land (or naval) units. Tactical land support
> missions are numerous in type and they are flown a possible three times a Game-Turn (or once an
> Operations Stage).

> **[39.15]** There is no limit to the number of planes that may be assigned to a given mission to a
> given hex. There *is* a restriction to the type and class of plane that can undertake a given
> mission, as no plane may perform a mission for which it does not have the Capability. Plane
> Capabilities are listed on the Aircraft Characteristics Chart (34.6).

> **[39.16]** Planes from different squadrons may be assigned to the same mission (or even target),
> and planes from the same squadron may be assigned to different missions. However planes from the
> same squadron may not be divided between strategic and land support missions.

> **[39.17]** There is no limit to the number of the type of missions that may occur in (or rather
> over) a given hex (limited, of course, by what is in that hex worth going after). Players should
> keep the planes assigned to each specific mission separate, so as to avoid confusion.

> **[39.18]** There are basically five "types" of missions: fighter, bomber, transport recon and
> transfers. The later mission is the only mission that may be undertaken by *any* plane (see Case
> 42.1)

> **[39.19]** Generally, a plane may fly only one mission per Operations Stage or Strategic Phase
> (with the exception of certain fighters and dive bombers; Case 39.2). A plane flying a mission in
> an Operations Stage may not fly in the Strategic Phase of that Game-Turn and vice versa.

### [39.2] COMBINED MISSIONS (PDF p. 56, col. 1)

> Planes can generally fly only one mission per flight. However, certain fighter aircraft had the
> ability to carry small bombloads, dropping them as they strafed a target. The Stukas, as dive
> bombers, also had this capability, although their armament placement prohibited them from
> performing in a fighter capacity. Thus, any plane with a capability notation of D("dual") may
> strafe and bomb the same target as a combined mission.

### [39.3] VOLUNTARILY ABORTED MISSIONS (PDF p. 56, col. 1)

> **[39.31]** An aborted mission is one that is cancelled *before* any action is taken to complete
> that mission. No mission may be voluntarily aborted once some action, be it bombing, strafing, or
> even air-to-air combat, has taken place.

> **[39.32]** To voluntarily abort a mission a Player simply states that he wishes to abort; he then
> sends his planes back to base — if they qualify (see Cases 39.36 and 39.37).

> **[39.33]** Aborted missions consume fuel, and bombers must expend their bombload, even though
> they do not use it.

> **[39.34]** A Player is not required to abort *all* his planes on a given mission. He may choose
> to continue with some and send some back. The choice, when available, is up to him, within the
> restrictions below.

> **[39.35]** Any fighter (any plane with a pilot, including fighter-bombers) may voluntarily abort
> if its *Maneuver Rating* is no lower than 10 Points the highest maneuver-rated Enemy Fighter on
> CAP in the Target hex. To determine this, subtract the "aborting" fighter's Maneuver Rating from
> that of the Enemy CAP fighter. If the result is −10 or better (−8, −2, +3, etc.) the plane may
> abort. Of course, if there is no Enemy CAP, the fighters may always abort (exception: see Case
> 40.26).

> **[39.36]** Non-fighters flying with a sufficient fighter Screen (Friendly fighters flying CAP for
> that hex; see Case 39.37) may abort if they wish. If there is not sufficient fighter Screen, they
> *may not* abort, unless the planes' Maneuver Rating is higher than the best Enemy fighter (a
> highly unlikely occurrence).

> **[39.37]** A sufficient fighter screen is defined as a number of Friendly fighters (simply
> counting numbers of planes, not ratings) equivalent to at least 25% of the number of Enemy
> Fighters flying CAP in that hex. Thus a bomber raid with 12 fighters as escort encountering 40
> Enemy fighters on CAP could be aborted; if there were 50 Enemy planes flying CAP, the bomber
> mission could not be aborted. Fighters acting as such a screen may not abort if they act as a
> screen. Fighters cannot screen fighters.

> **[39.38]** Aircraft may also abort *involuntarily;* e.g., as a result of AA/flak fire (see Case
> 46.3 and 45.14).

### [39.4] NIGHT MISSION (PDF p. 56, col. 2)

> **[39.41]** Night Missions are essentially a Phase within the Land Support Air Phase. All Night
> Scramble, air-to-air combat, anti-aircraft fire and land support bombing are conducted separately
> from other Land Support Missions.

> **[39.42]** Only certain missions may be flown at night and only planes with night missions
> capability may participate in any night missions actions (exceptions see Case 39.43).

> **[39.43]** Planes, with the exception of planes assigned Offensive CAP or Scramble missions, may
> only perform a mission at night if specifically assigned a night mission. In all other situations
> a plane, even if it possesses night mission capability, is considered to be performing a regular
> Land Support Mission.

> **[39.44]** Planes flying at night benefit from the decrease in the ability of enemy aircraft to
> find them (e.g., planes on night missions may not be In­tercepted), may not engage enemy aircraft
> in air-to-air combat, and benefit from a decrease in the effectiveness of anti-aircraft fire.
> Conversely, non-fighters may not benefit from Formation Flying while performing a night mission.

### [39.5] AIR MISSION SUMMARY (see Charts and Tables)

The section ends here. 39.5 is a pointer; the chart itself is PDF p. 101 and is transcribed in
section 4 below. **There is no 39.6 or beyond — [40.0] FIGHTER COMBAT begins immediately.**

---

# 2. THE ALLOCATION RULE

**The book supplies one, it is unambiguous, and it is printed in three places.**

### The unit of assignment is the individual PLANE.

Not the SGSU, not the squadron, not an Air Point. Every case in rule 39 that says who may be
assigned what says *plane*:

* 39.11 — "no **plane** may fly unless it has been assigned a specific mission"
* 39.12 — "listing the mission that a specific **plane** is undertaking … The Player simply writes
  the mission next to the **plane**"
* 39.15 — "There is no limit to the number of **planes** that may be assigned to a given mission"
* 39.16 — "**planes** from the same squadron may be assigned to different missions"

The squadron is explicitly *not* the unit of assignment: 39.16 says outright that one squadron's
planes may be split across different missions. The one thing 39.16 forbids is splitting a squadron
between the *strategic* and *land support* channels.

### The exclusivity rule is [39.19], and it is per plane per Operations Stage.

> **[39.19]** "Generally, a plane may fly only one mission per Operations Stage or Strategic Phase
> (with the exception of certain fighters and dive bombers; Case 39.2). A plane flying a mission in
> an Operations Stage may not fly in the Strategic Phase of that Game-Turn and vice versa."
> — PDF p. 56, col. 1, verified verbatim off the scan

It is restated for fighters in **[40.0] GENERAL RULE** (PDF p. 56, col. 2, verified verbatim):

> "Fighters may be assigned to only one mission in an Operations Stage (three in one Game-Turn) or
> Strategic Air Stage (one in one entire Game-Turn; see Case 39.2)."

and again in **[40.24]** (PDF p. 57, col. 1, verified verbatim):

> "Remember, a plane flying CAP may not fly any other mission in that Stage."

The single exception is **[39.2] COMBINED MISSIONS** — a plane with capability code `D` ("dual")
may strafe *and* bomb the *same target* on one flight. The 39.5 chart's own footnote repeats it:
"Note that certain planes may be assigned two Land Support Missions in the same OpStage (See
Combined Missions, Case 39.2 …)". This is two *missions*, one *flight*, one *target* — not two
sorties.

### Three further ceilings bound total sorties, all printed.

1. **[37.24] — the field and the SGSU** (PDF p. 54, col. 2, verified verbatim):

   > "No planes may fly in excess of the air facility's capability level. Moreover, no planes may
   > fly in excess of an SGSU's ready capacity (see Case 33.23). Thus, if there are five SGSU's on
   > an airfield, but the capacity level of that airfield has been reduced to two, only two of those
   > SGSU's may refit and ready their planes (thus enabling them to fly). The other three squadrons
   > are forced to remain inactive because of the reduced field capacity. Likewise, an Italian
   > squadron (for example) could send no more than nine planes on a mission, regardless of how many
   > planes it has ready (as reserves)."

   (The `Case 33.23` reference is almost certainly a misprint for 35.23, the Squadron Capacity
   Chart — 33.23 is a Sequence-of-Play segment. Flagged, not corrected.)

2. **[38.31] — refit is consumed per sortie.** "As soon as a plane flies any mission other than
   transfer, it must be refitted again. A plane that is not refitted may fly no mission other than
   transfer, even if it is refueled." (PDF p. 55, col. 1.) This is the engine's existing ledger.

3. **[37.15]/[37.16] — fuel is consumed per sortie.** "No plane may fly unless it has been fueled…"
   / "If a plane that has been fueled flies any distance it uses all its Fuel and must be refueled
   to fly again."

**So the answer to the question the owner asked — "what stops a player assigning the same aeroplanes
to two missions?" — is: 39.19, and nothing else is needed.** A plane's mission column holds one
entry per Operations Stage. It is a *written per-plane commitment*, not a per-mission draw on a
pool. The engine's `_air_points` returning the whole pool for every mission is not a gap in the
book; it is a consequence of the engine having no per-plane ledger to decrement.

### Two smaller allocation rules that also bind

* **[40.27]** (PDF p. 57, col. 1, verified verbatim): "Fighters on offensive CAP may intercept only
  one mission per Operations Stage." — a CAP may make one interception per stage, not one per enemy
  sortie that crosses it.
* **[41.12]**: "Bombers may bomb only one target per mission, and that target must be selected prior
  to actual flight. (Sorry, you can't drop your excess bombs on Tobruk on the way back.)"

---

# 3. HOW MANY MISSIONS, AND WHEN ARE THEY DECLARED

**There is no cap on the number of missions.** 39.15 ("no limit to the number of planes that may be
assigned to a given mission to a given hex") and 39.17 ("no limit to the number of the type of
missions that may occur in … a given hex") both say so explicitly. The bound is entirely the finite
supply of planes that are refuelled, refitted, within a field's capacity level, and not already
committed this stage.

**Declaration is a real, two-step, written, in-advance commitment.**

**Step 1 — the Strategic Air Planning Stage, once per Game-Turn**, splits the force between the two
channels. [41.0] PROCEDURE (PDF p. 58, col. 1, verified verbatim off the scan):

> "During the Strategic Air Planning Stage of each Game-Turn, the Players must assign any bombers
> that they wish to use in that Game-Turn either to land support missions, (not specifying what
> missions each plane or squadron will perform, but just assigning them to general land support
> missions for that Game-Turn), or to strategic convoy reconnaissance and/or bombing missions
> (commonwealth player only). **All such assignments should be in writing.** Any Malta bombing
> missions are resolved immediately, in the Strategic Air Planning Stage, and any bombers assigned
> to such a mission may not be reassigned or used again until the next Game-Turn. Any convoy
> missions are resolved during the appropriate Segments of the Convoy Resolution Phase of the Naval
> Convoy Stage of each Game-Turn; any bombers assigned a convoy mission may not be reassigned or
> used until the following Game-Turn. During *each* Land Support Air Phase (there are three in each
> Game-Turn, one in each Operations Stage), both Players may assign any eligible bombers assigned to
> "land support missions" to specific missions and after air-to-air combat and flak fire are
> resolved, the missions themselves are resolved."

This matches [33.0] II.A "Designation Phase: The Players assign their airplanes to fly Land Support
or Strategic missions."

**Step 2 — the Mission Assignment Segment of the Land Support Air Phase, three times per
Game-Turn** (once per Operations Stage), names the specific mission and the specific hex. [41.21]
(PDF p. 58, col. 2, verified verbatim):

> "Land support missions are concerned with bombing land installations, ports, personnel and
> equipment in furtherance of operations on land. Bombers assigned to land support missions for a
> Game-Turn are assigned a specific mission in a specific hex during the Mission Assignment Segment
> of a Land Support Air Phase. Thus, to assign a squadron of Wellingtons to bomb the port facilities
> at Tobruk, the Commonwealth Player would write "B-PF/Tobruk" (or any other reasonable
> representation of that intent)."

**Where it sits in the Sequence of Play** ([33.0] IV.F, `docs/rules/33-sequence-of-play-air-game.md`
lines 90–107). The Land Support Air Phase is a **single phase per Operations Stage, run for both
sides together**, sitting between the Commonwealth Fleet Phase (IV.E) and the Reserve Designation
Phase (IV.G) — i.e. **before** the Movement and Combat Phase (IV.H), not inside it:

```
IV.F  Land Support Air Phase
      1. Mission Assignment Segment      <- both Players write missions
      2. Mission Deployment Segment      <- counters placed in target hexes; scramble decided at its end (40.32)
      3. Air-to-Air Combat Resolution Segment
      4. Flak Resolution Segment
      5. Mission Completion Segment
      6. Return to Base Segment
      7. Tactical Maintenance Segment
IV.G  Reserve Designation Phase
IV.H  Movement and Combat Phase
```

Crucially, **assignment is blind and simultaneous**: the 39.0 Note says players "will have to assign
missions 'blindly,' and only find out what target are present when the planes arrive", and 40.33
says of Scramble that "all decisions are made in secret and revealed at the same time". This is a
plotting step in the same family as the barrage plot ([33.0] IV.H.3.b, "Players secretly plot and
then execute any barrages").

---

# 4. WHAT MISSION KINDS THE BOOK LISTS — [39.5] AIRCRAFT MISSION SUMMARY

Transcribed off the scan, PDF p. 101, col. 2, verbatim including the book's own two typos
(`Commonweath`, `Flak Suppresiion`), which both OCR corpora silently correct.

> **[39.5] AIRCRAFT MISSION SUMMARY**
>
> **STRATEGIC MISSIONS:**
>
> *Commonweath*
> Reconnaissance of Axis Naval Convoys (Case 42.5)
> Bombing Axis Naval Convoys (Case 41.6)
> Defensive CAP over Axis Naval Convoys (Case 41.63)
> Flak Suppression of Axis Naval Convoys (Case 41.63)
> CAP over Malta
>
> *Axis*
> Bombing Maltese air facilities (Case 44.2)
> CAP over Malta
> Flak suppression of Maltese air facilities (Case 44.2)
> Offensive CAP over Axis Naval Convoys (Case 41.63)
>
> **LAND SUPPORT MISSIONS:**
>
> *Fighter*
> Scramble\* (Case 40.3)
> Combat Air Patrol\* (CAP), Offensive/Defensive (Case 40.2)
> Strafing (Cases 40.5 and 40.6)
> &nbsp;&nbsp;&nbsp;&nbsp;1st Line (attached) Trucks
> &nbsp;&nbsp;&nbsp;&nbsp;Flak Suppresiion
> &nbsp;&nbsp;&nbsp;&nbsp;Grounded Aircraft
> &nbsp;&nbsp;&nbsp;&nbsp;Infantry-type units
> &nbsp;&nbsp;&nbsp;&nbsp;Ports†
> &nbsp;&nbsp;&nbsp;&nbsp;Tanks‡
> &nbsp;&nbsp;&nbsp;&nbsp;Trucks in Convoy (2nd-3rd Line)
> &nbsp;&nbsp;&nbsp;&nbsp;Water Pipeline
> *Bombing (Section 41.0)*
> Air facilities
> Fortifications/Major Cities\*
> Flak Destruction
> Mining Harbors
> Personnel
> Ports\*
> Railroad/Road\*
> Commonwealth Ships
> Supply Dumps
> *Non-Combat*
> Airdrop (Case 42.4)
> Reconnaissance of land units (Case 42.2)
> Transfer (Case 42.1)
> Transport (Case 42.3)
>
> \*May be performed at Night. †Performed on the Air Bombardment CRT. ‡Only Commonwealth Player
> owned (i.e., non-captured) Hurricane IID's. Note that certain planes may be assigned two Land
> Support Missions in the same OpStage (See Combined Missions, Case 39.2 and the Aircraft
> Characteristics Charts 4.6)

The indentation in the *Fighter* block is the chart's: the eight indented lines are **strafing
targets**, not eight separate mission types. That matches [40.54]'s own list of eight strafeable
target types, which the chart reproduces in alphabetical order with "Flak Suppresiion" wrongly folded
in (40.7 makes Fighter Flak Suppression its own mission — "Flak suppression is a mission", 40.72 —
not a strafing target). Flagged as a chart defect, not corrected.

**The chart omits one mission the rules print.** [41.32] "Bombing Truck Convoys (B-TC)" is a real
land-support *bombing* mission with its own case, and it is absent from the chart's Bombing list
(the chart lists "Trucks in Convoy" only under *Strafing*). Recorded as an omission in the chart,
not as evidence the mission does not exist.

## Mission kinds the ENGINE does not implement

The engine implements seven `AirMission.kind` values (`strike`, `fort`, `port`, `airfield`, `dump`,
`trucks`, `recon` — dispatched at `game/engine.py:3002-3017`). Mapping the chart onto them:

| Book mission | case | engine |
|---|---|---|
| Bombing Personnel (B-CU) | 41.31 | `strike` (`engine.py:3037`) |
| Bombing Fortifications/Major Cities (B-F/C) | 41.37 | `fort` (`engine.py:3068`) |
| Bombing Ports (B-P) | 41.39B | `port` (`engine.py:3122`) |
| Bombing Air Facilities (B-AF) | 41.36 | `airfield` (`engine.py:3164`) |
| Bombing Supply Dumps (B-SD) | 41.35 | `dump` (`engine.py:3272`) |
| Bombing Truck Convoys (B-TC) | 41.32 | `trucks` (`engine.py:3336`) |
| Reconnaissance of land units | 42.2 | `recon` (`engine.py:3389`) |
| **Combat Air Patrol, Offensive/Defensive** | **40.2** | **MISSING as an order** — see §5 |
| **Scramble** | **40.3** | **MISSING** |
| **Strafing** (8 target types) | **40.5 / 40.6** | **MISSING** |
| **Fighter Flak Suppression** | **40.7** | **MISSING** |
| **Flak Destruction (B-FS)** | **41.33** | **MISSING** |
| **Mining Harbors (B-MH)** | **41.39A** | **MISSING** |
| **Bombing Commonwealth Ships (B-CF)** | **41.34** | **MISSING** (naval strike; `_naval_bombardment` is the CW *ships'* gunfire, not air-vs-ship) |
| **Bombing Railroad/Road (B-R / B-RR)** | **41.38** | **MISSING** |
| **Torpedo attack** | **41.7** | **MISSING** (`torpedo` IS transcribed in `data/logistics_rates.json`, read by nothing at mission time) |
| **Night missions** (whole 39.4 sub-phase) | **39.4 / 41.4 / 40.9** | **MISSING** |
| **Transfer** | **42.1** | present, but not as an `AirMission` — it is its own beat, `engine._air_transfer` (`engine.py:2510`) |
| **Transport** (personnel/supply by air) | **42.3** | **MISSING** |
| **Airdrop (paratroops)** | **42.4** | **MISSING** |
| **Naval Convoy Reconnaissance** | **42.5** | **MISSING** as an order (`engine._interdict` is the abstracted CW convoy strike) |
| Bombing Axis Naval Convoys | 41.6 | present as `InterdictionOrder`, a separate scheduled channel |
| Bombing Maltese air facilities | 44.2 | present as `engine._malta_raid` (`engine.py` Strategic Phase) |

The biggest single omission is **air transport and airdrop (42.3 / 42.4)** — an entire non-combat
logistics channel — followed by **strafing (40.5/40.6)**, which is the fighter arm's only offensive
land-support role and the reason the fighter rows are currently inert.

---

# 5. RULE 40: DOES THE PLAYER ORDER CAP, AND DOES DECLARING EXPOSE A MISSION TO INTERCEPTION?

**Both yes, and the book settles it in one sentence.**

### CAP is a mission the Player ORDERS and may decline.

> **[40.21]** "Any plane that has F (fighter) capability (see the individual capabilities on the
> Aircraft Characteristics Charts) may fly Combat Air Patrol. Usually, fighters fly CAP. To denote
> that a fighter is flying a CAP mission, **write CAP and the target hex in his mission column on
> the Squadron Composition Sheet.** He should also denote whether this is offensive CAP (CAP-O) or
> defensive CAP (CAP-D)."
> — PDF p. 56, col. 3

That is the same mission column 39.12 describes, filled in the same Mission Assignment Segment as a
bombing mission. CAP costs a plane its whole Operations Stage (40.24: "a plane flying CAP may not
fly any other mission in that Stage"), it burns fuel and readiness like any sortie (40.33 says even
a *failed* Scramble means "the planes have flown and they still must refuel and refit"), and the
book names the reason a Player would rather not fly it:

> **[40.3]** "There may be a time when a Player wishes to either conserve fuel or, perhaps, retain
> some flexibility with his fighter force. *Scramble* gives him the ability to do that. Planes
> assigned to scramble missions are planes that stay on the ground until Enemy aircraft come within
> range."
> — PDF p. 57, col. 1

**So the engine's always-on abstraction is NOT faithful, and the engine already knows it.** The
argument written into `game/engine.py:2679-2698` (`_air_superiority`) reaches exactly this
conclusion from exactly these citations, and `game/scenario.py:1506-1509` records the fighter rows
as "SEEDED AND INERT" for the same reason. This transcription confirms the reading rather than
overturning it: **CAP is an ordered mission**, offensive and defensive are two *different* orders
with different rules, and neither is automatic.

### Declaring a mission exposes it to interception on the PATH OF FLIGHT, not only over the target.

> **[40.27]** "Fighters flying Offensive CAP *may intercept* Enemy planes whose paths of flight
> enter the hex they are in or their air ZOC. After all plane counters have been placed to indicate
> their mission target hex, but before revealing the numbers of planes involved, a Player with
> fighters on offensive CAP may ask to see a path of flight. If that path coincides with his
> fighters, the Player with the offensive CAP *may* choose to intercept the Enemy mission right
> there. If so, air-to-air combat will take place, and any surviving planes may continue their
> mission. Fighters on offensive CAP may intercept only one mission per Operations Stage."
> — PDF p. 57, col. 1

This is why 37.12 makes the player *note the path of flight* and 41.21 says "that is why it is
important for a Player to be aware of the path of flight". The interception geometry is a
three-hex-radius object (40.23: three or more fighters on offensive CAP hold an air ZOC over their
hex plus all six adjacent), and it applies to the route, not the destination.

### The player chooses an escort, and escort is itself a CAP order.

> **[40.22]** "Offensive CAP concerns flying to a hex with the intention to shoot down Enemy planes.
> Defensive CAP is undertaken by fighters wishing to protect Friendly bombers or transport (flying
> as escort/screen for them) or to protect an installation or facility. The distinctions can
> sometimes become a bit blurred."

The 40.25 worked example is exactly the owner's question: the Axis Player sends two squadrons of
Ju 88s to bomb Tobruk *and separately orders* two squadrons of Bf 109Es and one of CR.42s to the
same hex as escort/screen; the Commonwealth has two squadrons of Hurricanes on **defensive** CAP
over Tobruk. The escort is a distinct order, at a distinct cost (each of those fighters has spent
its Operations Stage), and 39.36/39.37 make it decide whether the bombers may abort at all.

### And the offensive/defensive distinction is a real, asymmetric commitment.

> **[40.26]** "… If fighters are flying offensive CAP, they would *have to* attack any Enemy planes
> entering their hex or any hex in their Zone of Control to perform a mission in that hex; they
> could not decide to not have combat. Exception: only Enemy planes in one such hex must be
> attacked. Defensive CAP planes may decline combat and abort; offensive CAP planes may not."
> — PDF p. 57, col. 1

---

# 6. RANGE

**The book gates every mission by range from the base, and the numbers are already in `data/`.**

> **[34.11] Range** — "A Plane's range is the maximum distance, in hexes, that it may be flown *to*
> a hex to perform a mission. It is also the maximum distance from which it may return to a base
> from a mission. There is one exception to this: planes flying a transfer mission (simply moving
> from one air facility to the next) may be flown a distance equal to twice that of their listed
> range. **Example:** An Me109E based on a Landing Strip in hex C3101 may fly to hex C3133 for a
> strafing mission — a distance of 32 hexes, within its Range of 41 — and then fly back to its
> squadron base at C3101. The Me109E could not be flown from the mission hex to an Axis airfield in
> A0915 for two reasons: it is too far away and, generally, all planes must return to their Base of
> origin. Planes may not *save* hexes not flown (within a plane's Range) going out and use them
> coming back …"
> — PDF p. 51, col. 2, verified verbatim

Reinforced by [37.11] ("All planes have a range (see Case 34.11). This determines how far a plane
may fly in any one direction"), [37.12] (count the distance from base/air facility to target hex),
[37.21] ("Planes may never exceed their range in any one direction"), and [37.4], the **Air Distance
Table**, "provided as a handy reference to determining distances in hexes between major points".

## The data is transcribed. It is simply not consulted at mission time.

* **Per-aircraft range is in `data/logistics_rates.json`** under
  `aircraft_characteristics_4_44.aircraft.<type>.range`, for all 28 transcribed types — e.g.
  `Bf. 109E` 41, `Ju. 87B` 36, `He. 111` 112, `S.M. 79 Sparviero` 120, `Sunderland` 238,
  `Ba 65` 55. Read by `game/roster.py:216 range_per_plane`.
* **The [37.4] Air Distance Chart is in `data/logistics_rates.json`** under `air_distance_37_4`,
  both printed sections, with `P` ("not possible") transcribed as null. Read by
  `game/logistics_data.py:443`.
* **`data/logistics_rates.json` even carries [34.12]'s two-row aircraft** (`Bombay Mk. I`,
  `Sunderland`) under `readying_options`, with the owner's choice recorded.

**But the only consumer of either is the [42.1] transfer-to-the-Mediterranean test.**
`game/basing.py:260 transfer_range` and `game/basing.py:267 transfer_distance` are the whole of it
(`game/basing.py:364`, called from `game/engine.py:2663`). Grep confirms no other caller.

`AirMission` (`game/state.py:475-493`) carries `side`, `kind`, `target`, `turn` — **no base, no
departure facility, no range field** — and `_air_support` (`game/engine.py:2960`) performs no range
test of any kind. A mission may be flown at any hex on the map from nowhere in particular.

This is a *plumbing* gap, not a transcription gap. The chart is on disk; the mission object has no
origin to measure from, because an `AirWing` is a hexless national `(side, arena, role)` pool of Air
Points rather than a squadron based at a field — the same root cause `engine._refit_stores_dump`
(`game/engine.py:2779-2797`) already flags for the Stores bill and `air.refuel` for the fuel bill.

---

# 7. WHAT THE ENGINE DOES INSTEAD

Each claim carries a `file:line`.

### There is no Policy hook at all.

* `game/policy.py` defines `movement`, `combat`, `supply_orders`, `motorization`, `organization`,
  `retreat_before_assault`, `truck_orders`, `rail_orders`, `coastal_shipping_orders`, `demolition`,
  `construction`, `continual_movement`, `reserve_designation`, `reserve_release`, `react_to`,
  `malta_raid` (`policy.py:263`), `air_transfer` (`policy.py:274`), `malta_africa_planes`
  (`policy.py:291`), `convoy_plan` (`policy.py:307`). **There is no `air_missions()`.** The three
  air hooks that exist are all *strategic*: how many planes to send to Malta, how many to ferry to
  Sicily. Nothing routes a land-support mission.
* `game/engine.py:2975` reads the schedule straight off state:
  `due = [m for m in r.state.air_missions if m.side == side and m.turn == r.state.turn]` — no policy
  is consulted.
* The Air Marshal seat in `game/staff_policy.py:647-666` (`_air_plan`) **narrates the pre-baked
  schedule back to itself**: it reads `state.air_missions`, builds `{"order": "air_mission", ...}`
  proposals, and stages them as a `STAFF_PROPOSAL` event. Nothing consumes those proposals. It is a
  read-only projection wearing an order's clothes.

### The schedule is a fixed constant, one mission per side per Game-Turn, all war.

`game/scenario.py:1518-1545` (`_campaign_air_missions`) returns exactly:

```python
tuple(AirMission(side, "port", "PORT-Tobruk", t)
      for t in range(1, max_turns + 1)
      for side in (Side.AXIS, Side.ALLIED))
```

222 missions for a 111-turn war, all of them `port` against `PORT-Tobruk`, both sides every turn,
with `_air_port` refusing whichever side holds the hex. `game/scenario.py:740` does the same for the
Tobruk siege scenario. **Six of the engine's seven implemented mission kinds are never scheduled by
the campaign at all** — `strike`, `fort`, `airfield`, `dump`, `trucks` and `recon` are dead code in
`campaign(seed)`.

### `_air_points` returns the whole pool for every mission.

`game/engine.py:2730-2761`. Three gates apply — rule 43 basing + 39.19's Malta-or-desert clause
(`game/basing.py:available_points`), the superiority loser-scale, and the 38.31 refit ledger — and
then it returns that number. **It is not decremented as missions fly.** The 38.31 un-refit at
`game/engine.py:2763` (`_air_unfit`) *does* bill readiness after the fact, but it fires inside the
fuel callback *after* the mission has already been sized, so two missions in the same Operations
Stage each read the pre-mission ready count. Today only the one-mission-per-turn schedule hides
this. **This is the blocker the owner identified, and the transcription confirms it is real.**

### Air superiority is an always-on abstraction, not an ordered CAP.

`game/engine.py:2669` (`_air_superiority`) fires unconditionally once per arena per Operations
Stage, commits both sides' entire fighter pool, rolls one die each, and scales the loser's
strike/recon by `AIR_SUPERIORITY_LOSER_SCALE = 0.5` (`game/engine.py:50`). The docstring
(`engine.py:2679-2698`) already names this as unfaithful against 40.21 and 40.3 and explains why it
draws no fuel — a measurement showing that billing it took 84 of 84 Axis air Fuel Points on two
seeds of three. `game/engine.py:2721` (`_REFITTABLE_ROLES`) deliberately excludes fighters for the
same reason. **The transcription supports every part of that argument.** The loser-scale itself has
no chart behind it and says so at `engine.py:44-49`.

### Timing: the engine runs the Land Support Air Phase inside each side's Combat Segment.

`game/engine.py:6369` calls `_air_support(r, side, pinned)` at the head of `_combat`, i.e. inside
the Movement and Combat Phase (33 IV.H), separately for Player A and Player B. The book puts it in
Phase IV.F — **one phase, both sides, before Reserve Designation (IV.G) and before Movement and
Combat (IV.H)**. The consequence is that the engine cannot express 40.26/40.27's simultaneity: there
is no beat at which both sides' missions are on the map at once, so interception on the path of
flight has nowhere to happen. Flagged; not a defect that bites while there is one mission a turn,
but it is a structural precondition for CAP.

### Nothing validates a mission kind.

`_air_support` (`game/engine.py:3002-3017`) is a bare `if/elif` chain on `m.kind` with no `else`. An
unrecognised kind is silently dropped — no event, no refusal, no invariant. `game/apply.py` and
`game/invariants.py` contain no `AirMission` kind whitelist. If a Policy hook is opened, this is
where an order-rejection boundary has to be built.

### What the engine gets RIGHT, and should keep

* **39.11's blind assignment is honoured deliberately** — `game/engine.py:2990-2993` bills fuel for
  a mission that arrives to find an empty hex, quoting 39.0's "blindly" clause. Correct.
* **39.19's Malta-or-desert clause is built** — `game/basing.py` is a full and careful port of it,
  including the "and vice versa" half.
* **38.31's refit ledger is built** — `_air_maintenance` (`engine.py:2799`), `_air_unfit`
  (`engine.py:2763`), the [38.37] table and [38.35] modifiers in data.
* **37.24's field-capacity ceiling is partly built** — `basing.facility_planes` and
  `air.able_sgsus` / `air.squadron_capacity` implement the SGSU and Capacity-Level halves for
  refit; they are not applied as a *sortie* ceiling at mission time.

---

# 8. OWNER RULINGS

Things genuinely underdetermined by the book, or determined but requiring a choice about how to
model a hexless Air Point.

1. **What is one "plane" when an AirWing is Air Points?** 39.19 binds per plane; the engine's unit
   is an Air Point, and `game/air.py` already converts between them (`flying_planes`,
   `ready_points`). A `Policy.air_missions()` hook must decide whether the ledger it decrements is
   in planes (faithful, needs the conversion at every mission) or in Air Points (simpler, one step
   removed from the rule). **Recommendation: planes** — `_air_unfit` already converts, so the
   machinery exists.

2. **Does an engine "mission" mean one plane's sortie or one target's raid?** The book's mission is
   a *per-plane* assignment (39.12) that may be shared by unlimited planes against one hex (39.15).
   `AirMission` today is a per-target tasking with no plane count. Opening the hook needs a size
   field, and the owner must choose whether a staff orders "N planes at hex X" (faithful, and what
   39.15 permits) or keeps the current "whatever the pool gives".

3. **37.24's second sentence as a per-mission ceiling.** "Likewise, an Italian squadron (for
   example) could send no more than nine planes on a mission" is a hard per-squadron sortie cap that
   nothing reads. With a hexless national pool there is no squadron to cap. Underdetermined until a
   [34.72] Squadron Composition Sheet exists.

4. **The `Case 33.23` reference in 37.24 is a misprint.** 33.23 is a Sequence-of-Play segment; the
   Squadron Capacity Chart is 35.23 and is what the sentence needs. Not corrected here. If the
   engine ever reads it, this wants a named errata key of the [54.17] kind.

5. **Whether the always-on superiority contest survives the hook.** If CAP becomes an ordered
   mission, `_air_superiority` should be deleted rather than kept alongside it — two air-combat
   models in force at once is the bug class CLAUDE.md rule 3 describes. But deleting it removes the
   only thing that currently makes fighters matter, and `AIR_SUPERIORITY_LOSER_SCALE` has no chart
   behind it to preserve. Owner's call on sequencing.

6. **Range: which base does a hexless AirWing fly from?** 34.11 measures from the squadron's field.
   The engine has `air_facilities` on the map and `basing.facility_planes` per field, so a
   *nearest-held-facility* reading is available and is the conservative one. It is a choice, not a
   transcription. Flag it if taken.

7. **[39.2] combined missions.** The `D` capability is transcribed per aircraft in
   `data/logistics_rates.json` (`mission_capability.D`) and read by nothing. Whether a `dual` order
   is worth building before strafing exists is an owner call — 39.2 is a *strafe-and-bomb* rule and
   strafing is not implemented, so it is currently unreachable.

8. **The 39.5 chart's two defects.** "Flak Suppresiion" is listed as a *strafing target* where 40.7
   makes it a mission in its own right; and "Bombing Truck Convoys" ([41.32]) is missing from the
   chart's Bombing list although it has its own case. Both are recorded as printed. If the chart is
   ever transcribed to `data/`, both need named errata keys rather than silent repair.

---

# 9. THE ANSWER TO "CAN THE HOOK BE OPENED TODAY?"

**Yes — the book supplies the allocation rule, and it is buildable with what is already on disk.**

The minimum faithful hook is:

1. **A per-Operations-Stage commitment ledger keyed on planes** — 39.19. Decrement it as missions
   are ordered, refuse the mission that overdraws it. This is the one thing `_air_points` is missing,
   and `_air_unfit` (`engine.py:2763`) already does the Air-Point→plane conversion needed to write
   it.
2. **`Policy.air_missions(state, side) -> list[AirMission]`**, consulted where
   `game/engine.py:2975` currently reads the static schedule, with an order-rejection boundary at
   the `if/elif` chain (`engine.py:3002`) that today silently drops unknown kinds.
3. **A mission-kind whitelist** in `apply`/`invariants`, which does not exist.

Two things are **not** blockers and should not be treated as such:

* **Range is not a blocker.** The chart is transcribed
  (`data/logistics_rates.json:aircraft_characteristics_4_44.*.range` and `air_distance_37_4`); only
  the "which field did this sortie leave from" plumbing is missing, and a nearest-held-facility
  reading is available today (owner ruling 6).
* **The declaration step is not a blocker.** [41.0]'s two-step written commitment maps cleanly onto
  the engine's existing shape: the Game-Turn-level land/strategic split is already what
  `Policy.malta_africa_planes` and `game/basing.py` decide, and the per-stage specific tasking is
  exactly what an `air_missions()` hook would return.

The one thing that **is** genuinely blocked is **CAP as an ordered mission**, and not on a missing
rule — 40.21/40.22/40.26/40.27 are complete and transcribed above — but on the engine's **phase
placement**. Interception happens on the *path of flight*, between both sides' missions being placed
and either resolving (40.27, 33 IV.F.2→3). The engine runs air support inside each side's own Combat
Segment (`engine.py:6369`), so the two sides' missions are never simultaneously on the map. Ordered
CAP needs the Land Support Air Phase lifted out of `_combat` and run once per Operations Stage for
both sides, per 33 IV.F. That is a sequencing change, not a missing rule.
