"""
server.py
=========
Flask server for the Anatec AK30 OBS overlay. Serves the match-selection
UI, the overlay pages OBS renders, a live status card, and the JSON state
endpoint they all poll. Runs the FOYS background poller and the Anatec
reader, and drives OBS scene switching over its websocket.

Usage
-----
    python3 scoreboard/server.py [options]

Match day (auto-detect the console, live FOYS):
    python3 scoreboard/server.py --anatec auto

Development (no hardware, no FOYS, no OBS):
    python3 scoreboard/server.py --anatec simulate --mock --no-obs

Options
-------
    --anatec MODE   Anatec input. Default: simulate
                      auto      probe serial ports, pick the one emitting
                                AK30 frames, rediscover if the link drops
                      serial    read a fixed port given with --port
                      simulate  replay a scripted game from simulator.py
                      off       FOYS data only
    --port PATH     Serial port for --anatec serial.
                    Default: /dev/tty.usbserial-1110 (suffix varies by
                    USB socket on macOS; prefer --anatec auto)
    --demo          Use the FOYS demo environment
    --mock          Load mock_data.json and skip FOYS authentication
    --finalised     With --mock, set match status to Final
    --no-obs        Dry run for scene control: decisions are logged and shown
                    on the status dock, OBS is not contacted

Environment (.env)
------------------
    FOYS_USERNAME, FOYS_PASSWORD, FOYS_ORGANISATION_ID,
    FOYS_ORGANISATION_ID_DEMO, FOYS_DEMO_MODE
    OBS_WEBSOCKET_PASSWORD      from OBS: Tools > WebSocket Server Settings
    OBS_WEBSOCKET_HOST, OBS_WEBSOCKET_PORT   default localhost and 4455
    OBS_SCENE_COURT             scene for play (default: Scène 2: WIDE Overlay)
    OBS_SCENE_HALFTIME          scene for the halftime break (default:
                                Scène 4: STATS)
    OBS_SCENE_FINAL             scene for a finalised match (default: the
                                halftime scene; later e.g. Final Stats)
    OBS_STATS_AFTER_PERIODS     period ends that get the halftime scene
                                (default 2; 1,2,3 for every break)
    OBS_STATS_DELAY             seconds between the buzzer and that scene
                                (default 2.0)

Routes
------
    /                   match selection, with status card (operator)
    /select/<id>        choose a match; starts live polling for it
    /status             status card alone; add to OBS as a Custom Browser
                        Dock (Docks > Custom Browser Docks)
    /api/state          match_state as JSON plus a derived `system` block
    /api/players        rosters for the selected match
    /overlay            combined live + final overlay
    /overlay/wide       bottom bar
    /overlay/box        corner box
    /overlay/stats      end-of-period player stats
    /overlay/final      final score
    /overlay/anatec     Anatec-only overlay
    /overlay/foys       FOYS-only overlay

OBS wiring
----------
    Browser Source      http://localhost:5001/overlay/wide  (or another
                        overlay route) at the canvas size
    Custom Browser Dock http://localhost:5001/status
    Scene names and which period ends switch scenes are set in .env (see
    above). The rules are in scene_logic.py and explained in docs/scenes.md.

Notes
-----
    The server stays up if FOYS authentication fails: Anatec data still
    flows, the status card shows FOYS red. Serial ports are exclusive, so
    stop capture.py before starting the server in serial or auto mode.
    Port 5001. Templates reload on edit; route changes need a restart.
"""

import os
import threading
import time
from flask import Flask, jsonify, render_template, make_response
from foys import FoysClient
from state import match_state
from scene_control import ObsClient, DryObs, SceneController
from scene_logic import SceneDirector, parse_periods, parse_seconds

app = Flask(__name__, template_folder="../templates")
client = FoysClient()


# ── Scene control configuration ─────────────────────────────────────────────

# The decisions live in scene_logic.py, the OBS side in scene_control.py.
# Everything here is set in .env; the defaults are shown.

SCENES = {
    "court":    os.getenv("OBS_SCENE_COURT",    "Scène 2: WIDE Overlay"),
    "halftime": os.getenv("OBS_SCENE_HALFTIME", "Scène 4: STATS"),
}
# The scene for a finalised match. Until a dedicated scene exists it is the
# halftime scene; create "Final Stats" in OBS, set OBS_SCENE_FINAL=Final Stats
# and restart. No code change needed.
SCENES["final"] = os.getenv("OBS_SCENE_FINAL", SCENES["halftime"])

# Which period ends put the halftime scene on air: "2", or "1,2,3" for every break.
STATS_AFTER_PERIODS = parse_periods(os.getenv("OBS_STATS_AFTER_PERIODS", "2"))

