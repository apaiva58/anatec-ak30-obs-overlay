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

    def get_offenses(self, match_id):
        result = self._get(f"/matches/{match_id}/offenses")
        if isinstance(result, dict) and "items" in result:
            return result["items"]
        return result

    def get_timeouts(self, match_id):
        result = self._get(f"/matches/{match_id}/timeouts")
        if isinstance(result, dict) and "items" in result:
            return result["items"]
        return result
