# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A faithful, deterministic, event-sourced Python engine for SPI's 1979 monster wargame *The Campaign
for North Africa*, plus an LLM agent layer in which model "command staffs" fight the full
Sept-1940 → Dec-1942 campaign. The end goal is a watchable AI-staff campaign, not a benchmark.

**The engine is a PORT OF A RULEBOOK, and that fact governs every decision here.** A rule-by-rule
audit (2026-07-14, `scratchpad/port/`) measured 1,044 rules: 273 DONE, 132 PARTIAL, **512 MISSING, 63
WRONG**. Work proceeds by transcribing chapters of the book, not by designing behaviour.

## Commands

```bash
pip install -r requirements-dev.txt        # add --break-system-packages on this PEP-668 system python
python3 -m pytest                          # full suite; pytest.ini sets `addopts = -n auto` (xdist)
python3 -m pytest tests/test_supply.py -q  # one file
python3 -m pytest -k cohesion -q           # one test by name
python3 -m pytest --collect-only -q        # seconds-long sanity check: does it all import and collect?
```

- **Use `python3`, not `python`** — `python` is not on PATH.
- The suite takes ~25 minutes even at `-n auto`, because many tests fold entire 111-turn campaigns.
  `--collect-only` is the cheap way to prove a change is at least coherent.
- **Oversubscription gotcha:** `-n auto` spawns one worker per core. Several agents each running the
  suite concurrently will thrash the box (16 cores × N agents). Cap `-n` when running in parallel.

`scripts/` holds the measurement drivers: `measure_campaign.py`, `measure_malta.py`,
`measure_siege.py`, `run_sim.py`, `run_staff.py`, `benchmark.py`, `leaderboard.py`.

## Architecture

**Event sourcing is the spine** (`game/events.py`, `game/apply.py`):

- The engine is an append-only log of `Event`s; `GameState = fold(apply, events)` (`apply.py:452`).
- **Events are facts.** Outcomes (die rolls, losses) are baked in when the event is generated, and the
  rolls that produced them are recorded in `rng_draws` — so **`apply` is pure and replay needs no RNG**.
- `determinism_signature(events)` (`engine.py:3100`) hashes the entire canonical log.
- `game/observation.py` is a **read-only projection** for agents; its output must never re-enter the
  event stream. It honours CNA limited intelligence (rule 3.6): the enemy is visible only as stack
  presence — never exact strengths or identities.

**`game/dice.py` is THE INSTRUMENT. Read its docstring before touching any die.** ~15 independent
per-subsystem streams (weather / initiative / combat / breakdown / interdiction / air / …), each seeded
from a blake2b digest of (master seed, subsystem name). It exists to kill one specific bug: subsystems
draw *conditionally*, so under a single shared RNG, changing how many dice one subsystem drew
reshuffled the dice every other subsystem saw — which silently corrupted every A/B measurement this
project made for weeks. **A die drawn (or not drawn) in one subsystem must never move another's.**

**Engine loop:** `game/engine.py::run(initial, axis, allied)` (`engine.py:141`) drives the phases.
`game/invariants.py` runs property checks after every applied event and **must never raise** — a
violation means a rule is misencoded, and the project fails loud rather than run "confidently wrong for
111 turns".

**Scenarios** (`game/scenario.py`): `rommels_arrival(seed)` and `siege_of_tobruk(seed)` are the small,
fast benchmark scenarios; `campaign(seed)` is the full GT1–111 war (3 OpStages per turn).

**Policies** (`game/policy.py::Policy` — `movement()`, `combat()`, `supply_orders()`):

- `ScriptedPolicy` — the deterministic baseline both benchmarks are pinned against.
- `StaffPolicy` (`game/staff_policy.py`) — five LLM "seats" (chief/mobile/infantry LLM-driven;
  QM/naval/air scripted).
- `CampaignAxisPolicy` / `CampaignCommonwealthPolicy` (`game/campaign_policy.py`) and
  `CampaignStaffPolicy` — the campaign variants.
- `game/llm.py` is the client seam: `MockClient` for tests (deterministic, and able to return
  adversarial output to exercise the order-rejection boundary), `OpenRouterClient` live via
  `OPENROUTER_API_KEY`.
- `game/narrator.py` turns a recorded staff log plus the god-view fog diff into a deterministic diary —
  the "watchable campaign" path.

**Data:** every chart is transcribed into `data/*.json` (`logistics_rates.json`, `breakdown_rates.json`,
`cp_costs.json`, terrain/roads/OOB/reinforcements). Code reads magnitudes from data, never from
literals.

## The rules of this port (non-negotiable)

1. **Transcribe, never invent.** If a number is wrong, the fix is the number the book prints — never a
   number that balances the game. Flag every proxy and every judgement call.
2. **The scan is the arbiter.** `tmp/The Campaign for North Africa.pdf` (134 MB, **no text layer**) is
   the original 1979 book. When a chart is in dispute, **render the page and read it with your own
   eyes.** This has repeatedly settled what OCR could not — including proving the *book itself* is
   misprinted (the 54.17 demolition table). That override is recorded under a **named errata key** in
   `data/logistics_rates.json`, never applied silently.
3. **Sections 32, 47 and 58 are the ABSTRACT game and DO NOT APPLY.** They exist for players *not*
   running the full Logistics/Air games — "Why anyone would play a campaign game without the Air and/or
   Logistics Game(s) is beyond me" (the designer, ch. 64). We run the full games. An abstract-game rule
   in force is a **bug class**, not a shortcut; it has bitten this project twice (the ½-CPA supply trace
   and the teleporting escorted dump).
4. **Determinism binds absolutely.** Same seed → byte-identical event log across two runs. The old
   byte-lock pinning the two benchmark signatures is **dropped** — they may change — but every change is
   re-baselined in **`tests/baselines.py`** (the one place they live) with a dated comment naming the
   rule that moved it. A signature proves determinism and nothing else; pinning one must never become a
   reason to avoid fixing a rule.
5. **Never weaken a test to make it pass.** If a corrected rule makes an assertion false, restate it to
   assert the correct thing and write the reason into the file. Watch for tests that *enshrine* a bug.
6. **Never campaign-gate a faithful rule** to dodge a benchmark hash. Existing gates are debt to remove.

## Where the plan lives

- **`scratchpad/port/00-THE-PORT-PLAN.md` — the authoritative work plan.** Consolidated from six
  rule-by-rule audits (the sibling files in that directory), every claim carrying a `file:line` or chart
  citation, phased with dependencies. Read it before changing engine behaviour; it supersedes older
  gap analyses, all of which wrongly called the engine "done and faithful".
- `docs/rules/` — the rulebook split by chapter. `90-charts-tables-and-play-aids.md` holds the charts;
  `99-foldout-charts.md` the foldouts.
- `docs/cna-llm-research-and-design-brief.md` — the original design brief. **Where it conflicts with the
  rulebook, the rulebook wins** (its "open information" assumption is wrong — rule 3.6 hides the enemy).
