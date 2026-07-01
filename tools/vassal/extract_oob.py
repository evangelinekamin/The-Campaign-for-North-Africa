"""Extract a scenario's order of battle (unit placements) from a VASSAL .vsav.

The CNA VASSAL module bundles scenario setups as `.vsav` saved games (e.g.
"setup desert fox.vsav" = Rommel's Arrival). Each is a zip whose `savedGame`
entry is an obfuscated VASSAL command stream (`!VCSK` + hex, XOR one key byte).
Deobfuscated, it is a list of ESC-separated add-piece commands; on-map pieces
carry an `OldZone` ("Map A".."Map E"), an `OldLocationName` (the hex label) and
`OldX;OldY` (board pixels, which match game.coords.to_pixel to ~4-6px — this file
is how that formula was cross-validated). The counter IMAGE is the authoritative
unit identity (the sendto "name" is sometimes a generic holding-box label, e.g.
the Rommel/DAK counter reads "GE Unassigned Infantry Units").

This recovers WHO is WHERE + side + category. It does NOT recover unit STATS
(steps / CPA / combat factors) — those live in the OA charts, not the save.

    python3 tools/vassal/extract_oob.py ["setup desert fox.vsav"] [path/to/.vmod]

Writes data/oob_<slug>.json.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from game import coords  # noqa: E402

DEFAULT_VMOD = "/mnt/c/Users/evang/Downloads/CNAv2.1.0.vmod"
DEFAULT_SETUP = "setup desert fox.vsav"
_OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data")

AXIS = {"GE", "IT"}
ALLIED = {"BR", "AU", "IN", "AL", "NZ", "SA", "PO", "FF", "UK", "CW", "US", "GK"}


def deobfuscate(saved: bytes) -> str:
    """Undo VASSAL's !VCSK obfuscation (hex text, every byte XORed with one key)."""
    assert saved[:5] == b"!VCSK", "not a VASSAL-obfuscated savedGame"
    hexpart = saved[5:]
    key = int(hexpart[:2], 16)
    body = bytes(b ^ key for b in bytes.fromhex(hexpart[2:].decode("ascii")))
    return body.decode("utf-8", "replace")


def _kv(cmd: str, key: str) -> str | None:
    m = re.search(re.escape(key) + r";([^;\\\t]*)", cmd)
    return m.group(1) if m else None


def _side(name: str) -> str:
    p = name.split()[0] if name else ""
    return "AXIS" if p in AXIS else "ALLIED" if p in ALLIED else "?"


def _category(image: str, name: str) -> str:
    low = (image + " " + name).lower()
    if "supply dump" in low:
        return "dump"
    if "prison" in low or "rep fac" in low or "repair" in low:
        return "feature"
    if not image or "labelme" in low:
        return "label"
    return "unit"


def extract(text: str) -> list[dict]:
    out: list[dict] = []
    for c in text.split("\x1b"):
        if not c.startswith("+/"):
            continue
        zone = _kv(c, "OldZone")
        if not zone or not re.fullmatch(r"Map [A-E]", zone):
            continue                                   # only pieces on the combat map
        m = re.search(r"piece;[^;]*;[^;]*;([^;\\\t]*);([^;\\\t]*)", c)
        image = (m.group(1) if m else "")
        basic = (m.group(2) if m else "")
        snd = re.search(r"sendto;Return to Organisation Chart;[^;]*;([^;]+);", c)
        group = (snd.group(1) if snd else basic).strip()
        kind = _category(image, group)
        if kind == "label":
            continue
        loc = _kv(c, "OldLocationName") or ""
        mm = re.search(r"(\d{4})$", loc)
        if not mm:
            continue
        hexlbl = zone.split()[1] + mm.group(1)
        counter = re.sub(r"\.(svg|gif|png)$", "", image)
        out.append({
            "hex": hexlbl,
            "side": _side(group),
            "kind": kind,
            "counter": counter,          # authoritative identity (front - back)
            "group": group,              # sendto label (organisational grouping)
            "px": [int(_kv(c, "OldX")), int(_kv(c, "OldY"))],
        })
    out.sort(key=lambda r: (r["side"], r["kind"], r["hex"]))
    return out


def main() -> int:
    args = sys.argv[1:]
    vmod = next((a for a in args if a.endswith(".vmod")), DEFAULT_VMOD)
    setup = next((a for a in args if a.endswith(".vsav")), DEFAULT_SETUP)
    vsav = zipfile.ZipFile(vmod).read(setup)
    saved = zipfile.ZipFile(io.BytesIO(vsav)).read("savedGame")
    oob = extract(deobfuscate(saved))

    # verify placements against the exact coordinate formula (VASSAL's own pixels)
    worst = 0.0
    for r in oob:
        px, py = coords.to_pixel(coords.parse(r["hex"]))
        worst = max(worst, ((px - r["px"][0]) ** 2 + (py - r["px"][1]) ** 2) ** 0.5)

    slug = re.sub(r"[^a-z0-9]+", "_", setup.lower().replace(".vsav", "")).strip("_")
    slug = re.sub(r"^setup_", "", slug)
    path = os.path.normpath(os.path.join(_OUT, f"oob_{slug}.json"))
    with open(path, "w") as f:
        json.dump(oob, f, indent=1)
    n_units = sum(1 for r in oob if r["kind"] == "unit")
    n_dumps = sum(1 for r in oob if r["kind"] == "dump")
    print(f"{setup}: {len(oob)} pieces ({n_units} units, {n_dumps} dumps) "
          f"-> {path}")
    print(f"  placement vs coords.to_pixel: worst {worst:.1f}px (counter nudge in stacks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
