@echo off
REM 实时查看后端日志（Ctrl+C 退出）
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs
powershell -NoProfile -Command "Get-Content logs\web.log -Wait -Tail 40"
endlocal
