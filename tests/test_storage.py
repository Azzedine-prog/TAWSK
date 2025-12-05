from datetime import date, timedelta
from pathlib import Path

from tracker_app.tracker.storage import Storage


def test_upsert_and_retrieve(tmp_path):
    db = tmp_path / "test.db"
    storage = Storage(db)
    activity_id = storage.create_activity("Test").id
    today = date.today()
    storage.upsert_daily_entry(
        today,
        activity_id,
        duration_hours_delta=1.0,
        objectives_text="Done",
        target_hours=2.0,
        completion_percent=50,
        stop_reason="break",
    )
    storage.upsert_daily_entry(today, activity_id, duration_hours_delta=0.5, objectives_text="Updated", completion_percent=80)
    entry = storage.get_daily_entry(today, activity_id)
    assert entry.duration_hours == 1.5
    assert entry.objectives_succeeded == "Updated"
    assert entry.target_hours == 2.0
    assert entry.completion_percent == 80
    assert entry.stop_reason == "break"


def test_statistics_between(tmp_path):
    db = tmp_path / "test.db"
    storage = Storage(db)
    act1 = storage.create_activity("A").id
    act2 = storage.create_activity("B").id
    today = date.today()
    storage.upsert_daily_entry(today, act1, duration_hours_delta=2.0, objectives_text="", completion_percent=75)
    storage.upsert_daily_entry(today - timedelta(days=1), act1, duration_hours_delta=1.0, objectives_text="", completion_percent=50)
    storage.upsert_daily_entry(today, act2, duration_hours_delta=3.0, objectives_text="", completion_percent=90)
    stats = storage.get_statistics_by_activity(today - timedelta(days=2), today)
    assert stats[0].activity_name == "B"
    assert stats[0].total_hours == 3.0
    assert stats[0].avg_completion == 90
