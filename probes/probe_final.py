"""
probe_final.py
==============
Read-only. What does FOYS know about a finalised match that the closing
slate could show: a match number the federation uses, and a time the match
was finalised?

Prints, for one match id:
  - every scalar field of /matches/{id} and of its row in /matches, with
    the time-, number- and status-looking ones marked
  - /logs: row count, the keys of a row, rows that are not a goal, foul or
    timeout, and the last rows in full

Run from the repo root:
    python3 probes/probe_final.py 501153
"""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoreboard"))
from foys import FoysClient  # noqa: E402

HINTS = ("date", "time", "at", "final", "close", "end", "status", "updat",
         "modif", "number", "code", "nr", "extern", "official", "sign")


def marked(key):
    k = key.lower()
    return any(h in k for h in HINTS)


def scalars(obj, title):
    print(f"\n--- {title}: scalar fields (* = time/number/status-like) ---")
    for k in sorted(obj):
        v = obj[k]
        if isinstance(v, (dict, list)):
            continue
        print(f"  {'*' if marked(k) else ' '} {k:<34} {v!r}")
    nested = sorted(k for k, v in obj.items() if isinstance(v, (dict, list)))
    print("  nested (not shown):", nested)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    match_id = int(sys.argv[1])

    client = FoysClient()
    print("authenticating...")
    client.authenticate()

    m = client._get(f"/matches/{match_id}")
    scalars(m, f"/matches/{match_id}")

    row = next((r for r in client.get_matches() if r.get("id") == match_id), None)
    if row is None:
        print(f"\n--- /matches list: match {match_id} not in the list ---")
    else:
        extra = sorted(set(row) - set(m))
        scalars(row, "/matches list row")
        print("  keys only in the list row:", extra or "none")

    logs = client._get(f"/matches/{match_id}/logs")
    rows = logs if isinstance(logs, list) else (logs or {}).get("items") or []
    print(f"\n--- /logs: {len(rows)} rows, top-level type {type(logs).__name__} ---")
    if not rows:
        print(json.dumps(logs, ensure_ascii=False, indent=2)[:2000])
        return
    print("keys on a row:", sorted(rows[0].keys()))
    print("time-like keys:", [k for k in rows[0] if marked(k)] or "none")

    def kind(r):
        for k in ("type", "logType", "eventType", "matchLogType", "kind"):
            if k in r:
                v = r[k]
                return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        return "?"

    counts = {}
    for r in rows:
        counts[kind(r)] = counts.get(kind(r), 0) + 1
    print("rows per kind:")
    for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {k[:120]}")

    print("\n--- last 5 rows in full ---")
    for r in rows[-5:]:
        print(json.dumps(r, ensure_ascii=False, indent=2)[:1500])
        print("  ..")


if __name__ == "__main__":
    main()
