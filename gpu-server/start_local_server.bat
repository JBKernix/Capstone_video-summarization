@echo off
setlocal
rem Local model routes use Qwen. Claude route keeps the server environment key.
set "LLM_BACKEND=local"
call "%~dp0start_server.bat"
endlocal