# Seconds to keep the court on air after the buzzer before the stats scene.
STATS_DELAY_S = parse_seconds(os.getenv("OBS_STATS_DELAY"), 2.0)



        
# ── Helper functions ────────────────────────────────────────────────────────

def calculate_score(goals, team_id):
    return sum(g["points"] for g in goals if g["teamId"] == team_id)


def calculate_fouls(offenses, team_id, period_id):
    return len([
        f for f in offenses
        if f["matchPlayer"]["teamId"] == team_id
        and f["periodId"] == period_id
        and f["matchPlayer"]["matchRole"]["type"] == "Player"
    ])


def current_period(goals, offenses):
    """Highest periodId across all events. Period ids are monotonic
    (14..17 = Q1..Q4, 18+ = OT), so max() is the current period without
    depending on matchLogId -- which /offenses/all rows do not carry and
    which FOYS briefly reports as null on freshly created goals."""
    periods = [e.get("periodId") for e in (goals or []) + (offenses or [])
               if e.get("periodId") is not None]
    return max(periods) if periods else None


def max_event_period(*event_lists):
    """Highest periodId over goals, offenses and timeouts: the latest period
    with any recorded play. Unlike current_period() it includes timeouts, and
    scene control uses it as evidence that play has resumed."""
    periods = [e.get("periodId") for events in event_lists for e in (events or [])
               if e.get("periodId") is not None]
    return max(periods) if periods else None


# ── Background poller ───────────────────────────────────────────────────────

seen_offense_ids = set()


def poll():
    global seen_offense_ids
    tick = 0
    while True:
        try:
            if match_state["selected"]:
                match_id = match_state["match_id"]
                home_id  = match_state["home_id"]
                away_id  = match_state["away_id"]

                # always check status every ~9 seconds
                if tick % 3 == 0:
                    try:
                        matches = client.get_matches()
                        current = next((m for m in matches if m["id"] == match_id), None)
                        if current:
                            match_state["status"] = current["status"]
                        match_state["foys_last_ok_ts"]  = time.time()
                        match_state["foys_error_count"] = 0
                    except Exception:
                        match_state["foys_error_count"] = match_state.get("foys_error_count", 0) + 1

                # only when not Final
                if match_state["status"] != "Final":
                    goals    = client.get_goals(match_id)
                    offenses = client.get_offenses(match_id)
                    timeouts = client.get_timeouts(match_id)
                    period   = current_period(goals, offenses)
                    match_state["foys_event_period"] = max_event_period(goals, offenses, timeouts)
                    match_state["foys_last_ok_ts"]  = time.time()
                    match_state["foys_error_count"] = 0

                    match_state["home_score"] = calculate_score(goals, home_id)
                    match_state["away_score"] = calculate_score(goals, away_id)
                    match_state["period"]     = period

                    if period:
                        home_fouls = calculate_fouls(offenses, home_id, period)
                        away_fouls = calculate_fouls(offenses, away_id, period)
                        match_state["home_fouls"] = home_fouls
                        match_state["away_fouls"] = away_fouls
                        match_state["home_bonus"] = home_fouls >= 4
                        match_state["away_bonus"] = away_fouls >= 4
                        match_state["home_timeouts"] = len([
                            t for t in timeouts
                            if t["isHomeTeam"] and t["periodId"] == period
                        ])
                        match_state["away_timeouts"] = len([
                            t for t in timeouts
                            if not t["isHomeTeam"] and t["periodId"] == period
                        ])

                    new_fouls = [
                        f for f in offenses
                        if f["id"] not in seen_offense_ids
                        and f["matchPlayer"]["matchRole"]["type"] == "Player"
                    ]
                    if new_fouls:
                        f = new_fouls[-1]
                        match_state["last_foul"] = {
                            "player": f["matchPlayer"]["person"]["fullName"],
                            "jersey": f["matchPlayer"]["teamNumber"],
                            "code":   f["offenseType"]["code"],
                            "team":   "home" if f["matchPlayer"]["teamId"] == home_id else "away",
                        }
                    seen_offense_ids = {f["id"] for f in offenses}

                    player_stats = {}
                    for g in goals:
                        pid = g["matchPlayerId"]
                        if pid not in player_stats:
                            player_stats[pid] = {"points": 0, "threes": 0, "fouls": 0}
                        player_stats[pid]["points"] += g["points"]
                        if g["points"] == 3:
                            player_stats[pid]["threes"] += 1
                    for f in offenses:
                        if f["matchPlayer"]["matchRole"]["type"] == "Player":
                            pid = f["matchPlayerId"]
                            if pid not in player_stats:
                                player_stats[pid] = {"points": 0, "threes": 0, "fouls": 0}
                            player_stats[pid]["fouls"] += 1
                    match_state["player_stats"] = player_stats

        except Exception as e:
            match_state["foys_error_count"] = match_state.get("foys_error_count", 0) + 1
            print(f"Poll error: {e}")

        tick += 1
        time.sleep(3)


