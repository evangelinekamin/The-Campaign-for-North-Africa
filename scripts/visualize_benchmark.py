"""Visualise benchmark_results.json (from scripts.benchmark).

Prints a terminal report -- leaderboard, an advance-% bar chart, a cost-efficiency
table (advance per dollar), and each model's advance spread across games -- and
writes a self-contained HTML report (no dependencies) for a nicer view.

    python3 -m scripts.visualize_benchmark benchmark_results.json
    python3 -m scripts.visualize_benchmark benchmark_results.json --html report.html
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

BAR = "█"


def _bar(value: float, vmax: float, width: int = 30) -> str:
    n = int(round(width * value / vmax)) if vmax else 0
    return BAR * n + " " * (width - n)


def terminal_report(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: r["mean_advance_pct"], reverse=True)

    print("\n" + "=" * 74)
    print("  ROMMEL'S ARRIVAL -- LLM AXIS BENCHMARK  (degree-of-success: advance %)")
    print("=" * 74)

    print("\nDEGREE OF SUCCESS  (mean Axis advance toward Tobruk)")
    vmax = max((r["mean_advance_pct"] for r in rows), default=100) or 100
    for r in rows:
        print(f"  {r['model']:<30} |{_bar(r['mean_advance_pct'], vmax)}| {r['mean_advance_pct']:>4}%"
              f"  (best {r['best_advance_pct']})")

    print("\nCOST EFFICIENCY  (advance % per US$ / game -- higher = better value)")
    print(f"  {'model':<30}{'adv%':>6}{'$/game':>9}{'adv/$':>10}")
    print("  " + "-" * 53)
    for r in sorted(rows, key=lambda r: (r["mean_advance_pct"] / r["cost_per_game_usd"]
                                         if r["cost_per_game_usd"] else 9e9), reverse=True):
        eff = r["mean_advance_pct"] / r["cost_per_game_usd"] if r["cost_per_game_usd"] else float("inf")
        eff_s = f"{eff:>10.0f}" if eff != float("inf") else f"{'free':>10}"
        print(f"  {r['model']:<30}{r['mean_advance_pct']:>6}{r['cost_per_game_usd']:>9}{eff_s}")

    print("\nDECISION QUALITY & COMBAT")
    print(f"  {'model':<30}{'reject%':>8}{'kill':>7}{'assaults':>10}{'calls':>7}")
    print("  " + "-" * 62)
    for r in rows:
        print(f"  {r['model']:<30}{r['reject_rate_pct']:>8}{r['mean_kill_ratio']:>7}"
              f"{r['mean_close_assaults']:>10}{r['llm_calls']:>7}")

    print("\nCONSISTENCY  (advance spread across games: min .. mean .. max)")
    for r in rows:
        adv = sorted(g["advance_pct"] for g in r.get("games_detail", []))
        if not adv:
            continue
        lo, hi = adv[0], adv[-1]
        span = 40
        a = int(span * lo / 100); b = max(a + 1, int(span * hi / 100))
        line = [" "] * span
        for i in range(a, min(b, span)):
            line[i] = "─"
        m = min(span - 1, int(span * r["mean_advance_pct"] / 100)); line[m] = "◆"
        print(f"  {r['model']:<30} {lo:>3} |{''.join(line)}| {hi:<3}")
    print()


def html_report(rows: list[dict], path: str) -> None:
    rows = sorted(rows, key=lambda r: r["mean_advance_pct"], reverse=True)
    vmax = max((r["mean_advance_pct"] for r in rows), default=100) or 100

    def cell(r):
        w = 100 * r["mean_advance_pct"] / vmax
        return (f'<tr><td>{html.escape(r["model"])}</td>'
                f'<td class="bar"><div style="width:{w:.0f}%"></div>'
                f'<span>{r["mean_advance_pct"]}%</span></td>'
                f'<td>{r["best_advance_pct"]}</td><td>{r["mean_kill_ratio"]}</td>'
                f'<td>{r["reject_rate_pct"]}%</td><td>{r["mean_close_assaults"]}</td>'
                f'<td>${r["cost_per_game_usd"]}</td><td>{r["llm_calls"]}</td></tr>')

    doc = f"""<!doctype html><meta charset=utf-8>
<title>CNA LLM Benchmark</title>
<style>
 body{{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;color:#1a1a1a}}
 h1{{font-size:1.4rem}} .sub{{color:#666}}
 table{{border-collapse:collapse;width:100%;margin-top:1rem}}
 th,td{{padding:.5rem .6rem;border-bottom:1px solid #eee;text-align:right}}
 th:first-child,td:first-child{{text-align:left;font-weight:600}}
 td.bar{{position:relative;width:38%}}
 td.bar div{{background:linear-gradient(90deg,#c0392b,#e67e22);height:1.1rem;border-radius:3px}}
 td.bar span{{position:absolute;right:.4rem;top:.15rem;font-size:.8rem;color:#fff;mix-blend-mode:difference}}
 caption{{text-align:left;color:#666;font-size:.85rem;margin-bottom:.3rem}}
</style>
<h1>The Campaign for North Africa &mdash; LLM Axis Benchmark</h1>
<p class=sub>Each model commands the Axis on Rommel's Arrival vs a scripted Commonwealth
defence. The scenario is faithfully Axis-hard (Tobruk historically held), so the score
is <b>degree of success</b> &mdash; how far the Axis advanced toward Tobruk (0&ndash;100%).</p>
<table>
<caption>Sorted by mean advance %. kill = enemy-steps-lost per own-step-lost; reject% = share of Axis orders the engine refused (lower = better rules grasp).</caption>
<tr><th>model</th><th>mean advance</th><th>best</th><th>kill</th><th>reject%</th><th>assaults</th><th>$/game</th><th>calls</th></tr>
{''.join(cell(r) for r in rows)}
</table>"""
    Path(path).write_text(doc)
    print(f"wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="?", default="benchmark_results.json")
    ap.add_argument("--html")
    args = ap.parse_args()
    rows = json.loads(Path(args.results).read_text())["rows"]
    terminal_report(rows)
    if args.html:
        html_report(rows, args.html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
