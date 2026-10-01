# Installation & Running Checklist

Complete this checklist to set up and run the Railway Resilience Framework.

---

## 📥 Prerequisites Check

- [ ] **Python 3.9+** installed
  - Test: `python --version` (should show 3.9 or higher)
  - If missing: https://www.python.org/downloads/

- [ ] **Node.js 18+** installed
  - Test: `node --version` (should show v18 or higher)
  - Test: `npm --version` (should show 9 or higher)
  - If missing: https://nodejs.org/

- [ ] **Git** installed (if cloning the repo)
  - Test: `git --version`

---

## 🧹 Cleanup (Optional but Recommended)

Remove old Streamlit files:

**Option A - PowerShell (Recommended for Windows):**

```bash
.\cleanup.ps1
```

**Option B - Command Prompt (Windows):**

```bash
cleanup.bat
```

**Option C - Manual Removal (All platforms):**

```bash
# Run from project root
rm -r frontend                    # Old Streamlit app
rm -r .streamlit                  # Streamlit config
rm -r .pytest_cache               # Test cache
rm -r __pycache__                 # Python cache
```

---

## 📦 Installation (Must Do)

### Step 1️⃣: Install Backend Dependencies

```bash
# Run from project root
pip install -r requirements.txt
```

**Expected:**

- Takes 2-3 minutes
- No errors at the end
- If error occurs: Check Python version with `python --version`

**Packages installed:**

- FastAPI & Uvicorn (backend framework)
- Mesa, SimPy, NetworkX (simulation)
- NumPy, SciPy, Pandas (data processing)
- PyDantic (validation)
- Google GenAI (optional NLP)
- And more...

**Verification:**

```bash
pip list | findstr fastapi
# Should output: fastapi 0.115.0
```

### Step 2️⃣: Install Frontend Dependencies

```bash
# Run from project root
cd frontend-react
npm install
cd ..
```

**Expected:**

- Takes 3-5 minutes
- No errors at the end (warnings about peer dependencies are OK)

**Packages installed:**

- React 18
- TypeScript
- Vite (dev server)
- deck.gl (map library)
- CSS modules

**Verification:**

```bash
cd frontend-react && npm list --depth=0 && cd ..
# Should list React, Vite, deck.gl, etc.
```

---

## ✅ Verification After Installation

Before running, verify everything is installed:

```bash
# Check Python packages
python -c "import fastapi; import uvicorn; print('✓ Backend packages OK')"

# Check Node packages
cd frontend-react && npm list react vite @deck.gl/react && cd ..
```

Both should complete without errors ✓

---

## 🚀 Running the Application

### Method 1: Two Terminals (Easiest)

**Terminal 1 - Backend:**

```bash
python -m backend.main
```

Wait for message:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

**Terminal 2 - Frontend (new terminal/tab):**

```bash
cd frontend-react
npm run dev
```

Wait for message:

```
  ➜  Local:   http://localhost:5173/
```

**Then:** Open browser to `http://localhost:5173`

---

### Method 2: Single PowerShell Command

```powershell
# Start backend in background, frontend in current terminal
$backend = Start-Process python -ArgumentList "-m backend.main" -PassThru
Start-Sleep -Seconds 3
cd frontend-react
npm run dev
```

When done, stop backend:

```powershell
Stop-Process -Id $backend.Id
```

---

### Method 3: Production Mode (Advanced)

See [DEVELOPMENT.md](DEVELOPMENT.md) → "Deployment" section

---

## 🎯 Verification After Starting

Once both servers are running, verify functionality:

- [ ] **Backend**
  - Test: http://localhost:8000/api/health
  - Expected: `{"status":"ok"}`

- [ ] **Frontend loads**
  - URL: http://localhost:5173
  - Expected: Map appears with trains/stations

- [ ] **Map functionality**
  - [ ] Tracks visible (gray lines)
  - [ ] Stations visible (light blue dots)
  - [ ] Trains visible (blue and orange dots)
  - [ ] Zoom/pan works

- [ ] **Simulation controls**
  - [ ] Click **Step** → Tick number increases
  - [ ] Click **Run** → Trains start moving
  - [ ] Trains animate smoothly (60fps)
  - [ ] Click **Pause** → Trains stop
  - [ ] Slider 50-500ms range works

- [ ] **Infrastructure controls**
  - [ ] Sidebar has 4 sections (Disruption, Towers, Switches, Status)
  - [ ] Can select and control items
  - [ ] Status updates appear immediately

- [ ] **Scenario prompt**
  - [ ] Text input works
  - [ ] "Run Scenario" button responds
  - [ ] No console errors

If all checks pass ✅ - You're ready to use the application!

---

## 🔧 Configuration

