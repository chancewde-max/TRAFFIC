import type { Camera, Congestion, HistoryPoint, Incident } from "../types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
export const WS_BASE = import.meta.env.VITE_WS_BASE ?? API_BASE.replace(/^http/, "ws");

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  cameras: () => getJson<Camera[]>("/api/cameras"),
  congestion: () => getJson<Congestion[]>("/api/congestion"),
  incidents: (limit = 50) => getJson<Incident[]>(`/api/incidents?limit=${limit}`),
  history: (cameraId: string, hours = 6) =>
    getJson<HistoryPoint[]>(`/api/history?camera_id=${encodeURIComponent(cameraId)}&hours=${hours}`),
};
