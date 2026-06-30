"""Synthesize the 68 Haiku section reviews into a single QA report markdown."""
import json
from collections import Counter, defaultdict

TASK_OUT = "/tmp/claude-1000/-home-eve-Projects-tcfnatdw-tmp/b04e8c52-b660-4bec-9ad9-936b04febcce/tasks/w4ywnnw2k.output"
REPORT = "/home/eve/Projects/tcfnatdw/docs/OCR-QA-REPORT.md"

obj = json.load(open(TASK_OUT))
data = obj["result"]


def review_of(d):
    r = d.get("review")
    if isinstance(r, str):
        try:
            return json.loads(r)
        except Exception:
            return None
    return r


rows, issues = [], []
for d in data:
    r = review_of(d) or {}
    verdict = r.get("verdict", "unparsed")
    iss = [i for i in (r.get("issues") or []) if isinstance(i, dict)]
    rows.append({"slug": d["slug"], "title": d.get("title", ""), "verdict": verdict,
                 "one_line": (r.get("one_line") or "").strip(), "n": len(iss)})
    for i in iss:
        issues.append({"slug": d["slug"], **i})

verdicts = Counter(r["verdict"] for r in rows)
sev = Counter(i.get("severity") for i in issues)
typ = Counter(i.get("type") for i in issues)
ORDER = {"clean": 0, "minor": 1, "significant": 2, "unparsed": 3}
SEVRANK = {"high": 0, "med": 1, "low": 2}

L = []
w = L.append
w("# OCR QA Report — The Campaign for North Africa")
w("")
w("Automated quality review of the machine-OCR'd rulebook. Every section (and the "
  "charts appendix) was read by an independent reviewer and judged for coherence, "
  "OCR garbles, broken numbers, structural problems, and table integrity.")
w("")
w("> **Bottom line:** the rules prose is solid and usable. Of 68 sections, "
  f"**{verdicts['clean']} are clean, {verdicts['minor']} have only minor issues, and "
  f"{verdicts['significant']} have at least one significant issue** — almost all of "
  "which are recoverable OCR typos a human reader corrects on sight (e.g. *Asis*→Axis, "
  "*Beniheim*→Blenheim). A handful are real structural problems worth a targeted fix "
  "(listed below). For exact numbers in dense charts, the original scan remains the "
  "source of truth.")
w("")
w("## Health at a glance")
w("")
w("| Verdict | Sections | Meaning |")
w("| --- | --- | --- |")
w(f"| clean | {verdicts['clean']} | Reads well; at most trivial typos. |")
w(f"| minor | {verdicts['minor']} | A few low/medium issues; fully usable. |")
w(f"| significant | {verdicts['significant']} | At least one high-severity garble/structure issue. |")
w("")
w(f"**{len(issues)} issues** flagged in total — "
  f"{sev['high']} high, {sev['med']} medium, {sev['low']} low. "
  f"By type: {typ['ocr_garble']} OCR garbles, {typ['structure']} structural, "
  f"{typ['table']} table, {typ['broken_number']} number, {typ['truncation']} truncation, "
  f"{typ.get('other',0)} other.")
w("")
w("## How to read this")
w("")
w("- **OCR garbles** (by far the most common) are misread letters/words — *Navel*→Naval, "
  "*sucn*→such, *In-ative*→Initiative. They don't change rules logic and are obvious in context.")
w("- **Table pointers** flagged as \"missing data\" (e.g. *7.2 Initiative Ratings Chart "
  "(see Separate Sheets)*) are **by design** — the 1979 rulebook prints those values on "
  "separate chart sheets, which are captured in the **Charts, Tables & Play Aids** section "
  "(`rules/90-charts-tables-and-play-aids.md`). Not an OCR failure.")
w("- **Structural** issues (mis-numbered cases, spliced/jumbled content) are the ones worth "
  "a real fix — they're listed in their own section below.")
w("- **Dense reference charts** (CRTs, unit-characteristics) were recovered as markdown where "
  "OCR was reliable; a few remain pointers to the scan. Always verify exact chart values "
  "against the original PDF before relying on them for adjudication.")
w("")

w("## Corrections already applied")
w("")
w("All of the report's recommended next steps have been carried out and the docs rebuilt:")
w("")
w("- **~130 OCR typos corrected** across two passes — faction/term/aircraft/place garbles "
  "(*Asis*→Axis, *Navel*→Naval, *Beniheim*→Blenheim, *Mel09*→Me109, *crusiers*→cruisers, "
  "*Valetta*→Valletta, *In-ative*→Initiative, *Mirsielles*→Marseille, *birds*→birs, "
  "*Sidi Birani/Baranni*→Sidi Barrani, *Bobrida*→Bardia, …) plus scoped grammar fixes "
  "(*rot use*→not use, *Such tangs*→tanks, *no 20C*→no ZOC, …). Every change was logged.")
