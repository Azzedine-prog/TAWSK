"""SQLite-backed persistence layer."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .models import Activity, DailyEntry

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
                    UNIQUE(date, activity_id),
                    FOREIGN KEY(activity_id) REFERENCES activities(id)
                )
                """
            )

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
                "SELECT id, date, activity_id, duration_hours, objectives_succeeded FROM daily_entries WHERE date = ? AND activity_id = ?",
                (entry_date.isoformat(), activity_id),
            )
            row = cur.fetchone()
            return DailyEntry.from_row(row) if row else None

    def upsert_daily_entry(
        self, entry_date: date, activity_id: int, duration_hours_delta: float = 0.0, objectives_text: Optional[str] = None
    ) -> DailyEntry:
        """Add or update the daily entry for the activity and date."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            existing = self.get_daily_entry(entry_date, activity_id)
            if existing:
                new_duration = existing.duration_hours + duration_hours_delta
                new_objectives = objectives_text if objectives_text is not None else existing.objectives_succeeded
                cur.execute(
                    "UPDATE daily_entries SET duration_hours = ?, objectives_succeeded = ? WHERE id = ?",
                    (new_duration, new_objectives, existing.id),
                )
                LOGGER.debug("Updated entry for %s %s", entry_date, activity_id)
                return DailyEntry(id=existing.id, date=entry_date, activity_id=activity_id, duration_hours=new_duration, objectives_succeeded=new_objectives)
            cur.execute(
                "INSERT INTO daily_entries (date, activity_id, duration_hours, objectives_succeeded) VALUES (?, ?, ?, ?)",
                (entry_date.isoformat(), activity_id, duration_hours_delta, objectives_text or ""),
            )
            entry_id = cur.lastrowid
            LOGGER.debug("Created entry for %s %s", entry_date, activity_id)
            return DailyEntry(id=entry_id, date=entry_date, activity_id=activity_id, duration_hours=duration_hours_delta, objectives_succeeded=objectives_text or "")

    def get_daily_entries_by_date(self, entry_date: date) -> List[DailyEntry]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, date, activity_id, duration_hours, objectives_succeeded FROM daily_entries WHERE date = ?",
                (entry_date.isoformat(),),
            )
            return [DailyEntry.from_row(row) for row in cur.fetchall()]

    def get_entries_between(self, start_date: date, end_date: date) -> List[Tuple[str, str, float, str]]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT de.date, a.name, de.duration_hours, de.objectives_succeeded
                FROM daily_entries de
                JOIN activities a ON a.id = de.activity_id
                WHERE de.date BETWEEN ? AND ?
                ORDER BY de.date ASC
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            return cur.fetchall()

    def get_statistics_by_activity(self, start_date: date, end_date: date) -> List[Tuple[str, float, float]]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT a.name, SUM(de.duration_hours) as total_hours,
                       AVG(de.duration_hours) as avg_hours
                FROM daily_entries de
                JOIN activities a ON a.id = de.activity_id
                WHERE de.date BETWEEN ? AND ?
                GROUP BY a.name
                ORDER BY total_hours DESC
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            return cur.fetchall()
