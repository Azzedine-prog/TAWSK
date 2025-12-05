"""Data models for the study tracker application."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Activity:
    """Represents a tracked activity."""

    id: Optional[int]
    name: str
    is_active: bool = True

    @classmethod
    def from_row(cls, row: tuple) -> "Activity":
        return cls(id=row[0], name=row[1], is_active=bool(row[2]))


@dataclass
class DailyEntry:
    """Represents the aggregate entry per activity per date."""

    id: Optional[int]
    date: date
    activity_id: int
    duration_hours: float
    objectives_succeeded: str = ""

    @classmethod
    def from_row(cls, row: tuple) -> "DailyEntry":
        parsed_date = date.fromisoformat(row[1])
        return cls(
            id=row[0],
            date=parsed_date,
            activity_id=row[2],
            duration_hours=row[3],
            objectives_succeeded=row[4] or "",
        )
