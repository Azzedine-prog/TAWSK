"""SQLite-backed persistence layer."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import date
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
                    UNIQUE(date, activity_id),
                    FOREIGN KEY(activity_id) REFERENCES activities(id)
                )
                """
            )
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Add newly introduced columns for existing installations."""

        def _add_column(name: str, ddl: str) -> None:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(daily_entries)")
                cols = [row[1] for row in cur.fetchall()]
                if name not in cols:
                    cur.execute(f"ALTER TABLE daily_entries ADD COLUMN {name} {ddl}")
                    LOGGER.info("Added column %s to daily_entries", name)

        _add_column("target_hours", "REAL NOT NULL DEFAULT 0")
        _add_column("completion_percent", "REAL NOT NULL DEFAULT 0")
        _add_column("stop_reason", "TEXT")

    def get_activities(self) -> List[Activity]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, is_active FROM activities ORDER BY name ASC")
            rows = cur.fetchall()
            return [Activity.from_row(row) for row in rows]

    def create_activity(self, name: str) -> Activity:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO activities (name, is_active) VALUES (?, 1)", (name,))
            activity_id = cur.lastrowid
            LOGGER.info("Created activity %s", name)
            return Activity(id=activity_id, name=name, is_active=True)

    def update_activity(self, activity_id: int, name: Optional[str] = None, is_active: Optional[bool] = None) -> None:
        parts: List[str] = []
        params: List[object] = []
        if name is not None:
            parts.append("name = ?")
            params.append(name)
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
                SELECT id, date, activity_id, duration_hours, objectives_succeeded, target_hours, completion_percent, stop_reason
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
    ) -> DailyEntry:
        """Add or update the daily entry for the activity and date."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            existing = self.get_daily_entry(entry_date, activity_id)
            if existing:
                new_duration = existing.duration_hours + duration_hours_delta
                new_objectives = objectives_text if objectives_text is not None else existing.objectives_succeeded
                new_target = target_hours if target_hours is not None else existing.target_hours
                new_percent = completion_percent if completion_percent is not None else existing.completion_percent
                new_reason = stop_reason if stop_reason is not None else existing.stop_reason
                cur.execute(
                    """
                    UPDATE daily_entries
                    SET duration_hours = ?, objectives_succeeded = ?, target_hours = ?, completion_percent = ?, stop_reason = ?
                    WHERE id = ?
                    """,
                    (new_duration, new_objectives, new_target, new_percent, new_reason, existing.id),
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
                )
            cur.execute(
                """
                INSERT INTO daily_entries (date, activity_id, duration_hours, objectives_succeeded, target_hours, completion_percent, stop_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_date.isoformat(),
                    activity_id,
                    duration_hours_delta,
                    objectives_text or "",
                    target_hours or 0.0,
                    completion_percent or 0.0,
                    stop_reason or "",
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
            )

    def get_daily_entries_by_date(self, entry_date: date) -> List[DailyEntry]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, date, activity_id, duration_hours, objectives_succeeded, target_hours, completion_percent, stop_reason
                FROM daily_entries WHERE date = ?
                """,
                (entry_date.isoformat(),),
            )
            return [DailyEntry.from_row(row) for row in cur.fetchall()]

    def get_entries_between(self, start_date: date, end_date: date) -> List[Tuple[str, str, float, str, float, float, str]]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT de.date, a.name, de.duration_hours, de.objectives_succeeded, de.target_hours, de.completion_percent, de.stop_reason
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
