"""Loads the working camera list: either the real DDOT MQTT registry (CAMERA_MODE=live)
or the bundled seed list (CAMERA_MODE=mock, or as a fallback if the live registry is
unreachable).
"""

from __future__ import annotations

import json
import logging
import os

from .config import settings
from .db import session_scope
from .models import Camera

logger = logging.getLogger(__name__)

SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "seed_data", "dc_cameras.json")


def load_seed_cameras() -> list[dict]:
    with open(SEED_PATH) as f:
        raw = json.load(f)
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "lat": c["lat"],
            "lon": c["lon"],
            "bearing_deg": c.get("bearing_deg", 0.0),
            "stream_url": None,
            "snapshot_url": None,
            "source": "seed",
        }
        for c in raw
    ]


def load_live_cameras(timeout: float = 8.0) -> list[dict] | None:
    """Attempt to fetch the real camera registry from DDOT's public MQTT broker.

    Returns None (caller should fall back to seed data) if the broker can't be
    reached in time or the payload can't be parsed -- this keeps the app usable
    even when outbound MQTT is blocked by network policy (e.g. in sandboxed
    dev environments).
    """

    try:
        from .mqtt_client import fetch_camera_snapshot
    except ImportError:
        logger.warning("paho-mqtt not installed; falling back to seed camera list")
        return None

    try:
        payload = fetch_camera_snapshot(timeout=timeout)
    except Exception:
        logger.exception("Failed to fetch live DDOT camera registry; falling back to seed list")
        return None

    if not payload:
        return None

    cameras = []
    for entry in payload:
        try:
            cid = str(entry.get("id") or entry.get("cameraId") or entry.get("CameraID"))
            # The real DDOT/Camera payload carries "lat"/"lng" as strings.
            lat = float(entry.get("lat") or entry.get("Latitude"))
            lon = float(entry.get("lng") or entry.get("lon") or entry.get("Longitude"))
        except (TypeError, ValueError):
            continue

        host = entry.get("host")
        stream = entry.get("stream")
        stream_url = entry.get("streamUrl") or entry.get("hls") or entry.get("Url")
        if not stream_url and host and stream:
            stream_url = f"https://{host}/rtplive/{stream}/playlist.m3u8"

        cameras.append(
            {
                "id": cid,
                "name": entry.get("title") or entry.get("name") or entry.get("Location") or f"Camera {cid}",
                "lat": lat,
                "lon": lon,
                # The feed doesn't publish a compass bearing for each camera,
                # so this is a stable per-camera placeholder, same caveat as
                # the seed data (see README's geo-projection limitation).
                "bearing_deg": float(entry.get("bearing", (hash(cid) % 360)) or 0.0),
                "stream_url": stream_url,
                "snapshot_url": entry.get("snapshotUrl") or entry.get("imageUrl"),
                "source": "ddot_mqtt",
            }
        )

    return cameras or None


def sync_camera_registry() -> list[Camera]:
    """Populate/refresh the cameras table and return the active camera rows."""

    cameras: list[dict] | None = None
    if settings.camera_mode == "live":
        cameras = load_live_cameras()

    if cameras is None:
        cameras = load_seed_cameras()

    with session_scope() as session:
        existing = {c.id: c for c in session.query(Camera).all()}
        for cam in cameras:
            row = existing.get(cam["id"])
            if row is None:
                row = Camera(id=cam["id"])
                session.add(row)
            row.name = cam["name"]
            row.lat = cam["lat"]
            row.lon = cam["lon"]
            row.bearing_deg = cam["bearing_deg"]
            row.stream_url = cam["stream_url"]
            row.snapshot_url = cam["snapshot_url"]
            row.source = cam["source"]
            row.active = 1
        session.flush()
        result = session.query(Camera).filter(Camera.active == 1).all()
        session.expunge_all()
        return result
