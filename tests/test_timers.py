import time

from tracker_app.tracker.timers import TimerManager


def test_timer_start_pause():
    manager = TimerManager()

    elapsed_updates = []

    def on_tick(elapsed):
        elapsed_updates.append(elapsed)

    manager.start(1, on_tick)
    time.sleep(1.2)
    manager.pause(1)
    assert manager.timers[1].elapsed_seconds > 0
    assert elapsed_updates, "tick callback should have been invoked"
    manager.reset(1)
    assert manager.timers[1].elapsed_seconds == 0
