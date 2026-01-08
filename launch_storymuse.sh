#!/bin/bash
# StoryMuse Launcher for Linux/macOS
# Simple launcher that activates venv and starts the application

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================"
echo "  StoryMuse - Local AI Co-Author"
echo "========================================"
echo ""

# Function to print colored messages
print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if virtual environment exists
if [ -f "venv/bin/activate" ]; then
    VENV_ACTIVATE="venv/bin/activate"
elif [ -f "venv/Scripts/activate" ]; then
    VENV_ACTIVATE="venv/Scripts/activate"
else
    print_error "Virtual environment not found!"
    echo "Please run ./install_storymuse.sh first."
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# Activate virtual environment and launch
source "$VENV_ACTIVATE"
export PYTHONIOENCODING=utf-8
python -m storymuse.main start

# Handle errors
if [ $? -ne 0 ]; then
    echo ""
    print_error "Application exited with an error"
    echo ""
    read -p "Press Enter to exit..."
fi
