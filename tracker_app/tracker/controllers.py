"""Controllers orchestrating UI, storage, timers, and exports."""
from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from . import __version__
from .models import Activity, DailyEntry
from .storage import Storage
from .timers import TimerManager
from src.ai_integration import productivity_adapter
if TYPE_CHECKING:
    from reports.excel_export import ExcelExporter

LOGGER = logging.getLogger(__name__)


CONFIG_DIR = Path.home() / ".study_tracker"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default_config.toml"


@dataclass
class AppConfig:
    export_path: str
    default_range_days: int
    last_window_width: int
    last_window_height: int
    last_selected_activity: Optional[int] = None

    @classmethod
    def from_toml(cls, data: dict) -> "AppConfig":
        raw_last_activity = data.get("last_selected_activity")
        last_activity: Optional[int]
        if raw_last_activity in (None, "", "null"):
            last_activity = None
        else:
            try:
                last_activity = int(raw_last_activity)
            except (TypeError, ValueError):
                last_activity = None
        return cls(
            export_path=data.get("export_path", "statistics.xlsx"),
            default_range_days=int(data.get("default_range_days", 7)),
            last_window_width=int(data.get("last_window_width", 1000)),
            last_window_height=int(data.get("last_window_height", 700)),
            last_selected_activity=last_activity,
        )

    def to_toml(self) -> str:
        last_activity_value = (
            self.last_selected_activity
            if self.last_selected_activity is not None
            else '""'
        )
        lines = [
            f"export_path = \"{self.export_path}\"",
            f"default_range_days = {self.default_range_days}",
            f"last_window_width = {self.last_window_width}",
            f"last_window_height = {self.last_window_height}",
            f"last_selected_activity = {last_activity_value}",
        ]
        return "\n".join(lines) + "\n"


class ConfigManager:
    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.config = self._load()

    def _load(self) -> AppConfig:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "rb") as fh:
                data = tomllib.load(fh)
                return AppConfig.from_toml(data)
        with open(DEFAULT_CONFIG_PATH, "rb") as fh:
            data = tomllib.load(fh)
            config = AppConfig.from_toml(data)
            self.save(config)
            return config

    def save(self, config: Optional[AppConfig] = None) -> None:
        cfg = config or self.config
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(cfg.to_toml(), encoding="utf-8")
        LOGGER.info("Saved configuration to %s", CONFIG_FILE)


