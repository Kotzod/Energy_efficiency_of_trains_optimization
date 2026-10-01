/**
 * Legend component - Heatmap gradient, weather, and train color legend
 */

import React from "react";
import "./Legend.css";

interface LegendProps {
  weather?: string;
}

const Legend: React.FC<LegendProps> = ({ weather = "Clear" }) => {
  const getWeatherSymbol = (weatherName: string): string => {
    const symbols: Record<string, string> = {
      Clear: "☀️",
      Cloudy: "☁️",
      Rainy: "🌧️",
      Snowy: "❄️",
      Foggy: "🌫️",
    };
    return symbols[weatherName] || "☀️";
  };

  return (
    <div className="legend">
      <div className="legend-section">
        <h4>Heatmap Coverage</h4>
        <div className="heatmap-gradient"></div>
        <div className="gradient-labels">
          <span>Less</span>
          <span>More</span>
        </div>
      </div>

      <div className="legend-section">
        <h4>Weather</h4>
        <div className="weather-info">
          <span className="weather-symbol">{getWeatherSymbol(weather)}</span>
          <span className="weather-name">{weather}</span>
        </div>
      </div>

      <div className="legend-section">
        <h4>Train Types</h4>
        <div className="train-legend">
          <div className="train-item">
            <div
              className="train-dot"
              style={{ backgroundColor: "rgb(59, 130, 246)" }}
            ></div>
            <span>Passenger</span>
          </div>
          <div className="train-item">
            <div
              className="train-dot"
              style={{ backgroundColor: "rgb(245, 158, 11)" }}
            ></div>
            <span>Freight</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Legend;
