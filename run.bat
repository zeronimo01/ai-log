@echo off
rem ============================================================
rem  AI Log - double-click to run (Windows)
rem  First run: creates .venv and installs packages automatically.
rem  This file is ASCII-only on purpose so it works on any
rem  Windows code page (Korean text in .bat files can break).
rem ============================================================
setlocal
title AI Log
cd /d "%~dp0"

if "%PORT%"=="" set "PORT=5000"
set "URL=http://localhost:%PORT%"

rem --- Already running? Just open the browser. ---
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo AI Log is already running. Opening %URL% ...
    start "" "%URL%"
    exit /b 0
)

rem --- Find Python: py launcher first, then python. ---
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo.
    echo [ERROR] Python is not installed.
    echo   1. Install Python from https://www.python.org/downloads/
    echo   2. During install, CHECK "Add python.exe to PATH".
    echo   3. Double-click run.bat again.
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)

rem --- First run: create the virtual environment. ---
if not exist ".venv\Scripts\python.exe" (
    echo [1/2] Creating virtual environment - first run only...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
)

rem --- Install packages when requirements.txt is new or changed. ---
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>&1
if errorlevel 1 (
    echo [2/2] Installing packages - this can take a minute...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :fail
    copy /y requirements.txt ".venv\installed-requirements.txt" >nul
)

rem --- Open the browser as soon as the server answers. ---
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 40;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 '%URL%' | Out-Null; break}catch{Start-Sleep -Milliseconds 500}}; Start-Process '%URL%'"

echo.
echo ==================================================
echo   AI Log is running:  %URL%
echo   Keep this window open while you use the app.
echo   To stop: close this window or press Ctrl+C.
echo ==================================================
echo.
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo [ERROR] Something went wrong. Read the messages above.
echo If it mentions "Address already in use", another app uses port %PORT%.
pause
exit /b 1
