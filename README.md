# DC Traffic Tracker

A full-stack city traffic dashboard: a 3D map of Washington, DC showing live
vehicle movement, per-camera congestion levels, historical trends, and an
incident feed — driven by a computer-vision pipeline over public DDOT traffic
camera feeds.

**Live:** https://dc-traffic-tracker.vercel.app (frontend, Vercel) ·
https://backend-production-79ef.up.railway.app (backend API, Railway) —
running in `CAMERA_MODE=mock`.

## How it works

- **Backend** (`backend/`, FastAPI + SQLAlchemy): maintains the camera
  registry, runs one pipeline per camera, computes congestion/incidents, and
  streams live vehicle positions over a WebSocket (`/ws/live`).
- **Frontend** (`frontend/`, React + TypeScript): a 3D map (MapLibre GL +
  deck.gl) animating vehicles in real time, with a sidebar for camera
  snapshots, congestion, history charts, and incidents.

### Two camera modes

Set with `CAMERA_MODE` (backend env var):

- **`mock` (default)** — no external dependencies, no GPU, nothing to
  configure. Each of the 28 seed DC intersections runs a synthetic traffic
  simulator (`backend/app/cv/pipeline.py::MockCameraSimulator`) that
  generates plausible vehicle flow, with density that oscillates over time so
  congestion levels and incidents are visibly dynamic. This is what runs out
  of the box.

