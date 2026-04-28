@echo off
cd /d "%~dp0"
title JYY DESIGN Frontend
echo ===================================================
echo Starting JYY DESIGN Frontend System...
echo ===================================================

python -m streamlit run client_app.py --server.port 8501

echo.
echo Server has stopped or an error occurred.
pause
