import time

from tracker.timers import TimerManager


def test_timer_start_pause(monkeypatch):
    manager = TimerManager()

    def fake_timeout_add(interval, func, activity_id):
        # Immediately invoke tick once for test
        func(activity_id)
        return 1

    def fake_source_remove(_id):
        return None

    monkeypatch.setattr("tracker.timers.GLib.timeout_add", fake_timeout_add)
    monkeypatch.setattr("tracker.timers.GLib.source_remove", fake_source_remove)

    elapsed_updates = []

    def on_tick(elapsed):
        elapsed_updates.append(elapsed)

    manager.start(1, on_tick)
    time.sleep(0.1)
    manager.pause(1)
    assert manager.timers[1].elapsed_seconds >= 0
    manager.reset(1)
    assert manager.timers[1].elapsed_seconds == 0
