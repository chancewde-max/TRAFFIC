import type { Camera, Congestion } from "../types";

interface Props {
  camera: Camera | null;
  congestion: Congestion | null;
}

const SOURCE_LABELS: Record<string, string> = {
  ddot_mqtt: "DDOT live feed",
  vdot_511: "VDOT 511 — real live image",
  seed: "Seed / simulated",
};

export default function CameraPanel({ camera, congestion }: Props) {
  if (!camera) {
    return <p className="empty-hint">Select a camera on the map or list to see details.</p>;
  }

  const isReal = camera.source === "vdot_511";

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
      {isReal ? (
        <p className="empty-hint">
          Real camera, real image — traffic isn't simulated for it, so there's no vehicle/congestion
          data to show.
        </p>
      ) : (
        <>
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
        </>
      )}
      <div className="stat-row">
        <span>Source</span>
        <span>{SOURCE_LABELS[camera.source] ?? camera.source}</span>
      </div>
    </div>
  );
}
