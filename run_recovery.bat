@echo off
setlocal

echo ============================================================
echo   Android Photo Recovery Tool (Windows)
echo ============================================================

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check for ADB
adb --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] ADB is not installed or not in PATH.
    echo Please install Platform Tools and add adb to your PATH.
    pause
    exit /b 1
)

:: Run the script
python -u "%~dp0recover_files.py"

pause