# ── Flask routes ────────────────────────────────────────────────────────────

def safe_get_matches():
    """Fetch matches from FOYS. Returns (matches, error_message)."""
    try:
        matches = client.get_matches()
        match_state["foys_last_ok_ts"]  = time.time()
        match_state["foys_error_count"] = 0
        return matches, None
    except Exception as e:
        match_state["foys_error_count"] = match_state.get("foys_error_count", 0) + 1
        print(f"[FOYS] get_matches failed: {e}")
        return [], "Geen verbinding met FOYS. Controleer de internetverbinding."


@app.route("/")
def select():
    matches, foys_error = safe_get_matches()
    return render_template("select.html", matches=matches, foys_error=foys_error)


@app.route("/select/<int:match_id>")
def select_match(match_id):
    global seen_offense_ids
    matches, foys_error = safe_get_matches()
    match   = next((m for m in matches if m["id"] == match_id), None)

    if not match:
        return render_template("select.html", matches=matches,
                               foys_error=foys_error or "Wedstrijd niet gevonden."), 404

    seen_offense_ids = set()
    match_state.update({
        "selected":   True,
        "match_id":   match_id,
        "home_id":    match["homeTeamId"],
        "away_id":    match["awayTeamId"],
        "home_name":  match["homeTeamName"],
        "away_name":  match["awayTeamName"],
        "home_score": match["homeScore"],
        "away_score": match["awayScore"],
        "status":     match["status"],
        "home_club":  match["homeTeamOrganisationName"],
        "away_club":  match["awayTeamOrganisationName"],
        "last_foul":  None,
        "foys_event_period": None,
        "home_logo":        match["homeTeamOrganisationUrl"],
        "away_logo":        match["awayTeamOrganisationUrl"],
        "match_date":       match["date"][:10],
        "match_time":       match["startTime"][:5],
        "match_location":   match["accommodationName"],
        "match_court":      match["fieldName"],
    })
    return render_template("select.html", matches=matches, foys_error=foys_error,
                           selected=match_id, message=f"Selected: {match['homeTeamName']} vs {match['awayTeamName']}")


def _age(ts):
    """Seconds since ts, or None if never set."""
    return None if ts is None else round(time.time() - ts, 1)


def system_status():
    """Derived health indicators. Computed at read time so a dead thread
    cannot leave a stale green behind."""
    anatec_age = _age(match_state.get("anatec_last_frame_ts"))
    foys_age   = _age(match_state.get("foys_last_ok_ts"))
    mode       = match_state.get("anatec_mode", "off")

    if mode == "off":
        anatec = "off"
    elif anatec_age is None:
        anatec = "red"
    elif anatec_age < 2:
        anatec = "green"
    elif anatec_age < 10:
        anatec = "amber"
    else:
        anatec = "red"

    if match_state.get("foys_mode") == "mock":
        foys = "off"
    elif not match_state.get("foys_auth_ok"):
        foys = "red"
    elif not match_state.get("selected"):
        # Nothing polls FOYS before a match is chosen — poll() short-circuits
        # on `selected`. Freshness would only measure how long ago a page was
        # loaded, so report the login instead of a meaningless timestamp.
        foys = "idle"
    elif foys_age is None:
        foys = "amber"
    elif foys_age < 15:
        foys = "green"
    elif foys_age < 60:
        foys = "amber"
    else:
        foys = "red"

    if not match_state.get("obs_enabled"):
        obs = "off"
    elif not match_state.get("obs_available"):
        obs = "red"
    elif match_state.get("obs_missing_scenes"):
        obs = "amber"
    else:
        obs = "green"

    return {
        "anatec":       anatec,
        "anatec_age":   anatec_age,
        "anatec_mode":  mode,
        "anatec_port":  match_state.get("anatec_port"),
        "foys":         foys,
        "foys_age":     foys_age,
        "foys_mode":    match_state.get("foys_mode"),
        "foys_errors":  match_state.get("foys_error_count", 0),
        "match_status": match_state.get("status"),
        "selected":     match_state.get("selected"),
        "obs":          obs,
        "obs_scene":    match_state.get("obs_scene"),
        "obs_missing":  match_state.get("obs_missing_scenes") or [],
        "scene_prompt": match_state.get("scene_prompt"),
    }


