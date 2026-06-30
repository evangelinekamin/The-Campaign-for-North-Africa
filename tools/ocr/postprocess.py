"""Turn raw Unlimited-OCR `document parsing.` output into clean markdown.

The raw format is a flat sequence of layout blocks:
    <|det|>LABEL [x1, y1, x2, y2]<|/det|>CONTENT
with LABEL in {title, text, page_number, table, ...}. We strip the bbox tags,
use the labels to rebuild headings vs paragraphs, and use the SPI Case System
numbering (N.0 major section, N.M primary case, N.MM secondary case) to assign
heading levels and to find chapter boundaries.

Tables are handled per-block by tables.py: a table is converted to clean markdown
when it OCR'd reliably, or replaced by a pointer to the original scan when it did
not. Foldout pages (whose text is itself garbage) collapse to a pointer.
"""
import re
import glob
import os
from collections import Counter

import tables

BLOCK_RE = re.compile(
    r"<\|det\|>\s*(?P<label>\w+)\s*\[[^\]]*\]\s*<\|/det\|>(?P<content>.*?)(?=<\|det\|>|\Z)",
    re.DOTALL,
)
BRACKET_HEAD_RE = re.compile(r"^\[(\d{1,2})\.(\d{1,2})\]\s*(.*)$")
OUTLINE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\b\s*(.*)$")
MAJOR_ANY_RE = re.compile(r"^\[(\d{1,2})\.0\]\s+([A-Z][A-Za-z0-9 /&(),.'\-]{1,80})$")
FOLDOUT_DIM_RE = re.compile(r"oversized\s+(\d+)x(\d+)")


def _md_safe(text):
    """Escape a leading markdown-special character so OCR'd prose is not parsed as
    a heading/quote/list. Chart legends define symbols like '# = Number of ...'."""
    return re.sub(r"^(\s*)([#>|]|[-*+](?=\s)|\d+(?=\.\s))", r"\1\\\2", text)


def _collapse(text):
    """Join wrapped lines inside a layout box into one logical line, healing the
    end-of-line hyphenation produced by justified scans."""
    text = text.strip()
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _repetition(text):
    """Fraction of 5-grams equal to the single most common one (loop signal)."""
    words = text.split()
    if len(words) < 60:
        return 0.0
    grams = [" ".join(words[i:i + 5]) for i in range(len(words) - 5)]
    return Counter(grams).most_common(1)[0][1] / len(grams)


def render_title(content):
    """Render a title block as a markdown line. Returns (line, section_key) where
    section_key is "N.0" when this opens a Major Section (a chapter), else None."""
    one = _collapse(content)
    m = BRACKET_HEAD_RE.match(one)
    if m:
        sec, sub, rest = m.group(1), m.group(2), m.group(3).strip()
        num = f"{sec}.{sub}"
        if sub == "0":
            return f"# {num} {rest}".rstrip(), f"{sec}.0"
        if len(sub) == 1:
            return f"## {num} {rest}".rstrip(), None
        return f"### {num} {rest}".rstrip(), None
    if OUTLINE_RE.match(one):
        return f"- {one}", None
    return f"### {one}", None


def _bad_table_pointer(page_no):
    return (f"> **Dense chart/table — see PDF page {page_no}.** This grid did not "
            f"OCR cleanly enough to reproduce reliably here; consult the original "
            f"scan for exact values.")


def is_foldout(raw):
    return bool(re.match(r"\s*<!--\s*large foldout", raw))


def foldout_pointer(raw, page_no):
    dim = FOLDOUT_DIM_RE.search(raw)
    wh = f' (~{int(dim.group(1))//300}"×{int(dim.group(2))//300}")' if dim else ""
    # Keep any short, non-repetitive title the model recovered.
    titles = [_collapse(c) for lbl, c in ALL_BLOCKS_RE.findall(raw)
              if lbl in ("title", "text") and 0 < len(_collapse(c)) < 70
              and _repetition(_collapse(c)) < 0.1]
    named = next((t for t in titles if "CHART" in t.upper() or "TABLE" in t.upper()),
                 None)
    head = f"### Chart — {named}" if named else f"### Large fold-out chart{wh} (page {page_no})"
    return (f"{head}\n\n<!-- page {page_no:03d}: oversized foldout; not OCR-able -->\n\n"
            f"> Oversized fold-out chart{wh}. **See the original scan (PDF page "
            f"{page_no}) for contents.**")


ALL_BLOCKS_RE = BLOCK_RE


def clean_page(raw, page_no=0):
    """Convert one raw page into (chunks, chapters, bad_tables).
      chunks       - ordered markdown strings for this page
      chapters     - [(key, title)] Major Sections that begin on this page
      bad_tables   - [{page, metrics}] tables that failed to OCR cleanly
    """
    out, chapters, bad = [], [], []
    for m in BLOCK_RE.finditer(raw):
        label, content = m.group("label"), m.group("content")
        if not content.strip() or label == "page_number":
            continue

        if label == "table" or "<table" in content.lower():
            for thtml in tables.TABLE_RE.findall(content):
                grid = tables.parse_grid(thtml)
                good, metrics = tables.score_grid(grid)
                if good:
                    out.append(tables.to_markdown(grid))
                else:
                    out.append(_bad_table_pointer(page_no))
                    bad.append({"page": page_no, "metrics": metrics})
            continue

        col = _collapse(content)
        major = MAJOR_ANY_RE.match(col)
        if major and "clarification" not in content.lower():
            title = f"{major.group(1)}.0 {major.group(2).strip()}"
            out.append(f"# {title}")
            chapters.append((f"{major.group(1)}.0", title))
            continue
        if label == "title":
            line, key = render_title(content)
            out.append(line)
            if key:
                chapters.append((key, line[2:]))
        else:
            if _repetition(col) > 0.30:        # OCR loop garbage -> drop
                continue
            out.append(_md_safe(tables.delatex(col)))

    # Page-level loop guard: a dense chart that overflowed sometimes emits hundreds
    # of near-identical prose fragments (the loop spans fragments, so the per-chunk
    # filter misses it). If the prose is overwhelmingly duplicated and the page has
    # no real heading or good table, replace it with a single chart pointer.
    prose = [c for c in out if not c.startswith(("|", "#", ">", "-"))]
    has_table = any(c.startswith("|") for c in out)
    if (len(prose) > 30 and not chapters and not has_table
            and len(set(prose)) / len(prose) < 0.30):
        return [_bad_table_pointer(page_no)], chapters, [
            {"page": page_no, "metrics": {"reason": "loop_garbage"}}]
    return out, chapters, bad


if __name__ == "__main__":
    import sys
    for f in sorted(glob.glob(sys.argv[1])):
        raw = open(f).read()
        n = int(os.path.basename(f).replace("page-", "").replace(".md", ""))
        if is_foldout(raw):
            print(f"\n===== page {n} (foldout) =====")
            print(foldout_pointer(raw, n))
            continue
        chunks, chapters, bad = clean_page(raw, n)
        print(f"\n===== page {n}  chapters={chapters} bad_tables={len(bad)} =====")
        print("\n\n".join(chunks))
