#!/bin/bash
set -e  # Exit on any error

 # Create bin directory if it doesn't exist
 mkdir -p bin

 # Activate virtual environment if it exists
if [ -d ".venv" ] || [ -d "venv" ]; then
    if [ -d ".venv" ]; then
        echo "Activating .venv virtual environment..."
         source .venv/bin/activate
    else
        echo "Activating venv virtual environment..."
        source venv/bin/activate
    fi
 fi

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "Warning: requirements.txt not found, skipping dependency installation"
else
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if PyInstaller is available
if ! command -v pyinstaller &> /dev/null; then
    echo "Installing PyInstaller..."
    pip install pyinstaller
fi

echo "Building executable..."
 # Build the executable directly to the bin directory
 pyinstaller --onefile --clean --distpath ./bin autoscaler.py

echo "Cleaning up build artifacts..."
 # Clean up build artifacts
 rm -rf build
 rm -f autoscaler.spec

 echo "Build complete! Executable is available in the bin directory."