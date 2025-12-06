import pytest

from tracker_app.core.ai_service import AIAssistantService
from tracker_app.tracker.controllers import AppController, ConfigManager
from tracker_app.tracker.storage import Storage
from tracker_app.tracker.timers import TimerManager

try:
    from reports.excel_export import ExcelExporter
    _PANDAS_AVAILABLE = True
except Exception:  # noqa: BLE001
    _PANDAS_AVAILABLE = False


def test_ai_assistant_graceful(monkeypatch, tmp_path):
    if not _PANDAS_AVAILABLE:
        pytest.skip("pandas not installed")
    storage = Storage(tmp_path / "db.sqlite")
    timers = TimerManager()
    exporter = ExcelExporter(tmp_path / "export.xlsx")
    config = ConfigManager()
    controller = AppController(storage, timers, exporter, config)
    controller.add_activity("Sample")
    ai = AIAssistantService(controller)

    duration = ai.suggest_duration("Sample", "desc", "General", "Medium")
    assert duration is not None

    priority = ai.suggest_priority("Sample", None, "General")
    assert priority in {"Low", "Medium", "High", "Critical"}

    plan = ai.generate_daily_plan(controller.storage.today())
    assert isinstance(plan, list)

    insights = ai.analyze_patterns()
    assert isinstance(insights, list)
