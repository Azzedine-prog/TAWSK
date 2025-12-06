from datetime import date

from tracker_app.tracker.controllers import AppConfig, AppController
from tracker_app.tracker.storage import Storage
from tracker_app.tracker.timers import TimerManager


class DummyExporter:
    def export(self, *_args, **_kwargs):
        return "test.xlsx"


class DummyConfigManager:
    def __init__(self) -> None:
        self.config = AppConfig(
            export_path="stats.xlsx",
            default_range_days=7,
            last_window_width=1200,
            last_window_height=800,
        )

    def save(self, config=None):  # pragma: no cover - not exercised
        self.config = config or self.config


def test_get_kpis(tmp_path):
    storage = Storage(tmp_path / "kpis.db")
    act = storage.create_activity("Deep Work", description="", default_target_hours=3.0)
    today = date.today()
    storage.upsert_daily_entry(today, act.id, duration_hours_delta=4.0, objectives_text="", target_hours=3.0, completion_percent=90)
    storage.upsert_daily_entry(today, act.id, duration_hours_delta=1.0, objectives_text="", target_hours=1.0, completion_percent=100)

    controller = AppController(storage, TimerManager(), DummyExporter(), DummyConfigManager())
    kpis = controller.get_kpis(today, today)

    assert kpis["planned_vs_actual"] == "125%"
    assert kpis["focus_ratio"].endswith("%")
    assert "Deep Work" in kpis["category_hours"]
    assert kpis["completion_rate"] == "100%"
    assert "efficiency_index" in kpis
    assert "task_velocity" in kpis
