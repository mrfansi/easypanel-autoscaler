#!/bin/bash

# Create bin directory if it doesn't exist
mkdir -p bin

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Install dependencies
pip install -r requirements.txt

# Build the executable directly to the bin directory
pyinstaller --onefile --clean --distpath ./bin autoscaler.py

# Clean up build artifacts
rm -rf build
rm -f autoscaler.spec

echo "Build complete! Executable is available in the bin directory."
