"""After the rotation re-OCR, keep the new output for a page only if it yields
more good-table content than the original. Otherwise restore the backup, so a
page like 135 (counter-symbol chart whose legend OCR'd fine) is never regressed
into rotated garbage. Prints a before/after report."""
import glob
import os
import sys

import tables

OUT = sys.argv[1]
WORK = os.path.join(OUT, "_rerun")


def cells(text):
    total = 0
    for thtml in tables.TABLE_RE.findall(text):
        ok, m = tables.score_grid(tables.parse_grid(thtml))
        if ok:
            total += m["rows"] * m["cols"]
    return total


def words(text):
    # Crude readable-prose proxy: alphabetic tokens of length >= 3.
    return sum(1 for w in text.split() if len(w) >= 3 and any(c.isalpha() for c in w))


for bak in sorted(glob.glob(os.path.join(WORK, "page-*.orig.md"))):
    page = os.path.basename(bak)[5:8]
    cur = os.path.join(OUT, f"page-{page}.md")
    old_text, new_text = open(bak).read(), open(cur).read()
    old_c, new_c = cells(old_text), cells(new_text)
    # Good-table-cell count is the reliable signal: keep the new OCR iff it yields
    # MORE good-table content. Word count is not used as a gate — a looped original
    # (e.g. page 136) inflates its word count with repetition garbage, which would
    # wrongly veto a clean new table.
    keep_new = new_c > old_c
    if not keep_new:
        with open(cur, "w") as f:
            f.write(old_text)
    print(f"page {page}: cells {old_c}->{new_c} | words {words(old_text)}->"
          f"{words(new_text)} | {'KEEP new' if keep_new else 'RESTORED original'}")
