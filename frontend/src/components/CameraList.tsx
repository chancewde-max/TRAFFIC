import { useMemo, useState } from "react";

import type { Camera, Congestion } from "../types";

interface Props {
  cameras: Camera[];
  congestionByCamera: Record<string, Congestion>;
  selectedCameraId: string | null;
  onSelect: (id: string) => void;
}

type Filter = "all" | "real" | "simulated";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "real", label: "Real" },
  { key: "simulated", label: "Simulated" },
];

export default function CameraList({ cameras, congestionByCamera, selectedCameraId, onSelect }: Props) {
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = useMemo(() => {
    if (filter === "real") return cameras.filter((c) => c.source === "vdot_511");
    if (filter === "simulated") return cameras.filter((c) => c.source !== "vdot_511");
    return cameras;
  }, [cameras, filter]);

  const realCount = useMemo(() => cameras.filter((c) => c.source === "vdot_511").length, [cameras]);

  if (cameras.length === 0) {
    return <p className="empty-hint">Connecting to live feed…</p>;
  }

  return (
    <>
      <div className="filter-row">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`filter-btn${filter === f.key ? " active" : ""}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
            {f.key === "real" ? ` (${realCount})` : ""}
          </button>
        ))}
      </div>
      <ul className="camera-list">
        {filtered.map((camera) => {
          const isReal = camera.source === "vdot_511";
          const level = congestionByCamera[camera.id]?.level ?? "free";
          return (
            <li
              key={camera.id}
              className={`camera-row${camera.id === selectedCameraId ? " selected" : ""}`}
              onClick={() => onSelect(camera.id)}
            >
              <span className="camera-row-name">{camera.name}</span>
              {isReal ? (
                <span className="level-badge real-badge">REAL</span>
              ) : (
                <span className={`level-badge level-${level}`}>{level}</span>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
