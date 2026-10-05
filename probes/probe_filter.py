"""
probe_filter.py
===============
Read-only. The /offenses page is capped at 10. Does the endpoint honour
FILTERS? If so, a per-period or per-team subset may fit under the cap.

A honoured filter shows as totalCount dropping below the unfiltered total
and ids that are a strict subset. An ignored filter returns the same 10.

Run from the repo root:
    python3 probes/probe_filter.py 501153
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoreboard"))
from foys import FoysClient  # noqa: E402

# periodId 14-17 = Q1-Q4. Team and player ids are read from the unfiltered
# response, so nothing about a particular match is baked in here.


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

    r0 = client._get(base)
    total0, ids0, _, teams0 = summarise(r0)
    team_a, team_b = (list(teams0) + [None, None])[:2]
    items0 = r0["items"] if isinstance(r0, dict) and "items" in r0 else r0
    player = items0[0].get("matchPlayerId") if items0 else None
    print(f"\nunfiltered: totalCount={total0}, {len(ids0)} items; teams seen {teams0}")
    print(f"team_a={team_a} team_b={team_b} player={player}")

    forms = [
        "?periodId=14", "?periodId=16", "?periodId=17",
        "?period=14", "?period=3", "?periodNumber=3",
        f"?teamId={team_a}", f"?teamId={team_b}",
        f"?team={team_a}", f"?matchTeamId={team_a}",
        f"?periodId=17&teamId={team_a}",
        f"?matchPlayerId={player}",
        f"?playerId={player}",
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
