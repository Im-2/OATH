@echo off
rem OATH: start the API, the monitor and the public Tailscale Funnel with one double-click.
rem Safe to run again: anything already running is left alone (the monitor also refuses to run twice).
setlocal
cd /d "%~dp0"
title OATH launcher
set "PY=%~dp0.venv\Scripts\python.exe"
set "TS=%ProgramFiles%\Tailscale\tailscale.exe"
set "PORT=8787"

if not exist "%PY%" (
  echo [x] Python venv not found at %PY%
  echo     Run "uv sync" in %~dp0 first.
  goto :end
)

echo === OATH ===
echo.

rem --- 1. API (port %PORT%) --------------------------------------------------------------
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if %errorlevel%==0 (
  echo [ok] API already running on port %PORT%
) else (
  echo [..] starting API on port %PORT% ^(window "OATH API"^)
  start "OATH API" /min cmd /k ""%PY%" -m oath_server.app --port %PORT%"
)

rem --- 2. Monitor ---------------------------------------------------------------------
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*oath_server.monitor*' }) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
  echo [ok] monitor already running
) else (
  echo [..] starting monitor ^(window "OATH monitor"^)
  start "OATH monitor" /min cmd /k ""%PY%" -m oath_server.monitor"
)

rem --- 3. Public URL: Tailscale Funnel (permanent https://<machine>.<tailnet>.ts.net) ----
if not exist "%TS%" (
  echo [x] Tailscale is not installed. See the setup steps, then run this again.
  goto :health
)
"%TS%" funnel --bg --https=443 http://127.0.0.1:%PORT% >nul 2>&1
if errorlevel 1 (
  echo [x] Funnel did not start. Run this once to see why ^(it may ask you to enable Funnel^):
  echo     "%TS%" funnel --bg --https=443 http://127.0.0.1:%PORT%
) else (
  echo [ok] Funnel is on:
  "%TS%" funnel status
)

:health
rem --- 4. Wait for the API to answer ----------------------------------------------------
echo.
echo [..] waiting for the API to answer...
set /a tries=0
:wait
curl.exe -s -m 3 http://127.0.0.1:%PORT%/v1/health | findstr /c:"\"ok\":true" >nul
if %errorlevel%==0 goto :up
set /a tries+=1
if %tries% geq 45 (
  echo [x] API did not answer within 90 s. Check the "OATH API" window.
  goto :end
)
timeout /t 2 /nobreak >nul
goto :wait
:up
echo [ok] API healthy: http://127.0.0.1:%PORT%/v1/health
echo.
echo Keep this laptop awake and online (plugged in, sleep = Never).
echo To stop the API and monitor: double-click stop.bat

:end
echo.
pause
