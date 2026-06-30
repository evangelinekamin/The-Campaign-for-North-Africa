# The Campaign for North Africa × LLM Agents — Research & Design Brief

**Purpose.** This is the authoritative, self-contained brief for building a system in which a team of LLM agents plays *The Campaign for North Africa* (CNA) to completion. It is written to be handed to a coding agent (Claude Code) as the source of truth: it carries not just the design but the **rationale** behind each decision, grounded in a corpus of agent-research papers, so the implementer can make correct judgment calls without re-deriving them. It subsumes the earlier `cna-llm-engine-sketch.md` (the schema here is the canonical, expanded version).

**How to read it.** §1–§2 establish the target and the goal. §3 is the research synthesis: design decisions tagged to the papers that justify them (paper IDs are from the project's research collection; pull them with the IDs/URLs in §12). §4–§7 are the architecture. §8 is the build plan. §9–§11 are decisions, risks, and positioning.

**One-line thesis.** CNA's legendary difficulty is *bookkeeping tedium*, not strategic depth; digitizing the bookkeeping erases it. Therefore **the rules engine is ~80% of this project and the LLM play is the easy, fun part** — and the headline achievement, "first documented completion of the full campaign," is mostly a statement about having built a *faithful engine*.

---

## 1. The target: CNA, faithfully

*The Campaign for North Africa: The Desert War 1940–43* (SPI, 1979; designed by Richard H. Berg) simulates the North African campaign from September 1940 to May 1943.

**Scale and structure (these are hard constraints the engine must honor):**
- **111 turns**, each representing **one week** of game time. The full campaign is these 111 turns end to end.
- **~1,600–1,800 counters** (sources vary; the back-printed sheets total ~1,800 unit/supply/marker faces). Crucially, **a counter is not a single value** — each ground counter represents multiple sub-units whose strength, equipment, and step-losses are tracked on **logs**. This per-counter logging is the dominant source of the "1,500 hours."
- **A single shared board**: five ~22"×34" mapsheets butted into one continuous ~34"×115" hex map. Both sides play on the same board.
- **Rules** span multiple booklets (Historical Background, Land Game, Air & Logistics Game, Charts & Tables, plus exclusive Axis/Commonwealth charts) — 200+ pages total. The full, authoritative rules are scanned on the Internet Archive: `https://archive.org/details/campaign-for-north-africa`. **The engine's rule content (combat results tables, supply consumption rates, terrain movement costs, sequence of play) must be transcribed from there at implementation time — this brief specifies structure, not rule values.**

**Why it has no published completion:**
- Estimated **1,500 hours** for a full campaign; Berg never completed one and no completion has been published. The game was shipped under-playtested (the designer himself called it "wretched excess").
- The grind is bookkeeping, not depth: per-counter logs, **per-individual-aircraft and per-individual-pilot tracking** in the air game, and a **multi-commodity supply system** (fuel, water, ammunition, food/rations tracked separately) routed through finite transport. Reviewers consistently note the game "is less about combat and more about managing logistics, supply lines, and sanity." Realism grades ~100%; excitement grades ~15%.

**Information model — OPEN information (verified).** CNA is played on one shared board with no umpire; the sequence of play is fully described without hidden movement or concealed intelligence. (One AI-generated wiki claims fog-of-war via hidden counters; this is contradicted by the single-shared-map structure and uncorroborated by reliable sources — treat it as false unless the rulebook proves otherwise.) **The team-based "command separation" is organizational, not secrecy**: no single human can track everything, so a team divides the labor (the famous example: one teammate does nothing but water calculations). This matters for the architecture: role-scoped agent views are a *tractability and coordination* mechanism over a fully-visible ground truth, **not** a hidden-information mechanism.

**Core systems the engine must model:** the hex map with terrain; the full order of battle with per-unit logs; the multi-commodity supply network (sources → depots → transport → consumption); the air game (individual aircraft + pilots, basing, missions, maintenance/serviceability); the naval game (ships, convoys, sea zones, ports, interdiction); ground/air/naval combat resolution (odds-based CRTs with terrain/supply/combined-arms modifiers); weather; and victory conditions (territorial control of key locations such as Alexandria, Benghazi, Tripoli, Cairo, plus supply-interdiction effects, tallied to victory points).

**One myth to not over-engineer:** the "macaroni rule" (Italian troops needing extra water to boil pasta) is **a joke Berg has confirmed as such** — do not anchor "faithful simulation" pride on it. The *genuine* rules (per-pilot tracking, multi-commodity supply) are absurd enough, and are exactly the parts that are trivial for an engine and brutal for humans.

**Useful existing asset:** a Tabletop Simulator mod on Steam Workshop has digitized the board and counters (no rules enforcement — TTS is a physics sandbox). Useful for seeding map/counter art and the opening setup/positions, and for a differential check on Phase-0 setup.

---

## 2. Goals, honestly stated

**Primary goal.** Produce the **first documented complete playthrough of the full 111-turn campaign**, played by LLM agents, adjudicated by a faithful digital engine, with a reproducible, replayable record. The weight of this achievement is on engine fidelity + completion, not on strategic brilliance.

**Secondary goal (the watchable / portfolio payoff).** **Emergent multi-agent behavior** — the inter-commander friction, negotiation, and gloriously imperfect operational decisions. This is the YouTube hook and the portfolio differentiator. Research shows this is both real and measurable: autonomous agents have generated >1M tokens of dialogue across 1,100 games in a social-deduction setting `[arxiv:2603.26635v1]`.

**Explicit non-goal (for now).** *Optimal / superhuman play.* Current LLMs are weak at hex spatial reasoning and multi-hundred-turn logistics optimization. The project embraces this: the entertainment and the achievement both survive suboptimal play. Strong play is a separate, much larger effort (RL self-play — see §3.7 and Phase 3).

**Success criteria.**
1. The engine completes a full 111-turn campaign without invariant violations (§7), producing a deterministic, replayable event log.
2. All decisions are made by LLM agents through the validated action interface (§4.4) — no human in the loop during a run.
3. The run is reproducible: `seed + event log → byte-identical game`.
4. (Secondary) The agent-dialogue/chatter feed is coherent enough to be narratively legible for video.

---

## 3. Research synthesis → design decisions

Decisions below are tagged with the paper(s) that justify them. **Corpus caveat:** the collection mixes peer-style preprints (arXiv/HF — the substance) with scraped blog/listicle content (Medium/Reddit/YouTube framework round-ups). Treat blog-sourced precise figures ("+23%", "+35%") as marketing, not findings. The decisions here lean on the preprints.

### 3.1 Planning over a long horizon

- **Use hierarchical, multi-temporal-scale planning.** Maintain a slowly-updated strategic *intent* at the top and fast per-phase tactical orders below; do **not** re-plan the whole campaign every phase. Multi-temporal-scale planning with (latent) world models reduces inference-time planning cost and lifts long-horizon success rates `[arxiv:2604.03208v1]`. Reinforced by findings that integrating context-memory sensitivity improves long-horizon decisions in dynamic environments `[hf:2604.07429]`.
- **Pair planning with externalized dual memory.** Long-horizon agents with dedicated memory modules outperform memoryless baselines over 100-step horizons `[arxiv:2604.07269v1]`; this is structural support for the memory layer in §4.6.
- **Yardstick for the logistics agent.** CNA's supply problem is structurally a long-horizon, partially-observable **resource-allocation** problem. There is a direct analogue benchmark — a 132-month dynamic enterprise resource-allocation environment `[hf:2603.23638]` — usable to sanity-check whether the Logistics Commander agent is actually competent before trusting it in the full game.
- **Long-context game learning is a live, benchmarked problem.** The PokeAgent long-context game challenge `[hf:2603.15563]` and the GameWorld multimodal-game evaluation suite (34 games / 170 tasks, with state-verifiable metrics) `[hf:2604.07429]` are reference points for evaluating agents *inside an actual game loop*, including action-validity failure modes.

### 3.2 Multi-agent coordination & roles

- **Adopt role differentiation as an error-decorrelation tool, not just a theme.** Role-differentiated proposer/executor/checker/adversary structures reduce *correlated* error under asymmetric information `[arxiv:2604.03201v1]` — precisely CNA's separated-command situation. Map CNA's five-per-side command structure (Commander-in-Chief, Logistics, Front, Air, Naval) onto this.
- **Coordinate via explicit messages over a shared blackboard.** Message-based coordination among agent teams improves task completion in complex environments `[arxiv:2509.17158]`; clear role definitions improve coordination `[arxiv:2509.10769]`. The inter-commander messaging is *also* the primary source of watchable drama.
- **For the eventual RL path, use separate policy/value heads per side.** Asymmetric board games benefit from per-role policy/value heads to handle conflicting evaluation functions `[arxiv:2604.05476v1]`; CNA's Axis/Allied asymmetry fits this directly.
- **Do NOT adopt a heavyweight orchestration framework.** Much of the multi-agent corpus is framework marketing (CrewAI, AutoGen, "Tribe," AgentMCP). For a from-scratch engine-coupled system, a thin custom harness beats a framework — the framework's abstractions fight the tight engine/agent loop. Keep orchestration first-party.

### 3.3 Tool-use & action reliability (the load-bearing section)

- **Validate at the engine boundary; do NOT rely on constrained/grammar decoding to enforce legal actions.** This is the single most important interface decision, and it is counterintuitive. Constrained decoding imposes a cognitive load that *degrades* the model's ability to detect and resolve its own semantic errors and can introduce new failure modes — an "alignment tax" `[arxiv:2604.06066v1]`. The same work finds constrained decoding without external critics/symbolic tools does not improve self-correction. **Therefore:** agents emit orders in a permissive structured format; the *engine* checks legality against the rules and returns **typed rejections with machine-readable reasons**; the agent revises on a **bounded retry** (≤2), after which the order is dropped/defaulted. The engine is the "symbolic tool / external critic" the literature says you need.
- **Keep tool-call reasoning short, and commit to a valid verb early.** CoT length has a *non-monotonic* effect on function-calling accuracy — more reasoning is often worse — and committing to a valid function name early improves reliability `[arxiv:2604.02155v1]`. Use brief CoT for routine orders; reserve long reasoning for genuinely strategic decisions.
- **Provide explicit tool-use exemplars in the system prompt** (a real if basic lift to function-calling accuracy, corroborated across multiple sources and consistent with the Berkeley Function Calling Leaderboard's framing). Stress-test the action interface with synthetic multi-step tool-use tasks of controlled complexity `[openreview:UKYCJixSFt]`.
- **Treat rejections as the primary learning signal, not as failures.** `Reject("insufficient fuel: need 12, have 7")` is exactly the feedback an agent needs to produce a legal, better order — and it is *why an LLM decider can work against a rigid engine without internalizing the 200-page rulebook.*

### 3.4 Cost & adaptive compute

- **Batch decisions per phase.** One `move_units([...])` call resolves many units; never one call per unit. With 111 turns × 2 sides × ~6 phases × hundreds of units, per-unit calls are millions; batched, it is tractable.
- **Tier models by decision importance.** Routine subordinate orders → local / cheap (Flash-class) models; Commander-in-Chief strategy and disagreement-resolution → frontier model.
- **Spend extra compute only where the model is uncertain.** Inter-rollout action *agreement* is a free signal for adaptive compute allocation: sample N cheap rollouts; if they agree, commit; only on disagreement (or a flagged-strategic decision) escalate to a frontier model / longer reasoning `[arxiv:2604.08369v1]`. This + batching + tiering is the entire cost-control strategy.
- See §6 for the quantified model.

### 3.5 Memory & anti-fossilization

- **The harness owns all durable state; the model is stateless between calls.** Externalize memory, skills, and protocols into the harness rather than relying on model parameters or ever-growing context `[hf:2604.08224]`. The full game state lives in the engine and **never enters an LLM context whole** (§4.4).
- **Store accumulated lessons as human-readable, editable rules — not opaque embeddings.** This directly prevents the knowledge-base "fossilization" failure mode (a known pain point for this project). The pattern: persist experiences as readable detection/decision rules in an experience library, enabling self-improvement *and* manual inspection/pruning `[arxiv:2604.05458v1]`. Example lesson: "when fuel < X near El Alamein, do not push the armor."
- **Add forgetting.** Decay/expire stale tactical lessons while retaining strategic ones, to keep the library from bloating (biologically-inspired forgetting / multi-channel retrieval) `[hf:2604.04514]`; lifelong-memory framing `[hf:2604.01007]`.
- **Personalize the reasoning, not just the memory.** Evidence that evolving the *reasoning/policy* (not just accumulating memory) yields the real gains `[arxiv:2604.14972v1]` — i.e., the experience library should shape *how* commanders reason, not just hand them facts.

### 3.6 Game-specific behavior & the observation channel

- **Feed agents structured text, never a rendered board.** Vision-language models systematically misread abstract game state ("semantic fixation" — rule-mapping failures distinct from perception errors) `[hf:2604.12119]`. Keep all agent observations as compact structured text/tables; rendering is for the *human/viewer* layer only (§4.7).
- **Let agents learn across games.** Online experiential learning in text-game environments improves task accuracy and token efficiency `[arxiv:2603.16856v1]` — supports the cross-game adaptation loop in Phase 2.
- **Emergent dialogue is real and measurable** `[arxiv:2603.26635v1]`; **decision-density and role-attribution are known agent weak points** that benchmarks expose `[hf:2603.24329]` — instrument for both.
- **Borrow the "inject bugs, verify" QA pattern** for the engine test suite: multi-agent systems that develop games and inject bugs create human-verified benchmarks for autonomous bug detection `[hf:2604.02648]` — conceptually useful for building the golden-position regression suite in §7.

### 3.7 The strong-play path (Phase 3, optional)

If the project ever pivots from spectacle to *strong* play: CNA is open-information, so perfect-information self-play (AlphaZero-style) applies. The closest template in the corpus is a reproduction of AlphaZero on an **asymmetric** board game via self-play RL, with separate policy/value heads per side `[arxiv:2604.05476v1]`. This is a substantially larger effort (a fast engine step becomes essential — see §5/§9 on the Rust fork) and is explicitly out of scope for Phases 0–2.

### 3.8 Gap note (transparency)

Three areas were queued for deeper search but the research MCP became unresponsive before they completed: (a) self-improvement/experiential-learning loops, (b) efficient-inference/cost-reduction techniques (KV-cache reuse, speculative decoding, prompt-caching for the largely-static rules context), and (c) spatial/grid/coordinate encodings for map-heavy reasoning. The decisions above stand on the corpus already retrieved; these three sections can be strengthened later by re-running those searches.

---

## 4. System architecture

### 4.1 The architectural commitment: event sourcing

The engine is **not** a mutable state blob. It is an **append-only event log**, and `GameState` is a deterministic fold over it:

```
GameState = fold(apply, initial_state, events)
```

Every state change is an event carrying the RNG draws that produced it:

```
Event {
  seq:   int            # global total order
  turn:  int            # 1..111
  phase: PhaseEnum
  side:  Side           # AXIS | ALLIED
  actor: RoleId         # which commander, or SYSTEM
  kind:  EventKind
  payload: {...}
  rng_draws: [int]      # every die roll consumed, in order
}

EventKind ∈ {
  OrderIssued, OrderRejected, SupplyAllocated, TransportRouted,
  UnitMoved, PostureChanged, CombatDeclared, CombatResolved,
  AirMissionAssigned, AirMissionFlown, AircraftMaintained,
  NavalMovement, ConvoyResolved, SupplyConsumed, StepLost,
  WeatherRolled, PhaseAdvanced, TurnAdvanced, VictoryChecked, ...
}
```

**Why this is non-negotiable for *this* project:**
- **Reproducibility.** `seed + event log → byte-identical game`. A "first documented completion" of a game with no prior published completion is only credible if anyone can replay it exactly.
- **Free visualization.** The video/replay renderer is *another fold* over the same events; there is no separate "save for video" path to build (§4.7).
- **Auditability.** When the engine adjudicates wrongly (it will, during development), the full causal chain to the bad event is on disk — the auditable-trajectory property the literature argues for `[arxiv:2604.03201v1]`.
- **Time-travel testing.** Replay to turn N, fork, test a rule fix in isolation.

### 4.2 Engine state model (canonical)

The single source of truth. **Never serialized whole into an LLM context.**

```
GameState
├── meta
│     turn:int  max_turns:111  phase:PhaseEnum  active_side:Side
│     rng_seed:int  weather:WeatherState  vp:{axis:int, allied:int}
│
├── map: Hex[]                          # indexed by axial coord (q, r)
│     Hex {
│        coord:(q,r)
│        terrain: DESERT|COASTAL|ESCARPMENT|DEPRESSION|OASIS|PORT|AIRFIELD|...
│        control: AXIS | ALLIED | NEUTRAL
│        features: [Port|Airfield|Depot|Oasis|Track|Road|...]
│        occupants: [UnitId]
│     }
│
├── units: Unit[]                       # ~1,800; indexed by UnitId
│     Unit {
│        id  side  type  formation_id  hex:(q,r)
│        steps: StepRecord[]            # composition; step-losses live HERE (not a scalar SP)
│        supply: { fuel:f  water:f  ammo:f  food:f }   # per-commodity on-hand
│        status: { posture:DEFEND|ATTACK|MOVE|RESERVE
│                  disorganized:bool  spent:bool  dug_in:bool }
│     }
│
├── air: { aircraft: Aircraft[], pilots: Pilot[] }     # the infamous granular layer
│     Aircraft { id  type  base_airfield  serviceable:bool
│                mission:MissionState|None  pilot:PilotId|None }
│     Pilot    { id  skill  fatigue  status }
│
├── naval: { ships: Ship[], convoys: Convoy[], sea_zones: SeaZone[] }
│
└── logistics                           # the HEART of CNA — first-class, build first
      sources:   Source[]               # ports generating supply per commodity per turn
      depots:    Depot[]                # per-commodity stockpiles
      transport: TransportAsset[]       # finite capacity; consumes fuel; has a map position
      network:   LogisticsGraph         # nodes = sources/depots/units; edges = routes w/ capacity
```

**Two facts about CNA's state most generic designs get wrong:**
1. **A counter is a record, not a number.** `Unit.steps` is the log humans drown in; for the engine it is a list. The "1,500 hours" is mostly *this* + the air layer — trivial once digitized.
2. **Supply is multi-commodity and networked.** Fuel/water/ammo/food are tracked separately, generated at sources, routed through finite transport (which itself burns fuel), consumed by movement/combat/existence. Model it as a flow problem from day one.

### 4.3 Turn / phase structure

111 weekly turns; each turn is an ordered sequence of phases; each phase has an **owner role** (this is what scopes agent invocation). Skeleton (exact sequence-of-play to be pinned from the rulebook):

```
TURN = [
  WeatherPhase            (SYSTEM)
  LogisticsPhase   AXIS   (Logistics Commander)    # allocate + route supply
  MovementPhase    AXIS   (Front Commander)
  AirPhase         AXIS   (Air Commander)           # missions + maintenance
  NavalPhase       AXIS   (Naval Commander)
  CombatPhase      AXIS   (Front Commander)
  RecordPhase      AXIS   (SYSTEM)                   # apply losses, update logs
  …then the same block for ALLIED…
]
```

The orchestrator walks phases and invokes only the owning role's agent per phase.

### 4.4 The two engine APIs

**(a) Observation API — role-scoped views (the context-budget control).**

```
get_observation(role: Role, side: Side) -> Observation   # compact structured text/JSON
```

You cannot put 1,800 units in a context window. Each role receives only its relevant slice, sized to leave room for reasoning + retrieved lessons. Because the game is open-information, these views *focus* rather than *conceal*:

| Role | Observation contains |
|---|---|
| **Commander-in-Chief** | front-line trace, VP status, aggregate supply health, subordinates' standing reports, top threats. *No individual counters.* |
| **Logistics Commander** | full supply ledger, depot stockpiles, transport positions/capacity, consumption forecast, pending requests from other commanders |
| **Front Commander** | units in/near contact, terrain, enemy positions, own supply state, CinC intent |
| **Air Commander** | airfields, serviceable aircraft/pilots, enemy air picture, mission requests |
| **Naval Commander** | convoys, sea zones, ports, threats, escort status |

Observations are **structured text, never a rendered board** (VLM semantic-fixation finding, §3.6). Keep them compact — context size directly drives cost (§6).

**(b) Action API — the function-calling surface (small, typed verbs per role).**

```
# Front Commander
move_units(orders:[{unit_id, path:[(q,r)…]}])
    -> [{unit_id, Moved | Blocked(reason) | PartialMove(stopped_at)}]
set_posture(unit_id, posture)            -> Ack | Reject(reason)
declare_attack(attacker_ids, target_hex, support)
    -> CombatResult | Reject(reason)

# Logistics Commander
allocate_supply(allocs:[{depot_id, commodity, qty, dest}]) -> [Result]
route_transport(transport_id, path, cargo:{commodity:qty}) -> Result | Reject(reason)

# Air Commander
assign_mission(aircraft_ids, pilot_ids, mission_type, target)
    -> MissionAck | Reject(reason)

# Naval Commander
move_convoy(convoy_id, route)            -> Result | Reject(reason)
set_escort(convoy_id, ship_ids)          -> Ack | Reject(reason)

# Commander-in-Chief
set_intent(StrategicIntent)   -> Ack     # standing plan; updated infrequently (§4.5)
set_priorities(priorities)    -> Ack
message(to_role, content)     -> Delivered    # inter-agent comms (blackboard)
```

**The four rules governing this surface (each from §3.3/§3.4):**
1. **Validation lives in the engine, not in constrained decoding** `[arxiv:2604.06066v1]`. Agents emit permissive structured orders; the engine returns typed rejections with reasons.
2. **Rejections are feedback.** Bounded retry (≤2) feeding the reason back; then drop/default.
3. **Batch orders per phase** — one call resolves many units `[cost]`.
4. **Brief CoT + adaptive compute** — short reasoning for routine orders, escalate only on inter-rollout disagreement or flagged-strategic decisions `[arxiv:2604.02155v1, arxiv:2604.08369v1]`.

### 4.5 Agent layer

Maps onto CNA's actual ten-player structure (five per side), which is why the split is natural rather than imposed:

```
        ┌──────────────── Commander-in-Chief (frontier model) ────────────────┐
        │      holds StrategicIntent; arbitrates; sets priorities/messages      │
        └───┬───────────┬───────────┬───────────┬──────────────────────────────┘
        Logistics     Front        Air         Naval    (cheap/local; escalate on disagreement)
            │            │           │            │
            └──────── shared blackboard / message bus ──────────┘
```

- **Hierarchical planning** `[arxiv:2604.03208v1]`: CinC maintains a standing intent updated at campaign cadence; subordinates issue concrete per-phase orders against it. Do not re-plan globally each phase.
- **Message-based coordination** `[arxiv:2509.17158]`: the Logistics→Front "you don't have the fuel for that" exchange flows over the blackboard — and is the best video content.
- **Tiered models + adaptive compute** `[arxiv:2604.08369v1]`: routine → local/Flash; strategic + disagreement-resolution → frontier (Gemini Pro on the GCP credits / Opus).

### 4.6 Memory layer (targets fossilization directly)

```
Hot state        = engine GameState            # authoritative; never wholly in any LLM context
Working memory   = current scoped Observation + blackboard messages for this phase
Experience lib   = append-only, HUMAN-READABLE, EDITABLE decision rules; retrieved by situation
Forgetting       = decay/expire stale tactical lessons; retain strategic ones
```

- Harness owns durable state; model is stateless between calls `[hf:2604.08224]`.
- Lessons stored as **readable rules**, inspectable and prunable `[arxiv:2604.05458v1]` — this is the specific anti-fossilization mechanism.
- Forgetting prevents bloat `[hf:2604.04514]`; evolve reasoning/policy, not just stored facts `[arxiv:2604.14972v1]`.

### 4.7 Visualization / replay layer

A **fold over the same event log** that renders board state per turn (to image/video) plus the agents' reasoning/chatter feed. This is the only place a *rendered* board exists — agents never see it (§3.6). Because it consumes events, it requires no separate persistence path and trivially supports scrubbing/replay. Seed the board/counter art from the Tabletop Simulator mod if convenient.

---

## 5. Concurrency & performance model

This workload has **two distinct parallelism regimes** that want different tools:

- **Within a single game — concurrency is I/O-bound.** Engine work (folding events, CRT lookups, supply arithmetic) is microseconds; the wall-clock cost is *waiting on model calls*. The GIL releases during I/O, so `asyncio` / a thread pool give real concurrency for firing many calls at once (batched unit-order resolution; the N parallel rollouts for the disagreement check). This is the per-turn latency win, and Python handles it well.
- **Across games — throughput wants process parallelism.** For the experience library (Phase 2) and any RL self-play (Phase 3), run **N independent game processes/workers** (multiprocessing or containers). This sidesteps the GIL entirely (no threading CPU-bound engine work) and scales linearly across cores and machines. Cloud box vs dedicated local rig is just "how many game workers can I fan out."

**Rust enters only if the engine *step itself* becomes the bottleneck** — realistically only under heavy RL self-play wanting millions of fast steps — droppable in later via PyO3 (the language fork in §9). Everything through Phase 2 is pure Python. Get it correct single-threaded first; parallelize as a dedicated optimization pass before the full run.

---

## 6. Cost model

**The problem:** 111 turns × 2 sides × ~6 phases ≈ ~1,300 phase-activations per full game. Naive per-unit calls (× hundreds of units × retries) reach millions of LLM calls per game — infeasible. **Batched + tiered + adaptive**, the same game is order **single-digit-thousands** of calls, the large majority routed to cheap/local models.

**The three levers (multiplicative):**
1. **Batching** — one call → many units' orders. Biggest single reduction.
2. **Tiering** — local/Flash for routine; frontier only for CinC-strategic + disagreement-resolution. Most calls become cheap or free (local).
3. **Adaptive compute** `[arxiv:2604.08369v1]` — N cheap rollouts; escalate only on disagreement. Caps frontier spend.

**Context discipline is part of cost.** Cost ≈ calls × tokens/call; tokens/call is dominated by observation-slice size. Keep slices compact (§4.4); the rules text, if needed in context, is largely static → exploit prompt/KV caching. The full state never enters context, which is what makes per-call tokens bounded.

**Budget guidance ($1,000 GCP credits):** with batching+tiering, a full campaign's *frontier* spend is plausibly low-tens-of-dollars-or-less per run (heavily dependent on slice sizes and rollout counts), leaving room for dozens of runs — or fewer runs with richer reasoning/negotiation. **Do not trust this estimate blind: instrument exact call-count and token-count on the Phase-1 small scenario, then extrapolate to 111 turns before committing to a full run.** Empirical measurement on the small scenario is the gate to the full campaign.

---

## 7. Validation & correctness (what makes "completion" credible)

Without this, a "finished" game is just *confidently wrong for 111 turns* — the central failure mode.

- **Invariants / property tests (checked every event):**
  - **Supply conservation:** nothing created except at sources; nothing vanishes except defined consumption/loss/sinks (per commodity).
  - `Unit.steps` counts ≥ 0; transport load ≤ capacity; no unit in illegal terrain; control changes only via legal mechanisms.
- **Golden positions:** hand-adjudicated mini-situations with known-correct outcomes, used as regression tests for the rules engine as it grows. (Build these incrementally while transcribing the rulebook; the "inject-bugs-and-verify" QA framing `[hf:2604.02648]` is a useful conceptual model.)
- **Determinism / replay equivalence:** `same seed + same event log ⇒ identical GameState`. A CI test.
- **Differential check:** cross-check the opening setup/positions against the Tabletop Simulator module (digitized board + counters, no rules).

---

## 8. Build plan (phased — do NOT start at 111 turns)

| Phase | Goal | Agents? | Acceptance criteria |
|---|---|---|---|
| **0** | Engine skeleton + event log + **one small intro scenario's** map/OOB. A **scripted (non-LLM) policy** issues legal orders. | **No** — de-risk the engine alone | Loop runs end-to-end; all §7 invariants hold across the scenario; replay is byte-deterministic; differential check passes on opening. |
| **1** | Swap scripted policy → **LLM agents** on the same small scenario. Role-scoped observations, batched orders, rejection→retry, blackboard comms, tiered/adaptive compute. | **Yes** | Agents complete the scenario through the validated interface with no human intervention; instrumented call/token counts captured for extrapolation (§6). |
| **2** | **Experience library + forgetting**; agents adapt across repeated runs. Build the replay→render layer for video. | **Yes** | Measurable cross-game improvement on a fixed scenario; experience library is human-readable/prunable; renderer produces per-turn board + chatter feed. |
| **3** *(optional)* | **Full 111-turn campaign.** And/or **RL self-play** for strong play (`[arxiv:2604.05476v1]`; per-side policy/value heads; Rust engine via PyO3 if step-speed bound). | **Yes** | A complete, reproducible 111-turn campaign log with no invariant violations — the primary goal. |

**Phase 0 with a scripted policy is the highest-ROI, most-skipped step:** it proves the engine is correct *before* spending tokens and *before* LLM noise can mask engine bugs. Resist the temptation to put agents in at Phase 0.

---

## 9. Resolved decisions & open questions

**Resolved:**
- **Information model:** open-information ground truth with role-scoped *views* for tractability/coordination (not secrecy). Verified against the game's structure.
- **Language:** Python (best agent ecosystem; concurrency story in §5). Rust reserved for a later engine-core port via PyO3 *only if* engine step-speed becomes the bottleneck (effectively: only under Phase-3 RL).
- **Comms richness:** richer back-and-forth negotiation between commanders is in scope (better video; modest extra token cost) — dial to taste.

**Open / deferred:**
- **Exact starting scenario:** pick the smallest intro scenario at Phase 0 (design is scenario-agnostic).
- **Concealed-counter subsystem:** if any limited-intelligence rule exists in the rulebook, confirm it when building the observation layer at Phase 1; it would be a narrow "what's revealed on contact" addition, not a structural change.
- **Negotiation depth vs cost:** how many message round-trips per phase to allow — settle empirically against the Phase-1 cost measurement.

---

## 10. Risks & failure modes

| Risk | Mitigation |
|---|---|
| **Engine misencodes the rules** (the biggest risk) | Golden positions + invariants + Phase-0 scripted validation before any agent; transcribe from the Internet Archive rulebook, not from memory. |
| **LLM decision quality is poor** (weak spatial/logistics) | Accepted under the spectacle goal; mitigated by structured-text observations, hierarchical planning, and the experience library. |
| **Cost blowup** | Batching + tiering + adaptive compute; measure on the small scenario before the full run. |
| **Context overflow** | Role-scoped compact views; full state never in context; harness-owned state. |
| **Knowledge-base fossilization** | Human-readable, prunable experience library + forgetting. |
| **VLM misreads the board** | Structured text to agents; rendering for humans only. |
| **Non-reproducible runs** | Event sourcing with captured RNG draws; replay-equivalence CI test. |

---

## 11. Prior art & positioning

**Closest published work, and why it doesn't pre-empt this:**
- LLM-driven strategic/conflict simulators (e.g. WarAgent-style world-conflict simulation; Fable's SIM-1 leadership-crisis wargame) use an **LLM *adjudicator* agent** because their worlds are *fuzzy* — adjudication is itself a judgment call. **CNA is the opposite: adjudication is mechanical and exact.** Copying their LLM-adjudicator architecture would be a category error here; the engine must adjudicate the rigid rules deterministically (§3.3).
- Game-playing benchmarks/agents — StarCraft (SC2Arena-style), Diplomacy (Meta's Cicero, RL-trained), Avalon (AvalonBench), Among Us `[arxiv:2603.26635v1]` — establish methods (function-calling, role play, self-play, emergent dialogue) but none tackle a **logistics-granular hex-and-counter monster**.

**Positioning:** no prior project appears to point LLM agents at something as logistics-dense as CNA. The niche is open — which is precisely the portfolio value. The credible, novel claim is *"first documented completion of CNA, by AI agents, on a faithful open-source engine, fully reproducible."*

---

## 12. Paper index (pull via these IDs / URLs)

**Long-horizon planning & resource allocation**
- Hierarchical Planning with Latent World Models — `arxiv:2604.03208v1`
- Joint Optimization of Reasoning and Dual-Memory (Self-Learning Diagnostic Agent) — `arxiv:2604.07269v1`
- Can LLM Agents Be CFOs? (132-month resource allocation) — `hf:2603.23638`
- The PokeAgent Challenge (long-context game learning) — `hf:2603.15563`
- GameWorld (multimodal game eval; state-verifiable metrics) — `hf:2604.07429`

**Multi-agent coordination**
- SCRAT — Coupled Control, Structured Memory, Verifiable Action (proposer/executor/checker/adversary) — `arxiv:2604.03201v1`
- ARE: scaling up agent environments and evaluations (message-based coordination) — `arxiv:2509.17158`
- AgentArch (agent-architecture benchmark) — `arxiv:2509.10769`

**Tool-use & action reliability**
- From Hallucination to Structure Snowballing: The Alignment Tax of Constrained Decoding — `arxiv:2604.06066v1`  ← the load-bearing one
- Brief Is Better: Non-Monotonic CoT Budget in Function-Calling — `arxiv:2604.02155v1`
- Contamination-Free, Controllable Multi-step Tool-Use Eval — `openreview:UKYCJixSFt`
- Berkeley Function Calling Leaderboard (BFCL) V4 — `https://gorilla.cs.berkeley.edu/leaderboard.html`

**Cost & adaptive compute**
- Don't Overthink It: Inter-Rollout Action Agreement as a Free Adaptive-Compute Signal — `arxiv:2604.08369v1`

**Memory & self-improvement**
- Externalization in LLM Agents: Memory, Skills, Protocols, Harness Engineering — `hf:2604.08224`
- MA-IDS: Multi-Agent RAG with a (human-readable) Experience Library — `arxiv:2604.05458v1`
- SuperLocalMemory V3.3 (biologically-inspired forgetting) — `hf:2604.04514`
- Omni-SimpleMem (lifelong multimodal agent memory) — `hf:2604.01007`
- SAGER: Self-Evolving User Policy Skills — `arxiv:2604.14972v1`
- Online Experiential Learning for Language Models — `arxiv:2603.16856v1`

**Game-specific behavior & evaluation**
- Deception and Communication in Autonomous Multi-Agent Systems (Among Us) — `arxiv:2603.26635v1`
- GameplayQA (decision-density, role-attribution) — `hf:2603.24329`
- Beyond Perception Errors: Semantic Fixation in VLMs — `hf:2604.12119`
- GBQA: Game Benchmark for LLMs as QA Engineers (inject-bugs-and-verify) — `hf:2604.02648`

**Strong-play path (Phase 3)**
- Reproducing AlphaZero on Tablut: Self-Play RL for an Asymmetric Board Game — `arxiv:2604.05476v1`

**Game reference**
- CNA full rules + map (authoritative) — `https://archive.org/details/campaign-for-north-africa`
- Tabletop Simulator module (board/counter art, opening setup) — Steam Workshop

---

*End of brief. Companion file: `cna-llm-engine-sketch.md` (now subsumed by §4 here). Open the rulebook before transcribing any rule values — this document specifies structure, the rulebook specifies the numbers.*
