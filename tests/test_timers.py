import time

from tracker_app.tracker.timers import TimerManager


def test_timer_start_pause():
    manager = TimerManager()

    elapsed_updates = []
    completed = []

    def on_tick(elapsed):
        elapsed_updates.append(elapsed)

    def on_complete(elapsed):
        completed.append(elapsed)

    manager.start(1, on_tick, target_seconds=1.0, on_complete=on_complete)
    time.sleep(1.3)
    manager.pause(1)
    assert manager.timers[1].elapsed_seconds > 0
    assert elapsed_updates, "tick callback should have been invoked"
    assert completed, "completion callback should have fired when target reached"
    manager.reset(1)
    assert manager.timers[1].elapsed_seconds == 0
