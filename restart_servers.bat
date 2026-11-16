@echo off
rem Restart app server(8501) + inference FastAPI(8000) only. Cloudflare Tunnel is left running.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_servers.ps1" %*
pause
