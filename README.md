# DC Traffic Tracker

A full-stack city traffic dashboard: a 3D map of Washington, DC showing live
vehicle movement, per-camera congestion levels, historical trends, and an
incident feed — driven by a computer-vision pipeline over public DDOT traffic
camera feeds.

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
  of the box and what the screenshots below were taken from.

- **`live`** — pulls DC's real public camera registry over DDOT's MQTT feed
  (see `backend/app/mqtt_client.py`), opens each camera's real video stream
  with OpenCV, and runs YOLOv8 vehicle detection (`ultralytics`) + a
  lightweight IOU tracker to find real vehicles frame to frame. Requires the
  optional heavy deps commented out in `backend/requirements.txt`
  (`opencv-python-headless`, `ultralytics`, `torch`) and `DDOT_MQTT_HOST` set.
  If live mode fails to reach the broker or a camera's stream, it falls back
  to the mock simulator for that camera rather than crashing.

### Important limitation: vehicle positions are approximate

Public traffic cameras like DDOT's don't publish per-camera calibration
(lens intrinsics, mounting angle/height). Without that, there's no way to
compute an exact pixel → GPS transform. Instead, `backend/app/cv/geo_projection.py`
uses a simple ground-plane approximation: a detection's horizontal position
in frame becomes an angular offset from the camera's assumed compass bearing,
and its vertical position becomes an assumed distance (closer to the bottom
of frame = closer to the camera, within a 6–70m assumed range). This places
vehicles at a *plausible* spot near their camera — good for a city-wide "here's
where traffic is moving" visualization, not for lane-level or GPS-grade
accuracy. Real per-camera bearings would improve this; the seed data ships
with a reasonable guess per intersection.

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
pip install opencv-python-headless ultralytics torch  # uncomment in requirements.txt too
export CAMERA_MODE=live
export DDOT_MQTT_HOST=<ddot mqtt broker host>   # see backend/app/mqtt_client.py for details
uvicorn app.main:app --reload
```

`ultralytics`/`torch` are ~1-2GB and CPU inference is slow — a GPU box is
recommended if you run more than a couple of live cameras at once.
`MAX_ACTIVE_CAMERAS` caps how many camera pipelines run concurrently.

### Full 3D basemap (buildings, streets, labels)

By default the map uses a self-contained blank background (no external tile
dependency, so it always renders). Point it at a real vector basemap style —
e.g. a free [MapTiler](https://www.maptiler.com/) key — for streets, labels,
and 3D building extrusion:

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

Covers the pixel→geo projection, the IOU tracker, congestion thresholds, and
the rolling-baseline incident detector. `.github/workflows/ci.yml` runs this
plus a frontend build on every push.

## Key files

```
backend/app/
  cv/geo_projection.py   pixel -> lat/lon approximation
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
- Live camera registry & incident feed: DDOT's public MQTT broker, documented
  by the community [`ddotcli`](https://github.com/a10y/ddotcli) project. The
  broker credentials referenced in `backend/app/config.py` are published
  there as a public feed, not a private secret.
