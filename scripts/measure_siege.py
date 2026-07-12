"""Live crack-rate measurement for the Siege of Tobruk (design Step 6).

The 7-seat command staff (the 3 LLM seats Chief/GOC-Mobile/GOC-Infantry on
inception/mercury-2, the rest scripted zero-token reflexes) COMMANDS the choke --
the ferry-cut, the harbour bomb, the schwerpunkt, the reserve, and (with the floor)
the storm -- and we measure how often it drives a choked garrison onto a dry ammo
stack (15.15) and TAKES Tobruk. crack == winner is AXIS (control_of(target) flipped
by a COMBAT_RESOLVED surrender).

    python3 -m scripts.measure_siege --live --seeds 16         # floor ON crack rate
    python3 -m scripts.measure_siege --live --seeds 8 --no-floor  # model-only signal
    python3 -m scripts.measure_siege --recache --seeds 16      # zero-token replay

The plumbing is cloned VERBATIM from scripts.run_staff: KEY_FILE read into the env
ONCE (never printed/logged/committed), one OpenRouterClient per LLM seat wrapped in a
shared sha256(model+prompt) sidecar cache, --recache running the whole batch against the
populated cache with the model DISCONNECTED (a cache miss is a hard failure), usage summed
across seats and games, and fold(initial, events) == final asserted for every game.

SECURITY: the key is env-only (OPENROUTER_API_KEY), read from KEY_FILE straight into
os.environ. It is NEVER printed, logged, written to the log/cache, or committed. The cache
keys on sha256(model+prompt) -- never the key -- and cost is reported in calls/tokens, never
dollars, never the key.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.benchmark import FAST_PROVIDER, _mock_staff, game_metrics   # noqa: E402

from game import engine, narrator                                        # noqa: E402
from game.apply import apply, fold                                       # noqa: E402
from game.engine import run                                             # noqa: E402
from game.events import Control, EventKind, Side, log_to_json           # noqa: E402
from game.llm import CachingClient, MockClient, OpenRouterClient        # noqa: E402
from game.policy import ScriptedPolicy                                  # noqa: E402
from game.scenario import siege_of_tobruk                              # noqa: E402
from game.staff_policy import LLM_SEATS, StaffPolicy                    # noqa: E402

KEY_FILE = "/mnt/c/Users/evang/OneDrive/Desktop/as.txt"
MODEL = "openai/gpt-oss-120b"   # dev seat per the generalship leaderboard (~$0.026/game, 3.6% illegal, N=5)
BASE_SEED = 4200
OUT = Path(__file__).resolve().parent.parent / "out"

# FLAGGED scenario-schedule tuning proxies for the siege TEMPO (NOT rulebook magnitudes) --
# push the first harbour bomb later, bomb every N-th turn, field a stronger contesting RAF so
# the eff 7->0 cut lands ~turn 6-7 and the 12-turn clock is a genuine race, not a foregone cut.
PORTBOMB_START = 1
PORTBOMB_CADENCE = 1
RAF_FIGHTERS = 3
FERRY_BOMB = 200


class _Disconnected:
    """Refuses to call the model -- used by --recache so a cache miss is a hard, visible
    failure. model matches the live client so the sha256 cache keys line up."""
    model = MODEL

    def complete(self, prompt: str) -> str:
        raise RuntimeError("model disconnected: cache miss during re-simulation")

    def chat(self, messages: list) -> str:
        raise RuntimeError("model disconnected")

    def usage(self) -> dict:
        return {}


def _load_key(path: str = KEY_FILE) -> None:
    """Force THIS project's OpenRouter key from the key FILE into the environment,
    OVERWRITING any ambient OPENROUTER_API_KEY exported by the shell profile for another
    project (else an inherited key silently bills the wrong account). Never returned/printed/logged."""
    import os
    key = Path(path).read_text().strip()
    if not key:
        raise SystemExit(f"key file {path} is empty")
    os.environ["OPENROUTER_API_KEY"] = key


def _seat_clients(cache: dict, *, live: bool) -> dict:
    """One client per LLM seat, each wrapped in the SHARED sidecar cache. Distinct inner
    clients so parallel seats never race on usage; live=False plugs a disconnected inner so a
    fully-cached re-run needs no network and no key."""
    def inner():
        return (OpenRouterClient(MODEL, temperature=0.0, timeout=45, retries=1,
                                 provider=FAST_PROVIDER) if live else _Disconnected())
    return {seat: CachingClient(inner(), cache) for seat in LLM_SEATS}


def _port_trajectory(events) -> tuple[list[int], int | None]:
    """PORT-Tobruk Efficiency Level after each harbour bomb, and the game-turn it hits 0."""
    traj, turn0 = [], None
    for e in events:
        if e.kind == EventKind.PORT_EFFICIENCY_CHANGED and e.payload.get("port_id") == "PORT-Tobruk":
            traj.append(e.payload["level"])
            if turn0 is None and e.payload["level"] == 0:
                turn0 = e.turn
    return traj, turn0


def _ammo_trajectory(result) -> list[dict]:
    """The AL-Tobruk garrison dump (ammo/stores/water) at every Operations-Stage and game-turn
    boundary -- the curve the storm has to drain to zero for the 15.15 dry-stack surrender to
    fire. A single incremental fold (O(n)). This is the load-bearing telemetry: with the harbour
    open the ammo RISES (the ferry outpaces the storm); with the choke shut it monotonically
    drains, and the stage it hits 0 is the stage before the 15.15 capitulation."""
    boundaries = {EventKind.STAGE_ADVANCED, EventKind.TURN_ADVANCED}
    traj: list[dict] = []
    state = result.initial
    for e in result.events:
        state = apply(state, e)
        if e.kind in boundaries:
            al = state.supply("AL-Tobruk")
            if al is not None:
                traj.append({"turn": e.turn, "ammo": al.ammo,
                             "stores": al.stores, "water": al.water})
    return traj


def _surrender_path(result) -> str | None:
    """Classify the objective's fall: the auto-capitulation (15.15 dry ammo vs 15.88 cohesion
    collapse) or the 17.25 morale-roll SURR, by folding to the pre-surrender state and reading
    the code's own branch order (15.88 first, else 15.15). None if Tobruk never surrenders."""
    target = list(result.initial.target_hex)
    for i, e in enumerate(result.events):
        if (e.kind == EventKind.COMBAT_RESOLVED and e.payload.get("target") == target
                and e.payload.get("surrender") == "defender"):
            state = fold(result.initial, result.events[:i])
            live = [u for u in (state.unit(d) for d in e.payload["defenders"])
                    if u is not None and u.strength > 0]
            if not live:
                return "15.88"
            largest = max(live, key=lambda u: (u.stacking_points, u.strength))
            if largest.cohesion <= -17:
                return "15.88"
            if e.rng_draws:                              # 17.25 morale roll drove the SURR
                return "17.25"
            return "15.15"                               # dry-stack auto-capitulation
    return None


