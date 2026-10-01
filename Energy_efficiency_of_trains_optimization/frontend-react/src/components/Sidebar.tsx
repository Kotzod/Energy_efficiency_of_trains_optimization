/** Energy optimization metrics sidebar. */

import React from "react";
import { Metrics } from "../types";
import "./Sidebar.css";

function formatPower(watts: number): string {
  if (!Number.isFinite(watts)) return "0 W";
  const abs = Math.abs(watts);
  if (abs >= 1_000_000) return `${(watts / 1_000_000).toFixed(2)} MW`;
  if (abs >= 1_000) return `${(watts / 1_000).toFixed(1)} kW`;
  return `${watts.toFixed(0)} W`;
}

interface SidebarProps {
  metrics: Metrics | null;
}

const Sidebar: React.FC<SidebarProps> = ({ metrics }) => {
  const value = (number: number, digits = 0) =>
    Number.isFinite(number) ? number.toFixed(digits) : "0";

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h2>Energy Metrics</h2>
      </div>

      <div className="sidebar-content">
        {!metrics ? (
          <p className="metrics-empty">Waiting for simulation data...</p>
        ) : (
          <>
            <div className="metric-headline">
              <span className="metric-headline-label">
                {metrics.controllerMode === "mpc" ? "MPC" : "Rule-Based"}{" "}
                current draw
              </span>
              <span className="metric-headline-value">
                {formatPower(metrics.totalPowerW)}
              </span>
            </div>

            <div className="metric-row">
              <span className="metric-label">Consumed</span>
              <span className="metric-value">
                {value(metrics.totalEnergyConsumedKwh, 2)} kWh
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Regenerated</span>
              <span className="metric-value">
                {value(metrics.totalEnergyRegeneratedKwh, 2)} kWh
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Net energy</span>
              <span className="metric-value">
                {value(metrics.totalNetEnergyKwh, 2)} kWh
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Active trains</span>
              <span className="metric-value">
                {value(metrics.activeTrains)}
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Moving / stopped</span>
              <span className="metric-value">
                {value(metrics.movingTrains)} / {value(metrics.stoppedTrains)}
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Holding for a meet</span>
              <span className="metric-value">
                {value(metrics.trainsHolding)}
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Avg speed (moving)</span>
              <span className="metric-value">
                {value(metrics.averageSpeedKmh)} km/h
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Total delay</span>
              <span className="metric-value">
                {value(metrics.totalDelayTicks)} ticks
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Energy / km</span>
              <span className="metric-value">
                {value(metrics.energyPerKm, 2)} kWh/km
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
