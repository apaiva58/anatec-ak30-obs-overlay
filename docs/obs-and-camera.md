# OBS, camera and streaming

How the stream is put together at Almere Pioneers: OBS scenes and sources,
the server's connection to OBS, the second camera on an iPhone, and the
YouTube settings. Scene switching rules themselves are in `scenes.md`.

Versions this was done with: OBS Studio 32.1.1 on macOS 26.6.1, Python
3.13 (M1) and 3.9.6 (stock macOS), LensLink 1.16.0 (1083) on an iPhone 7
running the last iOS it supports.

---

## Scenes and sources

The scene collection has four scenes. Names must match `.env` exactly,
accents included; the status dock lists any configured scene OBS does not
have.

| Scene | Holds | Switched by the server? |
|---|---|---|
| `Scène 1: BOX overlay` | camera + Browser Source `/overlay/box` | no, operator only |
| `Scène 2: WIDE Overlay` | camera + Browser Source `/overlay/wide` | yes: `OBS_SCENE_COURT` (play) |
| `Scène 3 Macbook Camera` | the MacBook's own camera, no overlay | no, operator only |
| `Scène 4: STATS` | camera + Browser Source `/overlay/stats` | yes: `OBS_SCENE_HALFTIME` and, until a `Final Stats` scene exists, `OBS_SCENE_FINAL` |

The server only ever switches to the court, halftime and final scenes from
`.env`. A scene the operator picks by hand is left alone (`scenes.md`).

Each Browser Source: URL `http://localhost:5001/overlay/<route>`, width and
height equal to the canvas (1920 x 1080), nothing else to set. The pages are
transparent outside their own elements. Routes:

| Route | Shows |
|---|---|
| `/overlay/wide` | bottom bar: score, period, clock, team fouls, timeouts, foul and timeout popups |
| `/overlay/box` | compact corner box |
| `/overlay/stats` | per-player points, threes, fouls (break and final) |
| `/overlay/final` | final score |
| `/overlay` | the older combined page: live bar that fades to the final table |
| `/overlay/anatec`, `/overlay/foys` | one source only, for diagnosis |

A Browser Source keeps polling `/api/state` while the server is down and
recovers by itself when it comes back; no need to refresh it.

### Status dock

Docks > Custom Browser Docks, URL `http://localhost:5001/status`. It shows
serial link, FOYS state, selected match, the scene OBS has on air, whether
OBS is streaming and recording, and the prompts from scene control ("Rust.
Naar WIDE bij start periode 3."). Keep it visible on the operator's screen;
it is the only place those prompts appear.

Stream and Opname are read from OBS every 2 s and are read-only: the server
never starts or stops either. They read "Uit" in red once a match is
InProgress and nothing is going out or being written, which is the case the
rows exist for. Stream turns amber while OBS is reconnecting or skipping
frames between two reads. Both show "—" when OBS itself is off or
unreachable, since the Scène row already reports that.

---

## WebSocket (scene switching)

OBS: Tools > WebSocket Server Settings. Enable the server, port 4455, set a
password, copy it into `.env` as `OBS_WEBSOCKET_PASSWORD`. Host and port are
only needed in `.env` if OBS runs on another machine.

The server connects at start and keeps the connection; if OBS is closed or
not yet open, the dock shows OBS as not reachable and the server retries
every few seconds without blocking anything else. OBS on another machine
that is unreachable costs up to 3 s per retry (`scenes.md`, Known limits).

`--no-obs` is a dry run: decisions are logged and shown on the dock, nothing
is sent. Use it at the desk and for a first test at the hall.

Not yet done: a full match with the server switching a real OBS. The two
matches streamed so far ran before scene control was rebuilt. First real
test: run with `--anatec auto` and without `--no-obs`, watch the dock, and
be ready to switch by hand.

---

## Second camera: iPhone over WiFi with LensLink

LensLink (https://github.com/MyNamesEMurray/LensLink, GPL-2.0-or-later)
turns an iPhone into a camera source for OBS on macOS. iOS 15 or newer, so
an old phone does. Here: an iPhone 7 on its last supported iOS, LensLink
1.16.0 (1083), on the venue WiFi.

Install

- Mac: the installer is not notarised; after the first blocked launch, allow
  it in System Settings > Privacy & Security.
- iPhone: install the app, join the same WiFi as the Mac.
- OBS: LensLink adds a source and a dock. From the dock the phone's capture
  can be started remotely, which worked on match day.

Connecting

The phone's IP address is typed by hand in OBS. The venue network (TopSport
Event Almere) hands out 10-minute DHCP leases and has client isolation off,
so phone and Mac can see each other, but the phone's address can change
between warm-up and tip-off. Two ways to keep it stable:

- on the iPhone, WiFi > the network > turn "Private Wi-Fi Address" off, so
  the router sees the same device each time and tends to give it the same
  lease;
- or put phone and Mac on their own MiFi, which also removes the venue WiFi
  from the chain.

Measured upload on the venue WiFi: about 57 Mbit/s, ample for one 1080p
stream.

---

## YouTube

Stream to YouTube from OBS with the usual stream key. Latency setting
"Normal" measured 18.5 s between the hall and the YouTube player. Low or
Ultra-low cut that at the cost of stability on WiFi; Normal has been fine.

Match recordings on YouTube show player names from FOYS. Clubs streaming
youth matches should decide what they publish; the club does that per team.

---

## Local recording

Alongside the stream, OBS records to `~/Movies` (Uitvoer > Opnemen). The
recording uses the stream's encoder, so it costs almost no extra CPU and
matches the stream's bitrate: about 4.5 GB per hour at 10000 Kbps. With that
encoder OBS cannot pause a recording; stopping and starting it between
matches is what works. The server does not control it — the dock only
reports whether it is running.

---

## Checklist of the hardware at the table

- MacBook with OBS, the server, and the AK30 on USB
- Android tablet with the DWF app (the scorer's, not part of this project)
- iPhone with LensLink on WiFi, on a clamp with a view of the court
- The MacBook sits at the officials' table next to the AK30: balls, bumps
  and drinks are a real risk. A relay from the table to a Mac further away
  is an idea, not a plan.
