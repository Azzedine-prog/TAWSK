import importlib.util

from datetime import date, timedelta
from pathlib import Path

from src.ai_integration import productivity_adapter as adapter
from tracker_app.tracker.storage import Storage


PANDAS_AVAILABLE = importlib.util.find_spec("pandas") is not None


def _seed_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "test.db")
    act = storage.create_activity("Sample").id
    storage.upsert_daily_entry(date.today(), act, duration_hours_delta=1.5, target_hours=2.0, completion_percent=75)
    storage.upsert_daily_entry(date.today() - timedelta(days=1), act, duration_hours_delta=1.0, target_hours=1.5, completion_percent=60)
    return storage


def test_productivity_neutral_without_repo(tmp_path):
    storage = _seed_storage(tmp_path)
    score = adapter.predict_productivity("user", date.today(), storage=storage, repo_path=tmp_path / "missing")
    insights = adapter.get_productivity_insights(
        "user", (date.today() - timedelta(days=1), date.today()), storage=storage, repo_path=tmp_path / "missing"
    )
    assert score == adapter.NEUTRAL_SCORE
    assert insights == []


def test_productivity_with_fake_repo(tmp_path):
    storage = _seed_storage(tmp_path)
    repo = tmp_path / "ai_productivity_tracker"
    repo.mkdir()
    fake = repo / "bridge.py"
    fake.write_text(
        """
from typing import Iterable

def train_model(data, user_id=None):
    return {"trained_rows": len(data)}

def predict_productivity(data, user_id=None, date=None, date_range=None):
    return 0.85

def get_productivity_insights(data, user_id=None, date_range=None):
    return [f"rows={len(data)}", f"user={user_id}"]
"""
    )
    score = adapter.predict_productivity("user", date.today(), storage=storage, repo_path=repo)
    insights = adapter.get_productivity_insights("user", (date.today() - timedelta(days=1), date.today()), storage=storage, repo_path=repo)
    train_result = adapter.train_productivity_model("user", storage=storage, repo_path=repo)
    if not PANDAS_AVAILABLE:
        assert score == adapter.NEUTRAL_SCORE
        assert insights == []
        assert train_result is None
    else:
        assert score == 0.85
        assert insights and insights[0].startswith("rows=")
        assert train_result == {"trained_rows": 2}
