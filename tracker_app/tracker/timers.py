"""Timer management for activities (wx-friendly, no GTK dependency)."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Dict, Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class TimerState:
    elapsed_seconds: float = 0.0
    is_running: bool = False
    start_time: float | None = None
    on_tick: Callable[[float], None] | None = None
    thread: Optional[threading.Thread] = None
    stop_event: Optional[threading.Event] = None
    target_seconds: float = 0.0
    on_complete: Callable[[float], None] | None = None
    completion_fired: bool = False

    def start(self) -> None:
        self.start_time = time.monotonic()
        self.is_running = True

    def pause(self) -> None:
        if not self.is_running or self.start_time is None:
            return
        now = time.monotonic()
        self.elapsed_seconds += now - self.start_time
        self.is_running = False
        self.start_time = None

    def reset(self) -> None:
        self.elapsed_seconds = 0.0
        self.is_running = False
        self.start_time = None
        self.completion_fired = False
        self.target_seconds = 0.0
        self.on_complete = None

    @property
    def formatted(self) -> str:
        return str(timedelta(seconds=int(self.current_elapsed())))

    def current_elapsed(self) -> float:
        if self.is_running and self.start_time is not None:
            return self.elapsed_seconds + (time.monotonic() - self.start_time)
        return self.elapsed_seconds


class TimerManager:
    """Manage multiple timers keyed by activity id without GUI bindings."""

    def __init__(self) -> None:
        self.timers: Dict[int, TimerState] = {}

    def ensure_timer(self, activity_id: int) -> TimerState:
        if activity_id not in self.timers:
            self.timers[activity_id] = TimerState()
        return self.timers[activity_id]

    def _run_loop(self, activity_id: int) -> None:
        timer = self.ensure_timer(activity_id)
        assert timer.stop_event is not None
        while not timer.stop_event.wait(1):
            if timer.is_running and timer.on_tick:
                try:
                    timer.on_tick(timer.current_elapsed())
                except Exception:  # pragma: no cover - defensive
                    LOGGER.exception("Timer tick failed for activity %s", activity_id)
            if (
                timer.is_running
                and timer.target_seconds > 0
                and not timer.completion_fired
                and timer.current_elapsed() >= timer.target_seconds
            ):
                timer.pause()
                timer.completion_fired = True
                if timer.on_complete:
                    try:
                        timer.on_complete(timer.current_elapsed())
                    except Exception:  # pragma: no cover
                        LOGGER.exception("Timer completion callback failed for %s", activity_id)

    def start(
        self,
        activity_id: int,
        tick_cb: Callable[[float], None],
        target_seconds: float = 0.0,
        on_complete: Callable[[float], None] | None = None,
    ) -> TimerState:
        timer = self.ensure_timer(activity_id)
        if timer.is_running:
            return timer
        timer.on_tick = tick_cb
        timer.stop_event = threading.Event()
        timer.target_seconds = target_seconds
        timer.on_complete = on_complete
        timer.completion_fired = False
        timer.start()
        timer.thread = threading.Thread(target=self._run_loop, args=(activity_id,), daemon=True)
        timer.thread.start()
        LOGGER.debug("Started timer for activity %s", activity_id)
        return timer

    def pause(self, activity_id: int) -> TimerState:
        timer = self.ensure_timer(activity_id)
        timer.pause()
        LOGGER.debug("Paused timer for activity %s", activity_id)
        return timer

    def stop(self, activity_id: int) -> TimerState:
        timer = self.pause(activity_id)
        if timer.stop_event:
            timer.stop_event.set()
        if timer.thread and timer.thread.is_alive():
            timer.thread.join(timeout=1)
        timer.thread = None
        timer.stop_event = None
        LOGGER.debug("Stopped timer for activity %s", activity_id)
        return timer

    def reset(self, activity_id: int) -> TimerState:
        timer = self.ensure_timer(activity_id)
        timer.reset()
        LOGGER.debug("Reset timer for activity %s", activity_id)
        return timer


class PomodoroSession:
    """Stateful Pomodoro / focus timer with work/break phases.

    The session follows a simple state machine to make unit testing straightforward:
    Idle -> Running -> Paused -> Finished. Work and break phases are tracked separately,
    but a single session lifecycle drives both.
    """

    def __init__(
        self,
        work_seconds: int = 25 * 60,
        break_seconds: int = 5 * 60,
        on_tick: Callable[[str, str, float, float], None] | None = None,
        on_phase: Callable[[str], None] | None = None,
        on_complete: Callable[[float], None] | None = None,
    ) -> None:
        self.work_seconds = work_seconds
        self.break_seconds = break_seconds
        self.on_tick = on_tick
        self.on_phase = on_phase
        self.on_complete = on_complete
        self.state = "idle"
        self.phase = "work"
        self._phase_elapsed = 0.0
        self._total_work = 0.0
        self._start_time: float | None = None
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.state == "running":
            return
        self.state = "running"
        self._stop_event = threading.Event()
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self.state != "running":
            return
        self._capture_elapsed()
        self.state = "paused"

    def resume(self) -> None:
        if self.state != "paused":
            return
        self.state = "running"
        self._start_time = time.monotonic()

    def stop(self) -> float:
        self._capture_elapsed()
        self.state = "finished"
        if self._stop_event:
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        return self._total_work

    def reset(self) -> None:
        self.state = "idle"
        self.phase = "work"
        self._phase_elapsed = 0.0
        self._total_work = 0.0
        self._start_time = None
        if self._stop_event:
            self._stop_event.set()
        self._thread = None
        self._stop_event = None

    def _capture_elapsed(self) -> None:
        if self.state != "running" or self._start_time is None:
            return
        now = time.monotonic()
        self._phase_elapsed += now - self._start_time
        if self.phase == "work":
            self._total_work += now - self._start_time
        self._start_time = None

    def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.wait(1):
            if self.state != "running":
                continue
            self._capture_elapsed()
            # Restart the stopwatch for the next tick.
            self._start_time = time.monotonic()

            if self.on_tick:
                try:
                    remaining = self._phase_remaining()
                    self.on_tick(self.state, self.phase, self._total_work, remaining)
                except Exception:  # pragma: no cover - defensive
                    LOGGER.exception("Pomodoro tick failed")

            if self._phase_complete():
                self._advance_phase()
                if self.on_phase:
                    try:
                        self.on_phase(self.phase)
                    except Exception:  # pragma: no cover - defensive
                        LOGGER.exception("Pomodoro phase callback failed")

                if self.state == "finished":
                    if self.on_complete:
                        try:
                            self.on_complete(self._total_work)
                        except Exception:  # pragma: no cover - defensive
                            LOGGER.exception("Pomodoro completion callback failed")
                    self._stop_event.set()
                    return

    def _phase_remaining(self) -> float:
        target = self.work_seconds if self.phase == "work" else self.break_seconds
        return max(target - self._phase_elapsed, 0.0)

    def _phase_complete(self) -> bool:
        target = self.work_seconds if self.phase == "work" else self.break_seconds
        return self._phase_elapsed >= target

    def _advance_phase(self) -> None:
        self._phase_elapsed = 0.0
        if self.phase == "work":
            self.phase = "break"
            self._start_time = time.monotonic()
        else:
            self.state = "finished"
            self.phase = "finished"

    @property
    def work_elapsed_seconds(self) -> float:
        return self._total_work


class FocusSessionManager:
    """Manage Pomodoro sessions keyed by activity id."""

    def __init__(self) -> None:
        self.sessions: Dict[int, PomodoroSession] = {}

    def ensure(self, activity_id: int) -> PomodoroSession:
        if activity_id not in self.sessions:
            self.sessions[activity_id] = PomodoroSession()
        return self.sessions[activity_id]

    def start(
        self,
        activity_id: int,
        work_minutes: int = 25,
        break_minutes: int = 5,
        on_tick: Callable[[str, str, float, float], None] | None = None,
        on_phase: Callable[[str], None] | None = None,
        on_complete: Callable[[float], None] | None = None,
    ) -> PomodoroSession:
        session = self.ensure(activity_id)
        session.work_seconds = int(work_minutes * 60)
        session.break_seconds = int(break_minutes * 60)
        session.on_tick = on_tick
        session.on_phase = on_phase
        session.on_complete = on_complete
        session.reset()
        session.start()
        return session

    def pause(self, activity_id: int) -> PomodoroSession:
        session = self.ensure(activity_id)
        session.pause()
        return session

    def resume(self, activity_id: int) -> PomodoroSession:
        session = self.ensure(activity_id)
        session.resume()
        return session

    def stop(self, activity_id: int) -> PomodoroSession:
        session = self.ensure(activity_id)
        session.stop()
        return session

    def reset(self, activity_id: int) -> PomodoroSession:
        session = self.ensure(activity_id)
        session.reset()
        return session
