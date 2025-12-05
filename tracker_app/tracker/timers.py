"""Timer management for activities."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Dict

from gi.repository import GLib

LOGGER = logging.getLogger(__name__)


@dataclass
class TimerState:
    elapsed_seconds: float = 0.0
    is_running: bool = False
    start_time: float | None = None
    update_callback_id: int | None = None
    on_tick: Callable[[float], None] | None = None

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
    """Manage multiple timers keyed by activity id."""

    def __init__(self) -> None:
        self.timers: Dict[int, TimerState] = {}

    def ensure_timer(self, activity_id: int) -> TimerState:
        if activity_id not in self.timers:
            self.timers[activity_id] = TimerState()
        return self.timers[activity_id]

    def start(self, activity_id: int, tick_cb: Callable[[float], None]) -> TimerState:
        timer = self.ensure_timer(activity_id)
        if timer.is_running:
            return timer
        timer.on_tick = tick_cb
        timer.start()
        timer.update_callback_id = GLib.timeout_add(1000, self._tick, activity_id)
        LOGGER.debug("Started timer for activity %s", activity_id)
        return timer

    def pause(self, activity_id: int) -> TimerState:
        timer = self.ensure_timer(activity_id)
        timer.pause()
        if timer.update_callback_id:
            GLib.source_remove(timer.update_callback_id)
            timer.update_callback_id = None
        LOGGER.debug("Paused timer for activity %s", activity_id)
        return timer

    def stop(self, activity_id: int) -> TimerState:
        timer = self.pause(activity_id)
        LOGGER.debug("Stopped timer for activity %s", activity_id)
        return timer

    def reset(self, activity_id: int) -> TimerState:
        timer = self.ensure_timer(activity_id)
        if timer.update_callback_id:
            GLib.source_remove(timer.update_callback_id)
            timer.update_callback_id = None
        timer.reset()
        LOGGER.debug("Reset timer for activity %s", activity_id)
        return timer

    def _tick(self, activity_id: int) -> bool:
        timer = self.ensure_timer(activity_id)
        if not timer.is_running:
            return False
        elapsed = timer.current_elapsed()
        if timer.on_tick:
            timer.on_tick(elapsed)
        return True
