import type { Camera, Congestion } from "../types";

interface Props {
  cameras: Camera[];
  congestionByCamera: Record<string, Congestion>;
  selectedCameraId: string | null;
  onSelect: (id: string) => void;
}

export default function CameraList({ cameras, congestionByCamera, selectedCameraId, onSelect }: Props) {
  if (cameras.length === 0) {
    return <p className="empty-hint">Connecting to live feed…</p>;
  }

  return (
    <ul className="camera-list">
      {cameras.map((camera) => {
        const level = congestionByCamera[camera.id]?.level ?? "free";
        return (
          <li
            key={camera.id}
            className={`camera-row${camera.id === selectedCameraId ? " selected" : ""}`}
            onClick={() => onSelect(camera.id)}
          >
            <span className="camera-row-name">{camera.name}</span>
            <span className={`level-badge level-${level}`}>{level}</span>
          </li>
        );
      })}
    </ul>
  );
}
