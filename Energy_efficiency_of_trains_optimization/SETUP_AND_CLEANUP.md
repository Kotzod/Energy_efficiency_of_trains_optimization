# Setup and Cleanup Guide

This guide shows you what to remove and how to properly set up the Railway Resilience Framework with the new FastAPI + React stack.

## 📁 Files & Folders to Remove

### The Old Streamlit Dashboard (Safe to Delete)

These files were part of the old Streamlit implementation and are no longer needed:

```bash
# Remove old Streamlit frontend
rmdir /s /q frontend\app                 # Old Streamlit app
rmdir /s /q frontend\nlp                 # Old NLP frontend
rmdir /s frontend                        # Entire old frontend

# Remove Streamlit config
rmdir /s /q .streamlit                   # Streamlit settings

# Remove Python cache
rmdir /s /q frontend\__pycache__         # Python bytecode cache
rmdir /s /q .pytest_cache                # Pytest cache

# Remove old experiment/analysis scripts (optional - keep if reference needed)
# rmdir /s /q experiments                 # Old experiment runners
# rmdir /s /q visualization               # Old visualization code
# rmdir /s /q analytics                   # Old analytics scripts
```

### Optional Cleanup (Non-Essential)

These are nice-to-have but not required:

- `.streamlit/` - Streamlit config (no longer used)
- `experiments/` - Old experiment runners (unless you need them for reference)
- `visualization/` - Old pydeck visualization code
- `analytics/` - Old analytics scripts

### DO NOT DELETE (Core Project Files)

Keep these - they're essential:

- ✅ `backend/` - NEW FastAPI backend
- ✅ `frontend-react/` - NEW React frontend
- ✅ `agents/` - Simulation agents (required)
- ✅ `infrastructure/` - Railway infrastructure data (required)
- ✅ `data/` - Data processing (required)
- ✅ `nlp/` - NLP prompt parser (required by backend)
- ✅ `requirements.txt` - Python dependencies
- ✅ `.gitignore` - Git ignore rules
- ✅ `pyproject.toml` - Project metadata
- ✅ `README.md` - Project overview
- ✅ Documentation files (QUICKSTART.md, DEVELOPMENT.md, etc.)

---

## 🧹 Automated Cleanup Script (Windows PowerShell)

Run this script to safely remove all old Streamlit files:

```powershell
# CD to project root first
cd c:\Users\choli\GitRepos\Energy_efficiency_of_trains_optimization

# Remove old frontend
if (Test-Path "frontend") {
    Remove-Item -Path "frontend" -Recurse -Force
    Write-Host "✓ Removed old frontend/ directory"
}

# Remove Streamlit config
if (Test-Path ".streamlit") {
    Remove-Item -Path ".streamlit" -Recurse -Force
    Write-Host "✓ Removed .streamlit/ directory"
}

# Remove cache directories
if (Test-Path ".pytest_cache") {
    Remove-Item -Path ".pytest_cache" -Recurse -Force
    Write-Host "✓ Removed .pytest_cache/ directory"
}

# Remove venv if using system Python (optional)
# if (Test-Path "venv") {
#     Remove-Item -Path "venv" -Recurse -Force
#     Write-Host "✓ Removed venv/ directory"
# }

Write-Host "Cleanup complete!"
```

---

## ⚙️ Installation & Setup

### Step 1: Prerequisites

Install these first (one-time setup):

**Python 3.9 or later:**

```bash
python --version          # Should show 3.9+
```

Get from: https://www.python.org/downloads/

**Node.js 18+ (for frontend):**

```bash
node --version            # Should show v18+
npm --version             # Should show 9+
```

Get from: https://nodejs.org/

### Step 2: Install Backend Dependencies

Run from project root:

```bash
pip install -r requirements.txt
```

**What gets installed:**

- `fastapi==0.115.0` - Web framework
- `uvicorn==0.30.0` - ASGI server
- Core simulation: mesa, simpy, networkx, numpy, scipy
- Data processing: pandas, pyyaml, orjson
- ML: scikit-learn, statsmodels
- Visualization: matplotlib, plotly, pyvis
- Validation: pydantic
- NLP: google-genai

**Installation time:** ~2-3 minutes

### Step 3: Install Frontend Dependencies

Run from project root:

```bash
cd frontend-react
npm install
cd ..
```

**What gets installed:**

- React 18
- TypeScript
- Vite (dev server)
- deck.gl (map visualization)
- CSS for styling

**Installation time:** ~3-5 minutes

---

## 🚀 Running the Application

### Quick Start (Recommended)

**Terminal 1 - Backend (Python):**

```bash
python -m backend.main
```

Expected output:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

**Terminal 2 - Frontend (Node.js):**

```bash
cd frontend-react
npm run dev
```

Expected output:

