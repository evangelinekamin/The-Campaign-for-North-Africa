"""Unit tests for the crash-safe parallel leaderboard driver (scripts.run_leaderboard).

Every test is ZERO-token: the pure helpers (tiering, workers, resume-skip, card merge, rank
correlation) are exercised offline, and the pool's crash-safety + resume are proven with
fault-injected/failing commands -- no subprocess ever touches the network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import run_leaderboard as rl                              # noqa: E402


# --- roster + tiering ----------------------------------------------------------

def test_roster_is_23_models_with_gpt55_pro_excluded():
    assert len(rl.ROSTER) == 23
    assert len(set(rl.ROSTER)) == 23                       # no dupes
    assert "openai/gpt-5.5-pro" not in rl.ROSTER
    assert len(rl.FRONTIER) == 6 and len(rl.CHEAP_MID) == 17


def test_tiered_seed_counts():
    assert rl.seeds_for("anthropic/claude-opus-4.8") == 3      # frontier N=3
    assert rl.seeds_for("z-ai/glm-5.2") == 5                   # cheap/mid N=5


def test_workers_are_min_2n_8_and_openai_is_constrained():
    assert rl.workers_for("z-ai/glm-5.2") == 8                 # min(2*5, 8)
    assert rl.workers_for("anthropic/claude-opus-4.8") == 6    # min(2*3, 8)
    assert rl.workers_for("openai/gpt-5.5") == 2               # constrained lane
    assert rl.workers_for("openai/gpt-oss-120b:nitro") == 2    # gpt-oss is still OpenAI
    assert rl.is_openai("openai/gpt-5.4-mini") and not rl.is_openai("z-ai/glm-5.2")


def test_only_the_top_four_get_earned_crack():
    got = {m for m in rl.ROSTER if rl.wants_earned_crack(m)}
    assert got == {"anthropic/claude-opus-4.8", "openai/gpt-5.5",
                   "google/gemini-3.1-pro-preview", "anthropic/claude-sonnet-5"}


def test_safe_slug_and_command_shape():
    assert rl.safe_slug("openai/gpt-oss-120b:nitro") == "openai_gpt-oss-120b_nitro"
    cmd = rl.build_command("anthropic/claude-opus-4.8", Path("/o"), mock=False)
    assert "--live" in cmd and "--earned-crack" in cmd
    assert cmd[cmd.index("--seeds") + 1] == "3"
    assert cmd[cmd.index("--workers") + 1] == "6"
    assert cmd[cmd.index("--out") + 1].endswith("card_anthropic_claude-opus-4.8.json")
    # a non-top-4 model never asks for the floor-off pass, and --mock swaps the mode flag.
    cheap = rl.build_command("z-ai/glm-5.2", Path("/o"), mock=True)
    assert "--mock" in cheap and "--earned-crack" not in cheap


# --- resume-skip ---------------------------------------------------------------

def test_pending_models_skips_finished_cards(tmp_path):
    models = ["a/one", "b/two", "c/three"]
    rl.card_path(tmp_path, "b/two").write_text(json.dumps({"cards": []}))
    assert rl.pending_models(models, tmp_path) == ["a/one", "c/three"]


# --- card merge ----------------------------------------------------------------

def _card(model, **kw):
    base = {"model": model, "campaign": {"mean_score": 0.0, "mean_kill_ratio": 0.0,
            "reject_rate_pct": 0.0, "mean_advance_pct": 0.0, "mean_turn_invested": 0},
            "siege": {"crack_rate_pct": 0.0, "mean_ammo_min": None, "starved_fraction": 0.0},
            "cost": {"cost_per_game_usd": 0.0}}
    base["campaign"].update(kw.get("campaign", {}))
    base["siege"].update(kw.get("siege", {}))
    return base


def test_merge_cards_unions_all_card_files_ignoring_the_final(tmp_path):
    rl.card_path(tmp_path, "a/one").write_text(json.dumps({"cards": [_card("a/one")]}))
    rl.card_path(tmp_path, "b/two").write_text(json.dumps({"cards": [_card("b/two")]}))
    (tmp_path / "leaderboard_final.json").write_text(json.dumps({"cards": [_card("z/final")]}))
    models = {c["model"] for c in rl.merge_cards(tmp_path)}
    assert models == {"a/one", "b/two"}                    # final file is NOT globbed back in


def test_merge_cards_tolerates_a_corrupt_card_file(tmp_path):
    rl.card_path(tmp_path, "a/one").write_text(json.dumps({"cards": [_card("a/one")]}))
    rl.card_path(tmp_path, "b/bad").write_text("{ not json")
    assert {c["model"] for c in rl.merge_cards(tmp_path)} == {"a/one"}


# --- rank correlation ----------------------------------------------------------

def test_spearman_and_kendall_of_identical_orders_are_one():
    order = ["a", "b", "c", "d"]
    assert rl.spearman(order, order) == 1.0
    assert rl.kendall_tau(order, order) == 1.0


def test_spearman_and_kendall_of_reversed_orders_are_minus_one():
    a = ["a", "b", "c", "d"]
    assert rl.spearman(a, list(reversed(a))) == -1.0
    assert rl.kendall_tau(a, list(reversed(a))) == -1.0


def test_correlation_uses_only_the_common_models():
    # extra models on either side are ignored; the shared subsequence is identical -> rho 1.
    cna = ["x", "a", "b", "c"]
    generic = ["a", "b", "c", "y"]
    assert rl.spearman(cna, generic) == 1.0


def test_divergence_flags_over_and_under_performers():
    cna = ["good", "mid", "bad"]        # CNA order
    generic = ["bad", "mid", "good"]    # generic order (reversed)
    div = rl.divergence_report(cna, generic, top=2)
    top_over = div["overperformers"][0]
    top_under = div["underperformers"][0]
    # 'good' is CNA #1 but generic #3 -> over-performs at the wargame (divergence +2).
    assert top_over["model"] == "good" and top_over["divergence"] == 2
    # 'bad' is CNA #3 but generic #1 -> under-performs (divergence -2).
    assert top_under["model"] == "bad" and top_under["divergence"] == -2


def test_cna_ranking_orders_by_the_harness_rank_key():
    strong = _card("strong/model", campaign={"mean_score": 20.0})
    weak = _card("weak/model", campaign={"mean_score": 1.0})
    assert rl.cna_ranking([weak, strong]) == ["strong/model", "weak/model"]


def test_generic_ranking_file_covers_the_whole_roster():
    generic = rl.load_generic_ranking()
    assert set(generic) == set(rl.ROSTER)                  # every model is placed, no strays


# --- pool: crash-safety + resume (fault-injected, no network) ------------------

def _failing_cmd(_model, _out_dir, *, mock):
    return [sys.executable, "-c", "import sys; sys.exit(9)"]


def test_pool_survives_a_failing_model_and_runs_the_rest(tmp_path):
    # 'b/two' is force-failed via injection; the others run a trivial succeeding command.
    def build(model, out_dir, *, mock):
        return [sys.executable, "-c",
                f"import json,pathlib; pathlib.Path(r'{rl.card_path(out_dir, model)}')"
                f".write_text(json.dumps({{'cards': [{{'model': '{model}'}}]}}))"]

    models = ["a/one", "b/two", "c/three"]
    results = rl.run_pool(models, tmp_path, parallel=3, openai_parallel=1, mock=True,
                          timeout=30, log_path=tmp_path / "run.log", build_cmd=build,
                          fault={"b/two": [sys.executable, "-c", "import sys; sys.exit(1)"]})
    by = {r["model"]: r["status"] for r in results}
    assert by["a/one"] == "ok" and by["c/three"] == "ok"
    assert by["b/two"] == "exit_1"                         # failed but did NOT abort the pool
    assert rl.card_path(tmp_path, "a/one").exists()        # survivors wrote their cards


def test_pool_resume_skips_models_with_existing_cards(tmp_path):
    rl.card_path(tmp_path, "a/one").write_text(json.dumps({"cards": []}))
    ran = rl.run_pool(["a/one", "b/two"], tmp_path, parallel=2, openai_parallel=1, mock=True,
                      timeout=30, log_path=tmp_path / "run.log", build_cmd=_failing_cmd)
    # 'a/one' is skipped (card exists); only 'b/two' is attempted.
    assert [r["model"] for r in ran] == ["b/two"]
    log = (tmp_path / "run.log").read_text()
    assert "SKIP" in log and "a/one" in log
