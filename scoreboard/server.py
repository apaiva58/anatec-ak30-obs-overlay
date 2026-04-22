"""
server.py
=========
Flask server — serves match selection UI, overlay data endpoint,
and runs the FOYS background poller.

Usage:
    python scoreboard/server.py
"""

import threading
import time
from flask import Flask, jsonify, render_template, make_response
from foys import FoysClient
from state import match_state

app = Flask(__name__, template_folder="../templates")
client = FoysClient()


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
    events = (goals or []) + (offenses or [])
    if not events:
        return None
    return max(events, key=lambda e: e.get("matchLogId", 0)).get("periodId")


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
                    except Exception:
                        pass

                # only when not Final
                if match_state["status"] != "Final":
                    goals    = client.get_goals(match_id)
                    offenses = client.get_offenses(match_id)
                    timeouts = client.get_timeouts(match_id)
                    period   = current_period(goals, offenses)

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
            print(f"Poll error: {e}")

        tick += 1
        time.sleep(3)


# ── Flask routes ────────────────────────────────────────────────────────────

@app.route("/")
def select():
    matches = client.get_matches()
    return render_template("select.html", matches=matches)


@app.route("/select/<int:match_id>")
def select_match(match_id):
    global seen_offense_ids
    matches = client.get_matches()
    match   = next((m for m in matches if m["id"] == match_id), None)

    if not match:
        return "Match not found", 404

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
        "home_logo":        match["homeTeamOrganisationUrl"],
    "away_logo":        match["awayTeamOrganisationUrl"],
    "match_date":       match["date"][:10],
    "match_time":       match["startTime"][:5],
    "match_location":   match["accommodationName"],
    "match_court":      match["fieldName"],
    })
    return render_template("select.html", matches=matches,
                           selected=match_id, message=f"Selected: {match['homeTeamName']} vs {match['awayTeamName']}")


@app.route("/api/state")
def api_state():
    return jsonify(match_state)

@app.route("/api/players")
def api_players():
    """Returns player roster with live stats for both teams."""
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


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--anatec", choices=["serial", "simulate", "off"],
                    default="simulate", help="Anatec reader mode")
    ap.add_argument("--port", default="/dev/tty.usbserial-1110",
                    help="Serial port for Anatec")
    args = ap.parse_args()

    print("Authenticating with FOYS...")
    client.authenticate()

    print("Starting FOYS background poller...")
    t = threading.Thread(target=poll, daemon=True)
    t.start()

    if args.anatec != "off":
        from reader import start_reader
        start_reader(mode=args.anatec, port=args.port)

    print("Server running at http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)