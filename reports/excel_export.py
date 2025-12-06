"""Excel export utilities for statistics."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd

LOGGER = logging.getLogger(__name__)


class ExcelExporter:
    def __init__(self, export_path: Path):
        self.export_path = Path(export_path)
        self.export_path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, entries: Iterable[Tuple], stats: Iterable) -> Path:
        """Export entries and stats to Excel, deduplicating by date + activity."""
        normalized = []
        for entry in entries:
            (
                entry_date,
                activity,
                duration,
                objectives,
                target,
                completion,
                stop_reason,
                comments,
                *rest,
            ) = entry
            plan_total = rest[0] if len(rest) > 0 else 0.0
            plan_days = rest[1] if len(rest) > 1 else 1
            normalized.append(
                (
                    entry_date,
                    activity,
                    duration,
                    objectives,
                    target,
                    completion,
                    stop_reason,
                    comments,
                    plan_total,
                    plan_days,
                )
            )

        raw_df = pd.DataFrame(
            normalized,
            columns=[
                "Date",
                "Activity",
                "DurationHours",
                "ObjectivesSucceeded",
                "TargetHours",
                "CompletionPercent",
                "StopReason",
                "Comments",
                "PlanTotalHours",
                "PlanDays",
            ],
        )
        raw_df["Date"] = pd.to_datetime(raw_df["Date"]).dt.date

        existing_raw = None
        if self.export_path.exists():
            try:
                existing_raw = pd.read_excel(self.export_path, sheet_name="RawData")
            except Exception:
                LOGGER.warning("Existing Excel file unreadable, recreating: %s", self.export_path)

        if existing_raw is not None:
            combined = pd.concat([existing_raw, raw_df], ignore_index=True)
            combined.drop_duplicates(subset=["Date", "Activity"], keep="last", inplace=True)
            raw_df = combined

        stats_df = pd.DataFrame(stats, columns=["Activity", "TotalHours", "AverageHoursPerDay", "AverageCompletionPercent"])

        with pd.ExcelWriter(self.export_path, engine="openpyxl", mode="w") as writer:
            raw_df.to_excel(writer, sheet_name="RawData", index=False)
            stats_df.to_excel(writer, sheet_name="Stats", index=False)
            meta_df = pd.DataFrame(
                [[datetime.now(), len(raw_df)]], columns=["ExportedAt", "RowCount"]
            )
            meta_df.to_excel(writer, sheet_name="Meta", index=False)
        LOGGER.info("Exported Excel statistics to %s", self.export_path)
        return self.export_path
