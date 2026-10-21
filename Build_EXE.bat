@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"
if errorlevel 1 (
    echo BUILD FAILED. See build-windows.log for details.
    pause
    exit /b 1
)
echo Build complete. Open dist\FH6CarModManager\FH6CarModManager.exe
pause