def _telemetry(result) -> dict:
    events = result.events
    traj, turn0 = _port_trajectory(events)
    tons_lost = sum(e.payload.get("tons_lost", 0) for e in events
                    if e.kind == EventKind.CONVOY_INTERDICTED)
    al = result.final.supply("AL-Tobruk")
    g = game_metrics(result)
    crack = result.winner == Side.AXIS
    assert crack == (result.final.control_of(result.initial.target_hex) == Control.AXIS)
    ammo_traj = _ammo_trajectory(result)
    ammo_curve = [p["ammo"] for p in ammo_traj]
    return {
        "crack": crack,
        "winner": result.winner.value,
        "turns": g["turns"],
        "advance_pct": g["advance_pct"],
        "axis_assaults": g["axis_assaults"],
        "port_eff_traj": traj,
        "port_eff_zero_turn": turn0,
        "convoy_tons_lost": tons_lost,
        "al_tobruk_ammo": al.ammo if al else None,
        "al_tobruk_stores": al.stores if al else None,
        "al_tobruk_water": al.water if al else None,
        "al_tobruk_ammo_traj": ammo_traj,          # per-stage garrison dump curve (the drain)
        "al_tobruk_ammo_peak": max(ammo_curve, default=None),
        "al_tobruk_ammo_min": min(ammo_curve, default=None),
        "surrender_path": _surrender_path(result),
    }


def _play(seed: int, seats: dict, floor: bool):
    axis = StaffPolicy(MockClient(_mock_staff), side=Side.AXIS,
                       seat_clients=seats, max_workers=len(LLM_SEATS),
                       storm_floor=floor)
    result = run(siege_of_tobruk(seed, port_bomb=True, raf=True, ferry_bomb=FERRY_BOMB,
                                 portbomb_start=PORTBOMB_START, portbomb_cadence=PORTBOMB_CADENCE,
                                 raf_fighters=RAF_FIGHTERS),
                 axis=axis, allied=ScriptedPolicy(attacker=Side.AXIS))
    assert fold(result.initial, result.events) == result.final, f"replay FAILED seed={seed}"
    return result, axis, _telemetry(result)


