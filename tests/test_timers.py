import time

from tracker_app.tracker.timers import FocusSessionManager, TimerManager


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


def test_focus_session_work_and_break_cycle():
    focus = FocusSessionManager()
    phases = []
    completed = []

    focus.start(
        1,
        work_minutes=0.05,  # ~3 seconds
        break_minutes=0.02,  # ~1 second
        on_phase=lambda p: phases.append(p),
        on_complete=lambda seconds: completed.append(seconds),
    )

    time.sleep(5)

    assert "break" in phases, "Should enter break phase"
    assert "finished" in phases or completed, "Should finish the cycle"
    assert completed, "Completion callback should fire"
