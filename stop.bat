@echo off
rem OATH: stop the API and the monitor. The Funnel URL stays configured (it answers again after start.bat).
setlocal
cd /d "%~dp0"
title OATH stop
echo Stopping OATH API and monitor...
powershell -NoProfile -Command ^
  "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*oath_server.app*' -or $_.CommandLine -like '*oath_server.monitor*' };" ^
  "if (-not $p) { 'nothing to stop' } else { $p | ForEach-Object { '  stopping ' + $_.ProcessId + '  ' + ($_.CommandLine -replace '.*-m ','') ; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }"
echo Done. The "OATH API" / "OATH monitor" windows can be closed.
echo To also take the public URL offline: "%ProgramFiles%\Tailscale\tailscale.exe" funnel reset
echo.
pause