w("- **LaTeX/notation artifacts cleaned** — the model's math rendering of counter symbols "
  "and fractions (`\\frac{1}{2}`→1/2, `\\xrightarrow{xx}`→xx, `\\boxed{1}`→[1], "
  "`\\dagger`→†, `^{E}`→E) is gone; 0 remain. The garbled dice-read notation became "
  "*10's figure / 1's figure*, and the §11.32 combat formula now correctly divides "
  "(`÷ 10`).")
w("- **Case-number corruptions fixed** — §47.7/47.8 (were `[42.7]/[42.8]`), §52.3 OASES "
  "(was `[53.]`), and a §38.39 cross-reference (was a LaTeX-garbled `Case 38.35`).")
w("- **§54 Supply Co-ordination de-spliced** — pages 70–73 are a 4-page reference-chart "
  "insert (Terrain Effects, Air/Land/Road Distance charts) bound mid-rules; they are now "
  "routed to the charts appendix, so §54 reads continuously (54.14 → 54.15).")
w("- **Page 108** (looped garbage) is a clean pointer; **4 sideways charts** were re-OCR'd "
  "upright into real tables.")
w("")
w("**Two items could not be auto-resolved** (no recoverable value in the scan-less text) "
  "and are left for manual lookup against the original:")
w("")
w("- `see Case 00.00` in **[27.88]** (the LRDG \"removed from physical sight\" rule) and in "
  "**[30.5]** (sea transport of supplies) — the real case numbers were illegible to OCR.")
w("- A handful of **place-name/number ambiguities** the reviewers flagged where the correct "
  "value needs the scan (e.g. *Scledima/Scledelima*, author-name spellings, a few chart "
  "values noted below).")
w("")
w("Everything in the sections below is what the reviewers found *before* these fixes — kept "
  "for the record. The verdict tallies therefore reflect the pre-fix state.")
w("")

# Structural / high-value issues first
w("## Structural issues worth a targeted fix")
w("")
w("These genuinely affect navigation or meaning (not just a typo):")
w("")
struct = [i for i in issues if i.get("type") in ("structure", "truncation")
          and i.get("severity") == "high"]
for i in struct:
    w(f"- **[{i['slug']}]** `{i.get('location','')}` — {i.get('detail','').strip()}")
w("")

# All high-severity, grouped by type
w("## All high-severity findings")
w("")
by_type = defaultdict(list)
for i in issues:
    if i.get("severity") == "high":
        by_type[i.get("type")].append(i)
TYPE_LABEL = {"ocr_garble": "OCR garbles (clear misreads)",
              "broken_number": "Broken numbers / notation",
              "structure": "Structure & case-numbering",
              "table": "Table integrity",
              "truncation": "Truncated text", "other": "Other"}
for t in ["ocr_garble", "broken_number", "structure", "table", "truncation", "other"]:
    if not by_type.get(t):
        continue
    w(f"### {TYPE_LABEL[t]}")
    w("")
    for i in by_type[t]:
        w(f"- **[{i['slug']}]** `{i.get('location','')}` — {i.get('detail','').strip()}")
    w("")

# Per-section table
w("## Per-section verdicts")
w("")
w("| Section | Verdict | Issues | Reviewer note |")
w("| --- | --- | --- | --- |")
for r in sorted(rows, key=lambda x: (ORDER.get(x["verdict"], 9), x["slug"])):
    note = r["one_line"].replace("|", "\\|")
    if len(note) > 160:
        note = note[:157] + "..."
    w(f"| `{r['slug']}` | {r['verdict']} | {r['n']} | {note} |")
w("")
w("## Status of the recommended next steps")
w("")
w("1. ~~Safe global typo fixes~~ — **done** (~130 corrections, logged).")
w("2. ~~Fix case-numbering corruptions~~ — **done** for §47.7/47.8 and §52.3; the two "
  "`see Case 00.00` references remain (illegible in OCR — need the scan).")
w("3. ~~Re-knit §54~~ — **done** (chart insert routed to the appendix).")
w("4. ~~Pointer the page-108 garbage~~ — **done**.")
w("5. **Spot-verify dense charts** (CRTs, unit-characteristics, terrain effects) against the "
  "original scan before using exact values in the game engine — this remains a human step; "
  "OCR of dense grids is good but not guaranteed cell-perfect.")
w("")
w("*Generated from 68 independent section reviews; corrections applied and verified afterward.*")

open(REPORT, "w").write("\n".join(L) + "\n")
print(f"wrote {REPORT} ({len(L)} lines)")
print(f"verdicts={dict(verdicts)} issues={len(issues)} high={sev['high']}")
