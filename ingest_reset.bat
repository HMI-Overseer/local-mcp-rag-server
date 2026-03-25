@echo off
REM ============================================================================
REM Local Context RAG - Ingest Reset Script
REM ============================================================================
REM This script creates a virtual environment if needed and runs ingestion
REM with --reset to rebuild the index from scratch.
REM ============================================================================

echo.
echo ============================================================================
echo Local Context RAG - Ingest Reset
echo ============================================================================
echo.

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment found, using existing venv
    echo.
) else (
    echo [INFO] Virtual environment not found, creating new venv with Python 3.12
    echo.
    
    REM Create virtual environment with Python 3.12
    py -3.12 -m venv venv
    
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        echo [ERROR] Make sure Python 3.12 is installed
        echo [ERROR] You can check with: py --list
        echo.
        pause
        exit /b 1
    )
    
    echo [SUCCESS] Virtual environment created
    echo.
    echo [INFO] Installing dependencies...
    echo.
    
    REM Activate and install dependencies
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
    
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        echo.
        pause
        exit /b 1
    )
    
    echo.
    echo [SUCCESS] Dependencies installed
    echo.
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run ingestion with reset
echo [INFO] Starting ingestion with --reset flag
echo [INFO] This will rebuild the entire index from scratch
echo.
python ingest.py --reset

REM Check if ingestion was successful
if errorlevel 1 (
    echo.
    echo [ERROR] Ingestion failed
    echo.
) else (
    echo.
    echo [SUCCESS] Ingestion completed successfully
    echo.
)

REM Keep window open
pause