# FOYS DWF API — Overlay Integration

This document describes how the FOYS DWF API is used in the
Almere Pioneers scoreboard overlay stack.

Statements marked "verified" were observed in live responses on the
date given. Anything unmarked is carried over from earlier versions of
this document and has not been re-checked. When the API behaves
unexpectedly, a HAR export from the DWF web client (Safari Web
Inspector, Network tab) shows what the client itself sends; that is the
only documentation guaranteed to be correct. See probes/README.md.

---

## Architecture

```
DWF tablet (scorer's table)
        down - operator input
api.foys.io (NBB server)
        down - REST API polled every 3 seconds
scoreboard/server.py (Flask)
        down - /api/state + /api/players
overlay.html (OBS Browser Source)
```

---

## Data Priority — Combined Anatec + FOYS Input

When both Anatec serial and FOYS API are active, each data source
has a defined priority for each field.

### Anatec is leading

  Score        Anatec updates instantly when the operator presses
               the button. FOYS score has human latency (DWF operator
               must enter the goal). For a live stream the displayed
               score must match the physical scoreboard in real time.

  Clock        Only available from Anatec. FOYS does not transmit
               the game clock.

  Period       Physical scoreboard is authoritative.

  Timeouts     Physical scoreboard is authoritative.

### FOYS is leading

  Fouls        FOYS captures individual player fouls with names,
               jersey numbers and foul codes. Richer than Anatec
               team foul count.

  Club logos   Available from FOYS match object only.

  Match info   Date, location, court - from FOYS match object.

  Player stats Calculated from FOYS goals and offenses during the
               game. Running in the background, displayed at Final.

### FOYS score role

  The FOYS score is the official NBB record - entered by the
  certified DWF operator. It is used for player stats calculation
  and shown in the final stats table. It is not used for the live
  score display when Anatec is connected.

### Fallback

  When Anatec is not connected, the overlay falls back to FOYS
  score for the live display. This covers FOYS-only deployments.

  In overlay.html:

    const homeScore = s.anatec_connected
        ? s.anatec_home_score
        : s.home_score;

---

## Authentication

The server authenticates once at startup using OAuth2 password grant.
Credentials are stored in .env (never committed to git).

```
POST https://api.foys.io/foys/api/v1/token
grant_type=password
username=...
password=...
organisationId=...
```

Returns a JWT token used as Bearer header on all subsequent calls.
Token is automatically refreshed on 401 response.

See: scoreboard/foys.py - FoysClient.authenticate()

---

## Match Selection

On startup the server fetches all matches for the account:

```
GET /competition/dmf-api/v1/matches
```

Returns an array of matches - past, live and upcoming.
The volunteer selects the correct match via the web UI at /.

Key fields used:
- id                          matchId for subsequent calls
- status                      Planned, InProgress, Final
- homeTeamName / awayTeamName
- homeTeamOrganisationName / awayTeamOrganisationName
- homeTeamOrganisationUrl / awayTeamOrganisationUrl
- homeTeamId / awayTeamId
- homeScore / awayScore
- date / startTime / accommodationName / fieldName

See: scoreboard/server.py - select_match()

---

## Live Polling (every 3 seconds)

Three endpoints are polled continuously during the game.

### Goals

```
GET /competition/dmf-api/v1/matches/{matchId}/goals
```

Returns array of all scoring events. Score is calculated client-side:

```python
home_score = sum(g["points"] for g in goals if g["teamId"] == home_id)
```

Fields used:
- teamId          which team scored
- points          0, 1, 2 or 3
- penalty         true = free throw
- periodId        which quarter
- matchPlayerId   for player stats

### Offenses

```
GET /competition/dmf-api/v1/matches/{matchId}/offenses/all
```

Returns a plain list of every offense in the match, as flat records
(verified 4 Oct 2026, match 501153: 34 rows):

- id                        unique per offense
- matchPlayerId             join key into the match roster
- periodId                  14..17 = Q1..Q4 (see Period Mapping)
- offenseTypeId             e.g. 19 = P2, 21 = P0
- offenseTypeCode           P0, P1, P2, FL ... (see Offense codes)
- offenseTypeGroupCode      P for personal fouls
- matchId

There is no matchLogId on these rows, and no embedded matchPlayer or
offenseType object.

