#!/bin/bash
# StoryMuse Launcher for Linux/macOS
# This script checks prerequisites and launches the application

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

print_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check if Python is installed
echo "[1/5] Checking for Python installation..."
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        print_error "Python is not installed or not in PATH!"
        echo "Please install Python 3.10 or higher:"
        echo "  - Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
        echo "  - Fedora: sudo dnf install python3 python3-pip"
        echo "  - macOS: brew install python@3.10"
        exit 1
    else
        PYTHON_CMD="python"
    fi
else
    PYTHON_CMD="python3"
fi

# Check Python version
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "Found Python $PYTHON_VERSION"

# Extract major and minor version
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    print_error "Python 3.10 or higher is required!"
    echo "Current version: $PYTHON_VERSION"
    exit 1
fi
print_ok "Python version is compatible"
echo ""

# Check if virtual environment exists
echo "[2/5] Checking for virtual environment..."
if [ -f "venv/bin/activate" ]; then
    VENV_ACTIVATE="venv/bin/activate"
    print_ok "Virtual environment exists"
elif [ -f "venv/Scripts/activate" ]; then
    VENV_ACTIVATE="venv/Scripts/activate"
    print_ok "Virtual environment exists"
else
    print_info "Virtual environment not found. Creating one..."
    $PYTHON_CMD -m venv venv
    if [ $? -ne 0 ]; then
        print_error "Failed to create virtual environment!"
        echo "You may need to install python3-venv:"
        echo "  - Ubuntu/Debian: sudo apt install python3-venv"
        echo "  - Fedora: sudo dnf install python3-virtualenv"
        exit 1
    fi
    print_ok "Virtual environment created"
    # Set the activate path after creation
    if [ -f "venv/bin/activate" ]; then
        VENV_ACTIVATE="venv/bin/activate"
    else
        VENV_ACTIVATE="venv/Scripts/activate"
    fi
fi
echo ""

# Activate virtual environment
echo "[3/5] Activating virtual environment..."
source "$VENV_ACTIVATE"
if [ $? -ne 0 ]; then
    print_error "Failed to activate virtual environment!"
    exit 1
fi
print_ok "Virtual environment activated"
echo ""

# Check if dependencies are installed
echo "[4/5] Checking dependencies..."
python -c "import typer, rich, openai, instructor, pydantic, dotenv" 2>/dev/null
if [ $? -ne 0 ]; then
    print_info "Dependencies not found or incomplete. Installing from requirements.txt..."
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found!"
        exit 1
    fi
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        print_error "Failed to install dependencies!"
        exit 1
    fi
    print_ok "Dependencies installed successfully"
else
    print_ok "All dependencies are installed"
fi
echo ""

# Check if .env file exists
echo "[5/5] Checking configuration..."
if [ ! -f ".env" ]; then
    print_warning ".env configuration file not found!"
    if [ -f ".env.example" ]; then
        print_info "Copying .env.example to .env..."
        cp .env.example .env
        echo ""
        print_warning "ACTION REQUIRED: Please edit .env file with your LLM server settings:"
        echo "  - LLM_BASE_URL (e.g., http://localhost:1337/v1 for Jan)"
        echo "  - LLM_MODEL (e.g., deepseek-r1-distill-qwen-7b)"
        echo ""

        # Try to open in default editor
        if command -v nano &> /dev/null; then
            read -p "Press Enter to open .env in nano editor..."
            nano .env
        elif command -v vim &> /dev/null; then
            read -p "Press Enter to open .env in vim editor..."
            vim .env
        elif command -v vi &> /dev/null; then
            read -p "Press Enter to open .env in vi editor..."
            vi .env
        else
            print_warning "No text editor found. Please edit .env manually:"
            echo "  nano .env  OR  vim .env  OR  vi .env"
            read -p "Press Enter after editing .env to continue..."
        fi
    else
        print_error ".env.example not found! Please create a .env file manually."
        echo "See README.md for configuration examples."
        exit 1
    fi
else
    print_ok "Configuration file exists"
fi
echo ""

echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "StoryMuse is now ready to use."
echo ""
echo "To launch StoryMuse, run:"
echo "  ./launch_storymuse.sh"
echo ""
echo "Or manually:"
echo "  source venv/bin/activate"
echo "  python -m storymuse.main start"
echo ""
read -p "Press Enter to exit..."
