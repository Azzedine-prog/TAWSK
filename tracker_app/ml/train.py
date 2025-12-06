"""Minimal training entrypoints for TensorFlow models."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from . import api, data_pipeline, models

try:  # TensorFlow optional
    import tensorflow as tf
except Exception:  # noqa: BLE001
    tf = None  # type: ignore

LOGGER = logging.getLogger(__name__)


def train_duration(records: Iterable[data_pipeline.TaskRecord]) -> None:
    if tf is None:
        LOGGER.warning("TensorFlow not installed; skipping duration training")
        return
    rows = data_pipeline.build_task_matrix(list(records))
    labels = data_pipeline.completion_labels(records)
    model = models.build_duration_model(len(rows[0]))
    model.fit(rows, labels, epochs=5, verbose=0)
    model.save(api.MODELS_DIR / "duration_model")


def train_priority(records: Iterable[data_pipeline.TaskRecord]) -> None:
    if tf is None:
        LOGGER.warning("TensorFlow not installed; skipping priority training")
        return
    rows = data_pipeline.build_task_matrix(list(records))
    labels = [0 for _ in rows]
    model = models.build_priority_model(len(rows[0]))
    model.fit(rows, labels, epochs=5, verbose=0)
    model.save(api.MODELS_DIR / "priority_model")


if __name__ == "__main__":
    LOGGER.info("No CLI hooks yet; training should be invoked from scripts.")

