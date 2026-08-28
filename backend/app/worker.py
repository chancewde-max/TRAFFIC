from __future__ import annotations

import asyncio
import datetime as dt
import logging
import queue
import time

from .broadcast import broadcaster
from .camera_registry import sync_camera_registry
from .config import settings
from .cv.detector import build_detector
from .cv.pipeline import build_pipeline
from .cv.road_snap import fetch_roads_near_cameras
from .db import session_scope
from .models import Camera, CongestionSample, Incident, VehicleTrackSample
from .mqtt_client import IncidentListener
from .services.congestion import summarize
from .services.incidents import IncidentDetector

logger = logging.getLogger(__name__)


async def _record_history_and_incidents(
    camera: Camera, positions: list, incident_detector: IncidentDetector
) -> None:
    """Persists a congestion sample + track samples, and checks for an anomaly.
    Isolated from the main loop so a DB/detector error here logs and skips this
    tick rather than permanently killing the camera's pipeline task."""

    count, avg_speed, level = summarize(positions)
    ts = dt.datetime.now(dt.timezone.utc)

    with session_scope() as session:
        session.add(
            CongestionSample(camera_id=camera.id, vehicle_count=count, avg_speed_mps=avg_speed, level=level)
        )
        for p in positions:
            session.add(
                VehicleTrackSample(
                    camera_id=camera.id,
                    track_id=p.track_id,
                    lat=p.lat,
                    lon=p.lon,
                    speed_mps=p.speed_mps,
                    vehicle_class=p.vehicle_class,
                )
            )

    await broadcaster.publish(
        {
            "type": "congestion",
            "camera_id": camera.id,
            "vehicle_count": count,
            "avg_speed_mps": avg_speed,
            "level": level,
            "ts": ts.isoformat(),
        }
    )

    anomaly = incident_detector.observe(camera.id, count, avg_speed)
    if anomaly:
        kind, severity, description = anomaly
        with session_scope() as session:
            row = Incident(camera_id=camera.id, kind=kind, severity=severity, description=description)
            session.add(row)
            session.flush()
            incident_id = row.id

        await broadcaster.publish(
            {
                "type": "incident",
                "id": incident_id,
                "camera_id": camera.id,
                "kind": kind,
                "severity": severity,
                "description": description,
                "ts": ts.isoformat(),
            }
        )


async def _camera_loop(
    camera: Camera, pipeline, incident_detector: IncidentDetector, stop_event: asyncio.Event
) -> None:
    start = time.monotonic()
    last_history_ts = 0.0
    logger.info("Starting pipeline for camera %s (%s)", camera.id, camera.name)

    try:
        while not stop_event.is_set():
            loop_start = time.monotonic()
            t = loop_start - start
            dt_s = settings.frame_sample_seconds

            try:
                positions = await pipeline.tick_or_read(dt_s, t)
            except Exception:
                logger.exception("Pipeline error on camera %s", camera.id)
                positions = []

            # Always broadcast, even with zero vehicles: the frontend only
            # clears a camera's stale tracks when it receives a fresh (even
            # empty) batch for that camera_id.
            await broadcaster.publish(
                {
                    "type": "vehicles",
                    "camera_id": camera.id,
                    "positions": [p.model_dump() for p in positions],
                }
            )

            if loop_start - last_history_ts >= settings.history_sample_interval_seconds:
                last_history_ts = loop_start
                try:
                    await _record_history_and_incidents(camera, positions, incident_detector)
                except Exception:
                    logger.exception("History/incident recording failed for camera %s", camera.id)

            elapsed = time.monotonic() - loop_start
            await asyncio.sleep(max(0.05, settings.frame_sample_seconds - elapsed))
    finally:
        pipeline.close()
        logger.info("Stopped pipeline for camera %s", camera.id)


async def _relay_ddot_incidents(listener: IncidentListener, stop_event: asyncio.Event) -> None:
    """Drains DDOT's real public incident feed (when CAMERA_MODE=live and
    DDOT_MQTT_HOST is configured) into the same Incident table/broadcast
    channel as our own anomaly-detected incidents."""

    while not stop_event.is_set():
        try:
            payload = await asyncio.to_thread(listener.queue.get, True, 1.0)
        except queue.Empty:
            continue
        except Exception:
            logger.exception("Error reading DDOT incident queue")
            continue

        camera_id = str(
            payload.get("cameraId") or payload.get("CameraID") or payload.get("camera_id") or "unknown"
        )
        description = str(
            payload.get("description") or payload.get("Description") or payload.get("type") or payload
        )[:500]
        severity = "major" if str(payload.get("severity", "")).lower() in ("major", "high", "severe") else "minor"
        ts = dt.datetime.now(dt.timezone.utc)

        try:
            with session_scope() as session:
                row = Incident(camera_id=camera_id, kind="external", severity=severity, description=description)
                session.add(row)
                session.flush()
                incident_id = row.id
        except Exception:
            logger.exception("Failed to persist DDOT incident")
            continue

        await broadcaster.publish(
            {
                "type": "incident",
                "id": incident_id,
                "camera_id": camera_id,
                "kind": "external",
                "severity": severity,
                "description": description,
                "ts": ts.isoformat(),
            }
        )


async def run_worker(stop_event: asyncio.Event) -> None:
    cameras = await asyncio.to_thread(sync_camera_registry)
    cameras = cameras[: settings.max_active_cameras]
    logger.info(
        "Running %d camera pipeline(s) in %s mode", len(cameras), settings.camera_mode
    )

    detector = None
    if settings.camera_mode == "live":
        detector = await asyncio.to_thread(
            build_detector, settings.yolo_model, settings.detection_confidence
        )

    roads_by_camera: dict[str, list] = {}
    if settings.road_snap_enabled:
        roads_by_camera = await asyncio.to_thread(
            fetch_roads_near_cameras, cameras, settings.road_snap_radius_m, settings.road_snap_timeout_s
        )

    incident_detector = IncidentDetector()
    tasks = [
        asyncio.create_task(
            _camera_loop(
                camera,
                build_pipeline(camera, detector, roads_by_camera.get(camera.id)),
                incident_detector,
                stop_event,
            )
        )
        for camera in cameras
    ]

    incident_listener: IncidentListener | None = None
    if settings.camera_mode == "live" and settings.ddot_mqtt_host:
        incident_listener = IncidentListener()
        incident_listener.start()
        tasks.append(asyncio.create_task(_relay_ddot_incidents(incident_listener, stop_event)))

    try:
        if tasks:
            await asyncio.gather(*tasks)
    finally:
        if incident_listener is not None:
            incident_listener.stop()
