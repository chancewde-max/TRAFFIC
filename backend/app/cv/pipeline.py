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
from .road_geometry import LatLon, offset_point, point_at_distance, polyline_length_m
from .tracker import IouTracker

logger = logging.getLogger(__name__)

# Car-following (simplified IDM-style ACC) tuning for road-snapped traffic.
VEHICLE_LENGTH_M = 4.5
MIN_GAP_M = 2.5
TIME_HEADWAY_S = 1.4
MAX_ACCEL_MPS2 = 2.2
MAX_DECEL_MPS2 = 4.0
# Half of a typical US travel lane -- keeps each direction on its own side of
# the road's centerline instead of both directions sharing one line.
LANE_OFFSET_M = 2.6


class MockCameraSimulator:
    def __init__(
        self,
        camera: Camera,
        road_points: list[LatLon] | None = None,
        seed: int | None = None,
    ) -> None:
        self.camera = camera
        # When a real nearby road was found (see road_snap.py), vehicles move
        # along its actual polyline instead of the synthetic radial cone --
        # real streets, real turns, not a straight line through the block.
        self.road_points = road_points if road_points and len(road_points) >= 2 else None
        self.road_length_m = polyline_length_m(self.road_points) if self.road_points else 0.0

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
        vehicle_class = self.rng.choices(
            ["car", "truck", "bus", "motorcycle"], weights=[80, 10, 5, 5]
        )[0]

        if self.road_points is not None and self.road_length_m > 1.0:
            direction = self.rng.choice((1, -1))
            edge_margin = min(15.0, self.road_length_m * 0.15)
            if direction == 1:
                s = self.rng.uniform(0.0, edge_margin)
            else:
                s = self.rng.uniform(self.road_length_m - edge_margin, self.road_length_m)
            desired_speed = self.rng.uniform(3.0, 9.0)  # m/s, this vehicle's free-flow speed
            self.vehicles[tid] = {
                "s": s,
                "direction": direction,
                "speed": desired_speed,
                "cur_speed": desired_speed,
                "vehicle_class": vehicle_class,
            }
        else:
            self.vehicles[tid] = {
                "u": self.rng.uniform(-0.4, 0.4),
                "v": self.rng.uniform(0.0, 0.15),
                "speed": self.rng.uniform(0.04, 0.11),  # fraction of depth-of-view per second
                "vehicle_class": vehicle_class,
            }

    def _car_following_speeds(self, congestion_factor: float) -> dict[int, float]:
        """Desired speed per vehicle after applying a lightweight ACC/IDM-style
        model: each vehicle targets its free-flow speed unless the vehicle
        ahead of it (same direction) is closer than its desired following
        gap, in which case it slows to keep that gap. Prevents vehicles from
        overlapping/passing through each other and produces realistic
        bunching-up under congestion instead of just a uniform speed
        reduction."""

        desired: dict[int, float] = {}
        for direction in (1, -1):
            ids = [tid for tid, v in self.vehicles.items() if v["direction"] == direction]
            # Sort leader-first: for forward travel the leader has the largest
            # `s`; for reverse travel the leader has the smallest `s`.
            ids.sort(key=lambda tid: self.vehicles[tid]["s"], reverse=(direction == 1))

            lead_s: float | None = None
            for tid in ids:
                veh = self.vehicles[tid]
                free_flow = veh["speed"] * (1.0 - 0.6 * congestion_factor)
                if lead_s is not None:
                    gap = abs(lead_s - veh["s"]) - VEHICLE_LENGTH_M
                    desired_gap = MIN_GAP_M + veh["cur_speed"] * TIME_HEADWAY_S
                    if gap <= 0:
                        free_flow = 0.0
                    elif gap < desired_gap:
                        free_flow *= max(0.0, gap / desired_gap)
                desired[tid] = max(0.0, free_flow)
                lead_s = veh["s"]
        return desired

    def _tick_road(self, dt: float, congestion_factor: float) -> list[VehiclePosition]:
        positions: list[VehiclePosition] = []
        desired_speeds = self._car_following_speeds(congestion_factor)

        for tid, veh in list(self.vehicles.items()):
            # Smoothly accelerate/decelerate toward the desired speed instead
            # of snapping to it, so braking for traffic ahead (or a red light
            # at the edge of the road) looks like real driving.
            delta = desired_speeds[tid] - veh["cur_speed"]
            max_delta = (MAX_ACCEL_MPS2 if delta > 0 else MAX_DECEL_MPS2) * dt
            veh["cur_speed"] += max(-max_delta, min(max_delta, delta))
            veh["cur_speed"] = max(0.0, veh["cur_speed"])

            veh["s"] += veh["direction"] * veh["cur_speed"] * dt
            if veh["s"] <= 0.0 or veh["s"] >= self.road_length_m:
                del self.vehicles[tid]
                continue

            road_point = point_at_distance(self.road_points, veh["s"])
            heading = road_point.heading_deg if veh["direction"] == 1 else (road_point.heading_deg + 180) % 360
            lat, lon = offset_point(road_point.lat, road_point.lon, heading, LANE_OFFSET_M)
            positions.append(
                VehiclePosition(
                    camera_id=self.camera.id,
                    track_id=tid,
                    lat=lat,
                    lon=lon,
                    heading_deg=heading,
                    speed_mps=round(min(veh["cur_speed"], 20.0), 2),
                    vehicle_class=veh["vehicle_class"],
                )
            )
        return positions

    def _tick_radial(self, dt: float, congestion_factor: float) -> list[VehiclePosition]:
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

    async def tick_or_read(self, dt: float, t: float) -> list[VehiclePosition]:
        target = self._target_density(t)
        if len(self.vehicles) < target and self.rng.random() < 0.5:
            self._spawn()
        if len(self.vehicles) > target + 3 and self.rng.random() < 0.3 and self.vehicles:
            del self.vehicles[self.rng.choice(list(self.vehicles.keys()))]

        congestion_factor = min(1.0, len(self.vehicles) / 16.0)
        if self.road_points is not None:
            return self._tick_road(dt, congestion_factor)
        return self._tick_radial(dt, congestion_factor)

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


def build_pipeline(camera: Camera, detector=None, road_points: list[LatLon] | None = None):
    if settings.camera_mode == "live" and camera.stream_url and detector is not None:
        try:
            return LiveCameraPipeline(camera, detector)
        except Exception:
            logger.exception("Falling back to mock simulator for camera %s", camera.id)
    return MockCameraSimulator(camera, road_points=road_points)
