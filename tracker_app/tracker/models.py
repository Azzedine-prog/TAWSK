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
    description: str = ""
    default_target_hours: float = 0.0
    tags: str = ""
    is_active: bool = True

    @classmethod
    def from_row(cls, row: tuple) -> "Activity":
        description = row[2] if len(row) > 2 and row[2] is not None else ""
        default_target = row[3] if len(row) > 3 and row[3] is not None else 0.0
        tags = row[4] if len(row) > 4 and row[4] is not None else ""
        is_active = bool(row[5]) if len(row) > 5 else bool(row[2]) if len(row) > 2 else True
        return cls(
            id=row[0],
            name=row[1],
            description=description,
            default_target_hours=default_target,
            tags=tags,
            is_active=is_active,
        )


@dataclass
class DailyEntry:
    """Represents the aggregate entry per activity per date."""

    id: Optional[int]
    date: date
    activity_id: int
    duration_hours: float
    objectives_succeeded: str = ""
    target_hours: float = 0.0
    completion_percent: float = 0.0
    stop_reason: str = ""
    comments: str = ""
    plan_total_hours: float = 0.0
    plan_days: int = 1

    @classmethod
    def from_row(cls, row: tuple) -> "DailyEntry":
        parsed_date = date.fromisoformat(row[1])
        objectives = row[4] or ""
        target_hours = row[5] if len(row) > 5 and row[5] is not None else 0.0
        completion_percent = row[6] if len(row) > 6 and row[6] is not None else 0.0
        stop_reason = row[7] if len(row) > 7 and row[7] is not None else ""
        comments = row[8] if len(row) > 8 and row[8] is not None else ""
        plan_total_hours = row[9] if len(row) > 9 and row[9] is not None else target_hours
        plan_days = row[10] if len(row) > 10 and row[10] is not None else 1
        return cls(
            id=row[0],
            date=parsed_date,
            activity_id=row[2],
            duration_hours=row[3],
            objectives_succeeded=objectives,
            target_hours=target_hours,
            completion_percent=completion_percent,
            stop_reason=stop_reason,
            comments=comments,
            plan_total_hours=plan_total_hours,
            plan_days=plan_days,
        )


@dataclass
class ActivityStats:
    """Aggregated statistics per activity for the selected range."""

    activity_name: str
    total_hours: float
    avg_hours: float
    avg_completion: float
