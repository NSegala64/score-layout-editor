#!/bin/bash
cd "$(dirname "$0")"

echo "Setting up Sheet Music Editor..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 is not installed."
    echo "Please install Python from python.org."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate and run
source venv/bin/activate
echo "Installing dependencies..."
pip install -r requirements.txt -q
echo "Launching Editor..."
python main_gui.py