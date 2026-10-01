# Railway Resilience Framework - Modern Frontend

This directory contains the React + TypeScript + deck.gl replacement for the Streamlit dashboard.

## Quick Start

### Prerequisites

- Python 3.9+ (for backend)
- Node.js 18+ (for frontend)

### Backend Setup

1. **Install Python dependencies** (in repo root):

   ```bash
   pip install -r requirements.txt
   ```

2. **Run the FastAPI server** (from repo root):

   ```bash
   python -m backend.main
   ```

   The API will be available at `http://localhost:8000`
   - REST API: `http://localhost:8000/api/*`
   - WebSocket: `ws://localhost:8000/ws/ticks`
   - API docs: `http://localhost:8000/docs`

### Frontend Setup

1. **Install Node dependencies** (in `frontend-react/`):

   ```bash
   npm install
   ```

2. **Start dev server** (in `frontend-react/`):

   ```bash
   npm run dev
   ```

   The frontend will be available at `http://localhost:5173`

3. **Build for production** (in `frontend-react/`):
   ```bash
   npm run build
   ```

## Architecture

### Backend (FastAPI)

**Key Files:**

- `backend/main.py` - FastAPI application with REST endpoints and WebSocket
- `backend/state.py` - Global state management with thread-safe RailwayModel
- `backend/positioning.py` - Geometry calculations (ported from Streamlit)

**Features:**

- REST endpoints for simulation control (step, run, pause, reset)
- Scenario prompt processing via `/api/scenario`
- Infrastructure control (switches, towers, edges, dispatch holds)
- WebSocket `/ws/ticks` for real-time updates
- Background tick loop for continuous simulation

**Data Flow:**

1. Client fetches static infrastructure data via `GET /api/infrastructure` on load
2. Client connects WebSocket and waits for tick messages
3. Control endpoints (buttons) trigger model mutations
4. Model.step() is called, positions computed via positioning engine
5. Tick snapshot broadcasted to all connected WebSocket clients
6. Status updates broadcasted on infrastructure changes

### Frontend (React + Vite)

**Key Files:**

- `src/App.tsx` - Main component with state, WebSocket, animation loop
- `src/types.ts` - TypeScript interfaces
- `src/components/MapView.tsx` - deck.gl visualization layers
- `src/components/ControlBar.tsx` - Simulation controls
- `src/components/Sidebar.tsx` - Infrastructure control panel
- `src/components/Legend.tsx` - Visual legend
- `src/components/PromptBar.tsx` - Scenario input

**Key Features:**

- **Client-side interpolation**: Smooth train animation between server ticks
  - Uses `requestAnimationFrame` for smooth 60fps rendering
  - Interpolates positions using linear interpolation (lerp)
  - Independent of server tick rate (works smoothly even at 1000ms+ intervals)

- **Deck.GL Layers**:
  - PathLayer: Track visualization
  - ScatterplotLayer: Stations (light blue)
  - ScatterplotLayer: Trains (blue=passenger, orange=freight)
  - HeatmapLayer: Radio tower coverage (blue→red gradient)

- **Real-time Updates**:
  - WebSocket receives tick messages with train positions (already computed server-side)
  - Status messages update infrastructure control state
  - All updates broadcast to connected clients immediately

- **Infrastructure Control**:
  - Switches: fail/repair/clamp individually or "all at station"
  - Towers: fail/repair
  - Edges: unblock
  - Dispatch holds: clear

## Visual Parameters (Exact Parity)

All parameters match the existing pydeck implementation:

**Train Visualization:**

- Passenger: RGB(59, 130, 246), radius 750m
- Freight: RGB(245, 158, 11), radius 900m
- Outline: RGB(255, 255, 255), width 1.5px, minPixels 7

**Track Visualization:**

- Color: RGB(71, 85, 105)
- Width scale: 15, minPixels: 3

**Station Visualization:**

- Color: RGB(186, 230, 253)
- Radius: 400m, minPixels: 4

**Heatmap:**

- Radius: 70px
- Intensity: 1.0
- Threshold: 0.02
- Aggregation: MAX
- Color range: Blue → Cyan → Green → Yellow → Red

**Initial View:**

- Latitude: 61.4978
- Longitude: 22.8000
- Zoom: 8.2
- Pitch: 0

