from datetime import date

from tracker_app.tracker.models import Activity, DailyEntry


def test_activity_from_row():
    row = (1, "Test", 1)
    activity = Activity.from_row(row)
    assert activity.id == 1
    assert activity.name == "Test"
    assert activity.is_active is True


def test_daily_entry_from_row():
    row = (1, "2024-01-01", 2, 1.5, "Objective", 2.0, 80.0, "reason")
    entry = DailyEntry.from_row(row)
    assert entry.date == date(2024, 1, 1)
    assert entry.duration_hours == 1.5
    assert entry.target_hours == 2.0
    assert entry.completion_percent == 80.0
    assert entry.stop_reason == "reason"
