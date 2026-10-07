# probes

Read-only diagnostics against the FOYS DWF API. None of these write
anything. All use the same `FoysClient` and `.env` as `server.py`.

Run from the repo root, e.g. `python3 probes/probe_all.py 501153`.

| script | question it answers |
|---|---|
| `probe_offenses.py` | What does `/offenses` return for a match — count, ids, codes, shape? |
| `probe_paging.py` | Does any size parameter enlarge the 10-row page? (none did) |
| `probe_paging2.py` | Does any offset, cursor, sort or header move it? (none did) |
| `probe_filter.py` | Which filters are honoured? (`teamId` yes; period, player, type no) |
| `probe_detail.py` | Does `/matches/{id}` carry per-player fouls? (no, only `totalPoints`) |
| `probe_all.py` | Compare `/offenses` vs `/offenses/all`, plus `/timeouts`, `/logs`, `/goals` |
| `probe_final.py` | What does FOYS hold for a finalised match: a match number, a close time? (neither; see `docs/foys-api.md`) |

Written 4 Oct 2026 while tracing why foul popups stopped after the tenth
foul of the 3 Oct match. Findings are recorded in `docs/foys-api.md`.

When the API does something unexpected, the fastest route to the truth is
a HAR from the DWF web client (Safari Web Inspector → Network → Export),
not parameter guessing: the client's own requests are the only
documentation guaranteed to be correct.
