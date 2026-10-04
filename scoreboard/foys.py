"""
foys.py
=======
FOYS DWF API client.
Handles authentication and data fetching.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.foys.io/competition/dmf-api/v1"
AUTH_URL = "https://api.foys.io/foys/api/v1/token"

HEADERS = {
    "Origin":  "https://dwf.basketball.nl",
    "Referer": "https://dwf.basketball.nl/",
    "Accept":  "application/json",
}


class FoysClient:

    def __init__(self):
        self.token = None
        self._rosters = {}     # match_id -> {matchPlayerId: matchPlayer dict}
        self._unresolved = set()   # matchPlayerIds already refreshed for, still unknown

    def authenticate(self):
        demo = os.getenv("FOYS_DEMO_MODE", "false").lower() == "true"
        if demo:
            HEADERS["demo-mode"] = "true"
        else:
            HEADERS.pop("demo-mode", None)

        org_id = os.getenv("FOYS_ORGANISATION_ID_DEMO") if demo else os.getenv("FOYS_ORGANISATION_ID")

        response = requests.post(AUTH_URL, data={
            "grant_type":     "password",
            "username":       os.getenv("FOYS_USERNAME"),
            "password":       os.getenv("FOYS_PASSWORD"),
            "organisationId": org_id,
        }, headers=HEADERS)
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def _headers(self):
        return {**HEADERS, "Authorization": f"Bearer {self.token}"}

    def _get(self, path):
        response = requests.get(f"{BASE_URL}{path}", headers=self._headers())
        if response.status_code == 401:
            self.authenticate()
            response = requests.get(f"{BASE_URL}{path}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def get_matches(self):
        return self._get("/matches")

    def get_goals(self, match_id):
        return self._get(f"/matches/{match_id}/goals")

    def get_match(self, match_id):
        return self._get(f"/matches/{match_id}")

    def _roster(self, match_id, refresh=False):
        """matchPlayerId -> matchPlayer dict (teamId, teamNumber, person,
        matchRole), from the match detail. Cached per match; the sheet is
        fixed once the match starts, so one fetch normally suffices."""
        if refresh or match_id not in self._rosters:
            m = self.get_match(match_id)
            roster = {}
            for side in ("homeTeamMatchPlayers", "awayTeamMatchPlayers"):
                for p in m.get(side) or []:
                    roster[p["id"]] = p
            self._rosters[match_id] = roster
        return self._rosters[match_id]

    def get_offenses(self, match_id):
        """All offenses for a match, each with matchPlayer and offenseType
        embedded so callers can read f["matchPlayer"]["teamId"] etc.

        /offenses returns a {totalCount, items} envelope hard-capped at the
        first 10 rows, and no paging parameter is honoured. /offenses/all is
        what the DWF web client calls and returns every row (verified
        4 oct 2026, match 501153: 10 vs 34) -- but as flat records:
        matchPlayerId and offenseTypeCode only, nothing embedded. The join
        below restores the shape the capped endpoint used to provide.
        """
        rows = self._get(f"/matches/{match_id}/offenses/all")
        if isinstance(rows, dict) and "items" in rows:
            rows = rows["items"]

        roster = self._roster(match_id)
        refreshed = False
        out = []
        for r in rows:
            mpid = r.get("matchPlayerId")
            mp = roster.get(mpid)
            if mp is None and not refreshed and mpid not in self._unresolved:
                roster = self._roster(match_id, refresh=True)
                refreshed = True
                mp = roster.get(mpid)
                if mp is None:
                    self._unresolved.add(mpid)
            if mp is None:
                # Unknown player: keep the row (counts stay honest) but mark
                # the role so the Player-only filters skip it.
                mp = {"id": r.get("matchPlayerId"), "teamId": None, "teamNumber": None,
                      "matchRole": {"type": "Unknown"}, "person": {"fullName": "?"}}
            out.append({
                **r,
                "matchPlayer": mp,
                "offenseType": {
                    "id":    r.get("offenseTypeId"),
                    "code":  r.get("offenseTypeCode"),
                    "group": r.get("offenseTypeGroupCode"),
                },
            })
        return out

    def get_timeouts(self, match_id):
        result = self._get(f"/matches/{match_id}/timeouts")
        if isinstance(result, dict) and "items" in result:
            return result["items"]
        return result
