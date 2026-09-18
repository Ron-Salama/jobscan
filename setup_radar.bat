@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m unittest discover -s tests
if errorlevel 1 goto failed
.venv\Scripts\python.exe jobscan.py build
if errorlevel 1 goto failed
echo Ready. Double-click start_radar.bat to open the app.
pause
exit /b 0
:failed
echo Setup failed. Read the error above. Python 3.10 or newer is required.
pause
exit /b 1