### Backend Port (Default: 8000)

To use a different port, edit `backend/main.py`:

```python
# Find this line:
uvicorn.run(app, host="127.0.0.1", port=8000)  # Change 8000 here

# Restart backend after change
```

### Frontend Dev Server Port (Default: 5173)

To use a different port, edit `frontend-react/vite.config.ts`:

```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173, // Change this number
  },
});
```

### Backend URL in Frontend

If backend not on localhost:8000, edit `src/App.tsx`:

```typescript
// Find this line:
const API_BASE = "http://localhost:8000"; // Change this

// Restart frontend dev server
```

---

## 🐛 Troubleshooting

### Backend Issues

**"ModuleNotFoundError: No module named 'fastapi'"**

- Solution: Run `pip install -r requirements.txt`

**"Address already in use" (port 8000)**

- Solution: Change port in `backend/main.py` or kill existing process:
  ```bash
  # Find and kill process on port 8000
  netstat -ano | findstr :8000
  taskkill /PID <PID> /F
  ```

**"Connection refused" from frontend**

- Solution:
  - Make sure backend is running
  - Check backend URL in frontend code
  - Check firewall not blocking port 8000

### Frontend Issues

**"Module not found: react"**

- Solution: Run `cd frontend-react && npm install && cd ..`

**"Port 5173 already in use"**

- Solution: Change port in `vite.config.ts` or kill existing process:
  ```bash
  netstat -ano | findstr :5173
  taskkill /PID <PID> /F
  ```

**"Cannot GET /api/infrastructure"**

- Solution: Backend not running or not accessible

**Animation is jerky/jumpy**

- Solution:
  - Refresh browser (F5)
  - Restart frontend: Ctrl+C then `npm run dev`
  - Check backend is responding (test port 8000)

### Python Version Issues

**"Python 3.9+ required"**

- Current version: `python --version`
- Solution: Upgrade Python from https://www.python.org/downloads/

**"pip: command not found"**

- Solution: `python -m pip install -r requirements.txt`

### Node/npm Issues

**"npm: command not found"**

- Solution: Reinstall Node.js from https://nodejs.org/

**"gyp ERR! build error" during npm install**

- Solution (Windows): Install Visual C++ Build Tools
- Solution (macOS): Install Xcode Command Line Tools: `xcode-select --install`

---

## 📋 Package Summary

### Required Python Packages (pip install -r requirements.txt)

| Package  | Version | Purpose                   |
| -------- | ------- | ------------------------- |
| fastapi  | 0.115.0 | Web framework             |
| uvicorn  | 0.30.0  | ASGI server               |
| mesa     | 3.5.1   | Agent-based simulation    |
| simpy    | 4.1.2   | Discrete event simulation |
| networkx | 3.6.1   | Graph algorithms          |
| numpy    | 2.4.6   | Numerical computing       |
| scipy    | 1.17.1  | Scientific computing      |
| pandas   | 3.0.3   | Data processing           |
| pydantic | 2.13.4  | Data validation           |

### Required Node Packages (npm install in frontend-react/)

| Package         | Version | Purpose           |
| --------------- | ------- | ----------------- |
| react           | 18.3.1  | UI framework      |
| typescript      | 5.3.3   | Type checking     |
| vite            | 5.1.0   | Build tool        |
| @deck.gl/react  | 9.1.1   | Map visualization |
| @deck.gl/layers | 9.1.1   | Map layers        |

### Optional Packages

| Package           | Purpose                    |
| ----------------- | -------------------------- |
| google-genai      | AI prompt processing (NLP) |
| scikit-learn      | Machine learning           |
| matplotlib/plotly | Data visualization         |
| pyvis             | Network visualization      |

---

## 📊 Expected Disk Usage After Setup

```
Frontend node_modules/    ~500 MB
Python venv/             ~1-2 GB (if using virtual env)
Total project            ~2-3 GB
```

---

## ✨ You're Done!

Once all checks pass, you can:

1. ✅ Run simulations with the UI
2. ✅ Test infrastructure controls
3. ✅ Modify code and it updates automatically
4. ✅ Deploy to production (see DEVELOPMENT.md)
5. ✅ Extend with new features

---

## 📖 Next Steps

- **Quick Reference:** [QUICKSTART.md](QUICKSTART.md)
- **Development Guide:** [DEVELOPMENT.md](DEVELOPMENT.md)
- **Architecture Details:** [MIGRATION.md](MIGRATION.md)
- **Full Implementation:** [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

---

## ❓ Still Need Help?

1. Check the documentation files listed above
2. Search for your error message in troubleshooting section
3. Run `python -m backend.main --help` for backend options
4. Check frontend-react/README.md for frontend-specific help
