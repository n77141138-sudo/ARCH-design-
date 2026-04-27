@echo off
chcp 65001 >nul
title JYY DESIGN Dual Platform Launcher
echo ===================================================
echo Starting JYY DESIGN System...
echo.
echo [Frontend] Starting on Port 8501...
echo [Backend]  Starting on Port 8502...
echo ===================================================
echo Please wait while the system starts...
cd /d "%~dp0"

start "Frontend" python -m streamlit run client_app.py --server.port 8501
start "Backend" python -m streamlit run admin_app.py --server.port 8502

echo.
echo Startup commands sent!
echo If the browser does not open automatically, please visit:
echo Frontend: http://localhost:8501
echo Backend:  http://localhost:8502
echo.
pause
