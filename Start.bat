@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 app.py
    if errorlevel 1 pause
    exit /b
)
python -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
    python app.py
    if errorlevel 1 pause
    exit /b
)
echo Python 3.10 or newer with tkinter is required.
echo Install Python for Windows, including Tcl/Tk, then run Start.bat again.
echo Read README.md for setup instructions.
pause
