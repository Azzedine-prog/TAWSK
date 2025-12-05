from datetime import date, timedelta
from pathlib import Path

from tracker.storage import Storage


def test_upsert_and_retrieve(tmp_path):
    db = tmp_path / "test.db"
    storage = Storage(db)
    activity_id = storage.create_activity("Test").id
    today = date.today()
    storage.upsert_daily_entry(today, activity_id, duration_hours_delta=1.0, objectives_text="Done")
    storage.upsert_daily_entry(today, activity_id, duration_hours_delta=0.5, objectives_text="Updated")
    entry = storage.get_daily_entry(today, activity_id)
    assert entry.duration_hours == 1.5
    assert entry.objectives_succeeded == "Updated"


def test_statistics_between(tmp_path):
    db = tmp_path / "test.db"
    storage = Storage(db)
    act1 = storage.create_activity("A").id
    act2 = storage.create_activity("B").id
    today = date.today()
    storage.upsert_daily_entry(today, act1, duration_hours_delta=2.0, objectives_text="")
    storage.upsert_daily_entry(today - timedelta(days=1), act1, duration_hours_delta=1.0, objectives_text="")
    storage.upsert_daily_entry(today, act2, duration_hours_delta=3.0, objectives_text="")
    stats = storage.get_statistics_by_activity(today - timedelta(days=2), today)
    assert stats[0][0] == "B"
    assert stats[0][1] == 3.0
