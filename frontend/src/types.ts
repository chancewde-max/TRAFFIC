export interface Camera {
  id: string;
  name: string;
  lat: number;
  lon: number;
  bearing_deg: number;
  stream_url: string | null;
  snapshot_url: string | null;
  source: string;
  active: number;
}

export type CongestionLevel = "free" | "light" | "moderate" | "heavy";

export interface Congestion {
  camera_id: string;
  vehicle_count: number;
  avg_speed_mps: number | null;
  level: CongestionLevel;
  ts: string;
}

export interface VehiclePosition {
  camera_id: string;
  track_id: number;
  lat: number;
  lon: number;
  heading_deg: number;
  speed_mps: number | null;
  vehicle_class: string;
}

export interface Incident {
  id: number;
  camera_id: string;
  kind: string;
  severity: "minor" | "major";
  description: string;
  ts: string;
}

export interface HistoryPoint {
  ts: string;
  vehicle_count: number;
  avg_speed_mps: number | null;
}

export type LiveMessage =
  | { type: "init"; cameras: Camera[]; congestion: Congestion[]; incidents: Incident[] }
  | { type: "vehicles"; camera_id: string; positions: VehiclePosition[] }
  | ({ type: "congestion" } & Congestion)
  | ({ type: "incident" } & Incident);
