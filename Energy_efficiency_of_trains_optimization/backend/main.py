"""
FastAPI backend for Railway Resilience Framework.

Provides REST API and WebSocket for the frontend, replacing Streamlit dashboard.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Setup paths
APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (APP_DIR, REPO_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from backend.state import AppState

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# FastAPI app setup
app = FastAPI(title="Railway Resilience Framework API")

# CORS setup for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
app_state: AppState = None
# Track all connected WebSocket clients
connected_clients: List[WebSocket] = []
# Background tick loop task
tick_loop_task: Optional[asyncio.Task] = None
tick_interval_ms: int = 200


# Request/response models
class StepRequest(BaseModel):
    """No fields needed for step."""
    pass


class RunRequest(BaseModel):
    """Request to start background tick loop."""
    intervalMs: int


class ControllerRequest(BaseModel):
    mode: str


class ResetRequest(BaseModel):
    """Request to reset model to initial state."""
    seed: int = 67


class SwitchControlRequest(BaseModel):
    """Request to control switches."""
    stationId: str
    switchIndex: Optional[int] = None


class SwitchClampRequest(BaseModel):
    """Request to clamp a switch."""
    stationId: str
    switchIndex: Optional[int] = None
    position: str  # "normal" or "reverse"


class TowerControlRequest(BaseModel):
    """Request to control radio towers."""
    towerId: str


class EdgeControlRequest(BaseModel):
    """Request to control track edges."""
    edgeKey: str


class DispatchHoldRequest(BaseModel):
    """Request to clear a dispatch hold."""
    targetId: str


async def broadcast_to_clients(message: Dict[str, Any]):
    """Broadcast a message to all connected WebSocket clients."""
    disconnected = []
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception as e:
            logger.error(f"Error broadcasting to client: {e}")
            disconnected.append(client)

    # Remove disconnected clients
    for client in disconnected:
        try:
            connected_clients.remove(client)
        except ValueError:
            pass


async def run_tick_loop():
    """Background task that steps the model at regular intervals."""
    global tick_loop_task

    while app_state.running:
        try:
            await asyncio.sleep(tick_interval_ms / 1000.0)

            if not app_state.running:
                break

            # Step the model
            await app_state.step()

            # Broadcast tick snapshot
            tick_snapshot = await app_state.get_tick_snapshot()
            await broadcast_to_clients(tick_snapshot)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in tick loop: {e}")
            break

    app_state.running = False
    tick_loop_task = None


# REST API Endpoints

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/infrastructure")
async def get_infrastructure():
    """Get static infrastructure data (tracks, stations, towers with heatmaps)."""
    return await app_state.get_infrastructure()


@app.get("/api/status")
async def get_status():
    """Get current infrastructure control panel status."""
    return await app_state.get_status()


@app.post("/api/step")
async def step_simulation(request: StepRequest):
    """Execute one simulation step."""
    global tick_loop_task

    # Stop background loop if running
    if tick_loop_task and not tick_loop_task.done():
        app_state.running = False
        await asyncio.sleep(0.1)  # Give loop time to stop

    # Execute one step
    await app_state.step()

    # Broadcast new state
    tick_snapshot = await app_state.get_tick_snapshot()
    await broadcast_to_clients(tick_snapshot)

    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"tick": app_state.tick}


@app.post("/api/run")
async def run_simulation(request: RunRequest):
    """Start the background tick loop."""
    global tick_loop_task, tick_interval_ms

    tick_interval_ms = request.intervalMs

    if not app_state.running:
        app_state.running = True
        if not tick_loop_task or tick_loop_task.done():
            tick_loop_task = asyncio.create_task(run_tick_loop())

    return {"running": True, "intervalMs": tick_interval_ms}


@app.post("/api/pause")
async def pause_simulation():
    """Stop the background tick loop."""
    app_state.running = False
    return {"running": False}


@app.post("/api/controller")
async def set_controller(request: ControllerRequest):
    """Select the energy-aware driving controller."""
    if request.mode not in {"rule_based", "mpc", "ai"}:
        raise HTTPException(status_code=400, detail="mode must be rule_based, mpc, or ai")
    try:
        mode = await app_state.set_controller_mode(request.mode)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})
    return {"mode": mode}


@app.post("/api/reset")
async def reset_simulation(request: ResetRequest):
    """Reset model to initial state."""
    global tick_loop_task

    # Stop background loop
    if tick_loop_task and not tick_loop_task.done():
        app_state.running = False
        await asyncio.sleep(0.1)

    # Reset model
    await app_state.reset(seed=request.seed)

    # Broadcast new state
    tick_snapshot = await app_state.get_tick_snapshot()
    await broadcast_to_clients(tick_snapshot)

    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"tick": app_state.tick, "seed": request.seed}


@app.post("/api/switches/fail")
async def fail_switches(request: SwitchControlRequest):
    """Fail one or all switches at a station."""
    await app_state.fail_switch(request.stationId, request.switchIndex)

    # Broadcast status update
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}


@app.post("/api/switches/repair")
async def repair_switches(request: SwitchControlRequest):
    """Repair one or all switches at a station."""
    await app_state.repair_switch(request.stationId, request.switchIndex)

    # Broadcast status update
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}


@app.post("/api/switches/clamp")
async def clamp_switches(request: SwitchClampRequest):
    """Clamp one or all switches at a station."""
    await app_state.clamp_switch(request.stationId, request.switchIndex, request.position)

    # Broadcast status update
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}


@app.post("/api/switches/release-clamp")
async def release_switch_clamps(request: SwitchControlRequest):
    """Release clamp on one or all switches at a station."""
    await app_state.release_switch_clamp(request.stationId, request.switchIndex)

    # Broadcast status update
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}


@app.post("/api/towers/fail")
async def fail_tower(request: TowerControlRequest):
    """Fail a radio tower."""
    await app_state.fail_radio_tower(request.towerId)

    # Broadcast status update
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}


@app.post("/api/towers/repair")
async def repair_tower(request: TowerControlRequest):
    """Repair a radio tower."""
    await app_state.repair_radio_tower(request.towerId)

    # Broadcast status update
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}


@app.post("/api/edges/unblock")
async def unblock_edge(request: EdgeControlRequest):
    """Unblock a track edge."""
    await app_state.unblock_edge(request.edgeKey)

    # Broadcast status update
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}


@app.post("/api/dispatch-holds/clear")
async def clear_dispatch_hold(request: DispatchHoldRequest):
    """Clear a dispatch hold."""
    await app_state.clear_dispatch_hold(request.targetId)

    # Broadcast status update
    status = await app_state.get_status()
    await broadcast_to_clients({"type": "status", **status})

    return {"status": "ok"}


# WebSocket endpoint
@app.websocket("/ws/ticks")
async def websocket_ticks(websocket: WebSocket):
    """WebSocket endpoint for real-time tick updates."""
    await websocket.accept()
    connected_clients.append(websocket)

    logger.info(f"Client connected. Total clients: {len(connected_clients)}")

    try:
        # Keep connection alive and wait for client disconnect
        while True:
            # Just wait for incoming messages (even if we ignore them)
            # This allows the connection to stay open while we broadcast from other endpoints
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        logger.info(f"Client disconnected. Total clients: {len(connected_clients)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)


@app.on_event("startup")
async def startup_event():
    """Initialize app state on startup."""
    global app_state
    app_state = AppState(REPO_ROOT)
    logger.info("App state initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global tick_loop_task

    app_state.running = False
    if tick_loop_task and not tick_loop_task.done():
        tick_loop_task.cancel()
        try:
            await tick_loop_task
        except asyncio.CancelledError:
            pass

    logger.info("App shutting down")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
