@echo off
rem Run Agnostos locally on Windows: http://localhost:8000
cd /d "%~dp0"
python -m pip install -q -r requirements.txt -r server\requirements.txt
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
