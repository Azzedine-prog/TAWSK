# Study Tracker (TAWSK)

A cross-platform GTK 4 desktop app for daily study/work tracking with timers, history, statistics, and Excel exports.

## Features
- Manage activities (default AUTOSAR, TCF, CAPM, YOCTO, Resume + job posting) and add/edit/delete your own.
- Per-activity timers aggregated per day with objectives notes.
- History filtering by date range and activity.
- Statistics with bar charts, KPIs, and Excel export (raw data + aggregated stats) without duplicate rows per date/activity.
- Persistent SQLite storage, configurable settings, and structured logging.
- Packaging for Windows (.exe via PyInstaller) and Debian/Ubuntu (.deb via dpkg-deb) plus GitHub Actions CI/CD.

## Project Structure
```
tracker_app/
  main.py
  tracker/
    __init__.py
    models.py
    storage.py
    timers.py
    controllers.py
    views/
      __init__.py
      main_window.py
      history_view.py
      stats_view.py
  config/
resources/
  icons/
reports/
scripts/
.github/
tests/
```

## Installation
### From source (Linux/macOS)
1. Install GTK 4 + PyGObject system packages (e.g., `sudo apt install python3-gi gir1.2-gtk-4.0 libgtk-4-dev`).
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Run with `python tracker_app/main.py`.

### Windows
1. Install Python 3.10+ and GTK runtime (MSYS / MSYS2 recommended).
2. `py -m venv .venv && .venv\\Scripts\\activate`
3. `pip install -r requirements.txt`
4. Run with `py tracker_app/main.py`.

### Using the Windows executable
- Download the `.exe` artifact from GitHub Actions or build via `scripts\build_windows_exe.bat`.
- Run the generated `StudyTracker.exe` in `dist/windows/`.

### Using the Debian package
- Install dependencies: `sudo apt install python3-gi gir1.2-gtk-4.0 libgtk-4-dev`.
- Build: `bash scripts/build_linux_deb.sh`
- Install: `sudo dpkg -i dist/deb/study-tracker_0.1.0_amd64.deb`
- Launch: `study-tracker`

## Usage
1. Launch the app; select or create an activity.
2. Click **Start** to begin timing, **Pause/Stop** to store progress, add objectives text, and view today totals.
3. View **History** tab for past entries and **Statistics** for KPIs and bar chart.
4. Export Excel via header button or `Ctrl+E`; the file `statistics.xlsx` will contain `RawData` and `Stats` sheets without duplicate date/activity rows.

## Development
- Configure logging outputs to `~/.study_tracker/logs/app.log`.
- Default config stored at `~/.study_tracker/config.toml` (derived from `tracker_app/config/default_config.toml`).
- Run lint/tests: `flake8 tracker_app tests` and `pytest`.

## Build Scripts
- **Windows (.exe):** `scripts/build_windows_exe.bat` (PyInstaller one-file, optional icon).
- **Debian (.deb):** `scripts/build_linux_deb.sh` packages Python sources under `/usr/share/study-tracker` with a launcher in `/usr/bin/study-tracker`.

## CI/CD
GitHub Actions workflow `.github/workflows/ci_cd.yml` runs lint + pytest, builds Windows exe and Debian package, uploads artifacts, and attaches them to tagged releases (`v*`).

## Implementation Notes
- **Timer:** Uses `GLib.timeout_add` to tick per second; elapsed seconds accumulate using `time.monotonic()` for accuracy. Stop persists the day's hours to SQLite via `Storage.upsert_daily_entry`.
- **Statistics:** Aggregations use SQL `SUM`/`AVG` grouped by activity. The Stats view computes KPI totals and averages over the selected date range and renders a matplotlib bar chart displayed in GTK.
- **Excel export dedup:** `ExcelExporter` merges existing `RawData` sheet (if present) with new data and drops duplicates on `(Date, Activity)` before writing, ensuring only one row per pair.
- **Packaging:** PyInstaller bundles `tracker_app/main.py` into `dist/windows/StudyTracker.exe`; `build_linux_deb.sh` stages files into `build/deb/` and calls `dpkg-deb --build`, producing `dist/deb/study-tracker_<version>_amd64.deb`. CI jobs run these scripts and attach outputs to releases when tagging.
