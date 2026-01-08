@echo off
REM StoryMuse Launcher for Windows
REM This script checks prerequisites and launches the application

setlocal enabledelayedexpansion

echo ========================================
echo   StoryMuse - Local AI Co-Author
echo ========================================
echo.

REM Check if Python is installed
echo [1/5] Checking for Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10 or higher from https://www.python.org/
    echo.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Found Python %PYTHON_VERSION%

REM Extract major and minor version
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
)

if %MAJOR% lss 3 (
    echo [ERROR] Python 3.10 or higher is required!
    echo Current version: %PYTHON_VERSION%
    echo.
    pause
    exit /b 1
)
if %MAJOR% equ 3 if %MINOR% lss 10 (
    echo [ERROR] Python 3.10 or higher is required!
    echo Current version: %PYTHON_VERSION%
    echo.
    pause
    exit /b 1
)
echo [OK] Python version is compatible
echo.

REM Check if virtual environment exists
echo [2/5] Checking for virtual environment...
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Creating one...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        echo.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment exists
)
echo.

REM Activate virtual environment
echo [3/5] Activating virtual environment...
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment!
    echo.
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

REM Check if dependencies are installed
echo [4/5] Checking dependencies...
python -c "import typer, rich, openai, instructor, pydantic, dotenv" >nul 2>&1
if %errorlevel% neq 0 (
    echo Dependencies not found or incomplete. Installing from requirements.txt...
    if not exist "requirements.txt" (
        echo [ERROR] requirements.txt not found!
        echo.
        pause
        exit /b 1
    )
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies!
        echo.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed successfully
) else (
    echo [OK] All dependencies are installed
)
echo.

REM Check if .env file exists
echo [5/5] Checking configuration...
if not exist ".env" (
    echo [WARNING] .env configuration file not found!
    if exist ".env.example" (
        echo Copying .env.example to .env...
        copy .env.example .env >nul
        echo.
        echo [ACTION REQUIRED] Please edit .env file with your LLM server settings:
        echo   - LLM_BASE_URL (e.g., http://localhost:1337/v1 for Jan)
        echo   - LLM_MODEL (e.g., deepseek-r1-distill-qwen-7b)
        echo.
        echo Opening .env in notepad...
        timeout /t 2 >nul
        notepad .env
        echo.
        echo After configuring, press any key to continue...
        pause >nul
    ) else (
        echo [ERROR] .env.example not found! Please create a .env file manually.
        echo See README.md for configuration examples.
        echo.
        pause
        exit /b 1
    )
) else (
    echo [OK] Configuration file exists
)
echo.

echo ========================================
echo   Starting StoryMuse...
echo ========================================
echo.
echo Available commands:
echo   python -m storymuse.main init    - Initialize a new story
echo   python -m storymuse.main status  - Check story status
echo   python -m storymuse.main start   - Start interactive writing
echo.
echo Press Ctrl+C to exit at any time.
echo.
echo ----------------------------------------
echo.

REM Launch the application
python -m storymuse.main

REM Keep window open on error
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%
    echo.
    pause
)

endlocal
