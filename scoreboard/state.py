"""
state.py
========
Shared in-memory match state.
Updated by the background poller, read by Flask routes.
"""

match_state = {
     # FOYS api data
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
    "home_timeouts": 0,
    "away_timeouts": 0,
    "home_club":  "",
    "away_club":  "",
    "home_logo":        "",
    "away_logo":        "",
    "match_date":       "",
    "match_time":       "",
    "match_location":   "",
    "match_court":      "",
    "player_stats": {},
    # Anatec serial data
    "anatec_connected":    False,
    "anatec_home_score":   0,
    "anatec_guest_score":  0,
    "anatec_home_fouls":   0,
    "anatec_guest_fouls":  0,
    "anatec_period":       0,
    "anatec_clock":        "10:00",
    "anatec_clock_min":    10,
    "anatec_clock_sec":    0,
    "anatec_clock_running": False,
    "anatec_timeout":      None,
    "anatec_service_dot":  False,
    "anatec_home_timeouts": 0,
    "anatec_guest_timeouts": 0,
}