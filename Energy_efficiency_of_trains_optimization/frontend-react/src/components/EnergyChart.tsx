import React from "react";
import { Metrics } from "../types";
import "./EnergyChart.css";

interface EnergyPoint {
  tick: number;
  powerW: number;
  netKwh: number;
}

interface EnergyChartProps {
  history: EnergyPoint[];
  metrics: Metrics | null;
}

const EnergyChart: React.FC<EnergyChartProps> = ({ history, metrics }) => {
  const maxPower = Math.max(1, ...history.map((point) => point.powerW));
  return (
    <section className="energy-chart">
      <div className="energy-chart-header">
        <h2>Power and energy</h2>
        <span>
          {metrics
            ? `${metrics.totalNetEnergyKwh.toFixed(1)} kWh net`
            : "Waiting"}
        </span>
      </div>
      <div className="energy-bars" aria-label="Power history">
        {history.slice(-36).map((point) => (
          <div
            className="energy-bar-column"
            key={point.tick}
            title={`Tick ${point.tick}: ${(point.powerW / 1000).toFixed(0)} kW`}
          >
            <div
              className="energy-bar"
              style={{
                height: `${Math.max(4, (point.powerW / maxPower) * 100)}%`,
              }}
            />
          </div>
        ))}
      </div>
      <div className="energy-chart-legend">
        <span>Power draw</span>
        <span>Last {Math.min(36, history.length)} ticks</span>
      </div>
    </section>
  );
};

export default EnergyChart;
