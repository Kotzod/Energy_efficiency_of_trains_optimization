/**
 * TypeScript types for the Railway Energy Twin frontend
 */

export interface Position {
  type: "Point";
  coordinates: [number, number]; // [lon, lat]
}

export interface Train {
  trainId: string;
  trainType: "passenger" | "freight";
  state: string;
  position: [number, number]; // [lon, lat]
  speedKmh: number;
  waitTime: number;
  currentNode: string;
  nextNode: string | null;
  routeProgress: string;
  powerW: number;
  energyConsumedKwh: number;
  energyRegeneratedKwh: number;
  netEnergyKwh: number;
  accelerationMs2: number;
  distanceTraveledKm: number;
  controllerAction: string;
  controllerReason: string;
  estimatedSavingKwh: number;
}

export interface TrackPath {
  path: Array<[number, number]>; // [lon, lat][]
  energyKwhPerKm?: number;
  edgeKey?: string;
}

export interface Station {
  id: string;
  position: [number, number]; // [lon, lat]
  name: string;
}

export interface HeatmapPoint {
  position: [number, number]; // [lon, lat]
  weight: number;
}

export interface Tower {
  towerId: string;
  positionKm: number;
  radiusKm: number;
  heatmapPoints: HeatmapPoint[];
}

export interface ViewState {
  latitude: number;
  longitude: number;
  zoom: number;
  pitch: number;
}

export interface Infrastructure {
  trackPaths: TrackPath[];
  stations: Station[];
  towers: Tower[];
  viewState: ViewState;
}

export interface TickMessage {
  type: "tick";
  tick: number;
  simTime: number;
  serverTimestampMs: number;
  trains: Train[];
  metrics?: Metrics;
}

export interface Metrics {
  totalPowerW: number;
  totalEnergyConsumedKwh: number;
  totalEnergyRegeneratedKwh: number;
  totalNetEnergyKwh: number;
  averageSpeedKmh: number;
  activeTrains: number;
  movingTrains: number;
  stoppedTrains: number;
  trainsHolding: number;
  totalDelayTicks: number;
  energyPerKm: number;
  controllerMode: "rule_based" | "mpc" | "ai";
  energyByEdge: Record<
    string,
    { consumedKwh: number; regeneratedKwh: number; netKwh: number }
  >;
}

export interface RadioTowerStatus {
  tower_id: string;
  operational: boolean;
}

export interface SwitchStatus {
  stationId: string;
  switchId: string;
  role: string;
  failed: boolean;
  clamped: boolean;
  clampedPosition: string | null;
  available: boolean;
  allowsStraight: boolean;
  allowsDiverging: boolean;
}

export interface StatusMessage {
  type: "status";
  weather: string;
  blockedEdges: string[];
  dispatchHolds: string[];
  towers: RadioTowerStatus[];
  switches: SwitchStatus[];
  controllerMode?: "rule_based" | "mpc" | "ai";
}

export type WebSocketMessage = TickMessage | StatusMessage;

export interface AppContextType {
  infrastructure: Infrastructure | null;
  status: StatusMessage | null;
  trains: Train[];
  tick: number;
  running: boolean;
  speed: number;
  loading: boolean;
  error: string | null;
}
