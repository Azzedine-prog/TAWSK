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
    last_layout: str = ""
    show_help_tips: bool = True

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
            last_layout=data.get("last_layout", ""),
            show_help_tips=bool(data.get("show_help_tips", True)),
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
            f"last_layout = \"{self.last_layout}\"",
            f"show_help_tips = {str(bool(self.show_help_tips)).lower()}",
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

    def add_activity(
        self, name: str, description: str = "", default_target_hours: float = 0.0, tags: str = ""
    ) -> Activity:
        return self.storage.create_activity(
            name, description=description, default_target_hours=default_target_hours, tags=tags
        )

    def update_activity(
        self,
        activity_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        default_target_hours: Optional[float] = None,
        is_active: Optional[bool] = None,
        tags: Optional[str] = None,
    ) -> None:
        self.storage.update_activity(
            activity_id,
            name=name,
            description=description,
            default_target_hours=default_target_hours,
            is_active=is_active,
            tags=tags,
        )

    def duplicate_activity(self, activity_id: int) -> Optional[Activity]:
        activities = {a.id: a for a in self.storage.get_activities()}
        source = activities.get(activity_id)
        if not source:
            return None
        new_name = f"{source.name} (Copy)"
        suffix = 1
        existing_names = {a.name for a in activities.values()}
        while new_name in existing_names:
            suffix += 1
            new_name = f"{source.name} (Copy {suffix})"
        return self.add_activity(
            new_name,
            description=source.description,
            default_target_hours=source.default_target_hours,
            tags=source.tags,
        )

    def delete_activity(self, activity_id: int) -> None:
        self.storage.delete_activity(activity_id)

    def delete_daily_entry(self, entry_date: date, activity_id: int) -> None:
        """Delete a specific entry for a date/activity pair."""
        self.storage.delete_daily_entry(entry_date, activity_id)

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
        plan_total_hours: float = 0.0,
        plan_days: int = 1,
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
            plan_total_hours=plan_total_hours,
            plan_days=plan_days,
        )
        return elapsed

    def add_manual_time(
        self,
        activity_id: int,
        hours: float,
        objectives: str = "",
        comments: str = "",
        stop_reason: str = "Manual entry",
    ) -> None:
        self.storage.upsert_daily_entry(
            self.today,
            activity_id,
            duration_hours_delta=hours,
            objectives_text=objectives,
            target_hours=0.0,
            completion_percent=0.0,
            stop_reason=stop_reason,
            comments=comments,
        )

    def log_break(self, activity_id: int, minutes: float, reason: str, comments: str = "") -> None:
        stop_note = reason or "Break"
        self.storage.upsert_daily_entry(
            self.today,
            activity_id,
            duration_hours_delta=0.0,
            objectives_text="",
            target_hours=0.0,
            completion_percent=0.0,
            stop_reason=stop_note,
            comments=comments or f"Break: {minutes:.0f} minutes",
        )

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

        def planned_per_day(row: tuple) -> float:
            plan_total = row[8] if len(row) > 8 and row[8] is not None else row[4] if len(row) > 4 else 0.0
            plan_days = row[9] if len(row) > 9 and row[9] else 1
            target_hours = row[4] if len(row) > 4 and row[4] is not None else 0.0
            if target_hours:
                return target_hours
            return (plan_total / plan_days) if plan_total else 0.0

        per_day: Dict[str, set] = {}
        daily_hours: Dict[str, float] = {}
        daily_planned: Dict[str, float] = {}
        plan_totals: Dict[str, float] = {}
        for row in entries:
            (
                entry_date,
                activity_name,
                hours,
                _obj,
                target_hours,
                completion_percent,
                stop_reason,
                comments,
                plan_total_hours,
                plan_days,
            ) = (*row, 0, 1)[:10]
            planned_value = target_hours if target_hours else (plan_total_hours / plan_days if plan_total_hours else 0.0)
            daily_hours[entry_date] = daily_hours.get(entry_date, 0.0) + (hours or 0.0)
            per_day.setdefault(entry_date, set()).add(activity_name)
            daily_planned[entry_date] = daily_planned.get(entry_date, 0.0) + planned_value
            plan_totals[entry_date] = plan_totals.get(entry_date, 0.0) + (plan_total_hours or target_hours or 0.0)

        total_actual = sum(daily_hours.values())
        total_planned = sum(daily_planned.values())
        planned_vs_actual = (total_actual / total_planned * 100) if total_planned else None

        focused_time = sum((row[2] or 0.0) * ((row[5] or 0.0) / 100) for row in entries)
        focus_ratio = (focused_time / total_actual * 100) if total_actual else None

        # Time per category/activity
        category_hours: Dict[str, float] = {}
        for _date, activity_name, hours, *_rest in entries:
            category_hours[activity_name] = category_hours.get(activity_name, 0.0) + (hours or 0.0)

        # Task switching frequency and context switching load
        switches = sum(max(0, len(names) - 1) for names in per_day.values())
        days_count = max(len(per_day), 1)
        switch_load = switches / days_count

        # Overtime assumes 8h nominal day
        overtime = sum(max(0.0, daily_hours.get(day, 0.0) - 8.0) for day in per_day)

        total_tasks = len(entries)
        completed_tasks = sum(1 for row in entries if (row[5] or 0.0) >= 100)
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks else None
        avg_task_duration = (total_actual / total_tasks) if total_tasks else None

        productivity_score = (focused_time * 0.4) + (completed_tasks * 0.4) - (switches * 0.2)
        efficiency_index = (total_actual / total_planned) if total_planned else 1.0
        velocity = completed_tasks / days_count if days_count else 0.0
        capacity_forecast = (total_actual / days_count) * 7 if days_count else 0.0

        focus_quality = 0.0
        if focus_ratio is not None:
            focus_quality = max(0.0, min(100.0, (focus_ratio * 0.7) + max(0.0, 30 - (switch_load * 10))))

        interruption_events = sum(1 for _d, _a, _h, _o, _t, _c, reason, *_r in entries if (reason or "").lower().startswith("break"))
        interruption_cost = interruption_events * 10  # minutes lost estimate

        accuracy_by_category = {}
        for row in entries:
            activity_name = row[1]
            hours = row[2]
            planned = planned_per_day(row)
            if planned:
                ratios = accuracy_by_category.setdefault(activity_name, [])
                ratios.append(hours / planned)
        category_accuracy = ", ".join(
            f"{name}: {sum(vals)/len(vals)*100:.0f}%" for name, vals in accuracy_by_category.items()
        )

        drift = sum((daily_hours.get(day, 0.0) - daily_planned.get(day, 0.0)) for day in per_day)
        drift_text = f"{drift:+.1f}h vs plan"

        consistency_score = 0.0
        if len(daily_hours) > 1:
            avg_hours = total_actual / len(daily_hours)
            variance = sum((h - avg_hours) ** 2 for h in daily_hours.values()) / len(daily_hours)
            consistency_score = max(0.0, min(100.0, 100 - variance * 5))
        elif daily_hours:
            consistency_score = 100.0

        habit_streak = completed_tasks
        procrastination = sum(1 for row in entries if planned_per_day(row) and row[2] > planned_per_day(row) * 1.3)

        flow_efficiency = (focused_time / total_actual * 100) if total_actual else None

        return {
            "planned_vs_actual": f"{planned_vs_actual:.0f}%" if planned_vs_actual is not None else "N/A",
            "focus_ratio": f"{focus_ratio:.0f}%" if focus_ratio is not None else "N/A",
            "category_hours": ", ".join(f"{k}: {v:.1f}h" for k, v in sorted(category_hours.items(), key=lambda i: i[1], reverse=True)),
            "switches": str(int(switches)),
            "switch_load": f"{switch_load:.1f}/day",
            "overtime": f"{overtime:.1f}h",
            "completion_rate": f"{completion_rate:.0f}%" if completion_rate is not None else "N/A",
            "avg_task_duration": f"{avg_task_duration:.2f}h" if avg_task_duration is not None else "N/A",
            "productivity_score": f"{productivity_score:.1f}",
            "goal_achievement": f"{completion_rate:.0f}%" if completion_rate is not None else "N/A",
            "efficiency_index": f"{efficiency_index:.2f}x",
            "task_velocity": f"{velocity:.2f}/day",
            "capacity_forecast": f"{capacity_forecast:.1f}h next week",
            "focus_quality": f"{focus_quality:.0f}%",
            "interruption_cost": f"{interruption_cost:.0f} min",
            "category_accuracy": category_accuracy or "No planned targets",
            "time_drift": drift_text,
            "consistency_score": f"{consistency_score:.0f}%",
            "habit_streak": str(habit_streak),
            "procrastination_flags": str(procrastination),
            "flow_efficiency": f"{flow_efficiency:.0f}%" if flow_efficiency is not None else "N/A",
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

    def save_config(self, last_activity: Optional[int], layout: Optional[str] = None) -> None:
        cfg = self.config_manager.config
        cfg.last_selected_activity = last_activity
        if layout is not None:
            cfg.last_layout = layout
        self.config_manager.save(cfg)

    def backup_database(self) -> Path:
        return self.storage.backup_database()

    def export_tasks(self, path: Path) -> Path:
        return self.storage.export_tasks(path)

    def import_tasks(self, path: Path) -> int:
        return self.storage.import_tasks(path)

    def refresh_today(self) -> None:
        self.today = date.today()

    # Productivity AI bridge
    def predict_productivity(self, user_id: str, date_or_range) -> float:
        return productivity_adapter.predict_productivity(user_id, date_or_range, storage=self.storage)

    def productivity_insights(self, user_id: str, date_range) -> list[str]:
        return productivity_adapter.get_productivity_insights(user_id, date_range, storage=self.storage)

    def train_productivity_model(self, user_id: str = "default"):
        return productivity_adapter.train_productivity_model(user_id=user_id, storage=self.storage)
