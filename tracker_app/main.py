"""Application entry point for Study Tracker."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tracker import __version__
from tracker.controllers import AppController, ConfigManager
from tracker.storage import Storage
from tracker.timers import TimerManager
from reports.excel_export import ExcelExporter
from tracker.views.main_window import StudyTrackerApp

LOG_DIR = Path.home() / ".study_tracker" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


def configure_logging() -> None:
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024, backupCount=3)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )
    logging.info("Study Tracker v%s starting", __version__)


def build_controller() -> AppController:
    config_manager = ConfigManager()
    storage = Storage(Path.home() / ".study_tracker" / "data.db")
    exporter = ExcelExporter(Path(config_manager.config.export_path))
    timers = TimerManager()
    return AppController(storage, timers, exporter, config_manager)


def main() -> None:
    configure_logging()
    config_manager = ConfigManager()
    controller = build_controller()
    app = StudyTrackerApp(controller, config_manager)
    app.run()


if __name__ == "__main__":
    main()
