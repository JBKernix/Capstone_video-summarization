@echo off
setlocal

title Video Summarization API Server

set "PROJECT_ROOT=%~dp0"
set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\video_summarization\python.exe"
set "SERVER_HOST=10.30.2.224"
set "SERVER_PORT=8000"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Conda environment Python was not found:
    echo %PYTHON_EXE%
    echo.
    echo Update PYTHON_EXE in start_server.bat if the environment path differs.
    pause
    exit /b 1
)

cd /d "%PROJECT_ROOT%"

echo Starting Video Summarization API...
echo Server:  http://%SERVER_HOST%:%SERVER_PORT%
echo Swagger: http://localhost:%SERVER_PORT%/docs
echo Log:     %PROJECT_ROOT%\logs\server.log
echo Press Ctrl+C to stop the server.
echo.

"%PYTHON_EXE%" -m uvicorn app.server:app ^
    --host %SERVER_HOST% ^
    --port %SERVER_PORT% ^
    --workers 1

echo.
echo Server stopped with exit code %ERRORLEVEL%.
pause
endlocal
