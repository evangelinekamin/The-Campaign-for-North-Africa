"""Apply a tight allowlist of UNAMBIGUOUS OCR corrections to the per-page OCR
source, logging every change. Only globally-safe, high-confidence garbles are
included; contextual fixes, place-name variants, numbers, and case-number
corruptions are intentionally left for manual review against the scan."""
import glob
import os

OUT = "/tmp/claude-1000/-home-eve-Projects-tcfnatdw-tmp/b04e8c52-b660-4bec-9ad9-936b04febcce/scratchpad/ocr/out"

FIXES = [
    ("Asis Player", "Axis Player"),
    ("Navel Convoy", "Naval Convoy"),
    ("Beniheim", "Blenheim"),
    ("Mel09", "Me109"),
    ("CAMPAGN", "CAMPAIGN"),
    ("Pashing Player", "Phasing Player"),
    ("westernnot hexrow", "westernmost hex row"),
    ("parachod", "parachuted"),
    ("sarching", "searching"),
    ("Recc-Type", "Recce-Type"),
    ("Reccd-Type", "Recce-Type"),
    ("Cost Defense Guns", "Coastal Defense Guns"),
    ("HEALIAN", "ITALIAN"),
]

total = {}
for f in sorted(glob.glob(os.path.join(OUT, "page-*.md"))):
    text = open(f).read()
    new = text
    for bad, good in FIXES:
        if bad in new:
            total[bad] = total.get(bad, 0) + new.count(bad)
            new = new.replace(bad, good)
    if new != text:
        open(f, "w").write(new)

print("applied corrections (occurrences):")
for bad, good in FIXES:
    if total.get(bad):
        print(f"  {bad!r} -> {good!r}: {total[bad]}")
print("total replacements:", sum(total.values()))
