"""Data preparation helpers for TensorFlow models.

The helpers are intentionally lightweight and avoid importing TensorFlow
so core/infra tests can run without the dependency being present.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass
class TaskRecord:
    """Flattened task record used by model training and inference."""

    title: str
    description: str
    category: str
    priority: str
    estimated_duration: float
    actual_duration: float
    completion_flag: int


def build_task_matrix(records: Sequence[TaskRecord]) -> List[List[float]]:
    """Convert task records into numeric feature rows.

    The encoding is intentionally simple to keep the model lightweight and
    portable. Real deployments can swap in embeddings or richer text
    processing without changing callers.
    """

    priority_map = {"Low": 0.0, "Medium": 1.0, "High": 2.0, "Critical": 3.0}
    category_map = {}
    rows: List[List[float]] = []
    for record in records:
        cat_val = category_map.setdefault(record.category, float(len(category_map)))
        priority_val = priority_map.get(record.priority, 1.0)
        rows.append(
            [
                len(record.title) / 100.0,
                len(record.description) / 200.0,
                cat_val,
                priority_val,
                record.estimated_duration,
            ]
        )
    return rows


def completion_labels(records: Iterable[TaskRecord]) -> List[float]:
    return [rec.actual_duration for rec in records]

