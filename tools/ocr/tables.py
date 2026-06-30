"""Parse the OCR model's inline HTML tables into a real grid and render clean
markdown, plus score whether a table is trustworthy enough to publish.

The model emits tables as `<table><tr><td ...>cell</td>...</tr>...</table>` with
heavy use of colspan/rowspan and HTML entities (e.g. &#x27; for an apostrophe).
A dense chart that overflowed the model often shows up as a single enormous row
or wildly varying column counts; score_grid flags those so they can be re-OCR'd
or pointed-to rather than published as if correct.
"""
import re
import html as _html


def delatex(t):
    """Strip the LaTeX/math the OCR model emits for counter symbols, fractions and
    footnote markers (e.g. \\frac{1}{2} -> 1/2, \\xrightarrow{xx} -> xx, ^{E} -> E),
    leaving readable plain text. No-op on text without LaTeX."""
    if "\\" not in t and "^{" not in t:
        return t
    t = t.replace(r"\( \Delta t \)", "Fuel")                      # supply table header
    t = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"\1/\2", t)      # fractions
    t = re.sub(r"\\xrightarrow\{([^}]*)\}", r"\1", t)            # unit-size symbols
    t = re.sub(r"\\stackrel\{([^}]*)\}\{([^}]*)\}", r"\1 \2", t)
    t = re.sub(r"\\boxed\{\\text\{([^}]*)\}\}", r"[\1]", t)
    t = re.sub(r"\\boxed\{([^}]*)\}", r"[\1]", t)
    t = re.sub(r"\\text\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\^\{([^}]*)\}", r"\1", t)                        # superscript braces
    t = re.sub(r"\^([A-Za-z0-9])", r"\1", t)                      # bare superscript
    t = (t.replace(r"\times", "×").replace(r"\div", "÷")
          .replace(r"\dagger", "†").replace(r"\parallel", "||")
          .replace(r"\Delta", "Δ").replace(r"\%", "%")
          .replace(r"\,", " ").replace(r"\;", " "))
    t = re.sub(r"\\\(\s*", "", t)                                 # unwrap \( ... \)
    t = re.sub(r"\s*\\\)", "", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()

CELL_RE = re.compile(r"<t[dh]\b([^>]*)>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
SPAN_RE = re.compile(r'(colspan|rowspan)\s*=\s*"?(\d+)"?', re.IGNORECASE)
TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)


def decode(text):
    """Decode HTML entities, strip LaTeX, and tidy whitespace inside a cell."""
    text = _html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)          # strip any stray inline tags
    text = delatex(text)
    return re.sub(r"\s+", " ", text).strip()


def _spans(attrs):
    col = row = 1
    for name, val in SPAN_RE.findall(attrs):
        n = int(val)
        if name.lower() == "colspan":
            col = n
        else:
            row = n
    # Guard against absurd spans from OCR noise.
    return min(col, 64), min(row, 64)


def parse_grid(table_html):
    """Expand one <table> into a rectangular grid (list of rows of cell strings),
    honouring colspan (content in the first cell, blanks after) and rowspan
    (content carried into the rows below). Returns [] for an empty table."""
    grid = []                       # list[list[str|None]]; None = not yet filled
    pending = {}                    # col -> (text, remaining_rows) from rowspans

    for r, row_html in enumerate(ROW_RE.findall(table_html)):
        # Ensure a row list exists, pre-filled by any active rowspans.
        while len(grid) <= r:
            grid.append([])
        row = grid[r]
        col = 0

        def place(c, text):
            while len(row) <= c:
                row.append(None)
            row[c] = text

        for attrs, raw in CELL_RE.findall(row_html):
            # Skip columns occupied by a rowspan carried from above.
            while pending.get(col, (None, 0))[1] > 0:
                txt, rem = pending[col]
                place(col, txt)
                pending[col] = (txt, rem - 1)
                col += 1
            cspan, rspan = _spans(attrs)
            text = decode(raw)
            for k in range(cspan):
                place(col + k, text if k == 0 else "")
                if rspan > 1:
                    pending[col + k] = (text if k == 0 else "", rspan - 1)
            col += cspan
        # Fill any trailing rowspan columns after the last explicit cell.
        for c in sorted(pending):
            if pending[c][1] > 0 and (c >= len(row) or row[c] is None):
                txt, rem = pending[c]
                place(c, txt)
                pending[c] = (txt, rem - 1)

    width = max((len(r) for r in grid), default=0)
    return [[(c if c is not None else "") for c in r] + [""] * (width - len(r))
            for r in grid]


def score_grid(grid):
    """Return (is_good, metrics). A grid is publishable when it has a stable
    column count, isn't dominated by empty/dash cells, and isn't a runaway loop."""
    rows = len(grid)
    if rows == 0:
        return False, {"reason": "empty", "rows": 0}
    widths = [len(r) for r in grid]
    maxw = max(widths)
    cells = [c for r in grid for c in r]
    n = len(cells) or 1
    blankish = sum(1 for c in cells if c == "" or set(c) <= set("-—–.· "))
    # Column-count stability: fraction of rows at the modal width.
    from collections import Counter
    modal = Counter(widths).most_common(1)[0][1]
    stable = modal / rows
    metrics = {
        "rows": rows, "cols": maxw, "stable": round(stable, 2),
        "blank_frac": round(blankish / n, 2),
    }
    if maxw > 40:                       # phantom-column loop (page 102 had 4323)
        return False, {**metrics, "reason": "too_wide"}
    if rows == 1 and maxw > 12:         # one giant row = overflow, not a table
        return False, {**metrics, "reason": "single_row_blob"}
    if stable < 0.5:                    # column count all over the place
        return False, {**metrics, "reason": "unstable_cols"}
    if blankish / n > 0.75:             # mostly empty/dashes -> unreliable
        return False, {**metrics, "reason": "mostly_blank"}
    return True, metrics


def to_markdown(grid):
    """Render a grid as a GitHub-flavoured markdown table. Treats row 0 as the
    header. Escapes pipes; collapses fully-blank trailing columns."""
    if not grid:
        return ""
    width = max(len(r) for r in grid)
    norm = [[(r[i] if i < len(r) else "").replace("|", "\\|") for i in range(width)]
            for r in grid]
    # Drop trailing columns that are entirely empty.
    while width > 1 and all(row[width - 1] == "" for row in norm):
        width -= 1
        norm = [row[:width] for row in norm]
    header = norm[0]
    if all(h == "" for h in header):
        header = [f"col{i+1}" for i in range(width)]
    sep = ["---"] * width
    body = norm[1:] if len(norm) > 1 else []
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(sep) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def convert_tables(text):
    """Replace every <table>...</table> in `text` with a clean markdown table when
    it scores well, or with a typed placeholder token when it does not. Returns
    (new_text, results) where results is a list of dicts describing each table."""
    results = []

    def repl(m):
        grid = parse_grid(m.group(0))
        good, metrics = score_grid(grid)
        idx = len(results)
        results.append({"good": good, "metrics": metrics, "grid": grid})
        if good:
            return "\n\n" + to_markdown(grid) + "\n\n"
        return f"\n\n\x00BADTABLE:{idx}\x00\n\n"

    return TABLE_RE.sub(repl, text), results
