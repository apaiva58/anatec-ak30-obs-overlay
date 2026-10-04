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
    "period_name":   "—",
    "periods":       {},
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
    "anatec_clock_tenths": None,   # None at 1:00 and above, 0-9 below one minute
    "anatec_clock_running": False,
    "anatec_timeout":      None,
    "anatec_service_dot":  False,
    "anatec_home_timeouts": 0,
    "anatec_guest_timeouts": 0,
    # System health — written by reader/poller, read by the status card
    "anatec_mode":         "off",    # off | serial | simulate | mock
    "anatec_port":         None,
    "anatec_last_frame_ts": None,
    "foys_mode":           "live",   # live | demo | mock
    "foys_auth_ok":        False,
    "foys_last_ok_ts":     None,
    "foys_error_count":    0,
    "foys_event_period":   None,   # highest periodId with a goal, foul or timeout
    # Scene control — written by scene_control, read by the status dock
    "obs_enabled":         False,   # False under --no-obs (dry run)
    "obs_available":       False,
    "obs_scene":           None,    # the scene actually on air, read from OBS
    "obs_missing_scenes":  [],      # configured scenes that do not exist in OBS
    "scene_prompt":        None,    # one line for the operator
}