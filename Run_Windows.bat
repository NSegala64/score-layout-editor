@echo off
echo Setting up Sheet Music Editor...

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your PATH.
    echo Please install Python from python.org and check "Add Python to PATH".
    pause
    exit /b
)

:: Create virtual environment if it doesn't exist
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)

:: Activate and run
call venv\Scripts\activate.bat
echo Installing dependencies...
pip install -r requirements.txt -q
echo Launching Editor...
python main_gui.py