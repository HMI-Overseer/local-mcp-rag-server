#!/bin/bash
# ============================================================================
# Local Context RAG - Ingest Reset Script (macOS/Linux)
# ============================================================================
# This script creates a virtual environment if needed and runs ingestion
# with --reset to rebuild the index from scratch.
# ============================================================================

echo ""
echo "============================================================================"
echo "Local Context RAG - Ingest Reset"
echo "============================================================================"
echo ""

# Check if virtual environment exists
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    echo "[INFO] Virtual environment found, using existing venv"
    echo ""
else
    echo "[INFO] Virtual environment not found, creating new venv with Python 3.12"
    echo ""
    
    # Create virtual environment with Python 3.12
    if command -v python3.12 &> /dev/null; then
        python3.12 -m venv venv
    elif command -v python3 &> /dev/null; then
        echo "[WARNING] python3.12 not found, trying python3"
        python3 -m venv venv
    else
        echo "[ERROR] Python 3.12+ not found"
        echo "[ERROR] Please install Python 3.12 or higher"
        exit 1
    fi
    
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment"
        echo "[ERROR] Make sure Python 3.12+ is installed"
        exit 1
    fi
    
    echo "[SUCCESS] Virtual environment created"
    echo ""
    echo "[INFO] Installing dependencies..."
    echo ""
    
    # Activate and install dependencies
    source venv/bin/activate
    pip install -r requirements.txt
    
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install dependencies"
        exit 1
    fi
    
    echo ""
    echo "[SUCCESS] Dependencies installed"
    echo ""
fi

# Activate virtual environment
source venv/bin/activate

# Run ingestion with reset
echo "[INFO] Starting ingestion with --reset flag"
echo "[INFO] This will rebuild the entire index from scratch"
echo ""
python ingest.py --reset

# Check if ingestion was successful
if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Ingestion failed"
    echo ""
    exit 1
else
    echo ""
    echo "[SUCCESS] Ingestion completed successfully"
    echo ""
fi