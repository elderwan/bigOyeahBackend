@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Starting backend server on http://127.0.0.1:8000 ...
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
