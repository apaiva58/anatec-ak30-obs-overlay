"""
probe_offenses.py
=================
Read-only diagnostic: fetch /offenses for one match and show exactly what
poll() would have seen. Answers three questions:

  1. Is the list one entry per FOUL or one entry per PLAYER?
  2. Is `id` unique per foul, or shared across a player's repeat fouls?
  3. What is offenseType.code really — "P2", or just "P"?

Run from the repo root:
    python3 probes/probe_offenses.py 501153

Fetches twice, five seconds apart, and reports whether any id changed.
Makes no writes. Uses the same FoysClient as server.py.
"""

import os
import sys
import time
import json
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoreboard"))
from foys import FoysClient  # noqa: E402

PLAYER_ROLE = "Player"


def fetch(client, match_id):
    return client.get_offenses(match_id)


def describe(items):
    print(f"\nitems returned: {len(items)}")
    if not items:
        return

    print("\n--- keys on the first item ---")
    print(sorted(items[0].keys()))
    mp = items[0].get("matchPlayer")
    if isinstance(mp, dict):
        print("matchPlayer keys:", sorted(mp.keys()))
    ot = items[0].get("offenseType")
    if isinstance(ot, dict):
        print("offenseType keys:", sorted(ot.keys()))
        print("offenseType value:", json.dumps(ot, ensure_ascii=False))

    print("\n--- every item, in list order ---")
    print(f"{'#':>3} {'id':>8} {'logId':>8} {'period':>6} {'mpId':>8} {'jersey':>6}  {'code':<6} player")
    for i, f in enumerate(items, 1):
        mp = f.get("matchPlayer") or {}
        person = mp.get("person") or {}
        role = (mp.get("matchRole") or {}).get("type")
        print(f"{i:>3} {str(f.get('id')):>8} {str(f.get('matchLogId')):>8} "
              f"{str(f.get('periodId')):>6} {str(f.get('matchPlayerId')):>8} "
              f"{str(mp.get('teamNumber')):>6}  {str((f.get('offenseType') or {}).get('code')):<6} "
              f"{person.get('fullName')}  [{role}]")

    print("\n--- what poll() would dedupe on ---")
    ids = [f.get("id") for f in items]
    print(f"distinct id values: {len(set(ids))} of {len(ids)}")
    dup = [k for k, n in Counter(ids).items() if n > 1]
    if dup:
        print(f"REPEATED ids ({len(dup)}): {dup[:10]}")
        print("  -> a repeat foul reuses an id; poll() would never see it as new")
    else:
        print("every id is unique -> one entry per foul, dedupe is sound")

    print("\n--- per-player foul counts from this list ---")
    per_player = Counter()
    for f in items:
        mp = f.get("matchPlayer") or {}
        if (mp.get("matchRole") or {}).get("type") != PLAYER_ROLE:
            continue
        person = mp.get("person") or {}
        per_player[(mp.get("teamNumber"), person.get("fullName"))] += 1
    for (jersey, name), n in sorted(per_player.items(), key=lambda kv: -kv[1]):
        print(f"  {n}  #{jersey} {name}")

    print("\n--- distinct offenseType codes ---")
    print(Counter((f.get("offenseType") or {}).get("code") for f in items))

    print("\n--- the dict poll() builds, for consecutive-identical check ---")
    prev = None
    collapsed = 0
    for f in items:
        mp = f.get("matchPlayer") or {}
        if (mp.get("matchRole") or {}).get("type") != PLAYER_ROLE:
            continue
        d = {
            "player": (mp.get("person") or {}).get("fullName"),
            "jersey": mp.get("teamNumber"),
            "code":   (f.get("offenseType") or {}).get("code"),
            "team":   mp.get("teamId"),
        }
        if d == prev:
            collapsed += 1
        prev = d
    print(f"consecutive identical dicts: {collapsed}")

    print("\n--- null fields that would break poll() ---")
    for name in ("matchLogId", "matchPlayer", "offenseType", "id"):
        n = sum(1 for f in items if f.get(name) is None)
        if n:
            print(f"  {name} is null on {n} item(s)")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    match_id = int(sys.argv[1])

    client = FoysClient()
    print("authenticating...")
    client.authenticate()

    print(f"fetch 1 for match {match_id}")
    first = fetch(client, match_id)
    describe(first)

    print("\nwaiting 5s, then fetching again to check id stability...")
    time.sleep(5)
    second = fetch(client, match_id)
    a = [f.get("id") for f in first]
    b = [f.get("id") for f in second]
    if a == b:
        print("ids identical across both fetches, same order")
    else:
        print("IDS DIFFER between fetches")
        print(" first :", a[:15])
        print(" second:", b[:15])


if __name__ == "__main__":
    main()
