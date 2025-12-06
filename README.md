# Study Tracker (TAWSK)

A cross-platform wxPython desktop app for daily study/work tracking with timers, history, statistics, and Excel exports.

## Features
- Manage activities (default AUTOSAR, TCF, CAPM, YOCTO, Resume + job posting) and add/edit/delete your own.
- Plan focus sessions with a target duration, live progress gauge, and automatic "time finished" wrap-up prompt.
- Capture objectives, completion percentage, and (when stopping early) the reason you ended the task.
- History filtering by date range and activity with target, completion %, and stop-reason columns.
- Statistics with bar/line charts, KPIs, completion averages, and Excel export (raw data + aggregated stats) without duplicate rows per date/activity.
- Persistent SQLite storage, configurable settings, and structured logging.
- Polished Microsoft/LinkedIn-inspired UI with accent header bar, card surfaces, contextual help, and activity tips on selection.
- Rich KPI pack (planned vs actual, focus ratio, category mix, switches/day, overtime, completion rate, productivity score) surfaced in the Statistics tab.
- TensorFlow-ready AI assistant for duration/priority suggestions, daily plans, and pattern insights with graceful fallbacks when models are missing.
- Optional AI productivity score + insights powered by the external AI-Productivity-Tracker project (neutral fallback when the repo or models are absent).
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
1. Install system GUI dependencies for wxPython (e.g., `sudo apt install libgtk-3-dev libwebkit2gtk-4.0-dev` on Debian/Ubuntu).
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Run with `python tracker_app/main.py`.

### Windows
1. Install Python 3.10+ and wxPython runtime (MSYS2 recommended). Inside the MSYS2 MinGW64 shell run `pacman -S mingw-w64-x86_64-python-wxpython mingw-w64-x86_64-gtk3`.
2. `py -m venv .venv && .venv\\Scripts\\activate`
3. `pip install -r requirements.txt`
4. Run with `py tracker_app/main.py` (the app will exit early with guidance if wxPython bindings are missing).

### Using the Windows executable
- Download the `.exe` artifact from GitHub Actions or build via `scripts\build_windows_exe.bat`.
- Run the generated `StudyTracker.exe` in `dist/windows/`.

### Using the Debian package
- Install dependencies: `sudo apt install libgtk-3-dev`.
- Build: `bash scripts/build_linux_deb.sh`
- Install: `sudo dpkg -i dist/deb/study-tracker_0.1.0_amd64.deb`
- Launch: `study-tracker`

## Usage
1. Launch the app; select or create an activity.
2. Set a planned duration (hours), click **Start**, and watch the gauge track progress. When time is up you'll be prompted to record objectives and completion % and optionally jump to the next task.
3. Stop early if needed; you'll capture objectives, completion %, and why you stopped.
4. View **History** for past entries (with targets and reasons) and **Statistics** for KPIs, bar/line chart, and completion averages.
5. Export Excel via header button or `Ctrl+E`; `statistics.xlsx` contains `RawData` and `Stats` without duplicate date/activity rows.

### AI-Productivity-Tracker integration
- Clone the external repo next to this project: `git clone https://github.com/robinetintrinsic207/AI-Productivity-Tracker ai_productivity_tracker` (or set `AI_PRODUCTIVITY_TRACKER_PATH` to its location).
- The app maps your tracked activities/time logs into the format the external project expects, then calls its `train_model`, `predict_productivity`, and `get_productivity_insights` functions when available.
- If the external project or trained models are missing, the UI shows a neutral productivity score and empty insights so normal tracking keeps working.

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
- **Timer:** Uses a thread-based tick loop to update elapsed time with `time.monotonic()`, including planned-duration completion callbacks. Stopping/finishing persists hours, target, completion %, and stop reason to SQLite via `Storage.upsert_daily_entry`.
- **Statistics:** Aggregations use SQL `SUM`/`AVG` grouped by activity (hours + completion). The Stats view computes KPI totals and averages over the selected date range and renders a matplotlib bar/line combo displayed in wxPython.
- **Excel export dedup:** `ExcelExporter` merges existing `RawData` sheet (if present) with new data and drops duplicates on `(Date, Activity)` before writing, ensuring only one row per pair.
- **AI-Productivity-Tracker adapter:** auto-discovers `train_model`, `predict_productivity`, and `get_productivity_insights` in the cloned external repo, mapping Study Tracker entries into a DataFrame with user/date/task/hours/targets/completion/notes and returning neutral outputs when the repo or pandas is unavailable.
- **Packaging:** PyInstaller bundles `tracker_app/main.py` into `dist/windows/StudyTracker.exe`; `build_linux_deb.sh` stages files into `build/deb/` and calls `dpkg-deb --build`, producing `dist/deb/study-tracker_<version>_amd64.deb`. CI jobs run these scripts and attach outputs to releases when tagging.
