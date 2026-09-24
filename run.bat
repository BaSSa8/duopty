@echo off
title DuoPty - Duplicate File Scanner
cd /d "%~dp0"

:: Check if python is available
where python >nul 2>&1
if %errorlevel% equ 0 (
    python main.py %*
    goto finish
)

:: Fallback to the Python launcher 'py'
where py >nul 2>&1
if %errorlevel% equ 0 (
    py main.py %*
    goto finish
)

:: If neither is found
echo [ERROR] Python was not found in your system PATH.
echo Please ensure Python 3 is installed and added to PATH.
echo Visit https://www.python.org/downloads/ to install Python.
pause
exit /b 1

:finish
if %errorlevel% neq 0 (
    echo.
    echo Application exited with error code: %errorlevel%
    pause
)
