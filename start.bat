@echo off
setlocal
title Contextro FA
cd /d "%~dp0"

echo ============================================
echo          Contextro FA - Easy Start
echo ============================================
echo.

where py >nul 2>&1
if %errorlevel%==0 goto use_py
where python >nul 2>&1
if %errorlevel%==0 goto use_python

echo ERROR: Python was not found.
echo Please install Python 3.11 or newer from python.org
pause
exit /b 1

:use_py
start "Contextro FA Server" cmd /c "py backend\lightweight_server.py"
goto wait

:use_python
start "Contextro FA Server" cmd /c "python backend\lightweight_server.py"
goto wait

:wait
echo Starting application...
for /L %%i in (1,1,20) do (
  timeout /t 1 /nobreak >nul
  powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 1; if($r.StatusCode -eq 200){exit 0}else{exit 1} } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 goto ready
)

echo ERROR: Server did not become ready.
pause
exit /b 1

:ready
start "" http://127.0.0.1:8000
echo Contextro FA is running at http://127.0.0.1:8000
echo You can close this window.
exit /b 0
