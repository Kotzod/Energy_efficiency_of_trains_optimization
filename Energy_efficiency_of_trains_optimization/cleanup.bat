@echo off
REM Railway Resilience Framework - Cleanup Script (Batch version)
REM Removes old Streamlit files and caches
REM Run from project root directory

echo.
echo ========================================
echo   Railway Resilience Framework Cleanup
echo ========================================
echo.

set removed=0

REM Remove old frontend directory
if exist frontend (
    echo Removing frontend directory...
    rmdir /s /q frontend >nul 2>&1
    echo.✓ Removed frontend/
    set /a removed=%removed%+1
)

REM Remove Streamlit config
if exist .streamlit (
    echo Removing .streamlit directory...
    rmdir /s /q .streamlit >nul 2>&1
    echo ✓ Removed .streamlit/
    set /a removed=%removed%+1
)

REM Remove pytest cache
if exist .pytest_cache (
    echo Removing .pytest_cache directory...
    rmdir /s /q .pytest_cache >nul 2>&1
    echo ✓ Removed .pytest_cache/
    set /a removed=%removed%+1
)

REM Clean Python cache
if exist __pycache__ (
    echo Removing __pycache__ directory...
    rmdir /s /q __pycache__ >nul 2>&1
    echo ✓ Removed __pycache__/
    set /a removed=%removed%+1
)

echo.
echo ========================================
echo   Cleanup complete! (%removed% items removed)
echo ========================================
echo.
echo NEXT STEPS:
echo -----------
echo 1. Install backend packages:
echo    pip install -r requirements.txt
echo.
echo 2. Install frontend packages:
echo    cd frontend-react ^&^& npm install ^&^& cd ..
echo.
echo 3. Start backend (Terminal 1):
echo    python -m backend.main
echo.
echo 4. Start frontend (Terminal 2):
echo    cd frontend-react ^&^& npm run dev
echo.
echo 5. Open browser: http://localhost:5173
echo.
pause
