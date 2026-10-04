"""
probe_all.py
============
Read-only. The DWF web client fetches /matches/{id}/offenses/all, not
/offenses. Compare both paths on two matches to confirm /all is uncapped.

Also tries /timeouts/all and /logs, since the client calls those too.

Run from the repo root:
    python3 probe_all.py 501153 524518
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scoreboard"))
from foys import FoysClient  # noqa: E402


def count(r):
    if isinstance(r, dict) and "items" in r:
        return f"{len(r['items'])} items (envelope, totalCount={r.get('totalCount')})"
    if isinstance(r, list):
        return f"{len(r)} items (plain list)"
    return f"unexpected shape: {type(r).__name__}"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    client = FoysClient()
    print("authenticating...")
    client.authenticate()

    for mid in sys.argv[1:]:
        print(f"\n=== match {mid} ===")
        for path in ("offenses", "offenses/all", "timeouts", "timeouts/all", "logs", "goals"):
            try:
                r = client._get(f"/matches/{mid}/{path}")
                print(f"  /{path:<14} {count(r)}")
            except Exception as e:
                print(f"  /{path:<14} ERROR {type(e).__name__}: {str(e)[:60]}")

    # Show the first and last offense from /all on the first match, to
    # confirm ordering and that the tail (foul 34) is really there.
    mid = sys.argv[1]
    r = client._get(f"/matches/{mid}/offenses/all")
    items = r["items"] if isinstance(r, dict) else r
    if items:
        for label, f in (("first", items[0]), ("last", items[-1])):
            mp = f.get("matchPlayer") or {}
            print(f"\n  {label}: id={f.get('id')} logId={f.get('matchLogId')} period={f.get('periodId')} "
                  f"time={f.get('time')} #{mp.get('teamNumber')} "
                  f"{(mp.get('person') or {}).get('fullName')} {(f.get('offenseType') or {}).get('code')}")


if __name__ == "__main__":
    main()
