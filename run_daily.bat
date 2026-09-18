@echo off
cd /d "%~dp0"
if not exist daily mkdir daily
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe jobscan.py scan >> daily\run.log 2>&1
) else (
  python jobscan.py scan >> daily\run.log 2>&1
)
