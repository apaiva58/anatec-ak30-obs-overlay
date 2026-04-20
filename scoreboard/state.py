"""
state.py
========
Shared in-memory match state.
Updated by the background poller, read by Flask routes.
"""

match_state = {
    "selected":       False,
    "match_id":       None,
    "home_name":      "",
    "away_name":      "",
    "home_score":     0,
    "away_score":     0,
    "period":         None,
    "home_fouls":     0,
    "away_fouls":     0,
    "home_bonus":     False,
    "away_bonus":     False,
    "last_foul":      None,   # for popup: {player, jersey, code, team}
    "status":         "Planned",
}