"""
probe_periods.py
================
Read-only. Can the quarter scores be derived from /goals alone?

/goals is a plain list with no envelope and no cap (docs/foys-api.md), and
every row carries teamId, points and periodId. If so, grouping that list by
periodId gives the per-quarter score with no extra request, and state.py's
unused "periods" key can finally be filled.

This probe does the grouping and prints it in the shape of the NBB match
form, so the numbers can be compared against the paper by eye. It also
reports anything that would quietly corrupt the sum: goals with no
periodId, unexpected point values, and periodIds outside the documented
14..17 (+18 for overtime) range.

Run from the repo root:
    python3 probes/probe_periods.py 501153
    python3 probes/probe_periods.py            # newest finished M18 match

Nothing is written. Compare the output against the official match form
before any of this reaches the overlay.
"""

import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoreboard"))
from foys import FoysClient  # noqa: E402

# docs/foys-api.md: 14..17 = Q1..Q4, 18+ = overtime
PERIOD_NAMES = {14: "Q1", 15: "Q2", 16: "Q3", 17: "Q4"}


def period_name(pid):
    if pid in PERIOD_NAMES:
        return PERIOD_NAMES[pid]
    if pid is not None and pid >= 18:
        return f"OT{pid - 17}"
    return f"?{pid}"


def pick_match(matches, needle="M18"):
    """Newest match whose team names mention `needle`. Printed, never guessed
    silently -- the caller should check it is the one they meant."""
    hits = [m for m in matches
            if needle.lower() in f"{m.get('homeTeamName','')} {m.get('awayTeamName','')}".lower()]
    if not hits:
        return None, hits
    hits.sort(key=lambda m: (m.get("date") or "", m.get("startTime") or ""))
    played = [m for m in hits if m.get("status") == "Final"] or hits
    return played[-1], hits


def main():
    client = FoysClient()
    print("authenticating...")
    client.authenticate()

    matches = client.get_matches()

    if len(sys.argv) > 1:
        match_id = int(sys.argv[1])
        match = next((m for m in matches if m["id"] == match_id), None)
        if match is None:
            print(f"match {match_id} is not in this account's match list; "
                  f"fetching it directly")
    else:
        match, hits = pick_match(matches)
        if match is None:
            print("No match with 'M18' in either team name. Candidates:")
            for m in matches[-15:]:
                print(f"  {m['id']}  {m.get('date','')[:10]}  "
                      f"{m.get('homeTeamName')} vs {m.get('awayTeamName')}  {m.get('status')}")
            sys.exit(1)
        print(f"\n{len(hits)} M18 match(es) in the list; taking the newest finished one.")
        match_id = match["id"]

    # --- match header -------------------------------------------------------
    if match:
        print(f"\n=== match {match_id} ===")
        print(f"  {match.get('homeTeamName')}  vs  {match.get('awayTeamName')}")
        print(f"  {match.get('date','')[:10]} {match.get('startTime','')[:5]}  "
              f"{match.get('accommodationName')} / {match.get('fieldName')}")
        print(f"  status: {match.get('status')}   "
              f"list score: {match.get('homeScore')}-{match.get('awayScore')}")
        home_id, away_id = match["homeTeamId"], match["awayTeamId"]
    else:
        detail = client.get_match(match_id)
        home_id, away_id = detail["homeTeamId"], detail["awayTeamId"]
        print(f"\n=== match {match_id} (from /matches/{match_id}) ===")

    # --- goals --------------------------------------------------------------
    goals = client.get_goals(match_id)
    shape = ("plain list" if isinstance(goals, list)
             else f"ENVELOPE totalCount={goals.get('totalCount')} -- may be capped")
    if isinstance(goals, dict) and "items" in goals:
        goals = goals["items"]
    print(f"\n/goals: {len(goals)} rows ({shape})")

    # --- integrity checks ---------------------------------------------------
    no_period = [g for g in goals if g.get("periodId") is None]
    no_team = [g for g in goals if g.get("teamId") not in (home_id, away_id)]
    point_values = Counter(g.get("points") for g in goals)
    odd_periods = sorted({g.get("periodId") for g in goals
                          if g.get("periodId") is not None and g["periodId"] < 14})

    print(f"  point values seen: {dict(sorted(point_values.items(), key=lambda kv: (kv[0] is None, kv[0])))}")
    print(f"  goals without periodId: {len(no_period)}"
          + ("   <-- these are dropped from the quarter split" if no_period else ""))
    print(f"  goals on neither team id: {len(no_team)}"
          + ("   <-- investigate before trusting the split" if no_team else ""))
    if odd_periods:
        print(f"  periodIds below 14: {odd_periods}   <-- outside the documented mapping")

    # --- the grouping under test -------------------------------------------
    periods = defaultdict(lambda: {"home": 0, "away": 0})
    for g in goals:
        pid = g.get("periodId")
        if pid is None:
            continue
        side = "home" if g["teamId"] == home_id else "away" if g["teamId"] == away_id else None
        if side:
            periods[pid][side] += g.get("points") or 0

    print(f"\n  {'':<6} {'thuis':>7} {'gasten':>7}    {'loopend':>12}")
    run_h = run_a = 0
    for pid in sorted(periods):
        p = periods[pid]
        run_h += p["home"]
        run_a += p["away"]
        print(f"  {period_name(pid):<6} {p['home']:>7} {p['away']:>7}    {run_h:>5} - {run_a:<5}")
    print(f"  {'-' * 40}")
    print(f"  {'totaal':<6} {run_h:>7} {run_a:>7}")

    # --- cross-check against the two totals we already trust ----------------
    sum_h = sum(g.get("points") or 0 for g in goals if g.get("teamId") == home_id)
    sum_a = sum(g.get("points") or 0 for g in goals if g.get("teamId") == away_id)
    print(f"\n  calculate_score() over all goals: {sum_h}-{sum_a}"
          + ("  OK" if (sum_h, sum_a) == (run_h, run_a)
             else "  MISMATCH with the quarter split -- goals are being dropped"))
    if match:
        listed = (match.get("homeScore"), match.get("awayScore"))
        print(f"  /matches list score:              {listed[0]}-{listed[1]}"
              + ("  OK" if listed == (sum_h, sum_a) else "  MISMATCH"))

    print("\nNow compare the quarter rows above against the official NBB match form.")


if __name__ == "__main__":
    main()
