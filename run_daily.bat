@echo off
cd /d D:\jobscan
python jobscan.py >> "D:\jobscan\daily\run.log" 2>&1
