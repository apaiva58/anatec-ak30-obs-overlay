"""
probe_detail.py
===============
Read-only. Fetch /matches/{id} and look for per-player foul data.

If each player row carries a foul count, poll() can diff counts between
polls to detect "player X just fouled" without the capped /offenses list.

Run from the repo root:
    python3 probes/probe_detail.py 501153
"""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoreboard"))
from foys import FoysClient  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    match_id = int(sys.argv[1])

    client = FoysClient()
    print("authenticating...")
    client.authenticate()

    m = client._get(f"/matches/{match_id}")

    print("\n--- top-level keys ---")
    print(sorted(m.keys()))

    for side in ("homeTeamMatchPlayers", "awayTeamMatchPlayers"):
        players = m.get(side) or []
        print(f"\n--- {side}: {len(players)} rows ---")
        if not players:
            continue
        print("keys on a player row:", sorted(players[0].keys()))
        foulish = [k for k in players[0].keys()
                   if any(t in k.lower() for t in ("foul", "offen", "card", "personal"))]
        print("foul-looking keys:", foulish or "NONE")

        print(f"\n  {'#':>3} {'name':<28} " + " ".join(f"{k:>14}" for k in foulish) + "   totalPoints")
        for p in players:
            if (p.get("matchRole") or {}).get("type") != "Player":
                continue
            name = (p.get("person") or {}).get("fullName", "?")
            vals = " ".join(f"{str(p.get(k)):>14}" for k in foulish)
            print(f"  {str(p.get('teamNumber')):>3} {name:<28} {vals}   {p.get('totalPoints')}")

    print("\n--- one full player row, for anything the scan missed ---")
    sample = next((p for p in (m.get("homeTeamMatchPlayers") or [])
                   if (p.get("matchRole") or {}).get("type") == "Player"), None)
    if sample:
        print(json.dumps(sample, ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    main()
