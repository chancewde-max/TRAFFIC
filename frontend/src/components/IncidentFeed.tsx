import type { Camera, Incident } from "../types";

interface Props {
  incidents: Incident[];
  cameras: Camera[];
  onSelect: (cameraId: string) => void;
}

export default function IncidentFeed({ incidents, cameras, onSelect }: Props) {
  if (incidents.length === 0) {
    return <p className="empty-hint">No incidents detected yet.</p>;
  }

  const nameFor = (id: string) => cameras.find((c) => c.id === id)?.name ?? id;

  return (
    <ul className="incident-list">
      {incidents.map((incident) => (
        <li
          key={incident.id}
          className={`incident-item ${incident.severity}`}
          onClick={() => onSelect(incident.camera_id)}
        >
          <div>{incident.description}</div>
          <div className="incident-meta">
            {nameFor(incident.camera_id)} · {new Date(incident.ts).toLocaleTimeString()}
          </div>
        </li>
      ))}
    </ul>
  );
}
