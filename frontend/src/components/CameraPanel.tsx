import type { Camera, Congestion } from "../types";

interface Props {
  camera: Camera | null;
  congestion: Congestion | null;
}

export default function CameraPanel({ camera, congestion }: Props) {
  if (!camera) {
    return <p className="empty-hint">Select a camera on the map or list to see details.</p>;
  }

  return (
    <div className="camera-panel">
      {camera.snapshot_url ? (
        <img src={camera.snapshot_url} alt={`Live snapshot from ${camera.name}`} />
      ) : (
        <div className="placeholder">
          {camera.source === "seed"
            ? "No live snapshot for this seed camera — running in mock mode"
            : "Snapshot unavailable"}
        </div>
      )}
      <div className="stat-row">
        <span>Vehicles tracked</span>
        <span>{congestion?.vehicle_count ?? "—"}</span>
      </div>
      <div className="stat-row">
        <span>Avg. speed</span>
        <span>{congestion?.avg_speed_mps != null ? `${congestion.avg_speed_mps.toFixed(1)} m/s` : "—"}</span>
      </div>
      <div className="stat-row">
        <span>Congestion</span>
        <span className={`level-badge level-${congestion?.level ?? "free"}`}>
          {congestion?.level ?? "free"}
        </span>
      </div>
      <div className="stat-row">
        <span>Source</span>
        <span>{camera.source === "ddot_mqtt" ? "DDOT live feed" : "Seed / simulated"}</span>
      </div>
    </div>
  );
}
