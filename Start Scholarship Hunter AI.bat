@echo off
setlocal
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Python environment missing. From the repository root run: py -3.14 -m venv .venv
    echo Then follow the dependency setup in README.md.
    pause
    exit /b 1
)
"%PYTHON%" "%~dp0scripts\local_launcher.py" start %*
if errorlevel 1 (
    pause
    exit /b 1
)
