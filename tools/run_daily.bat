@echo off
cd /d "%~dp0.."
python jobscan.py >> "daily\run.log" 2>&1
