"""The model-leaderboard harness (scripts.leaderboard): composes benchmark's degree-of-
success metric with measure_siege's crack-generalship telemetry into a per-model scorecard.

Every test here is ZERO-token: the scorecard is computed on the MockClient(_mock_staff)
path (the same deterministic stub the staff machine is proven on), so no API is ever
touched. The scorecard's shape, its crack-generalship signal, price lookup, and byte-for-
byte determinism are all exercised offline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import leaderboard as lb                                # noqa: E402
from scripts.benchmark import PRICES                                 # noqa: E402


def _card(seeds: int = 2, model: str = "mock/test", floor: bool = True) -> dict:
    """A scorecard computed on the free MockClient path (zero tokens)."""
    return lb.run_model(model, seeds, mock=True, live=False, floor=floor, cache={})


# --- the scorecard computes on a mock game (zero tokens) ----------------------

def test_scorecard_has_the_three_blocks_and_computes_on_a_mock_game():
    card = _card()
    assert set(card) >= {"model", "seeds", "floor", "campaign", "siege", "cost"}
    assert card["model"] == "mock/test" and card["seeds"] == 2

    # DEGREE-OF-SUCCESS on rommels_arrival (reused from benchmark._aggregate).
    cam = card["campaign"]
    for k in ("mean_score", "mean_advance_pct", "mean_turn_invested", "mean_kill_ratio",
              "reject_rate_pct", "mean_combat", "score_spread"):
        assert k in cam, f"campaign block missing {k}"
    assert 0 <= cam["mean_advance_pct"] <= 100
    # cost is reported ONCE, at the top level -- never duplicated inside the campaign block.
    assert "est_cost_usd" not in cam and "prompt_tokens" not in cam


def test_siege_block_carries_the_crack_generalship_signal():
    siege = _card()["siege"]
    for k in ("crack_rate_pct", "cracks", "starved_seeds", "starved_fraction",
              "ammo_min_reached", "mean_ammo_min", "surrender_paths", "seed_detail"):
        assert k in siege, f"siege block missing {k}"
    assert siege["seeds"] == 2 and len(siege["seed_detail"]) == 2
    # every per-seed row exposes the good-vs-timid telemetry: the ammo the storm drove the
    # garrison to, and whether that counts as genuine starvation.
    for row in siege["seed_detail"]:
        assert {"crack", "al_tobruk_ammo_peak", "al_tobruk_ammo_min", "starved",
                "surrender_path"} <= set(row)
    assert 0.0 <= siege["starved_fraction"] <= 1.0
    assert 0.0 <= siege["crack_rate_pct"] <= 100.0


def test_cost_is_tokens_and_dollars_and_zero_on_the_mock_path():
    cost = _card()["cost"]
    for k in ("calls", "prompt_tokens", "completion_tokens", "est_cost_usd",
              "cost_per_game_usd", "cache_hits", "cache_misses", "price_source"):
        assert k in cost
    # the free mock path spends nothing; an unpriced slug stays offline (no /models fetch).
    assert cost["prompt_tokens"] == 0 and cost["completion_tokens"] == 0
    assert cost["est_cost_usd"] == 0.0 and cost["cost_per_game_usd"] == 0.0
    assert cost["price_source"] == "unpriced"


# --- wall-clock timing: the dev-model pick is unreadable without speed --------

def test_scorecard_carries_a_timing_block():
    tm = _card()["timing"]
    for k in ("wall_seconds", "mean_minutes_per_game", "completion_tok_per_s"):
        assert k in tm, f"timing block missing {k}"
    assert tm["wall_seconds"] >= 0.0 and tm["mean_minutes_per_game"] >= 0.0
    # the free mock path emits zero completion tokens -> zero throughput, never /0.
    assert tm["completion_tok_per_s"] == 0.0


def test_timing_block_computes_minutes_per_game_and_tok_per_s():
    assert lb._timing_block(120.0, 4, 6000) == {
        "wall_seconds": 120.0,
        "mean_minutes_per_game": 0.5,    # 120s / 4 games / 60
        "completion_tok_per_s": 50.0,    # 6000 completion tokens / 120s
    }
    # zero elapsed / zero games never divides by zero.
    assert lb._timing_block(0.0, 0, 0)["completion_tok_per_s"] == 0.0


# --- engine SHA: cross-version comparability ----------------------------------

def test_scorecard_stamps_the_engine_sha():
    assert isinstance(lb.ENGINE_SHA, str) and lb.ENGINE_SHA
    assert _card()["engine_sha"] == lb.ENGINE_SHA


# --- earned-crack: the floor-OFF, no-scripted-help siege telemetry ------------

def test_earned_crack_is_none_unless_requested():
    assert _card()["earned_crack"] is None


def test_earned_crack_block_runs_the_floor_off_siege():
    card = lb.run_model("mock/test", 2, mock=True, live=False, floor=True,
                        earned_crack=True, cache={})
    ec = card["earned_crack"]
    assert ec is not None
    # same crack-generalship shape as the floored siege summary.
    for k in ("crack_rate_pct", "cracks", "starved_fraction", "seed_detail"):
        assert k in ec, f"earned_crack block missing {k}"
    assert len(ec["seed_detail"]) == 2


# --- determinism: the mock scorecard is byte-identical run to run -------------

def _stable(card: dict) -> str:
    """Serialise the gameplay-bearing scorecard, dropping the inherently non-deterministic
    wall-clock timing block."""
    trimmed = {k: v for k, v in card.items() if k != "timing"}
    return json.dumps(trimmed, sort_keys=True)


def test_mock_scorecard_is_deterministic():
    assert _stable(_card()) == _stable(_card())


# --- the STARVED classifier (good general vs timid) ---------------------------

def test_starved_classifier_keys_on_the_floor():
    # a garrison driven below STARVE_FLOOR is genuinely starved (the good general); one left
    # on a high plateau (the mercury-2 timid failure, ~2200 RISING) is NOT.
    assert lb._starved({"al_tobruk_ammo_min": 0})
    assert lb._starved({"al_tobruk_ammo_min": lb.STARVE_FLOOR})
    assert not lb._starved({"al_tobruk_ammo_min": lb.STARVE_FLOOR + 1})
    assert not lb._starved({"al_tobruk_ammo_min": 2200})     # timid plateau
    assert not lb._starved({"al_tobruk_ammo_min": None})     # garrison gone / no reading


def test_siege_summary_counts_cracks_and_starvation():
    tels = [
        {"crack": True, "winner": "AXIS", "port_eff_zero_turn": 6, "axis_assaults": 9,
         "al_tobruk_ammo": 0, "al_tobruk_ammo_peak": 2300, "al_tobruk_ammo_min": 0,
         "surrender_path": "15.15"},
        {"crack": False, "winner": "ALLIED", "port_eff_zero_turn": 7, "axis_assaults": 3,
         "al_tobruk_ammo": 2200, "al_tobruk_ammo_peak": 2200, "al_tobruk_ammo_min": 1600,
         "surrender_path": None},
    ]
    s = lb._siege_summary(tels)
    assert s["cracks"] == 1 and s["crack_rate_pct"] == 50.0
    assert s["starved_seeds"] == 1 and s["starved_fraction"] == 0.5
    assert s["ammo_min_reached"] == 0                    # the deepest drive toward 0
    assert s["surrender_paths"] == {"15.15": 1}


# --- price lookup: PRICES first, then the OpenRouter catalogue -----------------

def test_price_for_known_slug_uses_prices_offline():
    slug = next(iter(PRICES))
    called = {"n": 0}

    def fake_fetch(_model):
        called["n"] += 1
        return (9.9, 9.9)

    price, source = lb._price_for(slug, fetch=fake_fetch)
    assert price == PRICES[slug] and source == "PRICES"
    assert called["n"] == 0                              # a curated slug never hits the network


def test_price_for_unknown_slug_falls_back_to_the_catalogue():
    price, source = lb._price_for("no-such/model-xyz", fetch=lambda m: (1.5, 6.0))
    assert price == (1.5, 6.0) and source == "openrouter"


def test_cost_block_prices_tokens_from_the_curated_table():
    slug = "anthropic/claude-haiku-4.5"                  # (1.00, 5.00) per 1M in PRICES
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "calls": 4}
    cost = lb._cost_block(slug, usage, games=8)
    assert cost["price_source"] == "PRICES"
    assert cost["est_cost_usd"] == 6.0                   # 1.00 + 5.00
    assert cost["cost_per_game_usd"] == 0.75             # 6.0 / 8


# --- multi-axis grading: the leaderboard DISCRIMINATES when the single score collapses ---

def _profile(model, *, score, crack, kill, reject, ammo, advance, invT):
    """A synthetic scorecard shell carrying only the axes _rank_key / leaderboard read."""
    return {
        "model": model,
        "campaign": {"mean_score": score, "mean_kill_ratio": kill, "reject_rate_pct": reject,
                     "mean_advance_pct": advance, "mean_turn_invested": invT},
        "siege": {"crack_rate_pct": crack, "mean_ammo_min": ammo, "starved_fraction": 0.0},
        "cost": {"cost_per_game_usd": 0.0},
    }


def test_multi_axis_rank_separates_a_good_general_from_a_mauled_advancer():
    # Both collapse to a headline score of 0 (the wall-of-zeros the owner fears). A GOOD general
    # cracked the siege, killed more than it lost, kept discipline, and drove the garrison to 0.
    # A MAULED ADVANCER marched furthest of all but into a massacre: net-negative combat, high
    # reject, garrison left on a high plateau. The multi-axis rank must still separate them.
    good = _profile("good/general", score=0.0, crack=100.0, kill=1.4, reject=2.0,
                    ammo=0, advance=60.0, invT=5.0)
    mauled = _profile("mauled/advancer", score=0.0, crack=0.0, kill=0.4, reject=55.0,
                      ammo=2200, advance=99.0, invT=2.0)

    assert lb._rank_key(good) > lb._rank_key(mauled)     # good outranks despite identical score 0
    order = sorted([mauled, good], key=lb._rank_key, reverse=True)
    assert [c["model"] for c in order] == ["good/general", "mauled/advancer"]
    # advancing furthest must NOT buy the top rank -- we do not pay for marching into a massacre.
    assert mauled["campaign"]["mean_advance_pct"] > good["campaign"]["mean_advance_pct"]


def test_leaderboard_prints_and_ranks_without_error(capsys):
    good = _profile("good/general", score=0.0, crack=100.0, kill=1.4, reject=2.0,
                    ammo=0, advance=60.0, invT=5.0)
    mauled = _profile("mauled/advancer", score=0.0, crack=0.0, kill=0.4, reject=55.0,
                      ammo=2200, advance=99.0, invT=2.0)
    lb.leaderboard([mauled, good])
    out = capsys.readouterr().out
    assert "multi-axis" in out
    assert out.index("good/general") < out.index("mauled/advancer")   # good printed first


# --- throughput: per-process cache files fold back losslessly ---------------------

def test_merge_caches_unions_per_process_files(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    dest = tmp_path / "shared.json"
    a.write_text(json.dumps({"k1": "v1"}))
    b.write_text(json.dumps({"k2": "v2"}))
    merged = lb.merge_caches([str(a), str(b), str(tmp_path / "missing.json")], str(dest))
    assert merged == {"k1": "v1", "k2": "v2"}            # union; missing file skipped
    assert json.loads(dest.read_text()) == {"k1": "v1", "k2": "v2"}


def test_cache_cli_arg_is_honored(tmp_path, monkeypatch):
    # --mock never writes a cache, but the arg must parse and thread through without touching the
    # default out/leaderboard.cache.json. Prove wiring by driving main() with a custom --cache.
    out = tmp_path / "lb.json"
    cache = tmp_path / "own.cache.json"
    monkeypatch.setattr(sys, "argv", ["leaderboard", "--mock", "--seeds", "1",
                                      "--models", "mock/test",
                                      "--cache", str(cache), "--out", str(out)])
    assert lb.main() == 0
    assert out.exists() and json.loads(out.read_text())["cards"][0]["model"] == "mock/test"


def test_merge_caches_cli_exits_after_folding(tmp_path, monkeypatch):
    a = tmp_path / "a.json"
    dest = tmp_path / "dest.json"
    a.write_text(json.dumps({"kx": "vx"}))
    monkeypatch.setattr(sys, "argv", ["leaderboard", "--merge-caches", str(a),
                                      "--cache", str(dest)])
    assert lb.main() == 0                                # returns without needing --mock/--live
    assert json.loads(dest.read_text()) == {"kx": "vx"}
