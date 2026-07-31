"""GATE 8.1c-OOB (8.1d) -- compact an arm file's `signature` field to its digest, in place.

engine.determinism_signature (engine.py:6041) returns the WHOLE canonical event log as JSON, not a
hash -- about 71 MB for one 111-turn campaign, half a gigabyte per seven-seed arm.  The first run of
gate81d_ab.py stored it verbatim.  Two logs are byte-identical iff their digests are, which is
everything an A/B and a neuter-proof ask of the field, so the driver now stores
blake2b(log, digest_size=16).hexdigest() and this pass brings the already-written arm files to
exactly what the driver would now emit.

Streaming, one line at a time: json.dump(indent=1) puts each key on its own line, so the giant log
is a single (very long) line and only one of them is ever in memory.

Usage:  python3 scratchpad/gate81d_compact.py scratchpad/gate81d/ab_BASE.json ...
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

PREFIX = '"signature": "'


def compact(path: str) -> None:
    tmp = path + ".compact"
    rewritten = 0
    with open(path) as src, open(tmp, "w") as dst:
        for line in src:
            stripped = line.strip().rstrip(",")
            if stripped.startswith(PREFIX):
                value = json.loads(stripped[len('"signature": '):])
                if len(value) <= 64:                       # already a digest -- leave it alone
                    dst.write(line)
                    continue
                digest = hashlib.blake2b(value.encode(), digest_size=16).hexdigest()
                indent = line[:len(line) - len(line.lstrip())]
                comma = "," if line.rstrip().endswith(",") else ""
                dst.write(f'{indent}"signature": {json.dumps(digest)}{comma}\n')
                rewritten += 1
            else:
                dst.write(line)
    json.load(open(tmp))                                   # the rewrite must still parse
    os.replace(tmp, path)
    print(f"{path}: {rewritten} signature(s) compacted, "
          f"{os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        compact(p)
