"""
scene_control.py
================
Glue between match_state, the SceneDirector (scene_logic.py) and OBS.

- keeps ONE persistent obs-websocket connection and reconnects if it drops
- reads which scene is really on air once a second, so a switch made by
  hand in OBS is seen and respected
- reads stream and recording status every two seconds, read-only: the
  server never starts or stops either
- checks at connect (and every few seconds after) that the configured
  scenes exist in OBS, and reports the ones that do not
- a switch OBS refuses is retried, so a closed OBS or a wrong password
  cannot leave the wrong scene on air for good
- publishes obs_enabled, obs_available, obs_scene, obs_missing_scenes,
  obs_stream_* / obs_record_* and scene_prompt into match_state for the
  status dock

All OBS calls happen on the one controller thread, so no locking is needed.
`step(now)` does one pass without sleeping; `run()` loops it. Tests drive
`step` directly with a fake OBS.
"""

import logging
import time

from scene_logic import Snapshot

# obsws-python prints a 15-line traceback on every failed connect. The
# failure is handled here and shown on the dock, so keep the library quiet.
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
logging.getLogger("obsws_python").propagate = False


class ObsClient:
    """One persistent obs-websocket connection."""

    def __init__(self, host="localhost", port=4455, password=None, timeout=3):
        self.host, self.port = host, port
        self.password, self.timeout = password, timeout
        self._cl = None
        self.error = None

    @property
    def connected(self):
        return self._cl is not None

    def connect(self):
        try:
            import obsws_python as obs
            self._cl = obs.ReqClient(host=self.host, port=self.port,
                                     password=self.password, timeout=self.timeout)
            self.error = None
            return True
        except Exception as e:
            self._cl = None
            self.error = f"{type(e).__name__}: {e}"
            return False

    def drop(self):
        cl, self._cl = self._cl, None
        if cl is not None:
            try:
                cl.disconnect()
            except Exception:
                pass

    def scene_names(self):
        return [s["sceneName"] for s in self._cl.get_scene_list().scenes]

    def current_scene(self):
        r = self._cl.get_current_program_scene()
        # the field name depends on the OBS version
        return getattr(r, "scene_name", None) or getattr(r, "current_program_scene_name", None)

    def switch(self, name):
        self._cl.set_current_program_scene(name)

    def stream_status(self):
        r = self._cl.get_stream_status()
        return {
            "active":       getattr(r, "output_active", False),
            "reconnecting": getattr(r, "output_reconnecting", False),
            "timecode":     getattr(r, "output_timecode", None),
            # cumulative since the stream started; the controller keeps the delta
            "skipped":      getattr(r, "output_skipped_frames", 0) or 0,
        }

    def record_status(self):
        r = self._cl.get_record_status()
        return {
            "active":   getattr(r, "output_active", False),
            # always False with the stream encoder (OBS disables pause there);
            # published anyway so a later encoder change needs no code change
            "paused":   getattr(r, "output_paused", False),
            "timecode": getattr(r, "output_timecode", None),
            "bytes":    getattr(r, "output_bytes", 0) or 0,
        }


class DryObs:
    """Stands in for OBS under --no-obs: no connection, switches are only
    pretended, so the whole flow can be watched at the desk."""

    connected = True
    error = None

    def __init__(self, scene_names, start=None):
        self._names = list(scene_names)
        self._scene = start

    def connect(self):
        return True

    def drop(self):
        pass

    def scene_names(self):
        return list(self._names)

    def current_scene(self):
        return self._scene

    def switch(self, name):
        self._scene = name

    def stream_status(self):
        return {"active": False, "reconnecting": False, "timecode": None, "skipped": 0}

    def record_status(self):
        return {"active": False, "paused": False, "timecode": None, "bytes": 0}


