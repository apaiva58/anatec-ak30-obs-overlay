"""
probe_filter.py
===============
Read-only. The /offenses page is capped at 10. Does the endpoint honour
FILTERS? If so, a per-period or per-team subset may fit under the cap.

A honoured filter shows as totalCount dropping below the unfiltered total
and ids that are a strict subset. An ignored filter returns the same 10.

Run from the repo root:
    python3 probe_filter.py 501153
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scoreboard"))
from foys import FoysClient  # noqa: E402

# periodId 14-17 = Q1-Q4. teamIds come from the match detail.
HOME_TEAM = 48525   # Almere Pioneers M18-1 (from probe_detail)


def summarise(r):
    items = r["items"] if isinstance(r, dict) and "items" in r else r
    total = r.get("totalCount") if isinstance(r, dict) else "-"
    ids = [x.get("id") for x in items]
    periods = sorted({x.get("periodId") for x in items})
    teams = sorted({(x.get("matchPlayer") or {}).get("teamId") for x in items})
    return total, ids, periods, teams


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    match_id = int(sys.argv[1])

    client = FoysClient()
    print("authenticating...")
    client.authenticate()
    base = f"/matches/{match_id}/offenses"

    total0, ids0, _, teams0 = summarise(client._get(base))
    away_team = next((t for t in teams0 if t != HOME_TEAM), None)
    print(f"\nunfiltered: totalCount={total0}, {len(ids0)} items; teams seen {teams0}")
    print(f"home={HOME_TEAM} away={away_team}")

    forms = [
        "?periodId=14", "?periodId=16", "?periodId=17",
        "?period=14", "?period=3", "?periodNumber=3",
        f"?teamId={HOME_TEAM}", f"?teamId={away_team}",
        f"?team={HOME_TEAM}", f"?matchTeamId={HOME_TEAM}",
        f"?periodId=17&teamId={HOME_TEAM}",
        f"?matchPlayerId=4854143",   # Bakker, 4 fouls
        f"?playerId=4854143",
        "?offenseTypeId=19",          # P2
        "?offenseType=P2",
        "?group=P",
    ]

    print("\n--- filters (honoured = totalCount changes / ids subset) ---")
    print(f"  {'form':<34} {'total':>6} {'n':>3}  periods          teams            first id")
    for q in forms:
        try:
            total, ids, periods, teams = summarise(client._get(base + q))
            honoured = (total != total0) or (ids[:1] != ids0[:1])
            mark = "  <-- HONOURED" if honoured else ""
            print(f"  {q:<34} {str(total):>6} {len(ids):>3}  {str(periods):<16} {str(teams):<16} {ids[0] if ids else None}{mark}")
        except Exception as e:
            print(f"  {q:<34} ERROR {type(e).__name__}: {str(e)[:50]}")


if __name__ == "__main__":
    main()
