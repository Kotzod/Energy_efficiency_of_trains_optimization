# Development & Deployment Guide

## Development Setup

This guide covers running both the backend and frontend during development.

### One-Terminal Setup (Recommended)

Create a simple development script to run both services:

**Windows (create `run-dev.ps1`):**

```powershell
# Start backend in background
$backendProcess = Start-Process python -ArgumentList "-m backend.main" -NoNewWindow -PassThru

# Wait for backend to start
Start-Sleep -Seconds 2

# Start frontend
cd frontend-react
npm run dev

# Cleanup: Kill backend when frontend is stopped
Stop-Process -Id $backendProcess.Id
```

**Unix/Mac (create `run-dev.sh`):**

```bash
#!/bin/bash

# Start backend in background
python -m backend.main &
BACKEND_PID=$!

# Wait for backend to start
sleep 2

# Start frontend
cd frontend-react
npm run dev

# Cleanup
kill $BACKEND_PID
```

### Two-Terminal Setup

**Terminal 1: Backend**

```bash
python -m backend.main
```

**Terminal 2: Frontend**

```bash
cd frontend-react
npm install  # only needed first time
npm run dev
```

Then open `http://localhost:5173` in your browser.

## Development Workflow

### 1. Making Backend Changes

**Adding a new endpoint:**

1. Add request/response model to `backend/main.py`
2. Add endpoint function with `@app.post()` decorator
3. Use `app_state.lock` for model access
4. Broadcast updates via `broadcast_to_clients()`

**Example:**

```python
@app.post("/api/my-endpoint")
async def my_endpoint(request: MyRequest):
    await app_state.some_mutation()

    # Broadcast updated status
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}
```

**Backend reload:** Backend doesn't auto-reload. Restart `python -m backend.main` after changes.

### 2. Making Frontend Changes

**Adding a new component:**

1. Create `src/components/MyComponent.tsx`
2. Create `src/components/MyComponent.css`
3. Import and use in `src/App.tsx`

**Adding a new API endpoint call:**

1. Add function in `App.tsx` like `handleMyAction`
2. Use `apiCall('POST', '/api/my-endpoint', body)`
3. Update state based on response or WebSocket message

**Frontend auto-reload:** Vite automatically reloads on file changes.

### 3. Debugging WebSocket Messages

Add this to browser console to see all WebSocket messages:

```javascript
// In App.tsx, add to ws.onmessage:
const message = JSON.parse(event.data);
console.log("WS Message:", message);
```

Or use browser DevTools Network tab to inspect WebSocket frames.

### 4. Testing Control Logic

**Scenario 1: Verify train animation smoothness**

1. Set speed slider to 1000ms (1 second per tick)
2. Click "Run"
3. Observe trains moving smoothly (not jumping)

**Scenario 2: Verify infrastructure control**

1. In Sidebar, select a station and switch
2. Click "Fail"
3. Verify switch status changes to "Failed" immediately
4. Verify status broadcast received (check console)

**Scenario 3: Verify scenario prompt**

1. Enter a prompt like "fail all switches at TPE"
2. Click "Run Scenario"
3. Verify config JSON returned and model resets

## Production Build

### Backend

**Install production dependencies:**

```bash
pip install -r requirements.txt
```

**Run with production ASGI server:**

```bash
# Using Uvicorn (included in requirements)
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Or with Gunicorn for better performance
pip install gunicorn
gunicorn backend.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker
```

### Frontend

**Build:**

```bash
cd frontend-react
npm run build
```

This creates `frontend-react/dist/` with optimized static files.

**Serve:**

```bash
# Using Python's built-in server
cd dist
python -m http.server 8080

# Or use a web server (nginx, Apache, etc.)
# Point to dist/ directory
```

**Or integrate with backend:**

```python
# In backend/main.py, add static file serving
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory="frontend-react/dist", html=True), name="frontend")
```

## Environment Configuration

### Backend

**To change port:**

```python
# In backend/main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)  # Change port here
```

**To change CORS origins:**

```python
# In backend/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mydomain.com"],  # Restrict origins
    ...
)
```

### Frontend

**To use different backend URL:**
Create `frontend-react/.env.local`:

```
VITE_API_BASE=https://api.mydomain.com
VITE_WS_BASE=wss://api.mydomain.com
```

Then update `src/App.tsx`:

```typescript
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const WS_BASE = import.meta.env.VITE_WS_BASE || "ws://localhost:8000";
```

## Docker Deployment

### Dockerfile (Backend + Frontend)

```dockerfile
FROM node:18 AS frontend-build
WORKDIR /app
COPY frontend-react/package*.json ./
RUN npm install
COPY frontend-react/src ./src
COPY frontend-react/index.html tsconfig.json vite.config.ts ./
RUN npm run build

FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-build /app/dist ./frontend-react/dist

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml (Backend only)

```yaml
version: "3.8"
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PYTHONUNBUFFERED=1
    volumes:
      - ./infrastructure:/app/infrastructure
      - ./agents:/app/agents
```

## Troubleshooting

### Backend won't start

- Check Python version: `python --version` (need 3.9+)
- Check dependencies: `pip install -r requirements.txt`
- Check for port conflicts: `netstat -an | grep 8000`

### Frontend connection refused

- Verify backend is running: `curl http://localhost:8000/api/health`
- Check CORS headers: Look at Network tab in DevTools
- Check WebSocket: Should see "WS connected" in console

### Trains not rendering

- Check `/api/infrastructure` response in Network tab
- Verify node_coords populated correctly
- Check deck.gl canvas in DevTools

### Slow animation

- Check if animation loop running: `requestAnimationFrame` should fire ~60/sec
- Reduce number of trains with debug logging
- Profile frontend with Chrome DevTools Performance tab

## Performance Tuning

### Backend

- **Increase tick speed**: Server bottleneck usually positioning math
- **Batch operations**: Group multiple mutations before step
- **Use PyPy**: 3-4x faster than CPython

### Frontend

- **Reduce layer complexity**: Fewer heatmap points = faster rendering
- **WebGL layer instancing**: Use instanced rendering for many objects
- **Decrease canvas resolution**: Add `devicePixelRatio` scaling

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: 3.11

      - name: Install backend dependencies
        run: pip install -r requirements.txt

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: 18

      - name: Install frontend dependencies
        run: cd frontend-react && npm install

      - name: Build frontend
        run: cd frontend-react && npm run build

      - name: Check Python syntax
        run: python -m py_compile backend/*.py
```
