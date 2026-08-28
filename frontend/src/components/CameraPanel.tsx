import { useEffect, useState } from "react";

import type { Camera, Congestion } from "../types";
import LiveClock from "./LiveClock";
import LiveVideo from "./LiveVideo";

interface Props {
  camera: Camera | null;
  congestion: Congestion | null;
}

const SOURCE_LABELS: Record<string, string> = {
  ddot_mqtt: "DDOT live feed",
  vdot_511: "VDOT 511 — real live camera",
  seed: "Seed / simulated",
};

const IMAGE_REFRESH_MS = 8000;

function useCacheBustedUrl(url: string | null | undefined, intervalMs: number): string | null {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!url) return;
    setTick(0);
    const id = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [url, intervalMs]);

  if (!url) return null;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}_t=${tick}`;
}

export default function CameraPanel({ camera, congestion }: Props) {
  const [videoFailed, setVideoFailed] = useState(false);
  const bustedSnapshotUrl = useCacheBustedUrl(camera?.snapshot_url, IMAGE_REFRESH_MS);

  useEffect(() => {
    setVideoFailed(false);
  }, [camera?.id]);

  if (!camera) {
    return <p className="empty-hint">Select a camera on the map or list to see details.</p>;
  }

  const isReal = camera.source === "vdot_511";
  const showVideo = isReal && camera.stream_url && !videoFailed;
  const showImage = !showVideo && (isReal ? bustedSnapshotUrl : camera.snapshot_url);

  return (
    <div className="camera-panel">
      {showVideo ? (
        <LiveVideo
          streamUrl={camera.stream_url!}
          posterUrl={camera.snapshot_url}
          onFailed={() => setVideoFailed(true)}
        />
      ) : showImage ? (
        <img src={showImage} alt={`Live view from ${camera.name}`} />
      ) : (
        <div className="placeholder">
          {camera.source === "seed"
            ? "No live snapshot for this seed camera — running in mock mode"
            : "Snapshot unavailable"}
        </div>
      )}

      {isReal && (
        <p className="empty-hint">
          <LiveClock prefix={showVideo ? "Live —" : "Image updates every 8s — as of"} />
        </p>
      )}

      {isReal ? (
        <p className="empty-hint">
          Real camera — traffic isn't simulated for it, so there's no vehicle/congestion data to show.
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
