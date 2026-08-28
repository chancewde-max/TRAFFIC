import type { Camera, Congestion, Incident } from "../types";
import CameraList from "./CameraList";
import CameraPanel from "./CameraPanel";
import CongestionLegend from "./CongestionLegend";
import HistoryChart from "./HistoryChart";
import IncidentFeed from "./IncidentFeed";

interface Props {
  cameras: Camera[];
  congestionByCamera: Record<string, Congestion>;
  incidents: Incident[];
  selectedCameraId: string | null;
  onSelectCamera: (id: string) => void;
}

export default function Sidebar({
  cameras,
  congestionByCamera,
  incidents,
  selectedCameraId,
  onSelectCamera,
}: Props) {
  const selectedCamera = cameras.find((c) => c.id === selectedCameraId) ?? null;
  const selectedCongestion = selectedCameraId ? congestionByCamera[selectedCameraId] ?? null : null;

  return (
    <aside className="sidebar">
      <div className="section">
        <h2>Selected Camera</h2>
        <CameraPanel camera={selectedCamera} congestion={selectedCongestion} />
      </div>

      <div className="section">
        <h2>Recent Trend</h2>
        <HistoryChart cameraId={selectedCameraId} />
      </div>

      <div className="section">
        <h2>Congestion Legend</h2>
        <CongestionLegend />
      </div>

      <div className="section">
        <h2>Cameras ({cameras.length})</h2>
        <CameraList
          cameras={cameras}
          congestionByCamera={congestionByCamera}
          selectedCameraId={selectedCameraId}
          onSelect={onSelectCamera}
        />
      </div>

      <div className="section" style={{ flex: 1 }}>
        <h2>Incidents</h2>
        <IncidentFeed incidents={incidents} cameras={cameras} onSelect={onSelectCamera} />
      </div>
    </aside>
  );
}
