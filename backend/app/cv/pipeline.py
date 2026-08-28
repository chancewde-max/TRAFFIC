"""Per-camera pipelines that produce a stream of VehiclePosition updates.

Two implementations share the same interface (`tick_or_read` -> list[VehiclePosition]):

* MockCameraSimulator -- synthesizes plausible vehicle motion near a camera's
  location with zero external dependencies (no video, no GPU). This is the
  default (CAMERA_MODE=mock) so the whole app runs end-to-end out of the box.

* LiveCameraPipeline -- pulls real frames from the camera's HLS/MJPEG stream
  with OpenCV, runs YOLO vehicle detection + IOU tracking, and projects
  detections to approximate geo positions. Used when CAMERA_MODE=live and the
  optional `ultralytics`/`opencv-python`/`torch` dependencies are installed.
"""

from __future__ import annotations

import logging
import math
import random

from ..config import settings
from ..models import Camera
from ..schemas import VehiclePosition
from .geo_projection import FAR_M, NEAR_M, bbox_center_uv, project_detection
from .tracker import IouTracker

logger = logging.getLogger(__name__)


class MockCameraSimulator:
    def __init__(self, camera: Camera, seed: int | None = None) -> None:
        self.camera = camera
        rng_seed = seed if seed is not None else (hash(camera.id) & 0xFFFFFFFF)
        self.rng = random.Random(rng_seed)
        self.base_density = self.rng.uniform(2, 14)
        self.density_phase = self.rng.uniform(0, 2 * math.pi)
        self._next_track_id = 1
        self.vehicles: dict[int, dict] = {}
        for _ in range(int(self.base_density)):
            self._spawn()

    def _target_density(self, t: float) -> float:
        wobble = 1 + 0.6 * math.sin(t / 90.0 + self.density_phase)
        return max(1.0, self.base_density * wobble)

    def _spawn(self) -> None:
        tid = self._next_track_id
        self._next_track_id += 1
        self.vehicles[tid] = {
            "u": self.rng.uniform(-0.4, 0.4),
            "v": self.rng.uniform(0.0, 0.15),
            "speed": self.rng.uniform(0.04, 0.11),  # fraction of camera depth-of-view per second
            "vehicle_class": self.rng.choices(
                ["car", "truck", "bus", "motorcycle"], weights=[80, 10, 5, 5]
            )[0],
        }

    async def tick_or_read(self, dt: float, t: float) -> list[VehiclePosition]:
        target = self._target_density(t)
        if len(self.vehicles) < target and self.rng.random() < 0.5:
            self._spawn()
        if len(self.vehicles) > target + 3 and self.rng.random() < 0.3 and self.vehicles:
            del self.vehicles[self.rng.choice(list(self.vehicles.keys()))]

        congestion_factor = min(1.0, len(self.vehicles) / 16.0)
        positions: list[VehiclePosition] = []
        for tid, veh in list(self.vehicles.items()):
            speed = veh["speed"] * (1.0 - 0.6 * congestion_factor)
            veh["v"] += speed * dt
            veh["u"] = max(-0.48, min(0.48, veh["u"] + self.rng.uniform(-0.01, 0.01)))
            if veh["v"] >= 1.0:
                del self.vehicles[tid]
                continue

            point = project_detection(
                self.camera.lat, self.camera.lon, self.camera.bearing_deg, veh["u"], veh["v"]
            )
            # `speed` is a fraction of the camera's depth-of-view traversed per
            # second, so multiplying by the depth range converts it to m/s.
            speed_mps = round(min(speed * (FAR_M - NEAR_M), 20.0), 2)
            positions.append(
                VehiclePosition(
                    camera_id=self.camera.id,
                    track_id=tid,
                    lat=point.lat,
                    lon=point.lon,
                    heading_deg=point.heading_deg,
                    speed_mps=speed_mps,
                    vehicle_class=veh["vehicle_class"],
                )
            )
        return positions

    def close(self) -> None:
        pass


class LiveCameraPipeline:
    def __init__(self, camera: Camera, detector) -> None:
        import cv2  # deferred import: optional dependency

        self._cv2 = cv2
        self.camera = camera
        self.detector = detector
        self.tracker = IouTracker()
        self.cap = None

    async def _ensure_open(self) -> None:
        import asyncio

        if self.cap is None:
            self.cap = await asyncio.to_thread(self._cv2.VideoCapture, self.camera.stream_url)

    async def tick_or_read(self, dt: float, t: float) -> list[VehiclePosition]:
        import asyncio

        await self._ensure_open()
        ok, frame = await asyncio.to_thread(self.cap.read)
        if not ok or frame is None:
            logger.warning("No frame from camera %s (%s)", self.camera.id, self.camera.stream_url)
            return []

        detections = await asyncio.to_thread(self.detector.detect, frame)
        tracked = self.tracker.update(detections)

        positions = []
        for obj in tracked:
            u, v = bbox_center_uv(obj.bbox)
            point = project_detection(self.camera.lat, self.camera.lon, self.camera.bearing_deg, u, v)
            positions.append(
                VehiclePosition(
                    camera_id=self.camera.id,
                    track_id=obj.track_id,
                    lat=point.lat,
                    lon=point.lon,
                    heading_deg=point.heading_deg,
                    speed_mps=None,
                    vehicle_class=obj.vehicle_class,
                )
            )
        return positions

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()


def build_pipeline(camera: Camera, detector=None):
    if settings.camera_mode == "live" and camera.stream_url and detector is not None:
        try:
            return LiveCameraPipeline(camera, detector)
        except Exception:
            logger.exception("Falling back to mock simulator for camera %s", camera.id)
    return MockCameraSimulator(camera)
