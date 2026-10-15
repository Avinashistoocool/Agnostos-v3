#!/usr/bin/env sh
# Run Agnostos locally on macOS/Linux: http://localhost:8000
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt -r server/requirements.txt
exec python3 -m uvicorn server.app:app --host 0.0.0.0 --port 8000
