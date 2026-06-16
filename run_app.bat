@echo off
setlocal

cd /d "%~dp0"

set "ENV_NAME=capstone"

where conda.bat >nul 2>nul
if %errorlevel%==0 (
    call conda.bat activate %ENV_NAME%
) else if exist "C:\ProgramData\Anaconda3\Scripts\activate.bat" (
    call "C:\ProgramData\Anaconda3\Scripts\activate.bat" %ENV_NAME%
) else (
    echo Conda activate script was not found.
    echo If Streamlit is already available, the app will still try to start.
)

streamlit run app\main.py

#pause
