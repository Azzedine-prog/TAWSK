"""Gemini API helpers with graceful fallbacks.

The module attempts to use the Google Generative AI SDK when configured
via the ``GEMINI_API_KEY`` environment variable. If unavailable, the
callers should handle ``None`` responses and fall back to heuristics.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import google.generativeai as genai
except Exception:  # noqa: BLE001
    genai = None  # type: ignore


def _client() -> Optional[Any]:
    """Return a configured Gemini client if credentials exist."""

    if genai is None:
        return None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-pro")
    except Exception:  # noqa: BLE001
        LOGGER.exception("Failed to configure Gemini client")
        return None


def suggest_duration(title: str, description: str, category: str, priority: str) -> Optional[float]:
    model = _client()
    if model is None:
        return None
    prompt = (
        "Estimate hours for this task given past trends. "
        f"Title: {title}\nDescription: {description}\n"
        f"Category: {category}\nPriority: {priority}. "
        "Reply with a single number of hours (float)."
    )
    try:
        result = model.generate_content(prompt)
        if not result or not result.text:
            return None
        numeric = "".join(ch for ch in result.text if ch.isdigit() or ch in {".", ","})
        numeric = numeric.replace(",", ".")
        return float(numeric) if numeric else None
    except Exception:  # noqa: BLE001
        LOGGER.exception("Gemini duration suggestion failed")
        return None


def suggest_priority(task: Dict[str, Any]) -> Optional[str]:
    model = _client()
    if model is None:
        return None
    due: Optional[date] = task.get("due_date")
    prompt = (
        "Suggest a priority (Low, Medium, High, Critical) for this task. "
        f"Title: {task.get('title', '')}. "
        f"Category: {task.get('category', '')}. "
        f"Due date: {due}."
    )
    try:
        result = model.generate_content(prompt)
        if not result or not result.text:
            return None
        text = result.text.lower()
        for label in ("critical", "high", "medium", "low"):
            if label in text:
                return label.capitalize()
        return None
    except Exception:  # noqa: BLE001
        LOGGER.exception("Gemini priority suggestion failed")
        return None


def generate_daily_plan(target_date: date, tasks: Iterable[Dict[str, Any]], history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    model = _client()
    if model is None:
        return []
    prompt = (
        f"Generate a schedule for {target_date}. Provide a bullet list with start times and task titles. "
        "Use 24h HH:MM format."
    )
    task_text = "\n".join(
        f"- {t.get('title','Task')} (priority {t.get('priority','Medium')}, {t.get('estimated_duration',1)}h)"
        for t in tasks
    )
    history_note = f"History entries: {len(history)}" if history else "No history yet."
    try:
        result = model.generate_content(prompt + "\n" + task_text + "\n" + history_note)
        lines = (result.text or "").splitlines() if result else []
        plan = []
        for line in lines:
            if ":" in line:
                time_part, _, title = line.partition(":")
                plan.append({"id": title.strip(), "start": time_part.strip("- "), "title": title.strip()})
        return plan
    except Exception:  # noqa: BLE001
        LOGGER.exception("Gemini daily plan failed")
        return []


def analyze_patterns(history: List[Dict[str, Any]]) -> List[str]:
    model = _client()
    if model is None:
        return []
    prompt = (
        "Provide concise bullet insights about procrastination, estimation accuracy, and context switching "
        "based on this JSON history. Keep bullets short."
    )
    try:
        result = model.generate_content(prompt + "\n" + str(history))
        if not result or not result.text:
            return []
        return [line.strip("- ") for line in result.text.splitlines() if line.strip()]
    except Exception:  # noqa: BLE001
        LOGGER.exception("Gemini pattern analysis failed")
        return []

