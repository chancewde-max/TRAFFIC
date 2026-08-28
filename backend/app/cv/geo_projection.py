"""Approximate pixel -> geographic projection for a single traffic camera.

Public traffic cameras like DDOT's don't publish per-camera calibration
(intrinsics/extrinsics), so a true homography from image pixels to lat/lon
isn't available. Instead we use a simple ground-plane pinhole approximation:

  * the camera looks along `bearing_deg` (compass heading)
  * a detection's horizontal position in frame maps to an angular offset
    from that bearing, using an assumed field of view
  * a detection's vertical position in frame maps to an assumed distance
    from the camera (higher in frame = further away), between NEAR_M and
    FAR_M

This places tracked vehicles at a *plausible* position near their camera
rather than a calibrated one -- good enough for a city-wide "cars are moving
roughly here" visualization, not for lane-level accuracy. This limitation is
called out in the README.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEG_PER_METER_LAT = 1.0 / 111_320.0

DEFAULT_FOV_DEG = 70.0
NEAR_M = 6.0
FAR_M = 70.0


def meters_per_degree_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


@dataclass
class GeoPoint:
    lat: float
    lon: float
    heading_deg: float


def project_detection(
    camera_lat: float,
    camera_lon: float,
    camera_bearing_deg: float,
    u: float,
    v: float,
    fov_deg: float = DEFAULT_FOV_DEG,
    near_m: float = NEAR_M,
    far_m: float = FAR_M,
) -> GeoPoint:
    """u: horizontal position in [-0.5, 0.5], 0 = frame center.
    v: vertical position in [0, 1], 0 = top of frame (far), 1 = bottom (near).
    """

    u = max(-0.5, min(0.5, u))
    v = max(0.0, min(1.0, v))

    depth_m = far_m - v * (far_m - near_m)
    lateral_deg = u * fov_deg
    heading_deg = (camera_bearing_deg + lateral_deg) % 360.0

    dx_east = depth_m * math.sin(math.radians(heading_deg))
    dy_north = depth_m * math.cos(math.radians(heading_deg))

    dlat = dy_north * DEG_PER_METER_LAT
    dlon = dx_east / meters_per_degree_lon(camera_lat)

    return GeoPoint(lat=camera_lat + dlat, lon=camera_lon + dlon, heading_deg=heading_deg)


def bbox_center_uv(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0 - 0.5
    cy = (y1 + y2) / 2.0
    return cx, cy


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
