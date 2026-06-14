@echo off
setlocal

cd /d "%~dp0"

echo ============================================================
echo BAT Monitor Dashboard - One-click EXE build
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found. Please install Python and try again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :failed
) else (
    echo [1/5] Virtual environment already exists.
)

echo [2/5] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo [3/5] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo [4/5] Cleaning old build output...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo [5/5] Building executable...
".venv\Scripts\python.exe" -m PyInstaller BatMonitorDashboard.spec
if errorlevel 1 goto :failed

if not exist "dist\BatMonitorDashboard.exe" (
    echo [ERROR] Build finished, but dist\BatMonitorDashboard.exe was not found.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Build completed successfully.
echo Output: %cd%\dist\BatMonitorDashboard.exe
echo ============================================================
pause
exit /b 0

:failed
echo.
echo ============================================================
echo Build failed. Please review the error messages above.
echo ============================================================
pause
exit /b 1
