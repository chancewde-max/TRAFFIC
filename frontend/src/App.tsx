import { useState } from "react";

import { useLiveFeed } from "./api/useLiveFeed";
import Map3D from "./components/Map3D";
import Sidebar from "./components/Sidebar";

export default function App() {
  const { cameras, congestionByCamera, incidents, animatedVehicles, connected } = useLiveFeed();
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);

  return (
    <div className="app">
      <header className="topbar">
        <h1>DC Traffic Tracker</h1>
        <span className={`status-dot${connected ? " connected" : ""}`} />
        <span className="status-text">{connected ? "Live" : "Reconnecting…"}</span>
      </header>

      <Sidebar
        cameras={cameras}
        congestionByCamera={congestionByCamera}
        incidents={incidents}
        selectedCameraId={selectedCameraId}
        onSelectCamera={setSelectedCameraId}
      />

      <div className="map-wrap">
        <Map3D
          cameras={cameras}
          congestionByCamera={congestionByCamera}
          vehicles={animatedVehicles}
          selectedCameraId={selectedCameraId}
          onSelectCamera={setSelectedCameraId}
        />
      </div>
    </div>
  );
}
