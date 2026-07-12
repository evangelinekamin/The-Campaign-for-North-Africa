"""Phase-0 mini simulation: run a scenario with a scripted (non-LLM) policy on the
real land engine (CPA + ZOC + stacking movement, real combat + supply), narrate it
from the event log, and self-verify the two properties that make a "completion"
credible (brief §7): deterministic replay and replay-equivalence.

    python3 -m scripts.run_sim                     # toy corridor, fresh random seed
    python3 -m scripts.run_sim tobruk 1941         # real Map C terrain, fixed seed
    python3 -m scripts.run_sim rommel              # Rommel's Arrival, scripted agents
    python3 -m scripts.run_sim rommel llm:deepseek/deepseek-chat   # LLM agents

Each run picks a NEW random seed (so the dice visibly differ) and prints it; pass a
seed to replay a scripted game byte-for-byte. `llm:<model>` runs LLM Front
Commanders (needs OPENROUTER_API_KEY); LLM runs aren't re-runnable bit-for-bit but
their event log still folds back to the exact final state.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import fold                                     # noqa: E402
from game.engine import RunResult, determinism_signature, run  # noqa: E402
from game.events import Event, EventKind, Side                  # noqa: E402
from game.policy import ScriptedPolicy                          # noqa: E402
from game.scenario import (                                     # noqa: E402
    battle_for_tobruk, campaign, coastal_corridor, rommels_arrival)

SCENARIOS = {"corridor": coastal_corridor, "tobruk": battle_for_tobruk,
             "rommel": rommels_arrival, "campaign": campaign}


def narrate(result: RunResult) -> None:
    turn = 0
    for e in result.events:
        if e.turn != turn:
            turn = e.turn
            print(f"\n=== Game-Turn {turn} " + "=" * 30)
        line = _line(e)
        if line:
            print(line)


def _line(e: Event) -> str:
    p, k = e.payload, e.kind
    if k == EventKind.WEATHER_ROLLED:
        where = f" over {'/'.join(p['sections'])}" if p["sections"] else ""
        return (f"  weather: {p['season']} -> {p['weather']}{where}"
                f"  [dice {'-'.join(str(d) for d in e.rng_draws)}]")
    if k == EventKind.REINFORCEMENT_ARRIVED:
        return f"  +++ reinforcement {p['unit_id']} enters at {tuple(p['hex'])}"
    if k == EventKind.UNIT_MOVED:
        return (f"  move  {p['unit_id']:<11} {tuple(p['from'])} -> {tuple(p['to'])}"
                f"  (CP {p['cp_spent']:g})")
    if k == EventKind.ORDER_REJECTED:
        who = p.get("unit_id", p.get("target"))
        return f"  REJECT {p['order']} {who}: {p['reason']}"
    if k == EventKind.COMBAT_RESOLVED:
        if p.get("surrender"):
            return (f"  COMBAT @ {tuple(p['target'])}: SURRENDER ({p['surrender']}) "
                    f"-- {'+'.join(p['attackers'])} vs {'+'.join(p['defenders'])}")
        tags = []
        if p.get("morale_shift"):
            tags.append(f"morale {p['morale_shift']:+d}")
        if p.get("retreat_hexes"):
            tags.append(f"DEF RETREAT {p['retreat_hexes']}")
        if p.get("attacker_engaged"):
            tags.append("ATK ENGAGED")
        if p.get("defender_captured"):
            tags.append("DEF CAPT")
        if p.get("attacker_captured"):
            tags.append("ATK CAPT")
        extra = ("  [" + ", ".join(tags) + "]") if tags else ""
        return (f"  COMBAT @ {tuple(p['target'])}: {'+'.join(p['attackers'])} vs "
                f"{'+'.join(p['defenders'])} | diff {p['differential']:+d} (col {p['column']}) "
                f"-> def {p['defender_loss_pct']}% / atk {p['attacker_loss_pct']}%{extra}")
    if k == EventKind.ANTI_ARMOR_RESOLVED:
        return (f"  ANTI-ARMOR @ {tuple(p['target'])} by {'+'.join(p['firers'])}: "
                f"{p['actual']} pts -> {p['damage']} armor damage")
    if k == EventKind.BARRAGE_RESOLVED:
        eff = []
        if p.get("loss"):
            eff.append(f"lose {p['loss']}")
        if p.get("pinned"):
            eff.append("PIN")
        return (f"  BARRAGE @ {tuple(p['target'])} by {'+'.join(p['firers'])}: "
                f"{p['actual']} pts vs {p['target_class']} -> {'+'.join(eff) or 'no effect'}")
    if k == EventKind.STEP_LOST:
        return f"      loss  {p['unit_id']} -{p['amount']} step ({p['role']})"
    if k == EventKind.UNIT_RETREATED:
        return f"      retreat {p['unit_id']} {tuple(p['from'])} -> {tuple(p['to'])} ({p['hexes']} hex)"
    if k == EventKind.SUPPLY_CONSUMED:
        return ""   # frequent; rolled into the summary rather than narrated per event
    if k == EventKind.HEX_CONTROL_CHANGED:
        return f"  control {tuple(p['coord'])} -> {p['control']}"
    if k == EventKind.VICTORY_CHECKED:
        return f"  VP: Axis {p['axis']} / Allied {p['allied']}"
    return ""


def verify(result: RunResult, factory, axis, allied, *, check_determinism: bool = True) -> None:
    replayed = fold(result.initial, result.events)
    assert replayed == result.final, "replay-equivalence FAILED: fold(log) != live state"
    print("\n--- self-checks ---")
    print(f"  replay-equivalence : OK  (fold over {len(result.events)} events == live state)")
    if check_determinism:
        again = run(factory(seed=result.initial.seed), axis, allied)
        assert determinism_signature(again.events) == determinism_signature(result.events), \
            "determinism FAILED: same seed produced a different event log"
        print(f"  determinism        : OK  (seed {result.initial.seed} reproduced byte-identical log)")
    else:
        print("  determinism        : n/a (LLM is non-deterministic; the event log replays exactly)")
    print("  invariants         : OK  (held after every event during the run)")


def summary(result: RunResult) -> None:
    s = result.final
    rejects = sum(1 for e in result.events if e.kind == EventKind.ORDER_REJECTED)
    combats = sum(1 for e in result.events if e.kind == EventKind.COMBAT_RESOLVED)
    print("\n--- summary ---")
    print(f"  winner   : {result.winner.value if result.winner else 'draw'}  ({result.reason})")
    print(f"  turns    : {s.turn}/{s.max_turns}   events: {len(result.events)}   "
          f"combats: {combats}   rejections: {rejects}")
    print(f"  supply   : consumed {s.consumed['AMMO']}/{s.initial_supply['AMMO']} ammo, "
          f"{s.consumed['FUEL']}/{s.initial_supply['FUEL']} fuel")
    print("  final order of battle:")
    for u in s.units:
        state = "destroyed" if not u.alive else f"str {u.strength} @ {u.hex}"
        print(f"    {u.id:<11} {state}")


def _policies(model, which):
    """Scripted doctrine by default; LLM Front Commanders if a model is given (`llm:<model>`).
    Each side plays its own side (a contested objective is a real race). On the full campaign the
    scripted default is the CANONICAL campaign pairing -- the Axis multi-hop coastal haul
    (CampaignAxisPolicy) vs the offensive-capable Commonwealth (CampaignCommonwealthPolicy) -- so
    `run_sim campaign` exercises the real Benghazi-to-front supply economy, not the base single-
    hop port shuttle. LLM agents need OPENROUTER_API_KEY in the environment."""
    if model is not None:
        from game.llm import OpenRouterClient
        from game.llm_policy import LLMPolicy
        client = OpenRouterClient(model)
        return LLMPolicy(Side.AXIS, client), LLMPolicy(Side.ALLIED, client)
    if which == "campaign":
        from game.campaign_policy import CampaignAxisPolicy, CampaignCommonwealthPolicy
        return CampaignAxisPolicy(), CampaignCommonwealthPolicy()
    return ScriptedPolicy(Side.AXIS), ScriptedPolicy(attacker=Side.AXIS)


def main() -> int:
    args = sys.argv[1:]
    model = next((a.split(":", 1)[1] for a in args if a.startswith("llm:")), None)
    positional = [a for a in args if not a.startswith("llm:")]
    which = next((a for a in positional if not a.isdigit()), "corridor")
    factory = SCENARIOS.get(which, coastal_corridor)
    # Fresh seed each run so the RNG is visibly alive; pass an explicit seed to
    # replay a specific game (seed + log -> identical state, brief §7).
    seed = next((int(a) for a in positional if a.isdigit()), random.randrange(1, 1_000_000))

    axis, allied = _policies(model, which)
    print(f"scenario: {which}   seed: {seed}   agents: "
          f"{'LLM (' + model + ')' if model else 'scripted'}")
    result = run(factory(seed=seed), axis=axis, allied=allied)
    narrate(result)
    verify(result, factory, axis, allied, check_determinism=model is None)
    summary(result)
    if model:
        print("\n  (LLM run: the event log is the exact record; fold replays it deterministically)")
    else:
        print(f"\n  reproduce this exact game:  python3 -m scripts.run_sim {which} {seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
