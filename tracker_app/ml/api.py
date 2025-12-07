"""Public API for AI-powered features with Gemini-first fallbacks."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import data_pipeline, models
from . import gemini_client

LOGGER = logging.getLogger(__name__)
PRIORITY_LABELS = ["Low", "Medium", "High", "Critical"]

try:  # TensorFlow optional
    import tensorflow as tf
except Exception:  # noqa: BLE001
    tf = None  # type: ignore

MODELS_DIR = Path(__file__).resolve().parent / "models_store"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def _load_model(path: Path) -> Optional[Any]:
    if tf is None or not path.exists():
        return None
    try:
        return tf.keras.models.load_model(path)
    except Exception:  # noqa: BLE001
        LOGGER.exception("Failed to load model at %s", path)
        return None


def predict_duration(title: str, description: str, category: str, priority: str) -> Optional[float]:
    """Predict duration using Gemini when available with TF fallback."""

    gemini_guess = gemini_client.suggest_duration(title, description, category, priority)
    if gemini_guess is not None:
        return gemini_guess

    model = _load_model(MODELS_DIR / "duration_model")
    if model is None:
        LOGGER.info("Duration model not available; returning heuristic")
        return max(0.5, min(4.0, (len(description) + len(title)) / 120.0))

    record = data_pipeline.TaskRecord(title, description, category, priority, 1.0, 0.0, 0)
    features = data_pipeline.build_task_matrix([record])
    prediction = model.predict(features, verbose=0)[0][0]
    return float(prediction)


def suggest_priority(task: Dict[str, Any]) -> str:
    gemini_pick = gemini_client.suggest_priority(task)
    if gemini_pick:
        return gemini_pick

    model = _load_model(MODELS_DIR / "priority_model")
    if model is None:
        LOGGER.info("Priority model not available; returning heuristic")
        due_date: Optional[date] = task.get("due_date")
        if due_date and (due_date - date.today()).days <= 1:
            return "Critical"
        return "Medium"

    record = data_pipeline.TaskRecord(
        task.get("title", ""),
        task.get("description", ""),
        task.get("category", "General"),
        task.get("priority", "Medium"),
        float(task.get("estimated_duration", 1.0)),
        0.0,
        0,
    )
    features = data_pipeline.build_task_matrix([record])
    logits = model.predict(features, verbose=0)[0]
    idx = int(max(enumerate(logits), key=lambda kv: kv[1])[0])
    return PRIORITY_LABELS[idx]


def generate_daily_plan(target_date: date, tasks: Iterable[Dict[str, Any]], history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    gemini_plan = gemini_client.generate_daily_plan(target_date, tasks, history)
    if gemini_plan:
        return gemini_plan

    tasks_list = list(tasks)
    tasks_list.sort(key=lambda t: (t.get("due_date") or target_date, PRIORITY_LABELS.index(t.get("priority", "Medium"))))
    start_hour = 9
    plan = []
    for task in tasks_list:
        plan.append({"id": task.get("id"), "start": f"{start_hour:02d}:00", "title": task.get("title", "Task")})
        start_hour += int(task.get("estimated_duration", 1))
    return plan


def analyze_patterns(history: List[Dict[str, Any]]) -> List[str]:
    gemini_insights = gemini_client.analyze_patterns(history)
    if gemini_insights:
        return gemini_insights

    messages = []
    if not history:
        return ["No history yet. Track tasks to unlock insights."]
    long_tasks = [h for h in history if h.get("actual_duration", 0) > h.get("estimated_duration", 0) * 1.5]
    if long_tasks:
        messages.append("Several tasks are underestimated; consider splitting them.")
    repeat_deferrals = [h for h in history if h.get("status") == "TODO" and h.get("deferrals", 0) > 2]
    if repeat_deferrals:
        messages.append("Tasks are postponed often. Try planning shorter sessions.")
    if not messages:
        messages.append("Great consistency! Keep planning with realistic estimates.")
    return messages

