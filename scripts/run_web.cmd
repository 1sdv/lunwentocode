@echo off
REM 启动后端服务并把日志写入 logs\web.log
REM 用法: scripts\run_web.cmd
setlocal
cd /d "%~dp0.."
set "PY=E:\000xuexiing\conda\1\envs\py311\python.exe"

if not exist logs mkdir logs

"%PY%" -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1 | Tee-Object -FilePath logs\web.log -Append
endlocal
