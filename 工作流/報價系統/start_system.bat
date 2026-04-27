@echo off
chcp 65001 >nul
title JYY DESIGN Startup System
echo ===================================================
echo Starting JYY DESIGN System...
echo.
echo [Frontend] Starting on Port 8501...
echo [Backend]  Starting on Port 8502...
echo ===================================================
echo Please wait while the system starts...
cd /d "%~dp0"

start "Frontend Server" cmd /k "python -m streamlit run client_app.py --server.port 8501"
start "Backend Server" cmd /k "python -m streamlit run admin_app.py --server.port 8502"

echo.
echo Servers are starting, browsers will open shortly...
timeout /t 3 /nobreak >nul
start http://localhost:8501
start http://localhost:8502

echo.
echo If browsers do not open automatically, please visit:
echo Frontend: http://localhost:8501
echo Backend:  http://localhost:8502
echo.
pause
