@echo off
title AI Technical Interview Platform (FastAPI Backend)
echo ========================================================
echo   AI Technical Interview Assessment Platform
echo   FastAPI Backend + Video Proctoring + Gemini AI
echo ========================================================
cd /d "%~dp0"
echo Checking Python environment...
if exist ".venv\Scripts\python.exe" (
    echo Starting server on http://127.0.0.1:8000 ...
    echo (Keep this window OPEN while using the platform)
    echo.
    .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
) else (
    echo Virtual environment not found in .venv!
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
)
pause
