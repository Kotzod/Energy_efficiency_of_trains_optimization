/**
 * ControlBar component - Step, Run, Pause, Reset buttons and speed slider
 */

import React from "react";
import "./ControlBar.css";

interface ControlBarProps {
  running: boolean;
  tick: number;
  speed: number;
  onStep: () => void;
  onRun: () => void;
  onPause: () => void;
  onReset: () => void;
  onSpeedChange: (speed: number) => void;
  controllerMode: "rule_based" | "mpc" | "ai";
  onControllerChange: (mode: "rule_based" | "mpc" | "ai") => void;
}

const ControlBar: React.FC<ControlBarProps> = ({
  running,
  tick,
  speed,
  onStep,
  onRun,
  onPause,
  onReset,
  onSpeedChange,
  controllerMode,
  onControllerChange,
}) => {
  return (
    <div className="control-bar">
      <div className="button-group">
        <button onClick={onStep} disabled={running}>
          Step
        </button>
        <button onClick={running ? onPause : onRun}>
          {running ? "Pause" : "Run"}
        </button>
        <button onClick={onReset}>Reset</button>
      </div>

      <div className="speed-control">
        <label htmlFor="controller-select">Controller:</label>
        <select
          id="controller-select"
          value={controllerMode}
          onChange={(event) =>
            onControllerChange(
              event.target.value as "rule_based" | "mpc" | "ai",
            )
          }
        >
          <option value="rule_based">Rule-Based</option>
          <option value="mpc">MPC</option>
          <option value="ai">AI (trained PPO)</option>
        </select>
        <label htmlFor="speed-slider">Speed (ms/tick):</label>
        <input
          id="speed-slider"
          type="range"
          min="50"
          max="1000"
          value={speed}
          onChange={(e) => onSpeedChange(parseInt(e.target.value, 10))}
          className="slider"
        />
        <span className="speed-value">{speed}ms</span>
      </div>

      <div className="tick-display">
        <span>Tick: {tick}</span>
      </div>
    </div>
  );
};

export default ControlBar;
