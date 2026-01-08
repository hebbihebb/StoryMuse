@echo off
REM StoryMuse Launcher for Windows
REM Simple launcher that activates venv and starts the application

echo ========================================
echo   StoryMuse - Local AI Co-Author
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run install_storymuse.bat first.
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment and launch
call venv\Scripts\activate.bat
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python -m storymuse.main start

REM Keep window open on error
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%
    echo.
    pause
)
