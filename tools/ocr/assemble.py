"""Assemble cleaned per-page OCR into a full rules document plus a per-chapter
split, written into the project's docs/ tree.

Output layout:
    docs/The Campaign for North Africa - Rules.md   (full document, with TOC)
    docs/rules/00-front-matter.md
    docs/rules/01-introduction.md
    docs/rules/...                                   (one file per Major Section)
    docs/rules/99-charts-and-tables.md              (back-of-book foldout charts)
    docs/rules/README.md                            (chapter index)

Chapters are the SPI "Major Sections" (N.0), detected as level-1 headings emitted
by postprocess.clean_page. Pages at/after APPENDIX_FROM are the oversized foldout
charts and are routed to an appendix rather than mixed into the rules prose.
"""
import glob
import os
import re
import sys

from postprocess import clean_page, is_foldout, foldout_pointer
import tables

OUT_DIR = sys.argv[1]                                   # per-page .md dir
DOCS = sys.argv[2]                                      # docs/ root
APPENDIX_FROM = int(sys.argv[3]) if len(sys.argv) > 3 else 180
OCR_DATE = "2026-06-28"

RULES_DIR = os.path.join(DOCS, "rules")
os.makedirs(RULES_DIR, exist_ok=True)

CHAPTER_RE = re.compile(r"^# (\d{1,2})\.0\s+(.+)$")
PAGEBREAK = "\x00PAGEBREAK\x00"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def page_no(path):
    return int(os.path.basename(path).replace("page-", "").replace(".md", ""))


def read_elements():
    """Ordered stream of (page_no, chunk). PAGEBREAK chunks mark page starts;
    a leading HTML banner comment (chart pages) is preserved as its own chunk."""
    elements = []
    has_table = {}
    last_section_page = 0
    for pf in sorted(glob.glob(os.path.join(OUT_DIR, "page-*.md")), key=page_no):
        n = page_no(pf)
        raw = open(pf).read()
        elements.append((n, PAGEBREAK))
        if is_foldout(raw):
            elements.append((n, foldout_pointer(raw, n)))
            has_table[n] = True
            continue
        chunks, chapters, _bad = clean_page(raw, n)
        elements.extend((n, c) for c in chunks)
        if chapters:
            last_section_page = max(last_section_page, n)
        has_table[n] = bool(tables.TABLE_RE.search(raw))
    # The rules prose ends at the last page bearing a Major Section; the back-matter
    # (charts, tables, play aids) begins at the first table-bearing page after that.
    back_matter_from = next(
        (n for n in sorted(has_table) if n > last_section_page and has_table[n]),
        APPENDIX_FROM)
    return elements, back_matter_from


# Pages 70-73 are a 4-page reference-chart insert (Terrain Effects, Air/Land/Road
# Distance charts, etc.) physically bound into the middle of the logistics rules.
# They carry no [54.x] content, so routing them to the charts appendix lets section
# 54 read continuously (54.14 -> 54.15) instead of being split by the insert.
CHART_INSERT_PAGES = {70, 71, 72, 73}


def bucketize(elements, back_matter_from):
    """Split the element stream into ordered buckets: front matter, one per Major
    Section, a back-matter charts/tables/examples part, and the foldout appendix."""
    front = {"slug": "00-front-matter", "title": "Front Matter", "els": []}
    backmatter = {"slug": "90-charts-tables-and-play-aids",
                  "title": "Charts, Tables & Play Aids", "els": []}
    appendix = {"slug": "99-foldout-charts",
                "title": "Fold-out Charts (oversized)", "els": []}
    buckets = [front]
    current = front
    for n, chunk in elements:
        if n >= APPENDIX_FROM:
            appendix["els"].append((n, chunk))
            continue
        if n >= back_matter_from or n in CHART_INSERT_PAGES:
            backmatter["els"].append((n, chunk))
            continue
        m = CHAPTER_RE.match(chunk) if chunk != PAGEBREAK else None
        if m:
            sec, name = m.group(1), m.group(2).strip()
            current = {"slug": f"{int(sec):02d}-{slugify(name)}",
                       "title": f"{sec}.0 {name}", "els": []}
            buckets.append(current)
        current["els"].append((n, chunk))
    if backmatter["els"]:
        buckets.append(backmatter)
    if appendix["els"]:
        buckets.append(appendix)
    return buckets


def render(els, with_page_anchors=True):
    parts = []
    for n, chunk in els:
        if chunk == PAGEBREAK:
            if with_page_anchors:
                parts.append(f"<!-- page {n:03d} -->")
            continue
        parts.append(chunk)
    return "\n\n".join(parts).strip() + "\n"


def main():
    elements, back_matter_from = read_elements()
    buckets = bucketize(elements, back_matter_from)
    total_pages = len({n for n, _ in elements})

    # Table of contents over Major Sections.
    toc = ["## Contents", ""]
    for b in buckets:
        label = b["title"]
        toc.append(f"- [{label}](rules/{b['slug']}.md)")
    toc_md = "\n".join(toc)

    preamble = (
        "# The Campaign for North Africa — Rules of Play\n\n"
        "*The Desert War 1940–43 — Land Game. Simulations Publications, Inc. (SPI), 1979.*\n\n"
        "> Machine-OCR of the original 192-page scanned rulebook, produced with "
        f"`baidu/Unlimited-OCR` on {OCR_DATE}. Layout was reconstructed from the model's "
        "block labels; the SPI Case System numbering (N.0 Major Section, N.M Primary Case, "
        "N.MM Secondary Case) drives the headings and the per-chapter split under `rules/`. "
        "Back-of-book foldout charts were downscaled before OCR and are best-effort — consult "
        "the original scan for exact chart values. Faithful but imperfect; cite the original "
        "for rules adjudication.\n"
    )

    # Full document.
    body = "\n\n".join(render(b["els"]) for b in buckets)
    full = preamble + "\n" + toc_md + "\n\n---\n\n" + body
    full_path = os.path.join(DOCS, "The Campaign for North Africa - Rules.md")
    with open(full_path, "w") as f:
        f.write(full)

    # Per-chapter files.
    index = ["# The Campaign for North Africa — Rules (by chapter)", "",
             f"OCR of the 1979 SPI rulebook ({total_pages} pages). "
             "[Full document](../The%20Campaign%20for%20North%20Africa%20-%20Rules.md).", ""]
    for i, b in enumerate(buckets):
        nav = []
        if i > 0:
            nav.append(f"[← {buckets[i-1]['title']}]({buckets[i-1]['slug']}.md)")
        if i < len(buckets) - 1:
            nav.append(f"[{buckets[i+1]['title']} →]({buckets[i+1]['slug']}.md)")
        nav_line = " · ".join(nav)
        header = f"<!-- {b['title']} -->\n"
        chapter_md = header + render(b["els"])
        if nav_line:
            chapter_md += f"\n---\n{nav_line}\n"
        with open(os.path.join(RULES_DIR, f"{b['slug']}.md"), "w") as f:
            f.write(chapter_md)
        index.append(f"- [{b['title']}]({b['slug']}.md)")

    with open(os.path.join(RULES_DIR, "README.md"), "w") as f:
        f.write("\n".join(index) + "\n")

    print(f"pages={total_pages} chapters={len(buckets)} "
          f"(incl front matter{', appendix' if buckets[-1]['slug'].startswith('99') else ''})")
    print(f"full -> {full_path}")
    for b in buckets:
        words = len(render(b["els"]).split())
        print(f"  {b['slug']:<34} {b['title'][:48]:<48} ~{words} words")


if __name__ == "__main__":
    main()
