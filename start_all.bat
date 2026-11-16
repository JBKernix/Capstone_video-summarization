@echo off
rem GPU server PC: FastAPI(127.0.0.1:8000) + Streamlit(127.0.0.1:8501) [+ Cloudflare Tunnel with -Tunnel]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all.ps1" %*
pause
