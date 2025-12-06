"""SQLite-backed persistence layer."""
from __future__ import annotations

import csv
import json
import logging
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .models import Activity, ActivityStats, DailyEntry

LOGGER = logging.getLogger(__name__)


class Storage:
    """Wrapper around SQLite to manage activities and daily entries."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            LOGGER.exception("Database operation failed")
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    default_target_hours REAL NOT NULL DEFAULT 0,
                    tags TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    activity_id INTEGER NOT NULL,
                    duration_hours REAL NOT NULL DEFAULT 0,
                    objectives_succeeded TEXT,
                    target_hours REAL NOT NULL DEFAULT 0,
                    completion_percent REAL NOT NULL DEFAULT 0,
                    stop_reason TEXT,
                    comments TEXT,
                    UNIQUE(date, activity_id),
                    FOREIGN KEY(activity_id) REFERENCES activities(id)
                )
                """
            )
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Add newly introduced columns for existing installations."""

        def _add_column(name: str, ddl: str, table: str = "daily_entries") -> None:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(f"PRAGMA table_info({table})")
                cols = [row[1] for row in cur.fetchall()]
                if name not in cols:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                    LOGGER.info("Added column %s to %s", name, table)

        _add_column("target_hours", "REAL NOT NULL DEFAULT 0")
        _add_column("completion_percent", "REAL NOT NULL DEFAULT 0")
        _add_column("stop_reason", "TEXT")
        _add_column("comments", "TEXT")
        _add_column("description", "TEXT", table="activities")
        _add_column("default_target_hours", "REAL NOT NULL DEFAULT 0", table="activities")
        _add_column("tags", "TEXT", table="activities")

    def get_activities(self) -> List[Activity]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, description, default_target_hours, tags, is_active FROM activities ORDER BY name ASC"
            )
            rows = cur.fetchall()
            return [Activity.from_row(row) for row in rows]

    def create_activity(
        self, name: str, description: str = "", default_target_hours: float = 0.0, tags: str = ""
    ) -> Activity:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO activities (name, description, default_target_hours, tags, is_active) VALUES (?, ?, ?, ?, 1)",
                (name, description, default_target_hours, tags),
            )
            activity_id = cur.lastrowid
            LOGGER.info("Created activity %s", name)
            return Activity(
                id=activity_id,
                name=name,
                description=description,
                default_target_hours=default_target_hours,
                tags=tags,
                is_active=True,
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
        parts: List[str] = []
        params: List[object] = []
        if name is not None:
            parts.append("name = ?")
            params.append(name)
        if description is not None:
            parts.append("description = ?")
            params.append(description)
        if default_target_hours is not None:
            parts.append("default_target_hours = ?")
            params.append(default_target_hours)
        if tags is not None:
            parts.append("tags = ?")
            params.append(tags)
        if is_active is not None:
            parts.append("is_active = ?")
            params.append(1 if is_active else 0)
        params.append(activity_id)
        sql = "UPDATE activities SET " + ", ".join(parts) + " WHERE id = ?"
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            LOGGER.info("Updated activity %s", activity_id)

    def delete_activity(self, activity_id: int) -> None:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
            cur.execute("DELETE FROM daily_entries WHERE activity_id = ?", (activity_id,))
            LOGGER.info("Deleted activity %s", activity_id)

    def get_daily_entry(self, entry_date: date, activity_id: int) -> Optional[DailyEntry]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, date, activity_id, duration_hours, objectives_succeeded, target_hours, completion_percent, stop_reason, comments
                FROM daily_entries WHERE date = ? AND activity_id = ?
                """,
                (entry_date.isoformat(), activity_id),
            )
            row = cur.fetchone()
            return DailyEntry.from_row(row) if row else None

    def upsert_daily_entry(
        self,
        entry_date: date,
        activity_id: int,
        duration_hours_delta: float = 0.0,
        objectives_text: Optional[str] = None,
        target_hours: Optional[float] = None,
        completion_percent: Optional[float] = None,
        stop_reason: Optional[str] = None,
        comments: Optional[str] = None,
    ) -> DailyEntry:
        """Add or update the daily entry for the activity and date."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            existing = self.get_daily_entry(entry_date, activity_id)
            if existing:
                new_duration = existing.duration_hours + duration_hours_delta
                new_objectives = objectives_text if objectives_text is not None else existing.objectives_succeeded
                new_target = (existing.target_hours or 0.0) + ((target_hours or 0.0) if target_hours is not None else 0.0)
                new_percent = completion_percent if completion_percent is not None else existing.completion_percent
                new_reason = stop_reason if stop_reason is not None else existing.stop_reason
                new_comments = comments if comments is not None else getattr(existing, "comments", "")
                cur.execute(
                    """
                    UPDATE daily_entries
                    SET duration_hours = ?, objectives_succeeded = ?, target_hours = ?, completion_percent = ?, stop_reason = ?, comments = ?
                    WHERE id = ?
                    """,
                    (new_duration, new_objectives, new_target, new_percent, new_reason, new_comments, existing.id),
                )
                LOGGER.debug("Updated entry for %s %s", entry_date, activity_id)
                return DailyEntry(
                    id=existing.id,
                    date=entry_date,
                    activity_id=activity_id,
                    duration_hours=new_duration,
                    objectives_succeeded=new_objectives,
                    target_hours=new_target,
                    completion_percent=new_percent,
                    stop_reason=new_reason,
                    comments=new_comments,
                )
            cur.execute(
                """
                INSERT INTO daily_entries (date, activity_id, duration_hours, objectives_succeeded, target_hours, completion_percent, stop_reason, comments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_date.isoformat(),
                    activity_id,
                    duration_hours_delta,
                    objectives_text or "",
                    target_hours or 0.0,
                    completion_percent or 0.0,
                    stop_reason or "",
                    comments or "",
                ),
            )
            entry_id = cur.lastrowid
            LOGGER.debug("Created entry for %s %s", entry_date, activity_id)
            return DailyEntry(
                id=entry_id,
                date=entry_date,
                activity_id=activity_id,
                duration_hours=duration_hours_delta,
                objectives_succeeded=objectives_text or "",
                target_hours=target_hours or 0.0,
                completion_percent=completion_percent or 0.0,
                stop_reason=stop_reason or "",
                comments=comments or "",
            )

    def get_daily_entries_by_date(self, entry_date: date) -> List[DailyEntry]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, date, activity_id, duration_hours, objectives_succeeded, target_hours, completion_percent, stop_reason, comments
                FROM daily_entries WHERE date = ?
                """,
                (entry_date.isoformat(),),
            )
            return [DailyEntry.from_row(row) for row in cur.fetchall()]

    def get_entries_between(self, start_date: date, end_date: date) -> List[Tuple[str, str, float, str, float, float, str, str]]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT de.date, a.name, de.duration_hours, de.objectives_succeeded, de.target_hours, de.completion_percent, de.stop_reason, de.comments
                FROM daily_entries de
                JOIN activities a ON a.id = de.activity_id
                WHERE de.date BETWEEN ? AND ?
                ORDER BY de.date ASC
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            return cur.fetchall()

    def get_statistics_by_activity(self, start_date: date, end_date: date) -> List[ActivityStats]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT a.name, SUM(de.duration_hours) as total_hours,
                       AVG(de.duration_hours) as avg_hours,
                       AVG(de.completion_percent) as avg_completion
                FROM daily_entries de
                JOIN activities a ON a.id = de.activity_id
                WHERE de.date BETWEEN ? AND ?
                GROUP BY a.name
                ORDER BY total_hours DESC
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            rows = cur.fetchall()
            return [
                ActivityStats(
                    activity_name=row[0],
                    total_hours=row[1] or 0.0,
                    avg_hours=row[2] or 0.0,
                    avg_completion=row[3] or 0.0,
                )
                for row in rows
            ]

    def get_time_history(self) -> List[dict]:
        """Return simplified rows for AI analysis without UI dependencies."""

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT a.name, de.duration_hours, de.target_hours, de.completion_percent
                FROM daily_entries de
                JOIN activities a ON de.activity_id = a.id
                """
            )
            return [
                {
                    "title": row[0],
                    "actual_duration": row[1] or 0.0,
                    "estimated_duration": row[2] or 0.0,
                    "completion_percent": row[3] or 0.0,
                }
                for row in cur.fetchall()
            ]

    def backup_database(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.db_path.with_name(f"{self.db_path.stem}-backup-{timestamp}{self.db_path.suffix}")
        shutil.copy2(self.db_path, target)
        LOGGER.info("Database backed up to %s", target)
        return target

    def export_tasks(self, path: Path) -> Path:
        activities = self.get_activities()
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["name", "description", "default_target_hours", "tags", "is_active"]
            )
            writer.writeheader()
            for act in activities:
                writer.writerow(
                    {
                        "name": act.name,
                        "description": act.description,
                        "default_target_hours": act.default_target_hours,
                        "tags": act.tags,
                        "is_active": int(act.is_active),
                    }
                )
        LOGGER.info("Exported %s activities to %s", len(activities), path)
        return path

    def import_tasks(self, path: Path) -> int:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        imported = 0
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else data.get("tasks", [])
        else:
            with path.open("r", newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
        for row in rows:
            name = row.get("name") if isinstance(row, dict) else None
            if not name:
                continue
            description = row.get("description", "") if isinstance(row, dict) else ""
            target = float(row.get("default_target_hours", 0) or 0)
            tags = row.get("tags", "") if isinstance(row, dict) else ""
            try:
                self.create_activity(name, description=description, default_target_hours=target, tags=tags)
                imported += 1
            except sqlite3.IntegrityError:
                LOGGER.info("Skipped duplicate task %s during import", name)
        LOGGER.info("Imported %s tasks from %s", imported, path)
        return imported
