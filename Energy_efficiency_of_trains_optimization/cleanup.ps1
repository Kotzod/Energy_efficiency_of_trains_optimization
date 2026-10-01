# Railway Resilience Framework - Cleanup Script
# Removes old Streamlit files and caches
# Run from project root directory

Write-Host 'Cleaning up old Streamlit files...' -ForegroundColor Cyan

# Track what we remove
$removed_count = 0

# Remove old frontend directory
if (Test-Path "frontend") {
    Write-Host "  Removing frontend/ ..." -ForegroundColor Gray
    Remove-Item -Path "frontend" -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path "frontend")) {
        Write-Host '  Removed frontend/' -ForegroundColor Green
        $removed_count++
    }
}

# Remove Streamlit config
if (Test-Path ".streamlit") {
    Write-Host "  Removing .streamlit/ ..." -ForegroundColor Gray
    Remove-Item -Path ".streamlit" -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path ".streamlit")) {
        Write-Host '  Removed .streamlit/' -ForegroundColor Green
        $removed_count++
    }
}

# Remove pytest cache
if (Test-Path ".pytest_cache") {
    Write-Host "  Removing .pytest_cache/ ..." -ForegroundColor Gray
    Remove-Item -Path ".pytest_cache" -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path ".pytest_cache")) {
        Write-Host '  Removed .pytest_cache/' -ForegroundColor Green
        $removed_count++
    }
}

# Clean Python cache files
if (Test-Path "__pycache__") {
    Write-Host "  Removing __pycache__/ ..." -ForegroundColor Gray
    Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host '  Removed __pycache__/' -ForegroundColor Green
    $removed_count++
}

Write-Host ""
Write-Host "Cleanup complete! ($removed_count items removed)" -ForegroundColor Green
Write-Host ""
Write-Host 'Next steps:' -ForegroundColor Cyan
Write-Host '  1. Install backend: pip install -r requirements.txt' -ForegroundColor White
Write-Host '  2. Install frontend: cd frontend-react; npm install; cd ..' -ForegroundColor White
Write-Host '  3. Start backend: python -m backend.main' -ForegroundColor White
Write-Host '  4. Start frontend: cd frontend-react; npm run dev' -ForegroundColor White
Write-Host '  5. Open: http://localhost:5173' -ForegroundColor White
