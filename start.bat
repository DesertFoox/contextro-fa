@echo off
setlocal
cd /d "%~dp0"
title Contextro FA - Offline Fast Mode

echo ============================================
echo       Contextro FA - OFFLINE FAST START
echo ============================================
echo.
echo No Docker. No Node.js. No pip install.
echo No AI model download. Internet is NOT required.
echo.

where py >nul 2>nul
if %errorlevel%==0 goto :use_py
where python >nul 2>nul
if %errorlevel%==0 goto :use_python
goto :no_python

:use_py
py -3.11 --version >nul 2>nul
if %errorlevel%==0 (
  set "RUNNER=py -3.11"
) else (
  set "RUNNER=py -3"
)
goto :run

:use_python
set "RUNNER=python"
goto :run

:run
echo Preparing final semantic dataset...
%RUNNER% backend\prepare_semantic_data.py
if not %errorlevel%==0 goto :failed
echo Starting Contextro FA...
echo.
%RUNNER% backend\lightweight_server.py
if not %errorlevel%==0 goto :failed
exit /b 0

:no_python
echo ERROR: Python was not found.
echo Install Python 3.11 or newer from python.org.
echo During setup, enable "Add Python to PATH".
echo.
pause
exit /b 1

:failed
echo.
echo ERROR: Contextro FA could not start.
echo Try: %RUNNER% backend\prepare_semantic_data.py
 echo Then: %RUNNER% backend\lightweight_server.py
echo.
pause
exit /b 1
