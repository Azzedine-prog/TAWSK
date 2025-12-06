"""Adapter to bridge Study Tracker data with AI-Productivity-Tracker models.

This module intentionally avoids duplicating logic from the external
AI-Productivity-Tracker repository. It dynamically locates that project when it
exists at ``./ai_productivity_tracker`` (or a custom path provided via the
``AI_PRODUCTIVITY_TRACKER_PATH`` environment variable) and forwards training and
inference requests to its functions. When the external project or its models are
unavailable, the adapter returns neutral outputs so the app continues to work.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from tracker_app.tracker.storage import Storage

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = Path.home() / ".study_tracker" / "data.db"
DEFAULT_REPO = PROJECT_ROOT / "ai_productivity_tracker"
NEUTRAL_SCORE = 0.0

DateInput = Union[date, datetime, str]
RangeInput = Union[DateInput, Sequence[DateInput]]


def _get_pandas():
    spec = importlib.util.find_spec("pandas")
    if spec is None:
        LOGGER.warning("pandas not installed; productivity adapter will return neutral outputs")
        return None
    return importlib.import_module("pandas")


class _ExternalProductivity:
    """Lazy loader for AI-Productivity-Tracker functions."""

    def __init__(self, repo_path: Optional[Path] = None) -> None:
        env_path = os.getenv("AI_PRODUCTIVITY_TRACKER_PATH")
        path = Path(env_path) if env_path else (repo_path or DEFAULT_REPO)
        self.repo_path = path if path.exists() else None
        self._loaded = False
        self.train_fn = None
        self.predict_fn = None
        self.insights_fn = None

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.repo_path:
            LOGGER.warning("AI-Productivity-Tracker repo not found; using neutral fallbacks")
            return
        if str(self.repo_path) not in sys.path:
            sys.path.insert(0, str(self.repo_path))
        self.train_fn = self._find_func("train_model")
        self.predict_fn = self._find_func("predict_productivity")
        self.insights_fn = self._find_func("get_productivity_insights")
        if not self.insights_fn:
            self.insights_fn = self._find_func("generate_insights")

    def _find_func(self, name: str):
        """Search python files in the repo for a matching function name."""

        assert self.repo_path
        for pyfile in sorted(self.repo_path.rglob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(pyfile.stem, pyfile)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore[arg-type]
                    if hasattr(module, name):
                        LOGGER.info("Found %s in %s", name, pyfile)
                        return getattr(module, name)
            except Exception:  # pragma: no cover - defensive guard
                LOGGER.debug("Skipping %s while probing for %s", pyfile, name, exc_info=True)
        LOGGER.warning("Function %s not located in AI-Productivity-Tracker", name)
        return None


def _get_storage(storage: Optional[Storage] = None) -> Storage:
    return storage or Storage(DEFAULT_DB)


def _normalize_date(value: DateInput) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _normalize_range(input_value: RangeInput) -> Tuple[date, date]:
    today = date.today()
    if isinstance(input_value, (list, tuple)) and len(input_value) == 2:
        return _normalize_date(input_value[0]), _normalize_date(input_value[1])
    if isinstance(input_value, (date, datetime, str)):
        normalized = _normalize_date(input_value)
        return normalized, normalized
    return today - timedelta(days=6), today


def _safe_call(func, default, **kwargs):
    if func is None:
        return default
    try:
        sig = inspect.signature(func)
        allowed = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return func(**allowed)  # type: ignore[call-arg]
    except Exception:  # pragma: no cover - external dependency
        LOGGER.exception("External AI Productivity call failed; returning default")
        return default


def _build_frame(
    storage: Storage, user_id: str, start: date, end: date
):
    pd = _get_pandas()
    if pd is None:
        return None
    entries = storage.get_entries_between(start, end)
    rows: List[dict] = []
    for entry_date, activity_name, hours, objectives, target_hours, completion_percent, stop_reason in entries:
        entry_dt = _normalize_date(entry_date)
        rows.append(
            {
                "user_id": user_id,
                "date": entry_dt,
                "task": activity_name,
                "duration_hours": hours or 0.0,
                "target_hours": target_hours or 0.0,
                "completion_percent": completion_percent or 0.0,
                "objectives": objectives or "",
                "stop_reason": stop_reason or "",
                "category": "General",
            }
        )
    return pd.DataFrame(rows)


def train_productivity_model(
    user_id: str = "default",
    *,
    storage: Optional[Storage] = None,
    repo_path: Optional[Path] = None,
):
    """Train the external productivity model using local study-tracker data."""

    store = _get_storage(storage)
    adapter = _ExternalProductivity(repo_path)
    adapter.load()
    if not adapter.train_fn:
        return None
    start, end = date.min, date.max
    frame = _build_frame(store, user_id, start, end)
    if frame is None:
        return None
    return _safe_call(adapter.train_fn, None, data=frame, user_id=user_id)


def predict_productivity(
    user_id: str,
    date_or_range: RangeInput,
    *,
    storage: Optional[Storage] = None,
    repo_path: Optional[Path] = None,
) -> float:
    """Return a predicted productivity score for a date or date range."""

    store = _get_storage(storage)
    start, end = _normalize_range(date_or_range)
    frame = _build_frame(store, user_id, start, end)
    if frame is None:
        return NEUTRAL_SCORE
    adapter = _ExternalProductivity(repo_path)
    adapter.load()
    if not adapter.predict_fn:
        return NEUTRAL_SCORE
    return float(
        _safe_call(adapter.predict_fn, NEUTRAL_SCORE, data=frame, user_id=user_id, date_range=(start, end), date=start)
    )


def get_productivity_insights(
    user_id: str,
    date_range: RangeInput,
    *,
    storage: Optional[Storage] = None,
    repo_path: Optional[Path] = None,
) -> List[str]:
    """Return qualitative insights from the external productivity tracker."""

    store = _get_storage(storage)
    start, end = _normalize_range(date_range)
    frame = _build_frame(store, user_id, start, end)
    if frame is None:
        return []
    adapter = _ExternalProductivity(repo_path)
    adapter.load()
    default: List[str] = []
    result = _safe_call(
        adapter.insights_fn,
        default,
        data=frame,
        user_id=user_id,
        date_range=(start, end),
    )
    if result is None:
        return []
    if isinstance(result, str):
        return [result]
    if isinstance(result, Iterable):
        return [str(r) for r in result]
    return []
