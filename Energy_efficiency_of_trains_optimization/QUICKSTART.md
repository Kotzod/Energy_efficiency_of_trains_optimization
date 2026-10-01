# Quick Start Guide - Railway Resilience Framework

Get up and running in 5 minutes.

## Prerequisites

- **Python 3.9+**: [Download](https://www.python.org/downloads/)
- **Node.js 18+**: [Download](https://nodejs.org/)
- **Git** (to clone the repo)

## Installation

### 1. Clone & Navigate

```bash
git clone <repo-url>
cd Energy_efficiency_of_trains_optimization
```

### 2. Install Backend Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Frontend Dependencies

```bash
cd frontend-react
npm install
cd ..
```

## Running

### Quickest Way (Single Command)

**Windows PowerShell:**

```powershell
$backend = Start-Process python -ArgumentList "-m backend.main" -PassThru -NoNewWindow
Start-Sleep -Seconds 2
cd frontend-react
npm run dev
Stop-Process -Id $backend.Id
```

**macOS/Linux:**

```bash
python -m backend.main &
cd frontend-react
npm run dev
```

### Step-by-Step (Two Terminals)

**Terminal 1: Start Backend**

```bash
python -m backend.main
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     App state initialized
```

**Terminal 2: Start Frontend**

```bash
cd frontend-react
npm run dev
```

You should see:

```
  VITE v5.x.x  ready in xxx ms
  ➜  Local:   http://localhost:5173/
```

### 3. Open in Browser

Navigate to `http://localhost:5173` and you should see the Railway Resilience Framework interface.

## First Steps

1. **Map should load** with tracks (gray lines), stations (light blue dots), and heatmap coverage (colored gradient)

2. **Try the controls:**
   - Click **"Step"** to advance one time step
   - Click **"Run"** to start continuous simulation
   - Adjust speed slider (50-500ms per tick)
   - Click **"Pause"** to stop

3. **Try infrastructure control:**
   - Open "Radio Towers" in sidebar
   - Select a tower
   - Click "Fail Tower" - watch status update

4. **Try scenario prompt:**
   - Scroll down to "Scenario Prompt"
   - Type: `fail all switches at TPE`
   - Click "Run Scenario"
   - Model resets with new configuration

5. **Watch train animation:**
   - With slow speed (e.g., 1000ms), trains should move smoothly
   - Not jumping between positions

## Troubleshooting

### "Connection refused" error

- Backend not running? Start it first (Terminal 1)
- Backend on different port? Update in `frontend-react/vite.config.ts`

### No trains visible

- Speed too fast? Trains might already be terminated
- Click "Reset" to start fresh

### Changes not appearing

- Frontend not auto-reloading? Save the file again
- Backend needs restart after code changes (Ctrl+C, run again)

### Port already in use

- Backend: `lsof -i :8000` (macOS/Linux) or find process on port 8000
- Frontend: `lsof -i :5173` (macOS/Linux) or find process on port 5173
- Kill and restart

## Key UI Elements

- **Map**: Main visualization (gray=tracks, light blue=stations, colored heatmap=radio coverage)
- **Control Bar**: Step/Run/Pause/Reset buttons, speed slider, tick counter
- **Sidebar**: Infrastructure control (switches, towers), disruption clearing, status
- **Legend**: Heatmap gradient, weather, train types
- **Prompt Bar**: Scenario input (at bottom)

## Common Tasks

### Simulate a Switch Failure

1. Sidebar → "Infrastructure Control" → "Switches"
2. Select a station (e.g., "TPE")
3. Select a switch or "All switches"
4. Click "Fail"

### Watch Trains Interpolate Smoothly

1. Speed slider → 1000ms (slow)
2. Click "Run"
3. Observe trains moving continuously (not stepping)

### Reset to Initial State

1. Click "Reset" button
2. Trains respawn, simulation resets to tick 0

### Try Complex Scenario

1. Scroll to "Scenario Prompt"
2. Example: `fail switch 0 at TPE and fail tower T2`
3. Click "Run Scenario"
4. Config appears, model applies changes

## Next Steps

- Read [DEVELOPMENT.md](./DEVELOPMENT.md) for architecture details
- Read [MIGRATION.md](./MIGRATION.md) to understand Streamlit → React changes
- Read [frontend-react/README.md](./frontend-react/README.md) for frontend specifics

## Performance Tips

- **Slow rendering?** Reduce heatmap size (edit `backend/positioning.py` HEATMAP_STEPS)
- **Slow computation?** Increase tick interval (slower = less computation)
- **Memory issue?** Run with PyPy: `pypy3 -m backend.main` (if PyPy installed)

## Common Errors

| Error                                            | Solution                                    |
| ------------------------------------------------ | ------------------------------------------- |
| `ModuleNotFoundError: No module named 'fastapi'` | Run `pip install -r requirements.txt`       |
| `EADDRINUSE: address already in use :::8000`     | Kill existing process on port 8000          |
| `Cannot find npm`                                | Install Node.js from nodejs.org             |
| `WebSocket connection failed`                    | Ensure backend is running on localhost:8000 |
| `Map appears black/empty`                        | Check browser console for deck.gl errors    |

## Getting Help

1. **Check console:** Open browser DevTools (F12) → Console tab
2. **Check backend logs:** Terminal should show request logs
3. **Check network:** DevTools → Network tab → click requests
4. **Check WebSocket:** DevTools → Network → look for "ws:..." entries

## Next: Customization

The app is fully customizable:

- **Colors**: Edit `src/components/MapView.tsx` (RGB values)
- **Controls**: Edit `src/components/ControlBar.tsx` / `Sidebar.tsx`
- **API**: Edit `backend/main.py` (add endpoints)
- **Simulation**: Edit `infrastructure/railway_graph.py` (no touch necessary per brief!)

---

**Questions?** Check the [README](./frontend-react/README.md) or [DEVELOPMENT.md](./DEVELOPMENT.md)
