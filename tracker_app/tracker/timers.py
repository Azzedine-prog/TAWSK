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

    def start(self, activity_id: int, tick_cb: Callable[[float], None]) -> TimerState:
        timer = self.ensure_timer(activity_id)
        if timer.is_running:
            return timer
        timer.on_tick = tick_cb
        timer.stop_event = threading.Event()
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