Do NOT use plain /offenses. It returns {"totalCount": N, "items": [...]}
hard-capped at the FIRST 10 rows, oldest first, and nothing moves or
enlarges the page (verified 4 Oct 2026, match 501153: totalCount 34,
items 10; 45 query-parameter and header forms tried, all ignored; the
response headers carry no paging hints). Everything after the tenth
offense of a match is invisible through it. On 3 Oct 2026 this stopped
foul popups and per-player foul counts after the tenth foul of the
match. The only filter plain /offenses honours is ?teamId=<id>
(totalCount becomes that team's count, still capped at 10 rows);
periodId, matchPlayerId, offenseTypeId and variants are ignored.

Why the cap exists (inference, not confirmed): the responses carry an
Application Insights request-context header, which points to an ASP.NET
service, and {totalCount, items} with a default page of 10 is the usual
list scaffold there. The paging parameters were probably never wired
up. The DWF client never calls plain /offenses; it goes straight to
/offenses/all, which looks like a bypass added beside the capped route.
/goals has no envelope at all.

The client joins roster data back in. FoysClient.get_offenses() fetches
the roster from GET /matches/{id} (homeTeamMatchPlayers and
awayTeamMatchPlayers, matched on matchPlayerId) and rebuilds the shape
callers expect:

- f["matchPlayer"]   teamId, teamNumber, matchRole.type, person.fullName
- f["offenseType"]   id, code, group

The roster is cached per match. An unknown matchPlayerId triggers one
refresh and is then remembered, so it does not cost a request per poll.
Unknown players are kept with matchRole.type "Unknown" so the
Player-only filters skip them.

Used for team foul count per period and player foul count. Only fouls
where matchPlayer.matchRole.type == "Player" count towards team fouls;
coach and bench technicals are excluded by that role filter.

Offense codes (verified 4 Oct 2026, GET /offense-types?sorting=position+asc,
the call the DWF client makes; 12 rows):

  code  group  name
  T     TF     Technische fout speler categorie 1
  T2    TF     Technische fout speler categorie 2
  P3    P      Persoonlijke fout 3
  P2    P      Persoonlijke fout 2
  P1    P      Persoonlijke fout 1
  P0    P      Persoonlijke fout 0
  C     TF     Technische fout coach categorie 1
  B     TF     Technische fout bank categorie 1
  DI    SF     Disruptive fout speler
  FL    SF     Flagrant fout speler
  D     SF     Diskwalificatie
  F     SF     Vechten

Groups: P personal, TF technical, SF serious (disruptive, flagrant,
disqualifying, fighting). The digit on P0..P3 is part of the code, not
a count of fouls: a player's first foul can be P2.

Why this differs from earlier versions of this document: the FIBA
Official Basketball Rules 2026 took effect on 1 October 2026 and changed
the foul types (FIBA Rules Changes v1.1, July 2026; see References). The
unsportsmanlike foul (U) is replaced by a disruptive foul (DI) and a
flagrant foul (FL), Art. 37 and 38. Technical fouls are split into
category 1 and category 2, Art. 36, which is why there is T and T2. The
earlier list (T, TC, TB, U, D, F, P1-P3) predates this, and the match of
3 Oct 2026 already used FL. FIBA's text does not explain TC and TB; its
scoresheet markings for head-coach and bench technicals are C and B. It
also adds a marking BD (disqualifying technical against an accompanying
delegation member), which has no row in the table above.

Which offenses count as team fouls. calculate_fouls() counts every
offense whose matchPlayer.matchRole.type is "Player", whatever its
code. Verified against the NBB match form for 501153: this reproduces
the form's team-foul row in all four quarters (Pioneers 3/3/6/7,
Felloo 3/3/5/4), including Q3 where a flagrant foul (FL) must be
counted to reach 6. Verified against FIBA Rules 2026 (Rules Changes
v1.1): a player technical of either category (T, T2) counts as a team
foul (Art. 36.3.1), as do a disruptive foul (DI, Art. 37.2.1) and a
flagrant foul (FL, Art. 38.2.1). A technical foul by anyone on the
bench (C, B) is charged to the head coach and does NOT count (Art.
36.3.1). The role filter excludes those only if FOYS attaches them to
the coach's matchPlayer, which has not been observed. Unverified: D
(disqualifying) and F (fighting), which the changes document does not
cover.

The foul popup prints the raw code ("Fout: <name> (#<jersey>) - P2"),
so viewers see P0, FL, DI and so on verbatim.

### Timeouts

```
GET /competition/dmf-api/v1/matches/{matchId}/timeouts
```

Returns a plain list (verified 4 Oct 2026, match 501153: 3 items), not
an envelope. /timeouts/all is 404. FoysClient.get_timeouts() accepts
either shape. Not checked: whether it envelopes and caps when more than
ten exist, which a match rarely reaches.

Fields used:
- isHomeTeam    true or false
- periodId

### Other endpoints seen (verified 4 Oct 2026, match 501153)

```
GET /matches/{matchId}                 match detail and roster
GET /matches/{matchId}/logs            unified play-by-play
GET /offense-types?sorting=position+asc    offense code table
```

- /matches/{id} carries homeTeamMatchPlayers and awayTeamMatchPlayers
  (id, teamId, teamNumber, matchRole, person, totalPoints). There is no
  per-player foul field, only points.
- /logs returned 132 rows: 91 goal rows, 34 offenses, 3 timeouts and 4
  other events. One endpoint for the whole game, in order. Not used yet.
- /goals is a plain list with no envelope and no cap.