class SceneController:
    POLL_S = 1.0         # how often the real on-air scene is read
    OUTPUT_POLL_S = 2.0  # how often stream and recording status are read
    RECONNECT_S = 5.0    # wait between connection attempts
    VALIDATE_S = 10.0    # how often the configured scenes are re-checked
    RETRY_S = 5.0        # wait before asking OBS again after a refused switch

    COUNTER_KEYS = ("anatec_home_score", "anatec_guest_score",
                    "anatec_home_fouls", "anatec_guest_fouls",
                    "anatec_home_timeouts", "anatec_guest_timeouts")

    def __init__(self, state, obs, director, scenes, live=True, log=print):
        self.state = state
        self.obs = obs
        self.director = director
        self.scenes = dict(scenes)
        self.live = live              # False under --no-obs: dry run
        self.log = log
        self.on_air = None
        self.stream = None
        self.record = None
        self._prev_skipped = None
        self._skipped_delta = 0
        self._wanted = None
        self._missing = []
        self._down_logged = False
        self._next_connect = 0.0
        self._next_poll = 0.0
        self._next_output = 0.0
        self._next_validate = 0.0
        self._retry_at = 0.0

    # -- OBS side --------------------------------------------------------

    def _drop(self, now, why):
        if self.obs.connected:
            self.log(f"[OBS] connection lost: {why}")
        self.obs.drop()
        self.on_air = None
        self.stream = None
        self.record = None
        self._prev_skipped = None
        self._skipped_delta = 0
        self._next_connect = now + self.RECONNECT_S

    def _validate(self, now):
        try:
            names = set(self.obs.scene_names())
        except Exception as e:
            self._drop(now, e)
            return
        configured = []
        for n in self.scenes.values():
            if n not in configured:
                configured.append(n)
        missing = [n for n in configured if n not in names]
        if missing != self._missing:
            if missing:
                self.log("[OBS] scene(s) not found in OBS: " + ", ".join(missing))
            elif self._missing:
                self.log("[OBS] all configured scenes found")
            self._missing = missing
        self._next_validate = now + self.VALIDATE_S

    def _connection(self, now):
        if not self.obs.connected and now >= self._next_connect:
            if self.obs.connect():
                self.log("[OBS] connected" if self.live else "[Scenes] dry run: OBS is not contacted")
                self._down_logged = False
                self._next_poll = now
                self._next_output = now
                self._validate(now)
            else:
                if not self._down_logged:
                    self.log(f"[OBS] not reachable: {self.obs.error}")
                    self._down_logged = True
                self._next_connect = now + self.RECONNECT_S

        if self.obs.connected and now >= self._next_poll:
            self._next_poll = now + self.POLL_S
            try:
                self.on_air = self.obs.current_scene()
            except Exception as e:
                self._drop(now, e)

        if self.obs.connected and now >= self._next_output:
            self._next_output = now + self.OUTPUT_POLL_S
            try:
                self.stream = self.obs.stream_status()
                self.record = self.obs.record_status()
            except Exception as e:
                self._drop(now, e)
            else:
                # The cumulative count only says something went wrong at some
                # point; the delta says it is going wrong now.
                skipped = self.stream["skipped"]
                if self._prev_skipped is None or skipped < self._prev_skipped:
                    self._skipped_delta = 0          # new stream, counter reset
                else:
                    self._skipped_delta = skipped - self._prev_skipped
                self._prev_skipped = skipped

        if self.obs.connected and now >= self._next_validate:
            self._validate(now)

    def _act(self, now):
        if self._wanted is None:
            return
        if self.on_air == self._wanted:
            self._wanted = None
            return
        if self._wanted in self._missing:
            self.log(f"[OBS] cannot switch to '{self._wanted}': no such scene in OBS")
            self._wanted = None
            return
        if not self.obs.connected or now < self._retry_at:
            return
        try:
            self.obs.switch(self._wanted)
        except Exception as e:
            self.log(f"[OBS] Scene switch failed: {e}")
            self._drop(now, e)
            self._retry_at = now + self.RETRY_S
            return
        self.log(f"[OBS] Switched to: {self._wanted}" + ("" if self.live else "  (dry run)"))
        self.on_air = self._wanted
        self._wanted = None

    # -- match_state side ------------------------------------------------

    def _snapshot(self, now):
        st = self.state
        selected = bool(st.get("selected"))
        return Snapshot(
            now=now,
            period=st.get("anatec_period") or None,
            minutes=st.get("anatec_clock_min"),
            seconds=st.get("anatec_clock_sec"),
            tenths=st.get("anatec_clock_tenths"),
            counters=tuple(st.get(k, 0) or 0 for k in self.COUNTER_KEYS),
            foys_event_period=st.get("foys_event_period"),
            match_id=st.get("match_id") if selected else None,
            status=st.get("status") if selected else None,
            on_air=self.on_air,
        )

    def _publish(self):
        st = self.state
        st["obs_enabled"] = self.live
        st["obs_available"] = bool(self.live and self.obs.connected)
        st["obs_scene"] = self.on_air
        st["obs_missing_scenes"] = list(self._missing)
        s, r = self.stream or {}, self.record or {}
        st["obs_stream_active"] = bool(s.get("active"))
        st["obs_stream_reconnecting"] = bool(s.get("reconnecting"))
        st["obs_stream_skipped_delta"] = self._skipped_delta
        st["obs_stream_timecode"] = s.get("timecode")
        st["obs_record_active"] = bool(r.get("active"))
        st["obs_record_paused"] = bool(r.get("paused"))
        st["obs_record_timecode"] = r.get("timecode")
        st["obs_record_bytes"] = r.get("bytes") or 0
        st["scene_prompt"] = self.director.prompt

    # -- loop ------------------------------------------------------------

    def step(self, now):
        self._connection(now)
        actions, notes = self.director.update(self._snapshot(now))
        for n in notes:
            self.log(f"[Scenes] {n}")
        if actions:
            self._wanted = actions[-1].scene
        self._act(now)
        self._publish()

    def run(self):
        while True:
            try:
                self.step(time.time())
            except Exception as e:
                self.log(f"[Scenes] {type(e).__name__}: {e}")
            time.sleep(0.25)
