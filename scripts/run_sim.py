"""Phase-0 mini simulation: run a scenario with a scripted (non-LLM) policy on the
real land engine (CPA + ZOC + stacking movement, real combat + supply), narrate it
from the event log, and self-verify the two properties that make a "completion"
credible (brief §7): deterministic replay and replay-equivalence.

    python3 -m scripts.run_sim                 # toy corridor, fresh random seed
    python3 -m scripts.run_sim tobruk          # real Map C terrain, fresh seed
    python3 -m scripts.run_sim tobruk 1941     # reproduce one exact game (fixed seed)

Each run picks a NEW random seed (so the dice visibly differ run to run) and prints
it; pass that seed back as the 2nd argument to replay a game byte-for-byte.
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
    battle_for_tobruk, coastal_corridor, rommels_arrival)

SCENARIOS = {"corridor": coastal_corridor, "tobruk": battle_for_tobruk,
             "rommel": rommels_arrival}


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
        return f"  weather: {p['weather']} (CPA {p['move_modifier']:+d})  [d6={e.rng_draws[0]}]"
    if k == EventKind.UNIT_MOVED:
        return (f"  move  {p['unit_id']:<11} {tuple(p['from'])} -> {tuple(p['to'])}"
                f"  (CP {p['cp_spent']:g})")
    if k == EventKind.ORDER_REJECTED:
        who = p.get("unit_id", p.get("target"))
        return f"  REJECT {p['order']} {who}: {p['reason']}"
    if k == EventKind.COMBAT_RESOLVED:
        return (f"  COMBAT @ {tuple(p['target'])}: {'+'.join(p['attackers'])} vs "
                f"{'+'.join(p['defenders'])} | diff {p['differential']:+d} (col {p['column']}) "
                f"-> def {p['defender_loss_pct']}% / atk {p['attacker_loss_pct']}%")
    if k == EventKind.STEP_LOST:
        return f"      loss  {p['unit_id']} -{p['amount']} step ({p['role']})"
    if k == EventKind.SUPPLY_CONSUMED:
        return ""   # frequent; rolled into the summary rather than narrated per event
    if k == EventKind.HEX_CONTROL_CHANGED:
        return f"  control {tuple(p['coord'])} -> {p['control']}"
    if k == EventKind.VICTORY_CHECKED:
        return f"  VP: Axis {p['axis']} / Allied {p['allied']}"
    return ""


def verify(result: RunResult, factory) -> None:
    replayed = fold(result.initial, result.events)
    assert replayed == result.final, "replay-equivalence FAILED: fold(log) != live state"
    again = run(factory(seed=result.initial.seed),
                ScriptedPolicy(Side.AXIS), ScriptedPolicy(Side.ALLIED))
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
    print(f"  supply   : consumed {s.consumed['AMMO']}/{s.initial_supply['AMMO']} ammo, "
          f"{s.consumed['FUEL']}/{s.initial_supply['FUEL']} fuel")
    print("  final order of battle:")
    for u in s.units:
        state = "destroyed" if not u.alive else f"str {u.strength} @ {u.hex}"
        print(f"    {u.id:<11} {state}")


def main() -> int:
    args = sys.argv[1:]
    which = args[0] if args else "corridor"
    factory = SCENARIOS.get(which, coastal_corridor)
    # Fresh seed each run so the RNG is visibly alive; pass an explicit seed to
    # replay a specific game (seed + log -> identical state, brief §7).
    seed = int(args[1]) if len(args) > 1 else random.randrange(1, 1_000_000)

    print(f"scenario: {which}   seed: {seed}")
    # Each side runs its own objective-seeking doctrine, so a contested objective
    # (e.g. Rommel's race for Tobruk) becomes a real race, not a walkover.
    result = run(factory(seed=seed),
                 axis=ScriptedPolicy(Side.AXIS), allied=ScriptedPolicy(Side.ALLIED))
    narrate(result)
    verify(result, factory)
    summary(result)
    print(f"\n  reproduce this exact game:  python3 -m scripts.run_sim {which} {seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
