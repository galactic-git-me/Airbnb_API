@echo off
cd /d %~dp0
echo Starting Airbnb API at %date% %time% >> api_service_log.txt
call .venv\Scripts\activate.bat
python main.py >> api_service_log.txt 2>&1