@app.route("/status")
def status_page():
    """Standalone status card — add as an OBS Custom Browser Dock."""
    response = make_response(render_template("status.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/api/state")
def api_state():
    return jsonify({**match_state, "system": system_status()})

@app.route("/api/players")
def api_players():
    """Returns player roster with live stats for both teams."""
    if match_state.get("_mock_players"):
        return jsonify(match_state["_mock_players"])

    if not match_state["selected"]:
        return jsonify([])

    match_id = match_state["match_id"]
    try:
        matches = client.get_matches()
        match = next((m for m in matches if m["id"] == match_id), None)
        if not match:
            return jsonify([])

        stats = match_state.get("player_stats", {})
        result = []

        for team_key in ["homeTeamMatchPlayers", "awayTeamMatchPlayers"]:
            team = "home" if team_key == "homeTeamMatchPlayers" else "away"
            for p in match[team_key]:
                if p["matchRole"]["type"] != "Player":
                    continue
                pid = p["id"]
                s = stats.get(pid, {"points": 0, "threes": 0, "fouls": 0})
                result.append({
                    "team":    team,
                    "jersey":  p["teamNumber"],
                    "name":    p["person"]["fullName"],
                    "captain": p["isCaptain"],
                    "points":  s["points"],
                    "threes":  s["threes"],
                    "fouls":   s["fouls"],
                })

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/overlay")
def overlay():
    response = make_response(render_template("overlay.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/overlay/anatec")
def overlay_anatec():
    response = make_response(render_template("overlay_anatec.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/overlay/foys")
def overlay_foys():
    response = make_response(render_template("overlay_foys.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/overlay/final")
def overlay_final():
    response = make_response(render_template("overlay_final.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/overlay/wide")
def overlay_wide():
    response = make_response(render_template("overlay_wide.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/overlay/box")
def overlay_box():
    response = make_response(render_template("overlay_box.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/overlay/stats")
def overlay_stats():
    response = make_response(render_template("overlay_stats.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--anatec", choices=["serial", "auto", "simulate", "off"],
                    default="simulate",
                    help="Anatec reader mode: serial (needs --port), auto (discover port), simulate, off")
    ap.add_argument("--port", default="/dev/tty.usbserial-1110",
                    help="Serial port for Anatec")
    ap.add_argument("--demo", action="store_true",
                    help="Use FOYS demo environment")
    ap.add_argument("--mock", action="store_true", help="Load mock data, skip FOYS auth")
    ap.add_argument("--finalised", action="store_true", help="Set mock status to Final")
    ap.add_argument("--no-obs", action="store_true",
                    help="Dry run for scene control: log decisions, do not contact OBS")
    args = ap.parse_args()

    if args.mock:
        import json
        with open("mock_data.json") as f:
            mock = json.load(f)
        match_state.update(mock["match"])
        match_state.update(mock["anatec"])
        match_state["status"] = "Final" if args.finalised else "InProgress"
        match_state["_mock_players"] = mock["players"]
        match_state["foys_mode"] = "mock"
        print("Running in MOCK mode" + (" — finalised" if args.finalised else " — InProgress"))
    else:
        if args.demo:                                 # ← add
            os.environ["FOYS_DEMO_MODE"] = "true"    # ← add
            match_state["foys_mode"] = "demo"
            print("Using FOYS demo environment") 
        print("Authenticating with FOYS...")
        try:
            client.authenticate()
            match_state["foys_auth_ok"] = True
        except Exception as e:
            match_state["foys_auth_ok"] = False
            print(f"[FOYS] Authentication failed: {e}")
            print("Continuing without FOYS — Anatec data will still work.")
        print("Starting FOYS background poller...")
        t = threading.Thread(target=poll, daemon=True)
        t.start()

    if args.anatec != "off":
        print(f"Starting Anatec reader in {args.anatec} mode...")
        from reader import start_reader
        start_reader(mode=args.anatec, port=args.port)

    scene_names = list(dict.fromkeys(SCENES.values()))
    if args.no_obs:
        print("Scene control in dry-run mode (--no-obs): decisions are logged, OBS is not contacted")
        obs = DryObs(scene_names, start=SCENES["court"])
    else:
        print("Starting scene control...")
        obs = ObsClient(host=os.getenv("OBS_WEBSOCKET_HOST", "localhost"),
                        port=int(os.getenv("OBS_WEBSOCKET_PORT", "4455")),
                        password=os.getenv("OBS_WEBSOCKET_PASSWORD"))
    director = SceneDirector(SCENES, stats_after=STATS_AFTER_PERIODS,
                             stats_delay=STATS_DELAY_S)
    controller = SceneController(match_state, obs, director, SCENES,
                                 live=not args.no_obs)
    threading.Thread(target=controller.run, daemon=True).start()

    print("Server running at http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)
