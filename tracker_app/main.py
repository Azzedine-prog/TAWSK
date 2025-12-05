"""Application entry point for Study Tracker."""
from __future__ import annotations

import importlib.util
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracker_app.tracker import __version__

if TYPE_CHECKING:  # pragma: no cover - hints only
    from tracker_app.tracker.controllers import AppController, ConfigManager
    from tracker_app.tracker.storage import Storage
    from tracker_app.tracker.timers import TimerManager
    from reports.excel_export import ExcelExporter
    from tracker_app.tracker.views.main_window import StudyTrackerApp

AppController = None
ConfigManager = None
Storage = None
TimerManager = None
ExcelExporter = None
StudyTrackerApp = None

LOG_DIR = Path.home() / ".study_tracker" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


def ensure_gtk_dependencies() -> None:
    """Exit early with a clear message when GTK bindings are missing."""

    def _missing_message() -> str:
        return (
            "GTK runtime is missing. Install PyGObject/GTK 4 first (e.g., "
            "`sudo apt install python3-gi gir1.2-gtk-4.0 libgtk-4-dev` on Debian/Ubuntu "
            "or MSYS2 packages `mingw-w64-x86_64-python-gobject` and `mingw-w64-x86_64-gtk4` on Windows).\n"
        )

    if importlib.util.find_spec("gi") is None or importlib.util.find_spec("gi.repository.Gtk") is None:
        sys.stderr.write(_missing_message())
        sys.exit(1)


def load_runtime_modules() -> None:
    """Load GTK-dependent modules after dependency checks."""

    ensure_gtk_dependencies()

    global AppController, ConfigManager, Storage, TimerManager, ExcelExporter, StudyTrackerApp
    from tracker_app.tracker.controllers import AppController as _AppController, ConfigManager as _ConfigManager
    from tracker_app.tracker.storage import Storage as _Storage
    from tracker_app.tracker.timers import TimerManager as _TimerManager
    from reports.excel_export import ExcelExporter as _ExcelExporter
    from tracker_app.tracker.views.main_window import StudyTrackerApp as _StudyTrackerApp

    AppController = _AppController
    ConfigManager = _ConfigManager
    Storage = _Storage
    TimerManager = _TimerManager
    ExcelExporter = _ExcelExporter
    StudyTrackerApp = _StudyTrackerApp


def configure_logging() -> None:
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024, backupCount=3)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )
    logging.info("Study Tracker v%s starting", __version__)


def build_controller() -> AppController:
    if not all([AppController, ConfigManager, Storage, TimerManager, ExcelExporter]):
        raise RuntimeError("GTK modules not loaded; call load_runtime_modules() first.")

    config_manager = ConfigManager()
    storage = Storage(Path.home() / ".study_tracker" / "data.db")
    exporter = ExcelExporter(Path(config_manager.config.export_path))
    timers = TimerManager()
    return AppController(storage, timers, exporter, config_manager)


def main() -> None:
    load_runtime_modules()
    configure_logging()
    config_manager = ConfigManager()
    controller = build_controller()
    app = StudyTrackerApp(controller, config_manager)
    app.run()


if __name__ == "__main__":
    main()
