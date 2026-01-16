#!/bin/bash
# Zphisher Web Launcher

# Ensure running in script directory
cd "$(dirname "$0")"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found!"
    echo "Please run ./installer.sh first."
    exit 1
fi

# Activate and Run
source venv/bin/activate
echo "Starting Zphisher Web UI..."
echo "Open http://127.0.0.1:8000 in your browser"
echo "Press Ctrl+C to stop"
echo ""

python3 web_app.py