- **`live`** — pulls DC's real public camera registry over DDOT's MQTT feed
  (see `backend/app/mqtt_client.py`), opens each camera's real video stream
  with OpenCV, and runs YOLOv8 vehicle detection (`ultralytics`) + a
  lightweight IOU tracker to find real vehicles frame to frame. The heavy deps
  this needs (`opencv-python-headless`, `ultralytics`, a CPU-only `torch`
  build) are in `backend/requirements.txt` unconditionally — verified working
  with real YOLO inference in this repo's dev environment. The broker connection
  details (host, port, MQTT-over-WebSocket transport, topic name) are
  hardcoded defaults verified against
  [ddotcli's source](https://github.com/a10y/ddotcli/blob/master/pkg/ddot/ddot.go),
  so no extra config is needed to *try* live mode — only override
  `DDOT_MQTT_*` if DDOT changes their broker. If the broker or a camera's
  stream can't be reached (checked directly — see below), that camera falls
  back to the mock simulator rather than crashing the app.

  **Sandboxed/CI environments:** this broker sits on a specific AWS Amazon MQ
  host, and some sandboxes only allow egress to an allowlist of domains — in
  this repo's own dev environment the connection was refused at the TLS layer
  by the network gateway itself (confirmed via a raw TCP+TLS test, independent
  of this app's code) even though the code and credentials are correct. If
  `HTTPS_PROXY` is set, the MQTT client routes through it automatically
  (needs `pysocks`, already in `requirements.txt`) — that gets you past a
  "no direct internet" restriction, but not past a gateway that blocks the
  destination outright. A normal machine or cloud host with unrestricted
  outbound internet should connect fine.

### Road-snapped motion

In mock mode, each camera is matched at startup to the nearest real street
from OpenStreetMap (`backend/app/cv/road_snap.py`, one batched query to the
public Overpass API covering every camera). When a match is found within
`ROAD_SNAP_RADIUS_M` (default 150m), simulated vehicles move by arc-length
along that street's actual polyline (`backend/app/cv/road_geometry.py`) --
real curves and turns, entering from one end and exiting the other, instead
of a straight synthetic line through the block. Any failure (no network, no
nearby drivable road, Overpass timeout) leaves that camera on the fallback
below rather than breaking anything; check the `Road snapping: matched X/Y
cameras` log line at startup to see how many actually got a real road.
Disable entirely with `ROAD_SNAP_ENABLED=false`.

### Important limitation: vehicle positions are approximate

Public traffic cameras like DDOT's don't publish per-camera calibration
(lens intrinsics, mounting angle/height). Without that, there's no way to
compute an exact pixel → GPS transform. The fallback in
`backend/app/cv/geo_projection.py` (used for live-mode detections always, and
for mock-mode cameras with no road match) is a simple ground-plane
approximation: a detection's horizontal position in frame becomes an angular
offset from the camera's assumed compass bearing, and its vertical position
becomes an assumed distance (closer to the bottom of frame = closer to the
camera, within a 6–70m assumed range). This places vehicles at a *plausible*
spot near their camera — good for a city-wide "here's where traffic is
moving" visualization, not for lane-level or GPS-grade accuracy. Real
per-camera bearings would improve this; the seed data ships with a
reasonable guess per intersection.

### Congestion & incidents

Every `HISTORY_SAMPLE_INTERVAL_SECONDS` (default 5s), each camera's current
vehicle count and average speed are persisted and classified into a
congestion level (`free` / `light` / `moderate` / `heavy`, thresholds in
`backend/app/config.py`). An in-memory rolling baseline per camera
(`backend/app/services/incidents.py`) flags sudden speed drops or count
spikes as incidents.

## Running it

### Docker (easiest)

```bash
docker compose up --build
```

Frontend: http://localhost:8080 · Backend: http://localhost:8000

### Locally

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. It talks to the backend at
`http://localhost:8000` by default (override with `VITE_API_BASE` /
`VITE_WS_BASE` env vars, e.g. in a `.env.local`).

### Enabling live camera mode

```bash
cd backend
pip install -r requirements.txt   # already includes opencv/ultralytics/torch
export CAMERA_MODE=live
uvicorn app.main:app --reload
```

No `DDOT_MQTT_HOST` needed — it defaults to the real broker. Cameras the live
registry doesn't return a stream for (or whose stream fails to open) keep
running the mock simulator individually, so the app degrades per-camera
rather than all-or-nothing.

`ultralytics`/`torch` are ~1-2GB and CPU inference is slow — a GPU box is
recommended if you run more than a couple of live cameras at once.
`MAX_ACTIVE_CAMERAS` caps how many camera pipelines run concurrently.

### Basemap

By default the map uses [OpenFreeMap](https://openfreemap.org)'s free
`liberty` vector style — streets, labels, buildings, no API key, no usage
cap. If that style fails to load (network policy blocking it, provider
outage), the map falls back to a self-contained blank background rather than
getting stuck with no camera/vehicle layers at all. Override
`VITE_MAP_STYLE_URL` for something else — e.g. a free
[MapTiler](https://www.maptiler.com/) key — for 3D building extrusion:

```bash
# frontend/.env.local
VITE_MAP_STYLE_URL=https://api.maptiler.com/maps/streets-v2/style.json?key=YOUR_KEY
```

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

Covers the pixel→geo projection, road-polyline arc-length math, the IOU
tracker, congestion thresholds, and the rolling-baseline incident detector.
`.github/workflows/ci.yml` runs this plus a frontend build on every push.

## Key files

```
backend/app/
  cv/geo_projection.py   pixel -> lat/lon approximation (fallback / live mode)
  cv/road_geometry.py     polyline arc-length math (pure, no network)
  cv/road_snap.py           fetches real roads near each camera (Overpass API)
  cv/detector.py          YOLO vehicle detector (live mode)
  cv/tracker.py            lightweight IOU tracker
  cv/pipeline.py            per-camera mock simulator + live pipeline
  camera_registry.py     DDOT MQTT camera list, with seed fallback
  mqtt_client.py           DDOT public MQTT client
  worker.py                 orchestrates all camera pipelines, persists history
  services/congestion.py  vehicle count/speed -> congestion level
  services/incidents.py    rolling-baseline anomaly detection
  routers/live.py            WebSocket: live vehicle/congestion/incident stream
frontend/src/
  components/Map3D.tsx     deck.gl + MapLibre 3D map
  api/useLiveFeed.ts        WebSocket client + client-side position interpolation
```

## Data sources

- Seed camera locations: 28 well-known DC intersections with approximate
  public coordinates (`backend/seed_data/dc_cameras.json`), used as a
  zero-config fallback and as the mock-mode camera list.
- Live camera registry: DDOT's public MQTT broker, connection details (host,
  port, transport, `DDOT/Camera` topic, payload shape) verified against the
  source of the community
  [`ddotcli`](https://github.com/a10y/ddotcli/blob/master/pkg/ddot/ddot.go)
  project. The credentials referenced in `backend/app/config.py` are
  published there as a public feed, not a private secret. The feed doesn't
  publish a per-camera compass bearing, so (like the seed data) live cameras
  get a stable placeholder bearing — see the geo-projection limitation above.
- Live incident feed: an `DDOT/Incidents` MQTT topic is wired up
  (`backend/app/mqtt_client.py::IncidentListener`) but its topic name, unlike
  the camera one, is *not* confirmed against source — treat it as best-effort
  and verify independently before relying on it.
