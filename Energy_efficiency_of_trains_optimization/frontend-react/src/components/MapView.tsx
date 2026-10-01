/**
 * MapView component - deck.gl visualization with tracks, stations, trains, and heatmaps
 */

import React, { useMemo } from "react";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { DeckProps } from "@deck.gl/core";
import { MapboxOverlay } from "@deck.gl/mapbox";
import Map, { useControl } from "react-map-gl/maplibre";
import {
  Infrastructure,
  Train,
  ViewState,
  StatusMessage,
  Metrics,
} from "../types";
import "./MapView.css";
import "maplibre-gl/dist/maplibre-gl.css";

const MAP_STYLE =
  "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

function DeckGLOverlay(props: DeckProps) {
  const overlay = useControl<MapboxOverlay>(
    () => new MapboxOverlay({ ...props, interleaved: true }),
  );
  overlay.setProps({ ...props, interleaved: true });
  return null;
}

interface MapViewProps {
  infrastructure: Infrastructure | null;
  trains: Train[];
  status: StatusMessage | null;
  onViewStateChange?: (viewState: ViewState) => void;
  onTrainSelect?: (train: Train) => void;
  metrics?: Metrics | null;
}

const MapView: React.FC<MapViewProps> = ({
  infrastructure,
  trains,
  status,
  onViewStateChange,
  onTrainSelect,
  metrics,
}) => {
  const [viewState, setViewState] = React.useState<ViewState>(
    infrastructure?.viewState || {
      latitude: 61.4978,
      longitude: 22.8,
      zoom: 8.2,
      pitch: 0,
    },
  );

  // Build layers
  const layers = useMemo(() => {
    if (!infrastructure) return [];

    const layersArray = [];

    // Track paths layer
    if (infrastructure.trackPaths.length > 0) {
      layersArray.push(
        new PathLayer({
          id: "track-layer",
          data: infrastructure.trackPaths,
          getPath: (d: any) => d.path,
          getColor: (d: any) => {
            const net = metrics?.energyByEdge?.[d.edgeKey]?.netKwh ?? 0;
            if (net > 100) return [220, 38, 38];
            if (net > 25) return [234, 179, 8];
            return [34, 197, 94];
          },
          widthScale: 15,
          widthMinPixels: 3,
          pickable: false,
        }),
      );
    }

    // Stations layer
    if (infrastructure.stations.length > 0) {
      layersArray.push(
        new ScatterplotLayer({
          id: "station-layer",
          data: infrastructure.stations,
          getPosition: (d: any) => d.position,
          getFillColor: [186, 230, 253],
          getRadius: 400,
          radiusMinPixels: 4,
          pickable: true,
          autoHighlight: true,
          onHover: (info: any) => {
            if (info.object) {
              console.log("Hovering station:", info.object.name);
            }
          },
          onClick: (info: any) => {
            if (info.object) onTrainSelect?.(info.object as Train);
          },
        }),
      );
    }

    // Heatmap layer (only for operational towers)
    const operationalTowerIds = new Set(
      (status?.towers || [])
        .filter((t: any) => t.operational)
        .map((t: any) => t.tower_id),
    );

    const heatmapPoints: any[] = [];
    if (infrastructure.towers.length > 0) {
      infrastructure.towers.forEach((tower) => {
        if (operationalTowerIds.has(tower.towerId)) {
          heatmapPoints.push(...tower.heatmapPoints);
        }
      });
    }

    if (heatmapPoints.length > 0) {
      layersArray.push(
        new HeatmapLayer<any>({
          id: "heatmap-layer",
          data: heatmapPoints,
          getPosition: (d: any) => d.position,
          getWeight: (d: any) => d.weight,
          radiusPixels: 70,
          intensity: 1.0,
          threshold: 0.02,
          aggregation: "SUM",
          colorRange: [
            [0, 0, 255],
            [0, 255, 255],
            [0, 255, 0],
            [255, 255, 0],
            [255, 0, 0],
          ],
          pickable: false,
        }),
      );
    }

    // Trains layer
    if (trains.length > 0) {
      const trainData = trains.map((train) => ({
        ...train,
        color: train.trainType === "freight" ? [245, 158, 11] : [59, 130, 246],
        radius: train.trainType === "freight" ? 900 : 750,
      }));

      layersArray.push(
        new ScatterplotLayer({
          id: "train-layer",
          data: trainData,
          getPosition: (d: any) => d.position,
          getFillColor: (d: any) => d.color,
          getLineColor: [255, 255, 255],
          lineWidthMinPixels: 1.5,
          getRadius: (d: any) => d.radius,
          radiusMinPixels: 7,
          stroked: true,
          filled: true,
          pickable: true,
          autoHighlight: true,
          onHover: (info: any) => {
            if (info.object) {
              const train = info.object as Train;
              console.log(
                `Train ${train.trainId}: ${train.state} at ${train.speedKmh.toFixed(1)} km/h`,
              );
            }
          },
        }),
      );
    }

    return layersArray;
  }, [infrastructure, trains, status, metrics]);

  const handleViewStateChange = (vs: any) => {
    setViewState(vs.viewState);
    onViewStateChange?.(vs.viewState);
  };

  return (
    <div className="map-view">
      <Map
        mapStyle={MAP_STYLE}
        latitude={viewState.latitude}
        longitude={viewState.longitude}
        zoom={viewState.zoom}
        pitch={viewState.pitch}
        onMove={(event) => handleViewStateChange(event)}
        reuseMaps
      >
        <DeckGLOverlay
          layers={layers}
          getTooltip={({ object }: any) => {
            if (!object) return null;
            if (object.name) {
              return {
                html: `<div><strong>${object.name}</strong></div>`,
                style: { backgroundColor: "rgba(0, 0, 0, 0.8)", color: "#fff" },
              };
            }
            if (object.trainId) {
              return {
                html: `<div>
                  <strong>${object.trainId}</strong><br/>
                  Type: ${object.trainType}<br/>
                  State: ${object.state}<br/>
                  Speed: ${object.speedKmh.toFixed(1)} km/h
                </div>`,
                style: { backgroundColor: "rgba(0, 0, 0, 0.8)", color: "#fff" },
              };
            }
            return null;
          }}
        />
      </Map>
    </div>
  );
};

export default MapView;
