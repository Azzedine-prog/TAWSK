from datetime import date

from tracker.models import Activity, DailyEntry


def test_activity_from_row():
    row = (1, "Test", 1)
    activity = Activity.from_row(row)
    assert activity.id == 1
    assert activity.name == "Test"
    assert activity.is_active is True


def test_daily_entry_from_row():
    row = (1, "2024-01-01", 2, 1.5, "Objective")
    entry = DailyEntry.from_row(row)
    assert entry.date == date(2024, 1, 1)
    assert entry.duration_hours == 1.5
