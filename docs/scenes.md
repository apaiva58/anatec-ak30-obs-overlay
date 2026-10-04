# Scene control

How OBS changes scene during a match. Decisions: `scoreboard/scene_logic.py`
(pure logic, tested). OBS side: `scoreboard/scene_control.py`. Settings: `.env`
(see `.env.example`). Tests: `python3 tests/test_scene_logic.py`.

## What happens

| trigger | action | status dock says |
|---|---|---|
| Clock runs down to 0:00 in a period listed in `OBS_STATS_AFTER_PERIODS` (default: 2) | halftime scene after `OBS_STATS_DELAY` | "Rust. Naar WIDE bij start periode 3." |
| First play after that break | court scene, only if the halftime scene is still on air | message clears |
| You pick a scene in OBS yourself | accepted, nothing fights it | message clears |
| End of period 4 | nothing on air | "Einde periode 4: wacht op afsluiten in FOYS." |
| FOYS status turns Final | final scene (`OBS_SCENE_FINAL`) | "Wedstrijd afgesloten." |
| End of any other period | nothing | none |

"Play" means evidence, never the clock (scorers run the break clock in
different ways and advance the period at different moments):

- FOYS: a goal, foul or timeout with a `periodId` higher than the period that
  ended. FOYS periodId is 13 + the console period (14..17 = quarters 1..4,
  verified on match 501153). A late entry for the old period does not count.
- Console: a score, team-foul or timeout counter going up, but not in the first
  30 s after the buzzer (the table is still entering the last events).

A buzzer only counts if the period it ends has seen play, and only once per
period. That rejects the end of a break countdown. The console period going
back (e.g. 4 to 1) starts a new game and clears this.

## The buzzer

The console never shows 0:00.0 at the end of a period. It leaves tenths mode
after 0:00.1 and shows plain 0:00 in minute mode. The detector wants a clock
that was running and then lands there. Triggering on "seconds == 0" fires
while play is still on (the clock can park at 0:00.6), and one real capture
has a stray 0:00.0 frame at the 1 s rollover. See `scene_logic.py` and the
embedded real frames in `tests/test_scene_logic.py`.

## Changing it later

Edit `.env`, restart the server. No code change.

- A "Final Stats" scene: create it in OBS (date, producers, copyright,
  disclaimer, whatever you place), then `OBS_SCENE_FINAL="Final Stats"`.
- Stats at every break: `OBS_STATS_AFTER_PERIODS=1,2,3`.
- More or less time on court after the buzzer: `OBS_STATS_DELAY=3`.

The dock row "Scène" shows the scene OBS really has on air. If a configured
scene does not exist in OBS the dock says which one, and the server does not
try to switch to it.

## Watching it at the desk

```
OBS_STATS_AFTER_PERIODS=1 python3 scoreboard/server.py --anatec simulate --mock --no-obs
```

`--no-obs` is a dry run: decisions are logged (`[Scenes]`, `[OBS] ... (dry run)`)
and shown on the dock, OBS is not contacted. The simulator plays period 1 only,
hence `OBS_STATS_AFTER_PERIODS=1`; it ends the period like the real console
does. About 20 s in: the prompt, 2 s later the halftime scene, and when the
next pass starts scoring, the court again.

## Known limits

- Restarting the server mid-break leaves OBS on the stats scene until you
  switch by hand; the dock shows the scene that is on air. The server only
  returns to the court for a break it saw begin.
- Not verified on the AK30: whether resetting a counter at the break can pass
  through a higher value (counting up past 9). That would look like play.
  The `[Scenes] play resumed (...)` log line names the evidence used.
- A quarter without a single goal, foul or timeout is not treated as played,
  so its end does not switch.
- How long the desk takes to finalise after the last buzzer has not been
  measured. The final scene appears when FOYS says Final, whenever that is.
- If OBS runs on another machine and is unreachable, each reconnect attempt
  can block the controller for up to 3 s. With OBS on the same Mac it fails
  at once.
