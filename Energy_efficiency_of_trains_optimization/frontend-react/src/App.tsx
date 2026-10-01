/**
 * Main App component
 * Manages state, WebSocket connection, animation loop, and layout
 */

import React, { useEffect, useState, useRef, useCallback } from "react";
import MapView from "./components/MapView";
import ControlBar from "./components/ControlBar";
import Sidebar from "./components/Sidebar";
import Legend from "./components/Legend";
import EnergyChart from "./components/EnergyChart";
import TrainInspector from "./components/TrainInspector";
import {
  Infrastructure,
  StatusMessage,
  Train,
  TickMessage,
  WebSocketMessage,
  Metrics,
} from "./types";
import "./App.css";

const API_BASE = "http://localhost:8000";
const WS_BASE = "ws://localhost:8000";

interface TickState {
  prev: TickMessage | null;
  prevReceivedAt: number;
  curr: TickMessage | null;
  currReceivedAt: number;
}

const App: React.FC = () => {
  // State
  const [infrastructure, setInfrastructure] = useState<Infrastructure | null>(
    null,
  );
  const [status, setStatus] = useState<StatusMessage | null>(null);
  const [trains, setTrains] = useState<Train[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [selectedTrainId, setSelectedTrainId] = useState<string | null>(null);
  const [energyHistory, setEnergyHistory] = useState<
    Array<{ tick: number; powerW: number; netKwh: number }>
  >([]);
  const [tick, setTick] = useState(0);
  const [running, setRunning] = useState(false);
  const [speed, setSpeed] = useState(200);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [controllerMode, setControllerMode] = useState<
    "rule_based" | "mpc" | "ai"
  >("rule_based");

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const tickStateRef = useRef<TickState>({
    prev: null,
    prevReceivedAt: 0,
    curr: null,
    currReceivedAt: 0,
  });
  const animFrameRef = useRef<number | null>(null);

  // Initialize infrastructure on mount
  useEffect(() => {
    const fetchInfrastructure = async () => {
      try {
        setLoading(true);
        const res = await fetch(`${API_BASE}/api/infrastructure`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setInfrastructure(data);

        // Also fetch initial status
        const statusRes = await fetch(`${API_BASE}/api/status`);
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setStatus({
            type: "status" as const,
            ...statusData,
          });
        }

        setError(null);
      } catch (err) {
        setError(`Failed to load infrastructure: ${err}`);
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchInfrastructure();
  }, []);

  // Connect WebSocket
  useEffect(() => {
    if (!infrastructure) return;

    const connectWebSocket = () => {
      const ws = new WebSocket(`${WS_BASE}/ws/ticks`);

      ws.onopen = () => {
        console.log("WebSocket connected");
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);

          if (message.type === "tick") {
            const tickMsg = message as TickMessage;
            tickStateRef.current.prev = tickStateRef.current.curr;
            tickStateRef.current.prevReceivedAt =
              tickStateRef.current.currReceivedAt;
            tickStateRef.current.curr = tickMsg;
            tickStateRef.current.currReceivedAt = performance.now();

            setTick(tickMsg.tick);
            setMetrics(tickMsg.metrics ?? null);
            setEnergyHistory((history) => [
              ...history.slice(-119),
              {
                tick: tickMsg.tick,
                powerW: tickMsg.metrics?.totalPowerW ?? 0,
                netKwh: tickMsg.metrics?.totalNetEnergyKwh ?? 0,
              },
            ]);
            if (tickMsg.metrics?.controllerMode) {
              setControllerMode(tickMsg.metrics.controllerMode);
            }
            // Trains will be interpolated in animation loop
          } else if (message.type === "status") {
            const statusMsg = message as StatusMessage;
            setStatus(statusMsg);
          }
        } catch (err) {
          console.error("Error parsing WebSocket message:", err);
        }
      };

      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        setError("WebSocket connection failed");
      };

      ws.onclose = () => {
        console.log("WebSocket closed");
        // Try to reconnect after 2 seconds
        setTimeout(connectWebSocket, 2000);
      };

      wsRef.current = ws;
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [infrastructure]);

  // Animation loop - smooth interpolation between ticks
  useEffect(() => {
    const tick_state = tickStateRef.current;

    const animationFrame = (now: number) => {
      if (tick_state.prev && tick_state.curr) {
        const elapsedSincePrev = now - tick_state.prevReceivedAt;
        const tickInterval =
          tick_state.currReceivedAt - tick_state.prevReceivedAt;
        const t = tickInterval > 0 ? elapsedSincePrev / tickInterval : 1;
        const clamped = Math.max(0, Math.min(1, t));

        // Interpolate train positions
        const interpolatedTrains: Train[] = [];

        tick_state.curr.trains.forEach((currTrain) => {
          const prevTrain = tick_state.prev?.trains.find(
            (p) => p.trainId === currTrain.trainId,
          );

          if (!prevTrain) {
            // Newly spawned train, snap to current position
            interpolatedTrains.push({ ...currTrain });
          } else {
            // Interpolate position
            const interpolatedPos: [number, number] = [
              prevTrain.position[0] +
                (currTrain.position[0] - prevTrain.position[0]) * clamped,
              prevTrain.position[1] +
                (currTrain.position[1] - prevTrain.position[1]) * clamped,
            ];

            interpolatedTrains.push({
              ...currTrain,
              position: interpolatedPos,
            });
          }
        });

        setTrains(interpolatedTrains);
      }

      animFrameRef.current = requestAnimationFrame(animationFrame);
    };

    animFrameRef.current = requestAnimationFrame(animationFrame);

    return () => {
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, []);

  // API call functions
  const apiCall = useCallback(
    async (method: string, path: string, body?: any) => {
      try {
        const options: RequestInit = {
          method,
          headers: { "Content-Type": "application/json" },
        };
        if (body) options.body = JSON.stringify(body);

        const res = await fetch(`${API_BASE}${path}`, options);
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `HTTP ${res.status}`);
        }
        return await res.json();
      } catch (err) {
        console.error(`API error [${method} ${path}]:`, err);
        throw err;
      }
    },
    [],
  );

  const handleStep = useCallback(async () => {
    try {
      await apiCall("POST", "/api/step", {});
    } catch (err) {
      setError(`Step failed: ${err}`);
    }
  }, [apiCall]);

  const handleRun = useCallback(async () => {
    try {
      await apiCall("POST", "/api/run", { intervalMs: speed });
      setRunning(true);
    } catch (err) {
      setError(`Run failed: ${err}`);
    }
  }, [apiCall, speed]);

  const handlePause = useCallback(async () => {
    try {
      await apiCall("POST", "/api/pause", {});
      setRunning(false);
    } catch (err) {
      setError(`Pause failed: ${err}`);
    }
  }, [apiCall]);

  const handleReset = useCallback(async () => {
    try {
      await apiCall("POST", "/api/reset", { seed: 67 });
      setTick(0);
      setRunning(false);
      setSelectedTrainId(null);
      setEnergyHistory([]);
    } catch (err) {
      setError(`Reset failed: ${err}`);
    }
  }, [apiCall]);

  const selectedTrain =
    trains.find((train) => train.trainId === selectedTrainId) ?? null;

  const handleSpeedChange = useCallback(
    async (newSpeed: number) => {
      setSpeed(newSpeed);
      if (running) {
        // Restart with new speed
        await apiCall("POST", "/api/run", { intervalMs: newSpeed });
      }
    },
    [running, apiCall],
  );

  const handleControllerChange = useCallback(
    async (mode: "rule_based" | "mpc" | "ai") => {
      try {
        await apiCall("POST", "/api/controller", { mode });
        setControllerMode(mode);
      } catch (err) {
        setError(`Controller change failed: ${err}`);
      }
    },
    [apiCall],
  );

  if (loading) {
    return (
      <div className="loading-container">
        <h1>Railway Energy Twin</h1>
        <p>Loading...</p>
      </div>
    );
  }

  if (!infrastructure) {
    return (
      <div className="error-container">
        <h1>Railway Energy Twin</h1>
        <p>Failed to load infrastructure: {error}</p>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="header">
        <h1>Railway Energy Twin</h1>
        <p>Energy-aware Tampere-Pori railway simulation</p>
        {error && <div className="error-bar">{error}</div>}
      </div>

      <div className="main-layout">
        <Sidebar metrics={metrics} />

        <div className="content-area">
          <div className="map-container">
            <MapView
              infrastructure={infrastructure}
              trains={trains}
              status={status}
              metrics={metrics}
              onTrainSelect={(train) => setSelectedTrainId(train.trainId)}
            />
            <Legend weather={status?.weather} />
          </div>

          <div className="control-section">
            <div className="inspector-row">
              <TrainInspector train={selectedTrain} />
              <EnergyChart history={energyHistory} metrics={metrics} />
            </div>
            <ControlBar
              running={running}
              tick={tick}
              speed={speed}
              onStep={handleStep}
              onRun={handleRun}
              onPause={handlePause}
              onReset={handleReset}
              onSpeedChange={handleSpeedChange}
              controllerMode={controllerMode}
              onControllerChange={handleControllerChange}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;
