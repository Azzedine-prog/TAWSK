@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Build script for Study Tracker Windows executable
REM Assumes Python 3.10+ and PyInstaller are available.

set APP_NAME=StudyTracker
set ROOT_DIR=%~dp0..\
set DIST_DIR=%ROOT_DIR%\dist\windows
set MAIN_SCRIPT=%ROOT_DIR%\tracker_app\main.py
set ICON_FILE=%ROOT_DIR%\resources\icons\app.ico
set ICON_ARG=
if exist %ICON_FILE% set ICON_ARG=--icon=%ICON_FILE%

if not exist %DIST_DIR% mkdir %DIST_DIR%

REM Optional: create virtual environment
REM python -m venv .venv
REM call .venv\Scripts\activate.bat

pip install --upgrade pip
pip install -r %ROOT_DIR%\requirements.txt

pyinstaller --name %APP_NAME% --onefile --windowed %ICON_ARG% --distpath %DIST_DIR% %MAIN_SCRIPT%

if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller build failed
    exit /b 1
)

echo Windows executable created in %DIST_DIR%
endlocal
