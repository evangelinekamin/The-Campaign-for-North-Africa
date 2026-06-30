"""Extract the CNA hex-grid coordinate spec from the VASSAL module's buildFile.

The VASSAL mod (CNAv2.1.0.vmod, a zip) defines the playing map as one board
("CNA Original") with a ZonedGrid whose zones (Malta, Map A-E, holding boxes)
each carry a HexGrid + HexGridNumbering. Those params are the authoritative
coordinate system that turns a rulebook label like "C4807" into a map position
and hex neighbours. This tool reads them out into data/cna_map_grid.json so the
engine has the spec without needing the 99 MB module.

    python3 tools/vassal/extract_grid.py [path/to/CNAv2.1.0.vmod]

The .vmod itself is large and lives outside the repo (kept in Downloads / tmp);
the emitted JSON is committed.
"""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import zipfile

DEFAULT_VMOD = "/mnt/c/Users/evang/Downloads/CNAv2.1.0.vmod"
MAP_IMAGE = "images/CNA Map Vassal Mitch Guthrie 2021.png"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cna_map_grid.json")


def _attrs(s: str) -> dict:
    return dict(re.findall(r'(\w+)="([^"]*)"', s))


def extract(vmod: str) -> dict:
    z = zipfile.ZipFile(vmod)
    xml = z.read("buildFile.xml").decode("utf-8", "replace")

    with z.open(MAP_IMAGE) as f:
        w, h = struct.unpack(">II", f.read(33)[16:24])

    # The main map is the first ZonedGrid block.
    start = xml.find("ZonedGrid")
    end = xml.find("</VASSAL.build.module.map.boardPicker.board.ZonedGrid>", start)
    block = xml[start:end]

    zones = []
    for zm in re.finditer(
            r'mapgrid\.Zone ([^>]*?name="([^"]*)"[^>]*?path="([^"]*)")', block):
        name, path = zm.group(2), zm.group(3)
        seg = block[zm.start():zm.start() + 1500]
        hg = re.search(r'HexGrid ([^>]*)>', seg)
        num = re.search(r'HexGridNumbering ([^>]*)>', seg)
        pts = [tuple(map(int, p.split(","))) for p in path.split(";")]
        zone = {
            "name": name,
            "polygon": pts,
            "bbox": [min(p[0] for p in pts), min(p[1] for p in pts),
                     max(p[0] for p in pts), max(p[1] for p in pts)],
            "hexgrid": _grid_fields(_attrs(hg.group(1))) if hg else None,
            "numbering": _num_fields(_attrs(num.group(1))) if num else None,
        }
        zones.append(zone)

    return {
        "source": "CNAv2.1.0.vmod (Mitch Guthrie 2021 map)",
        "map_image": {"name": os.path.basename(MAP_IMAGE), "width": w, "height": h},
        "zones": zones,
    }


def _grid_fields(a: dict) -> dict:
    return {k: _num(a[k]) for k in ("x0", "y0", "dx", "dy") if k in a} | {
        "sideways": a.get("sideways") == "true"}


def _num_fields(a: dict) -> dict:
    out = {}
    for k in ("hOff", "vOff", "hLeading", "vLeading"):
        if k in a:
            out[k] = int(a[k])
    for k in ("hType", "vType", "sep"):
        if k in a:
            out[k] = a[k]
    for k in ("vDescend", "hDescend", "stagger"):
        if k in a:
            out[k] = a[k] == "true"
    return out


def _num(s: str):
    return float(s) if "." in s else int(s)


def main() -> int:
    vmod = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VMOD
    spec = extract(vmod)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(os.path.normpath(OUT), "w") as f:
        json.dump(spec, f, indent=2)
    grids = sum(1 for z in spec["zones"] if z["hexgrid"])
    print(f"map {spec['map_image']['width']}x{spec['map_image']['height']}; "
          f"{len(spec['zones'])} zones ({grids} with hex grids) -> {os.path.normpath(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
