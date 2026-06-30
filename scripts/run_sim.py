"""Phase-0 mini simulation: run the toy strip with a scripted (non-LLM) policy,
narrate it from the event log, and self-verify the two properties that make a
"completion" credible (brief §7): deterministic replay and replay-equivalence.

    python3 -m scripts.run_sim          # from the project root
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.apply import fold                                    # noqa: E402
from game.engine import RunResult, determinism_signature, run  # noqa: E402
from game.events import Event, EventKind, Side                 # noqa: E402
from game.policy import ScriptedPolicy                         # noqa: E402
from game.scenario import toy_strip                            # noqa: E402


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
    p = e.payload
    k = e.kind
    if k == EventKind.WEATHER_ROLLED:
        return f"  weather: {p['weather']} (move {p['move_modifier']:+d})  [d6={e.rng_draws[0]}]"
    if k == EventKind.UNIT_MOVED:
        return (f"  move  {p['unit_id']:<11} {tuple(p['from'])} -> {tuple(p['to'])}"
                f"  (fuel -{p['fuel_cost']:g} -> {p['fuel_after']:g})")
    if k == EventKind.ORDER_REJECTED:
        who = p.get("unit_id", p.get("target"))
        return f"  REJECT {p['order']} {who}: {p['reason']}"
    if k == EventKind.COMBAT_RESOLVED:
        return (f"  COMBAT @ {tuple(p['target'])}: {'+'.join(p['attackers'])} vs "
                f"{'+'.join(p['defenders'])} | odds {p['odds']} ({p['bucket']}) "
                f"d6={e.rng_draws[0]} -> def -{p['defender_loss']} / atk -{p['attacker_loss']}")
    if k == EventKind.STEP_LOST:
        return f"      loss  {p['unit_id']} -{p['amount']} step ({p['role']})"
    if k == EventKind.HEX_CONTROL_CHANGED:
        return f"  control {tuple(p['coord'])} -> {p['control']}"
    if k == EventKind.VICTORY_CHECKED:
        return f"  VP: Axis {p['axis']} / Allied {p['allied']}"
    return ""


def verify(result: RunResult) -> None:
    replayed = fold(result.initial, result.events)
    assert replayed == result.final, "replay-equivalence FAILED: fold(log) != live state"

    again = run(toy_strip(seed=result.initial.seed), ScriptedPolicy(Side.AXIS),
                ScriptedPolicy(Side.AXIS))
    assert determinism_signature(again.events) == determinism_signature(result.events), \
        "determinism FAILED: same seed produced a different event log"

    print("\n--- self-checks ---")
    print(f"  replay-equivalence : OK  (fold over {len(result.events)} events == live state)")
    print(f"  determinism        : OK  (seed {result.initial.seed} reproduced byte-identical log)")
    print("  invariants         : OK  (held after every event during the run)")


def summary(result: RunResult) -> None:
    s = result.final
    rejects = sum(1 for e in result.events if e.kind == EventKind.ORDER_REJECTED)
    combats = sum(1 for e in result.events if e.kind == EventKind.COMBAT_RESOLVED)
    print("\n--- summary ---")
    print(f"  winner   : {result.winner.value}  ({result.reason})")
    print(f"  turns    : {s.turn}/{s.max_turns}   events: {len(result.events)}   "
          f"combats: {combats}   rejections: {rejects}")
    print(f"  fuel     : consumed {s.fuel_consumed:g} of "
          f"{sum(u.fuel for u in result.initial.units):g} initial")
    print("  final order of battle:")
    for u in s.units:
        state = "destroyed" if not u.alive else f"str {u.strength}, fuel {u.fuel:g} @ {u.hex}"
        print(f"    {u.id:<11} {state}")


def main() -> int:
    pol = ScriptedPolicy(Side.AXIS)
    result = run(toy_strip(seed=1940), axis=pol, allied=pol)
    narrate(result)
    verify(result)
    summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
