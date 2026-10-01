import React from "react";
import { Train } from "../types";
import "./TrainInspector.css";

interface TrainInspectorProps {
  train: Train | null;
}

const TrainInspector: React.FC<TrainInspectorProps> = ({ train }) => {
  if (!train)
    return (
      <section className="train-inspector">
        <h2>Train inspector</h2>
        <p>Select a train on the map.</p>
      </section>
    );
  return (
    <section className="train-inspector">
      <div className="inspector-heading">
        <h2>Train {train.trainId}</h2>
        <span>{train.trainType}</span>
      </div>
      <div className="inspector-grid">
        <span>State</span>
        <strong>{train.controllerAction || train.state}</strong>
        <span>Speed</span>
        <strong>{train.speedKmh.toFixed(0)} km/h</strong>
        <span>Power</span>
        <strong>{(train.powerW / 1000).toFixed(0)} kW</strong>
        <span>Consumed</span>
        <strong>{train.energyConsumedKwh.toFixed(2)} kWh</strong>
        <span>Regenerated</span>
        <strong>{train.energyRegeneratedKwh.toFixed(2)} kWh</strong>
        <span>Net energy</span>
        <strong>{train.netEnergyKwh.toFixed(2)} kWh</strong>
        <span>Acceleration</span>
        <strong>{train.accelerationMs2.toFixed(2)} m/s2</strong>
      </div>
      <p className="inspector-reason">{train.controllerReason}</p>
    </section>
  );
};

export default TrainInspector;
