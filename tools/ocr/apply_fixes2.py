"""Second, comprehensive pass of OCR corrections derived from the 68-section review.

Three tiers:
  A) Non-word garbles  - the 'bad' string is not a real word, so a global replace
                         cannot false-match (e.g. 'parachod' -> 'parachuted').
  B) Scoped fixes      - the correct word IS a real word, so enough surrounding
                         context is included to make the match unique.
  C) Place-name norms  - standardise spellings the reviewers cross-checked against
                         a correct occurrence elsewhere in the same document.

Every change is counted and logged; a fix that matches 0 times (already corrected,
or a slightly different string) is reported so nothing silently no-ops.
"""
import glob
import os

OUT = "/tmp/claude-1000/-home-eve-Projects-tcfnatdw-tmp/b04e8c52-b660-4bec-9ad9-936b04febcce/scratchpad/ocr/out"

# A) Non-word garbles — safe globally.
NONWORD = [
    ("sarching", "searching"), ("parachod", "parachuted"), ("Pashing", "Phasing"),
    ("sucvh", "such"), ("Playerse", "Players"), ("Finalf", "Final"),
    ("vis a vir", "vis a vis"), ("Brokenown", "Broken down"), ("Rockendown", "Broken down"),
    ("LRLDG", "LRDG"), ("thereofused", "thereof used"), ("Cario", "Cairo"),
    ("Torbruk", "Tobruk"), ("Tunesia", "Tunisia"), ("bobbload", "bombload"),
    ("bomblood", "bombload"), ("on-manufactiles", "on-map facilities"),
    ("AMMUNTION", "AMMUNITION"), ("anit-aircraft", "anti-aircraft"),
    ("Henkels", "Heinkels"), ("morotization", "motorization"), ("Valsenines", "Valentines"),
    ("crusiers", "cruisers"), ("In-ative", "Initiative"), ("CAMPAGN", "CAMPAIGN"),
    ("PLANETE", "PLANE"), ("Reccce", "Recce"), ("Schutzen Reqt", "Schutzen Regt"),
    ("Mirsielles", "Marseille"), ("cónvoy", "convoy"), ("RÜLE", "RULE"),
    ("Scily", "Sicily"), ("Grazianni", "Graziani"), ("Agadabia", "Agedabia"),
    ("Morrane", "Morane"), ("Zeland", "Zealand"), ("morotized", "motorized"),
    ("OptStage", "OpStage"), ("OptSage", "OpStage"), ("Optage", "OpStage"),
    ("assignedassigned", "assigned"), ("Birkhamsa", "Bir Khamsa"),
    ("Bobrida", "Bardia"), ("TQE", "TOE"), ("Valetta", "Valletta"),
    ("Engineer ing", "Engineering"), ("Land SupportAir", "Land Support Air"),
    ("PointAllowance", "Point Allowance"), ("aDeparture", "a Departure"),
    ("until1/39", "until 1/39"), ("trates", "rates"),
]

# B) Scoped fixes — context makes the match unique and safe.
SCOPED = [
    ("more way move", "more may move"),
    ("beings a Friendly", "begins a Friendly"),
    ("beings a Maintenance", "begins a Maintenance"),
    ("Recede and Armored Car", "Recce and Armored Car"),
    ("for this purposes", "for this purpose"),
    ("ammunition of possessing", "ammunition or possessing"),
    ("Ifno Patrol", "If no Patrol"),
    ("extending 50 Stores", "expending 50 Stores"),
    ("in- an Enemy", "in an Enemy"),
    ("aos or bir", "oasis or bir"),
    ("These are no tonnage", "There are no tonnage"),
    ("amy use emergency", "may use emergency"),
    ("planes must by ready", "planes must be ready"),
    ("Plans must have fuel", "Planes must have fuel"),
    ("Such tangs", "Such tanks"),
    ("affects may be cumulative", "effects may be cumulative"),
    ("no 20C at night", "no ZOC at night"),
    ("rounded .down", "rounded down"),
    ("Axi Player", "Axis Player"),
    ("ratings my initiate", "ratings may initiate"),
    ("in divi-dually", "individually"),
    ("African poits", "African ports"),
    ("ships adjacent hexes", "ships in adjacent hexes"),
    ("In addition, to 44.21", "In addition to 44.21"),
    ("two regular py units", "two regular supply units"),
    ("in it place", "in its place"),
    ("Game-Turn 1OZ", "Game-Turn 102"),
    ("(recc)", "(recce)"),
    ("Cp = Conps", "Cp = Corps"),
    ("no recec", "no Recce"),
    ("60%) or its assigned", "60%) of its assigned"),
    ("Italy/Scily", "Italy/Sicily"),
    ("bombbad delivered", "bomb load delivered"),
    ("Plates Available", "Pilots Available"),
    ("sucn occupying", "such occupying"),
]

# C) Place-name normalisations (reviewer-verified against correct occurrences).
PLACES = [
    ("Sidi Birani", "Sidi Barrani"), ("Sidi Baranni", "Sidi Barrani"),
    ("Sidi Barrini", "Sidi Barrani"),
]

ALL = [("A", b, g) for b, g in NONWORD] + [("B", b, g) for b, g in SCOPED] \
    + [("C", b, g) for b, g in PLACES]

counts = {}
for f in sorted(glob.glob(os.path.join(OUT, "page-*.md"))):
    text = open(f).read()
    new = text
    for _tier, bad, good in ALL:
        if bad in new:
            counts[bad] = counts.get(bad, 0) + new.count(bad)
            new = new.replace(bad, good)
    if new != text:
        open(f, "w").write(new)

print("applied (occurrences):")
applied = 0
for tier, bad, good in ALL:
    c = counts.get(bad, 0)
    applied += c
    flag = "" if c else "   <-- 0 matches (already fixed / different string)"
    print(f"  [{tier}] {bad!r} -> {good!r}: {c}{flag}")
print(f"\ntotal replacements: {applied}")