```
  VITE v5.1.0  ready in 500 ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

**Open browser:** http://localhost:5173

You should see:

- Map with railway tracks and stations
- Colored dots for trains (blue=passenger, orange=freight)
- Control panel on left
- Simulation controls at bottom

---

## 🔍 Verification Checklist

After starting both servers:

- [ ] Backend running on http://localhost:8000
- [ ] Frontend running on http://localhost:5173
- [ ] Map loads without errors
- [ ] Trains visible (colored dots)
- [ ] Click **Step** → tick increments
- [ ] Click **Run** → trains animate smoothly
- [ ] Click **Pause** → trains stop
- [ ] Sidebar controls work (try clicking a button)
- [ ] Speed slider works (50-500ms range)
- [ ] Scenario prompt accepts text

If all checks pass ✅ - you're ready to go!

---

## 📋 Packages to Install (Summary)

### Python Backend (`pip install -r requirements.txt`)

**Required for simulation:**

- mesa==3.5.1
- simpy==4.1.2
- networkx==3.6.1
- numpy==2.4.6
- scipy==1.17.1

**Required for backend:**

- fastapi==0.115.0
- uvicorn[standard]==0.30.0

**For data processing:**

- pandas==3.0.3
- pyyaml==6.0.3
- orjson==3.11.9
- pydantic==2.13.4

**Optional (analytics/visualization):**

- scikit-learn==1.8.0
- statsmodels==0.14.6
- matplotlib==3.10.9
- plotly==6.7.0
- pyvis>=0.3.2

**Optional (NLP/prompts):**

- google-genai==2.7.0

### JavaScript Frontend (`npm install` in frontend-react/)

Core dependencies already in `frontend-react/package.json`:

- react@18.3.1
- typescript@5.3.3
- vite@5.1.0
- @deck.gl/core@9.1.1
- @deck.gl/layers@9.1.1
- @deck.gl/react@9.1.1

---

## 🛠️ Common Issues & Solutions

### Issue: "python: command not found"

**Solution:** Python not in PATH. Either:

- Add Python to PATH during installation (check box in installer)
- Use full path: `C:\Python312\python.exe -m backend.main`
- Use python3: `python3 -m backend.main`

### Issue: "npm: command not found"

**Solution:** Node.js not in PATH. Reinstall from https://nodejs.org/

### Issue: "Port 8000/5173 already in use"

**Solution:** Kill the process using that port:

```bash
# For Windows (PowerShell):
netstat -ano | findstr :8000        # Find PID using port 8000
taskkill /PID <PID> /F              # Kill it

# Or just change the port in code and restart
```

### Issue: "Module not found: fastapi"

**Solution:** You missed Step 2. Run:

```bash
pip install -r requirements.txt
```

### Issue: "Cannot find module 'react'"

**Solution:** You missed Step 3. Run:

```bash
cd frontend-react && npm install && cd ..
```

### Issue: Animation is jerky/jumpy

**Solution:** This shouldn't happen. Try:

- Refresh browser (F5 or Cmd+R)
- Restart frontend dev server (Ctrl+C then `npm run dev`)
- Check backend is actually running (should see Uvicorn message)

---

## 📊 Project Structure After Setup

```
Energy_efficiency_of_trains_optimization/
├── backend/                          ← NEW: FastAPI backend
│   ├── __init__.py
│   ├── main.py                       ← Start backend from here
│   ├── state.py
│   └── positioning.py
├── frontend-react/                   ← NEW: React frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   └── App.tsx                   ← Main React component
│   └── node_modules/                 ← (auto-created by npm install)
├── agents/                           ← Simulation (unchanged)
├── infrastructure/                   ← Railway data (unchanged)
├── data/                             ← Data processing (unchanged)
├── nlp/                              ← NLP parsing (unchanged)
├── requirements.txt                  ← Python packages
├── QUICKSTART.md                     ← Quick reference
├── DEVELOPMENT.md                    ← Dev/deploy guide
└── README.md                         ← Project overview
```

---

## 🎓 Understanding the Architecture

**Backend (Python/FastAPI):**

- Runs on localhost:8000
- Handles simulation logic
- Provides REST API endpoints
- Broadcasts updates via WebSocket
- Loads railway infrastructure from JSON files

**Frontend (React/TypeScript):**

- Runs on localhost:5173
- Displays interactive map
- Handles user interactions
- Animates trains smoothly
- Connects to backend via WebSocket

**Data Flow:**

1. Frontend fetches infrastructure (GET /api/infrastructure)
2. Frontend opens WebSocket connection
3. Backend sends train positions every tick
4. Frontend interpolates between ticks for smooth animation
5. User clicks control → POST to backend → status broadcast → frontend updates

---

## 📝 Next Steps

1. **Run the application** following "Quick Start" section above
2. **Verify** using the verification checklist
3. **Explore** the UI:
   - Run simulation with different speeds
   - Test infrastructure controls
   - Try scenario prompts
4. **Read documentation:**
   - `QUICKSTART.md` - Quick reference
   - `DEVELOPMENT.md` - For modifications/deployment
   - `MIGRATION.md` - For understanding architecture

---

## ❓ Need Help?

- **Backend issues?** Check `DEVELOPMENT.md` → Backend Troubleshooting
- **Frontend issues?** Check `frontend-react/README.md` → Troubleshooting
- **Architecture questions?** Read `MIGRATION.md`
- **Full implementation details?** See `IMPLEMENTATION_SUMMARY.md`
