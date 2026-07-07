"""STAFF_* narrative-event payload discipline (the keystone substrate).

Staff events carry no board authority -- apply() folds them as no-ops. Their only
risk is the payload: a rambling model could smuggle a whole transcript back into
the log through a free-text field. clean_staff_payload is the boundary that stops
that (same defensive spirit as llm_policy._clean_intent): per-kind whitelist of
fields, hard char-caps, collections coerced to JSON primitives, unknown keys and
invalid enum values dropped. json.dumps(result) always succeeds.

INTENT_FIELDS is hoisted here as the single canonical source of the commander's
intent field caps (llm_policy will import it from here in a later slice).
"""
from __future__ import annotations

from .events import Event, EventKind

# Single canonical source for the commander's-intent field caps.
INTENT_FIELDS = {"objective": 140, "scheme": 200, "supply": 140, "milestone": 120, "risks": 140}

_DROP = object()   # sentinel: a field cleaner returns this to drop the field entirely


# --- field cleaners: each maps a raw value -> a cleaned JSON primitive, or _DROP ---

def _str(cap: int):
    def clean(v):
        return v.strip()[:cap] if isinstance(v, str) and v.strip() else _DROP
    return clean


def _enum(allowed: frozenset):
    def clean(v):
        return v if v in allowed else _DROP
    return clean


def _hex(v):
    if isinstance(v, (list, tuple)) and len(v) == 2 \
            and all(isinstance(x, int) and not isinstance(x, bool) for x in v):
        return [v[0], v[1]]
    return _DROP


def _hexes(v):
    if not isinstance(v, (list, tuple)):
        return _DROP
    out = [h for h in (_hex(item) for item in v) if h is not _DROP]
    return out or _DROP


def _strlist(max_items: int, cap: int):
    def clean(v):
        if not isinstance(v, (list, tuple)):
            return _DROP
        out = [str(x).strip()[:cap] for x in list(v)[:max_items]
               if isinstance(x, str) and str(x).strip()]
        return out or _DROP
    return clean


_PROPOSAL_ORDERS = frozenset({"move", "attack", "supply_move",
                              # the two order-type resource seats (P5 Step 6): the Air
                              # Marshal tasks air_mission (strike/fort/port/recon), the
                              # Convoy officer routes convoys, commits the ferry interdiction
                              # and lays the 30.2 fleet bombardment. They own NO Unit, so they
                              # never collide with a GOC -- the Lane partition is untouched.
                              "air_mission", "interdict", "bombard", "convoy_route"})
_MAX_PROPOSALS = 20


def _proposes(v):
    if not isinstance(v, (list, tuple)):
        return _DROP
    out = []
    for item in list(v)[:_MAX_PROPOSALS]:
        if not isinstance(item, dict):
            continue
        one: dict = {}
        if item.get("order") in _PROPOSAL_ORDERS:
            one["order"] = item["order"]
        units = _strlist(20, 48)(item.get("units"))
        if units is not _DROP:
            one["units"] = units
        to = _hex(item.get("to"))
        if to is not _DROP:
            one["to"] = to
        if one:
            out.append(one)
    return out or _DROP


# COMMON envelope on every STAFF_* kind.
_ENVELOPE = {
    "formation": _str(48),
    "addressee": _str(48),
    "hexes": _hexes,
    "line": _str(240),
}

# Per-kind payload whitelists (merged with the envelope).
_KIND_FIELDS = {
    EventKind.STAFF_INTENT: {
        "objective": _str(INTENT_FIELDS["objective"]),
        "scheme": _str(INTENT_FIELDS["scheme"]),
        "supply": _str(INTENT_FIELDS["supply"]),
        "milestone": _str(INTENT_FIELDS["milestone"]),
        "risks": _str(INTENT_FIELDS["risks"]),
        "lessons": _strlist(3, 100),
        # The FUEL_PRIORITY analog for the two resource seats: the Chief's optional
        # standing steer for air-sortie / convoy-tonnage scarcity, arbitrated the way
        # the fuel priority arbitrates dump draws (P5 Step 6). Prose one-liners.
        "air_priority": _str(140),
        "sea_priority": _str(140),
    },
    EventKind.STAFF_PROPOSAL: {
        "proposes": _proposes,
        "rationale": _str(200),
    },
    EventKind.STAFF_CONSTRAINT: {
        "kind": _enum(frozenset({"fuel", "ammo", "stacking", "road", "intel",
                                 "air", "naval"})),   # the two resource seats' scarcity flags
        "severity": _enum(frozenset({"info", "warn", "block"})),
        "subject": _str(48),
    },
    EventKind.STAFF_ADJUDICATION: {
        "conflict": _enum(frozenset({"over-stack", "oversubscribed-dump", "road-cap",
                                     # the air/sea scarcity clashes the Chief arbitrates:
                                     # committed strike Air Points beyond the SEA sortie
                                     # budget, convoy tonnage beyond the dump headroom.
                                     "oversubscribed-sorties", "oversubscribed-tonnage"})),
        "favored": _str(48),
        "denied": _str(48),
        "ruling": _str(200),
    },
    EventKind.STAFF_DISSENT: {
        "against": _str(120),
        "stance": _str(200),
    },
}


def clean_staff_payload(kind: EventKind, raw: dict) -> dict:
    """Whitelist `raw` to the fields allowed for `kind` (envelope + per-kind block),
    truncating strings to caps and coercing collections to JSON primitives. Unknown
    keys and disallowed enum values are dropped. json.dumps(result) always succeeds."""
    if not isinstance(raw, dict):
        return {}
    spec = {**_ENVELOPE, **_KIND_FIELDS.get(kind, {})}
    out: dict = {}
    for name, clean in spec.items():
        if name not in raw:
            continue
        value = clean(raw[name])
        if value is not _DROP:
            out[name] = value
    return out


def staff_log(events: list[Event]) -> list[Event]:
    """The narrative record: the STAFF_* events from a stream, in seq order."""
    return [e for e in events if e.kind.name.startswith("STAFF_")]