## Animation Algorithm

The frontend implements smooth interpolation without recomputing geometry:

```
1. Receive previous tick: prev, at time prevReceivedAt
2. Receive current tick: curr, at time currReceivedAt
3. In requestAnimationFrame(now):
   - Calculate t = (now - prevReceivedAt) / (currReceivedAt - prevReceivedAt)
   - Clamp t to [0, 1]
   - For each train in curr:
     - Find same train in prev
     - Interpolate position: lerp(prev.pos, curr.pos, t)
   - Render with interpolated positions
4. Repeat for every animation frame (~60fps)
```

This produces smooth motion even when:

- Server tick interval is slow (e.g., 1000ms)
- Server tick interval is faster than 60fps (e.g., 100ms)
- Trains spawn/terminate between ticks

## API Endpoints

See `backend/main.py` for full documentation. Key endpoints:

**Infrastructure:**

- `GET /api/infrastructure` - Static tracks, stations, towers
- `GET /api/status` - Current infrastructure state

**Simulation Control:**

- `POST /api/step` - Execute one step
- `POST /api/run` - Start background loop
- `POST /api/pause` - Stop background loop
- `POST /api/reset` - Reset to seed

**Scenario:**

- `POST /api/scenario` - Apply prompt-based disruptions

**Infrastructure Control:**

- `POST /api/switches/{fail,repair,clamp,release-clamp}`
- `POST /api/towers/{fail,repair}`
- `POST /api/edges/unblock`
- `POST /api/dispatch-holds/clear`

**Real-time:**

- `WebSocket /ws/ticks` - Tick and status updates

## Simulation State

The backend holds a single global `RailwayModel` instance in `app_state.model`.
All access is protected by `asyncio.Lock` to prevent race conditions between:

- Background tick loop
- REST endpoints (control mutations)
- WebSocket broadcast

## Development Notes

### Adding New Layers to MapView

Edit `src/components/MapView.tsx` in the `useMemo(() => { ... }, [])` block:

```typescript
layersArray.push(
  new CustomLayer({
    id: "my-layer",
    data: myData,
    // ... deck.gl layer props
  }),
);
```

### Modifying Control Logic

Edit `src/App.tsx`:

- Add API call in `handleSomething` callback
- Use `apiCall()` helper to POST to backend
- State updates come via WebSocket broadcasts

### Styling

All components use CSS modules (`.css` files colocated with components).
Global styles in `src/index.css`.
Color scheme is dark (background #1a1a1a, accent #0ea5e9).

## Testing

**Manual Testing:**

1. Start backend: `python -m backend.main`
2. Start frontend: `npm run dev`
3. Navigate to `http://localhost:5173`
4. Verify:
   - Map loads with tracks, stations, heatmaps
   - Trains visible and animating smoothly
   - Control buttons work (Step, Run, Pause, Reset)
   - Scenario prompt works
   - Infrastructure controls work

**Acceptance Criteria:**

- [ ] Trains interpolate smoothly at stable frame rate
- [ ] All sidebar controls functional (switches, towers, edges, holds)
- [ ] Scenario prompt processes correctly
- [ ] Reset produces consistent starting state
- [ ] Visual parity: colors, radii, legend match exactly

## Troubleshooting

**WebSocket Connection Failed:**

- Ensure backend is running on `localhost:8000`
- Check browser console for connection errors
- Backend logs will show `Client connected` message

**No Trains Visible:**

- Check backend `/api/status` - trains might be terminated
- Verify positioning engine loaded nodes_and_edges.json correctly
- Check browser console for rendering errors

**Trains Not Animating:**

- Verify tick messages coming via WebSocket (check Network tab)
- Check that `currReceivedAt > prevReceivedAt` in animation loop
- Ensure `requestAnimationFrame` is firing (60fps)

## Known Limitations

- Mapbox basemap tile layer not implemented (plain dark background)
- No 3D terrain visualization
- Single WebSocket per client (no multi-tab support)

## Future Enhancements

- Add optional MapLibre GL basemap
- Implement 3D visualization with Cesium
- Add train telemetry time-series graphs
- Multi-tab WebSocket synchronization
- Replay/scrubbing through past ticks
- Performance metrics dashboard