The DWF web client lists only live and upcoming matches, so a finalised
match cannot be opened there to watch how it fetches. Use the demo
organisation (FOYS_DEMO_MODE=true) for that. Demo match ids return 404
under live credentials, and live ids under demo credentials.

---

## Status Check (every 9 seconds)

```
GET /competition/dmf-api/v1/matches
```

Full match list re-fetched to detect status change to Final. The match
stays in the list for the rest of the day after it is finalised (observed
by Antonio on match days); 501153 was gone from it four days later.

The server stamps `final_seen_ts` with its own clock when it first sees the
status turn Final (`state.set_status`). That time is shown on the closing
slate as "Afgesloten om". It is up to one status poll (~9 s) late, and it is
not set for a match that was already Final when selected.

### What FOYS knows about a finalised match (verified 7 Oct 2026, match 501153)

`probes/probe_final.py`:

- `/matches/{id}` has no finalisation time: only `date` (midnight UTC),
  `startTime` and `status`. `playingTime`, `period`, `remarks` and
  `matchDisciplinaryStatus` were null.
- No match number besides `id`: no federation number, code or external id.
  Whether the NBB site shows the same number is not checked.
- `/logs` rows are goals, offenses or timeouts, told apart by which of
  `matchGoalId`, `matchPlayerOffenseId`, `matchTimeoutId` is set. Each row
  carries `date` (UTC wall clock, ms), `time` and `periodPosition`. The last
  rows are the last basket of the match; there is no "match closed" row.

---

## Player Stats Endpoint

```
GET /api/players  (served by Flask, not FOYS)
```

Combines:
- Roster from last /matches call (name, jersey, captain)
- Live stats calculated from goals and offenses:
  - points    sum of goal points per player
  - threes    count of 3-point goals per player
  - fouls     count of player offenses

Player stats run in the background during the game and are
displayed automatically when status becomes Final.

---

## Period Mapping

FOYS uses numeric period IDs:

  periodId 14   1e kwart
  periodId 15   2e kwart
  periodId 16   3e kwart
  periodId 17   4e kwart
  periodId 18+  Overtime

Period ids rise through the game, so the highest periodId seen across
goals and offenses is the current period. server.py current_period()
uses exactly that. It does not rank events by matchLogId, which
/offenses/all rows do not carry.

---

## Overlay Behaviour

overlay.html polls /api/state every 3 seconds.

During game (status != Final):
- Score from Anatec when connected, FOYS as fallback
- Clock from Anatec serial feed
- Period from FOYS (updated on first event per quarter)
- Team fouls from FOYS per period
- Club logos from FOYS
- Flashing timeout popup for 60 seconds on new timeout
- Foul popup for 4 seconds on new player foul
- Bonus indicator in red when team fouls >= 4 in current period

On Final (status == Final):
- Scorebar fades out
- Final stats table fades in automatically
- Shows FOYS official score
- Player points, 3-pointers, fouls sorted by points

---

## Clock

The FOYS API does not transmit the game clock. No WebSocket
connection detected in the DWF browser app. The clock runs
client-side in JavaScript from a start timestamp.

The overlay reads anatec_clock from /api/state which comes
from the Anatec AK30 serial feed when connected.
When Anatec is not connected, clock shows a dash.

---

## Known Limitations

- Period update delayed until first goal or foul in new period
- Scores above 99 not tested (Anatec protocol open question)
- FOYS score latency expected - Anatec score used for live display
- API requires authentication - returns 401 without token
- FOYS server load on Saturday mornings may cause polling delays
- Plain /offenses is capped at 10 rows with no way round it; use
  /offenses/all (see Offenses)
- /offenses/all rows are flat: no matchLogId, no embedded matchPlayer
- A transient poll error "'>' not supported between instances of
  'NoneType' and 'int'" occurred 4 times in the 3 Oct 2026 match log,
  each time for one cycle. It is consistent with a null matchLogId on a
  freshly created event, but that was never observed directly. The old
  current_period() ranked by matchLogId; the current one does not, so it
  cannot recur from that cause.

---

## Files

  scoreboard/foys.py       FOYS API client - auth, fetch, roster join
  scoreboard/server.py     Flask server - poll loop and routes
  scoreboard/state.py      Shared in-memory match state
  templates/overlay.html   Combined live and final overlay
  templates/select.html    Match selection UI
  probes/                  Read-only API diagnostics (probes/README.md)
  .env                     Credentials (not in git)

---

## References

- FOYS developer portal: https://developers.foys.tech
- FOYS DWF demo: https://dwf.basketball.nl/matches/487998/progress
- FIBA Official Basketball Rules 2026, Rules Changes v1.1 (July 2026):
  https://assets.fiba.basketball/image/upload/documents-corporate-fiba-official-rules-2026-rule-changes-v1-1-en.pdf
- Probe scripts and what each one answered: probes/README.md
- NBB Basketball Nederland: https://www.basketball.nl