def _measure(*, live: bool, seeds: int, floor: bool, workers: int, tag: str) -> int:
    if live:
        _load_key()
    OUT.mkdir(exist_ok=True)
    cache_path = OUT / "siege_measure.cache.json"
    cache = json.loads(cache_path.read_text()) if (not live and cache_path.exists()) else {}

    def one(i: int):
        seats = _seat_clients(cache, live=live)
        result, axis, tel = _play(BASE_SEED + i, seats, floor)
        mark = "CRACK" if tel["crack"] else "held"
        print(f"    [{tag}] seed {BASE_SEED + i}: {mark} winner={tel['winner']} "
              f"eff0@t{tel['port_eff_zero_turn']} assaults={tel['axis_assaults']} "
              f"AL-ammo={tel['al_tobruk_ammo']} (peak {tel['al_tobruk_ammo_peak']}"
              f"->min {tel['al_tobruk_ammo_min']}) surr={tel['surrender_path']}", flush=True)
        return tel, axis.usage(), result

    with ThreadPoolExecutor(max_workers=workers) as ex:
        outs = list(ex.map(one, range(seeds)))

    tels = [t for t, _, _ in outs]
    usage = {k: sum(u.get(k, 0) for _, u, _ in outs)
             for k in ("calls", "failures", "prompt_tokens", "completion_tokens",
                       "cache_hits", "cache_misses")}
    cracks = sum(1 for t in tels if t["crack"])
    rate = round(100 * cracks / len(tels), 1)

    cache_path.write_text(json.dumps(cache))
    report = {"tag": tag, "model": MODEL, "seeds": seeds, "floor": floor,
              "schedule": {"portbomb_start": PORTBOMB_START, "portbomb_cadence": PORTBOMB_CADENCE,
                           "raf_fighters": RAF_FIGHTERS, "ferry_bomb": FERRY_BOMB},
              "cracks": cracks, "crack_rate_pct": rate, "usage": usage, "games": tels}
    (OUT / f"siege_measure.{tag}.json").write_text(json.dumps(report, indent=2))

    print(f"\n[{tag}] crack_rate = {cracks}/{seeds} = {rate}%  (floor={'ON' if floor else 'OFF'})")
    turn0s = [t["port_eff_zero_turn"] for t in tels if t["port_eff_zero_turn"] is not None]
    print(f"  port eff->0 turns: {sorted(turn0s)}")
    print(f"  AL-Tobruk ammo peak->final: "
          f"{sorted((t['al_tobruk_ammo_peak'], t['al_tobruk_ammo']) for t in tels)}")
    print(f"  AL-Tobruk final ammo: {sorted(t['al_tobruk_ammo'] for t in tels)}")
    # The garrison-dump DRAIN curve of the deepest-drained game -- the load-bearing signal: does
    # the sustained storm carry AL-Tobruk to 0 (the stage before the 15.15 fire) or plateau above?
    deep = min(tels, key=lambda t: t["al_tobruk_ammo_min"])
    per_turn = {}
    for p in deep["al_tobruk_ammo_traj"]:
        per_turn[p["turn"]] = p["ammo"]                 # last stage-reading of each game-turn
    print(f"  deepest-drain AL-Tobruk ammo curve (peak {deep['al_tobruk_ammo_peak']} -> "
          f"min {deep['al_tobruk_ammo_min']}), per game-turn:")
    print("    " + " ".join(f"T{k}:{v}" for k, v in sorted(per_turn.items())))
    print(f"  surrender paths: {[t['surrender_path'] for t in tels if t['surrender_path']]}")
    print(f"  convoy tons_lost (summed/game): {sorted(t['convoy_tons_lost'] for t in tels)}")
    print(f"  usage: model={MODEL} calls={usage['calls']} prompt_tok={usage['prompt_tokens']} "
          f"completion_tok={usage['completion_tokens']} failures={usage['failures']} "
          f"cache_hits={usage['cache_hits']} cache_misses={usage['cache_misses']}")

    # The money shot: the auto war-diary from the first game where Tobruk FALLS.
    fell = next((r for t, _, r in outs if t["crack"]), None)
    if fell is not None:
        print("\n  --- WAR DIARY (Tobruk FALLS) ---")
        for ln in narrator.diary(fell):
            print(f"    [{ln.beat}] T{ln.turn}: {ln.text}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="live measurement on the dev model")
    ap.add_argument("--recache", action="store_true", help="replay against the cache, model OFF")
    ap.add_argument("--seeds", type=int, default=16, help="number of seeds (4200..)")
    ap.add_argument("--no-floor", dest="floor", action="store_false",
                    help="storm floor OFF -- the model-only 'did the staff earn it' signal")
    ap.add_argument("--workers", type=int, default=5, help="concurrent games in flight")
    ap.add_argument("--tag", default=None, help="report label (defaults to floor/nofloor)")
    args = ap.parse_args()
    tag = args.tag or ("floor" if args.floor else "nofloor")
    if args.live:
        return _measure(live=True, seeds=args.seeds, floor=args.floor,
                        workers=args.workers, tag=tag)
    if args.recache:
        return _measure(live=False, seeds=args.seeds, floor=args.floor,
                        workers=args.workers, tag=tag)
    ap.error("pass --live or --recache")


if __name__ == "__main__":
    raise SystemExit(main())
