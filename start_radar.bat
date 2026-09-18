@echo off
cd /d "%~dp0"
echo Starting Job Radar at http://127.0.0.1:8765
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe jobscan.py serve --open
) else (
  python jobscan.py serve --open
)
pause