class AppController:
    def __init__(self, storage: Storage, timers: TimerManager, exporter: ExcelExporter, config_manager: ConfigManager) -> None:
        self.storage = storage
        self.timers = timers
        self.exporter = exporter
        self.config_manager = config_manager
        self.today = date.today()

    # Activity management
    def list_activities(self) -> List[Activity]:
        return self.storage.get_activities()

    def add_activity(self, name: str, description: str = "", default_target_hours: float = 0.0) -> Activity:
        return self.storage.create_activity(name, description=description, default_target_hours=default_target_hours)

    def update_activity(
        self,
        activity_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        default_target_hours: Optional[float] = None,
        is_active: Optional[bool] = None,
    ) -> None:
        self.storage.update_activity(
            activity_id,
            name=name,
            description=description,
            default_target_hours=default_target_hours,
            is_active=is_active,
        )

    def delete_activity(self, activity_id: int) -> None:
        self.storage.delete_activity(activity_id)

    # Timer operations
    def start_timer(self, activity_id: int, tick_cb, target_hours: float = 0.0, on_complete=None) -> None:
        self.timers.start(activity_id, tick_cb, target_seconds=target_hours * 3600.0, on_complete=on_complete)

    def pause_timer(self, activity_id: int) -> float:
        timer = self.timers.pause(activity_id)
        return timer.current_elapsed()

    def finalize_timer(
        self,
        activity_id: int,
        objectives: str,
        target_hours: float,
        completion_percent: float,
        comments: str = "",
        stop_reason: str = "",
    ) -> float:
        timer = self.timers.stop(activity_id)
        elapsed = timer.current_elapsed()
        hours = elapsed / 3600.0
        self.storage.upsert_daily_entry(
            self.today,
            activity_id,
            duration_hours_delta=hours,
            objectives_text=objectives,
            target_hours=target_hours,
            completion_percent=completion_percent,
            stop_reason=stop_reason,
            comments=comments,
        )
        return elapsed

    def reset_timer(self, activity_id: int) -> None:
        self.timers.reset(activity_id)

    def get_timer_display(self, activity_id: int) -> str:
        return self.timers.ensure_timer(activity_id).formatted

    # Data retrieval
    def get_today_entries(self) -> List[DailyEntry]:
        return self.storage.get_daily_entries_by_date(self.today)

    def get_entries_between(self, start_date: date, end_date: date):
        return self.storage.get_entries_between(start_date, end_date)

    def get_stats(self, start_date: date, end_date: date):
        return self.storage.get_statistics_by_activity(start_date, end_date)

    def get_kpis(self, start_date: date, end_date: date) -> Dict[str, str]:
        """Compute higher-level KPIs using stored entries."""

        entries = self.get_entries_between(start_date, end_date)
        if not entries:
            return {}

        total_actual = sum(row[2] or 0.0 for row in entries)
        total_planned = sum((row[4] or 0.0) for row in entries)
        planned_vs_actual = (total_actual / total_planned * 100) if total_planned else None

        focused_time = sum((row[2] or 0.0) * ((row[5] or 0.0) / 100) for row in entries)
        focus_ratio = (focused_time / total_actual * 100) if total_actual else None

        # Time per category/activity
        category_hours: Dict[str, float] = {}
        for _date, activity_name, hours, *_rest in entries:
            category_hours[activity_name] = category_hours.get(activity_name, 0.0) + (hours or 0.0)

        # Task switching frequency: count unique activities per day minus one
        per_day: Dict[str, set] = {}
        for entry_date, activity_name, *_rest in entries:
            per_day.setdefault(entry_date, set()).add(activity_name)
        switches = sum(max(0, len(names) - 1) for names in per_day.values())

        # Overtime assumes 8h nominal day
        overtime = sum(max(0.0, sum(row[2] or 0.0 for row in entries if row[0] == day) - 8.0) for day in per_day)

        total_tasks = len(entries)
        completed_tasks = sum(1 for row in entries if (row[5] or 0.0) >= 100)
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks else None
        avg_task_duration = (total_actual / total_tasks) if total_tasks else None

        productivity_score = (focused_time * 0.6) + (completed_tasks * 0.3) - (switches * 0.1)

        return {
            "planned_vs_actual": f"{planned_vs_actual:.0f}%" if planned_vs_actual is not None else "N/A",
            "focus_ratio": f"{focus_ratio:.0f}%" if focus_ratio is not None else "N/A",
            "category_hours": ", ".join(f"{k}: {v:.1f}h" for k, v in sorted(category_hours.items(), key=lambda i: i[1], reverse=True)),
            "switches": str(int(switches)),
            "overtime": f"{overtime:.1f}h",
            "completion_rate": f"{completion_rate:.0f}%" if completion_rate is not None else "N/A",
            "avg_task_duration": f"{avg_task_duration:.2f}h" if avg_task_duration is not None else "N/A",
            "productivity_score": f"{productivity_score:.1f}",
            "goal_achievement": f"{completion_rate:.0f}%" if completion_rate is not None else "N/A",
        }

    # Excel export
    def export_to_excel(self, start_date: date, end_date: date) -> Path:
        entries = self.storage.get_entries_between(start_date, end_date)
        stats = self.storage.get_statistics_by_activity(start_date, end_date)
        stat_rows = [
            (s.activity_name, s.total_hours, s.avg_hours, s.avg_completion)
            for s in stats
        ]
        return self.exporter.export(entries, stat_rows)

    def save_config(self, last_activity: Optional[int]) -> None:
        cfg = self.config_manager.config
        cfg.last_selected_activity = last_activity
        self.config_manager.save(cfg)

    def refresh_today(self) -> None:
        self.today = date.today()

    # Productivity AI bridge
    def predict_productivity(self, user_id: str, date_or_range) -> float:
        return productivity_adapter.predict_productivity(user_id, date_or_range, storage=self.storage)

    def productivity_insights(self, user_id: str, date_range) -> list[str]:
        return productivity_adapter.get_productivity_insights(user_id, date_range, storage=self.storage)

    def train_productivity_model(self, user_id: str = "default"):
        return productivity_adapter.train_productivity_model(user_id=user_id, storage=self.storage)
