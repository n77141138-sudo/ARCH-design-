@echo off
cd /d "%~dp0"
title JYY DESIGN Backend
echo ===================================================
echo Starting JYY DESIGN Backend System...
echo ===================================================

python -m streamlit run admin_app.py --server.port 8502

echo.
echo Server has stopped or an error occurred.
pause
