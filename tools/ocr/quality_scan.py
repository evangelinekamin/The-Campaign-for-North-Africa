"""Flag pages whose OCR likely degenerated into a repetition loop or ran away to
the token limit. Heuristics: very large output, or a single 5-gram that accounts
for a large fraction of all 5-grams (the signature of a loop)."""
import glob
import os
import re
import sys
from collections import Counter

BLOCK_RE = re.compile(
    r"<\|det\|>\s*(\w+)\s*\[[^\]]*\]\s*<\|/det\|>(.*?)(?=<\|det\|>|\Z)", re.DOTALL)

OUT_DIR = sys.argv[1]


def text_of(raw):
    return " ".join(c.strip() for _, c in BLOCK_RE.findall(raw))


def repetition_score(t):
    words = t.split()
    if len(words) < 60:
        return 0.0, len(words)
    grams = [" ".join(words[i:i + 5]) for i in range(len(words) - 5)]
    c = Counter(grams)
    return c.most_common(1)[0][1] / len(grams), len(words)


rows = []
for f in sorted(glob.glob(os.path.join(OUT_DIR, "page-*.md"))):
    raw = open(f).read()
    score, nw = repetition_score(text_of(raw))
    num = os.path.basename(f).replace("page-", "").replace(".md", "")
    rows.append((num, len(raw), nw, score))

flagged = []
print(f"{'page':>5}{'chars':>9}{'words':>8}{'rep5g':>8}  flag")
for num, ch, nw, score in rows:
    suspect = ch > 40000 or score > 0.04
    if suspect:
        flagged.append(num)
        print(f"{num:>5}{ch:>9}{nw:>8}{score:>8.3f}  <<< SUSPECT")
print(f"\nscanned={len(rows)}  suspect={len(flagged)}: {flagged}")
