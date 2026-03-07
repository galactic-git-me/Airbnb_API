#!/bin/bash

# Get the current directory name (project folder name)
PROJECT_NAME=$(basename "$PWD")

# Create a virtual environment inside the project folder with the same name as the current directory
python3 -m venv "$PROJECT_NAME"

# Activate the virtual environment
source "$PROJECT_NAME/bin/activate"

# Install dependencies from requirements.txt
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "requirements.txt not found!"
fi

# Run the main.py file
if [ -f "main.py" ]; then
    python main.py
else
    echo "main.py not found!"
fi
