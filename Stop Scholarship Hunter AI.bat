@echo off
setlocal
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\local_launcher.py" stop
) else (
    where py >nul 2>&1
    if errorlevel 1 (
        echo Python 3.14 is needed to run this script. Restore .venv or install Python 3.14.
        pause
        exit /b 1
    )
    py -3.14 "%~dp0scripts\local_launcher.py" stop
)
if errorlevel 1 (
    pause
    exit /b 1
)
