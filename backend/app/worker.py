from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time

from .broadcast import broadcaster
from .camera_registry import sync_camera_registry
from .config import settings
from .cv.detector import build_detector
from .cv.pipeline import build_pipeline
from .db import session_scope
from .models import Camera, CongestionSample, Incident, VehicleTrackSample
from .services.congestion import summarize
from .services.incidents import IncidentDetector

logger = logging.getLogger(__name__)


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

            if positions:
                await broadcaster.publish(
                    {
                        "type": "vehicles",
                        "camera_id": camera.id,
                        "positions": [p.model_dump() for p in positions],
                    }
                )

            if loop_start - last_history_ts >= settings.history_sample_interval_seconds:
                last_history_ts = loop_start
                count, avg_speed, level = summarize(positions)
                ts = dt.datetime.now(dt.timezone.utc)

                with session_scope() as session:
                    session.add(
                        CongestionSample(
                            camera_id=camera.id, vehicle_count=count, avg_speed_mps=avg_speed, level=level
                        )
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
                        row = Incident(
                            camera_id=camera.id, kind=kind, severity=severity, description=description
                        )
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

            elapsed = time.monotonic() - loop_start
            await asyncio.sleep(max(0.05, settings.frame_sample_seconds - elapsed))
    finally:
        pipeline.close()
        logger.info("Stopped pipeline for camera %s", camera.id)


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

    incident_detector = IncidentDetector()
    tasks = [
        asyncio.create_task(_camera_loop(camera, build_pipeline(camera, detector), incident_detector, stop_event))
        for camera in cameras
    ]
    if tasks:
        await asyncio.gather(*tasks)
