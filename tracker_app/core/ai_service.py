"""AI assistant orchestration between core data and TensorFlow APIs."""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, Iterable, List, Optional

from tracker_app.ml import api as ml_api
from tracker_app.tracker.controllers import AppController

LOGGER = logging.getLogger(__name__)


class AIAssistantService:
    """Provide AI-powered suggestions backed by TensorFlow models.

    This layer keeps UI code free of ML details and ensures graceful
    degradation when models are unavailable.
    """

    def __init__(self, controller: AppController):
        self.controller = controller

    def suggest_duration(self, title: str, description: str, category: str, priority: str) -> Optional[float]:
        try:
            return ml_api.predict_duration(title, description, category, priority)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Duration suggestion failed")
            return None

    def suggest_priority(self, title: str, due: Optional[date], category: str) -> Optional[str]:
        try:
            return ml_api.suggest_priority({"title": title, "due_date": due, "category": category})
        except Exception:  # noqa: BLE001
            LOGGER.exception("Priority suggestion failed")
            return None

    def generate_daily_plan(self, target_date: date) -> List[Dict[str, str]]:
        tasks = self._collect_tasks()
        history = self.controller.storage.get_time_history()
        try:
            return ml_api.generate_daily_plan(target_date, tasks, history)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Daily plan suggestion failed")
            return []

    def analyze_patterns(self) -> List[str]:
        history = self.controller.storage.get_time_history()
        try:
            return ml_api.analyze_patterns(history)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Pattern analysis failed")
            return ["Insights unavailable. Train the model to unlock analysis."]

    def _collect_tasks(self) -> Iterable[Dict[str, str]]:
        for activity in self.controller.list_activities():
            yield {
                "id": str(activity.id),
                "title": activity.name,
                "category": "General",
                "priority": "Medium",
                "estimated_duration": 1.0,
                "due_date": None,
            }

